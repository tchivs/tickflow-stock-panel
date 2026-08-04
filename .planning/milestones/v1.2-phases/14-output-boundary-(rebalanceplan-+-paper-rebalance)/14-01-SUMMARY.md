---
phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)
plan: 14-01
subsystem: portfolio
tags: [rebalance-plan, lot-sizing, paper-rebalance, append-only, sqlite, audit]
requires:
  - phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)
    provides: rebalance_plans + paper_rebalance_transitions tables, PortfolioRepository rebalance/paper methods, Wave 0 test scaffolds + conftest fixtures
provides:
  - "portfolio/rebalance.py: RebalancePlan + DiscretizationResult dataclasses, discretize_weights (engine.py:1158 lot formula + MatcherConfig fees, cash-aware largest-weight-first, odd-lot sell, cash residue, turnover cost, blocked, expiry, RMSE simple/weighted), build_rebalance_plan (fail-closed run gate → O_EXCL+fsync+sha256 artifact → rebalance_plans row), load_rebalance_plan (checksum-verified read)"
  - "portfolio/paper.py: create_suggestion / approve / reject / paper_fill — append-only paper-rebalance state machine (suggested/approved/rejected/filled), idempotent, expired fail-closed, zero execution authority"
  - "End-to-end tracer proof: run weights → plan artifact → suggestion → approve → fill on a fixture"
affects: [14-03, 14-04, 14-05, 15]

actuals:
  tokens: 6900
  tasks: 4
  commits: 4

tech-stack:
  added: []
  patterns:
    - "engine.py:1158 lot formula REUSE (floor(allocation/(price*(1+buy_cost_pct))/100)*100) — never a second matcher"
    - "MatcherConfig buy_cost_pct()/sell_cost_pct() fee model REUSE for turnover cost + lot sizing"
    - "O_EXCL + fsync + sha256 immutable plan artifact via PortfolioArtifactService.write_analysis_artifact"
    - "Append-only idempotent state machine over repository.record_paper_transition (UNIQUE (plan_id, transition))"
    - "Fail-closed run gate mirroring analyzer.py L92-95 + non-finite fail-closed mirroring L117-118"

key-files:
  created:
    - backend/app/portfolio/rebalance.py
    - backend/app/portfolio/paper.py
  modified:
    - backend/tests/portfolio/test_rebalance.py
    - backend/tests/portfolio/test_paper.py

key-decisions:
  - "RebalancePlan is a frozen slots dataclass; discretize_weights is a pure cash-aware largest-weight-first lot-sizing adapter reusing the engine.py:1158 formula — no second matcher"
  - "discretize_weights consumes odd_lot_positions (odd-lot sell: full exit below one board lot, remainder carried when target >= 1 lot); cash residue = equity - Σ share·price·(1+buy_cost_pct), never reallocated"
  - "Turnover cost = Σ buy_value·buy_cost_pct + Σ sell_value·sell_cost_pct from the REUSED MatcherConfig model; RMSE simple/weighted over the FULL universe incl. blocked"
  - "build_rebalance_plan binds input_snapshot_sha256 from the run row (consumed via snapshot, never recomputed); artifact written via write_analysis_artifact with output_sha256 bound to the rebalance_plans row"
  - "paper.py exposes ONLY the four transitions (create_suggestion/approve/reject/paper_fill); approve/reject idempotent by (plan_id, transition) + matching idempotency_key; paper_fill writes ONLY paper_rebalance_transitions"

patterns-established:
  - "Lot-sizing adapter: REUSE the engine.py matching rules, never a second matcher"
  - "State machine: every transition an append-only audit fact with UNIQUE (plan_id, transition) idempotency"

requirements-completed: [RBAL-01, RBAL-02]

coverage:
  - id: D1
    description: "RebalancePlan rendered from a recorded Phase 11 run through the engine.py-lot-formula adapter — 100-share lots, blocked exclusion, cash residue, turnover cost, RMSE, expires_at default (now+7d), immutable artifact + rebalance_plans row binding"
    requirement: RBAL-01
    verification:
      - kind: integration
        ref: "tests/portfolio/test_rebalance.py#test_tracer_rebalance_plan_to_paper_fill_end_to_end"
        status: pass
    human_judgment: false
  - id: D2
    description: "Paper-rebalance state machine — suggestion → approve → fill as append-only idempotent audit facts with zero execution authority (positions row count unchanged, no raw SQL, no execution vocabulary)"
    requirement: RBAL-02
    verification:
      - kind: integration
        ref: "tests/portfolio/test_paper.py#test_no_execution_route_regression_gate"
        status: pass
    human_judgment: false

duration: 75min
completed: 2026-08-02
status: complete
---

# Phase 14 Plan 14-01: Tracer — End-to-End RebalancePlan → Paper-Rebalance Slice Summary

**RebalancePlan lot-sizing adapter (engine.py:1158 formula REUSED) + append-only paper-rebalance state machine proven end-to-end on a fixture: run weights → O_EXCL+fsync+sha256 plan artifact + rebalance_plans row → suggestion → idempotent approve → paper fill — with the no-execution-route gate green.**

## Performance

- **Duration:** 75 min
- **Started:** 2026-08-02T20:55:00Z
- **Completed:** 2026-08-02T21:35:00Z
- **Tasks:** 4 (3 build/test tasks + 1 fix/reconcile commit)
- **Files modified:** 4

## Accomplishments
- `portfolio/rebalance.py` — frozen slots `RebalancePlan` + `DiscretizationResult`; `discretize_weights` is a cash-aware largest-weight-first lot-sizing adapter that REUSES the engine.py:1158 formula `floor(allocation/(price*(1+buy_cost_pct))/100)*100` and the `MatcherConfig` fee model (no second matcher). Odd-lot sell (full exit below one board lot; remainder carried when target ≥ 1 lot), deterministic cash residue never reallocated, turnover cost from buy/sell legs, blocked exclusion recorded verbatim, `expires_at` default now+7 calendar days, RMSE simple/weighted over the full universe incl. blocked.
- `build_rebalance_plan` — fail-closed run gate (missing / `problem_status != optimal` / empty weights → ValueError, mirroring analyzer L92-95); binds `input_snapshot_sha256` from the run row; writes the immutable artifact via `PortfolioArtifactService.write_analysis_artifact` (O_EXCL + fsync + sha256) and the append-only `rebalance_plans` row binding `optimization_run_id` + `input_snapshot_sha256` + `output_sha256` + `artifact_relative_path`. `load_rebalance_plan` — checksum-verified read (`read_artifact(relative_path, checksum_sha256=output_sha256)`).
- `portfolio/paper.py` — the paper-rebalance state machine: `create_suggestion` / `approve` / `reject` / `paper_fill`, each an append-only idempotent audit fact (UNIQUE (plan_id, transition) + matching idempotency_key); approve/reject mutually exclusive; expired plans fail closed; `paper_fill` writes ONLY `paper_rebalance_transitions` (zero raw SQL in the module).
- End-to-end tracer integration test — the full Phase 14 spine on a fixture (recorded optimal run → discretize → artifact + row → suggestion → idempotent approve → fill), asserting RMSE/lots/cash_residue/turnover/blocked/expiry, ledger ordinals, `paper_position_delta == discrete lots`, and the `positions` table row count UNCHANGED.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create `portfolio/rebalance.py`** - `c6169ef` (feat: RebalancePlan lot-sizing adapter + plan builder)
2. **Task 2: Create `portfolio/paper.py`** - `5e51cf8` (feat: paper-rebalance state machine with no-execution contract)
3. **Task 3: End-to-end tracer proof** - `a300ac9` (test: tracer end-to-end RebalancePlan → paper-fill spine + state-machine breadth)
4. **Task 4: Reconcile + commit crashed-pass fixes** - `d4fcc48` (fix: deterministic min_cash restore + odd-lot validation)

**Plan metadata:** `(pending)` — final metadata commit created after SUMMARY/STATE/ROADMAP updates.

## Files Created/Modified
- `backend/app/portfolio/rebalance.py` - RebalancePlan + DiscretizationResult dataclasses; discretize_weights / build_rebalance_plan / load_rebalance_plan (new)
- `backend/app/portfolio/paper.py` - create_suggestion / approve / reject / paper_fill state machine with no-execution contract (new)
- `backend/tests/portfolio/test_rebalance.py` - Wave 0 scaffold cases turned green + tracer integration test (extended)
- `backend/tests/portfolio/test_paper.py` - Wave 0 scaffold cases turned green + state-machine breadth + no-execution regression gate (extended)

## Decisions Made
- `discretize_weights` is a pure adapter: REUSE the engine.py:1158 lot formula and the MatcherConfig fee model — never a second matcher (per 14-CONTEXT.md locked decision).
- Cash residue = `equity − Σ share·price·(1 + buy_cost_pct)`, never reallocated; min_cash restore reduces whole board lots deterministically (largest-weight-first, stable symbol tie-break) rather than forcing a partial buy.
- Turnover cost = buy leg at `buy_cost_pct` + sell leg at `sell_cost_pct` (zero on a no-change plan); RMSE simple/weighted over the full universe incl. blocked (blocked contributes honestly with discrete weight 0).
- `build_rebalance_plan` binds `input_snapshot_sha256` from the run row (consumed via snapshot, never recomputed) and mirrors analyzer's fail-closed run gate.
- paper.py exposes ONLY the four transitions; approve/reject idempotent by (plan_id, transition) + matching idempotency_key; paper_fill records `paper_position_delta = {symbol: shares}` and writes ONLY `paper_rebalance_transitions`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Idempotent re-approve/re-reject returned a NEW row instead of the existing one**
- **Found during:** Task 3 (state-machine breadth tests)
- **Issue:** `approve`/`reject` guarded `state in _TERMINAL_STATES` before allowing the `approved`/`rejected` states, so a second approve/reject raised instead of returning the existing row.
- **Fix:** Gate on the allowed-state set (`suggested`/`approved` for approve, `suggested`/`rejected` for reject) and pass `previous_state=state` so re-transition is idempotent via the UNIQUE (plan_id, transition) key.
- **Files modified:** backend/app/portfolio/paper.py
- **Verification:** `pytest tests/portfolio/test_paper.py -q --tb=short` — approve/reject idempotency cases green.
- **Committed in:** a300ac9 (test) + d4fcc48 (fix)

**2. [Rule 1 - Bug] Deterministic min_cash restore + odd-lot validation missing in lot-sizing adapter**
- **Found during:** Final reconciliation before tracer commit (crashed-pass residue in the working tree)
- **Issue:** Odd-lot carry could push cash residue below min_cash after the board-lot budget was allocated; `odd_lot_positions` accepted fractional/negative shares silently.
- **Fix:** Added a deterministic whole-lot reduction loop (largest-weight-first) that restores min_cash without ever creating a partial buy; validated odd_lot_positions are non-negative whole shares; `min_cash > equity` fails closed.
- **Files modified:** backend/app/portfolio/rebalance.py
- **Verification:** All 25 portfolio tests green with the fixes in place.
- **Committed in:** d4fcc48

---

**Total deviations:** 2 auto-fixed (2 Rule 1 — Bug)
**Impact on plan:** Both fixes required for the idempotency and cash-residue contracts to hold. No scope creep.

## Issues Encountered
- Concurrent-executor reconciliation: a previous crashed pass left uncommitted edits in `rebalance.py`/`paper.py` (odd-lot-carry reduce loop, whole-share validation, message wording). Confirmed via the peer executor (Exec0101 made zero edits) that these were residue from an earlier pass of this session; reconciled, verified (25 tests green), and committed as `d4fcc48`.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave 2 breadth plans (14-03 lot-sizing breadth, 14-04 paper state-machine breadth) build directly on the tracer's adapter + state machine — both files are now green.
- Phase 15 can surface plans + paper state through the 14-02 repository read/list surface (`get/list rebalance plans`, `list paper transitions`, derived `get_paper_state`).

---
*Phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)*
*Completed: 2026-08-02*

## Self-Check: PASSED

- Created files verified: rebalance.py, paper.py, test_rebalance.py, test_paper.py, 14-01-SUMMARY.md
- Commits verified: c6169ef, 5e51cf8, a300ac9, d4fcc48

