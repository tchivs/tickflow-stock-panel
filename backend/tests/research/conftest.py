"""Shared fixtures for the Phase 10 factor-research test suite.

These fixtures are the contract surface consumed by the signal-chain, admission,
composite-model, and universe-resolution tests scaffolded by 10-02 and turned green
by 10-01/10-04.  The stub engine substitutes the governed ``BacktestEngine``
boundary so research code cannot inspect market-data provenance; the stub universe
resolver substitutes the PIT resolver until 10-04 lands the production one.
"""
from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository

FIXTURE_SYMBOLS = ("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ")


class StubBacktestEngine:
    """A governed-panel boundary substitute; research code cannot inspect its source."""

    def __init__(self, panel: pl.DataFrame) -> None:
        self.panel = panel
        self.calls: list[dict[str, Any]] = []

    def load_panel(self, symbols, start, end, *, columns, asset_type):  # type: ignore[no-untyped-def]
        self.calls.append(
            {
                "symbols": tuple(symbols) if symbols is not None else None,
                "start": start,
                "end": end,
                "columns": tuple(columns),
                "asset_type": asset_type,
            }
        )
        return self.panel.select([column for column in columns if column in self.panel.columns])


def membership_fingerprint(symbols: frozenset[str]) -> str:
    """Deterministic membership fingerprint: sha256 over the sorted symbol tuple."""
    return sha256(",".join(sorted(symbols)).encode("utf-8")).hexdigest()


class StubUniverseResolver:
    """Fixture PIT resolver bound to a static ``[symbol, date]`` membership frame."""

    def __init__(self, membership: pl.DataFrame) -> None:
        self.membership = membership

    def resolve_universe(
        self, *, universe_name: str, as_of: date, asset_type: str = "stock"
    ) -> tuple[frozenset[str], str]:
        del universe_name, asset_type
        eligible = self.membership.filter(pl.col("date") <= as_of)
        symbols = frozenset(eligible["symbol"].unique().to_list())
        return symbols, membership_fingerprint(symbols)

    def resolve_universe_daily(
        self, *, universe_name: str, start: date, end: date, asset_type: str = "stock"
    ) -> pl.DataFrame:
        del universe_name, asset_type
        return self.membership.filter((pl.col("date") >= start) & (pl.col("date") <= end))


@pytest.fixture
def fixture_panel() -> pl.DataFrame:
    """A two-date, four-symbol panel with deterministic close and forward returns."""
    first = date(2024, 1, 2)
    returns = {"000001.SZ": 0.0, "000002.SZ": 0.5, "000003.SZ": 0.1, "000004.SZ": 0.9}
    factors = {"000001.SZ": 1.0, "000002.SZ": 2.0, "000003.SZ": 3.0, "000004.SZ": 4.0}
    rows: list[dict[str, object]] = []
    for symbol, value in factors.items():
        rows.append({"symbol": symbol, "date": first, "close": value})
        rows.append(
            {"symbol": symbol, "date": first + timedelta(days=1), "close": value * (1 + returns[symbol])}
        )
    return pl.DataFrame(rows)


@pytest.fixture
def fixture_membership() -> pl.DataFrame:
    """Per-date membership covering the fixture panel: every symbol on both dates."""
    first = date(2024, 1, 2)
    rows: list[dict[str, object]] = []
    for symbol in FIXTURE_SYMBOLS:
        rows.append({"symbol": symbol, "date": first})
        rows.append({"symbol": symbol, "date": first + timedelta(days=1)})
    return pl.DataFrame(rows)


@pytest.fixture
def stub_engine(fixture_panel: pl.DataFrame) -> StubBacktestEngine:
    return StubBacktestEngine(fixture_panel)


@pytest.fixture
def stub_universe_resolver(fixture_membership: pl.DataFrame) -> StubUniverseResolver:
    return StubUniverseResolver(fixture_membership)


@pytest.fixture
def research_repository(tmp_path: Path) -> ResearchRepository:
    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository


@pytest.fixture
def research_registry(research_repository: ResearchRepository) -> FactorRegistry:
    return FactorRegistry(research_repository)
