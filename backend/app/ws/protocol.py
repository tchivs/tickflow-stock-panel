"""WebSocket 消息协议常量与工厂。

D-05: 消息格式 JSON {type: string, seq: number, data: object}
D-06: 环形缓冲区 1000 条
D-08: 频道命名: quotes, alerts, portfolio, run:{run_id}, analysis:{symbol}, review, depth
D-12 修正: 应用层 keepalive (Starlette WebSocket 无内置 ping_interval)
"""
from __future__ import annotations

# ── 客户端 → 服务端 消息类型 ────────────────────────────────────
CLIENT_MSG_TYPES = frozenset({"subscribe", "unsubscribe", "resume", "request"})

# ── 服务端 → 客户端 事件类型 ────────────────────────────────────
SERVER_EVENT_TYPES = frozenset({
    "connected",
    "subscribed",
    "unsubscribed",
    "resumed",
    "ping",
    "quotes_updated",
    "strategy_alert",
    "portfolio_updated",
    "depth_updated",
    "review_progress",
    "analysis_progress",
    "advanced_progress",
    "strategy_results_updated",
    "job_progress",
    "job_done",
    "job_error",
    "analysis_meta",
    "analysis_delta",
    "analysis_done",
    "error",
})

# ── 频道名 (D-08) ──────────────────────────────────────────────
CHANNEL_QUOTES = "quotes"
CHANNEL_ALERTS = "alerts"
CHANNEL_PORTFOLIO = "portfolio"
CHANNEL_REVIEW = "review"
CHANNEL_DEPTH = "depth"

# 动态频道前缀
RUN_PREFIX = "run:"
ANALYSIS_PREFIX = "analysis:"

# 静态频道集合 (用于快速校验; 动态频道用前缀匹配)
STATIC_CHANNELS = frozenset({
    CHANNEL_QUOTES,
    CHANNEL_ALERTS,
    CHANNEL_PORTFOLIO,
    CHANNEL_REVIEW,
    CHANNEL_DEPTH,
})

# ── 协议常量 ────────────────────────────────────────────────────
RING_SIZE = 1000  # D-06: 每连接环形缓冲区容量
MAX_CHANNELS_PER_CONNECTION = 50  # T-55-04: DoS 防护
KEEPALIVE_INTERVAL = 30.0  # D-12 修正: 应用层 keepalive 间隔 (秒)


def make_msg(msg_type: str, seq: int, data: dict) -> dict:
    """构造 WS 消息: {type, seq, data}。"""
    return {"type": msg_type, "seq": seq, "data": data}
