---
phase: 37-auction-backtest-rerun
verified: 2026-08-07T10:00:00Z
status: passed
score: 4/4 RC requirements — RC-01/02/03/04 verified (RC-02 honest current-lake form with the ≥0.94 full-coverage rerun source-gated, see behavior_unverified)
behavior_unverified: 1 — RC-02 ≥0.94 full-coverage rerun (coverage 37/5537 → ≈5204/5537) NOT met: upstream xyz MCP policy-blocked (403, Phase 36 FA-04 backfill incomplete); the committed ≥0.94 rerun is a documented post-recovery operator command (one CLI invocation, zero new code), never claimed by this phase
overrides_applied: 0 — no REQUIREMENTS.md/ROADMAP.md text changed; the honest current-lake rerun (0.67% not ≥0.94) is annotated in RUN-EVIDENCE-37-02.md §4/§7 and 37-03-SUMMARY §1, not papered over
human_verification: 3 items (post-recovery ≥0.94 operator rerun, intraday_confirm no-column-consumption by-design acceptance, wall-clock TestClient timings as representative) — sandbox cannot assert; labeled deploy-verified per standing policy
---

# Phase 37 Verification — 全量真列回测重跑 (RC-01..04)

**Verifier:** VerifierP37 · **Date:** 2026-08-07 · **Scope:** Phase 37 RC-01..04 (run_id lake-coverage fingerprint, honest current-lake rerun + coverage reporting, intraday_confirm annotation, `--force` escape hatch + at-scale read-only API)
**Method:** Goal-backward, behavior-level — 3-file pytest batch (20 passed, reproduced exactly) + code-level file:line evidence + guard-rail checks + direct read-only re-inspection of the live lake and run artifacts (manifest, part.parquet, kline_daily recomputation, TestClient on real `data/`). Live-lake numbers re-derived by this verifier, not taken from SUMMARY. **RC-02's committed ≥0.94 rerun remains source-gated** (upstream 403, Phase 36 FA-04 backfill incomplete) — recorded honestly in `behavior_unverified`, never claimed.

## Verdict: **PASSED** (RC-02 ≥0.94 acceptance honest-deferred)

All four RC requirements verified against code + tests + live artifacts (RC-01 fingerprint semantics, RC-02 honest current-lake rerun 37/5537 = 0.67% with 12→720 gated-4 [measured], RC-03 honest-partial framing + BT-10 annotation + 9dp BT-04 spot-check, RC-04 `--force` provenance + sub-second at-scale API). 20 passed, 0 failures. The only unmet committed acceptance (≥0.94 coverage) is an external source-side gate with a documented zero-code operator path. No needs-fix items in code.

---

## 1. Test batch (executor duty 1)

```
cd backend && .venv/bin/python -m pytest tests/test_auction_backtest.py tests/test_research_backtest_guard.py tests/test_research_backtest_api.py -q
→ 20 passed in 2.59s   (matches orchestrator claim exactly)
```

- Backtest 9 (incl. extended idempotency r6/r7 + new digest unit + minute-annotation + force/CLI) · guard 7 (E1/E2/E3/GET-only/whitelist/no-execution) · api 4.
- Idempotency spot-check by this verifier (read-only-safe CLI rerun, §5): same command → `run_id=298d743e8083`, `status: reused`, `wrote: False`, `reused: True`, part.parquet mtime **1786078994** and size **10,337,579** byte-identical before/after — RC-01 acceptance reproduced on the real lake, not just in tests.

## 1b. Behavioral summary (goal-backward, per RC)

- **RC-01 — run_id lake-coverage fingerprint.** `_compute_run_id` gains keyword-only `lake_digest` (auction_symbol_count, auction_enabled_dates); the blob appends `|lake:{n}:{m}` so a backfilled lake produces a fresh run_id (`wrote=True`) instead of silently reusing stale data; same lake + same inputs stays idempotent (`reused=True`, partition untouched). Digest helper mirrors `_coverage_symbols` partition-scan semantics verbatim → zero view-vs-scan drift with the honest coverage report; fail-closed 0 on broken/empty lake. `lake_digest=None` keeps the pre-fix blob (backward-compatible default). run_id stays `^[0-9a-f]{12}$`.
- **RC-02 — honest current-lake rerun.** Full-market rerun on the current lake: coverage 0.036% → 0.67% (37/5537), rows_present 496 → 8,951, gated-4 real hits **12 → 720 [measured]**, EOD 4 strategies **329,087 unchanged**, auction_intraday_confirm **52,591 unchanged**, runtime **5.18s wall (≤10s PASS)**. Never interpolated; `rows_present 8,951 < rows_expected 1,373,176` stated plainly. The ≥0.94 full-coverage rerun is a documented post-recovery operator command (RUN-EVIDENCE §7) — zero new code, and the RC-01 digest guarantees the pre-recovery run_id is not reused.
- **RC-03 — honesty + annotation.** Coverage framed as 37/5537 = 0.67% (backfilled/5537), never a standalone percentage of 1.0, never ≥0.94. Manifest `minute_note` + CLI summary annotate auction_intraday_confirm: branch=real daily prefilter consumes only `open_gap` (enriched derived column, **not** auction columns) — hits don't grow with lake coverage (52,591 constant, measured 2026-08-07); minute-confirm dimension honestly CLOSED (BT-10). BT-04 forward metrics re-derived to 9dp (worst diff 0.0); `n_missing_outcomes` counting verified (2,969 flagged, all null-formula — never 0-filled).
- **RC-04 (P2) — `--force` + at-scale API.** CLI `--force` bypasses the fingerprint idempotent early-return and rewrites the run, recording `rewritten_at` (UTC, seconds) in the manifest **only** on the force path → exact manifest key-set contract unchanged for normal runs. Zero API surface (GET-only guard green). Read-only API serves the 382,398-row part.parquet sub-second; 6-call TestClient matrix reproduced by this verifier on real `data/`.

## 2. RC evidence table

| Req | Evidence (file:line) | Test(s) / live check | Result |
|-----|----------------------|----------------------|--------|
| **RC-01** | `_lake_auction_symbol_count` `auction_backtest.py:380-407` (read-only: glob `date=*/part.parquet`, `fromisoformat` dir parse, bad-name/empty/missing-`symbol` skip, window filter, exception → skip; fail-closed 0; zero write patterns — no `_WRITE_PATTERNS` match) · `_compute_run_id` `:657-690` kw-only `lake_digest` `:665`, blob append `f"\|lake:{n}:{m}"` `:688-689` after `sorted(symbols)`, `sha1(...)[:12]` `:690` · single call site `:554-555` (digest = `(_lake_auction_symbol_count(data_dir, eff_start, eff_end), len(auction_enabled_dates))`, step ⑤-1 `:549-553`) · manifest fingerprint member `"lake_coverage": list(lake_digest)` `:605` · `_build_manifest` provenance note `:747-749` | extended `test_full_backtest_deterministic_run_id_idempotent` r6/r7 (`tests/test_auction_backtest.py:410-417`: lake gains partition → fresh run_id + `wrote=True`; same lake → `reused=True`) · new `test_full_backtest_run_id_lake_digest_tracks_coverage` `:431-445` (sparse≠full, same digest idempotent, None → legacy blob, 12-hex regex) · **live**: manifest `298d743e8083` fingerprint `lake_coverage=[37,248]` re-read by verifier; own CLI rerun → same run_id, `reused=True`, part mtime/size unchanged | **PASS** |
| **RC-02** | rerun evidence `RUN-EVIDENCE-37-02.md` §1-§5 (before-state lake facts, verbatim commands, runtime 5.235s/4.719s, after-state per-strategy hits, coverage 5-key block `{auction_symbol_count 37, enriched_symbol_count 5537, symbol_coverage_ratio 0.00668…, auction_rows_present 8951, auction_rows_expected 1373176}`, EOD/intraday invariance table, idempotency Run-2 mtime/size, post-recovery command §7) | **live re-measure** by verifier: `part.parquet` for `298d743e8083` — gated-4 **720** (allround 214/alpha 336/fast_grab 31/t1_flash 139, branch=real), EOD 4 **329,087**, intraday **52,591**, total **382,398** = 720+329,087+52,591; CLI rerun prints honest `coverage: auction_symbols=37 enriched_symbols=5537 ratio=0.67% rows_present=8951/1373176`, wall **5.183s**; lake 248 partitions / 8,951 rows / 37 symbols / 0 `.tmp` | **PASS** (≥0.94 deferred, §6) |
| **RC-03** | `_MINUTE_NOTE` `auction_backtest.py:66-71` ("日线初筛仅消费 open_gap (enriched 派生列, 非竞价列)… 不随湖覆盖增长") → manifest `minute_note` `:760` · CLI `_print_summary` note `scripts/auction_backtest.py:189-193` (prints when auction_intraday_confirm ∈ strategies) · intraday_confirm filter `app/strategy/builtin/auction_intraday_confirm.py:38-43` (`open_gap`-only, `pl.lit(False)` when column absent) · BT-04 formulas `auction_validation.py:477-480` (never 0-fill/forward-fill) | `test_full_backtest_minute_annotation_and_manifest` asserts `"不随湖覆盖增长" in manifest["minute_note"]` + exact key-set equality (still green) · **live**: manifest `minute_note` contains the fragment (verifier re-read); CLI rerun stdout prints both `note: …open_gap (enriched 派生列)…` and `BT-10: minute_confirm=not_applied` · **independent 9dp re-derivation** (verifier): 12 hit rows × 3 cols recomputed from `kline_daily` + global calendar → worst \|Δ\| **0.000e+00 < 1e-9** (36/36 checks) · n_missing: **2,969** flagged `outcome_missing=True`, 100% null formula columns (no 0-fill) | **PASS** |
| **RC-04** (P2) | `force: bool = False` kw-only in `run_full_backtest` `auction_backtest.py:468` and `_persist_run` `:771`; fingerprint-match branch `:793-799` — `if not force: … return reused` else rewrite + `manifest["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")` `:799` (**only** force path; key-set contract untouched) · CLI `--force` `scripts/auction_backtest.py:119-123` (after `--rpm`, help text "仅 CLI, 零 API 面") + pass-through `:240` · zero API surface (GET-only router untouched) | `test_full_backtest_force_rewrites_when_fingerprint_matches` (`tests/test_auction_backtest.py:565-601`: same run_id, `wrote=True`, part mtime changes, `rewritten_at` present, post-force idempotency `reused=True`, no `.tmp`) · `test_full_backtest_cli_force_flag` `:603-661` (`--help` exit 0 lists `--force`; hermetic `main(["--force"])` → `force=True`) · guard `test_backtest_api_is_get_only` green · **at-scale re-run by verifier** (TestClient on real `data/`): list 200 **count=7** incl. fresh run (12ms); detail `298d743e8083` 200 **n_rows=382,398** sample=20 (72ms); pushdown `?strategy=auction_fast_grab&branch=real` 200 **n_rows=31** (17ms); old run `1cbb901a5637` still 200 **381,690** (60ms); `as_of=bad-date` → **422**; `zzz` → **400** — all sub-second, GET-only | **PASS** |

## 3. Guard rails (executor duty 3)

- **Zero new imports**: `git diff 26dbd44..4e462a4 -- backend/app/services/auction_backtest.py backend/scripts/auction_backtest.py | grep -E "^\+.*(import|from) "` → **empty**; `test_backtest_import_whitelist` (AST, `_SERVICE_IMPORT_EXACT`) green in batch. Digest helper uses only already-imported `polars`/`datetime`/`pathlib`; `--force` uses already-imported `datetime.timezone`.
- **Zero new deps**: phase-37 commit surface = service + CLI + tests + `docs/features.md` + `.planning/` — **no** pyproject/requirements/uv.lock in `git diff 26dbd44..4e462a4`.
- **`strategy_cache` untouched**: absent from all phase-37 commits; `test_backtest_no_strategy_cache_reference` (E3) green in batch.
- **Watchlist.tsx zero-touch**: `git status --short` → single pre-existing `M frontend/src/pages/Watchlist.tsx` (user change, never read by this verifier or executors); `git diff 26dbd44..4e462a4 -- frontend/` → **empty**.
- **No network in rerun path**: rerun reads local `data/` parquet only (observed: 5.18s wall, zero network — the phase exists precisely because the upstream source is 403-blocked); writes land only under `data/backtest_results/` via `_atomic_write_*` (E2 guard green).

## 4. Cross-check claims (executor duty 4)

- **(a) `backtest_results/run_id=298d743e8083/manifest.json` contains `lake_coverage` [37, 248] + fingerprint** — verifier's own read: `fingerprint.lake_coverage == [37, 248]`; fingerprint key set `{start, end, params, strategy_ids, strategy_version, symbols, lake_coverage}`; `coverage.symbols` matches RUN-EVIDENCE byte-for-byte (37/5537/0.006682318945277226/8951/1373176); `coverage.dates.auction_enabled_count == 248`. **PASS**
- **(b) API list count=7** — both the manifest-dir count (`ls data/backtest_results` → 7 `run_id=*` dirs: `0f2b91e93975, 191642f83b2d, 1cbb901a5637, 298d743e8083, 45fb75b65731, 808be6bb00e1, be4ce9bc038b`) and the live TestClient `GET /api/research/backtest` (`count=7`, fresh run present). **PASS**
- **Consistency**: `382,398 = 720 (gated-4) + 329,087 (EOD 4) + 52,591 (intraday)` verified from part.parquet; old full-market run `1cbb901a5637` = 381,690 = 329,087 + 52,591 + 12 (pre-RC-01 gated-4) — delta 708 exactly the measured 12→720 increase.

## 5. SUMMARY cross-checks (executor duty 5)

- All 5 phase-37 commits present and in order: `65426a3` (RC-01, code+tests only), `caecaf4` (RC-03 annotation), `43211ca` (RUN-EVIDENCE, docs), `961141e` (RC-04 code+tests), `4e462a4` (docs/SUMMARY) — surfaces match claims (docs commits touch only docs).
- Anchor drift table (37-03-SUMMARY §5) re-verified against live file: `_coverage_symbols` :410, `_preload_full_enriched` :128, intraday_confirm filter :38-43, `_compute_run_id` :657, `_persist_run` :765 — all match.
- Orchestrator's "20 passed" reproduced exactly (2.59s). RUN-EVIDENCE per-strategy hits table reproduced from part.parquet (214/336/31/139/32,686/203,221/11,926/81,254/52,591).
- RUN-EVIDENCE §6's 9dp spot-check re-derived independently (12 rows × 3 cols, worst diff 0.0) — not taken on faith.

## 6. RC-02 ≥0.94 honest-PARTIAL status + recovery path (source-gated)

**What is verified**: the honest current-lake rerun end-to-end — RC-01 digest (fresh run_id on coverage change, idempotent reuse on same lake), coverage 0.67% (37/5537) with rows_present 8,951 / expected 1,373,176, gated-4 real hits 12 → 720 [measured], EOD 329,087 and intraday 52,591 invariance, runtime 5.18s ≤ 10s, BT-04 9dp + n_missing honesty, intraday_confirm annotation (by-design no auction-column consumption), `--force` escape hatch, at-scale read-only API.

**What is NOT verified (behavior_unverified)**: the committed RC-02 acceptance — full-coverage rerun at **≥0.94 (≈5204/5537)** with rows ≈1.29M. Cause: upstream xyz MCP policy-blocked (403) since Phase 36 FA-04; the backfill never completed. The phase's rerun is the honest current-lake rerun; the ≥0.94 rerun is a documented **post-recovery operator command** (RUN-EVIDENCE-37-02.md §7): `cd backend && time .venv/bin/python scripts/auction_backtest.py --range 248` — one command, 5-10s, zero new code; the RC-01 digest guarantees a fresh run_id (`wrote=True`) when lake coverage changes. Never interpolated, never claimed ≥0.94.

## 7. Human items (deploy-verified — not assertable in sandbox)

1. **Post-recovery ≥0.94 operator rerun (external gate)**: after upstream xyz recovers AND Phase 36 FA-04 completes the backfill (≈5204 symbols), the operator runs the one-command rerun above and records the outcome (expected: coverage ≈0.94+, rows ≈1.29M, gated-4 thousands+, EOD/intraday unchanged). Sandbox cannot run a full-universe rerun against a blocked source.
2. **intraday_confirm real-branch-no-column-consumption is by-design (BT-10)**: the 52,591 intraday hits are a daily prefilter consuming only the enriched derived `open_gap` column — they do not grow with lake coverage by construction, not a bug; the minute-confirm wiring is Phase 38's MN-01..04. Acceptable per BT-10 stance; flagged for operator awareness.
3. **Wall-clock API timings are representative, not benchmark-grade**: TestClient on the real `data/` (detail 0.052s claimed; verifier re-measured 0.072s on a fresh interpreter — same order, sub-second). No live server (port 3018 is the stale D8 container, deliberately unused).

## 8. Honesty notes

- All PASS evidence above is hermetic `[TEST]` or directly re-observed by this verifier: my own CLI rerun (reused=True, mtime/size unchanged), my own polars reads of the manifest/part.parquet/kline_daily, my own TestClient 6-call matrix, my own git diffs for guards.
- One nuance worth recording: the manifest `fingerprint` is a JSON **string** (`json.dumps(sort_keys=True)`), not a dict — the phase's own substring assertions (`"start" in fp`, `"symbols" in fp`) and the API contract operate on the string form; `lake_coverage` is present inside it. No contract drift.
- RC-02 is deliberately **not** marked fully verified against its committed ≥0.94 acceptance; the phase passes on the honest current-lake form with the acceptance deferred in `behavior_unverified` — matching the standing honesty policy (never present incomplete work as delivered).
