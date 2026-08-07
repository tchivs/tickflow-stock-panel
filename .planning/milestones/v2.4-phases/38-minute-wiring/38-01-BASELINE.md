# 38-01 Anchor Baseline (pre-wiring) — durable pass-count record

**Purpose**: durable baseline for 38-02 T5 byte-identical proof ("复跑同命令同通过数"). 38-02 MUST rerun the exact commands below after wiring main.py + governed_runner.py and compare pass counts.

**Recorded**: 2026-08-07 (ExecutorP3801, wave-1, pre-wiring). Environment: `cd backend && .venv/bin/python -m pytest <cmd> -q`.

## Baseline commands and pass counts (TOTAL = 16 passed)

| # | Command | Passed | Collected tests |
|---|---|---|---|
| 1 | `pytest tests/test_auction_strategy_family.py -k "short_circuit or truncation or time_window or missing_minute" -q` | 4 | `test_engine_short_circuit` (family:70) · `test_minute_truncation_no_future` (:102) · `test_time_window_default_and_validation` (:176) · `test_missing_minute_required_fail_closed` (:199) |
| 2 | `pytest tests/test_auction_strategy_family_p2.py -k "intraday_truncation or time_factor or intraday_minute_absent" -q` | 3 | `test_intraday_truncation` (p2:222) · `test_time_factor` (:252) · `test_intraday_minute_absent_empty` (:269) |
| 3 | `pytest tests/test_minute_sync_verify.py -q` | 4 | whole file (hermetic minute-K sync enable path, DATA-01) |
| 4 | `pytest tests/test_auction_backtest.py -k "minute_annotation" -q` | 1 | `test_full_backtest_minute_annotation_and_manifest` (backtest:455) |
| 5 | `pytest tests/test_auction_validation_report.py -k "empty_lake_honest or per_strategy_coverage or minute_confirm_regression or forward_stats_branch" -q` | 4 | `test_empty_lake_honest_report_all_9_strategies` (validation_report:159) · `test_per_strategy_coverage_and_minute_confirm` (:564) · `test_minute_confirm_regression_after_coverage` (:1054) · `test_endpoint_forward_stats_branch_minute_confirm` (:794) |

## Notes for 38-02

- Commands 4/5 anchor the report semantics `minute_confirm='not_applied'` (auction_backtest.py:66 hardcode `_MINUTE_CONFIRM`, auction_validation.py:434) — they must stay green at identical counts after wiring.
- Output summaries per command (pre-wiring, 2026-08-07): cmd1 `4 passed, 12 deselected`; cmd2 `3 passed, 8 deselected`; cmd3 `4 passed`; cmd4 `1 passed, 8 deselected`; cmd5 `4 passed, 16 deselected`.
