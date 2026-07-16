"""Authenticated, object-authorized Shadow workflow API."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.shadow import projections
from app.shadow.evaluation import ShadowEvaluationError
from app.shadow.importer import ShadowImportError
from app.shadow.repository import ShadowEvidenceError, ShadowRepositoryError
from app.shadow.schemas import EvidenceExclusion, ImportMapping
from app.shadow.service import ShadowRetentionError

router = APIRouter(prefix="/api/shadow", tags=["shadow"])
_MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class StrictShadowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceSetCreateRequest(StrictShadowRequest):
    included_batch_ids: list[str] = Field(min_length=1, max_length=128)
    included_trade_ids: list[str] = Field(max_length=100_000)
    exclusions: list[EvidenceExclusion] = Field(max_length=100_000)


class DistillRequest(StrictShadowRequest):
    feature_names: list[
        Literal["close_return_5d", "volume_ratio_20d", "intraday_range"]
    ] = Field(min_length=1, max_length=3)
    seed: int
    max_depth: int = Field(ge=1, le=3)
    min_leaf_support: int = Field(ge=2, le=10_000)
    exit_assumptions: dict[str, object]
    holding_assumptions: dict[str, object]


class DateWindow(StrictShadowRequest):
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class CostPolicy(StrictShadowRequest):
    commission_bps: float = Field(ge=0, le=10_000)
    slippage_bps: float = Field(ge=0, le=10_000)
    stamp_duty_bps: float = Field(ge=0, le=10_000)


class EvaluationRequest(StrictShadowRequest):
    in_sample_window: DateWindow
    out_of_sample_window: DateWindow
    split_policy: Literal["chronological"] = "chronological"
    adjustment_policy: str = Field(min_length=1, max_length=256)
    cost_policy: CostPolicy


class RetainRequest(StrictShadowRequest):
    in_sample_evaluation_id: str = Field(min_length=1, max_length=128)
    out_of_sample_evaluation_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=10, max_length=4_000)


def _unavailable(request: Request) -> HTTPException:
    status = getattr(request.app.state, "shadow_module_status", None)
    if not isinstance(status, Mapping):
        status = {
            "available": False,
            "code": "shadow_unavailable",
            "reason": "Shadow optional service is unavailable",
            "install_hint": "enable the shadow optional deployment capability",
        }
    return HTTPException(
        status_code=503,
        detail={
            "available": False,
            "code": str(status.get("code", "shadow_unavailable")),
            "reason": str(status.get("reason", "Shadow optional service is unavailable"))[:256],
            "install_hint": str(
                status.get(
                    "install_hint", "enable the shadow optional deployment capability"
                )
            )[:256],
        },
    )


def _principal(request: Request) -> str:
    principal = getattr(request.state, "reviewer_principal", None)
    if not isinstance(principal, str) or not principal:
        raise _unavailable(request)
    return principal


def _service(request: Request) -> Any:
    service = getattr(request.app.state, "shadow_service", None)
    if service is None:
        raise _unavailable(request)
    return service


def _repository(request: Request) -> Any:
    repository = getattr(request.app.state, "shadow_repository", None)
    if repository is None:
        repository = getattr(_service(request), "repository", None)
    if repository is None:
        raise _unavailable(request)
    return repository


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Shadow resource not found")


def _owned_batch(request: Request, batch_id: str) -> dict[str, Any]:
    record = _repository(request).get_import_batch(batch_id)
    if not isinstance(record, dict) or record.get("principal") != _principal(request):
        raise _not_found()
    return record


def _owned_evidence(request: Request, evidence_set_id: str) -> dict[str, Any]:
    record = _repository(request).get_evidence_set(evidence_set_id)
    if not isinstance(record, dict) or record.get("principal") != _principal(request):
        raise _not_found()
    return record


def _owned_candidate(request: Request, candidate_id: str) -> dict[str, Any]:
    record = _repository(request).get_candidate(candidate_id)
    if not isinstance(record, dict):
        raise _not_found()
    evidence_id = record.get("evidence_set_id")
    if not isinstance(evidence_id, str):
        raise _not_found()
    _owned_evidence(request, evidence_id)
    return record


def _owned_evaluation(request: Request, evaluation_id: str) -> dict[str, Any]:
    record = _repository(request).get_evaluation(evaluation_id)
    if not isinstance(record, dict):
        raise _not_found()
    candidate_id = record.get("candidate_id")
    if not isinstance(candidate_id, str):
        raise _not_found()
    _owned_candidate(request, candidate_id)
    return record


def _owned_retention(request: Request, retention_id: str) -> dict[str, Any]:
    record = _repository(request).get_retention_event(retention_id)
    if not isinstance(record, dict):
        raise _not_found()
    candidate_id = record.get("candidate_id")
    if not isinstance(candidate_id, str):
        raise _not_found()
    _owned_candidate(request, candidate_id)
    return record


def _translate(error: Exception, *, import_request: bool = False) -> HTTPException:
    message = str(error).lower()
    if "already" in message or "conflict" in message or "changed" in message:
        return HTTPException(status_code=409, detail="Shadow immutable state changed; refresh and retry")
    if import_request:
        status = 413 if "byte boundary" in message or "exceeds" in message else 400
        return HTTPException(status_code=status, detail="Shadow import request was rejected")
    return HTTPException(status_code=422, detail="Shadow request failed governed validation")


async def _upload_bytes(file: UploadFile) -> bytes:
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Shadow upload exceeds the configured boundary")
    return content


def _mapping(raw: str) -> dict[str, str | None]:
    try:
        parsed = json.loads(raw)
        return ImportMapping.model_validate(parsed).model_dump(exclude_none=True)
    except (json.JSONDecodeError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="Shadow import mapping is invalid") from error


def _page_payload(items: list[dict[str, object]], *, offset: int, limit: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    payload = projections.page(items, offset=offset, limit=limit)
    page = {key: payload[key] for key in ("offset", "limit", "has_more", "total")}
    return payload["items"], page  # type: ignore[return-value]


@router.post("/imports/preview")
async def preview_import(
    request: Request,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form(min_length=2, max_length=8_000)],
    source_timezone: Annotated[str, Form(min_length=1, max_length=64)],
) -> dict[str, object]:
    _principal(request)
    content = await _upload_bytes(file)
    try:
        result = _service(request).preview_import(
            filename=file.filename or "",
            media_type=file.content_type or "",
            content=content,
            mapping=_mapping(mapping),
            source_timezone=source_timezone,
        )
    except (ShadowImportError, ShadowRepositoryError, RuntimeError) as error:
        raise _translate(error, import_request=True) from error
    return {"preview": projections.import_preview(result)}


@router.post("/imports/confirm", status_code=201)
async def confirm_import(
    request: Request,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form(min_length=2, max_length=8_000)],
    source_timezone: Annotated[str, Form(min_length=1, max_length=64)],
    source_label: Annotated[str, Form(min_length=1, max_length=256)],
    supersedes_batch_id: Annotated[str | None, Form(max_length=128)] = None,
) -> dict[str, object]:
    principal = _principal(request)
    if supersedes_batch_id is not None:
        _owned_batch(request, supersedes_batch_id)
    content = await _upload_bytes(file)
    try:
        result = _service(request).confirm_import(
            filename=file.filename or "",
            media_type=file.content_type or "",
            content=content,
            mapping=_mapping(mapping),
            source_timezone=source_timezone,
            principal=principal,
            source_label=source_label,
            supersedes_batch_id=supersedes_batch_id,
        )
    except (ShadowImportError, ShadowRepositoryError, RuntimeError) as error:
        raise _translate(error, import_request=True) from error
    return {"batch": projections.batch(result)}


@router.get("/batches")
def list_batches(
    request: Request,
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    records = list(reversed(_repository(request).list_import_batches(principal=_principal(request))))
    items, page = _page_payload([projections.batch(record) for record in records], offset=offset, limit=limit)
    return {"batches": items, "page": page}


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, request: Request) -> dict[str, object]:
    return {"batch": projections.batch(_owned_batch(request, batch_id))}


@router.post("/evidence-sets", status_code=201)
def create_evidence_set(payload: EvidenceSetCreateRequest, request: Request) -> dict[str, object]:
    for batch_id in payload.included_batch_ids:
        _owned_batch(request, batch_id)
    try:
        record = _service(request).create_evidence_set(
            principal=_principal(request),
            included_batch_ids=payload.included_batch_ids,
            included_trade_ids=payload.included_trade_ids,
            exclusions=[item.model_dump() for item in payload.exclusions],
        )
    except (ShadowEvidenceError, ShadowRepositoryError, ValueError) as error:
        raise _translate(error) from error
    return {"evidence_set": projections.evidence_set(record)}


@router.get("/evidence-sets")
def list_evidence_sets(
    request: Request,
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    records = list(reversed(_repository(request).list_evidence_sets(principal=_principal(request))))
    items, page = _page_payload([projections.evidence_set(record) for record in records], offset=offset, limit=limit)
    return {"evidence_sets": items, "page": page}


@router.get("/evidence-sets/{evidence_set_id}")
def get_evidence_set(evidence_set_id: str, request: Request) -> dict[str, object]:
    return {"evidence_set": projections.evidence_set(_owned_evidence(request, evidence_set_id))}


@router.post("/evidence-sets/{evidence_set_id}/candidates", status_code=201)
def distill_candidate(
    evidence_set_id: str, payload: DistillRequest, request: Request
) -> dict[str, object]:
    _owned_evidence(request, evidence_set_id)
    try:
        record = _service(request).distill_candidate(
            evidence_set_id=evidence_set_id, **payload.model_dump()
        )
    except (ValueError, RuntimeError, ShadowRepositoryError) as error:
        raise _translate(error) from error
    return {"candidate": projections.candidate(record)}


@router.get("/candidates")
def list_candidates(
    request: Request,
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    _principal(request)
    records = []
    for record in reversed(_repository(request).list_candidates()):
        try:
            _owned_evidence(request, str(record["evidence_set_id"]))
        except HTTPException:
            continue
        records.append(projections.candidate(record))
    items, page = _page_payload(records, offset=offset, limit=limit)
    return {"candidates": items, "page": page}


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str, request: Request) -> dict[str, object]:
    return {"candidate": projections.candidate(_owned_candidate(request, candidate_id))}


@router.post("/evidence-sets/{evidence_set_id}/candidates/{candidate_id}/evaluations", status_code=201)
def evaluate_candidate(
    evidence_set_id: str,
    candidate_id: str,
    payload: EvaluationRequest,
    request: Request,
) -> dict[str, object]:
    candidate = _owned_candidate(request, candidate_id)
    if candidate.get("evidence_set_id") != evidence_set_id:
        raise _not_found()
    _owned_evidence(request, evidence_set_id)
    try:
        result = _service(request).evaluate_candidate(
            candidate_id=candidate_id,
            evidence_set_id=evidence_set_id,
            **payload.model_dump(),
        )
    except (ShadowEvaluationError, ShadowRepositoryError, ValueError) as error:
        raise _translate(error) from error
    return {
        "evaluations": {
            "in_sample": projections.evaluation(result["in_sample"]),
            "out_of_sample": projections.evaluation(result["out_of_sample"]),
        }
    }


@router.post("/evaluations/{evaluation_id}/retry", status_code=201)
def retry_evaluation(evaluation_id: str, request: Request) -> dict[str, object]:
    _owned_evaluation(request, evaluation_id)
    try:
        record = _service(request).retry_evaluation(evaluation_id=evaluation_id)
    except (ShadowEvaluationError, ShadowRepositoryError, ValueError) as error:
        raise _translate(error) from error
    return {"evaluation": projections.evaluation(record)}


@router.get("/evaluations")
def list_evaluations(
    request: Request,
    candidate_id: str | None = Query(default=None, max_length=128),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    if candidate_id is not None:
        _owned_candidate(request, candidate_id)
    else:
        _principal(request)
    records = []
    for record in reversed(_repository(request).list_evaluations(candidate_id=candidate_id)):
        try:
            _owned_candidate(request, str(record["candidate_id"]))
        except HTTPException:
            continue
        records.append(projections.evaluation(record))
    items, page = _page_payload(records, offset=offset, limit=limit)
    return {"evaluations": items, "page": page}


@router.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: str, request: Request) -> dict[str, object]:
    return {"evaluation": projections.evaluation(_owned_evaluation(request, evaluation_id))}


@router.post("/evidence-sets/{evidence_set_id}/candidates/{candidate_id}/retain", status_code=201)
def retain_candidate(
    evidence_set_id: str,
    candidate_id: str,
    payload: RetainRequest,
    request: Request,
) -> dict[str, object]:
    candidate = _owned_candidate(request, candidate_id)
    if candidate.get("evidence_set_id") != evidence_set_id:
        raise _not_found()
    _owned_evaluation(request, payload.in_sample_evaluation_id)
    _owned_evaluation(request, payload.out_of_sample_evaluation_id)
    try:
        record = _service(request).retain_candidate(
            candidate_id=candidate_id,
            evidence_set_id=evidence_set_id,
            in_sample_evaluation_id=payload.in_sample_evaluation_id,
            out_of_sample_evaluation_id=payload.out_of_sample_evaluation_id,
            reviewer_principal=_principal(request),
            rationale=payload.rationale,
        )
    except (ShadowRetentionError, ShadowRepositoryError, ValueError) as error:
        raise _translate(error) from error
    return {"retention": projections.retention(record)}


@router.get("/retentions")
def list_retentions(
    request: Request,
    candidate_id: str | None = Query(default=None, max_length=128),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    if candidate_id is not None:
        _owned_candidate(request, candidate_id)
    else:
        _principal(request)
    records = []
    for record in reversed(_repository(request).list_retention_events(candidate_id=candidate_id)):
        try:
            _owned_candidate(request, str(record["candidate_id"]))
        except HTTPException:
            continue
        records.append(projections.retention(record))
    items, page = _page_payload(records, offset=offset, limit=limit)
    return {"retentions": items, "page": page}


@router.get("/retentions/{retention_id}")
def get_retention(retention_id: str, request: Request) -> dict[str, object]:
    return {"retention": projections.retention(_owned_retention(request, retention_id))}
