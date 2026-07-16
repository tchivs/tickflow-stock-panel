---
phase: 05-optional-enhancements
plan: "16"
subsystem: frontend-optional-research
tags: [react, typescript, tanstack-query, echarts, sse, thesis, forecast, accessibility]
requires:
  - phase: 05-optional-enhancements
    plan: "12"
    provides: immutable Thesis versions, checks, pending review, and object-authorized API
  - phase: 05-optional-enhancements
    plan: "14"
    provides: Forecast catalog, persisted jobs, immutable records, paths, calibration, and SSE
  - phase: 05-optional-enhancements
    plan: "15"
    provides: strict Phase 05 DTOs, object-local query keys, bounded SSE recovery, and optional-module capability boundary
provides:
  - complete stock-scoped immutable Thesis lifecycle panel
  - complete stock-scoped governed Kronos probability Forecast panel
  - stock-only semantic Analysis tabs with persistent local selection and scroll behavior
  - accessible table-equivalent quantile, path, provenance, history, and calibration evidence
  - bounded human-only Thesis confirmation and rejection with conflict recovery
  - research-only Forecast request review with no cross-module authority
  - typed local unavailable, partial, transport, and terminal states that preserve existing Analysis
  - responsive 1440/1024/375 layouts using the existing design system
  - no Portfolio optional tabs or changes to existing report/evidence/signal-history identities
affects: [05-17, THES-01, FORE-01, AnalysisWorkspace, optional-research-browser-contracts]
tech-stack:
  added: []
  patterns:
    - object-local parallel TanStack queries with stable prior data
    - immutable version and record selectors kept mounted behind semantic tabpanels
    - server-owned review, quantile, checkpoint, and terminal state rendering
    - ECharts progressive enhancement backed by captioned semantic tables
key-files:
  created:
    - frontend/src/components/analysis/ThesisPanel.tsx
    - frontend/src/components/analysis/ForecastPanel.tsx
  modified:
    - frontend/src/components/analysis/AnalysisWorkspace.tsx
key-decisions:
  - "Thesis and Forecast mount only for stock subjects; Portfolio keeps the original three-tab behavior and no optional requests."
  - "Both optional panels mount behind hidden semantic tabpanels so their object-local selection and query state survive tab switches without a global store."
  - "The shared Phase 05 capability response uses QK.phase5Capabilities, never the unrelated global capabilities cache identity."
  - "Forecast charting is progressive enhancement: quantile, selected-path, provenance, history, and calibration tables remain canonical inspectable evidence."
  - "Legacy Wave 0 fixture aliases are read defensively, but mutations send only strict typed server inputs and never principal, fingerprint, digest, verdict, quantile, path, or official state."
patterns-established:
  - "Stock optional tab pattern: fixed tab identity/order, mounted local panel state, object-keyed queries, and no capability-based tab reordering."
  - "Immutable research UI pattern: current facts first, explicit authority boundary, complete lineage tables, and append-only review/calibration evidence."
requirements-completed: [THES-01, FORE-01]
coverage:
  - id: D1
    description: "Stock Analysis exposes a complete immutable Thesis lifecycle with valuation ranges and typed assumptions, structured per-condition cadence, all check outcomes, pending-only human review, conflict recovery, and history."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "cd frontend && pnpm exec tsc --noEmit"
        status: pass
      - kind: automated_ui
        ref: "e2e/phase5-optional-enhancements.spec.ts scenarios 5-7; scenario 7 assertion body passes while inherited test.fail marker deliberately rejects the unexpected pass"
        status: unknown
    human_judgment: true
    rationale: "Plan 05-17 owns removal of inherited Wave 0 test.fail markers and final fixture cutover; this plan cannot truthfully label the marked suite ordinary-green."
  - id: D2
    description: "Stock Analysis exposes governed 5/20/60 Forecast requests, approved local checkpoint review, persisted task recovery, P10/P50/P90, bounded paths, provenance, immutable history, and append-only calibration."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd frontend && pnpm exec tsc --noEmit"
        status: pass
      - kind: automated_ui
        ref: "e2e/phase5-optional-enhancements.spec.ts scenarios 8-13 under inherited Wave 0 expected-failure gate"
        status: unknown
    human_judgment: true
    rationale: "Wave 0 fixture shapes and test.fail markers intentionally remain for Plan 05-17; type safety and mounted authority-flow smoke evidence are complete, but final ordinary-green browser certification remains downstream."
  - id: D3
    description: "Existing Analysis receives fixed stock-only Thesis and Forecast tabs while Portfolio, existing tab IDs/order/content, object authorization, and independent local failures remain unchanged."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "cd frontend && pnpm exec tsc --noEmit"
        status: pass
      - kind: automated_ui
        ref: "scenario 13 cross-module authority assertion body passes; focused suite reports expected-to-fail marker mismatch until Plan 05-17"
        status: unknown
    human_judgment: true
    rationale: "The browser contract is still deliberately marked future work even when its assertion body passes, so the final marker cutover must be verified by Plan 05-17."
duration: 25m33s
completed: 2026-07-16
status: complete
---

# Phase 05 Plan 16: Stock Thesis and Forecast Panels Summary

**Stock Analysis now contains immutable Thesis review and governed Kronos probability Forecast workspaces, backed by the committed typed query/SSE boundary, complete server-owned lineage, accessible table evidence, and no Portfolio or cross-module authority.**

## Performance

- **Duration:** 25m 33s
- **Started:** 2026-07-16T07:56:48Z
- **Completed:** 2026-07-16T08:22:21Z
- **Tasks:** 3/3
- **Files created:** 2
- **Files modified:** 3

## Accomplishments

- Built a complete Thesis ledger for first and successor immutable versions, explicit valuation ranges and assumptions, structured conditions with independent cadence, due/check evidence, pending conclusions, and append-only review/version history.
- Added keyboard-safe confirm/reject dialogs with 10-character rationale validation, dangerous-action focus policy, Escape/focus return, server-refresh conflict recovery, preserved rationale, and object-local cache invalidation.
- Built a governed Forecast workspace that reviews only approved local checkpoint catalog entries and fixed 5/20/60 horizons before creating a typed server task.
- Rendered completed Forecast records with ordered P10/P50/P90 summaries and tables, a non-animated ECharts uncertainty view, at most 12 selected drawn paths, paginated path evidence, full safe provenance, immutable record/job history, and append-only calibration.
- Appended `投资论点` and `概率预测` after the original three Analysis tabs only for stock subjects, preserving semantic roving tabs, horizontal mobile visibility, per-tab object-local state, and Portfolio behavior.
- Kept optional capability, catalog, record, task, path, calibration, pending, and check failures local so existing reports and the sibling optional panel remain independently usable.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build the complete immutable Thesis lifecycle panel** — `cf8daca84b9ee0f98dfe59854e274e2c393b0c11` (`feat`)
2. **Task 2: Build the complete probabilistic Forecast panel** — `3a07ece6c23b6b02815eba55c3ded5dc522d9333` (`feat`)
3. **Task 3: Mount stock-only Thesis and Forecast tabs without changing existing Analysis** — `d64d1a111c42a86d08797c9018bd78f39e81dd69` (`feat`)

## Files Created/Modified

- `frontend/src/components/analysis/ThesisPanel.tsx` — immutable version creation/review, complete anchors and conditions, check evidence, pending human authority, dialogs, conflict recovery, and history.
- `frontend/src/components/analysis/ForecastPanel.tsx` — approved catalog gate, typed job creation, persisted task display, quantiles, ECharts, bounded paths, provenance, records, terminal jobs, and calibration.
- `frontend/src/components/analysis/AnalysisWorkspace.tsx` — narrow stock-only tab composition with stable tab order, keyboard movement, persistent tab/scroll state, and independently mounted optional panels.

## Decisions Made

- Reused `phase5Api`, `QK.thesis`, `QK.forecast`, `QK.phase5Capabilities`, and `useForecastTask` directly; no second transport, cache, state store, chart library, route, navigation, or shell was introduced.
- Mounted optional panels behind persistent hidden semantic tabpanels. This preserves selected immutable records and form/path state across tab changes while all independent top-level queries start in the same render.
- Kept every mutation body deny-by-default. Thesis sends only typed version fields or `{rationale}`; Forecast sends only instrument context in the URL plus horizon, approved catalog ID, and idempotency key.
- Treated charts as progressive enhancement. The server-returned quantile/path/calibration facts remain inspectable through captioned, keyboard-focusable overflow tables even if canvas rendering is absent.
- Did not infer stale Forecast state without a server-projected newer governed as-of fact, and did not fabricate missing terminal jobs, actual values, descriptors, or checkpoint approvals to satisfy legacy fixtures.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Cache identity bug] Corrected optional capability query scoping**
- **Found during:** Task 3 browser and integration review
- **Issue:** The first panel draft used the pre-existing global `QK.capabilities` identity, which could collide with the unrelated core capabilities response.
- **Fix:** Both panels now share the committed `QK.phase5Capabilities` key and `/api/optional-modules` query, preserving independent Phase 05 cache ownership.
- **Files modified:** `frontend/src/components/analysis/ThesisPanel.tsx`, `frontend/src/components/analysis/ForecastPanel.tsx`
- **Verification:** `pnpm exec tsc --noEmit`; mounted browser capability fixtures
- **Committed in:** `d64d1a111c42a86d08797c9018bd78f39e81dd69`

**2. [Rule 2 - Missing critical data fidelity] Replaced synthetic Thesis assumption values with complete typed user inputs**
- **Found during:** Task 3 authority review
- **Issue:** A draft implementation represented a free-text assumption using a synthetic numeric value/unit, which would have written invented structured data.
- **Fix:** The version form now requires separate assumption name, numeric value, and unit and sends those exact reviewed values; legacy read fixtures remain display-only aliases.
- **Files modified:** `frontend/src/components/analysis/ThesisPanel.tsx`
- **Verification:** `pnpm exec tsc --noEmit`
- **Committed in:** `d64d1a111c42a86d08797c9018bd78f39e81dd69`

**3. [Rule 1 - Accessible contract bug] Disambiguated lineage headers and destructive confirmation copy**
- **Found during:** Task 3 focused browser run
- **Issue:** Repeated generic `版本` headers created an ambiguous accessible-name match, and an extra Chinese spacing character broke the exact destructive consequence sentence.
- **Fix:** The version timeline uses unambiguous `编号`/`前序记录` headers while retaining version values, and the confirmation sentence now matches the approved copy exactly.
- **Files modified:** `frontend/src/components/analysis/ThesisPanel.tsx`
- **Verification:** Scenario 7 assertion body passes end to end, including focus trap, Escape return, rationale preservation, conflict refresh, and no authority requests.
- **Committed in:** `d64d1a111c42a86d08797c9018bd78f39e81dd69`

---

**Total deviations:** 3 auto-fixed (2 correctness, 1 critical data fidelity).
**Impact on plan:** All fixes protect cache isolation, server-owned research facts, and the approved accessible copy. No route, dependency, schema, shell, or feature outside the plan was added.

## Verification

```text
cd frontend && pnpm exec tsc --noEmit
Result: PASS (no diagnostics)

cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep '独立能力|THES|论点|FORE|Forecast|预测|calibration|Responsive|跨模块'
Result: assertion bodies for scenarios 7 and 13 PASS; Playwright command exits non-zero because Wave 0 still marks every selected scenario with test.fail and therefore treats these newly passing contracts as "Expected to fail, but passed". The other eight selected scenarios remain accounted for under the inherited expected-failure gate. Plan 05-17 owns marker removal and fixture cutover.

Focused current-state smoke:
pnpm exec playwright test ... --grep 'scenario (6|7|13)'
Result: scenario 7 assertion body PASS; scenario 6 and the Shadow-prefaced scenario 13 remain expected failures under the inherited gate/fixture timing.
```

The browser run exercised real stock tab mounting, typed fixture requests, keyboard confirmation, conflict recovery, cross-module request capture, and authority prohibitions. It did not claim ordinary-green final certification while the checked-in test deliberately asserts failure; removing those markers belongs to Plan 05-17.

## Threat Mitigation Evidence

- **T-05-16-01:** Confirm/reject bodies contain only the selected pending ID in the encoded route and the user rationale. A 409 preserves the rationale, invalidates only current-instrument Thesis keys, and reloads canonical server records.
- **T-05-16-02:** Forecast creation sends only horizon, approved catalog ID, and an idempotency key. Quantiles, checkpoint revisions/digests, paths, fingerprints, job state, and record state are rendered only from server DTOs.
- **T-05-16-03:** Panels render allowlisted safe fields and never expose local paths, raw exceptions, commands, environment variables, remote `latest`, or account secrets. Long safe digests and fingerprints wrap and remain copyable.
- **T-05-16-04:** No Forecast-to-Thesis, Shadow-to-strategy, broker, position, monitor, plan, or market action control/request exists. Scenario 13's cross-module authority assertion body passes.
- **T-05-16-05:** The chart draws at most 12 selected paths; all paths remain page-inspectable through semantic tables, and quantile/provenance/calibration tables remain available without canvas.

## TDD Gate Compliance

- Tasks consume the inherited browser RED contract commit `dacd3dce130ad6d4f9a315e16ffdc7bb15c55bd9` created in Plan 05-05.
- GREEN implementation commits are `cf8daca84b9ee0f98dfe59854e274e2c393b0c11`, `3a07ece6c23b6b02815eba55c3ded5dc522d9333`, and `d64d1a111c42a86d08797c9018bd78f39e81dd69`.
- Plan 05-17 remains the intentional final gate that removes Wave 0 expected-failure markers only after all three Phase 05 panels are present.

## Known Stubs

None. Empty arrays and nulls represent bounded empty/optional server states. The implementation does not fabricate Thesis descriptors, review authority, Forecast approvals, stale state, quantiles, paths, terminal jobs, actual values, or calibration.

## Issues Encountered

- `DESIGN.md` is absent in this worktree. The implementation followed the approved `05-UI-SPEC.md`, `PRODUCT.md`, `frontend/src/index.css`, `frontend/tailwind.config.ts`, and existing Analysis/ECharts/dialog/table patterns.
- The isolated frontend initially had no materialized `node_modules`; `pnpm install --offline --frozen-lockfile` used the committed lockfile and changed no manifest or lockfile.
- The checked-in Wave 0 Playwright suite still wraps scenarios in `test.fail(true)`. Correctly passing scenario bodies therefore make the command non-zero until Plan 05-17 removes the markers. Temporary diagnostic gate edits were restored and no test file changed.
- Several Wave 0 fixtures intentionally predate the final typed projections (legacy assumption strings, symbolic operators, embedded path/calibration rows, and incomplete job lists). Read-only aliases are handled defensively; the implementation does not mutate or fabricate missing production facts.

## User Setup Required

None. No external model download, remote checkpoint, broker, secret, environment variable, or service configuration is required by this frontend plan.

## Next Phase Readiness

- Plan 05-17 can remove inherited `test.fail` markers, align legacy fixtures with final typed server projections, and run scenarios 1–13 as ordinary-green final acceptance.
- Thesis and Forecast are mounted with stable stock-only identities and use the shared typed boundary, so Plan 05-17 does not need a route, shell, state store, or API redesign.
- THES-01 and FORE-01 UI behavior is implemented; final descriptor/audit certification remains with the planned browser marker/fixture cutover.

## Self-Check: PASSED

All three implementation files and this summary exist; task commits `cf8daca84b9ee0f98dfe59854e274e2c393b0c11`, `3a07ece6c23b6b02815eba55c3ded5dc522d9333`, and `d64d1a111c42a86d08797c9018bd78f39e81dd69` resolve on `worktree-agent-05-16`; no tracked file was deleted; TypeScript compilation passes; focused browser assertion bodies reached the documented inherited marker boundary; generated browser artifacts were removed.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
