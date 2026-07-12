---
phase: 03-ai-analysis
plan: 12
subsystem: analysis-ui
tags: [react, typescript, tanstack-query, playwright, fastapi, dto, lifecycle]
requires:
  - phase: 03-11
    provides: allowlisted report, evidence, and lifecycle display DTOs with server-issued signal IDs
provides:
  - typed frontend contracts aligned with the analysis display projection
  - report-to-signal lifecycle history loading and server-owned review/plan/outcome rendering
  - browser regression coverage for stock and portfolio DTO paths
affects: [analysis-ui, lifecycle-history, phase-03-verification]
tech-stack:
  added: []
  patterns: [display-subject-to-request-subject boundary, signal-scoped query, server-owned lifecycle projection]
key-files:
  created: []
  modified: [frontend/src/lib/api.ts, frontend/src/components/analysis/AnalysisWorkspace.tsx, frontend/src/components/analysis/ReportPanel.tsx, frontend/src/components/analysis/LifecyclePanel.tsx, frontend/e2e/phase3-ai-analysis.spec.ts]
key-decisions:
  - "UI display subjects remain stock/portfolio while the typed API client accepts only instrument/account request subjects."
  - "Lifecycle history is enabled only from the authorized report signal_id and is rendered from server projection fields without browser-derived state."
  - "Evidence limitations use optional-to-empty semantics so older or partial display projections cannot break report rendering."
patterns-established:
  - "Lifecycle mutations send only a server-issued review ID plus the bounded window_days payload, then invalidate the same subject-scoped history key."
requirements-completed: [ANLY-01, ANLY-02, ANLY-03]
coverage:
  - id: D1
    description: Report and evidence panels consume the allowlisted display DTO, including absent limitations and top-level material numbers.
    requirement: ANLY-01
    verification:
      - kind: e2e
        ref: frontend/e2e/phase3-ai-analysis.spec.ts
        status: pass
      - kind: integration
        ref: backend/tests/test_analysis_host_integration.py#test_authenticated_main_host_completes_governed_analysis_and_persists_immutable_artifacts
        status: pass
    human_judgment: false
  - id: D2
    description: Multi-perspective report, score, valuation, and IC memo consume the server report projection without mock-only fields.
    requirement: ANLY-02
    verification:
      - kind: e2e
        ref: frontend/e2e/phase3-ai-analysis.spec.ts
        status: pass
      - kind: other
        ref: cd frontend && pnpm run build
        status: pass
    human_judgment: false
  - id: D3
    description: Report signal IDs reach lifecycle history with pending, confirmed, rejected, plan, and outcome display records while review actions remain bounded.
    requirement: ANLY-03
    verification:
      - kind: e2e
        ref: frontend/e2e/phase3-ai-analysis.spec.ts
        status: pass
      - kind: integration
        ref: cd backend && uv run pytest tests/test_analysis_host_integration.py tests/test_analysis_api.py -q
        status: pass
    human_judgment: false
metrics:
  duration: 8m
  completed_date: 2026-07-12
status: complete
---

# Phase 03 Plan 12: Analysis UI Display DTO Summary

The object-local analysis workspace now renders the server's authoritative report, evidence, review, observation-plan, and outcome projections through a reachable report signal ID.

## Performance

- **Duration:** 8m
- **Started:** 2026-07-12T09:54:00+04:00
- **Completed:** 2026-07-12T10:02:00+04:00
- **Tasks:** 3/3
- **Files modified:** 5

## Accomplishments

- Replaced storage-shaped and mock-only TypeScript analysis contracts with the 03-11 display DTO, including server-issued signals, reviews, plans, and outcomes.
- Kept display-to-request subject conversion at the workspace boundary, enabling history only after the authorized report supplies `signal_id`.
- Made report limitations resilient to absent data and rendered pending/confirmed/rejected reviews plus immutable observation plans and appended outcomes.
- Updated browser fixtures to the exact display projection and asserted bounded review requests; the real authenticated backend path also passes.

## Task Commits

1. **Task 1: 对齐 typed client 与后端唯一展示 DTO** - `e19d9fa` (feat)
2. **Task 2: 使报告、证据与生命周期面板消费真实投影** - `b4c31df` (feat)
3. **Task 3: 更新浏览器合同以拒绝旧 mock-only 字段假设** - `fcdae76` (test)
4. **Follow-up: 可选 evidence limitations 语义** - `06b2443` (fix)

## Files Created/Modified

- `frontend/src/lib/api.ts` - Display DTOs, server request subject boundary, lifecycle review/plan/outcome types, and nullable limitation semantics.
- `frontend/src/components/analysis/AnalysisWorkspace.tsx` - Uses typed server subjects and the report-issued signal ID.
- `frontend/src/components/analysis/ReportPanel.tsx` - Handles missing evidence limitations as an empty list.
- `frontend/src/components/analysis/LifecyclePanel.tsx` - Displays the server-owned review, observation-plan, and appended outcome projection.
- `frontend/e2e/phase3-ai-analysis.spec.ts` - Uses the 03-11 DTO fixture and verifies signal reachability plus bounded review actions.

## Decisions Made

- API request subjects are distinct from UI display subjects to retain the existing stock/portfolio UI while forcing only instrument/account request kinds through the client.
- The panel does not calculate lifecycle authority or emit reviewer/provenance/status fields; it reads and mutates only server-issued references.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Made display limitations explicitly optional**
- **Found during:** Task 2
- **Issue:** A partial or legacy display projection without `evidence_limitations` could still reach the report UI despite the server normally returning an array.
- **Fix:** Modeled the field as optional and retained an empty-list rendering fallback.
- **Files modified:** `frontend/src/lib/api.ts`, `frontend/src/components/analysis/ReportPanel.tsx`
- **Verification:** `pnpm run build` and the focused Playwright contract pass.
- **Committed in:** `06b2443`

**Total deviations:** 1 auto-fixed (1 missing critical resilience guard).
**Impact on plan:** The correction preserves the stated nullable/empty contract without adding UI authority, routes, or state.

## Issues Encountered

- The pre-update Playwright fixture failed the portfolio lifecycle scenario because it omitted the real `plans` field. Updating it to the 03-11 projection made the regression pass.
- The authenticated backend integration retains three pre-existing Polars deprecation/sortedness warnings; all 9 selected tests pass.

## Known Stubs

None. All rendered report, evidence, review, plan, and outcome values come from typed server projection fields or explicit empty-state handling.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The Phase 3 frontend contract now has an authenticated backend integration proof and matching Playwright DTO regression.
- Residual risk: browser coverage uses a strict response fixture for visual interaction; production API behavior is independently covered by the authenticated FastAPI host integration test rather than a browser process connected to a live local backend.

## Self-Check: PASSED

- Found `frontend/src/lib/api.ts`, the analysis workspace panels, the browser regression, and `03-12-SUMMARY.md`.
- Found task commits `e19d9fa`, `b4c31df`, `fcdae76`, and follow-up commit `06b2443`.
