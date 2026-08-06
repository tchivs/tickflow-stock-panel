# Phase 35 UAT — 遗留补全与部署验证 (Legacy Completion & Deploy Verification)

**Phase:** 35 · **Requirements:** LG-01..05 · **Date:** 2026-08-06
**Verifier:** `.planning/phases/35-legacy-completion/35-VERIFICATION.md` — **passed** (5/5, 3 deploy-verified)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | R13 EOD-cache semantics locked by regression tests | ✅ passed | test_daily_pipeline_refresh.py (3 tests): finally-refresh on success + stage-error (exception propagates, cache still refreshed — daily_pipeline.py:1131-1135), latest-enriched EOD frame loads (close 11.5/11.2/10.8 exact); recap cross-lock 18 tests zero-edit (EOD change_pct @15:40, pre-EOD omission @15:10) |
| UAT-2 | CHART-04 stance documented (估算 standing, tier-2 re-eval gate) | ✅ passed | docs/features.md:247-253: 估算 labels live (StockListTable + api.ts anchors verified), BT-05 branch exclusivity, re-eval gate (external source providing unmatched_volume/virtual_price → D3) |
| UAT-3 | Deploy verification checklist = operator manual | ✅ passed | docs/deploy-verification.md = verbatim DEPLOY-CHECKLIST (diff from '## ' = 0 lines), 8 items D1..D8 + fail-closed 总则 + approval header; deployment.md cross-link live |
| UAT-4 | WATCH-04 batch-add works (VIP), guest masked, e2e green | ✅ passed | Checkbox column VIP-only (aria-checked three-state, indeterminate), selection clear-on-change (5 handlers), batch scope=selected∩filtered (empty → no request); 43/43 pool-hub e2e (CI=1) + 3 new tests + ALLOWED_RE; exactly 3 VIP PNGs regenerated |
| UAT-5 | OQ-3 probe smoke honest + deploy-gated weekly report documented | ✅ passed | /tmp/oq3-smoke: 2 runs → 4 drift lines append-only, shas byte-identical to real lake, real ext_history absent, offline zero network; weekly ≥5-day report deploy-gated (D7) |
| UAT-6 | Watchlist.tsx untouched; zero new deps; POOL-03 intact | ✅ passed | git status = exactly `M frontend/src/pages/Watchlist.tsx`; no dep-file in any 35 commit; test_pool_hub 36 passed |

## Deploy-verified items

- D7 weekly OQ-3 multi-day drift report (mechanism smoke only in sandbox).
- D6 live-trading-day R13 observation (15:40 recap vs manual EOD calc; pre-EOD/EOD coexistence).
- D8 production e2e requires deployed container parity with repo HEAD (stale 3018 container noted).

## Verdict

**UAT passed** — all 6 acceptance criteria satisfied (5 test/direct-observed, 1 docs-verified). Deploy items labeled deploy-verified.
