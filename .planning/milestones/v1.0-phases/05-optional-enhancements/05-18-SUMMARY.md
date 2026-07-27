---
phase: 05-optional-enhancements
plan: "18"
subsystem: shadow-production
status: complete
tags: [fastapi, react, playwright, polars, sqlite, backtest, shadow]
requires:
  - phase: 05-optional-enhancements
    plan: "17"
    provides: authenticated optional-module host, Shadow UI, and no-action browser acceptance
  - phase: 05-optional-enhancements
    plan: "30"
    provides: strict bounded Shadow assumption DTO, persistence, hydration, and projection contract
provides:
  - exact strict Shadow browser distillation request using the Plan 05-30 assumption schemas
  - production governed K-line feature source and immutable chronological split freezer
  - bounded BacktestEngine evaluation runner with complete lazy Shadow factory readiness
  - authenticated real-lifespan and browser tracer proving explainable candidate plus IS/OOS evidence
  - typed module-local unavailability when the governed collaborator is incomplete
  - zero completed-v1 action collaborator calls across the traced path
affects: [05-19, 05-20, 05-24, 05-25, SHDW-01, shadow-production]
tech-stack:
  added: []
  patterns:
    - existing KlineRepository plus FrozenPanelArtifactStore plus BacktestEngine production composition
    - strict browser selectors with server-owned evidence, fingerprints, frozen artifacts, and verdicts
    - optional factory availability means complete usable collaborators rather than dependency presence
key-files:
  created:
    - backend/app/shadow/production.py
    - .planning/phases/05-optional-enhancements/05-18-SUMMARY.md
  modified:
    - backend/app/optional_modules.py
    - backend/app/shadow/evaluation.py
    - backend/app/shadow/repository.py
    - backend/tests/test_phase5_optional_host.py
    - frontend/src/lib/phase5Api.ts
    - frontend/src/pages/backtest/ShadowAccount.tsx
    - frontend/e2e/phase5-optional-enhancements.spec.ts
key-decisions:
  - "The production tracer reuses KlineRepository, FrozenPanelArtifactStore, and BacktestEngine; it adds no second data source, artifact schema, evaluator authority, database, queue, or container."
  - "A bounded Shadow evidence set must resolve to one attributable instrument with buy entries for this thin production path; unsupported mixed-instrument evidence fails closed rather than blending session identity."
  - "Only the strict Plan 05-30 fixed_holding_days and governed price-adjustment assumptions reach the runner; the browser cannot send evidence identity, principal, verdict, or action authority."
patterns-established:
  - "Complete optional readiness: Shadow initialization fails locally unless the governed daily repository and all distillation/freezing/evaluation collaborators are present."
  - "Private frozen-panel reference and scope remain persisted runner inputs while the public artifact projection exposes only allowlisted integrity metadata."
requirements-completed: [SHDW-01]
coverage:
  - id: D1
    description: "An authenticated production Shadow request imports deterministic local execution evidence, creates an explainable candidate with the strict bounded DTO, and records passing chronological IS/OOS evaluations without completed-v1 action calls."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/test_phase5_optional_host.py::test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory -x (1 passed)"
        status: pass
      - kind: automated_ui
        ref: "cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep 'Shadow production distillation contract' (1 passed)"
        status: pass
    human_judgment: false
duration: 28m38s
completed: 2026-07-17
---

# Phase 05 Plan 18: Strict Shadow Production Tracer Summary

**Strict browser selectors now traverse the authenticated production host into governed local-trade feature derivation, an explainable transient candidate, immutable split panels, and bounded chronological IS/OOS evaluation with no completed-v1 action authority.**

## Performance

- **Duration:** 28m 38s
- **Started:** 2026-07-17T09:35:55Z
- **Completed:** 2026-07-17T10:04:33Z
- **Tasks:** 1/1
- **Files modified:** 8

## Accomplishments

- Replaced the hollow Shadow factory with a complete lazy composition: `ShadowImporter`, `ShadowDistiller`, governed feature source, immutable feature freezer, bounded evaluation runner, `ShadowEvaluationService`, and the existing repository/service.
- Derived the fixed explainable feature allowlist from the existing governed `KlineRepository`, froze each declared chronological split through `FrozenPanelArtifactStore`, and delegated trade simulation to the existing `BacktestEngine`.
- Updated the shared typed client and production Shadow panel to send exactly `feature_names`, `seed`, `max_depth`, `min_leaf_support`, `exit_assumptions`, and `holding_assumptions` under Plan 05-30's strict schemas.
- Added a named authenticated real-lifespan tracer covering local CSV import, attributable evidence freezing, explainable distillation, independent IS/OOS evaluation, safe artifact projection, typed missing-collaborator failure, v1 continuity, and zero action-domain calls.
- Added the named Playwright contract that observes the actual browser mutation body and rejects the removed `min_samples_leaf`, `min_support`, `min_precision`, and `training_window` fields.

## Task Commits

TDD gates were committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: Add failing production-host and browser contracts | `d5927ed` | Backend failed with 422 from the hollow factory; browser exposed the legacy incompatible body |
| GREEN | Task 1: Wire governed production Shadow path | `b466d01` | Named backend and browser tracers pass end to end |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/shadow/production.py` — bounded governed feature derivation, immutable split freezing, safe artifact identity, and BacktestEngine evaluation adapter.
- `backend/app/optional_modules.py` — complete Shadow factory composition and fail-closed governed readiness.
- `backend/app/shadow/evaluation.py` — carries only canonical rules, limitations, and the strict assumption pair into the bounded runner.
- `backend/app/shadow/repository.py` — fixes the evaluation-attempt schema guard so the real production path can append its immutable attempt.
- `backend/tests/test_phase5_optional_host.py` — authenticated real-lifespan Shadow production tracer and missing-collaborator contract.
- `frontend/src/lib/phase5Api.ts` — exact typed `DistillRequest`-compatible input.
- `frontend/src/pages/backtest/ShadowAccount.tsx` — strict production mutation body with no forbidden legacy fields.
- `frontend/e2e/phase5-optional-enhancements.spec.ts` — named browser mutation-body and governed-evaluation scenario.

## Decisions Made

- Reused the existing governed K-line repository, frozen-panel artifact store, and BacktestEngine instead of introducing a Shadow-specific lake, alternate backtest authority, or duplicate persistence schema.
- Kept estimator state transient. Only allowlisted rules, metrics, bounded assumptions, source lineage, immutable panel integrity, and terminal evaluation facts cross persistence.
- Limited the thin production path to one attributable instrument per evidence set and bounded training/evaluation windows and rows. Unsupported evidence fails typed and local rather than being silently blended or truncated.
- Kept private frozen references and scopes available to retry execution while relying on the existing hand-written public projection to omit paths and runner internals.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed the real evaluation-attempt schema guard**
- **Found during:** Task 1 GREEN authenticated IS/OOS tracer.
- **Issue:** `append_evaluation_attempt` attempted to construct a set containing mutable sets, raising `TypeError: unhashable type: 'set'` before any evaluation fact could be reserved.
- **Fix:** Compare the payload field set against a tuple of the two accepted field sets.
- **Files modified:** `backend/app/shadow/repository.py`
- **Verification:** The named production-host tracer completed both split attempts and returned two passing immutable evaluations.
- **Committed in:** `b466d01`

---

**Total deviations:** 1 auto-fixed (1 correctness bug).
**Impact on plan:** The fix was required for the declared real production path and changed no schema, authority, endpoint, or replay identity.

## Verification

```text
cd backend && uv run pytest tests/test_phase5_optional_host.py::test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory -x
Result: PASS — 1 passed, 3 pre-existing Polars warnings.

cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "Shadow production distillation contract"
Result: PASS — 1 passed.

cd backend && uv run pytest tests/shadow/test_evaluation_retention.py tests/shadow/test_distillation.py -x
Result: PASS — 19 passed.

cd frontend && pnpm exec tsc --noEmit
Result: PASS — no diagnostics.

cd backend && uv run ruff check app/shadow/production.py tests/test_phase5_optional_host.py
Result: PASS — no diagnostics.
```

The autonomous tracer feedback gate re-ran the exact plan command after the GREEN commit and passed both backend and browser legs.

## Threat Mitigation Evidence

- **T-05-18-01:** The browser contract asserts the exact six-field strict DTO and absence of the four legacy extra fields; the authenticated API consumes the same Plan 05-30 models.
- **T-05-18-02:** Evidence IDs, principals, trade labels, governed K-line rows, split fingerprints, panel checksums, and verdicts are all resolved or produced server-side.
- **T-05-18-03:** `LiveActionSpies.assert_zero_calls()` remains green after import, distillation, evaluation, and completed-v1 smoke; no strategy, monitor, plan, position, ledger, broker, provider, or market-action collaborator is supplied.
- **T-05-18-04:** Missing `governed_repository` makes only Shadow `shadow_initialization_failed`; the production host and completed-v1 surfaces remain available.
- No new endpoint, database, queue, container, external network access, broker integration, action collaborator, or browser authority was introduced.

## TDD Gate Compliance

- RED commit `d5927ed` contains both named failing observable contracts and failed at the confirmed hollow-factory/request-mismatch boundaries before implementation.
- GREEN commit `b466d01` implements the complete production path and passes the named backend/browser contracts plus focused Shadow domain regression.
- No refactor-only commit was necessary after focused Ruff, TypeScript, backend, and browser verification.

## Known Stubs

None. Empty and optional values in adjacent Phase 05 code remain typed absence/history representations; no placeholder, mock, no-op, or empty fallback can satisfy the new production tracer.

## Issues Encountered

- The isolated environment's existing `pytest` launcher still referenced the primary checkout. Reinstalling the already locked `pytest` package rewrote the local launcher to the isolated environment; no dependency version or project metadata changed.
- The first test fixture write used raw daily storage while the governed `get_daily` contract intentionally reads enriched storage. The tracer was corrected to append governed enriched rows and rebuild the repository views before exercising the production request.
- The initial server-owned training envelope exceeded its own 800-day cap when applied around a multi-month trade span. It was tightened to a bounded 180-day context on each side without weakening the row or chronology gates.

## User Setup Required

None.

## Next Phase Readiness

- Plan 05-19 can build audit/replay expansion on a proven production factory and exact bounded assumption path.
- Plan 05-20 can close broader import/evidence identity concerns without replacing this factory, feature authority, or runner composition.
- SHDW-01 now has the named production host/browser tracer required by this gap plan; no descriptor was fabricated and no activation authority was granted.

## Self-Check: PASSED

- All eight implementation/test artifacts and this summary exist in the isolated checkout.
- RED `d5927ed` and GREEN `b466d01` resolve as commits.
- The exact post-commit tracer feedback gate passed both backend and browser legs.
- No task commit deleted a tracked file; scoped implementation paths are clean.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` were not modified.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
