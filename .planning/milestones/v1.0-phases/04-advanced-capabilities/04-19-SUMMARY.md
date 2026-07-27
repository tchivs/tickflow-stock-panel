---
phase: 04-advanced-capabilities
plan: "19"
subsystem: testing
tags: [fastapi, playwright, sse, sqlite, authorization]
requires:
  - phase: 04-15
    provides: authorized advanced-job lifecycle and safe terminal sandbox contracts
  - phase: 04-16
    provides: scoped immutable viewpoint APIs and policy persistence
  - phase: 04-17
    provides: governed experiment execution and evolution evidence
  - phase: 04-18
    provides: advanced research workspace browser workflows
provides:
  - deployment-owned, schema-validated advanced host fixture support for production FastAPI lifespan tests
  - real-host browser coverage for authorized, unauthenticated, out-of-scope, rate-limited, and pre-execution-revoked advanced jobs
  - spawn-serializable strategy backtest collaborator reconstruction and bounded fixture runner startup budget
affects: [ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02, advanced-research, host-acceptance]
tech-stack:
  added: []
  patterns:
    - production lifespan reads optional deployment-owned host fixtures fail-closed and continues to use persisted policy, authorization, scope, and job services
    - spawned governed experiment workers reconstruct non-serializable collaborators from a serializable data-directory reference
key-files:
  created: []
  modified:
    - backend/app/main.py
    - backend/app/advanced/jobs.py
    - backend/app/advanced/repository.py
    - backend/app/advanced/governed_runner.py
    - backend/tests/advanced/test_production_host.py
    - backend/tests/advanced/test_experiments.py
    - frontend/e2e/phase4-advanced-capabilities.host.spec.ts
key-decisions:
  - "The advanced host fixture is deployment-owned, allowlisted, and validates its policy, subject scope, revocation task types, and 15–60 second runner wall-clock setting before startup."
  - "Fixture-only pre-execution revocation is installed as a server-side job lifecycle hook rather than a public browser/API revoke surface."
  - "Strategy experiment workers receive only the data directory and rebuild governed data/backtest dependencies after process spawn."
patterns-established:
  - "Real-host rejection coverage: authenticate through production routes, create jobs through the browser request client, and observe root SSE without route interception."
  - "Policy-revision reuse: append immutable viewpoint versions against an existing policy record by fingerprint or revision."
requirements-completed: [ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02]
coverage:
  - id: D1
    description: Deployment-owned advanced host fixture loads persisted policy and explicit subject scope into the production FastAPI lifespan.
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py#test_main_host_loads_and_persists_deployment_owned_advanced_fixture
        status: unknown
    human_judgment: true
    rationale: "The recovered commit history records the test addition but no executed test result."
  - id: D2
    description: A real FastAPI host browser spec exercises authorized root-SSE progress plus unauthenticated, out-of-scope, and rate-limited job rejection paths without route interception.
    requirement: SAFE-02
    verification:
      - kind: e2e
        ref: frontend/e2e/phase4-advanced-capabilities.host.spec.ts
        status: unknown
    human_judgment: true
    rationale: "The recovered commit history records the browser assertions but no Playwright result."
  - id: D3
    description: A fixture-selected queued strategy-evaluation job is revoked immediately before execution and persists a rejected job with safe audit data.
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py#test_main_host_fixture_revokes_selected_job_before_execution
        status: unknown
    human_judgment: true
    rationale: "The recovered commit history records the host assertion but no executed test result."
  - id: D4
    description: Strategy backtest experiment collaborators remain spawn-serializable by reconstructing governed services from a data directory in the child worker.
    requirement: ADV-02
    verification:
      - kind: unit
        ref: backend/tests/advanced/test_experiments.py#test_strategy_backtest_collaborator_is_spawn_serializable_without_duckdb_connection
        status: unknown
    human_judgment: true
    rationale: "The recovered commit history records the serialization assertion but no executed test result."
metrics:
  duration: 37m
  completed: 2026-07-13
status: complete
---

# Phase 04 Plan 19: Real-Host Advanced Acceptance Summary

**Production FastAPI lifespan can load a governed advanced fixture for real-host authorization, rejection, root-SSE, and bounded spawned-run coverage without browser route interception.**

## Performance

- **Duration:** 37 min
- **Started:** 2026-07-13T08:09:48+04:00
- **Completed:** 2026-07-13T08:47:01+04:00
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- Added an optional `ADVANCED_HOST_FIXTURE` lifespan seam that reads only a schema-validated deployment fixture, boots and persists the existing advanced policy, restricts server-derived instrument scope, and accepts only a bounded 15–60 second fixture runner wall-clock setting.
- Added real-host Playwright scenarios that start `app.main:app` with temporary governed data and fixture files, authenticate via production routes, use the root SSE stream, and cover authorized, unauthenticated, out-of-scope, rate-limited, and fixture-revoked job paths.
- Added pre-execution fixture revocation to the server job lifecycle, policy-record reuse for subsequent viewpoint appends, and a serializable strategy backtest collaborator that reconstructs its governed services in the spawned worker.

## Task Commits

1. **Task 1: 为真实 lifespan 构建可控但非拦截的 advanced acceptance fixture** - `13e1378` (test RED), `d0efc2c` (feat GREEN), `2d93139` (feat), `1acd3e4` (fix), `add44cb` (fix), `4952856` (feat)
2. **Task 2: 覆盖四条 Roadmap truth 与所有真实主机拒绝边界** - `e2ce267` (test RED), `c21c201` (feat GREEN), `9ce3136` (test)

_Note: The nine `04-19` commits form one linear range from `13e1378` through `9ce3136`; this recovery adds no implementation commit._

## Verification

No formatter, linter, build, or test command was run during this recovery closeout, per the explicit instruction. The commit history contains test additions but no recorded command result; coverage statuses above are therefore `unknown` rather than claimed as passing.

## Files Created/Modified

- `backend/app/main.py` - Loads and validates the deployment-owned advanced fixture, installs scoped policy/authorization state and optional pre-execution revocation, and passes the bounded wall-clock setting to the governed experiment runner.
- `backend/app/advanced/jobs.py` - Provides the server-side pre-execution hook before authorization revalidation.
- `backend/app/advanced/repository.py` - Reuses a persisted policy record by fingerprint or revision when appending a viewpoint version.
- `backend/app/advanced/governed_runner.py` - Reconstructs governed backtest collaborators inside spawned worker processes from the data directory.
- `backend/tests/advanced/test_production_host.py` - Covers fixture persistence, scoped rejection, revocation before execution, safe audit projection, and related host behavior.
- `backend/tests/advanced/test_experiments.py` - Asserts the strategy backtest collaborator can be pickle-serialized without a live data connection.
- `frontend/e2e/phase4-advanced-capabilities.host.spec.ts` - Starts the production FastAPI host with fixture data and asserts real-host job/SSE success and rejection paths.

## Decisions Made

- Kept the fixture at the deployment/lifespan boundary: no FastAPI route override, browser policy-editing surface, or direct browser database/service call was added.
- Applied fixture revocation after enqueue but immediately before `run_authorized_job` revalidation so the durable rejected job and sanitized audit path use the normal job service.
- Preserved production runner defaults when no fixture is configured; the fixture may only select the bounded wall-clock budget.

## Deviations from Plan

### Evidence Limitations

**1. Recovery closeout has no recorded execution output for the planned verification commands**
- **Found during:** Summary reconstruction
- **Issue:** The complete `04-19` commit range contains source and test commits, but no committed or otherwise available result for the plan's backend, TypeScript, or Playwright verification commands.
- **Fix:** Did not fabricate passing test, build, or browser claims; all summary coverage is marked `unknown` and requires human verification.
- **Files modified:** `04-19-SUMMARY.md`
- **Verification:** Not run by instruction.
- **Committed in:** Recovery summary commit.

**2. The recovered browser host spec demonstrates job/SSE acceptance and rejection scenarios, not all four broad Phase 4 success workflows named in the plan**
- **Found during:** Summary reconstruction
- **Issue:** The committed `frontend/e2e/phase4-advanced-capabilities.host.spec.ts` contains four job/SSE-focused tests and does not contain the plan's described end-to-end viewpoint, experiment/evolution-promotion, or sandbox UI success-flow assertions.
- **Fix:** Limited the accomplishments and coverage descriptions to the behavior present in the recovered commits; no missing workflow implementation was added in this recovery.
- **Files modified:** `04-19-SUMMARY.md`
- **Verification:** Source inspection only; no tests run by instruction.
- **Committed in:** Recovery summary commit.

---

**Total deviations:** 2 evidence limitations.
**Impact on plan:** The summary accurately closes out the existing commit range while preserving the distinction between committed host-rejection coverage and unproven or uncommitted broader acceptance claims.

## Issues Encountered

None during recovery. Existing unrelated worktree changes were preserved and excluded from the summary commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 19 is documented as completed from its existing production commits. Any future verification should run the plan's focused backend and `phase4-fastapi-host` commands before treating the unknown coverage entries as passing.

## Self-Check: PASSED

Verified the summary against the linear `04-19` commit range `13e1378` through `9ce3136`, its changed-file metadata and messages, the Plan 19 requirements, and current committed host/source artifacts. No validation commands were run.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-13*
