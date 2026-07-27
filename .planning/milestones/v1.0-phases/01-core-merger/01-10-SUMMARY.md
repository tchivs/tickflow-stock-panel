---
phase: 01-core-merger
plan: "10"
subsystem: ui
tags: [react, typescript, react-query, monitor, decision-playbook]
requires:
  - phase: 01-08
    provides: Typed operational alert-delivery and deterministic decision client contracts
provides:
  - Responsive canonical Monitor history, rule editing, and sanitized delivery inspection
  - Read-only deterministic playbook comparison with AI-disabled historical replay
  - Persisted replay creation timestamp in the decision response contract
affects: [monitor-frontend, dashboard-decision-inspector, phase-01-e2e]
tech-stack:
  added: []
  patterns:
    - Keep Monitor history refresh and delivery-detail polling in React Query; do not add a page-level stream.
    - Use the shared Modal primitive for rule, confirmation, delivery, and playbook dialogs.
key-files:
  created:
    - frontend/src/components/monitor/DeliveryDetailDialog.tsx
    - frontend/src/components/decision/PlaybookInspector.tsx
  modified:
    - frontend/src/pages/Monitor.tsx
    - frontend/src/components/monitor/RuleEditor.tsx
    - frontend/src/pages/Dashboard.tsx
    - frontend/src/lib/api.ts
    - backend/app/api/decision.py
    - backend/app/operational/repository.py
key-decisions:
  - "Monitor remains the sole alert workflow; persisted filters and delivery details extend its existing history panel."
  - "The Dashboard inspector is read-only and accepts a persisted decision-plan ID because the operational API exposes run retrieval but no run listing."
  - "Replay responses expose their persisted creation timestamp so the inspector does not infer replay provenance from the client clock."
patterns-established:
  - "Render delivery error text only as escaped React text and redact URL- or credential-shaped content before display."
  - "Display immutable action, score, and risk/reward as deterministic facts outside the AI-adjustment audit."
requirements-completed: [CORE-04, PLAN-01, PLAN-02]
coverage:
  - id: D1
    description: Responsive Monitor history exposes position, severity, and persisted delivery-state filters, holding-aware rules, and safe per-channel delivery details.
    requirement: CORE-04
    verification:
      - kind: other
        ref: pnpm --dir frontend build
        status: pass
    human_judgment: true
    rationale: Browser coverage in Plan 11 is required to exercise desktop and 320px interaction flows.
  - id: D2
    description: Dashboard opens a read-only inspector that compares baseline/final plans, audits permitted adjustments, and runs AI-disabled historical replay.
    requirement: PLAN-01
    verification:
      - kind: other
        ref: pnpm --dir frontend build
        status: pass
      - kind: integration
        ref: uv run --directory backend pytest tests/test_decision_replay.py -q
        status: pass
    human_judgment: true
    rationale: Browser coverage in Plan 11 is required to exercise inspector selection and rendering workflows.
  - id: D3
    description: Historical replay responses include the persisted replay creation timestamp used by the audit UI.
    requirement: PLAN-02
    verification:
      - kind: integration
        ref: uv run --directory backend pytest tests/test_decision_replay.py -q
        status: pass
    human_judgment: false
duration: not recorded
completed: 2026-07-11
status: complete
---

# Phase 01 Plan 10: Monitor And Decision Inspection Summary

**The existing Monitor now manages holding-aware rules and durable delivery outcomes, while Dashboard exposes a read-only deterministic decision-plan audit with AI-disabled historical replay.**

## Performance

- **Duration:** Not recorded
- **Completed:** 2026-07-11
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Extended the existing responsive Monitor center with all persisted type, severity, and delivery filters; position rule selection; valuation/history context; and refresh-in-place delivery status details.
- Added a shared-Modal delivery detail dialog that renders only per-channel status, timestamp, and redacted safe error text.
- Added Dashboard's `查看决策计划` action and a read-only inspector for deterministic baseline/final comparison, adjustment dispositions, unavailable AI changes, and selected-as-of AI-disabled replay.
- Returned persisted replay creation timestamps from the operational contract so replay audit provenance is displayed without client inference.

## Task Commits

1. **Task 1: Extend the single Monitor center with position rules and delivery detail** — `938dc1b` (feat)
2. **Task 2: Add deterministic playbook comparison and historical replay inspection** — `8b7a34e` (feat)

## Files Created/Modified

- `frontend/src/pages/Monitor.tsx` — persisted filters, responsive history/rule composition, delivery chips, and shared dialogs.
- `frontend/src/components/monitor/RuleEditor.tsx` — position scope, holdings selector, schedule, quiet-period bypass, and approved channel controls.
- `frontend/src/components/monitor/DeliveryDetailDialog.tsx` — credential-safe delivery-outcome inspection.
- `frontend/src/pages/Dashboard.tsx` — opens the decision-plan inspector.
- `frontend/src/components/decision/PlaybookInspector.tsx` — baseline/final comparison, audit, and replay inspection.
- `frontend/src/lib/api.ts` — exposes replay creation provenance.
- `backend/app/api/decision.py` and `backend/app/operational/repository.py` — return the persisted replay timestamp.

## Decisions Made

- Kept all Monitor behavior on the existing route and React Query refresh pattern; no second alert product or EventSource was introduced.
- Kept decision fields non-editable and made action, score, and risk/reward visibly deterministic facts.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Replay response lacked its persisted creation timestamp**
- **Found during:** Task 2 (Add deterministic playbook comparison and historical replay inspection)
- **Issue:** The persisted `replay_runs.created_at` value was not exposed by the API, preventing the required persisted replay timestamp from being rendered accurately.
- **Fix:** Returned `created_at` from repository and response model, exposed it in the typed client, and rendered it in the inspector.
- **Files modified:** `backend/app/operational/repository.py`, `backend/app/api/decision.py`, `frontend/src/lib/api.ts`, `frontend/src/components/decision/PlaybookInspector.tsx`
- **Verification:** `uv run --directory backend pytest tests/test_decision_replay.py -q` — 2 passed; `pnpm --dir frontend build` — passed.
- **Committed in:** `8b7a34e`

---

**Total deviations:** 1 auto-fixed (1 missing critical contract).
**Impact on plan:** The additive provenance field is necessary for a truthful replay audit and does not add inference, mutation, or a new product surface.

## Issues Encountered

- The initial frontend build caught a RuleEditor JSX boundary error during the holding-scope refactor; it was corrected before the final focused build.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 11 can exercise the Monitor's desktop/mobile filters, rule dialog, delivery details, and Dashboard inspector against isolated fixtures.

## Verification

- **PASS** — `pnpm --dir frontend build`
- **PASS** — `uv run --directory backend pytest tests/test_decision_replay.py -q` (2 passed)

## Self-Check: PASSED

---
*Phase: 01-core-merger*
*Completed: 2026-07-11*
