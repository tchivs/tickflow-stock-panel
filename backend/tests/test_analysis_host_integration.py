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
        snapshot = app.state.analysis_repository.get_frozen_snapshot(run["id"])
        assert snapshot is not None
        assert snapshot["context_status"] == "ready"
        assert report["report"]["run_id"] == run["id"]
        assert report["report"]["evidence_snapshot"]["sources"]
