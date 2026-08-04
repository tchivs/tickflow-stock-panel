---
phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)
review: code-review
status: clean
reviewed_commits:
  - c6169ef feat(14-01): RebalancePlan lot-sizing adapter + plan builder
  - 5e51cf8 feat(14-01): paper-rebalance state machine with no-execution contract
  - a300ac9 test(14-01): tracer end-to-end RebalancePlan → paper-fill spine + state-machine breadth
  - d4fcc48 fix(14-01): deterministic min_cash restore + odd-lot validation in lot-sizing adapter
  - 965d0dd test(14-03): lot-sizing adapter breadth cases
  - 0f62e9b feat(14-04): paper_fill values discrete lots through MatcherConfig fees + reject/expired guards
  - e4a7a9d test(14-04): paper state-machine breadth + no-execution-route regression gate
  - 9823e26 test(14-05): robustness + reporting breadth (run gate, checksum read, unwrap)
  - 5f310d8 feat(14-02): rebalance_plans + paper_rebalance_transitions migration
  - 1e12378 feat(14-02): PortfolioRepository rebalance/paper append-only methods
  - ac5b4cc fix(14): CR-14-01 forward odd_lot_positions/min_cash/rmse_definition through build_rebalance_plan
reviewed: 2026-08-02
---

# Phase 14 Code Review — Output & Boundary (RebalancePlan + Paper Rebalance)

## Files Reviewed

- `backend/app/portfolio/rebalance.py` — RebalancePlan lot-sizing adapter (engine.py formula reuse, build/load plan)
- `backend/app/portfolio/paper.py` — paper-rebalance state machine (suggest → approve/reject → fill)
- `backend/app/portfolio/repository.py` — rebalance_plans + paper_rebalance_transitions append-only methods
- `backend/app/operational/migrations.py` — Phase 14 migration script (both tables, triggers, UNIQUE idempotency)
- `backend/tests/portfolio/test_rebalance.py`, `test_paper.py`, `conftest.py` — locked contracts

## Verdict: clean (0 BLOCKER, 0 WARNING open, 4 INFO accepted)

The zero-execution-authority invariant HOLDS. The lot-sizing adapter correctly reuses the engine.py lot formula, the run-gate + checksum-read fail-closed paths are correct, the audit ledger is append-only with UNIQUE (plan_id, transition) idempotency at both the DB and repository level, and the paper state machine never writes positions. CR-14-01 (WARNING: odd-lot/min-cash/RMSE inputs not forwarded through `build_rebalance_plan`) was FIXED in `ac5b4cc` — the run-bound entry point now forwards `odd_lot_positions` / `min_cash` / `rmse_definition` to `discretize_weights`, with a tracer-level test proving the odd-lot carry + min_cash restore + weighted RMSE reach the rendered plan. Four INFO observations accepted as-is.

## Findings

| ID | Severity | File | Line | Description | Fix |
|----|----------|------|------|-------------|-----|
| CR-14-01 | WARNING | app/portfolio/rebalance.py | `build_rebalance_plan` (signature + the `discretize_weights(...)` call) | **FIXED in `ac5b4cc`.** `build_rebalance_plan` previously hardcoded `odd_lot_positions=None`, `min_cash=0.0`, `rmse_definition="simple"` and did NOT accept them from the caller, so the only plan-rendering path silently ignored researcher odd-lot positions / min_cash. Now forwards all three to `discretize_weights`; `test_build_rebalance_plan_forwards_adapter_inputs` locks odd-lot carry (`lot_sizes % 100 == 50`), min_cash restore (`cash_residue >= min_cash`), and weighted RMSE selection through the rendered plan. | FIXED — no action. |
| CR-14-02 | INFO | app/portfolio/paper.py | `paper_fill` | `fill_valuation` / `fill_value` are computed and attached to the returned record but are NOT persisted — the audit fact stores `paper_position_delta_json` = {symbol: shares} only. The valuation is a deterministic derived reference (MatcherConfig fees), recomputable by consumers. Matches the plan's locked `paper_position_delta_json == {symbol: shares}` contract. | Acceptable as-is; document that the fill VALUE is derived, not persisted. |
| CR-14-03 | INFO | app/portfolio/paper.py | `_require_not_expired` | `datetime.fromisoformat(plan["expires_at"])` compared against aware `datetime.now(UTC)` — a naive `expires_at` (no tz) would raise `TypeError` instead of a clean `ValueError`. The DB CHECK does not enforce tz-awareness on `expires_at`. | Acceptable for local single-user host; consider normalizing `expires_at` to aware ISO at `record_rebalance_plan` (or documenting "expires_at must be tz-aware ISO"). |
| CR-14-04 | INFO | app/portfolio/rebalance.py | `discretize_weights` weighted RMSE | `np.sqrt(np.mean(w_cont * diff**2))` is a variance-weighted RMSE without normalization by `sum(w_cont)`. Definitional choice, documented in the module; deterministic. | None — definitional. |
| CR-14-05 | INFO | app/portfolio/rebalance.py | `load_rebalance_plan` return | Returns `{"plan": row, "content": json.loads(verified_bytes)}` — the re-parsed `content` duplicates row fields, but both derive from the SAME checksum-verified artifact (the row's `output_sha256` gates the read), so no divergence is possible. | None — benign redundancy for the Phase 15 panel. |

## Zero-Execution-Authority Audit (success criterion 3)

- **Source-token gate:** `grep -vE '^\s*(#|""")' app/portfolio/rebalance.py app/portfolio/paper.py | grep -cE '\b(broker|submit|place_order|live_)\b'` → **0**.
- **Positions gate:** `grep -c "INSERT INTO positions" app/portfolio/paper.py` → **0**; `grep -c "INSERT INTO" app/portfolio/paper.py` → **0** (all writes route through `repository.record_paper_transition`).
- **Import audit:** rebalance.py/paper.py import only stdlib + numpy + `MatcherConfig` (backtest/engine.py) + `PortfolioArtifactService` + `PortfolioRepository` — no `requests`/`websocket`/`ccxt`/`bt`/live-client reach.
- **Behavioral gate:** `test_no_execution_route` regression test inspects source (no `INSERT INTO positions`, no live-client import, no `execute`/`submit`/`place_order` method) and asserts the `positions` table row count is UNCHANGED across a full suggestion→approve→fill.
- **Migration:** `paper_rebalance_transitions` is append-only (no_update/no_delete triggers); `UNIQUE (plan_id, transition)`; FK `plan_id → rebalance_plans` ON DELETE RESTRICT.

## Append-Only + Idempotency Audit

- `record_paper_transition` enforces exactly-once at the repository level (matching `idempotency_key` returns the existing row; mismatched key raises `ValueError`) AND at the DB level (`UNIQUE (plan_id, transition)` + `IntegrityError→ValueError` mapping).
- `record_rebalance_plan` validates sha256 (64-hex) + `rmse_definition` enum + required fields before INSERT; duplicate plan id → `ValueError`.
- `get_paper_state` derives the current state from the max-ordinal (id DESC) transition row — correct for the INTEGER-PK ledger.

## Fail-Closed Audit

- `build_rebalance_plan` raises `ValueError` on missing run / `problem_status != "optimal"` / empty `output_weights` (mirrors analyzer L92-95); non-finite weights fail closed.
- `load_rebalance_plan` verifies artifact bytes via `read_artifact(checksum_sha256=output_sha256)` — tamper or missing file raises `ArtifactReadError`.
- Every post-creation paper transition (`approve`/`reject`/`paper_fill`) compares `now` against `expires_at` and raises `ValueError` on expiry.
- `reject` is terminal and mutually exclusive with `approve`; `paper_fill` only from `approved`.

## Lot-Sizing Audit

- `discretize_weights` reuses the engine.py lot formula `floor(allocation / (price * (1 + buy_cost_pct)) / 100) * 100` (engine.py L1158) and the `MatcherConfig` fee model — **no second matcher** (`load_panel`/parquet absent from the plan path).
- Odd-lot full-exit / reduce-below-one-lot / remainder-carry behaviors locked by 14-03 tests; cash residue never reallocated, min_cash restore deterministic (`600000.SH == 49800` trace).
- RMSE computed over the FULL universe incl. blocked (honest `(w_cont - 0)²` contribution), recorded with `rmse_definition`.

## Test-Quality Audit

- Tests defend observable contracts: lot-floor vs engine.py formula, odd-lot full-exit/reduce, cash-residue reference, turnover-cost vs MatcherConfig fees (zero on no-change), RMSE both definitions, run-gate (missing/non-optimal/empty), tampered-artifact → ArtifactReadError, idempotency (matching key returns, mismatched raises), reject-then-approve / fill-before-approve, expired transitions, positions-count-unchanged, and the no-execution regression gate.
- 39 portfolio tests + 14 migration tests green; full suite 1284 passed / 2 skipped.

## Recommended Action

CR-14-01 FIXED (commit `ac5b4cc`, 40 portfolio tests green). INFOs (CR-14-02..CR-14-05) accepted as-is — no further action. Re-run the full suite before `/gsd-verify-work`.
