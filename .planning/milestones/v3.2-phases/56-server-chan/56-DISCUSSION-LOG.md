# Phase 56: Server酱微信推送 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-22
**Phase:** 56-Server酱微信推送
**Areas discussed:** SendKey 配置存储, Server酱 API 推送, 统一投递管道接入, 审计记录, 去重与频率限制, 前端设置页

---

## SendKey 配置存储

| Option | Description | Selected |
|--------|-------------|----------|
| preferences.py JSON | 复用 feishu/telegram 对称模式, 新增 get/set_sct_sendkey | ✓ |
| secrets.json 独立文件 | 独立凭证文件, 与 preferences 隔离 | |

**Auto-selected:** preferences.py JSON (recommended default — 与现有 feishu/telegram/wecom 完全对称)

---

## Server酱 API 推送

| Option | Description | Selected |
|--------|-------------|----------|
| SctChannel in delivery.py | 与 FeishuChannel/TelegramChannel 同文件, 实现 NotificationChannel Protocol | ✓ |
| webhook_adapter.py | 放在通用 webhook 适配器文件 | |

**Auto-selected:** SctChannel in delivery.py (recommended default — 与现有 channel 类同构)

---

## 统一投递管道接入

| Option | Description | Selected |
|--------|-------------|----------|
| 白名单 + _channel_for 分支 | RULE_DELIVERY_CHANNELS + REVIEW_PUSH_CHANNELS 加 sct, _channel_for 新增分支 | ✓ |
| 独立推送路径 | 不走 NotificationDeliveryService, 独立推送逻辑 | |

**Auto-selected:** 白名单 + _channel_for 分支 (recommended default — 统一管道是既定架构)

---

## 审计记录

| Option | Description | Selected |
|--------|-------------|----------|
| ToolCallEnvelope.append | tool=sct, category=notification, 复用 v3.1 审计 seam | ✓ |
| 独立审计表 | 新建 sct_audit 表 | |

**Auto-selected:** ToolCallEnvelope.append (recommended default — 复用 v3.1 审计架构)

---

## 去重与频率限制

| Option | Description | Selected |
|--------|-------------|----------|
| 内存 TTL + 每日上限 | 5 分钟 TTL 字典去重, 200 条/日上限超限降级摘要 | ✓ |
| SQLite 持久化 | 去重状态持久化到 SQLite | |

**Auto-selected:** 内存 TTL + 每日上限 (recommended default — 轻量, 重启重置可接受)

---

## 前端设置页

| Option | Description | Selected |
|--------|-------------|----------|
| Settings.tsx 新增 SCT 区 | 与飞书/Telegram 并列, SendKey 输入 + 测试推送 | ✓ |
| 独立设置页 | 新建 SctSettings.tsx | |

**Auto-selected:** Settings.tsx 新增 SCT 区 (recommended default — 与现有渠道对称)

---

## Claude's Discretion

- SCT API 超时时间 (2s, 与其他 channel 一致)
- 去重 TTL 字典具体实现 (cachetools 或手写)
- 每日摘要推送的时间窗口判定
- 降级批量摘要消息格式

## Deferred Ideas

None — discussion stayed within phase scope
