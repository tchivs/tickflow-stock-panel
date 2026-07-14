"""Test-only offline provider backed by the Phase 1 read-only fixture bundle."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

from app.contracts.market_data import (
    AdvancedFixtureReadiness,
    FixtureBundle,
    FixtureContractError,
    preflight_advanced_host_fixture,
)
from app.data_providers.base import AssetType, ProviderCapabilities


class FixtureProvider:
    """Loads deterministic market records without constructing a live-provider client."""

    name = "fixture"
    capabilities = ProviderCapabilities(
        instruments=True,
        daily=True,
        adj_factor=True,
        financial=True,
    )

    def __init__(self, fixture_dir: Path) -> None:
        self._bundle = FixtureBundle.load(fixture_dir)

    @property
    def bundle(self) -> FixtureBundle:
        return self._bundle

    def preflight_advanced_host(self, readiness: AdvancedFixtureReadiness) -> None:
        """Validate loaded fixture semantics without exposing a writable provider path."""
        preflight_advanced_host_fixture(self._bundle, readiness)

    def get_instruments(self, asset_type: AssetType) -> pl.DataFrame:  # noqa: ARG002
        return self._bundle.instruments_frame()

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,  # noqa: ARG002
    ) -> pl.DataFrame:
        frame = self._bundle.daily_frame()
        if symbols:
            frame = frame.filter(pl.col("symbol").is_in(symbols))
        if start_time is not None:
            frame = frame.filter(pl.col("date") >= start_time.date())
        if end_time is not None:
            frame = frame.filter(pl.col("date") <= end_time.date())
        return frame
    def get_index_daily(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> pl.DataFrame:
        frame = self._bundle.index_daily_frame()
        if symbols:
            frame = frame.filter(pl.col("symbol").is_in(symbols))
        if start_time is not None:
            frame = frame.filter(pl.col("date") >= start_time.date())
        if end_time is not None:
            frame = frame.filter(pl.col("date") <= end_time.date())
        return frame

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,  # noqa: ARG002
    ) -> pl.DataFrame:
        frame = self._bundle.adjustment_factors_frame()
        if symbols:
            frame = frame.filter(pl.col("symbol").is_in(symbols))
        if start_time is not None:
            frame = frame.filter(pl.col("trade_date") >= start_time.date())
        if end_time is not None:
            frame = frame.filter(pl.col("trade_date") <= end_time.date())
        return frame

    def get_financials(self) -> pl.DataFrame:
        return self._bundle.financials_frame()

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
        freq: str = "1m",  # noqa: ARG002
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()


__all__ = ["FixtureContractError", "FixtureProvider"]
