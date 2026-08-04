---
phase: 13-walk-forward-validation-parameter-search
plan: 13-02
subsystem: backtest/research/operational
tags: [wfwd-01, wfwd-02, wfwd-03, wave-0, migration, repository, test-scaffold]
requires: []
provides: [wf_* tables, wf_* repo methods, wave-0 test scaffolding]
affects: [migrations.py, repository.py, tests/backtest, tests/test_operational_migrations.py]
tech-stack:
  added: []
  patterns: [append-only SQLite + immutability triggers, IntegrityError->ValueError, measured-calendar fold fixture]
key-files:
  created:
    - backend/tests/backtest/conftest.py
    - backend/tests/backtest/test_walkforward.py
    - backend/tests/backtest/test_ensemble.py
  modified:
    - backend/app/operational/migrations.py
    - backend/app/research/repository.py
    - backend/tests/test_operational_migrations.py
    - backend/tests/backtest/test_optimizer_run.py
decisions:
  - option-a: ONE appended migration script with all five wf_* tables (the approved one-way door)
  - wf_folds UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256) = exactly-once incl. OOS
  - wf_validated_strategies.oos_evidence_fold_id UNIQUE ties the verdict to the once-evaluated OOS
  - wf_search_runs.oos_excluded CHECK + repo fail-closed on 0
  - resolved_asset_ids_json TEXT NOT NULL per the plan fix (Phase 14 binding)
metrics:
  duration: 0
  completed: "2026-08-02"
status: complete
---

# Phase 13 Plan 13-02: Wave 0 wf_* Migration, Repo Methods, Test Scaffolding — Summary

Append-only foundation for Phase 13: the five `wf_*` tables migrate in ONE atomic script (approved option-a), `ResearchRepository` gains the append-only `wf_*` methods with the exactly-once OOS / oos_excluded / validated-verdict contracts, and the Wave 0 test scaffolding (2 new test files + measured-calendar conftest + `test_optimizer_run.py` OOS-search cases + migration tests) is in place.

## Task Status

| # | Task | Type | Commit | Status |
|---|------|------|--------|--------|
| 1 | Approve the five append-only wf_* tables (one-way door) | checkpoint:decision | — | APPROVED (user pre-approval, implemented directly per batch context) |
| 2 | Append Phase 13 migration script + extend migration tests | build | ce164b1 | done |
| 3 | Extend ResearchRepository with wf_* methods | build | ab5fe58, 2f3daad | done |
| 4 | Scaffold new test files + conftest + test_optimizer_run.py OOS cases | test | 2f3daad, 56987db | done |

## Wave-0 Gate Results

Per-wave gate `pytest tests/test_operational_migrations.py tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py -q --tb=short`:

- `tests/test_operational_migrations.py`: **13 passed** (Phase 13 wf_* migration constraints, forward-only idempotence, FK RESTRICT, immutability triggers, exactly-once UNIQUE).
- `tests/backtest/test_walkforward.py`: 8 passed, 3 failed, 2 errors — the **expected RED scaffold**: geometry tests fail `ModuleNotFoundError: app.backtest.walkforward` (13-01); repository round-trip tests pass; the `run_walk_forward` integration tests error on the missing module (13-01).
- `tests/backtest/test_ensemble.py`: 2 passed (wf_ensembles repo round-trip), 2 failed — `ModuleNotFoundError: app.backtest.ensemble` (13-04).
- RED scaffold verification command (plan-listed): `pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py tests/backtest/test_optimizer_run.py -q` → 11 failed / 15 passed / 2 errors — all failures are the intended missing-module/class RED cases for 13-01/13-03/13-04.

Existing-suite regression: `tests/research tests/portfolio tests/forecast tests/advanced tests/shadow` → **632 passed, 1 skipped**; `tests/backtest` (minus RED scaffolds) → **61 passed**; migration suite 13/13.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] create_wf_plan JSON-serialization of date objects**
- **Found during:** Task 4 (repository round-trip tests)
- **Issue:** `_json(list(plan.trading_dates))` raised `ValueError: trading dates must be JSON serializable` for `date` objects (the `_FakePlan` fixture used real `date` objects, and 13-01's `WalkForwardPlan.trading_dates` is `tuple[date, ...]`).
- **Fix:** normalize every element through `_as_iso(day)` in `create_wf_plan` (and already via `_as_iso` for all fold boundary fields).
- **Files modified:** `backend/app/research/repository.py`
- **Commit:** 2f3daad

**2. [Rule 1 - Bug] oos_excluded CHECK test targeted a valid value**
- **Found during:** Task 2 migration test authoring
- **Issue:** the first draft mutated `1, '2026` → `0, '2026` which is still a valid `oos_excluded` value (0/1 both allowed by the CHECK) — the test passed `0` and expected a raise.
- **Fix:** mutate to the out-of-enum value `2` so the CHECK actually fires.
- **Files modified:** `backend/tests/test_operational_migrations.py`
- **Commit:** ce164b1

**3. [Rule 1 - Bug] `wf_fixture_plan` fixture broke collection for the fingerprint-drift test**
- **Found during:** Task 4
- **Issue:** the `_FakePlan`/`_FakeFold` duck-typed plan initially lived only in `test_ensemble.py`; `test_walkforward.py` imported `FIXTURE_SYMBOLS` from `conftest`, which under `--import-mode=importlib` fails (`ModuleNotFoundError: conftest`). Also `test_membership_fingerprint_changes_when_membership_changes` reused the same params for two runs, which collides on the exactly-once UNIQUE key.
- **Fix:** define local `_FakePlan`/`_FakeFold` in `test_walkforward.py`; use the conftest `make_stub_resolver`/`make_stub_chain` factory fixtures; give the second run distinct `params={"p": 2}`.
- **Files modified:** `backend/tests/backtest/test_walkforward.py`, `backend/tests/backtest/conftest.py`
- **Commit:** 2f3daad, 56987db

## Auth Gates

None.

## Known Stubs

None — the RED scaffold tests are intentional RED (missing modules/classes land in 13-01/13-03/13-04), not stubs in delivered code.

## Threat Flags

None — no new network endpoints, auth paths, or execution routes. All five tables are append-only research records with immutability triggers and CHECK constraints on every trust-boundary field (params_sha256, membership_fingerprint, oos_excluded, passed_gate).

## Self-Check: PASSED

- `backend/app/operational/migrations.py` — appended script with `CREATE TABLE wf_plans` found; migration suite 13/13 green.
- `backend/app/research/repository.py` — `create_wf_plan`/`record_wf_fold`/`record_wf_search`/`record_validated_strategy`/`record_wf_ensemble` + read paths verified by round-trip smoke test and pytest.
- `backend/tests/backtest/conftest.py`, `test_walkforward.py`, `test_ensemble.py`, `test_optimizer_run.py`, `test_operational_migrations.py` — all present, ruff-clean.
- Commits ce164b1, ab5fe58, 2f3daad, 56987db exist on `gsd/v1.2-end-to-end-factor-portfolio-pipeline-in-progress`.
