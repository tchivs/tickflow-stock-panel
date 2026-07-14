"""Strict request and public DTO contracts for controlled advanced workflows."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictAdvancedModel(BaseModel):
    """Reject undeclared fields at every browser or provider trust boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Identifier = str
AssetType = Literal["stock", "etf", "index"]
Confidence = Literal["low", "medium", "high"]
JobStage = Literal["authorized", "frozen", "drafted", "gates_complete", "awaiting_review", "recorded", "rejected"]
TerminalState = Literal["unevaluable", "insufficient_sample", "rejected", "constraint_failed", "awaiting_review", "recorded"]


class EvidenceReference(StrictAdvancedModel):
    id: Identifier = Field(min_length=1, max_length=128)
    published_at: datetime | None = None


class ViewpointRequest(StrictAdvancedModel):
    source_profile: Literal["operator-research-v1"]
    market_scope: Literal["CN-A"]
    asset_type: AssetType
    instrument: Identifier = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Z.\-]+$")
    published_at: datetime
    direction: Literal["bullish", "bearish", "neutral"]
    conclusion: str = Field(min_length=1, max_length=4_000)
    rating: Literal["overweight", "neutral", "underweight"]
    target_range: tuple[float, float]
    horizon_days: int = Field(ge=1, le=365)
    confidence: Confidence
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=32)
    evaluation_window_days: Literal[20, 60, 120]
    benchmark: Literal["000300.SH", "000905.SH", "000852.SH"] | None = None

    @model_validator(mode="after")
    def _target_range_is_ordered(self) -> ViewpointRequest:
        if self.target_range[0] > self.target_range[1]:
            raise ValueError("target_range must be ordered")
        return self


class ViewpointRevisionRequest(StrictAdvancedModel):
    conclusion: str | None = Field(default=None, min_length=1, max_length=4_000)
    direction: Literal["bullish", "bearish", "neutral"] | None = None
    rating: Literal["overweight", "neutral", "underweight"] | None = None
    target_range: tuple[float, float] | None = None
    horizon_days: int | None = Field(default=None, ge=1, le=365)
    confidence: Confidence | None = None
    evidence: list[EvidenceReference] | None = Field(default=None, min_length=1, max_length=32)


class ViewpointCorrectionRequest(ViewpointRevisionRequest):
    correction_reason: str = Field(min_length=1, max_length=1_000)


class FrozenStrategyScope(StrictAdvancedModel):
    """The complete immutable input contract for a governed strategy backtest."""

    market: Literal["CN-A"]
    strategy_id: Identifier = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    start: date
    end: date
    symbols: list[Identifier] | None = Field(default=None, max_length=64)
    asset_type: AssetType
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=32)

    @field_validator("symbols")
    @classmethod
    def _symbols_are_supported_identifiers(cls, value: list[Identifier] | None) -> list[Identifier] | None:
        if value is None:
            return None
        if not value or len(set(value)) != len(value):
            raise ValueError("symbols must be a non-empty unique list")
        if any(not 1 <= len(symbol) <= 32 or not _instrument_identifier(symbol) for symbol in value):
            raise ValueError("symbols must be valid instrument identifiers")
        return value

    @field_validator("parameters")
    @classmethod
    def _parameter_names_are_bounded(cls, value: dict[str, str | int | float | bool | None]) -> dict[str, str | int | float | bool | None]:
        if any(not 1 <= len(key) <= 64 or not key.replace("_", "").isalnum() for key in value):
            raise ValueError("parameter names must be bounded identifiers")
        return value

    @model_validator(mode="after")
    def _date_range_is_ordered(self) -> FrozenStrategyScope:
        if self.start > self.end:
            raise ValueError("start must not be after end")
        return self



class BoundStrategyBinding(StrictAdvancedModel):
    """Server-owned reverse binding attached to a persisted experiment specification."""

    strategy_id: Identifier = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    research_asset_id: Identifier = Field(min_length=1, max_length=128)
    revision: Identifier = Field(min_length=1, max_length=128)

def _instrument_identifier(value: str) -> bool:
    return all(character.isalnum() or character in ".-" for character in value)


class ExperimentSpecificationRequest(StrictAdvancedModel):
    research_asset_id: Identifier = Field(min_length=1, max_length=128)
    hypothesis: str = Field(min_length=1, max_length=4_000)
    data_scope: FrozenStrategyScope
    method: str = Field(min_length=1, max_length=256)
    metrics: list[str] = Field(min_length=1, max_length=16)
    success_criteria: dict[str, str | int | float | bool | None] = Field(min_length=1, max_length=16)
    failure_criteria: dict[str, str | int | float | bool | None] = Field(min_length=1, max_length=16)


class ExperimentRunRequest(StrictAdvancedModel):
    specification_id: Identifier = Field(min_length=1, max_length=128)
    governed_input_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    asset_version_reference: Identifier = Field(min_length=1, max_length=128)
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=32)
    resource_manifest: dict[str, str | int | float | bool] = Field(min_length=1, max_length=16)


class ResearchFeedbackRequest(StrictAdvancedModel):
    run_id: Identifier = Field(min_length=1, max_length=128)
    conclusion: Literal["supported", "refuted", "inconclusive", "needs_replication"]
    metrics_reference: Identifier = Field(min_length=1, max_length=128)
    artifact_references: list[Identifier] = Field(default_factory=list, max_length=32)
    notes: str = Field(min_length=1, max_length=4_000)


class StrategyCandidateRequest(StrictAdvancedModel):
    parent_asset_version: Identifier = Field(min_length=1, max_length=128)
    mutation_operation: Literal["parameter_adjustment", "feature_subset", "signal_threshold", "portfolio_constraint"]
    seed: int = Field(ge=0, le=2_147_483_647)
    resolved_configuration: dict[str, str | int | float | bool] = Field(min_length=1, max_length=64)


class CompletedRunCandidateRequest(StrictAdvancedModel):
    completed_run_id: Identifier = Field(min_length=1, max_length=128)
    mutation_operation: Literal["adjust_signal_threshold", "parameter_adjustment", "feature_subset", "signal_threshold", "portfolio_constraint"]
    seed: int = Field(ge=0, le=2_147_483_647)
    resolved_configuration: dict[str, str | int | float | bool | None] = Field(min_length=1, max_length=64)


class GateEvaluationRequest(StrictAdvancedModel):
    """Gate verdicts have no browser-provided evidence, status, or authority."""


class PromotionGateRequest(StrictAdvancedModel):
    candidate_id: Identifier = Field(min_length=1, max_length=128)
    gate: Literal["contract_sandbox", "provenance", "in_sample_out_of_sample", "robustness", "cost_feasibility"]
    evidence_reference: Identifier = Field(min_length=1, max_length=128)


class PromotionApprovalRequest(StrictAdvancedModel):
    candidate_id: Identifier = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=10, max_length=4_000)


class AuthorizationTaskRequest(StrictAdvancedModel):
    authorization_token: str = Field(min_length=16, max_length=512)
    task_type: Literal["research_draft", "experiment", "strategy_evaluation"]
    market: Literal["CN-A"]
    instrument: Identifier = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Z.\-]+$")
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class CustomStrategyContract(StrictAdvancedModel):
    contract_version: Literal["advanced-strategy-v1"]
    parent_asset_id: Identifier = Field(min_length=1, max_length=128)
    declared_inputs: tuple[Literal["governed_panel"], ...] = Field(min_length=1, max_length=1)
    declared_imports: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    timeout_seconds: int = Field(ge=1, le=60)
    memory_limit_mb: int = Field(ge=64, le=1_024)
    source_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @field_validator("declared_imports")
    @classmethod
    def _imports_are_simple_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.isidentifier() for item in value):
            raise ValueError("declared imports must be module names")
        if len(set(value)) != len(value):
            raise ValueError("declared imports must not contain duplicates")
        return value


class CustomStrategySubmission(StrictAdvancedModel):
    """Same-request source and contract admission; source never has a response DTO."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    contract: CustomStrategyContract
    source: str = Field(min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def _source_matches_declared_hash(self) -> CustomStrategySubmission:
        from hashlib import sha256

        actual = sha256(self.source.encode()).hexdigest()
        if actual != self.contract.source_sha256:
            raise ValueError("source_sha256 does not match source")
        return self


class AdvancedResearchAssetBinding(StrictAdvancedModel):
    """Read-only lifecycle-owned strategy-to-factor-revision projection."""

    strategy_id: Identifier = Field(min_length=1, max_length=128)
    research_asset_id: Identifier = Field(min_length=1, max_length=128)
    factor_name: str = Field(min_length=1, max_length=256)
    provenance: dict[str, object]


class SafeStatusDto(StrictAdvancedModel):
    id: Identifier = Field(min_length=1, max_length=128)
    status: TerminalState | JobStage
    label: str = Field(min_length=1, max_length=256)
    occurred_at: datetime | str
    audit_reference: Identifier | None = Field(default=None, max_length=128)


class AdvancedJobDto(StrictAdvancedModel):
    id: Identifier = Field(min_length=1, max_length=128)
    subject: dict[Literal["kind", "key"], str]
    status: JobStage
    stage: JobStage
    stage_recorded_at: datetime | str
    audit_reference: Identifier | None = Field(default=None, max_length=128)


class AuditSummaryDto(StrictAdvancedModel):
    reference: Identifier = Field(min_length=1, max_length=128)
    decision: Literal["authorized", "rejected", "recorded"]
    reason: str = Field(min_length=1, max_length=128)


class SandboxValidationDto(StrictAdvancedModel):
    status: Literal["rejected", "validated", "constraint_failed"]
    reason: str = Field(min_length=1, max_length=128)
    audit_reference: Identifier = Field(min_length=1, max_length=128)
    source_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
