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
    advanced_fixture = tmp_path / "advanced-host-fixture.json"
    _write_advanced_host_config(advanced_fixture)
    monkeypatch.setenv("ADVANCED_HOST_FIXTURE", str(advanced_fixture))
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


def _advanced_readiness() -> dict[str, object]:
    return {
        "benchmark_symbol": "000300.SH",
        "symbols": ["600000.SH"],
        "required_coverage": {"start": "2024-01-02", "end": "2024-09-30"},
        "evaluation_windows": [20, 60, 120],
        "strategy": {"id": "bullish_alignment", "warmup_trading_days": 60},
        "aggregate_coverage": {"start": "2024-01-02", "end": "2024-09-30"},
        "in_sample": {"start": "2024-01-02", "end": "2024-05-31"},
        "out_of_sample": {"start": "2024-06-03", "end": "2024-09-30"},
    }


def _write_advanced_host_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "policy": "advanced_policy_v1",
                "advanced_subjects": ["600000.SH"],
                "fixture_readiness": _advanced_readiness(),
            }
        ),
        encoding="utf-8",
    )


def _advanced_bars(*, symbol: str, eligible: bool = True) -> list[dict[str, object]]:
    from datetime import date, datetime, time, timedelta, timezone

    bars: list[dict[str, object]] = []
    cursor = date(2024, 1, 2)
    ordinal = 0
    while cursor <= date(2024, 9, 30):
        if cursor.weekday() < 5:
            close = 10.0 + ordinal * 0.1 if eligible else 100.0 - ordinal * 0.1
            bars.append(
                {
                    "symbol": symbol,
                    "date": cursor.isoformat(),
                    "open": close - 0.05,
                    "high": close + 0.15,
                    "low": close - 0.15,
                    "close": close,
                    "volume": 10_000.0,
                    "amount": close * 10_000.0,
                    "quote_ts": int(
                        datetime.combine(cursor, time(1, 30), timezone.utc).timestamp() * 1000
                    ),
                }
            )
            ordinal += 1
        cursor += timedelta(days=1)
    return bars


def _write_advanced_fixture(
    fixture_dir: Path,
    *,
    daily: list[dict[str, object]] | None = None,
    index_daily: list[dict[str, object]] | None = None,
    malformed_schema: bool = False,
) -> None:
    daily = _advanced_bars(symbol="600000.SH") if daily is None else daily
    index_daily = (
        [{**bar, "symbol": "000300.SH"} for bar in daily]
        if index_daily is None
        else index_daily
    )
    fixture_dir.mkdir()
    (fixture_dir / "instruments.json").write_text(
        json.dumps(
            {"instruments": [{"symbol": "600000.SH", "name": "浦发银行", "code": "600000", "exchange": "SH"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if malformed_schema:
        del daily[0]["close"]
    (fixture_dir / "market-data.json").write_text(
        json.dumps(
            {
                "daily": daily,
                "index_daily": index_daily,
                "adjustment_factors": [
                    {"symbol": "600000.SH", "trade_date": bar["date"], "adj_factor": 1.0}
                    for bar in daily
                    if "date" in bar
                ],
                "financials": [{"symbol": "600000.SH", "report_date": "2023-09-30", "roe": 0.09}],
            },
            ensure_ascii=False,
            allow_nan=True,
        ),
        encoding="utf-8",
    )
    for fixture_file in fixture_dir.iterdir():
        fixture_file.chmod(0o444)
    fixture_dir.chmod(0o555)


@pytest.mark.parametrize(
    ("case", "mutate"),
    [
        ("wrong-benchmark", lambda daily, index: (daily, [{**bar, "symbol": "000905.SH"} for bar in index])),
        ("missing-coverage", lambda daily, index: (daily[1:], index[1:])),
        ("duplicate", lambda daily, index: (daily + [daily[-1].copy()], index)),
        ("non-chronological", lambda daily, index: ([daily[1], daily[0], *daily[2:]], index)),
        ("nan", lambda daily, index: ([{**daily[0], "close": float("nan")}, *daily[1:]], index)),
        ("infinite", lambda daily, index: ([{**daily[0], "high": float("inf")}, *daily[1:]], index)),
        ("non-positive", lambda daily, index: ([{**daily[0], "volume": 0.0}, *daily[1:]], index)),
        ("invalid-ohlc", lambda daily, index: ([{**daily[0], "low": daily[0]["high"]}], index)),
        ("bad-timestamp", lambda daily, index: ([{**daily[0], "quote_ts": 0}, *daily[1:]], index)),
        ("out-of-session", lambda daily, index: ([{**daily[0], "quote_ts": 1704153600000}, *daily[1:]], index)),
    ],
)
def test_advanced_host_rejected_fixture_never_creates_governed_lake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    mutate,
) -> None:
    from app.contracts.market_data import AdvancedFixtureReadiness, FixtureContractError
    from app.jobs.daily_pipeline import run_phase1_fixture_sync

    daily = _advanced_bars(symbol="600000.SH")
    index_daily = [{**bar, "symbol": "000300.SH"} for bar in daily]
    invalid_daily, invalid_index = mutate(daily, index_daily)
    fixture_dir = tmp_path / case
    lake_dir = tmp_path / "governed-lake"
    _write_advanced_fixture(fixture_dir, daily=invalid_daily, index_daily=invalid_index)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("ADVANCED_HOST_FIXTURE", str(tmp_path / "advanced-host-fixture.json"))

    with pytest.raises(FixtureContractError):
        run_phase1_fixture_sync(
            lake_dir, readiness=AdvancedFixtureReadiness.model_validate_json(json.dumps(_advanced_readiness()))
        )

    assert not lake_dir.exists()


@pytest.mark.parametrize("malformed_schema", [True, False], ids=["schema", "no-eligible-signal"])
def test_advanced_host_schema_and_signal_fail_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, malformed_schema: bool
) -> None:
    from app.contracts.market_data import AdvancedFixtureReadiness, FixtureContractError
    from app.jobs.daily_pipeline import run_phase1_fixture_sync

    fixture_dir = tmp_path / "fixture"
    lake_dir = tmp_path / "governed-lake"
    _write_advanced_fixture(
        fixture_dir,
        daily=_advanced_bars(symbol="600000.SH", eligible=malformed_schema),
        malformed_schema=malformed_schema,
    )
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("ADVANCED_HOST_FIXTURE", str(tmp_path / "advanced-host-fixture.json"))

    with pytest.raises(FixtureContractError):
        run_phase1_fixture_sync(
            lake_dir, readiness=AdvancedFixtureReadiness.model_validate_json(json.dumps(_advanced_readiness()))
        )

    assert not lake_dir.exists()


def test_advanced_host_ready_fixture_reaches_existing_governed_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.contracts.market_data import AdvancedFixtureReadiness
    from app.jobs.daily_pipeline import run_phase1_fixture_sync

    fixture_dir = tmp_path / "fixture"
    lake_dir = tmp_path / "governed-lake"
    _write_advanced_fixture(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("ADVANCED_HOST_FIXTURE", str(tmp_path / "advanced-host-fixture.json"))

    report = run_phase1_fixture_sync(
        lake_dir, readiness=AdvancedFixtureReadiness.model_validate_json(json.dumps(_advanced_readiness()))
    )

    assert report["provider"] == "fixture"
    assert list((lake_dir / "kline_daily").rglob("*.parquet"))
    assert list((lake_dir / "kline_index_daily").rglob("*.parquet"))

