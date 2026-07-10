---
phase: 1
slug: core-merger
status: draft
shadcn_initialized: false
preset: none
created: 2026-07-11
---

# Phase 1 — UI Design Contract

> Visual and interaction contract for the operational Portfolio and Monitor workflow. Generated from `01-CONTEXT.md`, `01-RESEARCH.md`, `01-VALIDATION.md`, and the existing TickFlow frontend.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none; extend the existing manual Tailwind design system |
| Preset | not applicable; no `components.json` exists |
| Component library | existing shared React primitives: `Modal`, `PageHeader`, `EmptyState`, `Skeleton`, toast containers, and `cn` |
| Icon library | `lucide-react`; use a Lucide icon for every icon-only control and provide a visible `title` plus an `aria-label` |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, `system-ui`; use `JetBrains Mono`, `IBM Plex Mono`, or `ui-monospace` for symbols, prices, quantities, dates, and all financial figures |

**Source and scope.** This phase extends the dark-default, token-driven TickFlow workspace defined in `frontend/src/index.css` and `frontend/tailwind.config.ts`. Do not introduce shadcn, Radix, a third-party registry, a second component system, a second mobile shell, a PWA layer, or a visual redesign of the application shell.

**Existing primitive requirements.** Use `PageHeader` for Portfolio and Monitor page headings. Use the shared `Modal` for all account, holding, rule, delivery-detail, and destructive-confirmation dialogs so focus trapping, Escape, backdrop behavior, and focus restoration are consistent. Do not create another unguarded custom overlay. Reuse `EmptyState`, `Skeleton`, `ToastContainer`, and `AlertToastContainer` rather than adding parallel notification components.

**Surface rules.** The workspace remains a quiet operational terminal: 1px token borders establish hierarchy; decorative gradients, image heroes, oversized metric cards, and floating-card page sections are prohibited. A summary band is a single bordered surface with dividers, not a collection of nested cards. Repeated holdings, rules, and history entries may be bordered rows or cards at the responsive breakpoints below.

---

## Spacing Scale

Declared values (all are multiples of 4):

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Icon/text gaps, inline badge padding, table-cell internal separation |
| sm | 8px | Compact control gaps, row metadata gaps, mobile card sections |
| md | 16px | Default page content padding on mobile, dialog field groups, compact section padding |
| lg | 24px | Desktop page content padding, summary-band padding, section separation |
| xl | 32px | Major desktop layout gaps and dialog body padding where needed |
| 2xl | 48px | Empty-state vertical breathing room |
| 3xl | 64px | Reserved for page-level separation only; do not use inside dense operational views |

**Density and dimensions.** Use 32px desktop input/button height, 40px desktop primary-action height, 40px minimum data-row height, and 44px minimum touch targets on screens under 768px. Table cells use 8px horizontal and 8px vertical padding; page header uses the existing 20px desktop horizontal padding and 16px mobile padding. Cards use the existing 8px radius; buttons use 6px; inputs use 4px. Keep 1px borders and avoid large shadows; only dialogs and transient alert toasts may use existing elevated shadows.

**Exceptions.** 44px mobile targets and 40px primary-action height are intentional usability exceptions to the compact control height, not new spacing tokens. A maximum-width content rail is permitted only where the current page already centers content; Portfolio must otherwise use the available workspace width.

---

## Typography

Use exactly these four sizes and two weights for new Phase 1 UI. Existing legacy 9–11px labels may remain untouched outside this phase; do not add them to Portfolio, new rule fields, or new alert-delivery UI.

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Metadata / compact table label | 12px | 400 | 1.33 |
| Body / table value / form control | 14px | 400 | 1.5 |
| Section heading / dialog title | 16px | 600 | 1.2 |
| Page heading / key valuation total | 20px | 600 | 1.2 |

Use only `400` and `600`. Symbols, prices, quantities, timestamps, percentages, account balances, and P&L figures use tabular monospaced numerals via the existing `.num` or `.tabular` treatment. Never use color as the sole P&L indicator: retain `+`/`-` signs and show an em dash (`—`) for unavailable values. Do not use negative letter spacing; do not scale text with viewport width.

---

## Color

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | dark `#0A0A0B` / light `#FAFAFA` (`base`) | Page background and main application canvas |
| Secondary (30%) | dark `#18181B` / light `#FFFFFF` (`surface`) | Sidebar, dialogs, bordered rows, summary band, table header, and compact cards |
| Accent (10%) | `#3B82F6` (`accent`) | Primary submit button, active navigation/filter/tab, keyboard focus ring, real-time connected indicator, selected controls, and links to a relevant in-app action |
| Destructive | `#F04438` (`danger`) | Archive/delete confirmations, destructive button text/background, irreversible-action icon states, and delivery failure only |

**Supporting semantic tokens.** Preserve the established A-share convention: `bull #F04438` means a market price increase and `bear #12B76A` means a market price decrease. These values represent market direction, not generic success/failure. Use `warning #F79009` for stale data, quiet-period skips, pending action, and reconnecting; use a green delivery-success treatment only for a completed successful delivery outcome. The existing `danger` and `bull` happen to share a red value, so every use must include its text/icon label and context.

Accent reserved for: `添加持仓` and other primary form submission buttons; active Portfolio/Monitor navigation; selected account/filter chips; the SSE-connected dot; focus rings; and direct internal-action links such as `查看详情` or `前往设置`. Do not color all buttons, all positive values, passive badges, chart elements, or entire Portfolio rows blue. Keep the existing dark theme as default and preserve the current light theme token inversion.

---

## Information Architecture And Layout

### Portfolio Is A First-Class Workspace

Add a `Portfolio` item with a `WalletCards` Lucide icon to the existing application navigation and route it to `/portfolio`. Do not place portfolio management under Settings, Watchlist, Trading, or a second alert product. The page header is `投资组合`; its right-side controls are `新建账户` (secondary) and `添加持仓` (accent primary). The main primary CTA for this phase is **`添加持仓`**.

Order the Portfolio content exactly as follows:

1. A single aggregate summary band before all holdings.
2. Account filter/control row.
3. Holdings list in the breakpoint-specific form below.

The aggregate summary band has four evenly aligned metric cells: `总资产`, `可用资金`, `持仓市值`, and `未实现盈亏`. `总资产` is visually strongest at 20px/600; all other metric values are 16px/600. Each cell includes a 12px source/as-of line. The band includes an explicit freshness chip at its right edge, never a bare “latest” claim. Account selection changes the displayed summary and holdings; `全部账户` is the initial selection and shows the aggregate. Archived accounts are hidden by default behind a `显示已归档` toggle.

The account control row contains an account selector/filter, an optional count, `管理账户`, and a freshness legend. Do not turn each account total into a decorative dashboard card. Account management opens the account dialog; it does not navigate to a standalone edit route.

### Holdings Presentation

At **1280px and above**, use a dense, sticky-header semantic table with these columns in this order: `标的`, `账户`, `风格`, `数量`, `成本价`, `最新价`, `市值`, `未实现盈亏`, `监控`, `更新`, `操作`. The `标的` cell combines symbol, name, and market board badge. The `监控` cell reports rule state as text plus an icon, for example `2 条启用`; it opens Monitor filtered to that holding. The `操作` cell contains labeled-on-hover Lucide icon buttons for edit, archive, and create/view monitoring rule.

At **768px to 1279px**, keep a compact table with `标的`, `数量`, `最新价`, `市值`, `未实现盈亏`, `监控`, and `操作`. Place account, style, cost price, and freshness on the instrument/value secondary line within the row. Do not introduce a horizontal scrollbar or clip table data.

At **0px to 767px**, replace the table with compact holding cards, one per holding, in a single vertical column. Each card has: symbol/name and account on the top line; current price plus freshness on the second; three aligned value cells for cost, market value, and P&L; then trading style, active rule count, and icon actions. Cards must show price, P&L, alert state, and edit/action access without horizontal overflow. Do not provide a manual card/table switcher: the breakpoint selects the mode.

Prices and P&L update in place without reordering holdings, shifting column widths, or scrolling the user. Default sort is account then symbol; provide a visible sortable column header only when backend-supported sorting is available. Never show a missing quote as zero or mark a fallback close as live.

### Monitor Remains The Single Alert Center

Keep rule management and alert history at `/monitor`. Add `持仓监控` to the rule-type/filter vocabulary and `持仓` to the scope vocabulary; do not create a Portfolio alert page, a second scheduler UI, or an alternate history feed.

On desktop, preserve the current two-panel Monitor composition: alert history is the flexible primary panel and rules are the fixed right panel. Add type filters `全部`, `持仓`, `价格`, `信号`, `市场`, and `策略`; add severity and delivery-state filters only when they are backed by the persisted response. At 767px and below, stack history before rules, with each section maintaining its own header and scrollable content. The page must remain usable at 320px width with no horizontal page overflow.

Each persisted alert-history row/card must display: severity icon and labeled severity; source/type badge; account and holding when applicable; symbol/name; matched condition summary; valuation price and its source/as-of; event timestamp; and a compact delivery summary. The delivery summary is a clickable status chip such as `2/2 已发送`, `1 失败`, `待投递`, or `已跳过`. Opening it uses a dialog that lists one row per configured channel with channel name, outcome, timestamp, and a sanitized failure reason. Never display webhook URLs, tokens, chat IDs, raw response payloads, or credentials.

Use these status labels and visual treatments:

| State | Label | Treatment | Meaning |
|-------|-------|-----------|---------|
| `pending` | 待投递 | muted text + clock icon | Event persisted and SSE-visible; delivery work has not completed |
| `sent` | 已发送 | green text + check icon | Channel accepted the outbound delivery attempt |
| `failed` | 投递失败 | danger text + triangle icon | Event remains valid; only the external delivery failed |
| `skipped` | 已跳过 | warning text + moon/clock icon | Quiet-period or active-time policy skipped delivery; history remains retained |

Do not send a second intrusive toast when a pending delivery becomes sent, skipped, or failed. Refresh the status chip/detail in place. A rule hit always becomes a persisted Monitor history item before any delivery status changes.

### Decision Playbook Inspection

Expose the Phase 1 decision playbook from the existing Dashboard through a `查看决策计划` action that opens a read-only inspector dialog or dedicated in-page panel; it is not a competing quote view and does not create a separate AI product. The inspector shows `数据截至`, engine/config version, deterministic baseline, final plan, and a field-by-field adjustment audit in this order: entry range, stop, target 1, target 2, position size, action/reason. The deterministic baseline is the left/first comparison column and is visually labeled `确定性基线`; final values are labeled `最终计划`; each allowed AI change shows `已应用`, `已钳制`, or `已拒绝` with the recorded rationale. Action, score, and risk/reward are displayed as deterministic facts and cannot appear as AI-overridden fields.

The inspector includes `历史回放` only for a selected historical `数据截至` value. During replay it displays `正在以历史数据回放；AI 已禁用`; on completion it shows the stored replay timestamp and result hash. It must never imply that live AI is running during replay. An unavailable AI provider leaves the deterministic baseline visible with the label `未应用 AI 调整`, not an error-looking empty plan.

---

## Freshness, Real-Time, And State Contract

### Valuation Freshness

Every valuation-bearing Portfolio surface must render API-provided `source` and `as_of` metadata next to, or directly under, its price/P&L. Use exactly these presentation states:

| API state | User-facing label | Treatment |
|-----------|-------------------|-----------|
| Fresh shared quote | `实时 · HH:mm:ss` | Accent dot and neutral text; use only when the quote service marks the snapshot fresh |
| Market closed / governed fallback | `收盘 · YYYY-MM-DD` | Muted text with calendar icon; never animate it as live |
| Quote known but stale | `报价可能已过期 · HH:mm:ss` | Warning icon and warning text; retain the valuation but do not call it real-time |
| No quote or close | `暂无法估值` | Muted text, em dash for numeric values, and no calculated P&L |

The Portfolio summary freshness chip uses the least-fresh visible holding valuation. Clicking the chip opens a concise explanatory tooltip, not another quote screen. The tooltip states whether prices derive from the shared real-time quote or the latest governed close. P&L calculations and historical alert snapshots must identify the same source/as-of value used for the displayed price.

### Shared SSE Behavior

The existing root `useQuoteStream` connection to `/api/intraday/stream` is the only client streaming connection for this phase. Add `portfolio_updated` handling to invalidate Portfolio account, holding, and summary queries. Extend the existing `quotes_updated` invalidation list to include Portfolio valuation queries. Do not open an EventSource in Portfolio, Monitor, dialogs, or mobile-specific code.

On `portfolio_updated`, refetch affected data while preserving the current row order, account filter, scroll position, and any open non-stale dialog. On `strategy_alert`, including a position-scoped alert, retain the existing alert-toast behavior, invalidate alert history/total, and append or highlight the persisted Monitor row. The single alert toast must contain source, symbol/name where available, severity, and a concise condition summary; click/Enter/Space routes to `/monitor` as it does today.

When the shared stream is reconnecting, preserve the existing global `与服务连接已断开 · 正在重连` status treatment and add no per-page duplicate banners. Portfolio keeps the last known values, labels them with their existing as-of time, and does not show a false loading state. Respect `prefers-reduced-motion`: no pulsing ring or entrance movement is required for new/revalued rows; a static accent border and updated timestamp are sufficient.

### Loading, Empty, And Error States

| Surface | Loading | Empty | Error |
|---------|---------|-------|-------|
| Portfolio summary and holdings | Summary-cell skeletons plus 8 fixed-height row/card skeletons; retain prior data during background refresh | `还没有持仓` — `先新建账户，再添加第一笔持仓。` with `添加持仓` action | `无法读取投资组合。请检查服务连接后重试。` with `重试` action |
| Account filter | Disabled selector with a 32px skeleton | `还没有账户` — `新建账户后即可记录持仓与可用资金。` | Inline compact error; do not erase existing holdings |
| Monitor rules | Existing compact rule skeletons | `暂无监控规则` — `新建规则后，可在持仓、价格或市场条件满足时记录提醒。` with `新建规则` action | `无法加载监控规则。请检查服务连接后重试。` |
| Alert history | Existing compact event skeletons | `暂无触发记录` — `规则命中后，记录和投递结果会显示在这里。` | `无法加载触发记录。请检查服务连接后重试。` |
| Delivery detail | Two compact status-row skeletons | `此规则未配置外部通知渠道。` | `无法读取投递结果。请稍后重试。` |
| Playbook inspector | Field-row skeletons; preserve any prior snapshot until new data resolves | `尚无可用决策计划` — `完成数据同步后生成确定性计划。` | `无法读取决策计划。请检查数据状态后重试。` |

Use `Skeleton`, never a blank panel or full-page spinner, for local loading. Mutations disable only the submitted form and show progress in the submit button; do not lock unrelated navigation. After a successful account/holding/rule mutation, close the dialog, invalidate the affected queries, preserve the user’s current filter, and show a concise success toast.

---

## Component And Interaction Contract

### Account And Holding Dialogs

All creation and edit flows use page-level `Modal` dialogs. `新建账户` and `编辑账户` use a 560px maximum-width desktop dialog; `添加持仓` and `编辑持仓` use a 680px maximum-width desktop dialog. On mobile, dialogs use `width: calc(100vw - 32px)`, `max-height: 90vh`, a scrollable body, and a sticky action row. Do not navigate to an edit route.

Account fields, in visual order: `账户名称`, `可用资金`, optional `备注`, then active/archive state when editing. Holding fields: `账户`, `标的搜索`, `成本价`, `数量`, `投入金额`, `交易风格` (`短线`, `波段`, `长线`), optional `备注`. The instrument search uses the established accessible combobox behavior: input focus opens results, Arrow Up/Down changes the active result, Enter selects, Escape closes, and selected value remains visible. Require account, instrument, positive quantity, and non-negative cost/amount before submit. Show field-level validation directly below the relevant control and move focus to the first invalid field after submit.

Dialog footer buttons are `取消` (secondary) and `保存账户` / `保存持仓` (accent primary). Editing never overwrites real-time valuation fields; those remain calculated display-only values in the list. When a selected instrument already exists in the selected account, block submission with `该账户已持有此标的。请编辑现有持仓。`.

Accounts or holdings referenced by history or rules show `归档` rather than delete. The archive confirmation copy is `归档后将不再计入默认汇总；持仓、规则和告警历史会保留。` Empty, unreferenced records may expose `删除`; its confirmation names the record and states `删除后无法恢复。`. Archive/delete controls use `Archive`/`Trash2` icons and explicit accessible labels. Do not offer bulk deletion.

### Rule Editor

Extend the existing Monitor `RuleEditor` in the shared modal presentation. The full form is a single vertical sequence with these sections: `基本信息`, `监控范围`, `触发条件`, `通知与时间`, `确认`. A position rule presents `持仓` as its type and an explicit multi-select list of the user’s holdings; its selection label includes symbol, name, and account. A generic price or market rule remains evaluated independently of holdings and must not silently expand to one alert per owned account.

`通知与时间` contains severity, cooldown, active-time range, quiet-period behavior, and delivery channels. Use checkboxes for Feishu and Telegram. A selected but unconfigured channel stays selectable but shows `未配置` plus a direct internal `前往设置` action. The high-severity quiet-period bypass is a switch labeled `高优先级可绕过静默时段`; show a 12px helper line: `规则命中始终会保存；静默时段只影响外部投递。` Do not expose unsupported channels as selectable controls.

The rule form primary action is `保存规则`; a disabled submitting action reads `正在保存…`. Invalid condition, empty holding selection, or impossible active-time input produces adjacent field errors and a concise top form summary. Closing a dialog with unsaved changes opens `放弃未保存的更改？` with `继续编辑` and `放弃更改`.

### Alert History And Delivery Detail

Alert-history rows use the existing left severity rail and stable 8px card radius. New SSE-arrived events receive one short entrance treatment on non-reduced-motion devices and a static accent outline otherwise. Retain every matched event in the list even when delivery is skipped or fails. Event detail remains readable with a maximum of two lines before a `查看详情` expansion; do not truncate the account/holding relation or delivery status.

Delivery details open a modal titled `投递结果`. Each channel row has a named status icon, channel, time, outcome, and sanitized error text if failed. Failed text must never reveal a token, webhook URL, full request body, or raw remote response. Delivery failure must not change the event’s severity, remove it from history, or visually imply that rule evaluation failed.

### Responsive Shell

At 768px and above, retain the existing 14rem sidebar shell. Below 768px, replace the permanently visible sidebar with a menu button that opens the same navigation in an off-canvas dialog/drawer. The drawer uses the current surface/border tokens, traps focus, closes on Escape/backdrop activation, and returns focus to the menu button. It is navigation for the same web application, not a mobile-specific product. Page header actions wrap to a second line instead of overflowing; text labels remain visible for primary actions.

At all widths, use `min-width: 0`, truncation with a title/accessible name where necessary, and wrapping for labels. Financial values never wrap mid-number. Avoid horizontal scrolling on Portfolio, Monitor, forms, and dialogs; only a purpose-built existing data grid with an explicitly disclosed scroll area may scroll horizontally, and Phase 1 Portfolio must not require it.

---

## Accessibility And Motion Contract

- Use semantic `table`, `thead`, `th scope="col"`, and row headers for desktop holdings. Mobile holding cards must expose the same values with visible labels; do not hide a required value solely because the table has changed shape.
- Every form input has a persistent visible label. Placeholder text is supplementary, never the only label. Required fields include programmatic required state; validation messages are associated with the input through `aria-describedby`.
- All interactive controls are keyboard reachable. Icon-only buttons have `aria-label` and `title`. Selected filter chips expose `aria-pressed`; rule/channel switches expose checked state; disabled controls state why through visible helper copy or tooltip.
- Focus uses a visible 2px accent ring with sufficient contrast. Preserve the shared Modal focus trap, Escape close, and focus restoration. Destructive confirmations receive initial focus on `取消`, never on the destructive action.
- Announce user-initiated mutation success and noncritical query errors through the existing polite live region. Alert toasts and SSE reconnect notices remain polite. Do not announce each tick-level valuation update; refresh visual values silently.
- Color is always paired with text, icon, sign, or state label. Respect `prefers-reduced-motion`; reduce row/alert/dialog transitions to opacity-only or none, and never make an essential state depend on pulse animation.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA | `添加持仓` |
| Portfolio empty state heading | `还没有持仓` |
| Portfolio empty state body | `先新建账户，再添加第一笔持仓。` |
| Rule empty state heading | `暂无监控规则` |
| Rule empty state body | `新建规则后，可在持仓、价格或市场条件满足时记录提醒。` |
| Alert-history empty state heading | `暂无触发记录` |
| Alert-history empty state body | `规则命中后，记录和投递结果会显示在这里。` |
| Generic error state | `无法加载数据。请检查服务连接后重试。` |
| Missing valuation | `暂无法估值` |
| Fresh quote label | `实时 · HH:mm:ss` |
| Fallback-close label | `收盘 · YYYY-MM-DD` |
| Stale quote label | `报价可能已过期 · HH:mm:ss` |
| Rule hit delivery failure | `告警已记录，但外部通知投递失败。查看投递详情或检查通知设置。` |
| Archive confirmation | `归档后将不再计入默认汇总；持仓、规则和告警历史会保留。` |
| Delete confirmation | `删除后无法恢复。` |
| Unsaved form confirmation | `放弃未保存的更改？` |
| Replay in progress | `正在以历史数据回放；AI 已禁用` |

Use direct Chinese operational verbs: `新建`, `添加`, `保存`, `编辑`, `归档`, `删除`, `查看详情`, `重试`, and `前往设置`. Avoid marketing claims, reassurance language, unexplained acronyms, vague “latest” labels, and copied raw backend errors.

---

## Explicit Anti-Patterns

- Do not add a PanWatch UI, a second portfolio/quote polling view, a second EventSource, a mobile-only application shell, PWA prompts, or offline interaction semantics.
- Do not show a price as live without the source/as-of freshness contract, use zero for missing valuation, or calculate/label P&L when valuation is unavailable.
- Do not make delivery success/failure block, replace, or erase the stored rule hit. Do not toast delivery completion separately from the persisted hit.
- Do not use red/green without the accompanying price sign or delivery/status label. Do not use blue as a generic decorative color.
- Do not use decorative metric-card grids, oversize display typography, rounded pill-only primary buttons, gradients, glass panels, or nested cards in Portfolio and Monitor.
- Do not put account/holding/rule editing on a separate page or allow a history-associated account/holding to be deleted instead of archived.
- Do not expose webhook configuration values, credential material, raw channel errors, or unsupported delivery channels in the user interface.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none; shadcn is not initialized | not applicable — existing manual design system retained — 2026-07-11 |
| Third-party registries | none | not applicable — no third-party block declared — 2026-07-11 |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
