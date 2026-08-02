"""Walk-forward validation (WFWD-01) — Wave 0 RED scaffold.

Contract cases locked here (turned green by 13-01/13-03/13-05):
- geometry: 3 rolling folds with an explicit gap, pairwise-disjoint tiled test
  segments, a reserved final 40-day OOS pinned BEFORE any search reuse, and
  fold boundaries snapped to the measured calendar (a 14-trading-day "Feb"
  hole must not shorten a "20-day" test segment)
- per-fold PIT: every fold resolves its own membership window and records a
  64-hex ``membership_fingerprint`` that CHANGES when membership changes
- per-fold SignalChainConfig: ``end == test_end + horizon`` (label buffer)
- exactly-once OOS: a second evaluation raises ``ValueError``
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from types import SimpleNamespace

import polars as pl
import pytest

from app.research.repository import ResearchRepository


class _HoldingDaysService:
    """Backtest double exposing only ``avg_holding_days`` (min-direction gate case)."""

    def run(self, config, progress_cb=None, cancel_event=None):  # type: ignore[no-untyped-def]
        del config, progress_cb, cancel_event
        return SimpleNamespace(stats={"avg_holding_days": 1.0}, error=None)


class _FakeFold:
    """Duck-typed WalkForwardFold surface for repository round-trip tests."""

    def __init__(self, fold_index: int, is_oos: bool) -> None:
        self.fold_index = fold_index
        self.is_oos = is_oos
        self.train_start = date(2025, 7, 29)
        self.train_end = date(2026, 1, 22)
        self.gap_start = date(2026, 1, 23)
        self.gap_end = date(2026, 2, 27)
        self.test_start = date(2026, 3, 2)
        self.test_end = date(2026, 3, 27)


class _FakePlan:
    """Duck-typed WalkForwardPlan surface for repository round-trip tests."""

    def __init__(self) -> None:
        self.plan_id = "wf-plan-repo"
        self.universe = "cn-a-share"
        self.asset_type = "stock"
        self.start = date(2025, 7, 29)
        self.end = date(2026, 7, 30)
        self.train_size = 120
        self.gap_size = 20
        self.test_size = 20
        self.oos_size = 40
        self.horizon = 5
        self.trading_dates = [date(2025, 7, 29)]
        self.folds = (_FakeFold(0, False), _FakeFold(1, False), _FakeFold(2, False))
        self.oos_fold = _FakeFold(0, True)


# ---------------------------------------------------------------------------
# WFWD-01: geometry (pure, no repository) — RED until 13-01 lands build_plan
# ---------------------------------------------------------------------------


def test_build_plan_derives_three_folds_with_gap_and_reserved_oos(
    measured_calendar: list[date],
) -> None:
    """build_plan: 3 folds + final OOS; tests disjoint, tiled, snapped."""
    from app.backtest.walkforward import build_plan

    plan = build_plan(
        plan_id="wf-geometry",
        universe="cn-a-share",
        asset_type="stock",
        dates=measured_calendar,
        train_size=120,
        gap_size=20,
        test_size=20,
        oos_size=40,
        horizon=5,
    )
    assert len(plan.folds) == 3
    assert all(not fold.is_oos for fold in plan.folds)
    assert plan.oos_fold.is_oos is True
    # Exactly-20-date test segments: calendar snapping (Pitfall 1).
    for fold in plan.folds:
        test_dates = [
            day for day in measured_calendar if fold.test_start <= day <= fold.test_end
        ]
        assert len(test_dates) == 20
    # Pairwise disjoint + contiguous tiling: fold_{i+1}.test_start is the next
    # measured date after fold_i.test_end.
    for left, right in zip(plan.folds, plan.folds[1:], strict=False):
        assert left.test_end < right.test_start
        assert set(
            day for day in measured_calendar if left.test_start <= day <= left.test_end
        ).isdisjoint(
            day for day in measured_calendar if right.test_start <= day <= right.test_end
        )
    # OOS is the final 40 measured dates and never touched by the folds.
    oos_dates = [day for day in measured_calendar if day >= plan.oos_fold.test_start]
    assert len(oos_dates) == 40
    assert plan.folds[-1].test_end < plan.oos_fold.test_start
    assert plan.oos_fold.test_end == measured_calendar[-1]


def test_build_plan_fails_closed_on_short_history(measured_calendar: list[date]) -> None:
    """Below the walk-forward horizon the geometry fails closed, never 1 fold."""
    from app.backtest.walkforward import build_plan

    short = measured_calendar[:180]
    with pytest.raises(ValueError, match="insufficient history"):
        build_plan(
            plan_id="wf-short",
            universe="cn-a-share",
            asset_type="stock",
            dates=short,
            train_size=120,
            gap_size=20,
            test_size=20,
            oos_size=40,
            horizon=5,
        )


def test_calendar_snapping_respects_feb_2026_cny_hole(measured_calendar: list[date]) -> None:
    """A 14-trading-day month must not shorten a '20-day' test segment."""
    from app.backtest.walkforward import build_plan

    plan = build_plan(
        plan_id="wf-snap",
        universe="cn-a-share",
        asset_type="stock",
        dates=measured_calendar,
        train_size=120,
        gap_size=20,
        test_size=20,
        oos_size=40,
        horizon=5,
    )
    for fold in plan.folds:
        segment = [d for d in measured_calendar if fold.test_start <= d <= fold.test_end]
        assert len(segment) == 20, f"fold {fold.fold_index} test segment is not 20 dates"
    assert len([d for d in measured_calendar if date(2026, 2, 1) <= d <= date(2026, 2, 28)]) == 6


# ---------------------------------------------------------------------------
# WFWD-01: exactly-once OOS via repository (green once repo methods land)
# ---------------------------------------------------------------------------


def test_wf_plan_pinned_idempotently_and_fold_recorded_exactly_once(
    research_repository: ResearchRepository,
) -> None:
    """create_wf_plan pins OOS idempotently; record_wf_fold OOS raises on re-run."""
    plan = _FakePlan()
    pinned = research_repository.create_wf_plan(plan)
    assert pinned["id"] == plan.plan_id
    assert pinned["oos_pinned_at"]
    again = research_repository.create_wf_plan(plan)
    assert again["id"] == plan.plan_id  # idempotent re-create

    oos_fold = plan.oos_fold
    research_repository.record_wf_fold(
        plan_id=plan.plan_id,
        fold_index=oos_fold.fold_index,
        is_oos=True,
        strategy_id="fixture_strategy",
        params_sha256="a" * 64,
        train_start=oos_fold.train_start,
        train_end=oos_fold.train_end,
        test_start=oos_fold.test_start,
        test_end=oos_fold.test_end,
        membership_fingerprint="b" * 64,
        chain_config={"end": oos_fold.test_end.isoformat()},
        stats={"effective_days": 35},
    )
    with pytest.raises(ValueError, match="OOS segment already evaluated"):
        research_repository.record_wf_fold(
            plan_id=plan.plan_id,
            fold_index=oos_fold.fold_index,
            is_oos=True,
            strategy_id="fixture_strategy",
            params_sha256="a" * 64,
            train_start=oos_fold.train_start,
            train_end=oos_fold.train_end,
            test_start=oos_fold.test_start,
            test_end=oos_fold.test_end,
            membership_fingerprint="c" * 64,
            chain_config={"end": oos_fold.test_end.isoformat()},
            stats={"effective_days": 35},
        )


def test_fold_manifests_are_append_only_and_listable(
    research_repository: ResearchRepository,
) -> None:
    """Search-fold manifests round-trip; list filters and caps at limit."""
    plan = _FakePlan()
    research_repository.create_wf_plan(plan)
    for fold in plan.folds:
        research_repository.record_wf_fold(
            plan_id=plan.plan_id,
            fold_index=fold.fold_index,
            is_oos=False,
            strategy_id="fixture_strategy",
            params_sha256="a" * 64,
            train_start=fold.train_start,
            train_end=fold.train_end,
            test_start=fold.test_start,
            test_end=fold.test_end,
            membership_fingerprint="d" * 64,
            chain_config={"end": fold.test_end.isoformat()},
            stats={"effective_days": 15},
        )
    folds = research_repository.list_wf_folds(plan_id=plan.plan_id, is_oos=False)
    assert len(folds) == 3
    assert all(fold["is_oos"] == 0 for fold in folds)
    with pytest.raises(ValueError, match="limit"):
        research_repository.list_wf_folds(limit=0)


# ---------------------------------------------------------------------------
# WFWD-01: run_walk_forward integration spine — RED until 13-01
# ---------------------------------------------------------------------------


def test_run_walk_forward_pins_plan_and_records_fingerprints(
    research_repository: ResearchRepository,
    wf_fixture_plan,
    stub_resolver,
    stub_chain,
    stub_backtest_service,
) -> None:
    """The full spine: pinned plan → per-fold fingerprint manifests → OOS once."""
    from app.backtest.walkforward import run_walk_forward

    result = run_walk_forward(
        wf_fixture_plan,
        strategy_id="fixture_strategy",
        params={"ma_proximity": 0.02},
        service=stub_backtest_service,
        chain=stub_chain,
        resolver=stub_resolver,
        repo=research_repository,
    )
    assert result["plan_id"] == wf_fixture_plan.plan_id
    assert len(result["fold_manifests"]) == len(wf_fixture_plan.folds) + 1  # 3 + OOS
    oos_manifest = [m for m in result["fold_manifests"] if m["is_oos"] == 1]
    assert len(oos_manifest) == 1
    # Every fold's chain config end == test_end + horizon (label buffer), so
    # labels stay finite through the whole test segment (FACT-06 anti skew).
    for manifest in result["fold_manifests"]:
        test_end = date.fromisoformat(manifest["test_end"])
        expected_end = (test_end + timedelta(days=wf_fixture_plan.horizon)).isoformat()
        assert manifest["chain_config"]["end"] == expected_end
        assert len(manifest["membership_fingerprint"]) == 64
        assert manifest["stats"]["effective_days"] >= 10
    with pytest.raises(ValueError, match="OOS segment already evaluated"):
        run_walk_forward(
            wf_fixture_plan,
            strategy_id="fixture_strategy",
            params={"ma_proximity": 0.02},
            service=stub_backtest_service,
            chain=stub_chain,
            resolver=stub_resolver,
            repo=research_repository,
        )


def test_membership_fingerprint_changes_when_membership_changes(
    research_repository: ResearchRepository,
    wf_fixture_plan,
    fixture_membership: pl.DataFrame,
    stub_backtest_service,
    make_stub_resolver,
    make_stub_chain,
) -> None:
    """Pitfall 5: per-fold fingerprints differ when the resolved window differs."""
    from app.backtest.walkforward import run_walk_forward

    resolver_a = make_stub_resolver(fixture_membership)
    resolver_b = make_stub_resolver(
        fixture_membership.filter(pl.col("symbol") != "000001.SZ")
    )
    result_a = run_walk_forward(
        wf_fixture_plan,
        strategy_id="fixture_strategy",
        params={"p": 1},
        service=stub_backtest_service,
        chain=make_stub_chain(resolver_a),
        resolver=resolver_a,
        repo=research_repository,
    )
    research_repository = type(research_repository)(research_repository.database_path)
    result_b = run_walk_forward(
        wf_fixture_plan,
        strategy_id="fixture_strategy",
        params={"p": 2},  # distinct params_sha256 so fold records do not collide
        service=stub_backtest_service,
        chain=make_stub_chain(resolver_b),
        resolver=resolver_b,
        repo=research_repository,
    )
    assert result_a["fold_manifests"] != result_b["fold_manifests"]
    fp_a = {m["fold_index"]: m["membership_fingerprint"] for m in result_a["fold_manifests"]}
    fp_b = {m["fold_index"]: m["membership_fingerprint"] for m in result_b["fold_manifests"]}
    assert fp_a != fp_b


# ---------------------------------------------------------------------------
# WFWD-02: best_params 验证门 — exactly-once OOS + wf_validated_strategies 裁决
# ---------------------------------------------------------------------------


def _record_search_run(repo: ResearchRepository, plan_id: str, *, search_id: str) -> None:
    """Insert a real wf_search_runs row so the verdict FK (search_run_id) resolves."""
    repo.record_wf_search(
        id=search_id,
        plan_id=plan_id,
        strategy_id="fixture_strategy",
        objective="sharpe",
        direction="max",
        search_space={"param_grid": {"ma_proximity": [0.01, 0.02, 0.03]}, "params_meta": []},
        n_trials=3,
        n_completed=3,
        score_distribution={
            "per_trial": [],
            "per_fold": {},
            "min": 0.5,
            "median": 1.0,
            "max": 1.5,
            "mean": 1.0,
            "std": 0.5,
        },
        best_params={"ma_proximity": 0.02},
        best_score=1.5,
        oos_excluded=1,
    )


def test_evaluate_best_params_oos_exactly_once_and_validation_gate(
    research_repository: ResearchRepository,
    wf_fixture_plan,
    stub_resolver,
    stub_chain,
    stub_backtest_service,
) -> None:
    """OOS 只评估一次; 裁决绑定到 OOS 证据折 (oos_evidence_fold_id UNIQUE)。"""
    from app.backtest.walkforward import evaluate_best_params, run_walk_forward

    # 预热: 先走一遍 walk-forward (不同 params), 钉住 plan 并记录 3 个搜索折 + 该
    # params 键的 OOS 折 — 模拟真实流程: 搜索先用一组探索参数跑折, 再评估 best_params。
    run_walk_forward(
        wf_fixture_plan,
        strategy_id="fixture_strategy",
        params={"ma_proximity": 0.01},
        service=stub_backtest_service,
        chain=stub_chain,
        resolver=stub_resolver,
        repo=research_repository,
    )
    preheat_oos = research_repository.list_wf_folds(plan_id=wf_fixture_plan.plan_id, is_oos=True)
    assert len(preheat_oos) == 1  # 预热 params 键的 OOS 已记录
    _record_search_run(research_repository, wf_fixture_plan.plan_id, search_id="wf-search-run-1")

    # 评估 best_params: 该 params 键的 OOS 首次评估 → 新建 OOS 证据折 + 裁决。
    out = evaluate_best_params(
        wf_fixture_plan,
        strategy_id="fixture_strategy",
        best_params={"ma_proximity": 0.02},
        service=stub_backtest_service,
        chain=stub_chain,
        resolver=stub_resolver,
        repo=research_repository,
        objective="sharpe",
        search_run_id="wf-search-run-1",
        validation_threshold=0.0,
    )
    assert out["params_sha256"] == hashlib.sha256(
        json.dumps(
            {"ma_proximity": 0.02}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    assert out["passed_gate"] is True
    assert out["validation_score"] == 1.0  # stub 服务 sharpe=1.0
    assert out["oos_manifest"]["id"] not in {row["id"] for row in preheat_oos}
    assert out["verdict"]["oos_evidence_fold_id"] == out["oos_manifest"]["id"]

    # 第二次评估同一 (plan, strategy, params) → 恰好一次守卫
    with pytest.raises(ValueError, match="OOS segment already evaluated"):
        evaluate_best_params(
            wf_fixture_plan,
            strategy_id="fixture_strategy",
            best_params={"ma_proximity": 0.02},
            service=stub_backtest_service,
            chain=stub_chain,
            resolver=stub_resolver,
            repo=research_repository,
            objective="sharpe",
            search_run_id="wf-search-run-1",
            validation_threshold=0.0,
        )
    # 同一 OOS 证据折不能再产生第二个裁决 (oos_evidence_fold_id UNIQUE)
    verdicts = research_repository.list_validated_strategies(
        strategy_id="fixture_strategy", plan_id=wf_fixture_plan.plan_id
    )
    assert len(verdicts) == 1
    assert verdicts[0]["oos_evidence_fold_id"] == out["oos_manifest"]["id"]
    assert verdicts[0]["passed_gate"] == 1
    assert verdicts[0]["validation_score"] == 1.0


def test_evaluate_best_params_threshold_gate_min_and_max_direction(
    research_repository: ResearchRepository,
    wf_fixture_plan,
    stub_resolver,
    stub_chain,
    stub_backtest_service,
) -> None:
    """机械门: max 方向 OOS 表现 >= 阈值通过; min 方向 <= 阈值通过。"""
    from app.backtest.walkforward import evaluate_best_params

    out_pass = evaluate_best_params(
        wf_fixture_plan,
        strategy_id="fixture_strategy",
        best_params={"ma_proximity": 0.02},
        service=stub_backtest_service,
        chain=stub_chain,
        resolver=stub_resolver,
        repo=research_repository,
        objective="sharpe",
        search_run_id=None,  # 无搜索运行: 固定参数直接验证
        validation_threshold=0.5,
    )
    assert out_pass["passed_gate"] is True  # 1.0 >= 0.5 (max 方向)
    assert out_pass["params_sha256"] == out_pass["verdict"]["params_sha256"]

    # min 方向: avg_holding_days 越小越好 — OOS 1.0 <= 阈值 0.5? 否 → 失败。
    out_fail = evaluate_best_params(
        wf_fixture_plan,
        strategy_id="fixture_strategy",
        best_params={"ma_proximity": 0.03},
        service=_HoldingDaysService(),
        chain=stub_chain,
        resolver=stub_resolver,
        repo=research_repository,
        objective="avg_holding_days",
        search_run_id=None,
        validation_threshold=0.5,
    )
    assert out_fail["passed_gate"] is False  # 1.0 > 0.5 (min 方向) 失败
    assert out_fail["validation_score"] == 1.0
    # passed_gate=0 行可被 list_validated_strategies(passed_gate=False) 过滤出来
    failed = research_repository.list_validated_strategies(
        strategy_id="fixture_strategy", plan_id=wf_fixture_plan.plan_id, passed_gate=False
    )
    assert [v["strategy_id"] for v in failed] == ["fixture_strategy"]
    assert all(v["params_sha256"] == out_fail["params_sha256"] for v in failed)
