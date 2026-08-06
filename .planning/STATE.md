---
gsd_state_version: 1.0
milestone: v2.3
milestone_name: 数据纵深解锁 — planning
status: Awaiting next milestone
stopped_at: Completed 31-03-PLAN.md
last_updated: "2026-08-06T19:18:41.209Z"
last_activity: 2026-08-06
last_activity_desc: Milestone v2.3 completed and archived
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 16
  completed_plans: 12
  percent: 0
current_phase: 35
current_phase_name: Legacy Completion & Deploy Verification
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-06)

**Core value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.
**Current focus:** Milestone v2.3 — 数据纵深解锁

## Current Position

Phase: Milestone v2.3 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-08-06 — Milestone v2.3 completed and archived

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

Last session: 2026-08-06T15:34:27.037Z
Stopped at: Completed 31-03-PLAN.md
Resume file: None

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone

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
- [Phase ?]: Phase 28 P1 (CONCEPT-01..07 backend core): 归档源 = 当前 ext 快照行 (离线零网络, 与平台展示一致); capture_from_upstream 仅 OQ-3 探针独立测量上游
- [Phase ?]: Phase 28 P1: concept_history 模块 docstring 用「运行时缓存」指代 strategy_cache, 避免字面量 (E3 子串守卫绿); EOD 钩子函数内局部 import, 测试 patch app.services.concept_history.capture 模块对象
- [Phase ?]: Phase 28 P1: build_pool_hub (实时) 不传 as_of → 恒 current_snapshot; 仅 build_pool_hub_snapshot 透传 as_of (as_of_snapshot 时追加 concept_effective_date/captured_at)
- [Phase ?]: 概念徽标按服务端冻结 concept_attribution 双态渲染, as_of_snapshot 显示概念数据生效日期, 前端零推断 (CONCEPT-04/07)
- [Phase ?]: as_of e2e 用两步下拉导航保证 change 触发, 历史必走 /api/pool/history (PIT-1)
- [Phase ?]: _dimension_rank as_of 分支函数体内局部 import concept_history; as_of 参数兼容 str 与 date (build_market_overview/market_recap 传 date, read_partition 要 str → isoformat 归一)
- [Phase ?]: build_rps_rotation 提取 _build_rotation_full 私有 helper 复用 join/agg/grouped 段, as_of 与 latest 两分支各一次
- [Phase ?]: as_of 分支空 map → 返回空矩阵, 不 fallback 当前 ext (诚实标注来源)
- [Phase ?]: RPS 矩阵各历史列仍共用单日 map; 逐日概念 map 各列独立属未来增强
- [Phase ?]: 29-01 (BT-02): 等价性测试逐日裁剪缓存 — get_enriched_history 以整缓存 trading_dates[-(lookback+1)] 为切片锚点 (repository.py:951-957), 单日分母只有 T ∈ {cache_max-1, cache_max} 才等于「T 前 5 行」; 逐日 seed 缓存 = 面板 ≤ d 行, 缓存与面板同源同前导 (W2 前提), 逐值 <1e-9 成立
- [Phase ?]: 29-01 (BT-02): 向量化分母用 min_samples=1 (polars 1.40.1 现行 kwarg, 与 factor_dsl.py:575 一致), 不用已弃用 min_periods= (N1)
- [Phase ?]: 29-01 (BT-02): 等价性断言只用于 ≥5 前导行的全面板输入 (W2); 1-4 日前导短历史用手算均值断言 (边界/warmup 测试)
- [Phase ?]: 29-02 (BT-03/04/05): skipped_ids 语义 — 非空请求集不含任何可解析竞价族策略 → 回落默认族范围 (未知 id 记 skipped, 已知竞价族仍正常报告); 显式 [] → strategies: []; None → 9 族 ∩ engine
- [Phase ?]: 29-02 (BT-04): 全局日历 next-date 用 calendar 帧 join (polars 1.40.1 无 map_dict); 结果日全 null 时 outcome_date 显式 cast(pl.Date, strict=False) 修复 join schema
- [Phase ?]: 29-02: probe 在 build_report 顶部解析一次, 所有路径 (含 enriched_unavailable) 均携带 probe 字段 — 200 形全形状一致
- [Phase ?]: probe 透传由服务层承担: handler 直接构造 AuctionValidationService(repo, engine), 服务层 probe_resolver 顶部解析一次, 所有路径响应均带 probe 字段 (D-03)
- [Phase ?]: Test 6 白名单补 collections.abc (29-02 服务既有 stdlib import 面, 计划 parenthetical 遗漏) — 不改已交付服务, 守卫仍为封闭白名单
- [Phase ?]: preopen 规则 op=truth 配置期显式拒绝 (盘前帧无布尔信号列)
- [Phase ?]: evaluate_premarket 帧重建 change_pct 恒 None + 白名单禁 EOD 列双保险
- [Phase ?]: 尾段接线保持调度注册零改动 (T11 锁死): 不新增 job、不碰常量, 与 persist 同一 _run_tracked 单飞内完成评估
- [Phase ?]: evaluate_premarket_alerts 与 _evaluate_monitors 并列: 无时间 gate 是刻意差异 (仅 09:26 job 触发), 持久化/广播/投递三件套逐字节复用
- [Phase ?]: degraded 事件带冻结 probe 快照落库 (round-trip 保真), 不新增「未触发日志」表 (OQ-3 保持 v2.2 范围)
- [Phase ?]: mask_guest_alert 白名单含 message/conditions (盘前文案非 PII), 飞书/Telegram 所有者通道不受掩码约束
- [Phase ?]: T19 守卫扫描 docstring 剥离后的源码 (docstring 为禁令声明文本, 非调用面)
- [Phase ?]: 30-03: thresholdFields 按类型切换 (preopen → preopen_threshold_fields ?? []) 而非合并两份字段表 — 配置期白名单隔离, 杜绝建出必失败的规则
- [Phase ?]: 30-03: preopen 隐藏 truth 信号点选仅为 UX (后端 validate 白名单为最终防线 — 双保险)
- [Phase ?]: 30-03: 徽标区整体以 ev.source === 'preopen' 包裹, provisional/degraded 为可选字段 — 旧事件零渲染零崩溃
- [Phase ?]: 30-03: e2e 断言命中条件行与前端渲染器字形一致 ('open_gap>=0.05' 非 '≥'; cnSignal 映射后字段名)
- [Phase 31 / P1]: 31-01: pre_eod 判别用分钟算术 (now.hour*60+now.minute) vs 调度 (W-2); 懒 import from app.services.preferences.get_pipeline_schedule (W-1 守卫白名单形)
- [Phase 31 / P1]: 31-01: 服务模块避免 import math/json (不在 31-03 _IMPORT_EXACT), NaN/Inf 用 v != v or v in (inf,-inf) — 守卫白名单纪律前置
- [Phase ?]: recap_market_stream 面板 delta 事件序锁死 (meta → AI delta* → 面板 delta → done); 面板经 delta 机制三跳全收零改动; 全缺席退化纯 AI (验收 5 回归锁); AI 失败不发面板 (R8)
- [Phase ?]: 可选 AI 点评默认 OFF: preferences recap_auction_commentary + PUT/GET 端点 + 护栏行局部 system 串 (_SYSTEM_PROMPT 不动) + 切片与面板同 dict 构造性单源
- [Phase ?]: 调度默认 15:40 (竞价同步 15:30 + 股池持久化 15:35 后三块全亮); 已存偏好保留; 15:00 下限不动; Review.tsx:105 兜底字面量同步
- [Phase ?]: REV-05 guest DTO 锁死: 身份键 (symbol/name/code) MASKED_IDENTITY + 敏感值键 (auction_*/open_gap/量比) 剥离, 聚合统计与状态标注保留, probe 剥离, guest 视图无 markdown; 空态与 vip 同形 (available:false + blocks:{})
- [Phase ?]: 31-03 守卫白名单以实际 shipped imports 为准: 服务 import app.market_time + app.services.preferences (懒 import get_pipeline_schedule) + auction_columns/probe/validation/premarket_snapshot/screener — 全部落入 REV 白名单; 禁 import token 收窄 auction_sync|pool_snapshot|pool_backfill, 禁调用扩展 save_report

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
| Phase 31 P1 | 7min | 3 tasks | 2 files |

---
*Last updated: 2026-08-05 — Phase 21 plan 1 (STRAT-04/05/06 engine seam + managed column + P1 strategies) complete; Phase 21 in progress (plan 2 parallel)*
| Phase 25-watchlist-sync PP2 | 14 | 3 tasks | 6 files |
| Phase 26-auction-history-chart P1 | 24 | 2 tasks | 8 files |
| Phase 26 P2 | 38 | 2 tasks | 7 files |
| Phase 27-premarket-pool P1 | 11 | 3 tasks | 8 files |
| Phase 27 P2 | 35 | 3 tasks | 6 files |
| Phase 28 P1 | 41 | 3 tasks | 6 files |
| Phase 28 P2 | 5 | 3 tasks | 5 files |
| Phase 28-concept-pit P3 | 5 | 2 tasks | 4 files |
| Phase 29 P1 | 40 | 3 tasks | 2 files |
| Phase 29 P2 | 55 | 3 tasks | 2 files |
| Phase 29 P2 | 55 | 3 tasks | 2 files |
| Phase 29 P3 | 7min | 3 tasks | 5 files |
| Phase 30 P1 | 31 | 3 tasks | 4 files |
| Phase 30 P2 | 24 | 3 tasks | 8 files |
| Phase 30-premarket-monitor P3 | 36 | 2 tasks | 5 files |
| Phase 31 P2 | 9 | 3 tasks | 5 files |
| Phase 31 P3 | 20 | 3 tasks | 5 files |
