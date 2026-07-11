---
phase: 01-core-merger
plan: "02"
subsystem: data-governance
tags: [pytest, polars, duckdb, parquet, fixture-provider]

requires:
  - phase: 01-core-merger
    provides: "Offline fixture-sync and governed-data validation test contracts from Plan 01"
provides:
  - "Read-only two-file FixtureProvider for deterministic offline governed-market synchronization"
  - "Typed market-data contracts and deterministic Parquet contract validation"
  - "Daily-pipeline fixture seam that writes through Parquet, DuckDB views, and Polars enrichment"
affects: [compose-acceptance, governed-data, daily-pipeline]

tech-stack:
  added: []
  patterns:
    - "Fixture mode is enabled only with PHASE1_FIXTURE_MODE=1 and a read-only PHASE1_FIXTURE_DIR."
    - "Market-data validation checks governed Parquet partitions without creating a SQLite time-series mirror."

key-files:
  created:
    - backend/app/contracts/__init__.py
    - backend/app/contracts/market_data.py
    - backend/app/contracts/validator.py
    - backend/app/data_providers/fixture_provider.py
  modified:
    - backend/app/jobs/daily_pipeline.py
    - backend/tests/test_phase1_fixture_sync.py

key-decisions:
  - "Fixture acceptance requires exactly instruments.json and market-data.json in a read-only directory."
  - "Fixture synchronization reuses the existing DataStore, KlineRepository, DuckDB view refresh, and Polars enrichment path."
  - "Contract violations use deterministic D-17 category labels for primary-key, market-time, repair-window, and schema-drift failures."

patterns-established:
  - "Test-only providers must not construct a live TickFlow client or use a network path."
  - "Governed dataset schemas are validated from the actual partitioned Parquet files before fixture acceptance completes."

requirements-completed: [CORE-01, CORE-02]

coverage:
  - id: D1
    description: "Offline fixture provider writes instruments, daily bars, adjustment factors, financial metrics, and enriched bars through the governed lake."
    requirement: CORE-01
    verification:
      - kind: integration
        ref: "uv run --directory backend --extra dev pytest tests/test_phase1_fixture_sync.py -q"
        status: pass
    human_judgment: false
  - id: D2
    description: "Parquet contract validator rejects duplicate keys, invalid market times, invalid repair windows, and incompatible schemas."
    requirement: CORE-02
    verification:
      - kind: unit
        ref: "uv run --directory backend --extra dev pytest tests/test_data_contracts.py -q"
        status: pass
    human_judgment: false

# Metrics
duration: not measured
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 02: Governed fixture synchronization and contract validation Summary

**Deterministic read-only fixtures now enter Tickflow exclusively through the governed Parquet, DuckDB, and Polars pipeline, with D-17 validation at completion.**

## Performance

- **Duration:** Not measured
- **Started:** Not recorded
- **Completed:** 2026-07-11T02:05:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Added a typed, read-only two-file fixture bundle and `FixtureProvider` behind the explicit `PHASE1_FIXTURE_MODE=1` boundary.
- Added `run_phase1_fixture_sync`, which persists fixture instruments, daily bars, adjustment factors, financial metrics, and enriched output through existing governed storage and view-refresh paths.
- Added deterministic Parquet validation for primary-key, Asia/Shanghai market-time, repair-window, and schema-drift violations.

## Task Commits

Each task was committed atomically:

1. **Task 1: Make governed fixture synchronization tests pass** - `93feb9b` (feat)
2. **Task 2: Make market-data contract validation tests pass** - `7b0416f` (feat)

**Plan metadata:** committed with this summary

## Files Created/Modified
- `backend/app/contracts/market_data.py` - Strict fixture models and governed dataset contracts.
- `backend/app/contracts/validator.py` - Deterministic D-17 Parquet contract validator.
- `backend/app/data_providers/fixture_provider.py` - Offline fixture-only provider with no live-client dependency.
- `backend/app/jobs/daily_pipeline.py` - Explicit fixture-mode synchronization seam and completion validation.
- `backend/tests/test_phase1_fixture_sync.py` - Compose-shaped, read-only fixture bundle test coverage.

## Decisions Made
- Fixture input uses exactly `instruments.json` and `market-data.json`, matching the planned Compose mount contract.
- Fixture adjustment factors are normalized from input `adj_factor` to the existing lake `ex_factor` storage contract before enrichment.
- No market data is copied to SQLite; validation inspects only governed Parquet partitions.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The initial focused test invocation could not spawn `pytest` because the development extra was absent. Re-running the same focused tests with `--extra dev` and the public PyPI index completed successfully.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The planned Compose acceptance workflow can mount the typed two-file fixture bundle at `PHASE1_FIXTURE_DIR` and invoke the existing fixture sync seam.
- CORE-01 and CORE-02 now have green focused governed-data coverage.

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
