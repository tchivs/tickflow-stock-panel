# Phase 57: 客户端实时规则引擎 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.

**Date:** 2026-08-22
**Phase:** 57-客户端实时规则引擎
**Areas discussed:** 规则存储, 规则评估, 命中后处理, UI 布局, Notification 权限, 与服务端规则共存

---

## 规则存储

| Option | Description | Selected |
|--------|-------------|----------|
| storage.ts makeStorage | 复用 screenerResultColumns 对称模式, key=client_rules | ✓ |
| 独立 IndexedDB | 更大数据量, 异步 API | |

**Auto-selected:** storage.ts makeStorage (recommended — 轻量, 与现有模式一致)

---

## 规则评估

| Option | Description | Selected |
|--------|-------------|----------|
| WS quotes 频道订阅 | subscribe('quotes') → 本地评估 | ✓ |
| 轮询行情 API | 定时 fetch | |

**Auto-selected:** WS quotes 频道订阅 (recommended — 实时, 复用 Phase 55 WS 基础设施)

---

## 命中后处理

| Option | Description | Selected |
|--------|-------------|----------|
| 标记已处理 + 5分钟防抖 | 保持 enabled, 清除 triggered, 防抖 | ✓ |
| 命中后自动关闭 | enabled=false | |

**Auto-selected:** 标记已处理 + 5分钟防抖 (recommended — 用户可继续监控)

---

## UI 布局

| Option | Description | Selected |
|--------|-------------|----------|
| 监控中心新增 tab | 与服务端规则并列, 视觉分隔 | ✓ |
| 独立页面 | 新路由 /client-rules | |

**Auto-selected:** 监控中心新增 tab (recommended — 与服务端规则同处但独立)

---

## Notification 权限

| Option | Description | Selected |
|--------|-------------|----------|
| 首次创建规则时请求 | 拒绝降级为 toast + 声效 | ✓ |
| 页面加载时请求 | 侵入性强 | |

**Auto-selected:** 首次创建规则时请求 (recommended — 非侵入式)

---

## 与服务端规则共存

| Option | Description | Selected |
|--------|-------------|----------|
| 完全独立 | 数据/评估/通知全部分离, UI badge 区分 | ✓ |
| 共享通知通道 | 客户端规则也走后端推送 | |

**Auto-selected:** 完全独立 (recommended — D-06 明确要求两者不互扰)

---

## Claude's Discretion

- 防抖时间窗口 (5 分钟)
- toast 显示时长
- Notification 通知标题/正文格式
- 规则列表排序方式

## Deferred Ideas

None — discussion stayed within phase scope
