"""Typed contracts for deterministic Phase 1 market-data fixtures and lake datasets."""
from __future__ import annotations

from datetime import date
import math
import os
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class FixtureContractError(ValueError):
    """Fixture data violates the isolated Phase 1 file contract."""


class _StrictFixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FixtureInstrument(_StrictFixtureModel):
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    total_shares: float | None = None
    float_shares: float | None = None

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
    index_daily: list[FixtureDailyBar] = Field(default_factory=list)
    adjustment_factors: list[FixtureAdjustmentFactor] = Field(min_length=1)
    financials: list[FixtureFinancialRecord] = Field(min_length=1)


class FixtureBundle(_StrictFixtureModel):
    """The exact two-file fixture layout mounted by Phase 1 Compose acceptance."""

    instruments: list[FixtureInstrument]
    daily: list[FixtureDailyBar]
    index_daily: list[FixtureDailyBar]
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
        if os.environ.get("ADVANCED_HOST_FIXTURE", "").strip() and not market_data.index_daily:
            raise FixtureContractError("host fixture requires non-empty benchmark index_daily data")
        return cls(
            instruments=instruments.instruments,
            daily=market_data.daily,
            index_daily=market_data.index_daily,
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
    def index_daily_frame(self) -> pl.DataFrame:
        return pl.DataFrame(
            [item.model_dump() for item in self.index_daily],
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




class FixtureDateRange(_StrictFixtureModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _has_ordered_bounds(self) -> "FixtureDateRange":
        if self.start > self.end:
            raise ValueError("start must not exceed end")
        return self

    def contains(self, other: "FixtureDateRange") -> bool:
        return self.start <= other.start and other.end <= self.end


class FixtureStrategyReadiness(_StrictFixtureModel):
    id: str = Field(min_length=1)
    warmup_trading_days: int = Field(gt=0)


class AdvancedFixtureReadiness(_StrictFixtureModel):
    """Deployment-owned bounds required before a host fixture may enter the lake."""

    benchmark_symbol: str = Field(min_length=1)
    symbols: list[str] = Field(min_length=1)
    required_coverage: FixtureDateRange
    evaluation_windows: list[int]
    strategy: FixtureStrategyReadiness
    aggregate_coverage: FixtureDateRange
    in_sample: FixtureDateRange
    out_of_sample: FixtureDateRange

    @model_validator(mode="after")
    def _has_complete_host_policy(self) -> "AdvancedFixtureReadiness":
        if self.benchmark_symbol != "000300.SH":
            raise ValueError("advanced host benchmark_symbol must be 000300.SH")
        if any(not symbol.strip() for symbol in self.symbols) or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("symbols must be non-empty and unique")
        if self.evaluation_windows != [20, 60, 120]:
            raise ValueError("evaluation_windows must be exactly [20, 60, 120]")
        if self.strategy.id != "bullish_alignment":
            raise ValueError("advanced host strategy must be bullish_alignment")
        if self.in_sample.end >= self.out_of_sample.start:
            raise ValueError("in_sample and out_of_sample must not overlap")
        if not self.aggregate_coverage.contains(self.required_coverage):
            raise ValueError("aggregate_coverage must contain required_coverage")
        if not self.aggregate_coverage.contains(self.in_sample) or not self.aggregate_coverage.contains(self.out_of_sample):
            raise ValueError("aggregate_coverage must contain both split ranges")
        return self


def _validate_bar_semantics(bar: FixtureDailyBar, *, dataset: str) -> None:
    values = {
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "amount": bar.amount,
    }
    for field, value in values.items():
        if not math.isfinite(value) or value <= 0:
            raise FixtureContractError(f"{dataset} {bar.symbol} {bar.date} has invalid {field}")
    if not bar.low <= bar.open <= bar.high or not bar.low <= bar.close <= bar.high:
        raise FixtureContractError(f"{dataset} {bar.symbol} {bar.date} has invalid OHLC ordering")
    from app.contracts.validator import is_market_session_timestamp

    if not is_market_session_timestamp(bar.date, bar.quote_ts):
        raise FixtureContractError(f"{dataset} {bar.symbol} {bar.date} has invalid or out-of-session quote_ts")


def _validate_ordered_history(bars: list[FixtureDailyBar], *, dataset: str) -> dict[str, list[FixtureDailyBar]]:
    by_symbol: dict[str, list[FixtureDailyBar]] = {}
    for bar in bars:
        _validate_bar_semantics(bar, dataset=dataset)
        history = by_symbol.setdefault(bar.symbol, [])
        if history and bar.date <= history[-1].date:
            detail = "duplicate" if bar.date == history[-1].date else "non-chronological"
            raise FixtureContractError(f"{dataset} {bar.symbol} history is {detail}")
        history.append(bar)
    return by_symbol


def _weekday_dates(coverage: FixtureDateRange) -> set[date]:
    cursor = coverage.start
    expected: set[date] = set()
    while cursor <= coverage.end:
        if cursor.weekday() < 5:
            expected.add(cursor)
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return expected


def bullish_alignment_eligible_from_bars(bars: list[FixtureDailyBar]) -> bool:
    """Derive the installed strategy inputs from bounded raw bars, then run its predicate."""
    from app.strategy.builtin.bullish_alignment import eligibility_expression

    if len(bars) < 61:
        return False
    rows: list[dict[str, float | str]] = []
    closes = [bar.close for bar in bars]
    for index in range(60, len(bars)):
        rows.append(
            {
                "symbol": bars[index].symbol,
                "ma5": sum(closes[index - 4:index + 1]) / 5,
                "ma10": sum(closes[index - 9:index + 1]) / 10,
                "ma20": sum(closes[index - 19:index + 1]) / 20,
                "ma60": sum(closes[index - 59:index + 1]) / 60,
                "momentum_20d": closes[index] / closes[index - 20] - 1,
            }
        )
    frame = pl.DataFrame(rows)
    return frame.filter(eligibility_expression({})).height > 0


def preflight_advanced_host_fixture(bundle: FixtureBundle, readiness: AdvancedFixtureReadiness) -> None:
    """Reject unready host fixture data before a DataStore or governed write exists."""
    daily_history = _validate_ordered_history(bundle.daily, dataset="daily")
    index_history = _validate_ordered_history(bundle.index_daily, dataset="index_daily")
    benchmark_history = index_history.get(readiness.benchmark_symbol)
    if benchmark_history is None:
        raise FixtureContractError(f"advanced host requires benchmark {readiness.benchmark_symbol}")
    required_dates = _weekday_dates(readiness.required_coverage)
    for symbol in readiness.symbols:
        history = daily_history.get(symbol)
        if history is None:
            raise FixtureContractError(f"advanced host requires configured symbol {symbol}")
        dates = {bar.date for bar in history}
        if not required_dates.issubset(dates):
            raise FixtureContractError(f"daily {symbol} lacks required coverage")
        if len(history) < readiness.strategy.warmup_trading_days + max(readiness.evaluation_windows):
            raise FixtureContractError(f"daily {symbol} lacks strategy warmup and evaluation history")
        if not bullish_alignment_eligible_from_bars(history):
            raise FixtureContractError(f"daily {symbol} has no eligible {readiness.strategy.id} signal")
    benchmark_dates = {bar.date for bar in benchmark_history}
    if not required_dates.issubset(benchmark_dates):
        raise FixtureContractError(f"benchmark {readiness.benchmark_symbol} lacks required coverage")
    if len(benchmark_history) < readiness.strategy.warmup_trading_days + max(readiness.evaluation_windows):
        raise FixtureContractError(f"benchmark {readiness.benchmark_symbol} lacks required history")
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
