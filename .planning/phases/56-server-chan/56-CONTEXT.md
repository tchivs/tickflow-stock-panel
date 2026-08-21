# Phase 56: Server酱微信推送 - Context

**Gathered:** 2026-08-22
**Status:** Ready for planning

<domain>
## Phase Boundary

新增 Server酱 (sct.ftqq.com) 作为通知投递渠道, 接入现有 `NotificationDeliveryService` 统一投递管道。用户可在设置页配置 SCT SendKey, 监控规则触发/报告生成时按渠道选择推送。推送结果通过 `ToolCallEnvelope` 审计, 支持 5 分钟去重和每日推送上限。

**In scope:**
- SCT SendKey 配置 (preferences 存储 + settings API + 前端设置页)
- Server酱 HTTP 推送适配器 (sct.ftqq.com API)
- 接入 NotificationDeliveryService 统一投递管道
- ToolCallEnvelope 审计 (tool=sct)
- 5 分钟去重 (rule_id + symbol + event_type)
- 每日推送上限 + 超限降级批量摘要

**Out of scope:**
- 邮件/Slack 等其他新渠道
- 推送模板编辑器
- WebSocket 推送 (Phase 55 已完成)

</domain>

<decisions>
## Implementation Decisions

### SendKey 配置与存储
- **D-01:** SCT SendKey 存储复用 `preferences.py` 的 JSON load/save 模式 — 新增 `get_sct_sendkey()` / `set_sct_sendkey()`, 与 `get_feishu_webhook_url()` / `get_telegram_bot_token()` 完全对称。SendKey 为敏感凭证, API 返回时需脱敏 (仅显示前 4 后 4 字符, 中间用 `****` 替代)。 — **Reversibility:** reversible — 仅新增 preference key, 删除即回退

### Server酱 API 推送
- **D-02:** 新增 `SctChannel` 类实现 `NotificationChannel` Protocol, 与 `FeishuChannel` / `TelegramChannel` 完全对称。推送接口 `https://sctapi.ftqq.com/{sendkey}.send`, POST form-data `title` + `desp` (Markdown), 返回 JSON `{"code": 0}` 判定成功。适配器放在 `backend/app/notifications/delivery.py` 内, 与 FeishuChannel/TelegramChannel 同文件。 — **Reversibility:** reversible — 删除 channel 类 + 注册即可

### 统一投递管道接入
- **D-03:** `NotificationDeliveryService._channel_for()` 新增 `sct` 分支, 返回 `SctChannel` 实例。`RULE_DELIVERY_CHANNELS` 白名单新增 `"sct"`。`REVIEW_PUSH_CHANNELS` 白名单新增 `"sct"`。用户在监控规则编辑器/复盘推送设置中可按渠道选择 `feishu` / `telegram` / `sct`。 — **Reversibility:** costly — 修改白名单需同步 monitor_rules.normalize 逻辑, 但改动面可控

### 审计记录
- **D-04:** 每次推送成功/失败后, 在 `SctChannel.deliver()` 内调用 `ToolCallAuditRepository.append(tool="sct", category="notification", scope=f"notification:{event_id}", response_summary=..., raw_hash=..., duration_ms=...)`。审计页面 `api/audit.py` 的渠道筛选已支持按 `tool` 字段筛选, 无需额外修改。 — **Reversibility:** reversible — 删除 append 调用即可

### 去重与频率限制
- **D-05:** 去重 key = `{rule_id}:{symbol}:{event_type}`, 去重窗口 5 分钟。实现方式: 在 `NotificationDeliveryService.enqueue()` 前增加去重检查, 使用内存 TTL 字典 (与 quiet_period 共存)。每日推送上限默认 200 条, 超限后降级为每日摘要 (攒满后一次性推送)。 — **Reversibility:** reversible — 去重状态为内存, 重启即重置

### 前端设置页
- **D-06:** 前端设置页新增 "Server酱" 配置区, 与飞书/Telegram 并列。输入 SendKey + 测试推送按钮。测试推送调用后端 `POST /api/settings/sct-test` 端点, 后端发送一条测试消息并返回成功/失败。 — **Reversibility:** reversible — UI 组件可删除

### Claude's Discretion
- SCT API 超时时间: 2s (与 FeishuChannel/TelegramChannel 一致)
- 去重 TTL 字典的具体实现 (可用 `cachetools.TTLCache` 或手写 `dict + time`)
- 每日摘要推送的时间窗口判定 (按 UTC 日期 vs 交易日)
- 降级批量摘要的消息格式

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 通知投递管道
- `backend/app/notifications/delivery.py` — NotificationDeliveryService + FeishuChannel + TelegramChannel + DeliveryConfig + NotificationChannel Protocol — SCT 适配器需实现同一 Protocol
- `backend/app/notifications/__init__.py` — 导出接口

### 配置存储模式
- `backend/app/services/preferences.py` §`get_feishu_webhook_url` / `get_telegram_bot_token` / `get_wecom_webhook_url` — SendKey 存储的对称模式
- `backend/app/services/preferences.py` §`RULE_DELIVERY_CHANNELS` / `REVIEW_PUSH_CHANNELS` — 渠道白名单

### HTTP 推送适配器
- `backend/app/services/webhook_adapter.py` §`send_wecom` / `send_wecom_markdown` — HTTP POST 推送模式参考
- `backend/app/notifications/delivery.py` §`FeishuChannel.deliver()` — channel.deliver() 实现模板

### 审计
- `backend/app/audit/envelope.py` §`ToolCallAuditRepository.append()` — 审计记录接口
- `backend/app/audit/service.py` — `get_audit_repo()` / `set_audit_repo()` 全局 audit repo 访问
- `backend/app/api/audit.py` — 审计查询 API (已有 tool 筛选)

### 设置 API
- `backend/app/api/settings.py` §`update_wecom_webhook` / `update_wecom_bot` — 设置端点实现模板
- `backend/app/strategy/monitor_rules.py` §`DELIVERY_CHANNELS` / `normalize()` — 监控规则渠道规范化

### 前端设置页
- `frontend/src/pages/Settings.tsx` — 设置页组件 (飞书/Telegram 配置区)

### 贡献规范
- `CONTRIBUTING.md` — 项目架构、数据契约、测试矩阵、PR 标准
- `docs/secondary-development.md` — 可替换策略与扩展注册

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `NotificationDeliveryService` (notifications/delivery.py): 统一投递管道, 已有 FeishuChannel + TelegramChannel, SctChannel 以同构方式接入
- `DeliveryConfig` (dataclass): 已有 channel + config 字段, SCT 只需新增 channel name
- `ToolCallAuditRepository.append()`: 已有 tool/category/scope/response_summary/raw_hash/duration_ms 字段, SCT 审计直接调用
- `preferences.py` load/save: JSON 配置存储, 新增 SCT SendKey 只需加 key
- `webhook_adapter.py`: HTTP POST + 错误处理模式, 可参考但 SCT 适配器直接放 delivery.py

### Established Patterns
- **Channel Protocol:** `deliver(event) -> {"status": "sent"|"failed"}` — SCT 必须实现此接口
- **Safe error handling:** `_safe_error()` 脱敏错误信息, 不泄露凭证/端点
- **Whitelist pattern:** `RULE_DELIVERY_CHANNELS` / `REVIEW_PUSH_CHANNELS` 白名单控制可用渠道
- **Monitor rules normalize:** `monitor_rules.normalize()` 剥离白名单外渠道, SCT 需加入白名单否则被剥离

### Integration Points
- `NotificationDeliveryService._channel_for()`: 新增 `sct` 分支
- `preferences.RULE_DELIVERY_CHANNELS`: 新增 `"sct"`
- `preferences.REVIEW_PUSH_CHANNELS`: 新增 `"sct"`
- `monitor_rules.normalize()`: 不再剥离 `sct` (当前仅剥离 `wecom`)
- `api/settings.py`: 新增 `PUT /preferences/sct-sendkey` + `POST /sct-test`
- `frontend/src/pages/Settings.tsx`: 新增 SCT 配置区

</code_context>

<specifics>
## Specific Ideas

- Server酱 API: `https://sctapi.ftqq.com/{sendkey}.send` — POST `title` (string) + `desp` (Markdown body), 响应 JSON `{"code": 0, "message": "..."}`, `code != 0` 为失败
- 去重 TTL: 5 分钟窗口, key = `rule_id:symbol:event_type`, 超时自动过期
- 每日上限降级: 超过 200 条/天后, 不再逐条推送, 改为攒满后一次性推送摘要

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 56-Server酱微信推送*
*Context gathered: 2026-08-22*
