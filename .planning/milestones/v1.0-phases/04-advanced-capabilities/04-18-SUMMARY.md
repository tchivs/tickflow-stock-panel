---
phase: 04-advanced-capabilities
plan: "18"
subsystem: advanced-research-ui
tags: [react, tanstack-query, playwright, immutable-research, sandbox]
requires:
  - phase: 04-15
    provides: authorized terminal sandbox-run DTOs
  - phase: 04-16
    provides: scoped immutable viewpoint mutation and evaluation APIs
  - phase: 04-17
    provides: frozen experiment scopes and five server-owned evolution gates
provides:
  - immutable viewpoint revision, correction, and server-projected evaluation controls
  - frozen experiment scope, completed-run candidate, and independent gate review workflow
  - redacted terminal sandbox-run review in the Backtest workspace
affects: [ADV-01, ADV-02, ADV-03, SAFE-02, advanced-research]
tech-stack:
  added: []
  patterns:
    - typed advanced client actions use bounded server-owned identifiers and resource-scoped query keys
    - terminal sandbox UI renders only allowlisted projection fields
key-files:
  created: []
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/components/advanced/ViewpointPanel.tsx
    - frontend/src/components/advanced/AdvancedResearchPanels.tsx
    - frontend/e2e/phase4-advanced-capabilities.spec.ts
key-decisions:
  - "Viewpoint mutations invalidate only the active subject's viewpoint version and calibration keys."
  - "Experiment and evolution controls submit bounded scope/configuration while gate verdicts and sandbox details remain server-projected."
patterns-established:
  - "Governed UI actions: append immutable records through typed methods without browser-provided authority."
requirements-completed: [ADV-01, ADV-02, ADV-03, SAFE-02]
coverage:
  - id: D1
    description: Analysis workspaces append bounded immutable viewpoint revisions or corrections and display only server-projected evaluation facts.
    requirement: ADV-01
    verification:
      - kind: e2e
        ref: frontend/e2e/phase4-advanced-capabilities.spec.ts#scenario 1b
        status: pass
    human_judgment: false
  - id: D2
    description: Backtest workspaces collect frozen strategy scope, retain completed-run feedback, and use five independent server-owned promotion gates.
    requirement: ADV-02
    verification:
      - kind: e2e
        ref: frontend/e2e/phase4-advanced-capabilities.spec.ts#scenario 3b
        status: pass
    human_judgment: false
  - id: D3
    description: Terminal sandbox records display only safe status, reason, proof fingerprint, resource summary, timestamp, and audit disclosure.
    requirement: SAFE-02
    verification:
      - kind: integration
        ref: cd backend && timeout 75s uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py tests/advanced/test_evolution.py tests/advanced/test_sandbox.py -q
        status: pass
    human_judgment: false
metrics:
  duration: 12m
  completed: 2026-07-13
status: complete
---

# Phase 04 Plan 18: Advanced Research Workspace Summary

**Existing Analysis and Backtest workspaces now expose immutable viewpoint evaluation, frozen experiment evolution, and redacted terminal sandbox review through typed server contracts.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-13T03:53:18Z
- **Completed:** 2026-07-13T04:05:01Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Added typed, bounded viewpoint revision, correction, and empty-body evaluation actions with subject-local cache invalidation and accessible immutable controls.
- Added complete frozen strategy scope inputs, completed-run candidate creation, five independent evidence gate actions, and explicit research-only promotion review.
- Added terminal sandbox-run list rendering that discloses only safe allowlisted fields and browser contracts that assert sensitive execution data stays absent.

## Task Commits

1. **Task 1: 扩展 typed client 与 ViewpointPanel 的不可变 revision/evaluation 工作流** - `acc42b9` (test RED), `d2e99b4` (feat GREEN)
2. **Task 2: 完成 Backtest experiment、evolution 和 terminal sandbox-run 审阅** - `a3c2a9b` (test RED), `bba73c7` (feat GREEN)

## Verification

```text
cd frontend && timeout 60s pnpm exec tsc -b --pretty false
passed

cd frontend && timeout 90s pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium
9 passed

cd backend && timeout 75s uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py tests/advanced/test_evolution.py tests/advanced/test_sandbox.py -q
71 passed in 24.73s
```

## Files Created/Modified

- `frontend/src/lib/api.ts` - Typed advanced revision, frozen experiment, gate, and safe sandbox-run contracts.
- `frontend/src/lib/queryKeys.ts` - Subject/resource-scoped viewpoint, experiment, candidate, and sandbox cache keys.
- `frontend/src/components/advanced/ViewpointPanel.tsx` - Immutable revision/correction forms and server-evaluation controls in the existing Analysis workspace.
- `frontend/src/components/advanced/AdvancedResearchPanels.tsx` - Frozen strategy scope, candidate/gate workflow, and terminal sandbox review in Backtest.
- `frontend/e2e/phase4-advanced-capabilities.spec.ts` - Browser contracts for immutable actions, bounded workflow state, and disclosure boundaries.

## Decisions Made

- Cache invalidation remains resource-scoped to the active authorized subject, viewpoint, calibration profile, research asset, candidate, or sandbox run.
- The client never computes evaluation values, submits gate verdicts, or renders raw sandbox source, paths, environment values, or diagnostics.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test isolation] Scoped legacy browser locators after adding completed-run and pending-candidate fixtures**
- **Found during:** Task 2 verification
- **Issue:** Existing global Playwright locators became ambiguous once the contract fixture correctly represented both failed/completed runs and passed/pending candidates.
- **Fix:** Scoped assertions to their corresponding run or candidate article.
- **Files modified:** `frontend/e2e/phase4-advanced-capabilities.spec.ts`
- **Verification:** All nine Phase 4 browser scenarios pass.
- **Committed in:** `bba73c7`

---

**Total deviations:** 1 auto-fixed (1 Rule 1 test isolation).
**Impact on plan:** The fixture now represents the required multi-record workflow without weakening prior assertions.

## Issues Encountered

None.

## Known Stubs

None. `placeholderData` in the viewpoint panel is TanStack Query's retained-data option, not a rendered placeholder or disconnected data source.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The existing workspaces can now consume the production advanced API without exposing client authority or sandbox internals. Plan 04-19 can proceed with the remaining phase work.

## Self-Check: PASSED

Verified all five modified source/test artifacts and task commits `acc42b9`, `d2e99b4`, `a3c2a9b`, and `bba73c7` exist.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-13*
