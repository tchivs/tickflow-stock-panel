---
phase: 10
plan: 10-05
name: Admission + Evaluation Breadth
subsystem: factor-library-multi-factor-model
tags: [admission, evaluation, catalog, evidence, refactor]
requires: [10-01, 10-04]
provides: [candidate-trails, monthly-evidence-artifact, catalog-evidence-keys, chain-delegation]
affects: [backend/app/research/admission.py, backend/app/research/evaluation.py, backend/app/research/artifacts.py, backend/app/research/catalog.py, backend/tests/research/test_admission.py, backend/tests/research/test_factor_evaluation.py, backend/tests/research/test_experiment_catalog.py, backend/tests/research/test_signal_chain.py]
tech-stack:
  added: []
  patterns:
    - "candidate trail carries provenance + evaluation_run_id + ExperimentSnapshot.id + ordered gate results for admissions AND rejections"
    - "IC-correlation dedup (per-date IC Pearson on val window) alongside Jaccard structural score in the similarity_dedup gate verdict"
    - "monthly_series.json checksummed artifact via EvaluationArtifactService.write_bundle (additive descriptor)"
    - "evaluation delegates fully to FactorSignalChain.compute; no second factor-value implementation"
key-files:
  created: []
  modified:
    - backend/app/research/admission.py
    - backend/app/research/evaluation.py
    - backend/app/research/artifacts.py
    - backend/app/research/catalog.py
    - backend/tests/research/test_admission.py
    - backend/tests/research/test_factor_evaluation.py
    - backend/tests/research/test_experiment_catalog.py
    - backend/tests/research/test_signal_chain.py
decisions:
  - "MIN_TRAIN_OBSERVATIONS=40 enforced in the train_ic gate: a train window with fewer rebalance dates rejects with a recorded gate failure"
  - "IC-correlation series aligned on the sorted val-window dates; degenerate (constant) series yield 0.0"
  - "Admission orchestration records the evaluation it ran when catalog+artifact_service are supplied; references are optional so callers without catalog wiring (existing tests/pipeline) keep working"
  - "Legacy _evaluate_panel/_rebalance/_required_columns/_correlation_series deleted from evaluation.py; the per-date correlation series moved to a module-level helper _per_date_correlation_series"
  - "evaluation.py no longer imports parse_factor/compile_factor; revision-binding validation delegated to the chain"
metrics:
  duration: "~1.2h"
  completed: "2026-08-01"
status: complete
---

# Phase 10 Plan 5: Admission + Evaluation Breadth Summary

## One-liner

Production candidate trails for every admission verdict (provenance + catalogued evaluation references + ordered gate results, including rejections), IC-correlation dedup on the val window, `MIN_TRAIN_OBSERVATIONS=40` enforcement, the monthly evidence series persisted as a checksummed artifact, resolved-universe pre-filter coverage, and deletion of the legacy `_evaluate_panel` adapter so evaluation delegates fully to the shared signal chain.

## Objective

Harden the 10-01 tracer's admission pipeline and evaluation evidence to production reality (FACT-01/FACT-02): audit-grade candidate trails linked to real catalogued evaluation runs, IC-correlation dedup that catches what Jaccard structural similarity misses, `MIN_TRAIN_OBSERVATIONS` enforcement, the monthly evidence series as a checksummed `monthly_series.json` artifact, coverage computed on the production resolved universe pre-filter, and a closed evaluation seam (no second factor-value implementation).

## Tasks Completed

### 1. build — Production candidate trails + IC-correlation dedup + `MIN_TRAIN_OBSERVATIONS` (commit `9dddeba`, `9a181ab`)

- `run_admission` gains optional `catalog`/`artifact_service` parameters. When supplied, the admission orchestration runs the evaluation it performed through `FactorEvaluationService.evaluate` and links `ExperimentCatalog.record_factor_evaluation` → `ExperimentSnapshot.id`.
- Every verdict — admission AND rejection — now carries a full candidate trail: `provenance` (from `FactorRevision.provenance`), `evaluation_run_ids`, `experiment_snapshot_ids`, and every gate result in order (`candidate_trail_json`).
- `MIN_TRAIN_OBSERVATIONS = 40` is enforced in the `train_ic` gate: the train window must have ≥ 40 rebalance dates or the run rejects with a recorded gate failure (deterministic 70/30 split by date order).
- IC-correlation dedup against the ADMITTED set: candidate and admitted per-date IC series computed on the val window, `pearson(IC_cand, IC_admitted)`; series aligned on the sorted val dates. Both the Jaccard structural score (`discover_similar`, untouched) and the IC correlation are written into the `similarity_dedup` gate verdict.

### 2. test — `test_admission.py` trail, rejection, determinism, IC-corr dedup (commit `5ead3d4`)

- Every gate result recorded in `gates_json` (admitted and rejected).
- An admission verdict carries the full candidate trail with a real `evaluation_run_id` + `ExperimentSnapshot.id` wired from a catalogued evaluation.
- Temporal split deterministic — two runs on the same dates produce identical train/val boundaries (70/30 by date order).
- IC-correlation dedup catches a structurally-different twin (`close` vs `close * 1.0 + 0.0`, Jaccard 0.3 < 0.8 but IC correlation 1.0) — the verdict records the IC-corr failure.
- `MIN_TRAIN_OBSERVATIONS` short-window rejection: a 56-date window yields 38 train observations and rejects on `train_ic` with the recorded gate failure.

### 3. build — Monthly evidence artifact + resolved-universe coverage (commit `9dddeba`)

- `EvaluationArtifactService.write_bundle` gains an additive `monthly_series` parameter writing `monthly_series.json` (per-month IC/RankIC/ICIR/robustness rows) — existing descriptors unchanged.
- The `compact_result` written to `result.json` carries `icir`, `monthly_robustness`, `coverage`, and `monthly_ic_series`.
- Coverage is computed on the production resolved universe pre-filter (10-04 chain's per-date finite counts), so delisted/not-yet-listed symbols are excluded from the coverage cross-section.

### 4. test — `test_factor_evaluation.py` monthly artifact + resolved-universe coverage (commit `645e4a0`)

- The evidence bundle contains `monthly_series.json` with a descriptor whose `checksum_sha256` matches the file bytes.
- Coverage on a panel where a symbol is excluded by the resolved universe on some dates reflects the exclusion pre-filter; a member non-finite row makes coverage 2/3 (not 4/4 and not post-filter 1.0).
- `result.json` compact_result carries the three scalar metrics and the monthly series.

### 5. build — Catalog evidence keys (commit `9dddeba`)

- `record_factor_evaluation` metrics map records `icir`, `monthly_robustness`, `coverage`, `monthly_ic_series` alongside IC/RankIC (additive — `_compatibility_warnings` unaffected).
- `FactorEvidencePackage.metrics` and `ExperimentSnapshot` round-trip the new keys through the repository `_json` canonical serialization.

### 6. test — `test_experiment_catalog.py` new evidence keys round-trip (commit `7847dc7`)

- A completed `FactorEvaluationResult` carrying `icir`, `monthly_robustness`, `coverage`, `monthly_ic_series` persists through `ExperimentSnapshot.metrics`; `as_dict()` round-trips them unchanged across the immutable catalog boundary.

### 7. refactor — Delete legacy `_evaluate_panel` adapter (commit `9dddeba`, `7847dc7`)

- `FactorEvaluationService._evaluate_panel`, `_rebalance`, `_required_columns`, and `_correlation_series` deleted from `evaluation.py`.
- The per-date correlation series moved to a module-level `_per_date_correlation_series` helper; `evaluate()` delegates fully to `FactorSignalChain.compute`.
- `evaluation.py` no longer imports `parse_factor`/`compile_factor`; revision-binding validation delegated to the chain.
- The cross-consumer equality test in `test_signal_chain.py` now asserts `chain.compute(...)` equals a FROZEN expected `FactorSignalFrame` (columns, values, `panel_fingerprint`, `resolved_universe` block) instead of comparing `chain == _evaluate_panel`.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/research/test_admission.py tests/research/test_factor_evaluation.py tests/research/test_experiment_catalog.py -q --tb=short
```

**Result: 29 passed** (per-plan gate). Full research suite: 96 passed. Signal-chain suite (incl. frozen-frame test): 8 passed.

Grep gate (refactor task):

```bash
grep -rl "parse_factor\|compile_factor" backend/app --include="*.py"
```

lists only `hypotheses.py`, `factor_registry.py`, `signal_chain.py`, `factor_dsl.py`, `api/research.py`, `main.py` — `evaluation.py` is no longer a `parse_factor`/`compile_factor` importer. **Pre-existing legitimate importers documented:** `factor_registry.py` (parse in create/revise/discover_similar), `hypotheses.py` (parse provider drafts / reviewed expressions), `api/research.py` + `main.py` (parse user expressions at the API boundary). These are DSL validation entry points, not second factor-value implementations; `signal_chain.py` + `factor_dsl.py` remain the only factor-value computation path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_validated_revision` re-parsed the revision, keeping a latent second compile path in evaluation**
- **Found during:** Task 7 (refactor)
- **Issue:** `_validated_revision` called `parse_factor(revision.canonical_expression)` and re-ran the DSL-version/fields binding checks that `FactorSignalChain._binding` already performs — a second parse entry point in the evaluation module.
- **Fix:** `_validated_revision` now only fetches the revision; binding validation is delegated entirely to the chain.
- **Files modified:** backend/app/research/evaluation.py
- **Commit:** 9dddeba

**2. [Rule 1 - Bug] IC-correlation series alignment**
- **Found during:** Task 1 verification
- **Issue:** Candidate and admitted per-date IC series could be misaligned when their date sets differed; the naive truncation-by-position paired non-corresponding dates.
- **Fix:** Both series are built over the same sorted val-window dates (common finite overlap), so the Pearson is computed on a consistent temporal alignment.
- **Files modified:** backend/app/research/admission.py
- **Commit:** 9a181ab

### Documented structural deviation

**Candidate-trail evaluation references are optional.** The plan's "real run" wiring requires `catalog` + `artifact_service`; `run_admission` callers without them (the existing 10-01 test scaffolds and the pipeline tracer) keep empty `evaluation_run_ids`/`experiment_snapshot_ids` rather than raising. This preserves backward compatibility while the new tests exercise the full catalogued path. The trail always carries provenance + gate results regardless.

## Auth Gates

None — no external authentication was required.

## Known Stubs

None. All evidence paths are wired to real data; no placeholder metrics or empty data sources remain.

## Threat Flags

None — no new network endpoints, auth paths, file-access patterns, or schema changes at trust boundaries beyond the plan's `<threat_model>` (T-10-05 additive evidence keys, T-10-06 verdict trail integrity — both mitigated as planned).

## Self-Check: PASSED

- `backend/app/research/admission.py` — modified, imports OK
- `backend/app/research/evaluation.py` — modified; no `parse_factor`/`compile_factor`, no legacy `_evaluate_panel`/`_correlation_series`/`_required_columns`/`_rebalance` method definitions
- `backend/app/research/artifacts.py` — modified; `write_bundle` accepts additive `monthly_series`
- `backend/app/research/catalog.py` — modified (docstring); metrics map already carried the four evidence keys
- `backend/tests/research/test_admission.py` — 8 passed
- `backend/tests/research/test_factor_evaluation.py` — 15 passed
- `backend/tests/research/test_experiment_catalog.py` — 6 passed
- `backend/tests/research/test_signal_chain.py` — 8 passed (incl. frozen-frame cross-consumer test)
- Per-plan gate `test_admission.py + test_factor_evaluation.py + test_experiment_catalog.py`: **29 passed**
- Grep gate lists only `hypotheses.py`, `factor_registry.py`, `signal_chain.py`, `factor_dsl.py`, `api/research.py`, `main.py`
