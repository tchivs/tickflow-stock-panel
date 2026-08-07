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

### v2.5 诚实加固与本机数据源接入 — planning

五 phase（40-44）研究确认（`research/v2.5-honesty-local-source/SUMMARY.md`，confidence HIGH）：本机 stockdb **无竞价端点**（openapi 41 路径零 auction）→ 竞价源仍受 xyz 配额窗约束，FA-04 不立即解锁，诚实声明统计口径路径；SDK 需 Python ≥3.12（PEP 695，3.11 实测 SyntaxError）→ 通道形态 = `local_stockdb` HTTP 适配器，**零新增运行时依赖**；日K+复权（600519=4024 行）与 T-day 竞价窗口（09:25 撮合行 price×vol 对账闭合）可用，分钟 09:30 bar = 集合竞价统计 → 5537 标的 ≈46min 历史统计路径；403-vs-真空吞错链与 fail-closed 零 emit 为两处真实诚实性缺口；双源归一化（symbol/单位/时区）为头号风险 → 适配器单点归一化 + 契约测试锁死。顺序：LOCAL 通道 → HON 诚实修复（可并行）→ MIN 扩湖（依赖通道）→ SDC sidecar（独立可并行）→ DEP 部署日（依赖 40-43 全就绪）。延续零新增运行时依赖、诚实 provenance、POOL-03 零执行权与 Watchlist.tsx 零触碰。

## Phases

**Phase Numbering:**

- v2.3 ended at Phase 35; v2.4 continued at Phases 36-39; v2.5 continues at Phase 40 (`phase_naming: sequential`)

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
- [x] **Phase 39: 部署验证与残留 (Deploy Verification & Residue)** - D8 deploy-recipe preflight + checklist refresh + honest gap summary + observation plan — DV-01..04 (planned) (completed 2026-08-07)
- [x] **Phase 40: stockdb 本地通道接入 (Local Source Channel)** - HTTP 适配器 `local_stockdb` + 配置注册 + 归一化契约 + 日K/分钟旁路 — LOCAL-01..04 (completed 2026-08-07)
- [x] **Phase 41: 诚实性修复 (Honesty Fixes)** - `source_blocked` 三态化 + fail-closed 终态 emit — HON-01..02 (completed 2026-08-07)
- [x] **Phase 42: 分钟湖扩湖 (Minute Lake Expansion)** - backfill-minute 全量扩湖 + 历史竞价统计路径 + 诚实标注 — MIN-01..03 (completed 2026-08-07)
- [x] **Phase 43: T-day 竞价采集 sidecar (T-Day Auction Capture)** - 盘中逐秒快照 + 09:25 撮合行采集 + T-day 累积 + 诚实门 — SDC-01..03 (completed 2026-08-07)
- [ ] **Phase 44: 部署日执行面 (Deploy-Day Execution)** - 凭证/连通性前置 + 200-body 验证 + D1..D8 runbook 脚本化 + 3018 rebuild — DEP-01..04

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

### Phase 40: stockdb 本地通道接入 (Local Source Channel)

**Goal**: The local stockdb service (:8000) becomes a managed data-source channel — a `local_stockdb` HTTP adapter (zero new runtime deps, mirroring FreeStockDBProvider's httpx pattern) honestly declaring `ProviderCapabilities(auction=False)`, registered at the daily/minute chain-head with configurable position, normalizing symbol/unit/timezone at a single point (contract-locked against partition-key split and 100× volume distortion), with daily/minute bypass flowing through the existing `kline_sync` write path under the existing dual-source partition guards.
**Depends on**: Nothing (first phase); research `v2.5-honesty-local-source/SUMMARY.md` (HTTP-adapter form locked — SDK needs Python ≥3.12 / PEP 695, AQ runtime 3.11)
**Requirements**: LOCAL-01..04
**Success Criteria** (what must be TRUE):

  1. `_get_provider("local_stockdb")` resolves a lazy singleton; adapter declares `auction=False` honestly and never enters the auction_probe chain.
  2. `local_stockdb_url` (默认 `http://127.0.0.1:8000`) + `local_stockdb_api_key` (env 注入, 不入 git) configured; all requests send X-API-Key header-only (禁 URL 传参), `sleep_between_batches` aligns to server rate tiers (quotes 300/min, daily/minute/intraday 120/min, ticks 60/min), 429 honored with Retry-After.
  3. Normalization contract tests lock the three divergences — `SH600519→600519.SH`, volume 恒等 ×1 (实测 stockdb volume_hand 手 == 湖内手; 契约锁死量级不漂移, 绝不 ×100), unified timezone (剥 aware→naive, 镜像 `_normalize_daily`) — so 同股双键/100×量失真/时区漂移 never occur; lake writes go only through the existing write path (merge-upsert idempotent + atomic rename).
  4. daily/minute bypass: chain-head gap-merge consumes the local channel via existing `kline_sync` write path; dual-source guards hold (单源选择 + run-slot 互斥 + 幂等写); channel identity lands in ledger/终态 dict (湖无 provenance 列 — 铁律).
  5. Zero new runtime dependencies (httpx/pydantic only); hermetic + live smoke pass.

**Research flag**: 需 `--research-phase` — 适配器 symbol/单位/时区映射细节 UNKNOWN（须 live probe 定稿）；Docker 构建上下文不含 `../stockdb` 的部署形态；SDK 修订号锚定 (P6 版本锚纪律)。
**Plans**: 0/3 plans executed

Plans:

- [x] 40-01-PLAN.md — 契约先行: 冻结夹具 + 三差异/错误/限频契约测试 + stockdb_provider.py 适配器本体 (LOCAL-01, LOCAL-03)
- [x] 40-02-PLAN.md — 注册: config 键 + chain 链首/分支/单例/health + 白名单 + settings builtin + 注册回归 (LOCAL-02)
- [x] 40-03-PLAN.md — 集成: 链 gap-merge + TestClient + 写路径冒烟 + AST 守卫改形 + 全量回归 (LOCAL-04)

### Phase 41: 诚实性修复 (Honesty Fixes)

**Goal**: The two recorded honesty gaps (36-02/36-03 事故模式) are closed — upstream 403/配额窗 policy-blocks become a distinguishable `source_blocked` state (typed signal or reason-carrying empty frame, never collapsed into `empty_response`), and every fail-closed early return in auction backfill emits per-symbol terminal events so batch progress never freezes or misreports (cancel = `cancelled`/实际 pct, 绝不 `done`/100).
**Depends on**: 无硬依赖 (与 Phase 40 互相独立、可并行；按顺序排于 40 后)
**Requirements**: HON-01..02
**Success Criteria** (what must be TRUE):

  1. xyz provider classifies HTTP 403/配额窗 markers as policy-block signals (typed exception or reason-carrying empty frame); other network errors keep the「空帧不抛」contract (test_xyz_provider.py:126-137 保持绿).
  2. Ledger gains third reason `"source_blocked"` (两键形状 {symbol,reason} 不变, 与 `empty_response`/`str(e)[:200]` 互斥); `auction_probe` preflight 遇 policy-block → verdict `fail_closed` + detail `"source_blocked"`; R1 重试只对可重试态生效.
  3. All fail-closed early returns in `auction_backfill.py` (行 200/224/228/266/268) emit terminal events (每 symbol 一行, 含 reason); cancel path emits independent `cancelled` stage with actual pct — never `done`/100.
  4. `scripts/auction_backfill.py` CLI streams per-symbol progress to stderr (现零进度输出); regression lock: 全空帧批量 → 每 symbol 有进度行 + 终态 failed 计数正确.

**Research flag**: 无需 `--research-phase` — 三态化 + 台账第三类 reason + emit 补全均为既有代码模式的小幅扩展，证据锚点与行号已齐（xyz_provider.py:189-198/228-250、auction_backfill.py:200/224/228/266/268、verify_auction_backfill.py:187-217）。仅 xyz 403 真实响应体结构 UNKNOWN（2h 窗复现时回填定稿）。
**Plans**: 0/2 plans executed

Plans:

- [x] 41-01-PLAN.md — HON-01: xyz 三态化 (SourceBlockedError) + 台账第三类 reason + probe verdict + verify 区分门 (wave 1)
- [x] 41-02-PLAN.md — HON-02: fail-closed 五路径终态 emit + 取消独立 cancelled stage + CLI stderr + 回归锁 (wave 2)

### Phase 42: 分钟湖扩湖 (Minute Lake Expansion)

**Goal**: The minute lake expands from 16 sparse files to full-universe coverage (~5537 symbols, ≈46min measured pace at 120/min rate alignment) via the stockdb `backfill-minute` channel, unlocking the historical auction statistics path — the 09:30 bar (集合竞价统计) feeds the auction coverage report as an independent, honestly-labeled statistical caliber (never tick-by-tick, never into the canonical auction lake).
**Depends on**: Phase 40 (stockdb 通道, backfill-minute 源)
**Requirements**: MIN-01..03
**Success Criteria** (what must be TRUE):

  1. `backfill-minute` via the stockdb channel populates `kline_minute` partitions for ~5537 标的 at ≈46min total (120/min 限频对齐); incremental re-runs are idempotent on covered dates.
  2. Historical auction statistics path: minute 09:30 bar (量/额, 集合竞价统计口径) enters the auction coverage report as an independent caliber — 双口径并列报告, 绝不算逐笔.
  3. FA-04/RC-02 统计口径解锁门: coverage ≥0.94 或诚实 partial, 双口径并列报告 (统计口径绝不算逐笔).
  4. 09:30 bar 标注「集合竞价统计」非逐笔; canonical 竞价湖只收 09:25 撮合行 (09:15-09:24 委托统计绝不入湖); T-21-01 分钟截断语义不回归 (evaluation_time 截断保持).

**Research flag**: 需 `--research-phase` — Tushare stk_mins 接入细节与 09:30 bar 统计口径落地待调研 (5537 标的 ≈46min 为研究实测估算路径)。
**Plans**: TBD

### Phase 43: T-day 竞价采集 sidecar (T-Day Auction Capture)

**Goal**: A live-window sidecar (independent script + intraday cron) captures 09:15-09:25 per-second snapshots and the 09:25 撮合行 into staging (tick 湖/独立目录, never canonical 湖 — 虚拟量非成交), accumulating real auction columns (auction_volume/amount/price + num_trades metadata) day by day with live reconciliation closed (09:25 price×vol == intraday 09:30 bar amt) and fail-closed honesty gates (当日采集失败 → 无当日分区, 不伪造).
**Depends on**: 无硬依赖 (独立于 Phase 40-42、可并行；按顺序排于 42 后)
**Requirements**: SDC-01..03
**Success Criteria** (what must be TRUE):

  1. 09:15-09:25 逐秒快照 + 09:25 撮合行定时采集 (独立脚本 + 盘中 cron 窗口) 落 staging (tick 湖/独立目录); canonical 竞价湖零污染 (虚拟量非成交).
  2. Live 对账闭合: 09:25 撮合行 price×vol == intraday 09:30 bar amt (研究实测锚点 17300×1308.66=22,639,818).
  3. T-day 逐日累积真实竞价列 (auction_volume/amount/price, 多 num_trades 元数据); DATA-06 派生输入 (unmatched_volume/virtual_price) 语义经 probe 确认后映射 (不猜测).
  4. 诚实门: 当日采集失败 → 无当日分区 (fail-closed, 不伪造); sidecar 状态可观测 (台账/告警, 09:26 后缺失可告).

**Research flag**: 无需 `--research-phase` — 研究已 live 实测锚定 (fetch-on-miss 单次 GET 全窗口 / 09:25 撮合行 1308.66·173手·120笔 / 对账闭合 22,639,818 / 3s 源粒度 A1 / 池 ≤200 A2; DATA-06 probe 结论: unmatched_volume 不可得 → 诚实缺列, virtual_price 可映射 + kline_daily.open 1e-6 交叉验证)。
**Plans**: 3 plans

Plans:

- [x] 43-01-PLAN.md — staging 契约 + 采集驱动 (get_ticks + fetch-on-miss + 完整性校验 + 三重对账 + 池 ≤200 白名单) (SDC-01)
- [x] 43-02-PLAN.md — T-day 累积 + canonical 转化 (仅 09:25 撮合行升湖 + 单位映射 + DATA-06 映射/交叉验证) (SDC-02)
- [x] 43-03-PLAN.md — 诚实门 (台账 + 告警 + 交易日判定) + sidecar 三 job 调度 + 文档 (SDC-03)

### Phase 44: 部署日执行面 (Deploy-Day Execution)

**Goal**: Deploy day executes cleanly against a verified system — stockdb 凭证/连通性 preflight green (容器内 loopback 或 host 网络/网关实测判定), 3018 容器对齐检查 (4 运行时文件 md5 vs HEAD), 3 新端点 (backfill/validation/backtest) auth-gated 200-body 脚本化验证 (不再只验 401 门), D1..D8 观测窗口逐项可执行 (分钟点亮门 = 15:30 后分区存在 && auction_intraday_confirm 非空, 非盘中误判), 3018 rebuild 配方落地 (build 66s + boot 18s 预检 + root-owned 卷修复 + 替换流程文档化).
**Depends on**: Phase 40-43 (全部功能就绪)
**Requirements**: DEP-01..04
**Success Criteria** (what must be TRUE):

  1. 凭证/连通性前置: stockdb key 配置 + 容器内 127.0.0.1:8000 连通性验证 (loopback 不通 → host 网络或网关方案, 实测判定); 3018 容器对齐检查完成 (4 运行时文件 md5 vs HEAD).
  2. 3 新端点 (backfill/validation/backtest) 200-body 验证脚本化: login cookie → 请求 → body 键形状断言 (镜像空态契约 `{available:false}`), 不再只验 401 门.
  3. D1..D8 runbook 每项可执行: 09:26 premarket / 15:30 EOD+池持久化 / 15:40 recap / D7 探针周终; 分钟点亮门 = 15:30 后 `kline_minute/date={T}` 分区存在 && `auction_intraday_confirm` 非空, 非盘中误判.
  4. 3018 rebuild 对齐: 重建配方落地 (预检验证 build 66s + boot 18s) + 数据卷/权限检查 (root-owned 修复) + 旧容器替换流程文档化.

**Research flag**: 需 `--research-phase` — 部署日 runbook 需对照真实容器/卷状态细化 (3018 容器 root-owned 处置、compose 凭证注入方式、loopback 不通时 host 网络/网关实测判定); 若需 `uv pip install -e --no-deps` 进镜像, 首次构建 build isolation 需网络调研。
**Plans**: 3 plans

Plans:

- [ ] 44-01-PLAN.md — 凭证/连通性前置: env 方案 (.env.example 网关+key 来源) + deploy_check_connectivity.sh (三态探测/md5 对齐/401 门) (DEP-01)
- [ ] 44-02-PLAN.md — 200-body 验证脚本: deploy_verify_endpoints.py (401 先验→login→3 端点键断言→job 轮询 W-5) (DEP-02)
- [ ] 44-03-PLAN.md — D1..D8 runbook + rebuild 配方: deploy_day_runbook.sh + deploy_rebuild.sh + deploy-verification.md v2.5 节 (DEP-03, DEP-04)

## Progress

**Execution Order:**
Phases execute in numeric order: 36 → 37 → 38 → 39 (37 depends on 36's lake coverage; 38/39 independent)

| Phase | Requirements | Status |
|-------|-------------|--------|
| 36. 全量竞价回填 | FA-01..06 | Complete    |
| 37. 全量真列回测重跑 | RC-01..04 | Complete    |
| 38. 分钟确认接线 BT-10 | MN-01..04 | Complete    |
| 39. 部署验证与残留 | DV-01..04 | Complete    |

**v2.5 Execution Order:**
Phases execute in numeric order: 40 → 41 → 42 → 43 → 44 (41 与 40 互相独立、可并行; 42 依赖 40 的 stockdb 通道; 43 独立可并行; 44 依赖 40-43 全部就绪)

| Phase | Requirements | Status |
|-------|-------------|--------|
| 40. stockdb 本地通道接入 | LOCAL-01..04 | Not started |
| 41. 诚实性修复 | HON-01..02 | Not started |
| 42. 分钟湖扩湖 | MIN-01..03 | Not started |
| 43. T-day 竞价采集 sidecar | SDC-01..03 | Not started |
| 44. 部署日执行面 | DEP-01..04 | Not started |

---
*Last updated: 2026-08-07 — v2.5 roadmap created (5 phases 40-44); 16/16 requirements mapped*
