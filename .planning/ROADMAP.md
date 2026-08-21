# Roadmap: AthenaQuant v3.2

## Phases

- [ ] **Phase 55: WebSocket 全量迁移** - 服务端 WS 端点 + 现有 SSE 流全量迁移 + 连接复用 + 心跳自动重连, 保留 Last-Event-ID 语义。
- [ ] **Phase 56: Server酱微信推送** - SCT API 接入 + 统一通知投递管道 + 推送审计 + 频率限制与去重。
- [ ] **Phase 57: 客户端实时规则引擎** - 浏览器端价格阈值规则 (localStorage) + WebSocket 实时行情评估 + 命中弹窗 + 与服务端规则共存。
- [ ] **Phase 58: 推送审计与运维** - WebSocket 连接审计 + 推送投递审计 + 首页推送质量面板, 复用 v3.1 ToolCallEnvelope 与 workbench API。

## Phase Details

### Phase 55: WebSocket 全量迁移

**Goal**: 从单向 SSE 轮询升级为 WebSocket 双向通信 — 服务端可主动推送, 浏览器实时接收, 保留断连重连不丢失事件语义。

**Depends on**: v3.1 (Phase 52 ToolCallEnvelope 提供审计基础); v3.1 SSE Last-Event-ID 模式提供重连语义参考。

**Requirements**: WS-01, WS-02, WS-03, WS-04

**Success Criteria** (what must be TRUE):

1. 服务端 WebSocket 端点 (`/ws/stream`) 支持多客户端并发连接, 按 session token 鉴权; 连接生命周期审计记录复用 ToolCallEnvelope (scope=ws)。
2. 现有 4 处 SSE 流 (walkforward / optimizer / mining / quoteStream) 全部迁移到 WebSocket 传输; 断连重连后通过 Last-Event-ID 语义恢复, 不丢失也不发明事件。
3. 多个实时流 (运行进度 + 行情 + 告警) 共享同一 WebSocket 连接, 通过消息 `type` 字段路由, 不为每类流新建连接。
4. WebSocket 连接有服务端 ping/keepalive 心跳; 客户端断连后指数退避自动重连; 连接状态 (connected/reconnecting/disconnected) 对用户可见。

**Research flag**: **Yes** — settle WebSocket 消息协议 (消息类型/载荷/序号/Last-Event-ID 等价物)、连接复用的多路复用方案、SSE 迁移的渐进/全量策略边界。

**Explicit non-goals**: 不新增消息队列或外部 broker, 不做跨进程广播 (单进程多连接即可), 不改变现有运行进度的业务语义。

**Plans**: 4/4 plans executed
**Wave 1**

- [x] 55-01-PLAN.md — WS 传输层核心 + quotes 行情流 tracer (后端 ws/ 模块 + /ws/stream 端点 + ConnectionManager + 前端 useWsStream + 连接状态 UI)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 55-02-PLAN.md — 后端 SSE/ndjson 全量迁移 (8 处 SSE + 5 处 ndjson 广播迁移到 WS 频道 + request_dispatcher)
- [x] 55-03-PLAN.md — 前端消费者全量迁移 (7 处 EventSource + 5 处 ndjson + 1 处 fetch SSE → useWsStream)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 55-04-PLAN.md — SSE 代码删除 + sse-starlette 依赖移除 + test_guard 更新 (D-03 无回退路径)

**UI hint**: yes

### Phase 56: Server酱微信推送

**Goal**: 新增 Server酱 (sct.ftqq.com) 通知渠道, 接入统一通知投递管道, 推送结果可审计, 有频率限制与去重。

**Depends on**: Phase 55 (WebSocket 推送通道可复用推送触发点); v3.1 Phase 52 (ToolCallEnvelope 提供推送审计)。

**Requirements**: SCT-01, SCT-02, SCT-03, SCT-04

**Success Criteria** (what must be TRUE):

1. 用户在设置页配置 Server酱 SendKey, 后端按 SendKey 通过 sct.ftqq.com API 推送; 配置存储复用现有 secrets.json (脱敏)。
2. Server酱接入统一通知投递管道 — 与现有 WeCom bot 共享通知触发点 (监控规则触发/报告生成), 用户可按规则选择渠道。
3. Server酱每次推送记录一条 ToolCallEnvelope (tool=sct, raw_hash + response_summary + duration), 审计页面可按渠道筛选。
4. 相同告警 5 分钟内不重复推送 (去重 key = rule_id + symbol + event_type); 支持每日推送上限, 超限后降级为批量摘要。

**Research flag**: **No dedicated research phase** — 复用现有通知投递模式 (wecom_bot_service) + v3.1 审计 seam。

**Explicit non-goals**: 不新增微信企业号以外的新渠道 (邮件/Slack 留到后续), 不做推送模板编辑器。

**Plans**: TBD

### Phase 57: 客户端实时规则引擎

**Goal**: 浏览器端价格阈值规则引擎, 通过 WebSocket 接收实时行情, 本地评估命中后立即弹窗提醒; 规则存 localStorage 不落盘后端。

**Depends on**: Phase 55 (WebSocket 实时行情流), Phase 56 (通知渠道可选复用推送)。

**Requirements**: CR-01, CR-02, CR-03

**Success Criteria** (what must be TRUE):

1. 用户在浏览器配置标的 + 价格阈值 (涨跌幅 % 或绝对价格), 规则存储在 localStorage, 不发送到后端; 页面刷新后规则恢复。
2. 客户端规则通过 WebSocket 接收实时行情 tick, 本地评估命中阈值后立即触发 Notification API 弹窗 + 页内 toast; 命中后可标记为已处理或继续监控。
3. 客户端规则与现有服务端监控规则共存 — 服务端规则走后端评估 + 通知渠道, 客户端规则走浏览器评估 + 弹窗, 两者独立不互扰; UI 上明确标注来源。

**Research flag**: **No dedicated research phase** — 复用现有 WebSocket 行情流 + 浏览器 Notification API。

**Explicit non-goals**: 不做客户端规则云同步, 不做规则市场/分享, 不改变服务端监控规则评估语义。

**Plans**: TBD
**UI hint**: yes

### Phase 58: 推送审计与运维

**Goal**: WebSocket 连接审计 + 推送投递审计 + 首页推送质量面板, 复用 v3.1 ToolCallEnvelope 与 workbench API, 形成推送闭环可视化。

**Depends on**: Phase 55 (WebSocket 连接审计), Phase 56 (推送投递审计), v3.1 Phase 53 (workbench API + 前端组件)。

**Requirements**: PA-01, PA-02, PA-03

**Success Criteria** (what must be TRUE):

1. WebSocket 连接/断连/重连事件记录一条 ToolCallEnvelope (scope=ws, tool=connection), 审计页面可按连接状态筛选。
2. Server酱/WeCom 每次推送投递记录 ToolCallEnvelope (tool=sct/wecom, raw_hash + response_summary + duration), 审计页面可按渠道/日期/失败原因筛选。
3. 首页工作台新增推送投递统计 (今日成功/失败/去重跳过), 复用 v3.1 workbench API 扩展 pending 子项; 推送失败时首页显示告警。

**Research flag**: **No dedicated research phase** — 全部复用 v3.1 审计 + 工作台模式。

**Explicit non-goals**: 不新增推送重试策略配置, 不做推送 A/B 测试。

**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 55. WebSocket 全量迁移 | 4/4 | In Progress|  |
| 56. Server酱微信推送 | 0/TBD | Not started | - |
| 57. 客户端实时规则引擎 | 0/TBD | Not started | - |
| 58. 推送审计与运维 | 0/TBD | Not started | - |

**Execution order:** 55 → 56 → 57 → 58. Phase 55 (WebSocket 传输层) 是其余三者的基础设施; 56/57 可在 55 完成后并行, 58 收口审计与运维。

## Requirement Coverage

14/14 v3.2 requirements mapped, no orphans, no duplicates: WS-01..04 → Phase 55; SCT-01..04 → Phase 56; CR-01..03 → Phase 57; PA-01..03 → Phase 58. Per-requirement traceability lives in `.planning/REQUIREMENTS.md`.

## Milestone History

| Milestone | Name | Status | Shipped |
|-----------|------|--------|---------|
| v3.2 | 实时推送平台 | In Progress | - |
| v3.1 | 可信工作台与运维闭环 | Complete | 2026-08-20 |
| v3.0 | AlphaFactory 量化因子挖掘 | Complete | 2026-08-09 |

---
*Last updated: 2026-08-20 — v3.2 milestone started (实时推送平台), 14 requirements defined across 4 phases.*
