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
                          policy.revision AS policy_version, policy.fingerprint AS policy_fingerprint
                   FROM advanced_viewpoint_versions AS version
                   JOIN advanced_viewpoints AS viewpoint ON viewpoint.id = version.viewpoint_id
                   JOIN advanced_policy_revisions AS policy ON policy.id = version.policy_revision_id
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
                result.append(value)
        return result

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
        coverage_start: str | None, coverage_end: str | None,
    ) -> dict[str, Any]:
        identifier = str(uuid4())
        with self._connection() as connection, connection:
            connection.execute(
                "INSERT INTO advanced_viewpoint_evaluations (id, viewpoint_version_id, status, reason, relative_return, coverage_start, coverage_end, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, viewpoint_version_id, status, reason, relative_return, coverage_start, coverage_end, self.now()),
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
