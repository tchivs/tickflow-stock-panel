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
        requested_trade_ids = self._unique_nonempty(included_trade_ids, "trade")
        exclusion_items = self._normalize_exclusions(exclusions)
        excluded_ids = [item["trade_id"] for item in exclusion_items]
        if set(requested_trade_ids) & set(excluded_ids):
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
        trade_ids = [
            str(row["id"])
            for row in all_trade_rows
            if str(row["id"]) in included_id_set
        ]
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

    def append_candidate(self, candidate: dict[str, object]) -> dict[str, Any]:
        """Persist only canonical data exported by the optional learner."""
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
        evidence = self.get_evidence_set(str(candidate["evidence_set_id"]))
        if (
            evidence is None
            or candidate["evidence_set_fingerprint"] != evidence["fingerprint"]
            or candidate["source_batch_ids"] != evidence["included_batch_ids"]
        ):
            raise ShadowRepositoryError("candidate evidence attribution is invalid")
        identifier = uuid4().hex
        parameters_record = {
            "parameters": candidate["parameters"],
            "negative_sampling": candidate["negative_sampling"],
            "canonical_rules_json": candidate["canonical_rules_json"],
            "rule_fingerprint": candidate["rule_fingerprint"],
            "training_replay": candidate["training_replay"],
        }
        with self._connection() as connection, connection:
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
            if existing is None:
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
                        _canonical_json(candidate["rules"], "candidate rules"),
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

    def append_evaluation_attempt(
        self, payload: dict[str, object]
    ) -> dict[str, Any]:
        """Reserve one immutable attempt before the bounded collaborator starts.

        The Phase 05 schema intentionally permits only terminal run facts.  The
        reservation is therefore an immutable ``interrupted`` run boundary; its
        separately appended evaluation row owns the eventual terminal result.
        A process interruption leaves the reservation as truthful terminal evidence.
        """
        required = {
            "candidate_id",
            "evidence_set_id",
            "evidence_set_fingerprint",
            "split_kind",
            "window",
            "governed_fingerprint",
            "artifact",
            "adjustment_policy",
            "cost_policy",
        }
        if set(payload) not in {required, required | {"retry_of_evaluation_id"}}:
            raise ShadowRepositoryError("evaluation attempt schema is invalid")
        candidate_id = str(payload["candidate_id"])
        evidence_set_id = str(payload["evidence_set_id"])
        split_kind = str(payload["split_kind"])
        fingerprint = str(payload["governed_fingerprint"])
        if split_kind not in {"in_sample", "out_of_sample"} or len(fingerprint) != 64:
            raise ShadowRepositoryError("evaluation split identity is invalid")
        window = payload["window"]
        if not isinstance(window, Mapping) or set(window) != {"start", "end"}:
            raise ShadowRepositoryError("evaluation window is invalid")
        try:
            start = date.fromisoformat(str(window["start"]))
            end = date.fromisoformat(str(window["end"]))
        except ValueError as error:
            raise ShadowRepositoryError("evaluation window is invalid") from error
        if start > end:
            raise ShadowRepositoryError("evaluation window is invalid")
        artifact = payload["artifact"]
        cost_policy = payload["cost_policy"]
        if not isinstance(artifact, Mapping) or not isinstance(cost_policy, Mapping):
            raise ShadowRepositoryError("evaluation frozen inputs are invalid")

        evaluation_id = uuid4().hex
        run_id = uuid4().hex
        manifest = {
            "evaluation_id": evaluation_id,
            "evidence_set_id": evidence_set_id,
            "evidence_set_fingerprint": payload["evidence_set_fingerprint"],
            "split_kind": split_kind,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "artifact": dict(artifact),
            "adjustment_policy": payload["adjustment_policy"],
            "cost_policy": dict(cost_policy),
            "retry_of_evaluation_id": payload.get("retry_of_evaluation_id"),
        }
        created_at = self.now()
        with self._connection() as connection, connection:
            candidate = connection.execute(
                "SELECT evidence_set_id, evidence_set_fingerprint FROM shadow_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            evidence = connection.execute(
                "SELECT fingerprint FROM shadow_evidence_sets WHERE id = ?",
                (evidence_set_id,),
            ).fetchone()
            if (
                candidate is None
                or evidence is None
                or candidate["evidence_set_id"] != evidence_set_id
                or candidate["evidence_set_fingerprint"] != evidence["fingerprint"]
                or payload["evidence_set_fingerprint"] != evidence["fingerprint"]
            ):
                raise ShadowRepositoryError("evaluation candidate evidence is invalid")
            retry_of = payload.get("retry_of_evaluation_id")
            if retry_of is not None:
                previous = connection.execute(
                    "SELECT status FROM shadow_candidate_evaluations WHERE id = ? AND candidate_id = ?",
                    (retry_of, candidate_id),
                ).fetchone()
                if previous is None or previous["status"] == "passed":
                    raise ShadowRepositoryError("evaluation retry source is invalid")
            attempt = int(
                connection.execute(
                    "SELECT COALESCE(MAX(attempt), 0) + 1 FROM shadow_candidate_runs WHERE candidate_id = ?",
                    (candidate_id,),
                ).fetchone()[0]
            )
            connection.execute(
                """INSERT INTO shadow_candidate_runs
                   (id, candidate_id, attempt, governed_fingerprint, runner_manifest_json,
                    status, terminal_reason, created_at)
                   VALUES (?, ?, ?, ?, ?, 'interrupted', ?, ?)""",
                (
                    run_id,
                    candidate_id,
                    attempt,
                    fingerprint,
                    _canonical_json(manifest, "evaluation attempt manifest"),
                    "attempt boundary recorded before bounded evaluation",
                    created_at,
                ),
            )
        return {
            "id": evaluation_id,
            "run_id": run_id,
            "status": "running",
            "created_at": created_at,
            **dict(payload),
        }

    def complete_evaluation(
        self, evaluation_id: str, terminal: dict[str, object]
    ) -> dict[str, Any]:
        """Append, never update, the terminal evaluation for a reserved attempt."""
        status = terminal.get("status")
        status_to_db = {
            "passed": "passed",
            "failed": "failed",
            "failed_gate": "failed",
            "timeout": "timed_out",
            "resource_exhausted": "resource_limited",
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
        reason = None if status == "passed" else str(terminal.get("reason", "evaluation did not pass"))[:256]
        with self._connection() as connection, connection:
            run_row, manifest = self._evaluation_attempt(connection, evaluation_id)
            existing = connection.execute(
                "SELECT 1 FROM shadow_candidate_evaluations WHERE id = ?", (evaluation_id,)
            ).fetchone()
            if existing is not None:
                raise ShadowRepositoryError("evaluation terminal fact already exists")
            window = manifest["window"]
            connection.execute(
                """INSERT INTO shadow_candidate_evaluations
                   (id, candidate_id, run_id, split_kind, window_start, window_end,
                    governed_fingerprint, artifact_descriptor_json, metrics_json,
                    status, terminal_reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    evaluation_id,
                    run_row["candidate_id"],
                    run_row["id"],
                    manifest["split_kind"],
                    window["start"],
                    window["end"],
                    run_row["governed_fingerprint"],
                    _canonical_json(manifest["artifact"], "evaluation artifact"),
                    _canonical_json(dict(metrics), "evaluation metrics"),
                    status_to_db[status],
                    reason,
                    self.now(),
                ),
            )
        record = self.get_evaluation(evaluation_id)
        if record is None:
            raise ShadowRepositoryError("persisted evaluation is unavailable")
        return record

    def get_evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT evaluation.*, run.runner_manifest_json
                   FROM shadow_candidate_evaluations AS evaluation
                   JOIN shadow_candidate_runs AS run ON run.id = evaluation.run_id
                   WHERE evaluation.id = ?""",
                (evaluation_id,),
            ).fetchone()
        return None if row is None else self._evaluation_row(row)

    def list_evaluations(
        self, *, candidate_id: str | None = None
    ) -> list[dict[str, Any]]:
        query = """SELECT evaluation.*, run.runner_manifest_json
                   FROM shadow_candidate_evaluations AS evaluation
                   JOIN shadow_candidate_runs AS run ON run.id = evaluation.run_id"""
        parameters: tuple[object, ...] = ()
        if candidate_id is not None:
            query += " WHERE evaluation.candidate_id = ?"
            parameters = (candidate_id,)
        query += " ORDER BY evaluation.created_at, evaluation.id"
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._evaluation_row(row) for row in rows]

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
        candidate_id = str(payload["candidate_id"])
        in_id = str(payload["in_sample_evaluation_id"])
        out_id = str(payload["out_of_sample_evaluation_id"])
        with self._connection() as connection, connection:
            candidate = connection.execute(
                "SELECT * FROM shadow_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
            evidence = connection.execute(
                "SELECT * FROM shadow_evidence_sets WHERE id = ?", (payload["evidence_set_id"],)
            ).fetchone()
            evaluations = connection.execute(
                """SELECT evaluation.*, run.runner_manifest_json
                   FROM shadow_candidate_evaluations AS evaluation
                   JOIN shadow_candidate_runs AS run ON run.id = evaluation.run_id
                   WHERE evaluation.id IN (?, ?)""",
                (in_id, out_id),
            ).fetchall()
            by_id = {str(row["id"]): self._evaluation_row(row) for row in evaluations}
            in_sample, out_of_sample = by_id.get(in_id), by_id.get(out_id)
            if (
                candidate is None
                or evidence is None
                or candidate["evidence_set_id"] != evidence["id"]
                or candidate["evidence_set_fingerprint"] != evidence["fingerprint"]
                or payload["evidence_set_fingerprint"] != evidence["fingerprint"]
                or not self._eligible_evaluation(in_sample, candidate_id, "in_sample")
                or not self._eligible_evaluation(out_of_sample, candidate_id, "out_of_sample")
                or not self._ordered_evaluations(in_sample, out_of_sample)
            ):
                raise ShadowRepositoryError("retention requires canonical passing IS/OOS evidence")
            existing = connection.execute(
                """SELECT id FROM shadow_retention_events
                   WHERE candidate_id = ? AND in_sample_evaluation_id = ?
                     AND out_of_sample_evaluation_id = ?""",
                (candidate_id, in_id, out_id),
            ).fetchone()
            if existing is None:
                event_id = uuid4().hex
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
                        payload["reviewer_principal"],
                        payload["rationale"],
                        self.now(),
                    ),
                )
            else:
                event_id = str(existing["id"])
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

    def list_retention_events(
        self, *, candidate_id: str | None = None
    ) -> list[dict[str, Any]]:
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

    @staticmethod
    def _evaluation_attempt(
        connection: sqlite3.Connection, evaluation_id: str
    ) -> tuple[sqlite3.Row, dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM shadow_candidate_runs ORDER BY created_at, id"
        ).fetchall()
        for row in rows:
            manifest = _json_object(row["runner_manifest_json"], "evaluation attempt manifest")
            if manifest.get("evaluation_id") == evaluation_id:
                return row, manifest
        raise ShadowRepositoryError("evaluation attempt is unavailable")

    @staticmethod
    def _evaluation_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        manifest = _json_object(
            record.pop("runner_manifest_json"), "evaluation attempt manifest"
        )
        artifact = _json_object(
            record.pop("artifact_descriptor_json"), "evaluation artifact"
        )
        metrics = _json_object(record.pop("metrics_json"), "evaluation metrics")
        status_from_db = {
            "passed": "passed",
            "failed": "failed",
            "timed_out": "timeout",
            "resource_limited": "resource_exhausted",
            "interrupted": "interrupted",
        }
        public = {
            **record,
            "status": status_from_db[str(record["status"])],
            "evidence_set_id": manifest["evidence_set_id"],
            "evidence_set_fingerprint": manifest["evidence_set_fingerprint"],
            "window": manifest["window"],
            "artifact": artifact,
            "adjustment_policy": manifest["adjustment_policy"],
            "cost_policy": manifest["cost_policy"],
        }
        retry_of = manifest.get("retry_of_evaluation_id")
        if retry_of is not None:
            public["retry_of_evaluation_id"] = retry_of
        if metrics:
            public["metrics"] = metrics
        if public.get("terminal_reason"):
            public["reason"] = public.pop("terminal_reason")
        else:
            public.pop("terminal_reason", None)
        return public

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
        normalized = _json_object(
            record.pop("normalized_payload_json"), "normalized payload"
        )
        return {**record, "source_values": source_values, "normalized": normalized}

    @staticmethod
    def _candidate_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        parameters_record = _json_object(
            record.pop("parameters_json"), "candidate parameters"
        )
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
        source_batch_ids = _json_list(
            record.pop("source_batch_ids_json"), "source batch ids"
        )
        training_window = _json_object(
            record.pop("training_window_json"), "training window"
        )
        class_balance = _json_object(
            record.pop("class_balance_json"), "class balance"
        )
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
