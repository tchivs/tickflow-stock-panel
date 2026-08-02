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


def test_create_wf_plan_raises_on_geometry_divergence(
    research_repository: ResearchRepository,
) -> None:
    """WR-03: 同一 plan_id 以重测日历/不同 geometry 再钉 → ValueError, 不静默保留陈旧预约。"""
    plan = _FakePlan()
    research_repository.create_wf_plan(plan)

    # 同一 plan_id, 但 OOS 尺寸变化 (重测日历 → 几何漂移)。
    drifted = _FakePlan()
    drifted.plan_id = plan.plan_id
    drifted.oos_size = 50
    with pytest.raises(ValueError, match="already pinned with different geometry"):
        research_repository.create_wf_plan(drifted)

    # 日历重测但几何一致 → 幂等返回既有行 (仍是合法重跑)。
    same = _FakePlan()
    row = research_repository.create_wf_plan(same)
    assert row["id"] == plan.plan_id
    assert row["oos_size"] == 40


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
        evaluate_oos=True,  # WR-01: OOS 评估显式开启 (默认关闭)
    )
    assert result["plan_id"] == wf_fixture_plan.plan_id
    assert result["evaluate_oos"] is True
    assert len(result["fold_manifests"]) == len(wf_fixture_plan.folds) + 1  # 3 + OOS
    oos_manifest = [m for m in result["fold_manifests"] if m["is_oos"] == 1]
    assert len(oos_manifest) == 1
    # Every fold's chain config end is the label buffer snapped to `horizon`
    # TRADING days past test_end on the measured calendar (WR-09) — calendar-day
    # buffers shrink across weekends/holidays and silently shorten scorable test
    # days. Fully-covered search folds therefore get effective_days == test_size.
    for manifest in result["fold_manifests"]:
        test_end = date.fromisoformat(manifest["test_end"])
        after = [d for d in wf_fixture_plan.trading_dates if d > test_end]
        if len(after) >= wf_fixture_plan.horizon:
            expected_end = after[wf_fixture_plan.horizon - 1].isoformat()
        else:
            expected_end = (test_end + timedelta(days=wf_fixture_plan.horizon)).isoformat()
        assert manifest["chain_config"]["end"] == expected_end
        assert len(manifest["membership_fingerprint"]) == 64
        assert manifest["stats"]["effective_days"] >= 10
        if manifest["is_oos"] == 0:
            assert manifest["stats"]["effective_days"] == wf_fixture_plan.test_size  # fully covered
    with pytest.raises(ValueError, match="OOS segment already evaluated"):
        run_walk_forward(
            wf_fixture_plan,
            strategy_id="fixture_strategy",
            params={"ma_proximity": 0.02},
            service=stub_backtest_service,
            chain=stub_chain,
            resolver=stub_resolver,
            repo=research_repository,
            evaluate_oos=True,
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

    # 预热: 先走一遍 walk-forward (不同 params), 钉住 plan 并记录 3 个搜索折 —
    # WR-01: 默认 evaluate_oos=False, 搜索/探索绝不写 OOS 槽位 (WFWD-01 exactly-once)。
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
    assert len(preheat_oos) == 0  # 搜索折跑完不写 OOS (WR-01)
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
    # 报告面 (13-05): 验证裁决携带 resolved_asset_ids (来自 13-02 DDL 列
    # resolved_asset_ids_json) — Phase 14 无需重解析即可绑定组合快照。
    # 报告面 (13-05): 验证裁决携带 resolved_asset_ids (来自 13-02 DDL 列
    # resolved_asset_ids_json, 解包为 list) — Phase 14 无需重解析即可绑定组合快照。
    assert isinstance(failed[0]["resolved_asset_ids"], list)
    assert failed[0]["resolved_asset_ids"] == sorted(
        {"000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"}
    )  # WR-07: OOS 折的 PIT 成员符号被解析并持久化
    passed = research_repository.list_validated_strategies(
        strategy_id="fixture_strategy", plan_id=wf_fixture_plan.plan_id, passed_gate=True
    )
    assert [v["id"] for v in passed] == [out_pass["verdict"]["id"]]


# ---------------------------------------------------------------------------
# 13-05: 几何稳健性 + 报告面广度
# ---------------------------------------------------------------------------


def _weekday_range(start: date, end: date) -> list[date]:
    """Conftest 同构的 weekday 日期范围 (测日历重测增长)。"""
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def test_calendar_remeasured_grows_fold_count_and_rolls_oos_forward(
    measured_calendar: list[date],
) -> None:
    """日历重测 (measured at execution): 增长的历史滚动折叠数并把 OOS 前滚。"""
    from app.backtest.walkforward import build_plan

    grown = measured_calendar + _weekday_range(date(2026, 8, 3), date(2026, 8, 28))
    small = build_plan(
        plan_id="wf-grown",
        universe="cn-a-share",
        asset_type="stock",
        dates=measured_calendar,
        train_size=120,
        gap_size=20,
        test_size=20,
        oos_size=40,
        horizon=5,
    )
    large = build_plan(
        plan_id="wf-grown",
        universe="cn-a-share",
        asset_type="stock",
        dates=grown,
        train_size=120,
        gap_size=20,
        test_size=20,
        oos_size=40,
        horizon=5,
    )
    # ~20 个新交易日 ⇒ +1 折; OOS 前滚到新的历史末端。
    assert len(large.folds) == len(small.folds) + 1
    assert large.oos_fold.test_end == grown[-1]
    assert large.oos_fold.test_end > small.oos_fold.test_end


def test_fail_closed_below_two_folds_reports_measured_count(
    measured_calendar: list[date],
) -> None:
    """低于 2 折 (H≈180) 时 fail-closed, 报出实测日数与最小需求。"""
    from app.backtest.walkforward import build_plan

    short = measured_calendar[:180]
    with pytest.raises(ValueError, match="insufficient history") as excinfo:
        build_plan(
            plan_id="wf-short2",
            universe="cn-a-share",
            asset_type="stock",
            dates=short,
            train_size=120,
            gap_size=20,
            test_size=20,
            oos_size=40,
            horizon=5,
        )
    message = str(excinfo.value)
    assert "180 measured trading days" in message
    assert "minimum 221" in message  # WR-08: 真实最小值 = oos+train+gap+2*test+1 = 221


def test_build_plan_boundary_220_fails_221_builds(
    measured_calendar: list[date],
) -> None:
    """WR-08: 边界 220 日拒绝, 221 日恰好构建 2 折 + OOS。"""
    from app.backtest.walkforward import build_plan

    # 220 日 < 真实最小值 221 → fail-closed, 报出最小需求而非误导性几何错误。
    at_220 = measured_calendar[:220]
    with pytest.raises(ValueError, match="insufficient history") as excinfo:
        build_plan(
            plan_id="wf-220",
            universe="cn-a-share",
            asset_type="stock",
            dates=at_220,
            train_size=120,
            gap_size=20,
            test_size=20,
            oos_size=40,
            horizon=5,
        )
    assert "minimum 221" in str(excinfo.value)

    # 221 日 → 恰好 2 折, 各 test 段精确 20 日, OOS 精确 40 日, 几何断言通过。
    at_221 = measured_calendar[:221]
    plan = build_plan(
        plan_id="wf-221",
        universe="cn-a-share",
        asset_type="stock",
        dates=at_221,
        train_size=120,
        gap_size=20,
        test_size=20,
        oos_size=40,
        horizon=5,
    )
    assert len(plan.folds) == 2
    for fold in plan.folds:
        segment = [d for d in at_221 if fold.test_start <= d <= fold.test_end]
        assert len(segment) == 20
    oos_dates = [d for d in at_221 if d >= plan.oos_fold.test_start]
    assert len(oos_dates) == 40


def test_overlapping_fold_geometry_fails_closed(
    measured_calendar: list[date],
) -> None:
    """重叠折配置 fail-closed: 几何断言拒绝交叠的 test 段 (T-13-02)。"""
    from app.backtest.walkforward import (
        WalkForwardFold,
        _assert_geometry,
        _fold_chain_config,
    )

    dates = tuple(sorted(set(measured_calendar)))
    config = _fold_chain_config("cn-a-share", "stock", dates[0], dates[40], 5)

    def _fold(index: int, *, test_lo: int, test_hi: int) -> WalkForwardFold:
        # train [0, test_lo-21), gap [test_lo-20, test_lo-1], test [test_lo, test_hi]
        return WalkForwardFold(
            fold_index=index,
            is_oos=False,
            train_start=dates[0],
            train_end=dates[test_lo - 21],
            gap_start=dates[test_lo - 20],
            gap_end=dates[test_lo - 1],
            test_start=dates[test_lo],
            test_end=dates[test_hi],
            membership_fingerprint="0" * 64,
            chain_config=config,
        )

    # 第 0 折 test [30,49] 与第 1 折 test [40,59] 交叠 → 必须拒绝。
    with pytest.raises(ValueError, match=r"tile contiguously|must be disjoint"):
        _assert_geometry(
            folds=(_fold(0, test_lo=30, test_hi=49), _fold(1, test_lo=40, test_hi=59)),
            oos_fold=_fold(2, test_lo=80, test_hi=119),
            trading_dates=dates,
            oos_size=40,
        )


def test_oos_colliding_config_fails_closed(
    measured_calendar: list[date],
) -> None:
    """OOS 冲突配置 fail-closed: 保留 OOS 与末折 test 段交叠时拒绝 (T-13-02)。"""
    from app.backtest.walkforward import (
        WalkForwardFold,
        _assert_geometry,
        _fold_chain_config,
    )

    dates = tuple(sorted(set(measured_calendar)))
    config = _fold_chain_config("cn-a-share", "stock", dates[0], dates[40], 5)

    def _fold(index: int, *, is_oos: bool, test_lo: int, test_hi: int) -> WalkForwardFold:
        return WalkForwardFold(
            fold_index=index,
            is_oos=is_oos,
            train_start=dates[0],
            train_end=dates[test_lo - 21],
            gap_start=dates[test_lo - 20],
            gap_end=dates[test_lo - 1],
            test_start=dates[test_lo],
            test_end=dates[test_hi],
            membership_fingerprint="0" * 64,
            chain_config=config,
        )

    # 末折 test [30,49]; OOS test 起始 45 < 49 → 与末折 test 交叠。
    with pytest.raises(ValueError, match="must not overlap"):
        _assert_geometry(
            folds=(_fold(0, is_oos=False, test_lo=30, test_hi=49),),
            oos_fold=_fold(1, is_oos=True, test_lo=45, test_hi=84),
            trading_dates=dates,
            oos_size=40,
        )


def test_effective_days_label_buffer_reports_test_size_minus_horizon(
    measured_calendar: list[date],
) -> None:
    """标签缓冲: 无缓冲时末 horizon 日被丢弃 → effective = test_size - horizon。"""
    from app.backtest.walkforward import _effective_test_days

    # 合成一段密集 weekday 日历, 复现 13-RESEARCH 的 20 日 test/5 日 horizon 契约。
    days = _weekday_range(date(2025, 1, 2), date(2026, 1, 2))
    test_start, test_end = days[80], days[99]  # 20 个 test 交易日
    # 无标签缓冲: 计算窗终止于 test_end → 末 horizon 个交易日的前向收益为空。
    no_buffer = _effective_test_days(days, test_start, test_end, test_end, 5)
    assert no_buffer == 20 - 5
    assert no_buffer >= 10  # 标签缓冲守卫 (T-13-04)
    # 有缓冲 (end = test_end + horizon): 可评分日数 >= 无缓冲地板。
    with_buffer = _effective_test_days(
        days, test_start, test_end, test_end + timedelta(days=5), 5
    )
    assert with_buffer >= no_buffer
    assert with_buffer >= 10


def test_run_walk_forward_effective_days_below_10_raises(
    research_repository: ResearchRepository,
    measured_calendar: list[date],
    stub_resolver,
    stub_chain,
    stub_backtest_service,
) -> None:
    """effective_days < 10 时 run_walk_forward fail-closed (不是静默截断)。

    WR-09 后搜索折标签缓冲吸附到实测交易日, fully-covered 时 effective == test_size;
    只有日历末端不足 buffer 的折 (此处保留 OOS 折, 其后无更多实测交易日) 才会
    触发 < 10 守卫。
    """
    from app.backtest.walkforward import build_plan, run_walk_forward

    # horizon=40 ⇒ OOS 折在日历末端无足够未来交易日, effective ≈ 0 < 10。
    plan = build_plan(
        plan_id="wf-horizon40",
        universe="cn-a-share",
        asset_type="stock",
        dates=measured_calendar,
        train_size=120,
        gap_size=20,
        test_size=20,
        oos_size=40,
        horizon=40,
    )
    with pytest.raises(ValueError, match="effective days"):
        run_walk_forward(
            plan,
            strategy_id="fixture_strategy",
            params={"ma_proximity": 0.01},
            service=stub_backtest_service,
            chain=stub_chain,
            resolver=stub_resolver,
            repo=research_repository,
            evaluate_oos=True,  # 让保留 OOS 折 (日历末端) 参与, 触发 < 10 守卫
        )


def test_reporting_surface_get_plan_list_folds_and_validated(
    research_repository: ResearchRepository,
    wf_fixture_plan,
    stub_resolver,
    stub_chain,
    stub_backtest_service,
) -> None:
    """报告面 (13-05): get_wf_plan / list_wf_folds / list_wf_plans / list_wf_search_runs。"""
    from app.backtest.walkforward import run_walk_forward

    run_walk_forward(
        wf_fixture_plan,
        strategy_id="fixture_strategy",
        params={"ma_proximity": 0.02},
        service=stub_backtest_service,
        chain=stub_chain,
        resolver=stub_resolver,
        repo=research_repository,
        evaluate_oos=True,  # WR-01: 报告面覆盖 OOS 清单需要显式开启 OOS 评估
    )
    # get_wf_plan: trading_dates + fold_geometry 解包。
    plan_row = research_repository.get_wf_plan(wf_fixture_plan.plan_id)
    assert plan_row is not None
    assert plan_row["id"] == wf_fixture_plan.plan_id
    assert plan_row["trading_dates"] == [
        day.isoformat() for day in wf_fixture_plan.trading_dates
    ]
    assert len(plan_row["fold_geometry"]["folds"]) == len(wf_fixture_plan.folds)
    assert plan_row["fold_geometry"]["oos_fold"]["is_oos"] is True
    # list_wf_plans: 全部钉住的 plan, 新→旧。
    plans = research_repository.list_wf_plans()
    assert [p["id"] for p in plans] == [wf_fixture_plan.plan_id]
    # list_wf_folds(is_oos=1): 恰好一条 OOS 清单, chain_config/stats 解包。
    oos_folds = research_repository.list_wf_folds(plan_id=wf_fixture_plan.plan_id, is_oos=True)
    assert len(oos_folds) == 1
    assert oos_folds[0]["is_oos"] == 1
    assert "end" in oos_folds[0]["chain_config"]
    assert oos_folds[0]["stats"]["effective_days"] >= 10
    # list_wf_search_runs 读面存在 (空列表, limit 校验)。
    assert research_repository.list_wf_search_runs() == []
    with pytest.raises(ValueError, match="limit"):
        research_repository.list_wf_search_runs(limit=0)
    with pytest.raises(ValueError, match="limit"):
        research_repository.list_wf_plans(limit=0)
