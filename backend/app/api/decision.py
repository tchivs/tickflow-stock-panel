"""Authenticated deterministic decision-playbook API routes."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.decision.playbook import DecisionPlaybookService
from app.decision.adjustments import DecisionAdjustmentService
from app.decision.ai_review import ConfiguredAIReviewGateway, DecisionReviewService


router = APIRouter(prefix="/api/decision", tags=["decision"])

_DEFAULT_CONFIGURATION: dict[str, Any] = {
    "entry_band": ["0.02", "0.03"],
    "stop_k": "1.5",
    "tp_ratios": ["1.5", "3.0"],
    "per_trade_risk_pct": "0.02",
    "rr_threshold": "1.5",
    "position_cap": "0.50",
    "market_state": "震荡",
    "score": "0",
}


class DecisionRunRequest(BaseModel):
    """Generation inputs; market bars are always loaded from the host repository."""

    symbol: str
    as_of: str
    engine_config_version: str = "playbook-v1"
    configuration: dict[str, Any] = Field(default_factory=lambda: dict(_DEFAULT_CONFIGURATION))


class PlaybookSnapshotResponse(BaseModel):
    symbol: str
    entry_low: Decimal
    entry_high: Decimal
    stop: Decimal
    target1: Decimal
    target2: Decimal
    position_pct: Decimal
    action: str
    score: Decimal
    risk_reward: Decimal
    reason_snapshot: dict[str, str]


class AdjustmentAuditResponse(BaseModel):
    field: str
    proposed_value: str | None
    final_value: str | None
    disposition: str
    rationale: str


class DecisionRunResponse(BaseModel):
    id: str
    symbol: str
    data_as_of: str
    engine_config_version: str
    created_at: str
    baseline: PlaybookSnapshotResponse
    final: PlaybookSnapshotResponse
    proposal: dict[str, Any] | None
    adjustments: list[AdjustmentAuditResponse]


class DecisionAdjustmentRequest(BaseModel):
    """Untrusted proposal values are validated and audited by the bounded domain service."""

    proposal: dict[str, dict[str, Any]]


class DecisionReviewResponse(BaseModel):
    review_status: str
    final: PlaybookSnapshotResponse


def _operational(request: Request):
    repository = getattr(request.app.state, "operational", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="decision operational storage is unavailable")
    return repository


def _response(run: dict[str, Any]) -> DecisionRunResponse:
    return DecisionRunResponse.model_validate(run)


@router.post("/runs", response_model=DecisionRunResponse, status_code=status.HTTP_201_CREATED)
def generate_decision_run(payload: DecisionRunRequest, request: Request) -> DecisionRunResponse:
    """Persist a governed deterministic baseline before any future provider review."""
    try:
        data_as_of = date.fromisoformat(payload.as_of)
        service = DecisionPlaybookService()
        snapshot = service.snapshot_from_governed_history(
            repository=request.app.state.repo,
            symbol=payload.symbol,
            data_as_of=data_as_of,
            configuration={**_DEFAULT_CONFIGURATION, **payload.configuration},
        )
        baseline = service.build_baseline(
            snapshot=snapshot,
            data_as_of=data_as_of,
            engine_config_version=payload.engine_config_version,
        )
        run = _operational(request).persist_decision_baseline(baseline)
        persisted = _operational(request).get_decision_run(run["id"])
        assert persisted is not None
        return _response(persisted)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/runs/{run_id}", response_model=DecisionRunResponse)
def get_decision_run(run_id: str, request: Request) -> DecisionRunResponse:
    """Retrieve baseline provenance and the independently persisted final snapshot."""
    run = _operational(request).get_decision_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="decision run not found")
    return _response(run)


@router.post("/runs/{run_id}/review", response_model=DecisionReviewResponse)
async def review_decision_run(run_id: str, request: Request) -> DecisionReviewResponse:
    """Request an optional OpenAI-compatible proposal without changing baseline facts."""
    service = DecisionReviewService(
        repository=_operational(request),
        gateway=ConfiguredAIReviewGateway.from_current_configuration(),
    )
    try:
        return DecisionReviewResponse.model_validate(await service.review(run_id=run_id))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/runs/{run_id}/adjustments", response_model=DecisionRunResponse)
def apply_decision_adjustments(
    run_id: str,
    payload: DecisionAdjustmentRequest,
    request: Request,
) -> DecisionRunResponse:
    """Audit and apply only bounded numeric adjustments to a persisted final plan."""
    try:
        DecisionAdjustmentService(_operational(request)).apply(run_id=run_id, proposal=payload.proposal)
        run = _operational(request).get_decision_run(run_id)
        assert run is not None
        return _response(run)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
