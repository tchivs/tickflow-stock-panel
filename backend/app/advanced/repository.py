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

    @staticmethod
    def _policy_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["snapshot"] = json.loads(value.pop("snapshot_json"))
        return value
