"""WebSocket request 消息分发器 — ndjson LLM 流迁移 (Phase 55, Plan 02 Task 3).

客户端发 ``{type: "request", channel: "analysis:{symbol}" | "review", params: {...}}``
触发后端启动 LLM 流式生成, 通过同一频道推送流式事件:

  - ``analysis_meta`` / ``review_meta``   — 开头元数据
  - ``analysis_delta`` / ``review_delta`` — 逐 chunk 内容
  - ``analysis_done`` / ``review_done``   — 完成
  - ``analysis_error`` / ``review_error`` — 失败 (连接不中断)

D-02: POST StreamingResponse 替换为 WS 频道订阅 + request 消息触发 + 流式推送。
T-55-06: 验证 channel 前缀 (analysis:/review:) + params 白名单; symbol/strategy_id 格式验证。
T-55-07: per-connection 并发 request 上限; conn 断开时取消后台 task。
"""
from __future__ import annotations

import re
from datetime import date as date_cls
from typing import Any

# 合法 symbol / strategy_id 格式 (SAFE_REFERENCE 语义)
_SAFE_REFERENCE = re.compile(r"^[0-9A-Za-z._\-]{1,64}$")

# per-connection 并发 request 上限 (T-55-07)
MAX_PENDING_REQUESTS = 5

# params 字段白名单 (T-55-06)
_ALLOWED_PARAMS = {
    "focus", "symbol", "strategy_id", "days", "kind", "level",
    "as_of", "source", "step", "name", "description",
    "direction", "rules", "execution_backend", "current_code", "instruction",
}


class RequestDispatchError(Exception):
    """request 消息无法路由到合法的 LLM 流式生成。"""


def _validate_channel(channel: str) -> str:
    """验证 channel 格式 (T-55-06): analysis:{symbol} 或 review。"""
    if not isinstance(channel, str):
        raise RequestDispatchError("channel 必须是字符串")
    if channel == "review":
        return channel
    if channel.startswith("analysis:"):
        ref = channel[len("analysis:"):]
        if not ref or not _SAFE_REFERENCE.fullmatch(ref):
            raise RequestDispatchError(f"非法 analysis 频道引用: {channel!r}")
        return channel
    raise RequestDispatchError(f"不支持的频道: {channel!r}")


def _validate_params(params: Any) -> dict:
    """params 字段白名单 + 类型校验 (T-55-06)。"""
    if not isinstance(params, dict):
        raise RequestDispatchError("params 必须是对象")
    unknown = set(params) - _ALLOWED_PARAMS
    if unknown:
        raise RequestDispatchError(f"未知参数: {', '.join(sorted(unknown))}")
    for key in ("focus", "symbol", "strategy_id", "name", "description", "source"):
        value = params.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 256):
            raise RequestDispatchError(f"参数 {key} 必须是不超过 256 字符的字符串")
    for key in ("days", "level"):
        value = params.get(key)
        if value is not None and not isinstance(value, int):
            raise RequestDispatchError(f"参数 {key} 必须是整数")
    value = params.get("kind")
    if value is not None and not isinstance(value, str):
        raise RequestDispatchError("kind 必须是字符串")
    if value is not None and value not in ("concept", "industry", "market_recap", "rps"):
        raise RequestDispatchError("kind 只能是 concept/industry/market_recap/rps")
    return params


def _data_dir(app_state: Any) -> str:
    store = getattr(app_state, "datastore", None)
    if store is not None and getattr(store, "data_dir", None):
        return str(store.data_dir)
    from app.config import settings
    return settings.data_dir


def _repo(app_state: Any):
    repo = getattr(app_state, "repo", None)
    if repo is not None:
        return repo
    from app.parquet import open_repo
    return open_repo(_data_dir(app_state))


async def dispatch(
    conn: Any,
    channel: str,
    params: dict,
    app_state: Any,
) -> None:
    """在后台 task 中运行: 路由 channel → LLM 流式生成 → 频道推送。

    conn 断开时由调用方 (handler) 取消此 task。
    """
    try:
        _validate_channel(channel)
        _validate_params(params)
    except RequestDispatchError as exc:
        await conn.ws.send_json(
            {"type": "error", "seq": 0, "data": {"reason": str(exc)}}
        )
        return

    ws_manager = getattr(app_state, "ws_manager", None)
    if ws_manager is None:
        await conn.ws.send_json(
            {"type": "error", "seq": 0, "data": {"reason": "WS 广播不可用"}}
        )
        return

    if channel == "review":
        await _dispatch_review(ws_manager, channel, params, app_state)
    else:
        await _dispatch_analysis(ws_manager, channel, params, app_state)


# ── analysis:{symbol} — financials / stock_analysis / strategy build ──────

async def _dispatch_analysis(
    ws_manager: Any, channel: str, params: dict, app_state: Any
) -> None:
    ref = channel[len("analysis:"):]
    source = params.get("source") or ""
    symbol = params.get("symbol") or ref
    focus = params.get("focus") or ""

    # strategy build 流: 有 strategy_id/step 参数 → 路由到 strategy build
    if params.get("strategy_id") or "step" in params:
        await _dispatch_strategy_build(ws_manager, channel, params)
        return

    # financial 分析: source 显式指定 financial
    if source == "financial":
        await _dispatch_financials(ws_manager, channel, symbol, focus, app_state)
        return

    # 默认: 个股四维分析
    await _dispatch_stock_analysis(ws_manager, channel, symbol, focus, app_state)


async def _dispatch_financials(
    ws_manager: Any, channel: str, symbol: str, focus: str, app_state: Any
) -> None:
    from app.services.financial_analyzer import analyze_financials_stream

    data_dir = _data_dir(app_state)
    await _broadcast(ws_manager, channel, "analysis_meta", {"symbol": symbol, "focus": focus})
    try:
        async for chunk in analyze_financials_stream(data_dir, symbol, focus):
            await _broadcast(ws_manager, channel, "analysis_delta", {"content": chunk})
        await _broadcast(ws_manager, channel, "analysis_done", {})
    except Exception as exc:  # noqa: BLE001
        await _broadcast(ws_manager, channel, "analysis_error", {"reason": str(exc)})


async def _dispatch_stock_analysis(
    ws_manager: Any, channel: str, symbol: str, focus: str, app_state: Any
) -> None:
    from app.api.stock_analysis import analyze_stock_stream

    repo = _repo(app_state)
    data_dir = _data_dir(app_state)
    await _broadcast(ws_manager, channel, "analysis_meta", {"symbol": symbol, "focus": focus})
    try:
        async for chunk in analyze_stock_stream(repo, data_dir, symbol, focus):
            await _broadcast(ws_manager, channel, "analysis_delta", {"content": chunk})
        await _broadcast(ws_manager, channel, "analysis_done", {})
    except Exception as exc:  # noqa: BLE001
        await _broadcast(ws_manager, channel, "analysis_error", {"reason": str(exc)})


async def _dispatch_strategy_build(
    ws_manager: Any, channel: str, params: dict
) -> None:
    from app.api.strategy import AIStrategyGenerator, BuildRequest, _build_prompt

    meta = {
        "strategy_id": params.get("strategy_id"),
        "step": params.get("step", 1),
        "name": params.get("name"),
        "description": params.get("description"),
    }
    await _broadcast(ws_manager, channel, "analysis_meta", meta)
    gen = AIStrategyGenerator()
    chunks: list[str] = []
    try:
        req = BuildRequest(**{
            "step": int(params.get("step", 1)),
            "name": params.get("name") or "",
            "description": params.get("description") or "",
            "direction": params.get("direction") or "long",
            "rules": params.get("rules") or "",
            "strategy_id": params.get("strategy_id") or "",
            "execution_backend": params.get("execution_backend") or "polars_expr",
            "current_code": params.get("current_code") or "",
            "instruction": params.get("instruction") or "",
        })
        prompt = _build_prompt(req)
        async for chunk in gen.stream(prompt):
            chunks.append(chunk)
            await _broadcast(ws_manager, channel, "analysis_delta", {"content": chunk})
        result = gen.validate_code("".join(chunks))
        if gen.needs_structural_repair(result):
            result = await gen.repair_code(result["code"], result["error"])
        await _broadcast(ws_manager, channel, "analysis_done", {"result": result})
    except RuntimeError as exc:
        await _broadcast(ws_manager, channel, "analysis_error", {"reason": str(exc)})
    except Exception as exc:  # noqa: BLE001
        await _broadcast(ws_manager, channel, "analysis_error", {"reason": f"AI生成失败: {exc}"})


# ── review — market_recap / rps rotation ──────────────────────────────────

async def _dispatch_review(
    ws_manager: Any, channel: str, params: dict, app_state: Any
) -> None:
    kind = params.get("kind") or "concept"
    focus = params.get("focus") or ""
    days = params.get("days") or 12
    level = params.get("level")
    as_of = params.get("as_of")
    source = params.get("source") or ""

    if kind in ("industry", "rps") or source == "rps":
        # rps 端点 kind 归一化: concept/industry 传给分析器 (rps 是路由语义)
        stream_kind = "industry" if kind == "industry" else "concept"
        await _dispatch_rps(ws_manager, channel, days, focus, stream_kind, level, app_state)
        return

    # 默认: 大盘复盘 (kind=concept/market_recap)
    await _dispatch_market_recap(ws_manager, channel, as_of, focus, app_state)


async def _dispatch_rps(
    ws_manager: Any, channel: str, days: int, focus: str, kind: str, level: Any, app_state: Any
) -> None:
    from app.api.rps import analyze_rotation_stream

    repo = _repo(app_state)
    quote_service = getattr(app_state, "quote_service", None)
    depth_service = getattr(app_state, "depth_service", None)
    clamped_days = max(7, min(30, int(days)))
    await _broadcast(ws_manager, channel, "review_meta", {"days": clamped_days, "kind": kind})
    try:
        async for chunk in analyze_rotation_stream(
            repo, clamped_days, focus, quote_service, depth_service, kind, level,
        ):
            await _broadcast(ws_manager, channel, "review_delta", {"content": chunk})
        await _broadcast(ws_manager, channel, "review_done", {})
    except Exception as exc:  # noqa: BLE001
        await _broadcast(ws_manager, channel, "review_error", {"reason": str(exc)})


async def _dispatch_market_recap(
    ws_manager: Any, channel: str, as_of: Any, focus: str, app_state: Any
) -> None:
    from app.api.market_recap import recap_market_stream

    repo = _repo(app_state)
    quote_service = getattr(app_state, "quote_service", None)
    depth_service = getattr(app_state, "depth_service", None)
    parsed_as_of = None
    if as_of:
        try:
            parsed_as_of = date_cls.fromisoformat(str(as_of))
        except ValueError:
            await _broadcast(ws_manager, channel, "review_error", {"reason": f"as_of 格式应为 YYYY-MM-DD,收到: {as_of}"})
            return
    await _broadcast(ws_manager, channel, "review_meta", {"as_of": as_of})
    try:
        async for chunk in recap_market_stream(repo, quote_service, depth_service, parsed_as_of, focus):
            await _broadcast(ws_manager, channel, "review_delta", {"content": chunk})
        await _broadcast(ws_manager, channel, "review_done", {})
    except Exception as exc:  # noqa: BLE001
        await _broadcast(ws_manager, channel, "review_error", {"reason": str(exc)})


async def _broadcast(ws_manager: Any, channel: str, msg_type: str, data: dict) -> None:
    """通过 ws_manager 广播到频道 (async 上下文内直接 await)。"""
    await ws_manager.broadcast_to_channel(channel, msg_type, data)
