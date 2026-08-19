"""Walk-forward 测试 (双侧合并)。

本文件合并两组 walk-forward 契约:

1. 我方 (research 治理栈, WFWD-01/02) — build_plan 几何 (3 折 + gap + 预留
   40d OOS, 贴合实测日历), 每折 PIT membership 指纹, exactly-once OOS 钉定
   (repository 层), best_params 验证门与 wf_validated_strategies 裁决。
2. 上游 v0.2 (策略域滚动窗口) — generate_folds 滚动训练/测试窗口切分,
   aggregate_oos 聚合 (复利净值/IS-OOS 退化/一致性), WalkForwardService
   每折 训练区间优化 -> 测试区间 OOS 验证, 以及 API 层 job_key/cancel。

两组用例互不重叠, 分别锁定 app.backtest.walkforward 中两组正交实现面。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace

import polars as pl
import pytest

from app.backtest.engine import PanelCache
from app.backtest.walkforward import (
    WalkForwardConfig,
    WalkForwardService,
    aggregate_oos,
    generate_folds,
)
from app.research.repository import ResearchRepository

# ===========================================================================
# Part 1 — 我方 research 治理栈: WFWD-01/02 契约 (geometry / repository / gate)
# ===========================================================================


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


def test_evaluate_best_params_wr02_no_oos_row_on_missing_objective(
    research_repository: ResearchRepository,
    wf_fixture_plan,
    stub_resolver,
    stub_chain,
) -> None:
    """WR-02: 目标缺失时 OOS 折行绝不持久化 — 恰好一次槽位不被烧掉。"""
    from app.backtest.walkforward import evaluate_best_params

    class _NoObjectiveService:
        def run(self, config, progress_cb=None, cancel_event=None):  # type: ignore[no-untyped-def]
            del config, progress_cb, cancel_event
            return SimpleNamespace(stats={"total_return": 0.05}, error=None)  # 无 sharpe

    with pytest.raises(ValueError, match="has no objective 'sharpe'"):
        evaluate_best_params(
            wf_fixture_plan,
            strategy_id="fixture_strategy",
            best_params={"ma_proximity": 0.02},
            service=_NoObjectiveService(),
            chain=stub_chain,
            resolver=stub_resolver,
            repo=research_repository,
            objective="sharpe",
        )
    # 目标验证先于写行: OOS 槽位未被消耗, 无 OOS 折、无裁决。
    assert research_repository.list_wf_folds(
        plan_id=wf_fixture_plan.plan_id, is_oos=True
    ) == []
    assert research_repository.list_validated_strategies() == []


def test_evaluate_best_params_wr10_unknown_search_run_fk_mapped(
    research_repository: ResearchRepository,
    wf_fixture_plan,
    stub_resolver,
    stub_chain,
    stub_backtest_service,
) -> None:
    """WR-10: 伪造 search_run_id 的 FK 违反映射为清晰的缺失搜索运行错误。"""
    from app.backtest.walkforward import evaluate_best_params

    with pytest.raises(ValueError, match="unknown search run"):
        evaluate_best_params(
            wf_fixture_plan,
            strategy_id="fixture_strategy",
            best_params={"ma_proximity": 0.02},
            service=stub_backtest_service,
            chain=stub_chain,
            resolver=stub_resolver,
            repo=research_repository,
            objective="sharpe",
            search_run_id="never-persisted-search-run",
        )


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

# ===========================================================================
# Part 2 — 上游 v0.2 策略域 walk-forward: generate_folds / aggregate_oos /
#          WalkForwardService 编排 + API job_key
# ===========================================================================


# ---------------------------------------------------------------
# fold 生成
# ---------------------------------------------------------------

def test_folds_rolling_windows():
    # 1 年数据, 训练 90d / 测试 30d / 步进 30d
    folds = generate_folds(date(2024, 1, 1), date(2024, 12, 31), train_days=90, test_days=30, step_days=30)
    assert len(folds) > 0
    f0 = folds[0]
    assert f0.train_start == date(2024, 1, 1)
    assert f0.train_end == date(2024, 3, 31)     # +90d (2024 闰年)
    assert f0.test_start == date(2024, 4, 1)     # train_end + 1天 (隔断前视泄漏)
    assert f0.test_end == date(2024, 5, 1)       # +30d
    # 滚动: 下一折训练起点 +step
    assert folds[1].train_start == date(2024, 1, 31)  # +30d


def test_folds_test_starts_day_after_train_end():
    """无前视泄漏: 每折 test_start 严格晚于 train_end (不共享同一天)。"""
    folds = generate_folds(date(2024, 1, 1), date(2024, 12, 31), train_days=90, test_days=30, step_days=30)
    for f in folds:
        assert f.test_start > f.train_end


def test_folds_no_test_beyond_end():
    folds = generate_folds(date(2024, 1, 1), date(2024, 12, 31), train_days=90, test_days=30, step_days=30)
    for f in folds:
        assert f.test_end <= date(2024, 12, 31)


def test_folds_insufficient_span_raises():
    # 训练90+测试30=120d, 但只有 100d 数据 -> 0 折
    with pytest.raises(ValueError, match=r"数据区间不足|至少"):
        generate_folds(date(2024, 1, 1), date(2024, 4, 10), train_days=90, test_days=30, step_days=30)


def test_folds_reject_nonpositive_windows():
    with pytest.raises(ValueError, match=r"必须为正"):
        generate_folds(date(2024, 1, 1), date(2024, 12, 31), train_days=0, test_days=30, step_days=30)


# ---------------------------------------------------------------
# OOS 聚合
# ---------------------------------------------------------------

def _rec(index, is_score, total_return, obj):
    return {
        "index": index,
        "test_end": date(2024, 1, 1),
        "best_params": {"p": index},
        "is_score": is_score,
        "oos_objective": obj,
        "oos_stats": {"total_return": total_return, "sortino": obj},
    }


def test_aggregate_compounds_oos_returns():
    recs = [_rec(0, 2.0, 0.10, 1.5), _rec(1, 2.0, -0.05, 0.8), _rec(2, 2.0, 0.08, 1.2)]
    agg = aggregate_oos(recs, objective="sortino")
    # 复利: 1.1 * 0.95 * 1.08 - 1
    assert abs(agg["compounded_oos_return"] - (1.10 * 0.95 * 1.08 - 1)) < 1e-9
    assert len(agg["oos_equity_curve"]) == 3


def test_aggregate_is_oos_degradation():
    # IS 目标平均远高于 OOS -> 退化为正 (过拟合信号)
    recs = [_rec(0, 3.0, 0.05, 0.5), _rec(1, 3.0, 0.02, 0.3)]
    agg = aggregate_oos(recs, objective="sortino")
    assert agg["avg_is_objective"] == 3.0
    assert abs(agg["avg_oos_objective"] - 0.4) < 1e-9
    assert agg["degradation"] > 0  # IS 3.0 - OOS 0.4 = 2.6


def test_aggregate_consistency_fraction_positive():
    # consistency 按 OOS 总收益 > 0 的折占比: total_return 0.1>0, -0.1<=0, 0.1>0 -> 2/3
    recs = [_rec(0, 1, 0.1, 1.5), _rec(1, 1, -0.1, -0.2), _rec(2, 1, 0.1, 0.8)]
    agg = aggregate_oos(recs, objective="sortino")
    assert agg["consistency"] == round(2 / 3, 4)  # 0.6667


def test_aggregate_degradation_direction_aware_for_min_objective():
    """min 类目标 (avg_holding_days, 越小越好): OOS 持仓天数更大 = 退化, degradation>0。"""
    # IS 持仓 3 天, OOS 持仓 5 天 (更长=更差) -> 退化
    recs = [{"index": 0, "test_end": date(2024, 1, 1), "is_score": 3.0,
             "oos_objective": 5.0, "oos_stats": {"total_return": 0.05}}]
    agg = aggregate_oos(recs, objective="avg_holding_days", direction="min")
    # 归一空间: norm(3)=-3, norm(5)=-5 -> degradation = -3 - (-5) = 2 > 0 = 退化
    assert agg["degradation"] == round(2.0, 4)


def test_aggregate_empty_folds():
    agg = aggregate_oos([], objective="sortino")
    assert agg["n_folds"] == 0
    assert agg["compounded_oos_return"] == 0.0


# ---------------------------------------------------------------
# 编排 (假 optimizer / service)
# ---------------------------------------------------------------

@dataclass
class _FakeResult:
    stats: dict
    error: str | None = None


class _FakeOptimizer:
    """optimize 返回受控 best_params/best_score, 记录被优化的训练区间。"""
    def __init__(self):
        self.train_ranges = []
        self.opt_kwargs = []  # 记录每折 IS 优化收到的 backtest_kwargs (验证 mode 强制)

    def optimize(self, cfg, progress_cb=None, cancel_event=None):
        self.train_ranges.append((cfg.start, cfg.end))
        self.opt_kwargs.append(dict(cfg.backtest_kwargs))
        # best_params 随训练起点变化, best_score 固定
        return {"best_params": {"p": cfg.start.month}, "best_score": 2.0, "results": [], "n_completed": 1}


# 从真实 PanelCache 取字段模板 —— 字段被重命名时本桩自动跟随, 避免 test 绿而生产 KeyError。
# (PanelCache 的导入已上移至文件头部。)

_ZERO_CACHE_STATS = {k: type(v)() for k, v in PanelCache().stats().items()}


class _FakeEngine:
    """最小引擎桩: 仅提供 WF 遥测所需的 cache_stats (字段同源自 PanelCache.stats)。"""
    def cache_stats(self):
        return dict(_ZERO_CACHE_STATS)


class _FakeService:
    """run 返回受控 OOS stats, 记录测试区间 + 收到的 params。"""
    def __init__(self):
        self.calls = []
        self.engine = _FakeEngine()

    def run(self, config, progress_cb=None, cancel_event=None):
        self.calls.append({"start": config.start, "end": config.end,
                           "params": dict(config.params or {}), "mode": config.mode})
        return _FakeResult(stats={"total_return": 0.05, "sortino": 1.0})


def _wf_cfg(**kw):
    base = dict(
        strategy_id="s", symbols=None, start=date(2024, 1, 1), end=date(2024, 12, 31),
        param_grid={"p": [1, 2]}, objective="sortino",
        train_days=90, test_days=30, step_days=30,
    )
    base.update(kw)
    return WalkForwardConfig(**base)


def test_walkforward_optimizes_train_applies_oos():
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())

    assert out["n_folds"] > 0
    # 每折: optimizer 在训练区间跑, service 在测试区间用最优参数跑
    assert len(opt.train_ranges) == out["n_folds"]
    assert len(svc.calls) == out["n_folds"]
    # OOS 回测用的是该折优化出的 best_params (来自训练起点月份)
    first_fold = out["folds"][0]
    assert svc.calls[0]["params"] == first_fold["best_params"]
    # 训练区间与测试区间不重叠 (测试在训练之后)
    assert svc.calls[0]["start"] >= opt.train_ranges[0][1]


class _CountingEngine:
    """首尾两次 cache_stats 返回不同值, 用于验证 WF 遥测差值/顺序计算 (非全零掩盖)。"""
    def __init__(self):
        self._n = 0

    def cache_stats(self):
        self._n += 1
        if self._n == 1:  # run 开头快照 (before)
            return {"compute_seconds": 1.0, "compute_count": 2, "hit_count": 0, "reuse_count": 0}
        return {"compute_seconds": 3.5, "compute_count": 7, "hit_count": 4, "reuse_count": 3}  # after


def test_walkforward_cache_telemetry_computes_deltas():
    """cache_telemetry 用首尾快照差值: scans/hits/reuses/秒数 = after - before, 且方向正确。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    svc.engine = _CountingEngine()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())

    tel = out["cache_telemetry"]
    assert tel["scans"] == 5          # 7 - 2, 顺序写反会得 -5
    assert tel["hits"] == 4           # 4 - 0
    assert tel["single_flight_reuses"] == 3  # 3 - 0
    assert abs(tel["load_panel_seconds"] - 2.5) < 1e-9  # 3.5 - 1.0
    assert tel["load_panel_pct"] >= 0.0  # 扫盘耗时 / WF总耗时, 非负


def test_walkforward_forces_position_mode_for_is_optimization():
    """训练折(IS)强制 position 防前视泄漏(full 会用 OOS 区间 K 线平仓污染 IS);
    OOS 回测保留用户所选 mode。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    wf.run(_wf_cfg(backtest_kwargs={"mode": "full"}))

    assert len(opt.opt_kwargs) > 0 and len(svc.calls) > 0
    # 用户选了 full, 但每折 IS 优化都被强制 position
    assert all(kw["mode"] == "position" for kw in opt.opt_kwargs), "IS 优化未强制 position"
    # OOS 回测保留用户的 full
    assert all(c["mode"] == "full" for c in svc.calls), "OOS 未保留用户 mode"


def test_walkforward_reports_degradation():
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())
    # IS best_score=2.0, OOS sortino=1.0 -> 退化 1.0
    assert out["summary"]["avg_is_objective"] == 2.0
    assert out["summary"]["avg_oos_objective"] == 1.0
    assert abs(out["summary"]["degradation"] - 1.0) < 1e-9


class _NoParamsOptimizer(_FakeOptimizer):
    """模拟训练区间全组失败: best_params=None。"""
    def optimize(self, cfg, progress_cb=None, cancel_event=None):
        self.train_ranges.append((cfg.start, cfg.end))
        return {"best_params": None, "best_score": None, "results": [], "n_completed": 0}


class _ErrorService(_FakeService):
    """模拟 OOS 回测失败。"""
    def run(self, config, progress_cb=None, cancel_event=None):
        self.calls.append({"start": config.start, "end": config.end, "params": dict(config.params or {})})
        return _FakeResult(stats={}, error="no data")


def test_walkforward_skips_folds_without_optimized_params():
    """训练区间没优化出参数 (best_params=None) -> 跳过, 不用默认参数硬跑 OOS 伪装成有效折。"""
    opt, svc = _NoParamsOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())
    assert out["n_folds"] == 0           # 无有效折
    assert out["n_skipped"] > 0          # 全部跳过
    assert svc.calls == []               # 不跑 OOS
    assert out["summary"]["compounded_oos_return"] == 0.0  # 无效折不污染净值


def test_walkforward_skips_oos_error_folds():
    """OOS 回测失败的折 -> 跳过, 不把空/0 收益混入复利曲线。"""
    opt, svc = _FakeOptimizer(), _ErrorService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())
    assert out["n_folds"] == 0
    assert out["n_skipped"] > 0
    assert len(svc.calls) > 0            # OOS 跑了但失败
    assert out["summary"]["compounded_oos_return"] == 0.0  # 失败折不计入


def test_walkforward_cancel_stops():
    import threading
    ev = threading.Event()
    ev.set()
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg(), cancel_event=ev)
    # 取消 -> 不跑任何折
    assert svc.calls == []
    assert out["n_folds"] == 0


# ---------------------------------------------------------------
# API: job_key 回吐 + cancel 按 key 查表
# ---------------------------------------------------------------

def test_wf_job_key_distinguishes_windows():
    from app.api.backtest import _make_wf_job_key
    base = _make_wf_job_key("s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig")
    assert base != _make_wf_job_key("s", None, None, None, '{"p":[1]}', "sortino", None, "120/30/30", "sig")


def test_wf_job_key_distinguishes_params_and_overrides():
    """params/overrides 不同必须产出不同 job_key —— 否则 stream 与 cancel 会错配到别的任务。"""
    from app.api.backtest import _make_wf_job_key
    base = _make_wf_job_key("s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig")
    # params 不同 (未扫描参数固定值不同 -> 优化的策略不同)
    assert base != _make_wf_job_key(
        "s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig", params='{"x":1}')
    # overrides 不同 (basic_filter/信号/风控 不同)
    assert base != _make_wf_job_key(
        "s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig", overrides='{"score_min":5}')
    # 相同 params/overrides 必须稳定一致 (stream 端与 cancel 端对齐前提)
    k = _make_wf_job_key("s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig", params='{"x":1}')
    assert k == _make_wf_job_key(
        "s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig", params='{"x":1}')


def test_wf_cancel_by_echoed_key():
    import asyncio

    from app.api.backtest import _BacktestJob, _running_jobs, walkforward_cancel

    class _Req:
        def __init__(self, body):
            self._body = body
        async def json(self):
            return self._body

    key = "wfkey_test_1"
    _running_jobs[key] = _BacktestJob(key)
    try:
        res = asyncio.run(walkforward_cancel(_Req({"job_key": key})))
        assert res["ok"] is True
        assert _running_jobs[key].cancel_event.is_set()
        res2 = asyncio.run(walkforward_cancel(_Req({"job_key": "nope"})))
        assert res2["ok"] is False
    finally:
        _running_jobs.pop(key, None)
