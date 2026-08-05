# 22-REVIEW-2.md — Phase 22 股池日期导航 计划再核验 (Revision Gate, Round 2)

**Checked:** 2026-08-05
**Verifier:** gsd-plan-checker (PlanChecker22b)
**Mode:** Re-verification after orchestrator fixes (B-1, W-1, W-2, W-3, W-5, W-6, I-3)
**Plans verified:** `22-01-PLAN.md` (POOL-04 + POOL-05), `22-02-PLAN.md` (POOL-06 + E7 + docs)
**Sources re-checked (live):** `backend/app/main.py` (L777-783, L833-835), `backend/tests/test_pool_hub.py` (L487-546), `backend/tests/test_guest_masking.py`, `backend/app/services/pool_hub.py` (L69-146), `docs/features.md`, both plan files
**Structure validator:** `gsd-tools.cjs phase-plan-index 22` — **runs clean** (exit 0; wave 1 = [22-01, 22-02], 7 tasks total, has_checkpoints=false; `22-REVIEW*.md` out of `*-PLAN.md` glob).

## 概要 Verdicts

| Plan | Verdict | Blockers | Warnings | Infos |
|------|---------|----------|----------|-------|
| 22-01 | **EXECUTABLE** | 0 | 1 (W-4, pre-existing scope) | 2 (I-1, I-2, pre-existing) |
| 22-02 | **EXECUTABLE** | 0 | 0 | 1 (I-4, left as-is, acceptable) |
| Phase 22 (whole) | **EXECUTABLE** | 0 | 1 | 3 |

---

## 修复逐项核验（对照 orchestrator fixes 清单）

### B-1 — FIXED ✅
- 22-02 `files_modified` 现含 `backend/app/main.py`（5 文件: daily_pipeline.py / main.py / test_pool_eod_job.py / test_guest_masking.py / docs/features.md）。
- must_haves 第 28 行 truth 明确要求把两新路径加入 `_GUEST_READ_GET_PATHS` frozenset（main.py:778，否则 auth_middleware 路由前 401 拦截游客）。
- Task 2 `<files>` 含 `backend/app/main.py`；action step 0（L144）把 `"/api/pool/dates"` 与 `"/api/pool/history"` 追加进 frozenset，并注明 `_is_guest_readable` 读同一集合无需改。
- **源码实测**：main.py:778 `_GUEST_READ_GET_PATHS = frozenset({"/api/pool/hub", "/api/screener/strategies"})`、L783 `return method == "GET" and path in _GUEST_READ_GET_PATHS`、L833-835 游客分支 401。与计划引用的行号/逻辑一致。
- **无新问题**：全测试目录 grep 确认**无**任何测试断言 `_GUEST_READ_GET_PATHS` 的精确 frozenset 内容（test_guest_masking.py 只按 HTTP 行为断言，路径元组由本计划 Task 2 同步扩展），扩宽白名单不会破坏既有 exact-match 守卫。

### W-1 — FIXED ✅
- 22-01 Task 3 E2（L207）改为 **常量感知**：解析 `pool_snapshot.py` 模块常量 `_SNAPSHOT_ROOT == "screener_results"`（AST 或正则），并断言所有写路径（`os.replace`/`mkdir`/`open(w)`）的写目标均经 `_SNAPSHOT_ROOT` 或直接含 `screener_results` 派生。
- 与 Task 1 实现一致：L105 定义 `_SNAPSHOT_ROOT = "screener_results"`，L107 `part_dir = data_dir / _SNAPSHOT_ROOT / f"date={as_of}"`，L109 list 亦经 `_SNAPSHOT_ROOT`。不再要求写操作行内联字面量。

### W-2 — FIXED ✅
- 22-01 Task 3 E1（L206）明确 `_feature_sources()` 返回三元组 `(service_src, api_src, snapshot_src)` 并**同步更新既有三处 2 元组解包**：`test_pool_hub_no_execution_imports` (L507)、`test_pool_api_is_get_only` (L517)、`test_build_pool_hub_has_no_write_path` (L524)（否则 `ValueError: too many values to unpack`）。
- **源码实测**：`_feature_sources() -> tuple[str, str]`（L487-490）确为 2 元组；全文件恰好三处 `= _feature_sources()` 解包点位于 L507/L517/L524，与计划列举完全一致。

### W-3 — FIXED ✅
- 22-01 Task 1 step 4 `load_point_snapshot` 先 `if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of): return None`（isinstance 守卫在 fullmatch 之前，非 str 不抛 TypeError）。
- 路由层（Task 3 step 3）对 as_of=None 短路空态 + 双校验 400，双保险均闭合。

### W-5 — FIXED ✅
- 22-02 Task 3 `<verify>` 改为 `test "$(grep -c "27 个内置策略" docs/features.md)" = "1" && grep -q "股池日期导航" docs/features.md` — 强制计数 == 1 且小节存在。
- **源码实测**：`docs/features.md` 当前 `grep -c "27 个内置策略"` = 1（exit 0），命令目标真实存在且可判定。命令无 `2>/dev/null || echo` 吞错模式，符合 Verify Command Format Sanity。

### W-6 — FIXED ✅
- 22-02 Task 2 precondition 路径改为 `open('app/api/pool.py')`（相对 `cd backend` 后有效）。Task 1 precondition 用 `from app.services.pool_snapshot import ...`（模块导入，`cd backend` 后亦可解析），无 FileNotFoundError 风险。

### I-3 — FIXED ✅
- 22-01 Task 3 step 1 import 列表已含 `import re`（连同 `from datetime import date as date_type`、`HTTPException`、`build_pool_hub_snapshot`、`list_snapshot_dates`）。

---

## 全量检查集再跑

1. **测试命令约定** ✅ — 两个计划全部 7 个 `<verify><automated>` + 2 个 `<precondition>` 均用 `cd backend && .venv/bin/python -m pytest/-c`；全文件 grep **零 `uv run`**。
2. **文件零重叠** ✅ — 22-01（7 文件）∩ 22-02（5 文件，含新增 main.py）= ∅；`phase-plan-index` 亦确认。
3. **诚实规则** ✅ —
   - 无 union 键：persist payload 只含 `as_of/computed_at/strategy_version/snapshot_type/schema_version/results`，`test_snapshot_roundtrip_no_ever_rows` + `test_run_all_persists_point_snapshot` 断言无 `today_ever_rows/today_ever_matched`。
   - 不冻结概念标签：`concept_attribution: "current_snapshot"` 显式标注（实时 join 当前 ext）。
   - as_of 双校验：`^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat`，非法 → 400。
   - 缺失快照 → 200 `available:false` 空态（非 404）。
   - EOD job 直调 `run_all_with_hits` service 核心，绝不 HTTP 自调 POST run_all。
   - OQ-1 决策：22-02 must_haves 明示"本期不做首日一次性全量回填"，无 backfill job 任务。
4. **single-as_of hub 契约** ✅ — `build_pool_hub` 签名/行为零改动（回显 L79-80 实为 L93 `resolved_as_of = as_of if (as_of and as_of == cache_as_of) else cache_as_of` 保留），17 个既有 test_pool_hub 零修改锁死。
5. **POOL-03 守卫扩展健全性** ✅ — E1 三元组（三解包点同步）、E2 常量感知（只写 screener_results）、E3 隔离 strategy_cache（不 import/reference）、E4 全 `@router.get`、E5 pool.py 禁 run_all/write_cache/persist_point_snapshot、E6 词汇守卫扩至 `/api/pool/history`（有快照）+ `/api/pool/dates`（`_all_keys` 机制 L529-536 实测存在）、E7 游客白名单（22-02 Task 2，与 B-1 一致）。
6. **Smart-zone 估算**（`estimate-check --calibrated`，budget=100000，confidence=low / sample_count=0 → 未校准，仅供参考）：
   - 22-01: `tokens=68000, ratio=0.68, over_budget=false, recommendation=null`
   - 22-02: `tokens=52000, ratio=0.52, over_budget=false, recommendation=null`

---

## 剩余项（非阻塞）

- **W-4（22-01，pre-existing，未列入 fix 清单）**：4 tasks / 7 files 触及 scope 警告阈值（target 2-3 / warning 4）。可接受：执行按 TDD 原子提交推进，若 context 压力大优先把 Task 4 拆两步提交。
- **I-4（22-02，left as-is，确认可接受）**：EOD job `strategy_fingerprint(app_state.strategy_engine)` 未包 try/except（22-01 路由钩子包了）。生产 main.py:550-554 恒装配 strategy_engine，`strategy_engine=None` 仅在测试未装配时出现且测试 fixture 显式装配 engine；风险低，接受。
- **I-1（22-01/22-02，pre-existing，info）**：两计划同 wave 1，22-02 经任务级 `<precondition>` 阻塞等待 22-01 交付物 — 有意的 precondition-halt 设计；执行编排器须支持任务级 precondition。
- **I-2（22-01，pre-existing，info）**：`_project_hub` 追加 `concept_attribution` 顶层键后，非空 hub 响应也带该键；Phase 23 前端需容忍。
- **Nyquist 8e**：`*-VALIDATION.md` 仍缺失（research 已含 Validation Architecture 节）— 与首轮结论一致，预计 plan-check 通过后由 plan-phase orchestrator 生成；进入 execute 前需补出。

---

## 结论

- **22-01: EXECUTABLE** — 需求 POOL-04/05 覆盖完整；W-1/W-2/W-3/I-3 已修复且与源码逐点吻合；仅剩 pre-existing W-4（scope 4 tasks）与 I-1/I-2 两个 info，均不阻塞。
- **22-02: EXECUTABLE** — B-1 已修复（main.py 入 files_modified + frozenset 扩宽 + 测试同步，无精确内容断言破坏）；W-3/W-5/W-6 已修复；仅剩 I-4（info，确认可接受）。
- **Phase 22 整体: EXECUTABLE** — 0 blockers。可进入 `/gsd-execute-phase 22`（前提：orchestrator 补出 22-VALIDATION.md）。
