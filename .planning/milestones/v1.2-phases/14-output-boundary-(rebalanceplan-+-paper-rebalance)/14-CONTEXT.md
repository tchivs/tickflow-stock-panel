# Phase 14: Output & Boundary (RebalancePlan + Paper Rebalance) - Context

**Gathered:** 2026-08-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 14 is the milestone's raison d'être and **boundary phase**: it renders an immutable A-share **RebalancePlan** from continuous optimizer weights through a **lot-sizing adapter** (100-share lots, odd-lot sell handling, cash residue, turnover cost, blocked instruments, expiry, discretization RMSE visible) and lands suggestions in an **auditable paper-rebalance state machine** (append-only audit fact, human approval, idempotency). **Zero execution authority is a hard acceptance criterion** — no API endpoint, UI affordance, or service path can push a RebalancePlan to a live broker.

It is the fifth phase of milestone v1.2. Both requirements in scope: RBAL-01 (P1), RBAL-02 (P1). This phase reuses the existing A-share matching layer (`backtest/engine.py`) — the plan path MUST NOT build a naive second matcher.

**In scope:** RBAL-01, RBAL-02.
**Out of scope:** live broker execution (forever out of scope — platform boundary since v1.0); writing real positions; frontend (Phase 15). No execution routes anywhere.

</domain>

<decisions>
## Implementation Decisions

### A-share Lot-Sizing Adapter (RBAL-01)
- **Reuse `backtest/engine.py` matching layer** (T+1, price limits, suspension, 100-share lots, fees) — do NOT build a naive second matcher.
- Continuous optimizer weights → 100-share lots with odd-lot sell handling + cash residue.
- Discretization RMSE visible in the plan artifact.

### RebalancePlan Structure (RBAL-01)
- Continuous weights → discrete lot weights; **discretization RMSE** exposed.
- Fields: turnover cost, `blocked_instruments`, `expires_at` (expiry), target weights (continuous + discrete).
- **Immutable research-only artifact** (O_EXCL + fsync + sha256).

### Paper-Rebalance State Machine (RBAL-02)
- Flow: suggestion → human approve/reject → paper fill (PA_Agent ApprovalTicket pattern).
- Every transition is an **append-only audit fact** with idempotency.
- Paper fill does NOT write real positions; **no execution route anywhere** (hard acceptance criterion).

### Inputs & Binding (RBAL-01/02)
- Input = Phase 11 optimization run weights + Phase 13 validated strategies, bound by `input_snapshot_sha256`.
- Cash / blocked instruments provided explicitly by the researcher.
- Consumed by snapshot (artifact + sha256), never live module hand-off.

### Claude's Discretion
- Exact lot-sizing algorithm details (largest-lot-first vs remainder ordering), RMSE definition (weighted vs simple), state-machine transition names.
- New append-only table schemas (rebalance_plans, paper_rebalance_* audit facts) following existing conventions.
- `expires_at` default window.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backtest/engine.py` — A-share matching layer (T+1, limits, suspension, 100-share lots, fees) — REUSE, don't rebuild.
- `portfolio/optimizer.py` — Phase 11 continuous weights + immutable run records (`portfolio_optimization_runs`).
- `portfolio/repository.py` — `PortfolioRepository` run records by `input_snapshot_sha256`.
- `research/repository.py` — Phase 13 `wf_validated_strategies` (validated strategy signals).
- `research/artifacts.py` + `portfolio/artifacts.py` — O_EXCL + fsync + sha256 artifact discipline.
- `operational/migrations.py` — append-only conventions (Phases 10-13 tables + triggers).
- `portfolio/snapshot.py` — checksum-verified composite snapshot binding.

### Established Patterns
- Append-only SQLite rows + immutability triggers; `input_snapshot_sha256` binding; O_EXCL+fsync+sha256 artifacts.
- Shared signal chain / snapshot consumption (no live module hand-off).
- Module docstrings know/don't-know; ruff line-100 py311.

### Integration Points
- New `portfolio/rebalance.py` (lot-sizing adapter + RebalancePlan) + `portfolio/paper.py` (paper-rebalance state machine).
- New append-only tables: rebalance_plans + paper_rebalance transitions.
- Phase 15 surfaces plans + paper state via typed API.

</code_context>

<specifics>
## Specific Ideas

- RebalancePlan: continuous weights → discrete lots (100-share), odd-lot sell, cash residue, turnover cost, blocked instruments, `expires_at`; RMSE between continuous and discrete weights visible.
- Paper state machine: suggestion → approve/reject → paper fill; append-only audit fact per transition; idempotent approve/reject; NO route to live broker (hard acceptance).
- Reuses `backtest/engine.py` A-share rules — the plan path never builds a second matcher.

</specifics>

<deferred>
## Deferred Ideas

- Live broker execution — forever out of scope (platform boundary since v1.0).
- Auto-rebalance scheduling (v2).
- Writing real positions from paper fills (never — research-only).
- Frontend panels (Phase 15).

</deferred>
