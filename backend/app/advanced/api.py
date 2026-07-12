"""Narrow advanced API routes with server-derived identity and safe projections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.advanced import projections
from app.advanced.schemas import ViewpointRequest

router = APIRouter(prefix="/api/advanced", tags=["advanced"])


class PromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rationale: str = Field(min_length=10, max_length=4_000)


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: str = Field(pattern="^(approve|reject)$")


class ExperimentSpecificationRequest(BaseModel):
    """Browser input excludes identity, eligibility, and execution authority."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    research_asset_id: str = Field(min_length=1, max_length=128)
    hypothesis: str = Field(min_length=1, max_length=4_000)
    data_scope: dict[str, str] = Field(min_length=1, max_length=16)
    method: str = Field(min_length=1, max_length=256)
    metrics: list[str] = Field(min_length=1, max_length=16)
    success_criteria: dict[str, Any] = Field(min_length=1, max_length=16)
    failure_criteria: dict[str, Any] = Field(min_length=1, max_length=16)


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conclusion: Literal["supported", "refuted", "inconclusive", "needs_replication"]
    notes: str = Field(min_length=1, max_length=4_000)


@dataclass(frozen=True)
class AdvancedSubjectScope:
    """Immutable server-derived subject allowlist for advanced job projections."""

    subjects: frozenset[tuple[str, str]]
    unrestricted_kinds: frozenset[str] = frozenset()

    def allows(self, subject_kind: str, subject_key: str) -> bool:
        return subject_kind in self.unrestricted_kinds or (subject_kind, subject_key) in self.subjects


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


def _service(request: Request, name: str) -> Any:
    service = getattr(request.app.state, name, None)
    if service is None:
        raise HTTPException(status_code=503, detail="advanced service is temporarily unavailable")
    return service


def _require_instrument(request: Request, instrument: object) -> str:
    if not isinstance(instrument, str) or not _scope(request).allows("instrument", instrument):
        raise HTTPException(status_code=404, detail="advanced resource not found")
    return instrument


def _require_research_asset(request: Request, research_asset_id: object) -> str:
    if not isinstance(research_asset_id, str):
        raise HTTPException(status_code=404, detail="advanced experiment not found")
    resolver = getattr(request.app.state, "resolve_advanced_research_asset", None)
    try:
        allowed = resolver(request, research_asset_id) if callable(resolver) else False
    except Exception as error:
        raise HTTPException(status_code=503, detail="advanced authorization is unavailable") from error
    if allowed is not True:
        raise HTTPException(status_code=404, detail="advanced experiment not found")
    return research_asset_id


def _owned_specification(request: Request, specification_id: str) -> dict[str, object]:
    service = _service(request, "experiment_service")
    record = service.get_specification(specification_id)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail="advanced experiment not found")
    owner = record.get("owner_principal")
    if owner is not None and owner != _principal(request):
        raise HTTPException(status_code=404, detail="advanced experiment not found")
    _require_research_asset(request, record.get("research_asset_id"))
    return record


def _owned_run(request: Request, run_id: str) -> dict[str, object]:
    service = _service(request, "experiment_service")
    record = service.get_run(run_id)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail="advanced experiment run not found")
    _owned_specification(request, str(record.get("specification_id") or ""))
    return record


def _safe_value_error(error: ValueError) -> HTTPException:
    message = str(error).lower()
    if any(token in message for token in ("already", "conflict", "state changed", "replay")):
        return HTTPException(status_code=409, detail="advanced state changed; refresh and retry")
    return HTTPException(status_code=400, detail="advanced request cannot be completed")


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
    service = _service(request, "evolution_service")
    try:
        return service.approve(candidate_id=candidate_id, principal=_principal(request), rationale=payload.rationale)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="promotion conflict or incomplete gates") from error


@router.post("/viewpoints")
def create_viewpoint(payload: ViewpointRequest, request: Request) -> dict[str, object]:
    _require_instrument(request, payload.instrument)
    try:
        record = _service(request, "viewpoint_service").create_viewpoint(**payload.model_dump(mode="json"))
    except ValueError as error:
        raise _safe_value_error(error) from error
    return {"viewpoint": projections.viewpoint(record)}


@router.get("/viewpoints/{viewpoint_id}/versions")
def list_viewpoint_versions(viewpoint_id: str, request: Request) -> dict[str, object]:
    service = _service(request, "viewpoint_service")
    records = service.list_versions(viewpoint_id)
    if not isinstance(records, list) or not records:
        raise HTTPException(status_code=404, detail="advanced viewpoint not found")
    _require_instrument(request, records[0].get("instrument") if isinstance(records[0], dict) else None)
    return {"versions": [projections.viewpoint(record) for record in records if isinstance(record, dict)]}


@router.get("/viewpoints/calibration/{source_profile}")
def viewpoint_calibration(source_profile: str, request: Request) -> dict[str, object]:
    _principal(request)
    try:
        return {"calibration": _service(request, "viewpoint_service").calibration(source_profile=source_profile)}
    except ValueError as error:
        raise HTTPException(status_code=404, detail="advanced viewpoint calibration not found") from error


@router.post("/experiments/specifications")
def create_experiment_specification(payload: ExperimentSpecificationRequest, request: Request) -> dict[str, object]:
    _require_research_asset(request, payload.research_asset_id)
    try:
        record = _service(request, "experiment_service").create_specification(
            **payload.model_dump(), owner_principal=_principal(request)
        )
    except ValueError as error:
        raise _safe_value_error(error) from error
    return {"specification": record}


@router.get("/experiments/specifications/{specification_id}")
def experiment_specification(specification_id: str, request: Request) -> dict[str, object]:
    return {"specification": _owned_specification(request, specification_id)}


@router.post("/experiments/runs/{run_id}/feedback")
def append_experiment_feedback(run_id: str, payload: FeedbackRequest, request: Request) -> dict[str, object]:
    _owned_run(request, run_id)
    try:
        record = _service(request, "experiment_service").record_feedback(
            run_id=run_id, conclusion=payload.conclusion, notes=payload.notes
        )
    except ValueError as error:
        raise _safe_value_error(error) from error
    return {"feedback": record}


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
