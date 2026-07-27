---
phase: 04-advanced-capabilities
plan: "27"
subsystem: authorization
tags: [sqlite, authorization, policy, rate-limits, fastapi, sse, pytest]
requires:
  - phase: 04-advanced-capabilities
    provides: immutable authorization policy facts, task-specific rate windows, and scoped advanced-progress delivery
provides:
  - transactional denial when authorization and persisted current policy revisions differ at quota acquisition
  - execution-start rejection for queued jobs whose authorization policy changed after queueing
  - unit and real-lifespan A-to-B policy-transition regression coverage
affects: [SAFE-01, advanced jobs, operator policy, scoped authorization, advanced progress SSE]
tech-stack:
  added: []
  patterns:
    - acquisition joins immutable authorization provenance to the supplied current policy before a rate-window write
    - queued jobs resolve durable authorization provenance before any current-policy quota inspection or workflow activity
key-files:
  created:
    - .planning/phases/04-advanced-capabilities/04-27-SUMMARY.md
  modified:
    - backend/app/advanced/repository.py
    - backend/app/advanced/jobs.py
    - backend/tests/advanced/test_authorization_jobs.py
    - backend/tests/advanced/test_production_host.py
key-decisions:
  - "A policy revision mismatch fails closed at both queue acquisition and execution start; historical consumption is never moved to a replacement policy window."
  - "Policy-transition denials use one sanitized reason and do not publish advanced-progress events."
patterns-established:
  - "Policy provenance is resolved from the durable job-to-authorization lineage, never inferred from the current policy."
requirements-completed: [SAFE-01]
coverage:
  - id: D1
    description: "An authorization created under revision A cannot acquire a quota charge or queued job after persisted policy B becomes current."
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: "backend/tests/advanced/test_authorization_jobs.py#test_policy_transition_denies_authorization_before_quota_acquisition"
        status: pass
    human_judgment: false
  - id: D2
    description: "A queued job correctly charged under A is rejected before B quota inspection, work, or advanced progress after policy B becomes current."
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: "backend/tests/advanced/test_authorization_jobs.py#test_policy_transition_rejects_queued_job_before_current_policy_quota_or_work"
        status: pass
      - kind: integration
        ref: "backend/tests/advanced/test_production_host.py#test_main_host_policy_transition_rejects_preserved_queued_job_without_progress"
        status: pass
    human_judgment: false
  - id: D3
    description: "Stable-policy task buckets retain independent quota behavior and reject exhausted work before collaborators or progress publication."
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: "backend/tests/advanced/test_authorization_jobs.py#test_asymmetric_task_quotas_reject_without_work_or_progress_and_leave_research_capacity"
        status: pass
    human_judgment: false
metrics:
  duration: 7m 18s
  completed: 2026-07-14
status: complete
---

# Phase 04 Plan 27: Policy-Transition Quota Closure Summary

**Advanced job authorization now fails closed across deployment policy revisions: A-issued authority cannot charge under B, and a correctly queued A job rejects before any B inspection, work, or SSE activity.**

## Performance

- **Duration:** 7m 18s
- **Started:** 2026-07-14T07:16:46Z
- **Completed:** 2026-07-14T07:24:04Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Added an atomic acquisition provenance join that requires an authorization's immutable policy revision to equal the supplied persisted current policy before rate-window consumption or job insertion.
- Added execution-start durable provenance revalidation before `quota_is_current`, blocking queued A work after policy B becomes current without reassigning its original accounting.
- Added focused unit regressions for issuance-to-acquisition and queued-execution policy transitions, plus a two-lifespan FastAPI regression over one operational SQLite database with scoped SSE proof.
- Retained stable-policy asymmetric task-bucket behavior and its independent capacity regression.

## Task Commits

1. **Task 1: Fail closed at policy-consistent quota acquisition and queued execution start (RED)** — `4bb6974` (`test`)
2. **Task 1: Fail closed at policy-consistent quota acquisition and queued execution start (GREEN)** — `7e41dfa` (`feat`)
3. **Task 2: Prove queued A-to-B denial through real application lifespans** — `92076a5` (`test`)

## Files Created/Modified

- `backend/app/advanced/repository.py` — Atomically proves authorization/current-policy equivalence before charging and resolves queued-job policy provenance.
- `backend/app/advanced/jobs.py` — Rejects revision mismatches before quota inspection and maps them to the sanitized policy-transition reason.
- `backend/tests/advanced/test_authorization_jobs.py` — Covers both policy-transition temporal boundaries and no-work/no-progress behavior.
- `backend/tests/advanced/test_production_host.py` — Proves preserved A accounting, empty B accounting, no governed activity, and no scoped SSE over two real lifespans.

## Decisions Made

- Authorization-linked policy provenance remains the sole possible rate-window owner, and is used only after it matches the current persisted policy in the same acquisition transaction.
- A revision transition is a safe durable rejection requiring fresh server authorization; it never transfers, resets, merges, or reinterprets historical accounting.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Task 1 RED coverage failed as expected before the runtime change: an A authorization could acquire under B and an A queued job could reach the authorized state under B.
- The real-lifespan regression exercised existing Polars deprecation/sortedness warnings; focused verification passed and no warning represented a behavioral failure.

## Verification

```text
cd backend && timeout 30s uv run pytest tests/advanced/test_authorization_jobs.py tests/advanced/test_production_host.py -q -k 'policy_transition or policy_acquisition or asymmetric_task_quotas or worker_revalidates'
5 passed, 23 deselected in 9.57s
```

## Known Stubs

None. The modified runtime path reads persisted policy and authorization facts, and the new regressions exercise real SQLite lifecycle state and scoped progress queues.

## Threat Flags

None. This plan narrows existing authorization and queue/execution boundaries without adding an endpoint, datastore, external service, or new trust surface.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

SAFE-01 now has atomic policy-consistent acquisition and fail-closed queued execution semantics, evidenced at both unit and real-lifespan boundaries.

## Self-Check: PASSED

- Summary and all four modified runtime/test files exist.
- Task commits `4bb6974`, `7e41dfa`, and `92076a5` resolve as commits.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-14*
