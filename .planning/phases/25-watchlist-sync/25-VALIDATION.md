---
phase: 25
slug: watchlist-sync
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-06
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Phase 25 = 自选股联动 (WATCH-01/02/03/04, 纯前端): 池钻取行自选星标 + 「只看自选」过滤 + 共享 QK.watchlist 缓存一致 + (P2) 批量加可见行。两计划 Wave 1 并行、文件零重叠（25-01 = 全部前端源码；25-02 = e2e 契约更新 + WATCH e2e + docs）。零后端改动、零新增 npm 依赖。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Frontend build | `cd frontend && npm run build`（tsc + vite） |
| E2E runner | `cd frontend && npx playwright test pool-hub.spec.ts`（Playwright，无 vitest） |
| Backend smoke | `cd backend && .venv/bin/python -m pytest <file> -x -q`（本 phase 不动后端，仅可选 smoke） |
| Hermetic e2e | installShell mock `/api/watchlist` 默认 `{symbols: []}`；具体用例后注册覆盖（后注册优先） |
| Guest gate | 前端不自行 masking；VIP 明文 / guest 掩码由后端 DTO 决定（GUEST-01 服务端-权威） |

---

## Nyquist Coverage Map

| Nyquist | Coverage | Evidence |
|---------|----------|----------|
| 8a (automated verify per task) | ✅ 6/6 tasks | 25-01 T1-T3 build + 结构 grep 门；25-02 T1-T3 playwright pool-hub.spec.ts + docs grep |
| 8b (no E2E/watch/delays) | ⚠️ e2e 是 Playwright 既有套件（项目先例 Phase 23 同款）；无 watch/delays | pool-hub.spec.ts 既有 SC1-SC4 风格延续 |
| 8c (wave coverage) | ✅ | Wave 1: 25-01 3/3；Wave 2: 25-02 3/3 |
| 8d (no MISSING refs) | ✅ | 全部 `<verify>` 命令经 plan-checker 核验（round 1: 25-01 EXECUTABLE, 25-02 NOT EXECUTABLE → B1 已在计划内修订） |

---

## WATCH-01 — 行级自选星标 + 切换（VIP）

**诚实铁律**: guest 会话零控件零查询（逐像素不变）；watchlist 查询双门控 `enabled: !!data && mode==='vip'`（防 PoolHubPage mode 回退 vip → guest 401 跳登录）；匹配键 = 全后缀 symbol 精确 Set.has。

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| VIP 行星标渲染 | `WATCH-01 星标渲染` e2e | 300750.SZ 行 aria-label=移出自选、600519.SH=加入自选 |
| toggle 写请求 + 翻转 | `WATCH-01 toggle` e2e | 点 600519 星标 → POST /api/watchlist body symbol=600519.SH → 翻转 + 二次 GET（缓存失效） |
| guest 零控件零查询 | `WATCH-01 guest` e2e | 捕获数组不含 /api/watchlist；main 内无 加入自选/移出自选/switch |
| 结构门 | 25-01 grep | StockListTable 星标 props 仅 VIP 分支渲染 |

## WATCH-02 — 「只看自选」过滤（VIP）

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 收窄 + total 权威 | `WATCH-02 只看自选` e2e | 表格仅剩自选行，footer「筛选后 N 只 / 共 M 只」 |
| 诚实空态 | `WATCH-02 空态` e2e | 无交集 →「自选清单中无该策略个股」 |
| 历史同构 | `WATCH-02 历史` e2e | 切历史日期后开关保持生效 |
| 偏好存储 | 结构 grep | storage.poolWatchlistOnly（UI 偏好，非自选清单） |

## WATCH-03 — 自选集合一致性

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 共享缓存失效 | WATCH-01 toggle 二次 GET 断言 | invalidateQueries(QK.watchlist) 触发跨页一致 |
| 匹配键契约 | 结构 grep + WATCH-01 断言 | 全后缀 symbol 精确 Set.has（非模糊） |

## WATCH-04 — 批量加可见行（P2）

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 批量 body = 可见行 | `WATCH-04 批量` e2e | POST /api/watchlist/batch body.symbols 恰为可见行（filteredRows，display_limit 内） |
| 成功 toast | `WATCH-04 toast` e2e | 「已添加 N 只到自选」 |

---

## POOL-03 e2e 守卫（必须随新控件同步）

| Guard | Assertion | 25-02 更新 |
|-------|-----------|------------|
| affordances 白名单 | ALLOWED_RE（pool-hub.spec.ts:620-626）遍历 main 内所有按钮 | 加 `只看自选|批量加自选|加入自选|移出自选`；icon-only 必须 aria-label |
| no-mutating 守卫 | 「pool page never issues a mutating request」 | VIP 放行 watchlist 写；非 watchlist 写仍为零；guest 保持零 non-GET |
| installShell mock | 默认 `/api/watchlist` → `{symbols: []}` | 追加到 installShell 末尾；具体用例后注册覆盖 |
| VIP 视觉快照 | backstop（B1 修订） | 表格区 4 张重生成（resonance/filter-active/empty-zero-hit/vip-plaintext）；零 diff 集 4 张（grid-populated/card-unavailable/guest-masked/guest-grid） |

---

## Manual / Post-Verify Items

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| VIP 快照重生成后人工复核（仅星标/开关/批量按钮增量，无布局漂移） | WATCH-01/02 | 视觉快照语义需人眼确认；Playwright --update-snapshots 只生成不判定 | `cd frontend && npx playwright test pool-hub.spec.ts -g "captures visual evidence" --project=desktop-chromium --update-snapshots` 后复核 4 张表格区 PNG；若意外元素，回查 25-01 源码而非接受快照 |

*If none: "All phase behaviors have automated verification."*
