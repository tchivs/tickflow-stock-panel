---
phase: 04-advanced-capabilities
plan: "25"
subsystem: advanced-viewpoints
tags: [sqlite, immutable-ledger, calibration, idempotency, fastapi]
requires:
  - phase: 04-05
    provides: immutable viewpoint versions and append-only evaluation facts
  - phase: 04-16
    provides: governed evaluation collaborator and empty-body evaluation route
  - phase: 04-23
    provides: prior Phase 04 gap-closure baseline
provides:
  - deterministic first-terminal evaluation selection per immutable viewpoint version
  - idempotent terminal evaluation requests that reuse frozen ledger outcomes
  - confidence calibration that counts each version once and reports unevaluable exclusions
affects: [ADV-01, advanced-viewpoints, calibration]
tech-stack:
  added: []
  patterns:
    - canonical immutable ledger projections use created-at and stable-ID ordering
    - route retries read a frozen terminal fact before invoking governed evaluation
key-files:
  created:
    - .planning/phases/04-advanced-capabilities/04-25-SUMMARY.md
  modified:
    - backend/app/advanced/repository.py
    - backend/app/advanced/viewpoints.py
    - backend/tests/advanced/test_viewpoints.py
key-decisions:
  - "The canonical calibration observation is the first terminal fact by created_at and stable ID; the initial awaiting fact is not terminal."
  - "Unevaluable terminal facts remain auditable and are counted as explicit exclusions, never as zero-return observations."
patterns-established:
  - "One immutable viewpoint version contributes at most one terminal calibration candidate."
  - "Evaluation retries return a persisted terminal projection without re-running the governed collaborator."
requirements-completed: [ADV-01]
coverage:
  - id: D1
    description: "Calibration selects one deterministic terminal observation per immutable viewpoint version while retaining duplicate and unevaluable ledger facts."
    requirement: ADV-01
    verification:
      - kind: integration
        ref: "backend/tests/advanced/test_viewpoints.py#test_calibration_candidates_choose_one_first_terminal_fact_per_immutable_version"
        status: pass
    human_judgment: false
  - id: D2
    description: "Repeated empty-body evaluation requests reuse a frozen terminal outcome, invoke governed evaluation once, and leave confidence metrics unchanged."
    requirement: ADV-01
    verification:
      - kind: integration
        ref: "backend/tests/advanced/test_viewpoints.py#test_repeated_empty_body_evaluation_route_reuses_terminal_fact_and_stable_calibration"
        status: pass
    human_judgment: false
metrics:
  duration: 5m 14s
  completed: 2026-07-14
status: complete
---

# Phase 04 Plan 25: Canonical Viewpoint Evaluation Summary

**Immutable viewpoint versions now yield one deterministic terminal calibration observation, and repeated evaluation requests reuse that frozen fact without re-running governed inputs.**

## Performance

- **Duration:** 5m 14s
- **Started:** 2026-07-14T06:28:20Z
- **Completed:** 2026-07-14T06:33:34Z
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments

- Added deterministic repository selection of the first terminal evaluation fact per immutable viewpoint version, excluding only the initial awaiting-governed-evaluation fact.
- Added one-per-version calibration candidates so historical duplicate facts remain readable but cannot inflate count, hit rate, mean return, or coverage dates.
- Made the empty-body evaluation route idempotent through the service: after a terminal fact exists it returns the frozen outcome without invoking the governed evaluator or appending another observation.
- Preserved low/medium/high calibration buckets and insufficient-sample semantics while explicitly reporting unevaluable terminal facts as exclusions rather than zero returns.

## Task Commits

1. **Task 1: Select one canonical terminal evaluation per immutable viewpoint version** - `af1fea8` (test RED), `0608ae4` (feat GREEN)
2. **Task 2: Make terminal evaluation requests idempotent and calibrate from canonical facts** - `7d4e8a4` (test RED), `6030865` (feat GREEN)

## Files Created/Modified

- `backend/app/advanced/repository.py` - Provides canonical terminal lookup and one-per-version calibration candidates using stable deterministic ordering.
- `backend/app/advanced/viewpoints.py` - Reuses terminal outcomes before governed evaluation and aggregates only canonical candidates.
- `backend/tests/advanced/test_viewpoints.py` - Covers duplicate terminal history, stable calibration aggregates, immutable rows, and repeated public-route evaluation.

## Decisions Made

- The first evaluated or explicitly unevaluable terminal fact is canonical for a version; the append-only initial awaiting fact is intentionally excluded.
- Unevaluable terminal facts stay in the audit/calibration candidate set as exclusions, preserving uncertainty without treating them as returns.
- Duplicate terminal records already present in history are retained and deterministic selection prevents them from becoming independent evidence.

## Verification

```text
cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py -q
24 passed in 11.01s
```

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

`uv run ruff check app/advanced/repository.py app/advanced/viewpoints.py tests/advanced/test_viewpoints.py` reports two pre-existing import-order violations outside this plan's changes. They are documented in `deferred-items.md`; focused behavioral verification passes.

## Known Stubs

None. Terminal outcomes and calibration candidates are derived from persisted immutable facts; no mock or empty data path is exposed by the changed behavior.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

ADV-01's calibration projection is resistant to repeated evaluation requests and historic duplicate terminal ledger facts while retaining complete audit history.

## Self-Check: PASSED

Verified the three changed source/test files exist, the four task commits (`af1fea8`, `0608ae4`, `7d4e8a4`, and `6030865`) are present in git history, and the focused viewpoint test suite passed.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-14*
