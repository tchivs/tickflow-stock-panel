---
phase: 11-portfolio-construction-optimization
verified: 2026-08-02T06:30:00Z
status: passed
score: 4/4 roadmap success criteria verified (6/6 PLAN must-have truths verified)
behavior_unverified: 0
overrides_applied: 0
gaps: []
---

# Phase 11: Portfolio Construction & Optimization Verification Report

**Phase Goal:** Researchers can build a sample covariance from governed data with explicit PSD repair, solve auditable long-only min-vol and HRP-baseline portfolios under a constraint stack, and retrieve every run as an immutable record.
**Verified:** 2026-08-02
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Researcher can build sample covariance from a governed panel and inspect any PSD repair as an explicit recorded step (method, epsilon, eigenvalues before/after) in the immutable run record — never silent (SC-1 / PFOL-01) | ✓ VERIFIED | `portfolio/risk.py:sample_covariance/check_psd/repair_psd` return provenance dict with all four mandatory keys (`method`, `epsilon`, `eigenvalues_before`, `eigenvalues_after`); `portfolio/optimizer.py:_build_risk_model` records the full `psd_repair` block in `risk_model_json`; `ensure_psd_provenance` raises `ValueError("PSD repair provenance missing")` when a non-PSD covariance lacks provenance (never silent). Tests: `test_repair_psd_returns_psd_matrix_and_provenance`, `test_never_silent_repair_is_rejected_without_provenance`, `test_pipeline.py` asserts `risk_model_detail["psd_repair"]["method"] in ("none","eigen_clip")` on a real run. |
| 2 | Researcher can solve a long-only minimum-volatility portfolio and an HRP baseline side by side; max-Sharpe is available only as an explicit non-default option with baselines rendered alongside (SC-2 / PFOL-02) | ✓ VERIFIED | `schemas.py:OptimizationRequest.objective` defaults to `min_volatility`; `hrp.py:hrp_weights/render_baseline/hrp_portfolio` (scipy single-linkage + optimal_ordering, scaled by `1 - min_cash`); `optimizer.py:run_optimization` records HRP baseline for min-vol runs and **both** min-vol + HRP baselines for max-Sharpe; `max_sharpe` with `render_baselines=False` fails closed. Tests: `test_min_vol_two_asset_matches_analytical`, `test_hrp_weights_sum_to_one`, `test_max_sharpe_requires_baselines`, `test_max_sharpe_run_records_both_baselines` (drives the real orchestrator branch). |
| 3 | Researcher can apply the constraint stack — long-only bounds, per-instrument cap, minimum cash, convex turnover cost — and an industry cap fails closed until a governed industry mapping exists (SC-3 / PFOL-03) | ✓ VERIFIED | `constraints.py` defines `phase-11-policy-v1` constants (cap 0.10 / min-cash 0.05 / turnover 0.0014) and `assert_industry_cap_unavailable` raising `ValueError("industry mapping unavailable")`; `optimizer.py:solve_min_vol/solve_max_sharpe` build `w = cp.Variable(n, nonneg=True)` with `cp.sum(w) == 1 - min_cash`, `w <= cap`, and `+ turnover_coef * cp.norm1(w - w_prev)`; `_run_optimization_impl` calls the industry-cap gate first (requested cap → recorded failed run, never silent). Tests: `test_cap_and_min_cash_are_active_constraints`, `test_turnover_penalty_shifts_toward_w_prev`, `test_industry_cap_requested_fails_closed_with_failed_run`, `test_no_industry_cap_records_null_in_constraint_stack`. |
| 4 | Researcher can retrieve any optimization run as an immutable record carrying input-snapshot SHA-256, expected-return method, risk model, solver name/version/options, problem status, and output weights; failed runs retain their failure reason (SC-4 / PFOL-04) | ✓ VERIFIED | `operational/migrations.py` `portfolio_optimization_runs` table: CHECK enums, sha256 length=64, failed⇔failure_reason invariant, `no_update`/`no_delete` triggers; `portfolio/repository.py:record_optimization_run` validates sha256/status/invariants before INSERT; `optimizer.py:run_optimization` records all audit fields and wraps the entire spine so any `SnapshotBindingError/ValueError/RuntimeError/SolverError/DCPError` lands a `failed` run with `failure_reason`. Tests: `test_record_and_get_round_trip_json_columns`, `test_update_and_delete_are_blocked`, `test_failed_run_requires_failure_reason`, `test_indefinite_covariance_records_failed_run_in_orchestrator`, `test_phase11_optimization_runs_migrate_with_constraints_and_idempotence`. |
| 5 | The composite expected-return input is consumed by snapshot (checksum-verified artifact + input_snapshot_sha256), never a live module hand-off; missing/tampered artifact or lookahead as_of fails the run closed with a recorded reason | ✓ VERIFIED | `portfolio/snapshot.py:load_composite_snapshot` resolves `catalog.get_composite_model` → sha256-verifies artifact bytes against `output_sha256` → builds the `as_of` cross-section; all failure paths raise `SnapshotBindingError` recorded as `failed` runs; lookahead guarded on BOTH ends (`as_of precedes` / `as_of exceeds composite snapshot coverage`); `portfolio/` never calls `build_composite` (grep gate clean). Tests: `test_load_composite_snapshot_returns_checksum_verified_cross_section`, `test_artifact_tampered_fails_closed`, `test_lookahead_as_of_fails_closed`, `test_lookahead_as_of_after_last_date_fails_closed`, `test_run_optimization_records_failed_run_on_snapshot_binding_failure`, `test_composite_snapshot_consumption_matches_artifact_bytes` (cross-module, in `tests/research/test_models.py`). |
| 6 | Every run's output weights are checksum-verified immutable artifacts (O_EXCL + fsync + sha256) under the run's namespace; solver/options/status are recorded verbatim against pinned cvxpy 1.9.2 | ✓ VERIFIED | `portfolio/artifacts.py:PortfolioArtifactService.write_bundle` O_EXCL-creates the namespace + files, fsyncs, computes `checksum_sha256` from exact bytes; `read_artifact` refuses on checksum mismatch; `_finalize_result` records `status/solver_name/solve_time/num_iters/options/cvxpy_version/solver_version`; `pyproject.toml` pins `cvxpy==1.9.2` (verified installed: `cp.__version__ == 1.9.2`, `uv.lock` specifier `==1.9.2`). Tests: `test_full_pipeline_min_vol_run_is_immutable_and_checksum_bound`, `test_successful_run_records_covariance_sha256_and_artifact`, `test_solver_name_and_version_capture_actual_solver`. |

**Score:** 4/4 roadmap success criteria verified (6/6 PLAN must-have truths verified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | ---------| ------ | ------- |
| `backend/app/portfolio/risk.py` | `sample_covariance` / `check_psd` / `repair_psd` with mandatory PSD provenance | ✓ VERIFIED | Full provenance dict (method/epsilon/min_eigenvalue_before/eigenvalues_before/after); `covariance_sha256` canonical identity. |
| `backend/app/portfolio/optimizer.py` | `solve_min_vol`/`solve_max_sharpe` QP + `run_optimization` orchestrator + PSD fail-closed gate | ✓ VERIFIED | Clarabel default + OSQP fallback, full audit capture, DCPError/SolverError fail-closed wrapper, `optimal_inaccurate` demoted to `solver_error`. |
| `backend/app/portfolio/constraints.py` | policy constants + industry-cap fail-closed gate | ✓ VERIFIED | `phase-11-policy-v1` constants; `assert_industry_cap_unavailable` raises `ValueError("industry mapping unavailable")`. |
| `backend/app/portfolio/repository.py` | `record_optimization_run`/`get_optimization_run`/`list_optimization_runs` append-only | ✓ VERIFIED | sha256/status/failed⇔reason/model_id invariants; JSON columns canonical + unwrapped to `risk_model_detail`. |
| `backend/app/portfolio/artifacts.py` | `PortfolioArtifactService` O_EXCL+fsync+sha256 bundles | ✓ VERIFIED | weights/baseline/covariance.json under `research_artifacts/<run_id>/`; namespace cleanup on mid-write failure. |
| `backend/app/portfolio/schemas.py` | `OptimizationRequest` DTO + `SOLVER_OPTIONS_ALLOWLIST` | ✓ VERIFIED | frozen Pydantic model, min-vol default, baselines default, `industry_cap: float | None`; whitelist enforced in solver entry points. |
| `backend/app/portfolio/snapshot.py` | `load_composite_snapshot` checksum-verified binding | ✓ VERIFIED | catalog → artifact sha256 → as_of cross-section; both lookahead ends guarded; malformed rows fail closed. |
| `backend/app/portfolio/hrp.py` | deterministic HRP baseline + `render_baseline` | ✓ VERIFIED | scipy linkage single + optimal_ordering, recursive bisection inverse-variance, scaled by `1 - min_cash`. |
| `backend/app/operational/migrations.py` | `portfolio_optimization_runs` append-only table | ✓ VERIFIED | CHECK enums, sha256 lengths, failed⇔reason invariant, `no_update`/`no_delete` triggers, as_of index. |
| `backend/pyproject.toml` | cvxpy==1.9.2 exact pin | ✓ VERIFIED | `cvxpy==1.9.2` in base deps; `uv.lock` locks `==1.9.2`; installed interpreter reports `1.9.2`. |
| `backend/tests/portfolio/` | per-requirement tests + conftest | ✓ VERIFIED | 74 passed when run locally. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `portfolio/optimizer.py` | `portfolio/risk.py` | `ensure_psd_provenance` | ✓ WIRED | Imported and invoked in `_run_optimization_impl` before the QP; fail-closed gate tested. |
| `portfolio/snapshot.py` | `research/catalog.py` | `get_composite_model` | ✓ WIRED | `load_composite_snapshot` calls `catalog.get_composite_model(model_id)`; never `build_composite` (grep gate clean). |
| `portfolio/repository.py` | `operational/migrations.py` | `record_optimization_run` | ✓ WIRED | Constructor applies `migrate_operational_db`; inserts into `portfolio_optimization_runs`; `run.input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256` asserted in cross-module tests. |
| `portfolio/optimizer.py` | `portfolio/artifacts.py` | `PortfolioArtifactService` | ✓ WIRED | `write_bundle` persists weights under `research_artifacts/<run_id>/`; run row stores `output_sha256` + relative path; checksum-verified read-back tested. |
| `portfolio/risk.py` | `portfolio/optimizer.py` | `repair_psd` | ✓ WIRED | `_build_risk_model` uses `repair_psd`; `ensure_psd_provenance` is a hard prerequisite before `cp.quad_form`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `portfolio/snapshot.py:load_composite_snapshot` | `mu` / `symbols` / `input_snapshot_sha256` | `catalog.get_composite_model` → checksum-verified artifact bytes → as_of cross-section | Yes (real catalog rows + artifact bytes; `test_composite_snapshot_consumption_matches_artifact_bytes` verifies cross-section equals artifact payload) | ✓ FLOWING |
| `portfolio/optimizer.py:run_optimization` | `output_weights` | cvxpy solve over caller/governed returns panel + snapshot mu | Yes (solver-produced weights; `test_min_vol_two_asset_matches_analytical` matches inverse-variance reference) | ✓ FLOWING |
| `portfolio/artifacts.py:write_bundle` | `covariance.json` / `weights.json` | `_build_risk_model` covariance + solve weights | Yes (checksum round-trips; `test_successful_run_records_covariance_sha256_and_artifact`) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full portfolio suite (SC-1..4 + all review-fix regressions) | `cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short` | `74 passed` | ✓ PASS |
| Cross-module composite consumption + migration contract | `cd backend && .venv/bin/python -m pytest tests/research/test_models.py tests/test_operational_migrations.py -q --tb=short` | `19 passed` | ✓ PASS |
| Pinned engine versions | `.venv/bin/python -c "import cvxpy, scipy; print(cvxpy.__version__, scipy.__version__)"` | `cvxpy 1.9.2 scipy 1.17.1` | ✓ PASS |
| `build_composite` absent from `portfolio/` | `grep -rn "build_composite" backend/app/` | only `research/models.py`, `research/catalog.py` (no portfolio hits) | ✓ PASS |
| No execution authority in `portfolio/` | `grep -n "execute\|order\|broker\|trade" backend/app/portfolio/` | no broker/execute/order paths (only HRP/repository docstrings) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| PFOL-01 | 11-01, 11-06 | Sample covariance + explicit PSD repair provenance, never silent | ✓ SATISFIED | `test_risk.py` (8), `test_pipeline.py` psd_repair assertion, `test_successful_run_records_covariance_sha256_and_artifact` |
| PFOL-02 | 11-01, 11-03, 11-04 | Min-vol + HRP baseline; max-Sharpe non-default with baselines | ✓ SATISFIED | `test_optimizer.py` analytical match + baselines tests, `test_hrp.py` (7) |
| PFOL-03 | 11-01, 11-04, 11-06 | Constraint stack + industry-cap fail-closed | ✓ SATISFIED | `test_cap_and_min_cash_are_active_constraints`, `test_turnover_penalty_shift`, `test_industry_cap_requested_fails_closed_with_failed_run` |
| PFOL-04 | 11-01, 11-02, 11-05 | Immutable run records incl. failure reason + snapshot binding | ✓ SATISFIED | `test_repository.py` (5), `test_snapshot_binding.py` (8), migration test, orchestrator fail-closed tests |

No orphaned requirements: PFOL-01..04 all map to Phase 11 plans (11-01/11-02/11-03/11-04/11-05/11-06) and REQUIREMENTS.md marks all four Complete.

### Cross-Module Integrity

| Check | Evidence | Status |
| ----- | -------- | ------ |
| `run.input_snapshot_sha256 == composite snapshot sha256` | `tests/research/test_models.py::test_composite_snapshot_consumption_matches_artifact_bytes` (asserts snapshot `input_snapshot_sha256` == composite row + model); `test_snapshot_binding.py::test_run_optimization_input_snapshot_sha256_matches_composite`; `test_pipeline.py` asserts equality on a fixture run | ✓ VERIFIED |
| `covariance_sha256` in `risk_model_json` (Phase 12 seam) | `_build_risk_model` writes `covariance_sha256`; `covariance_artifact_relative_path` added on artifact-writing paths; `test_successful_run_records_covariance_sha256_and_artifact` checksum-verifies the artifact against the recorded digest; `test_risk.py` round-trips digest through `read_artifact` | ✓ VERIFIED |
| No second composite-build path in `portfolio/` | grep gate: `build_composite` appears only in `research/models.py` / `research/catalog.py`; `portfolio/snapshot.py` consumes only artifact bytes | ✓ VERIFIED |
| Evaluation / signal chain unchanged | Phase 11 commits touch only `backend/app/portfolio/`, `backend/app/operational/migrations.py`, `backend/pyproject.toml`, `backend/uv.lock`, and tests; `backend/app/research/signal_chain.py` and `research/models.py` have no Phase 11 commits | ✓ VERIFIED |

### Review Fixes Confirmed Live in Source (11-REVIEW: 16 findings → clean)

| Finding | Severity | Source evidence | Test evidence | Status |
| ------- | -------- | --------------- | ------------- | ------ |
| CR-01 (phantom composite row) | BLOCKER | `_run_optimization_impl`: no fabricated `factor_model_composites` row — resolves registered composite or raises `ValueError("composite-zscore-v1 requires a checksum-verified snapshot seam ...")`; no `insert_model_composite` call in the orchestrator | `test_composite_without_real_seam_records_failed_run_no_phantom_row` (asserts `list_model_composites("ghost-model") == []`) | ✓ FIXED |
| CR-02 (DCPError/SolverError unrecorded) | BLOCKER | `run_optimization` outer wrapper catches `(SnapshotBindingError, ValueError, RuntimeError, cp.error.SolverError, cp.error.DCPError)`; inner solve branch likewise | `test_indefinite_covariance_records_failed_run_in_orchestrator` (drives a non-PSD covariance through the real orchestrator → recorded `failed` run) | ✓ FIXED |
| CR-03 (`optimal_inaccurate` promoted) | BLOCKER | `_finalize_result` extracts weights only for `status == "optimal"`; orchestrator demotes `optimal_inaccurate` → `solver_error` with `failure_reason`, `output_weights_json=None` | `test_optimal_inaccurate_status_is_non_optimal_in_orchestrator` (monkeypatched solver returns `optimal_inaccurate` → `solver_error` run, no weights artifact) | ✓ FIXED |
| WR-01 (solver-options whitelist dead) | WARNING | `_validate_solver_options` called in `solve_min_vol`/`solve_max_sharpe` before `options.update(solver_options)`; unknown keys raise `ValueError` | `test_solver_options_unknown_key_rejected`, `test_solver_options_whitelisted_key_accepted` | ✓ FIXED |
| WR-06 (`created_at` hardcoded) | WARNING | `created_at = _now()` (real UTC `datetime.now(UTC).isoformat()`) | `test_created_at_is_real_utc_timestamp` (asserts not the planning date, close to now, UTC) | ✓ FIXED |
| WR-02/03/04/05/07 + IN-01..06 | WARNING/INFO | Source updated per FIX-SUMMARY (sentinel `0`*64, lookahead end guard, `fixture_mode` gate, documented min-cash equality deviation, `solver_name="n/a"` + `{}` options on pre-solve failures, `risk_model_detail` unwrap, scipy determinism note, namespace cleanup, `output_weights_json=None`) | Regression tests present in `test_optimizer.py` / `test_snapshot_binding.py` / `test_risk.py` (all passed in the 74-test run) | ✓ FIXED |

### Boundary: No Execution Authority

`backend/app/portfolio/` contains no broker / order / execution path (grep for `execute|order|broker` returns only HRP/repository docstrings and the append-only run INSERT). Phase 11 output is continuous research weights consumed by Phase 14's RebalancePlan; zero execution authority is preserved. The only broker references in the codebase are the pre-existing Shadow import module (`shadow/importer.py` — "never connect to a broker or mutate accounts", `list_operational_mutations() == []`), which is a v1.0 boundary, not a Phase 11 concern.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `backend/app/portfolio/service.py` | 4 | unused `timezone` import (F401) | ℹ️ Info | Pre-existing (v1.0), not caused by Phase 11; documented in `deferred-items.md`; out of scope. |
| — | — | TBD / FIXME / XXX / TODO / HACK / PLACEHOLDER | — | None found in `backend/app/portfolio/` (grep clean) |
| — | — | Hardcoded empty data / stub returns | — | None found; all rendered data flows from real solves/snapshot bytes |

### Human Verification Required

None. Every roadmap success criterion is behavior-verified by automated tests executed locally:
- SC-1 PSD provenance recorded in a run: exercised by `test_pipeline.py` and `test_risk.py`.
- SC-2 min-vol + HRP side by side / max-Sharpe baselines: exercised by `test_max_sharpe_run_records_both_baselines` (real orchestrator branch) and `test_hrp.py`.
- SC-3 constraint stack + industry-cap fail-closed: exercised by `test_industry_cap_requested_fails_closed_with_failed_run` and solver-level constraint tests.
- SC-4 immutable record retrieval + failed-run retention: exercised by `test_repository.py`, the migration test, and orchestrator fail-closed tests.

No visual, real-time, or external-service behavior requires human judgment.

### Gaps Summary

No gaps found. The phase goal is achieved in the codebase:
- All 4 ROADMAP success criteria are demonstrably true (concrete code paths cited above + passing automated tests).
- All 6 PLAN must-have truths verified against source.
- All required artifacts exist, are substantive, and are wired (Levels 1-3), with real data flowing through every dynamic artifact (Level 4).
- All 5 declared key links verified wired.
- All 16 code-review findings (3 BLOCKER, 7 WARNING, 6 INFO) are fixed in live source and locked by regression tests.
- Cross-module integrity holds: `input_snapshot_sha256` audit-root equality, `covariance_sha256` in `risk_model_json` for the Phase 12 seam, no `build_composite` in `portfolio/`, signal chain untouched.
- Boundary holds: no execution authority; industry cap fails closed with the exact reason "industry mapping unavailable".

## Overall Verdict

**PASS.** Phase 11 "Portfolio Construction & Optimization" delivers its goal end to end. Evidence was gathered from the actual source files (not SUMMARY.md claims): every success criterion maps to a concrete `file:function` path and a passing automated test; the three review BLOCKERs and all warnings/infos are confirmed fixed in the current working tree (which is clean at commit `b7181e4`); the portfolio suite (74 tests) and the cross-module research/migration suite (19 tests) both pass locally on the pinned stack (cvxpy 1.9.2, scipy 1.17.1).

---

_Verified: 2026-08-02_
_Verifier: Claude (gsd-verifier)_
