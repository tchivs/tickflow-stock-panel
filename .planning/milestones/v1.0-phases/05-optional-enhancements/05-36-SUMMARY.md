---
phase: 05-optional-enhancements
plan: 36
subsystem: thesis
tags: [thesis, ledger, pagination, dto-identity, playwright, wr-03]

requires:
  - phase: 05-21
    provides: repository-owned Thesis page predicates/count/order/limit
  - phase: 05-32
    provides: governed scanner/readiness output for Thesis lifecycle
  - phase: 05-35
    provides: phase5Api/ForecastPanel recent API surface shared with Thesis DTOs
provides:
  - Self-identifying check/history page DTOs with instrument, thesis_id, version_id, numeric version, and safe version display timestamp/state
  - ThesisPanel ledger rendering independent of loaded version pages
  - WR-03 Playwright evidence that old history renders before version 1 pagination
affects: [05-29, thesis-ui, phase5-browser-gate]

tech-stack:
  added: []
  patterns:
    - "Row-owned ledger identity: server joins instrument/version display fields; browser admits rows by item.instrument === active stock"
    - "versionById is enrichment-only; never admission for checks/history"

key-files:
  created: []
  modified:
    - backend/app/theses/repository.py
    - backend/app/theses/projections.py
    - backend/tests/theses/test_api.py
    - frontend/src/lib/phase5Api.ts
    - frontend/src/components/analysis/ThesisPanel.tsx
    - frontend/e2e/phase5-optional-enhancements.spec.ts

key-decisions:
  - "Checks/history SQL pages join theses + thesis_versions to project instrument, thesis_id, numeric version, version_created_at, and version_official_state under the same instrument predicate/count/order/limit"
  - "Public projections allowlist display identity only; reviewer principal, raw evidence paths, and lease internals remain withheld"
  - "Frontend removes versionById.has(...) as ledger admission and renders rows from row-owned identity; optional GET /versions/{id} enriches detail without dropping ledger rows"

patterns-established:
  - "Independent Thesis pagination: ledger pages must self-identify; version pages cannot gate immutable history visibility"
  - "Foreign-instrument ledger rows are rejected locally with a visible incomplete/error state, never rendered under the active stock"

requirements-completed: [THES-01]

coverage:
  - id: D1
    description: "Check/history page rows carry deny-by-default instrument, thesis ID, and safe version display identity without requiring a versions page"
    requirement: THES-01
    verification:
      - kind: unit
        ref: "backend/tests/theses/test_api.py#test_ledger_row_identity_present_without_versions_page"
        status: pass
      - kind: unit
        ref: "backend/tests/theses/test_api.py#test_old_version_ledger_rows_remain_authorized_after_revision"
        status: pass
      - kind: unit
        ref: "backend/tests/theses/test_api.py#test_ownership_before_pagination_rejects_foreign_instrument_on_repository_pages"
        status: pass
    human_judgment: false
  - id: D2
    description: "Thesis UI renders authorized check/history rows before the corresponding version page is loaded; no silent drop/duplicate after loading version 1"
    requirement: THES-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#WR-03 paged Thesis history renders before version page"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#paged Thesis history and strict condition review"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-22
status: complete
---

# Phase 05 Plan 36: Thesis Ledger Self-Identifying Rows Summary

**WR-03 closed: check/history pages self-identify with instrument/thesis/version display fields so immutable ledger rows render without waiting on version pagination**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-22T18:21:55Z
- **Completed:** 2026-07-22T18:47:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Backend check/history (and actionable pending) SQL pages join persisted instrument + version display identity under the same ownership predicate, count, order, and limit.
- Public projections allowlist only safe display identity fields; principals and raw authority internals stay out of page DTOs.
- Frontend typed DTOs require row-owned identity; `versionById.has(...)` is no longer a ledger admission gate.
- Playwright primary title `WR-03 paged Thesis history renders before version page` proves old check/history visibility before version 1 loads, then stable dedupe after pagination.

## Task Commits

1. **Task 1: Return one old-version ledger row with its own safe persisted identity** - `c58da49` (feat)
2. **Task 2: Render checks and history independently of loaded version pages** - `6a69fbb` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/app/theses/repository.py` - Join instrument/thesis/version display identity into checks/pending/history pages; project via `_row_display_identity`
- `backend/app/theses/projections.py` - Allowlist identity on public check/pending DTOs via `_display_identity`
- `backend/tests/theses/test_api.py` - Repository-backed API tests for ledger identity without versions page, old-version stability, foreign ownership 404
- `frontend/src/lib/phase5Api.ts` - ThesisCheck/ThesisPending require instrument, thesis_id, version, version_created_at, version_official_state
- `frontend/src/components/analysis/ThesisPanel.tsx` - Instrument-matched ledger render; optional version detail fetch; foreign rejection visible
- `frontend/e2e/phase5-optional-enhancements.spec.ts` - WR-03 primary title + fixtures with row identity; existing paged history review retained

## Decisions Made

- Page joins select `version_official_state` from confirmed review existence (same semantics as repository `_official_state`) rather than inventing a new column.
- Pending review still uses row instrument/status identity when version detail is not yet cached; cache mismatch still hard-fails.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Propagated identity through actionable pending page as well**
- **Found during:** Task 1 (repository identity joins)
- **Issue:** Plan focused on checks/history, but pending projection also lacked instrument/version display identity and shares `projections.pending`.
- **Fix:** Extended `page_actionable_pending_for_instrument` with the same display identity joins so pending rows are consistent with history.
- **Files modified:** `backend/app/theses/repository.py`
- **Verification:** Backend identity selector suite passed (4 tests)
- **Committed in:** `c58da49`

**2. [Rule 3 - Blocking] Playwright webServer uses `pnpm` which is absent; ran via local Vite + PHASE1_BASE_URL**
- **Found during:** Task 2 verification
- **Issue:** `pnpm` not on PATH; config `webServer.command` fails with exit 127.
- **Fix:** Started `node_modules/.bin/vite --host 127.0.0.1 --port 4173` and ran Playwright with `PHASE1_BASE_URL=http://127.0.0.1:4173` (reuseExistingServer path).
- **Files modified:** none (runtime only)
- **Verification:** 2/2 desktop-chromium tests matching `paged Thesis history` passed
- **Committed in:** n/a (verification environment)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking verification env)
**Impact on plan:** No scope creep; WR-03 contract delivered as specified.

## Issues Encountered

- Host lacks `pnpm`; Playwright verification used direct Vite + PHASE1_BASE_URL instead of the documented `pnpm exec` webServer command.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- WR-03 closed for THES-01 warning path; final phase gate 05-29 can include the named WR-03 Playwright node.
- Do not touch 05-26/05-27 supply chain from this plan.

## Verification Evidence

```text
cd backend && python3 -m pytest tests/theses/test_api.py -k "ledger_row_identity or old_version or ownership_before_pagination" -x
# 4 passed, 4 deselected

cd frontend && ATHENA_ALLOW_NETWORK=0 PHASE1_BASE_URL=http://127.0.0.1:4173 \
  ./node_modules/.bin/playwright test e2e/phase5-optional-enhancements.spec.ts \
  --project=desktop-chromium --grep "paged Thesis history"
# 2 passed
```

Exact WR-03 title appears once:

`WR-03 paged Thesis history renders before version page`

## Self-Check: PASSED

- `backend/app/theses/repository.py` FOUND
- `backend/app/theses/projections.py` FOUND
- `backend/tests/theses/test_api.py` FOUND
- `frontend/src/lib/phase5Api.ts` FOUND
- `frontend/src/components/analysis/ThesisPanel.tsx` FOUND
- `frontend/e2e/phase5-optional-enhancements.spec.ts` FOUND
- commits `c58da49`, `6a69fbb` present on `gsd/v1.0-milestone`
- no `versionById.has` admission remaining in ThesisPanel

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-22*
