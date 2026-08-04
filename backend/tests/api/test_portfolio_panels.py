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
