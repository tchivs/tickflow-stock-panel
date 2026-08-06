"""PM-01/02/03 — 盘前预览 job + 独立存储 + open_gap 补算 + 只读 API + guest 守卫。

Task 1 (tracer): 09:26 盘前预览垂直切片 —
- 注册形锁死 (grep 门禁): _PREMARKET_JOB_ID 常量 + _run_tracked 单飞 + mon-fri cron
  (W-2 修订: 注册用常量, 断言断常量赋值与 tokens, 不断字面 "hour=9")。
- 存储隔离: 预览只落 premarket_results/date={T}/part.json; strategy_cache.json 与
  screener_results/date=* 在 job 运行后不被改动 (PM-01 验收 3)。
- 诚实 skip: 无数据日 / 无 app state → 不写任何文件。
- 存储原子/校验: _DATE_RE 防路径穿越 (ValueError / None); round-trip; ISO desc。
- probe 三态 (D4): not_configured/fail_closed → degraded:true + probe.status 透传;
  available → degraded:false; 空 results → available:false。

Task 2: compute_enriched_today 补算 open_gap (与 Pass 4 单一公式, D2)。

Task 3: GET /api/pool/premarket 只读端点 (空态 200 + _project_hub 投影 + guest 掩码)
+ POOL-03 AST 守卫。

fixture 复用 test_pool_eod_job._FakeRepo/_make_app_state 形 (本文件内自建, 不跨模块
import 其他测试模块); 生产 import 放测试函数内 (hermetic)。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

FIXED_DATE = date(2026, 8, 6)


def _write_canned_strategy(d: Path, sid: str, name: str, min_change: float) -> None:
    """写入一个自包含的 canned builtin 策略文件 (无外部依赖)。"""
    (d / f"{sid}.py").write_text(
        f'''"""canned {sid} for premarket_pool regression (hermetic)."""
import polars as pl

META = {{
    "id": "{sid}",
    "name": "{name}",
    "description": "canned",
    "tags": [],
    "params": [],
    "scoring": {{}},
    "order_by": "change_pct",
    "descending": True,
    "limit": 100,
}}

BASIC_FILTER = {{"enabled": False}}


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("change_pct") > {min_change}
''',
        encoding="utf-8",
    )


class _FakeRepo:
    """最小 repo 桩 (与 test_factor_hits._FakeRepo 同型, 追加 enriched_latest_date)。"""

    def __init__(self, data_dir, enriched, latest, instruments=None):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._enriched = enriched
        self._latest = latest
        self._instruments = instruments if instruments is not None else pl.DataFrame()

    def get_enriched_latest_asset(self, asset_type):
        return self._enriched, self._latest

    def get_instruments_asset(self, asset_type):
        return self._instruments

    def get_enriched_history(self, target_date, lookback_days):
        return None

    def enriched_latest_date(self):
        return self._latest


def _make_app_state(tmp_path: Path, latest) -> SimpleNamespace:
    """构造 fake app_state: repo (enriched + instruments) + strategy_engine。

    change_pct: 000001=5% (双策略命中), 600000=3% (仅 strat_a),
    000002=1.2% / 300001=0.5% (不被任一策略命中)。
    """
    from app.strategy.engine import StrategyEngine

    strat_dir = tmp_path / "strategies"
    strat_dir.mkdir()
    _write_canned_strategy(strat_dir, "strat_a", "策略Alpha", 0.02)
    _write_canned_strategy(strat_dir, "strat_b", "策略Beta", 0.04)

    as_of = latest or FIXED_DATE
    enriched = pl.DataFrame(
        {
            "symbol": ["000001", "600000", "000002", "300001"],
            "name": ["平安银行", "浦发银行", "万科A", "创业板票"],
            "date": [as_of] * 4,
            "close": [10.0, 11.0, 12.0, 13.0],
            "prev_close": [9.5, 10.6, 11.8, 12.9],
            "change_pct": [0.05, 0.03, 0.012, 0.005],
            "amount": [5e8, 6e8, 7e8, 8e8],
        }
    )
    instruments = pl.DataFrame(
        {
            "symbol": ["000001", "600000", "000002", "300001"],
            "name": ["平安银行", "浦发银行", "万科A", "创业板票"],
        }
    )

    engine = StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[strat_dir],
    )
    repo = _FakeRepo(tmp_path, enriched, latest, instruments)
    return SimpleNamespace(repo=repo, strategy_engine=engine)


def _fake_verdict(status: str, source: str | None = None) -> dict:
    """构造 AuctionProbeVerdict.to_dict 同形 dict (hermetic, 不 import 生产探测)。"""
    return {
        "status": status,
        "source": source,
        "probed_at": "2026-08-06T09:26:00+00:00",
        "window": "09:15-09:25",
        "fallback": "open_gap",
        "detail": "hermetic verdict",
    }


# ================================================================
# Task 1 — 注册形 grep 门禁
# ================================================================


def test_premarket_job_registered_in_scheduler():
    """注册形锁死 (grep 门禁): 常量 + _run_tracked 单飞 + mon-fri cron + 固定 09:26。"""
    src = Path(__file__).resolve().parents[1] / "app" / "jobs" / "daily_pipeline.py"
    text = src.read_text(encoding="utf-8")

    assert '_PREMARKET_JOB_ID = "premarket_pool_preview"' in text
    assert "_PREMARKET_HOUR, _PREMARKET_MINUTE = 9, 26" in text
    assert "_run_tracked(_premarket_pool_preview" in text
    assert "hour=_PREMARKET_HOUR, minute=_PREMARKET_MINUTE" in text
    assert 'timezone="Asia/Shanghai"' in text
    assert "id=_PREMARKET_JOB_ID" in text


# ================================================================
# Task 1 — 存储隔离 + 诚实 skip
# ================================================================


def test_premarket_preview_never_touches_eod_store(tmp_path, monkeypatch):
    """PM-01 验收 3: 预览只落 premarket_results/date={T}/part.json; EOD 存储不被改动。"""
    from app.jobs import daily_pipeline
    from app.services import premarket_pool

    app_state = _make_app_state(tmp_path, latest=FIXED_DATE)
    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)
    monkeypatch.setattr(daily_pipeline, "cn_today", lambda: FIXED_DATE)
    monkeypatch.setattr(
        premarket_pool, "resolve_auction_probe",
        lambda: SimpleNamespace(to_dict=lambda: _fake_verdict("not_configured")),
    )

    result = daily_pipeline._premarket_pool_preview()

    assert result["as_of"] == "2026-08-06"
    assert result["strategies"] == 2  # strat_a + strat_b
    assert result["degraded"] is True  # probe not_configured

    part = tmp_path / "premarket_results" / f"date={FIXED_DATE}" / "part.json"
    assert part.exists(), "盘前预览应持久化到独立 premarket_results 根"
    payload = __import__("json").loads(part.read_text(encoding="utf-8"))
    assert payload["window"] == "pre_open"
    assert payload["provisional"] is True
    assert payload["degraded"] is True
    assert payload["probe"]["status"] == "not_configured"
    assert payload["available"] is True
    assert "computed_at" in payload
    assert "strategy_version" in payload
    assert "results" in payload
    assert payload["as_of"] == "2026-08-06"

    # EOD 存储不被改动: strategy_cache.json 不被创建; screener_results 不被创建
    assert not (tmp_path / "user_data" / "strategy_cache.json").exists(), \
        "盘前预览绝不写 strategy_cache (single-as_of 指针不被污染)"
    assert not (tmp_path / "screener_results").exists(), \
        "盘前预览绝不写 screener_results (EOD 语义不动)"


def test_premarket_preview_skips_no_data_date(tmp_path, monkeypatch):
    """无数据日: latest_date() 返回 None → 诚实 skip, 不写任何文件。"""
    from app.jobs import daily_pipeline

    app_state = _make_app_state(tmp_path, latest=None)
    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)
    monkeypatch.setattr(daily_pipeline, "cn_today", lambda: FIXED_DATE)

    result = daily_pipeline._premarket_pool_preview()

    assert result == {"as_of": None, "skipped": "no data date"}
    premarket_root = tmp_path / "premarket_results"
    assert not premarket_root.exists() or not any(premarket_root.iterdir()), \
        "无数据日不得写任何盘前预览文件"
    assert not (tmp_path / "user_data" / "strategy_cache.json").exists()


def test_premarket_preview_skips_no_app_state(tmp_path, monkeypatch):
    """无 app state: 诚实 skip (调度器早期启动保护)。"""
    from app.jobs import daily_pipeline

    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: None)

    assert daily_pipeline._premarket_pool_preview() == {"as_of": None, "skipped": "no app state"}


# ================================================================
# Task 1 — 存储原子/校验 + round-trip + list
# ================================================================


def test_premarket_snapshot_storage_roundtrip_and_list(tmp_path):
    """persist → load 同 payload; list ISO desc; 非法 as_of → ValueError / None (防路径穿越)。"""
    import pytest

    from app.services.premarket_snapshot import (
        list_premarket_dates,
        load_premarket_snapshot,
        persist_premarket_snapshot,
    )

    payload = {
        "as_of": "2026-08-06",
        "window": "pre_open",
        "provisional": True,
        "degraded": False,
        "probe": _fake_verdict("available"),
        "results": {"strat_a": {"total": 1, "as_of": "2026-08-06", "rows": []}},
    }
    path = persist_premarket_snapshot(tmp_path, "2026-08-06", payload)
    assert path == tmp_path / "premarket_results" / "date=2026-08-06" / "part.json"
    assert path.exists()
    # 无 .tmp 残留 (原子写)
    assert not path.with_name("part.json.tmp").exists()

    loaded = load_premarket_snapshot(tmp_path, "2026-08-06")
    assert loaded == payload

    # 第二日 → list 应 ISO desc (新日期在前)
    persist_premarket_snapshot(tmp_path, "2026-08-05", payload)
    assert list_premarket_dates(tmp_path) == ["2026-08-06", "2026-08-05"]

    # root 不存在 → []
    empty = tmp_path / "no_root"
    empty.mkdir()
    assert list_premarket_dates(empty) == []

    # 非法 as_of → persist ValueError; load None (防路径穿越, T-27-01-02)
    # 注: 存储层 _DATE_RE 只锁格式 (镜像 pool_snapshot), 日历合法性由 API 层
    # date.fromisoformat 二次校验 (get_pool_history 先例); 故 "2026-13-01" 不在非法集。
    for bad in ("../x", "2026-8-6", "2026/08/06", 123, None):
        with pytest.raises(ValueError):
            persist_premarket_snapshot(tmp_path, bad, payload)  # type: ignore[arg-type]
        assert load_premarket_snapshot(tmp_path, bad) is None  # type: ignore[arg-type]


# ================================================================
# Task 1 — probe 三态 (D4)
# ================================================================


def test_build_premarket_preview_probe_three_states(tmp_path, monkeypatch):
    """build_premarket_preview: probe 三态 → degraded 布尔 + probe.status 透传; 空 results → available:false。"""
    from app.services.premarket_pool import build_premarket_preview
    from app.services.screener import ScreenerService

    canonical_results = {
        "strat_a": {
            "total": 1,
            "as_of": "2026-08-06",
            "rows": [{"symbol": "000001", "name": "平安银行", "change_pct": 0.05}],
        }
    }

    def _run_all(self, as_of, strategy_ids=None, engine=None):
        return canonical_results

    monkeypatch.setattr(ScreenerService, "run_all_with_hits", _run_all)
    repo = _FakeRepo(tmp_path, pl.DataFrame(), FIXED_DATE)

    # not_configured → degraded:true + probe.status 透传
    p1 = build_premarket_preview(
        repo, as_of=FIXED_DATE,
        probe_resolver=lambda: SimpleNamespace(to_dict=lambda: _fake_verdict("not_configured")),
    )
    assert p1["available"] is True
    assert p1["degraded"] is True
    assert p1["probe"]["status"] == "not_configured"
    assert p1["window"] == "pre_open"
    assert p1["provisional"] is True
    assert p1["strategy_version"] == "unknown"  # engine=None → 容错指纹

    # fail_closed → degraded:true
    p2 = build_premarket_preview(
        repo, as_of=FIXED_DATE,
        probe_resolver=lambda: SimpleNamespace(to_dict=lambda: _fake_verdict("fail_closed", "src")),
    )
    assert p2["available"] is True
    assert p2["degraded"] is True
    assert p2["probe"]["status"] == "fail_closed"
    assert p2["probe"]["source"] == "src"

    # available → degraded:false
    p3 = build_premarket_preview(
        repo, as_of=FIXED_DATE,
        probe_resolver=lambda: SimpleNamespace(to_dict=lambda: _fake_verdict("available", "src")),
    )
    assert p3["available"] is True
    assert p3["degraded"] is False
    assert p3["probe"]["status"] == "available"

    # 空 results → available:false + degraded:true + results == {} (诚实空态, 不写文件)
    monkeypatch.setattr(ScreenerService, "run_all_with_hits", lambda self, as_of, strategy_ids=None, engine=None: {})
    p4 = build_premarket_preview(
        repo, as_of=FIXED_DATE,
        probe_resolver=lambda: SimpleNamespace(to_dict=lambda: _fake_verdict("available", "src")),
    )
    assert p4["available"] is False
    assert p4["degraded"] is True
    assert p4["window"] == "pre_open"
    assert p4["probe"]["status"] == "available"
    assert p4["results"] == {}


# ================================================================
# Task 2 — compute_enriched_today 补算 open_gap (PM-02, 单一实现零漂移)
# ================================================================

# live_agg 递推状态/窗口聚合占位值 (本组测试只断言 open_gap; 其余列值不影响结果)。
_LIVE_AGG_STATIC = {
    "ema5": 1.0, "ema10": 1.0, "ema20": 1.0, "ema30": 1.0, "ema60": 1.0,
    "_ema12": 1.0, "_ema26": 1.0, "macd_dea": 0.0,
    "_ma5_partial_sum": 0.0, "_ma10_partial_sum": 0.0,
    "_ma20_partial_sum": 0.0, "_ma30_partial_sum": 0.0, "_ma60_partial_sum": 0.0,
    "_boll_partial_sum": 0.0, "_boll_partial_sq_sum": 0.0,
    "_kdj_8d_low": 0.0, "_kdj_8d_high": 1.0, "kdj_k": 50.0, "kdj_d": 50.0,
    "atr_14": 0.1,
    "_rsi_avg_gain_6": 0.0, "_rsi_avg_loss_6": 0.0,
    "_rsi_avg_gain_14": 0.0, "_rsi_avg_loss_14": 0.0,
    "_rsi_avg_gain_24": 0.0, "_rsi_avg_loss_24": 0.0,
    "_vol_ma5_partial_sum": 0.0, "_vol_ma10_partial_sum": 0.0,
    "_vol_ma5_prev_sum": 1000.0,  # 非 0, 避免 vol_ratio_5d 除零
    "_high_59d": 0.0, "_low_59d": 0.0,
    "_close_5d_ago": 1.0, "_close_10d_ago": 1.0,
    "_close_20d_ago": 1.0, "_close_30d_ago": 1.0, "_close_60d_ago": 1.0,
    "_vol_19d_pct_sum": 0.0, "_vol_19d_pct_sq_sum": 0.0,
}


def _premarket_today_frames(symbols, opens, prev_closes, adj_factors, extra_today=None):
    """构造 compute_enriched_today 的最小 live_agg + today_ohlcv (本组测试只断言 open_gap)。"""
    live_agg = pl.DataFrame(
        [
            {"symbol": sym, "prev_close": pc, "_adj_factor": af, **_LIVE_AGG_STATIC}
            for sym, pc, af in zip(symbols, prev_closes, adj_factors)
        ]
    )
    ohlcv = {
        "symbol": symbols,
        "date": [FIXED_DATE] * len(symbols),
        "open": opens,
        "high": opens,
        "low": [0.0] * len(symbols),
        "close": opens,
        "volume": [1000000.0] * len(symbols),
        "amount": [1e8] * len(symbols),
    }
    if extra_today:
        ohlcv.update(extra_today)
    return live_agg, pl.DataFrame(ohlcv)


def test_compute_enriched_today_open_gap_normal_day():
    """正常日: open_gap == open/prev_close − 1 逐行数值断言; prev_close<=0 → None (guard)。"""
    from app.indicators.pipeline import compute_enriched_today

    live_agg, today_ohlcv = _premarket_today_frames(
        ["000001", "600000", "000002"],
        [10.0, 11.0, 12.0],
        [9.5, 11.0, 0.0],  # 第三行 prev_close<=0 → guard → None
        [1.0, 1.0, 1.0],
    )
    out = compute_enriched_today(
        live_agg, pl.DataFrame(), today_ohlcv, instruments=None, elapsed_minutes=240.0
    )

    assert "open_gap" in out.columns
    gaps = out["open_gap"].to_list()
    assert gaps[0] == pytest.approx(10.0 / 9.5 - 1)
    assert gaps[1] == pytest.approx(11.0 / 11.0 - 1)
    assert gaps[2] is None


def test_compute_enriched_today_open_gap_exdiv_caliber():
    """除权日: 采用对齐后 prev_close 口径 (open/prev_close 均乘 _adj_factor), 与 EOD Pass 4 一致。

    _adj_factor=0.9, API 原始 prev_close=10.0 → 对齐后 prev_close=9.0;
    open 原始 9.6 → 对齐后 8.64 → open_gap = 8.64/9.0 − 1 == −0.04。
    """
    from app.indicators.pipeline import compute_enriched_today

    live_agg, today_ohlcv = _premarket_today_frames(["000001"], [9.6], [10.0], [0.9])
    out = compute_enriched_today(
        live_agg, pl.DataFrame(), today_ohlcv, instruments=None, elapsed_minutes=240.0
    )

    gap = out["open_gap"].to_list()[0]
    # 对齐后口径: (9.6×0.9) / (10.0×0.9) − 1 == 8.64/9.0 − 1 == −0.04
    assert gap == pytest.approx((9.6 * 0.9) / (10.0 * 0.9) - 1)
    assert gap == pytest.approx(8.64 / 9.0 - 1)
    assert gap == pytest.approx(-0.04)


def test_compute_enriched_today_open_gap_idempotent():
    """输入帧已含 open_gap 列 → 补算不覆盖 (guard 幂等)。"""
    from app.indicators.pipeline import compute_enriched_today

    live_agg, today_ohlcv = _premarket_today_frames(
        ["000001"], [10.0], [9.5], [1.0], extra_today={"open_gap": 0.123}
    )
    out = compute_enriched_today(
        live_agg, pl.DataFrame(), today_ohlcv, instruments=None, elapsed_minutes=240.0
    )

    assert out["open_gap"].to_list()[0] == pytest.approx(0.123)  # 源已提供列 → 不覆盖
