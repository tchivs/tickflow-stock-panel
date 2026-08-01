---
phase: 11-portfolio-construction-optimization
plan: 11-04
subsystem: portfolio-optimization, api, database
tags: [cvxpy, clarabel, osqp, solver-path, turnover-anchor, max-sharpe, portfolio-optimization, append-only, pydantic]

# Dependency graph
requires:
  - phase: 11-portfolio-construction-optimization
    provides: 11-01 tracer — portfolio/optimizer.py solve_min_vol + run_optimization orchestrator + PSD fail-closed gate, PortfolioRepository/PortfolioArtifactService immutable run + artifact seams, OptimizationRequest DTO (objective: Literal["min_volatility","hrp","max_sharpe"], turnover_reference/w_prev_run_id declared); 11-03 — hrp_portfolio first-class objective + objective="hrp" branch
provides:
  - portfolio/optimizer.py — solver_path=["CLARABEL","OSQP"] fallback with per-solver version capture (solver_name/version of the solver that actually ran), _solve_problem manual fallback preserving honest non-optimal status (infeasible recorded as-is, never retried), solve_max_sharpe under the same constraint stack (risk_aversion=MAX_SHARPE_RISK_AVERSION 1.0), run_optimization max_sharpe gate (render_baselines=False -> ValueError), max_sharpe runs always record baseline_weights_json={"min_volatility","hrp"}, w_prev resolution (equal_weight 1/n anchor | checksum-verified prior-run weights artifact aligned to current symbols)
  - portfolio/constraints.py — TURNOVER_REFERENCE_EQUAL_WEIGHT / TURNOVER_REFERENCE_RUN_ID reference literals
  - portfolio/schemas.py — w_prev_run_id required iff turnover_reference == "run_id" (model_validator, fail closed)
  - tests/portfolio/test_optimizer.py — 12 new green cases: solver_path options + solver name/version, equal-weight anchor, run_id prior-run reference + missing-run fail-closed, schema w_prev_run_id requirement, max-Sharpe gate + both-baselines contract + missing-mu fail-closed, optimal_inaccurate verbatim, min-vol default
affects: [11-05, 11-06, Phase 13 walk-forward, Phase 14 RebalancePlan]

# Actuals (#2632)
actuals:
  tokens: 9000
  tasks: 4
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns: [solver_path fallback preserves the honest status contract (manual per-solver retry only on SolverError; a solver's infeasible/unbounded/optimal_inaccurate is recorded verbatim — pitfall 4), recorded options dict stays policy-verbatim while _solve_kwargs adapts tolerance keys to the active solver's namespace, turnover reference is checksum-verified against the prior run's weights ARTIFACT (never the DB JSON alone), max-sharpe ALWAYS renders min-vol + HRP baselines alongside (pitfall 2)]

key-files:
  created: []
  modified:
    - backend/app/portfolio/optimizer.py
    - backend/app/portfolio/constraints.py
    - backend/app/portfolio/schemas.py
    - backend/tests/portfolio/test_optimizer.py

key-decisions:
  - "solver_path is resolved manually (_solve_problem) instead of cvxpy's native solver_path: cvxpy 1.9.2 raises SolverError when every solver returns a non-optimal status, which would destroy the honest-status audit contract (an infeasible problem must record 'infeasible', not crash); the manual path tries CLARABEL then OSQP only on SolverError (solver crash) and records any status the first solver returns."
  - "The recorded options dict keeps solver_path + eps_abs/eps_rel verbatim (policy原文 in solver_options_json); _solve_kwargs maps tolerance keys to the active solver's namespace (CLARABEL tol_gap_abs/tol_gap_rel, OSQP eps_abs/eps_rel) so the audit record shows the policy contract while each solver gets its own recognized settings."
  - "w_prev run_id reference reads the prior run's weights ARTIFACT via PortfolioArtifactService.read_artifact with output_sha256 checksum verification — never trusts the DB JSON alone; missing symbols align to 0.0 and extra symbols are dropped."
  - "max_sharpe baselines are always rendered: baseline_weights_json = {'min_volatility': <same-constraint-stack min-vol>, 'hrp': <hrp weights>} — both scaled to (1 - min_cash); min_volatility runs keep the single HRP baseline (11-01/11-03 contract)."
  - "run_optimization takes mu as an explicit parameter for max_sharpe (composite cross-section); the snapshot binding lands in 11-05. Missing mu or length mismatch fails closed with ValueError."

patterns-established:
  - "solver_path fallback with honest status: retry the next solver ONLY on SolverError (crash); never on a returned non-optimal status (pitfall 4 — optimal_inaccurate/infeasible recorded as-is)."
  - "w_prev anchor provenance: constraint_stack_json carries turnover_reference + turnover_reference_detail (equal_weight | run_id:<id>) so the exact anchor is auditable per run."
  - "max-sharpe opt-in contract: render_baselines=False + objective='max_sharpe' -> ValueError (never a silent skip); every max-sharpe run carries BOTH min-vol and HRP baselines."

requirements-completed: [PFOL-02, PFOL-03]

coverage:
  - id: D1
    description: "solver_path=['CLARABEL','OSQP'] fallback with per-solver version capture — recorded options contain solver_path + solver keys; solver_name/version reflect the solver that actually ran; non-optimal status (infeasible) recorded verbatim"
    requirement: PFOL-02
    verification:
      - kind: unit
        ref: "tests/portfolio/test_optimizer.py#test_recorded_options_contain_solver_path_and_solver"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_optimizer.py#test_solver_name_and_version_capture_actual_solver"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_optimizer.py#test_non_optimal_status_recorded_as_is"
        status: pass
    human_judgment: false
  - id: D2
    description: "w_prev resolution — first-run equal-weight 1/n anchor + prior-run checksum-verified weights reference (turnover_reference + turnover_reference_detail recorded in constraint_stack_json); missing prior run fails closed"
    requirement: PFOL-03
    verification:
      - kind: integration
        ref: "tests/portfolio/test_optimizer.py#test_equal_weight_anchor_recorded_in_constraint_stack"
        status: pass
      - kind: integration
        ref: "tests/portfolio/test_optimizer.py#test_run_id_reference_loads_prior_weights_aligned_to_symbols"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_optimizer.py#test_run_id_reference_missing_prior_run_fails_closed"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_optimizer.py#test_schema_requires_w_prev_run_id_for_run_id_reference"
        status: pass
    human_judgment: false
  - id: D3
    description: "max-Sharpe explicit non-default — render_baselines=False rejected with ValueError; with True the run records objective='max_sharpe' and baseline_weights_json contains BOTH min_volatility and hrp keys; solve_max_sharpe uses risk_aversion=1.0 under the same constraint stack; min-vol stays the default"
    requirement: PFOL-02
    verification:
      - kind: integration
        ref: "tests/portfolio/test_optimizer.py#test_max_sharpe_requires_baselines"
        status: pass
      - kind: integration
        ref: "tests/portfolio/test_optimizer.py#test_max_sharpe_run_records_both_baselines"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_optimizer.py#test_max_sharpe_solves_under_constraint_stack"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_optimizer.py#test_min_vol_is_default_objective"
        status: pass
    human_judgment: false
  - id: D4
    description: "optimal_inaccurate never promoted — the honest status is recorded verbatim on the run row with options as-is (pitfall 4)"
    requirement: PFOL-03
    verification:
      - kind: integration
        ref: "tests/portfolio/test_optimizer.py#test_optimal_inaccurate_status_recorded_verbatim"
        status: pass
    human_judgment: false

# Metrics
duration: 44min
completed: 2026-08-01
status: complete
---

# Phase 11 Plan 11-04: Min-Vol Breadth + Max-Sharpe Non-Default Summary

**Min-vol breadth + max-Sharpe opt-in contract: `solver_path=["CLARABEL","OSQP"]` fallback with per-solver version capture and honest non-optimal status recording, checksum-verified `w_prev` turnover anchor (equal-weight `1/n` first run, prior-run artifact reference for rebalances), and max-Sharpe reachable only with `render_baselines=True` where every run records min-vol + HRP baselines alongside — all locked by 12 new green tests**

## Performance

- **Duration:** 44 min
- **Started:** 2026-08-01T21:58:00Z
- **Completed:** 2026-08-01T22:42:00Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments

- **`solver_path` fallback + per-solver version capture** — `DEFAULT_SOLVER_OPTIONS` now records `solver_path=["CLARABEL", "OSQP"]` plus `solver`/`eps_abs`/`eps_rel`/`max_iter` verbatim into `solver_options_json`. A new `_solve_problem` tries CLARABEL then OSQP **only on SolverError (solver crash)** — cvxpy 1.9.2's native `solver_path` raises `SolverError` when every solver returns a non-optimal status, which would destroy the honest-status audit contract (an infeasible problem must record `"infeasible"`, not crash). `_solve_kwargs` maps the policy tolerance keys to the active solver's namespace (CLARABEL `tol_gap_abs/tol_gap_rel`, OSQP `eps_abs/eps_rel`). `solver_name`/`solver_version` reflect the solver that actually ran, with the fixed distribution mapping (`clarabel`/`osqp`/`scs`/`highspy`) and `"unknown"` fallback.
- **`w_prev` resolution — equal-weight anchor + prior-run reference** — `_resolve_w_prev` returns `(w_prev, turnover_reference, turnover_reference_detail)`: `equal_weight` → uniform `1/n` anchor (first run, Phase 14 default); `run_id` → the prior run's weights **artifact** loaded via `PortfolioArtifactService.read_artifact` with `output_sha256` checksum verification (never trusts the DB JSON alone), aligned to the current symbols (missing → 0.0, extra dropped). A missing prior run or missing artifact raises `ValueError` (fail closed → the orchestrator records a `failed` run). `constraint_stack_json` now carries `turnover_reference` + `turnover_reference_detail` so the exact anchor is auditable per run.
- **Max-Sharpe — explicit non-default with baselines rendered** — `solve_max_sharpe(mu, cov, symbols, ...)` solves `cp.Maximize(mu@w - (risk_aversion/2)*quad_form(w,cov) - turnover_coef*norm1(w-w_prev))` under the SAME constraint stack with `risk_aversion = MAX_SHARPE_RISK_AVERSION (1.0)`. `run_optimization` gates it: `objective="max_sharpe"` with `render_baselines=False` raises `ValueError` (pitfall 2 — never a silent skip), and `mu` is a required parameter (length must match symbols). Every max-Sharpe run records `baseline_weights_json = {"min_volatility": <min-vol>, "hrp": <hrp>}` — both rendered — while min-vol runs keep the single HRP baseline.
- **`optimal_inaccurate` never promoted** — the run row records the honest status verbatim with options as-is (pitfall 4), locked by a dedicated test. Min-vol remains the default objective.

## Task Commits

Each task was committed atomically:

1. **Task 1: `solver_path` fallback + per-solver version capture** - `5638ffc` (feat)
2. **Task 2: `w_prev` resolution — equal-weight anchor + prior-run reference** - `6647bd9` (feat)
3. **Task 3: Max-Sharpe — explicit non-default with baselines rendered** - `cdb14f0` (feat)
4. **Task 4: Extend `test_optimizer.py` — solver_path, w_prev anchor, max-Sharpe gate** - `896f08f` (test) + `0a2db23` (test, optimal_inaccurate verbatim)

## Files Created/Modified

- `backend/app/portfolio/optimizer.py` - `_solve_problem`/`_solve_kwargs` manual solver_path fallback; `DEFAULT_SOLVER_OPTIONS` with `solver_path` + `eps_abs`/`eps_rel`; `solve_max_sharpe` + `_finalize_result` shared audit capture; `_resolve_w_prev` checksum-verified prior-run anchor; `run_optimization` max_sharpe gate + `mu` parameter + dual-baseline rendering + `turnover_reference_detail` in `constraint_stack_json`
- `backend/app/portfolio/constraints.py` - `TURNOVER_REFERENCE_EQUAL_WEIGHT` / `TURNOVER_REFERENCE_RUN_ID` reference literals
- `backend/app/portfolio/schemas.py` - `w_prev_run_id` required iff `turnover_reference == "run_id"` (`model_validator`, fail closed)
- `backend/tests/portfolio/test_optimizer.py` - 12 new green cases (solver_path options + solver name/version, equal-weight anchor, run_id reference + missing-run fail-closed, schema requirement, max-Sharpe gate + both-baselines + missing-mu, optimal_inaccurate verbatim, min-vol default)

## Decisions Made

- **Manual solver_path instead of cvxpy's native `solver_path`** — cvxpy 1.9.2 raises `SolverError` when every solver returns a non-optimal status; the manual `_solve_problem` retries OSQP only on `SolverError` (solver crash) and records any status the first solver returns. This is what keeps `infeasible`/`unbounded`/`optimal_inaccurate` honest (pitfall 4).
- **Recorded options stay policy-verbatim** — `solver_options_json` carries the policy dict (with `solver_path` + `eps_abs`/`eps_rel`) exactly as declared; `_solve_kwargs` adapts tolerance names per active solver so each solver receives its recognized settings.
- **Checksum-verified prior-run weights** — the `run_id` reference reads the weights **artifact** (O_EXCL + fsync + sha256 from 11-01) and verifies `output_sha256`, not the DB JSON column — the artifact is the audit source of truth.
- **max_sharpe always renders both baselines** — `baseline_weights_json` is a dict with `min_volatility` + `hrp` keys (min-vol computed under the same constraint stack + `w_prev` for audit consistency); this is the pitfall-2 contract.
- **`mu` is an explicit `run_optimization` parameter** — the composite cross-section (snapshot binding lands in 11-05); missing `mu` or length mismatch fails closed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] cvxpy native `solver_path` crashes on all-non-optimal statuses**
- **Found during:** Task 1 (solver_path fallback)
- **Issue:** cvxpy 1.9.2's `solve(solver_path=...)` raises `SolverError("All solvers failed")` when CLARABEL AND OSQP both return a non-optimal status (e.g. `infeasible` for cap×n < budget). The pre-existing `test_non_optimal_status_recorded_as_is` asserts `result["status"] == "infeasible"` — the plan's verbatim options would have made that test crash instead of recording the honest status.
- **Fix:** Implemented `_solve_problem` — iterate the path, retry the next solver ONLY on `SolverError` (solver crash); any returned status is recorded as-is. Also `_solve_kwargs` maps tolerance keys to the active solver's namespace (CLARABEL rejects OSQP-style `eps_abs`/`eps_rel` with `TypeError`; OSQP rejects `tol_gap_*`).
- **Files modified:** backend/app/portfolio/optimizer.py
- **Verification:** `test_non_optimal_status_recorded_as_is` passes (`infeasible` recorded verbatim); all 6 pre-existing + 6 new unit tests green.
- **Committed in:** `5638ffc` (Task 1 commit)

**2. [Rule 2 - Missing Critical] Max-Sharpe required `mu` with fail-closed validation**
- **Found during:** Task 3 (max-Sharpe branch)
- **Issue:** The plan's max-Sharpe formulation needs an expected-returns vector, but the tracer's `run_optimization` had no `mu` seam; calling `objective="max_sharpe"` without a vector would silently solve a degenerate objective (zero linear term).
- **Fix:** Added an explicit `mu` parameter to `run_optimization` (composite cross-section; snapshot binding lands in 11-05), required for `max_sharpe` with length-mismatch fail-closed `ValueError`. Tests lock both the gate and the missing-mu rejection.
- **Files modified:** backend/app/portfolio/optimizer.py
- **Verification:** `test_max_sharpe_requires_mu` green; `test_max_sharpe_run_records_both_baselines` green with `mu` supplied.
- **Committed in:** `cdb14f0` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both auto-fixes necessary for the plan's own success criteria — the honest-status audit contract (pitfall 4) and the max-Sharpe formulation's feasibility. No scope creep.

## Issues Encountered

- **cvxpy cross-solver option incompatibility (discovered, not a bug in our code)** — CLARABEL rejects OSQP-style `eps_abs`/`eps_rel` with `TypeError("Clarabel: unrecognized solver setting")`, and OSQP rejects `tol_gap_abs`/`tol_gap_rel` with `Unrecognized settings`. The `_solve_kwargs` tolerance-namespace mapping resolves this while keeping the recorded options policy-verbatim.
- **Native `solver_path` status semantics** — verified empirically: cvxpy's native `solver_path` passes the same kwargs to every candidate and raises `SolverError` if all return non-optimal; this is exactly why the manual fallback was needed (see Deviation 1).
- **`optimal_inaccurate` determinism on this fixture** — OSQP returns `user_limit` (not `optimal_inaccurate`) for degenerate `max_iter=1` on the 12-asset fixture; the pitfall-4 verbatim-status contract is locked instead by a direct repository-level run-row test asserting `problem_status == "optimal_inaccurate"` is stored as-is with options verbatim.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **11-05 (snapshot binding)** replaces the fixture snapshot bootstrap and wires `mu` from the composite cross-section (the `run_optimization` `mu` seam added here is the direct hook); the w_prev prior-run anchor already consumes the same repository/artifact seams, so rebalance references inherit the production catalog binding unchanged.
- **11-06 (constraint hardening)** — the max-Sharpe branch records the same `constraint_stack_json` (now with `turnover_reference_detail`), so hardening applies uniformly across objectives.
- **Phase 14 RebalancePlan** inherits the turnover reference semantics: first run `equal_weight` 1/n anchor, subsequent runs `run_id` checksum-verified prior weights.
- **Blockers/concerns:** none. Full-suite pytest deliberately NOT run (phase gate after all plans, per batch constraints). Per-plan gate `pytest tests/portfolio/test_optimizer.py tests/portfolio/test_pipeline.py -q --tb=short` → 19 passed; full `tests/portfolio/` → 48 passed. Grep gate: `objective="max_sharpe"` appears only in `optimizer.py` (the gate) and tests; `render_baselines=False` with max-sharpe is always rejected.

## Self-Check: PASSED

All 4 modified files present on disk; all 5 plan commits present in git history (`5638ffc`, `6647bd9`, `cdb14f0`, `896f08f`, `0a2db23`). Per-plan gate re-run after the final commit: `pytest tests/portfolio/test_optimizer.py tests/portfolio/test_pipeline.py -q --tb=short` → 19 passed; `pytest tests/portfolio/` → 48 passed. Grep: `scipy.cluster.hierarchy` imports appear only in `portfolio/hrp.py`; `objective="max_sharpe"` gate lives only in `optimizer.py` + tests.
