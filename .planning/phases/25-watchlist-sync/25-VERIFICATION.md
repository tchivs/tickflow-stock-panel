---
phase: 25-watchlist-sync
verified: 2026-08-06T12:30:00Z
status: passed
score: 11/11 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
deferred: []
human_verification: []
---

# Phase 25: 自选股联动 (Watchlist Sync) Verification Report

**Phase Goal:** VIP users can star/watch stocks in the pool drill-down and filter to "只看自选" — a pure-frontend composition over the existing `/api/watchlist` CRUD + shared `QK.watchlist` cache, with guest rendering pixel-identical and strategy-card totals authoritative.
**Verified:** 2026-08-06T12:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## 结论 (Verdict)

**PASSED — 11/11 must-haves verified, 0 blockers, 0 human items.**

Phase 25 goal is achieved in the codebase. All four WATCH requirements are implemented in `PoolHubPage.tsx` / `StockListTable.tsx` / `storage.ts` and locked as observable behavior by six passing Playwright e2e cases plus three POOL-03 guard updates. Guest pixel-identity is preserved (zero-diff snapshot set + guest e2e assertions). `frontend/src/pages/Watchlist.tsx` was **not** touched by any phase-25 commit (user's pre-saved change intact). Zero backend changes, zero new npm dependencies.

Verification evidence: `npm run build` green; `npx playwright test pool-hub.spec.ts --project=desktop-chromium` → **40/40 passed**; backend smoke `test_pool_hub.py test_guest_masking.py` → **52 passed**; independent source-grep guard re-run clean.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | WATCH-01 VIP 星标: StockListTable VIP 代码单元格渲染星标 — 在自选实心 amber (`fill="currentColor"` + `text-[#FACC15]`), 不在空心 muted; `aria-label`/`title`=移出自选/加入自选; `disabled={watchlistPending}`; 点击 → `onToggleWatchlist(row.symbol, inList)` → `api.watchlistAdd/Remove` → 失效 `QK.watchlist` + `QK.watchlistEnriched()` | ✓ VERIFIED | `StockListTable.tsx:306-321` (星标按钮); `PoolHubPage.tsx:70-78` (toggle mutation + 双 key 失效); e2e `WATCH-01: VIP 星标渲染 + toggle` PASSED (POST body `symbol=600519.SH` + 星标翻转 + 二次 GET) |
| 2 | WATCH-01 guest 双门控 + 像素不变: watchlist 查询 `enabled: !!data && mode === 'vip'`; guest 会话零 `/api/watchlist` 查询、零星标/开关/批量控件; `isGuest` 分支与 `GUEST_COLUMNS` 五列不变, rowKey=ordinal 保留 | ✓ VERIFIED | `PoolHubPage.tsx:61-64` (`enabled: !!data && mode === 'vip'`); `StockListTable.tsx:311-326` (guest 分支原样渲染); e2e `WATCH-01 guest: 零 watchlist 查询 + 零自选控件/switch` PASSED (捕获数组无 `/api/watchlist`, 控件 count 0) |
| 3 | WATCH-02 只看自选: 钻取区 header `role="switch"` + `aria-checked` 开关仅 VIP; `filteredRows` = 概念子串 AND `watchlistSet.has(r.symbol)`; footer `筛选后 N 只 / 共 M 只` M=`activeStrategy.total` 权威; 只看自选 0 行 → 诚实空态「自选清单中无该策略个股」(优先于概念空态, 不插值 filterText); 状态存 `storage.poolWatchlistOnly` | ✓ VERIFIED | `PoolHubPage.tsx:167-190` (switch + storage 持久化); `PoolHubPage.tsx:81-94` (filteredRows base 变量重构, AND 组合); `StockListTable.tsx:229-241` (诚实空态 + 渲染序); e2e WATCH-02 三用例 PASSED (收窄/total、空态、历史同构) |
| 4 | WATCH-03 一致性: 复用 `QK.watchlist` + `api.watchlistList`; join 键 = `row.symbol` 全等 (无归一化/无 code 匹配); 不新建独立自选 key/localStorage 清单; `api.ts`/`queryKeys.ts`/`useSharedMutations.ts` 零改动 | ✓ VERIFIED | `PoolHubPage.tsx:58-66` (QK.watchlist + watchlistSet Set 投影); `StockListTable.tsx:311` (`watchlistSet.has(row.symbol)` 全等); `storage.ts:46` (`poolWatchlistOnly` 仅 UI 偏好布尔); `git log` 确认 api/queryKeys/useSharedMutations 无 phase-25 提交 |
| 5 | WATCH-04 批量: 「批量加自选」按钮仅 VIP 且 `!watchlistOnly`; `handleBatchAdd` scope = `filteredRows.map(r => r.symbol)` (display_limit 内可见行, 绝不按 total); 复用 `useWatchlistBatchAdd` (双 key 失效); toast `已添加 ${data.added} 只到自选` / `批量添加失败`; pending 文案 `添加中…` | ✓ VERIFIED | `PoolHubPage.tsx:80-96` (handleBatchAdd scope=filteredRows); `PoolHubPage.tsx:196-210` (批量按钮 + toast); `useSharedMutations.ts:32-41` (batch add 双失效); e2e `WATCH-04` PASSED (POST /api/watchlist/batch body.symbols 集合比较 = {300750.SZ, 600519.SH} + toast) |
| 6 | H9 fail-closed: watchlist 查询 pending/error 期星标与开关 `disabled`; error 期 switch `title="自选清单加载失败"` | ✓ VERIFIED | `StockListTable.tsx:307` (`disabled={watchlistPending}`); `PoolHubPage.tsx:176` (`disabled={watchlist.isPending \|\| watchlist.isError}` + `title` 条件); `PoolHubPage.tsx:221` (`watchlistPending = toggle.isPending \|\| watchlist.isPending \|\| watchlist.isError`) |
| 7 | 前端源码 grep 守卫不破: PoolHubPage/StockListTable 新增代码无 `<form`、无执行族 API 标识符、无裸 fetch 写动词、无连续 6 星号字面量、无 `mask` 标识符 | ✓ VERIFIED | 独立 grep 复核全 rc=1 (零命中); e2e `pool page source contains no execution API call or form` (test 18) + `frontend contains no client-side masking code` (test 22) PASSED |
| 8 | POOL-03 affordances 白名单扩增: `ALLOWED_RE` 加入 `只看自选\|批量加自选\|加入自选\|移出自选` | ✓ VERIFIED | `pool-hub.spec.ts:628` (ALLOWED_RE 含 4 新控件名); e2e `pool page renders zero execution affordances` (test 16) PASSED |
| 9 | POOL-03 no-mutating 语义放宽: VIP 放行 watchlist 写族, 其余 non-GET 仍 `toEqual([])`; execPaths 执行族断言保留; guest 零写由 WATCH-01 guest 用例锁死 | ✓ VERIFIED | `pool-hub.spec.ts:658-662` (watchlistWrites/otherWrites 拆分断言 + execPaths 保留); e2e `pool page never issues a mutating request` (test 17) PASSED |
| 10 | installShell 默认 mock `/api/watchlist` → `{symbols:[]}` (P5 防 VIP 自动 GET 落 unhandled 500); 具体用例后注册覆盖 | ✓ VERIFIED | `pool-hub.spec.ts:305-308` (installShell 末尾 watchlist mock, 在 `**/api/**` unhandled 兜底之后); WATCH-01/04 用例后注册精确 route 覆盖 |
| 11 | VIP 视觉快照重生成 (B1 修订): 表格区 4 张重生成 (resonance/filter-active/empty-zero-hit/vip-plaintext); 零 diff 断言集 4 张 (grid-populated/card-unavailable/guest-masked/guest-grid); docs/features.md 自选联动小节 + 计数 27 保持 1 处 | ✓ VERIFIED | `git show --stat ac59697` 确认仅 4 张重生成; `git status` 确认零 diff 集 4 张零变更; 视觉模型分析共振快照确认星标 + 只看自选 switch + 批量加自选按钮; backstop 用例 (test 21/24) PASSED; `docs/features.md:32` 「⭐ 自选股联动（Watchlist Sync）」小节, `grep -c "27 个内置策略"` = 1, `grep -c "QK.watchlist"` = 1 |

**Score:** 11/11 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | ----------- | ------ | ------- |
| `frontend/src/lib/storage.ts` | `poolWatchlistOnly: kv<boolean>('pool-watchlist-only')` UI 偏好键 | ✓ VERIFIED | L46, 注释明示「绝不存 symbol 清单」 |
| `frontend/src/pages/PoolHubPage.tsx` | 双门控查询 + watchlistSet + toggleWatchlist + watchlistOnly state + filteredRows AND + handleBatchAdd + header 控件 | ✓ VERIFIED | L58-96 (查询/投影/mutations), L167-213 (switch/批量/toast), L218-223 (props 透传) |
| `frontend/src/components/pool-hub/StockListTable.tsx` | 新 props 接口 + VIP 星标按钮 + 空态三分流 + footer filterActive 扩展 | ✓ VERIFIED | L44-54 (props), L306-321 (星标), L229-241 (空态), L389-395 (footer) |
| `frontend/e2e/pool-hub.spec.ts` | installShell mock + ALLOWED_RE + no-mutating 放宽 + WATCH-01..04 六用例 | ✓ VERIFIED | L308, L628, L658-662, L1105-1257 |
| 快照 ×4 重生成 | resonance / filter-active / empty-zero-hit / vip-plaintext | ✓ VERIFIED | `ac59697` 二进制变更, 视觉复核含控件增量 |
| 快照 ×4 零 diff | grid-populated / card-unavailable / guest-masked / guest-grid | ✓ VERIFIED | `git status --porcelain` 快照目录零变更 |
| `docs/features.md` | 「⭐ 自选股联动（Watchlist Sync）」小节 | ✓ VERIFIED | L32-36, 提及 QK.watchlist + 全后缀 symbol + guest 零控件零查询 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| PoolHubPage watchlist query | `/api/watchlist` (GET) | `enabled: !!data && mode === 'vip'` 双门控 | ✓ WIRED | L61-64; guest 首屏不误发 (main.tsx:22-27 401 跳登录根因已核实) |
| watchlistSet | `filteredRows` | `base.filter(r => watchlistSet.has(r.symbol))` AND 组合 | ✓ WIRED | L89; 概念子串投影后追加, 新数组引用 |
| 星标按钮 | toggleWatchlist mutation | `onToggleWatchlist(row.symbol, inList)` → `api.watchlistAdd/Remove` | ✓ WIRED | StockListTable L314 → PoolHubPage L219 |
| toggleWatchlist onSuccess | `QK.watchlist` + `QK.watchlistEnriched()` | `qc.invalidateQueries` 双 key | ✓ WIRED | L72-77; e2e 二次 GET 断言证实 |
| storage.poolWatchlistOnly | switch onChange | `setWatchlistOnly(v)` + `storage.poolWatchlistOnly.set(v)` | ✓ WIRED | L181-183; useState 初始化 L59 |
| 批量按钮 | `useWatchlistBatchAdd` | `handleBatchAdd` scope = filteredRows | ✓ WIRED | L80-88; e2e body 集合比较证实 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| watchlistSet | `watchlist.data?.symbols` | `api.watchlistList` → `QK.watchlist` 共享缓存 | ✓ 真实服务端 parquet 投影 (非静态/空集) | ✓ FLOWING |
| filteredRows | `activeStrategy.rows` + `watchlistSet` | `poolQuery` 单 as_of 载荷 (D-02) + watchlist 投影 | ✓ 真实行投影, 绝不原地改 `activeStrategy.rows` | ✓ FLOWING |
| footer total | `activeStrategy.total` | `poolQuery` strategies 数组 | ✓ 权威计数恒定 (H1) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Frontend build (tsc -b && vite build) | `cd frontend && npm run build` | ✓ built in 13.62s, 0 errors | ✓ PASS |
| 全量 pool-hub e2e (含 WATCH-01..04 + POOL-03 守卫 + backstop) | `cd frontend && npx playwright test pool-hub.spec.ts --project=desktop-chromium` | 40/40 passed (58.0s) | ✓ PASS |
| 后端 smoke (POOL-03/guest 守卫回归) | `cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py tests/test_guest_masking.py -x -q` | 52 passed (2.19s) | ✓ PASS |

### Probe Execution

Step 7c: N/A — no probe scripts declared in PLAN/SUMMARY; phase verification uses build + e2e + backend smoke (all executed above).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| WATCH-01 | 25-01 + 25-02 | VIP 星标渲染/toggle; guest 零控件零查询像素不变 | ✓ SATISFIED | 源码 + WATCH-01 VIP/guest e2e 双用例 PASSED |
| WATCH-02 | 25-01 + 25-02 | 只看自选收窄 + total 权威 + 诚实空态 + 历史同构 | ✓ SATISFIED | 源码 + WATCH-02 三用例 PASSED |
| WATCH-03 | 25-01 + 25-02 | 共享 QK.watchlist 缓存一致 + 全后缀 symbol 精确匹配 | ✓ SATISFIED | 源码 + WATCH-01 二次 GET (缓存失效) PASSED |
| WATCH-04 (P2) | 25-01 + 25-02 | 批量加可见行 (scope=filteredRows) + 成功 toast | ✓ SATISFIED | 源码 + WATCH-04 e2e PASSED |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | 无 (TBD/FIXME/XXX 零命中; 无 placeholder stub; `placeholderData` 命中为 react-query 合法选项, 非 stub) | — | — |

### 守卫审计 (POOL-03 + guest)

- **源码 grep 守卫** (e2e test 18/22 + 独立复核): `PoolHubPage.tsx`/`StockListTable.tsx` 零 `<form`、零执行族 API 标识符、零裸 fetch 写动词、零掩码字面量、零 `mask` 标识符。新控件全部经 `api.watchlist*` 封装与 props 回调。✓
- **affordances 白名单** (e2e test 16): ALLOWED_RE 含 `只看自选|批量加自选|加入自选|移出自选`, 遍历 main 内所有按钮守卫绿。✓
- **no-mutating 语义放宽** (e2e test 17): 非 watchlist 写仍 `toEqual([])`; watchlist 写本用例不触发也为空; execPaths 执行族断言保留。✓
- **guest 面**: WATCH-01 guest 用例断言捕获数组无 `/api/watchlist` + main 内星标/switch count 0; guest 快照零 diff + 视觉模型复核。✓
- **`Watchlist.tsx` 未触碰**: `git log --oneline -- frontend/src/pages/Watchlist.tsx` 最近提交为 `9c6c1fc` (phase-25 之前); `git status` 仅 `M frontend/src/pages/Watchlist.tsx` (用户预存未提交改动)。✓
- **提交链**: 25-01 = `f96766a`/`a18cb37`/`1e32126`/`36a7a3b`/`e29eb94` (5); 25-02 = `68a9c91`/`ce54616`/`ac59697`/`d4fab8a`/`5c5b368` (5)。✓
- **零后端改动 / 零新增 npm 依赖**: `git log` phase-25 提交仅触碰 frontend src/e2e/docs/.planning; 无 package.json 变更。✓

### Human Verification Required

无 — 全部行为由通过的行为测试锁定; 视觉快照经视觉模型独立复核 (星标/开关/批量按钮增量确认) 且 backstop 用例绿; 零 diff 集由 git 校验。executor 在 25-02-SUMMARY 文档化了其人工快照复核。

### Gaps Summary

无 gaps。一项非阻塞观察 (Info): `.planning/REQUIREMENTS.md` 底部 Traceability 表仍将 WATCH-01..04 标为 `Open`, 但需求定义区 (L19-22) 与 Phase 25 均已勾选完成 — 与 Phase 24 HIST-01 在 Traceability 表中同样遗留 `Open` 的项目先例一致, 属项目文档维护惯例, 不影响验收结论。

---

_Verified: 2026-08-06T12:30:00Z_
_Verifier: Claude (gsd-verifier)_
