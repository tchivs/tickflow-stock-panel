---
phase: 02-factor-and-strategy-research
plan: 06
subsystem: factor-dsl-partition-semantics
tags: [python, polars, factor-dsl, governed-evaluation, testing]
requires:
  - phase: 02-01
    provides: immutable parsed factor revisions and governed evaluation contracts
  - phase: 02-02
    provides: Phase 2 factor research workflow foundations
provides:
  - Fixed date-partitioned cross-sectional rank and z-score DSL semantics
  - Fixed symbol-partitioned rolling mean semantics in vectorized Polars evaluation
  - Deterministic compiler and managed-artifact regression evidence for FACT-01
affects: [factor-evaluation, factor-dsl, governed-data-evidence]
tech-stack:
  added: []
  patterns:
    - Fixed AST constructors own their non-configurable partition semantics.
    - Stateful evaluation evidence is asserted from managed signal artifacts.
key-files:
  created:
    - .planning/phases/02-factor-and-strategy-research/02-06-SUMMARY.md
  modified:
    - backend/app/research/factor_dsl.py
    - backend/tests/research/test_factor_dsl.py
    - backend/tests/research/test_factor_evaluation.py
key-decisions:
  - "rank and zscore are fixed cross-sectional operations over date; callers cannot choose grouping semantics."
  - "rolling_mean uses min_samples=1 over symbol so each symbol begins with its own first governed observation."
patterns-established:
  - "Compile stateful factors as fixed Polars expressions partitioned at the constructor."
  - "Prove governed evaluation behavior by reading immutable signals.json artifact records."
requirements-completed: [FACT-01]
coverage:
  - id: D1
    description: Fixed stateful DSL expressions reset rank and z-score by date and rolling windows by symbol.
    requirement: FACT-01
    verification:
      - kind: unit
        ref: backend/tests/research/test_factor_dsl.py#test_compiler_partitions_stateful_functions_by_date_or_symbol
        status: pass
    human_judgment: false
  - id: D2
    description: The public governed evaluation service records partitioned factor values in managed signal artifacts while retaining its BacktestEngine loading boundary.
    requirement: FACT-01
    verification:
      - kind: integration
        ref: backend/tests/research/test_factor_evaluation.py#test_evaluation_artifacts_preserve_stateful_factor_partitions
        status: pass
    human_judgment: false
metrics:
  duration: not recorded
  completed: 2026-07-11
status: complete
---

# Phase 02 Plan 06: Factor DSL Partition Semantics Summary

**Date-partitioned rank/z-score and symbol-partitioned rolling factor evaluation, proven from fixed AST compilation through immutable governed signal artifacts.**

## Performance

- **Duration:** Not recorded; the executor start timestamp was unavailable.
- **Completed:** 2026-07-11T08:19:55Z
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments

- Bound `rank(close)` and `zscore(close)` to same-date peers while preserving the closed parsed-AST-to-Polars compiler.
- Bound `rolling_mean(close, 2)` to chronological observations of each symbol, including each symbol's first partial window.
- Added deterministic two-symbol, multi-date unit and public-service regressions that read exact factors and forward returns from managed `signals.json` evidence.

## Verification Evidence

- `uv run --project backend pytest backend/tests/research/test_factor_dsl.py -q` — passed: 12 tests.
- `uv run --project backend pytest backend/tests/research/test_factor_evaluation.py -q` — passed: 8 tests; 5 existing Polars `DataFrame.pivot(columns=...)` deprecation warnings.
- `uv run --project backend pytest backend/tests/research/test_factor_dsl.py backend/tests/research/test_factor_evaluation.py -q` — passed: 20 tests; the same 5 existing deprecation warnings.
- The service regression proves one `BacktestEngine.load_panel()` call with only `symbol`, `date`, and `close`, checks completed-result configuration/manifest/IC/RankIC evidence, and verifies artifact factors and forward returns row-by-row.

## Task Commits

Each completed task was committed atomically:

1. **Task 1: Make the fixed DSL stateful constructors partition-aware** — `d07900a` (`feat`)
2. **Task 2: Prove partition semantics through the governed evaluation service** — `6160fe4` (`test`)

## Files Created/Modified

- `backend/app/research/factor_dsl.py` — Fixed date/symbol partitions on the three stateful DSL constructors.
- `backend/tests/research/test_factor_dsl.py` — Covers deterministic date and symbol state boundaries at compiler level.
- `backend/tests/research/test_factor_evaluation.py` — Covers the governed evaluation path and immutable signal artifact values for all three functions.
- `.planning/phases/02-factor-and-strategy-research/02-06-SUMMARY.md` — Records execution, verification, decisions, and deviation evidence.

## Decisions Made

- Fixed `rank` and both z-score aggregate terms to `.over("date")`; this preserves cross-sectional factor semantics without exposing arbitrary group selection.
- Fixed `rolling_mean` to `.rolling_mean(..., min_samples=1).over("symbol")`; this preserves the specified first-observation behavior while preventing symbol-boundary leaks.
- Left `FactorEvaluationService._evaluate_panel()` unchanged: its single governed `BacktestEngine.load_panel()` boundary, `symbol,date` sort, vectorized Polars flow, and symbol-partitioned forward returns remain the execution contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored the specified first-observation rolling value**
- **Found during:** Task 1 (Make the fixed DSL stateful constructors partition-aware)
- **Issue:** Polars defaults to a full rolling window, producing `null` for each symbol's first observation rather than the plan's required `[10, 20]` and `[20, 30]` sequences.
- **Fix:** Set `min_samples=1` on the existing fixed `rolling_mean` constructor while adding `.over("symbol")`.
- **Files modified:** `backend/app/research/factor_dsl.py`
- **Verification:** `uv run --project backend pytest backend/tests/research/test_factor_dsl.py -q` passed 12 tests.
- **Committed in:** `d07900a`

---

**Total deviations:** 1 auto-fixed (Rule 1 bug)
**Impact on plan:** Required for the plan's explicit rolling-window behavior; no caller-configurable semantics or scope expansion was introduced.

## TDD Gate Compliance

- A RED run of `backend/tests/research/test_factor_dsl.py` failed as expected before the partition implementation, demonstrating the missing date partition (`rank` returned `[1, 3, 2, 4]`).
- The RED test and implementation were captured together in the atomic Task 1 commit (`d07900a`) to honor the assignment's one-commit-per-task requirement; therefore the plan-level git ordering does not contain a separate `test(...)` commit before the `feat(...)` commit.

## Known Stubs

None. The created and modified files were scanned for placeholder and TODO/FIXME patterns; no delivery-blocking stubs were found.

## Threat Surface

No new network endpoint, authentication path, file-access pattern, schema change, or trust boundary was introduced. The fixed compiler dispatch retains the plan's no-caller-controlled-partition mitigation.

## User Setup Required

None — no external service configuration is required.

## Next Phase Readiness

FACT-01's partitioning gap is closed with deterministic compiler and governed-service evidence. Phase 02's remaining FACT-03 manifest work remains outside this plan's scope.

## Self-Check: PASSED

- Confirmed all three modified source/test files and this summary exist.
- Confirmed task commits `d07900a` and `6160fe4` exist in repository history.
