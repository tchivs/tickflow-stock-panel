---
phase: 18-pool-hub
verified: 2026-08-04T14:15:26Z
status: passed
score: 18/18
behavior_unverified: 0
overrides_applied: 0
gaps: []
human_verification:
  - test: "浏览器打开 /pool-hub，确认「数据不可用」卡片（如 动量增强）以 40% 不透明度渲染、不可点击，悬停显示 tooltip `该策略无 {as_of} 的持久化结果`；其余卡片保持可用"
    expected: "Backstop 1 达标：数据不可用 卡片 40% 不透明度 + tooltip，网格其余部分不失效"
    why_human: "不透明度/tooltip 的视觉呈现是观感类判断，自动化仅断言了 opacity-40 class 与 disabled 状态；最终视觉确认需人工"
  - test: "确认超长策略名（如视觉夹具中的超长中文名）在卡片内以省略号截断（truncate），不换行撑破卡片、不把当日池数挤出布局"
    expected: "Backstop 2 达标：长策略名单行截断，卡片布局稳定"
    why_human: "文本截断的视觉正确性需人工目检；自动化只断言了 truncate class 存在"
  - test: "确认缺失的 概念板块/关联因子 单元格渲染为 `—`（muted），且 hit_factors < 2 的行不渲染 交叉共振 徽标；行结构完整"
    expected: "Backstop 3 达标：缺失值显示 —，单命中行无徽标，行完整性保持"
    why_human: "单元格渲染观感需人工目检；自动化已断言 — 出现 3 处且无徽标"
  - test: "确认多行数据在 overflow-x-auto 滚动容器内滚动、footer 显示 `共 {M} 只`，代码列不被截断"
    expected: "Backstop 4 达标：多行滚动正常，footer 计数正确，代码列完整"
    why_human: "滚动/布局行为需人工目检；自动化只断言了容器 class 与 whitespace-nowrap"
  - test: "确认长概念名在筛选输入框和 概念板块 chips 中安全截断/换行（chip truncate，输入框 overflow-wrap:anywhere），不破坏筛选行布局"
    expected: "Backstop 5 达标：长概念名不撑破布局"
    why_human: "换行/截断的观感需人工目检；自动化只断言了 chip 的 truncate class"
  - test: "浏览器打开 /pool-hub，对照 18-UI-SPEC 目检整体一致性（组件树、色彩 token、状态文案、research-only 声明）"
    expected: "页面与 18-UI-SPEC 批准的组件树/文案/token 一致"
    why_human: "UI 视觉一致性属于人工签收范畴，自动化无法替代"
human_signoff: user-approved 2026-08-04 (放行 — 16 Playwright e2e 结构断言 + 5 张视觉基线截图作为证据)
---

# Phase 18: 股池 Hub (Pool Hub) — Verification Report

**Phase Goal:** Users can open a pool hub showing strategy cards with per-day pool counts, drill into each strategy's stock list (code, 开盘涨幅, 涨跌幅, 概念板块, 关联因子), filter by 概念, and highlight 交叉共振 — all research-only.
**Verified:** 2026-08-04T14:15:26Z
**Status:** human_needed (all 18 automated truths verified; 5 UI-SPEC backstop scalars + browser smoke await human sign-off)
**Re-verification:** No — initial verification

## 结论摘要 (Verdict)

目标反向验证完成。ROADMAP Phase 18 三项成功标准与 PLAN 18-01/18-02 的 18 条 must-have truth 全部在**实际代码**中得到证据支撑：后端 `build_pool_hub` + `GET /api/pool/hub` 只读端点、前端 `PoolHubPage` 完整组件树（卡片 → 钻取明细 → 概念筛选 → 交叉共振高亮）均真实存在、接线完整、行为有自动化测试锁定。**未发现 BLOCKER / 未发现 FAILED truth / 未发现缺口。** 唯一待办是 UI-SPEC 的 5 个 `backstop` 标量 + 页面整体视觉一致性需要人工签收 → 状态 `human_needed`（非 gaps_found）。

## Goal Achievement

### Observable Truths

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | Hub 读取**单一 as_of** 权威来源（`strategy_cache.read_cache`），卡片 total 与明细 rows 同源、永不漂移（POOL-01; PITFALL #10） | ✓ VERIFIED | `pool_hub.py:87` 单次 `read_cache`；`test_build_pool_hub_single_as_of_counts_and_columns` + `test_get_pool_hub_mismatched_as_of_returns_cache_date` 均绿 |
| 2   | 每行投影 5 列：code / 开盘涨幅(open_gap) / 涨跌幅(change_pct) / 概念板块(concept_board) / 关联因子(hit_factors)，服务端投影 | ✓ VERIFIED | `pool_hub.py:118-126` 投影 dict；`test_concept_board_join_and_missing_value_dash` 绿（缺失 change_pct → None） |
| 3   | 交叉共振服务端计算 = `len(hit_factors) >= 2`，每行暴露 `cross_resonance`，badge N 由 hit_factors 派生（POOL-02; STRAT-02） | ✓ VERIFIED | `pool_hub.py:115`；`test_build_pool_hub_single_as_of_counts_and_columns` 断言 Y 为 True、W/X 为 False、resonance_count==1 |
| 4   | 概念筛选是当前 as_of 池上的投影：可选 `concept` query param，大小写不敏感子串，`total` 保持权威全量（POOL-02） | ✓ VERIFIED | `pool_hub.py:98,128`；`test_concept_filter_keeps_total_authoritative` + `test_concept_filter_is_case_insensitive` + API `test_get_pool_hub_concept_filter_keeps_total` 全绿 |
| 5   | 池特性**零执行权限**（POOL-03 后端）：无 broker/order/execution/trade/portfolio 导入、无写路径、只暴露 GET | ✓ VERIFIED | `pool.py` 仅 `@router.get("/hub")`；AST 守卫 `test_pool_hub_no_execution_imports`/`test_pool_api_is_get_only`/`test_build_pool_hub_has_no_write_path`/`test_hub_response_has_no_execution_vocabulary` 全绿；独立 grep 仅命中 docstring 声明 |
| 6   | Hub 响应 JSON 安全且可加性：NaN/Inf → None，total 派生自持久化行数，as_of 回显缓存（不伪造第二个日期） | ✓ VERIFIED | `pool_hub.py:33-43 (_safe_num), 93, 108`；`test_build_pool_hub_sanitizes_nan` + `test_get_pool_hub_json_serializable_roundtrip` + `test_get_pool_hub_missing_cache_empty` 绿 |
| 7   | Hub 加载态：`股池加载中…` + Loader2 + `role="status"` + 骨架占位 + `刷新股池` pending 禁用 | ✓ VERIFIED | `PoolHubPage.tsx:90-102`；e2e「hub loading renders 股池加载中…」绿 |
| 8   | Hub 错误态：`股池加载失败：{message}。请检查数据源后重试。` `role="alert"`（danger/bg-danger-10 边框）+ `重试` 重跑查询 | ✓ VERIFIED | `PoolHubPage.tsx:105-116`；e2e「hub error renders the alert with 重试 action」绿 |
| 9   | 空 as_of：`EmptyState` 标题 `当日无股池结果` + 正文 `截至 {as_of}，竞价策略均无命中个股…`，网格区不空白 | ✓ VERIFIED | `PoolHubPage.tsx:119-125`；e2e「empty hub renders 当日无股池结果」绿 |
| 10  | 有结果态：策略卡片 `当日池 {N} 只`（N mono/tabular）+ 钻取表 + footer `共 {M} 只`，全部派生自单一 as_of 载荷 | ✓ VERIFIED | `PoolHubPage.tsx:128-165` + `StrategyCardGrid.tsx:94` + `StockListTable.tsx:214`；e2e「populated hub renders…」绿（当日池 2/1 只 + 共 2 只 + 共 1 只） |
| 11  | 卡片计数加载 `股池统计中…`（禁点）；零命中 `当日无命中` 仍可钻取空表；`数据不可用`（40% 透明度 + tooltip，禁点） | ✓ VERIFIED | `StrategyCardGrid.tsx:88-94`；e2e「zero-hit strategy drills…」+「strategy absent…数据不可用」绿 |
| 12  | 钻取加载 `股池明细加载中…`（spinner）；钻取错误 `股池明细加载失败：{message}。请重试。` 行内 `role="alert"` + `重试` | ✓ VERIFIED | `StockListTable.tsx:98-121`；e2e「drill-down refresh failure renders inline…」绿 |
| 13  | 钻取空态：策略无池 `当日无命中`；概念筛选无匹配 `无符合「{概念}」的个股` + `试试切换其他概念或清除筛选。` + `清除筛选` | ✓ VERIFIED | `StockListTable.tsx:124-145`；e2e「concept filter with no match…」+「zero-hit…」绿 |
| 14  | 交叉共振存在：`bg-accent/[0.06]` + 左边框 + `交叉共振 · {N} 策略` 徽标 + legend `交叉共振：被 ≥2 个竞价策略同时命中的个股`；无共振 `今日无交叉共振` + `暂无个股被 ≥2 个竞价策略同时命中。` | ✓ VERIFIED | `StockListTable.tsx:163-196,218-222`；e2e「交叉共振 row renders the badge and legend…」+「no cross resonance renders 今日无交叉共振」绿 |
| 15  | 表头精确 `代码 · 开盘涨幅 · 涨跌幅 · 概念板块 · 关联因子`；开盘涨幅/涨跌幅用 `fmtPct`+`priceColorClass`（红涨绿跌，缺失 `—`）；概念板块 chips；关联因子 STRATEGY_TAG_CLS | ✓ VERIFIED | `StockListTable.tsx:13,35-74,153-155`；e2e「populated…」表头断言 +「accessibility and copy compliance」`+2.34%`/`-0.12%` 断言绿 |
| 16  | 概念筛选客户端投影：label `概念筛选`、placeholder `输入概念名筛选…`、非空显示清除 X、`清除筛选` 动作；**不触发第二次 fetch** | ✓ VERIFIED | `ConceptFilter.tsx:20-67` + `PoolHubPage.tsx:47-54`；e2e「concept filter projects client-side…」断言 `hubRequests === 1`（输入后不增）绿 |
| 17  | 页头：标题 `股池`、副标题 `竞价策略 · 数据日期 {as_of} · 仅研究参考`、动作 `刷新股池`（RefreshCw）；钻取标题 `{策略名} · 股池明细`；研究声明 footer `本页面仅用于研究参考，不提供任何交易执行功能。` | ✓ VERIFIED | `PoolHubPage.tsx:67-86,151,169`；e2e「populated…」断言副标题 + 钻取标题 + 声明绿 |
| 18  | POOL-03 前端：**零执行外观** — 无 trade/order/buy/sell 控件、无执行 API 调用、无 mutating 请求、无 `<form>`；唯一交互为钻取/客户端筛选/刷新（均只读） | ✓ VERIFIED | e2e「pool page renders zero execution affordances (POOL-03)」+「never issues a mutating request (POOL-03)」+「source contains no execution API call or form」绿；独立 grep 仅命中「不提供任何交易执行功能」声明文本 |

**Score:** 18/18 truths verified（0 present-behavior-unverified，0 FAILED，0 override）

### Deferred Items

无。本阶段所有成功标准均已达成，无项推迟到后续阶段（日期导航 POOL-04 属 v2，超出本阶段范围且已明确记录于 18-CONTEXT.md）。

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `backend/app/services/pool_hub.py` | `build_pool_hub` 只读投影服务 | ✓ VERIFIED | 存在且实质：`read_cache` 单源、5 列投影、`cross_resonance`、concept filter、`_safe_num`、`_build_concept_map`；无写路径 |
| `backend/app/api/pool.py` | `GET /api/pool/hub` 只读 router | ✓ VERIFIED | 存在且实质：`APIRouter(prefix="/api/pool")` 仅 `@router.get("/hub")`；`_strategy_display_name` 服务端解析 |
| `backend/app/main.py` | pool router 注册 | ✓ VERIFIED | `import pool`（L34）+ `app.include_router(pool.router)`（L830） |
| `backend/tests/test_pool_hub.py` | fixture + API + POOL-03 guard 测试 | ✓ VERIFIED | 17 个测试，实际运行 **17 passed in 0.64s** |
| `frontend/src/pages/PoolHubPage.tsx` | 页面组合（header→filter→cards→table→footer） | ✓ VERIFIED | 存在且实质：单 as_of `QK.poolHub`、四态、POOL-03 footer |
| `frontend/src/components/pool-hub/StrategyCardGrid.tsx` | 只读卡片网格，四态 | ✓ VERIFIED | `股池统计中…`/`当日无命中`/`数据不可用`/active 全实现 |
| `frontend/src/components/pool-hub/ConceptFilter.tsx` | 客户端投影筛选 | ✓ VERIFIED | label + input + clear X + 清除筛选 + `aria-describedby` |
| `frontend/src/components/pool-hub/StockListTable.tsx` | 五列钻取表 + 交叉共振高亮 | ✓ VERIFIED | 精确列头、PctCell、chips、STRATEGY_TAG_CLS、徽标、legend |
| `frontend/src/lib/api.ts` | PoolHub 类型 + `api.poolHub` | ✓ VERIFIED | `PoolHubRow/Strategy/Response` + `poolHub(asOf?, concept?)` GET |
| `frontend/src/lib/queryKeys.ts` | `QK.poolHub` | ✓ VERIFIED | `['pool-hub', asOf ?? 'latest']`，不在 SSE_INVALIDATE_PREFIXES |
| `frontend/src/router.tsx` | `/pool-hub` 路由 | ✓ VERIFIED | lazy `PoolHubPage` + `{ path: 'pool-hub' }`（L29/L83） |
| `frontend/src/components/Layout.tsx` | 股池 nav | ✓ VERIFIED | `{ to: '/pool-hub', label: '股池', icon: Layers3 }`（L77） |
| `frontend/e2e/pool-hub.spec.ts` | Playwright 门禁 | ✓ VERIFIED | 16 个测试，实际运行 **16 passed (32.6s)** |
| `frontend/e2e/pool-hub.spec.ts-snapshots/` | 5 张 backstop 视觉基线 | ✓ VERIFIED | 5 个 PNG 存在（grid/table-resonance/filter-active/zero-hit/unavailable） |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `strategy_cache.read_cache(data_dir)` | `build_pool_hub(as_of, concept, name_for)` | 单一 `read_cache` 调用喂给 total+rows（`pool_hub.py:87`） | ✓ WIRED | 单一 as_of、零漂移；guard 测试锁定 |
| Phase 17 `rows[].hit_factors` | `build_pool_hub` `cross_resonance` (≥2) → 徽标 | `pool_hub.py:114-115` → 响应 → `StockListTable.tsx:192-195` | ✓ WIRED | 服务端派生，前端只渲染不重算 |
| ExtConfigStore/`market_overview_builder` concept seam | `_build_concept_map` → 概念板块 join | `pool_hub.py:46-66`（`_dimension_field`/`_read_ext_rows`/`_dimension_values`/`_symbol_keys`） | ✓ WIRED | 无新概念数据源；缺数据 → `[]`/`—` |
| `api.poolHub()` | `QK.poolHub(asOf)` → PoolHubPage useQuery → 卡片+明细 | `api.ts:2067-2075` → `queryKeys.ts:41` → `PoolHubPage.tsx:21-25` | ✓ WIRED | 单一载荷无漂移 |
| ConceptFilter input | 客户端投影 → `筛选后 {N} 只 / 共 {M} 只` | `PoolHubPage.tsx:47-54` → `StockListTable.tsx:211-215` | ✓ WIRED | 输入不触发二次 fetch（e2e 断言 hubRequests==1） |
| Layout nav `股池` | `/pool-hub` 路由 → PoolHubPage | `Layout.tsx:77` → `router.tsx:83` → `PoolHubPage.tsx` | ✓ WIRED | 页面可达 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `build_pool_hub` strategies/rows | `strategy_cache.read_cache(data_dir)` | 持久化 `user_data/strategy_cache.json` | ✓ 真实持久化读取 | ✓ FLOWING |
| 概念板块 | `ExtConfigStore(data_dir).load_all()` + concept parquet | `ext_data/*/part.parquet` 概念维度 | ✓ 真实 ext 数据 seam | ✓ FLOWING |
| PoolHubPage 卡片计数/明细 | `QK.poolHub()` → `GET /api/pool/hub` | 后端投影响应 | ✓ 单一载荷驱动卡片+明细 | ✓ FLOWING |
| `数据不可用` 策略全集 | `api.screenerStrategies('stock')` | 策略 preset 列表 | ✓ 仅作名称源，不参与计数 | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 后端 pool hub 全量测试 | `cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py -q` | **17 passed in 0.64s** | ✓ PASS |
| 前端 TypeScript 编译 | `cd frontend && npx tsc --noEmit` | exit 0 | ✓ PASS |
| 前端 Playwright e2e | `cd frontend && npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium` | **16 passed (32.6s)** | ✓ PASS |
| POOL-03 独立源码审计（后端） | grep `broker|order|execution|trade|portfolio|…` in `pool_hub.py`+`pool.py` | 仅 docstring 声明，无实际导入 | ✓ PASS |
| POOL-03 独立源码审计（前端） | grep 执行族词汇 in 4 个 pool 文件 | 仅 research-only 声明文本 | ✓ PASS |

### Probe Execution

本阶段未声明 probe 脚本（`scripts/*/tests/probe-*.sh` 不存在于 PLAN/SUMMARY，亦无常规 probe 路径）；PASS 标记以 pytest + Playwright + tsc 实测替代。Step 7c: SKIPPED（无 probe 契约）。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| POOL-01 | 18-01 + 18-02 | 股池页显示策略卡片当日计数 + 五列钻取明细，单一 as_of 源不漂移 | ✓ SATISFIED | 后端 6 项投影测试 + 前端 e2e populated/zero-hit/unavailable 测试全绿 |
| POOL-02 | 18-01 + 18-02 | 概念筛选 + 交叉共振高亮（hit_factors ≥ 2） | ✓ SATISFIED | `test_concept_filter_*` + e2e filter/交叉共振/no-match/none 测试全绿 |
| POOL-03 | 18-01 + 18-02 | 研究只读投影，池特性零执行权限/零订单路由 | ✓ SATISFIED | 后端 4 项 AST guard + 前端 3 项 POOL-03 e2e + 独立源码审计全部通过 |

无孤儿需求：REQUIREMENTS.md 中映射到 Phase 18 的 POOL-01..03 全部被两个 PLAN 的 `requirements` 声明覆盖。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | 无 TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER | — | 无 |
| — | — | 无 `<form>`、无 `dangerouslySetInnerHTML`、无 `return null` 空实现 | — | 无 |
| — | — | 无硬编码空数据 / 空 props 桩 | — | 无 |

### Human Verification Required

全部 18 条 truth 已有自动化证据（17 pytest + 16 Playwright + tsc）。以下 UI-SPEC `backstop` 标量（5 项）+ 页面整体视觉一致性为**人工签收项**——自动化已断言结构属性并提交 5 张视觉基线截图，但观感类确认需人工：

1. **Backstop 1 — 数据不可用卡片** — 打开 `/pool-hub`，确认无持久化结果的策略卡片以 40% 不透明度渲染、不可点击、tooltip `该策略无 {as_of} 的持久化结果`，其余卡片可用。
2. **Backstop 2 — 长策略名截断** — 确认超长策略名单行 `truncate`，不撑破卡片/不挤压当日池数。
3. **Backstop 3 — 缺失单元格 `—`** — 确认缺失 概念板块/关联因子 渲染 `—`（muted），<2 命中行无交叉共振徽标，行完整性保持。
4. **Backstop 4 — 多行滚动** — 确认多行在 `overflow-x-auto` 容器内滚动、footer `共 {M} 只`、代码列不截断。
5. **Backstop 5 — 长概念名换行** — 确认筛选输入框 `overflow-wrap:anywhere`、概念 chips `truncate`，不破坏筛选行布局。
6. **页面整体一致性** — 对照 18-UI-SPEC 目检组件树/色彩 token/文案/交互。

证据：`frontend/e2e/pool-hub.spec.ts-snapshots/` 下 5 张基线（`pool-grid-populated` / `pool-table-resonance` / `pool-table-filter-active` / `pool-empty-zero-hit` / `pool-card-unavailable`）+ e2e「accessibility and copy compliance」测试已断言对应结构属性（opacity-40 / truncate / — / overflow-x-auto / whitespace-nowrap）。按 UI-SPEC #1154，backstop 在无人为签收前不得静默通过。

### Gaps Summary

**无缺口。** 未发现任何 FAILED truth、缺失/桩工件、断开的 key link、或债务标记。三项成功标准与全部 18 条 must-have truth 均有真实代码 + 实际运行测试的双重证据。唯一未决事项为 UI-SPEC 5 个 backstop 标量 + 页面视觉一致性的人工签收，属流程要求的 `human_needed` 状态，不影响功能正确性。

---

_Verified: 2026-08-04T14:15:26Z_
_Verifier: Claude (gsd-verifier, Verifier18)_
