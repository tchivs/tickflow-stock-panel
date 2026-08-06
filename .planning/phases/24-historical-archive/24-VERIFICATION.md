---
phase: 24-historical-archive
verified: 2026-08-06T04:15:00Z
status: passed
score: 11/11 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 24: 逐日全量存档 (Historical Archive) Verification Report

**Phase Goal:** Operator can backfill the historical pool archive in one bounded, cancelable, provenance-honest pass — `screener_results/date={as_of}/` snapshots replayed from `run_all_with_hits` without ever touching the `strategy_cache.json` single-as_of pointer; gaps and progress are visible; the manual historical-`run_all` pointer-pollution path is fixed.
**Verified:** 2026-08-06
**Status:** passed
**Re-verification:** No — initial verification

## 结论 (verdict)

**verdict: passed** — **must-haves 11/11 全部 VERIFIED**,0 blockers,0 human items。

目标方向核验(goal-backward):Phase 24 承诺的是「运营可一键触发有界、可取消、provenance 诚实的批量回填,逐历史日重放 `run_all_with_hits` 落快照,绝不触碰 `strategy_cache.json` single-as_of 指针;缺口与进度可见;手动历史 `run_all` 指针污染已修复」。以下证据链逐条对照真实代码(非 SUMMARY 声称)确认全部达成:

| 验证维度 | 证据形态 | 结果 |
|---------|---------|------|
| 代码存在性(Level 1) | 4 个源码改动文件 + 1 个新服务文件全部存在 | ✓ |
| 实质性(Level 2) | 关键函数体实读,非 stub(origin 校验/逐日重放/闸门/D6) | ✓ |
| 接线(Level 3) | 端点→服务→快照湖→读侧透传链路 import/调用完整 | ✓ |
| 数据流(Level 4) | 缺口源(list_backfill_gaps)→dates 端点→history 投影 全链真实数据 | ✓ |
| 行为(行为依赖 truth) | 11 项行为断言各有独立命名测试且实测全绿(83 passed) | ✓ |
| 文档对账 | features.md 计数 1 处不漂移 + date-nav 小节完备 | ✓ |
| Git 审计 | 提交链 9 笔存在;`Watchlist.tsx` 零触碰 | ✓ |

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | HIST-01 触发端点: `POST /api/pipeline/backfill` 在 `api/pipeline.py`(绝不在 `/api/pool/*`),operator-only,guest 401 | ✓ VERIFIED | `api/pipeline.py:100-183` `@router.post("/backfill")`;`api/pool.py` 全 GET(grep 仅 `@router.get`);`main.py:778-788,838-840` `_is_guest_readable` 仅放行 GET whitelist,POST 非游客面 → 401 结构性保证;`test_backfill_endpoint_*` 3 例实测绿 |
| 2 | HIST-01 回填服务语义: 逐历史 as_of 重放 `run_all_with_hits` → `persist_point_snapshot(origin="backfill")` 到 `screener_results/date={as_of}/`;缺口集=`list_backfill_gaps`;升序;限界(max_days/start/end);进度回调;合作式取消;失败日记录继续 | ✓ VERIFIED | `pool_backfill.py:34-123` `run_pool_backfill` 全文实读;`test_pool_backfill_replays_gaps_ascending`(升序序列断言 + origin=backfill)、`test_pool_backfill_bounds`、`test_pool_backfill_cooperative_cancel`(前 2 日跑、第 3 日起 failed 即停)、`test_pool_backfill_failed_days_continue`(failed_dates=[08-02] 其余继续)、`test_pool_backfill_idempotent_skips_existing_snapshots` 全部实测绿 |
| 3 | HIST-01 D2 铁律: 回填路径**绝不写 strategy_cache**(结构性不 import + byte-identical 断言) | ✓ VERIFIED | `pool_backfill.py` 模块 import 面仅 stdlib + pool_snapshot/pipeline_jobs/screener,无 strategy_cache、无执行族;import 面核对 + `test_backfill_never_touches_strategy_cache` byte-identical 断言(含「不存在则不创建」)实测绿 |
| 4 | HIST-01 调度: `job_store.create()` 单飞 + `try_acquire_run_slot()` 执行槽互斥 + `run_in_executor(_long_task_executor)` 请求内零阻塞;参数 400 校验(防路径穿越/无界) | ✓ VERIFIED | `api/pipeline.py:110-183`(reap_stale/create 单飞、try_acquire_run_slot、executor、create_task);`test_backfill_endpoint_singleflight_and_reuse`(二次触发 reused)、`test_backfill_endpoint_parameter_validation`(9 组非法参数全 400)、`test_backfill_endpoint_runs_in_executor_and_succeeds`(线程 ID 非主线程 + job_store.succeed 被调)实测绿 |
| 5 | HIST-02 写侧 provenance: `persist_point_snapshot(origin: str = "eod")` 校验 origin ∈ {eod, backfill, manual};payload 写 `snapshot_origin`;`_SCHEMA_VERSION=1`;旧快照缺字段读 eod | ✓ VERIFIED | `pool_snapshot.py:50-97`(签名 `origin="eod"`、非法 origin ValueError、payload 含 `"snapshot_origin"`、`_SCHEMA_VERSION=1`);`test_snapshot_origin_explicit_and_default`、`test_snapshot_origin_tolerance_old_payload`、`test_snapshot_roundtrip_no_ever_rows`(精确键集含 snapshot_origin,无 union 键)实测绿 |
| 6 | HIST-02 读侧透传: `build_pool_hub_snapshot` 投影响应透传 snapshot_origin(present 快照 `.get(...,"eod")` 旧快照缺省;空态 None);EOD job 落盘快照 `snapshot_origin=="eod"` | ✓ VERIFIED | `pool_hub.py:253,265`(空态 `"snapshot_origin": None`、present `snap.get("snapshot_origin", "eod")`);`test_pool_history_snapshot_origin_passthrough`(backfill 透传)、`test_pool_history_snapshot_origin_default_eod`(旧快照→eod 不 KeyError)、`test_pool_history_missing_available_false`(空态 None)、`test_pool_eod_job.py:136`(EOD `snapshot_origin=="eod"`)实测绿 |
| 7 | HIST-03 缺口信号: `GET /api/pool/dates` 响应增 `backfill_needed`(缺口计数)+ `backfill_examples`(升序前 5 缺口日),数据源=`list_backfill_gaps` 单点;`test_pool_dates_api` 精确断言同步;GET-only 零执行 | ✓ VERIFIED | `api/pool.py:55-75`(`gaps = list_backfill_gaps(data_dir)`;返回 `backfill_needed`/`backfill_examples: gaps[:5]`;仅 `@router.get`);`test_pool_dates_api`(精确 dict 含 `backfill_needed:2, backfill_examples:["2026-07-29","2026-08-02"]` + 空态 0/[])、`test_pool_dates_backfill_examples_truncated`(缺口>5 → 截断 5)、`test_pool_dates_backfill_needed_zero_when_all_covered`(回填完成归零)实测绿 |
| 8 | HIST-04 D6 修复: `api/screener.py` `run_all` 仅当 `as_of == svc.latest_date()` 才 `strategy_cache.write_cache`;快照**总是**落盘,`origin = "eod" if is_latest else "backfill"` | ✓ VERIFIED | `api/screener.py:443-463`(try `latest=svc.latest_date(); is_latest=...`;`if is_latest:` 包 write_cache;persist 无条件 `origin="eod" if is_latest else "backfill"`);`test_run_all_historical_asof_skips_cache_write`(历史 as_of → cache byte-identical + 快照 origin=backfill;最新日 → cache 写入 + origin=eod)实测绿;D6 source guard `test_screener_run_all_cache_write_is_latest_gated`(作用域 `def run_all` 段内 `is_latest`/`latest_date` 先于 `strategy_cache.write_cache`)实测绿 |
| 9 | HIST-04 POOL-03 守卫不破: E1(无执行族 import)/E2(只写 screener_results)/E3(不 import strategy_cache)/E4(GET-only)/E5(无计算触发)/E6(响应无执行词汇)全绿;零新增运行时依赖 | ✓ VERIFIED | `test_pool_hub.py` 守卫段 6 例全在 62 例回归套件中实测绿;`pool_snapshot.py`/`pool_backfill.py`/`api/pipeline.py` import 面实读确认无执行族、无 strategy_cache;`pool.py` grep 确认无 run_all/write_cache/persist_point_snapshot token;tech-stack `added: []` |
| 10 | docs 对账: `docs/features.md` 股池日期导航小节补回填/缺口信号/provenance;`27 个内置策略` 计数保持 1 处 | ✓ VERIFIED | `grep -c "27 个内置策略"` = 1;`grep -c "POST /api/pipeline/backfill"` = 1;`backfill_needed` = 1;`snapshot_origin` = 1;date-nav 小节(`features.md:26-30`)含 `POST /api/pipeline/backfill` 批量回填 + `/api/pipeline/jobs/{id}` 进度 + `backfill_needed` 缺口计数 + `snapshot_origin`(eod/backfill/旧快照按 eod 读) |
| 11 | git 审计: `frontend/src/pages/Watchlist.tsx`(用户预存)未被任何 phase-24 commit 触碰;提交链存在 | ✓ VERIFIED | `git log c5b3d4e..HEAD --oneline -- frontend/src/pages/Watchlist.tsx` 空输出;`git status --porcelain` 仅 `M frontend/src/pages/Watchlist.tsx`(预存未提交改动);9 笔 phase-24 提交存在(1df58d4/1eb764a/e17477b/30563cf/0a3d302/e7b6148/b84092d + 2 docs) |

**Score:** 11/11 truths verified (0 present, behavior-unverified)

## 逐需求证据 (HIST-01..04)

### HIST-01 — 批量回填 job

| Criterion | 代码/测试证据 | 结果 |
|-----------|--------------|------|
| 用户触发 `POST /api/pipeline/backfill`,放 `api/pipeline.py` 非 `/api/pool/*` | `api/pipeline.py:100` `@router.post("/backfill")`;`api/pool.py` 无 POST(E4 守卫实测绿) | ✓ |
| 逐历史 as_of 重放 `run_all_with_hits` → 冻结快照 | `pool_backfill.py:87-94` `svc.run_all_with_hits(date.fromisoformat(ds), engine=engine)` → `persist_point_snapshot(..., origin="backfill")` | ✓ |
| **绝不写 `strategy_cache.json`**(single-as_of 指针不污染) | `pool_backfill.py` 模块 import 面无 strategy_cache;`test_backfill_never_touches_strategy_cache` byte-identical + 不创建断言实测绿 | ✓ |
| 可取消(合作式)、可限界(最近 N / 日期区间)、升序摊销 warmup | `pool_backfill.py:61-68`(start/end/max_days)、`:76-79`(job failed → break);`test_pool_backfill_cooperative_cancel`/`bounds`/`replays_gaps_ascending` 实测绿 | ✓ |
| 失败日记录并继续,终态如实反映部分失败 | `pool_backfill.py:96-102`(except → failed_dates.append + continue);`test_pool_backfill_failed_days_continue` 实测绿 | ✓ |
| guest 401(operator-only) | `main.py:786-788` `_is_guest_readable` 仅 GET whitelist;`POST /api/pipeline/backfill` 非 GET → 结构性 401;`test_guest_cannot_read_authed_surfaces` 验证 401 机制 | ✓ |

### HIST-02 — snapshot_origin provenance

| Criterion | 代码/测试证据 | 结果 |
|-----------|--------------|------|
| `persist_point_snapshot` 增 `origin` 参数(默认 eod,校验 {eod,backfill,manual}),payload 写 `snapshot_origin` | `pool_snapshot.py:50-97` 全文实读 | ✓ |
| `_SCHEMA_VERSION` 保持 1 | `pool_snapshot.py:40` `_SCHEMA_VERSION = 1`;`test_snapshot_roundtrip_no_ever_rows` 断言 `schema_version == 1` | ✓ |
| 旧快照缺字段读为 eod(向后兼容,不 KeyError) | `pool_snapshot.py` 读侧原样返回 dict;`test_snapshot_origin_tolerance_old_payload` + `test_pool_history_snapshot_origin_default_eod` 实测绿 | ✓ |
| 读侧透传:present 快照透传/空态 None | `pool_hub.py:253,265`;`test_pool_history_snapshot_origin_passthrough`/`missing_available_false` 实测绿 | ✓ |
| EOD 快照 origin=eod | `test_pool_eod_job.py:136` `assert snap["snapshot_origin"] == "eod"` 实测绿 | ✓ |

### HIST-03 — 存档完整性可见

| Criterion | 代码/测试证据 | 结果 |
|-----------|--------------|------|
| `GET /api/pool/dates` 增 `backfill_needed` + `backfill_examples`(升序前 5) | `api/pool.py:68-74`;数据源 `list_backfill_gaps`(24-01 单点) | ✓ |
| 精确断言同步(非守卫破坏) | `test_pool_dates_api` 精确 dict 断言(含新键 + 空态 0/[])实测绿 | ✓ |
| GET-only 零执行(E4/E5 守卫不破) | `test_pool_api_is_get_only`/`test_pool_api_no_compute_trigger` 实测绿 | ✓ |
| 缺口归零(回填完成态)+ 示例截断 | `test_pool_dates_backfill_needed_zero_when_all_covered`/`test_pool_dates_backfill_examples_truncated` 实测绿 | ✓ |
| 回填进度可观察(非静默) | 端点经 `job_store.succeed(job_id, result)` + 既有 `GET /api/pipeline/jobs/{id}` 轮询;`test_backfill_endpoint_runs_in_executor_and_succeeds` 断言 result 传播 | ✓ |

### HIST-04 — 平台护栏 + D6 修复

| Criterion | 代码/测试证据 | 结果 |
|-----------|--------------|------|
| POOL-03 零执行权:触发端点不在 pool 面 | `api/pipeline.py` POST;`api/pool.py` GET-only(E4 实测绿) | ✓ |
| 无请求内阻塞回放 | `run_in_executor(_long_task_executor)` + `asyncio.create_task`;`test_backfill_endpoint_runs_in_executor_and_succeeds` 断言非主线程执行 | ✓ |
| 手动 `run_all` 历史 as_of 不再写 cache 指针(D6 修复) | `api/screener.py:443-463` `if is_latest:` 闸门;`test_run_all_historical_asof_skips_cache_write` byte-identical 实测绿 | ✓ |
| D6 修复被 source guard 锁死 | `test_screener_run_all_cache_write_is_latest_gated`(作用域限定 `def run_all` 段,避开 `_update_single_strategy_cache`)实测绿 | ✓ |
| 守卫 E1-E6 全绿 | 62 例回归套件全绿(含 6 守卫测试) | ✓ |
| 零新增运行时依赖 | tech-stack `added: []`;两计划 import 面实读全为既有锁定栈 | ✓ |

## Blockers

**0** — 无 must-have FAILED,无 artifact MISSING/STUB,无 key link NOT_WIRED,无 debt marker(TBD/FIXME/XXX)在改动文件中。

## Human Items

**0** — 本阶段交付为后端 API/服务 + hermetic 测试 + 文档,无 UI 渲染/外部服务/真实时延需人工测试的行为。前端缺口横幅/触发按钮属 I-8 明确 defer 至 Phase 25/27(本期只交付 API 契约);真实 247 日回填执行属运营操作,按 24-VALIDATION §8b 设计即不跑真实全量(TestClient + mock job_store 断言),所有行为契约(升序/限界/取消/失败继续/byte-identical/D6/origin 三态)均有独立命名测试实测绿,不构成 human_needed。

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 24-01 套件(snapshot origin/缺口 helper/回填服务/端点/D6 回归) | `cd backend && .venv/bin/python -m pytest tests/test_pool_snapshot.py tests/test_pool_backfill.py -x -q` | 21 passed | ✓ PASS |
| 回归套件(EOD job/POOL-03 守卫 E1-E6/guest 面/factor hits) | `cd backend && .venv/bin/python -m pytest tests/test_pool_eod_job.py tests/test_pool_hub.py tests/test_guest_masking.py tests/test_factor_hits.py -x -q` | 62 passed | ✓ PASS |
| docs 计数不漂移 | `grep -c "27 个内置策略" docs/features.md` | 1 | ✓ PASS |
| docs date-nav 小节完备 | `grep -c "POST /api/pipeline/backfill"` = 1;`backfill_needed` = 1;`snapshot_origin` = 1 | 全部命中 | ✓ PASS |
| git 审计:watchlist 零触碰 | `git log c5b3d4e..HEAD -- frontend/src/pages/Watchlist.tsx` | 空输出 | ✓ PASS |

**合计 83 passed** 与任务基线 `test_pool_snapshot/backfill/hub/eod_job/guest_masking/factor_hits 83 passed` 完全吻合。

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
| ---- | ------- | -------- | ------ |
| — | 无(TBD/FIXME/XXX/placeholder/return null/硬编码空数据扫描零命中) | — | — |

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| HIST-01 | 24-01 | 批量回填 job:逐日重放/绝不写 cache/可取消/可限界/升序 | ✓ SATISFIED | `pool_backfill.py` + `api/pipeline.py` + `test_pool_backfill.py`(6 服务 + 3 端点用例) |
| HIST-02 | 24-01 + 24-02 | snapshot_origin provenance(写侧 + 读侧透传 + 缺省 eod) | ✓ SATISFIED | `pool_snapshot.py` + `pool_hub.py` + `test_pool_snapshot.py`/`test_pool_hub.py`/`test_pool_eod_job.py` |
| HIST-03 | 24-02 | backfill_needed 缺口信号 + 进度可见 | ✓ SATISFIED | `api/pool.py` + `test_pool_hub.py`(dates 精确断言/截断/归零) |
| HIST-04 | 24-01 + 24-02 | POOL-03 守卫 + D6 修复 + source guard | ✓ SATISFIED | `api/screener.py` + 守卫套件 E1-E6 + `test_screener_run_all_cache_write_is_latest_gated` |

无 orphaned requirements(REQUIREMENTS.md 映射 HIST-01..04 全部被两份 PLAN 认领并闭环)。

## 守卫审计

### POOL-03 守卫 E1-E6

| 守卫 | 内容 | 证据 | 结果 |
|------|------|------|------|
| E1 | pool_hub/pool/pool_snapshot 不 import 执行族模块 | `test_pool_hub_no_execution_imports` 实测绿;`pool_snapshot.py` import 面实读无执行族 | ✓ |
| E2 | pool_snapshot 只写 `_SNAPSHOT_ROOT`(screener_results) | `test_pool_snapshot_writes_only_screener_results` 实测绿;写路径 `data_dir / _SNAPSHOT_ROOT / f"date={as_of}"` | ✓ |
| E3 | pool_snapshot 不 import/reference strategy_cache | `test_pool_snapshot_never_writes_runtime_cache` 实测绿;import 面实读无 strategy_cache | ✓ |
| E4 | pool.py 只允许 GET 路由 | `test_pool_api_is_get_only` 实测绿;grep 确认 `api/pool.py` 仅 `@router.get` | ✓ |
| E5 | pool.py 不得出现 run_all/write_cache/persist_point_snapshot | `test_pool_api_no_compute_trigger` 实测绿;grep 确认零 token | ✓ |
| E6 | hub/history/dates 响应键无执行词汇 | `test_hub_response_has_no_execution_vocabulary` 实测绿;新键 backfill_needed/backfill_examples/snapshot_origin 均不冲突 | ✓ |

### 其他守卫

- **guest 面**:`main.py:778-783` `_GUEST_READ_GET_PATHS` 未扩宽(仍 4 个只读 GET);`POST /api/pipeline/backfill` 结构性 401;`test_guest_cannot_read_authed_surfaces` 实测绿。
- **watchlist 未触碰**:`git log c5b3d4e..HEAD -- frontend/src/pages/Watchlist.tsx` 空输出;`git status --porcelain` 仅 `M frontend/src/pages/Watchlist.tsx`(用户预存改动,phase-24 零接触)。
- **提交链存在**:9 笔 phase-24 提交(24-01: 1df58d4/1eb764a/e17477b;24-02: 30563cf/0a3d302/e7b6148/b84092d;docs: ce9759c/df56231),与 SUMMARY 记录的 commit 完全一致。

## Gaps Summary

无。Phase 24 目标已完整达成,全部 4 项 ROADMAP Success Criteria 与 11 项 must-have truths 均经真实代码/测试证据核验为 VERIFIED。

---

_Verified: 2026-08-06_
_Verifier: Claude (gsd-verifier / Verifier24)_
