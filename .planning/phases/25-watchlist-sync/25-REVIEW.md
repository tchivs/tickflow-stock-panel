# Phase 25 计划检查 round 1

> 检查对象：`.planning/phases/25-watchlist-sync/25-01-PLAN.md` + `25-02-PLAN.md`
> 证据基准：本 session 实读源码 file:line（只读审查，未运行构建/测试，未触碰 `Watchlist.tsx`）

---

## 25-01: EXECUTABLE

全部 10 项审查点核实通过（1 项执行风险 → Warning W1/W2）：

- **文件路径准确性**：`frontend/src/lib/storage.ts`、`frontend/src/pages/PoolHubPage.tsx`、`frontend/src/components/pool-hub/StockListTable.tsx` 均存在；计划不新建组件文件（`WatchlistFilter.tsx` 内联于 PoolHubPage，UI-SPEC §4.3 允许二选一）→ 无新增文件需并入 e2e grep 文件清单。
- **符号真实性**：`Screener.tsx:429-447`（watchlist query → Set → toggle mutation，逐字先例）、`useSharedMutations.ts:32-41`（`useWatchlistBatchAdd` 双 key 失效）、`api.ts:2025-2051`（watchlistList/Add/BatchAdd/Remove）、`storage.ts` `kv<T>` 模式、`ConceptFilter.tsx`、`ExtDataPullPanel.tsx:205-215`（role=switch 先例）、`main.tsx:22-27`（401 跳登录）全部实读确认存在。
- **guest 双门控**：25-01 Task 1 step 4 明确 `enabled: !!data && mode === 'vip'`；与 `PoolHubPage.tsx:53` `mode = data?.mode === 'guest' ? 'guest' : 'vip'` 一致；`main.py:778-788` 游客白名单恰 4 个 GET，`/api/watchlist` 不在 → guest 误发必 401 跳登录的根因成立，双门控正确。
- **匹配键**：`watchlistSet.has(row.symbol)`（全后缀精确全等），与 `pool_hub.py` 行投影 `row.symbol` 全后缀一致，无归一化。
- **WATCH-04 批量范围**：`handleBatchAdd = filteredRows.map(r => r.symbol)`（可见行），绝不按 `activeStrategy.total`。
- **验证命令**：`npm run build`（package.json `tsc -b && vite build`）+ 结构 grep 均精确可命中；`playwright.config.ts` desktop-chromium 项目存在。
- **TS 构建影响**：`StockListTable` 唯一调用方是 `PoolHubPage.tsx:197`（grep 确认无其他引用）→ 新增 4 个必需 props 不会破坏其他调用点；`StockListTableProps`（L17-49）扩展后 PoolHubPage 全部透传。
- **诚实性**：`storage.poolWatchlistOnly` 仅 UI 偏好布尔；guest 分支（`StockListTable.tsx:297-317`）零变更声明；`git status` 确认 `frontend/src/pages/Watchlist.tsx` 为用户未提交改动，计划声明绝不触碰。
- **需求覆盖**：WATCH-01/02/03/04 全部在两份计划 `requirements` frontmatter 且有覆盖任务；依赖图 25-01(wave1)→25-02(wave2) 无环；文件零重叠。

**Round 1 结论：** 25-01 可执行。修正 W1/W2 后执行质量更稳（不阻塞）。

---

## 25-02: NOT EXECUTABLE

1 项 BLOCKER（B1：Task 3 快照重生成范围/「guest 快照」分类错误，且 verify 门自身必失败）+ 1 项 Warning + 2 项 Info。

---

## Blockers

### B1 [25-02 Task 3] 视觉快照重生成范围错误：把 VIP 快照误标为「guest」，漏掉必变快照，verify 门自身必失败

- **计划**：25-02-PLAN.md Task 3
- **证据**：
  - 计划 Task 3 action 声明「guest 三张快照零 diff」并把 `pool-grid-populated` / `pool-empty-zero-hit` / `pool-card-unavailable` 称为 guest 快照，verify 门：`test "$(git status --porcelain frontend/e2e/pool-hub.spec.ts-snapshots | grep -c 'pool-grid-populated\|pool-empty-zero-hit\|pool-card-unavailable')" = "0"`。
  - 这 3 张**不是 guest 快照**，而是 VIP 载荷（`visualHubPayload`）截的。真实 guest 快照是 `pool-guest-masked-desktop-chromium-linux.png`（`pool-hub.spec.ts:839`，guest 钻取明细区）与 `pool-guest-grid-desktop-chromium-linux.png`（`:837`，guest 卡片网格）。
  - 8 张快照的捕获帧逐一核对：
    | 快照 | 捕获帧（spec 行号） | 25-01 后是否变化 |
    |---|---|---|
    | `pool-table-resonance` | L756 钻取 `<section>` 区（VIP） | **变**（星标 + header 开关/批量按钮） |
    | `pool-table-filter-active` | L762 钻取 `<section>` 区（VIP） | **变**（同上） |
    | `pool-empty-zero-hit` | L770 钻取 `<section>` 区（早盘之星，VIP，0 行） | **变**（section 内 header 仍渲染开关 + 批量按钮，25-01 Task 3 控件仅 `mode==='vip'` 条件，无行数条件） |
    | `pool-vip-plaintext` | L852 钻取 `<section>` 区（VIP，来自 guest-mode backstop 用例） | **变**（同上） |
    | `pool-grid-populated` | L754 `region 策略卡片`（VIP 卡片网格） | 不变（卡片区无星标/控件） |
    | `pool-card-unavailable` | L773 单个卡片按钮 | 不变 |
    | `pool-guest-masked` | L839 钻取 `<section>` 区（guest） | 不变（guest 无控件/星标） |
    | `pool-guest-grid` | L837 `region 策略卡片`（guest） | 不变 |
  - 结论：应重生成的**至少 4 张**（resonance、filter-active、empty-zero-hit、vip-plaintext），计划只列了前 2 张；`pool-empty-zero-hit` 会被 `--update-snapshots` 连带重生成 → 计划的 verify grep 门计数 ≥1 → `test "1" = "0"` **必失败**；`pool-vip-plaintext` 变化完全不在计划视野 → 静默漂移。若按计划 action step 2「连带更新则 revert 这三张」执行，则 `pool-empty-zero-hit` 基线停留在旧帧，下一次全量 `npx playwright test pool-hub.spec.ts` 该 backstop 必红（最大 2% diff 容差盖不住新增控件）。
  - 根因传播链：`25-RESEARCH.md` P3 → `25-UI-SPEC.md` §8.1（L396）→ 25-02-PLAN.md Task 3，三处同误标。
- **修复建议**：
  1. 重生成范围改为 **4 张**：`pool-table-resonance-desktop-chromium-linux.png`、`pool-table-filter-active-desktop-chromium-linux.png`、`pool-empty-zero-hit-desktop-chromium-linux.png`、`pool-vip-plaintext-desktop-chromium-linux.png`（后两张含钻取 section 新控件）；人工复核仅星标/开关/批量按钮增量。
  2. 零 diff 断言改为真实不变集：`pool-grid-populated|pool-card-unavailable|pool-guest-masked|pool-guest-grid`（VIP 卡片区 + 全部 guest）。
  3. 同步修正 `25-RESEARCH.md` P3 与 `25-UI-SPEC.md` §8.1 的「guest 快照」误标。

---

## Warnings

### W1 [25-01 全计划] `read_first`/`action` 行号引用与真实代码偏移（部分超文件末尾）

- **计划**：25-01-PLAN.md Task 1/2/3
- **证据**（实读行号 vs 计划引用）：
  - `StockListTable.tsx` 全文 384 行；计划引 `:400-413`（footer）超 EOF。真实 footer：`filterActive` L166、`筛选后 … / 共 …` L366-370。
  - `StockListTable.tsx` 两空态实际在 L205-229（计划引 `:178-205`）；VIP 代码单元格实际 L296-311、guest 分支 L297-317（计划引 `:214-227` / `:228-242`）；props 接口实际 L17-49。
  - `PoolHubPage.tsx` `mode` 实际 L53（计划引 `:34`）；`filteredRows` 实际 L65-71（计划引 `:43-51`）；`<StockListTable>` 调用点实际 L197-207（计划引 `:120-135`）。
- **修复建议**：执行前以 grep 重新核对锚点行号，或修改计划 `read_first` 使其指向正确范围；尤其删除超 EOF 的 `:400-413`，避免 executor 按错误行号定位。

### W2 [25-01 Task 1 step 7] `filteredRows` 改造未显式处理既有 early-return，存在「只看自选」被跳过风险

- **计划**：25-01-PLAN.md Task 1
- **证据**：`PoolHubPage.tsx:65-71` 现有实现有两个早退路径：
  ```tsx
  const filteredRows = useMemo(() => {
    if (!activeStrategy) return []
    const q = filterText.trim().toLowerCase()
    if (!q) return activeStrategy.rows          // ← 若在早退后追加过滤即被跳过
    return activeStrategy.rows.filter(r => r.concept_board.some(...))
  }, [activeStrategy, filterText])
  ```
  计划 action 写「在返回前追加 `if (watchlistOnly) base = base.filter(...)`」，未明确要求把早退重构为单一 `base` 变量。若 executor 在既有 `return` 之后追加过滤，`filterText` 为空（开关使用最常见场景）时「只看自选」过滤被完全绕过，且 `useMemo` 依赖数组若不追加 `watchlistOnly, watchlistSet` 会直接失效。
- **修复建议**：action 明确改为「先以 `base` 承接概念投影（`let base = q ? … : activeStrategy.rows`），再 `if (watchlistOnly) base = base.filter(r => watchlistSet.has(r.symbol))`，末尾 `return base`」；依赖数组追加 `watchlistOnly, watchlistSet`。behavior Test 2 已覆盖此路径，但建议把重构步骤写进 action。

---

## Infos

### I1 [25-02 Task 2 Test 1] 「第二次 GET /api/watchlist」断言应以请求计数器实现，避免 exact-count 脆弱

- **证据**：`playwright.config.ts` webServer 用 vite dev server（非 preview）；`main.tsx` 包裹 `React.StrictMode`。开发态 StrictMode 双挂载 + react-query 缓存时序下，初始 GET 次数不保证恰为 1。
- **建议**：`page.on('request')` 中 `watchlistGets += 1`；点击星标后断言 `watchlistGets` 较点击前增加（≥2），不写死精确次数。

### I2 [25-02 Task 1 step 1] `installShell` 默认 `**/api/watchlist**` mock 是方法无关的

- **证据**：计划默认 mock `json(route, { symbols: [] })` 会对 POST/DELETE 也返回 200；若某用例忘记后注册写覆盖，写请求会被静默吞掉（掩盖真实 401/500）。
- **建议**：默认 mock 仅放行 GET（`route.request().method() === 'GET' ? json(...) : unhandled(route)`），写端点由具体用例显式覆盖——与 25-02 Task 1 action step 1 注明的「后注册覆盖」一致，但默认不吞写。

### I3 [RESEARCH/UI-SPEC] `25-RESEARCH.md` `## Open Questions` 缺 `(RESOLVED)` 标记

- **证据**：`25-RESEARCH.md` 末尾 `## Open Questions` 无 `(RESOLVED)` 后缀；但 3 个问题均带「建议：」内联结论且已由计划采纳（Q1→钻取区 header、Q2→只看自选文案优先、Q3→隐藏批量按钮）。
- **建议**：补 `(RESOLVED)` 标记，避免后续轮次误判为未决问题。

---

## 汇总

| 计划 | 判定 | Blocker | Warning | Info |
|---|---|---|---|---|
| 25-01 | **EXECUTABLE** | 0 | 2（W1 行号漂移 / W2 filteredRows 重构） | 1（I3） |
| 25-02 | **NOT EXECUTABLE** | 1（B1 快照范围+verify 门必失败） | 0 | 2（I1/I2） |

**Round 1 结论：** 25-01 可执行（建议先修 W1/W2）；25-02 因 B1 需回炉——修正 Task 3 快照重生成范围为 4 张、把零 diff 断言改为真实不变集（`pool-grid-populated|pool-card-unavailable|pool-guest-masked|pool-guest-grid`），并同步 RESEARCH P3 / UI-SPEC §8.1 的「guest 快照」误标。
