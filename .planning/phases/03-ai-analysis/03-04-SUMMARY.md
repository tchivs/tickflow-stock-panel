---
phase: 03-ai-analysis
plan: "04"
subsystem: governed-analysis-persistence
tags: [python, pydantic, sqlite, evidence, immutable-audit]
requires:
  - phase: 03-02
    provides: Analysis transport contracts and phase-level AI boundaries
provides:
  - Server-owned frozen evidence snapshots with deterministic source grading and material-number cross-checks
  - Strict Pydantic generated-body and server-envelope analysis contracts
  - Append-only analysis SQLite records in the shared operational database
affects: [03-05, 03-06, 03-07, analysis-service, lifecycle]
tech-stack:
  added: []
  patterns:
    - Frozen evidence retains only normalized provenance references and hashes, never raw untrusted source text.
    - Material-number confirmation requires an independent peer with identical unit, period, definition, and value.
    - Analysis audit facts are database-enforced append-only records in operational.db.
key-files:
  created:
    - backend/app/analysis/__init__.py
    - backend/app/analysis/schemas.py
    - backend/app/analysis/evidence.py
    - backend/app/analysis/repository.py
  modified:
    - backend/app/operational/migrations.py
    - backend/tests/test_analysis_evidence.py
key-decisions:
  - "The model only writes GeneratedAnalysis; report provenance, lifecycle, and citation authority remain in a frozen server envelope."
  - "Analysis audit rows use SQLite RESTRICT foreign keys plus update/delete-blocking triggers; only in-flight run status may transition."
patterns-established:
  - "EvidencePreparationService normalizes governed records before any model call and exposes unresolved/conflicting states explicitly."
  - "AnalysisRepository uses short-lived parameterized SQLite transactions over the existing operational.db."
requirements-completed: [ANLY-01, ANLY-03]
coverage:
  - id: D1
    description: Server-owned frozen evidence contracts, source grades, and material-number conflict handling
    requirement: ANLY-01
    verification:
      - kind: unit
        ref: backend/tests/test_analysis_evidence.py
        status: pass
    human_judgment: false
  - id: D2
    description: Shared operational.db migration with append-only reports and a single active subject run
    requirement: ANLY-03
    verification:
      - kind: integration
        ref: backend/tests/test_analysis_evidence.py
        status: pass
    human_judgment: false
duration: 5min
completed: 2026-07-12
status: complete
---

# Phase 03 Plan 04: Governed Evidence and Immutable Analysis Records Summary

**Server-frozen A/B/C evidence, fail-closed material-number cross-checks, and append-only analysis audit records now share operational.db.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-12T04:24:17Z
- **Completed:** 2026-07-12T04:29:18Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Added strict `GeneratedAnalysis` and `AnalysisReport` contracts so generated content cannot set source grades, lifecycle state, provenance, or unknown citations.
- Added deterministic evidence freezing with versioned source grades, independence-aware material-number comparison, explicit `context_insufficient`, and raw-content exclusion.
- Added the shared `operational.db` analysis migration and repository with active-run uniqueness, immutable audit triggers, report version ordering, and transactional snapshot persistence.

## Task Commits

1. **Task 1: Define frozen evidence and server authority envelope** - `c416b97` (test RED), `9e84830` (feat GREEN)
2. **Task 2: Migrate and implement immutable AnalysisRepository** - `1ab0fb7` (test RED), `4e9b068` (feat GREEN)

## Files Created/Modified

- `backend/app/analysis/__init__.py` - Stable analysis domain exports without route or lifecycle imports.
- `backend/app/analysis/schemas.py` - Strict frozen-evidence, generated-body, and server-envelope contracts.
- `backend/app/analysis/evidence.py` - Deterministic governed evidence normalization and cross-checking.
- `backend/app/analysis/repository.py` - Parameterized append-only analysis persistence over operational.db.
- `backend/app/operational/migrations.py` - Immutable analysis tables, indexes, foreign keys, and triggers.
- `backend/tests/test_analysis_evidence.py` - Evidence, strict-envelope, migration, and immutability coverage.

## Decisions Made

- The frozen snapshot stores source locators and content hashes only; it excludes raw source text from model context and ordinary persistence.
- A material number is confirmed only with a separate independence group and fully aligned unit, period, definition, and value. Alignment failures remain unresolved; conflicting aligned values remain conflicting.
- Database triggers reject update/delete operations on evidence, reports, reviews, events, observation plans, and outcomes; repository APIs expose append/read operations only.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test bug] Imported the evidence service in the strict-envelope test**
- **Found during:** Task 1
- **Issue:** The new test constructed a frozen snapshot without importing `EvidencePreparationService`.
- **Fix:** Added the local test import.
- **Files modified:** `backend/tests/test_analysis_evidence.py`
- **Verification:** `uv run pytest tests/test_analysis_evidence.py -q` passed.
- **Committed in:** `9e84830`

**Total deviations:** 1 auto-fixed (1 Rule 1 test bug)
**Impact on plan:** The correction was test-only and did not expand production scope.

## Deferred Issues

- `uv run pytest tests/test_analysis_evidence.py tests/test_analysis_service.py -q` reports two failures because `app.analysis.service.AnalysisService` is intentionally scheduled for a later plan. The repository-only assertion in that file passes; no service-layer code was preemptively added.

## TDD Gate Compliance

- Task 1 RED: `c416b97`; GREEN: `9e84830`.
- Task 2 RED: `1ab0fb7`; GREEN: `4e9b068`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Subsequent analysis service, graph, and lifecycle plans can persist server-validated snapshots and reports without introducing a second domain database.
- The full analysis-service test group remains pending the planned `AnalysisService` implementation.

## Self-Check: PASSED

---
*Phase: 03-ai-analysis*
*Completed: 2026-07-12*
