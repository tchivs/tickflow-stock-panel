---
phase: 23-frontend
verified: 2026-08-05T12:00:00Z
status: human_needed
score: 8/8 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "DateNavigator 真实数据视觉确认"
    expected: "真实 data/ 下日期列表加载、‹ › 步进、下拉白名单、无快照空态文案观感正常；明细表含竞价列横向滚动不溢出"
    why_human: "Playwright mock 覆盖功能路径；真实数据下观感/滚动/截断属视觉判断，需浏览器人工确认"
  - test: "probe 状态徽标真实环境验证"
    expected: "真实 /api/data/auction-probe available / fail_closed 与盘前时段下，徽标文案与真实列隐藏逻辑与 mock 断言一致"
    why_human: "mock 断言徽标渲染；真实 probe 状态与窗口时段需人工/环境验证"
---

# Phase 23: 前端 (Frontend) Verification Report

**Phase Goal:** 用户可以用 DateNavigator 按交易日浏览股池（‹ › 步进 + 日期列表 + as_of 重取 + 非交易日禁用 + 无数据日诚实空态），并在股池钻取中查看竞价列——真实集合竞价 vs 派生虚拟成交分开标注（股/元单位），盘前/空态诚实展示 probe/窗口状态。
**Verified:** 2026-08-05T12:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 — DateNavigator ‹ › 步进 + 日期列表（数据源 `GET /api/pool/dates`），每次步进触发 as_of 重取刷新卡片计数与钻取明细 | ✓ VERIFIED | `DateNavigator.tsx`（受控组件，`dates` 白名单下标步进，‹=idx+1 / ›=idx-1，边界与 `idx===-1` 双禁用）；`PoolHubPage.tsx` `selectedDate` state + `datesQuery`(`QK.poolDates`/`api.poolDates`) + `poolQuery` 按 `selectedDate` 切 `QK.poolHistory(d)`/`QK.poolHub()` + `placeholderData` 平滑；e2e **SC1**（34 passed 套件内）：初始 › disabled/‹ enabled → 点 ‹ subtitle 变 08-01 + `history?as_of=2026-08-01` 请求断言 + 卡片计数 total 2→5 刷新 → 下拉 07-31 → history 请求 + total 1 → ‹ 到最旧 disabled → 「最新」回 `/api/pool/hub` + 按钮消失 |
| 2 | SC2 — 非交易日禁用且不静默跳日；无快照日期诚实空态（非误导性零池） | ✓ VERIFIED | `DateNavigator.tsx` 非交易日物理不可达（白名单日期集 + 下标步进，无「跳到最近日」逻辑，PIT-5）；`PoolHubPage.tsx` `data.available === false` → 独立 EmptyState `CalendarX` + 「该日期无股池快照」**先于**零池分支短路，零池分支补 `available !== false` 门（PIT-2 真互斥）；e2e **SC2/SC2b**：零池载荷→「当日无股池结果」且「该日期无股池快照」不出现；步进到 available:false → 反证成立 + 无卡片/明细表；下拉 options 只含白名单 3 日；`dates:[]` → 双按钮+下拉禁用 + 「暂无历史日期」 |
| 3 | SC3 — 竞价列（竞价量/金额）真实集合竞价 vs 派生/虚拟成交明确分开展示并标注单位（股/元） | ✓ VERIFIED | `StockListTable.tsx` 两行分组 thead：基础列 rowSpan=2 + `真实集合竞价`(colSpan=2, accent) + `派生 · 虚拟成交`(colSpan=2, secondary)；成员列头带单位 `竞价量（股）`/`竞价金额（元）`/`竞价量比（×）`/`虚拟未匹配金额（元·估算）` + `title` tooltip；单元格 `BigNumCell`(fmtBigNum 万/亿)/`RatioCell`(toFixed(2)+'×')，null/NaN → `—`，数值列不套涨跌色；`open_gap` 留基础列不重复渲染；e2e **SC3/SC3b/SC3c**：组带 + 4 成员列 + tooltip + 行值 `2.35×`/`123万`/`2.35亿`/`1235万` + null 行 4 处 `—`；real:[] → 真实组整组不渲染 + warning「竞价数据未接入，仅展示派生列」+ 派生组保留；guest → 无竞价列/无分组/无徽标，既有 5 列不变 |
| 4 | SC4 — probe 非 `available` 或盘前时，UI 诚实展示 probe/窗口状态（fail-closed 空态或派生标注），绝不暗示存在真实竞价数据 | ✓ VERIFIED | `AuctionColumnStatusBadge`（StockListTable 导出）状态机：`auction_columns.real` 驱动主徽标（info `竞价数据可用 · 窗口 09:15-09:25` / warning 两分支），`useAuctionProbe()`(30s stale) + `useQuoteStatus().is_trading_hours` 只驱动 warning 与盘前 secondary 行（H3 双轨）；e2e **SC4a-d**：probe available+real 非空→info；probe fail_closed+real 空→warning；查看今日+`is_trading_hours:false`→盘前/休市 secondary 与 info 并列；历史快照 08-01 real 非空 + 今日 probe fail_closed → 真实列**仍渲染** + 徽标按 `auction_columns.real` 显示 info（历史事实不因今日状态重写） |
| 5 | OQ-2/PIT-3 — 后端 `_project_hub` 投影恒 12 键透传 + 顶层 `auction_columns:{real,derived}` 声明（hub/history 双路径共享单点）；raw row 缺键 → None（诚实缺列，非 0 填充）；列存在性服务端权威、前端零推导 | ✓ VERIFIED | `pool_hub.py:83-186` `_project_hub` 逐行透传 4 竞价键（`_safe_num(row.get(col))`，缺键→None）并据 raw rows 键存在性计算 `auction_columns`；`build_pool_hub`/`build_pool_hub_snapshot` 双路径共享（PIT-6 零改动）；`test_project_hub_passes_through_auction_columns`（round-trip + 声明精确）+ `test_project_hub_honest_absent_auction_columns`（real==[] + derived 不含竞价派生键）+ `test_project_hub_auction_columns_match_projection_keys`（极端夹具 real==["auction_volume"]）+ `test_build_pool_hub_single_as_of_counts_and_columns` 追加 `auction_columns == {"real": [], "derived": ["open_gap"]}` 全绿 |
| 6 | H7 — 游客零泄露：`mask_guest_hub` 顶层 `pop("auction_columns")` + `_GUEST_VISIBLE` 白名单行级剥离 `auction_*`/`open_gap`；守卫测试锁死 | ✓ VERIFIED | `guest_masking.py:23-54` `masked.pop("auction_columns", None)`；`_GUEST_VISIBLE = frozenset({"change_pct","concept_board","hit_factors","cross_resonance"})` 重建 masked_row 天然丢弃；`test_guest_hub_strips_top_level_auction_columns` + `test_guest_endpoint_no_auction_columns`（VIP 对照 `auction_columns` 存在 → 证明剥离发生于掩码层，非投影缺失）全绿；前端 `PoolHubPage` 徽标仅 `data?.auction_columns` 存在时挂载 |
| 7 | PIT-1/PIT-5 — 历史必走 `GET /api/pool/history?as_of=`（绝不 `/hub?as_of=` 反漂移）；非交易日物理不可达、绝不静默跳日 | ✓ VERIFIED | `PoolHubPage.tsx` `queryKey: selectedDate ? QK.poolHistory(selectedDate) : QK.poolHub()` + `queryFn` 同步切换；`api.ts:2114-2115` `poolHistory` 绑定 `/api/pool/history?as_of=`；`queryKeys.ts` `QK.poolHistory(asOf)` 与 `QK.poolHub` 物理分离（且不在 `SSE_INVALIDATE_PREFIXES`）；`DateNavigator.tsx` 下标步进 + `idx===-1` 双禁用；e2e **SC1** 断言 `historyDates` 含 08-01/07-31 且**不含** 08-04；e2e SC2/SC2b 锁非交易日不可达 |
| 8 | PIT-8 — `updated_at` 双型容忍（hub=epoch ms / history=ISO / 空态 null）；零新增运行时依赖；`Watchlist.tsx` 未触碰 | ✓ VERIFIED | `api.ts:726` `updated_at: number \| string \| null`；本期不展示 `updated_at`（grep 确认 PoolHubPage/StockListTable 无引用）；npm build 无新增依赖（package.json 零 diff）；`git log f8f21cb^..ad8a04b -- frontend/src/pages/Watchlist.tsx` 空 + `git diff cba61f5..ad8a04b` 0 行 → Phase 23 全部 6 个功能提交未触碰 Watchlist；工作树仅存用户未提交改动（+83/-50 portal 下拉修复） |

**Score:** 8/8 truths verified (0 present-but-behavior-unverified, 0 overrides)

### Honesty Rules (H1-H8 + PIT-1/PIT-5) — Code Evidence

| # | 规则 | 代码证据 | 状态 |
|---|------|---------|------|
| H1 | 列存在性由服务端声明，前端零猜测 | `StockListTable.tsx` `realCols = auctionColumns?.real ?? []` / `hasReal = realCols.some(c => c==='auction_volume' \|\| c==='auction_amount')` — 只消费服务端 `auction_columns` prop；行级 null 仅渲染 `—`，绝不按行值推导列存在；后端 `_project_hub` 由 raw row 键存在性计算；`test_project_hub_auction_columns_match_projection_keys` 锁死 | ✓ |
| H2 | `available:false` → 独立空态「该日期无股池快照」先于零池短路 | `PoolHubPage.tsx` 渲染序：`data.available === false` → EmptyState(CalendarX,「该日期无股池快照」) 在零池分支**之前**；零池分支 `data.available !== false` 门 → 两空态互斥；e2e SC2 双 heading 断言 | ✓ |
| H3 | 冻结列存在性 vs 实时 probe 双轨；历史快照不因今日状态重写 | `AuctionColumnStatusBadge`：主徽标由 `auction_columns.real` 驱动（hasReal→info），`useAuctionProbe`/`useQuoteStatus` 仅驱动 warning 分支与盘前 secondary 行；e2e SC4d：历史 real 非空 + 今日 probe fail_closed → 真实列仍渲染 + info 徽标 | ✓ |
| H4 | 真实/派生永不混排、永不相加 | `StockListTable.tsx` 两个独立 colSpan=2 组带（`真实集合竞价` accent / `派生 · 虚拟成交` secondary）+ 语义列头（`（元·估算）`）；无合计/求和逻辑；`open_gap` 留基础列「开盘涨幅」不搬入派生组不重复渲染 | ✓ |
| H5 | 单位在列头（股/元/×） | 列头 `竞价量（股）`/`竞价金额（元）`/`竞价量比（×）`/`虚拟未匹配金额（元·估算）`；e2e SC3 断言 | ✓ |
| H6 | probe 非 available/盘前 → fail-closed（真实组隐藏 + warning）或派生标注 | `StockListTable.tsx` `hasReal` false → 真实组整组不渲染；徽标 warning「竞价数据未接入，仅展示派生列」（probe 非 available）/「该快照计算时无真实竞价数据，仅展示派生列」（probe available 但快照无）；盘前 secondary 行；e2e SC3b/SC4b/SC4c | ✓ |
| H7 | 游客 payload 无 `auction_columns`/`auction_*`/`open_gap` | `guest_masking.py:53` `masked.pop("auction_columns", None)` + `_GUEST_VISIBLE` 白名单行级剥离；`test_guest_endpoint_no_auction_columns` VIP 对照证明剥离在掩码层；e2e SC3c guest 无竞价列/徽标 | ✓ |
| H8 | `updated_at` 双型容忍 | `api.ts:726` `updated_at: number \| string \| null`；后端 hub=epoch ms / history=ISO 串 / 空态 null；本期不展示 | ✓ |
| PIT-1 | 历史必走 `/api/pool/history`，绝不 `/hub?as_of=` | `PoolHubPage.tsx` queryKey/queryFn 按 `selectedDate` 切 `QK.poolHistory(d)`/`api.poolHistory(d)`，与 `QK.poolHub`/`api.poolHub` 物理分离；e2e SC1 断言 history 请求且最新日绝不打 history | ✓ |
| PIT-5 | 非交易日物理不可达、绝不静默跳日 | `DateNavigator.tsx` `idx = dates.indexOf(currentAsOf)`；‹ › 严格下标步进；边界/`idx===-1` 双禁用（不猜测）；下拉 options 只列白名单；无「跳到最近日」分支；e2e SC1/SC2/SC2b | ✓ |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | --------- | ------ | ------- |
| `frontend/src/components/pool-hub/DateNavigator.tsx` (new) | 受控只读 ‹ › 步进 + 日期下拉 + 「最新」复位 + 加载/错误/空态 | ✓ VERIFIED | 全形 109 行；白名单下标步进；`idx===-1` 双禁用；`暂无历史日期`；role=status/alert |
| `frontend/src/pages/PoolHubPage.tsx` (modified) | selectedDate state + datesQuery + poolQuery key 切换 + available:false 空态分流 + auctionColumns 接线 | ✓ VERIFIED | `placeholderData` 平滑；`asOf = data?.as_of ?? selectedDate ?? null` 诚实副标题；渲染序短路 |
| `frontend/src/components/pool-hub/StockListTable.tsx` (modified) | 两行分组 thead + 竞价列单元格 + AuctionColumnStatusBadge | ✓ VERIFIED | 全形 340 行；real/derived 分组渲染 + 单位 + tooltip + 状态徽标四态 |
| `frontend/src/lib/api.ts` (modified) | PoolDatesResponse/AuctionColumnsDecl/PoolHubRow 扩展 + poolDates/poolHistory | ✓ VERIFIED | 类型齐全；`poolDates()`/`poolHistory(asOf)` 绑定正确端点 |
| `frontend/src/lib/queryKeys.ts` (modified) | QK.poolDates/QK.poolHistory 与 QK.poolHub 物理分离 | ✓ VERIFIED | `poolDates: ['pool-dates'] as const`（非工厂，W-23-02-1）；`poolHistory(asOf)` 工厂；不在 SSE_INVALIDATE_PREFIXES |
| `frontend/e2e/pool-hub.spec.ts` (modified) | dates/history/probe mock + SC1-SC4 用例 | ✓ VERIFIED | 34 用例全绿（desktop），含 SC1-SC4 + SC2b/SC3b/SC3c/SC4a-d |
| `backend/app/services/pool_hub.py` (modified) | `_project_hub` 12 键透传 + auction_columns 声明；双路径零改动 | ✓ VERIFIED | L83-186；`_safe_num` 诚实缺列；build_pool_hub 反漂移/空缓存早退 dict 零改动 |
| `backend/app/services/guest_masking.py` (modified) | 顶层 `pop("auction_columns")`；白名单不改 | ✓ VERIFIED | L53 `masked.pop`；`_GUEST_VISIBLE` 原样 |
| `backend/tests/test_pool_hub.py` (modified) | expected_keys 8→12 + 透传/诚实缺列/声明一致性 | ✓ VERIFIED | 30 测试全绿（27 既有 + 3 新增） |
| `backend/tests/test_guest_masking.py` (modified) | 顶层剥离 + 端点 VIP↔guest 对照守卫 | ✓ VERIFIED | 17 测试全绿（15 既有 + 2 新增） |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| DateNavigator | PoolHubPage | `onChange={setSelectedDate}` — 步进只改 state | WIRED | e2e SC1：‹ ›/下拉/「最新」均更新 subtitle + 触发重取 |
| PoolHubPage `selectedDate` | poolQuery | `queryKey: selectedDate ? QK.poolHistory(d) : QK.poolHub()` — key 驱动重取 | WIRED | e2e SC1：步进 → `history?as_of=` 请求 + 卡片计数刷新 |
| poolQuery | `/api/pool/history` | `api.poolHistory(asOf)` → GET `/api/pool/history?as_of=`（PIT-1） | WIRED | e2e SC1：historyDates 含步进日、不含最新日 |
| StockListTable | `auction_columns` 声明 | `auctionColumns={data?.auction_columns ?? null}` — 服务端权威（H1） | WIRED | e2e SC3/SC3b/SC3c：real/derived 分组随声明显隐 |
| AuctionColumnStatusBadge | probe/时段 | `useAuctionProbe()` + `useQuoteStatus()` 仅驱动 warning/盘前分支（H3 双轨） | WIRED | e2e SC4a-d：四态徽标 + 历史不被今日重写 |
| `_project_hub` | build_pool_hub / build_pool_hub_snapshot | 共享单点（PIT-6）；history 路径经 build_pool_hub_snapshot → _project_hub | WIRED | `test_project_hub_*` 3 新增 + 双路径声明断言 |
| mask_guest_hub | `/api/pool/hub` + `/api/pool/history` | 两路由非 VIP → `mask_guest_hub(hub)`（pool.py:51,101） | WIRED | `test_guest_endpoint_no_auction_columns` 端点对照 |
| api.poolDates | `/api/pool/dates` | `poolDates: () => request('/api/pool/dates')` | WIRED | e2e SC1/SC2b：dates 白名单驱动步进/下拉 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| DateNavigator `dates` | `datesQuery.data?.dates` | `api.poolDates()` → `list_snapshot_dates` 分区 glob（真实 screener_results/date=* 扫描） | ✓ 真实快照日期集；e2e mock 验证白名单驱动 | ✓ FLOWING |
| 竞价列（数据列） | `row.auction_volume/amount/ratio/unmatched` | 快照 raw rows（screener to_dicts + attach_auction_columns 双闸门注入）→ `_project_hub` 12 键透传 | ✓ 真实冻结列数据；缺失→None→`—`；e2e SC3 断言格式化值 | ✓ FLOWING |
| `auction_columns` 声明 | `data.auction_columns` | `_project_hub` 由 raw row 键存在性计算（hub/history 双路径） | ✓ 服务端权威声明；guest 剥离；e2e SC3b/SC3c | ✓ FLOWING |
| 卡片计数 + 钻取 | `data.strategies[i].total/rows` | `build_pool_hub`/`build_pool_hub_snapshot` → `_project_hub`（total 权威） | ✓ 真实单 as_of 载荷；e2e SC1 断言 2→5→1 计数刷新 | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 后端跨层回归（OQ-2 透传 + H7 剥离 + POOL-03 exact-dict） | `cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py tests/test_guest_masking.py -x -q` | `47 passed in 2.18s` | ✓ PASS |
| 前端类型 + 构建 | `cd frontend && npm run build` | `✓ built in 8.81s`（tsc 0 错误；仅既有 chunk>500kB 提示非错误） | ✓ PASS |
| e2e（mock，SC1-SC4 + 既有回归） | `cd frontend && npx playwright test e2e/pool-hub.spec.ts` | `34 passed, 68 skipped, 0 failed (52.5s)`；68 skipped = 非 desktop-chromium 项目（mobile-chromium-320 + phase4-fastapi-host），desktop 全绿 | ✓ PASS |
| 单命名行为测试 — PIT-1 路径守卫 | e2e SC1（`historyDates` 含 08-01/07-31 不含 08-04） | passed | ✓ PASS |
| 单命名行为测试 — PIT-2 空态短路 | e2e SC2（available:false → 「该日期无股池快照」且「当日无股池结果」toHaveCount(0)） | passed | ✓ PASS |
| 单命名行为测试 — H3 历史不被今日重写 | e2e SC4d（历史 real 非空 + 今日 probe fail_closed → 真实列仍渲染 + info 徽标） | passed | ✓ PASS |
| 单命名行为测试 — guest 零泄露 | `test_guest_hub_strips_top_level_auction_columns` + `test_guest_endpoint_no_auction_columns` | 2 passed | ✓ PASS |

### Probe Execution

N/A — Phase 23 无 probe 脚本（`find scripts -path '*/tests/probe-*.sh'` 无输出；23-01/23-02-PLAN 与 SUMMARY 无 probe 声明）。自动化验证由 pytest + npm build + Playwright e2e 承担。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| FRONT-01 | 23-02 T1/T3 | DateNavigator ‹ › 步进 + 日期列表 + as_of 重取刷新卡片计数与钻取；非交易日禁用不静默跳日；无快照日诚实空态 | ✓ SATISFIED | DateNavigator.tsx + PoolHubPage.tsx + api.poolDates/poolHistory + e2e SC1/SC2/SC2b（34 套件全绿） |
| FRONT-02 | 23-01 T1/T2 + 23-02 T2/T3 | 竞价列（竞价量/金额）真实 vs 派生分开展示 + 单位（股/元）；probe/盘前诚实状态 fail-closed | ✓ SATISFIED | _project_hub 12 键透传 + auction_columns 声明 + guest 剥离 + StockListTable 分组 + AuctionColumnStatusBadge + e2e SC3/SC3b/SC3c/SC4a-d + 后端 47 测试全绿 |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | 无 TBD/FIXME/XXX 债务标记（7 个 phase 源文件 grep 零命中） | — | — |
| — | — | 无 TODO/HACK/PLACEHOLDER 占位（`placeholderData: (prev) => prev` 是 TanStack Query 官方 API 名，即 UI-SPEC §4.1 的 stale-while-revalidate 机制，非 stub） | — | — |
| — | — | 无 placeholder/coming soon/not yet implemented | — | — |
| — | — | 无空实现：`if (!auctionColumns) return null`（guest/无声明不渲染徽标）/`if (!strategy) return null`/`if (!activeStrategy) return []` 均为正确守卫逻辑 | — | — |
| — | — | 无硬编码空数据（竞价列来自真实快照透传，缺失→None→`—`） | — | — |

**Informational（非阻断，书面对账滞后，同 Phase 22 先例）：**
1. `.planning/REQUIREMENTS.md` FRONT-01/FRONT-02 行 66-67 仍标 `Open`、ROADMAP Phase 23 未勾选 —— 代码已交付且全部门禁绿，属阶段完成后的书面对账步骤。
2. `23-UI-SPEC.md` Checker Sign-Off 仍标 `pending` —— UI 契约审阅状态标记，非代码缺口。

### Human Verification Required

VALIDATION.md 明确将以下两项归属「Phase 23 verifier」（前端视觉/真实环境本质，mock e2e 无法完全覆盖）：

### 1. DateNavigator 真实数据视觉确认

**Test:** 在真实 data/ 后端数据下打开股池页，确认日期列表加载、‹ › 步进、下拉白名单、无快照空态文案观感；含竞价列明细表横向滚动与长文本截断。
**Expected:** 日期列表与步进逻辑与 mock 断言一致；空态/徽标文案清晰不截断；明细表含竞价列时 `overflow-x-auto` 正常。
**Why human:** Playwright mock 覆盖功能路径；真实数据下观感/滚动/截断属视觉判断，需浏览器人工确认。

### 2. probe 状态徽标真实环境验证

**Test:** 在真实环境中分别制造 probe `available` / `fail_closed` 与盘前时段，确认徽标文案与真实列隐藏逻辑。
**Expected:** 徽标按 `auction_columns.real` + 实时 probe/时段正确显示 info/warning/盘前状态，与 mock 断言一致。
**Why human:** mock 断言徽标渲染；真实 probe 状态与窗口时段需人工/环境验证。

### Gaps Summary

无阻断性缺口。8/8 must-have 真相在代码与测试中全部证实：

- **门禁全绿（独立复跑）**：后端 `test_pool_hub.py` + `test_guest_masking.py` = **47 passed**；`npm run build` green（tsc 0 错误）；Playwright `pool-hub.spec.ts` = **34 passed / 0 failed**（68 skipped 均为非 desktop 项目）。
- **SC1-SC4 行为证据**：e2e 用例实际驱动渲染后的 DOM 断言步进重取/计数刷新/空态短路/分组列/徽标状态，非仅符号存在。
- **诚实规则 H1-H8 + PIT-1/PIT-5**：逐一核对代码证据（见 Honesty Rules 表）——服务端声明权威（H1）、available:false 先于零池短路（H2）、冻结 vs 实时双轨（H3）、真实/派生永不混加（H4）、单位在列头（H5）、fail-closed（H6）、游客零泄露（H7）、updated_at 双型（H8）、历史必走 history（PIT-1）、非交易日物理不可达（PIT-5）。
- **后端契约回归**：`/api/pool/hub` single-as_of 契约零改动（exact-dict 测试 `test_get_pool_hub_missing_cache_empty`/`test_build_pool_hub_empty_cache`/`test_build_pool_hub_snapshot_missing_available_false`/`test_get_pool_hub_mismatched_as_of_returns_cache_date` 原样通过）；POOL-03 E1-E6 AST 守卫零修改。
- **git 清洁**：`git status` 仅 `M frontend/src/pages/Watchlist.tsx`；Phase 23 全部 6 个功能提交（`f8f21cb`→`0fe86d2`）均未触碰 Watchlist（`git diff cba61f5..ad8a04b` 0 行）；当前未提交 diff（+83/-50 portal 下拉修复）为用户既有改动，未受 Phase 23 影响。
- **零新增依赖**：无 pip/npm 安装（package.json/pyproject.toml 零 diff）。

唯一的 status 限制是 2 项前端视觉/真实环境人工确认（VALIDATION.md 显式归属本 phase verifier），故整体判定 **human_needed**（非 gaps_found，无失败真相）。

---

_Verified: 2026-08-05T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
