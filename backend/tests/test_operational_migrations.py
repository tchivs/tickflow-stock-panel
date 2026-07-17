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
    _ATOMIC_TEST_MIGRATIONS[0]
    + "INSERT INTO injected_mid_script_failure(value) VALUES ('boom');",
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
