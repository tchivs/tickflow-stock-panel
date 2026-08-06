---
phase: 26-auction-history-chart
verified: 2026-08-06T09:10:00Z
status: passed
score: 14/14 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
---

# Phase 26 验收:历史竞价图 + 派生列复活 (Auction History Chart)

**Phase Goal:** User can view per-symbol historical auction volume/amount trends in the stock drill-down (ECharts, zero new deps) via a read-only aggregate endpoint; the lake ingestion path preserves delegation-volume inputs so the derived 虚拟未匹配金额 column becomes live data instead of absent columns.
**Verified:** 2026-08-06
**Status:** passed
**Re-verification:** No — initial verification

## 结论 (verdict)

**must-haves 14/14 全部验证通过, 0 BLOCKER, 0 硬性 human_items。**

CHART-01 (只读竞价历史聚合端点)、CHART-02 (前端双轴竞价历史图)、CHART-03 (湖摄入保留委托量输入列 + 派生列复活) 三条需求全部以真实代码 + 测试证据核实。验证运行结果与声明一致:后端相关套件 **127 passed**、前端 `npm run build` **green**、Playwright e2e **4 passed / 8 skipped**。git 审计确认 `frontend/src/pages/Watchlist.tsx` 未被任何 phase 26 commit 触碰,用户未提交改动原样保留 (133 行 diff)。

## 逐需求证据 (CHART-01..03)

### CHART-01 — GET /api/kline/auction/history 只读聚合端点

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 每交易日末行 (09:25 最终撮合) 聚合,rows 按 date 升序,带 row_count/min_datetime/max_datetime 粒度标注;源提供时另含 auction_unmatched_volume/auction_virtual_price | ✓ VERIFIED | `backend/app/api/auction_history.py` sort+unique keep="last" 末行语义;`test_auction_history.py#test_last_row_aggregation_across_days` 断言 4 日升序、每行 09:25 值 (volume=300/amount=3000)、row_count==3、min=09:16、max=09:25、window="09:15-09:25"、unit 标注 |
| 2 | 空湖/该 symbol 无行 → 200 `{available:false, rows:[]}` (绝不 404/500/0 填充) | ✓ VERIFIED | `auction_history.py` 湖根目录 is_dir 检查 + 分区过滤后 frames 空 → `_empty_response`;`test_empty_lake_returns_available_false`、`test_no_symbol_rows_returns_available_false` 均断言 200 + available:false + coverage 0 |
| 3 | 非法 symbol/days → 显式 400 (非 FastAPI Query ge/le 的 422) | ✓ VERIFIED | `_SYMBOL_RE=^\d{6}\.(SH\|SZ\|BJ)$` 全匹配 + handler 内 `1 <= days <= 120` 显式判断;`test_invalid_symbol_returns_400` (abc/000001/000001.XX/../../x) 与 `test_invalid_days_returns_400` (0/-5/121) 参数化断言 400 |
| 4 | probe 非 available → 200 available:false + probe.status 透传 (not_configured/fail_closed/error) | ✓ VERIFIED | `auction_history.py` 第一闸门 `probe.status != available` → `_empty_response`;`test_probe_non_available_returns_empty_with_status` 三态参数化断言 status 透传 + mode vip |
| 5 | guest 掩码 → 200 `{available:false, rows:[], mode:'guest'}` 量/价零泄露;端点加入 `_GUEST_READ_GET_PATHS` | ✓ VERIFIED | `auction_history.py` `getattr(request.state,'reviewer_principal',None)` 判定;`main.py:784` 白名单含 `/api/kline/auction/history`;`test_guest_mask_returns_empty_mode_guest` 断言 mode guest + coverage 0;`test_main_guest_whitelist_and_router_registration` 断言白名单 2 处 + include_router |
| 6 | POOL-03 GET-only 零执行权;严禁 kline.get_daily 空库 live-fetch 兜底 | ✓ VERIFIED | AST 守卫 `test_auction_history_no_execution_imports` / `test_auction_history_api_is_get_only` / `test_auction_history_has_no_write_path` 全绿;源码 grep 确认零 sync_daily_batch/kline_sync/daily_pipeline/write_parquet/os.replace/unlink/mkdir,import 仅 logging/re/datetime/polars/fastapi/auction_probe |

### CHART-03 — 湖摄入 canonical 扩为 4 必需 + 2 可选

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 7 | CANONICAL_AUCTION_COLS=4 不变 + OPTIONAL_AUCTION_COLS=2;两处 keep 扩宽按存在性过滤;源不提供 → 仍 4 列 (向后兼容) | ✓ VERIFIED | `auction_sync.py` CANONICAL 保持 4 列 + `OPTIONAL_AUCTION_COLS=[auction_unmatched_volume, auction_virtual_price]`;`auction_sync.py` keep 与 `custom/provider.py _normalize_auction` keep 均按 `if c in df.columns` 过滤;`test_sync_without_optional_cols_stays_four_cols` 断言分区仍 == CANONICAL_AUCTION_COLS;既有 `test_sync_writes_partition` (df.columns == CANONICAL_AUCTION_COLS) 保持绿 |
| 8 | merge-upsert `pl.concat(how="diagonal_relaxed")` — 旧 4 列分区 + 新 6 列写入并集不 SchemaError | ✓ VERIFIED | `auction_sync.py` merge-upsert 用 `how="diagonal_relaxed"`;`test_sync_partition_merge_old_four_plus_new_six` 预写 4 列旧分区 + 再 sync 6 列新行 → 无异常、列 = 并集、旧行可选列 null (诚实)、无 .tmp 残留 |
| 9 | 读路径派生激活:分区含输入列 → attach 输出含 auction_unmatched_amount (= 乘积, 估算);缺输入列 → 诚实缺列;派生与真实列永不相加 | ✓ VERIFIED | `auction_columns.py` 既有 `compute_auction_unmatched_amount` 分支 (零改动, git 0 commits);`test_attach_derives_unmatched_amount_from_partition_inputs` 断言 5000*8.4==42000.0 且真实列照常;`test_attach_no_unmatched_when_inputs_absent` 断言无输入列 → 无 auction_unmatched_amount (不 0 填);纪律回归 `test_unmatched_proxy_never_mixed_with_real` 绿 |
| 10 | `_TABLE_FIELD_DESC["kline_auction"]` 补 3 字段带「估算」标注 | ✓ VERIFIED | `backend/app/api/data.py` kline_auction 字段含 auction_unmatched_volume/auction_virtual_price (估算输入列) + auction_unmatched_amount (估算, 非真实成交) |

### CHART-02 — 前端 ECharts 双轴竞价历史图

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 11 | 查询链路:api.auctionHistory (GET) + QK.auctionHistory 工厂 (不入 SSE_INVALIDATE_PREFIXES) + useAuctionHistory hook (enabled:!!symbol, staleTime 5min) | ✓ VERIFIED | `api.ts` AuctionHistoryRow/AuctionHistoryResponse 接口 + auctionHistory 方法;`queryKeys.ts` auctionHistory 工厂 → ['kline-auction-history', symbol, days];`SSE_INVALIDATE_PREFIXES` 不含该 key;`useSharedQueries.ts` useAuctionHistory |
| 12 | AuctionHistoryChart 双轴 ECharts:左轴柱=auction_volume (股),右轴线=auction_amount (元),category x=date;只画真实列,绝不混排派生列 | ✓ VERIFIED | `AuctionHistoryChart.tsx` buildOption 单 grid 双 yAxis,series 仅 竞价量(bar,yAxisIndex 0)/竞价金额(line,yAxisIndex 1);派生列 grep = 0 (api.ts:742 为既有 Phase 23 类型,非本图渲染);生命周期 init/ResizeObserver/dispose + useChartTheme |
| 13 | StockPreviewDialog 第三 toggle「竞价历史」(aria-pressed) + showAuction state → StockPanel showAuction prop → 条件渲染 AuctionHistoryChart (与分时同槽位) | ✓ VERIFIED | `StockPreviewDialog.tsx` showAuction state + Gavel 图标「竞价历史」按钮 + 透传 showAuction;`StockPanel.tsx` showAuction prop + `{showAuction && <AuctionHistoryChart ...>}` |
| 14 | 诚实空态 (probe 非 available/available:false/rows 空 → EmptyState「无历史竞价数据」+ 09:15-09:25 窗口标注 + 降级「数据源未配置」;guest → 空态零泄露);aria role=img + aria-label | ✓ VERIFIED | `AuctionHistoryChart.tsx` showChart 判定 + `chart.clear()` 绝不零值柱 + EmptyState + 窗口 chip/tooltip + role="img" aria-label="历史竞价量/金额趋势图";e2e 三态空态用例全绿 |

**Score:** 14/14 truths verified (0 present-behavior-unverified)

## 守卫审计

| Guard | Assertion | Evidence |
|-------|-----------|----------|
| 零执行权 (POOL-03) | auction_history.py 纯读 GET-only,AST 守卫绿,无 live-fetch 兜底 | AST 三守卫测试绿 + 源码 import/write-pattern grep 0 命中 |
| 诚实空态 | available:false 200 非 404;不 0 填 | 后端空态测试 + e2e available:false/probe 非 available 用例 |
| 派生 vs 真实隔离 | 派生 auction_unmatched_amount 永不相加/混排;描述带「估算」 | `test_unmatched_proxy_never_mixed_with_real` 绿;AuctionHistoryChart grep 派生列 0 命中;data.py 描述带「估算」 |
| guest 掩码 | 量/价敏感列 guest 空态零泄露 | `test_guest_mask_returns_empty_mode_guest` 绿 + e2e guest 用例断言 canvas 0 + 无量/价文本 |
| Watchlist.tsx 未触碰 | 用户未提交改动不被覆盖 | git log 确认 phase 26 commit 范围零触碰;`git status` 仅剩 `M frontend/src/pages/Watchlist.tsx` (133 行 diff 原样) |
| 零新依赖 | 无新增 npm/pip 运行时依赖 | package.json/pyproject/requirements 在 dc70f0e~1..HEAD 范围零 diff;echarts/lucide-react 在册 |

## 验证运行记录 (Verifier 亲自执行)

| 验证项 | 命令 | 结果 |
|--------|------|------|
| CHART-01/03 单元 | `cd backend && .venv/bin/python -m pytest tests/test_auction_history.py tests/test_auction_sync.py tests/test_auction_columns.py -x -q` | **48 passed** |
| 回归守卫 | `cd backend && .venv/bin/python -m pytest tests/test_guest_masking.py tests/test_pool_hub.py tests/test_auction_probe.py tests/test_auction_strategy_family.py -x -q` | **79 passed** |
| 后端相关合计 (baseline) | 48 + 79 | **127 passed** (与声明一致) |
| 前端构建 | `cd frontend && npm run build` | **green** (tsc -b + vite build, ~10.6s) |
| e2e | `cd frontend && npx playwright test e2e/auction-history.spec.ts` | **4 passed / 8 skipped** (desktop 4 全绿;mobile/host skip) |
| git 分支 | `git branch --show-current` | `gsd/v2.1-planning` ✓ |
| 26-01 提交链 | `git log dc70f0e~1..06944ed` | `dc70f0e` (feat CHART-01) + `81e9c25` (feat CHART-03) + `06944ed` (docs) = **3 commits** ✓ |
| 26-02 提交链 | `git log edc4a4d~1..5a34020` | `edc4a4d` (feat) + `51d53d3` (test) + `5a34020` (docs) = **3 commits** ✓ |

## Blockers

**0。**

## Human Items

**0 (必需)。** 所有验收行为均已有代码/测试/e2e 证据。可选建议(非阻塞,不影响 passed 判定):ECharts 图真实渲染观感 (双轴柱/线配色、窗口标注位置、tooltip 交互) 属美学判断,`26-VALIDATION.md` 亦列为 manual 项 — 建议接入真实 auction 数据源并开启 EOD 竞价同步后人工打开 /screener 个股弹窗复核观感,届时图自动点亮 (当前湖 0 分区,诚实空态是本设计预期)。

## Gaps Summary

无。SUMMARY.md 声称的行为全部经真实代码/测试核实,未发现 stub、未接线或数据空心化的证据。

---
_Verified: 2026-08-06_
_Verifier: Claude (gsd-verifier, Verifier26)_
