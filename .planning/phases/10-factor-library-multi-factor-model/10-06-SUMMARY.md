---
phase: 10
plan: 10-06
name: Composite + Catalog Breadth
subsystem: factor-library-multi-factor-model
tags: [composite, catalog, snapshot, lineage, determinism]
requires: [10-01, 10-05]
provides: [ic-weighted-catalog-evidence, snapshot-immutable-composites, admitted-factor-summaries, composite-catalog-record]
affects: [backend/app/research/models.py, backend/app/research/catalog.py, backend/tests/research/test_models.py, backend/tests/research/test_experiment_catalog.py]
tech-stack:
  added: []
  patterns:
    - "IC-weighted weights read mean IC from the catalog-recorded evidence (ExperimentSnapshot.metrics['ic_summary']['mean']) for the same revision + resolved config; missing evidence fails closed"
    - "composite output persisted via EvaluationArtifactService.write_bundle (O_EXCL + fsync + sha256) with input_snapshot_sha256 bound; factor_model_models + factor_model_composites append-only rows"
    - "admitted-factor summary catalog entries carry coverage (mean + series), finite counts, and revision signature — never full factor-value matrices"
    - "composite model exposed as a first-class catalog record with the latest composite snapshot reference (input_snapshot_sha256 + artifact path)"
key-files:
  created: []
  modified:
    - backend/app/research/models.py
    - backend/app/research/catalog.py
    - backend/tests/research/test_models.py
    - backend/tests/research/test_experiment_catalog.py
decisions:
  - "IC-weighted weights use catalog-recorded mean IC (NOT ICIR — user confirmed 2026-08-01); a revision with no recorded evidence or a missing ic_summary.mean raises ValueError (fail-closed, never silent equal-weight fallback)"
  - "Only the newest matching evidence per revision is used, and only evidence recorded under the same resolved config (universe/window/forward-return horizon); a config naming a different window/horizon is rejected for cross-module integrity"
  - "Composite outputs are written under a per-model run namespace: identical-input rebuilds append NEW composite rows; different-input writes to the same namespace fail on O_EXCL (T-10-04)"
  - "Admitted-factor summaries stored via record_admitted_factor_summary (metrics map carries coverage/finite_counts/factor_signature/factor_lineage only) — full factor matrices are an anti-feature (CONTEXT)"
  - "Composite model catalog record (record_composite_model/get_composite_model) binds definition + latest composite row; Phase 11 consumes by snapshot, never a live module hand-off"
metrics:
  duration: "~1.3h"
  completed: "2026-08-01"
status: complete
---

# Phase 10 Plan 6: Composite + Catalog Breadth Summary

## One-liner

IC-weighted composite weights sourced from catalog-recorded mean IC (cross-module integrity, fail-closed on missing evidence), snapshot-immutable composite outputs bound by `input_snapshot_sha256` through `EvaluationArtifactService.write_bundle` (O_EXCL + fsync + sha256) with append-only `factor_model_models`/`factor_model_composites` rows, and admitted-factor catalog summary storage (coverage, finite counts, signature) with revision lineage plus a first-class composite-model catalog record.

## Objective

Harden the composite model and admitted-factor catalog to production (FACT-03/FACT-05): IC-weighted weights from the catalog-recorded mean IC for the same revision/config, deterministic snapshot-immutable composite outputs consumed by Phase 11 by snapshot, and summary-only admitted-factor storage with revision lineage — turning `test_models.py` + `test_experiment_catalog.py` green.

## Tasks Completed

### 1. build — IC-weighted from catalog evidence + snapshot-immutable composite outputs (commit `c33c8c3`)

- `build_composite` IC-weighted path now resolves `w_r = mean_ic_r / sum mean_ic` from the CATALOG-RECORDED evidence (`ExperimentSnapshot.metrics["ic_summary"]["mean"]` for the same revision + resolved config) — never a live recomputation (cross-module integrity). A revision with no recorded evidence, or evidence with a missing `mean`, raises `ValueError` (fail-closed, never silent equal-weight fallback).
- `_collect_mean_ics` keeps only the NEWEST matching evidence per revision, and only evidence recorded under the same resolved config (universe, window, forward-return horizon) — a config naming a different window/horizon is rejected.
- Composite output persisted immutably: `input_snapshot_sha256` binds `(sorted revision_ids, weighting, membership_fingerprint, panel fingerprints, mean ICs)`; the output frame is written through `EvaluationArtifactService.write_bundle` (O_EXCL + fsync + sha256) under a per-model run namespace; one append-only `factor_model_composites` row records `output_sha256` + `artifact_relative_path` bound to `input_snapshot_sha256`.
- Determinism: revision ids sorted, float64 accumulation, no randomness — two identical builds produce identical `input_snapshot_sha256` and identical composite frames.

### 2. test — `test_models.py` weights, determinism, immutability, fail-closed (commit `c33c8c3`)

- Equal-weight `weights == {r: 1/n}`; IC-weighted weights proportional to catalog-recorded mean IC (`w_r / w_s == mean_ic_r / mean_ic_s`).
- Two identical builds → identical `input_snapshot_sha256`.
- Output artifact immutable: a second write to the same namespace fails with `ArtifactWriteError` (O_EXCL), and the persisted `output_sha256` matches the artifact bytes on disk.
- Repeated compute over the same inputs yields identical composite values.
- Fail-closed: a revision without recorded evidence raises `ValueError("no recorded evaluation evidence ...")`.

### 3. build — Admitted-factor catalog summary storage + revision lineage + composite record (commit `3f702f5`)

- `ExperimentCatalog.record_admitted_factor_summary` persists a summary-only catalog entry: coverage (mean + `coverage_series`), finite counts, and the revision's factor signature (`ast_signature`/`shape_signature`) — summary ONLY, never full factor-value matrices (CONTEXT anti-feature).
- Revision lineage wired: the metrics map carries `factor_id`, `revision_id`, `revision_number` resolving back to the registry revision.
- `ExperimentCatalog.record_composite_model` / `get_composite_model` expose the composite model as a first-class catalog record: definition (model_id, name, weighting, revision_ids, weights, `input_snapshot_sha256`) + LATEST composite snapshot reference (`input_snapshot_sha256`, `output_sha256`, `artifact_relative_path`).
- `AdmittedFactorSummary` / `CompositeModelRecord` frozen dataclasses with `as_dict` (canonical JSON-normalised); `list_admitted_factor_summaries` lists summary entries newest-first.
- `_compatibility_warnings` untouched — all new metrics keys are additive.

### 4. test — `test_experiment_catalog.py` summary + lineage + composite record (commit `3f702f5`)

- An admitted factor's catalog entry contains coverage (mean + series), finite counts, and the revision signature; lineage fields (`factor_id`, `revision_id`, `revision_number`) resolve to the registry revision.
- A composite model recorded in the catalog is retrievable with its latest composite snapshot reference (`input_snapshot_sha256` + artifact path); a second snapshot becomes the new `latest_composite`.
- No full factor-value matrix is persisted — the metrics map carries summaries only (`values`/`frame`/`factor_values`/`panel` absent).

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/research/test_models.py tests/research/test_experiment_catalog.py -q --tb=short
```

**Result: 16 passed** (per-plan gate). Full research suite: **102 passed**.

Manual end-to-end determinism + artifact proof (standalone script): two identical `build_composite(..., artifact_service=...)` runs produced identical `input_snapshot_sha256` and identical frames; each persisted one `factor_model_composites` row whose `input_snapshot_sha256` equals the model's, whose `output_sha256` is 64 hex chars matching the artifact bytes on disk, and whose `signals.json` carries the 4 composite rows `[symbol, date, composite]`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Cross-module config integrity in `_collect_mean_ics`**
- **Found during:** Task 1 verification
- **Issue:** The 10-01 scaffold picked the LAST matching experiment per revision from `list_experiments` (newest-first ordering was inverted) and compared no resolved-config identity — evidence from a different universe/window/horizon could supply the mean IC.
- **Fix:** `_collect_mean_ics` now keeps the first (newest) matching evidence per revision AND requires the same resolved config (universe, start, end, forward-return horizon); a config naming a different window/horizon is rejected for cross-module integrity. Evidence packages carrying no config keys (legacy) still resolve.
- **Files modified:** backend/app/research/models.py
- **Commit:** c33c8c3

**2. [Rule 1 - Bug] Ruff `SIM103`/import-order noise from the config-matching helper**
- **Found during:** Task 1 cleanup
- **Issue:** The `_config_matches` tail triggered `SIM103` and an import-ordering lint on the new test imports.
- **Fix:** Rewrote the tail as an explicit `mismatches` list; re-sorted the test import block and removed a redundant deferred import.
- **Files modified:** backend/app/research/models.py, backend/tests/research/test_models.py
- **Commit:** c33c8c3

### Documented structural deviation

None — plan executed as written; the only plan-text ambiguity (the `…v…` truncation in the first task's action line) was resolved by the schema sketch: one `factor_model_composites` row per computation recording `output_sha256` + `artifact_relative_path` bound to `input_snapshot_sha256`.

## Auth Gates

None — no external authentication was required.

## Known Stubs

None. All composite and catalog paths are wired to real data; no placeholder weights, empty artifact descriptors, or unbound snapshot references remain.

## Threat Flags

None — no new network endpoints, auth paths, file-access patterns, or schema changes at trust boundaries beyond the plan's `<threat_model>` (T-10-04 artifact substitution mitigated via O_EXCL + fsync + sha256 + `input_snapshot_sha256` binding; T-10-05 additive metrics keys; T-10-06 append-only verdict/model rows).

## Self-Check: PASSED

- `backend/app/research/models.py` — modified; imports OK
- `backend/app/research/catalog.py` — modified; imports OK
- `backend/tests/research/test_models.py` — 7 passed
- `backend/tests/research/test_experiment_catalog.py` — 9 passed
- Per-plan gate `test_models.py + test_experiment_catalog.py`: **16 passed**
- Full research suite: **102 passed** (no regressions in `test_factor_pipeline.py`, `test_admission.py`, or the rest of the research suite)
- Manual proof: identical builds → identical `input_snapshot_sha256` + frames; `output_sha256` matches artifact bytes; append-only composite rows bound by snapshot

## Fix Summary (post-review, 2026-08-01)

Code review (10-REVIEW.md, 19 findings) found 2 BLOCKERs, 8 WARNINGs, 9 INFOs in the executed phase code. All were resolved; each fix is an atomic commit.

### BLOCKERs

- **CR-01** `build_composite` equal-weight double-applied the 1/n weight (multiply by 1/n THEN `mean_horizontal` → `mean(z)/n`). Now uses the sum of the weighted z columns (`sum(z_r/n) == mean(z_r)`), matching the IC-weighted branch. Added `test_equal_weight_composite_matches_numeric_reference` asserting composite VALUES against the mean of the raw per-revision z-scores (n=2). Commit `bd78e46`.
- **CR-02** `_ic_correlation_duplicate` truncated both arrays to `min(len)` positionally, pairing a sparse admitted series at mismatched dates (a date-aligned anti-correlated series returned +1.0). Now intersects dates (`common = sorted(set(...) & set(...))`), requires ≥ 2 common dates, and returns the SIGNED worst correlation so anti-correlated twins (−1.0) are flagged as clearly as positive ones. Added `test_ic_correlation_dedup_aligns_sparse_admitted_dates` (positional pairing → +1.0, date-aligned → −1.0). Commit `a4aa43d`.

### WARNINGs

- **WR-01** `_collect_mean_ics` now filters `status == "completed"` AND requires `ic_summary.mean` before selecting the newest evidence (commit `2bd3e56`).
- **WR-02** `MIN_COVERAGE` is now enforced: a coverage gate after `no_lookahead` computes the mean finite share from `resolved_universe["pre_filter_counts"]` and rejects below 0.50; pipeline is now six gates (commit `7961e99`).
- **WR-03** `UniverseResolver(research_repository)` is constructed and injected into `FactorEvaluationService` in `main.py`, plus a best-effort idempotent `seed_membership` startup sync from the instruments dimension (commit `a5d3714`).
- **WR-04** `_resolve_symbols` no longer falls back to DSL field names — it fails closed with a clear error unless explicit symbols or a universe resolver (resolved via its membership) is provided (commit `771dc00`).
- **WR-05** composite artifact `composite_output` now points at `signals.json` where the composite rows actually live (commit `771dc00`).
- **WR-06** `ruff check --fix` + manual fixes: F401 unused imports, F811 duplicate `list_comparison_candidates` deleted (repository.py), RUF100 unused noqa, UP035/UP037/UP017/B009/I001, and explicit `zip(strict=True)` at the B905 sites. `ruff check` now passes clean on the phase files (commit `42687ed`).
- **WR-07** `run_admission` calls `record_admitted_factor_summary` once a factor clears every gate (coverage/finite counts from the same pre_filter_counts), best-effort (commit `3324234`).
- **WR-08** `build_composite` persistence is routed through `catalog.record_composite_model` (constructing an `ExperimentCatalog` from the repo when none is injected) so the snapshot record Phase 11 consumes is always created (commit `01fbaab`).

### INFOs

- **IN-01** pre_filter_counts exclude forward-return-null rows (last horizon days), so coverage measures the usable cross-section (commit `c1a4935`).
- **IN-02** the 70/30 split applies to the full window's rebalance dates, then intersects finite-IC dates (commit `b71b779`).
- **IN-03** manifest `resolved_symbols` records the sorted union of loaded-panel symbols, not the requested config symbols (commit `4190080`).
- **IN-04** same-date listed+delisted events tie-break by `MAX(created_at)` (commit `6772a0d`).
- **IN-05** `seed_membership` only swallows the UNIQUE-conflict ValueError; real errors surface (commit `2996900`).
- **IN-06** documented the `inf` fail-closed verdict in `shifted_label_ic` (commit `57a13af`).
- **IN-07** evaluation evidence recording is deferred until after gate 1 passes, so structurally-invalid factors are rejected without a duplicate evaluation (commit `1c6a500`).
- **IN-08** the empty-panel path preserves the resolved membership fingerprint (commit `26fe989`).
- **IN-09** `get_composite_model` docstring documents the fresh-model-id-per-build semantics (commit `57a13af`).

### Verification

```bash
cd backend && .venv/bin/python -m pytest tests/research -q --tb=short   # 105 passed
.venv/bin/python -m pytest -q --tb=short --ignore=tests/research        # 925 passed, 3 skipped
```

Full backend suite after fixes: **1030 passed, 3 skipped** (was 1027 passed, 3 skipped before review fixes). `ruff check app/research tests/research` → clean.
