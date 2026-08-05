---
phase: 22-pool-date-navigation
verified: 2026-08-05T10:49:38Z
status: passed
score: 10/10 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 22: 股池日期导航 (Pool Hub Date Navigation) Verification Report

**Phase Goal:** 用户可以按交易日浏览历史股池——每次 `run_all` 的行集以冻结式点快照（`as_of` + `computed_at` + 策略版本指纹）持久化到 `screener_results/date={as_of}/`，经独立只读端点列出日期与按 as_of 取池，并由盘后 EOD job 预生成保证自给自足；绝不落 `today_ever_rows` union，也不破坏既有 single-as_of 契约。
**Verified:** 2026-08-05T10:49:38Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 — 冻结式点快照：`run_all` 行集携 `as_of`/`computed_at`/`strategy_version`/`snapshot_type:"point"`/`schema_version:1` 落 `screener_results/date={as_of}/part.json`（temp + os.replace 原子写）；`today_ever_rows`/`today_ever_matched` union 永不作为点快照持久化；total=0 空策略保留；同 as_of 幂等无 .tmp 残留 | ✓ VERIFIED | `pool_snapshot.persist_point_snapshot` payload 仅含 6 键（`services/pool_snapshot.py:70-91`）；`test_snapshot_roundtrip_no_ever_rows`（精确键集 + 无 union 键 + round-trip）+ `test_snapshot_atomic_and_idempotent`（无 .tmp + 幂等覆盖）+ `test_snapshot_preserves_empty_strategy` + `test_run_all_persists_point_snapshot`（API 路径落盘含 point/指纹/无 union 键）全绿 |
| 2 | SC2 — `GET /api/pool/dates` 列出可用日期（ISO desc、source of truth = `screener_results/date=*` 含 part.json 分区 glob）；`GET /api/pool/history?as_of=` 独立只读取池（缺失 → 200 `available:false` 非 404；非法 as_of → 400 防路径穿越）；`GET /api/pool/hub` single-as_of 契约原样 | ✓ VERIFIED | `api/pool.py` `get_pool_dates`/`get_pool_history`（`_AS_OF_RE.fullmatch` + `date.fromisoformat` 双校验→400）；`build_pool_hub_snapshot` 缺失分支 `available:False`；`test_pool_dates_api` + `test_pool_history_snapshot` + `test_pool_history_missing_available_false`（200 非 404）+ `test_pool_history_rejects_bad_as_of`（含 `2026-13-01` 日历非法→400）全绿 |
| 3 | SC2 — single-as_of 契约不变：`build_pool_hub` 签名/行为零改动（空缓存早退 + 反漂移回显），17 个既有 test_pool_hub 零修改通过 | ✓ VERIFIED | `build_pool_hub` 保留 `resolved_as_of = as_of if (as_of and as_of == cache_as_of) else cache_as_of`（`pool_hub.py`）与空缓存 5 键早退；`test_build_pool_hub_echoes_cache_as_of_on_mismatch` + `test_get_pool_hub_mismatched_as_of_returns_cache_date` + `test_get_pool_hub_missing_cache_empty`（精确 dict 相等）通过 |
| 4 | SC3 — 盘后定时 `pool_eod_persist` job（mon-fri, Asia/Shanghai, 管道+5min 含跨小时进位, misfire_grace_time=3600, replace_existing, `_run_tracked` 单飞）；经 `run_all_with_hits` → `write_cache` → `persist_point_snapshot`；首个历史日请求只读快照、不触发请求内重算 | ✓ VERIFIED | `daily_pipeline.py` `_POOL_EOD_JOB_ID`/`_pool_eod_persist`/`start_scheduler` 注册（L961-989, L1075-1089）；`test_pool_eod_persist_writes_snapshot_and_cache`（落 point 快照无 union 键 + 缓存 as_of 刷新）+ `test_pool_eod_job_registered_in_scheduler`（grep 注册形锁死）+ `test_pool_history_snapshot`（只读快照路径无引擎计算）+ E5 守卫（pool.py 无 run_all/write_cache/persist_point_snapshot）证明无请求内重算路径 |
| 5 | SC3 — EOD job 诚实 skip：无数据日/无 app state → 不写任何文件 | ✓ VERIFIED | `_pool_eod_persist` 返回 `{"as_of": None, "skipped": "no data date"}` / `"no app state"`；`test_pool_eod_persist_skips_no_data_date` + `test_pool_eod_persist_skips_no_app_state` 全绿 |
| 6 | SC4 / 22-01 — POOL-03 守卫扩展 E1-E6：投影文件无写路径；pool_snapshot 只写 `screener_results`（常量感知）；不 import/reference strategy_cache；pool.py 全 GET；禁 run_all/write_cache/persist_point_snapshot；响应词汇扩展到 history+dates | ✓ VERIFIED | `test_pool_hub.py` 守卫：`test_pool_hub_no_execution_imports`（E1，3 元组解包同步）+ `test_pool_snapshot_writes_only_screener_results`（E2，AST 写函数须引用 `_SNAPSHOT_ROOT`）+ `test_pool_snapshot_never_writes_runtime_cache`（E3）+ `test_pool_api_is_get_only`（E4，`set(methods)=={"get"}`）+ `test_pool_api_no_compute_trigger`（E5）+ `test_hub_response_has_no_execution_vocabulary`（E6，history+dates 入 `_all_keys`）全绿 |
| 7 | SC4 / 22-02 — E7 游客白名单：`/api/pool/dates` + `/api/pool/history` 加入 `_GUEST_READ_GET_PATHS`（auth_middleware 路由前放行）+ guest 测试路径元组 + history mode 词汇/无 6 位代码泄露 | ✓ VERIFIED | `main.py:778-783` frozenset 含两新路径；`test_guest_cannot_read_authed_surfaces`（游客 GET 两新端点 200）+ `test_guest_read_paths_are_get_only`（非 GET 拒绝）+ `test_guest_mode_vocabulary_and_no_identity_leak`（history mode + 无 6 位代码）全绿 |
| 8 | POOL-04 调用点 1：`run_all` 核心抽 `ScreenerService.run_all_with_hits(as_of, strategy_ids, engine)`（路由与 EOD 共用）；write_cache 之后落点快照；输出形状不变（hit_factors/total/as_of 回归） | ✓ VERIFIED | `services/screener.py:723` `run_all_with_hits`（PRESET+engine 策略收集、history 惰性加载、hit_factors 聚合、空列表→`{}`）；`api/screener.py:437` 路由改调共享核心 + L448-458 persist 钩子；`test_run_all_rows_carry_hit_factors` 原样通过 + `test_run_all_with_hits_shared_core_shape` 全绿 |
| 9 | OQ-1 DECISION：本期不做首日一次性全量历史回填；EOD 只向前生成，历史缺口由手动 run_all 补齐 | ✓ VERIFIED | `daily_pipeline.py` 无 backfill/回填 job（grep 零命中）；22-02 计划明示 OQ-1 决策；无任何一次性回填调度注册 |
| 10 | 零新增外部运行时依赖；docs 对账：`features.md` 股池日期导航小节 + "27 个内置策略" 计数 1 处不漂移 | ✓ VERIFIED | `pool_snapshot.py` 仅 stdlib import（hashlib/json/os/re/datetime/pathlib/typing）；`pyproject.toml` 零改动（git status 无记录）；`grep -c "27 个内置策略" docs/features.md` = 1；`grep -c "股池日期导航" docs/features.md` = 1（小节 L26-28 提及冻结快照/日期列表/as_of 取池/EOD 预生成/空态/current_snapshot） |

**Score:** 10/10 truths verified (0 present-but-behavior-unverified, 0 overrides)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | --------- | ------ | ------- |
| `backend/app/services/pool_snapshot.py` (new) | persist_point_snapshot / load_point_snapshot / list_snapshot_dates / strategy_fingerprint + `_json_default`/`_DATE_RE`/`_SNAPSHOT_ROOT` | ✓ VERIFIED | 全形；原子写 temp+os.replace；payload 无 union 键；`_DATE_RE` 严格校验；fingerprint = meta+源码 sha256[:16] |
| `backend/app/services/pool_hub.py` (modified) | `_project_hub` 共享纯函数 + `build_pool_hub_snapshot`；build_pool_hub 行为不变 | ✓ VERIFIED | `total = result.get("total", len(rows))` 权威；`concept_attribution:"current_snapshot"`；缺失 → `available:false` 空态；`updated_at` = 快照 `computed_at` |
| `backend/app/api/pool.py` (modified) | GET-only `/dates` + `/history`（as_of 双校验 + mode + mask_guest_hub） | ✓ VERIFIED | 仅 `@router.get`×3；无计算/写触发；/hub 未改动 |
| `backend/app/services/screener.py` (modified) | `run_all_with_hits` 共享核心 + `_json_safe` | ✓ VERIFIED | 签名 `(as_of, strategy_ids=None, engine=None)`；输出与路由同形含 hit_factors |
| `backend/app/api/screener.py` (modified) | run_all 改调共享核心 + write_cache 后 persist_point_snapshot 钩子 | ✓ VERIFIED | L437 共享核心 + L448-458 钩子；日期解析/早退/ext 包装保留 |
| `backend/app/jobs/daily_pipeline.py` (modified) | `_pool_eod_persist` + `_POOL_EOD_JOB_ID` + start_scheduler 注册 | ✓ VERIFIED | 单飞 + 无数据日 skip + 绝不 HTTP 自调；mon-fri cron +5min 跨小时进位 |
| `backend/app/main.py` (modified) | `_GUEST_READ_GET_PATHS` 加 `/api/pool/dates` + `/api/pool/history` | ✓ VERIFIED | frozenset L778-783 含两新路径；`_is_guest_readable` 读同一集合 |
| `backend/tests/test_pool_snapshot.py` (new) | 8 tests（round-trip/原子/空策略/指纹/日期列表/as_of 校验/run_all 落快照/共享核心） | ✓ VERIFIED | 8 tests 全绿（见行为表） |
| `backend/tests/test_pool_hub.py` (modified) | 17 既有 + 3 投影 + 4 API + 3 守卫 | ✓ VERIFIED | 27 tests 全绿 |
| `backend/tests/test_pool_eod_job.py` (new) | EOD 写快照+刷新缓存 / 无数据日 skip / 无 app state skip / 注册 gate | ✓ VERIFIED | 4 tests 全绿 |
| `backend/tests/test_guest_masking.py` (modified) | 白名单 E7（两路径元组 + history 词汇） | ✓ VERIFIED | 15 tests 全绿 |
| `docs/features.md` (modified) | 股池日期导航小节 + 计数 27 对账 | ✓ VERIFIED | L26-28 小节；"27 个内置策略" 恰 1 处 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `persist_point_snapshot` | `load_point_snapshot` | `screener_results/date={as_of}/part.json` temp + os.replace | WIRED | round-trip 精确；同 as_of 幂等覆盖（test_snapshot_roundtrip/atomic） |
| `_project_hub` | `build_pool_hub` / `build_pool_hub_snapshot` | 共享纯函数双路径 | WIRED | 历史/最新 bit-identical；total 权威；concept_attribution 标注 |
| `run_all` 路由 | `ScreenerService.run_all_with_hits` | `svc.run_all_with_hits(as_of, strategy_ids, engine)` (api/screener.py:437) | WIRED | 输出形状回归锁死（test_run_all_rows_carry_hit_factors 原样通过） |
| `run_all_with_hits` | `persist_point_snapshot` | write_cache 后钩子 (api/screener.py:448-458) | WIRED | API 路径落 point 快照（test_run_all_persists_point_snapshot） |
| `pool_eod_persist` job | `run_all_with_hits` → `write_cache` → `persist_point_snapshot` | 直调 service 核心，绝不 HTTP 自调 (daily_pipeline.py:995-1006) | WIRED | EOD 行为测试全绿；缓存 as_of 刷新到最新 |
| `/api/pool/history` | `build_pool_hub_snapshot` | GET-only 路由 (api/pool.py) | WIRED | 缺失→200 available:false；非法→400；有快照→hub 同形状 |
| `_GUEST_READ_GET_PATHS` | auth_middleware | `_is_guest_readable(path, method)` (main.py:786-788, 838-840) | WIRED | 游客 GET 两新端点 200；非 GET 拒绝 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| 快照 `results` | `run_all_with_hits` 输出 | `_load_enriched_for_date(as_of)` → 逐策略 run/run_preset → `{sid:{total,as_of,rows}}` + hit_factors | ✓ 真实 enriched 行集 + 服务端因子聚合（非静态/非硬编码）；EOD 与手动 run_all 同路径 | ✓ FLOWING |
| `GET /api/pool/history` strategies | 快照 `results` → `_project_hub` | `load_point_snapshot` 读 `part.json`（冻结行集）→ total 权威 | ✓ 真实冻结快照数据；缺失 → 诚实空态 available:false | ✓ FLOWING |
| `GET /api/pool/dates` | `list_snapshot_dates` | `screener_results/date=*` 分区 glob（含 part.json） | ✓ 真实分区目录扫描；无快照目录排除；空态 `[]` | ✓ FLOWING |
| EOD 快照 | `_pool_eod_persist` | `latest_date()` → `run_all_with_hits` → `persist_point_snapshot` | ✓ 真实最新交易日数据；无数据日 skip 不写 | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 全部目标测试（5 文件） | `.venv/bin/python -m pytest tests/test_pool_snapshot.py tests/test_pool_hub.py tests/test_pool_eod_job.py tests/test_guest_masking.py tests/test_factor_hits.py -q` | `60 passed in 2.78s` | ✓ PASS |
| 快照铁律（无 union 键 / 原子 / 幂等） | test_snapshot_roundtrip_no_ever_rows + test_snapshot_atomic_and_idempotent | 2 passed | ✓ PASS |
| run_all 落快照（API 路径） | test_run_all_persists_point_snapshot | 1 passed | ✓ PASS |
| EOD job 写快照 + 刷新缓存 | test_pool_eod_persist_writes_snapshot_and_cache | 1 passed | ✓ PASS |
| 缺失快照 → 200 available:false | test_pool_history_missing_available_false + test_build_pool_hub_snapshot_missing_available_false | 2 passed | ✓ PASS |
| 非法 as_of → 400 | test_pool_history_rejects_bad_as_of（含 2026-13-01 日历非法） | 1 passed | ✓ PASS |
| single-as_of 回显回归 | test_build_pool_hub_echoes_cache_as_of_on_mismatch + test_get_pool_hub_mismatched_as_of_returns_cache_date | 2 passed | ✓ PASS |
| 守卫 E1-E6 + E7 白名单 | test_pool_hub.py 7 守卫 + test_guest_masking.py 3 白名单 | 10 passed | ✓ PASS |

### Probe Execution

N/A — Phase 22 无 probe 脚本（`find scripts -path '*/tests/probe-*.sh'` 无输出；22-VALIDATION.md 无 probe 声明）。自动化验证由 pytest 单测 + 源码 grep 门禁承担。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| POOL-04 | 22-01 | 冻结式点快照：as_of + computed_at + strategy-version fingerprint 落 `screener_results/date={as_of}/`，永不落 `today_ever_rows` union，绝不 backfill/appended | ✓ SATISFIED | pool_snapshot.py + test_snapshot_roundtrip_no_ever_rows + test_run_all_persists_point_snapshot + test_pool_eod_persist_writes_snapshot_and_cache |
| POOL-05 | 22-01 | `GET /api/pool/dates` + 独立只读 as_of 取池；`/api/pool/hub` single-as_of 契约原样 | ✓ SATISFIED | pool.py /dates+/history + test_pool_dates_api + test_pool_history_* + 17 回归零改动 |
| POOL-06 | 22-02 | 盘后定时 run_all job 自动持久化，历史浏览自给自足 | ✓ SATISFIED | daily_pipeline.py pool_eod_persist 注册 + test_pool_eod_persist_writes_snapshot_and_cache + test_pool_eod_job_registered_in_scheduler |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | 无 TBD/FIXME/XXX 债务标记（7 个 phase 源文件 grep 零命中） | — | — |
| — | — | 无 placeholder/coming soon/not yet implemented | — | — |
| — | — | 无空实现（return null/{}/[] / 空 handler） | — | — |
| — | — | 无硬编码空数据（快照/缓存/投影数据均来自真实加载路径） | — | — |

**Informational（非阻断，流程状态而非代码缺口）：**
1. `.planning/REQUIREMENTS.md` 中 POOL-04/05/06 仍标 `Open`（行 27-29、63-65）——代码已交付且测试全绿，属阶段完成后的书面对账步骤。
2. `.planning/ROADMAP.md` Phase 22 行 61 仍显示未勾选、Phase 状态表行 219 标 "Not started"——两计划均有 SUMMARY 与 10 个提交（`f33f6b7`/`00279cf`/`8daa116`/`49f91f6`/`dd0a2b2`/`76f12aa`/`0e68953`/`52bb546`/`28f9895`/`0359621`），为状态书面对账滞后。
3. EOD job 注册形用源码 grep 断言（`test_pool_eod_job_registered_in_scheduler`）而非启动真调度器——22-VALIDATION.md 与 22-02 计划明确设计的决策（"不启动真调度器"），非缺口；job 被触发时的行为由 `test_pool_eod_persist_writes_snapshot_and_cache` 直接测试。

### Human Verification Required

无。本阶段为后端纯代码阶段：
- 两 PLAN `backstops: []`（无 backstop 真相需人工裁决）；
- 无 `<verify><human-check>` 延后项；
- 全部 10 条 must-have 真相均有代码存在性 + 行为测试证据（原子写/幂等/空态/400 拒绝/无 union 键/EOD 落盘/单飞注册形均有通过的测试）；
- VALIDATION.md 唯一 manual-only 项（DateNavigator 前端渲染）明确归属 Phase 23 前端面（DTO 契约由 API 测试锁定：`/api/pool/dates` + `/api/pool/history` 形状 + `concept_attribution` 键），非 Phase 22 缺口。

### Gaps Summary

无阻断性缺口。10/10 must-have 真相在代码与测试中全部证实；60 项目标测试全绿；phase-plan-index 22 运行干净（exit 0，双计划 complete、wave 1、7 任务、无 checkpoint）；git status 仅 `M frontend/src/pages/Watchlist.tsx`（用户未提交改动，本阶段 10 个提交均未触碰）。硬边界逐一核实：快照 payload 无 union 键、原子写无 .tmp 残留、as_of 双校验防路径穿越、缺失快照 200 available:false（非 404）、EOD job 直调 service 核心绝不 HTTP 自调、OQ-1 无 backfill job、E1-E7 守卫全绿、游客白名单扩展、docs 计数 27 对账、零新增依赖。仅存的差异为 REQUIREMENTS/ROADMAP 状态标记滞后（见 Anti-Patterns informational），与目标达成无关，建议在阶段收尾书面对账时一并刷新。

---

_Verified: 2026-08-05T10:49:38Z_
_Verifier: Claude (gsd-verifier)_
