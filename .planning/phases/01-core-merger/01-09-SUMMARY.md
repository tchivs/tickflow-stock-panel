---
phase: 01-core-merger
plan: "09"
subsystem: frontend
tags: [react, typescript, react-query, portfolio, responsive-ui]
requires:
  - phase: 01-08
    provides: Typed Portfolio client, account-aware query keys, shared SSE invalidation, and Portfolio navigation entry
provides:
  - Aggregate-first Portfolio workspace at /portfolio
  - Accessible account and holding mutation dialogs with archive confirmation
  - Responsive desktop/tablet holdings table and mobile holding cards
  - Durable account and holding notes in the operational Portfolio contract
affects: [portfolio-frontend, monitor-frontend, compose-acceptance]
tech-stack:
  added: []
  patterns:
    - Portfolio mutations invalidate shared account, summary, and holding query families while keeping page selection local.
    - Portfolio uses semantic table columns from md upward and equivalent holding cards below md.
    - Form notes cross the typed client, Pydantic API boundary, versioned SQLite migration, and repository reads/writes.
key-files:
  created:
    - frontend/src/pages/Portfolio.tsx
    - frontend/src/components/portfolio/AccountDialog.tsx
    - frontend/src/components/portfolio/HoldingDialog.tsx
    - frontend/src/components/portfolio/HoldingsTable.tsx
    - frontend/src/components/portfolio/HoldingCard.tsx
  modified:
    - frontend/src/router.tsx
    - frontend/src/lib/api.ts
    - backend/app/api/portfolio.py
    - backend/app/operational/migrations.py
    - backend/app/operational/repository.py
    - backend/tests/test_portfolio_api.py
key-decisions:
  - "Portfolio derives its visible aggregate freshness from the least-fresh summary position and never labels governed-close or unavailable data as live."
  - "Archive affordances open the existing holding/account dialogs, whose nested shared-modal confirmation preserves focus on the safe return action."
  - "Notes were added to the existing operational contract instead of silently dropping dialog input."
patterns-established:
  - "Use the existing Modal primitive for full page-level mutation dialogs and destructive confirmations."
  - "Map account names and position-scoped enabled monitor rules locally from cached queries; no Portfolio EventSource is created."
requirements-completed: [CORE-03, CORE-05]
coverage:
  - id: D1
    description: Portfolio is a lazy first-class route with aggregate-first totals, account controls, loading, empty, error, and freshness states.
    requirement: CORE-03
    verification:
      - kind: other
        ref: pnpm --dir frontend build
        status: pass
    human_judgment: true
    rationale: "The build validates route and component integration; Plan 11 owns fixture-driven desktop and mobile browser verification."
  - id: D2
    description: Account and holding dialogs validate mutable values, preserve durable notes, and archive records with explicit confirmation.
    requirement: CORE-03
    verification:
      - kind: integration
        ref: uv run --directory backend pytest tests/test_portfolio_api.py -q
        status: pass
      - kind: other
        ref: pnpm --dir frontend build
        status: pass
    human_judgment: true
    rationale: "Focus restoration, combobox keyboard navigation, and visible form affordances require browser verification."
  - id: D3
    description: Holdings retain semantic desktop/tablet table access and mobile card access without a manual presentation switcher.
    requirement: CORE-05
    verification:
      - kind: other
        ref: pnpm --dir frontend build
        status: pass
    human_judgment: true
    rationale: "Breakpoint behavior and 320px overflow are validated by the later browser workflow."
---

# Phase 01 Plan 09: Portfolio Workspace Summary

**Portfolio is now a responsive first-class workspace with aggregate valuations, account-aware holdings maintenance, and source-aware freshness labels.**

## Performance

- **Duration:** Not recorded
- **Completed:** 2026-07-11
- **Tasks:** 3/3
- **Files modified:** 11

## Accomplishments

- Added page-level accessible Account and Holding dialogs with domain validation, instrument combobox keyboard support, focus-first error behavior, sticky actions, explicit archive confirmation, React Query invalidation, and durable notes.
- Added responsive holdings presentation: sticky semantic tables with desktop/compact columns at 768px and above, plus no-overflow mobile cards below 768px with equivalent value, alert, and action access.
- Added the lazy `/portfolio` route and aggregate-first workspace with account filtering, freshness derivation, retained background data, skeletons, recovery copy, account controls, and Monitor handoff links.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create accessible account and holding mutation dialogs** — `d81f887` (feat)
2. **Task 2: Build responsive desktop/tablet holdings tables and mobile holding cards** — `1dc4eaf` (feat)
3. **Task 3: Compose aggregate-first Portfolio page and register its route** — `b5a1580` (feat)
4. **Required Rule 2 contract fix: Persist account and holding notes** — `07c967f` (fix)
5. **Typed client correction for account notes** — `c9b4de5` (fix)

## Files Created/Modified

- `frontend/src/pages/Portfolio.tsx` — Aggregate-first Portfolio page and query-driven state handling.
- `frontend/src/components/portfolio/AccountDialog.tsx` — Shared-Modal account mutation and archive flow.
- `frontend/src/components/portfolio/HoldingDialog.tsx` — Shared-Modal holding mutation, instrument combobox, and archive flow.
- `frontend/src/components/portfolio/HoldingsTable.tsx` — Responsive semantic desktop/tablet holdings table.
- `frontend/src/components/portfolio/HoldingCard.tsx` — Compact mobile holdings display.
- `frontend/src/router.tsx` — Lazy named Portfolio route registration.
- `frontend/src/lib/api.ts` — Portfolio notes request and response contract.
- `backend/app/{api/portfolio.py,operational/migrations.py,operational/repository.py}` — Durable notes API and SQLite persistence.
- `backend/tests/test_portfolio_api.py` — Notes round-trip regression coverage.

## Decisions Made

- Used the summary position data already returned by the Portfolio API to calculate the least-fresh visible valuation label, without adding a second market feed or stream.
- Route monitor controls to `/monitor?position_id=<id>` so Portfolio remains a management surface rather than a second alert center.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Portfolio note input lacked an end-to-end persistence contract**
- **Found during:** Task 1 (Create accessible account and holding mutation dialogs)
- **Issue:** The completed Portfolio API client, Pydantic models, SQLite tables, and repository did not model account or holding notes, so the required dialog field would have been silently discarded.
- **Fix:** Added a versioned SQLite migration, repository validation and read/write support, Pydantic request fields, typed frontend contracts, and a focused notes round-trip test.
- **Files modified:** `frontend/src/lib/api.ts`, `frontend/src/components/portfolio/AccountDialog.tsx`, `frontend/src/components/portfolio/HoldingDialog.tsx`, `backend/app/api/portfolio.py`, `backend/app/operational/migrations.py`, `backend/app/operational/repository.py`, `backend/tests/test_portfolio_api.py`
- **Verification:** `uv run --directory backend pytest tests/test_portfolio_api.py -q` — 7 passed; `pnpm --dir frontend build` — passed.
- **Committed in:** `07c967f`, `c9b4de5`

---

**Total deviations:** 1 auto-fixed (1 missing critical contract).
**Impact on plan:** The minimal persisted notes contract fulfills the required dialog field without introducing a new service or data boundary.

## Issues Encountered

- The first dialog build identified an unused import; it was removed before Task 1's passing build.

## Verification

- **PASS** — `pnpm --dir frontend build` completed TypeScript checking and Vite production build successfully.
- **PASS** — `uv run --directory backend pytest tests/test_portfolio_api.py -q` completed with 7 passing Portfolio API tests.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 10 can link Monitor's position-rule editor to Portfolio holdings through the existing `/monitor?position_id=` handoff.
- Plan 11 can exercise Portfolio desktop/mobile layouts and dialogs against its isolated fixture deployment.

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
