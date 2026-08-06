---
phase: 27-premarket-pool
verified: 2026-08-06T08:45:07Z
status: passed
score: 4/4
behavior_unverified: 0
human_verification:
  - test: "真实 09:26 调度 — 部署到带真实 data/ 与真实竞价源的环境后, 观察 daily_pipeline 日志在 09:26 (Asia/Shanghai, 工作日) 触发 premarket_pool_preview job, 且 premarket_results/date={T}/part.json 落盘"
    expected: "09:26 触发后 premarket_results/date={T}/part.json 存在 (payload 含 window=pre_open/provisional:true/degraded/probe); strategy_cache.json 与 screener_results 未被写入"
    why_human: "sandbox 无真实 data/ 与真实竞价源, 无法验证真实 cron 触发; 注册形由 grep 门禁锁死 (test_premarket_job_registered_in_scheduler), 真实触发待部署环境人工确认"
  - test: "盘前视图视觉观感 — 打开股池页「最新」视图, 复核盘前预览 vs EOD 归档的视觉区分 (窗口标注位置/空态样式/degraded 警告样式)"
    expected: "「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」标注清晰; 空态「今日盘前预览尚未生成」非零池伪装; degraded 时「仅派生列 · 竞价数据源未配置」不渲染「竞价数据可用」"
    why_human: "e2e 断言控件存在与文案, 不判定视觉美学 (布局/间距/层次感)"
---

# Phase 27: 盘前股池 (Premarket Pool) Verification Report

**Phase Goal (ROADMAP.md):** A scheduled 09:26 job produces a same-day premarket pool preview (`premarket_results/date={T}/`, independent store) with a complete data frame (`open_gap` computed), honest probe semantics (real auction columns only when today-probe `available`, else degraded), and a frontend view distinct from EOD archives.
**Verified:** 2026-08-06T08:45:07Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | **SC1 / PM-01** — 09:26 job writes premarket preview to independent store; `strategy_cache`/`screener_results` (EOD) untouched | ✓ VERIFIED | `daily_pipeline.py:969-970` `_PREMARKET_JOB_ID = "premarket_pool_preview"` + `_PREMARKET_HOUR, _PREMARKET_MINUTE = 9, 26`; `:1017-1060` `_premarket_pool_preview()` (honest skip: `{"as_of": None, "skipped": "no app state"}` / `{"as_of": None, "skipped": "no data date"}`; only persists when `payload.get("available")`; never calls `write_cache`/`persist_point_snapshot`); `:1145-1153` `scheduler.add_job(lambda: _run_tracked(_premarket_pool_preview, ...), CronTrigger(day_of_week="mon-fri", hour=_PREMARKET_HOUR, minute=_PREMARKET_MINUTE, timezone="Asia/Shanghai"), id=_PREMARKET_JOB_ID, misfire_grace_time=1800, replace_existing=True)`. `premarket_snapshot.py`: `_PREMARKET_ROOT="premarket_results"` (vs `_SNAPSHOT_ROOT="screener_results"`), `_DATE_RE` path-traversal guard, atomic temp+`os.replace` write. Behavioral tests `test_premarket_preview_never_touches_eod_store` (asserts `premarket_results/date=2026-08-06/part.json` exists, `strategy_cache.json` NOT created, `screener_results` NOT created), skip tests, storage roundtrip — **all 13 passed** (ran). |
| 2 | **SC2 / PM-02** — Today frame has `open_gap` (single implementation, no Pass-4 drift); ex-div caliber fixture-covered | ✓ VERIFIED | `pipeline.py:1325-1334` open_gap block in `compute_enriched_today` verbatim-identical to Pass 4 (`:499-507`): `pl.when(prev_close>0).then(open/prev_close-1).otherwise(None).alias("open_gap")` + idempotency guard `if "open_gap" not in df.columns`. `compute_enriched` Pass 4 zero change (git diff `8bdb35e` adds only the today-block). Behavioral tests pass: normal day (10/9.5−1 numerical), ex-div (`adj_factor=0.9` → 8.64/9.0−1 == −0.04), idempotent (0.123 preserved). `open_gap` in `ENRICHED_STORAGE_COLS` (`:66`). Preview service never self-computes open_gap (build_premarket_preview has no open_gap code). |
| 3 | **SC3 / PM-03** — Probe-honest: today-probe `available` → real columns injected at read; else absent + `degraded`/window status; never implies real auction data premarket | ✓ VERIFIED | `premarket_pool.py` `build_premarket_preview` probe_resolver injection point (default `resolve_auction_probe`, signature zero change); `degraded = verdict.get("status") != "available"`; empty results → `available:false`/`degraded:true`. `pool.py` endpoint projects `auction_columns.real==[]` for degraded previews (test asserts). Behavioral tests pass: `test_build_premarket_preview_probe_three_states` (not_configured/fail_closed/available), `test_premarket_api_returns_stored_preview` (real==[] when degraded). Tier-2 real-column read-time injection explicitly NOT implemented — documented Out of Scope (deferred, gated on external real-time auction source; honest `degraded` is the delivered tier-1). |
| 4 | **SC4 / PM-04** — Frontend distinguishes premarket preview from EOD archives (window annotation); DateNavigator lists EOD dates only | ✓ VERIFIED | `api.ts:771` `PremarketPoolResponse extends PoolHubResponse` + `:2164` `poolPremarket()` GET; `queryKeys.ts:48` `QK.poolPremarket = ['pool-premarket']`, NOT in `SSE_INVALIDATE_PREFIXES` (`:221-224`); `useSharedQueries.ts:105` `usePremarketPool` (enabled/staleTime 30s/retry 1); `PoolHubPage.tsx:49-59` `showPremarket`/`showPremarketEmpty` logic (viewingToday ∧ available ∧ window==='pre_open' ∧ !hasTodayEod), `:219-241` window annotation「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」+ degraded「仅派生列 · 竞价数据源未配置」+ empty state「今日盘前预览尚未生成」; `StockListTable.tsx:133-137` degraded prop forces warning branch before `hasReal`. `DateNavigator.tsx` zero change (git log: 0 phase commits touch it). e2e **5 passed** (preview/empty/degraded/15:35-rollback/DateNavigator EOD-only) — ran; `npm run build` green — ran. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Guards Audit (all pass)

| Guard | Assertion | Evidence | Status |
|-------|-----------|----------|--------|
| POOL-03 零执行权 | pool.py 路由 ⊆ GET; 无执行族 import; 无写路径 pattern; 端点无 as_of/concept Query | `test_premarket_api_pool03_ast_guard` passed (in 13-passed batch); `pool.py` diff shows only `@router.get("/premarket")` + imports; 90-regression batch incl. `test_pool_hub` AST guards passed | ✓ |
| 诚实空态 | 预览缺失 → 200 `{available:false, degraded:true}`, 非 404/500, 绝不伪装零池 | `pool.py:137-150` empty-state shape; `test_premarket_api_empty_state_200` passed | ✓ |
| strategy_cache 不污染 | job 绝不 write_cache; 预览只落 premarket_results | `test_premarket_preview_never_touches_eod_store` passed; grep confirms `write_cache`/`persist_point_snapshot` appear only in「绝不调」prohibitions | ✓ |
| EOD 语义不动 | compute_enriched Pass 4 零改动; screener_results 不被盘前写 | git diff `8bdb35e` (pipeline) adds only compute_enriched_today open_gap block; storage-isolation test asserts no `screener_results` dir | ✓ |
| Watchlist.tsx 未触碰 | 用户未提交改动不被覆盖 | git log `8063b95^..e4e8f04 -- frontend/src/pages/Watchlist.tsx` = 0 hits; working tree still shows `M frontend/src/pages/Watchlist.tsx` (user's pre-existing change); phase 27 diff (19 files) excludes Watchlist/DateNavigator | ✓ |
| 零新增运行时依赖 | 无新 pip/npm 依赖 | git diff over phase range for `backend/pyproject.toml`, `backend/requirements*.txt`, `frontend/package.json` = empty | ✓ |
| 提交链 + 分支 | 27-01 (3 task + 1 docs) + 27-02 (3 task + 1 docs); branch gsd/v2.1-planning | Commits verified: `8063b95`/`8bdb35e`/`3cfad7b`/`b5742d7` + `f225393`/`7650de5`/`e4e8f04`/`a13604a`; `git branch --show-current` = `gsd/v2.1-planning` | ✓ |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | ----------- | ------ | ------- |
| `backend/app/services/premarket_snapshot.py` | 独立盘前存储 (D3): `_PREMARKET_ROOT` + `_DATE_RE` + 原子写 + load/list | ✓ VERIFIED | 113 lines; `_PREMARKET_ROOT="premarket_results"`; persist validates as_of via `_DATE_RE.fullmatch` (path-traversal); temp+`os.replace` atomic |
| `backend/app/services/premarket_pool.py` | `build_premarket_preview` (run_all_with_hits + probe verdict + window/pre_open + provisional/degraded) | ✓ VERIFIED | 92 lines; probe_resolver injection; `degraded` from verdict.status; never writes cache; never self-computes open_gap |
| `backend/app/jobs/daily_pipeline.py` | `_premarket_pool_preview` + `_PREMARKET_JOB_ID` + CronTrigger 注册 | ✓ VERIFIED | +64 lines; constants, job, scheduler registration (mon-fri 09:26 Asia/Shanghai, misfire_grace_time=1800) |
| `backend/app/indicators/pipeline.py` | `compute_enriched_today` 补算 open_gap (Pass 4 单一公式) | ✓ VERIFIED | +11 lines; verbatim formula + idempotency guard; Pass 4 zero change |
| `backend/app/api/pool.py` | `GET /premarket` 只读端点 (空态 + 投影 + guest 掩码) | ✓ VERIFIED | +63 lines; POOL-03; empty 200; `_project_hub` projection; `mask_guest_hub` for guests |
| `backend/app/main.py` | `_GUEST_READ_GET_PATHS` 加 `/api/pool/premarket` | ✓ VERIFIED | +1 line (`:785`) |
| `backend/tests/test_premarket_pool.py` | PM-01..03 + POOL-03 AST 守卫 | ✓ VERIFIED | 13 tests, all passed |
| `backend/tests/test_guest_masking.py` | guest 可 GET 且非 GET 不放行 | ✓ VERIFIED | +2 assertions (`:520`, `:529`) |
| `frontend/src/lib/api.ts` | `PremarketPoolResponse` + `poolPremarket()` | ✓ VERIFIED | interface extends PoolHubResponse; GET method |
| `frontend/src/lib/queryKeys.ts` | `QK.poolPremarket` 不入 SSE | ✓ VERIFIED | `:48`, absent from `SSE_INVALIDATE_PREFIXES` |
| `frontend/src/lib/useSharedQueries.ts` | `usePremarketPool` (enabled/staleTime 30s) | ✓ VERIFIED | `:105-111` |
| `frontend/src/pages/PoolHubPage.tsx` | 盘前分支 (showPremarket/showPremarketEmpty/标注/空态/degraded) | ✓ VERIFIED | `:49-59`, `:219-241`, `:332` |
| `frontend/src/components/pool-hub/StockListTable.tsx` | `AuctionColumnStatusBadge` degraded prop | ✓ VERIFIED | `:110`, `:133-137` warning branch before hasReal |
| `frontend/e2e/premarket-pool.spec.ts` | 五用例 mock 四态 | ✓ VERIFIED | 5 passed (desktop), 10 skipped (non-desktop) |
| `docs/features.md` | 「盘前预览」小节 | ✓ VERIFIED | `:36-42` honest annotation; `premarket_results` mentioned; `docs/strategy.md` untouched |

### Key Link Verification

| From | To | Via | Status |
| ---- | --- | --- | ------ |
| `indicators/pipeline.py` → `premarket_pool.py` | open_gap 帧 → 预览消费 (单一实现, 预览不自算) | `build_premarket_preview` calls `run_all_with_hits` (screener path), no open_gap code; open_gap only from `compute_enriched_today` | ✓ WIRED |
| `premarket_pool.py` → `premarket_snapshot.py` | payload → `persist_premarket_snapshot` (独立 root) | job `:1050-1051` `if payload.get("available"): persist_premarket_snapshot(...)` | ✓ WIRED |
| `daily_pipeline.py` → `premarket_pool.py` | `_premarket_pool_preview` → `build_premarket_preview` → persist | `:1044-1051` | ✓ WIRED |
| `api/pool.py` → `premarket_snapshot.py` | GET → `load_premarket_snapshot(cn_today())` | `pool.py:134` | ✓ WIRED |
| `main.py` → `api/pool.py` | guest 白名单 `/api/pool/premarket` | `main.py:785` in `_GUEST_READ_GET_PATHS`; guest GET 200 / non-GET rejected (`test_guest_masking` passed) | ✓ WIRED |
| `api.ts` → `pool.py` endpoint | `poolPremarket()` ↔ GET /api/pool/premarket | `:2164` + e2e mocks match backend contract | ✓ WIRED |
| `PoolHubPage.tsx` → `useSharedQueries.ts` | `usePremarketPool({enabled: viewingToday})` | `PoolHubPage.tsx:50` | ✓ WIRED |
| `PoolHubPage.tsx` → `StockListTable.tsx` | degraded 透传 → badge 强制诚实分支 | `:332` degraded prop | ✓ WIRED |
| `e2e/premarket-pool.spec.ts` → `e2e/pool-hub.spec.ts` | installShell 复制 + 后注册覆盖 | spec copies installShell (`:101-139`), overrides per-test | ✓ WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `build_premarket_preview` results | `svc.run_all_with_hits(as_of)` | `ScreenerService` real strategy path (same code path as EOD/backfill) | Yes — real strategy evaluation over today frame | ✓ FLOWING |
| `GET /api/pool/premarket` payload | `load_premarket_snapshot(data_dir, today)` | `premarket_results/date={T}/part.json` (independent store) | Yes — reads persisted preview; empty-state 200 when missing (honest, not static mock) | ✓ FLOWING |
| `PoolHubPage` premarket view | `premarketQuery.data` | `usePremarketPool` → `api.poolPremarket` → backend endpoint | Yes — real endpoint response drives showPremarket/showPremarketEmpty | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| PM-01/02/03 backend tests | `cd backend && .venv/bin/python -m pytest tests/test_premarket_pool.py -x -q` | 13 passed | ✓ PASS |
| Backend regression (EOD/hub/guest/auction/pipeline) | `.venv/bin/python -m pytest tests/test_pool_eod_job.py tests/test_pool_hub.py tests/test_guest_masking.py tests/test_auction_probe.py tests/test_auction_columns.py tests/test_pipeline_and_monitor_fixes.py -x -q` | 90 passed | ✓ PASS |
| Full backend suite | `.venv/bin/python -m pytest -q` | 1548 passed, 2 skipped | ✓ PASS |
| Frontend build (tsc + vite) | `cd frontend && npm run build` | ✓ built in 11.84s | ✓ PASS |
| e2e premarket | `cd frontend && npx playwright test e2e/premarket-pool.spec.ts` | 5 passed, 10 skipped (non-desktop projects) | ✓ PASS |
| Git audit — Watchlist untouched | `git log 8063b95^..e4e8f04 -- frontend/src/pages/Watchlist.tsx` | 0 commits | ✓ PASS |
| Git audit — commit chain | `git cat-file -t` on 6 task commits | all present | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| PM-01 | 27-01 | 09:26 盘前 job → 独立 premarket_results 存储, 绝不写 strategy_cache/screener_results | ✓ SATISFIED | job + registration + storage isolation tests passed |
| PM-02 | 27-01 | open_gap 补算 (Pass 4 单一公式) + 除权日 fixture | ✓ SATISFIED | compute_enriched_today block + 3 open_gap tests passed |
| PM-03 | 27-01 | probe 诚实 degraded 语义 (tier-1); tier-2 注入 Out of Scope | ✓ SATISFIED (tier-1) | probe three-states + API real==[] tests passed; tier-2 documented defer |
| PM-04 | 27-02 | 前端盘前视图 + 诚实空态 + degraded 标注 + DateNavigator EOD-only | ✓ SATISFIED | build green + e2e 5 passed + DateNavigator zero change |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TBD/FIXME/XXX debt markers in any phase-27 file (scanned) | — | None |
| — | — | No `write_cache`/`persist_point_snapshot` calls in premarket files (only「绝不调」prohibition docstrings) | — | None |
| — | — | `placeholderData` in PoolHubPage.tsx:37/42 is a legitimate React Query option, not a stub | ℹ️ Info | None |
| — | — | Starlette TestClient per-request cookie DeprecationWarning in 2 API tests | ℹ️ Info | Pre-existing repo-wide pattern, harmless |

### Human Verification Required

1. **真实 09:26 调度**
   **Test:** 部署到带真实 data/ 与真实竞价源的环境后, 观察 daily_pipeline 日志在 09:26 (Asia/Shanghai, 工作日) 触发 `premarket_pool_preview` job, 且 `premarket_results/date={T}/part.json` 落盘。
   **Expected:** 09:26 触发后 `premarket_results/date={T}/part.json` 存在 (payload 含 window=pre_open / provisional:true / degraded / probe); `strategy_cache.json` 与 `screener_results` 未被写入。
   **Why human:** sandbox 无真实 data/ 与真实竞价源, 无法验证真实 cron 触发; 注册形由 grep 门禁锁死 (`test_premarket_job_registered_in_scheduler`), 真实触发待部署环境人工确认。

2. **盘前视图视觉观感**
   **Test:** 打开股池页「最新」视图, 复核盘前预览 vs EOD 归档的视觉区分 (窗口标注位置/空态样式/degraded 警告样式)。
   **Expected:** 「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」标注清晰; 空态「今日盘前预览尚未生成」非零池伪装; degraded 时「仅派生列 · 竞价数据源未配置」, 不渲染「竞价数据可用」。
   **Why human:** e2e 断言控件存在与文案, 不判定视觉美学 (布局/间距/层次感)。

### Gaps Summary

无 gaps。全部 4 条 roadmap 成功标准均以行为级测试证据 VERIFIED (后端 1548 全绿、前端 build 绿、e2e 5 绿); 守卫审计 (POOL-03 零执行 / 诚实空态 / strategy_cache 不污染 / EOD 语义不动 / Watchlist.tsx 未触碰 / 零新增依赖 / 提交链完整) 全部通过。tier-2 盘前真实竞价列注入为显式 Out of Scope (依赖外部实时竞价源), 诚实 degraded 降级是本期交付。

---

_Verified: 2026-08-06T08:45:07Z_
_Verifier: Claude (gsd-verifier)_
