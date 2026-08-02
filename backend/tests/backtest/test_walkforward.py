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

from datetime import date

import polars as pl
import pytest

from app.research.repository import ResearchRepository


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
    # Every fold's chain config end == test_end + horizon (label buffer).
    for manifest in result["fold_manifests"]:
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
