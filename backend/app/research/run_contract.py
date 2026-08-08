"""Frozen value objects and canonical serialization for Alpha run contracts.

A Phase 45 run is created from a server-frozen specification (D-04).  This
module defines the immutable value objects that carry the complete input
snapshot, their canonical JSON serialization, and the lowercase SHA-256
helpers used by the repository/service seam.  Nothing here executes work,
calls a provider, evaluates a fold, or mutates a frozen fact.

The canonical snapshot digest covers every D-04 identity dimension:
DSL/grammar/vocabulary/policy versions, seed, expression/candidate budgets,
objective/cost policy, universe, measured date range, fold geometry, and the
code/data manifest.  A changed input produces a distinct digest and therefore
a new linked run, never a mutation of the original.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

MANIFEST_SCHEMA_VERSION = "alpha-manifest-v1"
PRODUCER_VERSION = "research-run-v1"

# Bounded cursor constants (D-11): declared totals may be zero until later
# phases populate evidence.  The repository persists these server-owned
# counters; workers report bounded progress, never policy.

RUN_STATUSES: tuple[str, ...] = (
    "queued",
    "preflight_failed",
    "running",
    "cancel_requested",
    "cancelled",
    "completed",
    "failed",
)
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"preflight_failed", "cancelled", "completed", "failed"}
)

_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")

REQUIRED_MANIFEST_GROUPS: tuple[str, ...] = (
    "dsl",
    "grammar",
    "vocabulary",
    "policy",
    "budgets",
    "objective",
    "universe",
    "measured_window",
    "fold_geometry",
    "code_manifest",
    "data_manifest",
)


def canonical_json(value: object) -> str:
    """Serialize to stable UTF-8 JSON bytes with sorted keys and no whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def canonical_bytes(value: object) -> bytes:
    return canonical_json(value).encode("utf-8")


def digest_bytes(value: object) -> str:
    """Lowercase SHA-256 hex digest over the canonical JSON of ``value``."""
    return sha256(canonical_bytes(value)).hexdigest()


def validate_sha256(value: str, field: str) -> None:
    """Fail closed unless ``value`` is a lowercase 64-hex SHA-256 digest."""
    if not isinstance(value, str) or not _SHA256_HEX.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Fail closed if any required D-04 manifest group is missing or empty."""
    if not isinstance(manifest, Mapping):
        raise ValueError("manifest must be a mapping")
    missing = [group for group in REQUIRED_MANIFEST_GROUPS if group not in manifest]
    if missing:
        raise ValueError(f"manifest is missing required groups: {', '.join(missing)}")
    for group in REQUIRED_MANIFEST_GROUPS:
        entry = manifest[group]
        if entry is None:
            raise ValueError(f"manifest group '{group}' must not be null")
        if isinstance(entry, (str, list, dict, tuple)) and len(entry) == 0:
            raise ValueError(f"manifest group '{group}' must not be empty")


@dataclass(frozen=True, slots=True)
class ResearchInputSnapshot:
    """Immutable server-frozen input snapshot bound to its canonical digest."""

    schema_version: str
    manifest: Mapping[str, Any]
    snapshot: Mapping[str, Any]
    manifest_sha256: str
    snapshot_sha256: str
    component_digests: Mapping[str, str]
    created_at: str

    def as_storage_record(self) -> dict[str, Any]:
        """Return the flat column dict the repository persists."""
        digests = dict(self.component_digests)
        return {
            "schema_version": self.schema_version,
            "snapshot_json": canonical_json(self.snapshot),
            "snapshot_sha256": self.snapshot_sha256,
            "manifest_json": canonical_json(self.manifest),
            "manifest_sha256": self.manifest_sha256,
            "dsl_version": str(self.manifest["dsl"].get("version", "")),
            "grammar_fingerprint": digests["grammar"],
            "vocabulary_fingerprint": digests["vocabulary"],
            "policy_version": str(self.manifest["policy"].get("version", "")),
            "policy_digest": digests["policy"],
            "data_fingerprint": digests["data"],
            "partition_fingerprint": digests["partition"],
            "membership_fingerprint": digests["membership"],
            "code_fingerprint": digests["code"],
            "build_fingerprint": digests["build"],
            "dependency_fingerprint": digests["dependency"],
            "created_at": self.created_at,
        }


def _component_digest(manifest: Mapping[str, Any], group: str, *, key: str | None = None) -> str:
    """Derive a lowercase SHA-256 over one manifest group (or a named sub-key)."""
    payload = manifest[group]
    if key is not None:
        payload = {key: payload.get(key)} if isinstance(payload, Mapping) else payload
    return digest_bytes(payload)


def freeze_input_snapshot(
    *,
    manifest: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None = None,
    created_at: str,
) -> ResearchInputSnapshot:
    """Validate, canonicalize, and digest a server-owned D-04 input snapshot.

    ``manifest`` is the authoritative frozen specification.  ``snapshot`` is an
    optional resolved-detail view (e.g. resolved universe membership); when
    omitted the manifest itself is the canonical snapshot.  Both are
    canonicalized before digesting so the persisted bytes are stable.
    """
    validate_manifest(manifest)
    canonical_manifest = json.loads(canonical_json(manifest))
    canonical_snapshot = (
        json.loads(canonical_json(snapshot)) if snapshot is not None else canonical_manifest
    )
    component_digests = {
        "grammar": _component_digest(canonical_manifest, "grammar", key="fingerprint"),
        "vocabulary": _component_digest(canonical_manifest, "vocabulary", key="fingerprint"),
        "policy": _component_digest(canonical_manifest, "policy"),
        "data": _component_digest(canonical_manifest, "data_manifest", key="fingerprint"),
        "partition": _component_digest(canonical_manifest, "data_manifest", key="partition_fingerprint"),
        "membership": _component_digest(canonical_manifest, "universe", key="membership_fingerprint"),
        "code": _component_digest(canonical_manifest, "code_manifest", key="fingerprint"),
        "build": _component_digest(canonical_manifest, "code_manifest", key="build_fingerprint"),
        "dependency": _component_digest(canonical_manifest, "code_manifest", key="dependency_fingerprint"),
    }
    manifest_sha256 = digest_bytes(canonical_manifest)
    snapshot_sha256 = digest_bytes(canonical_snapshot)
    return ResearchInputSnapshot(
        schema_version=MANIFEST_SCHEMA_VERSION,
        manifest=canonical_manifest,
        snapshot=canonical_snapshot,
        manifest_sha256=manifest_sha256,
        snapshot_sha256=snapshot_sha256,
        component_digests=component_digests,
        created_at=created_at,
    )


@dataclass(frozen=True, slots=True)
class AlphaFactoryRun:
    """Immutable projection of a persisted Alpha run identity + cursor."""

    id: str
    principal: str
    idempotency_key: str
    snapshot_id: str
    snapshot_sha256: str
    manifest_sha256: str
    status: str
    transition_version: int
    last_event_seq: int
    candidate_attempts_total: int
    candidate_attempts_completed: int
    folds_total: int
    folds_completed: int
    started_at: str | None
    finished_at: str | None
    terminal_reason: str | None
    retry_of_run_id: str | None
    retry_attempt: int
    created_at: str


@dataclass(frozen=True, slots=True)
class AlphaRunEvent:
    """Immutable projection of one append-only lifecycle event."""

    id: str
    run_id: str
    seq: int
    event_type: str
    entity_kind: str
    entity_id: str
    occurred_at: str
    idempotency_key: str
    actor: str
    source: str
    payload: Mapping[str, Any]
    payload_checksum: str
    artifact_id: str | None
    producer_version: str
    created_at: str
