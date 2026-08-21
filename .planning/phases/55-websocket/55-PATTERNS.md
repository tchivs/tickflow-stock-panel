# Phase 55: WebSocket 全量迁移 - Pattern Map

**Mapped:** 2026-08-21
**Files analyzed:** 27 (backend + frontend, create + modify + reference)
**Analogs found:** 25 / 27

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/ws/connection_manager.py` (NEW) | service | event-driven | `backend/app/services/quote_service.py` (QuoteSubscriber + subscribe/broadcast) | exact |
| `backend/app/ws/protocol.py` (NEW) | utility | transform | `backend/app/services/stockdb_ws.py` (dispatch + seq + deque ring) | exact |
| `backend/app/ws/handler.py` (NEW) | controller | request-response | `backend/app/api/intraday.py` (quote_stream SSE endpoint) | role-match |
| `backend/app/ws/channels.py` (NEW) | config | event-driven | `backend/app/api/intraday.py` (event type → channel mapping) | role-match |
| `backend/app/ws/__init__.py` (NEW) | config | — | `backend/app/forecast/__init__.py` | partial |
| `backend/app/services/quote_service.py` (MODIFY) | service | event-driven | self (adapt subscribe/broadcast → WS) | exact |
| `backend/app/bootstrap.py` (MODIFY) | config | — | self (add WS ConnectionManager init) | exact |
| `backend/app/main.py` (MODIFY) | route | — | self (add WS endpoint registration) | exact |
| `backend/app/api/intraday.py` (MODIFY) | controller | request-response | self (delete SSE, route to WS) | exact |
| `backend/app/api/mining.py` (MODIFY) | controller | request-response | self (delete SSE, route to WS) | exact |
| `backend/app/api/research_alpha_sse.py` (MODIFY/DELETE) | controller | request-response | self (delete SSE) | exact |
| `backend/app/api/walkforward_sse.py` (MODIFY/DELETE) | controller | request-response | self (delete SSE) | exact |
| `backend/app/api/backtest.py` (MODIFY) | controller | request-response | self (delete 3 SSE endpoints) | exact |
| `backend/app/forecast/api.py` (MODIFY) | controller | request-response | self (delete SSE) | exact |
| `backend/app/api/financials.py` (MODIFY) | controller | request-response | self (delete ndjson) | exact |
| `backend/app/api/market_recap.py` (MODIFY) | controller | request-response | self (delete ndjson) | exact |
| `backend/app/api/rps.py` (MODIFY) | controller | request-response | self (delete ndjson) | exact |
| `backend/app/api/stock_analysis.py` (MODIFY) | controller | request-response | self (delete ndjson) | exact |
| `backend/app/api/strategy.py` (MODIFY) | controller | request-response | self (delete ndjson build/stream) | exact |
| `frontend/src/lib/useWsStream.ts` (NEW) | hook | event-driven | `frontend/src/lib/useQuoteStream.ts` (status store + EventSource lifecycle) | exact |
| `frontend/src/lib/wsProtocol.ts` (NEW) | utility | transform | `backend/app/services/stockdb_ws.py` (subscribe/resume protocol) | role-match |
| `frontend/src/lib/useQuoteStream.ts` (MODIFY/DELETE) | hook | event-driven | self (replace with useWsStream) | exact |
| `frontend/src/lib/backtestTask.ts` (MODIFY) | hook | event-driven | self (replace SSE with WS) | exact |
| `frontend/src/lib/optimizerTask.ts` (MODIFY) | hook | event-driven | self (replace SSE with WS) | exact |
| `frontend/src/lib/walkforwardTask.ts` (MODIFY) | hook | event-driven | self (replace SSE with WS) | exact |
| `frontend/src/lib/miningTask.ts` (MODIFY) | hook | event-driven | self (replace SSE with WS) | exact |
| `frontend/src/lib/forecastTask.ts` (MODIFY) | hook | event-driven | self (replace fetch SSE with WS) | exact |
| `frontend/src/pages/backtest/AlphaWorkbench.tsx` (MODIFY) | component | event-driven | self (replace SSE with WS) | exact |
| `frontend/src/pages/backtest/WalkForward.tsx` (MODIFY) | component | event-driven | self (replace SSE with WS) | exact |
| `frontend/src/components/Layout.tsx` (MODIFY) | component | event-driven | self (replace useQuoteStream with useWsStream) | exact |
| `frontend/src/lib/api.ts` (MODIFY) | utility | streaming | self (replace ndjson consumers with WS) | exact |
| `frontend/src/lib/queryKeys.ts` (MODIFY) | config | — | self (rename SSE_INVALIDATE_PREFIXES) | exact |
| `backend/tests/test_ws_*.py` (NEW, 7 files) | test | request-response | FastAPI TestClient WebSocket docs | role-match |
| `backend/tests/test_phase50_guard.py` (MODIFY) | test | — | self (update dependency baseline) | exact |

## Pattern Assignments

### `backend/app/ws/connection_manager.py` (service, event-driven)

**Analog:** `backend/app/services/quote_service.py` — QuoteSubscriber + subscribe/broadcast pattern

**Key insight:** QuoteSubscriber (threading.Event + per-connection queue) → WsConnection (WebSocket + per-connection deque ring). QuoteService `_subscribers: set[QuoteSubscriber]` → ConnectionManager `_connections: list[WsConnection]`. The `_broadcast_*` methods → `broadcast_to_channel`. This is a direct adaptation, not a new pattern.

**QuoteSubscriber per-connection state** (`quote_service.py:44-107`):
```python
class QuoteSubscriber:
    """一个 SSE 连接对应一个订阅者: 独立事件 + 独立队列。"""
    def __init__(self, ...) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._max_alerts = max_alerts        # 背压: 丢弃最旧
        self._alerts: list[dict] = []
        self._reviews: list[str] = []
        # ... per-channel pending queues

    def wait(self, timeout: float = 5.0) -> bool:
        return self._event.wait(timeout=timeout)

    def pop(self) -> dict:
        """原子取走全部待推送内容并复位事件。"""
        with self._lock:
            out = { ... }
            self._event.clear()
            return out
```

**QuoteService subscribe/unsubscribe + broadcast** (`quote_service.py:443-493`):
```python
# SSE 订阅管理 — 每个 /stream 连接一个订阅者, 事件广播
def subscribe(self, *, analysis_scope=None, advanced_scope=None) -> QuoteSubscriber:
    """注册一个 SSE 订阅者 (连接建立时调用)。"""
    sub = QuoteSubscriber(analysis_scope=analysis_scope, advanced_scope=advanced_scope)
    with self._lock:
        self._subscribers.add(sub)
    return sub

def unsubscribe(self, sub: QuoteSubscriber) -> None:
    """注销订阅者 (连接断开时调用)。"""
    with self._lock:
        self._subscribers.discard(sub)

def _snapshot_subscribers(self) -> list[QuoteSubscriber]:
    with self._lock:
        return list(self._subscribers)

def _broadcast_quote_updated(self) -> None:
    for sub in self._snapshot_subscribers():
        sub.notify_quote()

def _broadcast_alerts(self, alerts: list[dict]) -> None:
    for sub in self._snapshot_subscribers():
        sub.push_alerts(alerts)
```

**Adaptation for WsConnection:** Replace `threading.Event + pop()` with `WebSocket.send_json()`. Replace per-channel pending lists with per-connection `deque(maxlen=1000)` ring buffer + seq counter. Add `channels: set[str]` for subscribe/unsubscribe filtering.

**stockdb_ws.py deque ring buffer pattern** (`stockdb_ws.py:84, 277-294`):
```python
# alerts 环缓冲(服务端仅事件推送, 无首推)
self._ring: deque[dict] = deque(maxlen=_ALERTS_RING)  # maxlen=500

def alerts_since(self, since_seq: int = 0, limit: int = 100) -> dict:
    """alerts 环缓冲增量读取(线程安全)。返回 {events, cursor, gate}。"""
    with self._lock:
        events = [e for e in self._ring if e.get("seq", 0) > since_seq]
    events.sort(key=lambda e: e.get("seq", 0))
    return {"events": events[-limit:], "cursor": self._last_seq, "source_gate": gate}
```

**seq advancement pattern** (`stockdb_ws.py:258-261`):
```python
for item in data:
    seq = item.get("seq")
    if isinstance(seq, int) and seq > self._last_seq:
        self._last_seq = seq
```

---

### `backend/app/ws/protocol.py` (utility, transform)

**Analog:** `backend/app/services/stockdb_ws.py` — message dispatch + seq tracking

**Message protocol from stockdb_ws** (`stockdb_ws.py:5-15`):
```python
# 协议(stockdb src/stockdb/api/ws.py, 2026-08 实测):
#   发: {"op":"subscribe","channel":"quotes"|"depth"|"alerts","symbols":[...]}
#       {"op":"unsubscribe",...} / {"op":"resume","last_seq":N}
#   收: {"op":"subscribed","channel",...,"total"}
#       {"op":"quotes"|"depth","data":[{"seq","ts","symbol","snap"|"depth"}]}
#       {"op":"alerts","data":[{"symbol","pct_chg","last","ts","level"}]}
#       {"op":"error","reason":...}
```

**Dispatch + seq pattern** (`stockdb_ws.py:245-276`):
```python
def _dispatch(self, msg: dict) -> None:
    """单帧分发: seq/时间戳推进 + 频道回调 + alerts 入环缓冲。"""
    op = msg.get("op")
    if op == "subscribed":
        logger.info("stockdb WS: subscribed %s (total=%s)", msg.get("channel"), msg.get("total"))
        return
    if op == "error":
        logger.warning("stockdb WS: 服务端 error: %s", msg.get("reason"))
        return
    data = msg.get("data")
    if not isinstance(data, list) or not data:
        return
    now = time.time()
    for item in data:
        seq = item.get("seq")
        if isinstance(seq, int) and seq > self._last_seq:
            self._last_seq = seq
    self._last_msg_ts = now
    self._last_msg_at = now
    handler = self._handlers.get(op)
    if handler is not None:
        try:
            handler(data)
        except Exception:  # noqa: BLE001 — 回调异常不拖垮读循环
            logger.exception("stockdb WS: %s 回调异常", op)
```

**Adaptation for protocol.py:** D-05 message format `{type: string, seq: number, data: object}`. Map `op` → `type`. Client messages: `subscribe`, `unsubscribe`, `resume`, `request` (for ndjson flows). Server messages: event types (`quotes_updated`, `strategy_alert`, `job_progress`, `analysis_delta`, `ping`, etc.) + control acks (`subscribed`, `unsubscribed`, `resumed`).

---

### `backend/app/ws/handler.py` (controller, request-response)

**Analog:** `backend/app/api/intraday.py:159-259` — SSE quote_stream endpoint

**SSE endpoint structure to replace** (`intraday.py:159-259`):
```python
@router.get("/stream")
async def quote_stream(request: Request):
    """SSE 端点: 行情更新 + 告警推送 + 五档修正 + 复盘进度。"""
    qs = _get_quote_service(request)
    analysis_scope = _analysis_scope(request) if qs is not None else None
    advanced_scope = _advanced_scope(request) if qs is not None else None

    async def event_generator():
        if qs is None:
            while True:
                await asyncio.sleep(30)
        sub = qs.subscribe(analysis_scope=analysis_scope, advanced_scope=advanced_scope)
        try:
            yield {"event": "stream_ready", "data": "{}"}
            while True:
                await asyncio.to_thread(sub.wait, 5.0)
                data = sub.pop()
                # 告警 (分片推送)
                alerts = data["alerts"]
                for chunk_start in range(0, len(alerts), 20):
                    chunk = alerts[chunk_start:chunk_start + 20]
                    yield {"event": "strategy_alert", "data": json.dumps({...})}
                if data["portfolio_updated"]:
                    yield {"event": "portfolio_updated", "data": json.dumps({...})}
                # ... 多事件类型
                if data["quote_updated"]:
                    yield {"event": "quotes_updated", "data": json.dumps({...})}
        finally:
            qs.unsubscribe(sub)

    return EventSourceResponse(event_generator())
```

**WS handler adaptation:** Replace `@router.get("/stream")` + `EventSourceResponse` with `@app.websocket("/ws/stream")`. Replace `event_generator()` yield loop with `websocket.receive_json()` → dispatch loop. Cookie auth at handshake (see Shared Patterns below). Connection lifecycle: `manager.connect(ws, principal)` → message loop → `manager.disconnect(conn)` on `WebSocketDisconnect`.

**Event type → channel mapping** from `intraday.py:194-255`:
```python
# SSE event names → WS message type / channel:
"strategy_alert"      → type="strategy_alert", channel="alerts"
"portfolio_updated"   → type="portfolio_updated", channel="portfolio"
"review_progress"     → type="review_progress", channel="review"
"analysis_progress"   → type="analysis_progress", channel="analysis:{symbol}"
"advanced_progress"   → type="advanced_progress", channel="analysis:{symbol}"
"quotes_updated"      → type="quotes_updated", channel="quotes"
"strategy_results_updated" → type="strategy_results_updated", channel="quotes"
"depth_updated"       → type="depth_updated", channel="depth"
```

---

### `backend/app/ws/channels.py` (config, event-driven)

**Analog:** `backend/app/api/intraday.py` event type mapping + `backend/app/api/backtest.py` job_key pattern

**Channel naming (D-08):** `quotes`, `alerts`, `portfolio`, `run:{run_id}`, `analysis:{symbol}`, `review`, `depth`

**Job key → channel pattern** from `backtest.py:649-660`:
```python
job_key = _make_job_key(
    strategy_id, symbols, start, end,
    matching, entry_fill, exit_fill,
    fees_pct, slippage_bps, max_positions, max_exposure_pct, initial_capital, position_sizing,
    params, overrides,
    mode, holding_days,
    commission_pct, stamp_tax_pct,
    asset_type=asset_type,
    minute_fill=minute_fill,
    regime_filter=regime_filter,
)
# WS: channel = f"run:{job_key}"
```

**ndjson → request channel pattern** from `financials.py:174-198`:
```python
@router.post("/analyze")
async def analyze_financials(request: Request, req: AnalyzeRequest):
    """AI 财务分析 — SSE 流式返回。"""
    # WS adaptation: client sends {type: "request", channel: "analysis:{symbol}", params: {focus: "..."}}
    # Server starts LLM stream, pushes via channel: analysis_meta / analysis_delta / analysis_done
    async def stream_gen():
        async for chunk in analyze_financials_stream(data_dir, req.symbol, req.focus):
            yield chunk + "\n"
    return StreamingResponse(stream_gen(), media_type="application/x-ndjson", ...)
```

---

### `backend/app/services/quote_service.py` (MODIFY, service, event-driven)

**Analog:** self — adapt `_broadcast_*` methods to also push to WS ConnectionManager

**Current broadcast methods to adapt** (`quote_service.py:461-593`):
```python
def _broadcast_quote_updated(self) -> None:
    from app.api.overview import invalidate_overview_cache
    invalidate_overview_cache()
    for sub in self._snapshot_subscribers():
        sub.notify_quote()

def _broadcast_alerts(self, alerts: list[dict]) -> None:
    for sub in self._snapshot_subscribers():
        sub.push_alerts(alerts)

def notify_portfolio_updated(self, account_ids: list[str | int]) -> None:
    for sub in self._snapshot_subscribers():
        sub.notify_portfolio_updated(account_ids)

def push_review_event(self, event_json: str) -> None:
    """广播一条复盘进度事件(JSON 字符串), 唤醒所有 SSE generator。"""
    for sub in self._snapshot_subscribers():
        sub.push_review(event_json)
```

**Modification:** Add `self._ws_manager: ConnectionManager | None = None` and `attach_ws_manager(mgr)` method (following the existing `attach_stockdb_ws` pattern at `quote_service.py:280`). In each `_broadcast_*` / `notify_*` method, after the existing SSE subscriber loop, also call `self._ws_manager.broadcast_to_channel(channel, type, data)`.

**attach_stockdb_ws pattern** (`quote_service.py:278-281`):
```python
# stockdb WS 实时通道 (M004): None = 未接入; attach 后由 WS 推送驱动
self._ws = None
self._ws_last_submitted: set[str] = set()
```

---

### `backend/app/bootstrap.py` (MODIFY, config)

**Analog:** self — QuoteService + stockdb_ws init pattern

**Current init pattern** (`bootstrap.py:451-460`):
```python
# 全局行情服务
qs = QuoteService()
app.state.quote_service = qs
qs.set_repo(repo)
# stockdb WS 实时通道 (M004)
from app.services.stockdb_ws import StockDBWS
ws_client = StockDBWS(settings.local_stockdb_url, settings.local_stockdb_api_key)
app.state.stockdb_ws = ws_client
qs.attach_stockdb_ws(ws_client)
ws_client.start()  # lifespan 事件循环内启动; 未配 key 时内部 no-op
```

**Modification:** After QuoteService init, add:
```python
# Phase 55: WebSocket ConnectionManager
from app.ws.connection_manager import ConnectionManager
ws_manager = ConnectionManager()
app.state.ws_manager = ws_manager
qs.attach_ws_manager(ws_manager)
```

**Shutdown pattern** (`bootstrap.py:795-801`):
```python
wsq = getattr(app.state, "stockdb_ws", None)
if wsq:
    wsq.stop()
qs = getattr(app.state, "quote_service", None)
if qs:
    qs.stop()
```

---

### `backend/app/main.py` (MODIFY, route)

**Analog:** self — router include pattern + WebSocket endpoint registration

**Current router registration** (`main.py:259-310`):
```python
app.include_router(core_router)
app.include_router(auth_api.router)
app.include_router(kline.router)
# ... 40+ routers
app.include_router(intraday.router)
# ...
```

**Modification:** Add WS endpoint registration. Two options (planner decides):
1. `@app.websocket("/ws/stream")` directly in main.py or a new ws module imported here
2. Import and include a ws router

---

### Frontend: `frontend/src/lib/useWsStream.ts` (NEW, hook, event-driven)

**Analog:** `frontend/src/lib/useQuoteStream.ts` — global SSE connection status + EventSource lifecycle

**Connection status store pattern** (`useQuoteStream.ts:41-78`):
```typescript
// ===== 全局 SSE 连接状态 (模块级 store, 仿 AlertToast.tsx 模式) =====
export type QuoteStreamStatus = 'connected' | 'reconnecting' | 'disconnected'

let _streamStatus: QuoteStreamStatus = 'disconnected'
const _statusListeners = new Set<() => void>()

const FAILS_BEFORE_TOAST = 3
const BACKOFF_CAP_MS = 60_000

function _emitStatus() {
  _statusListeners.forEach((fn) => fn())
}

function _setStatus(s: QuoteStreamStatus) { ... }
function _subscribeStatus(fn: () => void) { ... }
function _getStatus() { return _streamStatus }

export function useQuoteStreamStatus(): QuoteStreamStatus {
  return useSyncExternalStore(_subscribeStatus, _getStatus, () => 'disconnected' as const)
}
```

**EventSource lifecycle + reconnect pattern** (`useQuoteStream.ts:195-350`):
```typescript
const connect = () => {
  _setStatus(failCount > 0 ? 'reconnecting' : _streamStatus)
  const es = new EventSource('/api/intraday/stream')
  esRef.current = es

  es.onopen = () => {
    failCount = 0
    toastFired = false
    _setStatus('connected')
  }

  es.addEventListener('quotes_updated', () => {
    if (!enabledRef.current) return
    // ... invalidate queries via SSE_INVALIDATE_PREFIXES
  })
  es.addEventListener('strategy_alert', (e: MessageEvent) => { ... })
  // ... more event listeners

  es.onerror = () => {
    es.close()
    esRef.current = null
    failCount += 1
    _setStatus('reconnecting')
    if (failCount >= FAILS_BEFORE_TOAST && !toastFired) {
      toastFired = true
      toast('实时连接已断开，正在重连…', 'error')
    }
    // 指数退避 (base * 2^(n-1), 上限 60s)
    const base = getQueryConfig().sse.reconnectDelay
    const delay = Math.min(base * 2 ** (failCount - 1), BACKOFF_CAP_MS)
    retryRef.current = setTimeout(connect, delay)
  }
}
```

**Adaptation for useWsStream:** Replace `new EventSource(url)` with `new WebSocket(wsUrl)`. Replace `es.addEventListener('event_name', ...)` with `ws.onmessage` → JSON parse → route by `msg.type`. Add channel subscribe/unsubscribe on open. Add `resume` with `last_seq` on reconnect. D-13 backoff: 1s→2s→4s→8s→16s→30s.

**stockdb_ws.py client reconnect/resume pattern** (`stockdb_ws.py:157-211`):
```python
async def _run(self) -> None:
    """重连循环: 连接 → resume → 全量重订阅 → 读循环分发。"""
    backoff = 0
    while not self._closing:
        try:
            async with websockets.connect(
                self._url,
                additional_headers={"X-API-Key": self._api_key},
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ) as ws:
                backoff = 0
                self._connected = True
                await self._after_connect(ws)
                await self._read_loop(ws)
        except Exception as e:
            self._connected = False
            backoff += 1
            delay = min(1.0 * 2 ** min(backoff, 6), 60.0) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
            self._reconnects += 1

async def _after_connect(self, ws) -> None:
    """重连后: resume 补断帧 + 重建全部期望订阅。"""
    if self._last_seq > 0:
        await ws.send(json.dumps({"op": "resume", "last_seq": self._last_seq}))
    # 全量重订阅
    for channel in ("quotes", "depth", "alerts"):
        syms = sorted(wanted.get(channel, set()))
        if channel == "quotes" and not syms:
            continue
        await self._send_subscribe(ws, channel, syms)
```

**Frontend TypeScript equivalent:**
```typescript
// D-09: 前端全局单连接
// D-13: 指数退避重连 1s→2s→4s→8s→16s→30s
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

---

### Frontend: `frontend/src/lib/wsProtocol.ts` (NEW, utility, transform)

**Analog:** `backend/app/services/stockdb_ws.py` — client-side protocol types

**stockdb_ws protocol constants** (`stockdb_ws.py:5-15`):
```python
# 发: {"op":"subscribe","channel":"quotes"|"depth"|"alerts","symbols":[...]}
#     {"op":"unsubscribe",...} / {"op":"resume","last_seq":N}
# 收: {"op":"subscribed","channel",...,"total"}
#     {"op":"quotes"|"depth","data":[{"seq","ts","symbol","snap"|"depth"}]}
#     {"op":"alerts","data":[...]}
#     {"op":"error","reason":...}
```

**Adaptation:** D-05 message format `{type: string, seq: number, data: object}`. TypeScript types for `WsMessage`, `SubscribeMessage`, `UnsubscribeMessage`, `ResumeMessage`, `RequestMessage`.

---

### Frontend: `frontend/src/lib/backtestTask.ts` (MODIFY, hook, event-driven)

**Analog:** self — SSE connectSSE pattern → WS channel subscribe

**Current SSE pattern** (`backtestTask.ts:169-286`):
```typescript
function connectSSE(url: string): void {
  const id = current?.id ?? ++taskSeq
  if (eventSource) { eventSource.close(); eventSource = null }

  const es = new EventSource(url)
  eventSource = es
  let reconnectAttempts = 0

  es.onopen = () => { clearReconnecting() }

  es.addEventListener('progress', (e: MessageEvent) => {
    if (current?.id !== id || !current.isPending) return
    reconnectAttempts = 0
    try {
      const parsed = JSON.parse(e.data)
      // ... validate + update current
    } catch { /* ignore */ }
  })

  es.addEventListener('done', (e: MessageEvent) => {
    if (current?.id !== id || !current.isPending) return
    try {
      const payload = JSON.parse(e.data)
      current = { ...current, isPending: false, result: payload, error: null, reconnecting: false }
      emit()
    } catch { ... }
    es.close()
    eventSource = null
    localStorage.removeItem(RECONNECT_KEY)
  })

  es.addEventListener('error', (e: MessageEvent) => {
    if (current?.id !== id || !current.isPending) return
    if (e.data) {
      // 后端推送的错误
      current = { ...current, isPending: false, error: msg, reconnecting: false }
      emit()
      es.close()
      return
    }
    // 连接断开: EventSource 自动重连, 有界放弃
    reconnectAttempts += 1
    if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) { ... }
    current = { ...current, reconnecting: true }
    emit()
  })
}
```

**WS adaptation:** Replace `new EventSource(url)` with `useWsStream.subscribe('run:{job_key}', handler)`. Event names `progress`/`done`/`error` → WS message types `job_progress`/`job_done`/`job_error`. `localStorage` reconnect key stores `job_key` instead of query string. `cancel` still via POST (D-05: Pitfall 5 — cancel endpoint retained).

**job_key pattern** (`backtestTask.ts:312-356`):
```typescript
export function startBacktest(params: { ... }): void {
  // 存 reconnect 信息 (刷新后用)
  localStorage.setItem(RECONNECT_KEY, qs)
  connectSSE(`/api/backtest/strategy/stream?${qs}`)
}
```

**optimizerTask job_key pattern** (`optimizerTask.ts:119-137`):
```typescript
es.addEventListener('job', (e: MessageEvent) => {
  try {
    const key = JSON.parse(e.data)?.key
    if (key) {
      currentJobKey = key
      localStorage.setItem(JOB_KEY_KEY, key)
      // 竞态修复: stop 在拿到 key 前被点过 -> 补发 cancel
      if (cancelRequested) { postCancel(key); es.close() }
    }
  } catch { /* ignore */ }
})
```

**walkforwardTask pattern** (`walkforwardTask.ts:99-189`): Identical to optimizerTask — same `job`/`progress`/`done`/`error` events, same `localStorage` reconnect, same `MAX_RECONNECT` cap.

---

### Frontend: `frontend/src/lib/miningTask.ts` (MODIFY, hook, event-driven)

**Analog:** self — SSE EventSource + bounded polling fallback

**Current SSE pattern** (`miningTask.ts:182-234`):
```typescript
function connect(runId: string) {
  closeEvents()
  const token = connectionToken
  const source = new EventSource(`/api/backtest/mining/runs/${encodeURIComponent(runId)}/events`)
  eventSource = source

  source.onopen = () => {
    if (token !== connectionToken) return
    update({ reconnecting: false })
    if (!current.cancelling) stopStatusPolling()
  }

  source.addEventListener('progress', event => {
    update({ progress: eventPayload(event), reconnecting: false })
  })

  const onTerminal = (event: Event) => {
    const payload = eventPayload(event)
    const status = (payload.status || eventType) as MiningRunStatus
    closeEvents()
    void refreshTerminalRun(runId, status, ...)
  }
  for (const type of ['succeeded', 'failed', 'cancelled', 'interrupted', ...]) {
    source.addEventListener(type, onTerminal)
  }

  source.onerror = () => {
    if (token !== connectionToken || !current.isPending) return
    update({ reconnecting: true })
    startStatusPolling(runId, token)  // 降级到轮询
  }
}
```

**WS adaptation:** Replace `new EventSource(url)` with `useWsStream.subscribe('run:{run_id}', handler)`. Terminal event types → WS message types. Polling fallback (`startStatusPolling`) retained as degraded path (same pattern as AlphaWorkbench `EventSource === undefined` fallback).

---

### Frontend: `frontend/src/lib/forecastTask.ts` (MODIFY, hook, event-driven)

**Analog:** self — fetch + ReadableStream SSE consumer

**Current fetch SSE pattern** (`forecastTask.ts:243-280`):
```typescript
const connect = async () => {
  abortRef.current?.abort()
  const controller = new AbortController()
  abortRef.current = controller
  setState(previous => ({ ...previous, connection: 'connecting' }))
  try {
    const headers = new Headers({ Accept: 'text/event-stream' })
    if (latestEventIdRef.current) headers.set('Last-Event-ID', latestEventIdRef.current)
    const response = await fetch(`/api/forecast/jobs/${encodeURIComponent(jobId)}/stream`, { headers, signal: controller.signal })
    if (!response.ok || !response.body) throw new Error(...)
    setState(previous => ({ ...previous, connection: 'connected' }))
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (!disposed) {
      const chunk = await reader.read()
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const progress = acceptFrame(frame)
        if (progress && isTerminal(progress.status) && await finishFromPersisted(progress)) return
        boundary = buffer.indexOf('\n\n')
      }
    }
    if (!disposed) await scheduleReconnect(() => { void connect() })
  } catch (error) {
    if (!disposed && !(error instanceof DOMException && error.name === 'AbortError'))
      await scheduleReconnect(() => { void connect() })
  }
}
```

**WS adaptation:** Replace `fetch + ReadableStream` with `useWsStream.subscribe('run:{job_id}', handler)`. `Last-Event-ID` header → `resume last_seq` message. `acceptFrame(frame)` SSE parser → `ws.onmessage` JSON parse. Reconnect via useWsStream backoff.

---

### Frontend: `frontend/src/pages/backtest/AlphaWorkbench.tsx` (MODIFY, component, event-driven)

**Analog:** self — EventSource + seq dedup + Last-Event-ID

**Current SSE pattern** (`AlphaWorkbench.tsx:108-192`):
```typescript
function useAlphaStream(runId: string | null) {
  const [status, setStatus] = useState<ConnStatus>('idle')
  const [events, setEvents] = useState<AlphaRunEvent[]>([])
  const esRef = useRef<EventSource | null>(null)
  const seenSeqs = useRef<Set<number>>(new Set())

  useEffect(() => {
    // ... seq dedup by seenSeqs
    const onEvent = (raw: string) => {
      const data = JSON.parse(raw) as Partial<AlphaRunEvent>
      if (typeof data.seq === 'number') {
        if (seenSeqs.current.has(data.seq)) return  // dedup
        seenSeqs.current.add(data.seq)
        setEvents(prev => [...prev, data as AlphaRunEvent])
      }
    }

    // Graceful degradation: bounded polling when SSE is unavailable
    if (typeof EventSource === 'undefined') {
      setPolling(true)
      pollTimer.current = setInterval(async () => { ... }, POLL_INTERVAL_MS)
      return () => stopPoll()
    }

    const es = new EventSource(alphaRunStreamUrl(runId))
    esRef.current = es
    for (const type of ALPHA_PROGRESS_EVENTS) {
      es.addEventListener(type, (e: MessageEvent) => onEvent(e.data))
    }
    es.addEventListener('terminal', () => { setStatus('done'); es.close() })
    es.onerror = () => { setStatus(prev => prev === 'done' ? prev : 'reconnecting') }
    return () => { es.close(); esRef.current = null }
  }, [runId, stopPoll])
}
```

**WS adaptation:** Replace `new EventSource(url)` with `useWsStream.subscribe('run:{run_id}', handler)`. seq dedup via `seenSeqs` Set still needed (WS resume may replay). Polling fallback retained.

---

### Frontend: `frontend/src/pages/backtest/WalkForward.tsx` (MODIFY, component, event-driven)

**Analog:** self — EventSource for walkforward plan stream

**Current SSE pattern** (`WalkForward.tsx:18-82`):
```typescript
function useWfStream(planId: string | undefined) {
  const [state, setState] = useState<WfStreamState>({ status: 'idle', ... })
  const [running, setRunning] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  const open = () => {
    const current = planRef.current
    if (!current) return
    setState({ status: 'idle', foldIndex: 0, totalFolds: 0, isOos: false })
    esRef.current?.close()
    const es = new EventSource(`/api/research/wf/plans/${encodeURIComponent(current)}/stream`)
    esRef.current = es
    es.addEventListener('progress', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      setState({ status: 'running', foldIndex: data.fold_index, totalFolds: data.total_folds, isOos: data.is_oos })
    })
    es.addEventListener('done', () => { setState(prev => ({ ...prev, status: 'done' })); setRunning(false); es.close() })
    es.onerror = () => { setState(prev => prev.status === 'done' ? prev : { ...prev, status: 'reconnecting' }) }
  }

  useEffect(() => { open(); return () => esRef.current?.close() }, [planId])

  const start = async () => {
    setRunning(true)
    await api.runWfPlan(planRef.current)
    if (!esRef.current || esRef.current.readyState === EventSource.CLOSED) { open() }
  }
}
```

**WS adaptation:** Replace `new EventSource(url)` with `useWsStream.subscribe('run:{plan_id}', handler)`. POST `runWfPlan` retained (triggers backend job). `progress`/`done` events → WS message types.

---

### Frontend: `frontend/src/components/Layout.tsx` (MODIFY, component)

**Analog:** self — useQuoteStream call site

**Current call** (`Layout.tsx:484-487`):
```typescript
// SSE: 行情更新时自动刷新相关 queries + 告警通知
useQuoteStream(realtimeEnabled, prefs?.sse_refresh_pages)
// 实时 SSE 连接状态 — 断开时底部显示提示
const streamStatus = useQuoteStreamStatus()
```

**WS adaptation:** Replace with `useWsStream(realtimeEnabled, prefs?.sse_refresh_pages)` + `useWsStreamStatus()`.

---

### Frontend: `frontend/src/lib/api.ts` (MODIFY, utility, streaming)

**Analog:** self — ndjson async generator consumers

**Current ndjson consumer pattern** (`api.ts:3443-3489`):
```typescript
async *financialAnalyzeStream(symbol: string, focus?: string): AsyncGenerator<{...}> {
  const res = await fetch('/api/financials/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, focus: focus ?? '' }),
  })
  if (!res.ok) { ... throw new Error(msg) }
  if (!res.body) throw new Error('响应无 body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      const s = line.trim()
      if (!s) continue
      try { yield JSON.parse(s) } catch { /* ignore */ }
    }
  }
  if (buf.trim()) { try { yield JSON.parse(buf.trim()) } catch {} }
},
```

**WS adaptation (RESEARCH.md Open Question 4 recommendation):** Keep async generator interface, replace fetch+ReadableStream with WS channel subscribe + async queue buffer. Consumer code (UI components) stays unchanged.

```typescript
async *financialAnalyzeStream(symbol: string, focus?: string): AsyncGenerator<{...}> {
  // WS: send {type: "request", channel: `analysis:${symbol}`, params: {focus}}
  // Receive via useWsStream channel handler, buffer in async queue
  const queue = new AsyncQueue()
  const unsub = useWsStream.subscribe(`analysis:${symbol}`, (data) => {
    queue.push(data)
    if (data.type === 'done' || data.type === 'error') queue.close()
  })
  useWsStream.request(`analysis:${symbol}`, { symbol, focus })
  try {
    for await (const msg of queue) {
      yield msg  // {type: 'meta'|'delta'|'error'|'done', ...}
    }
  } finally {
    unsub()
  }
},
```

**5 ndjson consumers to migrate** (all identical pattern):
1. `financialAnalyzeStream` (`api.ts:3443`) → channel `analysis:{symbol}`
2. `stockAnalyzeStream` (`api.ts:3514`) → channel `analysis:{symbol}`
3. `reviewStream` (`api.ts:3576`) → channel `review`
4. `rotationAnalyzeStream` (`api.ts:3620`) → channel `review`
5. `buildStrategyStream` (`api.ts:3980-4013`) → channel `analysis:{strategy_id}`

---

### Frontend: `frontend/src/lib/queryKeys.ts` (MODIFY, config)

**Analog:** self — SSE_INVALIDATE_PREFIXES

**Current** (`queryKeys.ts:260-275`):
```typescript
export const SSE_INVALIDATE_PREFIXES = [
  'watchlist-quotes',
  'watchlist-enriched',
  'quote-status',
  'index-quotes',
  'overview-market',
  'limit-ladder',
  'portfolio-summary',
  'portfolio-holdings',
  'optimization-runs',
  'rebalance-plans',
  'paper',
] as const
```

**WS adaptation:** Rename to `WS_INVALIDATE_PREFIXES` (same values). Update all references in `useQuoteStream.ts` / `useWsStream.ts`.

---

### Backend SSE/ndjson endpoint files (MODIFY/DELETE) — collective pattern

All 8 SSE + 5 ndjson backend endpoints follow the same deletion pattern:

| File | Endpoint | Delete | Replace with |
|------|----------|--------|-------------|
| `intraday.py:159-259` | GET /api/intraday/stream | EventSourceResponse | WS broadcast via QuoteService → ConnectionManager |
| `mining.py:262-325` | GET /runs/{id}/events | EventSourceResponse | WS channel `run:{run_id}` |
| `research_alpha_sse.py:123-141` | GET /alpha/runs/{id}/stream | EventSourceResponse | WS channel `run:{run_id}` |
| `walkforward_sse.py:145-188` | GET /wf/plans/{id}/stream | StreamingResponse text/event-stream | WS channel `run:{plan_id}` |
| `backtest.py:594-803` | GET /strategy/stream | StreamingResponse text/event-stream | WS channel `run:{job_key}` |
| `backtest.py:916-1091` | GET /optimize/stream | StreamingResponse text/event-stream | WS channel `run:{job_key}` |
| `backtest.py:1136-1316` | GET /walkforward/stream | StreamingResponse text/event-stream | WS channel `run:{job_key}` |
| `forecast/api.py:339-371` | GET /jobs/{id}/events | StreamingResponse text/event-stream | WS channel `run:{job_id}` |
| `financials.py:174-198` | POST /analyze | StreamingResponse x-ndjson | WS channel `analysis:{symbol}` + request msg |
| `market_recap.py:33-67` | POST /analyze | StreamingResponse x-ndjson | WS channel `review` + request msg |
| `rps.py:62-92` | POST /rotation-analyze | StreamingResponse x-ndjson | WS channel `review` + request msg |
| `stock_analysis.py:154-175` | POST /analyze | StreamingResponse x-ndjson | WS channel `analysis:{symbol}` + request msg |
| `strategy.py:835-863` | POST /build/stream | StreamingResponse x-ndjson | WS channel `analysis:{strategy_id}` + request msg |

**Pattern for each:** Delete the endpoint function. For SSE job-stream endpoints (backtest/optimize/walkforward/mining/alpha/forecast), the job computation logic (thread launch, progress tracking) stays — only the SSE generator is removed; events now pushed via `ws_manager.broadcast_to_channel(f"run:{job_key}", "job_progress", data)`. For ndjson LLM endpoints, the `async for chunk in ..._stream(...)` generator stays — wrapped in a WS request handler that pushes chunks via `ws_manager.broadcast_to_channel`.

---

### `backend/tests/test_phase50_guard.py` (MODIFY, test)

**Analog:** self — dependency baseline

**Modification:** Remove `"sse-starlette>=2.0"` from `_DEPENDENCY_BASELINE`. Remove any `EventSourceResponse` assertions. Add WebSocket assertions if applicable.

---

## Shared Patterns

### Authentication — Cookie Session (WS Handshake)

**Source:** `backend/app/api/auth.py:32` + `backend/app/services/auth.py:181-209`
**Apply to:** `backend/app/ws/handler.py`

```python
# backend/app/api/auth.py:32
COOKIE_NAME = "tf_session"

# backend/app/services/auth.py:181-209
def is_valid_session(token: str) -> bool:
    """检查会话是否有效(存在且未过期)。"""
    if not token:
        return False
    with _lock:
        session = _sessions.get(token)
        if session is None:
            return False
        if time.time() > session["expires_at"]:
            _sessions.pop(token, None)
            _persist_sessions_locked()
            return False
        return True

def resolve_authenticated_reviewer(token: str | None) -> str | None:
    """Resolve the server-stored opaque reviewer identity for one valid session."""
    if not token:
        return None
    with _lock:
        session = _sessions.get(token)
        if session is None or time.time() > session["expires_at"]:
            if session is not None:
                _sessions.pop(token, None)
                _persist_sessions_locked()
            return None
        principal = session.get("reviewer_principal")
        return principal if isinstance(principal, str) and principal else None
```

**WS handshake auth pattern:**
```python
from app.api.auth import COOKIE_NAME
from app.services import auth

@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket):
    token = websocket.cookies.get(COOKIE_NAME)  # "tf_session"
    if not token or not auth.is_valid_session(token):
        await websocket.close(code=4001, reason="未登录或会话已过期")
        return
    principal = auth.resolve_authenticated_reviewer(token)
    if not principal:
        await websocket.close(code=4001, reason="principal 解析失败")
        return
    # 鉴权通过, 进入连接处理循环
```

**security_middleware.py reference** (`security_middleware.py:71-103`): HTTP middleware extracts Cookie + resolves principal for HTTP requests. WS handshake replicates the same logic inline (middleware doesn't cover WS).

---

### Audit — ToolCallEnvelope (WS Connection Lifecycle)

**Source:** `backend/app/audit/envelope.py:364-442` + `backend/app/audit/service.py:19`
**Apply to:** `backend/app/ws/handler.py`

```python
# backend/app/audit/service.py:19
def get_audit_repo() -> ToolCallAuditRepository | None:
    """获取全局审计 repository, 未注入时返回 None。"""
    return _audit_repo

# backend/app/audit/envelope.py:364-442 — AuditContext
class AuditContext:
    """上下文管理器: 自动记录工具调用的开始/结束/耗时/错误。"""
    def __init__(self, repo, *, tool, category, params=None, version=None, scope=None, principal=None):
        ...
    def __enter__(self) -> "AuditContext":
        self._t0 = time.monotonic()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        duration_ms = (time.monotonic() - self._t0) * 1000
        if exc_val is not None:
            self._error = str(exc_val)
        self._repo.append(tool=..., scope=..., principal=..., duration_ms=..., ...)
        return False
    def set_response(self, *, shape=None, summary=None, raw=None, ...):
        ...
```

**WS audit integration pattern:**
```python
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

---

### Error Handling — Connection Lifecycle

**Source:** `backend/app/services/stockdb_ws.py:157-190` (reconnect loop) + `backend/app/api/intraday.py:256-257` (finally unsubscribe)
**Apply to:** `backend/app/ws/handler.py`

**SSE finally cleanup** (`intraday.py:256-257`):
```python
    finally:
        qs.unsubscribe(sub)
```

**stockdb_ws reconnect** (`stockdb_ws.py:157-190`):
```python
async def _run(self) -> None:
    """重连循环: 连接 → resume → 全量重订阅 → 读循环分发。"""
    backoff = 0
    try:
        while not self._closing:
            try:
                async with websockets.connect(...) as ws:
                    backoff = 0
                    self._connected = True
                    await self._after_connect(ws)
                    await self._read_loop(ws)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._connected = False
                backoff += 1
                delay = min(1.0 * 2 ** min(backoff, 6), 60.0) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
    except asyncio.CancelledError:
        pass
    finally:
        self._connected = False
```

**WS handler error handling:**
```python
from fastapi import WebSocketDisconnect

conn = await manager.connect(websocket, principal)
try:
    await _handle_connection(conn)
except WebSocketDisconnect:
    manager.disconnect(conn)
```

---

### Keepalive — Application Layer Ping

**Source:** `backend/app/services/wecom_bot_service.py:229-246` (30s business-layer ping)
**Apply to:** `backend/app/ws/handler.py`

```python
# wecom_bot_service.py:229-246 — 应用层心跳
async def _maintain_connection(self, ws) -> None:
    """连接保持阶段: 每 30s 发 ping, 同时接收服务端推送。"""
    while self._running:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=_HEARTBEAT_INTERVAL)
            self._log_incoming(raw)
            continue
        except asyncio.TimeoutError:
            pass  # 接收超时 → 到了心跳时间
        await ws.send(json.dumps({"cmd": "ping"}))

# stockdb_ws.py:168-169 — websockets 库 ping_interval (客户端侧)
async with websockets.connect(
    self._url,
    ping_interval=20,
    ping_timeout=20,
    close_timeout=5,
) as ws:
```

**WS server keepalive pattern (D-12 correction — Starlette has no ping_interval):**
```python
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

---

### Validation — Input Validation (WS Messages)

**Source:** `frontend/src/lib/backtestTask.ts:78-167` (runtime type guards)
**Apply to:** `frontend/src/lib/wsProtocol.ts`

```typescript
// backtestTask.ts:78-167 — runtime type validation for stream payloads
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isStrategyBacktestResult(value: unknown): value is StrategyBacktestResult {
  // ... comprehensive structural validation
}
```

---

### Testing — FastAPI WebSocket TestClient

**Source:** FastAPI WebSocket testing docs
**Apply to:** `backend/tests/test_ws_*.py` (7 new test files)

```python
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

---

### Connection Status Store — useSyncExternalStore

**Source:** `frontend/src/lib/useQuoteStream.ts:41-78`
**Apply to:** `frontend/src/lib/useWsStream.ts`

```typescript
// useQuoteStream.ts:41-78
export type QuoteStreamStatus = 'connected' | 'reconnecting' | 'disconnected'

let _streamStatus: QuoteStreamStatus = 'disconnected'
const _statusListeners = new Set<() => void>()

function _emitStatus() { _statusListeners.forEach((fn) => fn()) }
function _setStatus(s: QuoteStreamStatus) { ... }
function _subscribeStatus(fn: () => void) { ... }
function _getStatus() { return _streamStatus }

export function useQuoteStreamStatus(): QuoteStreamStatus {
  return useSyncExternalStore(_subscribeStatus, _getStatus, () => 'disconnected' as const)
}
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/app/ws/__init__.py` (NEW) | config | — | Trivial package marker; no analog needed (copy any `__init__.py`) |
| `frontend/src/lib/wsProtocol.ts` (NEW) | utility | transform | No existing TS protocol file; derive from `stockdb_ws.py` Python protocol + D-05 spec |

## Metadata

**Analog search scope:** `backend/app/api/`, `backend/app/services/`, `backend/app/audit/`, `backend/app/bootstrap.py`, `backend/app/main.py`, `frontend/src/lib/`, `frontend/src/pages/backtest/`, `frontend/src/components/Layout.tsx`
**Files scanned:** 30+ source files
**Pattern extraction date:** 2026-08-21
