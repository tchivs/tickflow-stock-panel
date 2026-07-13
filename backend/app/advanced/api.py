"""Narrow advanced API routes with server-derived identity and safe projections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.advanced import projections
from app.advanced.schemas import (
    CustomStrategySubmission,
    ViewpointCorrectionRequest,
    ViewpointRequest,
    ViewpointRevisionRequest,
)

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


class SessionBoundJobStartRequest(BaseModel):
    """The browser selects only an allowlisted task type for an existing object."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_type: Literal["research_draft", "experiment", "strategy_evaluation"]


class ViewpointEvaluationRequest(BaseModel):
    """Evaluation authority is fully lifecycle-owned; the browser sends no inputs."""

    model_config = ConfigDict(extra="forbid")


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


def _owned_candidate(request: Request, candidate_id: str) -> dict[str, object]:
    service = _service(request, "evolution_service")
    candidate = service.get_candidate(candidate_id)
    if not isinstance(candidate, dict):
        raise HTTPException(status_code=404, detail="advanced candidate not found")
    _require_research_asset(request, candidate.get("parent_research_asset_id"))
    return candidate


def _safe_value_error(error: ValueError) -> HTTPException:
    message = str(error).lower()
    if any(token in message for token in ("already", "conflict", "state changed", "replay")):
        return HTTPException(status_code=409, detail="advanced state changed; refresh and retry")
    return HTTPException(status_code=400, detail="advanced request cannot be completed")


def _owned_viewpoint_version(request: Request, viewpoint_version_id: str) -> dict[str, object]:
    service = _service(request, "viewpoint_service")
    record = service.get_viewpoint_version(viewpoint_version_id)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail="advanced viewpoint not found")
    _require_instrument(request, record.get("instrument"))
    return record


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
    _owned_candidate(request, candidate_id)
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


@router.post("/viewpoints/{viewpoint_id}/revisions")
def revise_viewpoint(viewpoint_id: str, payload: ViewpointRevisionRequest, request: Request) -> dict[str, object]:
    service = _service(request, "viewpoint_service")
    records = service.list_versions(viewpoint_id)
    if not isinstance(records, list) or not records:
        raise HTTPException(status_code=404, detail="advanced viewpoint not found")
    _require_instrument(request, records[0].get("instrument") if isinstance(records[0], dict) else None)
    try:
        record = service.revise_viewpoint(
            viewpoint_id=viewpoint_id, **payload.model_dump(mode="json", exclude_none=True)
        )
    except ValueError as error:
        raise _safe_value_error(error) from error
    return {"viewpoint": projections.viewpoint(record)}


@router.post("/viewpoints/{viewpoint_id}/corrections")
def correct_viewpoint(viewpoint_id: str, payload: ViewpointCorrectionRequest, request: Request) -> dict[str, object]:
    service = _service(request, "viewpoint_service")
    records = service.list_versions(viewpoint_id)
    if not isinstance(records, list) or not records:
        raise HTTPException(status_code=404, detail="advanced viewpoint not found")
    _require_instrument(request, records[0].get("instrument") if isinstance(records[0], dict) else None)
    changes = payload.model_dump(mode="json", exclude_none=True, exclude={"correction_reason"})
    try:
        record = service.correct_viewpoint(
            viewpoint_id=viewpoint_id, correction_reason=payload.correction_reason, **changes
        )
    except ValueError as error:
        raise _safe_value_error(error) from error
    return {"viewpoint": projections.viewpoint(record)}


@router.post("/viewpoints/versions/{viewpoint_version_id}/evaluate")
def evaluate_viewpoint(
    viewpoint_version_id: str, payload: ViewpointEvaluationRequest, request: Request
) -> dict[str, object]:
    del payload
    version = _owned_viewpoint_version(request, viewpoint_version_id)
    service = _service(request, "viewpoint_service")
    try:
        service.evaluate_viewpoint(
            viewpoint_version_id=viewpoint_version_id,
            market_snapshot=_service(request, "viewpoint_market_snapshot"),
        )
    except ValueError as error:
        raise _safe_value_error(error) from error
    records = service.list_versions(str(version["viewpoint_id"]))
    record = next(
        (item for item in records if isinstance(item, dict) and item.get("id") == viewpoint_version_id),
        None,
    )
    if record is None:
        raise HTTPException(status_code=409, detail="advanced state changed; refresh and retry")
    return {"viewpoint": projections.viewpoint(record)}


@router.get("/viewpoints")
def list_viewpoints(instrument: str, request: Request) -> dict[str, object]:
    """List immutable research facts only after server-side object authorization."""

    _require_instrument(request, instrument)
    records = _service(request, "viewpoint_service").list_for_instrument(instrument)
    return {"viewpoints": [projections.viewpoint(record) for record in records if isinstance(record, dict)]}


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
    return {"specification": projections.experiment_specification(_owned_specification(request, specification_id))}


@router.get("/experiments")
def list_experiments(request: Request) -> dict[str, object]:
    """List only server-owned specifications, runs, and append-only feedback."""
    service = _service(request, "experiment_service")
    principal = _principal(request)
    specifications = getattr(service, "list_specifications", lambda: [])()
    visible_specs = [
        record for record in specifications
        if isinstance(record, dict)
        and record.get("owner_principal") == principal
        and _research_asset_allowed(request, record.get("research_asset_id"))
    ]
    visible_ids = {str(record["id"]) for record in visible_specs}
    runs = getattr(service, "list_runs", lambda: [])()
    visible_runs = [record for record in runs if isinstance(record, dict) and str(record.get("specification_id")) in visible_ids]
    feedback = [
        item for run in visible_runs
        for item in getattr(service, "list_feedback", lambda **_: [])(run_id=str(run["id"]))
        if isinstance(item, dict)
    ]
    return {
        "specifications": [projections.experiment_specification(record) for record in visible_specs],
        "runs": [projections.experiment_run(record) for record in visible_runs],
        "feedback": [projections.experiment_feedback(record) for record in feedback],
    }


def _research_asset_allowed(request: Request, asset_id: object) -> bool:
    try:
        _require_research_asset(request, asset_id)
    except HTTPException:
        return False
    return True


@router.post("/experiments/specifications/{specification_id}/runs")
def run_experiment(specification_id: str, request: Request) -> dict[str, object]:
    _owned_specification(request, specification_id)
    try:
        run = _service(request, "experiment_service").run_specification(specification_id=specification_id)
    except ValueError as error:
        raise _safe_value_error(error) from error
    return {"run": projections.experiment_run(run)}


@router.post("/experiments/runs/{run_id}/retry")
def retry_experiment(run_id: str, request: Request) -> dict[str, object]:
    _owned_run(request, run_id)
    try:
        run = _service(request, "experiment_service").retry_run(run_id=run_id)
    except ValueError as error:
        raise _safe_value_error(error) from error
    return {"run": projections.experiment_run(run)}


@router.post("/experiments/runs/{run_id}/feedback")
def append_experiment_feedback(run_id: str, payload: FeedbackRequest, request: Request) -> dict[str, object]:
    _owned_run(request, run_id)
    try:
        record = _service(request, "experiment_service").record_feedback(
            run_id=run_id, conclusion=payload.conclusion, notes=payload.notes
        )
    except ValueError as error:
        raise _safe_value_error(error) from error
    return {"feedback": projections.experiment_feedback(record)}


@router.get("/evolution/candidates")
def list_candidates(request: Request) -> dict[str, object]:
    service = _service(request, "evolution_service")
    records = [
        record for record in service.list_candidates()
        if _research_asset_allowed(request, record.get("parent_research_asset_id"))
    ]
    return {"candidates": [projections.candidate(record, service.list_gates(candidate_id=str(record["id"]))) for record in records]}


@router.post("/sandbox/submissions")
def submit_custom_strategy(payload: CustomStrategySubmission, request: Request) -> dict[str, object]:
    """Admit only a same-request, hash-bound strategy through the fail-closed sandbox."""

    _require_research_asset(request, payload.contract.parent_asset_id)
    service = _service(request, "advanced_sandbox_service")
    try:
        result = service.submit(payload.model_dump(mode="python"))
        run_id = result.get("run_id") if isinstance(result, dict) else None
        if isinstance(run_id, str):
            return {"run": service.public_run(run_id)}
        audit_reference = result.get("audit_reference") if isinstance(result, dict) else None
        if not isinstance(audit_reference, str):
            raise ValueError("sandbox did not retain a safe audit reference")
        return {"validation": projections.sandbox_validation(service.public_validation(audit_reference))}
    except ValueError as error:
        raise _safe_value_error(error) from error


def _owned_sandbox_run(request: Request, run_id: str) -> dict[str, object]:
    service = _service(request, "advanced_sandbox_service")
    record = service.sandbox_run(run_id)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail="advanced sandbox run not found")
    _require_research_asset(request, record.get("parent_asset_id"))
    _principal(request)
    return record


@router.get("/sandbox/runs")
def list_sandbox_runs(request: Request) -> dict[str, object]:
    """List only terminal runs whose persisted parent asset remains server-authorized."""
    service = _service(request, "advanced_sandbox_service")
    _principal(request)
    records = [
        record
        for record in service.sandbox_runs()
        if isinstance(record, dict) and _research_asset_allowed(request, record.get("parent_asset_id"))
    ]
    return {"runs": [projections.sandbox_run(record) for record in records]}


@router.get("/sandbox/runs/{run_id}")
def get_sandbox_run(run_id: str, request: Request) -> dict[str, object]:
    return {"run": projections.sandbox_run(_owned_sandbox_run(request, run_id))}


@router.get("/sandbox/validations")
def list_sandbox_validations(request: Request) -> dict[str, object]:
    """Sandbox records lack reusable browser authority; expose only server-held audit projections."""
    _principal(request)
    service = _service(request, "advanced_sandbox_service")
    return {"validations": [projections.sandbox_validation(record) for record in service.list_audits()]}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, object]:
    return {"job": projections.job(_owned_job(request, job_id))}


@router.post("/subjects/{instrument}/jobs")
async def create_session_bound_job(instrument: str, payload: SessionBoundJobStartRequest, request: Request) -> dict[str, object]:
    """Derive all authorization, scope, market, and idempotency data on the server."""

    scope = _scope(request)
    if not scope.allows("instrument", instrument):
        raise HTTPException(status_code=404, detail="advanced job not found")
    service = getattr(request.app.state, "advanced_job_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="advanced authorization is unavailable")
    try:
        created = service.create_session_bound_job(
            principal=_principal(request), task_type=payload.task_type, instrument=instrument
        )
        runner = getattr(service, "run_authorized_job", None)
        if not callable(runner):
            return {"job": projections.job(created)}
        return {"job": projections.job(await runner(job_id=str(created["id"]))) }
    except ValueError as error:
        raise HTTPException(status_code=409, detail="advanced job rejected") from error


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, payload: ResumeRequest, request: Request) -> dict[str, object]:
    _owned_job(request, job_id)
    service = request.app.state.advanced_job_service
    resume = getattr(service, "resume", None)
    if not callable(resume):
        raise HTTPException(status_code=503, detail="advanced workflow resume is temporarily unavailable")
    try:
        return {"job": projections.job(resume(principal=_principal(request), job_id=job_id, decision=payload.decision))}
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
