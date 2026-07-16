"""Deny-by-default display projections for immutable Thesis audit records."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def version(
    record: Mapping[str, Any],
    *,
    schedules: Mapping[str, Mapping[str, Any] | None] | None = None,
    checks: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Project one complete immutable version without creator authority internals."""
    schedule_map = schedules or {}
    check_map = checks or {}
    return {
        "id": str(record["id"]),
        "thesis_id": str(record["thesis_id"]),
        "instrument": str(record["instrument"]),
        "version": int(record["version"]),
        "predecessor_id": _optional_text(record.get("predecessor_id")),
        "core_judgment": str(record["core_judgment"]),
        "rationale": str(record["rationale"]),
        "change_reason": str(record["change_reason"]),
        "official_state": str(record.get("official_state", "active")),
        "anchors": [_anchor(item) for item in _mappings(record.get("anchors"))],
        "conditions": [
            condition(
                item,
                schedule=schedule_map.get(str(item.get("id", ""))),
                checks=check_map.get(str(item.get("id", "")), ()),
            )
            for item in _mappings(record.get("conditions"))
        ],
        "created_at": str(record["created_at"]),
    }


def condition(
    record: Mapping[str, Any],
    *,
    schedule: Mapping[str, Any] | None = None,
    checks: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Project the visible AST, independent cadence, cursor state, and immutable checks."""
    return {
        "id": str(record["id"]),
        "copied_from_condition_id": _optional_text(record.get("copied_from_condition_id")),
        "source_kind": str(record["source_kind"]),
        "field": str(record["field"]),
        "operator": str(record["operator"]),
        "threshold": record.get("threshold"),
        "unit": str(record["unit"]),
        "lookback_days": int(record["lookback_days"]),
        "cadence": str(record["cadence"]),
        "timezone": str(record["timezone"]),
        "description": str(record["description"]),
        "schedule": schedule_projection(schedule),
        "checks": [check(item) for item in checks],
    }


def schedule_projection(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Expose due/stale state while withholding lease ownership and transition internals."""
    if record is None:
        return None
    return {
        "active": bool(record["active"]),
        "next_due_at": str(record["next_due_at"]),
        "last_attempt_at": _optional_text(record.get("last_attempt_at")),
    }


def check(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project one immutable check with bounded evidence summaries only."""
    return {
        "id": str(record["id"]),
        "version_id": str(record["version_id"]),
        "condition_id": str(record["condition_id"]),
        "due_at": str(record["due_at"]),
        "checked_at": str(record["checked_at"]),
        "result": str(record["result"]),
        "observed_value": record.get("observed_value"),
        "evidence_fingerprint": str(record["evidence_fingerprint"]),
        "evidence": [_evidence_summary(item) for item in _mappings(record.get("evidence"))],
        "safe_reason": _optional_text(record.get("safe_reason")),
    }


def pending(record: Mapping[str, Any], *, review: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Project one evidence-linked proposal and its optional human decision."""
    return {
        "id": str(record["id"]),
        "thesis_id": str(record["thesis_id"]),
        "version_id": str(record["version_id"]),
        "condition_id": str(record["condition_id"]),
        "check_id": str(record["check_id"]),
        "evidence_fingerprint": str(record["evidence_fingerprint"]),
        "proposed_state": str(record["proposed_state"]),
        "reason": str(record["reason"]),
        "status": "pending" if review is None else str(review["decision"]),
        "created_at": str(record["created_at"]),
        "review": None if review is None else review_event(review),
    }


def review_event(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project an attributable human decision without exposing principal internals."""
    return {
        "id": str(record["id"]),
        "pending_id": str(record["pending_id"]),
        "version_id": str(record["version_id"]),
        "condition_id": str(record["condition_id"]),
        "check_id": str(record["check_id"]),
        "evidence_fingerprint": str(record["evidence_fingerprint"]),
        "decision": str(record["decision"]),
        "rationale": str(record["rationale"]),
        "created_at": str(record["created_at"]),
    }


def history(
    *,
    thesis_id: str,
    official_state: str,
    versions: Sequence[Mapping[str, Any]],
    schedules: Mapping[str, Mapping[str, Any] | None],
    checks: Mapping[str, Sequence[Mapping[str, Any]]],
    pending_records: Sequence[Mapping[str, Any]],
    reviews: Mapping[str, Sequence[Mapping[str, Any]]],
    official_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project the complete immutable version/check/pending/review ledger."""
    return {
        "thesis_id": thesis_id,
        "official_state": official_state,
        "versions": [version(item, schedules=schedules, checks=checks) for item in versions],
        "pending": [
            pending(item, review=(reviews.get(str(item["id"])) or [None])[0])
            for item in pending_records
        ],
        "official_events": [review_event(item) for item in official_events],
    }


def _anchor(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "method": str(record["method"]),
        "currency": str(record["currency"]),
        "as_of": str(record["as_of"]),
        "low": record["low"],
        "high": record["high"],
        "assumptions": [
            {"name": str(item["name"]), "value": item["value"], "unit": str(item["unit"])}
            for item in _mappings(record.get("assumptions"))
        ],
        "limitations": [str(item) for item in _sequence(record.get("limitations"))],
    }


def _evidence_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    allowed = ("source_id", "source_revision", "source_kind", "field", "observed_value", "unit", "as_of")
    return {field: record[field] for field in allowed if field in record}


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _mappings(value: object) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()
