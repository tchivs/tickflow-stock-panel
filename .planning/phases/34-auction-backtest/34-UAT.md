# Phase 34 UAT — 竞价回测解锁 (BT-07 Full Auction Backtest)

**Phase:** 34 · **Requirements:** BT-07..10 · **Date:** 2026-08-06
**Verifier:** `.planning/phases/34-auction-backtest/34-VERIFICATION.md` — **passed** (4/4, 2 deploy-verified)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | Full auction backtest unlocks and runs on the real lake | ✅ passed | REAL runs [OBSERVED]: Run A 4 EOD strategies × 248 days × full market → **329,087 hit rows in 4s** (replaces 1-3min estimate); Run B 4 real-column strategies × 248 days × 2 symbols → 12 rows in 3s; branch exclusivity group_by-verified (A 4/4 eod, B 4/4 real, no derived downgrade) |
| UAT-2 | Forward outcomes are correct, not fabricated | ✅ passed | Verifier recomputed 3 sampled hits from raw kline_daily + global calendar: +0.002648/+0.011474/−0.001757 etc. **exact to 9dp**; missing outcomes counted (Run A: bullish missing=219, early_star missing=1733) never filled |
| UAT-3 | Validation report activates with honest coverage | ✅ passed | data_gate:available at 248∩248 (gate zero-change); coverage.symbols {auction_symbol_count=2, enriched=5537, ratio=0.04%, rows 496/1373176} + per-strategy n_symbols_covered/n_symbols_hit; real branch never derived-downgraded |
| UAT-4 | Operator can run + query backtests read-only | ✅ passed | CLI `scripts/auction_backtest.py` (--strategies/--range/--symbols, idempotent reused, honest terminal summary); GET /api/research/backtest list + /{run_id} detail (predicate pushdown, vectorbt flat files honestly skipped, empty lake 200, 400/404 RESEARCH_BACKTEST) |
| UAT-5 | Zero execution-surface violations; strategy_cache untouched | ✅ passed | AST guard 7/7 (GET-only, no execution imports, E2 root isolation backtest_results only); 57-test batch + pool_hub E1-E6 green; strategy_cache untouched |
| UAT-6 | Minute limitation honestly annotated | ✅ passed | minute_confirm:'not_applied' per row + manifest minute_note (kline_minute CLOSED, auction_intraday_confirm 恒空); docs/features.md:82 |

## Deploy-verified items

- Full-universe real-branch backtest: requires the 3-5.5h operator auction backfill (Phase 32 runbook) to lift symbol coverage from 2 → 5537; today honest 0.04%.
- Live server query smoke on production port (sandbox verified via hermetic API tests + CLI).

## Verdict

**UAT passed** — all 6 acceptance criteria satisfied (3 observed real-run, 3 test-locked). Deploy items labeled deploy-verified.
