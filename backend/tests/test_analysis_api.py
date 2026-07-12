"""Wave 0 HTTP contracts for subject-scoped analysis and trusted reviewer identity."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analysis.api import SubjectScope


class _Repository:
    def __init__(self):
        self.reports = {
            "allowed-report": {
                "id": "allowed-report",
                "run_id": "allowed-run",
                "subject_kind": "instrument",
                "subject_key": "600519.SH",
                "version": 2,
                "created_at": "2026-07-12T00:00:00+00:00",
                "report": {
                    "generated": {
                        "perspectives": [{
                            "name": "fundamental", "stance": "supports", "score": 70,
                            "rationale": "governed rationale", "evidence_ids": ["source-a"],
                        }],
                        "valuation": {
                            "applicable": False, "method": "not_applicable", "conclusion": "insufficient inputs",
                            "evidence_ids": [],
                        },
                        "ic_memo": {
                            "recommendation": "watch", "thesis": "watch evidence", "risks": ["risk"],
                            "invalidation_conditions": ["condition"], "evidence_ids": ["source-a"],
                        },
                    },
                    "evidence_snapshot": {
                        "context_status": "ready",
                        "sources": [{"source_id": "source-a", "grade": "A"}],
                        "material_numbers": [],
                    },
                },
            },
            "other-subject-report": {"id": "other-subject-report", "run_id": "other-run", "subject_kind": "instrument", "subject_key": "000001.SZ"},
        }
        self.reviews = {"review-1": {"id": "review-1", "signal_id": "allowed-signal"}}
        self.signals = {
            "allowed-signal": {"id": "allowed-signal", "subject_kind": "instrument", "subject_key": "600519.SH"},
            "other-signal": {"id": "other-signal", "subject_kind": "instrument", "subject_key": "000001.SZ"},
        }

    def list_reports(self, subject_kind, subject_key):
        return [report for report in self.reports.values() if (report["subject_kind"], report["subject_key"]) == (subject_kind, subject_key)]

    def get_report(self, report_id):
        return self.reports.get(report_id)

    def get_frozen_snapshot(self, run_id):
        return {
            "run_id": run_id,
            "snapshot": {
                "context_status": "ready",
                "sources": [{
                    "source_id": "source-a", "grade": "A", "origin": "exchange", "independence_group": "exchange",
                    "retrieved_at": "2026-07-12T00:00:00+00:00", "period": "2026-Q1", "definition": "revenue",
                    "provenance": {"source_locator": "source://allowed"},
                }],
                "material_numbers": [{
                    "number_id": "revenue", "source_id": "source-a", "value": 100.0, "unit": "CNY_million",
                    "period": "2026-Q1", "definition": "revenue", "status": "confirmed",
                    "peer_source_ids": ["source-b"], "comparison_reason": "independent match",
                }],
            },
        }

    def get_lifecycle_review(self, review_id):
        return self.reviews.get(review_id)

    def get_signal(self, signal_id):
        return self.signals.get(signal_id)

    def list_events(self, *, subject_kind, subject_key):
        return [{
            "next_state": "strengthened", "occurred_at": "2026-07-12T00:00:00+00:00",
            "review_id": "review-1", "signal_id": "allowed-signal",
        }]

    def list_lifecycle_reviews(self, *, subject_kind, subject_key):
        return [{
            "id": "review-1", "signal_id": "allowed-signal", "prior_state": "active", "proposed_state": "strengthened",
            "evidence_ids": ["source-a"], "rationale": "governed proposal", "created_at": "2026-07-12T00:00:00+00:00",
        }]

    def list_observation_plans(self, review_id):
        return [{
            "id": "plan-1", "review_id": review_id, "window_days": 60, "benchmark": "CSI300",
            "metric": "excess_return", "created_at": "2026-07-12T00:00:00+00:00",
        }]

    def list_observation_outcomes(self, plan_id):
        return [{
            "id": "outcome-1", "plan_id": plan_id, "observed_at": "2026-09-12T00:00:00+00:00",
            "outcome": {"status": "complete", "observed_value": 0.12},
        }]

    def get_observation_plan_subject(self, plan_id):
        return None


class _Service:
    async def start_run(self, *, subject_kind, subject_key, focus):
        return {"id": "allowed-run", "subject_kind": subject_kind, "subject_key": subject_key, "focus": focus, "status": "queued"}


class _Lifecycle:
    def __init__(self):
        self.confirmed_with = None

    def confirm(self, **kwargs):
        self.confirmed_with = kwargs["session_token"]
        return {"official_state": "weakened"}

    def reject(self, **kwargs):
        self.confirmed_with = kwargs["session_token"]
        return {"official_state": "active"}


def _client(*, principal="reviewer-server-principal"):
    from app.analysis.api import router

    app = FastAPI()
    app.include_router(router)
    app.state.analysis_repository = _Repository()
    app.state.analysis_service = _Service()
    app.state.lifecycle_rule_service = _Lifecycle()
    app.state.resolve_analysis_subject_scope = lambda _request: SubjectScope(frozenset({("instrument", "600519.SH")}))

    @app.middleware("http")
    async def reviewer_context(request, call_next):
        request.state.reviewer_principal = principal
        return await call_next(request)

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
    client = _client(principal=None)

    response = client.post("/api/analysis/reviews/review-1/confirm", json={"window_days": 20})

    assert response.status_code == 503
    assert "principal" not in response.text.lower()
    assert client.app.state.lifecycle_rule_service.confirmed_with is None


def test_analysis_api_does_not_allow_opaque_report_id_to_bypass_subject_scope():
    client = _client()

    response = client.get("/api/analysis/reports/other-subject-report")

    assert response.status_code in {403, 404}


def test_analysis_api_authorizes_subject_before_start_reads_and_review_writes():
    client = _client()

    assert client.post("/api/analysis/runs", json={"subject_kind": "instrument", "subject_key": "000001.SZ"}).status_code == 404
    assert client.get("/api/analysis/subjects/instrument/000001.SZ/reports").status_code == 404
    assert client.get("/api/analysis/signals/other-signal/history").status_code == 404

    run = client.post("/api/analysis/runs", json={"subject_kind": "instrument", "subject_key": "600519.SH", "focus": "risk"})
    assert run.status_code == 200
    assert run.json()["run"]["status"] == "queued"

    confirmed = client.post("/api/analysis/reviews/review-1/confirm", json={"window_days": 60})
    assert confirmed.status_code == 200
    assert client.app.state.lifecycle_rule_service.confirmed_with == "reviewer-server-principal"


def test_analysis_api_returns_allowlisted_report_evidence_and_lifecycle_display_dtos():
    client = _client()

    reports = client.get("/api/analysis/subjects/instrument/600519.SH/reports")
    detail = client.get("/api/analysis/reports/allowed-report")
    evidence = client.get("/api/analysis/reports/allowed-report/evidence")
    history = client.get("/api/analysis/signals/allowed-signal/history")

    assert reports.status_code == detail.status_code == evidence.status_code == history.status_code == 200
    summary = reports.json()["reports"][0]
    assert summary == {
        "id": "allowed-report", "subject": {"kind": "instrument", "key": "600519.SH"}, "version": 2,
        "status": "validated", "generated_at": "2026-07-12T00:00:00+00:00", "evidence_limitations": [],
    }
    displayed_report = detail.json()["report"]
    assert displayed_report["signal_id"] == "allowed-signal"
    assert displayed_report["perspectives"] == [{
        "name": "fundamental", "conclusion": "governed rationale", "evidence_count": 1, "limitations": [],
    }]
    assert displayed_report["score"]["dimensions"][0]["rationale"] == "governed rationale"
    assert displayed_report["valuation"] == {"applicable": False, "reason": "insufficient inputs", "method": "not_applicable", "limitations": []}
    assert displayed_report["ic_memo"]["thesis"] == "watch evidence"
    assert "report_json" not in detail.text and "snapshot_json" not in detail.text and "prompt" not in detail.text

    displayed_evidence = evidence.json()["evidence"]
    assert displayed_evidence["report_id"] == "allowed-report"
    assert displayed_evidence["sources"][0]["reference"] == "source://allowed"
    assert displayed_evidence["material_numbers"][0] == {
        "id": "revenue", "label": "revenue", "value": 100.0, "unit": "CNY_million", "period": "2026-Q1",
        "source_count": 2, "cross_check": "confirmed", "difference_reason": "independent match",
    }

    displayed_history = history.json()
    assert displayed_history["signal_id"] == "allowed-signal"
    assert displayed_history["current_state"] == "strengthened"
    assert displayed_history["pending_review_id"] is None
    assert displayed_history["reviews"][0]["id"] == "review-1"
    assert displayed_history["plans"][0]["window_days"] == 60
    assert displayed_history["plans"][0]["outcomes"][0]["outcome"]["status"] == "complete"
    assert "reviewer_principal" not in history.text


def test_main_registers_analysis_domain_without_replacing_analysis_menus_router():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/analysis/runs" in paths
    assert "/api/analysis-menus" in paths


def test_analysis_progress_is_limited_to_the_server_bound_subscriber_scope():
    from app.services.quote_service import QuoteService

    service = QuoteService()
    allowed = service.subscribe(analysis_scope=SubjectScope(frozenset({("instrument", "600519.SH")})))
    denied = service.subscribe(analysis_scope=SubjectScope(frozenset({("instrument", "000001.SZ")})))

    service.notify_analysis_progress(
        run_id="run-600519", subject_kind="instrument", subject_key="600519.SH", status="completed"
    )

    assert allowed.pop()["analysis_progress"] == [{
        "run_id": "run-600519", "subject_kind": "instrument", "subject_key": "600519.SH", "status": "completed",
    }]
    assert denied.pop()["analysis_progress"] == []

    service._broadcast_quote_updated()
    assert allowed.pop()["quote_updated"] is True
    assert denied.pop()["quote_updated"] is True
