"""Typed contracts for deterministic Phase 1 market-data fixtures and lake datasets."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class FixtureContractError(ValueError):
    """Fixture data violates the isolated Phase 1 file contract."""


class _StrictFixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FixtureInstrument(_StrictFixtureModel):
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    exchange: str = Field(min_length=1)


class FixtureDailyBar(_StrictFixtureModel):
    symbol: str = Field(min_length=1)
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    quote_ts: int


class FixtureAdjustmentFactor(_StrictFixtureModel):
    symbol: str = Field(min_length=1)
    trade_date: date
    adj_factor: float


class FixtureFinancialRecord(_StrictFixtureModel):
    symbol: str = Field(min_length=1)
    report_date: date
    roe: float


class InstrumentsFixtureFile(_StrictFixtureModel):
    instruments: list[FixtureInstrument] = Field(min_length=1)


class MarketDataFixtureFile(_StrictFixtureModel):
    daily: list[FixtureDailyBar] = Field(min_length=1)
    adjustment_factors: list[FixtureAdjustmentFactor] = Field(min_length=1)
    financials: list[FixtureFinancialRecord] = Field(min_length=1)


class FixtureBundle(_StrictFixtureModel):
    """The exact two-file fixture layout mounted by Phase 1 Compose acceptance."""

    instruments: list[FixtureInstrument]
    daily: list[FixtureDailyBar]
    adjustment_factors: list[FixtureAdjustmentFactor]
    financials: list[FixtureFinancialRecord]

    INSTRUMENTS_FILENAME: ClassVar[str] = "instruments.json"
    MARKET_DATA_FILENAME: ClassVar[str] = "market-data.json"

    @classmethod
    def load(cls, fixture_dir: Path) -> "FixtureBundle":
        fixture_dir = Path(fixture_dir)
        if not fixture_dir.is_dir():
            raise FixtureContractError(f"fixture directory does not exist: {fixture_dir}")
        if fixture_dir.stat().st_mode & 0o222:
            raise FixtureContractError("fixture directory must be mounted read-only")

        expected = {cls.INSTRUMENTS_FILENAME, cls.MARKET_DATA_FILENAME}
        actual = {path.name for path in fixture_dir.iterdir()}
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise FixtureContractError(
                f"fixture directory must contain exactly {sorted(expected)}; "
                f"missing={missing}, extra={extra}"
            )

        def read_model(path: Path, model: type[BaseModel]) -> BaseModel:
            if path.stat().st_mode & 0o222:
                raise FixtureContractError(f"fixture file must be read-only: {path.name}")
            try:
                return model.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError) as exc:
                raise FixtureContractError(f"invalid fixture {path.name}: {exc}") from exc

        instruments = read_model(fixture_dir / cls.INSTRUMENTS_FILENAME, InstrumentsFixtureFile)
        market_data = read_model(fixture_dir / cls.MARKET_DATA_FILENAME, MarketDataFixtureFile)
        return cls(
            instruments=instruments.instruments,
            daily=market_data.daily,
            adjustment_factors=market_data.adjustment_factors,
            financials=market_data.financials,
        )

    def instruments_frame(self) -> pl.DataFrame:
        return pl.DataFrame([item.model_dump() for item in self.instruments])

    def daily_frame(self) -> pl.DataFrame:
        return pl.DataFrame(
            [item.model_dump() for item in self.daily],
            schema={
                "symbol": pl.String,
                "date": pl.Date,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
                "amount": pl.Float64,
                "quote_ts": pl.Int64,
            },
        )

    def adjustment_factors_frame(self) -> pl.DataFrame:
        return pl.DataFrame(
            [item.model_dump() for item in self.adjustment_factors],
            schema={"symbol": pl.String, "trade_date": pl.Date, "adj_factor": pl.Float64},
        )

    def financials_frame(self) -> pl.DataFrame:
        return pl.DataFrame(
            [item.model_dump() for item in self.financials],
            schema={"symbol": pl.String, "report_date": pl.Date, "roe": pl.Float64},
        )


DATASET_CONTRACTS: dict[str, dict[str, object]] = {
    "instruments": {
        "glob": "instruments/**/*.parquet",
        "primary_key": ["symbol"],
        "schema": {"symbol": "string", "name": "string", "code": "string", "exchange": "string"},
    },
    "daily": {
        "glob": "kline_daily/**/*.parquet",
        "primary_key": ["symbol", "date"],
        "market_timezone": "Asia/Shanghai",
        "time_column": "quote_ts",
        "schema": {
            "symbol": "string", "date": "date", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64", "amount": "float64",
            "quote_ts": "int64",
        },
    },
    "adjustment_factors": {
        "glob": "adj_factor/**/*.parquet",
        "primary_key": ["symbol", "trade_date"],
        "schema": {"symbol": "string", "trade_date": "date", "ex_factor": "float64"},
    },
    "financials": {
        "glob": "financials/**/*.parquet",
        "primary_key": ["symbol", "report_date"],
        "schema": {"symbol": "string", "report_date": "date", "roe": "float64"},
    },
    "enriched": {
        "glob": "kline_daily_enriched/**/*.parquet",
        "primary_key": ["symbol", "date"],
        "schema": {
            "symbol": "string", "date": "date", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64", "amount": "float64",
            "raw_close": "float64", "raw_high": "float64", "raw_low": "float64",
            "turnover_rate": "float64", "consecutive_limit_ups": "uint32",
            "consecutive_limit_downs": "uint32", "quote_ts": "int64",
        },
    },
}
