"""Phase 54 报告运营 API — 报告证据卡与多空冲突/失败路径。

MON-04: evidence — 返回报告关联的证据卡 (tool_call_envelopes) 与数据质量摘要。
MON-05: conflicts — 返回多空冲突观点 (decision run baseline/final) 与失败路径。

所有端点遵循 fail-soft: 无关联记录或查询失败时返回空列表, 不 500。
"""
from __future__ import annotations

import contextlib
import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Query, Request

from app.audit.envelope import ToolCallAuditRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/report-ops", tags=["report-ops"])


def _operational(request: Request) -> Any:
    """返回 OperationalRepository, 未装配时返回 None。"""
    return getattr(request.app.state, "operational", None)


def _audit_repo(request: Request) -> ToolCallAuditRepository | None:
    """从 app.state.operational 打开一个只读审计连接。"""
    operational = _operational(request)
    if operational is None:
        return None
    conn = sqlite3.connect(str(operational.database_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return ToolCallAuditRepository(conn)


def _close_audit_repo(repo: ToolCallAuditRepository | None) -> None:
    """关闭审计连接 (fail-soft)。"""
    if repo is None:
        return
    with contextlib.suppress(Exception):
        repo._conn.close()


def _resolve_scope(request: Request, run_id: str | None, report_type: str | None, report_id: str | None) -> str | None:
    """根据参数推导 tool_call_envelopes 的 scope 过滤值。

    - run_id 优先: 直接用 run_id 作为 scope (alpha run / decision run 约定)。
    - report_type + report_id: 构造 ``report:{type}:{id}`` 约定 scope。
    - 均无: 返回 None (调用方决定降级策略)。
    """
    if run_id:
        return run_id
    if report_type and report_id:
        return f"report:{report_type}:{report_id}"
    return None


def _report_title(report_type: str | None, report_id: str | None, tool: str, idx: int) -> str:
    """为证据卡生成可读标题。"""
    type_label = {"financial": "财务分析", "market_recap": "大盘复盘"}.get(report_type or "", report_type or "报告")
    return f"{type_label} 证据 #{idx + 1} · {tool}"


# ── MON-04: evidence ──────────────────────────────────────────────


@router.get("/evidence")
def evidence(
    request: Request,
    run_id: str | None = Query(None, description="决策/Alpha run id"),
    report_type: str | None = Query(None, description="financial | market_recap"),
    report_id: str | None = Query(None, description="报告 id (与 report_type 配合)"),
) -> dict[str, Any]:
    """返回报告关联的证据卡 (工具调用审计) 与数据质量摘要。

    - run_id: 查询关联的 decision run, 提取审计信息。
    - report_type + report_id: 用 ``report:{type}:{id}`` scope 查 tool_calls。
    - 从 audit data_quality 复用数据源健康摘要。
    - fail-soft: 无关联记录时返回空证据卡列表 + 空 data_quality。
    """
    operational = _operational(request)
    scope = _resolve_scope(request, run_id, report_type, report_id)

    evidence_cards: list[dict[str, Any]] = []
    data_quality: dict[str, Any] = {}

    # 1. 证据卡: 从 tool_call_envelopes 按 scope 查询
    audit_repo = _audit_repo(request)
    if audit_repo is not None and scope is not None:
        try:
            calls = audit_repo.list_calls(scope=scope, limit=200)
            for idx, call in enumerate(calls):
                title = _report_title(report_type, report_id, call.tool, idx)
                evidence_cards.append({
                    "title": title,
                    "raw_hash": call.raw_hash,
                    "tool": call.tool,
                    "category": call.category,
                    "response_summary": call.response_summary,
                    "duration_ms": call.duration_ms,
                    "error": call.error,
                    "created_at": call.created_at,
                })
        except Exception as e:
            logger.warning("evidence query failed for scope %s: %s", scope, e)
        finally:
            _close_audit_repo(audit_repo)
    elif audit_repo is not None:
        _close_audit_repo(audit_repo)

    # 2. 数据质量: 复用 audit data_quality 逻辑 (各数据源健康摘要)
    if operational is not None:
        try:
            data_quality = _data_quality_summary(request)
        except Exception as e:
            logger.warning("evidence data_quality query failed: %s", e)

    # 3. 若有 run_id 且为 decision run, 补充 baseline/final 上下文
    run_context: dict[str, Any] = {}
    if run_id and operational is not None:
        try:
            run_context = _decision_run_context(operational, run_id)
        except Exception as e:
            logger.warning("evidence run context failed for %s: %s", run_id, e)

    return {
        "evidence_cards": evidence_cards,
        "data_quality": data_quality,
        "run_context": run_context,
    }


def _data_quality_summary(request: Request) -> dict[str, Any]:
    """复用 audit data-quality 端点逻辑, 返回各数据源健康摘要。

    直接调用 /api/audit/data-quality 的内部实现, 避免重复编码。
    """
    from app.data_providers import chain as provider_chain

    sources: list[dict[str, Any]] = []
    builtin_sources = [
        {"name": "tickflow", "display_name": "TickFlow", "datasets": ["daily", "adj_factor", "realtime", "minute", "financial"]},
        {"name": "free_stockdb", "display_name": "Free-StockDB (HTTP)", "datasets": ["daily", "minute", "boards"]},
        {"name": "local_stockdb", "display_name": "Local StockDB (本机)", "datasets": ["daily", "minute"]},
        {"name": "ifzq", "display_name": "ifzq 免费K线", "datasets": ["daily", "minute"]},
        {"name": "sina", "display_name": "新浪 分钟K (免费)", "datasets": ["minute"]},
        {"name": "xyz", "display_name": "xyz 在线 (MCP)", "datasets": ["daily", "minute"]},
        {"name": "tencent", "display_name": "腾讯实时 (免费)", "datasets": ["realtime"]},
    ]

    daily_latest = None
    try:
        repo = request.app.state.repo
        if hasattr(repo, "store") and hasattr(repo.store, "data_dir"):
            daily_dir = repo.store.data_dir / "kline_daily"
            if daily_dir.exists():
                partitions = sorted([p.name for p in daily_dir.iterdir() if p.is_dir()])
                if partitions:
                    daily_latest = partitions[-1]
    except Exception:
        daily_latest = None

    for src in builtin_sources:
        name: str = str(src["name"])
        try:
            health = provider_chain.health_check(name)
        except Exception:
            health = "error"
        detail_map = {
            "ok": "数据源响应正常",
            "warn": "数据源返回空或部分数据, 可能有延迟",
            "error": "数据源不可用, 请检查配置",
        }
        sources.append({
            "name": name,
            "display_name": src["display_name"],
            "health": health,
            "datasets": src["datasets"],
            "last_sync": daily_latest if name in ("tickflow", "free_stockdb", "local_stockdb") else None,
            "detail": detail_map.get(health, "未知状态"),
        })

    from app.services.ai_provider import ai_configured, current_ai_provider
    sources.append({
        "name": "ai_provider",
        "display_name": f"AI Provider ({current_ai_provider()})",
        "health": "ok" if ai_configured(current_ai_provider()) else "error",
        "datasets": ["chat", "stream"],
        "detail": "AI provider 已配置" if ai_configured(current_ai_provider()) else "AI provider 未配置",
    })

    total = len(sources)
    ok_count = sum(1 for s in sources if s["health"] == "ok")
    warn_count = sum(1 for s in sources if s["health"] == "warn")
    error_count = sum(1 for s in sources if s["health"] == "error")

    return {
        "sources": sources,
        "summary": {
            "total": total,
            "ok": ok_count,
            "warn": warn_count,
            "error": error_count,
            "daily_latest_date": daily_latest,
            "overall": "healthy" if error_count == 0 else ("degraded" if warn_count > 0 else "unavailable"),
        },
    }


def _decision_run_context(operational: Any, run_id: str) -> dict[str, Any]:
    """提取 decision run 的 baseline/final 上下文 (供证据卡关联)。

    fail-soft: 非 decision run 或不存在时返回空。
    """
    run = operational.get_decision_run(run_id)
    if run is None:
        return {}
    return {
        "run_id": run.get("id", run_id),
        "symbol": run.get("symbol", ""),
        "data_as_of": run.get("data_as_of", ""),
        "action": (run.get("final") or {}).get("action", ""),
        "created_at": run.get("created_at", ""),
    }


# ── MON-05: conflicts ──────────────────────────────────────────────


@router.get("/conflicts")
def conflicts(
    request: Request,
    run_id: str | None = Query(None, description="决策/Alpha run id"),
    report_type: str | None = Query(None, description="financial | market_recap"),
    report_id: str | None = Query(None, description="报告 id (与 report_type 配合)"),
) -> dict[str, Any]:
    """返回多空冲突观点与失败路径。

    - conflicts: 从 decision run 的 baseline/final 提取多空观点 (action + reason_snapshot)。
    - failure_paths: 从 audit data_quality 取 error/warn 数据源 + 从 tool_calls 取 has_error 调用。
    - fail-soft: 无冲突/失败数据时返回空列表。
    """
    operational = _operational(request)
    scope = _resolve_scope(request, run_id, report_type, report_id)

    conflicts: list[dict[str, Any]] = []
    failure_paths: list[dict[str, Any]] = []

    # 1. 冲突观点: 从 decision run baseline/final 提取
    if run_id and operational is not None:
        try:
            conflicts = _extract_conflicts_from_run(operational, run_id)
        except Exception as e:
            logger.warning("conflicts run extraction failed for %s: %s", run_id, e)

    # 2. 失败路径: 数据源不可用 (data_quality error/warn)
    try:
        failure_paths.extend(_data_source_failures(request))
    except Exception as e:
        logger.warning("conflicts data source failures query failed: %s", e)

    # 3. 失败路径: tool_calls has_error
    audit_repo = _audit_repo(request)
    if audit_repo is not None and scope is not None:
        try:
            error_calls = audit_repo.list_calls(scope=scope, has_error=True, limit=100)
            for call in error_calls:
                failure_paths.append({
                    "step": call.tool,
                    "reason": call.error or "工具调用失败",
                    "data_source": call.category,
                })
        except Exception as e:
            logger.warning("conflicts tool_calls error query failed for scope %s: %s", scope, e)
        finally:
            _close_audit_repo(audit_repo)
    elif audit_repo is not None:
        _close_audit_repo(audit_repo)

    return {
        "conflicts": conflicts,
        "failure_paths": failure_paths,
    }


def _extract_conflicts_from_run(operational: Any, run_id: str) -> list[dict[str, Any]]:
    """从 decision run 的 baseline/final snapshot 提取多空冲突观点。

    decision baseline 的 action (突破确认/只观察/放弃/风险剔除) 体现看多/看空立场,
    reason_snapshot 携带 ATR/risk_per_share 等结构化依据。这里构造 bullish/bearish 文本。
    """
    run = operational.get_decision_run(run_id)
    if run is None:
        return []

    final = run.get("final") or {}
    baseline = run.get("baseline") or {}
    symbol = run.get("symbol", "")
    action = final.get("action", baseline.get("action", ""))
    reason = final.get("reason_snapshot", baseline.get("reason_snapshot", {})) or {}

    # 多头观点: action 为突破确认/只观察 → 看多逻辑
    bullish_views = []
    bearish_views = []

    if action in ("突破确认", "只观察"):
        entry_low = final.get("entry_low")
        entry_high = final.get("entry_high")
        target1 = final.get("target1")
        target2 = final.get("target2")
        if entry_low is not None and entry_high is not None:
            bullish_views.append(f"入场区间 {entry_low}~{entry_high}")
        if target1 is not None and target2 is not None:
            bullish_views.append(f"目标位 {target1} / {target2}")
        rr = final.get("risk_reward")
        if rr is not None:
            bullish_views.append(f"风险收益比 {rr}")
    elif action in ("放弃", "风险剔除"):
        score = final.get("score")
        if score is not None:
            bearish_views.append(f"综合评分 {score} 偏低")
        atr = reason.get("atr")
        if atr:
            bearish_views.append(f"ATR {atr} 波动偏大")

    # 如果 final 与 baseline action 不同, 体现调整后的冲突
    baseline_action = baseline.get("action", "")
    if baseline_action and baseline_action != action:
        if action in ("放弃", "风险剔除"):
            bearish_views.append(f"最终决策调整为 {action} (基线为 {baseline_action})")
        else:
            bullish_views.append(f"最终决策调整为 {action} (基线为 {baseline_action})")

    if not bullish_views and not bearish_views:
        return []

    bullish = "; ".join(bullish_views) if bullish_views else "无明确多头依据"
    bearish = "; ".join(bearish_views) if bearish_views else "无明确空头依据"

    return [{
        "bullish": bullish,
        "bearish": bearish,
        "source": f"decision_run:{run_id} ({symbol})",
    }]


def _data_source_failures(request: Request) -> list[dict[str, Any]]:
    """从 audit data_quality 提取 error/warn 数据源作为失败路径。"""
    failures: list[dict[str, Any]] = []
    dq = _data_quality_summary(request)
    sources = dq.get("sources", [])
    for src in sources:
        health = src.get("health", "")
        if health in ("error", "warn"):
            level = "数据源不可用" if health == "error" else "数据源降级"
            failures.append({
                "step": src.get("name", ""),
                "reason": f"{level}: {src.get('detail', '')}",
                "data_source": src.get("display_name", src.get("name", "")),
            })
    return failures
