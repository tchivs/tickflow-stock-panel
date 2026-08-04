---
phase: 12-risk-models-attribution
plan: 12-05
subsystem: portfolio-risk-attribution
tags: [rsk-01, rsk-02, cross-model, reconciliation-breadth, evidence-api, risk-model-selection]
requires: [12-03, 12-04]
provides: [run_attribution-model-selection, reconcile_all_models, load_covariance_artifact, list_attribution_evidence-risk_model-filter]
affects: [analyzer.py, risk.py, repository.py, test_attribution.py, test_repository.py, phase-15-api]
tech-stack:
  added: [run_attribution risk_model_name selection path, reconcile_all_models cross-model matrix, load_covariance_artifact checksum-bound helper, list_attribution_evidence risk_model equality filter]
  patterns: [two allowed covariance sources (identity artifact checksum-bound vs make_risk_model_family recompute), per-model evidence rows distinct append-only, cross-model matrix as integrity report, fail-closed on missing returns/misalignment]
key-files:
  created: []
  modified:
    - backend/app/portfolio/analyzer.py
    - backend/app/portfolio/risk.py
    - backend/app/portfolio/repository.py
    - backend/tests/portfolio/test_attribution.py
    - backend/tests/portfolio/test_repository.py
decisions:
  - "run_attribution accepts risk_model_name + returns: identity path (risk_model_name=None) consumes ONLY the run's recorded covariance artifact via load_covariance_artifact (checksum-bound, never recomputes); model-selection path recomputes the selected RSK-02 model's covariance from returns via make_risk_model_family (same PSD gate), then reconciles exactly on it"
  - "load_covariance_artifact lives in risk.py (not analyzer.py) — the canonical checksum-verified artifact read; analyzer delegates to it, removing the duplicated private _load_checksum_verified_covariance"
  - "reconcile_all_models is a pure integrity report (no evidence writes): model x variance x sum(MC) x max abs error across all 4 models; identity row (the run's recorded model) is checksum-bound to the run's recorded covariance_sha256; hard-aborts (AssertionError) if any model fails reconciliation"
  - "evidence rows record the ACTUAL model used (evidence_risk_model) — the model-selection path writes risk_model=<selected name>, distinct append-only records per (run, model)"
  - "list_attribution_evidence gains a risk_model equality filter validated against the 4-model enum (fail-closed on unknown), combined with run_id/attribution_type; positive-int limit fail-closed mirrors list_optimization_runs"
  - "model-selection path fails closed when returns is missing or columns misalign with output_weights (no silent fallback to the artifact)"
metrics:
  duration: "~35 min"
  completed: 2026-08-02
status: complete
---

# Phase 12 Plan 05: Cross-Model Attribution + Reconciliation Breadth Summary

One-liner: RSK-01's "reconciles to portfolio variance" now holds under ALL FOUR RSK-02 risk models — `run_attribution` gained a `risk_model_name` selection path that recomputes the selected model's covariance from returns through the same PSD gate, `reconcile_all_models` reports the cross-model matrix (model × variance × sum(MC) × max abs error, identity row checksum-bound to the run's recorded digest), `load_covariance_artifact` is the canonical checksum-bound identity source, and the Phase 15 evidence-list API surface (`list_attribution_evidence` by run/type/risk_model + limit cap) is locked by green tests.

## Objective Achieved

Plan 12-05 closed the two integrity gaps RSK-01/02 share: (1) attribution under ALL FOUR risk models with the EXACT reconciliation asserted per model — the cross-model matrix internally consistent (identity row matches the run's recorded digest path); (2) the Phase 15 evidence-list API surface (`list_attribution_evidence` by run/type/risk_model with the limit cap). The identity path stays checksum-bound — `run_attribution` with no model selection consumes ONLY the run's recorded covariance artifact; a model selection recomputes that model's covariance from the run's returns through `make_risk_model_family` + the same PSD gate, then reconciles exactly on it.

## Tasks Completed

1. **analyzer.py + risk.py — `run_attribution` risk-model selection + `reconcile_all_models` + `load_covariance_artifact`** — added `load_covariance_artifact(run, artifact_service_root)` to `risk.py` (checksum-verified artifact read via `PortfolioArtifactService.read_artifact` against the run's recorded `covariance_sha256`, decode to (n,n), `ArtifactReadError` on mismatch/absence); extended `run_attribution(run_id, *, repository, artifact_service_root, returns=None, risk_model_name=None)` so the identity path uses `load_covariance_artifact` (never recomputes) and the model-selection path recomputes the selected covariance from `returns` via `make_risk_model_family`; evidence rows record the actual model used; added `reconcile_all_models(run_id, *, returns, repository, artifact_service_root)` — the model × variance × sum(MC) × max abs error matrix across all 4 models with the identity row checksum-bound to the run's recorded `covariance_sha256`, hard-aborting on any reconciliation failure. Commit `df5f617`.
2. **repository.py — `list_attribution_evidence` breadth (Phase 15 API)** — added the `risk_model` equality filter (validated against the 4-model enum, fail-closed on unknown), combinable with `run_id` / `attribution_type`; preserved ORDER BY `created_at, id`, the positive-int `limit` fail-closed, and JSON un-wrapping via `_record_evidence`. Commit `d8bceb9`.
3. **test_attribution.py + test_repository.py — cross-model matrix + hard reconciliation per model + evidence filters** — for each of the 4 models on a fixture run: variance ≥ 0, sum(MC) == variance to rtol 1e-12, the evidence row carries the selected risk_model + a checksum-verified artifact read-back; `reconcile_all_models` returns all 4 rows with `all_reconciled == True` and the identity row matches the run's recorded digest; a tampered covariance artifact fails the identity path closed (no evidence row) while the model-selection path (recompute from returns) still reconciles; `list_attribution_evidence(risk_model="semi_covariance_v1")` returns only semi rows; repository-level test locks the risk_model filter + limit fail-closed. Commit `cf78bd2`.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py tests/portfolio/test_repository.py -q --tb=short
```

**Result: 26 passed.**

Per-plan gate (attribution + risk suite):
```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py tests/portfolio/test_risk.py -q --tb=short
```

**Result: 35 passed.**

Grep gates (per plan):
- `np.cov(` appears nowhere in `analyzer.py` — covariance comes only from `load_covariance_artifact` or `make_risk_model_family`. ✔
- Ruff: `ruff check` clean on all 5 touched files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] RUF002 ambiguous `×` in new docstrings**
- **Found during:** ruff check on Task 1 build
- **Issue:** The `×` multiplication sign in the new `reconcile_all_models` docstring triggered ruff RUF002 (ambiguous unicode). The shared analyzer.py module docstring (from Exec1206's committed 12-06 run_drawdown work) also carried `×` — ruff --fix corrected both, making the whole file lint-clean.
- **Fix:** Replaced `×` with `x` in docstrings/comments (via ruff --fix, 3 pre-existing + 1 new instance); no behavioral change.
- **Files modified:** `backend/app/portfolio/analyzer.py`
- **Verification:** `ruff check` clean; 26/35 tests pass.
- **Committed in:** `df5f617` (Task 1 commit)

## Deviations from Plan (scope adjustments)

- **None** — plan executed exactly as written within the 3 tasks. Shared analyzer.py edits were coordinated with Exec1206 (12-06): he committed his run_drawdown work (9c3c6d1) before I layered my run_attribution/reconcile_all_models on top, avoiding interleaved commits.

## Known Stubs

None. `run_attribution` computes the full report from either the checksum-bound artifact (identity) or a recomputed model covariance (selection); `reconcile_all_models` is a pure report with real per-model reconciliation; the evidence list API filters real rows.

## Threat Flags

None — no security-relevant surface beyond the planned read/analyze layer. The model-selection path fails closed on missing/misaligned returns; the identity path remains checksum-bound (tamper → `ArtifactReadError`, no evidence row, test-locked).

## Self-Check: PASSED

- All 5 modified files exist and lint clean.
- 3 commits recorded (df5f617, d8bceb9, cf78bd2), each verified via `git log`.
- Per-plan verification commands: 26 passed (attribution + repository) and 35 passed (attribution + risk suite).
