"""Deterministic validation for governed market-data Parquet partitions."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from app.contracts.market_data import DATASET_CONTRACTS


class DataContractViolation(ValueError):
    """A governed lake dataset violates D-17."""


def _violation(category: str, detail: str) -> DataContractViolation:
    return DataContractViolation(f"D-17 {category}: {detail}")


def _normalise_type(dtype: pl.DataType) -> str:
    name = str(dtype).lower()
    aliases = {
        "string": "string",
        "utf8": "string",
        "date": "date",
        "float64": "float64",
        "float32": "float32",
        "int64": "int64",
        "int32": "int32",
        "uint32": "uint32",
        "uint64": "uint64",
    }
    return aliases.get(name, name)


def _load_manifest(manifest_path: Path) -> tuple[Path, list[dict[str, Any]]]:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _violation("manifest", f"cannot load {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("datasets"), list):
        raise _violation("manifest", "datasets must be a list")
    data_dir = Path(raw.get("data_dir") or manifest_path.parent)
    return data_dir, [item for item in raw["datasets"] if isinstance(item, dict)]


def _dataset_files(data_dir: Path, glob: str) -> list[Path]:
    path = Path(glob)
    if path.is_absolute() or ".." in path.parts:
        raise _violation("manifest", f"dataset glob must stay within the lake: {glob}")
    return sorted(path for path in data_dir.glob(glob) if path.is_file())


def _validate_schema(files: list[Path], expected: dict[str, str], name: str) -> None:
    baseline: dict[str, str] | None = None
    for file in files:
        try:
            schema = {_name: _normalise_type(dtype) for _name, dtype in pl.read_parquet_schema(file).items()}
        except Exception as exc:  # noqa: BLE001
            raise _violation("schema-drift", f"{name} cannot read {file.name}: {exc}") from exc
        if baseline is None:
            baseline = schema
        elif schema != baseline:
            raise _violation("schema-drift", f"{name} differs across partitions at {file}")
        for column, type_name in expected.items():
            if schema.get(column) != type_name:
                actual = schema.get(column, "missing")
                raise _violation(
                    "schema-drift", f"{name}.{column} expected {type_name}, found {actual} in {file}")


def _read_dataset(files: list[Path], name: str) -> pl.DataFrame:
    try:
        return pl.concat([pl.read_parquet(file) for file in files], how="vertical")
    except Exception as exc:  # noqa: BLE001
        raise _violation("schema-drift", f"{name} cannot combine partitions: {exc}") from exc


def _validate_primary_key(frame: pl.DataFrame, columns: list[str], name: str) -> None:
    if not columns:
        return
    if any(column not in frame.columns for column in columns):
        raise _violation("primary-key", f"{name} missing key columns {columns}")
    if frame.select(pl.struct(columns).is_duplicated().any()).item():
        raise _violation("primary-key", f"{name} contains duplicate {columns}")


def _validate_market_time(frame: pl.DataFrame, dataset: dict[str, Any], name: str) -> None:
    time_column = dataset.get("time_column")
    if not time_column:
        return
    if time_column not in frame.columns or "date" not in frame.columns:
        raise _violation("market-time", f"{name} requires {time_column} and date")
    timezone_name = dataset.get("market_timezone", "Asia/Shanghai")
    try:
        market_timezone = ZoneInfo(timezone_name)
    except Exception as exc:  # noqa: BLE001
        raise _violation("market-time", f"invalid timezone {timezone_name}") from exc
    for record in frame.select(["date", time_column]).iter_rows(named=True):
        timestamp = record[time_column]
        try:
            market_time = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).astimezone(market_timezone)
        except (TypeError, ValueError, OSError) as exc:
            raise _violation("market-time", f"{name} has invalid {time_column}={timestamp!r}") from exc
        if market_time.date() != record["date"] or not (time(9, 0) <= market_time.timetz().replace(tzinfo=None) <= time(15, 30)):
            raise _violation("market-time", f"{name} has out-of-session {time_column}={timestamp!r}")


def _validate_repair_window(frame: pl.DataFrame, dataset: dict[str, Any], name: str) -> None:
    if dataset.get("mode") != "repair":
        return
    window = dataset.get("repair_window")
    if not isinstance(window, dict) or "start" not in window or "end" not in window:
        raise _violation("repair-window", f"{name} repair mode requires start and end")
    try:
        start = date.fromisoformat(str(window["start"]))
        end = date.fromisoformat(str(window["end"]))
    except ValueError as exc:
        raise _violation("repair-window", f"{name} repair window must use ISO dates") from exc
    if start > end:
        raise _violation("repair-window", f"{name} repair window start exceeds end")
    if "date" not in frame.columns or frame.filter((pl.col("date") < start) | (pl.col("date") > end)).height:
        raise _violation("repair-window", f"{name} contains rows outside {start}..{end}")


def validate_market_data_manifest(manifest_path: Path) -> None:
    """Validate every dataset declared by an explicit governed-lake manifest."""
    data_dir, datasets = _load_manifest(Path(manifest_path))
    for dataset in sorted(datasets, key=lambda item: str(item.get("name", ""))):
        name = str(dataset.get("name") or "unnamed")
        glob = dataset.get("glob")
        schema = dataset.get("schema")
        if not isinstance(glob, str) or not isinstance(schema, dict):
            raise _violation("manifest", f"{name} requires glob and schema")
        files = _dataset_files(data_dir, glob)
        if not files:
            raise _violation("schema-drift", f"{name} has no Parquet partitions")
        expected = {str(column): str(dtype).lower() for column, dtype in schema.items()}
        _validate_schema(files, expected, name)
        frame = _read_dataset(files, name)
        _validate_primary_key(frame, [str(key) for key in dataset.get("primary_key", [])], name)
        _validate_market_time(frame, dataset, name)
        _validate_repair_window(frame, dataset, name)


def validate_market_data_contract(data_dir: Path) -> None:
    """Validate all Phase 1 governed datasets written to a fixture lake."""
    data_dir = Path(data_dir)
    for name, contract in DATASET_CONTRACTS.items():
        files = _dataset_files(data_dir, str(contract["glob"]))
        if not files:
            raise _violation("schema-drift", f"{name} has no Parquet partitions")
        _validate_schema(files, dict(contract["schema"]), name)
        frame = _read_dataset(files, name)
        _validate_primary_key(frame, list(contract["primary_key"]), name)
        if name in {"daily", "enriched"}:
            _validate_market_time(frame, {"time_column": "quote_ts", "market_timezone": "Asia/Shanghai"}, name)


__all__ = ["DataContractViolation", "validate_market_data_contract", "validate_market_data_manifest"]
