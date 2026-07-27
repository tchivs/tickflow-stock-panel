"""Authenticated object-scoped Forecast API and persisted-state SSE."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Mapping
from threading import Lock
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


class ForecastSubscriptionCapacityError(RuntimeError):
    """A synchronized Forecast subscription ceiling rejected admission."""


class ForecastProgressHub:
    """Synchronized bounded wake queues; persisted transitions remain authoritative."""

    def __init__(
        self,
        *,
        queue_size: int = 16,
        per_principal_limit: int = 4,
        per_job_limit: int = 4,
        global_limit: int = 64,
    ) -> None:
        limits = (queue_size, per_principal_limit, per_job_limit, global_limit)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 128
            for value in limits
        ):
            raise ValueError("Forecast progress subscription limits are invalid")
        self._queue_size = queue_size
        self._per_principal_limit = per_principal_limit
        self._per_job_limit = per_job_limit
        self._global_limit = global_limit
        self._lock = Lock()
        self._subscribers: dict[str, list[tuple[str, deque[dict[str, str]]]]] = defaultdict(list)
        self._principal_counts: dict[str, int] = defaultdict(int)
        self._active_count = 0

    @property
    def active_count(self) -> int:
        with self._lock:
            return self._active_count

    def subscribe(self, *, principal: str, job_id: str) -> deque[dict[str, str]]:
        if not principal or not job_id:
            raise ValueError("Forecast progress subscription identity is invalid")
        with self._lock:
            if (
                self._active_count >= self._global_limit
                or self._principal_counts[principal] >= self._per_principal_limit
                or len(self._subscribers[job_id]) >= self._per_job_limit
            ):
                raise ForecastSubscriptionCapacityError(
                    "Forecast progress subscription capacity is exhausted"
                )
            queue: deque[dict[str, str]] = deque(maxlen=self._queue_size)
            self._subscribers[job_id].append((principal, queue))
            self._principal_counts[principal] += 1
            self._active_count += 1
            return queue

    def unsubscribe(self, *, principal: str, job_id: str, queue: deque[dict[str, str]]) -> None:
        with self._lock:
            self._remove_locked(principal=principal, job_id=job_id, queue=queue)

    def _remove_locked(self, *, principal: str, job_id: str, queue: deque[dict[str, str]]) -> None:
        subscribers = self._subscribers.get(job_id)
        if not subscribers:
            return
        for index, (registered_principal, registered_queue) in enumerate(subscribers):
            if registered_principal == principal and registered_queue is queue:
                subscribers.pop(index)
                self._principal_counts[principal] -= 1
                if self._principal_counts[principal] <= 0:
                    self._principal_counts.pop(principal, None)
                self._active_count -= 1
                break
        if not subscribers:
            self._subscribers.pop(job_id, None)

    def publish(self, record: Mapping[str, object]) -> None:
        event = projections.progress(record)
        version = record.get("transition_version")
        if isinstance(version, int) and not isinstance(version, bool):
            event["transition_version"] = str(version)
        job_id = str(record["id"])
        with self._lock:
            for principal, queue in tuple(self._subscribers.get(job_id, ())):
                if len(queue) >= self._queue_size:
                    queue.clear()
                    queue.append(
                        {
                            "job_id": job_id,
                            "status": "interrupted",
                            "stage": "transport_overflow",
                            "stage_recorded_at": str(record.get("updated_at") or ""),
                        }
                    )
                    self._remove_locked(principal=principal, job_id=job_id, queue=queue)
                else:
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
            projections.catalog_entry(entry) for entry in entries if isinstance(entry, Mapping)
        ]
    }


@router.post("/instruments/{instrument}/jobs", status_code=status.HTTP_201_CREATED)
def create_job(instrument: str, payload: ForecastJobRequest, request: Request) -> dict[str, object]:
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
        raise HTTPException(
            status_code=422, detail="Forecast request failed governed validation"
        ) from error
    result = projections.job(record, record_id=_record_id_for_job(request, record))
    _hub(request).publish(record)
    return {"job": result}


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_201_CREATED)
def retry_job(job_id: str, payload: ForecastRetryRequest, request: Request) -> dict[str, object]:
    source = _owned_job(request, job_id)
    service = getattr(request.app.state, "forecast_request_service", None)
    retry = getattr(service, "retry_job", None)
    if not callable(retry):
        raise HTTPException(status_code=503, detail=_module_status(request, available=False))
    try:
        record = retry(
            source_job_id=str(source["id"]), idempotency_key=payload.idempotency_key
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409, detail="Forecast retry conflicts with persisted state"
        ) from error
    _hub(request).publish(record)
    return {"job": projections.job(record)}


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, request: Request) -> dict[str, object]:
    record = _owned_job(request, job_id)
    return {
        "job": projections.job(record, record_id=_record_id_for_job(request, record))
    }


@router.get("/instruments/{instrument}/jobs")
def list_jobs(
    instrument: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, object]:
    canonical = _require_instrument(request, instrument)
    page = _repository(request).page_owned_jobs(
        principal=_principal(request),
        instrument_id=canonical,
        offset=offset,
        limit=limit,
    )
    items = [
        projections.job(row, record_id=row.get("record_id"))
        for row in page.pop("items")
    ]
    return {"jobs": items, "page": page}


@router.get("/instruments/{instrument}/records")
def list_records(
    instrument: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, object]:
    canonical = _require_instrument(request, instrument)
    page = _repository(request).page_owned_forecasts(
        principal=_principal(request),
        instrument_id=canonical,
        offset=offset,
        limit=limit,
    )
    items = [projections.record(row) for row in page.pop("items")]
    latest_governed_session_id = _latest_governed_session_id(request)
    return {
        "records": items,
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
        raise HTTPException(
            status_code=409, detail="Forecast path artifact failed verification"
        ) from error
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
    evaluate = getattr(scanner, "evaluate", None)
    if scanner is not None and callable(session_resolver):
        if not callable(evaluate):
            raise HTTPException(
                status_code=503, detail="Forecast calibration scanner is unavailable"
            )
        try:
            as_of_session_id = session_resolver()
            for horizon in (5, 20, 60):
                if horizon <= int(record["horizon"]):
                    evaluate(
                        forecast_id=str(record["id"]),
                        horizon=horizon,
                        as_of_session_id=as_of_session_id,
                    )
        except (OSError, ValueError, RuntimeError) as error:
            raise HTTPException(
                status_code=409, detail="Forecast calibration scan could not complete"
            ) from error
    return _calibration_payload(request, record)


@router.get("/jobs/{job_id}/events")
@router.get("/jobs/{job_id}/stream")
def job_events(job_id: str, request: Request) -> StreamingResponse:
    job = _owned_job(request, job_id)
    last_event_id = request.headers.get("last-event-id")
    if last_event_id is None:
        after_version = -1
    elif re.fullmatch(r"0|[1-9][0-9]{0,18}", last_event_id) is None:
        raise HTTPException(status_code=400, detail="Forecast Last-Event-ID is invalid")
    else:
        after_version = int(last_event_id)
    if after_version > int(job["transition_version"]):
        raise HTTPException(status_code=409, detail="Forecast Last-Event-ID is ahead of the job")
    principal = _principal(request)
    hub = _hub(request)
    try:
        queue = hub.subscribe(principal=principal, job_id=job_id)
    except ForecastSubscriptionCapacityError as error:
        raise HTTPException(
            status_code=429,
            detail={"code": "forecast_subscription_capacity", "retryable": True},
        ) from error
    return StreamingResponse(
        _event_stream(
            request,
            job_id=job_id,
            principal=principal,
            after_version=after_version,
            queue=queue,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/testing/terminal-jobs", status_code=status.HTTP_201_CREATED)
def create_terminal_job(payload: TerminalJobRequest, request: Request) -> dict[str, object]:
    if os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="Forecast resource not found")
    canonical = _require_instrument(request, payload.instrument)
    repository = _repository(request)
    fingerprint = (
        __import__("hashlib")
        .sha256(
            json.dumps(
                {"instrument": canonical, "terminal": payload.terminal, "nonce": uuid4().hex},
                sort_keys=True,
            ).encode()
        )
        .hexdigest()
    )
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
    request: Request,
    *,
    job_id: str,
    principal: str,
    after_version: int,
    queue: deque[dict[str, str]],
) -> AsyncIterator[str]:
    hub = _hub(request)
    repository = _repository(request)
    try:
        for _poll in range(120):
            if await request.is_disconnected():
                return
            current = _owned_job(request, job_id)
            transitions = repository.owned_job_transitions_after(
                job_id,
                principal=principal,
                instrument_id=str(current["instrument_id"]),
                after_version=after_version,
                limit=128,
            )
            for persisted in transitions:
                version = int(persisted["transition_version"])
                if version <= after_version:
                    continue
                event = projections.progress(persisted)
                event_name = "done" if event["status"] in _TERMINAL else "forecast_progress"
                yield _sse(event_name, event, event_id=str(version))
                after_version = version
                if event_name == "done":
                    return
            while queue:
                wake = queue.popleft()
                if wake.get("stage") == "transport_overflow":
                    return
            current = _owned_job(request, job_id)
            if (
                int(current["transition_version"]) <= after_version
                and projections.progress(current)["status"] in _TERMINAL
            ):
                return
            await asyncio.sleep(0.25)
    finally:
        hub.unsubscribe(principal=principal, job_id=job_id, queue=queue)


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
    principal = _principal(request)
    scope = {
        "forecast_id": str(record["id"]),
        "principal": principal,
        "instrument_id": str(record["instrument_id"]),
    }
    outcomes = repository.outcomes_for_owned_forecast(**scope)
    facts = repository.calibration_facts_for_owned_forecast(**scope)
    payload: dict[str, object] = {
        "outcomes": [projections.outcome(item) for item in outcomes],
        "calibration": [projections.calibration(item) for item in facts],
    }
    service = getattr(request.app.state, "forecast_request_service", None)
    public_price_context = getattr(service, "public_price_context", None)
    if callable(public_price_context):
        try:
            context = public_price_context(record)
        except (OSError, RuntimeError, ValueError):
            context = None
        if isinstance(context, Mapping):
            payload["price_context"] = dict(context)
    return payload


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
        "reason": "forecast optional capability is available"
        if is_available
        else "forecast optional capability is unavailable",
        "install_hint": "forecast optional capability is enabled"
        if is_available
        else "enable the forecast optional deployment capability",
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
    record = _repository(request).get_owned_job(
        job_id=job_id, principal=_principal(request)
    )
    if not isinstance(record, dict):
        raise _not_found()
    _require_instrument(request, str(record["instrument_id"]))
    return record


def _owned_record(request: Request, record_id: str) -> dict[str, Any]:
    record = _repository(request).get_owned_forecast(
        forecast_id=record_id, principal=_principal(request)
    )
    if not isinstance(record, dict):
        raise _not_found()
    _require_instrument(request, str(record["instrument_id"]))
    return record


def _record_id_for_job(request: Request, job: Mapping[str, object]) -> str | None:
    record = _repository(request).record_for_owned_job(
        job_id=str(job["id"]),
        principal=_principal(request),
        instrument_id=str(job["instrument_id"]),
    )
    return None if record is None else str(record["id"])


def _hub(request: Request) -> ForecastProgressHub:
    hub = getattr(request.app.state, "forecast_progress_hub", None)
    if not isinstance(hub, ForecastProgressHub):
        hub = ForecastProgressHub()
        request.app.state.forecast_progress_hub = hub
    return hub


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Forecast resource not found")
