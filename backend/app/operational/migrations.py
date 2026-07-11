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
