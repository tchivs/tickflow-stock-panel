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
