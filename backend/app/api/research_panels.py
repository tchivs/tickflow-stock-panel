"""Research panel READ routes over immutable Phases 10/13 rows (UI-01).

Server-owned strict DTOs (contracts/panels.py) on every route.  The panels
read append-only catalog rows — never live module hand-off.

Each route projects the repository's raw column shape onto its strict DTO.
Repository rows and DTOs do not share identical field names (e.g.
``canonical_expression`` -> ``expression``, ``gap_size`` -> ``gap``,
``passed_gate`` -> ``validated``), so a per-DTO mapper — not a naive
key-filter — is used everywhere. IC (Pearson) and RankIC (Spearman) are
surfaced as DISTINCT fields on the factor catalog, sourced from recorded
evaluation evidence; they are never collapsed into one column.
"""
from __future__ import annotations

from typing import Any

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


def _mean(summary: Any) -> float | None:
    """Pull a ``mean`` from an IC/RankIC summary dict (None if absent/non-numeric)."""
    if not isinstance(summary, dict):
        return None
    value = summary.get("mean")
    return value if isinstance(value, (int, float)) else None


# ================================================================
# Factor catalog (15-03)
# ================================================================


def _factor_dto(
    row: dict[str, Any],
    *,
    status: str,
    ic: float | None,
    rank_ic: float | None,
) -> FactorRevisionDTO:
    return FactorRevisionDTO(
        id=row["id"],
        factor_id=row["factor_id"],
        revision_number=row["revision_number"],
        name=row["name"],
        expression=row.get("canonical_expression", ""),
        description=row.get("description", ""),
        status=status,
        ic=ic,
        rank_ic=rank_ic,
        fields=row.get("fields"),
        operators=row.get("operators"),
        functions=row.get("functions"),
        provenance=row.get("provenance"),
        created_at=row["created_at"],
    )


@router.get("/factor-catalog", response_model=list[FactorRevisionDTO])
async def list_factors(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
) -> list[FactorRevisionDTO]:
    """Admitted factor catalog — current revisions only.

    Path note: the legacy research router already owns ``GET /factors``
    (all revisions, dict envelope) for the factor-backtest workspace, so the
    panel surface lives at ``/factor-catalog`` — a strict typed list of
    current revisions with DISTINCT IC and RankIC fields.

    Each row carries its admission status (``admitted`` / ``rejected`` /
    ``unadmitted``) and the DISTINCT IC and RankIC from its latest retained
    evaluation evidence, so the catalog never conflates the two correlations.
    """
    repo = _repository(request)
    revisions = repo.list_current_revisions()[:limit]
    if not revisions:
        return []
    revision_ids = [row["id"] for row in revisions]
    statuses = repo.latest_admission_verdicts(revision_ids)
    evidence = repo.latest_experiment_metrics(revision_ids)
    dtos: list[FactorRevisionDTO] = []
    for row in revisions:
        metrics = evidence.get(row["id"], {})
        dtos.append(
            _factor_dto(
                row,
                status=statuses.get(row["id"], "unadmitted"),
                ic=_mean(metrics.get("ic_summary")),
                rank_ic=_mean(metrics.get("rank_ic_summary")),
            )
        )
    return dtos


def _verdict_dto(row: dict[str, Any]) -> AdmissionVerdictDTO:
    return AdmissionVerdictDTO(
        revision_id=row["revision_id"],
        policy_version=row["policy_version"],
        admitted=(row.get("verdict") == "admitted"),
        reason=row.get("reason"),
        details={
            "gates": row.get("gates"),
            "candidate_trail": row.get("candidate_trail"),
            "resolved_universe": row.get("resolved_universe"),
        },
        created_at=row["created_at"],
    )


@router.get("/factors/{revision_id}/verdict", response_model=AdmissionVerdictDTO)
async def get_admission_verdict(
    request: Request, revision_id: str, policy_version: str = "v1"
) -> AdmissionVerdictDTO:
    repo = _repository(request)
    row = repo.get_admission_verdict(revision_id, policy_version)
    if row is None:
        raise HTTPException(status_code=404, detail="admission verdict not found")
    return _verdict_dto(row)


# ================================================================
# Model library (15-03)
# ================================================================


def _model_definition_dto(row: dict[str, Any]) -> ModelDefinitionDTO:
    return ModelDefinitionDTO(
        model_id=row["model_id"],
        name=row["name"],
        weighting=row["weighting"],
        revision_ids=row.get("revision_ids", []),
        weights=row.get("weights"),
        input_snapshot_sha256=row.get("input_snapshot_sha256"),
        created_at=row["created_at"],
    )


@router.get("/models", response_model=list[ModelDefinitionDTO])
async def list_models(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
) -> list[ModelDefinitionDTO]:
    """Composite model definitions + latest composites."""
    repo = _repository(request)
    rows = repo.list_model_definitions()
    return [_model_definition_dto(row) for row in rows[:limit]]


def _model_composite_dto(row: dict[str, Any]) -> ModelCompositeDTO:
    return ModelCompositeDTO(
        id=row["id"],
        model_id=row["model_id"],
        input_snapshot_sha256=row["input_snapshot_sha256"],
        output_sha256=row["output_sha256"],
        output_artifact_relative_path=row.get("artifact_relative_path"),
        mean_ic=row.get("mean_ic"),
        membership_fingerprint=row.get("membership_fingerprint"),
        created_at=row["created_at"],
    )


@router.get("/models/{model_id}/composites", response_model=list[ModelCompositeDTO])
async def list_model_composites(
    request: Request, model_id: str
) -> list[ModelCompositeDTO]:
    repo = _repository(request)
    rows = repo.list_model_composites(model_id)
    return [_model_composite_dto(row) for row in rows]


# ================================================================
# Walk-forward (15-03)
# ================================================================


def _wf_plan_dto(row: dict[str, Any]) -> WfPlanDTO:
    geometry = row.get("fold_geometry") or {}
    folds = geometry.get("folds") or []
    oos_fold = geometry.get("oos_fold") or {}
    return WfPlanDTO(
        id=row["id"],
        strategy_id=row.get("strategy_id"),
        n_folds=len(folds),
        train_size=row["train_size"],
        test_size=row["test_size"],
        gap=row.get("gap_size", 0),
        oos_start=oos_fold.get("test_start"),
        oos_end=oos_fold.get("test_end"),
        pinned=bool(row.get("oos_pinned_at")),
        created_at=row["created_at"],
    )


@router.get("/wf/plans", response_model=list[WfPlanDTO])
async def list_wf_plans(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfPlanDTO]:
    repo = _repository(request)
    rows = repo.list_wf_plans(limit=limit)
    return [_wf_plan_dto(row) for row in rows]


def _wf_fold_dto(row: dict[str, Any]) -> WfFoldDTO:
    return WfFoldDTO(
        id=row["id"],
        plan_id=row["plan_id"],
        fold_index=row["fold_index"],
        train_start=row["train_start"],
        train_end=row["train_end"],
        test_start=row["test_start"],
        test_end=row["test_end"],
        is_oos=bool(row["is_oos"]),
        created_at=row["created_at"],
    )


@router.get("/wf/folds", response_model=list[WfFoldDTO])
async def list_wf_folds(
    request: Request,
    plan_id: str | None = None,
    is_oos: bool | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfFoldDTO]:
    repo = _repository(request)
    rows = repo.list_wf_folds(plan_id=plan_id, is_oos=is_oos, limit=limit)
    return [_wf_fold_dto(row) for row in rows]


def _wf_search_run_dto(row: dict[str, Any]) -> WfSearchRunDTO:
    return WfSearchRunDTO(
        id=row["id"],
        plan_id=row.get("plan_id"),
        strategy_id=row.get("strategy_id"),
        n_trials=row["n_trials"],
        best_score=row.get("best_score"),
        best_params=row.get("best_params"),
        score_distribution=row.get("score_distribution"),
        status=row.get("status", "completed"),
        created_at=row["created_at"],
    )


@router.get("/wf/search-runs", response_model=list[WfSearchRunDTO])
async def list_wf_search_runs(
    request: Request,
    plan_id: str | None = None,
    strategy_id: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfSearchRunDTO]:
    repo = _repository(request)
    rows = repo.list_wf_search_runs(plan_id=plan_id, strategy_id=strategy_id, limit=limit)
    return [_wf_search_run_dto(row) for row in rows]


def _validated_strategy_dto(row: dict[str, Any]) -> WfValidatedStrategyDTO:
    return WfValidatedStrategyDTO(
        id=row["id"],
        strategy_id=row["strategy_id"],
        plan_id=row.get("plan_id"),
        validated=bool(row["passed_gate"]),
        oos_score=row.get("validation_score"),
        details=row.get("fold_evidence"),
        created_at=row["created_at"],
    )


@router.get("/wf/validated", response_model=list[WfValidatedStrategyDTO])
async def list_validated_strategies(
    request: Request,
    strategy_id: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfValidatedStrategyDTO]:
    repo = _repository(request)
    rows = repo.list_validated_strategies(strategy_id=strategy_id, limit=limit)
    return [_validated_strategy_dto(row) for row in rows]


def _wf_ensemble_dto(row: dict[str, Any]) -> WfEnsembleDTO:
    return WfEnsembleDTO(
        id=row["id"],
        name=row["name"],
        strategy_ids=row.get("strategy_ids", []),
        method=row.get("method", "rank_average"),
        output_snapshot_sha256=row.get("output_sha256"),
        created_at=row["created_at"],
    )


@router.get("/wf/ensembles", response_model=list[WfEnsembleDTO])
async def list_wf_ensembles(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
) -> list[WfEnsembleDTO]:
    repo = _repository(request)
    rows = repo.list_wf_ensembles(limit=limit)
    return [_wf_ensemble_dto(row) for row in rows]
