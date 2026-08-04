"""Hermetic integration test: minute-K sync enable path (DATA-01).

Proves the DATA-01 acceptance path without any network:
  enable -> 1m bars land in ``data/kline_minute`` with canonical columns and
  09:30+ timestamps -> the daily-K lake (partition sets + per-file sha256) is
  byte-identical before and after.

Also guards the pipeline capability gate (a stale capability can only skip,
never fabricate data).

All production imports happen inside test functions so the module never imports
DuckDB-backed singletons at collection time (repo convention).
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

import polars as pl


def _synthetic_minute_frame() -> pl.DataFrame:
    """Synthetic canonical 1m feed: 2 symbols, 09:30:00..09:34:00 on 2026-08-04.

    Columns are exactly ``CANONICAL_MINUTE_COLS``; ``datetime`` is naive
    Asia/Shanghai local (the existing convention).
    """
    rows: list[dict] = []
    base = datetime(2026, 8, 4, 9, 30)
    for symbol in ("000001.SZ", "600000.SH"):
        for i in range(5):
            rows.append({
                "symbol": symbol,
                "datetime": base + timedelta(minutes=i),
                "open": 10.0 + i,
                "high": 11.0 + i,
                "low": 9.5 + i,
                "close": 10.5 + i,
                "volume": 100.0,
                "amount": 1050.0,
            })
    return pl.DataFrame(rows).with_columns(
        pl.col("datetime").cast(pl.Datetime("us")),
    )


def _seed_daily_lake(repo) -> None:
    """Seed a measurable daily lake through the repository's own write helpers.

    kline_daily: date=2026-08-03 + date=2026-08-04 partitions.
    kline_daily_enriched: date=2026-08-04 partition.
    """
    daily = pl.DataFrame({
        "symbol": ["000001.SZ", "600000.SH"],
        "date": [date(2026, 8, 3), date(2026, 8, 3)],
        "open": [10.0, 20.0],
        "high": [11.0, 21.0],
        "low": [9.5, 19.5],
        "close": [10.5, 20.5],
        "volume": [1000.0, 2000.0],
        "amount": [10500.0, 41000.0],
    })
    daily_0804 = daily.with_columns(pl.lit(date(2026, 8, 4)).alias("date"))
    repo.append_daily(pl.concat([daily, daily_0804]))

    enriched = pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [date(2026, 8, 4)],
        "open": [10.5],
        "high": [11.0],
        "low": [10.0],
        "close": [10.8],
        "volume": [1200.0],
        "amount": [12960.0],
        "raw_close": [10.8],
        "raw_high": [11.0],
        "raw_low": [10.0],
        "turnover_rate": [0.01],
        "consecutive_limit_ups": [0],
        "consecutive_limit_downs": [0],
        "quote_ts": [1754300000000],
    })
    repo.append_enriched(enriched)


def _daily_lake_snapshot(data_dir) -> tuple[dict, dict]:
    """Snapshot the governed daily-K lake: partition dirs + per-file sha256."""
    tables = ("kline_daily", "kline_daily_enriched")
    parts: dict[str, list[str]] = {}
    digests: dict[str, str] = {}
    for table in tables:
        base = data_dir / table
        parts[table] = (
            sorted(d.name for d in base.glob("date=*") if d.is_dir())
            if base.exists()
            else []
        )
        for f in sorted(base.rglob("*.parquet")):
            rel = f.relative_to(data_dir).as_posix()
            digests[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return parts, digests


def test_minute_sync_enable_persists_and_leaves_daily_lake_unchanged(tmp_path, monkeypatch):
    """Enable -> 1m bars in kline_minute (09:30 anchor) -> daily lake byte-identical."""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    repo = KlineRepository(store)
    try:
        _seed_daily_lake(repo)
        before_parts, before_digests = _daily_lake_snapshot(data_dir)

        from app.services import preferences
        preferences.save({"minute_sync_enabled": True, "minute_sync_days": 1})
        assert preferences.get_minute_sync_enabled() is True
        assert preferences.get_minute_sync_days() == 1

        from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
        capset = CapabilitySet({Cap.KLINE_MINUTE_BATCH: CapabilityLimits(batch=100, rpm=30)})

        from app.services import kline_sync
        assert kline_sync.can_sync_minute(capset) is True
        monkeypatch.setattr(kline_sync, "sync_minute_batch", lambda *a, **k: _synthetic_minute_frame())

        written = kline_sync.sync_and_persist_minute(
            ["000001.SZ", "600000.SH"], repo, capset, days=1,
        )
        assert written > 0
        assert written == 10  # 5 bars x 2 symbols

        # 1m bars land with canonical columns + Datetime('us') + 09:30 anchor
        out = data_dir / "kline_minute" / "date=2026-08-04" / "part.parquet"
        assert out.exists()
        df = pl.read_parquet(out)
        assert df.columns == kline_sync.CANONICAL_MINUTE_COLS
        assert df.schema["datetime"] == pl.Datetime("us")
        assert df["datetime"].min() == datetime(2026, 8, 4, 9, 30)
        wall_min = df["datetime"].dt.hour().cast(pl.Int64) * 60 + df["datetime"].dt.minute()

        # Daily-K lake is byte-identical
        after_parts, after_digests = _daily_lake_snapshot(data_dir)
        assert after_parts == before_parts
        assert after_digests == before_digests
    finally:
        store.db.close()


def test_minute_sync_gate_skips_when_disabled_or_capability_missing(tmp_path, monkeypatch):
    """The enable flag is the real gate: disabled or no capability -> skip, 0 rows."""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    repo = KlineRepository(store)
    try:
        from app.tickflow.capabilities import CapabilitySet
        from app.services import kline_sync, preferences

        # No capability + no custom minute provider -> cannot sync minute
        capset = CapabilitySet()
        assert kline_sync.can_sync_minute(capset) is False

        # Disabled preference -> the run_now-equivalent gate appends sync_minute
        # to skipped and writes 0 minute rows.
        preferences.save({"minute_sync_enabled": False})
        assert preferences.get_minute_sync_enabled() is False

        skipped: list[str] = []
        written_minute = 0
        minute_on = preferences.get_minute_sync_enabled()
        if minute_on and kline_sync.can_sync_minute(capset):
            written_minute = kline_sync.sync_and_persist_minute(
                ["000001.SZ", "600000.SH"], repo, capset, days=1,
            )
        else:
            skipped.append("sync_minute")

        assert skipped == ["sync_minute"]
        assert written_minute == 0
        assert not list((data_dir / "kline_minute").rglob("*.parquet"))
    finally:
        store.db.close()
