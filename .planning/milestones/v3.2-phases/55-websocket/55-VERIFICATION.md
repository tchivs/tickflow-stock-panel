---
phase: 55-websocket
verified: 2026-08-22T03:16:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 55: WebSocket 全量迁移 Verification Report

**Phase Goal:** 从单向 SSE 轮询升级为 WebSocket 双向通信 — 服务端可主动推送, 浏览器实时接收, 保留断连重连不丢失事件语义。
**Verified:** 2026-08-22T03:16:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

The 4 roadmap Success Criteria are the governing contract. PLAN frontmatter truths add plan-specific detail but cannot subtract from these. All truths below map to the roadmap SCs plus requirement IDs WS-01 through WS-04.

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | 服务端 WebSocket 端点 (`/ws/stream`) 支持多客户端并发连接, 按 session token 鉴权; 连接生命周期审计记录复用 ToolCallEnvelope (scope=ws) | ✓ VERIFIED | `backend/app/ws/handler.py:21-82` — `ws_stream` extracts `tf_session` Cookie, calls `auth.is_valid_session` + `resolve_authenticated_reviewer`, rejects with `close(4001)` on failure. `AuditContext(repo, tool="connection", scope="ws", principal=...)` wraps the message loop (lines 53-68). `main.py:314` registers `app.websocket("/ws/stream")(ws_stream)`. `bootstrap.py:462-470` initializes `ConnectionManager`, sets `app.state.ws_manager`, calls `qs.attach_ws_manager`. Tests: `test_ws_connection.py::test_ws_auth` (valid Cookie → connected msg), `test_ws_connection.py::test_ws_reject_invalid_session` (close 4001), `test_ws_audit.py::test_audit_on_connect` (scope=ws audit record). |
| 2 | 现有 4 处 SSE 流 (walkforward / optimizer / mining / quoteStream) 全部迁移到 WebSocket 传输; 断连重连后通过 Last-Event-ID 语义恢复, 不丢失也不发明事件 | ✓ VERIFIED | **SSE deletion:** `grep EventSourceResponse backend/app/` → 0; `grep "from sse_starlette" backend/app/` → 0; `grep "text/event-stream" backend/app/api/` → 0; `grep "application/x-ndjson" backend/app/api/` → 0; `grep "sse-starlette" pyproject.toml` → 0; `useQuoteStream.ts` deleted; `QuoteSubscriber` removed from `quote_service.py`. **WS broadcast:** All 8 QuoteService events broadcast via `_ws_broadcast` (quotes/alerts/portfolio/review/depth/analysis/advanced/strategy_results — `quote_service.py:314-470`); 3 backtest task flows via `_ws_broadcast(request, run:{job_key}, ...)` in `backtest.py` (POST /strategy/start, /optimize/start, /walkforward/start); mining/alpha/walkforward_sse/forecast all have `_ws_broadcast` helpers. 5 ndjson streams via `request_dispatcher.py` (analysis_meta→delta→done). **Last-Event-ID → seq resume:** `connection_manager.py:45-47` `replay_after(last_seq)` replays from per-principal ring buffer (deque maxlen=1000); `handler.py:148-156` handles `resume` message. Tests: `test_ws_seq.py::test_resume_replay`, `test_ws_seq::test_ring_overflow`, `test_ws_sse_removed.py` (11 tests), `test_ws_quotes.py` (8 tests), `test_ws_task.py` (11 tests), `test_ws_ndjson.py` (7 tests). |
| 3 | 多个实时流 (运行进度 + 行情 + 告警) 共享同一 WebSocket 连接, 通过消息 `type` 字段路由, 不为每类流新建连接 | ✓ VERIFIED | **Backend channel filter:** `connection_manager.py:103-119` `broadcast_to_channel` only sends to connections where `channel in conn.channels`. **Frontend single connection:** `useWsStream.ts` module-level `_ws: WebSocket` (global singleton, D-09); `subscribe(channel, handler)` registers to `_channelHandlers` Map; `_typeBelongsToChannel` routes by channel prefix → event type set (`RUN_CHANNEL_EVENTS`, `ANALYSIS_CHANNEL_EVENTS`, `REVIEW_CHANNEL_EVENTS`). All 7 task flows + 5 ndjson consumers + AlphaWorkbench + WalkForward call `wsStream.subscribe('run:{id}', ...)` or `subscribe('analysis:{symbol}', ...)` on the same hook. `Layout.tsx:484` calls `useWsStream(realtimeEnabled, ...)` once. Tests: `test_ws_channels.py::test_channel_filter` (A subscribed, B not → only A receives), `test_ws_channels.py::test_subscribe/unsubscribe`, `test_ws_quotes.py::test_multi_channel_one_connection`, `useWsStream.test.tsx` channel routing (5 tests). |
| 4 | WebSocket 连接有服务端 ping/keepalive 心跳; 客户端断连后指数退避自动重连; 连接状态 (connected/reconnecting/disconnected) 对用户可见 | ✓ VERIFIED | **Server keepalive:** `handler.py:48` `asyncio.create_task(_keepalive(conn, KEEPALIVE_INTERVAL))`; `handler.py:202-216` `_keepalive` sends `{type:"ping", seq:N, data:{}}` every 30s (D-12 correction: application-layer, not protocol ping_interval); `protocol.py:73` `KEEPALIVE_INTERVAL = 30.0`. **Client backoff:** `wsProtocol.ts:43` `BACKOFF_STEPS = [1000, 2000, 4000, 8000, 16000, 30000]` (D-13); `useWsStream.ts:190-199` `_scheduleReconnect` uses `BACKOFF_STEPS[_backoffIndex]`; on reconnect sends `resume(last_seq)` + resubscribes channels. **Connection status UI:** `Layout.tsx:486` `useWsStreamStatus()` via `useSyncExternalStore` (`useWsStream.ts:126-128`); 3-state indicator (connected `bg-accent` / reconnecting `bg-warning animate-pulse` / disconnected `bg-danger`); reconnecting banner `role="status" aria-live="polite"` (line 1046-1048); disconnected banner `role="alert" aria-live="assertive"` + "重新连接" button calling `_reconnect()` (lines 1057-1069). Tests: `test_ws_keepalive.py::test_ping`, `useWsStream.test.tsx::test_backoff_sequence`, `test_resume_on_reconnect`, `test_resubscribe_on_reconnect`, `test_status_store`, `test_seq_advancement`. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/app/ws/__init__.py` | WS package marker | ✓ VERIFIED | Exists, 45B |
| `backend/app/ws/connection_manager.py` | ConnectionManager + WsConnection with per-principal seq + ring buffer | ✓ VERIFIED | 4.5KB; `WsConnection` (channels/seq/_ring deque maxlen=1000), `ConnectionManager` (connect/disconnect/broadcast_to_channel, per-principal `_principal_rings`/`_principal_seq` persistence, `set_main_loop`/`get_main_loop`) |
| `backend/app/ws/protocol.py` | Message protocol constants + make_msg factory | ✓ VERIFIED | `CLIENT_MSG_TYPES`, `SERVER_EVENT_TYPES` (30+ event types), `RING_SIZE=1000`, `MAX_CHANNELS_PER_CONNECTION=50`, `KEEPALIVE_INTERVAL=30.0`, `make_msg(type, seq, data)` |
| `backend/app/ws/handler.py` | /ws/stream endpoint handler with auth + audit + keepalive + message loop | ✓ VERIFIED | Cookie auth (close 4001), connected welcome msg, keepalive task, AuditContext(scope=ws), _message_loop (subscribe/unsubscribe/resume/request), _verify_run_ownership (T-55-02) |
| `backend/app/ws/channels.py` | Channel name constants + CHANNEL_EVENT_MAP | ✓ VERIFIED | QUOTES/ALERTS/PORTFOLIO/REVIEW/DEPTH + RUN_PREFIX/ANALYSIS_PREFIX + event mapping |
| `backend/app/ws/request_dispatcher.py` | ndjson request message dispatcher → LLM stream → channel push | ✓ VERIFIED | `dispatch()` routes analysis:{symbol}→financials/stock_analysis/strategy, review→market_recap/rps; sends meta→delta→done; validates channel+params (T-55-06); MAX_PENDING_REQUESTS=5 (T-55-07) |
| `backend/app/ws/broadcast.py` | Thread-safe broadcast_from_thread helper | ✓ VERIFIED | `broadcast_from_thread(ws_manager, channel, msg_type, data)` via `asyncio.run_coroutine_threadsafe` to main loop |
| `frontend/src/lib/useWsStream.ts` | Global single-connection WS hook | ✓ VERIFIED | Module-level `_ws` singleton, `useSyncExternalStore` status, `subscribe/unsubscribe/request/_reconnect/getCurrentBackoffSeconds`, `AsyncQueue` class, `setFocusSymbol/clearFocusSymbol`, channel event type routing (`_typeBelongsToChannel`) |
| `frontend/src/lib/wsProtocol.ts` | TypeScript message protocol types | ✓ VERIFIED | `WsMessage`, `SubscribeMessage`, `ResumeMessage`, `RequestMessage`, `WsStatus`, `BACKOFF_STEPS=[1000,2000,4000,8000,16000,30000]`, `FAILS_BEFORE_TOAST=3`, `isWsMessage` guard |
| `backend/tests/test_ws_*.py` | 11 WS test files | ✓ VERIFIED | test_ws_endpoint, test_ws_connection, test_ws_seq, test_ws_channels, test_ws_keepalive, test_ws_audit, test_ws_quotes, test_ws_task, test_ws_ndjson, test_ws_sse_removed, test_ws_background_broadcast — 52 WS tests pass |
| `frontend/src/lib/useWsStream.test.tsx` | WS hook + AsyncQueue + channel routing tests | ✓ VERIFIED | 24 tests (7 wsProtocol guard + 7 useWsStream behavior + 5 AsyncQueue + 5 channel routing) — all pass |
| `frontend/src/lib/backtestTask.test.tsx` | backtest task WS migration test | ✓ VERIFIED | 6 tests (subscribe run channel, job progress/done/error handlers, cancel POST, reconnect resubscribe) — all pass |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `bootstrap.py` lifespan | `ConnectionManager` init | `ConnectionManager()` → `app.state.ws_manager` → `qs.attach_ws_manager(ws_manager)` + `ws_manager.set_main_loop(loop)` | ✓ WIRED | `bootstrap.py:462-470` |
| `main.py` | `/ws/stream` endpoint | `app.websocket("/ws/stream")(ws_stream)` | ✓ WIRED | `main.py:311-314` |
| `QuoteService._broadcast_quote_updated` | `ws_manager.broadcast_to_channel('quotes', ...)` | `_ws_broadcast_quotes()` → `_ws_broadcast("quotes", "quotes_updated", ...)` → `broadcast_from_thread` | ✓ WIRED | `quote_service.py:312, 326-334` |
| `QuoteService` all 8 events | WS channel broadcast | `_ws_broadcast(channel, msg_type, data)` for quotes/alerts/portfolio/review/depth/analysis/advanced/strategy_results | ✓ WIRED | `quote_service.py:314-470` (8 broadcast calls) |
| `backtest.py` 3 task flows | `run:{job_key}` channel | `_ws_broadcast(request, f"run:{job_key}", "job_progress"/"job_done"/"job_error", data)` in POST /strategy/start, /optimize/start, /walkforward/start | ✓ WIRED | `backtest.py:608-1062` (19 `_ws_broadcast` calls across 3 endpoints) |
| `mining.py` events | `run:{run_id}` channel | `_ws_broadcast` + `_ws_broadcast_async` | ✓ WIRED | `mining.py:46-59` |
| `research_alpha_sse.py` alpha events | `run:{run_id}` channel | `_ws_broadcast` via `_stream_with_ws` wrapper | ✓ WIRED | `research_alpha_sse.py:56-63` |
| `walkforward_sse.py` plan events | `run:{plan_id}` channel | `_ws_broadcast` | ✓ WIRED | `walkforward_sse.py:25-32` |
| `forecast/api.py` job events | `run:{job_id}` channel | `_ws_broadcast` | ✓ WIRED | `forecast/api.py:24-31` |
| `handler.py` request branch | `request_dispatcher.dispatch` | `asyncio.create_task(_dispatch_request(conn, channel, params, app_state))` | ✓ WIRED | `handler.py:165-189` |
| `Layout.tsx` | `useWsStream` + `useWsStreamStatus` | `useWsStream(realtimeEnabled, ...)` + `useWsStreamStatus()` + `_reconnect()` + `getCurrentBackoffSeconds()` | ✓ WIRED | `Layout.tsx:5, 484, 486` |
| `useWsStream` onopen | resume + resubscribe | `ws.send({type:'resume', last_seq:_seq})` + `ws.send({type:'subscribe', channels})` | ✓ WIRED | `useWsStream.ts` onopen handler |
| `api.ts` 5 ndjson streams | `useWsStream.request` + `subscribe` + `AsyncQueue` | `wsRequest(channel, params)` + `subscribe(channel, handler)` + `AsyncQueue` async generator | ✓ WIRED | `api.ts:6, 3442-3946` (5 stream functions) |
| `backtestTask.ts` | POST /strategy/start + WS subscribe | `fetch('/api/backtest/strategy/start', {method:'POST'})` → `wsStream.subscribe('run:${jobKey}', handler)` | ✓ WIRED | `backtestTask.ts:3, 237, 398` |
| `backtestTask.ts` cancel | POST /strategy/cancel | `fetch('/api/backtest/strategy/cancel', {method:'POST'})` | ✓ WIRED | `backtestTask.ts:63, 315` (cancel still POST, not WS) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `quote_service.py` WS broadcast | `_ws_broadcast` calls | `QuoteService._broadcast_quote_updated/_broadcast_alerts/notify_portfolio_updated/push_review_event/notify_depth_updated/notify_analysis_progress/notify_advanced_progress/notify_strategy_results_updated` | Real market data (ts, symbol_count, alerts, account_ids, progress) | ✓ FLOWING |
| `backtest.py` WS broadcast | `_ws_broadcast(request, run:{job_key}, ...)` | Backtest job thread → `job.progress.append(d)` → broadcast job_progress | Real backtest progress (day/total/equity) | ✓ FLOWING |
| `request_dispatcher.py` | `analysis_delta` / `review_delta` | LLM stream generators (`analyze_financials_stream`, `analyze_stock_stream`, `recap_market_stream`, `analyze_rotation_stream`, `AIStrategyGenerator`) | Real LLM-generated content chunks | ✓ FLOWING |
| `useWsStream.ts` | `_channelHandlers` Map → handler calls | WebSocket onmessage → JSON parse → seq advance → type routing → handler | Real WS messages from server broadcasts | ✓ FLOWING |
| `api.ts` AsyncQueue | `queue.push(msg)` | `subscribe(channel, handler)` handler pushes on analysis_meta/delta/done events → async generator yields | Real LLM stream events from WS channel | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Backend WS tests (11 files, 52 tests) | `cd backend && .venv/bin/python -m pytest tests/test_ws_*.py -q` | 52 passed | ✓ PASS |
| Backend SSE removal + guard tests | `cd backend && .venv/bin/python -m pytest tests/test_ws_sse_removed.py tests/test_phase50_guard.py -q` | 90 passed (11 + 79) | ✓ PASS |
| Frontend WS tests (4 files, 81 tests) | `cd frontend && npx vitest run --reporter=verbose` | 81 passed | ✓ PASS |
| SSE remnants in backend/app | `grep -rc "EventSourceResponse\|from sse_starlette\|text/event-stream" backend/app/api/` | 0 matches | ✓ PASS |
| sse-starlette in pyproject.toml | `grep "sse-starlette" backend/pyproject.toml` | 0 matches | ✓ PASS |
| QuoteSubscriber removed | `grep "QuoteSubscriber" backend/app/services/quote_service.py` | 0 matches | ✓ PASS |
| useQuoteStream.ts deleted | `test ! -f frontend/src/lib/useQuoteStream.ts` | true | ✓ PASS |
| new EventSource in frontend src | `grep -rc "new EventSource" frontend/src/ --include="*.ts*"` | 0 (only in test description string) | ✓ PASS |
| useWsStream in Layout.tsx | `grep -c "useWsStream" frontend/src/components/Layout.tsx` | 3 (import + hook + status) | ✓ PASS |
| BACKOFF_STEPS correct values | `grep "1000, 2000, 4000, 8000, 16000, 30000" frontend/src/lib/wsProtocol.ts` | 1 match | ✓ PASS |
| WS broadcast in quote_service | `grep -c "_ws_broadcast" backend/app/services/quote_service.py` | ≥8 (all event types) | ✓ PASS |
| WS broadcast in backtest | `grep -c "_ws_broadcast" backend/app/api/backtest.py` | 19 (3 task flows) | ✓ PASS |
| request_dispatcher analysis_delta/done | `grep -c "analysis_delta\|analysis_done\|review_delta\|review_done" backend/app/ws/request_dispatcher.py` | present | ✓ PASS |

### Probe Execution

No conventional probe scripts (`scripts/*/tests/probe-*.sh`) declared in this phase's PLAN/SUMMARY. Behavioral spot-checks above serve as probe equivalents.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| WS-01 | 55-01 | 服务端 WebSocket 端点 (`/ws/stream`) 支持多客户端连接, 按 principal 鉴权, 替代现有 SSE 端点 | ✓ SATISFIED | `/ws/stream` registered in main.py:314; Cookie auth (close 4001) in handler.py:31-38; AuditContext(scope=ws) in handler.py:55-66; 11 backend WS test files pass |
| WS-02 | 55-02, 55-03, 55-04 | 现有 SSE 流全部迁移到 WebSocket 传输, 保留 Last-Event-ID 语义 | ✓ SATISFIED | All 8 SSE + 5 ndjson endpoints deleted (grep=0); all broadcasts via WS channels; 7 frontend EventSource + 5 ndjson + 1 fetch SSE consumers migrated to useWsStream; seq ring buffer resume replaces Last-Event-ID; test_ws_sse_removed.py 11 tests pass |
| WS-03 | 55-01, 55-03 | WebSocket 连接复用 — 多个实时流共享同一连接, 通过消息类型路由 | ✓ SATISFIED | useWsStream module-level singleton `_ws`; backend broadcast_to_channel channel filter; frontend _typeBelongsToChannel routing (run/analysis/review event sets); test_ws_channels + channel routing tests pass |
| WS-04 | 55-01 | WebSocket 连接心跳与自动重连 — 服务端 ping/keepalive, 客户端指数退避重连, 连接状态可见 | ✓ SATISFIED | Application-layer keepalive 30s (handler.py:202-216); BACKOFF_STEPS [1000..30000] (wsProtocol.ts:43); 3-state status UI (Layout.tsx:489-508); test_ws_keepalive + backoff/resume/resubscribe/status tests pass |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `backend/app/data_providers/xyz_provider.py` | 308 | `text/event-stream` in Accept header | ℹ️ Info | External HTTP client header to third-party MCP, not an SSE endpoint — out of phase scope, pre-existing |
| `frontend/src/lib/backtestTask.test.tsx` | 74 | `new EventSource` in test description string | ℹ️ Info | Test name documents "不创建 new EventSource" — not actual EventSource usage |

No TBD/FIXME/XXX debt markers found in any phase-modified files. No stubs, placeholders, or empty implementations detected.

### Human Verification Required

None — all truths verified with codebase evidence + passing behavioral tests.

### Gaps Summary

No gaps found. All 4 roadmap success criteria are verified as TRUE in the codebase:

1. **WS-01** — `/ws/stream` endpoint with Cookie session auth (close 4001 on invalid), connection lifecycle audit (scope=ws), multi-client support. ✓
2. **WS-02** — All 8 SSE + 5 ndjson endpoints deleted (grep=0); all event broadcasts migrated to WS channels; seq ring buffer (deque maxlen=1000) + resume message replaces Last-Event-ID semantics; sse-starlette dependency removed; QuoteSubscriber SSE mode deleted; useQuoteStream.ts deleted. ✓
3. **WS-03** — Single global WS connection (useWsStream module singleton); subscribe/unsubscribe channel multiplexing; backend channel filter; frontend event type routing (run/analysis/review channel event sets). ✓
4. **WS-04** — Application-layer 30s ping keepalive; client exponential backoff [1000,2000,4000,8000,16000,30000]ms; 3-state connection status UI (connected/reconnecting/disconnected) with accessibility annotations. ✓

D-03 (no rollback) fully executed: SSE code deleted, dependency removed, no fallback path.
Channel naming per D-08: quotes, alerts, portfolio, run:{run_id}, analysis:{symbol}, review, depth — all present in `channels.py` + `protocol.py`.
Per-principal seq + ring buffer persistence across reconnects (Summary 01 deviation auto-fix: `_principal_rings`/`_principal_seq` in ConnectionManager).

---

_Verified: 2026-08-22T03:16:00Z_
_Verifier: Claude (gsd-verifier)_
