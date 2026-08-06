---
phase: 29-auction-validation
verified: 2026-08-06T13:02:46Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 29: 竞价策略历史验证 (Auction Strategy Validation) Verification Report

**Phase Goal:** The 9 auction/pre-open strategies gain a historical signal-quality validation — a read-only `GET /api/research/auction/validation` report over `kline_auction`-enabled dates (honest `data_gate` when the lake is empty), built on a new vectorized `attach_auction_columns_range` primitive; derived/EOD-proxy branches validated on enriched history with mutually-exclusive branch labels; zero execution, zero new deps.
**Verified:** 2026-08-06T13:02:46Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth (ROADMAP Success Criterion) | Status     | Evidence |
| --- | -------------------------------- | ---------- | -------- |
| 1   | Empty lake / probe unavailable → 200 `{data_gate:"empty", coverage:0}` (never 404/500); enabled dates = `kline_auction` partitions ∩ enriched | ✓ VERIFIED | `auction_validation.py build_report` returns 200-shaped `_empty_report` on every empty path (`enriched_unavailable` / `no_dates_in_window` / `no_auction_partitions`) — never raises for empty states; only 400 is the `start > end` parameter error. `auction_enabled_dates = sorted(set(enabled_dates) & set(enriched_dates))` (partition glob ∩ enriched). Endpoint handler returns the dict directly (FastAPI → 200). Locked by `test_empty_lake_honest_report_all_9_strategies`, `test_enriched_unavailable_empty_cache`, `test_endpoint_empty_lake_full_shape_200`, `test_endpoint_available_gate_with_partitions` (available + coverage>0 when partitions exist), `test_probe_passthrough_not_gate`. Reported pass: orchestrator spot-check 50/50 (validation/columns tests). |
| 2   | `attach_auction_columns_range` is vectorized, PIT-safe denominator, no null-as-present, never touches the governed frozen-panel seam | ✓ VERIFIED | `auction_columns.py:174-276`: vectorized `with_columns(auction_volume / volume.shift(1).rolling_mean(5, min_samples=1).over("symbol"))`; partition-existence primary gate (glob `date=*/part.parquet`, `_dir_date` strict parse, unreadable/empty/missing-symbol partitions skipped fail-closed); per-partition `unique(subset=["symbol"], keep="last")` (09:25 final match); keep-list left join preserves df rows; missing partition day → column absent, never null-as-present; warmup rows (`date >= start` filter after ratio) only feed the denominator; honest `(df, [])` on empty lake/no partitions/empty panel; module imports only `auction_probe` + `tickflow.repository` — zero backtest seam access. Locked by 14 tests incl. `test_range_ratio_equivalent_to_single_day` (<1e-9 per enabled date vs single-day path), `test_range_bad_dir_and_empty_partition_skipped`, `test_range_fanout_dedup_keeps_last_row`, `test_range_warmup_contract_full_denominator`. |
| 3   | Per-strategy `{branch, n_dates, n_hits, coverage, forward_stats, per_date, data_gate}`; real-column strategies report `n_dates==0` honestly when lake empty (never downgraded); derived/EOD branches validated with explicit labels | ✓ VERIFIED | `_evaluate_strategy` returns `{id, name, branch, requires_auction_data, minute_confirm, params, n_dates, n_hits, coverage, n_missing_outcomes, forward_stats, per_date}` with `data_gate` at report top level (settled schema, RESEARCH §4); `requires_auction_data` strategies (fast_grab/allround/t1_flash/intraday_confirm — verified in builtin metas) branch `"real"` always, empty eval panel → `n_dates==0`, no mask call, never downgraded; `auction_alpha` (meta `requires_auction_data: False` — verified) flips `real|derived` by enabled-date presence; 4 EOD proxies always `"eod"` with real stats on enriched window. Locked by `test_empty_lake_honest_report_all_9_strategies`, `test_auction_alpha_branch_flip_mutual_exclusion`, `test_per_strategy_coverage_and_minute_confirm`, `test_endpoint_empty_lake_full_shape_200`. |
| 4   | Forward-outcome semantics locked (BT-04: T-open entry, next-day open/close rets, open_gap_outcome); missing outcomes counted in `n_missing_outcomes`, never filled | ✓ VERIFIED | `_forward_stats`: outcome day = global trading-calendar next-date via calendar-frame join (`dates[1:] + [None]`), never per-symbol `shift(-1)`; formulas exactly `next_open/open−1` (open>0), `next_close/open−1` (open>0), `next_open/close−1` (close non-null >0); missing outcome rows → `n_missing_outcomes` count via `next_open.is_null()`, stats exclude them, `otherwise(None)` + `drop_nulls()` — never 0-filled/forward-filled; per-metric independent n. Locked by `test_forward_formula_next_day_returns` (hand-computed 0.08/0.05/0.10/0.075/gap), `test_outcome_missing_halted_symbol_no_zero_fill` (null metrics, not 0), `test_outcome_global_calendar_next_date_not_shift`, `test_forward_close_t_boundary_independent_n`, `test_endpoint_forward_stats_branch_minute_confirm`. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/app/services/auction_columns.py` | `attach_auction_columns_range(df, start, end, repo) -> (df, enabled_dates)` + `_dir_date` (BT-02) | ✓ VERIFIED | +126 lines (0 deletions to single-day code); vectorized PIT-safe ratio, partition-existence gate, per-partition dedupe, warmup trim, honest empties; zero new imports |
| `backend/app/services/auction_validation.py` | `AuctionValidationService.build_report` (BT-03/04/05) | ✓ VERIFIED | 437 lines; window parse/clamp with requested/effective echo, warmup clamp `max(start−14d, cache_min)` (PLAN-CHECK W1 applied), `get_enriched_range` fast path, mirrored candidate mask (docstring anchor `backtest/strategy.py:522-570`, no `app.backtest` import), 9-strategy enumeration with META-default params, branch mutual exclusion, BT-04 forward stats, per_date, honest empty states |
| `backend/app/api/research_auction.py` | GET `/api/research/auction/validation` (BT-01) | ✓ VERIFIED | 72 lines; GET-only router, `_bad_request` (research.py:86-87 verbatim), `_split_csv`, `start>end`→400, bad date→422, service assembly with probe passthrough; guest whitelist untouched (endpoint behind full auth → 401 for guests, per plan D-05 — no guest masking by design) |
| `backend/app/main.py` | Registration | ✓ VERIFIED | import `research_auction` (L38) + `app.include_router(research_auction.router)` (L859) immediately after `research.router` (L857); no guest whitelist change |
| `backend/tests/test_auction_validation.py` | POOL-03 AST guards (BT-06) | ✓ VERIFIED | 6 guards: existence (anti-dangling), no execution/forbidden imports, GET-only, no write patterns + no forbidden call tokens, no `strategy_cache`/`write_cache` literal (import surface + source), import whitelist (prefix set + exact set incl. `collections.abc`); standalone constants mirroring test_pool_hub.py:857-963 |
| `backend/tests/test_attach_auction_columns_range.py` | BT-02 unit tests | ✓ VERIFIED | 14 tests; end-to-end injection, empty-lake/no-partition/empty-panel honest states, equivalence property (<1e-9), leading/warmup null contract, boundary robustness |
| `backend/tests/test_auction_validation_report.py` | BT-03/04/05 service + endpoint tests | ✓ VERIFIED | 16 tests (12 service + 4 endpoint integration via `_make_client` minimal app + real StrategyEngine); empty-lake full shape, enriched empty states, probe passthrough, hand-computed BT-04 formulas, window clamp echo, branch flip mutual exclusion, skipped_ids, coverage/per_date/minute_confirm, symbols filter, param matrix 400/422 |
| `docs/features.md` | Auction validation section | ✓ VERIFIED | 「🧪 竞价策略历史验证」 section (L52-62): honest data gate, branch labels, BT-04 formulas, honest boundaries, no frontend |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `auction_columns.attach_auction_columns_range` | `kline_auction/date=*/part.parquet` lake | glob scan + `_dir_date` parse → per-partition read (partition-existence gate) | ✓ WIRED | Verified in source (L185-222); probe deliberately NOT consumed (D-03/REV-01) |
| `auction_validation.build_report` | `attach_auction_columns_range` | import + call `(panel, start, end, repo)` → `(verification_panel, enabled_dates)` | ✓ WIRED | Verified (L15 import, L196-197 call) |
| `auction_validation.build_report` | `repo.get_enriched_range` fast path | warmup panel load with W1 clamp; None/empty → honest `enriched_unavailable` | ✓ WIRED | Verified (L184-190); None semantics confirmed in repository.py:966-998 |
| `auction_validation._build_candidate_mask` | `backtest/strategy.py:522-570` filter_fn semantics | mirrored implementation with docstring anchor — **never imported** | ✓ WIRED | Verified (L79-102): `fill_null(False).cast(Boolean)`, fail-closed all-False on exception, no `app.backtest` import in module |
| `auction_validation` | `StrategyEngine` (9 builtin strategies) | `engine._strategies`/`get()`; `requires_auction_data` metas verified | ✓ WIRED | All 9 builtin files exist; 4 real + alpha + 4 eod match branch logic |
| `research_auction.auction_validation` | `AuctionValidationService.build_report` | handler → service assembly; probe via service `probe_resolver` | ✓ WIRED | Verified (L58-64) |
| `main.py` | `research_auction.router` | import + include_router | ✓ WIRED | Verified (L38, L859) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `attach_auction_columns_range` | auction columns + `auction_volume_ratio` | real `kline_auction` parquet partitions (glob) + df volume | Yes — reads actual partition files; no static/empty returns (empty states are honest `(df, [])` with distinct reasons) | ✓ FLOWING |
| `build_report` coverage/enriched_dates | `verification_panel` | `repo.get_enriched_range` (enriched history cache; fallback dir scan) | Yes — real cache data; `None` → honest `enriched_unavailable`, never fabricated | ✓ FLOWING |
| per-strategy stats | hits via `_build_candidate_mask` | engine `filter_fn` over real panel rows | Yes — real filter evaluation, fail-closed on exception | ✓ FLOWING |
| endpoint response | `build_report` dict | full service chain | Yes — no hardcoded `[]`/`{}` except honest empty reasons | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Test execution | — | Not run — acceptance explicitly forbids running tests (`Do NOT modify source/run builds/tests`) | ? SKIP |
| Corroboration | Orchestrator spot-check | 50 passed (validation/columns tests = 6 guard + 16 report + 14 range + 14 columns regression) — reported by orchestrator, not self-executed | ✓ PASS (reported) |
| Corroboration | Executor full regression | 248 passed + test_pool_hub 35 — reported in 29-03-SUMMARY | ✓ PASS (reported) |

### Probe Execution

Step 7c: SKIPPED — Phase 29 declares no probe scripts (no `scripts/*/tests/probe-*.sh` referenced in any PLAN/SUMMARY; the phase is service/endpoint code verified via pytest, not probe-based tooling).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| BT-01 | 29-03 (endpoint) + 29-02 (service honest-empty) | Read-only GET endpoint, honest data gate, never 404/500 | ✓ SATISFIED | `research_auction.py` GET-only handler; `_empty_report` 200 shape; `test_endpoint_empty_lake_full_shape_200` + `test_endpoint_available_gate_with_partitions` |
| BT-02 | 29-01 | Vectorized range injector, PIT-safe denominator, no null-as-present, no backtest seam | ✓ SATISFIED | `attach_auction_columns_range` + `_dir_date`; equivalence property test; 14 tests green |
| BT-03 | 29-02 | Per-strategy report rows, honest `n_dates==0`, branch labels | ✓ SATISFIED | `_evaluate_strategy` row shape; `test_empty_lake_honest_report_all_9_strategies`, `test_skipped_ids_and_empty_list`, `test_per_strategy_coverage_and_minute_confirm` |
| BT-04 | 29-02 | Forward-outcome semantics locked, `n_missing_outcomes` never filled | ✓ SATISFIED | `_forward_stats` global-calendar next-date + 3 formulas; 4 tests + endpoint re-verification |
| BT-05 | 29-02 | Branch labels mutually exclusive per strategy | ✓ SATISFIED | Branch selection in `_evaluate_strategy`; `test_auction_alpha_branch_flip_mutual_exclusion`; endpoint tests assert single branch per strategy |
| BT-06 | 29-03 | Zero-execution + zero-dependency AST guard | ✓ SATISFIED | `test_auction_validation.py` 6 guards (existence/imports/GET-only/writes/cache-ref/whitelist); guard targets contain zero forbidden tokens (grep-verified); test_pool_hub.py 35 tests unchanged |
| BT-07 | — (deferred to v2.3+ per ROADMAP) | Full auction backtest | ✓ NOT IMPLEMENTED (by design) | Phase diff (`ba9412b..HEAD`) contains zero `backend/app/backtest/` changes; ROADMAP explicitly defers |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | None found | — | Debt-marker scan (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) over all phase-modified files: zero matches; no skip/xfail markers in new tests; no stub returns (empty states are honest, reason-carrying dicts) |

### Honesty Invariants (assignment item 3)

| Invariant | Status | Evidence |
| --------- | ------ | -------- |
| Empty lake → `data_gate:"empty"` 200, never 404/500 | ✓ | `_empty_report` + handler return; only 400 is the `start>end` param error; empty states never raise |
| Real strategies `n_dates==0` never downgraded to derived | ✓ | `requires_auction_data` → branch `"real"` always, empty eval panel short-circuits to `n_dates=0` without mask call |
| Derived/EOD branches explicitly labeled | ✓ | `branch ∈ {real, derived, eod}`; alpha flip; 4 eod proxies; `minute_confirm:"not_applied"` explicit |
| No `strategy_cache` / `screener_results` writes | ✓ | AST guard test 5 + zero forbidden tokens in guard targets (grep-verified); module docstrings use concept words |
| `Watchlist.tsx` untouched by phase commits | ✓ | `git log` — last commit touching it is `c9f01ba` (pre-phase); phase diff contains no `frontend/` paths; worktree `M` modification is pre-existing, documented in 29-03-SUMMARY, left uncommitted for its owner |
| BT-07 not implemented (deferred) | ✓ | Zero `backtest/` changes in phase diff; ROADMAP defers to v2.3+ |
| Zero new dependencies | ✓ | No requirements/pyproject/package files changed in phase diff; `tech-stack.added: []` in all 3 summaries (verified against diff) |

### Human Verification Required

None. All four success criteria are backed by substantive tests (hand-computed value assertions) that were independently run by the orchestrator (50/50 passed spot-check; executor full regression 248 + pool_hub 35 reported). No UI, real-time, or external-service behavior is in scope (pure read-only backend report; probe is passthrough-only).

### Notes (informational, non-blocking)

1. **SC3 per-strategy field list** — ROADMAP wording lists `data_gate` inside the per-strategy row; the implemented (and RESEARCH §4-settled) schema carries `data_gate` at report top level with per-strategy rows carrying `branch/n_dates/n_hits/coverage/forward_stats/per_date/n_missing_outcomes/minute_confirm`. Intent (honest per-strategy reporting with gate context) fully realized; endpoint integration tests assert the full shape.
2. **BT-01 "probe unavailable → data_gate:empty" wording** — superseded by design decision REV-01/D-03 (probe is a live-source probe with no information about historical partitions; partition existence is the historical gate; probe passed through for transparency). Documented in RESEARCH §1.6/§2.1.1 and the plan-check; implementation consistent.
3. **ROADMAP Phase 29 checkbox** (L44) still `[ ]` and milestone table (L207) shows "Planned" — bookkeeping owned by the workflow phase-completion step (Phase 28 was marked `[x]` at its completion). Informational.
4. **Pre-existing worktree modification** `M frontend/src/pages/Watchlist.tsx` (portal dropdown fix, +83/−50) — not part of Phase 29 commits; executor documented it and left it uncommitted; ownership pending (noted in 29-03-SUMMARY deviation 2).

### Gaps Summary

None. Phase goal achieved: all 4 roadmap success criteria verified against the actual codebase, all 6 requirements (BT-01..06) satisfied with test evidence, honesty invariants hold, zero blockers.

---

_Verified: 2026-08-06T13:02:46Z_
_Verifier: Claude (gsd-verifier)_
