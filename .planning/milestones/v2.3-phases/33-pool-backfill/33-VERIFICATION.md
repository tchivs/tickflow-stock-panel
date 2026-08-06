---
phase: 33-pool-backfill
verified: 2026-08-06T17:53:55Z
status: passed
score: 4/4 requirements verified (PB-01..04)
behavior_unverified: 0
overrides_applied: 0
human_verification: 2 deploy-verified items (full-248 operator run — now 6-7 min measured, still a deploy action; real trading-day EOD/premarket 09:26 interplay) — sandbox cannot assert; labeled deploy-verified per standing policy
---

# Phase 33 Verification — 股池回填 (PB-01..04)

**Verifier:** VerifierP33 · **Date:** 2026-08-06 · **Scope:** `.planning/REQUIREMENTS.md` PB-01..04 (Phase 33)
**Method:** Goal-backward, behavior-level — 5-file pytest batch + code-level file:line evidence + POOL-03 guard checks + Watchlist proof + SUMMARY cross-checks. Sandbox lake facts were directly re-inspected by this verifier `[OBSERVED]`; everything else is `[TEST]` (hermetic) or read directly from code.

## Verdict: **PASSED**

All 4 acceptance criteria verified against code + tests + live sandbox lake. 96 passed / 0 failed in 2.85s. No needs-fix items. Human items are deploy-verification only (full-248 operator run; real trading-day EOD/premarket interplay).

---

## 1. Test batch (executor duty 1)

```
cd backend && .venv/bin/python -m pytest tests/test_pool_backfill.py tests/test_pool_hub.py \
  tests/test_concept_history.py tests/test_premarket_pool.py tests/test_guest_masking.py -x -q
→ 96 passed, 2 warnings in 2.85s
```

Per-file collect (96 collected): pool_backfill **13** · pool_hub **36** · concept_history **16** · premarket_pool **14** · guest_masking **17**.
- The 2 warnings are starlette TestClient cookie DeprecationWarnings (pre-existing, non-failing).
- 7 phase-33 additions confirmed present: `test_backfill_endpoint_subset_bounds_integration` (pool_backfill:424), `test_backfill_endpoint_never_touches_strategy_cache` (:482), `test_backfill_endpoint_idempotent_rerun_subset` (:519), `test_backfill_auction_sparse_lake_honest_rows` (:680), `test_pool_history_renders_backfilled_snapshot` (pool_hub:841), `test_pool_history_backfilled_date_concept_fallback` (concept_history:667), `test_pool_backfill_never_creates_premarket_root` (premarket_pool:637). No pre-existing test was modified (33-01/02/03 diff claims of pure-append confirmed by executor summaries + this verifier's own test-name scan).

## 1b. Behavioral summary (goal-backward, per PB)

- **PB-01 — sandbox subset backfill end to end.** The existing `POST /api/pipeline/backfill` now runs the enriched-gap backfill: 8 real partitions (2026-07-27..08-05) landed with `snapshot_origin=backfill` provenance in each `part.json` payload `[OBSERVED]`; `strategy_cache` untouched (real md5 stable at `844886136b…` across the executor's run and this verifier's re-check + hermetic byte-identical tests); `/pool/history?as_of=2026-07-27` renders the backfilled date (n=27, origin passthrough); re-run idempotent by gap-set diff (`requested:0` on the executor's second run; three-run subset test locks `5 → requested:2 → requested:0`).
- **PB-02 — full-248 runbook, deploy-gated.** `docs/features.md:81-116` documents trigger/cancel/polling, single-flight, heavy-slot mutual exclusion, `max_days` 1..500 (500 ≥ 248, single call, no chunking), post-run verification commands, and measured anchors replacing the old INFERENCE estimates: 13 s/8 d ≈ 6-7 min full (vs 20-120 min [INFERENCE]), ~2.6 MiB/d ≈ 650 MiB full (vs 79-693 MiB [INFERENCE] interval). Mechanism verified on the 8-day sandbox artifact.
- **PB-03 — PIT interplay, no forgery.** `/pool/history` passthroughs `snapshot_origin` (`pool_hub.py:329-331`, `snap.get("snapshot_origin", "eod")`); concept attribution on backfilled dates resolves via `_build_concept_map(data_dir, as_of)` — `ext_history` partition hit → `as_of_snapshot` + `concept_effective_date`/`concept_captured_at`; missing `ext_history` → honest `current_snapshot` fallback with **no** PIT timestamp keys (keys added only when `attribution == "as_of_snapshot"`, `pool_hub.py:240-243`). Positive control flips to `as_of_snapshot` in the same test. `ext_history` absent in sandbox `[OBSERVED]` — real 3-day curl sampling showed `current_snapshot` + no effective/captured keys on all three.
- **PB-04 — premarket honest gap documented + structurally locked.** `docs/features.md:109` (诚实缺口 bullet) states the only creator is the 09:26 `premarket_pool_preview` job under dual gates (scheduler non-`fixture_mode` + live 09:15-09:25 feed; empty pre-market frame → honest `available:false`, never persisted); sandbox has no path producing the directory (absent `[OBSERVED]`); backfill/manual run_all never touch the premarket root — locked by `test_pool_backfill_never_creates_premarket_root` (structural: `(tmp_path/"premarket_results").exists() is False` after a service-level backfill).

## 2. PB evidence table

| Req | Evidence (file:line) | Test(s) | Result |
|-----|----------------------|---------|--------|
| **PB-01** | Chain: `api/pipeline.py:89` `POST /api/pipeline/backfill` — param validation (date regex + real date + start≤end + `max_days` int 1..500, :96-123), single-flight `job_store.create` (`reused` when active, :139-141), heavy-slot `try_acquire_run_slot` fail-fast (:146-149), `_long_task_executor` + `job_store.start/succeed/fail` (:155-165); `services/pool_backfill.py:30` `run_pool_backfill` — gap set = `list_backfill_gaps` (enriched − snapshots with part.json, :58), start/end/max_days bounds (:59-63), empty→`requested:0` (:66-73), per-day `run_all_with_hits` + `persist_point_snapshot(..., origin="backfill")` (:85-91), cooperative cancel via job status (:76-80), failed-dates ledger (:92-96), terminal 6 keys `{requested, backfilled, failed, failed_dates, origin:"backfill"}` (:114-120); provenance `pool_snapshot.py:52` payload `snapshot_type:"point"`/`schema_version:1`/`snapshot_origin` + origin validation `{eod,backfill,manual}` (:67-68), atomic tmp+`os.replace` (:57-62); **D2**: `pool_backfill.py:96` comment + no `strategy_cache` import anywhere in the chain (grep of pipeline.py/pool_backfill.py/pool_snapshot.py → docstring refs only) | `test_backfill_endpoint_subset_bounds_integration` (:424) · `test_backfill_endpoint_never_touches_strategy_cache` (:482) · `test_backfill_endpoint_idempotent_rerun_subset` (:519) · `test_backfill_auction_sparse_lake_honest_rows` (:680) · `test_pool_history_renders_backfilled_snapshot` (pool_hub:841) | **PASS** |
| **PB-02** (P1, deploy-gated doc) | `docs/features.md:81` `### 🗄️ 股池回填 (Pool Backfill)` — `max_days` 500 ≥ 248 (248 交易日 2025-07-29..2026-08-05) single-call (:86), trigger/cancel/polling (:88-94), 跑后验证 step-7 commands (`ls \| wc -l`==248 / `jq .snapshot_origin` / `/pool/dates` backfill_needed==0 / `/pool/history` render, :96-99), provenance-in-partition note (:101), preflight (:103), **measured anchors** (:105): 13 s/8 d (~1.6 s/d) → 6-7 min full, ~2.6 MiB/d → ~650 MiB full, both replacing earlier [INFERENCE] estimates; doc-structure grep gates all pass (`股池回填`×1, `max_days`, `backfill_needed`×3, `premarket_results` 诚实缺口 @:109, `09:26`×4, `fail_closed`×3) | mechanism re-verified on real 8-day artifact: `ls`==8, `jq .snapshot_origin`==backfill, `/pool/dates` count=8 / backfill_needed=240 (this verifier's own re-inspection, §6) — full-248 run itself is deploy-verified | **PASS** |
| **PB-03** (P2) | `/pool/history` = `build_pool_hub_snapshot` (`pool_hub.py:295-332`): missing snapshot → honest `available:false` empty state (:302-313); present → `_project_hub` + `snapshot_origin` passthrough `snap.get("snapshot_origin","eod")` (:329-331); `updated_at` = snapshot `computed_at`; concept via `_build_concept_map(data_dir, as_of)` (:44-123): `ext_history/gn_ths/date=D` partition rows non-empty → `as_of_snapshot` + effective_date/captured_at from manifest (:49-85); else fallback current-snapshot logic → `current_snapshot`/`unavailable` with `(None, None)` (:87-116); `_project_hub` appends `concept_effective_date`/`concept_captured_at` **only** when `attribution == "as_of_snapshot"` (:240-243) — no forgery (CONCEPT-05); W-1/W-2 applied: `available` key is empty-state-only, `snapshot_type`/`schema_version` live in partition payload not the response | `test_pool_history_renders_backfilled_snapshot` (pool_hub:841 — present-state no `available` key, origin passthrough, `sum(total)==5`, `updated_at==computed_at`, concept `current_snapshot` + no timestamp keys) · `test_pool_history_backfilled_date_concept_fallback` (concept_history:667 — fallback key-set lock + positive control flips to `as_of_snapshot` with `concept_effective_date==d` + origin-independence: `origin="eod"` behaves identically) | **PASS** |
| **PB-04** | `docs/features.md:109` 诚实缺口 bullet — sole creator = 09:26 `premarket_pool_preview` job; dual gates (scheduler non-`fixture_mode` 部署门禁; live 09:15-09:25 feed 数据门禁; pre-market empty frame → honest `available:false` not persisted); 沙箱无任何路径产生该目录; backfill/run_all 只写 `screener_results/` never premarket root; 前端空态诚实 (200 `available:false`); 绝不伪造; structural test locks isolation | `test_pool_backfill_never_creates_premarket_root` (premarket_pool:637 — after service-level `run_pool_backfill` subset, `(tmp_path/"premarket_results").exists() is False`, snapshot side normal `origin=="backfill"`, 6-key exact terminal set) · sandbox `premarket_results` absent `[OBSERVED]` | **PASS** |

## 3. Guard rails (POOL-03 E1-E6, executor duty 3)

All green in the batch; the pool-side guard suite lives in `test_pool_hub.py` (36 passed):

- **E1 — no-execution imports**: `test_pool_hub_no_execution_imports` (:951) — AST import scan over pool_hub.py / pool.py / pool_snapshot.py.
- **E2 — writes only screener**: `test_pool_snapshot_writes_only_screener_results` (:976) — all write paths derive from `_SNAPSHOT_ROOT` == `screener_results`.
- **E3 — never runtime cache**: `test_pool_snapshot_never_writes_runtime_cache` (:1005) — pool_snapshot imports no `strategy_cache`; independently verified by this verifier via grep (pool_backfill.py / pool_snapshot.py / api/pipeline.py / api/pool.py contain only docstring mentions, zero imports); behavioral byte-identical locked at service level (`test_backfill_never_touches_strategy_cache`, pool_backfill:113) and endpoint level (:482).
- **E4 — GET-only**: `test_pool_api_is_get_only` (:961) — pool.py has only `@router.get`; the mutating backfill endpoint deliberately lives in `/api/pipeline` (`pipeline.py:89`), not `/api/pool/*`.
- **E5 — no compute trigger**: `test_pool_api_no_compute_trigger` (:1016) — pool.py forbids `run_all`/`run_preset`/`write_cache`/`persist_point_snapshot` tokens.
- **E6 — vocabulary**: `test_hub_response_has_no_execution_vocabulary` (:1055) — response keys contain no orders/execution/broker/deals vocabulary.
- Guest masking: `test_guest_masking.py` 17 passed.

`strategy_cache` module itself untouched: no phase-33 commit touches it (git log below; the only working-tree modification is the user's Watchlist.tsx).

## 4. Watchlist (executor duty 4)

- `git status --short` → `staged 0, unstaged 1, untracked 0`, sole entry `M frontend/src/pages/Watchlist.tsx` (user's unstaged change).
- `git log --oneline -8` (29b1127…10b892c): **no frontend commit** — all 8 are docs/test/planning (`docs(33-03)` ×2, `docs(phase-33)` test+summary ×3, `docs(phase-33) plan-check/plans` ×2, `test(phase-33)` ×1 pair). Consistent with 33-01/02/03 claims of explicit single-file `git add`.

## 5. SUMMARY cross-checks (executor duty 5)

- **partition payload keys (point/1)**: `load_point_snapshot` reads the full payload written by `persist_point_snapshot` — this verifier jq'd the real `data/screener_results/date=2026-07-27/part.json`: keys `{as_of, computed_at, results, schema_version, snapshot_origin, snapshot_type, strategy_version}` with `snapshot_type=="point"`, `schema_version==1`, `snapshot_origin=="backfill"`, `strategy_version=="7affa346e5e586c5"` — matches 33-01's provenance table and 33-02's W-2 mirror claim exactly.
- **`/pool/history` response field set**: `api/pool.py:101-123` — `build_pool_hub_snapshot` → `{as_of, updated_at, strategies, resonance_count, concept_attribution, auction_columns, snapshot_origin}` (+ `concept_effective_date`/`concept_captured_at` only on as_of_snapshot) + `mode` + guest masking; empty state has `available:false`. Matches the SUMMARY-reported curl shapes (`has_available:false` in 33-02 = absence of the empty-state-only key, recorded honestly).
- **Gap math**: enriched 248 `[OBSERVED]` − snapshots 8 `[OBSERVED]` = 240 = the `/pool/dates` `backfill_needed` claimed in 33-01/33-03 — arithmetic re-derived from the live lake, not taken from SUMMARY text.
- **strategy_cache md5**: this verifier's re-check `844886136b4663ac74f4d31fcd3ee752` == 33-01's recorded before/after md5 — consistent with D2 untouched.

## 6. Sandbox data reality `[OBSERVED]` (read-only re-inspection by this verifier)

- `data/screener_results/`: **8** `date=*` partitions (2026-07-27..08-05), **8/8** `part.json` with `snapshot_origin=="backfill"` (jq over all partitions).
- `data/premarket_results`: **absent** (0 entries — directory does not exist).
- `data/ext_history`: **absent** (0 entries — root cause of the honest `current_snapshot` fallback).
- `data/kline_daily_enriched`: 248 partitions — gap math consistent (§5).
- `data/user_data/strategy_cache.json` md5 `844886136b…` — matches 33-01's recorded pre/post values.

## 7. Human items (deploy-verified — not assertable in sandbox)

1. **Full-248 operator run**: the sandbox proved 8/8 real days in 13 s; the full 248-day run (~6-7 min measured anchor, ~650 MiB) must still be executed on deployment per the runbook (`docs/features.md:81-116`) — the executor's runs used port 3019 with the stale-root 3018 container untouched; production port is 3018. Deploy action, not a code gap.
2. **Real trading-day EOD/premarket interplay**: EOD-forward `ext_history` accumulation (which flips concept attribution to `as_of_snapshot` on later backfilled dates) and the 09:26 `premarket_pool_preview` job under live 09:15-09:25 feed both require a live production scheduler + data feed; the sandbox has neither (no cron, no premarket dir). Sandbox verified the honest fallback and structural isolation; the positive-control flip mechanism is unit-locked but not live-observed.

## 8. Honesty notes

- All PASS evidence is hermetic `[TEST]` or direct code reads unless tagged `[OBSERVED]`; the live-lake facts (§6) were re-inspected by this verifier, not taken from SUMMARY text.
- 33-01's `requested:0` idempotent re-run and 33-02's 3-day curl sampling are executor live-smoke records not re-executed in this pass (server lifecycle is hub-managed and already released); their key claims are independently re-derived here from code semantics (gap-set diff) and the live lake (8/8 backfill origin, ext_history absent).
- No overrides applied (0); no behavior left unverified in the hermetic set (0).
