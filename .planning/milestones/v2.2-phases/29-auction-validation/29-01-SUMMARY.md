---
phase: 29-auction-validation
plan: 1
subsystem: api
tags: [polars, parquet, kline-auction, partition, pit-safe, vectorized]

requires:
  - phase: 20-auction-data
    provides: kline_auction/date=* lake + probe-gated single-day read path (attach_auction_columns)
  - phase: 21-auction-strategy-family
    provides: auction_volume_ratio managed-column semantics (竞价量 ÷ 前5日均量, PIT-safe)
provides:
  - "BT-02 attach_auction_columns_range(df, start, end, repo) -> (df, enabled_dates) vectorized range injector"
  - "_dir_date partition-date parser (verbatim copy of auction_history.py)"
affects: [29-02-auction-validation, 29-03-auction-validation, RESEARCH 2.1 vectorized-denominator proof]

actuals:
  tokens: 8972        # chars/4 over realized diff (35886 bytes / 4)
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Vectorized PIT-safe rolling denominator: volume.shift(1).rolling_mean(5, min_samples=1).over('symbol') mirrors single-day get_enriched_history(T,6)->filter(date<T)->tail(5).mean() per-value"
    - "Partition-existence history gate (D-03): range primitive deliberately drops the probe gate (REV-01), documented in docstring"

key-files:
  created:
    - backend/tests/test_attach_auction_columns_range.py
  modified:
    - backend/app/services/auction_columns.py

key-decisions:
  - "Equivalence test seeds the cache per comparison date (cache = panel rows <= d): get_enriched_history anchors its slice at trading_dates[-(lookback+1)] of the WHOLE cache (repository.py:951-957), so the single-day denominator equals 'T-5 prior rows' only when T is cache_max-1/cache_max; per-date slicing keeps cache and panel on identical prior rows (W2 premise)"
  - "min_samples=1 (N1) instead of deprecated min_periods= (polars 1.40.1; matches factor_dsl.py:575 / shadow/production.py:142 convention) — new test file runs warning-free"
  - "Equivalence asserted only on full-panel input with >=5 prior rows (W2); 1-4-prior short history locked by hand-computed mean assertions in boundary/warmup tests"

patterns-established:
  - "Range primitive: sort(symbol,date) -> glob date=* partitions -> _dir_date parse -> per-partition read+symbol-dedup(keep=last) -> diagonal_relaxed concat -> derived unmatched (inputs present) -> keep-list crop -> (symbol,date) left join -> vectorized ratio on df -> warmup trim -> sorted enabled_dates"

requirements-completed: [BT-02]

coverage:
  - id: D1
    description: "attach_auction_columns_range vertical slice — partition discovery (existence gate), per-partition symbol dedup, keep-list left join, enabled-dates, warmup trim, honest empty states (df, [])"
    requirement: BT-02
    verification:
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_end_to_end_injection"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_empty_lake_returns_df_and_empty_dates"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_no_partitions_returns_df_and_empty_dates"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_empty_panel_returns_df_and_empty_dates"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_date_key_join_no_fanout"
        status: pass
    human_judgment: false
  - id: D2
    description: "PIT-safe vectorized ratio equivalent to single-day per-value (every enabled date, <1e-9), leading-no-history difference documented, warmup contract (full 5-prior denominator + no-warmup honest null)"
    requirement: BT-02
    verification:
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_ratio_equivalent_to_single_day"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_leading_no_history_honest_null"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_warmup_contract_full_denominator"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_no_warmup_leading_null_honest"
        status: pass
    human_judgment: false
  - id: D3
    description: "Boundary robustness — bad dir name / empty partition skipped (T-29-01-01/03), fan-out dedup keep=last 09:25 (T-29-01-04), per-symbol absence honest null, derived auction_unmatched_amount injected only when inputs present, no-warmup no crash"
    requirement: BT-02
    verification:
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_bad_dir_and_empty_partition_skipped"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_fanout_dedup_keeps_last_row"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_per_symbol_absence_honest_null"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_derived_unmatched_amount_injected_when_inputs_present"
        status: pass
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py#test_range_no_warmup_no_crash"
        status: pass
    human_judgment: false
  - id: D4
    description: "Single-day attach_auction_columns / _attach_auction_volume_ratio / compute_auction_unmatched_amount zero-change regression lock"
    requirement: BT-02
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_columns.py (14 tests, full file)"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-08-06
status: complete
---

# Phase 29 Plan 1: attach_auction_columns_range 向量化区间竞价列注入原语 (BT-02) Summary

**BT-02 vectorized range injector `attach_auction_columns_range(df, start, end, repo) -> (df, enabled_dates)` in auction_columns.py: partition-existence history gate (no probe), per-partition symbol dedup, PIT-safe `volume.shift(1).rolling_mean(5, min_samples=1).over("symbol")` ratio proven per-value identical to the single-day path, warmup contract, honest empty states — 14 new tests + 14 regression tests green, single-day code zero-change.**

## Performance

- **Duration:** 40 min
- **Started:** 2026-08-06T11:47Z
- **Completed:** 2026-08-06T12:27Z
- **Tasks:** 3 (tracer + 2 expansion)
- **Files modified:** 2 (+1 log file)

## Accomplishments
- `attach_auction_columns_range` lands in `backend/app/services/auction_columns.py` (same module as single-day, shared constants/keep-list semantics, module docstring 「绝不写湖」 kept, **zero new imports**)
- History gate = partition existence only (D-03 / REV-01): no probe consumed, divergence from single-day dual-gate documented in docstring; no null-as-present (platform rule mirrored from :95-96)
- PIT-safe vectorized denominator locked by an equivalence property test: every enabled date's ratio matches single-day `get_enriched_history(T,6)→filter(date<T)→tail(5).mean()` per (symbol, date) within 1e-9 (full-panel input per W2; 1-4-prior short history verified via hand-computed means)
- Boundary robustness: bad dir name / empty partition skip (T-29-01-01/03/05), fan-out dedup keep="last" (09:25 final match, T-29-01-04), per-symbol absence honest null, derived `auction_unmatched_amount` only when input columns present
- Single-day `attach_auction_columns`/`_attach_auction_volume_ratio`/`compute_auction_unmatched_amount` zero-change; `test_auction_columns.py` 14 green

## Task Commits

Each task was committed atomically:

1. **Task 1: attach_auction_columns_range 垂直切片 (tracer, tdd)** —
   - `b4277c4` (test: RED — failing tests for vertical slice)
   - `8ec7fa1` (feat: GREEN — `_dir_date` + `attach_auction_columns_range` + test assertion fix)
2. **Task 2: PIT-safe 等价性属性测试** — `7a9630d` (test: `_seed_enriched_cache` + equivalence/leading/warmup tests)
3. **Task 3: 边界健壮性** — `0d17f05` (test: 5 boundary tests)

## Files Created/Modified
- `backend/app/services/auction_columns.py` — +126 lines: `_dir_date` (verbatim copy of auction_history.py:59-66 with copy-source note) + `attach_auction_columns_range`; module docstring gains a range-primitive bullet; existing code byte-identical
- `backend/tests/test_attach_auction_columns_range.py` — new, 628 lines: hermetic helpers (`repo_env`/`_write_auction_partition`/`_multi_day_panel`/`_auction_rows` mirroring test_auction_columns.py) + 14 tests
- `.planning/phases/29-auction-validation/deferred-items.md` — out-of-scope discovery log (pre-existing screener.py PerformanceWarning)

## Decisions Made
- **Equivalence test per-date cache slicing** (Rule 3 deviation): `get_enriched_history(T, 6)` slices from `trading_dates[-(lookback+1)]` of the whole cache — not ending at T — so the single-day denominator equals 「T 前 5 行」only for the last two cache dates. Fix: for each compared date d, seed `repo._enriched_history_cache = full_panel.filter(date <= d)` so cache and panel carry identical prior rows (exactly W2's premise). Every enabled date is compared; the 132-natural-day warmup gate still passes (cache_min = 03-20 = 07-30 − 132d boundary).
- **N1 applied**: `min_samples=1` (current polars kwarg) instead of plan's `min_periods=1`; new file runs warning-free; matches repo convention (factor_dsl.py:575).
- **W2 applied**: equivalence asserted only on full-panel input (≥5 prior rows); 1-4-prior short history covered by hand-computed assertions (Task 1 Test 1: 2-prior; Task 2 warmup/leading: 1-prior).
- Plan's 「140 个连续自然日 2026-03-20..2026-08-05」 internally inconsistent (that range is 139 days); helper uses the explicit date range (139 days) so the 132-day gate boundary is exact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Single-day denominator slice anchor breaks literal equivalence-test design**
- **Found during:** Task 2 (equivalence property test)
- **Issue:** Plan assumed `get_enriched_history(T, 6)` returns 「T 前 6 个交易日」; the code anchors the slice at `trading_dates[-(lookback_days+1)]` of the **whole cache** (repository.py:951-957) and filters `<= T`. With cache ending 08-05 and T=07-30 the slice is empty → single-day path yields no ratio column; even near the end, equality with the vectorized 「prior 5 panel rows」 holds only for T ∈ {cache_max−1, cache_max}. Verified live with a probe script.
- **Fix:** Per-comparison-date cache seeding — `repo._enriched_history_cache = full_panel.filter(pl.col("date") <= d)` before each single-day call; cache and panel then carry identical prior rows for every compared date (W2's stated premise). All 5 enabled dates compared per-value.
- **Files modified:** backend/tests/test_attach_auction_columns_range.py
- **Verification:** `pytest tests/test_attach_auction_columns_range.py -k "equiv or equivalence or warmup or leading" -x -q` → 4 passed
- **Committed in:** 7a9630d (Task 2 commit)

**2. [Rule 1 - Bug] Order-sensitive assertion in empty-lake test**
- **Found during:** Task 1 GREEN (implementation against RED tests)
- **Issue:** `attach_auction_columns_range` defensively sorts `["symbol","date"]` (plan contract), so the returned frame's row order differs from the date-major input panel; the empty-lake test asserted exact list equality on `symbol`.
- **Fix:** Assert set equality (sorted lists) instead — same rows, same values, documented sort contract.
- **Files modified:** backend/tests/test_attach_auction_columns_range.py
- **Verification:** full file 14 passed
- **Committed in:** 8ec7fa1 (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both necessary for the plan's core acceptance (per-value equivalence) to be implementable against real repository semantics. No scope creep; single-day code untouched.

## TDD Gate Compliance

- Plan frontmatter `type: execute` (not `tdd`) → plan-level RED/GREEN/REFACTOR gate sequence not applicable.
- Task 1 (`tdd="true"`): RED commit `b4277c4` (failing tests) → GREEN commit `8ec7fa1` (implementation) — both present in order. ✅
- Task 2 (`tdd="true"`, **test-only files**): tests written against the already-implemented range function (delivered in Task 1) pass immediately — RED is impossible by design for a test-addition task whose feature pre-exists. Committed as a single `test(...)` commit. Noted for the record.

## Issues Encountered
- `get_enriched_history` slice-anchor semantics (detailed in deviation 1) — resolved by per-date cache slicing; the equivalence proof remains end-to-end per-value for every enabled date.
- Pre-existing `PerformanceWarning` at `screener.py:376` surfaced in `test_auction_columns.py` regression (2 warnings, no failures) — unrelated to this plan (out of scope; logged to `deferred-items.md`).

## Known Stubs
None — all 14 tests assert real values; no placeholders, skips, or unwired data sources in the new code.

## Threat Flags
None — new surface is read-only parquet glob + strict `date.fromisoformat` parse of partition dir names (T-29-01-01), fail-closed read guard (T-29-01-05), symbol-level dedup (T-29-01-04), no writes (T-29-01-02), no null-as-present (T-29-01-03). All mitigations implemented and locked by tests. Zero new imports/deps (T-29-01-SC n/a).

## User Setup Required
None.

## Next Phase Readiness
- 29-02 (BT-03/04/05 report assembly) consumes `attach_auction_columns_range(df, start, end, repo) -> (df, enabled_dates)` exactly as contracted — panel from `get_enriched_range` fast path (same volume source as the equivalence premise), warmup rows loaded by the service (warmup_start clamp to cache_min per PLAN-CHECK W-1).
- 29-03 (BT-01/06 endpoint + AST guard) consumes the endpoint contract; `auction_columns.py` gained no write surface, no new imports (BT-06 import whitelist unchanged).

## Self-Check: PASSED
- FOUND: backend/app/services/auction_columns.py, backend/tests/test_attach_auction_columns_range.py, .planning/phases/29-auction-validation/29-01-SUMMARY.md
- FOUND commits: b4277c4 (RED), 8ec7fa1 (GREEN), 7a9630d (Task 2), 0d17f05 (Task 3)
- Final suites: test_attach_auction_columns_range.py 14 passed; test_auction_columns.py 14 passed

---
*Phase: 29-auction-validation*
*Completed: 2026-08-06*
