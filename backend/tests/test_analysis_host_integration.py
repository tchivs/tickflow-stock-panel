"""Authenticated host regression for the governed production analysis path."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _write_phase1_fixture(fixtures_dir: Path) -> None:
    fixtures_dir.mkdir()
    (fixtures_dir / "instruments.json").write_text(
        json.dumps(
            {
                "instruments": [
                    {"symbol": "600000.SH", "name": "浦发银行", "code": "600000", "exchange": "SH"}
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (fixtures_dir / "market-data.json").write_text(
        json.dumps(
            {
                "daily": [
                    {
                        "symbol": "600000.SH",
                        "date": "2024-01-02",
                        "open": 7.10,
                        "high": 7.30,
                        "low": 7.05,
                        "close": 7.25,
                        "volume": 1000.0,
                        "amount": 7250.0,
                        "quote_ts": 1704180600000,
                    }
                ],
                "adjustment_factors": [
                    {"symbol": "600000.SH", "trade_date": "2024-01-02", "adj_factor": 1.0}
                ],
                "financials": [{"symbol": "600000.SH", "report_date": "2023-09-30", "roe": 0.09}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for fixture_file in fixtures_dir.iterdir():
        fixture_file.chmod(0o444)
    fixtures_dir.chmod(0o555)


async def _deterministic_analysis_transport(_messages, **_kwargs):
    return (
        '{"perspectives":[{"name":"fundamental","stance":"supports","score":70,'
        '"rationale":"governed evidence","evidence_ids":["governed-market-data:600000.SH:2024-01-02:close"]},'
        '{"name":"risk","stance":"neutral","score":50,"rationale":"watch",'
        '"evidence_ids":["governed-market-data:600000.SH:2024-01-02:close"]}],'
        '"valuation":{"applicable":false,"method":"not_applicable","conclusion":"insufficient"},'
        '"ic_memo":{"recommendation":"research_only_watch","thesis":"wait","risks":["risk"],'
        '"invalidation_conditions":["conflict"],'
        '"evidence_ids":["governed-market-data:600000.SH:2024-01-02:close"]}}'
    )


def test_authenticated_main_host_completes_governed_analysis_and_persists_immutable_artifacts(
    tmp_path, monkeypatch
):
    from app.analysis import graph as graph_module
    from app.analysis.model_adapter import ConfiguredAnalysisAdapter
    from app.config import settings
    from app.services import auth as auth_service

    fixture_dir = tmp_path / "phase1-fixtures"
    data_dir = tmp_path / "governed-data"
    _write_phase1_fixture(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    import app.config as _cfg
    monkeypatch.setattr(_cfg, "_ENV_FILE", tmp_path / "nonexistent.env")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()
    monkeypatch.setattr(
        graph_module,
        "ConfiguredAnalysisAdapter",
        lambda **_kwargs: ConfiguredAnalysisAdapter(
            provider="test-transport",
            model="test-model",
            generate_text=_deterministic_analysis_transport,
        ),
    )

    from app.main import app

    with TestClient(app) as client:
        unauthenticated = client.post(
            "/api/analysis/runs",
            json={"subject_kind": "instrument", "subject_key": "600000.SH", "focus": "earnings"},
        )
        assert unauthenticated.status_code == 401

        login = client.post("/api/auth/login", json={"password": "host-test-password"})
        assert login.status_code == 200
        assert "tf_session" in login.headers.get("set-cookie", "")

        started = client.post(
            "/api/analysis/runs",
            json={"subject_kind": "instrument", "subject_key": "600000.SH", "focus": "earnings"},
        )
        assert started.status_code == 200
        run = started.json()["run"]
        assert run["status"] == "completed"

        reports = client.get("/api/analysis/subjects/instrument/600000.SH/reports")
        assert reports.status_code == 200
        report = reports.json()["reports"][0]
        assert isinstance(report["id"], str) and report["id"]
        assert report["status"] == "validated"
        assert report["evidence_limitations"]

        detail = client.get(f"/api/analysis/reports/{report['id']}")
        evidence = client.get(f"/api/analysis/reports/{report['id']}/evidence")
        assert detail.status_code == evidence.status_code == 200
        assert detail.json()["report"]["perspectives"]
        assert detail.json()["report"]["signal_id"]
        assert evidence.json()["report_id"] == report["id"]
        assert evidence.json()["sources"]

        signal_id = detail.json()["report"]["signal_id"]
        initial_history = client.get(f"/api/analysis/signals/{signal_id}/history")
        assert initial_history.status_code == 200
        pending_review_id = initial_history.json()["pending_review_id"]
        assert pending_review_id

        confirmed = client.post(f"/api/analysis/reviews/{pending_review_id}/confirm", json={"window_days": 60})
        assert confirmed.status_code == 200
        plan_id = confirmed.json()["plan"]["id"]
        appended = client.post(
            f"/api/analysis/plans/{plan_id}/outcomes",
            json={"status": "complete", "observed_value": 0.12, "notes": "tracked"},
        )
        assert appended.status_code == 200

        rejected = app.state.analysis_repository.append_lifecycle_proposal(
            subject_kind="instrument", subject_key="600000.SH", prior_state="strengthened", proposed_state="weakened",
            evidence={"evidence_ids": ["manual-review"], "evidence": [], "occurred_at": "2026-07-12T00:00:00+00:00"},
        )
        assert client.post(f"/api/analysis/reviews/{rejected['id']}/reject").status_code == 200
        history = client.get(f"/api/analysis/signals/{signal_id}/history")
        assert history.status_code == 200
        payload = history.json()
        assert payload["current_state"] == "strengthened"
        assert payload["pending_review_id"] is None
        assert {review["proposed_state"] for review in payload["reviews"]} >= {"strengthened", "weakened", "rejected"}
        assert payload["plans"][0]["window_days"] == 60
        assert payload["plans"][0]["benchmark"] == "CSI300"
        assert payload["plans"][0]["metric"] == "excess_return"
        assert payload["plans"][0]["outcomes"][0]["outcome"]["status"] == "complete"
