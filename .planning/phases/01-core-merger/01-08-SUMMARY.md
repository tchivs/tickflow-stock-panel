---
phase: 01-core-merger
plan: "08"
subsystem: frontend
tags: [react, typescript, react-query, sse, responsive-navigation]
requires:
  - phase: 01-03
    provides: Portfolio account, holding, and quote-projected valuation APIs
  - phase: 01-04
    provides: Persisted deterministic decision playbook APIs
  - phase: 01-05
    provides: Holding-aware Monitor event contracts
  - phase: 01-12
    provides: Shared portfolio_updated SSE events and durable delivery outcomes
provides:
  - Typed existing-client operations for Portfolio, alert delivery, and decision playbooks
  - Stable Portfolio, delivery-detail, and decision React Query keys
  - Account-scoped root SSE invalidation for shared Portfolio data
  - One accessible responsive workspace navigation shell ready for Portfolio
affects: [portfolio-frontend, monitor-frontend, dashboard-decision-inspector, compose-acceptance]
tech-stack:
  added: []
  patterns:
    - Keep operational API calls on the existing request helper and all client streaming in Layout's existing useQuoteStream invocation.
    - Scope portfolio stream invalidation to affected account cache entries plus the aggregate query.
    - Reuse the desktop workspace sidebar as the mobile focus-trapped drawer rather than creating another application shell.
key-files:
  created:
    - .planning/phases/01-core-merger/01-08-SUMMARY.md
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/lib/useQuoteStream.ts
    - frontend/src/components/Layout.tsx
key-decisions:
  - "Portfolio query keys preserve account identity so SSE events refetch only affected account views and the aggregate view."
  - "The existing Layout sidebar becomes the accessible mobile drawer; it remains the sole navigation model and sole root stream owner."
patterns-established:
  - "Operational frontend client methods use request<T> and encode every path identifier."
  - "portfolio_updated is handled only by useQuoteStream; Portfolio pages and dialogs do not open EventSource connections."
requirements-completed: [CORE-03, CORE-04, CORE-05, PLAN-01, PLAN-02]
coverage:
  - id: D1
    description: Typed existing-client operations and stable React Query keys cover Portfolio accounts/holdings/summary, delivery detail/history, and deterministic decision/replay contracts.
    requirement: CORE-03
    verification:
      - kind: other
        ref: pnpm --dir frontend build
        status: pass
    human_judgment: true
    rationale: "The build proves TypeScript integration; Plan 11's fixture-controlled browser workflow exercises the operational screens end to end."
  - id: D2
    description: The existing root EventSource refreshes Portfolio valuation queries for quotes_updated and account-scoped portfolio_updated events.
    requirement: CORE-05
    verification:
      - kind: other
        ref: pnpm --dir frontend build
        status: pass
    human_judgment: true
    rationale: "The build proves the shared hook compiles; fixture SSE behavior is exercised by the later Compose acceptance workflow."
  - id: D3
    description: The shared desktop workspace navigation is available through a focus-trapped, Escape/backdrop-close mobile drawer with focus return.
    requirement: CORE-03
    verification:
      - kind: other
        ref: pnpm --dir frontend build
        status: pass
    human_judgment: true
    rationale: "Keyboard and viewport behavior require the later desktop/mobile browser workflow."
duration: not recorded
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 08: Operational Frontend Foundation Summary

**The existing frontend now has typed Portfolio, Monitor-delivery, and decision contracts, account-aware shared SSE refreshes, and one responsive workspace shell.**

## Performance

- **Duration:** Not recorded
- **Completed:** 2026-07-11T02:56:22Z
- **Tasks:** 3/3
- **Files modified:** 4

## Accomplishments

- Extended the established request client with typed Portfolio CRUD/valuation, monitor delivery/history, deterministic playbook, audit, and historical replay operations; all path identifiers are encoded.
- Added stable account-aware Portfolio, delivery-detail, and decision query-key factories, and extended the sole root EventSource hook to invalidate aggregate and affected account valuation data.
- Kept the existing workspace shell, stream status, and toast hosts intact while making its navigation an accessible mobile drawer and adding the Portfolio navigation definition.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add typed operational API methods and query keys** — `b428049` (feat)
2. **Task 2: Extend the existing root SSE hook for Portfolio invalidation** — `7bc28a7` (feat)
3. **Task 3: Make the shared workspace shell mobile-operable** — `01703ee` (feat)

## Files Created/Modified

- `frontend/src/lib/api.ts` — Typed operational request/response contracts and existing-client methods.
- `frontend/src/lib/queryKeys.ts` — Stable Portfolio, delivery, and decision query factories plus valuation invalidation prefixes.
- `frontend/src/lib/useQuoteStream.ts` — Account-scoped `portfolio_updated` handling within the existing EventSource.
- `frontend/src/components/Layout.tsx` — Portfolio-ready shared navigation and a keyboard-safe responsive drawer.

## Decisions Made

- Kept the legacy Monitor channel array broad enough for the existing editor while the typed delivery outcome contract exposes only the supported Feishu and Telegram outcomes.
- Query invalidation refreshes the aggregate Portfolio cache and only the account caches reported by the server, preserving selected-account state and unrelated cached views.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Narrowing the pre-existing Monitor editor's legacy channel type initially caused a TypeScript build error. Restoring its compatibility type while keeping the new delivery-outcome contract precise resolved it; the final build passed.

## Verification

- **PASS** — `pnpm --dir frontend build` completed TypeScript checking and Vite production build successfully.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 09 can register and implement the Portfolio page against the typed client, stable cache keys, shared SSE refresh, and prepared navigation item.
- Plan 10 can consume typed delivery detail/history and decision playbook/replay operations in the existing Monitor and Dashboard surfaces.
- Plan 11 can validate the declared desktop/mobile workflows through isolated fixtures.

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
