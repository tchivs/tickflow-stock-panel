---
gsd_state_version: 1.0
milestone: v2.1
milestone_name: 历史深度与自选联动 — planning
current_phase: 25
current_phase_name: 自选股联动 (Watchlist Sync)
status: planning
stopped_at: Completed 25-01-PLAN.md
last_updated: "2026-08-06T06:05:01.951Z"
last_activity: 2026-08-06
last_activity_desc: Phase 24 complete, transitioned to Phase 25
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 4
  completed_plans: 3
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-04)

**Core value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.
**Current focus:** Phase 20 — 竞价数据层 (Auction Data)

## Current Position

Phase: 25 — 自选股联动 (Watchlist Sync)
Plan: Not started
Status: Ready to plan
Last activity: 2026-08-06 — Phase 24 complete, transitioned to Phase 25

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

Last session: 2026-08-06T06:05:01.939Z
Stopped at: Completed 25-01-PLAN.md
Resume file: None

## Operator Next Steps

- Phase 24 complete (2/2 plans); v2.1 继续 Phase 25 自选股联动 (WATCH-01..04)
- 前端 PoolHubPage 缺口横幅/回填触发按钮可消费 `GET /api/pool/dates` 新字段 (backfill_needed/backfill_examples) — 后续增强

## Decisions

- [Phase 24 / P2]: GET /api/pool/dates 增 backfill_needed (缺口计数) + backfill_examples (升序前 5 示例日), 数据源与回填共用 list_backfill_gaps 单点 (enriched 分区 − 快照分区), GET-only 零执行 (E4/E5 保持绿)
- [Phase 24 / P2]: build_pool_hub_snapshot 读侧透传 snapshot_origin — present 快照 snap.get(...,"eod") (旧快照缺字段→eod, Pitfall 5), 空态 None; EOD 落盘快照 origin=="eod" 断言
- [Phase 24 / P2]: D6 回归 source guard 作用域限定 def run_all 段 (W-1 修订), 避开 _update_single_strategy_cache 的 write_cache
- [Phase 24 / P1]: persist_point_snapshot 增 origin 参数 (eod/backfill/manual), payload 写 snapshot_origin, schema_version=1; 旧快照缺字段读 eod
- [Phase 24 / P1]: 回填路径绝不写 strategy_cache (byte-identical 断言锁死); 手动 run_all 历史 as_of 不写 cache 指针 (D6 latest_date 闸门)
- [Phase 21 / P1]: StrategyDef 新字段 (minute_confirm_fn/evaluation_time/minute_confirm_required) 置于 file_path 之后 (dataclass 默认值字段必须尾随非默认字段)
- [Phase 21 / P1]: auction_volume_ratio 受管列 = 竞价量/前5日均量(不含当日, PIT-safe), 注册进 ENRICHED_COLUMNS + BY_CATEGORY['auction'], 绝不进存储窄表/计算闭包; 无历史即列缺席
- [Phase 21 / P1]: 引擎 requires_auction_data 短路空池 (缺 auction_volume → 空 StrategyResult) + 策略 filter pl.lit(False) 守卫双保险; 分钟确认 seam 单点 datetime.time() <= evaluation_time 截断, minute_confirm_required 决定缺分钟数据空池/跳过
- [Phase ?]: watchlist 查询 enabled: !!data && mode === 'vip' 双门控 (D4/P2) — mode 由 data 派生回退 vip, data 未落地不误发
- [Phase ?]: 批量 scope = filteredRows 可见行 (display_limit 内), 绝不按 activeStrategy.total (D6/H8); watchlistOnly 开启时隐藏批量按钮
- [Phase ?]: watchlistPending = toggle.isPending || watchlist.isPending || watchlist.isError (H9 fail-closed); 星标/开关/批量按钮均带非空可访问名 (P1 白名单前提)

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
| Phase 21 P1 | 36 | 3 tasks | 7 files |
| Phase 24 P1 | — | 3 tasks | 6 files |
| Phase 24 P2 | 22 | 3 tasks | 5 files |
| Phase 25-watchlist-sync P1 | 10 | 3 tasks | 3 files |

---
*Last updated: 2026-08-05 — Phase 21 plan 1 (STRAT-04/05/06 engine seam + managed column + P1 strategies) complete; Phase 21 in progress (plan 2 parallel)*
