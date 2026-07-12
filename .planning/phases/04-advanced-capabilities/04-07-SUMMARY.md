---
phase: 04-advanced-capabilities
plan: "07"
subsystem: advanced-safety
tags: [sqlite, authorization, rate-limit, idempotency, sandbox, ast, fail-closed]
requires:
  - phase: 04-04
    provides: strict deployment-owned policy contracts and append-only advanced SQLite facts
  - phase: 04-02
    provides: two-stage authorization and durable job RED contracts
  - phase: 04-03
    provides: hostile custom-strategy admission and isolation RED contract
provides:
  - opaque server-bound authorizations with hashed secrets, least-privilege scope, revocation, and expiry checks
  - transactional quota accounting and durable idempotent jobs revalidated immediately before work
  - fail-closed custom-strategy admission with source binding, hostile AST rejection, affirmative isolation probes, and redacted records
affects: [04-08, 04-09, advanced-backend, advanced-workflow, advanced-api]
tech-stack:
  added: []
  patterns:
    - server-owned authorization facts and policy intersections are re-read at both creation and start time
    - security rate windows allow only monotonic consumption within their immutable identity and time window
    - untrusted source is admitted only after strict contract binding, AST checks, and affirmative launcher proof
key-files:
  created:
    - backend/app/advanced/authorization.py
    - backend/app/advanced/jobs.py
    - backend/app/advanced/sandbox.py
  modified:
    - backend/app/advanced/repository.py
    - backend/app/operational/migrations.py
key-decisions:
  - "Authorization tokens remain opaque to callers: only SHA-256 hashes, server principal bindings, and frozen scope facts are persisted."
  - "A queued job is rejected durably when revocation, current scope, expiry, or quota fails immediately before work."
  - "No unproven launcher has a fallback execution path; missing, false, or inconclusive isolation proof rejects without spawning source."
patterns-established:
  - "Rejected advanced actions append redacted security audits and never create runnable work or invoke collaborators."
  - "Sandbox records retain contract/source hashes and safe reasons only, never source content, paths, tracebacks, or raw runner output."
requirements-completed: [SAFE-01, SAFE-02]
coverage:
  - id: SAFE-01-AUTHORIZATION-JOBS
    description: Server-owned scoped authorization, transactional quota accounting, idempotent durable jobs, and start-time revocation/policy revalidation reject without work.
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_authorization_jobs.py -q
        status: pass
    human_judgment: false
  - id: SAFE-02-FAIL-CLOSED-SANDBOX
    description: Strict source/contract binding, AST/import admission, affirmative isolation capability checks, cleanup, redaction, and resource terminal paths prevent host execution.
    requirement: SAFE-02
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_sandbox.py -q
        status: pass
    human_judgment: false
metrics:
  duration: 5m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 07: Scoped Authorization and Fail-Closed Sandbox Summary

**Durable server-owned authorization and a fail-closed custom-strategy boundary now reject unsafe work before provider, sandbox, graph, or SSE activity can begin.**

## Performance

- **Duration:** 5m
- **Started:** 2026-07-12T14:38:22Z
- **Completed:** 2026-07-12T14:43:54Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Added opaque, short-lived authorization issuance with persisted SHA-256 token hashes, server principal bindings, restricted policy intersections, expiry, revocation, and redacted rejection audits.
- Added persistent idempotent jobs with atomic rate-window consumption and current authorization, policy scope, and quota revalidation immediately before invoking provider work.
- Added strict custom-strategy contract/source hashing, hostile AST and import rejection, affirmative all-fields isolation capability verification, cleanup, and safe terminal diagnostics with no host-engine fallback.

## Task Commits

1. **Task 1: Implement server-owned scoped authorizations and durable job revalidation** - `80ca866` (`feat`)
2. **Task 2: Implement strict custom-strategy validation and capability-gated runner** - `0b73978` (`feat`)

## Files Created/Modified

- `backend/app/advanced/authorization.py` - Opaque authorization issuance, revocation, expiry, principal, policy, and scope validation.
- `backend/app/advanced/jobs.py` - Atomic job creation and immediately-before-work revalidation with audit-only rejection.
- `backend/app/advanced/sandbox.py` - Strict admission, AST guards, fail-closed capability proof, sanitized terminal handling, and temporary handoff cleanup.
- `backend/app/advanced/repository.py` - Parameterized persistence for authorizations, quota accounting, security audits, and sandbox validation facts.
- `backend/app/operational/migrations.py` - Forward migration permitting only monotonic consumption updates in immutable-identity rate windows.

## Verification

```text
cd backend && uv run pytest tests/advanced/test_authorization_jobs.py -q
8 passed in 2.70s

cd backend && uv run pytest tests/advanced/test_sandbox.py -q
21 passed in 6.58s

cd backend && uv run pytest tests/advanced/test_authorization_jobs.py tests/advanced/test_sandbox.py -q
29 passed in 10.34s

cd backend && uv run ruff check app/advanced/authorization.py app/advanced/jobs.py app/advanced/sandbox.py app/advanced/repository.py app/operational/migrations.py
All checks passed
```

## Decisions Made

- Reject before job acquisition when the request is malformed, outside server-derived scope, revoked, expired, or rate-limited; audit records expose only stable safe reasons.
- Revalidate durable queued jobs against current authorization and policy immediately before work, rather than trusting their creation-time snapshot.
- Treat launcher availability as an affirmative proof requirement. A launcher without a bounded proven-isolation capability rejects and cannot execute source in the host process.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Made persisted rate-window consumption safely mutable**
- **Found during:** Task 1
- **Issue:** The foundational immutable trigger blocked all consumption increments, preventing transactional rate-window accounting after the first request.
- **Fix:** Added a forward migration which preserves immutable rate-window identity and permits only strictly increasing consumption within the same persisted window.
- **Files modified:** `backend/app/operational/migrations.py`, `backend/app/advanced/repository.py`
- **Verification:** Quota and idempotency contracts passed, including exactly-one consumption for a duplicate submission.
- **Committed in:** `80ca866`

**Total deviations:** 1 auto-fixed (1 Rule 2 critical functionality gap).
**Impact on plan:** The forward migration is required to enforce, rather than bypass, the planned transactional rate limit. No authority or execution scope was broadened.

## Known Stubs

None. The default sandbox launcher rejects every run until an affirmative external isolation implementation is injected; this is the intentional SAFE-02 fail-closed state, not a placeholder execution path.

## Issues Encountered

None. The pre-existing RED contracts transitioned to green without weakening their authority, rejection, or zero-side-effect assertions.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plans 04-08 and 04-09 can attach workflow and API surfaces only through the durable authorization/job service and safe sandbox projections. `STATE.md` and `ROADMAP.md` remain untouched by request.

## Self-Check: PASSED

Verified the created services and this summary exist, task commits `80ca866` and `0b73978` are present in git history, and neither `STATE.md` nor `ROADMAP.md` was modified.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
