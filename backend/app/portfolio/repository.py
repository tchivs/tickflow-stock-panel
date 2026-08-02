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
_RISK_MODELS = frozenset(
    {"sample_covariance_v1", "semi_covariance_v1", "ewma_covariance_v1", "ledoit_wolf_v1"}
)
# 12-02 option-a: runs 表 CHECK 已加宽到 4 模型枚举; 证据表使用同一枚举。
_RISK_MODELS_PHASE12 = _RISK_MODELS
_ATTRIBUTION_TYPES = frozenset({"exposure_contribution", "drawdown"})


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
        ("risk_model_json", "risk_model_detail"),
        ("constraint_stack_json", "constraint_stack"),
        ("solver_options_json", "solver_options"),
        ("output_weights_json", "output_weights"),
        ("baseline_weights_json", "baseline_weights"),
    ):
        if column in value and value[column] is not None:
            value[target] = json.loads(value.pop(column))
    return value


def _record_evidence(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    """Un-wrap an attribution-evidence row: reconciliation_json → reconciliation.

    The mirror of ``_record`` for portfolio_risk_attribution_evidence rows.
    """
    if row is None:
        return None
    value = dict(row)
    if value.get("reconciliation_json") is not None:
        value["reconciliation"] = json.loads(value.pop("reconciliation_json"))
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
        self,
        *,
        objective: str | None = None,
        as_of: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """List runs ordered by created_at, id; optional objective/as_of filters.

        Phase 15 API 面: limit 上限 (默认 200) 防止无界读取; objective / as_of
        为可选等式过滤。JSON 列经 _record 展开, 与 get_optimization_run 同构。

        Args:
            objective: 只返回该 objective 的 run (如 "min_volatility")。
            as_of: 只返回该 as_of 日期的 run (ISO 字符串)。
            limit: 返回行数上限 (默认 200; 必须为正整数)。

        Returns:
            按 created_at, id 升序排列的 run 记录列表 (JSON 列已展开)。
        """
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
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
                f"SELECT * FROM portfolio_optimization_runs{where} ORDER BY created_at, id LIMIT ?",
                [*parameters, limit],
            ).fetchall()
        records = [dict(row) for row in rows]
        return [
            unwrapped
            for unwrapped in (_record(record) for record in records)
            if unwrapped is not None
        ]

    def record_attribution_evidence(self, **fields: Any) -> dict[str, Any]:
        """Append one immutable attribution/drawdown evidence row (RSK-01/03).

        镜像 record_optimization_run: 校验 attribution_type / risk_model 枚举、
        output_sha256 64-hex、以及 (attribution_type == "exposure_contribution") ==
        (reconciliation_json is not None) 不变量 (DB CHECK 镜像, 失败信息更友好);
        reconciliation_json 经 _json 规范化后 INSERT。返回记录时 reconciliation_json
        展开为 reconciliation。无 UPDATE/DELETE 面 (表触发器强制 append-only)。
        """
        required = {
            "id",
            "attribution_type",
            "run_id",
            "risk_model",
            "as_of",
            "output_sha256",
            "artifact_relative_path",
            "reconciliation_json",
            "created_at",
        }
        missing = sorted(required - set(fields))
        if missing:
            raise ValueError(f"missing required evidence fields: {', '.join(missing)}")

        attribution_type = fields["attribution_type"]
        if attribution_type not in _ATTRIBUTION_TYPES:
            raise ValueError(f"unknown attribution_type: {attribution_type}")
        risk_model = fields["risk_model"]
        if risk_model not in _RISK_MODELS_PHASE12:
            raise ValueError(f"unknown risk_model: {risk_model}")
        if not _SHA256.fullmatch(str(fields["output_sha256"])):
            raise ValueError("output_sha256 must be a lowercase SHA-256 hex digest")
        # DB NOT NULL 镜像: 每个分析事实都携带 reconciliation_json (exposure 的
        # 对账载荷 + drawdown 的 period_count/max_depth)。缺省 fail closed。
        reconciliation = fields.get("reconciliation_json")
        if reconciliation is None:
            raise ValueError("reconciliation_json is required for every evidence row")

        columns = [
            "id",
            "attribution_type",
            "run_id",
            "risk_model",
            "as_of",
            "output_sha256",
            "artifact_relative_path",
            "reconciliation_json",
            "created_at",
        ]
        serialized = dict(fields)
        if reconciliation is not None:
            serialized["reconciliation_json"] = _json(reconciliation, "reconciliation_json")
        values = [serialized.get(column) for column in columns]
        with self._connection() as connection, connection:
            connection.execute(
                f"INSERT INTO portfolio_risk_attribution_evidence ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' * len(columns))})",
                values,
            )
            row = connection.execute(
                "SELECT * FROM portfolio_risk_attribution_evidence WHERE id = ?",
                (fields["id"],),
            ).fetchone()
        return _record_evidence(row)  # type: ignore[return-value]

    def get_attribution_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        """Return one evidence row by id with reconciliation_json unwrapped."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM portfolio_risk_attribution_evidence WHERE id = ?",
                (evidence_id,),
            ).fetchone()
        return _record_evidence(row)

    def list_attribution_evidence(
        self,
        *,
        run_id: str | None = None,
        attribution_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """List evidence rows ordered by created_at, id with optional filters.

        Args:
            run_id: 只返回该 run 的证据行。
            attribution_type: 只返回该类型 (exposure_contribution / drawdown)。
            limit: 行数上限 (默认 200; 必须为正整数, 否则 fail closed)。
        """
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if attribution_type is not None and attribution_type not in _ATTRIBUTION_TYPES:
            raise ValueError(f"unknown attribution_type: {attribution_type}")
        clauses: list[str] = []
        parameters: list[Any] = []
        if run_id is not None:
            clauses.append("run_id = ?")
            parameters.append(run_id)
        if attribution_type is not None:
            clauses.append("attribution_type = ?")
            parameters.append(attribution_type)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM portfolio_risk_attribution_evidence{where} "
                "ORDER BY created_at, id LIMIT ?",
                [*parameters, limit],
            ).fetchall()
        records = [dict(row) for row in rows]
        return [
            unwrapped
            for unwrapped in (_record_evidence(record) for record in records)
            if unwrapped is not None
        ]

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
            raise ValueError(
                "failure_reason is required when problem_status is failed or solver_error"
            )
        if status not in {"failed", "solver_error"} and failure_reason is not None:
            raise ValueError(
                "failure_reason must be NULL unless problem_status is failed or solver_error"
            )

        # model_id 不变量: composite-zscore-v1 必须携带 model_id (仓库层强制)。
        if method == "composite-zscore-v1" and not fields.get("model_id"):
            raise ValueError(
                "model_id is required when expected_return_method is composite-zscore-v1"
            )
