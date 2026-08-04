"""Lock the 09:30 timestamp convention for minute-K (DATA-01).

Regression suite over the provider timestamp convention:
  * ``_minute_ts`` anchors start-of-day to 09:30 (never 00:00 or the 9:15-9:25
    auction window) and end-of-day to 23:59:59.
  * ``_bucket_minutes`` never buckets a pre-09:30 bar into the morning session;
    the first morning bucket anchors at 09:30, the 11:30 bar stays in the final
    morning bucket (index M-1), and the afternoon session starts at 13:00.
  * Honesty guard: a frame whose earliest bar is 09:30:00 produces bucketed
    timestamps that never resolve below 09:30 — a pre-open bar structurally
    cannot be labeled session/auction data (ASVS L1 T-16-01).
"""
from __future__ import annotations

from datetime import datetime

import polars as pl

from app.data_providers.free_stockdb_provider import _bucket_minutes, _minute_ts


def _minute_frame(bars: list[tuple[str, datetime]]) -> pl.DataFrame:
    rows = [
        {
            "symbol": symbol,
            "datetime": dt,
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "volume": 100.0,
            "amount": 1050.0,
        }
        for symbol, dt in bars
    ]
    return pl.DataFrame(rows)


def test_minute_ts_anchors_start_of_day_to_0930():
    """Midnight start is anchored to 09:30, never 00:00 or 09:15."""
    assert _minute_ts(datetime(2026, 8, 4, 0, 0, 0), end="start") == "20260804093000"
    assert _minute_ts(datetime(2026, 8, 4, 23, 59, 59), end="end") == "20260804235959"
    assert _minute_ts(None, end="start") == "00000000000000"
    assert _minute_ts(None, end="end") == "99999999999999"


def test_bucket_minutes_never_buckets_pre_0930_bar_into_morning_session():
    """09:25/09:29 bars are dropped; morning anchors at 09:30, 11:30 stays in the
    final morning bucket, and the afternoon session starts at 13:00."""
    bars = [
        ("000001.SZ", datetime(2026, 8, 4, 9, 25)),   # pre-open — must not bucket
        ("000001.SZ", datetime(2026, 8, 4, 9, 29)),   # pre-open — must not bucket
        ("000001.SZ", datetime(2026, 8, 4, 9, 30)),   # first morning bucket anchor
        ("000001.SZ", datetime(2026, 8, 4, 9, 31)),   # merges into 09:30 bucket
        ("000001.SZ", datetime(2026, 8, 4, 11, 30)),  # final morning minute -> bucket M-1
        ("000001.SZ", datetime(2026, 8, 4, 13, 0)),   # afternoon start
        ("000001.SZ", datetime(2026, 8, 4, 13, 1)),   # merges into 13:00 bucket
    ]
    bucketed = _bucket_minutes(_minute_frame(bars), bucket_min=5, freq="5m")
    assert not bucketed.is_empty()

    # Exactly three session buckets: 09:30 morning anchor, 11:30 final morning,
    # 13:00 afternoon start. The pre-open 09:25/09:29 bars never appear.
    assert bucketed["datetime"].to_list() == [
        datetime(2026, 8, 4, 9, 30),
        datetime(2026, 8, 4, 11, 30),
        datetime(2026, 8, 4, 13, 0),
    ]

    # The 09:30-anchored bucket absorbed 09:31 (volume 200); the 11:30 bar stayed
    # in its own final-morning bucket (volume 100); the afternoon bucket absorbed
    # 13:01 (volume 200) — proving 11:30 never spilled into an afternoon bucket.
    assert bucketed["volume"].to_list() == [200.0, 100.0, 200.0]

    # No bucketed row is earlier than 09:30 and no lunch-gap row exists.
    wall_min = bucketed["datetime"].dt.hour().cast(pl.Int64) * 60 + bucketed["datetime"].dt.minute()
    assert (wall_min >= 9 * 60 + 30).all()
    assert not ((wall_min > 11 * 60 + 30) & (wall_min < 13 * 60)).any()


def test_bucket_minutes_honesty_guard_never_labels_pre_open_as_session():
    """A frame whose earliest bar is 09:30:00 never resolves below 09:30."""
    bars = [
        ("000001.SZ", datetime(2026, 8, 4, 9, 30)),
        ("000001.SZ", datetime(2026, 8, 4, 9, 31)),
        ("000001.SZ", datetime(2026, 8, 4, 9, 32)),
        ("000001.SZ", datetime(2026, 8, 4, 9, 33)),
        ("000001.SZ", datetime(2026, 8, 4, 9, 34)),
    ]
    bucketed = _bucket_minutes(_minute_frame(bars), bucket_min=5, freq="5m")
    assert not bucketed.is_empty()
    wall_min = bucketed["datetime"].dt.hour().cast(pl.Int64) * 60 + bucketed["datetime"].dt.minute()
    assert (wall_min >= 9 * 60 + 30).all()
    assert bucketed["datetime"].min() == datetime(2026, 8, 4, 9, 30)
