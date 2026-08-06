---
phase: 25-watchlist-sync
plan: 2
subsystem: testing
tags: [playwright, e2e, watchlist, snapshots, docs]

# Dependency graph
requires:
  - phase: 25-watchlist-sync
    provides: 25-01 源码 — PoolHubPage 双门控 watchlist 查询 / StockListTable 星标 aria / 只看自选 switch / 批量加自选按钮 (f96766a/a18cb37/1e32126)
provides:
  - POOL-03 e2e 守卫同步 (installShell 默认 watchlist mock + ALLOWED_RE 白名单扩增 + no-mutating 语义放宽为「非 watchlist 写仍为零」)
  - WATCH-01..04 六条 e2e 用例 (星标渲染/toggle/缓存失效、guest 零查询零控件、只看自选收窄+total 权威+诚实空态+历史同构、批量 body=可见行)
  - VIP 表格区 4 张视觉快照重生成 (resonance/filter-active/empty-zero-hit/vip-plaintext), 零 diff 断言集 4 张 (grid-populated/card-unavailable/guest-masked/guest-grid)
  - docs/features.md「⭐ 自选股联动」小节
affects: [verify-work, ship, phase-26 前端规划]

# Actuals (#2632) — chars/4 over realized text diff (estimateTokens 同尺度), 非 harness token 计数.
actuals:
  tokens: 2896
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "e2e 请求捕获 + route 顺序化: installShell 默认 mock 后注册覆盖, 用计数式 GET 断言替代 exact-count (StrictMode 双挂载免疫)"
    - "no-mutating 守卫语义拆分: watchlist 写族 (POST /api/watchlist[/batch], DELETE /api/watchlist/{symbol}) 与其余 non-GET 分别断言"

key-files:
  created: []
  modified:
    - frontend/e2e/pool-hub.spec.ts
    - frontend/e2e/pool-hub.spec.ts-snapshots/pool-table-resonance-desktop-chromium-linux.png
    - frontend/e2e/pool-hub.spec.ts-snapshots/pool-table-filter-active-desktop-chromium-linux.png
    - frontend/e2e/pool-hub.spec.ts-snapshots/pool-empty-zero-hit-desktop-chromium-linux.png
    - frontend/e2e/pool-hub.spec.ts-snapshots/pool-vip-plaintext-desktop-chromium-linux.png
    - docs/features.md

key-decisions:
  - "B1 修订 (REVIEW round 1): 快照重生成范围从 2 张修正为表格区 4 张 (resonance/filter-active/empty-zero-hit/vip-plaintext); 零 diff 断言集修正为真实不变集 grid-populated/card-unavailable/guest-masked/guest-grid — 原计划把 VIP 快照误标为 guest, verify 门自身必失败"
  - "WATCH-01 二次 GET 断言用计数式 (watchlistGetCount 增加) 而非精确次数 — StrictMode 双挂载下初始 GET 次数不保证为 1 (REVIEW I1)"
  - "installShell 默认 watchlist mock 仅返回 {symbols:[]} 空集, 具体用例后注册精确 route 覆盖 (Playwright 后注册优先) — 防 VIP 自动 GET /api/watchlist 落 unhandled 500 (P5)"
  - "批量 body 断言用 Set 集合比较 (顺序不敏感) — WATCH-04 契约是「恰为可见行 symbol 数组」, 不锁顺序"

patterns-established:
  - "e2e 守卫同步纪律: 生产源码新增交互控件必须同步登记 affordances 白名单 + 复核 no-mutating 捕获数组语义"
  - "快照重生成只对受影响帧执行 --update-snapshots, 零 diff 断言集用 git status 校验防连带漂移"

requirements-completed: [WATCH-01, WATCH-02, WATCH-03, WATCH-04]

coverage:
  - id: D1
    description: "POOL-03 e2e 守卫同步 — installShell 默认 watchlist mock (P5) + ALLOWED_RE 白名单扩增 只看自选|批量加自选|加入自选|移出自选 (P1) + no-mutating 语义放宽为「非 watchlist 写仍为零」(VIP 放行 watchlist 写, guest 零写由 D2 锁死)"
    requirement: WATCH-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#pool page renders zero execution affordances (POOL-03)"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#pool page never issues a mutating request (POOL-03)"
        status: pass
    human_judgment: false
  - id: D2
    description: "WATCH-01 e2e — VIP 星标渲染 + toggle 调 POST /api/watchlist body.symbol + 共享缓存失效重取 (二次 GET); guest 载荷零 /api/watchlist 查询 + main 内零 加入自选/移出自选/switch 控件"
    requirement: WATCH-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#WATCH-01: VIP 星标渲染 + toggle 调 POST /api/watchlist + 共享缓存失效重取"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#WATCH-01 guest: 零 watchlist 查询 + 零自选控件/switch"
        status: pass
    human_judgment: false
  - id: D3
    description: "WATCH-02 e2e — 只看自选收窄到自选行 + total 权威不变 (筛选后 1 只 / 共 2 只); 诚实空态「自选清单中无该策略个股」(无「无符合『』」误报); 历史同构 (开关跨日期保持, footer 按历史 total 权威)"
    requirement: WATCH-02
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#WATCH-02: 只看自选收窄到自选行 + total 权威不变"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#WATCH-02: 诚实空态 — 自选不含策略行时显示专属文案 (P4)"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#WATCH-02: 历史同构 — 开关跨日期保持生效, footer 按历史 total 权威"
        status: pass
    human_judgment: false
  - id: D4
    description: "WATCH-04 e2e — 批量加自选 POST /api/watchlist/batch body.symbols 恰为可见行 symbol 数组 (Set 集合比较) + 成功 toast 已添加 2 只到自选"
    requirement: WATCH-04
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#WATCH-04: 批量加自选 body = 可见行 symbols + 成功 toast"
        status: pass
    human_judgment: false
  - id: D5
    description: "VIP 表格区 4 张视觉快照重生成 (resonance/filter-active/empty-zero-hit/vip-plaintext) + 零 diff 断言集 4 张 (grid-populated/card-unavailable/guest-masked/guest-grid) + docs/features.md 自选股联动小节"
    requirement: WATCH-03
    verification:
      - kind: automated_ui
        ref: "frontend/e2e/pool-hub.spec.ts#captures visual evidence for the five UI-SPEC backstop scalars"
        status: pass
      - kind: automated_ui
        ref: "frontend/e2e/pool-hub.spec.ts#captures visual evidence for guest mode backstops"
        status: pass
      - kind: other
        ref: "git status zero-diff assertion set (grid-populated/card-unavailable/guest-masked/guest-grid) = 0"
        status: pass
      - kind: other
        ref: "grep '⭐ 自选股联动'=1 && grep 'QK.watchlist'=1 && grep '27 个内置策略'=1"
        status: pass
    human_judgment: false

# Metrics
duration: 14min
completed: 2026-08-06
status: complete
---

# Phase 25 Plan 2: 自选股联动 e2e 契约 + WATCH 用例 + VIP 快照重生成 Summary

**POOL-03 e2e 三条守卫随 25-01 新控件同步 (installShell 默认 /api/watchlist mock + affordances 白名单扩增 + no-mutating 放宽为「非 watchlist 写仍为零」), 新增 WATCH-01..04 六条 Playwright 用例锁死星标/开关/批量行为, VIP 表格区 4 张 backstop 快照重生成 (零 diff 断言集 4 张 git 校验), docs/features.md 补自选联动小节**

## Performance

- **Duration:** 14 min
- **Started:** 2026-08-06T06:02:57Z
- **Completed:** 2026-08-06T06:17:00Z
- **Tasks:** 3
- **Files modified:** 6 (pool-hub.spec.ts + 4 snapshots + docs/features.md)

## Accomplishments
- POOL-03 守卫同步全绿: installShell 末尾默认 `**/api/watchlist**` → `{symbols:[]}` (P5 防 VIP 自动 GET 落 unhandled 500); `ALLOWED_RE` 扩增 `只看自选|批量加自选|加入自选|移出自选` (P1 新控件可访问名全登记); no-mutating 断言从「零 non-GET」改为「watchlist 写族放行 + 其余 non-GET 仍 toEqual([])」, execPaths 执行族断言保留。
- WATCH-01..04 六用例全绿: VIP 星标渲染 + toggle 捕获 `POST /api/watchlist` body.symbol=600519.SH + 共享缓存失效二次 GET (计数式, StrictMode 免疫); guest 载荷捕获数组无 `/api/watchlist` + main 内 加入自选/移出自选/switch 全 0; 只看自选收窄 + total 权威 (筛选后 1 只 / 共 2 只) + 诚实空态 (无「无符合『』」误报) + 历史同构 (开关跨日期保持, footer 按历史 total 5); 批量 `POST /api/watchlist/batch` body.symbols 集合比较 = 可见行 + toast。
- VIP 表格区 4 张快照重生成 (B1 修订后范围), 经 ui_diff 逐张复核仅星标/开关/批量按钮增量, 无其他漂移; 零 diff 断言集 (grid-populated/card-unavailable/guest-masked/guest-grid) git 校验 0 变更; guest 逐像素不变由快照零 diff + WATCH-01 guest 用例双保险。
- docs/features.md「⭐ 自选股联动」小节落地, 提及共享 `QK.watchlist` 缓存 + 全后缀 symbol 匹配键 + guest 零控件零查询; 「27 个内置策略」计数行仍 1 处。
- 全量验证: `npm run build` 绿 + `npx playwright test pool-hub.spec.ts --project=desktop-chromium` 40/40 绿 + 后端 smoke `test_pool_hub.py test_guest_masking.py` 52 passed (零后端改动确认)。

## Task Commits

Each task was committed atomically:

1. **Task 1: POOL-03 e2e 守卫同步 (installShell mock + ALLOWED_RE + no-mutating 放宽)** - `68a9c91` (test)
2. **Task 2: WATCH-01..04 e2e 六用例 + watchlist fixtures** - `ce54616` (test)
3. **Task 3: VIP 4 张快照重生成 + docs/features.md 自选联动小节** - `ac59697` (docs)

**Plan metadata:** pending final docs commit (SUMMARY + STATE)

## Files Created/Modified
- `frontend/e2e/pool-hub.spec.ts` - installShell 末尾默认 watchlist mock; ALLOWED_RE 扩增 4 个新控件名; no-mutating 守卫拆分 watchlist 写族/其余 non-GET; 新增 WATCH-01..04 六用例 + watchlistPayloadSingle/Both/Empty/NoMatch fixtures
- `frontend/e2e/pool-hub.spec.ts-snapshots/pool-table-resonance-desktop-chromium-linux.png` - 重生成 (星标 + header 控件增量)
- `frontend/e2e/pool-hub.spec.ts-snapshots/pool-table-filter-active-desktop-chromium-linux.png` - 重生成 (星标 + header 控件增量)
- `frontend/e2e/pool-hub.spec.ts-snapshots/pool-empty-zero-hit-desktop-chromium-linux.png` - 重生成 (header 控件增量)
- `frontend/e2e/pool-hub.spec.ts-snapshots/pool-vip-plaintext-desktop-chromium-linux.png` - 重生成 (星标 + header 控件增量)
- `docs/features.md` - 补「⭐ 自选股联动（Watchlist Sync）」小节 (共享 QK.watchlist 缓存 + 全后缀 symbol 精确匹配 + guest 零控件零查询)

## Decisions Made
- **B1 修订采纳 (REVIEW round 1):** 快照重生成范围修正为表格区 4 张; 零 diff 断言集修正为 `pool-grid-populated|pool-card-unavailable|pool-guest-masked|pool-guest-grid`。原计划把 VIP 载荷快照 (grid-populated/empty-zero-hit/card-unavailable) 误标为 guest 且 verify 门 grep 计数必失败 — 按修订后动作执行。
- **WATCH-01 二次 GET 断言用计数式** (`watchlistGetCount` 较点击前增加) 而非精确次数 — StrictMode 双挂载下初始 GET 次数不保证为 1 (REVIEW I1)。
- **installShell 默认 watchlist mock 方法无关返回 `{symbols:[]}`** — 具体用例后注册精确 route 覆盖; 写端点由 WATCH 用例显式覆盖, 未点击星标/批量时 watchlist 写亦为空 (no-mutating 双断言)。
- **批量 body 用 Set 集合比较** — 契约是「恰为可见行 symbol 数组」, 顺序不敏感。

## Deviations from Plan

None - plan executed as written (B1 修订已内联于计划本身, 按修订后动作执行)。

---

**Total deviations:** 0
**Impact on plan:** None

## Issues Encountered
- 执行开始时 25-01 尚未合入 (Task 1 precondition grep 无命中), 经与 Executor25A (wave 1) hub 协调等待其 f96766a/a18cb37/1e32126 合入后前置门全过, 未 halt。
- `ui_diff_check` 对两张快照首调超时, 重试成功; 4 张快照均经人工视觉复核确认仅预期增量。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 25 (WATCH-01..04) 行为验证与文档全部落地; 全部 4 项需求经 e2e 覆盖。
- 快照基线已更新, 后续任何表格区视觉改动会触发 backstop 对比 (2% diff 容差)。
- 遗留: 用户 `frontend/src/pages/Watchlist.tsx` 未提交改动仍在工作树 (本计划零触碰), 交付时 git status 仅剩该文件。

---
*Phase: 25-watchlist-sync*
*Completed: 2026-08-06*

## Self-Check: PASSED

- 25-02-SUMMARY.md 存在
- 提交 68a9c91 / ce54616 / ac59697 存在
- 关键文件存在: pool-hub.spec.ts / docs/features.md / 重生成快照 4 张
- 零 diff 断言集 git 校验 0 变更 (grid-populated/card-unavailable/guest-masked/guest-grid)
