---
phase: 18-pool-hub
plan: 1
subsystem: api
tags: [fastapi, polars, pool-hub, strategy-cache, concept-filter, zero-execution]

# Dependency graph
requires:
  - phase: 17 (竞价策略族)
    provides: hit_factors seam (Phase 17 cross-strategy aggregate, codepoint-sorted)
  - phase: 16 (竞价数据层)
    provides: ext concept data seam (ExtConfigStore + market_overview_builder join)
provides:
  - build_pool_hub single-as_of projection (5-column rows + 交叉共振 + concept filter)
  - GET /api/pool/hub read-only endpoint (POOL-03 zero execution authority)
affects: [18-02 frontend PoolHubPage, 19 guest/VIP masking]

# Actuals (#2632) — pairs with the plan's estimate (52000 tokens / 34000 raw).
# Same estimateTokens scale: chars/4 over the realized diff (27563 chars added).
actuals:
  tokens: 6891
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Single as_of source of truth (card total + drill rows from one read_cache, PITFALL #10)
    - Server-computed 交叉共振 (cross_resonance = len(hit_factors) >= 2, D-03)
    - Concept filter as a projection over the current as_of pool (total stays authoritative)
    - POOL-03 AST guard locking no-execution boundary (imports / routes / write paths / vocab)

key-files:
  created:
    - backend/app/services/pool_hub.py
    - backend/app/api/pool.py
    - backend/tests/test_pool_hub.py
  modified:
    - backend/app/main.py

key-decisions:
  - "Projection is read-only over the existing strategy_cache (no new datastore, D-01); rows are copy-safe, cache never mutated."
  - "as_of is echoed from the cache read — a mismatched caller as_of never fabricates a second date (D-02, T-18-03)."
  - "交叉共振 = len(hit_factors) >= 2 server-side; resonance_count = distinct resonant symbols across strategies (D-03)."
  - "概念板块 joined from the ext ConceptAnalysis/overview seam (_dimension_field/_read_ext_rows/_dimension_values/_symbol_keys); missing data degrades to [] (D-04, T-18-05)."
  - "Strategy display names reuse screener._strategy_display_name (PRESET → engine META → sid fallback), never client-supplied (T-18-02)."

patterns-established:
  - "Single-read projection contract: one strategy_cache.read_cache call feeds both per-strategy total and drill rows."
  - "POOL-03 guard suite: AST import audit + route-method audit + write-path audit + response-vocabulary audit."

requirements-completed: [POOL-01, POOL-02, POOL-03]

coverage:
  - id: D1
    description: "POOL-01 backend — build_pool_hub reads the persisted strategy results for a single as_of and projects per-strategy authoritative totals plus 5-column drill rows (code/open_gap/change_pct/concept_board/hit_factors) + cross_resonance; card counts and drill lists never drift."
    requirement: POOL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_build_pool_hub_single_as_of_counts_and_columns"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_concept_board_join_and_missing_value_dash"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_build_pool_hub_does_not_mutate_cache"
        status: pass
      - kind: integration
        ref: "backend/tests/test_pool_hub.py#test_get_pool_hub_mismatched_as_of_returns_cache_date"
        status: pass
    human_judgment: false
  - id: D2
    description: "POOL-02 backend — concept filter projects over the current as_of pool (rows narrowed, total authoritative) and 交叉共振 is server-computed as hit_factors >= 2 with a resonance_count."
    requirement: POOL-02
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_concept_filter_keeps_total_authoritative"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_concept_filter_is_case_insensitive"
        status: pass
      - kind: integration
        ref: "backend/tests/test_pool_hub.py#test_get_pool_hub_concept_filter_keeps_total"
        status: pass
    human_judgment: false
  - id: D3
    description: "POOL-03 backend — GET /api/pool/hub is the only pool surface; no broker/order/execution import, no mutating route, no write path anywhere in the pool feature (guard tests green)."
    requirement: POOL-03
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_pool_hub_no_execution_imports"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_pool_api_is_get_only"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_build_pool_hub_has_no_write_path"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_hub_response_has_no_execution_vocabulary"
        status: pass
    human_judgment: false

# Metrics
duration: 20min
completed: 2026-08-04
status: complete
---

# Phase 18 Plan 1: Pool Hub Backend Summary

**Single-as_of pool-hub projection service (`build_pool_hub`) reading `screener_results/` persistence via `strategy_cache.read_cache`, projecting per-strategy counts + 5-column drill rows with server-computed 交叉共振 and a concept filter, exposed through read-only `GET /api/pool/hub`, with a POOL-03 zero-execution-authority guard suite.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-08-04
- **Completed:** 2026-08-04
- **Tasks:** 3 (all complete)
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments

- `build_pool_hub(data_dir, as_of, concept, name_for)` — deterministic single-as_of projection: per-strategy `total` equals the persisted row count, every row carries code/开盘涨幅/涨跌幅/概念板块/关联因子 + `cross_resonance` (hit_factors ≥ 2), 概念板块 joined from the ext ConceptAnalysis seam, NaN/Inf sanitized to None, cache never mutated.
- `GET /api/pool/hub?as_of=&concept=` — read-only endpoint registered in `main.py` beside screener; strategy names resolve server-side (PRESET → engine META → sid fallback); a mismatched `as_of` echoes the cache date (no fabricated second date); empty cache returns a clean 200 empty hub.
- POOL-03 guard suite (T-18-01): AST import audit, GET-only route audit, no-write-path audit, and response-vocabulary audit — any future execution/order surface in the pool feature fails the suite.
- 17 backend tests green in `backend/tests/test_pool_hub.py`.

## Task Commits

Each task was committed atomically:

1. **Task 1: build_pool_hub projection service (tracer)** - `ee47f7f` (feat)
2. **Task 2: GET /api/pool/hub endpoint + router registration** - `c2a27c3` (feat)
3. **Task 3: POOL-03 zero-execution-authority guard test** - `b0e96dc` (test)

**Fixture fidelity fix (post-Task-3, codepoint-sort alignment):** `2fcdb95` (test)

## Files Created/Modified

- `backend/app/services/pool_hub.py` - Pure read-only projection contract: `build_pool_hub`, `_safe_num` (NaN/Inf → None), `_build_concept_map` (ext concept seam). No execution imports, no write path.
- `backend/app/api/pool.py` - `APIRouter(prefix="/api/pool")` with only `@router.get("/hub")`; resolves `data_dir` from `request.app.state.repo.store.data_dir`, names via `screener._strategy_display_name`.
- `backend/app/main.py` - Added `pool` to the api import block and `app.include_router(pool.router)` beside the screener include.
- `backend/tests/test_pool_hub.py` - Hermetic fixtures (strategy_cache.json + ext concept parquet), 8 projection tests, 5 API regression tests, 4 POOL-03 guard tests (17 total).

## Decisions Made

- Followed the plan exactly: single-as_of read, 5-column projection, server-side 交叉共振, concept filter keeps `total` authoritative, zero execution authority. One fixture-order clarification documented under Deviations (the plan's sample ordering was reversed vs Python codepoint sort; the projection's determinism guarantee is locked either way).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing verification] Added case-insensitivity and service-level as_of-echo tests**
- **Found during:** Task 1 (fixture tests)
- **Issue:** The plan's verification section lists "case-insensitive substring" and "mismatched as_of does not fabricate a date" as locked truths, but its enumerated Task 1 test list did not include dedicated tests for either.
- **Fix:** Added `test_concept_filter_is_case_insensitive` (lowercase `ai` matches `AI;机器人`) and `test_build_pool_hub_echoes_cache_as_of_on_mismatch` (service-level echo; API-level covered by `test_get_pool_hub_mismatched_as_of_returns_cache_date`).
- **Files modified:** backend/tests/test_pool_hub.py
- **Verification:** 17/17 tests pass.
- **Committed in:** ee47f7f / c2a27c3

**2. [Plan-detail correction] Fixture hit_factors order aligned with Phase 17 codepoint sort**
- **Found during:** Post-Task-3 self-check against STATE.md (Phase 17 P2 note: hit_factors sorted by Unicode codepoint, 盘前强势量化 before 竞价多头).
- **Issue:** The initial fixture wrote Y's hit_factors as `["竞价多头", "盘前强势量化"]`; Phase 17's documented persisted shape is codepoint-sorted (`["盘前强势量化", "竞价多头"]`).
- **Fix:** Reordered Y's cross-strategy aggregate in both strategies; X/Z/W remain single-factor. No assertion depended on order — this is fidelity with the persistence contract.
- **Files modified:** backend/tests/test_pool_hub.py
- **Verification:** 17/17 tests pass.
- **Committed in:** 2fcdb95

**3. [Plan-detail correction] Task 1 sample order for Y's concept_board was reversed**
- **Found during:** Task 1 test authoring.
- **Issue:** The plan wrote `Y's == ["新能源","人工智能"] (sorted)`; Python codepoint sort yields `["人工智能", "新能源"]` (人 U+4EBA < 新 U+65B0).
- **Fix:** Asserted set equality `{"人工智能", "新能源"}` plus the deterministic `sorted()` invariant, with X's exact list `["人工智能"]` locked.
- **Files modified:** backend/tests/test_pool_hub.py
- **Verification:** 17/17 tests pass.
- **Committed in:** ee47f7f

---

**Total deviations:** 3 (2 plan-detail corrections, 1 added-verification)
**Impact on plan:** No scope creep; all changes are fixture-fidelity or added-verification, no production code beyond the plan's spec.

## Issues Encountered

- The edit tool (hunk application) mangled a couple of file sections mid-edit (duplicated imports in `pool_hub.py`, truncated `_SYMBOLS` dict in `test_pool_hub.py`). Both were resolved by rewriting the files cleanly; no net content loss.
- No package installs were required; no auth gates encountered.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Backend contract is live and regression-locked: `GET /api/pool/hub` returns `{as_of, updated_at, strategies: [{id, name, total, rows: [{symbol, code, open_gap, change_pct, concept_board, hit_factors, cross_resonance}]}], resonance_count}`.
- 18-02 (frontend PoolHubPage) can consume this contract; shape was confirmed with Executor1802 via hub. All NaN/Inf are null-serialized, missing values → None (UI renders `—`).
- Phase 19 (guest/VIP masking) will mask this DTO server-side at the boundary (out of scope for 18-01).

---
*Phase: 18-pool-hub*
*Completed: 2026-08-04*

## Self-Check: PASSED

Verified files exist: `backend/app/services/pool_hub.py`, `backend/app/api/pool.py`,
`backend/tests/test_pool_hub.py`, this SUMMARY.
Verified commits: `ee47f7f`, `c2a27c3`, `b0e96dc`, `2fcdb95`.
Tests: `backend/.venv/bin/python -m pytest tests/test_pool_hub.py -q` → 17 passed.
