"""RBAL-02 paper-rebalance state machine contracts — Wave 0 scaffold.

职责: 锁定纸面调仓状态机的契约面 —— 建议 (suggested) → 人工审批
(approved) / 驳回 (rejected) → 纸面成交 (filled), 每条迁移都是 append-only
审计事实, UNIQUE (plan_id, transition) 幂等, reject 终态且与 approve 互斥,
过期计划 fail-closed, 且纸面成交绝不写 positions (无执行路由, 硬性验收)。

Wave 0 状态: 14-01 之前本文件按计划保持 RED —— 所有引用
``app.portfolio.paper`` 的用例在模块缺失时失败 (ImportError), 由 14-01
转绿。仓库层 (14-02 PortfolioRepository) 的幂等 / 派生状态 / 列表用例在
14-02 落地后即转绿。
"""
from __future__ import annotations

import pytest

from app.portfolio.repository import PortfolioRepository


def _record_plan(
    repository: PortfolioRepository,
    run: dict[str, object],
    *,
    plan_id: str = "paper-plan-1",
) -> dict[str, object]:
    """Record a valid rebalance_plans row the transition ledger can reference."""
    return repository.record_rebalance_plan(
        id=plan_id,
        optimization_run_id=str(run["id"]),
        input_snapshot_sha256=str(run["input_snapshot_sha256"]),
        as_of=str(run["as_of"]),
        target_weights_json={"600000.SH": 0.5, "600001.SH": 0.5},
        discrete_weights_json={"600000.SH": 0.5, "600001.SH": 0.5},
        lot_sizes_json={"600000.SH": 5000, "600001.SH": 2500},
        cash_residue=1200.0,
        turnover_cost=45.6,
        blocked_instruments_json=[],
        discretization_rmse=0.012,
        rmse_definition="simple",
        expires_at="2026-08-08T00:00:00Z",
        output_sha256="b" * 64,
        artifact_relative_path="research_artifacts/run/rebalance/paper-plan-1.json",
        created_at="2026-08-01T00:00:00Z",
    )


# ================================================================
# Repository surface (14-02) — GREEN once the methods land
# ================================================================


def test_record_paper_transition_idempotent_with_matching_key(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    _record_plan(portfolio_repository, fixture_rebalance_run)
    first = portfolio_repository.record_paper_transition(
        plan_id="paper-plan-1", transition="suggested", idempotency_key="key-1"
    )
    second = portfolio_repository.record_paper_transition(
        plan_id="paper-plan-1", transition="suggested", idempotency_key="key-1"
    )
    assert second["id"] == first["id"]
    assert second["transition"] == "suggested"


def test_record_paper_transition_mismatched_key_raises(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    _record_plan(portfolio_repository, fixture_rebalance_run)
    portfolio_repository.record_paper_transition(
        plan_id="paper-plan-1", transition="suggested", idempotency_key="key-1"
    )
    with pytest.raises(ValueError, match="different idempotency key"):
        portfolio_repository.record_paper_transition(
            plan_id="paper-plan-1", transition="suggested", idempotency_key="other-key"
        )


def test_record_paper_transition_unknown_transition_raises(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    _record_plan(portfolio_repository, fixture_rebalance_run)
    with pytest.raises(ValueError, match="unknown paper transition"):
        portfolio_repository.record_paper_transition(
            plan_id="paper-plan-1", transition="pending", idempotency_key="key-1"
        )


def test_get_paper_state_derived_from_ledger(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    _record_plan(portfolio_repository, fixture_rebalance_run)
    assert portfolio_repository.get_paper_state("paper-plan-1") is None
    portfolio_repository.record_paper_transition(
        plan_id="paper-plan-1", transition="suggested", idempotency_key="key-1"
    )
    assert portfolio_repository.get_paper_state("paper-plan-1") == "suggested"
    portfolio_repository.record_paper_transition(
        plan_id="paper-plan-1",
        transition="approved",
        idempotency_key="key-2",
        previous_state="suggested",
    )
    assert portfolio_repository.get_paper_state("paper-plan-1") == "approved"


def test_list_paper_transitions_filters_and_caps(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    _record_plan(portfolio_repository, fixture_rebalance_run)
    portfolio_repository.record_paper_transition(
        plan_id="paper-plan-1", transition="suggested", idempotency_key="key-1"
    )
    portfolio_repository.record_paper_transition(
        plan_id="paper-plan-1",
        transition="approved",
        idempotency_key="key-2",
        previous_state="suggested",
    )
    all_rows = portfolio_repository.list_paper_transitions()
    assert [r["transition"] for r in all_rows] == ["suggested", "approved"]
    approved = portfolio_repository.list_paper_transitions(transition="approved")
    assert len(approved) == 1
    assert approved[0]["transition"] == "approved"
    with pytest.raises(ValueError, match="positive integer"):
        portfolio_repository.list_paper_transitions(limit=0)
    with pytest.raises(ValueError, match="unknown paper transition"):
        portfolio_repository.list_paper_transitions(transition="executed")


# ================================================================
# State-machine module contracts (14-01) — RED until the module lands
# ================================================================


def _paper_module() -> object:
    """Lazy import — RED (ImportError) until 14-01 creates portfolio/paper.py."""
    from app.portfolio.paper import approve, create_suggestion, paper_fill, reject  # noqa: F401

    return None


def test_create_suggestion_records_append_only_fact(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    _paper_module()


def test_approve_is_idempotent_and_requires_suggested_state(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    _paper_module()


def test_reject_is_terminal_and_mutually_exclusive_with_approve(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    _paper_module()


def test_paper_fill_writes_only_transition_ledger(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
    fixture_plan_inputs: dict[str, object],
) -> None:
    """paper_fill appends a 'filled' audit fact and NEVER writes positions."""
    _paper_module()


def test_expired_plan_fails_closed_on_post_creation_transitions(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    """approve/reject/fill on an expired plan raise ValueError."""
    _paper_module()


def test_no_execution_route_regression_gate(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    """No INSERT INTO positions, no broker/submit/place_order vocabulary, no execute method."""
    _paper_module()
