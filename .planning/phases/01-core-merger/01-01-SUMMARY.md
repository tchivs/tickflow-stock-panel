---
phase: 01-core-merger
plan: "01"
subsystem: testing
tags: [pytest, polars, duckdb, parquet, data-governance]

requires: []
provides:
  - "Offline fixture-sync pytest contract for the governed Parquet, DuckDB, and Polars path"
  - "Manifest validation pytest contracts for daily market-data integrity boundaries"
affects: [01-02, governed-data, daily-pipeline]

tech-stack:
  added: []
  patterns:
    - "Fixture mode is explicit, offline, and isolated through PHASE1_FIXTURE_MODE."
    - "Governed-data failures identify the D-17 invariant they reject."

key-files:
  created:
    - backend/tests/test_phase1_fixture_sync.py
    - backend/tests/test_data_contracts.py
  modified: []

key-decisions:
  - "Fixture synchronization is specified through the existing Parquet lake, DuckDB views, and Polars enrichment rather than a test-only storage path."
  - "The manifest contract rejects duplicate daily keys, invalid Asia/Shanghai timestamps, out-of-window repairs, and incompatible Parquet schemas deterministically."

patterns-established:
  - "Offline fixture contracts remove API keys and replace socket connections with a failing guard."
  - "Data-governance assertions name D-13 or D-17 at the isolation and lake boundaries."

requirements-completed: [CORE-01, CORE-02]

coverage:
  - id: D1
    description: "Offline governed fixture-sync contract module"
    requirement: CORE-01
    verification:
      - kind: other
        ref: "uv run --directory backend pytest tests/test_phase1_fixture_sync.py tests/test_data_contracts.py -q; test $? -ne 0"
        status: pass
    human_judgment: true
    rationale: "The contract has been verified in its intentionally RED state; Plan 02 must implement the provider and pipeline symbols before governed synchronization itself can pass."
  - id: D2
    description: "Governed market-data manifest rejection contract module"
    requirement: CORE-02
    verification:
      - kind: other
        ref: "uv run --directory backend pytest tests/test_phase1_fixture_sync.py tests/test_data_contracts.py -q; test $? -ne 0"
        status: pass
    human_judgment: true
    rationale: "The contract has been verified in its intentionally RED state; Plan 02 must implement the validator symbols before governed-data validation itself can pass."

# Metrics
duration: 3 min
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 01: Define governed fixture-sync and data-contract test contracts Summary

**Deterministic, offline pytest contracts now define the fixture-sync path and governed market-data validation boundary Plan 02 must implement.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-11T01:32:02Z
- **Completed:** 2026-07-11T01:35:52Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Added an isolated `PHASE1_FIXTURE_MODE` contract that requires local fixture data to travel through Parquet persistence, DuckDB views, and Polars enrichment without an API key or network connection.
- Added four deterministic D-17 validator contracts for duplicate daily primary keys, invalid market-time semantics, repair-window violations, and incompatible Parquet schema drift.
- Defined the expected Plan 02 seams: `run_phase1_fixture_sync`, `fixture_provider_enabled`, `DataContractViolation`, and `validate_market_data_manifest`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define governed fixture-sync and data-contract test contracts** - `704c132` (test)

**Plan metadata:** committed with this summary

## Files Created/Modified
- `backend/tests/test_phase1_fixture_sync.py` - Offline governed-lake fixture synchronization contracts.
- `backend/tests/test_data_contracts.py` - Manifest validation contracts for D-17 integrity failures.

## Decisions Made
- Fixture synchronization is specified through the existing Parquet lake, DuckDB views, and Polars enrichment rather than a test-only storage path.
- The manifest contract rejects duplicate daily keys, invalid Asia/Shanghai timestamps, out-of-window repairs, and incompatible Parquet schemas deterministically.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The configured Tsinghua PyPI mirror initially returned HTTP 403. Retrying against the official PyPI index with the backend `dev` extra (`uv run --directory backend --extra dev pytest tests/test_phase1_fixture_sync.py tests/test_data_contracts.py -q`) collected the suite and produced the expected six RED failures: the two fixture-pipeline symbols and the `app.contracts` validator module do not exist until Plan 02.
- `backend/.venv/bin/python -m py_compile backend/tests/test_phase1_fixture_sync.py backend/tests/test_data_contracts.py` passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 02 can implement the named fixture-provider, pipeline, manifest, and validator seams to turn these same tests green.
- Browser tooling plan 01-06 remains untouched and requires its own human checkpoint.

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
