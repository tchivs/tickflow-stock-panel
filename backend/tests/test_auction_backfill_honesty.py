"""AQ-04 诚实套件 — 失败台账终态形状 / BJ 空响应 / 交叉校验 / POOL-03 AST 守卫。

Hermetic, 不碰真实数据目录; 网络门用例以 ``RUN_NETWORK_TESTS=1`` 显式启用。
生产 import 放测试函数内 (仓库约定: 模块级不触发 DuckDB 单例)。

覆盖:
- Task 1 (AQ-04 诚实核心): 失败台账每条约两键 (symbol + reason), reason 截断 ≤200,
  ``empty_response`` 与异常两类互斥; 终态键集 8 键 (成功路径, W-5 限定); fail-closed
  9 键 (+reason, W-5 另述); origin 只在终态 dict 不在湖; BJ 空响应诚实记录不预填。
- Task 2 (成功准则 4 + 零执行面): 罐装交叉校验 (auction_virtual_price == kline_daily.open,
  恒 on) + 网络门变体 (真实 kline_daily 只读 + mock 上游确定性); POOL-03 AST 守卫
  (新 POST 路由 E1/E3, auction_history 保持 GET-only, 无 strategy_cache 引用)。
"""
from __future__ import annotations

import ast
import os
import re
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

# 成功路径终态键集 (W-5): 8 键 set 相等仅限成功路径; fail-closed 另加 "reason" (9 键)。
_SUCCESS_KEYS = {
    "requested", "backfilled_symbols", "rows", "dates", "failed",
    "failed_symbols", "origin", "rpm",
}

# ================================================================
# hermetic fixtures (复制 test_auction_backfill.py / test_auction_sync.py 形态,
# 独立文件, 不 import 32-02 测试模块)
# ================================================================


class _FakeAuctionProvider:
    """逐 symbol 假 provider: rows_by_symbol / exc_by_symbol 注入, calls 记录调用。"""

    name = "fake_auction"

    def __init__(self, rows_by_symbol=None, exc_by_symbol=None):
        self.rows_by_symbol = rows_by_symbol or {}
        self.exc_by_symbol = exc_by_symbol or {}
        self.calls: list[tuple[list[str], object, object]] = []

    def get_auction(self, symbols, start_date, end_date=None):
        self.calls.append((list(symbols), start_date, end_date))
        sym = symbols[0]
        if sym in self.exc_by_symbol:
            raise self.exc_by_symbol[sym]
        df = self.rows_by_symbol.get(sym)
        return df if df is not None else pl.DataFrame()


class _FakeDb:
    """最小 db 桩: execute(sql).fetchall() 返回 DISTINCT symbol 行 (W-1: 无 repo.query)。"""

    def __init__(self, symbols):
        self._symbols = list(symbols)

    def execute(self, sql, *args, **kwargs):
        return _FakeCursor([(s,) for s in self._symbols])


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeRepo:
    """最小 repo 桩: store.data_dir (写湖) + db.execute (universe, W-1)。"""

    def __init__(self, data_dir, symbols):
        self.store = SimpleNamespace(data_dir=data_dir)
        self.db = _FakeDb(symbols)


def _symbol_rows(symbol, dates, vp_by_date=None):
    """每日期 09:25:00 一行的 canonical 帧 (可选 auction_virtual_price, CHART-03 形)。"""
    vp = vp_by_date or {}
    cols = {
        "symbol": [symbol] * len(dates),
        "datetime": [datetime(d.year, d.month, d.day, 9, 25) for d in dates],
        "auction_volume": [100] * len(dates),
        "auction_amount": [1000] * len(dates),
    }
    if vp_by_date is not None:
        cols["auction_virtual_price"] = [float(vp.get(d, 10.0)) for d in dates]
    return pl.DataFrame(cols)


def _make_env(tmp_path, daily_dates, symbols, opens=None):
    """构造 kline_daily/date=* 分区 (symbol/open 列) + _FakeRepo (镜像 pool_backfill._make_env)。

    opens: {date: open 值}, 缺省 10.0 —— 罐装交叉校验用它让 kline_daily.open 与
    fake provider 的 current 对齐。
    """
    opens = opens or {}
    for d in daily_dates:
        part_dir = tmp_path / "kline_daily" / f"date={d.isoformat()}"
        part_dir.mkdir(parents=True, exist_ok=True)
        pl.DataFrame({
            "symbol": list(symbols),
            "open": [float(opens.get(d, 10.0))] * len(symbols),
        }).write_parquet(part_dir / "part.parquet")
    return _FakeRepo(tmp_path, symbols)


def _available_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.available, source="fake", probed_at=None, detail="fake",
    )


def _fail_closed_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.fail_closed, source="fake", probed_at=None, detail="fake",
    )


def _patch_probe(monkeypatch, verdict) -> None:
    """把 resolve_auction_probe 钉死为固定 verdict (源模块 + 消费模块双面 patch)。

    32-02 服务可能 (a) 模块级 from auction_probe import resolve_auction_probe →
    patch auction_backfill.resolve_auction_probe; (b) 经 auction_sync 引用 → patch
    auction_sync.resolve_auction_probe; (c) 函数内 import 源模块 → patch
    auction_probe.resolve_auction_probe。三面都钉, 覆盖全部 import 形态。
    """
    from app.services import auction_backfill, auction_sync
    from app.services import auction_probe as _probe_mod
    monkeypatch.setattr(_probe_mod, "resolve_auction_probe", lambda: verdict)
    monkeypatch.setattr(auction_sync, "resolve_auction_probe", lambda: verdict)
    if hasattr(auction_backfill, "resolve_auction_probe"):
        monkeypatch.setattr(auction_backfill, "resolve_auction_probe", lambda: verdict)


def _patch_provider(monkeypatch, provider) -> None:
    """把 _first_auction_provider 钉死为 fake (服务 + 源模块双面 patch)。"""
    from app.services import auction_backfill, auction_sync
    monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: provider)
    if hasattr(auction_backfill, "_first_auction_provider"):
        monkeypatch.setattr(auction_backfill, "_first_auction_provider", lambda: provider)


def _patch_pacing(monkeypatch) -> None:
    """中性化 rpm 限速, 避免真实 sleep (W-3: 模块级 patch 才生效)。

    _reserve_slot 返回 0 → sleep_between_batches 的 wait==0 不 sleep; 同时覆盖
    模块级 sleep_between_batches 绑定 (若服务把它 import 到模块命名空间)。
    """
    from app.tickflow import rate_limits
    monkeypatch.setattr(rate_limits, "_reserve_slot", lambda *a, **k: 0.0)
    from app.services import auction_backfill
    if hasattr(auction_backfill, "sleep_between_batches"):
        monkeypatch.setattr(auction_backfill, "sleep_between_batches", lambda *a, **k: None)


def _run_job(monkeypatch, tmp_path, daily_dates, symbols, provider, opens=None, **kwargs):
    """拼装环境 + patch probe/provider/pacing, 调 run_auction_backfill, 返回 (终态, repo)。"""
    from app.services import auction_backfill

    repo = _make_env(tmp_path, daily_dates, symbols, opens=opens)
    _patch_probe(monkeypatch, _available_verdict())
    _patch_provider(monkeypatch, provider)
    _patch_pacing(monkeypatch)
    term = auction_backfill.run_auction_backfill(repo, symbols=list(symbols), **kwargs)
    return term, repo


def _lake_rows(tmp_path, symbol, d) -> pl.DataFrame:
    out = tmp_path / "kline_auction" / f"date={d.isoformat()}" / "part.parquet"
    if not out.exists():
        return pl.DataFrame()
    return pl.read_parquet(out).filter(pl.col("symbol") == symbol)


# ================================================================
# Task 1 — 失败台账终态形状 (AQ-04 诚实核心)
# ================================================================


def test_auction_backfill_failed_ledger_terminal_shape(tmp_path, monkeypatch):
    """AQ-04 台账形状: B 抛 300 字异常 → 终态 failed_symbols 恰 [{"symbol","reason"}]
    两键, reason 恰截断 200 字; 终态键集 == 8 键 (成功路径, W-5)。"""
    d1 = date(2026, 8, 3)
    fake = _FakeAuctionProvider(
        rows_by_symbol={"A": _symbol_rows("A", [d1])},
        exc_by_symbol={"B": RuntimeError("x" * 300)},
    )
    term, repo = _run_job(monkeypatch, tmp_path, [d1], ["A", "B"], fake)

    # W-5: 8 键 set 相等仅限成功路径 (本 run 是成功路径 —— 终态如实反映部分失败)
    assert set(term) == _SUCCESS_KEYS, f"终态键集漂移: {sorted(term)}"
    assert term["requested"] == 2
    assert term["backfilled_symbols"] == 1
    assert term["failed"] == 1
    assert term["origin"] == "backfill"
    assert term["rpm"] == 30

    ledger = term["failed_symbols"]
    assert len(ledger) == 1
    entry = ledger[0]
    assert set(entry.keys()) == {"symbol", "reason"}, f"台账条目出现杂键: {entry}"
    assert entry["symbol"] == "B"
    assert entry["reason"] == "x" * 200  # 恰截断 200 字 (镜像 auction_probe._ERROR_DETAIL_MAX)
    assert len(entry["reason"]) == 200


def test_auction_backfill_partial_failure_ledger_records_others_continue(tmp_path, monkeypatch):
    """AQ-03c/04 部分失败如实: 3 symbols A/B/C, B 抛异常 → failed==1,
    backfilled_symbols==2, rows == A+C 实际写行数 (≠ 3 倍), A/C 分区在湖中, B 无行。"""
    d1 = date(2026, 8, 3)
    fake = _FakeAuctionProvider(
        rows_by_symbol={
            "A": _symbol_rows("A", [d1]),
            "C": _symbol_rows("C", [d1]),
        },
        exc_by_symbol={"B": RuntimeError("boom")},
    )
    term, repo = _run_job(monkeypatch, tmp_path, [d1], ["A", "B", "C"], fake)

    assert term["failed"] == 1
    assert term["backfilled_symbols"] == 2
    assert term["rows"] == 2  # A + C 各 1 行 (绝不 3 倍伪造)
    assert term["failed_symbols"] == [{"symbol": "B", "reason": "boom"}]

    lake = tmp_path / "kline_auction" / f"date={d1.isoformat()}" / "part.parquet"
    assert lake.exists()
    written = pl.read_parquet(lake)
    assert set(written["symbol"].to_list()) == {"A", "C"}
    assert "B" not in written["symbol"].to_list()


def test_auction_backfill_origin_backfill_only_in_terminal_dict(tmp_path, monkeypatch):
    """AQ-04 origin 契约: 终态 origin=="backfill" 且 rpm 与传入一致 (10);
    湖分区读回列 == 写缝裁剪列, 无 origin/source provenance 列 (origin 只在 dict)。"""
    d1 = date(2026, 8, 3)
    fake = _FakeAuctionProvider(rows_by_symbol={"A": _symbol_rows("A", [d1])})
    term, repo = _run_job(monkeypatch, tmp_path, [d1], ["A"], fake, rpm=10)

    assert term["origin"] == "backfill"
    assert term["rpm"] == 10

    out = tmp_path / "kline_auction" / f"date={d1.isoformat()}" / "part.parquet"
    df = pl.read_parquet(out)
    assert "origin" not in df.columns
    assert "source" not in df.columns
    from app.services.auction_sync import CANONICAL_AUCTION_COLS
    assert set(df.columns) <= set(CANONICAL_AUCTION_COLS) | {"auction_virtual_price"}


def test_auction_backfill_bj_stock_empty_response_recorded(tmp_path, monkeypatch):
    """R8 / BJ 空响应诚实记录: kline_daily 含 920146.BJ 行 + 上游对 BJ 返回空 →
    failed_symbols 含 {"symbol":"920146.BJ","reason":"empty_response"}; 湖中无该
    symbol 行 (绝不预填/0 填); 其余 symbol 正常写。"""
    d1, d2 = date(2026, 8, 3), date(2026, 8, 4)
    symbols = ["000001.SZ", "920146.BJ"]
    fake = _FakeAuctionProvider(rows_by_symbol={
        "000001.SZ": _symbol_rows("000001.SZ", [d1, d2]),
        # 920146.BJ 缺省 → 空 df (上游无 BJ 覆盖, R8)
    })
    term, repo = _run_job(monkeypatch, tmp_path, [d1, d2], symbols, fake)

    assert term["failed"] == 1
    assert term["backfilled_symbols"] == 1
    assert {"symbol": "920146.BJ", "reason": "empty_response"} in term["failed_symbols"]
    # 其余 symbol 正常写, BJ 无任何行
    assert _lake_rows(tmp_path, "000001.SZ", d1).height == 1
    assert _lake_rows(tmp_path, "000001.SZ", d2).height == 1
    for d in (d1, d2):
        assert _lake_rows(tmp_path, "920146.BJ", d).is_empty()


def test_auction_backfill_empty_response_reason_category_distinct(tmp_path, monkeypatch):
    """空响应类别: 有 kline_daily 覆盖但上游空 → reason 恰 "empty_response";
    与异常类别 str(e)[:200] 语义互斥 (两类 reason 可区分)。"""
    d1 = date(2026, 8, 3)
    symbols = ["A", "B"]
    fake = _FakeAuctionProvider(
        rows_by_symbol={"A": _symbol_rows("A", [d1])},  # A 正常
        # B: 有 kline_daily 覆盖但上游返回空 → empty_response
    )
    term, repo = _run_job(monkeypatch, tmp_path, [d1], symbols, fake)

    entry = [e for e in term["failed_symbols"] if e["symbol"] == "B"]
    assert entry == [{"symbol": "B", "reason": "empty_response"}]
    # 与异常类别互斥: 异常 reason 是 str(e)[:200] 而非 "empty_response"
    exc_fake = _FakeAuctionProvider(
        rows_by_symbol={"A": _symbol_rows("A", [d1])},
        exc_by_symbol={"B": RuntimeError("boom")},
    )
    term2, _ = _run_job(monkeypatch, tmp_path, [d1], symbols, exc_fake)
    entry2 = [e for e in term2["failed_symbols"] if e["symbol"] == "B"]
    assert entry2 == [{"symbol": "B", "reason": "boom"}]
    assert term2["failed_symbols"][0]["reason"] != "empty_response"


def test_auction_backfill_fail_closed_ledger_shape_and_zero_writes(tmp_path, monkeypatch):
    """W-5 fail-closed 终态 = 8 成功键 + reason (9 键); 源不可达 → 0 写 fail-closed。"""
    d1 = date(2026, 8, 3)
    repo = _make_env(tmp_path, [d1], ["A"])
    _patch_probe(monkeypatch, _fail_closed_verdict())
    _patch_pacing(monkeypatch)

    from app.services import auction_backfill
    term = auction_backfill.run_auction_backfill(repo, symbols=["A"])

    assert set(term) == _SUCCESS_KEYS | {"reason"}, f"fail-closed 键集漂移: {sorted(term)}"
    assert term["reason"] == "source_unavailable"
    assert term["rows"] == 0
    assert term["failed"] == 0
    assert term["failed_symbols"] == []
    lake = tmp_path / "kline_auction"
    if lake.exists():
        assert not list(lake.glob("date=*"))


# ================================================================
# Task 2 — 交叉校验 (成功准则 4) + POOL-03 AST 守卫
# ================================================================


def test_auction_backfill_cross_check_canned(tmp_path, monkeypatch):
    """成功准则 4 罐装证明 (恒 on): kline_daily 分区 {D1..D4} open {10.0,10.2,10.4,10.6};
    fake provider current == open 同值 → 写后每 Di auction_virtual_price == kline_daily.open[Di]
    (≥3 日期逐值相等, pytest.approx)。"""
    dates = [date(2026, 8, i) for i in range(1, 5)]
    opens = {dates[0]: 10.0, dates[1]: 10.2, dates[2]: 10.4, dates[3]: 10.6}
    symbol = "000001.SZ"
    fake = _FakeAuctionProvider(rows_by_symbol={
        symbol: _symbol_rows(symbol, dates, vp_by_date=opens),
    })
    term, repo = _run_job(
        monkeypatch, tmp_path, dates, [symbol], fake,
        opens=opens, rpm=10,
    )
    assert term["failed"] == 0
    assert term["rows"] == 4

    for d in dates:
        daily_open = pl.read_parquet(
            tmp_path / "kline_daily" / f"date={d.isoformat()}" / "part.parquet",
        ).filter(pl.col("symbol") == symbol)["open"][0]
        written = _lake_rows(tmp_path, symbol, d)
        assert written.height == 1, f"{d} 缺行"
        assert written["auction_virtual_price"][0] == pytest.approx(float(daily_open), rel=1e-6)


def test_auction_virtual_price_equals_daily_open(tmp_path, monkeypatch):
    """成功准则 4 网络门: 真实 kline_daily (settings.data_dir, 只读) 为 000001.SZ 取 ≥3 个
    对齐日期; mock 上游 (current == open, 确定性, 不依赖网络) → 写 tmp 湖 → 逐值断言相等。
    真实 MCP 可达时附加实时取数断言 (写 tmp 湖, 对齐过滤)。默认 skip (RUN_NETWORK_TESTS=1)。"""
    if os.environ.get("RUN_NETWORK_TESTS") != "1":
        pytest.skip("network-gated: 真实 kline_daily 只读 + mock 上游 (确定性), 可选真实 MCP")

    from app.config import settings
    from app.tickflow.repository import DataStore, KlineRepository

    real_daily = Path(settings.data_dir) / "kline_daily"
    if not real_daily.is_dir():
        pytest.skip("沙箱无真实 kline_daily 分区")

    symbol = "000001.SZ"
    # 收集含该 symbol 的分区日期 + open 值 (只读真实沙箱)
    aligned: dict[str, float] = {}
    for part in sorted(real_daily.glob("date=*")):
        d = part.name.split("=", 1)[1]
        df = pl.read_parquet(part / "part.parquet", columns=["symbol", "open"])
        row = df.filter(pl.col("symbol") == symbol)
        if not row.is_empty():
            aligned[d] = float(row["open"][0])
        if len(aligned) >= 3:
            break
    assert len(aligned) >= 3, f"000001.SZ 对齐日期不足 3 个: {sorted(aligned)}"
    dates = sorted(aligned)

    # tmp 湖: 拷贝真实分区进 tmp (只读真实, 写只进 tmp), 真实 DataStore/KlineRepository
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)
    store = DataStore(data_dir)
    try:
        for d in dates:
            dst = data_dir / "kline_daily" / f"date={d}" / "part.parquet"
            dst.parent.mkdir(parents=True, exist_ok=True)
            pl.read_parquet(real_daily / f"date={d}" / "part.parquet").write_parquet(dst)
        repo = KlineRepository(store)

        # 附加段 (真实 MCP 可达时): 真 fetch → tmp 湖 → 对齐日期上 virtual price == open
        real_checked = False
        try:
            from app.services.auction_probe import AuctionProbeStatus, resolve_auction_probe
            from app.services.auction_sync import _first_auction_provider, write_auction_partitions
            verdict = resolve_auction_probe()
            if verdict.status == AuctionProbeStatus.available:
                provider = _first_auction_provider()
                if provider is not None:
                    df = provider.get_auction(
                        [symbol], date.fromisoformat(dates[0]), date.fromisoformat(dates[-1]),
                    )
                    if not df.is_empty():
                        write_auction_partitions(df, repo)
                        real_checked = True
        except Exception:  # noqa: BLE001 — 真实源瞬时故障 → 附加段诚实跳过
            real_checked = False

        # 确定性段: mock 上游 current == open → 写 tmp 湖
        vp = {date.fromisoformat(d): aligned[d] for d in dates}
        fake = _FakeAuctionProvider(rows_by_symbol={
            symbol: _symbol_rows(symbol, [date.fromisoformat(d) for d in dates], vp_by_date=vp),
        })
        from app.services import auction_backfill
        _patch_probe(monkeypatch, _available_verdict())
        _patch_provider(monkeypatch, fake)
        _patch_pacing(monkeypatch)
        term = auction_backfill.run_auction_backfill(
            repo, symbols=[symbol], start=dates[0], end=dates[-1], rpm=30,
        )
        assert term["failed"] == 0, term

        for d in dates:
            lake = data_dir / "kline_auction" / f"date={d}" / "part.parquet"
            assert lake.exists(), f"缺少 {d} 分区"
            written = pl.read_parquet(lake).filter(pl.col("symbol") == symbol)
            assert not written.is_empty(), f"{d} 缺 {symbol} 行"
            assert written["auction_virtual_price"][0] == pytest.approx(aligned[d], rel=1e-6)
    finally:
        store.db.close()


# ================================================================
# POOL-03 AST 守卫 (新 POST 路由 E1/E3; auction_history GET-only 复验)
# ================================================================

# 执行族 token: 出现在新写面 import / 路由 / 响应键中即失败 (镜像 test_pool_hub.py:858-864)
_EXECUTION_TOKEN = re.compile(
    r"broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托",
    re.IGNORECASE,
)

_WRITE_PATTERNS = (
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']w"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']wb"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']a"),
    re.compile(r"write_parquet"),
    re.compile(r"os\.replace"),
    re.compile(r"unlink\s*\("),
    re.compile(r"mkdir\s*\("),
)


def _feature_sources(rel_path: str) -> str:
    backend = Path(__file__).resolve().parents[1]
    return (backend / "app" / rel_path).read_text(encoding="utf-8")


def _imported_module_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_auction_backfill_router_ast_guard():
    """POOL-03 E1/E3 新 POST 路由: api/auction_backfill.py — import 面无执行族 token
    (broker/order/execution/trade/portfolio/watchlist/position/account/transaction/下单/委托);
    无 strategy_cache import; 含 POST 宿主 (@router.post); 无文件写 pattern
    (open-w/write_parquet/os.replace/unlink/mkdir 负向 —— job_store/executor 编排是调用非文件写)。"""
    src = _feature_sources("api/auction_backfill.py")

    for module in _imported_module_names(src):
        assert not _EXECUTION_TOKEN.search(module), (
            f"auction backfill 特性引入了执行族模块: {module}"
        )
        assert "strategy_cache" not in module, f"auction backfill 引入了 strategy_cache: {module}"

    methods = re.findall(r"@router\.(get|post|put|delete|patch)\b", src)
    assert methods and set(methods) == {"post"}, f"auction backfill 路由漂移: {methods}"
    assert "@router.post" in src

    for pattern in _WRITE_PATTERNS:
        assert not pattern.search(src), f"api/auction_backfill.py 出现写路径: {pattern.pattern}"


def test_auction_history_router_stays_get_only():
    """POOL-03 E4 复验: api/auction_history.py 仍 GET-only (@router.post|put|delete|patch
    扫描零命中) — 既有守卫 test_auction_history.py:310-313 零改动, 本用例是追加复验。"""
    src = _feature_sources("api/auction_history.py")
    methods = re.findall(r"@router\.(get|post|put|delete|patch)\b", src)
    assert methods and set(methods) == {"get"}, f"auction history API 出现了非 GET 路由: {methods}"


def test_backfill_modules_never_reference_strategy_cache():
    """POOL-03 E3: backfill 服务/端点两文件均无 strategy_cache 引用 (import 级 + 源码
    字符串级); 单 as_of 指针完整性不动 (backfill 不 import 不写)。"""
    for rel in ("api/auction_backfill.py", "services/auction_backfill.py"):
        src = _feature_sources(rel)
        for module in _imported_module_names(src):
            assert "strategy_cache" not in module, f"{rel} 引入了 strategy_cache: {module}"
        assert "strategy_cache.json" not in src, f"{rel} 引用了 strategy_cache.json"
        assert "write_cache" not in src, f"{rel} 引用了 write_cache"
