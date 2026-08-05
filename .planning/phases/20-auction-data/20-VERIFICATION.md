---
phase: 20-auction-data
verified: 2026-08-05T00:00:00Z
status: passed
score: 18/18 must-have truths verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
human_verification:
  - test: "Data 页竞价数据面板：竞价列可用性 section（竞价量/金额，单位 股/元）在 probe available + 当日分区有行时渲染 `竞价列可用` + 真实列；probe 非 available 渲染 `竞价列不可用` fail-closed 空态"
    expected: "列/组分栏文案安全换行（overflow-wrap:anywhere），不溢出 max-w-2xl 面板"
    why_human: "Phase 20 为后端数据层，零前端改动（git 证实）；UI 渲染本体属 Phase 23。UI-SPEC backstop #1 无代码证据"
  - test: "fail-closed 长文案（`竞价列不可用` body）在窄面板换行包裹、不截断"
    expected: "长文案完整可见，无水平截断/溢出"
    why_human: "后端 DTO 契约已绿，但 UI 呈现需浏览器目检；UI-SPEC backstop #2 无代码证据"
  - test: "`竞价湖覆盖 {N} 天` 单复数文案：0 天不渲染为「可用」，1 天/N 天措辞正确"
    expected: "覆盖天数为 0 时显示诚实空态而非「竞价列可用」；{N} 用 mono/tabular-nums"
    why_human: "盘后管道已在 run_now 计算 auction_cover_days，但该数字的 UI 消费属 Phase 23；UI-SPEC backstop #3 无代码证据"
  - test: "Phase 16 既有 probe 判定长文案换行行为保持，不回归"
    expected: "既有 `竞价数据探测失败：{message}。…` 等长文案换行正常"
    why_human: "Phase 20 未触碰前端，既有行为需浏览器回归目检；UI-SPEC backstop #4 无代码证据"
---

# Phase 20: 竞价数据层 (Auction Data) 验证报告

**Phase Goal:** 研究者可以把真实 09:15–09:25 集合竞价撮合数据（竞价量/竞价金额）作为受管增强列持久化，经 `auction_sync` 落盘到 `kline_auction/date={d}/` 分区湖；整条生产路径以 auction probe 判定为前置——不可用时缺列并 fail-closed 回退到派生 `open_gap`，绝不静默填充，也绝不把 09:30 连续竞价 bar 标为集合竞价数据。
**Verified:** 2026-08-05
**Status:** passed (human_signoff 2026-08-05, UI backstops → Phase 23)
**Re-verification:** No — initial verification

## 目标达成 (Goal Achievement)

### 可观测真相 (Observable Truths)

| # | 真相 | 状态 | 证据 |
| --- | --- | --- | --- |
| SC1 | probe `available` 时日线帧带受管增强列 `auction_volume`/`auction_amount`；非 `available` 时列缺席、fail-closed 回退派生 `open_gap`，绝不静默填充 | ✓ VERIFIED | `auction_columns.attach_auction_columns` 双闸门（probe×分区）；`test_available_with_partition_injects_real_columns` / `test_available_without_partition_keeps_absent` / `test_non_available_statuses_keep_absent` / `test_partition_empty_keeps_absent` 全绿 |
| SC2 | `auction_sync` 把真实 09:15–09:25 窗口行按 `date={d}` 分区写入 `kline_auction/` 湖；09:30 连续竞价 bar 结构性排除（回归锁死） | ✓ VERIFIED | `auction_sync.sync_and_persist_auction` 555..565 写湖过滤器；`test_sync_writes_partition` / `test_0930_excluded` / `test_merge_upsert_same_day` / `test_atomic_write_leaves_no_tmp` / `test_auction_view_registered` 全绿 |
| SC3 | 委托量输入可得时研究者能查看派生竞价未匹配金额 proxy；输入不可得时列缺席、策略回退量比+金额强度 | ✓ VERIFIED | `compute_auction_unmatched_amount`（未匹配量×虚拟参考价）；engine.py:496-497 缺失列静默跳过；`test_unmatched_proxy_input_present` / `test_unmatched_proxy_input_absent` / `test_unmatched_proxy_never_mixed_with_real` 全绿 |
| SC4 | probe 非 `available` 时策略/UI 都看不到竞价列，只能看到派生列与 `open_gap`；无任何 UI 或策略把 09:30 bar 标为集合竞价数据 | ✓ VERIFIED | 策略侧 `ScreenerService._attach_auction` fail-closed + `test_screener_frame_absent_when_probe_not_available`；probe 回归 `test_0930_only_rows_are_fail_closed_never_available` / `test_all_0930_rows_can_never_produce_available` / `test_verdict_window_and_fallback_are_fixed_for_every_status`（window="09:15-09:25", fallback="open_gap"）；UI 侧 git 证实 Phase-20 六笔提交零前端改动（UI 渲染属 Phase 23） |
| T1 (20-01#1) | probe `available` 为写湖唯一准入闸门，非 available 一律 0 行不写湖 | ✓ VERIFIED | `sync_and_persist_auction:102-104`；`test_non_available_writes_nothing[not_configured/fail_closed/error]` 参数化全绿 |
| T2 (20-01#2) | 湖内只存真实窗口行：写湖过滤器与 `provider._normalize_auction` 共用 555..565 谓词 | ✓ VERIFIED | `auction_sync._WINDOW_START_MIN=555/_WINDOW_END_MIN=565`；`custom/provider.py:158` 同字面量；`test_0930_excluded` |
| T3 (20-01#3) | 原子写只走 `_atomic_write_parquet`（.tmp + 同目录 replace），无 .tmp 残留 | ✓ VERIFIED | `auction_sync.py:38-47`；`test_atomic_write_leaves_no_tmp`（目录内文件集 == {part.parquet}） |
| T4 (20-01#4) | `auction_sync_enabled`（默认 False）/`auction_sync_symbols`（空=全量）偏好旋钮镜像 minute | ✓ VERIFIED | `preferences.py:129-143`；`test_auction_prefs_round_trip` |
| T5 (20-01#5) | daily_pipeline Step 2.6 插在 sync_minute 之后、刷新视图之前；未开启/probe 不可用计 skipped；写湖后 `_invalidate("auction")`+`_refresh_single_view` | ✓ VERIFIED | `daily_pipeline.py:591-602`（Step 2.6 位于 562-589 sync_minute 之后、604 Step 3 之前）；`test_run_auction_sync_gate` / `test_resolve_auction_symbols_honors_scope` |
| T6 (20-01#6) | `kline_auction` DuckDB 视图登记于 DataStore 子目录 + `_register_views` + `rebuild_views` + `_refresh_single_view` 路径表 | ✓ VERIFIED | `repository.py:58/162-163/1669`；`daily_pipeline.py:653`；`test_auction_view_registered` / `test_auction_view_absent_without_lake` |
| T7 (20-02#1) | 受管列注册纪律：auction_* 三列在 `ENRICHED_COLUMNS`+`BY_CATEGORY["auction"]`，绝不在存储窄表/计算闭包 | ✓ VERIFIED | `pipeline.py:157-160/183`；`_ALL_INDICATOR_COLS` 上方注释（:313）；grep 证实不在 `ENRICHED_STORAGE_COLS`/`_ALL_INDICATOR_COLS`；`test_registry_discipline` |
| T8 (20-02#2) | probe 非 available → 日线帧缺列、`open_gap` 恒在，绝不写 null 列 | ✓ VERIFIED | `attach_auction_columns:70-73`；`test_non_available_statuses_keep_absent`（open_gap 恒在） |
| T9 (20-02#3) | 读路径 probe×分区双闸门；probe available 但无分区 → 诚实按日空态（非 null-as-present） | ✓ VERIFIED | `attach_auction_columns:76-84`；`test_available_without_partition_keeps_absent` |
| T10 (20-02#4) | 派生列独立命名 `auction_unmatched_amount` + 「估算, 非真实成交」标注；输入不可得时列缺席、策略回退 | ✓ VERIFIED | `pipeline.py:160` 描述；`compute_auction_unmatched_amount:44-50`；`test_unmatched_proxy_input_absent` |
| T11 (20-02#5) | 真实 vs 派生分列明确，绝不相加/混排 | ✓ VERIFIED | `test_unmatched_proxy_never_mixed_with_real`（三列独立 schema、真实列值不变）；派生列描述含「估算」「非真实成交」且 ≠ 真实列描述 |
| T12 (20-02#6) | 策略 as-of 帧（`_load_enriched_for_date`）probe 通过带真实列、非 available 不带 | ✓ VERIFIED | `screener.py:233/248/269` 三处 return 经 `_attach_auction`（:271-286）注入；`test_screener_frame_carries_auction_columns` / `test_screener_frame_absent_when_probe_not_available` |
| T13 (20-02#7) | API/schema 面：`_SCHEMA_VIEWS["auction"]="kline_auction"` + `_TABLE_FIELD_DESC["kline_auction"]` 单位中文描述 | ✓ VERIFIED | `data.py:769-774/822`；`test_schema_surface_lists_kline_auction`（含 TestClient GET /api/data/schema/enriched） |
| T14 (20-02#8) | 诚实标签回归：09:30 bar 永不标集合竞价；fail-closed 基准恒为派生 `open_gap`；error 详情 ≤200 字符 | ✓ VERIFIED | `auction_probe.py:23-30/48-49/169`；`test_0930_only_rows_are_fail_closed_never_available` / `test_verdict_window_and_fallback_are_fixed_for_every_status` / `test_raising_provider_is_error` |

**Score:** 18/18 truths verified（4/4 成功标准 + 14/14 计划真相）；0 present-behavior-unverified；4 项 UI-SPEC backstop 转入人工验证。

### 必选工件 (Required Artifacts)

| Artifact | 预期 | 状态 | 详情 |
| -------- | ----- | ---- | ---- |
| `backend/app/services/auction_sync.py` | 湖摄入服务：probe 门 + 555..565 过滤 + 按日分区原子写 | ✓ VERIFIED | 160 行实质实现，非 stub；`sync_and_persist_auction`/`can_sync_auction`/`_first_auction_provider`/`_atomic_write_parquet`/`CANONICAL_AUCTION_COLS` |
| `backend/app/services/auction_columns.py` | 读路径左联 + 派生 proxy | ✓ VERIFIED | 103 行实质实现；`attach_auction_columns`（双闸门+去重）/`compute_auction_unmatched_amount` |
| `backend/app/indicators/pipeline.py` | 受管列注册表 | ✓ VERIFIED | `ENRICHED_COLUMNS` 三列 + `BY_CATEGORY["auction"]` + `_ALL_INDICATOR_COLS` 注释；不进存储窄表/计算闭包 |
| `backend/app/services/screener.py` | 策略 as-of 帧注入 | ✓ VERIFIED | `_attach_auction` + `_load_enriched_for_date` 三处 return |
| `backend/app/api/data.py` | schema 面 | ✓ VERIFIED | `_SCHEMA_VIEWS["auction"]` + `_TABLE_FIELD_DESC["kline_auction"]` |
| `backend/app/jobs/daily_pipeline.py` | Step 2.6 竞价同步 stage | ✓ VERIFIED | `_run_auction_sync`/`_resolve_auction_symbols`/`auction_rows`/`_refresh_single_view` |
| `backend/app/tickflow/repository.py` | `kline_auction` 视图登记 | ✓ VERIFIED | 子目录 + `_register_views` + `rebuild_views` |
| `backend/app/services/preferences.py` | 偏好旋钮 | ✓ VERIFIED | `get/set_auction_sync_symbols` + `get_auction_sync_enabled` |
| `backend/tests/test_auction_sync.py` | 12 项 hermetic 测试 | ✓ VERIFIED | 12 项全绿 |
| `backend/tests/test_auction_columns.py` | 12 项 hermetic 测试 | ✓ VERIFIED | 12 项全绿 |
| `backend/tests/test_auction_probe.py` | 回归 11 项 | ✓ VERIFIED | 11 项全绿 |

### 关键连接验证 (Key Link Verification)

| From | To | Via | Status | 详情 |
| ---- | --- | --- | ------ | ---- |
| `resolve_auction_probe().status` | `auction_sync` 写湖 | `can_sync_auction` → `sync_and_persist_auction` → `kline_auction/date={d}/part.parquet` | ✓ WIRED | probe available 是唯一准入闸门（`auction_sync.py:102-104`） |
| provider `_normalize_auction` 谓词 | 写湖过滤器 | 同一 555..565 字面量 | ✓ WIRED | `custom/provider.py:158` == `auction_sync._WINDOW_START_MIN/_END_MIN` |
| `preferences.get_auction_sync_enabled()` | `daily_pipeline._run_auction_sync` | Step 2.6 双闸门 → `sync_and_persist_auction` | ✓ WIRED | `daily_pipeline.py:695-707` |
| `resolve_auction_probe().status` | `attach_auction_columns` 注入 | probe×分区双闸门 → `_load_enriched_for_date` 帧 | ✓ WIRED | `auction_columns.py:70-102` + `screener.py:271-286` |
| `ENRICHED_COLUMNS` auction 条目 | `api/data.py` schema | `_SCHEMA_VIEWS`/`_TABLE_FIELD_DESC` | ✓ WIRED | `data.py:769-774/822`；`test_schema_surface_lists_kline_auction` |
| `compute_auction_unmatched_amount` | 策略回退 | engine.py:496-497 缺失列静默跳过 | ✓ WIRED | 缺输入列 → 派生列缺席 → 回退量比+金额强度 |

### 数据流追踪 (Level 4)

| Artifact | 数据变量 | 来源 | 产生真实数据 | 状态 |
| -------- | -------- | ---- | ------------ | ---- |
| `auction_sync.sync_and_persist_auction` | df 行 | `provider.get_auction(symbols, trade_date)` → 555..565 过滤 → canonical 裁剪 → 分区合并写 | ✓ | ✓ FLOWING |
| `attach_auction_columns` | auction_volume/amount | `pl.read_parquet(part)` 真实湖分区 | ✓ | ✓ FLOWING |
| `compute_auction_unmatched_amount` | auction_unmatched_amount | `auction_unmatched_volume × auction_virtual_price` 派生 | ✓（仅输入可得时） | ✓ FLOWING |
| `_run_auction_sync` → run_now | auction_rows | `sync_and_persist_auction` 返回值 | ✓ | ✓ FLOWING |

### 行为抽查 (Behavioral Spot-Checks)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 全套竞价测试 | `cd backend && .venv/bin/python -m pytest tests/test_auction_sync.py tests/test_auction_columns.py tests/test_auction_probe.py -q` | 35 passed | ✓ PASS |
| 相关回归 | `cd backend && .venv/bin/python -m pytest tests/test_minute_sync_verify.py tests/test_screener_etf.py -q` | 14 passed | ✓ PASS |
| 09:30 结构性排除（单测命名验证） | `test_0930_excluded` 已跑绿 | 仅 ≥09:30 输入 → 湖 0 行无分区 | ✓ PASS |
| probe 诚实标签（单测命名验证） | `test_0930_only_rows_are_fail_closed_never_available` / `test_all_0930_rows_can_never_produce_available` 已跑绿 | 09:30+ 永不 available；fallback="open_gap" 恒在 | ✓ PASS |

### Probe 执行

无 probe 脚本（Phase 20 为数据层/服务层阶段，验证通过 pytest 行为测试完成）。N/A。

### 需求覆盖 (Requirements Coverage)

| Requirement | 来源计划 | 描述 | 状态 | 证据 |
| ----------- | -------- | ---- | ---- | ---- |
| DATA-04 | 20-02 | 受管竞价列 + probe 门控 + fail-closed | ✓ SATISFIED | 注册表 + 读路径左联 + 矩阵测试全绿 |
| DATA-05 | 20-01 | `auction_sync` 湖 + `kline_auction/date={d}/` 分区 + 09:30 排除 | ✓ SATISFIED | 写路径 + 视图登记 + 12 项测试全绿 |
| DATA-06 | 20-02 | 派生未匹配金额 proxy + 回退 | ✓ SATISFIED | `compute_auction_unmatched_amount` + proxy 三测试全绿 |

### 硬边界核验 (Hard Boundaries)

| # | 边界 | 状态 | 证据 |
| ---- | ---- | ---- | ---- |
| 1 | Fail-closed：probe 非 available → 列缺席、回退 `open_gap`，绝不静默填充 | ✓ VERIFIED | `attach_auction_columns:70-73` + `test_non_available_statuses_keep_absent` |
| 2 | 09:30 bar 永不标集合竞价（湖内结构性排除） | ✓ VERIFIED | `auction_sync.py:117-126` + provider 同谓词 + `test_0930_excluded` + probe 回归 |
| 3 | 真实 vs 派生分列，永不相加/混排 | ✓ VERIFIED | `test_unmatched_proxy_never_mixed_with_real` |
| 4 | 注册纪律：auction_* 在 `ENRICHED_COLUMNS`+`BY_CATEGORY["auction"]`，不在 `ENRICHED_STORAGE_COLS`/`_ALL_INDICATOR_COLS` | ✓ VERIFIED | `test_registry_discipline` + 源码 grep |
| 5 | 读路径 probe×分区双闸门；诚实按日空态 | ✓ VERIFIED | `attach_auction_columns:70-84` + 矩阵测试 |
| 6 | 原子写（.tmp + replace，无残留） | ✓ VERIFIED | `auction_sync.py:38-47` + `test_atomic_write_leaves_no_tmp` |
| 7 | 防 fan-out：symbol 级去重 | ✓ VERIFIED | `auction_columns.py:96` `unique(subset=["symbol"], keep="last")` + `test_partition_multi_row_dedup_no_fanout` |
| 8 | 零新增外部运行时依赖 | ✓ VERIFIED | 六笔 Phase-20 提交未触碰 pyproject.toml / uv.lock / requirements*.txt / package.json / 任何 lockfile；`auction_sync.py`/`auction_columns.py` 仅用 stdlib + polars + app 模块 |

### 反模式扫描 (Anti-Patterns Found)

| File | Pattern | Severity | Impact |
| ---- | ------- | -------- | ------ |
| — | 无债务标记（TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER） | — | 无 |
| — | 无 stub 模式（return null/空实现/硬编码空数据） | — | grep 命中均为合法错误路径空回退（`preferences.load` 异常返回 `{}`、`table_schema` 缺视图返回 `[]` 等），非 stub |

### 人工验证所需 (Human Verification Required)

Phase 20 为后端数据层，六笔提交零前端改动（git 证实）。以下 4 项为 UI-SPEC `backstop` 项——属 Phase 23 前端渲染面的视觉/文案行为，本期无显式代码证据，按 backstop 契约标记 `insufficient_spec` → 人工验证（绝不静默放行）：

#### 1. 竞价列/组分栏文案安全换行
**Test:** Data 页竞价数据面板竞价列可用性 section 中，列名（`竞价量（股）`）、组标签（`真实集合竞价`/`派生 / 虚拟成交`）在窄面板换行
**Expected:** `overflow-wrap:anywhere` 生效，不溢出 `max-w-2xl` 面板
**Why human:** UI 渲染本体属 Phase 23；后端 DTO 契约已绿（`/api/data/schema/auction` 返回单位描述），但呈现需浏览器目检

#### 2. fail-closed 长文案换行包裹
**Test:** `竞价列不可用` fail-closed body 长文案（含「09:30 起的连续竞价 bar 不会被标记为集合竞价数据」）在窄面板完整可见
**Expected:** 换行包裹、不截断、不溢出
**Why human:** 需浏览器目检；无代码证据

#### 3. 竞价湖覆盖 {N} 天单复数
**Test:** 盘后管道 `auction_cover_days`（daily_pipeline.py:596）驱动覆盖文案；0 天不得渲染为「可用」
**Expected:** 0 天显示诚实空态；{N} 用 mono/tabular-nums
**Why human:** 覆盖天数已由后端计算，但其 UI 消费（Phase 23）本期未实现；无代码证据

#### 4. Phase 16 既有长文案换行不回归
**Test:** Phase 16 probe 判定卡片（`竞价数据探测失败：{message}。…`）长文案换行行为保持
**Expected:** 既有换行行为不回归
**Why human:** Phase 20 未触碰前端，需浏览器回归目检；无代码证据

### 差距总结 (Gaps Summary)

无后端差距。全部 18 项 must-have 真相（4 成功标准 + 14 计划真相）在代码与行为测试中证实；8 项硬边界全部满足；35 项目标测试 + 14 项相关回归全绿；零新增运行时依赖；六笔 Phase-20 提交文件范围与 SUMMARY 声明一致且与用户未提交工作（`frontend/src/pages/Watchlist.tsx`）零交集。

唯一未决项为 4 项 UI-SPEC `backstop`（前端渲染/文案行为），属 Phase 23 前端面的延迟验证项——按契约 `insufficient_spec` 转人工验证，故整体状态为 **human_needed**（后端数据层达标，前端视觉行为待 Phase 23 后复核）。

---

_Verified: 2026-08-05_
_Verifier: Claude (gsd-verifier)_
