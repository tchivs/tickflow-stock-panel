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
    from app.research.universe import resolve_universe, resolve_universe_daily

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


def test_daily_resolution_closes_membership_after_delist(
    research_repository: ResearchRepository,
    universe_module,
) -> None:
    """A delist event closes the per-date frame on and after its effective date."""
    _seed_membership(
        research_repository,
        rows=[
            {"universe_name": "cn-a-share", "symbol": "600000.SH", "effective_date": "2025-01-01", "state": "listed"},
            {"universe_name": "cn-a-share", "symbol": "600000.SH", "effective_date": "2025-02-10", "state": "delisted"},
        ],
    )
    daily = universe_module["resolve_universe_daily"](
        research_repository,
        universe_name="cn-a-share",
        start=date(2025, 2, 1),
        end=date(2025, 2, 28),
    )
    dates = daily.filter(pl.col("symbol") == "600000.SH")["date"].to_list()
    assert date(2025, 2, 9) in dates
    assert date(2025, 2, 10) not in dates


def test_seed_membership_uses_listing_date_with_first_bar_fallback(
    research_repository: ResearchRepository,
    universe_module,
) -> None:
    """Seed: listing_date String cast normalization + first-bar fallback (OQ5)."""
    from app.research.universe import seed_membership

    instruments = pl.DataFrame(
        {
            "symbol": ["600000.SH", "600001.SH", "600002.SH"],
            "listing_date": ["2025-01-15", None, "not-a-date"],
        }
    )
    enriched = pl.DataFrame(
        {
            "symbol": ["600001.SH", "600001.SH", "600002.SH"],
            "date": [date(2025, 1, 20), date(2025, 1, 25), date(2025, 1, 5)],
        }
    )
    inserted = seed_membership(
        research_repository, instruments, enriched, universe_name="cn-a-share"
    )
    assert inserted == 3

    events = research_repository.list_universe_memberships(universe_name="cn-a-share")
    by_symbol = {event["symbol"]: event for event in events}
    assert by_symbol["600000.SH"]["effective_date"] == "2025-01-15"  # listing_date wins
    assert by_symbol["600001.SH"]["effective_date"] == "2025-01-20"  # first-bar fallback
    assert by_symbol["600002.SH"]["effective_date"] == "2025-01-05"  # invalid listing -> first bar
    assert all(event["state"] == "listed" for event in events)
    assert all(event["source"] == "instruments-sync" for event in events)


def test_resolve_universe_deterministic_fingerprint(
    research_repository: ResearchRepository,
    universe_module,
) -> None:
    """Two calls with identical membership state return identical fingerprints."""
    _seed_membership(
        research_repository,
        rows=[
            {"universe_name": "cn-a-share", "symbol": "600000.SH", "effective_date": "2025-01-01", "state": "listed"},
            {"universe_name": "cn-a-share", "symbol": "600001.SH", "effective_date": "2025-02-01", "state": "listed"},
        ],
    )
    first = universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 3, 1)
    )
    second = universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 3, 1)
    )
    assert first[0] == second[0]
    assert first[1] == second[1]


def test_close_membership_appends_delisted_row_and_never_auto_delists(
    research_repository: ResearchRepository,
    universe_module,
) -> None:
    """close_membership appends a delisted row; symbols_lagging never auto-delists."""
    from app.research.universe import close_membership

    _seed_membership(
        research_repository,
        rows=[
            {"universe_name": "cn-a-share", "symbol": "600000.SH", "effective_date": "2025-01-01", "state": "listed"},
        ],
    )
    close_membership(
        research_repository,
        universe_name="cn-a-share",
        symbol="600000.SH",
        effective_date=date(2025, 6, 1),
    )
    before = universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 5, 1)
    )[0]
    after = universe_module["resolve_universe"](
        research_repository, universe_name="cn-a-share", as_of=date(2025, 7, 1)
    )[0]
    assert "600000.SH" in before
    assert "600000.SH" not in after
    # A delist is a new row, never an UPDATE: both events remain in the history.
    events = research_repository.list_universe_memberships(universe_name="cn-a-share")
    assert [event["state"] for event in events] == ["listed", "delisted"]
