---
phase: 05-optional-enhancements
plan: "24"
subsystem: object-safe-analysis-browser
status: complete
tags: [react, tanstack-query, playwright, sse, accessibility, pagination, idempotency]
requires:
  - phase: 05-optional-enhancements
    plan: "20"
    provides: principal-owned Shadow histories and resource-prefix invalidation
  - phase: 05-optional-enhancements
    plan: "21"
    provides: strict bounded Thesis versions, checks, actionable pending, and immutable history pages
  - phase: 05-optional-enhancements
    plan: "23"
    provides: complete 32-path Forecast pages and persisted transition-version SSE
  - phase: 05-optional-enhancements
    plan: "31"
    provides: shared accessible Modal focus and keyboard pattern
provides:
  - canonical instrument/account Analysis cache identity with subject-keyed panel reset boundaries
  - strict object-owned Thesis and Forecast paging, selection, mutation, and invalidation state
  - durable Forecast operation keys, copied-config submission, canonical session comparison, and resumable bounded SSE
  - 375px StockAnalysis wrapping and labelled focus-safe confirmation behavior
  - production browser regressions for rapid switching, non-first pages, strict validation, and SSE flapping
aligns-with: [05-20, 05-21, 05-23, 05-31, SHDW-01, THES-01, FORE-01]
tech-stack:
  added: []
  patterns:
    - canonical server-subject query identity with response ownership checks before render or mutation
    - resource-prefix invalidation beneath an active instrument and immutable record
    - persisted monotonic SSE event cursors with sustained-health reconnect reset
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-24-SUMMARY.md
  modified:
    - frontend/src/pages/StockAnalysis.tsx
    - frontend/src/components/analysis/AnalysisWorkspace.tsx
    - frontend/src/components/analysis/ThesisPanel.tsx
    - frontend/src/components/analysis/ForecastPanel.tsx
    - frontend/src/lib/phase5Api.ts
    - frontend/src/lib/forecastTask.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/e2e/phase5-optional-enhancements.spec.ts
key-decisions:
  - "Analysis cache keys use canonical server kinds instrument/account while UI tabs remain stock/portfolio; response subjects are normalized and checked before becoming render authority."
  - "Forecast submission stores one exact operation tuple and idempotency key across ambiguous transport retries; an explicit new request creates a new tuple, while copied-record config is passed directly."
  - "Forecast SSE uses same-origin fetch streaming so reconnects can send the persisted Last-Event-ID header; short opens preserve the finite failure budget, while a valid durable event or 10-second healthy interval resets it."
patterns-established:
  - "Object cutover: reset drafts, dialogs, selected immutable IDs, pages, paths, jobs, and mutation state at the instrument boundary while restoring tab/scroll state from the object's own storage key."
  - "Strict page consumption: offset/limit/items/total/has_more DTOs remain in query keys and progressive controls; mutation invalidation targets resource roots rather than page zero."
requirements-completed: [SHDW-01, THES-01, FORE-01]
coverage:
  - id: D1
    description: "Rapid stock changes cannot render or mutate the prior stock, while StockAnalysis remains overflow-free and keyboard-safe at 375px."
    requirement: SHDW-01
    verification:
      - kind: automated_ui
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#rapid stock switch keeps Phase 05 object authority local"
        status: pass
      - kind: automated_ui
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#StockAnalysis narrow dialog focus contract"
        status: pass
    human_judgment: false
  - id: D2
    description: "Thesis consumes exact bounded pages, exposes immutable non-first history, and rejects malformed between bounds and non-positive or fractional lookback before confirmation."
    requirement: THES-01
    verification:
      - kind: automated_ui
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#paged Thesis history and strict condition review"
        status: pass
    human_judgment: false
  - id: D3
    description: "Forecast reaches all 32 complete paths, retains idempotency through ambiguous retry, uses copied config directly, and stops resumed SSE flapping within budget."
    requirement: FORE-01
    verification:
      - kind: automated_ui
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#complete path pages and durable retry"
        status: pass
      - kind: automated_ui
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#Forecast SSE persisted resume and flapping budget"
        status: pass
    human_judgment: false
duration: 34m14s
completed: 2026-07-17
---

# Phase 05 Plan 24: Object-Safe Analysis Browser Contracts Summary

**Analysis, Thesis, and Forecast browser authority now follows the active canonical object through strict immutable pages, durable request/SSE identities, and a keyboard-safe 375px stock workspace.**

## Performance

- **Duration:** 34m 14s
- **Started:** 2026-07-17T13:15:13Z
- **Completed:** 2026-07-17T13:49:27Z
- **Tasks:** 2/2
- **Files modified:** 8 implementation/test files plus this summary

## Accomplishments

- Normalized Analysis report/evidence/history keys to `instrument|account`, rejected mismatched response subjects, restored per-object tabs and scroll positions, and remounted optional panels at canonical subject boundaries.
- Cleared or ownership-filtered every Thesis/Forecast immutable ID, draft, dialog, page, path selection, active job, and mutation before it could cross an instrument change.
- Replaced legacy Thesis page parameters and Forecast path compatibility fallbacks with exact `offset/limit/items/total/has_more` DTOs and progressive, accessible non-first-page controls.
- Preserved one Forecast operation key across ambiguous transport loss, passed copied record horizon/catalog directly, and compared strict `CNA-YYYYMMDD` ordinals without `Date.parse`.
- Replaced manually recreated native EventSource connections with same-origin fetch streaming that persists monotonic event IDs, sends `Last-Event-ID`, bounds short-open failures, and invalidates only active resource roots.
- Reused the shared Modal primitive and established tokens for a wrapped 375px StockAnalysis header, 44px controls, visible keyboard delete action, focus trap, Escape, and trigger-focus restoration.

## Task Commits

TDD gates and production outcomes were committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: Object authority and StockAnalysis accessibility | `22dcc90` | Rapid switching retained the prior tab/object and keyboard-focused delete remained invisible |
| GREEN | Task 1: Canonical object state and accessible narrow shell | `a618c74` | Both Task 1 browser contracts, responsive regression, and TypeScript passed |
| RED | Task 2: Strict pages, durable retries, and resumed SSE | `479fd3b` | Retry keys changed, Thesis had no non-first history controls, and SSE flapped 83 times |
| GREEN | Task 2: Exact paging and deterministic Forecast transport | `f5e808d` | All five plan scenarios and all 22 Phase 05 browser scenarios passed |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `frontend/src/components/analysis/AnalysisWorkspace.tsx` — canonical server-subject query namespace, ownership-filtered report data, and object-local tab/scroll reset and restoration.
- `frontend/src/pages/StockAnalysis.tsx` — responsive wrapping controls, keyboard-visible deletion, 44px actions, and shared labelled Modal confirmation.
- `frontend/src/components/analysis/ThesisPanel.tsx` — instrument-owned state, strict condition validation, progressive exact pages, and accessible immutable history table.
- `frontend/src/components/analysis/ForecastPanel.tsx` — instrument/record-owned pages and selections, retained operations, direct copied config, canonical session ordinals, and history loading.
- `frontend/src/lib/phase5Api.ts` — exact generic resource pages, strict Thesis ledgers, and strict complete Forecast path page DTO.
- `frontend/src/lib/forecastTask.ts` — persisted monotonic SSE cursor, `Last-Event-ID` fetch resume, durable-event/healthy reset, finite reconnects, and terminal resource-root invalidation.
- `frontend/src/lib/queryKeys.ts` — instrument-scoped Thesis/Forecast resource roots plus immutable page identities.
- `frontend/e2e/phase5-optional-enhancements.spec.ts` — rapid-switch, 375px focus, complete path, retry, Thesis paging/validation, and SSE flapping acceptance.

## Decisions Made

- Kept UI subject kinds and product labels unchanged, but normalized every Analysis server cache identity to the API/SSE `instrument|account` namespace.
- Treated response ownership as render and mutation admission: IDs become actionable only after their instrument, thesis lineage, version, record, or job matches the active object.
- Kept bounded page continuity only within the same object/resource; object changes never use previous-object placeholder authority.
- Used fetch streaming for Forecast SSE because a newly constructed native `EventSource` cannot set the server-required `Last-Event-ID` header.
- Reset reconnect budget only after an accepted monotonic durable event or a sustained 10-second healthy stream; `open` alone is not health evidence.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Adding the second semantic Thesis history table made one pre-existing browser assertion for a generic `证据` column ambiguous. The assertion was scoped to the evidence-check table, then the affected scenario and the complete 22-scenario suite passed.
- One multi-hunk Forecast edit was rejected because its range restated a keeper outside the changed lines. The file was re-read and the exact smaller edits were applied; no partial tool write occurred.

## Verification

```text
cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "rapid stock switch keeps Phase 05 object authority local|StockAnalysis narrow dialog focus contract|complete path pages and durable retry|paged Thesis history and strict condition review|Forecast SSE persisted resume and flapping budget"
Result: PASS — 5 passed.

cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium
Result: PASS — 22 passed, including the 375px/reduced-motion responsive contract.

cd frontend && pnpm exec tsc --noEmit
Result: PASS — no diagnostics.
```

## Acceptance Criteria

- **PASS — active object authority:** Rapid stock switching immediately restores the new object's tab and removes prior report, Thesis pending/version IDs, Forecast record/path/calibration/job state before delayed reads complete.
- **PASS — canonical invalidation:** Analysis keys use `instrument|account`; Thesis and Forecast mutations/SSE invalidate instrument resource roots and record-local paths/calibration rather than page zero or global caches.
- **PASS — narrow keyboard contract:** At 375px the shell has no horizontal overflow, destructive controls become visible on keyboard focus, and the labelled modal traps focus, handles Escape, and returns focus.
- **PASS — exact immutable pages:** Forecast reaches offsets 0, 12, and 24 for all 32 paths; Thesis versions, checks, actionable pending, and history consume exact bounded page envelopes with accessible progressive controls.
- **PASS — deterministic requests:** Ambiguous retries reuse one UUID; copied records submit their own horizon/catalog directly; strict canonical session ordinals drive stale state.
- **PASS — durable bounded SSE:** Reconnects carry the last accepted durable event ID, a 429 and repeated short opens consume one finite budget, and the stream stops after six total requests without external traffic.

## Threat Mitigation Evidence

- **T-05-24-01 / T-05-24-03:** Canonical keys, subject-keyed remounts, response lineage checks, and the delayed rapid-switch browser scenario prevent stale object rendering and mutation.
- **T-05-24-02:** The operation tuple owns instrument, horizon, catalog, and UUID; transport ambiguity preserves it and copied configuration bypasses scheduled React state.
- **T-05-24-04:** Every ledger/path query is bounded and page-keyed, resource-root invalidation refreshes active non-first pages, and reconnect flapping stops at the declared ceiling.
- **T-05-24-05:** Only numeric monotonic durable IDs for the active job persist; reconnect sends `Last-Event-ID`, duplicate/older IDs are ignored, and terminal handling is idempotent.
- **T-05-24-06:** The existing shared Modal supplies labelled modal semantics, initial focus, trap, Escape, and restoration; 375px browser evidence also proves visible keyboard delete controls.
- No endpoint, schema, database, external network call, strategy/monitor/plan/position authority, broker action, or parallel client store was introduced.

## TDD Gate Compliance

- Task 1 RED `22dcc90` preceded GREEN `a618c74` and failed on observable cross-object tab/data authority plus keyboard-hidden destructive controls.
- Task 2 RED `479fd3b` preceded GREEN `f5e808d` and failed on changed retry UUIDs, missing strict Thesis paging/history controls, and unbounded SSE open/error flapping.
- No refactor-only commit was necessary.

## Known Stubs

None. The scoped scan matched typed empty accumulators, explicit absent values, local draft initialization, and TanStack `placeholderData` limited to same-object page continuity. No placeholder, mock fallback, TODO, FIXME, or empty UI authority can satisfy the delivered contracts.

## User Setup Required

None.

## Next Phase Readiness

- SHDW-01, THES-01, and FORE-01 now have named production-browser evidence for object cutover, strict non-first pages, durable retry, validation, and resumed bounded SSE.
- The browser consumes the repaired Plan 05-21/23 backend contracts without compatibility aliases or a second state store.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched for orchestrator reconciliation.

## Self-Check: PASSED

- All eight scoped implementation/test artifacts and this summary exist in the isolated checkout.
- RED/GREEN commits `22dcc90`, `a618c74`, `479fd3b`, and `f5e808d` resolve as commits in order.
- The literal five-scenario plan command, complete 22-scenario Phase 05 browser suite, and TypeScript check all passed after the final changes.
- No task commit deleted a tracked file; scoped implementation paths are clean.
- Shared tracking files have no diff.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
