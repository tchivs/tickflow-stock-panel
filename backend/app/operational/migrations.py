"""Versioned migrations for the operational SQLite database."""
from __future__ import annotations

import sqlite3


MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE accounts (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        available_funds REAL NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        archived_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE positions (
        id INTEGER PRIMARY KEY,
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
        instrument_symbol TEXT NOT NULL,
        cost_price REAL NOT NULL,
        quantity REAL NOT NULL,
        invested_amount REAL NOT NULL,
        trading_style TEXT NOT NULL CHECK (trading_style IN ('short', 'swing', 'long')),
        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        archived_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(account_id, instrument_symbol)
    );

    CREATE TABLE alert_references (
        id INTEGER PRIMARY KEY,
        position_id INTEGER NOT NULL REFERENCES positions(id) ON DELETE RESTRICT,
        rule_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE INDEX idx_positions_account_id ON positions(account_id);
    CREATE INDEX idx_alert_references_position_id ON alert_references(position_id);
    """,
    """
    CREATE TABLE decision_runs (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        data_as_of TEXT NOT NULL,
        engine_config_version TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE playbooks (
        run_id TEXT PRIMARY KEY REFERENCES decision_runs(id) ON DELETE RESTRICT,
        baseline_json TEXT NOT NULL,
        final_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE ai_review_proposals (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE REFERENCES decision_runs(id) ON DELETE RESTRICT,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        proposal_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE adjustment_audit (
        id INTEGER PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES decision_runs(id) ON DELETE RESTRICT,
        field TEXT NOT NULL,
        proposed_value TEXT,
        final_value TEXT,
        disposition TEXT NOT NULL CHECK (disposition IN ('applied', 'clamped', 'rejected')),
        rationale TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE replay_runs (
        id TEXT PRIMARY KEY,
        as_of TEXT NOT NULL,
        engine_config_version TEXT NOT NULL,
        provider TEXT,
        model TEXT,
        result_hash TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE INDEX idx_decision_runs_symbol_as_of ON decision_runs(symbol, data_as_of);
    CREATE INDEX idx_adjustment_audit_run_id ON adjustment_audit(run_id, id);
    CREATE INDEX idx_replay_runs_as_of ON replay_runs(as_of);
    """,
    """
    CREATE TABLE monitor_rules (
        id TEXT PRIMARY KEY,
        rule_json TEXT NOT NULL,
        enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE alert_events (
        id TEXT PRIMARY KEY,
        rule_id TEXT NOT NULL,
        source TEXT NOT NULL,
        type TEXT NOT NULL,
        symbol TEXT NOT NULL,
        name TEXT NOT NULL,
        price REAL,
        change_pct REAL,
        severity TEXT NOT NULL,
        conditions_json TEXT NOT NULL,
        account_id TEXT,
        position_id TEXT,
        valuation_source TEXT,
        valuation_as_of TEXT,
        occurred_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        event_json TEXT NOT NULL
    );

    CREATE INDEX idx_monitor_rules_updated_at ON monitor_rules(updated_at DESC);
    CREATE INDEX idx_alert_events_rule_occurred_at ON alert_events(rule_id, occurred_at DESC);
    CREATE INDEX idx_alert_events_position_occurred_at ON alert_events(position_id, occurred_at DESC);
    """,
    """
    CREATE TABLE notification_deliveries (
        id INTEGER PRIMARY KEY,
        event_id TEXT NOT NULL REFERENCES alert_events(id) ON DELETE RESTRICT,
        channel TEXT NOT NULL CHECK (channel IN ('feishu', 'telegram')),
        status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed', 'skipped')),
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(event_id, channel)
    );

    CREATE INDEX idx_notification_deliveries_event_id ON notification_deliveries(event_id, id);
    """, 
    """
    ALTER TABLE accounts ADD COLUMN notes TEXT NOT NULL DEFAULT '';
    ALTER TABLE positions ADD COLUMN notes TEXT NOT NULL DEFAULT '';
    """,
    """
    CREATE TABLE research_factor_definitions (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL
    );

    CREATE TABLE research_factor_revisions (
        id TEXT PRIMARY KEY,
        factor_id TEXT NOT NULL REFERENCES research_factor_definitions(id) ON DELETE RESTRICT,
        revision_number INTEGER NOT NULL CHECK (revision_number > 0),
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        hypothesis TEXT NOT NULL,
        canonical_expression TEXT NOT NULL,
        dsl_version TEXT NOT NULL,
        ast_signature TEXT NOT NULL,
        shape_signature TEXT NOT NULL,
        fields_json TEXT NOT NULL,
        operators_json TEXT NOT NULL,
        functions_json TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(factor_id, revision_number)
    );

    -- Reserved immutable experiment catalog tables for Phase 2 Plans 02-03.
    CREATE TABLE research_experiments (
        id TEXT PRIMARY KEY,
        factor_revision_id TEXT REFERENCES research_factor_revisions(id) ON DELETE RESTRICT,
        strategy_id TEXT,
        strategy_version TEXT,
        originating_run_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL CHECK (status IN ('draft', 'running', 'completed', 'failed', 'cancelled', 'invalid')),
        validated INTEGER NOT NULL CHECK (validated IN (0, 1)),
        retained_at TEXT,
        resolved_config_json TEXT NOT NULL,
        input_manifest_json TEXT NOT NULL,
        diagnostics_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK (
            (factor_revision_id IS NOT NULL AND strategy_id IS NULL AND strategy_version IS NULL)
            OR (factor_revision_id IS NULL AND strategy_id IS NOT NULL AND strategy_version IS NOT NULL)
        )
    );

    CREATE TABLE research_experiment_metrics (
        id INTEGER PRIMARY KEY,
        experiment_id TEXT NOT NULL REFERENCES research_experiments(id) ON DELETE RESTRICT,
        metric_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE research_experiment_artifacts (
        id INTEGER PRIMARY KEY,
        experiment_id TEXT NOT NULL REFERENCES research_experiments(id) ON DELETE RESTRICT,
        relative_path TEXT NOT NULL,
        content_type TEXT NOT NULL,
        byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
        checksum_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(experiment_id, relative_path)
    );

    CREATE TABLE research_experiment_model_provenance (
        id INTEGER PRIMARY KEY,
        experiment_id TEXT NOT NULL UNIQUE REFERENCES research_experiments(id) ON DELETE RESTRICT,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        model_version TEXT,
        provenance_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE INDEX idx_research_factor_revisions_factor ON research_factor_revisions(factor_id, revision_number);
    CREATE INDEX idx_research_factor_revisions_signature ON research_factor_revisions(ast_signature);
    CREATE INDEX idx_research_experiments_comparable ON research_experiments(status, validated, retained_at, created_at);
    CREATE INDEX idx_research_experiment_metrics_experiment ON research_experiment_metrics(experiment_id, id);
    CREATE INDEX idx_research_experiment_artifacts_experiment ON research_experiment_artifacts(experiment_id, id);
    """,
    """
    -- Evaluation evidence references are immutable JSON metadata; the managed
    -- payload bytes remain under the experiment's artifact directory.
    ALTER TABLE research_experiments
    ADD COLUMN prediction_signal_json TEXT NOT NULL DEFAULT '{}';
    """,
    """
    -- Analysis records share operational.db. Immutable facts are append-only;
    -- only an in-flight run's execution status may transition.
    CREATE TABLE analysis_runs (
        id TEXT PRIMARY KEY,
        subject_kind TEXT NOT NULL,
        subject_key TEXT NOT NULL,
        focus TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
        failure_reason TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    );

    CREATE TABLE analysis_evidence_snapshots (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE RESTRICT,
        policy_version TEXT NOT NULL,
        context_status TEXT NOT NULL CHECK (context_status IN ('ready', 'context_insufficient')),
        fingerprint TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE analysis_source_observations (
        id INTEGER PRIMARY KEY,
        snapshot_id TEXT NOT NULL REFERENCES analysis_evidence_snapshots(id) ON DELETE RESTRICT,
        source_id TEXT NOT NULL,
        grade TEXT NOT NULL CHECK (grade IN ('A', 'B', 'C')),
        origin TEXT NOT NULL,
        independence_group TEXT NOT NULL,
        retrieved_at TEXT NOT NULL,
        as_of TEXT NOT NULL,
        period TEXT NOT NULL,
        unit TEXT NOT NULL,
        definition TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(snapshot_id, source_id)
    );

    CREATE TABLE analysis_number_observations (
        id INTEGER PRIMARY KEY,
        snapshot_id TEXT NOT NULL REFERENCES analysis_evidence_snapshots(id) ON DELETE RESTRICT,
        number_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT NOT NULL,
        period TEXT NOT NULL,
        definition TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('confirmed', 'conflicting', 'unresolved', 'not_required')),
        peer_source_ids_json TEXT NOT NULL,
        comparison_reason TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(snapshot_id, number_id, source_id)
    );

    CREATE TABLE analysis_reports (
        id TEXT PRIMARY KEY,
        run_id TEXT REFERENCES analysis_runs(id) ON DELETE RESTRICT,
        subject_kind TEXT NOT NULL,
        subject_key TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        report_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(subject_kind, subject_key, version)
    );

    CREATE TABLE analysis_signals (
        id TEXT PRIMARY KEY,
        subject_kind TEXT NOT NULL,
        subject_key TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(subject_kind, subject_key)
    );

    CREATE TABLE analysis_signal_reviews (
        id TEXT PRIMARY KEY,
        signal_id TEXT NOT NULL REFERENCES analysis_signals(id) ON DELETE RESTRICT,
        prior_state TEXT NOT NULL,
        proposed_state TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE analysis_signal_events (
        id TEXT PRIMARY KEY,
        review_id TEXT NOT NULL UNIQUE REFERENCES analysis_signal_reviews(id) ON DELETE RESTRICT,
        signal_id TEXT NOT NULL REFERENCES analysis_signals(id) ON DELETE RESTRICT,
        prior_state TEXT NOT NULL,
        next_state TEXT NOT NULL,
        reviewer_principal TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE analysis_observation_plans (
        id TEXT PRIMARY KEY,
        review_id TEXT NOT NULL UNIQUE REFERENCES analysis_signal_reviews(id) ON DELETE RESTRICT,
        event_id TEXT NOT NULL UNIQUE REFERENCES analysis_signal_events(id) ON DELETE RESTRICT,
        window_days INTEGER NOT NULL CHECK (window_days IN (20, 60, 120)),
        benchmark TEXT NOT NULL,
        metric TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE analysis_observation_outcomes (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL REFERENCES analysis_observation_plans(id) ON DELETE RESTRICT,
        observed_at TEXT NOT NULL,
        outcome_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE UNIQUE INDEX idx_analysis_active_run_subject
    ON analysis_runs(subject_kind, subject_key)
    WHERE status IN ('queued', 'running');
    CREATE INDEX idx_analysis_runs_subject_created ON analysis_runs(subject_kind, subject_key, created_at DESC);
    CREATE INDEX idx_analysis_reports_subject_version ON analysis_reports(subject_kind, subject_key, version DESC);
    CREATE INDEX idx_analysis_sources_snapshot ON analysis_source_observations(snapshot_id, id);
    CREATE INDEX idx_analysis_numbers_snapshot ON analysis_number_observations(snapshot_id, id);
    CREATE INDEX idx_analysis_reviews_signal_created ON analysis_signal_reviews(signal_id, created_at);
    CREATE INDEX idx_analysis_events_signal_occurred ON analysis_signal_events(signal_id, occurred_at);
    CREATE INDEX idx_analysis_outcomes_plan_observed ON analysis_observation_outcomes(plan_id, observed_at);

    CREATE TRIGGER analysis_evidence_snapshots_no_update BEFORE UPDATE ON analysis_evidence_snapshots
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_evidence_snapshots_no_delete BEFORE DELETE ON analysis_evidence_snapshots
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_source_observations_no_update BEFORE UPDATE ON analysis_source_observations
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_source_observations_no_delete BEFORE DELETE ON analysis_source_observations
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_number_observations_no_update BEFORE UPDATE ON analysis_number_observations
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_number_observations_no_delete BEFORE DELETE ON analysis_number_observations
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_reports_no_update BEFORE UPDATE ON analysis_reports
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_reports_no_delete BEFORE DELETE ON analysis_reports
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_signal_reviews_no_update BEFORE UPDATE ON analysis_signal_reviews
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_signal_reviews_no_delete BEFORE DELETE ON analysis_signal_reviews
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_signal_events_no_update BEFORE UPDATE ON analysis_signal_events
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_signal_events_no_delete BEFORE DELETE ON analysis_signal_events
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_observation_plans_no_update BEFORE UPDATE ON analysis_observation_plans
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_observation_plans_no_delete BEFORE DELETE ON analysis_observation_plans
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_observation_outcomes_no_update BEFORE UPDATE ON analysis_observation_outcomes
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    CREATE TRIGGER analysis_observation_outcomes_no_delete BEFORE DELETE ON analysis_observation_outcomes
    BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
    """,
)


def migrate_operational_db(connection: sqlite3.Connection) -> None:
    """Apply each migration exactly once using SQLite's schema version."""
    connection.execute("PRAGMA foreign_keys = ON")
    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version > len(MIGRATIONS):
        raise RuntimeError("operational database is newer than this application")

    for version, migration in enumerate(MIGRATIONS[current_version:], start=current_version + 1):
        with connection:
            connection.executescript(migration)
            connection.execute(f"PRAGMA user_version = {version}")
