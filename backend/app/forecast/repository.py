"""Durable single-flight state and immutable Forecast record persistence."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
import math
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from pathlib import PurePosixPath
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

    def bind_commit_identity(
        self, *, job_id: str, immutable_record: Mapping[str, object]
    ) -> None:
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
                return self._record_row(canonical)
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
            descriptor = self._validated_output_descriptor(output_descriptor, record=record)

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
                _canonical_json(descriptor),
                descriptor["checksum_sha256"],
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
            canonical = connection.execute(
                "SELECT * FROM forecast_records WHERE id = ?", (record_id,)
            ).fetchone()
        self._commit_identities.pop(job_id, None)
        assert canonical is not None
        return self._record_row(canonical)

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
        sample_count = _strict_int(
            value["sample_count"], "sample count", minimum=32, maximum=32
        )
        lookback = _strict_int(value["lookback"], "lookback", minimum=1, maximum=4096)
        seed = _strict_int(value["seed"], "seed", minimum=0, maximum=2**63 - 1)
        top_k = _strict_int(value["top_k"], "top-k", minimum=1, maximum=4096)
        temperature = _strict_float(
            value["temperature"], "temperature", minimum=0.0, maximum=10.0,
            exclusive_minimum=True,
        )
        top_p = _strict_float(
            value["top_p"], "top-p", minimum=0.0, maximum=1.0,
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
        if set(value) != required:
            raise ValueError("forecast output descriptor is incomplete")
        relative = value["relative_path"]
        if (
            not isinstance(relative, str)
            or not relative
            or relative == "."
            or ":" in relative
            or "\\" in relative
        ):
            raise ValueError("forecast output descriptor path is invalid")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != relative:
            raise ValueError("forecast output descriptor path is invalid")
        unresolved = self.artifact_root / Path(*pure.parts)
        if unresolved.is_symlink():
            raise ValueError("forecast output artifact symlinks are forbidden")
        try:
            candidate = unresolved.resolve(strict=True)
            candidate.relative_to(self.artifact_root)
        except (OSError, ValueError) as error:
            raise ValueError("forecast output artifact escapes its managed root") from error
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError("forecast output artifact is not a regular file")
        payload = candidate.read_bytes()
        byte_size = _strict_int(value["byte_size"], "output byte size", minimum=1)
        checksum = _digest(value["checksum_sha256"], "output checksum")
        if byte_size != len(payload) or sha256(payload).hexdigest() != checksum:
            raise ValueError("forecast output artifact checksum or size diverges")
        sample_count = _strict_int(
            value["sample_count"], "output sample count", minimum=32, maximum=32
        )
        horizon = _strict_int(value["horizon"], "output horizon", minimum=1, maximum=60)
        feature_count = _strict_int(value["feature_count"], "output feature count", minimum=1)
        if horizon != record["horizon"] or sample_count != record["sample_count"]:
            raise ValueError("forecast output descriptor shape diverges from its record")
        if feature_count != len(record["feature_schema"]):
            raise ValueError("forecast output features diverge from its record")
        return {
            "artifact_id": _nonempty_text(value["artifact_id"], "output artifact"),
            "relative_path": relative,
            "schema_version": _immutable_text(value["schema_version"], "output schema"),
            "byte_size": byte_size,
            "checksum_sha256": checksum,
            "sample_count": sample_count,
            "horizon": horizon,
            "feature_count": feature_count,
        }

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

    def get_forecast(self, forecast_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM forecast_records WHERE id = ?", (forecast_id,)
            ).fetchone()
        return None if row is None else self._record_row(row)

    def list_forecasts_for_instrument(self, instrument_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM forecast_records
                   WHERE instrument_id = ? ORDER BY created_at DESC, id DESC""",
                (instrument_id,),
            ).fetchall()
        return [self._record_row(row) for row in rows]

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
            if connection.execute(
                "SELECT 1 FROM forecast_records WHERE id = ?", (forecast_id,)
            ).fetchone() is None:
                raise ValueError("forecast record does not exist")
            outcome_id = str(uuid4())
            outcome_values = None if actual_close is None else _canonical_json({"close": actual_close})
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

    def expire_maturity_leases(self, *, now: str | datetime) -> int:
        """Validate the recovery cursor time; maturity commits are lease-free and atomic."""
        _as_utc(now)
        return 0

    def insert_fixture_forecast(self, payload: Mapping[str, object]) -> dict[str, Any]:
        """Insert one complete immutable record for focused governed-boundary tests."""
        forecast_id = str(payload["id"])
        instrument_id = str(payload["instrument_id"])
        horizon = int(payload["horizon"])
        fingerprint = str(payload["input_fingerprint"])
        created_at = str(payload["created_at"])
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
                   VALUES (?, 'fixture-principal', ?, ?, 'fixture-catalog', ?, ?, 'completed',
                           1, NULL, 1, NULL, NULL, NULL, ?, ?)""",
                (job_id, instrument_id, horizon, job_id, fingerprint, created_at, created_at),
            )
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
                    str(payload.get("checkpoint_provenance", {}).get("source_revision", "fixture-source")),
                    fingerprint,
                    str(payload.get("checkpoint_provenance", {}).get("model_revision", "fixture-model")),
                    fingerprint,
                    str(payload.get("checkpoint_provenance", {}).get("tokenizer_revision", "fixture-tokenizer")),
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
        output = record["output_artifact_descriptor"]
        if isinstance(output, dict):
            for field in (
                "quantiles",
                "quantiles_checksum_sha256",
                "checkpoint_provenance",
            ):
                if field in output:
                    record[field] = output[field]
        return record
