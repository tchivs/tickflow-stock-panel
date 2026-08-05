# 22-PLAN-CHECK.md — Phase 22 股池日期导航 计划可执行性核验

**Checked:** 2026-08-05
**Verifier:** gsd-plan-checker (Revision Gate)
**Plans verified:** `22-01-PLAN.md` (POOL-04 + POOL-05), `22-02-PLAN.md` (POOL-06 + E7 + docs)
**Sources read:** 22-RESEARCH.md, 22-PATTERNS.md, ROADMAP Phase 22, `backend/app/services/pool_hub.py`, `strategy_cache.py`, `api/pool.py`, `api/screener.py`, `services/screener.py`, `strategy/engine.py`, `jobs/daily_pipeline.py`, `app/main.py` (auth middleware), `tests/test_pool_hub.py`, `tests/test_guest_masking.py`, `tests/test_factor_hits.py`, `docs/features.md`, `.planning/config.json`
**Structure validator:** `gsd-tools.cjs phase-plan-index 22` — **runs clean** (exit 0; wave 1 = [22-01, 22-02], 7 tasks total, has_checkpoints=false).

## 概要 Verdicts

| Plan | Verdict | Blockers | Warnings |
|------|---------|----------|----------|
| 22-01 | **EXECUTABLE** (with warnings) | 0 | 4 (W-1, W-2, W-3, W-4) |
| 22-02 | **NOT EXECUTABLE** | 1 (B-1) | 3 (W-3, W-5, W-6) |
| Phase 22 (whole) | **NOT EXECUTABLE** — B-1 must be fixed before execution | 1 | 6 total |

---

## 已验证通过的基础事实（实测/源码核验）

1. **测试命令约定** — `backend/.venv/bin/python` 存在；两个计划的全部 7 个 `<verify><automated>` 与 2 个 `<precondition>` 均用 `.venv/bin/python`，**无任何 `uv run pytest`**。✓
2. **文件零重叠** — 22-01 `files_modified`（7 文件）∩ 22-02 `files_modified`（4 文件）= ∅。✓（`phase-plan-index` 输出亦确认。）
3. **回归基线计数** — `test_pool_hub.py` 17 个、`test_guest_masking.py` 15 个、`test_factor_hits.py` 6 个测试函数，与 RESEARCH 声称的 17/15 基线一致。✓
4. **single-as_of 契约锁点** — `pool_hub.py:79-80` 回显逻辑 `resolved_as_of = as_of if (as_of and as_of == cache_as_of) else cache_as_of` 实际存在；22-01 Task 2 明确保留该回显 + 空缓存早退（`build_pool_hub` 签名/行为零改动），`test_get_pool_hub_mismatched_as_of_returns_cache_date` 等精确断言不受影响。✓
5. **`total = result.get("total", len(rows))` 兼容性** — 既有 `_write_strategy_cache` fixture 均带与 `len(rows)` 相等的 `total`；`test_concept_filter_keeps_total_authoritative` 概念筛选收窄 rows 后 total 保持权威，新语义不破坏 17 个既有测试。✓
6. **`concept_attribution` 新增键容忍性** — 既有测试中**无**对非空 hub 顶层 dict 的精确相等断言（`test_get_pool_hub_missing_cache_empty` 走空缓存早退路径，不加该键），`_all_keys` 词汇守卫不含 `concept_attribution`。✓
7. **诚实规则编码** — 快照 payload 只含 `results`（无 `today_ever_rows`/`today_ever_matched`）；概念实时 join + `concept_attribution:"current_snapshot"` 标注（不冻结）；as_of 双校验 `^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat`；缺失快照 200 `available:false`（非 404）；EOD job 直调 `run_all_with_hits` 不 HTTP 自调；**OQ-1 决策编码**：22-02 must_haves 明确"本期不做首日一次性全量回填"，无任何 backfill job 任务。✓
8. **POOL-03 守卫分拆方向** — E2 对 `pool_snapshot.py` 用"只写 screener_results"而非沿用投影无写断言（Pitfall 7）、E3 隔离 `strategy_cache`、E5 禁 `run_all/write_cache/persist_point_snapshot` 于 pool.py、E4 全 GET，方向与 RESEARCH RQ5 一致。✓（但见 W-1/W-2 的断言实现冲突。）
9. **Smart-zone 估算**（`estimate-check --calibrated`，budget=100000，confidence=low / sample_count=0 → 未校准，仅供参考）：
   - 22-01: `tokens=68000, ratio=0.68, over_budget=false`
   - 22-02: `tokens=52000, ratio=0.52, over_budget=false`

---

## Blockers (must fix before execution)

### B-1 — E7 游客白名单需要修改 `backend/app/main.py`，但两个计划都不触碰该文件

- **Dimension:** requirement_coverage / key_links_planned
- **Plan:** 22-02, Task 2
- **Evidence:**
  - 游客放行只认 `_GUEST_READ_GET_PATHS` 精确路径集合：`backend/app/main.py:778` `frozenset({"/api/pool/hub", "/api/screener/strategies"})`；`main.py:781-783` `_is_guest_readable`；`main.py:833-835` 游客分支对非白名单路径返回 401。
  - 22-02 Task 2 新增断言 `client.get("/api/pool/dates").status_code == 200` 与 `client.get("/api/pool/history").status_code == 200`（`test_guest_cannot_read_authed_surfaces` / `test_guest_read_paths_are_get_only`），且 `_make_guest_client`（`test_guest_masking.py:146-164`）使用**真实** `auth_middleware`。
  - 22-02 `files_modified` 只含 `daily_pipeline.py` / `test_pool_eod_job.py` / `test_guest_masking.py` / `docs/features.md`，22-01 亦不含 `main.py`。两个计划都没有把 `/api/pool/dates`、`/api/pool/history` 加入 `_GUEST_READ_GET_PATHS` 的任务。
- **Why it blocks:** 游客 GET 两个新端点会在到达路由前被中间件 401 拦截，`test_guest_masking.py` 扩展后的白名单测试必然失败（verify 不绿），且执行器无法在不越出计划 `files_modified` 的前提下自行修复。
- **Fix hint:** 在 22-02 Task 2 增加一步：`backend/app/main.py:778` 的 `_GUEST_READ_GET_PATHS` 追加 `"/api/pool/dates"` 与 `"/api/pool/history"`（并把 `main.py` 加入 22-02 `files_modified`）。若担心"任何扩宽触发守卫"的注释，可同步更新注释与 `_is_guest_readable` 的 docstring。

---

## Warnings (should fix before/at execution)

### W-1 — E2 守卫断言"同一行含 `screener_results`"与 Task 1 常量实现冲突

- **Dimension:** task_completeness（内部一致性）
- **Plan:** 22-01, Task 3 (E2) vs Task 1 (step 3)
- **Evidence:**
  - Task 3 E2: "对 pool_snapshot.py 源码的每个 `os.replace`/`mkdir`/`open(w)` 出现, 断言同一行含 `screener_results` 子串"。
  - Task 1 step 3 实现：`part_dir = data_dir / _SNAPSHOT_ROOT / f"date={as_of}"` → `part_dir.mkdir(...)` → `os.replace(tmp, path)`。`mkdir` 行与 `os.replace` 行都不含字面量 `screener_results`（只有 `_SNAPSHOT_ROOT` 常量定义行含之）。
- **Why:** 按字面实现，E2 守卫测试会对 `pool_snapshot.py` 的写操作行判失败，`pytest tests/test_pool_hub.py -x -q` 不绿。
- **Fix hint:** 二选一：(a) 在 `pool_snapshot.py` 中让写目标行内联 `"screener_results"`（牺牲常量复用）；或 (b) 将 E2 断言改为解析模块常量（如 `_SNAPSHOT_ROOT == "screener_results"` 且所有写路径经 `_SNAPSHOT_ROOT` 拼出）。建议 (b)。

### W-2 — `_feature_sources()` 改为返回三元组会破坏既有 2 元组解包

- **Dimension:** task_completeness
- **Plan:** 22-01, Task 3 (E1)
- **Evidence:**
  - `test_pool_hub.py:487-491` `_feature_sources() -> tuple[str, str]` 现返回 2 元组；既有解包点：`:507` `service_src, api_src = _feature_sources()`、`:517` `_service_src, api_src = _feature_sources()`、`:524` `service_src, _api_src = _feature_sources()`。
  - Task 3 E1 说"`_feature_sources()` 追加读 pool_snapshot.py (返回三元组)"，同时 E4 说"`test_pool_api_is_get_only` 不变"——返回三元组后这三处解包必须改，否则 `ValueError: too many values to unpack`。
- **Fix hint:** E1 明确改为返回三元组并同步更新三处解包（或返回 `(service, api, snapshot)` 具名结构）；"E4 不变"应指 GET-only 断言逻辑不变，而非解包代码不变。

### W-3 — `build_pool_hub_snapshot(None)` 会因 `_DATE_RE.fullmatch(None)` 抛 TypeError

- **Dimension:** task_completeness / edge-case
- **Plan:** 22-01, Task 2 step 3 + Task 3 step 3；22-02, Task 2 无 as_of 测试
- **Evidence:**
  - Task 2 step 3：`snap = pool_snapshot.load_point_snapshot(data_dir, as_of)`；Task 1 step 4：`load_point_snapshot` 先 `_DATE_RE.fullmatch(as_of)`——`re.Pattern.fullmatch(None)` 抛 `TypeError`，不返回 None。
  - Task 3 step 3："as_of 为 None → 直接走空态路径 (返回 build_pool_hub_snapshot 的缺失分支形状, 200)"——若执行器把 `None` 直接传给 `build_pool_hub_snapshot`，会 500 而非 200。
  - 22-02 Task 2 测试 `client.get("/api/pool/history")`（缺 as_of）断言 200 + `available is False`。
- **Fix hint:** 路由层在 as_of 为 None 时**内联构造空态**（或先判 `as_of is None` 短路），不要把 None 传进 `build_pool_hub_snapshot`；更稳妥的是让 `load_point_snapshot` 对非 str 输入防御性返回 None。

### W-4 — 22-01 任务数 4 触及 scope 警告阈值

- **Dimension:** scope_sanity
- **Plan:** 22-01（4 tasks / 7 files）
- **Evidence:** 任务阈值 target 2-3 / warning 4；估算 ratio 0.68（budget 100000），confidence=low（无已完成相位校准）。文件数 7 在 5-8 target 内。
- **Fix hint:** 可接受，但执行时按 TDD 原子提交推进；若执行中出现 context 压力，优先把 Task 4（run_all 抽取 + 落快照钩子）拆为两步提交。

### W-5 — docs verify 只断言"存在"，不强制"计数 == 1"

- **Dimension:** verification
- **Plan:** 22-02, Task 3
- **Evidence:** `<verify>` 为 `grep -c "27 个内置策略" docs/features.md && grep -c "股池日期导航" docs/features.md`——`grep -c` 返回 0 退出码即通过，2 处重复也通过；acceptance 却要求"27 个内置策略 计数保持 1 处不漂移"。
- **Fix hint:** 改为 `test "$(grep -c "27 个内置策略" docs/features.md)" = "1"`（并同样校验股池日期导航小节 ≥1）。

### W-6 — 22-02 Task 2 precondition 的文件路径在 `cd backend` 后失效

- **Dimension:** task_completeness（precondition gate）
- **Plan:** 22-02, Task 2
- **Evidence:** precondition 命令：`cd backend && .venv/bin/python -c "... s=open('backend/app/api/pool.py').read() ..."`。`cd backend` 后 CWD 已是 `backend/`，`backend/app/api/pool.py` 不存在 → `FileNotFoundError` → precondition 永远失败 → Task 2 即使 22-01 合入也 halt。
- **Fix hint:** 把路径改为 `app/api/pool.py`（相对 `cd backend` 后），或去掉 `cd backend` 用绝对/根相对路径。

---

## Info (建议，非阻塞)

- **I-1（wave/依赖）:** 22-02 `depends_on: []` wave 1，但其 Task 1/2 通过任务级 `<precondition>` 依赖 22-01 交付物；`phase-plan-index` 亦显示两计划同 wave 1。这是有意的 precondition-halt 设计（assignment 已确认），但计划级依赖图不反映该有效依赖——执行编排器必须支持任务级 precondition 阻塞。
- **I-2（API 面增量）:** `_project_hub` 返回追加 `concept_attribution` 后，非空 `/api/pool/hub` 响应也带该新键（research RQ2 已知并接受）。对既有测试无破坏，但 Phase 23 前端需容忍 hub 响应新增顶层键。
- **I-3（缺失 import）:** 22-01 Task 3 的 history 路由使用 `re.fullmatch` 但 import 列表未列 `import re`；执行器补一行即可。
- **I-4（EOD 防御）:** 22-02 Task 1 的 `strategy_fingerprint(app_state.strategy_engine)` 未包 try/except（22-01 路由钩子包了）；`strategy_engine` 为 None 时 job 会失败。生产 main.py:550-554 总是装配 engine，风险低。

---

## Nyquist (8a-8d)

| Task | Plan | Automated Verify | Status |
|------|------|------------------|--------|
| 1 persist/load/list/fingerprint | 22-01 | `pytest tests/test_pool_snapshot.py -x -q` | ✅ |
| 2 `_project_hub` + `build_pool_hub_snapshot` | 22-01 | `pytest tests/test_pool_hub.py -x -q` | ✅ |
| 3 `/pool/dates` + `/pool/history` + 守卫 E1-E6 | 22-01 | `pytest tests/test_pool_hub.py -x -q` | ✅（受 W-1/W-2 影响） |
| 4 run_all_with_hits + 落快照钩子 | 22-01 | `pytest tests/test_pool_snapshot.py tests/test_factor_hits.py -x -q` | ✅ |
| 1 EOD job | 22-02 | `pytest tests/test_pool_eod_job.py -x -q` | ✅ |
| 2 游客白名单 E7 | 22-02 | `pytest tests/test_guest_masking.py -x -q` | ❌（B-1） |
| 3 docs 对账 | 22-02 | `grep -c ...` | ✅（W-5 弱断言） |

- 8a Automated verify: 全部 7 任务均含 `<automated>`，无 `MISSING`，无需 Wave 0 依赖。✅
- 8b Feedback latency: 全为单元/API pytest，无 E2E/`--watchAll`/>30s 延迟。✅
- 8c Sampling continuity: wave 1 内 22-01 4/4、22-02 3/3 任务带 automated。✅
- 8d Wave 0: 无 `<automated>MISSING</automated>` 引用。✅
- 8e VALIDATION.md: **缺失**（`.planning/phases/22-pool-date-navigation/` 下无 `*-VALIDATION.md`）——research 已含 "Validation Architecture" 节，预计由 plan-phase orchestrator 在 plan-check 通过后生成；**不作为本回合阻塞**，但需 orchestrator 在进入 execute 前补出 22-VALIDATION.md。

---

## 结论

- **22-01: EXECUTABLE** — 需求 POOL-04/05 覆盖完整、无文件重叠、测试命令正确、诚实规则编码到位；4 条 WARNING 均可在执行内/小幅修订解决。
- **22-02: NOT EXECUTABLE** — B-1（游客白名单需改 `main.py:778` 但不在任何计划 files_modified 中）会导致 `test_guest_masking.py` 白名单测试必败；另 3 条 WARNING（W-3/W-5/W-6）建议一并修订。
- **Phase 22 整体: NOT EXECUTABLE** — 需先修复 B-1（并在 revision 中处理 W-1..W-6）后重跑 plan-check。
