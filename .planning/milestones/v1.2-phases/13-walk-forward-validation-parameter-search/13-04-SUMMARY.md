---
phase: 13-walk-forward-validation-parameter-search
plan: 13-04
subsystem: backtest/research
tags: [wfwd-03, rank-average, ensemble, polars, artifact-binding, wave-3]
requires:
  - phase: 13-walk-forward-validation-parameter-search
    provides: wf_* append-only tables (wf_validated_strategies, wf_ensembles) + list_validated_strategies/record_wf_ensemble repo methods (13-02), best_params OOS exactly-once + validation gate (13-03)
provides:
  - EnsembleConfig + build_ensemble — Polars rank-average of per-strategy _rank per (symbol, date) with validated-only gate (WFWD-03)
  - save_ensemble — checksum-verified immutable artifact (O_EXCL + fsync + sha256) + append-only wf_ensembles row binding input_snapshot_sha256 / output_sha256 / artifact_relative_path
affects: [13-05 (geometry/reporting breadth), Phase 14 (RebalancePlan consumes ensembles as a signal source)]
actuals:
  tokens: 5846
  tasks: 3
  commits: 5
tech-stack:
  added: []
  patterns: [Polars group_by weighted rank-mean, validated-only fail-closed gate, input-snapshot sha256 binding, deterministic run namespace from name]
key-files:
  created:
    - backend/app/backtest/ensemble.py
  modified:
    - backend/tests/backtest/test_ensemble.py
key-decisions:
  - "build_ensemble requires an explicit repo — a default None would silently skip the validated-only gate"
  - "ensemble_rank = per-date re-rank of the weighted mean with method='max' (tie keeps height; scaffold locks mean 2.0 -> 2.0). method='average' would collapse a full tie to 1.5 and violate the locked contract"
  - "artifact run namespace is deterministically derived from the ensemble name (sha256[:32]) — same name + different input collides on O_EXCL, never overwrites evidence"
patterns-established:
  - "Validated-only gate: every strategy_id must resolve to a wf_validated_strategies row with passed_gate=1, else ValueError (fail-closed)"
  - "Input snapshot = canonical JSON (sorted strategy_ids, weights, validation_record_ids, membership_fingerprint) hashed to sha256"
requirements-completed: [WFWD-03]
coverage:
  - id: D1
    description: "build_ensemble rank-averages validated per-strategy _rank signals per (symbol, date) with a validated-only gate"
    requirement: WFWD-03
    verification:
      - kind: unit
        ref: "tests/backtest/test_ensemble.py#test_build_ensemble_rank_averages_validated_signals"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_ensemble.py#test_build_ensemble_fails_closed_on_unvalidated_strategy"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_ensemble.py#test_build_ensemble_fails_closed_on_non_passed_gate_record"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_ensemble.py#test_build_ensemble_defaults_to_equal_weights"
        status: pass
    human_judgment: false
  - id: D2
    description: "save_ensemble persists the ensemble as a checksum-verified immutable artifact and records an append-only wf_ensembles row binding input/output digests"
    requirement: WFWD-03
    verification:
      - kind: unit
        ref: "tests/backtest/test_ensemble.py#test_save_ensemble_persists_checksum_verified_artifact"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_ensemble.py#test_save_ensemble_idempotent_same_inputs_different_inputs_raise"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_ensemble.py#test_save_ensemble_binds_membership_fingerprint_into_snapshot"
        status: pass
    human_judgment: false
duration: 28min
completed: 2026-08-02
status: complete
---

# Phase 13 Plan 13-04: Rank-Average Ensemble Breadth — Summary

Polars rank-average ensemble of validated-only strategy signals: `EnsembleConfig` + `build_ensemble` compute per-(symbol, date) weighted mean of per-strategy `_rank` (re-ranked per date) behind a fail-closed `passed_gate=1` gate, and `save_ensemble` persists the `[symbol, date, ensemble_rank, ensemble_zscore]` frame as an O_EXCL + fsync + sha256 artifact with an append-only `wf_ensembles` row binding `input_snapshot_sha256` (strategy_ids, weights, validation_record_ids, membership_fingerprint) and `output_sha256` — the Phase 14 signal source (WFWD-03).

## Performance

- **Duration:** ~28 min
- **Started:** 2026-08-02T15:00:00Z
- **Completed:** 2026-08-02T15:28:00Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- `build_ensemble` — pure-Polars rank-average: per-strategy frames stacked, `group_by(symbol, date)` weighted `_rank` mean, per-date re-rank (`method="max"`) → `ensemble_rank`, per-date z-score → `ensemble_zscore`; no scipy, no manual rank loop.
- Validated-only gate — every `strategy_id` must resolve to a `wf_validated_strategies` row with `passed_gate=1` (via `list_validated_strategies`), else `ValueError`; `validation_record_ids` referencing a `passed_gate=0` row also fails closed. The gate cannot be skipped: `build_ensemble`/`save_ensemble` require an explicit `repo`.
- `save_ensemble` — deterministic run namespace (sha256 of name → 32-hex), artifact via `EvaluationArtifactService.write_bundle` (O_EXCL + fsync + sha256); `wf_ensembles` row binds `input_snapshot_sha256` + `output_sha256` + relative path; same name+snapshot idempotent (existing row returned, no second artifact), same name + different input raises `ValueError` (O_EXCL never overwrites evidence).
- Green `test_ensemble.py` — 9 tests locking gate, rank-mean reference, output shape, equal-weight default, window trimming, and artifact binding.
- Per-plan gate `pytest tests/backtest/test_ensemble.py -q --tb=short`: **9 passed**.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create `backtest/ensemble.py` — EnsembleConfig + build_ensemble (rank-average, validated-only)** — `d0789b1` (feat), `55a610b` (docs)
2. **Task 2: Persist the ensemble — `record_wf_ensemble` + checksum-verified artifact** — `d0789b1` (feat, included in task-1 file; verified by smoke test)
3. **Task 3: Turn `test_ensemble.py` green — gate, rank-mean, shape, binding** — `1541c74` (test), `4643994` (test), `9c47f82` (style)

**Plan metadata:** `9c47f82` (style) — no separate docs(13-04) commit; the `docs(13-04)` commit `55a610b` corrected the module docstring semantics and is listed under Task 1.

## Files Created/Modified

- `backend/app/backtest/ensemble.py` — `EnsembleConfig` (frozen/slots), `build_ensemble`, `save_ensemble`, plus gate/weight/snapshot helpers (`_validate_gate`, `_effective_weights`, `_frame_membership_fingerprint`, `_input_snapshot_sha256`).
- `backend/tests/backtest/test_ensemble.py` — extended from 3 RED scaffold cases to 9 green WFWD-03 contract cases (gate incl. passed_gate=0, rank-mean reference, equal-weight default, window trim, artifact checksum read-back, idempotency + O_EXCL collision, snapshot content). Fixed the scaffold `_validated_record` to pass an explicit `id=oos_fold_id` so the verdict's `oos_evidence_fold_id` UNIQUE resolves to the actual OOS fold row.

## Decisions Made

- **`repo` is a required keyword arg to `build_ensemble`** — a `None` default would let a caller silently skip the validated-only gate; the WFWD-03 contract is that a non-validated strategy fails closed, so the gate is structurally unavoidable.
- **`ensemble_rank` semantics** — per-date re-rank of the weighted mean with `method="max"`. The locked scaffold contract asserts mean 2.0 → ensemble_rank 2.0 for a two-symbol full tie; `method="average"` would collapse that tie to 1.5 and violate the contract. Research-sketch phrasing ("mean_rank.rank(method='average')") was adjusted accordingly and documented in the module docstring.
- **Deterministic artifact namespace** — run_id = sha256(name)[:32], so re-saving the same ensemble name with different inputs collides (O_EXCL) instead of silently overwriting; idempotency is handled by the pre-write `wf_ensembles` lookup, not by reusing artifacts.
- **Input snapshot** — canonical JSON of (sorted strategy_ids, weights, validation_record_ids, membership_fingerprint) hashed to sha256; matches the 13-RESEARCH `## Rank-Average Ensembling` binding exactly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test scaffold's OOS evidence fold id was not the persisted fold row**
- **Found during:** Task 1 (running the RED scaffold against the new module)
- **Issue:** `_validated_record` called `record_wf_fold` without an explicit id, then referenced a different id in `record_validated_strategy`'s `oos_evidence_fold_id` — the verdict's `oos_evidence_fold_id` UNIQUE failed with `ValueError: validation verdict conflicts with a persisted OOS evidence fold` (FK RESTRICT).
- **Fix:** pass `id=oos_fold_id` to `record_wf_fold` so the verdict's UNIQUE references the actual OOS fold row.
- **Files modified:** `backend/tests/backtest/test_ensemble.py`
- **Verification:** `pytest tests/backtest/test_ensemble.py` green.
- **Committed in:** d0789b1 (Task 1 commit)

**2. [Rule 1 - Bug] `save_ensemble` idempotent lookup needed a same-name filter**
- **Found during:** Task 2 smoke test
- **Issue:** the idempotency lookup iterated all `wf_ensembles` rows without filtering by name, so a same-snapshot row under a different name would be wrongly treated as idempotent.
- **Fix:** skip rows whose `name` differs before comparing `input_snapshot_sha256`.
- **Files modified:** `backend/app/backtest/ensemble.py`
- **Verification:** smoke test: same name+snapshot idempotent, same name + different input raises.
- **Committed in:** d0789b1 (Task 1/2 commit)

**3. [Rule 1 - Bug] `build_ensemble` window filter compared date via Utf8 cast (fragile typing)**
- **Found during:** Task 1 review
- **Issue:** `pl.col("date").cast(pl.Utf8)` on a Date column yields ISO strings, but the comparison relies on the caller's `start`/`end` being ISO strings too — mixing `date`/`datetime` inputs would silently mis-filter.
- **Fix:** normalize `start`/`end` through `_iso()` (handles `date`/`datetime`/`str`) and compare against the date strings directly.
- **Files modified:** `backend/app/backtest/ensemble.py`
- **Verification:** `test_build_ensemble_window_trims_to_requested_dates` green; all 9 tests pass.
- **Committed in:** d0789b1 (Task 1/2 commit)

**4. [Rule 1 - Bug] Flaky input-snapshot reference in the test**
- **Found during:** Task 3 (running the backtest suite)
- **Issue:** the manual snapshot payload in `test_save_ensemble_binds_membership_fingerprint_into_snapshot` listed `validation_record_ids` in insertion order while `_input_snapshot_sha256` sorts them — verdict ids are random per run, so the test failed intermittently.
- **Fix:** sort `validation_record_ids` in the test's manual payload to mirror the implementation.
- **Files modified:** `backend/tests/backtest/test_ensemble.py`
- **Verification:** ensemble tests pass 3/3 consecutive runs; full backtest suite green.
- **Committed in:** 4643994 (Task 3 commit)

**5. [Rule 3 - Lint] RUF002 ambiguous multiplication sign**
- **Found during:** post-task lint pass
- **Issue:** `×` in the module docstring flagged by ruff (ambiguous char).
- **Fix:** replaced with `x`.
- **Files modified:** `backend/app/backtest/ensemble.py`
- **Verification:** `ruff check` clean.
- **Committed in:** 9c47f82 (style)

---

**Total deviations:** 5 auto-fixed (4 Rule 1, 1 Rule 3)
**Impact on plan:** All auto-fixes were correctness/determinism fixes within the task's own files. No scope creep; no architectural changes.

## Issues Encountered

- **`EvaluationArtifactService` has no checksum-verified read** — the plan referenced a "read via the existing checksum-verified read" for the artifact-binding test; `research/artifacts.py` only exposes `write_bundle` (O_EXCL + fsync + sha256 descriptor). The test instead re-hashes the artifact bytes on disk and compares against the row's `output_sha256` — the same guarantee, exercised at the write boundary where the service is authoritative.

## Auth Gates

None.

## Known Stubs

None — no stubs in delivered code.

## Threat Flags

None — no new network endpoints, auth paths, file-access patterns beyond the existing artifact service, or execution routes. The ensemble layer consumes append-only research records (`wf_validated_strategies`, `wf_ensembles`) and writes research-use artifacts only; the validated-only gate is a fail-closed security boundary.

## Self-Check: PASSED

- `backend/app/backtest/ensemble.py` — exists; `build_ensemble`/`save_ensemble`/`EnsembleConfig` present; ruff clean.
- `backend/tests/backtest/test_ensemble.py` — 9 green tests; `pytest tests/backtest/test_ensemble.py -q --tb=short` → 9 passed.
- Commits `d0789b1`, `55a610b`, `1541c74`, `4643994`, `9c47f82` exist on `gsd/v1.2-end-to-end-factor-portfolio-pipeline-in-progress`.
- Regression: `tests/backtest/` → 100 passed; `tests/backtest/test_optimizer_run.py tests/backtest/test_walkforward.py` → 30 passed; `tests/test_operational_migrations.py tests/research tests/portfolio` → 243 passed.

## Next Phase Readiness

- WFWD-03 deliverable complete: validated-only rank-average ensemble with exact `[symbol, date, ensemble_rank, ensemble_zscore]` output and checksum-bound artifact persistence — the Phase 14 signal source.
- 13-05 (geometry robustness + reporting breadth) builds on 13-01/13-03; the ensemble layer is independent of 13-05's fold-geometry work.
- No blockers.

---
*Phase: 13-walk-forward-validation-parameter-search*
*Completed: 2026-08-02*
