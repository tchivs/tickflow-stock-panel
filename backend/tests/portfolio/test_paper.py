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

from datetime import UTC, datetime, timedelta

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
    from app.portfolio.paper import create_suggestion

    _record_plan(portfolio_repository, fixture_rebalance_run)
    suggested = create_suggestion("paper-plan-1", repository=portfolio_repository)
    assert suggested["transition"] == "suggested"
    assert portfolio_repository.get_paper_state("paper-plan-1") == "suggested"
    # idempotent: a second suggestion returns the same row
    again = create_suggestion("paper-plan-1", repository=portfolio_repository)
    assert again["id"] == suggested["id"]


def test_approve_is_idempotent_and_requires_suggested_state(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    from app.portfolio.paper import approve, create_suggestion

    _record_plan(portfolio_repository, fixture_rebalance_run)
    with pytest.raises(ValueError, match="has not been suggested"):
        approve("paper-plan-1", repository=portfolio_repository, idempotency_key="key-a")
    create_suggestion("paper-plan-1", repository=portfolio_repository)
    approved = approve("paper-plan-1", repository=portfolio_repository, idempotency_key="key-a")
    assert approved["transition"] == "approved"
    assert portfolio_repository.get_paper_state("paper-plan-1") == "approved"
    # idempotent re-approve with the same key returns the same row
    approved_again = approve(
        "paper-plan-1", repository=portfolio_repository, idempotency_key="key-a"
    )
    assert approved_again["id"] == approved["id"]
    # a different key on an already-approved plan raises
    with pytest.raises(ValueError, match="different idempotency key"):
        approve("paper-plan-1", repository=portfolio_repository, idempotency_key="key-b")


def test_reject_is_terminal_and_mutually_exclusive_with_approve(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    from app.portfolio.paper import approve, create_suggestion, reject

    _record_plan(portfolio_repository, fixture_rebalance_run)
    create_suggestion("paper-plan-1", repository=portfolio_repository)
    rejected = reject("paper-plan-1", repository=portfolio_repository, idempotency_key="key-r")
    assert rejected["transition"] == "rejected"
    assert portfolio_repository.get_paper_state("paper-plan-1") == "rejected"
    # idempotent re-reject
    rejected_again = reject(
        "paper-plan-1", repository=portfolio_repository, idempotency_key="key-r"
    )
    assert rejected_again["id"] == rejected["id"]
    # approve after reject is mutually exclusive
    with pytest.raises(ValueError, match="cannot approve"):
        approve("paper-plan-1", repository=portfolio_repository, idempotency_key="key-a")


def test_paper_fill_writes_only_transition_ledger(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
    fixture_plan_inputs: dict[str, object],
    fixture_prices: dict[str, float],
) -> None:
    """paper_fill appends a 'filled' audit fact and NEVER writes positions."""
    import sqlite3

    from app.portfolio.paper import approve, create_suggestion, paper_fill

    _record_plan(portfolio_repository, fixture_rebalance_run)
    create_suggestion("paper-plan-1", repository=portfolio_repository)
    # fill before approve fails
    with pytest.raises(ValueError, match="has not been approved"):
        paper_fill(
            "paper-plan-1",
            repository=portfolio_repository,
            prices=fixture_prices,
            matcher_config=fixture_plan_inputs["matcher_config"],
        )
    approve("paper-plan-1", repository=portfolio_repository, idempotency_key="key-a")
    filled = paper_fill(
        "paper-plan-1",
        repository=portfolio_repository,
        prices=fixture_prices,
        matcher_config=fixture_plan_inputs["matcher_config"],
    )
    assert filled["transition"] == "filled"
    assert filled["paper_position_delta"] == {"600000.SH": 5000, "600001.SH": 2500}
    assert portfolio_repository.get_paper_state("paper-plan-1") == "filled"
    # re-fill is idempotent: returns the same row
    filled_again = paper_fill(
        "paper-plan-1",
        repository=portfolio_repository,
        prices=fixture_prices,
        matcher_config=fixture_plan_inputs["matcher_config"],
    )
    assert filled_again["id"] == filled["id"]
    # no positions row was written
    with sqlite3.connect(portfolio_repository.database_path) as connection:
        count = int(connection.execute("SELECT COUNT(*) FROM positions").fetchone()[0])
    assert count == 0


def _record_expired_plan(
    portfolio_repository: PortfolioRepository,
    run: dict[str, object],
) -> dict[str, object]:
    """Record a rebalance_plans row whose expires_at is already in the past."""
    return portfolio_repository.record_rebalance_plan(
        id="expired-plan-1",
        optimization_run_id=str(run["id"]),
        input_snapshot_sha256=str(run["input_snapshot_sha256"]),
        as_of=str(run["as_of"]),
        target_weights_json={"600000.SH": 1.0},
        discrete_weights_json={"600000.SH": 1.0},
        lot_sizes_json={"600000.SH": 100},
        cash_residue=0.0,
        turnover_cost=0.0,
        blocked_instruments_json=[],
        discretization_rmse=0.0,
        rmse_definition="simple",
        expires_at="2020-01-01T00:00:00Z",
        output_sha256="c" * 64,
        artifact_relative_path="research_artifacts/run/rebalance/expired-plan-1.json",
        created_at="2020-01-01T00:00:00Z",
    )


def test_expired_plan_fails_closed_on_post_creation_transitions(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
    fixture_plan_inputs: dict[str, object],
    fixture_prices: dict[str, float],
) -> None:
    """approve/reject/fill on an expired plan raise ValueError."""
    from app.portfolio.paper import approve, create_suggestion, paper_fill, reject

    _record_expired_plan(portfolio_repository, fixture_rebalance_run)
    with pytest.raises(ValueError, match="expired"):
        create_suggestion("expired-plan-1", repository=portfolio_repository)
    with pytest.raises(ValueError, match="expired"):
        approve("expired-plan-1", repository=portfolio_repository, idempotency_key="key-a")
    with pytest.raises(ValueError, match="expired"):
        reject("expired-plan-1", repository=portfolio_repository, idempotency_key="key-r")
    with pytest.raises(ValueError, match="expired"):
        paper_fill(
            "expired-plan-1",
            repository=portfolio_repository,
            prices=fixture_prices,
            matcher_config=fixture_plan_inputs["matcher_config"],
        )


def test_no_execution_route_regression_gate(
    portfolio_repository: PortfolioRepository,
    fixture_rebalance_run: dict[str, object],
) -> None:
    """No INSERT INTO positions, no broker/submit/place_order vocabulary, no execute method."""
    import inspect
    import re

    import app.portfolio.paper as paper_module
    import app.portfolio.rebalance as rebalance_module

    for module in (paper_module, rebalance_module):
        source = inspect.getsource(module)
        assert "INSERT INTO positions" not in source
        assert "INSERT INTO" not in source
        assert not re.search(r"\b(broker|submit|place_order|live_)\b", source)
    # the only public callables defined by paper.py are the four transitions
    public_callables = {
        name
        for name, member in vars(paper_module).items()
        if callable(member)
        and not name.startswith("_")
        and getattr(member, "__module__", None) == paper_module.__name__
    }
    assert public_callables == {"create_suggestion", "approve", "reject", "paper_fill"}
    assert not any(name in public_callables for name in ("execute", "submit", "place_order"))
