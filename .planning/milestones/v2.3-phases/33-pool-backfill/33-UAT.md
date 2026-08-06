# Phase 33 UAT — 股池回填 OQ-1 (Pool Backfill)

**Phase:** 33 · **Requirements:** PB-01..04 · **Date:** 2026-08-06
**Verifier:** `.planning/phases/33-pool-backfill/33-VERIFICATION.md` — **passed** (4/4, 2 deploy-verified)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | Operator backfills pool snapshots from history and sees honest provenance | ✅ passed | REAL run [OBSERVED]: POST /api/pipeline/backfill 2026-07-27..08-05 (8 days) → **13s runtime**, 8 partitions `snapshot_origin=backfill` (part.json point/1/backfill), strategy_cache md5 byte-identical (D2), /pool/dates count=8 backfill_needed=240, idempotent re-run requested:0 |
| UAT-2 | Full-248 run is deterministic and documented for deployment | ✅ passed | docs/features.md:81 runbook: single POST (max_days 500 ≥ 248), job polling/cancel, post-run verify (ls==248, jq origin, backfill_needed==0); **measured anchors** 13s/8d → ~6-7 min full + ~650 MiB (replaces old INFERENCE 20-120min/79-693MiB) |
| UAT-3 | Backfilled dates render in /pool/history with honest concept attribution | ✅ passed | /pool/history 2026-07-27/30/08-05 → 200, snapshot_origin=backfill, concept_attribution=current_snapshot (ext_history absent → no effective/captured keys, CONCEPT-05 no forgery); positive-control unit test flips to as_of_snapshot when partition exists |
| UAT-4 | Sparse-auction-lake interaction is honest, not silent | ✅ passed | Test + real run: derived-column strategies produced rows (bullish 50 / early_star 50 / preopen_quant 43); real-required strategies (allround/fast_grab/t1_flash/intraday_confirm/alpha) = 0 rows — fail-closed, never derived-downgraded; bimodal documented |
| UAT-5 | premarket_results gap honestly recorded, nothing fabricated | ✅ passed | docs/features.md:109 gap paragraph (09:26 job + live 09:15-09:25 dual gates; empty frame → available:false never persisted; sandbox no path); structural lock test_pool_backfill_never_creates_premarket_root; dir absent [OBSERVED] |
| UAT-6 | Zero execution-surface violations; Watchlist.tsx untouched | ✅ passed | POOL-03 E1-E6 green (96 passed batch); git status = exactly `M frontend/src/pages/Watchlist.tsx` |

## Deploy-verified items

- Full-248 operator run on production port 3018 (sandbox: 8-day subset on 3019; stale root-owned 3018 container untouched).
- Real trading-day interplay: EOD-forward ext_history accumulation flipping attribution to as_of_snapshot; 09:26 premarket job under live feed.

## Verdict

**UAT passed** — all 6 acceptance criteria satisfied (2 observed live-run, 4 test-locked). Deploy items labeled deploy-verified.
