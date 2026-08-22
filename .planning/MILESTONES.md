# Milestones

## v3.2 v3.2 (Shipped: 2026-08-22)

**Phases completed:** 4 phases, 10 plans, 26 tasks

**Key accomplishments:**

- 1. [Rule 1 - Bug] Per-principal ring buffer persistence
- 1. [Rule 1 - Bug] QuoteService WS 广播已在 Plan 01 或先前 session 部分实现
- 1. [Rule 1 - Bug] useWsStream 频道路由不匹配动态频道
- 1. [Rule 3 - Blocking] SSE 端点删除破坏任务启动路径
- Complete
- 设置页 Server酱 SendKey 配置区 (输入 + 保存 + 测试推送) + 监控规则/复盘推送渠道新增 sct 选项, 对称飞书/Telegram 模式
- localStorage 规则存储 + WS quotes 订阅本地评估 + Notification API 弹窗 + toast + 声效 + 5 分钟防抖的端到端 tracer 切片
- 客户端规则 CRUD 面板 + 命中列表 + Notification 权限区, 监控中心页面客户端规则与服务端规则并列 badge 区分
- 1. [Rule 3 - Blocking] Pre-existing test failure in test_notification_delivery.py

---

## v3.0 v3.0 (Shipped: 2026-08-09)

**Phases completed:** 6 phases, 22 plans, 20 tasks

**Key accomplishments:**

- 45-01 (wave 1)
- 45-02 (wave 2)
- 45-03 (wave 3)
- Typed principal-scoped durable run operations with safe projections, explicit lifecycle conflicts, and a complete no-execution module-graph guard.
- 46-01 (wave 1)
- 46-02 (wave 2)
- 46-03 (wave 3)
- 46-deterministic-alpha-factory
- 47-01 (wave 1)
- 47-02 (wave 2)
- 47-03 (wave 2)
- 47-04 (wave 3, final)
- 48-01 · **Wave:** 1 (depends_on: []) · **Requirements:** AF-REQ-11, AF-REQ-14
- 48-02 · **Wave:** 2 (depends_on: [48-01]) · **Requirements:** AF-REQ-12
- 48-03 · **Wave:** 2 (depends_on: [48-01, 48-02]) · **Requirements:** AF-REQ-13, AF-REQ-21
- 48-04 · **Wave:** 3 (depends_on: [48-01, 48-02, 48-03]) · **Requirements:** AF-REQ-21, AF-REQ-26
- 49-01 · **Wave:** 1 (depends_on: []) · **Requirements:** AF-REQ-15 (SC1, SC2 expire/conflict half)
- 49-02 · **Wave:** 2 (depends_on: [49-01]) · **Requirements:** AF-REQ-15 (SC2 concurrent half, SC3), AF-REQ-17 (SC4)
- 50-replay-workbench
- 50-replay-workbench
- 50-replay-workbench
- 50-replay-workbench

---

## v2.5 v2.5 (Shipped: 2026-08-07)

**Phases completed:** 5 phases, 14 plans, 9 tasks

**Key accomplishments:**

- 40-stockdb-local-channel · **Wave:** 01 (契约先行) · **Date:** 2026-08-07
- Phase
- Phase
- 41-honesty-fixes · **Wave:** 01 (HON-01 诚实性修复) · **Date:** 2026-08-07
- 41-honesty-fixes · **Wave:** 02 (HON-02) · **Date:** 2026-08-07
- 42-minute-lake-expansion · **Wave:** 01 (MIN-01 机制: 回填驱动 + 幂等) · **Date:** 2026-08-07
- 42-minute-lake-expansion · **Wave:** 02 (MIN-02) · **Date:** 2026-08-07
- 42-minute-lake-expansion · **Wave:** 03 (MIN-03) · **Date:** 2026-08-07
- 盘中竞价窗口 live 采集: StockDBProvider.get_ticks (fetch-on-miss 单次 GET) + auction_capture 采集驱动 (三重完整性校验 fail-closed → tick_staging 10 列原子写 + manifest) + 池解析 (白名单≤200 默认自选池) + auction_reconcile 三重对账 (22,639,818 闭合)
- 43-tday-auction-sidecar · **Wave:** 02 (SDC-02: T-day 逐日累积 + canonical 转化) · **Date:** 2026-08-07
- 43-tday-auction-sidecar · **Wave:** 03 (SDC-03: 诚实门 + 调度) · **Date:** 2026-08-07
- Phase
- deploy_verify_endpoints.py — 3 新端点 200-body 键形状验证脚本 (python3 stdlib 零新依赖): 401 先验 3/3 → 真实登录 → validation 8 键 / backtest {runs,count}+详情 / backfill fail-closed + job 轮询 W-5 9 键 → JSON 台账 + 退出码, 沙箱 :3020 全流程实测通过
- Executor

---

## v2.4 v2.4 (Shipped: 2026-08-07)

**Phases completed:** 4 phases, 12 plans, 0 tasks

**Key accomplishments:**

- `.planning/phases/36-auction-full-backfill/36-02-PLAN.md`
- Wave
- Phase
- Phase
- Phase

---

## v2.3 v2.3 (Shipped: 2026-08-06)

**Phases completed:** 4 phases, 12 plans, 4 tasks

**Key accomplishments:**

- ExecutorP3201 · **Date:** 2026-08-06 · **Plan:** `.planning/phases/32-auction-backfill/32-01-PLAN.md` · **Wave:** 1
- `.planning/phases/32-auction-backfill/32-02-PLAN.md`
- ExecutorP3203 · **Date:** 2026-08-06 · **Plan:** `.planning/phases/32-auction-backfill/32-03-PLAN.md`
- `.planning/phases/33-pool-backfill/33-01-PLAN.md` · **执行日期:** 2026-08-06 · **执行者:** ExecutorP3301
- `.planning/phases/33-pool-backfill/33-02-PLAN.md` · **执行日期:** 2026-08-06 · **执行者:** ExecutorP3302
- `.planning/phases/33-pool-backfill/33-03-PLAN.md` · **执行日期:** 2026-08-06 · **执行者:** ExecutorP3303
- 34-auction-backtest · **Plan:** 34-01 · **Executor:** ExecutorP3401 · **Date:** 2026-08-06
- 34-auction-backtest · **Plan:** 34-02 · **Executor:** ExecutorP3402 · **Date:** 2026-08-06
- 34-auction-backtest · **Plan:** 34-03 · **Executor:** ExecutorP3403 · **Date:** 2026-08-06
- 35-legacy-completion · **Plan:** 35-01 · **Executor:** ExecutorP3501 · **Date:** 2026-08-06
- `.planning/phases/35-legacy-completion/35-03-PLAN.md` (Task 1 tracer + Task 2 + Task 3)

---

## v2.2 v2.2 (Shipped: 2026-08-06)

**Phases completed:** 4 phases, 12 plans, 34 tasks

**Key accomplishments:**

- 前向逐日概念/行业历史归档模块 (concept_history.capture + read_partition + manifest) + pool_hub as_of 三态归属状态机 + EOD 非致命钩子 + CONCEPT-05 按模块 AST 守卫
- CONCEPT-04/07 前端交付: 股池页 detail header 概念归属诚实徽标 (服务端冻结 concept_attribution 驱动, as_of_snapshot 按日文案 + 概念数据生效日期) + 三态 Playwright e2e + features 文档
- 把 28-01 的 `read_partition` as_of 原语扩展到总览 (_dimension_rank) 与 RPS 矩阵 (_load_concept_map_df), 消除「历史复盘/历史 RPS 仍用当前 ext join → 未标注 drift」缺口; 并为 GET /api/rps/rotation 增加可选 as_of 双校验参数
- BT-02 vectorized range injector `attach_auction_columns_range(df, start, end, repo) -> (df, enabled_dates)` in auction_columns.py: partition-existence history gate (no probe), per-partition symbol dedup, PIT-safe `volume.shift(1).rolling_mean(5, min_samples=1).over("symbol")` ratio proven per-value identical to the single-day path, warmup contract, honest empty states — 14 new tests + 14 regression tests green, single-day code zero-change.
- 只读竞价策略历史验证报告服务 `AuctionValidationService.build_report` 落地: 窗口解析/回夹双字段回显 (D-06, W1 夹 warmup) → warmup 面板装载 → attach_auction_columns_range 注入 → 9 策略枚举 + 互斥 branch (BT-05) → 候选掩码镜像 (backtest/strategy.py:522-570, 绝不 import) → 前瞻统计 (BT-04 全局日历 next-date + 三公式 + n_missing_outcomes) → per_date → 诚实 gate 报告 — 12 服务级测试 + 14 原语回归全绿, 零新依赖、零写、docstring 无禁 token (BT-06 守卫就绪).
- 只读竞价策略历史验证端点落地: `backend/app/api/research_auction.py` (GET `/api/research/auction/validation`, 镜像 auction_history.py 只读范本 + research.py `_bad_request`) + main.py 一行注册 + 独立 POOL-03 AST 守卫文件 (`tests/test_auction_validation.py`, BT-06 6 项) + 端点集成测试 4 项 (空湖 200 全形状 / available 闸门 / 参数矩阵 400/422/空列表/skipped/窗口回夹 / BT-04 经 API 复验) + docs 小节 — 全量回归 248 绿, 零新增依赖, 零写面, frontend/backtest seam 零触碰 (D-05/D-08).
- preopen 规则类型 + 独立只读评估模块 (preopen_eval.py) + 隔离的 evaluate_premarket 入口 + D-03 盘中跳过回归锁, 配套 T1-T10 测试全绿
- 09:26 盘前 job 尾段接入统一告警链 (evaluate_premarket_alerts 持久化优先 → SSE → webhook) + mask_guest_alert 防御性脱敏 + /options preopen 白名单外露 + AST 守卫回归锁, 配套 T11-T20 测试全绿
- api.ts preopen 类型契约 + RuleEditor「盘前异动」规则编辑路径 (5 字段白名单下拉 / truth 隐藏 / open_gap 默认) + Monitor.tsx provisional「盘前·非最终」/ degraded「数据降级」徽标, 配套 5 用例 Playwright e2e + docs; 零新依赖, Watchlist.tsx 零触碰
- 只读竞价复盘装配服务 auction_recap.py — build_auction_recap 三块 (real_auction_activity / open_gap_snapshot / preopen_signal_quality) + data_completeness 枚举 + pre_eod 分钟算术判别 + render/slice 同 dict 纯函数单源, 18 项验收测试全绿
- GET /api/market-recap/auction 独立只读端点落地 — as_of 严格双重校验 (400) + 诚实空态 (200 available:false) + guest 掩码 (R12 DTO) + 与 REV-04 面板同源 (同一 build_auction_recap/render); 6 项 POOL-03 AST 守卫 (REV 白名单重订, 含 save_report 禁调用); main.py 注册 + docs/features.md 竞价复盘节; 全量后端 1686 项回归绿

---

## v2.1 v2.1 (Shipped: 2026-08-06)

**Phases completed:** 4 phases, 8 plans, 22 tasks

**Key accomplishments:**

- snapshot_origin provenance (eod/backfill/manual) + 缺口 helper + `run_pool_backfill` 逐日回填服务 + `POST /api/pipeline/backfill` 触发端点 + `api/screener.run_all` D6 latest-only cache 指针修复
- GET /api/pool/dates 增 backfill_needed 缺口信号, 读侧 snapshot_origin 透传 (旧快照缺省 eod), EOD origin 断言 + D6 source guard 回归锁, docs 对账
- 股池钻取面接入既有服务端自选体系 (WATCH-01..04): VIP 星标 (实心/空心 + aria + fail-closed)、「只看自选」AND 过滤 (total 权威 + 诚实空态)、共享 QK.watchlist 复用 (guest 双门控零查询)、批量加可见行 — 纯前端, 零后端改动/零新增依赖
- POOL-03 e2e 三条守卫随 25-01 新控件同步 (installShell 默认 /api/watchlist mock + affordances 白名单扩增 + no-mutating 放宽为「非 watchlist 写仍为零」), 新增 WATCH-01..04 六条 Playwright 用例锁死星标/开关/批量行为, VIP 表格区 4 张 backstop 快照重生成 (零 diff 断言集 4 张 git 校验), docs/features.md 补自选联动小节
- CHART-01 read-only `GET /api/kline/auction/history` last-row aggregation endpoint (POOL-03 GET-only zero-exec, honest empty states, guest masking) + CHART-03 write-path widening to preserve optional auction input columns and revive the `auction_unmatched_amount` derive branch.
- 个股弹窗第三开关「竞价历史」— ECharts 双轴柱线图 (柱=竞价量/股, 线=竞价金额/元) + 09:15-09:25 窗口标注 + 诚实空态 (probe 非 available / available:false / rows 空 / guest → EmptyState, 绝不零值柱冒充), 全站挂 StockPreviewDialog 的页面一改全生效, Watchlist.tsx 零触碰。
- 09:26 盘前预览 job (premarket_pool_preview) 经 run_all_with_hits 生成今日股池到独立 premarket_results/date={T}/part.json (绝不污染 strategy_cache/screener_results) + compute_enriched_today 补算 open_gap (与 EOD Pass 4 单一公式) + probe 诚实降级语义 + 只读 GET /api/pool/premarket (空态 200, guest 白名单+掩码, POOL-03 AST 守卫)
- 盘前预览垂直切片 — PoolHubPage「最新」视图在 09:26-15:35 展示 pre_open 预览池 (独立 `GET /api/pool/premarket` 端点, 窗口标注「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」+ 诚实空态 + degraded 徽标), 15:35 EOD 后自动回退既有 `/api/pool/hub` 流; DateNavigator 保持 EOD-only (PIT-5)

---

## v2.0 v2.0 (Shipped: 2026-08-05)

**Phases completed:** 4 phases, 8 plans, 15 tasks

**Key accomplishments:**

- DATA-05 竞价湖摄入路径端到端成立：`auction_sync` 服务以 probe `available` 为唯一写湖准入闸门，将真实 09:15–09:25 集合竞价撮合行按 `date={d}` hive 分区原子写入 `data/kline_auction/date={d}/part.parquet`（canonical 四列），09:30 连续竞价 bar 经 555..565 窗口谓词结构性排除（回归锁死）；偏好旋钮（默认 False）与 daily_pipeline Step 2.6 双闸门接入盘后管道，`kline_auction` DuckDB 视图登记进 repository 权威重建与单视图刷新路径表。
- DATA-04/06 读路径端到端成立：`auction_volume`/`auction_amount` 登记为受管增强列（`ENRICHED_COLUMNS` + 新分类 `"auction"`，绝不进存储窄表/计算闭包），由 `attach_auction_columns` 按 probe×分区双闸门从 `kline_auction` 湖左联注入日线帧——probe 非 `available` 或缺分区时列缺席、功能 fail-closed 到派生 `open_gap`，从不静默填充；`ScreenerService._load_enriched_for_date` 三处 return 经 `_attach_auction` 注入策略 as-of 帧，`kline_auction` 登记进 `_SCHEMA_VIEWS`/`_TABLE_FIELD_DESC`（单位中文描述）；DATA-06 派生 `auction_unmatched_amount`（估算, 非真实成交）在委托量输入可得时按 `虚拟未匹配量 × 虚拟参考价` 派生，缺输入即列缺席、与真实列分列永不相加。
- 引擎 seam (time_window/evaluation_time/requires_auction_data META + requires_auction_data 短路空池 + minute_loader/confirm_minute 单点截断)、受管列 auction_volume_ratio (前 5 日均量分母, PIT-safe)、P1 三策略 auction_fast_grab / auction_alpha / golden_230 落地, test_auction_strategy_family.py 16 tests + 四项回归门禁全绿
- 竞价全面 / T+1闪电 / 盘中确认 三个 P2 策略落地（pre_open 白名单 + fail-closed + 引擎单点截断分钟确认），文档计数对账到 27，strategy-guide.md 补时间窗/分钟确认契约字段
- 22-pool-date-navigation · **Plan:** 22-01 · **Wave:** 1
- 盘后定时 `pool_eod_persist` job 落地 (mon-fri, 管道+5min, 单飞): 经 `run_all_with_hits` 预生成冻结快照 + 刷新最新指针; 游客可读 /pool/dates + /pool/history (GET-only); features.md 股池日期导航小节, 策略计数 27 无漂移
- 23-frontend · **Plan:** 23-01 · **Wave:** 1
- 23-frontend · **Plan:** 23-02 · **Wave:** 2

---

## v1.3 v1.3 (Shipped: 2026-08-04)

**Phases completed:** 4 phases, 8 plans, 23 tasks

**Key accomplishments:**

- Hermetic proof that enabling minute-K sync persists canonical 1m bars to `kline_minute` with 09:30+ timestamps while leaving the daily-K lake byte-identical, plus a `minute_sync_symbols` scope knob and a regression-locked 09:30 timestamp convention
- Server-authoritative auction-data probe (not_configured / available / fail_closed / error) wired service → GET/POST /api/data/auction-probe → Data-page 竞价数据 panel with the approved honest vocabulary, plus a governed persisted `open_gap` column (`open / prev_close − 1`) that strategy filters can consume — and regression-locked proof that a 09:30 continuous bar is never labeled 集合竞价 data
- 三个第一性原理竞价策略 (竞价多头 / 盘前强势量化 / 早盘之星) 落地 `strategy/builtin/`, 引擎自动发现、仅消费 Phase 16 受管列 (open_gap/change_pct/vol_ratio_5d)、评分权重和恒为 1.0, 并以 11 个 fixture 测试锁死 STRAT-03: API 去重 + 无第三条注册轨道。
- Pure, server-derived per-stock factor-hit aggregation (`build_factor_hits`/`attach_factor_hits`) wired additively into the screener `run_all` response so every result row reports which strategies hit it — the seam Phase 18 cross-resonance consumes
- Single-as_of pool-hub projection service (`build_pool_hub`) reading `screener_results/` persistence via `strategy_cache.read_cache`, projecting per-strategy counts + 5-column drill rows with server-computed 交叉共振 and a concept filter, exposed through read-only `GET /api/pool/hub`, with a POOL-03 zero-execution-authority guard suite.
- 股池 (Pool Hub) single-as_of read-only workspace — strategy cards with 当日池数, exact five-column drill-down table, client-side 概念 filter, and 交叉共振 highlight — with an automated POOL-03 zero-execution guard and committed visual-regression evidence.
- Guest sessions now read GET /api/pool/hub as `mode: "guest"` with code/name/symbol masked to `
- PoolHubPage is now mode-aware from the server `mode` field: guest sessions render the exact GuestModeBanner, server-masked `

---

## v1.0 MVP (Shipped: 2026-07-27)

**Phases completed:** 5 phases, 106 plans, 186 tasks

**Key accomplishments:**

- Deterministic, offline pytest contracts now define the fixture-sync path and governed market-data validation boundary Plan 02 must implement.
- Deterministic read-only fixtures now enter Tickflow exclusively through the governed Parquet, DuckDB, and Polars pipeline, with D-17 validation at completion.
- Multi-account operational persistence and archive-safe Portfolio APIs now project current P&L from shared quotes or governed closes.
- Tickflow now generates deterministic governed-data playbooks, durably snapshots them in operational SQLite, and exposes them through the authenticated host API.
- The existing Monitor center now evaluates explicit holdings after generic rules and persists immutable position-aware event snapshots before downstream handoff.
- Human approval admits only `@playwright/test@1.61.1` for the later browser-workflow plan, while this checkpoint leaves frontend dependencies and browser tooling untouched.
- Pinned Playwright browser tooling and fixture-only desktop/mobile investor workflow contracts establish the isolated Compose acceptance seam.
- The existing frontend now has typed Portfolio, Monitor-delivery, and decision contracts, account-aware shared SSE refreshes, and one responsive workspace shell.
- Portfolio is now a responsive first-class workspace with aggregate valuations, account-aware holdings maintenance, and source-aware freshness labels.
- The existing Monitor now manages holding-aware rules and durable delivery outcomes, while Dashboard exposes a read-only deterministic decision-plan audit with AI-disabled historical replay.
- Immutable monitor alerts now reach every shared-stream subscriber before bounded Feishu or Telegram work records a separate credential-safe outcome, while portfolio mutations fan out through that same stream.
- Four deterministic RED pytest contracts define archive-safe portfolio state, holding-aware monitoring, bounded notification outcomes, and shared SSE fan-out.
- Four RED pytest modules define deterministic decision baselines, bounded AI proposals, durable audit outcomes, and provider-free historical replay.
- Decision runs now retain typed, provenance-recorded OpenAI-compatible proposals separately from deterministic facts, apply only bounded audited fields, and replay governed history with AI disabled.
- Date-partitioned rank/z-score and symbol-partitioned rolling factor evaluation, proven from fixed AST compilation through immutable governed signal artifacts.
- Registered strategy backtests now retain deterministic SHA-256 governed-panel identity through trusted POST/SSE handoffs and expose the existing data-mismatch warning for retained comparisons.
- Registered-strategy SSE executions now retain a trusted server handle through completion, explicitly create immutable comparison snapshots, and expose accessible research history and side-by-side comparison in Backtest.
- Approved the exact official LangGraph and SQLite checkpointer releases while preserving the direct OpenAI SDK adapter and an unchanged lockfile.
- LangGraph 1.2.9 with SQLite checkpoint persistence plus offline RED contracts for evidence, bounded generation, and human-governed lifecycle transitions.
- Typed, subject-isolated analysis transport with coarse root-SSE invalidation and fixture-backed evidence-first RED browser contracts.
- Server-frozen A/B/C evidence, fail-closed material-number cross-checks, and append-only analysis audit records now share operational.db.
- Fixed two-node LangGraph generation with strict Pydantic output, frozen-evidence citation validation, and immutable SQLite-backed audit records.
- 1. [Rule 1 - Bug] Serialized confirmation/rejection ordering
- Authenticated analysis reports and lifecycle reviews now enforce persisted subject scope, middleware-owned reviewer identity, and filtered shared-stream progress events.
- Stock and account workspaces now render server-owned analysis evidence, structured reports, and lifecycle history with accessible independent panels.
- 1. [Rule 2 - Missing Critical] Added repository idempotency and application collaborator wiring
- 1. [Rule 3 - Blocking] Honored the governed fixture read-only mount contract
- 1. [Rule 1 - Bug] Corrected tests to the actual frontend response envelope contract
- 1. [Rule 2 - Missing Critical] Made display limitations explicitly optional
- Three deterministic RED pytest contracts now define immutable viewpoint lineage, reproducible experiment records, and five-gate research-strategy promotion without any live market or execution dependency.
- Three deterministic RED pytest contracts now define scoped agent authorization, safe advanced API/SSE projections, and replay-safe workflow persistence before the Phase 4 domain implementation exists.
- A 21-case hostile sandbox matrix and six fixture-backed browser scenarios now prevent Phase 4 from treating unproven isolation, undisclosed strategy code, or incomplete safe UI states as acceptable.
- Strict server-authoritative advanced-domain contracts now feed a single immutable operational SQLite ledger with fingerprinted policy snapshots, safe public projections, and transactional job cursors.
- Immutable attributed viewpoints now retain policy-bound versions, evidence, structural stance changes, frozen governed outcomes, and honest confidence calibration.
- Governed experiment runs and strategy evolutions now preserve immutable evidence lineage, reject invalid conclusions, and permit only explicitly approved research-strategy registration.
- Durable server-owned authorization and a fail-closed custom-strategy boundary now reject unsafe work before provider, sandbox, graph, or SSE activity can begin.
- A server-thread-bound LangGraph workflow now freezes authorized inputs before deterministic gates, while shared SSE delivers only committed safe advanced stages to matching server-scoped subscribers.
- The shared FastAPI host now registers strict advanced research routes that authorize persisted viewpoint and experiment records before returning safe DTOs, while sandbox submissions remain hash-bound and fail closed.
- Session-authorized advanced research now renders immutable viewpoints, calibration uncertainty, and scoped task/audit status in the existing object analysis workspace without browser-held authority.
- Backtest now supports immutable experiment records, independent promotion gates, registered-only approval, and constrained custom-strategy sandbox review through typed server-authorized projections.
- Authorized immutable viewpoint outcomes and bounded experiment execution now run through the real FastAPI lifespan with durable, safe terminal evidence.
- Authorized advanced jobs now revalidate into a server-bound fixed workflow, persist each cursor and audit fact atomically, and publish only committed scoped SSE stages.
- Capability-gated Linux sandbox execution now records safe terminal facts, while a non-intercepted Playwright host proves real advanced API and root SSE delivery.
- Linux sandbox admission now requires observable isolation evidence, and authorized researchers can review sanitized immutable terminal run records.
- Immutable viewpoints now use a lifecycle-owned governed historical snapshot for outcome facts and expose authorized revision, correction, and evaluation actions.
- Production strategy experiments now freeze runner-ready scope, retain completed governed evidence, and drive five immutable evolution gates before explicit research-only registration.
- Existing Analysis and Backtest workspaces now expose immutable viewpoint evaluation, frozen experiment evolution, and redacted terminal sandbox review through typed server contracts.
- Production FastAPI lifespan can load a governed advanced fixture for real-host authorization, rejection, root-SSE, and bounded spawned-run coverage without browser route interception.
- The implementation-grounded LangGraph and SQLite checkpointer matrix passed the deterministic Phase 4 API-coverage gate without a matrix change.
- Complete.
- Experiment specifications now freeze the exact server-resolved installed strategy for their persisted research asset, and both service and runner deny divergent lineage before governed work begins.
- Advanced jobs now consume only their own policy-defined SQLite quota bucket at creation and execution start, while exhausted work is audited without starting workers or publishing SSE progress.
- Deployment-owned readiness descriptors now reject malformed, incomplete, or signal-ineligible advanced fixtures before any governed Parquet, DuckDB, view, or cache mutation.
- Immutable viewpoint versions now yield one deterministic terminal calibration observation, and repeated evaluation requests reuse that frozen fact without re-running governed inputs.
- Authenticated public routes now resolve immutable experiment lineage server-side, while real FastAPI lifespan regressions prove mismatch, quota, readiness, and repeated-evaluation safeguards before prohibited work begins.
- Advanced job authorization now fails closed across deployment policy revisions: A-issued authority cannot charge under B, and a correctly queued A job rejects before any B inspection, work, or SSE activity.
- Decision: `approved` for every listed package, source, model, tokenizer, digest, and local-only loading policy. Plan 05-07 may proceed only after validating this complete summary.
- Deterministic hostile broker-log fixtures and 31 exact pytest nodes now pin immutable Shadow evidence, explainable rule candidates, independent IS/OOS evaluation, and research-only retention before production implementation.
- Forty-nine exact pytest nodes now pin complete valuation anchors, immutable thesis version lineage, restart-safe per-condition checks, pending-only evidence conclusions, and server-authoritative human review before production implementation.
- Deterministic governed Forecast fixtures and 86 exact-node RED contracts now pin local checkpoint provenance, governed inputs, retained path-axis quantiles, durable concurrency/recovery, and append-only calibration.
- Exact real-host and Playwright RED gates now inventory eight module combinations and all 13 approved UI scenarios while rejecting every failure outside the intentionally missing Phase 05 production seams.
- A single append-only operational migration, atomically promoted immutable artifact store, and independent lazy OptionalModuleHost now provide the shared failure-isolated foundation for all three optional vertical slices.
- Approved Shadow/Forecast extras, byte-pinned Kronos inference source, and operator-only immutable safetensors provisioning now form a reproducible optional boundary without adding runtime downloads or heavy base dependencies.
- Bounded broker-log normalization now freezes every execution attempt into attributable immutable evidence and converts transient shallow trees into canonical replayable rule facts with no executable model state.
- Predecessor-guarded SQLite transactions now append canonical Thesis versions while fixed source resolvers and typed condition dispatch preserve auditable evidence, deterministic lineage, and explicit insufficiency.
- A deployment-pinned local catalog, exact governed CN-A input freezer, and worker-only pre-mean Kronos seam now preserve 32 immutable sampled paths and derive fixed path-axis P10/P50/P90 without runtime network authority.
- Shadow candidates now earn research-only retention solely from separately frozen, chronological, non-overlapping IS/OOS terminal evidence, exposed through authenticated deny-by-default immutable APIs without acquiring operational authority.
- Restart-safe per-condition leases now produce one canonical immutable check and matched-only pending conclusion, while stock-scoped APIs reserve official invalidation for revalidated server-principal review.
- A SQLite-backed CAS ledger and local-only spawn runner now enforce single-flight Forecast inference, bounded process cleanup, explicit retry/recovery semantics, and one immutable verified record commit.
- Append-only Forecast calibration, object-scoped job/record/path/SSE APIs, and independently recoverable Shadow, Thesis, and Forecast factories now run inside AthenaQuant's one completed-v1 FastAPI lifespan.
- A strict typed Phase 05 API/query/SSE boundary now powers an evidence-first Shadow workflow inside the existing Strategy Backtest workspace, with immutable history, accessible confirmations, bounded responsive tables, and no activation authority.
- Stock Analysis now contains immutable Thesis review and governed Kronos probability Forecast workspaces, backed by the committed typed query/SSE boundary, complete server-owned lineage, accessible table evidence, and no Portfolio or cross-module authority.
- All eight real optional-module host combinations and exactly 13 production Playwright scenarios now pass as ordinary green contracts, with governed stale-state metadata, strict no-authority telemetry, and an honest offline-only Kronos checkpoint gate.
- Strict browser selectors now traverse the authenticated production host into governed local-trade feature derivation, an explainable transient candidate, immutable split panels, and bounded chronological IS/OOS evaluation with no completed-v1 action authority.
- Shadow candidate, paired evaluation, and retention retries now resolve through one content-complete append-only identity chain that survives interruption without substituting divergent facts or granting action authority.
- Shadow confirmation now proves the exact reviewed transformation, while duplicate lineage, evidence construction, and every public ledger page remain principal-owned and bounded before materialization.
- Strict server-owned Thesis conditions now resolve on their declared Shanghai calendar day, expose only current unreviewed work as actionable, and retain every conclusion in deterministic repository-bounded history pages.
- Authenticated Forecast requests now freeze exact governed bytes, revalidate approved local identities before bounded execution, and cross one fail-closed immutable commit bound to the selected calendar, checkpoint, sampling shape, and verified output artifact.
- Forecast records now expose 32 complete checksum-verified paths with path-derived quantiles, mature fairly through one durable repairable cursor, and stream persisted transition versions under strict synchronized capacity limits.
- Analysis, Thesis, and Forecast browser authority now follows the active canonical object through strict immutable pages, durable request/SSE identities, and a keyboard-safe 375px stock workspace.
- Operational migrations now commit schema and version atomically, while the single FastAPI host exposes unconfigured data only through an exact loopback trust boundary and advertises each optional module only after complete independent readiness.
- Pinned Kronos catalog identities now bind `config.json` and `model.safetensors` digests; provisioning serializes publication with flock and never deletes shared finals. Forecast extra pins exact CPU torch from the official pytorch-cpu index. Planning approval paperwork is not a runtime precondition for this personal project.
- Catalog re-verifies every UPSTREAM destination and config/weight digest, Kronos imports only from the verified source directory with origin containment, and the spawn runner uses capped byte Pipe IPC with a ready handshake plus terminate/kill descendant cleanup.
- The independent reviewer rejected the incomplete Kronos-mini config provenance and marked the PyTorch CPU artifact identity incomplete; no new supply identity is approved, so Plan 05-26 remains fail-closed.
- Integrated final gate passed on the post-gap revision: 370 discovered = 370 passed across backend JUnit and both Playwright reports; CR-01..07 and WR-01..03 each map to exactly one passed node; no skip/xfail/xpass/duplicate.
- Strict allowlisted Shadow assumptions now use one canonical, resource-bounded contract from request parsing through immutable persistence, replay hydration, and public projection.
- Shadow import and Parquet failures now clean only invocation-owned temporary evidence with attributable reconciliation errors, while retention approval submits an exact trimmed rationale through a focus-safe accessible modal.
- Production Thesis checks now consume bounded facts from the existing governed lake and immutable analysis ledger, isolate poison leases, and advertise availability only after the real scheduler has registered a ready scanner.
- Shadow now turns a normal non-empty browser import into immutable evidence, candidate distillation, and passing IS/OOS evaluation while complete trade membership and principal ownership remain server-authoritative.
- 32-path 绑定的 P10/P50/P90 Parquet 工件现在可经唯一事务提交、进程重启、公共投影和成熟度校准全链路复用同一组校验字节，同时 SQLite 仅保存有界身份元数据。
- Forecast 校准表按 `calibration.outcome_id` 精确连接唯一 outcome，正确展示 5/20/60 实际与目标交易日，身份不完整时 fail closed 为「校准身份不完整」。
- WR-03 closed: check/history pages self-identify with instrument/thesis/version display fields so immutable ledger rows render without waiting on version pagination
- Forecast 的公开列表、详情、重试、SSE、record/path/outcome/calibration 现均由持久化 principal 与规范 instrument 双重约束，且同 instrument 的第二 principal 无法观察或触发首个 principal 的任何资源。
- Operation-first Forecast replay, read-only sealed worker input, mandatory final input revalidation before commit, and same-open Parquet decode close CR-05, WR-01, and WR-02.
- Startup recovery now dispatches each durable queued Forecast job once under CAS/global lease, and the runner reaps the handshake process group on every post-spawn path including normal leader exit.
- 开发者明确选择“Reject and continue independent fixes”；由于未提供完整、独立人工撰写并逐行批准的六行身份记录，本次重试以 `approval: rejected`、`gate_status: blocked` 终结，05-26 继续 fail-closed。
- One real Chromium browser now drives non-empty Shadow import through server-resolved evidence, candidate distillation, and chronological IS/OOS against the production optional host with zero Shadow interception and zero live-action authority.
- The production host now starts on Windows without POSIX `resource`, Linux isolation stays rigorously fail-closed, availability coverage has five independent browser budgets, and Thesis checks compile against their canonical persisted identity.
- Controlled strategy IR, owner-first Forecast publication, and retained shutdown ownership replace arbitrary Python, freeze-first retry, and silent close semantics.
- One provenance-bound closeout approved only the R43/Wave 15 scope after 613/613 checks passed against one frozen Git tree, including attested native Linux evidence from GitHub Actions.

---

## v1.1 Operational Hardening (Shipped: 2026-07-29)

**Phases completed:** 4 phases, 4 plans (Phase 6-9)
**Closeout type:** override_closeout (post-closeout native-Linux evidence verified 659/659; 1 Windows/WSL deferral remains)

**Key accomplishments:**

- Release evidence paths resolve dynamically from repo root, surviving archive layout changes; Linux evidence producer runs natively without WSL dependency.
- Historical approval-paperwork gate removed from sync_kronos.py — supply is fail-closed on SHA-256/identity, not reviewer paperwork.
- All avoidable backend test warnings eliminated across 9 files: Polars `collect(engine="streaming")`, `check_sortedness=False`, `datetime.now(UTC)`, explicit sqlite3/AsyncOpenAI client cleanup. Backend: 961 passed, 0 failed (down from 9 failures). Warnings 143→84 (84 all pytest GC artifacts, 0 application-code).
- Frontend validation clean: tsc 0 errors, vite build clean.
- Optional supply path verified complete: documented provision command, SHA-256 fail-closed identity gate, 24 tests pass.
- Visual regression baselines committed: 4 Playwright tests at desktop (1440×960) and mobile (375×812), 1% drift threshold.

---
