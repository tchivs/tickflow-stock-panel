---
phase: 57-client-rules
plan: 01
subsystem: ui
tags: [localStorage, websocket, notification-api, react-hooks, rules-engine]

# Dependency graph
requires:
  - phase: 55-websocket
    provides: WS quotes 频道订阅 (subscribe('quotes') + quotes_updated 事件)
provides:
  - ClientRule 类型 + evaluateRules 纯评估引擎 + 5 分钟防抖
  - localStorage client_rules 存储 (storage.clientRules kv key)
  - useClientRulesEngine hook (WS quotes 订阅 → 行情 refetch → 本地评估 → 通知触发)
  - ClientRulesProvider + useClientRules() Context (供 Plan 02 Monitor 页面消费)
  - Notification API 权限管理 + 降级 (toast + 声效)
affects: [57-02, client-rules-ui, monitor-page]

# Actuals (#2632)
actuals:
  tokens: 5000
  tasks: 3
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns: [localStorage kv pattern for client rules, WS subscribe → invalidateQueries → evaluate, module-level debounce Map, Notification API graceful degradation]

key-files:
  created:
    - frontend/src/lib/clientRules.ts
    - frontend/src/lib/clientRules.test.ts
    - frontend/src/hooks/useClientRulesEngine.tsx
  modified:
    - frontend/src/lib/storage.ts
    - frontend/src/components/Layout.tsx

key-decisions:
  - "storage.clientRules 用 kv<unknown[]>('client_rules') + clientRules.ts 内类型断言, 避免 storage.ts ↔ clientRules.ts 循环依赖"
  - "useClientRulesEngine.tsx (非 .ts) 因含 JSX Provider — Vite/tsc 需 .tsx 扩展"
  - "Task 2 (Context + Provider) 合并到 Task 1 tracer — plan 允许此合并"
  - "评估引擎为纯函数, hook 内用 useQuery + subscribe('quotes') → invalidateQueries 触发 refetch, data 更新后 useEffect 评估"

patterns-established:
  - "localStorage rules store: kv<unknown[]> + 类型断言避免循环依赖"
  - "WS-driven evaluation: subscribe → invalidateQueries → refetch → useEffect evaluate"
  - "Module-level debounce Map (不持久化), clearTriggered 供 markHandled 调用"
  - "Notification API 三级触发: toast() + playNotificationSound() + showNotification(), 权限被拒静默降级"

requirements-completed: [CR-01, CR-02]

coverage:
  - id: D1
    description: "ClientRule 类型 + localStorage 存储键 client_rules (CR-01): 规则 CRUD 纯函数 (load/save/add/update/delete/markHandled/disableRule)"
    requirement: CR-01
    verification:
      - kind: unit
        ref: "frontend/src/lib/clientRules.test.ts#evaluateRules — basic (5 cases)"
        status: pass
      - kind: unit
        ref: "frontend/src/lib/clientRules.test.ts#evaluateRules — edge cases (5 cases)"
        status: pass
      - kind: other
        ref: "pnpm build (tsc + vite) pass"
        status: pass
    human_judgment: false
  - id: D2
    description: "useClientRulesEngine hook: subscribe('quotes') → quotes_updated → invalidateQueries → evaluateRules → triggerAlert (toast + sound + Notification API) + 5min 防抖 (CR-02)"
    requirement: CR-02
    verification:
      - kind: unit
        ref: "frontend/src/lib/clientRules.test.ts#debounce (2 cases) + debounce reset (1 case)"
        status: pass
      - kind: other
        ref: "pnpm build pass — hook compiles with correct TS types"
        status: pass
    human_judgment: false
  - id: D3
    description: "ClientRulesProvider 全局挂载于 Layout.tsx, useClientRules() Context 供 Plan 02 消费"
    requirement: CR-02
    verification:
      - kind: other
        ref: "pnpm build pass — Layout wraps with <ClientRulesProvider>"
        status: pass
    human_judgment: false

# Metrics
duration: 10min
completed: 2026-08-22
status: complete
---

# Phase 57 Plan 01: 客户端规则引擎核心 Summary

**localStorage 规则存储 + WS quotes 订阅本地评估 + Notification API 弹窗 + toast + 声效 + 5 分钟防抖的端到端 tracer 切片**

## Performance

- **Duration:** 10 min
- **Started:** 2026-08-22T08:56:54Z
- **Completed:** 2026-08-22T09:07:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- `storage.ts` 新增 `clientRules: kv<unknown[]>('client_rules')` 键, 规则持久化 localStorage (D-01)
- `clientRules.ts` 实现完整规则引擎: ClientRule 类型 + CRUD (load/save/add/update/delete/markHandled/disableRule) + evaluateRules 纯评估函数 + 模块级 5 分钟防抖 Map + Notification API (request/show + 降级) + triggerAlert (toast+sound+notification 组合)
- `clientRules.test.ts` 13 个 vitest 用例: 评估引擎基本 5 + 边界 5 (op 边界/缺字段/pct 优先/多规则) + 防抖 2 + 防抖重置 1
- `useClientRulesEngine.tsx` hook: subscribe('quotes') → quotes_updated → invalidateQueries(QK.watchlistQuotes) → refetch → evaluateRules → 防抖检查 → triggerAlert; 暴露 rules/triggered/CRUD/notificationPermission; 含 ClientRulesProvider + useClientRules() Context
- `Layout.tsx` 全局挂载 `<ClientRulesProvider>`, 所有子页面可 useContext 消费

## Task Commits

Each task was committed atomically:

1. **Task 1+2: 端到端 tracer (存储→评估→通知) + ClientRulesContext** - `09fcf953` (feat)
2. **Task 3: 评估引擎边界用例 + 防抖重置测试** - `7d41f975` (test)

## Files Created/Modified

- `frontend/src/lib/storage.ts` - 新增 clientRules kv 键 (localStorage key=client_rules)
- `frontend/src/lib/clientRules.ts` - 规则类型 + CRUD + evaluateRules 纯函数 + 防抖 + Notification API + triggerAlert
- `frontend/src/lib/clientRules.test.ts` - 13 vitest 用例 (评估 10 + 防抖 3)
- `frontend/src/hooks/useClientRulesEngine.tsx` - WS 订阅 + 行情 refetch + 评估 + 通知 hook + ClientRulesProvider Context
- `frontend/src/components/Layout.tsx` - 全局挂载 ClientRulesProvider

## Decisions Made

- **storage.clientRules 用 `kv<unknown[]>` + 类型断言**: 避免 storage.ts 导入 ClientRule (从 clientRules.ts) 造成循环依赖 — clientRules.ts 导入 storage, 若 storage 反向导入 clientRules 则循环。用 `kv<unknown[]>` + clientRules.ts 内 `as ClientRule[]` 断言解决。
- **useClientRulesEngine.tsx (非 .ts)**: hook 文件含 JSX (ClientRulesProvider return `<Context.Provider>`)，需 .tsx 扩展供 tsc/vite 解析。
- **Task 2 合并到 Task 1**: Plan 明确允许 "若 Task 1 已包含 Context, 此任务可合并到 Task 1"。tracer 已含 ClientRulesProvider, 合并提交。
- **评估时机用 useQuery + invalidateQueries**: 与 useWsStream 的 `_invalidateQueries` 模式一致 — WS 消息触发 React Query invalidation, refetch 完成后 useEffect[data] 评估, 避免在 WS 回调内直接 fetch。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] useClientRulesEngine.ts → .tsx 重命名**
- **Found during:** Task 1 (pnpm build)
- **Issue:** hook 文件含 JSX (Provider return `<Context.Provider>`), .ts 扩展下 tsc 报 TS1005 '>', expected
- **Fix:** 重命名为 useClientRulesEngine.tsx, 更新 Layout.tsx 导入路径 (无扩展, Vite 自动解析)
- **Files modified:** frontend/src/hooks/useClientRulesEngine.tsx
- **Verification:** pnpm build pass
- **Committed in:** 09fcf953 (Task 1 commit)

**2. [Rule 3 - Blocking] 修正 import 路径 (./ → @/lib/)**
- **Found during:** Task 1 (pnpm build)
- **Issue:** hook 在 src/hooks/ 但导入 `./useWsStream` `./api` `./queryKeys` `./clientRules` — 这些在 src/lib/, 路径错误
- **Fix:** 改为 `@/lib/useWsStream` `@/lib/api` `@/lib/queryKeys` `@/lib/clientRules`; 移除未用的 `saveRules` `Quote` 导入
- **Files modified:** frontend/src/hooks/useClientRulesEngine.tsx
- **Verification:** pnpm build pass
- **Comitted in:** 09fcf953 (Task 1 commit)

**3. [Rule 1 - Bug] 显式类型注解修复 implicit any**
- **Found during:** Task 1 (pnpm build)
- **Issue:** subscribe handler 参数 `_data`, `type` 和 `.then(perm => ...)` 在严格 tsc 下 implicit any (TS7006)
- **Fix:** 添加显式类型 `Record<string, unknown>` / `string` / `NotificationPermission`
- **Files modified:** frontend/src/hooks/useClientRulesEngine.tsx
- **Verification:** pnpm build pass
- **Committed in:** 09fcf953 (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 bug)
**Impact on plan:** 全部为实现可构建的必要修正, 无范围蔓延。

## Issues Encountered

- 无重大问题。Layout.tsx 编辑时出现临时重复 `<div>` 标签, 已立即修复。

## User Setup Required

None - no external service configuration required. 客户端规则纯浏览器端, 不需后端配置。

## Next Phase Readiness

- 规则引擎核心就绪: Plan 02 可通过 `useClientRules()` 消费 rules/triggered/CRUD/notificationPermission
- ClientRulesProvider 已在 Layout 全局挂载, Monitor 页面直接 useContext 即可
- 待 Plan 02: 客户端规则编辑器 UI + 命中列表 UI + Notification 权限请求按钮

---
## Self-Check: PASSED

- FOUND: frontend/src/lib/clientRules.ts
- FOUND: frontend/src/lib/clientRules.test.ts
- FOUND: frontend/src/hooks/useClientRulesEngine.tsx
- FOUND: .planning/phases/57-client-rules/57-01-SUMMARY.md
- FOUND: 09fcf953 (feat commit)
- FOUND: 7d41f975 (test commit)
- storage.ts line 141: clientRules kv key confirmed
- Layout.tsx: ClientRulesProvider import + wrap confirmed

---
*Phase: 57-client-rules*
*Completed: 2026-08-22*
