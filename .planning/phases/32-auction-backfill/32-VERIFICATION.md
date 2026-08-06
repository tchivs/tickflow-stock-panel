# Phase 32 Verification — 竞价历史回填 (AQ-01..06)

**Verifier:** VerifierP32 · **Date:** 2026-08-06 · **Scope:** `.planning/REQUIREMENTS.md` AQ-01..06 (Phase 32)
**Method:** Goal-backward, behavior-level — full 7-file pytest batch + code-level file:line evidence + guard-rail checks + SUMMARY cross-checks. Live-network artifacts from executor smoke runs are marked `[OBSERVED live-smoke]`; everything else is `[TEST]` (hermetic) or directly observed by this verifier.

## Verdict: **PASSED**

All 6 acceptance criteria verified against code + tests. 97 passed / 2 skipped (network-gated), 0 failures. No needs-fix items. Human items are deploy-verification only (full-universe operator run, live MCP stability over multi-hour run).

---

## 1. Test batch (executor duty 1)

```
cd backend && .venv/bin/python -m pytest tests/test_auction_backfill_honesty.py tests/test_auction_backfill.py \
  tests/test_auction_sync.py tests/test_auction_history.py tests/test_auction_probe.py \
  tests/test_xyz_provider.py tests/test_pool_backfill.py -x -q
→ 97 passed, 2 skipped in 3.62s
```

Per-file collect (99 collected): honesty **10+1sk** · backfill **23** · auction_sync **17** · auction_history **19** · auction_probe **14+1sk** · xyz_provider **5** · pool_backfill **9**.
- The 2 skips are network-gated: `test_auction_virtual_price_equals_daily_open` (honesty:359) and the probe `real_mcp` case — both gated by `RUN_NETWORK_TESTS`; determinism of the 97 passing tests does not depend on them.
- Delta vs 32-03 SUMMARY's "96 passed": `test_auction_backfill_passes_date_objects_to_provider` (ae54252, live-smoke contract fix) landed after 32-03's run — count now 97. Consistent.

## 1b. Behavioral summary (goal-backward, per AQ)

- **AQ-01 — provider + probe unlock.** A user/operator calling the auction path now gets a real source: `xyz_provider` declares `auction=True` and `get_auction` returns canonical rows (suffixed symbol, datetime, volume/amount, virtual price only when upstream provides `current`). Because probe discovery is capability-driven (`_default_sources` → `capabilities.auction`), `resolve_auction_probe()` flips to `available` with zero new wiring — verified live in sandbox `[OBSERVED live-smoke]`. The EOD `sync_and_persist_auction` path still requires the explicit `auction_sync_enabled=True` preference (default False) + probe: intentionally unblocked, not auto-enabled.
- **AQ-02 — operator-triggered backfill job.** `POST /api/kline/auction/backfill` returns a `job_id` immediately; a duplicate trigger while one is active returns `reused` (single-flight). The job runs in a dedicated executor with `job_store` lifecycle (start → progress → succeed/fail), progress queryable via the existing jobs endpoint, cancellation via the existing cancel endpoint, and a heavy-task slot shared with pool-backfill/EOD to prevent concurrent lake writes.
- **AQ-03 — honest gates.** Under a down source, preflight exception, or preflight-empty-with-coverage, the job records 0 writes and a fail-closed terminal dict with `reason`. Only dates with an existing `kline_daily` partition are in scope and only those pass the write boundary — upstream over-delivery can never create phantom dates. Per-symbol failures are recorded (`empty_response` vs exception text ≤200) and the terminal state honestly reports `failed`/`failed_symbols` while continuing the rest of the universe.
- **AQ-04 — idempotent atomic single-write-path.** Backfill and EOD share `write_auction_partitions` (window filter → existence crop → per-date merge-upsert `keep="last"` → `.tmp` atomic rename), so re-runs fill only gaps (real lake re-run stayed 496 rows `[OBSERVED live-smoke]`). `auction_unmatched_volume` is absent from upstream and stays absent — never 0-filled; the derived unmatched amount remains unavailable. Cross-check: backfilled `auction_virtual_price` equals `kline_daily.open` value-for-value on ≥3 real read-only dates (canned variant always-on).
- **AQ-05 — pacing and cancel.** The loop issues exactly 1 request per symbol, throttled by the shared token-bucket pacing at rpm 30 default (validated 1..60); explicit 429/rate-limit signals trigger exponential backoff (2 retries, 2s→4s). Cancel is cooperative (per-symbol status check) and progress is emitted per symbol. Subset runs (`symbols`, `start`, `end`) are first-class, bounding the multi-hour full-universe run.
- **AQ-06 — minute CLOSED, documented.** Minute-history backfill is formally deferred with measured evidence (xyz 1m ≈ 21 trading days, ifzq/sina trailing windows, TickFlow minute pro+ gated) recorded in `docs/features.md` with a pointer to the research doc; `sync_and_persist_minute` incremental ≤30-day sync is untouched.

## 2. AQ evidence table

| Req | Evidence (file:line) | Test(s) | Result |
|-----|----------------------|---------|--------|
| **AQ-01** | `xyz_provider.py:59` `auction=True`; `xyz_provider.py:156` `get_auction` — 1-symbol guard (ValueError, :162-167), suffix map `code→symbol` via `suffix_map` with `.SZ/.SH` (docstring + `suffix_map.get(code.split(".")[0], code)`), `time→datetime` (`_parse_iso`), `volume→auction_volume` / `money→auction_amount` / `current→auction_virtual_price` (optional-col emission, never 0-fill), `end_date=None → start==end` single-date form (:170-172) | `test_xyz_provider.py` (5: suffix mapping, single-date form, 1-symbol guard, empty payload, no-optional-col) · `test_auction_probe.py` (14+1sk: capability auto-discovery + available flip) — `auction_probe.py:86` `_default_sources` scans `capabilities.auction` (:110), `_default_fetcher` (:118) single-date call · EOD unchanged: `daily_pipeline.py:695-706` double gate (`get_auction_sync_enabled` default **False** `preferences.py:129-131` + probe via `can_sync_auction` `auction_sync.py:144`) | **PASS** |
| **AQ-02** | `services/auction_backfill.py:124` `run_auction_backfill` (mirrors pool_backfill shape: probe/preflight gates → aligned scope → serial loop → terminal dict); `api/auction_backfill.py:40` `POST /api/kline/auction/backfill` — single-flight `job_store.create` (:91, `reused` when active), heavy-slot `try_acquire_run_slot` (:97 → fail record), `_long_task_executor` (:32), `job_store.start/succeed/fail` (:104-117), `invalidate_storage_cache` (:116); registered `main.py:856` (after auction_history :854) | `test_auction_backfill_endpoint_singleflight_and_reuse` (:549), `..._parameter_validation` (:587), `..._runs_in_executor_and_succeeds` (:628), `..._router_registered_in_main` (:663), `..._guest_whitelist_untouched` (:673), `..._heavy_slot_fail_fast` (:680) | **PASS** |
| **AQ-03** | (a) probe gate `resolve_auction_probe() != available → _fail_closed("source_unavailable")` (`auction_backfill.py:157-159`); preflight one real request before loop, exception → `_fail_closed(reason≤200)` / empty-with-daily-coverage → `preflight_empty` (:168-177); (b) dates = `kline_daily/date=*` partition dirs ∩ [start,end] (:163-175) + write boundary `datetime.date().is_in(aligned_date_set)` (:230) — never phantom-writes; (c) per-symbol ledger `failed_symbols:[{symbol,reason}]` (:233-245), empty_response vs exception categories, terminal reflects partial failure | `test_auction_backfill_source_down_zero_writes` (:120), `preflight_exception_zero_writes` (:142), `preflight_empty_zero_writes` (:161), `only_writes_kline_daily_aligned_dates` (:177), `per_symbol_failure_recorded` (:207), `empty_response_recorded` (:231), `bounds` (:248) · honesty: `fail_closed_ledger_shape_and_zero_writes` (:308), `bj_stock_empty_response_recorded` (:262), `partial_failure_ledger_records_others_continue` (:219) | **PASS** |
| **AQ-04** | Single write path: `auction_sync.py:57` `write_auction_partitions` (called by EOD `sync_and_persist_auction` :154 **and** backfill loop :233) — 555..565 window predicate (:78), existence crop 4+2 cols (:82), per-date merge-upsert `unique(["symbol","datetime"], keep="last")` (:93-99), `.tmp` same-dir atomic rename (:45-53) | `test_auction_backfill_idempotent_rerun` (:284), `atomic_no_tmp_left` (:429), `0930_excluded` (:448), `unmatched_col_absent` (:469) · honesty: `origin_backfill_only_in_terminal_dict` (:244), `failed_ledger_terminal_shape` (:192 — 8-key set-equality / 9-key fail-closed) · **cross-check:** `cross_check_canned` (honesty:333, always-on: `auction_virtual_price == kline_daily.open` on 4 dates, `pytest.approx`), `test_auction_virtual_price_equals_daily_open` (:359, network-gated: real `kline_daily` read-only, ≥3 dates) | **PASS** |
| **AQ-05** | rpm default 30, endpoint validates int 1..60 (`api/auction_backfill.py:63-64`); pacing `sleep_between_batches(i, rpm)` (`rate_limits.py:76`, module-level import :36) per-symbol serial loop (:213); 429 backoff `_RETRY_ATTEMPTS=2`, `_RATE_LIMIT_MARKERS` 429/rate-limit/限速/带宽, exponential 2s→4s (:42-46, `_fetch_auction` :102-122); cooperative cancel — job `failed` checked per symbol (:215-219), `emit("done",100,"回填被取消")` break; progress emit (:212, :245-248); subset `symbols` supported (:83-89, `_MAX_SYMBOLS=6000` :37) | `test_auction_backfill_rate_limit_pacing` (:354), `cooperative_cancel` (:379), `endpoint_parameter_validation` (:587, rpm 400 cases), `one_symbol_per_request` (:302), `passes_date_objects_to_provider` (:323) | **PASS** |
| **AQ-06** (P2, doc-only) | `docs/features.md:78` — 分钟历史回填 **正式关闭 (CLOSED)**: xyz 1m ≈ 21 交易日 (实测)、ifzq/sina 仅尾随窗口、TickFlow 分钟 gated at pro+; `kline_minute` 保持增量 ≤30 日 (`sync_and_persist_minute` 零改动); pointer `research/v2.3-data-depth/AUCTION-BACKFILL.md` §4/§6 (evidence rows at :49-53: xyz 21 trading days 2026-07-07..08-04, ifzq ~320 rows trailing, sina ≤1500 trailing, TickFlow Free tier ✗) | doc structure gate (grep: 竞价历史回填=1, AUCTION-BACKFILL.md=1, 正式关闭=1, curl -X POST=2) · no code change to minute sync path in any 32 commit (git log) | **PASS** |

## 3. Guard rails (executor duty 3)

- **POOL-03 zero-execution guard**: `api/auction_backfill.py` is POST-trigger only, imports no execution-family module and no `strategy_cache` (imports: `_SYMBOL_RE` from auction_history, `invalidate_storage_cache`, `job_store`/run-slot) — locked by `test_auction_backfill_router_ast_guard` (honesty:477, AST import-scan + write-pattern scan), `test_backfill_modules_never_reference_strategy_cache` (:506), and `test_auction_history_router_stays_get_only` (:498 — only `@router.get("/history")` at `auction_history.py:71`). `test_auction_history.py` 19 tests green; `strategy_cache` untouched (negative guard in honesty suite).
- **EOD path unchanged**: `daily_pipeline.py:695-706` still double-gated (`auction_sync_enabled` default False + probe); `sync_and_persist_auction` (`auction_sync.py:154`) now routes through the extracted `write_auction_partitions` seam — single write path for EOD and backfill (AQ-04 pure move, pre-existing 15 auction_sync tests zero-line-changed per 32-01).
- **Watchlist.tsx zero-touch** (executor duty 4): `git status --short` → `staged 0, unstaged 1, untracked 0` with the sole entry `M frontend/src/pages/Watchlist.tsx`; `git log --oneline -14` (3af70c4…b3fdb37) contains **no** frontend commit — all 14 are backend/docs/planning.
- **No new runtime deps**: none of the 32 commits touch pyproject/requirements; imports reuse existing modules (`tickflow.rate_limits`, `tickflow.repository`, `pipeline_jobs`, `auction_probe/sync`).

## 4. Data reality `[OBSERVED live-smoke]` (executor duty: honesty of provenance)

Directly re-inspected by this verifier (repo-root `data/` lake, read-only):
- `data/kline_auction/`: **248** `date=*` partitions, **248** `part.parquet` (2025-07-29..2026-08-05), **496 rows total** = 2 symbols × 248 days; distinct symbols `['000001.SZ','000002.SZ']`; columns `[symbol, datetime, auction_volume, auction_amount, auction_virtual_price]` — 4 canonical + real `current` column, no `auction_unmatched_volume`, no provenance column (origin lives only in job terminal dict), `auction_virtual_price` non-null on all 496 (0-fill never happened).
- `data/kline_daily/`: 248 partitions — auction lake is date-aligned with daily K (AQ-03b satisfied on real data).
- Probe availability flip (`resolve_auction_probe() → {status:'available', source:'xyz', window:'09:15-09:25'}`) recorded in 32-01 SUMMARY as a live MCP smoke at 2026-08-06T16:52:29Z; cancel + idempotent re-run (still 496 rows) recorded in 32-02 SUMMARY. These were not re-executed in this verification pass (network-gated tests stayed skipped) — see human_items.

## 5. SUMMARY cross-checks (executor duty 5)

- **Terminal dict key sets (W-5)**: code matches claim — success path 8 keys `auction_backfill.py:255-261`; `_fail_closed` 9 keys (+`reason`) `:52-63`; tests pin with set-equality (honesty:192/308).
- **`_SYMBOL_RE` usage**: `api/auction_backfill.py:25` imports from `auction_history.py:31` (`^\d{6}\.(SH|SZ|BJ)$`), applied via `fullmatch` with 400 on violation; `_MAX_SYMBOLS=6000` bound present.
- **`main.py:856` registration**: `app.include_router(auction_backfill.router)` confirmed at line 856, immediately after `auction_history` (:854), import at :22.
- **job_store/rate-limit APIs**: `pipeline_jobs.py` has `create/start/succeed/fail/progress/get/reap_stale` (:99-227) + `try_acquire_run_slot/release_run_slot` (:314-319); `rate_limits.sleep_between_batches` at :76; `invalidate_storage_cache` at `api/data.py:81`. All claims grounded.

## 6. Human items (deploy-verified — not assertable in sandbox)

1. **Full-universe operator run** (~5537 symbols, 3-5.5h @ rpm≈30-37, per features.md ops note): sandbox verified only the 2-symbol live smoke (496 rows) + hermetic subset runs. Multi-hour run, real-world 429 cadence, and job-store progress polling over hours remain deploy-verified.
2. **Live MCP stability**: probe resolved `available` once (16:52Z smoke); sustained availability of `http://8.138.149.215:7898/mcp` over a full run and real BJ `empty_response` behavior on upstream are deploy-verified. Network-gated tests were not re-run in this pass.
3. **EOD unlock is preference-gated by design**: live `sync_and_persist_auction` runs only when operator sets `auction_sync_enabled=True` (default False) — flipping and observing the 09:15-09:25 EOD fill is a deploy action, not a Phase-32 code gap.
4. **R3 probe latency**: each `resolve_auction_probe()` does 1 live HTTP (1.6s nominal / 8s timeout); short-TTL cache is documented as deferred (features.md R3 note) — acceptable per plan, but a known operational cost on `/api/kline/auction/history` and EOD gate.

## 7. Honesty notes

- All PASS evidence above is hermetic `[TEST]` unless tagged `[OBSERVED live-smoke]`; the live-lake facts (§4) were directly re-inspected by this verifier, not taken on faith from SUMMARY text.
- The two skipped tests are network-gated and their deterministic cores (canned cross-check, mock-probe determinism) are asserted always-on elsewhere — no coverage hole in the hermetic set.
- `origin=backfill` never reaches the lake (no provenance column, by design); 32-03's "96 passed" vs our "97 passed" delta is the date-object contract test landed after that SUMMARY — recorded, not a discrepancy.
