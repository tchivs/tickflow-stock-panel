# Phase 58: 推送审计与运维 - Context

**Gathered:** 2026-08-22
**Status:** Ready for planning

<domain>
## Phase Boundary

推送闭环可视化 — WebSocket 连接审计 + 推送投递审计 + 首页推送质量面板, 复用 v3.1 ToolCallEnvelope 与 workbench API。

**In scope:**
- PA-01: WebSocket 连接/断连/重连事件审计 (tool=connection, scope=ws) — Phase 55 已实现连接审计, 本 phase 需验证 + 审计页筛选
- PA-02: 推送投递审计 — SCT 已实现 (Phase 56, tool=sct), WeCom 需补审计 (tool=wecom)
- PA-03: 首页工作台推送投递统计 (今日成功/失败/去重跳过) + 推送失败告警

**Out of scope:**
- 推送重试策略配置
- 推送 A/B 测试

</domain>

<decisions>
## Implementation Decisions

### PA-01: WebSocket 连接审计
- **D-01:** Phase 55 已在 `ws/handler.py` 实现 `AuditContext(tool="connection", category="external", scope="ws")` — 连接建立/关闭/断连均记录 ToolCallEnvelope。本 phase 无需新增代码, 仅验证审计页可按 `tool=connection` 筛选 + 在审计页 UI 标注 "WebSocket 连接" 标签。 — **Reversibility:** reversible — 标签可删除

### PA-02: WeCom 推送投递审计
- **D-02:** WeCom 推送目前无审计记录。在 `webhook_adapter.py` 的 `send_wecom` / `send_wecom_markdown` 中添加审计调用: `get_audit_repo().append(tool="wecom", category="notification", scope=f"review:{title}", response_summary=..., raw=..., duration_ms=...)`。与 SctChannel 模式一致: 成功/失败均记录, `get_audit_repo()` 返回 None 时跳过。 — **Reversibility:** reversible

### PA-03: 推送质量面板
- **D-03:** 在 `workbench.py` 的 `GET /api/workbench` 端点新增 `push_stats` 子项 — 查询 `tool_call_envelopes` 中今日 `tool IN ('sct', 'wecom', 'connection')` 的统计: total / sent (error IS NULL) / failed (error IS NOT NULL) / dedup_skipped (error='dedup') / daily_limit (error='daily_limit_exceeded')。fail-soft: 审计 repo 不可用时返回空统计。 — **Reversibility:** reversible — 删除子项即回退

- **D-04:** 前端首页工作台新增 "推送质量" 面板: 今日成功/失败/去重跳过数字卡片 + 失败列表 (最近 10 条 failed 记录)。推送失败 >= 1 时显示告警 badge。复用现有 workbench API + 前端组件模式。 — **Reversibility:** reversible

### 审计页筛选
- **D-05:** 后端审计 API `GET /api/tool-calls` 已支持 `tool` 查询参数筛选。前端审计页新增渠道筛选下拉 (feishu/telegram/sct/wecom/connection), 调用 `GET /api/tool-calls?tool=xxx` 即可。 — **Reversibility:** reversible

### Claude's Discretion
- 推送质量面板的具体布局 (数字卡片 vs 表格)
- 失败告警的具体样式 (banner vs badge vs toast)
- WeCom 审计的 scope 命名 (review:xxx vs notification:xxx)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 审计系统
- `backend/app/audit/envelope.py` §`ToolCallAuditRepository.append()` — 审计记录接口
- `backend/app/audit/service.py` — `get_audit_repo()` / `set_audit_repo()`
- `backend/app/api/audit.py` §`list_tool_calls()` — `GET /tool-calls?tool=xxx` 已支持 tool 筛选
- `backend/app/api/audit.py` §`tool_calls_summary()` — 按 category/tool 统计

### WebSocket 连接审计 (已实现)
- `backend/app/ws/handler.py` §`AuditContext(tool="connection", scope="ws")` — Phase 55 已实现连接审计

### 推送审计
- `backend/app/notifications/delivery.py` §`SctChannel.deliver()` — tool=sct 审计已实现 (Phase 56)
- `backend/app/services/webhook_adapter.py` §`send_wecom` / `send_wecom_markdown` — WeCom 推送 (需补审计)

### Workbench API
- `backend/app/api/workbench.py` §`workbench()` — `GET /api/workbench` 聚合端点, 需新增 `push_stats` 子项
- `backend/app/api/workbench.py` §`_pending_section()` — 子项实现模式参考

### 前端
- `frontend/src/pages/` — 首页工作台组件
- `frontend/src/lib/api.ts` — API 调用

### 项目规范
- `CONTRIBUTING.md` — 项目架构、数据契约、测试矩阵
- `docs/secondary-development.md` — 可替换策略与扩展注册

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ToolCallAuditRepository.append()`: 已有审计接口, WeCom 审计直接调用
- `GET /api/tool-calls?tool=xxx`: 已支持按 tool 筛选, 无需后端改动
- `GET /api/workbench`: 已有聚合端点, 新增 `push_stats` 子项
- `AuditContext` (envelope.py): Phase 55 已用此模式记录 WS 连接审计

### Established Patterns
- **Audit append pattern:** `get_audit_repo().append(tool=..., category="notification", scope=..., response_summary=..., raw=..., duration_ms=..., error=...)`
- **Workbench fail-soft:** `_safe(fn, *args)` 包装, 子项独立 fail-soft
- **Workbench sub-section:** 返回 `{items: [...], counts: {...}}` 结构

### Integration Points
- `webhook_adapter.py` `send_wecom` / `send_wecom_markdown` — 新增审计调用
- `workbench.py` `workbench()` — 新增 `push_stats` 子项
- `workbench.py` `_push_stats_section()` — 新增函数
- 前端首页 — 新增推送质量面板
- 前端审计页 — 新增渠道筛选

</code_context>

<specifics>
## Specific Ideas

- push_stats SQL: `SELECT tool, COUNT(*) as total, SUM(CASE WHEN error IS NULL THEN 1 ELSE 0 END) as sent, SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as failed FROM tool_call_envelopes WHERE tool IN ('sct','wecom','connection') AND date(created_at) = date('now') GROUP BY tool`
- 去重跳过计数: `SUM(CASE WHEN error = 'dedup' THEN 1 ELSE 0 END) as dedup_skipped` — 但 audit 记录的是推送成功/失败, 去重跳过在 `notification_deliveries` 表不在 `tool_call_envelopes` 表; 需从 `notification_deliveries` 补充查询
- 推送失败告警: workbench 返回 `push_stats.failed > 0` 时前端显示告警

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 58-推送审计与运维*
*Context gathered: 2026-08-22*
