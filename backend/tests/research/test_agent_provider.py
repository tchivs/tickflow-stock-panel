"""Agent provider seam + failure taxonomy + AnalysisRecord contracts.

Phase 48-01. Covers:
* 48-01-02 — append-only ``research_alpha_analysis_attempts`` table + repo
  write/read (AF-REQ-14, OQ-1).
* 48-01-03 — ProviderFailure taxonomy + retry policy (AF-REQ-14 §7.1-7.2).
* 48-01-04 — AgentProviderSeam: retry/backoff/cancellation + one AnalysisRecord
  row per attempt + the no-fallback invariant (SC4).
"""
from __future__ import annotations

import json
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



# ==================================================================
# 48-01-03 — ProviderFailure taxonomy + retry policy
# ==================================================================


class _StatusError(Exception):
    """A transport-shaped error carrying an HTTP status_code attribute."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"http {status_code}")


class _APITimeoutError(Exception):
    pass


class _APIConnectionError(Exception):
    pass


class TestProviderFailureTaxonomy:
    def test_taxonomy_failure_classes_complete(self) -> None:
        from app.research.agent_provider import FAILURE_CLASSES

        assert FAILURE_CLASSES == frozenset({
            "malformed_json", "schema_violation", "parse_failure", "timeout",
            "rate_limited", "unavailable", "refused", "partial", "cancelled",
        })

    @pytest.mark.parametrize("status, expected", [
        (408, "timeout"), (504, "timeout"),
        (429, "rate_limited"),
        (500, "unavailable"), (502, "unavailable"), (503, "unavailable"),
        (400, "refused"), (401, "refused"), (403, "refused"), (404, "refused"),
    ])
    def test_classify_http_status_to_class(self, status: int, expected: str) -> None:
        from app.research.agent_provider import classify_provider_failure

        failure = classify_provider_failure(_StatusError(status))
        assert failure.klass == expected
        assert failure.http_status == status

    def test_classify_timeout_by_class_name(self) -> None:
        from app.research.agent_provider import classify_provider_failure

        failure = classify_provider_failure(_APITimeoutError())
        assert failure.klass == "timeout"
        assert failure.transient is True
        assert failure.terminal is False

    def test_classify_connection_error_by_class_name(self) -> None:
        from app.research.agent_provider import classify_provider_failure

        failure = classify_provider_failure(_APIConnectionError())
        assert failure.klass == "unavailable"
        assert failure.transient is True

    def test_classify_malformed_json(self) -> None:
        from app.research.agent_provider import classify_provider_failure

        failure = classify_provider_failure(json.JSONDecodeError("bad", "doc", 0))
        assert failure.klass == "malformed_json"
        assert failure.transient is False
        assert failure.terminal is True

    def test_classify_schema_violation(self) -> None:
        from app.research.agent_provider import classify_provider_failure

        failure = classify_provider_failure(ValueError("provider draft has unsupported field(s): foo"))
        assert failure.klass == "schema_violation"
        assert failure.terminal is True

    def test_classify_parse_failure(self) -> None:
        from app.research.agent_provider import classify_provider_failure
        from app.research.factor_dsl import parse_factor

        with pytest.raises(Exception):
            parse_factor("@@@not a factor@@@")
        try:
            parse_factor("@@@not a factor@@@")
        except Exception as exc:
            failure = classify_provider_failure(exc)
        assert failure.klass == "parse_failure"
        assert failure.terminal is True

    def test_classify_partial(self) -> None:
        from app.research.agent_provider import classify_provider_failure

        exc = ValueError("downstream validation")
        exc.partial_failure = True  # type: ignore[attr-defined]
        failure = classify_provider_failure(exc, raw_response="{\"partial\": true}")
        assert failure.klass == "partial"
        assert failure.transient is False
        assert failure.terminal is False

    def test_classify_is_pure(self) -> None:
        from app.research.agent_provider import classify_provider_failure

        first = classify_provider_failure(_StatusError(503))
        second = classify_provider_failure(_StatusError(503))
        assert first == second

    @pytest.mark.parametrize("klass, expected_retry", [
        ("timeout", True), ("rate_limited", True), ("unavailable", True),
        ("malformed_json", False), ("schema_violation", False), ("parse_failure", False),
        ("refused", False), ("partial", False), ("cancelled", False),
    ])
    def test_retry_policy(self, klass: str, expected_retry: bool) -> None:
        from app.research.agent_provider import ProviderFailure, retry_policy

        transient, terminal = {
            "malformed_json": (False, True), "schema_violation": (False, True),
            "parse_failure": (False, True), "timeout": (True, False),
            "rate_limited": (True, False), "unavailable": (True, False),
            "refused": (False, True), "partial": (False, False), "cancelled": (False, True),
        }[klass]
        failure = ProviderFailure(
            klass=klass, transient=transient, terminal=terminal,
            reason={"class": klass}, http_status=None,
        )
        decision = retry_policy(failure)
        assert decision.should_retry is expected_retry
        if expected_retry:
            assert decision.max_retries == 3
            assert decision.base_delay == 1.0
            assert decision.factor == 2.0
            assert decision.cap == 30.0


# ==================================================================
# 48-01-04 — AgentProviderSeam: retry/backoff/cancel + no fallback (SC4)
# ==================================================================


class _FakeRecorder:
    """Captures every record_analysis_attempt call as a dict."""

    def __init__(self, real_repo: ResearchRepository) -> None:
        self._repo = real_repo
        self.calls: list[dict] = []

    def __call__(self, **kwargs) -> dict:
        self.calls.append(dict(kwargs))
        return self._repo.record_analysis_attempt(**kwargs)

def _seam_kwargs(repo: ResearchRepository, run_id: str, **overrides) -> dict:
    base = dict(
        stage="stage1",
        messages=[{"role": "user", "content": "hi"}],
        request_payload={"thesis": "momentum"},
        repo=repo,
        run_id=run_id,
        schema_version="factor-stage1-v1",
        template_version="factor-stage1-v1",
        provider="openai_compat",
        model="test-model",
        model_version="test-v1",
    )
    base.update(overrides)
    return base


def _raising_generate(factory):
    async def _generate(*args, **kwargs):
        raise factory()
    return _generate


class TestAgentProviderSeamNoFallback:
    """SC4: every failure class records a failed row and raises — no fallback draft."""

    @pytest.mark.parametrize("factory, expected_rows", [
        (lambda: json.JSONDecodeError("bad", "doc", 0), 1),
        (lambda: ValueError("provider draft has unsupported field(s): x"), 1),
        (lambda: _make_parse_error(), 1),
        (lambda: _StatusError(400), 1),
        (lambda: _StatusError(408), 4),
        (lambda: _StatusError(429), 4),
        (lambda: _StatusError(503), 4),
    ])
    async def test_seam_no_fallback_per_failure_class(
        self, tmp_path, factory, expected_rows: int
    ) -> None:
        from app.research.agent_provider import AgentProviderSeam, ProviderCallError

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        recorder = _FakeRecorder(repo)
        seam = AgentProviderSeam(
            generate_text=_raising_generate(factory),
            record_analysis_attempt=recorder,
        )

        sleeps: list[float] = []

        async def _sleep(delay: float) -> None:
            sleeps.append(delay)

        with pytest.raises(ProviderCallError):
            await seam.request(
                **_seam_kwargs(repo, run_id, sleep=_sleep),
            )
        rows = repo.list_analysis_attempts(run_id, stage="stage1")
        assert len(rows) == expected_rows
        # Zero success rows — no fabricated fallback draft.
        assert all(r["outcome"] == "failed" for r in rows)
        assert not any(r["outcome"] in ("proposed", "validated") for r in rows)
        # Each row shares one request scope.
        assert len({r["request_scope_sha256"] for r in rows}) == 1
        # attempt_ordinal is contiguous from 1.
        assert [r["attempt_ordinal"] for r in rows] == list(range(1, expected_rows + 1))


def _make_parse_error() -> Exception:
    from app.research.factor_dsl import parse_factor

    try:
        parse_factor("@@@bogus@@@")
    except Exception as exc:
        return exc
    raise AssertionError("expected a parse error")


class TestAgentProviderSeamRetryBackoff:
    async def test_transient_retries_with_exponential_backoff_then_raises(
        self, tmp_path
    ) -> None:
        from app.research.agent_provider import AgentProviderSeam, ProviderCallError

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        recorder = _FakeRecorder(repo)
        seam = AgentProviderSeam(
            generate_text=_raising_generate(lambda: _StatusError(503)),
            record_analysis_attempt=recorder,
        )
        sleeps: list[float] = []

        async def _sleep(delay: float) -> None:
            sleeps.append(delay)

        with pytest.raises(ProviderCallError):
            await seam.request(**_seam_kwargs(repo, run_id, sleep=_sleep))
        # 1 initial attempt + 3 retries = 4 attempts, 3 sleeps.
        assert len(sleeps) == 3
        bases = [1.0, 2.0, 4.0]
        for delay, base in zip(sleeps, bases):
            # jitter = (0.5 + random()) ∈ [0.5, 1.5)
            assert base * 0.5 <= delay < base * 1.5
        # Cap is never exceeded.
        assert all(d <= 30.0 for d in sleeps)

    async def test_permanent_failure_records_and_raises_with_zero_retries(
        self, tmp_path
    ) -> None:
        from app.research.agent_provider import AgentProviderSeam, ProviderCallError

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        recorder = _FakeRecorder(repo)
        seam = AgentProviderSeam(
            generate_text=_raising_generate(lambda: json.JSONDecodeError("bad", "doc", 0)),
            record_analysis_attempt=recorder,
        )
        slept: list[float] = []

        async def _sleep(delay: float) -> None:
            slept.append(delay)

        with pytest.raises(ProviderCallError):
            await seam.request(**_seam_kwargs(repo, run_id, sleep=_sleep))
        assert slept == []  # no retry on a permanent failure
        rows = repo.list_analysis_attempts(run_id, stage="stage1")
        assert len(rows) == 1
        assert rows[0]["retries"] == 0
        assert rows[0]["failure_class"] == "malformed_json"


class TestAgentProviderSeamCancel:
    async def test_cancel_check_mid_loop_records_cancelled_row(self, tmp_path) -> None:
        from app.research.agent_provider import AgentProviderSeam, ProviderCallError

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        recorder = _FakeRecorder(repo)
        seam = AgentProviderSeam(
            generate_text=_raising_generate(lambda: _StatusError(503)),
            record_analysis_attempt=recorder,
        )

        async def _sleep(delay: float) -> None:
            return None

        with pytest.raises(ProviderCallError):
            await seam.request(
                **_seam_kwargs(repo, run_id, sleep=_sleep, cancel_check=lambda: True),
            )
        rows = repo.list_analysis_attempts(run_id, stage="stage1")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "cancelled"
        assert rows[0]["failure_class"] == "cancelled"
        assert rows[0]["cancelled"] == 1


class TestAgentProviderSeamSuccess:
    async def test_success_records_response_checksum_and_latency(self, tmp_path) -> None:
        from app.research.agent_provider import AgentProviderSeam

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        raw = '{"hypotheses": []}'

        async def _generate(*args, **kwargs):
            return raw

        seam = AgentProviderSeam(generate_text=_generate, record_analysis_attempt=_FakeRecorder(repo))
        result = await seam.request(**_seam_kwargs(repo, run_id))
        assert result.raw == raw
        assert result.attempt_ordinal == 1
        rows = repo.list_analysis_attempts(run_id, stage="stage1")
        assert len(rows) == 1
        row = rows[0]
        assert row["outcome"] == "proposed"
        assert row["response_sha256"] is not None and len(row["response_sha256"]) == 64
        assert row["response_byte_size"] == len(raw.encode("utf-8"))
        assert row["latency_ms"] >= 0
        assert row["response_artifact_id"] is None  # checksum-by-default
        assert row["retries"] == 0

    async def test_retain_raw_artifact_service_stores_full_response(self, tmp_path) -> None:
        from app.research.agent_provider import AgentProviderSeam

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        raw = '{"hypotheses": []}'

        async def _generate(*args, **kwargs):
            return raw

        class _ArtifactService:
            def __init__(self, repo):
                self._repo = repo

            def store(self, *, run_id, stage, raw, checksum_sha256, byte_size):
                artifact_id = "aart_" + checksum_sha256[:16]
                with self._repo._connection() as connection, connection:
                    connection.execute(
                        """INSERT INTO research_alpha_artifacts
                           (id, run_id, logical_kind, relative_path, content_type,
                            byte_size, checksum_sha256, schema_version, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            artifact_id, run_id, "response",
                            f"research_artifacts/alpha_runs/{run_id}/{checksum_sha256}.json",
                            "application/json", byte_size, checksum_sha256,
                            "alpha-artifact-v1", "2026-08-09T00:00:00+00:00",
                        ),
                    )
                return artifact_id

        seam = AgentProviderSeam(generate_text=_generate, record_analysis_attempt=_FakeRecorder(repo))
        await seam.request(
            **_seam_kwargs(repo, run_id, retain_raw_artifact_service=_ArtifactService(repo))
        )
        rows = repo.list_analysis_attempts(run_id, stage="stage1")
        assert rows[0]["response_artifact_id"].startswith("aart_")