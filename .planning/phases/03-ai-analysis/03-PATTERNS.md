# Phase 03: AI Analysis - Pattern Map

**Mapped:** 2026-07-11  
**Files analyzed:** 31 planned new/modified files  
**Analogs found:** 29 / 31

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/pyproject.toml` | config | transform | `backend/pyproject.toml` | exact |
| `backend/uv.lock` | config | transform | `backend/uv.lock` | exact |
| `backend/app/operational/migrations.py` | migration | CRUD | `backend/app/operational/migrations.py` | exact |
| `backend/app/analysis/__init__.py` | config | request-response | `backend/app/research/__init__.py` | role-match |
| `backend/app/analysis/schemas.py` | model | transform | `backend/app/decision/ai_review.py` | partial-match |
| `backend/app/analysis/evidence.py` | service | transform | `backend/app/services/stock_analyzer.py` | role-match |
| `backend/app/analysis/model_adapter.py` | service | request-response | `backend/app/decision/ai_review.py` | exact |
| `backend/app/analysis/graph.py` | service | event-driven | None: fixed LangGraph graph is new | none |
| `backend/app/analysis/repository.py` | repository | CRUD | `backend/app/research/repository.py` | exact |
| `backend/app/analysis/lifecycle.py` | service | event-driven | `backend/app/decision/ai_review.py` | role-match |
| `backend/app/analysis/service.py` | service | request-response | `backend/app/decision/ai_review.py` | role-match |
| `backend/app/analysis/api.py` | route | request-response | `backend/app/api/portfolio.py` | exact |
| `backend/app/main.py` | config | app-lifecycle | `backend/app/main.py` | exact |
| `backend/app/services/quote_service.py` | service | pub-sub | `backend/app/services/quote_service.py` | exact |
| `backend/app/api/intraday.py` | route | streaming | `backend/app/api/intraday.py` | exact |
| `frontend/src/lib/api.ts` | utility | request-response | `frontend/src/lib/api.ts` | exact |
| `frontend/src/lib/queryKeys.ts` | utility | request-response | `frontend/src/lib/queryKeys.ts` | exact |
| `frontend/src/lib/useQuoteStream.ts` | hook | pub-sub | `frontend/src/lib/useQuoteStream.ts` | exact |
| `frontend/src/components/analysis/AnalysisWorkspace.tsx` | component | request-response | `frontend/src/pages/Portfolio.tsx` | role-match |
| `frontend/src/components/analysis/ReportPanel.tsx` | component | transform | `frontend/src/components/financials/AiAnalysisDialog.tsx` | partial-match |
| `frontend/src/components/analysis/EvidencePanel.tsx` | component | request-response | `frontend/src/components/financials/ReportHistoryPanel.tsx` | role-match |
| `frontend/src/components/analysis/LifecyclePanel.tsx` | component | CRUD | `frontend/src/pages/Portfolio.tsx` | role-match |
| `frontend/src/components/analysis/AnalysisStatus.tsx` | component | streaming | `frontend/src/lib/useQuoteStream.ts` | role-match |
| `frontend/src/pages/StockAnalysis.tsx` | component/page | request-response | `frontend/src/pages/StockAnalysis.tsx` | exact |
| `frontend/src/pages/Portfolio.tsx` | component/page | request-response | `frontend/src/pages/Portfolio.tsx` | exact |
| `frontend/src/components/financials/AiAnalysisHost.tsx` | component/host | request-response | `frontend/src/components/financials/AiAnalysisHost.tsx` | exact |
| `backend/tests/test_analysis_evidence.py` | test | transform | `backend/tests/test_decision_ai_review.py` | role-match |
| `backend/tests/test_analysis_graph.py` | test | event-driven | `backend/tests/test_decision_ai_review.py` | partial-match |
| `backend/tests/test_analysis_service.py` | test | request-response | `backend/tests/test_decision_ai_review.py` | exact |
| `backend/tests/test_analysis_lifecycle.py` and `backend/tests/test_analysis_api.py` | test | CRUD/request-response | `backend/tests/test_portfolio_api.py` | exact |
| `frontend/e2e/phase3-ai-analysis.spec.ts` | test | request-response | `frontend/e2e/phase2-research.spec.ts` | exact |

## Pattern Assignments

### `backend/app/analysis/schemas.py` (model, transform)

**Analog:** `backend/app/decision/ai_review.py`

Use a strict, server-defined model boundary. The old report request schemas in `api/financials.py` and `api/stock_analysis.py` are intentionally not an authority source because they accept browser-owned report content.

**Imports and protocol seam** ([`ai_review.py`](/root/source/AthenaQuant/backend/app/decision/ai_review.py:4), lines 4-24):
```python
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

Message = dict[str, str]
GenerateText = Callable[..., Awaitable[str]]

class AIReviewGateway(Protocol):
    provider: str
    model: str

    async def propose(self, baseline: dict[str, Any]) -> dict[str, Any]: ...
```

**Fail-closed shape validation** ([`ai_review.py`](/root/source/AthenaQuant/backend/app/decision/ai_review.py:37), lines 37-57):
```python
if not isinstance(value, dict) or set(value) != {"adjustments"}:
    raise ValueError("review response must contain only adjustments")
...
if not isinstance(adjustment, dict) or set(adjustment) != {"field", "value", "rationale"}:
    raise ValueError("review adjustment has an invalid shape")
```

**Required adaptation:** Define `GeneratedAnalysis` with `ConfigDict(extra="forbid")`, bounded fields and Pydantic validators from AI-SPEC. Define a distinct `AnalysisReport` envelope that adds server-owned source records, cross-check states, lifecycle snapshot, report/run metadata, and citation whitelist validation. Do not put grade, cross-check result, lifecycle state, provider URL/key, or reviewer identity in the run request or generated-body schema.

---

### `backend/app/analysis/model_adapter.py` (service, request-response)

**Analog:** `backend/app/decision/ai_review.py`

**Configuration and injectable offline transport** ([`ai_review.py`](/root/source/AthenaQuant/backend/app/decision/ai_review.py:80), lines 80-111):
```python
class ConfiguredAIReviewGateway:
    def __init__(self, *, provider: str | None = None, model: str | None = None,
                 generate_text: GenerateText | None = None) -> None:
        self.provider = provider or ai_provider.current_ai_provider()
        self.model = model or ai_provider.current_ai_model()
        self._generate_text = generate_text or ai_provider.generate_ai_text

    async def propose(self, baseline: dict[str, Any]) -> dict[str, Any]:
        raw = await self._generate_text(_review_messages(baseline), temperature=0,
                                        max_tokens=600, timeout=30)
        try:
            return _typed_proposal(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("configured review returned malformed output") from error
```

**Provider access and sanitized transport error behavior** ([`ai_provider.py`](/root/source/AthenaQuant/backend/app/services/ai_provider.py:100), lines 100-115; [`ai_provider.py`](/root/source/AthenaQuant/backend/app/services/ai_provider.py:150), lines 150-168):
```python
async def generate_ai_text(messages: Sequence[Message], *, temperature: float = 0.3,
                           max_tokens: int = 3000, timeout: float = 180.0) -> str:
    if is_codex_cli_provider():
        return await _run_codex_cli(messages, max_tokens=max_tokens, timeout=max(timeout, 600.0))
    return await _run_openai_once(messages, temperature=temperature,
                                  max_tokens=max_tokens, timeout=timeout)
```

**Required adaptation:** accept only server-built messages and call `GeneratedAnalysis.model_validate_json(raw)` before returning. Keep provider/model metadata, injected async transport, `temperature=0`, explicit timeout/token cap, and sanitized `RuntimeError` behavior. Do not use `stream_ai_text`, prompt caller data directly, or fall back to unvalidated Markdown.

---

### `backend/app/analysis/evidence.py` (service, transform)

**Analog:** `backend/app/services/stock_analyzer.py`

**Governed data read and empty-data handling** ([`stock_analyzer.py`](/root/source/AthenaQuant/backend/app/services/stock_analyzer.py:39), lines 39-52):
```python
def _load_kline(repo, symbol: str) -> pl.DataFrame:
    end = date.today()
    start = end - timedelta(days=_KLINE_WINDOW * 2)
    df = repo.get_daily_asset(repo.resolve_asset_type(symbol), symbol, start, end)
    if df.is_empty():
        return df
    return df.tail(_KLINE_WINDOW)
```

**Deterministic JSON-safe value normalization** ([`stock_analyzer.py`](/root/source/AthenaQuant/backend/app/services/stock_analyzer.py:55), lines 55-76):
```python
for rec in sub.to_dicts():
    clean = {}
    for k, v in rec.items():
        if isinstance(v, float):
            clean[k] = None if not math.isfinite(v) else round(v, 4)
        elif isinstance(v, (datetime.date, datetime.datetime)):
            clean[k] = v.isoformat()
        else:
            clean[k] = v
    rows.append(clean)
```

**Financial source reader** ([`api/financials.py`](/root/source/AthenaQuant/backend/app/api/financials.py:73), lines 73-84):
```python
df = get_financial_df(request.app.state.repo.store.data_dir, "metrics")
if df.is_empty():
    return {"data": []}
if symbol:
    df = df.filter(pl.col("symbol") == symbol)
return {"data": df.to_dicts()}
```

**Required adaptation:** read market inputs only from `request.app.state.repo` / governed financial readers, build an immutable Pydantic `FrozenEvidenceSnapshot`, then deterministically assign source grade, independence group, normalized period/unit/definition and cross-check state. Return `context_insufficient`, `unresolved`, or `conflicting` rather than inventing a result. The browser supplies only bounded subject/focus identifiers, never evidence records or material-number verdicts.

---

### `backend/app/analysis/repository.py` (repository, CRUD)

**Analog:** `backend/app/research/repository.py`

**Short-lived, parameterized SQLite connections** ([`research/repository.py`](/root/source/AthenaQuant/backend/app/research/repository.py:45), lines 45-64):
```python
class ResearchRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()
```

**Atomic immutable aggregate insert** ([`research/repository.py`](/root/source/AthenaQuant/backend/app/research/repository.py:248), lines 248-315):
```python
with self._connection() as connection, connection:
    connection.execute("""INSERT INTO research_experiments (...) VALUES (...)""", (...))
    connection.execute("""INSERT INTO research_experiment_metrics (...) VALUES (?, ?, ?)""",
                       (experiment_id, _json(dict(metrics), "metrics"), now))
    for artifact in artifacts:
        connection.execute("""INSERT INTO research_experiment_artifacts (...) VALUES (...)""", (...))
```

**Immutable guard example** ([`operational/repository.py`](/root/source/AthenaQuant/backend/app/operational/repository.py:589), lines 589-592):
```python
def replace_decision_baseline(self, run_id: str, snapshot: Mapping[str, Any]) -> None:
    del run_id, snapshot
    raise ValueError("decision baseline is immutable")
```

**Required adaptation:** create a separate `AnalysisRepository` over the same `operational.db`, not a new data store. Persist only frozen snapshots, source/number observations, validated report versions, failed-run audit metadata, reviews/events/plans/outcomes. Use one transaction for active-run acquisition and one transaction for confirmation plus one observation-plan insert. Never expose update/delete methods for reports, evidence, events, plans, or outcomes.

---

### `backend/app/operational/migrations.py` (migration, CRUD)

**Analog:** same file.

**Append one ordered migration and let `user_version` make it idempotent** ([`migrations.py`](/root/source/AthenaQuant/backend/app/operational/migrations.py:7), lines 7-43; [`migrations.py`](/root/source/AthenaQuant/backend/app/operational/migrations.py:235), lines 235-245):
```python
MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE accounts (...);
    CREATE TABLE positions (...);
    CREATE INDEX idx_positions_account_id ON positions(account_id);
    """,
    ...
)

for version, migration in enumerate(MIGRATIONS[current_version:], start=current_version + 1):
    with connection:
        connection.executescript(migration)
        connection.execute(f"PRAGMA user_version = {version}")
```

Add all `analysis_*` tables, constraints, and lookup indexes in one final migration. Prefer foreign keys with `ON DELETE RESTRICT`; no cascade may erase immutable audit records. Add a partial unique index or equivalent database constraint for one queued/running subject run, not only an in-memory lock.

---

### `backend/app/analysis/graph.py` (service, event-driven)

**Analog:** No close code analog. The nearest safe AI boundary is `backend/app/decision/ai_review.py`, but it does not use a workflow graph.

**Binding implementation source:** AI-SPEC lines 128-162 and 204-242. Implement exactly `START -> validate_frozen_input -> generate_validated_body -> END`, using typed state and async nodes returning partial state updates. Compile with the approved persistent SQLite checkpointer after the required human package-verification and startup smoke test.

**Do not copy:** the old NDJSON generator from [`stock_analyzer.py`](/root/source/AthenaQuant/backend/app/services/stock_analyzer.py:250) lines 250-310. It streams raw model deltas and has a trading-oriented prompt, both prohibited for Phase 3.

---

### `backend/app/analysis/lifecycle.py` and `backend/app/analysis/service.py` (service, event-driven/request-response)

**Analog:** `backend/app/decision/ai_review.py`

**Proposal remains non-authoritative and failures retain the deterministic state** ([`ai_review.py`](/root/source/AthenaQuant/backend/app/decision/ai_review.py:141), lines 141-181):
```python
class DecisionReviewService:
    async def review(self, *, run_id: str) -> dict[str, Any]:
        run = self._repository.get_decision_run(run_id)
        if run is None:
            raise ValueError("decision run not found")
        unavailable = {"review_status": "unavailable", "final": run["final"]}
        if self._fixture_compose or self._gateway is None or run["proposal"] is not None:
            return unavailable
        try:
            proposal = await self._gateway.propose(run["baseline"])
            self._repository.record_ai_review_proposal(...)
        except (RuntimeError, ValueError, TypeError):
            return unavailable
```

**Persist before broadcasting** ([`operational/repository.py`](/root/source/AthenaQuant/backend/app/operational/repository.py:345), lines 345-390):
```python
def record_alert_event(self, event: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically retain an immutable alert snapshot before SSE or delivery work."""
    ...
    with self._connection() as connection, connection:
        connection.execute("""INSERT INTO alert_events (...) VALUES (...)""", (...))
    persisted = self.get_alert_event(event_id)
    assert persisted is not None
    return persisted
```

**Required adaptation:** `LifecycleRuleService` emits only a proposal after deterministic, state-specific checks. `confirm` reloads the review, validates reviewer identity server-side, appends the confirmed event and exactly one immutable 20/60/120-day plan atomically. `reject` appends a rejected review and never changes derived current state. `AnalysisService` must prepare/freeze evidence outside the graph, acquire the single active run transactionally, await graph invocation, validate model body and assembled envelope, then persist or audit a terminal failure before publishing controlled progress.

---

### `backend/app/analysis/api.py` (route, request-response)

**Analog:** `backend/app/api/portfolio.py`

**Router/app-state access** ([`portfolio.py`](/root/source/AthenaQuant/backend/app/api/portfolio.py:13), lines 13-21):
```python
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

def _repository(request: Request) -> OperationalRepository:
    return request.app.state.operational

def _service(request: Request) -> PortfolioService:
    return request.app.state.portfolio_service
```

**Pydantic payloads and `ValueError` translation** ([`portfolio.py`](/root/source/AthenaQuant/backend/app/api/portfolio.py:30), lines 30-65; [`portfolio.py`](/root/source/AthenaQuant/backend/app/api/portfolio.py:72), lines 72-91):
```python
class AccountCreate(BaseModel):
    name: str
    available_funds: float = 0

def _invalid(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))

@router.post("/accounts", status_code=201)
def create_account(payload: AccountCreate, request: Request) -> dict[str, Any]:
    try:
        account = _repository(request).create_account(**payload.model_dump())
    except ValueError as error:
        raise _invalid(error) from error
    return {"account": account}
```

Create a dedicated `/api/analysis` router with typed request/response models. Put subject existence/ownership checks in service/repository lookups before reads and mutations. `POST /runs` returns an existing active run when appropriate; report/evidence/history endpoints are read-only; `confirm`/`reject` accept no caller-supplied reviewer. Do not add report POST/DELETE endpoints, a standalone server, direct provider configuration, or an unbounded client stream.

---

### `backend/app/main.py`, `backend/pyproject.toml`, and `backend/uv.lock` (config, app-lifecycle/transform)

**Analog:** `backend/app/main.py`

**Lifespan dependency assembly** ([`main.py`](/root/source/AthenaQuant/backend/app/main.py:63), lines 63-87):
```python
operational = OperationalRepository(store.data_dir / "operational.db")
operational.migrate()
app.state.operational = operational
...
research_repository = ResearchRepository(operational.database_path)
app.state.research_repository = research_repository
app.state.factor_registry = FactorRegistry(research_repository)
```

**Router registration** ([`main.py`](/root/source/AthenaQuant/backend/app/main.py:315), lines 315-340):
```python
app.include_router(research.router)
app.include_router(intraday.router)
...
app.include_router(portfolio.router)
```

**Dependency declaration convention** ([`pyproject.toml`](/root/source/AthenaQuant/backend/pyproject.toml:8), lines 8-35):
```toml
dependencies = [
    "fastapi>=0.115",
    "pydantic>=2.7",
    "sse-starlette>=2.0",
    "openai>=1.40",
]
```

Instantiate `AnalysisRepository(operational.database_path)`, evidence/lifecycle/service collaborators, and the approved dedicated checkpoint store during this existing lifespan; assign them to `app.state`; include `analysis.router`; cleanly close the saver if its concrete API requires it. The install is a human-verify checkpoint before changing `pyproject.toml`/`uv.lock`; lock resolved packages after the graph compile/invoke smoke test.

---

### `backend/app/services/quote_service.py` and `backend/app/api/intraday.py` (service/route, pub-sub/streaming)

**Analog:** existing shared SSE channel.

**Subscriber-owned, bounded event channel** ([`quote_service.py`](/root/source/AthenaQuant/backend/app/services/quote_service.py:42), lines 42-87):
```python
class QuoteSubscriber:
    def pop(self) -> dict:
        with self._lock:
            out = {"quote_updated": self._quote_updated, ...}
            self._quote_updated = False
            self._alerts = []
            self._event.clear()
            return out
```

**Broadcast through the existing subscriber registry** ([`quote_service.py`](/root/source/AthenaQuant/backend/app/services/quote_service.py:320), lines 320-367):
```python
def subscribe(self) -> QuoteSubscriber:
    sub = QuoteSubscriber()
    with self._lock:
        self._subscribers.add(sub)
    return sub

def notify_portfolio_updated(self, account_ids: list[str | int]) -> None:
    for sub in self._snapshot_subscribers():
        sub.notify_portfolio_updated(account_ids)
```

**Named SSE emission and cleanup** ([`intraday.py`](/root/source/AthenaQuant/backend/app/api/intraday.py:131), lines 131-201):
```python
sub = qs.subscribe()
try:
    while True:
        await asyncio.to_thread(sub.wait, 5.0)
        data = sub.pop()
        if data["portfolio_updated"]:
            yield {"event": "portfolio_updated", "data": json.dumps({...})}
finally:
    qs.unsubscribe(sub)
```

Add only a coarse persisted `analysis_progress` event/status field to this channel. Publish after safe run-state persistence and include identifiers/status only. Never stream tokens, raw prompts, raw evidence, source excerpts, lifecycle mutations, or model-selected events.

---

### `frontend/src/lib/api.ts`, `frontend/src/lib/queryKeys.ts`, and `frontend/src/lib/useQuoteStream.ts` (utility/hook, request-response/pub-sub)

**Analog:** existing typed client and independent cache key ownership.

**Unified error and request helper** ([`api.ts`](/root/source/AthenaQuant/frontend/src/lib/api.ts:10), lines 10-37):
```typescript
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    ...
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}
```

**Typed endpoint and account-scoped query construction** ([`api.ts`](/root/source/AthenaQuant/frontend/src/lib/api.ts:2203), lines 2203-2253):
```typescript
portfolioHoldings: (accountId?: number, includeArchived = false) => {
  const params = new URLSearchParams({ include_archived: String(includeArchived) })
  if (accountId != null) params.set('account_id', String(accountId))
  return request<{ positions: PortfolioPosition[] }>(`/api/portfolio/positions?${params}`)
},
```

**Per-resource `QK` factories** ([`queryKeys.ts`](/root/source/AthenaQuant/frontend/src/lib/queryKeys.ts:46), lines 46-55; [`queryKeys.ts`](/root/source/AthenaQuant/frontend/src/lib/queryKeys.ts:94), lines 94-97):
```typescript
researchExperiment: (experimentId: string) => ['research', 'experiments', experimentId] as const,
portfolioSummary: (accountId?: number) => ['portfolio-summary', accountId ?? 'all'] as const,
```

**Controlled SSE invalidation** ([`useQuoteStream.ts`](/root/source/AthenaQuant/frontend/src/lib/useQuoteStream.ts:159), lines 159-165):
```typescript
es.addEventListener('portfolio_updated', (e: MessageEvent) => {
  try {
    const data = JSON.parse(e.data)
    invalidatePortfolio(data.account_ids)
  } catch {
    // Ignore malformed stream payloads without disrupting the shared connection.
  }
})
```

Add `Analysis*` interfaces plus `api.analysisStartRun`, report-list/detail/evidence/history, and review-action functions using `request`, `encodeURIComponent`, and `URLSearchParams`. Add separate `QK.analysisReports`, `analysisReport`, `analysisEvidence`, `analysisSignalHistory`, and `analysisRun` keys; process `analysis_progress` only through the one existing `EventSource`, invalidating the narrow affected keys. Components must not call `fetch` directly or infer provenance from report text.

---

### `frontend/src/components/analysis/*.tsx` (components, request-response/transform/CRUD/streaming)

**Analogs:** `frontend/src/pages/Portfolio.tsx` for independently retained queries and states; `frontend/src/components/financials/AiAnalysisDialog.tsx` for report metadata/copy/error states only.

**Independent cached panels retain prior successful data** ([`Portfolio.tsx`](/root/source/AthenaQuant/frontend/src/pages/Portfolio.tsx:44), lines 44-59):
```typescript
const summaryQuery = useQuery({
  queryKey: QK.portfolioSummary(selectedAccountId),
  queryFn: () => api.portfolioSummary(selectedAccountId),
  placeholderData: keepPreviousData,
})
const holdingsQuery = useQuery({
  queryKey: QK.portfolioHoldings(selectedAccountId),
  queryFn: () => api.portfolioHoldings(selectedAccountId),
  placeholderData: keepPreviousData,
})
```

**Partial failure leaves prior data visible** ([`Portfolio.tsx`](/root/source/AthenaQuant/frontend/src/pages/Portfolio.tsx:141), lines 141-156):
```tsx
{isError && summary && <p role="status" className="text-sm text-warning">
  刷新投资组合失败，正在显示上次结果。
  <button type="button" onClick={retry} className="ml-2 text-accent underline">重新加载投资组合</button>
</p>}
```

**Safe copy status pattern** ([`AiAnalysisDialog.tsx`](/root/source/AthenaQuant/frontend/src/components/financials/AiAnalysisDialog.tsx:70), lines 70-77):
```typescript
const handleCopy = async () => {
  if (!content) return
  try {
    await navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  } catch { /* ignore */ }
}
```

**Required adaptation:** `AnalysisWorkspace` owns local selected report/tab/reading-position restoration, starts analysis through a mutation, and gives Report/Evidence/Lifecycle/Status their own typed queries. `ReportPanel` renders structured body fields, warnings before affected conclusions and IC memo, and the fixed disclaimer. `EvidencePanel` uses semantic tables plus native `<details>` for raw records. `LifecyclePanel` renders only server-provided current state/timeline/outcomes and offers confirm/reject mutations where authorized. `AnalysisStatus` renders only coarse server status. Use UI-SPEC's native tabs, `role=status`/`role=alert`, token classes, 44px mobile controls, table horizontal overflow, and explicit Chinese labels; no gradient AI modal, second host shell, or client-side source/score calculation.

---

### `frontend/src/pages/StockAnalysis.tsx`, `frontend/src/pages/Portfolio.tsx`, and `frontend/src/components/financials/AiAnalysisHost.tsx` (page/host, request-response)

**Analog:** existing object-local entry wiring.

**Selected-object state is page-local and reset only when the object changes** ([`StockAnalysis.tsx`](/root/source/AthenaQuant/frontend/src/pages/StockAnalysis.tsx:47), lines 47-52):
```typescript
const onSelect = (sym: string, nm: string) => {
  setSymbol(sym)
  setName(nm)
  setConfirmReport(null)
  rememberStock(sym, nm)
}
```

**Existing selected-account context** ([`Portfolio.tsx`](/root/source/AthenaQuant/frontend/src/pages/Portfolio.tsx:37), lines 37-58):
```typescript
const [selectedAccountId, setSelectedAccountId] = useState<number | undefined>()
const summaryQuery = useQuery({
  queryKey: QK.portfolioSummary(selectedAccountId),
  queryFn: () => api.portfolioSummary(selectedAccountId),
  placeholderData: keepPreviousData,
})
```

**Host is mounted once by the existing app shell** ([`AiAnalysisHost.tsx`](/root/source/AthenaQuant/frontend/src/components/financials/AiAnalysisHost.tsx:10), lines 10-14; [`Layout.tsx`](/root/source/AthenaQuant/frontend/src/components/Layout.tsx:785), lines 785-800):
```tsx
export function AiAnalysisHost() {
  const { task, mode } = useDialogTask()
  const { minimized } = useDialogState()
  return <AiAnalysisDialog task={task} mode={mode} minimized={minimized} />
}
...
<Outlet />
<AiAnalysisHost />
```

Replace/extend the local stock CTA and account-local Portfolio region with `AnalysisWorkspace` using their currently selected symbol/account. Rework `AiAnalysisHost` only as a resume/review entry for persisted server reports, or remove its legacy modal dependence where necessary; do not add another route, global shell, direct-fetch store, client report persistence, or delete action. Preserve latest validated report while regeneration progresses and retain earlier immutable versions in server history.

---

### `backend/tests/test_analysis_*.py` (tests, transform/event-driven/CRUD/request-response)

**Analogs:** `backend/tests/test_decision_ai_review.py` and `backend/tests/test_portfolio_api.py`.

**Offline injected adapter test** ([`test_decision_ai_review.py`](/root/source/AthenaQuant/backend/tests/test_decision_ai_review.py:38), lines 38-77):
```python
async def offline_transport(messages, **_kwargs):
    observed_messages.extend(messages)
    return '{"adjustments":[...]}'

gateway = ConfiguredAIReviewGateway(
    provider="openai_compat", model="offline-contract-model",
    generate_text=offline_transport,
)
response = await DecisionReviewService(repository=repository, gateway=gateway).review(run_id=run["id"])
```

**Temporary SQLite + focused API host** ([`test_portfolio_api.py`](/root/source/AthenaQuant/backend/tests/test_portfolio_api.py:87), lines 87-105):
```python
repository, service = _service(tmp_path)
app = FastAPI()
app.include_router(portfolio_router)
app.state.operational = repository
app.state.portfolio_service = service
client = TestClient(app)
```

Cover: grade/independence/normalization matrix; unresolved and conflicting numbers; exact two-node fixed graph topology/no tools/loops; malformed JSON, unknown citations, and valuation mismatch cause terminal audited failure without a report; one active run per subject; immutable report version ordering; proposal vs confirmed/rejected lifecycle; one immutable observation plan plus append-only outcomes; ID/subject authorization and app router registration. Use fake adapters and local fixture inputs only, never live provider or network calls.

---

### `frontend/e2e/phase3-ai-analysis.spec.ts` (test, request-response)

**Analog:** `frontend/e2e/phase2-research.spec.ts`

**Route fixtures with an explicit unhandled-route failure** ([`phase2-research.spec.ts`](/root/source/AthenaQuant/frontend/e2e/phase2-research.spec.ts:27), lines 27-47):
```typescript
await page.route('**/api/**', route => route.fulfill({ contentType: 'application/json', body: '{}' }))
await page.route('**/api/research**', async route => {
  const request = route.request()
  const path = new URL(request.url()).pathname
  const json = (body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  ...
  return json({ detail: `Unhandled fixture route: ${path}` }, 500)
})
```

**Keyboard and responsive loop** ([`phase2-research.spec.ts`](/root/source/AthenaQuant/frontend/e2e/phase2-research.spec.ts:282), lines 282-287):
```typescript
for (const viewport of [
  { width: 1440, height: 960 },
  { width: 1024, height: 900 },
  { width: 375, height: 844 },
]) {
  await runKeyboardScenario(page, viewport)
}
```

Fixture server-owned reports/evidence/lifecycle history, including an unresolved conflict and an incomplete outcome. Verify stock and portfolio entry points, independent panel loading/failure retention, tab keyboard behavior, disclosure/table overflow, mobile 44px controls, no duplicate generation, source warning placement before conclusions/IC memo, and that confirmation/rejection request only the server-issued review reference. Do not fixture an AI token stream or browser-owned provenance.

## Shared Patterns

### Authentication And Subject Authorization
**Source:** [`backend/app/main.py`](/root/source/AthenaQuant/backend/app/main.py:282), lines 282-312
```python
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    ...
    token = request.cookies.get(auth_api.COOKIE_NAME)
    if token and auth_service.is_valid_session(token):
        return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "未登录或会话已过期"})
```
**Apply to:** all analysis endpoints. Router inheritance provides session enforcement; service/repository must additionally resolve report/signal/run IDs through the requested subject/account. Extract reviewer identity from the authenticated server context, not `confirm` request JSON.

### Persistence And Audit Integrity
**Source:** [`backend/app/research/repository.py`](/root/source/AthenaQuant/backend/app/research/repository.py:23), lines 23-27; [`backend/app/research/repository.py`](/root/source/AthenaQuant/backend/app/research/repository.py:248), lines 248-315
```python
def _json(value: object, field: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be JSON serializable") from error
```
**Apply to:** frozen evidence, model/prompt/schema provenance, lifecycle reason payloads, and diagnostics. Persist server records in SQLite transactions and never make checkpoints, client state, or report prose authoritative.

### API Error Handling
**Source:** [`backend/app/api/portfolio.py`](/root/source/AthenaQuant/backend/app/api/portfolio.py:63), lines 63-65
```python
def _invalid(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))
```
**Apply to:** invalid state transitions, missing subjects, bounded focus/pagination, and validation errors. Return 404 for absent scoped records, 409 for an incompatible active-run/review state where appropriate, and sanitized 5xx/provider errors. Do not leak prompts, raw evidence, credentials, or internal checkpoint content.

### Controlled Progress Only
**Source:** [`backend/app/api/intraday.py`](/root/source/AthenaQuant/backend/app/api/intraday.py:165), lines 165-171
```python
for evt_json in data["reviews"]:
    yield {
        "event": "review_progress",
        "data": evt_json,
    }
```
**Apply to:** analysis generation status after persistence. Keep the existing single SSE connection and named events; no new analysis stream endpoint and no raw generation delta display.

### UI Cache Isolation
**Source:** [`frontend/src/pages/Portfolio.tsx`](/root/source/AthenaQuant/frontend/src/pages/Portfolio.tsx:44), lines 44-58
```typescript
const accountsQuery = useQuery({ queryKey: QK.portfolioAccounts(showArchived), ... })
const summaryQuery = useQuery({ queryKey: QK.portfolioSummary(selectedAccountId), ... })
const holdingsQuery = useQuery({ queryKey: QK.portfolioHoldings(selectedAccountId), ... })
```
**Apply to:** report, evidence, lifecycle history, and status. Separate query keys and local panel state ensure one pending/error panel does not clear report content the user is reading.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/app/analysis/graph.py` | service | event-driven | No LangGraph workflow exists. Follow the locked AI-SPEC fixed two-node topology after approved dependency installation and smoke testing. |
| `backend/app/analysis/schemas.py` | model | transform | Existing code validates narrow JSON manually/Pydantic request models, but has no server-owned evidence envelope with cross-model citation invariants. Use AI-SPEC strict Pydantic contracts. |

## Metadata

**Analog search scope:** `backend/app/{main,operational,research,decision,services,api,tickflow}`, `backend/tests`, `frontend/src/{lib,pages,components}`, `frontend/e2e`  
**Files scanned:** 28 source/test/config files plus all four Phase 3 contracts  
**Pattern extraction date:** 2026-07-11
