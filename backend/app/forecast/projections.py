"""Deny-by-default public projections for immutable Forecast state."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_PUBLIC_STATUS = {
    "timed_out": "timeout",
    "resource_limited": "resource_terminated",
    "model_unavailable": "checkpoint_mismatch",
}
_STAGE = {
    "queued": "validating_checkpoint",
    "running": "generating_paths",
    "completed": "completed",
    "validation_failed": "validation_failed",
    "model_unavailable": "checkpoint_mismatch",
    "artifact_failed": "artifact_failed",
    "timed_out": "timeout",
    "resource_limited": "resource_terminated",
    "interrupted": "interrupted",
}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _status(value: object) -> str:
    raw = str(value)
    return _PUBLIC_STATUS.get(raw, raw)


def _safe_descriptor(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    projected: dict[str, object] = {}
    for key in (
        "artifact_id",
        "schema_version",
        "content_type",
        "byte_size",
        "checksum_sha256",
        "scope_sha256",
        "created_at",
        "sample_count",
        "horizon",
        "feature_count",
    ):
        item = value.get(key)
        if isinstance(item, (str, int)) and not isinstance(item, bool):
            projected[key] = item
    return projected or None


def job(record: Mapping[str, object], *, record_id: str | None = None) -> dict[str, object]:
    status = _status(record.get("status"))
    raw_status = str(record.get("status"))
    result: dict[str, object] = {
        "id": str(record["id"]),
        "instrument": str(record["instrument_id"]),
        "horizon": int(record["horizon"]),
        "catalog_id": str(record["catalog_id"]),
        "status": status,
        "stage": _STAGE.get(raw_status, "interrupted"),
        "stage_recorded_at": str(record.get("updated_at") or record.get("created_at") or ""),
        "attempt": int(record.get("attempt", 1)),
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or record.get("created_at") or ""),
    }
    retry_of = _text(record.get("retry_of_job_id"))
    if retry_of is not None:
        result["retry_of_job_id"] = retry_of
    reason = _text(record.get("terminal_reason"))
    if reason is not None:
        result["safe_reason"] = reason
    if status == "completed" and record_id is not None:
        result["record_id"] = record_id
    return result


def progress(record: Mapping[str, object]) -> dict[str, str]:
    projected = job(record)
    event = {
        "job_id": str(projected["id"]),
        "status": str(projected["status"]),
        "stage": str(projected["stage"]),
        "stage_recorded_at": str(projected["stage_recorded_at"]),
    }
    reason = projected.get("safe_reason")
    if isinstance(reason, str):
        event["safe_reason"] = reason
    return event


def record(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {
        "id": str(value["id"]),
        "job_id": str(value["job_id"]),
        "instrument": str(value["instrument_id"]),
        "origin_session_id": str(value["origin_session_id"]),
        "calendar_id": str(value["calendar_id"]),
        "calendar_revision": str(value["calendar_revision"]),
        "future_session_ids": [str(item) for item in value.get("future_session_ids", [])],
        "input_fingerprint": str(value["input_fingerprint"]),
        "horizon": int(value["horizon"]),
        "lookback": int(value["lookback"]),
        "seed": int(value["seed"]),
        "temperature": float(value["temperature"]),
        "top_k": int(value["top_k"]),
        "top_p": float(value["top_p"]),
        "sample_count": int(value["sample_count"]),
        "catalog_id": str(value["catalog_id"]),
        "source_revision": str(value["source_revision"]),
        "source_digest_sha256": str(value["source_digest_sha256"]),
        "model_revision": str(value["model_revision"]),
        "model_digest_sha256": str(value["model_digest_sha256"]),
        "tokenizer_revision": str(value["tokenizer_revision"]),
        "tokenizer_digest_sha256": str(value["tokenizer_digest_sha256"]),
        "paths_checksum_sha256": str(value["paths_checksum_sha256"]),
        "validation_warnings": [
            str(item) for item in value.get("validation_warnings", [])
            if isinstance(item, str)
        ],
        "created_at": str(value["created_at"]),
    }
    input_descriptor = _safe_descriptor(value.get("input_artifact_descriptor"))
    output_descriptor = _safe_descriptor(value.get("output_artifact_descriptor"))
    if input_descriptor is not None:
        result["input_artifact"] = input_descriptor
    if output_descriptor is not None:
        result["output_artifact"] = output_descriptor
    quantiles = value.get("quantiles")
    if isinstance(quantiles, Mapping):
        result["quantiles"] = {
            str(horizon): {
                label: float(number)
                for label in ("p10", "p50", "p90")
                if isinstance((number := values.get(label)), (int, float))
                and not isinstance(number, bool)
            }
            for horizon, values in quantiles.items()
            if isinstance(values, Mapping)
        }
    return result


def outcome(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {
        "id": str(value["id"]),
        "forecast_id": str(value["forecast_id"]),
        "horizon": int(value["horizon"]),
        "status": str(value["status"]),
        "actual_session_id": str(value["actual_session_id"]),
        "actual_close": value.get("actual_close"),
        "observed_at": str(value["observed_at"]),
    }
    fingerprint = _text(value.get("actual_fingerprint"))
    reason = _text(value.get("reason"))
    if fingerprint is not None:
        result["actual_fingerprint"] = fingerprint
    if reason is not None:
        result["reason"] = reason
    return result


def calibration(value: Mapping[str, object]) -> dict[str, object]:
    return {
        "id": str(value["id"]),
        "forecast_id": str(value["forecast_id"]),
        "outcome_id": str(value["outcome_id"]),
        "metric_schema": str(value["metric_schema"]),
        "metric_version": _metric_version(str(value["metric_schema"])),
        "close_mae": value.get("close_mae"),
        "p10_p90_interval_covered": value.get("p10_p90_interval_covered"),
        "pinball_p10": value.get("pinball_p10"),
        "pinball_p50": value.get("pinball_p50"),
        "pinball_p90": value.get("pinball_p90"),
        "coverage_start": value.get("coverage_start"),
        "coverage_end": value.get("coverage_end"),
        "created_at": str(value["created_at"]),
    }


def catalog_entry(value: Mapping[str, object]) -> dict[str, object]:
    allowed: dict[str, object] = {}
    for key in (
        "catalog_id",
        "source_repository",
        "source_revision",
        "model_repo",
        "model_revision",
        "model_weight_sha256",
        "tokenizer_repo",
        "tokenizer_revision",
        "tokenizer_weight_sha256",
        "pairing",
        "max_context",
        "allowed_devices",
        "weight_format",
        "local_files_only",
        "trust_remote_code",
    ):
        item = value.get(key)
        if isinstance(item, (str, int, bool, tuple, list)):
            allowed[key] = list(item) if isinstance(item, tuple) else item
    return allowed


def path_page(
    rows: Sequence[Mapping[str, object]], *, offset: int, limit: int, total: int
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for row in rows[:limit]:
        projected: dict[str, object] = {}
        for key in ("path_index", "session_id", "feature", "value", "warning_code"):
            item = row.get(key)
            if isinstance(item, (str, int, float)) and not isinstance(item, bool):
                projected[key] = item
        items.append(projected)
    return {
        "items": items,
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": offset + len(items) < total,
    }


def page(items: Sequence[dict[str, object]], *, offset: int, limit: int) -> dict[str, object]:
    total = len(items)
    selected = list(items[offset : offset + limit])
    return {
        "items": selected,
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": offset + len(selected) < total,
    }


def _metric_version(schema: str) -> int:
    marker = schema.rsplit("-v", 1)
    return int(marker[1]) if len(marker) == 2 and marker[1].isdigit() else 1
