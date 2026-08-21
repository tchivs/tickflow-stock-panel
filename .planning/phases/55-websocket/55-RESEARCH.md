# Phase 55: WebSocket 全量迁移 - Research

**Researched:** 2026-08-21
**Domain:** WebSocket 双向通信 / SSE → WS 迁移 / FastAPI WebSocket 端点
**Confidence:** HIGH

## Summary

Phase 55 将 AthenaQuant 后端从单向 SSE 轮询升级为 WebSocket 双向通信。当前代码库有 **8 处后端 SSE 端点** (EventSourceResponse + StreamingResponse text/event-stream) + **5 处 ndjson StreamingResponse** (POST 请求 + application/x-ndjson) + **7 处前端 EventSource 消费者** + **5 处前端 ndjson ReadableStream 消费者** 需要一次性全部迁移到 WebSocket 传输。

核心发现: Starlette 1.0.1 / FastAPI 0.136.1 的 WebSocket 实现没有内置 `ping_interval` 支持 (与 `websockets` 库不同), 因此 D-12 决策 (用 websockets 库 ping_interval) 需要调整 — 服务端 WS 端点必须实现**应用层 keepalive** 或使用 uvicorn 的 ASGI WebSocket 超时机制。现有 `stockdb_ws.py` 和 `wecom_bot_service.py` 提供了成熟的 WS 客户端重连模式可直接参考。`QuoteService` 的 `subscribe/unsubscribe + broadcast` 模式可适配为 WS 连接管理器的基础。

**Primary recommendation:** 新建 `backend/app/ws/` 模块 (connection_manager.py + protocol.py + handler.py), 复用 QuoteService 广播模式实现 WS 连接管理器; 前端新建 `useWsStream` hook 替代全部 EventSource, 全局单连接 + 频道订阅 + seq resume。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: 真正同时全量迁移 — 8 处后端 SSE 端点 + 4 处 ndjson StreamingResponse + 7 处前端 EventSource 在同一个 Phase 55 内一次性全部迁移到 WebSocket, 不分批次, 没有并行期, 不保留旧 SSE 端点
- D-02: ndjson 流也迁移到 WebSocket — POST 请求 StreamingResponse 迁移到 WS 频道订阅 + 流式推送
- D-03: 无回退路径 — 迁移后删除所有 SSE 代码
- D-04: TDD — 先写 WebSocket 版本测试, 再迁移代码, 再跑 e2e
- D-05: 消息格式 JSON {type: string, seq: number, data: object}
- D-06: 断连恢复用 seq 窗口 — 服务端内存环形缓冲区 (1000 条), 客户端 resume 消息重放
- D-07: 客户端 subscribe/unsubscribe 频道
- D-08: 频道命名: quotes, alerts, portfolio, run:{run_id}, analysis:{symbol}, review, depth
- D-09: 前端全局单连接 — 整个前端只开一个 WebSocket 连接
- D-10: QuoteSubscriber/QuoteService 可作 WS 连接管理参考
- D-11: Cookie session 鉴权 — 复用现有 SSE Cookie session
- D-12: 协议层 ping 心跳 — websockets 库 ping_interval
- D-13: 客户端断连后指数退避重连 1s→2s→4s→8s→16s→30s

### Claude's Discretion
- 环形缓冲区实现细节 (deque vs list, 淘汰策略) — 由 planner/researcher 决定
- WebSocket 端点路由注册位置 (main.py vs 新 ws 模块) — 由 planner 决定, 参考 bootstrap.py + security_middleware.py 拆分模式
- ndjson 流迁移后的频道设计细节 (是否需要 request 消息触发流式推送) — 由 researcher 调研

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WS-01 | 服务端 WebSocket 端点 (`/ws/stream`) 支持多客户端连接, 按 principal 鉴权 | FastAPI `@app.websocket` + ConnectionManager pattern; Cookie session 从 `websocket.cookies.get("tf_session")` 提取, 复用 `auth.is_valid_session` + `auth.resolve_authenticated_reviewer` |
| WS-02 | 现有 SSE 流全部迁移到 WebSocket 传输, 保留 Last-Event-ID 语义 | seq 环形缓冲区 (deque(maxlen=1000)) + resume 消息; 每个连接维护独立 seq, 重连时从 N+1 重放 |
| WS-03 | WebSocket 连接复用 — 多个实时流共享同一连接, 通过消息类型路由 | subscribe/unsubscribe 频道机制; per-connection channel set; 服务端只推已订阅频道的事件 |
| WS-04 | WebSocket 连接心跳与自动重连 | Starlette WS 无内置 ping_interval — 需应用层 keepalive (asyncio sleep + send ping); 客户端指数退避 1s→30s |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| WS 端点 + 连接管理 | API / Backend | — | FastAPI `@app.websocket` 运行在服务端, 管理多客户端连接生命周期 |
| Cookie session 鉴权 | API / Backend | — | WS 握手时从 Cookie 提取 `tf_session`, 复用 `auth.is_valid_session` |
| 消息路由 (频道订阅) | API / Backend | — | 服务端维护 per-connection channel set, 按 `type` 路由推送 |
| seq 环形缓冲区 | API / Backend | — | 服务端内存 deque(maxlen=1000), 每连接独立 seq 计数器 |
| 全局单连接管理 | Browser / Client | — | 前端 React hook 管理全局 WS 连接 + 频道订阅/退订 |
| 指数退避重连 | Browser / Client | — | 客户端 1s→2s→4s→8s→16s→30s 指数退避, 重连后发 resume |
| 连接状态 UI | Browser / Client | — | connected/reconnecting/disconnected 状态对用户可见 |
| 连接生命周期审计 | API / Backend | — | ToolCallEnvelope (scope=ws) 记录连接/断连/重连 |
| 心跳保活 | API / Backend | Browser / Client | 服务端应用层 keepalive; 客户端检测连接断开后触发重连 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.136.1 | WebSocket 端点定义 (`@app.websocket`) | 项目已用; 内置 WebSocket + WebSocketDisconnect [VERIFIED: backend/uv.lock:714-715] |
| Starlette | 1.0.1 | WebSocket 类 + ASGI 传输 | FastAPI 底层依赖; WebSocket.accept/send_json/receive_json [VERIFIED: backend/uv.lock:3445-3446] |
| websockets | 15.0.1 | WS 客户端 (stockdb_ws/wecom) | 已为传递依赖; 仅供参考, 不直接用于服务端 [VERIFIED: backend/uv.lock:3957-3959] |
| uvicorn | 0.47.0 | ASGI 服务器, WS 传输层 | 项目已用 [VERIFIED: backend/uv.lock:3756-3757] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sse-starlette | 3.4.4 | (待删除) 旧 SSE 端点依赖 | 迁移完成后从 pyproject.toml 移除 [VERIFIED: backend/uv.lock:3417-3419] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Starlette WebSocket | websockets 库服务端 | Starlette WebSocket 已集成 FastAPI; websockets 库主要用于客户端场景 (stockdb_ws/wecom); 服务端用 Starlette 即可 |
| 应用层 keepalive | uvicorn `--ws-ping-interval` | uvicorn 0.47 可能不支持 WS ping interval 参数; 需验证; 应用层 keepalive 更可控 |

**Installation:**
```bash
# 无需安装新依赖 — FastAPI + Starlette 已包含 WebSocket 支持
# 迁移完成后移除 sse-starlette:
# uv remove sse-starlette
```

**Version verification:**
```bash
# 已从 uv.lock 验证:
# fastapi==0.136.1, starlette==1.0.1, websockets==15.0.1, uvicorn==0.47.0
# sse-starlette==3.4.4 (待删除)
```

## Package Legitimacy Audit

> 本 phase 不安装任何新外部包。所有依赖 (FastAPI, Starlette, websockets, uvicorn) 已在项目中。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| fastapi | PyPI | ~7 yrs | 50M+/mo | github.com/fastapi/fastapi | OK | Pre-existing |
| starlette | PyPI | ~7 yrs | 50M+/mo | github.com/encode/starlette | OK | Pre-existing |
| websockets | PyPI | ~10 yrs | 30M+/mo | github.com/python-websockets/websockets | OK | Pre-existing (transitive) |
| sse-starlette | PyPI | ~4 yrs | 5M+/mo | github.com/sysid/sse-starlette | OK | Pre-existing (to be removed) |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Browser (Single Tab)                             │
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │ useQuoteStream│  │ backtestTask │  │ miningTask   │  │ AlphaWorkbench│     │
│  │ (quotes/alerts)│  │ (run:xxx)   │  │ (run:xxx)   │  │ (run:xxx)   │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
│         │                │                │                │             │
│         └────────────────┴────────────────┴────────────────┘             │
│                              │                                           │
│                    ┌─────────▼──────────┐                                │
│                    │  useWsStream (global)│                                │
│                    │  single WS connection │                                │
│                    │  + channel subscribe  │                                │
│                    │  + seq resume         │                                │
│                    │  + exp backoff recon  │                                │
│                    └─────────┬──────────┘                                │
│                              │                                           │
│                    ws://host/ws/stream                                    │
└──────────────────────────────┼───────────────────────────────────────────┘
                               │
┌──────────────────────────────┼───────────────────────────────────────────┐
│                    FastAPI Server                                           │
│                    ┌─────────▼──────────┐                                   │
│                    │ @app.websocket       │                                   │
│                    │ /ws/stream           │                                   │
│                    └─────────┬──────────┘                                   │
│                              │                                           │
│                    ┌─────────▼──────────┐                                   │
│                    │ ConnectionManager     │                                   │
│                    │ active_connections:  │                                   │
│                    │   list[WsConnection]  │                                   │
│                    └─────────┬──────────┘                                   │
│              ┌───────────────┼───────────────┐                              │
│              │               │               │                              │
│    ┌─────────▼──┐  ┌────────▼───┐  ┌────────▼───┐  ┌──────────────────┐   │
│    │ WsConnection │  │ WsConnection │  │ WsConnection │  │ WsConnection      │   │
│    │ channels: set │  │ channels: set │  │ channels: set │  │ channels: set     │   │
│    │ seq: int      │  │ seq: int      │  │ seq: int      │  │ seq: int          │   │
│    │ ring: deque   │  │ ring: deque   │  │ ring: deque   │  │ ring: deque       │   │
│    └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────┘   │
│              │                                                │          │
│    ┌─────────▼────────────────────────────────────────────────▼──────┐         │
│    │ Event Broadcast Layer                                            │         │
│    │ QuoteService.broadcast → all conns subscribed to 'quotes'        │         │
│    │ JobManager.broadcast  → conns subscribed to 'run:{id}'           │         │
│    │ AnalysisHub.broadcast → conns subscribed to 'analysis:{symbol}' │         │
│    └─────────────────────────────────────────────────────────────────┘         │
│                                                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │Cookie Auth   │  │Audit Logger  │  │Channel Router│  │ Seq Buffer   │    │
│  │tf_session    │  │ToolCallEnv   │  │by type field │  │deque(1000)   │    │
│  │→principal    │  │scope=ws      │  │→channel set  │  │→resume N+1   │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/app/
├── ws/                          # NEW: WebSocket module
│   ├── __init__.py
│   ├── connection_manager.py    # ConnectionManager + WsConnection
│   ├── protocol.py              # Message types, seq, ring buffer
│   ├── handler.py               # /ws/stream endpoint handler
│   └── channels.py              # Channel → event source mapping
├── api/                         # SSE endpoints → removed/delegated to WS
│   ├── intraday.py              # /stream SSE → deleted, QuoteService → WS broadcast
│   ├── mining.py                # /events SSE → deleted, store events → WS channel
│   ├── research_alpha_sse.py    # /stream SSE → deleted, run events → WS channel
│   ├── walkforward_sse.py       # /stream SSE → deleted, job events → WS channel
│   ├── backtest.py              # 3 SSE endpoints → deleted, job events → WS channel
│   ├── financials.py            # ndjson → deleted, LLM stream → WS channel
│   ├── market_recap.py          # ndjson → deleted, LLM stream → WS channel
│   ├── rps.py                   # ndjson → deleted, LLM stream → WS channel
│   ├── stock_analysis.py        # ndjson → deleted, LLM stream → WS channel
│   ├── strategy.py              # ndjson build/stream → deleted, LLM stream → WS
│   └── forecast/api.py          # SSE events → deleted, job events → WS channel
└── main.py                      # app.include_router → WS endpoint registration

frontend/src/
├── lib/
│   ├── useWsStream.ts           # NEW: global WS hook (replaces useQuoteStream)
│   ├── wsProtocol.ts            # NEW: message types, seq, subscribe/unsubscribe
│   ├── api.ts                   # ndjson consumers → WS channel send/receive
│   ├── backtestTask.ts          # EventSource → WS channel subscribe
│   ├── optimizerTask.ts         # EventSource → WS channel subscribe
│   ├── walkforwardTask.ts       # EventSource → WS channel subscribe
│   ├── miningTask.ts            # EventSource → WS channel subscribe
│   ├── forecastTask.ts          # fetch SSE → WS channel subscribe
│   └── queryKeys.ts             # SSE_INVALIDATE_PREFIXES → WS_INVALIDATE_PREFIXES
├── pages/backtest/
│   ├── AlphaWorkbench.tsx       # EventSource → WS channel subscribe
│   └── WalkForward.tsx          # EventSource → WS channel subscribe
└── components/
    └── Layout.tsx               # useQuoteStream → useWsStream
```

### Pattern 1: ConnectionManager (多客户端连接管理)
**What:** 内存管理所有活跃 WS 连接, 每连接维护频道订阅集 + seq + 环形缓冲区
**When to use:** 替代 QuoteService 的 `subscribe/unsubscribe + broadcast` 模式
**Example:**
```python
# Source: FastAPI WebSocket docs [CITED: fastapi.tiangolo.com/advanced/websockets]
# Adapted from ConnectionManager pattern + QuoteService subscribe/unsubscribe

from collections import deque
from fastapi import WebSocket, WebSocketDisconnect

class WsConnection:
    """一个 WS 连接的状态: 频道订阅 + seq + 环形缓冲区。"""
    def __init__(self, ws: WebSocket, principal: str):
        self.ws = ws
        self.principal = principal
        self.channels: set[str] = set()
        self.seq: int = 0
        self._ring: deque[dict] = deque(maxlen=1000)  # D-06: 1000 条环形缓冲

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def push_to_ring(self, msg: dict) -> None:
        """推入环形缓冲区 (溢出自动淘汰最旧)。"""
        self._ring.append(msg)

    def replay_after(self, last_seq: int) -> list[dict]:
        """重放 seq > last_seq 的消息。"""
        return [m for m in self._ring if m.get("seq", 0) > last_seq]

class ConnectionManager:
    def __init__(self):
        self._connections: list[WsConnection] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, principal: str) -> WsConnection:
        await ws.accept()
        conn = WsConnection(ws, principal)
        self._connections.append(conn)
        return conn

    def disconnect(self, conn: WsConnection):
        self._connections.remove(conn)

    async def broadcast_to_channel(self, channel: str, msg_type: str, data: dict):
        """只推送给订阅了指定频道的连接。"""
        for conn in list(self._connections):
            if channel in conn.channels:
                seq = conn.next_seq()
                msg = {"type": msg_type, "seq": seq, "data": data}
                conn.push_to_ring(msg)
                try:
                    await conn.ws.send_json(msg)
                except Exception:
                    pass  # 连接断开, 由 handler 清理
```

### Pattern 2: Cookie Session 鉴权 (WS 握手)
**What:** 从 WebSocket 握手时的 Cookie 提取 session token, 复用现有 auth 逻辑
**When to use:** `/ws/stream` 端点鉴权
**Example:**
```python
# Source: Starlette WebSocket docs [CITED: starlette docs/websockets.md]
# + app/api/auth.py COOKIE_NAME = "tf_session" [VERIFIED: backend/app/api/auth.py:32]
# + app/services/auth.py is_valid_session/resolve_authenticated_reviewer [VERIFIED: backend/app/services/auth.py:181-209]

from app.api.auth import COOKIE_NAME
from app.services import auth

@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket):
    # WS 握手时浏览器自动携带 Cookie
    token = websocket.cookies.get(COOKIE_NAME)  # "tf_session"
    if not token or not auth.is_valid_session(token):
        await websocket.close(code=4001, reason="未登录或会话已过期")
        return
    principal = auth.resolve_authenticated_reviewer(token)
    if not principal:
        await websocket.close(code=4001, reason="principal 解析失败")
        return
    # 鉴权通过, 进入连接处理循环
    conn = await manager.connect(websocket, principal)
    try:
        await _handle_connection(conn)
    except WebSocketDisconnect:
        manager.disconnect(conn)
```

### Pattern 3: 消息协议 + 频道订阅
**What:** `{type, seq, data}` 消息格式 + subscribe/unsubscribe/resume 消息
**When to use:** 客户端 → 服务端 (subscribe/unsubscribe/resume); 服务端 → 客户端 (事件推送)
**Example:**
```python
# D-05: 消息格式 JSON {type: string, seq: number, data: object}
# D-07: 客户端 subscribe/unsubscribe 频道
# D-08: 频道命名: quotes, alerts, portfolio, run:{run_id}, analysis:{symbol}, review, depth

async def _handle_connection(conn: WsConnection):
    while True:
        msg = await conn.ws.receive_json()
        msg_type = msg.get("type")
        if msg_type == "subscribe":
            channels = msg.get("channels", [])
            conn.channels.update(channels)
            # 确认订阅
            await conn.ws.send_json({"type": "subscribed", "seq": 0, "data": {"channels": list(conn.channels)}})
        elif msg_type == "unsubscribe":
            channels = msg.get("channels", [])
            conn.channels.difference_update(channels)
            await conn.ws.send_json({"type": "unsubscribed", "seq": 0, "data": {"channels": list(conn.channels)}})
        elif msg_type == "resume":
            last_seq = msg.get("last_seq", 0)
            # D-06: 从环形缓冲区重放 seq > last_seq 的消息
            replay = conn.replay_after(last_seq)
            for m in replay:
                await conn.ws.send_json(m)
            await conn.ws.send_json({"type": "resumed", "seq": 0, "data": {"replayed": len(replay)}})
```

### Pattern 4: 客户端全局单连接 Hook
**What:** React hook 管理全局唯一 WS 连接, 多组件通过频道订阅共享
**When to use:** 替代 useQuoteStream + backtestTask + optimizerTask 等各自的 EventSource
**Example:**
```typescript
// D-09: 前端全局单连接
// D-13: 指数退避重连 1s→2s→4s→8s→16s→30s
// 参考: useQuoteStream.ts 的连接状态管理模式 [VERIFIED: frontend/src/lib/useQuoteStream.ts:41-78]

let _ws: WebSocket | null = null
let _seq = 0
const _channelHandlers = new Map<string, Set<(data: any) => void>>()
const BACKOFF_STEPS = [1000, 2000, 4000, 8000, 16000, 30000]

function _connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/stream`)
  _ws = ws
  ws.onopen = () => {
    _setStatus('connected')
    // 重连后发送 resume
    if (_seq > 0) {
      ws.send(JSON.stringify({type: 'resume', last_seq: _seq}))
    }
    // 重订阅所有频道
    const channels = Array.from(_channelHandlers.keys())
    if (channels.length > 0) {
      ws.send(JSON.stringify({type: 'subscribe', channels}))
    }
  }
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (typeof msg.seq === 'number' && msg.seq > _seq) _seq = msg.seq
    // 按 type 路由到 handler
    for (const [ch, handlers] of _channelHandlers) {
      if (msg.type.startsWith(ch) || msg.type === ch) {
        handlers.forEach(fn => fn(msg.data))
      }
    }
  }
  ws.onclose = () => {
    _setStatus('reconnecting')
    _scheduleReconnect()
  }
}
```

### Anti-Patterns to Avoid
- **per-stream 独立 WS 连接:** D-09 明确要求全局单连接; 不要为每个流新建 WS 连接
- **服务端用 websockets 库而非 Starlette:** FastAPI 集成的 WS 端点用 Starlette WebSocket; websockets 库用于客户端 (stockdb_ws)
- **依赖 Starlette 内置 ping_interval:** Starlette 1.0.1 WebSocket **没有** ping_interval 参数; 必须应用层 keepalive
- **seq 全局递增:** seq 应为 per-connection 递增, 不同连接的 seq 独立; 环形缓冲区也 per-connection
- **ndjson 流保留 POST 端点:** D-02 要求 ndjson 也迁移到 WS; 不要保留 POST StreamingResponse 端点

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WS 连接管理 | 手写连接列表 + 广播 | ConnectionManager pattern (FastAPI 官方) | 官方推荐的 ConnectionManager 模式 [CITED: fastapi.tiangolo.com/advanced/websockets] |
| 重连/退避逻辑 | 手写重连计时器 | 参考 stockdb_ws.py `_run` 循环 | 已验证的指数退避 + resume + 重订阅模式 [VERIFIED: backend/app/services/stockdb_ws.py:157-186] |
| 连接状态管理 | 手写状态 store | 参考 useQuoteStream `_statusListeners` | 已验证的 `useSyncExternalStore` 模式 [VERIFIED: frontend/src/lib/useQuoteStream.ts:41-78] |
| Cookie session 鉴权 | 手写 WS 鉴权 | 复用 `auth.is_valid_session` + `resolve_authenticated_reviewer` | 现有 SSE 鉴权逻辑 [VERIFIED: backend/app/api/security_middleware.py:93-98] |
| 审计记录 | 手写日志 | 复用 `AuditContext` + `ToolCallAuditRepository` | Phase 52 审计 seam [VERIFIED: backend/app/audit/envelope.py:364-442] |
| 行情广播 | 手写广播逻辑 | 适配 QuoteService `_broadcast_*` 方法 | 已验证的订阅者广播模式 [VERIFIED: backend/app/services/quote_service.py:461-493] |

**Key insight:** 现有 QuoteService 的 `subscribe/unsubscribe + _broadcast_*` 模式就是 pub/sub 连接管理器的雏形; stockdb_ws.py 的 `_run` 重连循环就是客户端重连的参考实现。迁移的本质是把 QuoteSubscriber (threading.Event + list) 换成 WsConnection (WebSocket + deque), 把 SSE event 字段换成 WS message type 字段。

## Common Pitfalls

### Pitfall 1: Starlette WebSocket 没有 ping_interval
**What goes wrong:** D-12 决策说用 "websockets 库 ping_interval", 但 Starlette/FastAPI 的 `@app.websocket` 端点不支持 `ping_interval` 参数 — 它是 `websockets` 库 `connect()` 的客户端参数。
**Why it happens:** D-12 混淆了服务端和客户端 — `websockets` 库的 `ping_interval` 是在客户端 `websockets.connect()` 中设置的 (如 stockdb_ws.py:168 `ping_interval=20`); FastAPI 服务端 WebSocket 没有 API 设置协议层 ping。
**How to avoid:** 服务端实现**应用层 keepalive**: `asyncio.sleep(30)` + `websocket.send_json({"type":"ping"})`; 或研究 uvicorn 是否支持 `--ws-ping-interval` 参数。客户端仍可依赖浏览器 WebSocket 的协议层 ping (由浏览器自动处理)。
**Warning signs:** 连接长时间无消息后被代理/防火墙断开; 空闲连接超时。

### Pitfall 2: seq 作用域设计错误
**What goes wrong:** 如果 seq 是全局递增的, 不同连接 resume 时会得到不属于自己的消息; 如果 seq 是 per-channel 的, 跨频道消息的 seq 会重复。
**Why it happens:** seq 作用域不明确。
**How to avoid:** seq **per-connection** 递增 — 每个连接维护独立的 seq 计数器, 环形缓冲区也是 per-connection。服务端推送任何消息时, 对每个订阅了该频道的连接独立递增其 seq。
**Warning signs:** 重连后收到重复消息或丢失消息; seq 不连续。

### Pitfall 3: ndjson POST 流的请求参数传递
**What goes wrong:** ndjson 流 (financials/analyze, market_recap/analyze 等) 是 POST 请求带 body 参数的; WS 频道订阅只有频道名, 没有请求参数。
**Why it happens:** SSE/ndjson 端点是请求-响应模式 (POST + stream response); WS 是订阅-推送模式 (subscribe + receive)。
**How to avoid:** 设计 `request` 消息类型: 客户端先发 `{type: "request", channel: "analysis:{symbol}", params: {focus: "..."}}` 触发后端启动 LLM 流式生成, 后端通过同一频道推送 delta/done 消息。参考 D-08 频道命名 `analysis:{symbol}`。
**Warning signs:** 无法传递分析参数 (focus, days, kind 等); 后端不知道要分析什么。

### Pitfall 4: 多标签页/多设备广播语义变化
**What goes wrong:** SSE 时每个标签页各自建立 EventSource 连接, 各自收到全量事件; WS 全局单连接模式下, 多标签页共享一个连接, 但每个标签页可能只想订阅不同频道。
**Why it happens:** D-09 "前端全局单连接" 是指**整个浏览器标签页**内只有一个 WS 连接, 不是跨标签页共享。不同标签页各自建立自己的 WS 连接, 服务端多客户端广播不受影响。
**How to avoid:** 明确 D-09 语义: 每个浏览器标签页 (页面) 内部只有一个 WS 连接 (不是 7 个 EventSource), 但多个标签页各自有独立的 WS 连接。服务端 ConnectionManager 管理所有标签页的连接。
**Warning signs:** 不同标签页看到相同的频道订阅集; 一个标签页取消订阅影响另一个。

### Pitfall 5: backtestTask/optimizerTask 的 job_key + cancel 机制
**What goes wrong:** 当前 backtest/optimizer/walkforward SSE 流通过 job_key 关联任务, cancel 通过 POST 请求 cancel。迁移到 WS 后, job_key 机制需要适配。
**Why it happens:** SSE 端点首事件回吐 job_key, 前端存 localStorage 供 cancel 使用。WS 模式下频道 `run:{run_id}` 的 run_id 就是 job_key 等价物。
**How to avoid:** WS 模式: 客户端订阅 `run:{job_key}` 频道, 首个消息包含 job_key (等价 SSE job 事件); cancel 仍通过 POST 请求 (cancel 端点保留, 只迁移 stream 端点)。
**Warning signs:** cancel 请求找不到任务; 刷新后无法重连到同一任务。

### Pitfall 6: test_phase50_guard.py 依赖 sse-starlette
**What goes wrong:** `backend/tests/test_phase50_guard.py` 有断言检查 sse-starlette 在依赖基线中。删除 sse-starlette 会导致该测试失败。
**Why it happens:** Phase 50 的 release guard 把 sse-starlette 列为 pre-existing 依赖基线 [VERIFIED: backend/tests/test_phase50_guard.py:535-560]。
**How to avoid:** 迁移完成后更新 test_phase50_guard.py 的 `_DEPENDENCY_BASELINE`, 移除 `"sse-starlette>=2.0"`; 同时更新相关的 SSE/EventSourceResponse 断言。
**Warning signs:** test_phase50_guard.py 失败。

## Code Examples

### FastAPI WebSocket 端点 + TestClient 测试
```python
# Source: FastAPI WebSocket docs [CITED: fastapi.tiangolo.com/advanced/testing-websockets]
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.testclient import TestClient

app = FastAPI()

@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "connected", "seq": 0, "data": {}})
    try:
        while True:
            data = await websocket.receive_json()
            await websocket.send_json({"type": "echo", "seq": 1, "data": data})
    except WebSocketDisconnect:
        pass

def test_ws_connect():
    client = TestClient(app)
    with client.websocket_connect("/ws/stream") as ws:
        data = ws.receive_json()
        assert data["type"] == "connected"
        ws.send_json({"type": "subscribe", "channels": ["quotes"]})
        echo = ws.receive_json()
        assert echo["type"] == "echo"
```

### 环形缓冲区实现 (deque)
```python
# D-06: 服务端内存环形缓冲区 (1000 条)
# deque(maxlen=N) 自动淘汰最旧元素, 是 Python 标准库的环形缓冲区实现
from collections import deque

ring = deque(maxlen=1000)  # 溢出时自动丢弃最旧元素

# 推入消息
ring.append({"type": "quotes_updated", "seq": 42, "data": {"ts": 1234}})

# 重放 seq > N 的消息
last_seq = 40
replay = [m for m in ring if m.get("seq", 0) > last_seq]
# → [{"type": "quotes_updated", "seq": 42, "data": {"ts": 1234}}]
```

### 应用层 Keepalive (替代 ping_interval)
```python
# D-12 的修正: Starlette WebSocket 无内置 ping_interval
# 实现应用层 keepalive — 服务端定时发送 ping 消息
import asyncio

async def _keepalive(conn: WsConnection, interval: float = 30.0):
    """服务端应用层心跳: 每 interval 秒发一次 ping 消息。"""
    while True:
        await asyncio.sleep(interval)
        try:
            seq = conn.next_seq()
            await conn.ws.send_json({"type": "ping", "seq": seq, "data": {}})
        except Exception:
            break  # 连接断开, 退出心跳
```

### 审计集成 (ToolCallEnvelope scope=ws)
```python
# 复用 Phase 52 审计 seam [VERIFIED: backend/app/audit/envelope.py:364-442]
from app.audit.service import get_audit_repo
from app.audit.envelope import AuditContext

async def _handle_connection(conn: WsConnection):
    repo = get_audit_repo()
    if repo is not None:
        with AuditContext(repo, tool="connection", category="external",
                          params={"channels": list(conn.channels)},
                          scope="ws", principal=conn.principal) as audit:
            try:
                await _message_loop(conn)
                audit.set_response(shape="ws", summary="connection closed normally")
            except WebSocketDisconnect:
                audit.set_response(shape="ws", summary="client disconnected")
    else:
        await _message_loop(conn)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSE (EventSourceResponse) | WebSocket (Starlette WebSocket) | Phase 55 | 双向通信; 服务端可主动推送; 需手写连接管理 |
| Last-Event-ID header | seq + resume 消息 | Phase 55 | 客户端主动发 resume, 而非浏览器自动带 header |
| sse-starlette 依赖 | 移除 | Phase 55 | 减少依赖; 但需确保 test_phase50_guard 更新 |
| per-stream EventSource | 全局单 WS 连接 + 频道订阅 | Phase 55 | 连接数从 7→1 (per tab); 多路复用通过 type 路由 |
| POST + ndjson StreamingResponse | WS 频道 request + 流式推送 | Phase 55 | 请求参数通过 WS 消息传递; 响应通过同一频道推送 |

**Deprecated/outdated:**
- sse-starlette EventSourceResponse: 迁移后完全移除 [VERIFIED: backend/pyproject.toml:15]
- StreamingResponse text/event-stream: 3 处 backtest SSE + walkforward SSE + forecast SSE 迁移后删除
- StreamingResponse application/x-ndjson: 5 处 ndjson 流迁移后删除
- Last-Event-ID header: 被 seq + resume 消息替代
- EventSource (前端): 被 WebSocket 替代

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Starlette 1.0.1 WebSocket 不支持 `ping_interval` 参数 | Pitfalls / Code Examples | 如支持则可简化 keepalive; 但 Context7 文档未提及该参数, websockets 库的 ping_interval 是客户端参数 |
| A2 | uvicorn 0.47.0 可能支持 `--ws-ping-interval` 参数 | Pitfalls | 如不支持则必须应用层 keepalive; 需在实现阶段验证 |
| A3 | 浏览器 WebSocket 会自动处理协议层 ping/pong (TCP keepalive) | Pitfalls | 如浏览器不自动 ping, 长空闲连接可能被代理断开; 应用层 ping 可兜底 |
| A4 | ndjson 流可通过 `request` 消息 + 频道推送实现等价语义 | Architecture Patterns | 如 LLM 流式生成需要 HTTP 流式响应的背压机制, WS 模式可能需要额外流控 |
| A5 | strategy.py /build/stream 也需迁移 (未在 CONTEXT.md 中列出) | Migration Scope | 如遗漏该端点, 会残留 ndjson 代码; 已在本研究中补充 |
| A6 | forecast/api.py 路径在 backend/app/forecast/ 而非 backend/app/api/forecast/ | Migration Scope | 如路径理解错误, 迁移时遗漏 forecast SSE 端点 |

## Open Questions

1. **uvicorn WebSocket ping interval 支持**
   - What we know: Starlette WebSocket API 没有 `ping_interval` 参数 [CITED: starlette docs/websockets.md]
   - What's unclear: uvicorn 0.47.0 是否支持 `--ws-ping-interval` 命令行参数或 ASGI 配置
   - Recommendation: 实现阶段验证 `uvicorn --help | grep ping`; 如不支持则用应用层 keepalive

2. **ndjson 流的频道设计细节 (Claude's Discretion)**
   - What we know: ndjson 是 POST 请求 + 流式响应; WS 是订阅 + 推送
   - What's unclear: 是否需要 `request` 消息触发流式推送, 还是纯订阅 + 后端自动触发
   - Recommendation: 用 `request` 消息 — 客户端发 `{type: "request", channel: "analysis:{symbol}", params: {focus: "..."}}` 触发后端启动 LLM 生成; 后端通过同一频道推送 `analysis_meta`/`analysis_delta`/`analysis_done` 消息。这样保留了 POST 请求的"触发"语义。

3. **mining SSE 的 SQLite event ledger 与 seq 环形缓冲区的关系**
   - What we know: mining SSE 用 SQLite event ledger + Last-Event-ID 实现持久化恢复 [VERIFIED: backend/app/api/mining.py:266-325]; WS 用内存环形缓冲区
   - What's unclear: WS 重连后 seq 恢复是否能完全替代 SQLite ledger; 进程重启后内存缓冲区丢失
   - Recommendation: 对于 mining/alpha 等有持久化 ledger 的端点, resume 时如果环形缓冲区 miss (seq 太旧或进程重启), 应回退到 SQLite ledger 查询; 否则用环形缓冲区快速重放。但这可能超出 Phase 55 范围 — 如果用户接受 "进程重启后丢失未推送的事件" 语义 (与 SSE 的 SQLite 恢复不同), 则纯内存方案即可。

4. **前端 ndjson 消费者 (financialAnalyzeStream 等) 的迁移方式**
   - What we know: 5 处 ndjson 消费者用 `fetch + ReadableStream + getReader` 解析 [VERIFIED: frontend/src/lib/api.ts:3427-3473]
   - What's unclear: 迁移后这些 async generator 是否改为 WS 消息回调, 还是保持 async generator 接口但底层换 WS
   - Recommendation: 保持 async generator 接口不变, 底层从 fetch+ReadableStream 换成 WS 频道订阅 + 异步队列缓冲。这样消费方代码 (UI 组件) 无需改动。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| FastAPI WebSocket | WS 端点 | ✓ | 0.136.1 | — |
| Starlette WebSocket | WS 传输层 | ✓ | 1.0.1 | — |
| websockets (client) | stockdb_ws/wecom | ✓ | 15.0.1 | — |
| uvicorn | ASGI 服务器 | ✓ | 0.47.0 | — |
| sse-starlette | (待删除) 旧 SSE | ✓ | 3.4.4 | — |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** none

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + FastAPI TestClient |
| Config file | `backend/pyproject.toml` [VERIFIED: backend/pyproject.toml] |
| Quick run command | `cd backend && python -m pytest tests/test_ws_*.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WS-01 | WS 端点连接 + Cookie 鉴权 | unit | `pytest tests/test_ws_connection.py::test_ws_auth -x` | ❌ Wave 0 |
| WS-01 | 无效 session 被拒绝 | unit | `pytest tests/test_ws_connection.py::test_ws_reject_invalid_session -x` | ❌ Wave 0 |
| WS-01 | 多客户端并发连接 | unit | `pytest tests/test_ws_connection.py::test_multi_client -x` | ❌ Wave 0 |
| WS-02 | seq 环形缓冲区重放 | unit | `pytest tests/test_ws_seq.py::test_resume_replay -x` | ❌ Wave 0 |
| WS-02 | buffer 溢出淘汰最旧 | unit | `pytest tests/test_ws_seq.py::test_ring_overflow -x` | ❌ Wave 0 |
| WS-03 | subscribe/unsubscribe 频道 | unit | `pytest tests/test_ws_channels.py::test_subscribe -x` | ❌ Wave 0 |
| WS-03 | 只推已订阅频道 | unit | `pytest tests/test_ws_channels.py::test_channel_filter -x` | ❌ Wave 0 |
| WS-04 | keepalive 心跳 | unit | `pytest tests/test_ws_keepalive.py::test_ping -x` | ❌ Wave 0 |
| WS-01 | 连接生命周期审计 | unit | `pytest tests/test_ws_audit.py::test_audit_on_connect -x` | ❌ Wave 0 |
| WS-02 | 行情流迁移 e2e | integration | `pytest tests/test_ws_quotes.py -x` | ❌ Wave 0 |
| WS-02 | 任务流迁移 e2e | integration | `pytest tests/test_ws_task.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_ws_*.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ws_connection.py` — covers WS-01 (连接 + 鉴权 + 多客户端)
- [ ] `tests/test_ws_seq.py` — covers WS-02 (seq + 环形缓冲区 + resume)
- [ ] `tests/test_ws_channels.py` — covers WS-03 (subscribe/unsubscribe + 频道过滤)
- [ ] `tests/test_ws_keepalive.py` — covers WS-04 (keepalive + 心跳)
- [ ] `tests/test_ws_audit.py` — covers WS-01 (连接生命周期审计)
- [ ] `tests/test_ws_quotes.py` — covers WS-02 (行情流迁移 e2e)
- [ ] `tests/test_ws_task.py` — covers WS-02 (任务流迁移 e2e)

*(If no gaps: "None — existing test infrastructure covers all phase requirements")*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Cookie session 复用 `auth.is_valid_session` [VERIFIED: backend/app/services/auth.py:181-194] |
| V3 Session Management | yes | WS 连接生命周期 = session 生命周期; 断连即终止; 复用 30 天 session TTL [VERIFIED: backend/app/api/auth.py:33] |
| V4 Access Control | yes | principal 鉴权: `auth.resolve_authenticated_reviewer(token)` [VERIFIED: backend/app/services/auth.py:197-209] |
| V5 Input Validation | yes | WS 消息 JSON 解析 + type/channels/seq 字段验证 |
| V6 Cryptography | no | — (复用现有 session token, 无新加密需求) |

### Known Threat Patterns for WebSocket

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 未授权 WS 连接 | Spoofing | Cookie session 鉴权; 无效 session → close(4001) |
| 频道注入 (订阅他人 run_id) | Elevation | 服务端验证 principal 对 run_id 的所有权 (复用现有 `_owned_job` 模式) |
| seq 篡改 (客户端发 fake seq) | Tampering | seq 只由服务端递增; 客户端只能发 `resume last_seq` (只读) |
| 消息洪泛 (客户端大量 subscribe) | DoS | 限制 per-connection 频道数上限; subscribe 消息限频 |
| WS 注入 (跨频道消息泄露) | Information Disclosure | 服务端严格按 channel set 过滤; 不推未订阅频道消息 |

## Migration Scope (完整清单)

### 后端 SSE 端点 (8 处 → 删除)
| # | 文件 | 端点 | SSE 类型 | 迁移到频道 | 复杂度 |
|---|------|------|----------|-----------|--------|
| 1 | intraday.py:159-259 | GET /api/intraday/stream | EventSourceResponse | `quotes` + `alerts` + `portfolio` + `depth` + `review` + `analysis` | HIGH (多事件类型) |
| 2 | mining.py:262-325 | GET /api/backtest/mining/runs/{id}/events | EventSourceResponse | `run:{run_id}` (mining) | MEDIUM (SQLite ledger) |
| 3 | research_alpha_sse.py:123-141 | GET /api/research/alpha/runs/{id}/stream | EventSourceResponse | `run:{run_id}` (alpha) | MEDIUM (SQLite ledger) |
| 4 | walkforward_sse.py:145-188 | GET /api/research/wf/plans/{id}/stream | StreamingResponse text/event-stream | `run:{plan_id}` (wf) | LOW |
| 5 | backtest.py:594-803 | GET /api/backtest/strategy/stream | StreamingResponse text/event-stream | `run:{job_key}` (backtest) | MEDIUM |
| 6 | backtest.py:916-1091 | GET /api/backtest/optimize/stream | StreamingResponse text/event-stream | `run:{job_key}` (optimize) | MEDIUM |
| 7 | backtest.py:1136-1316 | GET /api/backtest/walkforward/stream | StreamingResponse text/event-stream | `run:{job_key}` (wf-opt) | MEDIUM |
| 8 | forecast/api.py:339-371 | GET /api/forecast/jobs/{id}/events | StreamingResponse text/event-stream | `run:{job_id}` (forecast) | MEDIUM (transition_version) |

### 后端 ndjson 端点 (5 处 → 删除)
| # | 文件 | 端点 | 迁移到频道 | 复杂度 |
|---|------|------|-----------|--------|
| 9 | financials.py:174-198 | POST /api/financials/analyze | `analysis:{symbol}` + request 消息 | MEDIUM (LLM 流) |
| 10 | market_recap.py:33-67 | POST /api/market-recap/analyze | `review` + request 消息 | MEDIUM (LLM 流) |
| 11 | rps.py:62-92 | POST /api/rps/rotation-analyze | `review` + request 消息 | MEDIUM (LLM 流) |
| 12 | stock_analysis.py:154-175 | POST /api/stock-analysis/analyze | `analysis:{symbol}` + request 消息 | MEDIUM (LLM 流) |
| 13 | strategy.py:835-863 | POST /api/strategies/build/stream | `analysis:{strategy_id}` + request 消息 | MEDIUM (LLM 流) |

### 前端 EventSource 消费者 (7 处 → 重写)
| # | 文件 | SSE 源 | 迁移到 WS 频道 | 复杂度 |
|---|------|--------|-------------|--------|
| 1 | useQuoteStream.ts:104-351 | /api/intraday/stream | useWsStream (global) + quotes/alerts/portfolio/depth/review | HIGH (多事件 + React Query) |
| 2 | backtestTask.ts:169-286 | /api/backtest/strategy/stream | run:{job_key} 频道 | MEDIUM |
| 3 | optimizerTask.ts:107-198 | /api/backtest/optimize/stream | run:{job_key} 频道 | MEDIUM |
| 4 | walkforwardTask.ts:99-189 | /api/backtest/walkforward/stream | run:{job_key} 频道 | MEDIUM |
| 5 | miningTask.ts:182-234 | /api/backtest/mining/runs/{id}/events | run:{run_id} 频道 | MEDIUM |
| 6 | AlphaWorkbench.tsx:108-195 | /api/research/alpha/runs/{id}/stream | run:{run_id} 频道 | MEDIUM (seq 去重) |
| 7 | WalkForward.tsx:18-82 | /api/research/wf/plans/{id}/stream | run:{plan_id} 频道 | LOW |

### 前端 ndjson 消费者 (5 处 → 重写)
| # | 文件 | ndjson 源 | 迁移到 WS 频道 | 复杂度 |
|---|------|-----------|-------------|--------|
| 8 | api.ts:3427-3473 | /api/financials/analyze | analysis:{symbol} + request | MEDIUM |
| 9 | api.ts:3560-3598 | /api/market-recap/analyze | review + request | MEDIUM |
| 10 | api.ts:3604-3635 | /api/rps/rotation-analyze | review + request | MEDIUM |
| 11 | api.ts:3498-3539 | /api/stock-analysis/analyze | analysis:{symbol} + request | MEDIUM |
| 12 | api.ts:3980-4013 | /api/strategies/build/stream | analysis:{strategy_id} + request | MEDIUM |

### 前端 fetch SSE 消费者 (1 处 → 重写)
| # | 文件 | SSE 源 | 迁移到 WS 频道 | 复杂度 |
|---|------|--------|-------------|--------|
| 13 | forecastTask.ts:243-280 | /api/forecast/jobs/{id}/stream | run:{job_id} 频道 | MEDIUM |

### 依赖删除
- `sse-starlette>=2.0` from `backend/pyproject.toml:15`
- 更新 `backend/tests/test_phase50_guard.py` 依赖基线 (移除 sse-starlette)

### 迁移顺序建议
1. **Wave 0 (TDD):** 写 WS 测试 (连接/鉴权/seq/频道/keepalive/审计)
2. **Wave 1 (后端基础设施):** 新建 `backend/app/ws/` 模块 (ConnectionManager + protocol + handler); 注册 `/ws/stream` 端点
3. **Wave 2 (后端迁移):** 迁移 8 处 SSE 端点的广播逻辑到 WS ConnectionManager; 迁移 5 处 ndjson 端点到 WS 频道触发
4. **Wave 3 (前端基础设施):** 新建 `useWsStream` hook + `wsProtocol.ts`; 替换 Layout.tsx 调用点
5. **Wave 4 (前端迁移):** 迁移 7 处 EventSource 消费者 + 5 处 ndjson 消费者 + 1 处 fetch SSE 消费者
6. **Wave 5 (清理):** 删除 SSE 端点代码; 删除 sse-starlette 依赖; 更新 test_phase50_guard.py

## Sources

### Primary (HIGH confidence)
- FastAPI WebSocket docs [CITED: fastapi.tiangolo.com/advanced/websockets] — ConnectionManager pattern, WebSocketDisconnect, TestClient
- FastAPI WebSocket testing [CITED: fastapi.tiangolo.com/advanced/testing-websockets] — websocket_connect, send_json, receive_json
- Starlette WebSocket docs [CITED: starlette docs/websockets.md] — WebSocket class, accept/send/close, headers/cookies

### Secondary (MEDIUM confidence)
- Codebase analysis of SSE endpoints, WS clients, QuoteService, auth, audit — all [VERIFIED] by reading source files

### Tertiary (LOW confidence)
- uvicorn WS ping interval support — [ASSUMED] not verified; needs implementation-phase check

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all packages pre-existing, versions verified in uv.lock
- Architecture: HIGH - FastAPI WebSocket pattern well-documented; ConnectionManager + seq + channel subscription directly mapped from existing QuoteService
- Pitfalls: MEDIUM - Starlette ping_interval gap is a real concern; ndjson request mechanism needs validation

**Research date:** 2026-08-21
**Valid until:** 2026-09-21 (30 days — stable stack, no fast-moving dependencies)
