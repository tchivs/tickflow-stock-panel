"""Hand-built, deny-by-default public projections for advanced records."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def job(record: Mapping[str, Any]) -> dict[str, object]:
    """Expose a persisted job stage without principal, policy, code, or diagnostics."""
    return {
        "id": str(record["id"]),
        "subject": {"kind": str(record["subject_kind"]), "key": str(record["subject_key"])},
        "status": str(record["status"]),
        "stage": str(record["stage"]),
        "stage_recorded_at": str(record["stage_recorded_at"]),
        "audit_reference": _optional_text(record.get("audit_reference")),
    }


def audit(record: Mapping[str, Any]) -> dict[str, object]:
    """Expose only the safe decision reason and opaque reference."""
    return {"reference": str(record["reference"]), "decision": str(record["decision"]), "reason": str(record["reason"])}


def viewpoint(record: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": str(record["id"]),
        "viewpoint_id": str(record["viewpoint_id"]),
        "version": int(record["version"]),
        "status": str(record.get("status", "recorded")),
        "source_profile": str(record["source_profile"]),
        "instrument": str(record["instrument"]),
        "published_at": str(record["published_at"]),
        "confidence": str(record["confidence"]),
        "evaluation": _safe_evaluation(record.get("evaluation")),
        "audit_reference": _optional_text(record.get("audit_reference")),
    }


def sandbox_validation(record: Mapping[str, Any]) -> dict[str, object]:
    return {
        "status": str(record["status"]),
        "reason": str(record["reason"]),
        "audit_reference": str(record["audit_reference"]),
        "source_sha256": str(record["source_sha256"]),
    }


def _safe_evaluation(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        "status": str(value.get("status", "unevaluable")),
        "reason": _optional_text(value.get("reason")),
        "window_days": value.get("window_days"),
        "benchmark": _optional_text(value.get("benchmark")),
        "relative_return": value.get("relative_return"),
    }


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
