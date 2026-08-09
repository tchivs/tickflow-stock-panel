"""Hand-built, deny-by-default public projections for Alpha run records.

Every projection is an explicit allowlist.  No projection returns principal
identity, raw filesystem paths, secrets, policy internals, raw diagnostics,
prompts, or arbitrary payloads.  Safe digests and bounded summaries are
exposed instead of internal data (T-45-08).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def run(record: Mapping[str, Any]) -> dict[str, object]:
    """Expose a run's safe identity and cursor without principal or internals."""
    return {
        "id": str(record["id"]),
        "status": str(record["status"]),
        "transition_version": int(record["transition_version"]),
        "last_event_seq": int(record["last_event_seq"]),
        "candidate_attempts_total": int(record["candidate_attempts_total"]),
        "candidate_attempts_completed": int(record["candidate_attempts_completed"]),
        "folds_total": int(record["folds_total"]),
        "folds_completed": int(record["folds_completed"]),
        "snapshot_sha256": str(record["snapshot_sha256"]),
        "manifest_sha256": str(record["manifest_sha256"]),
        "started_at": _optional_text(record.get("started_at")),
        "finished_at": _optional_text(record.get("finished_at")),
        "terminal_reason": _safe_terminal_reason(record.get("terminal_reason")),
        "retry_of_run_id": _optional_text(record.get("retry_of_run_id")),
        "retry_attempt": int(record.get("retry_attempt", 0)),
        "created_at": str(record["created_at"]),
    }


def snapshot(record: Mapping[str, Any]) -> dict[str, object]:
    """Expose every D-04 frozen group in bounded form without policy internals."""
    manifest = record.get("manifest") if isinstance(record.get("manifest"), Mapping) else {}
    return {
        "schema_version": str(record.get("schema_version", "")),
        "snapshot_sha256": str(record["snapshot_sha256"]),
        "manifest_sha256": str(record["manifest_sha256"]),
        "dsl_version": _safe_text(manifest.get("dsl", {}).get("version")),
        "grammar_fingerprint": str(record.get("grammar_fingerprint", "")),
        "vocabulary_fingerprint": str(record.get("vocabulary_fingerprint", "")),
        "policy_version": _safe_text(manifest.get("policy", {}).get("version")),
        "policy_digest": str(record.get("policy_digest", "")),
        "data_fingerprint": str(record.get("data_fingerprint", "")),
        "partition_fingerprint": str(record.get("partition_fingerprint", "")),
        "membership_fingerprint": str(record.get("membership_fingerprint", "")),
        "code_fingerprint": str(record.get("code_fingerprint", "")),
        "build_fingerprint": str(record.get("build_fingerprint", "")),
        "dependency_fingerprint": str(record.get("dependency_fingerprint", "")),
        "universe": _allow_mapping(manifest.get("universe"), ("name", "asset_type", "membership_fingerprint")),
        "measured_window": _allow_mapping(manifest.get("measured_window"), ("start", "end", "calendar")),
        "fold_geometry": _allow_mapping(manifest.get("fold_geometry"), ("train_size", "gap_size", "test_size", "n_folds")),
        "budgets": _allow_mapping(manifest.get("budgets"), ("max_expressions", "max_candidates")),
        "objective": _allow_mapping(manifest.get("objective"), ("name", "direction")),
        "seed": manifest.get("seed") if isinstance(manifest.get("seed"), int) else None,
        "created_at": str(record.get("created_at", "")),
    }


def event(record: Mapping[str, Any]) -> dict[str, object]:
    """Expose one append-only event without raw payload internals."""
    return {
        "id": str(record["id"]),
        "seq": int(record["seq"]),
        "event_type": str(record["event_type"]),
        "entity_kind": str(record["entity_kind"]),
        "entity_id": str(record["entity_id"]),
        "occurred_at": str(record["occurred_at"]),
        "source": str(record["source"]),
        "producer_version": str(record["producer_version"]),
        "created_at": str(record["created_at"]),
    }


def replay(record: Mapping[str, Any]) -> dict[str, object]:
    """Project a replay page and make truncation observable."""
    snapshot_record = record.get("snapshot")
    return {
        "run": run(record["run"]),
        "snapshot": snapshot(snapshot_record) if snapshot_record is not None else None,
        "events": [event(evt) for evt in record.get("events", [])],
        "events_after_sequence": int(record.get("events_after_sequence", 0)),
        "next_sequence": record.get("next_sequence"),
        "truncated": bool(record.get("truncated", False)),
    }

def candidate(record: Mapping[str, Any]) -> dict[str, object]:
    """Expose one candidate-attempt without reason internals or evidence paths."""
    return {
        "id": str(record["id"]),
        "attempt_ordinal": int(record["attempt_ordinal"]),
        "candidate_digest": str(record["candidate_digest"]),
        "canonical_expression": str(record["canonical_expression"]),
        "dsl_version": str(record["dsl_version"]),
        "operation": str(record["operation"]),
        "seed": int(record["seed"]),
        "step": int(record["step"]),
        "status": str(record["status"]),
        "created_at": str(record["created_at"]),
    }


# SC4: the declared-fingerprint keys whose completeness drives cache_state, and
# the coverage floor above which evidence may be considered clean production.
_DECLARED_FINGERPRINT_KEYS: tuple[str, ...] = (
    "panel", "membership", "source_field", "warmup", "missing_data", "signal",
)
_COVERAGE_CLEAN_THRESHOLD: float = 0.9
# Candidate statuses that terminally block the reserved final-blind evaluation
# (the candidate can never reach the OOS fold — its blind is unavailable).
_BLOCKED_BLIND_STATUSES: frozenset[str] = frozenset({
    "invalid", "duplicate", "low_coverage", "failed",
    "rejected", "cancelled", "budget_exhausted",
})


def lineage(edge: Mapping[str, Any]) -> dict[str, object]:
    """Expose one parent→child lineage edge with bounded candidate fields.

    Deny-by-default: only the edge identity + child/parent ``candidate``
    projections surface — never raw reason/payload internals (SC2 read half).
    """
    return {
        "lineage_id": str(edge["lineage_id"]),
        "edge_ordinal": int(edge["edge_ordinal"]),
        "operation": str(edge["operation"]),
        "created_at": str(edge["created_at"]),
        "child": candidate(edge["child"]),
        "parent": candidate(edge["parent"]),
    }


def evidence_classification(
    snapshot: Mapping[str, Any],
    candidate_record: Mapping[str, Any],
    fold_evidence: Mapping[str, Any] | None,
    fixture_flag: bool,
) -> dict[str, object]:
    """Deny-by-default SC4 classification of one candidate's evidence health.

    Every value is sourced from an EXISTING declared fingerprint on the frozen
    snapshot or fold evidence — no new data collection.  ``clean`` is False
    unless the cache is fresh, no declared fields are missing, coverage is at
    or above the clean threshold, the evidence is not a fixture, and the
    final-blind role is available.  Stale / partial / blocked / fixture
    results can therefore never look like clean production (SC4 invariant).
    """
    manifest = snapshot.get("manifest") if isinstance(snapshot, Mapping) else {}
    if not isinstance(manifest, Mapping):
        manifest = {}
    window = manifest.get("measured_window")
    if not isinstance(window, Mapping):
        window = {}

    # data_date ← declared measured window (start/end).
    start = window.get("start")
    end = window.get("end")
    if start and end:
        data_date: str | None = f"{start}/{end}"
    elif start:
        data_date = str(start)
    else:
        data_date = None

    # Source declared fingerprints + stats from the frozen fold evidence.
    declared: Mapping[str, Any] = {}
    stats: Mapping[str, Any] = {}
    if isinstance(fold_evidence, Mapping):
        raw_declared = fold_evidence.get("declared_fingerprints")
        if isinstance(raw_declared, Mapping):
            declared = raw_declared
        raw_stats = fold_evidence.get("stats")
        if isinstance(raw_stats, Mapping):
            stats = raw_stats

    # source_label ← declared source_field fingerprint.
    source_field = declared.get("source_field")
    source_label = str(source_field) if source_field else None

    # missing_fields ← explicitly declared missing-field list (if any).
    raw_missing = declared.get("missing_fields")
    if isinstance(raw_missing, (list, tuple)):
        missing_fields = [str(field) for field in raw_missing if field]
    else:
        missing_fields = []

    # cache_state ← declared-fingerprint block completeness.
    present = sum(1 for key in _DECLARED_FINGERPRINT_KEYS if str(declared.get(key, "")))
    if present == len(_DECLARED_FINGERPRINT_KEYS):
        cache_state = "fresh"
    elif present > 0:
        cache_state = "stale"
    else:
        cache_state = "degraded"

    # membership_coverage ← measured fold coverage (0..1).
    coverage_raw = stats.get("coverage")
    try:
        membership_coverage = float(coverage_raw) if coverage_raw is not None else 0.0
    except (TypeError, ValueError):
        membership_coverage = 0.0
    membership_coverage = max(0.0, min(1.0, membership_coverage))

    # evidence_role ← candidate status + fold-evidence presence.
    status = str(candidate_record.get("status", "")) if isinstance(candidate_record, Mapping) else ""
    if status == "selection_oos":
        evidence_role = "selection_oos"
    elif status in _BLOCKED_BLIND_STATUSES:
        evidence_role = "final_blind_unavailable"
    elif fold_evidence:
        evidence_role = "selection_fold"
    else:
        evidence_role = "exploratory"

    clean = (
        cache_state == "fresh"
        and not missing_fields
        and membership_coverage >= _COVERAGE_CLEAN_THRESHOLD
        and not bool(fixture_flag)
        and evidence_role != "final_blind_unavailable"
    )

    return {
        "data_date": data_date,
        "source_label": source_label,
        "cache_state": cache_state,
        "missing_fields": missing_fields,
        "membership_coverage": membership_coverage,
        "evidence_role": evidence_role,
        "fixture": bool(fixture_flag),
        "clean": clean,
    }


def progress(record: Mapping[str, Any]) -> dict[str, object]:
    """Expose the four bounded progress counters without token or principal."""
    return {
        "candidate_attempts_total": int(record["candidate_attempts_total"]),
        "candidate_attempts_completed": int(record["candidate_attempts_completed"]),
        "folds_total": int(record["folds_total"]),
        "folds_completed": int(record["folds_completed"]),
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _safe_text(value: object) -> str:
    return str(value) if value is not None else ""


def _safe_terminal_reason(value: object) -> str | None:
    if value is None:
        return None
    try:
        import json
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return None
    if isinstance(parsed, Mapping) and isinstance(parsed.get("code"), str):
        return parsed["code"]
    return None


def _allow_mapping(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: value[key] for key in keys
        if key in value and isinstance(value[key], (str, int, float, bool))
    }
