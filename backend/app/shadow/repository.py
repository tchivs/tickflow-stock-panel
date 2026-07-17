"""Append-only SQLite persistence for immutable Shadow evidence facts."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.operational.migrations import migrate_operational_db
from app.shadow.schemas import (
    ShadowAssumptionError,
    validate_assumption_pair,
    validate_persisted_assumption_pair,
)


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


def _canonical_digest(value: object, field: str) -> str:
    return sha256(_canonical_json(value, field).encode("utf-8")).hexdigest()


def _candidate_identity(candidate: Mapping[str, object]) -> tuple[str, str]:
    logical_key = {
        "evidence_set_id": candidate["evidence_set_id"],
        "distiller_version": candidate["distiller_version"],
        "rule_schema_version": candidate["rule_schema_version"],
        "seed": candidate["seed"],
    }
    identity = {
        key: candidate[key]
        for key in (
            "distiller_version",
            "rule_schema_version",
            "rules",
            "features",
            "parameters",
            "exit_assumptions",
            "holding_assumptions",
            "source_batch_ids",
            "evidence_set_id",
            "evidence_set_fingerprint",
            "training_window",
            "seed",
            "class_balance",
            "metrics",
            "limitations",
            "negative_sampling",
            "canonical_rules_json",
            "rule_fingerprint",
            "training_replay",
        )
    }
    return (
        _canonical_digest(logical_key, "candidate logical key"),
        _canonical_digest(identity, "candidate request identity"),
    )


def _retention_identity(payload: Mapping[str, object]) -> tuple[str, str]:
    logical_key = {
        "candidate_id": payload["candidate_id"],
        "in_sample_evaluation_id": payload["in_sample_evaluation_id"],
        "out_of_sample_evaluation_id": payload["out_of_sample_evaluation_id"],
    }
    return (
        _canonical_digest(logical_key, "retention logical key"),
        _canonical_digest(dict(payload), "retention decision identity"),
    )


def _evaluation_pair_identity(payload: Mapping[str, object]) -> tuple[str, str | None]:
    pair_key = {
        key: payload[key]
        for key in (
            "candidate_id",
            "evidence_set_id",
            "evidence_set_fingerprint",
            "in_sample_window",
            "out_of_sample_window",
            "adjustment_policy",
            "cost_policy",
        )
    }
    key_digest = _canonical_digest(pair_key, "evaluation pair logical key")
    splits = payload.get("splits")
    if splits is None:
        return key_digest, None
    return key_digest, _canonical_digest({**pair_key, "splits": splits}, "evaluation pair identity")


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
        evidence_member_limit: int = 200_000,
    ) -> None:
        self.database_path = Path(database_path)
        self._clock = clock or (lambda: datetime.now(UTC))
        if not isinstance(evidence_member_limit, int) or not 1 <= evidence_member_limit <= 200_000:
            raise ValueError("evidence member limit must be between 1 and 200000")
        self.evidence_member_limit = evidence_member_limit
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

    def set_artifact_verifier(self, verifier: Callable[[Mapping[str, object]], bytes]) -> None:
        """Attach the domain artifact verifier used before evidence selection."""
        if not callable(verifier):
            raise TypeError("artifact verifier must be callable")
        self._artifact_verifier = verifier

    def now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()

    @staticmethod
    def _page_window(offset: int, limit: int) -> tuple[int, int]:
        if not isinstance(offset, int) or offset < 0 or offset > 1_000_000:
            raise ShadowRepositoryError("page offset is invalid")
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            raise ShadowRepositoryError("page limit is invalid")
        return offset, limit

    @staticmethod
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
                   WHERE principal = ? AND content_sha256 = ? AND id != ?
                     AND (created_at < ? OR (created_at = ? AND id < ?))
                   ORDER BY created_at, id LIMIT 1""",
                (
                    row["principal"],
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

    def page_import_batches(
        self, *, principal: str, offset: int, limit: int
    ) -> dict[str, Any]:
        offset, limit = self._page_window(offset, limit)
        with self._connection() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM shadow_import_batches WHERE principal = ?",
                    (principal,),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """SELECT batch.*,
                          (SELECT prior.id FROM shadow_import_batches AS prior
                           WHERE prior.principal = batch.principal
                             AND prior.content_sha256 = batch.content_sha256
                             AND prior.id != batch.id
                             AND (prior.created_at < batch.created_at
                                  OR (prior.created_at = batch.created_at AND prior.id < batch.id))
                           ORDER BY prior.created_at, prior.id LIMIT 1) AS scoped_same_content_as
                   FROM shadow_import_batches AS batch
                   WHERE batch.principal = ?
                   ORDER BY batch.created_at DESC, batch.id DESC
                   LIMIT ? OFFSET ?""",
                (principal, limit, offset),
            ).fetchall()
        items = [
            self._import_batch_row(row, row["scoped_same_content_as"])
            for row in rows
        ]
        return self._page_result(items, offset=offset, limit=limit, total=total)

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
        requested_trade_ids = self._unique_nonempty(included_trade_ids, "trade")
        exclusion_items = self._normalize_exclusions(exclusions)
        excluded_ids = [item["trade_id"] for item in exclusion_items]
        if set(requested_trade_ids) & set(excluded_ids):
            raise ShadowEvidenceError("included and excluded trades must be disjoint")

        with self._connection() as connection:
            placeholders = ",".join("?" for _ in batch_ids)
            batch_rows = connection.execute(
                f"""SELECT * FROM shadow_import_batches
                    WHERE id IN ({placeholders}) AND principal = ? AND status = 'completed'""",
                (*batch_ids, principal),
            ).fetchall()
            if len(batch_rows) != len(batch_ids):
                raise ShadowEvidenceError("evidence requires an attributable completed batch")
            aggregate_member_count = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM shadow_trade_facts WHERE batch_id IN ({placeholders})",
                    batch_ids,
                ).fetchone()[0]
            )
            if aggregate_member_count > self.evidence_member_limit:
                raise ShadowEvidenceError("evidence aggregate member limit exceeded")
            all_trade_rows = connection.execute(
                f"""SELECT * FROM shadow_trade_facts WHERE batch_id IN ({placeholders})
                    ORDER BY batch_id, source_row_ordinal, id""",
                batch_ids,
            ).fetchall()

        available_ids = {str(row["id"]) for row in all_trade_rows}
        selected_ids = set(requested_trade_ids) | set(excluded_ids)
        if selected_ids != available_ids:
            raise ShadowEvidenceError(
                "every trade in an included batch must be explicitly included or excluded"
            )
        included_id_set = set(requested_trade_ids)
        trade_ids = [str(row["id"]) for row in all_trade_rows if str(row["id"]) in included_id_set]
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

    def page_evidence_sets(
        self, *, principal: str, offset: int, limit: int
    ) -> dict[str, Any]:
        offset, limit = self._page_window(offset, limit)
        with self._connection() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM shadow_evidence_sets WHERE principal = ?",
                    (principal,),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """SELECT * FROM shadow_evidence_sets WHERE principal = ?
                   ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?""",
                (principal, limit, offset),
            ).fetchall()
        items = [self._evidence_row(row) for row in rows]
        return self._page_result(items, offset=offset, limit=limit, total=total)

    def resolve_evidence_trades(self, *, evidence_set_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT trade.* FROM shadow_evidence_members AS member
                   JOIN shadow_trade_facts AS trade ON trade.id = member.trade_id
                   WHERE member.evidence_set_id = ? ORDER BY member.ordinal""",
                (evidence_set_id,),
            ).fetchall()
        return [self._trade_row(row) for row in rows]

    def append_candidate(self, candidate: dict[str, object]) -> dict[str, Any]:
        """Persist or replay one content-complete canonical candidate fact."""
        required = {
            "distiller_version",
            "rule_schema_version",
            "rules",
            "features",
            "parameters",
            "exit_assumptions",
            "holding_assumptions",
            "source_batch_ids",
            "evidence_set_id",
            "evidence_set_fingerprint",
            "training_window",
            "seed",
            "class_balance",
            "metrics",
            "limitations",
            "created_at",
            "negative_sampling",
            "canonical_rules_json",
            "rule_fingerprint",
            "training_replay",
        }
        if set(candidate) != required:
            raise ShadowRepositoryError("candidate fact schema is invalid")
        try:
            assumptions = validate_assumption_pair(
                exit_assumptions=candidate["exit_assumptions"],
                holding_assumptions=candidate["holding_assumptions"],
            )
        except ShadowAssumptionError as error:
            raise ShadowRepositoryError("candidate assumptions are invalid") from error
        candidate = {
            **candidate,
            "exit_assumptions": assumptions.exit,
            "holding_assumptions": assumptions.holding,
        }
        canonical_rules_json = _canonical_json(candidate["rules"], "candidate rules")
        if (
            candidate["canonical_rules_json"] != canonical_rules_json
            or candidate["rule_fingerprint"]
            != sha256(canonical_rules_json.encode("utf-8")).hexdigest()
        ):
            raise ShadowRepositoryError(
                "candidate replay conflict: canonical rule identity is invalid"
            )
        evidence = self.get_evidence_set(str(candidate["evidence_set_id"]))
        if (
            evidence is None
            or candidate["evidence_set_fingerprint"] != evidence["fingerprint"]
            or candidate["source_batch_ids"] != evidence["included_batch_ids"]
        ):
            raise ShadowRepositoryError("candidate evidence attribution is invalid")

        logical_digest, request_digest = _candidate_identity(candidate)
        identifier = uuid4().hex
        parameters_record = {
            "parameters": candidate["parameters"],
            "negative_sampling": candidate["negative_sampling"],
            "canonical_rules_json": canonical_rules_json,
            "rule_fingerprint": candidate["rule_fingerprint"],
            "training_replay": candidate["training_replay"],
        }
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT * FROM shadow_candidates
                   WHERE evidence_set_id = ? AND distiller_version = ?
                     AND rule_schema_version = ? AND seed = ?""",
                (
                    candidate["evidence_set_id"],
                    candidate["distiller_version"],
                    candidate["rule_schema_version"],
                    candidate["seed"],
                ),
            ).fetchone()
            identity = connection.execute(
                """SELECT request_digest, candidate_id
                   FROM shadow_candidate_request_identities
                   WHERE logical_key_digest = ?""",
                (logical_digest,),
            ).fetchone()
            if existing is not None:
                persisted_digest = _candidate_identity(self._candidate_row(existing))[1]
                if persisted_digest != request_digest or (
                    identity is not None
                    and (
                        identity["request_digest"] != request_digest
                        or identity["candidate_id"] != existing["id"]
                    )
                ):
                    raise ShadowRepositoryError(
                        "candidate replay conflict: canonical request digest diverged"
                    )
                if identity is None:
                    connection.execute(
                        """INSERT INTO shadow_candidate_request_identities
                           (logical_key_digest, request_digest, candidate_id, created_at)
                           VALUES (?, ?, ?, ?)""",
                        (logical_digest, request_digest, existing["id"], self.now()),
                    )
            else:
                if identity is not None:
                    raise ShadowRepositoryError(
                        "candidate replay conflict: logical identity is inconsistent"
                    )
                connection.execute(
                    """INSERT INTO shadow_candidates
                       (id, evidence_set_id, distiller_version, rule_schema_version,
                        rules_json, features_json, parameters_json, exit_assumptions_json,
                        holding_assumptions_json, source_batch_ids_json,
                        evidence_set_fingerprint, training_window_json, seed,
                        class_balance_json, metrics_json, limitations_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        identifier,
                        candidate["evidence_set_id"],
                        candidate["distiller_version"],
                        candidate["rule_schema_version"],
                        canonical_rules_json,
                        _canonical_json(candidate["features"], "candidate features"),
                        _canonical_json(parameters_record, "candidate parameters"),
                        assumptions.exit_json,
                        assumptions.holding_json,
                        _canonical_json(candidate["source_batch_ids"], "source batch ids"),
                        candidate["evidence_set_fingerprint"],
                        _canonical_json(candidate["training_window"], "training window"),
                        candidate["seed"],
                        _canonical_json(candidate["class_balance"], "class balance"),
                        _canonical_json(candidate["metrics"], "candidate metrics"),
                        _canonical_json(candidate["limitations"], "candidate limitations"),
                        candidate["created_at"],
                    ),
                )
                connection.execute(
                    """INSERT INTO shadow_candidate_request_identities
                       (logical_key_digest, request_digest, candidate_id, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (logical_digest, request_digest, identifier, self.now()),
                )
                existing = connection.execute(
                    "SELECT * FROM shadow_candidates WHERE id = ?", (identifier,)
                ).fetchone()
        if existing is None:
            raise ShadowRepositoryError("persisted candidate is unavailable")
        return self._candidate_row(existing)

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM shadow_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
        return None if row is None else self._candidate_row(row)

    def list_candidates(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM shadow_candidates ORDER BY created_at, id"
            ).fetchall()
        return [self._candidate_row(row) for row in rows]

    def page_candidates(
        self, *, principal: str, offset: int, limit: int
    ) -> dict[str, Any]:
        offset, limit = self._page_window(offset, limit)
        ownership = """FROM shadow_candidates AS candidate
                       JOIN shadow_evidence_sets AS evidence
                         ON evidence.id = candidate.evidence_set_id
                       WHERE evidence.principal = ?"""
        with self._connection() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) {ownership}", (principal,)
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""SELECT candidate.* {ownership}
                    ORDER BY candidate.created_at DESC, candidate.id DESC
                    LIMIT ? OFFSET ?""",
                (principal, limit, offset),
            ).fetchall()
        items = [self._candidate_row(row) for row in rows]
        return self._page_result(items, offset=offset, limit=limit, total=total)

    def get_evaluation_pair(self, payload: Mapping[str, object]) -> dict[str, Any] | None:
        pair_key_digest, _pair_digest = _evaluation_pair_identity(payload)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM shadow_evaluation_pairs WHERE pair_key_digest = ?",
                (pair_key_digest,),
            ).fetchone()
            return None if row is None else self._evaluation_pair_row(connection, row)

    def reserve_evaluation_pair(self, payload: Mapping[str, object]) -> dict[str, Any]:
        required = {
            "candidate_id",
            "evidence_set_id",
            "evidence_set_fingerprint",
            "in_sample_window",
            "out_of_sample_window",
            "adjustment_policy",
            "cost_policy",
            "splits",
        }
        if set(payload) != required:
            raise ShadowRepositoryError("evaluation pair schema is invalid")
        splits = payload["splits"]
        if not isinstance(splits, Mapping) or set(splits) != {
            "in_sample",
            "out_of_sample",
        }:
            raise ShadowRepositoryError("evaluation pair split identity is invalid")
        normalized_splits: dict[str, dict[str, object]] = {}
        for split_kind, window_key in (
            ("in_sample", "in_sample_window"),
            ("out_of_sample", "out_of_sample_window"),
        ):
            split = splits[split_kind]
            if not isinstance(split, Mapping) or set(split) != {
                "window",
                "governed_fingerprint",
                "artifact",
            }:
                raise ShadowRepositoryError("evaluation pair split identity is invalid")
            window = self._evaluation_window(split["window"])
            if window != self._evaluation_window(payload[window_key]):
                raise ShadowRepositoryError("evaluation pair window identity diverged")
            fingerprint = str(split["governed_fingerprint"])
            artifact = split["artifact"]
            if len(fingerprint) != 64 or not isinstance(artifact, Mapping):
                raise ShadowRepositoryError("evaluation pair frozen identity is invalid")
            normalized_splits[split_kind] = {
                "window": window,
                "governed_fingerprint": fingerprint,
                "artifact": dict(artifact),
            }
        normalized = {
            **payload,
            "in_sample_window": self._evaluation_window(payload["in_sample_window"]),
            "out_of_sample_window": self._evaluation_window(payload["out_of_sample_window"]),
            "cost_policy": dict(payload["cost_policy"])
            if isinstance(payload["cost_policy"], Mapping)
            else payload["cost_policy"],
            "splits": normalized_splits,
        }
        pair_key_digest, pair_digest = _evaluation_pair_identity(normalized)
        assert pair_digest is not None
        pair_id = uuid4().hex
        created = False
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            candidate = connection.execute(
                """SELECT evidence_set_id, evidence_set_fingerprint
                   FROM shadow_candidates WHERE id = ?""",
                (normalized["candidate_id"],),
            ).fetchone()
            evidence = connection.execute(
                "SELECT fingerprint FROM shadow_evidence_sets WHERE id = ?",
                (normalized["evidence_set_id"],),
            ).fetchone()
            if (
                candidate is None
                or evidence is None
                or candidate["evidence_set_id"] != normalized["evidence_set_id"]
                or candidate["evidence_set_fingerprint"] != evidence["fingerprint"]
                or normalized["evidence_set_fingerprint"] != evidence["fingerprint"]
            ):
                raise ShadowRepositoryError("evaluation pair candidate evidence is invalid")
            row = connection.execute(
                "SELECT * FROM shadow_evaluation_pairs WHERE pair_key_digest = ?",
                (pair_key_digest,),
            ).fetchone()
            if row is not None:
                if row["pair_digest"] != pair_digest:
                    raise ShadowRepositoryError(
                        "evaluation pair replay conflict: frozen identity diverged"
                    )
            else:
                created = True
                created_at = self.now()
                connection.execute(
                    """INSERT INTO shadow_evaluation_pairs
                       (id, pair_key_digest, pair_digest, candidate_id, evidence_set_id,
                        evidence_set_fingerprint, in_sample_window_json,
                        out_of_sample_window_json, adjustment_policy, cost_policy_json,
                        created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        pair_id,
                        pair_key_digest,
                        pair_digest,
                        normalized["candidate_id"],
                        normalized["evidence_set_id"],
                        normalized["evidence_set_fingerprint"],
                        _canonical_json(normalized["in_sample_window"], "in-sample window"),
                        _canonical_json(normalized["out_of_sample_window"], "out-of-sample window"),
                        normalized["adjustment_policy"],
                        _canonical_json(normalized["cost_policy"], "evaluation cost policy"),
                        created_at,
                    ),
                )
                for split_kind in ("in_sample", "out_of_sample"):
                    self._insert_evaluation_attempt(
                        connection,
                        pair_id=pair_id,
                        candidate_id=str(normalized["candidate_id"]),
                        evidence_set_id=str(normalized["evidence_set_id"]),
                        evidence_set_fingerprint=str(normalized["evidence_set_fingerprint"]),
                        split_kind=split_kind,
                        split=normalized_splits[split_kind],
                        adjustment_policy=str(normalized["adjustment_policy"]),
                        cost_policy=dict(normalized["cost_policy"]),
                        retry_of_evaluation_id=None,
                    )
                row = connection.execute(
                    "SELECT * FROM shadow_evaluation_pairs WHERE id = ?", (pair_id,)
                ).fetchone()
            if row is None:
                raise ShadowRepositoryError("reserved evaluation pair is unavailable")
            record = self._evaluation_pair_row(connection, row)
        record["created"] = created
        return record

    def reserve_evaluation_retry(self, *, pair_id: str, evaluation_id: str) -> dict[str, Any]:
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            pair = connection.execute(
                "SELECT * FROM shadow_evaluation_pairs WHERE id = ?", (pair_id,)
            ).fetchone()
            previous = self._evaluation_attempt(connection, evaluation_id)
            if pair is None or previous["pair_id"] != pair_id:
                raise ShadowRepositoryError("evaluation retry pair is invalid")
            if previous["status"] == "passed":
                raise ShadowRepositoryError("evaluation retry source is invalid")
            latest = connection.execute(
                """SELECT id FROM shadow_evaluation_attempts
                   WHERE pair_id = ? AND split_kind = ?
                   ORDER BY attempt DESC LIMIT 1""",
                (pair_id, previous["split_kind"]),
            ).fetchone()
            if latest is not None and latest["id"] != evaluation_id:
                return self._evaluation_attempt(connection, str(latest["id"]))
            return self._insert_evaluation_attempt(
                connection,
                pair_id=pair_id,
                candidate_id=str(previous["candidate_id"]),
                evidence_set_id=str(previous["evidence_set_id"]),
                evidence_set_fingerprint=str(previous["evidence_set_fingerprint"]),
                split_kind=str(previous["split_kind"]),
                split={
                    "window": previous["window"],
                    "governed_fingerprint": previous["governed_fingerprint"],
                    "artifact": previous["artifact"],
                },
                adjustment_policy=str(previous["adjustment_policy"]),
                cost_policy=dict(previous["cost_policy"]),
                retry_of_evaluation_id=evaluation_id,
            )

    def complete_evaluation(
        self, evaluation_id: str, terminal: dict[str, object]
    ) -> dict[str, Any]:
        """Append one terminal to its directly queryable reserved attempt."""
        status = terminal.get("status")
        status_to_db = {
            "passed": "passed",
            "failed": "failed",
            "failed_gate": "failed",
            "timeout": "timed_out",
            "resource_exhausted": "resource_limited",
            "interrupted": "interrupted",
        }
        status_to_public = {
            "passed": "passed",
            "failed": "failed",
            "failed_gate": "failed",
            "timeout": "timeout",
            "resource_exhausted": "resource_exhausted",
            "interrupted": "interrupted",
        }
        if status not in status_to_db or set(terminal) not in (
            {"status", "metrics"},
            {"status", "reason"},
        ):
            raise ShadowRepositoryError("evaluation terminal schema is invalid")
        metrics = terminal.get("metrics") if status == "passed" else {}
        if not isinstance(metrics, Mapping):
            raise ShadowRepositoryError("evaluation terminal metrics are invalid")
        reason = (
            None
            if status == "passed"
            else str(terminal.get("reason", "evaluation did not pass"))[:256]
        )
        incoming_terminal = (
            {"status": "passed", "metrics": dict(metrics)}
            if status == "passed"
            else {"status": status_to_public[str(status)], "reason": reason}
        )
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            attempt = self._evaluation_attempt(connection, evaluation_id)
            if attempt["status"] != "interrupted":
                persisted_terminal = (
                    {"status": "passed", "metrics": attempt["metrics"]}
                    if attempt["status"] == "passed"
                    else {"status": attempt["status"], "reason": attempt.get("reason")}
                )
                if _canonical_digest(
                    persisted_terminal, "persisted evaluation terminal"
                ) != _canonical_digest(incoming_terminal, "evaluation terminal"):
                    raise ShadowRepositoryError(
                        "evaluation terminal replay conflict: result diverged"
                    )
                return attempt
            connection.execute(
                """INSERT INTO shadow_candidate_evaluations
                   (id, candidate_id, run_id, split_kind, window_start, window_end,
                    governed_fingerprint, artifact_descriptor_json, metrics_json,
                    status, terminal_reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    evaluation_id,
                    attempt["candidate_id"],
                    attempt["run_id"],
                    attempt["split_kind"],
                    attempt["window"]["start"],
                    attempt["window"]["end"],
                    attempt["governed_fingerprint"],
                    _canonical_json(attempt["artifact"], "evaluation artifact"),
                    _canonical_json(dict(metrics), "evaluation metrics"),
                    status_to_db[str(status)],
                    reason,
                    self.now(),
                ),
            )
            return self._evaluation_attempt(connection, evaluation_id)

    def get_evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM shadow_evaluation_attempts WHERE id = ?",
                (evaluation_id,),
            ).fetchone()
            return None if exists is None else self._evaluation_attempt(connection, evaluation_id)

    def list_evaluations(self, *, candidate_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT id FROM shadow_evaluation_attempts"
        parameters: tuple[object, ...] = ()
        if candidate_id is not None:
            query += " WHERE candidate_id = ?"
            parameters = (candidate_id,)
        query += """ ORDER BY created_at,
                     CASE split_kind WHEN 'in_sample' THEN 0 ELSE 1 END,
                     attempt, id"""
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
            return [self._evaluation_attempt(connection, str(row["id"])) for row in rows]

    def page_evaluations(
        self,
        *,
        principal: str,
        candidate_id: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        offset, limit = self._page_window(offset, limit)
        ownership = """FROM shadow_evaluation_attempts AS attempt
                       JOIN shadow_candidates AS candidate ON candidate.id = attempt.candidate_id
                       JOIN shadow_evidence_sets AS evidence
                         ON evidence.id = candidate.evidence_set_id
                       WHERE evidence.principal = ?"""
        parameters: list[object] = [principal]
        if candidate_id is not None:
            ownership += " AND attempt.candidate_id = ?"
            parameters.append(candidate_id)
        with self._connection() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) {ownership}", parameters
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""SELECT attempt.id {ownership}
                    ORDER BY attempt.created_at DESC, attempt.id DESC
                    LIMIT ? OFFSET ?""",
                (*parameters, limit, offset),
            ).fetchall()
            items = [
                self._evaluation_attempt(connection, str(row["id"])) for row in rows
            ]
        return self._page_result(items, offset=offset, limit=limit, total=total)

    def append_retention_event(self, payload: dict[str, object]) -> dict[str, Any]:
        required = {
            "candidate_id",
            "evidence_set_id",
            "evidence_set_fingerprint",
            "in_sample_evaluation_id",
            "out_of_sample_evaluation_id",
            "reviewer_principal",
            "rationale",
        }
        if set(payload) != required:
            raise ShadowRepositoryError("retention event schema is invalid")
        reviewer = payload["reviewer_principal"]
        rationale = payload["rationale"]
        if (
            not isinstance(reviewer, str)
            or not reviewer.strip()
            or len(reviewer.strip()) > 128
            or not isinstance(rationale, str)
            or len(rationale.strip()) < 10
            or len(rationale.strip()) > 4_000
        ):
            raise ShadowRepositoryError("retention attributable decision is invalid")
        normalized = {
            **payload,
            "reviewer_principal": reviewer.strip(),
            "rationale": rationale.strip(),
        }
        candidate_id = str(normalized["candidate_id"])
        in_id = str(normalized["in_sample_evaluation_id"])
        out_id = str(normalized["out_of_sample_evaluation_id"])
        logical_digest, decision_digest = _retention_identity(normalized)
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            candidate = connection.execute(
                "SELECT * FROM shadow_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
            evidence = connection.execute(
                "SELECT * FROM shadow_evidence_sets WHERE id = ?",
                (normalized["evidence_set_id"],),
            ).fetchone()
            evaluation_ids = {
                str(row["id"])
                for row in connection.execute(
                    "SELECT id FROM shadow_evaluation_attempts WHERE id IN (?, ?)",
                    (in_id, out_id),
                ).fetchall()
            }
            in_sample = (
                self._evaluation_attempt(connection, in_id) if in_id in evaluation_ids else None
            )
            out_of_sample = (
                self._evaluation_attempt(connection, out_id) if out_id in evaluation_ids else None
            )
            if (
                candidate is None
                or evidence is None
                or candidate["evidence_set_id"] != evidence["id"]
                or candidate["evidence_set_fingerprint"] != evidence["fingerprint"]
                or normalized["evidence_set_fingerprint"] != evidence["fingerprint"]
                or not self._eligible_evaluation(in_sample, candidate_id, "in_sample")
                or not self._eligible_evaluation(out_of_sample, candidate_id, "out_of_sample")
                or in_sample.get("pair_id") is None
                or in_sample.get("pair_id") != out_of_sample.get("pair_id")
                or not self._ordered_evaluations(in_sample, out_of_sample)
            ):
                raise ShadowRepositoryError("retention requires canonical passing IS/OOS evidence")
            existing = connection.execute(
                """SELECT retention.*, candidate.evidence_set_id,
                          candidate.evidence_set_fingerprint
                   FROM shadow_retention_events AS retention
                   JOIN shadow_candidates AS candidate
                     ON candidate.id = retention.candidate_id
                   WHERE retention.candidate_id = ?
                     AND retention.in_sample_evaluation_id = ?
                     AND retention.out_of_sample_evaluation_id = ?""",
                (candidate_id, in_id, out_id),
            ).fetchone()
            identity = connection.execute(
                """SELECT decision_digest, retention_event_id
                   FROM shadow_retention_decision_identities
                   WHERE logical_key_digest = ?""",
                (logical_digest,),
            ).fetchone()
            if existing is not None:
                existing_payload = {key: existing[key] for key in required}
                persisted_digest = _retention_identity(existing_payload)[1]
                if persisted_digest != decision_digest or (
                    identity is not None
                    and (
                        identity["decision_digest"] != decision_digest
                        or identity["retention_event_id"] != existing["id"]
                    )
                ):
                    raise ShadowRepositoryError(
                        "retention replay conflict: canonical decision digest diverged"
                    )
                event_id = str(existing["id"])
                if identity is None:
                    connection.execute(
                        """INSERT INTO shadow_retention_decision_identities
                           (logical_key_digest, decision_digest, retention_event_id, created_at)
                           VALUES (?, ?, ?, ?)""",
                        (logical_digest, decision_digest, event_id, self.now()),
                    )
            else:
                if identity is not None:
                    raise ShadowRepositoryError(
                        "retention replay conflict: logical identity is inconsistent"
                    )
                event_id = uuid4().hex
                created_at = self.now()
                connection.execute(
                    """INSERT INTO shadow_retention_events
                       (id, candidate_id, in_sample_evaluation_id,
                        out_of_sample_evaluation_id, reviewer_principal, rationale,
                        status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, 'retained_research_only', ?)""",
                    (
                        event_id,
                        candidate_id,
                        in_id,
                        out_id,
                        normalized["reviewer_principal"],
                        normalized["rationale"],
                        created_at,
                    ),
                )
                connection.execute(
                    """INSERT INTO shadow_retention_decision_identities
                       (logical_key_digest, decision_digest, retention_event_id, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (logical_digest, decision_digest, event_id, created_at),
                )
        record = self.get_retention_event(event_id)
        if record is None:
            raise ShadowRepositoryError("persisted retention event is unavailable")
        return record

    def get_retention_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT retention.*, candidate.evidence_set_id,
                          candidate.evidence_set_fingerprint
                   FROM shadow_retention_events AS retention
                   JOIN shadow_candidates AS candidate ON candidate.id = retention.candidate_id
                   WHERE retention.id = ?""",
                (event_id,),
            ).fetchone()
        return None if row is None else dict(row)

    def list_retention_events(self, *, candidate_id: str | None = None) -> list[dict[str, Any]]:
        query = """SELECT retention.*, candidate.evidence_set_id,
                          candidate.evidence_set_fingerprint
                   FROM shadow_retention_events AS retention
                   JOIN shadow_candidates AS candidate ON candidate.id = retention.candidate_id"""
        parameters: tuple[object, ...] = ()
        if candidate_id is not None:
            query += " WHERE retention.candidate_id = ?"
            parameters = (candidate_id,)
        query += " ORDER BY retention.created_at, retention.id"
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def page_retention_events(
        self,
        *,
        principal: str,
        candidate_id: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        offset, limit = self._page_window(offset, limit)
        ownership = """FROM shadow_retention_events AS retention
                       JOIN shadow_candidates AS candidate ON candidate.id = retention.candidate_id
                       JOIN shadow_evidence_sets AS evidence
                         ON evidence.id = candidate.evidence_set_id
                       WHERE evidence.principal = ?"""
        parameters: list[object] = [principal]
        if candidate_id is not None:
            ownership += " AND retention.candidate_id = ?"
            parameters.append(candidate_id)
        with self._connection() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) {ownership}", parameters
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""SELECT retention.*, candidate.evidence_set_id,
                           candidate.evidence_set_fingerprint {ownership}
                    ORDER BY retention.created_at DESC, retention.id DESC
                    LIMIT ? OFFSET ?""",
                (*parameters, limit, offset),
            ).fetchall()
        items = [dict(row) for row in rows]
        return self._page_result(items, offset=offset, limit=limit, total=total)

    @staticmethod
    def _evaluation_window(value: object) -> dict[str, str]:
        if not isinstance(value, Mapping) or set(value) != {"start", "end"}:
            raise ShadowRepositoryError("evaluation window is invalid")
        try:
            start = date.fromisoformat(str(value["start"]))
            end = date.fromisoformat(str(value["end"]))
        except ValueError as error:
            raise ShadowRepositoryError("evaluation window is invalid") from error
        if start > end:
            raise ShadowRepositoryError("evaluation window is invalid")
        return {"start": start.isoformat(), "end": end.isoformat()}

    def _insert_evaluation_attempt(
        self,
        connection: sqlite3.Connection,
        *,
        pair_id: str,
        candidate_id: str,
        evidence_set_id: str,
        evidence_set_fingerprint: str,
        split_kind: str,
        split: Mapping[str, object],
        adjustment_policy: str,
        cost_policy: Mapping[str, object],
        retry_of_evaluation_id: str | None,
    ) -> dict[str, Any]:
        if split_kind not in {"in_sample", "out_of_sample"}:
            raise ShadowRepositoryError("evaluation split identity is invalid")
        window = self._evaluation_window(split.get("window"))
        fingerprint = str(split.get("governed_fingerprint"))
        artifact = split.get("artifact")
        if len(fingerprint) != 64 or not isinstance(artifact, Mapping):
            raise ShadowRepositoryError("evaluation frozen inputs are invalid")
        pair_attempt = int(
            connection.execute(
                """SELECT COALESCE(MAX(attempt), 0) + 1
                   FROM shadow_evaluation_attempts
                   WHERE pair_id = ? AND split_kind = ?""",
                (pair_id, split_kind),
            ).fetchone()[0]
        )
        run_attempt = int(
            connection.execute(
                """SELECT COALESCE(MAX(attempt), 0) + 1
                   FROM shadow_candidate_runs WHERE candidate_id = ?""",
                (candidate_id,),
            ).fetchone()[0]
        )
        evaluation_id = uuid4().hex
        run_id = uuid4().hex
        created_at = self.now()
        manifest = {
            "evaluation_id": evaluation_id,
            "pair_id": pair_id,
            "evidence_set_id": evidence_set_id,
            "evidence_set_fingerprint": evidence_set_fingerprint,
            "split_kind": split_kind,
            "window": window,
            "artifact": dict(artifact),
            "adjustment_policy": adjustment_policy,
            "cost_policy": dict(cost_policy),
            "retry_of_evaluation_id": retry_of_evaluation_id,
        }
        connection.execute(
            """INSERT INTO shadow_candidate_runs
               (id, candidate_id, attempt, governed_fingerprint, runner_manifest_json,
                status, terminal_reason, created_at)
               VALUES (?, ?, ?, ?, ?, 'interrupted', ?, ?)""",
            (
                run_id,
                candidate_id,
                run_attempt,
                fingerprint,
                _canonical_json(manifest, "evaluation attempt manifest"),
                "attempt boundary recorded before bounded evaluation",
                created_at,
            ),
        )
        connection.execute(
            """INSERT INTO shadow_evaluation_attempts
               (id, pair_id, run_id, candidate_id, split_kind, attempt,
                retry_of_evaluation_id, window_start, window_end,
                governed_fingerprint, artifact_descriptor_json, adjustment_policy,
                cost_policy_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evaluation_id,
                pair_id,
                run_id,
                candidate_id,
                split_kind,
                pair_attempt,
                retry_of_evaluation_id,
                window["start"],
                window["end"],
                fingerprint,
                _canonical_json(dict(artifact), "evaluation artifact"),
                adjustment_policy,
                _canonical_json(dict(cost_policy), "evaluation cost policy"),
                created_at,
            ),
        )
        return self._evaluation_attempt(connection, evaluation_id)

    @staticmethod
    def _evaluation_attempt(connection: sqlite3.Connection, evaluation_id: str) -> dict[str, Any]:
        row = connection.execute(
            """SELECT attempt.*,
                      pair.evidence_set_id AS pair_evidence_set_id,
                      pair.evidence_set_fingerprint AS pair_evidence_fingerprint,
                      run.runner_manifest_json,
                      evaluation.status AS terminal_status,
                      evaluation.metrics_json AS terminal_metrics_json,
                      evaluation.terminal_reason AS evaluation_terminal_reason
               FROM shadow_evaluation_attempts AS attempt
               JOIN shadow_candidate_runs AS run ON run.id = attempt.run_id
               LEFT JOIN shadow_evaluation_pairs AS pair ON pair.id = attempt.pair_id
               LEFT JOIN shadow_candidate_evaluations AS evaluation
                 ON evaluation.id = attempt.id
               WHERE attempt.id = ?""",
            (evaluation_id,),
        ).fetchone()
        if row is None:
            raise ShadowRepositoryError("evaluation attempt is unavailable")
        record = dict(row)
        manifest = _json_object(record.pop("runner_manifest_json"), "evaluation attempt manifest")
        artifact = _json_object(record.pop("artifact_descriptor_json"), "evaluation artifact")
        costs = _json_object(record.pop("cost_policy_json"), "evaluation cost policy")
        metrics_json = record.pop("terminal_metrics_json")
        terminal_status = record.pop("terminal_status")
        terminal_reason = record.pop("evaluation_terminal_reason")
        evidence_set_id = record.pop("pair_evidence_set_id") or manifest.get("evidence_set_id")
        evidence_fingerprint = record.pop("pair_evidence_fingerprint") or manifest.get(
            "evidence_set_fingerprint"
        )
        status_from_db = {
            "passed": "passed",
            "failed": "failed",
            "timed_out": "timeout",
            "resource_limited": "resource_exhausted",
            "interrupted": "interrupted",
        }
        public = {
            **record,
            "status": "interrupted"
            if terminal_status is None
            else status_from_db[str(terminal_status)],
            "evidence_set_id": evidence_set_id,
            "evidence_set_fingerprint": evidence_fingerprint,
            "window": {
                "start": record.pop("window_start"),
                "end": record.pop("window_end"),
            },
            "artifact": artifact,
            "cost_policy": costs,
        }
        if metrics_json is not None:
            metrics = _json_object(metrics_json, "evaluation metrics")
            if metrics:
                public["metrics"] = metrics
        if terminal_reason:
            public["reason"] = terminal_reason
        if public.get("retry_of_evaluation_id") is None:
            public.pop("retry_of_evaluation_id", None)
        if public.get("pair_id") is None:
            public.pop("pair_id", None)
        return public

    @classmethod
    def _evaluation_pair_row(
        cls, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> dict[str, Any]:
        record = dict(row)
        record["in_sample_window"] = _json_object(
            record.pop("in_sample_window_json"), "in-sample window"
        )
        record["out_of_sample_window"] = _json_object(
            record.pop("out_of_sample_window_json"), "out-of-sample window"
        )
        record["cost_policy"] = _json_object(
            record.pop("cost_policy_json"), "evaluation cost policy"
        )
        rows = connection.execute(
            """SELECT id FROM shadow_evaluation_attempts
               WHERE pair_id = ?
               ORDER BY CASE split_kind WHEN 'in_sample' THEN 0 ELSE 1 END,
                        attempt, id""",
            (record["id"],),
        ).fetchall()
        attempts = [cls._evaluation_attempt(connection, str(item["id"])) for item in rows]
        record["attempts"] = attempts
        for split_kind in ("in_sample", "out_of_sample"):
            matching = [attempt for attempt in attempts if attempt["split_kind"] == split_kind]
            if not matching:
                raise ShadowRepositoryError("evaluation pair attempt is unavailable")
            record[split_kind] = matching[-1]
        return record

    @staticmethod
    def _ordered_evaluations(
        in_sample: Mapping[str, object] | None,
        out_of_sample: Mapping[str, object] | None,
    ) -> bool:
        if in_sample is None or out_of_sample is None:
            return False
        in_window, out_window = in_sample.get("window"), out_of_sample.get("window")
        return bool(
            isinstance(in_window, Mapping)
            and isinstance(out_window, Mapping)
            and str(in_window.get("end", "")) < str(out_window.get("start", ""))
        )

    @staticmethod
    def _eligible_evaluation(
        evaluation: Mapping[str, object] | None,
        candidate_id: str,
        split_kind: str,
    ) -> bool:
        return bool(
            evaluation
            and evaluation.get("candidate_id") == candidate_id
            and evaluation.get("split_kind") == split_kind
            and evaluation.get("status") == "passed"
            and isinstance(evaluation.get("metrics"), Mapping)
        )

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
        normalized = _json_object(record.pop("normalized_payload_json"), "normalized payload")
        return {**record, "source_values": source_values, "normalized": normalized}

    @staticmethod
    def _candidate_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        parameters_record = _json_object(record.pop("parameters_json"), "candidate parameters")
        if set(parameters_record) != {
            "parameters",
            "negative_sampling",
            "canonical_rules_json",
            "rule_fingerprint",
            "training_replay",
        }:
            raise ShadowRepositoryError("persisted candidate parameters are invalid")
        rules = _json_list(record.pop("rules_json"), "candidate rules")
        features = _json_list(record.pop("features_json"), "candidate features")
        try:
            assumptions = validate_persisted_assumption_pair(
                exit_json=record.pop("exit_assumptions_json"),
                holding_json=record.pop("holding_assumptions_json"),
            )
        except ShadowAssumptionError as error:
            raise ShadowRepositoryError("persisted candidate assumptions are invalid") from error
        source_batch_ids = _json_list(record.pop("source_batch_ids_json"), "source batch ids")
        training_window = _json_object(record.pop("training_window_json"), "training window")
        class_balance = _json_object(record.pop("class_balance_json"), "class balance")
        metrics = _json_object(record.pop("metrics_json"), "candidate metrics")
        limitations = _json_list(record.pop("limitations_json"), "candidate limitations")
        return {
            **record,
            "rules": rules,
            "features": features,
            "parameters": parameters_record["parameters"],
            "exit_assumptions": assumptions.exit,
            "holding_assumptions": assumptions.holding,
            "source_batch_ids": source_batch_ids,
            "training_window": training_window,
            "class_balance": class_balance,
            "metrics": metrics,
            "limitations": limitations,
            "negative_sampling": parameters_record["negative_sampling"],
            "canonical_rules_json": parameters_record["canonical_rules_json"],
            "rule_fingerprint": parameters_record["rule_fingerprint"],
            "training_replay": parameters_record["training_replay"],
        }

    @staticmethod
    def _evidence_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        manifest = _json_object(record.pop("manifest_json"), "evidence manifest")
        return {**record, **manifest}
