# Plan 47-01 Summary: FactorSignalChain Wiring + Fingerprints + Candidate→Revision Binding

**Plan:** 47-01 (wave 1)
**Phase:** 47-governed-scoring-admission
**Status:** Complete
**Date:** 2026-08-08

## Objective

Establish the governed scoring identity seam for Phase 47 (AF-REQ-05 SC1): bind every
generated candidate to one evaluatable identity so the three load-bearing engines
(chain / evaluation / admission) operate unchanged, consolidate the full declared
fingerprint set onto the chain frame, and supply the factory fold scorer through the
existing `fold_scorer` seam. No new engine, no forked compute path, no catalog leakage.
This is the foundational Wave 1 layer: plans 47-02 (evidence), 47-03 (admission), and
47-04 (selection OOS) all require a candidate that flows through `FactorSignalChain.compute`
and a complete fingerprint block. Zero new runtime dependencies.

## Commits

| Hash | Message |
|------|---------|
| `cd20e05` | feat(phase-47): exploratory revision binding for generated candidates (47-01-01) |
| `1c797e8` | feat(phase-47): consolidated declared_fingerprints block on chain frame (47-01-02) |
| `ba26da8` | feat(phase-47): factory fold scorer + chain-routing guard (47-01-03) |

## What Was Delivered

### `backend/app/research/factor_registry.py` (modified) — Task 47-01-01

Transient exploratory revision binding (OQ1, option A). Exports:

- **`ALPHA_EXPLORATORY_KIND = "alpha_exploratory"`** — module constant marking a
  transient, research-only revision that binds a generated `AlphaCandidateAttempt`
  to one evaluatable identity.
- **`create_exploratory_revision(*, run_id, candidate_id, candidate_digest,
  canonical_expression, dsl_version, fields, step) -> FactorRevision`** — idempotent:
  first calls `find_exploratory_revision(run_id, candidate_digest)` and returns it if
  present; otherwise mints a research-only `FactorRevision` via `create_factor` with
  `provenance={"kind": ALPHA_EXPLORATORY_KIND, "run_id", "candidate_id",
  "candidate_digest", "step"}`. Fail-closed: the candidate's declared `dsl_version`/
  `fields` must round-trip through `parse_factor(canonical_expression)` — mirroring
  `FactorSignalChain._binding`'s validation surface — so a stale candidate provenance
  never mints a revision.
- **`find_exploratory_revision(run_id, candidate_digest) -> FactorRevision | None`** —
  queries the raw revision store (`repository.list_current_revisions()`), bypassing the
  catalog-filtered `list_current`, so an exploratory revision excluded from the formal
  catalog is still locatable for reconnect/retry idempotency.
- **`list_current()` (hardened)** — now excludes `alpha_exploratory` revisions. This is
  the W2 leakage filter: placed in `factor_registry.py` (in declared scope) rather than
  `admission._jaccard_duplicate`, so **all** registry consumers are covered — the formal
  factor catalog (`GET /factors` → `registry.list_current()`) **and** the admission
  similarity pool (`discover_similar` iterates `list_current()`).

### `backend/app/research/signal_chain.py` (modified) — Task 47-01-02

Consolidated declared-fingerprint block on the chain frame:

- **`FactorSignalFrame.declared_fingerprints: Mapping[str, str]`** — exactly six
  deterministic lowercase SHA-256 digests keyed `panel`, `membership`, `source_field`,
  `warmup`, `missing_data`, `signal`.
- **`_declared_fingerprints(...)` (static helper)** — `panel` and `membership` **reuse**
  the existing `panel_fingerprint` / `resolved_universe["membership_fingerprint"]`
  (no recomputation, existing values byte-identical); `source_field` =
  `digest_bytes({"required_source_fields": sorted(required)})`; `warmup` =
  `digest_bytes({"warmup_days", "warmup_treatment", "load_start_delta_days"})`;
  `missing_data` = `digest_bytes({"missing_data_treatment", "pre_filter_counts"})`
  (W4: `{total, finite}` shape in wave 1; 47-02 enriches `pre_filter_counts` to named
  per-state counts, intentionally changing this digest); `signal` =
  `digest_bytes({"canonical_expression", "dsl_version", "rebalance"})`.
- Computed on **both** the populated `compute` path and the empty-panel `_empty_frame`
  path (IN-08: an empty panel still records a full six-key block, never an empty mapping).
- `digest_bytes` is reused from `run_contract` (canonical sorted-key JSON SHA-256);
  import-safe (`run_contract` only lazy-imports `alpha_factory`).

### `backend/app/research/alpha_scoring.py` (created) — Task 47-01-03

Factory fold scorer + chain-routing guard. Exports:

- **`factor_fold_scorer(fold, *, frame, membership) -> dict`** — consumes the chain frame
  over the fold's TEST window and returns `{"test_stats": {"mean_ic", "rank_ic",
  "coverage", "effective_days"}, "membership_fingerprint", "declared_fingerprints"}` by
  reusing `evaluation._per_date_correlation_series` / `FactorEvaluationService._summary` /
  `_coverage` — the same helpers `evaluate` uses — **never** `StrategyBacktestService`.
  Supplied as `fold_scorer=` to `run_walk_forward` it replaces the default strategy
  backtest per-fold score with factor IC/coverage evidence. Never references the reserved
  OOS fold (only `fold.test_start`/`test_end`; OOS inaccessibility is enforced by
  `run_walk_forward(evaluate_oos=False)`).
- **`_routes_through_chain(func) -> bool`** — source-level check: a function's own source
  references a `FactorSignalChain.compute` call.
- **`assert_all_scoring_through_chain() -> None`** — durable SC1 guard: inspects the live
  source of `FactorEvaluationService.evaluate`, `admission.run_admission`, and
  `walkforward._run_fold` and raises `AssertionError` if any stops routing through
  `FactorSignalChain.compute`. Source-level (structural), not behavioral — cannot see
  dynamic dispatch or runtime monkeypatching (plan-check W3; documented in docstrings).

### `backend/tests/research/test_alpha_scoring.py` (created) — 18 tests

- **47-01-01 (7):** exploratory revision binds candidate to an evaluatable identity whose
  id flows unchanged through the chain; idempotent over `(run_id, candidate_digest)`;
  `find` returns None when absent / locates existing; excluded from the admission
  similarity pool (`_jaccard_duplicate` → 0.0; `discover_similar` never surfaces one);
  excluded from the formal catalog (`list_current`); DSL-version mismatch fails closed.
- **47-01-02 (7):** six stable 64-hex keys, identical computes yield identical blocks;
  `panel`/`membership` reuse existing values; `source_field` changes with required fields;
  `warmup` changes with warmup days (panel/source unchanged); `missing_data` changes with
  counts (signal/source/panel unchanged); `signal` changes with expression + rebalance;
  empty-panel path records a full non-empty block (IN-08).
- **47-01-03 (4):** scorer produces factor-shaped per-fold IC/coverage evidence (no
  backtest), never references `oos_fold`; respects the test window; the chain-routing guard
  passes today and `_routes_through_chain` detects a bypass.

## Test Totals

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/research/test_alpha_scoring.py` (new) | 18 | passed |
| `tests/research/test_signal_chain.py` + `test_factor_evaluation.py` | 23 | passed (contracts unaffected) |
| `tests/research/` (full research suite) | 396 | passed |

## Verification Commands (all green)

```
# Task selections (47-01-01 / 47-01-02 / 47-01-03)
cd backend && pytest tests/research/test_alpha_scoring.py -k 'exploratory or binding or similarity or idempotent or formal_catalog' -q
→ 7 passed

cd backend && pytest tests/research/test_alpha_scoring.py -k 'fingerprint or declared or source_field or warmup or missing_data or signal or empty_frame' -q
→ 7 passed

cd backend && pytest tests/research/test_alpha_scoring.py -k 'fold_scorer or chain_routing or through_chain or routes_through or window' -q
→ 4 passed

# Plan verification: chain + evaluation contracts unaffected (additive fingerprint field;
# existing panel_fingerprint / membership_fingerprint unchanged)
cd backend && pytest tests/research/test_signal_chain.py tests/research/test_factor_evaluation.py -q
→ 23 passed

# Regression: full research suite
cd backend && pytest tests/research/ -q
→ 396 passed
```

## Must-Have Truths (verified)

- ✅ Every generated AlphaCandidateAttempt binds to exactly one evaluatable identity via a
  transient exploratory FactorRevision (`provenance.kind="alpha_exploratory"`) whose id
  passes unchanged into `FactorSignalChain.compute`, `FactorEvaluationService.evaluate`,
  and `run_admission` — no second signal engine and no forked `_binding` path (option A;
  the single `_binding` validation surface is preserved).
- ✅ `FactorSignalFrame` exposes one declared fingerprint block covering panel, PIT-universe
  (membership), source-field, warmup, missing-data, and signal — each a deterministic
  lowercase SHA-256 over stable sorted-key canonical payloads.
- ✅ An exploratory revision never leaks into the formal factor catalog or the admission
  similarity pool; reconnect/retry of the same `(run_id, candidate_digest)` returns the same
  exploratory revision id (idempotent).
- ✅ A factor fold scorer turns a `FactorSignalFrame` into per-fold IC/coverage evidence via
  the existing `fold_scorer(fold, *, frame, membership)` seam (`walkforward.py:578`), and a
  test asserts every scoring entry point routes through `FactorSignalChain.compute`.

## Threat Model Mitigations

- **T-47-01 (Elevation/Spoofing — exploratory revision leaking into the catalog/similarity
  pool):** `list_current()` filters `alpha_exploratory` revisions, so the formal catalog
  (`GET /factors`) and `discover_similar` (→ `_jaccard_duplicate`) never see them. Verified:
  `_jaccard_duplicate` returns 0.0 when the only revisions are exploratory. Phase 49 owns
  catalog promotion.
- **T-47-02 (Tampering — a second binding path forking `_binding`):** option A keeps the
  single `_binding` validation surface; `create_exploratory_revision` mirrors `_binding`'s
  DSL-version/fields checks but never forks `compute`. `signal_chain.py:213-222` unchanged.
- **T-47-03 (Tampering/Information disclosure — scoring bypassing the governed chain):**
  `assert_all_scoring_through_chain` is a durable source-level guard proving evaluate /
  run_admission / `_run_fold` all call `FactorSignalChain.compute`.

## Plan-Check Warning Resolutions

- **W2 (exploratory-revision leakage filter placement):** resolved per plan-check — the
  `provenance.kind` filter is placed at `list_current()` in `factor_registry.py` (in
  declared scope), covering **all** registry consumers (formal catalog + similarity pool)
  so `files_modified` stays accurate and `admission.py` is untouched.
- **W3 (static-guard scope):** `assert_all_scoring_through_chain` is documented as a
  source-level (structural) guard in its docstring — it proves source-level routing but
  cannot see dynamic dispatch/runtime monkeypatching. No code change beyond the docstring.
- **W4 (`missing_data` fingerprint forward-compat):** the wave-1 `missing_data` digest is
  pinned over the current `{total, finite}` `pre_filter_counts` shape; the
  fingerprint-sensitivity test notes that 47-02's enrichment to named per-state counts
  intentionally changes the digest (the wave-2 shape is what ships).

## Deviations

None. The plan was implemented as written. The `missing_data` warmup-fingerprint
forward-compat (W4) and the W2 filter placement are documented above per the plan-check
resolutions, not deviations from the plan.

## Hand-off to Wave 2

1. **`create_exploratory_revision` / `find_exploratory_revision`** + the exploratory
   revision id as the **stable join key** between candidate attempts, evaluation evidence,
   and admission verdicts → 47-02 (immutable per-candidate evidence), 47-03 (admission
   ledger linkage via revision id).
2. **`declared_fingerprints`** block (panel/membership/source_field/warmup/missing_data/
   signal) → 47-02 (extends `missing_data` to per-state counts; freezes the full block into
   the manifest), 47-04 (selection-OOS evidence carries the declared block).
3. **`factor_fold_scorer`** + **`assert_all_scoring_through_chain`** → 47-02 (per-candidate
   per-fold IC evidence via the scorer), 47-04 (exactly-once selection OOS reuses the
   scorer + `evaluate_best_params` confirm-objective-before-slot pattern).

## Files Modified/Created

| File | Action |
|------|--------|
| `backend/app/research/factor_registry.py` | Modified (ALPHA_EXPLORATORY_KIND + create/find exploratory revision + list_current leakage filter) |
| `backend/app/research/signal_chain.py` | Modified (declared_fingerprints field + _declared_fingerprints helper, wired into compute + _empty_frame) |
| `backend/app/research/alpha_scoring.py` | Created (factor_fold_scorer + assert_all_scoring_through_chain) |
| `backend/tests/research/test_alpha_scoring.py` | Created (18 tests) |
| `.planning/phases/47-governed-scoring-admission/47-01-SUMMARY.md` | Created (this file) |
