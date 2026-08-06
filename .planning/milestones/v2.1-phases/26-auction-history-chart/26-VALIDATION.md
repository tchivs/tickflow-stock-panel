---
phase: 26
slug: auction-history-chart
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-06
---

# Phase 26 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Phase 26 = 历史竞价图 + 派生列复活 (CHART-01/02/03): 只读竞价历史聚合 API(末行语义)+ ECharts 双轴图 + 湖摄入保留委托量输入列(复活派生未匹配金额)。两计划 Wave 1 并行、文件零重叠(26-01 = 后端 API + 写路径扩展;26-02 = 前端图表 + e2e)。零新增运行时依赖(echarts in-tree)。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Backend runner | `cd backend && .venv/bin/python -m pytest <file> -x -q` |
| Frontend build | `cd frontend && npm run build`（tsc + vite） |
| E2E runner | `cd frontend && npx playwright test e2e/auction-history.spec.ts`（新独立 spec，复用 pool-hub installShell 模式为复制） |
| Hermetic | repo_env + `_write_auction_partition` + FakeAuctionProvider；e2e mock `/api/kline/auction/history` 三态 |
| Guest gate | auction 列量/价敏感 → guest 200 `available:false` 空态（镜像 guest_masking.py:31-37/52-53） |

---

## Nyquist Coverage Map

| Nyquist | Coverage | Evidence |
|---------|----------|----------|
| 8a (automated verify per task) | ✅ 4/4 tasks | 26-01 T1 `test_auction_history.py`、T2 `test_auction_sync.py + test_auction_columns.py + test_auction_strategy_family.py + test_auction_probe.py`；26-02 T1 build + 结构 grep、T2 `npx playwright test e2e/auction-history.spec.ts` |
| 8b (no watch/delays) | ✅ | 单元级 hermetic；e2e mock 三态无真实网络 |
| 8c (wave coverage) | ✅ | Wave 1: 26-01 2/2；Wave 2: 26-02 2/2 |
| 8d (no MISSING refs) | ✅ | 全部 `<verify>` 经 plan-checker 核验（round 1: 26-01 EXECUTABLE; 26-02 B1/B2 已在计划内修订; W1 已修订） |

---

## CHART-01 — 历史竞价聚合只读 API

**诚实铁律**: 末行语义（每 symbol 每日 max-datetime 行，09:25 最终撮合）+ row_count/min_datetime/max_datetime 粒度标注；空湖 200 `available:false`（非 404/500/0 填）；GET-only 零执行权；严禁复制 kline.get_daily 空库 live-fetch 兜底。

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 多日聚合末行 | `test_auction_history_last_row` | 每 symbol/日取 max-datetime 行；row_count/min/max_datetime 正确 |
| 空湖 available:false | `test_auction_history_empty_available_false` | 200 非 404，`{available:false, rows:[]}` |
| 参数校验 | `test_auction_history_bad_params` | 缺 symbol → 400；days 非法 → 400 |
| guest 掩码 | `test_auction_history_guest_masked` | guest 200 `{available:false, mode:'guest', rows:[]}` |
| GET-only 守卫 | AST 守卫测试 | auction_history.py 无执行词/POST |
| 白名单 | main.py `_GUEST_READ_GET_PATHS` | `/api/kline/auction/history` 已登记（guest 可达空态） |

## CHART-03 — 湖摄入保留委托量输入列

**诚实铁律**: CANONICAL_AUCTION_COLS=4 不变 + OPTIONAL_AUCTION_COLS 新增；源不提供可选列 → 列缺席（向后兼容）；派生 `auction_unmatched_amount` = 乘积（估算），与真实列永不相加；读路径派生零改动。

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 写湖 6 列 | `test_sync_writes_partition_with_optional_cols` | 分区列 = 4+2，末行值保留 |
| 旧 4 列 + 新 6 列 merge | `test_sync_partition_merge_old_four_plus_new_six` | diagonal_relaxed 并集不 SchemaError；旧行可选列缺席（诚实）；无 .tmp |
| 缺输入列仍 4 列 | `test_sync_without_optional_cols_stays_four_cols` | 向后兼容 |
| 读路径派生激活 | `test_attach_derives_unmatched_amount_from_partition_inputs` | 分区含输入列 → auction_unmatched_amount==5000*8.4（W1 修订：不断言 ratio） |
| 缺输入列诚实缺列 | `test_attach_no_unmatched_when_inputs_absent` | 无 auction_unmatched_amount（不 0 填） |
| 纪律回归 | `test_unmatched_proxy_never_mixed_with_real` | 派生与真实列永不求和/混排 |

## CHART-02 — 前端 ECharts 双轴图

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 有数据 → 图渲染 | `auction-history.spec.ts` Test 1 | 打开弹窗（B1 修订：/screener 打开，/pool-hub 不挂载）→ 点「竞价历史」→ 画布 + 轴单位「股」/「元」+ 窗口标注「09:15-09:25」 |
| available:false 空态 | Test 2 | 空态「无历史竞价数据」；无画布 |
| probe 非 available | Test 3 | 空态 + 降级标注「（数据源未配置）」 |
| guest 零泄露 | Test 4 | 空态（量/价零泄露） |
| 集成 | build + 结构 grep | StockPreviewDialog 第三 toggle + StockPanel showAuction prop + AuctionHistoryChart 双轴 |
| 前置门 | precondition grep | 端点契约（B2 修订：拆分 grep — 白名单 ≥1 + include_router 命中） |

---

## 平台护栏

| Guard | Assertion |
|-------|-----------|
| POOL-03 零执行权 | auction_history.py GET-only + AST 守卫；26-01 T1 |
| 诚实空态 | available:false 200 非 404；不 0 填 |
| 派生 vs 真实隔离 | 永不相加；schema 描述带「估算」标注 |
| guest 掩码 | 量/价敏感列 guest 空态 |
| Watchlist.tsx | 不触碰（git 审计） |

---

## Manual / Post-Verify Items

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ECharts 图真实渲染观感（双轴柱/线、窗口标注位置） | CHART-02 | 视觉快照/交互观感需人眼；e2e 断言画布存在但不判定美学 | `cd frontend && npx playwright test e2e/auction-history.spec.ts`（mock 有数据三态）后人工打开 /screener 个股弹窗复核图渲染 |

*If none: "All phase behaviors have automated verification."*
