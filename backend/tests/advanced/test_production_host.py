"""Production-lifespan proofs for advanced research routes."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient


def _viewpoint_payload(*, instrument: str) -> dict[str, object]:
    return {
        "source_profile": "operator-research-v1",
        "market_scope": "CN-A",
        "asset_type": "stock",
        "instrument": instrument,
        "published_at": "2026-01-02T00:00:00+00:00",
        "direction": "bullish",
        "conclusion": "受控研究观点",
        "rating": "overweight",
        "target_range": [1500, 1600],
        "horizon_days": 60,
        "confidence": "high",
        "evidence": [{"id": "filing-1"}],
        "evaluation_window_days": 60,
    }


def test_authenticated_main_host_projects_latest_immutable_viewpoint_evaluation(tmp_path, monkeypatch):
    from app.advanced import api as advanced_api
    from app.config import settings
    from app.services import auth as auth_service
    from tests.test_analysis_host_integration import _write_phase1_fixture

    fixture_dir = tmp_path / "phase1-fixtures"
    data_dir = tmp_path / "governed-data"
    _write_phase1_fixture(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    from app.main import app

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"password": "host-test-password"})
        assert login.status_code == 200

        app.state.resolve_advanced_subject_scope = lambda _request: advanced_api.AdvancedSubjectScope(
            frozenset({("instrument", "600000.SH")})
        )
        created = client.post("/api/advanced/viewpoints", json=_viewpoint_payload(instrument="600000.SH"))
        assert created.status_code == 200
        version_id = created.json()["viewpoint"]["id"]
        viewpoint_id = created.json()["viewpoint"]["viewpoint_id"]

        app.state.viewpoint_service.record_evaluation(
            viewpoint_version_id=version_id,
            status="evaluated",
            relative_return=0.02,
            coverage_start=date(2026, 1, 2),
            coverage_end=date(2026, 3, 31),
            governed_input_fingerprint="a" * 64,
        )
        app.state.viewpoint_service.record_evaluation(
            viewpoint_version_id=version_id,
            status="unevaluable",
            reason="missing_benchmark",
            governed_input_fingerprint="b" * 64,
        )

        listed = client.get(f"/api/advanced/viewpoints/{viewpoint_id}/versions")
        assert listed.status_code == 200
        evaluation = listed.json()["versions"][0]["evaluation"]
        assert evaluation == {
            "status": "unevaluable",
            "reason": "missing_benchmark",
            "window_days": 60,
            "benchmark": "000300.SH",
            "relative_return": None,
        }
        assert client.get("/api/advanced/viewpoints?instrument=000001.SZ").status_code == 404
