---
phase: 19
slug: guest-access
status: approved
shadcn_initialized: false
preset: none
reviewed_at: 2026-08-04
created: 2026-08-04
---

# Phase 19 — UI Design Contract

> Visual and interaction contract for the 游客/VIP 脱敏 (Guest Access) layer on the 股池 (Pool Hub) page. This contract extends the approved Phase-18 pool surface with a server-authoritative guest/VIP presentation contract: guests see masked `******` stock code/name and only 涨跌幅/概念板块 (+ 关联因子 strategy labels), VIP sessions see 明文 including 开盘涨幅. It adds the 名称 column to the drill-down table, a guest-mode banner, and a guest column set — and it explicitly bans any client-side masking code. It does not introduce date navigation (v2), execution affordances (POOL-03), or any change to the strategy engine's internal correctness (GUEST-02).

---

## Scope and Source Decisions

| Source | Binding UI decision |
|---|---|
| `ROADMAP.md` Phase 19 成功标准 | Guests see only 涨跌幅 and 概念板块 with stock code/name masked (`******`) at the API DTO boundary; VIP responses are 明文. No client-side masking is trusted. Masking is display-only — underlying factor computation and strategy results remain unmasked and correct for all sessions (GUEST-02). |
| `REQUIREMENTS.md` GUEST-01 | Non-VIP (guest) sessions see only 涨跌幅 and 概念板块, with stock code/name masked (`******`) applied server-authoritatively at the API DTO boundary; VIP sessions receive 明文. No client-side masking is trusted. |
| `REQUIREMENTS.md` GUEST-02 | Guest masking does not degrade the strategy engine's own internal correctness — masked fields are display-only, underlying factor computation remains unmasked. |
| `19-CONTEXT.md` Decisions #1–#6 | Server-authoritative masking at the API DTO boundary based on session/VIP state (PITFALL #8) — NEVER in the frontend; display-only, engine-correct; VIP = authenticated non-guest session; masked format `******` (6 asterisks) for code/name/symbol with 涨跌幅/概念板块 visible and 关联因子 (strategy labels, not PII) visible; 开盘涨幅 follows the ROADMAP letter — guests see ONLY 涨跌幅 and 概念板块, so 开盘涨幅 is hidden for guests; the frontend pool page renders whatever the API returns so no client masking code exists anywhere; no new datastore. |
| `.planning/research/v1.3-auction/SUMMARY.md` | Reference UI table stakes include 游客模式: 仅展示涨跌幅与概念, 股票代码/名称脱敏; VIP 明文; guest masking is server-authoritative at the API boundary, never client-side (PITFALL #8). |
| `18-UI-SPEC.md` (approved) | Phase-18 pool surface is the composition base: card grid → drill-down table → concept filter → 交叉共振 highlight. Phase 18 explicitly deferred "a 名称 column, with its masked/unmasked variants" to the Phase 19 guest composition. All Phase-18 status vocabulary, tokens, and interaction states are retained unless this contract overrides them for guest mode. |
| `frontend/src/pages/PoolHubPage.tsx` + `frontend/src/components/pool-hub/*` | Existing read-only workspace shell: PageHeader → ConceptFilter → StrategyCardGrid → StockListTable → research footer. Phase 19 adds the guest presentation layer on top of this exact tree — no new shell, no new design language. |
| `backend/app/api/pool.py` + `backend/app/services/pool_hub.py` | The `GET /api/pool/hub` DTO is the masking boundary: per-row `code`/`name`/`symbol` are masked at this layer for guest sessions; `change_pct`/`concept_board`/`hit_factors`/`cross_resonance` stay visible; `open_gap` is nulled/omitted for guests. The service projection (single-`as_of`, concept filter, 交叉共振) is unchanged (GUEST-02). |
| `backend/app/api/auth.py` + `backend/app/services/auth.py` + `backend/app/main.py` auth_middleware | Session/VIP state is server-owned (HttpOnly `tf_session` cookie, `is_valid_session`, `request.state.reviewer_principal`). The presentation mode for the pool hub is derived server-side from this session state and declared in the hub response — never derived client-side from row values. |
| `.impeccable/design.json` + `frontend/src/index.css` + `tailwind.config.ts` | Binding dark-first tokens (`base`/`surface`/`elevated`/`border`/`foreground`/`secondary`/`muted`/`accent`/`bull`/`bear`/`warning`/`danger`), 4px spacing scale, four-size/two-weight type scale, mono for data/identifiers, radii `rounded-input` 4 / `rounded-btn` 6 / `rounded-card` 8 / `rounded-dialog` 12, `ease-smooth` timing. |
| `16-UI-SPEC.md` / `18-UI-SPEC.md` (approved v1.3 convention) | Same UI-SPEC structure, required-status-vocabulary style, Simplified Chinese copy voice, covered-truths/backstop-scalars discipline, and 6-dimension self-check. |

### Phase boundary

- **In scope:** the guest/VIP presentation layer on the pool page — a server-declared presentation mode (`guest` | `vip`), a guest-mode banner, the 名称 column added to the drill-down table (明文 for VIP, `******` for guest), the guest column set (开盘涨幅 column hidden for guests), masked-cell rendering of server-masked rows verbatim, and the backend DTO masking at the `GET /api/pool/hub` boundary (display-only serialization transform). All Phase-18 interactions (drill-down, concept filter, refresh, 交叉共振 highlight) remain, unchanged, in both modes.
- **Out of scope:** 日期导航 per-trading-day browsing (POOL-04, v2); any execution/trade/order affordance and any watchlist/portfolio mutation (POOL-03); strategy authoring/settings UI (Phase 17, done); true 集合竞价 match-data columns (DATA-04, v2); any change to the strategy engine, factor computation, or persisted strategy results (GUEST-02); any new datastore; any client-side masking code of any kind.

---

## Design System

| Property | Value |
|---|---|
| Tool | Manual existing system: Tailwind CSS 3.4 tokens and local React components |
| Preset | Not applicable — `components.json` is absent as of 2026-08-04 (verified again this session); do not initialize shadcn for this phase |
| Component library | Existing local components only (`PageHeader`, `EmptyState`, `StrategyCardGrid`, `ConceptFilter`, `StockListTable`, `stock-table/primitives.tsx`); no new UI component registry |
| Icon library | `lucide-react`; 14–16px outline icons beside, never instead of, visible labels; a lock/shield icon for the guest banner |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, system sans; `JetBrains Mono`/`IBM Plex Mono` only for data, identifiers, codes, counts — and for the masked `******` cell |
| Server state | Existing typed `api.ts` methods plus TanStack Query `QK` factories; the hub response's `mode` field (server-declared) is the only driver of guest presentation. No direct `fetch`, no duplicate request helper, no client-side synthesis of masked values or of the guest mode |

### Existing visual tokens to preserve

Use the CSS variables in `frontend/src/index.css` and Tailwind semantic names (`base`, `surface`, `elevated`, `border`, `foreground`, `secondary`, `muted`, `accent`, `bull`, `bear`, `warning`, `danger`). Dark mode remains the default; light mode is the existing token inversion. Use 1px `border-border` separation and existing radii: `rounded-input` 4px, `rounded-btn` 6px, `rounded-card` 8px, `rounded-dialog` 12px. Do not introduce gradients, glass surfaces, oversized rounded cards, decorative shadows, or a Phase-19-specific palette. The masked cell is a token-composed visual (mono + `muted`), not a new treatment.

---

## Information Hierarchy and Workflow

### Page hierarchy

The pool hub remains a single read-only workspace. The presentation mode is server-declared in the hub response and displayed once as a page-level banner (guest only). The `as_of` date stays server-authoritative and displayed once in the header; there is no date picker and no per-day navigation.

```
PoolHubPage  (route /pool-hub · nav 「股池」)
├── PageHeader
│   ├── title 「股池」
│   ├── subtitle 「竞价策略 · 数据日期 {as_of} · 仅研究参考」
│   └── actions: 刷新股池 (RefreshCw, secondary)
├── GuestModeBanner  [NEW Phase 19 — renders only when mode = guest]
│   └── 「游客模式：股票代码与名称已脱敏」 + body 「仅展示涨跌幅与概念板块。」 (Lock icon, role="status")
├── ConceptFilter  (概念筛选 input + 清除筛选)  [unchanged]
├── StrategyCardGrid  (flex-wrap, gap per existing cardWrapCls)  [unchanged — strategy names are labels, visible to guests]
│   └── StrategyCard × N
│       ├── strategy name (600 weight, truncates)
│       ├── 当日池数 「当日池 {N} 只」 (N mono)
│       ├── active/selected state (accent border + tint)
│       └── on-click → drills into that strategy (read-only)
└── StockListTable  [Phase 19 — adds 名称 column; guest mode hides 开盘涨幅 column]
    ├── thead: [guest] 代码 | 名称 | 涨跌幅 | 概念板块 | 关联因子
    │          [vip]   代码 | 名称 | 开盘涨幅 | 涨跌幅 | 概念板块 | 关联因子
    ├── tbody rows (渲染服务端返回的行 — guest 行原样含 `******`; 交叉共振行保留 accent 高亮 + 徽标)
    │   └── 关联因子 cell: strategy-name tags + 「交叉共振 · {N} 策略」 badge  [unchanged]
    └── footer meta: 「筛选后 {N} 只 / 共 {M} 只」 · 交叉共振 legend  [unchanged]
```

Workflow: open the page → the hub loads the single-`as_of` pool plus the server-declared `mode` → if guest, the banner states the masking policy and the table renders masked rows with the guest column set; if VIP, the table renders 明文 rows with 开盘涨幅. Card grid, drill-down, concept filter, refresh, and 交叉共振 highlight behave exactly as Phase 18 in both modes. Nothing on the page writes to a portfolio, places an order, or routes to a broker.

### Guest vs VIP presentation contract

The core contract of this phase. Presentation mode comes from the server (`mode: "guest" | "vip"` in the hub response, or an equivalent server-declared boolean); the frontend MUST NOT derive it by inspecting row values (e.g. `code === '******'`), which would be client-side masking logic.

| Aspect | Guest (`mode: "guest"`) | VIP (`mode: "vip"`) |
|---|---|---|
| Banner | `游客模式：股票代码与名称已脱敏` (neutral info banner) | None (VIP unchanged) |
| 代码 column | `******` — mono, `muted`, no board tag, no stock identity hint | Real code, mono `tabular-nums` `text-secondary`, existing board tag (创/科/北) when applicable |
| 名称 column | `******` — mono, `muted` | Real stock name (sans, 400, `text-foreground`) |
| 开盘涨幅 column | Hidden — column header and cells are not rendered | Rendered — `fmtPct`, `priceColorClass`, missing → `—` |
| 涨跌幅 column | Rendered — `fmtPct`, `priceColorClass` | Rendered — unchanged |
| 概念板块 column | Rendered — concept chips (unchanged) | Rendered — unchanged |
| 关联因子 column | Rendered — strategy-name tags + 交叉共振 badge (unchanged; labels, not PII) | Rendered — unchanged |
| 交叉共振 highlight | Accent row tint + badge + legend — unchanged | Unchanged |
| Row identity (React key) | Strategy-scoped ordinal (index) or a server-provided stable id — NEVER the masked symbol | `row.symbol` (real, unique) |
| All Phase-18 status vocabulary (loading/error/empty/card states/drill states) | Unchanged, both modes | Unchanged |

Masked value semantics: the masked code/name cells display the exact server-provided `******` string verbatim. The frontend contains no function that produces or transforms masked text.

### Required status vocabulary

| State | Visible label and treatment | Allowed actions |
|---|---|---|
| Guest mode banner | `游客模式：股票代码与名称已脱敏` — neutral info banner: `bg-elevated/60 border border-border rounded-btn px-3 py-2`, `Lock` icon 14px `aria-hidden`, title `text-sm text-secondary`, body `仅展示涨跌幅与概念板块。` `text-xs text-muted`, `role="status"` (polite live region) | None (informational) |
| Guest masked cell | `******` — mono, `text-muted`, `tabular-nums`; no board tag; never blank, never `—` | None |
| Guest table columns | `代码 | 名称 | 涨跌幅 | 概念板块 | 关联因子` | Drill/filter/refresh exactly as Phase 18 |
| VIP table columns | `代码 | 名称 | 开盘涨幅 | 涨跌幅 | 概念板块 | 关联因子` | Drill/filter/refresh exactly as Phase 18 |
| Hub loading | `股池加载中…` (Phase 18, unchanged); banner does not render until `mode` is known | None while pending |
| Hub error | `股池加载失败：{message}。请检查数据源后重试。` (Phase 18, unchanged) | `重试` |
| Empty — no results for as_of | `当日无股池结果` (Phase 18, unchanged); guest banner still renders when the loaded hub declares guest mode — the banner is a session-policy state, not a data state | `刷新股池` |
| Strategy card states | `股池统计中…` / `当日无命中` / `数据不可用` / active (Phase 18, unchanged — strategy names are visible to guests) | Phase 18 behaviors |
| Drill-down loading / error / empty | `股池明细加载中…` / `股池明细加载失败：{message}。请重试。` / `无符合「{概念}」的个股` / `该策略当日无命中个股。` (Phase 18, unchanged) | Phase 18 behaviors |
| 交叉共振 — none / present | `今日无交叉共振 · 暂无个股被 ≥2 个竞价策略同时命中。` / `交叉共振 · {N} 策略` badge + legend (Phase 18, unchanged, both modes) | None (informational) |

Every state above is communicated by its literal words plus an icon or treatment, never by color alone. The guest banner is the only new state; all other rows are retained Phase-18 vocabulary applied unchanged in both modes.

---

## Interaction States and Feedback

| Control class | Default / hover / focus | Guest-mode behavior |
|---|---|---|
| Guest banner | Neutral info banner, `rounded-btn`, no interaction; `role="status"` | Renders only when `mode = guest`; disappears on refresh only if the server re-declares `vip`; never dismissible by the user (it is a policy statement, not a toast) |
| Strategy card | Phase 18 unchanged (surface card, hover `border-accent/40`, focus ring, selected = accent) | Identical in guest mode — strategy names, 当日池数, and 数据不可用 are visible to guests |
| 概念筛选 input | Phase 18 unchanged | Identical in guest mode; filtering projects over the loaded masked rows by 概念板块 only |
| `清除筛选` / `刷新股池` | Phase 18 unchanged | Identical in guest mode |
| Table row | Phase 18 unchanged (`border-t border-border hover:bg-elevated/50`; 交叉共振 rows keep `bg-accent/[0.06]` + left accent border) | Identical in guest mode; rows keyed by strategy-scoped ordinal, never the masked symbol, so no duplicate-key collisions when many rows show `******` |
| 代码 / 名称 cells | VIP: board tag + mono code; name in sans | Guest: `******` mono `muted` in both cells; no board tag; cells are inert text — no copy affordance, no tooltip with the real value |
| 开盘涨幅 column | VIP: sortable header + `PctCell` | Guest: column and header not rendered at all; the table reflows to the 5-column set without a layout jump |
| 涨跌幅 cells | Phase 18 unchanged (`PctCell`, `priceColorClass`) | Identical in guest mode |

Use 150–200ms `ease-smooth` opacity/color transitions for the guest banner entrance and card hover / active-card states only. Do not animate the column-set change (guest vs VIP) beyond a single opacity transition on the table block; under `prefers-reduced-motion: reduce`, all transitions are instant and the banner remains text/icon based.

---

## Data Display

- **代码 (guest):** `******` — mono, `tabular-nums`, `text-muted`, no board tag. The value is the server-masked string rendered verbatim.
- **代码 (VIP):** mono `tabular-nums` `text-secondary`, prefixed by the existing board tag (`创`/`科`/`北`, `stock-table/primitives.tsx`) when applicable — unchanged from Phase 18.
- **名称 (guest):** `******` — mono, `tabular-nums`, `text-muted`, no identity hint.
- **名称 (VIP):** real stock name, sans 400 `text-foreground`, truncates with ellipsis at cell width; never a blank cell (missing name renders `—` in muted only if the server supplies no name).
- **开盘涨幅 / 涨跌幅:** `fmtPct` (signed percentage, `+N.NN%`), mono, `priceColorClass` (A-share red-up `bull`, green-down `bear`); missing → `—`. The 开盘涨幅 column is present only in VIP mode; in guest mode the header and cells are not rendered.
- **概念板块:** comma-separated concept chips (existing tag pattern), wrapping; first few + `+{N}` expand/collapse per the existing `renderTagList` idiom — never clip mid-label. Identical in both modes.
- **关联因子:** strategy-name tags (existing amber `STRATEGY_TAG_CLS`). When the row is 交叉共振 (≥2 hits from `hit_factors`), the cell additionally renders the accent `交叉共振 · {N} 策略` badge. Identical in both modes — these are strategy labels, not PII.
- **当日池数:** `当日池 {N} 只`, `{N}` always mono/`tabular-nums`. Identical in both modes.
- **Counts / meta:** drill footer `筛选后 {N} 只 / 共 {M} 只` when a concept filter is active, otherwise `共 {M} 只` — Phase 18 unchanged, both modes.
- **Server-mode signal:** the hub response declares the presentation mode (`mode: "guest" | "vip"` or an equivalent server-declared boolean). The frontend consumes it for the banner and the column set; it never infers mode from row values.
- No charts, no sparklines, no heat maps on the pool hub — unchanged from Phase 18.

---

## Spacing Scale

Declared values (all multiples of 4):

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | Icon-label gap in the guest banner, badge inner padding, board-tag gap |
| sm | 8px | Card inner padding gap, tag row gap, table cell horizontal padding on compact rows |
| md | 16px | Default component gap, guest-banner inner padding (`px-3 py-2`), table cell padding |
| lg | 24px | Section separation (card grid → drill table), page inner padding on desktop |
| xl | 32px | Between major blocks (header → banner, banner → filter, filter → grid) |
| 2xl | 48px | Page-level separation only |
| 3xl | 64px | Page-level separation only; no decorative empty space inside the data tool |

**Exceptions:** At viewport widths below 768px, the guest banner text must wrap safely (`overflow-wrap:anywhere`) and keep ≥8px around the icon; the 概念筛选 input, its clear button, `清除筛选`, and `刷新股池` keep the Phase-18 44×44px hit-area exception. Table cells may compress below 16px only inside the horizontal-scroll container, never by truncating the masked `******` cell (fixed 6-char width fits without truncation).

---

## Typography

Use one existing sans family for all UI labels, headings, buttons, and body copy. Phase-19 additions use exactly these four sizes and two weights; code/data (and the masked `******` cell) use the existing mono family at the same declared size.

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Metadata / labels | 12px | 400 | 1.5 |
| Body / table content | 14px | 400 | 1.5 |
| Section heading | 16px | 600 | 1.2 |
| Page heading | 20px | 600 | 1.2 |

- Use `font-weight: 600` only for page/section headings, strategy card names, status names, and the 交叉共振 badge — unchanged. The guest banner title uses 400 (`text-sm`), not a heading weight; it is a notice, not a section heading.
- The masked `******` cell is mono (`num` class) with `tabular-nums`; it never renders in bold or accent — muted mono reads as "identity withheld", distinct from the secondary mono of real codes.
- Keep prose explanations at a maximum of 65ch. Status copy (including the guest banner) may use available panel width but must wrap safely (`overflow-wrap:anywhere`) instead of overflowing.

---

## Color

The established restrained dark-first system is binding. The 60/30/10 split describes surface allocation, not a reason to tint all controls. Phase 19 adds one neutral banner treatment and reuses existing tokens — no new palette.

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `base`: dark `#0A0A0B`; light `#FAFAFA` | Page background |
| Secondary (30%) | `surface`: dark `#18181B`; light `#FFFFFF`; `elevated`: dark `#212126`; light `#F4F4F5` | Strategy cards, table container, control backgrounds, guest banner (`bg-elevated/60`) |
| Accent (10%) | `accent` `#3B82F6` | 交叉共振 highlight only (row tint `bg-accent/[0.06]` + left border + `交叉共振 · {N} 策略` badge), active/selected strategy card, focus rings, 当日池数 numerals, single-as_of identity in the header — unchanged; NOT used for the guest banner or the masked cell |
| Warning | `warning` `#F79009` | Degraded-state labels: `数据不可用` strategy card only — unchanged; NOT used for the guest banner (guest mode is a policy state, not a degraded state) |
| Destructive | `danger` `#F04438` | Error diagnostics (`role="alert"`) only — unchanged |
| Market direction | `bull` `#F04438` for A-share positive/red; `bear` `#12B76A` for A-share negative/green | 开盘涨幅 / 涨跌幅 direction only (涨跌幅 visible to guests; 开盘涨幅 VIP-only) |
| Masked identity | `muted` (`#8E8E96` dark / `#A1A1AA` light) | The `******` cell in 代码/名称 for guests — muted mono reads as withheld identity, distinct from real `secondary` codes |

Accent is reserved for: 交叉共振 highlight, the active strategy card, focus rings, and the primary numeric identity (当日池数 / as_of). It is **not** a decoration color, not the guest-banner color, and not the masked-cell color. `bear` green `#12B76A` is market-direction-only — do **not** reuse it as a generic "available" success color. All normal text and interaction labels must meet 4.5:1 contrast against their occupied surface; large/bold text and focus indicators must meet at least 3:1. Provide text/icon redundancy for every status and market-direction state (the guest banner pairs the Lock icon with the literal 脱敏 statement).

---

## Responsive Behavior

| Viewport | Required layout behavior |
|---|---|
| `≥1280px` | Card grid multi-column `flex-wrap`; drill table full width; guest banner on one row with icon + title + body |
| `768–1279px` | Cards wrap to two columns; drill table full width with `overflow-x-auto` when columns exceed the container; guest banner wraps text safely |
| `<768px` | One-column card grid; table inside a horizontal-scroll container; guest banner stacks icon/title/body and wraps (`overflow-wrap:anywhere`); 概念筛选 input, clear, `清除筛选`, and `刷新股池` meet 44px touch targets |

Do not use fluid heading sizes. The pool hub keeps the existing page layout conventions (PageHeader + `px-4 py-4 space-y-3 sm:px-6 lg:px-8` shell); the guest banner is inserted as one element in that shell (between the header block and the ConceptFilter) with the standard `space-y-3` gap. No new shell at any viewport. The guest table's 5-column set fits the same `minWidth: 720` container with room to spare; the column-set difference (guest hides 开盘涨幅) must not cause a page-level reflow.

---

## Accessibility Contract

- Use semantic `main`, `section`, native `button`, native `input`, and a native `<table>` with `<th scope="col">` headers before custom equivalents — unchanged from Phase 18.
- The guest banner is a real element announced to assistive tech: `role="status"` (polite) with the exact copy `游客模式：股票代码与名称已脱敏，仅展示涨跌幅与概念板块。` as its accessible text; the `Lock` icon is `aria-hidden`.
- Masking is never communicated by visual style alone: the banner states the policy in words, and every masked cell shows the literal `******` string (not an empty or `—` cell), so screen-reader users hear the same withheld-identity signal as sighted users.
- The guest 代码/名称 cells expose no tooltip, `aria-label`, or copy affordance that could leak the real value; the real value exists only in the server payload and is never rendered or referenced in the DOM.
- The drill-down table exposes its row count to assistive tech (`共 {M} 只` in the footer meta) — unchanged, both modes.
- Use a visible 2px accent focus ring with 2px offset on every keyboard-reachable control. Keyboard order follows visual order. All Lucide icons that duplicate label text are `aria-hidden`.
- Respect `prefers-reduced-motion`; do not make state updates depend on animation. Maintain readable contrast in both current light and dark themes — the `muted` masked cell must still meet 4.5:1 against `base`/`elevated` table backgrounds.

---

## Copywriting Contract

| Element | Copy |
|---|---|
| Guest banner title | `游客模式：股票代码与名称已脱敏` |
| Guest banner body | `仅展示涨跌幅与概念板块。` |
| Guest banner accessible text (aria) | `游客模式：股票代码与名称已脱敏，仅展示涨跌幅与概念板块。` |
| Guest masked cell | `******` (mono, muted — rendered verbatim from the server response) |
| Guest column headers | `代码` · `名称` · `涨跌幅` · `概念板块` · `关联因子` |
| VIP column headers | `代码` · `名称` · `开盘涨幅` · `涨跌幅` · `概念板块` · `关联因子` |
| Page title | `股池` (unchanged) |
| Page subtitle | `竞价策略 · 数据日期 {as_of} · 仅研究参考` (unchanged) |
| Primary action | None — research-only; no verb+noun CTA implying an action on stocks (unchanged) |
| Refresh action | `刷新股池` (unchanged) |
| Strategy card count | `当日池 {N} 只` (unchanged) |
| Strategy card states | `股池统计中…` / `当日无命中` / `数据不可用` (unchanged) |
| Drill-down heading | `{策略名} · 股池明细` (unchanged) |
| Drill-down footer | `共 {M} 只` / `筛选后 {N} 只 / 共 {M} 只` (unchanged) |
| 概念筛选 label / placeholder | `概念筛选` / `输入概念名筛选…` (unchanged) |
| Clear filter | `清除筛选` (unchanged) |
| Concept filter — no match | heading `无符合「{概念}」的个股`; body `试试切换其他概念或清除筛选。` (unchanged) |
| 交叉共振 badge / legend / none | `交叉共振 · {N} 策略` / `交叉共振：被 ≥2 个竞价策略同时命中的个股` / `今日无交叉共振 · 暂无个股被 ≥2 个竞价策略同时命中。` (unchanged, both modes) |
| Hub loading / error | `股池加载中…` / `股池加载失败：{message}。请检查数据源后重试。` (unchanged) |
| Hub empty | heading `当日无股池结果`; body `截至 {as_of}，竞价策略均无命中个股。请先在策略页运行竞价策略，或确认数据日期。` (unchanged) |
| Drill-down loading / error | `股池明细加载中…` / `股池明细加载失败：{message}。请重试。` (unchanged) |
| Research-only disclaimer | `本页面仅用于研究参考，不提供任何交易执行功能。` (footer, muted — unchanged) |
| Destructive confirmation | None. Phase 19 adds no destructive or irreversible actions — no execution, no deletion, no write of any kind (unchanged) |

Use clear Chinese task language, not unexplained internal implementation names. `screener_results`, `as_of`, `hit_factors`, and `mode` may appear as inspectable metadata but must be accompanied by a human label (`数据日期`, `关联因子`, `游客模式`). The guest banner copy must not use the literal `******` (the mask is data, not copy) — the banner states the policy in words.

---

## UI Considerations

> Populated by the ui-phase UI-consideration probe (Step 9.5) and lifted by plan-phase's
> `## UI Considerations` lift rule. Shape-rooted UI *state* coverage (empty / loading / error /
> populated / partial / overflow / zero-one-many / long-text). Empty-state and error-state COPY
> live in `## Copywriting Contract` above — this section covers state coverage and references
> those rows rather than restating the copy (de-dup).

Applicable state considerations resolved: 11 covered, 4 backstop, 0 unresolved — guest/VIP presentation layer over the Phase-18 single-`as_of` pool workspace.

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| loading | PoolHubPage (mode unknown) | ✅ covered | Hub loading is Phase-18 unchanged (`股池加载中…` + `Loader2` + `role="status"`); the guest banner does NOT render until the hub response declares `mode`, so no banner flash during load; the guest column set is applied only once `mode` is known |
| error | PoolHubPage (mode unknown) | ✅ covered | Hub error is Phase-18 unchanged (`股池加载失败：{message}。请检查数据源后重试。` `role="alert"` + `重试`); no guest-specific error state and no banner on error (mode is not known) |
| empty | PoolHubPage (guest) | ✅ covered | `当日无股池结果` empty state is Phase-18 unchanged, and the guest banner still renders when the loaded hub declares guest mode — the banner is a session-policy state, not a data state; grid area never blanks |
| populated | StockListTable (guest) | ✅ covered | Guest table renders server-masked rows verbatim: 代码 and 名称 cells show the exact `******` string from the API, 开盘涨幅 column is hidden, 涨跌幅/概念板块/关联因子 render unchanged; the presentation mode comes from the server `mode` field, never from inspecting row values |
| populated | StockListTable (vip) | ✅ covered | VIP table renders 明文 rows unchanged from Phase 18 plus the new 名称 column (real name, sans 400) and the 开盘涨幅 column; no banner |
| zero-one-many | StockListTable (guest rows) | ✅ covered | Multiple guest rows may all show the same `******` in 代码/名称 yet remain distinct rows keyed by strategy-scoped ordinal (index or server-provided stable id) — never the masked symbol — so there are no duplicate React keys; 交叉共振 count derives from `hit_factors` |
| zero-one-many | 交叉共振 (guest) | ✅ covered | 交叉共振 none/present vocabulary and badge are unchanged and visible to guests (derived from `hit_factors`, strategy labels, not PII); `今日无交叉共振 · 暂无个股被 ≥2 个竞价策略同时命中。` footnote still renders |
| partial | StockListTable (guest) | ✅ covered | Guest rows with missing 概念板块/关联因子 render `—` (muted) exactly as Phase 18; masked `******` cells never render blank or `—` — a masked identity is a present value, not a missing value |
| overflow | StockListTable (guest) | ✅ covered | Many guest rows → `共 {M} 只` footer count + `overflow-x-auto` scroll container, Phase-18 unchanged; the 5-column guest table fits the `minWidth: 720` container; the fixed 6-char `******` cell never truncates |
| long-text | GuestModeBanner | ✅ covered | Banner title and body wrap safely (`overflow-wrap:anywhere`) at all viewports and never overflow the page shell; icon/title/body keep ≥8px separation |
| security | frontend/src (masking boundary) | ✅ covered | A grep guard over `frontend/src` finds no client-side masking function, no `******` literal in production code, and no logic that derives guest mode from row values (e.g. `code === '******'`); the only `******` occurrences are in e2e test fixtures asserting server-masked output — guest presentation is driven exclusively by the server `mode` field and server-masked row values |
| partial | StrategyCardGrid (guest) | 🧪 backstop | A strategy without a persisted result for as_of renders `数据不可用` (40% opacity, no click) — Phase-18 behavior — and the guest banner does not interfere with the card grid layout; verified visually at held-out card states |
| long-text | StrategyCard (guest) | 🧪 backstop | Long strategy names truncate with ellipsis (`truncate`) as Phase 18; in guest mode the card name line still never wraps the card or pushes the count off-layout with the banner present |
| populated | StockListTable (many masked rows) | 🧪 backstop | When a large guest pool shows many rows with identical `******` identities, rows remain visually distinct via 涨跌幅/概念板块/关联因子 and the 交叉共振 highlight; no row collapse, merge, or perceived duplication — held-out/visual UI-state check at high row volume |
| overflow | StockListTable (column-set shift) | 🧪 backstop | Switching guest → VIP (or the reverse) toggles the 开盘涨幅 column without a layout jump or page reflow; the table reflows cleanly within the scroll container — held-out/visual check of the mode transition |

**Covered truths vs backstop scalars.** Every `✅ covered` row is a plain truth string (e.g. "Guest table renders server-masked rows verbatim: 代码 and 名称 cells show the exact `******` string from the API, 开盘涨幅 column is hidden, 涨跌幅/概念板块/关联因子 render unchanged; the presentation mode comes from the server `mode` field, never from inspecting row values") that lifts into `must_haves.truths` and is verification-derivable from a wired UI test (e2e guest-session fixture, grep guard) or code inspection. Every `🧪 backstop` row is a flat scalar `{ statement, verification: backstop }` — a human-judgment item confirmed at verify time only by explicit evidence (held-out/visual UI-state test); without evidence it routes to `insufficient_spec → human_needed`, never a silent pass (#1154). No row is left `⚠ unresolved`; the planner is not required to carry a Phase-19 UI assumption forward.

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
| shadcn official | None | Not applicable — `components.json` absent when scanned on 2026-08-04 (re-verified this session); shadcn initialization is explicitly excluded for this phase. |
| Third-party registry | None | No third-party blocks declared or permitted; no registry vetting needed. |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: exact Simplified Chinese strings for the guest banner (`游客模式：股票代码与名称已脱敏` + body `仅展示涨跌幅与概念板块。`), guest/VIP column-header sets, masked cell `******`, and all retained Phase-18 states; research-only disclaimer unchanged; no execution vocabulary anywhere; the guest banner uses words, never the `******` literal, to state the policy
- [x] Dimension 2 Visuals: existing dark-first page shell and Phase-18 component tree (PageHeader → GuestModeBanner → ConceptFilter → StrategyCardGrid → StockListTable → research footer); no new shell or design language; guest banner is one neutral element inserted into the existing `space-y-3` shell; component tree matches the Phase-19 presentation layer with no client masking component
- [x] Dimension 3 Color: established 60/30/10 tokens; accent reserved for 交叉共振 highlight + active card + focus (unchanged); guest banner uses neutral `elevated`/`border`/`secondary`; masked cell uses `muted` only; warning stays `数据不可用`-only; bull/bear market-direction-only with sign redundancy; 4.5:1 contrast + text/icon redundancy
- [x] Dimension 4 Typography: four-size/two-weight scale (12/14/16/20, 400/600); mono + `tabular-nums` for codes/counts/percentages and the `******` cell; safe-wrap status copy incl. guest banner; 65ch prose cap; no new type roles
- [x] Dimension 5 Spacing: 4px-based scale (4/8/16/24/32/48/64); banner uses `px-3 py-2` (md); 44×44px touch-target exceptions below 768px retained; ≥8px touch-target gaps; table scroll without masked-cell truncation
- [x] Dimension 6 Registry Safety: no shadcn initialization and no third-party registry; timestamped absence evidence recorded (scanned 2026-08-04, re-verified this session)

**Approval:** approved (2026-08-04)
