# Phase 24 计划检查 round 1 — 24-REVIEW.md

**Checked:** 2026-08-06
**Verifier:** gsd-plan-checker (Revision Gate, round 1)
**Plans verified:** `24-01-PLAN.md`（HIST-01/02/04 写侧 + D6）、`24-02-PLAN.md`（HIST-02 读侧 / HIST-03 / HIST-04 回归锁 + docs）
**Sources read:** 24-RESEARCH.md、24-PATTERNS.md、REQUIREMENTS.md、`backend/app/services/pool_snapshot.py`、`screener.py`、`strategy_cache.py`、`pipeline_jobs.py`、`pool_hub.py`、`extend_history.py`、`backend/app/api/pipeline.py`、`pool.py`、`screener.py`、`kline.py`、`data.py`、`backend/app/jobs/daily_pipeline.py`、`backend/app/main.py`、`backend/tests/test_pool_snapshot.py`、`test_pool_hub.py`、`test_pool_eod_job.py`、`test_guest_masking.py`、`docs/features.md`、`frontend/src/pages/PoolHubPage.tsx`、`frontend/src/lib/api.ts`、`.planning/config.json`
**Git state:** 分支 `gsd/v2.0-planning`；唯一未提交改动 = `frontend/src/pages/Watchlist.tsx`（用户预存，两计划零触碰）。✓

---

## 概要 Verdicts

| Plan | Verdict | Blockers | Warnings |
|------|---------|----------|----------|
| 24-01 | **EXECUTABLE** | 0 | 0 |
| 24-02 | **EXECUTABLE**（需在 Task 3 修订 2 处执行内缺陷） | 0 | 2（W-1, W-2） |

> 按 v2.0 Phase 22 先例（W-1/W-2/W-6 同属「守卫/verify 断言实现缺陷」但执行器可在本计划 `files_modified` 范围内修订 → 判 WARNING 而非 BLOCKER）。本回合无「执行器越出 files_modified 才能修复」的 scope 缺口，故无 B。

---

## 已验证通过的基础事实（源码/磁盘实测）

1. **测试命令约定** — `backend/.venv/bin/python` 存在；两份计划全部 `<verify><automated>` 均以 `cd backend && .venv/bin/python -m pytest tests/... -x -q` 开头，路径相对 `cd backend` 正确。✓
2. **文件零重叠** — 24-01 `files_modified`（6）∩ 24-02 `files_modified`（5）= ∅。✓
3. **依赖/波次** — 24-01 wave 1 / `depends_on: []`；24-02 wave 2 / `depends_on: ["24-01"]`（消费 `list_backfill_gaps` 与 `persist_point_snapshot(origin=...)`），无环、无前向引用。✓
4. **符号真实性（对照真实代码）** —
   - `pool_snapshot.persist_point_snapshot(data_dir, as_of, results, strategy_version, computed_at)`（`pool_snapshot.py:50`，payload L87-93，`_SCHEMA_VERSION=1` L33，`_DATE_RE` L30）✓ 计划增 `origin="eod"` 参数 + `snapshot_origin` 键与既有签名/payload 顺序兼容。
   - `load_point_snapshot`（L102-117，缺失→None）✓ 旧 payload 无字段读 eod 兼容（Pitfall 5）。
   - `list_snapshot_dates`（L120-133，ISO desc，含 part.json 过滤）✓ `list_backfill_gaps` 用 set 差值后升序，不受 desc 影响。
   - `ScreenerService.run_all_with_hits(as_of: date, strategy_ids=None, engine=None)`（`screener.py:723`，内部不写 cache）✓ `latest_date()`（`screener.py:704`）✓。
   - `job_store.create()` 单飞返回 `(job_id, is_new)`（`pipeline_jobs.py:99`）、`try_acquire_run_slot`/`release_run_slot`（`pipeline_jobs.py:314-316`）、`_long_task_executor`（`api/pipeline.py:16-17`）✓。
   - 端点模板 `extend_history`（`api/kline.py:634-700`：body 校验 + job_store.create 单飞 + try_acquire_run_slot + run_in_executor + asyncio.create_task）✓ 24-01 Task 3 逐行镜像。
   - 新增符号 `list_enriched_dates`/`list_backfill_gaps`/`run_pool_backfill` 在 24-01 Task 1/2 内定义一致，24-02 消费签名匹配（`list_backfill_gaps(data_dir)->list[str]` 升序）。✓
5. **POOL-03 守卫合规** —
   - E4（GET-only，`test_pool_hub.py:836`）：`POST /backfill` 放 `api/pipeline.py`，`api/pool.py` 零新增路由。✓
   - E3（`test_pool_hub.py:880`）：`pool_snapshot.py` 继续不 import/reference `strategy_cache`；`list_enriched_dates`/`list_backfill_gaps` 纯读，无写 pattern，不触发 E2 写路径检查。✓
   - E5（`test_pool_hub.py:891`）：`pool.py` 只新增 `from app.services.pool_snapshot import list_backfill_gaps`，token 集不含 `run_all/run_preset/write_cache/persist_point_snapshot`。✓
   - E6（`test_pool_hub.py:900-922`）：新增键 `backfill_needed/backfill_examples/snapshot_origin` 均不含 orders/execution/broker/deals。✓
   - `test_pool_dates_api`（`test_pool_hub.py:704-723`，精确相等断言）由 24-02 Task 2 显式同步为含新键的空态/非空态 dict。✓
6. **D6 修复路径正确性** — 24-01 Task 3 对 `api/screener.py run_all`（write_cache 调用点 `:445`、persist `:448-458`）：`is_latest = (svc.latest_date() == as_of)` 闸门包住 write_cache，persist 无条件且 `origin="eod" if is_latest else "backfill"`；EOD job（`daily_pipeline.py:998-1008`）不受影响（latest 日写 cache 正确）。✓
7. **诚实性** —
   - 回填路径 `run_pool_backfill` 结构上不 import/调 `write_cache`，byte-identical 测试锁死（24-01 Task 2 Test 2）。✓
   - `snapshot_origin` 缺省 `eod`、非法 origin ValueError、旧 payload 读 eod（24-01 Task 1 Test 1-3）。✓
   - `backfill_needed` 形态 = 缺口计数 + 升序前 5 示例，数据源与回填共用 `list_backfill_gaps` 单点（24-02 Task 2）。✓
8. **docs 对账** — `docs/features.md:11` 「27 个内置策略」当前恰 1 处，`docs/features.md:26` 「### 🗓️ 股池日期导航」1 处；24-02 Task 3 verify 用 `test "$(grep -c ...)" = "1"`（已修复 Phase 22 W-5 的弱断言）。✓
9. **前置门完整性** — 24-02 Task 1/2/3 的 `<precondition>` 相对 `cd backend` 路径全部正确（`app/services/pool_snapshot.py` / `app/api/screener.py`），import/grep gate 语义成立（W-1 仅影响 Task 3 的 grep 语义细节）。✓
10. **scope** — 24-01：3 tasks / 6 files；24-02：3 tasks / 5 files，均在阈值内。`estimate`（68000/48000 tokens，confidence=low）因 config 无 `workflow.smart_zone_tokens` 且本 gsd-tools 无 `estimate-check` 命令无法校准，仅作参考（见 I-7）。✓

---

## Blockers

无。

---

## Warnings

### W-1 — 24-02 Task 3 的 D6 source guard 断言在「已 D6 修复」代码上必然失败（`src.index` 首次出现语义撞上 `_update_single_strategy_cache` 的 write_cache）

- **计划:** 24-02, Task 3（新增 `test_screener_run_all_cache_write_is_latest_gated`）
- **证据:**
  - 计划动作原文：`assert src.index("latest_date") < src.index("write_cache")` 且 `assert src.index("is_latest") < src.index("write_cache")`（"若多写点, 取 `strategy_cache.write_cache` 首次出现位置"）。
  - `backend/app/api/screener.py` 中 `write_cache` 的**首次**出现是 `:210`（`_update_single_strategy_cache` 内的 `strategy_cache.write_cache(data_dir, as_of, results)`），**早于** `latest_date` 首次出现（`:253` `req.as_of or svc.latest_date()`）和 D6 修复引入的 `is_latest`（run_all 内 ~`:437`）。
  - 因此 D6 修复正确落地后：`src.index("latest_date") < src.index("write_cache")` → `L253 < L210` = **False**；`src.index("is_latest") < src.index("write_cache")` → `L437 < L210` = **False**。两个断言均失败 → `pytest tests/test_pool_hub.py -x -q`（Task 3 verify）红，Task 3 无法按计划完成。
  - 同一语义问题也污染 24-02 Task 3 的 `<precondition>`：「`write_cache` 出现于 `is_latest` 之后」在首次出现语义下为假。
- **为什么不是 B:** 守卫测试文件 `test_pool_hub.py` 在 24-02 `files_modified` 内，执行器可在执行内修订断言实现（Phase 22 先例 W-1/W-2 同类 → WARNING）。
- **修复建议:** 把断言作用域限定到 `run_all` 函数段，避免撞上 `_update_single_strategy_cache`：
  ```python
  run_all_src = src[src.index("def run_all"):]
  assert "if is_latest:" in run_all_src
  assert run_all_src.index("is_latest") < run_all_src.index("strategy_cache.write_cache")
  assert run_all_src.index("latest_date") < run_all_src.index("strategy_cache.write_cache")
  ```
  或等价地 `src.index("if is_latest:", src.index("def run_all")) < src.index("strategy_cache.write_cache", src.index("def run_all"))`。precondition 同步改为 `grep -n "if is_latest:" app/api/screener.py` 有命中且该行位于 `strategy_cache.write_cache`（run_all 内）之前。

### W-2 — 24-02 Task 3 的 docs verify 在 `cd backend` 后 grep `docs/features.md` 路径失效

- **计划:** 24-02, Task 3
- **证据:** `<automated>` 为 `cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py -x -q && test "$(grep -c "27 个内置策略" docs/features.md)" = "1" && grep -q "股池日期导航" docs/features.md && grep -q "backfill_needed" docs/features.md`。`cd backend` 后 CWD = `backend/`，`docs/features.md` 解析为 `backend/docs/features.md`（不存在）→ `grep -c` 输出空 → `test "" = "1"` 失败 → 即使 docs 正确更新，verify 仍红。
- **为什么不是 B:** 同为执行内可修的 verify 路径缺陷（Phase 22 W-6 同类 → WARNING）。
- **修复建议:** 三选一：(a) docs 检查放到 `cd backend` 之前；(b) 改用 `../docs/features.md`；(c) 把 `cd backend &&` 拆成 pytest 用 `cd backend`、docs 用仓库根相对路径（或 `/home/orca/source/AthenaQuant/docs/features.md`）。

---

## Infos

- **I-1（Nyquist 8e）:** 阶段目录下无 `*-VALIDATION.md`（`ls .planning/phases/24-historical-archive/` 仅 PLAN×2 + RESEARCH + PATTERNS）。RESEARCH 已含 "Validation Architecture" 节且 `config.json workflow.nyquist_validation=true`。按 Phase 22 先例：round 1 不阻塞，但 orchestrator 需在进入 execute 前生成 `24-VALIDATION.md`。8a-8d 检查均 PASS（6/6 任务全含 `<automated>`、无 MISSING、无 E2E/watch、采样连续）。
- **I-2（行号漂移）:** 24-01 Task 1 `read_first`/step 引用的 `test_pool_snapshot.py` 行号偏旧：`test_snapshot_roundtrip_no_ever_rows` 实际在 `:145`（非 191-221），`_FakeRepo` 实际在 `:121`（非 105-117）；REQUIREMENTS/RESEARCH 引用的 E4 守卫 `test_pool_hub.py:807-813` 实际在 `:836`。符号均存在、按名可定位，不影响执行。
- **I-3（PATTERNS 漂移）:** `24-PATTERNS.md` §6 写 run_all persist `origin="manual"`，而 24-01-PLAN / 24-RESEARCH D6 一致为 `origin="eod" if is_latest else "backfill"`（origin 合法集含 manual 但本阶段不用）。计划为准，建议顺手更新 PATTERNS 避免执行器困惑。
- **I-4（PATTERNS 漂移）:** `24-PATTERNS.md` 的 `run_pool_backfill` 骨架返回 `{backfilled, failed, failed_dates, dates}`，而 24-01 Task 2 与 behavior Test 1 一致为 `{requested, backfilled, failed, failed_dates, origin}`。计划/测试内部自洽，建议同步 PATTERNS。
- **I-5（测试装配）:** 24-01 Task 3 的 D6 回归测试「基于既有 `_run_all_app` harness」，但 `_run_all_app`（`test_pool_snapshot.py:243`）请求体硬编码 `as_of: "2026-08-04"`（= repo.latest）。历史 as_of 用例需参数化该 harness（新增 `requested_as_of` 入参）。测试设计细节，执行器可处理。
- **I-6（端点健壮性）:** 24-01 Task 3 的 `POST /backfill` 未像 `extend_history`（`api/kline.py:660-666`）那样把 `await request.json()` 包进外层 try/except —— 空 body/非 JSON body 会 500 而非 400。另：端点未调 `invalidate_storage_cache()`/`repo.refresh_cache()`（extend_history 有）；因 `/api/pool/dates` 每次请求实时 glob 文件系统、`/api/pool/history` 直读 part.json，正确性不受影响，但建议与既有端点保持一致性。
- **I-7（估算）:** 两计划 `estimate.tokens`（68000/48000）confidence=low；config 无 `workflow.smart_zone_tokens`，本环境 gsd-tools 无 `estimate-check` 命令 → 无法校准，仅按 task/file 阈值评估（均达标）。数据点不足（0 个已完成相位带 actuals）时不把估算当精确值。
- **I-8（前端消费留待后续）:** HIST-03 的「DateNavigator empty-state」已由既有前端覆盖（`PoolHubPage.tsx:154-157`「该日期无股池快照」）；本阶段交付 `GET /api/pool/dates` 新字段（`backfill_needed`/`backfill_examples`），前端 `PoolDatesResponse` 类型（`api.ts:689-692`）未更新不影响运行时（加键为加法变更）。触发按钮/缺口横幅 UI 属后续增强，API 契约先行，可接受。
- **I-9（guest 面）:** `main.py:778-781` `_GUEST_READ_GET_PATHS` 已含 `/api/pool/dates`、`/api/pool/history`（Phase 22 B-1 已闭环）；24-02 只加字段不加端点，`/api/pipeline/backfill` 为 POST 天然被游客中间件 401 拦截（`main.py:838-840`），零 `main.py` 改动。✓

---

## 结论

- **24-01: EXECUTABLE** — HIST-01/02/04 覆盖完整、文件零重叠、全部符号与守卫边界经源码核验、D6 修复路径正确、回填诚实性（绝不 write_cache + byte-identical + snapshot_origin 缺省 eod）编码到位、测试命令与前置门路径正确。无 B/W。
- **24-02: EXECUTABLE**（建议按 W-1/W-2 在 Task 3 修订）— HIST-02 读侧/HIST-03/HIST-04 回归锁覆盖完整；2 条 WARNING 均为 Task 3 执行内可修的断言实现/verify 路径缺陷（Phase 22 同类先例判 W），不阻断阶段目标。
- **Phase 24 整体: EXECUTABLE（round 1 通过，附 2 条 Task 3 修订项）** — 建议执行前由 planner 对 24-02 Task 3 的 D6 source guard 断言与 docs verify 路径做一次小修订，避免执行中 Task 3 首次 verify 即红。
