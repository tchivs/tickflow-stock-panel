---
phase: 11-portfolio-construction-optimization
plan: 11-01
subsystem: portfolio-optimization, risk, api
tags: [cvxpy, clarabel, hrp, scipy, sqlite, append-only, pydantic, portfolio-optimization, psd, covariance]

# Dependency graph
requires:
  - phase: 11-portfolio-construction-optimization
    provides: Wave 0 (11-02) foundations — cvxpy 1.9.2 pin, portfolio_optimization_runs append-only table + triggers, PortfolioRepository seam, 6 RED test scaffolds + conftest fixtures
provides:
  - portfolio/schemas.py — strict OptimizationRequest DTO (frozen, min-vol default, baselines default) + SOLVER_OPTIONS_ALLOWLIST (V5)
  - portfolio/risk.py — sample_covariance / check_psd / repair_psd with mandatory PSD provenance (method/epsilon/eigenvalues before/after)
  - portfolio/constraints.py — phase-11-policy-v1 constants (cap 0.10 / min-cash 0.05 / turnover 0.0014 / PSD eps 1e-10) + industry-cap fail-closed gate
  - portfolio/hrp.py — deterministic HRP baseline over scipy linkage (single, optimal_ordering) + render_baseline scaled by (1 - min_cash)
  - portfolio/repository.py — append-only record_optimization_run / get_optimization_run / list_optimization_runs
  - portfolio/artifacts.py — PortfolioArtifactService O_EXCL + fsync + sha256 weight/baseline/covariance bundle + checksum-verified reads
  - portfolio/optimizer.py — ensure_psd_provenance fail-closed gate + solve_min_vol (Clarabel default) + run_optimization orchestrator
  - 5 green test files (test_risk/test_optimizer/test_hrp/test_repository/test_pipeline) proving the end-to-end tracer spine
affects: [11-03, 11-04, 11-05, 11-06, Phase 12 risk suite, Phase 13 walk-forward, Phase 14 RebalancePlan]

# Actuals (#2632)
actuals:
  tokens: 278
  tasks: 12
  commits: 7

# Tech tracking
tech-stack:
  added: []
  patterns: [PSD repair never silent (mandatory provenance in risk_model_json), budget-equality min-vol QP under cap/min-cash/turnover stack, append-only run records with canonical JSON + CHECK guards, O_EXCL+fsync+sha256 immutable weight artifacts, Clarabel tol_gap_abs/tol_gap_rel solver options]

key-files:
  created:
    - backend/app/portfolio/constraints.py
    - backend/app/portfolio/risk.py
    - backend/app/portfolio/hrp.py
    - backend/app/portfolio/schemas.py
    - backend/app/portfolio/artifacts.py
    - backend/app/portfolio/optimizer.py
  modified:
    - backend/app/portfolio/repository.py
    - backend/tests/portfolio/conftest.py
    - backend/tests/portfolio/test_risk.py
    - backend/tests/portfolio/test_optimizer.py
    - backend/tests/portfolio/test_hrp.py
    - backend/tests/portfolio/test_repository.py
    - backend/tests/portfolio/test_pipeline.py

key-decisions:
  - "Min-vol QP uses budget equality cp.sum(w) == 1 - min_cash (fully-deployed floor): the plan prose says <= floor, but the analytical scaffold test (w_i ∝ 1/σ² scaled by 1 - min_cash) and pitfall-7 assertions are only satisfiable with full deployment; the cash floor (1 - sum >= min_cash) still holds exactly."
  - "Clarabel 1.9.2 solver options are tol_gap_abs/tol_gap_rel (not OSQP eps_abs/eps_rel, per Wave 0 finding); options dict recorded verbatim in solver_options_json."
  - "HRP baseline rendered scaled by (1 - min_cash) so it compares apples-to-apples with the QP under the cash floor."
  - "Composite snapshot identity passed as a pre-resolved snapshot dict (model_id/input_snapshot_sha256/composite_snapshot_id) in 11-01; the production catalog seam lands in 11-05."

patterns-established:
  - "PSD provenance contract: repair_psd always returns method/epsilon/min_eigenvalue_before/eigenvalues_before/eigenvalues_after; ensure_psd_provenance raises 'PSD repair provenance missing' when a non-PSD covariance lacks the block (never silent)."
  - "Budget-equality min-vol: constraints = [cp.sum(w) == 1 - min_cash, w <= per_instrument_cap]; objective = quad_form + turnover_coef * norm1(w - w_prev)."
  - "Append-only run records: record_optimization_run validates sha256/status/failed⇔reason/model_id invariants before INSERT; JSON columns canonical-serialized via _json."

requirements-completed: [PFOL-01, PFOL-02, PFOL-03, PFOL-04]

coverage:
  - id: D1
    description: "portfolio/schemas.py — strict frozen OptimizationRequest DTO (min-vol default, baselines default, enum/date validation) + SOLVER_OPTIONS_ALLOWLIST"
    requirement: PFOL-02
    verification:
      - kind: unit
        ref: "tests/portfolio/test_schemas.py (4 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "portfolio/risk.py — sample covariance from a governed panel + PSD check/repair with mandatory provenance (method/epsilon/eigenvalues before/after), never silent"
    requirement: PFOL-01
    verification:
      - kind: unit
        ref: "tests/portfolio/test_risk.py (6 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "portfolio/optimizer.py — min-vol QP under the constraint stack with Clarabel default, honest status capture (optimal_inaccurate never promoted), solver/options/version audited; run_optimization orchestrator + PSD fail-closed gate"
    requirement: PFOL-02
    verification:
      - kind: unit
        ref: "tests/portfolio/test_optimizer.py (6 passed) + tests/portfolio/test_pipeline.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "portfolio/constraints.py — phase-11-policy-v1 constants (cap 0.10 / min-cash 0.05 / turnover 0.0014) + industry-cap fail-closed gate (never silently ignored)"
    requirement: PFOL-03
    verification:
      - kind: unit
        ref: "python -c 'assert_industry_cap_unavailable(False) / pytest.raises(ValueError)' + test_optimizer.py cap/min-cash assertions"
        status: pass
    human_judgment: false
  - id: D5
    description: "portfolio/repository.py — append-only record_optimization_run/get_optimization_run/list_optimization_runs with sha256/status/failed⇔reason/model_id invariants; immutability triggers reject UPDATE/DELETE"
    requirement: PFOL-04
    verification:
      - kind: unit
        ref: "tests/portfolio/test_repository.py (5 passed) + test_portfolio_repository.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "portfolio/artifacts.py — immutable weight/baseline/covariance bundle (O_EXCL + fsync + sha256) + checksum-verified reads"
    requirement: PFOL-04
    verification:
      - kind: unit
        ref: "tests/portfolio/test_pipeline.py#test_full_pipeline_min_vol_run_is_immutable_and_checksum_bound"
        status: pass
    human_judgment: false
  - id: D7
    description: "End-to-end tracer proof — composite snapshot identity → sample covariance + PSD gate → min-vol QP → immutable run record with HRP baseline + PSD provenance → checksum-verified artifact read-back"
    requirement: PFOL-04
    verification:
      - kind: integration
        ref: "tests/portfolio/test_pipeline.py (1 passed)"
        status: pass
    human_judgment: false

# Metrics
duration: 45min
completed: 2026-08-01
status: complete
---

# Phase 11 Plan 11-01: Tracer — End-to-End Optimization Pipeline Summary

**The full Phase 11 optimization spine proven end-to-end on a fixture: composite snapshot identity → sample covariance + explicit PSD check/repair (never silent) → Clarabel min-vol QP under the constraint stack (cap 0.10 / min-cash 0.05 / turnover 0.0014) with full solver/options/version audit → immutable append-only run record carrying HRP baseline + PSD provenance → checksum-verified weights artifact**

## Performance

- **Duration:** 45 min
- **Started:** 2026-08-01T16:44:00Z
- **Completed:** 2026-08-01T17:29:00Z
- **Tasks:** 12
- **Files modified:** 13

## Accomplishments

- **Strict input DTO + solver-options whitelist** — `OptimizationRequest` (frozen, objective defaults to `min_volatility`, `render_baselines` defaults True, enum/date validated) and `SOLVER_OPTIONS_ALLOWLIST` as the only accepted `solve()` options surface.
- **Sample covariance + PSD check/repair with mandatory provenance** — `sample_covariance` (np.cov on common finite window), `check_psd` (symmetrized `eigvalsh` min eigenvalue), `repair_psd` (eigen_clip to `PSD_EPSILON_DEFAULT` with `method`/`epsilon`/`min_eigenvalue_before`/`eigenvalues_before`/`eigenvalues_after`). The optimizer's `ensure_psd_provenance` fails closed when a non-PSD covariance lacks the provenance block — repair is never silent.
- **Constraint stack with phase-11-policy-v1 provenance** — `PER_INSTRUMENT_CAP_DEFAULT=0.10`, `MIN_CASH_DEFAULT=0.05`, `TURNOVER_COEF_DEFAULT=0.0014` (round-trip cost proxy from MatcherConfig), `PSD_EPSILON_DEFAULT=1e-10`, and `assert_industry_cap_unavailable` raising `ValueError("industry mapping unavailable")` — industry cap is never silently ignored.
- **Deterministic HRP baseline** — `hrp_weights` over scipy `linkage(method="single", optimal_ordering=True)` → `leaves_list` → recursive bisection inverse-variance (pure NumPy, deterministic); `render_baseline` scales by `(1 - min_cash)` so the baseline is apples-to-apples with the QP.
- **Append-only run records** — `record_optimization_run` / `get_optimization_run` / `list_optimization_runs` with sha256-format, problem-status, failed⇔reason, and model_id invariants; immutability triggers reject UPDATE/DELETE.
- **Immutable weight/covariance artifacts** — `PortfolioArtifactService` mirroring the research artifact discipline: namespace + files created with O_EXCL, fsynced, sha256-verified on read.
- **Min-vol QP with full audit capture** — `solve_min_vol` (Clarabel default, `tol_gap_abs`/`tol_gap_rel` per Wave 0) records status / solver_name / solve_time / num_iters / verbatim options / `cp.__version__` / solver version; `optimal_inaccurate` is never promoted.
- **End-to-end tracer proof** — `run_optimization` walks snapshot → covariance+PSD → QP → HRP baseline → immutable run → checksum-verified artifact; `test_pipeline.py` locks the whole spine including `input_snapshot_sha256` equality with the composite snapshot.

## Task Commits

Each task was committed atomically:

1. **Task: constraint stack constants + industry-cap gate (constraints.py)** - `9f0512c` (feat)
2. **Task: sample covariance + PSD check/repair (risk.py)** - `9f0512c` (feat)
3. **Task: deterministic HRP baseline (hrp.py)** - `9f0512c` (feat)
4. **Task: append-only run records (repository.py)** - `9f0512c` (feat)
5. **Task: immutable weight artifacts (artifacts.py)** - `9f0512c` (feat)
6. **Task: strict DTO + solver-options whitelist (schemas.py)** - `9f0512c` (feat)
7. **Task: min-vol QP + PSD gate + run_optimization orchestrator (optimizer.py)** - `32f2da9` (feat)
8. **Task: turn test_risk.py green** - `dcd9767` (test)
9. **Task: turn test_optimizer.py green + honest-status case** - `dcd9767` (test)
10. **Task: turn test_hrp.py green + leaf-order case** - `dcd9767` (test)
11. **Task: turn test_repository.py green + real trigger assertions** - `dcd9767` (test)
12. **Task: end-to-end tracer proof (test_pipeline.py + conftest fixture_composite)** - `eb3d91f` (test)

Supporting commits: `9a6e442` (feat: risk_model_json full PSD provenance payload), `7204453` (feat: composite_snapshot_id honors caller snapshot binding), `5d2d558` (style: ruff fixes).

## Files Created/Modified

- `backend/app/portfolio/constraints.py` - phase-11-policy-v1 constants + `assert_industry_cap_unavailable` fail-closed gate
- `backend/app/portfolio/risk.py` - `sample_covariance` / `check_psd` / `repair_psd` with mandatory provenance
- `backend/app/portfolio/hrp.py` - deterministic HRP over scipy linkage + `render_baseline`
- `backend/app/portfolio/schemas.py` - `OptimizationRequest` DTO + `SOLVER_OPTIONS_ALLOWLIST`
- `backend/app/portfolio/artifacts.py` - `PortfolioArtifactService` O_EXCL+fsync+sha256 bundle + checksum-verified reads
- `backend/app/portfolio/optimizer.py` - `ensure_psd_provenance` / `solve_min_vol` / `run_optimization`
- `backend/app/portfolio/repository.py` - append-only record/get/list methods + invariants
- `backend/tests/portfolio/conftest.py` - added `fixture_composite` (recorded composite model + snapshot identity)
- `backend/tests/portfolio/test_risk.py` - green (covariance/PSD/never-silent contracts)
- `backend/tests/portfolio/test_optimizer.py` - green (analytical, cap/min-cash, turnover, determinism, honest status)
- `backend/tests/portfolio/test_hrp.py` - green (cluster ordering + leaf adjacency, scaling, determinism)
- `backend/tests/portfolio/test_repository.py` - green (round-trip, immutability triggers, invariants, list filters)
- `backend/tests/portfolio/test_pipeline.py` - end-to-end tracer proof

## Decisions Made

- **Budget equality for the min-vol QP** — the plan prose describes `cp.sum(w) <= 1 - min_cash` as a floor, but the analytical scaffold test (`w_i ∝ 1/σ²` scaled to `1 - min_cash`) and the pitfall-7 cash-floor assertions are only satisfiable when the portfolio is fully deployed. Used `cp.sum(w) == 1 - min_cash`, which still satisfies `1 - sum(w) >= min_cash` exactly (cash = min_cash).
- **Clarabel solver options** — per Wave 0 finding, Clarabel 1.9.2 rejects OSQP-style `eps_abs`/`eps_rel`; recorded `tol_gap_abs=1e-8` / `tol_gap_rel=1e-8` / `max_iter=20000` verbatim in `solver_options_json`.
- **HRP baseline rendered scaled** — `render_baseline(hrp_weights(cov), min_cash)` so the baseline respects the same cash floor as the QP.
- **Snapshot identity as pre-resolved dict in 11-01** — `run_optimization` accepts `snapshot={"model_id", "input_snapshot_sha256", "composite_snapshot_id"}`; the production catalog seam (`load_composite_snapshot`) lands in 11-05.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Budget equality vs. floor semantics**
- **Found during:** Task 7 (solve_min_vol)
- **Issue:** The analytical scaffold test requires the fully-deployed inverse-variance solution scaled to `1 - min_cash`; the plan's literal `cp.sum(w) <= 1 - min_cash` floor would let the solver park in cash (w≈0), failing the analytical assertion and producing degenerate weights.
- **Fix:** Use `cp.sum(w) == 1 - min_cash` (budget equality). The cash floor invariant (`1 - sum(w) >= min_cash`) still holds exactly; pitfall 7 (no double-counting `sum==1` + separate cash constraint) is respected.
- **Files modified:** backend/app/portfolio/optimizer.py
- **Verification:** test_optimizer.py analytical test passes; pipeline test `sum(weights) <= 1 - min_cash + 1e-8` passes.
- **Committed in:** `32f2da9`

**2. [Rule 2 - Missing Critical] risk_model_json must carry the full PSD provenance payload**
- **Found during:** Task 12 (pipeline)
- **Issue:** The plan's pipeline test asserts `risk_model_json["psd_repair"]["method"]`; the first orchestrator draft stored only the provenance dict directly at the top level, so the `psd_repair` key was missing.
- **Fix:** `_build_risk_model` returns `risk_model_json = {"risk_model", "window", "dropna", "psd_repair": provenance}`; the run row stores the full block.
- **Files modified:** backend/app/portfolio/optimizer.py
- **Verification:** pipeline test passes; manual run shows `risk_model` with `psd_repair.method`.
- **Committed in:** `9a6e442`

**3. [Rule 3 - Blocking] composite_snapshot_id must reference the actual snapshot row**
- **Found during:** Task 12 (pipeline)
- **Issue:** The orchestrator initially set `composite_snapshot_id=None` after inserting the composite row, losing the audit link.
- **Fix:** `run_optimization` honors a caller-supplied `composite_snapshot_id` from the snapshot dict; when absent, it captures the inserted composite row's `id`.
- **Files modified:** backend/app/portfolio/optimizer.py
- **Verification:** manual run confirms `composite_snapshot_id` equals the recorded composite row id.
- **Committed in:** `7204453`

---

**Total deviations:** 3 auto-fixed (1 bug, 1 missing critical, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness and audit integrity. No scope creep; no architectural change.

## Issues Encountered

- **SQLite JSON binding:** the initial `record_optimization_run` passed dict values directly to sqlite3 (ProgrammingError). Fixed by canonical-serializing the JSON columns via the existing `_json` helper before INSERT.
- **Ruff cleanup:** RUF002/003 (ambiguous × in comments/docstrings), SIM102 (nested if), B905 (zip strict) fixed across the new modules; a pre-existing unused import in `app/portfolio/service.py` was left untouched (out of scope) and logged to `deferred-items.md`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **11-03 (HRP breadth)** can extend `hrp.py` with `hrp_portfolio` as a first-class objective; the deterministic `hrp_weights`/`render_baseline` and the `objective="hrp"` run path slot into `run_optimization`.
- **11-04 (min-vol/max-Sharpe breadth)** can add the `solver_path` fallback, `w_prev` prior-run resolution (the `turnover_reference` field is already on the DTO), and the max-Sharpe opt-in gate.
- **11-05 (snapshot binding)** replaces the pre-resolved snapshot dict with `load_composite_snapshot` (catalog.get_composite_model → checksum-verified artifact → as_of cross-section) and records fail-closed paths as `failed` runs.
- **11-06 (constraint hardening + artifact breadth)** wires `assert_industry_cap_unavailable` through the request surface and records `covariance_sha256` + covariance artifact path in `risk_model_json`.
- **Blockers/concerns:** none. Full-suite pytest deliberately NOT run (phase gate after all plans, per batch constraints). The `tests/portfolio` directory is green (30 passed).

## Known Stubs

- `portfolio/optimizer.py::_fixture_returns` — deterministic 12-symbol returns used when the tracer call omits a governed panel; the real `BacktestEngine.load_panel` seam is wired in 11-05 (snapshot binding plan).
- `run_optimization` fixture-snapshot bootstrap — when no snapshot is supplied, the orchestrator registers a fixture composite definition + snapshot row directly; 11-05 replaces this with the catalog seam and fail-closed failed-run recording.

---
*Phase: 11-portfolio-construction-optimization*
*Completed: 2026-08-01*

## Self-Check: PASSED

All 8 key files exist on disk (7 modules + SUMMARY); all 7 plan commits present in git history (`9f0512c`, `32f2da9`, `dcd9767`, `9a6e442`, `eb3d91f`, `7204453`, `5d2d558`). Final gate re-verified after the last commit: `pytest tests/portfolio -q --tb=short` → 30 passed; plan verification block (test_pipeline/test_risk/test_optimizer/test_hrp/test_repository) → 23 passed; `ruff check app/portfolio/ tests/portfolio/` clean (except pre-existing out-of-scope `service.py` F401); `import app.portfolio.optimizer` pulls no pandas; `cp.quad_form` appears only in optimizer.py (guarded by the PSD gate); Clarabel smoke QP `optimal` with `tol_gap_abs`/`tol_gap_rel`.
