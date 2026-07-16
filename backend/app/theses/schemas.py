"""Strict request and evidence contracts for immutable investment theses."""
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]+$")
_INSTRUMENT = re.compile(r"^[0-9A-Z.-]+$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_SAFE_TEXT_FORBIDDEN = ("${", "jndi:", "\x00")

MARKET_FIELDS: dict[str, frozenset[str]] = {
    "close": frozenset({"CNY"}),
    "open": frozenset({"CNY"}),
    "high": frozenset({"CNY"}),
    "low": frozenset({"CNY"}),
    "volume": frozenset({"shares"}),
    "amount": frozenset({"CNY"}),
}
FINANCIAL_FIELDS: dict[str, frozenset[str]] = {
    "revenue_growth_yoy": frozenset({"ratio"}),
    "net_income_growth_yoy": frozenset({"ratio"}),
    "gross_margin": frozenset({"ratio"}),
    "roe": frozenset({"ratio"}),
}
ANALYSIS_FIELDS: dict[str, frozenset[str]] = {
    "report_score": frozenset({"score"}),
}
CONDITION_FIELDS: dict[str, dict[str, frozenset[str]]] = {
    "market": MARKET_FIELDS,
    "financial": FINANCIAL_FIELDS,
    "analysis": ANALYSIS_FIELDS,
}


class StrictThesisModel(BaseModel):
    """Reject undeclared fields at every Thesis trust boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConditionCheckResult(StrEnum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ERROR = "error"


class EvidenceStatus(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    ERROR = "error"


class ValuationAssumption(StrictThesisModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    value: float
    unit: str = Field(min_length=1, max_length=24, pattern=r"^[A-Za-z][A-Za-z0-9_/%.-]*$")

    @field_validator("value")
    @classmethod
    def _value_is_finite(cls, value: float) -> float:
        if isinstance(value, bool) or not math.isfinite(value):
            raise ValueError("assumption value must be finite")
        return value


class ValuationAnchor(StrictThesisModel):
    method: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    currency: str = Field(min_length=3, max_length=3)
    as_of: date
    low: float
    high: float
    assumptions: list[ValuationAssumption] = Field(min_length=1, max_length=32)
    limitations: list[str] = Field(min_length=1, max_length=16)

    @field_validator("currency")
    @classmethod
    def _currency_is_canonical(cls, value: str) -> str:
        if not _CURRENCY.fullmatch(value):
            raise ValueError("currency must be an ISO-style uppercase code")
        return value

    @field_validator("low", "high")
    @classmethod
    def _range_value_is_finite(cls, value: float) -> float:
        if isinstance(value, bool) or not math.isfinite(value):
            raise ValueError("valuation range values must be finite")
        return value

    @field_validator("limitations")
    @classmethod
    def _limitations_are_bounded(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 500 or _unsafe_text(value) for value in values):
            raise ValueError("limitations must be non-empty bounded text")
        return values

    @model_validator(mode="after")
    def _range_is_ordered(self) -> "ValuationAnchor":
        if self.high < self.low:
            raise ValueError("valuation high must not be below low")
        names = [item.name for item in self.assumptions]
        if len(names) != len(set(names)):
            raise ValueError("assumption names must be unique")
        return self


class ThesisCondition(StrictThesisModel):
    source_kind: Literal["market", "financial", "analysis"]
    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    operator: Literal["lt", "lte", "gt", "gte", "eq", "between"]
    threshold: float | tuple[float, float]
    unit: str = Field(min_length=1, max_length=24, pattern=r"^[A-Za-z][A-Za-z0-9_/%.-]*$")
    lookback_days: int = Field(ge=1, le=3660)
    cadence: Literal["daily", "weekly", "monthly", "quarterly"]
    timezone: Literal["Asia/Shanghai"]
    description: str = Field(min_length=1, max_length=500)

    @field_validator("threshold")
    @classmethod
    def _threshold_is_finite(cls, value: float | tuple[float, float]) -> float | tuple[float, float]:
        values = value if isinstance(value, tuple) else (value,)
        if any(isinstance(item, bool) or not math.isfinite(item) for item in values):
            raise ValueError("condition threshold must be finite")
        return value

    @field_validator("description")
    @classmethod
    def _description_is_safe(cls, value: str) -> str:
        if _unsafe_text(value):
            raise ValueError("condition description contains forbidden control syntax")
        return value

    @model_validator(mode="after")
    def _shape_is_allowlisted(self) -> "ThesisCondition":
        allowed_units = CONDITION_FIELDS[self.source_kind].get(self.field)
        if allowed_units is None:
            raise ValueError("condition field is not allowed for its source")
        if self.unit not in allowed_units:
            raise ValueError("condition unit is incompatible with its source field")
        if self.operator == "between":
            if not isinstance(self.threshold, tuple) or len(self.threshold) != 2:
                raise ValueError("between requires an ordered two-value threshold")
            if self.threshold[0] > self.threshold[1]:
                raise ValueError("between threshold must be ordered")
        elif isinstance(self.threshold, tuple):
            raise ValueError("scalar operators require one threshold")
        return self


class ThesisVersionRequest(StrictThesisModel):
    instrument: str = Field(min_length=1, max_length=32)
    core_judgment: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(min_length=1, max_length=8000)
    change_reason: str = Field(min_length=1, max_length=1000)
    anchors: list[ValuationAnchor] = Field(min_length=1, max_length=16)
    conditions: list[ThesisCondition] = Field(min_length=1, max_length=32)

    @field_validator("instrument")
    @classmethod
    def _instrument_is_canonical(cls, value: str) -> str:
        value = value.upper()
        if not _INSTRUMENT.fullmatch(value):
            raise ValueError("instrument must be a canonical market identifier")
        return value

    @field_validator("core_judgment", "rationale", "change_reason")
    @classmethod
    def _version_text_is_safe(cls, value: str) -> str:
        if _unsafe_text(value):
            raise ValueError("thesis text contains forbidden control syntax")
        return value


class ThesisRevisionRequest(StrictThesisModel):
    expected_predecessor_id: str = Field(min_length=1, max_length=128)
    change_reason: str = Field(min_length=1, max_length=1000)
    core_judgment: str | None = Field(default=None, min_length=1, max_length=4000)
    rationale: str | None = Field(default=None, min_length=1, max_length=8000)
    anchors: list[ValuationAnchor] | None = Field(default=None, min_length=1, max_length=16)
    conditions: list[ThesisCondition] | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("expected_predecessor_id")
    @classmethod
    def _predecessor_is_opaque_identifier(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("expected predecessor must be an opaque identifier")
        return value

    @field_validator("change_reason", "core_judgment", "rationale")
    @classmethod
    def _revision_text_is_safe(cls, value: str | None) -> str | None:
        if value is not None and _unsafe_text(value):
            raise ValueError("revision text contains forbidden control syntax")
        return value


class ReviewDecisionRequest(StrictThesisModel):
    pending_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=1, max_length=4000)


class EvidenceFact(StrictThesisModel):
    """Server-owned bounded evidence returned by a governed source reader."""

    status: EvidenceStatus
    source_kind: Literal["market", "financial", "analysis"]
    source_id: str = Field(min_length=1, max_length=256)
    as_of: date | datetime | None = None
    observed_value: float | None = None
    unit: str | None = Field(default=None, max_length=24)
    source_revision: str | None = Field(default=None, max_length=128)
    evidence_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    safe_reason: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _status_has_consistent_value(self) -> "EvidenceFact":
        if self.status is EvidenceStatus.OBSERVED:
            if self.observed_value is None or isinstance(self.observed_value, bool) or not math.isfinite(self.observed_value):
                raise ValueError("observed evidence requires a finite numeric value")
            if self.as_of is None or self.unit is None:
                raise ValueError("observed evidence requires as_of and unit")
        elif self.observed_value is not None:
            raise ValueError("missing or error evidence cannot carry an observed value")
        return self


class ConditionEvaluation(StrictThesisModel):
    result: ConditionCheckResult
    observed_value: float | None = None
    evidence_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    safe_reason: str | None = Field(default=None, max_length=256)


def _unsafe_text(value: str) -> bool:
    lowered = value.lower()
    return any(fragment in lowered for fragment in _SAFE_TEXT_FORBIDDEN) or any(
        ord(character) < 32 and character not in "\n\t" for character in value
    )
