# Phase 34 Research: 竞价回测解锁 (BT-07 Full Auction Backtest)

**Phase:** 34-auction-backtest · **Requirements:** BT-07..10 (BT-10 P2)
**Researched:** 2026-08-06 · **Researcher:** ResearcherP34
**Confidence:** HIGH on seam map + root cause (verified against live code + real lake); HIGH on runtime (33-01 measured); MEDIUM on write-volume/schema choices (design, not measured)

---

## 0. Verdict

**BT-07..10 are implementable now with zero new deps and zero changes to the guarded read-only seams.** The 33-run "0 rows for real-column strategies" is NOT a gate failure and NOT the `requires_auction_data` short-circuit — it is the **honest sparse-lake outcome**: probe was `available`, auction columns WERE injected, the engine evaluated the full market against a panel where 5535/5537 symbols have NULL auction columns (null comparisons恒假) and the 2 covered symbols (000001.SZ/000002.SZ) did not pass strategy thresholds on the run day. The machinery already produces honest ≤2-symbol hits with a sparse lake (proven by `test_backfill_auction_sparse_lake_honest_rows`, which crafts ratio=50 to force a hit). Phase 34's real branch therefore needs NO new injection path: it reuses `attach_auction_columns_range` (partition-existence gate, probe-free — same as the 29 validation service) and reports coverage honestly (496 real rows / 5537×248 expected).

- **BACKTEST_MAX_SERVER_DAYS=186**: resolution = **(c) keep the cap on the legacy vectorbt endpoints; do not route the research backtest through `_guard_server_backtest_range` (D-06 precedent)**. The cap is a memory guard for the vectorbt OOM profile (1.8GB server), it is **off by default** (`config.py:103`), and when enabled it **rejects with 400** (`backtest.py:61-62`), never truncates. The auction backtest uses the screener-machinery vectorized single-panel scan (measured 1.6s/day, 33-01-SUMMARY:24), which has none of the vectorbt OOM profile; the validation service already scans the full 248-day panel without the guard (D-06 locked in 29-02/29-03).
- **BT-07 delta vs Phase 29 report**: the validation report is a computed-on-demand read-only projection with per-date + forward stats but **persists nothing**. BT-07 adds a **write side**: `run_full_backtest` service → `backtest_results` lake (origin/params/per-date hit rows + forward outcomes) + deterministic run_id idempotency, plus a read-only query endpoint (BT-09) and AST guard.
- **BT-08**: with 248 auction partitions ∩ 248 enriched dates, `build_report` flips `data_gate:"available"` automatically (`auction_validation.py:184-191`); real-branch strategies report real rows (2-symbol coverage). The report's coverage block is **date-level only** — BT-08 adds **symbol-level coverage** fields (honest: `auction_symbol_count=2`, `enriched_symbol_count≈5293`, `symbol_coverage_ratio≈0.04%`).
- **BT-10**: `minute_confirm` stays `"not_applied"` everywhere (`_minute_loader` unwired, `main.py:561-565`; `kline_minute` 0 partitions); `auction_intraday_confirm` is 恒 0 via `engine.py:376-390` required-short-circuit. Annotate in manifest/output.

---

## 1. Data reality (verified 2026-08-06, read-only lake inspection)

| Lake | Partitions | Notes (observed) |
|---|---|---|
| `data/kline_auction` | **248** (2025-07-29..2026-08-05) | 496 rows, 2 symbols `000001.SZ`/`000002.SZ`, cols `[symbol, datetime, auction_volume, auction_amount, auction_virtual_price]`; datetime all 09:25:00; no `auction_unmatched_*` col (upstream lacks it — honest absence) |
| `data/kline_daily` | 248 | — |
| `data/kline_daily_enriched` | 248 | 15 storage cols `[symbol,date,open,high,low,close,volume,amount,raw_close,raw_high,raw_low,turnover_rate,consecutive_limit_ups,consecutive_limit_downs,quote_ts]` (repo comments say "14 列" — count is 15, stale comment); total ≈ **1.33M rows** (~5293-5537 symbols/day) |
| `data/screener_results` | 8 | 2026-07-27..08-05, `origin=backfill` (33-01 sandbox subset) |
| `data/backtest_results` | **0** | dir pre-created by `DataStore` (repository.py:68); empty |
| `data/kline_minute` | **0** | BT-10 limitation |
| `data/ext_history` | **0** | concept as_of falls back `current_snapshot` (28-01: three-state machine, ext_history absent → current_snapshot) |

Probe status: `available` (source xyz) — verified live twice in 33-01 (33-01-SUMMARY:24-25, 17:40:49Z re-verify). Each `resolve_auction_probe()` call = 1 live HTTP (8s timeout, xyz_provider.py:62-64) — **never use the live probe as a history-date gate**.

---

## 2. Seam map (file:line)

### 2.1 Engine execution seam
- `backend/app/strategy/engine.py:295` `StrategyEngine.run(strategy_id, as_of, pool, params, overrides, precomputed, precomputed_history)` — data load branch: `filter_history_fn` (:301-314) → `precomputed` (:315-316) → `_loader(as_of)` (:317-320).
- `engine.py:345-348` — **`requires_auction_data` short-circuit**: `if s.meta.get("requires_auction_data") and "auction_volume" not in df.columns: return StrategyResult(...)` (empty). **Fires only when the column is absent from the panel** — not on low coverage.
- `engine.py:376-390` — **minute_confirm seam**: `if s.minute_confirm_fn is not None and s.evaluation_time is not None and not df.is_empty()` → `_minute_loader is None or not candidates` → `minute_confirm_required` → empty StrategyResult (:380-381). `_minute_loader` constructor param `engine.py:151-163`; **main.py:561-565 constructs StrategyEngine without it** → `None`.
- `engine.py:227-231` — param normalization; META-default params = `{p["id"]: p["default"] for p in meta.get("params", [])}` (deterministic, mirrors validation service).
- 9 auction-family strategies (verified meta scan): `auction_fast_grab`, `auction_allround`, `t1_flash` = `requires_auction_data=True`; `auction_intraday_confirm` = True **+ `minute_confirm_required=True`**; `auction_alpha` = False (column-existence branch); `golden_230`, `auction_bullish`, `auction_preopen_quant`, `auction_early_star` = no auction meta (EOD/derived). Thresholds e.g. `auction_allround.py:13-18,35-46` (min_open_gap 2.0%, min_auction_vol_ratio 1.2, min_auction_amount 1e6; `pl.lit(False)` guard at :37-38 when columns absent).

### 2.2 Panel loading seams
- `backend/app/backtest/engine.py:202-276` `_load_panel_inner` — cache-first `repo.get_enriched_range(start, end, symbols, columns)` (:209-217), fallback `scan_enriched_parquet` glob + `compute_all` (:223-276). **kline_daily_enriched only — auction columns never present** (v2.2 reason BT-07 was deferred).
- `backend/app/tickflow/repository.py:966-998` `get_enriched_range` — returns the **full computed in-memory history cache** (`_enriched_history_cache`, built by `_refresh_enriched` :461-556 with all indicator columns) when the cache covers `[start,end]`, else `None`. Cache covers all 248 days at boot (33-01 relied on this; ~1.33M rows in memory already).
- `backend/app/services/screener.py:245-297` `_load_enriched_for_date` — 3 paths, **all end in `self._attach_auction(df, target_date)`** (:261/:276/:297).
- `screener.py:299-314` `_attach_auction` → `attach_auction_columns` (single-day, **probe×partition double gate**) — this is the read path used by live screener / pool backfill.
- `backend/app/services/auction_columns.py:93-152` `attach_auction_columns` — gate 1 probe `resolve_auction_probe().status != available` → columns absent (:96-99); gate 2 partition exists+non-empty (:101-112); per-symbol left-join null (:146-147); fan-out unique (:143-145).
- `auction_columns.py:160-278` **`attach_auction_columns_range(df, start, end, repo) -> (df, enabled_dates)`** — the Phase 34 injection primitive: **partition-existence gate only, probe NOT consulted** (D-03/REV-01, :170-176); date taken from dirname, unreadable/empty/bad-dir skipped fail-closed; per-partition symbol-dedupe keep="last" (09:25 final match); schema-drift tolerant concat; PIT-safe vectorized `auction_volume_ratio` (shift(1) + rolling_mean(5) per symbol, no same-day EOD lookahead, :262-272); warmup rows cropped after inject (:274-276).

### 2.3 Screener batch seam (runtime reference)
- `screener.py:722-812` `run_all_with_hits(as_of, strategy_ids, engine)` — single-day batch: precomputed panel once (:745), PRESET + engine strategies (:753-761), per-sid try/except continue (:777-787), `engine.run(sid, as_of, precomputed=...)` for non-PRESET (:783-791). **Measured 1.6s/day** for 27 strategies over full market (33-01-SUMMARY:24: 13s / 8 days). Pool backfill loops this per day (`pool_backfill.py:30-70`).

### 2.4 Validation report seam (BT-08 base)
- `backend/app/services/auction_validation.py:130-220` `build_report` — window parse+clamp with requested/effective echo (:151-168), warmup load (:170-174), `attach_auction_columns_range` injection (:178), `auction_enabled_dates = enabled ∩ enriched` (:180-183), **data_gate flips "available" automatically at :184-191 when enabled dates exist**.
- `auction_validation.py:210-218` coverage block — **date-level only** (`auction_enabled_dates/count`, `enriched_dates/count`, `coverage_ratio`); **no symbol coverage** → BT-08 gap.
- `auction_validation.py:290-366` `_evaluate_strategy` — branch mutual exclusion (4 real 恒 real with empty enabled → n_dates==0, never derived-downgrade; alpha real|derived; 4 eod), `minute_confirm: "not_applied"` (:349), per-strategy `{branch, n_dates, n_hits, coverage, n_missing_outcomes, forward_stats, per_date}`.
- `auction_validation.py:381-438` `_forward_stats` — BT-04 locked: global-calendar next-date (calendar join, :396-405), 3 formulas (:419-435), `n_missing_outcomes` counted never filled, per-metric independent n.
- Endpoint: `backend/app/api/research_auction.py` — GET-only `/api/research/auction/validation`, `_bad_request` from research.py:86-87, AST guard `tests/test_auction_validation.py` (BT-06, 6 items, mirrors test_pool_hub.py:857-963).

### 2.5 Write-seam precedents (BT-09)
- `auction_sync.py:45-55` `_atomic_write_parquet` — `.tmp` + same-dir rename (atomic).
- `auction_sync.py:57-130` `write_auction_partitions` — window predicate, col crop, per-date merge-upsert `unique(["symbol","datetime"], keep="last")` idempotent, `.tmp` atomic.
- `pool_snapshot.py:59-109` `persist_point_snapshot` — provenance `origin ∈ {eod, backfill, manual}` (:84-88), payload `{as_of, computed_at, strategy_version, snapshot_type, schema_version, snapshot_origin, results}` (:91-101), temp + `os.replace` (:103-106).
- `services/backtest.py:358-371` `BacktestService._persist` — **existing `backtest_results/run_id={run_id}.parquet` flat hive layout precedent** (vectorbt path; `run_id/stats_json/n_trades` — too thin for BT-09, but confirms run_id= partition convention).
- `concept_history.py` (28-01) — `ext_history/{kind}/date={as_of}/` + manifest, strict `_DATE_RE`, E2 root-isolation guard ("writes only ext_history").

---

## 3. Q1 — BACKTEST_MAX_SERVER_DAYS=186 resolution

**Where defined/enforced:**
- `backend/app/api/backtest.py:29` `BACKTEST_MAX_SERVER_DAYS = 186`; `:57-62` `_guard_server_backtest_range` — **`if not settings.backtest_range_guard: return`** then `days > 186 → HTTPException 400` with "服务器内存约 1.8GB…6 个月" message (:31-33).
- Enforced (sync paths, raise 400): strategy backtest `:159`, factor backtest `:227`; factor evaluation in `research.py:114/:122` (imports the same guard).
- Enforced (job paths, **SSE error event, not HTTP**): `:484-489` + `:517-519` (strategy job), `:741-743` + `:768` (factor job) — `guard_violated` → `event: error` with the guard message. **Rejection, never truncation.**
- Default: `config.py:103` `backtest_range_guard: bool = False` — **guard is OFF in the current sandbox; a 248-day request passes today.**

**What happens at 248:** if `backtest_range_guard=True`, any sync call with `days > 186` → **HTTP 400** (or SSE error for jobs); `_resolve_start` with explicit-null start yields `date(1900,1,1)` (`:151-157`) which the guard catches. No silent truncation exists.

**Recommendation: (c) keep the cap for the legacy vectorbt endpoints; route the research backtest around it (D-06 precedent), with (b) chunking as documented fallback if a future server endpoint insists on wrapping it.**
- The cap protects the vectorbt engine's OOM profile on a 1.8GB server (message text says so). The auction backtest reuses the screener-machinery **single-panel vectorized scan** (validation service shape) — measured 1.6s/day full-market (33-01), and `auction_validation.build_report` already scans the 248-day panel with the guard **explicitly excluded** (D-06, `auction_validation.py:139-140` docstring + 29-02-PLAN must-have: "绝不套用 BACKTEST_MAX_SERVER_DAYS").
- Chunked 2×124 as an alternative is strictly worse: adds run-merge complexity, split-window forward-outcome boundary issues (outcome of day 124 needs day 125), no memory benefit for a panel already held in the enriched cache.
- (a) raise the cap — rejected: changes a memory guard's contract based on a different engine's profile; the guard stays meaningful for vectorbt.
- **Implementation note for 34-02:** extend the D-06 decision to the new backtest service + endpoint docstrings ("本回测区间不受回测 186 天 guard 限制 — 单面板向量化扫描, 覆盖由 enriched 缓存边界决定"), mirroring `auction_validation.py:139-140`; do not import `_guard_server_backtest_range`.

---

## 4. Q2 — Backtest seam today & what BT-07 adds

**What exists today:**
- `run_all_with_hits` produces per-day hit lists with forward outcomes **only inside the validation report** (`auction_validation.build_report`), which is **computed on demand, read-only, persisted nowhere** (POOL-03 zero-write). The pool backfill (`run_pool_backfill`) persists **snapshot results** (hit rows, no forward outcomes) to `screener_results` — that's a different artifact (pool rendering), not a backtest.
- `BacktestService` (`services/backtest.py`) is the vectorbt engine for parameter/entry-exit backtests — different machinery, different guard, no auction columns.

**BT-07 delta:** a persisted **full backtest run**: 9 strategies × aligned dates (auction partitions ∩ enriched) → per-(strategy, date, symbol) hit rows + BT-04 forward outcomes → `backtest_results` lake with provenance → queryable read-only.

**`run_full_backtest` design (recommended):**
1. **Reuse the validation service machinery, not `run_all_with_hits` per day.** Load ONE panel via `repo.get_enriched_range(warmup_start, end, symbols)` (full computed cache, 1.33M rows for 248 days), inject via `attach_auction_columns_range` (probe-free history gate), then per-strategy vectorized mask (`_build_candidate_mask` mirror) over the aligned sub-panel — exactly `build_report`'s shape, extended to emit hit rows. This is faster and memory-bound (one panel) vs 248× `run_all_with_hits` (measured 1.6s/day → ~6.6 min full run; the vectorized path is seconds-to-a-minute for masks).
2. **Signature:** `run_full_backtest(repo, engine, *, start=None, end=None, strategy_ids=None, symbols=None, on_progress=None, job_id=None) -> dict` (job shape mirrors `pool_backfill.py:30-70`: cooperative cancel on `job_id` failed, progress emit, honest terminal dict).
3. **Branch semantics:** mirror `_evaluate_strategy` exactly (4 real 恒 real on enabled sub-panel; alpha real|derived by enabled non-empty; 4 eod on full window; META-default params). Reuse or import `auction_validation._build_candidate_mask` semantics — do NOT import the execution family.
4. **Forward outcomes:** reuse the `_forward_stats` calendar-join (global next-date, 3 formulas, `n_missing_outcomes`, no zero-fill) — either extract a shared helper or mirror it; prefer extracting a small pure helper into the new service module (no behavior change) so write-side and report-side stay in lockstep. Note: 29-02 docstring discipline (no guard-forbidden literals) applies to any new service file touched by the 34-03 AST guard.
5. **Runtime estimate:** panel load ~1-2s (cache) + 9 masks over 1.33M rows (vectorized, <10s) + forward join + write. Full-market **~1-3 min total** vs 33's 6-7 min for 248× run_all. With `symbols=["000001.SZ","000002.SZ"]` (the honest sparse-lake full backtest): microseconds-fast — panel filter to 496 rows.
6. **Trigger surface:** CLI script (`backend/scripts/run_research_backtest.py`, mirror `probe_concept_drift.py` shape) **or** a POST job endpoint on a NON-research router (e.g. `/api/pipeline/research-backtest`, mirror `/api/pipeline/backfill` job plumbing: single-flight + job_store + cancel). Do NOT put the write trigger on the `/api/research` read-only router (would break the GET-only guard shape). **Open question O1** (see §11).

---

## 5. Q3 — Sparse-lake honesty & the 33-run-0-rows root cause (CRITICAL)

**Question:** with a 2-symbol lake and probe `available`, why did allround/fast_grab/t1_flash/intraday_confirm/alpha show 0 rows on the 33 backfill days? Was it the probe gate, or a coverage short-circuit?

**Answer: neither. The machinery worked exactly as designed; 0 rows is the honest sparse-lake filter result.**

Evidence chain:
1. **Probe was `available`** — 33-01-SUMMARY:24-25: verdict recorded during the run (source xyz) and independently re-verified `resolve_auction_probe()` at 17:40:49Z; snapshot rows for `auction_bullish` carry `auction_amount/auction_volume/auction_volume_ratio` columns → **columns were injected into the panel** (a column-absent run cannot produce those).
2. **The engine short-circuit did NOT fire** — `engine.py:345-348` requires `"auction_volume" not in df.columns`; the column WAS present. 33-01-SUMMARY §1.6 confirms `auction_alpha` ran the **真列分支 (real branch)** ("真列分支 (ratio 阈值未过)") — a real-branch evaluation is only possible with injected columns.
3. **The filter evaluated honestly over a 2-symbol-covered panel** — `attach_auction_columns` left-joins (`auction_columns.py:146-147`): 5535 symbols get NULL auction cols → null comparisons恒假 → excluded; `000001.SZ`/`000002.SZ` failed the day's thresholds: `auction_allround` needs `open_gap≥2.0% AND auction_volume_ratio≥1.2 AND auction_amount≥1e6` (`auction_allround.py:13-18,39-46`); `auction_alpha` real branch needs `vol_ratio≥1.0, real_gap≥1.5%, amount≥1e6`. Result: 0 hits — exactly the 33-RESEARCH §2.3 bimodal-table expectation ("最多命中 2 个标的 (大概率 0, 取决于样本码是否过阈值)").
4. **`auction_intraday_confirm` = 0 for a different, lake-independent reason**: `minute_confirm_required=True` + `_minute_loader` unwired (`main.py:561-565`) → `engine.py:376-390` required-short-circuit → empty pool (恒 0 regardless of lake).
5. **The machinery CAN produce hits with a sparse lake** — `test_backfill_auction_sparse_lake_honest_rows` (33-01) crafts `000001.SZ ratio=50` → hit row; fail_closed state → total==0 (short-circuit, the honest other mode).

**Design consequence for Phase 34:**
- The backtest service must use **`attach_auction_columns_range` (partition-existence gate only), never the live probe**, for history dates — exactly as `auction_validation.build_report` does (D-03). This makes the real branch deterministic, network-independent, and reproducible across the 248-day window (no 8s-timeout risk, no 33-min worst-case probe tax).
- **Honest reporting required (BT-07 "honest coverage"):**
  - `coverage.symbols` block: `auction_symbol_count` (distinct symbols with auction rows in window = **2** today), `enriched_symbol_count` (=5293-5537/day), `symbol_coverage_ratio` (≈0.04%), plus `auction_rows_expected = enriched_symbol_count × n_dates` vs `auction_rows_present` (496) — a rows-level coverage for the lake itself.
  - Per-strategy: `n_symbols_covered` (distinct symbols with non-null auction cols in eval panel) and `n_symbols_hit` alongside existing date-level coverage.
  - **Deploy note**: full-universe auction backfill (operator run, ~5500 symbols × 1.6s/req ≈ 2.5-3.5h; 32-02/33 docs "3-5.5h" estimate incl. pacing/retries) unlocks the full real branch; until then, real-branch backtests are **valid but tiny-universe** (2 symbols), and the report/backtest output must say so (never derive-downgrade, never claim full-market coverage).

---

## 6. Q4 — backtest_results schema + write/query seams

**Partition layout:** `backtest_results/run_id={id}/part.parquet` (rows) + `backtest_results/run_id={id}/manifest.json` (provenance) — mirrors the existing `BacktestService._persist` run_id= convention (`services/backtest.py:359-369`) and the pool snapshot's payload-provenance convention (`pool_snapshot.py:91-101`). Per-run directory keeps a run self-contained (atomic replace of a whole run), avoids cross-run merge-upsert complexity; date-level querying is done with parquet predicate pushdown on the `date` column, not by partition dirs.

**Deterministic run_id for idempotency:** `run_id = sha1(strategy_ids|start|end|params_snapshot|strategy_version)[:12]` — re-running the same config is a no-op overwrite (atomic), mirroring pool backfill's partition-diff idempotency. Distinct runs get distinct ids; no job_store required unless we want job progress (see O1).

**Row schema (long format, one row per hit; BT-09 "per-date rows" = hits + forward outcomes, per-date counts derivable):**

| col | type | notes |
|---|---|---|
| `run_id` | str | deterministic id |
| `strategy` | str | strategy id |
| `branch` | str | `real|derived|eod` (BT-05 mutual exclusion, persisted per row) |
| `as_of` | date | signal date T |
| `symbol` | str | |
| `entry_open` | f64 | open_T (BT-04 T-open entry) |
| `open_t1` / `close_t1` | f64 | open/close_{T+1} (null when outcome missing) |
| `next_day_open_ret` / `next_day_close_ret` / `open_gap_outcome` | f64 | BT-04 formulas; null per-metric when invalid/missing (never 0-filled) |
| `outcome_missing` | bool | result date absent (halted/delisted) → counted in n_missing_outcomes |
| `params_json` | str | META-default param snapshot (deterministic) |
| `strategy_version` | str | strategy fingerprint at run time (mirror pool_snapshot) |
| `origin` | str | `"research"` (fixed; keeps the {eod,backfill,manual} pool vocabulary distinct) |
| `minute_confirm` | str | `"not_applied"` (BT-10 annotation, per row) |
| `created_at` | str | UTC ISO |

**manifest.json:** `{run_id, origin, strategy_version, created_at, window:{start,end}, strategies:[...], params:{sid:params}, coverage:{dates & symbols blocks (§5)}, per_date:[{date, n_screened, n_hits}], minute_note}` — per_date summary mirrors `_build_per_date` output.

**Write seam:** reuse `_atomic_write_parquet` pattern (`.tmp` + same-dir rename; auction_sync.py:45-55). Manifest written after rows, same atomic pattern. **AST guard for the write module:** root-isolation guard "writes only `backtest_results`" (mirror concept_history's "writes only ext_history" E2 test, 28-01) + never touches `strategy_cache`/`screener_results` + no execution-family imports (mirror test_auction_validation.py forbidden-token sets).

**Read-only query surface (BT-09):**
- `GET /api/research/backtest` — list runs (scan `run_id=*` dirs, read manifests): `{runs:[{run_id, created_at, origin, strategy_version, window, n_strategies, n_hits, coverage}], count}`; filters `?strategy=&branch=&as_of=&symbols=` filter the list by manifest/parquet scan.
- `GET /api/research/backtest/{run_id}` — run detail: manifest + row stats + optional `?strategy=&branch=&as_of=&symbol=` predicate pushdown on the run parquet (polars `scan_parquet` filters), returns per-date/per-strategy summary + sampled rows.
- **Guard (34-03):** new `api/research_backtest.py` module — GET-only, zero-write, no execution imports, import whitelist (mirror test_auction_validation.py 6-item guard; E3: no strategy_cache/screener_results literals or writes). Never exposes a POST trigger (see O1).

---

## 7. Q5 — Validation activation (BT-08) + coverage fields

- **Activation is automatic.** With 248 auction partitions and 248 enriched dates, `build_report` computes `enabled_dates` via `attach_auction_columns_range` (all 248 pass the partition-existence gate), `auction_enabled_dates = enabled ∩ enriched = 248` → `data_gate="available"`, `empty_reason=None` (`auction_validation.py:184-191`). No code change needed to flip.
- Real-branch rows become **real but 2-symbol**: 4 real strategies evaluate on the enabled sub-panel with real auction cols for 000001.SZ/000002.SZ; hits only where thresholds pass (likely 0 on most days — same honest outcome as §5, now with `n_dates=248`). `auction_alpha` flips to `branch="real"` (enabled non-empty). **No derived-downgrade** (D-02 locked).
- **Missing today — symbol coverage** (BT-08 "honest coverage"): the coverage block (`auction_validation.py:210-218`) is date-level only. **34-02 adds:**
  - `coverage.symbols`: `{auction_symbol_count, enriched_symbol_count, symbol_coverage_ratio, auction_rows_present, auction_rows_expected}` — computed by scanning `kline_auction` window partitions (symbol count + row count) and `verification_panel["symbol"].n_unique()`.
  - per-strategy `n_symbols_covered` / `n_symbols_hit` in `_evaluate_strategy` output.
  - Empty-state shape extended consistently (`_empty_report` coverage block gains the same keys with 0/null values).
- **Also verify n_dates/n_symbols reporting** (29-03 endpoint tests `test_endpoint_available_gate_with_partitions` already assert the flip — extend with the 248-real partition fixture asserting `data_gate:"available"` + real rows for the 2 symbols).

---

## 8. Q6 — BT-10 minute limitation

- `kline_minute` = 0 partitions (verified); historical minute 248-day backfill is **CLOSED** (xyz 1m ≈ 21 trading days, ifzq/sina trailing windows, TickFlow minute gated at pro+ — AUCTION-BACKFILL.md Q3).
- `_minute_loader` unwired at engine construction (`main.py:561-565`) → `auction_intraday_confirm` (minute_confirm_required=True) is **恒 empty** via `engine.py:376-390`.
- **Annotation plan:** validation report already emits `minute_confirm:"not_applied"` per strategy (`auction_validation.py:349`); backtest_results manifest adds a `minute_note` field: "kline_minute 历史 CLOSED — confirmation dimensions honestly limited; auction_intraday_confirm empty by design (BT-10)"; per-row `minute_confirm:"not_applied"`. No code behavior change; a docs/features.md note in 34-03.

---

## 9. Plan split (3 plans)

- **34-01 — backtest service + schema + write seam (BT-07 core, BT-09 write side):**
  - New `backend/app/services/research_backtest.py`: `run_full_backtest(repo, engine, *, start, end, strategy_ids, symbols, on_progress, job_id)` — panel load (get_enriched_range) → `attach_auction_columns_range` → per-strategy branch + vectorized mask + forward outcomes (extracted/mirrored from auction_validation) → hit rows + manifest → `backtest_results/run_id=...` atomic write. Coverage (date+symbol blocks, §5/§7) computed here.
  - `backend/scripts/run_research_backtest.py` CLI (or job plumbing per O1).
  - Unit tests (hermetic, conventions from `tests/test_auction_validation_report.py`: `repo_env` fixture :38-52, `_write_auction_partition` :54-57, `_seed_enriched_cache` :103, `_make_engine` :87-101): sparse-lake run (2-symbol real rows, coverage ratios, honest per_date), idempotent re-run (deterministic run_id), atomic no-.tmp residue, branch mutual exclusion, BT-04 forward outcomes vs hand-computed, minute_confirm annotation.
- **34-02 — validation activation + coverage fields + 186-day resolution (BT-08, Q1/Q5):**
  - Extend `auction_validation.py` coverage block (symbols + rows-level) + `_evaluate_strategy` `n_symbols_covered/n_symbols_hit`; extend empty-state shapes; docstrings for the 186-day non-application (D-06 already present — verify + extend to the new backtest service docs).
  - Tests: 248-partition fixture → `data_gate:"available"` + real rows 2-symbol; symbol coverage assertions; real-branch honesty (n_dates=248, tiny universe noted, no derived-downgrade).
- **34-03 — query endpoint + guard + docs + cross-check (BT-09 read side, BT-10, verification):**
  - New `backend/app/api/research_backtest.py` GET-only endpoints (list + detail + filters) + main.py registration; AST guard file (mirror test_auction_validation.py 6-item + write-root isolation for the service module); docs/features.md 竞价回测 section (endpoint, honest coverage, 186-day note, BT-10 limitation).
  - **Cross-check (like 33-01's real sandbox run):** run `run_full_backtest` on the real 248-day lake for the 2-symbol real branch + derived/eod branches; sample forward outcomes vs `kline_daily` (open_{T+1}/close_{T+1} spot-check, e.g. 3 dates × 2 symbols, hand-verified like AUCTION-BACKFILL.md §4 cross-checks); record runtime + coverage in SUMMARY.

---

## 10. Test plan (names + conventions)

No `test_auction_backtest*` file exists today — new file `backend/tests/test_research_backtest.py` following `tests/test_auction_validation_report.py` conventions (hermetic tmp data_dir + real builtin-dir StrategyEngine + manual partition writes; no network — inject probe or use range gate which never probes). Proposed cases:

1. `test_full_backtest_sparse_lake_honest_rows` — 5-symbol enriched × 2-day + 2-symbol auction partitions → real-branch hits ⊆ {2 symbols}, coverage.symbols {auction_symbol_count=2, enriched_symbol_count=5, ratio=0.4}, derived/eod full-window stats.
2. `test_full_backtest_forward_outcomes_bt04_formulas` — hand-computed 3 formulas + n_missing_outcomes (halted symbol) — reuse the 29-02 fixture shape.
3. `test_full_backtest_branch_mutual_exclusion` — one branch per strategy per row set.
4. `test_full_backtest_deterministic_run_id_idempotent` — same config twice → same run_id, atomic overwrite, no .tmp residue.
5. `test_full_backtest_write_root_isolation` — service writes only `backtest_results/`; `strategy_cache`/`screener_results` untouched (byte-identical), mirror `test_pool_backfill_never_creates_premarket_root` shape.
6. `test_backtest_query_list_and_detail` (34-03) — GET /api/research/backtest lists runs with manifest fields; detail filters rows by strategy/branch/as_of.
7. AST guard file `tests/test_research_backtest_guard.py` (or extend `test_auction_validation.py`): 6-item guard for `api/research_backtest.py` (GET-only, no write tokens, no execution imports, import whitelist, no strategy_cache/screener_results literals) + E2 root-isolation guard for `services/research_backtest.py` ("writes only backtest_results").
8. `test_validation_available_248_partitions_real_rows` (34-02) — 248-partition fixture → data_gate available + symbol coverage fields.

Guard regression sets: `test_auction_validation.py` (6), `test_auction_validation_report.py` (16), `test_attach_auction_columns_range.py` (14), `test_pool_hub.py` (35, E1-E6), `test_auction_backfill*.py`, `test_auction_sync.py`, `test_pool_backfill.py` — all currently green; zero new deps.

---

## 11. Risks

| Risk | Sev | Mitigation |
|---|---|---|
| **Memory (248-day panel)**: 1.33M rows × ~30 cols in one polars frame + forward join | low | Same footprint the enriched cache already holds at boot (33-01 relied on it); validation service already scans it (D-06). Peak maybe 300-500MB — fits 1.8GB server; symbols filter is the escape hatch. |
| **Runtime**: 9 strategies × 248 days × 5537 symbols | low | Measured 1.6s/day for the per-day machinery (33-01) → ~6-7 min upper bound; vectorized single-panel path is faster (~1-3 min est.). Job-style progress + cooperative cancel (pool_backfill shape) bounds operator cost. |
| **186-day cap collision**: a reviewer wraps the new endpoint in `_guard_server_backtest_range` | low | D-06 precedent documented in 34-02 docstrings + docs; guard stays on legacy vectorbt endpoints only (Q1). |
| **Sparse-lake real branch misread as broken** (0 hits on most days) | medium | Honest coverage fields (§5/§7) + real-branch sample cross-check (34-03) + docs note "full-universe auction backfill (3-5.5h operator run) unlocks full real branch". Never derived-downgrade. |
| **Write-volume surprise** (derived/eod branches can hit ~50/day/strategy): 248 × 50 × 3 ≈ 37k rows + real-branch sparse | low | Long-format hits-only persistence; per-date summary in manifest; parquet predicate queries. Bound with `limit` passthrough? No — keep full hits (backtest semantics), volume is small. |
| **Forward-outcome boundary** at window end (last day has no T+1) | low | BT-04 already handles: outcome missing → counted, never filled (validation service precedent). |
| **Probe network tax** if anyone reintroduces the live probe into the backtest path | low | Range gate is probe-free (D-03); guard/docstring discipline; tests never call network. |

---

## 12. Confidence

- **HIGH**: seam map (all file:line verified against live code), 33-run root cause (33-01-SUMMARY evidence chain + engine/columns code read + test proof), lake facts (direct partition inspection), 186-cap behavior (guard code read, default-off verified), validation activation logic (build_report gate read).
- **MEDIUM**: runtime estimate for the vectorized write-side path (derived from the measured 1.6s/day, not measured for the new path — 34-03 cross-check will measure), write-volume/schema choices (design judgment; row counts bounded).

---

## 13. Open questions (3)

1. **O1 — Trigger surface for `run_full_backtest`**: operator CLI script (`backend/scripts/run_research_backtest.py`, zero API surface, mirrors probe scripts) vs POST job endpoint on a non-research router (`/api/pipeline/research-backtest` with job_store + single-flight, mirrors `/api/pipeline/backfill`). CLI is simpler and keeps the research router GET-only; POST gives progress/cancel. Recommend CLI + optional job wrapper later — needs planner confirmation.
2. **O2 — Strategy params source**: META defaults (deterministic, mirrors 29, no coupling) vs user overrides from the single-as_of runtime cache (prohibited by E3-style guard if read). Recommend META defaults only; `strategy_version` fingerprint records when strategy defs changed. Confirm.
3. **O3 — Concept PIT as_of dimension (BT-07 mentions "concept PIT as_of")**: the enriched+auction panel has no concept columns (concept attribution is a pool_hub projection; ext_history absent → honest `current_snapshot` fallback). Option (a) join current-snapshot concepts per date as a row dimension (adds a join + a fallback-labeled column), option (b) leave concepts out of backtest_results v1 (mirrors the validation report, documented). Recommend (b) with the honest note — concept attribution belongs to pool rendering, not signal backtests; confirm.

---

## 14. Evidence index (core file:line)

- `api/backtest.py:29` (186), `:57-62` (guard, off by default), `:159/:227` (sync enforce 400), `:484-489/:517-519/:741-743/:768` (job SSE error); `config.py:103` (default False); `research.py:114/:122` (factor-eval reuse)
- `strategy/engine.py:295` (run), `:345-348` (auction short-circuit — column-absent only), `:376-390` (minute confirm), `:151-163` (minute_loader param), `:227-231` (params); `main.py:561-565` (no minute_loader)
- `backtest/engine.py:202-276` (`_load_panel_inner`, enriched-only); `tickflow/repository.py:966-998` (get_enriched_range full-computed cache), `:461-556` (_refresh_enriched)
- `screener.py:245-297` (3 paths → `_attach_auction`), `:299-314` (single-day double gate), `:722-812` (run_all_with_hits); `pool_backfill.py:30-70` (job template)
- `auction_columns.py:93-152` (single-day probe×partition), `:160-278` (range — partition-existence gate, PIT ratio, warmup)
- `auction_validation.py:130-220` (build_report; gate flip :184-191; coverage date-only :210-218), `:290-366` (branch/minutes :349), `:381-438` (BT-04 forward)
- `auction_sync.py:45-55` (atomic write), `:57-130` (merge-upsert seam); `pool_snapshot.py:59-109` (provenance); `services/backtest.py:358-371` (run_id= precedent)
- 33-01-SUMMARY:24 (1.6s/day), :25 (probe available), §1.6 (0/50/50/43 rows, alpha real branch, thresholds not met); 33-RESEARCH §2.3 bimodal; 32-02-SUMMARY:45-48 (496 rows/248 days/2 symbols, origin=backfill)
- `auction_allround.py:13-18,35-46` (thresholds, lit(False) guard); `auction_alpha.py` params (real-branch thresholds)
- Tests: `tests/test_auction_validation_report.py:38-107` (conventions), `tests/test_auction_validation.py` (guard), `tests/test_pool_backfill.py::test_backfill_auction_sparse_lake_honest_rows` (sparse proof)
