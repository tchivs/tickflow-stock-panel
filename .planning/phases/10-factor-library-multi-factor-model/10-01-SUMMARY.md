---
phase: 10-factor-library-multi-factor-model
plan: 10-01
subsystem: research
tags: [tracer, signal-chain, admission, evaluation, composite, catalog, FACT-01, FACT-02, FACT-03, FACT-04, FACT-05, FACT-06]
requires: [10-02, 10-03]
provides: [signal_chain.py, admission.py, models.py, evaluation-upgrade, catalog-evidence-keys, tracer-test]
affects: [10-04, 10-05, 10-06, 11]
tech-stack:
  added: [signal_chain.py, admission.py, models.py, FactorSignalFrame, SignalChainConfig, CompositeModel]
  patterns: [revision-panel binding, temporal 70/30 split, pre-filter coverage, immutable append-only verdicts, orthogonal Hadamard fixtures]
key-files:
  created: [backend/app/research/signal_chain.py, backend/app/research/admission.py, backend/app/research/models.py, backend/tests/research/test_factor_pipeline.py]
  modified: [backend/app/research/evaluation.py, backend/app/research/catalog.py, backend/tests/research/test_signal_chain.py, backend/tests/research/test_admission.py, backend/tests/research/test_models.py, backend/tests/research/test_factor_evaluation.py, backend/tests/research/test_experiment_catalog.py]
decisions:
  - "FactorSignalChain is the single compile-to-compute path; evaluation + models consume it; the legacy _evaluate_panel adapter stays only as the sanctioned cross-consumer-equality reference until 10-05"
  - "IC-weighted composite uses catalogued mean IC (NOT ICIR) per CONTEXT"
  - "coverage is computed from the chain's PRE-FILTER finite counts over the resolved universe (never the post-filter frame)"
  - "shifted-label leakage frame is sorted (symbol, date) because the displaced label is row-order sensitive"
  - "MIN_TRAIN_OBSERVATIONS enforced as an additional train_ic gate condition (Rule 2 — missing critical correctness gate)"
metrics:
  duration: 90
  completed: 2026-08-01
status: complete
---

# Phase 10 Plan 10-01: Tracer — End-to-End Factor Pipeline Summary

End-to-end factor spine proven on a deterministic orthogonal fixture: shared signal chain → 5-gate admission with append-only verdicts (admission AND rejection) → evaluation with IC/RankIC/ICIR/monthly-robustness/coverage + monthly series → deterministic equal/IC-weighted composite (immutable input snapshot) → catalogued evidence with the new metrics (FACT-01..06).

## Tasks Completed

| # | Task | Commit |
|---|------|--------|
| 1 | Create `research/signal_chain.py` + turn `test_signal_chain.py` green | `986f99d` |
| 2 | Refactor `evaluation.py` to delegate to the chain + ICIR/robustness/coverage | `d11cdb2` |
| 3 | Extend `test_factor_evaluation.py` — evidence correctness vs NumPy reference | `d11cdb2` |
| 4 | Create `research/admission.py` — 5-gate pipeline + append-only verdicts | `f3dda67` |
| 5 | Create `research/models.py` + catalog evidence keys | `0ed48d0` |
| 6 | End-to-end tracer proof `test_factor_pipeline.py` (incl. rejection path) | `3a71d1f`, `47e55a5` |
| 7 | Extend `test_experiment_catalog.py` — new evidence keys in snapshot | `29066ad` |

## Verification

Per-plan gate (all green):

```
cd backend && .venv/bin/python -m pytest \
  tests/research/test_factor_pipeline.py \
  tests/research/test_signal_chain.py \
  tests/research/test_factor_evaluation.py \
  tests/research/test_admission.py \
  tests/research/test_models.py \
  tests/research/test_experiment_catalog.py \
  -q --tb=short
→ 32 passed
```

Broader regression: `pytest tests/research/` → 77 passed (only errors are the 4 `test_universe_resolution.py` ModuleNotFoundError failures, which 10-04 resolves — out of scope for 10-01). `test_operational_migrations.py` → 8 passed. Lazy-import audit: `sklearn` not in `sys.modules` after importing signal_chain/admission/evaluation/models/catalog.

FACT-06 grep contract: `parse_factor`/`compile_factor` imported only by `factor_dsl.py`, `signal_chain.py`, and the legacy sanctioned `evaluation._validated_revision` adapter plus `factor_registry`/`hypotheses` (registry/hypotheses parse for definition/registration, not factor-value computation — they do not compute values).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Shifted-label leakage gate was row-order non-deterministic**
- **Found during:** Task 6 (pipeline test construction)
- **Issue:** `shifted_label_ic` displaces the label via `shift().over("symbol")`, which is row-order sensitive; a join with the close column produced a non-deterministic row order, making the leakage metric (and thus the admission verdict) vary run-to-run on the same panel.
- **Fix:** admission joins the close column back and sorts the leakage frame by `(symbol, date)` before invoking `shifted_label_ic`.
- **Files modified:** `backend/app/research/admission.py`
- **Commit:** `3a71d1f`

**2. [Rule 2 - Missing critical functionality] `MIN_TRAIN_OBSERVATIONS` was not enforced in the train_ic gate**
- **Found during:** Task 4
- **Issue:** The plan/research defines `MIN_TRAIN_OBSERVATIONS = 40` as the ICIR-stability floor, but the first implementation only checked the mean-IC threshold; a 2-date fixture could pass gate 4.
- **Fix:** gate 4 now requires `train_observations >= MIN_TRAIN_OBSERVATIONS` AND `mean_ic_train >= TRAIN_MIN_MEAN_IC`, with the observation count in the gate detail.
- **Files modified:** `backend/app/research/admission.py`
- **Commit:** `f3dda67`

**3. [Rule 3 - Blocking] Wave 0 RED scaffolds contained defects that were fixed while turning them green**
- **Found during:** Tasks 1, 4, 5
- **Issue:** (a) `test_admission.py::test_temporal_split_is_deterministic` re-ran `run_admission` twice on the same revision, which contradicts the append-only `UNIQUE(revision_id, policy_version)` contract asserted by the very next test — rewritten to test `temporal_split` determinism directly. (b) `test_models.py::test_output_artifact_is_immutable` used run id `"same-run-id"` (not 32-hex, rejected by `ArtifactWriteError` before the immutability path) — fixed to a 32-hex id.
- **Files modified:** `backend/tests/research/test_admission.py`, `backend/tests/research/test_models.py`
- **Commits:** `f3dda67`, `0ed48d0`

**4. [Rule 2 - Missing critical functionality] IC-weighted composite weights require positive catalogued evidence**
- **Found during:** Task 5 design
- **Issue:** `build_composite(weighting="ic_weighted")` must derive `w_r = mean_ic_r / sum(mean_ic)` from recorded evaluation evidence (CONTEXT); an implementation that silently defaulted missing evidence to 0 would produce degenerate weights.
- **Fix:** `_collect_mean_ics` fails closed (`ValueError`) when a revision has no recorded mean-IC evidence or when the weight sum is non-positive.
- **Files modified:** `backend/app/research/models.py`
- **Commit:** `0ed48d0`

### Deferred Items
None. `test_universe_resolution.py` (4 RED scaffold tests) is intentionally deferred to 10-04, which creates `research/universe.py`.

## Known Stubs
None. Every deliverable is wired end-to-end on the fixture.

## Threat Flags
None. No new network endpoints, auth paths, or file access patterns beyond the append-only SQLite tables and immutable artifact bundles already specified by the plan's schema.

## Self-Check: PASSED
All created files exist; all 7 commits present in `git log`; per-plan gate 32/32 green.
