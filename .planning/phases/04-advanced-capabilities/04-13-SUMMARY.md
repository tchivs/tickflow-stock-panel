---
phase: 04-advanced-capabilities
plan: "13"
subsystem: advanced-production-host
tags: [fastapi, sqlite, langgraph, sse, authorization]
requires:
  - phase: 04-07
    provides: server-owned advanced authorization records and durable job cursor
  - phase: 04-08
    provides: fixed persistent advanced workflow topology
  - phase: 04-12
    provides: production FastAPI lifespan integration test fixture
provides:
  - revalidated server-bound advanced workflow execution for authorized durable jobs
  - atomic job-stage and security-audit persistence before scoped SSE publication
  - real-lifespan proofs for allowed and denied advanced job progress
affects: [advanced-backend, SAFE-01, ADV-03]
tech-stack:
  added: []
  patterns:
    - durable cursor plus append-only audit transaction before delivery-only SSE fan-out
    - lifespan-owned narrow workflow adapters with server-generated job thread IDs
key-files:
  created: []
  modified:
    - backend/app/advanced/jobs.py
    - backend/app/advanced/repository.py
    - backend/app/advanced/api.py
    - backend/app/main.py
    - backend/tests/advanced/test_production_host.py
key-decisions:
  - "The job service, not graph callbacks or browser input, owns stage persistence and post-commit publication."
  - "Production workflow adapters are deterministic and bounded; the graph remains a recovery cursor rather than an authority source."
requirements-completed: [SAFE-01, ADV-03]
coverage:
  - id: D1
    description: Authorized session-bound jobs are revalidated and advance through the lifecycle-bound fixed workflow with a durable review state and audit projection.
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py#test_authorized_main_host_job_runs_fixed_workflow_and_persists_audit
        status: pass
      - kind: integration
        ref: backend/tests/advanced/test_authorization_jobs.py
        status: pass
    human_judgment: false
  - id: D2
    description: Scoped advanced progress is emitted only after the matching persistent cursor and audit fact exist, and denied scopes receive no queued event.
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py#test_main_host_publishes_committed_scoped_advanced_progress_only
        status: pass
      - kind: integration
        ref: backend/tests/advanced/test_api_sse.py
        status: pass
    human_judgment: false
metrics:
  duration: 7m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 13: Authorized Workflow and SSE Summary

**Authorized advanced jobs now revalidate into a server-bound fixed workflow, persist each cursor and audit fact atomically, and publish only committed scoped SSE stages.**

## Performance

- **Duration:** 7m
- **Started:** 2026-07-12T18:54:28Z
- **Completed:** 2026-07-12T19:01:33Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Replaced the lifecycle no-op job provider with deterministic fixed-workflow adapters and a post-authorization async runner.
- Preserved idempotent active jobs, revalidated queued work immediately before execution, and converted workflow failures to safe persisted rejections.
- Added one SQLite transaction that writes an append-only audit alongside each legal advanced-job transition before the quote service fan-out.
- Proved real-lifespan authorized job progression, audit projection, scope-filtered committed progress, and no-event denial behavior.

## Task Commits

1. **Task 1: Execute authorized jobs through the persisted fixed workflow** - `c7c7be1` (test RED), `5c8f7ea` (feat GREEN)
2. **Task 2: Publish only committed scoped job stages on the real SSE stream** - `4d3911b` (feat)

## Files Created/Modified

- `backend/app/advanced/jobs.py` - Revalidation, server-bound graph invocation, durable stage transitions, and post-commit progress publication.
- `backend/app/advanced/repository.py` - Atomic cursor-transition and append-only-audit transaction plus audit lookups.
- `backend/app/advanced/api.py` - Awaits the production runner while preserving fixture-only service compatibility.
- `backend/app/main.py` - Builds deterministic lifecycle workflow adapters and injects the real QuoteService publisher.
- `backend/tests/advanced/test_production_host.py` - Real FastAPI lifespan coverage for authorized workflow and scoped advanced progress.

## Verification

```text
cd backend && timeout 60s uv run pytest tests/advanced/test_authorization_jobs.py tests/advanced/test_workflow.py tests/advanced/test_api_sse.py tests/advanced/test_production_host.py -q
22 passed, 9 warnings

cd backend && uv run ruff check app/advanced/jobs.py app/advanced/repository.py app/advanced/api.py tests/advanced/test_production_host.py
All checks passed

cd backend && uv run python -m compileall -q app/advanced/jobs.py app/advanced/repository.py app/advanced/api.py app/main.py
passed
```

## Decisions Made

- Job-state mutation and its audit fact commit together before the delivery-only quote service is called, so clients cannot observe a stage without durable evidence.
- The fixed workflow receives only persisted job, authorization, subject, and server-thread bindings; neither browser fields nor graph checkpoints grant authority.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added atomic stage/audit repository operation**
- **Found during:** Task 1
- **Issue:** Existing repository methods committed the job cursor and append-only audit in separate transactions, violating T-04-42's required ordering proof.
- **Fix:** Added a narrow transaction that inserts the audit fact and conditionally advances the cursor together, then returns the committed projection for publication.
- **Files modified:** `backend/app/advanced/repository.py`
- **Verification:** Production host tests assert SSE event stage, timestamp, and audit reference match the persisted job and audit route.
- **Committed in:** `5c8f7ea`

**2. [Rule 1 - Bug] Preserved minimal API service fixtures after async start wiring**
- **Found during:** Task 2
- **Issue:** Existing API projection tests use a fixture service that intentionally has no workflow collaborator; awaiting its missing runner raised an `AttributeError`.
- **Fix:** Kept the creation-only projection path for collaborator-free fixtures while production services always provide and await `run_authorized_job`.
- **Files modified:** `backend/app/advanced/api.py`
- **Verification:** `tests/advanced/test_api_sse.py` and real-host tests pass.
- **Committed in:** `4d3911b`

**Total deviations:** 2 auto-fixed (1 Rule 2 missing critical, 1 Rule 1 bug).
**Impact on plan:** Both changes enforce the stated durable ordering and preserve existing safe API-contract coverage without adding authority or execution capability.

## Issues Encountered

`backend/app/main.py` retains pre-existing whole-file Ruff findings outside the lifecycle additions. Targeted changed modules and host tests pass; unrelated formatting was not modified.

## Known Stubs

None. The lifecycle adapters produce bounded server-derived workflow inputs and persisted state; no placeholder result is projected to a client.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The production host now has a durable, scoped SAFE-01 job-to-workflow-to-SSE chain. Plan 04-14 can validate the remaining advanced capability closure.

## TDD Gate Compliance

Task 1 has the required RED (`c7c7be1`) then GREEN (`5c8f7ea`) sequence. Task 2's host proof was added after Task 1's shared post-commit publisher implementation because that publisher is necessary to Task 1's lifecycle wiring; the task's focused test was green on introduction and is retained as integration coverage.

## Self-Check: PASSED

Verified `backend/app/advanced/jobs.py` and `backend/tests/advanced/test_production_host.py` exist, and task commits `c7c7be1`, `5c8f7ea`, and `4d3911b` are present in git history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
