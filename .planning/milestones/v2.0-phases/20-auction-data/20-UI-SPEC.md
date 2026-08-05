---
phase: 20
slug: auction-data
status: approved
shadcn_initialized: false
preset: none
created: 2026-08-05
---

# Phase 20 — UI Design Contract

> Visual and interaction contract for the v2.0 竞价数据层 surfaces on the existing `/data` page. This contract extends the Phase-16 竞价数据 panel with a probe-gated **auction-column availability section** (竞价量/竞价金额 with unit labels, real-vs-derived separation, per-date availability) — it does **not** introduce a new shell, route, workspace, or the pool drill-down table (Phase 23). Backend source of truth: `20-RESEARCH.md` probe×column matrix and fail-closed read-path gate.

---

## Scope and Source Decisions

| Source | Binding UI decision |
|---|---|
| `ROADMAP.md` Phase 20 成功标准 1/4 | When probe is `available`, the researcher can see the governed enriched columns `auction_volume` (竞价量) and `auction_amount` (竞价金额, canonical 单位 股/元); when probe is not `available` the columns are **absent** and the feature fails closed to derived `open_gap`, never a silent fill. No UI ever labels the 09:30 continuous bar as 集合竞价 data. |
| `ROADMAP.md` Phase 20 成功标准 2 | The auction panel's availability section reflects `kline_auction/date={d}/` partition state; the lake stores only real 09:15–09:25 auction-window rows and the 09:30 continuous bar is structurally excluded. |
| `ROADMAP.md` Phase 20 成功标准 3 | When 委托量 input is available, the researcher can view the derived 竞价未匹配金额 (`auction_unmatched_amount`) column explicitly labeled 估算; when unavailable the strategy falls back to 量比 + 金额强度 (P2) — the UI shows the derived column as **derived**, never as real. |
| `20-RESEARCH.md` §Read-path 门控 (probe×列矩阵) | The probe-status × auction-column matrix is the single authority: only `available` injects real auction columns (and only for dates whose `kline_auction/date={d}` partition has rows); all other statuses keep the columns absent and the probe status value unchanged; `error` detail is truncated (≤200 chars). |
| `20-RESEARCH.md` §Common Pitfall 4 | Global probe must be combined with per-date partition existence: `probe==available && kline_auction/date={d} 分区存在且有行`; a date without a partition honestly shows absent columns — never null-as-present. |
| `20-RESEARCH.md` §Common Pitfall 5 | The derived unmatched proxy is independently named `auction_unmatched_amount` with an 估算 label; real and derived columns are never summed or mixed. |
| `20-RESEARCH.md` §Open Question 5 (recommendation) | `kline_auction` is registered in the schema surface (`_SCHEMA_VIEWS` / `_TABLE_FIELD_DESC` / `_refresh_single_view`) so the Data page can show the auction lake and its coverage; the auction column Chinese descriptions (with units) reuse the `ENRICHED_COLUMNS` registration. |
| `16-UI-SPEC.md` (approved 2026-08-04) | **Preserve verbatim**: auction probe verdict vocabulary, dark-first tokens, 4px spacing scale, four-size/two-weight type scale, mono/tabular numerals for data, honest fail-closed labels, and the rule that 09:30 bar is never 集合竞价. |
| `frontend/src/pages/Data.tsx` (竞价数据 panel) | The auction surface is the existing `SectionTitle icon={WandSparkles}` + card pattern inside `max-w-2xl` on the Data page (lines 903–909). Phase 20 extends this panel **in place** — no new shell, route, or workspace. |
| `frontend/src/components/data/AuctionProbeCard.tsx` | The existing probe verdict card renders only server `status === "available"` as available; no client-side synthesis of the verdict. Phase 20 keeps this card intact and appends the availability/columns section. |
| `frontend/src/index.css` + `.impeccable/design.json` | Binding dark-first tokens: `base`/`surface`/`elevated`/`border`/`foreground`/`secondary`/`muted`/`accent`/`bull`/`bear`/`warning`/`danger`; radii `rounded-input` 4px, `rounded-btn` 6px, `rounded-card` 8px, `rounded-dialog` 12px; mono/tabular for all data. |

### Phase boundary

- **In scope:** the 竞价数据 panel's probe-gated auction-column availability section — real auction column availability (`auction_volume` / `auction_amount`, units 股/元), 真实集合竞价 vs 派生/虚拟成交 分列明确标注, and the per-date availability note (`kline_auction/date={d}` has rows). Probe status row (Phase 16) preserved. Auction-column schema descriptions (unit-bearing Chinese labels) surface in the schema modal.
- **Out of scope:** the pool drill-down stock table with auction columns and DateNavigator date browsing (Phase 23, FRONT-01/02); strategy result columns and strategy authoring (Phase 21); the pool hub / concept filter / 交叉共振 (shipped Phase 18/19); client-side synthesis of probe verdicts or auction column availability.
- **Not locked by this contract:** the `auction_sync_enabled` / `auction_sync_symbols` preference knobs (20-RESEARCH.md Open Question 1, `[ASSUMED] A3`) — if the planner confirms they ship, they must mirror the `MinuteSyncConfig` pattern (`SettingsModal` titled `竞价数据 · 同步设置`); until then no sync toggle is a contract requirement.

### Hard boundaries (binding, verbatim)

1. **Fail-closed:** probe 非 `available` 时，竞价列（`auction_volume` / `auction_amount`）缺席，功能 fail-closed 回退到派生 `open_gap`，绝不静默填充；任何非 `available` 状态 UI 都不得渲染竞价列，也不得把派生/虚拟数据呈现为真实竞价数据。
2. **09:30 bar 永不标集合竞价:** 09:30 起的连续竞价 bar 永不标记为集合竞价数据；湖内只存真实 09:15–09:25 竞价窗口行，09:30 bar 结构性排除（写湖过滤器与 provider 归一化同一谓词 `555..565` 分钟双重锁死）。
3. **真实 vs 派生 分列:** 真实集合竞价列（`auction_volume` / `auction_amount`，单位 股/元）与派生/虚拟成交列（`auction_unmatched_amount`，标注“估算”）分列明确标注，永不相加比较、永不混排为同一列；UI 呈现与后端 DTO 完全一致（probe×列矩阵唯一权威）。

---

## Design System

| Property | Value |
|---|---|
| Tool | Manual existing system: Tailwind CSS 3.4 tokens and local React components |
| Preset | Not applicable — `components.json` is absent as of 2026-08-05; do not initialize shadcn for this data-layer phase |
| Component library | Existing local components (`AuctionProbeCard`, `StatCard`, `SectionTitle`, `SettingsModal`, `MinuteSyncConfig`) and native semantic controls; no new UI component registry |
| Icon library | `lucide-react`; 14–16px outline icons beside, never instead of, visible labels (`CheckCircle2`, `AlertTriangle`, `Loader2`, `Database`, `WandSparkles`) |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, system sans; `JetBrains Mono`/`IBM Plex Mono` only for data, column identifiers, units, dates, and coverage counts |
| Server state | Existing typed `api.ts` methods plus TanStack Query `QK` factories; no direct `fetch`, no duplicate request helper, no client-side synthesis of probe verdicts or auction-column availability |

### Existing visual tokens to preserve

Use the CSS variables in `frontend/src/index.css` and Tailwind semantic names (`base`, `surface`, `elevated`, `border`, `foreground`, `secondary`, `muted`, `accent`, `bull`, `bear`, `warning`, `danger`). Dark mode remains the default; light mode is the existing token inversion. Use 1px `border-border` separation and existing radii: `rounded-input` 4px, `rounded-btn` 6px, `rounded-card` 8px, `rounded-dialog` 12px. Do not introduce gradients, glass surfaces, oversized rounded cards, decorative shadows, or a Phase-20-specific palette.

---

## Information Hierarchy and Workflow

### Page hierarchy

1. **Page header — 数据:** retain the existing compact title, data-source switcher, and account hint. No new header content.
2. **Existing operational panels:** active job card, quote config, and schedule editors remain exactly as shipped. Phase 20 does not reorder them.
3. **数据画像 (`SectionTitle icon={Database}`):** unchanged; the schema surface (`EnrichedSchemaModal`) gains the `kline_auction` table so auction columns appear with their unit-bearing Chinese descriptions.
4. **竞价数据 panel (`SectionTitle icon={WandSparkles}`, `max-w-2xl`):** the existing probe verdict card is preserved and a new **auction-column availability section** renders below it:
   - **a. Probe verdict row** — Phase 16 vocabulary, unchanged (see preserved table below).
   - **b. Auction-column availability section** — probe `available` → real column list (`竞价量（股）` / `竞价金额（元）`) plus the per-date availability note; probe non-`available` → honest fail-closed empty state with **no** auction columns rendered.

### Required status vocabulary

**Table 1 — Probe verdict (Phase 16, preserved verbatim):**

| State | Visible label and treatment | Allowed actions |
|---|---|---|
| Probe not configured | `竞价数据未配置` in muted text with a short hint | No probe run; hint points to data-source configuration |
| Probe running | `竞价数据探测中…` with `Loader2` spinner and `role="status"` | No concurrent re-run; `重新探测` disabled |
| Auction data available | `竞价数据可用` in accent treatment with a check icon | `重新探测` (secondary); never claim more than the verified capability |
| Probe fail-closed | `未接入竞价数据（已退化派生因子）` in warning treatment with `AlertTriangle` icon | `重新探测`; derived open-gap factors remain the baseline; never label the 09:30 bar as 集合竞价 data |
| Probe failed (error) | `竞价数据探测失败：{message}。已按未接入处理，当前使用派生开盘涨幅因子。` in `role="alert"` | Retry `重新探测`; status never downgrades to `竞价数据可用` |

**Table 2 — Auction-column availability (Phase 20, new):**

| State | Visible label and treatment | Allowed actions |
|---|---|---|
| Auction columns available (probe `available` AND date partition has rows) | `竞价列可用` in accent treatment with `CheckCircle2`; real column list follows — `竞价量（股）` · `auction_volume`, `竞价金额（元）` · `auction_amount` (identifiers mono/tabular) | `重新探测`; read-only display — no client-side synthesis, no column mutation |
| Per-date covered | `竞价湖覆盖 {N} 天` in secondary text with `{N}` mono/tabular; latest covered date note `kline_auction/date={d} 有行` | none |
| Per-date absent (probe `available` but no partition for a date) | `该日期无竞价数据` honest empty note in muted text; no auction columns for that date — never null-as-present | none |
| Auction columns absent (probe `not_configured` / `fail_closed` / `error`) | `竞价列不可用` in muted/warning text with `AlertTriangle`; fail-closed body copy; **no** auction columns rendered | Configure data source; `重新探测`; never render auction columns as real |
| Real columns group | `真实集合竞价` group label (secondary text); rows `竞价量（股）` `auction_volume`, `竞价金额（元）` `auction_amount` | none |
| Derived columns group | `派生 / 虚拟成交` group label (muted text); row `派生未匹配金额（估算）` · `auction_unmatched_amount` with an `估算` badge (neutral `bg-elevated`/`border-border`) | none; real and derived never summed or mixed |
| Unmatched proxy absent (委托量 input unavailable) | No derived column rendered; strategy falls back to 量比 + 金额强度 (P2) | none |

---

## Interaction States and Feedback

| Control class | Default / hover / focus | Disabled / loading / error |
|---|---|---|
| `重新探测` (probe action, preserved) | Secondary elevated treatment beside the verdict; hover `bg-elevated`; focus ring | Disabled while probe running (`竞价数据探测中…`); failure shows inline `role="alert"` below the verdict |
| Auction-column availability section | Static read-only; text + icon always paired; column identifiers and units always visible as text | While the probe runs, row height is reserved (spinner in place); the section never blanks and never renders partial “real” columns |
| 真实 / 派生 group separation | Group labels are visible text (`真实集合竞价` / `派生 / 虚拟成交`); a 1px `border-border` divider and 16px vertical gap separate the groups | Derived `估算` badge is neutral informational (`bg-elevated`, `border-border`) — not warning, not danger; absence of the derived column renders no placeholder |
| Per-date availability note | Static secondary text; date and count mono/tabular | While a sync job runs, the existing active/progress `StatCard` treatment applies; never show a stale coverage count as fresh |
| Schema surface (`kline_auction`) | Existing schema-modal row/group patterns; auction columns grouped under a `竞价` category | Loads via the existing `enrichedSchema(table)` query; failure shows the existing schema-modal empty/error treatment |

Use 150–200ms `ease-smooth` opacity/color transitions only for state feedback. Do not animate initial page entry or layout height. Under `prefers-reduced-motion: reduce`, all state transitions are instant and loading remains text/spinner based.

---

## Data Display

- Real auction columns `auction_volume` / `auction_amount` render **only** when the server reports probe `available` AND the date partition (`kline_auction/date={d}`) has rows. Units are always visible in the column label: `竞价量（股）`, `竞价金额（元）`.
- The derived column `auction_unmatched_amount` renders only when 委托量 input is available, always labeled `估算`; it lives in the `派生 / 虚拟成交` group, never in the `真实集合竞价` group.
- Column identifiers (`auction_volume`, `auction_amount`, `auction_unmatched_amount`), dates, and the coverage count `{N}` use the mono family with `tabular-nums`.
- Fail-closed renders **no** auction columns — honest empty-state copy only. Do not render placeholder dashes or zero values that could read as real data.
- Per-date availability is expressed as `kline_auction/date={d} 有行` (mono date) and `竞价湖覆盖 {N} 天` (mono `{N}`); a date without a partition shows `该日期无竞价数据`, never a null-as-present column.
- Status is communicated by the literal state words in the vocabulary tables, not by weight, color, or icon alone. Every state pairs visible text with a Lucide icon (`aria-hidden` when it duplicates the label).
- No charts or per-stock auction tables exist in Phase 20 — the pool drill-down table lands in Phase 23 (FRONT-02).

---

## Spacing Scale

Declared values (all multiples of 4):

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | Icon-label gap, compact badge padding (`估算`) |
| sm | 8px | Group-label to column-row gap, compact control group gap |
| md | 16px | Default component gap, panel inner padding, real↔derived group separation |
| lg | 24px | Related-panel separation and desktop panel padding |
| xl | 32px | Section separation within the Data page |
| 2xl | 48px | Major workflow boundary only |
| 3xl | 64px | Page-level separation only; do not add empty decorative space inside data tools |

**Exceptions:** Existing dense desktop controls use compact 8px paddings for scanability. At viewport widths below 768px, the `重新探测` action must have a 44×44px hit area even when the visible glyph/control remains compact. Keep at least 8px between adjacent touch targets.

---

## Typography

Use one existing sans family for all UI labels, headings, buttons, and body copy. Phase-20 additions use exactly these four sizes and two weights; code/data may use the existing mono family at the same declared size.

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Metadata / labels | 12px | 400 | 1.5 |
| Body / panel content | 14px | 400 | 1.5 |
| Section heading | 16px | 600 | 1.2 |
| Page heading | 20px | 600 | 1.2 |

- Use `font-weight: 600` only for page headings, section headings, status names, and primary actions. All other content uses 400.
- Column identifiers, units, dates, and coverage counts use the mono family at the same declared size with `tabular-nums`.
- Keep prose explanations at a maximum of 65ch. Status copy may use available panel width but must wrap safely (`overflow-wrap:anywhere`) instead of overflowing.

---

## Color

The established restrained dark-first system is binding. The 60/30/10 split describes surface allocation, not a reason to tint all controls.

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `base`: dark `#0A0A0B`; light `#FAFAFA` | Application and Data page background |
| Secondary (30%) | `surface`: dark `#18181B`; light `#FFFFFF`; `elevated`: dark `#212126`; light `#F4F4F5` | Workspace panels, cards, toolbar backgrounds, `估算` badge background |
| Accent (10%) | `accent` `#3B82F6` | `重新探测` action, focus rings, `竞价数据可用` and `竞价列可用` identity, and neutral information identity only |
| Warning | `warning` `#F79009` | Fail-closed/degraded states: `未接入竞价数据（已退化派生因子）`, `竞价列不可用` |
| Destructive | `danger` `#F04438` | Probe failure diagnostics and truly destructive controls only |
| Market direction | `bull` `#F04438` for A-share positive/red; `bear` `#12B76A` for A-share negative/green | 涨跌幅/开盘涨幅 direction only; never generic success/error state |

Accent is reserved for: primary controls, active states, focus rings, and neutral information identity. It is **not** a decoration color, a generic card border, or the visual status of every clickable element.

`bear` green `#12B76A` is market-direction-only — do **not** reuse it as a generic “available” success color. `竞价数据可用` / `竞价列可用` use accent + check icon, consistent with the accent reservation.

The 真实/派生 distinction is conveyed by visible text labels (`真实集合竞价` / `派生 / 虚拟成交`), group separation, and the `估算` badge — **never by color alone**. The `估算` badge is neutral (`bg-elevated` + `border-border`), because absence of the derived input is informational, not a failure.

All normal text and interaction labels must meet 4.5:1 contrast against their occupied surface; large/bold text and focus indicators must meet at least 3:1. Provide text/icon redundancy for every status and market-direction state.

---

## Responsive Behavior

| Viewport | Required layout behavior |
|---|---|
| `≥1280px` | Retain the existing Data-page grid and panel widths unchanged; the 竞价数据 panel follows the existing `max-w-2xl` width |
| `768–1279px` | Panels stack per the existing `md:grid-cols-3` → single-column behavior; the probe verdict row and the availability section wrap |
| `<768px` | One-column flow: header wraps title/subtitle before controls; `重新探测` meets the 44px target; column rows and group labels stack vertically; fail-closed copy wraps safely (`overflow-wrap:anywhere`) |

Do not use fluid heading sizes. Preserve the existing Data-page layout conventions and panel spacing; no new shell or route is introduced at any viewport.

---

## Accessibility Contract

- Use semantic `main`, `section`, `aside`, headings in order, native `button`, native `input`, native `checkbox`, and native `details` before custom equivalents. Every form field has a visible programmatic `<label>`.
- Probe running uses `role="status"` or a polite live region; probe failure uses `role="alert"`. The fail-closed empty state is readable prose (not an icon or color alone).
- Associate help/error text with controls through `aria-describedby`. The auction-column availability section is a read-only region — no focus trap, no interactive container.
- Unit labels (`股`/`元`), group labels (`真实集合竞价` / `派生 / 虚拟成交`), and the `估算` marker are **text**, not icon/color-only. All Lucide icons that duplicate label text are `aria-hidden`; an icon-only action has an explicit `aria-label` and tooltip.
- Use a visible 2px accent focus ring with 2px offset on every keyboard-reachable control. Never remove focus outlines without providing that replacement. Keyboard order follows visual order.
- Respect `prefers-reduced-motion`; do not make state updates dependent on animation. Maintain readable contrast in both current light and dark themes.

---

## Copywriting Contract

| Element | Copy |
|---|---|
| Minute-K primary CTA (preserved) | `启用分钟K同步` (toggle on) / `自动同步` (existing on-state label) |
| Probe primary action (preserved) | `重新探测` |
| Probe not configured (preserved) | heading `竞价数据未配置`; body `尚未配置竞价数据源；配置后平台将自动探测 9:15–9:25 集合竞价匹配数据的可用性。` |
| Probe running (preserved) | `竞价数据探测中…` |
| Auction available (preserved) | `竞价数据可用` |
| Probe fail-closed heading (preserved) | `未接入竞价数据（已退化派生因子）` |
| Probe fail-closed body (preserved) | `平台未检测到可用的集合竞价匹配数据，已退化到派生开盘涨幅因子（open / prev_close − 1）。09:30 起的连续竞价 bar 不会被标记为集合竞价数据。` |
| Probe failure (preserved) | `竞价数据探测失败：{message}。已按未接入处理，当前使用派生开盘涨幅因子。请重试。` |
| Auction columns available heading | `竞价列可用` |
| Real columns group label | `真实集合竞价` |
| Real column rows | `竞价量（股）` · `auction_volume`; `竞价金额（元）` · `auction_amount` (identifiers mono) |
| Derived columns group label | `派生 / 虚拟成交` |
| Derived column row | `派生未匹配金额（估算）` · `auction_unmatched_amount` + `估算` badge |
| Derived column body | `由委托量输入派生的未匹配金额估算值，非真实成交；输入不可得时策略回退到量比 + 金额强度。` |
| Per-date availability | `竞价湖覆盖 {N} 天` · `kline_auction/date={d} 有行` |
| Per-date absent | `该日期无竞价数据` |
| Auction columns fail-closed heading | `竞价列不可用` |
| Auction columns fail-closed body | `未接入竞价数据源，竞价量/竞价金额列不可用。平台已 fail-closed 回退到派生开盘涨幅因子（open / prev_close − 1）。09:30 起的连续竞价 bar 不会被标记为集合竞价数据。` |
| Destructive confirmation | None in Phase 20 — no destructive actions. |

Use clear Chinese task language, not unexplained internal implementation names. `kline_auction`, `auction_volume`, capability keys, and timestamp values may appear as inspectable metadata but must be accompanied by a human label.

---

## UI Considerations

> Populated by the ui-phase UI-consideration probe (Step 9.5) and lifted by plan-phase's
> `## UI Considerations` lift rule. Shape-rooted UI *state* coverage (empty / loading / error /
> populated / partial / overflow / zero-one-many / long-text). Empty-state and error-state COPY
> live in `## Copywriting Contract` above — this section covers state coverage and references
> those rows rather than restating the copy (de-dup).

Applicable state considerations resolved: 6 covered, 4 backstop, 0 unresolved — backend data layer with a probe-gated auction-column availability section on the Data page.

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| loading | 竞价列可用性 section | ✅ covered | probe 运行中保留行高状态行（`竞价数据探测中…` + `Loader2` + `role="status"`）; section 不渲染部分“真实”列 |
| error | 竞价列可用性 section | ✅ covered | probe error → `竞价数据探测失败：{message}。…请重试。` `role="alert"` + `重新探测`; 列 fail-closed, 09:30 bar 绝不标为集合竞价数据 |
| empty | 竞价列可用性 section | ✅ covered | probe 非 available → `竞价列不可用` + fail-closed body, 无任何竞价列渲染（无占位虚线/零值） |
| populated | 竞价列可用性 section | ✅ covered | probe available 且有分区行 → `竞价列可用` accent 检查图标 + 真实列 `竞价量（股）`/`竞价金额（元）` 与派生列 `派生未匹配金额（估算）` 分列列出 |
| partial | 竞价列可用性 section | ✅ covered | probe available 但某日期无分区 → `该日期无竞价数据` 诚实按日空态, 非 null-as-present |
| partial | 派生列 | ✅ covered | 委托量输入不可得 → 派生列缺席, 显示回退说明（量比 + 金额强度）, 不显示占位 |
| overflow | 竞价列可用性 section | 🧪 backstop | 列/组副本安全换行 `overflow-wrap:anywhere`, 不溢出 `max-w-2xl` 面板 |
| long-text | 竞价列可用性 section | 🧪 backstop | fail-closed 长文案换行包裹, 不截断 |
| zero-one-many | 竞价湖覆盖 | 🧪 backstop | `竞价湖覆盖 {N} 天` 单复数由模板文案处理; 0 天不渲染为“可用” |
| long-text | probe 判定 (preserved) | 🧪 backstop | Phase 16 既有长文案换行行为保持, 不回归 |

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
| shadcn official | None | Not applicable — `components.json` absent when scanned on 2026-08-05; shadcn initialization is explicitly excluded for this data-layer phase. |
| Third-party registry | None | No third-party blocks declared or permitted; no registry vetting needed. |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: clear status labels, real-vs-derived separation copy, fail-closed empty language, and no opaque internal-only wording
- [ ] Dimension 2 Visuals: existing dark-first Data-page layout, in-place 竞价数据 panel extension, no duplicate shell or new route
- [ ] Dimension 3 Color: established 60/30/10 tokens, reserved accent, warning-only fail-closed, neutral informational `估算` badge, and contrast/redundancy
- [ ] Dimension 4 Typography: four-size/two-weight scale, mono/tabular column identifiers, units, dates, and counts
- [ ] Dimension 5 Spacing: 4px-based scale, responsive touch exceptions, and real↔derived group rhythm
- [ ] Dimension 6 Registry Safety: no shadcn initialization or third-party registry; timestamped absence evidence recorded

**Approval:** pending
