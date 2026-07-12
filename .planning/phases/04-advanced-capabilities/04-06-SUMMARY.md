---
phase: 04-advanced-capabilities
plan: "06"
subsystem: advanced-research-evolution
tags: [sqlite, immutable-facts, governed-backtest, promotion-gates, research-registration]
requires:
  - phase: 04-04
    provides: append-only advanced SQLite facts and transactional job foundation
  - phase: 02-08
    provides: governed strategy backtest manifest and research asset provenance patterns
provides:
  - immutable experiment specification, governed-run, feedback, and retry lineage
  - constrained candidate mutation provenance with five independent promotion gates
  - replay-safe, server-principal promotion that only registers research strategies
affects: [04-08, 04-09, advanced-backend]
tech-stack:
  added: []
  patterns:
    - narrow injected governed-backtest metadata boundary with no market-series persistence
    - append-only experiment retries and one-feedback-per-eligible-run enforcement
    - atomic all-gates promotion that registers research assets without activation
key-files:
  created:
    - backend/app/advanced/experiments.py
    - backend/app/advanced/evolution.py
    - backend/app/advanced/api.py
  modified:
    - backend/app/advanced/repository.py
    - backend/tests/advanced/test_experiments.py
    - backend/tests/advanced/test_evolution.py
key-decisions:
  - "Experiment services persist only governed manifests, fingerprints, bounded metadata, metrics, and managed artifact references; raw market series are discarded."
  - "A constrained or failed run is auditable infrastructure evidence, never a research feedback conclusion."
  - "Promotion requires the complete five-gate matrix and a server-resolved researcher with a rationale; its only side effect is research-strategy registration."
requirements-completed: [ADV-02, ADV-03]
coverage:
  - id: ADV-02-experiments
    description: Frozen experiment specifications retain governed run manifests, constrained terminal reasons, append-only feedback, and retry lineage.
    requirement: ADV-02
    verification:
      - kind: tests
        ref: cd backend && uv run pytest tests/advanced/test_experiments.py -q
        status: pass
    human_judgment: false
  - id: ADV-03-evolution
    description: Validated candidates retain mutation lineage, require every promotion gate, and register only a research strategy after server-derived approval.
    requirement: ADV-03
    verification:
      - kind: tests
        ref: cd backend && uv run pytest tests/advanced/test_evolution.py -q
        status: pass
    human_judgment: false
metrics:
  duration: 4m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 06: Reproducible Experiments and Constrained Evolution Summary

**Governed experiment runs and strategy evolutions now preserve immutable evidence lineage, reject invalid conclusions, and permit only explicitly approved research-strategy registration.**

## Performance

- **Started:** 2026-07-12T14:32:33Z
- **Completed:** 2026-07-12T14:36:52Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Added immutable experiment specifications containing hypothesis, data scope, method, metrics, and success/failure criteria; revisions and retries append fresh lineage.
- Added a narrow governed-backtest collaborator that stores only manifest fingerprint, asset version, resolved configuration, bounded environment/resources, metrics, and managed artifact references.
- Classified validation, timeout, and resource failures as auditable constrained terminal states that cannot receive research feedback.
- Added one-time append-only feedback with only supported, refuted, inconclusive, or needs-replication conclusions for completed runs.
- Added constrained mutation candidates, deterministic independent gate records, and atomic replay-safe promotion to `registered_research_only` assets.
- Added a minimal strict promotion route that derives researcher identity from server request state and never accepts browser authority fields.

## Task Commits

1. **Task 1: Implement frozen experiment specs, constrained runs, and append-only feedback** - `934ea9a` (`feat`)
2. **Task 2: Implement constrained candidate evaluation and replay-safe promotion** - `d9f8a7d` (`feat`)

## Files Created/Modified

- `backend/app/advanced/experiments.py` - Immutable experiment specification, governed-run, feedback, and retry service.
- `backend/app/advanced/evolution.py` - Candidate lineage, gate matrix, replay-safe approval, and registered-only strategy projection.
- `backend/app/advanced/api.py` - Strict server-derived promotion endpoint.
- `backend/app/advanced/repository.py` - Narrow promotion counting helper for durable replay-safety verification.
- `backend/tests/advanced/test_experiments.py` - Focused frozen-lineage and constrained-run contracts.
- `backend/tests/advanced/test_evolution.py` - Focused mutation, gate, principal, replay, and zero-execution contracts.

## Verification

```text
cd backend && uv run pytest tests/advanced/test_experiments.py -q
7 passed in 2.44s

cd backend && uv run pytest tests/advanced/test_evolution.py -q
9 passed in 3.30s

cd backend && uv run pytest tests/advanced/test_experiments.py tests/advanced/test_evolution.py -q
16 passed in 5.95s

cd backend && uv run ruff check app/advanced/experiments.py app/advanced/evolution.py app/advanced/api.py app/advanced/repository.py
All checks passed

cd backend && uv run python -m compileall -q app/advanced
passed
```

## Decisions Made

- Preserve governed manifest metadata rather than raw price-series payloads in the operational database.
- Treat validation, timeout, and resource limits as terminal operational constraints that cannot be recast as research conclusions.
- Do not use ranking as a promotion decision; all five deterministic gates and a server-resolved approval remain mandatory.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] Added the narrow promotion API and promotion-count repository helper required by the existing contract**
- **Found during:** Task 2
- **Issue:** The required evolution test invokes a strict promotion endpoint and verifies the durable promotion count, but the Phase 04 foundation exposed neither integration point.
- **Fix:** Added a single strict endpoint that derives the principal from `request.state` and a parameterized repository count helper. The endpoint only delegates approved registration and exposes no monitor, decision-plan, broker, or execution capability.
- **Files modified:** `backend/app/advanced/api.py`, `backend/app/advanced/repository.py`
- **Verification:** `uv run pytest tests/advanced/test_evolution.py -q` passed with all zero-call dependency spies intact.
- **Commit:** `d9f8a7d`

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking integration issue).
**Impact on plan:** The minimal integration surface is required to prove server-derived promotion authority and adds no activation or market-execution behavior.

## Known Stubs

None. All services persist concrete records through injected governed collaborators; no placeholder or empty UI data path was introduced.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: promotion_endpoint | `backend/app/advanced/api.py` | New authenticated promotion path derives authority from server request state and maps invalid state to a safe conflict. |

## Next Phase Readiness

Plans 04-08 and 04-09 can attach these immutable experiment and promotion services to authorization, workflow, and broader advanced API composition without adding activation or execution paths.

## Self-Check: PASSED

Verified the summary exists, task commits `934ea9a` and `d9f8a7d` are present in git history, and neither `STATE.md` nor `ROADMAP.md` was modified.
