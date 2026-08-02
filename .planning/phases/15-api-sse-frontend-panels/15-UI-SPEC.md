---
phase: 15
slug: api-sse-frontend-panels
status: draft
shadcn_initialized: false
preset: none
created: 2026-08-01
reviewed_at: null
---

# Phase 15 — UI Design Contract

> Visual and interaction contract for surfacing the full v1.2 factor→portfolio pipeline through typed server-owned contracts, with ModelLibrary/WalkForward panels in the Backtest workspace and Optimization/RiskAttribution/RebalancePlan panels in the Portfolio workspace. **Zero execution authority is the phase's cardinal UI invariant.**

---

## Scope and Source Decisions

| Source | Binding UI decision |
|---|---|
| `15-CONTEXT.md` (all 4 areas accepted) | Server-owned Pydantic DTOs first; frontend `api.ts` strictly consumes them; reuse typed `api.ts` / `queryKeys.ts` / SSE hooks (no rewrite); five panels all in scope; panels read immutable rows/artifacts (append-only tables + checksum-verified artifacts); walk-forward SSE via durable job; optimization/plan updates fan out via the existing shared SSE stream; reconnect/idempotent. |
| `15-CONTEXT.md` Boundary & Honest Display | Paper-rebalance panel: read-only display + human approve/reject (append-only audit). NO execute/order affordance anywhere. Never label RankIC as generic IC. Never present optimizer output as "optimal" without baselines. Label selection-validation vs reserved OOS honestly. |
| `ROADMAP.md` Phase 15 planning notes | Reuse typed `api.ts` / `queryKeys.ts` / SSE hooks; never label RankIC as generic IC; never present optimizer output as "optimal" without baselines; never offer an "execute" affordance on plans; label selection-validation vs reserved OOS honestly. |
| Existing workspace (v1.0/11 patterns) | Preserve the existing React/Vite/Tailwind workspace, typed `api.ts`, TanStack Query, Lucide icons, ECharts charts, and the strategy SSE lifecycle (`backtestTask.ts`). |

### Phase boundary

- **In scope:** five read panels (ModelLibrary, WalkForward, Optimization, RiskAttribution, RebalancePlan), typed read API routes over Phases 10-14 repositories, paper-approve/reject actions (append-only), SSE streaming for walk-forward progress + optimization/plan fan-out.
- **Out of scope:** live broker execution (forever out of scope); new backend features (all data surfaces exist from Phases 10-14 — this phase only ADDS typed read routes + panels + SSE wiring); auto-rebalance scheduling (v2); any execute/order affordance in the UI (never).

---

## Design System

| Property | Value |
|---|---|
| Tool | Manual existing system: Tailwind CSS tokens and local React components |
| Component library | Existing local components + native semantic controls; no new registry |
| Icon library | `lucide-react` (existing 14–16px outline icons beside, never instead of, visible labels) |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, system sans; mono (`JetBrains Mono`/`IBM Plex Mono`) only for identifiers, dates, weights, checksums |
| Charts | Existing ECharts integration; no new charting dependency |
| Server state | Existing typed `api.ts` methods + TanStack Query `QK` factories; no direct `fetch`, no duplicate request helper, no client-side provenance synthesis |

### Existing visual tokens to preserve

CSS variables in `frontend/src/index.css` + Tailwind semantic names (`base`, `surface`, `elevated`, `border`, `foreground`, `secondary`, `muted`, `accent`, `bull`, `bear`, `warning`, `danger`). Dark mode default; light mode token inversion. 1px `border-border` separation; radii `rounded-input` 4px, `rounded-btn` 6px, `rounded-card` 8px, `rounded-dialog` 12px. No gradients, glass surfaces, oversized rounded cards, decorative shadows, or a Phase-15-specific palette.

---

## Information Hierarchy and Workflow

### Workspace hierarchy

1. **Backtest workspace — ModelLibrary panel:** the focal point is the admitted-factor catalog. Present factors as immutable rows: name, current revision, admission verdict (policy version, passed gates, IC/ICIR), monthly evidence summary, and the composite models they feed (weights, lineage). RankIC MUST be labeled `RankIC` (never `IC`); IC and RankIC columns stay separate. Composite model rows show weighting (equal / IC-weighted), revision lineage, and input-snapshot sha256.
2. **Backtest workspace — WalkForward panel:** list pinned walk-forward plans (OOS reservation in `oos_pinned_at`), their folds (train/gap/test ranges), OOS-scored search runs (trial count, search space, score distribution), validated strategies, and ensembles (rank-average). Label the reserved final OOS segment honestly — `selection/validation` folds vs `reserved OOS` must be visually distinct, never conflated.
3. **Portfolio workspace — Optimization panel:** immutable run rows: objective (min-vol / HRP / max-Sharpe), as-of, universe, constraint stack, solver name/version, problem status, failure reason (for failed runs), and output weights. **Max-Sharpe / optimizer output MUST be presented with baselines (min-vol + HRP side by side) — never "optimal" alone.**
4. **Portfolio workspace — RiskAttribution panel:** exposure + marginal-contribution attribution evidence (signed components, reconciliation to portfolio variance), covariance provenance (method/epsilon/eigenvalues if PSD-repaired, never silent), and drawdown attribution by instrument × time segment.
5. **Portfolio workspace — RebalancePlan panel:** the plan header (continuous vs discrete weights side by side, lot sizes, cash residue, turnover cost, blocked instruments, discretization RMSE, expires_at) + the paper state machine: current state (suggested / approved / rejected / filled), append-only transition ledger, and — ONLY for a `suggested` plan — a human `approve` / `reject` action (idempotent). **There is NO execute/order/submit affordance anywhere in this panel or any panel.** A disabled "execute" button is FORBIDDEN (a disabled affordance still signals an intent the product must not have); the panel simply has no such control.

### Streaming progress

6. **Walk-forward SSE:** a walk-forward run streams progress (fold index / total folds / current status) over SSE through the durable job pattern (`_BacktestJob`-style module-level job + progress history replay on reconnect, mirroring `backtestTask.ts`). The UI shows a live progress bar with reconnect state.
7. **Optimization/plan fan-out:** optimization run completion and rebalance-plan/paper-transition updates fan out through the existing shared SSE stream (the `SSE_INVALIDATE_PREFIXES` mechanism in `queryKeys.ts`) — the panels auto-refresh without polling.

---

## Interaction States

| State | Visual | Behavior |
|---|---|---|
| Immutable run/plan/evidence row | `surface` card, mono identifiers, muted metadata | Read-only; expandable for full detail; never editable |
| Failed run | `danger` status chip + failure reason | Expandable to show the recorded failure reason |
| PSD-repaired risk model | `warning` chip "PSD repaired (method, ε)" | Expandable to show eigenvalues before/after — never silent |
| Paper state | status chip per state (suggested `accent` / approved `bull` / rejected `danger` / filled `muted`) | Current state always visible; ledger below |
| Paper approve/reject action | `accent` approve button + `danger` reject button, ONLY on `suggested` plans | POST → optimistic update → ledger append; idempotent (re-POST returns same row) |
| SSE streaming | live progress bar + `reconnecting` state | Auto-reconnect up to MAX_RECONNECT_ATTEMPTS; progress history replay |

---

## Accessibility & Honest-Display Rules (hard)

- No execute/order/submit control anywhere in the UI (zero execution authority).
- RankIC never rendered as IC; separate columns.
- Optimizer output always rendered with baselines.
- Reserved OOS vs selection/validation folds visually distinct and honestly labeled.
- Color is never the only signal (status chips carry text).
- Keyboard navigable: panels are standard lists/cards; approve/reject are real buttons with focus states.

---

## Success Criteria (from ROADMAP)

1. ModelLibrary + WalkForward panels in Backtest workspace backed by typed server-owned contracts. (UI-01)
2. Optimization + RiskAttribution + RebalancePlan panels in Portfolio workspace backed by typed server-owned contracts. (UI-02)
3. Walk-forward runs stream progress over SSE through the durable job pattern; optimization/plan updates fan out through the existing shared SSE stream.

---

*Phase: 15-api-sse-frontend-panels*
*Status: draft (approved by planner; verified during execution)*
