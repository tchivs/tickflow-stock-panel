---
phase: 05-optional-enhancements
plan: "05"
subsystem: acceptance-testing
tags: [pytest, fastapi, playwright, red-contract, accessibility, responsive, security]
requires:
  - phase: 01-core-merger
    provides: completed authenticated v1 FastAPI host, governed data, portfolio, monitor, decision, and root SSE loop
  - phase: 02-factor-and-strategy-research
    provides: Backtest workspace, immutable retention precedent, keyboard tabs, and semantic overflow tables
  - phase: 03-ai-analysis
    provides: object-local Analysis workspace and server-authoritative pending review lifecycle
  - phase: 04-advanced-capabilities
    provides: real-lifespan host, bounded SSE, deny-by-default DTO, and no-action spy precedents
provides:
  - strict real-host RED inventory for all eight Shadow/Thesis/Forecast availability combinations
  - exact 13-scenario Playwright contract covering all 40 approved Phase 05 UI considerations
  - fail-closed Python and Node verifiers that accept only the declared missing production surfaces
  - executable authority, object isolation, completed-v1, accessibility, responsive, motion, and no-live-action acceptance contracts
affects: [05-14, 05-15, 05-16, 05-17, SHDW-01, THES-01, FORE-01]
tech-stack:
  added: []
  patterns:
    - exact-node RED verification before production implementation
    - fixture-backed browser contracts with per-scenario missing-surface allowlists
    - object-local mutation and no-authority request capture
key-files:
  created:
    - backend/tests/test_phase5_optional_host.py
    - backend/tests/verify_phase5_host_red.py
    - frontend/e2e/phase5-optional-enhancements.spec.ts
    - frontend/e2e/verify-phase5-red-contract.mjs
    - .planning/phases/05-optional-enhancements/05-05-SUMMARY.md
  modified: []
key-decisions:
  - "The host contract uses one production app/lifespan and one operational database/data root; availability overrides are limited to independent deployment probes and failure injection."
  - "Each browser scenario has one explicit expected-failure marker and one scenario-specific missing production locator; fixture, syntax, host, browser, timeout, external-request, skip, retry, and unexpected-pass failures remain fatal."
  - "SHDW-01 and THES-01 remain descriptor-less flagged-unverified edges until the final named production host and browser scenarios pass; this plan invents no probe descriptor."
patterns-established:
  - "RED inventory gate: collect exact nodes first, then accept only an exact missing production seam and exact failure count."
  - "UI contract gate: parse Playwright JSON, require ordered scenarios 1–13, one desktop result each, and an allowlisted observable locator failure."
requirements-completed: [SHDW-01, THES-01, FORE-01]
coverage:
  - id: D1
    description: Eight availability combinations preserve a single authenticated completed-v1 host while every optional module owns an independent typed status and 503 boundary.
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run python tests/verify_phase5_host_red.py"
        status: pass
    human_judgment: false
  - id: D2
    description: Browser scenarios 1–4 specify independent placement plus immutable Shadow import, explainability, IS/OOS eligibility, terminal history, long content, and zero activation authority.
    requirement: SHDW-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#scenarios 1-4"
        status: pass
    human_judgment: false
  - id: D3
    description: Browser scenarios 5–7 specify immutable Thesis versions, valuation anchors, four check outcomes, pending-only automation, keyboard human authority, and conflict recovery.
    requirement: THES-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#scenarios 5-7"
        status: pass
    human_judgment: false
  - id: D4
    description: Browser scenarios 8–11 specify the approved checkpoint/input gate, P10/P50/P90 and 32 retained paths, immutable recovery/terminal behavior, and append-only calibration.
    requirement: FORE-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts#scenarios 8-11"
        status: pass
    human_judgment: false
  - id: D5
    description: Browser scenarios 12–13 specify responsive/accessibility/motion/theme contracts and prove cross-module mutations cannot gain authority or broadly invalidate cache state.
    verification:
      - kind: automated_ui
        ref: "cd frontend && node e2e/verify-phase5-red-contract.mjs"
        status: pass
    human_judgment: false
metrics:
  duration: 15m 20s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 05: Cross-Module Host and Browser RED Contracts Summary

**Exact real-host and Playwright RED gates now inventory eight module combinations and all 13 approved UI scenarios while rejecting every failure outside the intentionally missing Phase 05 production seams.**

## Performance

- **Duration:** 15m 20s
- **Started:** 2026-07-16T03:43:57Z
- **Completed:** 2026-07-16T03:59:17Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Added a 12-node real-lifespan host contract: eight availability combinations plus local failure isolation, hostile authority/foreign-ID rejection, zero live-action collaborators, and one-runtime database/lake/scheduler identity.
- Added exactly 13 fixture-backed Playwright scenarios mapping one-to-one to UI-SPEC scenarios 1–13 and exercising all 40 approved state considerations, exact copy, immutable histories, object-bound mutations, responsive geometry, semantics, focus, contrast, reduced motion, and chart/table equivalence.
- Added strict Python and Node verifiers that first inventory exact tests, then accept only the declared missing `app.optional_modules` seam or scenario-specific missing production locator; syntax, collection, fixture, browser/server launch, unexpected request, retry, skip, timeout, changed inventory, and unexpected pass are fatal.
- Preserved the descriptor-less flagged-unverified treatment for SHDW-01 and THES-01 while encoding executable evidence required to close those assumptions in Plan 05-17.

## Task Commits

1. **Task 1: Specify every optional-module host combination and preserve the completed v1 loop** — `d7e3df2` (`test`)
2. **Task 2: Encode all 13 browser scenarios and the 40 covered UI considerations** — `dacd3dc` (`test`)

## Files Created/Modified

- `backend/tests/test_phase5_optional_host.py` — Parameterized eight-combination real-lifespan, completed-v1, isolation, authority, single-runtime, and no-action RED contracts.
- `backend/tests/verify_phase5_host_red.py` — Exact-node pytest collector/executor that accepts only the missing optional-host/factory seam.
- `frontend/e2e/phase5-optional-enhancements.spec.ts` — Deterministic route/SSE fixtures and exactly 13 observable browser scenarios covering the approved UI contract.
- `frontend/e2e/verify-phase5-red-contract.mjs` — Playwright JSON verifier with exact scenario ordering and per-scenario missing-locator allowlists.
- `.planning/phases/05-optional-enhancements/05-05-SUMMARY.md` — Plan outcome, evidence, decisions, deviations, and downstream handoff.

## Decisions Made

- Host combination tests never construct an alternate FastAPI app: they start the existing production `app.main.app` lifespan and restrict overrides to deployment probe/failure seams.
- Browser contracts use deterministic local API/SSE fixtures, record every mutation and request, and deny provider/model/broker/market-action traffic; UI copy alone never certifies authority.
- Expected failure is scenario-local and temporary. The verifier requires `expectedStatus=failed` plus an actual missing-locator failure for the approved production surface; Plan 05-17 removes all expected-failure markers.
- The accessibility contract is observable: semantic roles, native fields, captions/headers, focus trap/return, touch geometry, computed typography, contrast, overflow, reduced-motion transition state, and equivalent tables are asserted in browser behavior.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Matched Playwright JSON files by reporter basename**
- **Found during:** Task 2 focused RED verification
- **Issue:** Playwright 1.61 reports each spec file as `phase5-optional-enhancements.spec.ts`, while the verifier initially compared it with the invocation path `e2e/phase5-optional-enhancements.spec.ts`, incorrectly producing an empty scenario inventory.
- **Fix:** Added an explicit basename derived from the fixed spec path and retained the exact ordered 13-title comparison.
- **Files modified:** `frontend/e2e/verify-phase5-red-contract.mjs`
- **Verification:** `cd frontend && node e2e/verify-phase5-red-contract.mjs`
- **Committed in:** `dacd3dc`

**Total deviations:** 1 auto-fixed (1 Rule 1 verifier bug).
**Impact on plan:** The fix narrows report parsing to the actual Playwright schema without weakening any failure allowlist or scenario requirement.

## Issues Encountered

- Playwright emits per-expected-failure `test-results/` diagnostics. These runtime artifacts were inspected and removed after both focused verifier runs; no generated output remains in the deliverable.
- The production Phase 05 host and panels are intentionally absent at Wave 0. Both strict harnesses accepted only that exact missing surface and rejected arbitrary RED as required.

## Verification

```text
cd backend && uv run python tests/verify_phase5_host_red.py
Phase 05 host RED contract accepted: 12 exact nodes; only the declared app.optional_modules production seam is missing.

cd frontend && node e2e/verify-phase5-red-contract.mjs
Phase 05 Playwright RED contract accepted: 13 exact scenarios; only allowlisted missing production surfaces failed.
```

## Threat Evidence

- **T-05-05-01:** Eight parameter IDs are mandatory, each starts the real lifespan and executes completed-v1 data/portfolio/monitor/decision/root-SSE checks; changed nodes or unrelated startup failures are rejected.
- **T-05-05-02:** Host and browser payloads explicitly inject principal/fingerprint/digest/verdict/status fields and require rejection; request capture forbids client authority fields.
- **T-05-05-03:** Strategy install, monitor, decision plan, position, manual ledger, broker, provider network, and market-action spies/requests remain zero across retention, review, forecast, calibration, terminal, and unavailable paths.
- **T-05-05-04:** Public projections and DOM assertions reject local paths, account secrets, worker commands, raw exceptions, stack traces, model internals, and unsafe fields.
- **T-05-05-05:** Forecast reconnect and terminal scenarios preserve committed server state, while scenario 13 accepts only object-local Phase 05 query activity after each mutation.

## Known Stubs

None. These are deliberate failing-first acceptance contracts, not production placeholders. Every fixture is connected to an observable request/DOM assertion, and both verifiers require the exact intentionally missing production surface.

## Threat Flags

None. This plan adds test and verification artifacts only; it introduces no production endpoint, authentication path, file-access surface, datastore, queue, or external network boundary.

## TDD Gate Compliance

This Wave 0 contract plan intentionally ends at the RED gate. Commits `d7e3df2` and `dacd3dc` are failing-first test contracts whose strict wrapper commands pass only for the approved missing production surfaces. Plans 05-14 through 05-17 own GREEN production implementation and removal of expected-failure allowances; adding a GREEN production commit here would violate the plan boundary.

## User Setup Required

None. Verification uses existing local pytest, FastAPI TestClient, Playwright Chromium, and Vite infrastructure and performs no model/provider/network request.

## Next Phase Readiness

- Plan 05-14 can implement `app.optional_modules`, independent typed status/503 behavior, one-lifespan factories/scanners/recovery, and make the host matrix ordinary green.
- Plans 05-15 and 05-16 can bind production Shadow/Thesis/Forecast panels directly to the exact fixture routes, locators, copy, semantics, request bodies, and object-local invalidation contract.
- Plan 05-17 must remove every expected-failure/missing-surface allowance and run all 12 host nodes plus 13 browser scenarios as ordinary green acceptance without diluting the inventories.

## Self-Check: PASSED

- Found all four created test/verifier artifacts and this summary on disk.
- Found task commits `d7e3df2` and `dacd3dc` as reachable commits.
- Confirmed no generated `frontend/test-results/` artifact remains.
- Re-ran both strict focused RED verifiers successfully after the task commits.
