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
    """
    ALTER TABLE analysis_runs ADD COLUMN audit_metadata_json TEXT;
    """,
    """
    -- Advanced records share operational.db. All business facts are append-only;
    -- advanced_jobs is the sole execution cursor with an explicitly guarded update path.
    CREATE TABLE advanced_policy_revisions (
        id TEXT PRIMARY KEY,
        revision TEXT NOT NULL,
        fingerprint TEXT NOT NULL UNIQUE,
        snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_viewpoints (
        id TEXT PRIMARY KEY,
        source_profile TEXT NOT NULL,
        market_scope TEXT NOT NULL CHECK (market_scope = 'CN-A'),
        instrument TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_viewpoint_versions (
        id TEXT PRIMARY KEY,
        viewpoint_id TEXT NOT NULL REFERENCES advanced_viewpoints(id) ON DELETE RESTRICT,
        version INTEGER NOT NULL CHECK (version > 0),
        policy_revision_id TEXT NOT NULL REFERENCES advanced_policy_revisions(id) ON DELETE RESTRICT,
        asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'etf', 'index')),
        published_at TEXT NOT NULL,
        direction TEXT NOT NULL CHECK (direction IN ('bullish', 'bearish', 'neutral')),
        rating TEXT NOT NULL CHECK (rating IN ('overweight', 'neutral', 'underweight')),
        conclusion TEXT NOT NULL,
        target_low REAL NOT NULL,
        target_high REAL NOT NULL CHECK (target_high >= target_low),
        horizon_days INTEGER NOT NULL CHECK (horizon_days BETWEEN 1 AND 365),
        confidence TEXT NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
        revision_kind TEXT NOT NULL CHECK (revision_kind IN ('initial', 'non_material_revision', 'material_stance_change', 'correction')),
        correction_reason TEXT,
        evaluation_window_days INTEGER NOT NULL CHECK (evaluation_window_days IN (20, 60, 120)),
        benchmark TEXT NOT NULL,
        metric TEXT NOT NULL CHECK (metric = 'relative_return'),
        created_at TEXT NOT NULL,
        UNIQUE(viewpoint_id, version)
    );
    CREATE TABLE advanced_viewpoint_evidence (
        id INTEGER PRIMARY KEY,
        viewpoint_version_id TEXT NOT NULL REFERENCES advanced_viewpoint_versions(id) ON DELETE RESTRICT,
        evidence_reference TEXT NOT NULL,
        evidence_published_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(viewpoint_version_id, evidence_reference)
    );
    CREATE TABLE advanced_viewpoint_evaluations (
        id TEXT PRIMARY KEY,
        viewpoint_version_id TEXT NOT NULL REFERENCES advanced_viewpoint_versions(id) ON DELETE RESTRICT,
        status TEXT NOT NULL CHECK (status IN ('evaluated', 'unevaluable')),
        reason TEXT,
        relative_return REAL,
        coverage_start TEXT,
        coverage_end TEXT,
        governed_input_fingerprint TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_experiment_specs (
        id TEXT PRIMARY KEY,
        research_asset_id TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        supersedes_specification_id TEXT REFERENCES advanced_experiment_specs(id) ON DELETE RESTRICT,
        hypothesis TEXT NOT NULL,
        data_scope_json TEXT NOT NULL,
        method TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        success_criteria_json TEXT NOT NULL,
        failure_criteria_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(research_asset_id, version)
    );
    CREATE TABLE advanced_experiment_runs (
        id TEXT PRIMARY KEY,
        specification_id TEXT NOT NULL REFERENCES advanced_experiment_specs(id) ON DELETE RESTRICT,
        status TEXT NOT NULL CHECK (status IN ('queued', 'completed', 'validation_failed', 'timed_out', 'resource_limited')),
        governed_fingerprint TEXT,
        asset_version TEXT,
        run_json TEXT NOT NULL,
        constraint_reason TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_experiment_feedback (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE REFERENCES advanced_experiment_runs(id) ON DELETE RESTRICT,
        conclusion TEXT NOT NULL CHECK (conclusion IN ('supported', 'refuted', 'inconclusive', 'needs_replication')),
        feedback_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_strategy_candidates (
        id TEXT PRIMARY KEY,
        parent_research_asset_id TEXT NOT NULL,
        parent_version TEXT NOT NULL,
        mutation_operation TEXT NOT NULL,
        seed INTEGER NOT NULL,
        resolved_configuration_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_promotion_gates (
        id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL REFERENCES advanced_strategy_candidates(id) ON DELETE RESTRICT,
        gate TEXT NOT NULL CHECK (gate IN ('contract_sandbox_safety', 'provenance', 'in_sample_out_of_sample_evidence', 'robustness', 'cost_feasibility')),
        status TEXT NOT NULL CHECK (status IN ('passed', 'failed')),
        evidence_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(candidate_id, gate)
    );
    CREATE TABLE advanced_promotions (
        id TEXT PRIMARY KEY,
        job_id TEXT UNIQUE REFERENCES advanced_jobs(id) ON DELETE RESTRICT,
        candidate_id TEXT NOT NULL UNIQUE REFERENCES advanced_strategy_candidates(id) ON DELETE RESTRICT,
        reviewer_principal TEXT NOT NULL,
        rationale TEXT NOT NULL,
        registered_strategy_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_authorizations (
        id TEXT PRIMARY KEY,
        principal TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        policy_revision_id TEXT NOT NULL REFERENCES advanced_policy_revisions(id) ON DELETE RESTRICT,
        scope_json TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_rate_windows (
        id TEXT PRIMARY KEY,
        principal TEXT NOT NULL,
        policy_revision_id TEXT NOT NULL REFERENCES advanced_policy_revisions(id) ON DELETE RESTRICT,
        window_started_at TEXT NOT NULL,
        consumed INTEGER NOT NULL CHECK (consumed >= 0),
        created_at TEXT NOT NULL,
        UNIQUE(principal, policy_revision_id, window_started_at)
    );
    CREATE TABLE advanced_jobs (
        id TEXT PRIMARY KEY,
        authorization_id TEXT NOT NULL REFERENCES advanced_authorizations(id) ON DELETE RESTRICT,
        principal TEXT NOT NULL,
        subject_kind TEXT NOT NULL,
        subject_key TEXT NOT NULL,
        task_type TEXT NOT NULL,
        market TEXT NOT NULL,
        instrument TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('queued', 'authorized', 'frozen', 'drafted', 'gates_complete', 'awaiting_review', 'recorded', 'rejected')),
        stage TEXT NOT NULL CHECK (stage IN ('authorized', 'frozen', 'drafted', 'gates_complete', 'awaiting_review', 'recorded', 'rejected')),
        stage_recorded_at TEXT NOT NULL,
        rejection_reason TEXT,
        audit_reference TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(principal, idempotency_key)
    );
    CREATE TABLE advanced_security_audit (
        id TEXT PRIMARY KEY,
        authorization_id TEXT REFERENCES advanced_authorizations(id) ON DELETE RESTRICT,
        job_id TEXT REFERENCES advanced_jobs(id) ON DELETE RESTRICT,
        reference TEXT NOT NULL UNIQUE,
        decision TEXT NOT NULL CHECK (decision IN ('authorized', 'rejected', 'recorded')),
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_sandbox_validations (
        id TEXT PRIMARY KEY,
        contract_fingerprint TEXT NOT NULL,
        source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
        status TEXT NOT NULL CHECK (status IN ('validated', 'rejected', 'constraint_failed')),
        reason TEXT NOT NULL,
        audit_reference TEXT NOT NULL REFERENCES advanced_security_audit(reference) ON DELETE RESTRICT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE advanced_sandbox_runs (
        id TEXT PRIMARY KEY,
        validation_id TEXT NOT NULL REFERENCES advanced_sandbox_validations(id) ON DELETE RESTRICT,
        runner_manifest_json TEXT NOT NULL,
        terminal_reason TEXT,
        artifact_reference TEXT,
        created_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX idx_advanced_active_job
    ON advanced_jobs(principal, task_type, market, instrument)
    WHERE status IN ('queued', 'authorized', 'frozen', 'drafted', 'gates_complete', 'awaiting_review');
    CREATE INDEX idx_advanced_viewpoint_versions ON advanced_viewpoint_versions(viewpoint_id, version DESC);
    CREATE INDEX idx_advanced_experiment_runs ON advanced_experiment_runs(specification_id, created_at DESC);
    CREATE INDEX idx_advanced_security_audit_job ON advanced_security_audit(job_id, created_at DESC);

    CREATE TRIGGER advanced_jobs_valid_transition BEFORE UPDATE ON advanced_jobs
    WHEN NOT (
        OLD.status = 'queued' AND NEW.status IN ('authorized', 'rejected')
        OR OLD.status = 'authorized' AND NEW.status IN ('frozen', 'rejected')
        OR OLD.status = 'frozen' AND NEW.status IN ('drafted', 'gates_complete', 'rejected')
        OR OLD.status = 'drafted' AND NEW.status IN ('gates_complete', 'rejected')
        OR OLD.status = 'gates_complete' AND NEW.status IN ('awaiting_review', 'recorded', 'rejected')
        OR OLD.status = 'awaiting_review' AND NEW.status IN ('recorded', 'rejected')
    )
    BEGIN SELECT RAISE(ABORT, 'advanced job cannot transition from its current state'); END;

    CREATE TRIGGER advanced_authorizations_update_only_revocation BEFORE UPDATE ON advanced_authorizations
    WHEN NEW.principal != OLD.principal OR NEW.token_hash != OLD.token_hash OR NEW.policy_revision_id != OLD.policy_revision_id
      OR NEW.scope_json != OLD.scope_json OR NEW.expires_at != OLD.expires_at OR OLD.revoked_at IS NOT NULL
    BEGIN SELECT RAISE(ABORT, 'advanced authorization is immutable except first revocation'); END;

    CREATE TRIGGER advanced_viewpoints_no_update BEFORE UPDATE ON advanced_viewpoints BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_viewpoints_no_delete BEFORE DELETE ON advanced_viewpoints BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_viewpoint_versions_no_update BEFORE UPDATE ON advanced_viewpoint_versions BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_viewpoint_versions_no_delete BEFORE DELETE ON advanced_viewpoint_versions BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_viewpoint_evidence_no_update BEFORE UPDATE ON advanced_viewpoint_evidence BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_viewpoint_evidence_no_delete BEFORE DELETE ON advanced_viewpoint_evidence BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_viewpoint_evaluations_no_update BEFORE UPDATE ON advanced_viewpoint_evaluations BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_viewpoint_evaluations_no_delete BEFORE DELETE ON advanced_viewpoint_evaluations BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_experiment_specs_no_update BEFORE UPDATE ON advanced_experiment_specs BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_experiment_specs_no_delete BEFORE DELETE ON advanced_experiment_specs BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_experiment_runs_no_update BEFORE UPDATE ON advanced_experiment_runs BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_experiment_runs_no_delete BEFORE DELETE ON advanced_experiment_runs BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_experiment_feedback_no_update BEFORE UPDATE ON advanced_experiment_feedback BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_experiment_feedback_no_delete BEFORE DELETE ON advanced_experiment_feedback BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_strategy_candidates_no_update BEFORE UPDATE ON advanced_strategy_candidates BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_strategy_candidates_no_delete BEFORE DELETE ON advanced_strategy_candidates BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_promotion_gates_no_update BEFORE UPDATE ON advanced_promotion_gates BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_promotion_gates_no_delete BEFORE DELETE ON advanced_promotion_gates BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_promotions_no_update BEFORE UPDATE ON advanced_promotions BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_promotions_no_delete BEFORE DELETE ON advanced_promotions BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_security_audit_no_update BEFORE UPDATE ON advanced_security_audit BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_security_audit_no_delete BEFORE DELETE ON advanced_security_audit BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_sandbox_validations_no_update BEFORE UPDATE ON advanced_sandbox_validations BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_sandbox_validations_no_delete BEFORE DELETE ON advanced_sandbox_validations BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_sandbox_runs_no_update BEFORE UPDATE ON advanced_sandbox_runs BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_sandbox_runs_no_delete BEFORE DELETE ON advanced_sandbox_runs BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_policy_revisions_no_update BEFORE UPDATE ON advanced_policy_revisions BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_policy_revisions_no_delete BEFORE DELETE ON advanced_policy_revisions BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_rate_windows_no_update BEFORE UPDATE ON advanced_rate_windows BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_rate_windows_no_delete BEFORE DELETE ON advanced_rate_windows BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    """,
    """
    -- Earlier advanced databases used one evaluation row per version. Rebuild the
    -- append-only ledger so a frozen plan and its eventual outcome remain distinct facts.
    DROP TRIGGER IF EXISTS advanced_viewpoint_evaluations_no_update;
    DROP TRIGGER IF EXISTS advanced_viewpoint_evaluations_no_delete;
    ALTER TABLE advanced_viewpoint_evaluations RENAME TO advanced_viewpoint_evaluations_legacy;
    CREATE TABLE advanced_viewpoint_evaluations (
        id TEXT PRIMARY KEY,
        viewpoint_version_id TEXT NOT NULL REFERENCES advanced_viewpoint_versions(id) ON DELETE RESTRICT,
        status TEXT NOT NULL CHECK (status IN ('evaluated', 'unevaluable')),
        reason TEXT,
        relative_return REAL,
        coverage_start TEXT,
        coverage_end TEXT,
        governed_input_fingerprint TEXT,
        created_at TEXT NOT NULL
    );
    INSERT INTO advanced_viewpoint_evaluations
        (id, viewpoint_version_id, status, reason, relative_return, coverage_start, coverage_end, governed_input_fingerprint, created_at)
    SELECT id, viewpoint_version_id, status, reason, relative_return, coverage_start, coverage_end, NULL, created_at
    FROM advanced_viewpoint_evaluations_legacy;
    DROP TABLE advanced_viewpoint_evaluations_legacy;
    CREATE TRIGGER advanced_viewpoint_evaluations_no_update BEFORE UPDATE ON advanced_viewpoint_evaluations BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_viewpoint_evaluations_no_delete BEFORE DELETE ON advanced_viewpoint_evaluations BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    """,
    """
    -- Rate windows are security accounting state: identity and window are immutable,
    -- while consumption may only advance within that exact persisted window.
    DROP TRIGGER advanced_rate_windows_no_update;
    CREATE TRIGGER advanced_rate_windows_monotonic_consumption BEFORE UPDATE ON advanced_rate_windows
    WHEN NEW.id != OLD.id OR NEW.principal != OLD.principal OR NEW.policy_revision_id != OLD.policy_revision_id
      OR NEW.window_started_at != OLD.window_started_at OR NEW.created_at != OLD.created_at OR NEW.consumed <= OLD.consumed
    BEGIN SELECT RAISE(ABORT, 'advanced rate consumption must increase within its immutable window'); END;
    """,
    """
    -- Opaque experiment records need a server-resolved owner before API disclosure.
    ALTER TABLE advanced_experiment_specs ADD COLUMN owner_principal TEXT NOT NULL DEFAULT '';
    CREATE INDEX idx_advanced_experiment_specs_owner ON advanced_experiment_specs(owner_principal, created_at DESC);
    """,
    """
    -- Sandbox validation lineage is immutable. The parent asset remains an opaque
    -- server-authorized identifier; validation-to-run foreign keys already enforce
    -- the durable relation between this fact and every terminal run.
    ALTER TABLE advanced_sandbox_validations ADD COLUMN parent_asset_id TEXT NOT NULL DEFAULT '';
    CREATE INDEX idx_advanced_sandbox_validations_parent_created
    ON advanced_sandbox_validations(parent_asset_id, created_at DESC);
    """,
    """
    -- A deployment policy version is descriptive, not a unique fact identity. Rebuild
    -- the fact table so the immutable content fingerprint is the sole reuse key.
    PRAGMA foreign_keys = OFF;
    CREATE TABLE advanced_policy_revisions_rebuilt (
        id TEXT PRIMARY KEY,
        revision TEXT NOT NULL,
        fingerprint TEXT NOT NULL UNIQUE,
        snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    INSERT INTO advanced_policy_revisions_rebuilt (id, revision, fingerprint, snapshot_json, created_at)
    SELECT id, revision, fingerprint, snapshot_json, created_at
    FROM advanced_policy_revisions;
    DROP TABLE advanced_policy_revisions;
    ALTER TABLE advanced_policy_revisions_rebuilt RENAME TO advanced_policy_revisions;
    CREATE TRIGGER advanced_policy_revisions_no_update BEFORE UPDATE ON advanced_policy_revisions
    BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_policy_revisions_no_delete BEFORE DELETE ON advanced_policy_revisions
    BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    PRAGMA foreign_keys = ON;
    """,
    """
    -- Pre-remediation policy facts can contain a partial snapshot whose fingerprint
    -- was derived from the complete policy. Preserve those immutable bytes and
    -- foreign-key targets under a legacy schema identity, so a self-verifying
    -- current fact with the same historical fingerprint mints a distinct row.
    PRAGMA foreign_keys = OFF;
    CREATE TABLE advanced_policy_revisions_rebuilt (
        id TEXT PRIMARY KEY,
        revision TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        fact_schema_version TEXT NOT NULL DEFAULT 'advanced_policy_snapshot_legacy_v1',
        snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(fingerprint, fact_schema_version)
    );
    INSERT INTO advanced_policy_revisions_rebuilt
        (id, revision, fingerprint, fact_schema_version, snapshot_json, created_at)
    SELECT id, revision, fingerprint, 'advanced_policy_snapshot_legacy_v1', snapshot_json, created_at
    FROM advanced_policy_revisions;
    DROP TABLE advanced_policy_revisions;
    ALTER TABLE advanced_policy_revisions_rebuilt RENAME TO advanced_policy_revisions;
    CREATE TRIGGER advanced_policy_revisions_no_update BEFORE UPDATE ON advanced_policy_revisions
    BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    CREATE TRIGGER advanced_policy_revisions_no_delete BEFORE DELETE ON advanced_policy_revisions
    BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
    PRAGMA foreign_keys = ON;
    """,
    """
    -- A lifecycle-selected installed strategy resolves to exactly one immutable
    -- factor revision. The binding never accepts a browser-selected revision.
    CREATE TABLE research_strategy_asset_bindings (
        strategy_id TEXT PRIMARY KEY,
        research_asset_id TEXT NOT NULL UNIQUE REFERENCES research_factor_revisions(id) ON DELETE RESTRICT,
        provenance_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TRIGGER research_strategy_asset_bindings_no_update BEFORE UPDATE ON research_strategy_asset_bindings
    BEGIN SELECT RAISE(ABORT, 'research strategy asset bindings are immutable'); END;
    CREATE TRIGGER research_strategy_asset_bindings_no_delete BEFORE DELETE ON research_strategy_asset_bindings
    BEGIN SELECT RAISE(ABORT, 'research strategy asset bindings are immutable'); END;
    """,
    """
    -- New specifications preserve the server-resolved installed strategy that owns
    -- their immutable research asset. Existing facts retain the empty legacy value.
    ALTER TABLE advanced_experiment_specs ADD COLUMN bound_strategy_id TEXT NOT NULL DEFAULT '';
    CREATE INDEX idx_advanced_experiment_specs_bound_strategy
    ON advanced_experiment_specs(bound_strategy_id, created_at DESC);
    """,
    """
    -- Task type is an immutable part of durable rate-window identity. Historical
    -- aggregate rows retain their evidence under a reserved identity that current
    -- authorization can never validate or consume.
    ALTER TABLE advanced_rate_windows RENAME TO advanced_rate_windows_legacy;
    CREATE TABLE advanced_rate_windows (
        id TEXT PRIMARY KEY,
        principal TEXT NOT NULL,
        policy_revision_id TEXT NOT NULL REFERENCES advanced_policy_revisions(id) ON DELETE RESTRICT,
        task_type TEXT NOT NULL CHECK (length(trim(task_type)) > 0),
        window_started_at TEXT NOT NULL,
        consumed INTEGER NOT NULL CHECK (consumed >= 0),
        created_at TEXT NOT NULL,
        UNIQUE(principal, policy_revision_id, task_type, window_started_at)
    );
    INSERT INTO advanced_rate_windows
        (id, principal, policy_revision_id, task_type, window_started_at, consumed, created_at)
    SELECT id, principal, policy_revision_id, '__legacy_rate_window__', window_started_at, consumed, created_at
    FROM advanced_rate_windows_legacy;
    DROP TABLE advanced_rate_windows_legacy;
    CREATE TRIGGER advanced_rate_windows_monotonic_consumption BEFORE UPDATE ON advanced_rate_windows
    WHEN NEW.id != OLD.id OR NEW.principal != OLD.principal OR NEW.policy_revision_id != OLD.policy_revision_id
      OR NEW.task_type != OLD.task_type OR NEW.window_started_at != OLD.window_started_at OR NEW.created_at != OLD.created_at
      OR NEW.consumed <= OLD.consumed
    BEGIN SELECT RAISE(ABORT, 'advanced rate consumption must increase within its immutable window'); END;
    """,
    """
    -- Phase 05 shares operational.db across three independently optional domains.
    -- Business/evidence rows are immutable; only schedules, global leases, and
    -- forecast jobs expose narrowly guarded recovery-cursor updates.
    CREATE TABLE shadow_import_batches (
        id TEXT PRIMARY KEY,
        principal TEXT NOT NULL,
        raw_artifact_descriptor_json TEXT NOT NULL,
        content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
        source_label TEXT NOT NULL,
        importer_version TEXT NOT NULL,
        mapping_version TEXT NOT NULL,
        supersedes_batch_id TEXT REFERENCES shadow_import_batches(id) ON DELETE RESTRICT,
        source_row_count INTEGER NOT NULL CHECK (source_row_count >= 0),
        normalized_row_count INTEGER NOT NULL CHECK (normalized_row_count >= 0),
        rejected_row_count INTEGER NOT NULL CHECK (rejected_row_count >= 0),
        diagnostics_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('completed', 'rejected')),
        created_at TEXT NOT NULL
    );
    CREATE TABLE shadow_trade_facts (
        id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL REFERENCES shadow_import_batches(id) ON DELETE RESTRICT,
        row_identity TEXT NOT NULL,
        duplicate_group_hash TEXT NOT NULL CHECK (length(duplicate_group_hash) = 64),
        broker_fill_id TEXT,
        account_alias TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
        executed_at TEXT NOT NULL,
        quantity REAL NOT NULL CHECK (quantity > 0),
        price REAL NOT NULL CHECK (price >= 0),
        fees REAL NOT NULL CHECK (fees >= 0),
        currency TEXT NOT NULL,
        source_row_ordinal INTEGER NOT NULL CHECK (source_row_ordinal > 0),
        source_values_json TEXT NOT NULL,
        normalized_payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(batch_id, row_identity),
        UNIQUE(batch_id, source_row_ordinal)
    );
    CREATE TABLE shadow_evidence_sets (
        id TEXT PRIMARY KEY,
        principal TEXT NOT NULL,
        fingerprint TEXT NOT NULL CHECK (length(fingerprint) = 64),
        manifest_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(principal, fingerprint)
    );
    CREATE TABLE shadow_evidence_batches (
        evidence_set_id TEXT NOT NULL REFERENCES shadow_evidence_sets(id) ON DELETE RESTRICT,
        batch_id TEXT NOT NULL REFERENCES shadow_import_batches(id) ON DELETE RESTRICT,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        created_at TEXT NOT NULL,
        PRIMARY KEY(evidence_set_id, batch_id),
        UNIQUE(evidence_set_id, ordinal)
    );
    CREATE TABLE shadow_evidence_members (
        evidence_set_id TEXT NOT NULL REFERENCES shadow_evidence_sets(id) ON DELETE RESTRICT,
        trade_id TEXT NOT NULL REFERENCES shadow_trade_facts(id) ON DELETE RESTRICT,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        created_at TEXT NOT NULL,
        PRIMARY KEY(evidence_set_id, trade_id),
        UNIQUE(evidence_set_id, ordinal)
    );
    CREATE TABLE shadow_evidence_exclusions (
        id TEXT PRIMARY KEY,
        evidence_set_id TEXT NOT NULL REFERENCES shadow_evidence_sets(id) ON DELETE RESTRICT,
        trade_id TEXT NOT NULL REFERENCES shadow_trade_facts(id) ON DELETE RESTRICT,
        reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
        created_at TEXT NOT NULL,
        UNIQUE(evidence_set_id, trade_id)
    );
    CREATE TABLE shadow_candidates (
        id TEXT PRIMARY KEY,
        evidence_set_id TEXT NOT NULL REFERENCES shadow_evidence_sets(id) ON DELETE RESTRICT,
        distiller_version TEXT NOT NULL,
        rule_schema_version TEXT NOT NULL,
        rules_json TEXT NOT NULL,
        features_json TEXT NOT NULL,
        parameters_json TEXT NOT NULL,
        exit_assumptions_json TEXT NOT NULL,
        holding_assumptions_json TEXT NOT NULL,
        source_batch_ids_json TEXT NOT NULL,
        evidence_set_fingerprint TEXT NOT NULL CHECK (length(evidence_set_fingerprint) = 64),
        training_window_json TEXT NOT NULL,
        seed INTEGER NOT NULL,
        class_balance_json TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        limitations_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(evidence_set_id, distiller_version, rule_schema_version, seed)
    );
    CREATE TABLE shadow_candidate_runs (
        id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL REFERENCES shadow_candidates(id) ON DELETE RESTRICT,
        attempt INTEGER NOT NULL CHECK (attempt > 0),
        governed_fingerprint TEXT NOT NULL CHECK (length(governed_fingerprint) = 64),
        runner_manifest_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'timed_out', 'resource_limited', 'interrupted')),
        terminal_reason TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(candidate_id, attempt)
    );
    CREATE TABLE shadow_candidate_evaluations (
        id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL REFERENCES shadow_candidates(id) ON DELETE RESTRICT,
        run_id TEXT NOT NULL REFERENCES shadow_candidate_runs(id) ON DELETE RESTRICT,
        split_kind TEXT NOT NULL CHECK (split_kind IN ('in_sample', 'out_of_sample')),
        window_start TEXT NOT NULL,
        window_end TEXT NOT NULL CHECK (window_end >= window_start),
        governed_fingerprint TEXT NOT NULL CHECK (length(governed_fingerprint) = 64),
        artifact_descriptor_json TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'timed_out', 'resource_limited', 'interrupted')),
        terminal_reason TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(candidate_id, split_kind, run_id)
    );
    CREATE TABLE shadow_retention_events (
        id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL REFERENCES shadow_candidates(id) ON DELETE RESTRICT,
        in_sample_evaluation_id TEXT NOT NULL REFERENCES shadow_candidate_evaluations(id) ON DELETE RESTRICT,
        out_of_sample_evaluation_id TEXT NOT NULL REFERENCES shadow_candidate_evaluations(id) ON DELETE RESTRICT,
        reviewer_principal TEXT NOT NULL,
        rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
        status TEXT NOT NULL CHECK (status = 'retained_research_only'),
        created_at TEXT NOT NULL,
        UNIQUE(candidate_id, in_sample_evaluation_id, out_of_sample_evaluation_id)
    );

    CREATE TABLE theses (
        id TEXT PRIMARY KEY,
        instrument TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(instrument)
    );
    CREATE TABLE thesis_versions (
        id TEXT PRIMARY KEY,
        thesis_id TEXT NOT NULL REFERENCES theses(id) ON DELETE RESTRICT,
        version INTEGER NOT NULL CHECK (version > 0),
        predecessor_id TEXT,
        core_judgment TEXT NOT NULL,
        rationale TEXT NOT NULL,
        change_reason TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(thesis_id, version),
        UNIQUE(thesis_id, id),
        FOREIGN KEY(thesis_id, predecessor_id)
            REFERENCES thesis_versions(thesis_id, id) ON DELETE RESTRICT
    );
    CREATE TABLE thesis_valuation_anchors (
        id TEXT PRIMARY KEY,
        version_id TEXT NOT NULL REFERENCES thesis_versions(id) ON DELETE RESTRICT,
        method TEXT NOT NULL,
        currency TEXT NOT NULL,
        as_of TEXT NOT NULL,
        low REAL NOT NULL,
        high REAL NOT NULL CHECK (high >= low),
        assumptions_json TEXT NOT NULL,
        limitations_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE thesis_conditions (
        id TEXT PRIMARY KEY,
        version_id TEXT NOT NULL REFERENCES thesis_versions(id) ON DELETE RESTRICT,
        copied_from_condition_id TEXT REFERENCES thesis_conditions(id) ON DELETE RESTRICT,
        source_kind TEXT NOT NULL CHECK (source_kind IN ('market', 'financial', 'analysis')),
        field TEXT NOT NULL,
        operator TEXT NOT NULL,
        threshold_json TEXT NOT NULL,
        unit TEXT NOT NULL,
        lookback_days INTEGER NOT NULL CHECK (lookback_days > 0),
        cadence TEXT NOT NULL CHECK (cadence IN ('daily', 'weekly', 'monthly', 'quarterly')),
        timezone TEXT NOT NULL,
        description TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(version_id, id)
    );
    CREATE TABLE thesis_condition_schedules (
        condition_id TEXT PRIMARY KEY REFERENCES thesis_conditions(id) ON DELETE RESTRICT,
        active INTEGER NOT NULL CHECK (active IN (0, 1)),
        next_due_at TEXT NOT NULL,
        lease_owner TEXT,
        lease_until TEXT,
        last_attempt_at TEXT,
        transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK ((lease_owner IS NULL) = (lease_until IS NULL))
    );
    CREATE TABLE thesis_condition_checks (
        id TEXT PRIMARY KEY,
        version_id TEXT NOT NULL,
        condition_id TEXT NOT NULL,
        due_at TEXT NOT NULL,
        result TEXT NOT NULL CHECK (result IN ('matched', 'not_matched', 'insufficient_evidence', 'error')),
        observed_value_json TEXT,
        evidence_fingerprint TEXT NOT NULL CHECK (length(evidence_fingerprint) = 64),
        evidence_json TEXT NOT NULL,
        safe_reason TEXT,
        checked_at TEXT NOT NULL,
        UNIQUE(condition_id, due_at),
        FOREIGN KEY(version_id, condition_id)
            REFERENCES thesis_conditions(version_id, id) ON DELETE RESTRICT
    );
    CREATE TABLE thesis_pending_conclusions (
        id TEXT PRIMARY KEY,
        thesis_id TEXT NOT NULL REFERENCES theses(id) ON DELETE RESTRICT,
        version_id TEXT NOT NULL REFERENCES thesis_versions(id) ON DELETE RESTRICT,
        condition_id TEXT NOT NULL REFERENCES thesis_conditions(id) ON DELETE RESTRICT,
        check_id TEXT NOT NULL UNIQUE REFERENCES thesis_condition_checks(id) ON DELETE RESTRICT,
        evidence_fingerprint TEXT NOT NULL CHECK (length(evidence_fingerprint) = 64),
        proposed_state TEXT NOT NULL CHECK (proposed_state = 'invalidated'),
        reason TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status = 'pending'),
        created_at TEXT NOT NULL
    );
    CREATE TABLE thesis_review_events (
        id TEXT PRIMARY KEY,
        pending_id TEXT NOT NULL UNIQUE REFERENCES thesis_pending_conclusions(id) ON DELETE RESTRICT,
        decision TEXT NOT NULL CHECK (decision IN ('confirmed', 'rejected')),
        reviewer_principal TEXT NOT NULL,
        rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
        created_at TEXT NOT NULL
    );

    CREATE TABLE forecast_jobs (
        id TEXT PRIMARY KEY,
        principal TEXT NOT NULL,
        instrument_id TEXT NOT NULL,
        horizon INTEGER NOT NULL CHECK (horizon IN (5, 20, 60)),
        catalog_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        input_fingerprint TEXT NOT NULL CHECK (length(input_fingerprint) = 64),
        status TEXT NOT NULL CHECK (status IN (
            'queued', 'running', 'completed', 'validation_failed', 'model_unavailable',
            'artifact_failed', 'timed_out', 'resource_limited', 'interrupted'
        )),
        transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
        retry_of_job_id TEXT REFERENCES forecast_jobs(id) ON DELETE RESTRICT,
        attempt INTEGER NOT NULL CHECK (attempt > 0),
        lease_owner TEXT,
        lease_until TEXT,
        terminal_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(principal, instrument_id, horizon, catalog_id, idempotency_key),
        CHECK ((lease_owner IS NULL) = (lease_until IS NULL))
    );
    CREATE TABLE forecast_global_leases (
        lease_name TEXT PRIMARY KEY CHECK (lease_name = 'forecast-inference'),
        lease_owner TEXT,
        lease_until TEXT,
        transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
        updated_at TEXT NOT NULL,
        CHECK ((lease_owner IS NULL) = (lease_until IS NULL))
    );
    INSERT INTO forecast_global_leases
        (lease_name, lease_owner, lease_until, transition_version, updated_at)
    VALUES ('forecast-inference', NULL, NULL, 0, '');
    CREATE TABLE forecast_records (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL UNIQUE REFERENCES forecast_jobs(id) ON DELETE RESTRICT,
        instrument_id TEXT NOT NULL,
        origin_session_id TEXT NOT NULL,
        calendar_id TEXT NOT NULL,
        calendar_revision TEXT NOT NULL,
        future_session_ids_json TEXT NOT NULL,
        input_fingerprint TEXT NOT NULL CHECK (length(input_fingerprint) = 64),
        input_artifact_descriptor_json TEXT NOT NULL,
        horizon INTEGER NOT NULL CHECK (horizon IN (5, 20, 60)),
        lookback INTEGER NOT NULL CHECK (lookback > 0),
        seed INTEGER NOT NULL,
        temperature REAL NOT NULL CHECK (temperature > 0),
        top_k INTEGER NOT NULL CHECK (top_k > 0),
        top_p REAL NOT NULL CHECK (top_p > 0 AND top_p <= 1),
        sample_count INTEGER NOT NULL CHECK (sample_count = 32),
        catalog_id TEXT NOT NULL,
        source_revision TEXT NOT NULL,
        source_digest_sha256 TEXT NOT NULL CHECK (length(source_digest_sha256) = 64),
        model_revision TEXT NOT NULL,
        model_digest_sha256 TEXT NOT NULL CHECK (length(model_digest_sha256) = 64),
        tokenizer_revision TEXT NOT NULL,
        tokenizer_digest_sha256 TEXT NOT NULL CHECK (length(tokenizer_digest_sha256) = 64),
        output_artifact_descriptor_json TEXT NOT NULL,
        paths_checksum_sha256 TEXT NOT NULL CHECK (length(paths_checksum_sha256) = 64),
        validation_warnings_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE forecast_outcomes (
        id TEXT PRIMARY KEY,
        forecast_id TEXT NOT NULL REFERENCES forecast_records(id) ON DELETE RESTRICT,
        horizon INTEGER NOT NULL CHECK (horizon IN (5, 20, 60)),
        status TEXT NOT NULL CHECK (status IN ('evaluated', 'unevaluable')),
        actual_session_id TEXT,
        actual_value_json TEXT,
        actual_fingerprint TEXT,
        reason TEXT,
        observed_at TEXT NOT NULL,
        UNIQUE(forecast_id, horizon),
        CHECK (actual_fingerprint IS NULL OR length(actual_fingerprint) = 64)
    );
    CREATE TABLE forecast_calibration_facts (
        id TEXT PRIMARY KEY,
        forecast_id TEXT NOT NULL REFERENCES forecast_records(id) ON DELETE RESTRICT,
        outcome_id TEXT NOT NULL UNIQUE REFERENCES forecast_outcomes(id) ON DELETE RESTRICT,
        metric_schema TEXT NOT NULL,
        close_mae REAL,
        p10_p90_interval_covered INTEGER CHECK (p10_p90_interval_covered IN (0, 1)),
        p10_pinball_loss REAL,
        p50_pinball_loss REAL,
        p90_pinball_loss REAL,
        coverage_start TEXT,
        coverage_end TEXT,
        created_at TEXT NOT NULL
    );

    CREATE INDEX idx_shadow_trade_facts_batch ON shadow_trade_facts(batch_id, source_row_ordinal);
    CREATE INDEX idx_shadow_evidence_sets_principal ON shadow_evidence_sets(principal, created_at DESC);
    CREATE INDEX idx_shadow_candidates_evidence ON shadow_candidates(evidence_set_id, created_at DESC);
    CREATE INDEX idx_shadow_candidate_runs_candidate ON shadow_candidate_runs(candidate_id, attempt DESC);
    CREATE INDEX idx_shadow_candidate_evaluations_candidate ON shadow_candidate_evaluations(candidate_id, split_kind, created_at DESC);
    CREATE INDEX idx_thesis_versions_thesis ON thesis_versions(thesis_id, version DESC);
    CREATE INDEX idx_thesis_conditions_version ON thesis_conditions(version_id, created_at);
    CREATE INDEX idx_thesis_condition_schedules_due ON thesis_condition_schedules(active, next_due_at, condition_id);
    CREATE INDEX idx_thesis_condition_checks_condition ON thesis_condition_checks(condition_id, due_at DESC);
    CREATE INDEX idx_thesis_pending_thesis ON thesis_pending_conclusions(thesis_id, created_at DESC);
    CREATE INDEX idx_forecast_jobs_status ON forecast_jobs(status, created_at, id);
    CREATE INDEX idx_forecast_jobs_lease ON forecast_jobs(status, lease_until, id);
    CREATE INDEX idx_forecast_records_instrument ON forecast_records(instrument_id, created_at DESC);
    CREATE INDEX idx_forecast_outcomes_forecast ON forecast_outcomes(forecast_id, horizon);

    CREATE TRIGGER thesis_condition_schedules_guarded_update
    BEFORE UPDATE ON thesis_condition_schedules
    WHEN NEW.condition_id IS NOT OLD.condition_id
      OR NEW.created_at IS NOT OLD.created_at
      OR NEW.active > OLD.active
      OR NEW.next_due_at < OLD.next_due_at
      OR NEW.transition_version != OLD.transition_version + 1
      OR NEW.updated_at < OLD.updated_at
      OR ((NEW.lease_owner IS NULL) != (NEW.lease_until IS NULL))
      OR (NEW.lease_owner IS NOT NULL AND OLD.lease_owner IS NOT NULL
          AND NEW.lease_owner IS NOT OLD.lease_owner)
      OR (NEW.lease_until IS NOT NULL AND OLD.lease_until IS NOT NULL
          AND NEW.lease_until < OLD.lease_until)
      OR (NEW.last_attempt_at IS NOT NULL AND OLD.last_attempt_at IS NOT NULL
          AND NEW.last_attempt_at < OLD.last_attempt_at)
    BEGIN SELECT RAISE(ABORT, 'thesis schedule cursor must advance monotonically'); END;
    CREATE TRIGGER thesis_condition_schedules_no_delete
    BEFORE DELETE ON thesis_condition_schedules
    BEGIN SELECT RAISE(ABORT, 'thesis schedule cursor is immutable'); END;

    CREATE TRIGGER forecast_jobs_guarded_columns
    BEFORE UPDATE ON forecast_jobs
    WHEN NEW.id IS NOT OLD.id OR NEW.principal IS NOT OLD.principal
      OR NEW.instrument_id IS NOT OLD.instrument_id OR NEW.horizon IS NOT OLD.horizon
      OR NEW.catalog_id IS NOT OLD.catalog_id OR NEW.idempotency_key IS NOT OLD.idempotency_key
      OR NEW.input_fingerprint IS NOT OLD.input_fingerprint
      OR NEW.retry_of_job_id IS NOT OLD.retry_of_job_id OR NEW.attempt IS NOT OLD.attempt
      OR NEW.created_at IS NOT OLD.created_at
      OR NEW.transition_version != OLD.transition_version + 1
      OR NEW.updated_at < OLD.updated_at
      OR ((NEW.lease_owner IS NULL) != (NEW.lease_until IS NULL))
      OR (OLD.status = 'running' AND NEW.status = 'running'
          AND NEW.lease_owner IS NOT OLD.lease_owner)
    BEGIN SELECT RAISE(ABORT, 'forecast job cursor cannot mutate immutable columns'); END;
    CREATE TRIGGER forecast_jobs_valid_transition
    BEFORE UPDATE ON forecast_jobs
    WHEN NOT (
        OLD.status = 'queued' AND NEW.status = 'running'
        OR OLD.status = 'queued' AND NEW.status IN ('validation_failed', 'model_unavailable', 'interrupted')
        OR OLD.status = 'running' AND NEW.status = 'running'
        OR OLD.status = 'running' AND NEW.status IN (
            'completed', 'validation_failed', 'model_unavailable', 'artifact_failed',
            'timed_out', 'resource_limited', 'interrupted'
        )
    )
    BEGIN SELECT RAISE(ABORT, 'forecast job cannot transition from its current state'); END;
    CREATE TRIGGER forecast_jobs_no_delete
    BEFORE DELETE ON forecast_jobs
    BEGIN SELECT RAISE(ABORT, 'forecast jobs are immutable after terminal state'); END;

    CREATE TRIGGER forecast_global_leases_guarded_update
    BEFORE UPDATE ON forecast_global_leases
    WHEN NEW.lease_name IS NOT OLD.lease_name
      OR NEW.transition_version != OLD.transition_version + 1
      OR NEW.updated_at < OLD.updated_at
      OR ((NEW.lease_owner IS NULL) != (NEW.lease_until IS NULL))
      OR (NEW.lease_until IS NOT NULL AND OLD.lease_until IS NOT NULL
          AND NEW.lease_until < OLD.lease_until)
    BEGIN SELECT RAISE(ABORT, 'forecast global lease cursor must advance monotonically'); END;
    CREATE TRIGGER forecast_global_leases_no_delete
    BEFORE DELETE ON forecast_global_leases
    BEGIN SELECT RAISE(ABORT, 'forecast global lease cursor is immutable'); END;

    CREATE TRIGGER shadow_import_batches_no_update BEFORE UPDATE ON shadow_import_batches BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_import_batches_no_delete BEFORE DELETE ON shadow_import_batches BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_trade_facts_no_update BEFORE UPDATE ON shadow_trade_facts BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_trade_facts_no_delete BEFORE DELETE ON shadow_trade_facts BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evidence_sets_no_update BEFORE UPDATE ON shadow_evidence_sets BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evidence_sets_no_delete BEFORE DELETE ON shadow_evidence_sets BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evidence_batches_no_update BEFORE UPDATE ON shadow_evidence_batches BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evidence_batches_no_delete BEFORE DELETE ON shadow_evidence_batches BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evidence_members_no_update BEFORE UPDATE ON shadow_evidence_members BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evidence_members_no_delete BEFORE DELETE ON shadow_evidence_members BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evidence_exclusions_no_update BEFORE UPDATE ON shadow_evidence_exclusions BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evidence_exclusions_no_delete BEFORE DELETE ON shadow_evidence_exclusions BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_candidates_no_update BEFORE UPDATE ON shadow_candidates BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_candidates_no_delete BEFORE DELETE ON shadow_candidates BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_candidate_runs_no_update BEFORE UPDATE ON shadow_candidate_runs BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_candidate_runs_no_delete BEFORE DELETE ON shadow_candidate_runs BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_candidate_evaluations_no_update BEFORE UPDATE ON shadow_candidate_evaluations BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_candidate_evaluations_no_delete BEFORE DELETE ON shadow_candidate_evaluations BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_retention_events_no_update BEFORE UPDATE ON shadow_retention_events BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_retention_events_no_delete BEFORE DELETE ON shadow_retention_events BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER theses_no_update BEFORE UPDATE ON theses BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER theses_no_delete BEFORE DELETE ON theses BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_versions_no_update BEFORE UPDATE ON thesis_versions BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_versions_no_delete BEFORE DELETE ON thesis_versions BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_valuation_anchors_no_update BEFORE UPDATE ON thesis_valuation_anchors BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_valuation_anchors_no_delete BEFORE DELETE ON thesis_valuation_anchors BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_conditions_no_update BEFORE UPDATE ON thesis_conditions BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_conditions_no_delete BEFORE DELETE ON thesis_conditions BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_condition_checks_no_update BEFORE UPDATE ON thesis_condition_checks BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_condition_checks_no_delete BEFORE DELETE ON thesis_condition_checks BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_pending_conclusions_no_update BEFORE UPDATE ON thesis_pending_conclusions BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_pending_conclusions_no_delete BEFORE DELETE ON thesis_pending_conclusions BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_review_events_no_update BEFORE UPDATE ON thesis_review_events BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER thesis_review_events_no_delete BEFORE DELETE ON thesis_review_events BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER forecast_records_no_update BEFORE UPDATE ON forecast_records BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER forecast_records_no_delete BEFORE DELETE ON forecast_records BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER forecast_outcomes_no_update BEFORE UPDATE ON forecast_outcomes BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER forecast_outcomes_no_delete BEFORE DELETE ON forecast_outcomes BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER forecast_calibration_facts_no_update BEFORE UPDATE ON forecast_calibration_facts BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER forecast_calibration_facts_no_delete BEFORE DELETE ON forecast_calibration_facts BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    """,
    """
    CREATE TABLE shadow_candidate_request_identities (
        logical_key_digest TEXT PRIMARY KEY CHECK (length(logical_key_digest) = 64),
        request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
        candidate_id TEXT NOT NULL UNIQUE REFERENCES shadow_candidates(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE shadow_retention_decision_identities (
        logical_key_digest TEXT PRIMARY KEY CHECK (length(logical_key_digest) = 64),
        decision_digest TEXT NOT NULL CHECK (length(decision_digest) = 64),
        retention_event_id TEXT NOT NULL UNIQUE REFERENCES shadow_retention_events(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL
    );
    CREATE TRIGGER shadow_candidate_request_identities_no_update
    BEFORE UPDATE ON shadow_candidate_request_identities
    BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_candidate_request_identities_no_delete
    BEFORE DELETE ON shadow_candidate_request_identities
    BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_retention_decision_identities_no_update
    BEFORE UPDATE ON shadow_retention_decision_identities
    BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_retention_decision_identities_no_delete
    BEFORE DELETE ON shadow_retention_decision_identities
    BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    """,
    """
    CREATE TABLE shadow_evaluation_pairs (
        id TEXT PRIMARY KEY,
        pair_key_digest TEXT NOT NULL UNIQUE CHECK (length(pair_key_digest) = 64),
        pair_digest TEXT NOT NULL CHECK (length(pair_digest) = 64),
        candidate_id TEXT NOT NULL REFERENCES shadow_candidates(id) ON DELETE RESTRICT,
        evidence_set_id TEXT NOT NULL REFERENCES shadow_evidence_sets(id) ON DELETE RESTRICT,
        evidence_set_fingerprint TEXT NOT NULL CHECK (length(evidence_set_fingerprint) = 64),
        in_sample_window_json TEXT NOT NULL,
        out_of_sample_window_json TEXT NOT NULL,
        adjustment_policy TEXT NOT NULL,
        cost_policy_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE shadow_evaluation_attempts (
        id TEXT PRIMARY KEY,
        pair_id TEXT REFERENCES shadow_evaluation_pairs(id) ON DELETE RESTRICT,
        run_id TEXT NOT NULL UNIQUE REFERENCES shadow_candidate_runs(id) ON DELETE RESTRICT,
        candidate_id TEXT NOT NULL REFERENCES shadow_candidates(id) ON DELETE RESTRICT,
        split_kind TEXT NOT NULL CHECK (split_kind IN ('in_sample', 'out_of_sample')),
        attempt INTEGER NOT NULL CHECK (attempt > 0),
        retry_of_evaluation_id TEXT REFERENCES shadow_evaluation_attempts(id) ON DELETE RESTRICT,
        window_start TEXT NOT NULL,
        window_end TEXT NOT NULL CHECK (window_end >= window_start),
        governed_fingerprint TEXT NOT NULL CHECK (length(governed_fingerprint) = 64),
        artifact_descriptor_json TEXT NOT NULL,
        adjustment_policy TEXT NOT NULL,
        cost_policy_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(pair_id, split_kind, attempt)
    );
    CREATE INDEX idx_shadow_evaluation_pairs_candidate
        ON shadow_evaluation_pairs(candidate_id, created_at, id);
    CREATE INDEX idx_shadow_evaluation_attempts_pair
        ON shadow_evaluation_attempts(pair_id, split_kind, attempt);
    CREATE INDEX idx_shadow_evaluation_attempts_candidate
        ON shadow_evaluation_attempts(candidate_id, created_at, id);

    INSERT INTO shadow_evaluation_attempts
        (id, pair_id, run_id, candidate_id, split_kind, attempt,
         retry_of_evaluation_id, window_start, window_end, governed_fingerprint,
         artifact_descriptor_json, adjustment_policy, cost_policy_json, created_at)
    SELECT
        json_extract(runner_manifest_json, '$.evaluation_id'),
        NULL,
        id,
        candidate_id,
        json_extract(runner_manifest_json, '$.split_kind'),
        attempt,
        json_extract(runner_manifest_json, '$.retry_of_evaluation_id'),
        json_extract(runner_manifest_json, '$.window.start'),
        json_extract(runner_manifest_json, '$.window.end'),
        governed_fingerprint,
        json_extract(runner_manifest_json, '$.artifact'),
        json_extract(runner_manifest_json, '$.adjustment_policy'),
        json_extract(runner_manifest_json, '$.cost_policy'),
        created_at
    FROM shadow_candidate_runs
    WHERE json_valid(runner_manifest_json)
      AND json_type(runner_manifest_json, '$.evaluation_id') = 'text'
      AND json_type(runner_manifest_json, '$.split_kind') = 'text';

    CREATE TRIGGER shadow_evaluation_pairs_no_update
    BEFORE UPDATE ON shadow_evaluation_pairs
    BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evaluation_pairs_no_delete
    BEFORE DELETE ON shadow_evaluation_pairs
    BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evaluation_attempts_no_update
    BEFORE UPDATE ON shadow_evaluation_attempts
    BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    CREATE TRIGGER shadow_evaluation_attempts_no_delete
    BEFORE DELETE ON shadow_evaluation_attempts
    BEGIN SELECT RAISE(ABORT, 'phase 05 facts are immutable'); END;
    """,
    """
    CREATE TABLE forecast_maturity_cursor (
        cursor_name TEXT PRIMARY KEY CHECK (cursor_name = 'forecast-maturity'),
        cursor_created_at TEXT NOT NULL,
        cursor_forecast_id TEXT NOT NULL,
        cursor_horizon INTEGER NOT NULL CHECK (cursor_horizon IN (0, 5, 20, 60)),
        lease_owner TEXT,
        lease_until TEXT,
        transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
        updated_at TEXT NOT NULL,
        CHECK ((lease_owner IS NULL) = (lease_until IS NULL)),
        CHECK (
            (cursor_created_at = '' AND cursor_forecast_id = '' AND cursor_horizon = 0)
            OR (cursor_created_at != '' AND cursor_forecast_id != '' AND cursor_horizon != 0)
        )
    );
    INSERT INTO forecast_maturity_cursor
        (cursor_name, cursor_created_at, cursor_forecast_id, cursor_horizon,
         lease_owner, lease_until, transition_version, updated_at)
    VALUES ('forecast-maturity', '', '', 0, NULL, NULL, 0, '');

    CREATE TABLE forecast_job_transitions (
        job_id TEXT NOT NULL REFERENCES forecast_jobs(id) ON DELETE RESTRICT,
        transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
        status TEXT NOT NULL CHECK (status IN (
            'queued', 'running', 'completed', 'validation_failed', 'model_unavailable',
            'artifact_failed', 'timed_out', 'resource_limited', 'interrupted'
        )),
        terminal_reason TEXT,
        recorded_at TEXT NOT NULL,
        PRIMARY KEY(job_id, transition_version)
    );
    INSERT INTO forecast_job_transitions
        (job_id, transition_version, status, terminal_reason, recorded_at)
    SELECT id, transition_version, status, terminal_reason, updated_at
    FROM forecast_jobs;
    CREATE INDEX idx_forecast_job_transitions_resume
        ON forecast_job_transitions(job_id, transition_version);

    CREATE TRIGGER forecast_maturity_cursor_guarded_update
    BEFORE UPDATE ON forecast_maturity_cursor
    WHEN NEW.cursor_name IS NOT OLD.cursor_name
      OR NEW.transition_version != OLD.transition_version + 1
      OR NEW.updated_at < OLD.updated_at
      OR ((NEW.lease_owner IS NULL) != (NEW.lease_until IS NULL))
      OR (
          NOT (
              NEW.cursor_created_at = ''
              AND NEW.cursor_forecast_id = ''
              AND NEW.cursor_horizon = 0
          )
          AND (NEW.cursor_created_at, NEW.cursor_forecast_id, NEW.cursor_horizon)
              < (OLD.cursor_created_at, OLD.cursor_forecast_id, OLD.cursor_horizon)
      )
    BEGIN SELECT RAISE(ABORT, 'forecast maturity cursor must advance monotonically'); END;
    CREATE TRIGGER forecast_maturity_cursor_no_delete
    BEFORE DELETE ON forecast_maturity_cursor
    BEGIN SELECT RAISE(ABORT, 'forecast maturity cursor is durable'); END;
    CREATE TRIGGER forecast_job_transitions_no_update
    BEFORE UPDATE ON forecast_job_transitions
    BEGIN SELECT RAISE(ABORT, 'forecast job transitions are immutable'); END;
    CREATE TRIGGER forecast_job_transitions_no_delete
    BEFORE DELETE ON forecast_job_transitions
    BEGIN SELECT RAISE(ABORT, 'forecast job transitions are immutable'); END;
    """,
    """
    ALTER TABLE forecast_records ADD COLUMN quantile_availability TEXT NOT NULL
        DEFAULT 'legacy_unavailable'
        CHECK (quantile_availability IN ('legacy_unavailable', 'available'));
    ALTER TABLE forecast_records ADD COLUMN quantiles_artifact_descriptor_json TEXT;
    ALTER TABLE forecast_records ADD COLUMN quantiles_checksum_sha256 TEXT
        CHECK (quantiles_checksum_sha256 IS NULL OR length(quantiles_checksum_sha256) = 64);
    ALTER TABLE forecast_records ADD COLUMN quantiles_source_paths_sha256 TEXT
        CHECK (quantiles_source_paths_sha256 IS NULL OR length(quantiles_source_paths_sha256) = 64);
    ALTER TABLE forecast_records ADD COLUMN quantiles_provenance_digest_sha256 TEXT
        CHECK (quantiles_provenance_digest_sha256 IS NULL OR length(quantiles_provenance_digest_sha256) = 64);
    ALTER TABLE forecast_records ADD COLUMN quantile_row_count INTEGER
        CHECK (quantile_row_count IS NULL OR quantile_row_count > 0);
    ALTER TABLE forecast_records ADD COLUMN quantile_session_count INTEGER
        CHECK (quantile_session_count IS NULL OR quantile_session_count IN (5, 20, 60));
    ALTER TABLE forecast_records ADD COLUMN quantile_feature_count INTEGER
        CHECK (quantile_feature_count IS NULL OR quantile_feature_count > 0);

    CREATE TRIGGER forecast_quantile_metadata_insert_guard
    BEFORE INSERT ON forecast_records
    WHEN NOT (
        (
            NEW.quantile_availability = 'legacy_unavailable'
            AND NEW.quantiles_artifact_descriptor_json IS NULL
            AND NEW.quantiles_checksum_sha256 IS NULL
            AND NEW.quantiles_source_paths_sha256 IS NULL
            AND NEW.quantiles_provenance_digest_sha256 IS NULL
            AND NEW.quantile_row_count IS NULL
            AND NEW.quantile_session_count IS NULL
            AND NEW.quantile_feature_count IS NULL
        )
        OR
        (
            NEW.quantile_availability = 'available'
            AND NEW.quantiles_artifact_descriptor_json IS NOT NULL
            AND NEW.quantiles_checksum_sha256 IS NOT NULL
            AND NEW.quantiles_source_paths_sha256 IS NOT NULL
            AND NEW.quantiles_provenance_digest_sha256 IS NOT NULL
            AND NEW.quantile_row_count = 3 * NEW.horizon * NEW.quantile_feature_count
            AND NEW.quantile_session_count = NEW.horizon
        )
    )
    BEGIN SELECT RAISE(ABORT, 'forecast quantile metadata is incomplete'); END;
    """,
    """
    -- A retry is not runnable until one durable operation owner has bound and
    -- atomically published the canonical job.
    ALTER TABLE forecast_jobs
        ADD COLUMN dispatch_ready INTEGER NOT NULL DEFAULT 0
        CHECK (dispatch_ready IN (0, 1));
    ALTER TABLE forecast_jobs ADD COLUMN bound_identity_json TEXT;
    ALTER TABLE forecast_jobs ADD COLUMN bound_input_artifact_id TEXT;

    CREATE TABLE forecast_retry_operations (
        id TEXT PRIMARY KEY,
        source_job_id TEXT NOT NULL REFERENCES forecast_jobs(id) ON DELETE RESTRICT,
        idempotency_key TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('reserved', 'bound', 'published', 'aborted')),
        owner_token TEXT NOT NULL,
        owner_lease_until TEXT NOT NULL,
        transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
        immutable_record_json TEXT,
        input_artifact_id TEXT,
        canonical_job_id TEXT UNIQUE REFERENCES forecast_jobs(id) ON DELETE RESTRICT,
        terminal_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(source_job_id, idempotency_key),
        CHECK (
            (state = 'reserved' AND immutable_record_json IS NULL
                                AND input_artifact_id IS NULL
                                AND canonical_job_id IS NULL
                                AND terminal_reason IS NULL)
            OR
            (state = 'bound' AND immutable_record_json IS NOT NULL
                             AND input_artifact_id IS NOT NULL
                             AND canonical_job_id IS NULL
                             AND terminal_reason IS NULL)
            OR
            (state = 'published' AND immutable_record_json IS NOT NULL
                                 AND input_artifact_id IS NOT NULL
                                 AND canonical_job_id IS NOT NULL
                                 AND terminal_reason IS NULL)
            OR
            (state = 'aborted' AND canonical_job_id IS NULL
                               AND terminal_reason IS NOT NULL)
        )
    );
    CREATE INDEX idx_forecast_retry_operations_recovery
        ON forecast_retry_operations(state, owner_lease_until, id);

    -- No prior release persisted a complete job binding. Conservatively
    -- quarantine every legacy queued row before recovery can observe it.
    UPDATE forecast_jobs
       SET status = 'interrupted',
           transition_version = transition_version + 1,
           terminal_reason = 'legacy_unbound_quarantined',
           dispatch_ready = 0
     WHERE status = 'queued';
    INSERT INTO forecast_job_transitions
        (job_id, transition_version, status, terminal_reason, recorded_at)
    SELECT id, transition_version, status, terminal_reason, updated_at
      FROM forecast_jobs
     WHERE terminal_reason = 'legacy_unbound_quarantined';

    CREATE TRIGGER forecast_jobs_dispatch_binding_immutable
    BEFORE UPDATE ON forecast_jobs
    WHEN NEW.dispatch_ready IS NOT OLD.dispatch_ready
      OR NEW.bound_identity_json IS NOT OLD.bound_identity_json
      OR NEW.bound_input_artifact_id IS NOT OLD.bound_input_artifact_id
    BEGIN SELECT RAISE(ABORT, 'forecast dispatch binding is immutable'); END;

    CREATE TRIGGER forecast_retry_operations_guarded_update
    BEFORE UPDATE ON forecast_retry_operations
    WHEN NEW.id IS NOT OLD.id
      OR NEW.source_job_id IS NOT OLD.source_job_id
      OR NEW.idempotency_key IS NOT OLD.idempotency_key
      OR NEW.owner_token IS NOT OLD.owner_token
      OR NEW.owner_lease_until IS NOT OLD.owner_lease_until
      OR NEW.created_at IS NOT OLD.created_at
      OR NEW.transition_version != OLD.transition_version + 1
      OR NEW.updated_at < OLD.updated_at
      OR NOT (
          (OLD.state = 'reserved' AND NEW.state IN ('bound', 'aborted'))
          OR (OLD.state = 'bound' AND NEW.state IN ('published', 'aborted'))
      )
    BEGIN SELECT RAISE(ABORT, 'forecast retry operation transition is invalid'); END;
    CREATE TRIGGER forecast_retry_operations_no_delete
    BEFORE DELETE ON forecast_retry_operations
    BEGIN SELECT RAISE(ABORT, 'forecast retry operations are durable'); END;
    """,
    """
    -- Phase 10 append-only research contracts (PIT universe + admission + composite).
    -- All four tables are immutable facts: rows are INSERT-only. A universe delist is
    -- a NEW row, never an UPDATE; an admission verdict or model/composite output row
    -- is never rewritten once persisted.
    CREATE TABLE factor_universe_membership (
        id TEXT PRIMARY KEY,
        universe_name TEXT NOT NULL,
        symbol TEXT NOT NULL,
        asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'etf')),
        effective_date TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('listed', 'delisted')),
        source TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (universe_name, symbol, effective_date, state)
    );
    CREATE INDEX idx_universe_membership_resolve
        ON factor_universe_membership(universe_name, symbol, effective_date);
    CREATE TRIGGER factor_universe_membership_no_update BEFORE UPDATE ON factor_universe_membership
    BEGIN SELECT RAISE(ABORT, 'factor universe membership is append-only'); END;
    CREATE TRIGGER factor_universe_membership_no_delete BEFORE DELETE ON factor_universe_membership
    BEGIN SELECT RAISE(ABORT, 'factor universe membership is append-only'); END;

    CREATE TABLE factor_admission_verdicts (
        id TEXT PRIMARY KEY,
        revision_id TEXT NOT NULL REFERENCES research_factor_revisions(id) ON DELETE RESTRICT,
        policy_version TEXT NOT NULL,
        verdict TEXT NOT NULL CHECK (verdict IN ('admitted', 'rejected')),
        reason TEXT NOT NULL,
        gates_json TEXT NOT NULL,
        candidate_trail_json TEXT NOT NULL,
        resolved_universe_json TEXT NOT NULL,
        input_snapshot_sha256 TEXT NOT NULL CHECK (length(input_snapshot_sha256) = 64),
        created_at TEXT NOT NULL,
        UNIQUE (revision_id, policy_version)
    );
    CREATE INDEX idx_admission_verdicts_revision ON factor_admission_verdicts(revision_id);
    CREATE TRIGGER factor_admission_verdicts_no_update BEFORE UPDATE ON factor_admission_verdicts
    BEGIN SELECT RAISE(ABORT, 'factor admission verdicts are append-only'); END;
    CREATE TRIGGER factor_admission_verdicts_no_delete BEFORE DELETE ON factor_admission_verdicts
    BEGIN SELECT RAISE(ABORT, 'factor admission verdicts are append-only'); END;

    CREATE TABLE factor_model_models (
        model_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        weighting TEXT NOT NULL CHECK (weighting IN ('equal', 'ic_weighted')),
        revision_ids_json TEXT NOT NULL,
        weights_json TEXT NOT NULL,
        input_snapshot_sha256 TEXT NOT NULL CHECK (length(input_snapshot_sha256) = 64),
        created_at TEXT NOT NULL
    );
    CREATE TRIGGER factor_model_models_no_update BEFORE UPDATE ON factor_model_models
    BEGIN SELECT RAISE(ABORT, 'factor model definitions are append-only'); END;
    CREATE TRIGGER factor_model_models_no_delete BEFORE DELETE ON factor_model_models
    BEGIN SELECT RAISE(ABORT, 'factor model definitions are append-only'); END;

    CREATE TABLE factor_model_composites (
        id TEXT PRIMARY KEY,
        model_id TEXT NOT NULL REFERENCES factor_model_models(model_id) ON DELETE RESTRICT,
        output_sha256 TEXT NOT NULL CHECK (length(output_sha256) = 64),
        artifact_relative_path TEXT NOT NULL,
        input_snapshot_sha256 TEXT NOT NULL CHECK (length(input_snapshot_sha256) = 64),
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_factor_model_composites_model ON factor_model_composites(model_id);
    CREATE TRIGGER factor_model_composites_no_update BEFORE UPDATE ON factor_model_composites
    BEGIN SELECT RAISE(ABORT, 'factor model composites are append-only'); END;
    CREATE TRIGGER factor_model_composites_no_delete BEFORE DELETE ON factor_model_composites
    BEGIN SELECT RAISE(ABORT, 'factor model composites are append-only'); END;
    """,
    """
    -- Phase 11 append-only optimization run records (PFOL-04).
    -- Every optimization run is one immutable fact: INSERT-only. Failed runs are
    -- retained with their failure reason; solver/options/status are recorded
    -- verbatim against the pinned cvxpy 1.9.2 engine. Weights/covariance live in
    -- checksum-verified immutable artifacts (output_sha256 + relative path).
    CREATE TABLE portfolio_optimization_runs (
        id TEXT PRIMARY KEY,
        objective TEXT NOT NULL CHECK (objective IN ('min_volatility', 'hrp', 'max_sharpe')),
        as_of TEXT NOT NULL,
        universe TEXT NOT NULL,
        model_id TEXT REFERENCES factor_model_models(model_id) ON DELETE RESTRICT,
        composite_snapshot_id TEXT,
        input_snapshot_sha256 TEXT NOT NULL CHECK (length(input_snapshot_sha256) = 64),
        expected_return_method TEXT NOT NULL CHECK (expected_return_method IN ('composite-zscore-v1', 'none')),
        risk_model TEXT NOT NULL CHECK (risk_model IN ('sample_covariance_v1')),
        risk_model_json TEXT NOT NULL,
        constraint_stack_json TEXT NOT NULL,
        solver_name TEXT NOT NULL,
        solver_version TEXT NOT NULL,
        solver_options_json TEXT NOT NULL,
        problem_status TEXT NOT NULL CHECK (
            problem_status IN ('optimal', 'optimal_inaccurate', 'infeasible',
                               'unbounded', 'solver_error', 'failed')
        ),
        failure_reason TEXT,
        output_weights_json TEXT,
        output_sha256 TEXT CHECK (output_sha256 IS NULL OR length(output_sha256) = 64),
        weights_artifact_relative_path TEXT,
        baseline_weights_json TEXT,
        created_at TEXT NOT NULL,
        CHECK (
            (problem_status IN ('failed', 'solver_error')) = (failure_reason IS NOT NULL)
        )
    );
    CREATE INDEX idx_portfolio_optimization_runs_as_of ON portfolio_optimization_runs(as_of, objective);
    CREATE TRIGGER portfolio_optimization_runs_no_update BEFORE UPDATE ON portfolio_optimization_runs
    BEGIN SELECT RAISE(ABORT, 'portfolio optimization runs are append-only'); END;
    CREATE TRIGGER portfolio_optimization_runs_no_delete BEFORE DELETE ON portfolio_optimization_runs
    BEGIN SELECT RAISE(ABORT, 'portfolio optimization runs are append-only'); END;
    """,
    """
    -- Phase 12 append-only attribution evidence (RSK-01/03) + risk-model enum widening.
    -- Two one-way doors in one atomic script (approved decision option-a):
    --   (1) rebuild portfolio_optimization_runs so risk_model accepts the 4-model enum
    --       (SQLite cannot ALTER a CHECK -- the Phase 7 rebuild pattern).
    --   (2) create portfolio_risk_attribution_evidence: every attribution/drawdown
    --       analysis is one immutable fact bound to a checksum-verified artifact.
    -- The runs rebuild runs FIRST so the evidence table's run_id FK binds to the
    -- FINAL runs table (renaming runs after the FK exists would re-point the FK to
    -- the _legacy table and then break when legacy is dropped).
    PRAGMA foreign_keys = OFF;
    DROP TRIGGER IF EXISTS portfolio_optimization_runs_no_update;
    DROP TRIGGER IF EXISTS portfolio_optimization_runs_no_delete;
    ALTER TABLE portfolio_optimization_runs RENAME TO portfolio_optimization_runs_legacy;
    CREATE TABLE portfolio_optimization_runs (
        id TEXT PRIMARY KEY,
        objective TEXT NOT NULL CHECK (objective IN ('min_volatility', 'hrp', 'max_sharpe')),
        as_of TEXT NOT NULL,
        universe TEXT NOT NULL,
        model_id TEXT REFERENCES factor_model_models(model_id) ON DELETE RESTRICT,
        composite_snapshot_id TEXT,
        input_snapshot_sha256 TEXT NOT NULL CHECK (length(input_snapshot_sha256) = 64),
        expected_return_method TEXT NOT NULL CHECK (expected_return_method IN ('composite-zscore-v1', 'none')),
        risk_model TEXT NOT NULL CHECK (risk_model IN ('sample_covariance_v1', 'semi_covariance_v1', 'ewma_covariance_v1', 'ledoit_wolf_v1')),
        risk_model_json TEXT NOT NULL,
        constraint_stack_json TEXT NOT NULL,
        solver_name TEXT NOT NULL,
        solver_version TEXT NOT NULL,
        solver_options_json TEXT NOT NULL,
        problem_status TEXT NOT NULL CHECK (
            problem_status IN ('optimal', 'optimal_inaccurate', 'infeasible',
                               'unbounded', 'solver_error', 'failed')
        ),
        failure_reason TEXT,
        output_weights_json TEXT,
        output_sha256 TEXT CHECK (output_sha256 IS NULL OR length(output_sha256) = 64),
        weights_artifact_relative_path TEXT,
        baseline_weights_json TEXT,
        created_at TEXT NOT NULL,
        CHECK (
            (problem_status IN ('failed', 'solver_error')) = (failure_reason IS NOT NULL)
        )
    );
    INSERT INTO portfolio_optimization_runs
        (id, objective, as_of, universe, model_id, composite_snapshot_id, input_snapshot_sha256,
         expected_return_method, risk_model, risk_model_json, constraint_stack_json, solver_name,
         solver_version, solver_options_json, problem_status, failure_reason, output_weights_json,
         output_sha256, weights_artifact_relative_path, baseline_weights_json, created_at)
    SELECT
        id, objective, as_of, universe, model_id, composite_snapshot_id, input_snapshot_sha256,
        expected_return_method, risk_model, risk_model_json, constraint_stack_json, solver_name,
        solver_version, solver_options_json, problem_status, failure_reason, output_weights_json,
        output_sha256, weights_artifact_relative_path, baseline_weights_json, created_at
    FROM portfolio_optimization_runs_legacy;
    DROP TABLE portfolio_optimization_runs_legacy;
    CREATE INDEX idx_portfolio_optimization_runs_as_of ON portfolio_optimization_runs(as_of, objective);
    CREATE TRIGGER portfolio_optimization_runs_no_update BEFORE UPDATE ON portfolio_optimization_runs
    BEGIN SELECT RAISE(ABORT, 'portfolio optimization runs are append-only'); END;
    CREATE TRIGGER portfolio_optimization_runs_no_delete BEFORE DELETE ON portfolio_optimization_runs
    BEGIN SELECT RAISE(ABORT, 'portfolio optimization runs are append-only'); END;

    CREATE TABLE portfolio_risk_attribution_evidence (
        id TEXT PRIMARY KEY,
        attribution_type TEXT NOT NULL CHECK (attribution_type IN ('exposure_contribution', 'drawdown')),
        run_id TEXT NOT NULL REFERENCES portfolio_optimization_runs(id) ON DELETE RESTRICT,
        risk_model TEXT NOT NULL CHECK (risk_model IN ('sample_covariance_v1', 'semi_covariance_v1', 'ewma_covariance_v1', 'ledoit_wolf_v1')),
        as_of TEXT NOT NULL,
        output_sha256 TEXT NOT NULL CHECK (length(output_sha256) = 64),
        artifact_relative_path TEXT NOT NULL,
        reconciliation_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_attribution_evidence_run ON portfolio_risk_attribution_evidence(run_id, attribution_type);
    CREATE TRIGGER portfolio_risk_attribution_evidence_no_update BEFORE UPDATE ON portfolio_risk_attribution_evidence
    BEGIN SELECT RAISE(ABORT, 'portfolio risk attribution evidence is append-only'); END;
    CREATE TRIGGER portfolio_risk_attribution_evidence_no_delete BEFORE DELETE ON portfolio_risk_attribution_evidence
    BEGIN SELECT RAISE(ABORT, 'portfolio risk attribution evidence is append-only'); END;
    PRAGMA foreign_keys = ON;
    """,
)


def _migration_statements(script: str) -> tuple[str, ...]:
    """Split one SQLite script without breaking compound trigger statements."""
    statements: list[str] = []
    pending: list[str] = []
    for line in script.splitlines(keepends=True):
        pending.append(line)
        candidate = "".join(pending)
        if sqlite3.complete_statement(candidate):
            statements.append(candidate)
            pending.clear()
    if "".join(pending).strip():
        raise ValueError("operational migration contains an incomplete SQL statement")
    return tuple(statement for statement in statements if statement.strip())


def _foreign_keys_directive(statement: str) -> bool | None:
    """Return an explicit foreign-key setting, ignoring leading line comments."""
    sql = "\n".join(line for line in statement.splitlines() if not line.lstrip().startswith("--"))
    normalized = "".join(sql.strip().rstrip(";").casefold().split())
    if normalized == "pragmaforeign_keys=off":
        return False
    if normalized == "pragmaforeign_keys=on":
        return True
    return None


def migrate_operational_db(connection: sqlite3.Connection) -> None:
    """Apply each migration and its schema version in one atomic transaction."""
    connection.execute("PRAGMA foreign_keys = ON")
    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version > len(MIGRATIONS):
        raise RuntimeError("operational database is newer than this application")

    for version, migration in enumerate(MIGRATIONS[current_version:], start=current_version + 1):
        statements = _migration_statements(migration)
        disable_foreign_keys = any(
            _foreign_keys_directive(statement) is False for statement in statements
        )
        connection.execute(
            "PRAGMA foreign_keys = OFF" if disable_foreign_keys else "PRAGMA foreign_keys = ON"
        )
        transactional_sql = "\n".join(
            statement for statement in statements if _foreign_keys_directive(statement) is None
        )
        transactional_sql = (
            f"BEGIN;\n{transactional_sql}\nPRAGMA user_version = {version};\nCOMMIT;"
        )
        try:
            connection.executescript(transactional_sql)
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.execute("PRAGMA foreign_keys = ON")
