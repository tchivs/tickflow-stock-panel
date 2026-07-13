"""SQLite repository for immutable research catalog records.

This repository shares the existing operational database file and its migration
sequence.  It owns only research tables; market time series remain in the lake.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
from typing import Any, Iterator, Mapping, Sequence

from app.operational.migrations import migrate_operational_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
