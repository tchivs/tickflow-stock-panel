---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: 竞价深度与历史股池
status: planning
last_updated: "2026-08-04T16:14:03.003Z"
last_activity: 2026-08-04
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-04)

**Core value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.
**Current focus:** v1.3 竞价选股引擎 (planning)

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-08-04 — Milestone v2.0 started

## v1.3 Phase Summary

| Phase | Requirements | Status |
|-------|-------------|--------|
| 16 竞价数据层 | DATA-01..03 | Complete |
| 18 股池 Hub | POOL-01..03 | Complete |
| 19 游客/VIP 脱敏 + 前端 | GUEST-01..02 | Complete |

## Accumulated Context

### v1.3 Decisions

- [Roadmap]: v1.3 continues v1.2 numbering (Phase 16 start); phase IDs are sequential.
- [Roadmap]: Auction strategy names from the reference attachment are product labels, not public factor definitions — every strategy is authored first-principles with honest naming (STRAT-01).
- [Roadmap]: True 集合竞价 match data (9:15–9:25) is a probe-gated capability; when unavailable, the milestone fails closed to derived open-gap factors and never labels the 09:30 continuous-trading bar as auction data (DATA-03).
- [Roadmap]: Guest masking is server-authoritative at the API DTO boundary; client-side masking is never trusted (GUEST-01).
- [Roadmap]: New auction strategies land in `strategy/builtin/` only; the strategies API dedups against `PRESET_STRATEGIES` — no third registration track (STRAT-03).

### Pending Todos

None.

### Blockers/Concerns

- [v1.3 / Phase 16]: 集合竞价 match-data source availability is unverified — the milestone's dominant risk. Phase 16 must probe before strategy breadth is committed.
- [v1.3 / Phase 16]: Minute-K sync over the full universe is heavy; scope to the auction pool/spot set.

## Deferred Items

| Category | Item | Status |
|----------|------|--------|
| Feature | 日期导航 (per-day historical pool browsing) | Deferred to POOL-04 (v2) |
| Feature | Additional auction strategies beyond core 3 | Deferred to STRAT-04/05 (v2) |
| Feature | True auction match data as first-class columns | Deferred to DATA-04 (v2), gated on source availability |

## Session Continuity

Last session: 2026-08-04T15:36:33.310Z
Stopped at: Completed 19-02-PLAN.md
Resume file: None

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone

## Decisions

- [Roadmap]: Auction strategy family is 3 core strategies (竞价多头/盘前强势量化/早盘之星) in v1.3; the remaining reference names (竞价阿尔法/极速抢筹/T+1闪电/竞价全面策略/金色两点半) are v2 STRAT-04 unless a user wants them pulled forward.
- [Roadmap]: Pool hub is research-only with zero execution authority (POOL-03), matching the platform boundary since v1.0.
- [Phase 16 / P1]: Minute-K sync enable path proven hermetically; `minute_sync_symbols` scope knob shipped (API/preference-only, empty = full universe); 09:30 timestamp convention regression-locked.
- [Phase 16 / P2]: Auction-probe verdict is server-authoritative (not_configured/available/fail_closed/error) and the Data page renders only server statuses; open_gap (`open / prev_close − 1`) is a governed persisted column; the 09:30 bar is regression-locked never to be labeled 集合竞价 data.
- [Phase 19 / P1]: Guest masking is a copy-safe DTO transform applied only at the API boundary in pool.py; build_pool_hub stays unmasked in all modes (GUEST-02).
- [Phase 19 / P1]: mode = vip iff request.state.reviewer_principal resolves, else guest — never from client input or row values.
- [Phase 19 / P1]: Guest rows omit open_gap entirely (ROADMAP letter: guests see only 涨跌幅+概念板块); code/name/symbol mask to the literal ******.
- [Phase 19 / P1]: Guest surface is exactly GET /api/pool/hub + GET /api/screener/strategies (GET-only); everything else still 401.

---
*Last updated: 2026-08-04 — Phase 16 complete (DATA-01..03)*

- [Phase ?]: Phase 17 P2: hit_factors values sorted by Unicode codepoint (deterministic; PLAN sample order corrected: 盘前强势量化 before 竞价多头)
- [Phase ?]: Pool hub backend: single-as_of projection over strategy_cache; concept filter keeps total authoritative; cross_resonance = hit_factors>=2; GET /api/pool/hub is GET-only with no execution imports/write path (POOL-03).
- [Phase ?]: Presentation mode consumed ONLY from response.mode; missing/unknown mode defaults to vip (frontend never masks by default, never infers from row values).
- [Phase ?]: Guest masked cells are inert text (no title/aria-label/tooltip) so real identity never reaches the DOM.
- [Phase ?]: Guest rows keyed by strategy-scoped ordinal, never the masked symbol (no duplicate React keys).
- [Phase ?]: 开盘涨幅 header+cells render only when mode==='vip' (guest column set hides it).

## Performance Metrics

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 16 P1 | 25 | 3 tasks | 5 files |
| Phase 16 P2 | 20 | 3 tasks | 14 files |
| Phase 17 P2 | 32 | 2 tasks | 3 files |
| Phase 18 P1 | 20 | 3 tasks | 4 files |
| Phase 18-pool-hub P2 | 45 | 3 tasks | 10 files |
| Phase 19 P1 | 55 | 3 tasks | 6 files |
| Phase 19 P2 | 25min | 3 tasks | 11 files |
