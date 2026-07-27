# Phase 05 — UI Review

**Audited:** 2026-07-27
**Previous baseline:** `bc00d16a21c5399cbe3e45ae6d048e21ceea8e66`
**Audited HEAD:** `750c46da46f529cc3464213de06261c432fdb5bd`
**Design baseline:** approved `05-UI-SPEC.md`
**Screenshots:** not captured — no dev server responded on ports 3000, 5173, or 8080
**Audit scope:** adversarial re-audit of the previously registered UI-01 through UI-10 findings only

All ten previously registered implementation findings are closed on the audited
HEAD. The fixes are covered by source evidence and the merged Phase 05 browser
contracts. The reported verification run is green: backend Forecast 39 passed,
TypeScript passed, Phase 05 fixture Playwright 33/33 passed, and real-host
Playwright 1/1 passed.

Because no rendered screenshots were available, the score does not award 4/4
for perceptual composition, whole-page color distribution, or zoom/adjacent
target spacing. Those are non-blocking human-review flags, not open
implementation defects.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Typed Forecast recovery actions, endpoint deltas, exact Thesis overdue copy, and dependency announcements now meet the contract. |
| 2. Visuals | 3/4 | Forecast history and mature actual series are truthfully populated or omitted, but rendered chart composition still requires a screenshot review. |
| 3. Color | 3/4 | Availability indicators now use neutral foreground/secondary tokens; whole-page 60/30/10 distribution remains unverified without screenshots. |
| 4. Typography | 4/4 | Ordinary Forecast and Thesis form labels/legends are 400 weight; 600 is retained for headings, key status, and primary actions. |
| 5. Spacing | 3/4 | Undeclared component rhythms were normalized and the Shadow selector has a 44×44px target; 200% zoom and adjacent-target spacing still require rendered review. |
| 6. Experience Design | 4/4 | Dependent-field resets, per-field accessible errors, first-invalid focus, overdue state, governed chart context, and typed recoveries are implemented and directly tested. |

**Overall: 21/24**

**Shipping verdict: PASS.** 0 blockers, 0 open implementation warnings, and
3 non-blocking rendered human-review flags.

---

## Top 3 Priority Fixes

No further code fix is required for UI-01 through UI-10. Before final visual
sign-off, complete these non-blocking rendered checks:

1. **Review the populated Forecast chart at 1440/1024/375px** — confirm history,
   quantile band, P50, mature actual, and selected paths remain perceptually
   distinct and that the conditional legend wraps without collision.
2. **Review full-page light/dark color distribution** — confirm the now-neutral
   availability indicators preserve the intended 60/30/10 balance and that
   accent remains concentrated on actions, selection, focus, evidence links,
   P50, and its uncertainty band.
3. **Review at 200% zoom and narrow-screen touch spacing** — confirm the fixed
   44×44px Shadow batch target and adjacent controls do not overlap or obscure
   table scroll affordances.

---

## UI-01–UI-10 Closure Register

| ID | Previous severity | Status | Closure evidence | Human review |
|----|-------------------|--------|------------------|--------------|
| UI-01 | WARNING | **CLOSED** | `governedPriceContext` validates record-bound history; `matureActualRows` derives evaluated actuals; `ForecastChart` conditionally renders and names only available series (`ForecastPanel.tsx:300-335`, `721-773`). Browser contracts assert both populated and governed-history-missing cases. | true — perceptual chart composition |
| UI-02 | WARNING | **CLOSED** | `QuantileSummary` calculates absolute and percentage endpoint change from governed `as_of_close`, with an explicit safe fallback when absent (`ForecastPanel.tsx:676-700`). `ForecastPriceContext` is exposed by the typed client (`phase5Api.ts:565-570`, `804-806`). | false |
| UI-03 | WARNING | **CLOSED** | The source registry constrains fields/units/operators; source changes reset incompatible dependencies and threshold, then announce the change through a polite status region (`ThesisPanel.tsx:53-81`, `742-779`). | false |
| UI-04 | WARNING | **CLOSED** | Conditions now join their latest check result and render the exact overdue message `检查已逾期，等待调度恢复。` when the current schedule is past due (`ThesisPanel.tsx:688-705`). | false |
| UI-05 | WARNING | **CLOSED** | The visible 20px checkbox is wrapped by a focus-visible `min-h-11 min-w-11` label target (`ShadowAccount.tsx:524`); the 375px browser contract asserts its accessible name, focus, and target size. | true — 200% zoom/adjacent spacing |
| UI-06 | WARNING | **CLOSED** | Terminal jobs map to distinct catalog, governed-input, worker, artifact-integrity, and output-shape recovery copy/actions (`ForecastPanel.tsx:616-673`); browser assertions cover all six fixture terminal rows and each recovery control. | false |
| UI-07 | WARNING | **CLOSED** | Shadow, Thesis, and Forecast availability indicators now use foreground/secondary and neutral surface/border tokens rather than accent (`ShadowAccount.tsx:407-413`; `ThesisPanel.tsx:664`; `ForecastPanel.tsx:601`). | true — full-page 60/30/10 distribution |
| UI-08 | WARNING | **CLOSED** | Ordinary Forecast labels and Thesis legends use `font-normal`; remaining semibold usage is confined to headings, key states, and primary actions (`ForecastPanel.tsx:554-555`; `ThesisPanel.tsx:781-782`). | false |
| UI-09 | WARNING | **CLOSED** | The prior `gap-3`, component `p-3`, `mt-5`, and `p-5` rhythms were removed from Phase 05 components. The only remaining `p-3` is a dense-table empty cell, within the approved table exception (`ThesisPanel.tsx:728`). | true — rendered rhythm/zoom check, shared with UI-05 |
| UI-10 | WARNING | **CLOSED** | `failDraft` focuses the first invalid control; `fieldProps` adds per-control `aria-invalid` and `aria-describedby` relationships (`ThesisPanel.tsx:495-595`, `737-740`). Browser coverage directly asserts invalid-condition focus and relationships. | false |

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)

- **Pass — UI-02/UI-04/UI-06 closed.** Forecast endpoint cards state the
  target session plus signed absolute/percentage change, Thesis uses the exact
  overdue-state sentence, and Forecast terminal failures provide
  category-specific recovery actions rather than a generic paragraph.
- The recovery mapping distinguishes catalog/checkpoint, governed input,
  worker/resource, artifact integrity, and output structure
  (`ForecastPanel.tsx:616-673`).
- The merged Playwright contract asserts the endpoint sentence, exact overdue
  sentence, five typed terminal headings, and the catalog/input/retry/copy
  actions (`phase5-optional-enhancements.spec.ts:964-977`,
  `1090-1094`, `1112-1134`).

### Pillar 2: Visuals (3/4)

- **Pass — UI-01/UI-02 closed.** Forecast history comes only from verified,
  record-bound governed input; actual points come only from evaluated,
  identity-complete calibration rows. The chart builds a unified session
  timeline and omits unavailable legend, series, and ARIA claims
  (`ForecastPanel.tsx:300-335`, `721-773`).
- The server projection verifies the managed artifact descriptor and checksum,
  bounds the close history to 512 rows, requires finite closes, and requires
  the final session to match the forecast origin
  (`backend/app/forecast/input.py:263-313`;
  `backend/app/forecast/service.py:206-218`).
- **WARNING — rendered confirmation remains.** Without screenshots, legend
  wrapping, series contrast at crossings, visual hierarchy, and dense-table
  scanability cannot be judged. This does not reopen UI-01 or UI-02.

### Pillar 3: Color (3/4)

- **Pass — UI-07 closed.** “可用” now uses neutral semantic tokens in all
  three Phase 05 surfaces (`ShadowAccount.tsx:407-413`;
  `ThesisPanel.tsx:664`; `ForecastPanel.tsx:601`).
- Forecast retains the contract-defined blue only for P50 and the uncertainty
  band (`ForecastPanel.tsx:755-756`); no new hard-coded application color was
  introduced by the closure patch.
- **WARNING — rendered confirmation remains.** Whole-page 60/30/10
  distribution and full light/dark contrast require screenshots.

### Pillar 4: Typography (4/4)

- **Pass — UI-08 closed.** Forecast `预测范围` and `批准检查点` use
  `font-normal` (`ForecastPanel.tsx:554-555`); Thesis ordinary fieldset legends
  also use `font-normal` (`ThesisPanel.tsx:781-782`).
- The remaining `font-semibold` occurrences in the three Phase 05 components
  represent titles, primary actions, key state labels, or table row identity,
  consistent with the approved role set.
- Phase surfaces continue to use the approved 12/14/16px component roles and
  400/600 weights.

### Pillar 5: Spacing (3/4)

- **Pass — UI-05/UI-09 closed.** The Shadow batch selector exposes a 44×44px
  hit area while retaining the 20px visual control and a visible focus ring
  (`ShadowAccount.tsx:524`).
- A focused source scan found no remaining `gap-3`, `mt-5`, or `p-5` in the
  three Phase 05 surfaces. The single remaining `p-3` is the empty cell of a
  dense evidence table (`ThesisPanel.tsx:728`), covered by the design
  contract's table-spacing exception.
- The merged 375px Playwright contract asserts the Shadow selector's accessible
  name, keyboard focus, and 44px target.
- **WARNING — rendered confirmation remains.** 200% zoom, adjacent-target
  separation, and actual horizontal-scroll affordances were not visually
  observed.

### Pillar 6: Experience Design (4/4)

- **Pass — UI-01/UI-03/UI-04/UI-05/UI-06/UI-10 closed.** Governed chart
  evidence, typed recovery controls, dependent-condition resets, overdue/latest
  check state, touch-target sizing, and accessible validation are all present.
- `failDraft` routes every validation branch to a concrete control ID and
  focuses it (`ThesisPanel.tsx:495-595`). `fieldProps` binds the alert to that
  control through `aria-describedby` and marks it invalid
  (`ThesisPanel.tsx:737-740`).
- Source changes reset field, unit, operator, and threshold to a compatible
  state, and a polite live region explains the reset
  (`ThesisPanel.tsx:742-779`).
- The added browser test changes source types, checks the constrained options
  and reset values, submits an invalid condition, and verifies focus,
  `aria-invalid`, and `aria-describedby`.

---

## Browser and Test Evidence

| Evidence | Result | Relevant closure |
|----------|--------|------------------|
| Backend Forecast tests | 39 passed | Governed price-context projection and rejection of forged descriptor identity |
| TypeScript verification | passed | Updated DTOs and component integrations compile |
| Phase 05 fixture Playwright | 33/33 passed | Direct UI-01–UI-06 and UI-10 assertions plus existing responsive/state contracts |
| Phase 05 real-host Playwright | 1/1 passed | Shadow production-host workflow remains intact after UI-05/UI-07/UI-09 changes |
| Dev server probe | no response on 3000/5173/8080 | Screenshot capture unavailable; three rendered checks remain |

### Items requiring rendered human review

- `needs_human_review: true` — Forecast populated chart composition and legend
  wrapping at 1440/1024/375px.
- `needs_human_review: true` — full-page light/dark 60/30/10 distribution after
  availability indicators became neutral.
- `needs_human_review: true` — 200% zoom, Shadow checkbox adjacent targets,
  and table scroll cues.

---

## Files Audited

### Design and prior audit

- `.planning/phases/05-optional-enhancements/05-UI-SPEC.md`
- `.planning/phases/05-optional-enhancements/05-UI-REVIEW.md` at baseline
  `bc00d16`

### Closure implementation

- `backend/app/forecast/api.py`
- `backend/app/forecast/input.py`
- `backend/app/forecast/service.py`
- `frontend/src/components/analysis/ForecastPanel.tsx`
- `frontend/src/components/analysis/ThesisPanel.tsx`
- `frontend/src/lib/phase5Api.ts`
- `frontend/src/pages/backtest/ShadowAccount.tsx`

### Closure tests

- `backend/tests/forecast/test_api.py`
- `backend/tests/forecast/test_input.py`
- `frontend/e2e/phase5-optional-enhancements.spec.ts`
