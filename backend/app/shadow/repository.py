"""Append-only SQLite persistence for immutable Shadow evidence facts."""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from app.operational.migrations import migrate_operational_db


class ShadowRepositoryError(RuntimeError):
    """A Shadow fact could not be persisted or safely reconstructed."""


class ShadowEvidenceError(ShadowRepositoryError):
    """An evidence manifest is incomplete, inconsistent, or ineligible."""


def _canonical_json(value: object, field: str) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ShadowRepositoryError(f"{field} must be canonical JSON") from error


def _json_object(raw: object, field: str) -> dict[str, Any]:
    value = _json_value(raw, field)
    if not isinstance(value, dict):
        raise ShadowRepositoryError(f"persisted {field} is invalid")
    return value


def _json_list(raw: object, field: str) -> list[Any]:
    value = _json_value(raw, field)
    if not isinstance(value, list):
        raise ShadowRepositoryError(f"persisted {field} is invalid")
    return value


def _json_value(raw: object, field: str) -> Any:
    if not isinstance(raw, str):
        raise ShadowRepositoryError(f"persisted {field} is invalid")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ShadowRepositoryError(f"persisted {field} is invalid") from error


class ShadowRepository:
    """Use short transactions over the sole operational database; never upsert facts."""

    def __init__(
        self,
        database_path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._artifact_verifier: Callable[[Mapping[str, object]], bytes] | None = None
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

    def set_artifact_verifier(
        self, verifier: Callable[[Mapping[str, object]], bytes]
    ) -> None:
        """Attach the domain artifact verifier used before evidence selection."""
        if not callable(verifier):
            raise TypeError("artifact verifier must be callable")
        self._artifact_verifier = verifier

    def now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()

    def append_import_batch(
        self,
        *,
        batch_id: str,
        principal: str,
        raw_artifact: Mapping[str, object],
        content_sha256: str,
        source_label: str,
        importer_version: str,
        mapping_version: str,
        supersedes_batch_id: str | None,
        source_row_count: int,
        trades: Sequence[Mapping[str, object]],
        rejected_row_count: int,
        diagnostics: Sequence[Mapping[str, object]],
        status: str,
    ) -> dict[str, Any]:
        if status not in {"completed", "rejected"}:
            raise ShadowRepositoryError("import status is invalid")
        if status == "rejected" and trades:
            raise ShadowRepositoryError("rejected imports cannot persist trade facts")
        if len(content_sha256) != 64:
            raise ShadowRepositoryError("content checksum is invalid")
        created_at = self.now()
        descriptor_json = _canonical_json(dict(raw_artifact), "raw artifact descriptor")
        diagnostics_json = _canonical_json(list(diagnostics), "import diagnostics")
        with self._connection() as connection, connection:
            if supersedes_batch_id is not None:
                predecessor = connection.execute(
                    "SELECT principal FROM shadow_import_batches WHERE id = ?",
                    (supersedes_batch_id,),
                ).fetchone()
                if predecessor is None or predecessor["principal"] != principal:
                    raise ShadowRepositoryError("superseded batch is unavailable")
            connection.execute(
                """INSERT INTO shadow_import_batches
                   (id, principal, raw_artifact_descriptor_json, content_sha256,
                    source_label, importer_version, mapping_version, supersedes_batch_id,
                    source_row_count, normalized_row_count, rejected_row_count,
                    diagnostics_json, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_id,
                    principal,
                    descriptor_json,
                    content_sha256,
                    source_label,
                    importer_version,
                    mapping_version,
                    supersedes_batch_id,
                    source_row_count,
                    len(trades),
                    rejected_row_count,
                    diagnostics_json,
                    status,
                    created_at,
                ),
            )
            for trade in trades:
                connection.execute(
                    """INSERT INTO shadow_trade_facts
                       (id, batch_id, row_identity, duplicate_group_hash, broker_fill_id,
                        account_alias, symbol, side, executed_at, quantity, price, fees,
                        currency, source_row_ordinal, source_values_json,
                        normalized_payload_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(trade["id"]),
                        batch_id,
                        str(trade["row_identity"]),
                        str(trade["duplicate_group_hash"]),
                        trade.get("broker_fill_id"),
                        str(trade["account_alias"]),
                        str(trade["symbol"]),
                        str(trade["side"]),
                        str(trade["executed_at"]),
                        float(trade["quantity"]),
                        float(trade["price"]),
                        float(trade["fees"]),
                        str(trade["currency"]),
                        int(trade["source_row_ordinal"]),
                        _canonical_json(trade["source_values"], "source values"),
                        _canonical_json(trade["normalized"], "normalized payload"),
                        created_at,
                    ),
                )
        persisted = self.get_import_batch(batch_id)
        if persisted is None:
            raise ShadowRepositoryError("persisted import batch is unavailable")
        return persisted

    def get_import_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM shadow_import_batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if row is None:
                return None
            same = connection.execute(
                """SELECT id FROM shadow_import_batches
                   WHERE content_sha256 = ? AND id != ?
                     AND (created_at < ? OR (created_at = ? AND id < ?))
                   ORDER BY created_at, id LIMIT 1""",
                (
                    row["content_sha256"],
                    row["id"],
                    row["created_at"],
                    row["created_at"],
                    row["id"],
                ),
            ).fetchone()
        return self._import_batch_row(row, None if same is None else str(same["id"]))

    def list_import_batches(self, *, principal: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM shadow_import_batches
                   WHERE principal = ? ORDER BY created_at, id""",
                (principal,),
            ).fetchall()
        return [self.get_import_batch(str(row["id"])) for row in rows]  # type: ignore[list-item]

    def list_trade_facts(self, *, batch_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM shadow_trade_facts WHERE batch_id = ?
                   ORDER BY source_row_ordinal, id""",
                (batch_id,),
            ).fetchall()
        return [self._trade_row(row) for row in rows]

    def create_evidence_set(
        self,
        *,
        principal: str,
        included_batch_ids: Sequence[str],
        included_trade_ids: Sequence[str],
        exclusions: Sequence[Mapping[str, object]],
    ) -> dict[str, Any]:
        batch_ids = sorted(self._unique_nonempty(included_batch_ids, "batch"))
        if not batch_ids:
            raise ShadowEvidenceError("evidence requires at least one completed batch")
        trade_ids = sorted(self._unique_nonempty(included_trade_ids, "trade"))
        exclusion_items = self._normalize_exclusions(exclusions)
        excluded_ids = [item["trade_id"] for item in exclusion_items]
        if set(trade_ids) & set(excluded_ids):
            raise ShadowEvidenceError("included and excluded trades must be disjoint")

        with self._connection() as connection:
            placeholders = ",".join("?" for _ in batch_ids)
            batch_rows = connection.execute(
                f"SELECT * FROM shadow_import_batches WHERE id IN ({placeholders})",
                batch_ids,
            ).fetchall()
            if len(batch_rows) != len(batch_ids) or any(
                row["status"] != "completed" or row["principal"] != principal
                for row in batch_rows
            ):
                raise ShadowEvidenceError("evidence requires an attributable completed batch")
            all_trade_rows = connection.execute(
                f"""SELECT * FROM shadow_trade_facts WHERE batch_id IN ({placeholders})
                    ORDER BY id""",
                batch_ids,
            ).fetchall()

        available_ids = {str(row["id"]) for row in all_trade_rows}
        selected_ids = set(trade_ids) | set(excluded_ids)
        if selected_ids != available_ids:
            raise ShadowEvidenceError(
                "every trade in an included batch must be explicitly included or excluded"
            )
        if self._artifact_verifier is not None:
            for row in batch_rows:
                descriptor = _json_object(
                    row["raw_artifact_descriptor_json"], "raw artifact descriptor"
                )
                try:
                    self._artifact_verifier(descriptor)
                except Exception as error:
                    raise ShadowEvidenceError(
                        "completed batch artifact failed integrity verification"
                    ) from error

        manifest = {
            "included_batch_ids": batch_ids,
            "included_trade_ids": trade_ids,
            "exclusions": exclusion_items,
        }
        manifest_json = _canonical_json(manifest, "evidence manifest")
        fingerprint = sha256(manifest_json.encode("utf-8")).hexdigest()
        with self._connection() as connection, connection:
            existing = connection.execute(
                "SELECT id FROM shadow_evidence_sets WHERE principal = ? AND fingerprint = ?",
                (principal, fingerprint),
            ).fetchone()
            if existing is not None:
                existing_id = str(existing["id"])
            else:
                existing_id = uuid4().hex
                now = self.now()
                connection.execute(
                    """INSERT INTO shadow_evidence_sets
                       (id, principal, fingerprint, manifest_json, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (existing_id, principal, fingerprint, manifest_json, now),
                )
                for ordinal, batch_id in enumerate(batch_ids):
                    connection.execute(
                        """INSERT INTO shadow_evidence_batches
                           (evidence_set_id, batch_id, ordinal, created_at)
                           VALUES (?, ?, ?, ?)""",
                        (existing_id, batch_id, ordinal, now),
                    )
                for ordinal, trade_id in enumerate(trade_ids):
                    connection.execute(
                        """INSERT INTO shadow_evidence_members
                           (evidence_set_id, trade_id, ordinal, created_at)
                           VALUES (?, ?, ?, ?)""",
                        (existing_id, trade_id, ordinal, now),
                    )
                for item in exclusion_items:
                    connection.execute(
                        """INSERT INTO shadow_evidence_exclusions
                           (id, evidence_set_id, trade_id, reason, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (uuid4().hex, existing_id, item["trade_id"], item["reason"], now),
                    )
        persisted = self.get_evidence_set(existing_id)
        if persisted is None:
            raise ShadowRepositoryError("persisted evidence set is unavailable")
        return persisted

    def get_evidence_set(self, evidence_set_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM shadow_evidence_sets WHERE id = ?", (evidence_set_id,)
            ).fetchone()
        return None if row is None else self._evidence_row(row)

    def list_evidence_sets(self, *, principal: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM shadow_evidence_sets WHERE principal = ?
                   ORDER BY created_at, id""",
                (principal,),
            ).fetchall()
        return [self._evidence_row(row) for row in rows]

    def resolve_evidence_trades(self, *, evidence_set_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT trade.* FROM shadow_evidence_members AS member
                   JOIN shadow_trade_facts AS trade ON trade.id = member.trade_id
                   WHERE member.evidence_set_id = ? ORDER BY member.ordinal""",
                (evidence_set_id,),
            ).fetchall()
        return [self._trade_row(row) for row in rows]

    @staticmethod
    def list_operational_mutations() -> list[dict[str, object]]:
        """Shadow evidence intentionally has no account, position, or broker mutations."""
        return []

    @staticmethod
    def _unique_nonempty(values: Sequence[str], field: str) -> list[str]:
        normalized = list(values)
        if any(not isinstance(value, str) or not value.strip() for value in normalized):
            raise ShadowEvidenceError(f"{field} identifiers are invalid")
        if len(normalized) != len(set(normalized)):
            raise ShadowEvidenceError(f"{field} identifiers must be unique")
        return normalized

    @staticmethod
    def _normalize_exclusions(
        exclusions: Sequence[Mapping[str, object]],
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in exclusions:
            if not isinstance(item, Mapping) or set(item) != {"trade_id", "reason"}:
                raise ShadowEvidenceError("evidence exclusion schema is invalid")
            trade_id = item["trade_id"]
            reason = item["reason"]
            if not isinstance(trade_id, str) or not trade_id.strip():
                raise ShadowEvidenceError("evidence exclusion trade identifier is invalid")
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 1_000:
                raise ShadowEvidenceError("evidence exclusion reason is required")
            normalized.append({"trade_id": trade_id, "reason": reason.strip()})
        normalized.sort(key=lambda item: item["trade_id"])
        ids = [item["trade_id"] for item in normalized]
        if len(ids) != len(set(ids)):
            raise ShadowEvidenceError("evidence exclusions must be unique")
        return normalized

    @staticmethod
    def _import_batch_row(row: sqlite3.Row, same_content_as: str | None) -> dict[str, Any]:
        record = dict(row)
        raw_artifact = _json_object(
            record.pop("raw_artifact_descriptor_json"), "raw artifact descriptor"
        )
        diagnostics = _json_list(record.pop("diagnostics_json"), "import diagnostics")
        return {
            **record,
            "raw_artifact": raw_artifact,
            "diagnostics": diagnostics,
            "same_content_as": same_content_as,
        }

    @staticmethod
    def _trade_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        source_values = _json_object(record.pop("source_values_json"), "source values")
        normalized = _json_object(
            record.pop("normalized_payload_json"), "normalized payload"
        )
        return {**record, "source_values": source_values, "normalized": normalized}

    @staticmethod
    def _evidence_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        manifest = _json_object(record.pop("manifest_json"), "evidence manifest")
        return {**record, **manifest}
