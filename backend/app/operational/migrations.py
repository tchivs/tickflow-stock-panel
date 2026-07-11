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
