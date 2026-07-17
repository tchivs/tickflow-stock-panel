"""Strict public contracts for immutable Shadow evidence and candidates."""
from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrictShadowModel(BaseModel):
    """Reject undeclared authority at every Shadow trust boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


MAX_ASSUMPTION_DEPTH = 2
MAX_ASSUMPTION_KEYS = 16
MAX_ASSUMPTION_LIST_ITEMS = 32
MAX_ASSUMPTION_STRING_BYTES = 128
MAX_ASSUMPTION_NUMBER = 1_000_000_000_000
MAX_ASSUMPTION_OBJECT_BYTES = 4_096
MAX_ASSUMPTION_COMBINED_BYTES = 8_192


class ShadowAssumptionError(ValueError):
    """An assumption payload crossed its strict schema or resource boundary."""


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def _validate_assumption_value(value: object, *, depth: int, field: str) -> None:
    if isinstance(value, str):
        if _utf8_size(value) > MAX_ASSUMPTION_STRING_BYTES:
            raise ShadowAssumptionError(
                f"{field} strings must not exceed {MAX_ASSUMPTION_STRING_BYTES} UTF-8 bytes"
            )
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)) or abs(value) > MAX_ASSUMPTION_NUMBER:
            raise ShadowAssumptionError(f"{field} numbers must be finite and bounded")
        return
    if isinstance(value, Mapping):
        if depth > MAX_ASSUMPTION_DEPTH:
            raise ShadowAssumptionError(
                f"{field} collections must not exceed depth {MAX_ASSUMPTION_DEPTH}"
            )
        if len(value) > MAX_ASSUMPTION_KEYS:
            raise ShadowAssumptionError(
                f"{field} mappings must not exceed {MAX_ASSUMPTION_KEYS} keys"
            )
        for key, item in value.items():
            if not isinstance(key, str):
                raise ShadowAssumptionError(f"{field} mapping keys must be strings")
            _validate_assumption_value(key, depth=depth, field=field)
            _validate_assumption_value(item, depth=depth + 1, field=field)
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if depth > MAX_ASSUMPTION_DEPTH:
            raise ShadowAssumptionError(
                f"{field} collections must not exceed depth {MAX_ASSUMPTION_DEPTH}"
            )
        if len(value) > MAX_ASSUMPTION_LIST_ITEMS:
            raise ShadowAssumptionError(
                f"{field} lists must not exceed {MAX_ASSUMPTION_LIST_ITEMS} entries"
            )
        for item in value:
            _validate_assumption_value(item, depth=depth + 1, field=field)
        return
    raise ShadowAssumptionError(f"{field} contains an unsupported value")


def _canonical_json(value: object, *, field: str) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ShadowAssumptionError(f"{field} must be canonical JSON") from error


def _raw_assumption_object(value: object, *, field: str) -> dict[str, object]:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)
    if not isinstance(value, Mapping):
        raise ShadowAssumptionError(f"{field} must be an object")
    raw = dict(value)
    _validate_assumption_value(raw, depth=0, field=field)
    encoded = _canonical_json(raw, field=field)
    if _utf8_size(encoded) > MAX_ASSUMPTION_OBJECT_BYTES:
        raise ShadowAssumptionError(
            f"{field} must not exceed {MAX_ASSUMPTION_OBJECT_BYTES} canonical bytes"
        )
    return raw


class ExitAssumptions(StrictShadowModel):
    """The fixed exit horizon currently consumed by Shadow evaluation/backtest."""

    kind: Literal["fixed_holding_days"]
    days: int = Field(ge=1, le=252)

    @model_validator(mode="before")
    @classmethod
    def _bounded_object(cls, value: object) -> object:
        return _raw_assumption_object(value, field="exit assumptions")


class HoldingAssumptions(StrictShadowModel):
    """The governed price semantics consumed when replaying Shadow research."""

    price_adjustment: Literal[
        "unadjusted_execution_vs_forward_adjusted_research"
    ]

    @model_validator(mode="before")
    @classmethod
    def _bounded_object(cls, value: object) -> object:
        return _raw_assumption_object(value, field="holding assumptions")


@dataclass(frozen=True, slots=True)
class ValidatedAssumptions:
    exit: dict[str, object]
    holding: dict[str, object]
    exit_json: str
    holding_json: str
    combined_json: str


def validate_assumption_pair(
    *, exit_assumptions: object, holding_assumptions: object
) -> ValidatedAssumptions:
    """Validate and serialize both assumption objects identically at every boundary."""

    raw_exit = _raw_assumption_object(exit_assumptions, field="exit assumptions")
    raw_holding = _raw_assumption_object(holding_assumptions, field="holding assumptions")
    raw_combined_json = _canonical_json(
        {
            "exit_assumptions": raw_exit,
            "holding_assumptions": raw_holding,
        },
        field="combined assumptions",
    )
    if _utf8_size(raw_combined_json) > MAX_ASSUMPTION_COMBINED_BYTES:
        raise ShadowAssumptionError(
            f"combined assumptions must not exceed {MAX_ASSUMPTION_COMBINED_BYTES} canonical bytes"
        )
    try:
        exit_record = ExitAssumptions.model_validate(raw_exit).model_dump(
            mode="json", exclude_none=True
        )
        holding_record = HoldingAssumptions.model_validate(raw_holding).model_dump(
            mode="json", exclude_none=True
        )
    except ValidationError as error:
        raise ShadowAssumptionError("assumptions do not match the strict allowlist") from error
    exit_json = _canonical_json(exit_record, field="exit assumptions")
    holding_json = _canonical_json(holding_record, field="holding assumptions")
    combined_json = _canonical_json(
        {
            "exit_assumptions": exit_record,
            "holding_assumptions": holding_record,
        },
        field="combined assumptions",
    )
    return ValidatedAssumptions(
        exit=exit_record,
        holding=holding_record,
        exit_json=exit_json,
        holding_json=holding_json,
        combined_json=combined_json,
    )


def validate_persisted_assumption_pair(
    *, exit_json: object, holding_json: object
) -> ValidatedAssumptions:
    """Reject non-canonical, oversized, or schema-divergent historical facts."""

    if not isinstance(exit_json, str) or not isinstance(holding_json, str):
        raise ShadowAssumptionError("persisted assumptions are invalid")
    if _utf8_size(exit_json) > MAX_ASSUMPTION_OBJECT_BYTES or _utf8_size(
        holding_json
    ) > MAX_ASSUMPTION_OBJECT_BYTES:
        raise ShadowAssumptionError("persisted assumptions exceed the canonical byte boundary")
    try:
        exit_value = json.loads(exit_json)
        holding_value = json.loads(holding_json)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ShadowAssumptionError("persisted assumptions are invalid") from error
    validated = validate_assumption_pair(
        exit_assumptions=exit_value,
        holding_assumptions=holding_value,
    )
    if validated.exit_json != exit_json or validated.holding_json != holding_json:
        raise ShadowAssumptionError("persisted assumptions are not canonical")
    return validated


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
    exit_assumptions: ExitAssumptions
    holding_assumptions: HoldingAssumptions
    source_batch_ids: list[Identifier] = Field(min_length=1, max_length=128)
    seed: int
    class_balance: dict[str, int]
    metrics: dict[str, float | int]
    limitations: list[str] = Field(min_length=1, max_length=16)
    created_at: datetime
