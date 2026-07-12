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
        "direction": str(record.get("direction", "neutral")),
        "rating": str(record.get("rating", "neutral")),
        "conclusion": str(record.get("conclusion", "")),
        "target_range": list(record.get("target_range", [])),
        "horizon_days": record.get("horizon_days"),
        "confidence": str(record["confidence"]),
        "revision_kind": str(record.get("revision_kind", "initial")),
        "correction_reason": _optional_text(record.get("correction_reason")),
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


def sandbox_run(record: Mapping[str, Any]) -> dict[str, object]:
    """Expose terminal run facts without source, paths, or runner diagnostics."""
    manifest = record.get("runner_manifest")
    if not isinstance(manifest, Mapping):
        manifest = {}
    resources = manifest.get("resources")
    return {
        "status": str(manifest.get("status", "failed")),
        "proof_fingerprint": _optional_text(manifest.get("proof_fingerprint")),
        "resources": _safe_mapping(resources),
        "audit_reference": _optional_text(manifest.get("audit_reference")),
        "run_id": str(record["id"]),
    }


def experiment_specification(record: Mapping[str, Any]) -> dict[str, object]:
    """Project immutable specification facts without owner identity or raw criteria objects."""
    return {
        "id": str(record["id"]),
        "research_asset_id": str(record["research_asset_id"]),
        "version": int(record["version"]),
        "hypothesis": str(record["hypothesis"]),
        "data_scope": _safe_mapping(record.get("data_scope")),
        "method": str(record["method"]),
        "metrics": _safe_strings(record.get("metrics")),
        "created_at": str(record["created_at"]),
    }


def experiment_run(record: Mapping[str, Any]) -> dict[str, object]:
    """Return an allowlisted manifest that cannot disclose runner diagnostics."""
    resources = _safe_mapping(record.get("resources"))
    return {
        "id": str(record["id"]),
        "specification_id": str(record["specification_id"]),
        "status": str(record["status"]),
        "governed_fingerprint": str(record["governed_fingerprint"]),
        "asset_version": _optional_text(record.get("asset_version")),
        "parameters": _safe_mapping(record.get("resolved_parameters")),
        "environment": _safe_mapping(record.get("environment")),
        "resource_limits": resources,
        "metrics": _safe_mapping(record.get("metrics")),
        "artifact_count": len(record.get("artifacts", [])) if isinstance(record.get("artifacts"), list) else 0,
        "constraint_reason": _optional_text(record.get("constraint_reason")),
        "created_at": str(record["created_at"]),
    }


def experiment_feedback(record: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": str(record["id"]),
        "run_id": str(record["run_id"]),
        "conclusion": str(record["conclusion"]),
        "notes": _optional_text(record.get("notes")) or "已记录受控研究反馈",
        "created_at": str(record.get("created_at", "")),
    }


def candidate(record: Mapping[str, Any], gates: list[Mapping[str, Any]]) -> dict[str, object]:
    return {
        "id": str(record["id"]),
        "parent_asset_id": str(record["parent_research_asset_id"]),
        "parent_version": str(record["parent_version"]),
        "mutation": str(record["mutation_operation"]),
        "seed": int(record["seed"]),
        "resolved_config": _safe_mapping(record.get("resolved_configuration")),
        "created_at": str(record["created_at"]),
        "gates": [
            {
                "name": str(gate["gate"]),
                "status": str(gate["status"]),
                "evidence": _optional_text(_safe_mapping(gate.get("evidence")).get("summary")) or "已记录受控证据",
            }
            for gate in gates
        ],
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


def _safe_mapping(value: object) -> dict[str, str | int | float | bool]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(item, (str, int, float, bool))}


def _safe_strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
