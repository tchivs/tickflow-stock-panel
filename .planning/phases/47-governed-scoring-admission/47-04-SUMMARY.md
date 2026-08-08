# Plan 47-04 Summary: Deterministic Selection + Exactly-Once Selection OOS

**Plan:** 47-04 (wave 3, final)
**Phase:** 47-governed-scoring-admission
**Status:** Complete
**Date:** 2026-08-09

## Objective

After all candidates are scored over the selection folds, choose exactly one winner
deterministically by the frozen objective and evaluate it on the reserved OOS fold exactly
once (AF-REQ-09 SC5). `evaluate_best_params` (`walkforward.py:245-365`) is the proven
exactly-once template; 47-04 adapts it to candidate identity (no `params_sha256`; identity
is `(run_id, candidate_digest)`) over the 47-02 `research_alpha_fold_evidence` table and a
new `selection_oos` candidate status. The reserved OOS is evaluated once only after
deterministic selection, reconnect/retry returns the existing row, and the outcome is
labeled `selection_oos` — never a blind final validation. Depends on 47-02 (typed fold
evidence) and 47-03 (admission ledger linkage). Zero new runtime dependencies.

## Commits

| Hash | Message |
|------|---------|
| `006b548` | feat(phase-47): deterministic selection + exactly-once selection OOS (47-04) |

## What Was Delivered

### `backend/app/operational/migrations.py` (modified) — Task 47-04-01

`selection_oos` candidate-status rebuild (AF-REQ-09 SC5). A new migration replicates the
Phase 46 rebuild pattern exactly (CREATE `_v2` → INSERT…SELECT → DROP → RENAME): the
expanded `CHECK (status IN (... 'selection_oos'))`, every row/ordinal/digest/status
preserved unchanged, and all four triggers recreated on the rebuilt table
(`research_alpha_candidates_no_update`/`_no_delete`, the same-run artifact guard, and the
cross-table `research_alpha_lineage_same_run` trigger — dropped first because SQLite eagerly
recompiles dependent triggers). `final_blind` is absent from the enum (the explicit
non-goal). `PRAGMA foreign_keys` is restored to ON after the rebuild.

### `backend/app/research/run_contract.py` (modified) — Task 47-04-01

`selection_oos` appended to `CANDIDATE_STATUSES` (`run_contract.py:404`), so
`append_candidate_attempt` accepts the terminal OOS outcome.

### `backend/app/research/repository.py` (modified) — Task 47-04-01

New **`list_alpha_fold_evidence(*, run_id, candidate_digest=None, is_oos=None,
limit=100_000) -> list[dict]`** — returns candidate-keyed fold evidence rows for a run
(ordered by `candidate_digest, fold_index`). `select_winner` loads every selection-fold
(`is_oos=0`) row to reduce each candidate to its objective score; this is a cache-only read
mirroring `list_wf_folds` (no re-validation). Reuses the existing
`record_alpha_fold_evidence` (INSERT; UNIQUE raises) + `find_alpha_fold_evidence`
(idempotent read) from 47-02.

### `backend/app/research/alpha_scoring.py` (modified) — Tasks 47-04-01 + 47-04-02

Two new exports:

- **`select_winner(*, repo, run_id, objective, direction) -> AlphaCandidateAttempt`** —
  loads all `is_oos=0` evidence for the run, reduces each candidate to its objective score
  (mean over folds, matching the frozen objective), and chooses the winner by
  `(direction-aware score, candidate_digest lexicographic)` so worker timing cannot change
  the winner (AF-REQ-23 precedent). `direction` is the optimizer form (`"max"`/`"min"`,
  from `default_direction`). A candidate with incomplete selection-fold evidence (missing
  any fold present in the run) is excluded (fail closed), never averaged as a partial
  winner. Returns the most recent terminal attempt for the winning digest.

- **`evaluate_selection_oos(*, repo, chain, resolver, plan, attempt, revision,
  objective="mean_ic") -> dict`** — evaluates the winner on `plan.oos_fold` exactly once.
  Mirrors `evaluate_best_params`' confirm-objective-before-slot + exactly-once +
  idempotent-reconnect pattern: (1) idempotent reconnect — a retry of the same
  `(run_id, candidate_digest)` returns the existing `is_oos=1` row without recomputing
  (read-before-write, mirroring `_find_existing_fold`); (2) the OOS frame is computed once
  over `plan.oos_fold` — the only place that touches the reserved fold; (3) WR-02: effective
  days (`_effective_test_days`) and the objective metric are confirmed BEFORE the OOS row is
  written, so a failed OOS never burns the once-only slot; (4) the `is_oos=1` fold row is
  recorded — the `UNIQUE (run_id, candidate_digest, fold_index, is_oos=1)` is the
  exactly-once backstop; (5) the outcome is labeled `selection_oos` on the candidate ledger
  (a distinct append-only fact, fresh id/ordinal, linked by `candidate_digest`) — never a
  blind final validation.

A private `_attempt_from_dict` projects a ledger row onto the immutable
`AlphaCandidateAttempt`.

## Acceptance Criteria

- `selection_oos` is a valid candidate status (`append_candidate_attempt` accepts it); the
  rebuild migration preserves every row/ordinal/digest/status unchanged and recreates all
  four triggers; `final_blind` is absent. ✓
- A second `evaluate_selection_oos` for the same `(run_id, candidate_digest)` reconnects to
  the existing `is_oos=1` row without recomputing or duplicating; the DB-level UNIQUE raises
  on a second INSERT (exactly-once backstop). ✓
- A failed OOS (missing objective metric / < 10 effective days) raises BEFORE the OOS row is
  written — the once-only slot is never burned by a failure (WR-02). ✓
- The selection-fold scorer never references `plan.oos_fold`; only `evaluate_selection_oos`
  touches the OOS fold. ✓
- `select_winner` returns the same candidate regardless of fold evaluation order/timing;
  ties break on `candidate_digest` lexicographic; incomplete candidates are excluded. ✓
- Only the winner proceeds to `evaluate_selection_oos`; non-winners never consume the OOS
  fold. ✓

## Tests

- `backend/tests/research/test_alpha_scoring.py`: 16 new tests — OOS exactly-once +
  idempotent reconnect, the DB-level UNIQUE backstop, WR-02 short-window and
  missing-objective failures, OOS-inaccessibility of the scorer, `select_winner`
  determinism / order-independence / tie-break / min-direction / fail-closed incomplete /
  no-complete-raises, and an end-to-end only-the-winner-proceeds test.
- `backend/tests/test_operational_migrations.py`: 2 new tests — the `selection_oos` rebuild
  preserves data (rows/ordinals/digests/statuses unchanged, `selection_oos` accepted,
  `final_blind` rejected, UNIQUE preserved, lineage + append-only triggers recreated,
  `foreign_keys` restored) and the rebuild is idempotent.

## Verification

```
# Task 47-04-01
pytest tests/research/test_alpha_scoring.py -k 'selection_oos or exactly_once or oos or idempotent or reconnect' -q  → 10 passed
pytest tests/test_operational_migrations.py -q                                                                       → 23 passed

# Task 47-04-02
pytest tests/research/test_alpha_scoring.py -k 'select_winner or winner or deterministic or tie_break' -q            → 7 passed

# Final (plan verification)
pytest tests/research/test_alpha_scoring.py tests/research/test_run_contract.py -q                                   → 192 passed

# Regression (walkforward — evaluate_selection_oos imports its helpers)
pytest tests/backtest/test_walkforward.py -q                                                                         → 20 passed
```

## Deviations

1. **Phase 46 migration-test locator sharpened.** The pre-existing
   `test_phase46_generated_candidate_status_rebuild_preserves_data` located its migration by
   `"'generated'" in s`. The 47-04 rebuild necessarily lists `'generated'` in its rebuilt
   CHECK (it preserves the full enum), so that locator now matches two migrations. Narrowed
   to `"'generated'" in s and "'selection_oos'" not in s` — the Phase 46 migration that
   introduced `'generated'` before `selection_oos` existed. Intent preserved; the test still
   asserts exactly one Phase 46 migration.

2. **`select_winner` completeness = union of fold indices.** Per the frozen signature
   `(repo, run_id, objective, direction)` there is no plan/`n_folds` parameter, so the
   "complete fold set" a candidate must cover is the union of fold indices observed across
   all candidates in the run. In a real run every candidate is scored over the same folds,
   so the union is the full set and any candidate missing a fold is excluded (fail closed).
   The "no complete candidate" test seeds two candidates with disjoint fold sets
   (union `{0,1}`, neither covers both) → raises.

3. **`selection_oos` ledger fact uses a fresh id/ordinal.** The candidate ledger is
   append-only (`UNIQUE (run_id, attempt_ordinal)`), so the winner's existing attempt row
   cannot be reused. `evaluate_selection_oos` appends a distinct `selection_oos` fact with a
   fresh `uuid` id and the next ordinal (computed from the ledger), carrying the winner's
   `candidate_digest` and identity fields. The durable exactly-once artifact is the
   `is_oos=1` fold row; the ledger fact is the terminal label.

## Artifacts

- `backend/app/operational/migrations.py`: `selection_oos` status rebuild (all four triggers
  recreated).
- `backend/app/research/run_contract.py`: `selection_oos` in `CANDIDATE_STATUSES`.
- `backend/app/research/repository.py`: `list_alpha_fold_evidence`.
- `backend/app/research/alpha_scoring.py`: `select_winner`, `evaluate_selection_oos`.
- `backend/tests/research/test_alpha_scoring.py` + `test_operational_migrations.py`.

## Phase 47 Complete

With plans 47-01/02/03/04 complete, Phase 47 delivers: candidates flow through the shared
chain with a full declared fingerprint set (47-01); immutable per-candidate evidence +
typed fold rows + measured-date/PIT/policy-state governance (47-02); candidate-ledger-linked
fail-closed admission (47-03); and deterministic selection + exactly-once selection OOS
(47-04). The evidence/OOS contracts are handed to Phase 48 (FactorResearchAgent Two-Stage
Workflow, `ROADMAP.md:114`).
