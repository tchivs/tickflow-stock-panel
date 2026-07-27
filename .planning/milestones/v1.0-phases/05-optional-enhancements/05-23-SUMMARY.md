---
phase: 05-optional-enhancements
plan: "23"
subsystem: forecast-audit-and-recovery
status: complete
tags: [forecast, parquet, sqlite, keyset-cursor, calibration, sse, concurrency]
requires:
  - phase: 05-optional-enhancements
    plan: "22"
    provides: canonical governed Forecast input, calendar, runner, and immutable commit identities
  - phase: 05-optional-enhancements
    plan: "25"
    provides: atomic forward SQLite migration semantics in the sole operational store
provides:
  - verified distinct-path paging for all 32 complete sampled paths
  - canonical P10/P50/P90 derivation from the committed path tensor
  - durable bounded Forecast maturity cursor and exclusive scanner lease
  - retryable delayed-actual repair and record-scoped public calibration refresh
  - persisted Forecast job transition ledger and resumable bounded SSE
  - preserved fail-closed local-only Forecast supply-chain boundary
affects: [FORE-01, forecast-artifacts, forecast-calibration, forecast-sse, phase-05-verification]
tech-stack:
  added: []
  patterns:
    - checksum-verified Parquet bytes decoded only after root and regular-file validation
    - repository-owned pending keyset page with lease-before-work and cursor-after-work
    - immutable transition versions as the sole SSE resume identity
key-files:
  created:
    - backend/tests/forecast/test_api.py
    - .planning/phases/05-optional-enhancements/05-23-SUMMARY.md
  modified:
    - backend/app/forecast/artifacts.py
    - backend/app/forecast/api.py
    - backend/app/forecast/repository.py
    - backend/app/forecast/calibration.py
    - backend/app/forecast/projections.py
    - backend/app/operational/migrations.py
    - backend/app/optional_modules.py
    - backend/tests/forecast/test_calibration.py
    - backend/tests/test_operational_migrations.py
key-decisions:
  - "The production path reader belongs to the Forecast artifact domain and pages distinct sample identities only after validating the complete 32 × session × feature relation."
  - "Maturity work uses one cursor and lease in operational.db; the cursor advances only after each candidate is considered, while pending missing actuals remain eligible after wraparound."
  - "Record-authorized calibration calls evaluate only that immutable record's eligible horizons; global pending scans remain scheduler-only."
  - "Forecast SSE event IDs are persisted per-job transition versions; bounded in-memory queues are wake transport only and never become progress authority."
  - "The rejected/unprovisioned Kronos supply state remains authoritative; no dependency, checkpoint, catalog, download, or remote identity was added."
patterns-established:
  - "Complete path page: select path indexes, then return every ordered session/feature point for each selected index with path-count totals."
  - "Repairable maturity: append outcome plus calibration only when governed actual evidence exists; temporary absence produces no terminal fact."
requirements-completed: [FORE-01]
coverage:
  - id: D1
    description: "Three pages expose all 32 complete paths exactly once and persisted fixed quantiles derive from those same path bytes."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_api.py -k 'distinct_complete_path_paging or corrupt_path_relation or path_quantile_consistency or quantile_divergence_rejected'"
        status: pass
    human_judgment: false
  - id: D2
    description: "The atomic forward migration owns one durable maturity cursor/lease and bounded scans remain fair, restart-safe, and repairable."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/test_operational_migrations.py -k 'forecast_maturity_cursor_upgrade or maturity_cursor_mid_migration_rollback'"
        status: pass
      - kind: integration
        ref: "backend/tests/forecast/test_calibration.py -k 'durable_cursor or starvation or restart_after_future_window or missing_actual_repair or parallel_cursor'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Public calibration refresh cannot scan or write unrelated records after object authorization."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_api.py#test_record_scoped_calibration_refresh_never_scans_unrelated_forecasts"
        status: pass
    human_judgment: false
  - id: D4
    description: "Forecast SSE resumes from durable transition versions under synchronized principal, job, server, and queue ceilings."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_api.py -k 'persisted_sse_event_id or last_event_id_resume or subscription_limits or slow_consumer_cleanup'"
        status: pass
    human_judgment: false
duration: 22m32s
completed: 2026-07-17
---

# Phase 05 Plan 23: Strict Forecast Paths, Maturity Recovery, and Durable SSE Summary

**Forecast records now expose 32 complete checksum-verified paths with path-derived quantiles, mature fairly through one durable repairable cursor, and stream persisted transition versions under strict synchronized capacity limits.**

## Performance

- **Duration:** 22m 32s
- **Started:** 2026-07-17T12:45:32Z
- **Completed:** 2026-07-17T13:08:04Z
- **Tasks:** 3/3
- **Files modified:** 10 implementation/test files plus this summary

## Accomplishments

- Moved the production path reader from host composition into `app.forecast.artifacts`, where it rejects unsafe paths, symlinks, size/checksum/schema divergence, malformed sample identities, duplicates, incomplete Cartesian relations, out-of-range indexes, non-finite values, and invalid warnings before exposing any point.
- Changed the page unit from raw Parquet rows to distinct sample indexes. Each selected sample returns every committed future-session/feature row in deterministic order, while `total` remains exactly 32 and `has_more` advances by paths.
- Recomputed fixed P10/P50/P90 with deterministic float64 path-axis quantiles and rejected supplied divergence before either immutable artifact commit.
- Added one atomic forward migration in `operational.db` for the Forecast maturity cursor/lease and immutable job-transition ledger; injected mid-migration failure rolls schema and `user_version` back together.
- Replaced oldest-first global materialization with repository-owned pending keyset pages. One scanner lease wins, cursor advancement follows successful consideration, interruption retries the same candidate, and end-of-keyspace wrap prevents starvation.
- Matured real governed `CNA-YYYYMMDD` identities beyond the finite forecast window, kept missing actuals non-terminal and retryable, and appended the canonical outcome/calibration after later repair.
- Replaced public record refresh's global scanner call with evaluation of only the already-authorized record's eligible horizons.
- Persisted every Forecast job transition version transactionally, resumed only events after authorized `Last-Event-ID`, rejected malformed/future identities, eliminated duplicate terminal events, and bounded subscriptions and wake queues under a synchronized registry.

## Task Commits

TDD gates and follow-up correctness commits were kept atomic with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: Complete path paging and quantiles | `1e0243f` | Failed on missing artifact-domain `ForecastPathReader` |
| GREEN | Task 1: Complete path paging and quantiles | `0203427` | Six focused path/quantile contracts passed |
| RED | Task 2: Durable maturity and scoped repair | `daaf22c` | Failed on absent cursor schema, starvation, and global public scan |
| GREEN | Task 2: Durable maturity and scoped repair | `a49dfb4` | Migration, fairness, repair, parallel lease, and authorization contracts passed |
| RED | Task 3: Persisted bounded SSE | `d139920` | Failed on absent persisted transition query |
| GREEN | Task 3: Persisted bounded SSE | `d3c23cb` | Durable resume and all capacity/cleanup contracts passed |
| Fix | Artifact trust boundary | `bc70104` | Rejected final-entry symlinks and decoded the exact verified bytes |
| Cleanup | Scoped import hygiene | `50168d2` | Changed modules pass scoped Ruff F/E9/I checks |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/forecast/artifacts.py` — artifact-domain path reader, strict complete relation validation, distinct-path pagination, and canonical quantile derivation.
- `backend/app/forecast/api.py` — record-only calibration evaluation, Last-Event-ID validation, persisted transition streaming, and bounded synchronized subscription registry.
- `backend/app/forecast/repository.py` — pending keyset page ownership, durable cursor/lease operations, transition-ledger appends, and resume queries.
- `backend/app/forecast/calibration.py` — leased bounded scans, cursor-after-work semantics, governed post-window maturity, and retryable missing actuals.
- `backend/app/forecast/projections.py` — public path-point projection with path-count totals and `has_more` semantics.
- `backend/app/operational/migrations.py` — atomic forward Forecast maturity cursor/lease and immutable transition ledger schema.
- `backend/app/optional_modules.py` — production composition now imports the artifact-domain path reader.
- `backend/tests/forecast/test_api.py` — path, quantile, record-scope, persisted resume, capacity race, and overflow cleanup contracts.
- `backend/tests/forecast/test_calibration.py` — fair bounded cursor, interruption, restart, post-window sequence, and delayed actual repair contracts.
- `backend/tests/test_operational_migrations.py` — existing-database upgrade, idempotence, rollback, and corrected restart contracts.

## Decisions Made

- The Forecast artifact root and immutable descriptor remain the only file authority. Public DTOs expose checksum metadata and bounded values, never managed local paths.
- Features are ordered deterministically from the verified relation, while sessions retain the immutable record's frozen order and samples retain canonical indexes 0–31.
- A temporarily unavailable actual is a pending observation, not an `unevaluable` terminal fact. Explicit governed finality remains the only permissible future terminal missing-data rule.
- The maturity cursor shares `operational.db` and is independent from the existing `forecast-inference` lease. No second database, broker, queue service, or scheduler authority was introduced.
- In-memory SSE queues only wake readers; reconnect truth comes from immutable transition rows joined back to the already-authorized job.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Repaired the ignored isolated pytest launcher**
- **Found during:** Task 1 RED verification.
- **Issue:** `backend/.venv/bin/pytest` pointed to `/root/source/AthenaQuant`, so the first run imported the primary checkout rather than this isolated executor's source.
- **Fix:** Repointed only the ignored local launcher to this isolated interpreter and reran every literal plan command.
- **Files modified:** `backend/.venv/bin/pytest` (ignored environment file; not committed)
- **Verification:** Failure and subsequent passing traces resolved under `/root/.omp/wt/tc776ab761/m/backend`.
- **Committed in:** Not applicable — ignored execution environment only.

**2. [Rule 1 - Bug] Closed final-entry symlink and verified-byte replacement races**
- **Found during:** Final threat-boundary review after all three tasks were green.
- **Issue:** Resolving a path before calling `is_symlink()` erased evidence that the descriptor's final entry was itself a symlink, and decoding by pathname reread bytes after checksum verification.
- **Fix:** Reject the unresolved final entry when it is a symlink and decode the exact in-memory checksum-verified payload bytes.
- **Files modified:** `backend/app/forecast/artifacts.py`, `backend/tests/forecast/test_api.py`
- **Verification:** The corrupt path selector now includes and passes a symlink rejection case; all 13 focused API/artifact tests pass.
- **Committed in:** `bc70104`

---

**Total deviations:** 2 auto-fixed (1 blocking environment issue, 1 artifact-boundary bug).
**Impact on plan:** Both fixes were necessary to exercise the isolated implementation and fully satisfy the planned fail-closed artifact boundary; no product scope or supply identity changed.

## Issues Encountered

- The first record-scope fixture attempted to instantiate a `Protocol`; replacing it with a concrete allowlist scope made the test exercise the intended public route rather than fail in fixture construction.
- The prior restart test expected canonical terminal horizons to be reread. The pending-only repository contract correctly excludes them, so the assertion was updated to prove they are skipped while later pending horizons continue.
- The production-host smoke test emitted three pre-existing Polars deprecation/sortedness warnings; the approved local request completed and remained independent.

## Verification

```text
cd backend && uv run pytest tests/forecast/test_api.py -k "distinct_complete_path_paging or corrupt_path_relation or path_quantile_consistency or quantile_divergence_rejected or persisted_sse_event_id or last_event_id_resume or subscription_limits or slow_consumer_cleanup or record_scoped_calibration" -x
Result: PASS — 13 passed.

cd backend && uv run pytest tests/test_operational_migrations.py -k "forecast_maturity_cursor_upgrade or maturity_cursor_mid_migration_rollback" -x
Result: PASS — 2 passed, 2 deselected.

cd backend && uv run pytest tests/forecast/test_calibration.py -k "durable_cursor or starvation or restart_after_future_window or missing_actual_repair or parallel_cursor" -x
Result: PASS — 6 passed, 13 deselected.

cd backend && uv run pytest tests/forecast/test_api.py -x
Result: PASS — 12 passed before the final symlink case; final plan selector passed all 13 current cases.

cd backend && uv run pytest tests/forecast/test_runner.py -x
Result: PASS — 29 passed.

cd backend && uv run pytest tests/forecast/test_calibration.py -x
Result: PASS — 19 passed.

cd backend && uv run pytest tests/test_phase5_optional_host.py::test_production_forecast_factory_completes_approved_request_and_stays_independent -x
Result: PASS — 1 passed, 3 pre-existing Polars warnings.

cd backend && uv run ruff check --select F,E9,I [all scoped implementation/test files]
Result: PASS.
```

## Acceptance Criteria

- **PASS — exact path semantics:** Three pages cover all 32 sample indexes once; every selected path contains its complete ordered session/feature relation and totals count paths, not rows.
- **PASS — quantile consistency:** Immutable P10/P50/P90 bytes derive from all 32 validated paths on axis 0; divergent supplied quantiles fail before artifact creation.
- **PASS — atomic durable schema:** Existing databases upgrade to one maturity cursor/lease and transition ledger; injected failure leaves neither schema nor version residue and corrected restart succeeds.
- **PASS — fair bounded maturity:** Pending keyset pages advance across terminal, not-mature, and processed positions; one parallel lease wins and interruption cannot skip or duplicate facts.
- **PASS — repairable delayed actual:** Missing actual evidence appends no terminal outcome/calibration and later governed evidence appends exactly one canonical pair.
- **PASS — record authority:** Public refresh evaluates only the authorized record's 5/20/60 horizons within its immutable bound and never invokes global scanning.
- **PASS — persisted bounded SSE:** Resume emits only durable versions after `Last-Event-ID`, invalid/future IDs fail closed, terminal events do not duplicate, and all subscription/queue ceilings release atomically.
- **PASS — supply-chain seal:** No catalog, checkpoint, dependency, lock, provisioner, download, remote lookup, or substitute identity was added; the local-only rejection boundary inherited from Plans 05-22/05-25 remains intact.

## Threat Mitigation Evidence

- **T-05-23-01:** Root containment, unresolved symlink rejection, regular-file check, exact size/SHA-256, fixed schema/shape, complete Cartesian identities, finite values, and canonical path-axis quantiles protect stored bytes before public projection.
- **T-05-23-02:** A single durable cursor/lease in the atomic operational migration owns bounded pending selection and monotonic advancement.
- **T-05-23-03:** Temporary actual absence persists no terminal fact; later repair appends immutable attributable actual and calibration evidence atomically.
- **T-05-23-04:** The public route authorizes the record first and calls `evaluate` only for that record; trusted scheduler scanning remains separate.
- **T-05-23-05:** Transition history is durable, Last-Event-ID is validated after authorization, synchronized ceilings bound every subscriber dimension, overflow unregisters immediately, and `finally` cleanup is idempotent.

## TDD Gate Compliance

- Task 1 RED `1e0243f` preceded GREEN `0203427` and proved the artifact-domain reader and path-count contract were absent.
- Task 2 RED `daaf22c` preceded GREEN `a49dfb4` and proved the cursor schema, fair scan, delayed repair, post-window maturity, and record-only API contracts were absent.
- Task 3 RED `d139920` preceded GREEN `d3c23cb` and proved persisted transition resume was absent.
- Follow-up fix `bc70104` closed a threat-boundary bug found after the GREEN gates; cleanup `50168d2` changed no behavior.

## Known Stubs

None. Empty warning strings represent the explicit no-warning value; empty pending/transition result lists represent bounded completed reads. Missing approved Kronos supply remains a deliberate fail-closed deployment state and cannot create records or bypass the rejected supply gate.

## User Setup Required

None. Real Kronos execution remains local-only and unavailable unless independently approved artifacts already satisfy the preserved catalog and supply-chain contracts.

## Next Phase Readiness

- FORE-01 can be re-verified against mutually consistent paths/quantiles, bounded fair maturity evidence, record-scoped repair, and durable reconnect semantics.
- Plan 05-27 may strengthen executed-byte provenance without changing these canonical input/commit identities or creating a supply fallback.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched as required by the Wave 14 executor contract.

## Self-Check: PASSED

- All ten scoped implementation/test artifacts and this summary exist in the isolated checkout.
- RED/GREEN/fix/cleanup commits `1e0243f`, `0203427`, `daaf22c`, `a49dfb4`, `d139920`, `d3c23cb`, `bc70104`, and `50168d2` resolve as commits.
- The literal plan-level three-part verification passed 13 API/artifact/SSE cases, 2 migration cases, and 6 maturity cases; focused Forecast regressions and production-host smoke also passed.
- Stub and threat-surface scans found no goal-blocking placeholder or unplanned trust boundary.
- No task commit deleted a tracked file; `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
