---
phase: 03-ai-analysis
plan: 08
subsystem: ui
tags: [react, tanstack-query, playwright, accessibility, sse, analysis]
requires:
  - phase: 03-ai-analysis
    provides: Server-owned analysis reports, evidence projections, lifecycle reviews, and scoped SSE invalidation
provides:
  - Evidence-first object-local stock and portfolio analysis workspaces
  - Accessible report, evidence, and lifecycle reading panels
  - Green Phase 3 browser contracts for evidence, lifecycle, and responsive keyboard use
affects: [phase-03-verification, analysis-ui]
tech-stack:
  added: []
  patterns: [subject-scoped TanStack Query panels, server-projection-only rendering, native tab and details accessibility]
key-files:
  created: [frontend/src/components/analysis/AnalysisWorkspace.tsx, frontend/src/components/analysis/ReportPanel.tsx, frontend/src/components/analysis/EvidencePanel.tsx, frontend/src/components/analysis/LifecyclePanel.tsx, frontend/src/components/analysis/AnalysisStatus.tsx]
  modified: [frontend/src/pages/StockAnalysis.tsx, frontend/src/pages/Portfolio.tsx, frontend/src/components/financials/AiAnalysisHost.tsx, frontend/e2e/phase3-ai-analysis.spec.ts]
key-decisions:
  - "Keep display subjects as stock/portfolio while translating requests to the server-authorized instrument/account contract inside the workspace."
  - "Retire the legacy global free-text dialog host so persistent server reports are only reviewed in object-local workspaces."
requirements-completed: [ANLY-01, ANLY-02, ANLY-03]
coverage:
  - id: D1
    description: Evidence-first report and source disclosure for stock and portfolio subjects
    requirement: ANLY-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/phase3-ai-analysis.spec.ts#stock report exposes source grades, material evidence, and conflict before conclusions"
        status: pass
    human_judgment: false
  - id: D2
    description: Structured multi-perspective report, score explanation, valuation applicability, and IC memo
    requirement: ANLY-02
    verification:
      - kind: e2e
        ref: "frontend/e2e/phase3-ai-analysis.spec.ts#stock report exposes source grades, material evidence, and conflict before conclusions"
        status: pass
    human_judgment: false
  - id: D3
    description: Server-owned lifecycle timeline, review actions, and responsive accessible controls
    requirement: ANLY-03
    verification:
      - kind: e2e
        ref: "frontend/e2e/phase3-ai-analysis.spec.ts#portfolio lifecycle keeps server-owned history and review actions scoped"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/phase3-ai-analysis.spec.ts#responsive keyboard controls retain accessible analysis panels"
        status: pass
    human_judgment: false
duration: 11m 22s
completed: 2026-07-12
status: complete
---

# Phase 03 Plan 08: Evidence-First Analysis UI Summary

**Stock and account workspaces now render server-owned analysis evidence, structured reports, and lifecycle history with accessible independent panels.**

## Performance

- **Duration:** 11m 22s
- **Started:** 2026-07-12T05:10:26Z
- **Completed:** 2026-07-12T05:21:48Z
- **Tasks:** 3 completed
- **Files modified:** 9

## Accomplishments

- Added independently cached report, evidence, lifecycle, and coarse run-status panels that preserve successfully read content through a sibling refresh failure.
- Added object-local entries for the selected stock and selected portfolio account; removed the legacy global free-text dialog presentation.
- Converted the Phase 3 browser contracts from expected RED to green across stock evidence, portfolio lifecycle, and 1440/1024/375 keyboard-responsive scenarios.

## Task Commits

1. **Task 1: 构建独立加载的证据优先分析面板** - `ac50d75` (feat)
2. **Task 2: 将对象本地入口和既有 AI 宿主接到持久化报告** - `70c4cca` (feat)
3. **Task 3: 完成 evidence-first 浏览器验收** - `5d46c81` (test)
4. **API contract correction** - `0e741cf` (fix)

## Files Created/Modified

- `frontend/src/components/analysis/AnalysisWorkspace.tsx` - Subject-scoped query workspace, accessible tabs, status, report version selection, and run controls.
- `frontend/src/components/analysis/{ReportPanel,EvidencePanel,LifecyclePanel,AnalysisStatus}.tsx` - Server-projection-only evidence, report, lifecycle, and status views.
- `frontend/src/pages/StockAnalysis.tsx` and `frontend/src/pages/Portfolio.tsx` - Selected-object workspace integration.
- `frontend/src/components/financials/AiAnalysisHost.tsx` - Retained shell mount without the legacy unpersisted AI modal.
- `frontend/e2e/phase3-ai-analysis.spec.ts` - Fixture-routed green browser contracts.

## Verification

- `cd backend && uv run pytest tests/test_analysis_evidence.py tests/test_analysis_graph.py tests/test_analysis_service.py tests/test_analysis_lifecycle.py tests/test_analysis_api.py -q` - 39 passed.
- `cd frontend && pnpm exec playwright test e2e/phase3-ai-analysis.spec.ts --project=desktop-chromium` - 3 passed.
- `cd frontend && pnpm run build` - passed.

## Decisions Made

- UI-local `stock` and `portfolio` subjects are converted to API `instrument` and `account` values at the workspace boundary, keeping user-facing cache keys isolated without sending an invalid authorization category.
- Evidence, provenance, score interpretation, lifecycle state, and review authority are always rendered from API projections; the UI does not synthesize or persist them.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reconciled UI and server subject classifications**
- **Found during:** Final integration verification
- **Issue:** Existing API routes authorize `instrument/account`, while the UI subject model is `stock/portfolio`; direct requests would fail authorization.
- **Fix:** Added a private workspace adapter and fixture assertion for the server contract.
- **Files modified:** `frontend/src/components/analysis/AnalysisWorkspace.tsx`, `frontend/e2e/phase3-ai-analysis.spec.ts`
- **Verification:** Phase 3 Playwright contracts and production build pass.
- **Committed in:** `0e741cf`

**Total deviations:** 1 auto-fixed (1 Rule 1 bug).

## Known Stubs

None. The created and modified analysis files were scanned for UI-facing placeholder values and unresolved placeholder markers.

## Issues Encountered

- The Vite build emits existing large-chunk warnings for the main and ECharts bundles; it does not fail the build and is outside this plan's scope.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ANLY-01 through ANLY-03 have automated backend and browser evidence.
- Residual risk: browser fixtures validate the public analysis contract but do not use a live configured AI provider or market data source, by design.

## Self-Check: PASSED

- Summary file exists and all four implementation commits are present in Git history.
