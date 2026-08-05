---
phase: 20-auction-data
plan: 2
subsystem: data
tags: [polars, parquet, auction, read-path, probe-gated, registry, schema, derived-proxy]

# Dependency graph
requires:
  - phase: 16
    provides: auction_probe verdict seam (DATA-03, resolve_auction_probe / AuctionProbeStatus / _ERROR_DETAIL_MAX)
  - phase: 20
    plan: 1
    provides: kline_auction/date={d}/part.parquet 湖 (canonical 四列) + DuckDB 视图登记 + Step 2.6 写路径
provides:
  - 受管竞价列注册表: ENRICHED_COLUMNS 增 auction_volume / auction_amount / auction_unmatched_amount (估算标注) + ENRICHED_COLUMNS_BY_CATEGORY["auction"]; 绝不进 ENRICHED_STORAGE_COLS / _ALL_INDICATOR_COLS (注释声明读路径注入)
  - attach_auction_columns 读路径左联 (probe×分区双闸门, symbol 级去重防 fan-out, fail-closed 到 open_gap)
  - ScreenerService._load_enriched_for_date 三处 return 经 _attach_auction 注入 (读路径异常也 fail-closed)
  - api/data.py _SCHEMA_VIEWS["auction"]="kline_auction" + _TABLE_FIELD_DESC["kline_auction"] (单位中文描述)
  - DATA-06 compute_auction_unmatched_amount 派生未匹配金额 proxy (委托量输入可得才派生, 与真实列分列)
affects: [21 strategy (消费竞价列), 23 frontend (Data 页 schema / 竞价列展示)]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 5720      # chars/4 over files actually changed (22882 chars / 4)
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []          # zero new external runtime dependencies (no install surface)
  patterns:
    - "受管增强列双注册: ENRICHED_COLUMNS + BY_CATEGORY['auction'] 是唯一权威; 存储窄表与计算闭包 grep 门禁锁死"
    - "probe×分区双闸门读路径: resolve_auction_probe().status==available 且 kline_auction/date={d}/part.parquet 存在且有行, 任一不通过原样返回"
    - "诚实按日/按标的空态: 无分区/空分区 → 列缺席 (非 null-as-present); 分区有行但某 symbol 缺席 → 该行 null"
    - "防 fan-out: auction 帧左联前 unique(subset=['symbol'], keep='last') 去重"
    - "派生列独立命名 + 估算标注: auction_unmatched_amount = 虚拟未匹配量 × 虚拟参考价, 与真实列永不求和/混排"

key-files:
  created:
    - backend/app/services/auction_columns.py
    - backend/tests/test_auction_columns.py
  modified:
    - backend/app/indicators/pipeline.py
    - backend/app/services/screener.py
    - backend/app/api/data.py

key-decisions:
  - "auction_* 三列注册进 ENRICHED_COLUMNS + BY_CATEGORY['auction'], 绝不进 ENRICHED_STORAGE_COLS (窄表=可从 OHLCV 重算) 与 _ALL_INDICATOR_COLS (破坏 _resolve_needed 计算闭包不变量); _ALL_INDICATOR_COLS 上方加注释声明读路径左联注入 (硬边界 4)"
  - "attach_auction_columns 对 not_configured / fail_closed / error 与 available+无分区/空分区 一律原样返回 df (列缺席, 功能 fail-closed 到 open_gap, 绝不静默填充) (硬边界 1/5)"
  - "真实列 (auction_volume/auction_amount) 与派生列 (auction_unmatched_amount) 独立命名、独立 schema; 描述带「估算, 非真实成交」标注, 永不求和/混排 (硬边界 3)"
  - "ScreenerService._attach_auction 以 try/except 包住注入 (读路径异常也 fail-closed: 缺列而非 500); 注入发生在 instruments JOIN 之后, 保证 name 等列已就位"
  - "compute_auction_unmatched_amount 缺任一输入列 (auction_unmatched_volume / auction_virtual_price) → 原样返回, 列缺席即策略回退量比+金额强度 (engine.py:496-497 缺失列静默跳过)"

patterns-established:
  - "test_auction_columns.py hermetic 模式: 生产 import 放测试函数内; monkeypatch auction_columns.resolve_auction_probe 返回固定 verdict; 手工写 kline_auction/date=*/part.parquet 分区 (repo_env fixture 隔离 data_dir + DataStore)"
  - "ScreenerService 慢路径 hermetic 测试: 写 kline_daily_enriched 单日分区 (14 存储列), _load_enriched_for_date 经缓存/慢路径返回帧, 断言竞价列带/缺"

requirements-completed: [DATA-04, DATA-06]

# Coverage metadata (#1602) — per-deliverable traceability for verify-work UAT routing.
coverage:
  - id: D1
    description: "受管竞价列注册纪律: auction_volume/auction_amount/auction_unmatched_amount 在 ENRICHED_COLUMNS + BY_CATEGORY['auction'], 绝不在 ENRICHED_STORAGE_COLS / _ALL_INDICATOR_COLS; 派生列描述带估算标注"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_registry_discipline"
        status: pass
    human_judgment: false
  - id: D2
    description: "probe×分区双闸门矩阵: available+分区注入 / available+无分区缺列 / not_configured/fail_closed/error 缺列+open_gap 恒在 / 空分区缺列 / 多窗口行去重防 fan-out"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_available_with_partition_injects_real_columns"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_available_without_partition_keeps_absent"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_non_available_statuses_keep_absent"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_partition_empty_keeps_absent"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_partition_multi_row_dedup_no_fanout"
        status: pass
    human_judgment: false
  - id: D3
    description: "ScreenerService._load_enriched_for_date as-of 帧注入: probe available 带真实竞价列, probe 非 available 不带 (诚实 fail-closed)"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_screener_frame_carries_auction_columns"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_screener_frame_absent_when_probe_not_available"
        status: pass
    human_judgment: false
  - id: D4
    description: "schema 面: _SCHEMA_VIEWS['auction']='kline_auction' + _TABLE_FIELD_DESC['kline_auction'] 单位描述; kline_enriched schema 自动带出竞价三列与估算标注"
    requirement: DATA-04
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_schema_surface_lists_kline_auction"
        status: pass
    human_judgment: false
  - id: D5
    description: "DATA-06 派生未匹配金额 proxy: 委托量输入可得 → 乘积派生; 缺输入 → 列缺席; 与真实列 schema 独立, 描述带估算/非真实成交标注"
    requirement: DATA-06
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_unmatched_proxy_input_present"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_unmatched_proxy_input_absent"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_unmatched_proxy_never_mixed_with_real"
        status: pass
    human_judgment: false

# Metrics
duration: 41min
completed: 2026-08-05
status: complete
---

# Phase 20 Plan 2: 竞价数据层 — 受管竞价列注册表 + 读路径左联 + DATA-06 派生 proxy Summary

**DATA-04/06 读路径端到端成立：`auction_volume`/`auction_amount` 登记为受管增强列（`ENRICHED_COLUMNS` + 新分类 `"auction"`，绝不进存储窄表/计算闭包），由 `attach_auction_columns` 按 probe×分区双闸门从 `kline_auction` 湖左联注入日线帧——probe 非 `available` 或缺分区时列缺席、功能 fail-closed 到派生 `open_gap`，从不静默填充；`ScreenerService._load_enriched_for_date` 三处 return 经 `_attach_auction` 注入策略 as-of 帧，`kline_auction` 登记进 `_SCHEMA_VIEWS`/`_TABLE_FIELD_DESC`（单位中文描述）；DATA-06 派生 `auction_unmatched_amount`（估算, 非真实成交）在委托量输入可得时按 `虚拟未匹配量 × 虚拟参考价` 派生，缺输入即列缺席、与真实列分列永不相加。**

## Performance

- **Duration:** 41 min
- **Tasks:** 3
- **Files modified:** 5 (2 created, 3 modified)
- **Tests:** test_auction_columns.py 12 passed; 回归 test_auction_probe.py 11 passed, test_screener_etf.py 10 passed, test_auction_sync.py 12 passed

## Accomplishments

- 受管列注册表：`ENRICHED_COLUMNS` 在 JOIN 列之前追加 `auction_volume`（竞价量, 单位: 股）、`auction_amount`（竞价金额, 单位: 元）、`auction_unmatched_amount`（派生未匹配金额, 估算, 非真实成交）；`ENRICHED_COLUMNS_BY_CATEGORY["auction"]` 收录三列；`_ALL_INDICATOR_COLS` 上方注释声明「auction_* 列不由 compute_indicators 计算, 由读路径从 kline_auction 湖左联注入; 缺列即 probe 不可用」。`test_registry_discipline` grep 门禁锁死「不进存储窄表、不进计算闭包」。
- `attach_auction_columns` 读路径左联（`auction_columns.py`）：第一闸门 `resolve_auction_probe().status == available`，第二闸门 `kline_auction/date={d}/part.parquet` 存在且有行；任一不通过原样返回。左联前 `unique(subset=["symbol"], keep="last")` 去重，防多窗口行 fan-out 把日线帧拉成 N 行/标的（`test_partition_multi_row_dedup_no_fanout` 锁死）。
- probe×列矩阵回归：`available`+分区注入真实列 / `available`+无分区缺列（诚实按日空态）/ `not_configured`/`fail_closed`/`error` 三态缺列且 `open_gap` 恒在 / 空分区缺列；error 详情沿用 probe 截断（≤ `_ERROR_DETAIL_MAX` 200）。
- 策略 as-of 帧注入：`ScreenerService._attach_auction`（try/except fail-closed）接入 `_load_enriched_for_date` 三个 return 点（最新日缓存 / repo 历史缓存 / 慢路径），注入发生在 instruments JOIN 之后；probe 非 available 或读路径异常时列缺席而非 500。
- API/schema 面：`_SCHEMA_VIEWS["auction"]="kline_auction"`，`_TABLE_FIELD_DESC["kline_auction"]` 含 `auction_volume`（竞价量, 单位: 股）/ `auction_amount`（竞价金额, 单位: 元）/ `datetime`（竞价时间戳 09:15-09:25）；`kline_enriched` schema（=`ENRICHED_COLUMNS` 同一引用）自动带出竞价三列与估算标注。
- DATA-06 派生 proxy：`compute_auction_unmatched_amount` 在 `auction_unmatched_volume` + `auction_virtual_price` 齐备时派生 `auction_unmatched_amount = 未匹配量 × 虚拟参考价`；缺任一输入列原样返回（列缺席 → 策略回退量比+金额强度，engine.py 缺失列静默跳过）。`attach_auction_columns` 在分区帧带输入列时同帧派生并注入，标准湖（canonical 四列）下派生列自然缺席。
- Hermetic 测试：12 项全绿（注册纪律 / 双闸门矩阵 / as-of 帧注入 / schema 面 / proxy 三测试），无网络；`test_auction_probe.py` 回归 11 项全绿（诚实标签与 `_ERROR_DETAIL_MAX` 不回归）。

## Task Commits

Each task was committed atomically:

1. **Task 1: 受管列注册表 + `attach_auction_columns` 读路径左联 + probe×列矩阵回归** - `c6c0976` (feat)
2. **Task 2: 策略 as-of 帧注入 + API/schema 面（`kline_auction` 登记 + 竞价列中文描述）** - `377f1b1` (feat)
3. **Task 3: DATA-06 派生竞价未匹配金额 proxy — 委托量输入可得才派生, 估算标注, 与真实列分列** - `4a1d8aa` (feat)

## Files Created/Modified

- `backend/app/services/auction_columns.py` (new) - `attach_auction_columns`（probe×分区双闸门左联 + symbol 级去重防 fan-out）/ `compute_auction_unmatched_amount`（派生估算, 缺输入原样返回）
- `backend/tests/test_auction_columns.py` (new) - 12 项 hermetic 测试（注册纪律 / 双闸门矩阵 / 去重回归 / screener 帧注入 / schema 面 / proxy 三测试）
- `backend/app/indicators/pipeline.py` - `ENRICHED_COLUMNS` 增三列 + `ENRICHED_COLUMNS_BY_CATEGORY["auction"]` + `_ALL_INDICATOR_COLS` 上方注释（不进存储窄表/计算闭包）
- `backend/app/services/screener.py` - `_attach_auction` 方法 + `_load_enriched_for_date` 三处 return 注入
- `backend/app/api/data.py` - `_SCHEMA_VIEWS["auction"]="kline_auction"` + `_TABLE_FIELD_DESC["kline_auction"]`

## Decisions Made

- `auction_*` 三列注册进受管注册表但绝不进 `ENRICHED_STORAGE_COLS` / `_ALL_INDICATOR_COLS`（RESEARCH Divergence 3/4）：存储窄表=可从 OHLCV 重算，计算闭包=可重算不变量，竞价列存在性是 probe 条件，两处都不得混入。
- `attach_auction_columns` 对非 available 三态 + available 无分区/空分区一律原样返回 df——诚实缺列而非 null 列、绝不静默填充（硬边界 1/5）。
- 真实/派生分列：`auction_unmatched_amount` 独立命名 + 「估算, 非真实成交」描述；`attach_auction_columns` 只在输入列齐备时同帧派生，标准湖（canonical 四列）下派生列缺席、策略自然回退。
- `ScreenerService._attach_auction` 以方法内 import（避免循环导入）+ try/except 包裹注入，读路径异常也 fail-closed（缺列而非 500）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test] `test_unmatched_proxy_never_mixed_with_real` 断言过严（「真实成交」子串误伤「非真实成交」）**
- **Found during:** Task 3
- **Issue:** plan 的 Registry 断言写「描述不含『真实成交』同义表述」，但批准描述串为「派生未匹配金额 (估算, 非真实成交; 委托量输入可得时存在)」——含子串「真实成交」但以「非」否定，断言 `"真实成交" not in desc` 误失败。
- **Fix:** 断言改为验证契约语义：描述含「估算」、含「非真实成交」否定标注、且与真实列 `auction_amount` 描述串不同（schema 独立、绝非真实成交同义描述）。
- **Files modified:** backend/tests/test_auction_columns.py
- **Verification:** proxy 三测试绿，12 项全绿
- **Committed in:** 4a1d8aa (Task 3 commit)

**2. [Rule 1 - Test] schema 端点静态回退测试需显式 `app.state.repo`**
- **Found during:** Task 2
- **Issue:** `table_schema` 路由的 `repo = request.app.state.repo` 位于 try/except 之外；bare FastAPI 无 `app.state.repo` 时 AttributeError 直接传播，无法触发静态回退。
- **Fix:** 测试在调用前设 `app.state.repo = None`——`None.execute_all` 在 try 内抛错 → 路由回退到 `_TABLE_FIELD_DESC` 静态定义（与无数据时生产行为一致）。
- **Files modified:** backend/tests/test_auction_columns.py
- **Verification:** `test_schema_surface_lists_kline_auction` 绿
- **Committed in:** 377f1b1 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 test-level fixes)
**Impact on plan:** 均为测试断言/夹具适配, 无生产行为变更、无 scope creep。

## Issues Encountered

- gsd-tools `query commit` 在本次环境静默 no-op（无输出、无提交、无报错）——按契约回退到 plain `git commit`，并确认只 stage 任务相关文件（绝不含 `frontend/src/pages/Watchlist.tsx` / `backend/uv.lock` 等用户未提交工作）。
- 并行 20-01 执行器（Executor2001）编辑 `repository.py` 时出现中间态语法损坏（`_register_views` 语句块错位），一度阻塞我的测试导入链（`app.tickflow.repository` 在 import 链上）；经 hub 协调后对方修复并确认（`ast.parse` + 12 项测试绿）。我未触碰任何 20-01 文件。
- 我的三笔提交（`c6c0976` / `377f1b1` / `4a1d8aa`）与 20-01 的提交（`642dec8` / `1e930e2` / `1b5bb97`）在同一分支交错排列，但文件集完全不相交（20-01: auction_sync/preferences/daily_pipeline/repository；20-02: pipeline/auction_columns/screener/data + test_auction_columns）。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 21 策略族可依赖策略 as-of 日线帧上的 `auction_volume`/`auction_amount`（probe available 时）与 `auction_unmatched_amount`（委托量输入可得时）；缺列时引擎按既有行为静默跳过（engine.py:496-497），回退量比+金额强度。
- Data 页（23 前端）可消费 `GET /api/data/schema/auction`（kline_auction 字段）与 `/schema/enriched`（竞价三列中文描述含单位与估算标注）。
- 零新增外部运行时依赖，无 package legitimacy checkpoint。

---
*Phase: 20-auction-data*
*Completed: 2026-08-05*

## Self-Check: PASSED

- 文件存在性: `auction_columns.py` / `test_auction_columns.py` / `pipeline.py` / `screener.py` / `data.py` / `20-02-SUMMARY.md` 全部 FOUND。
- 提交存在性: `c6c0976` / `377f1b1` / `4a1d8aa` 全部 FOUND。
