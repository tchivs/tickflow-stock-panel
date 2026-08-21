# Phase 55: WebSocket 全量迁移 - Context

**Gathered:** 2026-08-20
**Status:** Ready for planning

<domain>
## Phase Boundary

将后端 8 处 SSE 端点 + 4 处 ndjson StreamingResponse + 前端 7 处 EventSource 消费者全部一次性迁移到 WebSocket 双向通信。建立统一 WebSocket 端点 (`/ws/stream`), 实现 JSON `{type, seq, data}` 消息协议, 全局单连接多路复用 (subscribe/unsubscribe 频道), 客户端指数退避重连 + seq 窗口恢复, 协议层 ping 心跳。删除所有 SSE/ndjson 端点和 EventSource 消费者代码。

</domain>

<decisions>
## Implementation Decisions

### SSE 迁移策略
- **D-01:** 真正同时全量迁移 — 8 处后端 SSE 端点 + 4 处 ndjson StreamingResponse + 7 处前端 EventSource 在同一个 Phase 55 内一次性全部迁移到 WebSocket, 不分批次, 没有并行期, 不保留旧 SSE 端点 — **Reversibility:** one-way — 删除所有 SSE 代码后回退需要 git revert 整个 Phase 55
- **D-02:** ndjson 流 (financial_analysis / market_recap / rps_rotation / stock_analysis) 也迁移到 WebSocket — 这些是 POST 请求的 StreamingResponse 流式响应, 迁移后通过 WebSocket 频道订阅 + 流式推送实现等价语义 — **Reversibility:** costly — 4 处端点 + 前端 ReadableStream 消费者需要重写
- **D-03:** 无回退路径 — 迁移后删除所有 SSE 代码 (端点 + EventSource + sse-starlette 依赖), 不保留降级到 SSE 的能力
- **D-04:** TDD — 先写 WebSocket 版本测试 (连接/断连/重连/多路复用/seq 恢复), 再迁移代码, 再跑 e2e 确认

### WebSocket 消息协议
- **D-05:** 消息格式为 JSON `{type: string, seq: number, data: object}` — type 字段路由 (如 'quotes_updated', 'strategy_alert', 'job_progress'), seq 字段单调递增序号, data 字段携带载荷 — **Reversibility:** one-way — 消息协议是 WS 传输层的发布契约
- **D-06:** 断连恢复用 seq 窗口 — 服务端为每个连接维护内存环形缓冲区 (1000 条), 客户端重连时发送 `{type: 'resume', last_seq: N}`, 服务端从 N+1 开始重放
- **D-07:** 客户端订阅频道 — 连接后发送 `{type: 'subscribe', channels: ['quotes', 'alerts', 'run:abc123']}` 订阅, `{type: 'unsubscribe', channels: [...]}` 取消订阅, 服务端只推已订阅频道的事件
- **D-08:** 频道按功能域命名: `quotes` (行情), `alerts` (告警), `portfolio` (持仓), `run:{run_id}` (任务进度), `analysis:{symbol}` (AI 分析), `review` (复盘), `depth` (五档)

### 连接复用与多路复用
- **D-09:** 前端全局单连接 — 整个前端只开一个 WebSocket 连接 (`/ws/stream`), 所有流共享, 通过 subscribe/unsubscribe 频道切换 — **Reversibility:** costly — 前端 7 处 EventSource 全部重写为单 WS 连接 + 频道订阅
- **D-10:** 现有 QuoteSubscriber per-connection 订阅者模式 + QuoteService 广播模式可作为 WS 连接管理参考, 但需要适配到 WS 双向通信 + 频道订阅语义

### WebSocket 鉴权与心跳
- **D-11:** Cookie session 鉴权 — 复用现有 SSE 的 Cookie session, WebSocket 握手时浏览器自动携带 Cookie, 服务端从 Cookie 提取 session 验证, 零额外鉴权代码 — **Reversibility:** reversible — 与现有 SSE 鉴权一致
- **D-12:** 协议层 ping 心跳 — 用 websockets 库的 ping_interval (服务端自动发协议 ping, 无需应用代码), 客户端不需要感知 ping — **Reversibility:** reversible
- **D-13:** 客户端断连后指数退避重连: 1s → 2s → 4s → 8s → 16s → 30s 上限, 重连后发送 resume 消息恢复 seq, 连接状态 (connected/reconnecting/disconnected) 对用户可见 — 复用现有 useQuoteStream 的重连状态模式

### Claude's Discretion
- 环形缓冲区实现细节 (deque vs list, 淘汰策略) — 由 planner/researcher 决定
- WebSocket 端点路由注册位置 (main.py vs 新 ws 模块) — 由 planner 决定, 参考 bootstrap.py + security_middleware.py 拆分模式
- ndjson 流迁移后的频道设计细节 (是否需要 request 消息触发流式推送) — 由 researcher 调研

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 现有 SSE 端点 (迁移源)
- `backend/app/api/intraday.py:159-259` — 主行情 SSE 端点 `/api/intraday/stream`, sse-starlette EventSourceResponse, 多事件类型 (quotes/strategy_alert/portfolio/depth/review/analysis/advanced)
- `backend/app/api/mining.py:266-325` — mining SSE 端点, Last-Event-ID 恢复 + SQLite event ledger
- `backend/app/api/research_alpha_sse.py:124-141` — alpha SSE 端点, Last-Event-ID + seq 恢复
- `backend/app/api/walkforward_sse.py:20-188` — walkforward SSE 端点, StreamingResponse text/event-stream
- `backend/app/api/backtest.py:802-803,1091-1092,1316-1317` — 3 处 backtest SSE 端点 (strategy/optimize/walkforward)
- `backend/app/api/forecast/api.py:341-371` — forecast SSE 端点, Last-Event-ID 恢复
- `backend/app/api/financials.py:194-197` — ndjson 流 (AI 财务分析)
- `backend/app/api/market_recap.py:63-66` — ndjson 流 (市场复盘)
- `backend/app/api/rps.py:88-91` — ndjson 流 (RPS 轮动)
- `backend/app/api/stock_analysis.py:171-174` — ndjson 流 (股票分析)

### 现有前端 EventSource 消费者 (迁移源)
- `frontend/src/lib/useQuoteStream.ts:104-200` — 主行情 SSE hook, EventSource + 重连状态
- `frontend/src/lib/backtestTask.ts:40-320` — backtest 任务 SSE, EventSource + localStorage reconnect
- `frontend/src/lib/optimizerTask.ts:81-270` — optimizer 任务 SSE, EventSource + localStorage reconnect
- `frontend/src/lib/walkforwardTask.ts:73-250` — walkforward 任务 SSE, EventSource + localStorage reconnect
- `frontend/src/lib/miningTask.ts:42-186` — mining 任务 SSE, EventSource + bounded polling fallback
- `frontend/src/pages/backtest/AlphaWorkbench.tsx:100-190` — alpha 流 SSE, EventSource + seq 去重 + Last-Event-ID
- `frontend/src/pages/backtest/WalkForward.tsx:20-80` — walkforward plan 流 SSE

### WebSocket 客户端参考 (现有)
- `backend/app/services/stockdb_ws.py:42-170` — WebSocket 客户端连 stockdb-collector, 指数退避重连, ping_interval=20, resume + 重订阅
- `backend/app/services/wecom_bot_service.py:1-180` — WebSocket 长连接保活, 应用层 30s ping, 指数退避重连

### 后端基础设施参考
- `backend/app/services/quote_service.py:218-595` — QuoteService 单例 + QuoteSubscriber per-connection 订阅者 + 广播模式, SSE 连接管理参考
- `backend/app/bootstrap.py` — FastAPI 应用启动/lifespan, WebSocket 端点注册位置参考
- `backend/app/api/security_middleware.py` — 鉴权中间件, Cookie session 提取参考
- `backend/app/audit/tool_call_repo.py` — ToolCallEnvelope 审计 repository, scope=ws 连接审计接入参考

### 前端基础设施参考
- `frontend/src/lib/api.ts:4336-4338` — alphaRunStreamUrl, SSE URL 构造参考
- `frontend/src/lib/queryKeys.ts:262-266` — SSE_INVALIDATE_PREFIXES, SSE 事件触发的 query 失效模式参考

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **QuoteSubscriber / QuoteService**: per-connection 订阅者 + 广播模式可直接适配到 WS — 每个 WS 连接注册一个订阅者, 事件广播到所有订阅者。需要扩展为支持频道订阅/取消订阅。
- **useQuoteStream hook**: 已有重连状态管理 (connected/reconnecting/disconnected) + EventSource 生命周期管理, 可作为 WS 客户端 hook 的基础模板。
- **stockdb_ws.py 重连模式**: 指数退避重连 + resume + 全量重订阅的模式可直接参考。
- **mining/alpha SQLite event ledger**: 持久化事件日志 + Last-Event-ID 恢复的模式已验证, WS 版 seq 窗口是其轻量化等价物 (内存缓冲 vs SQLite 查询)。
- **backtestTask/optimizerTask/walkforwardTask**: 三处任务 SSE 模式高度相似 (job_key + cancel + localStorage reconnect), 可抽象为统一的 WS 任务流 hook。

### Established Patterns
- **sse-starlette EventSourceResponse**: 当前 SSE 标准, 迁移后移除依赖
- **StreamingResponse text/event-stream**: 部分端点用原生 StreamingResponse 而非 sse-starlette
- **StreamingResponse application/x-ndjson**: 4 处 ndjson 流用 POST 请求 + ReadableStream 消费
- **Last-Event-ID header**: mining/alpha/forecast 用此 header 恢复, WS 版用 resume 消息 + seq 替代
- **localStorage reconnect**: backtest/optimizer/walkforward 用 localStorage 存任务参数, 刷新后重连
- **ToolCallEnvelope 审计 seam**: v3.1 Phase 52 的 try/finally 审计模式, WS 连接生命周期审计接入

### Integration Points
- `backend/app/bootstrap.py`: WebSocket 端点注册 (或新建 ws 模块)
- `backend/app/api/security_middleware.py`: Cookie session 提取, WS 握手时复用
- `frontend/src/components/Layout.tsx:476-478`: useQuoteStream 调用点, 替换为 WS hook
- `frontend/src/lib/queryKeys.ts:262-266`: SSE_INVALIDATE_PREFIXES, WS 事件触发的 query 失效
- `backend/app/audit/tool_call_repo.py`: WS 连接审计接入点 (scope=ws)

</code_context>

<specifics>
## Specific Ideas

- 用户明确要求 "真正同时全量迁移, 全部一起改" — 不接受渐进/分批方案
- ndjson 流也迁移到 WebSocket — 用户明确选择包含这些, 不保留任何旧传输
- 心跳用协议层 ping (websockets 库), 不用应用层 ping/pong — 用户偏好零额外应用代码
- 前端全局单连接 — 用户明确选择所有流共享一个 WS 连接

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 55-WebSocket 全量迁移*
*Context gathered: 2026-08-20*
