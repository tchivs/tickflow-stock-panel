---
phase: 31-auction-recap
plan: 3
subsystem: api
tags: [auction, recap, endpoint, guest-masking, ast-guard, pytest, docs]

# Dependency graph
requires:
  - phase: 31-01
    provides: "build_auction_recap / render_auction_recap_markdown (panel dict {as_of, data_completeness, blocks, built_at} — 端点同源装配)"
  - phase: 31-02
    provides: "REV-04 集成契约 (事件序/点评默认关/调度 15:40) — docs 描述面"
provides:
  - "GET /api/market-recap/auction 独立只读端点 (as_of 严格双重校验 → 400 / 诚实空态 200 available:false / guest 掩码 R12 DTO / 与 REV-04 面板同源)"
  - "main.py 注册 (market_recap.router 后, REV-05 注释)"
  - "6 项 POOL-03 AST 守卫 (REV 白名单重订: 禁 import token 收窄 auction_sync|pool_snapshot|pool_backfill, 禁调用 token 扩展 save_report, import 白名单含 preferences)"
  - "docs/features.md 竞价复盘节 (REV-01..05 全部要点)"
affects: [verify-work UAT REV-05, 31-03-SUMMARY consumers]

# Actuals (#2632) — pairs with the plan estimate (44k tokens / 3 tasks / low confidence).
# estimateTokens scale: chars/4 over the realized diff (git diff 751dfb8..HEAD, 34231 chars).
actuals:
  tokens: 8558
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "独立只读端点模块: 镜像 research_auction.py/auction_history.py 契约 — GET-only + 模块 docstring 概念词铁律 + 空态 200 available:false"
    - "as_of 严格双重校验: _AS_OF_RE fullmatch + date.fromisoformat → 400 invalid as_of (防路径穿越, 镜像 pool.py:99-107)"
    - "guest 脱敏 DTO 边界: _masked_row/_mask_block 深拷贝变换 — 身份 MASKED_IDENTITY + 竞价值剥离 + 聚合/状态标注保留 + probe 剥离 (R12 锁定)"
    - "TDD 垂直切片: 端点集成测试先行 (TestClient + guest/vip stub 中间件), 实现后全绿"
    - "AST 守卫白名单随 REV 语义重订: 禁 import token 收窄 + 禁调用 token 扩展, 差异注释单一事实源"

key-files:
  created:
    - backend/app/api/market_recap_auction.py
    - backend/tests/test_auction_recap_endpoint.py
    - backend/tests/test_auction_recap_guard.py
  modified:
    - backend/app/main.py
    - docs/features.md

key-decisions:
  - "guest 空态与 vip 同形: available:false + blocks:{} + data_completeness + reason (无 markdown, 无 probe); guest 正常态含 available:true + 掩码 blocks, 绝不带 markdown (掩码视图无渲染文本)"
  - "端点空态判定用 present 块过滤 (panel.get('blocks') 中 present:true 的块), 与 render 纯函数的 present 语义一致 — 三块全缺席 → 空态"
  - "as_of 缺省 → ScreenerService(repo).latest_date(); latest None → 诚实空态 (绝不 500); 端点直接传 date 对象给 build_auction_recap (服务内不复解析, as_of 单一来源)"
  - "engine = getattr(request.app.state, 'strategy_engine', None) — None 容错 (显示名退 sid), 镜像 research_auction"
  - "守卫白名单含 app.market_time (服务 import cn_now) + app.services.preferences (pre_eod 判别懒 import get_pipeline_schedule) — 以实际 shipped imports 为准, 非计划占位"

patterns-established:
  - "REV-05 端点与 REV-04 面板构造性同源: 同一 build_auction_recap + render_auction_recap_markdown 调用点 (验收 4)"
  - "守卫目标两文件存在且非空 (防守卫悬空) + GET-only 断言仅作用于新 api 模块"
  - "guest DTO 锁死: 身份键 (symbol/name/code) 掩码 + 敏感值键 (auction_*/open_gap) 剥离 + 聚合保留 — 与 mask_guest_hub/mask_guest_alert 白名单模型同族"

requirements-completed: [REV-05]

# Coverage metadata (#1602) — deterministic UAT routing.
coverage:
  - id: D1
    description: "GET /api/market-recap/auction 只读端点: as_of 严格双重校验 (合法 200 / 非法 400 invalid as_of 绝不 500), 缺省 latest_date 解析, latest None 诚实空态"
    requirement: REV-05
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_recap_endpoint.py#test_as_of_valid_returns_200"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap_endpoint.py#test_as_of_default_latest_date"
        status: pass
    human_judgment: false
  - id: D2
    description: "诚实空态: 无分区+无预览+enriched 空 → 200 {available:false, blocks:{}, reason} (绝不 404/500/0 填)"
    requirement: REV-05
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_recap_endpoint.py#test_empty_returns_available_false"
        status: pass
    human_judgment: false
  - id: D3
    description: "正常装配与 REV-04 面板同源: 分区+预览+enriched → 200 dict 含 as_of/data_completeness/blocks/built_at + available:true + markdown 确定性数据标记"
    requirement: REV-05
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_recap_endpoint.py#test_full_assembly_vip"
        status: pass
    human_judgment: false
  - id: D4
    description: "guest 掩码 (R12 DTO): 身份 ****** + 竞价值剥离 + 聚合/状态标注保留 + probe 剥离 + 无 markdown; vip 明文"
    requirement: REV-05
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_recap_endpoint.py#test_guest_masking"
        status: pass
    human_judgment: false
  - id: D5
    description: "POOL-03 AST 守卫 6 项 (REV 白名单): 存在非空/无执行族 import/GET-only/无写路径+禁调用 (含 save_report)/无 strategy_cache/import 白名单"
    requirement: REV-05
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_recap_guard.py#test_recap_modules_exist"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap_guard.py#test_recap_no_execution_imports"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap_guard.py#test_recap_api_is_get_only"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap_guard.py#test_recap_no_write_path"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap_guard.py#test_recap_no_strategy_cache_reference"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap_guard.py#test_recap_import_whitelist"
        status: pass
    human_judgment: false
  - id: D6
    description: "docs/features.md 竞价复盘节 (三块/data_completeness/pre_eod/事件序/15:40/点评默认关/REV-05 端点/POOL-03)"
    requirement: REV-05
    verification:
      - kind: unit
        ref: "grep -n '竞价复盘' docs/features.md"
        status: pass
    human_judgment: false

# Metrics
duration: 20min
completed: 2026-08-06
status: complete
---

# Phase 31 Plan 3: REV-05 独立只读端点 + POOL-03 守卫 + 文档 Summary

**GET /api/market-recap/auction 独立只读端点落地 — as_of 严格双重校验 (400) + 诚实空态 (200 available:false) + guest 掩码 (R12 DTO) + 与 REV-04 面板同源 (同一 build_auction_recap/render); 6 项 POOL-03 AST 守卫 (REV 白名单重订, 含 save_report 禁调用); main.py 注册 + docs/features.md 竞价复盘节; 全量后端 1686 项回归绿**

## Performance

- **Duration:** 20 min
- **Started:** 2026-08-06T15:20:00Z (approx)
- **Completed:** 2026-08-06T15:40:00Z (approx)
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- REV-05 验收 1/2/3: 新独立模块 `backend/app/api/market_recap_auction.py` — `APIRouter(prefix="/api/market-recap", tags=["market-recap"])` + 仅 `@router.get("/auction")` (GET-only 独立模块使守卫可整模块断言); `_AS_OF_RE.fullmatch` + `date.fromisoformat` 双重校验 → 400 `invalid as_of` (防路径穿越 T-31-03-01, 绝不 500); as_of 缺省 → `ScreenerService.latest_date()` (与复盘缺省口径一致), latest None → 诚实空态; 无 present 块 → 200 `{"available": False, "data_completeness", "blocks": {}, "reason"}` (绝不 404/500/0 填, 镜像 auction_history 空态契约)
- REV-05 验收 4: 端点与 REV-04 面板同源 — 同一 `build_auction_recap` 装配 + `render_auction_recap_markdown` 渲染 (测试断言 markdown 逐字等于渲染纯函数输出); vip 响应含 `available: True` + `markdown`
- REV-05 验收 5 (R12 DTO 锁定): guest 掩码 — 逐标的身份 (symbol/name/code → `MASKED_IDENTITY '******'`) 与竞价值/open_gap/量比剥离 (Top N 行只留掩码身份 + 排名); 聚合统计 (n_symbols/total_amount/高开分布/策略统计/n_missing) 与状态标注 (provisional/degraded/data_completeness/note/source) 保留; probe verdict 剥离; guest 视图不含 markdown (掩码视图无渲染文本, 诚实); `is_vip = request.state.reviewer_principal is not None` 镜像 auction_history.py:97
- REV-05 验收 6: 6 项 POOL-03 AST 守卫 (`tests/test_auction_recap_guard.py`) — 存在非空 (防守卫悬空) / 无执行族 import + REV 禁 import token (`auction_sync|pool_snapshot|pool_backfill`, premarket_snapshot/screener 不再禁 — REV 需 import 二者, 差异注释) / GET-only 仅作用于新 api 模块 / `_WRITE_PATTERNS` 照抄 + 禁调用 token 含 `save_report` / 无 strategy_cache (import 面与源码均查) / import 白名单 11 前缀 + 11 精确 (含 `app.services.preferences` — pre_eod 判别懒 import `get_pipeline_schedule()` 只读 getter)
- main.py 注册: import 块加 `market_recap_auction` (字母序) + `market_recap.router` 后 `app.include_router(market_recap_auction.router)` (注释 `# REV-05 竞价复盘只读面板端点 (POOL-03 零执行)` 镜像 research_auction 注释形)
- docs/features.md: 独立 `### 📊 竞价复盘 (Auction Recap)` 节 (盘后 AI 复盘 bullet 后) — 三块面板 / data_completeness 诚实枚举 / pre_eod 标注 / 事件序三跳全收 / 默认调度 15:40 / 点评默认关 / REV-05 端点 (GET-only/as_of 校验/诚实空态/guest 掩码) / POOL-03 守卫 / 零新增依赖
- 全量后端回归: **1686 passed, 2 skipped** (含 Phase 28/29/30 守卫 test_auction_validation.py / test_pool_hub.py / test_premarket_pool.py 等); 定向: endpoint 5 + guard 6 + test_auction_recap 23 + test_market_recap_delta 18 + test_auction_history 15 + test_auction_validation 10 = 77 全绿

## Task Commits

Each task committed atomically (TDD test → feat):

1. **Task 1: GET /api/market-recap/auction 垂直切片 (as_of 双重校验 + 诚实空态 + guest 掩码 + main.py 注册)** - `29f7a74` (test, RED) + `df68416` (feat, GREEN)
2. **Task 2: POOL-03 AST 守卫 (6 项镜像 test_auction_validation + REV 白名单重订)** - `672e728` (test)
3. **Task 3: docs/features.md 竞价复盘节 + 全量回归** - `fa9ce0e` (docs)

**Plan metadata:** final docs commit (this SUMMARY + STATE/ROADMAP/REQUIREMENTS) — pending

## Files Created/Modified
- `backend/app/api/market_recap_auction.py` - 独立只读端点模块 (REV-05): GET /auction + as_of 双重校验 + latest_date 缺省 + 诚实空态 + guest 掩码 (`_masked_row`/`_mask_block`/`_mask_guest_recap` R12 DTO) + vip markdown; 模块 docstring 概念词铁律 (POOL-03)
- `backend/app/main.py` - import 块 `market_recap_auction` + `market_recap.router` 后 `include_router(market_recap_auction.router)`
- `backend/tests/test_auction_recap_endpoint.py` - 5 项端点集成测试: as_of 校验 400 / 诚实空态 / 正常装配同源 (markdown 逐字断言) / guest 掩码 / latest_date 缺省 (TestClient + guest/vip stub 中间件镜像 test_auction_history.py:79-92)
- `backend/tests/test_auction_recap_guard.py` - 6 项 POOL-03 AST 守卫 (REV 白名单重订, 逐字镜像 test_auction_validation.py 结构)
- `docs/features.md` - 竞价复盘节 (REV-01..05 全部要点)

## Decisions Made
- **guest 空态与 vip 同形**: `available:false` + `blocks:{}` + `data_completeness` + `reason` — guest 空态不含 markdown/probe (与 vip 空态一致, R12 无附加字段)
- **端点空态判定 = present 块过滤**: `{k: v for k, v in panel.get("blocks", {}).items() if v.get("present")}` — 与 render 纯函数 present 语义一致; 三块全缺席 → 空态 (含 open_gap_snapshot present:false 的情形)
- **as_of 传 date 对象**: 校验通过后 `date.fromisoformat(as_of)` 一次解析, 直接传 `build_auction_recap` (服务内绝不复解析, as_of 单一来源); 缺省路径 latest 为 date/None
- **engine 取用**: `getattr(request.app.state, "strategy_engine", None)` — None 容错 (显示名退 sid, 诚实), 镜像 research_auction 模式
- **守卫白名单以实际 shipped imports 为准**: 服务模块实际 import `app.market_time` (cn_now) + `app.services.preferences` (懒 import) + `app.services.auction_columns/auction_probe/auction_validation/premarket_snapshot/screener` — 全部落入 REV 白名单 (含计划 parenthetical 未列全的 market_time, 计划正文 §7.2 已含)
- **测试 fixture 三源同日**: 预览装载按 as_of 分区匹配 — `_full_fixture` 将预览/enriched/分区统一写 as_of 日 (首跑发现 no_premarket_preview, Rule 1 修正 fixture 而非实现)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 测试 fixture 预览日期与 as_of 错位 → data_completeness 误报 no_premarket_preview**
- **Found during:** Task 1 (GREEN 验证, test_full_assembly_vip)
- **Issue:** `_full_fixture` 写预览至 FIXED_DATE 而 as_of 用前一交易日; `load_premarket_snapshot` 按 as_of 分区匹配 → 预览未命中 → `no_premarket_preview` 而非 `full`
- **Fix:** fixture 改为三源 (分区/预览/enriched) 统一写 as_of 日; 生产实现零改动 (端点/服务行为正确, 测试数据装配错位)
- **Files modified:** backend/tests/test_auction_recap_endpoint.py
- **Verification:** test_full_assembly_vip 断言 `data_completeness == "full"` 通过
- **Committed in:** df68416 (Task 1 feat commit)

**2. [Rule 1 - Bug] 未使用 helper `_patch_probe` 残留**
- **Found during:** Task 1 (自审)
- **Issue:** 初稿含未调用的 `_patch_probe` helper (端点不暴露 probe_resolver 注入点; 历史日闸门 probe 不参与, 无需注入)
- **Fix:** 删除死代码
- **Files modified:** backend/tests/test_auction_recap_endpoint.py
- **Verification:** 5 项端点测试全绿 (删除后复跑)
- **Committed in:** df68416 (Task 1 feat commit, 同 commit 内)

---

**Total deviations:** 2 auto-fixed (均为 Rule 1, 测试侧修正, 生产实现零偏差)
**Impact on plan:** 无 scope creep; 生产代码与计划逐字一致, 守卫白名单与 shipped imports 吻合

## Issues Encountered
- `frontend/src/pages/Watchlist.tsx` 工作树存在**预先存在**的未提交修改 (另一 agent 的 WIP, dropdown portal 改动, ~83+/50-) — 非本计划引入; 按计划 Watchlist.tsx 零触碰, 未纳入任何 commit, 留给其属主处理
- 全量回归产生既有 DeprecationWarning (starlette TestClient per-request cookies) — 非本计划引入, 不处理 (SCOPE BOUNDARY)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- REV-05 验收 1-6 全部绿: 端点只读 GET-only / as_of 严格校验 400 / 诚实空态 200 / 与 REV-04 面板同源 / guest 掩码 / 6 项 AST 守卫
- 全量后端 1686 passed — Phase 29/30 守卫 (test_auction_validation / test_pool_hub / test_premarket_pool) 不受 REV 白名单重订影响 (守卫目标不同模块, 互不触碰)
- Phase 31 三计划全部完成 (31-01 装配 + 31-02 集成 + 31-03 端点/守卫/文档); 待 verifier 阶段验收
- 零新增依赖; Watchlist.tsx 零触碰; 前端唯一触碰 = 31-02 Review.tsx:105 兜底字面量

## Self-Check: PASSED

- Files: backend/app/api/market_recap_auction.py ✓, backend/app/main.py ✓, backend/tests/test_auction_recap_endpoint.py ✓, backend/tests/test_auction_recap_guard.py ✓, docs/features.md ✓, 31-03-SUMMARY.md ✓
- Commits: 29f7a74 / df68416 / 672e728 / fa9ce0e 全部存在 ✓
- Suite runs: endpoint 5 + guard 6 + 相邻回归 66 = 77 targeted passed; 全量 backend 1686 passed, 2 skipped ✓

---
*Phase: 31-auction-recap*
*Completed: 2026-08-06*
