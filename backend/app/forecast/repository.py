"""Durable single-flight state and immutable Forecast record persistence."""

from __future__ import annotations

import json
import math
import re
import shutil
import sqlite3
from io import BytesIO
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

import numpy as np
import polars as pl

from app.optional_artifacts import (
    ArtifactDescriptor,
    ManagedArtifactError,
    ManagedImmutableArtifactStore,
)

from app.operational.migrations import migrate_operational_db

_ACTIVE_STATUSES = frozenset({"queued", "running"})
_TERMINAL_STATUSES = frozenset(
    {
        "completed",
        "validation_failed",
        "model_unavailable",
        "artifact_failed",
        "timed_out",
        "resource_limited",
        "interrupted",
    }
)
_LEGAL_TRANSITIONS = {
    "queued": frozenset({"running", "validation_failed", "model_unavailable", "interrupted"}),
    "running": frozenset(
        {
            "running",
            "completed",
            "validation_failed",
            "model_unavailable",
            "artifact_failed",
            "timed_out",
            "resource_limited",
            "interrupted",
        }
    ),
}
_SAFE_REASON = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ARTIFACT_DESCRIPTOR_FIELDS = {
    "artifact_id",
    "relative_path",
    "content_type",
    "byte_size",
    "checksum_sha256",
    "schema_version",
    "scope_sha256",
    "created_at",
}
_PATH_ARTIFACT_COLUMNS = {
    "sample_index",
    "horizon_index",
    "session_id",
    "feature",
    "value",
}
_QUANTILE_ARTIFACT_COLUMNS = {
    "quantile",
    "horizon_index",
    "session_id",
    "feature",
    "value",
}
_QUANTILE_LABELS = ("P10", "P50", "P90")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _as_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_terminal_reason(value: object) -> str:
    return value if isinstance(value, str) and _SAFE_REASON.fullmatch(value) else "forecast_failed"


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError(f"forecast {field} is invalid")
    return value


def _immutable_text(value: object, field: str) -> str:
    text = _nonempty_text(value, field)
    lowered = text.lower()
    if lowered in {"main", "master", "latest", "head"} or lowered.startswith("unknown"):
        raise ValueError(f"forecast {field} is not immutable")
    return text


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"forecast {field} is not a full SHA-256")
    return value


def _strict_int(
    value: object,
    field: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"forecast {field} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"forecast {field} is out of range")
    return value


def _strict_float(
    value: object,
    field: str,
    *,
    minimum: float,
    maximum: float,
    exclusive_minimum: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"forecast {field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"forecast {field} must be finite")
    below = number <= minimum if exclusive_minimum else number < minimum
    if below or number > maximum:
        raise ValueError(f"forecast {field} is out of range")
    return number


def _session_id(value: object, field: str) -> str:
    text = _nonempty_text(value, field)
    if re.fullmatch(r"CNA-\d{8}", text) is None:
        raise ValueError(f"forecast {field} identity is invalid")
    return text


def _validated_input_descriptor(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("forecast input artifact descriptor is invalid")
    required = {"artifact_id", "schema_version", "byte_size", "checksum_sha256"}
    if set(value) != required:
        raise ValueError("forecast input artifact descriptor is incomplete")
    return {
        "artifact_id": _nonempty_text(value["artifact_id"], "input artifact"),
        "schema_version": _immutable_text(value["schema_version"], "input schema"),
        "byte_size": _strict_int(value["byte_size"], "input byte size", minimum=1),
        "checksum_sha256": _digest(value["checksum_sha256"], "input checksum"),
    }


class ForecastRepository:
    """Short-lived SQLite transactions for the Forecast job and record ledger."""

    def __init__(
        self,
        database_path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self._clock = clock or (lambda: datetime.now(UTC))
        configured_root = Path(artifact_root or self.database_path.parent / "forecast-outputs")
        configured_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root = configured_root.resolve(strict=True)
        self._commit_identities: dict[str, dict[str, object]] = {}

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _immediate(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def migrate(self) -> None:
        with self.connection() as connection:
            migrate_operational_db(connection)

    def now(self) -> str:
        return _timestamp(_as_utc(self._clock()))

    @staticmethod
    def _owned_page_window(offset: int, limit: int) -> tuple[int, int]:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("forecast page offset is invalid")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("forecast page limit is invalid")
        return offset, limit

    @staticmethod
    def _owned_page_result(
        items: list[dict[str, Any]], *, offset: int, limit: int, total: int
    ) -> dict[str, Any]:
        return {
            "items": items,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(items) < total,
        }

    @staticmethod
    def _require_owner_scope(principal: str, instrument_id: str) -> None:
        if not isinstance(principal, str) or not principal:
            raise ValueError("forecast principal scope is invalid")
        if not isinstance(instrument_id, str) or not instrument_id:
            raise ValueError("forecast instrument scope is invalid")

    def page_owned_jobs(
        self,
        *,
        principal: str,
        instrument_id: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        """Page jobs only after principal and instrument filtering in SQLite."""
        self._require_owner_scope(principal, instrument_id)
        offset, limit = self._owned_page_window(offset, limit)
        with self.connection() as connection:
            total = int(
                connection.execute(
                    """SELECT COUNT(*) FROM forecast_jobs
                       WHERE principal = ? AND instrument_id = ?""",
                    (principal, instrument_id),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """SELECT j.*, r.id AS record_id
                   FROM forecast_jobs AS j
                   LEFT JOIN forecast_records AS r ON r.job_id = j.id
                   WHERE j.principal = ? AND j.instrument_id = ?
                   ORDER BY j.created_at DESC, j.id DESC
                   LIMIT ? OFFSET ?""",
                (principal, instrument_id, limit, offset),
            ).fetchall()
        return self._owned_page_result(
            [dict(row) for row in rows], offset=offset, limit=limit, total=total
        )

    def page_owned_forecasts(
        self,
        *,
        principal: str,
        instrument_id: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        """Page records through their immutable owning job before pagination."""
        self._require_owner_scope(principal, instrument_id)
        offset, limit = self._owned_page_window(offset, limit)
        ownership = """FROM forecast_records AS r
                       JOIN forecast_jobs AS j ON j.id = r.job_id
                       WHERE j.principal = ? AND j.instrument_id = ?
                         AND r.instrument_id = j.instrument_id"""
        with self.connection() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) {ownership}", (principal, instrument_id)
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""SELECT r.* {ownership}
                    ORDER BY r.created_at DESC, r.id DESC
                    LIMIT ? OFFSET ?""",
                (principal, instrument_id, limit, offset),
            ).fetchall()
        items = [self._record_with_quantiles(self._record_row(row)) for row in rows]
        return self._owned_page_result(items, offset=offset, limit=limit, total=total)

    def get_owned_job(self, *, job_id: str, principal: str) -> dict[str, Any] | None:
        if (
            not isinstance(job_id, str)
            or not job_id
            or not isinstance(principal, str)
            or not principal
        ):
            return None
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ? AND principal = ?",
                (job_id, principal),
            ).fetchone()
        return None if row is None else dict(row)

    def get_owned_forecast(
        self, *, forecast_id: str, principal: str
    ) -> dict[str, Any] | None:
        if (
            not isinstance(forecast_id, str)
            or not forecast_id
            or not isinstance(principal, str)
            or not principal
        ):
            return None
        with self.connection() as connection:
            row = connection.execute(
                """SELECT r.* FROM forecast_records AS r
                   JOIN forecast_jobs AS j ON j.id = r.job_id
                   WHERE r.id = ? AND j.principal = ?
                     AND r.instrument_id = j.instrument_id""",
                (forecast_id, principal),
            ).fetchone()
        return (
            None if row is None else self._record_with_quantiles(self._record_row(row))
        )

    def record_for_owned_job(
        self, *, job_id: str, principal: str, instrument_id: str
    ) -> dict[str, Any] | None:
        self._require_owner_scope(principal, instrument_id)
        with self.connection() as connection:
            row = connection.execute(
                """SELECT r.* FROM forecast_records AS r
                   JOIN forecast_jobs AS j ON j.id = r.job_id
                   WHERE r.job_id = ? AND j.principal = ? AND j.instrument_id = ?
                     AND r.instrument_id = j.instrument_id""",
                (job_id, principal, instrument_id),
            ).fetchone()
        return (
            None if row is None else self._record_with_quantiles(self._record_row(row))
        )

    def owned_job_transitions_after(
        self,
        job_id: str,
        *,
        principal: str,
        instrument_id: str,
        after_version: int,
        limit: int = 128,
    ) -> list[dict[str, Any]]:
        self._require_owner_scope(principal, instrument_id)
        if (
            not isinstance(job_id, str)
            or not job_id
            or isinstance(after_version, bool)
            or not isinstance(after_version, int)
            or after_version < -1
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 256
        ):
            raise ValueError("forecast transition resume request is invalid")
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT j.id, t.job_id, j.instrument_id, j.horizon, j.catalog_id,
                          j.attempt, j.created_at, t.status, t.transition_version,
                          t.terminal_reason, t.recorded_at AS updated_at
                   FROM forecast_job_transitions AS t
                   JOIN forecast_jobs AS j ON j.id = t.job_id
                   WHERE t.job_id = ? AND j.principal = ? AND j.instrument_id = ?
                     AND t.transition_version > ?
                   ORDER BY t.transition_version
                   LIMIT ?""",
                (job_id, principal, instrument_id, after_version, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def outcomes_for_owned_forecast(
        self, *, forecast_id: str, principal: str, instrument_id: str
    ) -> list[dict[str, Any]]:
        self._require_owner_scope(principal, instrument_id)
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT o.*, r.calendar_revision
                   FROM forecast_outcomes AS o
                   JOIN forecast_records AS r ON r.id = o.forecast_id
                   JOIN forecast_jobs AS j ON j.id = r.job_id
                   WHERE o.forecast_id = ? AND j.principal = ? AND j.instrument_id = ?
                     AND r.instrument_id = j.instrument_id
                   ORDER BY o.horizon, o.observed_at, o.id""",
                (forecast_id, principal, instrument_id),
            ).fetchall()
        return [self._outcome_row(row) for row in rows]

    def calibration_facts_for_owned_forecast(
        self, *, forecast_id: str, principal: str, instrument_id: str
    ) -> list[dict[str, Any]]:
        self._require_owner_scope(principal, instrument_id)
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT c.* FROM forecast_calibration_facts AS c
                   JOIN forecast_records AS r ON r.id = c.forecast_id
                   JOIN forecast_jobs AS j ON j.id = r.job_id
                   WHERE c.forecast_id = ? AND j.principal = ? AND j.instrument_id = ?
                     AND r.instrument_id = j.instrument_id
                   ORDER BY c.coverage_start, c.id""",
                (forecast_id, principal, instrument_id),
            ).fetchall()
        return [self._calibration_row(row) for row in rows]

    @staticmethod
    def _append_job_transition(connection: sqlite3.Connection, row: sqlite3.Row | None) -> None:
        if row is None:
            raise RuntimeError("forecast job transition row is unavailable")
        connection.execute(
            """INSERT INTO forecast_job_transitions
               (job_id, transition_version, status, terminal_reason, recorded_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                row["id"],
                int(row["transition_version"]),
                row["status"],
                row["terminal_reason"],
                row["updated_at"],
            ),
        )

    def find_active_job(
        self,
        *,
        principal: str,
        instrument_id: str,
        horizon: int,
        catalog_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        """Owner-scoped operation lookup before freezer promotion (operation-first)."""
        if horizon not in {5, 20, 60}:
            raise ValueError("forecast horizon is invalid")
        if not all(
            isinstance(value, str) and value
            for value in (principal, instrument_id, catalog_id, idempotency_key)
        ):
            raise ValueError("forecast request identity is invalid")
        with self._immediate() as connection:
            existing = connection.execute(
                """SELECT * FROM forecast_jobs
                   WHERE principal = ? AND instrument_id = ? AND horizon = ?
                     AND catalog_id = ? AND idempotency_key = ?""",
                (principal, instrument_id, horizon, catalog_id, idempotency_key),
            ).fetchone()
            if existing is None:
                return None
            return dict(existing)

    def input_artifact_is_referenced(self, artifact_id: str) -> bool:
        """True when any bound commit identity or completed forecast references the id."""
        if not isinstance(artifact_id, str) or not artifact_id:
            return False
        for record in self._commit_identities.values():
            descriptor = record.get("input_artifact_descriptor")
            if isinstance(descriptor, Mapping) and descriptor.get("artifact_id") == artifact_id:
                return True
        with self._immediate() as connection:
            rows = connection.execute(
                "SELECT input_artifact_descriptor_json FROM forecast_records"
            ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["input_artifact_descriptor_json"])
            except (TypeError, json.JSONDecodeError, KeyError):
                continue
            if isinstance(payload, dict) and payload.get("artifact_id") == artifact_id:
                return True
        return False

    def create_or_get_active_job(
        self,
        *,
        instrument_id: str,
        horizon: int,
        catalog_id: str,
        idempotency_key: str,
        input_fingerprint: str,
        principal: str = "local-operator",
    ) -> dict[str, Any]:
        """Return the canonical request identity, whether active or terminal."""
        if horizon not in {5, 20, 60}:
            raise ValueError("forecast horizon is invalid")
        if not all(
            isinstance(value, str) and value
            for value in (principal, instrument_id, catalog_id, idempotency_key)
        ):
            raise ValueError("forecast request identity is invalid")
        if not _SHA256.fullmatch(input_fingerprint):
            raise ValueError("forecast input fingerprint is invalid")
        now = self.now()
        with self._immediate() as connection:
            existing = connection.execute(
                """SELECT * FROM forecast_jobs
                   WHERE principal = ? AND instrument_id = ? AND horizon = ?
                     AND catalog_id = ? AND idempotency_key = ?""",
                (principal, instrument_id, horizon, catalog_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            identifier = str(uuid4())
            try:
                connection.execute(
                    """INSERT INTO forecast_jobs
                       (id, principal, instrument_id, horizon, catalog_id, idempotency_key,
                        input_fingerprint, status, transition_version, retry_of_job_id, attempt,
                        lease_owner, lease_until, terminal_reason, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, 1, NULL, NULL, NULL, ?, ?)""",
                    (
                        identifier,
                        principal,
                        instrument_id,
                        horizon,
                        catalog_id,
                        idempotency_key,
                        input_fingerprint,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                existing = connection.execute(
                    """SELECT * FROM forecast_jobs
                       WHERE principal = ? AND instrument_id = ? AND horizon = ?
                         AND catalog_id = ? AND idempotency_key = ?""",
                    (principal, instrument_id, horizon, catalog_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    return dict(existing)
                raise ValueError("forecast job identity conflicts") from error
            row = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (identifier,)
            ).fetchone()
            self._append_job_transition(connection, row)
        assert row is not None
        return dict(row)

    def create_retry_job(self, *, source_job_id: str, idempotency_key: str) -> dict[str, Any]:
        """Append an explicit retry lineage; duplicate request handling never calls this."""
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ValueError("forecast retry identity is invalid")
        now = self.now()
        with self._immediate() as connection:
            source = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (source_job_id,)
            ).fetchone()
            if source is None:
                raise ValueError("forecast retry source does not exist")
            if source["status"] not in _TERMINAL_STATUSES:
                raise ValueError("forecast retry requires a terminal source")
            existing = connection.execute(
                """SELECT * FROM forecast_jobs
                   WHERE principal = ? AND instrument_id = ? AND horizon = ?
                     AND catalog_id = ? AND idempotency_key = ?""",
                (
                    source["principal"],
                    source["instrument_id"],
                    source["horizon"],
                    source["catalog_id"],
                    idempotency_key,
                ),
            ).fetchone()
            if existing is not None:
                if existing["retry_of_job_id"] != source_job_id:
                    raise ValueError("forecast retry identity conflicts")
                return dict(existing)
            identifier = str(uuid4())
            connection.execute(
                """INSERT INTO forecast_jobs
                   (id, principal, instrument_id, horizon, catalog_id, idempotency_key,
                    input_fingerprint, status, transition_version, retry_of_job_id, attempt,
                    lease_owner, lease_until, terminal_reason, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?, NULL, NULL, NULL, ?, ?)""",
                (
                    identifier,
                    source["principal"],
                    source["instrument_id"],
                    source["horizon"],
                    source["catalog_id"],
                    idempotency_key,
                    source["input_fingerprint"],
                    source_job_id,
                    int(source["attempt"]) + 1,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (identifier,)
            ).fetchone()
            self._append_job_transition(connection, row)
        assert row is not None
        return dict(row)

    def acquire_global_lease(self, *, owner: str, ttl_seconds: int) -> bool:
        if not owner or ttl_seconds <= 0:
            raise ValueError("forecast global lease request is invalid")
        now_dt = _as_utc(self._clock())
        now = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=ttl_seconds))
        with self._immediate() as connection:
            changed = connection.execute(
                """UPDATE forecast_global_leases
                   SET lease_owner = ?, lease_until = ?, transition_version = transition_version + 1, updated_at = ?
                   WHERE lease_name = 'forecast-inference'
                     AND (lease_owner IS NULL OR lease_until <= ? OR lease_owner = ?)""",
                (owner, lease_until, now, now, owner),
            ).rowcount
        return changed == 1

    def heartbeat_global_lease(self, *, owner: str, ttl_seconds: int) -> bool:
        if not owner or ttl_seconds <= 0:
            return False
        now_dt = _as_utc(self._clock())
        now = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=ttl_seconds))
        with self._immediate() as connection:
            changed = connection.execute(
                """UPDATE forecast_global_leases
                   SET lease_until = ?, transition_version = transition_version + 1, updated_at = ?
                   WHERE lease_name = 'forecast-inference' AND lease_owner = ? AND lease_until > ?""",
                (lease_until, now, owner, now),
            ).rowcount
        return changed == 1

    def release_global_lease(self, *, owner: str) -> bool:
        now = self.now()
        with self._immediate() as connection:
            changed = connection.execute(
                """UPDATE forecast_global_leases
                   SET lease_owner = NULL, lease_until = NULL,
                       transition_version = transition_version + 1, updated_at = ?
                   WHERE lease_name = 'forecast-inference' AND lease_owner = ?""",
                (now, owner),
            ).rowcount
        return changed == 1

    def acquire_job(
        self,
        *,
        job_id: str,
        expected_status: str,
        expected_version: int,
        lease_owner: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        if expected_status != "queued" or not lease_owner or ttl_seconds <= 0:
            raise ValueError("forecast job transition is invalid")
        now_dt = _as_utc(self._clock())
        now = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=ttl_seconds))
        with self._immediate() as connection:
            changed = connection.execute(
                """UPDATE forecast_jobs
                   SET status = 'running', transition_version = transition_version + 1,
                       lease_owner = ?, lease_until = ?, terminal_reason = NULL, updated_at = ?
                   WHERE id = ? AND status = ? AND transition_version = ?""",
                (lease_owner, lease_until, now, job_id, expected_status, expected_version),
            ).rowcount
            if changed != 1:
                raise ValueError("forecast job has a stale state or version")
            row = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            self._append_job_transition(connection, row)
        assert row is not None
        return dict(row)

    def heartbeat(
        self,
        *,
        job_id: str,
        expected_version: int,
        lease_owner: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        if not lease_owner or ttl_seconds <= 0:
            raise ValueError("forecast job owner is invalid")
        now_dt = _as_utc(self._clock())
        now = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=ttl_seconds))
        with self._immediate() as connection:
            changed = connection.execute(
                """UPDATE forecast_jobs
                   SET lease_until = ?, transition_version = transition_version + 1, updated_at = ?
                   WHERE id = ? AND status = 'running' AND transition_version = ?
                     AND lease_owner = ? AND lease_until > ?""",
                (lease_until, now, job_id, expected_version, lease_owner, now),
            ).rowcount
            if changed != 1:
                raise ValueError("forecast job owner, lease, or version is stale")
            row = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            self._append_job_transition(connection, row)
        assert row is not None
        return dict(row)

    def compare_and_swap_job(
        self,
        *,
        job_id: str,
        expected_status: str,
        expected_version: int,
        lease_owner: str | None,
        new_status: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if new_status not in _LEGAL_TRANSITIONS.get(expected_status, frozenset()):
            raise ValueError("forecast job transition is illegal")
        if new_status == "completed":
            raise ValueError("completed transition requires immutable forecast commit")
        now = self.now()
        terminal = new_status in _TERMINAL_STATUSES
        safe_reason = _safe_terminal_reason(reason) if terminal else None
        with self._immediate() as connection:
            owner_clause = "lease_owner IS NULL" if lease_owner is None else "lease_owner = ?"
            parameters: list[object] = [
                new_status,
                expected_version + 1,
                None if terminal else lease_owner,
                None
                if terminal
                else connection.execute(
                    "SELECT lease_until FROM forecast_jobs WHERE id = ?", (job_id,)
                ).fetchone()[0],
                safe_reason,
                now,
                job_id,
                expected_status,
                expected_version,
            ]
            if lease_owner is not None:
                parameters.append(lease_owner)
            changed = connection.execute(
                f"""UPDATE forecast_jobs
                    SET status = ?, transition_version = ?, lease_owner = ?, lease_until = ?,
                        terminal_reason = ?, updated_at = ?
                    WHERE id = ? AND status = ? AND transition_version = ? AND {owner_clause}""",
                parameters,
            ).rowcount
            if changed != 1:
                raise ValueError(
                    "forecast job transition rejected by stale state, version, or owner"
                )
            row = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            self._append_job_transition(connection, row)
        assert row is not None
        return dict(row)

    def terminalize(
        self,
        *,
        job_id: str,
        expected_status: str,
        expected_version: int,
        lease_owner: str | None,
        status: str,
        reason: str,
        temporary_paths: Sequence[Path] = (),
    ) -> dict[str, Any]:
        if status not in _TERMINAL_STATUSES - {"completed"}:
            raise ValueError("forecast terminal transition is invalid")
        try:
            return self.compare_and_swap_job(
                job_id=job_id,
                expected_status=expected_status,
                expected_version=expected_version,
                lease_owner=lease_owner,
                new_status=status,
                reason=reason,
            )
        finally:
            for path in temporary_paths:
                candidate = Path(path)
                if candidate.is_dir():
                    shutil.rmtree(candidate, ignore_errors=True)
                else:
                    candidate.unlink(missing_ok=True)

    def bind_commit_identity(self, *, job_id: str, immutable_record: Mapping[str, object]) -> None:
        """Bind the server-selected catalog/input identity before child execution."""
        job = self.get_job(job_id)
        if job is None:
            raise ValueError("forecast job does not exist")
        validated = self._validated_immutable_record(immutable_record, job=job)
        self._commit_identities[job_id] = deepcopy(validated)

    def mark_interrupted_before_commit(self, *, job_id: str, lease_owner: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job is None:
            raise ValueError("forecast job does not exist")
        return self.terminalize(
            job_id=job_id,
            expected_status="running",
            expected_version=int(job["transition_version"]),
            lease_owner=lease_owner,
            status="interrupted",
            reason="interrupted_before_commit",
        )

    def commit_completed_forecast(
        self,
        *,
        job_id: str,
        expected_status: str,
        expected_version: int,
        lease_owner: str,
        output_descriptor: Mapping[str, object],
        immutable_record: Mapping[str, object],
    ) -> dict[str, Any]:
        """Atomically cross the sole forecast creation commit point."""
        now = self.now()
        with self._immediate() as connection:
            canonical = connection.execute(
                "SELECT * FROM forecast_records WHERE job_id = ?", (job_id,)
            ).fetchone()
            if canonical is not None:
                return self._record_with_quantiles(self._record_row(canonical))
            job = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job is None:
                raise ValueError("forecast job does not exist")
            if (
                expected_status != "running"
                or job["status"] != expected_status
                or int(job["transition_version"]) != expected_version
                or job["lease_owner"] != lease_owner
                or not job["lease_until"]
                or _as_utc(job["lease_until"]) <= _as_utc(now)
            ):
                raise ValueError(
                    "forecast commit rejected by stale state, version, owner, or lease"
                )

            record = self._validated_immutable_record(immutable_record, job=dict(job))
            expected_identity = self._commit_identities.get(job_id)
            if expected_identity is None:
                raise ValueError("forecast commit has no server-bound immutable identity")
            expected_comparable = {
                key: value
                for key, value in expected_identity.items()
                if key != "validation_warnings"
            }
            record_comparable = {
                key: value for key, value in record.items() if key != "validation_warnings"
            }
            if record_comparable != expected_comparable:
                raise ValueError("forecast record diverges from its server-bound identity")
            bundle = self._validated_output_descriptor(output_descriptor, record=record)

            record_id = str(uuid4())
            values = (
                record_id,
                job_id,
                job["instrument_id"],
                record["origin_session_id"],
                record["calendar_id"],
                record["calendar_revision"],
                _canonical_json(record["future_session_ids"]),
                job["input_fingerprint"],
                _canonical_json(record["input_artifact_descriptor"]),
                job["horizon"],
                record["lookback"],
                record["seed"],
                record["temperature"],
                record["top_k"],
                record["top_p"],
                32,
                job["catalog_id"],
                record["source_revision"],
                record["source_digest_sha256"],
                record["model_revision"],
                record["model_digest_sha256"],
                record["tokenizer_revision"],
                record["tokenizer_digest_sha256"],
                _canonical_json(bundle["paths_artifact"]),
                bundle["source_paths_sha256"],
                "available",
                _canonical_json(bundle["quantiles_artifact"]),
                bundle["quantiles_artifact"]["checksum_sha256"],
                bundle["source_paths_sha256"],
                bundle["provenance_digest_sha256"],
                bundle["quantile_row_count"],
                bundle["quantile_session_count"],
                bundle["quantile_feature_count"],
                _canonical_json(record["validation_warnings"]),
                now,
            )
            connection.execute(
                """INSERT INTO forecast_records
                   (id, job_id, instrument_id, origin_session_id, calendar_id, calendar_revision,
                    future_session_ids_json, input_fingerprint, input_artifact_descriptor_json,
                    horizon, lookback, seed, temperature, top_k, top_p, sample_count, catalog_id,
                    source_revision, source_digest_sha256, model_revision, model_digest_sha256,
                    tokenizer_revision, tokenizer_digest_sha256, output_artifact_descriptor_json,
                    paths_checksum_sha256, quantile_availability,
                    quantiles_artifact_descriptor_json, quantiles_checksum_sha256,
                    quantiles_source_paths_sha256, quantiles_provenance_digest_sha256,
                    quantile_row_count, quantile_session_count, quantile_feature_count,
                    validation_warnings_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            changed = connection.execute(
                """UPDATE forecast_jobs
                   SET status = 'completed', transition_version = transition_version + 1,
                       lease_owner = NULL, lease_until = NULL, terminal_reason = NULL, updated_at = ?
                   WHERE id = ? AND status = ? AND transition_version = ? AND lease_owner = ?""",
                (now, job_id, expected_status, expected_version, lease_owner),
            ).rowcount
            if changed != 1:
                raise ValueError("forecast commit lost its state transition")
            transition = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            self._append_job_transition(connection, transition)
            canonical = connection.execute(
                "SELECT * FROM forecast_records WHERE id = ?", (record_id,)
            ).fetchone()
        self._commit_identities.pop(job_id, None)
        assert canonical is not None
        return self._record_with_quantiles(self._record_row(canonical))

    @staticmethod
    def _validated_immutable_record(
        value: Mapping[str, object], *, job: Mapping[str, object]
    ) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError("forecast immutable record is invalid")
        required = {
            "instrument_id",
            "origin_session_id",
            "calendar_id",
            "calendar_revision",
            "future_session_ids",
            "input_fingerprint",
            "input_artifact_descriptor",
            "horizon",
            "lookback",
            "seed",
            "temperature",
            "top_k",
            "top_p",
            "sample_count",
            "catalog_id",
            "source_revision",
            "source_digest_sha256",
            "model_revision",
            "model_digest_sha256",
            "tokenizer_revision",
            "tokenizer_digest_sha256",
            "feature_schema",
            "validation_warnings",
        }
        if not required.issubset(value):
            raise ValueError("forecast immutable record is incomplete")

        horizon = _strict_int(value["horizon"], "horizon", minimum=1, maximum=60)
        if horizon not in {5, 20, 60} or horizon != int(job["horizon"]):
            raise ValueError("forecast record horizon does not match its job")
        sample_count = _strict_int(value["sample_count"], "sample count", minimum=32, maximum=32)
        lookback = _strict_int(value["lookback"], "lookback", minimum=1, maximum=4096)
        seed = _strict_int(value["seed"], "seed", minimum=0, maximum=2**63 - 1)
        top_k = _strict_int(value["top_k"], "top-k", minimum=1, maximum=4096)
        temperature = _strict_float(
            value["temperature"],
            "temperature",
            minimum=0.0,
            maximum=10.0,
            exclusive_minimum=True,
        )
        top_p = _strict_float(
            value["top_p"],
            "top-p",
            minimum=0.0,
            maximum=1.0,
            exclusive_minimum=True,
        )
        instrument = _nonempty_text(value["instrument_id"], "instrument")
        catalog_id = _nonempty_text(value["catalog_id"], "catalog")
        fingerprint = _digest(value["input_fingerprint"], "input fingerprint")
        if instrument != job["instrument_id"]:
            raise ValueError("forecast record instrument does not match its job")
        if catalog_id != job["catalog_id"]:
            raise ValueError("forecast record catalog does not match its job")
        if fingerprint != job["input_fingerprint"]:
            raise ValueError("forecast record input does not match its job")

        origin = _session_id(value["origin_session_id"], "origin session")
        future_value = value["future_session_ids"]
        if not isinstance(future_value, (list, tuple)) or len(future_value) != horizon:
            raise ValueError("forecast future sessions do not match its horizon")
        future = [_session_id(item, "future session") for item in future_value]
        if len(set(future)) != horizon or origin in future:
            raise ValueError("forecast future sessions are invalid")

        input_descriptor = _validated_input_descriptor(value["input_artifact_descriptor"])
        features_value = value["feature_schema"]
        if not isinstance(features_value, (list, tuple)) or not features_value:
            raise ValueError("forecast feature schema is invalid")
        features = [_nonempty_text(item, "feature") for item in features_value]
        if len(set(features)) != len(features):
            raise ValueError("forecast feature schema is duplicated")
        warnings_value = value["validation_warnings"]
        if not isinstance(warnings_value, (list, tuple)) or len(warnings_value) > 64:
            raise ValueError("forecast validation warnings are invalid")
        warnings = []
        for warning in warnings_value:
            text = _nonempty_text(warning, "validation warning")
            if len(text) > 128:
                raise ValueError("forecast validation warning is too long")
            warnings.append(text)

        revisions = {
            field: _immutable_text(value[field], field)
            for field in (
                "calendar_revision",
                "source_revision",
                "model_revision",
                "tokenizer_revision",
            )
        }
        digests = {
            field: _digest(value[field], field)
            for field in (
                "source_digest_sha256",
                "model_digest_sha256",
                "tokenizer_digest_sha256",
            )
        }
        return {
            "instrument_id": instrument,
            "origin_session_id": origin,
            "calendar_id": _immutable_text(value["calendar_id"], "calendar_id"),
            **revisions,
            "future_session_ids": future,
            "input_fingerprint": fingerprint,
            "input_artifact_descriptor": input_descriptor,
            "horizon": horizon,
            "lookback": lookback,
            "seed": seed,
            "temperature": temperature,
            "top_k": top_k,
            "top_p": top_p,
            "sample_count": sample_count,
            "catalog_id": catalog_id,
            **digests,
            "feature_schema": features,
            "validation_warnings": warnings,
        }

    def _validated_output_descriptor(
        self, value: Mapping[str, object], *, record: Mapping[str, object]
    ) -> dict[str, object]:
        """Verify both managed Parquet byte streams and their immutable binding."""
        required = {
            "paths_artifact",
            "quantiles_artifact",
            "path_shape",
            "quantile_shape",
            "sample_count",
            "quantile_labels",
            "warning_codes",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise ValueError("forecast output artifact bundle is incomplete")
        horizon = int(record["horizon"])
        features = list(record["feature_schema"])
        expected_path_shape = [32, horizon, len(features)]
        expected_quantile_shape = [3, horizon, len(features)]
        if (
            value["path_shape"] != expected_path_shape
            or value["quantile_shape"] != expected_quantile_shape
            or value["sample_count"] != 32
            or value["quantile_labels"] != list(_QUANTILE_LABELS)
        ):
            raise ValueError("forecast output artifact bundle shape or labels diverge")
        warning_codes = value["warning_codes"]
        if (
            not isinstance(warning_codes, list)
            or len(warning_codes) > 64
            or any(
                not isinstance(code, str) or _SAFE_REASON.fullmatch(code) is None
                for code in warning_codes
            )
            or warning_codes != record["validation_warnings"]
        ):
            raise ValueError("forecast output warning codes diverge")

        paths_descriptor, paths_scope, paths_frame = self._verified_artifact_frame(
            value["paths_artifact"],
            schema_version="forecast-paths-v1",
            field="paths",
        )
        quantiles_descriptor, quantiles_scope, quantiles_frame = self._verified_artifact_frame(
            value["quantiles_artifact"],
            schema_version="forecast-quantiles-v1",
            field="quantiles",
        )
        paths = self._validated_path_tensor(
            paths_frame,
            sessions=list(record["future_session_ids"]),
            features=features,
        )
        quantiles, _mapping, _features = self._validated_quantile_tensor(
            quantiles_frame,
            sessions=list(record["future_session_ids"]),
            features=features,
            feature_count=len(features),
        )
        expected_quantiles = np.asarray(
            np.quantile(paths, q=(0.10, 0.50, 0.90), axis=0), dtype=np.float64
        )
        if not np.allclose(
            quantiles,
            expected_quantiles,
            rtol=1e-12,
            atol=1e-12,
            equal_nan=False,
        ):
            raise ValueError("forecast quantile bytes diverge from the complete path tensor")
        if (
            paths_scope.get("kind") != "sampled_paths"
            or paths_scope.get("shape") != expected_path_shape
            or quantiles_scope.get("kind") != "path_axis_quantiles"
            or quantiles_scope.get("shape") != expected_quantile_shape
            or quantiles_scope.get("source_paths_sha256")
            != paths_descriptor["checksum_sha256"]
        ):
            raise ValueError("forecast artifact scope or source binding diverges")
        path_base = {
            key: item for key, item in paths_scope.items() if key not in {"kind", "shape"}
        }
        quantile_base = {
            key: item
            for key, item in quantiles_scope.items()
            if key not in {"kind", "shape", "source_paths_sha256"}
        }
        if path_base != quantile_base:
            raise ValueError("forecast path and quantile artifact scopes diverge")
        provenance = self._quantile_provenance_digest(
            record=record,
            paths_descriptor=paths_descriptor,
            quantiles_descriptor=quantiles_descriptor,
        )
        return {
            "paths_artifact": paths_descriptor,
            "quantiles_artifact": quantiles_descriptor,
            "source_paths_sha256": paths_descriptor["checksum_sha256"],
            "provenance_digest_sha256": provenance,
            "quantile_row_count": 3 * horizon * len(features),
            "quantile_session_count": horizon,
            "quantile_feature_count": len(features),
        }

    def _verified_artifact_frame(
        self,
        value: object,
        *,
        schema_version: str,
        field: str,
    ) -> tuple[dict[str, object], dict[str, object], pl.DataFrame]:
        if not isinstance(value, Mapping) or set(value) != _ARTIFACT_DESCRIPTOR_FIELDS:
            raise ValueError(f"forecast {field} artifact descriptor is incomplete")
        if isinstance(value.get("byte_size"), bool):
            raise ValueError(f"forecast {field} artifact size is invalid")
        try:
            descriptor = ArtifactDescriptor(**dict(value))
            if (
                descriptor.schema_version != schema_version
                or descriptor.content_type != "application/vnd.apache.parquet"
            ):
                raise ValueError(f"forecast {field} artifact schema is invalid")
            store = ManagedImmutableArtifactStore(self.artifact_root)
            persisted, scope, payload_path = store._verified_payload(descriptor)
            if persisted != descriptor:
                raise ValueError(f"forecast {field} artifact metadata diverges")
            payload = payload_path.read_bytes()
            if (
                len(payload) != descriptor.byte_size
                or sha256(payload).hexdigest() != descriptor.checksum_sha256
            ):
                raise ValueError(f"forecast {field} artifact bytes diverge")
            frame = pl.read_parquet(BytesIO(payload))
        except (ManagedArtifactError, OSError, TypeError, ValueError, pl.exceptions.PolarsError) as error:
            if isinstance(error, ValueError) and str(error).startswith("forecast "):
                raise
            raise ValueError(f"forecast {field} artifact cannot be verified") from error
        return descriptor.as_dict(), dict(scope), frame

    @staticmethod
    def _validated_path_tensor(
        frame: pl.DataFrame,
        *,
        sessions: list[str],
        features: list[str],
    ) -> np.ndarray:
        if set(frame.columns) != _PATH_ARTIFACT_COLUMNS:
            raise ValueError("forecast path artifact relation schema is invalid")
        horizon = len(sessions)
        expected_rows = 32 * horizon * len(features)
        rows = frame.to_dicts()
        if len(rows) != expected_rows:
            raise ValueError("forecast path artifact relation shape is invalid")
        session_position = {session: index for index, session in enumerate(sessions)}
        feature_position = {feature: index for index, feature in enumerate(features)}
        tensor = np.empty((32, horizon, len(features)), dtype=np.float64)
        seen: set[tuple[int, int, int]] = set()
        for row in rows:
            sample = row.get("sample_index")
            session = row.get("session_id")
            feature = row.get("feature")
            value = row.get("value")
            if (
                isinstance(sample, bool)
                or not isinstance(sample, int)
                or not 0 <= sample < 32
                or session not in session_position
                or feature not in feature_position
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ValueError("forecast path artifact relation contains an invalid value")
            session_index = session_position[session]
            feature_index = feature_position[feature]
            if row.get("horizon_index") != session_index:
                raise ValueError("forecast path artifact session order diverges")
            identity = (sample, session_index, feature_index)
            if identity in seen:
                raise ValueError("forecast path artifact relation contains duplicates")
            seen.add(identity)
            tensor[identity] = float(value)
        if len(seen) != expected_rows:
            raise ValueError("forecast path artifact relation is incomplete")
        return tensor

    @staticmethod
    def _validated_quantile_tensor(
        frame: pl.DataFrame,
        *,
        sessions: list[str],
        features: list[str] | None,
        feature_count: int,
    ) -> tuple[np.ndarray, dict[str, dict[str, float]], list[str]]:
        if set(frame.columns) != _QUANTILE_ARTIFACT_COLUMNS:
            raise ValueError("forecast quantile artifact relation schema is invalid")
        if features is None:
            features = sorted(
                {item for item in frame["feature"].to_list() if isinstance(item, str)}
            )
        if len(features) != feature_count or len(set(features)) != feature_count or "close" not in features:
            raise ValueError("forecast quantile artifact feature relation is invalid")
        horizon = len(sessions)
        expected_rows = 3 * horizon * feature_count
        rows = frame.to_dicts()
        if len(rows) != expected_rows:
            raise ValueError("forecast quantile artifact relation shape is invalid")
        label_position = {label: index for index, label in enumerate(_QUANTILE_LABELS)}
        session_position = {session: index for index, session in enumerate(sessions)}
        feature_position = {feature: index for index, feature in enumerate(features)}
        tensor = np.empty((3, horizon, feature_count), dtype=np.float64)
        seen: set[tuple[int, int, int]] = set()
        for row in rows:
            label = row.get("quantile")
            session = row.get("session_id")
            feature = row.get("feature")
            value = row.get("value")
            if (
                label not in label_position
                or session not in session_position
                or feature not in feature_position
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ValueError("forecast quantile artifact relation contains an invalid value")
            session_index = session_position[session]
            if row.get("horizon_index") != session_index:
                raise ValueError("forecast quantile artifact session order diverges")
            identity = (label_position[label], session_index, feature_position[feature])
            if identity in seen:
                raise ValueError("forecast quantile artifact relation contains duplicates")
            seen.add(identity)
            tensor[identity] = float(value)
        if len(seen) != expected_rows:
            raise ValueError("forecast quantile artifact relation is incomplete")
        close_index = feature_position["close"]
        if np.any(tensor[0, :, close_index] > tensor[1, :, close_index]) or np.any(
            tensor[1, :, close_index] > tensor[2, :, close_index]
        ):
            raise ValueError("forecast close quantiles are crossed")
        mapping = {
            str(index + 1): {
                "p10": float(tensor[0, index, close_index]),
                "p50": float(tensor[1, index, close_index]),
                "p90": float(tensor[2, index, close_index]),
            }
            for index in range(horizon)
        }
        return tensor, mapping, features

    @staticmethod
    def _quantile_provenance_digest(
        *,
        record: Mapping[str, object],
        paths_descriptor: Mapping[str, object],
        quantiles_descriptor: Mapping[str, object],
    ) -> str:
        identity = {
            key: record[key]
            for key in (
                "origin_session_id",
                "calendar_id",
                "calendar_revision",
                "future_session_ids",
                "input_fingerprint",
                "horizon",
                "lookback",
                "seed",
                "temperature",
                "top_k",
                "top_p",
                "sample_count",
                "catalog_id",
                "source_revision",
                "source_digest_sha256",
                "model_revision",
                "model_digest_sha256",
                "tokenizer_revision",
                "tokenizer_digest_sha256",
            )
        }
        identity["paths_artifact"] = dict(paths_descriptor)
        identity["quantiles_artifact"] = dict(quantiles_descriptor)
        return sha256(_canonical_json(identity).encode("utf-8")).hexdigest()

    def load_verified_quantiles(
        self, record: Mapping[str, object]
    ) -> dict[str, dict[str, float]] | None:
        """Reload canonical close quantiles from checksum-verified Parquet bytes."""
        availability = record.get("quantile_availability")
        if availability == "legacy_unavailable":
            return None
        if availability != "available":
            raise ValueError("forecast quantile availability state is invalid")
        descriptor_value = record.get("quantiles_artifact_descriptor")
        paths_descriptor = record.get("output_artifact_descriptor")
        if not isinstance(descriptor_value, Mapping) or not isinstance(paths_descriptor, Mapping):
            raise ValueError("forecast quantile artifact metadata is unavailable")
        descriptor, scope, frame = self._verified_artifact_frame(
            descriptor_value,
            schema_version="forecast-quantiles-v1",
            field="quantiles",
        )
        expected_checksum = _digest(
            record.get("quantiles_checksum_sha256"), "quantiles checksum"
        )
        source_checksum = _digest(
            record.get("quantiles_source_paths_sha256"), "quantile source paths checksum"
        )
        paths_checksum = _digest(record.get("paths_checksum_sha256"), "paths checksum")
        if (
            descriptor["checksum_sha256"] != expected_checksum
            or source_checksum != paths_checksum
            or scope.get("source_paths_sha256") != paths_checksum
            or scope.get("kind") != "path_axis_quantiles"
        ):
            raise ValueError("forecast quantile artifact identity or source binding diverges")
        sessions = record.get("future_session_ids")
        if not isinstance(sessions, list) or len(sessions) != record.get("horizon"):
            raise ValueError("forecast quantile sessions are unavailable")
        session_count = _strict_int(
            record.get("quantile_session_count"),
            "quantile session count",
            minimum=1,
            maximum=60,
        )
        feature_count = _strict_int(
            record.get("quantile_feature_count"),
            "quantile feature count",
            minimum=1,
        )
        row_count = _strict_int(
            record.get("quantile_row_count"), "quantile row count", minimum=1
        )
        if (
            session_count != len(sessions)
            or row_count != 3 * session_count * feature_count
            or scope.get("shape") != [3, session_count, feature_count]
        ):
            raise ValueError("forecast quantile bounded shape metadata diverges")
        _tensor, mapping, _features = self._validated_quantile_tensor(
            frame,
            sessions=sessions,
            features=None,
            feature_count=feature_count,
        )
        provenance = self._quantile_provenance_digest(
            record=record,
            paths_descriptor=paths_descriptor,
            quantiles_descriptor=descriptor,
        )
        if provenance != _digest(
            record.get("quantiles_provenance_digest_sha256"),
            "quantile provenance digest",
        ):
            raise ValueError("forecast quantile provenance digest diverges")
        return mapping

    def _record_with_quantiles(self, record: dict[str, Any]) -> dict[str, Any]:
        quantiles = self.load_verified_quantiles(record)
        if quantiles is not None:
            record["quantiles"] = quantiles
        return record

    def recover_after_restart(
        self,
        *,
        revalidate: Callable[[dict[str, Any]], bool],
        now: str | datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Recover only durable cursors; a prior native process is never resumed."""
        observed = _as_utc(now or self._clock())
        outcomes: list[dict[str, Any]] = []
        for job in self.list_jobs():
            status = job["status"]
            if status == "queued":
                if revalidate(job):
                    outcomes.append({"job_id": job["id"], "action": "requeue"})
                else:
                    self.terminalize(
                        job_id=job["id"],
                        expected_status="queued",
                        expected_version=int(job["transition_version"]),
                        lease_owner=None,
                        status="validation_failed",
                        reason="restart_revalidation_failed",
                    )
                    outcomes.append(
                        {
                            "job_id": job["id"],
                            "action": "terminalized",
                            "status": "validation_failed",
                        }
                    )
            elif status == "running" and (
                not job["lease_until"] or _as_utc(job["lease_until"]) <= observed
            ):
                self.terminalize(
                    job_id=job["id"],
                    expected_status="running",
                    expected_version=int(job["transition_version"]),
                    lease_owner=job["lease_owner"],
                    status="interrupted",
                    reason="restart_expired_lease",
                )
                outcomes.append(
                    {"job_id": job["id"], "action": "terminalized", "status": "interrupted"}
                )
        return outcomes

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return None if row is None else dict(row)

    def job_transitions_after(
        self, job_id: str, *, after_version: int, limit: int = 128
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(job_id, str)
            or not job_id
            or isinstance(after_version, bool)
            or not isinstance(after_version, int)
            or after_version < -1
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 256
        ):
            raise ValueError("forecast transition resume request is invalid")
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT j.id, t.job_id, j.instrument_id, j.horizon, j.catalog_id,
                          j.attempt, j.created_at, t.status, t.transition_version,
                          t.terminal_reason, t.recorded_at AS updated_at
                   FROM forecast_job_transitions AS t
                   JOIN forecast_jobs AS j ON j.id = t.job_id
                   WHERE t.job_id = ? AND t.transition_version > ?
                   ORDER BY t.transition_version
                   LIMIT ?""",
                (job_id, after_version, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_jobs(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM forecast_jobs ORDER BY created_at, id"
            ).fetchall()
        return [dict(row) for row in rows]

    def forecast_for_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM forecast_records WHERE job_id = ?", (job_id,)
            ).fetchone()
        return None if row is None else self._record_with_quantiles(self._record_row(row))

    def list_forecasts(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM forecast_records ORDER BY created_at, id"
            ).fetchall()
        return [self._record_with_quantiles(self._record_row(row)) for row in rows]

    def get_forecast(self, forecast_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM forecast_records WHERE id = ?", (forecast_id,)
            ).fetchone()
        return None if row is None else self._record_with_quantiles(self._record_row(row))

    def list_forecasts_for_instrument(self, instrument_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM forecast_records
                   WHERE instrument_id = ? ORDER BY created_at DESC, id DESC""",
                (instrument_id,),
            ).fetchall()
        return [self._record_with_quantiles(self._record_row(row)) for row in rows]

    def outcomes_for_forecast(self, forecast_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT o.*, f.calendar_revision
                   FROM forecast_outcomes AS o
                   JOIN forecast_records AS f ON f.id = o.forecast_id
                   WHERE o.forecast_id = ? ORDER BY o.horizon, o.observed_at, o.id""",
                (forecast_id,),
            ).fetchall()
        return [self._outcome_row(row) for row in rows]

    def outcome_for_horizon(self, forecast_id: str, horizon: int) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT o.*, f.calendar_revision
                   FROM forecast_outcomes AS o
                   JOIN forecast_records AS f ON f.id = o.forecast_id
                   WHERE o.forecast_id = ? AND o.horizon = ?""",
                (forecast_id, horizon),
            ).fetchone()
        return None if row is None else self._outcome_row(row)

    def calibration_for_outcome(self, outcome_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM forecast_calibration_facts WHERE outcome_id = ?",
                (outcome_id,),
            ).fetchone()
        return None if row is None else self._calibration_row(row)

    def calibration_facts_for_forecast(self, forecast_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM forecast_calibration_facts
                   WHERE forecast_id = ? ORDER BY coverage_start, id""",
                (forecast_id,),
            ).fetchall()
        return [self._calibration_row(row) for row in rows]

    def append_maturity_fact(
        self,
        *,
        forecast_id: str,
        horizon: int,
        status: str,
        actual_session_id: str,
        actual_close: float | None,
        actual_fingerprint: str | None,
        reason: str | None,
        observed_at: str,
        metric_schema: str,
        close_mae: float | None,
        interval_covered: bool | None,
        pinball_p10: float | None,
        pinball_p50: float | None,
        pinball_p90: float | None,
    ) -> dict[str, Any]:
        """Append one canonical outcome and its calibration fact atomically."""
        if horizon not in {5, 20, 60} or status not in {"evaluated", "unevaluable"}:
            raise ValueError("forecast maturity fact is invalid")
        if status == "evaluated" and actual_close is None:
            raise ValueError("evaluated forecast outcome requires an actual close")
        if status == "unevaluable" and not reason:
            raise ValueError("unevaluable forecast outcome requires a reason")
        if actual_fingerprint is not None and not _SHA256.fullmatch(actual_fingerprint):
            raise ValueError("forecast actual fingerprint is invalid")
        with self._immediate() as connection:
            existing = connection.execute(
                """SELECT o.*, f.calendar_revision
                   FROM forecast_outcomes AS o
                   JOIN forecast_records AS f ON f.id = o.forecast_id
                   WHERE o.forecast_id = ? AND o.horizon = ?""",
                (forecast_id, horizon),
            ).fetchone()
            if existing is not None:
                return self._outcome_row(existing)
            if (
                connection.execute(
                    "SELECT 1 FROM forecast_records WHERE id = ?", (forecast_id,)
                ).fetchone()
                is None
            ):
                raise ValueError("forecast record does not exist")
            outcome_id = str(uuid4())
            outcome_values = (
                None if actual_close is None else _canonical_json({"close": actual_close})
            )
            connection.execute(
                """INSERT INTO forecast_outcomes
                   (id, forecast_id, horizon, status, actual_session_id, actual_value_json,
                    actual_fingerprint, reason, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    outcome_id,
                    forecast_id,
                    horizon,
                    status,
                    actual_session_id,
                    outcome_values,
                    actual_fingerprint,
                    reason,
                    observed_at,
                ),
            )
            connection.execute(
                """INSERT INTO forecast_calibration_facts
                   (id, forecast_id, outcome_id, metric_schema, close_mae,
                    p10_p90_interval_covered, p10_pinball_loss, p50_pinball_loss,
                    p90_pinball_loss, coverage_start, coverage_end, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid4()),
                    forecast_id,
                    outcome_id,
                    metric_schema,
                    close_mae,
                    None if interval_covered is None else int(interval_covered),
                    pinball_p10,
                    pinball_p50,
                    pinball_p90,
                    actual_session_id,
                    actual_session_id,
                    observed_at,
                ),
            )
            row = connection.execute(
                """SELECT o.*, f.calendar_revision
                   FROM forecast_outcomes AS o
                   JOIN forecast_records AS f ON f.id = o.forecast_id
                   WHERE o.id = ?""",
                (outcome_id,),
            ).fetchone()
        assert row is not None
        return self._outcome_row(row)

    def calibration_summary(self, *, metric_schema: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT COUNT(close_mae) AS sample_count,
                          MIN(CASE WHEN close_mae IS NOT NULL THEN coverage_start END) AS coverage_start,
                          MAX(CASE WHEN close_mae IS NOT NULL THEN coverage_end END) AS coverage_end
                   FROM forecast_calibration_facts WHERE metric_schema = ?""",
                (metric_schema,),
            ).fetchone()
        assert row is not None
        match = re.search(r"-v([1-9][0-9]*)$", metric_schema)
        return {
            "metric_schema": metric_schema,
            "metric_version": int(match.group(1)) if match else 1,
            "sample_count": int(row["sample_count"]),
            "coverage_start": row["coverage_start"],
            "coverage_end": row["coverage_end"],
        }

    def acquire_maturity_page(
        self, *, owner: str, ttl_seconds: int, limit: int
    ) -> list[dict[str, Any]]:
        """Lease one stable pending keyset page without advancing past unprocessed work."""
        if (
            not isinstance(owner, str)
            or not owner
            or isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 1 <= ttl_seconds <= 3600
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 256
        ):
            raise ValueError("forecast maturity page request is invalid")
        now_dt = _as_utc(self._clock())
        now = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=ttl_seconds))
        with self._immediate() as connection:
            cursor = connection.execute(
                "SELECT * FROM forecast_maturity_cursor WHERE cursor_name = 'forecast-maturity'"
            ).fetchone()
            if cursor is None:
                raise RuntimeError("forecast maturity cursor is unavailable")
            if (
                cursor["lease_owner"] is not None
                and cursor["lease_owner"] != owner
                and cursor["lease_until"] > now
            ):
                return []
            changed = connection.execute(
                """UPDATE forecast_maturity_cursor
                   SET lease_owner = ?, lease_until = ?,
                       transition_version = transition_version + 1, updated_at = ?
                   WHERE cursor_name = 'forecast-maturity'
                     AND (lease_owner IS NULL OR lease_owner = ? OR lease_until <= ?)""",
                (owner, lease_until, now, owner, now),
            ).rowcount
            if changed != 1:
                return []
            cursor = connection.execute(
                "SELECT * FROM forecast_maturity_cursor WHERE cursor_name = 'forecast-maturity'"
            ).fetchone()
            assert cursor is not None
            rows = self._pending_maturity_page(
                connection,
                after=(
                    str(cursor["cursor_created_at"]),
                    str(cursor["cursor_forecast_id"]),
                    int(cursor["cursor_horizon"]),
                ),
                limit=limit,
            )
            if not rows and (
                cursor["cursor_created_at"]
                or cursor["cursor_forecast_id"]
                or int(cursor["cursor_horizon"])
            ):
                connection.execute(
                    """UPDATE forecast_maturity_cursor
                       SET cursor_created_at = '', cursor_forecast_id = '', cursor_horizon = 0,
                           transition_version = transition_version + 1, updated_at = ?
                       WHERE cursor_name = 'forecast-maturity' AND lease_owner = ?""",
                    (now, owner),
                )
                rows = self._pending_maturity_page(connection, after=("", "", 0), limit=limit)
            if not rows:
                connection.execute(
                    """UPDATE forecast_maturity_cursor
                       SET lease_owner = NULL, lease_until = NULL,
                           transition_version = transition_version + 1, updated_at = ?
                       WHERE cursor_name = 'forecast-maturity' AND lease_owner = ?""",
                    (now, owner),
                )
                return []
            return [self._record_row(row) for row in rows]

    @staticmethod
    def _pending_maturity_page(
        connection: sqlite3.Connection,
        *,
        after: tuple[str, str, int],
        limit: int,
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """WITH maturity_horizons(horizon) AS (
                   SELECT 5 UNION ALL SELECT 20 UNION ALL SELECT 60
               )
               SELECT f.*, h.horizon AS maturity_horizon
               FROM forecast_records AS f
               JOIN maturity_horizons AS h ON h.horizon <= f.horizon
               LEFT JOIN forecast_outcomes AS o
                 ON o.forecast_id = f.id AND o.horizon = h.horizon
               WHERE o.id IS NULL
                 AND (f.created_at, f.id, h.horizon) > (?, ?, ?)
               ORDER BY f.created_at, f.id, h.horizon
               LIMIT ?""",
            (*after, limit),
        ).fetchall()

    def advance_maturity_cursor(
        self,
        *,
        owner: str,
        created_at: str,
        forecast_id: str,
        horizon: int,
    ) -> bool:
        if not owner or not created_at or not forecast_id or horizon not in {5, 20, 60}:
            raise ValueError("forecast maturity cursor identity is invalid")
        now = self.now()
        with self._immediate() as connection:
            changed = connection.execute(
                """UPDATE forecast_maturity_cursor
                   SET cursor_created_at = ?, cursor_forecast_id = ?, cursor_horizon = ?,
                       transition_version = transition_version + 1, updated_at = ?
                   WHERE cursor_name = 'forecast-maturity' AND lease_owner = ?
                     AND lease_until > ?
                     AND (cursor_created_at, cursor_forecast_id, cursor_horizon) < (?, ?, ?)""",
                (
                    created_at,
                    forecast_id,
                    horizon,
                    now,
                    owner,
                    now,
                    created_at,
                    forecast_id,
                    horizon,
                ),
            ).rowcount
        return changed == 1

    def release_maturity_page(self, *, owner: str) -> bool:
        if not owner:
            return False
        now = self.now()
        with self._immediate() as connection:
            changed = connection.execute(
                """UPDATE forecast_maturity_cursor
                   SET lease_owner = NULL, lease_until = NULL,
                       transition_version = transition_version + 1, updated_at = ?
                   WHERE cursor_name = 'forecast-maturity' AND lease_owner = ?""",
                (now, owner),
            ).rowcount
        return changed == 1

    def expire_maturity_leases(self, *, now: str | datetime) -> int:
        observed = _timestamp(_as_utc(now))
        with self._immediate() as connection:
            changed = connection.execute(
                """UPDATE forecast_maturity_cursor
                   SET lease_owner = NULL, lease_until = NULL,
                       transition_version = transition_version + 1, updated_at = ?
                   WHERE cursor_name = 'forecast-maturity'
                     AND lease_owner IS NOT NULL AND lease_until <= ?""",
                (observed, observed),
            ).rowcount
        return int(changed)

    def insert_fixture_forecast(self, payload: Mapping[str, object]) -> dict[str, Any]:
        """Insert one complete immutable record for focused governed-boundary tests."""
        forecast_id = str(payload["id"])
        principal = str(payload.get("principal", "fixture-principal"))
        instrument_id = str(payload["instrument_id"])
        horizon = int(payload["horizon"])
        fingerprint = str(payload["input_fingerprint"])
        created_at = str(payload["created_at"])
        if not principal:
            raise ValueError("fixture forecast principal is invalid")
        job_id = f"fixture-job-{forecast_id}"
        descriptor = {
            "artifact_id": f"fixture-{forecast_id}",
            "relative_path": f"forecast/{forecast_id}/paths.parquet",
            "schema_version": "forecast-output-v1",
            "byte_size": 1,
            "checksum_sha256": str(payload["paths_checksum_sha256"]),
            "sample_count": 32,
            "horizon": horizon,
            "feature_count": 6,
            "quantiles": payload.get("quantiles", {}),
            "quantiles_checksum_sha256": payload.get("quantiles_checksum_sha256"),
            "checkpoint_provenance": payload.get("checkpoint_provenance", {}),
        }
        with self._immediate() as connection:
            existing = connection.execute(
                "SELECT * FROM forecast_records WHERE id = ?", (forecast_id,)
            ).fetchone()
            if existing is not None:
                return self._record_row(existing)
            connection.execute(
                """INSERT INTO forecast_jobs
                   (id, principal, instrument_id, horizon, catalog_id, idempotency_key,
                    input_fingerprint, status, transition_version, retry_of_job_id, attempt,
                    lease_owner, lease_until, terminal_reason, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'fixture-catalog', ?, ?, 'completed',
                           1, NULL, 1, NULL, NULL, NULL, ?, ?)""",
                (
                    job_id,
                    principal,
                    instrument_id,
                    horizon,
                    job_id,
                    fingerprint,
                    created_at,
                    created_at,
                ),
            )
            fixture_job = connection.execute(
                "SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            self._append_job_transition(connection, fixture_job)
            connection.execute(
                """INSERT INTO forecast_records
                   (id, job_id, instrument_id, origin_session_id, calendar_id, calendar_revision,
                    future_session_ids_json, input_fingerprint, input_artifact_descriptor_json,
                    horizon, lookback, seed, temperature, top_k, top_p, sample_count, catalog_id,
                    source_revision, source_digest_sha256, model_revision, model_digest_sha256,
                    tokenizer_revision, tokenizer_digest_sha256, output_artifact_descriptor_json,
                    paths_checksum_sha256, validation_warnings_json, created_at)
                   VALUES (?, ?, ?, ?, 'cn-a', ?, ?, ?, '{}', ?, 1, 0, 1.0, 1, 1.0, 32,
                           'fixture-catalog', ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)""",
                (
                    forecast_id,
                    job_id,
                    instrument_id,
                    str(payload["origin_session_id"]),
                    str(payload["calendar_revision"]),
                    _canonical_json(payload["future_session_ids"]),
                    fingerprint,
                    horizon,
                    str(
                        payload.get("checkpoint_provenance", {}).get(
                            "source_revision", "fixture-source"
                        )
                    ),
                    fingerprint,
                    str(
                        payload.get("checkpoint_provenance", {}).get(
                            "model_revision", "fixture-model"
                        )
                    ),
                    fingerprint,
                    str(
                        payload.get("checkpoint_provenance", {}).get(
                            "tokenizer_revision", "fixture-tokenizer"
                        )
                    ),
                    fingerprint,
                    _canonical_json(descriptor),
                    str(payload["paths_checksum_sha256"]),
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM forecast_records WHERE id = ?", (forecast_id,)
            ).fetchone()
        assert row is not None
        return self._record_row(row)

    @staticmethod
    def _outcome_row(row: sqlite3.Row) -> dict[str, Any]:
        outcome = dict(row)
        raw_values = outcome.pop("actual_value_json")
        values = json.loads(raw_values) if raw_values else None
        outcome["actual_close"] = None if values is None else values.get("close")
        return outcome

    @staticmethod
    def _calibration_row(row: sqlite3.Row) -> dict[str, Any]:
        fact = dict(row)
        covered = fact.pop("p10_p90_interval_covered")
        fact["p10_p90_interval_covered"] = None if covered is None else bool(covered)
        fact["pinball_p10"] = fact.pop("p10_pinball_loss")
        fact["pinball_p50"] = fact.pop("p50_pinball_loss")
        fact["pinball_p90"] = fact.pop("p90_pinball_loss")
        return fact

    @staticmethod
    def _record_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        for field in (
            "future_session_ids_json",
            "input_artifact_descriptor_json",
            "output_artifact_descriptor_json",
            "validation_warnings_json",
        ):
            record[field.removesuffix("_json")] = json.loads(record.pop(field))
        raw_quantiles_descriptor = record.pop("quantiles_artifact_descriptor_json", None)
        record["quantiles_artifact_descriptor"] = (
            json.loads(raw_quantiles_descriptor)
            if isinstance(raw_quantiles_descriptor, str)
            else None
        )
        return record
