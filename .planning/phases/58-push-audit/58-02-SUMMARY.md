---
phase: 58-push-audit
plan: 02
subsystem: frontend
tags: [push-quality, audit-filter, dashboard-alert, workbench]
requires:
  - Phase 58-01 backend push_stats in GET /api/workbench
  - Phase 52 ToolCallEnvelope audit API with tool param support
provides:
  - PushQualityPanel component (today sent/failed/dedup cards + recent failures)
  - Audit page channel filter dropdown (feishu/telegram/sct/wecom/connection)
  - Dashboard push failure alert banner
affects:
  - frontend/src/components/workbench/WorkbenchPanel.tsx
  - frontend/src/pages/Dashboard.tsx
  - frontend/src/pages/Audit.tsx
  - frontend/src/lib/api.ts
tech-stack:
  added: []
  patterns:
    - CollapsibleSection badge prop for failure alert in collapsed state
    - TOOL_OPTIONS filter pattern mirroring CATEGORY_OPTIONS
    - Tool badge coloring (WS=blue, sct=purple, wecom=green, feishu=orange, telegram=cyan)
key-files:
  created:
    - frontend/src/components/workbench/PushQualityPanel.tsx
  modified:
    - frontend/src/components/workbench/WorkbenchPanel.tsx
    - frontend/src/lib/api.ts
    - frontend/src/pages/Audit.tsx
    - frontend/src/pages/Dashboard.tsx
decisions:
  - D-04: PushQualityPanel as 4th CollapsibleSection in WorkbenchPanel, badge replaces count when failures exist
  - D-05: TOOL_OPTIONS dropdown reuses existing selectCls + resetAndApply pattern from category filter
  - Tool badges colored by tool type, shown next to tool name in audit table rows
metrics:
  duration: 420s
  completed: 2026-08-22
actuals:
  tokens: 4063
  tasks: 3
  commits: 3
status: complete
---

# Phase 58 Plan 02: Frontend Push Quality Panel + Audit Filter + Failure Alert Summary

前端推送闭环可视化: 推送质量面板 + 审计页渠道筛选 + 首页推送失败告警 banner。

## What Was Built

### Task 1: PushQualityPanel 组件 + WorkbenchPanel 装配 (PA-03, D-04)

在 `api.ts` 的 `WorkbenchResponse` 接口新增 `push_stats` 类型:
- `today: { total, sent, failed, dedup_skipped }`
- `by_tool: Record<string, { total, sent, failed }>`
- `recent_failures: Array<{ tool, error, created_at }>`

创建 `PushQualityPanel.tsx` 组件:
- 三列数字卡片: 成功 (绿色 text-bull) / 失败 (红色 text-bear) / 去重跳过 (橙色 text-warning)
- 最近失败列表: 最多 10 条, 每条显示 tool 标签 (带渠道色) + error 文本 (truncate) + 时间
- 空状态: `total=0` 时显示 "今日暂无推送"
- 工具标签颜色: WS=blue, Server酱=purple, 企微=green, 飞书=orange, Telegram=cyan

在 `WorkbenchPanel.tsx` 装配 PushQualityPanel:
- `CollapsibleSection` 新增 `badge?: React.ReactNode` 可选 prop
- 推送质量区作为第 4 个折叠区, 放在 "监控触发" 之后
- 失败 >= 1 时标题旁显示红色 badge (AlertTriangle + 失败数), 折叠状态也可见
- `defaultOpen` 当 `push_stats.today.failed > 0` 时默认展开
- 复用 WorkbenchPanel 已有 useQuery data, 不新增独立请求

### Task 2: 审计页渠道筛选 + 工具标签 (PA-01/PA-02, D-01/D-05)

在 `Audit.tsx` 的 `ToolCallsTab` 新增渠道筛选:
- `TOOL_OPTIONS` 常量: 全部渠道 / WebSocket连接 / Server酱 / 企业微信 / 飞书 / Telegram
- 新增 `tool` state + `resetAndApply` 集成, 复用 `selectCls` 样式
- `params` useMemo 新增 `if (tool) p.tool = tool`
- 渠道下拉放在 "分类" 下拉之后
- "清除筛选" 按钮包含 `setTool('')` + `tool` 条件判断

在 `ToolCallRow` 新增工具标签 badge:
- `TOOL_BADGE_CLS` / `TOOL_BADGE_LABEL` 常量映射工具名到颜色和短标签
- tool 列显示工具名 + 彩色 badge (WS / Server酱 / 企微 / 飞书 / TG)
- 标签附着在 tool 列内容旁, 不占额外列

### Task 3: 首页推送失败告警 banner (PA-03, D-04)

在 `Dashboard.tsx` 新增推送失败告警:
- 新增 workbench useQuery (staleTime 30s, refetchInterval 60s)
- 从 `workbench.data?.push_stats` 读取推送统计
- 失败 >= 1 时在 `DataQualityBanner` 之后显示红色告警 banner
- 告警内容: 失败条数 + 最近失败原因 + 审计页链接 (`/audit`)
- 样式参考 Free 档提示 banner (amber-500/30), 用 red-500 主题
- Fail-soft: `push_stats` 为 null 时不渲染告警

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| Task 1 build | `cd frontend && pnpm build` | ✓ built in 9.28s, no TS errors |
| Task 2 build | `cd frontend && pnpm build` | ✓ built in 9.20s, no TS errors |
| Task 3 build | `cd frontend && pnpm build` | ✓ built in 8.69s, no TS errors |

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | f4aef505 | feat(58-02): add PushQualityPanel component + WorkbenchPanel assembly (PA-03, D-04) |
| 2 | 13d3e22a | feat(58-02): add audit page channel filter + tool badges (PA-01/PA-02, D-01/D-05) |
| 3 | f7d4aeaf | feat(58-02): add push failure alert banner on Dashboard (PA-03, D-04) |

## Deviations from Plan

None — plan executed exactly as written.

### Threat Model Compliance

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-58-04 | accept | **OK** — audit error field rendered via existing _safe_error sanitized text, frontend only displays |
| T-58-05 | accept | **OK** — push_stats counts are read-only from append-only audit table, no tampering surface |
| T-58-SC | accept | **OK** — no new packages installed |

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|---------|
| PA-01 | Delivered | Audit page tool=connection rows show "WS" badge; channel filter dropdown includes "WebSocket 连接" option |
| PA-02 | Delivered | Audit page channel filter dropdown (feishu/telegram/sct/wecom/connection) calls GET /api/tool-calls?tool=xxx |
| PA-03 | Delivered | PushQualityPanel renders today sent/failed/dedup cards + recent failures; Dashboard shows red alert banner when failed >= 1 |

## Known Stubs

None — all code is production-quality with real data from workbench API.

## Self-Check: PASSED

- [x] `frontend/src/components/workbench/PushQualityPanel.tsx` — FOUND (created, 78 lines)
- [x] `frontend/src/components/workbench/WorkbenchPanel.tsx` — FOUND (modified, PushQualityPanel assembled)
- [x] `frontend/src/lib/api.ts` — FOUND (modified, push_stats type added)
- [x] `frontend/src/pages/Audit.tsx` — FOUND (modified, channel filter + tool badges)
- [x] `frontend/src/pages/Dashboard.tsx` — FOUND (modified, push failure alert banner)
- [x] Commit f4aef505 — FOUND in git log
- [x] Commit 13d3e22a — FOUND in git log
- [x] Commit f7d4aeaf — FOUND in git log
