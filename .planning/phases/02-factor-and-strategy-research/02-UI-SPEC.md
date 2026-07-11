---
phase: 02
slug: factor-and-strategy-research
status: approved
shadcn_initialized: false
preset: none
created: 2026-07-11
reviewed_at: 2026-07-11
---

# Phase 02 — UI Design Contract

> Visual and interaction contract for the existing `/backtest` researcher workspace. This contract closes the remaining FACT-03 user-flow gap without introducing a new shell, route hierarchy, fetch client, or strategy-authoring surface.

---

## Scope and Source Decisions

| Source | Binding UI decision |
|---|---|
| `02-CONTEXT.md` D-01–D-08 | Show DSL validation before save/evaluation; distinguish non-persistent hypothesis drafts from immutable revisions; render parser diagnostics and model provenance; never make a model output executable or implicitly retained. |
| `02-CONTEXT.md` D-09–D-14 | Treat completed experiments as immutable evidence, require explicit retention before comparison, show all provenance dimensions and comparability warnings, and extend the existing Backtest workspace/API/query conventions. |
| `02-RESEARCH.md` | Preserve the existing React/Vite/Tailwind workspace, typed `api.ts`, TanStack Query, Lucide icons, ECharts charts, and strategy SSE lifecycle. |
| `02-05-PLAN.md` | Keep Pearson IC and Spearman RankIC separate; comparison is explicit, side-by-side, warning-led, and never declares a winner. |
| `02-VERIFICATION.md` | Close FACT-03 by preserving the server-issued strategy research execution handle from SSE, exposing an explicit strategy-retention action after successful completion, and invalidating experiment/candidate queries after retention. |

### Phase boundary

- **In scope:** factor DSL creation/validation, similarity review, hypothesis draft/review, factor evaluation evidence, registered-strategy experiment retention, experiment history, and transparent comparison.
- **Out of scope:** custom strategy authoring, arbitrary code execution, strategy promotion/evolution, broker execution, autonomous agents, a new route, a second API client, or a new design system.

---

## Design System

| Property | Value |
|---|---|
| Tool | Manual existing system: Tailwind CSS 3.4 tokens and local React components |
| Preset | Not applicable — `components.json` is absent as of 2026-07-11; do not initialize shadcn for this gap closure |
| Component library | Existing local components and native semantic controls; no new UI component registry |
| Icon library | `lucide-react`; use its existing 14–16px outline icons beside, never instead of, visible labels |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, system sans; `JetBrains Mono`/`IBM Plex Mono` only for identifiers, dates, expression code, and numeric evidence |
| Charts | Existing ECharts integration and existing Backtest chart components; do not add a charting dependency |
| Server state | Existing typed `api.ts` methods plus TanStack Query `QK` factories; no direct `fetch`, duplicate request helper, or client-side provenance synthesis |

### Existing visual tokens to preserve

Use the CSS variables in `frontend/src/index.css` and Tailwind semantic names (`base`, `surface`, `elevated`, `border`, `foreground`, `secondary`, `muted`, `accent`, `bull`, `bear`, `warning`, `danger`). Dark mode remains the default; light mode is the existing token inversion. Use 1px `border-border` separation and existing radii: `rounded-input` 4px, `rounded-btn` 6px, `rounded-card` 8px, `rounded-dialog` 12px. Do not introduce gradients, glass surfaces, oversized rounded cards, decorative shadows, or a Phase-02-specific palette.

---

## Information Hierarchy and Workflow

### Workspace hierarchy

1. **Page header — `回测工作台`:** retain the existing compact title, contextual mode hint, and factor/strategy/optimizer mode switch. The active mode is the only accent-filled tab; inactive modes use secondary text and elevated hover.
2. **Factor mode:** the visual focal point is the current factor lifecycle/evidence panel, which foregrounds the next gated action before stored history and comparison. Present the work in causal order: manual DSL definition and similarity review → natural-language draft and explicit review → governed evaluation and evidence/retention → stored factor/experiment history → explicit comparison. A draft, saved revision, completed-unretained run, and retained run must always have visually distinct status copy.
3. **Strategy mode:** retain the existing configuration panel and result workspace. The visual focal point is the completed-result header: after a successful registered-strategy result arrives, put provenance/retention directly beside the strategy identity and date range, before charts and trade details. A researcher must not have to navigate to a hidden history panel to retain their own completed run.
4. **History and comparison:** continue to use the existing research-library/history and comparison surfaces inside Backtest. The visual focal point of comparison is the compatibility warning followed by aligned selected immutable snapshot headers, before evidence columns and field deltas. History answers “what was retained?”; comparison answers “how do explicitly selected retained snapshots differ?” They must not be merged into a scorecard or ranking.

### Required status vocabulary

| State | Visible label and treatment | Allowed actions |
|---|---|---|
| Unvalidated DSL | `尚未验证` in muted text; parser errors appear inline beside the expression | Validate only; save/evaluate disabled |
| Validated DSL | `已验证：{normalized expression}` success treatment with text and check icon | Save immutable revision |
| Similar factor candidates | `相似因子候选` with deterministic reason and score components | Review only; never blocks save or auto-merges |
| Hypothesis draft | `草稿：不可比较` with violet-neutral provenance panel | Check explicit review acknowledgment, then save revision |
| Saved revision | `已保存修订版 #{n}` with immutable identity | Run governed evaluation |
| Running evaluation/backtest | `评估中…` or `回测中 · 第 {day}/{total} 天` with determinate progress when SSE provides it | Stop/cancel according to existing task control |
| Completed, not retained | `已完成，未保留` / `完成但未保留` in warning treatment | Explicitly retain; cannot be a comparison candidate |
| Retention pending | `正在保留完成实验…` beside a disabled retention action; retain result evidence in place | No duplicate submission |
| Retained | `已保留：此完成快照现在可在比较中选择。` success treatment | View history and select in comparison |
| Failed, cancelled, invalid, or draft | Exact status plus actionable diagnostic; `不可比较` is explicit | Retry only where the existing run contract permits; never retain/select |

### FACT-03 strategy-retention interaction contract

1. The SSE client must retain the **server-issued** `research` execution handle in the existing Backtest task state when received. The UI must never accept a handle from a form field, query string, local storage, or manually entered text.
2. The strategy result becomes retainable only when the same task reports a successful terminal `done` result and a non-empty server-issued handle. A result without a handle remains visible but shows `此运行没有可保留的研究句柄；请重新运行。`; it must not display a misleading retention CTA.
3. Render a secondary warning-outline action in the completed strategy-result header: **`保留此完成策略实验以供比较`**. It appears only for a completed, valid, not-yet-retained registered-strategy result with a trusted handle.
4. Activating the action calls only `api.retainStrategyResearchExecution(handle)`. Disable it while pending, replace its label with `正在保留完成策略实验…`, and prevent duplicate requests.
5. On success, replace the CTA with the retained status, expose the returned immutable experiment identifier in the research history, and invalidate **only** `QK.researchExperiments` and `QK.researchComparisonCandidates` (plus any existing selected-comparison key). Do not rerun the strategy, recreate its snapshot, or mutate the displayed strategy result.
6. On failure, retain the completed strategy result and handle in the workspace, restore the action, and show an inline `role="alert"`: `无法保留此完成策略实验：{server message}。请重试。` A stale, cancelled, failed, or already-retained handle must receive the server error verbatim enough to explain next action and must never be represented as retained.
7. Retention is deliberate but non-destructive: do **not** use a confirmation modal. The CTA itself must state the irreversible semantic effect—adding this immutable completed snapshot to comparison candidates. There is no Phase-02 delete or overwrite action.

---

## Interaction States and Feedback

| Control class | Default / hover / focus | Disabled / loading / error |
|---|---|---|
| Primary run action | Accent fill; hover retains solid accent contrast; keyboard focus is a 2px accent ring with 2px offset | Disabled until validation/required configuration passes; button label names active work; show inline error below the affected operation |
| Secondary retain action | Warning-outline treatment to distinguish retention from rerun; hover adds subtle warning background | Disabled during retain; completed state becomes success text, not another button |
| Mode and result tabs | Current tab uses accent text/border or fill; inactive tabs use secondary text and elevated hover | Implement `role="tablist"`, `role="tab"`, `aria-selected`, and `aria-controls`; Arrow Left/Right move focus and activate the adjacent tab |
| DSL editor and hypothesis form | Native label, visible field hint, monospaced expression only, local validation feedback below the input | Validation errors use `role="alert"`, source-location text if returned, and do not clear the user’s input |
| Checkboxes / candidate selection | Native checkbox plus visible factor/strategy identity, timestamp, and retention status | Candidate list is server-filtered to completed-and-retained only; disable comparison until at least two selections |
| Stop backtest | Existing `停止回测` control stays immediately available while work is running | After activation announce `已请求停止回测；取消的运行不会进入比较。`; no confirmation modal |
| Query-driven panels | Reserve panel height and render an in-place skeleton for library/history/candidates | Empty and error states replace only the affected panel; never blank the complete workspace |

Use 150–200ms `ease-smooth` opacity/color transitions only for state feedback. Do not animate initial page entry, chart data, layout height, or retention status in a way that hides content. Under `prefers-reduced-motion: reduce`, all state transitions are instant and loading remains text/progress based.

---

## Charts, Metrics, and Tables

### Metrics and chart rules

- **IC and RankIC are separate evidence:** label Pearson evidence exactly `Pearson IC` and rank evidence exactly `RankIC（Spearman）`. Never reuse a generic `IC`, merge series, or show one metric as a proxy for the other.
- Present each metric family with its own summary (mean, observations, and available dispersion/IR) and its own time-series chart or accessible time-series detail. Group and long-short outputs remain secondary supporting evidence after the two mandatory metric families.
- Every chart has a visible title, axis/series meaning, date/value tooltip, and a textual summary adjacent to it. Tooltips must identify the series and formatted value; do not rely on red/green or a tooltip alone to communicate direction.
- Preserve existing strategy equity and return-distribution charts. Their title must identify the strategy/result period; the distribution legend must state existing A-share convention in text: `红=正收益 · 绿=负收益`.
- Charts must render from the immutable returned result only. They must never recompute evidence, infer a winner, hide warning data, or make a retention mutation.
- If a chart has no valid points, show `此证据没有可绘制的数据。请检查运行配置和诊断信息。` in the chart region; do not render an empty axis as success.

### Provenance and comparison

- Use collapsed native `<details>` panels for dense JSON-like immutable evidence, with short labels: `已解析配置`, `受治理输入清单`, `预测 / 信号元数据`, `度量与补充证据`, `受管工件引用`, and `模型 / 提供商版本`.
- Preserve all six comparison dimensions side-by-side: configuration, governed input identity, predictions/signals, metrics, artifacts, and model/provider/version. Values and deltas are evidence, not implementation noise.
- Place `兼容性警告` **above** selected experiment columns and field deltas. It must remain visible whenever universe, date window, horizon, revision, or fingerprint differs; it must never be collapsed behind a disclosure by default.
- Do not compute, label, sort, badge, or imply a “winner,” best result, aggregate score, or recommendation. A compatibility warning is a caution, not a block on viewing differences.

### Table behavior

- Retain semantic `<table>`, `<thead>`, scoped `<th>`, and `<tbody>` for strategy daily trades, trade details, and picks. Caption each table with its active data view (visually hidden if the surrounding heading already supplies it).
- Keep numeric columns right-aligned with `.num`/tabular numerals; keep dates, factor/strategy IDs, DSL expressions, and checksums monospaced. Do not truncate an identifier without a title/expand affordance.
- Retain the existing minimum 960px width for complex result tables. On narrow layouts, preserve columns within an `overflow-x-auto` wrapper instead of converting rows to cards or dropping provenance columns; show a short `左右滚动查看全部列` hint before the first table.
- Pagination must announce the current range and total, keep previous/next disabled at boundaries, retain focus after page changes, and reset to page 1 when page size or source result changes. Do not use infinite scroll for immutable experiment evidence.
- Clicking a trade opens the existing detail modal; keyboard users can activate the same control and return focus to the originating trade row/chip on close.

---

## Spacing Scale

Declared values (all multiples of 4):

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | Icon-label gap, compact badge padding |
| sm | 8px | Form-label to control gap, compact control group gap |
| md | 16px | Default component gap, panel inner padding on narrow screens |
| lg | 24px | Related-panel separation and desktop panel padding |
| xl | 32px | Workspace section separation |
| 2xl | 48px | Major workflow boundary only |
| 3xl | 64px | Page-level separation only; do not add empty decorative space inside data tools |

**Exceptions:** Existing dense desktop tables use 8px cell padding for scanability. At viewport widths below 768px, all primary buttons, checkboxes, tab triggers, pagination controls, and icon-only actions must have a 44×44px hit area even when the visible glyph/control remains compact. Keep at least 8px between adjacent touch targets.

---

## Typography

Use one existing sans family for all UI labels, headings, buttons, and body copy. The Phase-02 additions use exactly these four sizes and two weights; code/data may use the existing mono family at the same declared size.

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Metadata / labels | 12px | 400 | 1.5 |
| Body / table content | 14px | 400 | 1.5 |
| Section heading | 16px | 600 | 1.2 |
| Page heading | 20px | 600 | 1.2 |

- Use `font-weight: 600` only for page headings, section headings, selected labels, status names, and primary actions. All other content uses 400.
- Keep prose explanations at a maximum of 65ch. Dense table/evidence values may use their available width but must wrap safely (`overflow-wrap:anywhere`) instead of overflowing.
- Status is communicated by the literal state words above, not by a weight, color, or icon alone.

---

## Color

The established restrained dark-first system is binding. The 60/30/10 split describes surface allocation, not a reason to tint all controls.

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `base`: dark `#0A0A0B`; light `#FAFAFA` | Application and Backtest workspace background |
| Secondary (30%) | `surface`: dark `#18181B`; light `#FFFFFF`; `elevated`: dark `#212126`; light `#F4F4F5` | Workspace panels, cards, toolbar/tab backgrounds, table headers |
| Accent (10%) | `accent` `#3B82F6` | Primary run/save actions, selected mode/result tabs, keyboard focus rings, active links, and neutral information identity only |
| Success | `#12B76A` | Validated DSL and retained-completed status only; accompany with check/status text and keep it distinct from market direction semantics |
| Warning | `warning` `#F79009` | Completed-but-unretained state, retention CTA, and comparability warnings; accompany with icon/text |
| Destructive | `danger` `#F04438` | Run failure/cancellation diagnostic and truly destructive controls only |
| Market direction | `bull` `#F04438` for A-share positive/red; `bear` `#12B76A` for A-share negative/green | Price, P&L, and chart direction only; never generic success/error state |

Accent is reserved for: primary run/save controls, active Backtest mode/result tabs, focus rings, visible selected comparison candidates, and neutral research identity links. It is **not** a decoration color, a generic card border, or the visual status of every clickable element.

All normal text and interaction labels must meet 4.5:1 contrast against their occupied surface; large/bold text and focus indicators must meet at least 3:1. Provide text/icon redundancy for validation, retention, warning, positive/negative market movement, and errors.

---

## Responsive Behavior

| Viewport | Required layout behavior |
|---|---|
| `≥1280px` | Retain the existing StrategyBacktest two-pane grid: approximately 18rem configuration column and flexible result column. Factor evidence/history/comparison may use two columns only when each remains at least 320px wide. |
| `768–1279px` | Stack configuration before results; use two-column evidence summaries only when both remain readable. Keep comparison experiment columns at two columns only when they are at least 320px each. |
| `<768px` | One-column flow: header wraps title/subtitle before controls; mode tabs remain horizontally reachable without clipped labels; form actions wrap; all phase controls meet 44px targets; dense provenance remains collapsed in `<details>`. |
| Any narrow table | Preserve semantic table and horizontal scroll as specified above; do not hide metric, artifact, manifest, or registered strategy identity columns. |

Do not use fluid heading sizes. Preserve the existing `xl` split as the desktop layout, the current `lg`/`md` evidence grid conventions, and the existing `overflow-x-auto` table pattern. Tooltips/popovers must use fixed/portal-like placement where necessary so an overflow-scrolling configuration pane cannot clip them.

---

## Accessibility Contract

- Use semantic `main`, `section`, `aside`, headings in order, native `button`, native `input`, `textarea`, `select`, `checkbox`, `table`, and `details` before custom equivalents. Every form field has a visible programmatic `<label>`.
- Associate validation/help/error text with controls through `aria-describedby`; errors use `role="alert"`, successful mutation feedback uses `role="status"` or a polite live region, and SSE progress uses a polite live region without announcing every render.
- Use a visible 2px accent focus ring with 2px offset on every keyboard-reachable control. Never remove focus outlines without providing that replacement. Keyboard order follows visual order.
- Treat the mode switch and result tabs as real tabs, including role, selected state, linked panel ID, and arrow-key navigation. Checkboxes retain native semantics and labels with full experiment identity.
- Provide non-color labels for all status and market-direction states. All Lucide icons that duplicate label text are `aria-hidden`; an icon-only action has an explicit `aria-label` and tooltip.
- Charts expose title/description and adjacent textual metric values; users can reach the same decision-relevant evidence in the summary/detail panels without pointer-only hovering.
- Respect `prefers-reduced-motion`; do not make state updates dependent on animation. Maintain readable contrast in both current light and dark themes.

---

## Copywriting Contract

| Element | Copy |
|---|---|
| Factor primary CTA | `运行受治理因子评估` |
| Strategy primary CTA | `运行回测` |
| Strategy retention CTA | `保留此完成策略实验以供比较` |
| Retention pending | `正在保留完成策略实验…` |
| Factor retention CTA | `显式保留此完成证据以供比较` |
| Draft state | `草稿：不可比较` |
| Unretained result | `已完成，未保留` / `完成但未保留` |
| Retained result | `已保留：此完成快照现在可在比较中选择。` |
| Factor library empty heading | `尚无保存的因子修订版。` |
| Factor library empty body | `先验证受限 DSL，再保存不可变修订版；相似候选只供审阅，不会阻止保存。` |
| Experiment history empty heading | `尚无实验快照。` |
| Experiment history empty body | `完成评估或注册策略回测后，在结果中显式保留完成快照以供比较。` |
| Comparison empty state | `尚无可比较的已保留实验。` |
| Comparison prerequisite | `至少选择两个已保留实验后才能比较。` |
| Retention error | `无法保留此完成策略实验：{server message}。请重试。` |
| Missing strategy handle | `此运行没有可保留的研究句柄；请重新运行。` |
| Chart no-data state | `此证据没有可绘制的数据。请检查运行配置和诊断信息。` |
| Stop feedback | `已请求停止回测；取消的运行不会进入比较。` |
| Destructive confirmation | None in Phase 02. Revisions and completed snapshots are immutable; stopping a run is non-destructive and needs no modal. |

Use clear Chinese task language, not unexplained internal implementation names. `run_id`, revision ID, execution handle, and checksum may appear as inspectable metadata but must be accompanied by a human label.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|---|---|---|
| shadcn official | None | Not applicable — `components.json` was absent when scanned on 2026-07-11; shadcn initialization is explicitly excluded for this gap closure. |
| Third-party registry | None | No third-party blocks declared or permitted; no registry vetting needed. |

---

## Verification Scenarios

1. **Manual factor flow:** validate a permitted DSL expression, inspect deterministic similarity reason, save an immutable revision, run a governed evaluation, visibly inspect separate Pearson IC and RankIC evidence, explicitly retain it, then select it with another retained experiment and see a compatibility warning with no winner.
2. **Hypothesis gate:** create a natural-language draft; confirm it is labeled non-persistent/non-comparable, review it explicitly, save the revision, complete evaluation, and retain only after completion. An invalid draft/error must remain actionable and must not become a revision.
3. **Strategy retention gap closure:** run a registered strategy through SSE; receive progress and a successful result; retain using the trusted server-issued execution handle; observe pending then retained state; see the returned snapshot in history and as a comparison candidate. Repeat with a failed/cancelled/missing-handle result and prove no retention CTA/candidate appears.
4. **Comparison honesty:** compare snapshots whose universe, time window, horizon, revision, or fingerprint differ; warnings appear before evidence, all dimensions remain visible, and no winner/ranking text exists.
5. **Responsive and keyboard:** exercise factor, strategy, retention, tabs, comparison candidates, table pagination, and evidence disclosures at 1440px, 1024px, and 375px using keyboard-only navigation. Confirm 44px narrow-screen targets and horizontal table access.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: clear state labels, CTA copy, empty/error/retention language, and no opaque internal-only wording
- [ ] Dimension 2 Visuals: existing dark-first restrained workspace, workflow hierarchy, chart/table readability, and no duplicate shell
- [ ] Dimension 3 Color: established 60/30/10 tokens, reserved accent, semantic status usage, and contrast/redundancy
- [ ] Dimension 4 Typography: four-size/two-weight scale, monospaced data rules, and readable dense evidence
- [ ] Dimension 5 Spacing: 4px-based scale, responsive touch exceptions, and table/panel rhythm
- [ ] Dimension 6 Registry Safety: no shadcn initialization or third-party registry; timestamped absence evidence recorded

**Approval:** pending
