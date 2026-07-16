"""Authenticated object-scoped Forecast API and persisted-state SSE."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Mapping
import json
import os
import re
from typing import Any, Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.forecast import projections


router = APIRouter(prefix="/api/forecast", tags=["forecast"])
_INSTRUMENT = re.compile(r"^[0-9A-Z.-]{1,32}$")
_TERMINAL = {
    "completed",
    "validation_failed",
    "checkpoint_mismatch",
    "artifact_failed",
    "timeout",
    "resource_terminated",
    "interrupted",
}


class ForecastSubjectScope(Protocol):
    def allows(self, subject_kind: str, subject_key: str) -> bool: ...


class StrictForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ForecastJobRequest(StrictForecastRequest):
    horizon: Literal[5, 20, 60]
    catalog_id: str = Field(min_length=1, max_length=128, pattern=r"^[0-9A-Za-z._-]+$")
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"^[0-9A-Za-z._:-]+$")


class ForecastRetryRequest(StrictForecastRequest):
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"^[0-9A-Za-z._:-]+$")


class EmptyRequest(StrictForecastRequest):
    pass


class TerminalJobRequest(StrictForecastRequest):
    instrument: str = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Z.-]+$")
    terminal: Literal[
        "validation_failed",
        "timeout",
        "resource_terminated",
        "checkpoint_mismatch",
        "artifact_failed",
    ]


class ForecastProgressHub:
    """Bound each subscriber while persisted job state remains the reconnect source."""

    def __init__(self, *, queue_size: int = 16) -> None:
        if not 1 <= queue_size <= 128:
            raise ValueError("Forecast progress queue size is invalid")
        self._queue_size = queue_size
        self._subscribers: dict[str, list[deque[dict[str, str]]]] = defaultdict(list)

    def subscribe(self, job_id: str) -> deque[dict[str, str]]:
        queue: deque[dict[str, str]] = deque(maxlen=self._queue_size)
        self._subscribers[job_id].append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: deque[dict[str, str]]) -> None:
        subscribers = self._subscribers.get(job_id)
        if subscribers is None:
            return
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            self._subscribers.pop(job_id, None)

    def publish(self, record: Mapping[str, object]) -> None:
        event = projections.progress(record)
        for queue in tuple(self._subscribers.get(str(record["id"]), ())):
            queue.append(dict(event))


@router.get("/capability")
def capability(request: Request) -> dict[str, object]:
    status_value = _module_status(request)
    return status_value


@router.get("/catalog")
def catalog(request: Request) -> dict[str, object]:
    _repository(request)
    entries = getattr(request.app.state, "forecast_catalog_entries", ())
    return {
        "entries": [
            projections.catalog_entry(entry)
            for entry in entries
            if isinstance(entry, Mapping)
        ]
    }


@router.post("/instruments/{instrument}/jobs", status_code=status.HTTP_201_CREATED)
def create_job(
    instrument: str, payload: ForecastJobRequest, request: Request
) -> dict[str, object]:
    canonical = _require_instrument(request, instrument)
    principal = _principal(request)
    service = getattr(request.app.state, "forecast_request_service", None)
    create = getattr(service, "create_or_get_job", None)
    if not callable(create):
        raise HTTPException(status_code=503, detail=_module_status(request, available=False))
    try:
        record = create(
            principal=principal,
            instrument=canonical,
            horizon=payload.horizon,
            catalog_id=payload.catalog_id,
            idempotency_key=payload.idempotency_key,
        )
    except LookupError as error:
        raise _not_found() from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Forecast request failed governed validation") from error
    result = projections.job(record, record_id=_record_id_for_job(request, str(record["id"])))
    _hub(request).publish(record)
    return {"job": result}


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_201_CREATED)
def retry_job(
    job_id: str, payload: ForecastRetryRequest, request: Request
) -> dict[str, object]:
    source = _owned_job(request, job_id)
    try:
        record = _repository(request).create_retry_job(
            source_job_id=str(source["id"]), idempotency_key=payload.idempotency_key
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Forecast retry conflicts with persisted state") from error
    _hub(request).publish(record)
    return {"job": projections.job(record)}


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, request: Request) -> dict[str, object]:
    record = _owned_job(request, job_id)
    return {
        "job": projections.job(
            record, record_id=_record_id_for_job(request, str(record["id"]))
        )
    }


@router.get("/instruments/{instrument}/jobs")
def list_jobs(
    instrument: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, object]:
    canonical = _require_instrument(request, instrument)
    rows = [
        projections.job(row, record_id=_record_id_for_job(request, str(row["id"])))
        for row in reversed(_repository(request).list_jobs())
        if row.get("instrument_id") == canonical
    ]
    page = projections.page(rows, offset=offset, limit=limit)
    return {"jobs": page.pop("items"), "page": page}


@router.get("/instruments/{instrument}/records")
def list_records(
    instrument: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, object]:
    canonical = _require_instrument(request, instrument)
    rows = [
        projections.record(row)
        for row in _repository(request).list_forecasts_for_instrument(canonical)
    ]
    page = projections.page(rows, offset=offset, limit=limit)
    latest_governed_session_id = _latest_governed_session_id(request)
    return {
        "records": page.pop("items"),
        "page": page,
        "latest_governed_session_id": latest_governed_session_id,
    }


@router.get("/records/{record_id}")
def record_detail(record_id: str, request: Request) -> dict[str, object]:
    return {"record": projections.record(_owned_record(request, record_id))}


@router.get("/records/{record_id}/paths")
def record_paths(
    record_id: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    record = _owned_record(request, record_id)
    reader = getattr(request.app.state, "forecast_path_reader", None)
    read_page = getattr(reader, "read_page", None)
    if not callable(read_page):
        raise HTTPException(status_code=503, detail="Forecast path artifact reader is unavailable")
    try:
        rows, total = read_page(record=record, offset=offset, limit=limit)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=409, detail="Forecast path artifact failed verification") from error
    return {"paths": projections.path_page(rows, offset=offset, limit=limit, total=total)}


@router.get("/records/{record_id}/calibration")
def record_calibration(record_id: str, request: Request) -> dict[str, object]:
    record = _owned_record(request, record_id)
    return _calibration_payload(request, record)


@router.post("/records/{record_id}/calibration")
def refresh_record_calibration(
    record_id: str, payload: EmptyRequest, request: Request
) -> dict[str, object]:
    del payload
    record = _owned_record(request, record_id)
    scanner = getattr(request.app.state, "forecast_maturity_scanner", None)
    session_resolver = getattr(request.app.state, "forecast_current_session", None)
    if scanner is not None and callable(session_resolver):
        try:
            scanner.scan(as_of_session_id=session_resolver())
        except (OSError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail="Forecast calibration scan could not complete") from error
    return _calibration_payload(request, record)


@router.get("/jobs/{job_id}/events")
@router.get("/jobs/{job_id}/stream")
def job_events(job_id: str, request: Request) -> StreamingResponse:
    _owned_job(request, job_id)
    last_event_id = request.headers.get("last-event-id")
    return StreamingResponse(
        _event_stream(request, job_id=job_id, last_event_id=last_event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/testing/terminal-jobs", status_code=status.HTTP_201_CREATED)
def create_terminal_job(
    payload: TerminalJobRequest, request: Request
) -> dict[str, object]:
    if os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="Forecast resource not found")
    canonical = _require_instrument(request, payload.instrument)
    repository = _repository(request)
    fingerprint = __import__("hashlib").sha256(
        json.dumps(
            {"instrument": canonical, "terminal": payload.terminal, "nonce": uuid4().hex},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    job = repository.create_or_get_active_job(
        principal=_principal(request),
        instrument_id=canonical,
        horizon=20,
        catalog_id="fixture-terminal",
        idempotency_key=uuid4().hex,
        input_fingerprint=fingerprint,
    )
    persisted_status = {
        "timeout": "timed_out",
        "resource_terminated": "resource_limited",
        "checkpoint_mismatch": "model_unavailable",
    }.get(payload.terminal, payload.terminal)
    if persisted_status in {"artifact_failed", "timed_out", "resource_limited"}:
        running = repository.acquire_job(
            job_id=str(job["id"]),
            expected_status="queued",
            expected_version=int(job["transition_version"]),
            lease_owner="fixture-terminal",
            ttl_seconds=30,
        )
        job = repository.terminalize(
            job_id=str(running["id"]),
            expected_status="running",
            expected_version=int(running["transition_version"]),
            lease_owner="fixture-terminal",
            status=persisted_status,
            reason=f"fixture_{persisted_status}",
        )
    else:
        job = repository.terminalize(
            job_id=str(job["id"]),
            expected_status="queued",
            expected_version=int(job["transition_version"]),
            lease_owner=None,
            status=persisted_status,
            reason=f"fixture_{persisted_status}",
        )
    _hub(request).publish(job)
    return {"job": projections.job(job)}


async def _event_stream(
    request: Request, *, job_id: str, last_event_id: str | None
) -> AsyncIterator[str]:
    del last_event_id
    hub = _hub(request)
    queue = hub.subscribe(job_id)
    sequence = 0
    last_payload: dict[str, str] | None = None
    try:
        for _poll in range(120):
            if await request.is_disconnected():
                return
            persisted = _owned_job(request, job_id)
            event = projections.progress(persisted)
            if queue:
                event = queue.popleft()
            if event != last_payload:
                sequence += 1
                last_payload = event
                yield _sse("forecast_progress", event, event_id=str(sequence))
            if event["status"] in _TERMINAL:
                yield _sse("done", event, event_id=str(sequence + 1))
                return
            await asyncio.sleep(0.25)
    finally:
        hub.unsubscribe(job_id, queue)


def _sse(event: str, payload: Mapping[str, str], *, event_id: str) -> str:
    return f"id: {event_id}\nevent: {event}\ndata: {json.dumps(dict(payload), separators=(',', ':'))}\n\n"


def _latest_governed_session_id(request: Request) -> str | None:
    repository = getattr(request.app.state, "repo", None)
    resolve_latest = getattr(repository, "latest_daily_date", None)
    if not callable(resolve_latest):
        return None
    try:
        latest = resolve_latest()
    except (OSError, RuntimeError, ValueError):
        return None
    if latest is None:
        return None
    strftime = getattr(latest, "strftime", None)
    if callable(strftime):
        return strftime("CNA-%Y%m%d")
    text = str(latest)
    return f"CNA-{text.replace('-', '')}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None


def _calibration_payload(request: Request, record: Mapping[str, object]) -> dict[str, object]:
    repository = _repository(request)
    outcomes = repository.outcomes_for_forecast(str(record["id"]))
    facts = repository.calibration_facts_for_forecast(str(record["id"]))
    return {
        "outcomes": [projections.outcome(item) for item in outcomes],
        "calibration": [projections.calibration(item) for item in facts],
    }


def _module_status(request: Request, *, available: bool | None = None) -> dict[str, object]:
    status_value = getattr(request.app.state, "forecast_module_status", None)
    if status_value is not None:
        as_dict = getattr(status_value, "as_dict", None)
        if callable(as_dict):
            projected = as_dict()
            if available is None or projected.get("available") is available:
                return projected
    is_available = bool(available)
    return {
        "available": is_available,
        "code": "forecast_available" if is_available else "forecast_unavailable",
        "reason": "forecast optional capability is available" if is_available else "forecast optional capability is unavailable",
        "install_hint": "forecast optional capability is enabled" if is_available else "enable the forecast optional deployment capability",
    }


def _repository(request: Request) -> Any:
    repository = getattr(request.app.state, "forecast_repository", None)
    if repository is None:
        raise HTTPException(status_code=503, detail=_module_status(request, available=False))
    return repository


def _principal(request: Request) -> str:
    principal = getattr(request.state, "reviewer_principal", None)
    if not isinstance(principal, str) or not principal:
        raise HTTPException(status_code=401, detail="Authenticated Forecast principal is required")
    return principal


def _canonical_instrument(value: str) -> str:
    canonical = value.strip().upper()
    if not _INSTRUMENT.fullmatch(canonical):
        raise HTTPException(status_code=422, detail="Forecast instrument is invalid")
    return canonical


def _require_instrument(request: Request, instrument: str) -> str:
    canonical = _canonical_instrument(instrument)
    resolver = getattr(request.app.state, "resolve_forecast_subject_scope", None)
    scope = resolver(request) if callable(resolver) else None
    if scope is None or not scope.allows("instrument", canonical):
        raise _not_found()
    return canonical


def _owned_job(request: Request, job_id: str) -> dict[str, Any]:
    record = _repository(request).get_job(job_id)
    if not isinstance(record, dict):
        raise _not_found()
    _require_instrument(request, str(record["instrument_id"]))
    return record


def _owned_record(request: Request, record_id: str) -> dict[str, Any]:
    record = _repository(request).get_forecast(record_id)
    if not isinstance(record, dict):
        raise _not_found()
    _require_instrument(request, str(record["instrument_id"]))
    return record


def _record_id_for_job(request: Request, job_id: str) -> str | None:
    record = _repository(request).forecast_for_job(job_id)
    return None if record is None else str(record["id"])


def _hub(request: Request) -> ForecastProgressHub:
    hub = getattr(request.app.state, "forecast_progress_hub", None)
    if not isinstance(hub, ForecastProgressHub):
        hub = ForecastProgressHub()
        request.app.state.forecast_progress_hub = hub
    return hub


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Forecast resource not found")
