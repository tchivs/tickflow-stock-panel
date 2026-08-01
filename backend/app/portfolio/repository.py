"""SQLite repository for immutable portfolio optimization run records.

职责: 共享 operational.db 及其迁移序列, 持有 portfolio_optimization_runs
(PFOL-04) 的 append-only 访问面。本文件在 11-02 只建立数据库接缝与迁移接线;
append-only 写入/查询方法由 11-01 补齐。

不知道: 求解逻辑 (optimizer.py)、风险模型 (risk.py)、工件存储 (artifacts.py)、
市场时间序列 (留在 lake)。
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.operational.migrations import migrate_operational_db


# 每个 run 的 immutable 事实用确定性 JSON 序列化 (排序键 + 紧凑分隔符), 与
# research/repository.py 的 _json 完全一致, 保证 checksum 跨模块可复现。
def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: object, field: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be JSON serializable") from error


def _record(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Un-wrap the JSON columns into their documented field names."""
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
