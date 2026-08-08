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
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

MAX_JSON_BYTES = 64 * 1024
MAX_JSON_DEPTH = 8
MAX_JSON_STRING_CHARS = 4096
MAX_JSON_COLLECTION_ITEMS = 256
MAX_INT64 = (1 << 63) - 1

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
    """Serialize to stable, finite JSON with sorted keys and no whitespace."""
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("value must be finite JSON") from error


def validate_bounded_json(
    value: object,
    field: str,
    *,
    max_bytes: int = MAX_JSON_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
) -> None:
    """Validate untrusted JSON recursively before it reaches SQLite."""
    def visit(node: object, depth: int, path: str) -> None:
        if depth > max_depth:
            raise ValueError(f"{field} exceeds maximum JSON depth")
        if node is None or isinstance(node, bool):
            return
        if isinstance(node, int):
            if node < -MAX_INT64 - 1 or node > MAX_INT64:
                raise ValueError(f"{field} contains an out-of-range integer")
            return
        if isinstance(node, float):
            if not math.isfinite(node):
                raise ValueError(f"{field} contains a non-finite number")
            return
        if isinstance(node, str):
            if len(node) > MAX_JSON_STRING_CHARS:
                raise ValueError(f"{field} contains an oversized string at {path}")
            return
        if isinstance(node, Mapping):
            if len(node) > MAX_JSON_COLLECTION_ITEMS:
                raise ValueError(f"{field} contains too many object members")
            for key, child in node.items():
                if not isinstance(key, str) or len(key) > MAX_JSON_STRING_CHARS:
                    raise ValueError(f"{field} contains an invalid object key at {path}")
                visit(child, depth + 1, f"{path}.{key}")
            return
        if isinstance(node, (list, tuple)):
            if len(node) > MAX_JSON_COLLECTION_ITEMS:
                raise ValueError(f"{field} contains too many array items")
            for index, child in enumerate(node):
                visit(child, depth + 1, f"{path}[{index}]")
            return
        raise ValueError(f"{field} contains unsupported JSON value at {path}")

    visit(value, 0, field)
    encoded = canonical_bytes(value)
    if len(encoded) > max_bytes:
        raise ValueError(f"{field} exceeds the {max_bytes}-byte UTF-8 JSON bound")


def canonical_bounded_json(value: object, field: str, *, max_bytes: int = MAX_JSON_BYTES) -> str:
    validate_bounded_json(value, field, max_bytes=max_bytes)
    return canonical_json(value)


def canonical_bytes(value: object) -> bytes:
    return canonical_json(value).encode("utf-8")


def digest_bytes(value: object) -> str:
    """Lowercase SHA-256 digest over canonical JSON."""
    return sha256(canonical_bytes(value)).hexdigest()


def validate_sha256(value: str, field: str) -> None:
    """Fail closed unless ``value`` is a lowercase 64-hex digest."""
    if not isinstance(value, str) or not _SHA256_HEX.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
def _is_number(value: object) -> bool:
    """True for a real int/float, excluding the bool subtype and NaN/inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    import math as _math
    return _math.isfinite(float(value))


def _validate_scoring_stage(manifest: Mapping[str, Any]) -> None:
    """Additive scoring/cost/fold inputs, required ONLY when a scoring stage is declared.

    A manifest without a ``scoring`` group validates byte-for-byte as before so
    completed Phase 45/46 frozen snapshots are never invalidated (OQ2, T-47-04).
    When ``scoring`` IS declared, the frozen manifest must also carry the
    measured-date fold OOS geometry (``fold_geometry.oos_size``/``horizon`` —
    the inputs ``wf_plans`` requires), a declared cost policy (``costs``), and
    the scoring cadence/shape (``scoring.rebalance``/``n_groups``/``warmup_days``)
    so a governed walk-forward + cost diagnostic can be rebuilt from the frozen
    manifest. A changed scoring/cost/fold input changes the canonical digest and
    creates a new run (no mutation, D-01).
    """
    scoring = manifest.get("scoring")
    if not isinstance(scoring, Mapping) or not scoring:
        if "scoring" in manifest:
            raise ValueError("manifest group 'scoring' must not be empty and must be a mapping")
        return  # no scoring stage declared → validate nothing new

    fold = manifest["fold_geometry"]
    for key in ("oos_size", "horizon"):
        value = fold.get(key)
        if type(value) is not int or value <= 0:
            raise ValueError(f"manifest field 'fold_geometry.{key}' must be a positive integer")

    costs = manifest.get("costs")
    if not isinstance(costs, Mapping) or not costs:
        raise ValueError("manifest group 'costs' must not be empty and must be a mapping")
    for key in ("commission_pct", "stamp_tax_pct"):
        value = costs.get(key)
        if not _is_number(value) or not (0.0 <= float(value) < 1.0):
            raise ValueError(f"manifest field 'costs.{key}' must be a bounded fraction in [0, 1)")
    slippage = costs.get("slippage_bps")
    # slippage_bps is expressed in basis points (mirrors BacktestConfig.slippage_bps,
    # engine.py:44, default 5.0) and divided by 1e4 in the cost-rate diagnostic; the
    # plan's literal "[0,1)" bound would reject any realistic basis-point value.
    if not _is_number(slippage) or float(slippage) < 0.0 or float(slippage) >= 1e4:
        raise ValueError("manifest field 'costs.slippage_bps' must be a non-negative basis-point float")

    rebalance = scoring.get("rebalance")
    if rebalance not in ("daily", "weekly", "monthly"):
        raise ValueError("manifest field 'scoring.rebalance' must be daily, weekly, or monthly")
    n_groups = scoring.get("n_groups")
    if type(n_groups) is not int or n_groups < 2:
        raise ValueError("manifest field 'scoring.n_groups' must be an integer >= 2")
    warmup_days = scoring.get("warmup_days")
    if type(warmup_days) is not int or warmup_days < 0:
        raise ValueError("manifest field 'scoring.warmup_days' must be a non-negative integer")

def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Fail closed if required groups or nested fields have wrong shapes.

    Additive scoring/cost/fold fields (``fold_geometry.oos_size``/``horizon``,
    ``costs``, ``scoring``) are validated ONLY when a ``scoring`` stage is
    declared (Phase 47-02, OQ2); a manifest without ``scoring`` validates
    byte-for-byte as before so completed Phase 45/46 snapshots are unchanged.
    """
    if not isinstance(manifest, Mapping):
        raise ValueError("manifest must be a mapping")
    validate_bounded_json(manifest, "manifest")
    missing = [group for group in REQUIRED_MANIFEST_GROUPS if group not in manifest]
    if missing:
        raise ValueError(f"manifest is missing required groups: {', '.join(missing)}")
    for group in REQUIRED_MANIFEST_GROUPS:
        entry = manifest[group]
        if not isinstance(entry, Mapping) or not entry:
            raise ValueError(f"manifest group '{group}' must not be empty and must be a mapping")
    required_types: tuple[tuple[str, str, type], ...] = (
        ("dsl.version", "dsl", str), ("grammar.fingerprint", "grammar", str),
        ("vocabulary.fingerprint", "vocabulary", str), ("policy.version", "policy", str),
        ("universe.name", "universe", str), ("measured_window.start", "measured_window", str),
        ("measured_window.end", "measured_window", str),
        ("fold_geometry.train_size", "fold_geometry", int),
        ("fold_geometry.gap_size", "fold_geometry", int),
        ("fold_geometry.test_size", "fold_geometry", int),
        ("fold_geometry.n_folds", "fold_geometry", int),
        ("budgets.max_candidates", "budgets", int),
        ("budgets.max_expressions", "budgets", int),
        ("objective.name", "objective", str),
        ("code_manifest.fingerprint", "code_manifest", str),
        ("data_manifest.fingerprint", "data_manifest", str),
    )
    max_counter = 1_000_000_000
    for label, group, expected_type in required_types:
        key = label.split(".", 1)[1]
        value = manifest[group].get(key)
        if expected_type is int:
            if type(value) is not int or value < 0 or value > max_counter:
                raise ValueError(f"manifest field '{label}' must be a bounded non-negative integer")
        elif not isinstance(value, expected_type):
            raise ValueError(f"manifest field '{label}' has the wrong type")
    # The admission policy fingerprint is server-owned (populated at freeze);
    # when a client supplies one it must at least be a well-formed digest, and
    # it is always overwritten server-side (AF-REQ-08 SC4).  ``policy.thresholds``
    # remains informational provenance and is NOT required.
    policy_fingerprint = manifest["policy"].get("fingerprint")
    if policy_fingerprint is not None:
        validate_sha256(policy_fingerprint, "policy.fingerprint")
    # Additive scoring-stage inputs are required only when a scoring stage is
    # declared; a no-scoring manifest validates byte-for-byte as before (OQ2).
    _validate_scoring_stage(manifest)
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

    @property
    def policy_fingerprint(self) -> str | None:
        """The frozen admission policy fingerprint (server-populated at freeze)."""
        policy = self.manifest.get("policy") or {}
        value = policy.get("fingerprint")
        return value if isinstance(value, str) else None


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
    from app.research.alpha_factory import normalize_manifest_fingerprints
    canonical_manifest = normalize_manifest_fingerprints(canonical_manifest)
    # The admission policy fingerprint is server-owned (T-47-10): a client
    # supplied value cannot survive freeze.  Mirrors the 46-01 vocabulary
    # fingerprint normalization — populated from the live admission constants so
    # a stored run is bound to the exact thresholds + gate order + policy version
    # it was frozen under (AF-REQ-08 SC4).
    from app.research.admission import ADMISSION_POLICY_FINGERPRINT
    policy = dict(canonical_manifest["policy"])
    policy["fingerprint"] = ADMISSION_POLICY_FINGERPRINT
    canonical_manifest["policy"] = policy
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

MAX_INLINE_CHECKPOINT_BYTES = 16 * 1024
CHECKPOINT_SCHEMA_VERSION = "alpha-checkpoint-v1"
ARTIFACT_SCHEMA_VERSION = "alpha-artifact-v1"
CANDIDATE_STATUSES: tuple[str, ...] = (
    "invalid",
    "duplicate",
    "low_coverage",
    "generated",
    "failed",
    "rejected",
    "admitted",
    "cancelled",
    "budget_exhausted",
    "selection_oos",
)


def event_checksum(payload: object, idempotency_key: str, event_type: str) -> str:
    """Lowercase SHA-256 over the canonical semantic identity of an event.

    The checksum covers the canonical payload JSON, idempotency key, and event
    type so that a repeated delivery of the *same* fact yields the same digest
    while a key reused with a *different* fact conflicts (D-05, T-45-03).
    """
    return digest_bytes(
        {"payload": payload, "idempotency_key": idempotency_key, "event_type": event_type}
    )


@dataclass(frozen=True, slots=True)
class AlphaArtifactReference:
    """A content-addressed reference to one managed Alpha run artifact."""

    artifact_id: str
    run_id: str
    logical_kind: str
    relative_path: str
    content_type: str
    byte_size: int
    checksum_sha256: str
    schema_version: str
    created_at: str

    @property
    def expected_relative_path(self) -> str:
        """The exact server-derived content-addressed key for this artifact."""
        return f"research_artifacts/alpha_runs/{self.run_id}/{self.checksum_sha256}.json"


@dataclass(frozen=True, slots=True)
class AlphaCandidateAttempt:
    """Immutable projection of one append-only candidate attempt fact."""

    id: str
    run_id: str
    attempt_ordinal: int
    candidate_digest: str
    canonical_expression: str
    ast_signature: str
    shape_signature: str
    dsl_version: str
    operation: str
    seed: int
    step: int
    status: str
    reason: Mapping[str, Any]
    evidence_artifact_id: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class AlphaCandidateLineage:
    """Immutable projection of one append-only parent/child lineage edge."""

    id: str
    run_id: str
    child_attempt_id: str
    parent_attempt_id: str
    edge_ordinal: int
    operation: str
    created_at: str


@dataclass(frozen=True, slots=True)
class AlphaRunCheckpoint:
    """Immutable projection of one append-only recovery cursor fact."""

    id: str
    run_id: str
    checkpoint_version: int
    committed_event_seq: int
    stage: str
    snapshot_sha256: str
    manifest_sha256: str
    state_checksum: str
    frontier_artifact_id: str | None
    created_at: str


def checkpoint_state_checksum(
    *,
    run_id: str,
    checkpoint_version: int,
    committed_event_seq: int,
    stage: str,
    snapshot_sha256: str,
    manifest_sha256: str,
    referenced_candidate_ids: Sequence[str],
    inline_summary: Mapping[str, Any] | None,
    frontier_artifact_id: str | None,
) -> str:
    """Lowercase SHA-256 over the canonical checkpoint cursor identity (D-07).

    The checksum covers the run, version, committed sequence, stage, both
    digests, the ordered referenced candidate IDs, the bounded inline summary,
    and the optional frontier artifact reference.  A stale or tampered cursor
    recomputes to a different digest and is rejected on recovery.
    """
    payload = {
        "run_id": run_id,
        "checkpoint_version": checkpoint_version,
        "committed_event_seq": committed_event_seq,
        "stage": stage,
        "snapshot_sha256": snapshot_sha256,
        "manifest_sha256": manifest_sha256,
        "referenced_candidate_ids": list(referenced_candidate_ids),
        "inline_summary": dict(inline_summary) if inline_summary is not None else {},
        "frontier_artifact_id": frontier_artifact_id,
    }
    return digest_bytes(payload)


# Bounded progress counter contract (D-11): four server-owned counters.
PROGRESS_COUNTERS: tuple[str, ...] = (
    "candidate_attempts_total",
    "candidate_attempts_completed",
    "folds_total",
    "folds_completed",
)


def attempt_token_digest(token: str) -> str:
    """Lowercase SHA-256 over an opaque attempt token.

    Only the digest is persisted; the raw token is returned to the worker
    adapter and never stored in durable plaintext (D-10, T-45-08).
    """
    if not isinstance(token, str) or not token:
        raise ValueError("attempt_token must be a non-empty string")
    return sha256(token.encode("utf-8")).hexdigest()


def validate_progress_counters(
    *,
    candidate_attempts_total: int | None = None,
    candidate_attempts_completed: int | None = None,
    folds_total: int | None = None,
    folds_completed: int | None = None,
) -> None:
    """Fail closed unless every provided counter is a non-negative integer.

    Phase 45 persists and reports these bounded server-owned counters; it does
    not calculate or evaluate folds (D-11).
    """
    for label, value in (
        ("candidate_attempts_total", candidate_attempts_total),
        ("candidate_attempts_completed", candidate_attempts_completed),
        ("folds_total", folds_total),
        ("folds_completed", folds_completed),
    ):
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > MAX_INT64:
                raise ValueError(f"{label} must be a non-negative SQLite int64 integer")
