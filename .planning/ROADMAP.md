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

### v2.2 决策闭环与历史纵深 — shipped 2026-08-06

四领域交付：概念板块 PIT（前向按日归档 + as_of 三态归属 + 总览/RPS 共享 seam）、竞价策略只读信号质量报告（data_gate 诚实空态）、盘前监控告警（preopen 规则类型 + 09:26 尾段接线）、确定性竞价复盘面板（15:40 调度 + 可选 AI 点评默认关）——后端全量 1686 passed + 2 skipped，零新增运行时依赖。Archived: `.planning/milestones/v2.2-phases/`, `v2.2-REQUIREMENTS.md`, `v2.2-ROADMAP.md`, `v2.2-MILESTONE-AUDIT.md`.

### v2.3 数据纵深解锁 — planning

三域研究确认（`research/v2.3-data-depth/SUMMARY.md`）：竞价历史回填 **OPEN**（xyz MCP `stockdb_get_call_auction` 实测 248 交易日真实集合竞价，与日 K open 交叉验证）→ kline_auction 湖从 0 对齐 248 日 + BT-07 全量回测解锁；股池回填 OQ-1（既有 backfill 机械沙箱子集验证 + 部署全量 runbook）；遗留补全（R13 回归测试、CHART-04 立场、8 项部署验证清单）+ 分钟历史回填 **CLOSED** 正式 defer——全部零新增运行时依赖，延续诚实 provenance 与 POOL-03 零执行权。

## Phases

**Phase Numbering:**

- v2.2 ended at Phase 31; v2.3 continues at Phase 32 (`phase_naming: sequential`)

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
- [x] **Phase 31: 竞价复盘 (Auction Recap)** - Deterministic auction recap panel in the post-close recap + optional AI commentary — REV-01..05 (completed 2026-08-06)
- [x] **Phase 32: 竞价历史回填 (Auction History Backfill)** - xyz auction capability + backfill job + honest gates + idempotent atomic writes — AQ-01..06 (planned) (completed 2026-08-06)
- [ ] **Phase 33: 股池回填 OQ-1 (Pool Backfill)** - Sandbox subset backfill verification + full-248 operator runbook + PIT interplay — PB-01..04 (planned)
- [ ] **Phase 34: 竞价回测解锁 (BT-07 Full Auction Backtest)** - Real-branch activation + 248-day full backtest + backtest_results persistence — BT-07..10 (planned)
- [ ] **Phase 35: 遗留补全与部署验证 (Legacy Completion & Deploy Verification)** - R13 regression + CHART-04 stance + deploy checklist + P2 extensions — LG-01..05 (planned)

## Phase Details

### Phase 32: 竞价历史回填 (Auction History Backfill)

**Goal**: The `kline_auction` lake transitions from 0 partitions to daily-aligned real auction data — the xyz provider declares auction capability (auto-discovering into `auction_probe`, unblocking the live EOD path), and a new `auction_backfill` job pulls the full 248-day history (single-symbol requests, rate-limited, cancelable) writing through the existing `auction_sync` atomic seam with honest gates (kline_daily-aligned dates only, per-symbol failure recorded, source-down fail-closed).
**Depends on**: v2.2 completion (Phase 31); `auction_sync` write seam + `auction_probe._default_sources` + xyz MCP endpoint (verified 2026-08-06)
**Requirements**: AQ-01..06 (AQ-06 P2)
**Success Criteria** (what must be TRUE):

  1. `xyz_provider.get_auction` maps `stockdb_get_call_auction` rows to canonical columns (`.SZ/.SH` suffix); probe resolves `available`; EOD `sync_and_persist_auction` path unblocks.
  2. `POST /api/kline/auction/backfill` runs single-flight with job_store progress + cooperative cancel; subset ranges supported.
  3. Only dates with existing `kline_daily` partitions are written; per-symbol failures recorded and skipped; source unreachable → 0 writes + fail-closed record.
  4. Writes are idempotent (merge-upsert) and atomic (.tmp rename); `auction_unmatched_volume` honestly absent; cross-check: sampled `auction_virtual_price` == `kline_daily.open` on ≥3 dates.

**Research flag**: 需要 `--research-phase`（中） — xyz 速率上限未压力测试（~1.6s/请求、单 symbol 已实证）、2010 至今完整覆盖（2024 抽验过）、symbol 全集来源与 `.SZ/.SH` 后缀映射、job 存储进度格式。

**Plans**: 0/3 plans executed

Plans:

- (planned 32-01/02/03)

### Phase 33: 股池回填 OQ-1 (Pool Backfill)

**Goal**: The never-executed backfill machinery (`POST /api/pipeline/backfill` → `run_pool_backfill` → `persist_point_snapshot(origin='backfill')`) is exercised and verified — a sandbox subset (5-10 gap days) proves provenance/idempotency/cache-integrity/rendering end to end, and a full-248 operator runbook makes the deploy-side complete run deterministic; PIT as_of attribution rides along honestly.
**Depends on**: v2.1 completion (Phase 24 machinery); enriched history (248 days); Phase 28 read-side as_of
**Requirements**: PB-01..04 (PB-03 P2)
**Success Criteria** (what must be TRUE):

  1. Subset backfill produces `snapshot_origin='backfill'` partitions; `strategy_cache` byte-identical (D2); re-run skips already-done dates (idempotent).
  2. `/pool/history` renders backfilled dates; concept attribution resolves with honest `current_snapshot` fallback where `ext_history` partitions are missing.
  3. Operator runbook covers full-248 execution (limits, progress, cancel, expected runtime/storage, failure handling).
  4. `premarket_results` honest gap documented (deploy + live-data gated), never fabricated.

**Research flag**: 需要 `--research-phase`（低） — 运行时实测（20-120min 估计）、磁盘余量、子集天数选择。

**Plans**: 0/3 plans executed

Plans:

- (planned 33-01/02/03)

### Phase 34: 竞价回测解锁 (BT-07 Full Auction Backtest)

**Goal**: With the auction lake aligned (Phase 32), the v2.2-deferred full backtest unlocks — the validation report's real branch activates (`data_gate:"available"`), and the 9 auction/pre-market strategies run the 248-day real-column panel with mutually-exclusive real/derived/eod branches, BT-04 forward semantics, honest coverage, and results persisted to `backtest_results` with a read-only query surface.
**Depends on**: Phase 32 (lake aligned); Phase 29 (`attach_auction_columns_range` + validation service); Phase 28 (concept as_of)
**Requirements**: BT-07..10 (BT-10 P2)
**Success Criteria** (what must be TRUE):

  1. `GET /api/research/auction/validation` reports `data_gate:"available"` with real-column rows for auction strategies (never derived-downgraded).
  2. Full backtest covers the aligned 248-day panel; branch labels mutually exclusive; forward outcomes per BT-04 (T-open entry, next-day open/close, open_gap_outcome, `n_missing_outcomes` counted never filled).
  3. Results persist to `backtest_results` (origin/params/per-date); query surface read-only; AST guard (E3) maintained.
  4. Minute-limited confirm dimensions honestly annotated (BT-10).

**Research flag**: 需要 `--research-phase`（中） — `BACKTEST_MAX_SERVER_DAYS=186` 与 248 天区间冲突的处理（窗口分段 or 上限复核）、全量 9 策略 × 248 日运行时、backtest_results 落盘 schema（现状 0 分区）。

**Plans**: 0/3 plans executed

Plans:

- (planned 34-01/02/03)

### Phase 35: 遗留补全与部署验证 (Legacy Completion & Deploy Verification)

**Goal**: v2.1/v2.2 遗留项收口与部署验证成册 — R13 缓存语义从「已修复代码」升级为「回归测试锁死」、CHART-04 估算立场文档定案、8 项部署验证清单成为运维手册；P2 扩展（WATCH-04 批量自选、OQ-3 探针 smoke）随带。
**Depends on**: v2.2 completion; daily_pipeline 15:30 refresh_cache-in-finally (already fixed, ce5c705)
**Requirements**: LG-01..05 (LG-04/05 P2)
**Success Criteria** (what must be TRUE):

  1. R13 regression test passes deterministically (15:30/run-now → repo latest-day asset EOD close; 15:40 recap change_pct from EOD; pre-EOD rule honored).
  2. CHART-04 stance doc published (估算 labels standing; tier-2 re-eval gate recorded).
  3. DEPLOY-CHECKLIST covers 8 items with verify-where/pass-criteria/owner/sequencing.
  4. WATCH-04 batch-add e2e green (pure frontend); OQ-3 probe smoke produces drift.jsonl once (offline path); `Watchlist.tsx` untouched.

**Research flag**: 需要 `--research-phase`（低） — R13 测试所需 fixtures（run_now + refresh_cache 模拟）、WATCH-04 勾选交互选型（table 内 checkbox vs 行选择条）。

**Plans**: 0/3 plans executed

Plans:

- (planned 35-01/02/03)

## Progress

**Execution Order:**
Phases execute in numeric order: 32 → 33 → 34 → 35

| Phase | Requirements | Status |
|-------|-------------|--------|
| 32. 竞价历史回填 | AQ-01..06 | Complete    |
| 33. 股池回填 OQ-1 | PB-01..04 | Planned |
| 34. 竞价回测解锁 | BT-07..10 | Planned |
| 35. 遗留补全与部署验证 | LG-01..05 | Planned |

---
*Last updated: 2026-08-06 — v2.3 milestone started; research synthesized (3 domains → 4 phases); requirements defined*
