---
phase: 34-auction-backtest
verified: 2026-08-06T19:10:00Z
status: passed
score: 4/4 BT requirements verified (BT-07..10)
behavior_unverified: 0
overrides_applied: 0
human_verification: 2 deploy-verified items (full-universe real-branch backtest after 3-5.5h auction backfill; live server query smoke on port 3019 optional) — sandbox cannot assert; labeled deploy-verified per standing policy
---

# Phase 34 Verification — 竞价回测解锁 (BT-07..10)

**Verifier:** VerifierP34 · **Date:** 2026-08-06 · **Scope:** `.planning/REQUIREMENTS.md` BT-07..10 (Phase 34)
**Method:** Goal-backward, behavior-level — 6-file pytest batch + code-level file:line evidence + real-lake spot-checks (row counts, branch exclusivity, idempotent re-run, forward-outcome recompute vs `kline_daily`) + guard-rail checks + SUMMARY cross-checks. Real-lake artifacts were directly re-inspected/recomputed by this verifier, not taken on faith from SUMMARY text.

## Verdict: **PASSED**

All 4 acceptance criteria verified against code + tests + real lake. 57 passed / 0 failures in the verification batch; 36 passed in POOL-03 `test_pool_hub.py` spot-check. No needs-fix items. Human items are deploy-verification only.

---

## 1. Test batch (executor duty 1)

```
cd backend && .venv/bin/python -m pytest tests/test_auction_backtest.py tests/test_auction_validation_report.py \
  tests/test_auction_validation.py tests/test_attach_auction_columns_range.py \
  tests/test_research_backtest_guard.py tests/test_research_backtest_api.py -x -q
→ 57 passed in 5.44s
```

Per-file collect (57 collected): backtest **6** · validation_report **20** · auction_validation **6** · attach_auction_columns_range **14** · research_backtest_guard **7** · research_backtest_api **4**. Sum matches the executor claims exactly (34-01 6 new + 36 regression; 34-02 20 report suite; 34-03 7 guard + 4 api).

## 1b. Behavioral summary (goal-backward, per BT)

- **BT-07 — full auction backtest unlocked.** An operator can now run the 9 auction/pre-market strategies over the 248-day real-column panel: `run_full_backtest` (single-panel vectorized) loads enriched history, clamps the window to the enriched cache boundary (never the 186-day backtest guard, D-06), injects auction columns via the partition-existence gate only (`attach_auction_columns_range`, zero live probe, zero network), evaluates each strategy with META-default params + `strategy_version` fingerprint, and writes deterministic, reusable results. Verified end-to-end on the real lake: Run A = 4 EOD strategies × 248 days × full market → 329,087 hit rows with `coverage.symbols` honestly reporting the 2-symbol auction universe (2/5537 ≈ 0.04%), never claiming full-market auction coverage.
- **BT-08 — validation report real branch activated.** `GET /api/research/auction/validation` now returns `data_gate:"available"` whenever backfilled `kline_auction` partitions intersect the enriched window (gate `auction_validation.py:196-201`, activation is purely behavioral — the gate itself was zero-line-changed). Real-column strategies report `branch:"real"` with real rows and are never derived-downgraded even on an empty lake (`n_dates==0` honest); `coverage.symbols` carries the 5-key symbol-level block and per-strategy `n_symbols_covered`/`n_symbols_hit` additive fields with all pre-existing date-level key assertions unbroken (20-test report suite green). Real lake: Run B = 4 real strategies × 248 days × 2 symbols → 12 hit rows, `auction_symbol_count==2`, ratio 100% within the small universe.
- **BT-09 — results persist to the `backtest_results` lake with a read-only query surface.** Write side: deterministic time-free `run_id` (sha1 over sorted strategies | window | sorted params | strategy_version | sorted symbols, `[:12]`) → atomic `part.parquet` + `manifest.json` (`.tmp`+rename, manifest written last), idempotent skip on identical fingerprint (`wrote=False, reused=True` — re-verified by this verifier's CLI re-run). Read side: `GET /api/research/backtest` lists runs (manifest-bearing dirs only; vectorbt flat files honestly skipped), `GET /{run_id}` returns manifest + predicate-pushdown row stats (strategy/branch/as_of/symbol via polars scan), bad run_id → 400, unknown → 404 `RESEARCH_BACKTEST`, empty lake → 200 `{runs:[],count:0}`, bad/missing parquet column → 400 not 500. Zero-execution AST guard (7 tests) locks GET-only, no execution-family imports, no write path on the API face, and E2 root isolation — all service write-target closures must contain `backtest_results` and never `strategy_cache`/`screener_results`/`kline_auction`/`kline_daily_enriched`.
- **BT-10 — minute-dependent confirmation honestly limited.** Every backtest row carries `minute_confirm:"not_applied"` (`auction_backtest.py:66`), every strategy stats block too (`auction_validation.py:434` for the report), and the manifest carries `minute_note` explaining `kline_minute` historical CLOSED + `auction_intraday_confirm` 恒空. Documented in `docs/features.md:82`. Verified in all 3 real manifests and both parquet lakes.

## 2. BT evidence table

| Req | Evidence (file:line) | Test(s) | Result |
|-----|----------------------|---------|--------|
| **BT-07** | `run_full_backtest` `auction_backtest.py:426` — ①enriched coverage (`_enriched_coverage` :87) ②window parse+clamp, requested/effective dual echo, D-06 no 186-day guard (:141 `_resolve_window`) ③warmup `max(start−14, cache_min)` panel load ④partition-existence gate **only** `attach_auction_columns_range(panel, eff_start, eff_end, repo)` :493 (def `auction_columns.py:174`; module imports no probe module — zero live probe, guard-locked) ⑤strategy enum = 9-family ∩ engine, unknown → `skipped_ids` (:222 `_resolve_strategy_ids`), params = META defaults (:307), `strategy_version = strategy_fingerprint(engine)` :511 ⑥per-strategy eval `_evaluate_strategy_rows` :284 — branch mutual exclusion BT-05 (`requires_auction_data`→`real` :309-311, `auction_alpha`→real\|derived :312-317, else→`eod` :319-321, empty lake → `n_dates==0` never derived-downgrade :323-335) + candidate mask (:338 `_build_candidate_mask` import, def `auction_validation.py:85`) + per_date + **BT-04 forward via unbound `AuctionValidationService._forward_stats(None, …)`** :338-340 (def `auction_validation.py:466`) + long-format row frame `_build_strategy_rows` :203 — three formulas `next_day_open_ret = next_open/open−1`, `next_day_close_ret = next_close/open−1`, `open_gap_outcome = next_open/close−1`, `open>0`/`close>0` denominators, `outcome_missing = next_open.is_null`, nulls never 0-filled/forward-filled (:235-259); outcome date = global trading-calendar next-date (`dates[1:]+[None]` join, never per-symbol shift :221-228); ⑦coverage dates+symbols dual block (`_coverage_symbols` :376); sparse-lake honesty — real branch panel ⊆ auction-enabled dates, `_n_symbols_covered` = auction_volume-non-null symbols (:190-198) | `test_auction_backtest.py` (6: sparse honesty / forward formulas / branch exclusion / idempotency / minute annotation / write-root isolation) + real-lake verification below (Run A/B, forward recompute) | **PASS** |
| **BT-08** | `data_gate` flips `"available"` on `auction_enabled_dates` non-empty (`auction_validation.py:196-201`; `empty`→`no_auction_partitions` / `no_dates_in_window`); `coverage.symbols` 5-key block `_coverage_symbols` :260 → `{auction_symbol_count, enriched_symbol_count, symbol_coverage_ratio, auction_rows_present, auction_rows_expected}`, wired :230, `_empty_report` same-shape 5 keys :327-333; per-strategy `n_symbols_covered`/`n_symbols_hit` :406-427 — real = `auction_volume` non-null symbol count (:420-424), derived/eod = eval universe (:426), hit = hits symbol n_unique (:427), empty panel → 0; real branch never derived-downgraded (:384-386, :398 empty → n_dates==0); `minute_confirm:"not_applied"` :434; report-side `_coverage_symbols` per-partition symbol dedup + fail-closed skip (mirror inject scan) | `test_auction_validation_report.py` (20, incl. 4 new: 248∩248 activation → `data_gate:"available"`, `coverage_ratio==1.0`, real-branch `n_dates==248` never derived, `coverage.symbols` sparse honesty 2/5/0.4/496/1240, per-strategy symbol coverage, minute-annotation regression) · `test_auction_backtest.py` manifest coverage/symbols 对账 | **PASS** |
| **BT-09** | Write: `_compute_run_id` `auction_backtest.py:614` — `sha1(sorted(strategy_ids)|start|end|json(params,sort_keys)|strategy_version|sorted(symbols))[:12]`, time-free, `on_progress`/`job_id` excluded; `_persist_run` :712 — mkdir under `backtest_results` (`_BACKTEST_ROOT` :70), `_atomic_write_parquet` tmp+replace (:626), `_atomic_write_json` tmp+os.replace (:634), manifest last; idempotent fingerprint skip → `(wrote=False, reused=True)` :728-737; `_build_manifest` :644 — 11 keys (run_id/origin/strategy_version/created_at/window/strategies/params/coverage/per_date/minute_note/fingerprint), `origin:"research"`. Read: `list_backtest_runs` `research_backtest.py:161` (`@router.get("/backtest")` :160) — manifest-bearing dirs only (vectorbt flat `run_id={id}.parquet` files excluded via `is_dir` :79 `_run_dirs`, honest skip), `?strategy=`/`?branch=` manifest filtering, created_at desc, empty lake → 200 `{runs:[],count:0}`; `get_backtest_run` :186 (`@router.get("/backtest/{run_id}")` :185) — `_RUN_ID_RE ^[0-9a-f]{12}$` :32 (bad → 400 :35-36), unknown → 404 `RESEARCH_BACKTEST` :39-40, predicate pushdown strategy/branch/as_of/symbol via `pl.scan_parquet` filter :101-155, missing column → 400 not 500, empty/bad parquet → 200 honest empty stats; registered `main.py:41` (import) + `:866` (`include_router`, `# BT-09 … POOL-03 零执行`) | `test_research_backtest_api.py` (4: list+detail+empty-lake, filters/predicate pushdown exact subsets, 404/400/422 semantics, vectorbt flat-file honest skip) · `test_research_backtest_guard.py` (7: modules exist / no execution imports / GET-only / no write path / **E2 root isolation** — write-target closure expansion must contain `backtest_results` and never strategy_cache\|screener_results\|kline_auction\|kline_daily_enriched / no strategy_cache reference / import whitelist) | **PASS** |
| **BT-10** (P2, honest-annotation) | `_MINUTE_CONFIRM = "not_applied"` `auction_backtest.py:66`; row column via `pl.lit(_MINUTE_CONFIRM)` in `_build_strategy_rows` (:279) + `_ROW_SCHEMA` :30; per-strategy stats `minute_confirm: _MINUTE_CONFIRM` :359; report-side `minute_confirm: "not_applied"` `auction_validation.py:434`; manifest `minute_note` = "kline_minute 历史 CLOSED — 确认维度诚实受限; auction_intraday_confirm 恒空 (BT-10)" (`_MINUTE_NOTE` :67 → `_build_manifest`) | `test_auction_backtest.py` minute-annotation case (all 9 strategies `not_applied`); `test_auction_validation_report.py` minute-annotation regression; real-lake manifests all carry `minute_note` (verified 3/3) · docs gate: `docs/features.md:82` BT-10 section (kline_minute CLOSED evidence) | **PASS** |

## 3. Real-run evidence `[OBSERVED — re-inspected by this verifier]` (executor duty 3)

Directly read from `data/backtest_results/` + `data/kline_auction/` + `data/kline_daily/` (read-only; `git status` confirms lake is untracked/gitignored):

| Run | run_id | rows (part.parquet) | per-strategy branch rows | manifest facts | vs SUMMARY |
|-----|--------|--------------------:|--------------------------|----------------|------------|
| A | `be4ce9bc038b` | **329,087** | golden_230 eod 81,254 · auction_bullish eod 32,686 · auction_preopen_quant eod 11,926 · auction_early_star eod 203,221 — **all 4 `branch="eod"`** | window 2025-07-29..2026-08-05 (248d) · origin research · `minute_confirm=['not_applied']` · coverage.symbols `{2, 5537, 0.000361, 496, 1373176}` · `strategy_version=7affa346e5e586c5` | ✅ rows 329,087; per-strategy hits exact; coverage 496/1,373,176 exact |
| B | `191642f83b2d` | **12** | auction_allround real 3 · auction_alpha real 6 · auction_fast_grab real 1 · t1_flash real 2 — **all 4 `branch="real"`** (no derived downgrade) | window 248d · coverage.symbols `{2, 2, 1.0, 496, 496}` | ✅ 12 rows; per-strategy hits exact; ratio 100% |
| smoke | `0f2b91e93975` | **0** (honest empty) | auction_bullish eod 0 | window 2026-07-30..2026-08-05 (5d) · rows_present 10/10 | ✅ 0 rows honest |

- **Branch exclusivity (BT-05)** — re-derived via `group_by(["strategy","branch"])` on both real lakes: Run A 4/4 `eod`, Run B 4/4 `real`. No mixed-branch run, no derived downgrade.
- **Idempotent re-run** — this verifier re-ran `python scripts/auction_backtest.py --strategies auction_bullish --range 5 --symbols 000001.SZ,000002.SZ` (2.8s wall incl. preload): **same run_id `0f2b91e93975`, `wrote: False  reused: True`, elapsed 0.0s**, manifest untouched (created_at unchanged at 18:36:14Z). Idempotency confirmed live, not just from SUMMARY.
- **Forward-outcome spot-check (BT-04 formulas vs raw `kline_daily`, read-only)** — 3 hit rows sampled from Run A `auction_bullish`, recomputed from `kline_daily/date=*` partitions using the global trading calendar (next date after T across the 248 partitions):

| as_of | symbol | open_T / close_T | T+1 | open_T1 / close_T1 | recomputed n_o / n_c / gap | stored | match |
|-------|--------|------------------|-----|--------------------|---------------------------|--------|-------|
| 2026-04-27 | 000001.SZ | 11.33 / 11.38 | 2026-04-28 | 11.36 / 11.46 | +0.002648 / +0.011474 / −0.001757 | 0.002648 / 0.011474 / −0.001757 | ✅ exact (9 dp) |
| 2026-01-28 | 000002.SZ | 4.88 / 4.86 | 2026-01-29 | 4.82 / 5.13 | −0.012295 / +0.051230 / −0.008230 | −0.012295 / 0.051230 / −0.008230 | ✅ exact (9 dp) |
| 2025-08-12 | 000006.SZ | 7.04 / 7.46 | 2025-08-13 | 7.50 / 7.43 | +0.065341 / +0.055398 / +0.005362 | 0.065341 / 0.055398 / 0.005362 | ✅ (stored 6 dp rounding) |

  First two rows are value-identical to the 34-03 SUMMARY forward-check table (independent recomputation confirms). All sampled rows `outcome_missing=False` with the outcome date present in the raw lake.
- **Lake shape** — `kline_auction` 248 partitions / 2 symbols / 496 rows (re-inspected 32-verifier fact, consistent); `kline_daily` 248 partitions (~5290 symbols/partition); all three `run_id=` dirs carry `manifest.json` + `part.parquet` with zero `.tmp` residue (`read` listing shows no `.tmp` files).

## 4. Guard rails (executor duty 4)

- **POOL-03 zero-execution guard**: `test_research_backtest_guard.py` 7/7 green in the batch — API is `@router.get`-only, imports only `{fastapi, polars, stdlib, app.config}` (whitelist-locked), zero write-pattern tokens (`open(...'w')`/`write_parquet`/`os.replace`/`unlink`/`mkdir` absent from API source), zero forbidden call tokens (`run_all`/`run_preset`/`write_cache`/`persist_point_snapshot`), and service write-target closures (AST-extracted + binding-expanded) all contain `backtest_results` with none of the forbidden lake literals. Service imports whitelist = `{polars, stdlib, auction_columns, auction_validation, pool_snapshot}` (fingerprint co-source exception).
- **POOL-03 E1-E6 regression**: `test_pool_hub.py` spot-run → **36 passed in 0.60s** — the standing zero-execution guard suite unaffected by phase 34.
- **`strategy_cache` untouched**: guard `test_backtest_no_strategy_cache_reference` green; commit file list (below) contains no `strategy_cache`-adjacent module (pool_snapshot untouched this phase — strategy_version co-sourced from the same fingerprint as 33-01, verified equal `7affa346e5e586c5`).
- **Watchlist.tsx zero-touch**: `git status --short` → `staged 0, unstaged 1, untracked 0` with the sole entry `M frontend/src/pages/Watchlist.tsx` (pre-existing user change, never read by any executor or verifier); `git log --oneline -8` = 7 phase-34 commits + 1 plan commit, all backend/docs/planning. Full unique file list of the 8 commits: `.planning/…34-01/02/03-SUMMARY.md` + `d071a3f` plan + `backend/app/api/research_backtest.py` (new), `backend/app/main.py` (+2), `backend/app/services/auction_backtest.py` (new), `backend/app/services/auction_validation.py` (extended), `backend/scripts/auction_backtest.py` (new), `backend/tests/{test_auction_backtest,test_research_backtest_api,test_research_backtest_guard}.py` (new), `backend/tests/test_auction_validation_report.py` (appended), `docs/features.md`. **Zero frontend paths.**
- **No new runtime deps**: no pyproject/requirements/uv.lock in any phase-34 commit; imports reuse the locked polars/duckdb stack.

## 5. SUMMARY cross-checks (executor duty 5)

- **run_id regex `^[0-9a-f]{12}$`**: `research_backtest.py:32` matches claim; all 3 real run_ids (`be4ce9bc038b`, `191642f83b2d`, `0f2b91e93975`) are 12-hex and match their deterministic inputs' sha1 prefixes.
- **404 code `RESEARCH_BACKTEST`**: `research_backtest.py:39-40` (`HTTPException(404, detail={"code":"RESEARCH_BACKTEST", …})`); api test asserts `detail["code"] == "RESEARCH_BACKTEST"` on unknown run and 400 on malformed.
- **Manifest keys**: `_build_manifest` 11-key set `{run_id, origin, strategy_version, created_at, window, strategies, params, coverage, per_date, minute_note, fingerprint}` — identical key set verified in all 3 real manifests (script read), matching the api-test skeleton `_manifest` field-for-field.
- **`strategy_version=7affa346e5e586c5`**: present in all 3 real manifests, equal to 33-01's recorded provenance — pool_snapshot co-source confirmed.
- **Executor "42 tests" / "46 passed" / "17 passed"**: reconciled with the single 57-test batch (6+20+6+14+7+4) — no overlap double-count, all green.

## 6. Human items (deploy-verified — not assertable in sandbox)

1. **Full-universe real-branch backtest** after the 3-5.5h auction backfill (D3): sandbox verified the real branch only on the sparse 2-symbol lake (Run B = 12 honest hit rows) and the full-market EOD branch (Run A). A full-universe real-column run (`kline_auction` covering all ~5537 enriched symbols) requires the operator backfill and is deploy-verified per standing policy.
2. **Live server query smoke on port 3019 (optional)**: the query endpoints were verified hermetic (TestClient, tmp lake) + against the real lake shape by direct file inspection; an in-server smoke against a running deployment remains available as an optional deploy check.

## 7. Honesty notes

- All PASS evidence above is hermetic `[TEST]` unless tagged `[OBSERVED]`; the real-lake facts (§3) were directly re-read and recomputed by this verifier (polars reads of `part.parquet`, `manifest.json`, `kline_daily` partitions; live CLI idempotent re-run), not taken on faith from SUMMARY text.
- The idempotent re-run performed by this verifier wrote nothing (fingerprint skip → `reused=True`); lake state before/after is byte-identical (same created_at).
- One sampled Run A row's third value pair matches at the stored 6-decimal precision (stored values are rounded to 6 dp); the recompute is exact at 9 dp. First two rows match exactly — BT-04 formula semantics confirmed.
