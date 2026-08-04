"""Server-owned strict DTOs for Phase 15 research + portfolio panel routes.

Every panel response type is pinned here — the frontend ``api.ts`` strictly
consumes these shapes.  ``extra="forbid"`` on every model means an unknown
field in either direction is a hard rejection, not a silent ignore.

Decision (15-02 checkpoint:decision): option-a — one module for all DTOs.
Shared types (e.g. PaperStateDTO) cross both routers; a single module avoids
circular imports and makes the contract boundary explicit.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Base: strict, frozen, extra fields forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ================================================================
# Portfolio panel DTOs (UI-02)
# ================================================================


class OptimizationRunDTO(_Strict):
    id: str
    objective: str
    as_of: str
    universe: str
    model_id: str | None = None
    composite_snapshot_id: str | None = None
    input_snapshot_sha256: str
    expected_return_method: str
    risk_model: str
    risk_model_detail: dict[str, Any] | None = None
    constraint_stack: dict[str, Any] | None = None
    solver_name: str
    solver_version: str
    solver_options: dict[str, Any] | None = None
    problem_status: str
    failure_reason: str | None = None
    output_weights: dict[str, Any] | None = None
    baseline_weights: dict[str, Any] | None = None
    output_sha256: str
    weights_artifact_relative_path: str | None = None
    created_at: str


class AttributionEvidenceDTO(_Strict):
    id: str
    run_id: str
    attribution_type: str
    risk_model: str | None = None
    contributions: dict[str, Any] | None = None
    reconciliation: dict[str, Any] | None = None
    output_sha256: str | None = None
    artifact_relative_path: str | None = None
    created_at: str


class RebalancePlanDTO(_Strict):
    id: str
    optimization_run_id: str
    input_snapshot_sha256: str
    as_of: str
    target_weights: dict[str, Any] | None = None
    discrete_weights: dict[str, Any] | None = None
    lot_sizes: dict[str, Any] | None = None
    cash_residue: float
    turnover_cost: float
    blocked_instruments: dict[str, Any] | None = None
    discretization_rmse: float
    rmse_definition: str
    expires_at: str
    output_sha256: str
    artifact_relative_path: str | None = None
    created_at: str


class PaperTransitionDTO(_Strict):
    id: int
    plan_id: str
    transition: str
    idempotency_key: str
    previous_state: str | None = None
    paper_position_delta: dict[str, Any] | None = None
    created_at: str


class PaperStateDTO(_Strict):
    plan_id: str
    current_state: str | None = None
    transitions: list[PaperTransitionDTO] = Field(default_factory=list)


class PaperActionRequest(_Strict):
    idempotency_key: str = Field(min_length=1)


class PaperActionResponse(_Strict):
    plan_id: str
    transition: str
    current_state: str
    idempotent: bool


# ================================================================
# Research panel DTOs (UI-01)
# ================================================================


class FactorRevisionDTO(_Strict):
    id: str
    factor_id: str
    revision_number: int
    name: str
    expression: str
    description: str = ""
    status: str
    fields: dict[str, Any] | None = None
    operators: dict[str, Any] | None = None
    functions: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    created_at: str


class AdmissionVerdictDTO(_Strict):
    revision_id: str
    policy_version: str
    admitted: bool
    reason: str | None = None
    details: dict[str, Any] | None = None
    created_at: str

class ModelDefinitionDTO(_Strict):

    model_id: str
    name: str
    weighting: str
    revision_ids: list[str] = Field(default_factory=list)
    weights: dict[str, Any] | None = None
    input_snapshot_sha256: str | None = None
    created_at: str


class ModelCompositeDTO(_Strict):
    id: str
    model_id: str
    input_snapshot_sha256: str
    output_sha256: str
    output_artifact_relative_path: str | None = None
    mean_ic: float | None = None
    membership_fingerprint: str | None = None
    created_at: str


class WfPlanDTO(_Strict):
    id: str
    strategy_id: str | None = None
    n_folds: int
    train_size: int
    test_size: int
    gap: int
    oos_start: str | None = None
    oos_end: str | None = None
    pinned: bool = True
    created_at: str


class WfFoldDTO(_Strict):
    id: str
    plan_id: str
    fold_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    is_oos: bool = False
    created_at: str


class WfSearchRunDTO(_Strict):
    id: str
    plan_id: str | None = None
    strategy_id: str | None = None
    n_trials: int
    best_score: float | None = None
    best_params: dict[str, Any] | None = None
    score_distribution: dict[str, Any] | None = None
    status: str = "completed"
    created_at: str


class WfValidatedStrategyDTO(_Strict):
    id: str
    strategy_id: str
    plan_id: str | None = None
    validated: bool
    oos_score: float | None = None
    details: dict[str, Any] | None = None
    created_at: str


class WfEnsembleDTO(_Strict):
    id: str
    name: str
    strategy_ids: list[str] = Field(default_factory=list)
    method: str = "rank_average"
    output_snapshot_sha256: str | None = None
    created_at: str
