# Phase 37 PLAN-CHECK — 全量真列回测重跑 (RC-01..04)

**Checked**: 2026-08-07 (PlanCheckerP37, read-only except this file)
**Inputs**: RESEARCH.md, PATTERNS.md, 37-01/02/03-PLAN.md, REQUIREMENTS.md, ROADMAP.md, live source + tests + real lake
**Verdict**: **EXECUTABLE** — 0 blockers, 6 warnings (1 substantive, 5 minor/cosmetic)

---

## 1. Verdict

No structural blocker. Goal-backward trace RC-01..04 → tasks → files/commands/acceptance is complete and anchored. The fingerprint design is deterministic and idempotency-preserving; the force path preserves the manifest key-set contract and atomic-write invariants; the rerun honesty framing matches the measured lake/baselines (all re-verified against the live repo this session). All plan-filed anchor corrections are accurate.

---

## 2. Blockers

None.

---

## 3. Warnings

| # | Severity | Location | Finding | Fix |
|---|---|---|---|---|
| W1 | **MEDIUM** (test-as-specified fails if the recommended option is followed) | 37-03 T3-B (`main(["--force"]) → 0` with honest-empty dict) | `main`'s return rule is `return 0 if result.get("status") in ("ok", "reused") else 1` (scripts/auction_backtest.py:233). A fake returning `{"status": "no_enriched", "empty_reason": "enriched_unavailable"}` → **exit 1**, not 0. The plan text first claims "no_enriched → exit 0 per main's return rule" (false) then recommends exactly that dict for a `→ 0` assertion — self-contradictory. | Use the `{"status": "ok", ...}`-shaped dict for exit-0 assertions (or assert `main(["--force"]) == 1` with the honest-empty dict). Note the ok-shaped fake must carry **every** key `_print_summary` reads (run_id, status, wrote, reused, strategy_version, origin, window.requested_*/effective_*, strategies, coverage.symbols 5 keys, path, rows with `.height`) — lines 154-183. |
| W2 | LOW (cosmetic, no functional impact) | 37-01 T4 / 37-03 T5 `-k "no_strategy_cache or ..."` on test_pool_hub.py | No test in test_pool_hub.py contains `no_strategy_cache` (verified via collect-only: the clause selects nothing; `no_execution`/`get_only`/`writes_only` clauses keep exit 0). The actual E3 mirror `test_backtest_no_strategy_cache_reference` lives in test_research_backtest_guard.py:239 and **is** run — so E3 coverage is real; only the pool_hub clause label is a no-op. | Optional: drop the `no_strategy_cache` clause from the pool_hub `-k` (E3 is covered by the guard file) or keep as-is (harmless). |
| W3 | LOW (per-requirement shape; known limitation) | 37-01 T2 (digest = symbol_count, enabled-date count) | RC-01's "e.g." digest shape does not detect same-coverage content changes (e.g. a re-backfill that fixes values while keeping 37 symbols × 248 dates) → same run_id → `reused=True` stale. `--force` (37-03) is the documented escape hatch; `auction_rows_present` is computed in the identical scan (`_coverage_symbols` :392) and could be added to the digest at zero extra cost. | Acceptable as planned; optional strengthening: add `rows_present` to the digest tuple. |
| W4 | LOW (wording) | 37-02 T1 Change A (`_MINUTE_NOTE`) | New note juxtaposes "auction_intraday_confirm 恒空 (BT-10)" with "52,591 全市场恒定" — reads contradictory. "恒空" refers only to the **minute-confirmation** dimension (rows carry `minute_confirm="not_applied"`; measured 52,591 daily-prefilter hits, manifest 1cbb901a5637). The manifest `minute_note` test (:452 `"kline_minute" in ...`) stays green. | Optional reword: "minute 确认恒空 (BT-10)". Also update the stale CLI module docstring line scripts/auction_backtest.py:17-18 ("auction_intraday_confirm 恒空") for consistency. |
| W5 | LOW | 37-02 T6 (9dp spot-check) | Recompute reads `kline_daily` raw open/close; stored rows carry enriched-panel values. Equality to 1e-9 requires enriched open/close == kline_daily open/close (caliber match). Precedent passed (docs/features.md:81 — 34-03 手核 kline_daily 通过), so low risk; verifier should confirm the price caliber before asserting. | Keep as planned; verify caliber in the first checked row before the ≥5-row pass. |
| W6 | LOW (line-drift nits) | PATTERNS.md / RESEARCH.md vs source | Confirmed correct anchors: `_coverage_symbols` def = :376 (PATTERNS.md said :260 — 37-03 SUMMARY item 5 already corrects); `_preload_full_enriched` def = :121 (research said :134-157); intraday filter = :38-43 (research said :42-45). Minor residual drift: `_persist_run` fingerprint-match branch is :735-737 (37-03 T1 cites :725-737); "symbols 纳入哈希" rationale is in the `_compute_run_id` docstring ~:618-621 (37-01 T2 cites :624-628). None affect implementation. | No action (already corrected in 37-03 SUMMARY; cited ranges overlap the target code). |

---

## 4. Anchor verification (all re-read live this session)

| Anchor | Claimed | Verified |
|---|---|---|
| `_MINUTE_NOTE` | :67 | :67 ✓ |
| `_coverage_symbols` | :376 | def :376 ✓ (window-scan semantics match plan's T1 helper verbatim: glob `date=*/part.parquet`, fromisoformat, skip bad/empty/missing-symbol, window filter, fail-closed) |
| `run_full_backtest` | :426 | :426 ✓ |
| step ④ injection | :493 | :493 ✓ (`attach_auction_columns_range`; `auction_enabled_dates` computed :496) |
| run_id computation | :513 | :513 ✓ — single `_compute_run_id` call site in repo (grep: def :614, call :513 only) |
| manifest fingerprint block | :555-562 | :555-562 ✓ |
| `_persist_run` call | :591 | :591 ✓ — single call site |
| `_compute_run_id` | :614 | :614-640 ✓; blob = pipe-joined `strategy_ids|start|end|params|version|symbols` → sha1[:12] |
| `_build_manifest` | :680 | :680 ✓; `minute_note` and `fingerprint` keys present |
| `_persist_run` | :712 | :712-743 ✓; reused branch (fingerprint match → `(run_dir, False, True)`) :735-737; manifest-last atomic write invariant |
| `_atomic_write_parquet`/`_atomic_write_json` | — | :662/:670 ✓ (`.tmp` + atomic replace) |
| CLI `_preload_full_enriched` | :121 | :121-147 ✓ |
| CLI `_print_summary` | :149-183 | :149-183 ✓ |
| CLI `_parse_args` | :92-118 | :92-118 ✓ (`--rpm` ends ~:118, `--force` insertion point after it is free) |
| CLI `main` | :187-236 | :187-236 ✓; DATA_DIR default = repo `data/` (:190); return rule `ok|reused → 0` (:233) |
| intraday_confirm filter | :38-43 | `def filter` :37, body :38-43 ✓ — `pl.col("open_gap") >= min_gap` only; EOD 列一票否决 |
| idempotency test | :357 | `test_full_backtest_deterministic_run_id_idempotent` :357-417 ✓ |
| manifest set-equality | :440-444 | `assert set(manifest) == {...11 keys...}` :441-445 ✓; substring checks `"start"/"symbols" in fingerprint` :414-415 ✓ |
| minute-annotation test | :419-470 | `test_full_backtest_minute_annotation_and_manifest` :419-480 ✓ |
| E3 guard | — | `test_backtest_no_strategy_cache_reference` test_research_backtest_guard.py:239 ✓; whitelist :255, E2 write-root :220, GET-only :203, no-execution :191 ✓ |
| API GET-only + run_id 12-hex | — | research_backtest.py:160/185 GET-only; `_RUN_ID_RE ^[0-9a-f]{12}$` :32 → 400; `as_of: date` → bad date 422 ✓ |
| hermetic API client pattern | :31-42 | test_research_backtest_api.py:31-42 `_make_client` ✓ |
| CLI hermetic pattern | 36-01 | `test_full_backfill_cli_writes_terminal_json` test_auction_backfill_full_universe.py:489 (importlib spec load) ✓ |
| `verify_auction_backfill.py` | 36-02 | backend/scripts/verify_auction_backfill.py exists ✓ |

## 5. Live cross-checks (this session, read-only)

- **Lake state**: `data/kline_auction/` = **248 partitions** (2025-07-29..2026-08-05), **8,951 rows**, **37 distinct symbols** — matches RESEARCH/37-02 claims exactly (37/5537 = 0.67%; rows_expected 5537×248 = 1,373,176).
- **Baseline manifests** (all 6 run dirs dumped): `be4ce9bc038b` EOD 32,686+203,221+11,926+81,254 = **329,087** ✓; `191642f83b2d` col-gated real **12** (3+6+1+2) @ 2 symbols ✓; `1cbb901a5637` intraday_confirm **52,591** (n_symbols_hit 5,230 — already full-market in sparse lake), coverage 2/5537 ✓; `45fb75b65731` 50-symbol run ✓. "6 old + 1 fresh = 7" (37-03 T4) matches.
- **intraday_confirm invariance is structurally sound**: `_evaluate_strategy_rows` :309-311 gates `requires_auction_data` strategies by **dates** (`eval_panel` filtered on `auction_enabled_dates`), not symbols; the sparse lake already enables all 248 dates → hits already full-market (52,591 measured) → backfill (symbols only) cannot change them. No blocker.
- **Fingerprint determinism**: digest members are `(int, int)` counts — no NaN/datetime; `_lake_auction_symbol_count` uses only `len(set)` over a sorted glob; `auction_enabled_dates` is `sorted(set(...) & set(...))`. Same lake + same inputs → same run_id; coverage flip → blob changes → new run_id. `lake_digest=None` default keeps the legacy blob; the single call site :513 passes it keyword-wise.
- **Digest consistency**: `_lake_auction_symbol_count` mirrors `_coverage_symbols` scan semantics verbatim → digest == `coverage.symbols.auction_symbol_count`; `len(auction_enabled_dates)` == `coverage.dates.auction_enabled_count` — "no view-vs-scan drift" claim verified.
- **Force path contract**: `rewritten_at` added only on the force branch (test_research_backtest_guard E2 sees no new write target — plain dict assignment; `datetime`/`timezone` already imported :512); key-set test :441 runs without force → green; force rewrites via existing `_atomic_write_*` (`.tmp` + replace, no residue); same run_id → in-place overwrite of a freshly recomputed full `rows_df`, manifest written last (invariant kept). No blocker.
- **37-01 T3-A r6/r7 logic**: `_seed_enriched_cache(days=3, start=d0)` uses calendar-day increments → exactly d0..d2; `cache_max=d2` → default window end covers the new d2 partition; `attach_auction_columns_range` enables non-empty partitions with symbol column → enabled dates 2→3 → digest flips → `r6.run_id != r1.run_id`, `wrote=True`; r7 same-lake → `reused=True`. Test-selection verified: `-k "run_id"` currently collects exactly 1 (will be 2); `-k "force or cli"` collects exactly the 2 new 37-03 tests (no collisions).
- **Guard batches**: `-k "no_strategy_cache or no_execution or get_only"` and `"... or writes_only"` each collect ≥3 tests in test_pool_hub.py → exit 0 (W2 covers the no-op clause).

## 6. Per-RC coverage

| Req | Criterion (goal-backward) | Where in plans | Verdict |
|---|---|---|---|
| RC-01 | digest in `_compute_run_id` (auction_symbol_count + enabled-date count); coverage flip → fresh run_id; same lake → reused; test extends :357; 12-hex kept | 37-01 T1-T4 (helper, blob+wiring+fingerprint `lake_coverage`, tests, guard batch) | COVERED — deterministic, backward-compatible, single call site |
| RC-02 | honest current-lake rerun (0.67%, 8,951/1,373,176); gated-4 12 → hundreds+ [measured]; EOD 329,087 ==; intraday 52,591 ==; runtime ≤10s; ≥0.94 = post-recovery operator command; ROADMAP deviation annotated | 37-02 T2-T5 + 37-03 T7 (SUMMARY) | COVERED — all numbers re-verified against live lake/manifests; deviation handling explicit |
| RC-03 | rows_present < expected honest partial; backfilled/5537 framing; intraday_confirm branch=real annotation (manifest + CLI); BT-04 9dp verifier spot-check | 37-02 T1, T3, T4, T6 | COVERED (W4/W5 wording/caliber nits) |
| RC-04 (P2) | `--force` CLI escape hatch (CLI-only, rewritten_at provenance); run_id dirs queryable at scale via GET; E3 guard green; docs + SUMMARY | 37-03 T1-T7 | COVERED (W1: test-as-specified exit-code contradiction — use ok-shaped dict) |

## 7. Notes for the executor

- Land 37-01 first (waves 2/3 depend on the digest); the digest changes pre-fix run_id identity **by design** — old runs stay readable via the API, never invalidated.
- 37-03 T3-B: follow the `{"status": "ok", ...}` alternative, not the honest-empty dict, for exit-0 assertions (W1).
- Real-lake rerun (37-02 T3) is local-only and safe: writes only `data/backtest_results/` (gitignored); no network; upstream 403-blocked so no concurrent backfill risk between Run 1 and Run 2.
- No frontend files touched in any wave; `frontend/src/pages/Watchlist.tsx` untouched.
