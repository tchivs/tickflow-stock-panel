"""Strict request and public DTO contracts for governed Alpha runs.

Every request model uses ``extra="forbid"`` so undeclared authority fields
(status, event_seq, snapshot_digest, candidate_id, checkpoint_ref) are
rejected at the trust boundary before any repository write.  Bounded
strings/lists/maps and finite numeric limits prevent unbounded JSON.  The
server derives run ID, policy, manifest, evidence refs, event sequence, and
statuses; the client supplies intent only (D-09, T-45-01).
"""
from __future__ import annotations

from typing import Any, Literal

_MANIFEST_SHA256 = r"^[0-9a-f]{64}$"

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.research.run_contract import MAX_INT64, validate_bounded_json


class StrictAlphaModel(BaseModel):
    """Reject undeclared fields at every browser or provider trust boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AlphaRunCreateRequest(StrictAlphaModel):
    """Bounded researcher create intent. The server freezes the snapshot."""

    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    manifest: dict[str, Any] = Field(min_length=1, max_length=64)

    @field_validator("manifest")
    @classmethod
    def _manifest_keys_are_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if any(not isinstance(key, str) or not 1 <= len(key) <= 64 for key in value):
            raise ValueError("manifest keys must be bounded strings")
        validate_bounded_json(value, "manifest")
        return value


class AlphaRunReadDTO(StrictAlphaModel):
    """Safe public run projection — no principal, path, secret, or internals."""

    id: str
    status: Literal[
        "queued",
        "preflight_failed",
        "running",
        "cancel_requested",
        "cancelled",
        "completed",
        "failed",
    ]
    transition_version: int
    last_event_seq: int
    candidate_attempts_total: int
    candidate_attempts_completed: int
    folds_total: int
    folds_completed: int
    snapshot_sha256: str = Field(pattern=_MANIFEST_SHA256)
    manifest_sha256: str = Field(pattern=_MANIFEST_SHA256)
    started_at: str | None = None
    finished_at: str | None = None
    terminal_reason: str | None = None
    retry_of_run_id: str | None = None
    retry_attempt: int
    created_at: str


class AlphaSnapshotDTO(StrictAlphaModel):
    """Safe public snapshot projection — every D-04 group, no policy internals."""

    schema_version: str
    snapshot_sha256: str = Field(pattern=_MANIFEST_SHA256)
    manifest_sha256: str = Field(pattern=_MANIFEST_SHA256)
    dsl_version: str
    grammar_fingerprint: str = Field(pattern=_MANIFEST_SHA256)
    vocabulary_fingerprint: str = Field(pattern=_MANIFEST_SHA256)
    policy_version: str
    policy_digest: str = Field(pattern=_MANIFEST_SHA256)
    data_fingerprint: str = Field(pattern=_MANIFEST_SHA256)
    partition_fingerprint: str = Field(pattern=_MANIFEST_SHA256)
    membership_fingerprint: str = Field(pattern=_MANIFEST_SHA256)
    code_fingerprint: str = Field(pattern=_MANIFEST_SHA256)
    build_fingerprint: str = Field(pattern=_MANIFEST_SHA256)
    dependency_fingerprint: str = Field(pattern=_MANIFEST_SHA256)
    universe: dict[str, Any]
    measured_window: dict[str, Any]
    fold_geometry: dict[str, Any]
    budgets: dict[str, Any]
    objective: dict[str, Any]
    seed: int | None = None
    created_at: str


class AlphaRunEventDTO(StrictAlphaModel):
    """Safe public event projection — no raw payload internals."""

    id: str
    seq: int
    event_type: str
    entity_kind: str
    entity_id: str
    occurred_at: str
    source: str
    producer_version: str
    created_at: str

class AlphaRunReplayDTO(StrictAlphaModel):
    """Safe replay page with explicit continuation markers."""

    run: AlphaRunReadDTO
    snapshot: AlphaSnapshotDTO | None
    events: list[AlphaRunEventDTO]
    events_after_sequence: int = 0
    next_sequence: int | None = None
    truncated: bool = False


class AlphaRunRetryRequest(StrictAlphaModel):
    """Bounded retry intent — server creates a linked child run (D-07).

    The client supplies intent only; the server freezes a fresh snapshot and
    derives the child run ID.  ``snapshot_sha256`` and other authority fields
    are rejected (T-45-10).
    """

    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    manifest: dict[str, Any] = Field(min_length=1, max_length=64)

    @field_validator("manifest")
    @classmethod
    def _manifest_keys_are_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if any(not isinstance(key, str) or not 1 <= len(key) <= 64 for key in value):
            raise ValueError("manifest keys must be bounded strings")
        validate_bounded_json(value, "manifest")
        return value


class AlphaRunCancelRequest(StrictAlphaModel):
    """Bounded cancel intent — server owns status and event sequence (D-07)."""

    expected_version: int = Field(ge=0)
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class AlphaProgressUpdateRequest(StrictAlphaModel):
    """Bounded worker progress update — token/version fenced (D-10, D-11).

    Every counter is optional and must be a non-negative integer.  The attempt
    token is required; it is validated against the persisted SHA-256 digest and
    never returned in projections.
    """

    expected_version: int = Field(ge=0, le=MAX_INT64)
    attempt_token: str = Field(min_length=16, max_length=256)
    candidate_attempts_total: int | None = Field(default=None, ge=0, le=MAX_INT64)
    candidate_attempts_completed: int | None = Field(default=None, ge=0, le=MAX_INT64)
    folds_total: int | None = Field(default=None, ge=0, le=MAX_INT64)
    folds_completed: int | None = Field(default=None, ge=0, le=MAX_INT64)


class AlphaCandidateDTO(StrictAlphaModel):
    """Safe public candidate-attempt projection — no reason internals or paths."""

    id: str
    attempt_ordinal: int
    candidate_digest: str = Field(pattern=_MANIFEST_SHA256)
    canonical_expression: str
    dsl_version: str
    operation: str
    seed: int
    step: int
    status: Literal[
        "invalid",
        "duplicate",
        "low_coverage",
        "generated",
        "failed",
        "rejected",
        "admitted",
        "cancelled",
        "budget_exhausted",
    ]
    created_at: str


class AlphaProgressDTO(StrictAlphaModel):
    """Safe public progress projection — four bounded counters, no token/principal."""

    candidate_attempts_total: int
    candidate_attempts_completed: int
    folds_total: int
    folds_completed: int



class AlphaLineageEdgeDTO(StrictAlphaModel):
    """One parent→child lineage edge with bounded child/parent candidates (SC2)."""

    lineage_id: str
    edge_ordinal: int = Field(ge=0)
    operation: str
    created_at: str
    child: AlphaCandidateDTO
    parent: AlphaCandidateDTO


class AlphaLineageDTO(StrictAlphaModel):
    """Ordered lineage edges for one run (SC2 read half)."""

    run_id: str
    edges: list[AlphaLineageEdgeDTO] = Field(default_factory=list)


class EvidenceClassificationDTO(StrictAlphaModel):
    """SC4 temporal/degradation classification — clean flag binds the data-quality banner."""

    data_date: str | None = None
    source_label: str | None = None
    cache_state: Literal["fresh", "stale", "degraded"]
    missing_fields: list[str] = Field(default_factory=list)
    membership_coverage: float = Field(ge=0.0, le=1.0)
    evidence_role: Literal[
        "exploratory",
        "selection_fold",
        "selection_oos",
        "final_blind_unavailable",
    ]
    fixture: bool
    clean: bool


# ------------------------------------------------------------------
# Phase 50-02: compare + Tier-1 stress matrix + replay-branch + clone.
# ------------------------------------------------------------------


class AlphaCandidateComparisonDTO(StrictAlphaModel):
    """One candidate's side-by-side comparison record (SC3, AF-REQ-22).

    Every requested candidate is exposed equally — there is never an opaque
    aggregate ``winner``/``rank``/``score`` field (the deny-by-default
    ``extra='forbid'`` rejects any such injected key at the trust boundary).
    """

    candidate_id: str
    candidate_digest: str = Field(pattern=_MANIFEST_SHA256)
    config: dict[str, Any]
    fold_evidence: list[dict[str, Any]]
    admission_verdict: str | None = None
    gate_trail_digest: str | None = None
    policy_version: str | None = None
    artifact_refs: list[dict[str, Any]]
    diversity: dict[str, Any] | None = None


class AlphaCompareDTO(StrictAlphaModel):
    """Side-by-side comparison page — all candidates, no opaque winner (SC3)."""

    run_id: str
    candidates: list[AlphaCandidateComparisonDTO]


class StressMatrixBaselineDTO(StrictAlphaModel):
    """The frozen cost-diagnostics baseline row (zero recomputation)."""

    total_turnover: float
    cost_rate: float
    cost_drag: float
    raw_long_short_return: float
    net_long_short_return: float


class StressMatrixRowDTO(StrictAlphaModel):
    """One Tier-1 stress row — pure arithmetic over stored turnover."""

    axis: Literal["fee_bps", "slippage_bps", "rebalance"]
    value: float | str
    total_turnover: float
    cost_rate: float
    cost_drag: float
    net_long_short_return: float


class StressMatrixDTO(StrictAlphaModel):
    """Tier-1 stress matrix — fee/slippage/rebalance re-projection (AF-REQ-20)."""

    candidate_id: str
    baseline: StressMatrixBaselineDTO
    matrix: list[StressMatrixRowDTO]


class ReplayBranchRequestDTO(StrictAlphaModel):
    """Bounded branch-replay intent — re-derive the PRNG frontier into a child run."""

    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    parent_step: int = Field(ge=0)
    max_candidates: int | None = Field(default=None, ge=1, le=MAX_INT64)


class ReplayBranchResultDTO(StrictAlphaModel):
    """Branch-replay result — new child run sharing the parent's frozen inputs."""

    parent_run_id: str
    child_run_id: str
    parent_step: int
    shared_snapshot_sha256: str = Field(pattern=_MANIFEST_SHA256)
    shared_manifest_sha256: str = Field(pattern=_MANIFEST_SHA256)
    replayed_prefix_digests: list[str]


class CloneRequestDTO(StrictAlphaModel):
    """Bounded clone intent — override declared scoring/costs/budgets only."""

    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    overrides: dict[str, Any] = Field(default_factory=dict, max_length=16)


class CloneResultDTO(StrictAlphaModel):
    """Clone result — new/parent run id + field-level diff (SC2 clone half)."""

    parent_run_id: str
    clone_run_id: str
    parent_manifest_sha256: str = Field(pattern=_MANIFEST_SHA256)
    clone_manifest_sha256: str = Field(pattern=_MANIFEST_SHA256)
    changed_dimensions: list[str]
    no_op: bool