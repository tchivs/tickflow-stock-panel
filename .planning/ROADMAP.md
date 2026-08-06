# Roadmap: AthenaQuant

## Milestones

### v1.0 MVP — shipped 2026-07-27

### v1.1 Operational Hardening — shipped 2026-07-29

### v1.2 End-to-End Factor Portfolio Pipeline — shipped 2026-08-03

### v1.3 竞价选股引擎 — shipped 2026-08-04

### v2.0 竞价深度与历史股池 — shipped 2026-08-05

Four phases (20-23) delivered probe-gated real auction columns + `kline_auction/date={d}/` lake, six auction/tail strategies (27 builtin total), frozen point snapshots + date navigation + EOD persistence, and the DateNavigator frontend. Archived: `.planning/milestones/v2.0-phases/`, `v2.0-REQUIREMENTS.md`, `v2.0-ROADMAP.md`, `v2.0-MILESTONE-AUDIT.md`.

### v2.1 历史深度与自选联动 — planning

四个领域深化已落地的历史股池与自选能力：逐日全量存档（批量回填 + 诚实 provenance）、自选股与股池联动（纯前端）、历史竞价图 + 派生列复活（条件式）、盘前股池第一档（独立预览 + 诚实降级）——全部零新增运行时依赖，沿 POOL-03 零执行权边界，strategy_cache single-as_of 完整性为跨领域护栏。

## Phases

**Phase Numbering:**

- v2.0 ended at Phase 23; v2.1 continues at Phase 24 (`phase_naming: sequential`)

- [x] **Phase 16: 竞价数据层 (Auction Data)** - Minute-K sync, governed open-gap factor, auction probe — DATA-01..03 (completed 2026-08-04)
- [x] **Phase 17: 竞价策略族 (Auction Strategy Family)** - 竞价多头/盘前强势量化/早盘之星 builtin strategies — STRAT-01..03 (completed 2026-08-04)
- [x] **Phase 18: 股池 Hub (Pool Hub)** - Strategy cards, drill-down, concept filter, 交叉共振 — POOL-01..03 (completed 2026-08-04)
- [x] **Phase 19: 游客/VIP 脱敏 + 前端 (Guest Access & Frontend)** - Server-authoritative masking + pool page — GUEST-01..02 (completed 2026-08-04)
- [x] **Phase 20: 竞价数据层 (Auction Data)** - Probe-gated real auction columns + `kline_auction/date=*/` lake + unmatched proxy — DATA-04..06 (completed 2026-08-05)
- [x] **Phase 21: 竞价策略族 (Auction Strategy Family)** - 极速抢筹/竞价阿尔法/金色两点半/竞价全面/T+1闪电/盘中确认 — STRAT-04..09 (completed 2026-08-05)
- [x] **Phase 22: 股池日期导航 (Pool Hub Date Navigation)** - Frozen point snapshots + dates/as_of endpoints + EOD job — POOL-04..06 (completed 2026-08-05)
- [x] **Phase 23: 前端 (Frontend)** - DateNavigator + auction column drill-down (real vs derived) — FRONT-01..02 (completed 2026-08-05)
- [x] **Phase 24: 逐日全量存档 (Historical Archive)** - User-triggered batch backfill + snapshot_origin provenance + backfill_needed gap signal + cache-pointer pollution fix — HIST-01..04 (completed 2026-08-06)
- [ ] **Phase 25: 自选股联动 (Watchlist Sync)** - Pool drill-down watch stars + 只看自选 filter + shared cache consistency — WATCH-01..04
- [ ] **Phase 26: 历史竞价图 + 派生列复活 (Auction History Chart)** - Read-only auction history API + ECharts chart + lake ingestion preserves delegation-volume columns — CHART-01..03
- [ ] **Phase 27: 盘前股池 (Premarket Pool)** - Scheduled premarket preview job (independent store) + open_gap completion + probe-honest degraded semantics + frontend premarket view — PM-01..04

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

**Plans**: TBD
**Research flag**: standard patterns — 纯前端, 抄 Screener.tsx 先例; 执行前确认用户预存 `Watchlist.tsx` 未改 `QK.watchlist` 契约.

### Phase 26: 历史竞价图 + 派生列复活 (Auction History Chart)

**Goal**: User can view per-symbol historical auction volume/amount trends in the stock drill-down (ECharts, zero new deps) via a read-only aggregate endpoint; the lake ingestion path preserves delegation-volume inputs so the derived 虚拟未匹配金额 column becomes live data instead of absent columns.
**Depends on**: v2.0 completion (Phase 23); `kline_auction` lake
**Requirements**: CHART-01, CHART-02, CHART-03
**Success Criteria** (what must be TRUE):

  1. `GET /api/kline/auction/history?symbol=&days=` returns per-day last-row (09:25 final) aggregates; empty lake returns 200 `available: false` (honest, not 404); GET-only zero execution.
  2. Frontend renders the chart in the stock popup with dual-axis 柱/线, empty state + 09:15–09:25 window annotation, zero new npm deps, `Watchlist.tsx` untouched.
  3. Auction lake canonical schema widens to 4 required + 2 optional delegation-volume columns (backward compatible); the derived `auction_unmatched_amount` branch activates with "估算" annotation intact.

**Plans**: TBD
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

**Plans**: TBD
**Research flag**: 需要 `--research-phase` — open_gap 补算 seam、probe 今日窗口语义、预览存储 schema、调度并发（与 EOD job/维表同步互斥）.

## Progress

**Execution Order:**
Phases execute in numeric order: 24 → 25 → 26 → 27

| Phase | Requirements | Status |
|-------|-------------|--------|
| 24. 逐日全量存档 | HIST-01..04 | Complete |
| 25. 自选股联动 | WATCH-01..04 | Not started |
| 26. 历史竞价图 + 派生列复活 | CHART-01..03 | Not started |
| 27. 盘前股池 | PM-01..04 | Not started |

---
*Last updated: 2026-08-05 — v2.1 milestone started; roadmap created (Phases 24-27)*
