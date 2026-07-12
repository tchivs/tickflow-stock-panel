"""Append-only SQLite persistence for governed analysis records."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from app.analysis.schemas import FrozenEvidenceSnapshot
from app.operational.migrations import migrate_operational_db


def _now() -> str:
    return datetime.now(UTC).isoformat()


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

    def complete_run(self, run_id: str, *, audit_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._transition_run(
            run_id, from_status="running", to_status="completed", audit_metadata=audit_metadata
        )

    def record_run_failure(
        self, run_id: str, reason: str, *, audit_metadata: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        self._require_text(reason, "failure reason")
        now = _now()
        with self._connection() as connection, connection:
            updated = connection.execute(
                """UPDATE analysis_runs SET status = 'failed', failure_reason = ?, audit_metadata_json = ?, finished_at = ?
                   WHERE id = ? AND status IN ('queued', 'running')""",
                (reason, None if audit_metadata is None else _json(audit_metadata, "run audit metadata"), now, run_id),
            ).rowcount
            if updated != 1:
                raise ValueError("analysis run cannot be failed from its current state")
            row = connection.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        assert row is not None
        return dict(row)

    def _transition_run(
        self,
        run_id: str,
        *,
        from_status: str,
        to_status: str,
        audit_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        fields = "status = ?, started_at = ?" if to_status == "running" else "status = ?, audit_metadata_json = ?, finished_at = ?"
        with self._connection() as connection, connection:
            values: tuple[Any, ...]
            if to_status == "running":
                values = (to_status, now, run_id, from_status)
            else:
                values = (
                    to_status,
                    None if audit_metadata is None else _json(audit_metadata, "run audit metadata"),
                    now,
                    run_id,
                    from_status,
                )
            updated = connection.execute(
                f"UPDATE analysis_runs SET {fields} WHERE id = ? AND status = ?",
                values,
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

    def append_lifecycle_proposal(
        self,
        *,
        subject_kind: str,
        subject_key: str,
        prior_state: str,
        proposed_state: str,
        evidence: Mapping[str, Any],
        review_id: str | None = None,
    ) -> dict[str, Any]:
        """Append a non-authoritative review proposal with its frozen rule inputs."""
        self._require_text(subject_kind, "subject_kind")
        self._require_text(subject_key, "subject_key")
        self._require_text(prior_state, "prior_state")
        self._require_text(proposed_state, "proposed_state")
        identifier = review_id or str(uuid4())
        now = _now()
        with self._connection() as connection, connection:
            signal = connection.execute(
                "SELECT * FROM analysis_signals WHERE subject_kind = ? AND subject_key = ?",
                (subject_kind, subject_key),
            ).fetchone()
            if signal is None:
                signal_id = str(uuid4())
                connection.execute(
                    "INSERT INTO analysis_signals (id, subject_kind, subject_key, created_at) VALUES (?, ?, ?, ?)",
                    (signal_id, subject_kind, subject_key, now),
                )
            else:
                signal_id = str(signal["id"])
            connection.execute(
                """INSERT INTO analysis_signal_reviews
                   (id, signal_id, prior_state, proposed_state, evidence_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (identifier, signal_id, prior_state, proposed_state, _json(evidence, "lifecycle evidence"), now),
            )
            review = connection.execute("SELECT * FROM analysis_signal_reviews WHERE id = ?", (identifier,)).fetchone()
        assert review is not None
        return self._review_record(review)

    def get_lifecycle_review(self, review_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            review = connection.execute("SELECT * FROM analysis_signal_reviews WHERE id = ?", (review_id,)).fetchone()
        return None if review is None else self._review_record(review)

    def current_lifecycle_state(self, *, subject_kind: str, subject_key: str) -> str:
        with self._connection() as connection:
            event = connection.execute(
                """SELECT events.next_state FROM analysis_signal_events AS events
                   JOIN analysis_signals AS signals ON signals.id = events.signal_id
                   WHERE signals.subject_kind = ? AND signals.subject_key = ?
                   ORDER BY events.occurred_at DESC, events.created_at DESC, events.id DESC LIMIT 1""",
                (subject_kind, subject_key),
            ).fetchone()
        return "active" if event is None else str(event["next_state"])

    def list_events(self, *, subject_key: str, subject_kind: str = "instrument") -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT events.* FROM analysis_signal_events AS events
                   JOIN analysis_signals AS signals ON signals.id = events.signal_id
                   WHERE signals.subject_kind = ? AND signals.subject_key = ?
                   ORDER BY events.occurred_at, events.created_at, events.id""",
                (subject_kind, subject_key),
            ).fetchall()
        return [dict(row) for row in rows]

    def confirm_lifecycle_review(
        self,
        *,
        review_id: str,
        reviewer_principal: str,
        window_days: int,
        benchmark: str,
        metric: str,
    ) -> dict[str, Any]:
        """Atomically append a confirmed official event and its sole observation plan."""
        self._require_text(reviewer_principal, "reviewer principal")
        self._validate_observation_plan(window_days=window_days, benchmark=benchmark, metric=metric)
        now = _now()
        event_id = str(uuid4())
        plan_id = str(uuid4())
        with self._connection() as connection, connection:
            review = connection.execute("SELECT * FROM analysis_signal_reviews WHERE id = ?", (review_id,)).fetchone()
            if review is None:
                raise ValueError("lifecycle review not found")
            existing = connection.execute(
                "SELECT id FROM analysis_signal_events WHERE review_id = ?", (review_id,)
            ).fetchone()
            if existing is not None:
                raise ValueError("lifecycle review is already confirmed and immutable")
            current = connection.execute(
                """SELECT next_state FROM analysis_signal_events WHERE signal_id = ?
                   ORDER BY occurred_at DESC, created_at DESC, id DESC LIMIT 1""",
                (review["signal_id"],),
            ).fetchone()
            current_state = "active" if current is None else str(current["next_state"])
            if current_state != review["prior_state"]:
                raise ValueError("lifecycle review no longer matches current state")
            evidence = json.loads(review["evidence_json"])
            occurred_at = evidence.get("occurred_at") if isinstance(evidence, dict) else None
            if not isinstance(occurred_at, str) or not occurred_at:
                raise RuntimeError("stored lifecycle review lacks occurrence time")
            connection.execute(
                """INSERT INTO analysis_signal_events
                   (id, review_id, signal_id, prior_state, next_state, reviewer_principal, occurred_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, review_id, review["signal_id"], review["prior_state"], review["proposed_state"], reviewer_principal, occurred_at, now),
            )
            connection.execute(
                """INSERT INTO analysis_observation_plans
                   (id, review_id, event_id, window_days, benchmark, metric, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (plan_id, review_id, event_id, window_days, benchmark, metric, now),
            )
            event = connection.execute("SELECT * FROM analysis_signal_events WHERE id = ?", (event_id,)).fetchone()
            plan = connection.execute("SELECT * FROM analysis_observation_plans WHERE id = ?", (plan_id,)).fetchone()
        assert event is not None and plan is not None
        return {"event": dict(event), "plan": dict(plan)}

    def append_lifecycle_rejection(self, *, review_id: str, reviewer_principal: str) -> dict[str, Any]:
        """Append a rejection audit record without modifying the proposed or official state."""
        self._require_text(reviewer_principal, "reviewer principal")
        review = self.get_lifecycle_review(review_id)
        if review is None:
            raise ValueError("lifecycle review not found")
        if self._review_has_event(review_id):
            raise ValueError("confirmed lifecycle review cannot be rejected")
        return self.append_lifecycle_proposal(
            subject_kind=self._signal_subject_kind(review["signal_id"]),
            subject_key=self._signal_subject_key(review["signal_id"]),
            prior_state=review["prior_state"],
            proposed_state="rejected",
            evidence={
                "disposition": "rejected",
                "rejected_review_id": review_id,
                "reviewer_principal": reviewer_principal,
                "recorded_at": _now(),
            },
        )

    def list_observation_plans(self, review_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_observation_plans WHERE review_id = ? ORDER BY created_at, id", (review_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def append_observation_outcome(self, *, plan_id: str, outcome: Mapping[str, Any]) -> dict[str, Any]:
        payload = _payload(outcome, "observation outcome")
        now = _now()
        identifier = str(uuid4())
        with self._connection() as connection, connection:
            plan = connection.execute("SELECT id FROM analysis_observation_plans WHERE id = ?", (plan_id,)).fetchone()
            if plan is None:
                raise ValueError("observation plan not found")
            connection.execute(
                """INSERT INTO analysis_observation_outcomes (id, plan_id, observed_at, outcome_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (identifier, plan_id, now, _json(payload, "observation outcome"), now),
            )
            row = connection.execute("SELECT * FROM analysis_observation_outcomes WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        value = dict(row)
        value["outcome"] = json.loads(value.pop("outcome_json"))
        return value

    def list_observation_outcomes(self, plan_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_observation_outcomes WHERE plan_id = ? ORDER BY observed_at, created_at, id",
                (plan_id,),
            ).fetchall()
        return [{**dict(row), "outcome": json.loads(row["outcome_json"])} for row in rows]

    @staticmethod
    def replace_observation_plan(*, plan_id: str, window_days: int) -> None:
        del plan_id, window_days
        raise ValueError("observation plan is immutable")

    def _review_has_event(self, review_id: str) -> bool:
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM analysis_signal_events WHERE review_id = ?", (review_id,)).fetchone() is not None

    def _signal_subject_kind(self, signal_id: str) -> str:
        with self._connection() as connection:
            row = connection.execute("SELECT subject_kind FROM analysis_signals WHERE id = ?", (signal_id,)).fetchone()
        if row is None:
            raise RuntimeError("lifecycle signal not found")
        return str(row["subject_kind"])

    def _signal_subject_key(self, signal_id: str) -> str:
        with self._connection() as connection:
            row = connection.execute("SELECT subject_key FROM analysis_signals WHERE id = ?", (signal_id,)).fetchone()
        if row is None:
            raise RuntimeError("lifecycle signal not found")
        return str(row["subject_key"])

    @staticmethod
    def _validate_observation_plan(*, window_days: int, benchmark: str, metric: str) -> None:
        if window_days not in {20, 60, 120}:
            raise ValueError("observation window must be 20, 60, or 120 trading days")
        if not isinstance(benchmark, str) or not benchmark.strip():
            raise ValueError("observation benchmark is required")
        if not isinstance(metric, str) or not metric.strip():
            raise ValueError("observation metric is required")

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
    def _review_record(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        payload = json.loads(value.pop("evidence_json"))
        if not isinstance(payload, dict):
            raise RuntimeError("stored lifecycle review evidence is malformed")
        value.update(payload)
        return value

    @staticmethod
    def _require_text(value: object, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
