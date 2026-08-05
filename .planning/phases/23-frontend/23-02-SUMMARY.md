# 23-02 SUMMARY — DateNavigator 按交易日浏览 + 竞价列钻取 UI (FRONT-01/02 前端面)

**Phase:** 23-frontend · **Plan:** 23-02 · **Wave:** 2
**Status:** ✅ COMPLETE — 3/3 tasks green, committed atomically
**Date:** 2026-08-05

## Objective

在既有 PoolHubPage 上落地 Phase 23 (FRONT-01/02) 的 UI 面: (1) **DateNavigator** (‹ › 步进 + 日期下拉 + 「最新」复位) 按交易日浏览股池, `selectedDate` 进 queryKey 触发 as_of 重取并刷新策略卡片与钻取明细, 非交易日物理不可达 (白名单日期集 + 下标步进, PIT-5), 无快照日渲染独立诚实空态「该日期无股池快照」(PIT-2); (2) **股池钻取竞价列** — StockListTable 按服务端 `auction_columns` 声明分组渲染真实集合竞价 (竞价量/股、竞价金额/元) 与派生·虚拟成交 (竞价量比/×、虚拟未匹配金额/元·估算), 两行分组表头 + 单位标注 + tooltip, probe/盘前状态徽标诚实呈现 (fail-closed 空态或派生标注, H3 双轨), 绝不暗示存在真实竞价数据。**前置 precondition 门 (W-23-02-1) 已过**: `api.poolDates`/`api.poolHistory` + `QK.poolDates`/`QK.poolHistory` + `PoolHubRow.auction_*`/`PoolHubResponse.available`/`auction_columns` 类型与后端声明均已合入 (23-01)。

## Tasks Delivered

| Task | Deliverable | Commit |
|------|-------------|--------|
| 1 | `frontend/src/components/pool-hub/DateNavigator.tsx` (NEW) — 受控只读组件: `dates` 白名单下标步进, ‹ › 严格在数组内移动 (‹=idx+1 更早 / ›=idx-1 更近), 边界/`idx===-1` 双禁用不猜测; 原生 select 只列白名单日期, 空 dates → disabled + `暂无历史日期`; `selectedDate !== null` 时「最新」复位按钮 → onChange(null) 回 `/api/pool/hub`; loading/error 行内状态 (role=status/alert)。`frontend/src/pages/PoolHubPage.tsx` — `selectedDate: string \| null` state + `datesQuery` (QK.poolDates/api.poolDates, retry:1) + `poolQuery` 按 selectedDate 切换 `QK.poolHistory(d)`/`QK.poolHub()` (历史必走 /api/pool/history, PIT-1) + `placeholderData: (prev) => prev` 平滑切换; `asOf = data?.as_of ?? selectedDate ?? null` (占位期显示旧载荷真实 as_of, 绝不伪造目标日); 渲染序: DateNavigator → 加载骨架 → 失败 alert → **available:false 独立空态** (CalendarX, 短路于零池之前) → 零池 → 有结果分支 | `83545e4` |
| 2 | `frontend/src/components/pool-hub/StockListTable.tsx` — 新可选 prop `auctionColumns?: AuctionColumnsDecl \| null`; 两行分组 thead (基础列 rowSpan=2 + `真实集合竞价` colSpan=2 accent + `派生 · 虚拟成交` colSpan=2 secondary), 成员列头带单位 (`竞价量（股）`/`竞价金额（元）`/`竞价量比（×）`/`虚拟未匹配金额（元·估算）`) + `title` tooltip; 行单元格 `fmtBigNum` (万/亿) + 量比 `toFixed(2)+'×'` (不用 fmtPct), null/NaN → `—`, 数值列不套涨跌色; `open_gap` 留在基础列「开盘涨幅」不重复渲染; `auction_columns.real` 空 → 真实组整组不渲染 + warning; guest/无声明 → 既有单行表头不变; 局部组件 `AuctionColumnStatusBadge` (export, 满足 UI-SPEC §4.3): 消费 `useAuctionProbe`(30s stale) + `useQuoteStatus`, 四态 (info 可用 / warning 未接入 / warning 快照无真实 / 盘前 secondary) — 冻结列存在性驱动数据列与主徽标, 实时 probe/时段只驱动 warning 分支与盘前行 (H3 双轨) | `acb0e21` |
| 3 | `frontend/src/pages/PoolHubPage.tsx` — 向 `<StockListTable>` 传 `auctionColumns={data?.auction_columns ?? null}` + 钻取区 h2 与表之间渲染 `<AuctionColumnStatusBadge>` (仅 `data?.auction_columns` 存在时挂载, 避免 guest/无声明时发 probe 请求); 零池分支补 `available !== false` 门 (PIT-2 真短路)。`frontend/e2e/pool-hub.spec.ts` — installShell 新增 `/api/pool/dates` + `/api/pool/history` (按 as_of 分派) + `/api/data/auction-probe` 路由; 新增 SC1-SC4 + SC2b/SC3b/SC3c/SC4a-d 共 10 用例; 既有用例 3 处适配 (见 Deviations) | `0fe86d2` |

## Test Results (all green)

```
cd frontend && npm run build                            # tsc -b && vite build
→ ✓ built (tsc 0 errors, vite bundle OK; 仅既有 chunk>500kB 提示非错误)
cd frontend && npx playwright test e2e/pool-hub.spec.ts
→ 34 passed, 68 skipped (非 desktop-chromium 项目), 0 failed
cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py tests/test_guest_masking.py -x -q
→ 47 passed
```

| Suite | Count | Notes |
|-------|-------|-------|
| `cd frontend && npm run build` | green | `tsc -b` 类型检查 (src/) + vite build; 零新增 npm 依赖 |
| `npx playwright test e2e/pool-hub.spec.ts` | 34 passed | desktop-chromium 项目全绿: 既有 pool-hub 用例零回归 + 10 个新 SC1-SC4 用例 |
| backend 回归 | 47 passed | `test_pool_hub` + `test_guest_masking` 不受 UI 影响, 全绿 |

**SC1-SC4 e2e 覆盖:**

| 用例 | 覆盖 |
|------|------|
| SC1 (PIT-1/PIT-5) | 初始 › disabled/‹ enabled; `‹` 步进 → subtitle 08-01 + `history?as_of=2026-08-01` 请求断言 + 卡片计数刷新 (total 2→5); 下拉选 07-31 → subtitle + history 请求; `‹` 到最旧 disabled; 「最新」→ 回 `/api/pool/hub` + 按钮消失; history 绝不含最新日 as_of |
| SC2 (PIT-2/PIT-5) | 下拉 options 只含白名单 3 日; 零池载荷 → `当日无股池结果`; 步进到 `available:false` → `该日期无股池快照` 可见且 `当日无股池结果` 不出现 + 无卡片/明细表 (渲染序短路) |
| SC2b | `dates: []` → 双按钮 disabled + 下拉 `暂无历史日期`, 最新 hub 查询照常 |
| SC3 (PIT-3) | 两行分组表头 (`真实集合竞价`/`派生 · 虚拟成交`) + 4 成员列单位 + tooltip title; 行值 `2.35×`/`123万`/`2.35亿`/`1235万`; 行级 null → 4 处 `—` |
| SC3b | `auction_columns.real: []` → 真实组带与成员列不渲染 + warning `竞价数据未接入，仅展示派生列` + 派生组保留 |
| SC3c | guest 载荷 → 无竞价列/无分组表头/无徽标, 既有 5 列结构不变 |
| SC4a/b | probe available + real 非空 → info `竞价数据可用 · 窗口 09:15-09:25`; probe fail_closed + real 空 → warning |
| SC4c | 查看日 == 今日 + `is_trading_hours:false` → secondary `盘前/休市 · 竞价窗口 09:15-09:25 未开始` 与 info 徽标并列 |
| SC4d (H3) | 历史快照 (08-01) real 非空 + 今日 probe fail_closed → 真实竞价列**仍渲染** + 徽标按 `auction_columns.real` 显示 info (历史事实不因今日状态重写) |

## Contract Compliance

- **PIT-1 (最高危)**: 历史必走 `/api/pool/history` — `poolQuery` queryKey/queryFn 按 `selectedDate` 切换 `QK.poolHistory(d)`/`api.poolHistory(d)`, 与 `QK.poolHub`/`api.poolHub` 物理分离; e2e SC1 断言步进后请求路径切到 `/api/pool/history?as_of=` 且最新日绝不打 history。
- **PIT-2 (无快照 ≠ 零池)**: `data.available === false` 独立 EmptyState (CalendarX + `该日期无股池快照`) 渲染序在零池分支之前; 因 JSX 无短路语义, 零池分支补 `available !== false` 门, 两空态互斥 (missingSnapshot 载荷 `strategies: []` 不再同时命中零池)。e2e SC2 断言两 heading 各自出现。
- **PIT-3 (列存在性服务端权威)**: `realCols.some(...)`/`derivedCols.some(...)` 只消费 `auction_columns` 声明; 行级 null 只渲染 `—` (该标的缺席), 绝不按行值推导列存在性。e2e SC3/SC3b 锁死。
- **PIT-5 (非交易日物理不可达)**: DateNavigator `idx = dates.indexOf(currentAsOf)`; ‹ › 严格下标步进, 边界/`idx===-1` 双禁用; 无「跳到最近日」分支。下拉 options = `dates` 白名单。e2e SC1/SC2/SC2b 锁死。
- **H1/H2 (真实/派生分离)**: 两行分组表头物理分隔 + 单位 (股/元/×/估算) + tooltip; `open_gap` 留在基础列「开盘涨幅」不搬入派生组不重复渲染; 数值列不套涨跌色, 无求和逻辑。
- **H3 (冻结 vs 实时双轨)**: 冻结 `auction_columns` 驱动数据列与主徽标; 实时 probe/时段只驱动 warning 分支与盘前 secondary 行; 历史快照不因今日 probe 状态重写 (e2e SC4d)。
- **H4/H5/H7**: available:false 诚实空态 / 白名单下标步进 / guest 无竞价列 (前端零处理, 服务端剥离; 徽标仅 `data?.auction_columns` 存在时挂载)。
- **零新增 npm 依赖**: 仅用 lucide 在册图标 (ChevronLeft/ChevronRight/CalendarX/CheckCircle2/AlertTriangle/Loader2); 原生 `select`/`button`, 无新包。
- **不触碰**: `frontend/src/lib/api.ts`、`frontend/src/lib/queryKeys.ts`、`backend/**`、`frontend/src/pages/Watchlist.tsx`。

## Deviations

1. **`QK.poolDates` 非函数**: 23-01 交付的 `queryKeys.ts` 定义 `poolDates: ['pool-dates'] as const` (常量数组, 非工厂); 计划示例 `QK.poolDates()` 改为 `QK.poolDates`。`QK.poolHistory(asOf)` 为函数不变。
2. **PIT-2 短路实现方式**: JSX 中「先插入分支」不足以短路 — `available:false` 载荷 `strategies` 亦为 `[]`, 会同时命中零池分支渲染两个空态。零池分支条件补 `data.available !== false` 实现真互斥 (语义 = 快照存在但零命中才显示「当日无股池结果」)。
3. **竞价列物理位置**: 计划文字「行单元格 (在 open_gap 列之后)」与 UI-SPEC §3.2 thead (竞价列在**关联因子之后**、行尾) 存在歧义; 为保持 thead/tbody 列对齐, 竞价 `<td>` 置于行尾 (关联因子之后), 与分组表头 colSpan 顺序一致。e2e 只断言列头与行值, 不依赖中间顺序。
4. **既有 e2e 用例 3 处适配** (行为意图不变): (a) `hub loading` 用例 `getByRole('status')` → `.filter({ hasText: '股池加载中…' })` — DateNavigator 首帧亦渲染 `role="status"` (加载日期中…), 裸定位会因 strict mode 双元素失败; (b) `pool page renders zero execution affordances` 的 `EXECUTION_RE` 加 `(?!交易日)` 负前瞻 — DateNavigator 步进按钮 aria-label `上一个交易日`/`下一个交易日` 含「交易」误命中执行动作正则 (日期导航 ≠ 交易动作); (c) 同用例 `ALLOWED_RE` 追加 `上一个交易日|下一个交易日|最新`。
5. **SC2 无快照日可达路径**: 计划引用 `history?as_of=2026-08-02` (不在白名单); 因非交易日物理不可达 (PIT-5), 改用白名单日 2026-08-01 并在用例内覆盖 history 路由返回 `available:false` 载荷, 经 `‹` 步进触发。
6. **SC4c 盘前用例**: 「查看日 == 今日」需 as_of 为运行日; 用例内 `localTodayISO()` 按本地时区动态计算今日串 (与应用 `isToday` 同机同 TZ), hub 载荷 as_of 置为今日, `is_trading_hours:false` 由 installShell 既有 `/api/intraday/status` mock 提供。
7. **截图基线零更新**: 既有 `pool-*.png` 基线均为元素级截图 (策略卡片 region / 钻取明细 region / 单卡片), DateNavigator 位于其外且不影响元素渲染; 视觉用例全绿, 无需 --update-snapshots。

## watchlist_touched

`false` — `frontend/src/pages/Watchlist.tsx` (用户未提交改动) 未被 stage/commit; 3 个提交均未包含该文件, 工作树保持其原有修改 (git status 仅剩 `M Watchlist.tsx`)。

## Pre-existing / Parallel State (not owned by 23-02)

- `frontend/src/pages/Watchlist.tsx` (M): 用户未提交改动, 保留在工作树, 未触碰。
- 23-01 交付物 (backend 透传/剥离 + 前端查询层): 已合入, 作为本计划 precondition 门通过。
- 23-03+ (后续前端收尾面): 未开始, 由下一计划处理。
