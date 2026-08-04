---
phase: 18
slug: pool-hub
status: approved
shadcn_initialized: false
preset: none
created: 2026-08-04
---

# Phase 18 — UI Design Contract

> Visual and interaction contract for the new 股池 (Pool Hub) page. This contract covers only the Phase-18 pool surface: strategy cards with 当日池数, a per-strategy drill-down stock list, a 概念 filter, and 交叉共振 highlight — a research-only projection with zero execution authority. It does not introduce guest/VIP masking (Phase 19), date navigation (v2), or strategy authoring (Phase 17, done).

---

## Scope and Source Decisions

| Source | Binding UI decision |
|---|---|
| `ROADMAP.md` Phase 18 成功标准 | User can open the pool hub, see strategy cards with 当日 pool counts, drill into a per-strategy stock list (代码/开盘涨幅/涨跌幅/概念板块/关联因子) backed by `screener_results/` persistence with a single `as_of` source of truth; filter by 概念; see 交叉共振 (stocks hit by ≥2 auction strategies) highlighted; zero execution authority anywhere in the feature. |
| `REQUIREMENTS.md` POOL-01 | A pool hub page shows per-strategy 当日 counts and a drill-down stock list with the exact columns 代码, 开盘涨幅, 涨跌幅, 概念板块, 关联因子 — derived from one `as_of` date's persisted results. Card count and drill-down list must never drift apart (PITFALL #10). |
| `REQUIREMENTS.md` POOL-02 | The page filters the pool by 概念 and highlights 交叉共振 — stocks hit by ≥2 auction strategies (computed from Phase 17 `hit_factors`). |
| `REQUIREMENTS.md` POOL-03 | Pool data is a research-only projection: no API endpoint, UI affordance, or service path can push a pool to a live broker. The page renders no trade/order/execution control of any kind. |
| `18-CONTEXT.md` Decisions #1–#7 | Backend projection over `screener_results/` (no new datastore); single `as_of`; 交叉共振 = ≥2 strategy hits from `hit_factors`; 概念板块 from enriched columns with filtering as a projection over the current `as_of` pool; zero execution authority enforced at the API boundary; the frontend pool hub composes cards → drill-down list → concept filter → 交叉共振 highlight consistent with `Screener.tsx`/`ConceptAnalysis.tsx` and design tokens; 日期导航 deferred to v2. |
| `.planning/research/v1.3-auction/SUMMARY.md` | Reference UI table stakes: strategy cards = 策略名 + 当日股池数; per-stock rows = 开盘涨幅, 涨跌幅, 关联因子 (hit strategies), 概念板块; 交叉共振 = multi-strategy hits; guest-mode masking is Phase 19 and server-authoritative (never client-side). |
| `frontend/src/pages/Screener.tsx` | Card-grid + results-table workspace pattern; client-side filter projection over the loaded payload; filtered-count convention `命中 N 只 / 共 M 只`; PageHeader + EmptyState + motion reveal idioms. |
| `frontend/src/components/screener/ScreenerTable.tsx` | 关联因子/strategy tags reuse the existing amber tag treatment (`STRATEGY_TAG_CLS`); board 创/科/北 tag from `stock-table/primitives.tsx`; numeric cells via `fmtPct` + `priceColorClass`. |
| `frontend/src/components/stock-table/StockDataTable.tsx` | Shared table skeleton: sticky/scrollable container `rounded-card border border-border overflow-x-auto`, `border-t border-border hover:bg-elevated/50` row base. |
| `frontend/src/components/ConceptAnalysis.tsx` / `analysis-shared.tsx` | 概念 display idioms: concept chips, `无符合…` empty copy, `正在计算…` loading copy. |
| `.impeccable/design.json` + `frontend/src/index.css` + `tailwind.config.ts` | Binding dark-first tokens (`base`/`surface`/`elevated`/`border`/`foreground`/`secondary`/`muted`/`accent`/`bull`/`bear`/`warning`/`danger`), 4px spacing scale, four-size/two-weight type scale, mono for data/identifiers, radii `rounded-input` 4 / `rounded-btn` 6 / `rounded-card` 8 / `rounded-dialog` 12, `ease-smooth` timing. |
| `16-UI-SPEC.md` (approved v1.3 convention) | Same UI-SPEC structure, required-status-vocabulary style, Simplified Chinese copy voice, and 6-dimension self-check discipline. |

### Phase boundary

- **In scope:** the pool hub page (route `/pool-hub`, nav entry `股池`), strategy card grid with 当日池数, drill-down stock list (代码/开盘涨幅/涨跌幅/概念板块/关联因子), 概念 filter, 交叉共振 highlight, `刷新股池` refresh action, single-`as_of` header display, research-only disclaimer. All interactions are read-only (drill-down, filter, refresh).
- **Out of scope:** guest/VIP 脱敏 and the masked pool-page composition (Phase 19, GUEST-01..02 — masking is server-authoritative at the DTO boundary, never client-side); 日期导航 per-trading-day browsing (POOL-04, v2); strategy authoring/settings UI (Phase 17, done); true 集合竞价 match-data columns (DATA-04, v2); any execution/trade/order affordance, and any watchlist or portfolio mutation on this page (POOL-03).

---

## Design System

| Property | Value |
|---|---|
| Tool | Manual existing system: Tailwind CSS 3.4 tokens and local React components |
| Preset | Not applicable — `components.json` is absent as of 2026-08-04; do not initialize shadcn for this phase |
| Component library | Existing local components only (`PageHeader`, `EmptyState`, `StatCard`, `SectionTitle`, `StockDataTable`/`primitives.tsx`, `ScreenerTable` tag patterns); no new UI component registry |
| Icon library | `lucide-react`; 14–16px outline icons beside, never instead of, visible labels |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, system sans; `JetBrains Mono`/`IBM Plex Mono` only for data, identifiers, codes, and counts |
| Server state | Existing typed `api.ts` methods plus TanStack Query `QK` factories (`QK.poolHub(...)` new keys); no direct `fetch`, duplicate request helper, or client-side synthesis of strategy counts or the 交叉共振 flag |

### Existing visual tokens to preserve

Use the CSS variables in `frontend/src/index.css` and Tailwind semantic names (`base`, `surface`, `elevated`, `border`, `foreground`, `secondary`, `muted`, `accent`, `bull`, `bear`, `warning`, `danger`). Dark mode remains the default; light mode is the existing token inversion. Use 1px `border-border` separation and existing radii: `rounded-input` 4px, `rounded-btn` 6px, `rounded-card` 8px, `rounded-dialog` 12px. Do not introduce gradients, glass surfaces, oversized rounded cards, decorative shadows, or a Phase-18-specific palette.

---

## Information Hierarchy and Workflow

### Page hierarchy

The pool hub is a single read-only workspace. The `as_of` date is server-authoritative (from the hub response) and displayed once in the header; there is no date picker and no per-day navigation.

```
PoolHubPage  (route /pool-hub · nav 「股池」)
├── PageHeader
│   ├── title 「股池」
│   ├── subtitle 「竞价策略 · 数据日期 {as_of} · 仅研究参考」
│   └── actions: 刷新股池 (RefreshCw, secondary)
├── ConceptFilter  (概念筛选 input + 清除筛选)
├── StrategyCardGrid  (flex-wrap, gap per existing cardWrapCls)
│   └── StrategyCard × N
│       ├── strategy name (600 weight, truncates)
│       ├── 当日池数 「当日池 {N} 只」 (N mono)
│       ├── active/selected state (accent border + tint)
│       └── on-click → drills into that strategy (read-only)
└── StockListTable  (drill-down of the active strategy)
    ├── thead: 代码 | 开盘涨幅 | 涨跌幅 | 概念板块 | 关联因子
    ├── tbody rows (交叉共振 rows get accent highlight + badge)
    │   └── 关联因子 cell: strategy-name tags + 「交叉共振 · {N} 策略」 badge
    └── footer meta: 「筛选后 {N} 只 / 共 {M} 只」 · 交叉共振 legend
```

Workflow: open the page → hub loads the single-`as_of` pool → the card grid shows each auction strategy with its 当日池数 → clicking a card drills into that strategy's stock list below → typing in 概念筛选 projects the filter over the loaded pool → rows hit by ≥2 strategies are accent-highlighted as 交叉共振. Nothing on the page writes to a portfolio, places an order, or routes to a broker.

### Required status vocabulary

| State | Visible label and treatment | Allowed actions |
|---|---|---|
| Hub loading | `股池加载中…` in secondary text with `Loader2` spinner and `role="status"`; card grid renders skeleton count placeholders | None while pending; `刷新股池` disabled |
| Hub error | `股池加载失败：{message}。请检查数据源后重试。` in `role="alert"` (danger text on `bg-danger/10` bordered container) | `重试` re-runs the same hub query |
| Empty — no results for as_of | `EmptyState` with icon: heading `当日无股池结果`; body `截至 {as_of}，竞价策略均无命中个股。请先在策略页运行竞价策略，或确认数据日期。` | `刷新股池`; hint points to the 策略 page |
| Pool-with-results | Card grid populated with `当日池 {N} 只` counts; drill-down table renders; footer meta `共 {M} 只` | Drill into a card; filter by 概念; `刷新股池` |
| Strategy card — count loading | `股池统计中…` in muted mono placeholder where the count will render | Card click disabled |
| Strategy card — zero hits | `当日无命中` in muted text | Card click still drills to an empty table |
| Strategy card — data unavailable | `数据不可用` in muted/warning text (strategy has no persisted result for as_of) | Card click disabled; tooltip `该策略无 {as_of} 的持久化结果` |
| Drill-down loading | `股池明细加载中…` with spinner; table header height reserved | No concurrent drill |
| Drill-down error | `股池明细加载失败：{message}。请重试。` in `role="alert"` inside the table area | `重试` re-runs the drill query |
| Concept filter — no match | Table area `EmptyState`-lite: heading `无符合「{概念}」的个股`; body `试试切换其他概念或清除筛选。` | `清除筛选` restores the full pool |
| 交叉共振 — none | Muted footnote `今日无交叉共振` with hint `暂无个股被 ≥2 个竞价策略同时命中。` | None (informational) |
| 交叉共振 — present | Rows accent-highlighted; `交叉共振 · {N} 策略` badge in the 关联因子 cell; legend `交叉共振：被 ≥2 个竞价策略同时命中的个股` | Drill remains read-only |

Every state above is communicated by its literal words plus an icon or treatment, never by color alone.

---

## Interaction States and Feedback

| Control class | Default / hover / focus | Disabled / loading / error |
|---|---|---|
| Strategy card | Surface card, 1px `border-border`, `rounded-card`; hover `border-accent/40`; keyboard focus 2px accent ring + 2px offset; selected/active = `border-accent bg-accent/5` with accent count | `数据不可用` cards render at 40% opacity with no click; count loading shows `股池统计中…`; no card ever exposes a run/settings/execute action |
| 概念筛选 input | Native text input, `h-9 rounded-input bg-base border border-border`, placeholder `输入概念名筛选…`; focus 2px accent ring; clear (`X`) button appears when non-empty | Empty value = full pool (no-op); projection is client-side over the loaded single-`as_of` payload, so it never triggers a second fetch |
| `清除筛选` | Secondary text action with `RotateCcw` icon; hover `bg-danger/10 text-danger` | Hidden when no filter is active |
| `刷新股池` | Secondary elevated (`bg-surface border-border`) with `RefreshCw`; hover `border-accent/50 text-accent`; focus ring | Disabled while pending (spinner replaces icon); never shows stale counts as fresh |
| Table row | `border-t border-border hover:bg-elevated/50` (existing `StockDataTable` base) | 交叉共振 rows keep `bg-accent/[0.06]` + left accent border on hover too; no inline editing anywhere |
| 开盘涨幅/涨跌幅 cells | Sortable header with the existing three-state sort indicator; numeric cells mono + `tabular-nums`, `priceColorClass` | Missing value renders `—` in muted text; never a blank cell |

Use 150–200ms `ease-smooth` opacity/color transitions for card hover, active-card state, and filter-count updates only. Do not animate initial page entry or layout height beyond the existing Screener-style 250ms reveal of the results block. Under `prefers-reduced-motion: reduce`, all transitions are instant and loading remains text/spinner based.

---

## Data Display

- **代码:** mono family, `tabular-nums`, prefixed by the existing board tag (`创`/`科`/`北`, `stock-table/primitives.tsx`) when applicable. No name column in Phase 18 — the contract column set is exactly 代码, 开盘涨幅, 涨跌幅, 概念板块, 关联因子 (a 名称 column, with its masked/unmasked variants, lands with the Phase 19 guest composition).
- **开盘涨幅 / 涨跌幅:** `fmtPct` (signed percentage, `+N.NN%`), mono, `priceColorClass` (A-share red-up `bull`, green-down `bear`); missing → `—`.
- **概念板块:** comma-separated concept chips (existing tag pattern), wrapping; when a cell holds many concepts, render the first few and `+{N}` expand/collapse per the existing `renderTagList` idiom — never clip mid-label.
- **关联因子:** strategy-name tags (existing amber `STRATEGY_TAG_CLS` from `ScreenerTable`). When the row is 交叉共振 (≥2 hits from `hit_factors`), the cell additionally renders the accent `交叉共振 · {N} 策略` badge.
- **当日池数:** `当日池 {N} 只`, `{N}` always mono/`tabular-nums`.
- **Counts / meta:** drill footer `筛选后 {N} 只 / 共 {M} 只` when a concept filter is active (the `共 {M}` is the authoritative per-strategy total, so the card count and drill list never drift); otherwise `共 {M} 只`.
- No charts, no sparklines, no heat maps on the pool hub — the reference surface is a card grid + a table.

---

## Spacing Scale

Declared values (all multiples of 4):

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | Icon-label gap, badge inner padding, board-tag gap |
| sm | 8px | Card inner padding gap, tag row gap, table cell horizontal padding on compact rows |
| md | 16px | Default component gap, card grid gap on narrow screens, table cell padding |
| lg | 24px | Section separation (card grid → drill table), page inner padding on desktop |
| xl | 32px | Between major blocks (header → filter, filter → grid) |
| 2xl | 48px | Page-level separation only |
| 3xl | 64px | Page-level separation only; no decorative empty space inside the data tool |

**Exceptions:** At viewport widths below 768px, the 概念筛选 input, its clear button, `清除筛选`, and `刷新股池` must keep a 44×44px hit area even when the visible control stays compact. Keep at least 8px between adjacent touch targets. Table cells may compress below 16px only inside the horizontal-scroll container, never by truncating the 代码 column.

---

## Typography

Use one existing sans family for all UI labels, headings, buttons, and body copy. Phase-18 additions use exactly these four sizes and two weights; code/data may use the existing mono family at the same declared size.

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Metadata / labels | 12px | 400 | 1.5 |
| Body / table content | 14px | 400 | 1.5 |
| Section heading | 16px | 600 | 1.2 |
| Page heading | 20px | 600 | 1.2 |

- Use `font-weight: 600` only for page/section headings, strategy card names, status names, and the 交叉共振 badge. All other content uses 400. The existing `PageHeader` component (22–24px) is an existing component and is retained as shipped — it is not a Phase-18 addition.
- Keep prose explanations at a maximum of 65ch. Status copy may use available panel width but must wrap safely (`overflow-wrap:anywhere`) instead of overflowing.

---

## Color

The established restrained dark-first system is binding. The 60/30/10 split describes surface allocation, not a reason to tint all controls.

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `base`: dark `#0A0A0B`; light `#FAFAFA` | Page background |
| Secondary (30%) | `surface`: dark `#18181B`; light `#FFFFFF`; `elevated`: dark `#212126`; light `#F4F4F5` | Strategy cards, table container, control backgrounds |
| Accent (10%) | `accent` `#3B82F6` | 交叉共振 highlight only (row tint `bg-accent/[0.06]` + left border + `交叉共振 · {N} 策略` badge), active/selected strategy card, focus rings, 当日池数 numerals, and the single-as_of identity in the header |
| Warning | `warning` `#F79009` | Degraded-state labels: `数据不可用` strategy card |
| Destructive | `danger` `#F04438` | Error diagnostics (`role="alert"`) only — there are no destructive controls in Phase 18 |
| Market direction | `bull` `#F04438` for A-share positive/red; `bear` `#12B76A` for A-share negative/green | 开盘涨幅 / 涨跌幅 direction only; never generic success/error state |

Accent is reserved for: 交叉共振 highlight, the active strategy card, focus rings, and the primary numeric identity (当日池数 / as_of). It is **not** a decoration color, a generic card border, or the visual status of every clickable element.

`bear` green `#12B76A` is market-direction-only — do **not** reuse it as a generic "available" success color. The 交叉共振 highlight uses accent (not bull/bear) because it is a research-identity state, not a market-direction state.

All normal text and interaction labels must meet 4.5:1 contrast against their occupied surface; large/bold text and focus indicators must meet at least 3:1. Provide text/icon redundancy for every status and market-direction state.

---

## Responsive Behavior

| Viewport | Required layout behavior |
|---|---|
| `≥1280px` | Card grid uses the existing multi-column `flex-wrap`; drill table uses full available width; filter and cards on one row where space allows |
| `768–1279px` | Cards wrap to two columns; the drill table stays full width with horizontal scroll (`overflow-x-auto`) when columns exceed the container |
| `<768px` | One-column card grid; table inside a horizontal-scroll container with a sticky first column (代码) if implemented per the shared table conventions; 概念筛选 input, clear, `清除筛选`, and `刷新股池` meet 44px touch targets; status copy wraps safely (`overflow-wrap:anywhere`) |

Do not use fluid heading sizes. The pool hub keeps the existing page layout conventions (PageHeader + `px-4 py-4 space-y-3 sm:px-6 lg:px-8` shell); no new shell is introduced at any viewport.

---

## Accessibility Contract

- Use semantic `main`, `section`, native `button`, native `input`, and a native `<table>` with `<th scope="col">` headers before custom equivalents. Every form control has a visible programmatic `<label>`.
- The 概念筛选 input is a real `<input>` with `<label>`; help/empty text associates via `aria-describedby`.
- Hub loading uses `role="status"` (or a polite live region); hub/drill errors use `role="alert"`.
- 交叉共振 is never communicated by color alone: the row always pairs the accent tint with the literal `交叉共振 · {N} 策略` badge and the legend line. Market-direction colors are always paired with a `+`/`−` sign.
- Use a visible 2px accent focus ring with 2px offset on every keyboard-reachable control. Never remove focus outlines without providing that replacement. Keyboard order follows visual order.
- All Lucide icons that duplicate label text are `aria-hidden`; an icon-only action has an explicit `aria-label` and tooltip.
- Respect `prefers-reduced-motion`; do not make state updates depend on animation. Maintain readable contrast in both current light and dark themes.
- The drill-down table exposes its row count to assistive tech (`共 {M} 只` in the footer meta), so screen-reader users know how many rows the table holds without tabbing through all of them.

---

## Copywriting Contract

| Element | Copy |
|---|---|
| Page title | `股池` |
| Page subtitle | `竞价策略 · 数据日期 {as_of} · 仅研究参考` |
| Primary action | None — research-only. The only primary interaction is drilling into a strategy card (read-only). No verb+noun CTA implying an action on stocks. |
| Refresh action | `刷新股池` |
| Strategy card count | `当日池 {N} 只` (`{N}` mono) |
| Strategy card — count loading | `股池统计中…` |
| Strategy card — zero hits | `当日无命中` |
| Strategy card — data unavailable | `数据不可用` (tooltip `该策略无 {as_of} 的持久化结果`) |
| Drill-down heading | `{策略名} · 股池明细` |
| Drill-down footer (no filter) | `共 {M} 只` |
| Drill-down footer (filter active) | `筛选后 {N} 只 / 共 {M} 只` |
| Column headers | `代码` · `开盘涨幅` · `涨跌幅` · `概念板块` · `关联因子` |
| 概念筛选 label | `概念筛选` |
| 概念筛选 placeholder | `输入概念名筛选…` |
| Clear filter | `清除筛选` |
| Concept filter — no match | heading `无符合「{概念}」的个股`; body `试试切换其他概念或清除筛选。` |
| 交叉共振 badge | `交叉共振 · {N} 策略` |
| 交叉共振 legend | `交叉共振：被 ≥2 个竞价策略同时命中的个股` |
| 交叉共振 — none | `今日无交叉共振` · `暂无个股被 ≥2 个竞价策略同时命中。` |
| Hub loading | `股池加载中…` |
| Hub error | `股池加载失败：{message}。请检查数据源后重试。` |
| Hub empty (no results for as_of) | heading `当日无股池结果`; body `截至 {as_of}，竞价策略均无命中个股。请先在策略页运行竞价策略，或确认数据日期。` |
| Drill-down loading | `股池明细加载中…` |
| Drill-down error | `股池明细加载失败：{message}。请重试。` |
| Research-only disclaimer | `本页面仅用于研究参考，不提供任何交易执行功能。` (footer, muted) |
| Destructive confirmation | None. Phase 18 has no destructive or irreversible actions — no execution, no deletion, no write of any kind. |

Use clear Chinese task language, not unexplained internal implementation names. `screener_results`, `as_of`, and `hit_factors` may appear as inspectable metadata but must be accompanied by a human label (`数据日期`, `关联因子`).

---

## UI Considerations

> Populated by the ui-phase UI-consideration probe (Step 9.5) and lifted by plan-phase's
> `## UI Considerations` lift rule. Shape-rooted UI *state* coverage (empty / loading / error /
> populated / partial / overflow / zero-one-many / long-text). Empty-state and error-state COPY
> live in `## Copywriting Contract` above — this section covers state coverage and references
> those rows rather than restating the copy (de-dup).

Applicable state considerations resolved: 9 covered, 5 backstop, 0 unresolved — pool hub research surface with a single `as_of` view.

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| loading | PoolHubPage | ✅ covered | `股池加载中…` + `Loader2` + `role="status"`; card grid renders skeleton count placeholders so layout height is reserved; `刷新股池` disabled |
| error | PoolHubPage | ✅ covered | `股池加载失败：{message}。请检查数据源后重试。` `role="alert"` (danger on `bg-danger/10` bordered container) + `重试` re-runs the hub query |
| empty | PoolHubPage | ✅ covered | no results for as_of renders `EmptyState` `当日无股池结果` + body pointing to 策略页; grid area never blanks |
| populated | PoolHubPage | ✅ covered | pool-with-results: cards with `当日池 {N} 只` and drill-down table render from the single as_of payload; footer `共 {M} 只` |
| zero-one-many | StrategyCardGrid | ✅ covered | 0 strategies → `当日无股池结果`; 1 strategy → single card + drill table; ≥2 → grid and 交叉共振 become possible |
| partial | StrategyCardGrid | 🧪 backstop | strategy without a persisted result for as_of renders `数据不可用` (40% opacity, no click); the rest of the grid stays usable — no silent card disappearance |
| long-text | StrategyCard | 🧪 backstop | long strategy names truncate with ellipsis (`truncate`); the card name line never wraps the card or pushes the count off-layout |
| loading | StockListTable | ✅ covered | `股池明细加载中…` with spinner; table header height reserved so the block does not jump |
| error | StockListTable | ✅ covered | `股池明细加载失败：{message}。请重试。` inline `role="alert"` inside the table area with `重试` |
| empty | StockListTable (drill-down / concept-filtered) | ✅ covered | active strategy with no pool → `当日无命中`; concept filter with no match → `无符合「{概念}」的个股` + `清除筛选` — both `EmptyState`-lite, never a blank table |
| partial | StockListTable | 🧪 backstop | missing 概念板块/关联因子 cells render `—` (muted) and omit the 交叉共振 badge when the row has <2 hits; row integrity is preserved |
| overflow | StockListTable | 🧪 backstop | many rows → `共 {M} 只` footer count + `overflow-x-auto` scroll container; no page reflow and the 代码 column is not truncated |
| zero-one-many | 交叉共振 | ✅ covered | none → `今日无交叉共振` footnote; ≥1 → accent-highlighted rows + `交叉共振 · {N} 策略` badge; the N count is mono and derived from `hit_factors` |
| long-text | ConceptFilter | 🧪 backstop | long concept names in the input value and in 概念板块 chips truncate/wrap safely (`truncate` per chip, `overflow-wrap:anywhere` for the input) — never break the filter row layout |

**Covered truths vs backstop scalars.** Every `✅ covered` row is a plain truth string (e.g. "Hub error renders `股池加载失败：{message}。请检查数据源后重试。` with `role=\"alert\"` and a `重试` action") that lifts into `must_haves.truths` and is verification-derivable from a wired UI test or code inspection. Every `🧪 backstop` row is a flat scalar `{ statement, verification: backstop }` — a human-judgment item confirmed at verify time only by explicit evidence (held-out/visual UI-state test); without evidence it routes to `insufficient_spec → human_needed`, never a silent pass (#1154). No row is left `⚠ unresolved`; the planner is not required to carry a Phase-18 UI assumption forward.

<!-- Status vocabulary (locked by probe-core projectTruths):
     ✅ covered   → a plain truth string lifted into must_haves.truths
     🧪 backstop  → a flat scalar { statement, verification: backstop }; at verify time, no explicit
                    evidence → insufficient_spec → human_needed (never a silent pass, #1154)
     ⚠ unresolved → an explicit planner assumption (surfaced, never silently dropped)
     Rows are REPLACED (not appended) on a probe re-run — idempotent. -->

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|---|---|---|
| shadcn official | None | Not applicable — `components.json` absent when scanned on 2026-08-04; shadcn initialization is explicitly excluded for this phase. |
| Third-party registry | None | No third-party blocks declared or permitted; no registry vetting needed. |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: exact Simplified Chinese strings for loading / error / empty-as_of / pool-with-results / concept-no-match / 交叉共振-none / 交叉共振-present; research-only disclaimer; no execution vocabulary anywhere; internal names only as inspectable metadata with human labels
- [x] Dimension 2 Visuals: existing dark-first page shell, PageHeader, `EmptyState`, card-grid + table workspace consistent with Screener; no duplicate shell or new design language; component tree matches PoolHubPage → StrategyCardGrid → StrategyCard → StockListTable → ConceptFilter → 交叉共振 highlight
- [x] Dimension 3 Color: established 60/30/10 tokens; accent reserved for 交叉共振 highlight + active card + focus; `数据不可用` warning-only; bull/bear market-direction-only with sign redundancy; 4.5:1 contrast + text/icon redundancy
- [x] Dimension 4 Typography: four-size/two-weight scale (12/14/16/20, 400/600), mono + `tabular-nums` for codes/counts/percentages, safe-wrap status copy, 65ch prose cap
- [x] Dimension 5 Spacing: 4px-based scale (4/8/16/24/32/48/64), 44×44px touch exceptions below 768px, ≥8px touch-target gaps, table scroll without code-column truncation
- [x] Dimension 6 Registry Safety: no shadcn initialization and no third-party registry; timestamped absence evidence recorded (scanned 2026-08-04)


**Approval:** approved 2026-08-04
