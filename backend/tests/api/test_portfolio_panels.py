"""Portfolio panel route scaffold tests (Wave 0 / 15-02).

These tests verify the routes register, return 200 on empty lists, return
404 on missing entities, and that the strict DTO rejects extra fields.

15-01 (tracer) extends these with fixture-data end-to-end cases.
15-04 (breadth) extends attribution + rebalance cases.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


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

    import pytest as _pytest

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
    with _pytest.raises(ValidationError):
        OptimizationRunDTO(**minimal)
