"""行情状态 API。

盘中选股相关端点已迁移至策略页面，此处仅保留全局行情基础设施。
实时推送已迁移到 WebSocket (Phase 55 /ws/stream 端点)。
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Query, Request


router = APIRouter(prefix="/api/intraday", tags=["quotes"])


def _get_quote_service(request: Request):
    """获取全局 QuoteService。"""
    return getattr(request.app.state, "quote_service", None)


def _analysis_scope(request: Request):
    resolver = getattr(request.app.state, "resolve_analysis_subject_scope", None)
    if not callable(resolver):
        raise HTTPException(status_code=503, detail="analysis stream authorization is unavailable")
    try:
        scope = resolver(request)
    except Exception as error:
        raise HTTPException(status_code=503, detail="analysis stream authorization is unavailable") from error
    if not callable(getattr(scope, "allows", None)):
        raise HTTPException(status_code=503, detail="analysis stream authorization is unavailable")
    return scope


def _advanced_scope(request: Request):
    """Resolve the advanced stream scope only from server-held policy."""
    resolver = getattr(request.app.state, "resolve_advanced_subject_scope", None)
    if not callable(resolver):
        return None
    try:
        scope = resolver(request)
    except Exception:
        return None
    return scope if callable(getattr(scope, "allows", None)) else None


def _fallback_index_quotes_from_daily(request: Request, symbols: list[str] | None = None) -> list[dict]:
    """实时指数缓存为空时，从本地指数日 K 取最近收盘价作为兜底。"""
    repo = getattr(request.app.state, "repo", None)
    if not repo:
        return []

    params: list[str] = []
    symbol_filter = ""
    if symbols:
        placeholders = ", ".join("?" for _ in symbols)
        symbol_filter = f"WHERE symbol IN ({placeholders})"
        params.extend(symbols)

    try:
        rows = repo.execute_all(
            f"""
            WITH ranked AS (
                SELECT symbol, date, close,
                       row_number() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                FROM kline_index_daily
                {symbol_filter}
            ), latest AS (
                SELECT symbol,
                       max(CASE WHEN rn = 1 THEN date END) AS date,
                       max(CASE WHEN rn = 1 THEN close END) AS last_price,
                       max(CASE WHEN rn = 2 THEN close END) AS prev_close
                FROM ranked
                WHERE rn <= 2
                GROUP BY symbol
            )
            SELECT latest.symbol, latest.date, latest.last_price, latest.prev_close
            FROM latest
            ORDER BY latest.symbol
            """,
            params,
        )
    except Exception:  # noqa: BLE001
        return []

    out: list[dict] = []
    for symbol, dt, last_price, prev_close in rows:
        change_amount = None
        change_pct = None
        if last_price is not None and prev_close not in (None, 0):
            change_amount = float(last_price) - float(prev_close)
            change_pct = change_amount / float(prev_close) * 100
        out.append({
            "symbol": symbol,
            "name": None,
            "date": str(dt) if dt else None,
            "last_price": float(last_price) if last_price is not None else None,
            "close": float(last_price) if last_price is not None else None,
            "prev_close": float(prev_close) if prev_close is not None else None,
            "change_amount": change_amount,
            "change_pct": change_pct,
            "source": "index_daily",
        })
    return out


@router.get("/status")
def status(request: Request):
    """行情状态 (来自全局 QuoteService)。"""
    qs = _get_quote_service(request)
    if qs:
        out = qs.status()
    else:
        out = {"enabled": False, "running": False, "symbol_count": 0, "index_symbol_count": 0,
               "quote_age_ms": None, "is_trading_hours": False, "last_fetch_ms": None}
    # stockdb WS 实时通道状态 (M004): 未接入时 ws.configured=false, 前端隐藏指示
    ws = getattr(request.app.state, "stockdb_ws", None)
    out["ws"] = ws.status() if ws is not None else {"configured": False, "connected": False}
    return out

@router.get("/alerts")
def alerts_feed(request: Request, since: int = Query(0, description="游标: 上次 cursor"),
                limit: int = Query(100, ge=1, le=500)):
    """实时异动事件流 (stockdb WS alerts 频道, M004)。

    source_gate: open=上游推送中; closed=订阅 ≥120s 无帧 (stockdb THS_PUSH_ENABLED
    未开, 异动源不存在); quiet=等待判定期。前端据 gate 如实呈现空态。
    """
    ws = getattr(request.app.state, "stockdb_ws", None)
    if ws is None:
        return {"events": [], "cursor": 0, "source_gate": "unavailable"}
    return ws.alerts_since(since_seq=since, limit=limit)


@router.get("/indices")
def index_quotes(
    request: Request,
    symbols: str | None = Query(None, description="逗号分隔的指数 symbol 列表"),
):
    """返回实时指数行情缓存，不触发 TickFlow 请求。"""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    qs = _get_quote_service(request)
    if not qs:
        rows = _fallback_index_quotes_from_daily(request, symbol_list)
        return {"rows": rows, "count": len(rows), "source": "index_daily"}
    df = qs.get_index_quotes(symbol_list)
    rows = df.to_dicts() if not df.is_empty() else []
    if not rows:
        rows = _fallback_index_quotes_from_daily(request, symbol_list)
        return {"rows": rows, "count": len(rows), "source": "index_daily"}
    return {"rows": rows, "count": len(rows), "source": "realtime"}


@router.post("/refresh")
def refresh_quotes(request: Request):
    """手动刷新一次行情数据。"""
    qs = _get_quote_service(request)
    if qs:
        return qs.refresh()
    return {"error": "QuoteService not available"}


@router.post("/phase1-trigger")
def trigger_phase1_fixture(request: Request) -> dict[str, bool]:
    """Exercise the governed fixture price-rule path without a live quote request."""
    import os

    if os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="not found")
    qs = _get_quote_service(request)
    if qs is None:
        raise HTTPException(status_code=503, detail="QuoteService not available")
    return qs.trigger_phase1_fixture_monitor()
