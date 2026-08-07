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

### v2.3 数据纵深解锁 — shipped 2026-08-06

四域交付：竞价历史回填（xyz MCP 实测 248 交易日真实集合竞价 → kline_auction 0→248 分区、BT-07 全量回测解锁、真实冒烟 496 行幂等/取消）、股池回填 OQ-1（8 日/13s 实测锚点 + 幂等 + PIT 联动）、竞价回测解锁（329,087 行/4s 实跑 + 确定性 run_id + 只读面）、遗留补全（R13 回归锁死、CHART-04 立场、8 项部署清单、WATCH-04 批量、OQ-3 smoke）——21/21 需求，后端 97+96+57+21 passed，43/43 e2e，零新增依赖。Archived: `.planning/milestones/v2.3-phases/`, `v2.3-REQUIREMENTS.md`, `v2.3-ROADMAP.md`, `v2.3-MILESTONE-AUDIT.md`.

### v2.4 全量数据解锁 — planning

三域研究确认（`research/v2.4-full-universe/SUMMARY.md`）：全量竞价回填 **FEASIBLE**（实测 0.96s/请求、3.5-5.5h、写缝 1.15s/标的、全湖 ~13 MB；BJ 333 上游恒空 → 覆盖上限 94.0% 诚实台账；600s 自杀陷阱与 resume/CLI 缺口需修）→ kline_auction 2-symbol → 5204-symbol 全量解锁；全量真列回测重跑（compute 2.3s 实测，run_id 指纹缺湖覆盖摘要必须补）；BT-10 分钟确认接线（纯代码增量，空湖行为保持）；部署验证残留（D8 陈旧容器实测 + build+boot 预检）——全部零新增运行时依赖，延续诚实 provenance 与 POOL-03 零执行权。

## Phases

**Phase Numbering:**

- v2.3 ended at Phase 35; v2.4 continues at Phase 36 (`phase_naming: sequential`)

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
- [x] **Phase 32: 竞价历史回填 (Auction History Backfill)** - xyz auction capability + backfill job + honest gates + idempotent atomic writes — AQ-01..06 (completed 2026-08-06)
- [x] **Phase 33: 股池回填 OQ-1 (Pool Backfill)** - Sandbox subset backfill verification + full-248 operator runbook + PIT interplay — PB-01..04 (completed 2026-08-06)
- [x] **Phase 34: 竞价回测解锁 (BT-07 Full Auction Backtest)** - Real-branch activation + 248-day full backtest + backtest_results persistence — BT-07..10 (completed 2026-08-06)
- [x] **Phase 35: 遗留补全与部署验证 (Legacy Completion & Deploy Verification)** - R13 regression + CHART-04 stance + deploy checklist + P2 extensions — LG-01..05 (completed 2026-08-06)
- [x] **Phase 36: 全量竞价回填 (Full-Universe Auction Backfill)** - Long-job timeout exemption + resume/only-missing + operator CLI + sandbox full 5537-symbol run + BJ honest ceiling — FA-01..06 (planned) (completed 2026-08-07)
- [x] **Phase 37: 全量真列回测重跑 (Full Real-Column Backtest Rerun)** - run_id lake-coverage fingerprint + full-market real-column rerun + honest coverage reporting — RC-01..04 (planned) (completed 2026-08-07)
- [x] **Phase 38: 分钟确认接线 BT-10 (Minute Confirm Wiring)** - minute loader factory + dual construction-site wiring + hermetic tests + doc sync — MN-01..04 (planned) (completed 2026-08-07)
- [ ] **Phase 39: 部署验证与残留 (Deploy Verification & Residue)** - D8 deploy-recipe preflight + checklist refresh + honest gap summary + observation plan — DV-01..04 (planned)

## Phase Details

### Phase 36: 全量竞价回填 (Full-Universe Auction Backfill)

**Goal**: The `kline_auction` lake transitions from 2-symbol smoke coverage (0.04%) to the full SZ/SH universe (~5204 symbols × 248 days ≈ 1.29M rows) via a long-running (3.5-5.5h, measured) sandbox detached CLI run — with the 600s job self-kill trap fixed (per-job `timeout_s`), resume/`only_missing` skip, an operator CLI (`scripts/auction_backfill.py`), and the BJ 333-symbol upstream gap honestly ledged (coverage ceiling 94.0%).
**Depends on**: Phase 32 (write seam + job machinery + probe); research `AUCTION-FULL-BACKFILL.md` (measured 0.96s/req, 1.15s/symbol write, ext2fs, 13MB lake)
**Requirements**: FA-01..06 (FA-06 P2)
**Success Criteria** (what must be TRUE):

  1. `job_store.create(timeout_s=…)` + `reap_stale` honors it; backfill API sets 21600 — a >10min backfill job is not reaped (regression test).
  2. `only_missing=True` skips fully-covered symbols (pre-scan over aligned dates); API body accepts it; partial coverage re-fetched; merge-upsert idempotency preserved.
  3. `scripts/auction_backfill.py` CLI runs detached (no job_store/reap/single-flight), progress stdout, terminal dict + `failed_symbols` ledger to JSON.
  4. Sandbox full run: backfilled ≥5200 symbols, rows ≈1.29M, 248 partitions, no `.tmp` residue; cross-check virtual_price == open on ≥3 dates × ≥3 symbols; `--only-missing` top-up stable.
  5. BJ 333 symbols in `failed_symbols` as `empty_response` (reason honest, never fabricated); coverage reported ≤94.0% (never 100%).
  6. EOD interplay: re-writing covered symbols is an idempotent no-op (row count unchanged); discipline note re: EOD window.

**Research flag**: 无需 `--research-phase` — 研究已实测校准 (pilot 20 请求 mean 0.96s 0×429; BJ 9 请求 5 格式全失败; 写路径 0.67→1.15s/标的; 3.5-5.5h 含裕量)。

**Plans**: 0/3 plans executed

Plans:

- (planned 36-01/02/03)

### Phase 37: 全量真列回测重跑 (Full Real-Column Backtest Rerun)

**Goal**: After Phase 36 fills the lake, the full-market real-column backtest rerun becomes meaningful — `run_id` fingerprints gain a lake-coverage digest (without it, a post-backfill rerun returns `reused=True` and silently keeps stale data — measured), the CLI full-market 248-day run flips `coverage.symbols` 0.036% → ≥0.94 and grows gated-strategy real hits 12 → thousands+ (EOD 329,087 and intraday_confirm 52,591 unchanged), with honest partial framing and BT-04 forward semantics untouched.
**Depends on**: Phase 36 (lake coverage); Phase 34 (`run_full_backtest` + `_compute_run_id` + persistence + CLI)
**Requirements**: RC-01..04 (RC-04 P2)
**Success Criteria** (what must be TRUE):

  1. Same inputs + different lake coverage → different run_id; same lake → idempotent reused (test extends `test_full_backtest_deterministic_run_id_idempotent`).
  2. Full-market rerun: coverage ratio ≥0.94; gated strategies real hits grow (12 → thousands+); EOD 329,087 unchanged; intraday_confirm 52,591 unchanged; runtime ≤10s measured.
  3. Honest reporting: `rows_present < expected` partial framing; coverage = backfilled/5537; intraday_confirm annotated (branch=real, no auction-column consumption); verifier forward spot-check to 9dp.
  4. Persistence + read-only surface at scale; `--force` escape hatch; AST guard E3 green.

**Research flag**: 无需 `--research-phase` — 研究实测全市场 9 策略 compute 2.3s (381,690 行)、指纹缺口实测 (reused=True 静默)、248 分区全量读 0.31s。

**Plans**: 0/3 plans executed

Plans:

- (planned 37-01/02/03)

### Phase 38: 分钟确认接线 BT-10 (Minute Confirm Wiring)

**Goal**: The minute-confirm seam (`engine.py:154,373-392`) gets its production loader — a `make_minute_loader(data_dir)` factory reads `kline_minute/date={as_of}/part.parquet`, wired at both construction sites (`main.py:562-565` + `advanced/governed_runner.py:63-66`); empty-lake behavior stays byte-identical (fail-closed), fixture tests prove partition-present lighting with ≤09:45 single-point truncation; research/validation reports keep `minute_confirm='not_applied'`.
**Depends on**: v2.1 STRAT-06/09 seam (T-21-01); kline_sync canonical minute columns
**Requirements**: MN-01..04 (MN-04 P2)
**Success Criteria** (what must be TRUE):

  1. Factory reads canonical columns, filters candidates, sorts; missing partition → empty frame.
  2. Both construction sites wired; empty-lake behavior identical to today (required → empty result; optional → confirm skipped).
  3. Hermetic tests: empty-lake keep; partition-present lights confirm with truncation; loader read-only; reports keep `not_applied`.
  4. docs/features.md + docs/deploy-verification.md one-line status sync (lighting = live-day lake writes, not intraday).

**Research flag**: 无需 `--research-phase` — 研究已核验 seam 完整 + 双接线点 + 既有 hermetic 测试锚点 (test_auction_strategy_family.py:31-39/59-62/146-162/199-225, test_auction_strategy_family_p2.py:222-273, test_minute_sync_verify.py)。

**Plans**: 0/3 plans executed

Plans:

- (planned 38-01/02/03)

### Phase 39: 部署验证与残留 (Deploy Verification & Residue)

**Goal**: Deploy-side residue is closed from the sandbox — a `docker build` from repo HEAD + fresh-container boot smoke on a scratch port/temp data proves the rebuild recipe (D8 preflight; the running stale 3018 container is root-owned and untouchable), the deploy checklist gains v2.4 measured facts, and the honest gap summary + post-deploy observation-window plan (D1..D8 calendar) are consolidated for the operator.
**Depends on**: Phase 35 (docs/deploy-verification.md); research `DEPLOY-MINUTE-LEGACY.md` (container md5 evidence)
**Requirements**: DV-01..04 (DV-03/04 P2)
**Success Criteria** (what must be TRUE):

  1. `docker build` HEAD succeeds; fresh container boots on scratch port with temp data dir; new endpoints respond; md5/endpoint parity vs stale 3018 documented.
  2. docs/deploy-verification.md refreshed with v2.4 measured facts; research↔docs parity maintained.
  3. Honest gap summary (premarket double-gate / BJ / minute live-day / AI-key) with evidence + owner + trigger.
  4. D1..D8 post-deploy observation-window plan (sequencing D4 after D1, D5 after D2, D7 ≥5th trading day).

**Research flag**: 无需 `--research-phase` — 研究已实测容器 stale 证据 (4 文件 md5 DIFFER, image 08-04 vs HEAD 08-07) + 沙箱预检配方可行 (Dockerfile + compose 存在, image 2.59GB 本地)。

**Plans**: 0/3 plans executed

Plans:

- (planned 39-01/02/03)

## Progress

**Execution Order:**
Phases execute in numeric order: 36 → 37 → 38 → 39 (37 depends on 36's lake coverage; 38/39 independent)

| Phase | Requirements | Status |
|-------|-------------|--------|
| 36. 全量竞价回填 | FA-01..06 | Complete    |
| 37. 全量真列回测重跑 | RC-01..04 | Complete    |
| 38. 分钟确认接线 BT-10 | MN-01..04 | Complete    |
| 39. 部署验证与残留 | DV-01..04 | Planned    |

---
*Last updated: 2026-08-07 — v2.4 milestone started; research synthesized (3 domains → 4 phases); requirements defined*
