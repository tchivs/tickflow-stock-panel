# Phase 11: Code Review Fix Summary

**Fixed at:** 2026-08-02
**Source review:** `.planning/phases/11-portfolio-construction-optimization/11-REVIEW.md`
**Fixes:** 2 atomic commits (`871a802`, `93a4aeb`)
**Result:** all 16 findings fixed (3 BLOCKER, 7 WARNING, 6 INFO); suite `93 passed`.

## Per-finding status

| ID | Severity | Status | Commit | Summary |
|---|---|---|---|---|
| CR-01 | BLOCKER | fixed | `871a802` | Phantom composite row eliminated: `composite-zscore-v1` resolves the model's registered checksum-bound composite or fails closed into a recorded failed run; never writes a fabricated `factor_model_composites` row / `output_sha256`. Orchestrator test: `test_composite_without_real_seam_records_failed_run_no_phantom_row`. |
| CR-02 | BLOCKER | fixed | `871a802` | `cp.error.DCPError`/`SolverError` (bare `Exception` subclasses) caught in the inner solve guard AND the outer `run_optimization` wrapper — non-PSD cov / `w_prev` mismatch / solver crash now record a failed run. Orchestrator test: `test_indefinite_covariance_records_failed_run_in_orchestrator`. |
| CR-03 | BLOCKER | fixed | `871a802` | `optimal_inaccurate` is demoted to a non-optimal `solver_error` run with `failure_reason`, no weights artifact, `output_weights_json=None`; `_finalize_result` extracts weights only for `status == "optimal"`. Orchestrator test: `test_optimal_inaccurate_status_is_non_optimal_in_orchestrator`. |
| WR-01 | WARNING | fixed | `871a802` | `SOLVER_OPTIONS_ALLOWLIST` enforced via `_validate_solver_options` in `solve_min_vol`/`solve_max_sharpe`; unknown keys → `ValueError`. Tests: `test_solver_options_unknown_key_rejected` / `test_solver_options_whitelisted_key_accepted`. |
| WR-02 | WARNING | fixed | `871a802` | Failed runs resolve the model's real `input_snapshot_sha256` (from the catalog/model definition) or the documented `0`*64 sentinel — never the fabricated `"f"*64`; `expected_return_method` kept verbatim (FK degradation unchanged). |
| WR-03 | WARNING | fixed | `93a4aeb` | `as_of > max(date)` rejected with `SnapshotBindingError("as_of exceeds composite snapshot coverage")` — both ends of the panel window guarded. Test: `test_lookahead_as_of_after_last_date_fails_closed`. |
| WR-04 | WARNING | fixed | `871a802` | Fixture returns / 12-symbol default gated behind explicit `fixture_mode=True`; production orchestrator requires `returns`+`symbols` (or the catalog seam universe). Test: `test_run_optimization_requires_returns_and_symbols_without_fixture_mode`. |
| WR-05 | WARNING | fixed | `871a802` | Min-cash budget equality documented as a deliberate tested deviation (per 11-01-SUMMARY.md) in `solve_min_vol`/`solve_max_sharpe`. Test: `test_min_cash_equality_is_documented_tested_deviation`. |
| WR-06 | WARNING | fixed | `871a802` | `created_at` uses `_now()` (real UTC run time) instead of the hardcoded planning date. Test: `test_created_at_is_real_utc_timestamp`. |
| WR-07 | WARNING | fixed | `871a802` | Pre-solve failures record `solver_name="n/a"` + `solver_options_json={}` (mirroring the HRP objective path) — no fabricated `DEFAULT_SOLVER_OPTIONS`. |
| IN-01 | INFO | fixed | `871a802` | `risk_model_json` unwraps to `risk_model_detail` — no collision with the literal `risk_model` column; consumers updated (`test_pipeline`, `test_repository`, `test_optimizer`). |
| IN-02 | INFO | fixed | `871a802` | `hrp.py` module docstring documents scipy-version-sensitive leaf ordering (weights frozen at record time, scipy pinned `<1.18`). |
| IN-03 | INFO | fixed | `871a802` | NaN/Inf covariance → recorded failed run covered by `test_nan_covariance_records_failed_run`. |
| IN-04 | INFO | fixed | `93a4aeb` | Parsed-row count must equal payload length — partially malformed artifacts fail closed. Test: `test_malformed_artifact_rows_fail_closed`. |
| IN-05 | INFO | fixed | `871a802` | `write_bundle` removes the namespace on mid-write failure. Test: `test_write_bundle_cleans_up_namespace_on_mid_write_failure`. |
| IN-06 | INFO | fixed | `871a802` | Failed solves record `output_weights_json=None` (not `{}`). |

## Files changed

- `backend/app/portfolio/optimizer.py` — CR-01/02/03, WR-01/02/04/05/06/07, IN-06
- `backend/app/portfolio/snapshot.py` — WR-03, IN-04
- `backend/app/portfolio/repository.py` — IN-01
- `backend/app/portfolio/artifacts.py` — IN-05
- `backend/app/portfolio/hrp.py` — IN-02
- `backend/tests/portfolio/test_optimizer.py` — +11 orchestrator-level regression tests
- `backend/tests/portfolio/test_snapshot_binding.py` — WR-03 + IN-04 tests
- `backend/tests/portfolio/test_pipeline.py`, `test_repository.py` — `risk_model_detail` consumer updates + `fixture_mode`

## Test results

```
cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short
74 passed

cd backend && .venv/bin/python -m pytest tests/portfolio tests/research/test_models.py tests/test_operational_migrations.py -q --tb=short
93 passed
```

---

_Fixed: 2026-08-02_
_Fixer: Claude (gsd-code-fixer)_
_Commits: 871a802, 93a4aeb_
