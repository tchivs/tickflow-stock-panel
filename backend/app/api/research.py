"""Typed, validated researcher workflow mounted in the existing FastAPI host."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal, Mapping

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.research.factor_dsl import ALLOWED_FIELDS, DSL_VERSION, FactorDslError, parse_factor
from app.research.hypotheses import HypothesisUnavailableError


router = APIRouter(prefix="/api/research", tags=["research"])


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DslValidationRequest(_StrictModel):
    expression: str


class ManualFactorRequest(_StrictModel):
    name: str = Field(min_length=1, max_length=200)
    expression: str = Field(min_length=1, max_length=1000)
    description: str = ""
    hypothesis: str = ""


class FactorRevisionRequest(ManualFactorRequest):
    pass


class SimilarityRequest(_StrictModel):
    expression: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=20, ge=1, le=100)
    exclude_revision_id: str | None = None


class HypothesisDraftRequest(_StrictModel):
    hypothesis: str = Field(min_length=1, max_length=4000)
    options: dict[str, str] | None = None


class ReviewedDraftRequest(_StrictModel):
    draft_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    expression: str = Field(min_length=1, max_length=1000)
    explanation: str = Field(min_length=1, max_length=4000)
    provenance: dict[str, Any]
    reviewed: Literal[True]
    factor_id: str | None = None
    description: str = ""


class FactorEvaluationRequest(_StrictModel):
    universe: str = Field(min_length=1, max_length=300)
    symbols: list[str] = Field(min_length=1, max_length=1000)
    asset_type: Literal["stock", "etf"]
    start: date
    end: date
    forward_return_horizon: int = Field(ge=1, le=252)
    rebalance: Literal["daily", "weekly", "monthly"]
    missing_data_treatment: Literal["drop"]
    warmup_treatment: Literal["exclude"]
    warmup_days: int = Field(ge=0, le=252)
    n_groups: int = Field(ge=2, le=100)
    weight: Literal["equal", "factor_weight"]
    fees_pct: float = Field(ge=0)
    slippage_bps: float = Field(ge=0)


class CompareRequest(_StrictModel):
    experiment_ids: list[str] = Field(min_length=2, max_length=20)


def _state_service(request: Request, name: str) -> Any:
    value = getattr(request.app.state, name, None)
    if value is None:
        raise HTTPException(status_code=503, detail={"code": "RESEARCH_UNAVAILABLE", "message": f"{name} is unavailable"})
    return value


def _bad_request(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "RESEARCH_VALIDATION", "message": str(error)})


def _conflict(error: Exception) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": "RESEARCH_STATE_CONFLICT", "message": str(error)})


def _reviewed_model_provenance(revision: Any) -> Mapping[str, Any] | None:
    provenance = getattr(revision, "provenance", {})
    if not isinstance(provenance, Mapping) or provenance.get("source") != "reviewed_hypothesis":
        return None
    model = provenance.get("model_provenance")
    if not isinstance(model, Mapping):
        return None
    return {
        "provider": model.get("provider"),
        "model": model.get("model"),
        "model_version": model.get("model_version"),
        "provenance": {
            "prompt_template_version": model.get("prompt_template_version"),
            "generated_at": model.get("generated_at"),
            "draft_id": provenance.get("draft_id"),
        },
    }


def _validate_evaluation_guard(request: Request, payload: FactorEvaluationRequest) -> None:
    from app.api.backtest import FACTOR_MAX_SYMBOLS, _guard_server_backtest_range

    if payload.start > payload.end:
        raise _bad_request(ValueError("start and end must be an ordered date range"))
    if len(set(payload.symbols)) != len(payload.symbols):
        raise _bad_request(ValueError("symbols must not contain duplicates"))
    if len(payload.symbols) > FACTOR_MAX_SYMBOLS:
        raise _bad_request(ValueError(f"specified symbols exceed the maximum of {FACTOR_MAX_SYMBOLS}"))
    _guard_server_backtest_range(payload.start, payload.end)


@router.get("/dsl/options")
def dsl_options() -> dict[str, Any]:
    return {
        "dsl_version": DSL_VERSION,
        "fields": sorted(ALLOWED_FIELDS),
        "functions": {
            "abs": ["value"],
            "sign": ["value"],
            "log1p": ["value"],
            "clip": ["value", "lower_literal", "upper_literal"],
            "rank": ["value"],
            "zscore": ["value"],
            "rolling_mean": ["value", "window_literal_1_to_252"],
        },
        "operators": ["+", "-", "*", "/"],
    }


@router.post("/dsl/validate")
def validate_dsl(payload: DslValidationRequest) -> dict[str, Any]:
    try:
        parsed = parse_factor(payload.expression)
    except (FactorDslError, TypeError, ValueError) as error:
        raise _bad_request(error) from error
    return {
        "valid": True,
        "normalized_expression": parsed.canonical_expression,
        "dsl_version": parsed.dsl_version,
        "fields": sorted(parsed.features.fields),
        "operators": sorted(parsed.features.operators),
        "functions": sorted(parsed.features.functions),
    }


@router.post("/factors")
def create_factor(payload: ManualFactorRequest, request: Request) -> dict[str, Any]:
    registry = _state_service(request, "factor_registry")
    try:
        revision = registry.create_factor(
            name=payload.name,
            expression=payload.expression,
            description=payload.description,
            hypothesis=payload.hypothesis,
            provenance={"source": "manual"},
        )
    except (FactorDslError, TypeError, ValueError) as error:
        raise _bad_request(error) from error
    return revision.as_dict()


@router.get("/factors")
def list_factors(request: Request) -> dict[str, Any]:
    registry = _state_service(request, "factor_registry")
    return {"factors": [revision.as_dict() for revision in registry.list_current()]}


@router.get("/factors/{factor_id}/revisions")
def factor_history(factor_id: str, request: Request) -> dict[str, Any]:
    registry = _state_service(request, "factor_registry")
    history = registry.list_history(factor_id)
    if not history:
        raise HTTPException(status_code=404, detail={"code": "FACTOR_NOT_FOUND", "message": "factor definition does not exist"})
    return {"revisions": [revision.as_dict() for revision in history]}


@router.post("/factors/{factor_id}/revisions")
def revise_factor(factor_id: str, payload: FactorRevisionRequest, request: Request) -> dict[str, Any]:
    registry = _state_service(request, "factor_registry")
    try:
        revision = registry.revise_factor(
            factor_id,
            expression=payload.expression,
            name=payload.name,
            description=payload.description,
            hypothesis=payload.hypothesis,
            provenance={"source": "manual"},
        )
    except (FactorDslError, TypeError, ValueError) as error:
        if "does not exist" in str(error):
            raise HTTPException(status_code=404, detail={"code": "FACTOR_NOT_FOUND", "message": str(error)}) from error
        raise _bad_request(error) from error
    return revision.as_dict()


@router.post("/factors/similarity")
def discover_similar(payload: SimilarityRequest, request: Request) -> dict[str, Any]:
    registry = _state_service(request, "factor_registry")
    try:
        candidates = registry.discover_similar(
            payload.expression, limit=payload.limit, exclude_revision_id=payload.exclude_revision_id
        )
    except (FactorDslError, TypeError, ValueError) as error:
        raise _bad_request(error) from error
    return {"candidates": [candidate.as_dict() for candidate in candidates]}


@router.post("/hypotheses/drafts")
async def draft_hypothesis(payload: HypothesisDraftRequest, request: Request) -> dict[str, Any]:
    service = _state_service(request, "factor_hypothesis_service")
    try:
        return (await service.draft(hypothesis=payload.hypothesis, options=payload.options)).as_dict()
    except HypothesisUnavailableError as error:
        raise HTTPException(status_code=503, detail={"code": "HYPOTHESIS_PROVIDER_UNAVAILABLE", "message": str(error)}) from error
    except (FactorDslError, TypeError, ValueError) as error:
        raise _bad_request(error) from error


@router.post("/hypotheses/reviewed-factor")
def promote_reviewed_draft(payload: ReviewedDraftRequest, request: Request) -> dict[str, Any]:
    service = _state_service(request, "factor_hypothesis_service")
    registry = _state_service(request, "factor_registry")
    try:
        draft = service.reviewed_draft(
            draft_id=payload.draft_id,
            expression=payload.expression,
            explanation=payload.explanation,
            provenance=payload.provenance,
        )
        embedded_provenance = {
            "source": "reviewed_hypothesis",
            "draft_id": draft.draft_id,
            "model_provenance": dict(draft.provenance),
        }
        revision = registry.save_factor(
            name=payload.name,
            expression=draft.normalized_expression,
            factor_id=payload.factor_id,
            description=payload.description,
            hypothesis=draft.hypothesis,
            provenance=embedded_provenance,
        )
    except (FactorDslError, TypeError, ValueError) as error:
        if "factor definition does not exist" in str(error):
            raise HTTPException(status_code=404, detail={"code": "FACTOR_NOT_FOUND", "message": str(error)}) from error
        raise _bad_request(error) from error
    return revision.as_dict()


@router.post("/factor-revisions/{revision_id}/evaluate")
def evaluate_factor_revision(revision_id: str, payload: FactorEvaluationRequest, request: Request) -> dict[str, Any]:
    _validate_evaluation_guard(request, payload)
    evaluator = _state_service(request, "factor_evaluation_service")
    registry = _state_service(request, "factor_registry")
    catalog = _state_service(request, "experiment_catalog")
    try:
        from app.research.evaluation import FactorEvaluationConfig

        result = evaluator.evaluate(
            FactorEvaluationConfig(
                factor_revision_id=revision_id,
                universe=payload.universe,
                symbols=tuple(payload.symbols),
                asset_type=payload.asset_type,
                start=payload.start,
                end=payload.end,
                forward_return_horizon=payload.forward_return_horizon,
                rebalance=payload.rebalance,
                missing_data_treatment=payload.missing_data_treatment,
                warmup_treatment=payload.warmup_treatment,
                warmup_days=payload.warmup_days,
                n_groups=payload.n_groups,
                weight=payload.weight,
                fees_pct=payload.fees_pct,
                slippage_bps=payload.slippage_bps,
            )
        )
    except (TypeError, ValueError) as error:
        raise _bad_request(error) from error
    if result.status == "invalid":
        raise _bad_request(ValueError("; ".join(result.diagnostics)))
    if result.status != "completed":
        raise HTTPException(status_code=409, detail={"code": "EVALUATION_NOT_COMPLETED", "diagnostics": list(result.diagnostics)})
    revision = registry.get_revision(revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail={"code": "FACTOR_REVISION_NOT_FOUND", "message": "factor revision does not exist"})
    try:
        snapshot = catalog.record_factor_evaluation(result, model_provenance=_reviewed_model_provenance(revision))
    except (TypeError, ValueError) as error:
        raise _conflict(error) from error
    return {"evaluation": result.as_dict(), "experiment": snapshot.as_dict()}


@router.get("/experiments")
def list_experiments(request: Request) -> dict[str, Any]:
    catalog = _state_service(request, "experiment_catalog")
    return {"experiments": [snapshot.as_dict() for snapshot in catalog.list_history()]}


@router.get("/experiments/{experiment_id}")
def experiment_detail(experiment_id: str, request: Request) -> dict[str, Any]:
    catalog = _state_service(request, "experiment_catalog")
    snapshot = catalog.get(experiment_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "EXPERIMENT_NOT_FOUND", "message": "experiment does not exist"})
    return snapshot.as_dict()


@router.post("/experiments/{experiment_id}/retain")
def retain_experiment(experiment_id: str, request: Request) -> dict[str, Any]:
    catalog = _state_service(request, "experiment_catalog")
    try:
        return catalog.retain(experiment_id).as_dict()
    except ValueError as error:
        if "does not exist" in str(error):
            raise HTTPException(status_code=404, detail={"code": "EXPERIMENT_NOT_FOUND", "message": str(error)}) from error
        raise _conflict(error) from error


@router.get("/comparison/candidates")
def comparison_candidates(request: Request) -> dict[str, Any]:
    catalog = _state_service(request, "experiment_catalog")
    return {"experiments": [snapshot.as_dict() for snapshot in catalog.list_comparison_candidates()]}


@router.post("/comparison")
def compare_experiments(payload: CompareRequest, request: Request) -> dict[str, Any]:
    catalog = _state_service(request, "experiment_catalog")
    try:
        return catalog.compare(payload.experiment_ids).as_dict()
    except ValueError as error:
        if "does not exist" in str(error):
            raise HTTPException(status_code=404, detail={"code": "EXPERIMENT_NOT_FOUND", "message": str(error)}) from error
        raise _bad_request(error) from error


@router.post("/strategy-executions/{execution_handle}/retain")
def retain_strategy_execution(execution_handle: str, request: Request) -> dict[str, Any]:
    """Retain only the completed catalog snapshot mapped from a server-issued handle."""
    catalog = _state_service(request, "experiment_catalog")
    handles = _state_service(request, "research_strategy_handles")
    record = handles.get(execution_handle)
    if not isinstance(record, Mapping):
        raise HTTPException(status_code=404, detail={"code": "STRATEGY_EXECUTION_NOT_FOUND", "message": "strategy execution handle is unknown or stale"})
    if record.get("status") != "completed" or not isinstance(record.get("experiment_id"), str):
        raise _conflict(ValueError("strategy execution is not a completed validated result"))
    try:
        return catalog.retain(record["experiment_id"]).as_dict()
    except ValueError as error:
        raise _conflict(error) from error
