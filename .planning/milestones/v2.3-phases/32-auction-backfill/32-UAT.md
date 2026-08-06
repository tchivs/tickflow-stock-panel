# Phase 32 UAT — 竞价历史回填 (Auction History Backfill)

**Phase:** 32 · **Requirements:** AQ-01..06 · **Date:** 2026-08-06
**Verifier:** `.planning/phases/32-auction-backfill/32-VERIFICATION.md` — **passed** (6/6, 0 human-needed)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | Operator can backfill auction history for a symbol subset and see real partitions in the lake | ✅ passed | Live smoke [OBSERVED]: POST /api/kline/auction/backfill {000001.SZ,000002.SZ} → 496 rows / 248 date-partitions written (origin=backfill), columns [symbol,datetime,auction_volume,auction_amount,auction_virtual_price]; re-run idempotent (496 stays 496); cancel via /api/pipeline/jobs/{id}/cancel → '用户手动取消' |
| UAT-2 | Auction data is real, not fabricated — cross-validated against the governed daily-K | ✅ passed | test_auction_virtual_price_equals_daily_open: 3 dates real kline_daily open (read-only) == written virtual price (mock upstream); live MCP probe resolved `available` (source xyz) [OBSERVED 2026-08-06T16:52Z] |
| UAT-3 | Honest gates hold: kline_daily-aligned dates only; per-symbol failures recorded; source-down → 0 writes; unmatched-volume column never written | ✅ passed | test_auction_backfill.py 23 + test_auction_backfill_honesty.py 10 (ledger/origin/bj/empty/fail-closed shape) — all green; lake col scan confirms no unmatched/origin col [OBSERVED] |
| UAT-4 | EOD live path unchanged and preference-gated (no surprise scheduled behavior) | ✅ passed | daily_pipeline.py:695-706 double gate (auction_sync_enabled default False + probe); sync_and_persist_auction routes through extracted write_auction_partitions (single write path); test_auction_sync.py 17 green |
| UAT-5 | Minute-history backfill honestly closed, documented with evidence | ✅ passed | docs/features.md 竞价历史回填 section: AQ-06 minute CLOSED note + AUCTION-BACKFILL.md §4/§6 pointer + operator runbook (rpm 1..60, full 5537 ≈ 3-5.5h, 429 auto-backoff, subset, idempotent rerun) |
| UAT-6 | Zero execution-surface violations; strategy_cache untouched; user Watchlist.tsx untouched | ✅ passed | POOL-03 AST guards green (router AST guard, no strategy_cache references, auction_history GET-only); git status = exactly `M frontend/src/pages/Watchlist.tsx` |

## Deploy-verified items (real trading day / full-scale; not assertable in sandbox)

- Full-universe operator run (~5537 symbols, 3-5.5h): sandbox verified 2-symbol smoke + hermetic subsets only; sustained 429 cadence + long-job polling on real runs.
- Live MCP stability over a multi-hour run; BJ-symbol empty_response behavior (333 .BJ symbols) on first full run.
- EOD live unlock: operator sets `auction_sync_enabled=True` and observes the 09:15-09:25 EOD fill on the next trading day.
- R3 probe latency: resolve_auction_probe() = 1 live HTTP per call; short-TTL cache deferred (documented in features.md).

## Verdict

**UAT passed** — all 6 acceptance criteria satisfied (2 observed live-smoke, 4 test-locked). Deploy items labeled deploy-verified per standing policy.
