# 33-02 执行摘要 — PB-03 PIT 联动端到端验证 (渲染 + 概念回退键集锁)

**计划:** `.planning/phases/33-pool-backfill/33-02-PLAN.md` · **执行日期:** 2026-08-06 · **执行者:** ExecutorP3302
**状态:** ✅ 完成 — `test_pool_hub.py` +1 新用例 (回填快照渲染), `test_concept_history.py` +1 新用例 (回填日概念回退键集锁 + 正向对照 + origin 无关性); 全量回归 52 passed; 守卫回归 23 passed; 沙箱真实回填快照 3 日抽查与单元断言同源。**零源码改动** (纯测试追加 + SUMMARY), 零新增依赖, 未触碰 `frontend/`。

---

## 1. Task 1 — `test_pool_history_renders_backfilled_snapshot` (test_pool_hub.py, 只追加)

- 布置: `_write_snapshot(tmp_path, origin="backfill")` (既有 helper, 默认 3 策略: auction_bullish/preopen_quant/early_star, computed_at 2026-08-04T15:30:00) → `_make_client(tmp_path, engine=_FakeEngine())` → `GET /api/pool/history?as_of=2026-08-04`。
- 断言:
  - 200; `as_of` 回显; `mode=="vip"`; **W-1 应用**: present-state 响应**无 `available` 键** (空态专属) — 以 `snapshot_origin=="backfill"` + `len(strategies)==3` 区分存在态;
  - `snapshot_origin=="backfill"` (透传, 非 eod 缺省); 3 策略各含 id/name/rows/total, 引擎注入 → 中文显示名三映射精确, `sum(total)==5` 权威一致;
  - `updated_at == "2026-08-04T15:30:00"` (== 快照 computed_at 投影语义);
  - `concept_attribution=="current_snapshot"` 且响应无 `concept_effective_date`/`concept_captured_at` 键 (无 ext_history fixture → 诚实回退, CONCEPT-05);
  - **W-2 应用**: `snapshot_type`/`schema_version` 响应键**缺席**, 断言落在分区载荷 `pool_snapshot.load_point_snapshot(...)` → `snapshot_type=="point"` / `schema_version==1`。

## 2. Task 2 — `test_pool_history_backfilled_date_concept_fallback` (test_concept_history.py, 只追加)

- 布置: `d="2026-07-27"` (镜像 33-01 真实回填首日) + 本文件既有 `_write_snapshot_with_origin` 局部 helper (重写 provenance 键, 不跨文件 import) + `_write_concept_ext` (沙箱状态镜像: ext_data 在, ext_history 缺)。
- 断言 1 (回退诚实): 回填快照 + 无 `ext_history/gn_ths/date=D` 分区 → `build_pool_hub_snapshot` → `concept_attribution=="current_snapshot"`, 载荷顶层**无** `concept_effective_date`/`concept_captured_at` 键 (键集锁 — 回退绝不携带 PIT 时间戳)。
- 断言 2 (正向对照, 证明锁非空转): 同 data_dir 写 `ext_history/gn_ths/date=D/part.parquet` (既有 `_write_partition_fixture`) → 同一 as_of 翻转为 `as_of_snapshot` + `concept_effective_date==d` + `concept_captured_at=="2026-08-04T10:00:00"` — 读侧机制真实。
- 断言 3 (origin 无关性): 换 `origin="eod"` 快照同布置 → 仍 `current_snapshot` 无时间键 — 归属只由 ext_history 分区决定, 回填不特殊化概念语义。

## 3. Task 3 — 沙箱真实快照抽查 (PB-03 端到端证据)

- 服务: hub 托管 `backend3019` (`.venv/bin/python -m uvicorn app.main:app --port 3019`, cwd backend), ready 13.4s; 登录 `POST /api/auth/login {"password": <repo .env AUTH_PASSWORD>}` → `tf_session` cookie; 用后即停 (exit=143), 3019 已释放交还 33-03 兄弟执行器。
- **3 日抽查 (curl + jq, 全部一致)**:

```
2026-07-27 → {"as_of":"2026-07-27","has_available":false,"snapshot_origin":"backfill","concept_attribution":"current_snapshot","has_effective":false,"has_captured":false,"n":27,"updated_at":"2026-08-06T21:39:05"}
2026-07-30 → {"as_of":"2026-07-30","has_available":false,"snapshot_origin":"backfill","concept_attribution":"current_snapshot","has_effective":false,"has_captured":false,"n":27,"updated_at":"2026-08-06T21:39:10"}
2026-08-05 → {"as_of":"2026-08-05","has_available":false,"snapshot_origin":"backfill","concept_attribution":"current_snapshot","has_effective":false,"has_captured":false,"n":27,"updated_at":"2026-08-06T21:39:15"}
```

- W-2 端到端镜像: 分区载荷 `data/screener_results/date=2026-07-27/part.json` → `{"snapshot_type":"point","schema_version":1,"snapshot_origin":"backfill"}` — provenance 键在分区, 不在 /pool/history 投影。
- 湖状态: `ls data/screener_results | wc -l` == 8 (33-01 回填分区就位); `premarket_results` 0; `ext_history` 0 (缺失 → current_snapshot 回退的根因, 与单元断言同源)。

## 4. 回归结果

| 命令 | 结果 |
|---|---|
| `pytest tests/test_pool_hub.py tests/test_concept_history.py -x -q` | **52 passed** (36 + 16) |
| 守卫回归 (POOL-03 E1-E6 + `test_hub_response_has_no_execution_vocabulary` + `tests/test_guest_masking.py`) | **23 passed** |

## 5. 偏差 (deviation log)

1. **测试基数与计划不符 (RESEARCH §4.1 计数漂移)**: 计划引 47+15=62 既有, 实测 `test_pool_hub.py` 35 既有 + `test_concept_history.py` 15 既有 = 50 既有 (grep `^def test_` 计数, 可能含参数化/异文件漂移); 追加 2 新后共 **52 passed**。既有用例零改动 (git diff 仅纯追加, 无任何 `-` 内容行)。
2. **W-1 应用**: present-state `/pool/history` 无 `available` 键 — 单元断言与 curl jq 均以 `snapshot_origin=="backfill"` + `n≥1` 区分存在态 (`has_available:false` 如实记录缺席)。
3. **W-2 应用**: `snapshot_type`/`schema_version` 属分区 payload — 断言移到 `load_point_snapshot` + 真实分区 jq, 响应键集断言二者缺席。
4. **端口/认证沿用 33-01 偏差**: 3018 为 stale root 容器占用 → 3019; 非游客端点需 `tf_session` cookie (POST /api/auth/login, AUTH_PASSWORD 取 repo `.env`, 与容器 env 一致)。
5. **与 33-03 兄弟执行器并发协调**: 通过 hub 消息协商 3019 生命周期 (33-02 先起先停, 停后通知 33-03 复用/自起), 零端口冲突, 零文件重叠。
6. 沙箱 `ext_history` 目录不存在 (真实) — 未创建任何临时分区 (单元正向对照已覆盖 as_of_snapshot 机制), 遵守「绝不写 ext_history 到真实 data/」。

## 6. Watchlist 零触碰证明

- `git status --short` (提交前): 仅 `M backend/tests/test_pool_hub.py` + `M backend/tests/test_concept_history.py` (本计划) + `M docs/features.md` (33-03 兄弟执行器) + `M frontend/src/pages/Watchlist.tsx` (用户未暂存改动, 本会话对其零工具调用 — 未 read/未 edit/未 add/未 commit)。
- 本计划提交均显式 `git add <单文件>`, 无 `git add -A` / `git add .`。
