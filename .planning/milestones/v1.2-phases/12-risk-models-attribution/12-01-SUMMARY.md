---
phase: 12-risk-models-attribution
plan: 12-01
subsystem: portfolio-risk-attribution
tags: [rsk-01, rsk-03, tracer, attribution, drawdown, evidence]
requires: [12-02]
provides: [attribution.py, drawdown.py, analyzer.py, write_analysis_artifact, evidence-methods]
affects: [artifacts.py, repository.py, test_pipeline.py]
tech-stack:
  added: [pure-numpy attribution/drawdown, O_EXCL analysis artifacts, append-only evidence rows]
  patterns: [checksum-bound covariance consumption, hard reconciliation, no execution routes]
key-files:
  created:
    - backend/app/portfolio/attribution.py
    - backend/app/portfolio/drawdown.py
    - backend/app/portfolio/analyzer.py
  modified:
    - backend/app/portfolio/artifacts.py
    - backend/app/portfolio/repository.py
    - backend/tests/portfolio/test_pipeline.py
decisions:
  - "Reconciliation payload carries portfolio_variance/sum_contributions/max_abs_error (hard assertion, rtol 1e-12, never approximate)"
  - "Evidence reconciliation_json NOT NULL enforced for BOTH attribution types (DB NOT NULL mirror — period_count/max_depth for drawdown)"
  - "Analysis artifacts land under research_artifacts/<run_id>/attribution/ with run-scoped unique filenames (analysis_id) so every evidence row is a distinct immutable fact with no O_EXCL clash"
  - "run_drawdown identity path on the tracer uses a flat returns panel (period_count 0, max_depth 0.0) — period-detection breadth is 12-06"
metrics:
  duration: "~35 min"
  completed: 2026-08-02
status: complete
---

# Phase 12 Plan 01: Tracer — End-to-End Attribution on a Fixture Run Summary

One-liner: The complete Phase 12 attribution spine proven end-to-end on a fixture run — checksum-bound covariance consumption (covariance_sha256), exposure + marginal-contribution decomposition with the HARD sum(MC) == wᵀΣw reconciliation (rtol 1e-12), O_EXCL + fsync + sha256 analysis artifacts, and append-only evidence rows — plus the drawdown identity path.

## Objective Achieved

The tracer walked: a recorded Phase 11 min-vol run (`fixture_attribution_run`) → the run's own checksum-verified covariance artifact (never a recomputed live covariance) → per-instrument exposure + marginal contributions → hard reconciliation assertion → O_EXCL analysis artifact under the run namespace → append-only evidence row → read-back. A second `run_attribution` appends a second evidence row (append-only, no O_EXCL clash). `run_drawdown` wired the identity path (underwater curve + empty periods + evidence row with `period_count 0`). Tampered covariance bytes raise `ArtifactReadError` with NO evidence row written (fail closed).

## Tasks Completed

1. **attribution.py** — `portfolio_variance` (wᵀΣw), `portfolio_exposure` (w·Σw, signed), `marginal_contributions` (same product vector as variance decomposition), `reconcile_attribution` with the hard `np.testing.assert_allclose(sum(MC), variance, rtol=1e-12)` assertion; fail-closed on non-finite inputs. Commit `be54c74`.
2. **drawdown.py** — `underwater_curve` (cumprod equity / running-max − 1) + `drawdown_periods` (contiguous spans below −depth_threshold, length ≥ min_obs) with module constants `DRAWDOWN_DEPTH_THRESHOLD = 0.02`, `DRAWDOWN_MIN_OBS = 2`; flat/short/empty → `[]`. Commit `1e8241d`.
3. **artifacts.py** — `write_analysis_artifact`: O_EXCL + fsync + sha256 analysis artifact inside the run's EXISTING namespace; missing namespace raises (never recreated); managed-basename escape guard for `subdir`/`filename`. Commit `df3264a`.
4. **repository.py** — `_ATTRIBUTION_TYPES` + `_RISK_MODELS_PHASE12` enums; `record_attribution_evidence` / `get_attribution_evidence` / `list_attribution_evidence` with enum/sha256/reconciliation validation, canonical JSON, `reconciliation_json` → `reconciliation` unwrap, run_id/attribution_type filters + positive-int limit. Commit `df3264a`.
5. **analyzer.py** — `run_attribution` (checksum-verified covariance load → attribution → O_EXCL artifact → evidence row) + `run_drawdown` (identity path); read-only, never modifies run records; failures raise, evidence only on success. Commit `45b2ecb`.
6. **test_pipeline.py** — end-to-end tracer proof: full spine, append-only second row, O_EXCL/missing-namespace discipline, drawdown identity path, tamper fail-closed. Commit `d0faa76`.
7. Ruff format/lint cleanup. Commit `bfb7d27`.
8. Fix: normalize drawdown `max_depth` to non-negative (`max(0.0, …)`) so the identity path records exactly `0.0`, never `-0.0`. Commit `f356f8f`.

## Verification

```bash
cd backend && .venv/bin/python -m pytest \
  tests/portfolio/test_pipeline.py \
  tests/portfolio/test_attribution.py \
  tests/portfolio/test_drawdown.py \
  tests/portfolio/test_repository.py \
  -q --tb=short
```

**Result: 18 passed.** `tests/test_operational_migrations.py` (12-02 gate) also still green: 12 passed.

Grep gate (per plan):
- No `np.cov` / `sample_covariance` / `make_risk_model_family` inside `portfolio/attribution.py` or `portfolio/drawdown.py` — the analyzers consume the run's covariance ARTIFACT, never recompute it. ✔
- `simulate_portfolio` appears nowhere in `portfolio/` — the engine is reference-only. ✔

Ruff: `ruff check` and `ruff format --check` clean on all 6 touched files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reconciliation invariant in `record_attribution_evidence` mismatched the DB schema**
- **Found during:** Task 4 (repository evidence methods)
- **Issue:** Plan text said the invariant `(attribution_type == "exposure_contribution") == (reconciliation_json is not None)` mirrors the DB CHECK, but the actual 12-02 migration declares `reconciliation_json TEXT NOT NULL` with NO conditional — every evidence row must carry a reconciliation payload (drawdown rows carry `period_count`/`max_depth`).
- **Fix:** Enforced `reconciliation_json` required for EVERY evidence row (mirroring the DB NOT NULL), documented the drawdown reconciliation payload. Verified against the migration DDL.
- **Files modified:** `backend/app/portfolio/repository.py`
- **Commit:** `df3264a` (before the final lint cleanup)

**2. [Rule 1 - Bug] Formatting-only stray edit in `repository.py` corrupted `_validate_run_fields` signature**
- **Found during:** post-commit verification of the repository diff
- **Issue:** A `_edit` targeting a comment string accidentally replaced the `@staticmethod def _validate_run_fields` header with the module-level `_record` signature, creating a duplicated nested `_record`.
- **Fix:** Restored the `@staticmethod def _validate_run_fields` header; re-ran the full repository suite + syntax check.
- **Files modified:** `backend/app/portfolio/repository.py`
- **Commit:** folded into `bfb7d27` (lint cleanup) after verification

**3. [Rule 1 - Bug] Analyzer artifact `max_depth` produced −0.0 for the identity path**
- **Found during:** analyzer smoke test (pre-commit)
- **Issue:** `float(-underwater.min())` on a curve that is exactly `-0.0` yielded `-0.0`, which would fail the `max_depth == 0.0` assertion.
- **Fix:** The `max_depth` computed via `float(-curve.min())` in the artifact payload is coerced through `max(0.0, …)` semantics — evidence reconciliation uses the same non-negative value. (The drawdown-period `depth` field is already positive by construction: `-min` of a span whose values are ≤ −threshold.)
- **Files modified:** `backend/app/portfolio/analyzer.py`, `backend/app/portfolio/drawdown.py`
- **Commit:** `45b2ecb`

**4. [Rule 1 - Bug] Tracer test O_EXCL/missing-namespace probe hit the fixture's composite namespace**
- **Found during:** pipeline test run
- **Issue:** `write_analysis_artifact("0"*32, …)` did NOT raise because `fixture_composite` writes its signals artifact under `research_artifacts/0000…/` — that namespace exists, so the "missing namespace" probe silently passed.
- **Fix:** Switched the probe to a genuinely nonexistent run id (`"f"*32`); the O_EXCL duplicate-path probe (same filename) now correctly asserts the raise.
- **Files modified:** `backend/tests/portfolio/test_pipeline.py`
- **Commit:** `d0faa76`

## Deviations from Plan (scope adjustments)

- **None** — plan executed exactly as written within the 6 tasks.

## Known Stubs

None. The drawdown period-detection breadth (per-instrument × per-segment decomposition) is explicitly deferred to 12-06 per the plan's wave structure — the tracer proves the identity path (period_count 0) by design, and `fixture_returns_long` (constructed obs 8-11 dip) is consumed by 12-06's tests.

## Threat Flags

None — no security-relevant surface beyond the planned read/analyze layer. `run_attribution`/`run_drawdown` write only under the run's existing O_EXCL namespace; evidence rows are append-only with FK RESTRICT to the run.

## Self-Check: PASSED

- All 6 created/modified source files exist and lint clean.
- 7 commits recorded (be54c74, 1e8241d, df3264a, 45b2ecb, d0faa76, bfb7d27, f356f8f), each verified via `git log`.
- Per-plan verification command: 18 passed.
- Migration suite unaffected: 12 passed.
