---
phase: 29-auction-validation
plan: 3
subsystem: api
tags: [fastapi, endpoint, POOL-03, AST-guard, honest-empty, BT-01, BT-06]

requires:
  - phase: 29-auction-validation
    provides: "BT-03/04/05 AuctionValidationService.build_report 服务契约 (29-02)"
  - phase: 29-auction-validation
    provides: "BT-02 attach_auction_columns_range 区间注入原语 (29-01)"
provides:
  - "BT-01 GET /api/research/auction/validation 只读端点 — 参数校验 (400/422) + 服务装配 + 诚实 200 空态 (data_gate/empty_reason/coverage), 绝不 404/500"
  - "BT-06 POOL-03 AST 守卫 6 项 — 零执行 import / GET-only / 零写 / 零缓存指针 / 零计算触发 / import 白名单 (独立守卫目标, 不与 research.py 混入)"
affects: [29-auction-validation, docs]

actuals:
  tokens: 5968        # chars/4 over realized diff (23871 chars / 4); estimate 39000 → 大幅低实现 (镜像模板 + 服务面已由 29-02 交付)
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Read-only endpoint: module docstring declares GET-only/zero-write/no-execution-imports (concept-word discipline, guard-token-free literals); _bad_request copied verbatim from research.py:86-87; _split_csv comma-parse (None/[] semantics); probe passthrough via service probe_resolver (D-03)"
    - "POOL-03 AST guard: standalone test file with self-contained constants (mirror test_pool_hub.py:857-963 E1/E3/E4/E5 shapes + Phase-29 forbidden import/call token sets + import whitelist)"
    - "Endpoint integration: _make_client minimal FastAPI app (repo + real StrategyEngine + stub auth) + monkeypatch service-module probe global"

key-files:
  created:
    - backend/app/api/research_auction.py
    - backend/tests/test_auction_validation.py
  modified:
    - backend/app/main.py
    - backend/tests/test_auction_validation_report.py
    - docs/features.md

key-decisions:
  - "probe 透传由服务层承担: handler 直接构造 AuctionValidationService(repo, engine) 调 build_report — 服务层 probe_resolver 顶部解析一次, 所有路径 (含 enriched_unavailable) 响应均带 probe 字段 (29-02 决策承接, D-03)"
  - "Test 6 白名单补 collections.abc: 29-02 已交付服务 import 面含 collections.abc (Callable 注入点, 29-02-SUMMARY 明示白名单前置满足); 计划 parenthetical 列表 (datetime/typing/logging/pathlib/re/ast) 遗漏, 以 stdlib 成员身份加入白名单 — 不改已交付服务"
  - "前端零触碰: frontend/src/pages/Watchlist.tsx 在本次执行开始前已有未提交的既有改动 (portal 下拉修复), 本计划三个 commit 均零触碰 frontend/ (D-05)"

requirements-completed: [BT-01, BT-06]

coverage:
  - id: R1
    description: "BT-01 端点落地 — GET-only /api/research/auction/validation, 空湖 → 200 全形状 (data_gate==empty + no_auction_partitions + coverage + 9 strategies + probe), available 当 enabled 日期存在"
    requirement: BT-01
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_endpoint_empty_lake_full_shape_200"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_endpoint_available_gate_with_partitions"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_endpoint_param_matrix_400_422_empty_skipped_clamp"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_endpoint_forward_stats_branch_minute_confirm"
        status: pass
    human_judgment: false
  - id: R2
    description: "BT-06 POOL-03 AST 守卫 6 项全绿 (存在性/禁执行 import/GET-only/零写/零缓存指针/import 白名单) + test_pool_hub E1-E6 零改动保持绿"
    requirement: BT-06
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_validation.py (6 tests, full file)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py (35 tests, E1-E6 unchanged)"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-08-06
status: complete
---

# Phase 29 Plan 3: GET /api/research/auction/validation 端点 + POOL-03 AST 守卫 (BT-01/BT-06) Summary

**只读竞价策略历史验证端点落地: `backend/app/api/research_auction.py` (GET `/api/research/auction/validation`, 镜像 auction_history.py 只读范本 + research.py `_bad_request`) + main.py 一行注册 + 独立 POOL-03 AST 守卫文件 (`tests/test_auction_validation.py`, BT-06 6 项) + 端点集成测试 4 项 (空湖 200 全形状 / available 闸门 / 参数矩阵 400/422/空列表/skipped/窗口回夹 / BT-04 经 API 复验) + docs 小节 — 全量回归 248 绿, 零新增依赖, 零写面, frontend/backtest seam 零触碰 (D-05/D-08).**

## Performance

- **Duration:** 7 min
- **Started:** 2026-08-06T12:52:31Z
- **Completed:** 2026-08-06T12:59Z
- **Tasks:** 3 (tracer + guard/integration + docs/regression)
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- `backend/app/api/research_auction.py` — GET-only 只读端点 (POOL-03, D-01):
  - 模块 docstring 声明 GET-only/零写/零执行 import/不套 186 天 guard (D-06)/无 guest 掩码; 概念词纪律 — 全文件 grep 0 个守卫禁 token 字面串。
  - `router = APIRouter(prefix="/api/research", tags=["research"])` (与 research.py 同前缀, 独立守卫目标); `_bad_request` 逐字复制 research.py:86-87 (N3 锚点已按 live 文件核对)。
  - `_split_csv` 逗号参数解析 (None → None / 空串 → [] / strip 去空); `start > end` → 400 RESEARCH_VALIDATION; 坏日期 → FastAPI 422。
  - 装配: `AuctionValidationService(repo, engine).build_report(...)` — probe 由服务层 probe_resolver 顶部解析一次透传 (D-03); 诚实 200 空态由服务层保证。
- `backend/app/main.py` — import 块 (research 后按字母序加 `research_auction,`) + `app.include_router(research_auction.router)` 紧跟 research.router 之后 (L856 后) + 注释; guest 白名单零改动。
- `backend/tests/test_auction_validation.py` — BT-06 守卫 6 项 (自建常量/helper, 不跨模块 import 守卫):
  - `_EXECUTION_TOKEN`/`_WRITE_PATTERNS`/`_imported_module_names` 逐字复制 test_pool_hub.py:857-963; Phase-29 扩展 `_FORBIDDEN_IMPORT_TOKEN` (auction_sync|pool_snapshot|pool_backfill|premarket_snapshot|screener) + `_FORBIDDEN_CALL_TOKENS` (run_all|run_preset|write_cache|persist_point_snapshot) + import 白名单前缀/精确集。
  - 6 测试: 存在性 (防守卫悬空) / 无执行 import+禁 import / API GET-only / 零写+零调用 token / 零 strategy_cache 字面量 (import 面+源码) / import 白名单。
- `backend/tests/test_auction_validation_report.py` — 端点集成测试 4 项 (29-02 同文件追加):
  - `_make_client` (repo + 真 StrategyEngine builtin dirs + stub auth + include router) + `_patch_service_probe` (patch 服务层模块全局 resolve_auction_probe)。
  - 空湖 200 全形状 (data_gate/empty_reason/coverage/9 id/4 real n_dates==0 branch real/probe/skipped); available 闸门 (分区在位 → data_gate available + alpha real); 参数矩阵 (400/422/空串 strategies:[]/未知 id skipped/超覆盖窗口回夹双字段回显); BT-04 三公式经 API 手算复验 + branch 互斥 + minute_confirm。
- `docs/features.md` — 「🧪 竞价策略历史验证 (Auction Strategy Validation)」小节 (端点/诚实 data_gate/互斥 branch/BT-04 口径/诚实边界/无前端 D-05), 插在盘前预览与指标流水线之间。

## Task Commits

1. **Task 1: GET /api/research/auction/validation 端点 + main.py 注册 (BT-01/BT-03 API 面)** — `b3ee490` (feat: endpoint module + registration; verify: py_compile + single GET route + grep include_router)
2. **Task 2: POOL-03 AST 守卫 (BT-06) + 端点集成测试 (BT-01/BT-03 经 API 复验)** — `435f85c` (test: 6 guards + 4 endpoint integration tests; verify: 22 passed + test_pool_hub 35 passed)
3. **Task 3: docs/features.md 小节 + 全量回归锁** — `ae9dcbe` (docs: section; verify: 36 passed new-files + 248 passed full regression + docs grep 1)

## Files Created/Modified
- `backend/app/api/research_auction.py` — 新, ~72 行: `router` / `_bad_request` (research.py:86-87 逐字) / `_split_csv` / `auction_validation` handler (GET-only, 参数校验, 服务装配)
- `backend/app/main.py` — 修改 (+3 行): import `research_auction` + include_router 紧跟 research.router
- `backend/tests/test_auction_validation.py` — 新, ~140 行: BT-06 守卫常量/helper + 6 测试
- `backend/tests/test_auction_validation_report.py` — 修改 (+202 行): `_make_client`/`_patch_service_probe` + 4 端点集成测试
- `docs/features.md` — 修改 (+9 行): 竞价策略历史验证小节

## Decisions Made
- **probe 透传由服务层承担** (承接 29-02): handler 不再显式解析 probe — `AuctionValidationService(repo, engine)` 构造时 probe_resolver 缺省取服务层模块全局, build_report 顶部解析一次, 所有路径响应均带 `probe` 字段 (空湖全形状断言前置); 端点 import 面因此不含 auction_probe, 守卫面最小。
- **Test 6 白名单补 collections.abc**: 计划 parenthetical stdlib 列表遗漏 29-02 已交付服务的 `collections.abc` import (Callable 注入点); 以 stdlib 成员身份加入 `_IMPORT_EXACT` (29-02-SUMMARY 明示该白名单前置满足) — 不改已交付服务代码。
- **Watchlist.tsx 既有改动不触碰**: 执行开始前工作区已有未提交修改 (portal 下拉修复); 本计划三 commit 均不 stage 该文件 (绝无 `git add -A`), D-05 对我方 delta 成立。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Plan-internal literal tension] 守卫白名单 stdlib 列表遗漏 collections.abc**
- **Found during:** Task 2 (test_validation_import_whitelist 首跑红)
- **Issue:** 计划 Test 6 白名单 parenthetical "(datetime/typing/logging/pathlib/re/ast)" 未列 `collections.abc`, 而 29-02 已交付服务 import 面含之 (29-02-SUMMARY: "服务模块 import 面 = {polars, collections.abc, ...} — 29-03 Test 6 白名单前置满足"); 首跑 AssertionError `import 越出白名单: collections.abc`。
- **Fix:** 将 `collections.abc` 以 stdlib 成员加入 `_IMPORT_EXACT` 白名单集 (附注释注明 29-02 锚点); 未改任何已交付源码, 守卫语义不变 (仍是封闭白名单, 只是补全既有 stdlib 面)。
- **Files modified:** backend/tests/test_auction_validation.py
- **Verification:** `pytest tests/test_auction_validation.py tests/test_auction_validation_report.py -x -q` → 22 passed
- **Committed in:** 435f85c (Task 2 commit)

### Pre-existing conditions (not caused by this plan)

**2. frontend/src/pages/Watchlist.tsx 未提交既有改动**
- **Found during:** Task 1 (初始 git status 即有 ` M frontend/src/pages/Watchlist.tsx`, portal 下拉修复, +83/−50)
- **Handling:** 本计划零触碰 frontend/ (D-05); 三 commit 文件清单不含任何 frontend 路径; 该改动保持未提交状态留待归属方处理。计划 Task 3 的「frontend/ 零改动」对我方 delta 成立, 但工作区整体 status 含该既有改动 — 已在 Summary 与回传中明示。

---

**Total deviations:** 1 auto-fixed (plan-internal literal tension) + 1 pre-existing condition documented
**Impact on plan:** None — 验收口径 (BT-01/BT-06) 全部满足; 无范围变更。

## TDD Gate Compliance

- Plan frontmatter `type: execute` (not `tdd`) → plan-level RED/GREEN/REFACTOR gate sequence not applicable.
- Task 2 (`tdd="true"`, **test-only files**): 被测 feature (端点/服务) 已由 Task 1 与 29-02 交付, 测试即写即绿 — RED 无法构造 (与 29-02 Task 2 同型); 记为单 `test(...)` commit (`435f85c`). 测试暴露 1 处守卫白名单遗漏 (deviation 1) 并已修入守卫测试。

## Issues Encountered
- 无运行期错误。全部 verify 首跑除守卫白名单 1 处 (见 deviation 1) 外均绿。

## Known Stubs
None — 6 守卫 + 4 端点测试全部断言真实值; 无占位/跳过/未接线数据源.

## Threat Flags
None — 新增面为只读投影端点: 参数注入防线 (T-29-03-01, 400/422/白名单解析 Test 8 锁死), GET-only/零写/禁调用 token (T-29-03-02, 6 项 AST 守卫锁死), 诚实空态 200 (T-29-03-03, Test 7 锁死), probe 透传 (T-29-03-04, accept — 与 auction_history 先例一致), 窗口回夹防无界装载 (T-29-03-05, Test 8 锁死) — 全部按 threat_model mitigate 实现并由测试锁死.

## User Setup Required
None.

## Next Phase Readiness
- Phase 29 全部 3 计划完成 (29-01 BT-02 / 29-02 BT-03/04/05 / 29-03 BT-01/06); 无后续波次计划。
- BT-07 (全量竞价回测) 按 ROADMAP 推迟至 v2.3+ (D-08 backtest seam 零触碰)。
- 待办: Watchlist.tsx 既有改动归属 (pre-existing, 非本计划产物)。

## Self-Check: PASSED
- FOUND: backend/app/api/research_auction.py, backend/tests/test_auction_validation.py, backend/tests/test_auction_validation_report.py (4 endpoint tests), docs/features.md (auction/validation grep=1)
- FOUND commits: b3ee490 (Task 1), 435f85c (Task 2), ae9dcbe (Task 3)
- Final suites: test_auction_validation.py 6 passed; test_auction_validation_report.py 16 passed (12 服务 + 4 端点); test_attach_auction_columns_range.py 14 passed; test_pool_hub.py 35 passed; 全量回归 248 passed
- Zero-change surfaces: backend/app/backtest/, api/research.py, api/auction_history.py, api/pool.py — 0 diff in my commits; frontend/ — pre-existing user modification untouched (documented)

---
*Phase: 29-auction-validation*
*Completed: 2026-08-06*
