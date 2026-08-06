# Phase 34 竞价回测解锁 — Plan Check Report

**Checker:** PlanCheckerP34 (gsd-plan-checker) · **Date:** 2026-08-06
**Scope:** Goal-backward executability review of the 3 Phase 34 plans (BT-07..10), before execution.
**Artifacts reviewed:** `REQUIREMENTS.md` (BT-07..10), `RESEARCH.md`, `34-01/02/03-PLAN.md`; precedent `32-PLAN-CHECK.md`.
**Method:** Live repo anchor spot-checks (read-only; no builds/tests run). Every file/symbol/line the plans name was verified against the current codebase. `frontend/` (incl. `Watchlist.tsx`) untouched.

---

## Verdict

| Plan | Wave | Depends | Tasks | Files | Estimate (conf) | Verdict |
|------|------|---------|-------|-------|-----------------|---------|
| 34-01 | 1 | — | 3 | 2 | 68k (medium) | **EXECUTABLE** — 2 warnings |
| 34-02 | 2 | 34-01 | 3 | 2 | 46k (high) | **EXECUTABLE** — 0 warnings |
| 34-03 | 2 | 34-01 | 4 | 7 | 82k (medium) | **EXECUTABLE** — 3 warnings |

**Overall: EXECUTABLE — 0 blockers, 5 warnings, 6 notes.** All warnings are line-ref hygiene, one naming deviation vs RESEARCH, and runtime-estimate/verify-scope clarifications — recoverable during execution; none change structure or dependencies. Estimate note (ADR-2629): confidence uncalibrated, advisory only.

---

## Requirement Coverage (BT-07..10)

| Requirement | Delivered by | Covered? |
|-------------|--------------|----------|
| BT-07 (full auction backtest: 9 strategies × aligned dates, real/derived/eod branches, honest coverage, BT-04 n_missing) | 34-01 T1/T2 (single-panel compute + persist) + 34-03 T4 (real 248-day dual run + forward spot-check vs kline_daily) | ✅ |
| BT-08 (report real branch activates `available`, real rows never derived-downgraded, symbol-level honest coverage) | 34-02 T1/T2 (coverage.symbols + n_symbols_covered/n_symbols_hit + 248-partition proof, gate zero-change) | ✅ |
| BT-09 (backtest_results lake origin/params/per-date rows + read-only query + zero-execution AST guard) | 34-01 T2 (write side) + 34-03 T2/T3 (GET-only endpoints + guard 7 items, incl. E2 root isolation) | ✅ |
| BT-10 (P2: minute-confirm limitations honestly noted) | 34-01 (per-row `minute_confirm:"not_applied"` + manifest minute_note) + 34-03 T4 (docs/features.md) | ✅ |

No requirement dropped; O1 (CLI trigger) resolved, O2 (META-default params only) resolved, O3 (concept PIT left out, honest note) resolved. **Dependencies:** 34-01 wave 1; 34-02 ∥ 34-03 wave 2, both `depends_on: [34-01]` — acyclic, wave-consistent, zero file overlap (34-01: services/auction_backtest.py + tests/test_auction_backtest.py; 34-02: services/auction_validation.py + tests/test_auction_validation_report.py; 34-03: scripts/api/main.py/tests×2/docs/SUMMARY).

---

## Executability Spot-Checks

### New files (must be created — absent today, glob-verified)

| File | Plan creates it? |
|------|------------------|
| `backend/app/services/auction_backtest.py` + `backend/tests/test_auction_backtest.py` | ✅ 34-01 (no collision — RESEARCH §10 proposed a single `test_research_backtest.py`; plan splits into service/API/guard files, internally consistent) |
| `backend/tests/test_research_backtest_guard.py` + `test_research_backtest_api.py` | ✅ 34-03 |
| `backend/scripts/auction_backtest.py` + `backend/app/api/research_backtest.py` | ✅ 34-03 (no existing script/router of that name; `probe_concept_drift.py` mirror precedent exists) |

### Backend anchors (must already exist — all verified)

| Symbol | Actual | Plan claim | Status |
|--------|--------|------------|--------|
| `attach_auction_columns_range(df,start,end,repo) -> (df, enabled_dates)` | `auction_columns.py:174-278` — partition-existence gate ONLY, probe-free (D-03 docstring), warmup contract, fail-closed skips | 34-01 Task 1 injection primitive | ✅ exact shape (W-1 line drift) |
| `strategy_fingerprint(engine)` | `pool_snapshot.py:166-177` — sha256(sorted meta + per-strategy source digests)[:16]; **this is also what produced 33's part.json `strategy_version=7affa346e5e586c5`** via `screener.py:461` | 34-01 `strategy_version` source | ✅ exact |
| Module-level pure helpers `_build_candidate_mask`(:79) / `_null_metric`(:60) / `_aggregate_metric`(:65) / `_FORWARD_METRICS`(:57) | `auction_validation.py` — module scope | 34-01 import list | ✅ exact |
| `_forward_stats` BT-04 semantics | `auction_validation.py:381-438` — global-calendar next-date (`dates[1:]+[None]`, never per-symbol shift), `next_day_open_ret=open_{T+1}/open_T−1`, `next_day_close_ret=close_{T+1}/open_T−1`, `open_gap_outcome=open_{T+1}/close_T−1`, `n_missing` counted never filled, per-metric independent n; **no `self.` state → unbound call safe** | 34-01 Task 1 unbound `_forward_stats` | ✅ exact; plan Test 2 hand-calc (0.08/0.15/0.028571) matches formulas |
| D-06 sentence 「本报告区间不受回测 186 天 guard 限制」 | `auction_validation.py:18` (module docstring) — exact string | 34-02 Task 3 grep gate | ✅ present |
| 9 auction-family ids + flags | `auction_validation.py:46-50` `_AUCTION_FAMILY_IDS`; builtin meta: fast_grab/allround/t1_flash/intraday_confirm `requires_auction_data=True`, alpha False, golden_230 `minute_confirm_required=False` | 34-01/34-02/34-03 | ✅ exact |
| `_guard_server_backtest_range` + `BACKTEST_MAX_SERVER_DAYS=186` + default-off | `api/backtest.py:29/:57-62`, `config.py:103` (`backtest_range_guard=False`) | D-06 non-application | ✅ exact |
| Engine seams | `engine.py:345-348` (auction short-circuit, column-absent only), `:376-390` (minute confirm required → empty), `main.py:551-565` (`_minute_loader` unwired) | BT-10 / intraday_confirm 恒空 | ✅ exact |
| `get_enriched_range(start,end,symbols,columns)` cache-full else None | `repository.py:966-998` | 34-01 single-panel load | ✅ exact |
| `_atomic_write_parquet` (.tmp + same-dir replace) | `auction_sync.py:45-55` | 34-01 mirror | ✅ exact |
| vectorbt flat-file precedent `run_id={id}.parquet` (no manifest) | `services/backtest.py:358-371` | 34-03 "dirs-with-manifest only" disambiguation | ✅ exact — needed, real |
| Router registration point + GET-only guard shape | `main.py` imports (:38-43 incl. `research_auction`) + include block `research.router` / `research_auction.router` adjacent (~:861-863); `research_auction.py` prefix `/api/research`, only `/auction/validation` | 34-03 insertion | ✅ exact |

### API surface — no conflict

`GET /api/research/backtest` + `/{run_id}` collide with nothing: `research.py` routes are `/dsl/*`, `/factors*`, `/hypotheses/*`, `/factor-revisions/*`, `/experiments/*`, `/comparison*`, `/strategy-executions/*`; `research_auction.py` only `/auction/validation`; `research_panels.py` only `/factor-catalog`, `/factors/…/verdict`, `/models*`, `/wf/*`. `api/backtest.py` is a different prefix (`/api/backtest`). `run_id` regex `^[0-9a-f]{12}$` matches 34-01's `sha1(...).hexdigest()[:12]`.

### Runtime / hermeticity

- `backend/.venv` present; plans add zero runtime deps (polars/fastapi/httpx locked stack only).
- Test conventions verified present in `test_auction_validation_report.py`: `repo_env`(:38), `_write_auction_partition`(:54), `_auction_rows`(:61), `_make_engine`(:87), `_seed_enriched_cache`(:103, supports `days=`/`symbols=` kwargs) — 34-01 Task 3 copy source exists.
- Suite-size claims verified: `test_auction_validation.py` = 6 tests (34-01/02/03 "守卫 6" exact), `test_attach_auction_columns_range.py` = 14, `test_auction_validation_report.py` = 16 existing + 4 new = 20.
- Existing coverage assertions are per-key (`report["coverage"]["auction_enabled_count"] == …`), never exact-dict equality → 34-02's additive `symbols` key cannot break them (plan claim validated).
- Real-lake facts: `data/kline_auction` = 248 `date=` partitions (dir listing consistent, RESEARCH counted 248/2 symbols); `data/backtest_results` = empty pre-created dir (34-03 list endpoint honest-empty path).
- 34-01's own `_evaluate_strategy_rows` computes `n_symbols_covered`/`n_symbols_hit` locally — no hidden ordering dependency on 34-02's `auction_validation` field additions; forward stats come only from unbound `_forward_stats`.

---

## Hidden-blocker sweep

| Check | Result |
|-------|--------|
| Test file named but not created | ✅ none — 4 named new files explicitly created; 3 named existing suites all present (validation report / validation / attach range are the real Phase 29 names) |
| `Watchlist.tsx` / frontend touched | ✅ none — absent from all `files_modified` |
| Write-root discipline | ✅ 34-01 E2 (backtest_results only) + 34-03 E2 guard (AST-extracted write targets) + `test_full_backtest_write_root_isolation` byte-identical lock |
| POOL-03 violated | ✅ no POST on research routers (trigger = CLI, O1); existing `test_auction_validation.py` GET-only guard unaffected |
| Circular import | ✅ acyclic — 34-01 service is a leaf; imports `auction_validation`/`auction_columns`/`pool_snapshot` (all leaf modules); 34-03 api imports fastapi/polars/stdlib only |
| Guard token collisions | ✅ 34-02's added coverage code is read-only (plan forbids write tokens; fallback "fix Task 1 code, never the guard" stated); 34-03 api guard whitelist explicitly admits `auction_validation`/`pool_snapshot` on the service side only |
| Verify command syntax | ✅ all `grep -c`/`pytest -x -q` gates well-formed; D-06 grep string verified present; `|| true` on zero-probe gate is a display gate only |

---

## Issues

### Blockers (must fix)

None.

### Warnings (should fix before execution)

**1. [line_ref] 34-01/34-02 cite drifted ranges (symbols verified — cosmetic)**
- `attach_auction_columns_range` def is `auction_columns.py:174` (plan/RESEARCH cite :160-278 — the range covers `_dir_date` + function); `_build_candidate_mask` def is `auction_validation.py:79` (34-01 read_first cites L93-152). All symbols/shapes verified exact; executors read by name.
- Fix: re-point the two ranges before execution (one-line edit in 34-01 read_first).

**2. [naming] 34-01 test file deviates from RESEARCH §10 (`test_research_backtest.py` → `test_auction_backtest.py`)**
- Deliberate split (service tests / API tests / guard) and collision-free; 34-02 Task 3 references `test_auction_backtest.py` consistently. No correction needed — record the deviation so the SUMMARY doesn't cite RESEARCH's old name.

**3. [runtime_estimate] 34-01's ~1-3 min full 248-day run is `[INFERENCE]` (RESEARCH §12 confidence MEDIUM)**
- Correctly deferred to 34-03 Task 4 measurement (Run A). Keep Run A bounded (4 EOD strategies only) and record wall-clock in 34-03-SUMMARY.md; the automated smoke (`--range 5 --symbols 000001.SZ,000002.SZ`) plus Run B (2 symbols) bound worst-case task time. Do not add new strategies to Run A.

**4. [verification_derivation] 34-03 Task 4 automated gate writes real runs into `data/backtest_results/`**
- `ls data/backtest_results/ | grep -c "run_id="` ≥ 1 is a smoke gate (reused reruns add no new dir — correct semantics); ensure the gate runs after at least one write-run, and confirm `data/` stays uncommitted (plan forbids). Consistent with 33-01 sandbox precedent.

**5. [cross_plan] 34-03 Task 4 docs cite 34-02's report-side coverage fields (semantic dep within wave 2)**
- Plan acknowledges ("语义依赖, 非文件依赖"); keep the features.md wording anchored on 34-01 manifest numbers (available at 34-03 execution time) and reference 34-02 report fields by name only, so late 34-02 merge cannot invalidate the docs.

### Notes (advisory)

**1.** `strategy_fingerprint` determinism verified: input = sorted strategy meta + strategy source bytes — same checkout → same 16-hex fingerprint; any strategy def/source change → new fingerprint → new run_id (intended: manifest fingerprint then differs, no silent reuse). 33's `7affa346e5e586c5` provenance confirmed (screener.py:461).
**2.** `_compute_run_id` input set (sorted strategy_ids, ISO start/end, sort_keys JSON params, strategy_version, sorted symbols) is time-free; `on_progress`/`job_id` explicitly excluded — idempotency holds across reruns. `sorted(symbols or [])` makes CLI full-market (None) and explicit-empty consistent.
**3.** `_forward_stats` has no instance-state dependency — the unbound-call design (34-01 must-have) is safe and keeps write-side/report-side zero-drift; 4 existing BT-04 report tests lock the same formulas.
**4.** 34-02 Task 1's `_coverage_symbols` needs `repo.store.data_dir` (same accessor `attach_auction_columns_range` uses) — mirror it rather than assuming a bare `data_dir` argument.
**5.** Write-volume bound (RESEARCH §11): derived/eod ~50 hits/day/strategy × 248 ≈ ~37k rows long-format + sparse real — parquet few-MB scale; no `limit` passthrough needed. Coverage `auction_rows_expected = enriched_symbol_count × n_dates` math is per-window, honest.
**6.** `backtest_results` currently empty → 34-03's list endpoint honest-empty path (`{runs: [], count: 0}` 200) is the first thing tested against the real lake; flat-file-skip test uses a hand-seeded `run_id=…parquet` fixture.

---

## Dimension Summary

1. Requirement coverage — ✅ PASS (BT-07..10 + O1/O2/O3 resolutions; no leakage) · 2. Task completeness — ✅ PASS (9 tasks across 3 plans; W-1 line refs) · 3. Dependency correctness — ✅ PASS (34-01 → 34-02 ∥ 34-03, acyclic, zero file overlap) · 4. Key links — ✅ PASS (service→helpers/columns/snapshot/repo, report↔backtest coverage parity, api→guard→main) · 5. Scope sanity — ✅ PASS (3/3/4 tasks, 2/2/7 files; zero new deps; zero frontend) · 6. Verification derivation — ✅ PASS (every task automated gate; W-4 smoke scope) · 7. Context compliance — ✅ PASS (honesty as tests+fields, not comments) · 8. Nyquist — ✅ PASS (all tasks carry `<automated>` verify; no watch/MISSING gates) · 9. Cross-plan contracts — ✅ PASS (import contract `_forward_stats`/helpers frozen by 34-01, 34-02 additive-only; manifest coverage.symbols ↔ report coverage.symbols same numbers; run_id layout shared by 34-01 write + 34-03 read) · 10. CLAUDE.md — SKIPPED · 11. Research — ✅ PASS (RESEARCH §4/§5/§6/§9/§10 fully consumed)

---

## Recommendation

All three plans are **EXECUTABLE** as-is, 0 blockers. Before execution starts, apply the five warning fixes (spec-hint corrections; no structural or dependency changes):

1. Re-point `attach_auction_columns_range` → `auction_columns.py:174` and `_build_candidate_mask` → `auction_validation.py:79` in 34-01 read_first.
2. Record the test-file naming deviation (RESEARCH §10 `test_research_backtest.py` → `test_auction_backtest.py` + `test_research_backtest_api.py` + `test_research_backtest_guard.py`) in the 34-01 SUMMARY.
3. Keep Run A to the 4 EOD strategies; measure and record wall-clock (do not treat the 1-3 min estimate as a guarantee).
4. Run the 34-03 Task 4 automated smoke after at least one write-run; keep `data/` uncommitted.
5. Anchor features.md on 34-01 manifest numbers; reference 34-02 report fields by name only.

Proceed to `/gsd-execute-phase 34` (wave 1: 34-01; wave 2: 34-02 + 34-03 in parallel).

---
*Plan-checked: 2026-08-06 — read-only review; no source/plan files modified; no builds/tests run; `Watchlist.tsx` untouched.*
