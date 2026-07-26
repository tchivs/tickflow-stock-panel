---
phase: 02
slug: factor-and-strategy-research
status: planned-gap-closure
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-11
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for the FACT-03 strategy-retention gap closure in `02-08-PLAN.md`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Playwright Test 1.61.1 and TypeScript/Vite build validation |
| **Config file** | `frontend/playwright.config.ts` |
| **Quick run command** | `pnpm --dir frontend build` |
| **Full phase-closure command** | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` |
| **Estimated runtime** | Not yet measured; the command is scoped to one Phase 2 spec and one browser project. |

---

## Sampling Rate

- **After Task 1:** Run `pnpm --dir frontend build` after the typed SSE handle lifecycle changes.
- **After Task 2:** Run `pnpm --dir frontend build` after the retention mutation, UI states, query invalidation, and strategy-mode composition changes.
- **After Task 3:** Run `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium`.
- **After Plan 02-08:** Run the build command followed by the full phase-closure command.
- **Before Phase 2 re-verification:** Both commands must pass; do not substitute the project-wide suite for these focused proofs.
- **Max feedback latency:** One frontend build or one deterministic single-spec browser run; record observed duration in `02-08-SUMMARY.md` after execution.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-08-01 | 08 | 5 | FACT-03 | T-02-08-01 | Only a matching server `research` SSE event can supply the non-empty execution handle that survives matching successful completion; new, malformed, failed, cancelled, and reconnect-created tasks have no trusted handle. | typecheck + browser integration | `pnpm --dir frontend build` and `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` | ✅ | ⬜ pending |
| 02-08-02 | 08 | 5 | FACT-03 | T-02-08-02 through T-02-08-06 | Retention submits only the task-owned server handle, is explicit and single-flight, refreshes experiment/candidate queries after success, and leaves rejected executions retryable but unretained. Each existing dense semantic result table keeps its hint and table structure while its `overflow-x-auto` wrapper becomes Tab-focusable, descriptively labeled `每日交易结果表，可使用左右方向键或 End 键查看全部列` or `交易明细结果表，可使用左右方向键或 End 键查看全部列`, visibly focus-ringed, and keyboard-scrollable with Arrow keys, End, and Home. | typecheck + browser integration | `pnpm --dir frontend build` and `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` | ✅ | ⬜ pending |
| 02-08-03 | 08 | 5 | FACT-03 | T-02-08-01, T-02-08-02, T-02-08-05 | Deterministic fixtures prove positive retention, stale/already-retained rejection, no-handle/error/cancelled non-promotion, query refresh, and the complete UI-SPEC Scenario 5 keyboard matrix at 1440px, 1024px, and 375px: factor and strategy flows, real mode/result tabs, comparison candidates, table pagination, evidence disclosures, 44px retention geometry, and narrow-table access. At 375px, Tab focuses `每日交易结果表，可使用左右方向键或 End 键查看全部列` with visible focus treatment; ArrowRight then End send real keyboard input to its implemented handler, prove `scrollLeft` changes without test-driven scrolling or `page.evaluate`, and prove the far-side `累计收益` header is visible/reachable. | Playwright end-to-end | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Focused Scenario Ledger

| Gap check | Fixture and observable proof | Command |
|-----------|------------------------------|---------|
| SSE-handle preservation | A strategy stream emits fixed `research` with the sole opaque handle before matching successful `done`; the retention POST path contains that handle and the UI cannot enable retention earlier. | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` |
| Explicit retention and query refresh | The dedicated 1440px positive lifecycle activates `保留此完成策略实验以供比较`; it observes pending then retained status, returned immutable experiment in `实验历史`, refreshed completed-only candidate list, and explicit side-by-side selection with the pre-retained fixture. | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` |
| No handle, error, and cancelled states | Exercise independent successful-without-`research`, SSE `error`, and cancelled stream fixtures; each displays its approved missing-handle/terminal diagnostic, offers no retention CTA, and yields no new candidate. | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` |
| Stale/already-retained server rejection | After a valid `research` plus successful `done`, make retain POST return HTTP 409 with `执行句柄已过期或已保留`; assert exact `role="alert"` retry copy, restored CTA, no retained status or experiment ID, no history/candidate promotion, and exactly one POST without automatic retry. | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` |
| Scenario 5 keyboard matrix — 1440px | The deterministic keyboard-only helper runs the factor validate/save/evaluate/retain flow and all six evidence disclosures; runs strategy SSE completion plus explicit retention; Arrow-navigates real mode/result tabs; Space-selects two comparison candidates and opens comparison evidence disclosure; keyboard-paginates the multi-page strategy table with visible range/current-page and focus proof. | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` |
| Scenario 5 keyboard matrix — 1024px | The same deterministic keyboard-only helper independently proves factor flow and disclosures, successful explicit strategy retention, real mode/result tabs, two comparison candidates plus disclosure, and focused table pagination with updated range/current-page at exactly 1024px. | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` |
| Scenario 5 keyboard matrix — 375px | The same deterministic keyboard-only helper independently proves factor flow and disclosures, successful explicit strategy retention, real mode/result tabs, two comparison candidates plus disclosure, and focused table pagination at exactly 375px. It measures the retention action at least 44px wide/high, then uses Tab—not pointer focus—to focus `每日交易结果表，可使用左右方向键或 End 键查看全部列`; asserts its visible focus treatment and `scrollWidth > clientWidth`; sends ArrowRight and End as real keyboard interaction to the implemented handler; asserts `scrollLeft` changes without `page.evaluate`, setting `scrollLeft`, or test-driven scrolling; and proves the far-side `累计收益` header is visible/reachable. | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` |

The responsive scenario is the approved `02-UI-SPEC.md` Verification Scenario 5. Its three-viewport matrix deliberately uses the existing desktop project with explicit viewport changes, rather than introducing a second fixture or browser-project convention.

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements:

- [x] `frontend/playwright.config.ts` — local Vite web server and existing `desktop-chromium` project.
- [x] `frontend/e2e/phase2-research.spec.ts` — existing deterministic Phase 2 route-fixture suite; Task 3 extends this file.
- [x] `frontend/package.json` — `build` script and pinned Playwright Test dependency.

No package installation, test framework scaffold, network credential, external database, or production-data setup is required.

---

## Manual-Only Verifications

All required Phase 02 gap-closure behaviors have deterministic automated coverage. Browser assertions must use accessible role/name selectors, native keyboard events, and DOM geometry rather than screenshot-only inspection.

---

## Validation Sign-Off

- [x] All planned tasks have an automated command.
- [x] Sampling continuity: each implementation task is followed by a focused build or browser command.
- [x] Existing infrastructure covers all test references; no Wave 0 work is missing.
- [x] No watch-mode flags are used.
- [x] The browser command is constrained to one deterministic Phase 2 spec and the existing desktop project.
- [ ] Record observed command durations and green status in `02-08-SUMMARY.md` after implementation.
- [x] `nyquist_compliant: true` is set in frontmatter.

**Approval:** pending execution
