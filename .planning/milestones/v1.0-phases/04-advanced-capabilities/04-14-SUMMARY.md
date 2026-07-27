---
phase: 04-advanced-capabilities
plan: "14"
subsystem: advanced-production-host
tags: [fastapi, linux-namespaces, sandbox, sse, playwright]
requires:
  - phase: 04-12
    provides: real FastAPI lifespan fixture and governed execution boundary
  - phase: 04-13
    provides: committed advanced job stages and scoped root SSE publication
provides:
  - fail-closed Linux isolation capability probe with safe terminal sandbox run facts
  - root SSE subscriber readiness signal and real FastAPI browser host coverage
affects: [SAFE-02, SAFE-01, ADV-01, ADV-02, ADV-03]
tech-stack:
  added: []
  patterns:
    - affirmative Linux namespace and private-root proof before untrusted child spawn
    - Playwright-owned temporary FastAPI host with no advanced API or root SSE interception
key-files:
  created:
    - frontend/e2e/phase4-advanced-capabilities.host.spec.ts
  modified:
    - backend/app/advanced/sandbox.py
    - backend/app/advanced/projections.py
    - backend/app/advanced/repository.py
    - backend/app/main.py
    - backend/app/api/intraday.py
    - backend/tests/advanced/test_production_host.py
    - backend/tests/advanced/test_sandbox.py
    - frontend/playwright.config.ts
key-decisions:
  - "Custom strategy source may spawn only after a fresh complete Linux isolation proof; unavailable or stale proof rejects before spawn."
  - "A root SSE subscriber sends a data-free ready event after scope-bound registration so host acceptance can avoid connection races."
requirements-completed: [SAFE-02, ADV-01, ADV-02, ADV-03, SAFE-01]
coverage:
  - id: D1
    description: Custom strategy execution remains fail-closed until Linux namespace, private-root, filesystem, network, and resource proof is affirmative; terminal runs expose only safe facts.
    requirement: SAFE-02
    verification:
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py#test_affirmative_isolation_proof_records_one_safe_terminal_sandbox_run
        status: pass
      - kind: integration
        ref: backend/tests/advanced/test_sandbox.py
        status: pass
    human_judgment: false
  - id: D2
    description: Browser acceptance starts a real FastAPI lifespan host, rejects an unauthenticated request, and receives the final persisted advanced stage through root SSE without route interception.
    requirement: SAFE-01
    verification:
      - kind: e2e
        ref: frontend/e2e/phase4-advanced-capabilities.host.spec.ts#real FastAPI host accepts an authorized advanced job and emits root SSE progress
        status: pass
    human_judgment: false
metrics:
  duration: 16m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 14: Real Sandbox and Host Acceptance Summary

**Capability-gated Linux sandbox execution now records safe terminal facts, while a non-intercepted Playwright host proves real advanced API and root SSE delivery.**

## Performance

- **Duration:** 16m
- **Started:** 2026-07-12T19:07:05Z
- **Completed:** 2026-07-12T19:22:49Z
- **Tasks:** 2/2
- **Files modified:** 10

## Accomplishments

- Added a fail-closed `LinuxIsolationLauncher` that probes user, mount, PID, and network namespaces plus a private root before any submitted source can start.
- Persisted append-only safe sandbox terminal facts and exposed only run status, proof fingerprint, resource summary, audit reference, and run identifier.
- Wired the production FastAPI lifespan to the Linux launcher and added real-host coverage for affirmative terminal records and proof-unavailable rejection.
- Added a dedicated Playwright host project that starts an isolated real FastAPI process, verifies an unauthenticated denial, then validates the authorized job's committed root SSE stage without advanced route interception.

## Task Commits

1. **Task 1: Run custom strategies only after affirmative Linux isolation proof** - `433d707` (test RED), `9c87f6b` (feat GREEN)
2. **Task 2: Prove the real FastAPI and browser acceptance paths without route fixtures** - `939a6dd` (test RED), `c0b8775` (feat GREEN)

## Verification

```text
cd backend && timeout 60s uv run pytest tests/advanced/test_production_host.py tests/advanced/test_sandbox.py -q
31 passed, 12 warnings

cd frontend && timeout 30s pnpm exec tsc -b --pretty false
passed

cd frontend && timeout 90s pnpm exec playwright test e2e/phase4-advanced-capabilities.host.spec.ts --project=phase4-fastapi-host
1 passed
```

## Files Created/Modified

- `backend/app/advanced/sandbox.py` - Linux namespace/private-root probe, bounded child launcher, and terminal sandbox record flow.
- `backend/app/advanced/repository.py` - Append-only sandbox run persistence and safe manifest decode.
- `backend/app/advanced/projections.py` - Allowlisted terminal sandbox run DTO.
- `backend/app/main.py` - Explicit lifecycle construction of the production Linux launcher.
- `backend/app/api/intraday.py` - Safe root SSE subscription readiness event.
- `backend/tests/advanced/test_production_host.py` - Affirmative and real-lifespan sandbox proof coverage.
- `frontend/e2e/phase4-advanced-capabilities.host.spec.ts` - Real FastAPI browser API/SSE acceptance harness.
- `frontend/playwright.config.ts` - Dedicated `phase4-fastapi-host` project.

## Decisions Made

- Capability evidence is fresh and complete or no submitted code starts; there is no host-process fallback.
- The host acceptance test treats SSE as a committed stage sequence and verifies the final event against the durable job projection.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added a root SSE subscriber-ready event**
- **Found during:** Task 2
- **Issue:** HTTP-level EventSource `open` can occur before the async server generator registers its scoped subscriber, producing a host-test race that misses the first committed event.
- **Fix:** Emit a data-free `stream_ready` event only after subscription registration; the browser waits for this signal before starting work.
- **Files modified:** `backend/app/api/intraday.py`, `frontend/e2e/phase4-advanced-capabilities.host.spec.ts`
- **Verification:** Real FastAPI Playwright host test passes repeatedly when run serially.
- **Committed in:** `c0b8775`

**2. [Rule 2 - Missing Critical] Added append-only sandbox run repository methods**
- **Found during:** Task 1
- **Issue:** The existing schema had `advanced_sandbox_runs`, but no repository operation could create or retrieve a durable terminal run projection.
- **Fix:** Added append-only run persistence and a deny-by-default terminal projection.
- **Files modified:** `backend/app/advanced/repository.py`, `backend/app/advanced/projections.py`
- **Verification:** Sandbox and production host tests pass.
- **Committed in:** `9c87f6b`

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 2 missing critical).
**Impact on plan:** Both changes are necessary for deterministic real-host verification and SAFE-02 auditability; neither expands execution authority.

## Issues Encountered

- Parallel browser and backend validation briefly exhausted Chromium thread resources. Serial Playwright verification passed.
- `backend/app/main.py` retains pre-existing whole-file Ruff findings outside this plan's lifecycle line; targeted changed modules pass Ruff and compilation checks.

## Known Stubs

None. The sandbox result projection is backed by durable terminal records, and the browser suite runs against a real FastAPI process.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 04 has real-host proof for the advanced API and root SSE path, with a fail-closed custom strategy boundary suitable for final phase verification.

## TDD Gate Compliance

Task 1 and Task 2 each contain the required RED then GREEN commit sequence.

## Self-Check: PASSED

Verified created host spec and modified sandbox files exist; task commits `433d707`, `9c87f6b`, `939a6dd`, and `c0b8775` are present in git history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
