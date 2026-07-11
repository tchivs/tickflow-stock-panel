"""SQLite repository for immutable research catalog records.

This repository shares the existing operational database file and its migration
sequence.  It owns only research tables; market time series remain in the lake.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping

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
