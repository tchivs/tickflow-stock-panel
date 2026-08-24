"""竞价策略族 (STRAT-01/STRAT-03) — 内置竞价策略: 引擎发现 + 受管列消费 + 评分权重 + API 去重。

覆盖:
- 竞价多头/盘前强势量化/早盘之星 三个第一性原理竞价策略 (STRAT-01; CONTEXT #1 — 名称是产品标签,
  因子定义是本项目的第一性原理, 不宣称与任何专有配方一致)
- 过滤器仅消费 Phase 16 受管列 open_gap/change_pct/vol_ratio_5d, 永不从 raw bar 重推 (T-17-01, PITFALL #6)
- 空值 open_gap/change_pct/vol_ratio_5d fail-closed (DATA-03 承继)
- 多因子评分权重和恒为 1.0 (PITFALL #7)
- strategies API 每个竞价策略恰好出现一次 source=builtin, 且不与 PRESET_STRATEGIES 冲突,
  无第三条注册轨道 (STRAT-03, PITFALL #5)
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.strategy.builtin import auction_bullish, auction_early_star, auction_preopen_quant
from app.strategy.engine import StrategyEngine

_AUCTION_IDS = ("auction_bullish", "auction_preopen_quant", "auction_early_star")
_BUILTIN_DIR = Path(__file__).resolve().parents[1] / "app" / "strategy" / "builtin"

def _governed_fixture() -> pl.DataFrame:
    """仅含 Phase 16 受管列 symbol/open_gap/change_pct/vol_ratio_5d 的 fixture。

    - 600001: 双 leg 达标 (gap 5% / change 5% / 量比 3.0)
    - 600002: gap 5% 但 change 1% (竞价多头应拒)
    - 600003: change 5% 但 gap 1% (竞价多头应拒)
    - 600004: 双 leg 均不达标
    - 600005: open_gap 为 null (无前收盘) — 竞价多头/盘前量化应 fail-closed
    - 600006: change_pct 为 null — 竞价多头应 fail-closed
    - 600007: 量比 1.0 (盘前量化应拒)
    - 600008: vol_ratio_5d 为 null — 盘前量化应 fail-closed
    """
    return pl.DataFrame(
        {
            "symbol": [
                "600001", "600002", "600003", "600004",
                "600005", "600006", "600007", "600008",
            ],
            "open_gap": [0.05, 0.05, 0.01, 0.01, None, 0.05, 0.05, 0.05],
            "change_pct": [0.05, 0.01, 0.05, 0.01, 0.05, None, 0.05, 0.05],
            "vol_ratio_5d": [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 1.0, None],
        }
    )


def _engine() -> StrategyEngine:
    return StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[_BUILTIN_DIR],
    )


def _run_auction(engine: StrategyEngine, strategy_id: str, fixture: pl.DataFrame):
    from app.strategy.engine import StrategyDataContext

    ctx = StrategyDataContext(
        asset_type="stock",
        timeframe="1d",
        as_of=date(2026, 8, 4),
        current=fixture,
    )
    return engine.run(
        strategy_id,
        ctx,
        overrides={"basic_filter": {"enabled": False}},
    )


# ================================================================
# Task 1: 竞价多头 (auction_bullish)
# ================================================================


def test_auction_bullish_requires_both_momentum():
    """严格 AND 双动量: gap>=2% 且 change>=2%; null open_gap fail-closed。"""
    df = _governed_fixture()
    hits = set(df.filter(auction_bullish.filter(df, {})).get_column("symbol"))
    assert hits == {"600001", "600007", "600008"}
    # gap 达标但 change < 2%
    assert "600002" not in hits
    # gap < 2% 但 change 达标
    assert "600003" not in hits
    # 无前收盘 (open_gap 为 null) → fail-closed
    assert "600005" not in hits
    # change_pct 为 null → fail-closed
    assert "600006" not in hits


def test_auction_strategies_auto_discovered_by_engine():
    engine = _engine()
    assert engine.has("auction_bullish")
    metas = {m["id"]: m for m in engine.list_strategies()}
    assert "auction_bullish" in metas
    assert metas["auction_bullish"]["source"] == "builtin"


def test_auction_bullish_run_returns_pool_with_governed_columns():
    """端到端: 文件 -> 引擎发现 -> run() -> 池子带 开盘涨幅/涨跌幅 受管列。"""
    engine = _engine()
    result = _run_auction(engine, "auction_bullish", _governed_fixture())
    assert {r["symbol"] for r in result.rows} == {"600001", "600007", "600008"}
    for r in result.rows:
        assert "open_gap" in r
        assert "change_pct" in r


def test_auction_strategy_scoring_weights_sum_to_one():
    """三个竞价策略的多因子评分权重和恒为 1.0 (PITFALL #7)。"""
    for strat in (auction_bullish, auction_preopen_quant, auction_early_star):
        assert sum(strat.META["scoring"].values()) == pytest.approx(1.0)


# ================================================================
# Task 2: 盘前强势量化 (auction_preopen_quant) + 早盘之星 (auction_early_star)
# ================================================================


def test_auction_preopen_strength_requires_gap_and_volume():
    """盘前强度 = open_gap>=3% AND vol_ratio_5d>=1.5; null 量比 fail-closed。"""
    df = _governed_fixture()
    hits = set(df.filter(auction_preopen_quant.filter(df, {})).get_column("symbol"))
    assert hits == {"600001", "600002", "600006"}
    # gap 达标但量比 1.0 < 1.5
    assert "600007" not in hits
    # gap < 3% 但量比达标
    assert "600003" not in hits
    # open_gap 为 null → fail-closed
    assert "600005" not in hits
    # vol_ratio_5d 为 null → fail-closed
    assert "600008" not in hits


def test_auction_early_star_either_leg_qualifies():
    """OR 组合: gap leg 或 change leg 任一达标即入选; 双 leg 均不达标则拒。"""
    df = _governed_fixture()
    hits = set(df.filter(auction_early_star.filter(df, {})).get_column("symbol"))
    assert hits == {
        "600001", "600002", "600003", "600005", "600006", "600007", "600008",
    }
    # 双 leg 均不达标
    assert "600004" not in hits


def test_auction_early_star_concept_corroboration_optional():
    """概念板块佐证: 无 concept_board 列时开启不崩溃不收窄; 有列时只保留非空概念行。"""
    base = _governed_fixture()
    base_hits = set(base.filter(auction_early_star.filter(base, {})).get_column("symbol"))

    # 无 concept_board 列: 开启佐证 → 基础 OR 组合不变
    without_col = base.filter(
        auction_early_star.filter(base, {"use_concept_corroboration": True})
    )
    assert set(without_col.get_column("symbol")) == base_hits

    # 有 concept_board 列: 开启佐证 → 只保留非空概念行
    with_col = base.with_columns(
        pl.Series("concept_board", ["AI", None, "军工", "AI", None, "半导体", "AI", None])
    )
    corrob = with_col.filter(
        auction_early_star.filter(with_col, {"use_concept_corroboration": True})
    )
    assert set(corrob.get_column("symbol")) == {"600001", "600003", "600006", "600007"}

    # 佐证默认关闭 (False) → 不因概念列收窄
    default_off = with_col.filter(auction_early_star.filter(with_col, {}))
    assert set(default_off.get_column("symbol")) == base_hits


def test_auction_strategies_only_use_governed_columns():
    """三个过滤器只在受管列 fixture 上执行 (无 raw bar 重推/rejoin; PITFALL #6)。"""
    df = _governed_fixture()
    assert set(df.columns) == {"symbol", "open_gap", "change_pct", "vol_ratio_5d"}
    for strat in (auction_bullish, auction_preopen_quant, auction_early_star):
        out = df.filter(strat.filter(df, {}))
        assert set(out.columns) == set(df.columns)

    # META id 唯一且与文件 stem 一致 (引擎按 stem 推导 id 的自动发现约定)
    ids = [strat.META["id"] for strat in (auction_bullish, auction_preopen_quant, auction_early_star)]
    assert len(set(ids)) == 3
    for strat, stem in zip(
        (auction_bullish, auction_preopen_quant, auction_early_star),
        ("auction_bullish", "auction_preopen_quant", "auction_early_star"),
    ):
        assert strat.META["id"] == stem


# ================================================================
# Task 3: STRAT-03 regression — builtin-only 发现 + PRESET_STRATEGIES 去重, 无第三条注册轨道
# ================================================================


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


def test_auction_strategies_appear_once_in_strategies_api(tmp_path):
    """strategies API: 每个竞价 id 恰好一次, source=builtin; load_errors 干净。"""
    client = _screener_client(tmp_path)
    resp = client.get("/api/screener/strategies?asset_type=stock")
    assert resp.status_code == 200
    presets = resp.json()["presets"]
    for sid in _AUCTION_IDS:
        entries = [p for p in presets if p["id"] == sid]
        assert len(entries) == 1, f"{sid} 应恰好出现一次, 实际 {len(entries)}"
        assert entries[0]["source"] == "builtin"
    auction_files = {
        "auction_bullish.py",
        "auction_preopen_quant.py",
        "auction_early_star.py",
    }
    for err in resp.json().get("load_errors", []):
        assert err.get("file") not in auction_files


def test_auction_ids_never_collide_with_presets():
    """去重前提: 三个竞价 id 均不在 PRESET_STRATEGIES 键中, 永不会双列。"""
    from app.services.screener import PRESET_STRATEGIES

    for sid in _AUCTION_IDS:
        assert sid not in PRESET_STRATEGIES


def test_no_third_registry_track():
    """无第三条注册轨道: 竞价策略只能经 builtin 目录被 engine 发现。"""
    engine = _engine()
    listed = {m["id"] for m in engine.list_strategies()}
    for sid in _AUCTION_IDS:
        assert sid in listed, f"{sid} 必须由 engine 从 strategy/builtin 自动发现"

    # 除 strategy/builtin/*.py 之外, 不应有任何硬注册出现竞价 id
    engine_src = (_BUILTIN_DIR.parent / "engine.py").read_text(encoding="utf-8")
    init_src = (_BUILTIN_DIR / "__init__.py").read_text(encoding="utf-8")
    for sid in _AUCTION_IDS:
        assert sid not in engine_src
        assert sid not in init_src
