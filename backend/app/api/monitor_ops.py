"""Phase 54 监控运营 API — 监控规则与通知渠道运营闭环。

MON-01: test-fire  — 对指定规则执行 synthetic 触发评估, 不落盘/不推送, 返回事件预览。
MON-02: rule-status — 返回每条启用规则的冷却剩余、最近触发、通知渠道健康统计。
MON-03: digest-preview — 汇总最近 24 小时告警, 生成 digest 文本预览 (不投递)。

所有端点遵循 fail-soft: 子查询失败时返回空结果而非 500, 保持监控面板可用性。
"""
from __future__ import annotations

import contextlib
import logging
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request

from app.audit.envelope import ToolCallAuditRepository
from app.strategy import monitor_rules

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitor-ops", tags=["monitor-ops"])


def _data_dir(request: Request) -> Path:
    """返回当前数据目录 (data/), 监控规则文件位于其下。"""
    return request.app.state.repo.store.data_dir


def _monitor_engine(request: Request) -> Any:
    """返回已装配的 MonitorRuleEngine, 未装配时返回 None。"""
    return getattr(request.app.state, "monitor_engine", None)


def _operational(request: Request) -> Any:
    """返回 OperationalRepository, 未装配时返回 None。"""
    return getattr(request.app.state, "operational", None)


def _audit_repo(request: Request) -> ToolCallAuditRepository | None:
    """从 app.state.operational 打开一个只读审计连接, 供工具调用查询复用。

    调用方负责在使用后关闭底层连接 (ToolCallAuditRepository 不持有生命周期管理)。
    """
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


# ── MON-01: test-fire ──────────────────────────────────────────────


@router.post("/test-fire")
def test_fire(request: Request, rule_id: str = Query(..., description="要触发预览的规则 id")) -> dict[str, Any]:
    """对指定规则执行 synthetic 触发评估, 返回事件预览 (不落盘/不推送)。

    - ladder 类型: 复用 monitor_rules API 的 test-ladder 逻辑 (mock 封单数据)。
    - 其他类型: 构造 mock DataFrame (从 enriched_latest 取), 调用 engine._evaluate_rule。
    - fail-soft: 规则类型不支持或无数据时返回 { events: [], error }。
    """
    engine = _monitor_engine(request)
    repo = request.app.state.repo

    # 定位规则: 优先从引擎内存态取 (已启用), 再回退文件加载 (含禁用规则供调试)
    rule = None
    if engine is not None:
        rule = engine.rules.get(rule_id)
    if rule is None:
        for r in monitor_rules.load_all(_data_dir(request)):
            if r.get("id") == rule_id:
                rule = r
                break

    if rule is None:
        return {"rule_id": rule_id, "rule_name": "", "events": [], "would_notify": False, "error": "规则不存在"}

    rule_name = rule.get("name", "")
    rtype = rule.get("type", "signal")

    try:
        if rtype == "ladder":
            events = _test_fire_ladder(request, rule)
        else:
            events = _test_fire_generic(request, rule, engine, repo)
    except Exception as e:
        logger.warning("test-fire failed for rule %s: %s", rule_id, e)
        return {"rule_id": rule_id, "rule_name": rule_name, "events": [], "would_notify": False, "error": str(e)}

    # 统一裁剪事件字段, 只返回预览所需
    preview_events = []
    for ev in events:
        preview_events.append({
            "symbol": ev.get("symbol", ""),
            "name": ev.get("name", ""),
            "type": ev.get("type", rtype),
            "message": ev.get("message", ""),
            "severity": ev.get("severity", rule.get("severity", "info")),
            "conditions": ev.get("conditions", [dict(c) for c in rule.get("conditions", [])]),
            "logic": ev.get("logic", rule.get("logic", "and")),
        })

    return {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "events": preview_events,
        "would_notify": bool(preview_events),
    }


def _test_fire_ladder(request: Request, rule: dict) -> list[dict[str, Any]]:
    """对 ladder 规则执行封单 mock 触发 (复用 test-ladder 的数据构造逻辑)。

    与 /api/monitor-rules/test-ladder 的区别: 只评估单条规则, 不批量。
    """
    import polars as pl

    repo = request.app.state.repo
    depth_svc = getattr(request.app.state, "depth_service", None)
    if depth_svc is None:
        return []

    latest = repo.enriched_latest_date()
    if not latest:
        return []

    # 取涨停+跌停封单 {symbol: vol}
    sealed: dict[str, int] = {}
    for is_down in (False, True):
        m = depth_svc.get_sealed_map(latest, is_down=is_down)
        for sym, info in m.items():
            vol = (info or {}).get("vol")
            if vol and vol > 0:
                sealed[sym] = vol
    if not sealed:
        return []

    enriched_today, _ = repo.get_enriched_latest()
    cols = ["symbol", "close", "change_pct"]
    avail = [c for c in cols if c in enriched_today.columns]
    mock = enriched_today.select(avail).filter(pl.col("symbol").is_in(list(sealed.keys())))
    sealed_df = pl.DataFrame({
        "symbol": list(sealed.keys()),
        "_sealed_vol": list(sealed.values()),
    })
    mock = mock.join(sealed_df, on="symbol", how="inner")

    syms = rule.get("symbols", [])
    sym = syms[0] if syms else None
    metric = rule.get("metric", "sealed_vol")
    thr = rule.get("threshold", 0)
    direction = rule.get("direction", "up")
    warn_label = "炸板预警" if direction == "up" else "翘板预警"

    cur_vol = sealed.get(sym) if sym else None
    row = mock.filter(pl.col("symbol") == sym) if sym else mock.clear()
    cur_close = row["close"][0] if len(row) and "close" in row.columns else None
    cur_amt = (cur_vol * 100 * cur_close) if (cur_vol and cur_close) else None
    cur_val = cur_amt if metric == "sealed_amount" else cur_vol

    if cur_val is not None and cur_val > 0 and cur_val <= thr:
        if metric == "sealed_amount":
            sv_text = f"{cur_val / 1e4:.0f}万元"
            th_text = f"{thr / 1e4:.0f}万元"
        else:
            sv_text = f"{cur_val:,.0f} 手"
            th_text = f"{thr:,.0f} 手"
        return [{
            "rule_id": rule["id"],
            "rule_name": rule.get("name", ""),
            "symbol": sym,
            "name": sym,
            "type": warn_label,
            "message": f"{warn_label} · 封单 {sv_text} ≤ {th_text}",
            "severity": rule.get("severity", "warn"),
            "conditions": [],
            "logic": "and",
        }]
    return []


def _test_fire_generic(request: Request, rule: dict, engine: Any, repo: Any) -> list[dict[str, Any]]:
    """对 signal/price/market 类型规则用 enriched_latest mock 数据评估。

    复用 engine._evaluate_rule, 但在副本上跑 (不污染 _last_fire 冷却状态)。
    """
    import copy

    if engine is None:
        return []

    enriched_today, _ = repo.get_enriched_latest()
    if enriched_today.is_empty():
        return []

    # 保存并清空该规则的 _last_fire 键, 避免 mock 触发被冷却跳过
    rule_id = rule["id"]
    saved_keys = {
        k: v for k, v in list(engine._last_fire.items()) if k[0] == rule_id
    }
    for k in saved_keys:
        engine._last_fire.pop(k, None)

    try:
        now = time.time()
        events = engine._evaluate_rule(enriched_today, copy.deepcopy(rule), now)
    finally:
        # 恢复冷却状态
        engine._last_fire.update(saved_keys)

    return events


# ── MON-02: rule-status ────────────────────────────────────────────


@router.get("/rule-status")
def rule_status(request: Request) -> dict[str, Any]:
    """返回每条启用规则的冷却剩余、最近触发时间、通知渠道健康统计。

    - cooldown_remaining = cooldown_seconds - (now - last_fire), 若 > 0 则在冷却中。
    - channel_health: 最近 7 天 notification_deliveries 的 sent/failed/skipped 计数。
    """
    engine = _monitor_engine(request)
    operational = _operational(request)

    # 加载启用规则集
    if engine is not None:
        rules_list = list(engine.rules.values())
    else:
        rules_list = [r for r in monitor_rules.load_all(_data_dir(request)) if r.get("enabled", True)]

    # 渠道健康: 最近 7 天全局统计 (按 rule_id 不分, 因 deliveries 关联 event_id 而非 rule_id)
    channel_health_total = {"sent": 0, "failed": 0, "skipped": 0}
    if operational is not None:
        try:
            channel_health_total = _channel_health_total(operational, days=7)
        except Exception as e:
            logger.warning("channel health query failed: %s", e)

    now = time.time()
    rules_out: list[dict[str, Any]] = []
    with_active_cooldown = 0

    for rule in rules_list:
        rule_id = rule.get("id", "")
        cooldown_seconds = int(rule.get("cooldown_seconds", 3600))
        last_fire_ts = _last_fire_for_rule(engine, rule_id) if engine is not None else None
        last_fire_iso: str | None = None
        cooldown_remaining: float | None = None
        if last_fire_ts is not None:
            last_fire_iso = datetime.fromtimestamp(last_fire_ts, tz=UTC).isoformat()
            elapsed = now - last_fire_ts
            remaining = cooldown_seconds - elapsed
            if remaining > 0:
                cooldown_remaining = round(remaining, 1)
                with_active_cooldown += 1

        rules_out.append({
            "rule_id": rule_id,
            "rule_name": rule.get("name", ""),
            "cooldown_seconds": cooldown_seconds,
            "last_fire": last_fire_iso,
            "cooldown_remaining": cooldown_remaining,
            "channel_health": dict(channel_health_total),
        })

    return {
        "rules": rules_out,
        "summary": {
            "total_rules": len(rules_out),
            "with_active_cooldown": with_active_cooldown,
            "channel_health": dict(channel_health_total),
        },
    }


def _last_fire_for_rule(engine: Any, rule_id: str) -> float | None:
    """从 engine._last_fire 取该规则最近一次触发的时间戳 (多 symbol 取最大)。"""
    candidates = [v for k, v in engine._last_fire.items() if k[0] == rule_id]
    if not candidates:
        return None
    return max(candidates)


def _channel_health_total(operational: Any, days: int = 7) -> dict[str, int]:
    """统计最近 N 天 notification_deliveries 的 sent/failed/skipped 计数。"""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with operational._connection() as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) as cnt
            FROM notification_deliveries
            WHERE created_at >= ?
            GROUP BY status
            """,
            (cutoff,),
        ).fetchall()
    result = {"sent": 0, "failed": 0, "skipped": 0}
    for row in rows:
        status = row["status"]
        if status in result:
            result[status] = int(row["cnt"])
    return result


# ── MON-03: digest-preview ─────────────────────────────────────────


@router.post("/digest-preview")
def digest_preview(request: Request) -> dict[str, Any]:
    """汇总最近 24 小时触发的告警, 生成 digest 内容预览 (不投递)。

    从 operational.list_alert_events(days=1) 取告警事件, 拼成可读文本。
    fail-soft: operational 未装配或无告警时返回空列表 + 占位文本。
    """
    operational = _operational(request)
    as_of = datetime.now(UTC).isoformat()

    if operational is None:
        return {
            "as_of": as_of,
            "total_alerts": 0,
            "digest_text": "运营存储未初始化, 无告警数据",
            "alerts": [],
        }

    try:
        events, _ = operational.list_alert_events(days=1, limit=5000)
    except Exception as e:
        logger.warning("digest-preview alert query failed: %s", e)
        events = []

    alerts: list[dict[str, Any]] = []
    for ev in events:
        alerts.append({
            "symbol": ev.get("symbol", ""),
            "name": ev.get("name", ""),
            "type": ev.get("type", ""),
            "message": ev.get("message", ""),
            "severity": ev.get("severity", "info"),
            "occurred_at": ev.get("occurred_at", ""),
        })

    digest_lines = [f"告警摘要 (最近 24 小时, 共 {len(alerts)} 条)"]
    for a in alerts:
        sym = a["symbol"] or "—"
        name = a["name"] or ""
        label = f"{sym} {name}".strip()
        digest_lines.append(f"- [{a['severity'].upper()}] {label}: {a['type']} · {a['message']}")

    digest_text = "\n".join(digest_lines)

    return {
        "as_of": as_of,
        "total_alerts": len(alerts),
        "digest_text": digest_text,
        "alerts": alerts,
    }
