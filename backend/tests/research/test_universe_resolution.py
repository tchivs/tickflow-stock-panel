"""RED scaffold for the Phase 10 PIT universe resolver (PIT contract).

These tests lock the universe-resolution contracts and are expected to FAIL until
10-04 creates ``app/research/universe.py``.  Contracts covered:

1. listed-after-start excluded per date — a symbol with a post-start listing date is
   absent from the per-date set before its listing and present after;
2. delist event closes membership as-of;
3. fingerprint changes when membership changes;
4. ``resolve_universe`` returns ``(symbols, membership_fingerprint)`` with the
   fingerprint over the sorted symbol tuple;
5. determinism — two calls with identical membership state return identical
   fingerprints.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.research.repository import ResearchRepository


@pytest.fixture
def universe_module():
    """Deferred import: the module does not exist until 10-04."""
    from app.research.universe import resolve_universe, resolve_universe_daily  # noqa: F401

    return {"resolve_universe": resolve_universe, "resolve_universe_daily": resolve_universe_daily}


def _seed_membership(repo: ResearchRepository, *, rows: list[dict]) -> None:
    """Append membership rows through the repository (INSERT-only)."""
    for row in rows:
        repo.insert_universe_membership(
            universe_name=row["universe_name"],
            symbol=row["symbol"],
            asset_type=row.get("asset_type", "stock"),
            effective_date=row["effective_date"],
            state=row["state"],
            source=row.get("source", "instruments-sync"),
            provenance_json=row.get("provenance_json", {}),
        )


def test_listed_after_start_excluded_per_date(
    research_repository: ResearchRepository,
    universe_module,
) -> None:
    _seed_membership(
        research_repository,
        rows=[
            {"universe_name": "cn-a-share", "symbol": "600000.SH", "effective_date": "2025-01-01", "state": "listed"},
            {"universe_name": "cn-a-share", "symbol": "600001.SH", "effective_date": "2025-06-01", "state": "listed"},
        ],
    )
    symbols, fingerprint = universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 3, 1)
    )
    assert symbols == frozenset({"600000.SH"})
    assert fingerprint == universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 3, 1)
    )[1]


def test_delist_event_closes_membership_as_of(
    research_repository: ResearchRepository,
    universe_module,
) -> None:
    _seed_membership(
        research_repository,
        rows=[
            {"universe_name": "cn-a-share", "symbol": "600000.SH", "effective_date": "2025-01-01", "state": "listed"},
            {"universe_name": "cn-a-share", "symbol": "600000.SH", "effective_date": "2025-06-01", "state": "delisted"},
        ],
    )
    before = universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 5, 1)
    )[0]
    after = universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 7, 1)
    )[0]
    assert "600000.SH" in before
    assert "600000.SH" not in after


def test_fingerprint_changes_when_membership_changes(
    research_repository: ResearchRepository,
    universe_module,
) -> None:
    _seed_membership(
        research_repository,
        rows=[
            {"universe_name": "cn-a-share", "symbol": "600000.SH", "effective_date": "2025-01-01", "state": "listed"},
        ],
    )
    before = universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 3, 1)
    )[1]
    _seed_membership(
        research_repository,
        rows=[
            {"universe_name": "cn-a-share", "symbol": "600001.SH", "effective_date": "2025-02-01", "state": "listed"},
        ],
    )
    after = universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 3, 1)
    )[1]
    assert before != after


def test_daily_resolution_returns_symbol_date_frame(
    research_repository: ResearchRepository,
    universe_module,
) -> None:
    _seed_membership(
        research_repository,
        rows=[
            {"universe_name": "cn-a-share", "symbol": "600000.SH", "effective_date": "2025-01-01", "state": "listed"},
        ],
    )
    daily = universe_module["resolve_universe_daily"](
        research_repository,
        universe_name="cn-a-share",
        start=date(2025, 2, 1),
        end=date(2025, 2, 28),
    )
    assert daily.columns == ["symbol", "date"]
    assert daily["symbol"].unique().to_list() == ["600000.SH"]
