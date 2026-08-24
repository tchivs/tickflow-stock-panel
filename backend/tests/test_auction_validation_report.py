"""竞价策略历史验证报告服务 ``AuctionValidationService.build_report`` (BT-03/BT-04/BT-05) —
服务级测试: 空湖诚实报告 / enriched 空态 / probe 透传 / BT-04 前瞻公式与缺失 / 全局日历 /
窗口回夹 / branch 互斥 / skipped_ids / coverage / minute_confirm / symbols 裁剪。

Hermetic (镜像 test_attach_auction_columns_range.py / test_auction_columns.py):
- 生产 import 全放测试函数内 (仓库约定: 模块级不触发 DuckDB 单例);
- repo 用 ``repo_env`` fixture (tmp data_dir + DataStore + KlineRepository);
- enriched 缓存直接 seed ``repo._enriched_history_cache`` (get_enriched_range 快路径同源);
- ``kline_auction`` 分区手工写盘; probe 一律注入固定 verdict (服务层 probe_resolver
  注入点, D-03), 测试不依赖真实竞价数据源。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, time

import polars as pl
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# 竞价族 9 策略 (与服务模块硬编码集一致 — 独立复述, 防漂移)
_AUCTION_FAMILY_IDS = {
    "auction_fast_grab", "auction_allround", "t1_flash", "auction_intraday_confirm",
    "auction_alpha", "golden_230", "auction_bullish", "auction_preopen_quant",
    "auction_early_star",
}
# 4 个 requires_auction_data 真列策略 / 4 个 EOD 代理
_REAL_IDS = {"auction_fast_grab", "auction_allround", "t1_flash", "auction_intraday_confirm"}
_EOD_IDS = {"golden_230", "auction_bullish", "auction_preopen_quant", "auction_early_star"}
_FORWARD_METRICS = ("next_day_open_ret", "next_day_close_ret", "open_gap_outcome")


# ================================================================
# hermetic helpers (镜像 test_attach_auction_columns_range.py)
# ================================================================


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_auction_columns.py:20-32)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    repo = KlineRepository(store)
    try:
        yield repo, data_dir
    finally:
        store.db.close()


def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    """手工写盘 kline_auction/date=YYYY-MM-DD/part.parquet (镜像 test_attach_auction_columns_range)。"""
    out = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


def _auction_rows(
    trade_date: date,
    symbol_volume: dict[str, tuple[float, float]],
    n_rows: int = 1,
) -> pl.DataFrame:
    """canonical 四列 (symbol, datetime, auction_volume, auction_amount)。"""
    _WINDOW_MINUTES = (16, 20, 25)
    rows = []
    for sym, (av, aa) in symbol_volume.items():
        for k in range(n_rows):
            rows.append({
                "symbol": sym,
                "datetime": datetime(trade_date.year, trade_date.month, trade_date.day, 9, _WINDOW_MINUTES[k]),
                "auction_volume": av,
                "auction_amount": aa,
            })
    return pl.DataFrame(rows)


def _write_minute_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    """手工写盘 kline_minute/date=YYYY-MM-DD/part.parquet (镜像 _write_auction_partition)。"""
    out = data_dir / "kline_minute" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


# 09:30 bar 统计口径锚点 (RESEARCH 双源实测 600519): OHLC 全等 1328.36 / vol 521 手
# / amount 69,207,556 元 = 521×1328.36×100 精确闭合 (腾讯 mkline 无 amount 列的派生面)
_MINUTE_ANCHOR_PRICE = 1328.36
_MINUTE_ANCHOR_VOLUME = 521.0
_MINUTE_ANCHOR_AMOUNT = _MINUTE_ANCHOR_VOLUME * _MINUTE_ANCHOR_PRICE * 100  # 69,207,556.0


def _minute_rows(
    trade_date: date,
    symbols,
    n_bars: int = 1,
    *,
    price: float = _MINUTE_ANCHOR_PRICE,
    ohlc_eq: bool = True,
    volume: float = _MINUTE_ANCHOR_VOLUME,
) -> pl.DataFrame:
    """kline_minute canonical 列: 每 symbol 生成 09:30 起 n_bars 根 (09:30, 09:31, ...)。

    默认 OHLC 全等 (纯净竞价单价位): open==high==low==close==1328.36, volume 521 手
    → amount 派生契约锚 521×1328.36×100≈69,207,556。ohlc_eq=False → close 偏移
    (非全等 → amount UNKNOWN 面, 绝不猜)。
    """
    rows = []
    for sym in symbols:
        for k in range(n_bars):
            t = time(9, 30 + k)
            close = price if ohlc_eq else price + 1.64
            rows.append({
                "symbol": sym,
                "datetime": datetime(trade_date.year, trade_date.month, trade_date.day, t.hour, t.minute),
                "open": price,
                "high": price,
                "low": price,
                "close": close,
                "volume": volume,
                "amount": None,
            })
    return pl.DataFrame(rows)


def _available_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.available, source="fake", probed_at=None, detail="available",
    )


def _make_engine():
    """真 StrategyEngine (builtin 策略目录) — 报告不调 engine.run, loader 用 dummy。

    构造形镜像 main.py:555-563; loader 返回 None (报告只消费 engine 定义面)。
    """
    from pathlib import Path

    from app.strategy.engine import StrategyEngine
    backend = Path(__file__).resolve().parents[1]
    return StrategyEngine(
        enriched_loader=lambda as_of: None,
        enriched_history_loader=lambda as_of, lookback: None,
        strategy_dirs=[backend / "app" / "strategy" / "builtin"],
    )


def _seed_enriched_cache(
    repo,
    symbols: tuple[str, ...] = ("000001", "600000"),
    days: int = 139,
    start: date | None = None,
    *,
    open_gap: float = 0.03,
    change_pct: float = 0.035,
    vol_ratio_5d: float = 1.6,
    volume: float = 100_000.0,
    close_ratio: float = 1.05,
    overrides: dict[tuple[str, date], dict[str, object]] | None = None,
) -> pl.DataFrame:
    """seed ``repo._enriched_history_cache`` (get_enriched_range 快路径同源)。

    确定性取值 (derived/eod 分支默认全命中, 可手算):
    - 恒定 volume → 前 5 日均量 = volume, auction_volume_ratio 精确可手算;
    - open 按 symbol (000001→10.0 / 600000→20.0), close = open × close_ratio (收阳);
    - open_gap 3% / change_pct 3.5% / vol_ratio_5d 1.6 / amount = volume×10 = 1M
      → 满足 auction_alpha 派生 (2%/1.2/1M)、auction_bullish (2%/2%)、
      auction_preopen_quant (3%/1.5)、auction_early_star (1.5% OR 3%)、
      golden_230 (change ∈ [3%,5%] 且收阳) 的 META 默认阈值。

    overrides: {(symbol, date): {column: value}} — 逐行覆盖 (停牌缺行/坏 close 等边界)。
    """
    start = start or date(2026, 3, 20)
    overrides = overrides or {}
    rows = []
    for i in range(days):
        d = start + timedelta(days=i)
        for sym in symbols:
            o = 10.0 if sym == "000001" else 20.0
            row = {
                "symbol": sym,
                "date": d,
                "open": o,
                "close": o * close_ratio,
                "high": o * 1.06,
                "low": o * 0.99,
                "volume": volume,
                "amount": volume * 10.0,
                "open_gap": open_gap,
                "change_pct": change_pct,
                "vol_ratio_5d": vol_ratio_5d,
            }
            row.update(overrides.get((sym, d), {}))
            rows.append(row)
    repo._enriched_history_cache = pl.DataFrame(rows)
    # 同步 generation 标记, 避免 get_enriched_range 因 generation 不匹配返回 None
    try:
        repo._enriched_history_generation = repo.get_matrix_data_generation("stock")
    except Exception:
        pass
    return repo._enriched_history_cache


# ================================================================
# Task 1 — Test 1: 空湖诚实报告 (BT-01/BT-05, tracer 垂直切片核心)
# ================================================================


def test_empty_lake_honest_report_all_9_strategies(repo_env):
    """湖空 (无 kline_auction 分区) → 200 形诚实报告 (绝不 404/500/0 填):
    data_gate=="empty" + no_auction_partitions; 4 个 real 策略 n_dates==0 branch=="real"
    (绝不落 derived); auction_alpha branch=="derived" 且 derived/eod 在 enriched 窗口
    给出真实统计; probe 透传; window/coverage 齐全; minute_confirm 显式 not_applied。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    _seed_enriched_cache(repo)  # 139 日 2026-03-20..2026-08-05, 默认缺省窗口内 derived/eod 全命中
    engine = _make_engine()
    verdict = _available_verdict()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: verdict)

    report = svc.build_report()

    # 诚实 gate + 窗口/coverage/probe 全形状
    assert report["data_gate"] == "empty"
    assert report["empty_reason"] == "no_auction_partitions"
    for key in ("requested_start", "requested_end", "effective_start", "effective_end"):
        assert report["window"][key], key
    assert report["coverage"]["auction_enabled_count"] == 0
    assert report["coverage"]["coverage_ratio"] == 0.0
    assert report["coverage"]["enriched_count"] > 0
    assert report["probe"] == verdict.to_dict()
    assert report["skipped_ids"] == []

    # 9 策略齐全
    ids = {s["id"] for s in report["strategies"]}
    assert ids == _AUCTION_FAMILY_IDS
    by_id = {s["id"]: s for s in report["strategies"]}

    # 4 个真列策略: 恒 real + n_dates==0 诚实空 (绝不落 derived, D-02)
    for sid in _REAL_IDS:
        s = by_id[sid]
        assert s["branch"] == "real", sid
        assert s["n_dates"] == 0
        assert s["n_hits"] == 0
        assert s["coverage"] == 0.0
        assert s["per_date"] == []
        assert s["n_missing_outcomes"] == 0
        assert s["minute_confirm"] == "not_applied"
        for m in _FORWARD_METRICS:
            assert s["forward_stats"][m]["n"] == 0
            assert s["forward_stats"][m]["mean"] is None
            assert s["forward_stats"][m]["median"] is None
            assert s["forward_stats"][m]["win_rate"] is None

    # auction_alpha: enabled 空 → derived, 在 enriched 窗口有真实统计
    alpha = by_id["auction_alpha"]
    assert alpha["branch"] == "derived"
    assert alpha["n_dates"] > 0
    assert alpha["n_hits"] > 0
    assert alpha["coverage"] > 0.0

    # 4 个 EOD 代理: 恒 eod + enriched 窗口真实统计
    for sid in _EOD_IDS:
        s = by_id[sid]
        assert s["branch"] == "eod", sid
        assert s["n_dates"] > 0
        assert s["n_hits"] > 0

    # BT-05 互斥: 每策略单 branch 标注 + 显式 minute_confirm
    for s in report["strategies"]:
        assert s["branch"] in {"real", "derived", "eod"}
        assert s["minute_confirm"] == "not_applied"


def test_enriched_unavailable_empty_cache(repo_env):
    """无 enriched 缓存 + 无分区 → 诚实 enriched_unavailable + strategies==[] (绝不 404/500)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report()

    assert report["data_gate"] == "empty"
    assert report["empty_reason"] == "enriched_unavailable"
    assert report["strategies"] == []


def test_probe_passthrough_not_gate(repo_env):
    """D-03: probe_resolver 注入点 — probe 判定透传报告 (to_dict), 不参与历史闸门;
    即便 probe 非 available, 报告照常装配。"""
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    _seed_enriched_cache(repo)
    engine = _make_engine()
    verdict = AuctionProbeVerdict(
        status=AuctionProbeStatus.not_configured, source=None, probed_at=None,
        detail="not configured",
    )
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: verdict)

    report = svc.build_report()

    assert report["probe"] == verdict.to_dict()
    assert report["probe"]["status"] == "not_configured"
    # 报告照常装配 (probe 不 gate 历史报告)
    assert report["data_gate"] == "empty"
    assert report["empty_reason"] == "no_auction_partitions"
    assert len(report["strategies"]) == 9


# ================================================================
# Task 2 — BT-04 前瞻口径锁死 (全局日历 next-date + 三公式 + n_missing_outcomes)
# ================================================================


def test_forward_formula_next_day_returns(repo_env):
    """BT-04 三公式手算断言 (auction_early_star, eod 分支, 确定性命中):

    T=2026-08-04 (open 10.0/20.0, close 10.5/20.5), T+1=2026-08-05 (open 10.8/21.0,
    close 11.0/21.5); 结果日 = 全局日历 next-date → 每 hit:
      next_day_open_ret  = 10.8/10.0−1 = 0.08; 21.0/20.0−1 = 0.05
      next_day_close_ret = 11.0/10.0−1 = 0.10; 21.5/20.0−1 = 0.075
      open_gap_outcome   = 10.8/10.5−1; 21.0/20.5−1
    T+1 行 open_gap/change_pct 置低 → 不产生额外命中 (n_hits==2, n_missing==0)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    t, t1 = date(2026, 8, 4), date(2026, 8, 5)
    _seed_enriched_cache(
        repo, days=2, start=t,
        overrides={
            ("600000", t): {"close": 20.5},
            ("000001", t1): {"open": 10.8, "close": 11.0, "open_gap": 0.0, "change_pct": 0.01},
            ("600000", t1): {"open": 21.0, "close": 21.5, "open_gap": 0.0, "change_pct": 0.01},
        },
    )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=t, end=t1)

    s = {st["id"]: st for st in report["strategies"]}["auction_early_star"]
    assert s["n_hits"] == 2
    assert s["n_missing_outcomes"] == 0
    fs = s["forward_stats"]
    assert fs["next_day_open_ret"] == {
        "mean": pytest.approx(0.065), "median": pytest.approx(0.065),
        "win_rate": pytest.approx(1.0), "n": 2,
    }
    assert fs["next_day_close_ret"] == {
        "mean": pytest.approx(0.0875), "median": pytest.approx(0.0875),
        "win_rate": pytest.approx(1.0), "n": 2,
    }
    assert fs["open_gap_outcome"]["n"] == 2
    assert fs["open_gap_outcome"]["mean"] == pytest.approx(
        (10.8 / 10.5 - 1.0 + 21.0 / 20.5 - 1.0) / 2.0
    )


def test_outcome_missing_halted_symbol_no_zero_fill(repo_env):
    """BT-04: 停牌 symbol 结果日缺行 → n_missing_outcomes>0, 统计排除, 绝不 0 填/
    前向填充; 全部缺失 → mean/median/win_rate 全 null 而非 0。

    600000 有 T 行 (命中) 但 T+1 无行 (停牌) → 其 T 命中计入 n_missing_outcomes,
    三指标均值只含 000001 的有效行 (若 0 填, mean 会是 0.04 且 n=2)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    t, t1 = date(2026, 8, 4), date(2026, 8, 5)
    panel = _seed_enriched_cache(
        repo, days=2, start=t,
        overrides={
            ("000001", t1): {"open": 10.8, "close": 11.0, "open_gap": 0.0, "change_pct": 0.01},
        },
    )
    # 600000 在 T+1 停牌: 无 T+1 行
    panel = panel.filter(~((pl.col("symbol") == "600000") & (pl.col("date") == t1)))
    repo._enriched_history_cache = panel

    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=t, end=t1)

    s = {st["id"]: st for st in report["strategies"]}["auction_early_star"]
    assert s["n_hits"] == 2
    assert s["n_missing_outcomes"] == 1
    fs = s["forward_stats"]
    # 统计只含 000001 的有效行 (600000 的命中被排除, 绝不 0 填)
    assert fs["next_day_open_ret"]["n"] == 1
    assert fs["next_day_open_ret"]["mean"] == pytest.approx(10.8 / 10.0 - 1.0)
    assert fs["next_day_open_ret"]["win_rate"] == pytest.approx(1.0)
    assert fs["next_day_close_ret"]["n"] == 1
    assert fs["next_day_close_ret"]["mean"] == pytest.approx(11.0 / 10.0 - 1.0)
    assert fs["open_gap_outcome"]["n"] == 1
    assert fs["open_gap_outcome"]["mean"] == pytest.approx(10.8 / 10.5 - 1.0)

    # 全部缺失变体: 单日窗口 → 结果日不存在 → 三指标全 null (诚实, 非 0)
    _seed_enriched_cache(repo, days=1, start=t)
    report2 = svc.build_report(start=t, end=t)
    s2 = {st["id"]: st for st in report2["strategies"]}["auction_early_star"]
    assert s2["n_hits"] == 2
    assert s2["n_missing_outcomes"] == 2
    for m in _FORWARD_METRICS:
        assert s2["forward_stats"][m] == {"mean": None, "median": None, "win_rate": None, "n": 0}


def test_outcome_global_calendar_next_date_not_shift(repo_env):
    """BT-04: 结果日 = 全局交易日历 next-date, 绝不 per-symbol shift(-1)。

    600000 在 T 命中但 T+1 停牌 (T+2 恢复有行): 其结果日必须按全局日历取 T+1
    (缺席 → missing), 绝不能按行内 shift(-1) 错配到 T+2 —— 若错配,
    next_day_open_ret 会把 30.0/20.0−1=0.50 算进统计 (mean 0.29), 而正确值只含
    000001 的 10.8/10.0−1=0.08。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    t, t1, t2 = date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 6)
    panel = _seed_enriched_cache(
        repo, days=3, start=t,
        overrides={
            ("000001", t1): {"open": 10.8, "close": 11.0, "open_gap": 0.0, "change_pct": 0.01},
            ("600000", t1): {"open_gap": 0.0, "change_pct": 0.01},
            ("000001", t2): {"open": 15.0, "close": 15.5, "open_gap": 0.0, "change_pct": 0.01},
            ("600000", t2): {"open": 30.0, "close": 31.5, "open_gap": 0.0, "change_pct": 0.01},
        },
    )
    # 600000 在 T+1 停牌: 全局交易日历仍有 T+1 (000001 有行)
    panel = panel.filter(~((pl.col("symbol") == "600000") & (pl.col("date") == t1)))
    repo._enriched_history_cache = panel

    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=t, end=t2)

    s = {st["id"]: st for st in report["strategies"]}["auction_early_star"]
    assert s["n_hits"] == 2
    assert s["n_missing_outcomes"] == 1  # 600000 的 T 命中 (全局日历 T+1 缺行)
    fs = s["forward_stats"]
    assert fs["next_day_open_ret"]["n"] == 1
    assert fs["next_day_open_ret"]["mean"] == pytest.approx(10.8 / 10.0 - 1.0)
    assert fs["next_day_close_ret"]["n"] == 1
    assert fs["next_day_close_ret"]["mean"] == pytest.approx(11.0 / 10.0 - 1.0)
    assert fs["open_gap_outcome"]["n"] == 1
    assert fs["open_gap_outcome"]["mean"] == pytest.approx(10.8 / 10.5 - 1.0)


def test_forward_close_t_boundary_independent_n(repo_env):
    """BT-04: close_T 为 null/≤0 → open_gap_outcome 该单点剔除, 其余两指标保留
    (每指标独立 n)。

    600000 的 T close=null (但 open_T=20 > 0, T+1 行存在): next_day_open_ret/
    next_day_close_ret 仍含该 hit (n=2), open_gap_outcome 只含 000001 (n=1)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    t, t1 = date(2026, 8, 4), date(2026, 8, 5)
    _seed_enriched_cache(
        repo, days=2, start=t,
        overrides={
            ("600000", t): {"close": None},
            ("000001", t1): {"open": 10.8, "close": 11.0, "open_gap": 0.0, "change_pct": 0.01},
            ("600000", t1): {"open": 21.0, "close": 21.5, "open_gap": 0.0, "change_pct": 0.01},
        },
    )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=t, end=t1)

    s = {st["id"]: st for st in report["strategies"]}["auction_early_star"]
    assert s["n_hits"] == 2
    assert s["n_missing_outcomes"] == 0
    fs = s["forward_stats"]
    assert fs["next_day_open_ret"]["n"] == 2
    assert fs["next_day_open_ret"]["mean"] == pytest.approx((10.8 / 10.0 - 1.0 + 21.0 / 20.0 - 1.0) / 2.0)
    assert fs["next_day_close_ret"]["n"] == 2
    assert fs["next_day_close_ret"]["mean"] == pytest.approx((11.0 / 10.0 - 1.0 + 21.5 / 20.0 - 1.0) / 2.0)
    assert fs["open_gap_outcome"]["n"] == 1
    assert fs["open_gap_outcome"]["mean"] == pytest.approx(10.8 / 10.5 - 1.0)


# ================================================================
# Task 3 — 窗口回夹回显 / skipped_ids / 空列表 / branch 翻转 / coverage / minute_confirm
# ================================================================


def test_window_clamp_requested_effective_echo(repo_env):
    """D-06 窗口回夹 + 双字段回显: 请求超缓存覆盖 → effective 回夹到缓存边界,
    requested 保留原始值 (双字段可区分); 窗口在覆盖内 → effective == requested;
    缺省调用 → requested = 默认 (end=cache_max, start=end−120 自然日)。

    同时锁 PLAN-CHECK W-1: 近缓存边界的超覆盖请求必须产出回夹报告 (而非因 warmup
    低于 cache_min 误报 enriched_unavailable)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    panel = _seed_enriched_cache(repo)  # 2026-03-20..2026-08-05
    cache_min, cache_max = panel["date"].min(), panel["date"].max()
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    # 超覆盖请求 (start 早于 cache_min / end 晚于 cache_max) → 回夹 + 双字段回显
    report = svc.build_report(start=date(2026, 1, 1), end=date(2026, 9, 1))
    w = report["window"]
    assert w["requested_start"] == "2026-01-01"
    assert w["requested_end"] == "2026-09-01"
    assert w["effective_start"] == cache_min.isoformat()
    assert w["effective_end"] == cache_max.isoformat()
    # W1: 回夹后 warmup_start 夹到 cache_min → 报告照常装配 (诚实 no_auction_partitions, 非 enriched_unavailable)
    assert report["data_gate"] == "empty"
    assert report["empty_reason"] == "no_auction_partitions"
    assert len(report["strategies"]) == 9

    # 窗口在覆盖内 → effective == requested
    report2 = svc.build_report(start=date(2026, 4, 1), end=date(2026, 6, 1))
    w2 = report2["window"]
    assert w2["effective_start"] == w2["requested_start"] == "2026-04-01"
    assert w2["effective_end"] == w2["requested_end"] == "2026-06-01"

    # 缺省调用 → requested = 默认 (end=cache_max, start=end−120 自然日), effective 一致
    report3 = svc.build_report()
    w3 = report3["window"]
    assert w3["requested_end"] == cache_max.isoformat()
    assert w3["requested_start"] == (cache_max - timedelta(days=120)).isoformat()
    assert w3["effective_start"] == w3["requested_start"]
    assert w3["effective_end"] == w3["requested_end"]


def test_auction_alpha_branch_flip_mutual_exclusion(repo_env):
    """BT-05: auction_alpha 按 enabled 非空取 real (enabled 子面板) / derived (全验证窗口) 其一;
    同一响应内每策略只含单 branch 统计; 4 个真列策略恒 real (湖空 n_dates==0 绝不落 derived)。"""
    import shutil

    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    _seed_enriched_cache(repo, days=10, start=date(2026, 7, 27), volume=100_000.0)
    start, end = date(2026, 7, 30), date(2026, 8, 3)
    for i in range(5):
        d = start + timedelta(days=i)
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {"000001": (180_000.0, 3_000_000.0), "600000": (180_000.0, 3_000_000.0)}),
        )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    # 有 enabled 日 → real, 评估于 enabled 子面板
    report = svc.build_report(start=start, end=end)
    assert report["data_gate"] == "available"
    by_id = {st["id"]: st for st in report["strategies"]}
    alpha = by_id["auction_alpha"]
    assert alpha["branch"] == "real"
    assert alpha["n_dates"] == 5
    assert alpha["n_hits"] > 0
    # 互斥: 每策略单 branch 标注, 同 id 只出现一次
    assert len(report["strategies"]) == 9
    assert len({st["id"] for st in report["strategies"]}) == 9
    for st in report["strategies"]:
        assert st["branch"] in {"real", "derived", "eod"}

    # 删除分区 → 翻转 derived (全验证窗口), 4 real 恒 real 诚实空
    shutil.rmtree(data_dir / "kline_auction")
    report2 = svc.build_report(start=start, end=end)
    assert report2["data_gate"] == "empty"
    assert report2["empty_reason"] == "no_auction_partitions"
    by_id2 = {st["id"]: st for st in report2["strategies"]}
    assert by_id2["auction_alpha"]["branch"] == "derived"
    assert by_id2["auction_alpha"]["n_dates"] > 0
    for sid in _REAL_IDS:
        assert by_id2[sid]["branch"] == "real"
        assert by_id2[sid]["n_dates"] == 0


def test_skipped_ids_and_empty_list(repo_env):
    """BT-03: 未知 id → skipped_ids 记录 (200 形, 不 500), 已知竞价族仍正常报告;
    请求含未知 + 已知族 → 未知记 skipped、已知族被报告; 显式空列表 → strategies: []
    且 coverage/probe/window 仍在。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    _seed_enriched_cache(repo)
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    # 纯未知请求 → 200 形 + skipped_ids 记录 + 已知竞价族仍正常报告
    report = svc.build_report(strategy_ids=["no_such_strategy"])
    assert report["skipped_ids"] == ["no_such_strategy"]
    assert len(report["strategies"]) == 9
    assert report["data_gate"] == "empty"
    assert report["empty_reason"] == "no_auction_partitions"

    # 未知 + 已知族混搭 → 未知记 skipped, 已知族被报告
    report2 = svc.build_report(strategy_ids=["no_such_strategy", "auction_alpha"])
    assert report2["skipped_ids"] == ["no_such_strategy"]
    assert {st["id"] for st in report2["strategies"]} == {"auction_alpha"}

    # 显式空列表 → strategies: [] (coverage/probe/window 仍返回)
    report3 = svc.build_report(strategy_ids=[])
    assert report3["strategies"] == []
    assert report3["skipped_ids"] == []
    assert report3["coverage"]["enriched_count"] > 0
    assert report3["probe"] is not None
    assert report3["window"]["requested_start"]


def test_per_strategy_coverage_and_minute_confirm(repo_env):
    """per-strategy coverage + per_date (n_screened/n_hits) + minute_confirm (BT-03/BT-05)。

    5 个 enabled 日 (07-30..08-03 全分区, 竞价量 180k → ratio 1.8, 金额 3M);
    open_gap 在 08-01 为 2% (< auction_fast_grab sweet_low 2.8%) → 4 日命中
    (2 symbol × 4 = 8 hits), coverage = 4/5 = 0.8; per_date 5 行, 08-01 行
    n_hits==0 且 n_screened==2; 全 9 策略 minute_confirm=="not_applied" (含
    auction_intraday_confirm)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    low_gap_day = date(2026, 8, 1)
    _seed_enriched_cache(
        repo, days=10, start=date(2026, 7, 27), volume=100_000.0,
        overrides={
            ("000001", low_gap_day): {"open_gap": 0.02},
            ("600000", low_gap_day): {"open_gap": 0.02},
        },
    )
    start, end = date(2026, 7, 30), date(2026, 8, 3)
    for i in range(5):
        d = start + timedelta(days=i)
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {"000001": (180_000.0, 3_000_000.0), "600000": (180_000.0, 3_000_000.0)}),
        )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=end)
    by_id = {st["id"]: st for st in report["strategies"]}

    fg = by_id["auction_fast_grab"]
    assert fg["branch"] == "real"
    assert fg["n_dates"] == 5
    assert fg["n_hits"] == 8
    assert fg["coverage"] == pytest.approx(0.8)
    per = {row["date"]: row for row in fg["per_date"]}
    assert len(per) == 5
    assert per["2026-07-30"] == {"date": "2026-07-30", "n_screened": 2, "n_hits": 2}
    assert per["2026-08-01"] == {"date": "2026-08-01", "n_screened": 2, "n_hits": 0}

    # minute_confirm 全 9 策略显式 not_applied (含 auction_intraday_confirm)
    for st in report["strategies"]:
        assert st["minute_confirm"] == "not_applied"
    assert by_id["auction_intraday_confirm"]["minute_confirm"] == "not_applied"


def test_symbols_filter_limits_evaluation(repo_env):
    """symbols 裁剪: 报告只评估请求 symbol 的行 (n_screened/n_hits 受限)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    _seed_enriched_cache(repo, days=10, start=date(2026, 7, 27), volume=100_000.0)
    start, end = date(2026, 7, 30), date(2026, 8, 3)
    for i in range(5):
        d = start + timedelta(days=i)
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {"000001": (180_000.0, 3_000_000.0), "600000": (180_000.0, 3_000_000.0)}),
        )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report_all = svc.build_report(start=start, end=end)
    report_one = svc.build_report(start=start, end=end, symbols=["000001"])

    fg_all = {st["id"]: st for st in report_all["strategies"]}["auction_fast_grab"]
    fg_one = {st["id"]: st for st in report_one["strategies"]}["auction_fast_grab"]
    assert fg_all["n_hits"] == 10  # 5 日 × 2 symbol
    assert fg_one["n_hits"] == 5   # 5 日 × 1 symbol
    assert all(row["n_screened"] == 2 for row in fg_all["per_date"])
    assert all(row["n_screened"] == 1 for row in fg_one["per_date"])


# ================================================================
# 29-03 — 端点集成 (GET /api/research/auction/validation, BT-01/BT-06)
# ================================================================


def _make_client(repo, engine) -> TestClient:
    """最小 FastAPI 应用 + stub auth + include research_auction router (镜像
    test_auction_history.py:78-93 形; 端点无 guest 掩码 — stub auth 仅形制一致)。"""
    from app.api import research_auction as research_auction_api

    app = FastAPI()
    app.state.repo = repo
    app.state.strategy_engine = engine

    @app.middleware("http")
    async def _stub_auth(request: Request, call_next):
        if request.cookies.get("tf_session") == "vip-token":
            request.state.reviewer_principal = "reviewer_test"
        return await call_next(request)

    app.include_router(research_auction_api.router)
    return TestClient(app)


def _patch_service_probe(monkeypatch, verdict) -> None:
    """patch 目标是 app.services.auction_validation.resolve_auction_probe (服务层
    模块全局; AuctionValidationService 构造时经 probe_resolver 缺省取用)。"""
    from app.services import auction_validation as av_module

    monkeypatch.setattr(av_module, "resolve_auction_probe", lambda: verdict)


def test_endpoint_empty_lake_full_shape_200(repo_env, monkeypatch):
    """BT-01/BT-05 API 面: 空湖 → 200 全形状 (data_gate/empty_reason/coverage/
    strategies 9 id / 4 real n_dates==0 branch real / probe 字段), 绝不 404/500;
    branch 互斥 + minute_confirm 显式。"""
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict

    repo, data_dir = repo_env
    _seed_enriched_cache(repo)  # 139 日 enriched, kline_auction 空
    client = _make_client(repo, _make_engine())
    verdict = AuctionProbeVerdict(
        status=AuctionProbeStatus.not_configured, source=None, probed_at=None,
        detail="hermetic probe",
    )
    _patch_service_probe(monkeypatch, verdict)

    resp = client.get("/api/research/auction/validation")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data_gate"] == "empty"
    assert body["empty_reason"] == "no_auction_partitions"
    assert body["coverage"]["auction_enabled_count"] == 0
    assert body["coverage"]["coverage_ratio"] == 0.0
    assert body["coverage"]["enriched_count"] > 0
    assert body["probe"] == verdict.to_dict()
    assert body["skipped_ids"] == []

    ids = {s["id"] for s in body["strategies"]}
    assert ids == _AUCTION_FAMILY_IDS
    by_id = {s["id"]: s for s in body["strategies"]}
    for sid in _REAL_IDS:
        s = by_id[sid]
        assert s["branch"] == "real", sid
        assert s["n_dates"] == 0
        assert s["n_hits"] == 0
    assert by_id["auction_alpha"]["branch"] == "derived"
    # branch 互斥 (BT-05) + minute_confirm 显式
    for s in body["strategies"]:
        assert s["branch"] in {"real", "derived", "eod"}
        assert s["minute_confirm"] == "not_applied"


def test_endpoint_available_gate_with_partitions(repo_env, monkeypatch):
    """BT-01 API 面: enabled 日期存在 → data_gate=='available' + empty_reason null +
    coverage>0 (auction_alpha real 翻转, BT-05)。"""
    repo, data_dir = repo_env
    _seed_enriched_cache(repo, days=10, start=date(2026, 7, 27), volume=100_000.0)
    start, end = date(2026, 7, 30), date(2026, 8, 3)
    for i in range(5):
        d = start + timedelta(days=i)
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {"000001": (180_000.0, 3_000_000.0), "600000": (180_000.0, 3_000_000.0)}),
        )
    client = _make_client(repo, _make_engine())
    _patch_service_probe(monkeypatch, _available_verdict())

    resp = client.get(
        "/api/research/auction/validation",
        params={"start": "2026-07-30", "end": "2026-08-03"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data_gate"] == "available"
    assert body["empty_reason"] is None
    assert body["coverage"]["auction_enabled_count"] == 5
    assert body["coverage"]["coverage_ratio"] == pytest.approx(1.0)
    alpha = {s["id"]: s for s in body["strategies"]}["auction_alpha"]
    assert alpha["branch"] == "real"
    assert alpha["n_dates"] == 5


def test_endpoint_param_matrix_400_422_empty_skipped_clamp(repo_env, monkeypatch):
    """参数矩阵 (T-29-03-01): start>end → 400 RESEARCH_VALIDATION; 坏日期 → 422;
    strategy_ids 空串 → strategies: []; 未知 id → 200 + skipped_ids (已知族仍报告);
    超覆盖窗口 → effective 回夹 + requested 保留。"""
    repo, data_dir = repo_env
    _seed_enriched_cache(repo)
    client = _make_client(repo, _make_engine())
    _patch_service_probe(monkeypatch, _available_verdict())

    # start > end → 400 RESEARCH_VALIDATION
    resp = client.get(
        "/api/research/auction/validation",
        params={"start": "2026-08-05", "end": "2026-08-01"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "RESEARCH_VALIDATION"

    # 坏日期 → FastAPI 422 (Query date)
    resp = client.get("/api/research/auction/validation", params={"start": "2026-13-99"})
    assert resp.status_code == 422

    # strategy_ids 空串 → 显式空列表 → strategies: []
    resp = client.get("/api/research/auction/validation", params={"strategy_ids": ""})
    assert resp.status_code == 200
    assert resp.json()["strategies"] == []

    # 未知 id → 200 + skipped_ids (已知竞价族仍正常报告, 绝不 500)
    resp = client.get(
        "/api/research/auction/validation",
        params={"strategy_ids": "no_such_strategy"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "no_such_strategy" in body["skipped_ids"]
    assert len(body["strategies"]) == 9

    # 超覆盖窗口 → effective 回夹到缓存边界 + requested 保留 (D-06 双字段回显)
    resp = client.get(
        "/api/research/auction/validation",
        params={"start": "2026-01-01", "end": "2026-09-01"},
    )
    assert resp.status_code == 200
    w = resp.json()["window"]
    assert w["requested_start"] == "2026-01-01"
    assert w["requested_end"] == "2026-09-01"
    panel = repo._enriched_history_cache
    assert w["effective_start"] == panel["date"].min().isoformat()
    assert w["effective_end"] == panel["date"].max().isoformat()


def test_endpoint_forward_stats_branch_minute_confirm(repo_env, monkeypatch):
    """BT-04 公式经 API 复验 (auction_early_star, 2 日 fixture 手算: open_ret 0.065 /
    close_ret 0.0875) + branch 互斥 + minute_confirm 显式 not_applied。"""
    repo, data_dir = repo_env
    t, t1 = date(2026, 8, 4), date(2026, 8, 5)
    _seed_enriched_cache(
        repo, days=2, start=t,
        overrides={
            ("600000", t): {"close": 20.5},
            ("000001", t1): {"open": 10.8, "close": 11.0, "open_gap": 0.0, "change_pct": 0.01},
            ("600000", t1): {"open": 21.0, "close": 21.5, "open_gap": 0.0, "change_pct": 0.01},
        },
    )
    client = _make_client(repo, _make_engine())
    _patch_service_probe(monkeypatch, _available_verdict())

    resp = client.get(
        "/api/research/auction/validation",
        params={"start": "2026-08-04", "end": "2026-08-05"},
    )

    assert resp.status_code == 200
    body = resp.json()
    by_id = {s["id"]: s for s in body["strategies"]}
    s = by_id["auction_early_star"]
    assert s["branch"] == "eod"
    assert s["n_hits"] == 2
    assert s["n_missing_outcomes"] == 0
    fs = s["forward_stats"]
    assert fs["next_day_open_ret"] == {
        "mean": pytest.approx(0.065), "median": pytest.approx(0.065),
        "win_rate": pytest.approx(1.0), "n": 2,
    }
    assert fs["next_day_close_ret"] == {
        "mean": pytest.approx(0.0875), "median": pytest.approx(0.0875),
        "win_rate": pytest.approx(1.0), "n": 2,
    }
    assert fs["open_gap_outcome"]["n"] == 2
    # branch 互斥 (BT-05) + minute_confirm (含 auction_intraday_confirm)
    for st in body["strategies"]:
        assert st["branch"] in {"real", "derived", "eod"}
        assert st["minute_confirm"] == "not_applied"
    assert by_id["auction_intraday_confirm"]["minute_confirm"] == "not_applied"


# ================================================================
# BT-08 — 248 分区激活 + symbol 级诚实覆盖
# ================================================================


# 5-symbol enriched 宇宙 (含 2 个竞价分区 symbol — 稀疏湖小宇宙如实)
_ENRICHED_SYMBOLS_5 = ("000001.SZ", "000002.SZ", "600519.SH", "300750.SZ", "601318.SH")


def _seed_auction_partitions(
    data_dir,
    start: date,
    days: int,
    symbol_volume: dict[str, tuple[float, float]],
) -> None:
    """循环 _write_auction_partition 生成 days 个连续日 kline_auction 分区
    (hermetic, 无网络 — 服务 range 闸门无 probe)。"""
    for i in range(days):
        d = start + timedelta(days=i)
        _write_auction_partition(data_dir, d, _auction_rows(d, symbol_volume))


def _seed_auction_partitions_248(
    data_dir,
    start: date,
    symbols: tuple[str, ...] = ("000001.SZ", "000002.SZ"),
) -> None:
    """248 日全分区 fixture (BT-08 激活证明): 2 symbols × 每分区 1 行, 竞价量
    180k/3M (与既有 sparse fixture 同值 — ratio 1.8 / amount 3M 过 fast_grab
    META 默认阈值, open_gap 0.03 在甜点区)。"""
    _seed_auction_partitions(
        data_dir, start, 248,
        {sym: (180_000.0, 3_000_000.0) for sym in symbols},
    )


def test_validation_available_248_partitions_real_rows(repo_env):
    """BT-08 核心验收: 248 个 auction 分区 ∩ 248 个 enriched 日 → data_gate 自动
    翻转为 "available" (闸门零改动, 行为性激活 — 分区存在性闸门全通过), 真列分支
    报告真实行 (2-symbol 小宇宙, n_dates==248 恒 real 绝不落 derived); 其余 3
    symbol 竞价列 null 恒假 → 单 symbol 评估 0 命中; coverage.symbols 诚实稀疏。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2025, 12, 1)
    end = start + timedelta(days=247)  # 2026-08-05
    _seed_enriched_cache(repo, days=248, start=start, symbols=_ENRICHED_SYMBOLS_5)
    _seed_auction_partitions_248(data_dir, start)
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=end)

    # 激活: data_gate 自动翻转 (闸门 :184-191 零改动, 248∩248 → available)
    assert report["data_gate"] == "available"
    assert report["empty_reason"] is None
    assert report["skipped_ids"] == []
    assert report["coverage"]["auction_enabled_count"] == 248
    assert report["coverage"]["enriched_count"] == 248
    assert report["coverage"]["coverage_ratio"] == pytest.approx(1.0)
    # coverage.symbols 诚实稀疏: 湖 2 symbol / 宇宙 5 symbol
    sym = report["coverage"]["symbols"]
    assert sym["auction_symbol_count"] == 2
    assert sym["enriched_symbol_count"] == 5
    assert sym["symbol_coverage_ratio"] == pytest.approx(0.4)
    assert sym["auction_rows_present"] == 496  # 248 分区 × 2 symbol
    assert sym["auction_rows_expected"] == 1240  # 5 symbol × 248 日

    by_id = {st["id"]: st for st in report["strategies"]}
    # 4 个真列策略: 恒 real + 全窗口 n_dates==248 (绝不 derived-downgrade, D-02)
    for sid in _REAL_IDS:
        s = by_id[sid]
        assert s["branch"] == "real", sid
        assert s["n_dates"] == 248, sid
        assert s["n_symbols_covered"] == 2, sid  # 竞价列非 null 的 symbol 数
        assert s["minute_confirm"] == "not_applied", sid
    # 竞价列依赖过滤的真列策略: hits ⊆ {000001.SZ, 000002.SZ} (其余 3 symbol
    # 竞价列 null 恒假 — ratio/amount 条件不满足); fast_grab/allround 过阈值
    # (ratio 1.8), t1_flash 阈值 2.0 未达 → 诚实 0 命中
    for sid in ("auction_fast_grab", "auction_allround", "t1_flash"):
        assert by_id[sid]["n_symbols_hit"] <= 2, sid
    assert by_id["auction_fast_grab"]["n_symbols_hit"] == 2
    assert by_id["auction_allround"]["n_symbols_hit"] == 2
    assert by_id["t1_flash"]["n_symbols_hit"] == 0
    # auction_intraday_confirm: filter 仅 open_gap (分钟确认层未接, BT-10
    # minute_confirm 注解诚实受限) → 全 symbol 命中如实 (5×248), 不参与竞价列子集
    aic = by_id["auction_intraday_confirm"]
    assert aic["n_symbols_hit"] == 5
    assert aic["n_hits"] == 1240
    # auction_alpha: enabled 非空 → real 翻转 (绝不落 derived)
    alpha = by_id["auction_alpha"]
    assert alpha["branch"] == "real"
    assert alpha["n_dates"] == 248
    # derived/eod 策略: 全窗口评估
    for sid in _EOD_IDS:
        assert by_id[sid]["n_dates"] == 248, sid

    # 稀疏诚实 (其余 3 symbol 竞价列 null 恒假): 单 symbol 评估 → 真列 0 命中
    report_non = svc.build_report(start=start, end=end, symbols=["600519.SH"])
    fg_non = {st["id"]: st for st in report_non["strategies"]}["auction_fast_grab"]
    assert fg_non["branch"] == "real"
    assert fg_non["n_hits"] == 0
    assert fg_non["n_symbols_covered"] == 0
    assert fg_non["n_symbols_hit"] == 0


def test_coverage_symbols_block_honest_sparse(repo_env):
    """BT-08 coverage.symbols 子块: 稀疏 fixture (5-symbol enriched × 2 日,
    2-symbol auction 分区) → 实况 {2, 5, 0.4, 4, 10}; 删分区 → data_gate 诚实
    empty 且同键如实 (auction 侧 0, enriched 侧非 0); 全空 (enriched 缓存空) →
    _empty_report 同键全 0 形状 (空态与实态同形状, D-02)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(repo, days=2, start=start, symbols=_ENRICHED_SYMBOLS_5)
    _seed_auction_partitions(
        data_dir, start, 2,
        {"000001.SZ": (180_000.0, 3_000_000.0), "000002.SZ": (180_000.0, 3_000_000.0)},
    )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=start + timedelta(days=1))

    assert report["data_gate"] == "available"
    assert report["coverage"]["auction_enabled_count"] == 2
    assert report["coverage"]["symbols"] == {
        "auction_symbol_count": 2,
        "enriched_symbol_count": 5,
        "symbol_coverage_ratio": pytest.approx(0.4),
        "auction_rows_present": 4,   # 2 分区 × 2 symbol
        "auction_rows_expected": 10,  # 5 symbol × 2 日
    }

    # 删分区 → 诚实 empty, 同键如实 (enriched 侧不归零 — 绝不 0 填)
    import shutil
    shutil.rmtree(data_dir / "kline_auction")
    report2 = svc.build_report(start=start, end=start + timedelta(days=1))
    assert report2["data_gate"] == "empty"
    assert report2["empty_reason"] == "no_auction_partitions"
    assert report2["coverage"]["symbols"] == {
        "auction_symbol_count": 0,
        "enriched_symbol_count": 5,
        "symbol_coverage_ratio": pytest.approx(0.0),
        "auction_rows_present": 0,
        "auction_rows_expected": 10,
    }

    # 全空 (enriched 缓存空 + 无分区) → _empty_report 同键全 0 (空态与实态同形状)
    repo._enriched_history_cache = pl.DataFrame()
    report3 = svc.build_report()
    assert report3["data_gate"] == "empty"
    assert report3["empty_reason"] == "enriched_unavailable"
    assert report3["coverage"]["symbols"] == {
        "auction_symbol_count": 0,
        "enriched_symbol_count": 0,
        "symbol_coverage_ratio": pytest.approx(0.0),
        "auction_rows_present": 0,
        "auction_rows_expected": 0,
    }


def test_per_strategy_symbol_coverage(repo_env):
    """BT-08 per-strategy symbol 覆盖: 稀疏 fixture 造确定性 1 命中 → 真列策略
    n_symbols_covered==2 (竞价列非 null) + n_symbols_hit==1 (仅 000001.SZ 过
    fast_grab 阈值; 000002.SZ 量比 1.0 < 1.5); derived/eod 策略 n_symbols_covered==5
    (全评估宇宙); 湖空 → n_symbols_covered==0 且 n_dates==0 仍 branch=="real"。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(repo, days=2, start=start, symbols=_ENRICHED_SYMBOLS_5)
    # 000001.SZ 竞价量 180k (ratio 1.8 → 命中), 000002.SZ 竞价量 100k (ratio 1.0 → 不命中)
    _seed_auction_partitions(
        data_dir, start, 2,
        {"000001.SZ": (180_000.0, 3_000_000.0), "000002.SZ": (100_000.0, 1_000_000.0)},
    )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=start + timedelta(days=1))
    by_id = {st["id"]: st for st in report["strategies"]}

    # 真列策略: 竞价列非 null symbol 数 = 2 (两 symbol 都在分区), 命中 symbol 数 = 1
    fg = by_id["auction_fast_grab"]
    assert fg["branch"] == "real"
    assert fg["n_symbols_covered"] == 2
    assert fg["n_symbols_hit"] == 1  # 确定性 1 命中 (000001.SZ, 仅第 2 日 ratio 可算)
    assert fg["n_hits"] == 1
    for sid in _REAL_IDS:
        assert by_id[sid]["n_symbols_covered"] == 2, sid

    # derived/eod 分支: 评估宇宙 = 全面板 symbol 集 (5)
    for sid in _EOD_IDS:
        assert by_id[sid]["n_symbols_covered"] == 5, sid
    assert by_id["auction_alpha"]["n_symbols_covered"] == 2  # real 分支 (enabled 非空)

    # 湖空 → 真列 n_symbols_covered==0 且 n_dates==0 仍 branch real (D-02)
    import shutil
    shutil.rmtree(data_dir / "kline_auction")
    report2 = svc.build_report(start=start, end=start + timedelta(days=1))
    by_id2 = {st["id"]: st for st in report2["strategies"]}
    for sid in _REAL_IDS:
        s2 = by_id2[sid]
        assert s2["branch"] == "real", sid
        assert s2["n_dates"] == 0, sid
        assert s2["n_symbols_covered"] == 0, sid
        assert s2["n_symbols_hit"] == 0, sid
    # alpha derived: 全验证窗口宇宙
    assert by_id2["auction_alpha"]["branch"] == "derived"
    assert by_id2["auction_alpha"]["n_dates"] == 2
    assert by_id2["auction_alpha"]["n_symbols_covered"] == 5


def test_minute_confirm_regression_after_coverage(repo_env):
    """BT-10 回归: coverage 扩展 (symbols 子块 + per-strategy n_symbols_*) 后
    minute_confirm:"not_applied" 注解不破 — 248 分区 fixture 全 9 策略逐项断言。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2025, 12, 1)
    end = start + timedelta(days=247)  # 2026-08-05
    _seed_enriched_cache(repo, days=248, start=start, symbols=_ENRICHED_SYMBOLS_5)
    _seed_auction_partitions_248(data_dir, start)
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=end)

    assert report["data_gate"] == "available"
    by_id = {st["id"]: st for st in report["strategies"]}
    assert set(by_id) == _AUCTION_FAMILY_IDS
    # 全 9 策略逐项断言 (BT-10: kline_minute 历史 CLOSED — 确认维度诚实受限)
    for st in report["strategies"]:
        assert st["minute_confirm"] == "not_applied", st["id"]
    assert by_id["auction_intraday_confirm"]["minute_confirm"] == "not_applied"


# ================================================================
# MIN-02 — 统计口径双报告 (coverage.minute_stats, caliber=statistical_minute_0930)
# ================================================================


def test_minute_stats_block_dual_caliber_parallel(repo_env):
    """MIN-02 双口径并列: coverage.symbols (canonical 撮合) 与 coverage.minute_stats
    (统计口径) 两独立键并存, 各按自身口径, 绝不相加; caliber 逐字标注。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(repo, days=2, start=start, symbols=_ENRICHED_SYMBOLS_5)
    # canonical 口径: 2 symbol 竞价分区 (555..565 窗口行)
    _seed_auction_partitions(
        data_dir, start, 2,
        {"000001.SZ": (180_000.0, 3_000_000.0), "000002.SZ": (180_000.0, 3_000_000.0)},
    )
    # 统计口径: 3 symbol 09:30 bar 分区 (与 canonical 宇宙不同子集, 双口径可比)
    for d in (start, start + timedelta(days=1)):
        _write_minute_partition(data_dir, d, _minute_rows(d, ("000001.SZ", "600519.SH", "300750.SZ")))

    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=start + timedelta(days=1))

    assert report["data_gate"] == "available"
    cov = report["coverage"]
    assert "symbols" in cov and "minute_stats" in cov  # 双口径并列
    ms = cov["minute_stats"]
    assert ms["caliber"] == "statistical_minute_0930"
    assert ms["auction_symbol_count"] == 3
    assert ms["symbol_coverage_ratio"] == pytest.approx(3 / 5)
    assert ms["universe_size"] == 5
    assert ms["dates_covered"] == [start.isoformat(), (start + timedelta(days=1)).isoformat()]
    # canonical 子块保持自身口径 (2 symbol) — 两键不相加、不混同
    assert cov["symbols"]["auction_symbol_count"] == 2
    assert ms["auction_symbol_count"] != cov["symbols"]["auction_symbol_count"]


def test_minute_stats_only_0930_rows(repo_env):
    """MIN-02 09:30-only: 统计只认 datetime.time()==09:30 的行; 09:31/14:59 行
    绝不进统计口径 (symbol 覆盖与日期集合均排除)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(
        repo, days=2, start=start,
        symbols=("000001.SZ", "600519.SH", "300750.SZ", "601318.SH"),
    )
    # 第一日: 09:30 只有 000001.SZ; 600519.SH 只有 09:31; 300750.SZ 只有 14:59
    rows = pl.concat([
        _minute_rows(start, ("000001.SZ",)),
        pl.DataFrame([{
            "symbol": "600519.SH",
            "datetime": datetime(2026, 8, 4, 9, 31),
            "open": 1328.36, "high": 1328.36, "low": 1328.36, "close": 1328.36,
            "volume": 999.0, "amount": None,
        }]),
        pl.DataFrame([{
            "symbol": "300750.SZ",
            "datetime": datetime(2026, 8, 4, 14, 59),
            "open": 200.0, "high": 200.0, "low": 200.0, "close": 200.0,
            "volume": 777.0, "amount": None,
        }]),
    ])
    _write_minute_partition(data_dir, start, rows)
    # 第二日: 分区在场但只有 09:31 行 → 该日绝不进统计口径 (dates_covered 只含实有 09:30 的日)
    _write_minute_partition(
        data_dir, start + timedelta(days=1),
        pl.DataFrame([{
            "symbol": "601318.SH",
            "datetime": datetime(2026, 8, 5, 9, 31),
            "open": 50.0, "high": 50.0, "low": 50.0, "close": 50.0,
            "volume": 888.0, "amount": None,
        }]),
    )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=start + timedelta(days=1))
    ms = report["coverage"]["minute_stats"]

    assert ms["auction_symbol_count"] == 1  # 只有 09:30 的 000001.SZ
    assert ms["dates_covered"] == [start.isoformat()]


def test_minute_stats_honest_empty(repo_env):
    """MIN-02 诚实空态: 无 kline_minute 分区 → minute_stats 全 0 同键形状
    (与 canonical 空态并列, 绝不编造覆盖/解锁)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(repo, days=2, start=start, symbols=_ENRICHED_SYMBOLS_5)
    _seed_auction_partitions(
        data_dir, start, 2,
        {"000001.SZ": (180_000.0, 3_000_000.0), "000002.SZ": (180_000.0, 3_000_000.0)},
    )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=start + timedelta(days=1))
    ms = report["coverage"]["minute_stats"]

    assert ms["caliber"] == "statistical_minute_0930"
    assert ms["auction_symbol_count"] == 0
    assert ms["symbol_coverage_ratio"] == pytest.approx(0.0)
    assert ms["unlock_met"] is False
    assert ms["dates_covered"] == []
    assert ms["universe_size"] == 5
    # canonical 子块如实非 0 — 双口径独立, 统计空态不拖累 canonical
    assert report["coverage"]["symbols"]["auction_symbol_count"] == 2


def test_minute_stats_unlock_gate_fields(repo_env):
    """MIN-02 解锁门可观测: unlock_threshold==0.94 (FA-04/RC-02 统计口径门);
    3/3 覆盖 → unlock_met True; 1/3 → False (诚实 partial, 绝不假解锁)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    syms3 = ("000001.SZ", "000002.SZ", "600519.SH")
    _seed_enriched_cache(repo, days=2, start=start, symbols=syms3)
    _seed_auction_partitions(
        data_dir, start, 2,
        {"000001.SZ": (180_000.0, 3_000_000.0), "000002.SZ": (180_000.0, 3_000_000.0)},
    )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    # 3/3 覆盖 → 解锁
    for d in (start, start + timedelta(days=1)):
        _write_minute_partition(data_dir, d, _minute_rows(d, syms3))
    report = svc.build_report(start=start, end=start + timedelta(days=1))
    ms = report["coverage"]["minute_stats"]
    assert ms["unlock_threshold"] == pytest.approx(0.94)
    assert ms["auction_symbol_count"] == 3
    assert ms["unlock_met"] is True

    # 1/3 → 诚实 partial, 绝不假解锁
    import shutil
    shutil.rmtree(data_dir / "kline_minute")
    _write_minute_partition(data_dir, start, _minute_rows(start, ("000001.SZ",)))
    report2 = svc.build_report(start=start, end=start + timedelta(days=1))
    ms2 = report2["coverage"]["minute_stats"]
    assert ms2["auction_symbol_count"] == 1
    assert ms2["unlock_met"] is False


def test_minute_stats_amount_derivation_closed(repo_env):
    """MIN-02 amount 诚实派生: OHLC 全等 09:30 bar → volume×close×100
    (521×1328.36×100≈69,207,556 契约闭合, RESEARCH live 实测); 量恒等手。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(repo, days=2, start=start, symbols=("600519.SH",))
    _write_minute_partition(data_dir, start, _minute_rows(start, ("600519.SH",)))
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=start + timedelta(days=1))
    ms = report["coverage"]["minute_stats"]

    assert ms["auction_volume_hands"] == pytest.approx(_MINUTE_ANCHOR_VOLUME)
    assert ms["auction_amount_yuan"] == pytest.approx(_MINUTE_ANCHOR_AMOUNT, abs=1.0)
    assert ms["amount_unknown_count"] == 0


def test_minute_stats_amount_unknown_non_closed_ohlc(repo_env):
    """MIN-02 amount 诚实缺额: OHLC 不全等 09:30 bar → 不计入 auction_amount_yuan,
    amount_unknown_count==1 (绝不猜, RESEARCH Pitfall 5)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(repo, days=2, start=start, symbols=("600519.SH",))
    _write_minute_partition(data_dir, start, _minute_rows(start, ("600519.SH",), ohlc_eq=False))
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=start + timedelta(days=1))
    ms = report["coverage"]["minute_stats"]

    assert ms["auction_volume_hands"] == pytest.approx(_MINUTE_ANCHOR_VOLUME)  # 量恒等计入
    assert ms["auction_amount_yuan"] == pytest.approx(0.0)
    assert ms["amount_unknown_count"] == 1


def test_minute_stats_amount_mixed_symbols(repo_env):
    """MIN-02 amount 混合: 2 symbol (一全等一非全等) → 派生额只含全等者,
    amount_unknown_count==1。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(repo, days=2, start=start, symbols=("600519.SH", "000001.SZ"))
    _write_minute_partition(
        data_dir, start,
        pl.concat([
            _minute_rows(start, ("600519.SH",)),                                   # 全等 → 派生
            _minute_rows(start, ("000001.SZ",), price=10.0, ohlc_eq=False),        # 非全等 → UNKNOWN
        ]),
    )
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=start + timedelta(days=1))
    ms = report["coverage"]["minute_stats"]

    assert ms["auction_symbol_count"] == 2
    assert ms["auction_amount_yuan"] == pytest.approx(_MINUTE_ANCHOR_AMOUNT, abs=1.0)
    assert ms["amount_unknown_count"] == 1


def test_digest_source_default_unknown(repo_env):
    """MIN-03 源身份诚实默认: build_report() 缺省 minute_source →
    coverage.minute_stats["source"] == "unknown" (湖无 provenance 列, 报告绝不猜源)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(repo, days=2, start=start, symbols=("600519.SH", "000001.SZ"))
    _write_minute_partition(data_dir, start, _minute_rows(start, ("600519.SH",)))
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(start=start, end=start + timedelta(days=1))
    ms = report["coverage"]["minute_stats"]

    assert ms["source"] == "unknown"


def test_digest_source_declared(repo_env):
    """MIN-03 源身份声明: build_report(minute_source="tencent-mkline") →
    coverage.minute_stats["source"] == "tencent-mkline" (覆盖声明 = 源插件深度)。"""
    from app.services.auction_validation import AuctionValidationService

    repo, data_dir = repo_env
    start = date(2026, 8, 4)
    _seed_enriched_cache(repo, days=2, start=start, symbols=("600519.SH", "000001.SZ"))
    _write_minute_partition(data_dir, start, _minute_rows(start, ("600519.SH",)))
    engine = _make_engine()
    svc = AuctionValidationService(repo, engine, probe_resolver=lambda: _available_verdict())

    report = svc.build_report(
        start=start, end=start + timedelta(days=1), minute_source="tencent-mkline",
    )
    ms = report["coverage"]["minute_stats"]

    assert ms["source"] == "tencent-mkline"
