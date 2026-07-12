"""Narrow advanced API routes with server-derived identity and safe projections."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.advanced import projections

router = APIRouter(prefix="/api/advanced", tags=["advanced"])


class PromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rationale: str = Field(min_length=10, max_length=4_000)


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: str = Field(pattern="^(approve|reject)$")


@dataclass(frozen=True)
class AdvancedSubjectScope:
    """Immutable server-derived subject allowlist for advanced job projections."""

    subjects: frozenset[tuple[str, str]]

    def allows(self, subject_kind: str, subject_key: str) -> bool:
        return (subject_kind, subject_key) in self.subjects


def _scope(request: Request) -> AdvancedSubjectScope:
    resolver = getattr(request.app.state, "resolve_advanced_subject_scope", None)
    if not callable(resolver):
        raise HTTPException(status_code=503, detail="advanced authorization is unavailable")
    try:
        scope = resolver(request)
    except Exception as error:
        raise HTTPException(status_code=503, detail="advanced authorization is unavailable") from error
    if not callable(getattr(scope, "allows", None)):
        raise HTTPException(status_code=503, detail="advanced authorization is unavailable")
    return scope


def _principal(request: Request) -> str:
    principal = getattr(request.state, "reviewer_principal", None)
    if not isinstance(principal, str) or not principal:
        raise HTTPException(status_code=503, detail="advanced authorization is unavailable")
    return principal


def _owned_job(request: Request, job_id: str) -> dict[str, object]:
    service = getattr(request.app.state, "advanced_job_service", None)
    record = service.get_job(job_id) if service is not None else None
    scope = _scope(request)
    if not isinstance(record, dict) or str(record.get("principal")) != _principal(request):
        raise HTTPException(status_code=404, detail="advanced job not found")
    if not scope.allows(str(record.get("subject_kind")), str(record.get("subject_key"))):
        raise HTTPException(status_code=404, detail="advanced job not found")
    return record


def _audit_is_in_scope(request: Request, reference: str) -> bool:
    service = getattr(request.app.state, "advanced_job_service", None)
    scope = _scope(request)
    principal = _principal(request)
    # Production services should expose this indexed repository lookup. The bounded
    # fixture fallback keeps the same ownership check without accepting a browser scope.
    lookup = getattr(service, "get_job_by_audit_reference", None)
    record = lookup(reference) if callable(lookup) else None
    if record is None:
        records = getattr(service, "jobs", {}).values()
        record = next((item for item in records if item.get("audit_reference") == reference), None)
    return isinstance(record, dict) and str(record.get("principal")) == principal and scope.allows(
        str(record.get("subject_kind")), str(record.get("subject_key"))
    )


@router.post("/evolution/candidates/{candidate_id}/promote")
def promote_candidate(candidate_id: str, payload: PromotionRequest, request: Request) -> dict[str, object]:
    service = request.app.state.evolution_service
    principal = getattr(request.state, "reviewer_principal", None)
    try:
        return service.approve(candidate_id=candidate_id, principal=principal, rationale=payload.rationale)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="promotion conflict or incomplete gates") from error


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, object]:
    return {"job": projections.job(_owned_job(request, job_id))}


@router.post("/jobs")
def create_job(payload: dict[str, object], request: Request) -> dict[str, object]:
    scope = _scope(request)
    instrument = payload.get("instrument")
    if not isinstance(instrument, str) or not scope.allows("instrument", instrument):
        raise HTTPException(status_code=404, detail="advanced job not found")
    service = getattr(request.app.state, "advanced_job_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="advanced authorization is unavailable")
    try:
        return {"job": projections.job(service.create_job(principal=_principal(request), request=payload))}
    except ValueError as error:
        raise HTTPException(status_code=409, detail="advanced job rejected") from error


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, payload: ResumeRequest, request: Request) -> dict[str, object]:
    _owned_job(request, job_id)
    service = request.app.state.advanced_job_service
    try:
        return {"job": projections.job(service.resume(principal=_principal(request), job_id=job_id, decision=payload.decision))}
    except ValueError as error:
        raise HTTPException(status_code=409, detail="advanced job conflict") from error


@router.get("/audits/{audit_reference}")
def get_audit(audit_reference: str, request: Request) -> dict[str, object]:
    if not _audit_is_in_scope(request, audit_reference):
        raise HTTPException(status_code=404, detail="advanced audit not found")
    service = request.app.state.advanced_job_service
    record = service.get_audit(audit_reference)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail="advanced audit not found")
    return {"audit": projections.audit(record)}
