---
phase: 10-factor-library-multi-factor-model
verified: 2026-08-01T16:45:00Z
status: passed
score: 7/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 10: Factor Library & Multi-Factor Model — Verification Report

**Phase Goal:** Researchers can admit factors through deterministic gates, evaluate them on full monthly evidence, compose them into a deterministic multi-factor expected-return model, and reuse one shared signal chain everywhere — with every verdict and catalog entry immutable.
**Verified:** 2026-08-01
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Admission gates (train/val IC, no-lookahead, no-label-leakage, similarity dedup) run on a candidate factor; every verdict incl. rejections is an immutable append-only record with the candidate trail (FACT-01 / SC-1) | ✓ VERIFIED | `admission.py:run_admission` — six ordered deterministic gates (`no_lookahead`, `coverage`, `no_label_leakage`, `similarity_dedup`, `train_ic`, `val_ic`); every verdict (admission AND rejection) persists one immutable row via `repository.py:insert_admission_verdict` with `gates_json` + `candidate_trail_json` (provenance, evaluation_run_ids, experiment_snapshot_ids, gate_results). Table `factor_admission_verdicts` (migrations.py:1531-1548) has CHECK `verdict IN ('admitted','rejected')`, UNIQUE(revision_id, policy_version), FK RESTRICT, and UPDATE/DELETE ABORT triggers. Tests: `test_admission.py` (gate recording, rejection trail, append-only single-row, IC-corr dedup incl. sparse-date alignment, MIN_TRAIN_OBSERVATIONS); `test_factor_pipeline.py::test_rejection_path_records_identical_verdict`. |
| 2 | Factor evaluation report shows IC, RankIC, ICIR, monthly robustness, coverage with full monthly evidence set (FACT-02 / SC-2) | ✓ VERIFIED | `evaluation.py` — `FactorEvaluationResult` carries `icir`, `monthly_robustness`, `coverage {mean, coverage_series}`, `monthly_ic_series` (monthly IC/RankIC rows); `_monthly_evidence` computes ICIR = mean/std of monthly IC and robustness = positive-month share; `_coverage` from chain pre-filter counts; `monthly_series.json` checksummed artifact via `artifacts.write_bundle`; `catalog.record_factor_evaluation` round-trips the new keys. Tests: `test_factor_evaluation.py` (evidence matches NumPy reference, coverage pre-filter <1.0, resolved-universe exclusion, monthly artifact checksummed, result.json carries monthly set); `test_experiment_catalog.py::test_new_evidence_keys_round_trip_through_catalog_boundary`. |
| 3 | Admitted factors compose into a deterministic multi-factor expected-return model (equal-weight or IC-weighted cross-sectional z-score, no ML) handed to portfolio optimization by immutable snapshot (FACT-03 / SC-3) | ✓ VERIFIED | `models.py:build_composite` — both weightings compute per-revision z-scores through `FactorSignalChain.compute`; equal-weight = mean of per-revision z (CR-01 fix live: `composite_expr = sum(...)` of already-weighted columns, verified numerically by `test_equal_weight_composite_matches_numeric_reference` against an independent reference); IC-weighted `w_r = mean_ic_r/sum` from catalog-recorded evidence only (`_collect_mean_ics` filters `status == "completed"` + `ic_summary.mean`, fail-closed on missing). Output persisted immutably via `EvaluationArtifactService.write_bundle` (O_EXCL+fsync+sha256), one append-only `factor_model_composites` row bound by `input_snapshot_sha256`; persistence routed through `catalog.record_composite_model` (WR-08). Tests: `test_models.py` (uniform weights, identical input sha256, O_EXCL immutability, checksum matches bytes, IC-weights ∝ catalogued mean IC, fail-closed, determinism, numeric reference, symbols-or-resolver); `test_experiment_catalog.py::test_composite_model_record_is_first_class_catalog_record`. |
| 4 | DSL compiler rejects operators lacking partition semantics or referencing denied label fields; shifted-label leakage gate blocks changes (FACT-04 / SC-4) | ✓ VERIFIED | `factor_dsl.py` — `_FUNCTION_PARTITION` beside `_FUNCTION_ARITY` (abs/sign/log1p/clip→pointwise, rank/zscore→per_date, rolling_mean→per_symbol, matching `.over(...)` compile semantics); `_validate_call`/`_validate_expression`/`_compile_node` all raise on missing partition entry; `DENIED_FIELDS` (`date/symbol/label/forward_return/_forward_return/_factor/_rank/_zscore`) rejected by `_validate_field_name` at parser+validator+compile; `shifted_label_ic` deterministic leakage gate (displaced label one extra horizon, returns inf fail-closed on empty cross-section); `DSL_VERSION = "factor-dsl-v2"`. Tests: `test_factor_dsl.py` — arity↔partition consistency, denied-field diagnostics parametrized, effective partition context union, shifted-label collapses ≤0.02 for clean factors (matrix over all partition functions), blocks a lookahead expression, inf on empty cross-section. |
| 5 | Admitted-factor catalog shows summary storage (coverage, finite counts, signature) with revision lineage (FACT-05 / SC-5) | ✓ VERIFIED | `catalog.py:record_admitted_factor_summary` — summary-only entry (coverage mean+series, finite_counts, factor_signature ast/shape, factor_lineage factor_id/revision_id/revision_number) — never full factor-value matrices (asserted by `test_admitted_summary_never_persists_full_factor_value_matrix`); wired into `admission.run_admission` on admission (WR-07). `catalog.list_admitted_factor_summaries` lists newest-first. Tests: `test_experiment_catalog.py::test_admitted_factor_summary_stores_coverage_finite_counts_and_lineage` and matrix-absence test. |
| 6 | Evaluation, multi-factor models, walk-forward, expected returns, live as-of suggestions all consume the same signal chain — no second factor-value implementation (FACT-06 / SC-5) | ✓ VERIFIED | `signal_chain.py:FactorSignalChain.compute` is the single compile→panel→values/rank/zscore path. `evaluation.py` delegates fully (legacy `_evaluate_panel` deleted; `parse_factor`/`compile_factor` imported only by `factor_dsl.py`, `signal_chain.py`, and validation-only consumers `factor_registry.py`/`hypotheses.py`/`api/research.py`/`main.py` — grep-verified; no `.compile()` outside the chain). `models.py` composite z-scores per-revision via `chain.compute`; PanelCache dedups the shared governed read (test: `test_panel_cache_dedup_results_in_single_governed_load`). Cross-consumer equality locked by `test_cross_consumer_equality_with_frozen_expected_frame`. Tests: `test_signal_chain.py` (8: binding, per-date membership, frozen equality, cache dedup, live as-of horizon=None, real-resolver per-date exclusion, fingerprint change). |
| 7 | Every evaluation/admission/model manifest records the resolved universe with a membership fingerprint (PIT contract) | ✓ VERIFIED | `universe.py` — `resolve_universe` (as-of symbol set + fingerprint), `resolve_universe_daily` (per-date [symbol,date] frame from append-only events; delist = new row, never UPDATE), `seed_membership` (idempotent, listing_date/first-bar fallback, only UNIQUE collisions swallowed), `close_membership`; `UniverseResolver` adapter injected into `FactorEvaluationService` in `main.py` (WR-03) plus best-effort startup `seed_membership`. `signal_chain._resolved_universe` carries `{method, membership_fingerprint, per_date_symbol_counts, excluded_delisted, pre_filter_counts}`; `evaluation._manifest` records the `universe_resolution` block in every manifest (resolver path `factor_universe_membership/v1`; `config-symbols` fallback documented). Tests: `test_universe_resolution.py` (8: listed-after-start, delist closure, fingerprint change, daily frame, seed/close rules); `test_evaluation_manifest_records_universe_resolution_fingerprint`; `test_coverage_reflects_resolved_universe_exclusion_pre_filter`. |

**Score:** 7/7 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/app/research/signal_chain.py` | single revision→panel→values/rank/zscore compute path | ✓ VERIFIED | `FactorSignalChain.compute`, `FactorSignalFrame`, `SignalChainConfig`; membership filter after single governed load; pre-filter counts; fingerprint |
| `backend/app/research/admission.py` | 5(6)-stage gate pipeline + append-only verdicts incl. rejections | ✓ VERIFIED | `run_admission`, policy constants w/ provenance, `_ic_correlation_duplicate` date-intersected (CR-02), coverage gate (WR-02) |
| `backend/app/research/models.py` | deterministic equal/IC-weighted composite + immutable snapshot output | ✓ VERIFIED | `build_composite`, `CompositeModel`, catalog evidence mean-IC (WR-01), symbols fail-closed (WR-04), artifact pointer fixed (WR-05) |
| `backend/app/research/universe.py` | PIT membership resolver + fingerprint | ✓ VERIFIED | `resolve_universe(_daily)`, `seed_membership`, `close_membership`, `UniverseResolver` |
| `backend/app/operational/migrations.py` | 4 new append-only tables | ✓ VERIFIED | `factor_universe_membership`, `factor_admission_verdicts`, `factor_model_models`, `factor_model_composites` w/ CHECK/UNIQUE/FK + UPDATE/DELETE ABORT triggers |
| `backend/app/research/evaluation.py` | ICIR / monthly robustness / coverage + monthly series, delegating to chain | ✓ VERIFIED | `_monthly_evidence`, `_coverage` (pre-filter), `_manifest` universe_resolution; no second compute path |
| `backend/app/research/catalog.py` | admitted-factor summary + revision lineage + new evidence keys + composite record | ✓ VERIFIED | `record_admitted_factor_summary`, `record_composite_model`, `get_composite_model` |
| `backend/app/research/repository.py` | append-only insert/query methods | ✓ VERIFIED | verdict UNIQUE guard, membership as-of tie-break (IN-04), model/composite rows |
| `backend/pyproject.toml` | scipy>=1.17.1,<1.18 base dependency | ✓ VERIFIED | line 22; scikit-learn==1.8.0 stays shadow extra |

### Key Link Verification

| From | To | Via | Status |
| ---- | --- | --- | ------ |
| research/evaluation.py | research/signal_chain.py | `FactorSignalChain` constructed in `FactorEvaluationService.__init__`; `evaluate()` delegates compute to `self._chain.compute`; legacy `_evaluate_panel` deleted | ✓ WIRED |
| research/models.py | research/signal_chain.py | `build_composite` per-revision `chain.compute`; PanelCache dedup shared governed read | ✓ WIRED |
| research/admission.py | research/catalog.py | `_record_evaluation_reference` → `catalog.record_factor_evaluation`; `candidate_trail_json` carries `evaluation_run_ids` + `experiment_snapshot_ids`; `_record_admitted_summary` → `record_admitted_factor_summary` | ✓ WIRED |
| research/universe.py | research/signal_chain.py | `_resolve_membership` calls `universe_resolver.resolve_universe_daily`; per-date inner join after single `load_panel` | ✓ WIRED |
| research/models.py | research/artifacts.py | `_write_composite_artifact` → `write_bundle` (O_EXCL + fsync + sha256); `input_snapshot_sha256` bound; `composite_output` points at `signals.json` (WR-05) | ✓ WIRED |
| main.py | research/universe.py + evaluation.py | `UniverseResolver(research_repository)` injected into `FactorEvaluationService`; startup `seed_membership` (WR-03) | ✓ WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| evaluation coverage | `pre_filter_counts` | chain `_compute` over resolved universe pre-filter | Real per-date finite counts over loaded panel (IN-01 excludes null-forward-return rows) | ✓ FLOWING |
| evaluation monthly series | `monthly_ic_series` | `_monthly_evidence` from per-date IC/RankIC series | Real per-month means persisted to `monthly_series.json` checksummed artifact | ✓ FLOWING |
| composite weights (ic_weighted) | `mean_ics` | `_collect_mean_ics` from catalog `ExperimentSnapshot.metrics.ic_summary.mean` (completed only, same resolved config) | Real catalogued evaluation evidence; fail-closed on missing | ✓ FLOWING |
| composite output | `composite` frame | per-revision chain z-scores | Real values; deterministic (identical input → identical sha256 + frame) | ✓ FLOWING |
| manifest universe_resolution | `membership_fingerprint` | `resolve_universe_daily` over append-only events | Real 64-hex fingerprint; production wired via main.py | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Per-requirement test files (FACT-01..06 + PIT + migrations) | `pytest tests/research/{test_admission,test_factor_evaluation,test_models,test_factor_dsl,test_experiment_catalog,test_signal_chain,test_factor_pipeline,test_universe_resolution}.py tests/test_operational_migrations.py -q` | **100 passed in 8.91s** | ✓ PASS |
| Ruff on phase files | `ruff check app/research tests/research` | `All checks passed!` (WR-06 clean) | ✓ PASS |
| No second factor-value implementation | `grep -rl "parse_factor\|compile_factor" app` | only `hypotheses.py, factor_registry.py, signal_chain.py, factor_dsl.py, api/research.py, main.py` — all validation/registration entry points; no `.compile()` outside chain | ✓ PASS |
| No execution authority in Phase 10 modules | grep for order/execute/broker paths in the 8 research modules + migrations | only SQLite `connection.execute` and the "execution costs" config validation — no order/execute/broker/live-trade path | ✓ PASS |
| Review-fix commits exist | `git cat-file -e` for all 17 fix commits (bd78e46..26fe989) | all present | ✓ PASS |
| CR-01/CR-02/WR-01/WR-02 fixes live in code | source inspection of `models.build_composite`, `admission._ic_correlation_duplicate`, `models._collect_mean_ics`, `admission.run_admission` | equal-weight uses sum (not mean_horizontal); IC-corr intersects dates; status filter live; `MIN_COVERAGE` coverage gate present in `run_admission` | ✓ PASS |
| DB constraint + append-only guards | `tests/test_operational_migrations.py::test_phase10_append_only_tables_migrate_with_constraints_and_idempotence` (in the 100) | CHECK/UNIQUE/FK + UPDATE/DELETE ABORT asserted | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| FACT-01 | 10-01, 10-05 | Admission gates + immutable append-only verdicts incl. rejections with candidate trail | ✓ SATISFIED | `admission.py:run_admission`; `test_admission.py` (8) + `test_factor_pipeline.py::test_rejection_path_records_identical_verdict` |
| FACT-02 | 10-01, 10-04, 10-05 | Evaluation exposes ICIR, monthly robustness, coverage + full monthly evidence | ✓ SATISFIED | `evaluation.py:_monthly_evidence/_coverage`; `test_factor_evaluation.py` (evidence vs NumPy reference, monthly artifact) |
| FACT-03 | 10-01, 10-06 | Deterministic equal/IC-weighted z-score composite, no ML, snapshot-consumed | ✓ SATISFIED | `models.py:build_composite`; `test_models.py` (numeric reference, determinism, immutability, fail-closed) |
| FACT-04 | 10-03 | DSL partition-context contract; denied labels; shifted-label leakage gate | ✓ SATISFIED | `factor_dsl.py:_FUNCTION_PARTITION/_validate_field_name/shifted_label_ic`; `test_factor_dsl.py` (32) |
| FACT-05 | 10-01, 10-05, 10-06 | Immutable admitted-factor catalog: summary storage + revision lineage | ✓ SATISFIED | `catalog.py:record_admitted_factor_summary` wired into admission; `test_experiment_catalog.py` (summary, lineage, no-matrix) |
| FACT-06 | 10-01, 10-04 | Single shared signal chain consumed by evaluation/models/as-of | ✓ SATISFIED | `signal_chain.py`; `test_signal_chain.py` (8); grep gate; `main.py` wiring |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No `TBD`/`FIXME`/`XXX`/`PLACEHOLDER`/unreferenced debt markers in any phase file | ℹ️ none | clean |

### Human Verification Required

None. All six FACT requirements plus the PIT contract have automated coverage that was re-run during this verification (100 passed in 8.91s), and every code path cited above was read directly. Full-suite green (1030 passed, 3 skipped) was already established by the executor after review fixes; no additional manual checks are needed for the Phase 10 goal.

### Gaps Summary

No gaps. All 7 must-have truths verified against the codebase:

1. Admission gates with append-only verdicts including rejections and candidate trail (FACT-01).
2. Evaluation with IC/RankIC/ICIR/monthly-robustness/coverage + monthly series (FACT-02).
3. Deterministic equal/IC-weighted composite with immutable snapshot output (FACT-03).
4. DSL partition-context contract, denied label fields, shifted-label leakage gate (FACT-04).
5. Admitted-factor catalog with summary storage + revision lineage (FACT-05).
6. Single shared signal chain with no second factor-value implementation (FACT-06).
7. PIT universe resolution with membership fingerprint in every manifest.

### Informational Observations (non-blocking)

- **Constant-cross-section z-scores:** during live smoke testing, a factor that is constant across symbols on a given date produces `NaN` z-scores (`0/0` std); those NaN values propagate into `build_composite`'s output frame and make `EvaluationArtifactService.write_bundle` (which uses `allow_nan=False`) raise an opaque `ValueError: Out of range float values are not JSON compliant` instead of a clear diagnostic. The phase's own tests use non-degenerate fixtures so this path is not exercised; the composite mechanism is deterministic, immutable (nothing partial is written), and works correctly on valid finite inputs, so this does not fail any must-have truth. A follow-up hardening could drop non-finite z-scores or reject with an explicit message.

**Cross-module integrity confirmed:** evaluation delegates to the chain (legacy `_evaluate_panel` deleted); composite IC-weighted weights read catalog-recorded mean IC (never ICIR — CONTEXT decision); manifests carry `universe_resolution.method` + `membership_fingerprint` + per-date counts; admission verdicts are append-only at both the repository and SQL-trigger layers with candidate trails for rejections. **Boundary confirmed:** no execution authority anywhere in Phase 10 code (no order/execute/broker/live-trade path; only `connection.execute` on SQLite and non-negative execution-cost validation). All 19 code-review findings (2 BLOCKER, 8 WARNING, 9 INFO) verified fixed in source with their commits present.

---

_Verified: 2026-08-01_
_Verifier: Claude (gsd-verifier)_
