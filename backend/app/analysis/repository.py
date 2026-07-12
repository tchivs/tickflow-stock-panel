"""Append-only SQLite persistence for governed analysis records."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping
from uuid import uuid4

from pydantic import BaseModel

from app.analysis.schemas import FrozenEvidenceSnapshot
from app.operational.migrations import migrate_operational_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object, field: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be JSON serializable") from error


def _payload(value: Mapping[str, Any] | BaseModel, field: str) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError(f"{field} must be a mapping")


class AnalysisRepository:
    """Parameterized short-lived connections over the shared operational database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

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

    def acquire_run(self, *, run_id: str, subject_kind: str, subject_key: str, focus: str) -> dict[str, Any]:
        """Atomically return an existing active run or append a queued run."""
        self._require_text(run_id, "run_id")
        self._require_text(subject_kind, "subject_kind")
        self._require_text(subject_key, "subject_key")
        if not isinstance(focus, str):
            raise ValueError("focus must be text")
        now = _now()
        with self._connection() as connection, connection:
            active = connection.execute(
                """SELECT * FROM analysis_runs WHERE subject_kind = ? AND subject_key = ?
                   AND status IN ('queued', 'running') ORDER BY created_at DESC, id DESC LIMIT 1""",
                (subject_kind, subject_key),
            ).fetchone()
            if active is not None:
                return dict(active)
            try:
                connection.execute(
                    """INSERT INTO analysis_runs (id, subject_kind, subject_key, focus, status, created_at)
                       VALUES (?, ?, ?, ?, 'queued', ?)""",
                    (run_id, subject_kind, subject_key, focus, now),
                )
            except sqlite3.IntegrityError as error:
                active = connection.execute(
                    """SELECT * FROM analysis_runs WHERE subject_kind = ? AND subject_key = ?
                       AND status IN ('queued', 'running') ORDER BY created_at DESC, id DESC LIMIT 1""",
                    (subject_kind, subject_key),
                ).fetchone()
                if active is not None:
                    return dict(active)
                raise ValueError("could not acquire analysis run") from error
            row = connection.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        assert row is not None
        return dict(row)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        return None if row is None else dict(row)

    def mark_run_running(self, run_id: str) -> dict[str, Any]:
        return self._transition_run(run_id, from_status="queued", to_status="running")

    def complete_run(self, run_id: str) -> dict[str, Any]:
        return self._transition_run(run_id, from_status="running", to_status="completed")

    def record_run_failure(self, run_id: str, reason: str) -> dict[str, Any]:
        self._require_text(reason, "failure reason")
        now = _now()
        with self._connection() as connection, connection:
            updated = connection.execute(
                """UPDATE analysis_runs SET status = 'failed', failure_reason = ?, finished_at = ?
                   WHERE id = ? AND status IN ('queued', 'running')""",
                (reason, now, run_id),
            ).rowcount
            if updated != 1:
                raise ValueError("analysis run cannot be failed from its current state")
            row = connection.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        assert row is not None
        return dict(row)

    def _transition_run(self, run_id: str, *, from_status: str, to_status: str) -> dict[str, Any]:
        now = _now()
        fields = "status = ?, started_at = ?" if to_status == "running" else "status = ?, finished_at = ?"
        with self._connection() as connection, connection:
            updated = connection.execute(
                f"UPDATE analysis_runs SET {fields} WHERE id = ? AND status = ?",
                (to_status, now, run_id, from_status),
            ).rowcount
            if updated != 1:
                raise ValueError(f"analysis run cannot transition from {from_status} to {to_status}")
            row = connection.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        assert row is not None
        return dict(row)

    def record_frozen_snapshot(
        self,
        *,
        run_id: str,
        snapshot: FrozenEvidenceSnapshot | Mapping[str, Any],
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        """Append the full frozen snapshot plus normalized source and number observations."""
        parsed = FrozenEvidenceSnapshot.model_validate(_payload(snapshot, "frozen evidence snapshot"))
        identifier = snapshot_id or str(uuid4())
        payload = parsed.model_dump(mode="json")
        now = _now()
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO analysis_evidence_snapshots
                   (id, run_id, policy_version, context_status, fingerprint, snapshot_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (identifier, run_id, parsed.policy_version, parsed.context_status, parsed.evidence_fingerprint, _json(payload, "frozen evidence snapshot"), now),
            )
            for source in parsed.sources:
                value = source.model_dump(mode="json")
                connection.execute(
                    """INSERT INTO analysis_source_observations
                       (snapshot_id, source_id, grade, origin, independence_group, retrieved_at, as_of,
                        period, unit, definition, provenance_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (identifier, value["source_id"], value["grade"], value["origin"], value["independence_group"], value["retrieved_at"], value["as_of"], value["period"], value["unit"], value["definition"], _json(value["provenance"], "source provenance"), now),
                )
            for number in parsed.material_numbers:
                value = number.model_dump(mode="json")
                connection.execute(
                    """INSERT INTO analysis_number_observations
                       (snapshot_id, number_id, source_id, value, unit, period, definition, status,
                        peer_source_ids_json, comparison_reason, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (identifier, value["number_id"], value["source_id"], value["value"], value["unit"], value["period"], value["definition"], value["status"], _json(value["peer_source_ids"], "number peers"), value["comparison_reason"], now),
                )
            row = connection.execute("SELECT * FROM analysis_evidence_snapshots WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return self._snapshot_record(row)

    def get_frozen_snapshot(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM analysis_evidence_snapshots WHERE run_id = ?", (run_id,)).fetchone()
        return None if row is None else self._snapshot_record(row)

    def append_validated_report(
        self,
        *,
        subject_kind: str,
        subject_key: str,
        report: Mapping[str, Any] | BaseModel,
        run_id: str | None = None,
        report_id: str | None = None,
    ) -> dict[str, Any]:
        """Append a new immutable report version; never overwrite historical prose."""
        self._require_text(subject_kind, "subject_kind")
        self._require_text(subject_key, "subject_key")
        if run_id is not None:
            self._require_text(run_id, "run_id")
        identifier = report_id or str(uuid4())
        payload = _payload(report, "validated report")
        now = _now()
        with self._connection() as connection, connection:
            version = int(connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM analysis_reports WHERE subject_kind = ? AND subject_key = ?",
                (subject_kind, subject_key),
            ).fetchone()[0]) + 1
            connection.execute(
                """INSERT INTO analysis_reports (id, run_id, subject_kind, subject_key, version, report_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (identifier, run_id, subject_kind, subject_key, version, _json(payload, "validated report"), now),
            )
            row = connection.execute("SELECT * FROM analysis_reports WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return self._report_record(row)

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM analysis_reports WHERE id = ?", (report_id,)).fetchone()
        return None if row is None else self._report_record(row)

    def list_reports(self, subject_kind: str, subject_key: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM analysis_reports WHERE subject_kind = ? AND subject_key = ?
                   ORDER BY version DESC, created_at DESC, id DESC""",
                (subject_kind, subject_key),
            ).fetchall()
        return [self._report_record(row) for row in rows]

    @staticmethod
    def _snapshot_record(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["snapshot"] = json.loads(value.pop("snapshot_json"))
        return value

    @staticmethod
    def _report_record(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["report"] = json.loads(value.pop("report_json"))
        return value

    @staticmethod
    def _require_text(value: object, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
