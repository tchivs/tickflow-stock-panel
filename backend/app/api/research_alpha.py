"""Typed create/get/replay/retry/cancel/history/progress routes for governed Alpha runs.

Routes resolve the shared ``ResearchRunService`` from ``app.state`` and never
execute SQL directly.  The server-resolved principal is the only identity
source; cross-principal access returns the same 404 boundary as an unknown
run (T-45-12).  No route imports provider, factor evaluation, OOS, promotion,
broker, order, portfolio, monitor, or live-execution collaborators.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.research import projections
from app.research.repository import AlphaRunConflictError
from app.research.run_service import (
    AlphaRunPreflightError,
    ResearchRunService,
)
from app.research.run_schemas import (
    AlphaCandidateDTO,
    AlphaProgressDTO,
    AlphaProgressUpdateRequest,
    AlphaRunCancelRequest,
    AlphaRunCreateRequest,
    AlphaRunEventDTO,
    AlphaRunReadDTO,
    AlphaRunReplayDTO,
    AlphaRunRetryRequest,
    AlphaSnapshotDTO,
)

router = APIRouter(prefix="/api/research/alpha", tags=["research-alpha"])


def _service(request: Request) -> ResearchRunService:
    service = getattr(request.app.state, "research_run_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="research run service not initialized")
    return service


def _principal(request: Request) -> str:
    """Resolve the server-owned principal from existing host authentication context.

    The auth middleware sets ``request.state.reviewer_principal`` from the
    validated session; this is the only principal source (T-45-12).
    """
    principal = getattr(request.state, "reviewer_principal", None)
    if not isinstance(principal, str) or not principal:
        raise HTTPException(status_code=401, detail="authenticated principal required")
    return principal


@router.post("/runs", response_model=AlphaRunReadDTO, status_code=201)
async def create_run(
    request: Request,
    body: AlphaRunCreateRequest,
) -> AlphaRunReadDTO:
    """Create one immutable queued run from bounded researcher intent.

    The server freezes the D-04 snapshot, commits the snapshot/run/event
    atomically, and returns the server-generated run ID and queued status.
    Malformed/incomplete run-level input returns ``preflight_failed`` with a
    bounded machine-readable reason and no queued row.
    """
    service = _service(request)
    principal = _principal(request)
    try:
        run = service.create(
            principal=principal,
            idempotency_key=body.idempotency_key,
            manifest=body.manifest,
        )
    except AlphaRunPreflightError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "preflight_failed",
                "reason": _bounded_reason(str(error)),
            },
        ) from error
    except AlphaRunConflictError as error:
        raise HTTPException(status_code=409, detail="idempotency key conflicts with an existing run") from error
    return AlphaRunReadDTO(**projections.run(run))


@router.get("/runs/{run_id}", response_model=AlphaRunReadDTO)
async def get_run(request: Request, run_id: str) -> AlphaRunReadDTO:
    """Return one principal-scoped run projection."""
    service = _service(request)
    principal = _principal(request)
    run = service.get(run_id, principal=principal)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return AlphaRunReadDTO(**projections.run(run))


@router.get("/runs/{run_id}/replay", response_model=AlphaRunReplayDTO)
async def replay_run(
    request: Request,
    run_id: str,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
) -> AlphaRunReplayDTO:
    """Read-only replay page with explicit continuation markers."""
    service = _service(request)
    principal = _principal(request)
    replay_record = service.replay(
        run_id, principal=principal, after_seq=after_sequence, limit=limit
    )
    if replay_record is None:
        raise HTTPException(status_code=404, detail="run not found")
    projected = projections.replay(replay_record)
    snapshot_dto: AlphaSnapshotDTO | None = None
    if projected["snapshot"] is not None:
        snapshot_dto = AlphaSnapshotDTO(**projected["snapshot"])  # type: ignore[arg-type]
    return AlphaRunReplayDTO(
        run=AlphaRunReadDTO(**projected["run"]),  # type: ignore[arg-type]
        snapshot=snapshot_dto,
        events=[AlphaRunEventDTO(**evt) for evt in projected["events"]],  # type: ignore[arg-type]
        events_after_sequence=int(projected["events_after_sequence"]),
        next_sequence=projected["next_sequence"],
        truncated=bool(projected["truncated"]),
    )


def _bounded_reason(reason: str) -> str:
    """Keep diagnostic reasons bounded and free of internal paths/secrets."""
    bounded = reason.strip()
    return bounded[:500] if len(bounded) > 500 else bounded
@router.post("/runs/{run_id}/retry", response_model=AlphaRunReadDTO, status_code=201)
async def retry_run(
    request: Request,
    run_id: str,
    body: AlphaRunRetryRequest,
) -> AlphaRunReadDTO:
    """Create a linked child run, preserving the immutable parent (D-07).

    A retry either resumes a valid checkpoint (Phase 48) or creates a new
    linked child run with ``retry_of_run_id`` set to the parent.  The parent's
    status/facts are never mutated.  Unknown or cross-principal parents return
    the same 404 boundary as an unknown run (T-45-12).
    """
    service = _service(request)
    principal = _principal(request)
    try:
        child = service.retry(
            run_id,
            principal=principal,
            idempotency_key=body.idempotency_key,
            manifest=body.manifest,
        )
    except AlphaRunPreflightError as error:
        raise HTTPException(
            status_code=422,
            detail={"status": "preflight_failed", "reason": _bounded_reason(str(error))},
        ) from error
    except AlphaRunConflictError as error:
        raise HTTPException(status_code=409, detail="idempotency key conflicts with an existing retry") from error
    if child is None:
        raise HTTPException(status_code=404, detail="run not found")
    return AlphaRunReadDTO(**projections.run(child))


@router.post("/runs/{run_id}/cancel", response_model=AlphaRunReadDTO)
async def cancel_run(
    request: Request,
    run_id: str,
    body: AlphaRunCancelRequest,
) -> AlphaRunReadDTO:
    """Idempotently request cooperative cancellation (D-07).

    Appends ``cancel_requested`` and transitions ``queued``/``running`` to
    ``cancel_requested``.  Terminal runs return current state with no new
    event.  A repeated idempotency key does not append a duplicate event.
    """
    service = _service(request)
    principal = _principal(request)
    if service.get(run_id, principal=principal) is None:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        result = service.cancel(
            run_id, principal=principal, expected_version=body.expected_version,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail="stale lifecycle request") from error
    if result is None:
        raise HTTPException(status_code=409, detail="stale lifecycle request")
    return AlphaRunReadDTO(**projections.run(result))


@router.get("/runs/{run_id}/events", response_model=list[AlphaRunEventDTO])
async def list_events(
    request: Request,
    run_id: str,
    response: Response,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=500),
) -> list[AlphaRunEventDTO]:
    service = _service(request)
    principal = _principal(request)
    if service.get(run_id, principal=principal) is None:
        raise HTTPException(status_code=404, detail="run not found")
    events = service.list_events(
        run_id, principal=principal, after_seq=after_sequence, limit=limit
    )
    response.headers["X-History-Truncated"] = str(len(events) >= limit).lower()
    if len(events) >= limit and events:
        response.headers["X-Next-Sequence"] = str(events[-1]["seq"])
    return [AlphaRunEventDTO(**projections.event(evt)) for evt in events]


@router.get("/runs/{run_id}/candidates", response_model=list[AlphaCandidateDTO])
async def list_candidates(
    request: Request,
    run_id: str,
    response: Response,
    after_ordinal: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=500),
) -> list[AlphaCandidateDTO]:
    service = _service(request)
    principal = _principal(request)
    if service.get(run_id, principal=principal) is None:
        raise HTTPException(status_code=404, detail="run not found")
    candidates = service.list_candidates(
        run_id, principal=principal, after_ordinal=after_ordinal, limit=limit
    )
    response.headers["X-History-Truncated"] = str(len(candidates) >= limit).lower()
    if len(candidates) >= limit and candidates:
        response.headers["X-Next-Ordinal"] = str(candidates[-1]["attempt_ordinal"])
    return [AlphaCandidateDTO(**projections.candidate(c)) for c in candidates]


@router.get("/runs/{run_id}/progress", response_model=AlphaProgressDTO)
async def get_progress(request: Request, run_id: str) -> AlphaProgressDTO:
    """Return the four bounded progress counters (D-11, T-45-08).

    Exposes ``candidate_attempts_total``, ``candidate_attempts_completed``,
    ``folds_total``, and ``folds_completed`` without token or principal.  This
    does NOT evaluate folds — it reads server-owned declared counters.
    """
    service = _service(request)
    principal = _principal(request)
    run = service.get(run_id, principal=principal)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return AlphaProgressDTO(**projections.progress(run))


@router.post("/runs/{run_id}/progress", response_model=AlphaProgressDTO)
async def update_progress(
    request: Request,
    run_id: str,
    body: AlphaProgressUpdateRequest,
) -> AlphaProgressDTO:
    """Persist a bounded worker progress update (D-10, D-11).

    Validates the attempt token plus expected version before persisting any
    counter.  A stale or invalid token/version returns 409 conflict with no
    side effect.  Only non-``None`` counters are updated.
    """
    service = _service(request)
    principal = _principal(request)
    try:
        result = service.update_progress(
            run_id, principal=principal, expected_version=body.expected_version,
            attempt_token=body.attempt_token,
            candidate_attempts_total=body.candidate_attempts_total,
            candidate_attempts_completed=body.candidate_attempts_completed,
            folds_total=body.folds_total, folds_completed=body.folds_completed,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid bounded progress update") from error
    if result is None:
        raise HTTPException(status_code=409, detail="stale version or invalid attempt token")
    return AlphaProgressDTO(**projections.progress(result))

