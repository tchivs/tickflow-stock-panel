---
phase: 01-core-merger
plan: 15
subsystem: decision
tags: [fastapi, sqlite, openai-compatible, ai-review, replay]
requires:
  - phase: 01-04
    provides: Persisted deterministic playbook baselines and SQLite decision repository methods
  - phase: 01-14
    provides: Bounded adjustment, provider fallback, and historical replay contracts
provides:
  - Typed OpenAI-compatible proposal gateway with offline fake and safe unavailable fallback
  - Bounded field-adjustment audit preserving immutable deterministic facts
  - Historical-only provider-free replay with stable hashes and context-local call guard
affects: [dashboard-decision-inspector, compose-acceptance]
tech-stack:
  added: []
  patterns:
    - Optional AI proposals are persisted separately and never directly mutate a deterministic decision run.
    - Adjustment fields are allowlisted, bounds-checked, and individually audited before the final snapshot changes.
    - Historical replay derives stable snapshots from as-of-bounded governed rows under a fail-closed AI guard.
key-files:
  created:
    - backend/app/decision/adjustments.py
    - backend/app/decision/ai_review.py
    - backend/app/decision/replay.py
  modified:
    - backend/app/api/decision.py
key-decisions:
  - "Only the existing OpenAI-compatible provider gateway is selectable; Codex CLI and direct credential access remain excluded."
  - "A provider proposal is typed and persisted independently; only the explicit audited-adjustment route may change a final plan snapshot."
  - "Replay accepts persisted decision-run IDs, reads only the requested governed history cutoff, and records no provider provenance."
patterns-established:
  - "Use DecisionReviewService for optional proposal provenance and DecisionAdjustmentService for every bounded field disposition."
  - "Use replay_guard at the review boundary so any attempted provider path raises before repository or gateway work."
requirements-completed: [PLAN-02]
coverage:
  - id: D1
    description: Configured OpenAI-compatible proposal provenance, offline fake behavior, unavailable fallback, and bounded field audit outcomes.
    requirement: PLAN-02
    verification:
      - kind: unit
        ref: uv run --directory backend pytest tests/test_decision_adjustments.py tests/test_decision_ai_review.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: As-of-bounded, symbol-ordered deterministic replay persists stable hashes without provider provenance and fails closed for AI review.
    requirement: PLAN-02
    verification:
      - kind: unit
        ref: uv run --directory backend pytest tests/test_decision_replay.py -q
        status: pass
    human_judgment: false
duration: not measured
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 15: Configured-provider Adjustment and Replay Guard Summary

**Decision runs now retain typed, provenance-recorded OpenAI-compatible proposals separately from deterministic facts, apply only bounded audited fields, and replay governed history with AI disabled.**

## Performance

- **Duration:** Not measured
- **Started:** Not recorded
- **Completed:** 2026-07-11T02:38:40Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Added an OpenAI-compatible typed proposal gateway with provider/model provenance, a deterministic offline fake, and baseline-safe behavior when review is unavailable, malformed, failed, or disabled for fixture Compose.
- Added strict adjustment allowlisting and bounds with durable `applied`, `clamped`, and `rejected` audit records while preserving action, score, and risk/reward as deterministic facts.
- Added as-of-bounded, stable-order historical replay, persisted result snapshots/hashes, a context-local AI-call guard, and validated review/adjustment/replay API endpoints.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement configured proposals and bounded field-audit application** - `058ab2d` (feat)
2. **Task 2: Implement guarded historical replay and API handling** - `f4553c3` (feat)

**Plan metadata:** Pending this commit.

## Files Created/Modified

- `backend/app/decision/adjustments.py` - Enforces field allowlist/domain bounds and persists every adjustment disposition.
- `backend/app/decision/ai_review.py` - Provides configured OpenAI-compatible/offline proposal gateways and baseline-safe review orchestration.
- `backend/app/decision/replay.py` - Supplies governed historical replay, stable snapshots, and the context-local provider guard.
- `backend/app/api/decision.py` - Exposes validated proposal review, adjustment application, and persisted-run replay endpoints.

## Decisions Made

- Reused only `app.services.ai_provider.generate_ai_text` and current provider/model configuration; no new vendor, direct credential access, or Codex CLI review path was introduced.
- Kept proposal persistence and adjustment application separate so generated text has no authority to mutate a final decision snapshot.
- Derived replay timestamps from the requested `as_of` date and recorded provider/model as `null` for every replay run.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The Dashboard decision inspector can distinguish a deterministic baseline, configured-provider proposal provenance, and per-field audit outcomes.
- Historical replay is available through `/api/decision/replay` for persisted decision runs and cannot invoke a review gateway.

## Verification

- `uv run --directory backend pytest tests/test_decision_adjustments.py tests/test_decision_ai_review.py tests/test_decision_replay.py -q` — **passed** (9 passed).
- `uv run --directory backend python -m py_compile app/decision/adjustments.py app/decision/ai_review.py app/decision/replay.py app/api/decision.py` — **passed**.

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
