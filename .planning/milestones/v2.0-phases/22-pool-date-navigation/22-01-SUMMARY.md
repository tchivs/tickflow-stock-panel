# 22-01 SUMMARY — 股池日期导航: 冻结式点快照 + 只读日期导航 (POOL-04/05)

**Phase:** 22-pool-date-navigation · **Plan:** 22-01 · **Wave:** 1
**Status:** ✅ COMPLETE — 4/4 tasks green, committed atomically
**Date:** 2026-08-05

## Objective

交付 POOL-04 (冻结式点快照服务) + POOL-05 (日期列表 / 独立只读 as_of 取池端点) 的全部后端与守卫: 新建 `services/pool_snapshot.py` 点快照持久化/读取/日期列表/策略指纹; 把 `pool_hub.build_pool_hub` 的投影循环抽为共享纯函数 `_project_hub` 并新增 `build_pool_hub_snapshot`; 在 `api/pool.py` 新增 GET-only `/pool/dates` + `/pool/history`; 把 `api/screener.py run_all` 核心抽为 `ScreenerService.run_all_with_hits` 并在 write_cache 之后追加 `persist_point_snapshot` 调用; 最后把 POOL-03 AST 守卫扩展覆盖新文件/新路由 (E1-E6)。

## Tasks Delivered

| Task | Deliverable | Commit |
|------|-------------|--------|
| 1 | `services/pool_snapshot.py` (NEW) — `persist_point_snapshot`/`load_point_snapshot`/`list_snapshot_dates`/`strategy_fingerprint` + `_json_default`/`_DATE_RE`; `tests/test_pool_snapshot.py` (NEW, 6 组) | `f33f6b7` |
| 2 | `services/pool_hub.py` — 抽 `_project_hub` 纯函数 (`total = result.get("total", len(rows))` 权威, `concept_attribution:"current_snapshot"`) + `build_pool_hub_snapshot` (缺失 → `available:false` 空态); build_pool_hub 行为不变; +3 测试 | `00279cf` |
| 3 | `api/pool.py` — `GET /pool/dates` + `GET /pool/history` (as_of 严格 regex + fromisoformat, None→200 空态, 非法→400, mode + mask_guest_hub); AST 守卫 E1-E6; +4 API 测试 +3 守卫测试 | `8daa116` |
| 4 | `services/screener.py` `run_all_with_hits` (共享核心) + `api/screener.py` run_all 改调 + write_cache 后 `persist_point_snapshot` 钩子; +2 测试 | `49f91f6` |

## Test Results (all green)

```
cd backend && .venv/bin/python -m pytest tests/test_pool_snapshot.py tests/test_pool_hub.py tests/test_factor_hits.py -q
→ 41 passed
```

| Suite | Count | Notes |
|-------|-------|-------|
| `tests/test_pool_snapshot.py` | 8 | Task 1 (roundtrip/原子/空策略/指纹/日期列表/as_of 校验) + Task 4 (run_all 落快照 + 共享核心形状) |
| `tests/test_pool_hub.py` | 27 | 17 既有 (Task 2 零修改通过) + 3 Task 2 快照投影 + 4 Task 3 API + 3 新守卫 (E2/E3/E5) |
| `tests/test_factor_hits.py` | 6 | `test_run_all_rows_carry_hit_factors` 原样通过 (run_all 输出形状回归) |

## Contract Compliance

- **POOL-04 铁律**: 快照 payload 只含 `as_of/computed_at/strategy_version/snapshot_type:"point"/schema_version:1/results`, 结构上无 `today_ever_rows`/`today_ever_matched`; 原子写 temp+`os.replace`, 同 as_of 幂等, 无 .tmp 残留; total=0 空策略保留。
- **POOL-05**: `/api/pool/dates` source of truth = `screener_results/date=*` glob (含 part.json); `/api/pool/history?as_of=` 快照缺失 → 200 `available:false` 空态 (非 404), 非法 as_of → 400 (regex + fromisoformat 双重校验防路径穿越)。
- **single-as_of 契约**: `build_pool_hub` 签名/行为零改动 (空缓存早退 + 反漂移回显保留); 17 个既有 test_pool_hub 测试在 Task 2 零修改通过。
- **诚实标注**: 投影输出带 `concept_attribution:"current_snapshot"` (概念实时 join 当前 ext, 不冻结历史标签)。
- **POOL-03 守卫 E1-E6**: 投影文件 (pool_hub.py/pool.py) 无写断言保持严格; pool_snapshot.py 只写 `screener_results` (E2)、不 import/reference `strategy_cache.json`/`write_cache` (E3); pool.py 全 GET (E4)、禁 run_all/run_preset/write_cache/persist_point_snapshot (E5); 响应词汇扩展到 history+dates (E6)。
- **零新增运行时依赖**: 全部 stdlib (json/os/hashlib/re/pathlib/datetime) + 既有锁定栈。

## Deviations

1. **E4 guard assertion shape** (`test_pool_api_is_get_only`): 原 `methods == ["get"]` 在新增 /dates+/history 后出现 3 个 GET 装饰器而失败; 改为 `set(methods) == {"get"}` — 守卫语义 (仅 GET) 不变, 字面列表比较适配新路由数。计划原文 "不变" 指语义, 新路由全为 GET 天然通过。
2. **E3 guard wording** (`test_pool_snapshot_never_writes_runtime_cache`): 从全文件禁止字符串 `strategy_cache` 放宽为禁止 `strategy_cache.json`/`write_cache` (与计划文字一致) — pool_snapshot.py 的 docstring 按计划要求描述"与 strategy_cache 的 union 语义严格分离"时合法提及模块名, 无任何 import/调用。
3. **Task 1 invalid-as_of 测试用例**: `"2026-13-01"` (日历非法但 regex 格式合法) 从 persist 的 ValueError 列表移除 — persist 只做格式校验 (计划 Task 1 明示), 日历校验在 Task 3 API 层 `date.fromisoformat`; 该输入在 load 路径断言返回 None。
4. **Task 4 测试早含于 Task 1 文件**: test_pool_snapshot.py 创建时即含 2 个 Task 4 测试 (run_all 相关), Task 1 提交验证用 `-k "not run_all"` 排除; Task 4 落地后全绿。
5. **`_strategy_display_name` 本地副本**: services/screener.py 新增同名模块级 helper (逻辑与 api/screener.py 版本逐行一致) — 避免 service 层 import api 层造成的循环依赖; 路由层的 `_strategy_display_name` 保留供 api/pool.py 导入。

## watchlist_touched

`false` — `frontend/src/pages/Watchlist.tsx` 未被 stage/commit (用户未提交改动保留在工作树; 4 个提交均未包含该文件)。

## Pre-existing / Parallel State (not owned by 22-01)

- `backend/app/jobs/daily_pipeline.py` (M) + `backend/tests/test_pool_eod_job.py` (untracked): Executor2202 (22-02) 并行改动, 未触碰。
- `.planning/phases/22-pool-date-navigation/PLAN-CHECK-22.md` (D): 规划流程产物, 未触碰。
