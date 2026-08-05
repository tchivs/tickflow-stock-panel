# Phase 23 Plan Review — 23-01 / 23-02

> 生成: 2026-08-05 · gsd-plan-checker（执行前只读审查，不修改源文件/计划）
> 范围: `.planning/phases/23-frontend/23-01-PLAN.md` + `23-02-PLAN.md`

## 结论摘要

| Plan | 判定 | Blockers | Warnings |
|------|------|----------|----------|
| 23-01（后端透传 + 查询层） | **EXECUTABLE** | 0 | 3 |
| 23-02（DateNavigator + 竞价列 UI） | **EXECUTABLE** | 0 | 1 |
| Phase 级 | — | 0 | 2 |

无 B-blocker。23-01 与 23-02 均可执行；23-02 以 23-01 为 precondition（wave 1 → wave 2，执行顺序已保证）。

---

## 23-01-PLAN.md — EXECUTABLE

### Blockers
无。

### Warnings
1. **W-23-01-1（fixture 引用不存在）**：Task 2 step 4 引用 `_make_client`（VIP 对照）——该 fixture 在 `backend/tests/test_guest_masking.py` 中不存在（全文件仅 `_make_guest_client` L146）。同文件既有 VIP 先例为 `_make_guest_client` + `client.cookies.set("tf_session", "valid-token")`（`test_vip_valid_cookie_returns_clear_hub` L263-284）。执行者需改用该既有模式或自行新增 `_make_client`。不影响目标达成，但需执行者自行发现替代路径。
2. **W-23-01-2（数值声明失准）**：计划多处称「既有 17 个 test_pool_hub 测试」——实测 `test_pool_hub.py` 现有 **27** 个测试函数（含 Phase 22 新增 dates/history 端点测试与 E1-E6 AST 守卫）。回归意图正确（`expected_keys` 8→12 是唯一需改的键集断言，其余测试均按具体键/值断言不受影响），但计数失实，建议更正为 27。
3. **W-23-01-3（UI-SPEC 契约措辞分歧）**：UI-SPEC §5.1 末句「real 缺时列缺席（诚实缺列，非 null 占位）」与计划 23-01「投影行恒为 12 键、缺键 → `None`」（Test 2 断言 4 键全为 None）措辞相左。UI-SPEC 自身不一致（同节要求 `expected_keys` 12 键、JSON 示例恒含 4 竞价键）。计划的「恒定 12 键 + 顶层声明权威」解读自洽（H1/PIT-3 满足，前端以 `auction_columns` 判定渲染、恒不读行值），建议对齐二文档措辞以免 verifier 误判。

### 逐项检查
| # | 检查项 | 结果 |
|---|--------|------|
| 1 | `frontmatter.validate --schema plan` + `verify.plan-structure` | ✅ valid，0 error，3 任务全字段齐全（files/action/verify/done） |
| 2 | 文件路径 | ✅ `backend/app/services/pool_hub.py`、`guest_masking.py`、`backend/tests/test_pool_hub.py`、`test_guest_masking.py`、`frontend/src/lib/api.ts`、`queryKeys.ts` 均存在 |
| 3 | 任务步骤完整有序 | ✅ T1 经共享 `_project_hub` 单点改动 → hub 与 history 双路径同得 `auction_columns`（PIT-6）；反漂移回显 L173、空缓存早退 dict、快照缺失空态 dict 均声明零改动。T2 正确定位 `mask_guest_hub`（guest_masking.py:31-43）并 `masked.pop("auction_columns", None)`。T3 扩展 api 类型 + queryKeys，`updated_at: number \| string \| null`（PIT-8） |
| 4 | verify 命令可运行 | ✅ `cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py -x -q`（`.venv` 存在）、`tests/test_guest_masking.py`、`cd frontend && npm run build`。无裸 `uv run pytest`，无全仓套件 |
| 5 | 前置门 | N/A（23-01 为 wave 1） |
| 6 | 护栏 | ✅ 不触碰 Watchlist.tsx（git 显示用户未提交改动）、/hub 契约零改动、零新增依赖、无 e2e |
| 7 | SC1-SC4 覆盖 | ✅ 后端侧 SC3（透传+声明+expected_keys 12 键测试）/SC4（guest 守卫）就位；前端 SC1-SC4 在 23-02 |
| 8 | docs/tests/cleanup | ✅ 每任务列测试文件；`<output>` 声明 `23-01-SUMMARY.md` |
| 9 | 零重叠 | ✅ phase-plan-index 确认 23-01/23-02 文件集不相交 |
| 10 | 跨计划契约 | ✅ `auction_columns` 形状（real/derived）、`PoolDatesResponse`（dates/count/latest，与 backend `get_pool_dates` 返回一致）、`updated_at` 双型均与 23-02 消费一致 |

---

## 23-02-PLAN.md — EXECUTABLE

### Blockers
无。

### Warnings
1. **W-23-02-1（前置门为隐式）**：23-01 → 23-02 的 precondition 以「Task 1/2 tsc 编译即失败，即为前置门未过」的形式声明（`<verification>` 段），属执行中途的 fail-fast，而非任务开始前的显式 import/route 检查。风险低（wave 顺序已保证 23-01 先执行，`execution_context` 引用 `23-01-SUMMARY.md`），但建议在 Task 1 起始加一行显式检查（如 `grep api.poolDates frontend/src/lib/api.ts`）以提高前置门确定性。

### 逐项检查
| # | 检查项 | 结果 |
|---|--------|------|
| 1 | `frontmatter.validate --schema plan` + `verify.plan-structure` | ✅ valid，0 error，3 任务全字段齐全 |
| 2 | 文件路径 | ✅ `PoolHubPage.tsx`/`StockListTable.tsx`/`e2e/pool-hub.spec.ts` 存在；`DateNavigator.tsx` 为新建（当前不存在，符合预期） |
| 3 | 任务步骤完整有序 | ✅ T1：selectedDate state + datesQuery + poolQuery 切换 + asOf 回退 + 空态分流（available:false 先于零池短路，PIT-2）+ DateNavigator 受控组件（下标步进、idx===-1 双禁用、PIT-5）。T2：auctionColumns prop + 两行分组表头 + 单元格（fmtBigNum/toFixed×）+ real 空整组隐藏 + AuctionColumnStatusBadge 四态（H3 双轨）。T3：prop 接线 + e2e SC1-SC4（installShell 增 mock，desktop-only 门禁沿用）。Task 1/2 零文件重叠、Task 3 依赖二者接线，同 plan 内顺序声明正确 |
| 4 | verify 命令可运行 | ✅ `cd frontend && npm run build`（= tsc -b && vite build）+ `npx playwright test e2e/pool-hub.spec.ts`；Playwright Chromium 未装时回退 `npm run dev` 手动核验（23-RESEARCH RQ6 已声明，计划引用该回退） |
| 5 | 前置门 | ⚠️ W-23-02-1（隐式 tsc fail-fast，见上） |
| 6 | 护栏 | ✅ 不触碰 Watchlist.tsx / `backend/**` / api.ts / queryKeys.ts（23-01 已交付）；零新增 npm 依赖（lucide 图标全在册）；e2e 全 mock 无真实后端 |
| 7 | SC1-SC4 覆盖 | ✅ SC1（T1+T3 e2e 步进/下拉/复位 + PIT-1 路径断言）、SC2（T1 空态分流 + T3 渲染序/白名单断言）、SC3（T2 分组渲染 + T3 分组/单位/tooltip/real 空 warning/guest 无列）、SC4（T2 徽标 + T3 probe/盘前/H3 历史快照诚实）均有一任务 + 一 verify |
| 8 | docs/tests/cleanup | ✅ e2e 用例按任务列出；`<output>` 声明 `23-02-SUMMARY.md` |
| 9 | 零重叠 | ✅ 与 23-01 文件集不相交（phase-plan-index 确认） |
| 10 | 跨计划契约 | ✅ 消费 23-01 的 `api.poolDates/poolHistory`、`QK.poolDates/poolHistory`、`PoolHubRow.auction_*`、`PoolHubResponse.available/auction_columns`；类型形状一致 |

---

## Phase 级发现

1. **W-PHASE-1（Nyquist 8e 门）**：`23-VALIDATION.md` 不存在（`config.json` `nyquist_validation: true`，RESEARCH 含 Validation Architecture 节）。按 Nyquist 维度 8e 属 BLOCKING FAIL（门禁级）——需 `/gsd-plan-phase 23 --research` 重新生成。**不影响两 plan 的代码可执行性**，但 phase 验证门会被卡，建议在规划侧补齐。
2. **W-PHASE-2（Research 格式）**：RESEARCH.md 用「设计决策（Open Questions → 推荐）」表承载 OQ-1..10 决议（全部有推荐），非标准「(RESOLVED)」后缀格式。实质全部已决议（UI-SPEC OQ 表亦确认），仅格式偏差。

---

## 复核要点（跨维度汇总）

- **诚实规则 H1-H8 / PIT-1..8**：全部被任务/verify 覆盖——H1/PIT-3（列存在性仅服务端声明，前端零推导）、H2/PIT-2（available:false ≠ 零池，渲染序短路）、H3（冻结列存在性 vs 实时 probe/时段双轨，历史快照不重写）、H4（无快照独立空态）、H5/PIT-5（白名单下标步进，不静默跳日）、H6/PIT-1（历史必走 `/api/pool/history`）、H7/PIT-7（guest 顶层 pop + 行级白名单剥离 + 守卫测试）、H8/PIT-8（`updated_at` 双型容忍）。列头单位 股/元/×/估算；09:30 连续竞价 bar 永不标集合竞价（沿用 AuctionProbeCard 诚实词汇）。
- **/hub 契约零破坏**：`expected_keys` 8→12 为唯一后端测试契约变更；反漂移回显、空缓存早退精确 dict、快照缺失空态 dict 均零改动；E1-E6 AST 守卫不受影响（`auction_*`/`auction_columns` 不含执行族词汇）。
- **范围（scope）**：两 plan 各 3 任务、4-6 文件，在阈值内（目标 2-3 任务、5-8 文件）。`estimate` tokens 52000/54000、confidence low（estimate-check verb 本 runtime 不可用，仅作参考）。
- **Context/CLAUDE.md**：无 CONTEXT.md（维度 7 跳过）；无 CLAUDE.md（维度 10 跳过）。PATTERNS.md 9/9 analog，计划 read_first 均引用对应 analog 源码位置（DatePicker/LimitUpLadder/Dashboard/`_project_hub`/`_GUEST_VISIBLE`/installShell），共享模式（queryKey 切换、mode 声明、诚实空态、数值单元格、徽标词汇）覆盖齐全。

---

## 修复建议（如采纳，concise）

- **23-01**：① T2 将 `_make_client` 改为既有 VIP cookie 模式（或补建该 fixture）；② 更正「17 回归」为 27；③ 与 UI-SPEC §5.1 对齐「缺列表达」措辞（二选一：恒定 12 键 None，或 8/12 键随声明变化）。
- **23-02**：① Task 1 起始加显式前置检查（grep/import 23-01 交付物）。
- **Phase**：① 补生成 `23-VALIDATION.md`。
