---
phase: 04-advanced-capabilities
plan: "17"
subsystem: advanced-research-evolution
tags: [fastapi, pydantic, sqlite, governed-backtest, immutable-facts]
requires:
  - phase: 04-12
    provides: lifecycle-owned governed experiment runner
  - phase: 04-16
    provides: scoped production advanced API and host authorization conventions
provides:
  - strict frozen strategy scopes for governed experiments
  - completed-run evidence handoff to constrained evolution candidates
  - deterministic five-gate evaluation and research-only promotion APIs
affects: [ADV-02, ADV-03, advanced-api, strategy-research]
tech-stack:
  added: []
  patterns:
    - browser requests select bounded identifiers and configuration while immutable evidence is reloaded server-side
    - promotion gate actions use strict empty request bodies and persist server-derived summaries only
key-files:
  created:
    - .planning/phases/04-advanced-capabilities/04-17-SUMMARY.md
  modified:
    - backend/app/advanced/api.py
    - backend/app/advanced/experiments.py
    - backend/app/advanced/evolution.py
    - backend/app/advanced/governed_runner.py
    - backend/app/advanced/projections.py
    - backend/app/advanced/schemas.py
    - backend/tests/advanced/test_experiments.py
    - backend/tests/advanced/test_evolution.py
    - backend/tests/advanced/test_production_host.py
key-decisions:
  - "Frozen strategy scopes are shared schema contracts and are normalized to ISO dates before persistence."
  - "Candidate source attribution remains immutable internal configuration, so public projections never disclose run evidence, artifacts, or sandbox diagnostics."
  - "Each gate re-evaluates persisted completed-run evidence with an empty browser body; no browser-supplied pass status or evidence reference is accepted."
patterns-established:
  - "Completed-run handoff: EvolutionService validates a complete experiment evidence matrix before candidate creation."
  - "Independent gates: one immutable server-derived verdict per fixed gate name, followed by explicit principal-bound promotion."
requirements-completed: [ADV-02, ADV-03]
coverage:
  - id: D1
    description: Researchers create strict immutable strategy experiments and only completed governed runs can receive one feedback record.
    requirement: ADV-02
    verification:
      - kind: integration
        ref: cd backend && timeout 75s uv run pytest tests/advanced/test_experiments.py tests/advanced/test_production_host.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: Completed immutable evidence creates a constrained candidate, independently evaluates all five gates, and permits only explicit research-only promotion.
    requirement: ADV-03
    verification:
      - kind: integration
        ref: cd backend && timeout 75s uv run pytest tests/advanced/test_experiments.py tests/advanced/test_evolution.py tests/advanced/test_production_host.py -q
        status: pass
    human_judgment: false
metrics:
  duration: 10m 52s
  completed: 2026-07-13
status: complete
---

# Phase 04 Plan 17: Governed Experiment Evolution Summary

**Production strategy experiments now freeze runner-ready scope, retain completed governed evidence, and drive five immutable evolution gates before explicit research-only registration.**

## Performance

- **Duration:** 10m 52s
- **Started:** 2026-07-13T03:37:09Z
- **Completed:** 2026-07-13T03:48:01Z
- **Tasks:** 2/2
- **Files modified:** 9

## Accomplishments

- Replaced the API-local loose experiment scope with a shared strict CN-A strategy/date/symbol/asset/parameter schema and repeated that validation in the service layer.
- Preserved server-produced governed manifests, metrics, artifacts, sandbox lineage, split evidence, robustness trials, and cost assumptions with completed runs only.
- Added scoped candidate creation and five empty-body gate actions that recompute immutable evidence, write a single safe verdict, and preserve explicit server-principal research-only promotion.

## Task Commits

1. **Task 1: 冻结 production runner 所需的 strategy scope 并完成真实反馈循环** - `eb5d676` (test RED), `c3cb3be` (feat GREEN)
2. **Task 2: 将 completed run 证据接入 candidate、五门禁和显式晋级 API** - `756053b` (test RED), `82596f2` (feat GREEN)

## Verification

```text
cd backend && timeout 75s uv run pytest tests/advanced/test_experiments.py tests/advanced/test_evolution.py tests/advanced/test_production_host.py -q
33 passed, 15 existing runtime warnings

cd backend && uv run ruff check app/advanced/api.py app/advanced/experiments.py app/advanced/evolution.py app/advanced/projections.py app/advanced/schemas.py
All checks passed

cd backend && uv run python -m compileall -q app/advanced
passed
```

## Decisions Made

- Scope, dates, symbols, asset type, and scalar parameters are normalized by a shared strict request model before the server invokes a runner.
- The completed-run source record is nested within immutable candidate configuration and omitted by the shallow public projection allowlist.
- Gate API bodies are strict and empty; the server uses only persisted experiment and sandbox evidence to decide each gate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Created the required sandbox audit fact before immutable validation lineage**
- **Found during:** Task 2 (completed-run evidence persistence)
- **Issue:** `advanced_sandbox_validations.audit_reference` has a foreign-key constraint, so a completed experiment could not persist its linked sandbox validation without a matching server audit fact.
- **Fix:** Appended the safe `recorded` audit fact in the same SQLite transaction before appending validation and terminal sandbox-run facts.
- **Files modified:** `backend/app/advanced/experiments.py`
- **Verification:** Full focused experiment, evolution, and production-host suite passes.
- **Committed in:** `82596f2`

**Total deviations:** 1 auto-fixed (1 Rule 1 bug).
**Impact on plan:** The correction is required for the existing immutable foreign-key contract and does not expand the public API or trust surface.

## Issues Encountered

The focused host suite continues to emit existing Polars streaming deprecation and sortedness warnings. No planned verification failed.

## Known Stubs

None. Completed-run evidence and public candidate/gate projections are wired to persisted server facts; no placeholder data reaches the public workflow.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

ADV-02 and ADV-03 now have an auditable path from frozen production strategy inputs through feedback, candidate evidence, independent gates, and explicit research-only registration.

## Self-Check: PASSED

Verified all nine listed source/test artifacts exist and task commits `eb5d676`, `c3cb3be`, `756053b`, and `82596f2` are present in git history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-13*
