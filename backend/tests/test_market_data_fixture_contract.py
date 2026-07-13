"""Focused validation tests for Phase 1 market-data fixture bundles."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


_MISSING = object()


def _daily_bar(*, symbol: str = "600000.SH") -> dict[str, object]:
    return {
        "symbol": symbol,
        "date": "2024-01-02",
        "open": 7.10,
        "high": 7.30,
        "low": 7.05,
        "close": 7.25,
        "volume": 1000.0,
        "amount": 7250.0,
        "quote_ts": 1704180600000,
    }


def _write_fixture_bundle(fixture_dir: Path, *, index_daily: object = _MISSING) -> None:
    fixture_dir.mkdir()
    (fixture_dir / "instruments.json").write_text(
        json.dumps(
            {
                "instruments": [
                    {
                        "symbol": "600000.SH",
                        "name": "浦发银行",
                        "code": "600000",
                        "exchange": "SH",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    market_data: dict[str, object] = {
        "daily": [_daily_bar()],
        "adjustment_factors": [
            {"symbol": "600000.SH", "trade_date": "2024-01-02", "adj_factor": 1.0}
        ],
        "financials": [{"symbol": "600000.SH", "report_date": "2023-09-30", "roe": 0.09}],
    }
    if index_daily is not _MISSING:
        market_data["index_daily"] = index_daily
    (fixture_dir / "market-data.json").write_text(
        json.dumps(market_data, ensure_ascii=False), encoding="utf-8"
    )
    for fixture_file in fixture_dir.iterdir():
        fixture_file.chmod(0o444)
    fixture_dir.chmod(0o555)


@pytest.mark.parametrize(
    "index_daily",
    [_MISSING, []],
    ids=["missing-index-daily", "empty-index-daily"],
)
def test_plan21_host_fixture_requires_non_empty_benchmark_index_daily(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, index_daily: object
) -> None:
    from app.contracts.market_data import FixtureBundle, FixtureContractError

    fixture_dir = tmp_path / "fixtures"
    _write_fixture_bundle(fixture_dir, index_daily=index_daily)
    monkeypatch.setenv("ADVANCED_HOST_FIXTURE", str(tmp_path / "advanced-host-fixture.json"))

    with pytest.raises(FixtureContractError, match="non-empty benchmark index_daily"):
        FixtureBundle.load(fixture_dir)


def test_plan21_host_with_missing_benchmark_fails_during_fastapi_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.contracts.market_data import FixtureContractError
    from app.services import auth as auth_service

    fixture_dir = tmp_path / "fixtures"
    _write_fixture_bundle(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("ADVANCED_HOST_FIXTURE", str(tmp_path / "advanced-host-fixture.json"))
    monkeypatch.setattr(settings, "data_dir", tmp_path / "governed-data")
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    from app.main import app

    with pytest.raises(FixtureContractError, match="non-empty benchmark index_daily"):
        with TestClient(app):
            pass


def test_non_host_fixture_allows_missing_benchmark_index_daily(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.contracts.market_data import FixtureBundle

    fixture_dir = tmp_path / "fixtures"
    _write_fixture_bundle(fixture_dir)
    monkeypatch.delenv("ADVANCED_HOST_FIXTURE", raising=False)

    bundle = FixtureBundle.load(fixture_dir)

    assert bundle.index_daily == []
