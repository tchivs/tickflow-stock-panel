---
phase: 05-optional-enhancements
plan: "14"
subsystem: optional-module-host
status: complete
tags: [fastapi, forecast, calibration, sse, optional-modules, lifespan, sqlite, recovery]
requires:
  - phase: 05-optional-enhancements
    plan: "11"
    provides: Shadow research-only service and safe object-authorized router
  - phase: 05-optional-enhancements
    plan: "12"
    provides: Thesis lifecycle service, safe router, and restart-safe due scanner
  - phase: 05-optional-enhancements
    plan: "13"
    provides: Forecast CAS job ledger, immutable records, retry lineage, and restart recovery
provides:
  - append-only Forecast maturity outcomes and versioned calibration metrics
  - object-authorized Forecast jobs, immutable records, paths, calibration, and bounded persisted-state SSE
  - one production lifespan registering Shadow, Thesis, and Forecast independently
  - module-local probe, initialization, recovery, scanner, and shutdown isolation
  - completed-v1 availability across all eight optional-module combinations
affects: [05-15, 05-16, 05-17, SHDW-01, THES-01, FORE-01]
tech-stack:
  added: []
  patterns:
    - canonical unique maturity fact with atomic outcome-and-calibration append
    - deny-by-default Forecast DTOs and object authorization before disclosure
    - bounded SSE subscribers seeded from persisted job state on every reconnect
    - independently probed lazy optional factories installed in one FastAPI lifespan
key-files:
  created:
    - backend/app/forecast/calibration.py
    - backend/app/forecast/projections.py
    - backend/app/forecast/api.py
  modified:
    - backend/app/forecast/repository.py
    - backend/app/optional_modules.py
    - backend/app/main.py
    - backend/tests/test_phase5_optional_host.py
key-decisions:
  - "Forecast maturity evaluation uses the existing unique (forecast_id,horizon) fact identity and one immediate transaction rather than adding another mutable scheduler database or queue."
  - "Every Forecast SSE subscription re-authorizes the persisted job and emits only the committed job projection; the bounded in-memory queue is transport-only and never authoritative."
  - "All optional route shapes are installed once, while each lifespan independently probes, initializes, recovers, schedules, downgrades, and closes only its own module service."
patterns-established:
  - "Forecast maturity replay: canonical persisted outcomes return before governed actuals are reread, while interrupted pre-append work remains retryable."
  - "Optional host failure isolation: service state and typed status are cleared only for the failed module; completed-v1 and peer modules remain live."
requirements-completed: [SHDW-01, THES-01, FORE-01]
coverage:
  - id: D1
    description: "Forecast maturity scanning appends at most one immutable governed outcome and calibration fact with actual fingerprint, MAE, interval coverage, pinball losses, sample count, coverage period, and explicit unevaluable state."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_calibration.py (13 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Forecast jobs, records, paths, calibration, and progress are exposed through authenticated object-scoped deny-by-default APIs and persisted-state SSE."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_runner.py plus backend/tests/test_phase5_optional_host.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "The real lifespan preserves completed v1 while independently registering every Shadow, Thesis, and Forecast availability combination and isolating probe, initialization, recovery, and scanner failures."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "backend/tests/test_phase5_optional_host.py (12 passed)"
        status: pass
    human_judgment: false
metrics:
  duration: 20m
  completed: 2026-07-16
---

# Phase 05 Plan 14: Forecast Calibration API and Optional Host Summary

**Append-only Forecast calibration, object-scoped job/record/path/SSE APIs, and independently recoverable Shadow, Thesis, and Forecast factories now run inside AthenaQuant's one completed-v1 FastAPI lifespan.**

## Performance

- **Duration:** 20m
- **Started:** 2026-07-16T06:49:08Z
- **Completed:** 2026-07-16T07:08:54Z
- **Tasks:** 2/2
- **Files created:** 3
- **Files modified:** 4

## Accomplishments

- Added bounded restart-safe maturity evaluation that resolves the frozen future-session identity, never substitutes zero for missing/non-finite actuals, computes close MAE, P10–P90 coverage, P10/P50/P90 pinball losses, and appends outcome plus calibration atomically without changing the forecast.
- Added strict Forecast requests and hand-written public projections for catalog, create/reuse, explicit retry, job/history/detail, immutable records, verified paginated paths, calibration, fixture-only terminal verification, and bounded authenticated SSE seeded from committed persisted state.
- Registered Shadow, Thesis, and Forecast through one production lifespan with one operational database/data root, one route installation, independent lazy probes/factories, Forecast restart recovery, Thesis/Forecast scanner registration, local typed failures, and reverse-order close.
- Proved all eight availability combinations preserve authenticated data, portfolio, monitor, decision, intraday, and root-SSE completed-v1 surfaces while optional failures remain local and all live-action spies stay at zero.

## Task Commits

1. **Task 1: Append restart-safe maturity outcomes and expose safe Forecast API/SSE** — `e0dfcf0dbae9cd0995475f98f4f4d308b2a6e5aa` (`feat`)
2. **Task 2: Register three independent optional factories, routers, scanners, recovery, and shutdown** — `62e683d6ccc356cca983f21a9ec4b4ea6c109d19` (`feat`)

Inherited RED gates:

- Forecast calibration contract — `b2f4ba966696b32356c0347b5f7e35bf72b01e95`
- Real optional-host contract — `d7e3df2eb66e834f02546fb2408c58dd927709ff`

## Files Created/Modified

- `backend/app/forecast/calibration.py` — bounded maturity scanner, immutable session resolution, actual fingerprinting, metric computation, replay, interruption, and restart behavior.
- `backend/app/forecast/projections.py` — explicit allowlists for jobs, progress, records, artifacts, catalog entries, outcomes, calibration, and bounded pages.
- `backend/app/forecast/api.py` — authenticated stock-scoped Forecast create/retry/read/path/calibration routes plus bounded reconnectable SSE.
- `backend/app/forecast/repository.py` — canonical maturity reads, atomic outcome/calibration append, aggregate coverage summary, immutable fixture records, and instrument-scoped history.
- `backend/app/optional_modules.py` — concrete lazy factories, typed probes, shared runtime identities, module-local lifecycle status, router installation, recovery/scanner registration, and reverse shutdown.
- `backend/app/main.py` — narrow build/install/close seam inside the existing lifespan after shared prerequisites are ready.
- `backend/tests/test_phase5_optional_host.py` — corrected completed-v1 monitor response access and supplied a valid bounded Shadow retention body to exercise the intended object-not-found boundary.

## Verification

```text
RED Task 1:
uv run --offline --extra dev pytest tests/forecast/test_calibration.py tests/forecast/test_runner.py -x
Result before implementation: expected ModuleNotFoundError for app.forecast.calibration

Task 1:
uv run --offline --extra dev pytest tests/forecast/test_calibration.py tests/forecast/test_runner.py -x
Result: 39 passed

RED Task 2:
uv run --offline --extra dev pytest tests/test_phase5_optional_host.py -x
Result before implementation: expected missing OptionalModuleProbe production seam

Task 2:
uv run --offline --extra dev pytest tests/test_phase5_optional_host.py -x
Result: 12 passed

Compatibility:
uv run --offline --extra dev pytest tests/test_phase5_foundation.py::test_optional_identity_is_independent_lazy_cached_and_light tests/test_phase5_foundation.py::test_optional_identity_probe_failure_is_sanitized_and_local -x
Result: 2 passed

Overall:
uv run --offline --extra dev pytest tests/forecast tests/test_phase5_optional_host.py -x
Result: 97 passed, 1 skipped (approved local-model regression assets absent)
```

All commands used the existing lock with `--offline --extra dev`. No dependency declaration, lock file, runtime network request, checkpoint download, formatter, linter, browser suite, or project-wide command ran.

## Decisions Made

- Used the schema's existing unique `(forecast_id,horizon)` identity and an immediate atomic append for the outcome/calibration pair. No second scheduler ledger, database, queue, process, service, or container was introduced.
- Kept job state authoritative in SQLite. SSE subscriber queues are bounded transport buffers only; initial and reconnect state is always read from the persisted job ledger.
- Installed optional routers exactly once because the FastAPI app object outlives repeated test lifespans, but rebuilt statuses and service state on every lifespan so a previous module combination cannot leak into the next.
- Kept terminal public vocabulary (`timeout`, `resource_terminated`, `checkpoint_mismatch`) as a safe projection over the persisted migration vocabulary (`timed_out`, `resource_limited`, `model_unavailable`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added Forecast repository maturity persistence primitives**
- **Found during:** Task 1
- **Issue:** Plan 05-13 supplied the durable job/record ledger, but the declared calibration contract required canonical forecast lookup, unique outcome/calibration append, aggregate coverage reads, and focused immutable fixture insertion that were not yet exposed by the repository.
- **Fix:** Added schema-compatible repository methods using the existing tables, unique key, immutable triggers, and one immediate transaction; no migration or new store was added.
- **Files modified:** `backend/app/forecast/repository.py`
- **Verification:** All 13 calibration contracts and all 26 existing runner contracts pass.
- **Committed in:** `e0dfcf0dbae9cd0995475f98f4f4d308b2a6e5aa`

**2. [Rule 1 - Contract Bug] Corrected two host RED fixture calls without weakening production assertions**
- **Found during:** Task 2
- **Issue:** The host contract treated the completed-v1 monitor payload as a bare list although the shipped frontend and route use `{rules: [...]}`, and it sent an empty body to a Shadow retention request whose strict pre-existing schema requires two evaluation IDs and a rationale. Both failed before the optional-host behavior under test.
- **Fix:** Asserted the existing `rules` list and supplied a valid bounded retention body, preserving every availability, authorization, foreign-ID, no-action, and completed-v1 assertion.
- **Files modified:** `backend/tests/test_phase5_optional_host.py`
- **Verification:** The complete 12-node real-lifespan matrix passes.
- **Committed in:** `62e683d6ccc356cca983f21a9ec4b4ea6c109d19`

---

**Total deviations:** 2 auto-fixed (1 missing critical persistence boundary, 1 blocking test-contract bug).
**Impact on plan:** Both changes were necessary to exercise the declared production behavior and remained inside Forecast persistence or the Plan 05-14 host contract. No unrelated runtime behavior or dependency changed.

## Threat Mitigation Evidence

- **T-05-14-01:** Canonical outcome lookup occurs before governed actual reads; the unique key and atomic outcome/calibration transaction collapse parallel/restart replay while forecast triggers prevent mutation.
- **T-05-14-02:** Opaque jobs and records resolve to persisted instruments before scope checks, and strict bodies reject principal, fingerprint, digest, verdict, status, quantile, or record authority from the browser.
- **T-05-14-03:** Public DTOs omit local paths, commands, environment, policy, raw worker/model output, traces, and unbounded path tensors; SSE emits only committed allowlisted progress fields.
- **T-05-14-04:** Every probe, initialization, recovery, and scanner branch downgrades only its own typed module state. All eight combinations retain the real completed-v1 host.
- **T-05-14-05:** Forecast calibration, requests, terminal cases, recovery, and optional-host failures never invoke strategy, thesis, plan, monitor, position, ledger, broker, provider-network, or market-action collaborators.

## Issues Encountered

- The isolated worktree began detached and was attached to `worktree-agent-05-14` before any commit.
- The fresh worktree had no virtual environment. `uv run --offline --extra dev` materialized only already-locked packages and changed neither `pyproject.toml` nor `uv.lock`.
- The opt-in Kronos regression remains skipped because approved local model assets were not provisioned; this is the declared local-only behavior and no download was attempted.

## TDD Gate Compliance

- Task 1 inherited RED commit `b2f4ba966696b32356c0347b5f7e35bf72b01e95`; the exact focused command was observed failing on the absent `app.forecast.calibration` module before GREEN commit `e0dfcf0dbae9cd0995475f98f4f4d308b2a6e5aa` made 39/39 nodes pass.
- Task 2 inherited RED commit `d7e3df2eb66e834f02546fb2408c58dd927709ff`; the exact focused command was observed failing on the absent `OptionalModuleProbe` seam before GREEN commit `62e683d6ccc356cca983f21a9ec4b4ea6c109d19` made the 12-node matrix pass.

## Known Stubs

None. Empty collections represent bounded histories/subscriber sets or explicit governed non-observation; unavailable optional collaborators fail closed through module-local typed status and never fabricate output. The testing terminal route is fixture-mode gated and persists real terminal ledger rows without creating fake forecast records.

## User Setup Required

None for the completed host or focused tests. Forecast inference remains available only when the deployment has explicitly provisioned and approved a pinned local Kronos checkpoint through the previously approved operator workflow.

## Next Phase Readiness

- Plan 05-15 can consume authenticated Shadow capability and history while relying on independently stable v1 and peer-module status.
- Plan 05-16 can consume Forecast catalog/jobs/SSE/records/path/calibration resources and Thesis lifecycle resources from the real host.
- Plan 05-17 can run final host/browser no-action acceptance against one operational database/data lake and the ordinary-green 12-node host matrix.

## Self-Check: PASSED

Verified all seven changed implementation/contract files and this summary exist; both GREEN commits and both inherited RED commits resolve; no tracked file was deleted; the overall focused suite passes 97 nodes with only the approved local-model skip; and no generated or unrelated untracked file remains.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
