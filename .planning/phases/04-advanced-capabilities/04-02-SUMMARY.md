---
phase: 04-advanced-capabilities
plan: "02"
subsystem: testing
tags: [pytest, sqlite, fastapi, sse, langgraph, tdd, authorization, idempotency]
requires:
  - phase: 03-ai-analysis
    provides: server-derived subject scope, SQLite graph checkpoint facade, and scoped SSE subscriber patterns
provides:
  - RED contracts for two-stage scoped authorization, quota accounting, idempotent advanced jobs, and audit-only denials
  - RED contracts for ownership-safe advanced API DTOs and committed scope-filtered SSE progress
  - RED contracts for fixed replay-safe LangGraph topology, pure interrupts, and record-once outcomes
affects: [SAFE-01, advanced-backend, advanced-api, advanced-workflow, advanced-sse]
tech-stack:
  added: []
  patterns:
    - temporary SQLite and fake clock fixtures for deterministic authorization-state contracts
    - bounded provider and sandbox spies that prove denied or replayed flows perform no work
    - subscriber-queue scope filtering and allowlisted persistent progress DTOs
key-files:
  created:
    - backend/tests/advanced/test_authorization_jobs.py
    - backend/tests/advanced/test_api_sse.py
    - backend/tests/advanced/test_workflow.py
  modified: []
key-decisions:
  - "SAFE-01 contracts require both creation-time and execution-start authorization against current server policy."
  - "Advanced SSE tests permit only committed allowlisted stage projections after server-bound subscriber scope filtering."
  - "The fixed graph treats checkpoints as recovery cursors and persists authority only through idempotent record_once outcomes."
patterns-established:
  - "Advanced security contracts use fake collaborators and assert zero provider or sandbox calls on every denied path."
  - "Replay tests require a server-owned thread ID and a durable job-plus-outcome uniqueness boundary."
requirements-completed: [SAFE-01]
coverage:
  - id: SAFE-01-AUTHORIZATION-RED-CONTRACT
    description: Two-stage scoped authorization, audit-only rejection, quota accounting, idempotent submission, and pre-run revocation/policy revalidation are specified.
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_authorization_jobs.py -q
        status: fail
    human_judgment: true
    rationale: Phase 4 advanced-domain production modules are intentionally absent; this Wave 0 contract must fail until the deterministic authorization and job services exist.
  - id: SAFE-01-API-SSE-RED-CONTRACT
    description: Advanced HTTP reads, audit projections, rejected creates, and subscriber queues are constrained by persisted scope and a safe event allowlist.
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_api_sse.py -q
        status: fail
    human_judgment: true
    rationale: The scoped advanced router and QuoteService projection extension are intentionally not implemented in Wave 0.
  - id: SAFE-01-WORKFLOW-RED-CONTRACT
    description: The advanced LangGraph facade has a fixed deterministic topology, server-owned thread binding, pure interrupt, and idempotent outcome persistence contract.
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_workflow.py -q
        status: fail
    human_judgment: true
    rationale: The Phase 4 workflow facade is intentionally absent until later implementation plans consume this RED contract.
metrics:
  duration: 4m 39s
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 02: Advanced Safety RED Contracts Summary

**Three deterministic RED pytest contracts now define scoped agent authorization, safe advanced API/SSE projections, and replay-safe workflow persistence before the Phase 4 domain implementation exists.**

## Performance

- **Duration:** 4m 39s
- **Started:** 2026-07-12T14:01:18Z
- **Completed:** 2026-07-12T14:05:57Z
- **Tasks:** 3/3
- **Files modified:** 3

## Accomplishments

- Defined SAFE-01 creation and worker-start authorization contracts for opaque server-issued records, policy intersections, expiry/revocation, request rejection, quota consumption, transactional idempotency, and redacted audit-only denial.
- Defined ownership-safe advanced API and SSE contracts for opaque resource IDs, server-derived principals, strict response projections, rejected-create behavior, committed-stage allowlists, and subscriber-time scope filtering.
- Defined a fixed advanced LangGraph contract with server-owned thread IDs, deterministic routes, prompt-injection-resistant drafts, a side-effect-free interrupt, and replay-safe idempotent outcome recording.

## Task Commits

1. **Task 1: Define two-phase scoped authorization and durable job contracts** - `142f769` (`test`)
2. **Task 2: Define safe API projection and server-scoped advanced SSE contracts** - `348441f` (`test`)
3. **Task 3: Define replay-safe fixed workflow topology** - `0ad0d8c` (`test`)
4. **Follow-up: Align RED contracts with lint rules** - `bd77597` (`fix`)

## Files Created/Modified

- `backend/tests/advanced/test_authorization_jobs.py` - RED two-phase authorization, denial audit, idempotency, quota, and pre-run revalidation contract.
- `backend/tests/advanced/test_api_sse.py` - RED scope-safe advanced API DTO, rejection, audit, and committed SSE projection contract.
- `backend/tests/advanced/test_workflow.py` - RED fixed workflow topology, injection isolation, pure interrupt, and record-once replay contract.

## Verification

```text
cd backend && uv run python -m compileall -q tests/advanced/test_authorization_jobs.py tests/advanced/test_api_sse.py tests/advanced/test_workflow.py
passed

cd backend && uv run ruff check tests/advanced/test_authorization_jobs.py tests/advanced/test_api_sse.py tests/advanced/test_workflow.py
passed

cd backend && uv run pytest tests/advanced/test_authorization_jobs.py tests/advanced/test_api_sse.py tests/advanced/test_workflow.py -q
16 failed as expected: every failure is ModuleNotFoundError for the intentionally absent app.advanced implementation.
```

## Decisions Made

- Authorization is tested at task creation and immediately before work begins, with current token, allowlist, and quota state as the only authority.
- HTTP and SSE projections expose only allowlisted durable state; browser-supplied principal, policy, thread, or opaque identifier fields cannot grant access.
- Workflow checkpoints are recovery cursors, while the repository must own atomic outcome uniqueness under repeated resume.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected Ruff violations in new RED contracts**
- **Found during:** Plan-level verification after Task 3
- **Issue:** Regex assertions omitted raw-string markers and one local import block was not ordered according to repository lint rules.
- **Fix:** Marked regexes as raw strings and applied Ruff's deterministic import ordering.
- **Files modified:** `backend/tests/advanced/test_authorization_jobs.py`, `backend/tests/advanced/test_api_sse.py`, `backend/tests/advanced/test_workflow.py`
- **Verification:** Focused Ruff check and Python compilation pass.
- **Committed in:** `bd77597`

**Total deviations:** 1 auto-fixed (1 bug).
**Impact on plan:** Lint-only correction; contracts and planned behavior remain unchanged.

## Known Stubs

None. The three files intentionally provide executable RED contracts; their missing `app.advanced` imports are the planned implementation boundary, not test placeholders.

## Issues Encountered

None. Focused pytest failures are the required RED state because the Phase 4 `app.advanced` domain has not been implemented.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 04-04, 04-07, and 04-08 can implement advanced repository, authorization/job, API/SSE, and workflow services against these safety contracts.
- The future implementation must replace the intended `ModuleNotFoundError` failures with passing tests without relaxing server-derived authority, scope, or replay assertions.

## Self-Check: PASSED

Verified the three created test files exist and task/follow-up commits `142f769`, `348441f`, `0ad0d8c`, and `bd77597` are present in git history. `STATE.md` and `ROADMAP.md` were intentionally not modified per execution request.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
