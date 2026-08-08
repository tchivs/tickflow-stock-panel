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
