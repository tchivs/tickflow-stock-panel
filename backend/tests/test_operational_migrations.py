"""Atomicity contracts for the shared operational SQLite migrations."""

from __future__ import annotations

import sqlite3

import pytest

from app.operational import migrations

_ATOMIC_TEST_MIGRATIONS = (
    """
    CREATE TABLE atomic_probe (
        id INTEGER PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE INDEX atomic_probe_value_idx ON atomic_probe(value);
    """,
    """
    CREATE TABLE atomic_probe_followup (
        id INTEGER PRIMARY KEY REFERENCES atomic_probe(id) ON DELETE RESTRICT
    );
    """,
)
_ATOMIC_FAILING_MIGRATIONS = (
    _ATOMIC_TEST_MIGRATIONS[0] + "INSERT INTO injected_mid_script_failure(value) VALUES ('boom');",
    _ATOMIC_TEST_MIGRATIONS[1],
)


def _schema_objects(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE name LIKE 'atomic_probe%' AND type IN ('table', 'index')"
        )
    }


def test_atomic_version_and_user_version_roll_back_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migrations, "MIGRATIONS", _ATOMIC_FAILING_MIGRATIONS)
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    with pytest.raises(sqlite3.DatabaseError):
        migrations.migrate_operational_db(connection)

    assert _schema_objects(connection) == set()
    assert connection.execute("PRAGMA user_version").fetchone() == (0,)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_restart_after_mid_script_failure_applies_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migrations, "MIGRATIONS", _ATOMIC_FAILING_MIGRATIONS)
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    with pytest.raises(sqlite3.DatabaseError):
        migrations.migrate_operational_db(connection)

    monkeypatch.setattr(migrations, "MIGRATIONS", _ATOMIC_TEST_MIGRATIONS)
    migrations.migrate_operational_db(connection)
    assert _schema_objects(connection) == {
        "atomic_probe",
        "atomic_probe_followup",
        "atomic_probe_value_idx",
    }
    assert connection.execute("PRAGMA user_version").fetchone() == (2,)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)

    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (2,)


def test_forecast_maturity_cursor_upgrade_is_forward_only_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned = migrations.MIGRATIONS
    assert "forecast_maturity_cursor" in planned[-1]
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:-1])
    migrations.migrate_operational_db(connection)
    previous_version = len(planned) - 1
    assert connection.execute("PRAGMA user_version").fetchone() == (previous_version,)
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'forecast_maturity_cursor'"
        ).fetchone()
        is None
    )

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    row = connection.execute(
        "SELECT cursor_created_at, cursor_forecast_id, cursor_horizon, lease_owner, "
        "lease_until, transition_version FROM forecast_maturity_cursor"
    ).fetchone()
    assert row == ("", "", 0, None, None, 0)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    migrations.migrate_operational_db(connection)
    assert connection.execute("SELECT COUNT(*) FROM forecast_maturity_cursor").fetchone() == (1,)


def test_maturity_cursor_mid_migration_rollback_restores_schema_and_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned = migrations.MIGRATIONS
    assert "forecast_maturity_cursor" in planned[-1]
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:-1])
    migrations.migrate_operational_db(connection)
    previous_version = len(planned) - 1

    failing = planned[:-1] + (
        planned[-1] + "INSERT INTO injected_maturity_migration_failure(value) VALUES ('boom');",
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", failing)
    with pytest.raises(sqlite3.DatabaseError):
        migrations.migrate_operational_db(connection)

    assert connection.execute("PRAGMA user_version").fetchone() == (previous_version,)
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'forecast_maturity_cursor'"
        ).fetchone()
        is None
    )
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    assert connection.execute("SELECT COUNT(*) FROM forecast_maturity_cursor").fetchone() == (1,)


def _insert_legacy_forecast_record(connection: sqlite3.Connection) -> None:
    fingerprint = "a" * 64
    connection.execute(
        """INSERT INTO forecast_jobs
           (id, principal, instrument_id, horizon, catalog_id, idempotency_key,
            input_fingerprint, status, transition_version, retry_of_job_id, attempt,
            lease_owner, lease_until, terminal_reason, created_at, updated_at)
           VALUES ('legacy-job', 'researcher', 'instrument-600000', 5, 'kronos-mini',
                   'legacy-request', ?, 'completed', 1, NULL, 1, NULL, NULL, NULL,
                   '2025-04-30T08:00:00Z', '2025-04-30T08:00:00Z')""",
        (fingerprint,),
    )
    connection.execute(
        """INSERT INTO forecast_records
           (id, job_id, instrument_id, origin_session_id, calendar_id, calendar_revision,
            future_session_ids_json, input_fingerprint, input_artifact_descriptor_json,
            horizon, lookback, seed, temperature, top_k, top_p, sample_count, catalog_id,
            source_revision, source_digest_sha256, model_revision, model_digest_sha256,
            tokenizer_revision, tokenizer_digest_sha256, output_artifact_descriptor_json,
            paths_checksum_sha256, validation_warnings_json, created_at)
           VALUES ('legacy-forecast', 'legacy-job', 'instrument-600000', 'CNA-20250430',
                   'cn-a-v1', 'cn-a-calendar-2025-v1',
                   '["CNA-20250501","CNA-20250502","CNA-20250503","CNA-20250504","CNA-20250505"]',
                   ?, '{}', 5, 64, 0, 1.0, 1, 1.0, 32, 'kronos-mini',
                   'source-revision', ?, 'model-revision', ?, 'tokenizer-revision', ?,
                   '{}', ?, '[]', '2025-04-30T08:00:00Z')""",
        (fingerprint, "b" * 64, "c" * 64, "d" * 64, "e" * 64),
    )


def test_forecast_quantile_migration_is_forward_only_bounded_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned = migrations.MIGRATIONS
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:-1])
    migrations.migrate_operational_db(connection)
    previous_version = len(planned) - 1
    _insert_legacy_forecast_record(connection)
    connection.commit()

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)

    columns = {
        row[1]: row for row in connection.execute("PRAGMA table_info(forecast_records)")
    }
    expected = {
        "quantile_availability",
        "quantiles_artifact_descriptor_json",
        "quantiles_checksum_sha256",
        "quantiles_source_paths_sha256",
        "quantiles_provenance_digest_sha256",
        "quantile_row_count",
        "quantile_session_count",
        "quantile_feature_count",
    }
    assert expected.issubset(columns)
    assert not ({"p10", "p50", "p90", "quantiles_json", "quantile_values_json"} & columns.keys())
    row = connection.execute(
        """SELECT id, quantile_availability, quantiles_artifact_descriptor_json,
                  quantiles_checksum_sha256, quantiles_source_paths_sha256,
                  quantiles_provenance_digest_sha256, quantile_row_count,
                  quantile_session_count, quantile_feature_count
           FROM forecast_records WHERE id = 'legacy-forecast'"""
    ).fetchone()
    assert row == ("legacy-forecast", "legacy_unavailable", None, None, None, None, None, None, None)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    migrations.migrate_operational_db(connection)
    assert connection.execute("SELECT COUNT(*) FROM forecast_records").fetchone() == (1,)


def test_quantile_migration_failure_rolls_back_schema_and_user_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned = migrations.MIGRATIONS
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:-1])
    migrations.migrate_operational_db(connection)
    previous_version = len(planned) - 1

    failing = planned[:-1] + (
        planned[-1] + "INSERT INTO injected_quantile_migration_failure(value) VALUES ('boom');",
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", failing)
    with pytest.raises(sqlite3.DatabaseError):
        migrations.migrate_operational_db(connection)

    columns = {row[1] for row in connection.execute("PRAGMA table_info(forecast_records)")}
    assert "quantile_availability" not in columns
    assert connection.execute("PRAGMA user_version").fetchone() == (previous_version,)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
