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

    def __init__(
        self,
        database_path: Path,
        *,
        clock: Callable[[], datetime | str] | None = None,
        now: Callable[[], datetime | str] | None = None,
    ) -> None:
        if clock is not None and now is not None:
            raise ValueError("provide only one Thesis repository clock")
        self.database_path = Path(database_path)
        self._clock = clock or now or (lambda: datetime.now(UTC))
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
        return _timestamp(self._clock(), "clock")

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

    def page_versions_for_instrument(
        self, instrument: str, *, offset: int, limit: int
    ) -> dict[str, Any]:
        """Page immutable versions after exact instrument ownership filtering."""
        canonical = _required_instrument(instrument)
        page_offset, page_limit = _page_bounds(offset, limit)
        with self._connection() as connection:
            total = int(
                connection.execute(
                    """SELECT COUNT(*)
                       FROM thesis_versions AS version
                       JOIN theses AS thesis ON thesis.id = version.thesis_id
                       WHERE thesis.instrument = ?""",
                    (canonical,),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """SELECT version.id
                   FROM thesis_versions AS version
                   JOIN theses AS thesis ON thesis.id = version.thesis_id
                   WHERE thesis.instrument = ?
                   ORDER BY version.version DESC, version.created_at DESC, version.id DESC
                   LIMIT ? OFFSET ?""",
                (canonical, page_limit, page_offset),
            ).fetchall()
            items = [
                version
                for row in rows
                if (version := self._version(connection, row["id"])) is not None
            ]
        return _page_result(items, offset=page_offset, limit=page_limit, total=total)

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

    def get_condition(self, condition_id: str) -> dict[str, Any] | None:
        """Return one persisted condition with its immutable version and instrument scope."""
        with self._connection() as connection:
            row = connection.execute(
                """SELECT condition.*, version.thesis_id, thesis.instrument
                   FROM thesis_conditions AS condition
                   JOIN thesis_versions AS version ON version.id = condition.version_id
                   JOIN theses AS thesis ON thesis.id = version.thesis_id
                   WHERE condition.id = ?""",
                (_required_identifier(condition_id, "condition_id"),),
            ).fetchone()
        if row is None:
            return None
        return {
            **self._condition_projection(row),
            "version_id": row["version_id"],
            "thesis_id": row["thesis_id"],
            "instrument": row["instrument"],
        }

    def acquire_due_conditions(
        self,
        *,
        now: datetime,
        owner: str,
        lease_until: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Lease a stable bounded batch of due current-version conditions."""
        owner_value = _required_text(owner, "owner", maximum=128)
        now_value = _timestamp(now, "now")
        lease_value = _timestamp(lease_until, "lease_until")
        if lease_value <= now_value:
            raise ValueError("lease_until must be later than now")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256:
            raise ValueError("limit must be between 1 and 256")
        acquired: list[dict[str, Any]] = []
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            # Expiry recovery is a separate guarded transition because lease ownership
            # cannot be transferred directly by the schedule trigger.
            connection.execute(
                """UPDATE thesis_condition_schedules
                   SET lease_owner = NULL, lease_until = NULL,
                       transition_version = transition_version + 1, updated_at = ?
                   WHERE active = 1 AND lease_until IS NOT NULL AND lease_until <= ?""",
                (now_value, now_value),
            )
            rows = connection.execute(
                """SELECT schedule.condition_id, schedule.next_due_at,
                          schedule.transition_version
                   FROM thesis_condition_schedules AS schedule
                   JOIN thesis_conditions AS condition ON condition.id = schedule.condition_id
                   JOIN thesis_versions AS version ON version.id = condition.version_id
                   WHERE schedule.active = 1
                     AND schedule.next_due_at <= ?
                     AND schedule.lease_owner IS NULL
                     AND NOT EXISTS (
                         SELECT 1 FROM thesis_versions AS successor
                         WHERE successor.thesis_id = version.thesis_id
                           AND successor.predecessor_id = version.id
                     )
                   ORDER BY schedule.next_due_at ASC, schedule.condition_id ASC
                   LIMIT ?""",
                (now_value, limit),
            ).fetchall()
            for row in rows:
                changed = connection.execute(
                    """UPDATE thesis_condition_schedules
                       SET lease_owner = ?, lease_until = ?, last_attempt_at = ?,
                           transition_version = transition_version + 1, updated_at = ?
                       WHERE condition_id = ? AND active = 1 AND next_due_at = ?
                         AND lease_owner IS NULL AND transition_version = ?""",
                    (
                        owner_value,
                        lease_value,
                        now_value,
                        now_value,
                        row["condition_id"],
                        row["next_due_at"],
                        row["transition_version"],
                    ),
                ).rowcount
                if changed == 1:
                    acquired.append(
                        {
                            "condition_id": row["condition_id"],
                            "due_at": row["next_due_at"],
                            "lease_owner": owner_value,
                            "lease_until": lease_value,
                        }
                    )
        return acquired

    def complete_due_condition(
        self,
        *,
        condition_id: str,
        due_at: str,
        owner: str,
        next_due_at: str,
        completed_at: str,
    ) -> bool:
        """Advance exactly the lease that produced a canonical due check."""
        condition_value = _required_identifier(condition_id, "condition_id")
        due_value = _timestamp(due_at, "due_at")
        next_value = _timestamp(next_due_at, "next_due_at")
        completed_value = _timestamp(completed_at, "completed_at")
        if next_value <= due_value:
            raise ValueError("next_due_at must advance monotonically")
        with self._connection() as connection, connection:
            changed = connection.execute(
                """UPDATE thesis_condition_schedules
                   SET next_due_at = ?, lease_owner = NULL, lease_until = NULL,
                       transition_version = transition_version + 1, updated_at = ?
                   WHERE condition_id = ? AND active = 1 AND next_due_at = ?
                     AND lease_owner = ?""",
                (
                    next_value,
                    completed_value,
                    condition_value,
                    due_value,
                    _required_text(owner, "owner", maximum=128),
                ),
            ).rowcount
        return changed == 1

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
        """Append one immutable check or return the canonical due identity."""
        result_value = result.value if isinstance(result, ConditionCheckResult) else result
        try:
            ConditionCheckResult(result_value)
        except ValueError as error:
            raise ValueError("condition check result is invalid") from error
        _fingerprint(evidence_fingerprint)
        evidence_json = _canonical_json(list(evidence), "evidence", maximum=64_000)
        observed_json = (
            None
            if observed_value is None
            else _canonical_json(observed_value, "observed_value", maximum=4_000)
        )
        identifier = uuid4().hex
        reason = None if safe_reason is None else _required_text(safe_reason, "safe_reason", maximum=500)
        due_value = _timestamp(due_at, "due_at")
        try:
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
                        due_value,
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
        except sqlite3.IntegrityError as error:
            with self._connection() as connection:
                row = connection.execute(
                    """SELECT * FROM thesis_condition_checks
                       WHERE condition_id = ? AND due_at = ?""",
                    (condition_id, due_value),
                ).fetchone()
            if row is None:
                raise error
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

    def page_checks_for_instrument(
        self, instrument: str, *, offset: int, limit: int
    ) -> dict[str, Any]:
        """Page immutable checks across every version of one exact instrument."""
        canonical = _required_instrument(instrument)
        page_offset, page_limit = _page_bounds(offset, limit)
        joins = """FROM thesis_condition_checks AS condition_check
                   JOIN thesis_conditions AS condition
                     ON condition.id = condition_check.condition_id
                   JOIN thesis_versions AS version ON version.id = condition.version_id
                   JOIN theses AS thesis ON thesis.id = version.thesis_id
                   WHERE thesis.instrument = ?"""
        with self._connection() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) {joins}", (canonical,)).fetchone()[0])
            rows = connection.execute(
                f"""SELECT condition_check.* {joins}
                    ORDER BY condition_check.due_at DESC,
                             condition_check.checked_at DESC,
                             condition_check.id DESC
                    LIMIT ? OFFSET ?""",
                (canonical, page_limit, page_offset),
            ).fetchall()
        items = [self._check_projection(row) for row in rows]
        return _page_result(items, offset=page_offset, limit=page_limit, total=total)

    def condition_outcome(self, condition_id: str, due_at: str) -> dict[str, Any] | None:
        """Return the canonical check and optional pending fact for one due identity."""
        with self._connection() as connection:
            check = connection.execute(
                """SELECT * FROM thesis_condition_checks
                   WHERE condition_id = ? AND due_at = ?""",
                (
                    _required_identifier(condition_id, "condition_id"),
                    _timestamp(due_at, "due_at"),
                ),
            ).fetchone()
            if check is None:
                return None
            pending = connection.execute(
                "SELECT * FROM thesis_pending_conclusions WHERE check_id = ?",
                (check["id"],),
            ).fetchone()
        return {
            "check": self._check_projection(check),
            "pending": None if pending is None else self._pending_projection(pending),
        }

    def append_condition_outcome(
        self,
        *,
        condition_id: str,
        due_at: str,
        result: str | ConditionCheckResult,
        evidence_fingerprint: str,
        evidence: Sequence[Mapping[str, Any]],
        checked_at: str,
        observed_value: object | None = None,
        safe_reason: str | None = None,
    ) -> dict[str, Any]:
        """Atomically append one check and its sole matched pending conclusion."""
        result_value = result.value if isinstance(result, ConditionCheckResult) else result
        try:
            result_value = ConditionCheckResult(result_value).value
        except ValueError as error:
            raise ValueError("condition check result is invalid") from error
        condition_value = _required_identifier(condition_id, "condition_id")
        due_value = _timestamp(due_at, "due_at")
        fingerprint = _fingerprint(evidence_fingerprint)
        checked_value = _timestamp(checked_at, "checked_at")
        evidence_json = _canonical_json(list(evidence), "evidence", maximum=64_000)
        observed_json = (
            None
            if observed_value is None
            else _canonical_json(observed_value, "observed_value", maximum=4_000)
        )
        reason = None if safe_reason is None else _required_text(safe_reason, "safe_reason", maximum=500)
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT * FROM thesis_condition_checks
                   WHERE condition_id = ? AND due_at = ?""",
                (condition_value, due_value),
            ).fetchone()
            if existing is not None:
                pending = connection.execute(
                    "SELECT * FROM thesis_pending_conclusions WHERE check_id = ?",
                    (existing["id"],),
                ).fetchone()
                return {
                    "check": self._check_projection(existing),
                    "pending": None if pending is None else self._pending_projection(pending),
                }
            condition = connection.execute(
                """SELECT condition.version_id, version.thesis_id
                   FROM thesis_conditions AS condition
                   JOIN thesis_versions AS version ON version.id = condition.version_id
                   WHERE condition.id = ?""",
                (condition_value,),
            ).fetchone()
            if condition is None:
                raise ValueError("thesis condition not found")
            current = self._current_row(connection, condition["thesis_id"])
            if current is None or current["id"] != condition["version_id"]:
                raise ValueError("old thesis version condition conflict")
            check_id = uuid4().hex
            connection.execute(
                """INSERT INTO thesis_condition_checks
                   (id, version_id, condition_id, due_at, result, observed_value_json,
                    evidence_fingerprint, evidence_json, safe_reason, checked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    check_id,
                    condition["version_id"],
                    condition_value,
                    due_value,
                    result_value,
                    observed_json,
                    fingerprint,
                    evidence_json,
                    reason,
                    checked_value,
                ),
            )
            pending_row = None
            if result_value == ConditionCheckResult.MATCHED.value:
                pending_id = uuid4().hex
                connection.execute(
                    """INSERT INTO thesis_pending_conclusions
                       (id, thesis_id, version_id, condition_id, check_id,
                        evidence_fingerprint, proposed_state, reason, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, 'invalidated', ?, 'pending', ?)""",
                    (
                        pending_id,
                        condition["thesis_id"],
                        condition["version_id"],
                        condition_value,
                        check_id,
                        fingerprint,
                        "Structured condition matched governed evidence.",
                        checked_value,
                    ),
                )
                pending_row = connection.execute(
                    "SELECT * FROM thesis_pending_conclusions WHERE id = ?",
                    (pending_id,),
                ).fetchone()
            check_row = connection.execute(
                "SELECT * FROM thesis_condition_checks WHERE id = ?",
                (check_id,),
            ).fetchone()
        assert check_row is not None
        return {
            "check": self._check_projection(check_row),
            "pending": None if pending_row is None else self._pending_projection(pending_row),
        }

    def list_pending(self, thesis_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM thesis_pending_conclusions WHERE thesis_id = ?
                   ORDER BY created_at DESC, id DESC""",
                (_required_identifier(thesis_id, "thesis_id"),),
            ).fetchall()
        return [self._pending_projection(row) for row in rows]

    def page_actionable_pending_for_instrument(
        self, instrument: str, *, offset: int, limit: int
    ) -> dict[str, Any]:
        """Page only current-version pending conclusions without a human review."""
        canonical = _required_instrument(instrument)
        page_offset, page_limit = _page_bounds(offset, limit)
        predicate = """FROM thesis_pending_conclusions AS pending
                       JOIN theses AS thesis ON thesis.id = pending.thesis_id
                       WHERE thesis.instrument = ?
                         AND pending.status = 'pending'
                         AND NOT EXISTS (
                             SELECT 1 FROM thesis_review_events AS review
                             WHERE review.pending_id = pending.id
                         )
                         AND NOT EXISTS (
                             SELECT 1 FROM thesis_versions AS successor
                             WHERE successor.thesis_id = pending.thesis_id
                               AND successor.predecessor_id = pending.version_id
                         )"""
        with self._connection() as connection:
            total = int(
                connection.execute(f"SELECT COUNT(*) {predicate}", (canonical,)).fetchone()[0]
            )
            rows = connection.execute(
                f"""SELECT pending.* {predicate}
                    ORDER BY pending.created_at DESC, pending.id DESC
                    LIMIT ? OFFSET ?""",
                (canonical, page_limit, page_offset),
            ).fetchall()
        items = [self._pending_projection(row) for row in rows]
        return _page_result(items, offset=page_offset, limit=page_limit, total=total)

    def page_pending_history_for_instrument(
        self, instrument: str, *, offset: int, limit: int
    ) -> dict[str, Any]:
        """Page all-version pending history with immutable review and lifecycle state."""
        canonical = _required_instrument(instrument)
        page_offset, page_limit = _page_bounds(offset, limit)
        with self._connection() as connection:
            total = int(
                connection.execute(
                    """SELECT COUNT(*)
                       FROM thesis_pending_conclusions AS pending
                       JOIN theses AS thesis ON thesis.id = pending.thesis_id
                       WHERE thesis.instrument = ?""",
                    (canonical,),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """SELECT pending.*,
                          review.id AS review_id,
                          review.decision AS review_decision,
                          review.reviewer_principal AS review_principal,
                          review.rationale AS review_rationale,
                          review.created_at AS review_created_at,
                          CASE WHEN NOT EXISTS (
                              SELECT 1 FROM thesis_versions AS successor
                              WHERE successor.thesis_id = pending.thesis_id
                                AND successor.predecessor_id = pending.version_id
                          ) THEN 1 ELSE 0 END AS is_current
                   FROM thesis_pending_conclusions AS pending
                   JOIN theses AS thesis ON thesis.id = pending.thesis_id
                   LEFT JOIN thesis_review_events AS review ON review.pending_id = pending.id
                   WHERE thesis.instrument = ?
                   ORDER BY pending.created_at DESC, pending.id DESC
                   LIMIT ? OFFSET ?""",
                (canonical, page_limit, page_offset),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            review = None
            if row["review_id"] is not None:
                review = {
                    "id": row["review_id"],
                    "pending_id": row["id"],
                    "thesis_id": row["thesis_id"],
                    "version_id": row["version_id"],
                    "condition_id": row["condition_id"],
                    "check_id": row["check_id"],
                    "evidence_fingerprint": row["evidence_fingerprint"],
                    "decision": row["review_decision"],
                    "reviewer_principal": row["review_principal"],
                    "rationale": row["review_rationale"],
                    "created_at": row["review_created_at"],
                }
            state = (
                str(row["review_decision"])
                if review is not None
                else "actionable"
                if bool(row["is_current"]) and row["status"] == "pending"
                else "superseded"
            )
            items.append(
                {
                    "pending": self._pending_projection(row),
                    "review": review,
                    "state": state,
                }
            )
        return _page_result(items, offset=page_offset, limit=page_limit, total=total)

    def get_pending(self, pending_id: str) -> dict[str, Any] | None:
        """Return one pending fact with the exact persisted check and condition."""
        with self._connection() as connection:
            row = connection.execute(
                """SELECT pending.*, thesis.instrument,
                          condition_check.due_at, condition_check.result,
                          condition_check.observed_value_json,
                          condition_check.evidence_json, condition_check.safe_reason,
                          condition.copied_from_condition_id, condition.source_kind,
                          condition.field, condition.operator, condition.threshold_json,
                          condition.unit, condition.lookback_days, condition.cadence,
                          condition.timezone, condition.description
                   FROM thesis_pending_conclusions AS pending
                   JOIN theses AS thesis ON thesis.id = pending.thesis_id
                   JOIN thesis_condition_checks AS condition_check
                     ON condition_check.id = pending.check_id
                   JOIN thesis_conditions AS condition ON condition.id = pending.condition_id
                   WHERE pending.id = ?""",
                (_required_identifier(pending_id, "pending_id"),),
            ).fetchone()
        if row is None:
            return None
        pending = self._pending_projection(row)
        pending["instrument"] = row["instrument"]
        pending["due_at"] = row["due_at"]
        pending["result"] = row["result"]
        pending["observed_value"] = (
            None if row["observed_value_json"] is None else json.loads(row["observed_value_json"])
        )
        pending["evidence"] = json.loads(row["evidence_json"])
        pending["safe_reason"] = row["safe_reason"]
        pending["condition"] = {
            **self._condition_projection(row),
            "version_id": row["version_id"],
            "thesis_id": row["thesis_id"],
            "instrument": row["instrument"],
        }
        return pending

    def append_review_event(
        self,
        *,
        pending_id: str,
        decision: str,
        reviewer_principal: str,
        rationale: str,
    ) -> dict[str, Any]:
        """Append one typed human decision after transactional current-state checks."""
        if decision not in {"confirmed", "rejected"}:
            raise ValueError("review decision is invalid")
        pending_value = _required_identifier(pending_id, "pending_id")
        principal = _required_text(reviewer_principal, "reviewer_principal", maximum=256)
        reason = _required_text(rationale, "rationale", maximum=4_000)
        created_at = self.now()
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute(
                "SELECT * FROM thesis_pending_conclusions WHERE id = ?",
                (pending_value,),
            ).fetchone()
            if pending is None:
                raise ValueError("pending thesis conclusion not found")
            if connection.execute(
                "SELECT 1 FROM thesis_review_events WHERE pending_id = ?", (pending_value,)
            ).fetchone() is not None:
                raise ValueError("pending thesis conclusion already processed conflict")
            current = self._current_row(connection, pending["thesis_id"])
            if current is None or current["id"] != pending["version_id"]:
                raise ValueError("old thesis version pending conflict")
            if self._official_state(connection, pending["thesis_id"], pending["version_id"]) != "active":
                raise ValueError("thesis official state changed conflict")
            event_id = uuid4().hex
            connection.execute(
                """INSERT INTO thesis_review_events
                   (id, pending_id, decision, reviewer_principal, rationale, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (event_id, pending_value, decision, principal, reason, created_at),
            )
            row = connection.execute(
                """SELECT review.*, pending.thesis_id, pending.version_id,
                          pending.condition_id, pending.check_id,
                          pending.evidence_fingerprint
                   FROM thesis_review_events AS review
                   JOIN thesis_pending_conclusions AS pending ON pending.id = review.pending_id
                   WHERE review.id = ?""",
                (event_id,),
            ).fetchone()
        assert row is not None
        return self._review_projection(row)

    def list_review_events(self, pending_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT review.*, pending.thesis_id, pending.version_id,
                          pending.condition_id, pending.check_id,
                          pending.evidence_fingerprint
                   FROM thesis_review_events AS review
                   JOIN thesis_pending_conclusions AS pending ON pending.id = review.pending_id
                   WHERE review.pending_id = ? ORDER BY review.created_at ASC, review.id ASC""",
                (_required_identifier(pending_id, "pending_id"),),
            ).fetchall()
        return [self._review_projection(row) for row in rows]

    def list_official_events(self, thesis_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT review.*, pending.thesis_id, pending.version_id,
                          pending.condition_id, pending.check_id,
                          pending.evidence_fingerprint
                   FROM thesis_review_events AS review
                   JOIN thesis_pending_conclusions AS pending ON pending.id = review.pending_id
                   WHERE pending.thesis_id = ? AND review.decision = 'confirmed'
                   ORDER BY review.created_at ASC, review.id ASC""",
                (_required_identifier(thesis_id, "thesis_id"),),
            ).fetchall()
        return [self._review_projection(row) for row in rows]

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

    @staticmethod
    def _pending_projection(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "thesis_id": row["thesis_id"],
            "version_id": row["version_id"],
            "condition_id": row["condition_id"],
            "check_id": row["check_id"],
            "evidence_fingerprint": row["evidence_fingerprint"],
            "proposed_state": row["proposed_state"],
            "reason": row["reason"],
            "status": row["status"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _review_projection(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "pending_id": row["pending_id"],
            "thesis_id": row["thesis_id"],
            "version_id": row["version_id"],
            "condition_id": row["condition_id"],
            "check_id": row["check_id"],
            "evidence_fingerprint": row["evidence_fingerprint"],
            "decision": row["decision"],
            "reviewer_principal": row["reviewer_principal"],
            "rationale": row["rationale"],
            "created_at": row["created_at"],
        }


def _required_instrument(value: str) -> str:
    if not isinstance(value, str) or not (canonical := value.strip().upper()):
        raise ValueError("instrument must be non-empty bounded text")
    if len(canonical) > 32 or any(
        not (character.isalnum() or character in ".-") for character in canonical
    ):
        raise ValueError("instrument is invalid")
    return canonical


def _page_bounds(offset: int, limit: int) -> tuple[int, int]:
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    return offset, limit


def _page_result(
    items: list[dict[str, Any]], *, offset: int, limit: int, total: int
) -> dict[str, Any]:
    return {
        "items": items,
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": offset + len(items) < total,
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


def _timestamp(value: datetime | str, field: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field} must be an ISO timestamp") from error
    else:
        raise ValueError(f"{field} must be an ISO timestamp")
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat()
