"""竞价回测服务 ``run_full_backtest`` 单测 (BT-07/BT-09) — 稀疏湖诚实 / 前瞻公式
手算 / 分支互斥 / 确定性 run_id 幂等 + 原子无 .tmp / 分钟注解 + manifest / 写根隔离。

Hermetic (镜像 test_auction_validation_report.py):
- 生产 import 全放测试函数内 (仓库约定: 模块级不触发 DuckDB 单例);
- repo 用 ``repo_env`` fixture (tmp data_dir + DataStore + KlineRepository);
- enriched 缓存直接 seed ``repo._enriched_history_cache`` (get_enriched_range 快路径同源);
- ``kline_auction`` 分区手工写盘; 服务历史闸门 = 分区存在性 (D-03), 零网络 (不 probe)。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import polars as pl
import pytest

# 竞价族 9 策略 (与服务模块硬编码集一致 — 独立复述, 防漂移)
_AUCTION_FAMILY_IDS = {
    "auction_fast_grab", "auction_allround", "t1_flash", "auction_intraday_confirm",
    "auction_alpha", "golden_230", "auction_bullish", "auction_preopen_quant",
    "auction_early_star",
}
# 4 个 requires_auction_data 真列策略 / 4 个 EOD 代理
_REAL_IDS = {"auction_fast_grab", "auction_allround", "t1_flash", "auction_intraday_confirm"}
_EOD_IDS = {"golden_230", "auction_bullish", "auction_preopen_quant", "auction_early_star"}


# ================================================================
# hermetic helpers (镜像 test_auction_validation_report.py, 防跨文件 import 耦合)
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


def _make_engine():
    """真 StrategyEngine (builtin 策略目录) — 回测不调 engine.run, loader 用 dummy。

    构造形镜像 main.py:555-563; loader 返回 None (回测只消费 engine 定义面)。
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

    确定性取值 (镜像 test_auction_validation_report.py:103-135):
    - 恒定 volume → 前 5 日均量 = volume, auction_volume_ratio 精确可手算;
    - open 按 symbol (000001→10.0 / 其余→20.0), close = open × close_ratio (收阳);
    - open_gap 3% / change_pct 3.5% / vol_ratio_5d 1.6 / amount = volume×10 = 1M
      → 满足 auction_bullish (2%/2%) 等 EOD 分支的 META 默认阈值。

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


def _real_rows(res) -> pl.DataFrame:
    """长格式行中真列分支的行子集。"""
    return res["rows"].filter(pl.col("branch") == "real")


# ================================================================
# Test 1 — 稀疏湖诚实 (BT-07 诚实覆盖)
# ================================================================


def test_full_backtest_sparse_lake_honest_rows(repo_env):
    """5-symbol × 2 日 enriched + 仅 2 symbols 的 kline_auction 分区 → 真列策略
    hits ⊆ {000001.SZ, 000002.SZ} (稀疏诚实, 绝不产生全市场规模结果); coverage.symbols
    双块如实; derived/eod 全窗口统计。"""
    from app.services.auction_backtest import run_full_backtest

    repo, data_dir = repo_env
    symbols = ("000001.SZ", "000002.SZ", "600000.SH", "600001.SH", "600002.SH")
    d0, d1 = date(2026, 3, 20), date(2026, 3, 21)
    _seed_enriched_cache(repo, symbols=symbols, days=2, start=d0)
    # 仅 2 symbols 有竞价分区; auction_volume 5M / volume 100k → ratio 50 (次日) 过阈值
    for d in (d0, d1):
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {
                "000001.SZ": (5_000_000.0, 2_000_000.0),
                "000002.SZ": (5_000_000.0, 2_000_000.0),
            }),
        )
    engine = _make_engine()

    res = run_full_backtest(repo, engine, symbols=list(symbols))


    stats = {s["id"]: s for s in res["strategies"]}
    assert set(stats) == _AUCTION_FAMILY_IDS, "9 竞价族策略全部评估"

    # 真列分支 (auction 列门控的策略): hits 只可能落在有竞价列的 2 symbols
    # (稀疏诚实, 绝不 derived-downgrade); auction_intraday_confirm 日线初筛仅用
    # open_gap (镜像验证报告语义) → 不在此约束内
    _AUCTION_COL_GATED = {"auction_fast_grab", "auction_allround", "t1_flash"}
    gated_rows = _real_rows(res).filter(pl.col("strategy").is_in(_AUCTION_COL_GATED))
    assert set(gated_rows["symbol"].unique().to_list()) <= {"000001.SZ", "000002.SZ"}
    for sid in _REAL_IDS:
        assert stats[sid]["branch"] == "real"
        assert stats[sid]["n_symbols_covered"] == 2
        assert stats[sid]["n_dates"] == 2  # enabled ∩ enriched = 2 日
    for sid in _AUCTION_COL_GATED:
        assert stats[sid]["n_symbols_hit"] == 2, "auction 列门控策略命中必 ⊆ 2-symbol 宇宙"
    assert stats["auction_alpha"]["branch"] == "real"  # enabled 非空 → 真列分支

    # derived/eod 分支: 全窗口统计
    for sid in _EOD_IDS:
        assert stats[sid]["branch"] == "eod"
        assert stats[sid]["n_dates"] == 2
        assert stats[sid]["n_symbols_covered"] == 2  # 诚实: 竞价列仅覆盖 2 symbols

    # coverage.symbols 双块如实 (2-symbol 稀疏宇宙)
    assert res["coverage"]["symbols"] == {
        "auction_symbol_count": 2,
        "enriched_symbol_count": 5,
        "symbol_coverage_ratio": 0.4,
        "auction_rows_present": 4,  # 2 symbols × 2 日 × 1 行
        "auction_rows_expected": 10,  # 5 symbols × 2 dates
    }
    assert res["coverage"]["dates"]["auction_enabled_count"] == 2
    assert res["coverage"]["dates"]["enriched_count"] == 2
    assert res["coverage"]["dates"]["coverage_ratio"] == 1.0

    # 真列命中行确实落 2-symbol 宇宙且携带竞价口径列
    allround = _real_rows(res).filter(pl.col("strategy") == "auction_allround")
    assert allround.height == 2  # 两 symbol 次日 ratio=50 均过阈值
    assert set(allround["symbol"].unique().to_list()) == {"000001.SZ", "000002.SZ"}


# ================================================================
# Test 2 — BT-04 前瞻公式手算 + 停牌/末日边界 (绝不 0 填)
# ================================================================


def test_full_backtest_forward_outcomes_bt04_formulas(repo_env):
    """2 日 fixture 手算: T 日命中 (open 10.0, close 10.5), T+1 (open 10.8, close 11.5)
    → next_day_open_ret = 0.08, next_day_close_ret = 0.15, open_gap_outcome ≈ 0.028571;
    停牌 symbol 结果日缺行 → outcome_missing + n_missing_outcomes 计数 + 公式列 null
    (绝不 0 填); 窗口末日命中 → 结果日缺失 (calendar null) → outcome_missing。"""
    from app.services.auction_backtest import run_full_backtest

    repo, data_dir = repo_env
    d0, d1 = date(2026, 3, 20), date(2026, 3, 21)
    _seed_enriched_cache(
        repo,
        symbols=("000001", "600000"),
        days=2,
        start=d0,
        overrides={("000001", d1): {"open": 10.8, "close": 11.5}},
    )
    # 停牌: 600000 结果日 (d1) 缺行
    cache = repo._enriched_history_cache
    repo._enriched_history_cache = cache.filter(
        ~((pl.col("symbol") == "600000") & (pl.col("date") == d1))
    )
    engine = _make_engine()

    res = run_full_backtest(repo, engine, strategy_ids=["auction_bullish"])

    stats = res["strategies"][0]
    assert stats["id"] == "auction_bullish" and stats["branch"] == "eod"
    rows = res["rows"].to_dicts()
    by_key = {(r["symbol"], r["as_of"]): r for r in rows}
    assert len(rows) == 3  # 000001/T, 000001/T+1, 600000/T

    # T 日命中 (000001): 结果日存在 → 三公式手算精确
    r_t = by_key[( "000001", d0)]
    assert r_t["entry_open"] == 10.0 and r_t["open_t1"] == 10.8 and r_t["close_t1"] == 11.5
    assert r_t["next_day_open_ret"] == pytest.approx(0.08)
    assert r_t["next_day_close_ret"] == pytest.approx(0.15)
    assert r_t["open_gap_outcome"] == pytest.approx(10.8 / 10.5 - 1)
    assert r_t["outcome_missing"] is False

    # 窗口末日命中 (000001/T+1): 结果日缺失 → outcome_missing, 公式列 null 绝不 0 填
    r_end = by_key[("000001", d1)]
    assert r_end["outcome_missing"] is True
    assert r_end["open_t1"] is None and r_end["close_t1"] is None
    assert r_end["next_day_open_ret"] is None
    assert r_end["next_day_close_ret"] is None
    assert r_end["open_gap_outcome"] is None

    # 停牌 symbol (600000/T): 结果日缺行 → outcome_missing, 公式列 null
    r_halt = by_key[("600000", d0)]
    assert r_halt["outcome_missing"] is True
    assert r_halt["next_day_open_ret"] is None
    assert r_halt["next_day_close_ret"] is None
    assert r_halt["open_gap_outcome"] is None

    # n_missing_outcomes 统计排除 (绝不填充): 2 = 末日 1 + 停牌 1
    assert stats["n_missing_outcomes"] == 2
    # 每指标独立 n: 仅 000001/T 一个有效样本
    fs_open = stats["forward_stats"]["next_day_open_ret"]
    assert fs_open["mean"] == pytest.approx(0.08)
    assert fs_open["median"] == pytest.approx(0.08)
    assert fs_open["win_rate"] == 1.0 and fs_open["n"] == 1
    fs_close = stats["forward_stats"]["next_day_close_ret"]
    assert fs_close["mean"] == pytest.approx(0.15)
    assert fs_close["median"] == pytest.approx(0.15)
    assert fs_close["win_rate"] == 1.0 and fs_close["n"] == 1
    assert stats["forward_stats"]["open_gap_outcome"]["n"] == 1

    # 行级 outcome_missing 与 n_missing_outcomes 计数一致 (零漂移)
    assert sum(1 for r in rows if r["outcome_missing"]) == stats["n_missing_outcomes"]


# ================================================================
# Test 3 — branch 互斥 (BT-05)
# ================================================================


def test_full_backtest_branch_mutual_exclusion(repo_env):
    """每行 branch ∈ 该策略单值; 4 real 恒 "real" (含湖空 → n_dates==0 仍 real,
    绝不落 derived); auction_alpha = "real" 当 enabled 非空 / "derived" 当 enabled 空;
    4 eod 恒 "eod"; 同 run 内每策略只产单 branch 行。"""
    from app.services.auction_backtest import run_full_backtest

    repo, data_dir = repo_env
    d0, d1 = date(2026, 3, 20), date(2026, 3, 21)
    _seed_enriched_cache(repo, symbols=("000001", "600000"), days=2, start=d0)
    engine = _make_engine()

    # 湖空: 4 real 仍 real (n_dates==0), alpha → derived, 4 eod → eod
    res_empty = run_full_backtest(repo, engine)
    stats_empty = {s["id"]: s for s in res_empty["strategies"]}
    for sid in _REAL_IDS:
        assert stats_empty[sid]["branch"] == "real"
        assert stats_empty[sid]["n_dates"] == 0, "湖空绝不落 derived / 绝不伪造 n_dates"
    assert stats_empty["auction_alpha"]["branch"] == "derived"
    for sid in _EOD_IDS:
        assert stats_empty[sid]["branch"] == "eod"
        assert stats_empty[sid]["n_dates"] == 2

    # 湖有分区 (enabled 非空): 4 real 恒 real (n_dates>0), alpha → real
    for d in (d0, d1):
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {
                "000001": (5_000_000.0, 2_000_000.0),
                "600000": (5_000_000.0, 2_000_000.0),
            }),
        )
    res = run_full_backtest(repo, engine)
    stats = {s["id"]: s for s in res["strategies"]}
    for sid in _REAL_IDS:
        assert stats[sid]["branch"] == "real"
        assert stats[sid]["n_dates"] == 2
    assert stats["auction_alpha"]["branch"] == "real"
    for sid in _EOD_IDS:
        assert stats[sid]["branch"] == "eod"

    # 同 run 内每策略只产单 branch 行 (行级互斥)
    per_strategy = res["rows"].group_by(["strategy", "branch"]).len().sort("strategy")
    one_branch_each = per_strategy.group_by("strategy").agg(pl.len()).filter(
        pl.col("len") != 1
    )
    assert one_branch_each.is_empty(), "每策略行必须只带一个 branch"
    branch_by_strategy = {
        row["strategy"]: row["branch"] for row in per_strategy.iter_rows(named=True)
    }
    for sid, br in branch_by_strategy.items():
        assert br == stats[sid]["branch"]


# ================================================================
# Test 4 — run_id 确定性幂等 + 原子无 .tmp (BT-09)
# ================================================================


def test_full_backtest_deterministic_run_id_idempotent(repo_env):
    """同配置两次运行 → 同 run_id, 二次 reused==True 且分区文件 mtime 不变 (跳过重写);
    改窗口/改 symbols/改 strategy_ids 任一 → 异 run_id; 跑后无 *.tmp 残留;
    part.parquet + manifest.json 均存在且可读。"""
    from app.services.auction_backtest import run_full_backtest

    repo, data_dir = repo_env
    symbols = ("000001.SZ", "000002.SZ")
    d0, d1, d2 = date(2026, 3, 20), date(2026, 3, 21), date(2026, 3, 22)
    _seed_enriched_cache(repo, symbols=symbols, days=3, start=d0)
    for d in (d0, d1):
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {
                "000001.SZ": (5_000_000.0, 2_000_000.0),
                "000002.SZ": (5_000_000.0, 2_000_000.0),
            }),
        )
    engine = _make_engine()

    # 同配置两次 → 同 run_id, 二次幂等跳过 (wrote=False, reused=True, mtime 不变)
    r1 = run_full_backtest(repo, engine)
    part_path = data_dir / "backtest_results" / f"run_id={r1['run_id']}" / "part.parquet"
    assert part_path.exists()
    assert (data_dir / "backtest_results" / f"run_id={r1['run_id']}" / "manifest.json").exists()
    mtime_before = part_path.stat().st_mtime_ns

    r2 = run_full_backtest(repo, engine)
    assert r2["run_id"] == r1["run_id"]
    assert r2["wrote"] is False and r2["reused"] is True
    assert r2["status"] == "reused"
    assert part_path.stat().st_mtime_ns == mtime_before, "幂等跳过不得重写分区"

    # 改窗口 → 异 run_id
    r3 = run_full_backtest(repo, engine, end=d1)
    assert r3["run_id"] != r1["run_id"]

    # 改 symbols → 异 run_id (稀疏 2-symbol 与全市场绝不共 run_id)
    r4 = run_full_backtest(repo, engine, symbols=["000001.SZ"])
    assert r4["run_id"] != r1["run_id"]

    # 改 strategy_ids → 异 run_id
    r5 = run_full_backtest(repo, engine, strategy_ids=["auction_bullish"])
    assert r5["run_id"] != r1["run_id"]

    # 湖覆盖变化 → 异 run_id (RC-01: 同命令 + 湖新增分区 → 新鲜 run_id, 绝不幂等跳过)
    _write_auction_partition(
        data_dir, d2,
        _auction_rows(d2, {
            "000001.SZ": (5_000_000.0, 2_000_000.0),
            "000002.SZ": (5_000_000.0, 2_000_000.0),
        }),
    )
    r6 = run_full_backtest(repo, engine)  # 同命令, 湖新增 d2 分区 (enabled dates 2→3)
    assert r6["run_id"] != r1["run_id"]
    assert r6["wrote"] is True
    # 同湖同命令 → 幂等 (RC-01: 同覆盖 reused, part 不重写)
    r7 = run_full_backtest(repo, engine)
    assert r7["run_id"] == r6["run_id"]
    assert r7["wrote"] is False and r7["reused"] is True
    assert r7["status"] == "reused"

    # 无 .tmp 残留; part.parquet + manifest 可读
    assert list((data_dir / "backtest_results").rglob("*.tmp")) == []
    rows = pl.read_parquet(part_path)
    assert rows.height == r1["rows"].height
    manifest = json.loads(
        (data_dir / "backtest_results" / f"run_id={r1['run_id']}" / "manifest.json")
        .read_text(encoding="utf-8")
    )
    assert manifest["fingerprint"] and manifest["run_id"] == r1["run_id"]
    assert "start" in manifest["fingerprint"] and "symbols" in manifest["fingerprint"]


def test_full_backtest_run_id_lake_digest_tracks_coverage(repo_env):
    """湖覆盖 digest 是 run_id 身份成员 (RC-01): 同输入 + 异 digest → 异 run_id;
    同 digest → 同 run_id; 缺省 None → 旧 blob (向后兼容); 12-hex 契约不变。"""
    from app.services.auction_backtest import _compute_run_id
    import re
    kw = dict(strategy_ids=["auction_bullish"], start=date(2026, 3, 20),
              end=date(2026, 3, 21), params_snapshot={}, strategy_version="v1",
              symbols=["000001.SZ"])
    sparse = _compute_run_id(**kw, lake_digest=(2, 2))
    full = _compute_run_id(**kw, lake_digest=(37, 248))
    sparse2 = _compute_run_id(**kw, lake_digest=(2, 2))
    legacy = _compute_run_id(**kw)  # None → 修复前 blob (向后兼容缺省)
    assert sparse != full          # 覆盖变化 → 新鲜 run_id
    assert sparse == sparse2       # 同覆盖 → 幂等同 id
    assert legacy != sparse        # digest 成员改变身份 (修复即语义翻转)
    for rid in (sparse, full, legacy):
        assert re.fullmatch(r"[0-9a-f]{12}", rid), "run_id 前缀 12-hex 契约"


# ================================================================
# Test 5 — 分钟注解 (BT-10) + manifest provenance
# ================================================================


def test_full_backtest_minute_annotation_and_manifest(repo_env):
    """全部行 minute_confirm == "not_applied"; manifest 字段集 + origin 'research' +
    strategy_version 非空 + coverage dates/symbols 双块 + minute_note 含 kline_minute。"""
    from app.services.auction_backtest import run_full_backtest

    repo, data_dir = repo_env
    d0, d1 = date(2026, 3, 20), date(2026, 3, 21)
    _seed_enriched_cache(repo, symbols=("000001", "600000"), days=2, start=d0)
    for d in (d0, d1):
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {
                "000001": (5_000_000.0, 2_000_000.0),
                "600000": (5_000_000.0, 2_000_000.0),
            }),
        )
    engine = _make_engine()

    res = run_full_backtest(repo, engine)
    assert res["rows"].height > 0
    assert res["rows"]["minute_confirm"].unique().to_list() == ["not_applied"]
    assert res["rows"]["origin"].unique().to_list() == ["research"]
    assert res["rows"]["strategy_version"].unique().to_list() == [res["strategy_version"]]
    assert res["strategy_version"], "strategy_version 非空 (strategy_fingerprint 共源)"

    manifest_path = data_dir / "backtest_results" / f"run_id={res['run_id']}" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest) == {
        "run_id", "origin", "strategy_version", "created_at", "window", "strategies",
        "params", "coverage", "per_date", "minute_note", "fingerprint",
    }
    assert manifest["origin"] == "research"
    assert manifest["run_id"] == res["run_id"]
    assert "kline_minute" in manifest["minute_note"]
    assert "集合竞价统计" in manifest["minute_note"]  # MIN-03: 09:30 bar = 统计口径诚实标注
    assert "统计口径" in manifest["minute_note"]  # caliber=statistical_minute_0930 锚点
    assert "dates_covered" in manifest["minute_note"]  # 实际覆盖以 minute_stats.dates_covered 为准
    assert set(manifest["window"]) == {
        "requested_start", "requested_end", "effective_start", "effective_end",
    }
    assert set(manifest["coverage"]) == {"dates", "symbols"}
    assert set(manifest["coverage"]["dates"]) == {
        "auction_enabled_count", "enriched_count", "coverage_ratio",
    }
    assert set(manifest["coverage"]["symbols"]) == {
        "auction_symbol_count", "enriched_symbol_count", "symbol_coverage_ratio",
        "auction_rows_present", "auction_rows_expected",
    }
    assert manifest["strategies"], "manifest 策略摘要非空"
    assert set(manifest["strategies"][0]) == {
        "id", "branch", "n_dates", "n_hits", "n_symbols_covered", "n_symbols_hit",
        "n_missing_outcomes", "forward_stats",
    }
    assert set(manifest["params"]) == {s["id"] for s in res["strategies"]}
    assert manifest["per_date"] and set(manifest["per_date"][0]) == {
        "date", "n_screened", "n_hits",
    }
    # 行级 minute_confirm 与 manifest 注解一致 (BT-10 诚实受限)
    assert res["strategies"][0]["minute_confirm"] == "not_applied"


# ================================================================
# Test 6 — 写根隔离 (E2): 只写 backtest_results/
# ================================================================


def test_full_backtest_write_root_isolation(repo_env):
    """跑前写 strategy_cache.json / screener_results 哨兵 → 跑后 byte-identical;
    data_dir 下除 backtest_results/ 与哨兵外无新增文件 (镜像
    test_pool_backfill_never_creates_premarket_root 形)。"""
    from app.services.auction_backtest import run_full_backtest

    repo, data_dir = repo_env
    d0, d1 = date(2026, 3, 20), date(2026, 3, 21)
    _seed_enriched_cache(repo, symbols=("000001", "600000"), days=2, start=d0)
    for d in (d0, d1):
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {
                "000001": (5_000_000.0, 2_000_000.0),
                "600000": (5_000_000.0, 2_000_000.0),
            }),
        )
    engine = _make_engine()

    # 哨兵: 写面绝不触碰 strategy_cache / screener_results
    cache_path = data_dir / "user_data" / "strategy_cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b"sentinel")
    screener_part = data_dir / "screener_results" / "date=2026-08-04" / "part.json"
    screener_part.parent.mkdir(parents=True, exist_ok=True)
    screener_part.write_bytes(b"sentinel")
    before_cache, before_screener = cache_path.read_bytes(), screener_part.read_bytes()
    files_before = {p for p in data_dir.rglob("*") if p.is_file()}

    res = run_full_backtest(repo, engine)

    assert res["path"].startswith(str(data_dir / "backtest_results"))
    assert cache_path.read_bytes() == before_cache, "回测路径绝不得改写 strategy_cache.json"
    assert screener_part.read_bytes() == before_screener, "回测路径绝不得改写 screener_results"

    # 服务新增文件只可能落在 backtest_results/ 根下 (E2 写根隔离)
    new_files = [p for p in data_dir.rglob("*") if p.is_file() and p not in files_before]
    assert new_files, "回测运行至少应写出 part.parquet + manifest.json"
    assert all("backtest_results" in p.parts for p in new_files)


# ================================================================
# Test 7 — --force 强制重写 (RC-04)
# ================================================================


def test_full_backtest_force_rewrites_when_fingerprint_matches(repo_env):
    """同配置 + force → 强制重写 (RC-04): 同 run_id, wrote=True, part mtime 变化,
    manifest 记 rewritten_at; 无 force → 幂等语义不变; 无 .tmp 残留。"""
    from app.services.auction_backtest import run_full_backtest

    repo, data_dir = repo_env
    symbols = ("000001.SZ", "000002.SZ")
    d0, d1, d2 = date(2026, 3, 20), date(2026, 3, 21), date(2026, 3, 22)
    _seed_enriched_cache(repo, symbols=symbols, days=3, start=d0)
    for d in (d0, d1):
        _write_auction_partition(
            data_dir, d,
            _auction_rows(d, {
                "000001.SZ": (5_000_000.0, 2_000_000.0),
                "000002.SZ": (5_000_000.0, 2_000_000.0),
            }),
        )
    engine = _make_engine()

    # 同配置 + force → 强制重写 (RC-04): 同 run_id, wrote=True, part mtime 变化, manifest 记 rewritten_at
    r1 = run_full_backtest(repo, engine)
    part_path = data_dir / "backtest_results" / f"run_id={r1['run_id']}" / "part.parquet"
    mtime_before = part_path.stat().st_mtime_ns
    r2 = run_full_backtest(repo, engine, force=True)
    assert r2["run_id"] == r1["run_id"]
    assert r2["wrote"] is True and r2["reused"] is False
    assert r2["status"] == "ok"
    assert part_path.stat().st_mtime_ns != mtime_before, "force 必须重写分区"
    manifest = json.loads((data_dir / "backtest_results" / f"run_id={r1['run_id']}" / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert "rewritten_at" in manifest, "force 覆写 provenance 必须记录 rewritten_at"
    # 无 force → 幂等语义不变 (指纹匹配仍 reused)
    r3 = run_full_backtest(repo, engine)
    assert r3["wrote"] is False and r3["reused"] is True
    # 无 .tmp 残留
    assert list((data_dir / "backtest_results").rglob("*.tmp")) == []


def test_full_backtest_cli_force_flag(tmp_path, monkeypatch):
    """--force (RC-04): --help 列出旗标 exit 0; hermetic main(["--force"]) 经
    run_full_backtest 绑定透传 force=True → exit 0 (W1: ok-shaped fake dict);
    main([]) → force=False。"""
    import importlib.util
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    cli_path = backend / "scripts" / "auction_backtest.py"
    spec = importlib.util.spec_from_file_location("auction_backtest_cli", cli_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    # 1. --help exit 0 且列出 --force
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--help"],
        capture_output=True, text=True, cwd=str(backend),
    )
    assert proc.returncode == 0, proc.stderr
    assert "--force" in proc.stdout, "help 缺 --force 旗标"

    # 2. hermetic 透传: monkeypatch 脚本模块的 run_full_backtest 绑定 → 捕获 kwargs。
    #    W1 (plan-check): main 的返回规则 = status ∈ {ok, reused} → 0, 因此 fake 必须
    #    是 ok-shaped dict 且带 _print_summary 读取的全部键 (诚实空 dict → exit 1, 不可用于 0 断言)。
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    captured: dict = {}
    fake_result = {
        "run_id": "a1b2c3d4e5f6",
        "status": "ok",
        "wrote": True,
        "reused": False,
        "strategy_version": "v-test",
        "origin": "research",
        "window": {
            "requested_start": "2026-03-20", "requested_end": "2026-03-22",
            "effective_start": "2026-03-20", "effective_end": "2026-03-22",
        },
        "strategies": [],
        "coverage": {"symbols": {
            "auction_symbol_count": 0, "enriched_symbol_count": 0,
            "symbol_coverage_ratio": 0.0, "auction_rows_present": 0,
            "auction_rows_expected": 0,
        }},
        "path": str(tmp_path / "backtest_results" / "run_id=a1b2c3d4e5f6"),
        "rows": pl.DataFrame({"x": [1]}),
    }

    def _fake_run_full_backtest(repo, engine, **kwargs):
        captured.update(kwargs)
        return fake_result

    monkeypatch.setattr(cli, "run_full_backtest", _fake_run_full_backtest)
    assert cli.main(["--force"]) == 0
    assert captured.get("force") is True
    captured.clear()
    assert cli.main([]) == 0
    assert captured.get("force") is False
