"""竞价策略族 (STRAT-04/05/06, Phase 21) — 引擎 seam + 受管列 auction_volume_ratio + P1 三策略。

覆盖 (21-01):
- Task 1 引擎 seam: requires_auction_data 短路空池 / 分钟单点截断 / time_window 校验 / minute_confirm_required
- Task 2 受管列 auction_volume_ratio: 前 5 日均量分母 (PIT-safe) + 注册纪律
- Task 3 P1 三策略: auction_fast_grab / auction_alpha / golden_230 + STRAT-03 回归

Hermetic: 生产 import 全部放测试函数内; _BUILTIN_DIR 指向真实 builtin 目录。
"""
from __future__ import annotations

import importlib.util
import re
from datetime import date, datetime, time as dt_time
from datetime import timedelta
from pathlib import Path

import polars as pl
import pytest

_BUILTIN_DIR = Path(__file__).resolve().parents[1] / "app" / "strategy" / "builtin"

_P1_IDS = ("auction_fast_grab", "auction_alpha", "golden_230")


# ================================================================
# hermetic helpers (镜像 test_auction_strategies._engine/_run_auction)
# ================================================================


def _engine(minute_loader=None):
    """真实 builtin 引擎 + 空 enriched loader; 可注入 minute_loader。"""
    from app.strategy.engine import StrategyEngine

    return StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[_BUILTIN_DIR],
        minute_loader=minute_loader,
    )


def _run_auction(engine, strategy_id: str, fixture: pl.DataFrame):
    return engine.run(
        strategy_id,
        as_of=date(2026, 8, 4),
        precomputed=fixture,
        overrides={"basic_filter": {"enabled": False}},
    )


def _write_strategy(tmp_path, name: str, body: str) -> Path:
    """写一个临时策略文件, 返回 strategies 目录。"""
    d = tmp_path / "strategies"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")
    return d


def _minute_partition_dir(tmp_path, trade_date: date) -> Path:
    d = tmp_path / "kline_minute" / f"date={trade_date.isoformat()}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ================================================================
# Task 1: 引擎 seam — 短路空池 / 分钟单点截断 / time_window 校验 / 缺分钟 fail-closed
# ================================================================


def test_engine_short_circuit(tmp_path):
    """requires_auction_data=True + 缺 auction_volume → 空 StrategyResult, 不抛 ColumnNotFoundError。"""
    from app.strategy.engine import StrategyEngine

    _write_strategy(tmp_path, "seam_probe.py", '''"""seam probe"""
import polars as pl

META = {
    "id": "seam_probe",
    "time_window": "pre_open",
    "requires_auction_data": True,
    "scoring": {"open_gap": 1.0},
}

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    # 若引擎未短路, 引用缺失列会抛 ColumnNotFoundError
    return pl.col("auction_volume") >= 0
''')
    engine = StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[tmp_path / "strategies"],
    )
    fixture = pl.DataFrame({"symbol": ["600001"], "open_gap": [0.03]})
    result = engine.run(
        "seam_probe", as_of=date(2026, 8, 4), precomputed=fixture,
        overrides={"basic_filter": {"enabled": False}},
    )
    assert result.total == 0
    assert result.rows == []
    assert result.strategy_id == "seam_probe"


def test_minute_truncation_no_future(tmp_path):
    """引擎单点截断: 分钟帧含 09:45 后 bar → "确认时刻之后无输入" 断言不触发且池只含 09:45 及之前确认的 symbol。"""
    from app.strategy.engine import StrategyEngine

    # 手工分钟帧 (canonical 8 列): 600001 与 600002 有 09:30–09:45 bar; 600003 只有 09:50/10:00 bar
    minute_dir = _minute_partition_dir(tmp_path, date(2026, 8, 4))
    bars = pl.DataFrame({
        "symbol": [
            "600001", "600001", "600001", "600001", "600001", "600001",
            "600002", "600002", "600002",
            "600003", "600003",
        ],
        "datetime": [
            datetime(2026, 8, 4, 9, 30), datetime(2026, 8, 4, 9, 35),
            datetime(2026, 8, 4, 9, 40), datetime(2026, 8, 4, 9, 45),
            datetime(2026, 8, 4, 9, 50), datetime(2026, 8, 4, 10, 0),
            datetime(2026, 8, 4, 9, 30), datetime(2026, 8, 4, 9, 45),
            datetime(2026, 8, 4, 10, 0),
            datetime(2026, 8, 4, 9, 50), datetime(2026, 8, 4, 10, 0),
        ],
        "open": [10.0] * 11,
        "high": [10.0] * 11,
        "low": [10.0] * 11,
        "close": [10.0] * 11,
        "volume": [100] * 11,
        "amount": [1000.0] * 11,
    })
    bars.write_parquet(minute_dir / "part.parquet")

    _write_strategy(tmp_path, "minute_probe.py", '''"""minute probe"""
import polars as pl
from datetime import time as dt_time

META = {
    "id": "minute_probe",
    "time_window": "intraday",
    "evaluation_time": "09:45",
    "minute_confirm_required": True,
    "scoring": {"open_gap": 1.0},
}

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("symbol").is_not_null()

def minute_confirm(df_minute: pl.DataFrame, params: dict) -> pl.DataFrame:
    # "确认时刻之后无输入" 硬回归 (T-21-01): 引擎截断后不应出现 >09:45 的 bar
    assert df_minute["datetime"].max().time() <= dt_time(9, 45), "确认时刻之后无输入"
    # 只确认 09:45 bar 存在的 symbol (600003 只有 09:50/10:00 bar → 截断后无行 → 落选)
    return df_minute.filter(pl.col("datetime").dt.time() == dt_time(9, 45))
''')

    def minute_loader(symbols, trade_date):
        return pl.scan_parquet(str(minute_dir / "part.parquet")).filter(
            pl.col("symbol").is_in(symbols)
        ).sort(["symbol", "datetime"]).collect()

    engine = StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[tmp_path / "strategies"],
        minute_loader=minute_loader,
    )
    daily = pl.DataFrame({
        "symbol": ["600001", "600002", "600003"],
        "open_gap": [0.03, 0.02, 0.04],
    })
    result = engine.run(
        "minute_probe", as_of=date(2026, 8, 4), precomputed=daily,
        overrides={"basic_filter": {"enabled": False}},
    )
    assert result.total == 2
    assert {r["symbol"] for r in result.rows} == {"600001", "600002"}
    assert "600003" not in {r["symbol"] for r in result.rows}


def test_time_window_default_and_validation(tmp_path):
    """未声明 time_window 的既有策略默认 intraday 照常加载; 非法 time_window → load_errors。"""
    from app.strategy.engine import StrategyEngine

    engine = _engine()
    metas = {m["id"]: m for m in engine.list_strategies()}
    assert metas["auction_bullish"]["time_window"] == "intraday"
    assert metas["auction_bullish"]["requires_auction_data"] is False
    assert metas["auction_bullish"]["evaluation_time"] is None

    _write_strategy(tmp_path, "bad_window.py", '''"""bad window"""
META = {"id": "bad_window", "time_window": "foo", "scoring": {"open_gap": 1.0}}
''')
    eng2 = StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[tmp_path / "strategies"],
    )
    errs = eng2.load_errors()
    assert any(e["file"] == "bad_window.py" for e in errs), f"expected load error, got {errs}"
    ids = {m["id"] for m in eng2.list_strategies()}
    assert "bad_window" not in ids


def test_missing_minute_required_fail_closed(tmp_path):
    """minute_confirm_required=True + minute_loader 返回空帧 → 空 StrategyResult (分钟数据缺席即空池)。"""
    from app.strategy.engine import StrategyEngine

    _write_strategy(tmp_path, "minute_req.py", '''"""minute required"""
import polars as pl
from datetime import time as dt_time

META = {
    "id": "minute_req",
    "time_window": "intraday",
    "evaluation_time": "09:45",
    "minute_confirm_required": True,
    "scoring": {"open_gap": 1.0},
}

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("symbol").is_not_null()

def minute_confirm(df_minute: pl.DataFrame, params: dict) -> pl.DataFrame:
    return df_minute
''')
    engine = StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[tmp_path / "strategies"],
        minute_loader=lambda symbols, trade_date: pl.DataFrame(),
    )
    daily = pl.DataFrame({"symbol": ["600001"], "open_gap": [0.03]})
    result = engine.run(
        "minute_req", as_of=date(2026, 8, 4), precomputed=daily,
        overrides={"basic_filter": {"enabled": False}},
    )
    assert result.total == 0
    assert result.rows == []

# ================================================================
# Task 2: 受管列 auction_volume_ratio (前 5 日均量分母, PIT-safe) + 注册纪律
# ================================================================


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_auction_columns)。"""
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


def _daily_frame() -> pl.DataFrame:
    """单日帧: symbol/date/open/close/open_gap。"""
    return pl.DataFrame({
        "symbol": ["000001", "600000"],
        "date": [date(2026, 8, 4), date(2026, 8, 4)],
        "open": [10.0, 20.0],
        "close": [10.5, 20.5],
        "open_gap": [0.01, 0.02],
    })


def _available_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.available, source="fake", probed_at=None, detail="available",
    )


def _patch_probe(monkeypatch, verdict) -> None:
    from app.services import auction_columns
    monkeypatch.setattr(auction_columns, "resolve_auction_probe", lambda: verdict)


def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    out = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


def _auction_rows() -> pl.DataFrame:
    """canonical 四列 (symbol, datetime, auction_volume, auction_amount), 09:20 窗口内。"""
    return pl.DataFrame({
        "symbol": ["000001", "600000"],
        "datetime": [datetime(2026, 8, 4, 9, 20), datetime(2026, 8, 4, 9, 20)],
        "auction_volume": [8000, 9000],
        "auction_amount": [42000.0, 48000.0],
    })


def _seed_history_cache(repo, trade_date: date, per_symbol_volumes: dict[str, list[float]]) -> None:
    """直接写 repo._enriched_history_cache: 前 5 交易日 + trade_date + 覆盖校验早期行。"""
    prior_dates = [trade_date - timedelta(days=i) for i in range(5, 0, -1)]  # d-5..d-1
    early = trade_date - timedelta(days=140)
    rows = []
    for sym, vols in per_symbol_volumes.items():
        assert len(vols) == 6, f"{sym}: 需要 6 个值 [d-5..d-1, d]"
        for d, v in zip([*prior_dates, trade_date], vols):
            rows.append({"symbol": sym, "date": d, "volume": v})
        # get_enriched_history 覆盖校验: cache_min <= warmup_start (lookback 6 → 132 日历日前)
        rows.append({"symbol": sym, "date": early, "volume": 1.0})
    repo._enriched_history_cache = pl.DataFrame(rows)


def test_auction_volume_ratio_prior_5d(repo_env, monkeypatch):
    """probe available + 分区有行 + 前 5 日历史 → auction_volume_ratio == 竞价量/前5日均量。"""
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    _write_auction_partition(data_dir, date(2026, 8, 4), _auction_rows())
    # 前 5 日均量: 000001 = 300.0, 600000 = 200.0
    _seed_history_cache(repo, date(2026, 8, 4), {
        "000001": [300.0, 300.0, 300.0, 300.0, 300.0, 500.0],
        "600000": [200.0, 200.0, 200.0, 200.0, 200.0, 500.0],
    })

    from app.services.auction_columns import attach_auction_columns
    out = attach_auction_columns(_daily_frame(), date(2026, 8, 4), repo)

    assert "auction_volume_ratio" in out.columns
    assert out.filter(pl.col("symbol") == "000001").select("auction_volume_ratio").item() == pytest.approx(8000 / 300.0)
    assert out.filter(pl.col("symbol") == "600000").select("auction_volume_ratio").item() == pytest.approx(9000 / 200.0)


def test_auction_volume_ratio_excludes_today_eod(repo_env, monkeypatch):
    """历史含 trade_date 当日 EOD 巨量 → 分母 = 前 5 日均量 (绝不含当日 EOD, PIT-safe)。"""
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    _write_auction_partition(data_dir, date(2026, 8, 4), _auction_rows())
    # 当日 volume = 1_000_000 (EOD 巨量); 前 5 日均量仍 = 300.0
    _seed_history_cache(repo, date(2026, 8, 4), {
        "000001": [300.0, 300.0, 300.0, 300.0, 300.0, 1_000_000.0],
        "600000": [200.0, 200.0, 200.0, 200.0, 200.0, 1_000_000.0],
    })

    from app.services.auction_columns import attach_auction_columns
    out = attach_auction_columns(_daily_frame(), date(2026, 8, 4), repo)

    assert "auction_volume_ratio" in out.columns
    # 若内联含当日 EOD 量: (300*5 + 1e6)/6 ≈ 167k → ratio ≈ 0.048, 断言 26.6667 锁死禁用
    assert out.filter(pl.col("symbol") == "000001").select("auction_volume_ratio").item() == pytest.approx(8000 / 300.0)


def test_auction_volume_ratio_absent_without_history(repo_env, monkeypatch):
    """无历史缓存 → auction_volume_ratio 列缺席 (诚实缺列, 不 0 填充)。"""
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    _write_auction_partition(data_dir, date(2026, 8, 4), _auction_rows())
    # repo._enriched_history_cache 默认 None → get_enriched_history 返回 None

    from app.services.auction_columns import attach_auction_columns
    out = attach_auction_columns(_daily_frame(), date(2026, 8, 4), repo)

    assert "auction_volume_ratio" not in out.columns
    assert "auction_volume" in out.columns  # 真实竞价列照常注入


def test_auction_volume_ratio_registry_discipline():
    """注册纪律: 在 ENRICHED_COLUMNS + BY_CATEGORY['auction'], 绝不在存储窄表/计算闭包。"""
    from app.indicators.pipeline import (
        ENRICHED_COLUMNS,
        ENRICHED_COLUMNS_BY_CATEGORY,
        ENRICHED_STORAGE_COLS,
        _ALL_INDICATOR_COLS,
    )
    assert "auction_volume_ratio" in ENRICHED_COLUMNS
    assert "auction_volume_ratio" in ENRICHED_COLUMNS_BY_CATEGORY["auction"]
    assert "auction_volume_ratio" not in ENRICHED_STORAGE_COLS
    assert "auction_volume_ratio" not in _ALL_INDICATOR_COLS
