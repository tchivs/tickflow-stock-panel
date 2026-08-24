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
    from app.strategy.engine import StrategyDataContext
    return engine.run(
        strategy_id,
        context=StrategyDataContext(
            asset_type="stock",
            timeframe="1d",
            as_of=date(2026, 8, 4),
            current=fixture,
        ),
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
    from app.strategy.engine import StrategyEngine, StrategyDataContext

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
        "seam_probe", context=StrategyDataContext(
            asset_type="stock", timeframe="1d",
            as_of=date(2026, 8, 4), current=fixture,
        ),
        overrides={"basic_filter": {"enabled": False}},
    )
    assert result.total == 0
    assert result.rows == []
    assert result.strategy_id == "seam_probe"


def test_minute_truncation_no_future(tmp_path):
    """引擎单点截断: 分钟帧含 09:45 后 bar → "确认时刻之后无输入" 断言不触发且池只含 09:45 及之前确认的 symbol。"""
    from app.strategy.engine import StrategyEngine, StrategyDataContext

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
        "minute_probe", context=StrategyDataContext(
            asset_type="stock", timeframe="1d",
            as_of=date(2026, 8, 4), current=daily,
        ),
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
    assert any(e["file"].endswith("bad_window.py") for e in errs), f"expected load error, got {errs}"
    ids = {m["id"] for m in eng2.list_strategies()}
    assert "bad_window" not in ids


def test_missing_minute_required_fail_closed(tmp_path):
    """minute_confirm_required=True + minute_loader 返回空帧 → 空 StrategyResult (分钟数据缺席即空池)。"""
    from app.strategy.engine import StrategyEngine, StrategyDataContext

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
        "minute_req", context=StrategyDataContext(
            asset_type="stock", timeframe="1d",
            as_of=date(2026, 8, 4), current=daily,
        ),
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

# ================================================================
# Task 3: P1 三策略 — auction_fast_grab / auction_alpha / golden_230
# ================================================================


def test_fast_grab_bands():
    """甜点区 2.8%–3.5% + >7% 风险带剔除 + 量比/金额阈值。"""
    engine = _engine()
    fixture = pl.DataFrame({
        "symbol": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"],
        "open_gap": [0.030, 0.020, 0.050, 0.080, 0.030, 0.030, 0.035],
        "auction_volume": [8000] * 7,  # 短路闸门列: requires_auction_data 要求存在
        "auction_volume_ratio": [2.0, 2.0, 2.0, 2.0, 1.0, 2.0, 2.0],
        "auction_amount": [3_000_000.0, 3_000_000.0, 3_000_000.0, 3_000_000.0, 3_000_000.0, 1_000_000.0, 3_000_000.0],
    })
    result = _run_auction(engine, "auction_fast_grab", fixture)
    hits = {r["symbol"] for r in result.rows}
    assert hits == {"A1", "A7"}       # A1 甜点内三因子全达标; A7 恰在上界 3.5% 入选
    assert "A2" not in hits           # 甜点外 (2.0% < 2.8%)
    assert "A3" not in hits           # 甜点外 (5.0% > 3.5%)
    assert "A4" not in hits           # >7% 风险带剔除
    assert "A5" not in hits           # 量比 1.0 < 1.5
    assert "A6" not in hits           # 金额 1M < 2M


def test_fast_grab_fail_closed(repo_env, monkeypatch):
    """probe 非 available 三态 → 竞价列缺席 → 引擎短路空池 (双保险)。"""
    from app.services.auction_probe import (
        _ERROR_DETAIL_MAX,
        AuctionProbeStatus,
        AuctionProbeVerdict,
    )
    from app.services.auction_columns import attach_auction_columns
    repo, _ = repo_env
    statuses = [
        (AuctionProbeStatus.not_configured, "not configured"),
        (AuctionProbeStatus.fail_closed, "fail closed"),
        (AuctionProbeStatus.error, ("x" * (_ERROR_DETAIL_MAX + 10))[:_ERROR_DETAIL_MAX]),
    ]
    for status, detail in statuses:
        verdict = AuctionProbeVerdict(status=status, source="fake", probed_at=None, detail=detail)
        _patch_probe(monkeypatch, verdict)
        frame = attach_auction_columns(_daily_frame(), date(2026, 8, 4), repo)
        assert "auction_volume" not in frame.columns
        result = _run_auction(_engine(), "auction_fast_grab", frame)
        assert result.total == 0, f"probe {status.value} 下应空池"
        assert result.rows == []


def test_alpha_branch_exclusive():
    """真列分支与派生分支互斥: 同帧绝不混用, 阈值各自生效。"""
    engine = _engine()
    # 真列 fixture → 只走真列阈值 (gap 1.6% 入选, 1.0% 落选, 量比 0.5 落选)
    real_fixture = pl.DataFrame({
        "symbol": ["R1", "R2", "R3"],
        "open_gap": [0.016, 0.010, 0.025],
        "auction_volume_ratio": [1.2, 1.2, 0.5],
        "auction_amount": [2_000_000.0, 2_000_000.0, 2_000_000.0],
    })
    real_hits = {r["symbol"] for r in _run_auction(engine, "auction_alpha", real_fixture).rows}
    assert real_hits == {"R1"}

    # 派生 fixture → 只走派生阈值 (gap 2.5% + 量比 1.5 + 金额 2M 入选)
    derived_fixture = pl.DataFrame({
        "symbol": ["D1", "D2", "D3"],
        "open_gap": [0.025, 0.015, 0.025],
        "vol_ratio_5d": [1.5, 1.5, 1.0],
        "amount": [2_000_000.0, 2_000_000.0, 2_000_000.0],
    })
    derived_hits = {r["symbol"] for r in _run_auction(engine, "auction_alpha", derived_fixture).rows}
    assert derived_hits == {"D1"}

    # 互斥: 无任何符号同时由两分支输出
    assert real_hits.isdisjoint(derived_hits)


def test_alpha_scoring_renormalize():
    """scoring 超集权重和=1.0; 缺真列 fixture 跑 run 不崩溃, score 非负。"""
    from app.strategy.builtin import auction_alpha
    assert sum(auction_alpha.META["scoring"].values()) == pytest.approx(1.0)

    engine = _engine()
    derived_fixture = pl.DataFrame({
        "symbol": ["D1", "D2"],
        "open_gap": [0.025, 0.015],
        "vol_ratio_5d": [1.5, 1.5],
        "amount": [2_000_000.0, 2_000_000.0],
    })
    result = _run_auction(engine, "auction_alpha", derived_fixture)
    assert result.total == 1
    assert all(v >= 0 for v in result.scores.values())


def test_golden_230_window():
    """META 诚实归类 post_close (id 无竞价前缀, 描述尾盘/隔夜) + filter 带 + 收阳 + W-5 grep 门禁。"""
    from app.strategy.builtin import golden_230
    meta = golden_230.META
    assert meta["time_window"] == "post_close"
    assert meta["evaluation_time"] == "15:00"
    assert meta["minute_confirm_required"] is False
    assert meta["id"] == "golden_230"
    assert not meta["id"].startswith("auction_")
    assert "尾盘" in meta["description"]
    assert "隔夜" in meta["description"]
    assert "非竞价窗口" in meta["description"]

    engine = _engine()
    fixture = pl.DataFrame({
        "symbol": ["G1", "G2", "G3", "G4"],
        "open": [10.0, 10.0, 10.0, 10.0],
        "close": [10.4, 10.5, 10.3, 9.6],   # G3 收阳; G4 阴线 (close < open)
        "change_pct": [0.04, 0.055, 0.03, 0.04],
    })
    result = _run_auction(engine, "golden_230", fixture)
    hits = {r["symbol"] for r in result.rows}
    assert hits == {"G1", "G3"}   # 3%–5% + 收阳
    assert "G2" not in hits       # 5.5% > 5% 落选
    assert "G4" not in hits       # 阴线落选

    # W-5 grep 门禁: 文件全文无 auction_ 列引用 (label-drift 回归锁)
    src = (_BUILTIN_DIR / "golden_230.py").read_text(encoding="utf-8")
    assert "auction_" not in src


def test_golden_230_minute_confirm_optional(tmp_path):
    """分钟数据缺席 → 日线核心池仍产出; 有弱尾盘 bar → 池收窄 (可选增强, A3)。"""
    daily = pl.DataFrame({
        "symbol": ["G1", "G2"],
        "open": [10.0, 10.0],
        "close": [10.4, 10.4],
        "change_pct": [0.04, 0.04],
    })
    # 1) 分钟数据缺席 (空帧) → 跳过确认, 日线池保留
    r1 = _run_auction(_engine(minute_loader=lambda symbols, d: pl.DataFrame()), "golden_230", daily)
    assert r1.total == 2

    # 2) 分钟帧含 14:30–15:00 弱尾盘 → 池收窄 (G2 尾盘弱 9.9 < 10.0 → 剔除)
    minute_bars = pl.DataFrame({
        "symbol": ["G1", "G1", "G2", "G2"],
        "datetime": [
            datetime(2026, 8, 4, 14, 30), datetime(2026, 8, 4, 15, 0),
            datetime(2026, 8, 4, 14, 30), datetime(2026, 8, 4, 15, 0),
        ],
        "open": [10.0, 10.0, 10.0, 10.0],
        "high": [10.0, 10.0, 10.0, 10.0],
        "low": [10.0, 10.0, 10.0, 10.0],
        "close": [10.3, 10.1, 10.3, 9.9],  # G1 尾盘不弱 (10.1>=10.0); G2 弱 (9.9<10.0)
        "volume": [100] * 4,
        "amount": [1000.0] * 4,
    })

    def loader(symbols, trade_date):
        return minute_bars.filter(pl.col("symbol").is_in(symbols))

    r2 = _run_auction(_engine(minute_loader=loader), "golden_230", daily)
    assert {r["symbol"] for r in r2.rows} == {"G1"}


def test_preopen_no_eod_cols():
    """B-1 grep 门禁: pre_open filter 禁 EOD 列 (change_pct/vol_ratio_5d/amount/close)。"""
    fast_grab_src = (_BUILTIN_DIR / "auction_fast_grab.py").read_text(encoding="utf-8")
    alpha_src = (_BUILTIN_DIR / "auction_alpha.py").read_text(encoding="utf-8")

    def _filter_body(src: str) -> str:
        return src[src.index("def filter"):]

    fg_body = _filter_body(fast_grab_src)
    for col in ("change_pct", "vol_ratio_5d", "amount", "close"):
        assert not re.search(rf"\b{re.escape(col)}\b", fg_body), \
            f"auction_fast_grab filter 禁引用 {col}"

    alpha_body = _filter_body(alpha_src)
    for col in ("change_pct", "close"):
        assert not re.search(rf"\b{re.escape(col)}\b", alpha_body), \
            f"auction_alpha filter 禁引用 {col}"
    # REQUIREMENTS 授权例外: 派生分支合法引用 vol_ratio_5d/amount
    assert re.search(r"\bvol_ratio_5d\b", alpha_body)
    assert re.search(r"\bamount\b", alpha_body)


def _fake_repo(tmp_path):
    """最小 repo 桩: 仅提供 strategies 端点用到的 store.data_dir。"""
    from types import SimpleNamespace
    return SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))


def _screener_client(tmp_path):
    """最小 FastAPI + screener.router + 真实 builtin 引擎, 无网络无真实数据湖。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import screener as screener_api

    app = FastAPI()
    app.include_router(screener_api.router)
    app.state.repo = _fake_repo(tmp_path)
    app.state.strategy_engine = _engine()
    return TestClient(app)


def test_no_third_registry(tmp_path):
    """P1 三 id 仅 builtin 自动发现 + PRESET 零碰撞 + strategies API 恰好一次。"""
    engine = _engine()
    metas = {m["id"]: m for m in engine.list_strategies()}
    for sid in _P1_IDS:
        assert sid in metas, f"{sid} 必须由 builtin 自动发现"
        assert metas[sid]["source"] == "builtin"
        assert metas[sid]["time_window"] in ("pre_open", "post_close")

    from app.services.screener import PRESET_STRATEGIES
    for sid in _P1_IDS:
        assert sid not in PRESET_STRATEGIES

    client = _screener_client(tmp_path)
    resp = client.get("/api/screener/strategies?asset_type=stock")
    assert resp.status_code == 200
    presets = resp.json()["presets"]
    for sid in _P1_IDS:
        entries = [p for p in presets if p["id"] == sid]
        assert len(entries) == 1, f"{sid} 应恰好出现一次, 实际 {len(entries)}"
        assert entries[0]["source"] == "builtin"
    p1_files = {f"{sid}.py" for sid in _P1_IDS}
    for err in resp.json().get("load_errors", []):
        assert err.get("file") not in p1_files
