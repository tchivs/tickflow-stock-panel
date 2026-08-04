---
phase: 17-auction-strategy-family
plan: 2
subsystem: strategy
tags: [factor-hits, 关联因子, screener, run_all, polars, fastapi]

# Dependency graph
requires:
  - phase: 16-auction-data
    provides: open_gap governed factor column (open / prev_close - 1), auction probe honesty
provides:
  - factor_hits.build_factor_hits / attach_factor_hits pure aggregation contract (Phase 18 交叉共振 seam)
  - screener run_all per-row hit_factors tagging (关联因子)
affects: [Phase 18 pool hub 交叉共振, screener API consumers]

# Actuals (#2632) — chars/4 over the realized diff (13171 added chars / 4)
actuals:
  tokens: 3293
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - pure server-derived aggregation over strategy result rows (no synthesized hits)
    - display-name resolver: PRESET_STRATEGIES name -> engine META name -> sid fallback
    - additive per-row field wiring (total/as_of untouched)

key-files:
  created:
    - backend/app/strategy/factor_hits.py
    - backend/tests/test_factor_hits.py
  modified:
    - backend/app/api/screener.py

key-decisions:
  - "hit_factors values sorted by Unicode codepoint (deterministic, per plan rule; sample order in PLAN was corrected from 竞价多头-first to 盘前强势量化-first)"
  - "canned API-test strategies disable the default basic filter (BASIC_FILTER enabled=false) to keep the API regression hermetic"
  - "Task 1 committed as one feat(17-02) commit (module + fixture tests) rather than split test/feat"

patterns-established:
  - "Pattern: server-derived factor-hit tagging — a symbol enters hit_factors only when that strategy's own result rows contain it"
  - "Pattern: _strategy_display_name resolver degrades unknown ids to sid (never 500s run_all)"

requirements-completed: [STRAT-02]

coverage:
  - id: D1
    description: "Pure aggregation contract — build_factor_hits maps overlapping strategy results to {symbol: sorted[display names]}, attach_factor_hits adds the hit_factors column without mutating inputs; zero-hit symbols absent, deterministic order"
    requirement: STRAT-02
    verification:
      - kind: unit
        ref: "backend/tests/test_factor_hits.py#test_build_factor_hits_overlap_aggregation"
        status: pass
      - kind: unit
        ref: "backend/tests/test_factor_hits.py#test_build_factor_hits_default_resolver_is_identity"
        status: pass
      - kind: unit
        ref: "backend/tests/test_factor_hits.py#test_build_factor_hits_deterministic_order"
        status: pass
      - kind: unit
        ref: "backend/tests/test_factor_hits.py#test_build_factor_hits_symbol_with_no_hits_absent"
        status: pass
      - kind: unit
        ref: "backend/tests/test_factor_hits.py#test_attach_factor_hits_adds_column_without_mutation"
        status: pass
    human_judgment: false
  - id: D2
    description: "screener run_all API wiring — every result row carries a JSON-safe hit_factors list naming each strategy whose result contains that symbol; total/as_of unchanged; resolver maps preset and engine ids to display names"
    requirement: STRAT-02
    verification:
      - kind: integration
        ref: "backend/tests/test_factor_hits.py#test_run_all_rows_carry_hit_factors"
        status: pass
    human_judgment: false

# Metrics
duration: 32min
completed: 2026-08-04
status: complete
---

# Phase 17 Plan 2: 关联因子 (Factor-Hit Tagging) Summary

**Pure, server-derived per-stock factor-hit aggregation (`build_factor_hits`/`attach_factor_hits`) wired additively into the screener `run_all` response so every result row reports which strategies hit it — the seam Phase 18 cross-resonance consumes**

## Performance

- **Duration:** ~32 min
- **Started:** 2026-08-04
- **Completed:** 2026-08-04
- **Tasks:** 2
- **Files modified:** 3 (1 created module, 1 created test, 1 modified API)

## Accomplishments

- `backend/app/strategy/factor_hits.py` — the STRAT-02 contract: pure module (no I/O, no strategy imports) exposing `HIT_FACTORS_COLUMN = "hit_factors"`, `build_factor_hits(results, name_for=None) -> {symbol: sorted[display names]}`, and `attach_factor_hits(rows, hits)` (non-mutating). A symbol enters `hit_factors` only for strategies whose own result rows contain it (T-17-05 server-derived, no synthesized hits).
- `backend/app/api/screener.py` — `_strategy_display_name(engine, sid)` resolver (PRESET name -> engine META name -> sid fallback, T-17-06) and `run_all` post-loop wiring: build hits over sanitized results, attach per row before cache write / ext projection. `total`/`as_of` unchanged (additive, T-17-07).
- `backend/tests/test_factor_hits.py` — 6 tests: 5 pure-function fixture tests (overlap aggregation, identity resolver, determinism incl. reversed strategy order, zero-hit-absent, non-mutation) + 1 FastAPI/TestClient regression driving `POST /api/screener/run_all` with two canned engine strategies over overlapping pools.

## Task Commits

Each task was committed atomically:

1. **Task 1: 关联因子 contract — build_factor_hits pure aggregation + fixture tests** - `e25660c` (feat)
2. **Task 2: Wire 关联因子 into screener run_all response + API regression test** - `f4a49e7` (feat)

## Files Created/Modified

- `backend/app/strategy/factor_hits.py` - Pure aggregation contract: `HIT_FACTORS_COLUMN`, `build_factor_hits`, `attach_factor_hits`.
- `backend/tests/test_factor_hits.py` - 5 fixture tests + 1 run_all API regression test (hermetic canned strategies).
- `backend/app/api/screener.py` - `_strategy_display_name` resolver + `run_all` hit_factors post-processing.

## Decisions Made

- **hit_factors sort order:** Unicode codepoint lexicographic order (per plan's stated rule). The PLAN's sample fixture list for symbol `Y` ("竞价多头" before "盘前强势量化") contradicts codepoint order (盘 U+76D8 < 竞 U+7ADE), so the test asserts the actual deterministic order.
- **Hermetic API regression:** canned strategies disable the default basic filter (`BASIC_FILTER = {"enabled": False}`) so the endpoint test depends only on `change_pct` + `symbol` columns, not the default market-cap/price/amount filter.
- **Resolver path:** `PRESET_STRATEGIES`-free sids in the API test force the engine META path (matching the plan requirement); the preset path is covered by the resolver's branch and PRESET entries all carry `name`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Correctness] Sample fixture order corrected to actual codepoint sort**
- **Found during:** Task 1 (fixture tests)
- **Issue:** PLAN's sample assertion expected `{"Y": ["竞价多头", "盘前强势量化"]}`, but Python's lexicographic sort orders Chinese by Unicode codepoint — 盘(U+76D8) < 竞(U+7ADE), so the true deterministic result is `["盘前强势量化", "竞价多头"]`.
- **Fix:** Updated the fixture test to assert the codepoint-deterministic order (the plan's stated rule). No change to `factor_hits.py`.
- **Files modified:** `backend/tests/test_factor_hits.py`
- **Verification:** `pytest tests/test_factor_hits.py` green (6 passed).
- **Committed in:** e25660c (Task 1 commit)

**2. [Rule 3 - Implementation detail] Canned API-test strategies disable default basic filter**
- **Found during:** Task 2 (API regression test)
- **Issue:** PLAN's canned-strategy description only specified META id/name + `filter`; with the engine default basic filter active, the enriched fixture would need to satisfy market-cap/price/amount constraints, coupling the test to unrelated filter logic.
- **Fix:** Added `BASIC_FILTER = {"enabled": False}` to the two canned strategy files written by the test fixture.
- **Files modified:** `backend/tests/test_factor_hits.py`
- **Verification:** API regression test passes; `total`/`as_of` unchanged asserted.
- **Committed in:** f4a49e7 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 correctness, 1 implementation detail)
**Impact on plan:** Both auto-fixes necessary for a correct, hermetic test suite. No scope creep; no change to the delivered contract.

## Issues Encountered

- One edit-tool hunk landed on stale line numbers and briefly displaced a helper inside `market_snapshot`; the block was repaired by re-reading the region and restoring the loop body before the resolver was inserted at the correct location. Verified by import check and `test_screener_etf.py` (10 passed) + `test_factor_hits.py` (6 passed).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 18 (pool hub 交叉共振) can consume `hit_factors` on every `run_all` result row via the pure `factor_hits` contract, or re-derive from `screener_results/` persistence in the same `{"rows": [...]}` shape.
- The run_all response is backward compatible: `total`/`as_of`/`rows` shape unchanged, `hit_factors` additive per row, JSON-safe (list of strings).
- No blockers. Executor 17-01 runs concurrently on `strategy/builtin/` + engine discovery; this plan did not touch those files (17-01 only reads `screener.py`; my edits are the sole writer there).

---
*Phase: 17-auction-strategy-family*
*Completed: 2026-08-04*
