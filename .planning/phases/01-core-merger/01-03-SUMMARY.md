---
phase: 01-core-merger
plan: 03
subsystem: database
tags: [sqlite, fastapi, portfolio, quote-projection]
requires:
  - phase: 01-13
    provides: Deterministic portfolio persistence and valuation contracts
provides:
  - Versioned SQLite operational records for archive-safe accounts and positions
  - Quote-projected portfolio valuation with governed-close fallback metadata
  - Authenticated Portfolio CRUD, summary, and holdings endpoints in the single host app
affects: [01-05, 01-12, portfolio-frontend]
tech-stack:
  added: []
  patterns:
    - Short-lived SQLite connections enable foreign keys and use parameterized transactions.
    - Portfolio values are projected from shared quotes or governed closes and never copied into SQLite.
key-files:
  created:
    - backend/app/operational/migrations.py
    - backend/app/operational/repository.py
    - backend/app/portfolio/service.py
    - backend/app/api/portfolio.py
  modified:
    - backend/app/main.py
    - backend/tests/test_portfolio_api.py
key-decisions:
  - "Archive keeps stable account and position identifiers when operational history prevents deletion."
  - "An unavailable quote or governed close yields unavailable P&L rather than a zero valuation."
patterns-established:
  - "OperationalRepository is the SQLite boundary for durable portfolio state; time-series data stays in the governed lake."
  - "PortfolioService owns quote freshness, close fallback, and P&L projection before API serialization."
requirements-completed: [CORE-03]
coverage:
  - id: D1
    description: Archive-safe multi-account SQLite persistence with uniqueness and deletion guards.
    requirement: CORE-03
    verification:
      - kind: integration
        ref: uv run --directory backend pytest tests/test_portfolio_api.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: Authenticated portfolio API exposes quote-projected aggregate and per-account valuations with source and as_of metadata.
    requirement: CORE-03
    verification:
      - kind: integration
        ref: backend/tests/test_portfolio_api.py#test_portfolio_api_returns_quote_projected_positions_and_archive_guards
        status: pass
    human_judgment: false
duration: 2 min
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 03: SQLite Portfolio and Quote Projection Summary

**Multi-account operational persistence and archive-safe Portfolio APIs now project current P&L from shared quotes or governed closes.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-07-11T02:09:55Z
- **Completed:** 2026-07-11T02:12:34Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Added versioned `operational.db` migrations with foreign-key enforcement, parameterized account/position CRUD, uniqueness, validation, archival, and history-aware deletion guards.
- Added quote-projected P&L calculation with explicit `source`, `as_of`, and freshness metadata, governed-close fallback, and unavailable valuation semantics.
- Registered authenticated `/api/portfolio` account, position, summary, and holdings routes through the existing FastAPI lifespan.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement versioned operational SQLite persistence** - `78f56b3` (feat)
2. **Task 2: Implement quote-projected Portfolio service and API** - `f5ff2f1` (feat)

**Plan metadata:** Pending this commit.

## Files Created/Modified

- `backend/app/operational/migrations.py` - Versioned schema for accounts, positions, and operational references.
- `backend/app/operational/repository.py` - Parameterized SQLite repository with validation and archive/delete transitions.
- `backend/app/portfolio/service.py` - Shared-quote and governed-close valuation projection.
- `backend/app/api/portfolio.py` - Validated Portfolio CRUD, summary, and valuation endpoints.
- `backend/app/main.py` - Lifespan migration/state wiring and router registration.
- `backend/tests/test_portfolio_api.py` - Persistence, valuation, archive, API, and host-registration contracts.

## Decisions Made

- Operational state is isolated in `DATA_DIR/operational.db`; market series remain governed Parquet/DuckDB data.
- Position and account deletions are limited to empty, unreferenced records; archival preserves historical identifiers and links.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 05 can attach position-scoped monitor associations to the operational repository without changing Portfolio persistence semantics.
- Portfolio frontend work can consume the authenticated account, positions, and summary endpoints with explicit valuation freshness metadata.

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
