---
phase: 19-guest-access
plan: 2
subsystem: ui
tags: [guest-access, masking, react, typescript, playwright, pool-hub]

# Dependency graph
requires:
  - phase: 19-01
    provides: GET /api/pool/hub top-level `mode` (guest|vip), masked guest rows (code/name/symbol = ******, open_gap omitted), `name` projected on every row
provides:
  - Guest/VIP presentation layer on PoolHubPage driven exclusively by the server `mode` field (GUEST-01 frontend)
  - GuestModeBanner (role=status, exact 19-UI-SPEC copy) rendered only in guest mode
  - Guest 5-column set (代码|名称|涨跌幅|概念板块|关联因子 — 开盘涨幅 hidden) with masked `******` cells rendered verbatim
  - VIP 6-column set (代码|名称|开盘涨幅|涨跌幅|概念板块|关联因子) with 明文 name + board tag + PctCell
  - Provable no-client-masking boundary: grep guard over frontend/src + strategy-scoped row keys (no duplicate-key pageerror)
  - Visual evidence for the four UI-SPEC backstop scalars (guest-grid, guest-masked, vip-plaintext screenshots)
affects: [verify-work, ui-review, /gsd-ship]

actuals:
  tokens: 8146        # chars/4 over the realized text diff (32583 chars, 5 text files +340 -32, excludes binary PNGs)
  tasks: 3
  commits: 3          # 2 task commits + final docs commit

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Server-declared presentation mode: mode read ONLY from response.mode; a missing/unknown mode safely defaults to vip (never derived from row values)"
    - "Masked cells render row.code/row.name verbatim (mono muted) — zero client-side masking logic, zero `******` literal in src"
    - "Guest row keys = strategy-scoped ordinal (${strategy.id}-${index}); VIP keeps row.symbol — duplicate-key safe for many shared ****** rows"
    - "e2e grep guard audits pool-hub sources for masked literal / row-derived mode / mask identifier"

key-files:
  created:
    - frontend/src/components/pool-hub/GuestModeBanner.tsx
    - frontend/e2e/pool-hub.spec.ts-snapshots/pool-guest-grid-desktop-chromium-linux.png
    - frontend/e2e/pool-hub.spec.ts-snapshots/pool-guest-masked-desktop-chromium-linux.png
    - frontend/e2e/pool-hub.spec.ts-snapshots/pool-vip-plaintext-desktop-chromium-linux.png
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/pages/PoolHubPage.tsx
    - frontend/src/components/pool-hub/StockListTable.tsx
    - frontend/e2e/pool-hub.spec.ts
    - frontend/e2e/pool-hub.spec.ts-snapshots/pool-table-resonance-desktop-chromium-linux.png (regenerated to 6-col)
    - frontend/e2e/pool-hub.spec.ts-snapshots/pool-table-filter-active-desktop-chromium-linux.png (regenerated to 6-col)

key-decisions:
  - "Presentation mode is consumed ONLY from response.mode; PoolHubPage defaults a missing/unknown mode to vip so the page never masks by default and never infers mode from row values (T-19-07)."
  - "Guest masked cells are inert text (no title/aria-label/tooltip/copy affordance) so the real identity never reaches the DOM (T-19-08)."
  - "Guest rows are keyed by strategy-scoped ordinal, never the masked symbol, so many ****** rows stay distinct with no duplicate React keys (T-19-10)."
  - "The 开盘涨幅 header + cells render only when mode === 'vip' (T-19-09)."

patterns-established:
  - "GuestModeBanner: role=status + aria-label exact copy, Lock aria-hidden, neutral info banner (bg-elevated/60 border-border rounded-btn), overflow-wrap:anywhere"
  - "StockListTable mode prop drives GUEST_COLUMNS vs VIP_COLUMNS + masked-cell rendering + row keys"
  - "e2e fixture convention: guest fixtures hold the only ****** literals (server-masked output assertions); production src has none"

requirements-completed: [GUEST-01, GUEST-02]

coverage:
  - id: D1
    description: "Guest mode renders server-masked rows verbatim (****** in 代码/名称), the exact GuestModeBanner, and the 5-column guest set with no 开盘涨幅 column"
    requirement: GUEST-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#guest mode renders banner, masked cells, and the 5-column guest set"
        status: pass
    human_judgment: false
  - id: D2
    description: "Guest banner still renders on a guest empty hub (session-policy state, not data state)"
    requirement: GUEST-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#guest empty hub still renders the guest banner (session-policy state)"
        status: pass
    human_judgment: false
  - id: D3
    description: "VIP mode renders 明文 rows (real code + board tag, real name, 开盘涨幅 PctCell) with the 6-column set and no banner"
    requirement: GUEST-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#vip mode renders 明文 with 名称 and 开盘涨幅"
        status: pass
    human_judgment: false
  - id: D4
    description: "guest↔vip mode switch toggles the 开盘涨幅 column purely from the server mode field, with no duplicate-key pageerror/console error across many shared ****** rows"
    requirement: GUEST-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#guest↔vip mode switch toggles the 开盘涨幅 column from the server mode field"
        status: pass
    human_judgment: false
  - id: D5
    description: "No client-side masking code anywhere in frontend/src: no masked literal, no row-value mode derivation, no mask identifier/function (grep guard)"
    requirement: GUEST-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#frontend contains no client-side masking code (grep guard)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Guest banner accessibility + copy contract: role=status, accessible name exactly 游客模式：股票代码与名称已脱敏，仅展示涨跌幅与概念板块。, masked cells are real non-blank non-— text nodes with no title/aria-label leak"
    requirement: GUEST-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#guest accessibility and copy contract"
        status: pass
    human_judgment: false
  - id: D7
    description: "交叉共振 badge + legend + accent highlight remain visible to guests (hit_factors are strategy labels, not PII)"
    requirement: GUEST-02
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#guest 交叉共振 badge and legend remain visible"
        status: pass
    human_judgment: false
  - id: D8
    description: "Visual evidence for the four UI-SPEC backstop scalars: (1) guest banner coexists with card grid, (2) long strategy names still truncate with the banner present, (3) many masked rows remain visually distinct, (4) guest↔vip column-set shift without page reflow"
    requirement: GUEST-01
    verification:
      - kind: automated_ui
        ref: "frontend/e2e/pool-hub.spec.ts-snapshots/pool-guest-grid-desktop-chromium-linux.png"
        status: pass
      - kind: automated_ui
        ref: "frontend/e2e/pool-hub.spec.ts-snapshots/pool-guest-masked-desktop-chromium-linux.png"
        status: pass
      - kind: automated_ui
        ref: "frontend/e2e/pool-hub.spec.ts-snapshots/pool-vip-plaintext-desktop-chromium-linux.png"
        status: pass
    human_judgment: true
    rationale: "The four backstops are held-out visual scalars; screenshots are captured and the e2e toHaveScreenshot assertions pass, but the end-of-phase human gate must visually confirm distinctness/reflow per the plan's Task 3 human-check."

# Metrics
duration: ~25min
completed: 2026-08-04
status: complete
---

# Phase 19 Plan 2: Guest/VIP Presentation Layer (Frontend) Summary

**PoolHubPage is now mode-aware from the server `mode` field: guest sessions render the exact GuestModeBanner, server-masked `******` cells verbatim, and the 5-column guest set (开盘涨幅 hidden), while VIP sessions render 明文 with 名称 and 开盘涨幅 — with a provable zero-client-masking boundary (grep guard) and full Phase-18 interactions (drill-down, concept filter, 交叉共振) unchanged in both modes.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3
- **Files modified:** 6 text + 5 snapshot PNGs (3 new, 2 regenerated)
- **Commits:** 2 task commits + final docs commit
- **Verify:** `npx tsc --noEmit` exit 0; `npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium` → **24 passed**

## Accomplishments

- **Server-declared mode plumbing (GUEST-01):** `PoolHubResponse.mode: 'guest' | 'vip'` and `PoolHubRow.name: string` added to `api.ts`; `PoolHubPage` derives `mode = data?.mode === 'guest' ? 'guest' : 'vip'` — a missing/unknown mode safely defaults to vip, and mode is never inferred from row values (T-19-07).
- **GuestModeBanner (new):** `role="status"`, `aria-label` = exact UI-SPEC accessible text, `Lock` icon `aria-hidden`, neutral info banner (`bg-elevated/60 border-border rounded-btn`), title `游客模式：股票代码与名称已脱敏` + body `仅展示涨跌幅与概念板块。` with `overflow-wrap:anywhere`. Rendered only when `data && mode === 'guest'` — never during loading (mode unknown) or error (no flash).
- **StockListTable mode-driven presentation:** guest 5-column set (`代码|名称|涨跌幅|概念板块|关联因子`) hides 开盘涨幅 entirely; VIP 6-column set includes it. Guest 代码/名称 cells render `row.code`/`row.name` verbatim (mono `num tabular-nums text-muted`, no board tag); VIP renders board tag + real code and 名称 as sans `text-foreground truncate` (missing → `—`). Guest rows keyed `${strategy.id}-${index}`; VIP keeps `row.symbol` (T-19-10).
- **No-client-masking boundary proven:** the e2e grep guard audits `PoolHubPage.tsx`, `GuestModeBanner.tsx`, `StockListTable.tsx`, `ConceptFilter.tsx`, `StrategyCardGrid.tsx`, `api.ts` for the `******` literal, row-value mode-derivation, and mask identifiers — none exist (T-19-07, PITFALL #8).
- **Visual evidence:** 3 new snapshots (guest-grid, guest-masked, vip-plaintext) + 2 regenerated VIP baselines (resonance, filter-active) lock the four UI-SPEC backstop scalars for the end-of-phase human gate.

## Task Commits

1. **Task 1: Mode plumbing + GuestModeBanner + masked-cell rendering (tracer)** - `20907ee` (feat)
2. **Task 2: VIP 明文 presentation + guest↔VIP mode switching + 交叉共振/概念/因子 unchanged** - `6296c33` (test — e2e additions shared with Task 1/3, see deviation 1)
3. **Task 3: No-client-masking grep guard + a11y/copy compliance + visual evidence** - `6296c33` (test — same shared e2e commit)
4. **Final metadata commit** - (docs) — this SUMMARY + STATE.md/ROADMAP.md

**Plan baseline:** `8359a59` (`docs(19-01): complete guest masking backend plan`)

## Files Created/Modified

- `frontend/src/lib/api.ts` - `PoolHubRow.name: string`; `PoolHubResponse.mode: 'guest' | 'vip'`.
- `frontend/src/components/pool-hub/GuestModeBanner.tsx` (new) - guest policy banner, `role="status"`, exact 19-UI-SPEC copy, no dismiss.
- `frontend/src/pages/PoolHubPage.tsx` - `mode` derivation from server field; `<GuestModeBanner />` after the error block gated on `data && mode === 'guest'`; passes `mode` to StockListTable.
- `frontend/src/components/pool-hub/StockListTable.tsx` - `mode` prop; `GUEST_COLUMNS`/`VIP_COLUMNS`; masked-cell rendering; 名称 column; 开盘涨幅 VIP-only; strategy-scoped guest row keys.
- `frontend/e2e/pool-hub.spec.ts` - `mode:'vip'` + `name` on all VIP fixtures; `hubPayloadGuest`/`emptyHubPayloadGuest`/guest row fixtures; 24 tests including guest banner/masked/5-col, guest empty banner, VIP 明文, guest↔vip mode switch (no duplicate-key pageerror), guest 交叉共振, grep guard, guest a11y/copy, guest visual evidence.
- Snapshot PNGs - `pool-guest-grid`, `pool-guest-masked`, `pool-vip-plaintext` (new); `pool-table-resonance`, `pool-table-filter-active` (regenerated to the 6-column VIP layout).

## Decisions Made

- Presentation mode is consumed **only** from `response.mode`; unknown/missing mode defaults to `vip` so the page never masks by default (T-19-07).
- Guest masked cells are **inert text** — no `title`/`aria-label`/tooltip/copy affordance carries the real identity into the DOM (T-19-08).
- Guest rows keyed by **strategy-scoped ordinal** — never the masked symbol — so many `******` rows stay distinct with no duplicate React keys (T-19-10).
- 开盘涨幅 column (header + cells) renders **only** when `mode === 'vip'` (T-19-09).
- The `******` literal exists only in e2e fixtures asserting server-masked output; production `frontend/src` has none (PITFALL #8).

## Deviations from Plan

### Auto-fixed Issues

**1. [Commit grouping — shared e2e file] Tasks 2 and 3 committed together with Task 1's e2e proof in `6296c33`**
- **Found during:** Task boundary — the plan's Tasks 1–3 all modify the single file `frontend/e2e/pool-hub.spec.ts` (fixtures are shared; the tracer gate requires the full suite green at the tracer commit).
- **Issue:** A per-task split of the spec is not feasible without fragmenting shared fixtures/assertions and breaking the tracer gate (the tracer's `<verify>` runs the whole spec).
- **Fix:** Task 1's source (api.ts, GuestModeBanner.tsx, PoolHubPage.tsx, StockListTable.tsx) committed as `20907ee` (feat); the e2e spec + all snapshot PNGs (guest/VIP/mode-switch tests, grep guard, a11y, visual evidence for Tasks 1–3) committed as `6296c33` (test).
- **Files modified:** frontend/e2e/pool-hub.spec.ts, snapshot PNGs
- **Verification:** 24/24 e2e green after `6296c33`.
- **Committed in:** `20907ee`, `6296c33`

**2. [Rule 1 - Bug] Edit-tool range misalignment dropped `rows` (StockListTable) and `asOf` (PoolHubPage)**
- **Found during:** Task 1 — first `npx tsc --noEmit` after edits reported TS2304 (`Cannot find name 'rows'` / `'asOf'`).
- **Issue:** Two `SWAP` hunks replaced destructure/const lines and dropped a kept line each.
- **Fix:** Restored `rows,` in the StockListTable destructure and `const asOf = data?.as_of ?? null` in PoolHubPage.
- **Files modified:** frontend/src/components/pool-hub/StockListTable.tsx, frontend/src/pages/PoolHubPage.tsx
- **Verification:** `npx tsc --noEmit` exit 0.
- **Committed in:** `20907ee`

**3. [Rule 1 - Bug] Stale Phase-18 `pool-table-resonance.png` baseline; Playwright's dark-theme pixelmatch was too lenient to catch the 5→6 column shift**
- **Found during:** Task 3 visual evidence — the five-backstops test passed against the OLD 5-column baseline even though the render is now 6 columns (threshold-30 diff 4.8% vs `maxDiffPixelRatio: 0.02`; pixelmatch ignores many near-black background deltas).
- **Issue:** The committed baseline did not reflect the new 名称 column; visual evidence would be misleading.
- **Fix:** Force-regenerated the baseline (deleted, then `--update-snapshots`) so `pool-table-resonance.png` reflects the 6-column VIP layout (verified via header-band analysis: 6 text bands).
- **Files modified:** frontend/e2e/pool-hub.spec.ts-snapshots/pool-table-resonance-desktop-chromium-linux.png
- **Verification:** full suite green; baseline now 6-column.
- **Committed in:** `6296c33`

**4. [Rule 1 - Bug] Production-source comments initially contained the `******` literal**
- **Found during:** Task 1 — would violate the plan's own grep guard ("no `******` literal in production source").
- **Issue:** Doc comments in `api.ts` and `GuestModeBanner.tsx` referenced the mask string.
- **Fix:** Reworded comments to describe 脱敏 policy without the literal.
- **Files modified:** frontend/src/lib/api.ts, frontend/src/components/pool-hub/GuestModeBanner.tsx
- **Verification:** grep-guard e2e passes.
- **Committed in:** `20907ee`

---

**Total deviations:** 4 auto-fixed (1 commit grouping + 3 Rule-1 fixes)
**Impact on plan:** No scope creep; all fixes keep the plan's own acceptance criteria and the e2e suite green.

## Issues Encountered

- Playwright 1.61 `toHaveScreenshot` with `maxDiffPixelRatio: 0.02` on a dark theme can accept a 5→6 column layout change (~4.8% threshold-30 diff) because most background pixels stay near-black; the stale baseline was force-regenerated so visual evidence is accurate.
- `CI=1` is set in this shell, so Playwright does not `reuseExistingServer`; stale Vite processes on port 4173 had to be `pkill`ed between runs.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The full pool-hub surface works under both server-declared modes; Phase-18 interactions (drill-down, concept filter, refresh, 交叉共振, zero-execution) remain green in both modes.
- Visual evidence (guest-grid / guest-masked / vip-plaintext) is ready for the end-of-phase human gate on the four UI-SPEC backstop scalars.
- The backend contract (19-01) and frontend presentation (19-02) together close GUEST-01/GUEST-02; remaining work is the verifier's goal-backward check and the UI review.

---
*Phase: 19-guest-access*
*Completed: 2026-08-04*

## Self-Check: PASSED

- All 4 plan source files + e2e spec + SUMMARY + 3 new snapshot PNGs exist on disk (verified via `[ -f ]`).
- Task commits `20907ee` (feat) and `6296c33` (test) present in `git log`.
- Plan verify command green: `npx tsc --noEmit` exit 0; `npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium` → **24 passed**.
