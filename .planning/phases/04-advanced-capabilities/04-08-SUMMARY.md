---
phase: 04-advanced-capabilities
plan: "08"
subsystem: advanced-workflow-sse
tags: [langgraph, sqlite, sse, authorization, idempotency, scope-filtering]
requires:
  - phase: 04-06
    provides: immutable experiment and promotion services with registered-only outcomes
  - phase: 04-07
    provides: durable authorization, job revalidation, and fail-closed security controls
provides:
  - fixed replay-safe advanced LangGraph facade bound to server-owned job threads
  - committed-only scoped advanced SSE stages with bounded per-subscriber queues
  - ownership-safe job and audit projections for the advanced router
affects: [04-09, advanced-api, advanced-workflow, advanced-sse]
tech-stack:
  added: []
  patterns:
    - per-invocation AsyncSqliteSaver with server-owned checkpoint binding
    - deterministic graph routing with pure interrupt and idempotent outcome adapter
    - subscription-time advanced scope filtering before bounded SSE queues
key-files:
  created:
    - backend/app/advanced/workflow.py
  modified:
    - backend/app/advanced/api.py
    - backend/app/api/intraday.py
    - backend/app/services/quote_service.py
key-decisions:
  - "Advanced graph checkpoints are bound to server-owned job threads and remain recovery cursors rather than an authorization source."
  - "Advanced SSE emits only committed allowlisted stages after immutable server scope filtering and never carries drafts, tokens, policy, code, paths, or diagnostics."
patterns-established:
  - "Graph nodes use narrow injected adapters for authorization, frozen evidence, optional draft, deterministic gates, and idempotent outcome recording."
  - "Advanced job and audit reads perform principal plus subject-scope checks before hand-built safe projections."
requirements-completed: [ADV-03, SAFE-01]
coverage:
  - id: ADV-03-REPLAY-SAFE-WORKFLOW
    description: Fixed advanced graph validates the server thread binding, freezes inputs before untrusted draft data, routes only deterministic gate results, pauses without side effects, and delegates final writes to idempotent record_once.
    requirement: ADV-03
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_workflow.py -q
        status: pass
    human_judgment: false
  - id: SAFE-01-SCOPED-ADVANCED-SSE
    description: Advanced SSE progress is a committed, allowlisted, bounded projection filtered against the server-derived subscription scope before it enters a subscriber queue.
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_api_sse.py -q
        status: pass
    human_judgment: false
metrics:
  duration: 6m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 08: Fixed Advanced Workflow and Scoped SSE Summary

**A server-thread-bound LangGraph workflow now freezes authorized inputs before deterministic gates, while shared SSE delivers only committed safe advanced stages to matching server-scoped subscribers.**

## Performance

- **Duration:** 6m
- **Started:** 2026-07-12T14:44:00Z
- **Completed:** 2026-07-12T14:50:20Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Added a fixed advanced workflow topology with per-invocation SQLite checkpoints, server-owned thread validation, frozen evidence, constrained draft projection, deterministic gates, pure human interrupt, and idempotent terminal adapters.
- Added a bounded `advanced_progress` subscriber collection that rejects uncommitted or non-allowlisted stages and filters every safe event against the subscription's immutable server-derived subject scope before queueing.
- Added safe advanced job/audit read and resume projections required by the shared SSE contract without registering the advanced router in the main application.

## Task Commits

1. **Task 1: Implement fixed replay-safe advanced workflow facade** - `8082c5c` (`feat`)
2. **Task 3: Extend shared SSE with scoped durable advanced stages** - `8084009` (`feat`)

## Files Created/Modified

- `backend/app/advanced/workflow.py` - Fixed LangGraph facade and narrow injected adapters for replay-safe advanced jobs.
- `backend/app/advanced/api.py` - Server principal/scope checks and hand-built job/audit projections needed by the advanced SSE contract.
- `backend/app/api/intraday.py` - Resolves optional server-derived advanced scope and emits the matching SSE event.
- `backend/app/services/quote_service.py` - Holds bounded advanced progress queues and broadcasts only committed allowlisted projections.

## Verification

```text
cd backend && uv run pytest tests/advanced/test_workflow.py tests/advanced/test_api_sse.py -q
8 passed in 0.58s

cd backend && uv run ruff check app/advanced/api.py tests/advanced/test_api_sse.py
All checks passed

cd backend && uv run python -m compileall -q app/advanced/workflow.py app/advanced/api.py app/api/intraday.py app/services/quote_service.py
passed
```

## Decisions Made

- The graph accepts a checkpoint thread only when it matches the injected server-owned job binding; draft payload authority fields and routing hints are discarded before gates run.
- Advanced SSE state is a post-commit delivery projection, not a job-security truth source. Subscriber scopes are bound at connection creation and checked before enqueueing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Made mismatched workflow bindings report a server-thread rejection**
- **Found during:** Task 1
- **Issue:** The rejected thread-binding message omitted the server/thread safety wording expected by the durable ownership contract.
- **Fix:** Reported a clear server thread ownership mismatch while retaining the fail-closed check before any graph node executes.
- **Files modified:** `backend/app/advanced/workflow.py`
- **Verification:** `uv run pytest tests/advanced/test_workflow.py -q` passed.
- **Committed in:** `8082c5c`

**2. [Rule 3 - Blocking Issue] Added the minimal safe advanced job/audit projection boundary**
- **Found during:** Task 3
- **Issue:** The existing advanced router exposed only promotion, so the pre-existing scoped SSE contract could not construct its temporary authenticated host or validate job/audit ownership.
- **Fix:** Added server-principal and subject-scope checked job, audit, and resume projections without router registration, policy editing, or execution capability.
- **Files modified:** `backend/app/advanced/api.py`
- **Verification:** `uv run pytest tests/advanced/test_api_sse.py -q` passed.
- **Committed in:** `8084009`

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 3 blocking integration issue).
**Impact on plan:** Both changes enforce the intended authorization and verification contract without adding execution authority or registering an advanced host route.

## Known Stubs

None. The optional draft provider has a deterministic no-provider path, while all persisted authority and outcome work remains delegated to injected services.

## Issues Encountered

- A whole-file Ruff check of `backend/app/services/quote_service.py` reports existing unrelated documentation/style violations. Focused advanced API lint, compilation, and all targeted workflow/SSE tests pass; the deferred item records this scope-bound follow-up.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 04-09 can register the already-defined advanced router and inject the operational advanced services into the single application lifespan. `STATE.md` and `ROADMAP.md` remain untouched by request.

## Self-Check: PASSED

Verified `backend/app/advanced/workflow.py` and this summary exist, and task commits `8082c5c` and `8084009` are present in git history. `STATE.md` and `ROADMAP.md` were not modified.
