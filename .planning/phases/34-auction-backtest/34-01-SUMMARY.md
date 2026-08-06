# 34-01 Summary — 竞价回测解锁: backtest service + deterministic persistence (BT-07/BT-09)

**Phase:** 34-auction-backtest · **Plan:** 34-01 · **Executor:** ExecutorP3401 · **Date:** 2026-08-06
**Status:** ✅ COMPLETE — 3/3 tasks, verification green, all commits atomic per task

## Deliverables

| Task | Artifact | Commit |
|------|----------|--------|
| 1 — `run_full_backtest` compute core (BT-07) | `backend/app/services/auction_backtest.py` (new) | `56f8dc2` |
| 2 — deterministic run_id persistence + manifest (BT-09 write side) | `backend/app/services/auction_backtest.py` (extended) | `8d11101` |
| 3 — 6-case test suite | `backend/tests/test_auction_backtest.py` (new) | `9d345d5` |
| Summary | `.planning/phases/34-auction-backtest/34-01-SUMMARY.md` (this file) | committed below |

## What was built

**`run_full_backtest(repo, engine, *, start, end, strategy_ids, symbols, on_progress, job_id) -> dict`** — single-panel vectorized full backtest, mirroring `AuctionValidationService.build_report` assembly shape:

1. enriched coverage `[cache_min, cache_max]` (`repo._enriched_history_cache` → `kline_daily_enriched/date=*` dir fallback); empty → honest `{"status":"no_enriched","empty_reason":"enriched_unavailable"}`
2. window parse + clamp (D-06): end default = cache_max, start default = end−120 natural days; `requested_*`/`effective_*` dual echo; clamped start > end → `no_dates_in_window`
3. warmup load `max(start−14, cache_min)` via `get_enriched_range`; None/empty → `enriched_unavailable`
4. **partition-existence gate ONLY** (`attach_auction_columns_range`, D-03) — zero live probe, zero network
5. strategy enumeration = 9 auction-family ids ∩ engine; unknown ids → `skipped_ids` (no 500); params = META defaults only (O2); `strategy_version = strategy_fingerprint(engine)` (pool_snapshot co-source)
6. per-strategy `_evaluate_strategy_rows`: branch mutual exclusion (BT-05) + `_build_candidate_mask` (imported module-level helper) + per_date + forward stats via **unbound** `AuctionValidationService._forward_stats(None, …)` (BT-04 zero-drift, no instance state) + long-format row frame (RESEARCH §6 schema verbatim)
7. coverage: dates block + symbols block (`_coverage_symbols` scans kline_auction window partitions read-only, fail-closed)
8. persistence: deterministic run_id → atomic `backtest_results/run_id={id}/part.parquet` + `manifest.json` (.tmp+rename, auction_sync.py:45-55 semantics) → idempotent skip on identical fingerprint (`wrote=False, reused=True`)

## Key semantics locked

- **Branch mutual exclusion (BT-05):** 4 `requires_auction_data` strategies always `real` (empty lake → n_dates==0, never derived-downgrade); `auction_alpha` real|derived by enabled non-empty; 4 EOD always `eod`.
- **Forward outcomes (BT-04, co-sourced):** outcome date = global trading calendar next-date (never per-symbol shift); `next_day_open_ret = open_{T+1}/open_T − 1`, `next_day_close_ret = close_{T+1}/open_T − 1`, `open_gap_outcome = open_{T+1}/close_T − 1` (open_T>0 denominators); missing outcome rows → `outcome_missing=True` + counted in `n_missing_outcomes`, **never 0-filled/forward-filled**; per-metric independent n. Row-level values mirror the same calendar join so rows agree with the aggregate count.
- **Deterministic run_id (time-free):** `sha1(sorted(strategy_ids) | start | end | json(params, sort_keys) | strategy_version | sorted(symbols))[:12]` — **symbols included** (2-symbol sparse run never collides with full-market run); `on_progress`/`job_id` excluded; manifest `fingerprint` = same input set as JSON, idempotent skip judge.
- **Honest sparse-lake coverage:** `coverage.symbols = {auction_symbol_count, enriched_symbol_count, symbol_coverage_ratio, auction_rows_present, auction_rows_expected}` + per-strategy `n_symbols_covered`/`n_symbols_hit`.
- **BT-10:** every row `minute_confirm="not_applied"`; manifest `minute_note` = "kline_minute 历史 CLOSED — 确认维度诚实受限; auction_intraday_confirm 恒空 (BT-10)"; `origin="research"` fixed (keeps {eod,backfill,manual} pool vocabulary distinct).
- **O3:** no concept PIT as_of column (honest missing dimension, mirrored from validation report).
- **D-06:** module docstring mirrors auction_validation.py:139-140 ("本回测区间不受回测 186 天 guard 限制 — 单面板向量化扫描, 覆盖由 enriched 缓存边界决定"); `_guard_server_backtest_range` never imported.

## Deviations applied (W1–W5 from 34-PLAN-CHECK)

- **W1 (line refs):** `attach_auction_columns_range` read at `auction_columns.py:160-278` (def at :174), `_build_candidate_mask` at `auction_validation.py:79` — symbols verified by name, cosmetic only.
- **W2 (naming):** test file is `test_auction_backtest.py` (plan), **not** RESEARCH §10's proposed `test_research_backtest.py` — deliberate split recorded; 34-02 references `test_auction_backtest.py` consistently.
- **W3 (runtime):** full 248-day wall-clock measurement deferred to 34-03 Task 4 (this plan's estimate `[INFERENCE]`; smoke runs on 2-3 day fixtures complete in <1s).
- **W4/W5:** n/a to 34-01 (34-03 concerns, acknowledged).
- **Additional executor observation:** `auction_intraday_confirm`'s day-level filter gates on `open_gap` only (no auction-column gate, `builtin/auction_intraday_confirm.py`), so in the real branch it honestly evaluates all symbols on the enabled sub-panel — identical to the validation report's behavior. Test 1 asserts the ⊆-2-symbol property for the auction-column-gated strategies (`auction_fast_grab`/`auction_allround`/`t1_flash`), not intraday_confirm. No service code change needed; behavior is co-sourced with the report.

## Verification evidence

| Gate | Result |
|------|--------|
| New suite `pytest tests/test_auction_backtest.py -x -q` | **6 passed** |
| Regression `pytest tests/test_auction_validation_report.py tests/test_auction_validation.py tests/test_attach_auction_columns_range.py -x -q` | **36 passed** (16 + 6 + 14; import-helper zero-drift lock) |
| Structure `grep -c 'def run_full_backtest' app/services/auction_backtest.py` | 1 |
| Structure `grep -c '_compute_run_id\|_persist_run\|_atomic_write_parquet' app/services/auction_backtest.py` | 8 |
| **Probe-free gate** `grep -c 'auction_probe\|resolve_auction_probe' app/services/auction_backtest.py` | **0** (zero live probe; history gate = partition existence only) |
| `ast.parse` of service module | ok |

Manual smoke (hermetic tmp env, deleted after use): 2-symbol × 3-day run → real branch n_dates=2/hits=2/covered=2, eod full-window, `coverage.symbols.ratio=1.0`, rows 36; second identical run → `wrote=False, reused=True`; manifest field set exact; zero `*.tmp` residue; `strategy_version=7affa346e5e586c5` matches 33-01's recorded provenance (pool_snapshot co-source confirmed).

## Commits

```
9d345d5 test(34-01): 6-case backtest suite (sparse honesty/forward formulas/branch exclusion/idempotency/minute annotation/write-root isolation)
8d11101 feat(34-01): deterministic run_id persistence + provenance manifest (BT-09 write side)
56f8dc2 feat(34-01): run_full_backtest compute core (BT-07 single-panel backtest)
```

## Watchlist proof

`frontend/src/pages/Watchlist.tsx` was **never read, touched, or committed** — it remains the only unstaged change in the repo. Final state check below (run after the summary commit):

```
$ git status --short
M frontend/src/pages/Watchlist.tsx
```

## Zero-touch inventory

- No existing source files modified (only 1 new service file, 1 new test file).
- No existing test lines modified (regression suites untouched, all green).
- Zero new runtime dependencies (polars/duckdb locked stack only).
- `data/` never touched; write-root isolation test locks `backtest_results/` as the only write root (strategy_cache/screener_results byte-identical sentinels).
- 34-02/34-03 dependencies: module-level helper import face (`_build_candidate_mask`/`_null_metric`/`_aggregate_metric`/`_FORWARD_METRICS` + unbound `_forward_stats`) frozen as the plan's contract; manifest coverage/symbols block anchored for 34-03's list endpoint.
