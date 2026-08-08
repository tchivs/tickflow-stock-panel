# Plan 47-02 Summary: Immutable Per-Candidate Evidence + Manifest Cost/Fold Extension + Typed Fold Evidence

**Plan:** 47-02 (wave 2)
**Phase:** 47-governed-scoring-admission
**Status:** Complete
**Date:** 2026-08-08

## Objective

Produce immutable per-candidate evaluation evidence and extend the frozen manifest so a
governed walk-forward + cost policy can be built from it (AF-REQ-06 SC2, AF-REQ-07 SC3).
The evaluation metrics already existed (`evaluation.py:103-152,493-508`); the work was
(a) additive manifest fields gated on a declared scoring stage, (b) a cost/turnover
diagnostic without a second engine, (c) per-state exclusion counts, (d) durable
per-candidate artifact binding, and (e) a typed candidate-keyed fold-evidence table (the
research-flag verdict: `wf_folds` is strategy/params-shaped and cannot carry candidate
identity). Depends on 47-01 (exploratory revision binding + `declared_fingerprints` +
`factor_fold_scorer`). Zero new runtime dependencies.

## Commits

| Hash | Message |
|------|---------|
| `1b03171` | feat(phase-47): additive scoring/cost/fold manifest validation (47-02-01) |
| `112945d` | feat(phase-47): per-state exclusion counts + cost/turnover diagnostic (47-02-02) |
| `eacfe5d` | feat(phase-47): per-candidate evidence binding + typed fold-evidence table (47-02-03) |

## What Was Delivered

### `backend/app/research/run_contract.py` (modified) — Task 47-02-01

Scoring-gated additive manifest validation (OQ2, T-47-04). `validate_manifest` now calls
`_validate_scoring_stage(manifest)`: when and only when a `scoring` group is declared, it
fails closed unless the manifest also carries:

- `fold_geometry.oos_size` and `fold_geometry.horizon` — positive integers (the inputs
  `wf_plans` requires, `migrations.py:1721-1722`), so a `WalkForwardPlan` can be rebuilt
  from the frozen manifest.
- a `costs` group `{commission_pct, stamp_tax_pct, slippage_bps}` — `commission_pct`/
  `stamp_tax_pct` as bounded fractions in `[0, 1)`; `slippage_bps` as a non-negative
  basis-point float (`< 1e4`), mirroring `BacktestConfig.slippage_bps` (`engine.py:44`,
  default `5.0`) and the `cost_diagnostics` cost-rate formula.
- `scoring.rebalance` (`daily`/`weekly`/`monthly`), `scoring.n_groups` (int ≥ 2),
  `scoring.warmup_days` (non-negative int).

A manifest **without** a `scoring` group validates byte-for-byte as before — completed
Phase 45/46 frozen snapshots are never invalidated. `scoring`/`costs` are intentionally
**not** added to `REQUIRED_MANIFEST_GROUPS` (they are optional). Any scoring/cost/fold
input change alters the canonical `manifest_sha256` (new run, no mutation, D-01).

### `backend/app/research/signal_chain.py` (modified) — Task 47-02-02

Per-state exclusion counts (OQ3). `compute` now emits a `pre_filter_counts` where each
date maps to `{total, finite, non_finite, suspended, stale, source_quality_excluded,
warmup_excluded}` that **partitions** the cross-section:

- Evaluation-window dates preserve `total`/`finite` byte-for-byte (computed over the
  forward-return-finite cross-section as before, IN-01), with `non_finite = total − finite`
  and the named buckets structurally zero until a suspended/stale/source-quality rule is
  declared (audit surface only).
- Warmup dates (`< config.start`, present when `warmup_days > 0` and the panel extends
  before `start`) carry `warmup_excluded == total` and are skipped by the coverage
  diagnostic.

The invariant `finite + non_finite + suspended + stale + source_quality_excluded +
warmup_excluded == total` holds for every date. The `missing_data` declared fingerprint now
digests the per-state shape (47-01 W4 resolved).

### `backend/app/research/evaluation.py` (modified) — Task 47-02-02

Cost/turnover **diagnostic** (OQ4) + coverage warmup-skip. New exports:

- **`cost_diagnostics(frame, *, costs, rebalance) -> dict`** — a one-pass turnover×cost
  DIAGNOSTIC (NOT execution P&L) over the rebalance-dated chain frame. Equal-weight
  long-short weights are the cross-sectional `_zscore` (dollar-neutral); turnover per
  rebalance is `0.5·Σ|w_t − w_{t−1}|` (`w_{t−1}=0` on the first date);
  `cost_rate = commission_pct·2 + stamp_tax_pct + slippage_bps·2/1e4` (mirrors
  `BacktestConfig.buy/sell_cost_pct`, `engine.py:69-76`); `cost_drag =
  total_turnover·cost_rate`; `net_long_short_return = raw − cost_drag`. A zero cost rate
  degrades gracefully (`cost_drag=0`, net == raw). Does not invoke
  `StrategyBacktestService`.
- **`_coverage`** — skips warmup dates so coverage is measured over the evaluation window
  only.
- **`ResolvedEvaluationConfig.costs`** (optional, default `{}`) and
  **`FactorEvaluationResult.cost_diagnostics`** (default `{}`) — wired into `evaluate()`
  so a scoring run with a declared `costs` group bakes the diagnostic into the result.
  Admission's group-NAV still uses `fees_pct=0` (additive; no-execution boundary,
  `REQUIREMENTS.md:69,78`).

### `backend/app/research/alpha_scoring.py` (modified) — Task 47-02-03

Per-candidate immutable evidence binding (AF-REQ-07 SC3). New exports:

- **`record_candidate_evidence(*, repo, artifact_service, attempt, revision, result,
  declared_fingerprints, costs) -> dict`** — writes one content-addressed evidence
  artifact (full `FactorEvaluationResult.as_dict()` + six declared fingerprints + declared
  cost policy; `cost_diagnostics` is already inside the result) via
  `AlphaRunArtifactService`, records it through the service-owned `append_artifact` seam,
  then appends a candidate attempt whose `evidence_artifact_id` is set with
  `artifact_verified=True`. A **completed** evaluation preserves the candidate's prior
  status (`generated`, pending admission in 47-03); a **failed/invalid** evaluation records
  `status='failed'` with the diagnostic as `reason` — never a zero score or a `completed`
  evidence row (`_candidate_outcome`).
- **`record_selection_fold_evidence(*, repo, run_id, candidate_digest, revision_id, folds)
  -> list[dict]`** — records `is_oos=0` selection-fold evidence via `factor_fold_scorer`
  (47-01) in the candidate-keyed table; idempotent on reconnect (`find_alpha_fold_evidence`
  skips an already-recorded fold). The reserved OOS fold is never recorded here (47-04 owns
  the single `is_oos=1` row).

### `backend/app/research/repository.py` (modified) — Task 47-02-03

Append-only candidate fold-evidence persistence. New exports:

- **`record_alpha_fold_evidence(*, run_id, candidate_digest, fold_index, is_oos,
  revision_id, train_start, train_end, test_start, test_end, membership_fingerprint,
  declared_fingerprints, stats) -> dict`** — INSERT; the `UNIQUE (run_id,
  candidate_digest, fold_index, is_oos)` raises `ValueError("alpha fold evidence already
  recorded")` on a second write.
- **`find_alpha_fold_evidence(*, run_id, candidate_digest, fold_index, is_oos) -> dict |
  None`** — idempotent read (mirrors `walkforward._find_existing_fold`).

### `backend/app/operational/migrations.py` (modified) — Task 47-02-03

New `research_alpha_fold_evidence` table (research-flag verdict). Candidate-keyed
`UNIQUE (run_id, candidate_digest, fold_index, is_oos)` mirroring `wf_folds`'
INSERT-only discipline (`no_update`/`no_delete` triggers) — the selection-OOS exactly-once
becomes a UNIQUE over the candidate-keyed row. `wf_folds` and `wf_validated_strategies`
are untouched (two provenance models kept separate).

## Verification

All task-level pytest selections green; the manifest/freeze and evaluation contracts are
unaffected (additive fields; existing metrics unchanged).

| Command | Result |
|---------|--------|
| `pytest tests/research/test_run_contract.py -k 'manifest or freeze or digest or idempotent or scoring or costs' -q` | **29 passed** |
| `pytest tests/research/test_alpha_scoring.py -k 'pre_filter or cost or turnover or diagnostic' -q` | **10 passed** |
| `pytest tests/research/test_alpha_scoring.py -k 'evidence or fold_evidence or artifact or failed or append_only' -q && pytest tests/test_operational_migrations.py -q` | **7 passed** + **21 passed** |
| `pytest tests/research/test_run_contract.py tests/research/test_factor_evaluation.py -q` (plan final) | **147 passed** |
| `pytest tests/research/ tests/test_operational_migrations.py -q` (full sweep) | **445 passed** |

`test_signal_chain.py:147` (the frozen `pre_filter_counts` assertion) and the coverage
ratios in `test_factor_evaluation.py` were re-grounded to the new per-state shape;
eval-window `total`/`finite` are preserved so existing coverage semantics hold.

## Test totals

- **New tests added:** 12 in `test_run_contract.py` (scoring-stage manifest), 9 in
  `test_alpha_scoring.py` (per-state counts + cost diagnostic), 7 in
  `test_alpha_scoring.py` (per-candidate evidence binding + typed fold evidence), and 1
  in `test_operational_migrations.py` (new table constraints/triggers) — 29 new tests.
- **Full research + migrations sweep:** 445 passed, 0 failed.

## Deviations

1. **`slippage_bps` bound (47-02-01).** The plan literal "each a bounded float in `[0, 1)`"
   would reject any realistic basis-point value (`BacktestConfig` default is `5.0`; the
   `cost_diagnostics` cost-rate divides `slippage_bps` by `1e4`, confirming bps units).
   `commission_pct`/`stamp_tax_pct` are validated as fractions in `[0, 1)`; `slippage_bps`
   is validated as a non-negative basis-point float (`[0, 1e4)`), consistent with
   `engine.py` and the cost-rate formula. Documented in `_validate_scoring_stage`.
2. **`record_selection_fold_evidence` signature (47-02-03).** Takes an iterable of
   `(fold, frame, membership)` triples and scores each via `factor_fold_scorer` internally
   (the walkforward `fold_scorer(fold, *, frame, membership)` seam), rather than taking a
   single plan/frame and computing per-fold membership. This keeps it a pure, testable
   persistence orchestrator; 47-04 supplies the real fold list.
3. **`test_evaluation.py` (plan final verification).** The plan's final verification names
   `tests/research/test_evaluation.py`, which does not exist; the evaluation contract lives
   in `tests/research/test_factor_evaluation.py` (run instead — 147 passed combined with
   `test_run_contract.py`).

## Hand-off

To **47-03** (admission): the immutable per-candidate evidence artifact +
`evidence_artifact_id` binding, the exploratory revision id (stable join key from 47-01),
and the `status='failed'` reason path. Admission records `rejected`/`admitted`/`failed`
onto the candidate ledger via the exploratory revision id.

To **47-04** (selection OOS): `research_alpha_fold_evidence` (candidate-keyed, INSERT-only,
selection folds `is_oos=0`), the scoring-gated manifest (`oos_size`/`horizon`/`costs`/
`scoring`), `record_selection_fold_evidence`, and the exactly-once `is_oos=1` slot +
`selection_oos` status into the same table. `run_contract.py` was edited only in
`validate_manifest` (distinct region from 47-03's planned `policy.fingerprint` work in
`freeze_input_snapshot`) per plan-check W1.
