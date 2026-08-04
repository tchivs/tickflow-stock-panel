"""Portfolio panel route scaffold tests (Wave 0 / 15-02) + tracer tests (Wave 1 / 15-01).

Wave 0 scaffold cases verify the routes register, return 200 on empty lists,
return 404 on missing entities, and that the strict DTO rejects extra fields.

Wave 1 tracer cases (15-01) record a fixture optimization run + a failed run
and verify the full run-row → DTO → route → response spine works end-to-end
with baselines + honest failure display.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.portfolio.repository import PortfolioRepository


# ================================================================
# Wave 0 scaffold cases (15-02)
# ================================================================


def test_list_optimization_runs_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/portfolio/optimization-runs")
    assert response.status_code == 200
    assert response.json() == []


def test_get_optimization_run_not_found(panel_client: TestClient) -> None:
    response = panel_client.get("/api/portfolio/optimization-runs/nonexistent")
    assert response.status_code == 404


def test_list_optimization_runs_limit_fail_closed(panel_client: TestClient) -> None:
    response = panel_client.get("/api/portfolio/optimization-runs", params={"limit": 0})
    assert response.status_code == 422


def test_list_attribution_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/portfolio/attribution")
    assert response.status_code == 200
    assert response.json() == []


def test_list_rebalance_plans_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/portfolio/rebalance-plans")
    assert response.status_code == 200
    assert response.json() == []


def test_get_paper_state_not_found(panel_client: TestClient) -> None:
    response = panel_client.get("/api/portfolio/rebalance-plans/nonexistent/paper")
    assert response.status_code == 404


def test_optimization_run_dto_rejects_extra_fields() -> None:
    """Strict DTO: extra field in the Pydantic model itself is forbidden."""
    from app.contracts.panels import OptimizationRunDTO
    from pydantic import ValidationError

    minimal = {
        "id": "run-1",
        "objective": "min_volatility",
        "as_of": "2026-01-01",
        "universe": "cn-a-share",
        "input_snapshot_sha256": "a" * 64,
        "expected_return_method": "none",
        "risk_model": "sample_covariance_v1",
        "solver_name": "CLARABEL",
        "solver_version": "1.9.2",
        "problem_status": "optimal",
        "output_sha256": "b" * 64,
        "created_at": "2026-01-01T00:00:00Z",
        "bogus_field": "should fail",
    }
    with pytest.raises(ValidationError):
        OptimizationRunDTO(**minimal)


# ================================================================
# Wave 1 tracer cases (15-01)
# ================================================================


def _record_fixture_run(
    repo: PortfolioRepository, *, failed: bool = False
) -> dict:
    """Record a minimal optimization run row for panel testing."""
    weights = {"600000.SH": 0.6, "600001.SH": 0.4}
    weights_payload = json.dumps(weights, sort_keys=True, separators=(",", ":")).encode()
    weights_sha = hashlib.sha256(weights_payload).hexdigest()
    baseline = {"600000.SH": 0.5, "600001.SH": 0.5}
    baseline_payload = json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode()
    from app.research.repository import ResearchRepository
    research = ResearchRepository(repo.database_path)
    try:
        research.insert_model_definition(
            model_id="composite-model-v1",
            name="tracer composite",
            weighting="equal",
            revision_ids=[],
            weights={},
            input_snapshot_sha256="f" * 64,
        )
    except Exception:
        pass  # already exists
    return repo.record_optimization_run(
        id="run-tracer-001" if not failed else "run-tracer-failed",
        objective="min_volatility",
        as_of="2026-08-01",
        universe="cn-a-share",
        model_id="composite-model-v1",
        composite_snapshot_id="snap-001",
        input_snapshot_sha256="f" * 64,
        expected_return_method="composite-zscore-v1",
        risk_model="sample_covariance_v1",
        risk_model_json={"risk_model": "sample_covariance_v1"},
        constraint_stack_json={"long_only": True, "max_weight": 0.3},
        solver_name="CLARABEL",
        solver_version="1.9.2",
        solver_options_json={"tol_gap_abs": 1e-8},
        problem_status="solver_error" if failed else "optimal",
        failure_reason="CLARABEL returned solver_error" if failed else None,
        output_weights_json=weights if not failed else None,
        output_sha256=weights_sha if not failed else "0" * 64,
        weights_artifact_relative_path=f"research_artifacts/run-tracer-{'failed' if failed else '001'}/weights.json",
        baseline_weights_json=baseline if not failed else None,
        created_at="2026-08-01T00:00:00Z",
    )


def test_tracer_list_returns_recorded_run(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    _record_fixture_run(portfolio_repository)
    response = panel_client.get("/api/portfolio/optimization-runs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    run = data[0]
    assert run["id"] == "run-tracer-001"
    assert run["objective"] == "min_volatility"
    assert run["problem_status"] == "optimal"
    assert run["output_weights"] == {"600000.SH": 0.6, "600001.SH": 0.4}
    # Baselines rendered alongside — never "optimal" alone
    assert run["baseline_weights"] == {"600000.SH": 0.5, "600001.SH": 0.5}


def test_tracer_get_by_id_returns_full_dto(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    _record_fixture_run(portfolio_repository)
    response = panel_client.get("/api/portfolio/optimization-runs/run-tracer-001")
    assert response.status_code == 200
    run = response.json()
    assert run["id"] == "run-tracer-001"
    assert run["output_weights"] == {"600000.SH": 0.6, "600001.SH": 0.4}
    assert run["baseline_weights"] == {"600000.SH": 0.5, "600001.SH": 0.5}
    assert run["constraint_stack"] == {"long_only": True, "max_weight": 0.3}
    assert run["solver_name"] == "CLARABEL"
    assert run["input_snapshot_sha256"] == "f" * 64


def test_tracer_failed_run_shows_failure_reason(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    _record_fixture_run(portfolio_repository, failed=True)
    response = panel_client.get("/api/portfolio/optimization-runs/run-tracer-failed")
    assert response.status_code == 200
    run = response.json()
    assert run["problem_status"] == "solver_error"
    assert run["failure_reason"] == "CLARABEL returned solver_error"
    assert run["output_weights"] is None


def test_tracer_objective_filter(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    _record_fixture_run(portfolio_repository)
    _record_fixture_run(portfolio_repository, failed=True)
    response = panel_client.get(
        "/api/portfolio/optimization-runs", params={"objective": "min_volatility"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


# ================================================================
# Wave 2 breadth cases (15-04) — attribution, rebalance, paper state
# ================================================================


def _record_fixture_evidence(
    repo: PortfolioRepository,
    *,
    evidence_id: str = "attr-001",
    run_id: str = "run-tracer-001",
) -> dict:
    """Record one attribution-evidence row bound to a fixture optimization run."""
    return repo.record_attribution_evidence(
        id=evidence_id,
        attribution_type="exposure_contribution",
        run_id=run_id,
        risk_model="sample_covariance_v1",
        as_of="2026-08-01",
        output_sha256="a" * 64,
        artifact_relative_path=f"portfolio_artifacts/{evidence_id}/attribution.json",
        reconciliation_json={"reconciled": True, "drift": 0.0004, "max_depth": 3},
        created_at="2026-08-01T00:00:00Z",
    )


def _record_fixture_plan(
    repo: PortfolioRepository,
    *,
    plan_id: str = "plan-001",
    run_id: str = "run-tracer-001",
) -> dict:
    """Record one immutable rebalance plan bound to a fixture optimization run."""
    return repo.record_rebalance_plan(
        id=plan_id,
        optimization_run_id=run_id,
        input_snapshot_sha256="a" * 64,
        as_of="2026-08-01",
        target_weights_json={"600000.SH": 0.6, "600001.SH": 0.4},
        discrete_weights_json={"600000.SH": 0.6, "600001.SH": 0.4},
        lot_sizes_json={"600000.SH": 600, "600001.SH": 400},
        cash_residue=0.0008,
        turnover_cost=0.0021,
        blocked_instruments_json={},
        discretization_rmse=0.00012,
        rmse_definition="simple",
        expires_at="2026-09-01T00:00:00Z",
        output_sha256="b" * 64,
        artifact_relative_path=f"portfolio_artifacts/{plan_id}/plan.json",
        created_at="2026-08-01T00:00:00Z",
    )


def test_attribution_list_returns_recorded_evidence(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    _record_fixture_run(portfolio_repository)
    _record_fixture_evidence(portfolio_repository)
    response = panel_client.get("/api/portfolio/attribution")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "attr-001"
    assert row["attribution_type"] == "exposure_contribution"
    assert row["risk_model"] == "sample_covariance_v1"
    assert row["run_id"] == "run-tracer-001"
    # exposure-contribution evidence MUST carry a reconciliation payload
    assert row["reconciliation"] == {"reconciled": True, "drift": 0.0004, "max_depth": 3}


def test_attribution_filters_by_risk_model(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    _record_fixture_run(portfolio_repository)
    _record_fixture_evidence(portfolio_repository)
    miss = panel_client.get(
        "/api/portfolio/attribution", params={"risk_model": "semi_covariance_v1"}
    )
    assert miss.status_code == 200
    assert miss.json() == []
    hit = panel_client.get(
        "/api/portfolio/attribution", params={"risk_model": "sample_covariance_v1"}
    )
    assert hit.status_code == 200
    assert len(hit.json()) == 1


def test_rebalance_plan_list_returns_recorded_plan(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    _record_fixture_run(portfolio_repository)
    _record_fixture_plan(portfolio_repository)
    response = panel_client.get("/api/portfolio/rebalance-plans")
    assert response.status_code == 200
    plans = response.json()
    assert len(plans) == 1
    plan = plans[0]
    assert plan["id"] == "plan-001"
    assert plan["optimization_run_id"] == "run-tracer-001"
    assert plan["target_weights"] == {"600000.SH": 0.6, "600001.SH": 0.4}
    assert plan["discrete_weights"] == {"600000.SH": 0.6, "600001.SH": 0.4}
    assert plan["lot_sizes"] == {"600000.SH": 600, "600001.SH": 400}
    assert plan["cash_residue"] == 0.0008
    assert plan["turnover_cost"] == 0.0021
    assert plan["discretization_rmse"] == 0.00012
    assert plan["rmse_definition"] == "simple"
    assert plan["expires_at"] == "2026-09-01T00:00:00Z"
    assert plan["output_sha256"] == "b" * 64


def test_paper_state_empty_before_any_transition(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    _record_fixture_run(portfolio_repository)
    _record_fixture_plan(portfolio_repository)
    response = panel_client.get("/api/portfolio/rebalance-plans/plan-001/paper")
    assert response.status_code == 200
    state = response.json()
    assert state["plan_id"] == "plan-001"
    assert state["current_state"] is None
    assert state["transitions"] == []


def test_paper_state_approve_is_idempotent(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    _record_fixture_run(portfolio_repository)
    _record_fixture_plan(portfolio_repository)

    first = panel_client.post(
        "/api/portfolio/rebalance-plans/plan-001/approve",
        json={"idempotency_key": "approve-key-1"},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["transition"] == "approved"
    assert first_body["current_state"] == "approved"

    # Re-POSTing the SAME idempotency key replays the existing transition — no
    # duplicate row, same derived state (UNIQUE (plan_id, transition)).
    replay = panel_client.post(
        "/api/portfolio/rebalance-plans/plan-001/approve",
        json={"idempotency_key": "approve-key-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["current_state"] == "approved"

    state = panel_client.get("/api/portfolio/rebalance-plans/plan-001/paper").json()
    assert state["current_state"] == "approved"
    assert len(state["transitions"]) == 1
    assert state["transitions"][0]["transition"] == "approved"
    assert state["transitions"][0]["idempotency_key"] == "approve-key-1"


def test_paper_state_reject_after_approve_appends_audit_fact(
    portfolio_repository: PortfolioRepository, panel_client: TestClient
) -> None:
    """The route is append-only audit, not a guarded state machine: a later
    'rejected' transition is a distinct (plan_id, transition) row, so the
    derived current_state advances to 'rejected'. There is no execute path."""
    _record_fixture_run(portfolio_repository)
    _record_fixture_plan(portfolio_repository)
    panel_client.post(
        "/api/portfolio/rebalance-plans/plan-001/approve",
        json={"idempotency_key": "approve-key-1"},
    )
    reject = panel_client.post(
        "/api/portfolio/rebalance-plans/plan-001/reject",
        json={"idempotency_key": "reject-key-1"},
    )
    assert reject.status_code == 200
    assert reject.json()["transition"] == "rejected"
    assert reject.json()["current_state"] == "rejected"

    # Re-reject with the same key replays idempotently.
    replay = panel_client.post(
        "/api/portfolio/rebalance-plans/plan-001/reject",
        json={"idempotency_key": "reject-key-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["current_state"] == "rejected"

    state = panel_client.get("/api/portfolio/rebalance-plans/plan-001/paper").json()
    assert state["current_state"] == "rejected"
    transitions = [t["transition"] for t in state["transitions"]]
    assert transitions == ["approved", "rejected"]


def test_paper_state_nonexistent_plan_404(panel_client: TestClient) -> None:
    response = panel_client.get("/api/portfolio/rebalance-plans/nonexistent/paper")
    assert response.status_code == 404


def test_paper_approve_nonexistent_plan_404(panel_client: TestClient) -> None:
    response = panel_client.post(
        "/api/portfolio/rebalance-plans/nonexistent/approve",
        json={"idempotency_key": "approve-key-1"},
    )
    assert response.status_code == 404
