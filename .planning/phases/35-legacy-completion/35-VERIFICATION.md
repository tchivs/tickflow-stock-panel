---
phase: 35-legacy-completion
verified: 2026-08-06T23:20:00Z
status: passed
score: 5/5 LG requirements verified (LG-01..05)
behavior_unverified: 0
overrides_applied: 0
human_verification: 3 deploy-verified items (D7 weekly OQ-3 multi-day report, D6 live-trading-day R13 observation, production e2e vs stale container note) — sandbox cannot assert; labeled deploy-verified per standing policy
---

# Phase 35 Verification — 遗留补全与部署验证 (LG-01..05)

**Verifier:** VerifierP35 · **Date:** 2026-08-06 · **Scope:** `.planning/REQUIREMENTS.md` LG-01..05 (Phase 35)
**Method:** Goal-backward, behavior-level — backend batch (21 tests) + frontend e2e spot subset (4 tests) + POOL-03 guard run (36 tests) + LG-by-LG code-level file:line evidence + cross-cutting guard checks + executor SUMMARY cross-checks against re-inspected artifacts (`/tmp/oq3-smoke`, git history, snapshot commit scope). All evidence below is directly observed by this verifier in this pass unless tagged `[OBSERVED live-smoke]` (executor) or `[executor-claimed]`.

## Verdict: **PASSED**

All 5 LG items verified against code + tests. Verifier re-runs: **61 passed, 0 failed** (21 LG-01 batch · 4 WATCH-04 e2e · 36 POOL-03 guard). No needs-fix items. Two non-blocking honesty observations (stale line refs in LG-02 doc; research test-name drift) — recorded in §6, neither affects behavior.

---

## 1. Test runs (verifier duty 1)

```
cd backend && .venv/bin/python -m pytest tests/test_daily_pipeline_refresh.py tests/test_auction_recap.py -x -q
→ 21 passed in 67.42s        (3 new LG-01 tests + 18 recap regression — matches 35-01 SUMMARY claim exactly)

cd frontend && CI=1 npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium -g "WATCH-04"
→ 4 passed (7.0s)            (3 new tests :1276/:1300/:1338 + updated existing :1248; CI=1 fresh vite webServer)

cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py -q
→ 36 passed in 0.57s         (POOL-03 zero-execution AST guard — no regression)
```

Frontend note: executor's full 43/43 run + `npm run build` (tsc -b + vite) were **not re-executed**; verifier spot-ran the 4 WATCH-04 tests (all new/changed e2e coverage) on a fresh CI=1 vite instance — every behavior the executor added is exercised by this subset. Snapshot commit scope re-verified independently (§4).

## 2. LG evidence table (behavior-level, goal-backward)

| Req | Behavior (goal) | Evidence (file:line, this pass) | Verifier result | Verdict |
|-----|------------------|---------------------------------|-----------------|---------|
| **LG-01** | R13 recipe locked deterministically: after 15:30/run-now pipeline, repo latest-day enriched asset holds EOD close; recap 15:40 change_pct computes from EOD; pre-EOD rule honored early. **Zero production edits.** | New `backend/tests/test_daily_pipeline_refresh.py` (258 lines, sole file of commit `f1bcaf2`): (1) `test_pipeline_then_refresh_refreshes_cache_on_success` — stubbed `run_now` (zero network) writes EOD frame then returns `{"ok": True}`; spy on `repo.refresh_cache` asserts finally-refresh on success path, `qs.paused()` enter/exit 1×, post-call `get_enriched_latest_asset("stock")` → `cache_date==T`, `close==[11.5]`, `enriched_latest_date()==T`; (2) `test_pipeline_then_refresh_refreshes_cache_in_finally_on_stage_error` — staged `run_now` seeds then raises `PipelineStageError`; `pytest.raises` wraps (exception still propagates) + cache holds `close==[11.2]` (9aa96ed partial-success semantics); (3) `test_refresh_cache_loads_latest_enriched_eod_frame` — real DataStore+KlineRepository on tmp_path, `refresh_cache(background=False)` genuinely loads parquet: `cache_date==T`, `close==[10.8]` distinct from prior-day 10.5, `enriched_latest_date()==T` (cold-start None asserted first). Production recipe read this pass: `daily_pipeline.py:1115-1136` `_pipeline_then_refresh` — `qs.paused()` wrap (`:1123-1130`), `repo.refresh_cache()` in **finally** (`:1131-1135`, ce5c705/9aa96ed), exception propagates to `_run_tracked`. Recap cross-lock (zero new recap tests): `test_auction_recap.py:541-559` EOD change_pct (0.06/0.01 from EOD frame, never preview 0.051/0.021); `:636-643` pre-EOD omission (`close_fulfill_rate`/`up_rate`/`avg_change_pct` absent + EOD-pending note); `:275-295` `pre_eod` vs `no_auction_lake` label discrimination. Recap file zero-edit: last commit is Phase 31 (`1172dad`), empty diff `f1bcaf2~1..HEAD` for that file. | 21 passed (verifier re-run) · `git show --stat f1bcaf2` = 1 file, 258 insertions · no `app/`/`services/` file in last 8 commits | **PASS** |
| **LG-02** | CHART-04 standing stance documented: 估算 labeling is the norm; re-eval gate (external source with `auction_unmatched_volume` + `auction_virtual_price` → tier-2 gate re-open). | `docs/features.md:247-253` new section `### 🧮 竞价列与派生列（Auction Columns & Derived Estimates）`: (1) standing stance bullet — 估算 anchored to UI titles (verified verbatim this pass at `StockListTable.tsx:359`「由竞价量与历史均量、委托量输入派生的估算值，非真实成交。」, `:361` 组头「派生 · 虚拟成交」, `:375` 「虚拟未匹配金额（元·估算）」) + `api.ts:741-742`「元·估算, 派生」 + server precedents `indicators/pipeline.py:160` and `api/data.py:776` (both verified verbatim this pass) + 诚实缺列 `auction_columns.py:110-118,134-139`; (2) CHART-04 defer bullet (BT-05 branch mutual exclusion: real-column strategies 恒 `branch:"real"`, never derived-downgraded); (3) tier-2 re-eval gate bullet — both input columns → D3 gate re-open, 未提供 → 不伪造、不 0 填. Cross-refs: `features.md:245` (竞价复盘 → new section), `:3` intro link to deploy-verification.md. | All 3 bullets present with verified anchors; section header + cross-refs confirmed | **PASS** |
| **LG-03** | Consolidated 8-item deploy checklist (D1..D8) becomes the operator's manual with verify-where/pass-criteria/owner/sequencing, fail-closed 总则, approval header. | `docs/deploy-verification.md` exists (191 lines). Verifier diff: `diff <(sed -n '/^## /,$p' .planning/research/v2.3-data-depth/DEPLOY-CHECKLIST.md) <(sed -n '/^## /,$p' docs/deploy-verification.md)` → **0 lines** (body verbatim). `grep -c '^## D[1-8]'` = **8**; `Fail-closed 总则` = 1; provenance line `source: .planning/.../DEPLOY-CHECKLIST.md` present; D3 conditional annotation (external auction-source gate, currently unconfigured → fail-closed pass state). Approval header uses `>` blockquotes — no `## `-prefixed header lines (total `^## ` = 10, all from source: 8 D-items + 时序总览 + 执行顺序总结). Cross-link `docs/deployment.md:3` verified. | Body verbatim (0 diff), 8 items, fail-closed preserved, header clean, cross-link live | **PASS** |
| **LG-04** (P2) | WATCH-04 batch-add extension: VIP-only row checkboxes + selection set + batch add to watchlist (pure frontend + e2e, reuses idempotent endpoint, `Watchlist.tsx` untouched). | `StockListTable.tsx`: props `selection`/`onToggleSelection`/`onToggleSelectAll` (`:52-57`); VIP-only checkbox column — header `<th>` under `mode === 'vip'` (`:342-345`, `:382-385`), row checkbox under `!isGuest` with `isGuest = mode === 'guest'` (`:397`, `:410-420`), join key = full-suffix `row.symbol` (same as star); three-state header `aria-checked={allSelected ? 'true' : someSelected ? 'mixed' : 'false'}` (`:255`) + indeterminate visual via ref/effect (`:245-248`); aria-labels `全选` / `选择${row.code}`; `GUEST_COLUMNS`/`VIP_COLUMNS` untouched (`:19-20`). `PoolHubPage.tsx`: `selected: Set<string>` state (`:116`); clear-on-change in **all 5** handlers (strategy `:118`, filter `:122`, clear filter `:126`, date `:130`, watchlistOnly `:134`); `handleBatchAdd` scope = `[...selected].filter(s => filteredRows.some(...))` + empty → early return, no request no toast (`:161-164`); batch button `disabled={batchAdd.isPending \|\| selected.size === 0}` + hidden under watchlistOnly (`:354-359`); `useWatchlistBatchAdd` imported from `@/lib/useSharedMutations` (`:10,:113`) — double-key invalidation QK.watchlist + QK.watchlistEnriched verified (`useSharedMutations.ts:33-41`). e2e `pool-hub.spec.ts`: 3 new tests (`:1276` single-row body+toast, `:1300` select-all+empty-disabled, `:1338` switch-clears-selection) + updated existing (`:1248`); `ALLOWED_RE` includes `选择\d{6}\|全选` (`:629`) + parallel checkbox-name loop (`:636-641`); guest zero-checkbox assertion (`:1176`). Snapshot regen: commit `45e47bc` = **exactly 3 VIP PNGs** (resonance/filter-active/vip-plaintext). **Watchlist.tsx untouched**: sole unstaged change, never in any 35 commit (see §3). | 4 WATCH-04 e2e passed (verifier, CI=1); code-level evidence above; snapshot scope = 3 | **PASS** |
| **LG-05** (P2) | OQ-3 concept-drift probe offline smoke run once on the current ext snapshot; weekly multi-day report stays deploy-gated (D7). | `/tmp/oq3-smoke` re-inspected this pass: `ext_history/{gn_ths,hy_ths}/date=2026-08-06/{part.parquet,manifest.json}` all present (4 files); `_probe/drift.jsonl` = **exactly 4 lines** (2 runs × 2 kinds), fields date/kind/sha256/rows/effective_date, rows=5542 per kind; shas `5d617a5c…df15e` (gn_ths) / `8e70e588…4c95` (hy_ths) match SUMMARY **and** are byte-identical to the real lake (`sha256sum data/ext_data/...` = same hashes, verified this pass); real `data/ext_history` **absent** (probe never ran against the real lake); script offline path + `DATA_DIR` override at `scripts/probe_concept_drift.py:27-28,45-74`, capture at `concept_history.py:171-196`. | 4 drift lines, 4 partition files, real lake byte-identical + ext_history absent — all re-verified | **PASS** |

## 3. Cross-cutting guards (verifier duty 3)

- **POOL-03 zero-execution guard**: `tests/test_pool_hub.py` → **36 passed** (verifier re-run). No 35 commit touches `strategy_cache`/`screener_results` execution paths.
- **Zero new runtime deps**: `git log -8 --name-only` — no `package.json`/`requirements*`/`pyproject`/lockfile in any of the 8 commits (`0ccc61d`..`12d4896`).
- **strategy_cache untouched**: no `app/`/`services/`/`repository` production file appears in any 35 commit (verified via `git log -8 --name-only` grep).
- **Zero production edits**: `f1bcaf2` = 1 new test file only; 35-02 commits = frontend components/page/spec/snapshots only; `3b59da0` = docs only.
- **Watchlist.tsx zero-touch** (duty 5): `git status --short` this pass → `staged 0, unstaged 1, untracked 0`, sole entry `M frontend/src/pages/Watchlist.tsx`. Not read by this verifier (per constraint), never modified/committed by any 35 executor (git log evidence above).

## 4. SUMMARY cross-checks (verifier duty 4)

- **35-01 / LG-05**: `/tmp/oq3-smoke` drift.jsonl = 4 lines (2-run append-only semantics confirmed, not 2) · partition shas stable across both runs (identical sha256 in lines 1-2 vs 3-4) · snapshot artifact count = **4 partition files + 1 drift.jsonl** under `/tmp/oq3-smoke/ext_history` (matches SUMMARY's "4 文件全存在"; "snapshot file count 3" in the verification brief maps to the 3 regenerated VIP PNGs — verified exactly 3 in `45e47bc`). Real lake ext_data shas byte-identical; real `data/ext_history` absent. 21-test count matches verifier re-run exactly.
- **35-02**: 3-new-tests + updated existing WATCH-04 test — all 4 green on verifier's CI=1 run. Snapshot commit = exactly the 3 named VIP PNGs (no guest/other rewrites; PNG byte sizes changed, dimensions stable per SUMMARY's pixel analysis — not re-audited here). `useWatchlistBatchAdd` source + double-key invalidation verified at `useSharedMutations.ts:33-41`.
- **35-03**: diff gate 0 (body verbatim from `## ` onward), 8 D-sections, Fail-closed 总则 = 1, D3 conditional note present, approval header blockquoted (no `## ` lines) — all three claims re-verified by direct commands.

## 5. Human items (deploy-verified — not assertable in sandbox)

1. **D7 — weekly OQ-3 multi-day report**: the smoke validates mechanism only (single forward archive + drift line, append-only). The weekly deliverable — sha256 dedup over ≥5 consecutive trading days, per-day concept add/drop samples, `effective_date` vs upstream publish-lag calibration, optional `--upstream` measurement — requires a real trading-day cadence and stays deploy-gated (D7-1..4).
2. **D6 — live-trading-day R13 observation**: comparing the 15:40 recap Block 3 `avg_change_pct` against a manual EOD calc from `data/kline_daily_enriched/date={T}/part.parquet` (±0.1% tolerance), plus the two-version coexistence (pre-EOD omission vs EOD values), is a real-trading-day observation (D6-1/2); the code semantics are locked hermetically by LG-01's tests.
3. **Production e2e vs stale container note**: D8's optional real-backend browser smoke (VIP star / watchlist-only / batch-add + guest zero-controls) assumes the deployed container matches repo HEAD — a stale container would fail the smoke while e2e (mocked backend) stays green. E2e covers equivalent behavior; the deploy operator must confirm container parity before treating D8 smoke results as authoritative.

## 6. Honesty notes (non-blocking observations)

- **LG-02 doc line-ref drift**: `docs/features.md:251` cites the 估算 UI anchors at `StockListTable.tsx:319,321,335`; this pass they live at **:359,361,375** (35-02's checkbox-column insertion shifted ~40 lines). Title strings are verbatim correct — content-accurate, stale line refs. No behavior impact; flagged for a future doc touch-up.
- **Research test-name drift**: RESEARCH/SUMMARY named the recap EOD test `test_signal_quality_uses_eod_change_pct`; the actual test is `test_signal_quality_family_intersection` (`test_auction_recap.py:532`) and the pre-EOD test is `test_signal_quality_pre_eod_honest` (`:626`). The **cited line ranges (541-559 / 636-643) are accurate** — the EOD change_pct assertion and the pre-EOD omission assertions fall inside them; only the names drifted. The new LG-01 test's docstring cross-links resolve to the correct assertions.
- All evidence above is hermetic `[TEST]` (verifier re-ran) or directly re-inspected artifacts; the OQ-3 smoke outputs are the executor's recorded runs re-verified on disk, not re-executed (W-4 standing policy: no probe re-run to avoid drift.jsonl growth beyond the documented 4 lines).
