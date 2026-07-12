"""Strict, server-owned contracts for governed analysis evidence and reports."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SourceGrade = Literal["A", "B", "C"]
CrossCheckStatus = Literal["confirmed", "conflicting", "unresolved", "not_required"]
ContextStatus = Literal["ready", "context_insufficient"]


class TruncatedProvenance(BaseModel):
    """A hash/reference pair, never the untrusted raw material itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_locator: str
    content_sha256: str | None = None
    truncated: bool = True
    truncation_reason: str | None = None


class FrozenEvidenceSource(BaseModel):
    """One normalized governed source as available before model invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    grade: SourceGrade
    origin: str
    independence_group: str
    retrieved_at: datetime
    as_of: date
    period: str
    unit: str
    definition: str
    provenance: TruncatedProvenance


class MaterialNumberObservation(BaseModel):
    """A server-derived material value and its deterministic comparison state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    number_id: str
    source_id: str
    value: float
    unit: str
    period: str
    definition: str
    status: CrossCheckStatus
    peer_source_ids: tuple[str, ...] = ()
    comparison_reason: str | None = None

    @model_validator(mode="after")
    def _confirmed_requires_independent_peer(self) -> "MaterialNumberObservation":
        if self.status == "confirmed" and not self.peer_source_ids:
            raise ValueError("confirmed material number requires an independent peer")
        return self


class FrozenEvidenceSnapshot(BaseModel):
    """Immutable, model-safe input prepared by the server before generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_key: str = Field(min_length=1, max_length=128)
    policy_version: str = Field(min_length=1, max_length=64)
    context_status: ContextStatus
    sources: tuple[FrozenEvidenceSource, ...] = ()
    material_numbers: tuple[MaterialNumberObservation, ...] = ()
    evidence_fingerprint: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def _context_matches_sources(self) -> "FrozenEvidenceSnapshot":
        if self.context_status == "context_insufficient" and self.sources:
            raise ValueError("context_insufficient snapshot cannot contain sources")
        if self.context_status == "ready" and not self.sources:
            raise ValueError("ready snapshot requires governed sources")
        return self


class Perspective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["fundamental", "technical", "risk", "market"]
    stance: Literal["supports", "opposes", "neutral"]
    score: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(min_length=1, max_length=32)


class ValuationAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicable: bool
    method: Literal["dcf", "ddm", "relative", "asset_based", "not_applicable"]
    conclusion: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def _method_matches_applicability(self) -> "ValuationAssessment":
        if self.applicable == (self.method == "not_applicable"):
            raise ValueError("valuation applicability and method disagree")
        return self


class ICMemo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: Literal["research_only_watch", "watch", "reject", "escalate_human_review"]
    thesis: str = Field(min_length=1, max_length=4000)
    risks: list[str] = Field(min_length=1, max_length=32)
    invalidation_conditions: list[str] = Field(min_length=1, max_length=32)
    evidence_ids: list[str] = Field(min_length=1, max_length=32)


class GeneratedAnalysis(BaseModel):
    """The full extent of the model-writable report body."""

    model_config = ConfigDict(extra="forbid")

    perspectives: list[Perspective] = Field(min_length=2, max_length=4)
    valuation: ValuationAssessment
    ic_memo: ICMemo


class SignalLifecycleState(BaseModel):
    """A server-loaded lifecycle view; it is not model-generated state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: str = Field(min_length=1)
    current_state: Literal["active", "strengthened", "weakened", "falsified", "priced_in", "closed"]
    history: tuple[dict[str, object], ...] = ()


class AnalysisReport(BaseModel):
    """Server envelope combining a validated generated body with frozen authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generated: GeneratedAnalysis
    evidence_snapshot: FrozenEvidenceSnapshot
    lifecycle: SignalLifecycleState
    run_id: str = Field(min_length=1)
    report_version: int = Field(ge=1)
    schema_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _cites_only_frozen_sources(self) -> "AnalysisReport":
        allowed = {source.source_id for source in self.evidence_snapshot.sources}
        cited = set(self.generated.valuation.evidence_ids) | set(self.generated.ic_memo.evidence_ids)
        for perspective in self.generated.perspectives:
            cited.update(perspective.evidence_ids)
        if unknown := cited - allowed:
            raise ValueError(f"unknown evidence ids: {sorted(unknown)}")
        return self
