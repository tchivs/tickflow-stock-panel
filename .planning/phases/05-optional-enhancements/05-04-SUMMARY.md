---
phase: 05-optional-enhancements
plan: "04"
subsystem: testing
tags: [pytest, forecast, kronos, parquet, numpy, concurrency, calibration, red-contract]
requires:
  - phase: 05-optional-enhancements
    provides: approved pinned Kronos source, checkpoint identities, and local-only supply-chain policy from Plan 05-01
provides:
  - four deterministic governed Forecast fixtures for OHLCV, CN-A sessions, sampled paths, and maturity actuals
  - exact RED contracts for catalog, input, pre-mean quantiles, runner concurrency/recovery, and append-only calibration
  - strict group-aware verifier that rejects collection, fixture, node-inventory, timeout, xfail/xpass, unexpected-pass, and unrelated-failure drift
affects: [05-10, 05-13, 05-14, FORE-01, Kronos forecast implementation]
tech-stack:
  added: []
  patterns:
    - exact node inventory plus allowlisted missing-production-symbol failures for Wave 0 RED verification
    - deterministic Parquet/NumPy fixtures validated before any expected RED outcome is accepted
key-files:
  created:
    - backend/tests/forecast/fixtures/governed_daily.parquet
    - backend/tests/forecast/fixtures/cn_a_sessions.parquet
    - backend/tests/forecast/fixtures/sample_paths.npy
    - backend/tests/forecast/fixtures/maturity_actuals.parquet
    - backend/tests/forecast/test_catalog.py
    - backend/tests/forecast/test_input.py
    - backend/tests/forecast/test_kronos_adapter.py
    - backend/tests/forecast/test_runner.py
    - backend/tests/forecast/test_calibration.py
    - backend/tests/forecast/test_kronos_regression.py
    - backend/tests/forecast/verify_red_contract.py
  modified: []
key-decisions:
  - "The RED verifier accepts only 85 exact missing app.forecast symbol failures plus the one explicitly opt-in offline regression skip; every other outcome is fatal."
  - "FORE-01 concurrency is represented by separately named CAS, idempotency, global/job lease, parallel-winner, interruption-boundary, explicit-retry, restart, immutable-terminal, and no-authority contracts."
  - "Path probability remains measurable from an immutable float64 [32,60,6] fixture whose P10/P50/P90 differ from an averaged-path substitute."
patterns-established:
  - "Wave 0 RED contract: collect exact nodes first, validate fixtures independently, then accept only reviewed missing production symbols at test-call time."
  - "Offline regression: skip only when approved local paths are absent; configured-but-invalid paths and any network attempt are fatal."
requirements-completed: [FORE-01]
coverage:
  - id: D1
    description: "Approved catalog and governed daily/calendar input contracts fail only at declared missing production symbols with exact inventory."
    requirement: FORE-01
    verification:
      - kind: unit
        ref: "cd backend && uv run python tests/forecast/verify_red_contract.py --group catalog-input"
        status: pass
    human_judgment: false
  - id: D2
    description: "Exactly 32 retained pre-mean paths, path-axis quantiles, durable runner concurrency/recovery, and offline regression contracts have exact RED evidence."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd backend && uv run python tests/forecast/verify_red_contract.py --group adapter-runner"
        status: pass
    human_judgment: false
  - id: D3
    description: "Maturity and calibration replay contracts require unique append-only outcomes without rewriting immutable Forecast evidence."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd backend && uv run python tests/forecast/verify_red_contract.py --group calibration"
        status: pass
    human_judgment: false
metrics:
  duration: 12m 15s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 04: Forecast RED Contracts Summary

**Deterministic governed Forecast fixtures and 86 exact-node RED contracts now pin local checkpoint provenance, governed inputs, retained path-axis quantiles, durable concurrency/recovery, and append-only calibration.**

## Performance

- **Duration:** 12m 15s
- **Started:** 2026-07-16T03:44:13Z
- **Completed:** 2026-07-16T03:56:28Z
- **Tasks:** 3/3
- **Files created:** 11

## Accomplishments

- Created governed daily OHLCV and versioned CN-A session Parquet fixtures with valid, duplicate, gap, as-of, insufficiency, partial, and missing cases; added a deterministic float64 `[32,60,6]` sampled-path tensor and governed maturity actuals.
- Declared 33 exact catalog/input nodes covering approved mini/small/base pairings, local roots and digests, safetensors-only loading, no network/remote code, persisted-stock authority, daily OHLCV, exact 5/20/60 sessions, complete provenance, and immutable inputs.
- Declared 40 adapter/runner/regression nodes covering pre-mean path retention, axis-0 P10/P50/P90, invalid numerical output, spawn/process limits, CAS/idempotency/leases, parallel winners, interruption commit points, explicit retry, restart recovery, immutable success, and zero downstream authority.
- Declared 13 calibration nodes covering governed maturity, actual fingerprint, MAE/coverage/pinball metrics, duplicate/parallel/interruption/retry/restart behavior, explicit unevaluable outcomes, and byte-stable original forecasts.
- Added a subprocess-isolated, timeout-bounded verifier that validates all fixture structures before pytest and accepts only the exact reviewed RED failure set.

## Task Commits

Each task was committed atomically:

1. **Task 1: Specify approved catalog, governed OHLCV/calendar input, and local-only loading** — `62ee24f` (`test`)
2. **Task 2: Specify retained path-axis inference and bounded concurrency/recovery** — `f08c1d8` (`test`)
3. **Task 3: Specify append-only maturity outcomes and calibration replay** — `b2f4ba9` (`test`)

## Files Created/Modified

- `backend/tests/forecast/fixtures/governed_daily.parquet` — Deterministic governed stock-daily OHLCV/amount fixture with valid and hostile cases.
- `backend/tests/forecast/fixtures/cn_a_sessions.parquet` — Versioned full and insufficient CN-A future-session calendars.
- `backend/tests/forecast/fixtures/sample_paths.npy` — Finite float64 `[32,60,6]` pre-mean paths with detectably non-mean quantiles.
- `backend/tests/forecast/fixtures/maturity_actuals.parquet` — Mature, partial, and missing governed actual outcomes.
- `backend/tests/forecast/test_catalog.py` — Approved catalog, integrity, local-only, typed-unavailable, and base-host isolation contracts.
- `backend/tests/forecast/test_input.py` — Persisted-stock, horizon, governed OHLCV/calendar, fingerprint, and immutable-input contracts.
- `backend/tests/forecast/test_kronos_adapter.py` — Pre-mean path, sampling, quantile-axis, finite/shape, warning, and local-load contracts.
- `backend/tests/forecast/test_runner.py` — CAS state, idempotency, global/job lease, bounded worker, interruption, retry, restart, commit, and no-authority contracts.
- `backend/tests/forecast/test_calibration.py` — Append-only maturity outcome, metric, uniqueness, replay, restart, and immutability contracts.
- `backend/tests/forecast/test_kronos_regression.py` — Opt-in approved local-model regression with exact provenance and network denial.
- `backend/tests/forecast/verify_red_contract.py` — Strict exact-inventory RED harness for three independent groups and the complete plan.

## Decisions Made

- The harness treats the expected RED set as data: exact node IDs, exact owning groups, allowed production-module/symbol families, and one exact offline-regression skip.
- Fixture/schema validation is independent of pytest outcomes, so corrupt Parquet/NumPy assets can never be misclassified as acceptable RED failures.
- Every concurrency edge called out by FORE-01 has its own executable test node rather than being folded into one broad runner test.
- The public upstream `predict()` averaging behavior is rejected explicitly; quantiles must derive from the retained sample axis before any mean.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used the current governed runner implementation and production-host runner tests after the named test analog was absent**
- **Found during:** Task 2
- **Issue:** `backend/tests/advanced/test_governed_runner.py`, named in `read_first`, does not exist in the current source tree.
- **Fix:** Read `backend/app/advanced/governed_runner.py` plus the focused spawned-runner cases in `backend/tests/advanced/test_production_host.py` and preserved their spawn/process-group/RLIMIT/queue/reap patterns in the Forecast contracts.
- **Files modified:** Forecast test files only.
- **Verification:** Adapter/runner group passed with 40 exact nodes.
- **Committed in:** `f08c1d8`

**2. [Rule 1 - Bug] Bound the base-host import proof to the missing Forecast catalog contract**
- **Found during:** Task 1 verification
- **Issue:** The first strict run correctly rejected one unexpected pass because the base host already imports without optional Forecast dependencies.
- **Fix:** Kept the base-host no-heavy-import assertions but first required the typed missing-catalog probe, making the complete node intentionally RED until the declared catalog symbol exists.
- **Files modified:** `backend/tests/forecast/test_catalog.py`
- **Verification:** Catalog/input group then reported 33 exact declared missing-symbol failures and zero unexpected passes.
- **Committed in:** `62ee24f`

---

**Total deviations:** 2 auto-fixed (1 blocking reference, 1 RED-contract bug).
**Impact on plan:** Both fixes were required to preserve exact read-first grounding and strict failure classification; no production or unrelated code changed.

## Issues Encountered

- The strict harness intentionally surfaced the baseline host-only pass during its first run; after binding that test to the catalog availability contract, every non-regression node failed only at a declared missing production symbol.

## Verification

```text
cd backend && uv run python tests/forecast/verify_red_contract.py --group catalog-input
RED CONTRACT VERIFIED [catalog-input]: 33 exact nodes; 33 declared missing-symbol failures; 0 approved offline skip.

cd backend && uv run python tests/forecast/verify_red_contract.py --group adapter-runner
RED CONTRACT VERIFIED [adapter-runner]: 40 exact nodes; 39 declared missing-symbol failures; 1 approved offline skip.

cd backend && uv run python tests/forecast/verify_red_contract.py --group calibration
RED CONTRACT VERIFIED [calibration]: 13 exact nodes; 13 declared missing-symbol failures; 0 approved offline skip.

cd backend && uv run python tests/forecast/verify_red_contract.py --group all
RED CONTRACT VERIFIED [all]: 86 exact nodes; 85 declared missing-symbol failures; 1 approved offline skip.
```

## TDD Gate Compliance

This is the intentional Wave 0 RED-only plan: the three `test(05-04)` commits establish failing contracts, while Plans 05-10, 05-13, and 05-14 own the corresponding GREEN production commits and ordinary pytest commands. No production implementation or placeholder was added here.

## Known Stubs

None. The missing `app.forecast` symbols are the explicit RED boundary owned by later plans, not delivered stubs; all fixture and verifier infrastructure is executable now.

## Threat Flags

None. This plan adds test fixtures and contracts only; it introduces no endpoint, authentication path, schema migration, runtime file access, or network surface.

## User Setup Required

None for routine verification. The `kronos_model` smoke remains opt-in and skips only when the approved local source/model/tokenizer paths are absent.

## Next Phase Readiness

- Plan 05-10 can implement the approved catalog, governed input/calendar, immutable artifacts, and pre-mean adapter against exact catalog/input/adapter nodes.
- Plan 05-13 can implement the durable repository/runner against separately named CAS, lease, retry, interruption, restart, resource, and commit contracts.
- Plan 05-14 can implement maturity/calibration using the exact unique append and immutable-record replay contracts.

## Self-Check: PASSED

- All 11 planned Forecast files exist.
- Task commits `62ee24f`, `f08c1d8`, and `b2f4ba9` resolve as commits.
- Final all-group verification passed with the exact 86-node inventory and expected RED classifications.
- No unrelated file was staged or committed.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
