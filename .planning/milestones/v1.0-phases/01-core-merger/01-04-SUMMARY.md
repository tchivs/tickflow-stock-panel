---
phase: 01-core-merger
plan: "04"
subsystem: decision
tags: [fastapi, sqlite, duckdb, polars, deterministic-playbook]
requires:
  - phase: 01-02
    provides: Governed Parquet/DuckDB/Polars market-data boundary
  - phase: 01-03
    provides: Versioned operational SQLite repository and host lifecycle state
  - phase: 01-14
    provides: Deterministic decision baseline contract tests
provides:
  - Immutable deterministic decision playbook baselines with governed-data provenance
  - Versioned SQLite decision runs, baseline/final snapshots, proposal/audit, and replay record boundary
  - Authenticated host API routes for persisted decision-run generation and retrieval
affects: [01-15, dashboard-decision-inspector, compose-acceptance]
tech-stack:
  added: []
  patterns:
    - Deterministic calculation is pure and separate from governed history loading, HTTP, and SQLite persistence.
    - Baseline and final playbook snapshots are independently persisted; only final snapshots may later transition.
    - Decision generation reads the existing KlineRepository governed history and uses the host operational repository.
key-files:
  created:
    - backend/app/decision/__init__.py
    - backend/app/decision/playbook.py
    - backend/app/api/decision.py
  modified:
    - backend/app/operational/migrations.py
    - backend/app/operational/repository.py
    - backend/app/main.py
    - backend/tests/test_decision_playbook.py
key-decisions:
  - "Decision baselines derive solely from governed historical rows and explicit engine configuration; no provider is invoked."
  - "SQLite retains immutable baseline snapshots separately from initially identical final snapshots so future bounded adjustments cannot rewrite baseline facts."
  - "Decision routes attach to the existing authenticated Tickflow host and existing operational state rather than introducing a second app or database."
patterns-established:
  - "Use DecisionPlaybookService for deterministic calculations and OperationalRepository for all durable decision state."
  - "Translate as_of and configuration domain validation failures to HTTP 400 at the Pydantic API boundary."
requirements-completed: [PLAN-01]
coverage:
  - id: D1
    description: Fixed governed inputs produce stable entry range, stop, targets, sizing, action, score, risk/reward, and reason provenance.
    requirement: PLAN-01
    verification:
      - kind: unit
        ref: backend/tests/test_decision_playbook.py#test_plan_01_fixed_governed_history_produces_a_typed_stable_baseline
        status: pass
    human_judgment: false
  - id: D2
    description: Generated decision runs persist immutable baseline facts and an initially equal final snapshot before proposals or audits.
    requirement: PLAN-01
    verification:
      - kind: integration
        ref: backend/tests/test_decision_playbook.py#test_plan_01_persists_immutable_baseline_and_initial_final_before_review
        status: pass
    human_judgment: false
  - id: D3
    description: The existing host exposes validated persisted decision-run generation and retrieval with baseline provenance.
    requirement: PLAN-01
    verification:
      - kind: integration
        ref: backend/tests/test_decision_playbook.py#test_plan_01_api_generates_and_retrieves_persisted_baseline
        status: pass
    human_judgment: false
duration: not measured
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 04: Persisted Deterministic Playbook Baseline Summary

**Tickflow now generates deterministic governed-data playbooks, durably snapshots them in operational SQLite, and exposes them through the authenticated host API.**

## Performance

- **Duration:** Not measured
- **Started:** Not recorded
- **Completed:** 2026-07-11T02:25:50Z
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- Implemented a pure `DecisionPlaybookService` that emits a typed, reproducible baseline with entry range, stop, targets, position sizing, action, score, risk/reward, and governed-history reason snapshot.
- Added the versioned operational SQLite decision boundary: immutable baseline/final snapshots plus typed proposal, field-audit, and replay storage for the later configured-provider/replay work.
- Added validated `/api/decision/runs` generation and retrieval endpoints to the existing authenticated Tickflow application, backed by governed `KlineRepository` historical reads.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement deterministic baseline calculation and decision persistence** - `395c0a7` (feat)
2. **Task 2: Expose baseline generation and retrieval through the host API** - `ef93fb8` (feat)

**Plan metadata:** Pending this commit.

## Files Created/Modified

- `backend/app/decision/__init__.py` - Decision-domain public exports.
- `backend/app/decision/playbook.py` - Pure deterministic baseline calculation and governed-history input adapter.
- `backend/app/api/decision.py` - Validated decision-run generation and retrieval routes.
- `backend/app/operational/migrations.py` - Versioned decision run/playbook/proposal/audit/replay schema.
- `backend/app/operational/repository.py` - Parameterized, transaction-safe decision persistence methods.
- `backend/app/main.py` - Existing host router registration.
- `backend/tests/test_decision_playbook.py` - Deterministic, persistence, API, and host-registration contracts.

## Decisions Made

- Adapted only the Hermes deterministic calculation semantics; no Hermes ORM, runtime, AI provider, or persistence code was imported.
- Kept Parquet/DuckDB/Polars governed history authoritative and SQLite limited to decision operational state.
- Made the stored baseline immutable and maintained the final plan as a separate record initialized from that baseline, preserving the Plan 15 adjustment boundary.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 15 can persist configured-provider proposals, field-bounded adjustment audit outcomes, and AI-free replay results through the established operational repository boundary.
- The Dashboard inspector can generate or retrieve a deterministic run from `/api/decision/runs` without a separate application or data store.

## Verification

- `uv run --directory backend pytest tests/test_decision_playbook.py -q` — **passed** (4 passed).

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
