---
phase: 16-auction-data
plan: 1
subsystem: api
tags: [minute-k, parquet, polars, duckdb, preferences, timestamp-convention, data-lake]
requires: []
provides:
  - Hermetic integration proof that minute-K sync enable path persists 1m bars to kline_minute with 09:30+ timestamps and leaves the daily-K lake byte-identical
  - minute_sync_symbols scope preference (empty = full universe) wired through preferences, settings API, and daily_pipeline._resolve_minute_symbols
  - Regression-locked 09:30 timestamp convention (_minute_ts anchor + _bucket_minutes morning/afternoon session boundary)
affects: [17-strategy-family, 18-pool-hub, DATA-02, DATA-03]
actuals:
  tokens: 3599
  tasks: 3
  commits: 3
tech-stack:
  added: []
  patterns:
    - Hermetic lake test: monkeypatch settings.data_dir to tmp_path, construct DataStore/KlineRepository, snapshot parquet partition sets + per-file sha256 before/after
    - Stub the minute feed at the sync_minute_batch fetch seam (never at the write path) for network-free integration coverage
    - Preference scope knob: empty list = full universe (default unchanged), normalized on read and write
key-files:
  created:
    - backend/tests/test_minute_sync_verify.py
    - backend/tests/test_minute_timestamp_convention.py
  modified:
    - backend/app/services/preferences.py
    - backend/app/api/settings.py
    - backend/app/jobs/daily_pipeline.py
key-decisions:
  - "Minute symbol scope shipped as an API/preference-only knob in Phase 16 (no frontend control) per plan; UI surfaced in Phase 18/19 if needed"
  - "The run_now gate is proven hermetically via run_now-equivalent branch logic + can_sync_minute() semantics rather than invoking the full heavy pipeline"
  - "_bucket_minutes morning bucket index is capped at M-1 so the 11:30 bar stays in the final morning bucket and never spills into afternoon"
patterns-established:
  - "Preference normalization helper (_normalize_symbol_list) splits on commas/newlines, strips, drops empties, preserves order/dedup, and handles both list and string storage"
  - "Timestamp honesty guard: a pre-open bar structurally cannot be labeled session/auction data"
requirements-completed: [DATA-01]
coverage:
  - id: D1
    description: "Enable minute sync -> 1m bars land in data/kline_minute/date=2026-08-04/part.parquet with canonical columns, Datetime('us'), 09:30 anchor, and the daily-K lake (partition sets + per-file sha256) byte-identical before/after"
    requirement: DATA-01
    verification:
      - kind: integration
        ref: "backend/tests/test_minute_sync_verify.py#test_minute_sync_enable_persists_and_leaves_daily_lake_unchanged"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pipeline gate: with minute_sync_enabled False (or a CapabilitySet lacking Cap.KLINE_MINUTE_BATCH and no custom minute provider) can_sync_minute is False and run_now-equivalent logic appends sync_minute to skipped, writing 0 minute rows"
    requirement: DATA-01
    verification:
      - kind: integration
        ref: "backend/tests/test_minute_sync_verify.py#test_minute_sync_gate_skips_when_disabled_or_capability_missing"
        status: pass
    human_judgment: false
  - id: D3
    description: "minute_sync_symbols scope preference: normalization of messy input, empty/whitespace-only -> [], save/load round-trip, and _resolve_minute_symbols honors non-empty scope while falling back to the universe when empty; GET/PUT /api/settings/preferences/minute-sync round-trip minute_sync_symbols"
    requirement: DATA-01
    verification:
      - kind: unit
        ref: "backend/tests/test_minute_sync_verify.py#test_minute_sync_symbols_normalization_and_round_trip"
        status: pass
      - kind: unit
        ref: "backend/tests/test_minute_sync_verify.py#test_resolve_minute_symbols_honors_scope"
        status: pass
    human_judgment: false
  - id: D4
    description: "09:30 timestamp convention locked: _minute_ts anchors start-of-day to 093000 (never 00:00/09:15), _bucket_minutes never buckets a pre-09:30 bar into the morning session, the 11:30 bar stays in the final morning bucket, the afternoon session starts at 13:00, and a 09:30-earliest frame never resolves below 09:30 (honesty guard)"
    requirement: DATA-01
    verification:
      - kind: unit
        ref: "backend/tests/test_minute_timestamp_convention.py#test_minute_ts_anchors_start_of_day_to_0930"
        status: pass
      - kind: unit
        ref: "backend/tests/test_minute_timestamp_convention.py#test_bucket_minutes_never_buckets_pre_0930_bar_into_morning_session"
        status: pass
      - kind: unit
        ref: "backend/tests/test_minute_timestamp_convention.py#test_bucket_minutes_honesty_guard_never_labels_pre_open_as_session"
        status: pass
    human_judgment: false
duration: 25min
completed: 2026-08-04
status: complete
---

# Phase 16 Plan 1: Minute-K sync enable + 09:30 timestamp convention + symbol scoping Summary

**Hermetic proof that enabling minute-K sync persists canonical 1m bars to `kline_minute` with 09:30+ timestamps while leaving the daily-K lake byte-identical, plus a `minute_sync_symbols` scope knob and a regression-locked 09:30 timestamp convention**

## Performance

- **Duration:** 25 min
- **Started:** 2026-08-04T12:47:26Z
- **Completed:** 2026-08-04T13:12:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- `test_minute_sync_verify.py` proves the DATA-01 enable path end-to-end with zero network: temp lake seeded through the repository's own write helpers, daily-K partition sets + per-file sha256 snapshotted before/after, `sync_minute_batch` stubbed at the fetch seam, and `sync_and_persist_minute` verified to write 10 canonical rows anchored at 09:30 while the daily lake stays byte-identical.
- Pipeline gate test proves the enable flag is the real gate: `can_sync_minute(CapabilitySet())` is False (no capability, no custom minute provider) and the disabled-preference branch appends `sync_minute` to `skipped` with 0 minute rows written.
- `minute_sync_symbols` preference shipped: `get_minute_sync_symbols`/`set_minute_sync_symbols` (commas/newlines, strip, dedup, order-preserving; empty = full universe), `MinuteSyncPrefs.minute_sync_symbols`, GET/PUT `/api/settings/preferences/minute-sync` round-trip, and `daily_pipeline._resolve_minute_symbols` honoring a non-empty scope. No frontend control (per plan).
- `test_minute_timestamp_convention.py` locks the 09:30 convention: `_minute_ts` start-of-day resolves to `093000`, `_bucket_minutes` drops pre-09:30 bars, anchors the first morning bucket at 09:30, keeps 11:30 in the final morning bucket (M-1), starts the afternoon at 13:00, and structurally prevents labeling a pre-open bar as session/auction data.

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end minute-K sync tracer test** - `1b78480` (test)
2. **Task 2: minute_sync_symbols scope preference + settings API + pipeline** - `f0dc03a` (feat)
3. **Task 3: 09:30 timestamp convention regression tests** - `7dd565d` (test)

**Plan metadata:** (final metadata commit follows in the state-update step)

## Files Created/Modified

- `backend/tests/test_minute_sync_verify.py` - Hermetic integration test (tracer + gate) and symbol-scope preference unit tests
- `backend/tests/test_minute_timestamp_convention.py` - `_minute_ts`/`_bucket_minutes` 09:30 convention regression suite
- `backend/app/services/preferences.py` - Added `_normalize_symbol_list`, `get_minute_sync_symbols`, `set_minute_sync_symbols`
- `backend/app/api/settings.py` - `MinuteSyncPrefs.minute_sync_symbols`, GET payload key, `update_minute_sync` persistence
- `backend/app/jobs/daily_pipeline.py` - `_resolve_minute_symbols` honors `minute_sync_symbols` (empty = full universe)

## Decisions Made

- Shipped the symbol-scope knob as API/preference-only in Phase 16 (no frontend control) exactly per plan; the auction pool is not defined until Phase 17, so the generic scope knob is the Phase 16 deliverable.
- Proven the pipeline gate hermetically with `can_sync_minute()` semantics + run_now-equivalent branch logic rather than invoking the full daily pipeline (which would need network).
- Used per-file sha256 over the daily-K parquet partitions plus sorted `date=*` dir sets as the byte-identical lake proof.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Polars Int8 overflow in wall-clock minute arithmetic**
- **Found during:** Task 1 (tracer test)
- **Issue:** `datetime.dt.hour()` returns Int8; multiplying by 60 overflowed (540 > 127), raising `OverflowError`.
- **Fix:** Cast to Int64 before arithmetic: `.dt.hour().cast(pl.Int64) * 60 + .dt.minute()`.
- **Files modified:** `backend/tests/test_minute_sync_verify.py` (and same pattern reused in `test_minute_timestamp_convention.py`)
- **Verification:** Full suite green (7 passed).
- **Committed in:** `1b78480` (task 1 commit)

**2. [Rule 1 - Bug] Symbol-list normalizer did not split separators inside list elements**
- **Found during:** Task 2 (preference unit tests)
- **Issue:** Input `[" 000001.SZ ", ",600000.SH\n", "000001.SZ"]` produced `[",600000.SH"]` because each list element was treated as one token.
- **Fix:** `_normalize_symbol_list` now splits every element (string or list) on commas and newlines before stripping/dedup.
- **Files modified:** `backend/app/services/preferences.py`
- **Verification:** Normalization/round-trip test green.
- **Committed in:** `f0dc03a` (task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes were test/implementation correctness requirements; no scope creep.

## Issues Encountered

None - the two deviations above were caught and fixed during the task's own verify run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- DATA-01 enable path is proven and reproducible against a real provider (set `minute_sync_enabled` + run the pipeline `sync_minute` stage; scope with `minute_sync_symbols` for cheap verification runs).
- The 09:30 convention is regression-locked, ready as the data-integrity foundation for DATA-03 (never label a pre-open bar as auction data) and Phase 17 strategy work.
- The `minute_sync_symbols` knob is API/preference-only; a UI control can be surfaced in Phase 18/19 work if needed.

---
*Phase: 16-auction-data*
*Completed: 2026-08-04*

## Self-Check: PASSED

- Created files verified: `backend/tests/test_minute_sync_verify.py`, `backend/tests/test_minute_timestamp_convention.py`, `.planning/phases/16-auction-data/16-01-SUMMARY.md`
- Commits verified: `1b78480`, `f0dc03a`, `7dd565d`
