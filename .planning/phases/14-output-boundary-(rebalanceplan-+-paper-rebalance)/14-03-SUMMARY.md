---
phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)
plan: 14-03
subsystem: portfolio
tags: [lot-sizing, rebalance, rmse, turnover, odd-lot, blocked]

requires: [14-01]
provides:
  - "Lot-sizing adapter breadth: odd-lot sell (full-exit sells entire position incl. odd lot; reduce-below-one-lot carries odd remainder), cash residue never reallocated (min_cash respected), turnover-cost contract matching MatcherConfig fees (zero on no-change), blocked-instrument exclusion, expires_at default now+7d honored, RMSE simple/weighted, non-finite fail-closed, deterministic tie-break"
affects: [14-05, phase-15]

actuals:
  tokens: 17350
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns:
    - "engine.py lot formula `floor(allocation/(price*(1+cost))/100)*100` reused; MatcherConfig buy/sell cost pct"
    - "deterministic min_cash restore (excess stays in residue) — verified via 600000.SH == 49800 trace"

key-files:
  created: []
  modified:
    - backend/tests/portfolio/test_rebalance.py
  verified:
    - backend/app/portfolio/rebalance.py

key-decisions:
  - "Odd-lot full-exit sells the entire position incl. odd remainder (A-share legal); reduce-below-one-lot carries the odd remainder"
  - "Cash residue never reallocated; min_cash breach leaves excess in residue"

patterns-established:
  - "Breadth cases lock each RBAL-01 edge as a green test: lot floor vs engine.py formula, odd-lot, cash residue, turnover cost, blocked, expiry, RMSE both definitions, non-finite fail-closed"

requirements-completed: [RBAL-01]

coverage:
  - id: D1
    description: "Lot-sizing adapter breadth — odd-lot sell, cash residue (min_cash restore), turnover cost reference, blocked exclusion, expiry default, RMSE simple/weighted, non-finite fail-closed, deterministic tie-break"
    requirement: RBAL-01
    verification:
      - kind: unit
        ref: "backend/tests/portfolio/test_rebalance.py (20 passed)"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-08-02
status: complete
---

# Phase 14 Plan 14-03: Lot-Sizing Adapter Breadth Summary

**The lot-sizing adapter's RBAL-01 breadth is locked by 20 green tests: exact odd-lot sell handling, deterministic cash-residue flooring with min_cash restore, a turnover-cost contract matching MatcherConfig fees (zero on no-change), blocked-instrument exclusion, the expires_at default window, RMSE under both definitions, and non-finite fail-closed.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-08-02T17:55:00Z
- **Completed:** 2026-08-02T18:06:00Z
- **Tasks:** 3
- **Files modified:** 1

## Accomplishments

- Replaced the RED scaffold section of `tests/portfolio/test_rebalance.py` with 20 green breadth tests (up from 14) covering: (1) lot floor equality with the engine.py formula reference `floor(allocation/(price*(1+buy_cost_pct))/100)*100` for every symbol; (2) odd-lot full-exit (sells entire position incl. odd remainder) and reduce-below-one-lot (carries odd remainder); (3) cash residue — the recorded residue equals the hand-computed remainder and is never reallocated; min_cash breach leaves excess in residue (verified `600000.SH == 49800` — the restore path fired); (4) blocked symbol has discrete weight 0 and appears in `blocked_instruments`; (5) expiry default = now + 7 calendar days and a caller-provided value honored; (6) RMSE under both `simple` and `weighted` definitions; (7) turnover cost reference + zero on no-change; (8) deterministic tie-break (same inputs → identical output twice); (9) non-finite weights fail closed.
- Verified the current `rebalance.py` implementation (from 14-01) already handles the breadth behaviors correctly; the 14-03 work is the locked test suite (plus 2 test-design fixes: correct expected lot values; prices covering the run's SYM000-SYM011 symbols).

## Task Commits

1. **Breadth test suite (green)** - `a1cf7e2` (test) — replaces the RED scaffold breadth cases with the 20 green cases.

## Files Created/Modified

- `backend/tests/portfolio/test_rebalance.py` - Replaced the RED scaffold breadth section with 20 green breadth tests; added `Path` import for the missing-run test; fixed expected values and price coverage for the run's SYM symbols.
- `backend/app/portfolio/rebalance.py` - Verified (no changes needed; 14-01 implementation already correct).

## Decisions Made

- Odd-lot full-exit sells the entire position including the odd remainder; reduce-below-one-lot carries the odd remainder — both legal A-share behaviors, asserted exactly.
- Cash residue is never reallocated; a min_cash breach leaves the excess in residue (restore path verified via the `600000.SH == 49800` trace).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test-design errors in expected values**
- **Found during:** breadth test authoring
- **Issue:** Several scaffold expected values were wrong (test-design errors, not implementation bugs) — the lot floor / cash-residue expectations did not match the engine.py formula.
- **Fix:** Corrected the expected values to the hand-computed engine.py formula references.
- **Files modified:** backend/tests/portfolio/test_rebalance.py
- **Verification:** all 20 tests pass.
- **Committed in:** `a1cf7e2`

**2. [Rule 1 - Bug] Price coverage for run symbols**
- **Found during:** breadth test authoring
- **Issue:** Two tests used `fixture_prices` (FIXTURE_SYMBOLS) but the run's `output_weights` are SYM000-SYM011 — the prices did not cover the run symbols.
- **Fix:** Added prices covering the run's SYM symbols.
- **Files modified:** backend/tests/portfolio/test_rebalance.py
- **Verification:** all 20 tests pass.
- **Committed in:** `a1cf7e2`

---

**Total deviations:** 2 auto-fixed (1 test-design expectation, 1 fixture coverage)
**Impact on plan:** None — implementation verified correct; only the locked test suite needed authoring.

## Issues Encountered

- None beyond the two auto-fixed test-design issues.

## User Setup Required

None.

## Next Phase Readiness

- The lot-sizing adapter's full RBAL-01 surface is locked by green tests — 14-05 (robustness + reporting breadth) builds on it.

---
*Phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)*
*Completed: 2026-08-02*

## Self-Check: PASSED

- `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py -q --tb=short` → 20 passed.
- No-execution grep gate: `grep -vE '^\s*(#|""")' app/portfolio/rebalance.py app/portfolio/paper.py | grep -cE '\b(broker|submit|place_order|live_)\b'` == 0; `grep -c "INSERT INTO positions" app/portfolio/paper.py` == 0.
- Tree clean after final commit (only 14-03-SUMMARY.md untracked).
