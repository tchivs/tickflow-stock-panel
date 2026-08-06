# Phase 29: 竞价策略历史验证 (BT-01..06) — Pattern Map

**Mapped:** 2026-08-06
**Files analyzed:** 7 new/modified artifacts (2 modified source + 2 new source + 3 new tests)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/services/auction_columns.py` (modify: +`attach_auction_columns_range` + partition-discovery helper) | service (injection primitive) | file-I/O + transform (partition discovery → symbol dedup → vectorized left-join) | self: `attach_auction_columns` `:89-151` (gates/keep-list/dedup/join) + `_attach_auction_volume_ratio` `:54-87` (PIT-safe denominator) + `auction_history.py:_dir_date` `:61-66` (partition date parse) | exact (self-analog + adjacent) |
| `backend/app/services/auction_validation.py` (new: `AuctionValidationService`) | service (report assembly) | transform/aggregate (read-only projection + forward stats, zero write) | `pool_hub.py` (projection core + honest empty + as_of echo) + `premarket_pool.py` (payload assembly + probe passthrough) + `screener.py:722-812` (enumeration/empty-list) + `backtest/strategy.py:522-570` (mask, mirrored not imported) | role-match (4 analogs, one per concern) |
| `backend/app/api/research_auction.py` (new: GET `/api/research/auction/validation`) | controller | request-response (GET-only read, honest empty) | `api/auction_history.py` (GET-only + 200-empty + probe passthrough + `_dir_date`) + `api/research.py` (`_bad_request` code shape, Query date) + `api/backtest.py:_resolve_start` (default window) | exact |
| `backend/app/main.py` (modify: 1 line) | config | — | self: include_router block `:848-881` (insert `research_auction.router` right after `research.router`) | exact (self-analog) |
| `backend/tests/test_auction_validation.py` (new) | test (POOL-03 AST guard) | static analysis | `test_pool_hub.py:857-963` (E1/E3/E4/E5 shapes) + `test_auction_history.py` guard section (single-file `_feature_sources`) | exact |
| `backend/tests/test_attach_auction_columns_range.py` (new) | test (unit + equivalence property) | transform (vectorized vs single-day equality) | `test_auction_columns.py` (hermetic helpers `:20-61` + dual-gate matrix + fan-out dedup) | exact |
| `backend/tests/test_auction_validation_report.py` (new) | test (service + endpoint integration, fixture lake) | request-response + aggregate | `test_auction_history.py` (`_make_client` minimal app + stub middleware) + `test_auction_columns.py` (`_write_enriched_partition` lake seeding) | exact |

---

## Pattern Assignments

### `backend/app/services/auction_columns.py` (modify — add `attach_auction_columns_range`)

**Best analog:** current single-date `attach_auction_columns` in the same module (`:89-151`) — copy the injection skeleton verbatim, swap the two live gates for historical partition discovery. **Do not create a new module** (keeps `_AUCTION_REAL_COLS`/keep-list/注释语义 shared; module docstring already declares "绝不写湖"). New function introduces **no new imports** (BT-06 import whitelist: `app.tickflow.repository` + polars + stdlib only).

**Gate change (the one deliberate divergence, REV-01):** single-day has probe×分区双闸门 (`:94-98` probe gate, `:101-106` partition gate); the range version drops the probe gate entirely — history gate = partition existence only. Document this divergence in the new function docstring, mirroring the `:95-96` 铁律注释:

```python
# 平台铁律 (单日版 :95-96): 分区不存在 → 诚实按日空态 (列缺席), 绝不做 null-as-present
```

**Partition discovery** — copy `auction_history.py:_dir_date` (`:61-66`) and the scan-loop shape from `get_auction_history` (glob + parse + skip-bad + guarded read):
```python
def _dir_date(part_dir) -> date | None:      # auction_history.py:61-66, copy verbatim
    name = part_dir.parent.name
    if not name.startswith("date="):
        return None
    try:
        return date.fromisoformat(name[len("date="):])
    except ValueError:
        return None
```
Scan loop: `base = repo.store.data_dir / "kline_auction"`; `for part in base.glob("date=*/part.parquet")`; `d = _dir_date(part); if d is None or not (start <= d <= end): continue`; `try: pl.read_parquet(part) except Exception: continue` (mirror auction_history read-guard); empty partition → skip (mirror `:119-121`). No matching partitions → `(df, [])`.

**Multi-partition concat** — copy `auction_history.py` `pl.concat(frames, how="diagonal_relaxed")` (tolerates old 4-col / new 6-col partition schema drift).

**Keep-list cropping** — copy `:122-128` verbatim:
```python
keep = [
    c for c in (
        "symbol", *_AUCTION_REAL_COLS,
        _AUCTION_UNMATCHED_AMOUNT_COL, _AUCTION_VOLUME_RATIO_COL,
    ) if c in auction.columns
]
auction = auction.select(keep)
```

**Symbol dedup + join** — copy `:130-133` (`unique(subset=["symbol"], keep="last")` fan-out defense) and `:137`; **adapt the join key** from `on="symbol"` to `on=["symbol", "date"]` (range key). Partition has rows but a symbol absent on that date → null (honest per-symbol absence, mirror `:149-151` comment). After injection, trim `df.filter(pl.col("date") >= start)` so warmup rows never appear in results. Return `(df, sorted(enabled_dates))` where enabled_dates = non-empty partition dates within `[start, end]`.

**Vectorized PIT-safe ratio (new — no existing multi-day analog, see Gaps)** — semantic mirror of `_attach_auction_volume_ratio` `:54-87` (single-day: `get_enriched_history(T,6)` → `filter(date < T)` → `tail(5).mean()`):
```python
# 计算帧须先 sort(["symbol","date"]) 且同时携带 auction_volume 与 volume
(df.with_columns(
    (pl.col("auction_volume")
     / pl.col("volume").shift(1).rolling_mean(5, min_periods=1).over("symbol"))
    .alias("auction_volume_ratio"))
)
```
Executor note (RESEARCH §2.1.3): recommended to compute on the auction frame before left-join (panel row count untouched) — the auction frame must first receive `volume` via a `(symbol, date)` join from `df`; alternatively compute post-join on `df`. Either is acceptable; the equivalence property test locks both to per-day value equality with the single-day path.

---

### `backend/app/services/auction_validation.py` (new — `AuctionValidationService`)

**Best analogs:** `pool_hub.py` (report projection + honest empty + authority echo), `premarket_pool.py` (payload assembly + probe injection/passthrough), `screener.py` `run_all_with_hits` (strategy enumeration), `backtest/strategy.py` `_build_candidate_filter_mask` (mask semantics — **documented mirror in docstring with anchor `backtest/strategy.py:522-570`, never imported** per BT-06).

**Class skeleton** — copy `ScreenerService.__init__` ctor shape (`screener.py:724-728`): `def __init__(self, repo, ...)` storing `self.repo`; Phase 29 adds `self.engine`.
```python
class AuctionValidationService:
    def __init__(self, repo: KlineRepository, engine: StrategyEngine) -> None: ...
    def build_report(self, *, start, end, strategy_ids, symbols) -> dict: ...
```

**Probe injection/passthrough** — copy `premarket_pool.py:45-57` (`probe_resolver: Callable | None = None` param defaulting to `resolve_auction_probe`; verdict via `probe.to_dict()`):
```python
probe_resolver = probe_resolver or resolve_auction_probe
probe = probe_resolver()
verdict = probe.to_dict() if hasattr(probe, "to_dict") else probe
```
Probe does **not** gate the historical report (REV-01); API resolves once, payload carries it verbatim (BT-01 `probe` field).

**Honest empty skeleton** — copy `premarket_pool.py:66-75` (empty → 200-shaped dict with flags, never raise) and `pool_hub.build_pool_hub` `:314-317` (`cache is None → 空 Hub` dict, no 404/500). Phase 29 mapping: enriched window empty → `{"data_gate":"empty","empty_reason":"enriched_unavailable","strategies":[]}`; auction lake empty → `data_gate:"empty"` + `no_auction_partitions` but `strategies` still carries all 9 (4 real with `n_dates==0`, derived/eod with stats — RESEARCH §5 BT-01 调和; `strategies==[]` only when enriched itself is empty).

**Window clamp + honest echo** — copy `pool_hub.build_pool_hub` `:319-321` `resolved_as_of` (authority wins; caller value echoed only when identical):
```python
# pool_hub.py:319-321 — 回显权威值, 不伪造第二个日期
resolved_as_of = as_of if (as_of and as_of == cache_as_of) else cache_as_of
```
Phase 29: clamp `[start, end]` to enriched cache bounds (`repo._enriched_history_cache` `date.min()/max()`; fallback: scan `kline_daily_enriched/date=*`), echo both `window.requested_*` and `window.effective_*`. **Do NOT apply `BACKTEST_MAX_SERVER_DAYS`** (locked decision, RESEARCH §2.3.1 — the 186-day guard protects portfolio backtests' memory, `backtest.py:30-32`; this endpoint is a single-panel vectorized scan with no guard and `settings.backtest_range_guard` default `False` at `config.py:103`).

**Panel load** — `repo.get_enriched_range(warmup_start, end, symbols=symbols)` (`repository.py:966-998`); `None`/empty → honest empty (`enriched_unavailable`), never 500 (fast-path cache returns `None` when uncovered — mirror that semantic). warmup_start = `start − 14 自然日` (RESEARCH §2.2.1; contrast with strategy backtest's 120-day warmup in `strategy.py:_panel_window` `:109-113` — different scale, don't copy). **Do not reuse the slow path** (`scan_enriched_parquet` + `compute_all`) — the research report is honest-empty when the cache doesn't cover (RESEARCH §5 risk 3).

**Strategy enumeration** — copy `screener.py:745-754` shape (engine id enumeration + dedupe):
```python
all_ids = list(PRESET_STRATEGIES.keys())          # Phase 29: _AUCTION_FAMILY_IDS 硬编码 9 个竞价族 id
if engine:
    for meta in engine.list_strategies():
        sid = meta["id"]
        if sid not in PRESET_STRATEGIES:
            all_ids.append(sid)
if strategy_ids and isinstance(strategy_ids, list):
    id_set = set(strategy_ids)
    all_ids = [sid for sid in all_ids if sid in id_set]
if not all_ids:
    return {}                                     # screener.py:756 — 空列表 → {} (BT-03)
```
Fetch definitions via `engine.get(sid)` / `engine._strategies` (StrategyDef with `filter_fn`/`meta`/`minute_confirm_fn`); unknown id → `engine.get` raises `ValueError` (`engine.py:282-285`) → catch per-strategy, record in `skipped_ids`, no 500 (mirror `run_all_with_hits` `except (ValueError, Exception): continue` `:780-781`).

**Params** — always META defaults, deterministic: `{p["id"]: p["default"] for p in params}` (the normalization applied at `engine.py:229`; `meta["params"]` is already a normalized list of defs after `_load_file` `:227-231`). No user overrides (BT-03).

**Candidate mask (mirror, not import)** — semantic copy of `_build_candidate_filter_mask` `:522-570`, restricted to the `filter_fn` path (9-family strategies have no `filter_history_fn`):
```python
def _build_candidate_mask(panel, s: StrategyDef, params) -> pl.Series:
    if s.filter_fn is None:
        return pl.Series("_cand", [True] * len(panel), dtype=pl.Boolean)
    try:
        expr = s.filter_fn(panel, params)
        return panel.select(expr.alias("_cand"))["_cand"].fill_null(False).cast(pl.Boolean)
    except Exception:
        return pl.Series("_cand", [False] * len(panel), dtype=pl.Boolean)  # fail-closed, mirror strategy.py:551-552
```
hits = `verification_panel.filter(mask)` rows; `n_hits` = row count; `per_date` = `group_by("date")` counts (+ `n_screened` = that day's panel rows).

**Branch selection (BT-05 mutual exclusion, new logic)** — 4 `requires_auction_data=True` → always `branch="real"` evaluated on enabled-date subpanel (empty → `n_dates=0`, never falls to derived); `auction_alpha` → `"real"` if enabled non-empty else `"derived"`; 4 EOD proxies → `"eod"` on full verification window. One branch per strategy per report. Partially analogous to `pool_hub._project_hub` `:140-158` top-level `auction_columns: {real, derived}` server-declared existence (same "server declares column existence" philosophy — copy the declaration shape into the report, but the per-strategy branch is new).

---

### `backend/app/api/research_auction.py` (new — GET `/api/research/auction/validation`)

**Best analog:** `api/auction_history.py` — same GET-only read-only POOL-03 profile; plus `api/research.py` error-code conventions.

**Module docstring 铁律** — copy `auction_history.py:1-17` shape (declares: GET-only; no lake writes; no execution-family imports; no sync/backfill/run_all triggers; violations trip `tests/test_auction_validation.py` AST guard). Must also declare: research-report range is not subject to the backtest 186-day guard (RESEARCH §2.3.1).

**Router + imports** — copy `auction_history.py:29-30` + `research.py:26`:
```python
router = APIRouter(prefix="/api/research", tags=["research"])   # research.py:26 — same prefix, new file
```

**Handler signature** — Query params with `date` typing (FastAPI 422 on bad format, mirror `research.py` Query date behavior in `FactorEvaluationRequest.start/end`); comma-split `strategy_ids`/`symbols`; `start > end` → 400 via `_bad_request` (copy `research.py:48-49`):
```python
def _bad_request(error: Exception) -> HTTPException:             # research.py:48-49, copy verbatim
    return HTTPException(status_code=400, detail={"code": "RESEARCH_VALIDATION", "message": str(error)})
```

**Handler body flow** — copy `auction_history.py` structure (resolve probe once → passthrough; never 404/500; empty states are 200 dicts):
1. `repo = request.app.state.repo` (`:81` pattern; `main.py:129` guarantees it); `engine = request.app.state.strategy_engine` (`main.py:563`).
2. `probe = resolve_auction_probe(); probe_dict = probe.to_dict()` — passthrough only, no gate.
3. `svc = AuctionValidationService(repo, engine)`; `report = svc.build_report(...)`; merge `probe` + `window` echo into response dict (or pass verdict into `build_report` — premarket_pool `probe_resolver` injection is the precedent).
4. Return the assembled dict (200), including honest empty states.

**Guest masking:** NOT carried over — `auction_history` masks guests (`:101-104`, D5); the research endpoints sit behind full auth (`main.py` auth middleware, guest whitelist covers only pool-page GETs). Do not add guest masking; do not touch the whitelist in `main.py`.

---

### `backend/app/main.py` (modify — 1 line)

**Best analog:** self — the include_router block `:848-881`. Insert immediately after `app.include_router(research.router)` (`:856`):
```python
app.include_router(research.router)
app.include_router(research_auction.router)      # Phase 29: 竞价策略历史验证只读报告 (BT-03)
```
(Import `research_auction` alongside the other router imports at top of `main.py`.) No auth-whitelist change (see Guest masking note above).

---

### `backend/tests/test_auction_validation.py` (new — POOL-03 AST guard)

**Best analog:** `test_pool_hub.py:857-963` (canonical guard shapes) + `test_auction_history.py` guard section (tighter single-file variant). Copy verbatim:
```python
_EXECUTION_TOKEN = re.compile(
    r"broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托",
    re.IGNORECASE,
)
_WRITE_PATTERNS = (
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']w"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']wb"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']a"),
    re.compile(r"write_parquet"),
    re.compile(r"os\.replace"),
    re.compile(r"unlink\s*\("),
    re.compile(r"mkdir\s*\("),
)
def _feature_sources() -> tuple[str, str]:      # this phase: api/research_auction.py + services/auction_validation.py
    backend = Path(__file__).resolve().parents[1]
    ...
def _imported_module_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names
```
**Phase-29 extensions** (from RESEARCH §5 BT-06): forbidden import tokens `auction_sync|pool_snapshot|pool_backfill|premarket_snapshot|screener`; forbidden call tokens `run_all|run_preset|write_cache|persist_point_snapshot`; `strategy_cache` reference absence; GET-only (`@router.get` only — copy `test_auction_history_api_is_get_only`); guard-target existence test (`test_validation_modules_exist`, 防守卫悬空). Test list (5 tests) is fully specified in RESEARCH §7.

---

### `backend/tests/test_attach_auction_columns_range.py` (new — primitive unit + equivalence)

**Best analog:** `test_auction_columns.py` — copy hermetic helpers verbatim: `repo_env` fixture `:20-32`, `_available_verdict`, `_patch_probe` (patch target = `app.services.auction_columns.resolve_auction_probe` — but note the range primitive does not consume probe, so probe patching only matters for single-day equivalence comparisons), `_write_auction_partition`, `_auction_rows`.

**New fixture needs** (no existing analog): multi-day enriched panel (symbol/date/open/close/volume/open_gap/… covering consecutive trading days + warmup prefix), written either via `_write_enriched_partition`-style parquet (copy `:266-290`) or seeded directly into `repo._enriched_history_cache`. **Equivalence property test (core, BT-02):** for each enabled day, assert `attach_auction_columns_range` `auction_volume_ratio` is value-identical to single-day `attach_auction_columns` (which internally uses `get_enriched_history` → `tail(5).mean()`) — covering short-history prefix rows (<5 prior trading days). Also: partition-missing day absent from enabled-dates; empty/bad-named partition skipped; multi-window rows deduped to one per symbol (copy `test_partition_multi_row_dedup_no_fanout`); per-symbol absence → null; warmup-present vs warmup-absent prefix behavior; empty lake/empty panel → `(df, [])`; `auction_unmatched_amount` injected only when inputs present (copy `test_attach_derives_unmatched_amount_from_partition_inputs`).

---

### `backend/tests/test_auction_validation_report.py` (new — service + endpoint integration, fixture lake)

**Best analog:** `test_auction_history.py` — copy `_make_client` minimal-app pattern (`:63-76`: `FastAPI()` + stub auth middleware setting `request.state.reviewer_principal` + `app.state.repo = repo` + `app.include_router(router)` + `TestClient`); for Phase 29 also set `app.state.strategy_engine` (real `StrategyEngine` with builtin strategy dirs — `main.py:555-563` shows the construction pattern) and include the new router. Lake seeding: `_write_auction_partition` + `_write_enriched_partition` (from `test_auction_columns.py:266-290`).

Test matrix (fully specified in RESEARCH §7): empty lake → 200 `data_gate=="empty"` + `no_auction_partitions` + 4 real strategies `n_dates==0 branch=="real"` + derived/eod have stats + probe passthrough (BT-01/BT-05); synthetic partitions → per-strategy `n_hits`/`per_date` match hand-built masks (BT-03); BT-04 formula assertions on a fixed 2-day fixture (`next_day_open_ret`/`next_day_close_ret`/`open_gap_outcome`) + a halted-symbol T+1 row missing → `n_missing_outcomes>0`, stats exclude, no zero-fill; BT-05 branch mutual exclusion for `auction_alpha`; empty `strategy_ids` → `strategies: []`; unknown id → `skipped_ids` + 200; `start>end` → 400; over-coverage window → `window.effective_*` clamp; `minute_confirm=="not_applied"` for `auction_intraday_confirm`.

---

## Shared Patterns

### 1. Honest empty state = 200 dict, never 404/500/0-fill
**Sources:** `auction_history.py:_empty_response` `:46-55`; `premarket_pool.py:66-75`; `pool_hub.build_pool_hub` `:314-317`; `get_enriched_range` None semantics (`repository.py:966-998`).
**Apply to:** all new files. Empty lake → `data_gate:"empty"` + `empty_reason`; enriched empty → `"enriched_unavailable"`; no partition day → absent from enabled-dates (never null-as-present).

### 2. Fail-closed masking
**Sources:** `backtest/strategy.py:551-552` (filter exception → false mask); `screener.py:_attach_auction` `:306-314` (injection exception → return df unchanged).
**Apply to:** `_build_candidate_mask` (exception → all-False) and the range primitive (partition read failure → skip that partition, keep others).

### 3. Server-declared column existence
**Sources:** `pool_hub._project_hub` `:140-158` (`auction_columns: {real, derived}`); `attach_auction_columns` `:122-128` keep-list.
**Apply to:** report `strategies[].branch` (real/derived/eod) and `coverage` — the server answers existence, the client derives nothing.

### 4. Probe verdict passthrough
**Source:** `premarket_pool.py:45-57` (injection point + `to_dict()`); `auction_history.py:97-98`.
**Apply to:** `research_auction.py` + service (passthrough, not gate).

### 5. POOL-03 AST guard (zero-execution lock)
**Source:** `test_pool_hub.py:857-963` / `test_auction_history.py` guard section.
**Apply to:** `test_auction_validation.py` — `_EXECUTION_TOKEN` + `_WRITE_PATTERNS` + `_imported_module_names` + GET-only + forbidden import/call tokens (Phase 29 set in RESEARCH §5 BT-06).

### 6. Hermetic test discipline
**Source:** `test_auction_columns.py:20-61` + `test_auction_history.py:30-76` — production imports inside test functions (module level never touches DuckDB singleton), `monkeypatch.setattr(settings, "data_dir", tmp_path/"data")`, probe verdict monkeypatched, lake partitions hand-written to disk.
**Apply to:** all three new test files.

### 7. Strategy enumeration + META-default params
**Source:** `screener.py:745-756`; `engine.py:227-231` (param normalization) + `:229` default dict.
**Apply to:** `AuctionValidationService.build_report` — enumerate from engine (never import builtin modules), params from META defaults only, unknown ids → `skipped_ids`.

### 8. Window/date handling
**Sources:** `api/backtest.py:_resolve_start` `:50-56` (`end - timedelta(days=default_days)` — Phase 29 default `start = end − 120 自然日`); `pool_hub.py:319-321` authority echo; in-handler 400 for out-of-range params (`auction_history.py:90-94`).
**Apply to:** `research_auction.py`/service window parse + clamp + `window.requested_*/effective_*` echo.

---

## No Analog Found (planner: use RESEARCH.md design, these are new patterns)

| File / Concern | Reason |
|----------------|--------|
| Vectorized multi-day `auction_volume_ratio` (`shift(1).rolling_mean(5, min_periods=1).over("symbol")`) | Only single-day `get_enriched_history`-based denominator exists (`auction_columns.py:54-87`); the vectorized form and its per-day equivalence must be proven by the new property test (BT-02). |
| Forward-stat aggregation (`next_day_open_ret`/`next_day_close_ret`/`open_gap_outcome`, mean/median/win_rate/n, `n_missing_outcomes`) | No existing forward-return aggregator in the service layer (research `evaluation` module does factor-level returns but is not importable per BT-06 whitelist). Global trading-calendar next-date mapping (`next_map`) is also new — never `shift(-1)` per-symbol (BT-04). |
| Branch mutual-exclusion labeling (real/derived/eod per strategy) | Partial analog only: `pool_hub._project_hub:140-158` declares real/derived *column existence*; per-strategy branch selection + `minute_confirm:"not_applied"` is new (BT-05). |
| `_AUCTION_FAMILY_IDS` hardcoded 9-id set + `skipped_ids` semantics | No existing family-set pattern; nearest is `PRESET_STRATEGIES` filtering in `run_all_with_hits` (`screener.py:745-751`). |
| `per_date` per-day hit counts with `n_screened` | No existing daily histogram of strategy hits; nearest is `per_date`-style aggregation in `pool_snapshot` backfill gaps (not importable — BT-06). |

---

## Metadata

**Analog search scope:** `backend/app/services/` (auction_columns, auction_probe, screener, pool_hub, premarket_pool), `backend/app/api/` (auction_history, research, backtest), `backend/app/backtest/strategy.py`, `backend/app/strategy/engine.py`, `backend/app/tickflow/repository.py`, `backend/app/main.py`, `backend/tests/` (test_pool_hub, test_auction_history, test_auction_columns)
**Files scanned:** 15 (all anchors in RESEARCH.md §8 re-verified by direct read, 2026-08-06)
**Pattern extraction date:** 2026-08-06
**Off-limits:** `frontend/src/pages/Watchlist.tsx` (not read, not claimed); `backtest/` seam untouched (frozen panel/`_load_panel_inner` NOT modified — BT-07 deferred)
