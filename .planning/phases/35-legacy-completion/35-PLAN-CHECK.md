# Phase 35 遗留补全与部署验证 — Plan Check Report

**Checker:** PlanCheckerP35 (gsd-plan-checker) · **Date:** 2026-08-06
**Scope:** Goal-backward executability review of the 3 Phase 35 plans (LG-01..05), before execution.
**Artifacts reviewed:** `REQUIREMENTS.md` (LG-01..05), `RESEARCH.md`, `35-01/02/03-PLAN.md`.
**Method:** Live repo anchor spot-checks (read-only; no builds/tests run). Every file/symbol/line the plans name was verified against the current codebase.

---

## Verdict

| Plan | Wave | Depends | Tasks | Files | Estimate (conf) | Verdict |
|------|------|---------|-------|-------|-----------------|---------|
| 35-01 | 1 | — | 3 | 1 new test file (+SUMMARY) | 50k (high) | **EXECUTABLE** — 4 warnings |
| 35-02 | 1 | — | 4 | 2 src + 1 e2e + 3 PNG | 60k (medium) | **EXECUTABLE** — 3 warnings |
| 35-03 | 1 | — | 3 | 3 docs files | 30k (high) | **EXECUTABLE** — 2 warnings |

**Overall: EXECUTABLE — 0 blockers, 9 warnings, 3 notes.** All warnings are fixture-citation/mechanism/command corrections (fake `paused()` source, closure access, smoke cwd + gate arithmetic, snapshot regen scope, diff-gate hazard) — recoverable during execution; fix before starting. Wave 1 all-independent, zero file overlap across plans.

---

## Requirement Coverage (LG-01..05)

| Requirement | Delivered by | Covered? |
|-------------|--------------|----------|
| LG-01 (R13 EOD cache-refresh regression test) | 35-01 T1 (success finally) + T2 (finally-on-error 9aa96ed + EOD frame load) | ✅ |
| LG-02 (CHART-04 stance + tier-2 re-open gate) | 35-03 T1 (features.md 新节) + T3 (D3 cross-ref) | ✅ |
| LG-03 (deploy-verification checklist D1..D8) | 35-03 T2 (copy + header) + T3 (cross-links) | ✅ |
| LG-04 (WATCH-04 batch-add, pure frontend+e2e) | 35-02 T1+T2 (checkbox/selection) + T3 (4 e2e) + T4 (snapshots/build) | ✅ |
| LG-05 (OQ-3 probe offline smoke) | 35-01 T3 (isolated DATA_DIR capture, 2 runs) | ✅ |

No requirement dropped; zero new deps; `Watchlist.tsx` untouched by all three plans (35-02 proves via `git status`).

---

## Executability Spot-Checks

### 35-01 fixtures & symbols (all verified live)

| Plan claim | Actual | Status |
|------------|--------|--------|
| `_pipeline_then_refresh` daily_pipeline.py:1115-1136 — `qs.paused()` wrap (:1127) + `repo.refresh_cache()` in finally (:1135), comment :1116-1118 | `:1115-1136` exact; finally :1131-1135, refresh_cache :1135 | ✅ (name exact — plan names the real symbol) |
| `run_now` :185 `(repo, capset, on_progress)` / `PipelineStageError` :36 / `_get_app_state` :1253 | all exact | ✅ |
| repository.py: refresh_cache :351 → `_refresh_enriched` :461 / `get_enriched_latest_asset` :920 / `enriched_latest_date` :1118 / `_live_agg_baseline_date` :770 | all exact | ✅ |
| `ENRICHED_STORAGE_COLS` indicators/pipeline.py:57-71 (14 cols) | :57 exact | ✅ |
| `_FakeRepo`/`_make_app_state` test_pool_eod_job.py:23-97 (SimpleNamespace repo+strategy_engine; monkeypatch `_get_app_state`) | class :23, helper :49-72+; shape exact | ✅ (minor drift → N-1) |
| fake `qs.paused()` "复制自 test_preopen_scheduling.py:60-84" | **does not exist** — no `paused` anywhere in `backend/tests`; :60-84 holds `_make_app_state_with_quoteservice` (accepts `qs`, never defines the fake) | ⚠️ W-1 |
| real DataStore+KlineRepository tmp seeding test_minute_sync_verify.py:71-110 (`append_daily`/`append_enriched`) | `_seed_daily_lake` :59-91 + DataStore(tmp_path)+`store.db.close()` :87-91+ | ✅ (minor drift → N-1) |
| recap anchors test_auction_recap.py:541-559 / 636-643 / 275-295 | all exist with claimed semantics (EOD change_pct / pre-EOD omission / label discrimination) | ✅ exact |
| OQ-3: probe CLI positional date + DATA_DIR env (:27-28) + offline capture 零网络 (concept_history.py:171-196) + `_DATE_RE` :39 + `ExtConfigStore` ext_data.py:182-215 + ext_data/{gn_ths,hy_ths}/part.parquet 存在 + ext_history 不存在 | all exact; **data lives at repo root `data/`** (backend/data doesn't exist) | ✅ (⚠️ W-3 cwd) |
| pytest invocation `uv run pytest` | uv installed + uv.lock (contains pytest ×4) + .venv pytest 9.0.3 → viable; but 32/33/34 all used `.venv/bin/python -m pytest` (97/96/57 passed on record) | ⚠️ W-5 |

### 35-02 frontend / e2e

| Plan claim | Actual | Status |
|------------|--------|--------|
| playwright projects — `--project=desktop-chromium` | exact name ✅; 5 projects (desktop-chromium / mobile-chromium-320 / visual-desktop / visual-mobile-375 / phase4-fastapi-host) | ✅ |
| webServer auto-start + baseURL | `node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173 --strictPort`, url `http://127.0.0.1:4173`, `reuseExistingServer: !CI`; baseURL = `PHASE1_BASE_URL ?? :4173`; **e2e never touches port 3018** — installShell mocks `**/api/**` (spec :268-309, watchlist empty default) | ✅ (⚠️ W-8 stale-vite reuse; stale 3018 container irrelevant) |
| ALLOWED_RE :628 (button+link loops only, no checkbox loop) | exact — must add `选择\d{6}|全选` + parallel checkbox loop | ✅ |
| WATCH-04 :1237-1254 (batch body set-compare + toast) | exact | ✅ |
| 3 PNG names under `pool-hub.spec.ts-snapshots/` | all 3 present (8 PNGs total) | ✅ |
| `-g "captures visual evidence"` matches snapshot tests | matches **both** backstop tests ('…five UI-SPEC backstop scalars' + '…guest mode backstops') → 8 toHaveScreenshot calls run | ⚠️ W-7 |
| StockListTable props :22-51 / GUEST_COLUMNS :19 / VIP_COLUMNS :20; PoolHubPage handleBatchAdd :112-114, batch button :309-322 (aria-label 批量加自选 :315); api.ts watchlistBatchAdd :2092-2096; useWatchlistBatchAdd dual-key invalidation | all exact; **file is `frontend/src/lib/useSharedMutations.ts`** (plan cites `hooks/`) | ⚠️ W-6 |
| backend batch endpoint watchlist.py:35-40 / services watchlist.py:37-52 `add` | POST /batch actual :55-59 (drift, exists); `add` :37 | ✅ (N-1) |

### 35-03 docs

| Plan claim | Actual | Status |
|------------|--------|--------|
| DEPLOY-CHECKLIST.md exists (D1..D8 + 时序总览 + runbook + Fail-closed 总则) | exists; 8× `## D*` + 时序总览 :9 + 执行顺序 :171 + Fail-closed 总则 ✅ | ✅ |
| docs/ naming kebab (仅 UPSTREAM-SYNC.md 偏离) | exact | ✅ |
| no docs/deploy-verification.md collision | none exists | ✅ |
| features.md 竞价复盘 :217 (新节插入点), intro :3 (config/deployment 链), ARCHITECTURE.md 零 auction 内容, AQ-06/PB-04 在册 | :217 exact (section 217-247); intro :3 ✅; ARCHITECTURE grep 竞价/auction/tier-2/估算 = 0 ✅; AQ-06=1, PB-04=1 | ✅ |
| verify diff gate `sed -n '/^## /,$p'` 零差异 | hazard if added header contains `^## ` lines | ⚠️ W-9 |

---

## Issues

### Blockers (must fix)

None.

### Warnings (should fix before execution)

1. **[fixture_citation] 35-01 T1 — fake `paused()` quote_service citation is fabricated.** `test_preopen_scheduling.py:60-84` contains `_make_app_state_with_quoteservice` + `_preopen_payload`; grep for `paused` across `backend/tests` = **zero matches**. Only production `QuoteService.paused()` (quote_service.py:308-316, `@contextmanager`) exists. Fix: write a self-contained fake qs class in the new test file (a `@contextmanager paused()` that yields — ~6 lines), or reuse the real `QuoteService` instance; cite `quote_service.py:308-316` as the contract source, not the nonexistent test fake.
2. **[testability] 35-01 T1/T2 — `_pipeline_then_refresh` is a closure inside `start_scheduler` (daily_pipeline.py:1103-1140), not a module-level symbol.** Plan says "调 `_pipeline_then_refresh()`" but never states how to obtain it (RESEARCH.md likewise). Fix: monkeypatch `AsyncIOScheduler.add_job` to capture the callable registered for `id="daily_pipeline"` (or extract from `scheduler.get_job('daily_pipeline').func.__closure__`); also handle `preferences.get_pipeline_schedule()/get_instruments_schedule()` (monkeypatch `settings.data_dir` to tmp, mirroring test_minute_sync_verify). Never start the scheduler.
3. **[cwd] 35-01 T3 — `data/ext_data` lives at repo root; backend/data does not exist.** Baseline `sha256sum data/ext_data/…` + `cp -r data/ext_data /tmp/oq3-smoke/` must run from **repo root**, and the verify's trailing `test ! -e data/ext_history` after `cd backend` is **vacuous** (backend/data never exists). Fix: run side-effect checks from repo root (or `test ! -e ../data/ext_history`); keep the real-lake sha256 before/after comparison in the SUMMARY (it's action-step only, not in verify).
4. **[verify_gate] 35-01 T3 — drift.jsonl line-count arithmetic broken.** Action steps run the probe twice (→ 4 lines), then the verify chain runs it a **third** time and asserts `len(lines)==4` → 6, gate fails. Fix: drop the probe re-run from the verify command (assert file state only, e.g. `assert len(lines) >= 4`), or make the verify's single run the second run (action runs once).
5. **[cmd_consistency] 35-01 — `uv run pytest` vs proven `.venv/bin/python -m pytest`.** 32/33/34 all executed `.venv/bin/python -m pytest` (32-VERIFICATION 97 passed, 33: 96, 34: 57 — on record); RESEARCH.md:62 claims "prior phases ran 1686 passed" via `uv run pytest`, unsupported by those records. uv IS installed, `uv.lock` contains pytest (×4), `.venv` has pytest 9.0.3 → `uv run pytest` is viable but the first invocation may re-sync. Fix: either accept `uv run pytest` (functionally fine here) or align all three verifies to `.venv/bin/python -m pytest` for consistency with the executed precedent; don't mix.
6. **[path] 35-02 — `useSharedMutations.ts` is at `frontend/src/lib/`, not `frontend/src/hooks/`** (PoolHubPage.tsx:10 imports `@/lib/useSharedMutations`). Symbol `useWatchlistBatchAdd` :33-42 with dual invalidation `QK.watchlist` + `QK.watchlistEnriched()` :38-39 — exact. Fix: correct the path in read_first/context.
7. **[snapshot_regen] 35-02 T4 — `--update-snapshots -g "captures visual evidence"` regenerates up to 8 PNGs, not 3.** The filter matches both backstop tests; the 5-scalar test also takes `pool-grid-populated`/`pool-empty-zero-hit`/`pool-card-unavailable`, the guest test also takes `pool-guest-grid`/`pool-guest-masked`. "git diff 只含 3 个 VIP PNG" holds only if those 5 rewrite byte-identically (expected — guest zero-control, card grids unaffected — but not guaranteed). Fix: after regen, assert `git diff --stat frontend/e2e/pool-hub.spec.ts-snapshots/` shows exactly the 3 VIP PNGs; any non-VIP diff → `git checkout` it and investigate before committing.
8. **[e2e_server] 35-02 — stale-vite reuse risk; port 3018 is NOT involved.** Backend port 3018 (dev.sh) is never contacted — pool-hub e2e is fully mocked (installShell) and baseURL is 4173, so the stale 3018 container is irrelevant. Real risk: `reuseExistingServer: true` (non-CI) silently reuses a stale vite already on 4173 → old frontend code. Fix: run with `CI=1` (forbids reuse; `--strictPort` then fails loudly if 4173 busy) or check/kill (`lsof -i :4173`, `pkill -f 'vite.*4173'`) before the run.
9. **[diff_gate] 35-03 T2 — added header must avoid `^## `-prefixed lines or the verify diff gate breaks.** The gate diffs `sed -n '/^## /,$p'` of source vs copy; a `## D3 条件标注` heading in the orchestrator-approval header would shift the copy's sed window and produce a non-zero diff. Fix: format header items as `### `, bold, or plain paragraphs (no line starting exactly `## `) before the verbatim body.

### Notes (advisory)

1. Line-anchor drift (symbols all exist; executors re-read by name): watchlist.py POST /batch actual :55-59 (plan :35-40); `concept_history._current_rows` :77 (plan :102-111); probe stdout print :86 (plan :76); `_FakeRepo` block spans 23-103 (plan :23-97); `_seed_daily_lake` starts :59 (plan :71-110).
2. 35-01 T1 internally drops the `_FakeRepo` copy ("复制 `_FakeRepo` 不需要 — 用真实 repo") despite must_haves listing it as fixture source — consistent with the tracer design (real repo is required so `refresh_cache` reads real parquet); no action needed.
3. 35-02 Task 1/2 verify `echo "tsc_exit=$?"` echoes the pipeline's own exit (harmless); `npx tsc -b`/`npm run build` (= tsc -b && vite build) valid; node_modules present.

---

## Dimension Summary

1. Requirement coverage — ✅ PASS (LG-01..05; no leakage) · 2. Task completeness — ✅ PASS (W-1/W-2 fixtures, W-3/W-4 smoke commands) · 3. Dependency correctness — ✅ PASS (wave 1, no deps, acyclic) · 4. Key links — ✅ PASS (pipeline→refresh→repo, checkbox→batch→watchlist, stance→D3, checklist→docs) · 5. Scope sanity — ✅ PASS (3/4/3 tasks; estimates advisory) · 6. Verification derivation — ✅ PASS (W-3/W-4/W-7/W-9 refine gates) · 7. Context compliance — ✅ PASS (zero new deps; Watchlist.tsx zero-touch; honest smoke isolation) · 8. Nyquist — ✅ PASS (every task automated verify; no watch/MISSING gates) · 9. Cross-plan contracts — ✅ PASS (zero file overlap: backend/tests · frontend+PNG · docs/; 35-03 reads StockListTable.tsx read-only) · 10. CLAUDE.md — SKIPPED (no repo CLAUDE.md, same as 28-34) · 11. Research consistency — ✅ PASS (W-1/W-5 correct RESEARCH.md's two unsupported claims).

---

## Recommendation

All three plans are **EXECUTABLE** as-is, 0 blockers. Apply the nine warning fixes before/at start of execution (spec-hint corrections; no structural or dependency changes):

1. 35-01: write the `paused()` fake inline (test_preopen_scheduling.py:60-84 has no such fixture; contract = quote_service.py:308-316).
2. 35-01: specify closure access — capture `daily_pipeline._pipeline_then_refresh` via monkeypatched `AsyncIOScheduler.add_job` (id="daily_pipeline") or `__closure__` extraction.
3. 35-01 T3: run baseline `sha256sum`/`cp` from repo root; fix vacuous `test ! -e data/ext_history` (use `../data/ext_history` or root cwd).
4. 35-01 T3 verify: don't re-run the probe inside the gate (line-count 4 vs 6 mismatch) — assert existing file state.
5. 35-01: pick one pytest invocation — `uv run pytest` is viable here (uv + lock + venv all present), or align to the 32-34-proven `.venv/bin/python -m pytest`; don't mix.
6. 35-02: correct `useSharedMutations.ts` path to `frontend/src/lib/`.
7. 35-02 T4: after `--update-snapshots -g "captures visual evidence"`, verify git diff shows exactly 3 VIP PNGs; revert any non-VIP rewrite.
8. 35-02: run playwright with `CI=1` (or clear port 4173) to avoid stale-vite reuse; stale 3018 container is irrelevant to e2e.
9. 35-03 T2: no `^## ` lines in the added header, or the `sed '/^## /'` diff gate fails.

Proceed to `/gsd-execute-phase 35` (single wave: 35-01 ∥ 35-02 ∥ 35-03 in parallel; execution order 35-01 → 35-02 → 35-03 is convention, not dependency).

---
*Plan-checked: 2026-08-06 — read-only review; no source/plan files modified; no builds/tests run; `Watchlist.tsx` untouched (content never read).*
