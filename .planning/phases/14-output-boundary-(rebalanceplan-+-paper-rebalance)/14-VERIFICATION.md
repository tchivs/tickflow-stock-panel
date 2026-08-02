---
phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)
verified: 2026-08-02T22:15:00Z
status: passed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
deferred: []
behavior_unverified_items: []
human_verification: []
---

# Phase 14: Output & Boundary (RebalancePlan + Paper Rebalance) Verification Report

**Phase Goal:** Researchers can render an immutable A-share RebalancePlan from continuous optimizer weights and land suggestions in an auditable paper-rebalance state machine — with zero execution authority as a hard acceptance criterion.
**Verified:** 2026-08-02T22:15:00Z
**Status:** passed
**Re-verification:** No — initial verification (no prior VERIFICATION.md existed)

## Goal Achievement

### Success Criteria

| SC | Success Criterion | Requirement | Evidence (source + test + command) | Satisfied |
|----|-------------------|-------------|-------------------------------------|-----------|
| 1 | Render a RebalancePlan from continuous optimizer weights through the A-share lot-sizing adapter — 100-share lots, odd-lot sell, cash residue, turnover cost, blocked instruments, expiry — as an immutable research-only artifact (O_EXCL + fsync + sha256) with discretization RMSE visible | RBAL-01 | `backend/app/portfolio/rebalance.py` — `discretize_weights` (cash-aware largest-weight-first: `floor(allocation/(price*(1+buy_cost_pct))/100)*100`, odd-lot sell/carry, `_cash_residue()` never reallocated, turnover cost via MatcherConfig buy/sell legs, blocked exclusion, RMSE simple/weighted); `build_rebalance_plan` → `PortfolioArtifactService.write_analysis_artifact` (`os.O_WRONLY|O_CREAT|O_EXCL`, `os.fsync`, `sha256(content).hexdigest()` in `app/portfolio/artifacts.py:210-228`) + `record_rebalance_plan` row binding `optimization_run_id`/`input_snapshot_sha256`/`output_sha256`; tests `test_discretize_weights_lot_floor_matches_engine_formula`, `test_odd_lot_full_exit_sells_entire_position`, `test_odd_lot_reduce_carries_remainder_into_target`, `test_cash_residue_is_deterministic`, `test_turnover_cost_matches_matcher_config_reference`, `test_blocked_instruments_excluded_and_recorded`, `test_expires_at_defaults_to_now_plus_seven_days`, `test_discretization_rmse_simple_and_weighted`, `test_build_rebalance_plan_writes_artifact_and_row`, `test_tracer_rebalance_plan_to_paper_fill_end_to_end`; command `pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q` → 40 passed | YES |
| 2 | Approve or reject a rebalance suggestion in the paper-rebalance state machine; every transition is an append-only audit fact with idempotency | RBAL-02 | `backend/app/portfolio/paper.py` — `create_suggestion`/`approve`/`reject`/`paper_fill`; `backend/app/portfolio/repository.py` — `record_paper_transition` (UNIQUE `(plan_id, transition)` + idempotency-key exactly-once, IntegrityError→ValueError), `get_paper_state` derived from max-ordinal row; migration `app/operational/migrations.py` — `paper_rebalance_transitions` with `UNIQUE (plan_id, transition)`, `no_update`/`no_delete` triggers, transition CHECK enum; tests `test_create_suggestion_records_append_only_fact`, `test_approve_is_idempotent_and_requires_suggested_state`, `test_reject_is_terminal_and_mutually_exclusive_with_approve`, `test_record_paper_transition_idempotent_with_matching_key`, `test_record_paper_transition_mismatched_key_raises`, `test_full_ledger_ordinals_and_previous_state`, `test_reject_and_fill_idempotency_mismatched_key_raises`; command `pytest tests/portfolio/test_paper.py -q` → 40 passed (incl. paper) | YES |
| 3 | No execution route exists anywhere: no API endpoint, UI affordance, or service path can push a RebalancePlan to a live broker | RBAL-01/02 (hard acceptance) | grep gates: `grep -vE '^\s*(#|""")' rebalance.py paper.py | grep -cE '\b(broker|submit|place_order|live_)\b'` → 0; `grep -c "INSERT INTO positions" paper.py` → 0; `grep -c "INSERT INTO" paper.py` → 0 (all writes route through `record_paper_transition`); imports of rebalance.py/paper.py = stdlib + numpy + `MatcherConfig` + `PortfolioArtifactService`/`PortfolioRepository` — no `requests`/`websocket`/`ccxt`/`bt`; no module outside tests imports the plan/paper modules; no API router (`app/main.py` include_router list) references a plan/paper router and `grep -rniE "rebalance_plan|paper_transition|paper_fill" app/api/` → no matches; no frontend exists for Phase 14 (Phase 15); tests `test_paper_fill_writes_only_transition_ledger` (positions count == 0 after fill) and `test_no_execution_route_regression_gate` (source-token inspection + positions row count unchanged across suggestion→approve→fill) and tracer test positions-count assertion | YES |

### Observable Truths (Plan must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Researcher can render a RebalancePlan from continuous Phase 11 optimizer weights through the A-share lot-sizing adapter — 100-share lots, odd-lot sell handling, cash residue, turnover cost, blocked instruments, expiry — as an immutable research-only artifact (O_EXCL + fsync + sha256) with discretization RMSE visible (RBAL-01) | ✓ VERIFIED | `rebalance.py:discretize_weights` implements all listed features; `build_rebalance_plan` writes via `PortfolioArtifactService.write_analysis_artifact` (O_EXCL+fsync+sha256, `artifacts.py:210-228`) and records `rebalance_plans` row; 40 portfolio tests exercise the behavior (lot-floor, odd-lot, cash residue, turnover, blocked, expiry, RMSE, artifact+row, tracer) |
| 2 | The plan path REUSES the proven A-share matching rules from `backtest/engine.py` — the lot formula `floor(allocation / (price * (1 + cost)) / 100) * 100` (engine.py:1158) and the MatcherConfig fee model — never a naive second matcher | ✓ VERIFIED | `rebalance.py` line `int(np.floor(allocation / (price * (1 + buy_cost_pct)) / 100) * 100)` byte-matches `engine.py:1158` `np.floor(allocation / (entry_price * (1 + buy_cost_pct)) / 100) * 100`; imports only `MatcherConfig` from engine; `grep load_panel\|parquet rebalance.py` → NONE; `test_discretize_weights_lot_floor_matches_engine_formula` cross-checks against `_engine_lot_reference` (the engine formula) |
| 3 | Researcher can approve or reject a rebalance suggestion in the paper-rebalance state machine; every transition (suggested/approved/rejected/filled) is an append-only audit fact and approve/reject/fill are idempotent (RBAL-02) | ✓ VERIFIED | `paper.py` four transitions; `repository.record_paper_transition` exactly-once by idempotency key + `UNIQUE (plan_id, transition)`; migration triggers `no_update`/`no_delete`; tests lock idempotent re-approve/re-reject/re-fill, mismatched-key ValueError, reject/approve mutual exclusion, fill-before-approve error, ledger ordinals + `previous_state` |
| 4 | Paper fills NEVER write positions and no execution route exists anywhere — no broker/order/submit/place_order path in the plan or paper modules, no INSERT INTO positions from paper.py (hard acceptance criterion, Phase 14 success criterion 3) | ✓ VERIFIED | grep gates all 0; `paper_fill` writes only via `record_paper_transition`; `test_no_execution_route_regression_gate` inspects source + asserts `positions` count unchanged; `test_paper_fill_writes_only_transition_ledger` asserts positions count == 0; no API router / no external module imports the modules |
| 5 | Every RebalancePlan binds its Phase 11 optimization run via optimization_run_id + input_snapshot_sha256 and reads back checksum-verified from its artifact (audit contract) | ✓ VERIFIED | `build_rebalance_plan` binds `run["id"]` + `run["input_snapshot_sha256"]` + `output_sha256` (descriptor) into the row; `load_rebalance_plan` reads via `read_artifact(checksum_sha256=output_sha256)`; `test_build_rebalance_plan_writes_artifact_and_row`, `test_load_rebalance_plan_checksum_verified_read` (tamper → `ArtifactReadError`), tracer test |
| 6 | Phase 15 can surface plans and paper state through the read/list repository surface (get/list rebalance plans, list paper transitions, derived current state) | ✓ VERIFIED | `repository.py`: `get_rebalance_plan`, `list_rebalance_plans(run_id, limit)`, `get_paper_state`, `list_paper_transitions(plan_id, transition, limit)`; tests `test_list_rebalance_plans_filters_and_caps`, `test_get_rebalance_plan_unwraps_all_json_columns_and_blocked_verbatim`, `test_get_paper_state_derived_from_ledger`, `test_list_paper_transitions_filters_and_caps` |

**Score:** 6/6 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | --------- | ------ | ------- |
| `backend/app/portfolio/rebalance.py` | lot-sizing adapter + RebalancePlan + build/load | ✓ VERIFIED | 408 lines; `DiscretizationResult`, `RebalancePlan`, `discretize_weights`, `build_rebalance_plan`, `load_rebalance_plan`; engine formula + MatcherConfig fees; O_EXCL+fsync+sha256 write; checksum-verified read |
| `backend/app/portfolio/paper.py` | append-only state machine | ✓ VERIFIED | 4 transitions; `_require_not_expired` fail-closed; never writes positions |
| `backend/app/portfolio/repository.py` | rebalance/paper append-only methods | ✓ VERIFIED | `record_rebalance_plan`/`get`/`list`; `record_paper_transition` (UNIQUE idempotency + key check); `get_paper_state`; `list_paper_transitions` |
| `backend/app/operational/migrations.py` | ONE appended script, both tables + triggers + UNIQUE | ✓ VERIFIED | `rebalance_plans` (sha256 CHECKs, FK→optimization_runs, no_update/no_delete triggers) + `paper_rebalance_transitions` (CHECK enum, `UNIQUE (plan_id, transition)`, FK ON DELETE RESTRICT, triggers) |
| `backend/tests/portfolio/conftest.py` | fixtures | ✓ VERIFIED | `fixture_rebalance_run` (recorded optimal run), `fixture_prices`, `fixture_plan_inputs` (blocked/equity/MatcherConfig/odd lots) |
| `backend/tests/portfolio/test_rebalance.py` | RBAL-01 unit + integration | ✓ VERIFIED | 26 tests incl. tracer end-to-end; all pass |
| `backend/tests/portfolio/test_paper.py` | RBAL-02 state-machine cases | ✓ VERIFIED | 16 tests incl. no-execution regression gate; all pass |
| `backend/tests/test_operational_migrations.py` | schema CHECKs, triggers, FK, UNIQUE, forward-only | ✓ VERIFIED | `test_phase14_rebalance_tables_migrate_with_constraints_and_idempotence` passes |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `portfolio/rebalance.py` | `backtest/engine.py` | `MatcherConfig.buy_cost_pct()/sell_cost_pct()` + engine.py:1158 lot formula | ✓ WIRED | `discretize_weights` uses `floor(allocation/(price*(1+buy_cost_pct))/100)*100`; `test_discretize_weights_lot_floor_matches_engine_formula` cross-checks with engine reference |
| `portfolio/rebalance.py` | `portfolio/repository.py` | `get_optimization_run(run_id).output_weights` fail-closed → `record_rebalance_plan` | ✓ WIRED | `build_rebalance_plan` raises on missing/non-optimal/empty; row binds run id + snapshot sha256; tests cover each failure mode |
| `portfolio/rebalance.py` | `portfolio/artifacts.py` | `write_analysis_artifact(subdir='rebalance', filename=f'rebalance-{plan_id}.json')` O_EXCL+fsync+sha256; `read_artifact(checksum_sha256=output_sha256)` | ✓ WIRED | Artifact written + checksum bound to row; tamper → `ArtifactReadError` verified by test |
| `portfolio/paper.py` | `portfolio/repository.py` | `record_paper_transition` (UNIQUE idempotency) + `get_paper_state` | ✓ WIRED | All 4 transitions route through the append-only ledger; state derived from max-ordinal row; tests lock ledger semantics |
| `portfolio/paper.py` | `portfolio/rebalance.py` | `paper_fill` consumes plan `lot_sizes` + prices via MatcherConfig fees, records `paper_position_delta_json` — never positions | ✓ WIRED | `paper_fill` reads `plan["lot_sizes"]`, values via `matcher_config.buy_cost_pct()`, writes `{symbol: shares}` only; no INSERT INTO positions |
| `portfolio/repository.py` | `operational/migrations.py` | `UNIQUE (plan_id, transition)` + no_update/no_delete triggers + FK | ✓ WIRED | DB schema enforces append-only + idempotency; migration test asserts all constraints |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `rebalance.py:build_rebalance_plan` | `output_weights` | `repository.get_optimization_run(run_id)` → Phase 11 run row (real `output_weights` from `fixture_rebalance_run`, recorded via `run_optimization` in conftest) | YES — fail-closed on missing/non-optimal/empty | ✓ FLOWING |
| `rebalance.py:discretize_weights` | `prices`/`equity`/`blocked` | researcher-provided inputs (`fixture_prices`, `fixture_plan_inputs`) | YES — real values consumed into lots/residue/cost/RMSE | ✓ FLOWING |
| `rebalance.py` → artifact | `plan_dict` → JSON bytes | `PortfolioArtifactService.write_analysis_artifact` (canonical JSON) → sha256 | YES — artifact + checksum persisted, read back checksum-verified | ✓ FLOWING |
| `paper.py:paper_fill` | `plan["lot_sizes"]` | `repository.get_rebalance_plan` → plan row `lot_sizes_json` | YES — real discrete lots valued via MatcherConfig fees | ✓ FLOWING |
| `repository.py:record_paper_transition` | `paper_position_delta_json` | `{symbol: shares}` from plan lots | YES — persisted to `paper_rebalance_transitions`; positions untouched | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Portfolio rebalance + paper test suite | `.venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short` | 40 passed in 6.82s | ✓ PASS |
| Phase 14 migration contract | `.venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short -k phase14` | 1 passed (13 deselected) | ✓ PASS |
| Execution-token gate | `grep -vE '^\s*(#|""")' rebalance.py paper.py | grep -cE '\b(broker|submit|place_order|live_)\b'` | 0 | ✓ PASS |
| Positions-INSERT gate | `grep -c "INSERT INTO positions" paper.py` | 0 | ✓ PASS |
| No-INSERT gate (paper.py) | `grep -c "INSERT INTO" paper.py` | 0 | ✓ PASS |
| No second matcher | `grep -nE "load_panel|parquet" rebalance.py` | NONE | ✓ PASS |
| Live-client import gate | `grep -nE "import (requests|websocket|ccxt|bt)" rebalance.py paper.py` | NONE | ✓ PASS |
| API-surface gate | `grep -rniE "rebalance_plan|paper_transition|paper_fill" app/api/` | no matches | ✓ PASS |
| Module-consumer gate | `grep -rn "from app.portfolio.rebalance/paper import" app/` (non-test) | no matches | ✓ PASS |

### Probe Execution

No probe scripts are declared by this phase's PLAN/SUMMARY (`grep -R "probe-" 14-PLAN.md 14-*.SUMMARY.md` → none). Behavioral gates above (pytest + grep) serve as the runnable checks. **N/A.**

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| RBAL-01 | 14-01..14-05 | RebalancePlan from continuous weights via A-share lot-sizing adapter — 100-share lots, odd-lot sell, cash residue, turnover cost, blocked, expiry — immutable artifact with discretization RMSE visible | ✓ SATISFIED | `rebalance.py` + `build_rebalance_plan`/`load_rebalance_plan` + artifact O_EXCL/fsync/sha256 + 26 rebalance tests + migration table |
| RBAL-02 | 14-01..14-05 | Rebalance suggestions land in an auditable paper-rebalance state machine (append-only audit fact, human approval, idempotency) with no execution route anywhere | ✓ SATISFIED | `paper.py` + `record_paper_transition` UNIQUE idempotency + append-only triggers + 16 paper tests + no-execution gate |

**Orphaned requirements:** none — both in-scope requirements (RBAL-01, RBAL-02) are claimed by the plan and verified.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | TBD/FIXME/XXX/HACK/PLACEHOLDER in phase source | none found | — |
| — | — | Stub returns (`return {}`/`return []`/`return null`) in plan/paper | none found | — |
| — | — | `INSERT INTO positions` reachable from plan/paper path | none (the single app-wide `positions` INSERT lives in `app/operational/repository.py`, a legacy manual-position manager unreachable from the plan/paper modules) | — |

### Human Verification Required

None. Every must-have truth is behaviorally exercised by the 40-test portfolio run + the Phase 14 migration test; no state-transition or cancellation/cleanup/ordering invariant is left to symbol-presence inference.

### Gaps Summary

No gaps. All 6 plan must-have truths VERIFIED, both success-criteria requirements satisfied, and the zero-execution-authority hard acceptance criterion holds across source tokens, DB writes, imports, API surface, and runtime behavior (positions row count unchanged). The four INFO-level review observations (CR-14-02..CR-14-05: fill valuation not persisted, naive-`expires_at` tz caveat, weighted-RMSE normalization choice, `load_rebalance_plan` benign redundancy) were accepted as-is by the clean code review and do not affect the phase contract.

## Verdict

Phase 14 achieves its goal. Researchers can render an immutable A-share RebalancePlan from continuous Phase 11 optimizer weights through the lot-sizing adapter (100-share lots, odd-lot sell/carry, cash residue, turnover cost, blocked exclusion, expiry, RMSE simple/weighted) as an O_EXCL+fsync+sha256 artifact bound to `rebalance_plans` by `optimization_run_id` + `input_snapshot_sha256` + `output_sha256`, and land suggestions in the paper-rebalance state machine (suggested → approve/reject → filled) where every transition is an append-only, UNIQUE-idempotent audit fact. The plan path reuses the engine.py lot formula and MatcherConfig fee model — no second matcher. Paper fills write only `paper_rebalance_transitions` and never positions; no API endpoint, UI affordance, or service path can push a plan to a live broker. Run fail-closed (missing/non-optimal/empty weights) and checksum-verified read (tamper → `ArtifactReadError`) are enforced and tested. **Status: passed (6/6 must-haves, 2/2 requirements, 3/3 success criteria).**

---

_Verified: 2026-08-02T22:15:00Z_
_Verifier: Claude (gsd-verifier, Phase14Verifier)_
