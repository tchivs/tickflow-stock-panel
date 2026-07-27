---
phase: 01-core-merger
plan: 14
subsystem: testing
tags: [pytest, decision-playbook, ai-review, replay, sqlite]
requires: []
provides:
  - Deterministic baseline persistence contracts over governed historical data.
  - Bounded field-adjustment and per-field audit contracts.
  - Offline configured-provider provenance, fallback, and AI-free replay contracts.
affects: [01-04, 01-15]
tech-stack:
  added: []
  patterns:
    - Decision contracts use fixed governed snapshots and temporary SQLite repositories.
    - Provider paths inject offline transports or fakes and never need credentials.
    - Replay contracts assert as_of filtering, stable symbol order, deterministic timestamps, and a context-local AI guard.
key-files:
  created:
    - backend/tests/test_decision_playbook.py
    - backend/tests/test_decision_adjustments.py
    - backend/tests/test_decision_ai_review.py
    - backend/tests/test_decision_replay.py
  modified: []
key-decisions:
  - "The baseline snapshot is persisted before proposals or adjustment records can be associated with its run."
  - "Only six numeric plan fields are adjustable; action, score, and risk/reward remain deterministic facts."
  - "Configured provider tests use injected offline collaborators, while replay has no provider provenance and fails closed under its AI guard."
patterns-established:
  - "Decision RED handoff: future implementations satisfy contract-level public services, typed snapshots, and temporary SQLite audit assertions."
  - "Replay safety: governed rows are as_of-bounded and symbol-sorted, with result hash and derived timestamp stability tested twice."
requirements-completed: [PLAN-01, PLAN-02]
coverage:
  - id: D1
    description: Deterministic typed baseline and immutable persisted initial-final snapshot contract.
    requirement: PLAN-01
    verification:
      - kind: unit
        ref: "uv run --directory backend pytest tests/test_decision_playbook.py tests/test_decision_adjustments.py -q; test $? -ne 0"
        status: unknown
    human_judgment: false
  - id: D2
    description: Bounded adjustment allowlist with applied, clamped, and rejected field audit records.
    requirement: PLAN-02
    verification:
      - kind: unit
        ref: "uv run --directory backend pytest tests/test_decision_playbook.py tests/test_decision_adjustments.py -q; test $? -ne 0"
        status: unknown
    human_judgment: false
  - id: D3
    description: Offline configured-provider provenance and unavailable-review fallback contract.
    requirement: PLAN-02
    verification:
      - kind: unit
        ref: "uv run --directory backend pytest tests/test_decision_ai_review.py tests/test_decision_replay.py -q; test $? -ne 0"
        status: unknown
    human_judgment: false
  - id: D4
    description: As-of-bounded ordered, stable-hash replay with an AI invocation guard.
    requirement: PLAN-02
    verification:
      - kind: unit
        ref: "uv run --directory backend pytest tests/test_decision_ai_review.py tests/test_decision_replay.py -q; test $? -ne 0"
        status: unknown
    human_judgment: false
duration: 2min
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 14: Decision-safety Wave 1 Contracts Summary

**Four RED pytest modules define deterministic decision baselines, bounded AI proposals, durable audit outcomes, and provider-free historical replay.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-07-11T01:52:32Z
- **Completed:** 2026-07-11T01:54:21Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Added fixed governed-history contracts for a typed, reproducible playbook baseline and its immutable pre-review SQLite snapshot.
- Added strict field-allowlist contracts requiring applied, clamped, and rejected audit dispositions while protecting deterministic action, score, and risk/reward facts.
- Added offline configured-provider proposal/provenance and unavailable fallback contracts without live credentials or network access.
- Added historical replay contracts for as_of filtering, deterministic ordering, stable stored hashes/timestamps, and a fail-closed review-invocation guard.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define deterministic baseline and bounded-adjustment contracts** - `f34db1d` (test)
2. **Task 2: Define configured-provider provenance, fallback, and AI-free replay contracts** - `14a3211` (test)

**Plan metadata:** Pending this commit.

## Files Created/Modified

- `backend/tests/test_decision_playbook.py` - Deterministic governed-input calculation and immutable baseline/final persistence contracts.
- `backend/tests/test_decision_adjustments.py` - Allowed-field bound and per-disposition adjustment audit contracts.
- `backend/tests/test_decision_ai_review.py` - Typed configured-provider provenance, offline fake, and safe unavailable-path contracts.
- `backend/tests/test_decision_replay.py` - Historical-only ordering, stable-hash, and AI-guard replay contracts.

## Decisions Made

- The test contract keeps HermesAlpha as a calculation reference only; it requires host-native future decision code over Tickflow-governed history and SQLite snapshots.
- RED tests inject only offline review collaborators, preserving the resolved OpenAI-compatible provider boundary without credentials or network use.
- Replay is explicitly provider-free and checks the decision review entry point fails before a gateway can execute.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Both focused `uv run` commands reached the configured package mirror but could not download existing locked dependencies (`polars==1.40.1` and `h11==0.16.0`) because the mirror returned HTTP 403. The plan-mandated RED wrappers completed successfully because they assert a nonzero pytest invocation, but pytest did not collect the new contracts. `python3 -m py_compile` successfully validated the syntax of all four test modules.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04 can implement the deterministic decision package and SQLite baseline contract in `test_decision_playbook.py`.
- Plan 15 can implement provider review, adjustment audit, and replay guard behavior against the three PLAN-02 contract modules.

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
