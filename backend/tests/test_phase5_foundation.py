"""Focused contracts for the shared Phase 05 foundation."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.operational.migrations import MIGRATIONS, migrate_operational_db


PHASE5_TABLES = {
    "shadow_import_batches",
    "shadow_trade_facts",
    "shadow_evidence_sets",
    "shadow_evidence_batches",
    "shadow_evidence_members",
    "shadow_evidence_exclusions",
    "shadow_candidates",
    "shadow_candidate_runs",
    "shadow_candidate_evaluations",
    "shadow_retention_events",
    "theses",
    "thesis_versions",
    "thesis_valuation_anchors",
    "thesis_conditions",
    "thesis_condition_schedules",
    "thesis_condition_checks",
    "thesis_pending_conclusions",
    "thesis_review_events",
    "forecast_jobs",
    "forecast_global_leases",
    "forecast_records",
    "forecast_outcomes",
    "forecast_calibration_facts",
}

IMMUTABLE_PHASE5_TABLES = PHASE5_TABLES - {
    "thesis_condition_schedules",
    "forecast_jobs",
    "forecast_global_leases",
}


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _phase4_database(path: Path) -> sqlite3.Connection:
    connection = _connect(path)
    for version, migration in enumerate(MIGRATIONS[:-1], start=1):
        connection.executescript(migration)
        connection.execute(f"PRAGMA user_version = {version}")
    connection.execute(
        "INSERT INTO advanced_policy_revisions "
        "(id, revision, fingerprint, fact_schema_version, snapshot_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "preserved-policy",
            "phase-4",
            "a" * 64,
            "advanced_policy_snapshot_v1",
            "{}",
            "2026-07-15T00:00:00Z",
        ),
    )
    connection.commit()
    return connection


def _phase5_table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        if row[0] in PHASE5_TABLES
    }


def _insert_thesis_graph(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO theses (id, instrument, created_by, created_at) VALUES (?, ?, ?, ?)",
        ("thesis-1", "600519.SH", "principal-1", "2026-07-16T00:00:00Z"),
    )
    connection.execute(
        """INSERT INTO thesis_versions
           (id, thesis_id, version, predecessor_id, core_judgment, rationale,
            change_reason, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "version-1",
            "thesis-1",
            1,
            None,
            "Pricing power remains durable.",
            "Governed filing evidence.",
            "Initial thesis record",
            "principal-1",
            "2026-07-16T00:00:00Z",
        ),
    )
    connection.execute(
        """INSERT INTO thesis_conditions
           (id, version_id, copied_from_condition_id, source_kind, field, operator,
            threshold_json, unit, lookback_days, cadence, timezone, description, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "condition-1",
            "version-1",
            None,
            "financial",
            "revenue_growth_yoy",
            "lt",
            "0.0",
            "ratio",
            120,
            "quarterly",
            "Asia/Shanghai",
            "Revenue growth turns negative.",
            "2026-07-16T00:00:00Z",
        ),
    )
    connection.execute(
        """INSERT INTO thesis_condition_schedules
           (condition_id, active, next_due_at, lease_owner, lease_until,
            last_attempt_at, transition_version, created_at, updated_at)
           VALUES (?, 1, ?, NULL, NULL, NULL, 0, ?, ?)""",
        (
            "condition-1",
            "2026-07-17T00:00:00Z",
            "2026-07-16T00:00:00Z",
            "2026-07-16T00:00:00Z",
        ),
    )


def _insert_forecast_job(connection: sqlite3.Connection) -> None:
    connection.execute(
        """INSERT INTO forecast_jobs
           (id, principal, instrument_id, horizon, catalog_id, idempotency_key,
            input_fingerprint, status, transition_version, retry_of_job_id, attempt,
            lease_owner, lease_until, terminal_reason, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, 1, NULL, NULL, NULL, ?, ?)""",
        (
            "job-1",
            "principal-1",
            "instrument-600000",
            20,
            "kronos-mini",
            "request-key-1",
            "b" * 64,
            "2026-07-16T00:00:00Z",
            "2026-07-16T00:00:00Z",
        ),
    )


def test_migration_upgrades_phase4_and_fresh_databases_without_losing_rows(tmp_path: Path) -> None:
    upgraded = _phase4_database(tmp_path / "upgraded.db")
    fresh = _connect(tmp_path / "fresh.db")

    migrate_operational_db(upgraded)
    migrate_operational_db(fresh)

    expected_version = len(MIGRATIONS)
    assert upgraded.execute("PRAGMA user_version").fetchone()[0] == expected_version
    assert fresh.execute("PRAGMA user_version").fetchone()[0] == expected_version
    assert _phase5_table_names(upgraded) == PHASE5_TABLES
    assert _phase5_table_names(fresh) == PHASE5_TABLES
    assert upgraded.execute(
        "SELECT revision FROM advanced_policy_revisions WHERE id = 'preserved-policy'"
    ).fetchone() == ("phase-4",)

    migrate_operational_db(upgraded)
    assert upgraded.execute("PRAGMA user_version").fetchone()[0] == expected_version
    assert _phase5_table_names(upgraded) == PHASE5_TABLES


def test_migration_installs_update_and_delete_guards_for_every_fact(tmp_path: Path) -> None:
    connection = _connect(tmp_path / "operational.db")
    migrate_operational_db(connection)
    trigger_names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }

    for table in IMMUTABLE_PHASE5_TABLES:
        assert f"{table}_no_update" in trigger_names
        assert f"{table}_no_delete" in trigger_names


def test_migration_restricts_orphans_and_direct_fact_mutation(tmp_path: Path) -> None:
    connection = _connect(tmp_path / "operational.db")
    migrate_operational_db(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO shadow_trade_facts
               (id, batch_id, row_identity, duplicate_group_hash, broker_fill_id,
                account_alias, symbol, side, executed_at, quantity, price, fees,
                currency, source_row_ordinal, source_values_json,
                normalized_payload_json, created_at)
               VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "trade-orphan",
                "missing-batch",
                "row-1",
                "c" * 64,
                "opaque-account",
                "600000.SH",
                "buy",
                "2026-07-16T01:00:00Z",
                10.0,
                12.5,
                0.2,
                "CNY",
                1,
                "{}",
                "{}",
                "2026-07-16T01:00:00Z",
            ),
        )

    _insert_thesis_graph(connection)
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        connection.execute(
            "UPDATE thesis_versions SET core_judgment = ? WHERE id = ?",
            ("tampered", "version-1"),
        )
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        connection.execute("DELETE FROM thesis_conditions WHERE id = ?", ("condition-1",))


def test_migration_allows_only_monotonic_schedule_cursor_updates(tmp_path: Path) -> None:
    connection = _connect(tmp_path / "operational.db")
    migrate_operational_db(connection)
    _insert_thesis_graph(connection)

    connection.execute(
        """UPDATE thesis_condition_schedules
           SET lease_owner = ?, lease_until = ?, transition_version = 1, updated_at = ?
           WHERE condition_id = ?""",
        (
            "scanner-1",
            "2026-07-17T00:01:00Z",
            "2026-07-16T00:01:00Z",
            "condition-1",
        ),
    )
    connection.execute(
        """UPDATE thesis_condition_schedules
           SET next_due_at = ?, lease_owner = NULL, lease_until = NULL,
               last_attempt_at = ?, transition_version = 2, updated_at = ?
           WHERE condition_id = ?""",
        (
            "2026-10-17T00:00:00Z",
            "2026-07-17T00:00:30Z",
            "2026-07-17T00:00:30Z",
            "condition-1",
        ),
    )

    with pytest.raises(sqlite3.DatabaseError, match="monotonic|cursor"):
        connection.execute(
            """UPDATE thesis_condition_schedules
               SET next_due_at = ?, transition_version = 3, updated_at = ?
               WHERE condition_id = ?""",
            (
                "2026-01-01T00:00:00Z",
                "2026-07-17T00:01:00Z",
                "condition-1",
            ),
        )
    with pytest.raises(sqlite3.DatabaseError, match="monotonic|cursor"):
        connection.execute(
            """UPDATE thesis_condition_schedules
               SET active = 1, transition_version = 7, updated_at = ?
               WHERE condition_id = ?""",
            ("2026-07-17T00:01:00Z", "condition-1"),
        )


def test_migration_enforces_forecast_job_state_machine_and_column_guard(tmp_path: Path) -> None:
    connection = _connect(tmp_path / "operational.db")
    migrate_operational_db(connection)
    _insert_forecast_job(connection)

    with pytest.raises(sqlite3.DatabaseError, match="transition"):
        connection.execute(
            """UPDATE forecast_jobs
               SET status = 'completed', transition_version = 1, updated_at = ?
               WHERE id = 'job-1'""",
            ("2026-07-16T00:01:00Z",),
        )
    with pytest.raises(sqlite3.DatabaseError, match="immutable|cursor"):
        connection.execute(
            """UPDATE forecast_jobs
               SET horizon = 5, status = 'running', transition_version = 1,
                   lease_owner = 'worker-1', lease_until = ?, updated_at = ?
               WHERE id = 'job-1'""",
            ("2026-07-16T00:02:00Z", "2026-07-16T00:01:00Z"),
        )

    connection.execute(
        """UPDATE forecast_jobs
           SET status = 'running', transition_version = 1,
               lease_owner = 'worker-1', lease_until = ?, updated_at = ?
           WHERE id = 'job-1'""",
        ("2026-07-16T00:02:00Z", "2026-07-16T00:01:00Z"),
    )
    connection.execute(
        """UPDATE forecast_jobs
           SET status = 'completed', transition_version = 2,
               lease_owner = NULL, lease_until = NULL, updated_at = ?
           WHERE id = 'job-1'""",
        ("2026-07-16T00:02:00Z",),
    )
    with pytest.raises(sqlite3.DatabaseError, match="transition|immutable"):
        connection.execute(
            """UPDATE forecast_jobs
               SET status = 'running', transition_version = 3, updated_at = ?
               WHERE id = 'job-1'""",
            ("2026-07-16T00:03:00Z",),
        )
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        connection.execute("DELETE FROM forecast_jobs WHERE id = 'job-1'")
