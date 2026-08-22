# Phase 55: WebSocket 全量迁移 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-20
**Phase:** 55-WebSocket 全量迁移
**Areas discussed:** SSE 迁移策略, WebSocket 消息协议, 连接复用与多路复用, WebSocket 鉴权方式

---

## SSE 迁移策略

| Option | Description | Selected |
|--------|-------------|----------|
| 渐进: 主行情流优先 | 先迁移主行情流 + AlphaWorkbench, 验证稳定后再迁移剩余 6 处。保留旧 SSE 直到全量完成。 | |
| 大爆炸: 全量迁移 | 一次性将 8 处后端 SSE + 7 处前端 EventSource 全部迁移到 WebSocket, 删除所有 SSE 代码。 | ✓ |
| 并行: 新建 WS, 旧 SSE 保留 | 新建 WS 与 SSE 并行, 新功能用 WS, 旧功能逐步迁移。 | |

**User's choice:** 大爆炸: 全量迁移
**Notes:** 用户进一步确认 "真正同时全部一起改, 不分先后"

### 迁移回退策略

| Option | Description | Selected |
|--------|-------------|----------|
| 无回退: 删除旧代码 | 迁移后删除所有 SSE 代码, 不保留回退路径。出问题需 git revert。 | ✓ |
| 降级: WS 失败时回退 SSE | SSE 端点保留 deprecated, WS 失败时降级到 SSE。 | |

**User's choice:** 无回退: 删除旧代码

### 测试策略

| Option | Description | Selected |
|--------|-------------|----------|
| 先写测试再迁移 (TDD) | 先写 WS 版本测试 (连接/断连/重连/多路复用), 再迁移代码, 再跑 e2e。 | ✓ |
| 先迁移再测试 | 先迁移代码, 再写 WS 测试, 最后跑 e2e。 | |

**User's choice:** 先写测试再迁移 (TDD)

### ndjson 流处理

| Option | Description | Selected |
|--------|-------------|----------|
| 保留 ndjson 不迁移 | financial_analysis/market_recap/rps_rotation/stock_analysis 用 application/x-ndjson, 是 POST 请求流式响应, 保留不迁移。 | |
| ndjson 也迁移 | ndjson 流也迁移到 WebSocket, 统一为单一传输层。 | ✓ |

**User's choice:** ndjson 也迁移

---

## WebSocket 消息协议

### 消息格式

| Option | Description | Selected |
|--------|-------------|----------|
| JSON {type, seq, data} | 每条 WS 消息是 JSON, 顶层 type 字段路由 + seq 字段单调递增 + data 字段载荷。 | ✓ |
| SSE 兼容格式 | event 字段 + data 字段 + id 字段, 跟 SSE 一致但通过 WS 发送。 | |
| 二进制格式 | MessagePack 或 Protobuf。更高效但调试复杂, 需额外解析库。 | |

**User's choice:** JSON {type, seq, data}

### 断连恢复

| Option | Description | Selected |
|--------|-------------|----------|
| seq 窗口: 服务端缓冲 + resume | 客户端重连时发 {type: 'resume', last_seq: N}, 服务端从 N+1 重放, 内存环形缓冲区。 | ✓ |
| 持久化日志查询 | 服务端维护持久化事件日志, 客户端重连时按 run_id + cursor 查询。 | |
| 不恢复: 只推新事件 | 不保留断连期间事件, 重连后只推新事件。 | |

**User's choice:** seq 窗口: 服务端缓冲 + resume

### 订阅机制

| Option | Description | Selected |
|--------|-------------|----------|
| 客户端订阅频道 | 连接后发 {type: 'subscribe', channels: [...]}, 服务端只推已订阅频道事件。 | ✓ |
| 自动接收所有事件 | 连接后自动接收所有事件, 不需要订阅。 | |

**User's choice:** 客户端订阅频道

### 缓冲区大小

| Option | Description | Selected |
|--------|-------------|----------|
| 500 条 | 覆盖约 30 秒行情流。内存占用小, 断连超 30s 可能丢事件。 | |
| 1000 条 | 覆盖约 1 分钟行情流 + 告警/进度。平衡内存与恢复窗口。 | ✓ |
| 5000 条 | 覆盖约 5 分钟。恢复能力强, 但内存占用大 (每连接 ~1MB)。 | |

**User's choice:** 1000 条

---

## 连接复用与多路复用

### 连接数

| Option | Description | Selected |
|--------|-------------|----------|
| 全局单连接 | 整个前端只开一个 WS (/ws/stream), 所有流共享, subscribe/unsubscribe 频道切换。 | ✓ |
| 按域分 2 个连接 | 行情/告警共享一个 WS, 任务进度共享另一个 WS。 | |
| 每模块各自连接 | 每个功能模块各自开 WS (跟现在 EventSource 一样)。 | |

**User's choice:** 全局单连接

### 频道设计

| Option | Description | Selected |
|--------|-------------|----------|
| 功能域频道 | quotes/alerts/portfolio/run:{run_id}/analysis:{symbol}/review/depth。 | ✓ |
| 事件类型频道 | quotes_updated/strategy_alert/job_progress 等。更细粒度但管理复杂。 | |

**User's choice:** 功能域频道

---

## WebSocket 鉴权方式

### 鉴权方式

| Option | Description | Selected |
|--------|-------------|----------|
| Query param (?token=) | URL 携带 token。最简单, 但 token 可能出现在日志/Referer。 | |
| 子协议 (Sec-WebSocket-Protocol) | 用子协议传递 token。不出现在 URL, 但语义滥用。 | |
| Cookie session (复用现有) | 复用现有 SSE Cookie session, 浏览器自动携带 Cookie, 零额外代码。 | ✓ |
| 应用层 auth 消息 | 连接后发 {type: 'auth', token} 验证。未验证前连接已建立。 | |

**User's choice:** Cookie session (复用现有)

### 心跳机制

| Option | Description | Selected |
|--------|-------------|----------|
| 应用层 ping/pong | 服务端每 20s 发 {type: 'ping'}, 客户端回 {type: 'pong'}。应用层心跳。 | |
| 协议层 ping (websockets 库) | websockets 库 ping_interval=20, 服务端自动发协议 ping, 无需应用代码。 | ✓ |
| 双重心跳 | 协议层 ping 保活 + 应用层 ping/pong 检测逻辑连接。最稳但最复杂。 | |

**User's choice:** 协议层 ping (websockets 库)

### 重连策略

| Option | Description | Selected |
|--------|-------------|----------|
| 指数退避 + resume | 1s → 2s → 4s → 8s → 16s → 30s 上限, 重连后发 resume 恢复 seq, 状态对用户可见。 | ✓ |
| 固定间隔重连 | 每 3s 一次。简单但不灵活。 | |

**User's choice:** 指数退避 + resume

---

## Claude's Discretion

- 环形缓冲区实现细节 (deque vs list, 淘汰策略) — 由 planner/researcher 决定
- WebSocket 端点路由注册位置 (main.py vs 新 ws 模块) — 由 planner 决定
- ndjson 流迁移后的频道设计细节 — 由 researcher 调研

## Deferred Ideas

None — discussion stayed within phase scope
