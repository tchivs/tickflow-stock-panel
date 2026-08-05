# Deferred Items — Phase 21 (竞价策略族)

## Known Failures / Flakes (pre-existing, unrelated to Phase 21)

| Item | Status | Notes |
|------|--------|-------|
| `backend/tests/advanced/test_production_host.py::test_spawned_governed_backtest_completes_split_evidence_within_budget` | pre-existing fail | Fails identically at Phase 20 HEAD (cb6a30b) — verified via worktree. `strategy filter_fn failed: unable to find column "momentum_20d"` in governed backtest fixture scope (`bullish_alignment` preset references momentum_20d; governed fixture panel lacks the derived column → `eligible_buy_count == 0` → `resource_limited`). NOT a Phase 21 regression (Phase 21 touches auction/screener strategy files only; zero governed_runner/backtest touchpoints). |
| `backend/tests/portfolio/test_optimizer.py::test_nan_covariance_records_failed_run` | flaky | NaN covariance floating-point; passes in isolation, intermittently fails in full suite (Phase 20 record). Still tracked. |

## Deferred to Later Phases

| Category | Item | Phase |
|----------|------|-------|
| Feature | Frontend API visualization of strategy META fields (time_window/evaluation_time/requires_auction_data) | Phase 23 (frontend) |
| Feature | 竞价列 UI 展示 (real vs derived, 股/元 units, probe/empty honesty) | Phase 23 (frontend) |
