# Phase 31: 竞价复盘 (REV-01..05) - Pattern Map

**Mapped:** 2026-08-06
**Files analyzed:** 12 (6 production + 4 tests + 1 router registration + 1 frontend)
**Analogs found:** 11 / 12 (1 gap: market_recap has zero existing tests)

All line anchors below were verified against current HEAD (Phase 30 complete).
Watchlist.tsx is OFF-LIMITS — no analog is drawn from it.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/services/auction_recap.py` (new) | service | read-only aggregation (lake/preview/enriched → dict) | `services/premarket_pool.py` (probe injection + honest payload) + `services/auction_validation.py` (family IDs + null-not-0 metrics) | exact (assembly) / role-match (injection) |
| `render_auction_recap_markdown` (in new service) | utility | transform (dict → markdown) | `services/market_recap.py` `_build_*_block` + `_build_user_prompt` (parts/join pattern) | partial (bullets exist; no markdown table precedent) |
| `recap_market_stream` delta insertion | service | request-response (NDJSON streaming) | `services/market_recap.py:253-356` (itself, in-place change) | exact (self) |
| `_build_user_prompt` optional `auction_slice` param | service | transform | `services/market_recap.py:177-227` (itself) + news/focus conditional-append pattern | exact (self) |
| `backend/app/services/preferences.py` default 15:40 | config | config read/write | `services/preferences.py:433-457` (itself) + `get_pipeline_schedule` :329-342 | exact (self) |
| `backend/app/api/settings.py` PUT recap-auction-commentary | config API | request-response | `api/settings.py:1467-1477` (update_review_push, no-job variant) + `:1425-1465` (job variant) | exact |
| `backend/app/api/market_recap_auction.py` (new) | controller | request-response (GET-only read) | `api/auction_history.py` (read-only module) + `api/pool.py:99-131` (as_of validation + guest path) | exact |
| `backend/app/main.py` router registration | config | — | `main.py:871-872` (`research_auction.router` precedent) | exact |
| `frontend/src/pages/Review.tsx:105` fallback literal | component | — | `Review.tsx:105` (itself, 1-line literal) | exact (self) |
| `backend/tests/test_auction_recap.py` (new) | test | fixture-driven unit | `tests/test_attach_auction_columns_range.py:24-47` (repo_env/_write_auction_partition) + `tests/test_premarket_pool.py` (probe 3-state) | exact |
| `backend/tests/test_auction_recap_guard.py` (new) | test | AST guard | `tests/test_auction_validation.py` (6 guards) | exact |
| `backend/tests/test_market_recap_delta.py` (new) | test | integration (stream events) | **none** — no market_recap/review tests exist (grep-verified); borrow `test_premarket_pool.py` job-grep + TestClient patterns | gap |
| `backend/tests/test_auction_recap_endpoint.py` (new) | test | API test (TestClient) | `tests/test_auction_history.py:79-92` (guest/vip stub middleware) | exact |

## Pattern Assignments

### `backend/app/services/auction_recap.py` (service, read-only aggregation)

**Analog A: `services/premarket_pool.py`** (probe injection + honest payload shape)

**Signature/injection pattern** (`premarket_pool.py:32-51`):
```python
def build_premarket_preview(
    repo,
    engine=None,
    *,
    as_of: date | None = None,
    probe_resolver=None,
) -> dict:
    as_of = as_of or cn_today()
    probe_resolver = probe_resolver or resolve_auction_probe
```
→ `build_auction_recap(repo, as_of, engine=None, *, probe_resolver=None, now=None)` copies this exact kwarg-only injection shape; `now` freezes `cn_today()` for `pre_eod` tests (mirror `test_auction_probe.py` three-state fixtures).

**Honest empty payload** (`premarket_pool.py:53-74`):
```python
if not results:
    return {
        "as_of": str(as_of), "available": False, "degraded": True,
        "window": "pre_open", "probe": verdict, "results": {},
    }
```
→ Block absence = key omitted + explicit `note`; `data_completeness` head label; never 0-fill. Same vocabulary (`provisional`/`degraded`/`probe`).

**Analog B: `services/auction_validation.py`** (family IDs single source + honest metrics)

**Family filter** (`auction_validation.py:44-52`) — import, never re-declare:
```python
_AUCTION_FAMILY_IDS = frozenset({
    "auction_fast_grab", "auction_allround", "t1_flash", "auction_intraday_confirm",
    "auction_alpha", "golden_230", "auction_bullish", "auction_preopen_quant",
    "auction_early_star",
})
```
`from app.services.auction_validation import _AUCTION_FAMILY_IDS` — single source of truth, zero drift (REV-03).

**Null-not-zero metric** (`auction_validation.py:67-75`):
```python
def _null_metric() -> dict:
    """无有效行的指标聚合 (诚实 null, 绝不 0 填)。"""
    return {"mean": None, "median": None, "win_rate": None, "n": 0}
```
→ Signal-quality stats use this shape; `n_missing` mirrors Phase 29 semantics.

**Analog C: data-assembly consumers (zero-write reads)**
- Partition gate + dedup: `auction_columns.py:95-121` (probe×partition double gate for `as_of==today`), `:146` (`unique(subset=["symbol"], keep="last")`); historical gate = partition existence per `attach_auction_columns_range` (research R5). Partition path: `repo.store.data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"` (`auction_columns.py:107`).
- Enriched frame: `screener.py:245-280` `ScreenerService._load_enriched_for_date` — cross-service private call has precedent (`market_overview_builder.py:412`); `open_gap`/`change_pct` computed at read time, never expected as parquet columns.
- Display names: `screener.py:205-216` `_strategy_display_name(engine, sid)` (unknown id → sid, never 500).
- Preview load: `premarket_snapshot.py:61-88` `load_premarket_snapshot(data_dir, as_of)` → None on missing/invalid (does not raise).

**Error handling**: fail-closed per block — missing source → block omitted + note; no exceptions propagate (mirror `premarket_snapshot.py:81-88` try/except → None and `_strategy_display_name` try/except → sid).

### `render_auction_recap_markdown` + `build_auction_slice` (utility, pure functions)

**Analog: `services/market_recap.py` block builders**

**Parts/join pattern** (`market_recap.py:159-175` — `_build_emotion_block`):
```python
def _build_emotion_block(overview: dict) -> str:
    emo = overview.get("emotion") or {}
    score = emo.get("score", "—")
    label = emo.get("label", "—")
    lines = [f"- 情绪温度: {score} ({label})"]
    if radar:
        dims = "、".join(f"{r.get('label')}{r.get('value',0)}" for r in radar)
        lines.append(f"- 六维雷达: {dims}")
    return "\n".join(lines)
```
→ Same `lines: list[str]` + `"\n".join(lines)` style; markdown table for signal quality is new (no precedent — planner notes it; `MarkdownRenderer` in Review.tsx:721-725 renders tables, so it is safe).
- Pure function: dict in → str out (no repo access) so service is unit-testable and slice/panel stay single-source (REV-04 acceptance 6).
- Section separator `---` + `## 📊 竞价复盘(确定性数据,非 AI 生成)` matches existing markdown headers rendered by Review.tsx.

### `recap_market_stream` panel-delta insertion (service, NDJSON streaming)

**Analog: itself** — `services/market_recap.py:253-356`

**Event order contract** (`:285-354`):
```python
    # 2. meta 事件(前端据此先渲染信号灯/看板)
    yield json.dumps({"type": "meta", "as_of": as_of_str, ...}, ensure_ascii=False)

    # 3+4. 构建 prompt + 流式调用 LLM(整体 try-except,任何异常 yield error,避免前端卡死)
    try:
        from app.services.ai_provider import stream_ai_text
        user_prompt = _build_user_prompt(overview, news or [], focus)
        async for delta in stream_ai_text([...], temperature=0.5, max_tokens=4500):
            yield json.dumps({"type": "delta", "content": delta}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        logger.exception("AI market recap failed for %s: %s", as_of_str, e)
        yield json.dumps({"type": "error", "message": f"AI 复盘失败: {e}"}, ensure_ascii=False)
        return

    yield json.dumps({"type": "done"}, ensure_ascii=False)
```
→ Insert panel delta BETWEEN the try/except and the `done` yield:
```python
    if panel 存在任何 present 块:
        yield json.dumps({"type": "delta", "content": render_auction_recap_markdown(panel)}, ensure_ascii=False)
    yield json.dumps({"type": "done"}, ensure_ascii=False)
```
AI-failure path (`error` + `return`, no panel fallback) stays untouched (R8). `as_of` single source: `overview.get("as_of")` at `:295-298` — pass the parsed string into `build_auction_recap`, never re-resolve.

### `_build_user_prompt` optional `auction_slice` param (transform)

**Analog: itself** — `market_recap.py:177-227`

**Conditional-append pattern** (news section, `:207-217`):
```python
    if news:
        news_lines = []
        for i, n in enumerate(news[:8], 1):
            ...
        parts.extend(["", "## 近期市场新闻", "\n".join(news_lines)])
    else:
        parts.extend(["", "## 近期市场新闻", "(暂无新闻数据:外部新闻源不可用。...)"])
```
→ Change signature to `def _build_user_prompt(overview, news, focus, auction_slice: str | None = None)` and append:
```python
    if auction_slice:
        parts.extend(["", "## 竞价复盘数据(确定性切片)", auction_slice])
```
Existing call site `market_recap.py:313` (`_build_user_prompt(overview, news or [], focus)`) compiles unchanged — default None keeps output byte-identical (R9). Guardrail line appends to a *local* system string, `_SYSTEM_PROMPT` constant untouched.

### `preferences.get_review_schedule` default 15:40 (config)

**Analog: itself** — `preferences.py:433-457`

**Get/set pattern with floor clamp** (`:433-457`):
```python
def get_review_schedule() -> dict:
    d = load().get("review_schedule", {"enabled": False, "hour": 15, "minute": 10})
    return {"enabled": bool(d.get("enabled", False)), "hour": d.get("hour", 15), "minute": d.get("minute", 10)}

def set_review_schedule(enabled: bool, hour: int, minute: int) -> dict:
    h = max(0, min(23, hour)); m = max(0, min(59, minute))
    if h * 60 + m < 15 * 60:
        h, m = 15, 0
    save({"review_schedule": {"enabled": bool(enabled), "hour": h, "minute": m}})
    return {"enabled": bool(enabled), "hour": h, "minute": m}
```
→ Change default dict `minute: 10 → 40` **in both** the `load().get(..., default)` literal and the `.get("minute", 10)` fallback; update docstring with timing rationale (竞价同步 15:30 + 股池持久化 15:35). Do NOT touch the 15:00 floor in `set_review_schedule`. `load().get("review_schedule", default)` semantics auto-preserve saved user values (backward compat).

**New `recap_auction_commentary` pref** — copy `get_review_push_channels` shape (`:460-473`): whitelist constant + `load().get(key, default)`; setter mirrors `set_review_schedule` minus clamp.

### `api/settings.py` PUT `/preferences/recap-auction-commentary` (config API)

**Analog A (no-job variant): `update_review_push`** — `settings.py:1467-1477`:
```python
class ReviewPushIn(BaseModel):
    channels: list[str]

@router.put("/preferences/review-push")
def update_review_push(req: ReviewPushIn) -> dict:
    from app.services import preferences
    saved = preferences.set_review_push_channels(req.channels)
    return {"review_push_channels": saved}
```
→ New endpoint is this exact shape (Pydantic in-model, local `from app.services import preferences` import, return saved value).

**Analog B (job variant, if commentary ever gates scheduling): `update_review_schedule`** — `settings.py:1425-1465` (AI-key 400 guard at `:1433-1438`, `scheduler = getattr(request.app.state, "scheduler", None)` dynamic job ops).

**GET /preferences passthrough** — add `"recap_auction_commentary": preferences.get_recap_auction_commentary()` to the dict at `settings.py:371-422` (backend default auto-propagates to frontend, no frontend switch needed — P2 API-first).

### `api/market_recap_auction.py` REV-05 endpoint (controller, GET-only)

**Analog A: `api/auction_history.py`** (read-only module contract)

**Module skeleton + honesty contract** (`auction_history.py:1-30`):
```python
"""竞价历史只读聚合 API (CHART-01)。

只读 ``GET ...`` (POOL-03: 零执行权限) ... 本模块只暴露 GET 端点: 不写湖、不触发
同步/回填、不持久化任何计算、不 import 任何执行族模块。

空湖/该 symbol 无行 → 诚实 200 ``available:false`` 空态 (绝不 404/500/0 填充);
probe 非 available → 空态 + ``probe.status`` 透传; guest 会话 → 掩码空态 ...
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Query, Request
router = APIRouter(prefix="/api/kline/auction", tags=["kline"])
```
→ New module: `APIRouter(prefix="/api/market-recap", tags=["market-recap"])`, GET-only `@router.get("/auction")`, module docstring restates the 铁律. Do NOT add the GET to existing `api/market_recap.py` (has POST/DELETE → GET-only guard assertion would break; separate module keeps the guard whole-module).

**Analog B: `api/pool.py:99-131`** (as_of double validation + guest path)

**Strict as_of validation** (`pool.py:99-107`):
```python
    if as_of is not None:
        if not _AS_OF_RE.fullmatch(as_of):
            raise HTTPException(status_code=400, detail="invalid as_of")
        try:
            date_type.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid as_of")
```
(`_AS_OF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")` — anti path-traversal.)

**Guest masking** (`pool.py:127-131`):
```python
    is_vip = getattr(request.state, "reviewer_principal", None) is not None
    hub["mode"] = "vip" if is_vip else "guest"
    if not is_vip:
        hub = mask_guest_hub(hub)
```
→ For the recap endpoint: `mask_guest_alert` semantics (guest_masking.py) — strip per-symbol identity (`symbol/name/code → "******"` via `MASKED_IDENTITY`), strip auction values + `open_gap` + `probe`; KEEP aggregates (counts/ratios) + status annotations (`provisional/degraded/data_completeness`). `_GUEST_ALERT_VISIBLE` frozenset (`guest_masking.py:22-31`) is the whitelist model. Exact guest DTO field list is R12 — locked at plan/implementation time.

**Empty state** — 200 `{"available": false, "data_completeness": ..., "blocks": {}, "reason": ...}` mirroring `auction_history.py` `_empty_response` + `pool.py:139-152` premarket empty payload (never 404/500/0-fill).

**Display name closure** (`pool.py:118-120`):
```python
    def name_for(sid: str) -> str:
        return _strategy_display_name(engine, sid)
```

### `backend/app/main.py` router registration (config)

**Analog: `main.py:871-872`**:
```python
# BT-03 竞价策略历史验证只读报告 (POOL-03 零执行)
app.include_router(research_auction.router)
```
→ After `market_recap.router` include (`:886`), add with a same-style comment: `app.include_router(market_recap_auction.router)`.

### `frontend/src/pages/Review.tsx:105` fallback literal (component, 1 line)

**Analog: itself** — `Review.tsx:105`:
```tsx
  const reviewSched = prefs.data?.review_schedule ?? { enabled: false, hour: 15, minute: 10 }
```
→ Change `minute: 10` → `minute: 40`. This literal is the ONLY frontend touch; `usePreferences()` (`:104`) reads the backend default via GET /preferences, so the fallback only matters when prefs fetch fails. Do NOT touch Watchlist.tsx. Optional P2 commentary toggle is skipped (API-first).

### `backend/tests/test_auction_recap.py` (unit tests)

**Analog: `tests/test_attach_auction_columns_range.py:24-47`** (hermetic write fixtures):
```python
@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_auction_columns.py:20-32)。"""
    ...  # yields (repo, data_dir); store.db.close() at teardown

def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    """手工写盘 kline_auction/date=YYYY-MM-DD/part.parquet (镜像 :54-58)。"""
    ...
    rows.write_parquet(out)
```
→ Add `_write_premarket_preview` (canned 3-strategy payload via `persist_premarket_snapshot`, mirror `test_premarket_pool._write_premarket_preview`) + EOD enriched write + probe three-state monkeypatch (`test_premarket_pool.py` `_fake_verdict` / `_patch_probe` shape) + frozen `now` injection. Hand-computed assertions style: `test_attach_auction_columns_range.py::test_range_warmup_contract_full_denominator` (pytest.approx hand math). Window-predicate regression fixture writes a 09:31 row variant (09:30+ never enters auction columns).

### `backend/tests/test_auction_recap_guard.py` (POOL-03 AST guard)

**Analog: `tests/test_auction_validation.py`** (6 guards — copy structure, re-tune whitelist per §7.2):

| Guard (function name) | REV-31 change |
|---|---|
| `test_validation_modules_exist` | targets `api/market_recap_auction.py` + `services/auction_recap.py`; assert non-empty |
| `test_validation_no_execution_imports` | `_EXECUTION_TOKEN` unchanged; **`_FORBIDDEN_IMPORT_TOKEN` drops `premarket_snapshot\|screener`** (REV must import both) → `auction_sync\|pool_snapshot\|pool_backfill` |
| `test_validation_api_is_get_only` | apply only to the new api module |
| `test_validation_no_write_path` | `_WRITE_PATTERNS` copied verbatim |
| `test_validation_no_strategy_cache_reference` | `write_cache` forbidden; **add `save_report`** to `_FORBIDDEN_CALL_TOKENS` (research §7.2) |
| `test_validation_import_whitelist` | `_IMPORT_PREFIXES` includes `app.services.auction_probe, auction_columns, auction_validation, premarket_snapshot, screener, auction_recap, guest_masking, app.tickflow.repository, app.strategy.engine, app.market_time`; `_IMPORT_EXACT` = stdlib + polars + fastapi |

Helper functions to copy: `_feature_sources()`, `_imported_module_names()` (AST), token regexes (mirror `test_pool_hub.py:858-889`).

### `backend/tests/test_market_recap_delta.py` (integration) — GAP

No direct analog: zero existing market_recap/review tests (grep-verified, RESEARCH §0). Borrow:
- `monkeypatch.setattr` on `app.services.market_recap.stream_ai_text` with a fake async generator (fake stream) — the `_patch_probe` monkeypatch idiom from `test_attach_auction_columns_range.py` generalizes to any injected callable.
- Job/preference assertions: `test_premarket_pool.py::test_premarket_job_registered_in_scheduler` (registration-shape grep gate) pattern for the 15:40 default + saved-preference-preserved + 15:00 floor tests.
- Archive assertion: JsonReportStore pointed at `tmp_path` (mirror how `test_premarket_pool.py` uses `tmp_path` for storage isolation — `test_premarket_preview_never_touches_eod_store`).
- Webhook fixture: nearest precedent is Feishu/WeCom push tests elsewhere in the suite (research cites "webhook fixture 镜像既有推送测试") — planner must locate exact webhook test module at execution time.
- `recap_market_once` accumulation + event-order assertions are new territory (contract lock for REV-04 acceptance 1-6).

### `backend/tests/test_auction_recap_endpoint.py` (API tests)

**Analog: `tests/test_auction_history.py:79-92`** (stub auth middleware):
```python
def _make_client(repo) -> TestClient:
    """最小 FastAPI 应用 + stub 中间件: cookie ``tf_session == "vip-token"`` → 设
    ``reviewer_principal``, 否则不设 (guest)。"""
    app = FastAPI()
    app.state.repo = repo
    @app.middleware("http")
    async def _stub_auth(request: Request, call_next):
        if request.cookies.get("tf_session") == "vip-token":
            request.state.reviewer_principal = "reviewer_test"
        return await call_next(request)
    app.include_router(auction_history_api.router)
    return TestClient(app)
```
→ Same `_make_client` for `market_recap_auction.router`; assert 200 empty state (available:false), as_of 400, guest masking vs vip (mirror `test_auction_history.py::test_empty_lake_returns_available_false` + `test_premarket_pool.py::test_premarket_api_guest_mask`).

## Shared Patterns

### Honest empty state (200 available:false, never 404/500/0-fill)
**Sources:** `auction_history.py` `_empty_response`, `pool.py:139-152`, `premarket_snapshot.py:61-88`, `premarket_pool.py:53-58`
**Apply to:** `auction_recap.py` blocks + REV-05 endpoint. Missing source → block omitted + explicit note; never fake zeros.

### POOL-03 read-only enforcement (AST guards)
**Source:** `test_pool_hub.py:858-963` → specialized by `test_auction_validation.py`
**Apply to:** `auction_recap.py` + `api/market_recap_auction.py` via new `test_auction_recap_guard.py`. REV whitelist deliberately differs from Phase 29 (screener/premarket_snapshot now importable; `save_report` added to forbidden calls).

### Probe verdict provenance passthrough
**Source:** `premarket_pool.py:47-56` + `auction_validation.py:79-82` (injection: `probe_resolver or resolve_auction_probe`)
**Apply to:** all three blocks (historical as_of: probe is provenance only, partition existence is the gate — `attach_auction_columns_range` semantics).

### Null-not-zero metrics
**Source:** `auction_validation.py:67-75` (`_null_metric`), `screener.py:199-204` (`_json_safe` NaN→None)
**Apply to:** signal-quality stats, `n_missing`, JSON serializability of the recap dict.

### Preference get/set pattern
**Source:** `preferences.py:329-342, 433-457, 460-473` + `settings.py:371-422, 1467-1477`
**Apply to:** review_schedule default 15:40 + new `recap_auction_commentary` pref + PUT endpoint. `load().get(key, default)` = backward compat for saved values.

### Backward-compatible optional parameters
**Source:** `_build_user_prompt` (market_recap.py:177) gets `auction_slice: str | None = None`; existing call site `:313` unchanged.
**Apply to:** prompt signature (R9); same discipline for any new kwarg (e.g. `now` in `build_auction_recap`).

## No Analog Found

| File | Role | Data Flow | Reason / Fallback |
|------|------|-----------|-------------------|
| `backend/tests/test_market_recap_delta.py` | test | integration (NDJSON event order, archive, webhook) | No market_recap/review tests exist anywhere (grep `market_recap\|recap_market_stream\|ai_market_recaps\|review_schedule\|push_review_event` = zero hits). Assemble from `test_premarket_pool.py` (job grep, tmp storage) + `test_attach_auction_columns_range.py` (monkeypatch) + existing Feishu/WeCom webhook tests (locate at execution) |
| `render_auction_recap_markdown` markdown **table** | utility | transform | No service in the repo renders a markdown table today; `_build_*_block` helpers only emit bullet lists. Table is safe because `MarkdownRenderer` (Review.tsx:721-725) renders tables; planner must specify the table layout in PLAN.md |
| `build_auction_slice` (LLM slice from panel dict) | utility | transform | Same bullet-list join pattern as `_build_*_block`; the "single-source slice + guardrail line" contract is new (REV-04 acceptance 6) |

## Metadata

**Analog search scope:** `backend/app/services/{market_recap,auction_validation,premarket_pool,premarket_snapshot,auction_columns,screener,preferences,guest_masking}.py`, `backend/app/api/{market_recap,auction_history,pool,settings}.py`, `backend/app/main.py`, `frontend/src/pages/Review.tsx`, `backend/tests/{test_auction_validation,test_attach_auction_columns_range,test_premarket_pool,test_auction_history}.py`
**Files scanned:** 15 production/test files + Review.tsx (all line-anchored)
**Pattern extraction date:** 2026-08-06
**Verification:** all cited line anchors read directly at current HEAD; no source files modified; Watchlist.tsx untouched.
