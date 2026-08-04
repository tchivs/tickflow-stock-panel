---
phase: 16
status: approved
shadcn_initialized: false
preset: none
created: 2026-08-04
---

# Phase 16 — UI Design Contract

> Visual and interaction contract for the existing `/data` settings page. This contract covers only the Phase-16 data-layer surfaces: minute-K sync enable/disable plus coverage, and the auction-data probe verdict — without introducing a new shell, route, workspace, or pool surface.

---

## Scope and Source Decisions

| Source | Binding UI decision |
|---|---|
| `ROADMAP.md` Phase 16 成功标准 | Enable minute-K sync with a visible enable/disable control and 1m-bar coverage; expose the auction-data probe verdict honestly (available / fail-closed to derived open-gap factors); never label the 09:30 continuous-trading bar as 集合竞价 data. |
| `REQUIREMENTS.md` DATA-01 | The Data page's 分钟 K surface gains an enable/disable control and a coverage display backed by `kline_minute` partition state; existing daily-K surfaces are untouched. |
| `REQUIREMENTS.md` DATA-02 | 开盘涨幅 (`open / prev_close − 1`) is a governed factor consumed by strategy filters — no dedicated Phase-16 UI surface; strategy result columns land in Phase 17/18. |
| `REQUIREMENTS.md` DATA-03 | A data-source status/verdict surface reports the probe result with the exact fail-closed vocabulary; when the source is unavailable the surface must never label the 09:30 bar as 集合竞价 data. |
| `.planning/research/v1.3-auction/SUMMARY.md` | Minute bars today start at 09:30 continuous trading; true 9:15–9:25 match data (竞价量/金额/虚拟成交) is a probe-gated capability. All copy must distinguish derived 开盘涨幅 from true 集合竞价 match data. |
| `frontend/src/pages/Data.tsx` | The Data page keeps its existing layout and shell. Minute-K sync slots into the existing 分钟 K `StatCard` + `SettingsModal`/`MinuteSyncConfig` pattern; the probe verdict slots into an existing `SectionTitle` panel pattern — never a new shell or route. |
| `.impeccable/design.json` + `frontend/src/index.css` | Binding dark-first tokens (`base`/`surface`/`elevated`/`border`/`foreground`/`secondary`/`muted`/`accent`/`bull`/`bear`/`warning`/`danger`), 4px spacing scale, four-size/two-weight type scale, mono for data/identifiers. |
| `02-UI-SPEC.md` (v1.0 convention) | Match the existing UI-SPEC structure, scope-boundary discipline, and Simplified Chinese copy style. |

### Phase boundary

- **In scope:** minute-K sync enable/disable toggle plus coverage display on the 分钟 K surface; an auction-data probe status/verdict surface with honest fail-closed labels.
- **Out of scope:** the pool hub, strategy cards, drill-down stock lists, concept filter, and 交叉共振 highlight (Phase 18); guest/VIP masking and the frontend pool page (Phase 19); 日期导航 (POOL-04, v2); strategy-authoring UI (Phase 17); true 集合竞价 match data as first-class table columns (DATA-04, v2).

---

## Design System

| Property | Value |
|---|---|
| Tool | Manual existing system: Tailwind CSS 3.4 tokens and local React components |
| Preset | Not applicable — `components.json` is absent as of 2026-08-04; do not initialize shadcn for this data-layer phase |
| Component library | Existing local components (`StatCard`, `SectionTitle`, `SettingsModal`, `MinuteSyncConfig`, `QuoteConfigCard`) and native semantic controls; no new UI component registry |
| Icon library | `lucide-react`; 14–16px outline icons beside, never instead of, visible labels |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, system sans; `JetBrains Mono`/`IBM Plex Mono` only for data, identifiers, timestamps, and coverage counts |
| Server state | Existing typed `api.ts` methods plus TanStack Query `QK` factories; no direct `fetch`, duplicate request helper, or client-side synthesis of probe verdicts |

### Existing visual tokens to preserve

Use the CSS variables in `frontend/src/index.css` and Tailwind semantic names (`base`, `surface`, `elevated`, `border`, `foreground`, `secondary`, `muted`, `accent`, `bull`, `bear`, `warning`, `danger`). Dark mode remains the default; light mode is the existing token inversion. Use 1px `border-border` separation and existing radii: `rounded-input` 4px, `rounded-btn` 6px, `rounded-card` 8px, `rounded-dialog` 12px. Do not introduce gradients, glass surfaces, oversized rounded cards, decorative shadows, or a Phase-16-specific palette.

---

## Information Hierarchy and Workflow

### Page hierarchy

1. **Page header — 数据:** retain the existing compact title, data-source switcher, and account hint. No new header content.
2. **Existing operational panels:** active job card, quote config, and schedule editors remain exactly as shipped. Phase 16 does not reorder them.
3. **数据画像 (`SectionTitle icon={Database}`):** the 分钟 K `StatCard` carries the minute-K sync coverage display in its hint/status area. The card's `同步设置` modal (`SettingsModal` titled `分钟 K · 同步设置`, containing `MinuteSyncConfig`) keeps the enable toggle, 同步天数 stepper, and 向前扩展历史数据 controls.
4. **竞价数据 panel (`SectionTitle` + card pattern):** a new status panel on the existing Data page renders the auction-data probe verdict. It sits inside the existing panel pattern — same `SectionTitle`, card, and spacing conventions — never a new workspace or route.

### Required status vocabulary

| State | Visible label and treatment | Allowed actions |
|---|---|---|
| Minute-K sync disabled | `分钟K未启用` in muted text on the 分钟 K card; no coverage count shown | Enable via the existing toggle in 同步设置 |
| Minute-K sync enabled | `分钟K同步中·覆盖{N}天` in secondary text with the `{N}` count always mono/tabular | Adjust 同步天数 (1–15) or 向前扩展历史数据 in 同步设置 |
| Probe not configured | `竞价数据未配置` in muted text with a short hint | No probe run; hint points to data-source configuration |
| Probe running | `竞价数据探测中…` with `Loader2` spinner and `role="status"` | No concurrent re-run; `重新探测` disabled |
| Auction data available | `竞价数据可用` in accent treatment with a check icon | `重新探测` (secondary); never claim more than the verified capability |
| Probe fail-closed | `未接入竞价数据（已退化派生因子）` in warning treatment with `AlertTriangle` icon | `重新探测`; derived open-gap factors remain the baseline; never label the 09:30 bar as 集合竞价 data |
| Probe failed (error) | `竞价数据探测失败：{message}。已按未接入处理，当前使用派生开盘涨幅因子。` in `role="alert"` | Retry `重新探测`; status never downgrades to `竞价数据可用` |

---

## Interaction States and Feedback

| Control class | Default / hover / focus | Disabled / loading / error |
|---|---|---|
| Minute-K sync toggle | Existing switch in `MinuteSyncConfig`: off = `bg-elevated`, on = `bg-accent`; hover cursor-pointer; keyboard focus 2px accent ring with 2px offset | Disabled at 40% opacity when the provider lacks `kline.minute.batch` (`需 Pro+` chip); during the update mutation the label shows pending feedback; no partial commit |
| 同步天数 stepper | Native buttons with visible mono value; hover `bg-border/50`; focus ring | Disabled when toggle is off or at bounds (1–15); stepper-only, no direct text entry |
| Coverage display | Static secondary/muted text on the 分钟 K card; `{N}` always mono/tabular | While a sync job runs, the existing `StatCard` active/progress treatment applies; never show a stale count as fresh |
| `重新探测` (probe action) | Secondary elevated treatment beside the verdict; hover `bg-elevated`; focus ring | Disabled while probe running (`竞价数据探测中…`); failure shows inline `role="alert"` below the verdict |
| Probe verdict row | Text + icon always paired; `role="status"` when running, `role="alert"` on failure | Loading reserves row height (spinner in place); verdicts never blank the panel |

Use 150–200ms `ease-smooth` opacity/color transitions only for state feedback. Do not animate initial page entry or layout height. Under `prefers-reduced-motion: reduce`, all state transitions are instant and loading remains text/spinner based.

---

## Data Display

- The only numeric displays in Phase 16 are the coverage count `覆盖{N}天` and the probe verdict state — both rendered as text with `role="status"`/`role="alert"` where required. Numerals use the mono family with `tabular-nums`.
- Status is communicated by the literal state words above, not by a weight, color, or icon alone. Every verdict pairs visible text with a Lucide icon (`aria-hidden` when it duplicates the label).
- No charts, tables, or pool lists exist in Phase 16 — those surfaces land in Phase 17/18.

---

## Spacing Scale

Declared values (all multiples of 4):

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | Icon-label gap, compact badge padding (`需 Pro+`) |
| sm | 8px | Form-label to control gap, compact control group gap |
| md | 16px | Default component gap, panel inner padding on narrow screens |
| lg | 24px | Related-panel separation and desktop panel padding |
| xl | 32px | Section separation within the Data page |
| 2xl | 48px | Major workflow boundary only |
| 3xl | 64px | Page-level separation only; do not add empty decorative space inside data tools |

**Exceptions:** Existing dense desktop controls use compact 8px paddings for scanability. At viewport widths below 768px, the sync toggle, 同步天数 steppers, and `重新探测` action must have a 44×44px hit area even when the visible glyph/control remains compact. Keep at least 8px between adjacent touch targets.

---

## Typography

Use one existing sans family for all UI labels, headings, buttons, and body copy. Phase-16 additions use exactly these four sizes and two weights; code/data may use the existing mono family at the same declared size.

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Metadata / labels | 12px | 400 | 1.5 |
| Body / panel content | 14px | 400 | 1.5 |
| Section heading | 16px | 600 | 1.2 |
| Page heading | 20px | 600 | 1.2 |

- Use `font-weight: 600` only for page headings, section headings, status names, and primary actions. All other content uses 400.
- Keep prose explanations at a maximum of 65ch. Status copy may use available panel width but must wrap safely (`overflow-wrap:anywhere`) instead of overflowing.

---

## Color

The established restrained dark-first system is binding. The 60/30/10 split describes surface allocation, not a reason to tint all controls.

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `base`: dark `#0A0A0B`; light `#FAFAFA` | Application and Data page background |
| Secondary (30%) | `surface`: dark `#18181B`; light `#FFFFFF`; `elevated`: dark `#212126`; light `#F4F4F5` | Workspace panels, cards, toolbar backgrounds, toggle off-state |
| Accent (10%) | `accent` `#3B82F6` | Minute-K toggle on-state, active `StatCard`/progress, `重新探测` action, focus rings, `竞价数据可用` identity, and neutral information identity only |
| Warning | `warning` `#F79009` | Fail-closed/degraded states: `未接入竞价数据（已退化派生因子）`, `需 Pro+` capability chip |
| Destructive | `danger` `#F04438` | Probe failure diagnostics and truly destructive controls only |
| Market direction | `bull` `#F04438` for A-share positive/red; `bear` `#12B76A` for A-share negative/green | 涨跌幅/开盘涨幅 direction only; never generic success/error state |

Accent is reserved for: primary controls, active states, focus rings, and neutral information identity. It is **not** a decoration color, a generic card border, or the visual status of every clickable element.

`bear` green `#12B76A` is market-direction-only — do **not** reuse it as a generic "available" success color. `竞价数据可用` uses accent + check icon, consistent with the accent reservation.

All normal text and interaction labels must meet 4.5:1 contrast against their occupied surface; large/bold text and focus indicators must meet at least 3:1. Provide text/icon redundancy for every status and market-direction state.

---

## Responsive Behavior

| Viewport | Required layout behavior |
|---|---|
| `≥1280px` | Retain the existing Data-page grid and panel widths unchanged; the 竞价数据 panel follows the existing `StatCard`/panel widths |
| `768–1279px` | Panels stack per the existing `md:grid-cols-3` → single-column behavior; the probe verdict row wraps |
| `<768px` | One-column flow: header wraps title/subtitle before controls; toggle, 同步天数 steppers, and `重新探测` meet 44px targets; verdict copy wraps safely (`overflow-wrap:anywhere`) |

Do not use fluid heading sizes. Preserve the existing Data-page layout conventions and panel spacing; no new shell or route is introduced at any viewport.

---

## Accessibility Contract

- Use semantic `main`, `section`, `aside`, headings in order, native `button`, native `input`, native `checkbox`, and native `details` before custom equivalents. Every form field has a visible programmatic `<label>`.
- The minute-K toggle is a real button with `role="switch"` and `aria-checked`, or a native checkbox with a visible label — never a div styled as a switch.
- Associate help/error text with controls through `aria-describedby`; probe running uses `role="status"` or a polite live region, and probe failure uses `role="alert"`.
- Use a visible 2px accent focus ring with 2px offset on every keyboard-reachable control. Never remove focus outlines without providing that replacement. Keyboard order follows visual order.
- Provide non-color labels for all status and market-direction states. All Lucide icons that duplicate label text are `aria-hidden`; an icon-only action has an explicit `aria-label` and tooltip.
- Respect `prefers-reduced-motion`; do not make state updates dependent on animation. Maintain readable contrast in both current light and dark themes.

---

## Copywriting Contract

| Element | Copy |
|---|---|
| Minute-K primary CTA | `启用分钟K同步` (toggle on) / `自动同步` (existing on-state label) |
| Minute-K disabled | `分钟K未启用` |
| Coverage display | `分钟K同步中·覆盖{N}天` |
| 同步天数 stepper | `同步天数` · `{N}` · `天` (bounds 1–15) |
| Probe primary action | `重新探测` |
| Probe not configured | heading `竞价数据未配置`; body `尚未配置竞价数据源；配置后平台将自动探测 9:15–9:25 集合竞价匹配数据的可用性。` |
| Probe running | `竞价数据探测中…` |
| Auction available | `竞价数据可用` |
| Probe fail-closed heading | `未接入竞价数据（已退化派生因子）` |
| Probe fail-closed body | `平台未检测到可用的集合竞价匹配数据，已退化到派生开盘涨幅因子（open / prev_close − 1）。09:30 起的连续竞价 bar 不会被标记为集合竞价数据。` |
| Probe failure | `竞价数据探测失败：{message}。已按未接入处理，当前使用派生开盘涨幅因子。请重试。` |
| Capability gate | `需 Pro+` (existing chip treatment) |
| Destructive confirmation | None in Phase 16. Disabling minute-K sync is non-destructive (stops future auto sync; existing data retained); no confirmation modal. |

Use clear Chinese task language, not unexplained internal implementation names. `kline_minute`, capability keys, and timestamp values may appear as inspectable metadata but must be accompanied by a human label.

---

## UI Considerations

> Populated by the ui-phase UI-consideration probe (Step 9.5) and lifted by plan-phase's
> `## UI Considerations` lift rule. Shape-rooted UI *state* coverage (empty / loading / error /
> populated / partial / overflow / zero-one-many / long-text). Empty-state and error-state COPY
> live in `## Copywriting Contract` above — this section covers state coverage and references
> those rows rather than restating the copy (de-dup).

Applicable state considerations resolved: 5 covered, 9 backstop, 0 unresolved — backend data layer with a single probe-verdict surface.

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| loading | 分钟K toggle | ✅ covered | `分钟K同步中·覆盖{N}天` 显示在分钟 K StatCard, `{N}` 用 mono/tabular |
| error | 分钟K toggle | ✅ covered | capability 缺失时 toggle 禁用(40% 透明度)并显示 `需 Pro+` chip; 绝不显示陈旧计数为新 |
| long-text | 分钟K toggle | 🧪 backstop | 状态副本安全换行 `overflow-wrap:anywhere`, 不溢出面板 |
| loading | 竞价数据探测判定 | ✅ covered | `竞价数据探测中…` 渲染保留行高状态行 + `Loader2` + `role="status"`; `重新探测` 禁用, 无并发 |
| error | 竞价数据探测判定 | ✅ covered | `竞价数据探测失败：{message}。已按未接入处理，当前使用派生开盘涨幅因子。请重试。` `role="alert"`; 09:30 bar 绝不标为集合竞价数据 |
| overflow | 竞价数据探测判定 | 🧪 backstop | 判定文案安全换行, 不溢出面板 |
| long-text | 竞价数据探测判定 | 🧪 backstop | fail-closed 长文案换行包裹, 不截断 |
| empty | 竞价数据面板 | ✅ covered | `竞价数据未配置` 渲染提示副本且无探测动作, 面板永不全白 |
| loading | 竞价数据面板 | 🧪 backstop | 加载保留行高, 判定行在面板内不抖动 |
| error | 竞价数据面板 | 🧪 backstop | 失败态显示 `role="alert"` 文案 + `重新探测`, 面板不空白 |
| populated | 竞价数据面板 | 🧪 backstop | `竞价数据可用` 显示 accent 检查图标状态行 |
| partial | 竞价数据面板 | 🧪 backstop | 部分配置时显示 `竞价数据未配置` 或 `已退化派生因子`, 不假装完整 |
| overflow | 竞价数据面板 | 🧪 backstop | 面板内容安全换行, 不溢出 |
| zero-one-many | 竞价数据面板 | 🧪 backstop | 单个判定状态行, 无复数副本 |

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
| shadcn official | None | Not applicable — `components.json` absent when scanned on 2026-08-04; shadcn initialization is explicitly excluded for this data-layer phase. |
| Third-party registry | None | No third-party blocks declared or permitted; no registry vetting needed. |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: clear status labels, CTA copy, empty/error/fail-closed language, and no opaque internal-only wording
- [x] Dimension 2 Visuals: existing dark-first Data-page layout, panel hierarchy, no duplicate shell or new route
- [x] Dimension 3 Color: established 60/30/10 tokens, reserved accent, warning-only fail-closed, market-direction-only bull/bear, and contrast/redundancy
- [x] Dimension 4 Typography: four-size/two-weight scale, monospaced data rules, and readable status copy
- [x] Dimension 5 Spacing: 4px-based scale, responsive touch exceptions, and panel rhythm
- [x] Dimension 6 Registry Safety: no shadcn initialization or third-party registry; timestamped absence evidence recorded


**Approval:** approved 2026-08-04
