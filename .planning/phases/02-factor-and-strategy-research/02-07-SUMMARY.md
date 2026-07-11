---
phase: 02-factor-and-strategy-research
plan: "07"
subsystem: strategy-governed-data-provenance
tags: [python, polars, sha256, strategy-backtest, experiment-catalog, provenance]
requires:
  - phase: 02-03
    provides: immutable retained experiment snapshots and governed-data compatibility warnings
  - phase: 02-04
    provides: trusted registered-strategy execution handles and catalog handoff lifecycle
provides:
  - deterministic governed-panel revision and fingerprint on completed registered-strategy results
  - server-only propagation of recognized identity fields through POST and SSE experiment handoffs
  - focused catalog proof of the existing governed-data mismatch warning without ranking
affects: [FACT-03, backtest-api, research-catalog, strategy-experiments]
tech-stack:
  added: []
  patterns:
    - derive provenance once at the governed load_panel boundary from normalized source characteristics
    - pass only catalog-recognized revision and fingerprint values from a server-issued result
key-files:
  created: []
  modified:
    - backend/app/backtest/strategy.py
    - backend/app/api/backtest.py
    - backend/tests/backtest/test_strategy_backtest_correctness.py
    - backend/tests/research/test_strategy_experiment_handoff.py
    - backend/tests/research/test_experiment_catalog.py
key-decisions:
  - "Completed strategy results fingerprint the full governed panel loaded for execution, including warmup and any full-mode buffer."
  - "The catalog receives only revision and fingerprint copied from the server-issued result under its existing recognized keys."
  - "Catalog warning vocabulary and no-winner comparison semantics remain unchanged."
patterns-established:
  - "Governed strategy provenance: normalize schema and source-reference metadata with compact sorted JSON before SHA-256 hashing."
requirements-completed: [FACT-03]
coverage:
  - id: FACT-03-STRATEGY-PROVENANCE
    description: Completed registered strategy results expose deterministic governed-panel revision and fingerprint identity.
    requirement: FACT-03
    verification:
      - kind: unit
        ref: uv run --project backend pytest backend/tests/backtest/test_strategy_backtest_correctness.py -q
        status: pass
    human_judgment: false
  - id: FACT-03-TRUSTED-HANDOFF
    description: POST and SSE strategy completion retain only server-derived identity and reject forged request provenance.
    requirement: FACT-03
    verification:
      - kind: integration
        ref: uv run --project backend pytest backend/tests/research/test_strategy_experiment_handoff.py -q
        status: pass
    human_judgment: false
  - id: FACT-03-COMPARISON-WARNING
    description: Otherwise matching retained strategy snapshots emit only the existing governed-data mismatch warning and no winner or ranking.
    requirement: FACT-03
    verification:
      - kind: unit
        ref: uv run --project backend pytest backend/tests/research/test_experiment_catalog.py -q
        status: pass
    human_judgment: false
metrics:
  duration: 4m 30s
  completed: 2026-07-11
status: complete
---

# Phase 02 Plan 07: Strategy Governed-Data Provenance Summary

**Registered strategy backtests now retain deterministic SHA-256 governed-panel identity through trusted POST/SSE handoffs and expose the existing data-mismatch warning for retained comparisons.**

## Performance

- **Duration:** 4m 30s
- **Started:** 2026-07-11T08:25:29Z
- **Completed:** 2026-07-11T08:29:59Z
- **Tasks:** 3/3
- **Files modified:** 5

## Accomplishments

- Derived `revision` from the loaded panel schema and `fingerprint` from normalized governed source metadata at the sole `BacktestEngine.load_panel()` boundary; the full loaded panel is represented rather than copied or re-read.
- Added the resolved `asset_type` to serialized strategy configuration and kept result, failure, and cancellation values compatible with `dataclasses.asdict()` and `dataclasses.replace()`.
- Copied only recognized server-issued `revision` and `fingerprint` fields into the existing immutable strategy input manifest for synchronous and SSE terminal handoffs; request evidence remains forbidden.
- Added regressions proving the unchanged catalog warning is isolated to a governed-data identity mismatch and that comparison never reports a winner or ranking.

## Task Commits

Each task was committed atomically:

1. **Task 1: Derive deterministic governed-panel identity in registered strategy results** — `cf06907` (`feat`)
2. **Task 2: Preserve trusted manifest identity through synchronous and SSE catalog handoff** — `89e9e55` (`feat`)
3. **Task 3: Isolate the governed-data mismatch warning for retained strategy snapshots** — `d233742` (`test`)

**Plan metadata:** committed with this summary.

## Verification

```text
uv run --project backend pytest backend/tests/backtest/test_strategy_backtest_correctness.py backend/tests/research/test_strategy_experiment_handoff.py backend/tests/research/test_experiment_catalog.py -q
11 passed in 2.24s
```

Focused task evidence:

```text
uv run pytest tests/backtest/test_strategy_backtest_correctness.py -q
4 passed in 0.28s

uv run pytest tests/research/test_strategy_experiment_handoff.py -q
2 passed in 1.48s

uv run pytest tests/research/test_experiment_catalog.py -q
5 passed in 1.03s
```

## Files Created/Modified

- `backend/app/backtest/strategy.py` — derives normalized governed source metadata and stable identities from the actual loaded Polars panel.
- `backend/app/api/backtest.py` — transfers only recognized server-generated identity fields into the catalog input manifest.
- `backend/tests/backtest/test_strategy_backtest_correctness.py` — covers stable and materially changed panel identities plus result dataclass compatibility.
- `backend/tests/research/test_strategy_experiment_handoff.py` — covers POST/SSE identity retention and rejected forged provenance.
- `backend/tests/research/test_experiment_catalog.py` — isolates data-identity comparison warnings and equal-identity control behavior.

## Decisions Made

- Fingerprint the full panel loaded by the service, including its warmup and full-mode forward buffer, because that is the governed data actually used during execution.
- Use the catalog's existing `revision` and `fingerprint` compatibility keys and warning text; do not introduce an alternate comparison convention.
- Preserve requested start/end in the resolved strategy configuration while recording observed loaded range in the governed result manifest.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed ordering dependence from the catalog delta regression**
- **Found during:** Task 3 (Isolate the governed-data mismatch warning for retained strategy snapshots)
- **Issue:** The first regression assertion assumed SQLite history ordering when checking the immutable manifest-delta values.
- **Fix:** Assert each delta by its experiment ID rather than iteration order.
- **Files modified:** `backend/tests/research/test_experiment_catalog.py`
- **Verification:** `uv run pytest tests/research/test_experiment_catalog.py -q` — 5 passed.
- **Committed in:** `d233742` (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 test-correctness fix).
**Impact on plan:** The fix makes the planned regression deterministic without changing product behavior or scope.

## Known Stubs

None. The plan's modified implementation files were scanned for placeholder and TODO/FIXME markers; no deliverable-blocking stub was found.

## Issues Encountered

None. The existing catalog implementation already recognized the required fields and warning text, so Task 3 required only the focused regression specified by the plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

FACT-03's remaining governed-data provenance gap is covered by focused service, API-handoff, and catalog-comparison tests. No new storage, strategy execution path, comparison vocabulary, or client provenance boundary was added.

## Self-Check: PASSED

Verified all five implementation/test artifacts, the summary artifact, and task commits `cf06907`, `89e9e55`, and `d233742` exist.

---
*Phase: 02-factor-and-strategy-research*
*Completed: 2026-07-11*
