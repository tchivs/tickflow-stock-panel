"""Wave 0 HTTP contracts for subject-scoped analysis and trusted reviewer identity."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client():
    from app.analysis.api import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_analysis_router_registers_read_resources_and_explicit_review_actions_only():
    client = _client()
    paths = {route.path for route in client.app.routes}

    assert "/api/analysis/runs" in paths
    assert "/api/analysis/reviews/{review_id}/confirm" in paths
    assert "/api/analysis/reviews/{review_id}/reject" in paths
    assert not any(path.endswith("/reports") and "delete" in path for path in paths)


def test_analysis_api_rejects_reviewer_injected_by_request_json_before_service_call():
    client = _client()

    response = client.post(
        "/api/analysis/reviews/review-1/confirm",
        json={"window_days": 20, "reviewer": "browser-controlled"},
    )

    assert response.status_code == 422


def test_analysis_api_fails_closed_when_server_reviewer_principal_is_unavailable():
    client = _client()

    response = client.post("/api/analysis/reviews/review-1/confirm", json={"window_days": 20})

    assert response.status_code == 503
    assert "reviewer" not in response.text.lower()


def test_analysis_api_does_not_allow_opaque_report_id_to_bypass_subject_scope():
    client = _client()

    response = client.get("/api/analysis/reports/other-subject-report")

    assert response.status_code in {403, 404}
