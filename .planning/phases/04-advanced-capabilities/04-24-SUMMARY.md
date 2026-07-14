---
phase: 04-advanced-capabilities
plan: 24
subsystem: data-ingestion
tags: [fixture, readiness, market-data, parquet, duckdb, pydantic]
requires:
  - phase: 04-advanced-capabilities
    provides: deployment-owned advanced-host fixture and governed research asset binding
provides:
  - Typed deployment-owned advanced-host readiness descriptor
  - Read-only semantic fixture preflight before governed-lake mutation
  - Production bullish-alignment eligibility reuse for host fixture admission
affects: [advanced-host, fixture-sync, governed-lake, production-lifecycle]
tech-stack:
  added: []
  patterns:
    - Parse trusted host readiness before DataStore construction.
    - Validate raw fixture semantics and strategy eligibility before normal provider writes.
key-files:
  created: []
  modified:
    - backend/app/contracts/market_data.py
    - backend/app/jobs/daily_pipeline.py
    - backend/app/main.py
    - backend/tests/test_market_data_fixture_contract.py
    - backend/tests/test_phase1_fixture_sync.py
    - backend/tests/advanced/test_production_host.py
key-decisions:
  - "Advanced-host readiness is deployment-owned and must specify 000300.SH, symbols, fixed evaluation windows, coverage, splits, and bullish_alignment warmup."
  - "The preflight derives MA and momentum inputs from bounded raw bars, then invokes the production bullish-alignment expression rather than duplicating its predicate."
  - "Fixture validation runs after read-only bundle load and before DataStore construction, Parquet writes, DuckDB view work, or cache refresh."
patterns-established:
  - "Advanced fixture inputs use a typed descriptor plus bounded read-only preflight at the provider-to-lake boundary."
requirements-completed: [ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02]
coverage:
  - id: D1
    description: Typed readiness parsing and strict malformed-bar, benchmark, coverage, order, timestamp, and no-signal rejection.
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: backend/tests/test_market_data_fixture_contract.py
        status: pass
    human_judgment: false
  - id: D2
    description: Advanced fixture synchronization rejects before DataStore and governed-lake state mutation while valid fixtures retain the normal pipeline.
    requirement: SAFE-02
    verification:
      - kind: integration
        ref: cd backend && timeout 30s uv run pytest tests/test_market_data_fixture_contract.py tests/test_phase1_fixture_sync.py -q
        status: pass
    human_judgment: false
  - id: D3
    description: Real lifespan accepts a valid readiness descriptor and rejects an invalid descriptor before governed-lake artifacts exist.
    requirement: ADV-02
    verification:
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py -k 'loads_and_persists or rejects_invalid or stale_research'
        status: pass
    human_judgment: false
metrics:
  duration: 12m 53s
  completed: 2026-07-14
status: complete
---

# Phase 04 Plan 24: Advanced Host Fixture Readiness Summary

**Deployment-owned readiness descriptors now reject malformed, incomplete, or signal-ineligible advanced fixtures before any governed Parquet, DuckDB, view, or cache mutation.**

## Performance

- **Duration:** 12m 53s
- **Started:** 2026-07-14T05:59:20Z
- **Completed:** 2026-07-14T06:12:23Z
- **Tasks:** 2/2
- **Files modified:** 9

## Accomplishments

- Added typed readiness ranges, split containment, fixed `[20, 60, 120]` evaluation windows, configured symbols, required `000300.SH`, and positive strategy warmup validation.
- Added finite/positive/OHLC/session-time semantic validation, chronological uniqueness and weekday coverage checks, and a bounded MA/momentum derivation that calls the production `bullish_alignment` predicate.
- Moved advanced readiness parsing ahead of fixture synchronization and gates the provider before `DataStore`, lake, view, and cache work; normal non-host fixtures retain their established path.
- Added malformed/no-readiness matrix and valid-path regressions that assert rejected fixtures leave no governed-lake state; added real-lifespan descriptor coverage.

## Task Commits

1. **Task 1: Define semantic advanced-host fixture readiness and reuse the real required-signal rule** — `9476d68` (feat)
2. **Task 2: Gate fixture synchronization before writes and prove every rejected shape is side-effect free** — `f4458b7` (test)

## Files Created/Modified

- `backend/app/contracts/market_data.py` — typed readiness descriptor and bounded semantic fixture preflight.
- `backend/app/contracts/validator.py` — shared positive Asia/Shanghai market-session timestamp checker.
- `backend/app/data_providers/fixture_provider.py` — read-only provider preflight boundary.
- `backend/app/jobs/daily_pipeline.py` — pre-`DataStore` advanced-host gate.
- `backend/app/main.py` — deployment fixture parsing before synchronization.
- `backend/app/strategy/builtin/bullish_alignment.py` — reusable production eligibility expression.
- `backend/tests/test_market_data_fixture_contract.py` — malformed/no-readiness and valid governed-pipeline matrix.
- `backend/tests/test_phase1_fixture_sync.py` — descriptor-absence prewrite regression.
- `backend/tests/advanced/test_production_host.py` — valid and invalid lifecycle descriptor proof plus preserved prior host binding proof.

## Decisions Made

- The advanced host accepts only the built-in `bullish_alignment` strategy and `000300.SH` benchmark configured through the deployment-owned descriptor.
- Coverage is checked against bounded weekday sessions for every configured stock and benchmark, with no calendar or live-provider access.
- The provider calls the extracted production eligibility expression only after deriving its MA/momentum inputs from raw fixture bars.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Preserved prerequisite Plan 04-22 host fixture assertions while adding readiness coverage**
- **Found during:** Task 1
- **Issue:** `backend/tests/advanced/test_production_host.py` contained uncommitted, related Plan 04-22 fixture/binding assertions. The old index fixture also had inconsistent scaled close versus unscaled OHLC values, which the planned semantic validator correctly rejected.
- **Fix:** Retained the existing binding assertion group, made all index OHLC/amount values consistently scaled, and committed the consolidated lifecycle fixture coverage after verifying both the preserved stale-binding proof and the new readiness proofs.
- **Files modified:** `backend/tests/advanced/test_production_host.py`
- **Verification:** `cd backend && timeout 30s uv run pytest tests/advanced/test_production_host.py -q -k 'loads_and_persists or rejects_invalid or stale_research'` — 3 passed.
- **Committed in:** `9476d68`

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking)
**Impact on plan:** Required to preserve existing host assertions while making the shared fixture semantically valid for the new fail-closed readiness contract.

## Known Stubs

None found in the files changed by this plan.

## Issues Encountered

The broader production-host module has unrelated pre-existing failures in governed-runner tests that require a Plan 04-22 binding resolver. The focused readiness and preserved host binding assertions pass; this plan did not alter the unrelated runner service boundary.

## User Setup Required

None — the descriptor is part of the existing deployment-owned `ADVANCED_HOST_FIXTURE` JSON.

## Next Phase Readiness

Advanced-host startup can now deny malformed, incomplete, wrong-benchmark, or non-eligible fixtures before governed data exists, while a valid read-only fixture follows the existing Parquet/SQLite/DuckDB path.

## Self-Check: PASSED

- Summary file exists and both task commits (`9476d68`, `f4458b7`) resolve to commit objects.

---
*Phase: 04-advanced-capabilities*
*Plan: 24*
*Completed: 2026-07-14*
