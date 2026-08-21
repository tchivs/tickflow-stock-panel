"""Contract tests for the local stockdb provider (LOCAL-01 / LOCAL-03).

Hermetic — canned live-probe response bodies frozen under
``tests/fixtures/stockdb/``, zero network (mirrors test_ifzq_provider.py's
_JsonTransport injection, extended with status_code/headers).

Locks the three wire normalization differences (measured 2026-08-07):
  * symbol prefix form ``SH600519`` -> lake suffix form ``600519.SH``
  * volume_hand (手) is identity (x1) — the lake stores 手, never x100
  * aware Asia/Shanghai date/bar_time -> naive lake wall clock

plus the typed error contract (401 no-retry / 429 Retry-After single retry
then raise / 400 typed / 200+[] legitimate vacuum), current DataResponse daily
semantics (`{"ok": true, "state": "ok", "data": {sym: [bars]}}`, chunked <=
batch_size), direct/enveloped minute responses, and rate-limit alignment
(rpm=120).

Import of the provider module fails today (classes not yet implemented) —
that red state is the contract-first acceptance step.
"""
from __future__ import annotations

import json as _json
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import polars as pl
import pytest

from app.data_providers.stockdb_provider import (
    StockDBAuthError,
    StockDBBadRequest,
    StockDBProtocolError,
    StockDBProvider,
    StockDBRateLimited,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "stockdb"


def _load_fixture(name: str) -> Any:
    with open(_FIXTURES / name, encoding="utf-8") as fh:
        return _json.load(fh)


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: Any,
        headers: dict[str, str] | None = None,
        url: str = "http://stockdb.test/v1/query/daily",
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self._url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            req = httpx.Request("GET", self._url)
            raise httpx.HTTPStatusError(
                str(self.status_code), request=req, response=httpx.Response(self.status_code, request=req)
            )

    @property
    def text(self) -> str:
        return self._body if isinstance(self._body, str) else _json.dumps(self._body)

    def json(self) -> Any:
        return self._body if not isinstance(self._body, str) else _json.loads(self._body)


class _JsonTransport:
    """Canned router keyed by request path; records (url, params) per call.

    Route values are either a body (dict/list -> 200) or a list of
    ``(status_code, body, headers)`` tuples consumed in order (for retry
    sequences such as 429 -> 200).
    """

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def get(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any) -> _FakeResponse:
        self.calls.append((url, params))
        route = self.routes[urlparse(url).path]
        if isinstance(route, list) and route and isinstance(route[0], tuple):
            status, body, headers = route.pop(0)
        else:
            status, body, headers = 200, route, {}
        return _FakeResponse(status, body, headers, url=url)

    def close(self) -> None:
        pass


def _provider(routes: dict[str, Any], **kwargs: Any) -> StockDBProvider:
    p = StockDBProvider(base_url="http://stockdb.test", api_key="test-key", **kwargs)
    p._client = _JsonTransport(routes)
    return p


def _daily_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "state": "ok", "data": data}


# -- 三差异契约 (LOCAL-03) ---------------------------------------------------


def test_daily_normalizes_symbol_to_suffix_form():
    p = _provider({"/v1/query/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["SH600519"])
    assert df["symbol"][0] == "600519.SH"  # 差异①: 前缀 -> 后缀, 同股单键


def test_daily_volume_is_identity_not_hand_to_share():
    p = _provider({"/v1/query/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["SH600519"])
    assert df["volume"][0] == 42689.0  # 差异②: 恒等 x1 — 湖实测 = 手
    assert df["volume"][0] != 42689.0 * 100  # 回归: 永不做 x100 失真


def test_daily_date_is_naive_trade_date():
    p = _provider({"/v1/query/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["SH600519"])
    assert str(df["date"][0]) == "2026-08-05"  # 差异③: aware -> naive date
    assert df["date"].dtype == pl.Date


def test_request_symbols_sent_in_prefix_form():
    """湖内后缀形态输入 -> 请求侧前缀形态 (600519.SH -> SH600519)."""
    p = _provider({"/v1/query/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["600519.SH"])
    assert p._client.calls[0][1]["symbols"] == "SH600519"
    assert df["symbol"][0] == "600519.SH"


# -- 错误契约 (LOCAL-01, typed 窄捕获 — 禁 catch-all 空帧吞错) ----------------


def test_401_raises_typed_auth_error_not_empty():
    p = _provider({"/v1/query/daily": [(401, _load_fixture("error_401.json"), {})]})
    with pytest.raises(StockDBAuthError):
        p.get_daily(["SH600519"])
    assert len(p._client.calls) == 1  # 401 不重试 (配置错误信号)


def test_429_honors_retry_after_then_raises(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.data_providers.stockdb_provider.time.sleep", lambda s: sleeps.append(s))
    p = _provider({
        "/v1/query/daily": [
            (429, _load_fixture("error_429.json"), {"Retry-After": "50"}),
            (429, _load_fixture("error_429.json"), {"Retry-After": "50"}),
        ],
    })
    with pytest.raises(StockDBRateLimited):
        p.get_daily(["SH600519"])
    assert sleeps == [50.0]  # 遵守 Retry-After 等待
    assert len(p._client.calls) == 2  # 重试恰好 1 次后上抛


def test_429_retries_once_then_returns_frame(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.data_providers.stockdb_provider.time.sleep", lambda s: sleeps.append(s))
    p = _provider({
        "/v1/query/daily": [
            (429, _load_fixture("error_429.json"), {"Retry-After": "50"}),
            (200, _load_fixture("daily_sh600519_20260805.json"), {}),
        ],
    })
    df = p.get_daily(["SH600519"])
    assert sleeps == [50.0]
    assert not df.is_empty()
    assert df["symbol"][0] == "600519.SH"


def test_400_raises_typed_bad_request():
    p = _provider({"/v1/query/daily": [(400, {"error": "bad_request", "code": 400}, {})]})
    with pytest.raises(StockDBBadRequest):
        p.get_daily(["SH600519"])


def test_200_empty_bars_is_legitimate_vacuum():
    """200 + 空 bars = 真空 (该窗口无数据), 返回空帧绝不抛."""
    p = _provider({"/v1/query/daily": _daily_response({"SH600519": []})})
    df = p.get_daily(["SH600519"])
    assert df.is_empty()


def test_200_malformed_daily_payload_raises_protocol_error():
    p = _provider({"/v1/query/daily": {"ok": True, "state": "ok"}})
    with pytest.raises(StockDBProtocolError):
        p.get_daily(["SH600519"])


def test_data_response_failure_state_does_not_become_empty_frame():
    p = _provider({
        "/v1/query/daily": {
            "ok": False,
            "state": "unavailable",
            "data": {},
            "error": "local lake unavailable",
        }
    })
    with pytest.raises(StockDBProtocolError):
        p.get_daily(["SH600519"])


# -- 批语义 + 限频对齐 + 分钟端日语义 (LOCAL-01) ------------------------------


def test_batch_endpoint_parses_sym_bars_dict():
    """批响应 {sym: [bars]} dict: 两 symbol 行都在, 各自归一化 (后缀形态)."""
    p = _provider({"/v1/query/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["SH600519", "SH600000"])
    assert sorted(df["symbol"].unique().to_list()) == ["600000.SH", "600519.SH"]
    assert len(df) == 2


def test_get_daily_chunks_by_batch_size(monkeypatch):
    """3 symbols + batch_size=2 -> 2 次 /v1/query/daily 调用, 首次 2 个末次 1 个."""
    monkeypatch.setattr("app.data_providers.stockdb_provider.sleep_between_batches", lambda i, rpm: None)
    p = _provider({"/v1/query/daily": _daily_response({"SH600519": [], "SH600000": [], "SZ000001": []})}, batch_size=2)
    p.get_daily(["600519.SH", "600000.SH", "000001.SZ"])
    params = [params for _, params in p._client.calls]
    assert len(params) == 2
    assert params[0]["symbols"] == "SH600519,SH600000"
    assert params[1]["symbols"] == "SZ000001"


def test_sleep_between_batches_aligns_to_server_rpm(monkeypatch):
    """进程级共享槽 rpm 对齐服务端 daily/minute 档位 (120/min)."""
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "app.data_providers.stockdb_provider.sleep_between_batches",
        lambda i, rpm: calls.append((i, rpm)),
    )
    p = _provider({"/v1/query/daily": _daily_response({"SH600519": [], "SH600000": []})}, batch_size=1)
    p.get_daily(["600519.SH", "600000.SH"])
    assert calls == [(0, 120), (1, 120)]  # 默认 rpm=120


def test_minute_end_excludes_end_day(monkeypatch):
    """分钟窗口不含 end 日 (实测 Pitfall 3): end 请求参数 = end_time + 1day."""
    monkeypatch.setattr("app.data_providers.stockdb_provider.sleep_between_batches", lambda i, rpm: None)
    p = _provider({"/v1/minute": {"SH600519": []}})
    p.get_minute(["600519.SH"], end_time=datetime(2026, 8, 5))
    params = p._client.calls[0][1]
    assert params["end"] == "2026-08-06"
    assert params["freq"] == 1  # 服务端 freq 为 int 枚举


def test_daily_end_includes_end_day(monkeypatch):
    """日K窗口含 end 日 (实测): end 请求参数原样传递."""
    monkeypatch.setattr("app.data_providers.stockdb_provider.sleep_between_batches", lambda i, rpm: None)
    p = _provider({"/v1/query/daily": _daily_response({"SH600519": []})})
    p.get_daily(["600519.SH"], end_time=datetime(2026, 8, 5))
    assert p._client.calls[0][1]["end"] == "2026-08-05"


def test_minute_bar_time_is_naive():
    """分钟 bar_time aware +08:00 -> 输出 naive 北京墙钟 (无 tzinfo)."""
    p = _provider({"/v1/minute": _load_fixture("minute_sh600519_20260805.json")})
    df = p.get_minute(["SH600519"])
    dt = df["datetime"][0]
    assert dt == datetime(2026, 8, 5, 9, 30)
    assert dt.tzinfo is None
    assert "freq" in df.columns and df["freq"][0] == "1m"


def test_minute_accepts_current_data_response_envelope():
    p = _provider({
        "/v1/minute": {
            "ok": True,
            "state": "ok",
            "data": _load_fixture("minute_sh600519_20260805.json"),
            "schema": {"schema_version": 1, "contract_version": "1.1"},
        }
    })
    df = p.get_minute(["SH600519"])
    assert df.height == 2
    assert df["symbol"][0] == "600519.SH"


def test_indicators_uses_stockdb_sdk_route_and_numeric_params():
    p = _provider({
        "/v1/indicators/SH600519": [{"date": "2026-08-05", "ma20": 1300.0}]
    })
    rows = p.get_indicators(
        "600519.SH",
        name="ma",
        start_time=datetime(2026, 8, 1),
        end_time=datetime(2026, 8, 5),
        period=20,
    )
    assert rows == [{"date": "2026-08-05", "ma20": 1300.0}]
    assert p._client.calls[0][1] == {
        "name": "ma",
        "start": "2026-08-01",
        "end": "2026-08-05",
        "adjust": "none",
        "period": 20,
    }


def test_push_alerts_returns_none_when_feature_is_disabled():
    p = _provider({"/v1/push/alerts": [(404, {"detail": "disabled"}, {})]})
    assert p.get_push_alerts(threshold=7.0, limit=20) is None


def test_429_retry_after_header_controls_wait(monkeypatch):
    """Retry-After 头 (50s) 决定重试前等待; 重试成功后返回正常帧."""
    sleeps: list[float] = []
    monkeypatch.setattr("app.data_providers.stockdb_provider.time.sleep", lambda s: sleeps.append(s))
    p = _provider({
        "/v1/query/daily": [
            (429, _load_fixture("error_429.json"), {"Retry-After": "50"}),
            (200, _load_fixture("daily_sh600519_20260805.json"), {}),
        ],
    })
    df = p.get_daily(["SH600519"])
    assert sleeps == [50.0]
    assert not df.is_empty()


def test_429_retry_after_falls_back_to_body(monkeypatch):
    """无 Retry-After 头 -> 回退 body retry_after (实测 50)."""
    sleeps: list[float] = []
    monkeypatch.setattr("app.data_providers.stockdb_provider.time.sleep", lambda s: sleeps.append(s))
    p = _provider({
        "/v1/query/daily": [
            (429, _load_fixture("error_429.json"), {}),
            (200, _load_fixture("daily_sh600519_20260805.json"), {}),
        ],
    })
    df = p.get_daily(["SH600519"])
    assert sleeps == [50.0]
    assert not df.is_empty()


# -- tick 端点 (43-01): GET /v1/ticks/{sym}?date=YYYYMMDD ----------------------


def test_get_ticks_requests_date_and_returns_raw_list():
    """请求必带 date=T (Pitfall 3: 无 date 服务端回退上一交易日); 返回原始 TickBar list。

    归一化 (staging 10 列) 交给采集层, provider 只透传原始 JSON list。
    """
    rows = [
        {"symbol": "SH600519", "trade_date": "20260807", "time": "09:25:00",
         "price": 1308.66, "vol_hand": 173, "num_trades": 120, "buyorsell": 2,
         "source": "eastmoney", "fetched_at": None, "ingested_at": None},
    ]
    p = _provider({"/v1/ticks/SH600519": rows})
    out = p.get_ticks("SH600519", _date(2026, 8, 7))
    assert out == rows  # 原样透传 (无归一化, 契约单点归采集层)
    url, params = p._client.calls[0]
    assert urlparse(url).path == "/v1/ticks/SH600519"
    assert params == {"date": "20260807"}  # 请求必带 date=T


def test_get_ticks_accepts_suffix_input():
    """湖内后缀形态输入 -> 请求侧前缀形态 (镜像 daily/minute 语义)。"""
    p = _provider({"/v1/ticks/SH600519": []})
    assert p.get_ticks("600519.SH", _date(2026, 8, 7)) == []
    url, params = p._client.calls[0]
    assert urlparse(url).path == "/v1/ticks/SH600519"
    assert params == {"date": "20260807"}


# ================================================================
# LOCAL-01 硬验收 — 只读 HTTP 客户端 AST 守卫 (POOL-03 模板改形)
# ================================================================
#
# stockdb_provider.py 是纯只读 HTTP 客户端, 四判据:
#   A) 无执行族 import (镜像 POOL-03 E1: _imported_module_names 判据)
#   B) 无写模式 token (open(写模式 / write_parquet / os.replace / unlink / mkdir)
#   C) HTTP 动词仅 GET (client.get( 存在, 无 client.post/put/delete/patch)
#   D) api_key 只出现于 headers dict (X-API-Key 仅 headers 行 — 禁 URL 传参)
# 过滤规则镜像 test_pool_hub.py:951-972 同款判据并按 data_providers 面裁剪。
# ---------------------------------------------------------------------------


def _provider_source() -> str:
    backend = Path(__file__).resolve().parents[1]
    return (backend / "app" / "data_providers" / "stockdb_provider.py").read_text(encoding="utf-8")


def _imported_module_names(source: str) -> list[str]:
    import ast as _ast

    tree = _ast.parse(source)
    names: list[str] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, _ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _strip_comments_docstrings(source: str) -> str:
    """tokenize 级剔除注释与文档串 (镜像 POOL-03「grep 过滤注释/文档串」判据)。

    按 token 覆盖的行号剔除: 注释 token 与三引号文档串 token 起始行整体丢弃
    (INDENT 等 token 的 line 属性会携带文档串首行, 不能按 tok.line 过滤)。
    """
    import io
    import tokenize

    skip_rows: set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            skip_rows.add(tok.start[0])
        elif tok.type == tokenize.STRING and tok.string.startswith(('"""', "'''")):
            skip_rows.update(range(tok.start[0], tok.end[0] + 1))
    return "\n".join(
        ln for i, ln in enumerate(source.splitlines(), 1) if i not in skip_rows
    )


def test_stockdb_provider_is_read_only_http_client():
    """LOCAL-01 硬验收: provider 无执行族 import / 无写模式 / 仅 GET / api_key 仅 headers。"""
    import re

    src = _provider_source()

    # A) 无执行族 import (POOL-03 E1 判据: broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托)
    execution_token = re.compile(
        r"broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托",
        re.IGNORECASE,
    )
    for module in _imported_module_names(src):
        assert not execution_token.search(module), (
            f"stockdb_provider 引入了执行族模块: {module}"
        )

    # B) 无写模式 token
    code = _strip_comments_docstrings(src)
    write_patterns = (
        re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']w"),
        re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']wb"),
        re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']a"),
        re.compile(r"write_parquet"),
        re.compile(r"os\.replace"),
        re.compile(r"unlink\s*\("),
        re.compile(r"mkdir\s*\("),
    )
    for pattern in write_patterns:
        assert not pattern.search(code), f"stockdb_provider 出现写路径: {pattern.pattern}"

    # C) HTTP 动词仅 GET
    assert "client.get(" in code, "stockdb_provider 缺少只读 GET 请求面"
    for verb in ("post", "put", "delete", "patch"):
        assert f"client.{verb}(" not in code, f"stockdb_provider 出现非 GET HTTP 动词: client.{verb}("

    # D) api_key 仅 headers dict (禁 URL 传参 — LOCAL-01 硬验收)
    key_lines = [ln for ln in code.splitlines() if "X-API-Key" in ln]
    assert key_lines, "stockdb_provider 缺少 X-API-Key 注入"
    for ln in key_lines:
        assert "headers" in ln, f"api_key 出现在非 headers 行: {ln.strip()}"
