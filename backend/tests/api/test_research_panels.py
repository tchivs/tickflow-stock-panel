"""Research panel route scaffold tests (Wave 0 / 15-02).

These tests verify the routes register and return 200 on empty lists.

15-03 (breadth) extends these with fixture-data cases.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_factors_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/factors")
    assert response.status_code == 200
    assert response.json() == []


def test_list_models_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/models")
    assert response.status_code == 200


def test_list_wf_plans_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/plans")
    assert response.status_code == 200
    assert response.json() == []


def test_list_wf_folds_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/folds")
    assert response.status_code == 200


def test_list_wf_search_runs_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/search-runs")
    assert response.status_code == 200


def test_list_wf_validated_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/validated")
    assert response.status_code == 200


def test_list_wf_ensembles_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/ensembles")
    assert response.status_code == 200


def test_get_admission_verdict_not_found(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/factors/nonexistent/verdict")
    assert response.status_code == 404


def test_factor_revision_dto_rejects_extra_fields() -> None:
    """Strict DTO: extra field is forbidden."""
    from app.contracts.panels import FactorRevisionDTO
    from pydantic import ValidationError

    import pytest as _pytest

    minimal = {
        "id": "rev-1",
        "factor_id": "fac-1",
        "revision_number": 1,
        "name": "test",
        "expression": "close",
        "status": "admitted",
        "created_at": "2026-01-01T00:00:00Z",
        "bogus_field": "should fail",
    }
    with _pytest.raises(ValidationError):
        FactorRevisionDTO(**minimal)
