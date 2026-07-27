---
phase: 03-ai-analysis
plan: 09
subsystem: lifecycle-governance
tags: [sqlite, lifecycle, evidence, audit, tdd]
requires:
  - phase: 03-05
    provides: immutable completed analysis runs, reports, and frozen evidence snapshots
  - phase: 03-06
    provides: deterministic lifecycle proposal and human confirmation services
provides:
  - post-completion evaluation from persisted frozen server evidence to attributable review proposals
  - idempotent proposal persistence for retried completed-analysis evaluation
  - application lifecycle wiring for non-authoritative proposal evaluation
affects: [03-08, analysis-api, lifecycle-history]
tech-stack:
  added: []
  patterns: [post-persistence evaluation, deterministic proposal keys, server-derived lifecycle state]
key-files:
  created: []
  modified: [backend/app/analysis/service.py, backend/app/analysis/lifecycle.py, backend/app/analysis/repository.py, backend/app/main.py, backend/tests/test_analysis_service.py, backend/tests/test_analysis_lifecycle.py]
key-decisions:
  - "Lifecycle evaluation runs only after the immutable report and completed terminal run are persisted."
  - "Proposal keys are deterministic over run, report, and frozen snapshot attribution so retries return the same append-only review."
  - "Proposal evaluation cannot call confirmation or append official lifecycle events."
requirements-completed: [ANLY-03]
coverage:
  - id: D1
    description: Persisted successful frozen analysis creates an attributable lifecycle review proposal while official state remains unchanged.
    requirement: ANLY-03
    verification:
      - kind: unit
        ref: "cd backend && uv run pytest tests/test_analysis_service.py tests/test_analysis_lifecycle.py -q"
        status: pass
    human_judgment: false
  - id: D2
    description: Failed or repeated analysis completion creates no extra proposal or official lifecycle event.
    requirement: ANLY-03
    verification:
      - kind: unit
        ref: "backend/tests/test_analysis_service.py; backend/tests/test_analysis_lifecycle.py"
        status: pass
    human_judgment: false
metrics:
  duration: 6m
  completed_date: 2026-07-12
status: complete
---

# Phase 03 Plan 09: Completed Analysis Lifecycle Proposals Summary

Successful immutable analysis runs now create only evidence-attributed, idempotent lifecycle review proposals; official lifecycle state remains exclusively human-confirmed.

## Performance

- **Duration:** 6m
- **Completed:** 2026-07-12T05:07:23Z
- **Tasks:** 1/1
- **Files modified:** 6

## Accomplishments

- Connected the only successful report persistence path to a post-completion lifecycle evaluation collaborator.
- Re-read completed run, immutable report, frozen evidence snapshot, and repository-derived official state before proposing a transition.
- Persisted run, report, and snapshot attribution on eligible proposals while preserving the existing human confirmation-only event path.
- Added regression coverage for successful attribution, no official transition, failed generation, source-repeat ineligibility, and duplicate evaluation idempotency.

## Task Commits

1. **Task 1 RED: 从成功完成的冻结分析评估并记录生命周期提案** - `5867cb3` (`test`)
2. **Task 1 GREEN: 从成功完成的冻结分析评估并记录生命周期提案** - `1adae25` (`feat`)

## Files Created/Modified

- `backend/app/analysis/service.py` - Invokes proposal evaluation only after report and completed-run persistence.
- `backend/app/analysis/lifecycle.py` - Reconstructs attributable frozen evidence and derives review-only proposals.
- `backend/app/analysis/repository.py` - Returns an existing deterministic proposal and exposes scoped review history.
- `backend/app/main.py` - Supplies the existing lifecycle service to the analysis service.
- `backend/tests/test_analysis_service.py` and `backend/tests/test_analysis_lifecycle.py` - Exercise success, failure, repeat, attribution, and official-state boundaries.

## Decisions Made

- Kept lifecycle-state derivation repository-owned and evaluated only server-persisted IDs; model prose and live/browser inputs do not participate.
- Used deterministic UUIDv5 review IDs over immutable run/report/snapshot attribution to make completed-analysis retries idempotent without update paths.
- Preserved invalidation conditions in proposal evidence so later human confirmation can recheck the same rule inputs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added repository idempotency and application collaborator wiring**
- **Found during:** Task 1 GREEN implementation
- **Issue:** The existing repository appended every proposal and the lifespan-created `AnalysisService` did not receive the existing `LifecycleRuleService`, so retry safety and the live integration path were incomplete.
- **Fix:** Added deterministic review-ID reuse in the repository and injected the rule service at application assembly.
- **Files modified:** `backend/app/analysis/repository.py`, `backend/app/main.py`
- **Verification:** Focused service/lifecycle tests pass, including repeat evaluation assertions.
- **Committed in:** `1adae25`

**2. [Rule 1 - Bug] Persisted invalidation conditions with proposal evidence**
- **Found during:** Task 1 GREEN implementation
- **Issue:** Falsification proposals accepted recorded invalidation conditions but omitted them from immutable review evidence, preventing confirmation-time revalidation of that rule input.
- **Fix:** Store validated invalidation conditions in the proposal evidence payload.
- **Files modified:** `backend/app/analysis/lifecycle.py`, `backend/tests/test_analysis_lifecycle.py`
- **Verification:** `uv run pytest tests/test_analysis_lifecycle.py -q`
- **Committed in:** `1adae25`

**Total deviations:** 2 auto-fixed (1 missing critical functionality, 1 bug).
**Impact on plan:** Both changes enforce the specified post-persistence, append-only, human-confirmed lifecycle boundary without expanding lifecycle authority.

## Issues Encountered

- Full-file Ruff checking of `backend/app/main.py` reports pre-existing import/comment violations outside this plan's one-line assembly change. The changed analysis modules and tests pass Ruff; `main.py` compiles successfully.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The review API and Phase 03 UI can now surface proposals that are tied to immutable analysis evidence without implying an official state transition.
- Price/event-context and recorded invalidation-condition sources remain eligible only when provided by server-owned lifecycle inputs; model prose is not used to create such proposals.

## Self-Check: PASSED

- Found `.planning/phases/03-ai-analysis/03-09-SUMMARY.md`.
- Found task commits `5867cb3` and `1adae25`.
