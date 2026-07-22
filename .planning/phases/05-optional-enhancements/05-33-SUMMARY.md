---
phase: 05-optional-enhancements
plan: "33"
subsystem: shadow-evidence-membership
tags: [fastapi, sqlite, react, playwright, authorization, immutable-evidence]
requires:
  - phase: 05-optional-enhancements
    plan: "20"
    provides: principal-owned bounded Shadow histories and the 200000-member evidence ceiling
  - phase: 05-optional-enhancements
    plan: "24"
    provides: object-safe Shadow browser state, immutable history, and accessible error behavior
provides:
  - strict public evidence requests containing selected batches, one server-resolved membership mode, and bounded exclusions only
  - one principal-scoped transaction that validates completed batches, counts before materialization, verifies artifacts, and freezes complete membership
  - production-host import through evidence, distillation, and chronological IS/OOS proof without repository trade-ID access
  - fixture-browser proof of exact request shape, rejection-state preservation, immutable evidence visibility, and distillation continuation
affects: [05-41, SHDW-01, shadow-production, shadow-browser]
tech-stack:
  added: []
  patterns:
    - server-authoritative set resolution from browser-selected immutable parent records
    - BEGIN IMMEDIATE validation and append transaction for immutable evidence membership
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-33-SUMMARY.md
  modified:
    - backend/app/shadow/api.py
    - backend/app/shadow/repository.py
    - backend/app/shadow/service.py
    - backend/tests/shadow/test_evidence_sets.py
    - backend/tests/test_phase5_optional_host.py
    - frontend/src/lib/phase5Api.ts
    - frontend/src/pages/backtest/ShadowAccount.tsx
    - frontend/e2e/phase5-optional-enhancements.spec.ts
key-decisions:
  - "The public request accepts only membership_mode=all_authorized_batch_trades; explicit included trade IDs are rejected rather than retained as an alternate browser authority path."
  - "The repository resolves owned completed batches, counts members, validates exclusions, verifies artifacts, and appends the canonical manifest under one BEGIN IMMEDIATE transaction."
  - "Exclusions remain explicit bounded user intent, but every exclusion must name a unique trade in the selected authorized batches and cannot cross batches or principals."
patterns-established:
  - "Server-resolved complete set: the browser names immutable parents and exclusions; the repository derives and freezes the authoritative child membership."
  - "Research-only continuation: evidence creation enables distillation and evaluation without adding broker, strategy activation, monitor, plan, position, or market-action authority."
requirements-completed: [SHDW-01]
coverage:
  - id: D1
    description: "Selected completed batches freeze every principal-owned trade except validated bounded exclusions, with limits and immutable membership preserved."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "backend/tests/shadow/test_evidence_sets.py (11 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A public browser-shaped production request reaches candidate distillation and passing chronological IS/OOS evaluations without repository-ID bypass or live actions."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "backend/tests/test_phase5_optional_host.py::test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory (1 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The Shadow browser sends only selected batch IDs, the literal server-resolved mode, and exclusions, preserves state on rejection, and continues to distillation."
    requirement: SHDW-01
    verification:
      - kind: automated_ui
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts --grep 'SHDW-01|Shadow' (8 passed)"
        status: pass
    human_judgment: false
duration: 9m25s
completed: 2026-07-22
status: complete
---

# Phase 05 Plan 33: Server-Resolved Shadow Evidence Membership Summary

**Shadow now turns a normal non-empty browser import into immutable evidence, candidate distillation, and passing IS/OOS evaluation while complete trade membership and principal ownership remain server-authoritative.**

## Performance

- **Duration:** 9m 25s
- **Started:** 2026-07-22T05:39:01Z
- **Completed:** 2026-07-22T05:48:26Z
- **Tasks:** 2/2
- **Files modified:** 8 implementation/test files plus this summary

## Accomplishments

- Replaced browser-authored trade membership with the single literal `all_authorized_batch_trades` mode; the strict DTO forbids the former `included_trade_ids` request field and any other extra authority field.
- Moved complete membership resolution into one principal-scoped `BEGIN IMMEDIATE` transaction that authorizes completed batches, runs SQL `COUNT(*)` before fetching facts, validates exclusions, verifies every batch artifact, derives the included set, and appends the canonical fingerprinted manifest.
- Preserved stable replay fingerprints, the 200,000-member cap, append-only evidence triggers, exact row identity, partial fills, duplicate groups, and foreign/incomplete/cross-batch rejection.
- Reworked the named production-host tracer so it never reads trade IDs from `app.state.shadow_repository`; the public body now reaches a real candidate and passing in-sample/out-of-sample evaluations with all live-action spies at zero.
- Added fixture-browser assertions for the exact three-field request, visible frozen evidence ID/count, distillation continuation, immutable-history retention, selected-batch retention after rejection, and absence of principal/fingerprint/verdict/action fields.

## Task Commits

TDD gates and focused coverage were committed atomically:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: Production and repository membership contracts | `65c84d3` | Existing repository rejected the new server-resolved mode and the host could not accept the browser-shaped body |
| GREEN | Task 1: Atomic server-resolved membership | `3f4ad0f` | Repository selector and named production-host tracer passed |
| RED | Task 2: Strict browser request and rejection behavior | `9d2f70f` | Existing UI sent the forbidden empty explicit trade-ID array |
| GREEN | Task 2: Typed browser membership mode | `9cfa96b` | Focused Shadow Playwright contracts passed |
| COVERAGE | Task 1: Ambiguous and hostile exclusion rejection | `41ded6b` | Invalid modes plus duplicate, missing, cross-batch, and foreign exclusions append no evidence |

**Plan metadata:** committed separately after self-check.

## Files Created/Modified

- `backend/app/shadow/api.py` — strict selected-batch, literal-mode, exclusions-only public request.
- `backend/app/shadow/repository.py` — atomic principal-owned complete-membership resolution and immutable append.
- `backend/app/shadow/service.py` — research-only mode handoff with no trade-ID authority.
- `backend/tests/shadow/test_evidence_sets.py` — complete-set, exclusion, ownership, ambiguity, cap, replay, and immutability contracts.
- `backend/tests/test_phase5_optional_host.py` — public-body production splice through distillation and both evaluations, with explicit old-body rejection and zero live actions.
- `frontend/src/lib/phase5Api.ts` — literal server-resolved evidence input type with no explicit membership field.
- `frontend/src/pages/backtest/ShadowAccount.tsx` — reachable non-empty evidence mutation preserving selection and immutable history on rejection.
- `frontend/e2e/phase5-optional-enhancements.spec.ts` — strict fixture boundary, exact telemetry body, visible continuation, rejection retention, and no-authority assertions.

## Decisions Made

- Kept resolved trade IDs in the immutable evidence response/manifest for audit and downstream distillation, but removed them entirely from the browser input authority surface.
- Used one immediate SQLite transaction for authorization, bounded resolution, artifact verification, replay lookup, and append so batch membership cannot change between validation and freezing.
- Reused existing exclusion records and canonical manifest/fingerprint formats; no schema migration, compatibility alias, alternate endpoint, or client-side trade API was needed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The inherited ignored `backend/.venv/bin/pytest` launcher has a stale shebang pointing at the primary checkout. Focused backend verification therefore used the same locked environment through `uv run python -m pytest`, which loaded this isolated worktree's modules and exercised the exact planned test nodes. No dependency or generated launcher was modified.

## Verification

```text
cd backend && uv run python -m pytest tests/shadow/test_evidence_sets.py -x
Result: PASS — 11 passed.

cd backend && uv run python -m pytest tests/test_phase5_optional_host.py::test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory -x
Result: PASS — 1 passed, with 3 pre-existing Polars warnings.

cd frontend && ATHENA_ALLOW_NETWORK=0 pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep 'SHDW-01|Shadow'
Result: PASS — 8 passed.
```

## Acceptance Criteria

- **PASS — reachable non-empty contract:** the public import batch ID plus literal membership mode creates four-member immutable evidence, distills a real candidate, and records passing chronological IS/OOS evaluations.
- **PASS — principal and completeness authority:** only owned completed batches enter resolution; aggregate count precedes trade fetch; invalid modes and foreign, missing, duplicate, or cross-batch exclusions fail before any evidence append.
- **PASS — immutable audit identity:** artifact verification, canonical trade ordering, exclusions, stable fingerprint replay, and append-only membership records remain enforced.
- **PASS — browser boundary:** the request contains only `included_batch_ids`, `membership_mode`, and `exclusions`; server-derived trade IDs appear only in the immutable response.
- **PASS — zero live-action authority:** production spies remain at zero and fixture telemetry observes no broker, strategy install, monitor, plan, position sync, or market-action request.

## Threat Mitigation Evidence

- **T-05-33-01:** the authenticated principal comes only from request state; the repository applies it in the completed-batch query and rejects browser-authored member IDs at strict DTO validation.
- **T-05-33-02:** complete membership, exclusions, artifact integrity, canonical fingerprint, replay lookup, and immutable child inserts execute in one transaction.
- **T-05-33-03:** repository `list_operational_mutations()` remains empty, the browser exposes no activation crossover, and the production tracer's live-action spies record zero calls.
- No new endpoint, table, external service, broker connection, strategy registration, monitor, plan, position, or market-action surface was introduced.

## TDD Gate Compliance

- Task 1 RED `65c84d3` failed on the absent repository mode and obsolete host body before GREEN `3f4ad0f` passed the focused repository and production-host contracts.
- Task 2 RED `9d2f70f` failed because the UI still sent `included_trade_ids: []`; GREEN `9cfa96b` passed the focused fixture-browser contracts.
- Coverage commit `41ded6b` extended hostile/ambiguous rejection evidence after GREEN without changing production behavior.

## Known Stubs

None. Scoped matches are established SQL placeholder variables, typed empty test accumulators, React Query `placeholderData`, deliberate empty exclusion intent, and explicit absent-value rendering; none is a runtime stub or fake fallback.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 05-41 can drive the same strict body through its real-host primary browser evidence without reconstructing repository trade IDs.
- SHDW-01 now has focused repository, production-host, and fixture-browser proof for the previously unreachable CR-01 node.
- Shared `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain for the parallel-wave orchestrator to reconcile, avoiding unrelated pre-existing changes in this isolated checkout.

## Self-Check: PASSED

- All eight implementation/test artifacts and this summary exist in the isolated checkout.
- RED/GREEN/coverage commits `65c84d3`, `3f4ad0f`, `9d2f70f`, `9cfa96b`, and `41ded6b` resolve as commits in order.
- Final repository, exact production-host review node, and focused fixture-browser contracts all passed after the last code/test change.
- No task commit deleted a tracked file; shared planning state remains outside this plan's scoped metadata commit.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-22*
