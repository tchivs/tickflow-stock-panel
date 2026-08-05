---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: 竞价深度与历史股池 — planning
current_phase: 21
current_phase_name: 竞价策略族 (Auction Strategy Family)
status: planning
stopped_at: Completed 20-02-PLAN.md
last_updated: "2026-08-05T05:18:43.648Z"
last_activity: 2026-08-05
last_activity_desc: Phase 20 complete, transitioned to Phase 21
progress:
  total_phases: 8
  completed_phases: 1
  total_plans: 2
  completed_plans: 2
  percent: 13
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-04)

**Core value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.
**Current focus:** Phase 20 — 竞价数据层 (Auction Data)

## Current Position

Phase: 21 — 竞价策略族 (Auction Strategy Family)
Plan: Not started
Status: Ready to plan
Last activity: 2026-08-05 — Phase 20 complete, transitioned to Phase 21

Progress: [██████████] 100%

## v1.3 Phase Summary (shipped 2026-08-04)

| Phase | Requirements | Status |
|-------|-------------|--------|
| 16 竞价数据层 | DATA-01..03 | Complete |
| 17 竞价策略族 | STRAT-01..03 | Complete |
| 18 股池 Hub | POOL-01..03 | Complete |
| 19 游客/VIP 脱敏 + 前端 | GUEST-01..02 | Complete |

## v2.0 Phase Summary

| Phase | Requirements | Status |
|-------|-------------|--------|
| 20 竞价数据层 | DATA-04..06 | Complete |
| 21 竞价策略族 | STRAT-04..09 | Not started |
| 22 股池日期导航 | POOL-04..06 | Not started |
| 23 前端 | FRONT-01..02 | Not started |

## Accumulated Context

### v2.0 Roadmap Decisions

- [Roadmap]: v2.0 continues v1.3 numbering (Phase 20 start, after Phase 19); phase IDs are sequential (`phase_naming: sequential`).
- [Roadmap]: Data-first build order is locked — DATA (20) → STRAT (21) → POOL (22) → FRONT (23). Auction columns are the value precondition for strategy differentiation; per-day caching precedes historical browsing; frontend is pure display consumption.
- [Roadmap]: True 集合竞价 columns (DATA-04) are probe-gated end to end — probe 非 `available` → columns absent + fail-closed to derived `open_gap`; the 09:30 continuous bar is regression-locked to never be labeled 集合竞价 data.
- [Roadmap]: Historical pools are frozen point snapshots (`as_of` + `computed_at` + strategy-version fingerprint) at `screener_results/date={as_of}/` — never the `today_ever_rows` union, never backfilled/appended (POOL-04).
- [Roadmap]: Date navigation uses an independent read-only `GET /api/pool/dates` + as_of projection; the existing single-as_of `GET /api/pool/hub` contract is preserved and unmodified (POOL-05).
- [Roadmap]: 金色两点半 (STRAT-06) is honestly classified as a 尾盘/隔夜 strategy, never mixed into the auction window.
- [Roadmap]: The pool feature carries zero execution authority — POOL-03 AST guard extends to all `/api/pool/*`.

### Pending Todos

None.

### Blockers/Concerns

- [v2.0 / Phase 20]: DATA-04 集合竞价数据源可用性未验证 — 本期最大不确定项。Phase 20 规划前必须先做 probe 探测（`--research-phase`）；全部下游策略与 UI 以 fail-closed 为前提设计。
- [v2.0 / Phase 20]: 虚拟成交（`auction_virtual_fill`）字段语义依赖具体上游 — 物化前以 probe 实测确认，不做来源推测。
- [v2.0 / Phase 22]: 概念板块 PIT — 历史 ext 概念映射分区目前不存在；历史视图概念标签需标注「当前快照」或引入历史 ext 分区。

## Deferred Items

| Category | Item | Status |
|----------|------|--------|
| Feature | 虚拟成交实时列 / 历史竞价图 | Deferred to v2.1+ (needs real-time auction source) |
| Feature | DATA-05 盘前股池 (09:30 前可用) | Deferred to v2.1+ (needs real-time source) |
| Feature | 逐日全量存档模式（非回放） | Deferred to v2.1+ (replay-first, zero storage) |
| Feature | POOL-05 自选股联动 | Deferred to v2.1+ |

## Session Continuity

Last session: 2026-08-05T00:58:01.000Z
Stopped at: Completed 20-02-PLAN.md
Resume file: None

## Operator Next Steps

- Phase 20 (DATA-04..06) complete — proceed to `/gsd-plan-phase 21` (竞价策略族, STRAT-04..09).

## Decisions

### v1.3 Decisions (carried)

- [Roadmap]: Auction strategy family is 3 core strategies (竞价多头/盘前强势量化/早盘之星) in v1.3; the remaining reference names (竞价阿尔法/极速抢筹/T+1闪电/竞价全面策略/金色两点半) are v2 STRAT-04 unless a user wants them pulled forward.
- [Roadmap]: Pool hub is research-only with zero execution authority (POOL-03), matching the platform boundary since v1.0.
- [Phase 16 / P1]: Minute-K sync enable path proven hermetically; `minute_sync_symbols` scope knob shipped; 09:30 timestamp convention regression-locked.
- [Phase 16 / P2]: Auction-probe verdict is server-authoritative (not_configured/available/fail_closed/error); open_gap (`open / prev_close − 1`) is a governed persisted column; the 09:30 bar is regression-locked never to be labeled 集合竞价 data.
- [Phase 17 / P2]: hit_factors values sorted by Unicode codepoint (deterministic; PLAN sample order corrected: 盘前强势量化 before 竞价多头).
- [Phase 18 / P1]: Pool hub backend: single-as_of projection over strategy_cache; concept filter keeps total authoritative; cross_resonance = hit_factors >= 2; GET /api/pool/hub is GET-only with no execution imports/write path (POOL-03).
- [Phase 19 / P1]: Guest masking is a copy-safe DTO transform applied only at the API boundary in pool.py; build_pool_hub stays unmasked in all modes (GUEST-02).
- [Phase 19 / P1]: mode = vip iff request.state.reviewer_principal resolves, else guest — never from client input or row values; guest surface is exactly GET /api/pool/hub + GET /api/screener/strategies (GET-only).
- [Phase 19 / P1]: Guest masked cells are inert text (no title/aria-label/tooltip); rows keyed by strategy-scoped ordinal; 开盘涨幅 header+cells render only when mode==='vip'.
- [Phase 20 / P1]: Auction lake write gate is the probe verdict (`resolve_auction_probe().status == available`), not a capability — `can_sync_auction` keeps the capset signature for alignment only; 09:30 continuous bar is structurally excluded by the shared 555..565 predicate (single source of truth with provider `_normalize_auction`).
- [Phase 20 / P1]: `kline_auction` empty lake registers no view (existing empty-dir semantics) — read path degrades to 0 rows; `auction_sync_enabled` defaults False (explicit opt-in mirroring minute).
- [Phase 20 / P2]: `auction_volume`/`auction_amount`/`auction_unmatched_amount` 注册进 `ENRICHED_COLUMNS` + `BY_CATEGORY["auction"]`, 绝不进 `ENRICHED_STORAGE_COLS`/`_ALL_INDICATOR_COLS` (窄表=可重算, 计算闭包=可重算不变量; 竞价列存在性是 probe 条件)。
- [Phase 20 / P2]: 读路径按 probe×分区双闸门左联注入: `resolve_auction_probe().status==available` 且 `kline_auction/date={d}/part.parquet` 存在且有行; 任一不通过列缺席, fail-closed 到 `open_gap`; 左联前 symbol 级去重防 fan-out。
- [Phase 20 / P2]: DATA-06 派生 `auction_unmatched_amount = 虚拟未匹配量 × 虚拟参考价` (估算, 非真实成交), 委托量输入可得才派生, 缺输入列缺席 → 策略回退量比+金额强度; 与真实竞价列分列永不相加。

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
| Phase 20 P1 | 32 | 3 tasks | 5 files |
| Phase 20 P2 | 41 | 3 tasks | 5 files |

---
*Last updated: 2026-08-05 — Phase 20 plan 2 (DATA-04/06 auction columns + unmatched proxy) complete; Phase 20 (DATA-04..06) complete*
