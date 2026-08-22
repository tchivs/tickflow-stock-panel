"""Phase 53 WORK-01..06: 今日工作台汇总 API。

一个 GET /api/workbench 聚合首页所需的全部运维信号:

  - data_quality: 数据新鲜度 + 缺陷 (复用 Phase 52 AUDIT-04)
  - provider_health: Provider 健康总览 (复用 Phase 52 AUDIT-03)
  - jobs: 运行中 / 失败任务 (WORK-02)
  - recent_reports: 最近报告与产物入口 (WORK-03)
  - recent_alerts: 最近监控触发 (WORK-04)
  - pending: 统一待确认收件箱 (WORK-05)
    - lifecycle: 决策运行待审核
    - promotion: 因子晋升 ticket 待消费
    - signals: 自定义信号
    - paper_rebalance: 纸面调仓待确认

该端点只读, 无副作用。各子项失败时 fail-soft 返回空, 不阻断整体响应。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.audit import data_quality, provider_doctor

router = APIRouter(prefix="/api/workbench", tags=["workbench"])


# ── helpers ──────────────────────────────────────────────────────

def _safe(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """fail-soft: 子项异常时返回 None, 不阻断汇总响应。"""
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001
        return None


def _operational(request: Request) -> Any:
    return request.app.state.operational


# ── jobs: 运行中 / 失败任务 ──────────────────────────────────────

def _jobs_section() -> dict[str, Any]:
    from app.services.pipeline_jobs import job_store

    job_store.reap_stale()
    recent = job_store.list_recent(limit=20)
    running = [j for j in recent if j["status"] in ("pending", "running")]
    failed = [j for j in recent if j["status"] == "failed"]
    return {
        "active_id": job_store.active_id(),
        "running": running,
        "failed": failed[:5],
        "total_recent": len(recent),
    }


# ── recent_reports: 最近报告与产物 ───────────────────────────────

def _reports_section(request: Request) -> dict[str, Any]:
    financials_reports: list[dict[str, Any]] = []
    try:
        from app.api.financials import _financial_allowed
        capset = request.app.state.capabilities
        if _financial_allowed(capset):
            from app.services import ai_reports
            financials_reports = [
                {"id": r.get("id"), "symbol": r.get("symbol"), "name": r.get("name"),
                 "focus": r.get("focus"), "created_at": r.get("created_at"),
                 "type": "financial"}
                for r in ai_reports.list_reports()
            ]
    except Exception:  # noqa: BLE001
        pass

    recap_reports: list[dict[str, Any]] = []
    try:
        from app.services import market_recap_reports
        recap_reports = [
            {"id": r.get("id"), "as_of": r.get("as_of"), "focus": r.get("focus"),
             "emotion_label": r.get("emotion_label"), "created_at": r.get("created_at"),
             "type": "market_recap"}
            for r in market_recap_reports.list_reports()
        ]
    except Exception:  # noqa: BLE001
        pass

    all_reports = financials_reports + recap_reports
    all_reports.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"items": all_reports[:10], "total": len(all_reports)}


# ── recent_alerts: 最近监控触发 ───────────────────────────────────

def _alerts_section(request: Request) -> dict[str, Any]:
    repo = _operational(request)
    events, total = repo.list_alert_events(days=7, limit=20)
    items = [
        {
            "id": e.get("id"),
            "symbol": e.get("symbol"),
            "name": e.get("name"),
            "type": e.get("type"),
            "severity": e.get("severity"),
            "message": e.get("message"),
            "occurred_at": e.get("occurred_at"),
            "source": e.get("source"),
        }
        for e in events
    ]
    return {"items": items, "total": total}


# ── pending: 统一待确认收件箱 ─────────────────────────────────────

def _pending_section(request: Request) -> dict[str, Any]:
    repo = _operational(request)

    # 1. 生命周期: 最近决策运行 (最近 7 天)
    lifecycle: list[dict[str, Any]] = []
    try:
        with repo._connection() as conn:
            rows = conn.execute(
                """SELECT id, symbol, data_as_of, created_at
                   FROM decision_runs
                   ORDER BY created_at DESC LIMIT 10"""
            ).fetchall()
        lifecycle = [
            {"id": r["id"], "symbol": r["symbol"], "data_as_of": r["data_as_of"],
             "created_at": r["created_at"], "type": "lifecycle",
             "link": f"/review?run_id={r['id']}"}
            for r in rows
        ]
    except Exception:  # noqa: BLE001
        pass

    # 2. 因子晋升: pending 状态的 ticket
    promotion: list[dict[str, Any]] = []
    try:
        with repo._connection() as conn:
            rows = conn.execute(
                """SELECT id, run_id, candidate_id, canonical_expression,
                          status, issued_at, expires_at
                   FROM promotion_tickets
                   WHERE status = 'pending'
                   ORDER BY issued_at DESC LIMIT 10"""
            ).fetchall()
        promotion = [
            {"id": r["id"], "run_id": r["run_id"], "candidate_id": r["candidate_id"],
             "canonical_expression": r["canonical_expression"], "status": r["status"],
             "issued_at": r["issued_at"], "expires_at": r["expires_at"],
             "type": "promotion", "link": f"/backtest/alpha-workbench?run_id={r['run_id']}"}
            for r in rows
        ]
    except Exception:  # noqa: BLE001
        pass

    # 3. 自定义信号
    signals: list[dict[str, Any]] = []
    try:
        from app.strategy import custom_signals
        data_dir = request.app.state.repo.store.data_dir
        sigs = custom_signals.load_all(data_dir)
        signals = [
            {"id": s.get("id"), "name": s.get("name"), "enabled": s.get("enabled"),
             "type": "signal", "link": "/monitor"}
            for s in sigs if s.get("enabled")
        ]
    except Exception:  # noqa: BLE001
        pass

    # 4. 纸面调仓: 最近 portfolio 快照
    paper_rebalance: list[dict[str, Any]] = []
    try:
        positions = repo.list_positions(limit=5)
        paper_rebalance = [
            {"symbol": p.get("symbol"), "name": p.get("name"),
             "quantity": p.get("quantity"), "cost": p.get("cost"),
             "type": "paper_rebalance", "link": "/portfolio"}
            for p in positions
        ]
    except Exception:  # noqa: BLE001
        pass

    items = lifecycle + promotion + signals + paper_rebalance
    return {
        "items": items,
        "counts": {
            "lifecycle": len(lifecycle),
            "promotion": len(promotion),
            "signals": len(signals),
            "paper_rebalance": len(paper_rebalance),
            "total": len(items),
        },
    }


# ── push_stats: 推送质量统计 (PA-03, D-03) ──────────────────────

_EMPTY_PUSH_STATS: dict[str, Any] = {
    "today": {"total": 0, "sent": 0, "failed": 0, "dedup_skipped": 0},
    "by_tool": {},
    "recent_failures": [],
}


def _push_stats_section(request: Request) -> dict[str, Any]:
    """推送投递质量统计: 今日 sct/wecom/connection 三类 tool 的 total/sent/failed
    + notification_deliveries 去重跳过计数 + 最近 10 条失败记录。

    fail-soft: 审计 repo 不可用或表不存在时返回空统计。
    """
    repo = _operational(request)
    by_tool: dict[str, dict[str, int]] = {}
    total = sent = failed = 0
    dedup_skipped = 0
    recent_failures: list[dict[str, Any]] = []

    with repo._connection() as conn:
        # 1. 今日 tool_call_envelopes 统计 (sct/wecom/connection)
        rows = conn.execute(
            """
            SELECT
                tool,
                COUNT(*) as total,
                SUM(CASE WHEN error IS NULL THEN 1 ELSE 0 END) as sent,
                SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as failed
            FROM tool_call_envelopes
            WHERE tool IN ('sct', 'wecom', 'connection')
              AND date(created_at) = date('now')
            GROUP BY tool
            """
        ).fetchall()
        for r in rows:
            by_tool[r["tool"]] = {
                "total": int(r["total"] or 0),
                "sent": int(r["sent"] or 0),
                "failed": int(r["failed"] or 0),
            }
            total += int(r["total"] or 0)
            sent += int(r["sent"] or 0)
            failed += int(r["failed"] or 0)

        # 2. 今日 notification_deliveries 去重跳过计数
        dedup_row = conn.execute(
            """
            SELECT COUNT(*) as dedup_skipped
            FROM notification_deliveries
            WHERE status = 'skipped' AND error = 'dedup'
              AND date(created_at) = date('now')
            """
        ).fetchone()
        dedup_skipped = int(dedup_row["dedup_skipped"]) if dedup_row else 0

        # 3. 最近 10 条失败记录
        fail_rows = conn.execute(
            """
            SELECT tool, error, created_at
            FROM tool_call_envelopes
            WHERE tool IN ('sct', 'wecom', 'connection')
              AND error IS NOT NULL
            ORDER BY seq DESC
            LIMIT 10
            """
        ).fetchall()
        for r in fail_rows:
            recent_failures.append({
                "tool": r["tool"],
                "error": r["error"],
                "created_at": r["created_at"],
            })

    return {
        "today": {
            "total": total,
            "sent": sent,
            "failed": failed,
            "dedup_skipped": dedup_skipped,
        },
        "by_tool": by_tool,
        "recent_failures": recent_failures,
    }


# ── GET /api/workbench ───────────────────────────────────────────

@router.get("")
def workbench(request: Request) -> dict[str, Any]:
    """今日工作台汇总端点。

    首页一次性拉取全部运维信号, 每个子项 fail-soft 独立。
    数据质量与 Provider 健康复用 Phase 52 审计 API。
    """
    return {
        "data_quality": _safe(data_quality, request),
        "provider_health": _safe(provider_doctor, request),
        "jobs": _safe(_jobs_section),
        "recent_reports": _safe(_reports_section, request),
        "recent_alerts": _safe(_alerts_section, request),
        "pending": _safe(_pending_section, request),
        "push_stats": _safe(_push_stats_section, request),
    }
