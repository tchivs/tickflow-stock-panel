"""POOL-06 — 盘后 EOD 股池持久化 job (22-02 Task 1)。

- ``_pool_eod_persist`` 经 service 级共享核心 ``ScreenerService.run_all_with_hits``
  跑当日全部策略, 先 ``strategy_cache.write_cache`` 刷新最新指针, 再
  ``pool_snapshot.persist_point_snapshot`` 落冻结式点快照 (POOL-04 铁律:
  只落当次 results, 绝不落 today_ever_rows union)。
- 无数据日 / 无 app state → 诚实 skip, 不写任何文件。
- 注册形锁死 (grep 门禁): ``_POOL_EOD_JOB_ID`` + ``_run_tracked`` 单飞包裹 +
  ``CronTrigger(day_of_week="mon-fri")``。

fixture 复用 test_factor_hits._FakeRepo/_write_canned_strategy 形 (本文件内自建,
不 import 其他测试模块)。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl


def _write_canned_strategy(d: Path, sid: str, name: str, min_change: float) -> None:
    """写入一个自包含的 canned builtin 策略文件 (无外部依赖)。"""
    (d / f"{sid}.py").write_text(
        f'''"""canned {sid} for pool_eod_persist regression (hermetic)."""
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

    as_of = date(2026, 8, 4)
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


def test_pool_eod_persist_writes_snapshot_and_cache(tmp_path, monkeypatch):
    """POOL-06: EOD job 落冻结快照 (point, 无 union 键) + 刷新 strategy_cache 指针。"""
    import json

    from app.jobs import daily_pipeline

    app_state = _make_app_state(tmp_path, latest=date(2026, 8, 4))
    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)

    result = daily_pipeline._pool_eod_persist()

    assert result == {"as_of": "2026-08-04", "strategies": 2}

    # 冻结式点快照: screener_results/date={as_of}/part.json
    part = tmp_path / "screener_results" / "date=2026-08-04" / "part.json"
    assert part.exists(), "EOD job 应持久化点快照"
    snap = json.loads(part.read_text(encoding="utf-8"))
    assert snap["snapshot_type"] == "point"
    assert snap["as_of"] == "2026-08-04"
    assert snap["strategy_version"]  # 策略版本指纹非空
    assert snap["computed_at"]  # 计算时刻 ISO 秒
    assert "results" in snap
    # HIST-02 写侧 provenance: EOD job 缺省路径落快照 origin == "eod" (盘后归档)
    assert snap["snapshot_origin"] == "eod"
    # POOL-04 铁律: 快照绝不落 today_ever_rows union
    assert "today_ever_rows" not in snap
    assert "today_ever_matched" not in snap

    # 最新指针刷新: strategy_cache.json 的 as_of 指向最新交易日
    cache_path = tmp_path / "user_data" / "strategy_cache.json"
    assert cache_path.exists(), "EOD job 应刷新 strategy_cache 最新指针"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache["as_of"] == "2026-08-04"


def test_pool_eod_persist_skips_no_data_date(tmp_path, monkeypatch):
    """无数据日: latest_date() 返回 None → 诚实 skip, 不写任何文件。"""
    from app.jobs import daily_pipeline

    app_state = _make_app_state(tmp_path, latest=None)
    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)

    result = daily_pipeline._pool_eod_persist()

    assert result == {"as_of": None, "skipped": "no data date"}
    screener_root = tmp_path / "screener_results"
    assert not screener_root.exists() or not any(screener_root.iterdir()), \
        "无数据日不得写任何快照文件"
    assert not (tmp_path / "user_data" / "strategy_cache.json").exists()


def test_pool_eod_persist_skips_no_app_state(tmp_path, monkeypatch):
    """无 app state: 诚实 skip (调度器早期启动保护)。"""
    from app.jobs import daily_pipeline

    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: None)

    assert daily_pipeline._pool_eod_persist() == {"as_of": None, "skipped": "no app state"}


def test_pool_eod_job_registered_in_scheduler():
    """注册形锁死 (grep 门禁): 常量 + _run_tracked 单飞 + mon-fri cron (不启动真调度器)。"""
    src = Path(__file__).resolve().parents[1] / "app" / "jobs" / "daily_pipeline.py"
    text = src.read_text(encoding="utf-8")

    assert '_POOL_EOD_JOB_ID = "pool_eod_persist"' in text
    assert "_POOL_EOD_OFFSET_MIN" in text
    assert "id=_POOL_EOD_JOB_ID" in text
    assert "_run_tracked(_pool_eod_persist" in text
    assert 'CronTrigger(day_of_week="mon-fri"' in text
    assert 'timezone="Asia/Shanghai"' in text
