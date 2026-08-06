---
phase: 28-concept-pit
plan: 3
subsystem: api
tags: [concept-seam, read_partition, as_of, dimension-rank, rps-rotation, overview, polars]

# Dependency graph
requires:
  - "28-01: concept_history.read_partition 原语 + /api/pool/history concept_effective_date 透传"
provides:
  - "market_overview_builder._dimension_rank(..., as_of) 分支: 总览历史概念/行业板块由 D 日分区聚合 (kind→gn_ths/hy_ths, 局部 import 防循环, 分区缺失诚实降级为空)"
  - "build_market_overview :503-504 接线: explicit_as_of 时透传 as_of 到 concept_rank/industry_rank; as_of=None 行为逐位一致"
  - "rps_rotation._load_concept_map_df(repo, as_of): as_of 非空绕过 600s 模块级缓存读 D 日 gn_ths 分区 (缓存零污染)"
  - "rps_rotation.build_rps_rotation(repo, days, as_of): as_of 透传 + 结果缓存绕过 + _build_rotation_full 复用"
  - "api/rps.py GET /api/rps/rotation?as_of=: 镜像 api/pool.py 双校验 (非法 → 400), GET-only"
  - "CONCEPT-07 复验: /api/pool/history 透传 effective/captured_at 不回退 + overview as_of 消费分区"
affects: [28-04]

# Actuals (#2632) — pairs with the plan's `estimate` (52000 tokens, low confidence)
actuals:
  tokens: 8022    # 32088 realized-diff chars / 4
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "函数体内局部 import concept_history (防循环依赖铁律; concept_history 模块级 import 了 market_overview_builder._dimension_field)"
    - "as_of 非空 → 分区缺失诚实降级为空, 绝不混用当前 ext (T-28-03-03)"
    - "as_of 查询绕过/复键模块级缓存 (600s 概念 map + 120s 结果缓存), 永不污染最新视图 (T-28-03-02)"
    - "api as_of 双校验: ^\\d{4}-\\d{2}-\\d{2}$ fullmatch + date.fromisoformat → 400 (镜像 api/pool.py:99-107, T-28-03-01)"

key-files:
  created:
    - backend/tests/test_concept_seam.py
  modified:
    - backend/app/services/market_overview_builder.py
    - backend/app/services/rps_rotation.py
    - backend/app/api/rps.py

key-decisions:
  - "_dimension_rank as_of 分支在函数体内局部 import concept_history; as_of 参数兼容 str 与 date (build_market_overview/market_recap 传 date, read_partition 要 str → isoformat 归一)"
  - "build_rps_rotation 提取 _build_rotation_full 私有 helper 复用 join/agg/grouped 段 (as_of 与 latest 两分支各一次), 避免复制 40 行"
  - "as_of 分支空 map → 返回空矩阵 (dates/columns/concept_count), 不 fallback 当前 ext"
  - "RPS 矩阵各历史列仍共用单日 map (RESEARCH §3.4 语义); 逐日概念 map 各列独立属未来增强, 不在本期"

patterns-established:
  - "共享 seam: 三消费方 (pool_hub 28-01 / _dimension_rank / _load_concept_map_df) 统一走 concept_history.read_partition"
  - "测试 hermetic 镜像 test_concept_history fixtures: _write_concept_ext (ExtConfig config.json + part.parquet) + _write_partition_fixture (直写 ext_history 分区, 不依赖 capture)"

requirements-completed: [CONCEPT-06, CONCEPT-07]

coverage:
  - id: D1
    description: "_dimension_rank as_of 分支: kind==concept→gn_ths, industry→hy_ths; 分区优先于当前 ext; 分区缺失诚实降级"
    requirement: CONCEPT-06
    verification:
      - kind: unit
        ref: "backend/tests/test_concept_seam.py#test_dimension_rank_as_of_partition_priority"
        status: pass
      - kind: unit
        ref: "backend/tests/test_concept_seam.py#test_dimension_rank_industry_maps_to_hy_ths"
        status: pass
    human_judgment: false
  - id: D2
    description: "build_market_overview :503-504 接线: explicit_as_of 时 concept_rank/industry_rank 由 D 日分区; as_of=None 行为与现状一致"
    requirement: CONCEPT-06
    verification:
      - kind: unit
        ref: "backend/tests/test_concept_seam.py#test_build_market_overview_as_of_wiring"
        status: pass
      - kind: unit
        ref: "backend/tests/test_concept_seam.py#test_overview_api_as_of_partition"
        status: pass
    human_judgment: false
  - id: D3
    description: "rps_rotation._load_concept_map_df as_of (缓存绕过) + build_rps_rotation as_of 透传, join/agg 逻辑原样"
    requirement: CONCEPT-06
    verification:
      - kind: unit
        ref: "backend/tests/test_concept_seam.py#test_load_concept_map_df_as_of_branch"
        status: pass
      - kind: unit
        ref: "backend/tests/test_concept_seam.py#test_build_rps_rotation_as_of_passthrough"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /api/rps/rotation?as_of= 可选 Query + 双校验 (非法 → 400), GET-only"
    requirement: CONCEPT-06
    verification:
      - kind: unit
        ref: "backend/tests/test_concept_seam.py#test_rps_api_as_of_query"
        status: pass
      - kind: other
        ref: "grep -c as_of app/api/rps.py (8) / grep -c read_partition app/services/rps_rotation.py (1) / market_overview_builder.py (1)"
        status: pass
    human_judgment: false
  - id: D5
    description: "CONCEPT-07 复验: /api/pool/history?as_of=D 载荷 concept_effective_date/concept_captured_at 不回退; overview as_of 消费分区冒烟"
    requirement: CONCEPT-07
    verification:
      - kind: unit
        ref: "backend/tests/test_concept_seam.py#test_concept07_history_passthrough_verify"
        status: pass
    human_judgment: false

# Metrics
duration: 5min
completed: 2026-08-06
status: complete
---

# Phase 28 Plan 3: 概念板块 PIT 历史映射 — 共享 seam (CONCEPT-06/07) Summary

**把 28-01 的 `read_partition` as_of 原语扩展到总览 (_dimension_rank) 与 RPS 矩阵 (_load_concept_map_df), 消除「历史复盘/历史 RPS 仍用当前 ext join → 未标注 drift」缺口; 并为 GET /api/rps/rotation 增加可选 as_of 双校验参数**

## Performance

- **Duration:** 5 min
- **Started:** 2026-08-06T11:25:11Z
- **Completed:** 2026-08-06T11:30:10Z
- **Tasks:** 2 (T1 tracer + T2 auto, 均 tdd)
- **Files modified:** 4 (683 insertions / 15 deletions)

## Accomplishments
- `_dimension_rank(rows, repo, kind, limit=5, level=None, as_of=None)` as_of 分支: 函数体内**局部 import** `concept_history` (防循环铁律 — concept_history 模块级 import 了 `_dimension_field`); `kind==concept→gn_ths` / `industry→hy_ths`; 分区命中 → `part["rows"]` 替换 ext 行 (聚合逻辑 quote_map/groups/leading/lagging 原样), 分区缺失/rows 空 → `ext_rows=[]` 诚实降级 (T-28-03-03)。`as_of` 参数兼容 str 与 `date` (build_market_overview/market_recap 传 date → `.isoformat()` 归一, read_partition 需 str)。
- `build_market_overview` :503-504 接线: `explicit_as_of` 时 `_dimension_rank(..., as_of=...)`; as_of=None → 参数 None → 行为与现状逐位一致 (既有 overview/rps 消费方零改动)。
- `_load_concept_map_df(repo, as_of=None)` as_of 分支: 新 helper `_load_concept_map_from_partition` 读 D 日 gn_ths 分区展开 `(_sym_up, concept)` pairs + `pl.DataFrame(...).unique()`; **绕过/复键 600s 模块级缓存** (绝不写 `_concept_map_cache`, 历史日绝不拿最新日 map — T-28-03-02); config 缺失 → 退化用行内 symbol/code/股票代码 键。
- `build_rps_rotation(repo, days=12, as_of=None)`: as_of 非空 → 绕过结果缓存 (`_cache`, latest-key 冲突), 空 map → 空矩阵; 提取 `_build_rotation_full(repo, latest, days, map_df, concept_count)` 复用 join/agg/grouped/columns 段 (两分支各一次, 零复制)。
- `GET /api/rps/rotation?as_of=`: `_AS_OF_RE.fullmatch` + `date.fromisoformat` 双校验 (镜像 api/pool.py:99-107) → 非法 400; 透传 `build_rps_rotation(repo, days, as_of=as_of)`; **GET-only**。
- CONCEPT-07 复验: `/api/pool/history?as_of=D` 载荷 concept_effective_date/concept_captured_at 透传不回退 (28-01 契约), overview as_of 冒烟由分区驱动。

## Task Commits

每个任务原子提交 (T1 为 tracer 垂直切片, T2 为 RPS 侧):

1. **Task 1 (tracer): CONCEPT-06 总览 seam (_dimension_rank as_of + build_market_overview 接线)** - `c3bece0` (feat)
2. **Task 2 (auto): CONCEPT-06 RPS seam (_load_concept_map_df as_of + build_rps_rotation 透传 + api as_of) + CONCEPT-07 复验** - `108ba7d` (feat)

**Plan metadata:** (final docs commit, separate)

## Files Created/Modified
- `backend/app/services/market_overview_builder.py` - `_dimension_rank` as_of 分支 (局部 import + kind→gn_ths/hy_ths + 诚实降级); `build_market_overview` :503-504 接线
- `backend/app/services/rps_rotation.py` - `_load_concept_map_df` as_of 分支 + `_load_concept_map_from_partition` helper; `build_rps_rotation` as_of 透传 + `_build_rotation_full` helper
- `backend/app/api/rps.py` - `as_of` Query + 双校验 (400), GET-only
- `backend/tests/test_concept_seam.py` (new) - CONCEPT-06 seam 8 用例 (T1 4 + T2 4)

## Decisions Made
- as_of 参数在 `_dimension_rank` 内归一 `date.isoformat()` — 因为 `build_market_overview`/`market_recap` 的 as_of 是 `date`, 而 `read_partition` 需要 str; 归一放在 seam 边界最内聚。
- `_build_rotation_full` helper 无 as_of 参数, 只收 `map_df + latest` — 让最新与 as_of 两分支共享同一段 join/agg/grouped 逻辑, 符合「as_of 仅指概念映射来源」语义。
- as_of 分支空 map → 空矩阵返回, 绝不 fallback 当前 ext (诚实标注来源, RESEARCH §3.4)。
- `_write_partition_fixture` 泛化为接受 `kind` (test_concept_history 版本硬编码 gn_ths), 供 hy_ths seam 用例使用。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_dimension_rank` call-site 行号 (PLAN-CHECK W-2 应用)**
- **Found during:** Task 1
- **Issue:** 计划原文写 :505-506, PLAN-CHECK 实测实际在 :503 (concept) / :504 (industry)。
- **Fix:** 按 live 文件 :503-504 定位编辑 (未改其余部分)。
- **Files modified:** backend/app/services/market_overview_builder.py
- **Verification:** 全量 seam 测试绿。
- **Committed in:** c3bece0

**2. [Rule 2 - Missing Correctness] as_of date→str 归一 (计划接线文本的隐性前提)**
- **Found during:** Task 1 实现/测试
- **Issue:** 计划 action 字面接线 `_dimension_rank(..., as_of=as_of if explicit_as_of else None)` 会把 `build_market_overview` 的 `date` 对象传给 `as_of: str` 参数; `concept_history.read_partition` 用 `_DATE_RE.fullmatch` (需 str), date 会静默返回 None → seam 失效。
- **Fix:** `_dimension_rank` as_of 分支内 `as_of_str = as_of if isinstance(as_of, str) else as_of.isoformat()`; `_load_concept_map_from_partition` 同样归一。保持计划字面接线不变, 归一在 seam 边界。
- **Files modified:** backend/app/services/market_overview_builder.py, backend/app/services/rps_rotation.py
- **Verification:** `build_market_overview(repo, as_of=date(2026,8,4))` 与 `GET /api/overview/market?as_of=2026-08-04` (FastAPI 解析为 date) 均命中分区聚合。
- **Committed in:** c3bece0 / 108ba7d

**3. [Rule 2 - Missing Test Support] `_write_partition_fixture` 泛化 kind**
- **Found during:** Task 1 Test 2 (industry→hy_ths)
- **Issue:** 计划「复用 28-01 _write_partition_fixture」但该 fixture 硬编码 gn_ths 目录; seam 需 hy_ths 分区写读。
- **Fix:** 在 test_concept_seam.py 自建泛化 `_write_partition_fixture(data_dir, kind, as_of, field, rows)` (镜像形, 不跨模块 import — PLAN-CHECK N-3)。
- **Files modified:** backend/tests/test_concept_seam.py
- **Verification:** hy_ths as_of 聚合用例绿。
- **Committed in:** c3bece0

---

**Total deviations:** 3 auto-fixed (2 Rule 1, 1 Rule 2; 1 为 PLAN-CHECK 警告应用)
**Impact on plan:** All auto-fixes are correctness/consistency requirements; no scope creep, no architectural change (Rule 4 not triggered).

## Issues Encountered
- TDD RED 阶段确认: T2 测试先红 (`TypeError: _load_concept_map_df() got an unexpected keyword argument 'as_of'`), 实现后全绿 (8 passed)。
- 无阻塞性问题; 无包安装; 零新增依赖 (polars 既有锁定栈)。
- 与 28-02 (前端) 无文件重叠; `frontend/src/pages/Watchlist.tsx` 未被本计划触碰。

## User Setup Required

None - 零新增依赖, 零外部配置.

## Next Phase Readiness
- 三个消费方 (pool_hub / _dimension_rank / _load_concept_map_df) 现在共享同一 `read_partition` as_of seam。
- `market_recap` 历史复盘 (`build_market_overview(..., as_of=date)`) 概念板块/行业排名由 D 日分区聚合 — 未标注 drift 缺口关闭。
- RPS 历史矩阵 (`/api/rps/rotation?as_of=`) 概念列与 D 日分区一致, 600s/120s 缓存零污染。

---
*Phase: 28-concept-pit*
*Completed: 2026-08-06*

## Self-Check: PASSED
- Files: `backend/app/services/market_overview_builder.py`, `backend/app/services/rps_rotation.py`, `backend/app/api/rps.py`, `backend/tests/test_concept_seam.py` all exist/modified.
- Commits: `c3bece0`, `108ba7d` present in `git log`.
- Test result: `75 passed` — test_concept_seam (8) + test_pool_hub + test_guest_masking + test_concept_history (回归全绿, POOL-03 守卫不破)。
