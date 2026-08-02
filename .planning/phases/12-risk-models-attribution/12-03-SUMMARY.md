---
phase: 12-risk-models-attribution
plan: 12-03
subsystem: portfolio-risk-models
tags: [rsk-02, risk-models, semi-covariance, ewma, ledoit-wolf, sklearn-lazy-import, psd-provenance, optimizer-dispatch]
requires: [12-01]
provides: [semi_covariance, ewma_covariance, ledoit_wolf_covariance, make_risk_model_family, OptimizationRequest.risk_model, _build_risk_model-dispatch]
affects: [12-05, 12-06, phase-13-walk-forward]
tech-stack:
  added: [scikit-learn-1.8.0-lazy-import-at-model-boundary (shadow extra, never module-top)]
  patterns: [make_risk_model_family single PSD-provenance dispatcher, model_params in risk_model_json, verbatim risk_model recording]
key-files:
  created: []
  modified:
    - backend/app/portfolio/risk.py
    - backend/app/portfolio/optimizer.py
    - backend/app/portfolio/schemas.py
    - backend/app/portfolio/repository.py
    - backend/tests/portfolio/test_risk.py
    - backend/tests/portfolio/test_pipeline.py
    - backend/tests/portfolio/test_optimizer.py
key-decisions:
  - "make_risk_model_family is the single PSD-provenance dispatcher all four models pass through (check_psd → repair_psd → provenance), shared with Phase 13 per-fold covariance"
  - "model_params (benchmark/lam/shrinkage/sklearn_version) recorded in risk_model_json so the selected model's parameters are auditable on the run"
  - "OptimizationRequest.risk_model defaults to sample_covariance_v1 — RSK-02 selection is explicit, never accidental"
  - "runs-table risk_model gate widened to the approved 4-model enum in repository.py (Rule 3 — the 12-02 option-a migration already widened the DB CHECK; the repository gate had to match or every non-sample run would fail validation)"
patterns-established:
  - "Sklearn lazy-import boundary: from sklearn.* only inside risk.py function bodies (subprocess gate asserts 'sklearn' not in sys.modules after import)"
  - "Per-model PSD provenance never silent: method/epsilon/eigenvalues before/after in psd_repair for every model"
requirements-completed: [RSK-02]
coverage:
  - id: D1
    description: "semi_covariance / ewma_covariance (lambda=0.94) / ledoit_wolf_covariance (sklearn 1.8.0 lazy-import at the model boundary only)"
    requirement: RSK-02
    verification:
      - kind: unit
        ref: "tests/portfolio/test_risk.py#test_semi_covariance_matches_manual_below_mean_reference"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_risk.py#test_ewma_covariance_matches_hand_computed_recursion"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_risk.py#test_ledoit_wolf_covariance_returns_psd_with_shrinkage"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_risk.py#test_risk_module_import_does_not_load_sklearn"
        status: pass
    human_judgment: false
  - id: D2
    description: "make_risk_model_family dispatcher with per-model PSD provenance (method/epsilon/eigenvalues before/after) for all four models; unknown name raises"
    requirement: RSK-02
    verification:
      - kind: unit
        ref: "tests/portfolio/test_risk.py#test_make_risk_model_family_dispatches_all_four_models"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_risk.py#test_make_risk_model_family_rejects_unknown_name"
        status: pass
    human_judgment: false
  - id: D3
    description: "OptimizationRequest.risk_model + _build_risk_model dispatch wiring the three new models into run_optimization; selected name recorded verbatim on the run row + risk_model_json; covariance artifact checksum-bound per model"
    requirement: RSK-02
    verification:
      - kind: integration
        ref: "tests/portfolio/test_pipeline.py#test_run_optimization_records_selected_risk_model_with_checksum_bound_covariance"
        status: pass
      - kind: integration
        ref: "tests/portfolio/test_pipeline.py#test_run_optimization_default_records_sample_covariance"
        status: pass
    human_judgment: false
metrics:
  duration: "~45 min"
  completed: 2026-08-02
status: complete
---

# Phase 12 Plan 03: Risk-Model Suite Breadth Summary

**The full RSK-02 risk-model suite ships: semi-covariance (below-mean benchmark), EWMA (RiskMetrics λ=0.94, adjust=True), and Ledoit-Wolf shrinkage (scikit-learn 1.8.0 lazy-imported at the model boundary only) — every model passing through the single `make_risk_model_family` dispatcher with explicit PSD-repair provenance (method/epsilon/eigenvalues before/after, never silent), wired into `run_optimization` via `OptimizationRequest.risk_model` and recorded verbatim on the run row + risk_model_json with model params, checksum-bound per model.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-08-02T00:25:03Z
- **Completed:** 2026-08-02T01:10:00Z
- **Tasks:** 4 (plus 2 style/prune commits)
- **Files modified:** 7

## Accomplishments
- `semi_covariance` (benchmark mean/zero, PyPortfolioOpt contract as design spec — Gram matrix of below-benchmark co-movement normalized by observation count)
- `ewma_covariance` (recursive Σ_t = λΣ_{t−1} + (1−λ)r_t r_tᵀ, λ=0.94 RiskMetrics default, adjust=True/False, λ=1.0 degenerates to sample covariance on demeaned data)
- `ledoit_wolf_covariance` returning `(cov, {"shrinkage", "sklearn_version"})` with the `from sklearn.covariance import LedoitWolf` import INSIDE the function body only — subprocess gate asserts `"sklearn" not in sys.modules` after `import app.portfolio.risk`
- `make_risk_model_family` — the single PSD-provenance dispatcher: dispatch 4 builders (unknown → ValueError), then check_psd → repair_psd (eigen_clip) → provenance (method/epsilon/eigenvalues before/after) → covariance_sha256 for EVERY model; model_params (benchmark/lam/shrinkage/sklearn_version) recorded
- `OptimizationRequest.risk_model` (4-model Literal, sample default) + `_build_risk_model` delegation + `req.risk_model` threaded through `_run_optimization_impl` into all three record sites (HRP branch, solver-error branch, success branch) + `risk_model_json["risk_model"]` verbatim
- Parameterized pipeline test: runs under all four models record the selected name, model params, full PSD provenance, 64-hex covariance_sha256, and a checksum-verified covariance artifact; default still records `sample_covariance_v1`

## Task Commits

Each task was committed atomically:

1. **Task 1: risk.py — 3 models + make_risk_model_family** — `5222a72` (feat)
2. **Task 2: optimizer + schemas — risk_model dispatch** — `4a5ccf5` (feat)
3. **Task 3: test_risk.py green + lazy-import gate** — `a303994` (test)
4. **Task 4: test_pipeline.py 4-model runs** — `2f4e1e9` (test)
5. Prune unused risk imports after dispatcher refactor — `9c7d6cf` (style)
6. Replace unicode minus signs in ewma docstring (ruff RUF002) — `76630fc` (style)

## Files Created/Modified
- `backend/app/portfolio/risk.py` — semi_covariance, ewma_covariance, ledoit_wolf_covariance, make_risk_model_family; sklearn lazy-import boundary
- `backend/app/portfolio/schemas.py` — `RiskModel` Literal + `OptimizationRequest.risk_model` (default sample_covariance_v1)
- `backend/app/portfolio/optimizer.py` — `_build_risk_model` delegates to `make_risk_model_family`; `req.risk_model` threaded into build + all record sites; unused imports pruned
- `backend/app/portfolio/repository.py` — `_RISK_MODELS` runs gate widened to the approved 4-model enum (Rule 3)
- `backend/tests/portfolio/test_risk.py` — ledoit tuple contract, full provenance + model_params assertions
- `backend/tests/portfolio/test_pipeline.py` — parameterized 4-model run test + default-sample test
- `backend/tests/portfolio/test_optimizer.py` — `_bypass_repair` monkeypatch accepts new `risk_model_name` kwarg (Rule 3)

## Decisions Made
- `make_risk_model_family` is the single PSD-provenance path all four models pass through (threat model T-12-01 mitigation — never a silent clip); `_build_risk_model` is a thin delegating wrapper preserving the Phase 11 output shape for sample.
- Model params are recorded in `risk_model_json["model_params"]` so the selected model's configuration (benchmark/lam/shrinkage/sklearn_version) is auditable on the immutable run — the Phase 13 per-fold covariance seam.
- `OptimizationRequest.risk_model` defaults to `sample_covariance_v1` — RSK-02 selection is explicit, never accidental.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Widen the repository runs-table risk_model gate to the 4-model enum**
- **Found during:** Task 2 (optimizer dispatch)
- **Issue:** The 12-02 migration (option-a) widened the DB CHECK on `portfolio_optimization_runs.risk_model` to the 4-model enum, but `PortfolioRepository._RISK_MODELS` still contained only `sample_covariance_v1` — every `run_optimization(risk_model="semi_covariance_v1")` would fail validation with "unknown risk_model" before reaching the DB.
- **Fix:** Widened `_RISK_MODELS` to the same 4-model frozenset (reused as `_RISK_MODELS_PHASE12`).
- **Files modified:** backend/app/portfolio/repository.py
- **Verification:** `tests/portfolio/test_pipeline.py` 4-model parameterized test passes; full impacted suite green (64 passed).
- **Committed in:** `4a5ccf5` (Task 2 commit)

**2. [Rule 3 - Blocking] test_optimizer `_bypass_repair` monkeypatch signature**
- **Found during:** Task 2 verification
- **Issue:** `_build_risk_model` gained the `risk_model_name` keyword argument; the test's monkeypatched `_bypass_repair(returns, *, window, epsilon=1e-10)` no longer matched the call signature, raising TypeError.
- **Fix:** Added the `risk_model_name="sample_covariance_v1"` keyword parameter to the stub (no behavior change — the test still bypasses the PSD gate deliberately).
- **Files modified:** backend/tests/portfolio/test_optimizer.py
- **Verification:** test_optimizer.py green.
- **Committed in:** `4a5ccf5` (Task 2 commit)

**3. [Rule 1 - Bug] scaffolded Ledoit-Wolf test called the function with the pre-refactor signature**
- **Found during:** Task 3 (test_risk green)
- **Issue:** The 12-02 RED scaffold's `test_ledoit_wolf_covariance_returns_psd_with_shrinkage` unpacked `cov = ledoit_wolf_covariance(fixture_returns)` as a bare array, but the plan's contract (12-03 task 1) returns `(cov, {"shrinkage", "sklearn_version"})` — ValueError on unpacking the tuple.
- **Fix:** Updated the test to the tuple contract and strengthened `make_risk_model_family` assertions (full provenance keys, model_params, covariance_sha256).
- **Files modified:** backend/tests/portfolio/test_risk.py
- **Verification:** test_risk.py green (16 passed).
- **Committed in:** `a303994` (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (2 blocking [Rule 3], 1 bug [Rule 1])
**Impact on plan:** All three were necessary for the plan's stated contracts to actually pass — no scope creep, no architectural change.

## Issues Encountered
- LedoitWolf in sklearn 1.8.0 rejects `block_size=None` (`InvalidParameterError`) — the plan's `block_size: int | None = None` parameter is accepted but only forwarded when not None, letting sklearn use its default (verified 2x2 and 3-obs x 4-asset degenerate inputs fit fine).
- `lam=1.0` EWMA on non-demeaned data does not recover `np.cov` (mean not removed) — the plan's documented contract is on demeaned data, which passes (test uses demeaned input).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 12-05 (cross-model attribution + reconciliation) consumes `make_risk_model_family` as the recompute path for model-selected attribution and `_RISK_MODELS_PHASE12` in the evidence API.
- Phase 13 walk-forward reuses `make_risk_model_family` for per-fold covariance.
- Grep gate hygiene verified: `sklearn` appears only inside `risk.py` function bodies (plus a module docstring reference and the unrelated `app/shadow/distillation.py`); no hardcoded `risk_model="sample_covariance_v1"` record sites remain in optimizer.py.

---
*Phase: 12-risk-models-attribution*
*Completed: 2026-08-02*
