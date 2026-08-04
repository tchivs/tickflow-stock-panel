---
phase: 12-risk-models-attribution
verified: 2026-08-02T00:00:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 12: Risk Models & Attribution — Verification Report

**Phase Goal:** Researchers can inspect risk exposure and marginal contribution attribution — reconciling exactly to portfolio variance — backed by a risk-model suite whose every PSD repair carries explicit provenance, plus drawdown attribution by instrument and time segment.
**Verified:** 2026-08-02
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | Researcher can inspect risk exposure and marginal contribution attribution for an optimized portfolio, and the attribution reconciles exactly to portfolio variance (cross-module integrity check) (RSK-01) | ✓ VERIFIED | `attribution.py:portfolio_variance/exposure/marginal_contributions/attribution_report/reconcile_attribution` — hard `np.testing.assert_allclose(np.sum(mc), var, rtol=1e-12, atol=1e-15)`; `analyzer.py:run_attribution` (checksum-bound identity + model-selection paths) and `reconcile_all_models`. Behavior proven by named tests run: `test_sum_marginal_contributions_equals_portfolio_variance`, `test_reconcile_attribution_rejects_perturbed_mc_vector`, `test_negative_mc_diversifier_keeps_signed_identity`, `test_run_attribution_model_selection_reconciles_exactly_per_model[4]`, `test_reconcile_all_models_cross_model_matrix`, `test_attribution_spine_end_to_end_on_fixture_run` — all PASSED |
| 2   | Researcher can select among sample, semi-covariance, exponentially weighted, and Ledoit-Wolf risk models, and every PSD repair records method, epsilon, and eigenvalues before/after (RSK-02) | ✓ VERIFIED | `risk.py:semi_covariance/ewma_covariance(λ=0.94)/ledoit_wolf_covariance/make_risk_model_family` — single dispatcher runs check_psd → repair_psd → provenance `{method, epsilon, min_eigenvalue_before, eigenvalues_before, eigenvalues_after}` for all four; `schemas.py:OptimizationRequest.risk_model` (4-model Literal, sample default); `optimizer.py:_build_risk_model` delegates + records verbatim; migration widens runs CHECK to 4-model enum. Behavior proven: `test_make_risk_model_family_dispatches_all_four_models`, `test_run_optimization_records_selected_risk_model_with_checksum_bound_covariance[4]`, per-model formula tests — all PASSED |
| 3   | Researcher can inspect drawdown attribution decomposed by instrument and time segment (RSK-03) | ✓ VERIFIED | `drawdown.py:underwater_curve/drawdown_periods/drawdown_attribution` — per-segment contributions `c_i = Σ_t w_i r_{i,t}` with segment_return computed INDEPENDENTLY `(w @ segment.T).sum()` and hard `assert_allclose(Σc_i, segment_return, rtol=1e-10, atol=1e-15)`; module constants `DRAWDOWN_DEPTH_THRESHOLD=0.02`, `DRAWDOWN_MIN_OBS=2` recorded in evidence; `analyzer.py:run_drawdown` full report + append-only evidence. Behavior proven: `test_drawdown_period_detects_constructed_segment`, `test_drawdown_attribution_segment_identity_holds_exactly`, `test_run_drawdown_full_report_and_evidence_on_fixture_run`, threshold tests — all PASSED |
| 4   | Attribution consumes the Phase 11 run's checksum-verified covariance artifact (`covariance_sha256` + `covariance_artifact_relative_path`) — never a recomputed live covariance — and every analysis lands as an append-only evidence row bound to a checksum-verified artifact | ✓ VERIFIED | `risk.py:load_covariance_artifact` reads artifact bytes via `PortfolioArtifactService.read_artifact` against recorded digest, raises `ArtifactReadError` on mismatch/absence; `analyzer.py:run_attribution` identity path uses it exclusively (`np.cov` absent from attribution/analyzer); O_EXCL+fsync+sha256 analysis artifacts (`artifacts.py:write_analysis_artifact`); append-only evidence rows with `output_sha256` binding. Behavior proven: `test_tampered_covariance_fails_closed_with_no_evidence_row`, `test_tampered_covariance_fails_identity_but_model_selection_reconciles`, `test_run_attribution_missing_covariance_metadata_fails_closed` — PASSED |
| 5   | scikit-learn 1.8.0 is lazy-imported at the risk-model boundary only (never a module-top import); every one of the four risk models records explicit PSD-repair provenance, never silent | ✓ VERIFIED | `from sklearn.covariance import LedoitWolf` only inside `ledoit_wolf_covariance` body (verified by grep — only `risk.py` function body + unrelated `app/shadow/distillation.py`); direct subprocess check `import app.portfolio.risk` → `"sklearn" not in sys.modules` (OK); provenance keys mandatory in `make_risk_model_family` and enforced by `ensure_psd_provenance` fail-closed in optimizer. Behavior proven: `test_risk_module_import_does_not_load_sklearn` PASSED |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `backend/app/portfolio/risk.py` | 4-model suite + dispatcher + sklearn lazy-import boundary | ✓ VERIFIED | semi/EWMA/Ledoit-Wolf builders, `make_risk_model_family`, `load_covariance_artifact`; provenance keys method/epsilon/eigenvalues before/after |
| `backend/app/portfolio/attribution.py` | variance / exposure / MC / hard reconcile / report | ✓ VERIFIED | Signed components, hard `rtol=1e-12` assertion, negative-MC diversifier semantics |
| `backend/app/portfolio/drawdown.py` | underwater / periods / per-instrument × per-segment attribution | ✓ VERIFIED | Segment identity `rtol=1e-10` asserted before any write; thresholds are module constants |
| `backend/app/portfolio/analyzer.py` | run_attribution / reconcile_all_models / run_drawdown orchestrators | ✓ VERIFIED | Checksum-bound load → compute → O_EXCL artifact → append-only evidence; no execution routes |
| `backend/app/portfolio/artifacts.py` | write_analysis_artifact — O_EXCL + fsync + sha256 | ✓ VERIFIED | Inside run's existing namespace; escape guards; read_artifact checksum-verified |
| `backend/app/portfolio/repository.py` | record/get/list attribution evidence | ✓ VERIFIED | Enum + sha256 + reconciliation validation; run_id FK; risk_model filter; append-only |
| `backend/app/operational/migrations.py` | evidence table + 4-model risk_model CHECK widening | ✓ VERIFIED | `portfolio_risk_attribution_evidence` with CHECKs/triggers/FK; option-a rebuild preserves Phase 11 rows |
| `backend/app/portfolio/optimizer.py` | risk_model_name dispatch + verbatim recording | ✓ VERIFIED | `_build_risk_model` delegates to `make_risk_model_family`; selection recorded in run row + risk_model_json |
| `backend/app/portfolio/schemas.py` | OptimizationRequest.risk_model | ✓ VERIFIED | 4-model Literal, default `sample_covariance_v1` |
| `backend/tests/portfolio/` + `tests/test_operational_migrations.py` | per-requirement test contracts | ✓ VERIFIED | 124 passed in `tests/portfolio`; 12 passed migrations; all phase-12 files green |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `analyzer.py` | `artifacts.py` | `load_covariance_artifact` → `read_artifact` against `covariance_sha256` | ✓ WIRED | Identity path never recomputes; tamper raises `ArtifactReadError`, no evidence row |
| `attribution.py` | `analyzer.py` | `reconcile_attribution` hard `sum(MC)==wᵀΣw` (rtol 1e-12) before any evidence write | ✓ WIRED | Exact MC vector reconstructed from report; perturbed-MC test proves the guard |
| `risk.py` | `optimizer.py` | `make_risk_model_family` single PSD-provenance path; `_build_risk_model` dispatches | ✓ WIRED | 4-model parameterized run test proves checksum-bound per-model runs |
| `repository.py` | `migrations.py` | `portfolio_risk_attribution_evidence` append-only; run_id FK; output_sha256 == artifact bytes | ✓ WIRED | Migration tests + repository evidence tests prove constraints and immutability |
| `drawdown.py` | `backtest/engine.py` | underwater semantics follow equity-curve reference; drawdown never calls the engine | ✓ WIRED | `simulate_portfolio` absent from `portfolio/` (grep); returns/weights passed in |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `analyzer.run_attribution` | covariance | run's frozen `covariance.json` artifact, checksum-verified vs `covariance_sha256` | Yes (real recorded matrix) | ✓ FLOWING |
| `analyzer.run_attribution` (selection) | covariance | `make_risk_model_family` recompute from caller returns | Yes (real model covariance) | ✓ FLOWING |
| `analyzer.run_drawdown` | portfolio returns | `weights @ returns.T` from run output_weights + caller panel | Yes (real arithmetic) | ✓ FLOWING |
| `repository.record_attribution_evidence` | output_sha256 | `ArtifactDescriptor.checksum_sha256` of O_EXCL analysis artifact | Yes (binds evidence to bytes) | ✓ FLOWING |
| Evidence rows | risk_model / reconciliation | Selected model verbatim + reconciliation payload (variance/segment invariants) | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| sum(MC)==variance hard reconcile (rtol 1e-12) | `pytest test_attribution.py -q` (12) + named model-selection cases (4) | PASS | ✓ PASS |
| Segment identity Σc_i==segment_return (rtol 1e-10) | `pytest test_drawdown.py::test_drawdown_attribution_segment_identity_holds_exactly` | PASS | ✓ PASS |
| Cross-model matrix all-reconciled | `pytest test_attribution.py::test_reconcile_all_models_cross_model_matrix` | PASS | ✓ PASS |
| Tamper fail-closed (no evidence row) | `pytest test_attribution.py::test_tampered_covariance_fails_closed_with_no_evidence_row` | PASS | ✓ PASS |
| sklearn lazy-import gate | `python -c "import app.portfolio.risk; assert 'sklearn' not in sys.modules"` | OK | ✓ PASS |
| Evidence FK + append-only | `pytest test_operational_migrations.py -q` (12) | PASS | ✓ PASS |
| 4-model optimization runs checksum-bound | `pytest test_pipeline.py -q` (parameterized 4 models) | PASS | ✓ PASS |

### Probe Execution

No `probe-*.sh` scripts declared in PLAN/SUMMARY for this phase; verification used the plan's documented pytest commands (Step 7b). N/A.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| RSK-01 | 12-01/12-04/12-05 | Exposure + marginal contribution attribution reconciling to portfolio variance (cross-module integrity) | ✓ SATISFIED | `attribution.py` + `analyzer.run_attribution` + `test_attribution.py` (12 passed) + pipeline tracer |
| RSK-02 | 12-02/12-03/12-05 | Semi / EWMA / Ledoit-Wolf with explicit PSD provenance; sklearn lazy-import | ✓ SATISFIED | `risk.py` + `schemas.py`/`optimizer.py` + `test_risk.py` (16 passed) + 4-model pipeline runs |
| RSK-03 | 12-01/12-06 | Drawdown attribution decomposed by instrument and time segment | ✓ SATISFIED | `drawdown.py` + `analyzer.run_drawdown` + `test_drawdown.py` (12 passed) |

No orphaned requirements: RSK-01..03 all claimed by phase plans and all satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | none | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` markers, no stubs, no empty implementations, no hardcoded empty data in phase files |

### Cross-Module Integrity

- **sum(MC) == wᵀΣw, rtol 1e-12 hard assert** — `attribution.py:reconcile_attribution` (`np.testing.assert_allclose(np.sum(mc), var, rtol=1e-12, atol=1e-15)`), invoked inside `attribution_report` before any evidence write; proven by perturbed-MC rejection and per-model exact reconciliation tests. ✓
- **Segment identity Σc_i == segment_return, rtol 1e-10** — `drawdown.py:drawdown_attribution`, segment_return computed independently `(w @ segment.T).sum()` (not a tautology), asserted before any write; proven by `test_drawdown_attribution_segment_identity_holds_exactly`. ✓
- **Evidence FK to runs** — `portfolio_risk_attribution_evidence.run_id REFERENCES portfolio_optimization_runs(id) ON DELETE RESTRICT` in the migration; repository enforces `PRAGMA foreign_keys = ON`; FK violation raises `sqlite3.IntegrityError` (test-locked). ✓
- **risk_model filter (Phase 15 seam)** — `repository.list_attribution_evidence(risk_model=...)` equality filter validated against the 4-model enum, combinable with run_id/type, positive-int limit fail-closed; test-locked. ✓
- **covariance_sha256 checksum-bound** — identity path loads only the run's artifact bytes verified against the recorded digest; tamper → `ArtifactReadError`, no evidence row; WR-03 adds digest + `covariance_source` (`"artifact"`/`"recompute"`) to artifact payload and evidence `reconciliation_json` so Phase 15 consumers can distinguish identity vs recompute. ✓
- **sklearn lazy-import gate** — `sklearn` import only inside `ledoit_wolf_covariance` body; direct check `import app.portfolio.risk` leaves `"sklearn" not in sys.modules`; subprocess test locks it. ✓

### Boundary: No Execution Authority

- Grep across `backend/app/portfolio/` for `broker|place_order|submit_order|live_execution|execution_adapter|execution_route|rebalance.*execute|def.*execute.*order` → **no matches**.
- `analyzer.py` is a read/analyze layer: loads immutable run records, writes only O_EXCL analysis artifacts under the run's existing namespace, and appends evidence rows. It never modifies run records and exposes no execution route.
- No API endpoint, UI affordance, or service path in the phase's scope can push a plan to a live broker (consistent with the milestone hard acceptance criterion; Phase 14 owns the boundary).

### Review Fixes Confirmed Live in Source (12-REVIEW → clean)

| Finding | Fix | Verified in Source |
| ------- | --- | ------------------ |
| WR-01 | Finiteness gate in `run_attribution` selection branch | `analyzer.py` `if not np.all(np.isfinite(panel)): raise ValueError("returns must be finite")`; test `test_run_attribution_model_selection_non_finite_returns_fail_closed` PASSED |
| WR-02 | `underwater_curve` rejects returns ≤ −1.0 | `drawdown.py` `if np.any(returns <= -1.0): raise ValueError(...)`; test `test_underwater_curve_rejects_returns_at_or_below_minus_one` PASSED |
| WR-03 | `covariance_sha256` + `covariance_source` in evidence | `analyzer.py` records both in artifact payload and `reconciliation_json` on identity and selection paths; tests assert `"artifact"` digest-match and `"recompute"` provenance PASSED |
| WR-04 | Finiteness gate at top of `reconcile_all_models` | `analyzer.py` gate before the 4-model loop; test `test_reconcile_all_models_non_finite_returns_fail_closed` PASSED |
| IN-02 | `load_covariance_artifact` `.get()` + `ArtifactReadError` on missing metadata | `risk.py`; test `test_run_attribution_missing_covariance_metadata_fails_closed` PASSED |

IN-01/03/04/05/06/07 (docstring clarifications, intentional alias comment, CHECK-drop comment, strict-depth docstring, normalization docstring) confirmed present in source comments. IN-08 (evidence id 32-hex) intentionally skipped per review — low priority, consistent with runs-table convention; not a gap for this phase.

### Human Verification Required

None. All behavior-dependent truths (reconciliation invariants, tamper fail-closed, segment identity, lazy-import gate, fail-closed input gates) are exercised by passing named tests run directly in this verification. No visual/real-time/external-service behaviors in scope.

### Gaps Summary

No gaps found. All 3 ROADMAP success criteria and all 5 PLAN must-have truths are verified in code with passing behavioral tests. The 12-REVIEW findings (0 blockers, 4 warnings, 7 infos) are all resolved and confirmed live in source.

---

_Verified: 2026-08-02_
_Verifier: Claude (gsd-verifier)_
