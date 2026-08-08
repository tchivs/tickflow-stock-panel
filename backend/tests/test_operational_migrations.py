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


def _insert_phase11_model(connection: sqlite3.Connection) -> None:
    """Insert the minimal factor model row the runs-table FK requires."""
    connection.execute(
        "INSERT INTO factor_model_models (model_id, name, weighting, revision_ids_json, "
        "weights_json, input_snapshot_sha256, created_at) "
        f"VALUES ('pf-m1', 'portfolio-composite', 'equal', '[]', '{{}}', '{'h' * 64}', "
        "'2026-01-01T00:00:00Z')"
    )


def _run_row(
    run_id: str = "a1b2c3d4e5f60718293a4b5c6d7e8f90",
    *,
    objective: str = "min_volatility",
    expected_return_method: str = "composite-zscore-v1",
    risk_model: str = "sample_covariance_v1",
    problem_status: str = "optimal",
    failure_reason: str | None = None,
    input_sha256: str | None = None,
    output_sha256: str | None = None,
    model_id: str | None = "pf-m1",
) -> str:
    """Build a valid portfolio_optimization_runs INSERT statement."""
    return (
        "INSERT INTO portfolio_optimization_runs (id, objective, as_of, universe, model_id, "
        "composite_snapshot_id, input_snapshot_sha256, expected_return_method, risk_model, "
        "risk_model_json, constraint_stack_json, solver_name, solver_version, solver_options_json, "
        "problem_status, failure_reason, output_weights_json, output_sha256, "
        "weights_artifact_relative_path, baseline_weights_json, created_at) "
        "VALUES ("
        f"'{run_id}', '{objective}', '2026-08-01', 'cn-a-share', "
        + (f"'{model_id}', " if model_id else "NULL, ")
        + f"'csnap-1', '{input_sha256 if input_sha256 is not None else '1' * 64}', "
        f"'{expected_return_method}', '{risk_model}', '{{\"psd_repair\":{{\"method\":\"none\"}}}}', "
        f"'{{\"cap\":0.1}}', 'CLARABEL', '0.11.1', '{{}}', '{problem_status}', "
        + (f"'{failure_reason}', " if failure_reason is not None else "NULL, ")
        + (f"'{{\"000001.SZ\":0.5}}', " if output_sha256 is not None else "NULL, ")
        + (f"'{output_sha256}', " if output_sha256 is not None else "NULL, ")
        + "'research_artifacts/run-id/weights.json', '{\"000001.SZ\":0.5}', "
        + "'2026-08-01T00:00:00Z')"
    )


def test_phase11_optimization_runs_migrate_with_constraints_and_idempotence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """portfolio_optimization_runs: CHECK enums + sha256 + failed⇔reason + triggers."""
    planned = migrations.MIGRATIONS
    runs_index = next(
        index
        for index, script in enumerate(planned)
        if "portfolio_optimization_runs" in script
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    # Forward-only: table absent before the Phase 11 script, present after.
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:runs_index])
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (runs_index,)
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'portfolio_optimization_runs'"
        ).fetchone()
        is None
    )

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    migrations.migrate_operational_db(connection)  # idempotent no-op
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)

    _insert_phase11_model(connection)

    # --- Valid minimal optimal run row. ---
    connection.execute(_run_row())

    # --- CHECK objective enum. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_run_row(run_id="r2" * 16, objective="max_alpha"))
    # --- CHECK expected_return_method enum. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_run_row(run_id="r3" * 16, expected_return_method="live"))
    # --- CHECK risk_model enum. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_run_row(run_id="r4" * 16, risk_model="shrinkage_v1"))
    # --- CHECK problem_status enum. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_run_row(run_id="r5" * 16, problem_status="converged"))
    # --- CHECK input_snapshot_sha256 length. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_run_row(run_id="r6" * 16, input_sha256="short"))
    # --- CHECK output_sha256 length when present. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            _run_row(run_id="r7" * 16, output_sha256="not-a-sha256")
        )
    # --- failed requires failure_reason; failure_reason requires failed/solver_error. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_run_row(run_id="r8" * 16, problem_status="failed"))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            _run_row(run_id="r9" * 16, failure_reason="solver blew up")
        )
    # --- failed + failure_reason is the valid invariant row. ---
    connection.execute(
        _run_row(
            run_id="ra" * 16,
            problem_status="failed",
            failure_reason="non-PSD covariance without provenance",
        )
    )
    # --- solver_error also requires failure_reason. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_run_row(run_id="rb" * 16, problem_status="solver_error"))
    connection.execute(
        _run_row(
            run_id="rc" * 16,
            problem_status="solver_error",
            failure_reason="CLARABEL crashed",
        )
    )

    # --- model_id NULL allowed for expected_return_method='none' (risk-only run). ---
    connection.execute(_run_row(run_id="rd" * 16, model_id=None, expected_return_method="none"))

    # --- Immutability triggers: UPDATE and DELETE raise. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE portfolio_optimization_runs SET solver_name = 'OSQP' "
            "WHERE id = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM portfolio_optimization_runs WHERE id = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'")

    # --- FK RESTRICT: model_id must reference factor_model_models. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_run_row(run_id="re" * 16, model_id="missing-model"))


def test_phase12_risk_model_enum_widened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """option-a: the runs-table risk_model CHECK accepts the 4-model enum."""
    planned = migrations.MIGRATIONS
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    _insert_phase11_model(connection)

    for index, model in enumerate(
        ("sample_covariance_v1", "semi_covariance_v1", "ewma_covariance_v1", "ledoit_wolf_v1")
    ):
        connection.execute(_run_row(run_id=f"r{index}" * 16, risk_model=model))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_run_row(run_id="rf" * 16, risk_model="shrinkage_v1"))


def test_phase12_attribution_evidence_migrate_with_constraints_and_idempotence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """portfolio_risk_attribution_evidence: enums + sha256 + reconciliation + triggers."""
    planned = migrations.MIGRATIONS
    evidence_index = next(
        index
        for index, script in enumerate(planned)
        if "portfolio_risk_attribution_evidence" in script
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    # Forward-only: table absent before the Phase 12 script, present after.
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:evidence_index])
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (evidence_index,)
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'portfolio_risk_attribution_evidence'"
        ).fetchone()
        is None
    )

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    migrations.migrate_operational_db(connection)  # idempotent no-op
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)

    _insert_phase11_model(connection)
    connection.execute(_run_row())
    evidence = (
        "INSERT INTO portfolio_risk_attribution_evidence (id, attribution_type, run_id, risk_model, "
        "as_of, output_sha256, artifact_relative_path, reconciliation_json, created_at) "
        f"VALUES ('e1', 'exposure_contribution', 'a1b2c3d4e5f60718293a4b5c6d7e8f90', "
        f"'sample_covariance_v1', '2026-08-01', '{'a' * 64}', "
        "'research_artifacts/run-id/attribution.json', '{\"portfolio_variance\":1.0}', "
        "'2026-08-01T00:00:00Z')"
    )
    connection.execute(evidence)

    # --- CHECK attribution_type enum. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            evidence.replace("'e1'", "'e2'").replace("'exposure_contribution'", "'backtest'")
        )
    # --- CHECK risk_model enum. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            evidence.replace("'e1'", "'e3'").replace("'sample_covariance_v1'", "'shrinkage_v1'")
        )
    # --- CHECK output_sha256 length. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            evidence.replace("'e1'", "'e4'").replace("'" + "a" * 64 + "'", "'short'")
        )
    # --- CHECK reconciliation_json NOT NULL (exposure rows always reconcile). ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            evidence.replace("'e1'", "'e5'").replace("'{\"portfolio_variance\":1.0}'", "NULL")
        )
    # --- Immutability triggers: UPDATE and DELETE raise. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE portfolio_risk_attribution_evidence SET as_of = '2026-08-02' WHERE id = 'e1'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM portfolio_risk_attribution_evidence WHERE id = 'e1'")
    # --- FK RESTRICT: run_id must reference portfolio_optimization_runs. ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            evidence.replace("'e1'", "'e6'").replace(
                "'a1b2c3d4e5f60718293a4b5c6d7e8f90'", "'missing-run-id'"
            )
        )
    # --- Drawdown evidence rows are valid with a reconciliation payload. ---
    connection.execute(
        "INSERT INTO portfolio_risk_attribution_evidence (id, attribution_type, run_id, risk_model, "
        "as_of, output_sha256, artifact_relative_path, reconciliation_json, created_at) "
        f"VALUES ('e7', 'drawdown', 'a1b2c3d4e5f60718293a4b5c6d7e8f90', "
        f"'semi_covariance_v1', '2026-08-01', '{'b' * 64}', "
        "'research_artifacts/run-id/drawdown.json', '{\"period_count\":0}', "
        "'2026-08-01T00:00:00Z')"
    )


def _wf_plan_row(plan_id: str = "wf-plan-1") -> str:
    """Build a valid wf_plans INSERT statement."""
    return (
        "INSERT INTO wf_plans (id, universe, asset_type, start, end, train_size, gap_size, "
        "test_size, oos_size, horizon, trading_dates_json, fold_geometry_json, "
        "oos_pinned_at, created_at) "
        f"VALUES ('{plan_id}', 'cn-a-share', 'stock', '2025-07-29', '2026-07-30', "
        f"120, 20, 20, 40, 5, '[]', '{{}}', '2026-08-01T00:00:00Z', "
        "'2026-08-01T00:00:00Z')"
    )


def _wf_fold_row(
    fold_id: str = "wf-fold-1",
    *,
    plan_id: str = "wf-plan-1",
    fold_index: int = 0,
    is_oos: int = 0,
    strategy_id: str = "fixture_strategy",
    params_sha256: str | None = None,
) -> str:
    """Build a valid wf_folds INSERT statement (plan FK row must exist)."""
    return (
        "INSERT INTO wf_folds (id, plan_id, fold_index, is_oos, strategy_id, params_sha256, "
        "train_start, train_end, test_start, test_end, membership_fingerprint, "
        "chain_config_json, stats_json, created_at) "
        f"VALUES ('{fold_id}', '{plan_id}', {fold_index}, {is_oos}, '{strategy_id}', "
        f"'{params_sha256 if params_sha256 is not None else 'a' * 64}', "
        f"'2025-07-29', '2026-01-22', '2026-03-02', '2026-03-27', '{'b' * 64}', "
        "'{\"end\":\"2026-04-01\"}', '{\"effective_days\":15}', '2026-08-01T00:00:00Z')"
    )


def test_phase13_wf_tables_migrate_with_constraints_and_idempotence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Five wf_* tables: CHECKs + sha256 + FK graph + immutability triggers."""
    planned = migrations.MIGRATIONS
    wf_index = next(
        index for index, script in enumerate(planned) if "CREATE TABLE wf_plans" in script
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    # Forward-only: wf_* tables absent before the Phase 13 script, present after.
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:wf_index])
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (wf_index,)
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'wf_plans'"
        ).fetchone()
        is None
    )

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    for table in ("wf_plans", "wf_folds", "wf_search_runs", "wf_validated_strategies", "wf_ensembles"):
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            is not None
        )
    migrations.migrate_operational_db(connection)  # idempotent no-op
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)

    # --- wf_plans: valid row + CHECK enums. ---
    connection.execute(_wf_plan_row())
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_wf_plan_row().replace("'stock'", "'index'"))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            _wf_plan_row(plan_id="wf-plan-bad").replace("120, 20, 20, 40, 5", "0, 20, 20, 40, 5")
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            _wf_plan_row(plan_id="wf-plan-bad2").replace("120, 20, 20, 40, 5", "120, 20, 20, 40, 0")
        )

    # --- wf_folds: FK RESTRICT + exactly-once UNIQUE (incl. OOS). ---
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_wf_fold_row(fold_id="wf-fold-missing", plan_id="missing-plan"))
    connection.execute(_wf_fold_row())
    with pytest.raises(sqlite3.IntegrityError):  # duplicate key -> exactly-once
        connection.execute(_wf_fold_row(fold_id="wf-fold-dup"))
    with pytest.raises(sqlite3.IntegrityError):  # bad params_sha256 length
        connection.execute(_wf_fold_row(fold_id="wf-fold-short", params_sha256="short"))
    with pytest.raises(sqlite3.IntegrityError):  # is_oos must be 0/1
        connection.execute(_wf_fold_row(fold_id="wf-fold-bad-oos", is_oos=2))
    # OOS fold row records is_oos=1 under the same UNIQUE key.
    connection.execute(
        _wf_fold_row(fold_id="wf-fold-oos", fold_index=0, is_oos=1, params_sha256="c" * 64)
    )

    # --- wf_search_runs: oos_excluded CHECK (must be 0/1). ---
    search = (
        "INSERT INTO wf_search_runs (id, plan_id, strategy_id, objective, direction, "
        "search_space_json, n_trials, n_completed, score_distribution_json, "
        "best_params_json, best_score, oos_excluded, created_at) "
        f"VALUES ('wf-search-1', 'wf-plan-1', 'fixture_strategy', 'sharpe', 'max', "
        f"'{{}}', 3, 3, '{{}}', '{{}}', 0.5, 1, '2026-08-01T00:00:00Z')"
    )
    connection.execute(search)
    with pytest.raises(sqlite3.IntegrityError):  # oos_excluded CHECK enum (0/1 only)
        connection.execute(search.replace("'wf-search-1'", "'wf-search-2'").replace("0.5, 1, '", "0.5, 2, '"))

    # --- wf_validated_strategies: FK graph + oos_evidence_fold_id UNIQUE. ---
    validated = (
        "INSERT INTO wf_validated_strategies (id, strategy_id, plan_id, search_run_id, "
        "params_sha256, oos_evidence_fold_id, resolved_asset_ids_json, validation_score, "
        "fold_evidence_json, passed_gate, created_at) "
        f"VALUES ('wf-valid-1', 'fixture_strategy', 'wf-plan-1', 'wf-search-1', "
        f"'{'d' * 64}', 'wf-fold-oos', '[]', 0.5, '{{}}', 1, '2026-08-01T00:00:00Z')"
    )
    connection.execute(validated)
    with pytest.raises(sqlite3.IntegrityError):  # oos_evidence_fold_id UNIQUE
        connection.execute(
            validated.replace("'wf-valid-1'", "'wf-valid-2'").replace("'wf-fold-oos'", "'wf-fold-1'")
        )
    with pytest.raises(sqlite3.IntegrityError):  # FK: search_run_id must exist
        connection.execute(
            validated.replace("'wf-valid-1'", "'wf-valid-3'").replace(
                "'wf-search-1'", "'missing-search'"
            )
        )
    with pytest.raises(sqlite3.IntegrityError):  # passed_gate CHECK
        connection.execute(
            validated.replace("'wf-valid-1'", "'wf-valid-4'").replace("'wf-fold-oos'", "'wf-fold-1'").replace(
                ", 1, '", ", 2, '"
            )
        )

    # --- wf_ensembles: sha256 CHECKs, standalone. ---
    ensemble = (
        "INSERT INTO wf_ensembles (id, name, strategy_ids_json, weights_json, "
        "validation_record_ids_json, input_snapshot_sha256, output_sha256, "
        "artifact_relative_path, created_at) "
        f"VALUES ('wf-ens-1', 'wf-ensemble-v1', '[]', '{{}}', '[]', '{'e' * 64}', "
        f"'{'f' * 64}', 'research_artifacts/wf-ens-1/ensemble.parquet', "
        "'2026-08-01T00:00:00Z')"
    )
    connection.execute(ensemble)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(ensemble.replace("'wf-ens-1'", "'wf-ens-2'").replace("'" + "e" * 64 + "'", "'short'"))

    # --- Immutability triggers: UPDATE/DELETE raise on every wf_* table. ---
    for table, where in (
        ("wf_plans", "id = 'wf-plan-1'"),
        ("wf_folds", "id = 'wf-fold-1'"),
        ("wf_search_runs", "id = 'wf-search-1'"),
        ("wf_validated_strategies", "id = 'wf-valid-1'"),
        ("wf_ensembles", "id = 'wf-ens-1'"),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f"UPDATE {table} SET created_at = 'x' WHERE {where}")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f"DELETE FROM {table} WHERE {where}")


def test_phase12_rebuild_preserves_phase11_run_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """option-a rebuild: existing portfolio_optimization_runs rows survive.

    Records a run under the pre-Phase-12 schema (single-value risk_model CHECK),
    then applies the FULL migration and proves the row survives column-for-column
    and the new evidence table's FK binds to the rebuilt runs table.
    """
    planned = migrations.MIGRATIONS
    evidence_index = next(
        index
        for index, script in enumerate(planned)
        if "portfolio_risk_attribution_evidence" in script
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:evidence_index])
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (evidence_index,)

    _insert_phase11_model(connection)
    connection.execute(_run_row())
    before = connection.execute(
        "SELECT * FROM portfolio_optimization_runs WHERE id = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'"
    ).fetchone()
    assert before is not None
    assert before[8] == "sample_covariance_v1"  # risk_model column

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    after = connection.execute(
        "SELECT * FROM portfolio_optimization_runs WHERE id = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'"
    ).fetchone()
    assert after is not None
    assert tuple(after) == tuple(before)

    connection.execute(
        "INSERT INTO portfolio_risk_attribution_evidence (id, attribution_type, run_id, risk_model, "
        "as_of, output_sha256, artifact_relative_path, reconciliation_json, created_at) "
        f"VALUES ('survivor-ev', 'exposure_contribution', "
        f"'a1b2c3d4e5f60718293a4b5c6d7e8f90', 'sample_covariance_v1', '2026-08-01', "
        f"'{'c' * 64}', 'research_artifacts/run-id/attribution.json', "
        "'{\"portfolio_variance\":1.0}', '2026-08-01T00:00:00Z')"
    )


def _rebalance_plan_row(
    plan_id: str = "rebalance-plan-1",
    *,
    run_id: str = "a1b2c3d4e5f60718293a4b5c6d7e8f90",
    input_sha256: str | None = None,
    rmse_definition: str = "simple",
    output_sha256: str | None = None,
) -> str:
    """Build a valid rebalance_plans INSERT statement (run FK row must exist)."""
    return (
        "INSERT INTO rebalance_plans (id, optimization_run_id, input_snapshot_sha256, as_of, "
        "target_weights_json, discrete_weights_json, lot_sizes_json, cash_residue, turnover_cost, "
        "blocked_instruments_json, discretization_rmse, rmse_definition, expires_at, output_sha256, "
        "artifact_relative_path, created_at) "
        "VALUES ("
        f"'{plan_id}', '{run_id}', "
        f"'{input_sha256 if input_sha256 is not None else '1' * 64}', "
        "'2026-08-01', '{\"600000.SH\":0.5}', '{\"600000.SH\":0.5}', "
        "'{\"600000.SH\":100}', 1000.0, 12.5, '[]', 0.01, "
        f"'{rmse_definition}', '2026-08-08T00:00:00Z', "
        f"'{output_sha256 if output_sha256 is not None else 'a' * 64}', "
        "'research_artifacts/rebalance-plan-1/rebalance.json', '2026-08-01T00:00:00Z')"
    )


def _paper_transition_row(
    transition_id: int = 1,
    *,
    plan_id: str = "rebalance-plan-1",
    transition: str = "suggested",
    idempotency_key: str = "key-1",
) -> str:
    """Build a valid paper_rebalance_transitions INSERT statement."""
    return (
        "INSERT INTO paper_rebalance_transitions (id, plan_id, transition, idempotency_key, "
        "previous_state, paper_position_delta_json, created_at) "
        "VALUES ("
        f"{transition_id}, '{plan_id}', '{transition}', '{idempotency_key}', "
        "NULL, NULL, '2026-08-01T00:00:00Z')"
    )


def test_phase14_rebalance_tables_migrate_with_constraints_and_idempotence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rebalance_plans + paper_rebalance_transitions: CHECKs + sha256 + FK + triggers."""
    planned = migrations.MIGRATIONS
    r14_index = next(
        index
        for index, script in enumerate(planned)
        if "CREATE TABLE rebalance_plans" in script
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    # Forward-only: tables absent before the Phase 14 script, present after.
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:r14_index])
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (r14_index,)
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'rebalance_plans'"
        ).fetchone()
        is None
    )

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    for table in ("rebalance_plans", "paper_rebalance_transitions"):
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            is not None
        )
    migrations.migrate_operational_db(connection)  # idempotent no-op
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)

    # --- rebalance_plans: valid row + CHECK enums + sha256 lengths + FK + PK. ---
    _insert_phase11_model(connection)
    connection.execute(_run_row())
    connection.execute(_rebalance_plan_row())
    with pytest.raises(sqlite3.IntegrityError):  # rmse_definition CHECK enum
        connection.execute(_rebalance_plan_row(plan_id="rp-bad-rmse").replace("'simple'", "'squared'"))
    with pytest.raises(sqlite3.IntegrityError):  # input_snapshot_sha256 length CHECK
        connection.execute(
            _rebalance_plan_row(plan_id="rp-bad-in-sha").replace("'" + "1" * 64 + "'", "'short'")
        )
    with pytest.raises(sqlite3.IntegrityError):  # output_sha256 length CHECK
        connection.execute(
            _rebalance_plan_row(plan_id="rp-bad-out-sha").replace("'" + "a" * 64 + "'", "'short'")
        )
    with pytest.raises(sqlite3.IntegrityError):  # FK RESTRICT: optimization_run_id must exist
        connection.execute(_rebalance_plan_row(plan_id="rp-missing-run", run_id="missing-run-id"))
    with pytest.raises(sqlite3.IntegrityError):  # duplicate plan id -> PK conflict
        connection.execute(_rebalance_plan_row(plan_id="rebalance-plan-1"))

    # --- paper_rebalance_transitions: FK + transition enum + UNIQUE idempotency. ---
    connection.execute(_paper_transition_row())
    with pytest.raises(sqlite3.IntegrityError):  # FK RESTRICT: plan_id must exist
        connection.execute(
            _paper_transition_row(transition_id=2, plan_id="missing-plan", transition="suggested")
        )
    with pytest.raises(sqlite3.IntegrityError):  # transition enum CHECK
        connection.execute(
            _paper_transition_row(
                transition_id=3, plan_id="rebalance-plan-1", transition="pending"
            )
        )
    with pytest.raises(sqlite3.IntegrityError):  # UNIQUE (plan_id, transition) idempotency
        connection.execute(
            _paper_transition_row(
                transition_id=4, plan_id="rebalance-plan-1", transition="suggested"
            )
        )
    connection.execute(  # a distinct transition is allowed under the same plan
        _paper_transition_row(
            transition_id=5, plan_id="rebalance-plan-1", transition="approved", idempotency_key="key-2"
        )
    )

    # --- Immutability triggers: UPDATE/DELETE raise on both tables. ---
    for table, where in (
        ("rebalance_plans", "id = 'rebalance-plan-1'"),
        ("paper_rebalance_transitions", "id = 1"),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f"UPDATE {table} SET created_at = 'x' WHERE {where}")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f"DELETE FROM {table} WHERE {where}")



def _alpha_snapshot_row(
    snapshot_id: str = "alpha-snap-1",
    *,
    snapshot_sha256: str | None = None,
    manifest_sha256: str | None = None,
    schema_version: str = "alpha-manifest-v1",
) -> str:
    """Build a valid research_alpha_input_snapshots INSERT statement."""
    digest = snapshot_sha256 if snapshot_sha256 is not None else "a" * 64
    manifest = manifest_sha256 if manifest_sha256 is not None else "b" * 64
    return (
        "INSERT INTO research_alpha_input_snapshots (id, schema_version, snapshot_json, "
        "snapshot_sha256, manifest_json, manifest_sha256, dsl_version, grammar_fingerprint, "
        "vocabulary_fingerprint, policy_version, policy_digest, data_fingerprint, "
        "partition_fingerprint, membership_fingerprint, code_fingerprint, build_fingerprint, "
        "dependency_fingerprint, created_at) VALUES ("
        f"'{snapshot_id}', '{schema_version}', '{{}}', '{digest}', '{{}}', '{manifest}', "
        f"'1.0', '{'c' * 64}', '{'d' * 64}', 'policy-v1', '{'e' * 64}', '{'f' * 64}', "
        f"'{'g' * 64}', '{'h' * 64}', '{'i' * 64}', '{'j' * 64}', '{'k' * 64}', "
        "'2026-08-08T00:00:00Z')"
    )


def _alpha_run_row(
    run_id: str = "alpha-run-1",
    *,
    snapshot_id: str = "alpha-snap-1",
    principal: str = "researcher@example.com",
    idempotency_key: str = "idem-key-0000000000000001",
    status: str = "queued",
    snapshot_sha256: str | None = None,
    manifest_sha256: str | None = None,
) -> str:
    """Build a valid research_alpha_runs INSERT statement (snapshot FK must exist)."""
    snap = snapshot_sha256 if snapshot_sha256 is not None else "a" * 64
    manifest = manifest_sha256 if manifest_sha256 is not None else "b" * 64
    return (
        "INSERT INTO research_alpha_runs (id, principal, idempotency_key, snapshot_id, "
        "snapshot_sha256, manifest_sha256, status, transition_version, last_event_seq, "
        "candidate_attempts_total, candidate_attempts_completed, folds_total, folds_completed, "
        "started_at, finished_at, terminal_reason, retry_of_run_id, retry_attempt, created_at) "
        "VALUES ("
        f"'{run_id}', '{principal}', '{idempotency_key}', '{snapshot_id}', '{snap}', "
        f"'{manifest}', '{status}', 0, 0, 0, 0, 0, 0, NULL, NULL, NULL, NULL, 0, "
        "'2026-08-08T00:00:00Z')"
    )


def _alpha_event_row(
    event_id: str = "alpha-evt-1",
    *,
    run_id: str = "alpha-run-1",
    seq: int = 1,
    event_type: str = "run_created",
    idempotency_key: str = "evt-key-0000000000000001",
    payload_checksum: str | None = None,
) -> str:
    """Build a valid research_alpha_events INSERT statement (run FK must exist)."""
    checksum = payload_checksum if payload_checksum is not None else "f" * 64
    return (
        "INSERT INTO research_alpha_events (id, run_id, seq, event_type, entity_kind, "
        "entity_id, occurred_at, idempotency_key, actor, source, payload_json, "
        "payload_checksum, artifact_id, producer_version, created_at) VALUES ("
        f"'{event_id}', '{run_id}', {seq}, '{event_type}', 'run', '{run_id}', "
        f"'2026-08-08T00:00:00Z', '{idempotency_key}', 'service', 'api', '{{}}', "
        f"'{checksum}', NULL, 'research-run-v1', '2026-08-08T00:00:00Z')"
    )


def test_phase45_alpha_tables_migrate_with_constraints_and_idempotence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seven Phase 45 tables: CHECKs + sha256 + FK graph + immutability + guarded cursor."""
    planned = migrations.MIGRATIONS
    p45_index = next(
        index for index, script in enumerate(planned) if "CREATE TABLE research_alpha_runs" in script
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    # Forward-only: alpha tables absent before the Phase 45 script, present after.
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:p45_index])
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (p45_index,)
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'research_alpha_runs'"
        ).fetchone()
        is None
    )

    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    for table in (
        "research_alpha_input_snapshots",
        "research_alpha_runs",
        "research_alpha_candidate_attempts",
        "research_alpha_candidate_lineage",
        "research_alpha_events",
        "research_alpha_checkpoints",
        "research_alpha_artifacts",
    ):
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            is not None
        )
    migrations.migrate_operational_db(connection)  # idempotent no-op
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)

    # --- snapshots: valid row + sha256 length CHECK + UNIQUE digest + immutability. ---
    connection.execute(_alpha_snapshot_row())
    with pytest.raises(sqlite3.IntegrityError):  # bad snapshot_sha256 length
        connection.execute(
            _alpha_snapshot_row(snapshot_id="snap-bad").replace("'" + "a" * 64 + "'", "'short'")
        )
    with pytest.raises(sqlite3.IntegrityError):  # duplicate snapshot_sha256
        connection.execute(_alpha_snapshot_row(snapshot_id="snap-dup"))
    with pytest.raises(sqlite3.IntegrityError):  # UPDATE blocked
        connection.execute("UPDATE research_alpha_input_snapshots SET dsl_version = 'x' WHERE id = 'alpha-snap-1'")
    with pytest.raises(sqlite3.IntegrityError):  # DELETE blocked
        connection.execute("DELETE FROM research_alpha_input_snapshots WHERE id = 'alpha-snap-1'")

    # --- runs: status CHECK + sha256 CHECK + FK RESTRICT + UNIQUE(principal,key). ---
    with pytest.raises(sqlite3.IntegrityError):  # FK: snapshot_id must exist
        connection.execute(_alpha_run_row(snapshot_id="missing-snap"))
    connection.execute(_alpha_run_row())
    with pytest.raises(sqlite3.IntegrityError):  # bad status enum
        connection.execute(
            _alpha_run_row(run_id="alpha-run-bad").replace("'queued'", "'pending'")
        )
    with pytest.raises(sqlite3.IntegrityError):  # duplicate (principal, idempotency_key)
        connection.execute(_alpha_run_row(run_id="alpha-run-dup"))
    with pytest.raises(sqlite3.IntegrityError):  # bad snapshot_sha256 length
        connection.execute(
            _alpha_run_row(run_id="alpha-run-short").replace("'" + "a" * 64 + "'", "'short'")
        )
    # run row is mutable only on lifecycle cursor columns.
    connection.execute(
        "UPDATE research_alpha_runs SET status = 'running', transition_version = 1, "
        "last_event_seq = 1, started_at = '2026-08-08T00:00:00Z' WHERE id = 'alpha-run-1'"
    )
    # identity columns are guarded.
    for col, value in (
        ("principal", "'other'"),
        ("idempotency_key", "'changed'"),
        ("snapshot_id", "'x'"),
        ("snapshot_sha256", "'z' * 64"),
        ("manifest_sha256", "'y' * 64"),
        ("created_at", "'mutated'"),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"UPDATE research_alpha_runs SET {col} = {value} WHERE id = 'alpha-run-1'"
            )
    with pytest.raises(sqlite3.IntegrityError):  # DELETE blocked
        connection.execute("DELETE FROM research_alpha_runs WHERE id = 'alpha-run-1'")

    # --- events: FK + UNIQUE(run_id,seq) + UNIQUE(run_id,idempotency_key) + immutability. ---
    connection.execute(_alpha_event_row())
    with pytest.raises(sqlite3.IntegrityError):  # FK: run_id must exist
        connection.execute(_alpha_event_row(event_id="evt-missing", run_id="missing-run"))
    with pytest.raises(sqlite3.IntegrityError):  # duplicate (run_id, seq)
        connection.execute(_alpha_event_row(event_id="evt-dup-seq"))
    with pytest.raises(sqlite3.IntegrityError):  # duplicate (run_id, idempotency_key)
        connection.execute(
            _alpha_event_row(event_id="evt-dup-key", seq=2, idempotency_key="evt-key-0000000000000001")
        )
    with pytest.raises(sqlite3.IntegrityError):  # bad payload_checksum length
        connection.execute(
            _alpha_event_row(event_id="evt-short", seq=3, payload_checksum="short")
        )
    with pytest.raises(sqlite3.IntegrityError):  # UPDATE blocked
        connection.execute("UPDATE research_alpha_events SET event_type = 'x' WHERE id = 'alpha-evt-1'")
    with pytest.raises(sqlite3.IntegrityError):  # DELETE blocked
        connection.execute("DELETE FROM research_alpha_events WHERE id = 'alpha-evt-1'")


def test_phase45_migration_is_atomic_and_rerunnable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing Phase 45 script rolls back all objects and user_version; rerun succeeds."""
    planned = migrations.MIGRATIONS
    p45_index = next(
        index for index, script in enumerate(planned) if "CREATE TABLE research_alpha_runs" in script
    )
    p45_script = planned[p45_index]
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(migrations, "MIGRATIONS", planned[:p45_index])
    migrations.migrate_operational_db(connection)
    pre_version = p45_index

    failing = planned[:p45_index] + (
        p45_script + "INSERT INTO injected_phase45_failure(value) VALUES ('boom');",
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", failing)
    with pytest.raises(sqlite3.OperationalError):
        migrations.migrate_operational_db(connection)
    # No Phase 45 table survived the rollback.
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'research_alpha_runs'"
        ).fetchone()
        is None
    )
    assert connection.execute("PRAGMA user_version").fetchone() == (pre_version,)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)

    # Clean rerun applies everything.
    monkeypatch.setattr(migrations, "MIGRATIONS", planned)
    migrations.migrate_operational_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone() == (len(planned),)
    assert (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'research_alpha_runs'"
        ).fetchone()
        is not None
    )