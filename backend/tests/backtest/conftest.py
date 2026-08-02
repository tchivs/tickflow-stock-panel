"""Shared fixtures for the Phase 13 walk-forward test suite (WFWD-01/02/03).

Wave 0 provides the measured-calendar fold-plan fixtures, the stub
chain/resolver/service doubles, and the repository fixture shared by
test_walkforward.py / test_ensemble.py / test_optimizer_run.py.  The
``wf_fixture_plan`` fixture lazily imports ``build_plan`` from
``app.backtest.walkforward`` (landed by 13-01), so it stays RED until the
tracer module exists — the exact Wave 0 scaffold contract.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest

from app.research.repository import ResearchRepository

FIXTURE_SYMBOLS = ("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ")

_CAL_START = date(2025, 7, 29)
_CAL_END = date(2026, 7, 30)
# 14-trading-day CNY hole inside "Feb 2026" so calendar snapping is testable:
# 2026-02-10..2026-02-27 are weekdays removed from the measured calendar.
_CNY_HOLE_START = date(2026, 2, 10)
_CNY_HOLE_END = date(2026, 2, 27)


def _weekdays(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _membership_fingerprint(membership: pl.DataFrame) -> str:
    """sha256 over the canonical per-date membership frame ``[symbol, date]``."""
    ordered = membership.select(["symbol", "date"]).sort(["symbol", "date"])
    payload = "|".join(f"{row['symbol']}:{row['date']}" for row in ordered.iter_rows(named=True))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Measured-calendar fixtures (fold boundaries snap to these, never timedelta)
# ---------------------------------------------------------------------------


@pytest.fixture
def measured_calendar() -> list[date]:
    """Deterministic ~244-trading-day calendar with a 14-trading-day Feb CNY hole.

    Weekday dates 2025-07-29 → 2026-07-30 with the 2026-02 CNY closure removed,
    so a ``timedelta``-based 20-day gap would silently bleed into the hole and
    produce test segments shorter than 20 dates — exactly the Pitfall-1 trap
    ``build_plan`` must snap against.
    """
    return [
        day
        for day in _weekdays(_CAL_START, _CAL_END)
        if not (_CNY_HOLE_START <= day <= _CNY_HOLE_END)
    ]


@pytest.fixture
def fixture_membership() -> pl.DataFrame:
    """Per-date membership covering the measured calendar for every fixture symbol."""
    rows: list[dict[str, object]] = []
    for symbol in FIXTURE_SYMBOLS:
        for day in _weekdays(_CAL_START, _CAL_END):
            if not (_CNY_HOLE_START <= day <= _CNY_HOLE_END):
                rows.append({"symbol": symbol, "date": day})
    return pl.DataFrame(rows)


@pytest.fixture
def wf_fixture_plan(measured_calendar: list[date]):
    """A ``WalkForwardPlan`` over the measured calendar (default geometry).

    RED until 13-01 lands ``app.backtest.walkforward.build_plan``; the lazy
    import keeps this conftest importable so existing backtest tests collect.
    """
    from app.backtest.walkforward import build_plan

    return build_plan(
        plan_id="wf-fixture-plan",
        universe="cn-a-share",
        asset_type="stock",
        dates=measured_calendar,
        train_size=120,
        gap_size=20,
        test_size=20,
        oos_size=40,
        horizon=5,
    )


# ---------------------------------------------------------------------------
# Stub doubles (record calls, return controlled shapes)
# ---------------------------------------------------------------------------


class StubUniverseResolver:
    """PIT resolver double bound to a per-date ``[symbol, date]`` membership frame."""

    def __init__(self, membership: pl.DataFrame) -> None:
        self.membership = membership
        self.calls: list[dict[str, Any]] = []

    def resolve_universe_daily(
        self, *, universe_name: str, start: date, end: date, asset_type: str = "stock"
    ) -> pl.DataFrame:
        del universe_name, asset_type
        self.calls.append({"start": start, "end": end})
        return self.membership.filter((pl.col("date") >= start) & (pl.col("date") <= end))


class StubSignalChain:
    """FactorSignalFrame-shaped double; fingerprint derives from resolver membership.

    ``compute()`` resolves membership through the injected resolver over the
    config window and returns a namespace carrying ``resolved_universe`` with a
    ``membership_fingerprint`` — so a membership change changes the fingerprint
    (the Pitfall-5 reproducibility contract is testable).
    """

    def __init__(self, resolver: StubUniverseResolver) -> None:
        self.resolver = resolver
        self.calls: list[dict[str, Any]] = []

    def compute(self, *, revision_id: str, config: object) -> SimpleNamespace:
        self.calls.append({"revision_id": revision_id, "config": config})
        membership = self.resolver.resolve_universe_daily(
            universe_name=config.universe,
            start=config.start,
            end=config.end,
            asset_type=config.asset_type,
        )
        fingerprint = (
            _membership_fingerprint(membership)
            if membership is not None and membership.height
            else "0" * 64
        )
        return SimpleNamespace(
            revision_id=revision_id,
            resolved_universe={
                "method": "factor_universe_membership/v1",
                "membership_fingerprint": fingerprint,
                "per_date_symbol_counts": {},
                "excluded_delisted": [],
                "pre_filter_counts": {},
            },
            frame=pl.DataFrame({"symbol": [], "date": [], "_rank": [], "_zscore": []}),
        )


class StubBacktestService:
    """StrategyBacktestService double returning controlled backtest stats."""

    def __init__(self, stats: dict[str, float] | None = None) -> None:
        self.stats = stats or {"sharpe": 1.0, "sortino": 1.5, "total_return": 0.1}
        self.calls: list[object] = []

    def run(self, config: object, progress_cb=None, cancel_event=None):  # type: ignore[no-untyped-def]
        del progress_cb, cancel_event
        self.calls.append(config)
        return SimpleNamespace(stats=self.stats, error=None)


@pytest.fixture
def stub_resolver(fixture_membership: pl.DataFrame) -> StubUniverseResolver:
    return StubUniverseResolver(fixture_membership)


@pytest.fixture
def make_stub_resolver() -> Any:
    """Factory for a resolver over an arbitrary membership frame."""
    return StubUniverseResolver


@pytest.fixture
def make_stub_chain() -> Any:
    """Factory for a stub chain bound to a given resolver."""
    return StubSignalChain


@pytest.fixture
def stub_chain(stub_resolver: StubUniverseResolver) -> StubSignalChain:
    return StubSignalChain(stub_resolver)


@pytest.fixture
def stub_backtest_service() -> StubBacktestService:
    return StubBacktestService()


@pytest.fixture
def research_repository(tmp_path: Path) -> ResearchRepository:
    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository
