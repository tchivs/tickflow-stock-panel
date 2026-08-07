"""Contract tests for the local stockdb provider (LOCAL-01 / LOCAL-03).

Hermetic — canned live-probe response bodies frozen under
``tests/fixtures/stockdb/``, zero network (mirrors test_ifzq_provider.py's
_JsonTransport injection, extended with status_code/headers).

Locks the three wire normalization differences (measured 2026-08-07):
  * symbol prefix form ``SH600519`` -> lake suffix form ``600519.SH``
  * volume_hand (手) is identity (x1) — the lake stores 手, never x100
  * aware Asia/Shanghai date/bar_time -> naive lake wall clock

plus the typed error contract (401 no-retry / 429 Retry-After single retry
then raise / 400 typed / 200+[] legitimate vacuum), batch semantics
({sym: [bars]}, chunked <= batch_size) and rate-limit alignment (rpm=120).

Import of the provider module fails today (classes not yet implemented) —
that red state is the contract-first acceptance step.
"""
from __future__ import annotations

import json as _json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import polars as pl
import pytest

from app.data_providers.stockdb_provider import (
    StockDBProvider,
    StockDBAuthError,
    StockDBRateLimited,
    StockDBBadRequest,
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
        url: str = "http://stockdb.test/v1/daily",
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


# -- 三差异契约 (LOCAL-03) ---------------------------------------------------


def test_daily_normalizes_symbol_to_suffix_form():
    p = _provider({"/v1/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["SH600519"])
    assert df["symbol"][0] == "600519.SH"  # 差异①: 前缀 -> 后缀, 同股单键


def test_daily_volume_is_identity_not_hand_to_share():
    p = _provider({"/v1/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["SH600519"])
    assert df["volume"][0] == 42689.0  # 差异②: 恒等 x1 — 湖实测 = 手
    assert df["volume"][0] != 42689.0 * 100  # 回归: 永不做 x100 失真


def test_daily_date_is_naive_trade_date():
    p = _provider({"/v1/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["SH600519"])
    assert str(df["date"][0]) == "2026-08-05"  # 差异③: aware -> naive date
    assert df["date"].dtype == pl.Date


def test_request_symbols_sent_in_prefix_form():
    """湖内后缀形态输入 -> 请求侧前缀形态 (600519.SH -> SH600519)."""
    p = _provider({"/v1/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["600519.SH"])
    assert p._client.calls[0][1]["symbols"] == "SH600519"
    assert df["symbol"][0] == "600519.SH"


# -- 错误契约 (LOCAL-01, typed 窄捕获 — 禁 catch-all 空帧吞错) ----------------


def test_401_raises_typed_auth_error_not_empty():
    p = _provider({"/v1/daily": [(401, _load_fixture("error_401.json"), {})]})
    with pytest.raises(StockDBAuthError):
        p.get_daily(["SH600519"])
    assert len(p._client.calls) == 1  # 401 不重试 (配置错误信号)


def test_429_honors_retry_after_then_raises(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.data_providers.stockdb_provider.time.sleep", lambda s: sleeps.append(s))
    p = _provider({
        "/v1/daily": [
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
        "/v1/daily": [
            (429, _load_fixture("error_429.json"), {"Retry-After": "50"}),
            (200, _load_fixture("daily_sh600519_20260805.json"), {}),
        ],
    })
    df = p.get_daily(["SH600519"])
    assert sleeps == [50.0]
    assert not df.is_empty()
    assert df["symbol"][0] == "600519.SH"


def test_400_raises_typed_bad_request():
    p = _provider({"/v1/daily": [(400, {"error": "bad_request", "code": 400}, {})]})
    with pytest.raises(StockDBBadRequest):
        p.get_daily(["SH600519"])


def test_200_empty_bars_is_legitimate_vacuum():
    """200 + 空 bars = 真空 (该窗口无数据), 返回空帧绝不抛."""
    p = _provider({"/v1/daily": {"SH600519": []}})
    df = p.get_daily(["SH600519"])
    assert df.is_empty()


# -- 批语义 + 限频对齐 + 分钟端日语义 (LOCAL-01) ------------------------------


def test_batch_endpoint_parses_sym_bars_dict():
    """批响应 {sym: [bars]} dict: 两 symbol 行都在, 各自归一化 (后缀形态)."""
    p = _provider({"/v1/daily": _load_fixture("daily_sh600519_20260805.json")})
    df = p.get_daily(["SH600519", "SH600000"])
    assert sorted(df["symbol"].unique().to_list()) == ["600000.SH", "600519.SH"]
    assert len(df) == 2


def test_get_daily_chunks_by_batch_size(monkeypatch):
    """3 symbols + batch_size=2 -> 2 次 /v1/daily 调用, 首次 2 个末次 1 个."""
    monkeypatch.setattr("app.data_providers.stockdb_provider.sleep_between_batches", lambda i, rpm: None)
    p = _provider({"/v1/daily": {"SH600519": [], "SH600000": [], "SZ000001": []}}, batch_size=2)
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
    p = _provider({"/v1/daily": {"SH600519": [], "SH600000": []}}, batch_size=1)
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
    p = _provider({"/v1/daily": {"SH600519": []}})
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


def test_429_retry_after_header_controls_wait(monkeypatch):
    """Retry-After 头 (50s) 决定重试前等待; 重试成功后返回正常帧."""
    sleeps: list[float] = []
    monkeypatch.setattr("app.data_providers.stockdb_provider.time.sleep", lambda s: sleeps.append(s))
    p = _provider({
        "/v1/daily": [
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
        "/v1/daily": [
            (429, _load_fixture("error_429.json"), {}),
            (200, _load_fixture("daily_sh600519_20260805.json"), {}),
        ],
    })
    df = p.get_daily(["SH600519"])
    assert sleeps == [50.0]
    assert not df.is_empty()
