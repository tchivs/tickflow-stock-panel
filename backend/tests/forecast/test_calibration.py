"""RED contracts for append-only maturity outcomes and calibration replay."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

import polars as pl
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "maturity_actuals.parquet"


class GovernedActuals:
    def __init__(self, frame: pl.DataFrame | None = None) -> None:
        self.frame = frame if frame is not None else pl.read_parquet(FIXTURE)
        self.calls = 0

    def load_actual(self, *, instrument_id: str, session_id: str, calendar_revision: str):
        self.calls += 1
        rows = self.frame.filter(
            (pl.col("instrument_id") == instrument_id)
            & (pl.col("session_id") == session_id)
            & (pl.col("calendar_revision") == calendar_revision)
        )
        return None if rows.is_empty() else rows.to_dicts()[0]


class AuthoritySpy:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("calibration acquired downstream authority")


def _repository(tmp_path: Path):
    from app.forecast.repository import ForecastRepository

    repository = ForecastRepository(tmp_path / "operational.db")
    repository.migrate()
    repository.insert_fixture_forecast(
        {
            "id": "forecast-1",
            "instrument_id": "instrument-600000",
            "origin_session_id": "CNA-20250430",
            "calendar_revision": "cn-a-calendar-2025-v1",
            "future_session_ids": [f"CNA-FUTURE-{index:02}" for index in range(1, 61)],
            "horizon": 60,
            "input_fingerprint": "a" * 64,
            "paths_checksum_sha256": "b" * 64,
            "quantiles_checksum_sha256": "c" * 64,
            "checkpoint_provenance": {
                "source_revision": "67b630e",
                "model_revision": "f4e6869",
                "tokenizer_revision": "26966d0",
            },
            "created_at": "2025-04-30T08:00:00Z",
            "quantiles": {
                "5": {"p10": 9.0, "p50": 10.0, "p90": 11.0},
                "20": {"p10": 10.0, "p50": 12.0, "p90": 14.0},
                "60": {"p10": 11.0, "p50": 14.0, "p90": 17.0},
            },
        }
    )
    return repository


def _scanner(tmp_path: Path, *, actuals: GovernedActuals | None = None):
    from app.forecast.calibration import ForecastMaturityScanner

    repository = _repository(tmp_path)
    governed = actuals or GovernedActuals()
    spies = {
        name: AuthoritySpy()
        for name in ("thesis", "strategy", "decision_plan", "monitor", "position", "broker")
    }
    scanner = ForecastMaturityScanner(
        repository=repository,
        actuals=governed,
        max_items_per_scan=8,
        metric_schema="forecast-close-calibration-v1",
        action_collaborators=spies,
    )
    return scanner, repository, governed, spies


def _immutable_projection(repository) -> str:
    record = repository.get_forecast("forecast-1")
    return json.dumps(
        {
            key: record[key]
            for key in (
                "input_fingerprint",
                "paths_checksum_sha256",
                "quantiles_checksum_sha256",
                "checkpoint_provenance",
                "created_at",
                "quantiles",
            )
        },
        sort_keys=True,
    )


def test_maturity_resolves_nth_session_from_original_frozen_calendar_identity(tmp_path):
    scanner, repository, _actuals, _spies = _scanner(tmp_path)
    outcome = scanner.evaluate(
        forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-20"
    )
    assert outcome["actual_session_id"] == "CNA-FUTURE-20"
    assert outcome["calendar_revision"] == "cn-a-calendar-2025-v1"
    assert repository.get_forecast("forecast-1")["origin_session_id"] == "CNA-20250430"


def test_not_yet_mature_horizon_appends_no_terminal_outcome(tmp_path):
    scanner, repository, actuals, _spies = _scanner(tmp_path)
    result = scanner.evaluate(
        forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-19"
    )
    assert result == {"status": "not_mature", "forecast_id": "forecast-1", "horizon": 20}
    assert repository.outcomes_for_forecast("forecast-1") == []
    assert actuals.calls == 0


def test_mature_outcome_appends_actual_session_and_fingerprint(tmp_path):
    scanner, repository, _actuals, _spies = _scanner(tmp_path)
    outcome = scanner.evaluate(
        forecast_id="forecast-1", horizon=5, as_of_session_id="CNA-FUTURE-60"
    )
    assert outcome["status"] == "evaluated"
    assert outcome["actual_session_id"] == "CNA-FUTURE-05"
    assert len(outcome["actual_fingerprint"]) == 64
    assert repository.outcomes_for_forecast("forecast-1") == [outcome]


def test_calibration_computes_close_mae_interval_coverage_and_pinball_losses(tmp_path):
    scanner, repository, _actuals, _spies = _scanner(tmp_path)
    outcome = scanner.evaluate(
        forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60"
    )
    fact = repository.calibration_for_outcome(outcome["id"])
    assert fact["close_mae"] == pytest.approx(abs(outcome["actual_close"] - 12.0))
    assert fact["p10_p90_interval_covered"] is True
    assert fact["pinball_p10"] == pytest.approx(
        max(0.1 * (outcome["actual_close"] - 10.0), -0.9 * (outcome["actual_close"] - 10.0))
    )
    assert fact["pinball_p50"] == pytest.approx(
        max(0.5 * (outcome["actual_close"] - 12.0), -0.5 * (outcome["actual_close"] - 12.0))
    )
    assert fact["pinball_p90"] == pytest.approx(
        max(0.9 * (outcome["actual_close"] - 14.0), -0.1 * (outcome["actual_close"] - 14.0))
    )


def test_calibration_fact_records_schema_sample_count_and_coverage_period(tmp_path):
    scanner, repository, _actuals, _spies = _scanner(tmp_path)
    scanner.evaluate(forecast_id="forecast-1", horizon=5, as_of_session_id="CNA-FUTURE-60")
    scanner.evaluate(forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60")
    aggregate = repository.calibration_summary(metric_schema="forecast-close-calibration-v1")
    assert aggregate["sample_count"] == 2
    assert aggregate["coverage_start"] == "CNA-FUTURE-05"
    assert aggregate["coverage_end"] == "CNA-FUTURE-20"
    assert aggregate["metric_schema"] == "forecast-close-calibration-v1"
    assert aggregate["metric_version"] == 1


def test_partial_maturity_evaluates_only_due_horizons(tmp_path):
    scanner, repository, _actuals, _spies = _scanner(tmp_path)
    results = scanner.scan(as_of_session_id="CNA-FUTURE-20")
    assert {(item["horizon"], item["status"]) for item in results} == {
        (5, "evaluated"),
        (20, "evaluated"),
        (60, "not_mature"),
    }
    assert {outcome["horizon"] for outcome in repository.outcomes_for_forecast("forecast-1")} == {
        5,
        20,
    }


def test_missing_or_nonfinite_actual_stays_pending_without_zero_or_terminal_fact(tmp_path):
    frame = pl.read_parquet(FIXTURE).with_columns(
        pl.when(pl.col("session_id") == "CNA-FUTURE-20")
        .then(None)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    scanner, repository, _actuals, _spies = _scanner(tmp_path, actuals=GovernedActuals(frame))
    result = scanner.evaluate(
        forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60"
    )
    assert result["status"] == "missing_actual"
    assert result["forecast_id"] == "forecast-1"
    assert result["horizon"] == 20
    assert repository.outcomes_for_forecast("forecast-1") == []
    assert repository.calibration_facts_for_forecast("forecast-1") == []


def test_duplicate_evaluation_returns_canonical_fact_without_reread(tmp_path):
    scanner, _repository, actuals, _spies = _scanner(tmp_path)
    first = scanner.evaluate(forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60")
    calls = actuals.calls
    second = scanner.evaluate(
        forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60"
    )
    assert second == first
    assert actuals.calls == calls


def test_two_parallel_scanners_append_one_outcome_and_calibration_fact(tmp_path):
    scanner, repository, _actuals, _spies = _scanner(tmp_path)
    barrier = threading.Barrier(2)

    def evaluate(_index: int):
        barrier.wait()
        return scanner.evaluate(
            forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(evaluate, (1, 2)))
    assert outcomes[0]["id"] == outcomes[1]["id"]
    assert len(repository.outcomes_for_forecast("forecast-1")) == 1
    assert len(repository.calibration_facts_for_forecast("forecast-1")) == 1


def test_interruption_before_terminal_append_is_retryable_without_partial_fact(tmp_path):
    scanner, repository, _actuals, _spies = _scanner(tmp_path)
    scanner.interrupt_at = "before_append"
    with pytest.raises(RuntimeError, match="interrupted"):
        scanner.evaluate(forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60")
    assert repository.outcomes_for_forecast("forecast-1") == []
    assert repository.calibration_facts_for_forecast("forecast-1") == []
    scanner.interrupt_at = None
    assert (
        scanner.evaluate(forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60")[
            "status"
        ]
        == "evaluated"
    )


def test_restart_releases_expired_scan_lease_and_skips_terminal_fact(tmp_path):
    scanner, repository, actuals, _spies = _scanner(tmp_path)
    first = scanner.evaluate(forecast_id="forecast-1", horizon=5, as_of_session_id="CNA-FUTURE-60")
    calls = actuals.calls
    repository.expire_maturity_leases(now="2099-01-01T00:00:00Z")
    restarted = scanner.restart_scan(as_of_session_id="CNA-FUTURE-60")
    assert first not in restarted
    assert actuals.calls > calls
    assert (
        len([row for row in repository.outcomes_for_forecast("forecast-1") if row["horizon"] == 5])
        == 1
    )


def test_calibration_never_rewrites_forecast_paths_quantiles_provenance_or_time(tmp_path):
    scanner, repository, _actuals, _spies = _scanner(tmp_path)
    before = _immutable_projection(repository)
    scanner.scan(as_of_session_id="CNA-FUTURE-60")
    assert _immutable_projection(repository) == before


def test_calibration_invokes_zero_thesis_strategy_plan_monitor_position_or_broker_actions(tmp_path):
    scanner, _repository, _actuals, spies = _scanner(tmp_path)
    scanner.scan(as_of_session_id="CNA-FUTURE-60")
    assert all(spy.calls == 0 for spy in spies.values())


def _insert_cursor_forecast(repository, *, forecast_id: str, created_at: str) -> None:
    repository.insert_fixture_forecast(
        {
            "id": forecast_id,
            "instrument_id": "instrument-600000",
            "origin_session_id": "CNA-20250430",
            "calendar_revision": "cn-a-calendar-2025-v1",
            "future_session_ids": [f"CNA-FUTURE-{index:02}" for index in range(1, 6)],
            "horizon": 5,
            "input_fingerprint": sha256(forecast_id.encode()).hexdigest(),
            "paths_checksum_sha256": "b" * 64,
            "quantiles_checksum_sha256": "c" * 64,
            "checkpoint_provenance": {
                "source_revision": "67b630e",
                "model_revision": "f4e6869",
                "tokenizer_revision": "26966d0",
            },
            "created_at": created_at,
            "quantiles": {"5": {"p10": 9.0, "p50": 10.0, "p90": 11.0}},
        }
    )


def test_durable_cursor_prevents_starvation_across_scan_batches(tmp_path):
    from app.forecast.calibration import ForecastMaturityScanner
    from app.forecast.repository import ForecastRepository

    repository = ForecastRepository(tmp_path / "operational.db")
    repository.migrate()
    for index in range(6):
        _insert_cursor_forecast(
            repository,
            forecast_id=f"forecast-{index}",
            created_at=f"2025-04-30T08:00:{index:02}Z",
        )
    scanner = ForecastMaturityScanner(
        repository=repository,
        actuals=GovernedActuals(),
        max_items_per_scan=2,
    )

    for _batch in range(3):
        assert len(scanner.scan(as_of_session_id="CNA-FUTURE-05")) == 2

    assert {
        row["id"]
        for row in repository.list_forecasts()
        if repository.outcome_for_horizon(str(row["id"]), 5) is not None
    } == {f"forecast-{index}" for index in range(6)}


def test_starvation_not_mature_old_record_does_not_hide_newer_due_record(tmp_path):
    from app.forecast.calibration import ForecastMaturityScanner
    from app.forecast.repository import ForecastRepository

    repository = ForecastRepository(tmp_path / "operational.db")
    repository.migrate()
    _insert_cursor_forecast(
        repository, forecast_id="forecast-old", created_at="2025-04-30T08:00:00Z"
    )
    _insert_cursor_forecast(
        repository, forecast_id="forecast-new", created_at="2025-04-30T08:00:01Z"
    )
    scanner = ForecastMaturityScanner(
        repository=repository, actuals=GovernedActuals(), max_items_per_scan=1
    )

    assert scanner.scan(as_of_session_id="CNA-FUTURE-04")[0]["status"] == "not_mature"
    result = scanner.scan(as_of_session_id="CNA-FUTURE-05")
    assert result[0]["forecast_id"] == "forecast-new"
    assert result[0]["status"] == "evaluated"


def test_parallel_cursor_acquisition_has_one_lease_winner(tmp_path):
    from app.forecast.repository import ForecastRepository

    repository = ForecastRepository(tmp_path / "operational.db")
    repository.migrate()
    _insert_cursor_forecast(
        repository, forecast_id="forecast-parallel", created_at="2025-04-30T08:00:00Z"
    )
    barrier = threading.Barrier(2)

    def acquire(owner: str):
        barrier.wait()
        return repository.acquire_maturity_page(owner=owner, ttl_seconds=30, limit=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pages = list(pool.map(acquire, ("scanner-a", "scanner-b")))

    assert sorted(bool(page) for page in pages) == [False, True]


def test_restart_after_future_window_uses_governed_sequence(tmp_path):
    from app.forecast.calibration import ForecastMaturityScanner
    from app.forecast.repository import ForecastRepository

    repository = ForecastRepository(tmp_path / "operational.db")
    repository.migrate()
    repository.insert_fixture_forecast(
        {
            "id": "forecast-restart",
            "instrument_id": "instrument-600000",
            "origin_session_id": "CNA-20250430",
            "calendar_revision": "cn-a-calendar-2025-v1",
            "future_session_ids": [
                "CNA-20250506",
                "CNA-20250507",
                "CNA-20250508",
                "CNA-20250509",
                "CNA-20250512",
            ],
            "horizon": 5,
            "input_fingerprint": "a" * 64,
            "paths_checksum_sha256": "b" * 64,
            "quantiles_checksum_sha256": "c" * 64,
            "checkpoint_provenance": {},
            "created_at": "2025-04-30T08:00:00Z",
            "quantiles": {"5": {"p10": 9.0, "p50": 10.0, "p90": 11.0}},
        }
    )

    class Actuals:
        @staticmethod
        def load_actual(**_identity):
            return {"close": 10.5}

    scanner = ForecastMaturityScanner(repository=repository, actuals=Actuals())
    result = scanner.restart_scan(as_of_session_id="CNA-20250520")
    assert result[0]["status"] == "evaluated"
    assert result[0]["actual_session_id"] == "CNA-20250512"


def test_missing_actual_repair_remains_retryable(tmp_path):

    class RepairableActuals:
        close: float | None = None

        def load_actual(self, **_identity):
            return None if self.close is None else {"close": self.close}

    actuals = RepairableActuals()
    scanner, repository, _unused, _spies = _scanner(
        tmp_path,
        actuals=actuals,  # type: ignore[arg-type]
    )
    first = scanner.evaluate(forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60")
    assert first["status"] == "missing_actual"
    assert repository.outcomes_for_forecast("forecast-1") == []

    actuals.close = 12.5
    repaired = scanner.evaluate(
        forecast_id="forecast-1", horizon=20, as_of_session_id="CNA-FUTURE-60"
    )
    assert repaired["status"] == "evaluated"
    assert repaired["actual_close"] == 12.5
    assert len(repository.calibration_facts_for_forecast("forecast-1")) == 1


def test_durable_cursor_interruption_before_append_retries_same_candidate(tmp_path):
    scanner, repository, _actuals, _spies = _scanner(tmp_path)
    scanner.interrupt_at = "before_append"
    with pytest.raises(RuntimeError, match="interrupted"):
        scanner.scan(as_of_session_id="CNA-FUTURE-60")
    assert repository.outcomes_for_forecast("forecast-1") == []

    scanner.interrupt_at = None
    repaired = scanner.restart_scan(as_of_session_id="CNA-FUTURE-60")
    assert repaired[0]["status"] == "evaluated"
