---
phase: 11-portfolio-construction-optimization
plan: 11-05
subsystem: portfolio-optimization, database, research-catalog
tags: [snapshot-binding, checksum, catalog, composite, input-snapshot-sha256, fail-closed, append-only, pydantic]

# Dependency graph
requires:
  - phase: 11-portfolio-construction-optimization
    provides: 11-01 tracer — run_optimization orchestrator + PortfolioRepository/PortfolioArtifactService immutable run + artifact seams; 11-03/11-04 — hrp_portfolio objective + solver_path/w_prev/max-Sharpe breadth; 10-01 — build_composite + catalog.get_composite_model (CompositeModelRecord with latest_composite = {id, output_sha256, artifact_relative_path, input_snapshot_sha256, created_at}) + factor_model_composites append-only rows
provides:
  - portfolio/snapshot.py — load_composite_snapshot(catalog, model_id, as_of, data_dir[, universe_resolver]) → checksum-verified artifact load (sha256(bytes) == output_sha256, frozen_panel fail-closed pattern) → as_of cross-section [symbol, date, composite] → {model_id, composite_snapshot_id, input_snapshot_sha256, as_of, symbols, mu}; SnapshotBindingError for model-missing / no-snapshot / absent-tampered-mismatch / lookahead / empty-cross-section; optional universe_resolver PIT inner-join (post-seam)
  - portfolio/optimizer.py — run_optimization fail-closed wrapper: SnapshotBindingError / ValueError / RuntimeError / cp.error.SolverError recorded as failed runs with failure_reason (PFOL-04), never a silent abort; _record_failed_run FK-degrades model_id→None + expected_return_method→"none" when the model does not exist; catalog+data_dir seam resolves expected returns via load_composite_snapshot (snapshot symbols define the run universe; snapshot mu feeds max_sharpe)
  - portfolio/repository.py — list_optimization_runs limit cap (default 200, positive-int fail-closed) for the Phase 15 API
  - tests/portfolio/test_snapshot_binding.py — 8 green cases (checksum cross-section, model-missing, no-snapshot, tampered, absent, lookahead, run-level failed-record, audit-root equality)
  - tests/research/test_models.py — cross-module composite-snapshot consumption (input_snapshot_sha256 == factor_model_composites row; mu cross-section == artifact bytes)
affects: [11-06, Phase 12 risk suite, Phase 14 RebalancePlan, Phase 15 API]

# Actuals (#2632)
actuals:
  tokens: 14000
  tasks: 5
  commits: 6

# Tech tracking
tech-stack:
  added: []
  patterns: [composite consumed BY SNAPSHOT — catalog.get_composite_model → checksum-verified artifact bytes → as_of cross-section, never a live module hand-off (pitfall 5), fail-closed wrapper records every failure as an auditable failed run with failure_reason (PFOL-04), lookahead guard keyed on artifact data coverage (panel window), list_optimization_runs limit cap for the Phase 15 API]

key-files:
  created:
    - backend/app/portfolio/snapshot.py
    - backend/tests/portfolio/test_snapshot_binding.py
  modified:
    - backend/app/portfolio/optimizer.py
    - backend/app/portfolio/repository.py
    - backend/tests/portfolio/test_optimizer.py
    - backend/tests/research/test_models.py

key-decisions:
  - "Expected returns are consumed by snapshot: catalog.get_composite_model → checksum-verified artifact load (sha256(bytes) == output_sha256, frozen_panel fail-closed pattern) → as_of cross-section [symbol, date, composite] → mu; run row's input_snapshot_sha256 == composite's input_snapshot_sha256 (audit root, cross-module integrity)."
  - "run_optimization wraps the ENTIRE run (snapshot load → covariance → solve → persist) in a fail-closed handler: SnapshotBindingError / ValueError / RuntimeError / cp.error.SolverError are recorded as failed runs with failure_reason (PFOL-04) — never a silent abort. Request-validation errors that prevent a meaningful run row (Pydantic ValidationError) still propagate."
  - "Model-not-found (snapshot binding 'model not found') FK-degrades the failed-run row: model_id→None and expected_return_method→'none' so the append-only INSERT satisfies the factor_model_models FK; failure_reason retains the full fact (that run never consumed any composite snapshot)."
  - "The production catalog seam (catalog + data_dir) takes precedence over the tracer's pre-resolved snapshot dict; when it resolves, the snapshot's symbols define the run universe and its mu feeds max_sharpe expected returns (symbols/mu length mismatch fails closed)."
  - "The lookahead guard is keyed on artifact DATA COVERAGE (earliest [symbol,date,composite] date), not created_at — a backtest composite's created_at is later than its data dates, so RESEARCH.md's 'as_of precedes ... the panel window' clause is the operative one."
  - "11-04 request-validation ValueErrors (render_baselines, missing prior run, missing mu) are now failed-run records, not propagated exceptions — matching the 11-05/11-06 fail-closed contract; the three 11-04 tests were updated accordingly."

patterns-established:
  - "Snapshot binding fail-closed contract: 5 named SnapshotBindingError paths (model not found / no composite snapshot recorded / composite artifact checksum mismatch / as_of precedes composite snapshot coverage / no composite cross-section at as_of), all recorded as failed runs through run_optimization."
  - "list_optimization_runs breadth: objective/as_of equality filters + limit cap (default 200, positive-int validation) for the Phase 15 API; ORDER BY created_at, id preserved."
  - "Cross-module integrity lock: tests/research/test_models.py proves the optimizer consumes exactly the artifact bytes identified by input_snapshot_sha256."

requirements-completed: [PFOL-04]

coverage:
  - id: D1
    description: "load_composite_snapshot — checksum-verified composite artifact load (sha256(bytes) == output_sha256) → as_of cross-section returns symbols/mu with input_snapshot_sha256 == composite record's; model-missing, no-snapshot, artifact tampered/absent, and lookahead as_of all raise SnapshotBindingError"
    requirement: PFOL-04
    verification:
      - kind: unit
        ref: "tests/portfolio/test_snapshot_binding.py#test_load_composite_snapshot_returns_checksum_verified_cross_section"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_snapshot_binding.py#test_model_missing_fails_closed"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_snapshot_binding.py#test_no_composite_snapshot_fails_closed"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_snapshot_binding.py#test_artifact_tampered_fails_closed"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_snapshot_binding.py#test_artifact_absent_fails_closed"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_snapshot_binding.py#test_lookahead_as_of_fails_closed"
        status: pass
    human_judgment: false
  - id: D2
    description: "run_optimization fail-closed wrapper — a snapshot binding failure is recorded as a failed run with failure_reason (never a silent abort); a successful catalog-seam run records input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256 (audit root)"
    requirement: PFOL-04
    verification:
      - kind: integration
        ref: "tests/portfolio/test_snapshot_binding.py#test_run_optimization_records_failed_run_on_snapshot_binding_failure"
        status: pass
      - kind: integration
        ref: "tests/portfolio/test_snapshot_binding.py#test_run_optimization_input_snapshot_sha256_matches_composite"
        status: pass
    human_judgment: false
  - id: D3
    description: "list_optimization_runs breadth — objective/as_of filters preserved, ORDER BY created_at, id, and a limit cap (default 200, positive-int fail-closed) for the Phase 15 API"
    requirement: PFOL-04
    verification:
      - kind: unit
        ref: "tests/portfolio/test_repository.py#test_list_filters_by_objective_and_as_of"
        status: pass
      - kind: unit
        ref: "tests/portfolio/test_repository.py#test_list_caps_at_limit"
        status: pass
    human_judgment: false
  - id: D4
    description: "Cross-module integrity — composite consumed by snapshot equals artifact bytes verified by output_sha256; run input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256"
    requirement: PFOL-04
    verification:
      - kind: integration
        ref: "tests/research/test_models.py#test_composite_snapshot_consumption_matches_artifact_bytes"
        status: pass
    human_judgment: false

# Metrics
duration: 55min
completed: 2026-08-01
status: complete
---

# Phase 11 Plan 11-05: Snapshot Binding + Run-Record Breadth Summary

**Composite expected returns consumed BY SNAPSHOT through the production catalog seam — `catalog.get_composite_model` → checksum-verified artifact bytes (`sha256(bytes) == output_sha256`) → `as_of` cross-section → `mu`, with every fail-closed path (model missing, no snapshot, artifact absent/tampered, lookahead) recorded as an auditable `failed` run carrying `failure_reason`, `run_optimization` wrapping the ENTIRE run, `list_optimization_runs` limit-capped for the Phase 15 API, and the cross-module audit root `run.input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256` locked by tests**

## Performance

- **Duration:** 55 min
- **Started:** 2026-08-01T18:03:00Z
- **Completed:** 2026-08-01T18:58:01Z
- **Tasks:** 5
- **Files modified:** 6

## Accomplishments

- **`load_composite_snapshot` — production snapshot binding** — new `portfolio/snapshot.py` implements the 5-step contract from RESEARCH.md `## Input Snapshot Binding`: `catalog.get_composite_model(model_id)` → `record.latest_composite` (missing → `SnapshotBindingError("no composite snapshot recorded")`) → read `data_dir/artifact_relative_path` and verify `sha256(bytes) == output_sha256` (frozen_panel fail-closed pattern; absent/tampered/mismatch → `SnapshotBindingError("composite artifact checksum mismatch")`) → parse `[symbol, date, composite]` rows → `as_of` cross-section as the expected-return vector `mu`. An optional `universe_resolver` PIT inner-join (post-seam, signal_chain parity) filters membership. **`build_composite` never appears in `portfolio/`** (grep gate clean) — the composite is consumed by snapshot, never a live module hand-off (pitfall 5).
- **`run_optimization` fail-closed wrapper + catalog seam** — the orchestrator now wraps the ENTIRE run (snapshot load → covariance+PSD → solve → persist) and records any `SnapshotBindingError` / `ValueError` / `RuntimeError` / `cp.error.SolverError` as a `failed` run with `failure_reason` (PFOL-04) — never a silent abort. When `catalog` + `data_dir` are supplied, expected returns resolve through the real seam (snapshot symbols define the run universe; snapshot `mu` feeds `max_sharpe`), replacing the tracer's fixture bootstrap. Model-not-found FK-degrades the failed-run row (`model_id→None`, `expected_return_method→"none"`) so the append-only INSERT still lands while `failure_reason` retains the full fact.
- **`list_optimization_runs` breadth** — the Phase 15 API surface: optional `objective`/`as_of` equality filters, `ORDER BY created_at, id`, and a `limit` cap (default 200) with positive-int fail-closed validation.
- **Fail-closed snapshot-binding contract locked by 8 new tests** — checksum-verified cross-section (symbols/mu + audit-root sha), model-missing, no-snapshot, artifact tampered, artifact absent, lookahead as_of (data-coverage keyed), run-level failed-record, and audit-root equality on a successful run.
- **Cross-module integrity in `test_models.py`** — a real `build_composite` records the frozen artifact; `load_composite_snapshot` (portfolio) consumes exactly those bytes: `snapshot["input_snapshot_sha256"] == factor_model_composites.input_snapshot_sha256` and the as_of mu cross-section equals the artifact's `[symbol, date, composite]` values.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create `portfolio/snapshot.py` — checksum-verified composite snapshot binding** - `7ab5cf5` (feat)
2. **Task 2: Wire the snapshot into `run_optimization` + record failed runs fail-closed** - `4f205e2` (feat)
3. **Task 3: `list_optimization_runs` breadth (limit cap)** - `7cb099b` (feat)
4. **Task 4: Turn `test_snapshot_binding.py` green — fail-closed binding** - `5a8b189` (test)
5. **Task 5: Cross-module consumption in `test_models.py`** - `b5e94e2` (test)
6. **Grep-gate hygiene: snapshot docstring reworded** - `5c5b870` (feat)

**Plan metadata:** pending after 11-06 (docs: complete plan)

## Files Created/Modified

- `backend/app/portfolio/snapshot.py` - `load_composite_snapshot` + `SnapshotBindingError`; checksum-verified artifact read → as_of cross-section; optional PIT universe filter; 5 named fail-closed paths
- `backend/app/portfolio/optimizer.py` - fail-closed wrapper (`_run_optimization_impl` + `_record_failed_run`); catalog+data_dir snapshot seam (symbols/mu wiring); `SnapshotBindingError` import
- `backend/app/portfolio/repository.py` - `list_optimization_runs(limit=200)` + positive-int validation
- `backend/tests/portfolio/test_snapshot_binding.py` - 8 green cases locking the fail-closed binding contract
- `backend/tests/portfolio/test_optimizer.py` - 3 tests updated: request-validation ValueErrors (render_baselines / missing prior run / missing mu) now assert failed-run records
- `backend/tests/research/test_models.py` - cross-module composite-snapshot consumption test

## Decisions Made

- **Snapshot consumption is the audit root** — `run.input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256` for the recorded `composite_snapshot_id`; the artifact bytes are verified against `output_sha256` on every load (frozen_panel pattern), so a tampered/absent artifact fails the run closed.
- **Fail-closed wrapper records, never aborts** — the orchestrator catches `SnapshotBindingError`/`ValueError`/`RuntimeError`/`cp.error.SolverError` and persists a `failed` run with `failure_reason` (PFOL-04); request-validation errors that prevent a meaningful run row (Pydantic `ValidationError`) still propagate.
- **Model-not-found FK degradation** — a snapshot-binding failure for a model that does not exist in `factor_model_models` degrades the failed-run row (`model_id=None`, `expected_return_method="none"`) so the append-only INSERT satisfies the FK; `failure_reason` keeps the complete fact.
- **Production seam precedence** — `catalog`+`data_dir` take precedence over the pre-resolved `snapshot` dict; the snapshot's `symbols` define the run universe and its `mu` feeds `max_sharpe` (length mismatch fails closed).
- **Lookahead guard on data coverage** — the guard compares `as_of` against the artifact's earliest `[symbol, date, composite]` date (the panel window), not `created_at`, because a backtest composite's `created_at` is later than its data dates (RESEARCH.md "as_of precedes ... the panel window" clause).
- **11-04 test contract update** — the three request-validation ValueErrors that 11-04 asserted as propagated exceptions are now failed-run records (the 11-05/11-06 fail-closed contract); the tests were updated and re-locked.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 11-04 tests asserted ValueError propagation; fail-closed wrapper records failed runs**
- **Found during:** Task 2 (fail-closed wrapper)
- **Issue:** The plan's fail-closed wrapper requirement (every fail-closed path recorded as a failed run with reason) directly conflicts with three 11-04 tests that asserted `pytest.raises(ValueError)` on `run_optimization` — `test_run_id_reference_missing_prior_run_fails_closed`, `test_max_sharpe_requires_baselines`, `test_max_sharpe_requires_mu`. With the wrapper in place, those ValueErrors are recorded as `failed` runs and no longer propagate.
- **Fix:** Updated the three tests to assert the failed-run record (`problem_status == "failed"`, `failure_reason` contains the expected message). This is the correct contract per 11-05 task 2 and 11-06 task 1 (industry-cap gate depends on the same recording behavior).
- **Files modified:** backend/tests/portfolio/test_optimizer.py
- **Verification:** `pytest tests/portfolio/test_optimizer.py -q --tb=short` → 18 passed; full `tests/portfolio/` → 50 passed at commit time.
- **Committed in:** `4f205e2` (Task 2 commit)

**2. [Rule 1 - Bug] Model-not-found failed-run INSERT violated the factor_model_models FK**
- **Found during:** Task 2 (snapshot-binding failure through the wrapper)
- **Issue:** A snapshot binding failure "model not found" recorded a failed run with the requested `model_id`, but `portfolio_optimization_runs.model_id` has `REFERENCES factor_model_models(model_id) ON DELETE RESTRICT` — the INSERT raised `sqlite3.IntegrityError` and the failed run was lost (silent abort, violating PFOL-04).
- **Fix:** `_record_failed_run` FK-degrades: on `sqlite3.IntegrityError` the row is re-inserted with `model_id=None` and `expected_return_method="none"`; `failure_reason` retains the full fact. Verified the failed run is retrievable via `get_optimization_run`.
- **Files modified:** backend/app/portfolio/optimizer.py
- **Verification:** manual smoke — model-not-found through the catalog seam records a retrievable `failed` run; `pytest tests/portfolio -q --tb=short` green.
- **Committed in:** `4f205e2` (Task 2 commit)

**3. [Rule 1 - Bug] Cross-module test used the wrong as_of (composite frame drops the panel last day)**
- **Found during:** Task 5 (cross-module test_models extension)
- **Issue:** The composite frame only contains `2024-01-02` (the panel's last day is dropped because `forward_return` needs a next-day label); my test passed `as_of=date(2024,1,3)` and hit `SnapshotBindingError("no composite cross-section at as_of")`.
- **Fix:** Used `as_of=date(2024,1,2)` and matched the artifact bytes at that date.
- **Files modified:** backend/tests/research/test_models.py
- **Verification:** `pytest tests/research/test_models.py -q --tb=short` → 10 passed.
- **Committed in:** `b5e94e2` (Task 5 commit)

**4. [Rule 2 - Missing Critical] Grep gate: snapshot.py docstring named `build_composite`**
- **Found during:** plan verification
- **Issue:** The plan's negative grep gate (`build_composite` appears nowhere in `backend/app/portfolio/`) was self-invalidated by the docstring that explained why it never calls `build_composite`.
- **Fix:** Reworded the docstring to state the contract without naming the function (negative-grep hygiene per the phase grep-gate notes).
- **Files modified:** backend/app/portfolio/snapshot.py
- **Verification:** `grep -rn "build_composite" backend/app/portfolio/ --include="*.py"` → no matches; snapshot binding tests still 8 passed.
- **Committed in:** `5c5b870`

---

**Total deviations:** 4 auto-fixed (3 bugs, 1 missing critical)
**Impact on plan:** All auto-fixes necessary for the plan's own success criteria — PFOL-04 failed-run retention (FK degradation), the fail-closed contract coherence across 11-04/11-05/11-06, and the negative-grep gate hygiene. No scope creep.

## Issues Encountered

- **Parallel-agent coordination (11-06 prep)** — `Exec1106` (11-06) had uncommitted edits to `optimizer.py` (industry_cap lines), `risk.py`, `artifacts.py`, `schemas.py`, `conftest.py`, `test_optimizer.py`, `test_risk.py` when 11-05 started. We coordinated via IRC: Exec1106 reverted its `optimizer.py` hunks so my 11-05 commits stayed clean, then re-applied its changes after my task-2 commit. Its `conftest.py` half-finished edit briefly broke `test_pipeline.py` (NameError `output_sha256`) — resolved by Exec1106 finishing the fixture (writes a real signals.json artifact with `output_sha256 = sha256(bytes)`). Final tree state: my 11-05 commits + Exec1106's uncommitted 11-06 WIP (all green; 63 passed in `tests/portfolio`).
- **Lookahead semantics** — the artifact `created_at` (write time) is not a sound lookahead key for backtest composites; the guard uses the earliest data date instead (see Decision: lookahead on data coverage).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **11-06 (constraint hardening)** — the fail-closed wrapper is the exact seam its industry-cap gate needs: `assert_industry_cap_unavailable` raising `ValueError("industry mapping unavailable")` will be recorded as a failed run with that reason (Exec1106's WIP already wires it). The snapshot-seam `symbols` define the run universe, so 11-06's covariance artifact breadth lands on the same path.
- **Phase 12 risk suite** — `load_composite_snapshot` + the checksum-verified artifact discipline are the model for consuming any frozen input by snapshot.
- **Phase 14 RebalancePlan** — turnover reference (equal_weight | run_id) already consumes the repository/artifact seams; snapshot-bound expected returns flow through unchanged.
- **Phase 15 API** — `list_optimization_runs(objective, as_of, limit)` is the list endpoint surface.
- **Blockers/concerns:** none. Per-plan gate `pytest tests/portfolio/test_pipeline.py tests/research/test_models.py -q --tb=short` → 11 passed; plan verification `pytest tests/portfolio/test_snapshot_binding.py tests/portfolio/test_repository.py tests/research/test_models.py -q --tb=short` → 24 passed. Grep gate: `build_composite` absent from `backend/app/portfolio/`. Full-suite pytest deliberately NOT run (phase gate after all plans, per batch constraints).

## Self-Check: PASSED

All 6 files present on disk; all 6 plan commits present in git history (`7ab5cf5`, `4f205e2`, `7cb099b`, `5a8b189`, `b5e94e2`, `5c5b870`). Per-plan gate re-run after the final commit: `pytest tests/portfolio/test_pipeline.py tests/research/test_models.py -q --tb=short` → 11 passed; `pytest tests/portfolio/test_snapshot_binding.py tests/portfolio/test_repository.py tests/research/test_models.py -q --tb=short` → 24 passed. Grep gate: `grep -rn "build_composite" backend/app/portfolio/ --include="*.py"` → no matches.
