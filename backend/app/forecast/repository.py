"""Durable single-flight state and immutable Forecast record persistence."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence
from uuid import uuid4

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


def _digest_or_default(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and _SHA256.fullmatch(value) else fallback


class ForecastRepository:
    """Short-lived SQLite transactions for the Forecast job and record ledger."""

    def __init__(self, database_path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.database_path = Path(database_path)
        self._clock = clock or (lambda: datetime.now(UTC))

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
        if not all(isinstance(value, str) and value for value in (principal, instrument_id, catalog_id, idempotency_key)):
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
            row = connection.execute("SELECT * FROM forecast_jobs WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return dict(row)

    def create_retry_job(self, *, source_job_id: str, idempotency_key: str) -> dict[str, Any]:
        """Append an explicit retry lineage; duplicate request handling never calls this."""
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ValueError("forecast retry identity is invalid")
        now = self.now()
        with self._immediate() as connection:
            source = connection.execute("SELECT * FROM forecast_jobs WHERE id = ?", (source_job_id,)).fetchone()
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
            row = connection.execute("SELECT * FROM forecast_jobs WHERE id = ?", (identifier,)).fetchone()
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
            row = connection.execute("SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)).fetchone()
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
            row = connection.execute("SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)).fetchone()
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
                None if terminal else connection.execute(
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
                raise ValueError("forecast job transition rejected by stale state, version, or owner")
            row = connection.execute("SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)).fetchone()
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
        descriptor = self._validated_output_descriptor(output_descriptor)
        now = self.now()
        with self._immediate() as connection:
            canonical = connection.execute("SELECT * FROM forecast_records WHERE job_id = ?", (job_id,)).fetchone()
            if canonical is not None:
                return self._record_row(canonical)
            job = connection.execute("SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)).fetchone()
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
                raise ValueError("forecast commit rejected by stale state, version, owner, or lease")
            if immutable_record.get("instrument_id") != job["instrument_id"]:
                raise ValueError("forecast record instrument does not match its job")
            if int(immutable_record.get("horizon", 0)) != int(job["horizon"]):
                raise ValueError("forecast record horizon does not match its job")
            if immutable_record.get("catalog_id") != job["catalog_id"]:
                raise ValueError("forecast record catalog does not match its job")
            if immutable_record.get("input_fingerprint") != job["input_fingerprint"]:
                raise ValueError("forecast record input does not match its job")
            if int(immutable_record.get("sample_count", 0)) != 32:
                raise ValueError("forecast record must retain exactly 32 paths")

            fallback_digest = str(job["input_fingerprint"])
            record_id = str(uuid4())
            values = (
                record_id,
                job_id,
                job["instrument_id"],
                str(immutable_record.get("origin_session_id", "origin-session")),
                str(immutable_record.get("calendar_id", "cn-a")),
                str(immutable_record.get("calendar_revision", "governed-calendar-v1")),
                _canonical_json(immutable_record.get("future_session_ids", [])),
                job["input_fingerprint"],
                _canonical_json(immutable_record.get("input_artifact_descriptor", {})),
                job["horizon"],
                int(immutable_record.get("lookback", 1)),
                int(immutable_record.get("seed", 0)),
                float(immutable_record.get("temperature", 1.0)),
                int(immutable_record.get("top_k", 1)),
                float(immutable_record.get("top_p", 1.0)),
                32,
                job["catalog_id"],
                str(immutable_record.get("source_revision", "unknown-source")),
                _digest_or_default(immutable_record.get("source_digest_sha256"), fallback_digest),
                str(immutable_record.get("model_revision", "unknown-model")),
                _digest_or_default(immutable_record.get("model_digest_sha256"), fallback_digest),
                str(immutable_record.get("tokenizer_revision", "unknown-tokenizer")),
                _digest_or_default(immutable_record.get("tokenizer_digest_sha256"), fallback_digest),
                _canonical_json(descriptor),
                descriptor["checksum_sha256"],
                _canonical_json(immutable_record.get("validation_warnings", [])),
                now,
            )
            connection.execute(
                """INSERT INTO forecast_records
                   (id, job_id, instrument_id, origin_session_id, calendar_id, calendar_revision,
                    future_session_ids_json, input_fingerprint, input_artifact_descriptor_json,
                    horizon, lookback, seed, temperature, top_k, top_p, sample_count, catalog_id,
                    source_revision, source_digest_sha256, model_revision, model_digest_sha256,
                    tokenizer_revision, tokenizer_digest_sha256, output_artifact_descriptor_json,
                    paths_checksum_sha256, validation_warnings_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            canonical = connection.execute("SELECT * FROM forecast_records WHERE id = ?", (record_id,)).fetchone()
        assert canonical is not None
        return self._record_row(canonical)

    @staticmethod
    def _validated_output_descriptor(value: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError("forecast output descriptor is invalid")
        required = {
            "artifact_id",
            "relative_path",
            "schema_version",
            "byte_size",
            "checksum_sha256",
            "sample_count",
            "horizon",
            "feature_count",
        }
        if not required.issubset(value):
            raise ValueError("forecast output descriptor is incomplete")
        relative_path = value["relative_path"]
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or relative_path.startswith(("/", "\\"))
            or ".." in Path(relative_path).parts
        ):
            raise ValueError("forecast output descriptor path is invalid")
        if not isinstance(value["checksum_sha256"], str) or not _SHA256.fullmatch(value["checksum_sha256"]):
            raise ValueError("forecast output descriptor checksum is invalid")
        if int(value["sample_count"]) != 32 or int(value["horizon"]) not in {5, 20, 60}:
            raise ValueError("forecast output descriptor shape is invalid")
        if int(value["byte_size"]) < 0 or int(value["feature_count"]) <= 0:
            raise ValueError("forecast output descriptor bounds are invalid")
        return {key: value[key] for key in sorted(required)}

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
                        {"job_id": job["id"], "action": "terminalized", "status": "validation_failed"}
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
                outcomes.append({"job_id": job["id"], "action": "terminalized", "status": "interrupted"})
        return outcomes

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM forecast_jobs WHERE id = ?", (job_id,)).fetchone()
        return None if row is None else dict(row)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM forecast_jobs ORDER BY created_at, id").fetchall()
        return [dict(row) for row in rows]

    def forecast_for_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM forecast_records WHERE job_id = ?", (job_id,)).fetchone()
        return None if row is None else self._record_row(row)

    def list_forecasts(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM forecast_records ORDER BY created_at, id").fetchall()
        return [self._record_row(row) for row in rows]

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
        return record
