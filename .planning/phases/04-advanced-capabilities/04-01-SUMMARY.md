---
phase: 04-advanced-capabilities
plan: "01"
subsystem: testing
tags: [pytest, sqlite, tdd, immutable-lineage, promotion-gates]
requires:
  - phase: 03-ai-analysis
    provides: temporary SQLite, immutable record, and server-derived reviewer test patterns
provides:
  - RED contracts for immutable attributed viewpoint versions and confidence calibration
  - RED contracts for frozen experiment specification, governed run, feedback, and retry lineage
  - RED contracts for five independent promotion gates and registered-only outcomes
affects: [ADV-01, ADV-02, ADV-03, advanced-backend]
tech-stack:
  added: []
  patterns:
    - temporary SQLite and bounded collaborator fixtures for advanced-domain contracts
    - append-only fact assertions and explicit no-execution dependency spies
key-files:
  created:
    - backend/tests/advanced/test_viewpoints.py
    - backend/tests/advanced/test_experiments.py
    - backend/tests/advanced/test_evolution.py
  modified: []
key-decisions:
  - "Wave 0 establishes RED public-service contracts without placeholder production implementations."
  - "Viewpoint, experiment, and promotion contracts use fixed local fixtures and forbid live market, provider, broker, or execution dependencies."
patterns-established:
  - "Advanced fact lineage is tested through temporary SQLite state and direct immutable-trigger attempts."
  - "Promotion contracts inject monitor, decision-plan, broker, and execution spies and require zero calls."
requirements-completed: [ADV-01, ADV-02, ADV-03]
coverage:
  - id: ADV-01-RED-CONTRACT
    description: Immutable viewpoint revisions, frozen evaluation windows, explicit unevaluable outcomes, and confidence calibration have deterministic RED contracts.
    requirement: ADV-01
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_viewpoints.py -q
        status: fail
    human_judgment: true
    rationale: Phase 4 production services are intentionally absent; this Wave 0 deliverable is the failing contract that later implementation must satisfy.
  - id: ADV-02-RED-CONTRACT
    description: Frozen experiment specifications, governed manifests, failure honesty, feedback eligibility, and retry lineage have deterministic RED contracts.
    requirement: ADV-02
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_experiments.py -q
        status: fail
    human_judgment: true
    rationale: Phase 4 production services are intentionally absent; this Wave 0 deliverable is the failing contract that later implementation must satisfy.
  - id: ADV-03-RED-CONTRACT
    description: Constrained mutation provenance, five independent gates, server-derived approval, replay safety, and registered-only promotion have deterministic RED contracts.
    requirement: ADV-03
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_evolution.py -q
        status: fail
    human_judgment: true
    rationale: Phase 4 production services are intentionally absent; this Wave 0 deliverable is the failing contract that later implementation must satisfy.
metrics:
  duration: 11m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 01: Advanced Research RED Contracts Summary

**Three deterministic RED pytest contracts now define immutable viewpoint lineage, reproducible experiment records, and five-gate research-strategy promotion without any live market or execution dependency.**

## Performance

- **Duration:** 11m
- **Started:** 2026-07-12T13:48:20Z
- **Completed:** 2026-07-12T13:59:38Z
- **Tasks:** 3/3
- **Files modified:** 3

## Accomplishments

- Defined ADV-01 public-service contracts for immutable viewpoint versions, material versus non-material revisions, frozen 20/60/120-day evaluation plans, server-only benchmark policy, unevaluable outcomes, and low/medium/high calibration projections.
- Defined ADV-02 contracts for immutable experiment specifications, server-derived governed manifests with no raw series persistence, sanitized constraint failures, one eligible append-only feedback entry, and retry-created records.
- Defined ADV-03 contracts for validated constrained candidates, all five independent promotion gates, server-derived research approval with rationale, replay-safe registration, and zero monitor/decision/broker/execution calls.

## Task Commits

1. **Task 1: Specify immutable attributed-viewpoint and calibration behavior** - `0d00971` (`test`)
2. **Task 2: Specify frozen experiment specifications, runs, and feedback** - `438c36a` (`test`)
3. **Task 3: Specify constrained evolution gates and promotion outcome** - `e20a579` (`test`)

## Files Created/Modified

- `backend/tests/advanced/test_viewpoints.py` - RED contract for immutable attributed viewpoints, frozen evaluation, explicit unevaluable states, and calibration.
- `backend/tests/advanced/test_experiments.py` - RED contract for immutable experiment specifications/runs, governed provenance, feedback, and retry semantics.
- `backend/tests/advanced/test_evolution.py` - RED contract for constrained candidates, independent gates, replay-safe approval, API principal derivation, and no market action.

## Verification

```text
cd backend && uv run python -m compileall -q tests/advanced
passed

cd backend && uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py tests/advanced/test_evolution.py -q
32 failed as expected: every failure is ModuleNotFoundError for the intentionally absent app.advanced implementation.
```

## Decisions Made

- The Wave 0 contracts use direct public-service calls, temporary operational SQLite paths, and bounded fakes so later implementations cannot depend on live providers or current-price recomputation.
- Promotion approval explicitly tests server-derived principal handling and injects side-effect spies; registration is the only permitted successful outcome.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. The three files intentionally contain only executable RED contracts and no delivery-blocking placeholder implementation.

## Issues Encountered

None. The focused pytest failures are the required RED state because `app.advanced` has not yet been implemented.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plans 04-04 through 04-06 can implement the tested public services, SQLite schema, and API boundary without altering the Wave 0 safety and lineage contracts.

## Self-Check: PASSED

Verified `backend/tests/advanced/test_viewpoints.py`, `backend/tests/advanced/test_experiments.py`, and `backend/tests/advanced/test_evolution.py` exist and task commits `0d00971`, `438c36a`, and `e20a579` are present in git history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
