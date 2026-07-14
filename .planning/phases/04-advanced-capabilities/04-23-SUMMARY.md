---
phase: 04-advanced-capabilities
plan: "23"
subsystem: authorization
status: complete
tags: [sqlite, authorization, rate-limits, policy, sse, pytest]
requires:
  - phase: 04-advanced-capabilities
    provides: server-owned advanced-job authorization, durable operational SQLite state, and scoped SSE projection
provides:
  - Task-type-keyed immutable SQLite rate windows with preserved legacy accounting facts
  - Exact deployment-policy quotas at job creation and pre-execution authorization gates
  - Regression coverage for asymmetric task buckets and denial-before-work/SSE behavior
affects: [advanced jobs, operator policy, scoped authorization, advanced progress SSE]
tech-stack:
  added: []
  patterns:
    - Rate-window identity is principal, policy revision, task type, and UTC hour.
    - Job creation and pre-execution revalidation use the same policy-derived task quota and durable identity.
key-files:
  created: []
  modified:
    - backend/app/advanced/repository.py
    - backend/app/advanced/authorization.py
    - backend/app/advanced/jobs.py
    - backend/app/main.py
    - backend/app/operational/migrations.py
    - backend/tests/advanced/test_authorization_jobs.py
key-decisions:
  - "Historical aggregate windows migrate to the reserved __legacy_rate_window__ identity, which current policy validation rejects."
  - "Rejected creation and pre-execution checks record durable audit state but do not publish advanced-progress SSE events."
patterns-established:
  - "Deployment policies expose immutable positive per-task quota mappings through a narrow quota_for validator."
  - "A rate-limit decision is atomic with its idempotent job lookup and queue insertion."
requirements-completed: [SAFE-01]
coverage:
  - id: D1
    description: Task-specific durable SQLite windows preserve legacy evidence, isolate research_draft, experiment, and strategy_evaluation consumption, and charge idempotent requests once.
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: backend/tests/advanced/test_authorization_jobs.py#test_rate_window_migration_preserves_legacy_accounting_under_unrunnable_identity
        status: pass
      - kind: unit
        ref: backend/tests/advanced/test_authorization_jobs.py#test_task_type_rate_windows_are_independent_and_charge_once
        status: pass
    human_judgment: false
  - id: D2
    description: Exact asymmetric policy quotas are enforced before creation and immediately before execution without provider, workflow, sandbox, runnable-work, or advanced-progress activity on denial.
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: backend/tests/advanced/test_authorization_jobs.py#test_asymmetric_task_quotas_reject_without_work_or_progress_and_leave_research_capacity
        status: pass
      - kind: unit
        ref: backend/tests/advanced/test_api_sse.py
        status: pass
    human_judgment: false
metrics:
  duration: 9m 37s
  completed: 2026-07-14
---

# Phase 04 Plan 23: Task-Specific Durable Policy Quotas Summary

**Advanced jobs now consume only their own policy-defined SQLite quota bucket at creation and execution start, while exhausted work is audited without starting workers or publishing SSE progress.**

## Performance

- **Duration:** 9m 37s
- **Started:** 2026-07-14T06:15:29Z
- **Completed:** 2026-07-14T06:25:06Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Rebuilt durable rate-window identity to include immutable task type, preserving historical aggregate rows as the reserved non-runnable `__legacy_rate_window__` identity.
- Replaced the collapsed scalar quota with immutable per-task positive quotas, retaining the configured `AdvancedPolicy.rate_limits` map when wiring server authorization.
- Applied the exact task quota and full principal/policy/task/hour identity at both atomic creation and pre-execution revalidation gates.
- Added migration, idempotency, asymmetric-bucket, and no-worker/no-SSE regressions for exhausted creation and start-time denial.

## Task Commits

1. **Task 1: Migrate SQLite rate-window identity and acquisition to include task type** — `6648ff6` (`feat`)
2. **Task 2: Carry exact AdvancedPolicy quotas through both authorization gates** — `49433b7` (`fix`)

## Files Created/Modified

- `backend/app/advanced/repository.py` — Acquires, revalidates, and counts full task-specific rate-window keys.
- `backend/app/advanced/authorization.py` — Provides immutable positive quota mappings and validated `quota_for()` lookup.
- `backend/app/advanced/jobs.py` — Uses exact quotas at creation and execution-start gates; suppresses rejected progress publication.
- `backend/app/main.py` — Preserves deployment policy rate limits without maximum aggregation.
- `backend/app/operational/migrations.py` — Adds task type to immutable window identity and migrates legacy accounting safely.
- `backend/tests/advanced/test_authorization_jobs.py` — Covers migration, idempotency, independent quotas, and denial-before-work/SSE behavior.

## Decisions Made

- A historic aggregate rate row remains durable evidence but is deliberately assigned the reserved `__legacy_rate_window__` task identity, which the live policy interface rejects.
- A rejected authorization transition remains a durable job/audit cursor but is not an SSE progress event, so no pre-work rejection leaks into the worker progress stream.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The planned TDD RED runs failed as expected before implementation: migration tests observed the absent `task_type` column and scoped-count signature; policy tests observed the absent `rate_limits` interface.

## Verification

- `cd backend && timeout 30s uv run pytest tests/advanced/test_authorization_jobs.py tests/advanced/test_api_sse.py -q` — **16 passed in 5.45s**

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

SAFE-01 task limits now retain deployment-policy asymmetry throughout durable creation and pre-execution revalidation. No external queue, second datastore, or client authorization authority was added.

## Self-Check: PASSED

- Task commits `6648ff6` and `49433b7` exist in repository history.
- All six modified runtime and test files exist.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-14*
