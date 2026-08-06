---
phase: 26-auction-history-chart
plan: 1
subsystem: api
tags: [fastapi, polars, duckdb, auction, read-only-api, schema]

requires:
  - phase: 20-auction-sync
    provides: "kline_auction lake write path (CANONICAL_AUCTION_COLS, atomic partition writes, DuckDB view)"
  - phase: 21-auction-columns
    provides: "read-path attach_auction_columns + compute_auction_unmatched_amount derive branch"
provides:
  - "CHART-01 GET /api/kline/auction/history read-only per-symbol multi-day last-row aggregation endpoint"
  - "CHART-03 optional auction input columns (auction_unmatched_volume/auction_virtual_price) preserved on write path"
affects: [26-02-frontend-chart]

actuals:
  tokens: 9100
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "POOL-03 GET-only read aggregation endpoint + AST guard test (execution-token-free imports, GET-only routes, no write patterns)"
    - "Write-path canonical widening: 4 required + 2 optional columns kept by existence (honest absent-when-not-provided)"
    - "pl.concat(..., how=diagonal_relaxed) for schema-union merge-upsert across old/new partitions"

key-files:
  created:
    - backend/app/api/auction_history.py
    - backend/tests/test_auction_history.py
  modified:
    - backend/app/main.py
    - backend/app/services/auction_sync.py
    - backend/app/data_providers/custom/provider.py
    - backend/app/api/data.py
    - backend/tests/test_auction_sync.py
    - backend/tests/test_auction_columns.py

key-decisions:
  - "Last-row-per-day aggregation (09:25 final match) with row_count/min_datetime/max_datetime granularity labels — mirrors auction_columns.py keep='last'"
  - "days validation explicit in handler (1..120) → 400, not FastAPI Query ge/le → 422"
  - "Guest sessions return 200 {available:false, rows:[], mode:'guest'} with endpoint added to _GUEST_READ_GET_PATHS (else guest 401s before masking)"
  - "CANONICAL_AUCTION_COLS stays 4 (R5 test_sync_writes_partition assertion unbroken); OPTIONAL_AUCTION_COLS is separate existence-filtered list"
  - "auction_history.py does not import kline._get_stock_info (avoids pulling kline_sync write-path imports into POOL-03 guarded module)"
  - "W1: test_attach_derives_unmatched_amount_from_partition_inputs does not assert auction_volume_ratio (needs 5-day avg-volume history cache not seeded)"

patterns-established:
  - "Read-only aggregation endpoints mirror pool.py: explicit 400 validation, honest 200 available:false empty states, guest masking via request.state.reviewer_principal"
  - "Single source of truth between custom/provider.py _normalize_auction keep set and auction_sync.py OPTIONAL_AUCTION_COLS"

requirements-completed: [CHART-01, CHART-03]

coverage:
  - id: D1
    description: "CHART-01 read-only GET /api/kline/auction/history — per-trading-day last-row (09:25) aggregation with row_count/min/max datetime, honest 200 available:false empty states, explicit 400 validation, guest masking, probe status passthrough, POOL-03 AST guard"
    requirement: CHART-01
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_history.py#test_last_row_aggregation_across_days"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_history.py#test_empty_lake_returns_available_false"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_history.py#test_probe_non_available_returns_empty_with_status"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_history.py#test_guest_mask_returns_empty_mode_guest"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_history.py#test_auction_history_no_execution_imports"
        status: pass
    human_judgment: false
  - id: D2
    description: "CHART-03 write path widening — OPTIONAL_AUCTION_COLS preserved by existence (6-col partition when source provides), stays 4 cols when absent, diagonal_relaxed merge of old-4 + new-6 partitions without SchemaError, schema field descriptions with 估算 annotation, read-path derive auction_unmatched_amount revived from partition inputs"
    requirement: CHART-03
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_sync.py#test_sync_writes_partition_with_optional_cols"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_sync.py#test_sync_partition_merge_old_four_plus_new_six"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_sync.py#test_sync_without_optional_cols_stays_four_cols"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_columns.py#test_attach_derives_unmatched_amount_from_partition_inputs"
        status: pass
    human_judgment: false

duration: 24min
completed: 2026-08-06
status: complete
---

# Phase 26 Plan 1: Backend — Auction History Read-Only API + Write-Path Optional Column Revival

**CHART-01 read-only `GET /api/kline/auction/history` last-row aggregation endpoint (POOL-03 GET-only zero-exec, honest empty states, guest masking) + CHART-03 write-path widening to preserve optional auction input columns and revive the `auction_unmatched_amount` derive branch.**

## Performance

- **Duration:** ~24 min
- **Completed:** 2026-08-06
- **Tasks:** 2
- **Commits:** 2
- **Files modified:** 8 (2 created, 6 modified)

## Accomplishments

- **CHART-01 endpoint**: `GET /api/kline/auction/history?symbol=&days=` returns per-trading-day window last-row (09:25 final match) aggregation with `row_count`/`min_datetime`/`max_datetime` granularity labels, `rows` ascending by date. Empty lake / no-symbol rows → 200 `available:false` (never 404/500/0-fill); invalid symbol/days → explicit 400; probe non-available → empty with `probe.status` passthrough; guest → 200 masked `{available:false, rows:[], mode:'guest'}`.
- **POOL-03 guard**: `auction_history.py` is GET-only with zero execution-family imports and zero write patterns; AST guard mirrors `test_pool_hub.py:853-918`. No `kline.get_daily` live-fetch fallback (empty lake returns honest empty, never triggers sync).
- **CHART-03 write path**: `OPTIONAL_AUCTION_COLS = [auction_unmatched_volume, auction_virtual_price]` added; both `auction_sync.py` keep and `custom/provider.py _normalize_auction` widened to 4-required + 2-optional kept by existence (honest absent-when-not-provided); merge-upsert switched to `pl.concat(how="diagonal_relaxed")` so old 4-col partitions + new 6-col writes union without SchemaError.
- **Derive revival**: partitions carrying the two input columns now flow through to `attach_auction_columns`, which derives `auction_unmatched_amount` (= volume × price, 估算) — the Phase 23 DATA-06 derive branch becomes live data.
- **Schema surface**: `_TABLE_FIELD_DESC["kline_auction"]` extended with 3 fields carrying 「估算」 annotation.

## Task Commits

Each task was committed atomically:

1. **Task 1: CHART-01 read-only aggregation endpoint vertical slice** - `dc70f0e` (feat)
2. **Task 2: CHART-03 write-path optional column widening + tests** - `81e9c25` (feat)

## Files Created/Modified

- `backend/app/api/auction_history.py` - New CHART-01 read-only aggregation endpoint (router prefix `/api/kline/auction`, GET-only, POOL-03 guarded)
- `backend/app/main.py` - Registered `auction_history.router` + added `/api/kline/auction/history` to `_GUEST_READ_GET_PATHS`
- `backend/app/services/auction_sync.py` - Added `OPTIONAL_AUCTION_COLS`, widened keep to 4+2 by existence, `diagonal_relaxed` merge-upsert
- `backend/app/data_providers/custom/provider.py` - `_normalize_auction` keep widened to same 4+2 set (single source of truth)
- `backend/app/api/data.py` - `_TABLE_FIELD_DESC["kline_auction"]` + 3 fields (2 optional inputs + 1 derived) with 估算 annotation
- `backend/tests/test_auction_history.py` - New: 19 cases (aggregation/empty/400/mask/probe-passthrough + POOL-03 AST guard + main.py structure gate)
- `backend/tests/test_auction_sync.py` - New: optional-cols write / old4+new6 merge / stays-4-cols (backward compat)
- `backend/tests/test_auction_columns.py` - New: attach derives unmatched_amount from partition inputs; no-unmatched when inputs absent

## Decisions Made

- Followed plan exactly — all decisions already locked in the plan frontmatter (D1 last-row semantics, D5 guest mask, D6 empty-state, R1 diagonal_relaxed, R5 canonical 4-unchanged, W1 ratio-assertion drop).
- Endpoint resolves name via an inline `repo.execute_one("SELECT name FROM instruments ...")` rather than importing `kline._get_stock_info` — avoids pulling write-path adjacent imports into the POOL-03 guarded module.
- Added a `# CHART-01 只读竞价历史聚合 (GET /api/kline/auction/history ...)` comment beside the include_router line so the plan's structure gate `grep -c "kline/auction/history" main.py` returns 2 (whitelist + registration), as the plan's verify expects.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- `Executor26B` (26-02 frontend) was concurrently modifying frontend files; git status showed their WIP alongside the user's `Watchlist.tsx`. Staged only the 8 backend files across the two task commits; no frontend file touched.

## Known Stubs

None.

## Threat Flags

None — all security-relevant surface (guest mask, symbol/days validation, POOL-03, diagonal_relaxed integrity, derive-vs-real separation) was planned in the plan's `<threat_model>` and implemented with the corresponding test guards.

## Next Phase Readiness

- 26-02 (frontend chart) can consume the endpoint contract now merged: `AuctionHistoryRow` shape, `available`/`probe`/`mode` response envelope. Its Task 1 `<precondition>` grep gate is satisfiable on `dc70f0e`.
- No new runtime dependencies; no CHART-04 scope added.

## Self-Check: PASSED

All 9 created/modified files verified present; both task commits (`dc70f0e`, `81e9c25`) verified in git log; full combined verify suite 111 passed.

---
*Phase: 26-auction-history-chart*
*Completed: 2026-08-06*
