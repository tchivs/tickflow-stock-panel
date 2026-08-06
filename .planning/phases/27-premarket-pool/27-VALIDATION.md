---
phase: 27
slug: premarket-pool
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-06
---

# Phase 27 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Phase 27 = 盘前股池 (PM-01/02/03/04): 09:26 盘前预览 job + 独立存储 + open_gap 补算 + probe 诚实 degraded + 前端盘前视图。两计划 Wave 1 并行、文件零重叠（27-01 = 后端 job/存储/open_gap/端点/白名单；27-02 = 前端视图 + e2e）。零新增运行时依赖。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Backend runner | `cd backend && .venv/bin/python -m pytest <file> -x -q` |
| Frontend build | `cd frontend && npm run build`（tsc + vite） |
| E2E runner | `cd frontend && npx playwright test e2e/premarket-pool.spec.ts`（新独立 spec，复用 pool-hub installShell 模式为复制） |
| Hermetic | fixture 湖 + 模拟盘前调度（不启真 cron）；e2e mock `/api/pool/premarket` 三态 |
| Guest gate | 量/价敏感 → guest 空态 + mask_guest_hub（镜像 guest_masking.py） |

---

## Nyquist Coverage Map

| Nyquist | Coverage | Evidence |
|---------|----------|----------|
| 8a (automated verify per task) | ✅ 6/6 tasks | 27-01 T1 `test_premarket_pool.py -k job/storage`、T2 `-k open_gap` + 回归、T3 `-k api` + guest/hub；27-02 T1-T3 build + `npx playwright test e2e/premarket-pool.spec.ts` |
| 8b (no watch/delays) | ✅ | 单元级 hermetic；e2e mock 无真实网络 |
| 8c (wave coverage) | ✅ | Wave 1: 27-01 3/3；Wave 2: 27-02 3/3 |
| 8d (no MISSING refs) | ✅ | 全部 `<verify>` 经 plan-checker 核验（round 1: B-1 VALIDATION 已补; W-1/W-2/W-3 已在计划内修订） |

---

## PM-01 — 盘前预览 job + 独立存储

**诚实铁律**: 09:26 mon-fri Asia/Shanghai 调度（_run_tracked 单飞）；只写 `premarket_results/date={T}/part.json`，**绝不**写 `strategy_cache.json`（指针污染）/`screener_results`（EOD 语义）；payload 含 `window:pre_open`/`computed_at`/`provisional:true`/`degraded`/`probe`/`results`。

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 注册形锁死 | `test_premarket_job_registered_in_scheduler` | `_PREMARKET_JOB_ID` + `_PREMARKET_HOUR,MINUTE=9,26` + `hour=_PREMARKET_HOUR,minute=_PREMARKET_MINUTE` + `_run_tracked` + `timezone="Asia/Shanghai"`（W-2 修订：断常量与 tokens，不断字面） |
| 存储隔离 | `test_premarket_storage_isolation` | job 后 premarket_results 存在；strategy_cache.json 不被创建/改动；screener_results 不被创建 |
| 诚实 skip | `test_premarket_skip_no_data` | 无数据日 → `{as_of:None, skipped:"no data date"}` 无新文件 |
| 原子写 + 幂等 | `test_premarket_snapshot_storage_roundtrip_and_list` | 同 payload 读回；list ISO desc；非法 as_of → ValueError/None |

## PM-02 — open_gap 补算（单一实现零漂移）

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 正常日数值 | `test_compute_enriched_today_open_gap_normal_day` | open_gap == open/prev_close−1；prev_close≤0 → None |
| 除权日口径 | `test_compute_enriched_today_open_gap_exdiv_caliber` | adj_factor=0.9 对齐后 prev_close 口径与 EOD Pass 4 一致 |
| 幂等/EOD 回归 | `test_compute_enriched_today_open_gap_idempotent` | 已含 open_gap 不覆盖；compute_enriched Pass 4 零改动 |
| 单一公式 | 结构门 | 补算块注释引用 Pass 4 L499-507（W-3 修订：结构门 = `grep -c compute_enriched_today` ≥1；pytest -k open_gap 为真实门） |

## PM-03 — probe 诚实 degraded

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| degraded 透传 | `test_premarket_api_degraded` | 无今日竞价 → `degraded:true` + `auction_columns.real==[]`（量/价零泄露） |
| probe 三态 | `test_premarket_probe_states` | available / not_configured / fail_closed 透传 probe 对象 |
| 读时注入边界 | 结构门 + 测试 | tier-2 读时源注入 gate 在 today-probe available，本期不实现（D6） |

## PM-04 — 前端盘前视图

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 端点 + 白名单 | `test_premarket_api_*` | GET /api/pool/premarket 只读 + guest 白名单（main.py）；guest 空态 + POST 不放行 |
| 空态 200 | Test 1 | 无快照 → 200 `{available:false, ...}`（非 404/500） |
| 有预览投影 | Test 2 | available:true + window/provisional/degraded/probe 透传 + total 权威 + auction_columns 声明 |
| 前端视图 | e2e premarket-pool.spec.ts | 盘前入口 + 窗口标注（pre-open 预览 vs post-close）+ 诚实空态 + AuctionColumnStatusBadge preopen 分支 |
| DateNavigator EOD-only | e2e + 结构门 | 盘前日绝不列 EOD dates（PIT-5） |

---

## 平台护栏

| Guard | Assertion |
|-------|-----------|
| POOL-03 零执行权 | pool.py 路由 ⊆ GET；import 无执行族 token；无写路径 pattern（AST 守卫） |
| strategy_cache 不污染 | 回填/盘前绝不 write_cache；存储隔离测试 |
| EOD 语义不动 | screener_results 不被盘前写；compute_enriched Pass 4 零改动 |
| 诚实空态 | available:false 200 非 404；不 0 填 |
| guest 掩码 | 量/价敏感列 guest 空态 + 顶层剥离 |
| Watchlist.tsx | 不触碰（git 审计） |

---

## Manual / Post-Verify Items

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 盘前视图视觉观感（pre-open 标注、预览 vs EOD 区分） | PM-04 | UI 渲染观感需人眼；e2e 断言控件存在不判定美学 | `cd frontend && npx playwright test e2e/premarket-pool.spec.ts` 后人工打开盘前视图复核窗口标注与空态 |
| 真实 09:26 调度（真实数据环境 cron 触发） | PM-01 | sandbox 无真实 data/ 与真实竞价源；调度用注册 grep 锁死，真实触发待部署 | 部署后观察 daily_pipeline 日志 09:26 `premarket_pool_preview` 触发 |

*If none: "All phase behaviors have automated verification."*
