---
phase: 11-portfolio-construction-optimization
reviewed: 2026-08-02T00:00:00Z
depth: standard
files_reviewed: 24
files_reviewed_list:
  - backend/app/portfolio/schemas.py
  - backend/app/portfolio/risk.py
  - backend/app/portfolio/constraints.py
  - backend/app/portfolio/optimizer.py
  - backend/app/portfolio/hrp.py
  - backend/app/portfolio/repository.py
  - backend/app/portfolio/artifacts.py
  - backend/app/portfolio/snapshot.py
  - backend/app/operational/migrations.py
  - backend/app/research/models.py
  - backend/pyproject.toml
  - backend/uv.lock
  - backend/tests/portfolio/conftest.py
  - backend/tests/portfolio/test_risk.py
  - backend/tests/portfolio/test_optimizer.py
  - backend/tests/portfolio/test_hrp.py
  - backend/tests/portfolio/test_repository.py
  - backend/tests/portfolio/test_schemas.py
  - backend/tests/portfolio/test_portfolio_repository.py
  - backend/tests/portfolio/test_snapshot_binding.py
  - backend/tests/portfolio/test_pipeline.py
  - backend/tests/research/test_models.py
  - backend/tests/test_operational_migrations.py
  - backend/tests/portfolio/__pycache__ (excluded — generated)
findings:
  critical: 3
  warning: 7
  info: 6
  total: 16
status: clean
---

# Phase 11: Code Review Report

**Reviewed:** 2026-08-02T00:00:00Z
**Depth:** standard
**Files Reviewed:** 24 (10 app source, 1 operational migration, 2 dependency files, 11 test files)
**Status:** issues_found

## Summary

Adversarial review of the executed Phase 11 "Portfolio Construction & Optimization" implementation against
`11-PLAN.md` / `11-RESEARCH.md` / `11-CONTEXT.md`. All 24 in-scope files were read in full; the portfolio test
suite plus the cross-module research/migration tests were executed and are green (`82 passed`). The cvxpy
QP formulation (long-only `nonneg`, min-cash budget, per-instrument cap, convex `norm1` turnover penalty),
the PSD fail-closed gate, solver/options/status audit capture, HRP determinism, the checksum-verified
composite-snapshot binding (no `build_composite` in `portfolio/`), the industry-cap fail-closed gate, and the
append-only immutable run-record contract are all implemented and locked by tests.

However, three defects violate the phase's own fail-closed and audit contracts: (1) the real composite
binding writes a **phantom `factor_model_composites` row** pointing at a non-existent
`research_artifacts/0000…/signals.json` artifact with a **fabricated 64×`f` `output_sha256`** (verified by
execution — a fresh composite row is appended on every fixture-snapshot run); (2) the pre-solve solver
try/except is **unreachable** for the only real solver-path failure modes (`cp.error.DCPError` / `SolverError`
are bare `Exception` subclasses, not `ValueError`/`RuntimeError` — verified), so a non-PSD covariance, a
`w_prev` length mismatch, or a solver crash **propagates out of `run_optimization` with no `failed` run
recorded**, silently violating PFOL-04/pitfall 3; (3) an **`optimal_inaccurate` solve is silently
re-promoted to `optimal`** with weights persisted, directly contradicting pitfall 4 (the honest-status
contract). Additional warnings cover the unenforced `SOLVER_OPTIONS_ALLOWLIST` whitelist, the
`input_snapshot_sha256` sentinel that silently replaces a failed binding's true identity on every failed run,
the lookahead guard that only checks `earliest_date` (not coverage of `as_of`), a dev-time fixture default
path (`_fixture_returns`) that can land in the production spine, the min-cash *floor* vs *equality* semantic
drift from the locked decision, and a hardcoded `created_at` timestamp.

## Findings Table

| Severity | ID | File | Line / Function | Issue | Recommendation |
|---|---|---|---|---|---|
| BLOCKER | CR-01 | backend/app/portfolio/optimizer.py | 607-634 (`_run_optimization_impl` — snapshot binding side-branch) | When no catalog seam is supplied, `run_optimization` **writes a phantom `factor_model_composites` row**: `insert_model_composite(..., output_sha256="f"*64, artifact_relative_path="research_artifacts/00000000000000000000000000000000/signals.json")` points at a file that is never created; the composite's `output_sha256` never matches any artifact bytes. The run row is bound to a fabricated snapshot identity — a silent integrity break of the composite-snapshot contract (T-11-01 / pitfall 5), and a fresh bogus composite row is appended on **every** fixture-snapshot run (verified: composites 1 → 2). The `input_snapshot_sha256` returned is the hardcoded 64×`f` sentinel, not the snapshot's real identity. | Require the real seam: raise a fail-closed error (recorded as a `failed` run) when `expected_return_method == "composite-zscore-v1"` and neither `catalog`+`data_dir` nor a pre-verified `snapshot` dict with a real `input_snapshot_sha256`/`composite_snapshot_id` is provided. Alternatively register the snapshot row only from a genuine checksum-verified artifact, never a fabricated 64×`f` digest. |
| BLOCKER | CR-02 | backend/app/portfolio/optimizer.py | 481, 746 (`run_optimization` fail-closed wrapper; solver `try/except`) | The solver try/except around `solve_min_vol`/`solve_max_sharpe` catches only `(ValueError, RuntimeError)` — but the only real solver-path failure modes are `cp.error.DCPError` (non-PSD/indefinite `quad_form`, bad `w_prev` shape) and `cp.error.SolverError`, both bare `Exception` subclasses (verified: `DCPError.__mro__ = (DCPError, Exception, BaseException)`). The outer wrapper's `except (SnapshotBindingError, ValueError, RuntimeError, cp.error.SolverError)` misses `DCPError` too. A non-PSD covariance, a `w_prev` length mismatch, or a solver crash therefore **propagates out of `run_optimization` with no `failed` run row** — the exact silent-abort PFOL-04/pitfall 3 forbids. | Catch `cp.error.SolverError` and `cp.error.DCPError` explicitly (or all `cp.error.Error`) in both the inner solve guard and the outer `run_optimization` wrapper, and record a `failed` run with the exception message. Add a test that a non-PSD covariance fed to `solve_min_vol` (no repair) yields a recorded `failed` run. |
| BLOCKER | CR-03 | backend/app/portfolio/optimizer.py | 745-767 (`_run_optimization_impl` status gate); backend/app/portfolio/optimizer.py | 296-319 (`_finalize_result`) | The status gate accepts `optimal_inaccurate` into the success path (writes weights artifacts + run row with `problem_status="optimal_inaccurate"` **and** populated `output_weights_json`/`output_sha256`), and `_finalize_result` reads `w.value` unconditionally when it is not `None` — a solver returning `optimal_inaccurate` (or any non-`optimal` status with partial values) still has its **inaccurate weights persisted as if exact**. This directly contradicts pitfall 4 ("`optimal_inaccurate` treated as success … weights are recorded as if exact") and the test `test_optimal_inaccurate_status_recorded_verbatim`, which only exercises a hand-crafted repository row — the orchestrator path is never covered. | Treat `optimal_inaccurate` as non-optimal in the orchestrator: record a `failed` (or `solver_error`) run with `failure_reason`, no weights artifact, `output_weights_json=None` — or tighten tolerances and re-solve before persisting. Update the existing test to cover the orchestrator path. |
| WARNING | WR-01 | backend/app/portfolio/schemas.py | 20-31 (`SOLVER_OPTIONS_ALLOWLIST`); backend/app/portfolio/optimizer.py | 212-217, 261-268 (`options.update(solver_options)`) | `SOLVER_OPTIONS_ALLOWLIST` is declared "the only accepted solve() options surface" (V5 / T-11-04) but is **never referenced anywhere in `app/`** — a caller-supplied `solver_options` dict (arbitrary keys) is merged verbatim via `options.update(...)` and recorded/forwarded. The whitelist is dead code; the documented option-injection mitigation is not enforced. | Validate `solver_options` against the allowlist (reject unknown keys with `ValueError`) in `solve_min_vol`/`solve_max_sharpe` (or in the `OptimizationRequest` validator), and add a test that a non-whitelisted key is rejected. |
| WARNING | WR-02 | backend/app/portfolio/optimizer.py | 505-543 (`_record_failed_run`) | Every failed run records `"input_snapshot_sha256": "f" * 64` — a fabricated sentinel that replaces the requested composite's true snapshot identity. Downstream consumers cannot distinguish "identity unknown / not bound" from an actual 64×`f` digest, and the sentinel silently collides with the fixture identity used elsewhere in the phase. | For `composite-zscore-v1` failures, resolve the model's real `input_snapshot_sha256` from the catalog before recording; if truly unavailable, record `None`/`""` (schema allows) or a distinct sentinel and document it — never a fake valid-looking digest. |
| WARNING | WR-03 | backend/app/portfolio/snapshot.py | 118-124 (`lookahead guard`) | The lookahead guard only compares `as_of` against `min(row["date"])` — the artifact's **earliest** date. `as_of` later than the last recorded date, or a date on which the artifact has no rows, is not treated as lookahead: the binding fails later with `"no composite cross-section at as_of"` only if no rows match at all, and an `as_of` beyond coverage is recorded as a generic failed run without the documented lookahead semantics. RESEARCH.md specifies "as_of precedes … the panel window" as the guard clause; the *end* of coverage is unchecked. | Also guard `as_of > max(row["date"])` (raise `SnapshotBindingError("as_of precedes composite snapshot coverage")` / a distinct out-of-coverage message), and add a test for `as_of` beyond the last data date. |
| WARNING | WR-04 | backend/app/portfolio/optimizer.py | 442-459, 592-597 (`run_optimization`, `_run_optimization_impl` fixture default) | `run_optimization` silently substitutes `_fixture_returns()` and a hardcoded 12-symbol fixture universe when `returns`/`symbols` are not supplied — a dev/test scaffolding default living inside the production orchestrator. A production caller omitting the risk panel would get a **deterministic random fixture** covariance recorded as a real run, and the run's `as_of` window records the same date twice. The phase contract says covariance comes from a governed `load_panel` read. | Remove the fixture defaults from `run_optimization` (require `returns` + `symbols`, or resolve them from a governed panel / snapshot universe); if kept for tracer compatibility, gate them behind an explicit `fixture_mode=True` flag. |
| WARNING | WR-05 | backend/app/portfolio/optimizer.py | 212, 261 (min-cash budget); 11-RESEARCH.md `## Constraint Stack` | The locked decision and RESEARCH.md specify min-cash as a **floor**: `cp.sum(w) <= 1 - min_cash` (pitfall 7). The implementation uses `cp.sum(w) == 1 - min_cash` (strict budget equality). The rationale (avoid degenerate all-cash min-vol) is legitimate, but the semantic drift is undocumented and the existing test only asserts `1 - sum(w) >= min_cash` with the equality always exactly satisfied — the floor semantics (more cash than required) are never exercised and Phase 14's cash-residue handling may assume the floor. | Either restore the floor inequality (and fix the degenerate-case via the turnover penalty / a small linear term), or document the equality decision as a deliberate deviation in the module docstring and add a test that cash > min_cash is feasible when optimal. |
| WARNING | WR-06 | backend/app/portfolio/optimizer.py | 461 (`created_at`) | `created_at` is hardcoded to `"2026-08-01T00:00:00Z"` for every run (the phase's planning date) instead of the actual run time. The append-only ordering contract (`ORDER BY created_at, id`) still holds per-batch, but the audit record's timestamp is false and non-monotonic across actual run dates; `repository._now()` exists and is unused. | Use `repository._now()` (or a `clock` parameter like `advanced/repository.py`) for `created_at`; add a test asserting `created_at` is a valid UTC ISO timestamp close to `now()`. |
| WARNING | WR-07 | backend/app/portfolio/optimizer.py | 740-756 (solve failure branch) | When the solve raises and the run is recorded as `failed`, the inner branch records `solver_options=dict(DEFAULT_SOLVER_OPTIONS)` verbatim even though **no solve ran** — misleading the audit trail (solver/options were never actually applied). The same fabricated-default pattern appears in the `optimal_inaccurate` handling. | Record `solver_name="n/a"`, `solver_options_json={}` (mirroring the HRP objective path) for pre-solve failures; only record real solver stats when a solve actually ran. |
| INFO | IN-01 | backend/app/portfolio/repository.py | 53-57 (`_record`) | `_record` maps `risk_model_json → "risk_model"`, clobbering the distinct `risk_model` column value with the JSON payload — so `run["risk_model"]` is the whole risk-model dict, and the literal risk-model name (`sample_covariance_v1`) is only reachable as `run["risk_model"]["risk_model"]`. Tests and `test_pipeline` rely on this accidental shape. | Rename the unwrapped key (e.g. `risk_model_detail` / `risk_model_json`) so the audit contract stays unambiguous; update consumers. |
| INFO | IN-02 | backend/app/portfolio/hrp.py | 75-77 (`hrp_weights`), 31 (`_cov_to_corr`) | Determinism relies on scipy's `linkage(..., optimal_ordering=True)` tie-breaking, which is only guaranteed within a scipy version; RESEARCH.md already pins `scipy<1.18` and freezes weights in the run record, so reproducibility holds for recorded runs. Non-blocking; document the version sensitivity in the module docstring. | Add a one-line note that HRP leaf order may change across scipy versions (weights are frozen at record time). |
| INFO | IN-03 | backend/app/portfolio/risk.py | 71-73 (`covariance_sha256`) | `allow_nan=False` raises `ValueError` for any non-finite covariance — but `_build_risk_model` / `write_bundle` never catch it, so a NaN covariance aborts the run via the (unreliable) wrapper. Acceptable fail-closed behavior, but the path is untested. | Add a test that a NaN/Inf covariance produces a recorded `failed` run (after CR-02 is fixed). |
| INFO | IN-04 | backend/app/portfolio/snapshot.py | 95-106 (row parsing) | Rows missing `symbol`/`date`/`composite` are silently skipped; an artifact whose rows are all malformed raises "composite artifact is empty", but a partially malformed artifact is consumed with silently fewer symbols than the artifact claims. | After parsing, verify the parsed row count equals the payload length (fail closed on unexpected structure), or record the skip count. |
| INFO | IN-05 | backend/app/portfolio/artifacts.py | 111-115, 128-129 (`write_bundle` → `_write_json`) | `write_bundle` O_EXCL-creates the namespace, then `_write_json` O_EXCL-creates each file; if a **later** file write fails, the already-written files remain under the namespace (namespace removal is not attempted). Run recording then also fails, leaving orphaned partial bundles. | Wrap the descriptor loop so a failure cleans up the namespace directory; add a failure-injection test. |
| INFO | IN-06 | backend/app/portfolio/optimizer.py | 754-756 | The failed-run inner branch records `output_weights_json={}` (empty dict) rather than `None` for solve failures — the schema's "NULL on failure" semantics; `get_optimization_run` returns `{}` for a failed run, which downstream consumers may read as "zero weights" instead of "no weights". | Record `None` (consistent with the repository-level failed-run path in `_record_failed_run`). |

---

## Critical Issues

### CR-01: Phantom composite snapshot row written by the non-catalog binding path

**File:** `backend/app/portfolio/optimizer.py:607-634` (`_run_optimization_impl` snapshot side-branch)
**Issue:** When `run_optimization` is called without `catalog`+`data_dir` (the fixture/tracer seam used by every
non-catalog test, including `test_pipeline`), and `expected_return_method == "composite-zscore-v1"` with no
`composite_snapshot_id` in the snapshot dict, the orchestrator **writes a new `factor_model_composites` row** whose
`output_sha256` is the fabricated sentinel `"f"*64` and whose `artifact_relative_path` points at
`research_artifacts/00000000000000000000000000000000/signals.json` — a file that is **never created**. The
composite's recorded `output_sha256` therefore never matches any artifact bytes, and the run's
`input_snapshot_sha256` is the same hardcoded 64×`f` sentinel. This breaks the composite-snapshot integrity
contract end to end: a run can carry an audit root (`input_snapshot_sha256`) that no real snapshot artifact
backs (T-11-01, pitfall 5). Execution verified the side effect: after one fixture-snapshot run,
`list_model_composites` grew 1 → 2, with the phantom row present.
**Fix:** Require the real seam for `composite-zscore-v1` — if neither a catalog/checksum-verified artifact path
nor a pre-verified snapshot carrying a genuine `input_snapshot_sha256`/`composite_snapshot_id` is available,
raise a fail-closed `ValueError` that `run_optimization` records as a `failed` run (never write a fabricated
composite row). If the tracer fixture path must remain, register the composite row only after writing real
artifact bytes through `PortfolioArtifactService` and hashing them.

### CR-02: Fail-closed wrapper misses the real solver failure modes (unrecorded aborts)

**File:** `backend/app/portfolio/optimizer.py:481, 746` (`run_optimization` wrapper; inner solve try/except)
**Issue:** The inner `try:` around `solve_min_vol`/`solve_max_sharpe` catches only `(ValueError, RuntimeError)`;
the outer wrapper adds `SnapshotBindingError` and `cp.error.SolverError`. But `cp.error.DCPError` — raised by
`cp.quad_form` on an indefinite matrix, by an ill-shaped `w_prev`, or by a DCP violation — and `cp.error.SolverError`
are both **bare `Exception` subclasses**, not `ValueError`/`RuntimeError` (verified at runtime:
`DCPError.__mro__ == (DCPError, Exception, BaseException)`). Consequently a non-PSD covariance that slips past
the gate, a `w_prev` length mismatch, or a solver crash propagates out of `run_optimization` **with no `failed`
run recorded** — precisely the silent-abort behavior PFOL-04 (failed runs retained with reason) and pitfall 3
forbid. Note `ensure_psd_provenance` is a soft gate: it only checks provenance, so a caller-provided covariance
that was never repaired still reaches `cp.quad_form`.
**Fix:** Catch `cp.error.SolverError` and `cp.error.DCPError` (or the common `cp.error.Error` base) in both the
inner solve guard and the outer `run_optimization` wrapper, and persist a `failed` run with the exception
message. Add an orchestrator test: `run_optimization` with a deliberately indefinite `cov` (bypassing the repair)
must yield a recorded `failed` run, not a raised exception.

### CR-03: `optimal_inaccurate` silently promoted to success with weights persisted

**File:** `backend/app/portfolio/optimizer.py:745-767` (status gate), `296-319` (`_finalize_result`)
**Issue:** The success-path gate is `if status not in {"optimal", "optimal_inaccurate"}` — i.e. `optimal_inaccurate`
is treated as success: weights are written to O_EXCL artifacts, `output_sha256` is recorded, and the run row
carries `problem_status="optimal_inaccurate"` with populated weights. Pitfall 4 exists precisely because OSQP
first-order solutions are frequently `optimal_inaccurate` and "weights are recorded as if exact". The existing
`test_optimal_inaccurate_status_recorded_verbatim` only hand-crafts a repository row — the orchestrator path
(which is what a real OSQP fallback would hit) is never exercised, so the promotion is real and untested.
**Fix:** Treat `optimal_inaccurate` as non-optimal in the orchestrator: record a `failed`/`solver_error` run with
`failure_reason`, no weights artifact, and `output_weights_json=None` (or tighten tolerances and re-solve first).
Update the test to drive the orchestrator path.

## Warnings

### WR-01: Solver-options whitelist is dead code — arbitrary options accepted

**File:** `backend/app/portfolio/schemas.py:20-31`; `backend/app/portfolio/optimizer.py:212-217, 261-268`
**Issue:** `SOLVER_OPTIONS_ALLOWLIST` (V5 / T-11-04 mitigation) is declared but never referenced in `app/`.
`options.update(solver_options)` merges caller-supplied keys verbatim, so a caller can pass arbitrary solver
kwargs (e.g. `verbose`, or any solver-specific key) and have them recorded and forwarded. The documented
"fixed whitelist is the only accepted surface" mitigation is not enforced.
**Fix:** Validate `solver_options` keys against the allowlist in `solve_min_vol`/`solve_max_sharpe` (reject
unknown keys), and add a rejection test.

### WR-02: Failed runs record a fabricated snapshot identity

**File:** `backend/app/portfolio/optimizer.py:505-543` (`_record_failed_run`)
**Issue:** Every failed run records `input_snapshot_sha256="f"*64`. For a `composite-zscore-v1` run whose binding
failed, the run's audit root is a fake 64-hex digest that collides with the phase's fixture identity and cannot
be distinguished from a real value. The "model not found" degradation additionally rewrites
`expected_return_method` to `"none"` — a silent rewrite of the caller's stated intent.
**Fix:** Resolve the requested model's real `input_snapshot_sha256` before recording (or record a documented
`None`/empty sentinel); keep `expected_return_method` verbatim and let `failure_reason` carry the full fact.

### WR-03: Lookahead guard checks only the earliest artifact date

**File:** `backend/app/portfolio/snapshot.py:118-124`
**Issue:** The guard `as_of.isoformat() < earliest_date` rejects only dates before the artifact window's start.
An `as_of` after the last data date (or inside a gap) is not flagged as lookahead; the run fails later with the
generic "no composite cross-section at as_of" rather than the documented out-of-coverage guard, and RESEARCH.md's
"as_of precedes … the panel window" covers both ends.
**Fix:** Also reject `as_of > max(row["date"])` with a specific `SnapshotBindingError`; add a test for as_of beyond
the last data date.

### WR-04: Production orchestrator silently falls back to fixture data

**File:** `backend/app/portfolio/optimizer.py:442-459, 592-597`
**Issue:** `run_optimization` substitutes `_fixture_returns()` and a hardcoded 12-symbol universe when
`returns`/`symbols` are absent — a dev-scaffold default inside the production orchestrator. A caller that forgets
the governed risk panel silently produces a run over deterministic random data with a duplicated as_of window
recorded as a real run.
**Fix:** Require `returns`+`symbols` (or resolve them from a governed panel / the snapshot universe) in
`run_optimization`; if kept for the tracer, gate behind an explicit `fixture_mode` flag.

### WR-05: Min-cash implemented as budget equality, not the locked floor

**File:** `backend/app/portfolio/optimizer.py:212, 261`; contract: `11-RESEARCH.md ## Constraint Stack` (pitfall 7)
**Issue:** The locked decision and research specify `cp.sum(w) <= 1 - min_cash` (a floor). The implementation
uses `cp.sum(w) == 1 - min_cash`. The rationale (avoid the degenerate all-cash min-vol optimum) is defensible,
but the deviation is undocumented and the tests only assert the equality-exact case — the floor semantics Phase 14
cash-residue handling may rely on are never exercised.
**Fix:** Either restore the floor (and fix the degenerate case via the turnover penalty or a tiny linear term),
or document the equality as a deliberate, tested deviation.

### WR-06: `created_at` hardcoded to the planning date

**File:** `backend/app/portfolio/optimizer.py:461`
**Issue:** Every run's `created_at` is `"2026-08-01T00:00:00Z"` (the phase planning date), not the actual run
time. The audit record's timestamp is false and non-monotonic across real run dates; `repository._now()` exists
but is unused by the orchestrator.
**Fix:** Use `repository._now()` (or inject a `clock`) for `created_at`; assert it is a valid UTC timestamp near
`now()` in tests.

### WR-07: Failed solves record fabricated solver/options audit data

**File:** `backend/app/portfolio/optimizer.py:740-756`
**Issue:** When a solve raises and the run is recorded as `failed`, the branch records
`solver_options=dict(DEFAULT_SOLVER_OPTIONS)` even though no solve ran — implying options were applied when they
were not. The same fabricated-default pattern accompanies `optimal_inaccurate` handling.
**Fix:** For pre-solve failures record `solver_name="n/a"`, `solver_options_json={}` (mirroring the HRP path);
only record real solver stats when a solve actually ran.

## Info

### IN-01: `risk_model_json` unwrap key collides with the `risk_model` column

**File:** `backend/app/portfolio/repository.py:53-57`
`_record` maps `risk_model_json → "risk_model"`, overwriting the literal risk-model name with the full JSON
payload; the model name is only reachable as `run["risk_model"]["risk_model"]`. Rename the unwrapped key (e.g.
`risk_model_detail`) for an unambiguous audit contract.

### IN-02: HRP determinism is scipy-version-sensitive

**File:** `backend/app/portfolio/hrp.py:75-77, 31`
`optimal_ordering=True` tie-breaking is deterministic only within a scipy release; weights are frozen at record
time and scipy is pinned `<1.18`, so recorded runs stay reproducible. Document the version sensitivity in the
module docstring.

### IN-03: NaN covariance path is fail-closed but untested

**File:** `backend/app/portfolio/risk.py:71-73`
`covariance_sha256` uses `allow_nan=False`, raising `ValueError` on non-finite covariance. Acceptable, but the
path to a recorded `failed` run is untested (and currently unreliable — see CR-02).

### IN-04: Malformed artifact rows silently dropped

**File:** `backend/app/portfolio/snapshot.py:95-106`
Rows missing `symbol`/`date`/`composite` are skipped silently; a partially malformed artifact is consumed with
fewer symbols than it claims. Fail closed by comparing parsed-row count to payload length.

### IN-05: Partial artifact bundle left behind on mid-write failure

**File:** `backend/app/portfolio/artifacts.py:111-115, 128-129`
If a later file write in `write_bundle` fails, earlier files remain under the O_EXCL namespace (no cleanup
attempt), leaving orphaned partial bundles. Clean up the namespace on failure and add a failure-injection test.

### IN-06: Failed solve records `{}` instead of `None` for output weights

**File:** `backend/app/portfolio/optimizer.py:754-756`
The failed-run branch records `output_weights_json={}` rather than the schema's "NULL on failure" semantics;
downstream consumers may read `{}` as "zero weights". Record `None`, consistent with `_record_failed_run`.

---

## Verdict

**status: findings** — 3 BLOCKER, 7 WARNING, 6 INFO.

The implementation is high quality and the phase's headline contracts are demonstrably met: the cvxpy min-vol QP
with the constraint stack solves correctly (analytical match, active cap/min-cash, turnover anchoring,
determinism), the PSD repair provenance is recorded never-silently with the eigen-clip gate before `quad_form`,
HRP is deterministic and correctly rendered at `(1 - min_cash)`, the composite is consumed by checksum-verified
snapshot through the catalog seam with `input_snapshot_sha256` cross-module equality, the industry cap fails
closed, artifacts are O_EXCL+fsync+sha256 immutable, and the append-only run table with immutability triggers and
the failed⇔reason invariant is solid (all verified by green tests: 82 passed).

But the three BLOCKERs are contract violations, not polish: the phantom composite row (CR-01) silently breaks the
snapshot-integrity audit root, the fail-closed wrapper cannot catch the real solver failure modes (CR-02) so
failures can escape unrecorded, and `optimal_inaccurate` is silently promoted to a persisted success (CR-03). Each
is directly contradicted by a stated PFOL requirement or pitfall in `11-RESEARCH.md`. The fix set is small and
localized to `optimizer.py` (+ one snapshot guard and one schemas validator); after CR-01..03 are resolved, the
warnings should be addressed before Phase 12 builds on this audit contract.

## Resolved

All 16 findings are fixed (3 BLOCKER, 7 WARNING, 6 INFO). Orchestrator-level regression tests were added for the
three BLOCKERs and for WR-01/WR-03/WR-04/WR-06 and IN-03/IN-04/IN-05. Full portfolio + cross-module suite:
`93 passed` (portfolio 74 + research models + operational migrations).

| Finding | Fix commit | Summary |
|---|---|---|
| CR-01 | `871a802` | No fabricated `factor_model_composites` row — resolve the model's registered checksum-bound composite or fail closed (recorded failed run); `test_composite_without_real_seam_records_failed_run_no_phantom_row` |
| CR-02 | `871a802` | Catch `cp.error.DCPError`/`SolverError` (bare `Exception` subclasses) in the inner solve guard + outer wrapper; non-PSD cov / `w_prev` mismatch / solver crash record a failed run; `test_indefinite_covariance_records_failed_run_in_orchestrator` |
| CR-03 | `871a802` | `optimal_inaccurate` → non-optimal `solver_error` run with `failure_reason`, no weights artifact, `output_weights_json=None`; `_finalize_result` extracts weights only for `status == "optimal"`; `test_optimal_inaccurate_status_is_non_optimal_in_orchestrator` |
| WR-01 | `871a802` | `_validate_solver_options` enforces `SOLVER_OPTIONS_ALLOWLIST` in `solve_min_vol`/`solve_max_sharpe`; `test_solver_options_unknown_key_rejected` |
| WR-02 | `871a802` | Failed runs resolve the model's real `input_snapshot_sha256` (or documented `0`*64 sentinel); never `"f"*64`; `expected_return_method` kept verbatim |
| WR-03 | `93a4aeb` | `as_of > max(date)` rejected with `SnapshotBindingError("as_of exceeds composite snapshot coverage")`; `test_lookahead_as_of_after_last_date_fails_closed` |
| WR-04 | `871a802` | Fixture returns/12-symbol default gated behind explicit `fixture_mode`; `test_run_optimization_requires_returns_and_symbols_without_fixture_mode` |
| WR-05 | `871a802` | Min-cash budget equality documented as a deliberate tested deviation (11-01 summary already recorded it); `test_min_cash_equality_is_documented_tested_deviation` |
| WR-06 | `871a802` | `created_at` uses `_now()` (real UTC run time); `test_created_at_is_real_utc_timestamp` |
| WR-07 | `871a802` | Pre-solve failures record `solver_name="n/a"` + `solver_options_json={}` (no fabricated `DEFAULT_SOLVER_OPTIONS`) |
| IN-01 | `871a802` | `risk_model_json` unwraps to `risk_model_detail` (no `risk_model` column collision) |
| IN-02 | `871a802` | `hrp.py` module docstring notes scipy-version-sensitive leaf ordering |
| IN-03 | `871a802` | `test_nan_covariance_records_failed_run` covers the NaN covariance → failed run path |
| IN-04 | `93a4aeb` | Parsed-row count must equal payload length; malformed rows fail closed; `test_malformed_artifact_rows_fail_closed` |
| IN-05 | `871a802` | `write_bundle` removes the namespace on mid-write failure; `test_write_bundle_cleans_up_namespace_on_mid_write_failure` |
| IN-06 | `871a802` | Failed solves record `output_weights_json=None` (not `{}`) |

---

_Reviewed: 2026-08-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Fixed: 2026-08-02 (commits 871a802, 93a4aeb)_
