"""Phase 52 AUDIT-02/03/04: 统一审计 API。

AUDIT-02: 工具调用查询 API (分页 + 筛选)
AUDIT-03: Provider Doctor 诊断 API (只读, 分级结论)
AUDIT-04: 统一数据质量 API (新鲜度 + 缺陷摘要)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.audit.envelope import ToolCallAuditRepository
from app.data_providers import chain as provider_chain

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _audit_repo(request: Request) -> ToolCallAuditRepository:
    """从 app.state.operational 获取审计 repository。"""
    db_path: Path = request.app.state.operational.database_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return ToolCallAuditRepository(conn)


def _close_repo(repo: ToolCallAuditRepository) -> None:
    """关闭底层连接。"""
    try:
        repo._conn.close()
    except Exception:
        pass


# ── AUDIT-02: 工具调用查询 ───────────────────────────────────────


class ToolCallListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


@router.get("/tool-calls", response_model=ToolCallListResponse)
def list_tool_calls(
    request: Request,
    category: str | None = Query(None, description="provider / ai / notification / external"),
    tool: str | None = Query(None, description="tool name"),
    scope: str | None = Query(None, description="scope tag"),
    principal: str | None = Query(None, description="principal identity"),
    cached: bool | None = Query(None, description="cached calls only"),
    degraded: bool | None = Query(None, description="degraded calls only"),
    schema_valid: bool | None = Query(None, description="schema valid/invalid only"),
    has_error: bool | None = Query(None, description="error/no-error only"),
    date_from: str | None = Query(None, description="ISO date string, inclusive"),
    date_to: str | None = Query(None, description="ISO date string, inclusive"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ToolCallListResponse:
    """查询工具调用审计记录 (分页 + 筛选)。

    审计只追加事实, 不改变确定性代码对生成/评估/门禁/晋级的所有权。
    返回内容经过脱敏: 不暴露密钥、完整报文或个人数据, 只能看到 raw_hash 与脱敏摘要。
    """
    repo = _audit_repo(request)
    try:
        calls = repo.list_calls(
            category=category,
            tool=tool,
            scope=scope,
            principal=principal,
            cached=cached,
            degraded=degraded,
            schema_valid=schema_valid,
            has_error=has_error,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
        total = repo.count(
            category=category,
            tool=tool,
            scope=scope,
            principal=principal,
            cached=cached,
            degraded=degraded,
            schema_valid=schema_valid,
            has_error=has_error,
            date_from=date_from,
            date_to=date_to,
        )
        return ToolCallListResponse(
            items=[c.to_dict() for c in calls],
            total=total,
            limit=limit,
            offset=offset,
        )
    finally:
        _close_repo(repo)


@router.get("/tool-calls/{envelope_id}")
def get_tool_call(request: Request, envelope_id: str) -> dict[str, Any]:
    """获取单条工具调用审计记录详情。"""
    repo = _audit_repo(request)
    try:
        env = repo.get_by_id(envelope_id)
        if env is None:
            raise HTTPException(status_code=404, detail="tool call not found")
        return env.to_dict()
    finally:
        _close_repo(repo)


@router.get("/tool-calls-summary/summary")
def tool_calls_summary(request: Request) -> dict[str, Any]:
    """审计摘要: 按 category/tool 统计调用次数与错误率。"""
    repo = _audit_repo(request)
    try:
        conn = repo._conn
        # 按 category 统计
        cat_rows = conn.execute("""
            SELECT category, COUNT(*) as total,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors,
                   SUM(CASE WHEN degraded = 1 THEN 1 ELSE 0 END) as degraded,
                   SUM(CASE WHEN cached = 1 THEN 1 ELSE 0 END) as cached
            FROM tool_call_envelopes GROUP BY category
        """).fetchall()
        by_category = {
            r[0]: {"total": r[1], "errors": r[2], "degraded": r[3], "cached": r[4]}
            for r in cat_rows
        }
        # 按 tool 统计 (top 20)
        tool_rows = conn.execute("""
            SELECT tool, COUNT(*) as total,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors
            FROM tool_call_envelopes GROUP BY tool ORDER BY total DESC LIMIT 20
        """).fetchall()
        by_tool = {
            r[0]: {"total": r[1], "errors": r[2]} for r in tool_rows
        }
        total = sum(c["total"] for c in by_category.values())
        total_errors = sum(c["errors"] for c in by_category.values())
        return {
            "total_calls": total,
            "total_errors": total_errors,
            "error_rate": round(total_errors / total, 4) if total > 0 else 0,
            "by_category": by_category,
            "by_tool": by_tool,
        }
    finally:
        _close_repo(repo)


# ── AUDIT-03: Provider Doctor ────────────────────────────────────


class DoctorVerdict(BaseModel):
    name: str
    display_name: str
    health: str  # ok / warn / error
    datasets: list[str]
    detail: str
    recommendation: str


@router.get("/provider-doctor")
def provider_doctor(request: Request) -> dict[str, Any]:
    """对每个数据源 Provider 执行 Doctor 诊断。

    只读, 无自动修复副作用。返回健康/降级/不可用分级结论与建议动作。
    """
    from app.config import settings

    verdicts: list[DoctorVerdict] = []

    builtin_sources = [
        {"name": "tickflow", "display_name": "TickFlow", "datasets": ["daily", "adj_factor", "realtime", "minute", "financial"]},
        {"name": "free_stockdb", "display_name": "Free-StockDB (HTTP)", "datasets": ["daily", "minute", "boards"]},
        {"name": "local_stockdb", "display_name": "Local StockDB (本机)", "datasets": ["daily", "minute"]},
        {"name": "ifzq", "display_name": "ifzq 免费K线", "datasets": ["daily", "minute"]},
        {"name": "sina", "display_name": "新浪 分钟K (免费)", "datasets": ["minute"]},
        {"name": "xyz", "display_name": "xyz 在线 (MCP)", "datasets": ["daily", "minute"]},
        {"name": "tencent", "display_name": "腾讯实时 (免费)", "datasets": ["realtime"]},
    ]

    for src in builtin_sources:
        name = src["name"]
        try:
            health = provider_chain.health_check(name)
        except Exception as e:
            health = "error"
            detail = f"诊断异常: {e}"
        else:
            if health == "ok":
                detail = "Provider 响应正常"
            elif health == "warn":
                detail = "Provider 返回空或部分数据"
            else:
                detail = "Provider 不可用"

        recommendation = {
            "ok": "无需操作",
            "warn": "检查网络或切换到备用数据源",
            "error": "检查 Provider 配置与网络连通性; 可临时切换到其他数据源",
        }.get(health, "未知状态")

        verdicts.append(DoctorVerdict(
            name=name,
            display_name=src["display_name"],
            health=health,
            datasets=src["datasets"],
            detail=detail,
            recommendation=recommendation,
        ))

    # AI provider 诊断
    from app.services.ai_provider import ai_configured, current_ai_provider
    ai_ok = ai_configured(current_ai_provider())
    verdicts.append(DoctorVerdict(
        name="ai_provider",
        display_name=f"AI Provider ({current_ai_provider()})",
        health="ok" if ai_ok else "error",
        datasets=["chat", "stream"],
        detail="AI provider 已配置" if ai_ok else "AI provider 未配置或密钥缺失",
        recommendation="无需操作" if ai_ok else "在设置页配置 AI provider 和 API key",
    ))

    total = len(verdicts)
    ok_count = sum(1 for v in verdicts if v.health == "ok")
    warn_count = sum(1 for v in verdicts if v.health == "warn")
    error_count = sum(1 for v in verdicts if v.health == "error")

    return {
        "verdicts": [v.model_dump() for v in verdicts],
        "summary": {
            "total": total,
            "ok": ok_count,
            "warn": warn_count,
            "error": error_count,
            "overall": "healthy" if error_count == 0 else ("degraded" if warn_count > 0 else "unavailable"),
        },
    }


# ── AUDIT-04: 数据质量 API ───────────────────────────────────────


class DataSourceQuality(BaseModel):
    name: str
    display_name: str
    health: str  # ok / warn / error
    last_sync: str | None = None
    datasets: list[str] = []
    detail: str = ""


@router.get("/data-quality")
def data_quality(request: Request) -> dict[str, Any]:
    """统一数据质量 API: 各数据源新鲜度与缺陷摘要。

    该 API 是 Phase 53 首页与各页面共享 Banner 的数据源。
    """
    from app.config import settings

    sources: list[DataSourceQuality] = []

    builtin_sources = [
        {"name": "tickflow", "display_name": "TickFlow", "datasets": ["daily", "adj_factor", "realtime", "minute", "financial"]},
        {"name": "free_stockdb", "display_name": "Free-StockDB (HTTP)", "datasets": ["daily", "minute", "boards"]},
        {"name": "local_stockdb", "display_name": "Local StockDB (本机)", "datasets": ["daily", "minute"]},
        {"name": "ifzq", "display_name": "ifzq 免费K线", "datasets": ["daily", "minute"]},
        {"name": "sina", "display_name": "新浪 分钟K (免费)", "datasets": ["minute"]},
        {"name": "xyz", "display_name": "xyz 在线 (MCP)", "datasets": ["daily", "minute"]},
        {"name": "tencent", "display_name": "腾讯实时 (免费)", "datasets": ["realtime"]},
    ]

    # 查询最近的 Parquet 分区日期作为新鲜度指标
    try:
        from app.tickflow.repository import KlineRepository
        repo = request.app.state.repo
        # 获取 kline_daily 最新分区日期
        daily_latest = None
        if hasattr(repo, "store") and hasattr(repo.store, "data_dir"):
            daily_dir = repo.store.data_dir / "kline_daily"
            if daily_dir.exists():
                partitions = sorted([p.name for p in daily_dir.iterdir() if p.is_dir()])
                if partitions:
                    daily_latest = partitions[-1]
    except Exception:
        daily_latest = None

    for src in builtin_sources:
        name = src["name"]
        try:
            health = provider_chain.health_check(name)
        except Exception:
            health = "error"
        detail_map = {
            "ok": "数据源响应正常",
            "warn": "数据源返回空或部分数据, 可能有延迟",
            "error": "数据源不可用, 请检查配置",
        }
        sources.append(DataSourceQuality(
            name=name,
            display_name=src["display_name"],
            health=health,
            datasets=src["datasets"],
            last_sync=daily_latest if name in ("tickflow", "free_stockdb", "local_stockdb") else None,
            detail=detail_map.get(health, "未知状态"),
        ))

    # AI provider 质量
    from app.services.ai_provider import ai_configured, current_ai_provider
    sources.append(DataSourceQuality(
        name="ai_provider",
        display_name=f"AI Provider ({current_ai_provider()})",
        health="ok" if ai_configured(current_ai_provider()) else "error",
        datasets=["chat", "stream"],
        detail="AI provider 已配置" if ai_configured(current_ai_provider()) else "AI provider 未配置",
    ))

    total = len(sources)
    ok_count = sum(1 for s in sources if s.health == "ok")
    warn_count = sum(1 for s in sources if s.health == "warn")
    error_count = sum(1 for s in sources if s.health == "error")

    # 生成告警
    alerts: list[dict[str, Any]] = []
    for s in sources:
        if s.health == "error":
            alerts.append({
                "level": "error",
                "source": s.name,
                "message": f"{s.display_name} 不可用: {s.detail}",
            })
        elif s.health == "warn":
            alerts.append({
                "level": "warn",
                "source": s.name,
                "message": f"{s.display_name} 降级: {s.detail}",
            })

    return {
        "sources": [s.model_dump() for s in sources],
        "alerts": alerts,
        "summary": {
            "total": total,
            "ok": ok_count,
            "warn": warn_count,
            "error": error_count,
            "daily_latest_date": daily_latest,
            "overall": "healthy" if error_count == 0 else ("degraded" if warn_count > 0 else "unavailable"),
        },
    }
