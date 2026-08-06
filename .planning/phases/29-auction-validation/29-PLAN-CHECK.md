# Phase 29 竞价策略历史验证 — Plan Check Report

**Checker:** PlanCheckerP29 (gsd-plan-checker)
**Date:** 2026-08-06
**Scope:** Goal-backward executability review of the 3 Phase 29 plans (BT-01..06), before execution.
**Artifacts reviewed:** `.planning/ROADMAP.md` (Phase 29), `.planning/REQUIREMENTS.md` (BT-01..06), `.planning/phases/29-auction-validation/RESEARCH.md`, `.planning/phases/29-auction-validation/PATTERNS.md`, `29-01-PLAN.md`, `29-02-PLAN.md`, `29-03-PLAN.md`.
**Method:** Live repo anchor spot-checks (read-only; no builds/tests run). Every file/symbol the plans name was verified against the current codebase; polars API semantics verified against the installed interpreter (`polars 1.40.1`).

---

## Verdict

| Plan | Wave | Depends | Tasks | Files | Estimate (conf) | Verdict |
|------|------|---------|-------|-------|-----------------|---------|
| 29-01 | 1 | — | 3 | 2 | 36k tokens (low) | **EXECUTABLE** — 1 warning |
| 29-02 | 2 | 29-01 | 3 | 2 | 63k tokens (low) | **EXECUTABLE** — 1 warning |
| 29-03 | 3 | 29-02 | 3 | 5 | 39k tokens (low) | **EXECUTABLE** — notes only |

**Overall: EXECUTABLE — 0 blockers, 2 warnings, 4 notes.**

No structural blocker prevents the phase goal. The two warnings are implementation-level traps that the plans' own acceptance tests will surface during execution (warmup-vs-cache-min clipping; equivalence-test short-history ambiguity) — each has a concrete fix below. All named files/symbols exist or are explicitly created by the plans; the dependency chain 29-01 → 29-02 → 29-03 is acyclic and wave-consistent; no POOL-03 / Watchlist / strategy_cache / import-cycle hazards found.

> **Estimate note (ADR-2629):** All three estimates carry `confidence: low` (<3 completed phases with actuals → uncalibrated for this project). `gsd-tools query estimate-check --calibrated` is **not available** in this build (verb missing) and `.planning/config.json` defines no `smart_zone_tokens`, so no budget comparison is possible — treat figures as directional only. 29-02's 63k is the densest (report-assembly service + 5-test matrix over 2 files); task/file thresholds (3 tasks, 2 files) are well inside budget, so no split is warranted.

---

## Requirement Coverage (BT-01..06)

| Requirement | Delivered by | Covered? |
|-------------|--------------|----------|
| BT-01 (GET /api/research/auction/validation, honest 200 data_gate) | 29-03 T1 (endpoint + registration) + T2 (AST guard + integration) + 29-02 T1 (service-level honest-empty) | ✅ |
| BT-02 (`attach_auction_columns_range` vectorized primitive) | 29-01 T1 (vertical slice) + T2 (equivalence property) + T3 (boundaries) | ✅ |
| BT-03 (per-strategy rows, honest n_dates==0, branch labels) | 29-02 T1 (assembly) + T3 (window/skipped/coverage) | ✅ |
| BT-04 (forward-outcome semantics locked) | 29-02 T2 (formula assertions + n_missing_outcomes) + T3 | ✅ |
| BT-05 (mutually-exclusive branch labels) | 29-02 T1 (branch selection) + T3 (auction_alpha flip test) | ✅ |
| BT-06 (zero-execution + zero-dependency AST guard) | 29-03 T2 (`tests/test_auction_validation.py` 6 guard tests) + T3 (regression lock) | ✅ |

- All 6 roadmap requirements map to at least one task; none dropped. ROADMAP mapping (29-01→BT-02, 29-02→BT-03/04/05, 29-03→BT-01/06) matches plan frontmatter exactly.
- No deferred-idea leakage: BT-07 (full auction backtest) is correctly excluded — ROADMAP explicitly defers it to v2.3+ and every plan states D-08 (backtest seam untouched).
- No scope reduction: BT-01 vs BT-05 reconciliation (strategies always carries all 9; `strategies==[]` only when enriched window empty) is locked in RESEARCH §5 and implemented in 29-02 must_haves/action + 29-03 integration test — the "shadow delivery" failure mode is closed.

---

## Executability Spot-Checks (live repo anchors)

### New files (must be created by the plan — verified the plan says so)

| File | Plan creates it? |
|------|------------------|
| `backend/tests/test_attach_auction_columns_range.py` | ✅ 29-01 T1/T2/T3 (does not exist today) |
| `backend/app/services/auction_validation.py` | ✅ 29-02 T1 (does not exist today) |
| `backend/tests/test_auction_validation_report.py` | ✅ 29-02 T1 (does not exist today) + 29-03 T2 extends it (same file, wave-ordered) |
| `backend/app/api/research_auction.py` | ✅ 29-03 T1 (does not exist today) |
| `backend/tests/test_auction_validation.py` | ✅ 29-03 T2 (does not exist today) |

### Backend anchors (must already exist — all verified)

| Symbol | Actual location | Plan claim | Status |
|--------|-----------------|------------|--------|
| `attach_auction_columns` (dual-gate injector) | `auction_columns.py:89-151` | 29-01 `:89-151` | ✅ exact |
| `_attach_auction_volume_ratio` (PIT-safe denominator) | `auction_columns.py:54-87` | 29-01 `:60-87` | ⚠️ stale line, symbol ✅ |
| `compute_auction_unmatched_amount` | `auction_columns.py:35-51` | 29-01 `:44-58` | ⚠️ stale line, symbol ✅ |
| `_AUCTION_REAL_COLS` / `_AUCTION_UNMATCHED_AMOUNT_COL` / `_AUCTION_VOLUME_RATIO_COL` / `_AUCTION_UNMATCHED_VOLUME_COL` / `_AUCTION_VIRTUAL_PRICE_COL` | `auction_columns.py:26-32` | 29-01 must_haves / action | ✅ |
| Module docstring 「绝不写湖」 | `auction_columns.py:11` | 29-01 (keep) | ✅ |
| `_dir_date` (copy source for new helper) | `auction_history.py:59-66` | 29-01 `:61-66` | ⚠️ stale line, symbol ✅ |
| `repo.store.data_dir` + `kline_auction/date=*` scan pattern | `repository.py:290` (`self.store`), `:485` (same dir-glob shape) | 29-01 action 3b | ✅ |
| `get_enriched_history` trading-day slice + warmup gate | `repository.py:937-964` — gate = `(lookback_days+60)*2` = **132 natural days** | 29-01 T2 "132 自然日 warmup-start 校验" | ✅ exact (claim verified: `(6+60)*2 = 132`) |
| `get_enriched_range(start, end, symbols=None, columns=None)` → None-on-non-coverage, sorts by symbol/date | `repository.py:966-998` | 29-02 action 4b | ✅ (⚠️ see W-1 for the None semantics trap) |
| `_enriched_history_cache` (direct seed target) | `repository.py:305` | 29-01 T2 / 29-02 T1 `_seed_enriched_cache` | ✅ |
| `_build_candidate_filter_mask` (filter_fn path + fail-closed) | `backtest/strategy.py:522-570` | 29-02 `:522-570` | ✅ exact |
| `StrategyDef` (meta/filter_fn/filter_history_fn/minute_confirm_fn) | `engine.py:115-118+` | 29-02 `_build_candidate_mask` | ✅ |
| `StrategyEngine.__init__(enriched_loader, enriched_history_loader, strategy_dirs, minute_loader)` | `engine.py:151-154` | 29-02 `_make_engine()` construction shape | ✅ |
| `engine._strategies` (dict[str, StrategyDef]) / `list_strategies()` / `get()` raising ValueError | `engine.py:162/275-285` | 29-02 action 4e | ✅ |
| `requires_auction_data` short-circuit | `engine.py:345-348` | 29-02 must_haves / PATTERNS | ✅ exact |
| `meta["params"]` normalization (META-default param dict source) | `engine.py:227-229` | 29-02 action 4f | ✅ |
| `run_all_with_hits` enumeration + `except (ValueError, Exception): continue` | `screener.py:723-750, 799-800` | 29-02 action 4e (mirror) | ✅ |
| `probe_resolver` injection + `to_dict()` passthrough | `premarket_pool.py:62-68` (param at :35) | 29-02 `:45-57` / 29-03 | ⚠️ stale line, pattern ✅ |
| `resolved_as_of` authority echo | `pool_hub.py:281` | 29-02 Task 3 read_first `:319-321` | ⚠️ stale line, pattern ✅ |
| `resolve_auction_probe` / `AuctionProbeVerdict.to_dict` / `AuctionProbeStatus` | `auction_probe.py:139 / 41-51 / 33-36` | 29-02/29-03 probe passthrough | ✅ |
| `BACKTEST_MAX_SERVER_DAYS=186` / `_guard_server_backtest_range` | `backtest.py:29 / 57-63` | 29-02/29-03 D-06 (must NOT apply) | ✅ |
| `settings.backtest_range_guard` default False | `config.py:103` | RESEARCH §2.3.1 / 29-02 | ✅ |
| `api/research.py` router prefix + `_bad_request` | `research.py:14 / 86-87` | 29-03 `:86-87` | ✅ exact (PATTERNS.md `:48-49` is stale — plan is right) |
| `main.py` `from app.api import (` block / `include_router(research.router)` / `app.state.repo` / `app.state.strategy_engine` / `_GUEST_READ_GET_PATHS` | `main.py:20-44 / 856 / 129 / 563 / 779` | 29-03 T1 (insert after :856, no whitelist change) | ✅ |
| POOL-03 guard shapes (`_EXECUTION_TOKEN` / `_WRITE_PATTERNS` / `_feature_sources` / `_imported_module_names` / E1/E3/E4/E5) | `test_pool_hub.py:857-963` | 29-03 T2 (copy source) | ✅ exact |
| `auction_history.py` guard section (single-file `_feature_sources` variant) | `test_auction_history.py:285+` | 29-03 T2 (mirror) | ✅ |
| Hermetic helpers (`repo_env` / `_patch_probe` / `_write_auction_partition` / `_auction_rows`) | `test_auction_columns.py:20-73` | 29-01/29-02 (copy shape) | ✅ |
| `_make_client` minimal-app pattern | `test_auction_history.py:78-93` | 29-03 T2 | ✅ |
| Regression-lock test files | `test_pool_hub.py`, `test_auction_history.py`, `test_auction_columns.py`, `test_auction_probe.py`, `test_auction_sync.py`, `test_auction_strategies.py`, `test_auction_strategy_family.py`, `test_auction_strategy_family_p2.py`, `tests/research/test_research_api.py`, `tests/backtest/` | 29-03 T3 verify | ✅ all present |
| docs insertion anchor (`---` before `## 📊 指标流水线`) | `docs/features.md:57-59` | 29-03 T3 `:44-52` | ✅ (anchor exists) |
| Builtin auction-family strategies (9 files) | `strategy/builtin/auction_*.py` + `golden_230.py` | 29-02 `_AUCTION_FAMILY_IDS` | ✅ all 9 present |
| polars vectorized window precedent (`.over("symbol")` + `rolling_mean`) | `indicators/pipeline.py:374`, `shadow/production.py:142`, `factor_dsl.py:575` (`min_samples`) | 29-01 action 3h | ✅ (⚠️ see N-1) |

### Runtime environment

- `backend/.venv` present; `polars 1.40.1` importable. `rolling_mean(5, min_periods=1)` **works** (deprecated alias, renamed `min_samples` in 1.21.0); short-history semantics verified live: group-first row → null, N<5 prior rows → mean of available (matches single-day `tail(5).mean()`). Pytest config has **no** `filterwarnings=error` → the deprecation warning cannot fail tests.
- `Watchlist.tsx` exists at `frontend/src/pages/Watchlist.tsx`; **absent from all `files_modified`** (D-05) ✅ not touched.
- No `CLAUDE.md` / `.claude/skills` / `.agents/skills` in repo root → Dimension 10 (CLAUDE.md compliance) **SKIPPED**.
- STATE.md: Phase 29 is current, no error state ✅.

---

## Hidden-blocker sweep (assignment item 2d)

| Check | Result |
|-------|--------|
| Plan names a test file that doesn't exist AND doesn't say it creates it | ✅ none — `test_attach_auction_columns_range.py`, `test_auction_validation_report.py`, `test_auction_validation.py` all explicitly created (29-01/29-02/29-03); every verify command references a file that either exists today or is created earlier in the wave chain |
| Plan touches `Watchlist.tsx` | ✅ none — D-05 explicit in all three plans; `frontend/` absent from all `files_modified` |
| Plan implies writing `strategy_cache` | ✅ none — BT-06 guard bans the reference; 29-02 T1 mandates concept-word docstring discipline («单 as_of 运行期缓存指针») so the source never contains the literal; 29-03 T2 Test 5 asserts source+import absence |
| POOL-03 guard violated | ✅ none — new modules stay GET-only / zero-write; import whitelist enforced by 29-03 T2 Test 6 (`{polars, fastapi, app.services.auction_probe, app.tickflow.repository, app.strategy.engine, app.services.auction_columns, app.services.auction_validation, __future__ + stdlib}`); 29-02/29-03 docstrings forbid write/call-token literals (run_all/write_parquet/…) |
| Circular import / forbidden import | ✅ none — `auction_validation.py` imports only whitelisted modules; the candidate-mask mirror is **documented-in-docstring, never imported** from `app.backtest` (29-02 key_links + action 4g confirm; `backtest/strategy.py` anchor `:522-570` cited but no import). `auction_columns.py` gains zero new imports (D-01) |
| `research_auction` API registration point exists | ✅ `main.py:856` `app.include_router(research.router)` — 29-03 T1 inserts `research_auction.router` immediately after; `from app.api import (` block at :20-44 accepts the new member |
| Probe gating contradiction (REV-01) | ✅ none — range primitive deliberately drops the probe gate (partition existence is the historical gate, documented in docstring per D-03); probe is passthrough-only in the report. This matches RESEARCH §1.6/§2.1.1 and REV-01 |
| 186-day guard conflict | ✅ none — D-06 locked: window clamps to enriched cache bounds + `window.requested_*/effective_*` echo; guard (default-off at `config.py:103`) explicitly NOT applied |

---

## Issues

### Blockers (must fix)

None.

### Warnings (should fix before execution)

**1. [dependency_correctness / data_contract] 29-02 T1 action 4b — `warmup_start` below `cache_min` makes `get_enriched_range` return `None` → false `enriched_unavailable`**
- `get_enriched_range` (`repository.py:966-998`) returns `None` when `cache_min > start or cache_max < end`. The plan clamps the requested window to `[cache_min, cache_max]`, then computes `warmup_start = start − 14 自然日` and calls `get_enriched_range(warmup_start, end, ...)`. Whenever the effective `start` is within 14 days of `cache_min` (e.g. a full-coverage request `[cache_min, cache_max]`, which is exactly what 29-02 T3 Test 1 constructs for the over-coverage clamp), `warmup_start < cache_min` → `None` → the report returns `{"empty_reason":"enriched_unavailable"}` instead of a clamped report. The plan's own Task 3 Test 1 (effective_start == cache_min with a working report) would fail.
- Fix: `warmup_start = max(start − timedelta(days=14), cache_min)` in `auction_validation.py` (first enabled day's denominator then degrades honestly to null per RESEARCH §2.1.4 — documented degradation, not data loss), or load `get_enriched_range(cache_min, end)` and slice. Add one line to 29-02 T1 action 4b and a note in 29-02 T3 Test 1 asserting the warmup-clamp behavior. Same fix should be reflected in RESEARCH §2.2.1 for the next planner pass.

**2. [verification_derivation] 29-01 T2 Test 1 — "覆盖 1-4 日前导的短历史行" contradicts the equivalence premise**
- The equivalence assertion `abs(ranged_ratio − single_ratio) < 1e-9` only holds when the range panel and the seeded `_enriched_history_cache` carry the **same prior rows** for the compared (symbol, date). The plan seeds a 140-day cache but calls `attach_auction_columns_range(full_panel, start=07-30, end=08-03, repo)`; if `full_panel` is the full 140-day frame, the equivalence holds but **no short-history rows exist** in the comparison (every enabled date has ≥5 prior panel rows), so the "1-4 日前导" claim in the same test is unreachable; if the executor instead passes a trimmed panel (07-27..07-31 like T1's fixture) to create short-history rows, those rows' range-ratio uses ≤4 prior rows while the single-day path reads 5 from the fuller cache → the `<1e-9` assertion **fails** and the executor chases a phantom bug.
- Fix: scope the equivalence test to enabled dates with ≥5 prior **panel** rows (full-panel input — equivalence holds); verify the 1-4-prior behavior with hand-computed means (as Task 1 Test 1 and Task 2 Test 3 already do) or seed the cache and panel from the same trimmed slice. Add one sentence to 29-01 T2 Test 1 behavior clarifying that short-history equivalence requires cache and panel to agree on prior rows.

### Notes (advisory)

**1. All three plans + RESEARCH/PATTERNS — `rolling_mean(5, min_periods=1)` is a deprecated polars kwarg**
Installed `polars 1.40.1` renamed `min_periods` → `min_samples` in 1.21.0; the alias still works and pytest has no `-W error`, so nothing breaks. Repo convention (e.g. `factor_dsl.py:575` `min_samples=1`, `shadow/production.py:142` `rolling_mean(window_size=20)`) uses the current name. Recommend switching `min_periods=1` → `min_samples=1` in 29-01 must_haves/key_links/action 3h (and RESEARCH §2.1/PATTERNS) to keep the code warning-free and convention-consistent.

**2. RESEARCH.md §9 「遗留开放问题」 not marked `(RESOLVED)`**
All 5 items are answered by the plans: (1) historical auction availability → honest-empty design (29-02 D-02); (2) `minute_confirm` → explicit `"not_applied"` for all 9 (29-02 must_haves); (3) `per_date` volume → returned as-is (29-02 action 4h); (4) Phase 24 replay → not this phase; (5) frontend → none (D-05). Recommend renaming the section to 「遗留开放问题 (RESOLVED)」 with one-line resolutions for audit-trail cleanliness (Dimension 11).

**3. PATTERNS.md stale line citations** — `_bad_request` `:48-49` (actual `:86-87` — the plans are correct), `pool_hub` echo `:319-321` (actual `:281`), `auction_history._dir_date` `:61-66` (actual `:59-66`), `premarket_pool` probe `:45-57` (actual `:62-68`), `auction_columns._attach_auction_volume_ratio` `:60-87` (actual `:54-87`), `compute_auction_unmatched_amount` `:44-58` (actual `:35-51`). All symbols exist; executors re-read files by name, so this is accuracy hygiene, not a blocker.

**4. 29-02 estimate 63k tokens (confidence low)** — the densest of the three (report-assembly service + 5-test matrix, 2 files, 3 tasks). No `smart_zone_tokens` budget is configured in `.planning/config.json` and `estimate-check` is unavailable in this gsd-tools build, so no calibrated comparison is possible. Within task/file thresholds → no split required; flag only so the team tracks actuals against it for future calibration.

---

## Dimension Summary

| Dimension | Result |
|-----------|--------|
| 1. Requirement coverage (BT-01..06) | ✅ PASS — all 6 covered across 29-01/02/03; BT-07 correctly excluded; no scope reduction |
| 2. Task completeness (files/action/verify/done per task) | ✅ PASS — 9/9 tasks complete (tracer/auto + tdd shapes all present); verify commands concrete and runnable |
| 3. Dependency correctness | ✅ PASS — 29-01 wave1 → 29-02 wave2 → 29-03 wave3; acyclic; no forward refs; shared test file extension ordered by depends_on |
| 4. Key links planned | ✅ PASS — primitive→lake (glob+_dir_date), primitive→volume denominator, service→primitive, service→engine/repository, endpoint→service/probe, main.py→router, guard→sources |
| 5. Scope sanity | ✅ PASS — 3/3/3 tasks, 2/2/5 files; estimates advisory (low confidence, no budget configured) |
| 6. Verification derivation | ✅ PASS — truths user-observable (honest data_gate, per-value ratio equality, branch mutual exclusion, formula lock); W-2 refines one test's reachable coverage |
| 7. Context compliance | ✅ PASS — no CONTEXT.md in repo; plans implement D-01..D-08 research decisions faithfully; no deferred-idea leakage (BT-07, replay, frontend all excluded) |
| 7c. Architectural tier compliance | SKIPPED — RESEARCH.md has no Architectural Responsibility Map |
| 8. Nyquist | SKIPPED (no 「Validation Architecture」 section in RESEARCH.md) — informally ✅: every task has `<automated>` verify, no watch flags, no MISSING refs, no 30s+ gates |
| 9. Cross-plan data contracts | ✅ PASS — `attach_auction_columns_range(df,start,end,repo)->(df,enabled_dates)` and `build_report(*,start,end,strategy_ids,symbols)->dict` contracts consistent across waves; no conflicting transforms (W-1 is a service-internal clipping fix, not a cross-plan contract break) |
| 10. CLAUDE.md compliance | SKIPPED — no CLAUDE.md in repo |
| 11. Research resolution | ✅ PASS (see N-2 — all 5 open questions answered in plans; recommend (RESOLVED) marker) |
| 12. Pattern compliance | ✅ PASS — 7/7 files mapped in PATTERNS.md; plans reference analogs (self-analog `attach_auction_columns`, `pool_hub`/`premarket_pool`/`screener` service shapes, `auction_history` API template, `test_pool_hub` guard); mirror-not-import discipline for `backtest/strategy.py` |
| Verify command format sanity | ✅ PASS — no `^`-anchored package-manager greps, no `2>/dev/null || echo` comparisons, no `|| true`; `grep -c` gates fail-closed on zero; numeric assertions are hand-derived in-test (BT-04 formulas) or structural (router methods) |

---

## Recommendation

All three plans are **EXECUTABLE** as-is, with 0 blockers. Before execution starts, apply the two warning fixes (implementation-level, no structural or dependency changes):

1. 29-02 T1 action 4b: clamp `warmup_start = max(start − 14d, cache_min)` (or load from `cache_min` and slice) so windows near the cache edge produce clamped reports instead of false `enriched_unavailable`; assert the clamp in T3 Test 1.
2. 29-01 T2 Test 1: clarify that the equivalence assertion applies to dates with ≥5 prior panel rows (full-panel input) and that 1-4-prior behavior is verified via hand-computed means (T1 Test 1 / T2 Test 3) — or seed cache and panel from the same slice.

Recommended (non-blocking): apply `min_samples=1` (N-1), mark RESEARCH §9 (RESOLVED) (N-2), refresh PATTERNS.md line refs (N-3).

Proceed to `/gsd-execute-phase 29` (wave 1: 29-01; wave 2: 29-02; wave 3: 29-03, sequential).

---
*Plan-checked: 2026-08-06 — read-only review; no source/plan files modified; no builds/tests run; `Watchlist.tsx` untouched.*
