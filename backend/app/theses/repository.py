"""Transactional append-only repository for immutable thesis facts."""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from app.operational.migrations import migrate_operational_db
from app.theses.schemas import (
    ConditionCheckResult,
    ThesisCondition,
    ThesisRevisionRequest,
    ThesisVersionRequest,
    ValuationAnchor,
)


class ThesisRepository:
    """Own short-lived connections and append-only Thesis transactions."""

    def __init__(self, database_path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.database_path = Path(database_path)
        self._clock = clock or (lambda: datetime.now(UTC))
        self.migrate()

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

    def create_version(self, *, request: ThesisVersionRequest, created_by: str) -> dict[str, Any]:
        """Atomically create one identity, version, anchors, conditions, and schedules."""
        principal = _required_text(created_by, "created_by", maximum=256)
        thesis_id = uuid4().hex
        version_id = uuid4().hex
        created_at = self.now()
        try:
            with self._connection() as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO theses (id, instrument, created_by, created_at) VALUES (?, ?, ?, ?)",
                    (thesis_id, request.instrument, principal, created_at),
                )
                connection.execute(
                    """INSERT INTO thesis_versions
                       (id, thesis_id, version, predecessor_id, core_judgment, rationale,
                        change_reason, created_by, created_at)
                       VALUES (?, ?, 1, NULL, ?, ?, ?, ?, ?)""",
                    (
                        version_id,
                        thesis_id,
                        request.core_judgment,
                        request.rationale,
                        request.change_reason,
                        principal,
                        created_at,
                    ),
                )
                self._append_anchors(connection, version_id, request.anchors, created_at)
                self._append_conditions(connection, version_id, request.conditions, created_at)
                persisted = self._version(connection, version_id)
        except sqlite3.IntegrityError as error:
            if "theses.instrument" in str(error) or "UNIQUE constraint failed: theses.instrument" in str(error):
                raise ValueError("a thesis already exists for this instrument") from error
            raise
        assert persisted is not None
        return persisted

    def revise_version(
        self,
        *,
        thesis_id: str,
        request: ThesisRevisionRequest,
        created_by: str,
    ) -> dict[str, Any]:
        """Append a revision only when its expected predecessor is still current."""
        thesis_identifier = _required_identifier(thesis_id, "thesis_id")
        principal = _required_text(created_by, "created_by", maximum=256)
        version_id = uuid4().hex
        created_at = self.now()
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            current_row = self._current_row(connection, thesis_identifier)
            if current_row is None:
                raise ValueError("thesis not found")
            if current_row["id"] != request.expected_predecessor_id:
                raise ValueError("stale predecessor conflict; refresh the current thesis version")
            current = self._version(connection, current_row["id"])
            assert current is not None

            core_judgment = request.core_judgment if request.core_judgment is not None else current["core_judgment"]
            rationale = request.rationale if request.rationale is not None else current["rationale"]
            anchors: Sequence[ValuationAnchor | Mapping[str, Any]] = (
                request.anchors if request.anchors is not None else current["anchors"]
            )
            copied_conditions = request.conditions is None
            conditions: Sequence[ThesisCondition | Mapping[str, Any]] = (
                request.conditions if request.conditions is not None else current["conditions"]
            )

            connection.execute(
                """INSERT INTO thesis_versions
                   (id, thesis_id, version, predecessor_id, core_judgment, rationale,
                    change_reason, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    thesis_identifier,
                    int(current_row["version"]) + 1,
                    request.expected_predecessor_id,
                    core_judgment,
                    rationale,
                    request.change_reason,
                    principal,
                    created_at,
                ),
            )
            self._append_anchors(connection, version_id, anchors, created_at)
            self._append_conditions(
                connection,
                version_id,
                conditions,
                created_at,
                copied_from_existing=copied_conditions,
            )
            self._deactivate_version_schedules(connection, current_row["id"], created_at)
            persisted = self._version(connection, version_id)
        assert persisted is not None
        return persisted

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._version(connection, version_id)

    def list_versions(self, thesis_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT id FROM thesis_versions WHERE thesis_id = ?
                   ORDER BY version DESC, created_at DESC, id DESC""",
                (thesis_id,),
            ).fetchall()
            return [version for row in rows if (version := self._version(connection, row["id"])) is not None]

    def list_for_instrument(self, instrument: str) -> list[dict[str, Any]]:
        """Return deterministic latest projections for the exact persisted instrument."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT id FROM theses WHERE instrument = ? ORDER BY created_at DESC, id DESC""",
                (instrument.strip().upper(),),
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                current = self._current_row(connection, row["id"])
                if current is not None:
                    projection = self._version(connection, current["id"])
                    if projection is not None:
                        result.append(projection)
            return result

    def current_version(self, thesis_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = self._current_row(connection, thesis_id)
            return None if row is None else self._version(connection, row["id"])

    def current_version_for_instrument(self, instrument: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            thesis = connection.execute(
                "SELECT id FROM theses WHERE instrument = ?",
                (instrument.strip().upper(),),
            ).fetchone()
            if thesis is None:
                return None
            row = self._current_row(connection, thesis["id"])
            return None if row is None else self._version(connection, row["id"])

    def get_schedule(self, condition_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM thesis_condition_schedules WHERE condition_id = ?",
                (condition_id,),
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        value["active"] = bool(value["active"])
        return value

    def append_condition_check(
        self,
        *,
        version_id: str,
        condition_id: str,
        due_at: str,
        result: str | ConditionCheckResult,
        evidence_fingerprint: str,
        evidence: Sequence[Mapping[str, Any]],
        checked_at: str,
        observed_value: object | None = None,
        safe_reason: str | None = None,
    ) -> dict[str, Any]:
        """Append one immutable check tied to the exact condition/version pair."""
        result_value = result.value if isinstance(result, ConditionCheckResult) else result
        try:
            ConditionCheckResult(result_value)
        except ValueError as error:
            raise ValueError("condition check result is invalid") from error
        _fingerprint(evidence_fingerprint)
        evidence_json = _canonical_json(list(evidence), "evidence", maximum=64_000)
        observed_json = None if observed_value is None else _canonical_json(observed_value, "observed_value", maximum=4_000)
        identifier = uuid4().hex
        reason = None if safe_reason is None else _required_text(safe_reason, "safe_reason", maximum=500)
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO thesis_condition_checks
                   (id, version_id, condition_id, due_at, result, observed_value_json,
                    evidence_fingerprint, evidence_json, safe_reason, checked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    identifier,
                    version_id,
                    condition_id,
                    _timestamp(due_at, "due_at"),
                    result_value,
                    observed_json,
                    evidence_fingerprint,
                    evidence_json,
                    reason,
                    _timestamp(checked_at, "checked_at"),
                ),
            )
            row = connection.execute(
                "SELECT * FROM thesis_condition_checks WHERE id = ?", (identifier,)
            ).fetchone()
        assert row is not None
        return self._check_projection(row)

    def list_checks(self, condition_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM thesis_condition_checks WHERE condition_id = ?
                   ORDER BY due_at DESC, checked_at DESC, id DESC""",
                (condition_id,),
            ).fetchall()
        return [self._check_projection(row) for row in rows]

    @staticmethod
    def _current_row(connection: sqlite3.Connection, thesis_id: str) -> sqlite3.Row | None:
        return connection.execute(
            """SELECT version.* FROM thesis_versions AS version
               WHERE version.thesis_id = ?
                 AND NOT EXISTS (
                     SELECT 1 FROM thesis_versions AS successor
                     WHERE successor.thesis_id = version.thesis_id
                       AND successor.predecessor_id = version.id
                 )
               ORDER BY version.version DESC, version.created_at DESC, version.id DESC
               LIMIT 1""",
            (thesis_id,),
        ).fetchone()

    def _version(self, connection: sqlite3.Connection, version_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            """SELECT version.*, thesis.instrument
               FROM thesis_versions AS version
               JOIN theses AS thesis ON thesis.id = version.thesis_id
               WHERE version.id = ?""",
            (version_id,),
        ).fetchone()
        if row is None:
            return None
        anchors = connection.execute(
            """SELECT method, currency, as_of, low, high, assumptions_json, limitations_json
               FROM thesis_valuation_anchors WHERE version_id = ?
               ORDER BY created_at ASC, id ASC""",
            (version_id,),
        ).fetchall()
        conditions = connection.execute(
            """SELECT id, copied_from_condition_id, source_kind, field, operator,
                      threshold_json, unit, lookback_days, cadence, timezone, description
               FROM thesis_conditions WHERE version_id = ?
               ORDER BY created_at ASC, id ASC""",
            (version_id,),
        ).fetchall()
        return {
            "id": row["id"],
            "thesis_id": row["thesis_id"],
            "instrument": row["instrument"],
            "version": row["version"],
            "predecessor_id": row["predecessor_id"],
            "core_judgment": row["core_judgment"],
            "rationale": row["rationale"],
            "change_reason": row["change_reason"],
            "anchors": [
                {
                    "method": anchor["method"],
                    "currency": anchor["currency"],
                    "as_of": anchor["as_of"],
                    "low": anchor["low"],
                    "high": anchor["high"],
                    "assumptions": json.loads(anchor["assumptions_json"]),
                    "limitations": json.loads(anchor["limitations_json"]),
                }
                for anchor in anchors
            ],
            "conditions": [self._condition_projection(condition) for condition in conditions],
            "official_state": self._official_state(connection, row["thesis_id"], row["id"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _official_state(connection: sqlite3.Connection, thesis_id: str, version_id: str) -> str:
        confirmed = connection.execute(
            """SELECT 1 FROM thesis_review_events AS review
               JOIN thesis_pending_conclusions AS pending ON pending.id = review.pending_id
               WHERE pending.thesis_id = ? AND pending.version_id = ?
                 AND review.decision = 'confirmed'
               ORDER BY review.created_at ASC, review.id ASC LIMIT 1""",
            (thesis_id, version_id),
        ).fetchone()
        return "invalidated" if confirmed is not None else "active"

    @staticmethod
    def _append_anchors(
        connection: sqlite3.Connection,
        version_id: str,
        anchors: Sequence[ValuationAnchor | Mapping[str, Any]],
        created_at: str,
    ) -> None:
        for anchor in anchors:
            value = anchor.model_dump(mode="json") if isinstance(anchor, ValuationAnchor) else dict(anchor)
            validated = ValuationAnchor.model_validate(value)
            connection.execute(
                """INSERT INTO thesis_valuation_anchors
                   (id, version_id, method, currency, as_of, low, high,
                    assumptions_json, limitations_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid4().hex,
                    version_id,
                    validated.method,
                    validated.currency,
                    validated.as_of.isoformat(),
                    validated.low,
                    validated.high,
                    _canonical_json(
                        [item.model_dump(mode="json") for item in validated.assumptions],
                        "assumptions",
                        maximum=16_000,
                    ),
                    _canonical_json(validated.limitations, "limitations", maximum=16_000),
                    created_at,
                ),
            )

    @staticmethod
    def _append_conditions(
        connection: sqlite3.Connection,
        version_id: str,
        conditions: Sequence[ThesisCondition | Mapping[str, Any]],
        created_at: str,
        *,
        copied_from_existing: bool = False,
    ) -> None:
        for condition in conditions:
            value = condition.model_dump(mode="json") if isinstance(condition, ThesisCondition) else dict(condition)
            copied_from = value.pop("id", None) if copied_from_existing else None
            value.pop("copied_from_condition_id", None)
            validated = ThesisCondition.model_validate(value)
            condition_id = uuid4().hex
            connection.execute(
                """INSERT INTO thesis_conditions
                   (id, version_id, copied_from_condition_id, source_kind, field, operator,
                    threshold_json, unit, lookback_days, cadence, timezone, description, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    condition_id,
                    version_id,
                    copied_from,
                    validated.source_kind,
                    validated.field,
                    validated.operator,
                    _canonical_json(validated.threshold, "threshold", maximum=256),
                    validated.unit,
                    validated.lookback_days,
                    validated.cadence,
                    validated.timezone,
                    validated.description,
                    created_at,
                ),
            )
            connection.execute(
                """INSERT INTO thesis_condition_schedules
                   (condition_id, active, next_due_at, lease_owner, lease_until,
                    last_attempt_at, transition_version, created_at, updated_at)
                   VALUES (?, 1, ?, NULL, NULL, NULL, 0, ?, ?)""",
                (condition_id, created_at, created_at, created_at),
            )

    @staticmethod
    def _deactivate_version_schedules(
        connection: sqlite3.Connection, version_id: str, updated_at: str
    ) -> None:
        connection.execute(
            """UPDATE thesis_condition_schedules
               SET active = 0, lease_owner = NULL, lease_until = NULL,
                   transition_version = transition_version + 1, updated_at = ?
               WHERE active = 1 AND condition_id IN (
                   SELECT id FROM thesis_conditions WHERE version_id = ?
               )""",
            (updated_at, version_id),
        )

    @staticmethod
    def _condition_projection(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "copied_from_condition_id": row["copied_from_condition_id"],
            "source_kind": row["source_kind"],
            "field": row["field"],
            "operator": row["operator"],
            "threshold": json.loads(row["threshold_json"]),
            "unit": row["unit"],
            "lookback_days": row["lookback_days"],
            "cadence": row["cadence"],
            "timezone": row["timezone"],
            "description": row["description"],
        }

    @staticmethod
    def _check_projection(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "version_id": row["version_id"],
            "condition_id": row["condition_id"],
            "due_at": row["due_at"],
            "result": row["result"],
            "observed_value": None
            if row["observed_value_json"] is None
            else json.loads(row["observed_value_json"]),
            "evidence_fingerprint": row["evidence_fingerprint"],
            "evidence": json.loads(row["evidence_json"]),
            "safe_reason": row["safe_reason"],
            "checked_at": row["checked_at"],
        }


def _required_identifier(value: str, field: str) -> str:
    return _required_text(value, field, maximum=128)


def _required_text(value: str, field: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()) or len(normalized) > maximum:
        raise ValueError(f"{field} must be non-empty bounded text")
    return normalized


def _canonical_json(value: object, field: str, *, maximum: int) -> str:
    try:
        serialized = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be canonical finite JSON") from error
    if len(serialized.encode("utf-8")) > maximum:
        raise ValueError(f"{field} exceeds its canonical JSON limit")
    return serialized


def _fingerprint(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("evidence fingerprint must be 64 lowercase hexadecimal characters")
    return value


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat()
