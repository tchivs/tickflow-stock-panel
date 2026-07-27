---
phase: 04-advanced-capabilities
plan: "03"
subsystem: testing
tags: [pytest, playwright, tdd, sandbox, fail-closed, redaction, responsive-ui]
requires:
  - phase: 04-01
    provides: immutable research and promotion RED contract patterns
  - phase: 04-02
    provides: scoped authorization, safe projection, and SSE RED contracts
provides:
  - hostile custom-strategy admission and isolation RED contract
  - fixture-backed browser contract for all six Phase 4 UI scenarios
affects: [SAFE-02, SAFE-01, ADV-01, ADV-02, ADV-03, advanced-backend, advanced-frontend]
tech-stack:
  added: []
  patterns:
    - same-request contract plus source hash admission with fail-closed capability proof
    - fixture-only browser scenarios marked expected-fail until Phase 4 UI wiring exists
key-files:
  created:
    - backend/tests/advanced/test_sandbox.py
    - frontend/e2e/phase4-advanced-capabilities.spec.ts
  modified: []
key-decisions:
  - "Sandbox admission rejects every missing or inconclusive launcher capability before any child spawn."
  - "Wave 0 browser contracts are explicit expected failures so implementation cannot be mistaken for complete before the UI exists."
requirements-completed: [SAFE-02, ADV-01, ADV-02, ADV-03, SAFE-01]
coverage:
  - id: SAFE-02-SANDBOX-RED-CONTRACT
    description: Hostile strategy source, isolation capability, resource termination, cleanup, and redacted audit behavior are specified before production sandbox code exists.
    requirement: SAFE-02
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_sandbox.py -q
        status: fail
    human_judgment: true
    rationale: The advanced sandbox module is intentionally absent in Wave 0; 21 deterministic failures are the RED implementation contract.
  - id: PHASE-04-UI-RED-CONTRACT
    description: Six fixture-only browser scenarios define viewpoint, experiment, promotion, authorization, sandbox, keyboard, and responsive acceptance behavior.
    requirement: ADV-01
    verification:
      - kind: e2e
        ref: cd frontend && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium
        status: pass
    human_judgment: true
    rationale: Playwright passes because all six scenarios are deliberately marked expected-fail until later Phase 4 UI/API wiring removes those markers.
metrics:
  duration: 6m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 03: Fail-Closed Sandbox and Advanced UI RED Contracts Summary

**A 21-case hostile sandbox matrix and six fixture-backed browser scenarios now prevent Phase 4 from treating unproven isolation, undisclosed strategy code, or incomplete safe UI states as acceptable.**

## Performance

- **Duration:** 6m
- **Started:** 2026-07-12T14:07:47Z
- **Completed:** 2026-07-12T14:13:47Z
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments

- Defined fail-closed custom-strategy admission for strict contract/source hashing, hostile AST/import/file/network/process inputs, and zero host-code or research-side effects on rejection.
- Defined affirmative namespace, mount, network, governed-input, temporary-workdir, resource-limit, and cleanup probe requirements before a sandbox runner may spawn.
- Added deterministic, allowlisted fixture routes and root SSE payloads for all six Phase 4 UI-SPEC scenarios at desktop, tablet, and mobile viewports.

## Task Commits

1. **Task 1: Define fail-closed custom-strategy admission and isolated-run matrix** - `b645553` (`test`)
2. **Task 2: Define fixture-backed Phase 4 browser scenarios** - `70999ec` (`test`)

## Files Created/Modified

- `backend/tests/advanced/test_sandbox.py` - RED hostile admission, capability-proof, resource-boundary, cleanup, and safe-projection contract.
- `frontend/e2e/phase4-advanced-capabilities.spec.ts` - RED fixture-only contracts for the six approved advanced-capability UI scenarios.

## Verification

```text
cd backend && uv run python -m compileall -q tests/advanced/test_sandbox.py && uv run ruff check tests/advanced/test_sandbox.py
passed

cd backend && uv run pytest tests/advanced/test_sandbox.py -q
21 failed as expected: every failure is ModuleNotFoundError for intentionally absent app.advanced sandbox production code.

cd frontend && timeout 30s pnpm exec tsc -b --pretty false
passed

cd frontend && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium
6 passed in 28.7s: every scenario is an intentional expected failure until Phase 4 UI/API wiring exists.
```

## Decisions Made

- Isolation capability evidence is all-or-nothing: false, unavailable, or inconclusive namespace, network, file, resource, or cleanup proof must create a durable rejection before child-process spawn.
- Browser contracts use only typed local fixtures, no live market or broker calls, and make pending implementation explicit with `test.fail` markers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Made absent UI controls fail quickly inside expected-failure scenarios**
- **Found during:** Task 2 (focused Playwright verification)
- **Issue:** Two planned controls used Playwright's default 30-second locator timeout, making the intended RED result a real timeout failure.
- **Fix:** Added one-second visibility assertions before the action and geometry lookup so absent Phase 4 controls become bounded expected failures.
- **Files modified:** `frontend/e2e/phase4-advanced-capabilities.spec.ts`
- **Verification:** Focused Playwright suite completed with 6 expected-failure passes in 28.7 seconds.
- **Committed in:** `70999ec`

**Total deviations:** 1 auto-fixed (1 Rule 1 bug).
**Impact on plan:** The correction keeps the browser contract deterministic and bounded; it does not change product behavior or scope.

## Known Stubs

None. Both created files are intentionally executable Wave 0 RED contracts; no placeholder implementation or empty UI data path is introduced.

## Issues Encountered

None. The missing `app.advanced` module and six expected browser failures are the required pre-implementation state.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plans 04-04 and 04-07 can implement strict DTO/repository and sandbox services against the hostile matrix, while Plans 04-10 and 04-11 can remove the browser expected-failure markers only after fixture contracts pass unchanged.

## Self-Check: PASSED

Verified `backend/tests/advanced/test_sandbox.py`, `frontend/e2e/phase4-advanced-capabilities.spec.ts`, and task commits `b645553` and `70999ec` exist. `STATE.md` and `ROADMAP.md` were intentionally not modified per execution request.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
