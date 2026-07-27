---
phase: 03-ai-analysis
plan: 11
subsystem: analysis-api
tags: [fastapi, sqlite, dto, projections, lifecycle, authentication]
requires:
  - phase: 03-10
    provides: governed immutable reports, evidence snapshots, and authenticated host execution
provides:
  - allowlisted display DTOs for reports and frozen evidence
  - server-issued signal IDs for completed-report detail views
  - authorized lifecycle history with reviews, immutable plans, and outcomes
affects: [03-12, analysis-ui, lifecycle-history]
tech-stack:
  added: []
  patterns: [storage-to-display projection, subject-scoped opaque-ID resolution, append-only lifecycle read model]
key-files:
  created: [backend/app/analysis/projections.py]
  modified: [backend/app/analysis/api.py, backend/app/analysis/repository.py, backend/tests/test_analysis_api.py, backend/tests/test_analysis_host_integration.py]
key-decisions:
  - "Analysis API responses use an explicit allowlisted projection instead of raw SQLite records or nested snapshots."
  - "A completed report obtains its signal ID only after report-to-subject authorization; legacy persisted reports receive a signal without any lifecycle transition."
  - "Rejected proposals are inferred from their append-only rejection record, while official state remains derived only from confirmed events."
patterns-established:
  - "Presentation mapper: transform immutable records into frontend DTOs without recomputing grades, validation, or official lifecycle state."
  - "Lifecycle projection: expose proposal, confirmation/rejection, plan, and outcome history without reviewer principals or raw evidence payloads."
requirements-completed: [ANLY-01, ANLY-02, ANLY-03]
coverage:
  - id: D1
    description: "Authenticated report list, detail, and evidence resources return the frontend display DTO rather than storage envelopes."
    requirement: ANLY-01
    verification:
      - kind: unit
        ref: "backend/tests/test_analysis_api.py#test_analysis_api_returns_allowlisted_report_evidence_and_lifecycle_display_dtos"
        status: pass
      - kind: integration
        ref: "backend/tests/test_analysis_host_integration.py#test_authenticated_main_host_completes_governed_analysis_and_persists_immutable_artifacts"
        status: pass
    human_judgment: false
  - id: D2
    description: "Validated report reasoning, score dimensions, valuation, IC memo, and evidence limitations are projected from server-owned records."
    requirement: ANLY-02
    verification:
      - kind: unit
        ref: "backend/tests/test_analysis_api.py#test_analysis_api_returns_allowlisted_report_evidence_and_lifecycle_display_dtos"
        status: pass
      - kind: integration
        ref: "backend/tests/test_analysis_host_integration.py#test_authenticated_main_host_completes_governed_analysis_and_persists_immutable_artifacts"
        status: pass
    human_judgment: false
  - id: D3
    description: "Authorized signal history exposes pending and rejected reviews, confirmed events, immutable plans, and appended outcomes."
    requirement: ANLY-03
    verification:
      - kind: integration
        ref: "backend/tests/test_analysis_host_integration.py#test_authenticated_main_host_completes_governed_analysis_and_persists_immutable_artifacts"
        status: pass
      - kind: unit
        ref: "backend/tests/test_analysis_lifecycle.py"
        status: pass
    human_judgment: false
metrics:
  duration: 8m 47s
  completed_date: 2026-07-12
status: complete
---

# Phase 03 Plan 11: Analysis Display DTO Summary

Immutable reports, frozen evidence, and signal governance records now have one authorized display DTO contract consumable by the analysis UI.

## Performance

- **Duration:** 8m 47s
- **Started:** 2026-07-12T05:43:03Z
- **Completed:** 2026-07-12T05:48:50Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Added a single allowlisted mapper for report summaries/details and top-level evidence fields, excluding raw storage envelopes and internal prompt/checkpoint data.
- Connected completed reports to server-issued subject signals and preserved subject authorization before every report, signal, review, or plan projection.
- Exposed read-only lifecycle history with pending, confirmed, and rejected reviews, immutable plan windows/benchmarks/metrics, and append-only outcomes.
- Expanded the real authenticated host regression through proposal confirmation, rejection, outcome append, and subsequent projection reads.

## Task Commits

1. **Task 1 RED: 固化真实响应的 report、evidence 和 lifecycle DTO 契约** - `9df2c52` (`test`)
2. **Task 2 GREEN: 实现唯一授权展示投影并接入分析资源** - `1b8dd06` (`feat`)

## Files Created/Modified

- `backend/app/analysis/projections.py` - Explicit storage-to-display allowlist for report, evidence, and lifecycle resources.
- `backend/app/analysis/repository.py` - Subject signal lookup/creation and existing immutable lifecycle reads.
- `backend/app/analysis/api.py` - Authorized DTO responses for report, evidence, and signal history routes.
- `backend/tests/test_analysis_api.py` - RED/contract coverage for DTO shape, opaque-ID scope, and sensitive-field exclusion.
- `backend/tests/test_analysis_host_integration.py` - Real lifespan and authenticated lifecycle projection regression.

## Decisions Made

- UI display subjects map persistent `instrument`/`account` records to the declared `stock`/`portfolio` contract; route authorization still operates on persistent subject kinds.
- Display score dimensions retain each server-generated perspective score as a contribution and do not synthesize an aggregate grade.
- Rejection is projected from append-only audit records, so no historical review is rewritten.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected tests to the actual frontend response envelope contract**
- **Found during:** Task 2
- **Issue:** `frontend/src/lib/api.ts` consumes evidence and signal history as top-level DTOs, while the initial RED assertions expected an extra response wrapper.
- **Fix:** Kept report list/detail wrappers as declared and changed evidence/history assertions to their declared top-level DTO shapes.
- **Files modified:** `backend/tests/test_analysis_api.py`, `backend/tests/test_analysis_host_integration.py`
- **Verification:** Targeted API, host integration, lifecycle, and service tests pass.
- **Committed in:** `1b8dd06`

**2. [Rule 2 - Missing Critical] Preserved signal reachability for existing completed reports**
- **Found during:** Task 2
- **Issue:** Creating a signal only during new report persistence would leave historical completed reports without a reachable `signal_id` after upgrade.
- **Fix:** Added a parameterized, subject-authorized get-or-create signal path that never writes a lifecycle event or changes official state.
- **Files modified:** `backend/app/analysis/repository.py`, `backend/app/analysis/api.py`
- **Verification:** The real host returns a server-issued signal ID and reads lifecycle projections after authenticated review actions.
- **Committed in:** `1b8dd06`

**Total deviations:** 2 auto-fixed (1 contract correction, 1 missing critical continuity path).
**Impact on plan:** Both changes are necessary to make the declared API contract and existing completed data usable; no new route, write workflow, or lifecycle authority was added.

## Issues Encountered

- The established governed fixture pipeline emits three unrelated Polars deprecation/sortedness warnings during the host integration test. All requested analysis tests pass.

## Known Stubs

None. The projection uses persisted report, snapshot, review, plan, and outcome records; it does not render mock or empty display data.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03-12 can rely on the real report/evidence/history resources matching the typed UI request shapes.
- Residual risk: the frontend lifecycle type intentionally represents the persistent `active` state as `null`; this matches its current UI state-label model but should be revisited if `active` needs an explicit label.

## Self-Check: PASSED

- Found `backend/app/analysis/projections.py` and `03-11-SUMMARY.md`.
- Found task commits `9df2c52` and `1b8dd06`.
