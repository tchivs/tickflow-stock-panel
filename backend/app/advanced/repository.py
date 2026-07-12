"""Transactional SQLite primitives for immutable advanced-domain facts."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.operational.migrations import migrate_operational_db


def _json(value: object, field: str) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be JSON serializable") from error


class AdvancedRepository:
    """Short-lived parameterized connections over the sole operational database."""

    def __init__(self, database_path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.database_path = Path(database_path)
        self._clock = clock or (lambda: datetime.now(UTC))

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        with self._connection() as connection:
            migrate_operational_db(connection)

    def now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()

    def record_policy_revision(self, *, revision: str, fingerprint: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        identifier = str(uuid4())
        with self._connection() as connection, connection:
            try:
                connection.execute(
                    "INSERT INTO advanced_policy_revisions (id, revision, fingerprint, snapshot_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (identifier, revision, fingerprint, _json(snapshot, "policy snapshot"), self.now()),
                )
            except sqlite3.IntegrityError as error:
                row = connection.execute("SELECT * FROM advanced_policy_revisions WHERE fingerprint = ?", (fingerprint,)).fetchone()
                if row is None:
                    raise ValueError("advanced policy revision conflict") from error
                return self._policy_row(row)
            row = connection.execute("SELECT * FROM advanced_policy_revisions WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return self._policy_row(row)

    def acquire_job(self, *, job_id: str, authorization_id: str, principal: str, subject_kind: str, subject_key: str, task_type: str, market: str, instrument: str, idempotency_key: str) -> dict[str, Any]:
        """Return the existing idempotent job or append the one runnable cursor."""
        now = self.now()
        with self._connection() as connection, connection:
            existing = connection.execute(
                "SELECT * FROM advanced_jobs WHERE principal = ? AND idempotency_key = ?", (principal, idempotency_key)
            ).fetchone()
            if existing is not None:
                return dict(existing)
            active = connection.execute(
                """SELECT * FROM advanced_jobs WHERE principal = ? AND task_type = ? AND market = ? AND instrument = ?
                   AND status IN ('queued', 'authorized', 'frozen', 'drafted', 'gates_complete', 'awaiting_review')""",
                (principal, task_type, market, instrument),
            ).fetchone()
            if active is not None:
                return dict(active)
            try:
                connection.execute(
                    """INSERT INTO advanced_jobs (id, authorization_id, principal, subject_kind, subject_key, task_type, market,
                       instrument, idempotency_key, status, stage, stage_recorded_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'authorized', ?, ?, ?)""",
                    (job_id, authorization_id, principal, subject_kind, subject_key, task_type, market, instrument, idempotency_key, now, now, now),
                )
            except sqlite3.IntegrityError as error:
                row = connection.execute("SELECT * FROM advanced_jobs WHERE principal = ? AND idempotency_key = ?", (principal, idempotency_key)).fetchone()
                if row is not None:
                    return dict(row)
                raise ValueError("advanced job conflict") from error
            row = connection.execute("SELECT * FROM advanced_jobs WHERE id = ?", (job_id,)).fetchone()
        assert row is not None
        return dict(row)

    def create_authorization(self, *, principal: str, token_hash: str, policy_revision_id: str, scope: Mapping[str, object], expires_at: str) -> dict[str, Any]:
        identifier = str(uuid4())
        with self._connection() as connection, connection:
            connection.execute(
                "INSERT INTO advanced_authorizations (id, principal, token_hash, policy_revision_id, scope_json, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identifier, principal, token_hash, policy_revision_id, _json(scope, "authorization scope"), expires_at, self.now()),
            )
            row = connection.execute("SELECT * FROM advanced_authorizations WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return dict(row)

    def get_authorization_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM advanced_authorizations WHERE token_hash = ?", (token_hash,)).fetchone()
        return None if row is None else dict(row)

    def get_authorization(self, authorization_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM advanced_authorizations WHERE id = ?", (authorization_id,)).fetchone()
        return None if row is None else dict(row)

    def revoke_authorization(self, *, authorization_id: str) -> None:
        with self._connection() as connection, connection:
            changed = connection.execute(
                "UPDATE advanced_authorizations SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (self.now(), authorization_id),
            ).rowcount
        if changed != 1:
            raise ValueError("authorization cannot be revoked")

    def acquire_authorized_job(self, *, job_id: str, authorization_id: str, principal: str, subject_kind: str, subject_key: str, task_type: str, market: str, instrument: str, idempotency_key: str, policy_revision_id: str, quota: int, now: str) -> dict[str, Any] | None:
        """Atomically return an idempotent job or consume one current policy quota slot."""
        window_started_at = datetime.fromisoformat(now).astimezone(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
        with self._connection() as connection, connection:
            existing = connection.execute(
                "SELECT * FROM advanced_jobs WHERE principal = ? AND idempotency_key = ?", (principal, idempotency_key)
            ).fetchone()
            if existing is not None:
                return dict(existing)
            rate = connection.execute(
                "SELECT * FROM advanced_rate_windows WHERE principal = ? AND policy_revision_id = ? AND window_started_at = ?",
                (principal, policy_revision_id, window_started_at),
            ).fetchone()
            consumed = 0 if rate is None else int(rate["consumed"])
            if consumed >= quota:
                return None
            if rate is None:
                connection.execute(
                    "INSERT INTO advanced_rate_windows (id, principal, policy_revision_id, window_started_at, consumed, created_at) VALUES (?, ?, ?, ?, 1, ?)",
                    (str(uuid4()), principal, policy_revision_id, window_started_at, now),
                )
            else:
                connection.execute("UPDATE advanced_rate_windows SET consumed = consumed + 1 WHERE id = ?", (rate["id"],))
            connection.execute(
                """INSERT INTO advanced_jobs (id, authorization_id, principal, subject_kind, subject_key, task_type, market,
                   instrument, idempotency_key, status, stage, stage_recorded_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'authorized', ?, ?, ?)""",
                (job_id, authorization_id, principal, subject_kind, subject_key, task_type, market, instrument, idempotency_key, now, now, now),
            )
            row = connection.execute("SELECT * FROM advanced_jobs WHERE id = ?", (job_id,)).fetchone()
        assert row is not None
        return dict(row)

    def quota_is_current(self, *, principal: str, quota: int, now: str) -> bool:
        window_started_at = datetime.fromisoformat(now).astimezone(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(consumed), 0) AS consumed FROM advanced_rate_windows WHERE principal = ? AND window_started_at = ?",
                (principal, window_started_at),
            ).fetchone()
        assert row is not None
        return int(row["consumed"]) <= quota

    def count_rate_consumptions(self, *, principal: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(consumed), 0) AS consumed FROM advanced_rate_windows WHERE principal = ?", (principal,)
            ).fetchone()
        assert row is not None
        return int(row["consumed"])

    def list_security_audits(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM advanced_security_audit ORDER BY rowid").fetchall()
        return [dict(row) for row in rows]

    def append_sandbox_validation(self, *, contract_fingerprint: str, source_sha256: str, status: str, reason: str, audit_reference: str) -> dict[str, Any]:
        identifier = str(uuid4())
        with self._connection() as connection, connection:
            connection.execute(
                "INSERT INTO advanced_sandbox_validations (id, contract_fingerprint, source_sha256, status, reason, audit_reference, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identifier, contract_fingerprint, source_sha256, status, reason, audit_reference, self.now()),
            )
            row = connection.execute("SELECT * FROM advanced_sandbox_validations WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return dict(row)

    def list_sandbox_validations(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM advanced_sandbox_validations ORDER BY rowid").fetchall()
        return [dict(row) for row in rows]

    def get_sandbox_validation_by_audit_reference(self, audit_reference: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM advanced_sandbox_validations WHERE audit_reference = ?", (audit_reference,)
            ).fetchone()
        return None if row is None else dict(row)

    def append_sandbox_run(
        self,
        *,
        validation_id: str,
        runner_manifest: Mapping[str, Any],
        terminal_reason: str | None,
        artifact_reference: str | None,
    ) -> dict[str, Any]:
        identifier = str(uuid4())
        with self._connection() as connection, connection:
            connection.execute(
                "INSERT INTO advanced_sandbox_runs "
                "(id, validation_id, runner_manifest_json, terminal_reason, artifact_reference, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    validation_id,
                    _json(runner_manifest, "sandbox runner manifest"),
                    terminal_reason,
                    artifact_reference,
                    self.now(),
                ),
            )
            row = connection.execute("SELECT * FROM advanced_sandbox_runs WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return self._sandbox_run(dict(row))

    def get_sandbox_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM advanced_sandbox_runs WHERE id = ?", (run_id,)).fetchone()
        return None if row is None else self._sandbox_run(dict(row))

    @staticmethod
    def _sandbox_run(record: dict[str, Any]) -> dict[str, Any]:
        try:
            manifest = json.loads(str(record.pop("runner_manifest_json")))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("sandbox runner manifest is invalid") from error
        if not isinstance(manifest, dict):
            raise ValueError("sandbox runner manifest is invalid")
        return {**record, "runner_manifest": manifest}

    def transition_job(self, *, job_id: str, from_status: str, to_status: str, stage: str, rejection_reason: str | None = None, audit_reference: str | None = None) -> dict[str, Any]:
        """Perform the only legal fact-adjacent update: a guarded job cursor transition."""
        now = self.now()
        with self._connection() as connection, connection:
            changed = connection.execute(
                """UPDATE advanced_jobs SET status = ?, stage = ?, stage_recorded_at = ?, rejection_reason = ?, audit_reference = ?, updated_at = ?
                   WHERE id = ? AND status = ?""",
                (to_status, stage, now, rejection_reason, audit_reference, now, job_id, from_status),
            ).rowcount
            if changed != 1:
                raise ValueError("advanced job state changed; refresh and retry")
            row = connection.execute("SELECT * FROM advanced_jobs WHERE id = ?", (job_id,)).fetchone()
        assert row is not None
        return dict(row)

    def transition_job_with_audit(
        self,
        *,
        job_id: str,
        from_status: str,
        to_status: str,
        stage: str,
        decision: str,
        reason: str,
        authorization_id: str,
        rejection_reason: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Atomically persist a legal cursor transition and its audit fact."""
        now = self.now()
        reference = str(uuid4())
        with self._connection() as connection, connection:
            connection.execute(
                "INSERT INTO advanced_security_audit (id, authorization_id, job_id, reference, decision, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid4()), authorization_id, job_id, reference, decision, reason, now),
            )
            changed = connection.execute(
                """UPDATE advanced_jobs SET status = ?, stage = ?, stage_recorded_at = ?, rejection_reason = ?, audit_reference = ?, updated_at = ?
                   WHERE id = ? AND status = ?""",
                (to_status, stage, now, rejection_reason, reference, now, job_id, from_status),
            ).rowcount
            if changed != 1:
                raise ValueError("advanced job state changed; refresh and retry")
            job = connection.execute("SELECT * FROM advanced_jobs WHERE id = ?", (job_id,)).fetchone()
            audit = connection.execute("SELECT * FROM advanced_security_audit WHERE reference = ?", (reference,)).fetchone()
        assert job is not None and audit is not None
        return dict(job), dict(audit)

    def get_job_by_audit_reference(self, reference: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM advanced_jobs WHERE audit_reference = ?", (reference,)).fetchone()
        return None if row is None else dict(row)

    def get_security_audit(self, reference: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM advanced_security_audit WHERE reference = ?", (reference,)).fetchone()
        return None if row is None else dict(row)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM advanced_jobs WHERE id = ?", (job_id,)).fetchone()
        return None if row is None else dict(row)

    def list_runnable_jobs(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM advanced_jobs WHERE status IN ('queued', 'authorized', 'frozen', 'drafted', 'gates_complete', 'awaiting_review')").fetchall()
        return [dict(row) for row in rows]

    def append_security_audit(self, *, decision: str, reason: str, authorization_id: str | None = None, job_id: str | None = None, reference: str | None = None) -> dict[str, Any]:
        identifier = str(uuid4())
        audit_reference = reference or str(uuid4())
        with self._connection() as connection, connection:
            connection.execute(
                "INSERT INTO advanced_security_audit (id, authorization_id, job_id, reference, decision, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identifier, authorization_id, job_id, audit_reference, decision, reason, self.now()),
            )
            row = connection.execute("SELECT * FROM advanced_security_audit WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return dict(row)

    def count_promotions(self, *, candidate_id: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM advanced_promotions WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
        assert row is not None
        return int(row["count"])

    def append_viewpoint_version(
        self,
        *,
        viewpoint_id: str,
        source_profile: str,
        market_scope: str,
        instrument: str,
        policy_revision: str,
        policy_fingerprint: str,
        policy_snapshot: Mapping[str, Any],
        asset_type: str,
        published_at: str,
        direction: str,
        rating: str,
        conclusion: str,
        target_range: tuple[float, float],
        horizon_days: int,
        confidence: str,
        revision_kind: str,
        correction_reason: str | None,
        evaluation_window_days: int,
        benchmark: str,
        evidence: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Append the next immutable viewpoint version and its evidence atomically."""
        version_id = str(uuid4())
        with self._connection() as connection, connection:
            policy = connection.execute(
                "SELECT * FROM advanced_policy_revisions WHERE fingerprint = ?", (policy_fingerprint,)
            ).fetchone()
            if policy is None:
                policy_id = str(uuid4())
                connection.execute(
                    "INSERT INTO advanced_policy_revisions (id, revision, fingerprint, snapshot_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (policy_id, policy_revision, policy_fingerprint, _json(policy_snapshot, "policy snapshot"), self.now()),
                )
            else:
                policy_id = policy["id"]
            existing = connection.execute(
                "SELECT source_profile, market_scope, instrument FROM advanced_viewpoints WHERE id = ?", (viewpoint_id,)
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO advanced_viewpoints (id, source_profile, market_scope, instrument, created_at) VALUES (?, ?, ?, ?, ?)",
                    (viewpoint_id, source_profile, market_scope, instrument, self.now()),
                )
            elif tuple(existing) != (source_profile, market_scope, instrument):
                raise ValueError("viewpoint identity cannot change")
            next_version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM advanced_viewpoint_versions WHERE viewpoint_id = ?", (viewpoint_id,)
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO advanced_viewpoint_versions
                   (id, viewpoint_id, version, policy_revision_id, asset_type, published_at, direction, rating, conclusion,
                    target_low, target_high, horizon_days, confidence, revision_kind, correction_reason,
                    evaluation_window_days, benchmark, metric, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'relative_return', ?)""",
                (version_id, viewpoint_id, next_version, policy_id, asset_type, published_at, direction, rating, conclusion,
                 target_range[0], target_range[1], horizon_days, confidence, revision_kind, correction_reason,
                 evaluation_window_days, benchmark, self.now()),
            )
            for item in evidence:
                connection.execute(
                    "INSERT INTO advanced_viewpoint_evidence (viewpoint_version_id, evidence_reference, evidence_published_at, created_at) VALUES (?, ?, ?, ?)",
                    (version_id, item["id"], item.get("published_at"), self.now()),
                )
            connection.execute(
                """INSERT INTO advanced_viewpoint_evaluations
                   (id, viewpoint_version_id, status, reason, relative_return, coverage_start, coverage_end, created_at)
                   VALUES (?, ?, 'unevaluable', 'awaiting_governed_evaluation', NULL, NULL, NULL, ?)""",
                (str(uuid4()), version_id, self.now()),
            )
            row = connection.execute("SELECT * FROM advanced_viewpoint_versions WHERE id = ?", (version_id,)).fetchone()
        assert row is not None
        return dict(row)

    def viewpoint_versions(self, viewpoint_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT version.*, viewpoint.source_profile, viewpoint.market_scope, viewpoint.instrument,
                          policy.revision AS policy_version, policy.fingerprint AS policy_fingerprint,
                          evaluation.id AS evaluation_id, evaluation.status AS evaluation_status,
                          evaluation.reason AS evaluation_reason,
                          evaluation.relative_return AS evaluation_relative_return,
                          evaluation.coverage_start AS evaluation_coverage_start,
                          evaluation.coverage_end AS evaluation_coverage_end
                   FROM advanced_viewpoint_versions AS version
                   JOIN advanced_viewpoints AS viewpoint ON viewpoint.id = version.viewpoint_id
                   JOIN advanced_policy_revisions AS policy ON policy.id = version.policy_revision_id
                   LEFT JOIN advanced_viewpoint_evaluations AS evaluation
                     ON evaluation.id = (
                        SELECT latest.id
                        FROM advanced_viewpoint_evaluations AS latest
                        WHERE latest.viewpoint_version_id = version.id
                        ORDER BY latest.created_at DESC, latest.id DESC
                        LIMIT 1
                     )
                   WHERE version.viewpoint_id = ? ORDER BY version.version DESC""",
                (viewpoint_id,),
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                value = dict(row)
                evidence = connection.execute(
                    "SELECT evidence_reference, evidence_published_at FROM advanced_viewpoint_evidence WHERE viewpoint_version_id = ? ORDER BY id",
                    (value["id"],),
                ).fetchall()
                value["evidence"] = [
                    {"id": evidence_row["evidence_reference"], **({"published_at": evidence_row["evidence_published_at"]} if evidence_row["evidence_published_at"] else {})}
                    for evidence_row in evidence
                ]
                value["evaluation"] = None if value["evaluation_id"] is None else {
                    "status": value["evaluation_status"],
                    "reason": value["evaluation_reason"],
                    "relative_return": value["evaluation_relative_return"],
                    "coverage_start": value["evaluation_coverage_start"],
                    "coverage_end": value["evaluation_coverage_end"],
                    "window_days": value["evaluation_window_days"],
                    "benchmark": value["benchmark"],
                }
                result.append(value)
        return result

    def viewpoint_versions_for_instrument(self, instrument: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            viewpoint_ids = connection.execute(
                "SELECT id FROM advanced_viewpoints WHERE instrument = ? ORDER BY created_at DESC", (instrument,)
            ).fetchall()
        return [
            version
            for row in viewpoint_ids
            for version in self.viewpoint_versions(str(row["id"]))
        ]

    def viewpoint_version(self, version_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT version.*, viewpoint.source_profile, viewpoint.market_scope, viewpoint.instrument,
                          policy.revision AS policy_version, policy.fingerprint AS policy_fingerprint
                   FROM advanced_viewpoint_versions AS version
                   JOIN advanced_viewpoints AS viewpoint ON viewpoint.id = version.viewpoint_id
                   JOIN advanced_policy_revisions AS policy ON policy.id = version.policy_revision_id
                   WHERE version.id = ?""",
                (version_id,),
            ).fetchone()
        return None if row is None else dict(row)

    def append_viewpoint_evaluation(
        self, *, viewpoint_version_id: str, status: str, reason: str | None, relative_return: float | None,
        coverage_start: str | None, coverage_end: str | None, governed_input_fingerprint: str | None,
    ) -> dict[str, Any]:
        identifier = str(uuid4())
        with self._connection() as connection, connection:
            connection.execute(
                "INSERT INTO advanced_viewpoint_evaluations (id, viewpoint_version_id, status, reason, relative_return, coverage_start, coverage_end, governed_input_fingerprint, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, viewpoint_version_id, status, reason, relative_return, coverage_start, coverage_end, governed_input_fingerprint, self.now()),
            )
            row = connection.execute("SELECT * FROM advanced_viewpoint_evaluations WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return dict(row)

    def viewpoint_evaluations(self, source_profile: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT evaluation.*, version.confidence
                   FROM advanced_viewpoint_evaluations AS evaluation
                   JOIN advanced_viewpoint_versions AS version ON version.id = evaluation.viewpoint_version_id
                   JOIN advanced_viewpoints AS viewpoint ON viewpoint.id = version.viewpoint_id
                   WHERE viewpoint.source_profile = ? ORDER BY evaluation.coverage_start""",
                (source_profile,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _policy_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["snapshot"] = json.loads(value.pop("snapshot_json"))
        return value
