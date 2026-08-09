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
    CloneOverrideForbidden,
    ResearchRunService,
)
from app.research.run_schemas import (
    AlphaCandidateComparisonDTO,
    AlphaCandidateDTO,
    AlphaCompareDTO,
    AlphaLineageDTO,
    AlphaLineageEdgeDTO,
    AlphaProgressDTO,
    AlphaProgressUpdateRequest,
    AlphaRunCancelRequest,
    AlphaRunCreateRequest,
    AlphaRunEventDTO,
    AlphaRunReadDTO,
    AlphaRunReplayDTO,
    AlphaRunRetryRequest,
    AlphaSnapshotDTO,
    CloneRequestDTO,
    CloneResultDTO,
    EvidenceClassificationDTO,
    ReplayBranchRequestDTO,
    ReplayBranchResultDTO,
    StressMatrixDTO,
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
                "code": "preflight_failed",
                "reason": "invalid run manifest",
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


def _bounded_reason(_reason: str) -> str:
    """Return the fixed public preflight detail; never echo diagnostics."""
    return "invalid run manifest"
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
            detail={
                "status": "preflight_failed",
                "code": "preflight_failed",
                "reason": "invalid run manifest",
            },
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
        run_id, principal=principal, after_seq=after_sequence, limit=limit + 1
    )
    truncated = len(events) > limit
    page = events[:limit]
    response.headers["X-History-Truncated"] = str(truncated).lower()
    if truncated and page:
        response.headers["X-Next-Sequence"] = str(page[-1]["seq"])
    return [AlphaRunEventDTO(**projections.event(evt)) for evt in page]


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
        run_id, principal=principal, after_ordinal=after_ordinal, limit=limit + 1
    )
    truncated = len(candidates) > limit
    page = candidates[:limit]
    response.headers["X-History-Truncated"] = str(truncated).lower()
    if truncated and page:
        response.headers["X-Next-Ordinal"] = str(page[-1]["attempt_ordinal"])
    return [AlphaCandidateDTO(**projections.candidate(c)) for c in page]


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



@router.get("/runs/{run_id}/lineage", response_model=AlphaLineageDTO)
async def get_lineage(request: Request, run_id: str) -> AlphaLineageDTO:
    """Return ordered parent→child lineage edges for one run (SC2 read half).

    Principal-scoped read-only projection over the append-only lineage table.
    Cross-principal reads return the same empty boundary as an unknown run
    (T-45-12: never a 403 leak).
    """
    service = _service(request)
    principal = _principal(request)
    if service.get(run_id, principal=principal) is None:
        raise HTTPException(status_code=404, detail="run not found")
    edges = service.list_lineage(run_id, principal=principal)
    return AlphaLineageDTO(
        run_id=run_id,
        edges=[AlphaLineageEdgeDTO(**projections.lineage(edge)) for edge in edges],
    )


@router.get(
    "/runs/{run_id}/candidates/{candidate_id}/evidence-classification",
    response_model=EvidenceClassificationDTO,
)
async def get_evidence_classification(
    request: Request, run_id: str, candidate_id: str,
) -> EvidenceClassificationDTO:
    """Return the SC4 temporal/degradation classification + clean flag.

    Sources every value from existing declared fingerprints on the frozen
    snapshot / fold evidence — no new data collection.  The ``clean`` flag is
    deny-by-default: stale/partial/blocked/fixture results can never look like
    clean production (AF-REQ-24).
    """
    service = _service(request)
    principal = _principal(request)
    inputs = service.candidate_evidence_classification(
        run_id, candidate_id, principal=principal,
    )
    if inputs is None:
        raise HTTPException(status_code=404, detail="run or candidate not found")
    snapshot, candidate, fold_evidence, fixture_flag = inputs
    classification = projections.evidence_classification(
        snapshot, candidate, fold_evidence, fixture_flag,
    )
    return EvidenceClassificationDTO(**classification)


@router.get("/runs/{run_id}/compare", response_model=AlphaCompareDTO)
async def compare_candidates(
    request: Request,
    run_id: str,
    candidates: str = Query(..., min_length=1, max_length=2048),
) -> AlphaCompareDTO:
    """Side-by-side comparison of every requested candidate (SC3, AF-REQ-22).

    Exposes each present candidate's configuration, per-fold evidence,
    admission verdict + gate trail, artifact refs, and diversity outcome
    equally — there is NEVER an opaque aggregate ``winner`` score.  An unknown
    candidate among the set is skipped (graceful partial); cross-principal or
    unknown runs return the same 404 boundary (no leak).
    """
    service = _service(request)
    principal = _principal(request)
    candidate_ids = [cid for cid in candidates.split(",") if cid]
    result = service.compare_candidates(
        run_id, principal=principal, candidate_ids=candidate_ids,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    projected = projections.compare(result)
    return AlphaCompareDTO(
        run_id=projected["run_id"],
        candidates=[AlphaCandidateComparisonDTO(**entry) for entry in projected["candidates"]],
    )


_TIER2_QUERY_AXES = {"calendar_regime", "coverage", "symbol_subset"}


@router.get("/runs/{run_id}/stress-matrix", response_model=StressMatrixDTO)
async def get_stress_matrix(
    request: Request,
    run_id: str,
    candidate_id: str = Query(..., min_length=1, max_length=128),
    fee_bps: list[float] = Query(default_factory=list),
    slippage_bps: list[float] = Query(default_factory=list),
    rebalance: list[str] = Query(default_factory=list),
    calendar_regime: list[str] = Query(default_factory=list),
    coverage: list[str] = Query(default_factory=list),
    symbol_subset: list[str] = Query(default_factory=list),
) -> StressMatrixDTO:
    """Tier-1 stress matrix — pure arithmetic over stored turnover (AF-REQ-20).

    Recomputes cost_drag/net under declared fee/slippage/rebalance values with
    zero factor-value recomputation and zero admission-threshold touch.
    Tier-2 axes (calendar-regime/coverage/symbol-subset) are an explicit
    deferral and return a bounded 422 ``not_implemented``.
    """
    service = _service(request)
    principal = _principal(request)
    tier2 = {
        "calendar_regime": calendar_regime, "coverage": coverage,
        "symbol_subset": symbol_subset,
    }
    if any(tier2[axis] for axis in _TIER2_QUERY_AXES):
        raise HTTPException(
            status_code=422,
            detail={"code": "not_implemented", "axis": "tier2_stress_deferred"},
        )
    axes = {
        "fee_bps": fee_bps, "slippage_bps": slippage_bps, "rebalance": rebalance,
    }
    try:
        result = service.stress_matrix(
            run_id, principal=principal, candidate_id=candidate_id, axes=axes,
        )
    except NotImplementedError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "not_implemented", "reason": str(error)},
        ) from error
    if result is None:
        raise HTTPException(status_code=404, detail="run or candidate not found")
    return StressMatrixDTO(
        candidate_id=result["candidate_id"],
        baseline=result["baseline"],
        matrix=result["matrix"],
    )


@router.post(
    "/runs/{run_id}/replay-branch",
    response_model=ReplayBranchResultDTO, status_code=201,
)
async def replay_branch(
    request: Request,
    run_id: str,
    body: ReplayBranchRequestDTO,
) -> ReplayBranchResultDTO:
    """Replay one branch into a NEW child run sharing the parent's inputs (SC2).

    Re-derives the PRNG frontier from the frozen seed and continues generation
    into a new immutable child run via the existing worker path.  The child
    shares the parent's frozen manifest digests; the parent is never mutated.
    """
    service = _service(request)
    principal = _principal(request)
    try:
        result = service.replay_branch(
            run_id, principal=principal, parent_step=body.parent_step,
            idempotency_key=body.idempotency_key, max_candidates=body.max_candidates,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return ReplayBranchResultDTO(**result)


@router.post("/runs/{run_id}/clone", response_model=CloneResultDTO, status_code=201)
async def clone_run(
    request: Request,
    run_id: str,
    body: CloneRequestDTO,
) -> CloneResultDTO:
    """Clone a run overriding declared scoring/costs/budgets only (SC2).

    Deep-merges only declared override dimensions into the existing immutable
    ``create()``.  ``seed``/``universe`` are rejected (422).  An unchanged
    manifest hashes identically and returns the parent id (unchanged-inputs-
    keep-their-hashes); a changed digested dimension produces a new run id.
    """
    service = _service(request)
    principal = _principal(request)
    try:
        result = service.clone_run(
            run_id, principal=principal, overrides=body.overrides,
            idempotency_key=body.idempotency_key,
        )
    except CloneOverrideForbidden as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "CloneOverrideForbidden", "reason": str(error)},
        ) from error
    except AlphaRunPreflightError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return CloneResultDTO(**result)
