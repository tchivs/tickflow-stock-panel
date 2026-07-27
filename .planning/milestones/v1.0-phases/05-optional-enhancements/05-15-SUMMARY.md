---
phase: 05-optional-enhancements
plan: "15"
subsystem: frontend-optional-research
status: complete
tags: [react, typescript, tanstack-query, sse, shadow, accessibility, responsive]
requires:
  - phase: 05-optional-enhancements
    plan: "05"
    provides: exact Phase 05 browser RED contracts and authority-capture fixtures
  - phase: 05-optional-enhancements
    plan: "11"
    provides: deny-by-default Shadow API, immutable workflow, evaluation, and research-only retention
  - phase: 05-optional-enhancements
    plan: "12"
    provides: immutable Thesis versions, checks, pending review, and stock-scoped API
  - phase: 05-optional-enhancements
    plan: "14"
    provides: Forecast catalog/job/record/path/calibration API, persisted-state SSE, and independent optional host
provides:
  - strict shared TypeScript DTO and request boundary for Shadow, Thesis, and Forecast
  - module/object/immutable-record TanStack Query key factories
  - exact-key Forecast progress parser with bounded persisted-state reconnection and object-local invalidation
  - complete Shadow local import, frozen evidence, explainable candidate, IS/OOS, and research-retention panel
  - narrow Shadow section mount in the existing Strategy Backtest workspace
affects: [05-16, 05-17, SHDW-01, THES-01, FORE-01]
tech-stack:
  added: []
  patterns:
    - module/object/immutable-record query identities
    - deny-by-default typed mutation bodies
    - exact-key SSE parsing with persisted terminal refresh
    - research-ledger panel with semantic overflow tables and accessible confirmations
key-files:
  created:
    - frontend/src/lib/phase5Api.ts
    - frontend/src/lib/forecastTask.ts
    - frontend/src/pages/backtest/ShadowAccount.tsx
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/pages/Backtest.tsx
key-decisions:
  - "The shared request wrapper is exported with a typed status-bearing error rather than duplicating fetch semantics inside Phase 05."
  - "Forecast SSE remains hook-local and transport-only; every terminal transition is refreshed from the persisted job endpoint before object-local invalidation."
  - "Shadow renders only bounded safe server projections and derives retainability from two persisted passing evaluations; the browser never supplies verdict, fingerprint, principal, or activation authority."
  - "Wave 0 fixture-only optional fields are normalized to safe empty projections without fabricating production facts; production /evaluations remains authoritative over the older fixture /runs shape."
patterns-established:
  - "Phase 05 key shape: ['phase5', module, object, resource, immutable-id, bounded-page]."
  - "Optional panel loading/error states retain previous query data and never gate the existing v1 workspace."
requirements-completed: [SHDW-01, THES-01, FORE-01]
coverage:
  - id: D1
    description: "Strict shared Phase 05 DTOs, request bodies, object-local query keys, and Forecast SSE parser/recovery compile against the production frontend contract."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd frontend && pnpm exec tsc --noEmit"
        status: pass
    human_judgment: false
  - id: D2
    description: "The complete Shadow workflow is mounted in Backtest with immutable import/evidence/candidate/evaluation/retention states and no authority actions."
    requirement: SHDW-01
    verification:
      - kind: automated_ui
        ref: "cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep 'SHDW|Shadow'"
        status: pass
    human_judgment: true
    rationale: "The checked-in Wave 0 spec still marks scenarios 2-4 as expected failures until Plan 05-17; the command exits green but final ordinary-green visual and terminal-fixture acceptance must not be auto-claimed here."
  - id: D3
    description: "Shared Thesis DTO and key contracts are ready for the stock Analysis panel without mounting or mutating Thesis authority early."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "cd frontend && pnpm exec tsc --noEmit"
        status: pass
    human_judgment: false
metrics:
  duration: 18m30s
  completed: 2026-07-16
---

# Phase 05 Plan 15: Shared Frontend Boundary and Shadow Account Summary

**A strict typed Phase 05 API/query/SSE boundary now powers an evidence-first Shadow workflow inside the existing Strategy Backtest workspace, with immutable history, accessible confirmations, bounded responsive tables, and no activation authority.**

## Performance

- **Duration:** 18m 30s
- **Started:** 2026-07-16T07:24:34Z
- **Completed:** 2026-07-16T07:43:04Z
- **Tasks:** 2/2
- **Files created:** 3
- **Files modified:** 3

## Accomplishments

- Added strict Shadow, Thesis, Forecast, catalog, job, path, outcome, calibration, and module-capability DTOs plus request methods that send only bounded selectors, rationales, files, mappings, horizons, catalog IDs, and idempotency keys.
- Added module/object/immutable-record query factories and a Forecast-only SSE hook that rejects unknown/malformed/foreign events, retains the last committed stage, performs bounded reconnect, refreshes persisted status, and invalidates only matching instrument/job/record/calibration identities.
- Built and mounted the approved Shadow import → evidence → candidate → independent IS/OOS → research-only retention workflow after `ExperimentComparison` and before `AdvancedResearchPanels`, preserving all three Backtest modes and the existing shell.
- Implemented exact Shadow copy, local loading/error/unavailable/stale/partial/pending/terminal states, bounded immutable histories, semantic tables, keyboard-focusable overflow, 44px controls, reduced motion, dialog focus management, and full long-identifier wrapping.

## Task Commits

1. **Task 1: Add strict Phase 05 API, object-local query keys, and Forecast SSE recovery client** — `1c4ba0cf902b8dcc9f3d970e45a3e67948f3c90e` (`feat`)
2. **Task 2: Build and mount the complete ShadowAccount production panel** — `2ac1e2896aa32b792cbf0265f9fcbc434d35e89b` (`feat`)

Inherited browser RED gate: `dacd3dce130ad6d4f9a315e16ffdc7bb15c55bd9`.

## Files Created/Modified

- `frontend/src/lib/api.ts` — exported the existing request wrapper and added a typed status-bearing error while preserving existing toast/auth behavior.
- `frontend/src/lib/phase5Api.ts` — strict shared DTOs, bounded request bodies, encoded routes, and safe Shadow fixture/production normalization.
- `frontend/src/lib/queryKeys.ts` — module/object/immutable-record/page-scoped Shadow, Thesis, and Forecast key factories.
- `frontend/src/lib/forecastTask.ts` — exact-key Forecast progress parser, local task state, bounded reconnect, persisted terminal refresh, and focused invalidation.
- `frontend/src/pages/backtest/ShadowAccount.tsx` — complete accessible responsive Shadow production panel and immutable research ledger.
- `frontend/src/pages/Backtest.tsx` — narrow Shadow mount in the approved Strategy Backtest order and restored rendering of the existing optimizer tabpanel.

## Decisions Made

- Reused the existing `request<T>` implementation by exporting it and introducing `ApiRequestError`; no parallel fetch wrapper, state store, or SSE library was added.
- Kept Forecast SSE state hook-local. The event stream is transport, not authority: terminal state and record identity come from `GET /api/forecast/jobs/{jobId}` before invalidation.
- Started all independent Shadow capability/history queries in the same render. Selection and eligibility are derived from current query data rather than mirrored through effects.
- Kept production `/api/shadow/evaluations` authoritative. Safe optional fixture fields are normalized, but the client does not fabricate terminal `/runs` facts or a SHDW descriptor.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Exported typed shared request errors**
- **Found during:** Task 1
- **Issue:** The existing `request<T>` wrapper was private and threw a status-less `Error`, so the required separate Phase 05 module could neither reuse it nor preserve typed 404/409/422/503 outcomes.
- **Fix:** Exported the same wrapper and added backward-compatible `ApiRequestError.status`/`detail`; existing callers retain the same safe message and toast behavior.
- **Files modified:** `frontend/src/lib/api.ts`
- **Verification:** `pnpm exec tsc --noEmit`
- **Committed in:** `1c4ba0cf902b8dcc9f3d970e45a3e67948f3c90e`

**2. [Rule 1 - Browser Contract Bug] Normalized bounded safe fixture projections before rendering**
- **Found during:** Task 2 focused Playwright run
- **Issue:** Wave 0 fixture DTOs intentionally predated the final deny-by-default backend projection and omitted several arrays now required by production types; direct rendering could read `.length` from an absent field.
- **Fix:** Added allowlisted defaults and field aliases for preview, batch, evidence, candidate, and retention projections without inventing authority or terminal facts.
- **Files modified:** `frontend/src/lib/phase5Api.ts`
- **Verification:** TypeScript compile passed; the subsequent focused Playwright run rendered the panel at 375px and reached the declared terminal fixture boundary instead of crashing.
- **Committed in:** `2ac1e2896aa32b792cbf0265f9fcbc434d35e89b`

**3. [Rule 3 - Blocking Existing Host Issue] Rendered the existing optimizer tabpanel**
- **Found during:** Task 2 mount verification
- **Issue:** `StrategyOptimizer` was imported and exposed as the third keyboard tab but had no tabpanel render branch, causing `tsc --noEmit` to fail and violating the plan requirement to preserve all three Backtest modes.
- **Fix:** Added the missing existing-mode tabpanel without changing its tab identity, order, navigation, or component.
- **Files modified:** `frontend/src/pages/Backtest.tsx`
- **Verification:** `pnpm exec tsc --noEmit`
- **Committed in:** `2ac1e2896aa32b792cbf0265f9fcbc434d35e89b`

---

**Total deviations:** 3 auto-fixed (2 correctness, 1 blocking host issue).
**Impact on plan:** All fixes were required to reuse the declared transport, safely render the existing RED fixtures, or preserve the named three-mode Backtest host. No feature, route, dependency, backend contract, or shell was added outside Plan 05-15.

## Verification

```text
cd frontend && pnpm exec tsc --noEmit
Result: PASS (no diagnostics)

cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "SHDW|Shadow"
Result: PASS command exit; 3/3 inherited expected-failure scenarios accounted for.
```

The focused browser command remains under Wave 0's deliberate `test.fail(true)` gate until Plan 05-17. The latest run proved that the panel renders without the earlier projection crash, that the 375px stale workflow is reached, and that the remaining terminal assertion stops at the fixture's pre-production `/runs` vocabulary while production correctly uses `/evaluations`. This summary does not relabel that expected-failure gate as ordinary-green final acceptance.

## Threat Mitigation Evidence

- **T-05-15-01:** Query keys include module, object, immutable ID, and bounded page; Forecast progress accepts only exact allowlisted keys and matching job identity, then refreshes persisted state before focused invalidation.
- **T-05-15-02:** Mutation interfaces expose no principal, reviewer, fingerprint, digest, verdict, official state, scope, quantile, path, or checkpoint revision fields.
- **T-05-15-03:** Shadow responses are normalized from deny-by-default allowlists; local paths, account secrets, raw errors, commands, traces, and internal policies are neither typed nor rendered.
- **T-05-15-04:** The only terminal Shadow action is research-only retention after two passing evaluations; confirmation explicitly states that no strategy, monitor, plan, position, broker, or market action is created.
- **T-05-15-05:** Every history query is bounded and paginated; tables preserve full lineage through keyboard-focusable horizontal overflow instead of unbounded mobile rendering.

## TDD Gate Compliance

- Task 1 and Task 2 consume the inherited browser RED contract commit `dacd3dce130ad6d4f9a315e16ffdc7bb15c55bd9` from Plan 05-05.
- GREEN implementation commits are `1c4ba0cf902b8dcc9f3d970e45a3e67948f3c90e` followed by `2ac1e2896aa32b792cbf0265f9fcbc434d35e89b`.
- Final removal of Wave 0 expected-failure markers is intentionally assigned to Plan 05-17 after the Thesis and Forecast panels from Plan 05-16 are mounted.

## Known Stubs

None. Empty arrays and nulls are bounded absent-history/optional-field states, not fake output. The client does not fabricate the descriptor-less SHDW edge, server verdicts, terminal runs, fingerprints, paths, or authority.

## Issues Encountered

- The plan referenced `DESIGN.md`, but no such file exists in this worktree. The implementation used the approved `05-UI-SPEC.md`, `PRODUCT.md`, `index.css`, `tailwind.config.ts`, and existing Backtest/advanced-research patterns instead.
- The isolated frontend had no materialized `node_modules`; `pnpm install --offline --frozen-lockfile` used the existing lock only and changed no manifest or lockfile.
- The installed `agent-browser` did not support the skill's live-guide command, so browser verification reused the checked-in Playwright workflow as required by the fallback policy.
- Wave 0's terminal Shadow fixture exposes `/runs`, whereas the final production API exposes `/evaluations`. The panel intentionally follows production and does not invent missing terminal facts; Plan 05-17 owns the final fixture/marker cutover.

## User Setup Required

None. No external service, model, broker, provider, checkpoint download, or environment secret is required for this frontend plan.

## Next Phase Readiness

- Plan 05-16 can consume `phase5Api`, `QK.thesis`, `QK.forecast`, and `useForecastTask` directly for the two stock Analysis panels without adding another transport or cache convention.
- Plan 05-17 can remove the inherited expected-failure markers, align the Shadow terminal fixture with production evaluation records, and run all 13 scenarios as ordinary-green final acceptance.
- SHDW-01 remains descriptor-less flagged-unverified until that final real-host/browser acceptance; this plan did not fabricate or auto-dismiss it.

## Self-Check: PASSED

All six implementation files exist; task commits `1c4ba0cf902b8dcc9f3d970e45a3e67948f3c90e` and `2ac1e2896aa32b792cbf0265f9fcbc434d35e89b` resolve on `worktree-agent-05-15`; no tracked file was deleted; TypeScript compilation passes; the plan-focused Playwright command exits successfully under the documented inherited gate; generated `test-results/` artifacts were removed; and the task worktree was clean before summary/state updates.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
