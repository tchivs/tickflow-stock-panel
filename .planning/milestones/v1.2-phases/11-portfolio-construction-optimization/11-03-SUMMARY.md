---
phase: 11-portfolio-construction-optimization
plan: 11-03
subsystem: portfolio-optimization, risk, api
tags: [hrp, scipy, clustering, portfolio-optimization, append-only, determinism, pydantic]

# Dependency graph
requires:
  - phase: 11-portfolio-construction-optimization
    provides: 11-01 tracer — portfolio/hrp.py (hrp_weights/render_baseline over scipy single-linkage optimal_ordering), portfolio/optimizer.py run_optimization orchestrator + PSD fail-closed gate, PortfolioRepository/PortfolioArtifactService immutable run + artifact seams, OptimizationRequest DTO with objective: Literal["min_volatility","hrp","max_sharpe"]
provides:
  - portfolio/hrp.py — hrp_portfolio(cov, *, min_cash, symbols): first-class HRP objective, PSD-gated, renders (1 - min_cash)-scaled weights, returns {weights, status: optimal, solver_name: n/a}
  - portfolio/optimizer.py — objective="hrp" branch in run_optimization: persists weights through write_bundle, records append-only run row with solver_name/solver_version="n/a" and solver_options_json={}
  - tests/portfolio/test_hrp.py — 6 new green cases: objective-path scaling/bounds, audit record shape, determinism, pitfall-9 fail-closed, symbol-length guard
affects: [11-04, 11-05, 11-06, Phase 13 walk-forward, Phase 14 RebalancePlan]

# Actuals (#2632)
actuals:
  tokens: 2634
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns: [first-class non-solver objective keeps the audit contract (solver_name="n/a" + problem_status="optimal" in the immutable run row), HRP baseline rendering scaled by (1 - min_cash) reused as the objective output itself, PSD gate runs before HRP recursion (pitfall 9: negative diagonal breaks inverse-variance)]

key-files:
  created: []
  modified:
    - backend/app/portfolio/hrp.py
    - backend/app/portfolio/optimizer.py
    - backend/tests/portfolio/test_hrp.py

key-decisions:
  - "HRP objective outputs the rendered baseline as both output_weights and baseline_weights: an objective='hrp' run has no min-vol QP to compare against, so baseline == output is the honest shape (record still immutable)."
  - "hrp_portfolio runs the same fail-closed PSD gate as the QP path: a non-PSD covariance raises ValueError('PSD repair provenance missing') instead of producing meaningless inverse-variance weights (pitfall 9)."
  - "solver_version recorded as 'n/a' alongside solver_name='n/a' and solver_options_json={} so the audit fields stay uniform across objectives — no version to record because no solver ran."

patterns-established:
  - "Non-solver objective audit shape: solver_name='n/a' + solver_version='n/a' + solver_options_json={} + problem_status='optimal' in the immutable append-only run record (PFOL-02/04)."
  - "HRP rendering contract: render_baseline(hrp_weights(cov), min_cash).round(8) is the single scaling path — used both for the min-vol baseline_weights_json and as the hrp objective's output."

requirements-completed: [PFOL-02]

coverage:
  - id: D1
    description: "portfolio/hrp.py hrp_portfolio — first-class HRP objective producing (1 - min_cash)-scaled deterministic weights in [0,1] with status optimal and solver_name n/a"
    requirement: PFOL-02
    verification:
      - kind: unit
        ref: "tests/portfolio/test_hrp.py#test_hrp_portfolio_scales_to_one_minus_min_cash"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_hrp.py#test_hrp_portfolio_is_auditable_without_solver"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_hrp.py#test_hrp_portfolio_deterministic_across_calls"
        status: pass
    human_judgment: false
  - id: D2
    description: "portfolio/optimizer.py objective='hrp' branch — immutable append-only run row (solver_name/solver_version='n/a', solver_options_json={}, baseline == output) with checksum-verified weights artifact"
    requirement: PFOL-02
    verification:
      - kind: integration
        ref: "tests/portfolio/test_hrp.py#test_hrp_objective_run_record_shape"
        status: pass
      - kind: integration
        ref: "tests/portfolio/test_pipeline.py (min-vol run still renders the HRP baseline)"
        status: pass
    human_judgment: false
  - id: D3
    description: "HRP determinism / [0,1] bounds / cluster-ordering guarantees locked by green tests"
    requirement: PFOL-02
    verification:
      - kind: unit
        ref: "tests/portfolio/test_hrp.py (11 passed, incl. cluster ordering, determinism, unit-sum-then-scaled, [0,1] bounds)"
        status: pass
    human_judgment: false

# Metrics
duration: 21min
completed: 2026-08-01
status: complete
---

# Phase 11 Plan 11-03: HRP Baseline Breadth Summary

**HRP promoted from a rendered side-baseline to a first-class auditable objective: `hrp_portfolio` produces deterministic (1 − min_cash)-scaled weights in [0,1] with an immutable run record (`objective="hrp"`, `problem_status="optimal"`, `solver_name/solver_version="n/a"`, `solver_options_json={}`) — no solver call, same audit contract as min-vol; determinism, bounds, cluster ordering, and the pitfall-9 PSD fail-closed gate locked by 11 green tests**

## Performance

- **Duration:** 21 min
- **Started:** 2026-08-01T21:28:00Z
- **Completed:** 2026-08-01T21:49:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- **`hrp_portfolio` first-class objective** — `hrp_portfolio(cov, *, min_cash, symbols)` runs the PSD gate first (pitfall 9: a negative diagonal breaks `_cluster_weights` inverse-variance), computes deterministic `hrp_weights`, scales by `(1 - min_cash)` via the same `render_baseline` used for min-vol side-baselines, rounds to 8dp, and returns `{"weights", "status": "optimal", "solver_name": "n/a"}`. A symbol-length mismatch is rejected with a clear `ValueError`.
- **`objective="hrp"` run path in `run_optimization`** — the orchestrator now branches on the objective: HRP weights are persisted through `PortfolioArtifactService.write_bundle` (O_EXCL + fsync + sha256) and recorded as an append-only immutable run row with `objective="hrp"`, `problem_status="optimal"`, `solver_name="n/a"`, `solver_version="n/a"`, `solver_options_json={}`, and `baseline_weights == output_weights` (the HRP output is itself the rendered baseline — there is no QP to compare against). No solver is invoked.
- **Determinism / bounds / ordering locked by tests** — 6 new green cases in `test_hrp.py`: objective-path scaling to 0.95 within 1e-8 with [0,1] bounds, output identical to `render_baseline(hrp_weights(...))` (single rendering contract), audit record shape (`solver_name="n/a"` + `optimal` + no solver version), determinism across two calls, indefinite covariance rejected without provenance, and symbol-length mismatch rejected. The 5 existing 11-01 cases (cluster ordering of the correlated pair, unit sum, scaling, determinism, bounds) remain green.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add `hrp_portfolio` + the `objective="hrp"` run path** - `664d250` (feat)
2. **Task 2: Extend `test_hrp.py` — objective path, baseline scaling, determinism** - `a7b0d80` (test)

## Files Created/Modified

- `backend/app/portfolio/hrp.py` - added `hrp_portfolio` (PSD-gated first-class HRP objective); imports `check_psd` + `PSD_EPSILON_DEFAULT`
- `backend/app/portfolio/optimizer.py` - added the `objective="hrp"` branch in `run_optimization` (write_bundle + append-only run row with `solver_name/version="n/a"`)
- `backend/tests/portfolio/test_hrp.py` - 6 new green cases for the objective path (scaling/bounds, audit shape, determinism, pitfall-9 gate, symbol guard, run-record shape)

## Decisions Made

- **HRP objective outputs baseline == weights** — an `objective="hrp"` run has no min-vol QP, so `baseline_weights_json` equals `output_weights_json`; the honest shape of an HRP-only run.
- **Same fail-closed PSD gate as the QP path** — `hrp_portfolio` raises `ValueError("PSD repair provenance missing")` on a non-PSD covariance rather than emitting meaningless inverse-variance weights (pitfall 9).
- **Uniform audit fields across objectives** — `solver_version="n/a"` and `solver_options_json={}` alongside `solver_name="n/a"` keep the PFOL-04 audit columns filled for every objective.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- **Objective-path test initially failed with a symbol/covariance dimension mismatch** — the run-record test passed `symbols` (3) while the orchestrator defaulted to its 12-asset fixture returns matrix. Fixed by passing a matching 3-asset deterministic returns matrix alongside the 3 symbols (the test now exercises the full covariance → PSD → HRP → run-record path with consistent dimensions). Resolved in the same test task commit; no production code change.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **11-04 (min-vol breadth + max-Sharpe non-default)** can now build the max-Sharpe branch on `run_optimization` and add the `solver_path` fallback / `w_prev` prior-run anchor. The `objective` Literal already includes `"hrp"` (and `"max_sharpe"`) in `schemas.py` and the repository `_OBJECTIVES` set, so the new branch slots in without schema churn.
- **11-05 (snapshot binding)** replaces the fixture snapshot bootstrap; the HRP objective path already consumes the same snapshot/risk/artifact seams, so it inherits the production catalog binding unchanged.
- **11-06 (constraint hardening)** — the HRP objective records the same `constraint_stack_json` (cap/min-cash/turnover) as solver runs, so the hardening and artifact-breadth work applies uniformly.
- **Blockers/concerns:** none. Full-suite pytest deliberately NOT run (phase gate after all plans, per batch constraints). `tests/portfolio` remains green (30 existing + 6 new = 36 passed across the plan gate).

## Self-Check: PASSED

All 3 modified files present on disk; both plan commits present in git history (`664d250`, `a7b0d80`). Plan verification command re-run after the final commit: `pytest tests/portfolio/test_hrp.py tests/portfolio/test_pipeline.py -q --tb=short` → 12 passed. Per-plan gate `pytest tests/portfolio/test_optimizer.py tests/portfolio/test_pipeline.py -q --tb=short` → 7 passed. Grep: `scipy.cluster.hierarchy` imports appear only in `portfolio/hrp.py`; `cp.quad_form` appears only in `portfolio/optimizer.py` (PSD-gated).
