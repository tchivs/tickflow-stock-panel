---
phase: 10-factor-library-multi-factor-model
plan: 10-02
subsystem: database, testing, dependencies
tags: [sqlite, migrations, scipy, uv, pytest, polars, append-only, research]

# Dependency graph
requires:
  - phase: 02-research-catalog
    provides: research_factor_definitions/revisions/experiments tables, ResearchRepository append-only conventions
provides:
  - 4 append-only tables: factor_universe_membership, factor_admission_verdicts, factor_model_models, factor_model_composites
  - scipy>=1.17.1,<1.18 base dependency + locked uv.lock + empty-.venv Wave 0 gate proof
  - 4 RED test scaffolds + shared conftest fixtures consumed by 10-01/10-04
  - ResearchRepository insert/query methods for membership, verdicts, models, composites
affects: [10-01, 10-04, 10-05, 10-06, Phase 11 HRP, Phase 13 walk-forward]

# Actuals (#2632)
actuals:
  tokens: 15000
  tasks: 5
  commits: 4

# Tech tracking
tech-stack:
  added: [scipy>=1.17.1,<1.18 (base deps)]
  patterns: [append-only SQLite tables with immutability triggers, UNIQUE+FK+CHECK guards, empty-.venv dependency gate, RED test scaffolding]

key-files:
  created:
    - backend/tests/research/conftest.py
    - backend/tests/research/test_signal_chain.py
    - backend/tests/research/test_admission.py
    - backend/tests/research/test_models.py
    - backend/tests/research/test_universe_resolution.py
  modified:
    - backend/app/operational/migrations.py
    - backend/app/research/repository.py
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/tests/test_operational_migrations.py

key-decisions:
  - "Land the 4 append-only tables exactly per the RESEARCH.md schema (option-a) — UNIQUE/CHECK/FK guards plus immutability triggers so the audit contract is enforced at the SQL layer."
  - "Promote scipy>=1.17.1,<1.18 to base [project] dependencies (option-a) — <1.18 upper bound protects the Python>=3.11 floor; scikit-learn stays shadow lazy-import."
  - "Fixed the pre-existing r43 migration test to locate its target script by index instead of assuming it is the last MIGRATIONS entry."

patterns-established:
  - "Append-only research tables: INSERT-only repository methods, UNIQUE+FK+CHECK guards in the migration, immutability triggers on UPDATE/DELETE."
  - "RED test scaffolds: new Phase 10 test files import their modules via fixtures so they fail on the missing module until 10-01/10-04 land."
  - "Shared conftest: StubBacktestEngine + StubUniverseResolver + fixture panel/membership reused across the four new test files."

requirements-completed: [FACT-01, FACT-02, FACT-03, FACT-05, FACT-06]

coverage:
  - id: D1
    description: "4 append-only tables migrate atomically with CHECK/UNIQUE/FK guards and immutability triggers"
    requirement: FACT-01
    verification:
      - kind: unit
        ref: "tests/test_operational_migrations.py#test_phase10_append_only_tables_migrate_with_constraints_and_idempotence"
        status: pass
    human_judgment: false
  - id: D2
    description: "scipy>=1.17.1,<1.18 in base deps, locked, verified in an empty .venv with no dependency conflicts and no sklearn module-top import"
    requirement: FACT-06
    verification:
      - kind: unit
        ref: "uv lock && uv venv --clear && uv sync --extra shadow && uv pip check && python -c 'import scipy' (1.17.1)"
        status: pass
    human_judgment: false
  - id: D3
    description: "4 new test files scaffolded RED with shared fixtures in conftest.py — the exact tests 10-01/10-04 turn green"
    requirement: FACT-06
    verification:
      - kind: unit
        ref: "tests/research/test_signal_chain.py, test_admission.py, test_models.py, test_universe_resolution.py (19 collection errors on missing modules)"
        status: pass
    human_judgment: false
  - id: D4
    description: "ResearchRepository append-only methods for all 4 tables with canonical JSON serialization and transactionality"
    requirement: FACT-05
    verification:
      - kind: unit
        ref: "repository smoke: insert/resolve membership (delist closure), verdict UNIQUE conflict, model/composite round-trip"
        status: pass
    human_judgment: false

# Metrics
duration: 60min
completed: 2026-08-01
status: complete
---

# Phase 10 Plan 2: Wave 0 — Migrations, Dependencies, Test Scaffolding Summary

**4 append-only research tables migrated with UNIQUE/FK/CHECK guards and immutability triggers, scipy>=1.17.1,<1.18 promoted to base deps and verified in a fresh empty `.venv`, 4 RED test scaffolds plus shared conftest fixtures, and ResearchRepository append-only methods for membership/verdicts/models/composites**

## Performance

- **Duration:** 60 min
- **Started:** 2026-08-01T07:40:00Z
- **Completed:** 2026-08-01T08:05:00Z
- **Tasks:** 5
- **Files modified:** 9

## Accomplishments

- **4-table migration landed** — `factor_universe_membership`, `factor_admission_verdicts`, `factor_model_models`, `factor_model_composites` appended as ONE new script to `MIGRATIONS` per the RESEARCH.md schema (option-a), with UNIQUE/CHECK/FK guards and immutability triggers on UPDATE/DELETE. `PRAGMA user_version` advances atomically with the schema.
- **scipy promoted and locked** — `scipy>=1.17.1,<1.18` added to base `[project] dependencies`; `uv lock` regenerated (stable — 1.17.1 was already the transitive pin). Empty-`.venv` Wave 0 gate passed: `uv venv --clear` + `uv sync --extra shadow` + `uv pip check` (72 packages compatible) + `scipy.__version__ == '1.17.1'` + lazy-import audit (`sklearn`/`scikit_learn` absent from `sys.modules` after importing the research package surface) + smoke (`migrate` + `create_factor` + all 4 tables present).
- **4 RED test scaffolds + shared fixtures** — `test_signal_chain.py` (binding, per-date membership, cross-consumer equality, PanelCache dedup, `forward_return_horizon=None`), `test_admission.py` (policy constants, gate-result verdicts, rejection trail, temporal determinism, append-only single-row), `test_models.py` (equal/IC weights, deterministic sha256, immutable output), `test_universe_resolution.py` (listed-after-start, delist closure, fingerprint stability). Shared `conftest.py` provides `StubBacktestEngine`, `StubUniverseResolver`, fixture panel/membership. Scaffolds are provably RED (19 collection errors on the missing modules 10-01/10-04 create).
- **Repository append-only methods** — `insert_universe_membership`/`resolve_universe_memberships` (latest event per symbol with `effective_date <= as_of`; delist = new row), `insert_admission_verdict`/`get_admission_verdict` (UNIQUE conflict surfaced as `ValueError`, sha256 length validation), `insert_model_definition`/`get_model_definition`, `insert_model_composite`/`list_model_composites`. Canonical `_json` serialization, transactional inserts, FK/CHECK violations wrapped.
- **Migration tests extended** — new `test_phase10_append_only_tables_migrate_with_constraints_and_idempotence` proves table existence, UNIQUE/CHECK/FK/sha256-length constraints, immutability triggers, and forward-only idempotence.

## Task Commits

Each task was committed atomically:

1. **Task: 4-table migration + migration tests** - `9ee9901` (feat)
2. **Task: scipy base promotion + lock** - `0ac7cd6` (feat)
3. **Task: RED test scaffolds + conftest fixtures** - `02098a4` (test)
4. **Task: repository append-only methods** - `bd2c5ec` (feat)

## Files Created/Modified

- `backend/app/operational/migrations.py` - One new migration script creating the 4 append-only tables with UNIQUE/CHECK/FK guards and immutability triggers
- `backend/app/research/repository.py` - `insert_universe_membership`, `resolve_universe_memberships`, `insert_admission_verdict`, `get_admission_verdict`, `insert_model_definition`, `get_model_definition`, `insert_model_composite`, `list_model_composites`
- `backend/pyproject.toml` - `scipy>=1.17.1,<1.18` in base `[project] dependencies`
- `backend/uv.lock` - regenerated; scipy declared as a direct base dependency
- `backend/tests/test_operational_migrations.py` - Phase 10 constraint test + fixed the r43 test to slice by index
- `backend/tests/research/conftest.py` - Shared `StubBacktestEngine`, `StubUniverseResolver`, fixture panel/membership
- `backend/tests/research/test_signal_chain.py` - RED scaffold (FACT-06 contracts)
- `backend/tests/research/test_admission.py` - RED scaffold (FACT-01 contracts)
- `backend/tests/research/test_models.py` - RED scaffold (FACT-03 contracts)
- `backend/tests/research/test_universe_resolution.py` - RED scaffold (PIT contract)

## Decisions Made

- **Option-a for both one-way doors (ALREADY APPROVED by user, not re-prompted):** landed the RESEARCH.md table schema exactly, and promoted scipy to base deps with the `<1.18` upper bound protecting the Python≥3.11 floor.
- **Immutability triggers added beyond the plan:** the plan specified CHECK/UNIQUE/FK guards; I additionally added `BEFORE UPDATE`/`BEFORE DELETE` triggers on all four tables so the append-only audit contract is enforced at the SQL layer (threat T-10-03/T-10-06 disposition — tamper protection), not just by repository convention.
- **Fixed a pre-existing test bug:** `test_r43_cr03_legacy_unbound_queued_migration_quarantines_before_restart` sliced `planned[:-1]` assuming the retry migration is last; with the new Phase 10 script appended it started failing (Rule 1). Fixed it to locate the `forecast_retry_operations` script by index.
- **Repository FK on verdicts needs a real revision:** smoke tests insert verdicts only after creating a revision through `FactorRegistry` (the FK `ON DELETE RESTRICT` requires the target row).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-existing r43 migration test broke after appending the Phase 10 script**
- **Found during:** Task 1 (4-table migration)
- **Issue:** `test_r43_cr03_legacy_unbound_queued_migration_quarantines_before_restart` monkeypatched `MIGRATIONS` to `planned[:-1]`, assuming the `forecast_retry_operations` migration is the last script. Appending the Phase 10 script made the test run `forecast_retry_operations` during the pre-quarantine setup, so the inserted `queued` job was already quarantined before the assertion — the test failed.
- **Fix:** Locate the `forecast_retry_operations` script by index (`next(i for i, s in enumerate(planned) if "forecast_retry_operations" in s)`) and slice `planned[:retry_index]`, matching the convention used by the other forward-only tests.
- **Files modified:** backend/tests/test_operational_migrations.py
- **Verification:** full migration test file green (8 passed)
- **Committed in:** `9ee9901` (Task 1 commit)

**2. [Rule 2 - Missing Critical] SQL-layer immutability enforcement beyond repository convention**
- **Found during:** Task 1 (4-table migration)
- **Issue:** The plan specified CHECK/UNIQUE/FK guards but no row-level protection; the threat model (T-10-03 tampering, T-10-06 verdict integrity) and the append-only contract benefit from SQL-enforced immutability, not just "INSERT-only repository methods".
- **Fix:** Added `BEFORE UPDATE`/`BEFORE DELETE` triggers on all four tables raising `ABORT` — consistent with the existing `research_strategy_asset_bindings` and forecast/advanced immutable-fact triggers in the same file.
- **Files modified:** backend/app/operational/migrations.py
- **Verification:** migration test asserts UPDATE/DELETE raise `sqlite3.IntegrityError`
- **Committed in:** `9ee9901` (Task 1 commit)

**3. [Rule 3 - Blocking] Empty-.venv gate used a different Python version than the project baseline**
- **Found during:** Task 2 (scipy promotion)
- **Issue:** `uv venv --clear` created a CPython 3.11.2 interpreter while the prior `.venv` was python3.14; the lazy-import audit and test runs needed to re-verify on the reconstructed environment.
- **Fix:** Re-ran the audit and all targeted tests on the fresh 3.11 `.venv`; `uv sync --extra dev` restored pytest. This actually *strengthens* the gate: it proves the cp311 wheel path (Assumption A5) rather than just the host's 3.14.
- **Verification:** `uv pip check` clean, `scipy.__version__ == '1.17.1'`, audit passes, tests green
- **Committed in:** `0ac7cd6` (Task 2 commit) — evidence recorded here

---

**Total deviations:** 3 auto-fixed (1 bug, 1 missing critical, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness and the audit contract. No scope creep; no architectural change.

## Issues Encountered

- **Smoke-test assertion nuance:** `resolve_universe_memberships` returns the latest event per symbol *including delisted rows* (correct — the caller filters `state == 'listed'` for membership). Initial smoke assertions expected delisted symbols to vanish from the result set entirely; corrected the smoke to filter on state. The repository semantics match the RESEARCH.md contract ("latest event with effective_date <= D is 'listed'").
- **`uv venv --clear` replaces the host `.venv`:** the gate is destructive by design (RESEARCH.md mandates a fresh environment). Re-synced `--extra shadow --extra dev` afterwards for the test run.

## User Setup Required

None - no external service configuration required. The scipy/sklearn package legitimacy was already verified in RESEARCH.md (PyPI audit; the npm `SUS` results are documented cross-ecosystem false positives).

## Next Phase Readiness

- **10-01 (tracer) can start immediately:** the migration, repository methods, and RED scaffolds it turns green are all in place; `signal_chain.py`/`admission.py`/`models.py` consumers can rely on the append-only insert methods and the shared conftest fixtures.
- **10-03 (DSL contract)** runs in parallel on disjoint files (`factor_dsl.py`, `test_factor_dsl.py`) — no overlap with 10-02's files.
- **10-04 (PIT resolver)** consumes `insert_universe_membership`/`resolve_universe_memberships` and turns `test_universe_resolution.py` green.
- **Blockers/concerns:** none. The empty-.venv gate confirmed scipy 1.17.1 resolves on CPython 3.11 (Assumption A5 verified).

---
*Phase: 10-factor-library-multi-factor-model*
*Completed: 2026-08-01*

## Self-Check: PASSED

All 10 created/modified files exist on disk and all 4 plan commits are present in git history (`9ee9901`, `0ac7cd6`, `02098a4`, `bd2c5ec`). Wave 0 gates re-verified after the final commit: `tests/test_operational_migrations.py` 8 passed; `uv pip check` clean; `scipy.__version__ == '1.17.1'`.
