---
gsd_state_version: 1.0
milestone: v2.2
milestone_name: 决策闭环与历史纵深 — planning
status: planning
stopped_at: Milestone v2.2 research synthesized; REQUIREMENTS + ROADMAP defined
last_updated: "2026-08-06T09:20:00.000Z"
last_activity: 2026-08-06
last_activity_desc: Milestone v2.2 requirements defined (25 reqs, Phases 28-31)
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
current_phase: null
current_phase_name: null
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-06)

**Core value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.
**Current focus:** Milestone v2.2 — 决策闭环与历史纵深

## Current Position

Phase: Milestone v2.2 planning (requirements + roadmap defined)
Plan: —
Status: Planning — research complete, awaiting Phase 28 research/plans
Last activity: 2026-08-06 — Milestone v2.2 requirements defined (25 reqs: 21 P1 + 4 P2, Phases 28-31)

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
| Feature | 概念板块 PIT 历史映射（历史股池概念标签按 as_of 解析，消除 current_snapshot 标注） | Deferred to v2.2 (research: data source history availability) |
| Feature | 竞价/盘前策略历史验证（回测引擎基于日 K，竞价策略族无验证路径） | Deferred to v2.2 (research) |
| Feature | 盘前/竞价监控告警（v2.1 盘前预览 + 竞价列接入规则引擎） | Deferred to v2.2 (research) |
| Feature | 竞价复盘（盘后复盘扩展竞价维度） | Deferred to v2.2 (research) |

## Session Continuity

Last session: 2026-08-06T08:27:24.050Z
Stopped at: Completed 27-02-PLAN.md (frontend PM-04 premarket view)
Resume file: None

## Operator Next Steps

- Milestone v2.2 research in progress — 4 domain researchers (concept-PIT / auction-backtest / preopen-monitor / auction-recap) → synthesize SUMMARY → REQUIREMENTS → ROADMAP (Phase 28+)

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
- [Phase ?]: Phase 25 / P2 (B1): 快照重生成范围修正为表格区 4 张 (resonance/filter-active/empty-zero-hit/vip-plaintext), 零 diff 断言集 = grid-populated/card-unavailable/guest-masked/guest-grid — 原计划误标 VIP 快照为 guest, verify 门必失败
- [Phase ?]: Phase 25 / P2: WATCH-01 二次 GET 断言用计数式而非精确次数 (StrictMode 双挂载免疫); no-mutating 守卫拆分 watchlist 写族与其余 non-GET 分别断言
- [Phase ?]: CHART-01: per-trading-day last-row (09:25) aggregation endpoint GET /api/kline/auction/history with row_count/min/max labels, honest 200 available:false, explicit 400, guest masking, probe passthrough
- [Phase ?]: CHART-03: CANONICAL_AUCTION_COLS stays 4 (R5); OPTIONAL_AUCTION_COLS = [auction_unmatched_volume, auction_virtual_price] kept by existence; merge-upsert how=diagonal_relaxed for old-4+new-6 schema union
- [Phase 26 / CHART-02]: 集成点 = StockPreviewDialog 顶栏第三开关「竞价历史」(镜像分时按钮 + aria-pressed) + StockPanel showAuction prop — 全站挂该弹窗页面一改全生效; Watchlist.tsx 零触碰
- [Phase 26 / CHART-02]: 历史竞价数据不可变 → QK.auctionHistory 不入 SSE_INVALIDATE_PREFIXES + useAuctionHistory staleTime 5min; 查询 days=120 显式
- [Phase 26 / CHART-02]: 诚实空态 D6 — probe 非 available / available:false / rows 空 / guest → EmptyState「无历史竞价数据」, 绝不渲染零值柱; 派生列 auction_unmatched_amount 绝不混排真实列
- [Phase 26 / CHART-02]: e2e 经 /screener 钻取打开弹窗 (B1 修订 — /pool-hub 不挂载 StockPreviewDialog); 轴单位/窗口标注以 DOM 文本渲染供 e2e 断言
- [Phase ?]: 盘前预览只落 premarket_results/date={T}/part.json, 绝不写 strategy_cache/screener_results (single-as_of 指针 + EOD 语义不动); 09:26 固定 mon-fri Asia/Shanghai, _run_tracked 单飞
- [Phase ?]: 固定 09:26 mon-fri Asia/Shanghai (CronTrigger + _PREMARKET_HOUR/_PREMARKET_MINUTE 常量), _run_tracked 单飞, misfire_grace_time=1800 (盘前窗口窄)
- [Phase ?]: open_gap 补算放 compute_enriched_today (prev_close 对齐块后), 与 EOD Pass 4 同一公式; 预览服务零自算 (无第二实现)
- [Phase ?]: GET /api/pool/premarket 只读零执行 (POOL-03); 预览缺失 → 200 available:false 诚实空态 (非 404); guest 掩码 + 白名单就位
- [Phase ?]: Phase 27 / P2 (27-02): 盘前判定消费 dates 白名单 (hasTodayEod = today ∈ /api/pool/dates) 而非墙钟 — 15:35 EOD 快照落盘后自动回退 hub, e2e 可稳定复现
- [Phase ?]: Phase 27 / P2 (27-02): QK.poolPremarket 不入 SSE_INVALIDATE_PREFIXES (定时快照非实时流) + staleTime 30s 对齐服务端 probe 30s TTL
- [Phase ?]: Phase 27 / P2 (27-02): AuctionColumnStatusBadge degraded prop 置于 hasReal 之前 — 服务端冻结 probe 判定驱动诚实警告分支, 绝不渲染「竞价数据可用」
- [Phase ?]: Phase 27 / P2 (27-02): showPremarketEmpty 时零池/策略网格短路 (盘前空态优先, 不混排昨日 hub 流) — Rule 3 修正

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
| Phase 25-watchlist-sync PP2 | 14 | 3 tasks | 6 files |
| Phase 26-auction-history-chart P1 | 24 | 2 tasks | 8 files |
| Phase 26 P2 | 38 | 2 tasks | 7 files |
| Phase 27-premarket-pool P1 | 11 | 3 tasks | 8 files |
| Phase 27 P2 | 35 | 3 tasks | 6 files |
