# Roadmap: AthenaQuant

## Milestones

### v1.0 MVP — shipped 2026-07-27

### v1.1 Operational Hardening — shipped 2026-07-29

### v1.2 End-to-End Factor Portfolio Pipeline — shipped 2026-08-03

### v1.3 竞价选股引擎 — shipped 2026-08-04

### v2.0 竞价深度与历史股池 — shipped 2026-08-05

Four phases (20-23) delivered probe-gated real auction columns + `kline_auction/date={d}/` lake, six auction/tail strategies (27 builtin total), frozen point snapshots + date navigation + EOD persistence, and the DateNavigator frontend. Archived: `.planning/milestones/v2.0-phases/`, `v2.0-REQUIREMENTS.md`, `v2.0-ROADMAP.md`, `v2.0-MILESTONE-AUDIT.md`.

### v2.1 历史深度与自选联动 — shipped 2026-08-06

四个领域深化已落地的历史股池与自选能力：逐日全量存档（批量回填 + 诚实 provenance）、自选股与股池联动（纯前端）、历史竞价图 + 派生列复活（条件式）、盘前股池第一档（独立预览 + 诚实降级）——全部零新增运行时依赖，沿 POOL-03 零执行权边界，strategy_cache single-as_of 完整性为跨领域护栏。Archived: `.planning/milestones/v2.1-phases/`, `v2.1-REQUIREMENTS.md`, `v2.1-ROADMAP.md`, `v2.1-MILESTONE-AUDIT.md`.

### v2.2 决策闭环与历史纵深 — planning

四领域研究确认（`research/v2.2-decision-loop/SUMMARY.md`）：概念板块 PIT 前向按日归档（消除 current_snapshot 标注）、竞价策略只读信号质量报告、盘前预览接入监控告警（新 preopen 规则类型）、确定性竞价复盘面板——全部零新增运行时依赖，延续诚实 provenance（data_gate/pre_eod/as_of_snapshot 三态）与 POOL-03 零执行权。

## Phases

**Phase Numbering:**

- v2.1 ended at Phase 27; v2.2 continues at Phase 28 (`phase_naming: sequential`)

- [x] **Phase 16: 竞价数据层 (Auction Data)** - Minute-K sync, governed open-gap factor, auction probe — DATA-01..03 (completed 2026-08-04)
- [x] **Phase 17: 竞价策略族 (Auction Strategy Family)** - 竞价多头/盘前强势量化/早盘之星 builtin strategies — STRAT-01..03 (completed 2026-08-04)
- [x] **Phase 18: 股池 Hub (Pool Hub)** - Strategy cards, drill-down, concept filter, 交叉共振 — POOL-01..03 (completed 2026-08-04)
- [x] **Phase 19: 游客/VIP 脱敏 + 前端 (Guest Access & Frontend)** - Server-authoritative masking + pool page — GUEST-01..02 (completed 2026-08-04)
- [x] **Phase 20: 竞价数据层 (Auction Data)** - Probe-gated real auction columns + `kline_auction/date=*/` lake + unmatched proxy — DATA-04..06 (completed 2026-08-05)
- [x] **Phase 21: 竞价策略族 (Auction Strategy Family)** - 极速抢筹/竞价阿尔法/金色两点半/竞价全面/T+1闪电/盘中确认 — STRAT-04..09 (completed 2026-08-05)
- [x] **Phase 22: 股池日期导航 (Pool Hub Date Navigation)** - Frozen point snapshots + dates/as_of endpoints + EOD job — POOL-04..06 (completed 2026-08-05)
- [x] **Phase 23: 前端 (Frontend)** - DateNavigator + auction column drill-down (real vs derived) — FRONT-01..02 (completed 2026-08-05)
- [x] **Phase 24: 逐日全量存档 (Historical Archive)** - User-triggered batch backfill + snapshot_origin provenance + backfill_needed gap signal + cache-pointer pollution fix — HIST-01..04 (completed 2026-08-06)
- [x] **Phase 25: 自选股联动 (Watchlist Sync)** - Pool drill-down watch stars + 只看自选 filter + shared cache consistency — WATCH-01..04 (completed 2026-08-06)
- [x] **Phase 26: 历史竞价图 + 派生列复活 (Auction History Chart)** - Read-only auction history API + ECharts chart + lake ingestion preserves delegation-volume columns — CHART-01..03 (completed 2026-08-06)
- [x] **Phase 27: 盘前股池 (Premarket Pool)** - Scheduled premarket preview job (independent store) + open_gap completion + probe-honest degraded semantics + frontend premarket view — PM-01..04 (completed 2026-08-06)
- [x] **Phase 28: 概念板块 PIT (Concept PIT)** - Forward daily concept archive + as_of read-side resolution + three-state attribution — CONCEPT-01..07 (completed 2026-08-06)
- [x] **Phase 29: 竞价策略历史验证 (Auction Strategy Validation)** - Read-only signal-quality report + vectorized auction-column injector — BT-01..06 (completed 2026-08-06)
- [x] **Phase 30: 盘前监控告警 (Premarket Monitoring)** - New preopen rule type + evaluate_premarket + 09:26 job-tail wiring — MON-01..07 (completed 2026-08-06)
- [ ] **Phase 31: 竞价复盘 (Auction Recap)** - Deterministic auction recap panel in the post-close recap + optional AI commentary — REV-01..05

## Phase Details

### Phase 24: 逐日全量存档 (Historical Archive)

**Goal**: Operator can backfill the historical pool archive in one bounded, cancelable, provenance-honest pass — `screener_results/date={as_of}/` snapshots replayed from `run_all_with_hits` without ever touching the `strategy_cache.json` single-as_of pointer; gaps and progress are visible; the manual historical-`run_all` pointer-pollution path is fixed.
**Depends on**: v2.0 completion (Phase 23)
**Requirements**: HIST-01, HIST-02, HIST-03, HIST-04
**Success Criteria** (what must be TRUE):

  1. Operator triggers a backfill (full or date-bounded) and missing historical snapshots appear under `screener_results/date={as_of}/`; `strategy_cache.json` latest-as_of pointer is byte-identical before/after backfill.
  2. Every new snapshot carries `snapshot_origin: backfill` (vs `eod`); existing snapshots without the field read as `eod`.
  3. The API/UI surfaces `backfill_needed` for dates with no snapshot and observable progress; backfill is cancelable and bounded.
  4. Backfill surface is GET-only / operator-only, zero execution authority (POOL-03); manual `run_all` for historical as_of no longer writes the cache pointer.

**Plans**: 2/2 plans executed

- [x] 24-01-PLAN.md
- [x] 24-02-PLAN.md

**Research flag**: 需要 `--research-phase` — 回填 job 触发方式（手动端点 vs 空闲自动）与默认边界（全量 vs 最近 N 日）需细化；历史 as_of 来源（交易日历 vs 现有快照/分区）。

### Phase 25: 自选股联动 (Watchlist Sync)

**Goal**: VIP users can star/watch stocks in the pool drill-down and filter to "只看自选" — a pure-frontend composition over the existing `/api/watchlist` CRUD + shared `QK.watchlist` cache, with guest rendering pixel-identical and strategy-card totals authoritative.
**Depends on**: v2.0 completion (Phase 23); existing watchlist service
**Requirements**: WATCH-01, WATCH-02, WATCH-03, WATCH-04
**Success Criteria** (what must be TRUE):

  1. VIP pool rows render watch stars that toggle membership via `/api/watchlist`; guest session shows zero watch controls and issues zero watchlist queries.
  2. "只看自选" filter narrows rows without changing strategy-card `total`; works on latest and historical as_of views; honest empty state.
  3. Membership is consistent across pages via shared cache; join key = fully-suffixed `symbol` exact match.
  4. (P2) Batch-add visible rows reuses the existing batch-add endpoint.

**Plans**: 2/2 plans executed

- [x] 25-01-PLAN.md
- [x] 25-02-PLAN.md

**Research flag**: standard patterns — 纯前端, 抄 Screener.tsx 先例; 执行前确认用户预存 `Watchlist.tsx` 未改 `QK.watchlist` 契约.

### Phase 26: 历史竞价图 + 派生列复活 (Auction History Chart)

**Goal**: User can view per-symbol historical auction volume/amount trends in the stock drill-down (ECharts, zero new deps) via a read-only aggregate endpoint; the lake ingestion path preserves delegation-volume inputs so the derived 虚拟未匹配金额 column becomes live data instead of absent columns.
**Depends on**: v2.0 completion (Phase 23); `kline_auction` lake
**Requirements**: CHART-01, CHART-02, CHART-03
**Success Criteria** (what must be TRUE):

  1. `GET /api/kline/auction/history?symbol=&days=` returns per-day last-row (09:25 final) aggregates; empty lake returns 200 `available: false` (honest, not 404); GET-only zero execution.
  2. Frontend renders the chart in the stock popup with dual-axis 柱/线, empty state + 09:15–09:25 window annotation, zero new npm deps, `Watchlist.tsx` untouched.
  3. Auction lake canonical schema widens to 4 required + 2 optional delegation-volume columns (backward compatible); the derived `auction_unmatched_amount` branch activates with "估算" annotation intact.

**Plans**: 2/2 plans executed

Plans:

- [x] 26-01-PLAN.md — 后端: CHART-01 只读竞价历史聚合端点 (POOL-03 GET-only + 诚实空态 + guest 掩码) + CHART-03 湖摄入 canonical 扩为 4 必需 + 2 可选委托量输入列 (diagonal_relaxed)
- [x] 26-02-PLAN.md — 前端: CHART-02 竞价历史双轴柱线图 (StockPreviewDialog toggle + StockPanel prop + AuctionHistoryChart) + e2e mock 三态

**Research flag**: medium — 窗口内行粒度语义（末行 vs 逐分钟累计快照 vs 求和）需在接入真实源前钉死并写进验收.

### Phase 27: 盘前股池 (Premarket Pool)

**Goal**: A scheduled 09:26 job produces a same-day premarket pool preview (`premarket_results/date={T}/`, independent store) with a complete data frame (`open_gap` computed), honest probe semantics (real auction columns only when today-probe `available`, else degraded), and a frontend view distinct from EOD archives.
**Depends on**: v2.0 completion (Phase 23); `run_all_with_hits` + probe seam
**Requirements**: PM-01, PM-02, PM-03, PM-04
**Success Criteria** (what must be TRUE):

  1. 09:26 job writes premarket preview to independent store; `strategy_cache`/`screener_results` (EOD) untouched.
  2. Today frame has `open_gap` (single implementation, no Pass-4 drift); absent real auction columns fail closed to derived factors; ex-div caliber fixture-covered.
  3. Probe-honest: today-probe `available` → real columns injected at read; else absent + `degraded`/window status; never implies real auction data premarket.
  4. Frontend distinguishes premarket preview from EOD archives (window annotation); DateNavigator lists EOD dates only.

**Plans**: 2/2 plans executed

- [x] 27-01-PLAN.md
- [x] 27-02-PLAN.md

**Research flag**: 需要 `--research-phase` — open_gap 补算 seam、probe 今日窗口语义、预览存储 schema、调度并发（与 EOD job/维表同步互斥）.

### Phase 28: 概念板块 PIT (Concept PIT)

**Goal**: Historical pool concept labels become as-of accurate — a forward daily concept archive (`data/ext_history/gn_ths/date={as_of}/`) captured at EOD, read-side as-of resolution in `_build_concept_map`, and a three-state `concept_attribution` (`as_of_snapshot`/`current_snapshot`/`unavailable`), eliminating the today's `current_snapshot`-only labeling; shared seam extends to overview/RPS.
**Depends on**: v2.1 completion (Phase 27); `ext_gn_ths` snapshot + `_pool_eod_persist` hook + `_read_ext_rows` hive-partition read
**Requirements**: CONCEPT-01..07
**Success Criteria** (what must be TRUE):

  1. EOD hook captures concept snapshot to `ext_history/gn_ths/date={as_of}/part.parquet` (atomic, strict date, never blocks pool snapshot); `ext_gn_ths` current file untouched (manual-refresh design kept).
  2. Historical pool view resolves concept membership at `as_of`; missing partition falls back to current ext with `current_snapshot` attribution (honest, never fabricated).
  3. Attribution is three-state and never mixed per-row; write path AST-guarded (only `ext_history/`).
  4. Frontend shows a badge/tooltip when not `as_of_snapshot`; market overview + RPS use the same as-of seam; `Watchlist.tsx` untouched.

**Research flag**: 需要 `--research-phase` — 上游 `concepts.json` 更新节奏（OQ-3 一周逐日抓取 diff 探针）、EOD 归档是否自动刷新当前 ext（OQ-1，决策：否，保持手动）、行业归档范围（OQ-2，决策：概念+行业一起建）.

**Plans**: 3/3 plans executed

Plans:

- [x] 28-01-PLAN.md — 后端核心: `concept_history.py` (capture/read_partition/manifest/list/sha256 + OQ-3 probe 脚本) + `_pool_eod_persist` EOD 钩子 + `_build_concept_map` as_of 三态归属状态机 + CONCEPT-05 AST 守卫 + 回归锁
- [x] 28-02-PLAN.md — 前端: CONCEPT-04 概念归属徽标/工具提示 (`current_snapshot`/`unavailable` vs `as_of_snapshot` + 生效日期) + e2e 三态 + docs (Watchlist.tsx 零触碰)
- [x] 28-03-PLAN.md — CONCEPT-06 共享 seam: `_dimension_rank`/`_load_concept_map_df` as_of 接线 (总览/RPS) + `/api/rps/rotation?as_of=` + CONCEPT-07 API 外露复验

### Phase 29: 竞价策略历史验证 (Auction Strategy Validation)

**Goal**: The 9 auction/pre-open strategies gain a historical signal-quality validation — a read-only `GET /api/research/auction/validation` report over `kline_auction`-enabled dates (honest `data_gate` when the lake is empty), built on a new vectorized `attach_auction_columns_range` primitive; derived/EOD-proxy branches validated on enriched history with mutually-exclusive branch labels; zero execution, zero new deps.
**Depends on**: v2.1 completion (Phase 27); `attach_auction_columns` dual-gate + `kline_auction` lake + enriched history
**Requirements**: BT-01..06 (BT-07 full auction backtest explicitly deferred to v2.3+)
**Success Criteria** (what must be TRUE):

  1. Empty lake / probe unavailable → 200 `{data_gate:"empty", coverage:0}` (never 404/500); enabled dates = `kline_auction` partitions ∩ enriched.
  2. `attach_auction_columns_range` is vectorized, PIT-safe denominator, no null-as-present, never touches the governed frozen-panel seam.
  3. Per-strategy `{branch, n_dates, n_hits, coverage, forward_stats, per_date, data_gate}`; real-column strategies report `n_dates==0` honestly when lake empty (never downgraded); derived/EOD branches validated with explicit labels.
  4. Forward-outcome semantics locked (BT-04: T-open entry, next-day open/close rets, open_gap_outcome); missing outcomes counted in `n_missing_outcomes`, never filled.

**Research flag**: 需要 `--research-phase`（中） — `attach_auction_columns_range` 向量化与 enabled-dates 语义、`BACKTEST_MAX_SERVER_DAYS=186` 与 248 天 enriched 区间冲突、历史竞价数据源可行性（超出代码范围）.

**Plans**: 3/3 plans executed

Plans:

- [x] 29-01-PLAN.md — BT-02 区间竞价列注入原语: `attach_auction_columns_range` (分区存在性主闸门 + PIT-safe 向量化 ratio + enabled-dates) + 等价性属性测试 + 边界
- [x] 29-02-PLAN.md — BT-03/04/05 报告装配服务: `AuctionValidationService.build_report` (窗口回夹双字段回显、9 策略枚举 + 互斥 branch、候选掩码镜像、BT-04 前瞻统计、per_date)
- [x] 29-03-PLAN.md — BT-01/06 API 面: `GET /api/research/auction/validation` + main.py 注册 + POOL-03 AST 守卫 + 端点集成测试 + docs

### Phase 30: 盘前监控告警 (Premarket Monitoring)

**Goal**: v2.1 premarket preview enters the unified alert chain — a new `preopen` monitor rule type (whitelisted pre-open fields, EOD columns banned), `evaluate_premarket()` isolated from the intraday `_strategy_pools` baseline, wired to the 09:26 preview job tail, with honest provisional/degraded/probe annotation and guest masking.
**Depends on**: v2.1 completion (Phase 27); premarket preview + `MonitorRuleEngine` + operational alert chain
**Requirements**: MON-01..07
**Success Criteria** (what must be TRUE):

  1. `preopen` rule type validates against the whitelist (`open_gap`/auction cols, numeric ops only — `op=truth` explicitly rejected); EOD-only fields banned; `change_pct` set to `None` in the eval frame (honest).
  2. `evaluate_premarket` runs in isolation — zero pollution of `_strategy_pools`/`_latest_strategy_results` (no spurious 09:30 dropped/new_entry).
  3. Wired to 09:26 job tail (same single-flight, after persist); reuses operational → SSE → webhook.
  4. `provisional/degraded/probe` annotated on events; degraded + auction-dependent rules fail closed (0 alerts, never silent-0-fill); guest-visible surfaces masked.

**Plans**: 3/3 plans executed

Plans:

- [x] 30-01-PLAN.md — 后端核心 (MON-01/02/04): preopen 规则类型 + PREOPEN_ALLOWED_FIELDS 白名单 + validate 专属分支 + `preopen_eval.py` 独立只读模块 + `evaluate_premarket` 隔离评估 + evaluate() 盘中跳过 (D-03) + T1-T10
- [x] 30-02-PLAN.md — 后端接线 (MON-03/04/05/06/07 后端): 09:26 job 尾段 + `evaluate_premarket_alerts` 持久化优先链 + `mask_guest_alert` + /options preopen 外露 + T11-T20 (含 AST 守卫)
- [x] 30-03-PLAN.md — 前端 P2 (MON-07): api.ts 类型 + RuleEditor preopen 编辑 + Monitor.tsx provisional/degraded 徽标 + e2e + docs (Watchlist.tsx 零触碰)

**Research flag**: 需要 `--research-phase`（高） — R1 `change_pct` 盘前帧口径核实（`compute_enriched_today` + quote_service preopen flush）、调度（尾段 vs 独立 09:27）、`scope=sector` 支持.

### Phase 31: 竞价复盘 (Auction Recap)

**Goal**: The post-close recap gains a deterministic auction dimension — a read-only `auction_recap.py` assembles real auction activity / `open_gap` snapshot / premarket signal-quality blocks from frozen assets, appended as a delta before the `done` event (SSE/archive/Feishu all receive it); honest `data_completeness` enum + `pre_eod` degradation; optional AI commentary defaults OFF; default recap schedule moves to 15:40.
**Depends on**: v2.1 completion (Phase 27); `premarket_results` + `kline_auction` + enriched + `recap_market_stream`
**Requirements**: REV-01..05 (REV-05 P2 standalone endpoint)
**Success Criteria** (what must be TRUE):

  1. Deterministic blocks assembled read-only from frozen assets (never triggers `run_all_with_hits`); historical as_of uses partition-existence gate.
  2. `data_completeness` enum + missing-block omission with note; 09:30+ bar never labeled auction; `pre_eod` when run before 15:30 sync; 「确定性数据，非 AI 生成」 marker.
  3. Premarket signal-quality block driven by strategies with actual preview rows; joins EOD `change_pct` caliber.
  4. Panel delta appended before `done`; optional AI commentary (default off) may only cite slice values; `_build_user_prompt` backward compatible; default schedule 15:40.

**Research flag**: 需要 `--research-phase`（高） — 复盘默认调度决策（15:40 定案）、历史 as_of probe 语义（分区存在性主闸门）、AI 失败时面板兜底（R8，不纳入）、REV-05 纳入.

**Plans**: 2/3 plans executed

Plans:

- [x] 31-01-PLAN.md — 后端服务: `auction_recap.py` (build_auction_recap 三块 + data_completeness 枚举 + render/slice 纯函数, REV-01/02/03) + test_auction_recap.py
- [x] 31-02-PLAN.md — 后端集成: recap_market_stream 面板 delta + `_build_user_prompt` 可选参 + 点评开关 (preferences + settings PUT) + 调度默认 15:40 + Review.tsx:105 字面量 (REV-04) + test_market_recap_delta.py
- [ ] 31-03-PLAN.md — REV-05 端点 + 守卫: `GET /api/market-recap/auction` + main.py 注册 + test_auction_recap_guard.py (6 项 POOL-03) + test_auction_recap_endpoint.py + docs/features.md

## Progress

**Execution Order:**
Phases execute in numeric order: 28 → 29 → 30 → 31

| Phase | Requirements | Status |
|-------|-------------|--------|
| 28. 概念板块 PIT | CONCEPT-01..07 | Complete    |
| 29. 竞价策略历史验证 | BT-01..06 | Complete    |
| 30. 盘前监控告警 | MON-01..07 | Complete    |
| 31. 竞价复盘 | REV-01..05 | In Progress|

---
*Last updated: 2026-08-06 — v2.2 milestone started; research synthesized (4 domains → 4 phases); requirements defined*
