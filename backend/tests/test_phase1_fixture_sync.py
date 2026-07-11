"""Offline contract for governed fixture synchronization (CORE-01)."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import polars as pl


def _write_fixture_bundle(fixtures_dir: Path) -> None:
    fixtures_dir.mkdir()
    (fixtures_dir / "governed-market-data.json").write_text(
        json.dumps(
            {
                "instruments": [
                    {
                        "symbol": "600000.SH",
                        "name": "浦发银行",
                        "code": "600000",
                        "exchange": "SH",
                    }
                ],
                "daily": [
                    {
                        "symbol": "600000.SH",
                        "date": "2024-01-02",
                        "open": 7.10,
                        "high": 7.30,
                        "low": 7.05,
                        "close": 7.25,
                        "volume": 1000.0,
                        "amount": 7250.0,
                        "quote_ts": 1704180600000,
                    }
                ],
                "adjustment_factors": [
                    {"symbol": "600000.SH", "trade_date": "2024-01-02", "adj_factor": 1.0}
                ],
                "financials": [
                    {"symbol": "600000.SH", "report_date": "2023-09-30", "roe": 0.09}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _deny_network(*_args, **_kwargs) -> None:
    raise AssertionError("D-13 fixture synchronization must not open a network connection")


def test_d13_fixture_mode_is_offline_and_uses_governed_lake_boundary(
    tmp_path, monkeypatch
):
    """PHASE1_FIXTURE_MODE exercises the normal Parquet, DuckDB, and Polars path locally."""
    fixture_dir = tmp_path / "fixtures"
    lake_dir = tmp_path / "isolated-governed-lake"
    _write_fixture_bundle(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.delenv("TICKFLOW_API_KEY", raising=False)
    monkeypatch.setattr(socket.socket, "connect", _deny_network)

    from app.jobs.daily_pipeline import run_phase1_fixture_sync

    report = run_phase1_fixture_sync(data_dir=lake_dir)

    assert report["provider"] == "fixture"
    assert {
        "sync_instruments",
        "sync_daily",
        "sync_adj",
        "sync_financials",
        "compute_enriched",
        "refresh_views",
    }.issubset(report["stages"])
    assert list((lake_dir / "instruments").rglob("*.parquet"))
    assert list((lake_dir / "kline_daily").rglob("*.parquet"))
    assert list((lake_dir / "adj_factor").rglob("*.parquet"))
    assert list((lake_dir / "financials").rglob("*.parquet"))
    enriched_parts = list((lake_dir / "kline_daily_enriched").rglob("*.parquet"))
    assert enriched_parts

    from app.tickflow.repository import DataStore

    store = DataStore(lake_dir)
    try:
        assert store.db.execute("SELECT count(*) FROM instruments").fetchone()[0] == 1
        assert store.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 1
    finally:
        store.db.close()

    enriched = pl.read_parquet(enriched_parts[0])
    assert enriched.select("symbol").item() == "600000.SH"
    assert {"raw_close", "turnover_rate"}.issubset(enriched.columns)


def test_d13_fixture_mode_requires_an_explicit_test_only_environment_switch(tmp_path, monkeypatch):
    """The governed-data boundary must not activate fixture data in ordinary runtime mode."""
    fixture_dir = tmp_path / "fixtures"
    _write_fixture_bundle(fixture_dir)
    monkeypatch.delenv("PHASE1_FIXTURE_MODE", raising=False)
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))

    from app.jobs.daily_pipeline import fixture_provider_enabled

    assert fixture_provider_enabled() is False
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    assert fixture_provider_enabled() is True
