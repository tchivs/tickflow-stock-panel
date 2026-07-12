"""Authenticated, subject-scoped HTTP resources for governed analysis."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.analysis import projections

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalysisSubjectScope(Protocol):
    """An immutable server-derived scope used by both REST and the shared SSE stream."""

    def allows(self, subject_kind: str, subject_key: str) -> bool: ...


@dataclass(frozen=True)
class SubjectScope:
    """Minimal concrete scope for the single-user host and focused tests."""

    subjects: frozenset[tuple[str, str]]
    unrestricted_kinds: frozenset[str] = frozenset()

    def allows(self, subject_kind: str, subject_key: str) -> bool:
        return subject_kind in self.unrestricted_kinds or (subject_kind, subject_key) in self.subjects


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_kind: Literal["instrument", "account"]
    subject_key: str = Field(min_length=1, max_length=128)
    focus: str = Field(default="", max_length=256)


class ConfirmReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_days: Literal[20, 60, 120]


class OutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["complete", "incomplete"]
    observed_value: float | None = None
    notes: str = Field(default="", max_length=1000)


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="analysis service is temporarily unavailable")


def _scope(request: Request) -> AnalysisSubjectScope:
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


def _require_subject(request: Request, subject_kind: str, subject_key: str) -> None:
    if not _scope(request).allows(subject_kind, subject_key):
        # Do not reveal whether a foreign subject exists.
        raise HTTPException(status_code=404, detail="analysis subject not found")


def _repository(request: Request):
    repository = getattr(request.app.state, "analysis_repository", None)
    if repository is None:
        raise _unavailable()
    return repository


def _service(request: Request):
    service = getattr(request.app.state, "analysis_service", None)
    if service is None:
        raise _unavailable()
    return service


def _lifecycle(request: Request):
    service = getattr(request.app.state, "lifecycle_rule_service", None)
    if service is None:
        raise _unavailable()
    return service


def _reviewer_principal(request: Request) -> str:
    principal = getattr(request.state, "reviewer_principal", None)
    if not isinstance(principal, str) or not principal:
        raise _unavailable()
    return principal


def _report_subject(request: Request, report_id: str) -> dict[str, Any]:
    report = _repository(request).get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="analysis report not found")
    _require_subject(request, str(report["subject_kind"]), str(report["subject_key"]))
    return report


def _review_subject(request: Request, review_id: str) -> dict[str, Any]:
    repository = _repository(request)
    review = repository.get_lifecycle_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="analysis review not found")
    signal = repository.get_signal(str(review["signal_id"]))
    if signal is None:
        raise HTTPException(status_code=404, detail="analysis review not found")
    _require_subject(request, str(signal["subject_kind"]), str(signal["subject_key"]))
    return review


def _translate(error: ValueError) -> HTTPException:
    message = str(error)
    if "already" in message or "cannot transition" in message or "no longer matches" in message:
        return HTTPException(status_code=409, detail="analysis state changed; refresh and retry")
    return HTTPException(status_code=400, detail=message)


def _publish_progress(request: Request, run: dict[str, Any]) -> None:
    notifier = getattr(getattr(request.app.state, "quote_service", None), "notify_analysis_progress", None)
    if callable(notifier):
        notifier(
            run_id=str(run["id"]),
            subject_kind=str(run["subject_kind"]),
            subject_key=str(run["subject_key"]),
            status=str(run["status"]),
        )


@router.post("/runs")
async def start_run(payload: RunRequest, request: Request) -> dict[str, Any]:
    _require_subject(request, payload.subject_kind, payload.subject_key)
    try:
        run = await _service(request).start_run(**payload.model_dump())
    except ValueError as error:
        raise _translate(error) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail="analysis provider is temporarily unavailable") from error
    _publish_progress(request, run)
    return {"run": run}


@router.get("/subjects/{subject_kind}/{subject_key}/reports")
def list_reports(subject_kind: Literal["instrument", "account"], subject_key: str, request: Request) -> dict[str, Any]:
    _require_subject(request, subject_kind, subject_key)
    return {"reports": [projections.report_summary(report) for report in _repository(request).list_reports(subject_kind, subject_key)]}


@router.get("/reports/{report_id}")
def report_detail(report_id: str, request: Request) -> dict[str, Any]:
    report = _report_subject(request, report_id)
    signal = _repository(request).get_or_create_subject_signal(
        subject_kind=str(report["subject_kind"]), subject_key=str(report["subject_key"])
    )
    return {"report": projections.report_detail(report, signal_id=str(signal["id"]))}


@router.get("/reports/{report_id}/evidence")
def report_evidence(report_id: str, request: Request) -> dict[str, Any]:
    report = _report_subject(request, report_id)
    snapshot = _repository(request).get_frozen_snapshot(str(report.get("run_id") or ""))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="analysis evidence not found")
    return projections.evidence(report, snapshot)


@router.get("/signals/{signal_id}/history")
def signal_history(signal_id: str, request: Request) -> dict[str, Any]:
    signal = _repository(request).get_signal(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="analysis signal not found")
    subject_kind = str(signal["subject_kind"])
    subject_key = str(signal["subject_key"])
    _require_subject(request, subject_kind, subject_key)
    repository = _repository(request)
    events = repository.list_events(subject_kind=subject_kind, subject_key=subject_key)
    reviews = repository.list_lifecycle_reviews(subject_kind=subject_kind, subject_key=subject_key)
    plans = [
        {**plan, "outcomes": repository.list_observation_outcomes(str(plan["id"]))}
        for review in reviews
        for plan in repository.list_observation_plans(str(review["id"]))
    ]
    return projections.signal_history(
        signal=signal,
        current_state=repository.current_lifecycle_state(subject_kind=subject_kind, subject_key=subject_key),
        events=events,
        reviews=reviews,
        plans=plans,
    )


@router.post("/reviews/{review_id}/confirm")
def confirm_review(review_id: str, payload: ConfirmReviewRequest, request: Request) -> dict[str, Any]:
    _review_subject(request, review_id)
    principal = _reviewer_principal(request)
    try:
        confirmed = _lifecycle(request).confirm(
            review_id=review_id,
            session_token=principal,
            window_days=payload.window_days,
            benchmark="CSI300",
            metric="excess_return",
        )
    except ValueError as error:
        raise _translate(error) from error
    return {"review": {"id": review_id, "status": "confirmed"}, **confirmed}


@router.post("/reviews/{review_id}/reject")
def reject_review(review_id: str, request: Request) -> dict[str, Any]:
    _review_subject(request, review_id)
    principal = _reviewer_principal(request)
    try:
        rejected = _lifecycle(request).reject(review_id=review_id, session_token=principal)
    except ValueError as error:
        raise _translate(error) from error
    return {"review": {"id": review_id, "status": "rejected"}, **rejected}


@router.post("/plans/{plan_id}/outcomes")
def append_outcome(plan_id: str, payload: OutcomeRequest, request: Request) -> dict[str, Any]:
    repository = _repository(request)
    subject = repository.get_observation_plan_subject(plan_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="analysis observation plan not found")
    _require_subject(request, str(subject["subject_kind"]), str(subject["subject_key"]))
    try:
        outcome = _lifecycle(request).append_outcome(plan_id=plan_id, outcome=payload.model_dump())
    except ValueError as error:
        raise _translate(error) from error
    return {"outcome": outcome}
