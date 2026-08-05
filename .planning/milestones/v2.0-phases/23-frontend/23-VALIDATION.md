---
phase: 23
slug: frontend
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-05
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Phase 23 = 前端 (FRONT-01/02): DateNavigator 按交易日浏览股池 + 股池钻取竞价列（真实集合竞价 vs 派生·虚拟成交分开展示）。两计划 Wave 1→2 串行依赖（23-01 = 后端透传 + 前端查询层；23-02 = DateNavigator + 竞价列钻取 UI），文件零重叠，23-02 依赖 23-01 交付物（`api.poolDates`/`api.poolHistory` + `auction_columns` 服务端声明 + `mask_guest_hub` 顶层剥离）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| 后端测试 | `backend/.venv/bin/python -m pytest <file> -x -q`（仓库约定，非 `uv run pytest`） |
| 前端构建 | `cd frontend && npm run build`（tsc -b + vite build）；仓库无 vitest/jest（诚实记录） |
| E2E | Playwright `frontend/e2e/pool-hub.spec.ts`（mocked 后端，不依赖 live backend） |
| Hermetic fixtures | 后端 `tmp_path` + `_write_strategy_cache`/`_write_snapshot` helper；前端 e2e 用 route mock |
| Production imports | 后端测试函数内局部 import（与既有 test_pool_hub.py 风格一致） |

---

## Nyquist Coverage Map

| Nyquist | Coverage | Evidence |
|---------|----------|----------|
| 8a Criteria from Requirements | POOL-03 守卫扩展（E1-E6 已在 22 期）+ FRONT-01/02 成功标准 | 23-VERIFICATION.md SC1-SC4 |
| 8b Business Logic Branching | `available:false` 空态短路（PIT-2）；`auction_columns.real` 空 → 真实组隐藏 + 徽标（H3）；非交易日禁用（PIT-5） | 23-02 T1/T2 e2e + 单测 |
| 8c Failure Paths | probe 不可用/盘前 fail-closed（SC4）；无快照日 200 空态（PIT-2）；invalid as_of 400（后端已锁） | 23-02 T3 e2e status badge 用例 |
| 8d Correctness of Key Domain Rule | 真实集合竞价列（auction_volume/auction_amount，股/元）与派生·虚拟成交（auction_volume_ratio/auction_unmatched_amount/open_gap）由服务端 `auction_columns` 声明驱动，绝不按行值推断（H3/PIT-3）；绝不混排/相加（PIT-4） | 23-01 T1 expected_keys 12 + 诚实缺列测试；23-02 T2 分组表头 |
| 8e Trade-offs / Anti-features | 历史必走 /api/pool/history（PIT-1）；updated_at 双型容忍不展示（PIT-8）；游客零泄露（H7/H8） | 23-01 T2 guest 守卫；23-02 T3 e2e PIT-1 守卫 |
| 8f Migration / Compatibility | `/api/pool/hub` single-as_of 契约零改动（17 回归原样绿）；`_project_hub` 投影 8→12 键（expected_keys 更新） | 23-01 T1 回归；23-02 后端回归命令 |
| 8g Resource Isolation | e2e 全 mock 不碰真实 data/；零新增 npm/pip 依赖 | 23-02 T3 e2e mocked |

---

## 成功标准 → 验证映射

| SC (ROADMAP) | 验证位置 | 证据 |
|--------------|----------|------|
| SC1 DateNavigator ‹ › 步进 + 日期列表（数据源 /api/pool/dates），每次步进 as_of 重取刷新卡片计数与钻取明细 | 23-02 T1（PoolHubPage selectedDate + queryKey 切换）+ T3 e2e step/dropdown/reset | e2e: 步进后卡片计数/明细随 as_of 变；`QK.poolHistory(d)` 触发请求 |
| SC2 非交易日禁用不静默跳日；无快照日诚实空态非零池 | 23-02 T1（available:false 短路）+ T3 e2e empty-state | e2e: 无快照日显示「该日期无股池快照」；‹ › 边界禁用 |
| SC3 竞价列真实 vs 派生分开展示 + 单位（股/元） | 23-01 T1（auction_columns 声明）+ 23-02 T2（分组表头） | e2e: 两组表头 + 单位；后端 expected_keys 12 |
| SC4 probe 不可用/盘前诚实状态（fail-closed 空态或派生标注） | 23-02 T2（状态徽标）+ T3 e2e | e2e: warning/info/pre-open 徽标用例；真实组隐藏 |

---

## 手动项（human_items）

| 项 | 说明 | 归属 |
|----|------|------|
| DateNavigator 视觉确认 | Playwright mock 覆盖功能路径；真实数据下日期列表/空态观感需浏览器人工确认 | Phase 23 verifier |
| probe 状态徽标在真实环境 | mock 断言徽标渲染；真实 probe available/not_available 场景需人工/环境验证 | Phase 23 verifier |

---

## 需求 Traceability

| 需求 | 计划 | 测试 |
|------|------|------|
| FRONT-01 | 23-02 T1/T3 | e2e step/dropdown/reset/empty-state；`test_pool_hub.py` 回归 |
| FRONT-02 | 23-01 T1/T2 + 23-02 T2/T3 | `test_pool_hub.py` expected_keys 12 + 诚实缺列；`test_guest_masking.py` 零泄露；e2e auction 分组/徽标 |
