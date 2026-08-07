# 36-PLAN-CHECK — Plan Quality Gate

**Checked**: 2026-08-07 (PlanCheckerP36, independent read of RESEARCH/PATTERNS/36-01/02/03 + live code)
**Scope**: 36-01/02/03-PLAN.md against REQUIREMENTS.md FA-01..06, ROADMAP.md Phase 36 success criteria, and the codebase anchors (backend/app, backend/tests, backend/scripts).
**Method**: every anchor re-read in code; no file writes except this document; no commit.

## Verdict

**EXECUTABLE** — 0 blockers, 5 warnings (1 HIGH / 2 MEDIUM / 1 LOW-MEDIUM / 1 LOW). All six FA-01..06 map to concrete tasks with files+commands+acceptance; sequencing is sound (36-01 lands FA-01/02/03 + the full CLI as detached carrier, 36-02/03 parallel after, detached 3.5-5.5h run launched immediately after 36-01's batch is green). The HIGH warning (36-02 top-up acceptance numbers) does not block execution — the runs themselves behave correctly and honestly — but the verification checklist as written would fail against reality and must be corrected before the verifier reads the top-up ledger.

## 1. Goal-backward coverage (FA-01..06 → tasks)

| Req | REQUIREMENTS.md text | Tasks | Verdict |
|---|---|---|---|
| FA-01 | `create(timeout_s=...)` persists; `reap_stale` honors `j.get("timeout_s", STALE_JOB_TIMEOUT_S)`; API passes 21600; >600s job survives (regression) | 36-01 T1 (`create` sig+key), T2 (`j.get` in reap), T3 (API `create(timeout_s=21600)`), T8 tests `timeout`/`reap` | Complete |
| FA-02 | `only_missing=True` pre-scan over aligned dates (GROUP BY symbol), fully-covered skipped, partial re-fetched, API body accepts, merge-upsert preserved | 36-01 T4 (`_covered_symbols`), T5 (service filter + empty→8-key success), T6 (API param + 400), T8 tests `only_missing` | Complete |
| FA-03 | CLI `--symbols\|--all --start --end --rpm --only-missing`; job_id=None → no job_store; per-symbol stdout progress; terminal dict + `failed_symbols` → JSON; detached carrier | 36-01 T7 (full CLI, not skeleton, + launch command), T8 tests `cli` (incl. AST no-job_store gate) | Complete |
| FA-04 | Detached full run 5537×248d; backfilled ≥5200; rows ≈1,290,592; 248 partitions; no `.tmp`; cross-check ≥3 dates × ≥3 symbols; top-up stable | 36-02 T1 launch runbook, T2 monitoring, T3 top-up, T4 verifier script, T6 checklist | Complete (numbers correct except top-up `requested` semantics — see W1) |
| FA-05 | BJ 333 `empty_response` ledger; ≤94.0% framing; 5 formats documented | 36-02 T5 stance doc, T6 items 1-2/6; 36-03 T3 item 6 folds into features.md | Complete |
| FA-06 (P2) | EOD re-write on covered symbols = idempotent no-op crop; cross-process discipline documented | 36-03 T1 (3-level EOD test), T2 (features.md discipline note) | Complete |

Nothing missing. ROADMAP.md:71-90 success criteria 1-6 map 1:1 to the same tasks.

## 2. Sequencing

- **36-01 first, then 36-02/03 in parallel**: correct — 36-02's runbook and 36-03's SUMMARY consume 36-01's code/tests; 36-02 (runbook/verify/stance) and 36-03 (EOD test exec, features.md, SUMMARY) are independent of each other. Ownership split on docs is explicit (36-02 writes FA-05-BJ-STANCE.md, only 36-03 touches `docs/features.md`) — no concurrent doc edits.
- **Detached run can start immediately after 36-01**: yes. 36-01 exit gate (T1-T7 implemented, T8 batch green) → orchestrator launches per 36-01 T7 / 36-02 T1. The launch command is stated in both plans identically (`hub op=start name=auction-backfill application=.venv/bin/python args=["scripts/auction_backfill.py","--all","--rpm","30",...] cwd=backend detached=true ready={"log":"\[progress\]"}` + nohup equivalent). First run **without** `--only-missing` → acceptance numbers exact (requested=5537).
- **Verifier can monitor mid-run**: yes — 36-02 T2 (progress lines `i/5537 (成功 X, 失败 Y)` match the real emit format at auction_backfill.py:245-249; stall detection; `--out` written only at completion), T3 top-up, T4 verifier (read-only), T6 final checklist.
- Trivial note: 36-01 T8's first batch command runs the whole new test file, which already includes the `eod` test (defined there, executed again by 36-03) — harmless redundancy, no conflict.
- **36-03 T4 SUMMARY gating**: T4 is explicitly gated on 36-02 run evidence (ledger + verify output) and has a no-placeholder rule — consistent with "36-03 runs in parallel with 36-02" (T1-T3 parallel; T4 waits).

## 3. Blocker hunt (all cleared)

| Hunt item | Finding | Evidence |
|---|---|---|
| 600s reap × CLI path | CLI `job_id=None` → the cooperative-cancel branch (`if job_id is not None:`) is never entered, and no job_store import/reap happens in the CLI script itself. T7's AST gate (`test_full_backfill_cli_no_job_store_import`) locks it. | auction_backfill.py:216-220; 36-01 T7/T8 |
| 600s reap × API path | Real trap confirmed: `STALE_JOB_TIMEOUT_S=600` (pipeline_jobs.py:29), `reap_stale` compares the param directly (pipeline_jobs.py:252); API calls `job_store.reap_stale()` at :89 and the polling endpoints at api/pipeline.py:45,132,173. A >10-min API backfill would be reaped mid-run → FA-01 fix is genuinely required, and T1/T2 are the correct minimal shape (`create(timeout_s=...)` key persisted; `j.get("timeout_s", timeout_s)` inside the locked section; `succeed()`/`fail()` already persist the whole dict via `_write_file` so the key survives disk round-trip for free — verified pipeline_jobs.py:143-155/165-186). | pipeline_jobs.py:29,227-255; api/auction_backfill.py:89-91; api/pipeline.py:45,132,173 |
| `_MAX_SYMBOLS` | 6000 > 5537 universe → `--all` never needs the API at all (CLI passes symbols=None → `_lake_distinct_symbols`), and a hypothetical API call with all 5537 fits. | api/auction_backfill.py:37; service `symbols=None` branch :159-160 |
| Single-flight | CLI bypasses `job_store.create` entirely → no reuse/reap interaction. Server path unchanged (pending∨running dedup preserved). | api/auction_backfill.py:91-94 |
| Run slot | `try_acquire_run_slot()` lives in the API executor task only (api/auction_backfill.py:98-101); the service never acquires it → the CLI (separate process, job_id=None) takes no slot. Correct decision, consistent with the plan. | api/auction_backfill.py:98-101,111-116; auction_backfill.py:124-131 |
| EOD window concurrency | Seam is read-modify-write + atomic rename, last-rename-wins (auction_sync.py:49-57,103-111); in-process slot covers server-side only. Discipline (launch outside EOD window, no run_all during backfill) is the only cross-process protection — documented honestly, not claimed fixed. `auction_sync_enabled` default False keeps EOD off unless explicitly enabled. | auction_sync.py:49-111; daily_pipeline.py:699-708; preferences.py:129-131; 36-02 T1 step 3; 36-03 T2 |
| 429/retry | `_fetch_auction` 2 retries with 2s→4s backoff (auction_backfill.py:102-121) — unchanged; pacing shared via `rate_limits._reserve_slot` (rate_limits.py:31-52) — CLI reuses the same module-level throttle. | auction_backfill.py:102-121; rate_limits.py:31-52 |

## 4. Test determinism

- **Hermetic**: tmp_path lakes (`_make_env`-style kline_daily/date=* partitions), fake provider with per-symbol rows/exc injection, `_patch_pacing` neutralizes `_reserve_slot` (no real sleep), probe pinned to a fixed verdict. All module-object monkeypatch (source + consumer modules) — matches the honesty suite pattern (test_auction_backfill_honesty.py:131-163). No live network except the RUN_NETWORK_TESTS-gated test (:359-378) which stays skipped by default.
- **No flaky timing**: reap tests backdate `started_at` by a fixed `datetime.now() - timedelta(seconds=601)` offset; `reap_stale`'s elapsed computation is monotonic-deterministic vs the backdated value (pipeline_jobs.py:239-252). API test uses `_wait_job_terminal`/`_wait_slot_free` polling helpers (test_auction_backfill.py:517-547).
- **Real-repo construction in tests**: the CLI hermetic test builds `KlineRepository(DataStore(tmp))` over a tmp dir with only kline_daily — safe because view registration try/excepts missing datasets ("view registration skipped (no parquet yet)", repository.py:191-198). Verified feasible.
- The plan's `only_missing` tests replicate `_FakeDb` — but `_FakeDb.execute()` returns single-element `(symbol,)` tuples (honesty :100-110), so `_covered_symbols`' DuckDB branch (`int(r[1])`) raises IndexError and **every coverage test silently exercises the polars fallback, never the DuckDB view** (see W3).

## 5. Contract risk

- **Terminal dict freeze**: success 8 keys = `{requested, backfilled_symbols, rows, dates, failed, failed_symbols, origin, rpm}` (services/auction_backfill.py:253-261, matches `_SUCCESS_KEYS` in honesty tests :29-34); fail-closed +`reason` = 9 keys (`_fail_closed` :44-52). No new keys anywhere in the plans — skip info goes through the progress emit only. Set-equality tests guard it.
- **Backward compat**: `only_missing: bool = False` added keyword-only after `rpm` (service) and as a new optional body field (API). All existing callers pass kwargs; the full existing batch re-run in 36-01 T8 proves byte-identical default behavior.
- **`timeout_s` optional key**: absent → `j.get("timeout_s", timeout_s)` falls back to the 600 default; old records and `/run`/pool-backfill jobs unaffected; `reap_stale`'s signature and all 3 call sites unchanged.
- **CLI exit codes**: 0 = no `reason` key (success or honest partial incl. BJ), 1 = fail-closed `reason` or uncaught exception; `--rpm` validation → `parser.error` (exit 2). Mirrors auction_backtest.py's `return 0 if status in ("ok","reused") else 1` + top-level `raise SystemExit(main())` (auction_backtest.py:188-230).
- **Verify script read-only**: 36-02 T4 prints six lake-derived facts; only reads via DuckDB views + globs; spot-checked against the pre-run lake (2 symbols/248 partitions/496 rows) before the run makes it interesting.

## 6. Line-level anchor cross-check (read in code, 2026-08-07)

All plan/RESEARCH/PATTERNS anchors verified accurate except the corrections below:

| Anchor | Claimed | Actual | Status |
|---|---|---|---|
| pipeline_jobs.py:29 | `STALE_JOB_TIMEOUT_S = 600` | :29 | ✓ |
| pipeline_jobs.py:99-113 | `create()` | def :101, dict :105-119 | ✓ close |
| pipeline_jobs.py:227-255 | `reap_stale(timeout_s=...)` | def :227, compare :252 | ✓ |
| api/pipeline.py:45,132,173 | reap call sites | :45/:132/:173 (file is **api**/pipeline.py) | ✓ |
| auction_backfill.py:67-88 | `_lake_distinct_symbols` | :67-88 | ✓ |
| auction_backfill.py:102-121 | 429 backoff | `_fetch_auction` :102-121 | ✓ |
| auction_backfill.py:124-251 | `run_auction_backfill` | :124-261 | ✓ |
| auction_backfill.py:215-219 | cancel check | :216-220 | ✓ |
| auction_backfill.py:222-235 | empty-vs-宕机 | :223-231 | ✓ |
| auction_backfill.py:250-258 | success terminal dict | services file :253-261 (8 keys) | ✓ (note: this is the **service** file, not api/auction_backfill.py) |
| api/auction_backfill.py:37 | `_MAX_SYMBOLS = 6000` | :37 | ✓ |
| api/auction_backfill.py:62-83 | params/validation | :61-83 | ✓ |
| api/auction_backfill.py:75 | rpm 1..60 | :75 | ✓ |
| api/auction_backfill.py:89 | reap call | :89 | ✓ |
| api/auction_backfill.py:97-119 | slot/executor/invalidate | :98-121 | ✓ |
| auction_sync.py:57-112 | write seam | :58-112 | ✓ |
| auction_sync.py:99-104 | merge-upsert | `unique(subset=["symbol","datetime"], keep="last")` :103-106 | ✓ |
| **auction_sync.py:137-141 (PATTERNS row 6)** | "幂等 crop" | crop (keep columns) is :82-86, window filter :63-75, merge-upsert :99-106; :137-141 is inside `_first_auction_provider` | **STALE — see W5** |
| daily_pipeline.py:699-708 | EOD double gate | :699-708 | ✓ |
| preferences.py:129-131 | default False | :129-131 | ✓ |
| repository.py:162-164 (36-02 T4) | kline_daily view | :146-147 | **off by ~16 lines — W5** |
| repository.py:169-171 | kline_auction view | :168-170 | ✓ |
| rate_limits.py:31-56 | `_reserve_slot` | :31-52 | ✓ |
| honesty :131/:147/:155/:168 | `_patch_probe`/`_patch_provider`/`_patch_pacing`/`_run_job` | :131/:147/:155/:168 | ✓ |
| honesty :262 | BJ empty_response test | :262-278 | ✓ |
| honesty :333 | canned cross-check | :335 (test_auction_backfill_cross_check_canned) | ✓ close |
| honesty :359 | network-gate | :361 (RUN_NETWORK_TESTS skip) | ✓ close |
| test_auction_backfill.py:506-514 | `_make_auction_app` | :505-514 | ✓ |
| backtest CLI conventions | argparse/`DATA_DIR` env/exit 0·1/`main(argv=None)`/`_SCRIPT_DIR` inserts/`SystemExit` | auction_backtest.py:14-26,188-230 | ✓ |
| pipeline_jobs.py:39-40 | `JobStore(max_jobs=50, store_dir=...)` | :39-40 — positional first arg is `max_jobs` | **matters for W2** |

## Warnings

### W1 — HIGH — 36-02 top-up acceptance numbers contradict the mechanics (BJ 333 can never be "covered")
- **Location**: `36-02-PLAN.md` T3 step 1 (expected log `覆盖扫描: 跳过 5537 已全覆盖, 待回填 0` → `requested=0`), T3 step 2 (`both must report requested == 0 / backfilled_symbols == 0`), T6 checklist item 5 (`both requested=0`); mirrors in 36-01 T5's acceptance framing (`requested == 0` when "all symbols fully covered").
- **Problem**: after the first full run, kline_auction contains only SZ/SH (~5204). BJ 333 symbols are never covered (they have zero lake rows and always fetch empty — honesty test :262-278). `--all --only-missing` therefore filters the requested list to the 333 BJ symbols every time: `覆盖扫描: 跳过 5204 已全覆盖, 待回填 333` → terminal dict `requested=333, backfilled=0, failed=333` (all `{symbol, reason:"empty_response"}`), `rows=0`, exit 0. `requested == 0` is unreachable for `--all --only-missing`, so the stability gate as written fails against reality and the verifier would misread a healthy top-up as an anomaly. The RESEARCH anchor already has it right: "连续两次 **0 新增**" (RESEARCH.md 验收口径).
- **Fix**: change the criterion to `backfilled_symbols == 0 && rows == 0` (0 新增) with `failed == 333` all-BJ as *expected noise*, not failure: T3 step 1 expected log → `跳过 5204 已全覆盖, 待回填 333 (BJ)` and dict `requested=333/backfilled=0/failed=333`; T3 step 2 and T6 item 5 → `both backfilled_symbols == 0`; 36-03 SUMMARY item 4 ("0 new") is already correct. Optionally add the honest note that BJ re-request per top-up is intended (idempotent, ~6 min, no new rows).

### W2 — MEDIUM — 36-01 T8: `JobStore(tmp_dir)` is the wrong constructor call
- **Location**: `36-01-PLAN.md` T8, `test_full_backfill_job_store_timeout_s_persisted` and the three `reap` tests ("`JobStore(tmp_dir)`").
- **Problem**: signature is `JobStore(max_jobs: int = 50, store_dir: Path = _STORE_DIR)` (pipeline_jobs.py:39-40). `JobStore(tmp_dir)` binds the path to `max_jobs` and keeps the **real** `settings.data_dir / "job_store"` — non-hermetic (writes into the sandbox's real store dir) and the disk-roundtrip assertion (`succeed()` → on-disk JSON has `timeout_s`) would read/write the wrong location.
- **Fix**: `JobStore(store_dir=tmp_dir)` in all four tests; assert the on-disk file via `store_dir / f"{job_id}.json"`.

### W3 — MEDIUM — `_covered_symbols` DuckDB happy path is untestable with the replicated `_FakeDb`
- **Location**: `36-01-PLAN.md` T4 acceptance ("unit test covers the happy path via the DuckDB view on the tmp lake") + T8 (replicate `_make_env`-style helpers).
- **Problem**: the honesty suite's `_FakeDb.execute()` returns `[(s,) for s in symbols]` (test_auction_backfill_honesty.py:100-110) — 1-tuples with no COUNT. `_covered_symbols`' DuckDB branch reads `r[1]` → IndexError → caught → **always** falls back to the polars scan. Every `only_missing` test would pass through the fallback, and the DuckDB branch stays dead under test — the opposite of the stated acceptance.
- **Fix**: make the replicated fake db shape-aware: when the SQL contains `COUNT(*)`, return `(symbol, count)` rows (counts hand-crafted per test, e.g. full/partial/none), otherwise the DISTINCT shape. Then the DuckDB branch is genuinely exercised. (The polars fallback itself is sound: `pl.scan_parquet(str(data_dir/"kline_auction"/"**"/"*.parquet"))` + `datetime.date().is_in(aligned_date_set)` mirrors the production write-boundary call at auction_backfill.py:231, and empty lake → `scan_parquet` raises → caught → `set()` ✓.)

### W4 — LOW-MEDIUM — 36-01 T5: `aligned_date_set` must be hoisted; skip-emit ordering vs hub `ready`
- **Location**: `36-01-PLAN.md` T5 (insert coverage scan "after provider resolution, before preflight").
- **Problem (a)**: `aligned_date_set = {date.fromisoformat(d) for d in aligned_dates}` is computed *after* the preflight today (auction_backfill.py:214-215); T5 calls `_covered_symbols(repo, data_dir, aligned_date_set, eff_start, eff_end)` before the preflight → the implementer must move that one-liner above the `only_missing` block or the run hits a `NameError`. Mechanical, but unstated.
- **Problem (b)**: the skip emit is listed after the "symbols became empty → return" step. If a fully-covered run returns without any `emit`, the CLI prints no `[progress]` line and `hub op=start ready={"log":"\[progress\]"}` never matches for top-up launches (36-01 T7 / 36-02 T3 both launch top-ups via hub). First run is unaffected (it always emits `回填 N 个标的`).
- **Fix**: hoist `aligned_date_set`; emit the skip line (`覆盖扫描: 跳过 … 待回填 …`) **before** the empty-return so every run emits at least one `[progress]` line. Note W1's numbers apply to that line (5204/333, not 5537/0).

### W5 — LOW — Stale anchors (documentation only)
- PATTERNS.md row 6 "幂等 crop (auction_sync.py:137-141)": the idempotent crop is the keep-columns select at auction_sync.py:82-86; merge-upsert :99-106; window filter :63-75; :137-141 is inside `_first_auction_provider`. No behavioral impact (36-03 T4 item 5 already anticipates PATTERNS anchor drift).
- 36-02 T4 cites "kline_daily :162-164" for the view; actual `CREATE OR REPLACE VIEW kline_daily` is repository.py:146-147 (kline_auction :168-170 matches).
- PATTERNS row 7 cites "auction_backfill.py:250-258" for the terminal dict — the 8-key dict is in the **service** file (services/auction_backfill.py:253-261); the api file is only 125 lines. Cosmetic.

## Per-FA coverage table

| Req | Criterion (REQUIREMENTS.md) | Where planned | Verified by | Status |
|---|---|---|---|---|
| FA-01 | `create(timeout_s)` persists; `reap_stale` honors per-job key; API 21600; >600s regression | 36-01 T1-T3 | T8 `timeout`/`reap` tests + existing batch | ✓ (code anchors verified) |
| FA-02 | only-missing pre-scan; skip covered; re-fetch partial; API body; idempotent | 36-01 T4-T6 | T8 `only_missing` tests | ✓ (with W3/W4 notes) |
| FA-03 | CLI full surface; job_id=None; stdout progress; JSON ledger; detached carrier | 36-01 T7 | T8 `cli` tests (AST gate, help, hermetic JSON) | ✓ (conventions verified against auction_backtest.py) |
| FA-04 | detached full run; ≥5200 backfilled; ≈1,290,592 rows; 248 partitions; no .tmp; cross-check; top-up stable | 36-02 T1-T4, T6 | 36-02 checklist + verifier script + ledger evidence | ✓ (with W1 top-up gate fix) |
| FA-05 | 333 BJ `empty_response` ledger; ≤94.0% framing; 5 formats | 36-02 T5, T6 | FA-05-BJ-STANCE.md + ledger facts + existing BJ test | ✓ |
| FA-06 (P2) | EOD rewrite = no-op crop; discipline documented | 36-03 T1, T2 | `test_full_backfill_eod_interplay_rewrite_idempotent` (3 levels) + features.md note | ✓ |

## Conclusion

Plans are executable as written: the code delta is minimal and anchored to real code (all line references checked), the test strategy is hermetic and deterministic, the contract freeze (terminal dict 8/9 keys, backward-compatible signatures, optional `timeout_s` key) is respected, and the runbook/verification path is read-only and evidence-based. Fix W1 before the verifier runs 36-02 T6 (top-up stability gate), and apply W2/W3 while writing 36-01 T8's test file. W4 is a mechanical implementation note; W5 is doc drift only.
