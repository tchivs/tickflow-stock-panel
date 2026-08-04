"""SQLite repository for immutable research catalog records.

This repository shares the existing operational database file and its migration
sequence.  It owns only research tables; market time series remain in the lake.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from app.operational.migrations import migrate_operational_db


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: object, field: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be JSON serializable") from error


def _record(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    value = dict(row)
    for column, target in (
        ("fields_json", "fields"),
        ("operators_json", "operators"),
        ("functions_json", "functions"),
        ("provenance_json", "provenance"),
    ):
        if column in value:
            value[target] = json.loads(value.pop(column))
    return value


def _unpack_json(row: sqlite3.Row | None, columns: Mapping[str, str]) -> dict[str, Any] | None:
    """Convert a row to a dict, decoding the named ``*_json`` columns."""
    if row is None:
        return None
    value = dict(row)
    for column, target in columns.items():
        if column in value:
            value[target] = json.loads(value.pop(column))
    return value


def _wf_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _as_iso(value: object) -> str:
    """Normalize a ``date``/``datetime``/ISO string to an ISO date string."""
    if isinstance(value, str):
        return value
    iso = value.isoformat()
    return iso[:10] if len(iso) > 10 else iso


class ResearchRepository:
    """Parameterized, short-lived SQLite access for immutable research metadata."""

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

    def create_factor_with_revision(
        self,
        *,
        factor_id: str,
        revision_id: str,
        name: str,
        description: str,
        hypothesis: str,
        canonical_expression: str,
        dsl_version: str,
        ast_signature: str,
        shape_signature: str,
        fields: frozenset[str],
        operators: frozenset[str],
        functions: frozenset[str],
        provenance: Mapping[str, Any],
    ) -> dict[str, Any]:
        now = _now()
        with self._connection() as connection, connection:
            connection.execute(
                "INSERT INTO research_factor_definitions (id, created_at) VALUES (?, ?)",
                (factor_id, now),
            )
            self._insert_revision(
                connection,
                factor_id=factor_id,
                revision_id=revision_id,
                revision_number=1,
                name=name,
                description=description,
                hypothesis=hypothesis,
                canonical_expression=canonical_expression,
                dsl_version=dsl_version,
                ast_signature=ast_signature,
                shape_signature=shape_signature,
                fields=fields,
                operators=operators,
                functions=functions,
                provenance=provenance,
                created_at=now,
            )
            row = self._revision_row(connection, revision_id)
        assert row is not None
        return row

    def append_factor_revision(
        self,
        *,
        factor_id: str,
        revision_id: str,
        name: str,
        description: str,
        hypothesis: str,
        canonical_expression: str,
        dsl_version: str,
        ast_signature: str,
        shape_signature: str,
        fields: frozenset[str],
        operators: frozenset[str],
        functions: frozenset[str],
        provenance: Mapping[str, Any],
    ) -> dict[str, Any]:
        now = _now()
        with self._connection() as connection, connection:
            latest = connection.execute(
                "SELECT COALESCE(MAX(revision_number), 0) FROM research_factor_revisions WHERE factor_id = ?",
                (factor_id,),
            ).fetchone()
            if latest is None or int(latest[0]) == 0:
                raise ValueError("factor definition does not exist")
            self._insert_revision(
                connection,
                factor_id=factor_id,
                revision_id=revision_id,
                revision_number=int(latest[0]) + 1,
                name=name,
                description=description,
                hypothesis=hypothesis,
                canonical_expression=canonical_expression,
                dsl_version=dsl_version,
                ast_signature=ast_signature,
                shape_signature=shape_signature,
                fields=fields,
                operators=operators,
                functions=functions,
                provenance=provenance,
                created_at=now,
            )
            row = self._revision_row(connection, revision_id)
        assert row is not None
        return row

    def _insert_revision(
        self,
        connection: sqlite3.Connection,
        *,
        factor_id: str,
        revision_id: str,
        revision_number: int,
        name: str,
        description: str,
        hypothesis: str,
        canonical_expression: str,
        dsl_version: str,
        ast_signature: str,
        shape_signature: str,
        fields: frozenset[str],
        operators: frozenset[str],
        functions: frozenset[str],
        provenance: Mapping[str, Any],
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO research_factor_revisions (
                   id, factor_id, revision_number, name, description, hypothesis,
                   canonical_expression, dsl_version, ast_signature, shape_signature,
                   fields_json, operators_json, functions_json, provenance_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                revision_id, factor_id, revision_number, name, description, hypothesis,
                canonical_expression, dsl_version, ast_signature, shape_signature,
                _json(sorted(fields), "factor fields"), _json(sorted(operators), "factor operators"),
                _json(sorted(functions), "factor functions"), _json(dict(provenance), "factor provenance"), created_at,
            ),
        )

    def _revision_row(self, connection: sqlite3.Connection, revision_id: str) -> dict[str, Any] | None:
        return _record(connection.execute("SELECT * FROM research_factor_revisions WHERE id = ?", (revision_id,)).fetchone())

    def get_revision(self, revision_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._revision_row(connection, revision_id)
    def get_strategy_asset_binding(self, strategy_id: str) -> dict[str, Any] | None:
        """Return a binding only while its immutable revision exists."""
        with self._connection() as connection:
            row = connection.execute(
                """SELECT binding.strategy_id, binding.research_asset_id,
                          binding.provenance_json, binding.created_at
                   FROM research_strategy_asset_bindings AS binding
                   JOIN research_factor_revisions AS revision ON revision.id = binding.research_asset_id
                   WHERE binding.strategy_id = ?""",
                (strategy_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["provenance"] = json.loads(record.pop("provenance_json"))
        return record

    def resolve_bound_strategy(self, research_asset_id: str) -> dict[str, str] | None:
        """Resolve exactly one extant installed strategy for an immutable research asset."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT binding.strategy_id, binding.research_asset_id, revision.id AS revision
                   FROM research_strategy_asset_bindings AS binding
                   JOIN research_factor_revisions AS revision ON revision.id = binding.research_asset_id
                   WHERE binding.research_asset_id = ?""",
                (research_asset_id,),
            ).fetchall()
        if len(rows) != 1:
            return None
        row = rows[0]
        strategy_id = row["strategy_id"]
        asset_id = row["research_asset_id"]
        revision = row["revision"]
        if not all(isinstance(value, str) and value for value in (strategy_id, asset_id, revision)):
            return None
        return {"strategy_id": strategy_id, "research_asset_id": asset_id, "revision": revision}

    def bind_strategy_asset(
        self, *, strategy_id: str, research_asset_id: str, provenance: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Create exactly one immutable lifecycle binding or fail closed on conflict."""
        existing = self.get_strategy_asset_binding(strategy_id)
        if existing is not None:
            if existing["research_asset_id"] != research_asset_id or existing["provenance"] != dict(provenance):
                raise ValueError("strategy research asset binding conflicts with persisted lifecycle binding")
            return existing
        with self._connection() as connection, connection:
            try:
                connection.execute(
                    """INSERT INTO research_strategy_asset_bindings
                       (strategy_id, research_asset_id, provenance_json, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (strategy_id, research_asset_id, _json(dict(provenance), "binding provenance"), _now()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("strategy research asset binding conflicts with persisted lifecycle binding") from error
        binding = self.get_strategy_asset_binding(strategy_id)
        if binding is None:
            raise ValueError("strategy research asset binding is unavailable")
        return binding

    def get_current_revision(self, factor_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT * FROM research_factor_revisions
                   WHERE factor_id = ? ORDER BY revision_number DESC LIMIT 1""",
                (factor_id,),
            ).fetchone()
            return _record(row)

    def list_revisions(self, factor_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM research_factor_revisions WHERE factor_id = ? ORDER BY revision_number",
                (factor_id,),
            ).fetchall()
        return [_record(row) for row in rows]  # type: ignore[list-item]

    def list_current_revisions(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT revisions.* FROM research_factor_revisions AS revisions
                   JOIN (
                       SELECT factor_id, MAX(revision_number) AS revision_number
                       FROM research_factor_revisions GROUP BY factor_id
                   ) AS current
                   ON current.factor_id = revisions.factor_id
                   AND current.revision_number = revisions.revision_number
                   ORDER BY revisions.name COLLATE NOCASE, revisions.factor_id, revisions.id"""
            ).fetchall()
        return [_record(row) for row in rows]  # type: ignore[list-item]

    def create_experiment(
        self,
        *,
        experiment_id: str,
        originating_run_id: str,
        status: str,
        validated: bool,
        factor_revision_id: str | None,
        strategy_id: str | None,
        strategy_version: str | None,
        resolved_config: Mapping[str, Any],
        input_manifest: Mapping[str, Any],
        prediction_signals: Mapping[str, Any],
        metrics: Mapping[str, Any],
        artifacts: Sequence[Mapping[str, Any]],
        diagnostics: Mapping[str, Any],
        model_provenance: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Atomically insert a complete immutable experiment snapshot."""
        if not isinstance(validated, bool):
            raise ValueError("validated must be a boolean")
        self._validate_artifacts(originating_run_id, artifacts)
        now = _now()
        with self._connection() as connection, connection:
            try:
                connection.execute(
                    """INSERT INTO research_experiments (
                           id, factor_revision_id, strategy_id, strategy_version, originating_run_id,
                           status, validated, retained_at, resolved_config_json, input_manifest_json,
                           prediction_signal_json, diagnostics_json, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)""",
                    (
                        experiment_id,
                        factor_revision_id,
                        strategy_id,
                        strategy_version,
                        originating_run_id,
                        status,
                        int(validated),
                        _json(dict(resolved_config), "resolved configuration"),
                        _json(dict(input_manifest), "input manifest"),
                        _json(dict(prediction_signals), "prediction and signal metadata"),
                        _json(dict(diagnostics), "diagnostics"),
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                if "originating_run_id" in str(error):
                    raise ValueError("an experiment already exists for this immutable run ID") from error
                raise
            connection.execute(
                """INSERT INTO research_experiment_metrics (experiment_id, metric_json, created_at)
                   VALUES (?, ?, ?)""",
                (experiment_id, _json(dict(metrics), "metrics"), now),
            )
            for artifact in artifacts:
                connection.execute(
                    """INSERT INTO research_experiment_artifacts (
                           experiment_id, relative_path, content_type, byte_size, checksum_sha256, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        experiment_id,
                        artifact["relative_path"],
                        artifact["content_type"],
                        artifact["byte_size"],
                        artifact["checksum_sha256"],
                        artifact["created_at"],
                    ),
                )
            if model_provenance is not None:
                connection.execute(
                    """INSERT INTO research_experiment_model_provenance (
                           experiment_id, provider, model, model_version, provenance_json, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        experiment_id,
                        model_provenance["provider"],
                        model_provenance["model"],
                        model_provenance.get("model_version"),
                        _json(dict(model_provenance["provenance"]), "model provenance"),
                        now,
                    ),
                )
            record = self._experiment_row(connection, experiment_id)
        assert record is not None
        return record

    @staticmethod
    def _validate_artifacts(originating_run_id: str, artifacts: Sequence[Mapping[str, Any]]) -> None:
        if not isinstance(originating_run_id, str) or not originating_run_id:
            raise ValueError("originating_run_id is required")
        seen_paths: set[str] = set()
        checksum = re.compile(r"[0-9a-f]{64}\Z")
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                raise ValueError("artifact descriptor must be a mapping")
            if artifact.get("evaluation_run_id") != originating_run_id:
                raise ValueError("artifact descriptor must be bound to its originating run ID")
            relative_path = artifact.get("relative_path")
            if not isinstance(relative_path, str) or not relative_path:
                raise ValueError("artifact relative_path is required")
            path = PurePosixPath(relative_path)
            if path.is_absolute() or "\\" in relative_path or path.parts[:2] != ("research_artifacts", originating_run_id) or len(path.parts) < 3:
                raise ValueError("artifact path must be a managed relative path bound to its originating run ID")
            if any(part in {".", ".."} for part in path.parts) or path.as_posix() != relative_path:
                raise ValueError("artifact path must not escape the managed artifact directory")
            if relative_path in seen_paths:
                raise ValueError("artifact paths must be unique within an experiment")
            seen_paths.add(relative_path)
            if not isinstance(artifact.get("content_type"), str) or not artifact["content_type"].strip():
                raise ValueError("artifact content_type is required")
            byte_size = artifact.get("byte_size")
            if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size < 0:
                raise ValueError("artifact byte_size must be a non-negative integer")
            if not isinstance(artifact.get("checksum_sha256"), str) or not checksum.fullmatch(artifact["checksum_sha256"]):
                raise ValueError("artifact checksum_sha256 must be a lowercase SHA-256 hex digest")
            if not isinstance(artifact.get("created_at"), str) or not artifact["created_at"].strip():
                raise ValueError("artifact created_at is required")

    def _experiment_row(self, connection: sqlite3.Connection, experiment_id: str) -> dict[str, Any] | None:
        row = connection.execute("SELECT * FROM research_experiments WHERE id = ?", (experiment_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        for column, target in (
            ("resolved_config_json", "resolved_config"),
            ("input_manifest_json", "input_manifest"),
            ("prediction_signal_json", "prediction_signals"),
            ("diagnostics_json", "diagnostics"),
        ):
            record[target] = json.loads(record.pop(column))
        metric_rows = connection.execute(
            "SELECT metric_json FROM research_experiment_metrics WHERE experiment_id = ? ORDER BY id", (experiment_id,)
        ).fetchall()
        metrics: dict[str, Any] = {}
        for metric in metric_rows:
            payload = json.loads(metric["metric_json"])
            if not isinstance(payload, dict):
                raise RuntimeError("stored experiment metrics are malformed")
            metrics.update(payload)
        record["metrics"] = metrics
        artifact_rows = connection.execute(
            """SELECT relative_path, content_type, byte_size, checksum_sha256, created_at
               FROM research_experiment_artifacts WHERE experiment_id = ? ORDER BY id""",
            (experiment_id,),
        ).fetchall()
        record["artifacts"] = [
            {"evaluation_run_id": record["originating_run_id"], **dict(artifact)} for artifact in artifact_rows
        ]
        model = connection.execute(
            """SELECT provider, model, model_version, provenance_json
               FROM research_experiment_model_provenance WHERE experiment_id = ?""",
            (experiment_id,),
        ).fetchone()
        record["model_provenance"] = None if model is None else {
            "provider": model["provider"],
            "model": model["model"],
            "model_version": model["model_version"],
            "provenance": json.loads(model["provenance_json"]),
        }
        record["validated"] = bool(record["validated"])
        return record

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._experiment_row(connection, experiment_id)
    def list_experiments(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id FROM research_experiments ORDER BY created_at DESC, id DESC"
            ).fetchall()
            return [self._experiment_row(connection, row["id"]) for row in rows]  # type: ignore[list-item]

    def retain_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Set retention once for a completed validated snapshot, never update it afterward."""
        with self._connection() as connection, connection:
            record = self._experiment_row(connection, experiment_id)
            if record is None:
                raise ValueError("experiment does not exist")
            if record["status"] != "completed" or not record["validated"]:
                raise ValueError("only completed validated experiments can be retained")
            if record["retained_at"] is not None:
                raise ValueError("experiment has already been retained")
            retained_at = _now()
            updated = connection.execute(
                "UPDATE research_experiments SET retained_at = ? WHERE id = ? AND retained_at IS NULL",
                (retained_at, experiment_id),
            ).rowcount
            if updated != 1:
                raise RuntimeError("experiment retention was modified concurrently")
            retained = self._experiment_row(connection, experiment_id)
        assert retained is not None
        return retained

    def list_comparison_candidates(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT id FROM research_experiments
                   WHERE status = 'completed' AND validated = 1 AND retained_at IS NOT NULL
                   ORDER BY retained_at, created_at, id"""
            ).fetchall()
            return [self._experiment_row(connection, row["id"]) for row in rows]  # type: ignore[list-item]

    # ------------------------------------------------------------------
    # Phase 10 append-only tables (PIT universe + admission + composite).
    # Every insert below follows the repository's append-only convention:
    # canonical JSON serialization, transactional writes, and no UPDATE/DELETE
    # paths (the migration enforces immutability triggers at the SQL level).
    # ------------------------------------------------------------------

    def insert_universe_membership(
        self,
        *,
        universe_name: str,
        symbol: str,
        asset_type: str,
        effective_date: str,
        state: str,
        source: str,
        provenance_json: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Append one PIT membership event. A delist is a new row, never an UPDATE."""
        if state not in {"listed", "delisted"}:
            raise ValueError("membership state must be listed or delisted")
        if asset_type not in {"stock", "etf"}:
            raise ValueError("asset_type must be stock or etf")
        membership_id = uuid.uuid4().hex
        now = _now()
        with self._connection() as connection, connection:
            try:
                connection.execute(
                    """INSERT INTO factor_universe_membership (
                           id, universe_name, symbol, asset_type, effective_date,
                           state, source, provenance_json, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        membership_id,
                        universe_name,
                        symbol,
                        asset_type,
                        effective_date,
                        state,
                        source,
                        _json(dict(provenance_json), "membership provenance"),
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("universe membership row conflicts with a persisted event") from error
            row = connection.execute(
                "SELECT * FROM factor_universe_membership WHERE id = ?", (membership_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("universe membership row was not persisted")
        record = dict(row)
        record["provenance"] = json.loads(record.pop("provenance_json"))
        return record

    def resolve_universe_memberships(
        self, *, universe_name: str, as_of: str, asset_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Latest membership event per symbol with ``effective_date <= as_of``.

        A symbol is a member when its latest event is ``listed``; a delist event
        closes membership as-of without deleting the earlier row (append-only).
        When a symbol has listed AND delisted events on the same
        ``effective_date`` (the schema permits different states on one date),
        the row with the latest ``created_at`` wins the tie-break so the as-of
        resolution is deterministic (IN-04).
        """
        query = (
            """SELECT membership.* FROM factor_universe_membership AS membership
               JOIN (
                   SELECT symbol, MAX(effective_date) AS effective_date,
                          MAX(created_at) AS latest_created_at
                   FROM factor_universe_membership
                   WHERE universe_name = ? AND effective_date <= ?
                   GROUP BY symbol
               ) AS latest
                 ON latest.symbol = membership.symbol
                AND latest.effective_date = membership.effective_date
                AND latest.latest_created_at = membership.created_at
               WHERE membership.universe_name = ? AND membership.effective_date <= ?"""
        )
        parameters: list[object] = [universe_name, as_of, universe_name, as_of]
        if asset_type is not None:
            query += " AND membership.asset_type = ?"
            parameters.append(asset_type)
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["provenance"] = json.loads(record.pop("provenance_json"))
            records.append(record)
        return records

    def list_universe_memberships(
        self, *, universe_name: str, asset_type: str | None = None
    ) -> list[dict[str, Any]]:
        """All membership events for a universe (the append-only history).

        Ordered by symbol then effective date so interval construction in the
        resolver is deterministic.  Delist events are rows in this history, never
        updates to an earlier row.
        """
        query = "SELECT * FROM factor_universe_membership WHERE universe_name = ?"
        parameters: list[object] = [universe_name]
        if asset_type is not None:
            query += " AND asset_type = ?"
            parameters.append(asset_type)
        query += " ORDER BY symbol, effective_date"
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["provenance"] = json.loads(record.pop("provenance_json"))
            records.append(record)
        return records

    def insert_admission_verdict(
        self,
        *,
        revision_id: str,
        policy_version: str,
        verdict: str,
        reason: str,
        gates_json: Sequence[Mapping[str, Any]],
        candidate_trail_json: Mapping[str, Any],
        resolved_universe_json: Mapping[str, Any],
        input_snapshot_sha256: str,
    ) -> dict[str, Any]:
        """Append one immutable admission verdict (admission or rejection)."""
        if verdict not in {"admitted", "rejected"}:
            raise ValueError("verdict must be admitted or rejected")
        if not re.fullmatch(r"[0-9a-f]{64}", input_snapshot_sha256):
            raise ValueError("input_snapshot_sha256 must be a lowercase SHA-256 hex digest")
        verdict_id = uuid.uuid4().hex
        now = _now()
        with self._connection() as connection, connection:
            try:
                connection.execute(
                    """INSERT INTO factor_admission_verdicts (
                           id, revision_id, policy_version, verdict, reason, gates_json,
                           candidate_trail_json, resolved_universe_json,
                           input_snapshot_sha256, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        verdict_id,
                        revision_id,
                        policy_version,
                        verdict,
                        reason,
                        _json(list(gates_json), "admission gates"),
                        _json(dict(candidate_trail_json), "admission candidate trail"),
                        _json(dict(resolved_universe_json), "resolved universe"),
                        input_snapshot_sha256,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError(
                    "an admission verdict already exists for this revision and policy"
                ) from error
            row = connection.execute(
                "SELECT * FROM factor_admission_verdicts WHERE id = ?", (verdict_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("admission verdict was not persisted")
        record = dict(row)
        record["gates"] = json.loads(record.pop("gates_json"))
        record["candidate_trail"] = json.loads(record.pop("candidate_trail_json"))
        record["resolved_universe"] = json.loads(record.pop("resolved_universe_json"))
        return record

    def get_admission_verdict(self, revision_id: str, policy_version: str) -> dict[str, Any] | None:
        """Return the persisted verdict for a (revision, policy) pair, if any."""
        with self._connection() as connection:
            row = connection.execute(
                """SELECT * FROM factor_admission_verdicts
                   WHERE revision_id = ? AND policy_version = ?""",
                (revision_id, policy_version),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["gates"] = json.loads(record.pop("gates_json"))
        record["candidate_trail"] = json.loads(record.pop("candidate_trail_json"))
        record["resolved_universe"] = json.loads(record.pop("resolved_universe_json"))
        return record

    def insert_model_definition(
        self,
        *,
        model_id: str,
        name: str,
        weighting: str,
        revision_ids: Sequence[str],
        weights: Mapping[str, float],
        input_snapshot_sha256: str,
    ) -> dict[str, Any]:
        """Append one immutable composite-model definition."""
        if weighting not in {"equal", "ic_weighted"}:
            raise ValueError("weighting must be equal or ic_weighted")
        if not re.fullmatch(r"[0-9a-f]{64}", input_snapshot_sha256):
            raise ValueError("input_snapshot_sha256 must be a lowercase SHA-256 hex digest")
        now = _now()
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO factor_model_models (
                       model_id, name, weighting, revision_ids_json, weights_json,
                       input_snapshot_sha256, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        model_id,
                        name,
                        weighting,
                        _json(sorted(revision_ids), "model revision ids"),
                        _json(dict(weights), "model weights"),
                        input_snapshot_sha256,
                        now,
                    ),
            )
            row = connection.execute(
                "SELECT * FROM factor_model_models WHERE model_id = ?", (model_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("model definition was not persisted")
        record = dict(row)
        record["revision_ids"] = json.loads(record.pop("revision_ids_json"))
        record["weights"] = json.loads(record.pop("weights_json"))
        return record

    def get_model_definition(self, model_id: str) -> dict[str, Any] | None:
        """Return the persisted composite-model definition, if any."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM factor_model_models WHERE model_id = ?", (model_id,)
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["revision_ids"] = json.loads(record.pop("revision_ids_json"))
        record["weights"] = json.loads(record.pop("weights_json"))
        return record

    def list_model_definitions(self) -> list[dict[str, Any]]:
        """All composite model definitions, ordered by name then model_id."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM factor_model_models
                   ORDER BY name COLLATE NOCASE, model_id"""
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["revision_ids"] = json.loads(record.pop("revision_ids_json"))
            record["weights"] = json.loads(record.pop("weights_json"))
            results.append(record)
        return results

    def insert_model_composite(
        self,
        *,
        model_id: str,
        output_sha256: str,
        artifact_relative_path: str,
        input_snapshot_sha256: str,
    ) -> dict[str, Any]:
        """Append one immutable composite output row (one per computation)."""
        for field, value in (("output_sha256", output_sha256), ("input_snapshot_sha256", input_snapshot_sha256)):
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
        composite_id = uuid.uuid4().hex
        now = _now()
        with self._connection() as connection, connection:
            try:
                connection.execute(
                    """INSERT INTO factor_model_composites (
                           id, model_id, output_sha256, artifact_relative_path,
                           input_snapshot_sha256, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        composite_id,
                        model_id,
                        output_sha256,
                        artifact_relative_path,
                        input_snapshot_sha256,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("model composite references a missing model definition") from error
            row = connection.execute(
                "SELECT * FROM factor_model_composites WHERE id = ?", (composite_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("model composite row was not persisted")
        return dict(row)

    def list_model_composites(self, model_id: str) -> list[dict[str, Any]]:
        """All immutable composite outputs for a model, oldest first."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM factor_model_composites
                   WHERE model_id = ? ORDER BY created_at, id""",
                (model_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # =====================================================================
    # Phase 13 walk-forward records (WFWD-01/02/03) — append-only.
    # Every row is INSERT-only; the migration enforces immutability triggers
    # at the SQL level. The exactly-once OOS contract maps sqlite3
    # IntegrityError to ValueError mirroring create_experiment (L338-341).
    # =====================================================================

    def create_wf_plan(self, plan: object) -> dict[str, Any]:
        """Pin a walk-forward plan (OOS reservation) or return the existing row.

        Append-only idempotent: a re-insert of the same plan_id returns the
        already-recorded row via the query path — never an error. This is the
        ``oos_pinned_at`` reservation recorded BEFORE any search reuse.

        WR-03: 幂等重创建前比较几何 — 同一 plan_id 以重测日历 / 不同 geometry 再钉时
        抛出 ValueError (绝不静默保留陈旧 OOS 预约)。几何以 (train_size, gap_size,
        test_size, oos_size, horizon, start, end, trading_dates, fold_geometry)
        的规范化序列判定。
        """
        plan_id = plan.plan_id
        trading_dates = _json(
            [_as_iso(day) for day in plan.trading_dates], "trading dates"
        )
        fold_geometry = _json(
            {
                "folds": [
                    {
                        "fold_index": fold.fold_index,
                        "is_oos": fold.is_oos,
                        "train_start": _as_iso(fold.train_start),
                        "train_end": _as_iso(fold.train_end),
                        "gap_start": _as_iso(fold.gap_start),
                        "gap_end": _as_iso(fold.gap_end),
                        "test_start": _as_iso(fold.test_start),
                        "test_end": _as_iso(fold.test_end),
                    }
                    for fold in plan.folds
                ],
                "oos_fold": {
                    "fold_index": plan.oos_fold.fold_index,
                    "is_oos": True,
                    "train_start": _as_iso(plan.oos_fold.train_start),
                    "train_end": _as_iso(plan.oos_fold.train_end),
                    "gap_start": _as_iso(plan.oos_fold.gap_start),
                    "gap_end": _as_iso(plan.oos_fold.gap_end),
                    "test_start": _as_iso(plan.oos_fold.test_start),
                    "test_end": _as_iso(plan.oos_fold.test_end),
                },
            },
            "fold geometry",
        )
        now = _now()
        with self._connection() as connection, connection:
            try:
                connection.execute(
                    """INSERT INTO wf_plans (
                           id, universe, asset_type, start, end, train_size, gap_size,
                           test_size, oos_size, horizon, trading_dates_json,
                           fold_geometry_json, oos_pinned_at, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        plan_id,
                        plan.universe,
                        plan.asset_type,
                        _as_iso(plan.start),
                        _as_iso(plan.end),
                        plan.train_size,
                        plan.gap_size,
                        plan.test_size,
                        plan.oos_size,
                        plan.horizon,
                        trading_dates,
                        fold_geometry,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                # Idempotent re-create: same plan_id already pinned. WR-03: 先比较
                # 几何 — 重测日历/改几何必须以 ValueError 暴露, 绝不静默保留陈旧预约。
                stored = connection.execute(
                    "SELECT * FROM wf_plans WHERE id = ?", (plan_id,)
                ).fetchone()
                if stored is None:
                    raise
                incoming_geometry = (
                    _as_iso(plan.start),
                    _as_iso(plan.end),
                    int(plan.train_size),
                    int(plan.gap_size),
                    int(plan.test_size),
                    int(plan.oos_size),
                    int(plan.horizon),
                    trading_dates,
                    fold_geometry,
                )
                stored_geometry = (
                    stored["start"],
                    stored["end"],
                    stored["train_size"],
                    stored["gap_size"],
                    stored["test_size"],
                    stored["oos_size"],
                    stored["horizon"],
                    stored["trading_dates_json"],
                    stored["fold_geometry_json"],
                )
                if incoming_geometry != stored_geometry:
                    raise ValueError(
                        "walk-forward plan already pinned with different geometry: "
                        f"plan_id={plan_id} (re-measure the calendar or use a new plan_id)"
                    ) from None
            row = connection.execute("SELECT * FROM wf_plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise RuntimeError("walk-forward plan was not persisted")
        return _unpack_json(
            row,
            {"trading_dates_json": "trading_dates", "fold_geometry_json": "fold_geometry"},
        )  # type: ignore[return-value]

    def get_wf_plan(self, plan_id: str) -> dict[str, Any] | None:
        """Return the pinned walk-forward plan with JSON unwrapped.

        Read surface for the Phase 15 panel and Phase 14 handoff:
        ``trading_dates_json`` / ``fold_geometry_json`` decode into
        ``trading_dates`` / ``fold_geometry``.
        """
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM wf_plans WHERE id = ?", (plan_id,)).fetchone()
        return _unpack_json(
            row,
            {"trading_dates_json": "trading_dates", "fold_geometry_json": "fold_geometry"},
        )

    def list_wf_plans(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """All pinned walk-forward plans, newest first, capped at limit.

        Read breadth (13-05): the Phase 15 panel lists every pinned plan (each
        carries its OOS reservation in ``oos_pinned_at``); ``limit`` must be a
        positive integer (limit=0 raises ValueError)."""
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM wf_plans ORDER BY created_at DESC, id LIMIT ?", (limit,)
            ).fetchall()
        return [
            _unpack_json(
                row,
                {"trading_dates_json": "trading_dates", "fold_geometry_json": "fold_geometry"},
            )
            for row in rows
        ]  # type: ignore[list-item]

    def record_wf_fold(self, **fields: Any) -> dict[str, Any]:
        """Append one fold manifest (search fold OR the reserved OOS).

        The ``UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)``
        constraint makes the OOS exactly-once: a second evaluation of the same
        (plan, strategy, params) raises ValueError (mirroring L338-341).
        """
        fold_id = fields.get("id") or uuid.uuid4().hex
        _wf_sha256(fields["params_sha256"], "params_sha256")
        _wf_sha256(fields["membership_fingerprint"], "membership_fingerprint")
        now = _now()
        with self._connection() as connection, connection:
            try:
                connection.execute(
                    """INSERT INTO wf_folds (
                           id, plan_id, fold_index, is_oos, strategy_id, params_sha256,
                           train_start, train_end, test_start, test_end,
                           membership_fingerprint, chain_config_json, stats_json, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        fold_id,
                        fields["plan_id"],
                        int(fields["fold_index"]),
                        int(bool(fields["is_oos"])),
                        fields["strategy_id"],
                        fields["params_sha256"],
                        _as_iso(fields["train_start"]),
                        _as_iso(fields["train_end"]),
                        _as_iso(fields["test_start"]),
                        _as_iso(fields["test_end"]),
                        fields["membership_fingerprint"],
                        _json(dict(fields.get("chain_config") or {}), "chain config"),
                        _json(dict(fields.get("stats") or {}), "fold stats"),
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                # IN-02: 只把真正的 UNIQUE 违反映射为 "OOS segment already evaluated";
                # FK (缺 plan) / CHECK 失败保留原始错误, 不再误报。
                message = str(error)
                is_unique_violation = "UNIQUE constraint failed" in message
                if fields.get("is_oos"):
                    if is_unique_violation:
                        raise ValueError("OOS segment already evaluated") from error
                    raise ValueError(
                        f"OOS fold row rejected by the database: {message}"
                    ) from error
                if is_unique_violation:
                    raise ValueError("fold row conflicts with a persisted fold manifest") from error
                raise ValueError(f"fold row rejected by the database: {message}") from error
            row = connection.execute("SELECT * FROM wf_folds WHERE id = ?", (fold_id,)).fetchone()
        if row is None:
            raise RuntimeError("walk-forward fold was not persisted")
        return _unpack_json(
            row,
            {"chain_config_json": "chain_config", "stats_json": "stats"},
        )  # type: ignore[return-value]

    def list_wf_folds(
        self, *, plan_id: str | None = None, is_oos: bool | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        """All fold manifests, ordered by plan_id then fold_index, capped at limit.

        Read breadth (13-05): filters by ``plan_id`` / ``is_oos``, unwraps
        ``chain_config_json`` / ``stats_json``, and fails closed on a non-
        positive ``limit`` (limit=0 raises ValueError)."""
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        clauses: list[str] = []
        parameters: list[Any] = []
        if plan_id is not None:
            clauses.append("plan_id = ?")
            parameters.append(plan_id)
        if is_oos is not None:
            clauses.append("is_oos = ?")
            parameters.append(int(is_oos))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"""SELECT * FROM wf_folds{where}
                   ORDER BY plan_id, fold_index, id LIMIT ?""",
                (*parameters, limit),
            ).fetchall()
        return [
            _unpack_json(
                row,
                {"chain_config_json": "chain_config", "stats_json": "stats"},
            )
            for row in rows
        ]  # type: ignore[list-item]

    def record_wf_search(self, **fields: Any) -> dict[str, Any]:
        """Append one OOS-scored search run with multiple-comparison bookkeeping.

        Fails closed with ValueError unless ``oos_excluded == 1`` — the search
        must never touch the reserved OOS (WFWD-02).
        """
        if not fields.get("oos_excluded"):
            raise ValueError("walk-forward search must exclude the reserved OOS (oos_excluded=1)")
        search_id = fields.get("id") or uuid.uuid4().hex
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO wf_search_runs (
                       id, plan_id, strategy_id, objective, direction, search_space_json,
                       n_trials, n_completed, score_distribution_json, best_params_json,
                       best_score, oos_excluded, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    search_id,
                    fields["plan_id"],
                    fields["strategy_id"],
                    fields["objective"],
                    fields["direction"],
                    _json(dict(fields.get("search_space") or {}), "search space"),
                    int(fields["n_trials"]),
                    int(fields["n_completed"]),
                    _json(dict(fields.get("score_distribution") or {}), "score distribution"),
                    _json(dict(fields.get("best_params") or {}), "best params"),
                    fields.get("best_score"),
                    1,
                    _now(),
                ),
            )
            row = connection.execute("SELECT * FROM wf_search_runs WHERE id = ?", (search_id,)).fetchone()
        if row is None:
            raise RuntimeError("walk-forward search run was not persisted")
        return _unpack_json(
            row,
            {
                "search_space_json": "search_space",
                "score_distribution_json": "score_distribution",
                "best_params_json": "best_params",
            },
        )  # type: ignore[return-value]

    def list_wf_search_runs(
        self,
        *,
        plan_id: str | None = None,
        strategy_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """All OOS-scored search runs, newest first, capped at limit.

        Read breadth (13-05): the Phase 15 panel lists every search run per
        plan/strategy with the multiple-comparison bookkeeping
        (search_space / score_distribution / best_params unwrapped);
        ``limit`` must be a positive integer (limit=0 raises ValueError)."""
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        clauses: list[str] = []
        parameters: list[Any] = []
        if plan_id is not None:
            clauses.append("plan_id = ?")
            parameters.append(plan_id)
        if strategy_id is not None:
            clauses.append("strategy_id = ?")
            parameters.append(strategy_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"""SELECT * FROM wf_search_runs{where}
                   ORDER BY created_at DESC, id LIMIT ?""",
                (*parameters, limit),
            ).fetchall()
        return [
            _unpack_json(
                row,
                {
                    "search_space_json": "search_space",
                    "score_distribution_json": "score_distribution",
                    "best_params_json": "best_params",
                },
            )
            for row in rows
        ]  # type: ignore[list-item]

    def record_validated_strategy(self, **fields: Any) -> dict[str, Any]:
        """Append one validation verdict tied to the once-evaluated OOS.

        ``oos_evidence_fold_id`` is UNIQUE — one OOS evaluation per
        strategy/params, the unbiased estimate (WFWD-02).
        """
        _wf_sha256(fields["params_sha256"], "params_sha256")
        verdict_id = fields.get("id") or uuid.uuid4().hex
        resolved_asset_ids = fields.get("resolved_asset_ids", [])
        with self._connection() as connection, connection:
            try:
                connection.execute(
                    """INSERT INTO wf_validated_strategies (
                           id, strategy_id, plan_id, search_run_id, params_sha256,
                           oos_evidence_fold_id, resolved_asset_ids_json, validation_score,
                           fold_evidence_json, passed_gate, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        verdict_id,
                        fields["strategy_id"],
                        fields["plan_id"],
                        fields.get("search_run_id"),
                        fields["params_sha256"],
                        fields["oos_evidence_fold_id"],
                        _json(list(resolved_asset_ids), "resolved asset ids"),
                        float(fields["validation_score"]),
                        _json(dict(fields.get("fold_evidence") or {}), "fold evidence"),
                        int(bool(fields["passed_gate"])),
                        _now(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                message = str(error)
                # WR-10: search_run_id FK 违反 (引用不存在的搜索) 应报出缺失的搜索运行,
                # 而非误导性的 "verdict conflicts" 消息。
                if "FOREIGN KEY constraint failed" in message and fields.get("search_run_id"):
                    raise ValueError(
                        "validation verdict references an unknown search run: "
                        f"search_run_id={fields['search_run_id']!r} "
                        "(persist the search via WalkForwardOptimizer(repo=...) first)"
                    ) from error
                raise ValueError("validation verdict conflicts with a persisted OOS evidence fold") from error
            row = connection.execute(
                "SELECT * FROM wf_validated_strategies WHERE id = ?", (verdict_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("validation verdict was not persisted")
        return _unpack_json(
            row,
            {
                "resolved_asset_ids_json": "resolved_asset_ids",
                "fold_evidence_json": "fold_evidence",
            },
        )  # type: ignore[return-value]

    def list_validated_strategies(
        self,
        *,
        strategy_id: str | None = None,
        plan_id: str | None = None,
        passed_gate: bool | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Validation verdicts, filtered and capped at limit.

        Read breadth (13-05): the ``passed_gate`` filter is what the ensemble
        gate (13-04) and the Phase 15 panel both filter on; every row carries
        ``resolved_asset_ids`` (unwrapped from the 13-02 DDL column
        ``resolved_asset_ids_json``) so Phase 14 binds the composite snapshot
        without re-resolving."""
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        clauses: list[str] = []
        parameters: list[Any] = []
        if strategy_id is not None:
            clauses.append("strategy_id = ?")
            parameters.append(strategy_id)
        if plan_id is not None:
            clauses.append("plan_id = ?")
            parameters.append(plan_id)
        if passed_gate is not None:
            clauses.append("passed_gate = ?")
            parameters.append(int(passed_gate))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"""SELECT * FROM wf_validated_strategies{where}
                   ORDER BY created_at, id LIMIT ?""",
                (*parameters, limit),
            ).fetchall()
        return [
            _unpack_json(
                row,
                {
                    "resolved_asset_ids_json": "resolved_asset_ids",
                    "fold_evidence_json": "fold_evidence",
                },
            )
            for row in rows
        ]  # type: ignore[list-item]

    def record_wf_ensemble(self, **fields: Any) -> dict[str, Any]:
        """Append one ensemble output bound to a checksum-verified artifact."""
        _wf_sha256(fields["input_snapshot_sha256"], "input_snapshot_sha256")
        _wf_sha256(fields["output_sha256"], "output_sha256")
        ensemble_id = fields.get("id") or uuid.uuid4().hex
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO wf_ensembles (
                       id, name, strategy_ids_json, weights_json,
                       validation_record_ids_json, input_snapshot_sha256, output_sha256,
                       artifact_relative_path, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ensemble_id,
                        fields["name"],
                        _json(sorted(fields["strategy_ids"]), "strategy ids"),
                        _json(dict(fields["weights"]), "weights"),
                        _json(sorted(fields["validation_record_ids"]), "validation record ids"),
                        fields["input_snapshot_sha256"],
                        fields["output_sha256"],
                        fields["artifact_relative_path"],
                        _now(),
                    ),
            )
            row = connection.execute("SELECT * FROM wf_ensembles WHERE id = ?", (ensemble_id,)).fetchone()
        if row is None:
            raise RuntimeError("walk-forward ensemble was not persisted")
        return _unpack_json(
            row,
            {
                "strategy_ids_json": "strategy_ids",
                "weights_json": "weights",
                "validation_record_ids_json": "validation_record_ids",
            },
        )  # type: ignore[return-value]

    def list_wf_ensembles(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """All ensemble outputs, newest first, capped at limit."""
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM wf_ensembles ORDER BY created_at DESC, id LIMIT ?", (limit,)
            ).fetchall()
        return [
            _unpack_json(
                row,
                {
                    "strategy_ids_json": "strategy_ids",
                    "weights_json": "weights",
                    "validation_record_ids_json": "validation_record_ids",
                },
            )
            for row in rows
        ]  # type: ignore[list-item]
