---
phase: 28-concept-pit
plan: 2
subsystem: ui
tags: [react, typescript, playwright, pool-hub, concept-attribution, pit-history]

# Dependency graph
requires:
  - phase: 28-01
    provides: backend concept_attribution / concept_effective_date / concept_captured_at contract (pool_hub `_project_hub` + `/api/pool/history` passthrough)
provides:
  - PoolHubResponse type extension (concept_effective_date / concept_captured_at)
  - ConceptAttributionBadge component (server-frozen attribution dual-state + effective date)
  - PoolHubPage detail-header render site (zero render when attribution missing)
  - concept-pit.spec.ts e2e (current_snapshot / as_of_snapshot / unavailable)
  - docs/features.md 概念板块 PIT section
affects: [28-03, verifier, ui-review, ship]

# Actuals (#2632) — chars/4 over the realized diff (5 files, e8f11e7 → 1785681)
actuals:
  tokens: 4498
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Server-frozen attribution badge (mirrors AuctionColumnStatusBadge): zero client inference, PIT-3 discipline, top-level element not per-row"
    - "Independent e2e spec copying installShell helpers (no cross-file import coupling); literal badge copy matches component consts"

key-files:
  created:
    - frontend/e2e/concept-pit.spec.ts
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/components/pool-hub/StockListTable.tsx
    - frontend/src/pages/PoolHubPage.tsx
    - docs/features.md

key-decisions:
  - "Badge renders effectiveDate directly (no fmtDate call) — server already emits ISO date; keep render simple (PLAN-CHECK N-4)"
  - "as_of e2e navigates via two-step combobox (07-31 → 08-04) to guarantee the change event fires (latest date is default-selected)"
  - "installShell omits /api/pool/premarket route — premarket 500 keeps showPremarket false so hub flow renders (pool-hub.spec precedent)"
  - "Skipped state.advance-plan — parallel 28-03 executor would double-advance the shared plan counter"

patterns-established:
  - "Concept attribution badge: server-frozen concept_attribution drives dual-state copy + effective date; top-level element, never per-row"
  - "e2e fixture discipline: concept fixtures reuse pool-hub doublyHitRow shape; literal badge copy matches component consts"

requirements-completed: [CONCEPT-04, CONCEPT-07]

coverage:
  - id: D1
    description: "PoolHubResponse 类型扩展 — concept_effective_date / concept_captured_at (全可选, 向后兼容 guest/旧后端)"
    requirement: CONCEPT-07
    verification:
      - kind: e2e
        ref: "frontend/e2e/concept-pit.spec.ts#as_of_snapshot 载荷 → 按日文案 + 概念数据生效日期, 无回退徽标"
        status: pass
      - kind: other
        ref: "cd frontend && npm run build"
        status: pass
    human_judgment: false
  - id: D2
    description: "ConceptAttributionBadge 组件 + PoolHubPage detail-header 渲染位 — as_of_snapshot 按日文案 + 生效日期; 其余态诚实警告; 缺键零渲染"
    requirement: CONCEPT-04
    verification:
      - kind: e2e
        ref: "frontend/e2e/concept-pit.spec.ts#current_snapshot 载荷 → 回退警告徽标"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/concept-pit.spec.ts#unavailable 载荷 → 诚实警告徽标"
        status: pass
    human_judgment: false
  - id: D3
    description: "concept-pit e2e 三态 (current_snapshot / as_of_snapshot / unavailable) 全绿, 3 passed desktop"
    requirement: CONCEPT-04
    verification:
      - kind: e2e
        ref: "cd frontend && npx playwright test e2e/concept-pit.spec.ts"
        status: pass
    human_judgment: false
  - id: D4
    description: "docs/features.md 概念板块 PIT 小节 — 前向归档 + as_of 三态 + effective date 展示 + 诚实回退"
    requirement: CONCEPT-07
    verification:
      - kind: other
        ref: "grep -c \"概念板块 PIT\" docs/features.md >= 1 && grep -c \"ext_history\" docs/features.md >= 1"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-08-06
status: complete
---

# Phase 28 Plan 2: 概念板块 PIT 前端徽标 Summary

**CONCEPT-04/07 前端交付: 股池页 detail header 概念归属诚实徽标 (服务端冻结 concept_attribution 驱动, as_of_snapshot 按日文案 + 概念数据生效日期) + 三态 Playwright e2e + features 文档**

## Performance

- **Duration:** 5 min (wave 2, parallel with 28-03)
- **Started:** 2026-08-06T11:28:48Z
- **Completed:** 2026-08-06T11:30:21Z
- **Tasks:** 3
- **Files modified:** 5 (3 src + 1 e2e + 1 doc)

## Accomplishments
- `PoolHubResponse` 追加 `concept_effective_date` / `concept_captured_at`（全可选, guest/旧后端兼容）
- `ConceptAttributionBadge` 双态组件: `as_of_snapshot` → 「概念按当日快照 · 概念数据生效日期 {date}」; 其余 → 「概念归属为当前快照，非该日数据」（零客户端推断, PIT-3）
- `PoolHubPage` detail header 渲染位（attribution 存在时渲染, 载荷缺键零渲染）
- `concept-pit.spec.ts` 三态 e2e 全绿（current_snapshot / as_of_snapshot / unavailable）
- `docs/features.md` 概念板块 PIT 小节 + 日期导航小节补注
- 回归: `pool-hub.spec.ts` 40 passed / 80 skipped, 零 snapshot 变更; 后端 `test_pool_hub` + `test_concept_history` 50 passed
- `Watchlist.tsx` 零改动（git status 证明, 仅保留用户未提交改动）

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer): CONCEPT-04 垂直切片 — api 类型 + badge + 渲染位** - `652e0b6` (feat)
2. **Task 2: concept-pit e2e 三态** - `5da597d` (test)
3. **Task 3: docs/features.md 概念板块 PIT 小节** - `1785681` (docs)

**Plan metadata:** 待 final docs commit（SUMMARY + STATE + ROADMAP + REQUIREMENTS）.

## Files Created/Modified
- `frontend/src/lib/api.ts` - PoolHubResponse 追加 concept_effective_date / concept_captured_at（全可选）
- `frontend/src/components/pool-hub/StockListTable.tsx` - 新增导出 ConceptAttributionBadge + 徽标文案模块级 const
- `frontend/src/pages/PoolHubPage.tsx` - import ConceptAttributionBadge + detail header 渲染位
- `frontend/e2e/concept-pit.spec.ts` - 三态 e2e（新建, 独立 spec 自足 installShell）
- `docs/features.md` - 新增「🧭 概念板块 PIT（历史映射）」小节 + 日期导航补注

## Decisions Made
- **effectiveDate 直接渲染**（不调 fmtDate）: 服务端已外露 ISO 日期串, 保持渲染简单（PLAN-CHECK N-4 认可, fmtDate 引用属无害）。
- **as_of e2e 两步导航**（07-31 → 08-04）: 最新日 08-04 为下拉默认选中, 单选同值可能不触发 change 事件; 两步保证真实值变化, 且历史必走 `/api/pool/history`（PIT-1）。
- **installShell 不注册 `/api/pool/premarket`**: 预览查询 500 → showPremarket 保持 false, hub 流正常渲染（pool-hub.spec 同款外壳先例; 若注册 available:false 空态会压过 hub 流, 因 DATES 不含今日）。
- **徽标文案提为模块级 const**, e2e 用同字面量断言（独立 spec 不 import 跨文件耦合）。
- **跳过 `state.advance-plan`**: 并行 28-03 也会推进共享计划计数器, 双 advance 会使 phase 提前翻页（交给 orchestrator wave 收尾时推进）。

## Deviations from Plan

None - plan executed exactly as written. PLAN-CHECK 备注均已按计划应用:
- installShell 自注册 `/api/pool/history` 默认路由（premarket 复制源不含, N-1）。
- `fmtDate` 未使用属无害（N-4）。
- 徽标文案按计划字面量落地。

### TDD Gate Compliance

计划 frontmatter `type: execute`（非 tdd plan-level gate）。Task 1/2 标记 `tdd="true"` 但仓库无 vitest 且计划明确禁止引入; 前端行为断言由 Playwright e2e（Task 2）承担, Task 1 以 `npm run build`（tsc 严格类型门）作编译测试。提交链含 `test(28-02)`（5da597d, 行为回归门）与 `feat(28-02)`（652e0b6, 实现）; 无独立 RED test 提交, 按 tdd_execution 约定记录此说明。

## Issues Encountered
- **并行 executor 28-03 插入共享分支 commit `c3bece0`**（位于我的 Task 2 与 Task 3 之间）: 我的 Task 3 基于其 tip 提交, 仅含 `docs/features.md`, 无文件冲突; 28-03 的 in-flight 文件（`rps_rotation.py` / `test_concept_seam.py`）未被我触碰。
- **`state.advance-plan` 并行竞态**: 为避免双 advance 使 phase 计划计数器提前翻页, 本执行器跳过该调用（见 Decisions）。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- CONCEPT-04/07 前端展示闭环: 历史股池视图可见概念归属徽标 + 概念数据生效日期; 后端 attribution 契约经 50 passed 确认。
- 28-03（CONCEPT-06 seam）并行进行中; 前端零文件与其重叠。
- `Watchlist.tsx` 用户未提交改动保留原样, 供用户自行处理。

---
*Phase: 28-concept-pit*
*Completed: 2026-08-06*
