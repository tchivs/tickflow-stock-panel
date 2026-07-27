---
phase: 03-ai-analysis
plan: 02
subsystem: testing
tags: [langgraph, sqlite, pytest, wave-0, contracts]
requires:
  - phase: 03-01
    provides: Human approval for the exact LangGraph dependency pair.
provides:
  - Exact LangGraph and SQLite checkpointer lock resolution with an async fixed-graph smoke test.
  - Offline RED contracts for evidence, graph, report service, lifecycle, and analysis API invariants.
affects: [03-04, 03-05, 03-06, 03-07]
tech-stack:
  added: [langgraph==1.2.9, langgraph-checkpoint-sqlite==3.1.0]
  patterns: [fixed two-node graph, server-owned evidence and reviewer contracts, append-only lifecycle contracts]
key-files:
  created:
    - backend/tests/test_analysis_evidence.py
    - backend/tests/test_analysis_graph.py
    - backend/tests/test_analysis_service.py
    - backend/tests/test_analysis_lifecycle.py
    - backend/tests/test_analysis_api.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
key-decisions:
  - "Use the approved exact LangGraph package pair and keep the existing direct OpenAI SDK boundary; do not add langchain-openai."
  - "Keep Wave 0 domain contracts intentionally RED until plans 03-04 through 03-07 provide app.analysis implementations."
patterns-established:
  - "Analysis tests use temporary SQLite paths, inline Pydantic fixtures, and injected offline collaborators only."
  - "Lifecycle confirmation contracts reject browser-supplied reviewers and require a server-resolved principal."
requirements-completed: [ANLY-01, ANLY-02, ANLY-03]
coverage:
  - id: D1
    description: "Exact LangGraph SQLite dependency lock and asynchronous fixed-topology smoke test."
    requirement: ANLY-02
    verification:
      - kind: integration
        ref: "cd backend && uv lock --check && uv run python async SQLite StateGraph smoke"
        status: pass
    human_judgment: false
  - id: D2
    description: "Offline Wave 0 evidence, graph, service, lifecycle, and API contracts."
    requirement: ANLY-01
    verification:
      - kind: unit
        ref: "backend/tests/test_analysis_*.py"
        status: fail
    human_judgment: true
    rationale: "The contracts are intentionally RED until the later plans create app.analysis."
duration: 4min
completed: 2026-07-12
status: complete
---

# Phase 03 Plan 02: Analysis Wave 0 Contracts Summary

**LangGraph 1.2.9 with SQLite checkpoint persistence plus offline RED contracts for evidence, bounded generation, and human-governed lifecycle transitions.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-12T04:06:19Z
- **Completed:** 2026-07-12T04:10:38Z
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- Pinned the approved `langgraph==1.2.9` and `langgraph-checkpoint-sqlite==3.1.0` dependencies with a reproducible `uv.lock` resolution, without `langchain-openai`.
- Proved an async `AsyncSqliteSaver` graph with exactly `START -> validate_frozen_input -> generate_validated_body -> END` accepts a server-provided `thread_id` and completes successfully.
- Added five isolated Wave 0 contract modules covering deterministic evidence, fixed graph topology, auditable report generation, immutable lifecycle transitions, and trusted reviewer API handling.

## Task Commits

1. **Task 1: Lock approved graph dependencies and prove SQLite saver support** - `d7d794f` (chore)
2. **Task 2: Add analysis-domain Wave 0 failing-first contracts** - `e391ed2` (test)

## Files Created/Modified

- `backend/pyproject.toml` - Adds only the approved exact LangGraph dependencies.
- `backend/uv.lock` - Resolves the compatible LangGraph, SQLite saver, and transitives.
- `backend/tests/test_analysis_evidence.py` - A/B/C grading, independence, normalization, conflict, and insufficient-context contracts.
- `backend/tests/test_analysis_graph.py` - Exact two-node topology, server `thread_id`, and fail-closed output contracts.
- `backend/tests/test_analysis_service.py` - Single active run, citation failure audit, and immutable version contracts.
- `backend/tests/test_analysis_lifecycle.py` - Attributable proposal, trusted reviewer confirmation, immutable plan, and rejection contracts.
- `backend/tests/test_analysis_api.py` - Scoped routes and rejection of browser-injected reviewer identity.

## Decisions Made

- Used the approved exact dependency pair and retained the established direct OpenAI-compatible SDK seam; `langchain-openai` was not introduced.
- Preserved the planned RED state for domain contracts so subsequent plans receive precise failing feedback instead of placeholder production code.

## Deviations from Plan

None - plan executed as specified. The plan's async SQLite graph behavior was verified directly.

## Issues Encountered

- The plan's synchronous `SqliteSaver(sqlite3.connect(":memory:"))` verification snippet raises `sqlite3.ProgrammingError` under the current Python 3.14 runtime because LangGraph performs checkpoint work on another thread. The required async path using `AsyncSqliteSaver` passed; the equivalent sync smoke also passes with `sqlite3.connect(":memory:", check_same_thread=False)`. Production plan 03-05 uses the async graph path.
- `cd backend && uv run pytest tests/test_analysis_evidence.py tests/test_analysis_graph.py tests/test_analysis_service.py tests/test_analysis_lifecycle.py tests/test_analysis_api.py -q` reports 22 expected RED failures, all `ModuleNotFoundError: app.analysis`, because the planned public domain package does not exist until 03-04 through 03-07.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 03-04 through 03-07 can now implement each public `app.analysis` boundary against a focused offline contract.
- Retain `AsyncSqliteSaver` for the asynchronous application graph; do not copy the synchronous in-memory smoke without configuring SQLite for cross-thread use.

---

*Phase: 03-ai-analysis*
*Completed: 2026-07-12*

## Self-Check: PASSED

- Verified all two modified dependency files, five created Wave 0 test files, and this summary exist.
- Verified task commits `d7d794f` and `e391ed2` exist in Git history.
