"""Authenticated stock-scoped API for the immutable Thesis lifecycle."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.theses import projections
from app.theses.schemas import ThesisRevisionRequest, ThesisVersionRequest
from app.theses.service import ThesisConflictError

router = APIRouter(prefix="/api/theses", tags=["theses"])
_INSTRUMENT = re.compile(r"^[0-9A-Z.-]+$")


class ThesisSubjectScope(Protocol):
    def allows(self, subject_kind: str, subject_key: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class SubjectScope:
    """Minimal immutable server-derived stock scope for host wiring and tests."""

    instruments: frozenset[str]

    def allows(self, subject_kind: str, subject_key: str) -> bool:
        return subject_kind == "instrument" and subject_key in self.instruments


class ReviewRationaleRequest(BaseModel):
    """The browser supplies rationale only; identity and evidence remain server-owned."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    rationale: str = Field(min_length=10, max_length=4_000)


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "available": False,
            "code": "thesis_unavailable",
            "reason": "investment thesis service is temporarily unavailable",
            "install_hint": "enable the thesis optional module and restart the application",
        },
    )


def _service(request: Request) -> Any:
    service = getattr(request.app.state, "thesis_service", None)
    if service is None:
        raise _unavailable()
    return service


def _scope(request: Request) -> ThesisSubjectScope:
    resolver = getattr(request.app.state, "resolve_thesis_subject_scope", None)
    if not callable(resolver):
        resolver = getattr(request.app.state, "resolve_analysis_subject_scope", None)
    if not callable(resolver):
        raise _unavailable()
    try:
        scope = resolver(request)
    except Exception as error:
        raise _unavailable() from error
    if not callable(getattr(scope, "allows", None)):
        raise _unavailable()
    return scope


def _principal(request: Request) -> str:
    principal = getattr(request.state, "reviewer_principal", None)
    if not isinstance(principal, str) or not principal.strip():
        raise _unavailable()
    return principal


def _instrument(value: str) -> str:
    canonical = value.strip().upper()
    if not canonical or len(canonical) > 32 or _INSTRUMENT.fullmatch(canonical) is None:
        raise HTTPException(status_code=404, detail="thesis resource not found")
    return canonical


def _require_instrument(request: Request, instrument: str) -> str:
    canonical = _instrument(instrument)
    if not _scope(request).allows("instrument", canonical):
        raise HTTPException(status_code=404, detail="thesis resource not found")
    return canonical


def _owned_version(request: Request, version_id: str) -> dict[str, Any]:
    record = _service(request).get_version(version_id)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail="thesis resource not found")
    _require_instrument(request, str(record.get("instrument", "")))
    return record


def _owned_pending(request: Request, pending_id: str) -> dict[str, Any]:
    record = _service(request).get_pending(pending_id)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail="thesis resource not found")
    _require_instrument(request, str(record.get("instrument", "")))
    return record


def _translate(error: ValueError) -> HTTPException:
    message = str(error).lower()
    if isinstance(error, ThesisConflictError) or any(
        marker in message for marker in ("conflict", "stale", "already processed", "state changed", "no longer matches")
    ):
        return HTTPException(status_code=409, detail="thesis state changed; refresh and retry")
    if "not found" in message:
        return HTTPException(status_code=404, detail="thesis resource not found")
    return HTTPException(status_code=422, detail="thesis request is invalid")




@router.get("/capability")
def capability(request: Request) -> dict[str, object]:
    _service(request)
    return {"available": True, "code": "thesis_available", "reason": None, "install_hint": None}


@router.get("/instruments/{instrument}/versions")
def list_versions(
    instrument: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    canonical = _require_instrument(request, instrument)
    return _service(request).versions_for_instrument(
        canonical, offset=offset, limit=limit
    )


@router.post("/instruments/{instrument}/versions", status_code=status.HTTP_201_CREATED)
def create_version(instrument: str, payload: ThesisVersionRequest, request: Request) -> dict[str, Any]:
    canonical = _require_instrument(request, instrument)
    principal = _principal(request)
    if payload.instrument != canonical:
        raise HTTPException(status_code=422, detail="thesis instrument does not match object scope")
    try:
        record = _service(request).create_version(request=payload, created_by=principal)
    except ValueError as error:
        raise _translate(error) from error
    return {"version": projections.version(record)}


@router.get("/versions/{version_id}")
def version_detail(version_id: str, request: Request) -> dict[str, Any]:
    record = _owned_version(request, version_id)
    return {"version": _service(request).version_projection(record)}


@router.post("/versions/{version_id}", status_code=status.HTTP_201_CREATED)
def revise_version(version_id: str, payload: ThesisRevisionRequest, request: Request) -> dict[str, Any]:
    predecessor = _owned_version(request, version_id)
    principal = _principal(request)
    if payload.expected_predecessor_id != version_id:
        raise HTTPException(status_code=409, detail="thesis state changed; refresh and retry")
    try:
        record = _service(request).revise_version(
            thesis_id=str(predecessor["thesis_id"]),
            request=payload,
            created_by=principal,
        )
    except ValueError as error:
        raise _translate(error) from error
    return {"version": projections.version(record)}


@router.get("/instruments/{instrument}/checks")
def list_checks(
    instrument: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    canonical = _require_instrument(request, instrument)
    return _service(request).checks_for_instrument(
        canonical, offset=offset, limit=limit
    )


@router.get("/instruments/{instrument}/pending")
def list_pending(
    instrument: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    canonical = _require_instrument(request, instrument)
    return _service(request).pending_for_instrument(
        canonical, offset=offset, limit=limit
    )


@router.get("/instruments/{instrument}/history")
def history(
    instrument: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    canonical = _require_instrument(request, instrument)
    return _service(request).history_for_instrument(
        canonical, offset=offset, limit=limit
    )


@router.post("/pending/{pending_id}/confirm")
def confirm_pending(
    pending_id: str,
    payload: ReviewRationaleRequest,
    request: Request,
) -> dict[str, Any]:
    _owned_pending(request, pending_id)
    principal = _principal(request)
    try:
        outcome = _service(request).confirm(
            pending_id=pending_id,
            rationale=payload.rationale,
            reviewer_principal=principal,
        )
    except ValueError as error:
        raise _translate(error) from error
    return {"review": projections.review_event(outcome["event"]), "official_status": outcome["official_state"]}


@router.post("/pending/{pending_id}/reject")
def reject_pending(
    pending_id: str,
    payload: ReviewRationaleRequest,
    request: Request,
) -> dict[str, Any]:
    _owned_pending(request, pending_id)
    principal = _principal(request)
    try:
        outcome = _service(request).reject(
            pending_id=pending_id,
            rationale=payload.rationale,
            reviewer_principal=principal,
        )
    except ValueError as error:
        raise _translate(error) from error
    return {"review": projections.review_event(outcome["event"]), "official_status": outcome["official_state"]}
