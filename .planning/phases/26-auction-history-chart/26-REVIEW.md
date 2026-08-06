# Phase 26 计划检查 round 1

> 检查方式:只读静态审查(不改代码/计划/文档;不跑测试/构建)。全部结论对照真实代码 file:line 核验。参照 Phase 23/24/25 风格,B/W/I 分级。
>
> 维度过一遍:需求覆盖(CHART-01/02/03 均有任务)→ 任务完整性(files/action/verify/done 齐)→ 依赖正确性(26-02 depends_on 26-01,wave 2 一致,无环)→ 零文件重叠(26-01 纯后端 8 文件 / 26-02 纯前端 7 文件)→ scope(2+2 任务,均 2-3 目标内)→ must_haves 派生(truths 用户可观测)。Dimension 7/7b(无 CONTEXT.md)、Dimension 10(无 CLAUDE.md)SKIPPED。

## 26-01: EXECUTABLE

后端计划(CHART-01 只读聚合端点 + CHART-03 写路径扩列)。核心设计与既有代码逐一对得上:新端点走新模块 `auction_history.py`(避开 kline.py 已有 POST 路由,`kline.py:85,342,377,541...` 无法做模块级 GET-only 守卫);`available:false` 200 空态镜像 `pool.py:88-113`;400 校验镜像 `pool.py:22,100-107`;POOL-03 AST 守卫镜像 `test_pool_hub.py:857-918`;`CANONICAL_AUCTION_COLS=4` 保持不变(`auction_sync.py:33-36` + `test_auction_sync.py:79` 断言不破坏);merge-upsert `how="diagonal_relaxed"` 有先例(`custom/provider.py` get_auction/get_financials);guest 白名单扩宽不破坏既有守卫(`test_guest_masking.py:507-534` 不锁死精确路径集)。零新 pip 依赖、不触碰 `Watchlist.tsx`(git status 已核验 ` M frontend/src/pages/Watchlist.tsx`)。

带 2 个 WARNING(W1 会让 Task 2 verify 门红、W2 行号偏差),建议执行前修正 W1。

## 26-02: NOT EXECUTABLE

前端计划(CHART-02)。Task 1 的组件/查询链路设计正确且全部落到真实文件;但 **Task 1 `<precondition>` 门不可满足(B2)** 且 **Task 2 e2e 从 `/pool-hub` 打不开 StockPreviewDialog(B1)**,两项都会在执行时阻塞,CHART-02 验收「e2e 四用例全绿」不可达。必须先修两个 BLOCKER。

## Blockers

### B / 26-02 Task 2 / e2e 从 `/pool-hub` 无法打开 StockPreviewDialog —— 四用例第一步即失败

**证据:**
- `frontend/src/pages/PoolHubPage.tsx` 全页不挂载 `StockPreviewDialog`。对 `frontend/src/pages/` 全量 grep:`StockPreviewDialog` 只出现在 ConceptAnalysis.tsx:433 / Dashboard.tsx:203,795 / IndustryAnalysis.tsx:486 / LimitUpLadder.tsx:1705 / Monitor.tsx:493,683 / Screener.tsx:839 / StockAnalysis.tsx:179 / Watchlist.tsx:1339 —— **PoolHubPage 不在其中**。
- `PoolHubPage.tsx:286-302` 只把 `onToggleWatchlist` 传给 `StockListTable`;`components/pool-hub/StockListTable.tsx` 行级 onClick 仅有 展开/收起(L61-73)、重试(L210-237)、清筛选(L234-238)、自选星标(L335-339),无 onPreview、无 navigate、无打开弹窗。
- 路由 `frontend/src/router.tsx:83` `/pool-hub → PoolHubPage`;`PoolHubPage.tsx` 依赖 `api.poolHub()`/`api.poolHistory()`(L38-46),与 Screener 的 `/api/screener/cached` 不是同一数据面。
- 26-02 Task 2 步骤 4: `page.goto('/pool-hub')` → 点击含 '300750' 明细行 → `await expect(page.getByRole('dialog')).toBeVisible()`。该前提不成立,四个用例(有数据/available:false/probe 非 available/guest)全在弹窗步骤失败。
- 「复用既有钻取点击方式,见 pool-hub.spec 既有用例」无出处:`frontend/e2e/pool-hub.spec.ts` 全部用例只点策略卡片/刷新/日期导航,没有任何打开个股弹窗的用例。RESEARCH D3 自己列的全站挂载页也不含 pool-hub。

**修复建议:** e2e 改在真正挂载 `StockPreviewDialog` 的页面打开弹窗。最小改动建议 `/screener`:`installShell` 后 mock `**/api/screener/cached**`(返回含 `300750.SZ` 行的策略结果,`api.screenerCached` 见 Screener.tsx:115-118)+ `**/api/screener/strategies**`(installShell 已默认 mock 空 presets,需用例覆盖),点 `ScreenerTable` 行(ScreenerTable.tsx:173 `onClick={() => onPreview(r.symbol, r.name ?? '')}`)→ Screener.tsx:800 → 弹窗可见。备选:`/stock-analysis`(StockAnalysis.tsx:112,179)或 `/dashboard` 热榜 onStockClick(Dashboard.tsx:762-770,795)。随后再点「竞价历史」toggle 断言。

### B / 26-01 验证节 + 26-02 Task 1 precondition / `grep -c "kline/auction/history" app/main.py` == 2 / >= 2 不可能成立(实际为 1)

**证据:**
- 该字面串在 main.py 只会出现 **1 次**:`_GUEST_READ_GET_PATHS`(`backend/app/main.py:779-785`)新增 `"/api/kline/auction/history"`。
- include_router 行是 `app.include_router(auction_history.router)`(26-01 Task 1 步骤 7,紧随 main.py:847 `include_router(kline.router)`),不含字面路径串;import 块(main.py:20-43)加的是模块名 `auction_history`,也不含。
- 受影响的三处:**26-01 验证节** `grep -c "kline/auction/history" backend/app/main.py == 2 (guest 白名单 + include_router)`;**26-01 Task 1 `<done>`**「main.py 命中 2 处」;**26-02 Task 1 `<precondition>`** `grep -c "kline/auction/history" app/main.py >= 2 (guest 白名单 + include_router)`。三者都建立在错误的计数上。
- 影响:26-02 Task 1 前置门 `>= 2` 永远为假 → 前端计划启动即被 gate 卡住;26-01 结构门文案与实际不符(其 `<verify>` 里裸 `grep -c` 退出码为 0,故 26-01 不阻塞,但验证节声称的 `== 2` 是错的)。

**修复建议:** 把两个注册点分开 grep,不要数同一个字面串两次:
- 白名单: `grep -c 'kline/auction/history' backend/app/main.py` **>= 1**(恰好 1 处)。
- include_router: `grep -n 'auction_history.router' backend/app/main.py` 有命中。
- 26-01 验证节文案改为「白名单 1 处 + include_router 1 处」;26-02 Task 1 precondition 同步改为上面的组合。或者(次选)在 include_router 行旁加一行含 `/api/kline/auction/history` 的注释,再保持 `== 2`,但前者更稳。

## Warnings

### W / 26-01 Task 2 步骤 11 / `test_attach_derives_unmatched_amount_from_partition_inputs` 断言 `auction_volume_ratio 照常派生`,但未 seed 历史缓存 → Task 2 verify 门会红

**证据:**
- `backend/app/services/auction_columns.py:53-76 _attach_auction_volume_ratio`:`repo.get_enriched_history(trade_date, 6)` 为 None/空、或 `date < trade_date` 的 prior 为空时,直接 return,`auction_volume_ratio` **列缺席**(诚实缺列)。
- 既有 `backend/tests/test_auction_strategy_family.py:346-357 test_auction_volume_ratio_absent_without_history` 已锁死「无历史缓存 → ratio 缺席」;同文件 L308-324 的 `test_auction_volume_ratio_prior_5d` 必须先 `_seed_history_cache`(L314-317)才派生。
- 26-01 Task 2 步骤 11 的新测试只写分区(含 2 输入列)就直接 `attach_auction_columns(...)` 并断言「auction_volume/auction_amount/auction_volume_ratio 照常」,没有 seed 历史 → ratio 实际缺席 → 断言失败 → Task 2 verify `pytest tests/test_auction_sync.py tests/test_auction_columns.py ... -x -q` 红。

**修复建议:** 在测试内 seed 历史缓存(镜像 `test_auction_strategy_family.py:314-317` 的 `_seed_history_cache(repo, date(2026,8,4), {...})`),或删去 `auction_volume_ratio` 断言、只保留核心断言 `auction_unmatched_amount == 5000 * 8.4 == 42000.0`(读路径派生激活的真实验收点)。

### W / 26-01 + 26-02 / 计划 read_first/action 的行号引用有多处偏移(符号全部真实,不影响执行)

**证据:**
- `frontend/src/lib/queryKeys.ts` 的 `SSE_INVALIDATE_PREFIXES` 实际在 **L209-223**(26-02 写 L172-183)。
- `backend/tests/test_auction_sync.py` 的 `df.columns == CANONICAL_AUCTION_COLS` 断言实际在 **L79**(26-01 写 L67-71;`test_sync_writes_partition` 定义在 L56)。
- `backend/app/services/auction_probe.py` 的 `resolve_auction_probe` 定义在 **L139**(26-01 read_first 写 L80-83 调用点;`to_dict` 在 L51、`AuctionProbeStatus` 在 L33、`_ERROR_DETAIL_MAX` 在 L30 均核验存在)。
- `backend/app/main.py` include_router 区实际在 L845-869(kline.router 在 L847,26-01 写 L849,偏移 2 行内)。

**修复建议:** 按上列实际行号更新引用,避免执行时 grep/read 落空浪费时间。

## Infos

- I1: 26-02 Task 1 在 StockPreviewDialog 引入 `Gavel` 图标,当前 `frontend/src/` 全仓库零引用(grep 无命中);lucide-react ^0.439.0 在册含该图标,属低风险新引入,非新增依赖。
- I2: 新端点 `repo = request.app.state.repo` 在 guest 分支**之前**读取(26-01 Task 1 步骤 3),测试 app 必须设 `app.state.repo`(镜像 `backend/tests/test_guest_masking.py:194 _make_guest_client`),否则包括 guest 在内的所有用例都会 AttributeError。建议在 test_auction_history.py 的客户端构造里显式写 `app.state.repo = repo`。
- I3: 多日末行聚合测试用 `date.today() - timedelta(days=days)` 回看窗口、fixture 日期固定 2026-08-01..04;若在 fixture 日期之后 >120 天跑测试,分区会被 `start` 过滤成空。需保持 fixture 相对执行日期的窗口(或把 days 传到端点用大值)。属长期漂移风险,非当前阻塞。
- I4: 两计划 estimate 均 `confidence: low`(本相位无历史 actuals 可校准);本环境 `gsd-tools` 无 `estimate-check` 动词,未能跑 `--calibrated`。任务数(2/2)与文件数(8/7)均在 smart-zone 阈值内,scope 健康,无切分建议。
- I5: guest 白名单扩宽是安全的 —— `test_guest_cannot_read_authed_surfaces`(test_guest_masking.py:507-518)与 `test_guest_read_paths_are_get_only`(:521-534)均枚举固定路径、不断言 frozenset 精确相等;新增 `/api/kline/auction/history` 不会破坏它们。D5 掩码语义(guest → 200 available:false mode:'guest')与 `pool.py:108-112` / `guest_masking.py:31-37` 既有纪律一致。
- I6: `pl.concat(..., how="diagonal_relaxed")` 在 polars 可用且仓库已有先例(`custom/provider.py` get_auction/get_financials 均用 `how="diagonal_relaxed"`);旧 4 列分区 + 新 6 列写入并集、旧行可选列补 null 的语义与 RESEARCH R1/R7 一致,`.tmp` 原子 rename 路径保留。

---

### 结论

| 计划 | 判定 | 阻塞项 |
|------|------|--------|
| 26-01 | **EXECUTABLE** | 无 BLOCKER;修 W1 后 Task 2 verify 门可绿 |
| 26-02 | **NOT EXECUTABLE** | B1(e2e 打不开弹窗)+ B2(Task 1 precondition `>=2` 不可满足) |

**Round 1 返回修订:** 26-01 修 W1(测试 seed 历史缓存)+ 行号;26-02 修 B1(改在 Screener 等挂载弹窗的页面开弹窗)与 B2(grep 门拆分)。两计划其余部分(需求覆盖/依赖/零重叠/诚实空态/POOL-03/掩码)核验通过。
