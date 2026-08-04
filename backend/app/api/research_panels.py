"""Research panel READ routes over immutable Phases 10/13 rows (UI-01).

Server-owned strict DTOs (contracts/panels.py) on every route.  The panels
read append-only catalog rows — never live module hand-off.

Wave 0 (15-02): routes scaffolded; bodies implemented in 15-03.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.contracts.panels import (
    AdmissionVerdictDTO,
    FactorRevisionDTO,
    ModelCompositeDTO,
    ModelDefinitionDTO,
    WfEnsembleDTO,
    WfFoldDTO,
    WfPlanDTO,
    WfSearchRunDTO,
    WfValidatedStrategyDTO,
)
from app.research.repository import ResearchRepository

router = APIRouter(prefix="/api/research", tags=["research-panels"])


def _repository(request: Request) -> ResearchRepository:
    repo = getattr(request.app.state, "research_repository", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="research repository not initialized")
    return repo


def _to_dto(row: dict, dto_cls):
    """Convert a repository dict to a strict DTO, filtering unknown keys."""
    known = dto_cls.model_fields
    filtered = {k: v for k, v in row.items() if k in known}
    return dto_cls(**filtered)


# ================================================================
# Factor catalog (15-03)
# ================================================================


@router.get("/factors", response_model=list[FactorRevisionDTO])
async def list_factors(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
) -> list[FactorRevisionDTO]:
    """Admitted factor catalog — current revisions only."""
    repo = _repository(request)
    rows = repo.list_current_revisions()
    return [_to_dto(row, FactorRevisionDTO) for row in rows[:limit]]


@router.get("/factors/{revision_id}/verdict", response_model=AdmissionVerdictDTO)
async def get_admission_verdict(
    request: Request, revision_id: str, policy_version: str = "v1"
) -> AdmissionVerdictDTO:
    repo = _repository(request)
    row = repo.get_admission_verdict(revision_id, policy_version)
    if row is None:
        raise HTTPException(status_code=404, detail="admission verdict not found")
    return _to_dto(row, AdmissionVerdictDTO)


# ================================================================
# Model library (15-03)
# ================================================================


@router.get("/models", response_model=list[ModelDefinitionDTO])
async def list_models(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
) -> list[ModelDefinitionDTO]:
    """Composite model definitions + latest composites."""
    repo = _repository(request)
    rows = repo.list_model_definitions()
    return [_to_dto(row, ModelDefinitionDTO) for row in rows[:limit]]


@router.get("/models/{model_id}/composites", response_model=list[ModelCompositeDTO])
async def list_model_composites(
    request: Request, model_id: str
) -> list[ModelCompositeDTO]:
    repo = _repository(request)
    rows = repo.list_model_composites(model_id)
    return [_to_dto(row, ModelCompositeDTO) for row in rows]


# ================================================================
# Walk-forward (15-03)
# ================================================================


@router.get("/wf/plans", response_model=list[WfPlanDTO])
async def list_wf_plans(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfPlanDTO]:
    repo = _repository(request)
    rows = repo.list_wf_plans(limit=limit)
    return [_to_dto(row, WfPlanDTO) for row in rows]


@router.get("/wf/folds", response_model=list[WfFoldDTO])
async def list_wf_folds(
    request: Request,
    plan_id: str | None = None,
    is_oos: bool | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfFoldDTO]:
    repo = _repository(request)
    rows = repo.list_wf_folds(plan_id=plan_id, is_oos=is_oos, limit=limit)
    return [_to_dto(row, WfFoldDTO) for row in rows]


@router.get("/wf/search-runs", response_model=list[WfSearchRunDTO])
async def list_wf_search_runs(
    request: Request,
    plan_id: str | None = None,
    strategy_id: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfSearchRunDTO]:
    repo = _repository(request)
    rows = repo.list_wf_search_runs(plan_id=plan_id, strategy_id=strategy_id, limit=limit)
    return [_to_dto(row, WfSearchRunDTO) for row in rows]


@router.get("/wf/validated", response_model=list[WfValidatedStrategyDTO])
async def list_validated_strategies(
    request: Request,
    strategy_id: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfValidatedStrategyDTO]:
    repo = _repository(request)
    rows = repo.list_validated_strategies(strategy_id=strategy_id, limit=limit)
    return [_to_dto(row, WfValidatedStrategyDTO) for row in rows]


@router.get("/wf/ensembles", response_model=list[WfEnsembleDTO])
async def list_wf_ensembles(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfEnsembleDTO]:
    repo = _repository(request)
    rows = repo.list_wf_ensembles(limit=limit)
    return [_to_dto(row, WfEnsembleDTO) for row in rows]
