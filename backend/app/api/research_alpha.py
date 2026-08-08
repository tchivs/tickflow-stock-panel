"""Typed create/get/replay routes for governed Alpha runs (AF-REQ-01).

Routes resolve the shared ``ResearchRunService`` from ``app.state`` and never
execute SQL directly.  The server-resolved principal is the only identity
source; cross-principal access returns the same 404 boundary as an unknown
run (T-45-12).  No route imports provider, factor evaluation, OOS, promotion,
broker, order, portfolio, monitor, or live-execution collaborators.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.research import projections
from app.research.run_service import AlphaRunPreflightError, ResearchRunService
from app.research.run_schemas import (
    AlphaRunCreateRequest,
    AlphaRunEventDTO,
    AlphaRunReadDTO,
    AlphaRunReplayDTO,
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
async def replay_run(request: Request, run_id: str) -> AlphaRunReplayDTO:
    """Read-only replay of the frozen snapshot and committed event history."""
    service = _service(request)
    principal = _principal(request)
    replay_record = service.replay(run_id, principal=principal)
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
    )


def _bounded_reason(reason: str) -> str:
    """Keep diagnostic reasons bounded and free of internal paths/secrets."""
    bounded = reason.strip()
    return bounded[:500] if len(bounded) > 500 else bounded
