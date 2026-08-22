---
phase: 55-websocket
plan: 04
subsystem: websocket-transport
tags: [websocket, realtime, sse-removal, ndjson, d03-no-rollback]
dependency:
  requires:
    - "backend/app/ws/ module (ConnectionManager, WsConnection, protocol, handler, channels)"
    - "/ws/stream WebSocket endpoint with Cookie auth"
    - "backend/app/ws/request_dispatcher.py (ndjson request dispatch)"
    - "backend/app/ws/broadcast.py (broadcast_from_thread helper)"
    - "frontend/src/lib/useWsStream.ts (Plan 01: subscribe/request/reconnect)"
    - "frontend/src/lib/backtestTask.ts (Plan 03: WS subscribe)"
  provides:
    - "All SSE/ndjson endpoint code deleted from backend (D-03 no rollback)"
    - "sse-starlette dependency removed from pyproject.toml"
    - "QuoteSubscriber SSE subscriber mode deleted, WS broadcast only"
    - "POST /strategy/start, /optimize/start, /walkforward/start endpoints (replace SSE GET streams)"
    - "test_ws_sse_removed.py: 11 tests verifying complete SSE deletion"
    - "test_phase50_guard.py: dependency baseline updated (sse-starlette removed)"
    - "Frontend useQuoteStream.ts deleted + SSE URL functions removed"
    - "CHANGELOG.md: Phase 55 WebSocket migration entry"
  affects:
    - "backend/app/api/intraday.py (quote_stream deleted)"
    - "backend/app/api/mining.py (stream_events deleted)"
    - "backend/app/api/research_alpha_sse.py (SSE endpoint deleted, _stream_events kept with local ServerSentEvent dataclass)"
    - "backend/app/api/walkforward_sse.py (stream_walk_forward deleted)"
    - "backend/app/api/backtest.py (3 SSE functions deleted, 3 POST /start endpoints added)"
    - "backend/app/forecast/api.py (job_events deleted, _event_stream/_sse helpers deleted)"
    - "backend/app/api/financials.py (ndjson POST endpoint deleted)"
    - "backend/app/api/market_recap.py (ndjson POST endpoint deleted)"
    - "backend/app/api/rps.py (ndjson POST endpoint deleted)"
    - "backend/app/api/stock_analysis.py (ndjson POST endpoint deleted)"
    - "backend/app/api/strategy.py (ndjson POST endpoint deleted)"
    - "backend/app/services/quote_service.py (QuoteSubscriber class + subscribe/unsubscribe deleted)"
    - "backend/pyproject.toml (sse-starlette removed)"
    - "backend/tests/test_phase50_guard.py (baseline + assertions updated)"
    - "backend/tests/research/test_research_alpha_sse.py (endpoint tests removed)"
    - "frontend/src/lib/useQuoteStream.ts (deleted)"
    - "frontend/src/lib/api.ts (alphaRunStreamUrl deleted)"
    - "frontend/src/lib/backtestTask.ts (fetch-to-SSE → POST /strategy/start)"
    - "frontend/src/lib/optimizerTask.ts (fetch-to-SSE → POST /optimize/start)"
    - "frontend/src/lib/walkforwardTask.ts (fetch-to-SSE → POST /walkforward/start)"
    - "docs/phase50_release_evidence.md (updated for Phase 55 SSE removal)"
    - "CHANGELOG.md (Phase 55 entry added)"
tech-stack:
  added: []
  removed:
    - "sse-starlette (SSE transport dependency, D-03 no rollback)"
  patterns:
    - "POST /start → job_key + WS channel subscription (replaces GET SSE stream)"
    - "Local ServerSentEvent dataclass (replaces sse_starlette.ServerSentEvent for _stream_events generator)"
    - "No-op clear_pending_alerts (SSE subscribers removed, method kept for API compat)"
key-files:
  modified:
    - backend/app/api/intraday.py
    - backend/app/api/mining.py
    - backend/app/api/research_alpha_sse.py
    - backend/app/api/walkforward_sse.py
    - backend/app/api/backtest.py
    - backend/app/forecast/api.py
    - backend/app/api/financials.py
    - backend/app/api/market_recap.py
    - backend/app/api/rps.py
    - backend/app/api/stock_analysis.py
    - backend/app/api/strategy.py
    - backend/app/services/quote_service.py
    - backend/pyproject.toml
    - backend/tests/test_phase50_guard.py
    - backend/tests/research/test_research_alpha_sse.py
    - frontend/src/lib/api.ts
    - frontend/src/lib/backtestTask.ts
    - frontend/src/lib/optimizerTask.ts
    - frontend/src/lib/walkforwardTask.ts
    - frontend/src/lib/useWsStream.ts
    - docs/phase50_release_evidence.md
    - CHANGELOG.md
  created:
    - backend/tests/test_ws_sse_removed.py
  deleted:
    - frontend/src/lib/useQuoteStream.ts
decisions:
  - "POST /start endpoints replace SSE GET streams: Task startup (job creation + thread launch + WS broadcast) moved to POST endpoints returning {key: job_key}, frontend subscribes to WS channel for progress (Rule 3 auto-fix: SSE deletion broke task startup path)"
  - "Local ServerSentEvent dataclass: sse_starlette.ServerSentEvent replaced with a frozen dataclass in research_alpha_sse.py to keep _stream_events generator working after sse-starlette dependency removal"
  - "clear_pending_alerts kept as no-op: method called from data.py, empty body (no SSE subscribers to clear); removing the call would be out of scope"
  - "test_research_alpha_sse TestStreamEndpoint removed: SSE endpoint tests for deleted /runs/{run_id}/stream endpoint; _stream_events generator tests retained"
metrics:
  duration: ~30min
  completed: "2026-08-21"
  tasks: 2
  commits: 3
actuals:
  tokens: 95000
  tasks: 2
  commits: 3
status: complete
---

# Phase 55 Plan 04: SSE/ndjson 代码删除 (D-03 无回退路径) Summary

执行 D-03 无回退路径决策: 删除全部 SSE/ndjson 端点代码 + EventSource 消费者 + sse-starlette 依赖 + 相关测试基线。此前 Plans 01-03 已建立 WS 传输并迁移全部广播与消费, 此 plan 清除旧传输残留, 完成全量迁移闭环。

## What Was Done

### Task 1: 后端 SSE/ndjson 端点删除 + 依赖移除 + test_guard 更新

- **8 处 SSE 端点删除**:
  - `intraday.py::quote_stream` + `EventSourceResponse` import
  - `mining.py::stream_events` + `EventSourceResponse` import + `_SSE_HEARTBEAT_SECONDS`
  - `research_alpha_sse.py::stream_run_events` SSE endpoint (保留 `_stream_events` generator + ledger 查询函数)
  - `walkforward_sse.py::stream_walk_forward` + `StreamingResponse` import
  - `backtest.py` 3 处 SSE: `strategy_stream`/`optimize_stream`/`walkforward_stream` + `StreamingResponse` import
  - `forecast/api.py::job_events` + `_event_stream`/`_sse` helpers + `StreamingResponse` import

- **5 处 ndjson POST 端点删除** (StreamingResponse application/x-ndjson 包装):
  - `financials.py::analyze_financials` POST endpoint
  - `market_recap.py::analyze_market` POST endpoint
  - `rps.py::analyze_rotation` POST endpoint
  - `stock_analysis.py::analyze_stock` POST endpoint
  - `strategy.py::build_strategy_stream` POST endpoint

- **3 处 POST /start 端点新增** (替代 SSE GET 流, Rule 3 自动修复):
  - `POST /api/backtest/strategy/start` — 启动策略回测, 返回 `{key: job_key}`, 进度走 WS
  - `POST /api/backtest/optimize/start` — 启动参数优化, 返回 `{key: job_key}`
  - `POST /api/backtest/walkforward/start` — 启动 walk-forward, 返回 `{key: job_key}`
  - 前端 `backtestTask.ts`/`optimizerTask.ts`/`walkforwardTask.ts` 从 fetch-to-SSE 改为 POST `/start`

- **QuoteSubscriber SSE 订阅者模式删除** (`quote_service.py`):
  - 删除 `QuoteSubscriber` 类 (44-182 行)
  - 删除 `subscribe`/`unsubscribe`/`_snapshot_subscribers` 方法
  - 删除 `self._subscribers` 属性
  - 移除所有 broadcast 方法中的 SSE subscriber 循环 (`for sub in self._snapshot_subscribers()`)
  - 保留 `_ws_broadcast`/`broadcast_to_channel` WS 广播路径

- **sse-starlette 依赖移除** (`pyproject.toml`): 从 `[project.dependencies]` 移除 `sse-starlette>=2.0`

- **test_phase50_guard.py 更新**:
  - `_DEPENDENCY_BASELINE`: 移除 `sse-starlette>=2.0`
  - `_STREAMING_TOKENS`: 移除 `EventSourceResponse`/`sse_starlette`
  - `test_sse_scope_streaming_tokens_only_in_sse_module`: 改为验证无模块包含 streaming token
  - 移除 sse-starlette 存在断言 + release evidence doc 引用
  - 重命名 `test_module_graph_sse_router_wired_in_main` → `test_module_graph_alpha_router_wired_in_main`

- **research_alpha_sse.py**: `sse_starlette.ServerSentEvent` → 本地 `@dataclass(frozen=True)` (保留 `_stream_events` generator 供 WS dispatcher)

- **test_ws_sse_removed.py** (11 tests): grep 断言验证 SSE 代码完全删除 + WS 广播回归

### Task 2: 前端 SSE 残留删除 + CHANGELOG

- **useQuoteStream.ts 删除**: 整个文件删除 (Plan 01 `useWsStream` 替代)
- **api.ts `alphaRunStreamUrl` 删除**: SSE URL 构造函数删除
- **useWsStream.ts**: 移除 `useQuoteStream.ts` 引用注释
- **CHANGELOG.md**: 追加 Phase 55 WebSocket 全量迁移条目

## Verification

### Backend (130 tests, all passing)
```
cd backend && python -m pytest tests/test_ws_sse_removed.py tests/test_phase50_guard.py \
  tests/test_ws_endpoint.py tests/test_ws_connection.py tests/test_ws_seq.py \
  tests/test_ws_channels.py tests/test_ws_keepalive.py tests/test_ws_audit.py \
  tests/test_ws_quotes.py tests/test_ws_task.py tests/test_ws_ndjson.py -x -q
→ 130 passed
```

### Research tests (11 tests, all passing)
```
cd backend && python -m pytest tests/research/test_research_alpha_sse.py -x -q
→ 11 passed
```

### Acceptance grep checks
- `grep -rc --include="*.py" "EventSourceResponse" backend/app/` → 0 ✓
- `grep -rc --include="*.py" "from sse_starlette" backend/app/` → 0 ✓
- `grep -rc --include="*.py" "text/event-stream" backend/app/` (excl data_providers) → 0 ✓
- `grep -rc --include="*.py" "application/x-ndjson" backend/app/api/` → 0 ✓
- `grep -c "sse-starlette" backend/pyproject.toml` → 0 ✓
- `grep -c "sse-starlette" backend/tests/test_phase50_guard.py` → 0 ✓
- `grep -c "QuoteSubscriber" backend/app/services/quote_service.py` → 0 ✓
- `grep -c "broadcast_to_channel" backend/app/services/quote_service.py` → 1 ✓
- `grep -c "_ws_broadcast" backend/app/api/backtest.py` → 19 ✓ (POST /start endpoints)
- `grep -rc "useQuoteStream" frontend/src/ --include="*.ts"` → 0 ✓
- `grep -rc "alphaRunStreamUrl" frontend/src/ --include="*.ts"` → 0 ✓
- `grep -c "WebSocket\|ws/stream\|useWsStream" CHANGELOG.md` → ≥1 ✓

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] SSE 端点删除破坏任务启动路径**
- **Found during:** Task 1 — 删除 backtest SSE 端点后
- **Issue:** Plan 03 的 `backtestTask.ts`/`optimizerTask.ts`/`walkforwardTask.ts` 用 fetch GET SSE 端点启动任务并获取 job_key, 然后切到 WS 频道。删除 SSE 端点后任务无法启动。
- **Fix:** 新增 `POST /strategy/start`、`/optimize/start`、`/walkforward/start` 端点 — 接收 JSON 参数, 创建 job, 启动后台线程, 广播 job_key 到 WS 频道, 返回 `{key: job_key}`。前端改为 POST 启动 + WS 订阅。
- **Files modified:** backend/app/api/backtest.py, frontend/src/lib/backtestTask.ts, optimizerTask.ts, walkforwardTask.ts
- **Commit:** 4537798e

**2. [Rule 1 - Bug] sse_starlette.ServerSentEvent 依赖问题**
- **Found during:** Task 1 — 移除 sse-starlette 依赖后
- **Issue:** `research_alpha_sse.py` 的 `_stream_events` generator yield `ServerSentEvent` 对象 (来自 sse_starlette), 移除依赖后 import 失败。`test_phase50_guard.py` 和 `test_research_alpha_sse.py` 都依赖这个 generator。
- **Fix:** 用本地 `@dataclass(frozen=True, slots=True) ServerSentEvent` 替代 (data/event/id/comment 属性不变), 保留 `_stream_events` generator 供 WS dispatcher 和测试使用。
- **Files modified:** backend/app/api/research_alpha_sse.py
- **Commit:** 4537798e

**3. [Rule 3 - Blocking] test_research_alpha_sse.py 端点测试**
- **Found during:** Task 1 — 运行测试
- **Issue:** `TestStreamEndpoint` 类测试已删除的 SSE 端点 (`/api/research/alpha/runs/{id}/stream`), `sse_client` fixture 依赖已删除的路由。
- **Fix:** 删除 `TestStreamEndpoint` 类 + `sse_client` fixture + `_parse_sse` helper + 未使用的 import (FastAPI/TestClient)。保留 `_stream_events` generator 测试。
- **Files modified:** backend/tests/research/test_research_alpha_sse.py
- **Commit:** 4537798e

**4. [Rule 1 - Bug] quote_service.py 缩进错误**
- **Found during:** Task 1 — 运行测试
- **Issue:** 删除 SSE subscribe/unsubscribe 方法后, `_broadcast_quote_updated` 方法被错误缩进到 `get_min_interval` 方法内。
- **Fix:** 修正缩进, 添加 section header。
- **Files modified:** backend/app/services/quote_service.py
- **Commit:** 4537798e

## Auth Gates

None — all testing done with mock auth (monkeypatch).

## Known Stubs

None — all code is production implementation.

## Threat Flags

None — T-55-12 (dependency removal) verified by test_ws_sse_removed.py grep assertions + test_phase50_guard dependency baseline; T-55-13 (residual SSE endpoint) verified by grep returning 0; T-55-SC (no new installs) — only dependency removal.

## Self-Check: PASSED

- [x] backend/tests/test_ws_sse_removed.py — FOUND
- [x] backend/pyproject.toml (no sse-starlette) — FOUND
- [x] frontend/src/lib/useQuoteStream.ts — DELETED
- [x] commit fd4d857 — FOUND (RED test)
- [x] commit 4537798e — FOUND (Task 1)
- [x] commit 9db87435 — FOUND (Task 2)
