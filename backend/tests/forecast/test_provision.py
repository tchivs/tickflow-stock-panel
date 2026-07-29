"""Governed Forecast calendar provisioning contracts."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest


def test_cfets_2027_preset_sessions_exclude_published_closures() -> None:
    from app.forecast.provision import _cfets_2027_sessions

    sessions = set(_cfets_2027_sessions())
    assert len(sessions) == 243
    assert min(sessions) == date(2027, 1, 4)
    assert max(sessions) == date(2027, 12, 31)
    assert date(2027, 2, 4) in sessions
    assert date(2027, 2, 5) not in sessions
    assert date(2027, 2, 12) not in sessions
    assert date(2027, 2, 15) in sessions
    for closure in (
        date(2027, 4, 5),
        date(2027, 5, 3),
        date(2027, 6, 9),
        date(2027, 9, 15),
        date(2027, 10, 1),
        date(2027, 10, 7),
    ):
        assert closure not in sessions


def test_written_calendar_supports_cross_year_forecast(tmp_path) -> None:
    pytest.importorskip("exchange_calendars")
    from app.forecast.calendar import GovernedTradingCalendar
    from app.forecast.provision import _write_calendar

    _write_calendar(tmp_path)
    frame = pl.read_parquet(tmp_path / "cn_a_sessions.parquet")
    assert frame["trade_date"].max() == date(2027, 12, 31)
    revision = frame["calendar_revision"].unique().to_list()
    assert len(revision) == 1
    assert revision[0].startswith("xshg-cfets-preset-2027-")

    calendar = GovernedTradingCalendar(frame)
    sessions = calendar.future_sessions(
        calendar_id="cn-a-v1", after_session_id="CNA-20261230", count=5
    )
    assert [item.session_id for item in sessions] == [
        "CNA-20261231",
        "CNA-20270104",
        "CNA-20270105",
        "CNA-20270106",
        "CNA-20270107",
    ]
