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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_MANIFEST_SHA256 = r"^[0-9a-f]{64}$"


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
    """Safe public replay projection — run + snapshot + ordered events."""

    run: AlphaRunReadDTO
    snapshot: AlphaSnapshotDTO | None
    events: list[AlphaRunEventDTO]
