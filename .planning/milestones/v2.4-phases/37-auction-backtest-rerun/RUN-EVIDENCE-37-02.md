# RUN-EVIDENCE-37-02 — RC-02/03 Honest Current-Lake Rerun + Coverage Reporting

**Phase**: 37-02 (wave 2, runs after 37-01 RC-01 fingerprint landed as `65426a3`)
**Executed**: 2026-08-07 (real lake measured; local parquet only, zero network)
**Precondition**: 37-01 `65426a3` in git log before Run 1 (the rerun's fresh run_id is only meaningful with the RC-01 lake-coverage digest). Verified at preflight: `pytest tests/test_auction_backtest.py -k "run_id"` → 2 passed.
**Single evidence source** for 37-03 docs/SUMMARY. All numbers measured, no fabrication.

---

## 1. Before-state (baseline, verified 2026-08-07)

**Lake** (`data/kline_auction/`, scan via repo venv polars):

| Fact | Value |
|---|---|
| Partitions (`date=*`) | **248** |
| Rows | **8,951** |
| Distinct symbols | **37** |
| Rows expected (5537 × 248) | 1,373,176 |

**Baseline run manifests** (`data/backtest_results/run_id=*/manifest.json`):

| run_id | Content (manifest facts) |
|---|---|
| `be4ce9bc038b` | Run A — 4 EOD strategies: auction_bullish 32,686 / auction_early_star 203,221 / auction_preopen_quant 11,926 / golden_230 81,254 = **329,087 total**; coverage.symbols auction_symbol_count **2** / enriched 5537 / ratio 0.0004; rows_present 496/1,373,176 |
| `191642f83b2d` | Run B — col-gated real hits **12** @ 2 symbols: auction_allround 3 / auction_alpha 6 / auction_fast_grab 1 / t1_flash 2; coverage 2/2 |
| `1cbb901a5637` | 9-strategy full market: auction_intraday_confirm **52,591** (n_symbols_hit 5,230 — already full-market in sparse lake); coverage.symbols auction_symbol_count 2/5537; rows_present 496/1,373,176 |

---

## 2. Rerun commands (verbatim) + runtime

Run 1 (the rerun itself — 9 strategies × 248 enriched days × full market, current lake):

```
cd backend && time .venv/bin/python scripts/auction_backtest.py --range 248
```

Runtime: **elapsed 2.4s (in-script) / real 5.235s (wall clock)** — ≤10s criterion **PASS**.

Run 2 (idempotency proof on the SAME lake — RC-01 acceptance on real data):

```
cd backend && .venv/bin/python scripts/auction_backtest.py --range 248
```

Runtime: elapsed 2.0s / real 4.719s.

---

## 3. After-state (Run 1, fresh run_id)

- **run_id**: `298d743e8083` — fresh (≠ `1cbb901a5637`; RC-01 digest now includes lake coverage 37/248 vs 2/248 → new fingerprint)
- **status**: `ok`, **wrote**: `True`, **reused**: `False`
- manifest fingerprint `lake_coverage`: `[37, 248]` (RC-01 member present)

**coverage.symbols (manifest verbatim)**:

```json
{"auction_symbol_count": 37, "enriched_symbol_count": 5537, "symbol_coverage_ratio": 0.006682318945277226, "auction_rows_present": 8951, "auction_rows_expected": 1373176}
```

**Per-strategy hits** (manifest):

| strategy | branch | n_hits | n_symbols_hit | vs baseline |
|---|---|---|---|---|
| auction_allround | real | 214 | 34 | Run B 3 |
| auction_alpha | real | 336 | 36 | Run B 6 |
| auction_fast_grab | real | 31 | 18 | Run B 1 |
| t1_flash | real | 139 | 33 | Run B 2 |
| auction_bullish | eod | 32,686 | 5,041 | Run A == |
| auction_early_star | eod | 203,221 | 5,508 | Run A == |
| auction_preopen_quant | eod | 11,926 | 4,216 | Run A == |
| golden_230 | eod | 81,254 | 5,454 | Run A == |
| auction_intraday_confirm | real | 52,591 | 5,230 | `1cbb901a5637` == |

**Totals (measured)**:

| Metric | Baseline | After | Verdict |
|---|---|---|---|
| Gated-4 real hits (allround/alpha/fast_grab/t1_flash) | 12 | **720** (214+336+31+139) | 12 → hundreds+ **[measured]** |
| EOD 4 strategies | 329,087 | **329,087** (32,686+203,221+11,926+81,254) | **unchanged** ✓ |
| auction_intraday_confirm | 52,591 | **52,591** | **unchanged** ✓ (branch=real, filter consumes only `open_gap` — intraday_confirm.py:38-43; no auction-column consumption by design) |

CLI summary printed the T1 annotation note (present in Run 1 stdout) and manifest `minute_note` carries the T1 annotation (grep-verified, §8).

---

## 4. Honest framing block (RC-03)

- `rows_present` 8,951 < `rows_expected` 1,373,176 → **honest partial**, no interpolation, never implied full.
- `coverage = 37/5537 = 0.67%` (backfilled/5537 口径). **Never** claimed as a standalone percentage of 1.0, **never** ≥0.94 for this run.
- Full-coverage (≥0.94) rerun = **post-recovery operator command** (§7), zero new code.

---

## 5. Idempotency (Run 2)

| Fact | Run 2 value |
|---|---|
| run_id | `298d743e8083` (same as Run 1) |
| status | `reused` |
| wrote / reused | `False` / `True` |
| part.parquet mtime (before) | 1786078994 |
| part.parquet mtime (after) | 1786078994 — **unchanged** |
| part.parquet size | 10,337,579 bytes — unchanged |

Lake stability between runs: no concurrent backfill possible (upstream 403-blocked); `reused=True` itself proves lake state identical for the fingerprint.

---

## 6. BT-04 9dp forward spot-check (T6, verifier procedure — PASS)

Method: read-only recomputation from `data/kline_daily` (global trading calendar = next `kline_daily` date after T, never per-symbol shift) against `run_id=298d743e8083/part.parquet`. Formulas:
`next_day_open_ret = open_{T+1}/open_T − 1`, `next_day_close_ret = close_{T+1}/open_T − 1`, `open_gap_outcome = open_{T+1}/close_T − 1`.

**W5 caliber pre-check** (enriched stored prices == kline_daily open/close at T and T+1, 8 rows): **PASS** (max |Δ| ≤ 1e-12).

**9dp recomputation** — 12 hit rows (col-gated real strategies) spanning **3 dates × 4 symbols**:

| strategy | symbol | as_of | next_day_open_ret stored | recomputed | diff |
|---|---|---|---|---|---|
| auction_alpha | 000010.SZ | 2025-07-31 | 0.011627906976744207 | 0.011627906976744207 | 0.0 |
| auction_alpha | 000010.SZ | 2025-07-31 | next_day_close_ret 0.09883720930232553 | 0.09883720930232553 | 0.0 |
| auction_alpha | 000010.SZ | 2025-07-31 | open_gap_outcome −0.008547008547008517 | −0.008547008547008517 | 0.0 |
| auction_allround | 000031.SZ | 2025-08-01 | −0.06211180124223603 | −0.06211180124223603 | 0.0 |
| auction_allround | 000031.SZ | 2025-08-01 | next_day_close_ret −0.05900621118012439 | −0.05900621118012439 | 0.0 |
| auction_allround | 000031.SZ | 2025-08-01 | open_gap_outcome −0.013071895424836666 | −0.013071895424836666 | 0.0 |
| t1_flash | 000031.SZ | 2025-08-01 | (matches, diff 0.0) | — | 0.0 |
| … | … | … | 12 rows × 3 cols all diff 0.0 | — | 0.0 |

**Verdict**: worst diff **0.000e+00 < 1e-9** over 12 rows × 3 columns → **PASS** (9dp exact).

**n_missing_outcomes spot-check**: 2,969 rows flagged `outcome_missing=True` across auction_bullish/auction_early_star/auction_preopen_quant/golden_230/auction_intraday_confirm. Checked ≥2 such rows: every flagged row has null `open_t1`/`close_t1`/`next_day_open_ret`/`next_day_close_ret`/`open_gap_outcome` and no (symbol, next-trading-day) row in `kline_daily` (incl. the terminal-date case 2026-08-05 → no next day). Violations: **0** — BT-04 "绝不 0 填/前向填充" preserved.

---

## 7. Post-recovery full-coverage operator command (T5, RC-02 ≥0.94 path)

After upstream xyz recovers AND Phase 36 FA-04's backfill completes the lake to ≈5204 symbols, the operator runs — **one command, 5-10s, zero new code**:

```
cd backend && time .venv/bin/python scripts/auction_backtest.py --range 248
```

Expected (per REQUIREMENTS FA-04/RC-02): coverage 37/5537 → ≈5204/5537 (≥0.94); rows_present → ≈1.29M; gated-4 real hits 720 → thousands+ [measured]; EOD 329,087 unchanged; auction_intraday_confirm 52,591 unchanged; runtime 5-10s. The RC-01 digest guarantees the pre-recovery run_id (`298d743e8083`) is **not** reused — lake coverage differs → fresh run_id, `wrote=True`. Record the outcome here once executed.

---

## 8. Annotation (T1, RC-03)

- Manifest `minute_note` (verbatim, run `298d743e8083`): `kline_minute 历史 CLOSED — 确认维度诚实受限; auction_intraday_confirm minute 确认恒空 (BT-10); auction_intraday_confirm branch=real 日线初筛仅消费 open_gap (enriched 派生列, 非竞价列) — 其 hits 不随湖覆盖增长 (52,591 全市场恒定, 2026-08-07 实测)`
- CLI summary prints the note when `auction_intraday_confirm` is among run strategies (observed in Run 1 stdout).
- Test `test_full_backtest_minute_annotation_and_manifest` extended to assert `"不随湖覆盖增长" in manifest["minute_note"]`; manifest key-set exact-equality still green.
- Guard batch pre-rerun: `pytest tests/test_auction_backtest.py tests/test_research_backtest_guard.py tests/test_research_backtest_api.py -q` → **18 passed**.

---

## 9. Read-only API at-scale check (37-03 T4, RC-04 — appended by ExecutorP3703)

**Method**: TestClient bootstrapped on the real repo-root `data/` dir (`settings.data_dir = data/`; minimal FastAPI app + stub auth, mirroring `test_research_backtest_api.py:31-42`). No live server (port 3018 is the stale D8 container — deliberately not used). Read-only: GET-only router, zero writes.

**Six calls, all measured 2026-08-07** (response time = wall clock):

| # | Call | Expected | Measured | Verdict |
|---|---|---|---|---|
| 1 | `GET /api/research/backtest` | 200; count == backtest_results run dirs; includes fresh run_id | 200; **count=7** (6 old + fresh `298d743e8083`); fresh present | PASS |
| 2 | `GET /api/research/backtest/298d743e8083` | 200; `stats.n_rows` == part.parquet height; `len(sample)` ≤ 20; per_strategy/per_date sums reconcile | 200; **n_rows=382,398** (== part.parquet height); sample=20; per_strategy sum **382,398**; per_date sum **382,398** | PASS |
| 3 | `GET /api/research/backtest/298d743e8083?strategy=auction_fast_grab&branch=real` | 200; n_rows == fast_grab real hits (31) | 200; **n_rows=31** (predicate pushdown at scale) | PASS |
| 4 | `GET /api/research/backtest/1cbb901a5637` | 200 (pre-rerun full-market run still served — old runs never invalidated) | 200; **n_rows=381,690** | PASS |
| 5 | `GET /api/research/backtest/298d743e8083?as_of=bad-date` | 422 (contract untouched) | **422** | PASS |
| 6 | `GET /api/research/backtest/zzz` | 400 `RESEARCH_BACKTEST` (12-hex run_id) | **400** | PASS |

**Response times (wall clock, TestClient on real data)**: detail on the 382,398-row part.parquet = **0.052s** (sub-second; polars scan + predicate pushdown); pushdown detail = **0.015s**; old-run detail = **0.039s**; list = **0.012s**.

**Honest skip at scale**: `backtest_results/` contains only `run_id=*` directories (0 flat `*.parquet` files); the count=7 check confirms no vectorbt flat file is misread as a run (the flat-file coexistence case stays unit-tested in `test_research_backtest_api.py`).
