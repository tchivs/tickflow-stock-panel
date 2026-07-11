"""Governed market-data manifest contract tests (CORE-02)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest


DAILY_SCHEMA = {
    "symbol": "string",
    "date": "date",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
    "amount": "float64",
    "quote_ts": "int64",
}


def _write_daily_part(lake_dir: Path, partition: str, frame: pl.DataFrame) -> Path:
    path = lake_dir / "kline_daily" / f"date={partition}" / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)
    return path


def _daily_frame(*, rows: int = 1, quote_ts: int = 1704180600000) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": ["600000.SH"] * rows,
            "date": [date(2024, 1, 2)] * rows,
            "open": [7.10] * rows,
            "high": [7.30] * rows,
            "low": [7.05] * rows,
            "close": [7.25] * rows,
            "volume": [1000.0] * rows,
            "amount": [7250.0] * rows,
            "quote_ts": [quote_ts] * rows,
        }
    )


def _write_manifest(lake_dir: Path, **overrides: object) -> Path:
    manifest = {
        "data_dir": str(lake_dir),
        "datasets": [
            {
                "name": "daily",
                "glob": "kline_daily/**/*.parquet",
                "primary_key": ["symbol", "date"],
                "market_timezone": "Asia/Shanghai",
                "time_column": "quote_ts",
                "schema": DAILY_SCHEMA,
                "mode": "append",
            }
        ],
    }
    manifest["datasets"][0].update(overrides)
    path = lake_dir / "market-data-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _validator():
    from app.contracts.validator import DataContractViolation, validate_market_data_manifest

    return DataContractViolation, validate_market_data_manifest


def test_d17_governed_data_rejects_duplicate_daily_primary_keys(tmp_path):
    lake_dir = tmp_path / "governed-lake"
    _write_daily_part(lake_dir, "2024-01-02", _daily_frame(rows=2))
    violation, validate = _validator()

    with pytest.raises(violation, match="D-17.*primary-key"):
        validate(_write_manifest(lake_dir))


def test_d17_governed_data_rejects_invalid_asia_shanghai_market_time(tmp_path):
    lake_dir = tmp_path / "governed-lake"
    _write_daily_part(lake_dir, "2024-01-02", _daily_frame(quote_ts=0))
    violation, validate = _validator()

    with pytest.raises(violation, match="D-17.*market-time"):
        validate(_write_manifest(lake_dir))


def test_d17_governed_data_rejects_repair_outside_permitted_replacement_window(tmp_path):
    lake_dir = tmp_path / "governed-lake"
    _write_daily_part(lake_dir, "2024-01-02", _daily_frame())
    violation, validate = _validator()

    with pytest.raises(violation, match="D-17.*repair-window"):
        validate(
            _write_manifest(
                lake_dir,
                mode="repair",
                repair_window={"start": "2024-01-03", "end": "2024-01-05"},
            )
        )


def test_d17_governed_data_rejects_incompatible_parquet_schema_drift(tmp_path):
    lake_dir = tmp_path / "governed-lake"
    _write_daily_part(lake_dir, "2024-01-02", _daily_frame())
    drifted = _daily_frame().with_columns(pl.lit("7.25").alias("close"))
    _write_daily_part(lake_dir, "2024-01-03", drifted)
    violation, validate = _validator()

    with pytest.raises(violation, match="D-17.*schema-drift"):
        validate(_write_manifest(lake_dir))
