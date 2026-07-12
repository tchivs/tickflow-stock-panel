---
phase: 03-ai-analysis
plan: 10
subsystem: analysis-production-integration
tags: [fastapi, sqlite, langgraph, evidence, authentication, integration-testing]
requires:
  - phase: 03-05
    provides: frozen evidence, immutable reports, and bounded async analysis graph
  - phase: 03-07
    provides: authenticated analysis routes and application lifecycle assembly
  - phase: 03-09
    provides: post-completion lifecycle proposal evaluation
provides:
  - governed read-only market, financial, and holdings evidence loader
  - terminal failure handling for unconfigured new analysis runs
  - authenticated real-host regression from governed fixture data to persisted report
affects: [03-11, 03-12, analysis-api, analysis-ui, lifecycle-history]
tech-stack:
  added: []
  patterns: [governed evidence adaptation, terminal configuration failure, async SQLite graph verification, authenticated host integration]
key-files:
  created: [backend/app/analysis/evidence_loader.py, backend/tests/test_analysis_host_integration.py]
  modified: [backend/app/analysis/service.py, backend/app/main.py, backend/tests/test_analysis_evidence.py, backend/tests/test_analysis_service.py, backend/tests/test_analysis_graph.py]
key-decisions:
  - "Production evidence is derived only from governed KlineRepository, local financial parquet, and OperationalRepository boundaries; client focus and notes do not become facts."
  - "Only a genuinely active queued/running run is deduplicated; a newly acquired run lacking execution collaborators is recorded as a sanitized terminal failure."
  - "Graph execution verification uses PersistentAnalysisGraph with AsyncSqliteSaver, never a cross-thread synchronous SQLite saver."
patterns-established:
  - "Governed evidence loader: normalize finite numeric repository records into provenance-bounded snapshots without raw content."
  - "Host integration: use real FastAPI lifespan and cookies while injecting only the configured provider transport seam."
requirements-completed: [ANLY-01, ANLY-02, ANLY-03]
coverage:
  - id: D1
    description: "Production analysis builds read-only A/B/C-capable evidence records from governed market, financial, and account boundaries."
    requirement: ANLY-01
    verification:
      - kind: unit
        ref: "backend/tests/test_analysis_evidence.py#test_governed_evidence_loader_uses_only_repository_financial_and_operational_boundaries"
        status: pass
    human_judgment: false
  - id: D2
    description: "A newly authorized analysis request either completes through the fixed graph or records a controlled terminal failure when collaborators are absent."
    requirement: ANLY-02
    verification:
      - kind: unit
        ref: "backend/tests/test_analysis_service.py#test_analysis_service_records_terminal_failure_when_new_run_lacks_execution_collaborator"
        status: pass
      - kind: integration
        ref: "backend/tests/test_analysis_host_integration.py#test_authenticated_main_host_completes_governed_analysis_and_persists_immutable_artifacts"
        status: pass
    human_judgment: false
  - id: D3
    description: "The authenticated production host persists a completed report and frozen evidence before post-completion lifecycle evaluation can run."
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
  duration: 14m
  completed_date: 2026-07-12
status: complete
---

# Phase 03 Plan 10: Governed Production Analysis Execution Summary

Authenticated FastAPI analysis now freezes governed market, financial, and holdings evidence, executes the fixed AsyncSqliteSaver graph, and persists a completed immutable report.

## Performance

- **Duration:** 14m
- **Started:** 2026-07-12T05:26:00Z
- **Completed:** 2026-07-12T05:40:02Z
- **Tasks:** 3/3
- **Files modified:** 7

## Accomplishments

- Added a read-only loader that adapts only existing governed market, financial, and operational account boundaries into JSON-safe, provenance-bounded evidence records.
- Changed missing graph, preparer, or loader handling so a new run records a sanitized terminal failure instead of remaining misleadingly queued; real active runs still deduplicate.
- Added an authenticated TestClient host regression using the real lifespan, Phase 1 fixture synchronization, cookie session, SQLite persistence, and fixed async graph path.

## Task Commits

1. **Task 1 RED: 先锁定生产受治理证据与异步执行的失败回归** - `ced7e22` (`test`)
2. **Task 2 GREEN: 实现并注入只读生产 evidence loader** - `4a819f3` (`feat`)
3. **Task 3: 证明认证真实主机可完成分析而非仅 fixture API** - `657d7f0` (`test`)

## Files Created/Modified

- `backend/app/analysis/evidence_loader.py` - Converts governed KlineRepository, financial parquet, and operational positions into finite evidence facts.
- `backend/app/analysis/service.py` - Records configuration failures as terminal, auditable run failures.
- `backend/app/main.py` - Constructs and injects the production evidence loader during lifespan startup.
- `backend/tests/test_analysis_evidence.py` - Covers governed inputs, provenance boundaries, finite values, and missing context.
- `backend/tests/test_analysis_service.py` - Covers terminal execution configuration failures and actual active-run deduplication.
- `backend/tests/test_analysis_graph.py` - Runs the fixed graph through AsyncSqliteSaver checkpoints.
- `backend/tests/test_analysis_host_integration.py` - Exercises the real authenticated host path without mocking analysis infrastructure.

## Decisions Made

- Kept evidence facts server-derived and read-only: browser focus and operational notes are excluded, non-finite values are discarded, and raw source content is never passed to the graph.
- Used the existing configured model transport as the sole host-test seam; the router, service, evidence loader, repositories, authentication middleware, and HTTP responses remain production implementations.
- Retained AsyncSqliteSaver as the only execution checkpointer contract because it is the supported path under the current Python runtime.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Honored the governed fixture read-only mount contract**
- **Found during:** Task 3
- **Issue:** The real Phase 1 fixture provider rejected the initially writable temporary fixture directory before lifespan could start.
- **Fix:** Marked generated fixture files and directory read-only in the host integration setup.
- **Files modified:** `backend/tests/test_analysis_host_integration.py`
- **Verification:** The real lifespan fixture synchronization and authenticated analysis request pass.
- **Committed in:** `657d7f0`

**2. [Rule 1 - Bug] Made active-run deduplication regression construct an actual active run**
- **Found during:** Task 2
- **Issue:** The prior test invoked an intentionally unconfigured service twice, which no longer creates an active run after the required terminal-failure change.
- **Fix:** Seeded a repository-owned queued run before invoking the service, preserving the intended active-run contract.
- **Files modified:** `backend/tests/test_analysis_service.py`
- **Verification:** Focused service tests pass.
- **Committed in:** `4a819f3`

**Total deviations:** 2 auto-fixed (1 blocking integration setup issue, 1 behavior-regression correction).
**Impact on plan:** Both changes preserve governed data and run-state semantics without expanding scope.

## Issues Encountered

- The host test emits three existing Polars fixture-pipeline warnings about deprecated streaming collection and grouped `join_asof` sortedness checks. The requested test suite passes and no analysis behavior is affected.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03-11 can map the now-real immutable report and snapshot records into authorized presentation DTOs.
- Plan 03-12 can align the typed UI contract to the real API and lifecycle history resources.

## Self-Check: PASSED

- Found `backend/app/analysis/evidence_loader.py` and `backend/tests/test_analysis_host_integration.py`.
- Found task commits `ced7e22`, `4a819f3`, and `657d7f0`.
