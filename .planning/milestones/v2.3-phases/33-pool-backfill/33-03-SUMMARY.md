# 33-03 执行摘要 — PB-02 全量 248 运营手册 + PB-04 premarket 诚实缺口 + 结构门测试

**计划:** `.planning/phases/33-pool-backfill/33-03-PLAN.md` · **执行日期:** 2026-08-06 · **执行者:** ExecutorP3303
**状态:** ✅ 完成 — docs/features.md 股池回填运营手册 + premarket 诚实缺口 + probe 注记落地; `test_premarket_pool.py` 14 用例 (13 既有零改动 + 1 新结构门) 全绿; 手册步骤 7 在 33-01 真实 8 日产物上逐条复验通过; 守卫回归 44 绿; 原子提交 2 个。

---

## 1. Task 1/2 — docs/features.md 股池回填小节 (PB-02 手册 + PB-04 缺口 + probe 注记)

新增 `### 🗄️ 股池回填 (Pool Backfill)` 小节 (features.md:81-116, 紧邻既有「竞价历史回填」小节, 镜像其运营面/触发/验证/诚实注记形), 既有小节零改动:

| 内容 | 落点 |
|---|---|
| 运营面: `POST /api/pipeline/backfill` body `{"start"/"end"/"max_days"}` → `{"status":"started"\|"reused","job_id"}`; 单飞 + 重任务执行槽互斥 (并发 → `已有数据任务在运行`) | 小节首段 |
| **全量 248 一次调用**: `max_days` 上限 500 ≥ 248 (2025-07-29..2026-08-05), 无需分块; 触发示例 curl (`{}` 或显式界) | 触发示例 |
| 轮询/取消: `GET /api/pipeline/jobs/{id}` 终态 6 键; `POST .../cancel` 合作式 (当前日完成后停); 失败处理: `failed_dates` 即剩余缺口, 重跑幂等 | 轮询/取消 + 失败处理 |
| 跑后验证 (步骤 7): `ls \| wc -l`==248 / `jq .snapshot_origin`==backfill / `/pool/dates` backfill_needed==0 / `/pool/history` 渲染; **provenance 在分区 payload 内** (`snapshot_origin` 键 + `strategy_version` 指纹, 无独立 manifest) | 跑后验证 |
| 前置检查: `df -h data/` ≥1 GiB / enriched 248 / 当前缺口基线 / 网络 (probe) | 前置检查 |
| 预期 (**实测锚点取代早期估算**): 13s/8 日 → 全量 248 ≈ **6-7 分钟** (早期 20-120min [INFERENCE] 已为实测取代); **2.6 MiB/日 → ≈ 650 MiB** (早期 79-693 MiB [INFERENCE] 区间, 实测落上沿); `strategy_version` 指纹 → 改策略需重跑 | 预期 |
| **premarket_results 诚实缺口 (PB-04)**: 唯一创建方 = 09:26 job `premarket_pool_preview`; 部署门禁 (scheduler 仅非 fixture_mode) + 数据门禁 (live 09:15-09:25, 盘前空帧 → 诚实 `available:false`); **沙箱无任何路径产生该目录 (实测不存在)**; 回填/手动 run_all 绝不触碰 premarket root; 前端空态已诚实; 无沙箱路径, 绝不伪造 | 诚实缺口段 |
| **Probe 网络注记 (Phase 32 联动)**: 回填逐日一次 live HTTP (PROBE_SYMBOL `000001`, 8s 超时); 源挂全量最坏 +~33min; 诚实双峰: fail-closed → requires_auction_data 族 0 行 (引擎短路), available → 真列族 ≤2 标的 (实测 0 行), 派生族全市场 (实测 50/50/43), 绝不产生全市场规模结果 | probe 注记段 |

**文档结构门 (grep, 全过)**: `股池回填` @ :81 · `max_days` (500 论证) · `backfill_needed` ×3 · `premarket_results` (诚实缺口段 @ :109 + 既有 :46/:205) · `09:26` ×4 · `fail_closed` ×3。与既有 :30 一句话回填描述对账: 不重复不冲突 (既有描述原样, 新小节提供操作细节)。

## 2. Task 3 — 结构门测试 + 手册步骤 7 沙箱复验 (PB-04 结构面)

### 2.1 测试 (test-first, 只追加)

`backend/tests/test_premarket_pool.py` +43 行, 追加 `test_pool_backfill_never_creates_premarket_root` 至文件尾 (既有 13 用例零改动):

- tmp data_dir 建 3 个 enriched 分区日 (2026-08-01..03); 局部 `_FakeRepo` 复用 (本文件既有 :64-90, 形吻合); patch `ScreenerService.run_all_with_hits` (canned results 形, 镜像 test_pool_backfill._canned_results) → `run_pool_backfill(repo, max_days=2)` 服务级直调。
- 断言: 终态 6 键精确集 `{requested:2, backfilled:2, failed:0, failed_dates:[], origin:"backfill"}`; 前 2 个缺口日快照 `snapshot_origin=="backfill"` (快照侧正常, 隔离锁不误伤); 第 3 日未写; **`(tmp_path/"premarket_results").exists()` 为 False** (root 隔离锁, 回填路径绝不越界创建盘前根)。
- 生产 import 放函数内 (repo 惯例); 零跨测试文件 import。

### 2.2 手册步骤 7 复验 (沙箱, 33-01 真实 8 日产物上逐条执行)

服务: 复用 33-02 executor 的 hub 托管实例 `backend3019` (`cd backend && .venv/bin/python -m uvicorn app.main:app --port 3019`, 就绪后使用; 游客 GET 白名单 `/api/pool/dates` `/api/pool/history` 当前代码正常放行, 无需 cookie)。复验后交还 33-02 停服 (共享单实例, 未重复启动)。

| 步骤 7 命令 | 沙箱实测 | 全量目标 (PB-02) | 结论 |
|---|---|---|---|
| `ls data/screener_results \| wc -l` | **8** | 248 | 机制实证 (33-01 产物) ✓ |
| `jq -r '.snapshot_origin' data/screener_results/date=2026-08-05/part.json` | **backfill** | backfill | provenance 在分区 payload ✓ |
| `curl -s localhost:3019/api/pool/dates \| jq '{count, backfill_needed}'` | **`{"count": 8, "backfill_needed": 240}`** | `{"count": 248, "backfill_needed": 0}` | 缺口计数语义 ✓ |
| `ls data/premarket_results 2>/dev/null \| wc -l` | **0** (目录不存在) | 0 (部署后由真实 09:26 job 按日产生) | PB-04 沙箱无路径 ✓ |
| `curl -s "localhost:3019/api/pool/history?as_of=2026-07-27"` | 200, `snapshot_origin:"backfill"`, n=27, `mode:"guest"` | 渲染 backfill | W-1 应用: present-state 无 `available` 键, 断言 origin + n≥1 (沙箱最早回填日 2026-07-27 ↔ 全量最早 2025-07-29) ✓ |

## 3. 验证

- 结构门: `.venv/bin/python -m pytest tests/test_premarket_pool.py -x -q` → **14 passed** (13 既有零改动 + 1 新)。
- 守卫回归 (本文件 + 已提交共享面, 不跑 33-02 在飞文件): `pytest tests/test_premarket_pool.py tests/test_pool_backfill.py tests/test_guest_masking.py -q` → **44 passed**。
- 文档结构门 grep 全过 (§1 表)。

## 4. 提交

| hash | 消息 |
|---|---|
| `344e20c` | `docs(phase-33): PB-02 pool backfill runbook + PB-04 premarket honest gap (features.md + structural test)` (+91 -0, docs/features.md + backend/tests/test_premarket_pool.py) |
| `9f162ef` | `docs(33-03): complete 33-03 plan (PB-02 runbook + PB-04 honest gap + structural gate)` (+73 -0, 本摘要) |

提交门: `git status --short` 仅 `M frontend/src/pages/Watchlist.tsx` (用户未暂存改动, 全程未 read/未 edit/未 add/未 commit) + 本计划文件; 所有提交显式 `git add <单文件>`, 无 `git add -A`。

## 5. 偏差 (deviation log)

1. **W-4 应用 (PLAN-CHECK)**: 计划 T3 behavior 缺起服务命令 → 本摘要 §2.2 记录服务生命周期 (hub 托管, 共享 33-02 单实例 3019, 复验后交还停服; 未重复启动第二实例)。
2. **端口**: 手册文档按生产标准写 3018 (README.md:54); 沙箱复验走 3019 (3018 被 stale root 容器占用, 33-01 偏差先例)。
3. **测试计数**: RESEARCH §4.1 / PLAN-CHECK 引 test_premarket_pool.py "12 既有"; 实测既有 **13** 用例 (多 `test_premarket_api_pool03_ast_guard` 等) → 追加后 **14** 全绿, 既有零改动 (计数事实修正, 非范围变更)。
4. **W-1 无关** (33-02 面): `/pool/history` present-state 无 `available` 键 — 复验断言 `snapshot_origin=="backfill"` + n≥1 (n=27), 与 33-01/33-02 口径一致。
5. **未触后端源码** (pipeline.py / pool_backfill.py / pool_snapshot.py / premarket_pool.py / daily_pipeline.py / main.py 零改动); 零新增运行时依赖; 未创建任何 premarket 产物 (诚实: 无沙箱路径)。

## 6. 后续依赖物 (33-02/33-04 及部署)

- 运营手册已就位: 部署后按 features.md:81-116 执行全量 248 回填 (单次调用, ~6-7 min, ~650 MiB)。
- premarket_results 在真实部署 + 实时竞价 feed 下由 09:26 job 按日产生 (双门禁解除后), 沙箱零伪造。
