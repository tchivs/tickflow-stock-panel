"""Agent provider seam + failure taxonomy + AnalysisRecord contracts.

Phase 48-01. Covers:
* 48-01-02 — append-only ``research_alpha_analysis_attempts`` table + repo
  write/read (AF-REQ-14, OQ-1).
* 48-01-03 — ProviderFailure taxonomy + retry policy (AF-REQ-14 §7.1-7.2).
* 48-01-04 — AgentProviderSeam: retry/backoff/cancellation + one AnalysisRecord
  row per attempt + the no-fallback invariant (SC4).
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from app.research.repository import AlphaRunConflictError, ResearchRepository
from app.research.run_contract import freeze_input_snapshot


def _manifest(*, seed: int = 42) -> dict:
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {
            "name": "cn-a-share",
            "asset_type": "stock",
            "membership_fingerprint": "c" * 64,
        },
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {
            "fingerprint": "d" * 64,
            "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": seed,
    }


def _make_run(repo: ResearchRepository, *, run_id: str = "run-agent") -> str:
    snapshot = freeze_input_snapshot(
        manifest=_manifest(), created_at="2026-08-09T00:00:00+00:00"
    )
    repo.create_alpha_run(
        run_id=run_id,
        principal="researcher@example.com",
        idempotency_key=f"idem-{run_id}",
        snapshot=snapshot,
        event_id=f"evt-{run_id}",
    )
    return run_id


def _attempt_kwargs(run_id: str, *, ordinal: int = 1, stage: str = "stage1", **overrides) -> dict:
    base = dict(
        run_id=run_id,
        stage=stage,
        attempt_ordinal=ordinal,
        template_version="factor-stage1-v1",
        schema_version="factor-stage1-v1",
        provider="openai_compat",
        model="test-model",
        model_version="test-v1",
        request_scope_sha256="1" * 64,
        response_sha256="2" * 64,
        response_byte_size=42,
        parsed_output_sha256="3" * 64,
        retries=0,
        cancelled=0,
        latency_ms=17,
        outcome="proposed",
    )
    base.update(overrides)
    return base


# ==================================================================
# 48-01-02 — append-only analysis_attempts table + repo write/read
# ==================================================================


class TestAnalysisAttemptsTable:
    def test_analysis_attempt_record_and_get(self, tmp_path) -> None:
        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        row = repo.record_analysis_attempt(**_attempt_kwargs(run_id))
        assert row["run_id"] == run_id
        assert row["stage"] == "stage1"
        assert row["attempt_ordinal"] == 1
        assert row["outcome"] == "proposed"
        assert row["response_sha256"] == "2" * 64
        assert row["id"].startswith("aan_")

        fetched = repo.get_analysis_attempt(run_id, stage="stage1", attempt_ordinal=1)
        assert fetched is not None
        assert fetched["id"] == row["id"]

    def test_analysis_attempt_duplicate_ordinal_raises_conflict(self, tmp_path) -> None:
        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        repo.record_analysis_attempt(**_attempt_kwargs(run_id, ordinal=1))
        with pytest.raises(AlphaRunConflictError):
            repo.record_analysis_attempt(**_attempt_kwargs(run_id, ordinal=1))

    def test_analysis_attempt_list_in_ordinal_order_scoped_to_stage(self, tmp_path) -> None:
        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        repo.record_analysis_attempt(**_attempt_kwargs(run_id, ordinal=2, outcome="failed", failure_class="timeout"))
        repo.record_analysis_attempt(**_attempt_kwargs(run_id, ordinal=1))
        repo.record_analysis_attempt(**_attempt_kwargs(run_id, ordinal=1, stage="stage2", outcome="validated"))

        stage1 = repo.list_analysis_attempts(run_id, stage="stage1")
        assert [r["attempt_ordinal"] for r in stage1] == [1, 2]
        all_rows = repo.list_analysis_attempts(run_id)
        assert len(all_rows) == 3
        # Ordered by attempt_ordinal then stage (deterministic).
        assert all_rows[0]["attempt_ordinal"] == 1

    def test_analysis_attempt_append_only_update_delete_raise(self, tmp_path) -> None:
        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        row = repo.record_analysis_attempt(**_attempt_kwargs(run_id))
        with repo._connection() as connection:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE research_alpha_analysis_attempts SET outcome = ? WHERE id = ?",
                    ("failed", row["id"]),
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM research_alpha_analysis_attempts WHERE id = ?", (row["id"],)
                )

    def test_attempts_table_cross_run_artifact_rejected_at_seam(self, tmp_path) -> None:
        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_a = _make_run(repo, run_id="run-a")
        run_b = _make_run(repo, run_id="run-b")
        # Insert an artifact owned by run_b directly (testing the guard, not byte verification).
        with repo._connection() as connection, connection:
            connection.execute(
                """INSERT INTO research_alpha_artifacts
                   (id, run_id, logical_kind, relative_path, content_type, byte_size,
                    checksum_sha256, schema_version, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "aart_foreign", run_b, "response", "research_artifacts/alpha_runs/run-b/" + "9" * 64 + ".json",
                    "application/json", 1, "9" * 64, "alpha-artifact-v1", "2026-08-09T00:00:00+00:00",
                ),
            )
        with pytest.raises(ValueError, match="belong to analysis run"):
            repo.record_analysis_attempt(
                **_attempt_kwargs(run_a, response_artifact_id="aart_foreign")
            )

    def test_attempts_table_cross_run_trigger_fires(self, tmp_path) -> None:
        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_a = _make_run(repo, run_id="run-a2")
        run_b = _make_run(repo, run_id="run-b2")
        with repo._connection() as connection, connection:
            connection.execute(
                """INSERT INTO research_alpha_artifacts
                   (id, run_id, logical_kind, relative_path, content_type, byte_size,
                    checksum_sha256, schema_version, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "aart_foreign2", run_b, "response", "research_artifacts/alpha_runs/run-b2/" + "8" * 64 + ".json",
                    "application/json", 1, "8" * 64, "alpha-artifact-v1", "2026-08-09T00:00:00+00:00",
                ),
            )
        # Bypass the repo ownership check; the DB trigger must still abort.
        with repo._connection() as connection:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """INSERT INTO research_alpha_analysis_attempts
                       (id, run_id, attempt_ordinal, stage, template_version, schema_version,
                        provider, model, model_version, request_scope_sha256, outcome, created_at,
                        response_artifact_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "aan_raw", run_a, 1, "stage1", "factor-stage1-v1", "factor-stage1-v1",
                        "openai_compat", "m", None, "1" * 64, "proposed", "2026-08-09T00:00:00+00:00",
                        "aart_foreign2",
                    ),
                )

    def test_attempts_table_migration_rerunnable(self, tmp_path) -> None:
        from app.operational import migrations

        conn = sqlite3.connect(":memory:")
        migrations.migrate_operational_db(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == len(migrations.MIGRATIONS)
        # A second run is a no-op.
        migrations.migrate_operational_db(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version
