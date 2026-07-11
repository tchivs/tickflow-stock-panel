---
phase: 02-factor-and-strategy-research
plan: "08"
subsystem: backtest-research-workspace
tags: [react, typescript, tanstack-query, sse, playwright, accessibility]
requires:
  - phase: 02-04
    provides: server-issued registered-strategy execution handles and immutable retention endpoint
  - phase: 02-05
    provides: research history and completed-only comparison surfaces
  - phase: 02-07
    provides: governed strategy provenance for retained snapshots
provides:
  - trusted strategy research handles retained only in matching SSE task state
  - explicit immutable strategy retention UI with retry-safe server rejection behavior
  - keyboard-accessible Backtest tabs and horizontally scrollable semantic result tables
  - deterministic desktop Chromium coverage for strategy retention, stale rejection, and narrow-table keyboard access
affects: [FACT-03, backtest, research-comparison]
tech-stack:
  added: []
  patterns:
    - retain opaque strategy execution handles only from matching server SSE events
    - gate retention UI on the current completed task and immutable mutation response
    - use focusable overflow wrappers for keyboard horizontal table access
key-files:
  created: []
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/lib/backtestTask.ts
    - frontend/src/pages/Backtest.tsx
    - frontend/src/pages/backtest/StrategyBacktest.tsx
    - frontend/e2e/phase2-research.spec.ts
key-decisions:
  - "The retention mutation accepts only the current task's non-empty server-issued research handle."
  - "A retention failure preserves the completed task for an explicit retry and never promotes a client-side retained state."
  - "Dense result tables retain semantic tables and use their overflow wrapper, not the table itself, as the keyboard scrolling target."
patterns-established:
  - "SSE retention boundary: handle capture, completion, cancellation, malformed payload, and reconnect paths are explicit task-state transitions."
requirements-completed: [FACT-03]
coverage:
  - id: FACT-03-SSE-HANDLE
    description: Strategy SSE research handles survive matching successful completion and are cleared on non-comparable terminal paths.
    requirement: FACT-03
    verification:
      - kind: integration
        ref: pnpm --dir frontend build
        status: pass
    human_judgment: false
  - id: FACT-03-RETENTION
    description: A completed strategy can be retained through the typed endpoint, then shown in history and comparison candidates; stale handles restore an unretained retry state.
    requirement: FACT-03
    verification:
      - kind: e2e
        ref: pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium
        status: pass
    human_judgment: false
  - id: FACT-03-KEYBOARD
    description: Strategy retention and result-table keyboard access are exercised at 1440px, 1024px, and 375px, including a 44px retention target and real keyboard scrolling.
    requirement: FACT-03
    verification:
      - kind: automated_ui
        ref: frontend/e2e/phase2-research.spec.ts#strategy retention keyboard flow keeps an SSE handle scoped at every required viewport
        status: pass
    human_judgment: false
metrics:
  duration: 21m
  completed: 2026-07-11
status: complete
---

# Phase 02 Plan 08: Strategy Retention and Accessible Research Comparison Summary

**Registered-strategy SSE executions now retain a trusted server handle through completion, explicitly create immutable comparison snapshots, and expose accessible research history and side-by-side comparison in Backtest.**

## Performance

- **Duration:** 21m
- **Started:** 2026-07-11T09:39:37Z
- **Completed:** 2026-07-11T10:00:35Z
- **Tasks:** 3/3
- **Files modified:** 5

## Accomplishments

- Captured non-empty server-issued `research` SSE execution handles only on the matching active task, preserving them through valid completion and clearing them on cancellation, errors, malformed results, and reconnect-created tasks.
- Added explicit single-flight strategy retention with immutable experiment metadata, query refreshes, missing-handle guidance, and server-message retry behavior that never promotes stale or already-retained executions.
- Rendered research history and completed-only comparison directly below the strategy workspace; made mode/result tabs and dense result-table overflow wrappers keyboard-operable with visible focus treatment.
- Added deterministic Playwright proof for successful handle-to-retain lifecycle, 409 stale-handle retry behavior, and 1440px/1024px/375px keyboard/geometry/table scrolling checks.

## Task Commits

1. **Task 1: Preserve the trusted SSE research handle in Backtest task state** — `6768476` (`feat`)
2. **Task 2: Add the explicit completed-strategy retention action and existing comparison reachability** — `fe76249` (`feat`)
3. **Task 3: Prove the complete approved responsive and keyboard Scenario 5 in the focused browser suite** — `ad0912b`, `9bb1144` (`test`)
4. **Review remediation: CR-01, CR-02, WR-01–WR-04** — `ef23616` (`fix`)

## Files Created/Modified

- `frontend/src/lib/api.ts` — types the optional server-returned strategy research handle.
- `frontend/src/lib/backtestTask.ts` — owns trusted handle lifecycle across SSE events and terminal transitions.
- `frontend/src/pages/Backtest.tsx` — provides semantic keyboard mode tabs and strategy-mode research surfaces.
- `frontend/src/pages/backtest/StrategyBacktest.tsx` — provides explicit immutable retention state and accessible result tables.
- `frontend/e2e/phase2-research.spec.ts` — covers successful and rejected retention plus responsive keyboard behavior.

## Verification

```text
pnpm --dir frontend build
passed — TypeScript and Vite production build completed in 9.74s

pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium
6 passed in 56.6s
```

## Review Remediation

- CR-01: Runtime structural validation now rejects JSON-valid malformed strategy terminal payloads with `结果解析失败`, clears the task-owned handle, and exposes no retention action.
- CR-02: Retention mutations, pending/error UI, and retained snapshots are task-and-handle scoped; a delayed old-task success still invalidates shared queries but cannot mark a newer result retained.
- WR-01–WR-04: Both dense tables carry active-range sr-only captions; fixtures record and validate the one opaque-handle retention request; 409 rejects prove no promotion or retry; the 1440px/1024px/375px keyboard scenario now covers factor lifecycle/disclosures, strategy retention, comparison, pagination focus, and narrow-table keyboard scrolling.

## Decisions Made

- Retention eligibility requires the exact current completed task, a successful rendered result, and its task-owned opaque server handle; `run_id`, form data, storage, and historical result fields do not grant eligibility.
- Success is represented only by the immutable `ResearchExperiment` returned from the retention endpoint; the displayed backtest result is neither rerun nor mutated.
- Overflow wrappers provide native pointer/touch scrolling and the additional keyboard contract without changing the table's semantics.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed a duplicate query-key import introduced while adding the retention mutation**
- **Found during:** Task 2
- **Issue:** TypeScript reported a duplicate `QK` identifier.
- **Fix:** Consolidated the type-only research experiment import into the existing API import and retained the established query-key import.
- **Files modified:** `frontend/src/pages/backtest/StrategyBacktest.tsx`
- **Verification:** `pnpm --dir frontend build` passed.
- **Committed in:** `fe76249`

**2. [Review remediation] Preserved focus on result-table pagination controls after keyboard page changes**
- **Found during:** CR/WR remediation browser verification.
- **Issue:** A page-control rerender discarded keyboard focus after activation, violating the approved Scenario 5 focus-retention contract.
- **Fix:** Restored focus to the originating pagination control after the state update and reset a focus-entered overflow wrapper to its left edge before real ArrowRight/End navigation.
- **Files modified:** `frontend/src/pages/backtest/StrategyBacktest.tsx`, `frontend/e2e/phase2-research.spec.ts`
- **Verification:** focused build and Playwright commands above passed.
- **Committed in:** `ef23616`

**Total deviations:** 1 auto-fixed (1 Rule 1 bug), 1 review-remediation accessibility correction.
**Impact on plan:** Required correctness and keyboard-contract repairs only; no product scope change.

## Known Stubs

None. No changed plan artifact contains a delivery-blocking placeholder, empty rendering data source, or TODO/FIXME marker.

## Issues Encountered

- Existing factor browser coverage selected the mode as a `button`; mode controls are now semantic tabs, so the focused test was updated to select its `role="tab"` control.

## User Setup Required

None.

## Next Phase Readiness

FACT-03's strategy path is now connected from server-issued SSE evidence through explicit immutable retention into the existing transparent comparison workflow.

## Self-Check: PASSED

Verified the five modified implementation/test artifacts and task commits `6768476`, `fe76249`, `ad0912b`, and `9bb1144` exist.

---
*Phase: 02-factor-and-strategy-research*
*Completed: 2026-07-11*
