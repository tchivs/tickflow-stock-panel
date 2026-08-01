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
    cursor_indexes = [
        index for index, script in enumerate(planned) if "forecast_maturity_cursor" in script
    ]
    assert cursor_indexes, "forecast_maturity_cursor migration is missing"
    cursor_index = cursor_indexes[0]
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:cursor_index])
    migrations.migrate_operational_db(connection)
    previous_version = cursor_index
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
    cursor_indexes = [
        index for index, script in enumerate(planned) if "forecast_maturity_cursor" in script
    ]
    assert cursor_indexes, "forecast_maturity_cursor migration is missing"
    cursor_index = cursor_indexes[0]
    cursor_script = planned[cursor_index]
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:cursor_index])
    migrations.migrate_operational_db(connection)
    previous_version = cursor_index

    failing = planned[:cursor_index] + (
        cursor_script + "INSERT INTO injected_maturity_migration_failure(value) VALUES ('boom');",
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
    quantile_index = next(
        index
        for index, script in enumerate(planned)
        if "quantile_availability" in script
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:quantile_index])
    migrations.migrate_operational_db(connection)
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
    quantile_index = next(
        index
        for index, script in enumerate(planned)
        if "quantile_availability" in script
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:quantile_index])
    migrations.migrate_operational_db(connection)
    previous_version = quantile_index

    failing = planned[:quantile_index] + (
        planned[quantile_index]
        + "INSERT INTO injected_quantile_migration_failure(value) VALUES ('boom');",
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


def test_r43_cr03_legacy_unbound_queued_migration_quarantines_before_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned = migrations.MIGRATIONS
    retry_index = next(
        index
        for index, script in enumerate(planned)
        if "forecast_retry_operations" in script
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:retry_index])
    migrations.migrate_operational_db(connection)
    connection.execute(
        """INSERT INTO forecast_jobs
           (id, principal, instrument_id, horizon, catalog_id, idempotency_key,
            input_fingerprint, status, transition_version, retry_of_job_id, attempt,
            lease_owner, lease_until, terminal_reason, created_at, updated_at)
           VALUES ('legacy-unbound-queued', 'researcher', 'instrument-600000', 20,
                   'kronos-mini', 'legacy-unbound-request', ?, 'queued', 0, NULL, 1,
                   NULL, NULL, NULL, '2025-04-30T08:00:00Z',
                   '2025-04-30T08:00:00Z')""",
        ("a" * 64,),
    )
    connection.execute(
        """INSERT INTO forecast_job_transitions
           (job_id, transition_version, status, terminal_reason, recorded_at)
           VALUES ('legacy-unbound-queued', 0, 'queued', NULL,
                   '2025-04-30T08:00:00Z')"""
    )
    connection.commit()

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)

    row = connection.execute(
        """SELECT status, transition_version, terminal_reason, dispatch_ready,
                  bound_identity_json, bound_input_artifact_id
           FROM forecast_jobs WHERE id = 'legacy-unbound-queued'"""
    ).fetchone()
    assert row == (
        "interrupted",
        1,
        "legacy_unbound_quarantined",
        0,
        None,
        None,
    )
    transitions = connection.execute(
        """SELECT transition_version, status, terminal_reason
           FROM forecast_job_transitions
           WHERE job_id = 'legacy-unbound-queued'
           ORDER BY transition_version"""
    ).fetchall()
    assert transitions == [
        (0, "queued", None),
        (1, "interrupted", "legacy_unbound_quarantined"),
    ]
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)


def _insert_phase10_revision(connection: sqlite3.Connection) -> None:
    """Insert the minimal factor definition + revision the verdict FK requires."""
    connection.execute(
        "INSERT INTO research_factor_definitions (id, created_at) VALUES ('f1', '2026-01-01T00:00:00Z')"
    )
    connection.execute(
        """INSERT INTO research_factor_revisions (
               id, factor_id, revision_number, name, description, hypothesis,
               canonical_expression, dsl_version, ast_signature, shape_signature,
               fields_json, operators_json, functions_json, provenance_json, created_at
           ) VALUES ('r1', 'f1', 1, 'close-factor', '', '', 'close', 'factor-dsl-v1',
                     'sig', 'shape', '["close"]', '[]', '[]', '{}', '2026-01-01T00:00:00Z')"""
    )


def test_phase10_append_only_tables_migrate_with_constraints_and_idempotence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned = migrations.MIGRATIONS
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    migrations.migrate_operational_db(connection)

    tables = {
        "factor_universe_membership",
        "factor_admission_verdicts",
        "factor_model_models",
        "factor_model_composites",
    }
    present = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert tables.issubset(present)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)

    # Forward-only idempotence: re-running the full migration is a no-op.
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)

    # --- factor_universe_membership: UNIQUE + CHECK + append-only triggers. ---
    membership = (
        "INSERT INTO factor_universe_membership (id, universe_name, symbol, asset_type, "
        "effective_date, state, source, provenance_json, created_at) "
        "VALUES ('m1', 'cn-a-share', '600000.SH', 'stock', '2025-07-29', 'listed', "
        "'instruments-sync', '{}', '2026-01-01T00:00:00Z')"
    )
    connection.execute(membership)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(membership.replace("'m1'", "'m2'"))  # UNIQUE violation
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO factor_universe_membership (id, universe_name, symbol, asset_type, "
            "effective_date, state, source, provenance_json, created_at) "
            "VALUES ('m3', 'cn-a-share', '600001.SH', 'future', '2025-07-29', 'listed', "
            "'instruments-sync', '{}', '2026-01-01T00:00:00Z')"  # CHECK asset_type
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO factor_universe_membership (id, universe_name, symbol, asset_type, "
            "effective_date, state, source, provenance_json, created_at) "
            "VALUES ('m4', 'cn-a-share', '600001.SH', 'stock', '2025-07-29', 'suspended', "
            "'instruments-sync', '{}', '2026-01-01T00:00:00Z')"  # CHECK state
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE factor_universe_membership SET state = 'delisted' WHERE id = 'm1'")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM factor_universe_membership WHERE id = 'm1'")

    # --- factor_admission_verdicts: FK + UNIQUE + CHECK + sha256 length. ---
    _insert_phase10_revision(connection)
    verdict = (
        "INSERT INTO factor_admission_verdicts (id, revision_id, policy_version, verdict, reason, "
        "gates_json, candidate_trail_json, resolved_universe_json, input_snapshot_sha256, created_at) "
        f"VALUES ('v1', 'r1', 'admission-policy-v1', 'admitted', 'ok', '[]', '{{}}', '{{}}', "
        f"'{'a' * 64}', '2026-01-01T00:00:00Z')"
    )
    connection.execute(verdict)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(verdict.replace("'v1'", "'v2'"))  # UNIQUE(revision_id, policy_version)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO factor_admission_verdicts (id, revision_id, policy_version, verdict, reason, "
            "gates_json, candidate_trail_json, resolved_universe_json, input_snapshot_sha256, created_at) "
            f"VALUES ('v3', 'r1', 'admission-policy-v1', 'maybe', 'x', '[]', '{{}}', '{{}}', "
            f"'{'b' * 64}', '2026-01-01T00:00:00Z')"  # CHECK verdict
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO factor_admission_verdicts (id, revision_id, policy_version, verdict, reason, "
            "gates_json, candidate_trail_json, resolved_universe_json, input_snapshot_sha256, created_at) "
            "VALUES ('v4', 'missing-revision', 'admission-policy-v1', 'admitted', 'x', '[]', '{{}}', "
            f"'{{}}', '{'c' * 64}', '2026-01-01T00:00:00Z')"  # FK RESTRICT
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO factor_admission_verdicts (id, revision_id, policy_version, verdict, reason, "
            "gates_json, candidate_trail_json, resolved_universe_json, input_snapshot_sha256, created_at) "
            "VALUES ('v5', 'r1', 'admission-policy-v1', 'admitted', 'x', '[]', '{{}}', "
            "'{}', 'short', '2026-01-01T00:00:00Z')"  # CHECK sha256 length
        )

    # --- factor_model_models: CHECK weighting. ---
    connection.execute(
        "INSERT INTO factor_model_models (model_id, name, weighting, revision_ids_json, "
        "weights_json, input_snapshot_sha256, created_at) "
        f"VALUES ('m1', 'composite', 'equal', '[]', '{{}}', '{'d' * 64}', '2026-01-01T00:00:00Z')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO factor_model_models (model_id, name, weighting, revision_ids_json, "
            "weights_json, input_snapshot_sha256, created_at) "
            f"VALUES ('m2', 'composite', 'quantile', '[]', '{{}}', '{'e' * 64}', '2026-01-01T00:00:00Z')"
        )

    # --- factor_model_composites: FK + sha256 length. ---
    connection.execute(
        "INSERT INTO factor_model_composites (id, model_id, output_sha256, artifact_relative_path, "
        "input_snapshot_sha256, created_at) "
        f"VALUES ('c1', 'm1', '{'f' * 64}', 'research_artifacts/run/composite.parquet', "
        f"'{'d' * 64}', '2026-01-01T00:00:00Z')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO factor_model_composites (id, model_id, output_sha256, artifact_relative_path, "
            "input_snapshot_sha256, created_at) "
            f"VALUES ('c2', 'missing-model', '{'g' * 64}', 'research_artifacts/run/composite.parquet', "
            f"'{'d' * 64}', '2026-01-01T00:00:00Z')"  # FK RESTRICT
        )
