# 32-01 Summary — AQ-01 provider + write seam + probe unlock

**Executor:** ExecutorP3201 · **Date:** 2026-08-06 · **Plan:** `.planning/phases/32-auction-backfill/32-01-PLAN.md` · **Wave:** 1
**Verdict:** DONE — 3/3 tasks, all verification gates green, live MCP probe resolved `available` (source `xyz`) in sandbox.

---

## Task status

| Task | Status | Commit(s) |
|------|--------|-----------|
| T1 — `xyz_provider.get_auction` + `capabilities.auction=True` + `test_xyz_provider.py` (AQ-01 provider) | ✅ | `1089b6e` test(32-01): hermetic get_auction unit tests (mapping/single-date/1-symbol guard/empty payload/no-optional-col) · `3a84b77` feat(32-01): xyz_provider.get_auction + capabilities.auction=True (AQ-01 provider) |
| T2 — `auction_sync.write_auction_partitions` write-seam extraction (AQ-04 pure move) | ✅ | `5eca51e` test(32-01): write_auction_partitions direct-call tests (suffix upsert key + shape) · `1ec11a5` feat(32-01): extract write_auction_partitions write seam (AQ-04 pure move, single write path) |
| T3 — probe unlock verification (capability auto-discovery + available flip) | ✅ | `b3fdb37` test(32-01): probe unlock verification — capability auto-discovery + available flip (AQ-01 acceptance) |
| SUMMARY | ✅ | committed with this file |

## Verification

| Gate | Result |
|------|--------|
| `pytest tests/test_xyz_provider.py -x -q` | **5 passed** (mapping w/ suffix symbol, single-date form, 1-symbol ValueError guard incl. empty + missing start_date, empty payload `""`/raise → empty df, no-optional-col → 4 canonical cols) |
| `pytest tests/test_auction_sync.py -x -q` | **17 passed** — 15 pre-existing cases **zero-line-changed** (window 555..565 / atomic no-.tmp / merge-upsert idempotent / optional-col passthrough / 4-col absence) + 2 new (`write_auction_partitions_preserves_suffix_key`, `_direct_shape`) |
| `pytest tests/test_auction_probe.py -x -q` (hermetic) | **14 passed, 1 skipped** — 11 pre-existing (not_configured / 0930 fail-closed / error / fixed fields / detail copy / endpoint cache) + 3 new (capability discovery, available flip w/ 0930+empty fail-closed, xyz capability declared); 1 network-gated skip |
| Combined `test_xyz_provider + test_auction_sync + test_auction_probe` | **36 passed, 1 skipped** |
| Structure gates | `auction=True` @ xyz_provider.py:59 · `def get_auction` @ xyz_provider.py:156 · `def write_auction_partitions` @ auction_sync.py:57 — all ≥1 |
| **Live smoke** `RUN_NETWORK_TESTS=1 pytest tests/test_auction_probe.py -k real_mcp -x -q` | **1 passed** — real MCP reachable from sandbox; `resolve_auction_probe()` → `{'status': 'available', 'source': 'xyz', 'window': '09:15-09:25', 'detail': '已检测到 9:15–9:25 集合竞价匹配数据。'}` (probed 2026-08-06T16:52:29Z). **AQ-01 acceptance flip verified live, not just mocked.** |

## Deviations & execution notes

- **No source deviations from the plan.** Test-draft corrections only (no production code changes beyond the plan's spec):
  1. `test_write_auction_partitions_preserves_suffix_key` initially assumed first-write dedupe; actual pure-move semantics (and the pre-existing `test_merge_upsert_same_day` precedent) dedupe via `unique([symbol,datetime], keep="last")` **only when merging with an existing partition** — test rewritten to two direct writes (raw 3 rows → upsert → 2 rows: `000001.SZ` and bare `000001` distinct keys, keep-last picks v=300/v=200).
  2. `test_write_auction_partitions_direct_shape` initially asserted `kline_auction` dir absent after empty-df call; `DataStore(data_dir)` pre-creates the lake dir — assertion relaxed to "no `date=*` partitions" (same guard the pre-existing suite uses).
  3. Plan Test 4 requires "`_call_tool` 抛异常 → 空 df 不抛"; the real `_call_tool` swallows errors internally, so `get_auction` adds an explicit `try/except` around `_call_tool` → log + empty `pl.DataFrame()` (documented in the docstring; mirrors the swallow semantics at the method boundary). All other mapping/guard/arg logic verbatim per plan.
- **Plan-check warnings:** W-1 (`repo.query` → `repo.db.execute`/scan_parquet fallback), W-2 (imports `date`/`logger`/`_noop`), W-3 (module-level `sleep_between_batches` import for patchability), W-5 (8-key success terminal invariant; `reason` fail-closed-only) are **32-02 concerns — wave-2 executor must apply them**. W-4 (`-k` filter token coverage) is **32-03**. No W applies to 32-01 execution; all applied implicitly where 32-01 touched shared contracts (none).
- **Honesty invariants honored:** `auction_unmatched_volume` never emitted (upstream lacks it; only 5-level book b/a1-5); `auction_virtual_price` emitted only when upstream provides `current`; probe fail-closed rules (T-16-01 09:30+ never `available`) unchanged and re-pinned with capability-declaring source; empty-vs-down left to caller gates.
- **Zero-touch surface:** `base.py`, `auction_probe.py`, `daily_pipeline.py`, `custom/provider.py` source untouched; no new runtime deps; no `data/` writes outside tmp lakes; `frontend/` untouched incl. `Watchlist.tsx` (proof below).
- **R3 accepted:** probe now performs 1 live HTTP per invocation (1.6s nominal / 8s timeout); short-TTL probe cache deferred to 32-03 per plan — no scope creep.

## Watchlist.tsx zero-touch proof

```
staged 0, unstaged 1, untracked 0
M frontend/src/pages/Watchlist.tsx
```
`frontend/src/pages/Watchlist.tsx` remains the **only** unstaged change at close (user-owned, never read/claimed/modified). No `frontend/` file in any 32-01 commit.

## Downstream readiness (wave-2 consumers)

- `xyz_provider.get_auction(symbols, start_date=None, end_date=None)` — 1-symbol guard, single-date form (`end_date=None` → start==end), suffixed-symbol mapping — ready for `auction_probe._default_fetcher` (single-date call) and 32-02 per-symbol loop.
- `auction_sync.write_auction_partitions(df, repo) -> int` — single write path (window → crop → per-date merge-upsert → .tmp atomic rename) — ready for `run_auction_backfill` (32-02).
- `capabilities.auction=True` → `_default_sources`/`_first_auction_provider` auto-discover xyz; probe resolves `available` (verified live); EOD double gate unchanged (gate 2 flips, gate 1 `auction_sync_enabled` default False).
