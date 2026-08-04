---
phase: 10-factor-library-multi-factor-model
plan: phase-plan
type: execute
requirements: [FACT-01, FACT-02, FACT-03, FACT-04, FACT-05, FACT-06]
wave_summary:
  wave_0: [10-02, 10-03]
  wave_1: [10-01]
  wave_2: [10-04]
  wave_3: [10-05]
  wave_4: [10-06]
must_haves:
  truths:
    - "Researcher can run the admission gates (train/val IC, no-lookahead, no-label-leakage, similarity dedup) on a candidate factor and inspect every verdict — including rejections — as an immutable append-only record with the candidate trail (FACT-01)."
    - "Researcher can open a factor evaluation report that shows IC, RankIC, ICIR, monthly robustness, and coverage, with the full monthly evidence set exposed rather than a scalar mean (FACT-02)."
    - "Researcher can compose admitted factors into a deterministic multi-factor expected-return model (equal-weight or IC-weighted cross-sectional z-score, no ML) and hand it to portfolio optimization by immutable snapshot (FACT-03)."
    - "Researcher cannot compile a DSL change whose operators lack explicit partition semantics (per-date / per-symbol / pointwise) or that references a denied label field — the compiler rejects it and the shifted-label leakage gate blocks the change (FACT-04)."
    - "Researcher can open the admitted factor catalog and see summary storage (coverage, finite counts, signature) with revision lineage (FACT-05)."
    - "Evaluation, multi-factor models, walk-forward, expected returns, and live as-of rebalance suggestions all consume the same signal chain — a second factor-value implementation is a bug (FACT-06)."
    - "Every evaluation/admission/model manifest records the resolved universe with a membership fingerprint, closing the survivorship-bias gap going forward (PIT contract)."
  artifacts:
    - path: backend/app/research/signal_chain.py
      provides: "single revision→panel→values/rank/zscore compute path consumed by evaluation, models, walk-forward, expected returns, live as-of"
    - path: backend/app/research/admission.py
      provides: "5-stage gate pipeline with append-only verdicts incl. rejections (factor_admission_verdicts)"
    - path: backend/app/research/models.py
      provides: "deterministic equal/IC-weighted composite + immutable snapshot output"
    - path: backend/app/research/universe.py
      provides: "PIT membership resolver (resolve_universe / resolve_universe_daily) + membership_fingerprint"
    - path: backend/app/operational/migrations.py
      provides: "4 new append-only tables: factor_universe_membership, factor_admission_verdicts, factor_model_models, factor_model_composites"
    - path: backend/app/research/evaluation.py
      provides: "ICIR / monthly robustness / coverage + monthly series, delegating compute to the chain"
    - path: backend/app/research/catalog.py
      provides: "admitted-factor summary storage (coverage, finite counts, signature) + revision lineage + new evidence keys"
    - path: backend/app/research/repository.py
      provides: "append-only insert/query methods for membership, verdicts, models, composites"
    - path: backend/pyproject.toml
      provides: "scipy>=1.17.1,<1.18 base dependency (Phase 11 HRP readiness)"
  key_links:
    - from: research/evaluation.py
      to: research/signal_chain.py
      via: "FactorEvaluationService delegates _evaluate_panel + _correlation_series to FactorSignalChain.compute — no second implementation"
      pattern: "FactorSignalChain"
    - from: research/models.py
      to: research/signal_chain.py
      via: "composite z-scores computed per revision through chain.compute; PanelCache dedups the shared governed read"
      pattern: "FactorSignalChain"
    - from: research/admission.py
      to: research/catalog.py
      via: "candidate_trail_json links evaluation_run_id + ExperimentSnapshot.id from ExperimentCatalog.record_factor_evaluation"
      pattern: "candidate_trail_json"
    - from: research/universe.py
      to: research/signal_chain.py
      via: "per-date membership filter applied after the single BacktestEngine.load_panel call"
      pattern: "resolve_universe_daily"
    - from: research/models.py
      to: backend/app/research/artifacts.py
      via: "composite output persisted immutably (O_EXCL + fsync + sha256) and consumed by Phase 11 by snapshot"
      pattern: "input_snapshot_sha256"
---

# Phase 10: Factor Library & Multi-Factor Model — Executable Plan

## Phase Goal

Researchers can admit factors through deterministic gates, evaluate them on full monthly evidence, compose them into a deterministic multi-factor expected-return model, and reuse one shared signal chain everywhere — with every verdict and catalog entry immutable.

## Scope

**In scope (FACT-01..06 + PIT contract):** factor admission gates with append-only verdicts; evaluation upgrade to the full monthly evidence set (IC, RankIC, ICIR, monthly robustness, coverage); deterministic multi-factor composite (equal / IC-weighted cross-sectional z-score, no ML); admitted-factor catalog with summary storage and revision lineage; DSL partition-context contract with a shifted-label leakage gate; the shared factor signal chain; the minimal point-in-time universe contract.

**Out of scope:** portfolio optimization (Phase 11), risk models (Phase 12), walk-forward (Phase 13), RebalancePlan (Phase 14), frontend panels (Phase 15). No execution authority anywhere. Deferred ideas from `10-CONTEXT.md` (richer PIT tooling, interactive LLM mining loop FACT-07, parameter optimization / ensembling, Black-Litterman / max-Sharpe / short selling, ML expected returns) MUST NOT appear in any task.

## Source Coverage Audit

| Source | ID | Required behavior or constraint | Plans | Status |
|---|---|---|---|---|
| GOAL | Phase 10 | Deterministic admission, full monthly evidence, deterministic composite, one shared signal chain, immutable verdicts/catalog | 10-01, 10-05, 10-06 | COVERED |
| REQ | FACT-01 | Admission gates (train/val IC, no-lookahead, no-label-leakage, similarity dedup) with immutable append-only verdicts incl. candidate trail and rejections | 10-01, 10-05 | COVERED |
| REQ | FACT-02 | Evaluation reports ICIR, monthly robustness, coverage alongside IC/RankIC with full monthly evidence set | 10-01, 10-04, 10-05 | COVERED |
| REQ | FACT-03 | Deterministic multi-factor composite (equal/IC-weighted z-score, no ML), consumed by portfolio optimization by snapshot | 10-01, 10-06 | COVERED |
| REQ | FACT-04 | DSL partition-context contract; label fields denied; deterministic shifted-label leakage gate | 10-03, 10-01 | COVERED |
| REQ | FACT-05 | Admitted factors in immutable catalog with summary storage (coverage, finite counts, signature) and revision lineage | 10-01, 10-05, 10-06 | COVERED |
| REQ | FACT-06 | Single shared signal chain used identically by evaluation, models, walk-forward, expected returns, live as-of | 10-01, 10-04 | COVERED |
| RESEARCH | PIT universe | Append-only membership in operational.db, per-date resolution before coverage, manifest fingerprint | 10-02, 10-04 | COVERED |
| RESEARCH | Dependencies | scipy>=1.17.1,<1.18 base promotion; sklearn==1.8.0 stays shadow lazy-import; empty-.venv Wave 0 gate | 10-02 | COVERED |
| RESEARCH | Migrations | 4 new append-only tables appended to MIGRATIONS tuple | 10-02 | COVERED |
| CONTEXT | D-* | All locked decisions implemented; deferred ideas excluded | 10-01..10-06 | COVERED |

**Exclusions (not gaps):** deferred ideas in `10-CONTEXT.md`; Phase 11-15 scope; storing full factor value matrices (anti-feature); external datastore (no second datastore constraint).

## Plan List

- [ ] 10-01: **Tracer** — end-to-end factor pipeline on a fixture panel: signal chain → admission → evaluation (ICIR/robustness/coverage) → composite → catalog (FACT-01..06)
- [ ] 10-02: **Wave 0 foundations** — 4-table migration, scipy base promotion + empty-.venv gate, base test scaffolding
- [ ] 10-03: **DSL partition-context contract** — `_FUNCTION_PARTITION`, denied fields, `DSL_VERSION` bump to `factor-dsl-v2`, shifted-label leakage gate (FACT-04)
- [ ] 10-04: **PIT universe resolver** — `research/universe.py`, per-date membership filter, manifest `universe_resolution` block
- [ ] 10-05: **Admission + evaluation breadth** — real candidate trails, IC-correlation dedup, monthly-series artifacts, coverage on the resolved universe (FACT-01/02)
- [ ] 10-06: **Composite + catalog breadth** — IC-weighted from catalog evidence, immutable snapshot output, admitted-factor summaries + revision lineage (FACT-03/05)

## Wave Structure

| Wave | Plans | Purpose |
|------|-------|---------|
| 0 | 10-02, 10-03 | Foundations and compiler contract — prerequisites for the tracer. Run in parallel (no file overlap). |
| 1 | 10-01 | The tracer: prove the whole pipeline end-to-end on a fixture before any breadth. |
| 2 | 10-04 | PIT universe resolver — closes the survivorship-bias gap and feeds evaluation coverage. |
| 3 | 10-05 | Admission + evaluation breadth — production candidate trails, monthly-series artifacts, resolved-universe coverage. |
| 4 | 10-06 | Composite + catalog breadth — snapshot-immutable composite outputs, admitted-factor catalog summaries. |

## Artifacts this phase produces

| Artifact | Kind | Provides |
|---|---|---|
| `FactorSignalChain` / `FactorSignalFrame` / `SignalChainConfig` (signal_chain.py) | class + frozen dataclass | single revision→panel→values/rank/zscore compute path (FACT-06); per-revision output frame with panel/resolved-universe fingerprints; chain configuration surface |
| Admission policy constants `ADMISSION_POLICY_VERSION`, `TRAIN_MIN_MEAN_IC`, `VAL_MIN_MEAN_IC`, `MIN_TRAIN_OBSERVATIONS`, `MAX_SIMILARITY_SCORE`, `MAX_IC_CORRELATION`, `SHIFTED_LABEL_MAX_ABS_IC`, `MIN_COVERAGE` (admission.py) | constants | fixed, documented admission policy with provenance (FACT-01) |
| 5-stage gate pipeline (admission.py) | module functions | no_lookahead → no_label_leakage → temporal-split → similarity/IC-corr dedup → coverage gates producing append-only verdicts incl. rejections |
| `CompositeModel` + `CompositeWeighting` (models.py) | frozen dataclass + `Literal` | deterministic equal/IC-weighted composite definition with immutable snapshot output (FACT-03) |
| `resolve_universe` / `resolve_universe_daily` (universe.py) | functions | PIT membership resolution returning per-date symbol sets + `membership_fingerprint` (PIT contract) |
| `factor_universe_membership` / `factor_admission_verdicts` / `factor_model_models` / `factor_model_composites` (migrations.py) | SQLite tables | 4 new append-only tables in operational.db with CHECK/UNIQUE/FK guards |
| `_FUNCTION_PARTITION` / `DENIED_FIELDS` (factor_dsl.py) | constants | DSL partition-context contract + denied label/identity fields (FACT-04) |
| `icir` / `monthly_robustness` / `coverage` / `monthly_ic_series` (evaluation.py + catalog.py) | evidence keys | full monthly evidence set recorded in evaluation results, artifacts, and catalog metrics (FACT-02) |

## Requirement → Plan Mapping

| Requirement | Behavior | Plans | Verification command |
|---|---|---|---|
| FACT-01 | Admission gates + immutable verdicts | 10-01, 10-05 | `pytest tests/research/test_admission.py -q --tb=short` |
| FACT-02 | ICIR / monthly robustness / coverage | 10-01, 10-04, 10-05 | `pytest tests/research/test_factor_evaluation.py -q --tb=short` |
| FACT-03 | Deterministic composite | 10-01, 10-06 | `pytest tests/research/test_models.py -q --tb=short` |
| FACT-04 | DSL partition contract + leakage gate | 10-03 | `pytest tests/research/test_factor_dsl.py -q --tb=short` |
| FACT-05 | Catalog summary + revision lineage | 10-01, 10-05, 10-06 | `pytest tests/research/test_experiment_catalog.py -q --tb=short` |
| FACT-06 | Shared signal chain | 10-01, 10-04 | `pytest tests/research/test_signal_chain.py -q --tb=short` |

All commands run from `backend/` with the project interpreter: `cd backend && .venv/bin/python -m pytest …`.

---

# Plan 10-01 — Tracer: End-to-End Factor Pipeline (FACT-01..06)

**wave:** 1 · **depends_on:** [10-02, 10-03] · **autonomous:** true
**requirements:** [FACT-01, FACT-02, FACT-03, FACT-04, FACT-05, FACT-06]
**files_modified:**
- backend/app/research/signal_chain.py (new)
- backend/app/research/admission.py (new)
- backend/app/research/models.py (new)
- backend/app/research/evaluation.py (refactor — delegate to chain, add evidence metrics)
- backend/app/research/catalog.py (extend — new evidence keys)
- backend/app/research/repository.py (extend — verdict/model insert methods)
- backend/tests/research/test_signal_chain.py (new — scaffolded RED in 10-02, turned green here)
- backend/tests/research/test_admission.py (new — scaffolded RED in 10-02, turned green here)
- backend/tests/research/test_models.py (new — scaffolded RED in 10-02, turned green here)
- backend/tests/research/test_factor_evaluation.py (extend)
- backend/tests/research/test_experiment_catalog.py (extend)
- backend/tests/research/test_factor_pipeline.py (new — end-to-end tracer test)

## Objective

Prove the complete Phase 10 spine on a fixture panel, end to end, before any breadth work: create a factor revision → compute cross-sectional values/rank/zscore through the shared signal chain → run the 5 admission gates and persist a verdict (including a rejection path) → evaluate with IC/RankIC/ICIR/monthly-robustness/coverage → compose admitted factors into equal-weight and IC-weighted composites → record evidence in the catalog. Every artifact on this path is immutable and checksum-bound.

Purpose: This is the architecture's keel. It forces the one-compile/one-panel/one-value-path contract (FACT-06) into existence on the first commit, proves the append-only verdict + model + composite records work together, and catches a dead-end (e.g., chain/evaluation skew, verdict write failure) before ten layers are committed. Functionality is fixture-scoped (fixture universe resolver, fixture panels, no lake reads); no architectural gap is left.
Output: `signal_chain.py`, `admission.py`, `models.py`, evaluation/catalog/repository extensions, and the green test files that lock the contracts.

## Context

- @.planning/PROJECT.md
- @.planning/ROADMAP.md
- @.planning/STATE.md
- @.planning/phases/10-factor-library-multi-factor-model/10-RESEARCH.md — ground truth for the chain surface, gate stages, evidence formulas, composite design, schema
- @.planning/phases/10-factor-library-multi-factor-model/10-CONTEXT.md — locked decisions D-01..D-06 + PIT contract
- backend/app/research/evaluation.py — `_validated_revision` (L231-245), `_evaluate_panel` (L247-260), `_correlation_series` (L268-284), `_manifest` (L341-378), `FactorEvaluationResult` (L80-110) — the refactor target
- backend/app/research/factor_registry.py — `FactorRevision.provenance` (L15-36), `discover_similar` (L245-275)
- backend/app/research/catalog.py — `FactorEvidencePackage` (L105-116), `record_factor_evaluation` (L230-258)
- backend/app/research/repository.py — `_insert_revision` / `create_experiment` append-only conventions, `_json` canonical serialization (L13-30)
- backend/app/backtest/engine.py — `load_panel` (L191-200), `PanelCache.get_or_compute/_make_key` (L110-176)
- backend/app/research/artifacts.py — `write_bundle` (L42-65), O_EXCL + fsync + sha256 (L76-118)
- backend/app/research/factor_dsl.py — `_FUNCTION_PARTITION` + `DENIED_FIELDS` + `partition_context` (landed by 10-03; this plan consumes them)

## Tasks

- **build: Create `research/signal_chain.py` — the single factor-value implementation**
  - Files: backend/app/research/signal_chain.py
  - Read first: backend/app/research/evaluation.py (L115-199, L231-284), backend/app/backtest/engine.py (L110-200)
  - Action: Implement `SignalChainConfig` (frozen slots dataclass with fields: `universe: str`, `symbols: tuple[str, ...]`, `asset_type: str`, `start/end: date`, `warmup_days: int`, `forward_return_horizon: int | None`, `rebalance: RebalanceCadence = "daily"`, `missing_data_treatment: MissingDataTreatment = "drop"`, `warmup_treatment: WarmupTreatment = "exclude"` — reuse the literals from evaluation.py), `FactorSignalFrame` (frozen slots: `revision_id`, `dsl_version`, `panel_fingerprint`, `resolved_universe: Mapping[str, Any]`, `frame: pl.DataFrame` with columns `symbol, date, _factor, _forward_return, _rank, _zscore`), and `FactorSignalChain` constructed with `(engine: BacktestEngine, registry: FactorRegistry, universe_resolver: object)`. `compute(*, revision_id, config)` must: (1) validate config mirroring `FactorEvaluationService._validate_config`; (2) bind the revision exactly once via the `_validated_revision` logic (registry.get_revision → parse_factor → DSL-version + fields cross-check) — never re-derive the expression; (3) resolve the universe through the injected resolver (fixture resolver for this plan — `resolve_universe_daily` returns a `pl.DataFrame[symbol, date]`; the real resolver lands in 10-04, the injection seam is the contract); (4) call `engine.load_panel(symbols, start-warmup, end, columns=required, asset_type)` — the sole governed-data seam; (5) compute `_factor` via `parsed.compile()`, `_forward_return` via `close.shift(-horizon).over("symbol") / close - 1` when `forward_return_horizon` is not None (skip the label column when None — the live as-of path); (6) compute `_rank` and `_zscore` cross-sectionally per date using the DSL `rank()`/`zscore()` partition semantics; (7) apply the per-date membership inner join (fixture no-op acceptable), the finite/close filters, and the rebalance cadence filter (reuse evaluation `_rebalance` semantics); (8) bind `panel_fingerprint` (sha256 over schema + observed range + row count) and `resolved_universe`. The frame carries BOTH the finite-filtered rows and the pre-filter per-date finite counts so coverage can be computed on the resolved universe (pitfall 5). Module docstring: knows/doesn't-know per CONVENTIONS (knows revision→panel binding and partition semantics; doesn't know HTTP/API/frontend/persistence).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_signal_chain.py -q --tb=short`
  - Done: `FactorSignalChain.compute` returns a `FactorSignalFrame` with the compiled values/rank/zscore, forward return, fingerprint, and resolved-universe block for a fixture revision and panel; the chain is the only place that imports `parse_factor`/`compile_factor` outside the DSL itself.

- **test: Turn `tests/research/test_signal_chain.py` green**
  - Files: backend/tests/research/test_signal_chain.py
  - Read first: backend/tests/research/test_signal_chain.py (the 10-02 RED scaffold), backend/app/research/signal_chain.py (module under test)
  - Action: The scaffold from 10-02 defines these cases; make them pass: (1) revision→panel binding — a stored revision with a mismatched `dsl_version` or `fields` set raises before any governed load; (2) per-date membership filter — symbols with a post-start listing date are excluded on dates before their listing but present after (fixture membership frame); (3) cross-consumer equality — `chain.compute` output for a config equals the legacy `FactorEvaluationService._evaluate_panel` result for the same panel/config on the same dates (guards pitfall 3 — a second implementation drifting from evaluation); (4) PanelCache dedup — two `chain.compute` calls with identical config result in exactly one `load_panel` call on the stub engine; (5) `forward_return_horizon=None` skips the label column (live as-of shape). Use the `StubBacktestEngine` fixture from `tests/research/conftest.py`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_signal_chain.py -q --tb=short`
  - Done: The chain's binding, per-date membership, cross-consumer equality, and cache-dedup contracts are locked by passing tests.

- **refactor: Make `evaluation.py` delegate to the chain and expose ICIR / monthly robustness / coverage**
  - Files: backend/app/research/evaluation.py
  - Read first: backend/app/research/evaluation.py (L115-199, L229-306, L341-378)
  - Action: Rebuild `FactorEvaluationService.evaluate` so panel evaluation delegates to `FactorSignalChain.compute` (the service keeps config validation + artifact orchestration). Extend `FactorEvaluationResult` with `icir: float | None`, `monthly_robustness: float | None`, `coverage: Mapping[str, Any]` (mean + `coverage_series`), and `monthly_ic_series: tuple[Mapping, ...]`. Compute `icir = mean(monthly_ic)/std(monthly_ic)` (None when std ~ 0), `monthly_robustness = positive-month share`, and `coverage = mean per-date finite share over the resolved universe` computed from the chain's PRE-FILTER counts (never the post-filter frame — pitfall 5). Wire the new fields into `as_dict()` and the `FactorEvidencePackage`-bound `metrics` map so cataloging (10-01 task 6) sees them. Add the `universe_resolution` block to `_manifest` using the chain's `resolved_universe` (method `"factor_universe_membership/v1"`; the fixture path records the fixture fingerprint; 10-04 fills production values). Do NOT delete `_evaluate_panel`/`_correlation_series` in this task if existing tests still reference them — keep a thin adapter that calls the chain so the existing evaluation tests keep passing until 10-05 removes the last direct consumer.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_evaluation.py -q --tb=short`
  - Done: Evaluation reports ICIR, monthly robustness, and coverage (with the monthly series) and its panel compute goes through the chain; existing evaluation tests still pass.

- **test: Extend `tests/research/test_factor_evaluation.py` — evidence correctness**
  - Files: backend/tests/research/test_factor_evaluation.py
  - Read first: backend/tests/research/test_factor_evaluation.py, backend/app/research/evaluation.py (module under test)
  - Action: Add assertions that on a fixture panel the ICIR, monthly robustness, and coverage match a NumPy reference implementation (compute monthly means of the per-date IC series, then mean/std and positive share); coverage is < 1.0 when the fixture panel contains non-finite factor rows on some dates (proving it is computed pre-filter); `monthly_ic_series` contains one entry per calendar month with the month label and monthly mean IC/RankIC.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_evaluation.py -q --tb=short`
  - Done: The new evidence metrics are locked against a reference on a fixture, and coverage provably measures the resolved pre-filter cross-section.

- **build: Create `research/admission.py` — 5-gate pipeline with append-only verdicts**
  - Files: backend/app/research/admission.py, backend/app/research/repository.py
  - Read first: backend/app/research/factor_registry.py (L245-275), 10-RESEARCH.md "Admission Gates" section
  - Action: Implement `ADMISSION_POLICY_VERSION = "admission-policy-v1"` and the fixed policy constants `TRAIN_MIN_MEAN_IC = 0.02`, `VAL_MIN_MEAN_IC = 0.01`, `MIN_TRAIN_OBSERVATIONS = 40`, `MAX_SIMILARITY_SCORE = 0.80`, `MAX_IC_CORRELATION = 0.90`, `SHIFTED_LABEL_MAX_ABS_IC = 0.02`, `MIN_COVERAGE = 0.50` (provenance recorded in the module docstring). Implement the 5 ordered, deterministic gate stages — (1) `no_lookahead`: compiled expr references only `ALLOWED_FIELDS` and every stateful function declares its partition context (consumes the 10-03 `_FUNCTION_PARTITION`/`partition_context`); (2) `no_label_leakage`: `abs(mean(IC_shifted)) <= SHIFTED_LABEL_MAX_ABS_IC` using a `shifted_label_ic(evaluated, *, horizon)` module function (label displaced one extra horizon); (3) `similarity_dedup`: top `discover_similar` score < `MAX_SIMILARITY_SCORE` AND max |IC-correlation| with the admitted set on the val window < `MAX_IC_CORRELATION`; (4) `train_ic`: `mean_IC_train >= TRAIN_MIN_MEAN_IC`; (5) `val_ic`: `mean_IC_val >= VAL_MIN_MEAN_IC`. The temporal train/val split is by date order only: `TRAIN_FRACTION = 0.7` of the evaluation window's trading dates, first 70% train / last 30% val, applied identically each run. Every run — admission AND rejection — writes a full verdict row to `factor_admission_verdicts` via new `ResearchRepository` methods (`insert_admission_verdict`, `get_admission_verdict`, following `_insert_revision`/`_json` append-only conventions): `gates_json` (one entry per gate: gate, passed, metric, observed, threshold, detail — rejections included), `candidate_trail_json` (revision provenance from `FactorRevision.provenance`, evaluation_run_id, gate results), `resolved_universe_json`, `input_snapshot_sha256`, `UNIQUE(revision_id, policy_version)` enforcement. `discover_similar` is untouched; the IC-correlation check lives in admission.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_admission.py -q --tb=short`
  - Done: A candidate factor passes or fails the 5 ordered gates deterministically and produces an append-only verdict row (rejection recorded identically to admission) with the full candidate trail.

- **build: Create `research/models.py` + extend catalog — deterministic composite + evidence keys**
  - Files: backend/app/research/models.py, backend/app/research/catalog.py, backend/app/research/repository.py
  - Read first: backend/app/research/factor_dsl.py (zscore compile semantics), 10-RESEARCH.md "Multi-Factor Composite" + "Evaluation Evidence" sections, backend/app/research/artifacts.py (write_bundle)
  - Action: In `models.py`, define `CompositeWeighting = Literal["equal", "ic_weighted"]` and a frozen `CompositeModel` dataclass (`model_id`, `name`, `revision_ids: tuple[str, ...]` sorted for determinism, `weighting`, `weights: Mapping[str, float]`, `input_snapshot_sha256`, `created_at`). Compute per revision via `chain.compute`; the composite per (date, symbol) is the cross-sectional z-score mean across revisions for equal-weight, and `sum_r w_r * z_{r,t,i}` with `w_r = mean_ic_r / sum mean_ic` for IC-weighted (mean IC from the recorded evaluation evidence, NOT ICIR — CONTEXT decision). Optional composite `.rank().over("date")`. Persist the definition to `factor_model_models` and one immutable output row to `factor_model_composites` (with `output_sha256` + artifact path) via new `ResearchRepository` methods; write the output artifact through `EvaluationArtifactService.write_bundle` (O_EXCL + fsync + sha256) bound by `input_snapshot_sha256`. In `catalog.py`, extend the `metrics` map built by `record_factor_evaluation` with `icir`, `monthly_robustness`, `coverage`, `monthly_ic_series` (additive — `_compatibility_warnings` untouched). Module docstrings per CONVENTIONS.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_models.py tests/research/test_experiment_catalog.py -q --tb=short`
  - Done: Equal-weight and IC-weighted composites compute deterministically over admitted revisions via the chain, persist immutably with `input_snapshot_sha256`, and the catalog records the new evidence keys.

- **test: End-to-end tracer proof — `tests/research/test_factor_pipeline.py`**
  - Files: backend/tests/research/test_factor_pipeline.py
  - Read first: backend/tests/research/test_factor_pipeline.py, backend/tests/research/conftest.py (StubBacktestEngine + fixture panel + fixture universe resolver), backend/app/research/repository.py
  - Action: Write one integration test that walks the full spine on a fixture: create a factor revision in `FactorRegistry` → run admission (assert the verdict row exists, is append-only, and carries gates_json + candidate_trail_json) → evaluate (assert ICIR/coverage/monthly series present) → compose both weightings (assert weights frozen + deterministic `input_snapshot_sha256`) → record through `ExperimentCatalog` (assert the evidence package carries the new metrics). Also drive ONE rejection path (a deliberately lookahead or low-IC factor) and assert its verdict row is recorded identically with verdict="rejected". Run against a `StubBacktestEngine` + fixture panel + fixture universe resolver from `conftest.py`; use a tmp_path SQLite repository (`ResearchRepository(tmp_path / "operational.db")` + `.migrate()`).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_pipeline.py -q --tb=short`
  - Done: The full admit → evaluate → compose → catalog path works on a fixture with an immutable verdict, model, and catalog record — the spine is proven before any breadth plan starts.

## Verification

```bash
cd backend && .venv/bin/python -m pytest \
  tests/research/test_factor_pipeline.py \
  tests/research/test_signal_chain.py \
  tests/research/test_factor_evaluation.py \
  tests/research/test_admission.py \
  tests/research/test_models.py \
  tests/research/test_experiment_catalog.py \
  -q --tb=short
```

All green. No second factor-value implementation exists outside the chain (grep: `parse_factor`/`compile_factor` imported only by `signal_chain.py` and the DSL itself — the legacy `_evaluate_panel` adapter is the one sanctioned exception until 10-05).

## Success Criteria

- The chain is the single compile→compute path; evaluation and models consume it.
- Admission produces append-only verdicts for admitted AND rejected factors with the candidate trail.
- Evaluation exposes ICIR, monthly robustness, coverage, and the monthly series.
- Composites are deterministic, immutable, snapshot-consumed, and catalogued with the new evidence keys.
- The tracer test proves the full path on a fixture.

---

# Plan 10-02 — Wave 0: Migrations, Dependencies, Test Scaffolding

**wave:** 0 · **depends_on:** [] · **autonomous:** false (two one-way-door checkpoint:decision gates)
**requirements:** [FACT-01, FACT-02, FACT-03, FACT-05, FACT-06]
**files_modified:**
- backend/app/operational/migrations.py
- backend/pyproject.toml
- backend/uv.lock
- backend/tests/test_operational_migrations.py
- backend/tests/research/test_signal_chain.py (new)
- backend/tests/research/test_admission.py (new)
- backend/tests/research/test_models.py (new)
- backend/tests/research/test_universe_resolution.py (new)
- backend/tests/research/conftest.py
- backend/app/research/repository.py

## Objective

Land the irreversible foundations every other plan builds on: the 4 new append-only tables in the existing operational.db, the scipy base-dependency promotion with the empty-`.venv` verification gate, and the base test scaffolding (new test files + fixtures) that 10-01 turns green. The two one-way-door decisions (new append-only tables; scipy promotion to base deps) are gated behind explicit `checkpoint:decision` tasks BEFORE any implementation — per the reversibility contract, they are `costly`/`one-way` (undoing requires a schema migration or a dependency revert that breaks the Phase 11 contract).

Purpose: Every later plan assumes these tables, this dependency floor, and these test files exist. Wave 0 is the only place the migration sequence advances and the only place the fresh-environment dependency truth is verified (RESEARCH.md Wave 0 gate — not an assumption).
Output: 4 migrated tables with UNIQUE/FK guards, scipy promoted and locked, empty-`.venv` gate passed, 4 new test files + conftest fixtures, repository append-only methods for the new tables.

## Context

- @.planning/phases/10-factor-library-multi-factor-model/10-RESEARCH.md — `## PIT Universe Contract` (schema), `## Admission Gates` (verdicts schema), `## Multi-Factor Composite` (models/composites schema), `## Dependency Changes` (scipy/sklearn + empty-.venv gate), `## Schema/Migration Sketch`, `## Verification Plan` (Wave 0 gaps)
- @.planning/phases/10-factor-library-multi-factor-model/10-CONTEXT.md — Claude's Discretion: exact schema column names and migration structure within `operational/migrations.py` conventions; scipy packaging shape at planner discretion
- backend/app/operational/migrations.py — `MIGRATIONS` tuple (L7+), append a new script at the end; `migrate_operational_db` (L1547-1564) applies atomically with `PRAGMA user_version`
- backend/app/research/repository.py — `_insert_revision` / `create_experiment` append-only conventions, `_json` canonical serialization (L13-30)
- backend/pyproject.toml — `[project] dependencies` (base) and the `shadow` extra (`scikit-learn==1.8.0`), `requires-python = ">=3.11"`
- backend/uv.lock — scipy 1.17.1 already transitive (via vectorbt / scikit-learn); promotion should keep the lock stable
- backend/tests/test_operational_migrations.py — migration atomicity test conventions (monkeypatch `MIGRATIONS`, assert schema objects + `user_version`)

## Tasks

- **checkpoint:decision — Approve the 4 new append-only tables (one-way door)**
  - Decision: Land the four new append-only tables in `operational/migrations.py` — `factor_universe_membership`, `factor_admission_verdicts`, `factor_model_models`, `factor_model_composites` — as a single new migration script appended to the `MIGRATIONS` tuple.
  - Context: This is a one-way door: the migration advances `PRAGMA user_version` for every operational.db (research + forecast + jobs share the same database). Undoing requires a follow-up migration, and downstream phases (11-15) are built on these table contracts. The schema is specified in RESEARCH.md; the columns, constraints, and index names are at planner discretion per CONTEXT.
  - Options:
    - option-a: Ship exactly the RESEARCH.md schema — `factor_universe_membership` (universe_name, symbol, asset_type CHECK stock|etf, effective_date, state CHECK listed|delisted, source, provenance_json, UNIQUE(universe_name, symbol, effective_date, state), index on (universe_name, symbol, effective_date)); `factor_admission_verdicts` (revision_id FK RESTRICT, policy_version, verdict CHECK admitted|rejected, reason, gates_json, candidate_trail_json, resolved_universe_json, input_snapshot_sha256 CHECK length=64, UNIQUE(revision_id, policy_version)); `factor_model_models` (model_id, name, weighting CHECK equal|ic_weighted, revision_ids_json, weights_json, input_snapshot_sha256, created_at); `factor_model_composites` (id, model_id FK, output_sha256, artifact_relative_path, input_snapshot_sha256, created_at). Pros: researched, verified against the host conventions, minimal review delta. Cons: none significant.
    - option-b: Adjust column names/types now (e.g., store membership as date-range rows). Pros: could reduce row count. Cons: diverges from the researched, qlib-distilled contract; more review; no measured benefit.
  - Resume signal: Select: option-a or option-b

- **build: Append the migration script for the 4 tables + extend migration tests**
  - Files: backend/app/operational/migrations.py, backend/tests/test_operational_migrations.py
  - Read first: backend/app/operational/migrations.py (the last entry of the `MIGRATIONS` tuple around L1419-1473 to match the script style), backend/tests/test_operational_migrations.py (atomicity conventions)
  - Action: Append ONE new SQL script to the `MIGRATIONS` tuple creating all four tables per the approved schema (option-a): `factor_universe_membership` with `state CHECK (state IN ('listed','delisted'))`, `asset_type CHECK (asset_type IN ('stock','etf'))`, `UNIQUE (universe_name, symbol, effective_date, state)` and `idx_universe_membership_resolve ON factor_universe_membership(universe_name, symbol, effective_date)`; `factor_admission_verdicts` with `revision_id TEXT NOT NULL REFERENCES research_factor_revisions(id) ON DELETE RESTRICT`, `verdict CHECK (verdict IN ('admitted','rejected'))`, `input_snapshot_sha256 TEXT NOT NULL CHECK (length(input_snapshot_sha256) = 64)`, `UNIQUE (revision_id, policy_version)` and `idx_admission_verdicts_revision`; `factor_model_models` with `weighting CHECK (weighting IN ('equal','ic_weighted'))`; `factor_model_composites` with `model_id TEXT NOT NULL REFERENCES factor_model_models(model_id) ON DELETE RESTRICT`. Extend `tests/test_operational_migrations.py` with a test that runs the full `MIGRATIONS` sequence on a fresh in-memory connection and asserts all four tables exist with their UNIQUE and FK constraints enforced (insert a duplicate membership row → IntegrityError; delete a revision referenced by a verdict → FK RESTRICT).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short`
  - Done: The 4 tables exist after migration with CHECK/UNIQUE/FK guards; the migration test proves constraints and forward-only idempotence.

- **checkpoint:decision — Approve scipy 1.17.1 promotion to base dependencies (one-way door)**
  - Decision: Promote scipy from a transitive lock dependency to a direct base dependency pinned `scipy>=1.17.1,<1.18` in `backend/pyproject.toml`.
  - Context: Phase 11 HRP needs `scipy.cluster.hierarchy.linkage`. CONTEXT mandates the promotion now. The `<1.18` upper bound is REQUIRED: scipy 1.18.0 requires Python ≥3.12 while the project floor is `>=3.11` (RESEARCH.md Assumptions Log A1). This changes the published dependency contract of the package — a one-way door for downstream consumers.
  - Options:
    - option-a: Promote to base `[project] dependencies` as `scipy>=1.17.1,<1.18`; keep scikit-learn `==1.8.0` in the `shadow` extra (lazy-import only, no promotion). Pros: matches CONTEXT and Phase 11 readiness; uv.lock already pins 1.17.1 transitively so resolution is stable. Cons: grows the base install surface slightly.
    - option-b: Keep scipy extra-only (`backtest` or a new `scipy` extra). Pros: smallest base install. Cons: violates the locked decision (promotion now); Phase 11 base installs would miss HRP.
  - Resume signal: Select: option-a or option-b

- **build: Promote scipy to base deps + run the empty-.venv Wave 0 gate**
  - Files: backend/pyproject.toml, backend/uv.lock
  - Read first: backend/pyproject.toml (`[project] dependencies`, `shadow` extra, `requires-python`)
  - Action: Add `"scipy>=1.17.1,<1.18"` to `[project] dependencies` per the approved option. Run `cd backend && uv lock` to regenerate `uv.lock` (expected stable — 1.17.1 is already the transitive pin). Then execute the RESEARCH.md Wave 0 gate: (1) `cd backend && uv venv --clear`; (2) `uv sync --extra shadow` — must resolve with scipy 1.17.1; (3) `uv pip check` — no conflicts; (4) `.venv/bin/python -c "import scipy; print(scipy.__version__)"` → `1.17.1`; (5) lazy-import audit — a subprocess that imports `app.research.signal_chain`, `app.research.admission`, `app.research.evaluation` (the modules 10-01 creates; until then audit the research package import surface) and asserts `"sklearn" not in sys.modules` (module-top imports only); (6) smoke — `ResearchRepository(path).migrate()` + `FactorRegistry.create_factor` + `FactorSignalChain.compute` over a fixture panel with no sklearn on the path (this smoke completes once 10-01 lands; in this plan run the migrate + create_factor portion). scikit-learn stays `==1.8.0` shadow, never module-top imported (Phase 12 consumes it at the risk-model boundary only).
  - Verify: `cd backend && uv sync --extra shadow && uv pip check && .venv/bin/python -c "import scipy,sys; sys.exit(0 if scipy.__version__=='1.17.1' else 1)"`
  - Done: `scipy>=1.17.1,<1.18` is in base deps and locked; the empty-`.venv` gate passes (scipy 1.17.1, no dependency conflicts, no sklearn import on the research module path).

- **test: Scaffold the 4 new test files + shared fixtures (Wave 0 gaps)**
  - Files: backend/tests/research/test_signal_chain.py, backend/tests/research/test_admission.py, backend/tests/research/test_models.py, backend/tests/research/test_universe_resolution.py, backend/tests/research/conftest.py
  - Read first: backend/tests/research/test_factor_evaluation.py (StubBacktestEngine pattern), backend/tests/research/test_factor_dsl.py
  - Action: Create the 4 new test files as RED scaffolds per the RESEARCH.md Wave 0 gaps: `test_signal_chain.py` (cases: revision→panel binding, per-date membership filter, cross-consumer equality, PanelCache dedup, `forward_return_horizon=None`), `test_admission.py` (cases: every gate result recorded; a rejection produces a full verdict row with candidate trail; temporal split deterministic; IC-correlation dedup catches a near-duplicate that Jaccard misses), `test_models.py` (cases: equal vs IC-weighted weights; two identical builds → identical `input_snapshot_sha256`; output artifact immutable), `test_universe_resolution.py` (cases: listed-after-start excluded per date; delist event closes membership as-of; fingerprint changes when membership changes). These files import the modules 10-01 creates; until then they must FAIL (RED). Move the shared `StubBacktestEngine` + fixture panel + fixture universe resolver helpers from `test_factor_evaluation.py` into `backend/tests/research/conftest.py` as importable fixtures (update `test_factor_evaluation.py` imports accordingly). Follow CONVENTIONS: pytest 8+, `--import-mode=importlib` (already in pyproject), module docstrings, `# noqa: BLE001` on broad catches.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_signal_chain.py tests/research/test_admission.py tests/research/test_models.py tests/research/test_universe_resolution.py -q --tb=short` — expected failures (RED) until 10-01/10-04 land
  - Done: The 4 new test files exist with the RESEARCH.md cases, shared fixtures are in conftest.py, and the scaffolds are provably RED (failing on the missing modules) — the exact tests 10-01 and 10-04 turn green.

- **build: Add repository append-only methods for the 4 new tables**
  - Files: backend/app/research/repository.py
  - Read first: backend/app/research/repository.py (`_insert_revision` L95-150, `create_experiment` L251-330, `_json` L13-30)
  - Action: Add `ResearchRepository` methods following the append-only conventions: `insert_universe_membership(universe_name, symbol, asset_type, effective_date, state, source, provenance_json)` (INSERT only; a delist is a new row, never an UPDATE), `resolve_universe_memberships(universe_name, as_of)` (latest event per symbol with `effective_date <= as_of`), `insert_admission_verdict(...)` + `get_admission_verdict(revision_id, policy_version)` (enforce `UNIQUE(revision_id, policy_version)`), `insert_model_definition(...)` + `get_model_definition(model_id)`, `insert_model_composite(...)` + `list_model_composites(model_id)`. Use `_json` canonical serialization for JSON columns; wrap inserts in `with self._connection() as connection, connection:` transactions. Do NOT add the resolver here — that is 10-04.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_universe_resolution.py tests/research/test_admission.py tests/research/test_models.py -q --tb=short` (RED scaffold portion that exercises the repository can be expected to fail until the modules land; the repository methods themselves are verified by the 10-01/10-05/10-06 tests)
  - Done: The repository exposes append-only insert/query methods for membership events, admission verdicts, model definitions, and composite outputs with canonical JSON serialization and transactionality.

## Verification

```bash
cd backend && uv sync --extra shadow && uv pip check && .venv/bin/python -c "import scipy,sys; sys.exit(0 if scipy.__version__=='1.17.1' else 1)"   # 1.17.1 (exit 1 on mismatch)
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short
```

The 4 new test files exist and are RED; the migration and dependency gates pass.

## Success Criteria

- The 4 append-only tables migrate atomically with CHECK/UNIQUE/FK guards.
- `scipy>=1.17.1,<1.18` is in base deps, locked, and verified in an empty `.venv`; sklearn stays shadow lazy-import (no module-top import).
- The 4 new test files are scaffolded RED with shared fixtures in conftest.py.
- Repository append-only methods exist for all 4 tables.

---

# Plan 10-03 — DSL Partition-Context Contract + Leakage Gate (FACT-04)

**wave:** 0 · **depends_on:** [] · **autonomous:** false (one-way-door checkpoint:decision before the DSL_VERSION bump)
**requirements:** [FACT-04]
**files_modified:**
- backend/app/research/factor_dsl.py
- backend/tests/research/test_factor_dsl.py
- backend/app/research/factor_registry.py

## Objective

Make every DSL operator declare its partition semantics (per-date / per-symbol / pointwise) inside the compiler beside `_FUNCTION_ARITY`, deny label/identity fields explicitly, and gate any DSL change with a deterministic shifted-label leakage test. The `DSL_VERSION` bump from `factor-dsl-v1` to `factor-dsl-v2` is a one-way door — stored revisions keep their `dsl_version` and `_validated_revision` rejects cross-version reuse — so it is gated behind a `checkpoint:decision` BEFORE the bump task.

Purpose: This is the compiler-side no-lookahead contract. It is a prerequisite for the tracer (10-01's admission `no_lookahead` gate and the chain's partition-aware compute consume `_FUNCTION_PARTITION` / `DENIED_FIELDS` / `partition_context`) and closes RESEARCH.md pitfall 4 (a new operator silently acquiring full-panel/lookahead semantics) and pitfall 1 of SUMMARY.md.
Output: `_FUNCTION_PARTITION` table, `DENIED_FIELDS`, `FactorFeatures.partition_context`, `DSL_VERSION = "factor-dsl-v2"`, `shifted_label_ic` leakage gate, and the tests that enforce all of it.

## Context

- @.planning/phases/10-factor-library-multi-factor-model/10-RESEARCH.md — `## DSL Partition-Context Contract + Leakage Test` (the contract spec), `## Common Pitfalls` (pitfall 4)
- @.planning/phases/10-factor-library-multi-factor-model/10-CONTEXT.md — FACT-04 locked decisions
- backend/app/research/factor_dsl.py — `DSL_VERSION` (L10), `ALLOWED_FIELDS` (L12-29), `_FUNCTION_ARITY` (L36-43), `_validate_call` (L160-181), `_validate_expression` (L214-247), `extract_features` (L347-373), `_compile_node` (L400-423), `FactorFeatures`
- backend/tests/research/test_factor_dsl.py — existing rejection + partition tests (the compile-partition test at L45-61 is the model for `_FUNCTION_PARTITION` assertions)
- backend/app/research/factor_registry.py — `create_factor` / `revise_factor` store `parsed.dsl_version`; bumping `DSL_VERSION` means NEW revisions carry v2 while stored revisions keep v1

## Tasks

- **checkpoint:decision — Approve the DSL_VERSION bump to factor-dsl-v2 (one-way door)**
  - Decision: Bump `DSL_VERSION` in `factor_dsl.py` from `"factor-dsl-v1"` to `"factor-dsl-v2"` when the partition-context contract lands.
  - Context: Revisions store their `dsl_version` at creation; `_validated_revision` (evaluation.py L231-245) rejects reuse across versions. After the bump, a v1 expression still parses under the v1 contract for stored revisions, but NEW revisions are v2. The bump is one-way for the research catalog: a future downgrade would silently change the semantics of v2 revisions already admitted.
  - Options:
    - option-a: Bump to `factor-dsl-v2` now, alongside `_FUNCTION_PARTITION` + `DENIED_FIELDS` + `partition_context`. Pros: the contract is versioned from its first day; cross-version reuse is rejected structurally; matches RESEARCH.md. Cons: new revisions are v2-only (v1 expressions remain valid — they just record v2).
    - option-b: Keep `factor-dsl-v1` and add the contract without a bump. Pros: no version churn. Cons: violates the researched contract — the leakage gate and partition semantics would be unversioned, and the shifted-label gate is defined to re-verify on every `DSL_VERSION` change.
  - Resume signal: Select: option-a or option-b

- **build: Add `_FUNCTION_PARTITION`, `DENIED_FIELDS`, and `FactorFeatures.partition_context`**
  - Files: backend/app/research/factor_dsl.py
  - Read first: backend/app/research/factor_dsl.py (L7-43 constants block; L160-247 validators; L347-373 `extract_features`; L400-423 `_compile_node`)
  - Action: Add `PartitionContext = Literal["pointwise", "per_date", "per_symbol"]` and `_FUNCTION_PARTITION: Final[dict[str, PartitionContext]]` beside `_FUNCTION_ARITY` mapping `abs/sign/log1p/clip → "pointwise"`, `rank/zscore → "per_date"` (matches `.over("date")`), `rolling_mean → "per_symbol"` (matches `.over("symbol")`). Add `DENIED_FIELDS: Final[frozenset[str]] = frozenset({"date", "symbol", "label", "forward_return", "_forward_return", "_factor", "_rank", "_zscore"})`. In `_validate_call` and `_validate_expression`, require every call name ∈ `_FUNCTION_PARTITION` (a function in `_FUNCTION_ARITY` without a partition entry is a compile error — a specific `FactorDslError` diagnostic) and reject any field resolving to a denied name with a specific diagnostic. Extend `FactorFeatures` with `partition_context: frozenset[str]` — the effective partition context computed by `extract_features` as the union of leaf contexts (binary ops and fields are pointwise; a call contributes its declared context). Update `as_dict`/signature serialization so the structural signature DOES NOT change (partition context is semantic, not structural — `discover_similar` Jaccard must stay byte-identical). Binary `+ - * /` and fields are pointwise by construction.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_dsl.py -q --tb=short`
  - Done: Every operator declares its partition context in the compiler; denied label/identity fields raise specific diagnostics; `FactorFeatures.partition_context` is populated without changing the structural signature.

- **build: Bump `DSL_VERSION` to `factor-dsl-v2` (per approved decision)**
  - Files: backend/app/research/factor_dsl.py, backend/app/research/factor_registry.py
  - Read first: backend/app/research/factor_dsl.py (L10), backend/app/research/factor_registry.py (create_factor / revise_factor — they persist `parsed.dsl_version`)
  - Action: Set `DSL_VERSION: Final = "factor-dsl-v2"`. Confirm `create_factor` / `revise_factor` store the parsed `dsl_version` unchanged (they already do — no code change needed there) and `_validated_revision` still rejects cross-version reuse (already the case). Existing stored v1 revisions remain readable; new revisions are v2. Ensure no other module hard-codes the v1 string.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_registry.py -q --tb=short`
  - Done: New factor revisions carry `dsl_version = "factor-dsl-v2"`; stored v1 revisions still resolve; cross-version reuse is rejected.

- **test: Extend `test_factor_dsl.py` — partition consistency, denied fields, effective context**
  - Files: backend/tests/research/test_factor_dsl.py
  - Read first: backend/tests/research/test_factor_dsl.py, backend/app/research/factor_dsl.py (module under test)
  - Action: Add tests: (1) table consistency — `set(_FUNCTION_ARITY) == set(_FUNCTION_PARTITION)` (a function added to arity without a partition entry fails this test); (2) denied-field diagnostics — `parse_factor("close + label")` raises a FactorDslError whose message identifies the denied label field; `parse_factor("date")` and `parse_factor("symbol")` are also rejected; (3) effective partition context — `parse_factor("zscore(close) + rolling_mean(volume, 2)").features.partition_context == {"per_date", "per_symbol"}`; `parse_factor("abs(close)").features.partition_context == {"pointwise"}`; (4) the compile-partition behavior test (rank/zscore per-date, rolling_mean per-symbol) continues to pass after the version bump.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_dsl.py -q --tb=short`
  - Done: The partition contract, denied fields, and effective-context computation are locked by tests; a future operator without a partition entry fails CI.

- **test: Deterministic shifted-label leakage gate over all partitioned functions**
  - Files: backend/tests/research/test_factor_dsl.py
  - Action: Implement the module-level `shifted_label_ic(evaluated: pl.DataFrame, *, horizon: int) -> float` in `factor_dsl.py` per RESEARCH.md (label displaced one extra horizon: `close.shift(-2*horizon).over("symbol") / close.shift(-horizon).over("symbol") - 1.0`; per-date `pl.corr("_factor", "_shifted_label")`; return `abs(mean(ic))`, `inf` when empty). Then add a parametrized test iterating ALL functions in `_FUNCTION_PARTITION`: build a fixture panel with two clean expressions per function (e.g., `abs(close)`, `zscore(close)`, `rolling_mean(close, 5)`) and assert `shifted_label_ic <= SHIFTED_LABEL_MAX_ABS_IC (0.02)` — the IC must collapse to ~0 (pitfall: a lookahead factor shows nonzero IC with a misaligned label). Add ONE deliberately lookahead expression (a factor that references the next bar — e.g., constructed via the compiled `close.shift(-1)` semantics) and assert its shifted-label IC EXCEEDS the threshold — proving the gate blocks leakage. The test matrix re-runs on every DSL change because it iterates `_FUNCTION_PARTITION` directly.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_dsl.py -q --tb=short`
  - Done: Clean factors collapse to |IC| ≤ 0.02 under the displaced label; a deliberately lookahead expression is blocked; the matrix is keyed off `_FUNCTION_PARTITION` so new operators are covered automatically.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/research/test_factor_dsl.py tests/research/test_factor_registry.py -q --tb=short
```

All green. The table-consistency test guarantees `set(_FUNCTION_ARITY) == set(_FUNCTION_PARTITION)` — a future operator must declare its partition context or CI fails.

## Success Criteria

- `_FUNCTION_PARTITION` lives beside `_FUNCTION_ARITY`; a function without a partition entry is a compile error.
- `DENIED_FIELDS` is enforced with specific diagnostics; label/identity fields cannot enter an expression.
- `FactorFeatures.partition_context` surfaces the effective semantics without changing the structural signature.
- `DSL_VERSION` is `factor-dsl-v2`; stored v1 revisions still resolve; cross-version reuse rejected.
- The shifted-label leakage gate blocks lookahead expressions and is automatically re-verified on every DSL change.

---

# Plan 10-04 — PIT Universe Resolver + Manifest (FACT-02/06, PIT contract)

**wave:** 2 · **depends_on:** [10-01, 10-02] · **autonomous:** true
**requirements:** [FACT-02, FACT-06]
**files_modified:**
- backend/app/research/universe.py (new)
- backend/app/research/repository.py (extend — membership seed/close/query)
- backend/app/research/signal_chain.py (wire the real resolver into the chain)
- backend/app/research/evaluation.py (manifest `universe_resolution` block)
- backend/tests/research/test_universe_resolution.py (turn RED scaffold green)
- backend/tests/research/test_signal_chain.py (extend — real resolver integration)
- backend/tests/research/test_factor_evaluation.py (extend — manifest fingerprint)

## Objective

Close the survivorship-bias gap measured in RESEARCH.md (144 instruments listed after the enriched window start — a naive today-universe cross-section silently inflates IC) with the minimal point-in-time contract: append-only membership events resolved per evaluation date, applied AFTER the single `BacktestEngine.load_panel` call, and fingerprinted into every manifest. No second datastore; `load_panel` itself is byte-identical.

Purpose: Phases 11-13 inherit per-date universe resolution and the `membership_fingerprint` reproducibility contract. Without this plan, evaluation coverage (FACT-02) and every downstream return number carry survivorship bias (pitfall 1). This plan also fulfills the PIT half of FACT-06 — the chain's resolved universe is now production, not fixture.
Output: `research/universe.py` resolver, repository membership methods, chain wiring, manifest `universe_resolution` block, green `test_universe_resolution.py`.

## Context

- @.planning/phases/10-factor-library-multi-factor-model/10-RESEARCH.md — `## PIT Universe Contract` (schema, seed/close rules, resolver signatures, manifest block, honest limitation: pre-Phase-10 delists unrecoverable — Open Question 1)
- backend/app/research/signal_chain.py (from 10-01) — the resolver injection seam (fixture resolver → real resolver)
- backend/app/research/repository.py — `insert_universe_membership` / `resolve_universe_memberships` (from 10-02)
- backend/app/tickflow/repository.py — `get_instruments` (L1032-1040), `get_enriched_range` (L963-1000), `symbols_lagging` (L1501)
- backend/app/data_providers/schemas.py — `INSTRUMENT_COLUMNS` (L11-13): `listing_date` declared as String `'YYYY-MM-DD'` (Open Question 5 — normalize cast + fallback)
- backend/app/research/evaluation.py — `_manifest` (L341-378) extension point

## Tasks

- **build: Create `research/universe.py` — PIT resolver + seed/close rules**
  - Files: backend/app/research/universe.py, backend/app/research/repository.py
  - Read first: 10-RESEARCH.md `## PIT Universe Contract` (resolver signatures, seed/close rules), backend/app/tickflow/repository.py (L1032-1040, L1501)
  - Action: Implement `resolve_universe(repo, *, universe_name: str, as_of: date, asset_type: str = "stock") -> tuple[frozenset[str], str]` — membership as-of: latest event per symbol with `effective_date <= as_of` is `'listed'`; returns `(symbols, membership_fingerprint)` where fingerprint = sha256 of the sorted symbol tuple. Implement `resolve_universe_daily(repo, *, universe_name, start, end, asset_type="stock") -> pl.DataFrame` with columns `[symbol, date]` — per-date membership exploded from interval endpoints over the window's trading dates (Polars-native interval overlap predicate). Implement the seed rule `seed_membership(repo, instruments: pl.DataFrame, enriched: pl.DataFrame, *, universe_name, source="instruments-sync")`: for each instrument, `effective_date = listing_date` when present (normalize the String `'YYYY-MM-DD'` → ISO date; fallback when missing/invalid to the symbol's first bar date in the enriched lake), `state='listed'`, `asset_type` from the instrument row; INSERT-only. Implement `close_membership(repo, *, universe_name, symbol, effective_date, source="delist-event"|"manual")` appending a `state='delisted'` row. NEVER auto-delist via `symbols_lagging` (suspension ≠ delist — Assumptions Log A4); a long suspension drops out of per-date cross-sections naturally because the enriched panel has no rows for the suspended dates. Add the missing `ResearchRepository` membership helpers if 10-02 did not cover them (query latest event per symbol, list events for a symbol). Module docstring per CONVENTIONS (knows membership events and resolution; doesn't know market data read paths — the chain owns `load_panel`).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_universe_resolution.py -q --tb=short`
  - Done: `resolve_universe`/`resolve_universe_daily` return correct as-of membership with a fingerprint; seed uses listing_date with first-bar fallback; delist closes membership; `symbols_lagging` never triggers a delist.

- **test: Turn `test_universe_resolution.py` green**
  - Files: backend/tests/research/test_universe_resolution.py
  - Read first: backend/tests/research/test_universe_resolution.py (the 10-02 RED scaffold), backend/app/research/universe.py (module under test)
  - Action: Make the scaffolded cases pass: (1) listed-after-start excluded per date — a symbol with `listing_date` after `start` is absent from the per-date set before its listing and present after; (2) delist event closes membership as-of — a symbol with a delist row is excluded on and after the delist effective date; (3) fingerprint changes when membership changes — adding a membership row changes `membership_fingerprint`; (4) `listing_date` String normalization + first-bar fallback when listing_date missing; (5) determinism — two calls with identical membership state return identical fingerprints.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_universe_resolution.py -q --tb=short`
  - Done: The PIT resolver's per-date membership, delist closure, fingerprint stability, and listing_date normalization are locked by tests.

- **refactor: Wire the real resolver into `FactorSignalChain`**
  - Files: backend/app/research/signal_chain.py, backend/tests/research/test_signal_chain.py
  - Read first: backend/app/research/signal_chain.py (from 10-01 — the `universe_resolver` injection seam)
  - Action: Replace the fixture resolver path with the production resolver: `FactorSignalChain.compute` now derives the symbol set via `resolve_universe_daily(universe, start-warmup, end)` → union of per-date eligible symbols → passes that list as `symbols` to `engine.load_panel` → applies the per-date membership inner join (`panel.join(membership_daily, on=["symbol","date"], how="inner")`) AFTER the single governed read. Populate `FactorSignalFrame.resolved_universe` with `{"method": "factor_universe_membership/v1", "membership_fingerprint": ..., "per_date_symbol_counts": {"min":..., "median":..., "max":...}, "excluded_delisted": [...]}`. Keep the `universe_resolver` constructor parameter as the injection seam so tests can still pass a fixture resolver; the default is the production resolver bound to the repository. `load_panel` itself is UNCHANGED — the seam stays the only governed-data access (PanelCache dedup key hashes the sorted symbol list, so identical calls are deduped).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_signal_chain.py tests/research/test_universe_resolution.py -q --tb=short`
  - Done: The chain resolves the per-date universe through `factor_universe_membership`, applies it after the single `load_panel`, and records the fingerprint + per-date counts + excluded delists in `resolved_universe`.

- **refactor: Add the `universe_resolution` block to `evaluation._manifest`**
  - Files: backend/app/research/evaluation.py, backend/tests/research/test_factor_evaluation.py
  - Read first: backend/app/research/evaluation.py `_manifest` (L341-378)
  - Action: Extend `_manifest` with `"universe_resolution": {"method": "factor_universe_membership/v1", "membership_fingerprint": <sha256 of the per-date membership frame>, "per_date_symbol_counts": {"min", "median", "max"}, "excluded_delisted": [symbols]}` sourced from the chain's `FactorSignalFrame.resolved_universe`. The `membership_fingerprint` feeds `catalog._compatibility_warnings` (unchanged — additive key). Extend `test_factor_evaluation.py` with an assertion that a completed evaluation's `input_manifest` carries a `universe_resolution` block with a non-empty `membership_fingerprint`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_evaluation.py -q --tb=short`
  - Done: Every evaluation manifest records the resolved universe with a membership fingerprint, per-date counts, and excluded delisted symbols — reproducible and comparable across runs.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/research/test_universe_resolution.py tests/research/test_signal_chain.py tests/research/test_factor_evaluation.py -q --tb=short
```

All green. The chain reads the universe through `factor_universe_membership` only; `load_panel` is byte-identical.

## Success Criteria

- Per-date universe membership resolved from the append-only table, applied after the single governed read.
- `membership_fingerprint` recorded in every evaluation manifest with per-date counts and excluded delists.
- `symbols_lagging` never auto-delists; pre-Phase-10 historical delists remain an Open Question (forward-fix only).

---

# Plan 10-05 — Admission + Evaluation Breadth (FACT-01/02)

**wave:** 3 · **depends_on:** [10-01, 10-04] · **autonomous:** true
**requirements:** [FACT-01, FACT-02]
**files_modified:**
- backend/app/research/admission.py
- backend/app/research/evaluation.py
- backend/app/research/artifacts.py
- backend/app/research/signal_chain.py
- backend/app/research/catalog.py
- backend/tests/research/test_admission.py
- backend/tests/research/test_factor_evaluation.py
- backend/tests/research/test_experiment_catalog.py

## Objective

Harden the tracer's admission pipeline and evaluation evidence to production reality: verdict candidate trails linked to real catalogued evaluation runs (including rejections), `MIN_TRAIN_OBSERVATIONS` enforcement, IC-correlation dedup against the admitted set on the val window, the monthly evidence series persisted as a checksummed artifact, and coverage computed on the production resolved universe (pre-filter).

Purpose: The tracer (10-01) proved the spine on a fixture; this plan makes the evidence audit-grade and closes pitfall 2 (scalar mean-IC hides hot months) and pitfall 5 (coverage on the post-filter panel).
Output: Full candidate-trail verdicts, monthly-series artifact bundle, resolved-universe coverage, catalog evidence keys.

## Context

- @.planning/phases/10-factor-library-multi-factor-model/10-RESEARCH.md — `## Admission Gates` (candidate trail, IC-correlation dedup), `## Evaluation Upgrade` (monthly series artifact), `## Common Pitfalls` (pitfall 2, pitfall 5), `## Verification Plan` (test cases)
- backend/app/research/admission.py (from 10-01) — extend gate pipeline
- backend/app/research/evaluation.py (from 10-01/10-04) — extend evidence + manifest
- backend/app/research/artifacts.py — `write_bundle` (L42-65) for the monthly-series artifact
- backend/app/research/catalog.py — `record_factor_evaluation` (L230-258) metrics map
- backend/tests/research/test_admission.py (scaffold from 10-02), test_factor_evaluation.py, test_experiment_catalog.py

## Tasks

- **build: Production candidate trails + IC-correlation dedup + `MIN_TRAIN_OBSERVATIONS`**
  - Files: backend/app/research/admission.py
  - Read first: 10-RESEARCH.md `## Admission Gates` (candidate trail spec, gate table), backend/app/research/catalog.py `record_factor_evaluation` (L230-258)
  - Action: Extend the admission run so `candidate_trail_json` carries, for a real run: (a) factor provenance from `FactorRevision.provenance`; (b) each evaluation evidence package reference — the `evaluation_run_id` plus the `ExperimentSnapshot.id` from `ExperimentCatalog.record_factor_evaluation` (the admission orchestration records the evaluation it ran and links the catalog snapshot); (c) every gate result in order. Enforce `MIN_TRAIN_OBSERVATIONS = 40`: if the train window has fewer rebalance dates, the run rejects with a recorded gate failure (deterministic). Implement the IC-correlation dedup against the ADMITTED set: compute the candidate's per-date IC series and each admitted factor's per-date IC series on the val window; `pearson(IC_cand, IC_admitted)`; both the Jaccard structural score (from `discover_similar`) and the IC correlation are written into the gate verdict. Confirm the temporal split is applied identically each run (`TRAIN_FRACTION = 0.7`). Do NOT modify `discover_similar` — the correlation check lives only in admission.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_admission.py -q --tb=short`
  - Done: Verdicts carry a full candidate trail (provenance + evaluation_run_id + ExperimentSnapshot.id + gate results) for admissions AND rejections; the IC-correlation dedup is part of the verdict; `MIN_TRAIN_OBSERVATIONS` is enforced.

- **test: Extend `test_admission.py` — trail, rejection, determinism, IC-corr dedup**
  - Files: backend/tests/research/test_admission.py
  - Read first: backend/tests/research/test_admission.py (the 10-02 RED scaffold), backend/app/research/admission.py (module under test)
  - Action: Make the scaffolded cases pass and add: (1) every gate result recorded in `gates_json` (admitted and rejected); (2) a rejection produces a full verdict row with candidate trail including the evaluation evidence references; (3) temporal split deterministic — two runs on the same dates produce identical train/val boundaries; (4) IC-correlation dedup catches a near-duplicate that Jaccard misses (two expressions with different structure but highly correlated per-date IC — e.g., `close` vs `close * 1.0 + 0.0` with identical panels — Jaccard may flag the exact-structure one; construct a structurally-different-but-IC-correlated pair) — assert the verdict records the IC-corr failure; (5) `MIN_TRAIN_OBSERVATIONS` short-window rejection.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_admission.py -q --tb=short`
  - Done: The admission gate suite proves full candidate trails, deterministic splits, and that IC-correlation dedup catches what Jaccard misses.

- **build: Persist the monthly evidence series as a checksummed artifact + resolved-universe coverage**
  - Files: backend/app/research/evaluation.py, backend/app/research/artifacts.py
  - Read first: backend/app/research/evaluation.py (evidence fields from 10-01), backend/app/research/artifacts.py `write_bundle` (L42-65)
  - Action: Persist the monthly series as `monthly_series.json` in the evidence bundle — extend `_combined_metric_series` (or the artifact orchestration) to add ONE new descriptor via `EvaluationArtifactService.write_bundle` (additive; existing descriptors unchanged) containing the per-month IC/RankIC/ICIR/robustness rows. Ensure `coverage` is computed on the PRODUCTION resolved universe pre-filter using the 10-04 chain's per-date finite counts (the tracer's fixture path is replaced by the resolved-universe path). Wire `monthly_ic_series`, `icir`, `monthly_robustness`, and `coverage` into the `compact_result` written to `result.json`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_evaluation.py -q --tb=short`
  - Done: The monthly evidence set is persisted as a checksummed artifact; coverage reflects the resolved universe (delisted symbols excluded) pre-filter.

- **test: Extend `test_factor_evaluation.py` — monthly artifact + resolved-universe coverage**
  - Files: backend/tests/research/test_factor_evaluation.py
  - Read first: backend/tests/research/test_factor_evaluation.py, backend/app/research/evaluation.py (module under test)
  - Action: Add: (1) the artifact bundle contains `monthly_series.json` with a descriptor whose `checksum_sha256` matches the file bytes; (2) coverage on a panel where a symbol is excluded by the resolved universe on some dates reflects the exclusion (pre-filter, resolved cross-section) and is < 1.0 when non-finite rows exist; (3) the `compact_result` (`result.json`) carries the three scalar metrics.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_factor_evaluation.py -q --tb=short`
  - Done: The monthly-series artifact and resolved-universe coverage are locked by tests.

- **build: Catalog evidence keys — `icir`, `monthly_robustness`, `coverage`, `monthly_ic_series`**
  - Files: backend/app/research/catalog.py
  - Read first: backend/app/research/catalog.py `record_factor_evaluation` (L230-258) metrics map
  - Action: Extend the `metrics` dict built by `record_factor_evaluation` with `icir`, `monthly_robustness`, `coverage`, `monthly_ic_series` from the evaluation result (additive — `_compatibility_warnings` L360-398 is unaffected; new keys do not change the comparison). Ensure `FactorEvidencePackage.metrics` and `ExperimentSnapshot` round-trip the new keys through the repository `_json` canonical serialization.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_experiment_catalog.py -q --tb=short`
  - Done: The catalog records the full monthly evidence set alongside IC/RankIC for every completed factor evaluation.

- **test: Extend `test_experiment_catalog.py` — new evidence keys round-trip**
  - Files: backend/tests/research/test_experiment_catalog.py
  - Read first: backend/tests/research/test_experiment_catalog.py, backend/app/research/catalog.py (module under test)
  - Action: Add a test that records a completed `FactorEvaluationResult` carrying `icir`, `monthly_robustness`, `coverage`, `monthly_ic_series` and asserts the returned `ExperimentSnapshot.metrics` contains all four keys with the expected values, and that a snapshot `as_dict()` round-trips them.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_experiment_catalog.py -q --tb=short`
  - Done: The new evidence keys persist and round-trip through the immutable catalog boundary.

- **refactor: Delete the legacy `_evaluate_panel` adapter — evaluation delegates fully to the chain**
  - Files: backend/app/research/evaluation.py, backend/app/research/signal_chain.py, backend/tests/research/test_signal_chain.py
  - Read first: backend/app/research/evaluation.py (L247-260 `_evaluate_panel`, L268-284 `_correlation_series`), backend/tests/research/test_signal_chain.py (the cross-consumer equality test)
  - Action: Remove the legacy `FactorEvaluationService._evaluate_panel` adapter and its `_correlation_series` companion — the 10-01 refactor left them as the phase's one sanctioned exception, and this task closes that seam so evaluation delegates fully to `FactorSignalChain.compute` and a second factor-value implementation cannot drift back in. Update the cross-consumer equality test in `test_signal_chain.py`: instead of comparing `chain.compute(...)` to `FactorEvaluationService._evaluate_panel(...)`, freeze the expected `FactorSignalFrame` for the fixture config (columns, values, `panel_fingerprint`, `resolved_universe` block) and assert `chain.compute(...)` equals that frozen frame. Verify the phase grep gate: `grep -rl "parse_factor\|compile_factor" backend/app --include="*.py"` lists only `backend/app/research/signal_chain.py` and `backend/app/research/factor_dsl.py` (the DSL itself) — no module other than `signal_chain.py` imports `parse_factor`/`compile_factor`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_signal_chain.py tests/research/test_factor_evaluation.py -q --tb=short`, then the grep gate `grep -rl "parse_factor\|compile_factor" backend/app --include="*.py"` lists only `signal_chain.py` and `factor_dsl.py`
  - Done: `_evaluate_panel` and `_correlation_series` are deleted from evaluation.py; the cross-consumer equality test asserts against a frozen expected frame; the phase grep gate passes with only `signal_chain.py` and `factor_dsl.py` importing `parse_factor`/`compile_factor`.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/research/test_admission.py tests/research/test_factor_evaluation.py tests/research/test_experiment_catalog.py -q --tb=short
```

All green.

## Success Criteria

- Admission verdicts (admission AND rejection) carry the full candidate trail with catalogued evaluation references and every gate result.
- The legacy `_evaluate_panel` adapter is deleted; evaluation delegates fully to the chain and the phase grep gate lists only `signal_chain.py` + `factor_dsl.py` importing `parse_factor`/`compile_factor`.
- IC-correlation dedup is recorded in verdicts; `MIN_TRAIN_OBSERVATIONS` enforced.
- The monthly evidence set is persisted as a checksummed artifact; coverage is computed on the resolved universe pre-filter.
- The catalog records `icir`, `monthly_robustness`, `coverage`, `monthly_ic_series` and round-trips them.

---

# Plan 10-06 — Composite + Catalog Breadth (FACT-03/05)

**wave:** 4 · **depends_on:** [10-01, 10-05] · **autonomous:** true
**requirements:** [FACT-03, FACT-05]
**files_modified:**
- backend/app/research/models.py
- backend/app/research/catalog.py
- backend/tests/research/test_models.py
- backend/tests/research/test_experiment_catalog.py

## Objective

Harden the composite model and admitted-factor catalog to production: IC-weighted weights sourced from the catalog-recorded mean IC (cross-module integrity — the library IC used to weight MUST equal the evaluation-recorded IC for the same revision/config), snapshot-immutable composite outputs bound by `input_snapshot_sha256` (O_EXCL + fsync + sha256, consumed by Phase 11 by snapshot — never a live module hand-off), and admitted-factor summary storage (coverage, finite counts, signature) with revision lineage.

Purpose: FACT-03's hand-off contract — Phase 11 consumes the composite BY SNAPSHOT, so the output artifact + sha256 must be immutable and reproducible. FACT-05's summary storage — coverage/finite-counts/signature, never full factor matrices (anti-feature).
Output: Production composite persistence, catalog summary + lineage, green `test_models.py` + `test_experiment_catalog.py`.

## Context

- @.planning/phases/10-factor-library-multi-factor-model/10-RESEARCH.md — `## Multi-Factor Composite` (persistence, snapshot discipline, IC-weighted = mean IC NOT ICIR — Assumptions Log A2 / Open Question 2), `## Schema/Migration Sketch` (factor_model_models, factor_model_composites), `## Common Pitfalls` (pitfall 3)
- @.planning/phases/10-factor-library-multi-factor-model/10-CONTEXT.md — FACT-03 locked decisions
- backend/app/research/models.py (from 10-01), catalog.py, repository.py
- backend/app/research/artifacts.py — `write_bundle` (L42-65) immutable artifact discipline
- backend/app/backtest/frozen_panel.py — `FrozenPanelArtifactStore` checksum discipline (L38-137) as the pattern for snapshot consumption

## Tasks

- **build: IC-weighted from catalog evidence + snapshot-immutable composite outputs**
  - Files: backend/app/research/models.py, backend/app/research/repository.py
  - Read first: backend/app/research/models.py (from 10-01), 10-RESEARCH.md `## Multi-Factor Composite` (persistence), backend/app/research/artifacts.py `write_bundle`
  - Action: Change the IC-weighted weight source so `w_r = mean_ic_r / sum mean_ic` reads the mean IC from the CATALOG-RECORDED evidence (the `ExperimentSnapshot.metrics["ic_summary"]["mean"]` for the same revision + resolved config — NOT a live recomputation), enforcing cross-module integrity: if the recorded mean IC is missing for a revision, the model build fails closed rather than defaulting to equal weight silently. Persist the composite output immutably: compute `input_snapshot_sha256` over `(sorted revision_ids, weighting, membership_fingerprint, panel fingerprints)`; write the output frame through `EvaluationArtifactService.write_bundle` (O_EXCL + fsync + sha256) and record the `output_sha256` + `artifact_relative_path` in `factor_model_composites` via the repository method from 10-02. Float64 accumulation only; revision ids sorted; no randomness anywhere.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_models.py -q --tb=short`
  - Done: IC-weighted weights equal catalog-recorded mean IC normalized; composite outputs are immutable artifacts bound by `input_snapshot_sha256`; a missing recorded mean IC fails the build closed.

- **test: Turn `test_models.py` green — weights, determinism, immutability**
  - Files: backend/tests/research/test_models.py
  - Read first: backend/tests/research/test_models.py (the 10-02 RED scaffold), backend/app/research/models.py (module under test)
  - Action: Make the scaffolded cases pass and add: (1) equal-weight `weights == {r: 1/n}`; IC-weighted `weights` proportional to the catalog-recorded mean IC (assert `w_r / w_s == mean_ic_r / mean_ic_s`); (2) two identical builds (same revision_ids, weighting, universe) produce identical `input_snapshot_sha256`; (3) output artifact immutable — a second computation with a different input fails to overwrite the prior namespace (O_EXCL) and the artifact descriptor checksum matches the bytes; (4) determinism — repeated compute over the same inputs yields identical composite values; (5) fail-closed — a revision without recorded evidence raises.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_models.py -q --tb=short`
  - Done: The composite contract — weights from catalog evidence, deterministic sha256, immutable output, fail-closed missing evidence — is locked by tests.

- **build: Admitted-factor catalog summary storage + revision lineage**
  - Files: backend/app/research/catalog.py
  - Read first: backend/app/research/catalog.py (FactorEvidencePackage, ExperimentSnapshot, record_factor_evaluation), 10-RESEARCH.md `## Schema/Migration Sketch` + `## Multi-Factor Composite` (first-class catalog record)
  - Action: Add admitted-factor summary storage: for an admitted factor, persist a catalog entry exposing coverage (mean + series), finite counts, and the factor signature (`ast_signature`/`shape_signature` from the revision) — summary ONLY, never full factor value matrices (CONTEXT anti-feature). Wire revision lineage: the catalog entry links to the factor definition and every revision (`factor_id`, `revision_id`, `revision_number`) so a researcher can trace an admitted factor back through its revisions. Expose the composite model as a first-class catalog record (model definition + latest composite snapshot reference with `input_snapshot_sha256`). Keep `_compatibility_warnings` additive.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_experiment_catalog.py -q --tb=short`
  - Done: The catalog stores admitted-factor summaries (coverage, finite counts, signature) with revision lineage and a first-class composite-model record bound by snapshot sha256.

- **test: Extend `test_experiment_catalog.py` — summary + lineage + composite record**
  - Files: backend/tests/research/test_experiment_catalog.py
  - Read first: backend/tests/research/test_experiment_catalog.py, backend/app/research/catalog.py (module under test)
  - Action: Add tests: (1) an admitted factor's catalog entry contains coverage (mean + series), finite counts, and the revision signature, and the lineage fields (`factor_id`, `revision_id`, `revision_number`) resolve to the registry revision; (2) a composite model recorded in the catalog is retrievable with its latest composite snapshot reference (`input_snapshot_sha256` + artifact path); (3) no full factor-value matrix is persisted (the metrics map carries summaries only).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_experiment_catalog.py -q --tb=short`
  - Done: The catalog's summary storage, revision lineage, and composite-model record are locked by tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/research/test_models.py tests/research/test_experiment_catalog.py -q --tb=short
```

All green. Phase 11 consumes composite outputs by artifact snapshot + sha256 only.

## Success Criteria

- Composite weights derive from catalog-recorded mean IC (cross-module integrity); missing evidence fails closed.
- Composite outputs are immutable, checksum-bound, and consumed by snapshot (Phase 11 contract).
- The catalog stores admitted-factor summaries with revision lineage and a first-class composite-model record.

---

# Consolidated Threat Model

> `workflow.security_enforcement: true` (config.json) — section required. Trust model: local single-user research host; no new auth/session surface (ASVS V2/V3 N/A). New records are server-issued only (V4 minimal). DSL restricted grammar (V5); SHA-256 checksums for snapshots/manifests (V6).

## Trust Boundaries

| Boundary | Description |
|---|---|
| Researcher → DSL compiler | Untrusted factor source text crosses here; must be restricted grammar with no eval/exec escape hatch. |
| Signal chain → governed lake | Only `BacktestEngine.load_panel` may read market data; universe filter applies after this single seam. |
| Admission pipeline → append-only verdicts | Every gate result (incl. rejections) becomes an immutable row; candidate trail is server-assembled, never client-selected. |
| Composite model → immutable artifacts | Output bytes are written O_EXCL + fsync and consumed by Phase 11 by sha256, never a live object hand-off. |
| Research modules → dependencies | scipy promoted to base; sklearn stays shadow lazy-import (module-top import forbidden). |

## STRIDE / ASVS L1 Traceability

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|---|---|---|---|---|---|
| T-10-01 | Tampering | DSL expression injection | high | mitigate | Allowlist compiler (`ALLOWED_FIELDS`, `_FUNCTION_ARITY`, `_FUNCTION_PARTITION`); `DENIED_FIELDS` explicit; no eval/exec; compile-boundary validation repeated (`factor_dsl.py:385-423`). Tests: denied-field diagnostics, partition-table consistency. |
| T-10-02 | Elevation of Privilege (data) | Lookahead / label leakage via new operators | high | mitigate | `_FUNCTION_PARTITION` compile contract + shifted-label leakage gate re-run on every DSL change (10-03); `no_lookahead` admission gate consumes `partition_context`. |
| T-10-03 | Tampering | PIT universe membership | high | mitigate | Append-only rows (`INSERT` only; delist = new row), `UNIQUE(universe_name, symbol, effective_date, state)`, `membership_fingerprint` in every manifest; `symbols_lagging` never auto-delists. |
| T-10-04 | Spoofing | Artifact substitution (composite outputs / evidence bundles) | high | mitigate | O_EXCL creation + fsync + sha256 (`artifacts.py:76-118`); `input_snapshot_sha256` binds composite outputs; checksum-verified reads (FrozenPanelArtifactStore pattern). |
| T-10-05 | Spoofing | Evidence-package integrity | medium | mitigate | `FactorEvidencePackage` immutable frozen dataclass; new metrics keys additive; `_compatibility_warnings` compares retained snapshots only. |
| T-10-06 | Tampering | Verdict record integrity | medium | mitigate | `factor_admission_verdicts` UNIQUE(revision_id, policy_version), FK ON DELETE RESTRICT, `input_snapshot_sha256` length-checked; rejections recorded identically to admissions. |
| T-10-SC | Tampering | Python package supply chain | high | mitigate | PyPI-verified scipy/sklearn (Package Legitimacy Audit — npm results are cross-ecosystem false positives); empty-`.venv` Wave 0 gate re-verifies versions and lazy-import audit at install time. |

# Phase Verification

```bash
# Per-wave gates (from backend/)
cd backend && uv sync --extra shadow && uv pip check && .venv/bin/python -c "import scipy,sys; sys.exit(0 if scipy.__version__=='1.17.1' else 1)"   # wave 0 — 1.17.1 (exit 1 on mismatch)
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short                                  # wave 0
cd backend && .venv/bin/python -m pytest tests/research/test_factor_dsl.py tests/research/test_factor_registry.py -q --tb=short  # wave 0
cd backend && .venv/bin/python -m pytest tests/research/test_factor_pipeline.py tests/research/test_signal_chain.py tests/research/test_factor_evaluation.py tests/research/test_admission.py tests/research/test_models.py -q --tb=short  # wave 1 (tracer)
cd backend && .venv/bin/python -m pytest tests/research/test_universe_resolution.py tests/research/test_signal_chain.py tests/research/test_factor_evaluation.py -q --tb=short  # wave 2
cd backend && .venv/bin/python -m pytest tests/research/test_admission.py tests/research/test_factor_evaluation.py tests/research/test_experiment_catalog.py -q --tb=short  # wave 3
cd backend && .venv/bin/python -m pytest tests/research/test_models.py tests/research/test_experiment_catalog.py -q --tb=short  # wave 4

# Phase gate (before /gsd-verify-work)
cd backend && .venv/bin/python -m pytest -x
```

Cross-module integrity checks:
- Library IC used by composite weights == evaluation-recorded mean IC for the same revision/config (10-06 test 1).
- Composite output consumed by Phase 11 == artifact bytes identified by `input_snapshot_sha256` (10-06 test 3).
- `set(_FUNCTION_ARITY) == set(_FUNCTION_PARTITION)` (10-03 test 1) — no operator without partition semantics.
- Grep gate hygiene: partition/denied-field tests use `grep -v '^#'` filtering where negative counts are asserted.

# Phase Success Criteria

- All 6 plans complete with their per-plan gates green.
- The full backend suite is green before `/gsd-verify-work` (phase gate).
- Every locked decision in 10-CONTEXT.md is implemented (see Source Coverage Audit): admission gates with immutable verdicts (FACT-01), full monthly evidence (FACT-02), deterministic composite consumed by snapshot (FACT-03), DSL partition contract + leakage gate (FACT-04), immutable catalog with summary storage + revision lineage (FACT-05), one shared signal chain (FACT-06), and the minimal PIT universe contract.
- No second factor-value implementation exists (grep: only `signal_chain.py` and the DSL import `parse_factor`/`compile_factor`; the legacy `_evaluate_panel` adapter is removed by 10-05).
- Deferred ideas from CONTEXT (richer PIT tooling, FACT-07, Phase 13 ensembling, v2 portfolio objectives, ML expected returns) do NOT appear in any delivered artifact.

# Output

After each plan completes, create the matching summary at `.planning/phases/10-factor-library-multi-factor-model/10-{NN}-SUMMARY.md` documenting what landed, the evidence, and any deviations from this plan. The phase gate is the full backend suite green before `/gsd-verify-work`.
