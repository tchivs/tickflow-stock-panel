"""Strict public contracts for immutable Shadow evidence and candidates."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrictShadowModel(BaseModel):
    """Reject undeclared authority at every Shadow trust boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class ImportMapping(StrictShadowModel):
    broker_fill_id: str | None = Field(default=None, min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=128)
    executed_at: str = Field(min_length=1, max_length=128)
    quantity: str = Field(min_length=1, max_length=128)
    price: str = Field(min_length=1, max_length=128)
    fees: str | None = Field(default=None, min_length=1, max_length=128)
    currency: str | None = Field(default=None, min_length=1, max_length=128)
    account_alias: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def _source_columns_are_unique(self) -> ImportMapping:
        values = [value for value in self.model_dump().values() if value is not None]
        if len(values) != len(set(values)):
            raise ValueError("mapping source columns must be unique")
        return self


class ImportDiagnostic(StrictShadowModel):
    severity: Literal["error", "warning"]
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    message: str = Field(min_length=1, max_length=512)
    source_row_ordinal: int | None = Field(default=None, ge=1)


class ArtifactDescriptor(StrictShadowModel):
    artifact_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    relative_path: str = Field(min_length=1, max_length=256)
    content_type: str = Field(min_length=1, max_length=128)
    byte_size: int = Field(ge=0)
    checksum_sha256: Sha256
    schema_version: str = Field(min_length=1, max_length=64)
    scope_sha256: Sha256
    created_at: datetime

    @field_validator("relative_path")
    @classmethod
    def _relative_managed_path(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or ".." in value.replace("\\", "/").split("/"):
            raise ValueError("artifact path must be relative and contained")
        return value


class ImportPreviewRequest(StrictShadowModel):
    filename: str = Field(min_length=1, max_length=255)
    media_type: Literal[
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]
    mapping: ImportMapping
    source_timezone: str = Field(min_length=1, max_length=64)


class ImportConfirmationRequest(ImportPreviewRequest):
    principal: Identifier
    source_label: str = Field(min_length=1, max_length=256)
    supersedes_batch_id: Identifier | None = None


class EvidenceExclusion(StrictShadowModel):
    trade_id: Identifier
    reason: str = Field(min_length=1, max_length=1_000)


class EvidenceSetRequest(StrictShadowModel):
    included_batch_ids: list[Identifier] = Field(min_length=1, max_length=128)
    included_trade_ids: list[Identifier] = Field(max_length=100_000)
    exclusions: list[EvidenceExclusion] = Field(max_length=100_000)

    @model_validator(mode="after")
    def _membership_is_unambiguous(self) -> EvidenceSetRequest:
        if len(self.included_batch_ids) != len(set(self.included_batch_ids)):
            raise ValueError("included batch identifiers must be unique")
        if len(self.included_trade_ids) != len(set(self.included_trade_ids)):
            raise ValueError("included trade identifiers must be unique")
        excluded = [item.trade_id for item in self.exclusions]
        if len(excluded) != len(set(excluded)) or set(excluded) & set(self.included_trade_ids):
            raise ValueError("evidence exclusions must be unique and disjoint")
        return self


class RuleCondition(StrictShadowModel):
    field: Literal["close_return_5d", "volume_ratio_20d", "intraday_range"]
    operator: Literal["<=", ">"]
    threshold: float


class CandidateRule(StrictShadowModel):
    conditions: list[RuleCondition] = Field(min_length=1, max_length=3)
    prediction: Literal["entry"]
    support: int = Field(ge=1)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)


class CandidateResult(StrictShadowModel):
    id: Identifier
    evidence_set_id: Identifier
    evidence_set_fingerprint: Sha256
    distiller_version: str = Field(min_length=1, max_length=64)
    rule_schema_version: str = Field(min_length=1, max_length=64)
    rules: list[CandidateRule] = Field(min_length=1, max_length=8)
    features: list[str] = Field(min_length=1, max_length=3)
    parameters: dict[str, object]
    source_batch_ids: list[Identifier] = Field(min_length=1, max_length=128)
    seed: int
    class_balance: dict[str, int]
    metrics: dict[str, float | int]
    limitations: list[str] = Field(min_length=1, max_length=16)
    created_at: datetime
