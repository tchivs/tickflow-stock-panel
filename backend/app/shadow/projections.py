"""Deny-by-default public projections for immutable Shadow research facts."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.shadow.schemas import validate_assumption_pair

_METRIC_FIELDS = (
    "precision",
    "recall",
    "coverage",
    "candidate_trades",
    "total_return",
    "max_drawdown",
    "costs",
    "actual_trade_consistency",
)
_FORBIDDEN_KEYS = frozenset(
    {
        "absolute_path",
        "account_alias",
        "account_secret",
        "raw_artifact",
        "raw_bytes",
        "raw_exception",
        "source_values",
        "stacktrace",
        "traceback",
        "worker_command",
        "runner_manifest",
    }
)


def import_preview(record: Mapping[str, Any], *, max_rows: int = 50) -> dict[str, object]:
    """Return a bounded sample without source paths, account aliases, or raw values."""
    rows = record.get("rows")
    safe_rows: list[dict[str, object]] = []
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
        for row in rows[:max_rows]:
            if isinstance(row, Mapping):
                safe_rows.append(
                    _select(
                        row,
                        (
                            "broker_fill_id",
                            "symbol",
                            "side",
                            "executed_at",
                            "quantity",
                            "price",
                            "fees",
                            "currency",
                            "source_row_ordinal",
                            "duplicate_group_hash",
                        ),
                    )
                )
    return {
        "status": str(record.get("status", "preview_ready")),
        "encoding": _optional_text(record.get("encoding")),
        "mapping_version": _optional_text(record.get("mapping_version")),
        "preview_identity": str(record.get("preview_identity", "")),
        "source_row_count": _nonnegative_int(record.get("source_row_count")),
        "sample_rows": safe_rows,
        "sample_truncated": _nonnegative_int(record.get("source_row_count")) > len(safe_rows),
    }


def batch(record: Mapping[str, Any]) -> dict[str, object]:
    diagnostics = record.get("diagnostics")
    safe_diagnostics: list[dict[str, object]] = []
    if isinstance(diagnostics, list):
        for diagnostic in diagnostics[:100]:
            if isinstance(diagnostic, Mapping):
                safe_diagnostics.append(
                    _select(
                        diagnostic,
                        ("severity", "code", "message", "source_row_ordinal"),
                    )
                )
    return {
        "id": str(record["id"]),
        "source_label": str(record.get("source_label", "Shadow import")),
        "content_sha256": str(record.get("content_sha256", "")),
        "importer_version": str(record.get("importer_version", "")),
        "mapping_version": str(record.get("mapping_version", "")),
        "supersedes_batch_id": _optional_text(record.get("supersedes_batch_id")),
        "same_content_as": _optional_text(record.get("same_content_as")),
        "source_row_count": _nonnegative_int(record.get("source_row_count")),
        "normalized_row_count": _nonnegative_int(record.get("normalized_row_count")),
        "rejected_row_count": _nonnegative_int(record.get("rejected_row_count")),
        "diagnostics": safe_diagnostics,
        "status": str(record.get("status", "rejected")),
        "created_at": str(record.get("created_at", "")),
    }


def evidence_set(record: Mapping[str, Any]) -> dict[str, object]:
    included_trades = _safe_strings(record.get("included_trade_ids"), maximum=100_000)
    exclusions: list[dict[str, str]] = []
    raw_exclusions = record.get("exclusions")
    if isinstance(raw_exclusions, list):
        for item in raw_exclusions[:100_000]:
            if isinstance(item, Mapping):
                trade_id, reason = item.get("trade_id"), item.get("reason")
                if isinstance(trade_id, str) and isinstance(reason, str):
                    exclusions.append({"trade_id": trade_id, "reason": reason[:1_000]})
    return {
        "id": str(record["id"]),
        "fingerprint": str(record.get("fingerprint", "")),
        "included_batch_ids": _safe_strings(record.get("included_batch_ids"), maximum=128),
        "included_trade_ids": included_trades,
        "included_trade_count": len(included_trades),
        "exclusions": exclusions,
        "created_at": str(record.get("created_at", "")),
    }


def candidate(record: Mapping[str, Any]) -> dict[str, object]:
    assumptions = validate_assumption_pair(
        exit_assumptions=record.get("exit_assumptions"),
        holding_assumptions=record.get("holding_assumptions"),
    )
    return {
        "id": str(record["id"]),
        "evidence_set_id": str(record.get("evidence_set_id", "")),
        "evidence_set_fingerprint": str(record.get("evidence_set_fingerprint", "")),
        "distiller_version": str(record.get("distiller_version", "")),
        "rule_schema_version": str(record.get("rule_schema_version", "")),
        "rules": _safe_json(record.get("rules")),
        "features": _safe_strings(record.get("features"), maximum=16),
        "parameters": _safe_json(record.get("parameters")),
        "exit_assumptions": assumptions.exit,
        "holding_assumptions": assumptions.holding,
        "source_batch_ids": _safe_strings(record.get("source_batch_ids"), maximum=128),
        "training_window": _safe_json(record.get("training_window")),
        "seed": record.get("seed") if isinstance(record.get("seed"), int) else None,
        "class_balance": _safe_json(record.get("class_balance")),
        "metrics": _safe_json(record.get("metrics")),
        "limitations": _safe_strings(record.get("limitations"), maximum=16),
        "rule_fingerprint": _optional_text(record.get("rule_fingerprint")),
        "created_at": str(record.get("created_at", "")),
    }


def evaluation(record: Mapping[str, Any]) -> dict[str, object]:
    artifact = record.get("artifact")
    public_artifact: dict[str, object] = {}
    if isinstance(artifact, Mapping):
        public_artifact = _select(
            artifact,
            (
                "artifact_id",
                "content_type",
                "byte_size",
                "checksum_sha256",
                "schema_version",
                "scope_sha256",
                "created_at",
            ),
        )
    metrics = record.get("metrics")
    public_metrics = _select(metrics, _METRIC_FIELDS) if isinstance(metrics, Mapping) else {}
    cost_policy = record.get("cost_policy")
    public_cost_policy = (
        _select(cost_policy, ("commission_bps", "slippage_bps", "stamp_duty_bps"))
        if isinstance(cost_policy, Mapping)
        else {}
    )
    return {
        "id": str(record["id"]),
        "candidate_id": str(record.get("candidate_id", "")),
        "evidence_set_id": str(record.get("evidence_set_id", "")),
        "evidence_set_fingerprint": str(record.get("evidence_set_fingerprint", "")),
        "run_id": _optional_text(record.get("run_id")),
        "retry_of_evaluation_id": _optional_text(record.get("retry_of_evaluation_id")),
        "split_kind": str(record.get("split_kind", "")),
        "window": _safe_json(record.get("window")),
        "governed_fingerprint": str(record.get("governed_fingerprint", "")),
        "artifact": public_artifact,
        "status": str(record.get("status", "failed")),
        "metrics": public_metrics,
        "terminal_reason": _optional_text(record.get("reason")),
        "adjustment_policy": _optional_text(record.get("adjustment_policy")),
        "cost_policy": public_cost_policy,
        "created_at": str(record.get("created_at", "")),
    }


def retention(record: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": str(record["id"]),
        "candidate_id": str(record.get("candidate_id", "")),
        "evidence_set_id": str(record.get("evidence_set_id", "")),
        "evidence_set_fingerprint": str(record.get("evidence_set_fingerprint", "")),
        "in_sample_evaluation_id": str(record.get("in_sample_evaluation_id", "")),
        "out_of_sample_evaluation_id": str(record.get("out_of_sample_evaluation_id", "")),
        "reviewer_principal": str(record.get("reviewer_principal", "")),
        "rationale": str(record.get("rationale", ""))[:4_000],
        "status": str(record.get("status", "retained_research_only")),
        "created_at": str(record.get("created_at", "")),
    }


def page(items: list[dict[str, object]], *, offset: int, limit: int) -> dict[str, object]:
    return {
        "items": items[offset : offset + limit],
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < len(items),
        "total": len(items),
    }


def _select(record: Mapping[str, Any], fields: Sequence[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for field in fields:
        value = record.get(field)
        if field in _FORBIDDEN_KEYS or value is None or isinstance(value, (Mapping, list, tuple, bytes)):
            continue
        if isinstance(value, (str, int, float, bool)):
            result[field] = value
    return result


def _safe_json(value: object, *, depth: int = 0) -> object:
    if depth > 5:
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _safe_json(item, depth=depth + 1)
            for key, item in value.items()
            if isinstance(key, str) and key not in _FORBIDDEN_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_json(item, depth=depth + 1) for item in value[:1_000]]
    return None


def _safe_strings(value: object, *, maximum: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:maximum] if isinstance(item, str)]


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
