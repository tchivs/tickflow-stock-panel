---
phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)
plan: 14-04
subsystem: portfolio
tags: [paper-rebalance, state-machine, idempotency, reject, expiry, no-execution]

requires: [14-01]
provides:
  - "Paper-rebalance state-machine breadth: reject path (terminal, mutually exclusive with approve), expired-plan fail-closed on EVERY post-creation transition (approve/reject/paper_fill raise ValueError when now > expires_at), idempotent reject (repeated reject returns existing row with matching idempotency_key, raises on mismatch), paper_fill values discrete lots at prices through MatcherConfig fees, and the no-execution-route regression gate (no raw INSERT INTO positions, no live-client import, no execute/submit/place_order method, positions row count unchanged across suggestion→approve→fill)"
affects: [14-05, phase-15]

actuals:
  tokens: 14500
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "paper_fill valuation = shares · price · (1 + buy_cost_pct) via MatcherConfig fee model (REUSE, no second matcher)"
    - "no-execution regression gate: inspect.getsource on paper.py/rebalance.py/repository.py — no INSERT INTO positions, no INSERT INTO in paper.py, only INSERT INTO paper_rebalance_transitions in record_paper_transition"

key-files:
  created: []
  modified:
    - backend/app/portfolio/paper.py
    - backend/tests/portfolio/test_paper.py
  verified:
    - backend/app/portfolio/rebalance.py (no changes — gate only)

key-decisions:
  - "paper_fill returns fill_valuation (per-symbol shares·price·(1+buy_cost_pct)) + fill_value (sum) as deterministic derived references; persisted paper_position_delta_json remains {symbol: shares}"
  - "Reject/approve/fill each check expiry via the shared _require_not_expired guard — fail-closed on every post-creation transition"

patterns-established:
  - "Each RBAL-02 edge is a locked green test: full ledger ordinals + previous_state, idempotency (matching key returns existing row / mismatch raises), reject-then-approve raises, fill-before-approve raises, expired transitions raise ValueError, valuation through MatcherConfig fees, and the no-execution regression gate"

requirements-completed: [RBAL-02]

coverage:
  - id: D1
    description: "Paper-rebalance state machine breadth — reject terminal + mutually exclusive with approve, expired fail-closed on every post-creation transition, idempotent reject, paper-fill valuation through MatcherConfig fees, no-execution-route regression gate"
    requirement: RBAL-02
    verification:
      - kind: unit
        ref: "backend/tests/portfolio/test_paper.py (14 passed)"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-08-02
status: complete
---

# Phase 14 Plan 14-04: Paper-Rebalance State Machine Breadth Summary

**The paper-rebalance state machine's RBAL-02 breadth is locked by 14 green tests: reject is terminal and mutually exclusive with approve, every post-creation transition (approve/reject/paper_fill) fails closed on an expired plan, reject/fill idempotency is exact (matching key returns the existing row, a mismatched key raises), paper fills value the discrete lots at prices through the MatcherConfig fee model, and the zero-execution-authority contract is pinned by an automated no-execution-route regression gate (no raw INSERT INTO positions in paper.py, no live-client import, no execute/submit/place_order method, positions row count unchanged across suggestion→approve→fill).**

## Performance

- **Duration:** 14 min
- **Started:** 2026-08-02T22:10:00Z
- **Completed:** 2026-08-02T22:24:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Extended `backend/app/portfolio/paper.py`: `paper_fill` now values the plan's discrete lots at prices through `MatcherConfig` fees — `valuation = {symbol: round(shares · price · (1 + buy_cost_pct), 4)}` with a derived `fill_value` (sum) returned on the audit record, and a missing-price fail-closed path (a symbol in `lot_sizes` absent from `prices` raises `ValueError`). The persisted `paper_position_delta_json` remains exactly `{symbol: shares}`. `reject` and `paper_fill` docstrings document the expired-plan guard (already enforced via the shared `_require_not_expired` helper on every post-creation transition).
- Extended `backend/tests/portfolio/test_paper.py` from 11 to 14 green tests:
  1. `test_no_execution_route_regression_gate` — now a full regression gate: `inspect.getsource` on `paper.py` + `rebalance.py` asserts no `INSERT INTO positions`, no raw `INSERT INTO` at all, no `broker|submit|place_order|live_` vocabulary, and no live-client import (`requests`/`websocket`/`broker`); the paper module's only public callables are exactly `{create_suggestion, approve, reject, paper_fill}`; `record_paper_transition`'s only INSERT targets `paper_rebalance_transitions` (never positions) and the whole `repository.py` module contains no `INSERT INTO positions`; and a full suggestion→approve→fill on the fixture leaves `SELECT COUNT(*) FROM positions` unchanged (before == after).
  2. `test_full_ledger_ordinals_and_previous_state` — suggestion→approve→filled with strictly increasing ordinals and `previous_state` recorded per transition (`None → suggested → approved`).
  3. `test_reject_and_fill_idempotency_mismatched_key_raises` — repeated reject with the matching key returns the existing row, a different key raises; re-fill is idempotent (deterministic `fill-{plan_id}` key) and a conflicting re-issue at the repository layer raises.
  4. `test_paper_fill_valuation_through_matcher_config_fees` — `paper_position_delta_json == {symbol: shares}` and the fill valuation equals the hand-computed `shares · price · (1 + buy_cost_pct)` reference per symbol (via the REUSED MatcherConfig fee model); a missing price fails closed.
- Verified the existing reject/expired guards (from 14-01) already satisfy the plan's reject-terminal, mutually-exclusive-with-approve, and expired fail-closed requirements — the breadth work is the locked test suite plus the valuation completion.

## Task Commits

1. **paper_fill valuation + reject/expired guard docs** - `0f62e9b` (feat) — `paper_fill` values the discrete lots at prices through MatcherConfig fees (deterministic `fill_valuation` + `fill_value` returned; missing price raises); reject/paper_fill docstrings document the expired fail-closed guard.
2. **Paper state-machine breadth + no-execution gate** - `e4a7a9d` (test) — replaced the RED scaffold breadth section with 14 green tests, including the full no-execution-route regression gate.

## Files Created/Modified

- `backend/app/portfolio/paper.py` - paper_fill valuation through MatcherConfig fees (`valuation = shares·price·(1+buy_cost_pct)`, derived `fill_value`), missing-price fail-closed, docstring updates for reject/expired guards.
- `backend/tests/portfolio/test_paper.py` - Expanded 11 → 14 green tests; strengthened `test_no_execution_route_regression_gate` with live-client import assertion, repository INSERT-target assertion, and the positions-row-count-unchanged end-to-end check; added full-ledger ordinal/previous_state, reject/fill idempotency-mismatch, and MatcherConfig-fee valuation cases.

## Decisions Made

- paper_fill's derived `fill_valuation` / `fill_value` are deterministic audit references (computed via the REUSED MatcherConfig `buy_cost_pct()`), while the persisted `paper_position_delta_json` stays `{symbol: shares}` — the plan's requirement is that the delta equals the discrete lots and that the fill is valued through the fee model.
- Reject/approve/fill each enforce expiry through the shared `_require_not_expired` guard — fail-closed on every post-creation transition (T-14-06 mitigated).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `inspect.getsource` on a repository *instance* raises TypeError**
- **Found during:** no-execution gate authoring
- **Issue:** The gate initially called `inspect.getsource(portfolio_repository)` (an instance), which raises `TypeError: module, class, method, function, traceback, frame, or code object was expected`.
- **Fix:** Asserted against `inspect.getsource(repository_module)` (the imported module) instead — the whole `app.portfolio.repository` module contains no `INSERT INTO positions`.
- **Files modified:** backend/tests/portfolio/test_paper.py
- **Verification:** all 14 tests pass.
- **Committed in:** `e4a7a9d`

---

**Total deviations:** 1 auto-fixed (test bug — getsource on instance)
**Impact on plan:** None — the gate's assertion is unchanged in intent (no `INSERT INTO positions` anywhere in the repository surface).

## Issues Encountered

- None beyond the one auto-fixed test bug.

## User Setup Required

None.

## Next Phase Readiness

- The paper state machine's full RBAL-02 surface is locked by green tests — 14-05 (robustness + reporting breadth: derived `get_paper_state` after each transition, `list_paper_transitions` filters, limit fail-closed) builds on it.

---
*Phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)*
*Completed: 2026-08-02*

## Self-Check: PASSED

- `cd backend && .venv/bin/python -m pytest tests/portfolio/test_paper.py -q --tb=short` → 14 passed.
- No-execution grep gate: `grep -vE '^\s*(#|""")' app/portfolio/paper.py app/portfolio/rebalance.py | grep -cE '\b(broker|submit|place_order|live_)\b'` == 0; `grep -c "INSERT INTO positions" app/portfolio/paper.py` == 0; `grep -c "INSERT INTO" app/portfolio/paper.py` == 0.
- Tree clean after final commit (14-04-SUMMARY.md untracked at time of check).
- `backend/app/portfolio/rebalance.py` and `backend/tests/portfolio/test_rebalance.py` untouched.
