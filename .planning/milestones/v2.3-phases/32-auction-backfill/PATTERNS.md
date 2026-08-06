# Phase 32: 竞价历史回填 (Auction History Backfill) — Pattern Map

**Mapped:** 2026-08-06 · **Consumes:** `RESEARCH.md` §1-§13 (line-verified, HIGH confidence) + `research/v2.3-data-depth/AUCTION-BACKFILL.md` (live probes #1-#11)
**Files analyzed:** 8 new/modified artifacts (6 backend + 2 test/registration)
**Analogs found:** 8 / 8 — every file maps to a live analog (5 self-analogs, 3 cross-file). The genuinely new surface is *pattern gaps*, not missing analogs.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/data_providers/xyz_provider.py` (modify) | provider | JSON-RPC MCP call → pl.DataFrame | self `_price_frame:107-149` + `_call_tool:151-177` + `custom/provider.py:129-148` (single-date `get_auction`) | exact (self-analog + custom precedent) |
| `backend/app/data_providers/base.py` (modify) | capability | data (declaration) | self `:19-26` (`ProviderCapabilities.auction` at :26) | exact (one-flag) |
| `backend/app/services/auction_sync.py` (modify) | service write seam | file-I/O (atomic hive-partition parquet) | self `:126-164` (window→crop→merge-upsert) + `:45-55` (`_atomic_write_parquet`) + `kline_sync.py:892-912` | exact (pure-move extraction) |
| `backend/app/services/auction_backfill.py` (new) | job | batch/transform (serial loop + pacing) | `pool_backfill.py:30-123` (`run_pool_backfill`) + `rate_limits.py:18-32,76-83` + `pipeline_jobs.py:99,132,140,155,171,252-267` | exact (job template) |
| `backend/app/api/auction_backfill.py` (new) | route | request-response (async job trigger) | `api/pipeline.py:90-166` (`pool_backfill` endpoint) + `api/auction_history.py:28,31,87` | exact (endpoint template) |
| `backend/app/main.py` (modify) | wiring | registration | self `:845-881` (router block), `:853`, guest whitelist `:791-793` | exact (self-analog) |
| `backend/tests/test_auction_backfill.py` (new) | test | file-I/O + endpoint + AST guard | `test_pool_backfill.py` + `test_auction_sync.py:7-31` + `test_auction_history.py:313,324-329` | exact |
| `backend/app/services/auction_probe.py` (touch-free unlock) | probe | read (capability scan) | self `:86-116` (`_default_sources`) + `:139-186` (`resolve_auction_probe`) | exact (no code change — behavioral unlock via xyz `auction=True`) |

---

## Pattern Assignments

### `backend/app/data_providers/xyz_provider.py` (modify — `get_auction`)

**Best analog:** self `_price_frame:107-149` (args building + row→frame mapping) + `_call_tool:151-177` (JSON-RPC envelope, errors → `""`); secondary `custom/provider.py:129-148` (existing single-date `get_auction(symbols, trade_date)` precedent) and `_normalize_auction:150-167` (555..565 + crop).

**Copy verbatim:**
- `_call_tool` envelope (`xyz_provider.py:151-177`) — `jsonrpc 2.0 / tools/call`, persistent `httpx.Client` (`:57-62`), `"error" in data` → log + `""` (feeds the empty-vs-coverage honesty heuristic).
- `_parse_payload:179-195` / `_parse_iso:196-205` / `_num:207-215` helper trio, reused as-is.
- `_price_frame` arg-building shape (`:107-149`): `{"security": [...]}` + optional `start_date`/`end_date` ISO strings; `strftime("%Y-%m-%d")` on the range bounds.
- Docstring discipline: `_price_frame` documents that upstream rejects a `fields` arg — `get_auction` docstring must repeat "do not pass `fields`" (probe #2 fetched full rows without it).

**Adapt (deliberate divergences):**
- **1 symbol per request guard** — `len(symbols) == 1` else `ValueError` (upstream probe #7: `带宽限制批量请求，检测到 N 个代码`). `_price_frame` batches N — no guard exists there; this is a new contract.
- **Suffix-preserving symbol mapping** — map `code` → the *requested suffixed* `symbols[0]` (defensive `{stripped: full}` map), NOT `_price_frame`'s stripping (`str(row.get("code") or symbols[0]).split(".")[0]` at :139). The `kline_auction` merge-upsert key `["symbol","datetime"]` (`auction_sync.py:153-158`) demands suffix-consistent symbols matching `kline_daily`, else backfill and live EOD rows for one stock collide as two keys (§4 same-day collision rule).
- **Tool name** `stockdb_get_call_auction`; **no `fields` arg**.
- **Column crop** → canonical subset `["symbol","datetime","auction_volume","auction_amount",("auction_virtual_price")]` — subset of `CANONICAL_AUCTION_COLS + OPTIONAL_AUCTION_COLS` (`auction_sync.py:33-43`) so the seam crop passes through. `auction_unmatched_volume` **never** produced (upstream lacks it; only 5-level book b/a1-5 — not real unmatched volume).
- **Single-date form** — `end_date is None` → `start_date == end_date` (probe `_default_fetcher:117-118` and `custom/provider.py:129` call with one date).
- **Capability flag** — add `auction=True` to `ProviderCapabilities(...)` at `:48-56`. Nothing else; `base.py:26` already exists, probe and seam auto-discover (§3).

### `backend/app/data_providers/base.py` (modify — capability declaration)

**Analog:** self `:19-26`. One-flag change: `auction: bool = False` field already declared at :26 — flip it on in xyz only. Probe selection is `getattr(getattr(provider, "capabilities", None), "auction", False)` (`auction_sync.py:75-84`); no other provider declares it, so xyz becomes the sole `_default_sources` candidate. No Cap enum / tiers.yaml change (`capabilities.py:11-28` has no auction cap — out of scope, probe gate is capability-agnostic).

### `backend/app/services/auction_sync.py` (modify — extract `write_auction_partitions`)

**Analog:** self. Factor the lake-write segment out of `sync_and_persist_auction` (`:126-164`) into `write_auction_partitions(df, repo) -> int`:
- 555..565 window predicate `:126-135` (minutes = hour*60+min, cast to `pl.Datetime("us")` first — the `datetime` normalization at :128-131 rides along),
- canonical crop `:137-141` (existence-based `keep = [c for c in CANONICAL+OPTIONAL if c in df.columns]` — honest column absence),
- per-`date=` partition merge-upsert `:145-164` (`unique(subset=["symbol","datetime"], keep="last")`, `_trade_date` temp col, `partition_by`),
- `_atomic_write_parquet:45-55` (`.tmp` same-dir rename).

**Pure move, zero behavior change:** `sync_and_persist_auction:97-165` keeps probe gate (`:104-106`) + `_first_auction_provider` (`:57-84`) + single-date fetch, then calls the helper. Existing `test_auction_sync.py` suite must stay green unchanged. Write path becomes single-source-of-truth: seam + backfill job both land here; the window predicate + crop + upsert + rename are never duplicated. Comment at :117-122 already names `kline_sync.py:892-912` as the merge-upsert idiom source.

### `backend/app/services/auction_backfill.py` (new — job)

**Best analog:** `pool_backfill.run_pool_backfill:30-123` (job shape), `rate_limits.py` (pacing), `pipeline_jobs.py` (lifecycle), `auction_probe.py:71-84` (partition-dir scan).

**Copy from `pool_backfill.py:30-123`:**
- Signature shape `(repo, *, symbols=None, start=None, end=None, rpm=30, on_progress=None, job_id=None) -> dict` (`:30-38`).
- Empty-terminal short-circuit dict `{"requested":0,"backfilled":0,"failed":0,"failed_symbols":[],"reason":"source_unavailable"}` (`:66-77` shape, extended with `reason`).
- Cooperative cancel (`:88-91`): `j = job_store.get(job_id); if j is None or j["status"] == "failed": emit("done",100,...); break`.
- Per-item try/except → record failure → continue (`:93-108`); `emit("auction_backfill", pct, f"{i}/{tot}", stage_pct=...)` progress (`:109-111`); final terminal dict with `"origin": "backfill"` (`:113-123`).
- `_ERROR_DETAIL_MAX` reason truncation — mirror `auction_probe.py:29-30` (`reason = str(e)[:200]`).
- Pacing via `sleep_between_batches(i, rpm)` (`rate_limits.py:76-83`) → shared `_reserve_slot` throttle (`rate_limits.py:18-32`); rpm=30 → 2s/symbol, ~5.5h worst case for 5537 symbols (rpm≈37 → ~3h); range 1..60, operator-tunable.

**Adapt (new seams, see Pattern Gaps):**
- **Lake-derived scope**: dates = `kline_daily` partition dirs ∩ [start,end] (glob idiom `pool_snapshot.py:144`); symbols = `SELECT DISTINCT symbol FROM kline_daily` via repo view (`repository.py:162-164`, `union_by_name=true` — drift-tolerant) or column-scoped `pl.scan_parquet(...).select("symbol").unique()` (schema drift, `quote_ts`). Universe taken once at job start.
- **Probe gate (AQ-03a)**: direct `resolve_auction_probe().status == available` (`auction_sync.py:87-95` precedent) — **no capset, no `auction_sync_enabled` preference** (mirror pool_backfill: operator-triggered, preference-independent).
- **Preflight reachability**: one real `get_auction([symbols[0]], start, end)`; exception/empty-with-coverage → fail-closed record, 0 writes.
- **Per-symbol serial loop**: 1 request per symbol via `_first_auction_provider()` (`auction_sync.py:57-84` — same candidates[0] as the probe, so verdict `available` ⇒ provider non-None). Empty response while symbol has kline_daily rows in range → `failed_symbols.append({"symbol": sym, "reason": "empty_response"})`.
- **Write-boundary alignment (AQ-03b)**: `df.filter(pl.col("datetime").dt.date().is_in(aligned_dates))` before `write_auction_partitions` — upstream rows for dates absent locally are dropped, never phantom-written.
- **Terminal dict**: `{"requested", "backfilled_symbols", "rows", "dates", "failed", "failed_symbols":[{symbol,reason}], "origin":"backfill", "rpm"}`.

### `backend/app/api/auction_backfill.py` (new — endpoint)

**Best analog:** `api/pipeline.py:90-166` `pool_backfill` endpoint (full skeleton), `api/auction_history.py:28,31,87` (router prefix + `_SYMBOL_RE`).

**Copy from `api/pipeline.py:90-166` (the endpoint is the template, not `auction_history.py`):**
- `APIRouter(prefix="/api/kline/auction", tags=["kline"])` (`auction_history.py:28` same prefix — separate module, separate router object).
- Validation loop `:104-122`: `^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat`, `start <= end`, `isinstance(int) and not isinstance(bool)` bounds check → `HTTPException(400)`. Adapt: rpm int 1..60; `symbols` optional list, each `_SYMBOL_RE` fullmatch (`auction_history.py:31`), length cap ≤6000.
- Lifecycle `:124-166`: `job_store.reap_stale()` → `job_id, is_new = job_store.create()` (single-flight, pending∨running) → `{"status":"reused"}` short-circuit → `async def task()`: `try_acquire_run_slot()` fail-fast (`pipeline_jobs.py:252-267`) → `job_store.start` → `asyncio.get_event_loop().run_in_executor(_long_task_executor, lambda: run_auction_backfill(...))` (`_long_task_executor`, `pipeline.py:17`) → `job_store.succeed` → `invalidate_storage_cache()` (mirror `pipeline.py:159-162` run_now path) → `finally: release_run_slot()`.
- Immediate `{"status": "started"|"reused", "job_id"}` return; client polls existing `GET /api/pipeline/jobs/{id}`, cancels via existing `POST /api/pipeline/jobs/{id}/cancel` (cooperative, per symbol). No new job UI.

### `backend/app/main.py` (modify — registration)

**Analog:** self. Add `app.include_router(auction_backfill.router)` inside the `# 路由` block after `:853` (auction_history registration line). POST is not guest-readable (`_is_guest_readable` admits only two pool GETs, `:791-793`) — **no whitelist change**.

### `backend/tests/test_auction_backfill.py` (new — tests)

**Analog:** `test_pool_backfill.py` (endpoint conventions) + `test_auction_sync.py:7-31` (hermetic provider fakes) + `test_auction_history.py:313,324-329` (POOL-03 AST guard + router registration). No `test_extend_history.py` exists — `test_pool_backfill.py` is the template.

**Copy:**
- Hermetic unit conventions: production imports inside test functions (`test_auction_sync.py:7-9`); `FakeAuctionProvider` with rows/`exc`-injectable (`test_auction_sync.py:14-31`); `_FakeRepo` + `tmp_path` partition dirs (`test_pool_backfill.py`); endpoint `_make_backfill_app`/`_wait_job_terminal`/`_wait_slot_free` poll helpers.
- `test_0930_excluded` / `test_atomic_write_leaves_no_tmp` / `test_sync_without_optional_cols_stays_four_cols` (seam invariants), `test_backfill_endpoint_singleflight_and_reuse` / `_parameter_validation` / executor-succeeds, `test_pool_backfill_cooperative_cancel` — mirror each by name.
- Router-registration test mirroring `test_auction_history.py:324-329`.
- AST guard mirrors: `test_auction_history.py:313` scans `@router.(post|put|delete|patch)` — new tests must assert the *new* router (not auction_history) hosts POST, and auction_history stays mutation-free.

**Adapt (new-load-bearing, no direct analog):**
- `test_xyz_get_auction_maps_rows_to_canonical` (monkeypatch `_call_tool` → canned payload; suffixed symbol, datetime, volume/amount, virtual price), `_single_date_form` (start==end), `_rejects_multi_symbol` (ValueError), `_empty_payload_on_error` (→ empty df, no raise).
- `test_write_auction_partitions_preserves_suffix_key` — `000001.SZ` vs bare `000001` distinct upsert keys (same-day collision rule).
- `test_auction_backfill_only_writes_kline_daily_aligned_dates` (AQ-03b, load-bearing), `_source_down_zero_writes` (AQ-03a), `_per_symbol_failure_recorded` (AQ-03c), `_idempotent_rerun` (AQ-04), `_one_symbol_per_request` (AQ-05), `_rate_limit_pacing` (monkeypatch time).
- Network-gated cross-check `test_auction_virtual_price_equals_daily_open` — `skip unless RUN_NETWORK_TESTS=1`; canned always-on variant (fixture kline_daily open == fake `current`).

### `backend/app/services/auction_probe.py` (touch-free unlock)

**Analog:** self. **No code change.** `_default_sources:86-116` already scans (a) custom providers with `"auction"` dataset (`custom/config.py:10` DatasetName includes it) and (b) builtin chain members with `capabilities.auction == True` (`chain.py:20-26`, `_get_provider("xyz")` at `:74-75`). With xyz declaring `auction=True`, `resolve_auction_probe():139-186` flips `not_configured → available` with zero edits. **Behavioral consequence (R3)**: probe now performs one live HTTP call per invocation (1.6s nominal / 8s timeout) — added latency to `GET /api/kline/auction/history` and EOD gate; acceptable, short-TTL probe cache explicitly deferred (do not scope-creep).

---

## Shared Patterns

### JSON-RPC MCP call with error→empty payload
**Source:** `xyz_provider.py:151-177` (`_call_tool`), `:179-195` (`_parse_payload`), `:196-205` (`_parse_iso`), `:207-215` (`_num`).
**Apply to:** `get_auction` — same envelope, same helpers; errors swallow to `""` → `[]` → empty `pl.DataFrame()` (no crash); caller-side gates distinguish empty-from-down.

### Atomic hive-partition write (`.tmp` + rename, merge-upsert idempotency)
**Source:** `auction_sync.py:45-55` (`_atomic_write_parquet`), `:145-164` (per-date merge-upsert `unique(subset=["symbol","datetime"], keep="last")`); `kline_sync.py:892-912` (same idiom).
**Apply to:** `write_auction_partitions` extraction + backfill reruns — re-runs only fill gaps; interrupted runs never corrupt; `*.tmp` never matches the `*.parquet` glob.

### 555..565 window predicate (single source of truth)
**Source:** `auction_sync.py:29-30` (`_WINDOW_START/END_MIN`), filter `:126-135`; duplicated in `custom/provider.py:150-167`.
**Apply to:** `get_auction` never needs its own window logic — upstream emits 09:25:00 only; the seam's predicate structurally excludes 09:30+ rows at the write boundary.

### Capability-declared source discovery
**Source:** `base.py:19-26` (field default False), `auction_sync.py:57-84` (`_first_auction_provider`), `auction_probe.py:86-116` (`_default_sources`).
**Apply to:** one-flag unlock — no chain key (`_BUILTIN_CHAIN` has no `auction` entry and none is needed), no Cap enum change, probe and write land on the same `candidates[0]`.

### Job lifecycle + heavy-slot mutual exclusion
**Source:** `pipeline_jobs.py:99` (`create`, pending∨running single-flight), `:132/:140/:155/:171` (start/succeed/fail/progress), `:252-267` (`try_acquire_run_slot`/`release_run_slot`); `api/pipeline.py:90-166` orchestration.
**Apply to:** backfill endpoint + job — `reap_stale` → `create` → slot → executor → `succeed/fail` → `release` in `finally`. A running pool/EOD backfill blocks auction backfill via the slot — correct and intended (same parquet-adjacent heavy-task family; R7).

### ISO date validation (path-safety + bounded work)
**Source:** `api/pipeline.py:104-122`; `api/auction_history.py:31,87` (`_SYMBOL_RE` + validation).
**Apply to:** backfill endpoint params; job's `start`/`end` string comparison (ISO lexical order, `pool_backfill.py:66-69`).

---

## Pattern Gaps (no existing analog — fresh design needed)

1. **MCP tool with 1-symbol/request cap + `fields` param discipline.** Upstream `stockdb_get_call_auction` rejects multi-symbol batches (probe #7) — no existing provider guards `len(symbols) == 1` (`_price_frame:107-149` batches N; minute sync fetches multi-symbol chunks). Fresh: `ValueError` guard in provider + serial per-symbol loop in job + docstring "no `fields` arg" rule (probe #2 evidence). No analog for a per-request cardinality contract.
2. **Per-symbol failure ledger.** `pool_backfill.py:66-77` tracks `failed_dates` (bare strings); auction backfill needs `failed_symbols: [{"symbol", "reason"}]` — symbol + truncated reason (≤200 chars, `auction_probe.py:29-30` idiom) per failure class (`empty_response` vs exception). Dict-in-list ledger shape is new; fail-and-continue discipline is shared.
3. **kline_daily-aligned date gate (cross-lake partition alignment).** No existing job cross-gates its writes against *another lake's* partitions: pool_backfill aligns against its own snapshot partitions; extend_history doesn't align. Two layers here: (a) scope = `kline_daily` partition-dir dates ∩ [start,end]; (b) **write-boundary filter** `pl.col("datetime").dt.date().is_in(aligned_dates)` inside the job before `write_auction_partitions` (covers upstream returning extra dates). Load-bearing honesty invariant (AQ-03b) — fresh design, pinned by a dedicated test.
4. **Empty-vs-coverage heuristic.** `_call_tool` swallows errors to `""` (`xyz_provider.py:151-177`), so "upstream down" and "no data for this symbol" are indistinguishable at the provider. The job's heuristic — symbol has kline_daily rows in range but provider returned empty → `empty_response` failure record — is new logic with no precedent (pool_backfill just records the date). Preflight call adds a second layer: fail-closed record + 0 writes before the loop.
5. **Lake-derived universe + date scope with schema drift.** Universe = `SELECT DISTINCT symbol FROM kline_daily` (view, `repository.py:162-164` `union_by_name=true`) or column-scoped `pl.scan_parquet`; dates from physical partition dirs (glob, `pool_snapshot.py:144`). pool_backfill derives its date set from its own partitions (`list_backfill_gaps`); deriving both universe *and* date window from a different, schema-drifted lake (R6: `quote_ts` on later partitions only) is a new reader pattern. Universe must be snapshotted once at job start (multi-hour run vs concurrently-added partitions).
6. **Preflight reachability call.** One real `get_auction([symbols[0]], start, end)` before the loop → fail-closed record, 0 writes on exception/empty-with-coverage. pool_backfill has no preflight (iterates and records). Also new: probe verdict flips from zero-network to live-HTTP (R3) — no cache analog exists; short-TTL probe cache is a documented follow-up, not 32-01 scope.
7. **`origin="backfill"` in terminal dict only.** The lake has no provenance column (seam writes none today) — provenance is partition presence. Job's terminal dict carries `origin:"backfill"` mirroring pool_backfill; if per-partition provenance is later wanted it is a seam change **out of Phase 32 scope** — flag for planner, do not invent.

---

## Guard Rails

1. **POOL-03 AST guard placement.** `api/auction_history.py` is mutation-forbidden — `tests/test_auction_history.py:313` scans `@router.(post|put|delete|patch)` on that router. The new POST lives in a **separate** `api/auction_backfill.py` router with the same `/api/kline/auction` prefix; `auction_history.py` stays GET-only. Registration in `main.py` after `:853`; guest whitelist (`:791-793`) unchanged — POST is not guest-readable.
2. **Honesty rules (AQ-03/04).** (a) Fail-closed: probe gate + preflight reachability before any write; 0 writes on source-down, explicit `reason` record. (b) kline_daily-aligned dates only — scope ∩ range plus write-boundary `is_in(aligned_dates)` filter; never phantom-write a date the daily lake doesn't have. (c) `auction_unmatched_volume`/`auction_unmatched_amount` **never 0-filled** — upstream lacks the field, `get_auction` never emits it, seam crop (existence-based `keep`, `auction_sync.py:137-141`) never writes it; pinned by `test_auction_backfill_unmatched_col_absent`. (d) `origin="backfill"` lives in the terminal dict, not the lake. (e) 09:30+ exclusion is structural (seam 555..565 predicate) — never rely on upstream alone.
3. **Watchlist.tsx zero-touch.** `frontend/src/pages/Watchlist.tsx` must not be read, claimed, or modified. Broader: **no frontend changes this phase at all** (Q6: no new job UI — status/cancel reuse existing `/api/pipeline/jobs/*` endpoints).
4. **Write-seam single source of truth.** `write_auction_partitions` extraction is a **pure move** — `sync_and_persist_auction` keeps probe gate + `_first_auction_provider` + fetch, delegates writes; existing `test_auction_sync.py` must pass unchanged. One write path, two entry points. Rejected alternative: calling `sync_and_persist_auction` per (symbol, date) = 5537 × 248 ≈ 1.37M provider calls.
5. **Backfill must NOT consult `auction_sync_enabled`** (`preferences.py:129-132`, default False). Operator-triggered like pool_backfill; EOD scheduled path stays double-gated and off by default (flipping xyz capability flips only gate 2, `daily_pipeline.py:696-708`).
6. **Same-day collision rule.** Backfill writes suffixed symbols (`000001.SZ`) exactly like `_resolve_universe` (`daily_pipeline.py:141-165`) and the EOD path — the upsert key treats bare vs suffixed as different rows. Pinned by `test_write_auction_partitions_preserves_suffix_key`.

## Metadata

**Analog search scope:** `backend/app/data_providers/*`, `backend/app/services/*`, `backend/app/api/*`, `backend/app/jobs/*`, `backend/tests/*`, `backend/app/main.py`, `backend/app/tickflow/*`
**Files scanned (anchors verified):** xyz_provider, base, custom/provider, chain, auction_sync, auction_probe, pool_backfill, pipeline_jobs, rate_limits, pool_snapshot, kline_sync (via seam comment), api/pipeline, api/auction_history, main, repository, preferences, daily_pipeline, test_pool_backfill, test_auction_sync, test_auction_probe, test_auction_history
**Pattern extraction date:** 2026-08-06
**Off-limits:** `frontend/src/pages/Watchlist.tsx` (user-pending — not read, not claimed); no frontend files analyzed.
