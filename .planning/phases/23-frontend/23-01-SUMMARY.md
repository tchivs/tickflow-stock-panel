# 23-01 SUMMARY — 后端透传 + 前端查询层 (FRONT-01/02 前置面)

**Phase:** 23-frontend · **Plan:** 23-01 · **Wave:** 1
**Status:** ✅ COMPLETE — 3/3 tasks green, committed atomically
**Date:** 2026-08-05

## Objective

交付 Phase 23 (FRONT-01/02) 的**后端透传 + 前端查询层**前置面: 扩展 `pool_hub._project_hub` 投影循环把快照 raw rows 已携带的竞价列 (`auction_volume`/`auction_amount`/`auction_volume_ratio`/`auction_unmatched_amount`) 透传进投影行 (8 键 → 12 键), 并新增顶层 `auction_columns: {real, derived}` 服务端列存在性声明字段 (hub 与 history 双路径, 经共享 `_project_hub` 单点生效); `mask_guest_hub` 对游客剥离顶层 `auction_columns` (H7); 前端 `api.ts`/`queryKeys.ts` 新增 `poolDates`/`poolHistory` 方法与 `QK` keys, 并扩展 `PoolHubRow`/`PoolHubResponse` 类型 (`available?`/`auction_columns?`/`concept_attribution?`/`auction_*`/`updated_at` 双型容忍, PIT-8)。23-02 的 DateNavigator 与竞价列 UI 以本计划为 precondition 门。

## Tasks Delivered

| Task | Deliverable | Commit |
|------|-------------|--------|
| 1 | `services/pool_hub.py` — `_project_hub` 透传 4 竞价键 (12 键投影) + 顶层 `auction_columns` 声明 (raw rows 键存在性逐列计算, real/derived 过滤; 概念筛选逻辑不变); build_pool_hub 反漂移回显 + 空缓存早退 dict + build_pool_hub_snapshot 缺失分支零改动; `test_pool_hub.py` `expected_keys` 8→12 + 透传 round-trip + 诚实缺列 + 声明一致性测试 | `f8f21cb` |
| 2 | `services/guest_masking.py` — `mask_guest_hub` 返回前 `pop("auction_columns")` (顶层剥离, 行级 `auction_*`/`open_gap` 由 `_GUEST_VISIBLE` 白名单天然丢弃, 白名单不改); `test_guest_masking.py` `_sample_hub` 扩展 + 顶层剥离单元测试 + 端点 VIP/guest 对照守卫 | `d93da86` |
| 3 | `frontend/src/lib/queryKeys.ts` — `QK.poolDates` / `QK.poolHistory(asOf)` (与 `QK.poolHub` 物理分离, 不入 `SSE_INVALIDATE_PREFIXES`); `frontend/src/lib/api.ts` — `api.poolDates()` / `api.poolHistory(asOf)` + `PoolDatesResponse`/`AuctionColumnsDecl` 类型 + `PoolHubRow` 4 竞价可选键 + `PoolHubResponse` `available?`/`auction_columns?`/`concept_attribution?` + `updated_at: number | string | null` | `2ed83eb` |

## Test Results (all green)

```
cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py tests/test_guest_masking.py -q
→ 47 passed
cd frontend && npm run build   # tsc -b && vite build
→ ✓ built (tsc 0 errors, vite bundle OK)
```

| Suite | Count | Notes |
|-------|-------|-------|
| `tests/test_pool_hub.py` | 30 | 27 既有 (含 AST 守卫 E1-E6) 零修改通过 + 3 新增 (透传 round-trip / 诚实缺列 / 声明一致性) |
| `tests/test_guest_masking.py` | 17 | 15 既有零修改通过 + 2 新增 (顶层剥离单元 / 端点 VIP↔guest 对照守卫) |
| `cd frontend && npm run build` | green | `tsc -b` 类型检查 + vite build; 仅既有 chunk>500kB 提示 (非错误) |

## Contract Compliance

- **OQ-2 透传**: `_project_hub` 投影行恒 12 键; raw row 缺竞价键 → `_safe_num(None)` → `None` (诚实缺列, 非 0 填充); 顶层 `auction_columns` 由 raw rows 键存在性计算 (`real` 非空 iff probe 双闸门注入), 经共享 `_project_hub` 单点生效于 hub 与 history 双路径。
- **PIT-3 消歧**: 列存在性只由服务端声明回答; `test_project_hub_honest_absent_auction_columns` (默认夹具 real==[], derived 不含竞价派生键) + `test_project_hub_auction_columns_match_projection_keys` (极端夹具只带 auction_volume → real==["auction_volume"]) 锁死。
- **PIT-6 零改动**: `build_pool_hub` 反漂移回显 L173 逻辑、空缓存早退 dict、`build_pool_hub_snapshot` 缺失分支空态 dict 全部零改动; `test_get_pool_hub_missing_cache_empty` / `test_build_pool_hub_empty_cache` / `test_build_pool_hub_snapshot_missing_available_false` 精确 dict 相等测试原样通过。
- **H7 游客零泄露**: guest 响应顶层无 `auction_columns`, 行无 `auction_*`/`open_gap`; VIP 对照证明是掩码剥离而非投影缺失。
- **PIT-1 历史端点**: 前端历史只走 `/api/pool/history` (`api.poolHistory` + `QK.poolHistory` 与 `poolHub` 物理分离); `/hub?as_of=` 反漂移语义不变。
- **PIT-8 双型容忍**: `PoolHubResponse.updated_at` 改 `number | string | null` (hub=epoch ms / history=ISO 串 / 空态 null); 前端本期不展示 `updated_at`。
- **零新增外部运行时依赖**: 无 pip/npm 安装 (全部既有锁定栈)。
- **POOL-03 AST 守卫 E1-E6** 与 GUEST-02 隔离守卫零修改通过 (未引入执行族 import/写路径/非 GET 路由)。

## Deviations

1. **W-23-01-1 (contract-declared)**: `test_guest_masking.py` 无 `_make_client` fixture (仅 `_make_guest_client` + cookie 模式)。VIP 对照断言改为: `_make_guest_client` + monkeypatch `is_valid_session`/`resolve_authenticated_reviewer` + `tf_session` cookie (同 `test_vip_valid_cookie_returns_clear_hub` 既有模式), 未发明新 fixture。
2. **W-23-01-2 (contract-declared)**: 实际 `test_pool_hub.py` 为 27 个测试函数 (含 AST 守卫 E1-E6, 非计划引用的 17 个投影/API 回归); 全部 27 个零修改通过, 加 3 新增 = 30。
3. **hub 路径声明断言追加**: 在既有 `test_build_pool_hub_single_as_of_counts_and_columns` 内追加一行 `hub["auction_columns"] == {"real": [], "derived": ["open_gap"]}` — 证明 build_pool_hub 路径同样经共享 `_project_hub` 携带顶层声明 (计划「双路径」声明的低成本正面证据; 默认缓存 raw rows 无竞价列故 real==[], open_gap 恒在 derived)。
4. **VIP 对照夹具竞价键范围**: `_write_strategy_cache_with_auction` 按计划只给 X 行加 `auction_volume`/`auction_amount` 键 (未加 ratio/unmatched), 故 VIP 对照 `auction_columns.derived == ["open_gap"]`; 守卫目的 (证明剥离发生于掩码层) 已达成。
5. **新测试位置**: 3 个 `_project_hub` 测试置于 test_pool_hub.py 快照投影段 (经 `build_pool_hub_snapshot` + `_write_snapshot` 驱动), 与既有快照测试同区, 未新建文件。

## watchlist_touched

`false` — `frontend/src/pages/Watchlist.tsx` (用户未提交改动) 未被 stage/commit; 3 个提交均未包含该文件, 工作树保持其原有修改。

## Pre-existing / Parallel State (not owned by 23-01)

- `frontend/src/pages/Watchlist.tsx` (M): 用户未提交改动, 保留在工作树, 未触碰。
- 23-02 文件 (`DateNavigator.tsx`/`StockListTable.tsx`/`PoolHubPage.tsx`/`frontend/e2e/pool-hub.spec.ts`): 由 23-02 处理, 本计划未触碰。
- 23-01 交付的 precondition 契约已就位: `api.poolDates`/`api.poolHistory` + `QK.poolDates`/`QK.poolHistory` + `PoolHubRow.auction_*` + `PoolHubResponse.available`/`auction_columns` + 后端 `auction_columns` 声明 (hub/history 双路径)。
