"""Portfolio panel READ routes over immutable Phases 11-14 rows (UI-02).

Server-owned strict DTOs (contracts/panels.py) on every route.  The panels
read append-only tables + checksum-verified artifacts — never live module
hand-off.  Paper approve/reject are the ONLY write surface and are paper-only
(idempotent append-only state machine, never a live execution path).

Wave 0 (15-02): routes scaffolded; optimization-runs body implemented in
the tracer (15-01); attribution/rebalance bodies in 15-04.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.contracts.panels import (
    AttributionEvidenceDTO,
    OptimizationRunDTO,
    PaperActionRequest,
    PaperActionResponse,
    PaperStateDTO,
    PaperTransitionDTO,
    RebalancePlanDTO,
)
from app.portfolio.repository import PortfolioRepository

router = APIRouter(prefix="/api/portfolio", tags=["portfolio-panels"])


def _repository(request: Request) -> PortfolioRepository:
    repo = getattr(request.app.state, "portfolio_repository", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="portfolio repository not initialized")
    return repo


def _to_dto(row: dict, dto_cls):
    """Convert a repository dict to a strict DTO, filtering unknown keys."""
    known = dto_cls.model_fields
    filtered = {k: v for k, v in row.items() if k in known}
    return dto_cls(**filtered)


# ================================================================
# Optimization runs (15-01 tracer)
# ================================================================


@router.get("/optimization-runs", response_model=list[OptimizationRunDTO])
async def list_optimization_runs(
    request: Request,
    objective: str | None = None,
    as_of: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[OptimizationRunDTO]:
    repo = _repository(request)
    rows = repo.list_optimization_runs(objective=objective, as_of=as_of, limit=limit)
    return [_to_dto(row, OptimizationRunDTO) for row in rows]


@router.get("/optimization-runs/{run_id}", response_model=OptimizationRunDTO)
async def get_optimization_run(request: Request, run_id: str) -> OptimizationRunDTO:
    repo = _repository(request)
    row = repo.get_optimization_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="optimization run not found")
    return _to_dto(row, OptimizationRunDTO)


# ================================================================
# Attribution evidence (15-04)
# ================================================================


@router.get("/attribution", response_model=list[AttributionEvidenceDTO])
async def list_attribution(
    request: Request,
    run_id: str | None = None,
    attribution_type: str | None = None,
    risk_model: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[AttributionEvidenceDTO]:
    repo = _repository(request)
    rows = repo.list_attribution_evidence(
        run_id=run_id,
        attribution_type=attribution_type,
        risk_model=risk_model,
        limit=limit,
    )
    return [_to_dto(row, AttributionEvidenceDTO) for row in rows]


# ================================================================
# Rebalance plans + paper state machine (15-04)
# ================================================================


@router.get("/rebalance-plans", response_model=list[RebalancePlanDTO])
async def list_rebalance_plans(
    request: Request,
    run_id: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[RebalancePlanDTO]:
    repo = _repository(request)
    rows = repo.list_rebalance_plans(run_id=run_id, limit=limit)
    return [_to_dto(row, RebalancePlanDTO) for row in rows]


@router.get("/rebalance-plans/{plan_id}/paper", response_model=PaperStateDTO)
async def get_paper_state(request: Request, plan_id: str) -> PaperStateDTO:
    repo = _repository(request)
    plan = repo.get_rebalance_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="rebalance plan not found")
    current = repo.get_paper_state(plan_id)
    transitions = repo.list_paper_transitions(plan_id=plan_id)
    return PaperStateDTO(
        plan_id=plan_id,
        current_state=current,
        transitions=[_to_dto(t, PaperTransitionDTO) for t in transitions],
    )


@router.post("/rebalance-plans/{plan_id}/approve", response_model=PaperActionResponse)
async def approve_rebalance_plan(
    request: Request, plan_id: str, body: PaperActionRequest
) -> PaperActionResponse:
    """Idempotent approve — append-only audit, never a live execution path."""
    repo = _repository(request)
    plan = repo.get_rebalance_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="rebalance plan not found")
    previous = repo.get_paper_state(plan_id)
    record = repo.record_paper_transition(
        plan_id=plan_id,
        transition="approved",
        idempotency_key=body.idempotency_key,
        previous_state=previous,
    )
    current = repo.get_paper_state(plan_id)
    return PaperActionResponse(
        plan_id=plan_id,
        transition="approved",
        current_state=current or "approved",
        idempotent=record.get("idempotency_key") != body.idempotency_key,
    )


@router.post("/rebalance-plans/{plan_id}/reject", response_model=PaperActionResponse)
async def reject_rebalance_plan(
    request: Request, plan_id: str, body: PaperActionRequest
) -> PaperActionResponse:
    """Idempotent reject — append-only audit, never a live execution path."""
    repo = _repository(request)
    plan = repo.get_rebalance_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="rebalance plan not found")
    previous = repo.get_paper_state(plan_id)
    record = repo.record_paper_transition(
        plan_id=plan_id,
        transition="rejected",
        idempotency_key=body.idempotency_key,
        previous_state=previous,
    )
    current = repo.get_paper_state(plan_id)
    return PaperActionResponse(
        plan_id=plan_id,
        transition="rejected",
        current_state=current or "rejected",
        idempotent=record.get("idempotency_key") != body.idempotency_key,
    )
