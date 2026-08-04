---
status: clean
phase: 12-risk-models-attribution
reviewed: 2026-08-02
depth: standard
files_reviewed: 11
findings:
  blocker: 0
  warning: 4
  info: 7
  total: 11
---

# Phase 12: Risk Models & Attribution — Code Review Report

**Reviewed:** 2026-08-02
**Depth:** standard
**Files Reviewed:** 11
**Status:** clean

## Summary

Phase 12 delivers the risk-analysis layer over Phase 11's immutable optimization runs: the four-model risk suite (`risk.py`), exposure + marginal-contribution attribution with hard variance reconciliation (`attribution.py`, `analyzer.py`), drawdown attribution by instrument × time segment (`drawdown.py`, `analyzer.py`), the O_EXCL + fsync + sha256 analysis-artifact seam (`artifacts.py`), append-only attribution evidence (`repository.py`), and the one-way-door migration (`operational/migrations.py`). The full backend suite passes (1155 passed, 3 skipped), including the new `test_attribution` / `test_drawdown` suites, cross-model reconciliation, the tamper fail-closed path, the sklearn lazy-import subprocess gate, and the option-a runs-table rebuild migration.

The core integrity machinery is sound: `sum(MC) == wᵀΣw` is a hard `assert_allclose(rtol=1e-12)` that runs inside `attribution_report` before any evidence write; the segment identity `Σc_i == segment_return` is hard-asserted at `rtol=1e-10`; the identity path loads the run's own covariance artifact checksum-verified against `covariance_sha256` and raises `ArtifactReadError` on tamper with no evidence row written; evidence rows are append-only (triggers + no update/delete surface); and sklearn appears only inside the `ledoit_wolf_covariance` function body (never module-top). No execution authority exists in the layer.

The findings below are WARNING/INFO-level: the main gaps are (1) the model-selection path does not fail closed on non-finite returns (inconsistent with `run_drawdown`), (2) `underwater_curve` does not reject returns ≤ −1, producing NaN/infinite curves that are silently skipped by period detection, and (3) selection-path evidence rows are not checksum-bound to the covariance they used, weakening auditability of the evidence trail.

## Findings

| Severity | File | Line / Function | Issue | Recommendation |
|---|---|---|---|---|
| WARNING | backend/app/portfolio/analyzer.py | L103–109, L203–211 (`run_attribution`, `reconcile_all_models`) | The model-selection path converts `returns` to a panel and passes it straight to `make_risk_model_family` without a finiteness gate. The risk-model builders drop non-finite rows (common-window `dropna`), so a panel with NaNs silently yields a covariance over a reduced window and a valid-looking evidence row. `run_drawdown` (L279) fail-closes on non-finite returns, so the two analyzers have inconsistent contracts. | Add `if not np.all(np.isfinite(panel)): raise ValueError("returns must be finite")` in both the `run_attribution` selection branch and `reconcile_all_models`, mirroring `run_drawdown`. |
| WARNING | backend/app/portfolio/drawdown.py | L47–48 (`underwater_curve`) | `equity = np.cumprod(1.0 + returns)` is unbounded below: a portfolio return of −1.0 (or lower) drives equity to 0/negative, making `equity / np.maximum.accumulate(equity) − 1` produce NaN or meaningless positive/negative values. `drawdown_periods` then treats NaN comparisons as False (silently skipping) — a −100% instrument or bad input corrupts the curve without an error. | Reject non-finite AND `returns <= -1.0` (or validate `equity > 0`) in `underwater_curve`; raise `ValueError` so `run_drawdown`'s fail-closed contract is upheld. |
| WARNING | backend/app/portfolio/analyzer.py | L95–111 (`run_attribution` selection branch); L118–121, L161–170 (payload/evidence) | When the caller selects the run's own recorded model (e.g. `sample_covariance_v1`), the selection path recomputes covariance from caller-supplied `returns` instead of the checksum-bound artifact. The recomputed `covariance_sha256` from `make_risk_model_family` is discarded, and the evidence row/artifact carry no covariance digest or provenance flag. A Phase 15 consumer filtering evidence by `risk_model` cannot distinguish a checksum-bound identity analysis from a caller-returns recompute, and the two can disagree numerically. | Record the covariance source and digest (e.g. add `covariance_sha256` + `covariance_source: "artifact"|"recompute"` to the artifact payload and/or reconciliation), or reject selection of the run's own model on the selection path. |
| WARNING | backend/app/portfolio/analyzer.py | L178–205 (`reconcile_all_models`) | `reconcile_all_models` never validates `panel` finiteness before recomputing the four model covariances. Combined with the dropna behavior in the risk-model builders, a NaN-containing panel silently produces four "reconciled" rows over a reduced window, and `all_reconciled=True` masks the data problem. | Apply the same `np.all(np.isfinite(panel))` gate at the top of `reconcile_all_models` as recommended for `run_attribution`. |
| INFO | backend/app/portfolio/risk.py | L99–105 (`ewma_covariance`) | The `lam == 1.0` special case returns `np.cov(finite)` while the recursion limit as `lam → 1⁻` is `outer(r_1, r_1)` — a documented discontinuity. The recursion also uses raw (non-demeaned) returns, so the result is a second-moment matrix (includes mean²) rather than a covariance about the mean. This is per the plan's locked formula/test contract, but worth an explicit note for Phase 13 consumers. | Document the λ=1.0 discontinuity and the non-demeaned semantics in the module docstring (already partially done); consider demeaning or documenting mean assumptions for walk-forward use. |
| INFO | backend/app/portfolio/risk.py | L295–310 (`load_covariance_artifact`) | Uses direct `run["risk_model_detail"]["covariance_artifact_relative_path"]` / `["covariance_sha256"]` access; a run whose `risk_model_json` lacks these keys (e.g. a hand-inserted row or a Phase 11 run predating the seam) raises `KeyError` rather than the documented `ArtifactReadError`/`ValueError`. | Use `.get(...)` and raise `ArtifactReadError` ("covariance artifact metadata missing") when either key is absent. |
| INFO | backend/app/portfolio/analyzer.py | L43–47 (`_RISK_MODEL_NAMES`) | The 4-model tuple is hardcoded in the analyzer, duplicating `schemas.RiskModel` (Literal) and `repository._RISK_MODELS`/`_RISK_MODELS_PHASE12`. A fifth model added for Phase 13 must be updated in three places or `reconcile_all_models` silently omits it. | Derive the tuple from a single source of truth (e.g. `schemas.RiskModel` values or the repository enum) or add a comment cross-referencing the other two definitions. |
| INFO | backend/app/portfolio/repository.py | L33 (`_RISK_MODELS_PHASE12 = _RISK_MODELS`) | The evidence-table enum is aliased to the runs-table enum. Harmless today (both are the same 4 models), but if Phase 13 ever widens runs-only models, the alias silently widens evidence validation too. | Keep two explicitly-named frozensets or add a comment stating the alias is intentional per the 12-02 option-a decision. |
| INFO | backend/app/operational/migrations.py | L1680–1690 (evidence table DDL) | The plan's schema specified `CHECK ((attribution_type = 'exposure_contribution') = (reconciliation_json IS NOT NULL))`; the migration instead uses `reconciliation_json TEXT NOT NULL` with no conditional CHECK. The plan's own combination was self-contradictory (NOT NULL already forces the RHS to TRUE, rejecting drawdown rows). The implementation's stricter NOT NULL is consistent with the repository and all analyzers always write a reconciliation payload — correct resolution, but a documented deviation. | Add a migration comment noting the plan's conditional CHECK was intentionally dropped in favor of strict NOT NULL. |
| INFO | backend/app/portfolio/drawdown.py | L75 (`drawdown_periods`) | `active = curve < -depth_threshold` is strict, while the docstring ("深度 >= depth_threshold") and plan wording ("深度 ≥ 2%") state `>=`. A drawdown whose underwater sits exactly at the threshold (e.g. exactly −2%) is not flagged. Floating-point exact hits are rare, but the docstring and behavior disagree. | Align the docstring to strict `<` semantics or use `<=` if inclusive boundaries are intended; add a one-line comment. |
| INFO | backend/app/portfolio/risk.py | L44–71 (`semi_covariance`) | Normalization divides by `drops.shape[0]` (all common-window observations), while plan 12-03 text says "normalize by the subset observation count". The module docstring ("normalized by the observation count") and the test contract (`drops.T @ drops / drops.shape[0]`) match the implementation, so this is a plan-wording discrepancy only. | Fix the plan wording or add a docstring note that normalization is over all observations (PyPortfolioOpt contract). |
| INFO | backend/app/portfolio/repository.py | L184–231 (`record_attribution_evidence`) | Evidence `id` is not validated as 32-hex (the analyzer generates `uuid4().hex`, but a direct caller could insert an arbitrary TEXT PK) and `as_of` is not format-checked. Runs-table records have the same convention (id format enforced only at the artifact namespace), so this is consistent, but the evidence PK could be tightened. | Optionally validate `id` against the 32-hex pattern to match `artifacts._RUN_ID`; low priority. |

## Verdict

**Verdict: findings (no blockers).** The Phase 12 implementation meets the core correctness and security contracts:

- **RSK-01** — exposure/MC attribution with hard `sum(MC) == wᵀΣw` (rtol 1e-12) on the run's own checksum-verified covariance artifact; tamper fails closed with no evidence row. ✅
- **RSK-02** — semi/EWMA/Ledoit-Wolf + `make_risk_model_family` single PSD-provenance dispatcher; sklearn lazy-import gate passes (`"sklearn" not in sys.modules` after `import app.portfolio.risk`); per-model provenance (method/epsilon/eigenvalues before/after). ✅
- **RSK-03** — underwater curve → periods → per-instrument × per-segment contributions with hard `Σc_i == segment_return` (rtol 1e-10); thresholds are module constants recorded in evidence. ✅
- **Cross-module** — evidence rows FK to runs, risk_model filter ready for Phase 15, `covariance_sha256` checksum-bound identity path; O_EXCL + fsync + sha256 artifact discipline and append-only triggers verified. ✅
- **Quality** — no `np.cov` in attribution/analyzer (covariance only from artifact or `make_risk_model_family`); signed components never `abs()`ed (negative-MC diversifier fixture); ruff clean; module docstrings follow know/don't-know convention.

The four WARNINGs are robustness/auditability improvements, not correctness failures in the exercised paths: add finiteness gates to the model-selection paths, guard `underwater_curve` against returns ≤ −1, and record the covariance digest/source in selection-path evidence so the audit trail is self-verifying.

**Verification performed:** `pytest tests/portfolio` (120 passed), `pytest tests/portfolio/test_pipeline.py tests/portfolio/test_repository.py tests/test_operational_migrations.py` (26 passed), full `pytest -q` (1155 passed, 3 skipped), `ruff check` on all reviewed files (clean). Pre-existing RuntimeWarnings in `test_nan_covariance_records_failed_run` originate from Phase 11 `sample_covariance`, not Phase 12.

---
_Reviewed: 2026-08-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

## Resolved

All findings fixed and verified 2026-08-02 (commit per finding):

| Finding | Fix commit | Notes |
|---|---|---|
| WR-01 | `e5d8821` | Finiteness gate in `run_attribution` selection branch → `ValueError("returns must be finite")`; regression test asserts no evidence row on NaN panel. |
| WR-02 | `8a930f5` | `underwater_curve` rejects returns `<= -1.0` → `ValueError`; regression test covers exactly −1.0, below, and the −0.9999 boundary. |
| WR-03 | `35543c7` | Selection path (and identity path) record `covariance_sha256` + `covariance_source` (`"recompute"` / `"artifact"`) in artifact payload + evidence `reconciliation_json`; regression tests assert digest/source on both paths. |
| WR-04 | `e1ffa04` | Finiteness gate at top of `reconcile_all_models`; regression test asserts ValueError on inf panel. |
| IN-01 | `a881979` | `ewma_covariance` docstring documents λ=1.0 discontinuity (special-cased jump vs `outer(r_1,r_1)` recursion limit) and non-demeaned second-moment semantics. |
| IN-02 | `a881979` | `load_covariance_artifact` uses `.get()` and raises `ArtifactReadError("covariance artifact metadata missing")` on missing keys (no more bare `KeyError`); regression test. |
| IN-03 | `f88bb5b` | `_RISK_MODEL_NAMES` cross-reference comment pointing at `schemas.RiskModel` / `repository._RISK_MODELS`. |
| IN-04 | `f88bb5b` | Repository alias comment states `_RISK_MODELS_PHASE12 = _RISK_MODELS` is intentional per 12-02 option-a. |
| IN-05 | `f88bb5b` | Migration comment documents the plan's conditional CHECK was intentionally dropped for strict NOT NULL. |
| IN-06 | `f88bb5b` | `drawdown_periods` docstring aligned to strict `>` (curve `< -threshold` ⟺ depth strictly above threshold) with IN-06 note. |
| IN-07 | `a881979` | `semi_covariance` docstring notes normalization is over ALL common-window observations (`drops.shape[0]`, PyPortfolioOpt contract), not the subset count. |

**Verification after fixes:** `pytest tests/portfolio` (124 passed), full `pytest -q --tb=short -p no:cacheprovider --ignore=tests/test_phase5_optional_host.py --ignore=tests/shadow` (1084 passed, 3 skipped), plus the excluded dirs (75 passed) — total 1159 passed, 3 skipped. IN-08 (evidence id 32-hex validation) intentionally skipped per review (low priority, runs-table convention is consistent).
