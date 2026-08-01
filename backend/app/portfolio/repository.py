"""SQLite repository for immutable portfolio optimization run records.

职责: 共享 operational.db 及其迁移序列, 持有 portfolio_optimization_runs
(PFOL-04) 的 append-only 访问面。本文件在 11-02 只建立数据库接缝与迁移接线;
append-only 写入/查询方法由 11-01 补齐。

不知道: 求解逻辑 (optimizer.py)、风险模型 (risk.py)、工件存储 (artifacts.py)、
市场时间序列 (留在 lake)。
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.operational.migrations import migrate_operational_db

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RUN_STATUSES = frozenset(
    {"optimal", "optimal_inaccurate", "infeasible", "unbounded", "solver_error", "failed"}
)
_OBJECTIVES = frozenset({"min_volatility", "hrp", "max_sharpe"})
_EXPECTED_RETURN_METHODS = frozenset({"composite-zscore-v1", "none"})
_RISK_MODELS = frozenset({"sample_covariance_v1"})


# 每个 run 的 immutable 事实用确定性 JSON 序列化 (排序键 + 紧凑分隔符), 与
# research/repository.py 的 _json 完全一致, 保证 checksum 跨模块可复现。
def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: object, field: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be JSON serializable") from error


def _record(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    """Un-wrap the JSON columns into their documented field names.

    Accepts either a sqlite3.Row (from a SELECT) or a plain dict (e.g. a row
    already materialized by list_optimization_runs).
    """
    if row is None:
        return None
    value = dict(row)
    for column, target in (
        ("risk_model_json", "risk_model"),
        ("constraint_stack_json", "constraint_stack"),
        ("solver_options_json", "solver_options"),
        ("output_weights_json", "output_weights"),
        ("baseline_weights_json", "baseline_weights"),
    ):
        if column in value and value[column] is not None:
            value[target] = json.loads(value.pop(column))
    return value


class PortfolioRepository:
    """Parameterized, short-lived SQLite access for immutable optimization runs."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        with self._connection() as connection:
            migrate_operational_db(connection)

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
        """Apply the shared operational migration sequence (idempotent)."""
        with self._connection() as connection:
            migrate_operational_db(connection)

    def record_optimization_run(self, **fields: Any) -> dict[str, Any]:
        """Append one immutable optimization run row (PFOL-04).

        Validates every sha256 field, the problem-status enum, and the
        failed-reason invariant before INSERT; JSON columns are canonicalized via
        ``_json`` so checksums are reproducible across modules. Returns the
        stored record with JSON columns un-wrapped (same shape as
        ``get_optimization_run``).
        """
        self._validate_run_fields(fields)
        columns = [
            "id",
            "objective",
            "as_of",
            "universe",
            "model_id",
            "composite_snapshot_id",
            "input_snapshot_sha256",
            "expected_return_method",
            "risk_model",
            "risk_model_json",
            "constraint_stack_json",
            "solver_name",
            "solver_version",
            "solver_options_json",
            "problem_status",
            "failure_reason",
            "output_weights_json",
            "output_sha256",
            "weights_artifact_relative_path",
            "baseline_weights_json",
            "created_at",
        ]
        # JSON 列先用确定性序列化 (排序键 + 紧凑分隔符) 压成 TEXT, 与 _record 展开对称。
        serialized = dict(fields)
        for column in (
            "risk_model_json",
            "constraint_stack_json",
            "solver_options_json",
            "output_weights_json",
            "baseline_weights_json",
        ):
            value = serialized.get(column)
            if value is not None:
                serialized[column] = _json(value, column)
        values = [serialized.get(column) for column in columns]
        with self._connection() as connection, connection:
            connection.execute(
                f"INSERT INTO portfolio_optimization_runs ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                values,
            )
            row = connection.execute(
                "SELECT * FROM portfolio_optimization_runs WHERE id = ?", (fields["id"],)
            ).fetchone()
        return _record(row)  # type: ignore[return-value]

    def get_optimization_run(self, run_id: str) -> dict[str, Any] | None:
        """Return one run by id with JSON columns un-wrapped."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM portfolio_optimization_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return _record(row)

    def list_optimization_runs(
        self, *, objective: str | None = None, as_of: str | None = None
    ) -> list[dict[str, Any]]:
        """List runs ordered by created_at, id; optional objective/as_of filters."""
        clauses: list[str] = []
        parameters: list[Any] = []
        if objective is not None:
            clauses.append("objective = ?")
            parameters.append(objective)
        if as_of is not None:
            clauses.append("as_of = ?")
            parameters.append(as_of)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM portfolio_optimization_runs{where} ORDER BY created_at, id",
                parameters,
            ).fetchall()
        records = [dict(row) for row in rows]
        return [unwrapped for unwrapped in (_record(record) for record in records) if unwrapped is not None]

    @staticmethod
    def _validate_run_fields(fields: dict[str, Any]) -> None:
        """Enforce PFOL-04 invariants before any INSERT (fail fast, clear message)."""
        required = {
            "id",
            "objective",
            "as_of",
            "universe",
            "input_snapshot_sha256",
            "expected_return_method",
            "risk_model",
            "risk_model_json",
            "constraint_stack_json",
            "solver_name",
            "solver_version",
            "solver_options_json",
            "problem_status",
            "created_at",
        }
        missing = sorted(required - set(fields))
        if missing:
            raise ValueError(f"missing required run fields: {', '.join(missing)}")

        objective = fields["objective"]
        if objective not in _OBJECTIVES:
            raise ValueError(f"unknown objective: {objective}")
        method = fields["expected_return_method"]
        if method not in _EXPECTED_RETURN_METHODS:
            raise ValueError(f"unknown expected_return_method: {method}")
        risk_model = fields["risk_model"]
        if risk_model not in _RISK_MODELS:
            raise ValueError(f"unknown risk_model: {risk_model}")
        status = fields["problem_status"]
        if status not in _RUN_STATUSES:
            raise ValueError(f"unknown problem_status: {status}")

        for column in ("input_snapshot_sha256", "output_sha256"):
            value = fields.get(column)
            if value is not None and not _SHA256.fullmatch(str(value)):
                raise ValueError(f"{column} must be a lowercase SHA-256 hex digest")

        # failed / solver_error ⇔ failure_reason 不变量 (DB CHECK 镜像, 失败信息更友好)。
        failure_reason = fields.get("failure_reason")
        if status in {"failed", "solver_error"} and not failure_reason:
            raise ValueError("failure_reason is required when problem_status is failed or solver_error")
        if status not in {"failed", "solver_error"} and failure_reason is not None:
            raise ValueError("failure_reason must be NULL unless problem_status is failed or solver_error")

        # model_id 不变量: composite-zscore-v1 必须携带 model_id (仓库层强制)。
        if method == "composite-zscore-v1" and not fields.get("model_id"):
            raise ValueError("model_id is required when expected_return_method is composite-zscore-v1")
