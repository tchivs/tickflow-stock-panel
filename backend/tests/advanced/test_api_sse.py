"""RED contracts for safe advanced API projections and scoped SSE delivery."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


class FakeAdvancedService:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.resume_calls: list[dict[str, object]] = []
        self.jobs = {
            "owned-job": {
                "id": "owned-job",
                "principal": "server-principal",
                "subject_kind": "instrument",
                "subject_key": "600519.SH",
                "status": "awaiting_review",
                "stage": "awaiting_review",
                "stage_recorded_at": "2026-07-12T00:00:00+00:00",
                "audit_reference": "audit-allowed",
                "authorization_token_hash": "must-not-project",
                "policy_fingerprint": "must-not-project",
                "provider_output": "must-not-project",
                "source_code": "must-not-project",
                "sandbox_path": "/private/must-not-project",
                "diagnostics": "must-not-project",
            },
            "other-job": {
                "id": "other-job",
                "principal": "other-server-principal",
                "subject_kind": "instrument",
                "subject_key": "000001.SZ",
                "status": "recorded",
                "stage": "recorded",
                "stage_recorded_at": "2026-07-12T00:00:00+00:00",
                "audit_reference": "audit-other",
            },
        }

    def get_job(self, job_id: str):
        return self.jobs.get(job_id)

    def create_job(self, *, principal: str, request: dict[str, object]):
        self.create_calls.append({"principal": principal, "request": request})
        return self.jobs["owned-job"]

    def resume(self, *, principal: str, job_id: str, decision: str):
        self.resume_calls.append({"principal": principal, "job_id": job_id, "decision": decision})
        return self.jobs[job_id]

    def get_audit(self, audit_reference: str):
        return {
            "reference": audit_reference,
            "decision": "rejected",
            "reason": "scope_denied",
            "authorization_token_hash": "must-not-project",
            "policy_fingerprint": "must-not-project",
            "raw_provider_output": "must-not-project",
            "source_code": "must-not-project",
            "sandbox_path": "/private/must-not-project",
            "diagnostics": "must-not-project",
        }


def _client(*, allowed_subjects=frozenset({("instrument", "600519.SH")})) -> tuple[TestClient, FakeAdvancedService]:
    from app.advanced import api as advanced_api
    from app.advanced.api import AdvancedSubjectScope

    service = FakeAdvancedService()
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.advanced_job_service = service
    app.state.resolve_advanced_subject_scope = lambda _request: AdvancedSubjectScope(allowed_subjects)

    @app.middleware("http")
    async def server_principal(request: Request, call_next):
        request.state.reviewer_principal = "server-principal"
        return await call_next(request)

    return TestClient(app), service


def test_advanced_api_requires_server_principal_and_subject_ownership_before_read_or_resume():
    client, service = _client()

    cross_scope_read = client.get("/api/advanced/jobs/other-job")
    cross_scope_audit = client.get("/api/advanced/audits/audit-other")
    cross_scope_resume = client.post("/api/advanced/jobs/other-job/resume", json={"decision": "approve"})
    injected_principal = client.post(
        "/api/advanced/jobs/owned-job/resume",
        json={"decision": "approve", "principal": "browser-controlled"},
    )

    assert cross_scope_read.status_code in {403, 404}
    assert cross_scope_audit.status_code in {403, 404}
    assert cross_scope_resume.status_code in {403, 404}
    assert injected_principal.status_code == 422
    assert service.resume_calls == []


def test_opaque_ids_never_bypass_scope_and_authorized_status_uses_an_allowlisted_projection():
    client, _service = _client()

    allowed = client.get("/api/advanced/jobs/owned-job")
    denied = client.get("/api/advanced/jobs/other-job")

    assert allowed.status_code == 200
    assert denied.status_code in {403, 404}
    assert allowed.json() == {
        "job": {
            "id": "owned-job",
            "subject": {"kind": "instrument", "key": "600519.SH"},
            "status": "awaiting_review",
            "stage": "awaiting_review",
            "stage_recorded_at": "2026-07-12T00:00:00+00:00",
            "audit_reference": "audit-allowed",
        }
    }
    for forbidden in (
        "authorization_token",
        "policy",
        "provider_output",
        "source_code",
        "sandbox_path",
        "diagnostics",
        "principal",
    ):
        assert forbidden not in allowed.text


def test_rejection_responses_and_audit_projections_are_safe_and_never_attach_sse_work():
    client, service = _client()

    rejected = client.post(
        "/api/advanced/jobs",
        json={
            "authorization_token": "opaque-token",
            "task_type": "research_draft",
            "market": "CN-A",
            "instrument": "000001.SZ",
            "idempotency_key": "denied-request",
        },
    )
    audit = client.get("/api/advanced/audits/audit-allowed")

    assert rejected.status_code in {403, 404, 409, 429}
    assert service.create_calls == []
    assert audit.status_code == 200
    assert audit.json() == {
        "audit": {
            "reference": "audit-allowed",
            "decision": "rejected",
            "reason": "scope_denied",
        }
    }
    for forbidden in ("token", "policy", "provider", "source", "path", "diagnostic"):
        assert forbidden not in audit.text.lower()


def test_advanced_progress_is_committed_allowlisted_and_filtered_before_subscriber_queueing():
    from app.advanced.api import AdvancedSubjectScope
    from app.services.quote_service import QuoteService

    quote_service = QuoteService()
    allowed = quote_service.subscribe(
        advanced_scope=AdvancedSubjectScope(frozenset({("instrument", "600519.SH")}))
    )
    denied = quote_service.subscribe(
        advanced_scope=AdvancedSubjectScope(frozenset({("instrument", "000001.SZ")}))
    )

    quote_service.notify_advanced_progress(
        job_id="owned-job",
        subject_kind="instrument",
        subject_key="600519.SH",
        stage="awaiting_review",
        occurred_at="2026-07-12T00:00:00+00:00",
        committed=True,
        human_label="Awaiting review",
        audit_reference="audit-allowed",
    )
    quote_service.notify_advanced_progress(
        job_id="owned-job",
        subject_kind="instrument",
        subject_key="600519.SH",
        stage="drafted",
        occurred_at="2026-07-12T00:00:01+00:00",
        committed=False,
        human_label="Uncommitted draft",
        audit_reference="audit-allowed",
    )

    assert allowed.pop()["advanced_progress"] == [{
        "job_id": "owned-job",
        "subject_kind": "instrument",
        "subject_key": "600519.SH",
        "stage": "awaiting_review",
        "label": "Awaiting review",
        "occurred_at": "2026-07-12T00:00:00+00:00",
        "audit_reference": "audit-allowed",
    }]
    assert denied.pop()["advanced_progress"] == []
