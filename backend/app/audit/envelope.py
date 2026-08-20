"""Phase 52 AUDIT-01: ToolCallEnvelope — 统一工具调用审计记录。

每次 Provider/AI/通知/外部工具调用追加一条不可变记录:
  tool / params_hash / version / scope / response_shape / raw_hash / duration_ms / error

审计只追加事实, 不改变确定性代码对生成/评估/门禁/晋级的所有权。
脱敏: 密钥、完整报文与个人数据不出后端; API 只暴露 raw_hash 与脱敏摘要。
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── 脱敏白名单: params 中允许明文展示的字段名 ──────────────────────
_SAFE_PARAM_KEYS: frozenset[str] = frozenset({
    "model", "temperature", "max_tokens", "timeout", "provider", "base_url",
    "symbol", "symbols", "start", "end", "asset_type", "dataset", "dataset_type",
    "channel", "channel_type", "rule_id", "rule_name", "monitor_id",
    "limit", "offset", "page", "page_size",
})

# 敏感 key 模式: 出现即脱敏
_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"key", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"auth", re.IGNORECASE),
    re.compile(r"cookie", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"api_key", re.IGNORECASE),
)


def _is_sensitive_key(key: str) -> bool:
    return any(p.search(key) for p in _SENSITIVE_PATTERNS)


def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """脱敏 params: 敏感字段值替换为 '***', 只保留白名单字段的原始值。"""
    if not params or not isinstance(params, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in params.items():
        if _is_sensitive_key(key):
            sanitized[key] = "***"
        elif key in _SAFE_PARAM_KEYS:
            sanitized[key] = value
        elif isinstance(value, (str, int, float, bool)):
            # 非敏感标量保留, 但截断长字符串
            if isinstance(value, str) and len(value) > 200:
                sanitized[key] = value[:200] + "..."
            else:
                sanitized[key] = value
        elif isinstance(value, (list, dict)):
            # 非敏感容器只记类型和长度
            sanitized[key] = f"<{type(value).__name__}:len={len(value)}>"
        else:
            sanitized[key] = "***"
    return sanitized


def _compute_hash(raw: str | bytes | None) -> str | None:
    """计算 raw payload 的 SHA-256 hash; None → None。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _params_hash(params: dict[str, Any] | None) -> str:
    """对 params 做稳定哈希 (排序后 JSON 序列化)。"""
    if not params:
        return hashlib.sha256(b"{}").hexdigest()
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ToolCallEnvelope:
    """一条不可变工具调用审计记录。"""

    id: str
    seq: int
    tool: str
    category: str  # provider / ai / notification / external
    params_hash: str
    params_summary: dict[str, Any] = field(default_factory=dict)
    version: str | None = None
    scope: str | None = None
    principal: str | None = None
    response_shape: str | None = None
    response_summary: str | None = None
    raw_hash: str | None = None
    duration_ms: float = 0.0
    error: str | None = None
    cached: bool = False
    degraded: bool = False
    schema_valid: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """API 友好的 dict 表示 (脱敏后)。"""
        return {
            "id": self.id,
            "seq": self.seq,
            "tool": self.tool,
            "category": self.category,
            "params_hash": self.params_hash,
            "params_summary": self.params_summary,
            "version": self.version,
            "scope": self.scope,
            "principal": self.principal,
            "response_shape": self.response_shape,
            "response_summary": self.response_summary,
            "raw_hash": self.raw_hash,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "cached": self.cached,
            "degraded": self.degraded,
            "schema_valid": self.schema_valid,
            "created_at": self.created_at,
        }


class ToolCallAuditRepository:
    """ToolCallEnvelope 的 append-only repository。"""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def _next_seq(self) -> int:
        row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM tool_call_envelopes").fetchone()
        return int(row[0]) if row else 1

    def append(
        self,
        *,
        tool: str,
        category: str,
        params: dict[str, Any] | None = None,
        version: str | None = None,
        scope: str | None = None,
        principal: str | None = None,
        response_shape: str | None = None,
        response_summary: str | None = None,
        raw: str | bytes | None = None,
        duration_ms: float = 0.0,
        error: str | None = None,
        cached: bool = False,
        degraded: bool = False,
        schema_valid: bool = True,
    ) -> ToolCallEnvelope:
        """追加一条审计记录。Raw payload 不入库, 只存 hash + 脱敏摘要。"""
        envelope_id = secrets.token_hex(12)
        seq = self._next_seq()
        env = ToolCallEnvelope(
            id=envelope_id,
            seq=seq,
            tool=tool,
            category=category,
            params_hash=_params_hash(params),
            params_summary=_sanitize_params(params),
            version=version,
            scope=scope,
            principal=principal,
            response_shape=response_shape,
            response_summary=response_summary,
            raw_hash=_compute_hash(raw),
            duration_ms=round(duration_ms, 3),
            error=error,
            cached=cached,
            degraded=degraded,
            schema_valid=schema_valid,
            created_at=_now_iso(),
        )
        self._conn.execute(
            """
            INSERT INTO tool_call_envelopes
                (id, seq, tool, category, params_hash, params_summary, version, scope,
                 principal, response_shape, response_summary, raw_hash, duration_ms,
                 error, cached, degraded, schema_valid, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                env.id, env.seq, env.tool, env.category, env.params_hash,
                json.dumps(env.params_summary, ensure_ascii=False, default=str),
                env.version, env.scope, env.principal, env.response_shape,
                env.response_summary, env.raw_hash, env.duration_ms,
                env.error, int(env.cached), int(env.degraded), int(env.schema_valid),
                env.created_at,
            ),
        )
        self._conn.commit()
        return env

    def list_calls(
        self,
        *,
        category: str | None = None,
        tool: str | None = None,
        scope: str | None = None,
        principal: str | None = None,
        cached: bool | None = None,
        degraded: bool | None = None,
        schema_valid: bool | None = None,
        has_error: bool | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ToolCallEnvelope]:
        """按筛选条件查询审计记录 (分页)。"""
        where: list[str] = []
        args: list[Any] = []
        if category:
            where.append("category = ?")
            args.append(category)
        if tool:
            where.append("tool = ?")
            args.append(tool)
        if scope:
            where.append("scope = ?")
            args.append(scope)
        if principal:
            where.append("principal = ?")
            args.append(principal)
        if cached is not None:
            where.append("cached = ?")
            args.append(int(cached))
        if degraded is not None:
            where.append("degraded = ?")
            args.append(int(degraded))
        if schema_valid is not None:
            where.append("schema_valid = ?")
            args.append(int(schema_valid))
        if has_error is not None:
            if has_error:
                where.append("error IS NOT NULL")
            else:
                where.append("error IS NULL")
        if date_from:
            where.append("created_at >= ?")
            args.append(date_from)
        if date_to:
            where.append("created_at <= ?")
            args.append(date_to)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
            SELECT id, seq, tool, category, params_hash, params_summary, version, scope,
                   principal, response_shape, response_summary, raw_hash, duration_ms,
                   error, cached, degraded, schema_valid, created_at
            FROM tool_call_envelopes
            {clause}
            ORDER BY seq DESC
            LIMIT ? OFFSET ?
        """
        args.extend([limit, offset])
        rows = self._conn.execute(sql, args).fetchall()
        return [self._row_to_envelope(row) for row in rows]

    def count(
        self,
        *,
        category: str | None = None,
        tool: str | None = None,
        scope: str | None = None,
        principal: str | None = None,
        cached: bool | None = None,
        degraded: bool | None = None,
        schema_valid: bool | None = None,
        has_error: bool | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        """按筛选条件计数。"""
        where: list[str] = []
        args: list[Any] = []
        if category:
            where.append("category = ?")
            args.append(category)
        if tool:
            where.append("tool = ?")
            args.append(tool)
        if scope:
            where.append("scope = ?")
            args.append(scope)
        if principal:
            where.append("principal = ?")
            args.append(principal)
        if cached is not None:
            where.append("cached = ?")
            args.append(int(cached))
        if degraded is not None:
            where.append("degraded = ?")
            args.append(int(degraded))
        if schema_valid is not None:
            where.append("schema_valid = ?")
            args.append(int(schema_valid))
        if has_error is not None:
            where.append("error IS NOT NULL" if has_error else "error IS NULL")
        if date_from:
            where.append("created_at >= ?")
            args.append(date_from)
        if date_to:
            where.append("created_at <= ?")
            args.append(date_to)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        row = self._conn.execute(f"SELECT COUNT(*) FROM tool_call_envelopes {clause}", args).fetchone()
        return int(row[0]) if row else 0

    def get_by_id(self, envelope_id: str) -> ToolCallEnvelope | None:
        row = self._conn.execute(
            "SELECT id, seq, tool, category, params_hash, params_summary, version, scope, "
            "principal, response_shape, response_summary, raw_hash, duration_ms, "
            "error, cached, degraded, schema_valid, created_at "
            "FROM tool_call_envelopes WHERE id = ?",
            (envelope_id,),
        ).fetchone()
        return self._row_to_envelope(row) if row else None

    @staticmethod
    def _row_to_envelope(row: sqlite3.Row) -> ToolCallEnvelope:
        try:
            params_summary = json.loads(row[5]) if row[5] else {}
        except (json.JSONDecodeError, TypeError):
            params_summary = {"_raw": str(row[5])}
        return ToolCallEnvelope(
            id=str(row[0]),
            seq=int(row[1]),
            tool=str(row[2]),
            category=str(row[3]),
            params_hash=str(row[4]),
            params_summary=params_summary,
            version=row[6],
            scope=row[7],
            principal=row[8],
            response_shape=row[9],
            response_summary=row[10],
            raw_hash=row[11],
            duration_ms=float(row[12]) if row[12] is not None else 0.0,
            error=row[13],
            cached=bool(row[14]),
            degraded=bool(row[15]),
            schema_valid=bool(row[16]),
            created_at=str(row[17]),
        )


# ── 审计 seam: 上下文管理器 + 装饰器 ──────────────────────────────

class AuditContext:
    """上下文管理器: 自动记录工具调用的开始/结束/耗时/错误。

    Usage:
        with AuditContext(repo, tool="openai.chat", category="ai",
                          params={"model": "gpt-4"}, scope="analysis") as audit:
            result = some_tool_call()
            audit.set_response(shape="text", summary=result[:200], raw=result)
    """

    def __init__(
        self,
        repo: ToolCallAuditRepository,
        *,
        tool: str,
        category: str,
        params: dict[str, Any] | None = None,
        version: str | None = None,
        scope: str | None = None,
        principal: str | None = None,
    ) -> None:
        self._repo = repo
        self._tool = tool
        self._category = category
        self._params = params
        self._version = version
        self._scope = scope
        self._principal = principal
        self._t0: float = 0.0
        self._response_shape: str | None = None
        self._response_summary: str | None = None
        self._raw: str | bytes | None = None
        self._cached: bool = False
        self._degraded: bool = False
        self._schema_valid: bool = True
        self._error: str | None = None

    def __enter__(self) -> "AuditContext":
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Any, exc_tb: Any) -> bool:
        duration_ms = (time.monotonic() - self._t0) * 1000
        if exc_val is not None:
            self._error = str(exc_val)
        self._repo.append(
            tool=self._tool,
            category=self._category,
            params=self._params,
            version=self._version,
            scope=self._scope,
            principal=self._principal,
            response_shape=self._response_shape,
            response_summary=self._response_summary,
            raw=self._raw,
            duration_ms=duration_ms,
            error=self._error,
            cached=self._cached,
            degraded=self._degraded,
            schema_valid=self._schema_valid,
        )
        return False  # 不抑制异常

    def set_response(
        self,
        *,
        shape: str | None = None,
        summary: str | None = None,
        raw: str | bytes | None = None,
        cached: bool = False,
        degraded: bool = False,
        schema_valid: bool = True,
    ) -> None:
        self._response_shape = shape
        self._response_summary = summary[:500] if summary else None
        self._raw = raw
        self._cached = cached
        self._degraded = degraded
        self._schema_valid = schema_valid
