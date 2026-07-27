---
phase: 03-ai-analysis
plan: 05
subsystem: ai-analysis
tags: [langgraph, sqlite, pydantic, async, audit]
requires:
  - phase: 03-04
    provides: frozen governed evidence and immutable analysis persistence
provides:
  - fixed two-node LangGraph generation pipeline with SQLite checkpoints
  - validated server-owned report envelopes and bounded generation audit trail
affects: [03-06, 03-07, 03-08, 03-09]
tech-stack:
  added: []
  patterns: [fixed async LangGraph facade, strict Pydantic model boundary, sanitized terminal-run audit]
key-files:
  created: [backend/app/analysis/model_adapter.py, backend/app/analysis/graph.py, backend/app/analysis/service.py]
  modified: [backend/app/analysis/schemas.py, backend/app/analysis/repository.py, backend/app/operational/migrations.py, backend/tests/test_analysis_graph.py, backend/tests/test_analysis_service.py]
key-decisions:
  - "Graph execution opens AsyncSqliteSaver per invocation so async ainvoke retains durable thread checkpoints without a process-global connection."
  - "Lifecycle remains a read-only fallback snapshot; lifecycle mutation integration is intentionally deferred to Plan 03-09."
requirements-completed: [ANLY-01, ANLY-02]
coverage:
  - id: D1
    description: Fixed two-node graph validates frozen inputs and model-generated JSON before output.
    requirement: ANLY-02
    verification:
      - kind: unit
        ref: "cd backend && uv run pytest tests/test_analysis_graph.py -q"
        status: pass
    human_judgment: false
  - id: D2
    description: Server orchestration freezes evidence, preserves one active run, validates envelopes, and audits terminal failures.
    requirement: ANLY-01
    verification:
      - kind: unit
        ref: "cd backend && uv run pytest tests/test_analysis_graph.py tests/test_analysis_service.py -q"
        status: pass
    human_judgment: false
duration: 7m 8s
completed: 2026-07-12
status: complete
---

# Phase 03 Plan 05: Fixed Validated Analysis Generation Summary

**Fixed two-node LangGraph generation with strict Pydantic output, frozen-evidence citation validation, and immutable SQLite-backed audit records.**

## Performance

- **Duration:** 7m 8s
- **Started:** 2026-07-12T04:32:13Z
- **Completed:** 2026-07-12T04:39:21Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Added a server-built-message analysis adapter with temperature zero, fixed timeout/token caps, injected async transport, and fail-closed `GeneratedAnalysis` parsing.
- Added the only permitted graph topology: `START -> validate_frozen_input -> generate_validated_body -> END`, using an async persistent SQLite saver and server-issued `thread_id`.
- Added `AnalysisService` orchestration for scoped run acquisition, evidence freezing, bounded validation retries, second envelope validation, immutable version writes, and sanitized success/failure audit metadata.

## Task Commits

1. **Task 1: 构建严格模型适配器与固定两节点图** - `196c1c0` (`feat`)
2. **Task 2: 编排单活动生成和双重验证持久化** - `5666764` (`feat`)
3. **Task 2 follow-up: retain safe failure audit metadata** - `68daac6` (`fix`)

## Files Created/Modified

- `backend/app/analysis/model_adapter.py` - Fixed server prompt and strict async structured-output adapter.
- `backend/app/analysis/graph.py` - Persistent fixed-topology graph facade with required server thread IDs.
- `backend/app/analysis/service.py` - Evidence-to-report orchestration and terminal audit handling.
- `backend/app/analysis/schemas.py` - Server report envelope carries generation audit metadata.
- `backend/app/analysis/repository.py` and `backend/app/operational/migrations.py` - Persist sanitized terminal-run metadata.
- `backend/tests/test_analysis_graph.py` and `backend/tests/test_analysis_service.py` - Offline graph, validation, envelope, and audit contracts.

## Decisions Made

- Used `AsyncSqliteSaver` within each graph invocation because asynchronous LangGraph execution cannot use `SqliteSaver`; checkpoints persist by the server-generated run ID without retaining a process-global connection.
- Kept lifecycle integration out of this plan. The service accepts an optional read-only lifecycle snapshot loader and uses a deterministic fallback snapshot until Plan 03-09 owns lifecycle integration.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Replaced synchronous SQLite saver in async graph execution**
- **Found during:** Task 1
- **Issue:** `SqliteSaver` raises `NotImplementedError` when LangGraph executes via `ainvoke`.
- **Fix:** Wrapped the fixed graph with an `AsyncSqliteSaver` opened for each invocation.
- **Files modified:** `backend/app/analysis/graph.py`
- **Verification:** `uv run pytest tests/test_analysis_graph.py -q`
- **Committed in:** `196c1c0`

**2. [Rule 2 - Missing Critical] Added sanitized terminal-run audit metadata**
- **Found during:** Task 2
- **Issue:** Existing run records held only a failure reason and could not retain bounded attempts, adapter/model identity, versions, timing, and frozen-evidence fingerprint.
- **Fix:** Added an `audit_metadata_json` migration and repository support; report envelopes and terminal failures now retain safe reproducibility metadata without raw prompts, evidence, or provider responses.
- **Files modified:** `backend/app/analysis/schemas.py`, `backend/app/analysis/repository.py`, `backend/app/analysis/service.py`, `backend/app/operational/migrations.py`
- **Verification:** `uv run pytest tests/test_analysis_graph.py tests/test_analysis_service.py -q`
- **Committed in:** `5666764`, `68daac6`

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical functionality).
**Impact on plan:** Both changes are required for the planned async persistence and auditable failure handling; no lifecycle integration or additional generation capabilities were introduced.

## Issues Encountered

- The Wave 0 graph/service contracts were already committed by the prior 03-02 RED wave; this plan implemented and extended those contracts rather than duplicating the RED commit.

## User Setup Required

None - no external service configuration required. Live provider calls remain outside tests through the injected async transport seam.

## Next Phase Readiness

- Plans 03-06 through 03-08 can use the strict graph/service boundary and immutable report history.
- Plan 03-09 should supply the lifecycle snapshot loader and lifecycle mutation integration; it was deliberately not implemented here.

## Self-Check: PASSED

- Created files exist: `backend/app/analysis/model_adapter.py`, `backend/app/analysis/graph.py`, `backend/app/analysis/service.py`.
- Task commits exist: `196c1c0`, `5666764`, `68daac6`.
