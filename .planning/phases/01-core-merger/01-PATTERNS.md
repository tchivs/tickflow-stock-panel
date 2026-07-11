# Phase 1: Core Merger - Pattern Map

**Mapped:** 2026-07-11
**Files analyzed:** 38 planned new or modified files
**Analogs found:** 29 / 38

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/app/operational/repository.py` | repository/service | CRUD | `app/strategy/monitor_rules.py` | partial: replace JSON files with SQLite |
| `backend/app/operational/migrations.py` | migration | batch | `app/main.py` lifespan | partial |
| `backend/app/portfolio/service.py` | service | transform/request-response | `app/services/quote_service.py` | role-match |
| `backend/app/api/portfolio.py` | route/controller | CRUD/request-response | `app/api/monitor_rules.py` | role-match |
| `backend/app/main.py` | application config | lifecycle | `app/main.py` | exact modification |
| `backend/app/strategy/monitor_rules.py` | model/validation | CRUD/transform | `app/strategy/monitor_rules.py` | exact modification |
| `backend/app/strategy/monitor.py` | rule engine | event-driven/transform | `app/strategy/monitor.py` | exact modification |
| `backend/app/services/quote_service.py` | service | event-driven/streaming | `app/services/quote_service.py` | exact modification |
| `backend/app/api/intraday.py` | route/controller | streaming | `app/api/intraday.py` | exact modification |
| `backend/app/notifications/delivery.py` | service | event-driven | `app/services/quote_service.py` + `app/services/webhook_adapter.py` | partial |
| `backend/app/services/webhook_adapter.py` | utility/adapter | request-response | `app/services/webhook_adapter.py` | exact extension |
| `backend/app/contracts/market_data.py` | model/utility | batch/transform | `app/parquet.py` | partial |
| `backend/app/contracts/validator.py` | service | batch/transform | `app/parquet.py` | partial |
| `backend/app/data_providers/fixture_provider.py` | provider | file-I/O/batch | `app/data_providers/tickflow_provider.py` | role-match |
| `backend/app/jobs/daily_pipeline.py` | job | batch | `app/jobs/daily_pipeline.py` | exact modification |
| `backend/app/decision/playbook.py` | service | transform | no host analog | none |
| `backend/app/decision/adjustments.py` | service | transform | no host analog | none |
| `backend/app/decision/replay.py` | service | batch/transform | no host analog | none |
| `backend/app/api/decision.py` | route/controller | request-response | `app/api/monitor_rules.py` | role-match |
| `frontend/src/lib/api.ts` | API client/types | request-response | `frontend/src/lib/api.ts` | exact modification |
| `frontend/src/lib/queryKeys.ts` | utility/config | transform | `frontend/src/lib/queryKeys.ts` | exact modification |
| `frontend/src/lib/useQuoteStream.ts` | hook | streaming | `frontend/src/lib/useQuoteStream.ts` | exact modification |
| `frontend/src/router.tsx` | route config | request-response | `frontend/src/router.tsx` | exact modification |
| `frontend/src/components/Layout.tsx` | component/shell | event-driven | `frontend/src/components/Layout.tsx` | exact modification |
| `frontend/src/pages/Portfolio.tsx` | page/component | CRUD/request-response | `frontend/src/pages/Monitor.tsx` | role-match |
| `frontend/src/components/portfolio/AccountDialog.tsx` | component | CRUD | `components/monitor/RuleEditor.tsx` + `components/Modal.tsx` | role-match |
| `frontend/src/components/portfolio/HoldingDialog.tsx` | component | CRUD | `components/monitor/RuleEditor.tsx` + `components/Modal.tsx` | role-match |
| `frontend/src/components/portfolio/HoldingsTable.tsx` | component | transform | `pages/Watchlist.tsx` | role-match |
| `frontend/src/components/portfolio/HoldingCard.tsx` | component | transform | `pages/Watchlist.tsx` | role-match |
| `frontend/src/pages/Monitor.tsx` | page/component | CRUD/streaming | `frontend/src/pages/Monitor.tsx` | exact modification |
| `frontend/src/components/monitor/RuleEditor.tsx` | component | CRUD | `components/monitor/RuleEditor.tsx` | exact modification |
| `frontend/src/components/monitor/DeliveryDetailDialog.tsx` | component | request-response | `components/Modal.tsx` | role-match |
| `frontend/src/pages/Dashboard.tsx` | page/component | request-response | `pages/Dashboard.tsx` | exact modification |
| `frontend/src/components/decision/PlaybookInspector.tsx` | component | request-response | `components/Modal.tsx` | partial |
| `backend/tests/test_phase1_fixture_sync.py`, `test_data_contracts.py` | test | batch/file-I/O | `tests/test_pipeline_and_monitor_fixes.py` | role-match |
| `backend/tests/test_portfolio_api.py`, `test_position_monitor.py`, `test_notification_delivery.py`, `test_portfolio_sse.py` | test | CRUD/event-driven/streaming | `tests/test_monitor_etf.py` + `tests/test_strategy_realtime_refresh.py` | role-match |
| `backend/tests/test_decision_playbook.py`, `test_decision_adjustments.py`, `test_decision_replay.py` | test | transform/batch | no host analog | none |
| `frontend/playwright.config.ts`, `frontend/e2e/phase1.spec.ts` | test/config | request-response/streaming | no host analog | none |
| `compose/phase1.test.yml`, receiver/verifier fixtures/scripts | config/test harness | event-driven/file-I/O | `docker-compose.yml` | partial |
| `docs/UPSTREAM-SYNC.md` | documentation | transform | `docs/ARCHITECTURE.md` | partial |

## Pattern Assignments

### Operational SQLite, Portfolio API, and application lifecycle

**Apply to:** `backend/app/operational/{repository,migrations}.py`, `backend/app/portfolio/service.py`, `backend/app/api/portfolio.py`, and `backend/app/main.py`.

**API analog:** `backend/app/api/monitor_rules.py`

**Imports and state lookup** (lines 7-26):
```python
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/monitor-rules", tags=["monitor-rules"])

def _data_dir(request: Request) -> Path:
    return request.app.state.repo.store.data_dir
```

**Validation, persistence, state synchronization, and response contract** (lines 133-156):
```python
@router.post("")
def save_rule(req: RuleModel, request: Request):
    rule = monitor_rules.normalize(req.model_dump())
    try:
        monitor_rules.validate(rule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    monitor_rules.save_one(_data_dir(request), rule)
    _sync_engine(request)
    return {"ok": True, "rule": rule}
```

Use the same Pydantic-boundary/`HTTPException(400, detail=...)` shape for account, holding, archive, and delete actions. Unlike monitor rules, portfolio records must persist through an `app.state.operational` repository and parameterized SQLite transactions, not JSON files.

**Lifespan registration and shutdown ownership:** `backend/app/main.py` lines 45-82 and 189-208.
```python
store = DataStore()
repo = KlineRepository(store)
app.state.datastore = store
app.state.repo = repo
...
qs = QuoteService()
app.state.quote_service = qs
qs.set_repo(repo)
...
yield
...
if qs:
    qs.stop()
```

Create/migrate the operational database immediately after `DataStore`/`KlineRepository` construction, attach it to `app.state`, then initialize portfolio/notification collaborators. Include the new `portfolio` and `decision` routers with the existing `app.include_router(...)` sequence at lines 275-297. Do not create another FastAPI app or persistence location.

### Position rules, persisted alert history, and SSE order

**Apply to:** `backend/app/strategy/monitor_rules.py`, `backend/app/strategy/monitor.py`, `backend/app/services/quote_service.py`, `backend/app/api/intraday.py`, and operational alert/delivery tables.

**Rule validation model:** `backend/app/api/monitor_rules.py` lines 30-58 and `backend/app/strategy/monitor_rules.py` lines 98-168. Extend the existing rule vocabulary with `type="position"`, position IDs/scope, active-time, quiet-period bypass, and channels. Keep validation in the domain module and translate only `ValueError` at the API boundary.

**Cooldown and immutable event construction:** `backend/app/strategy/monitor.py` lines 502-583.
```python
last = self._last_fire.get(key)
if last is not None and (now - last) < cooldown:
    continue
self._last_fire[key] = now

ev = {
    "ts": int(now * 1000),
    "rule_id": rule["id"],
    "source": source,
    "symbol": "" if is_batch else sym,
    "price": price,
    "severity": severity,
    "conditions": list(rule.get("conditions", [])),
}
```

Position rules must evaluate an explicit per-position quote projection after generic rules, so a generic symbol rule remains one market event. Preserve `(rule_id, symbol)` cooldown ownership in `MonitorRuleEngine`; add account/position IDs, valuation source/as-of, and condition snapshot to the additive event payload.

**Required hot-path ordering:** `backend/app/services/quote_service.py` lines 1008-1051.
```python
if rule_events:
    alert_store.append_many(self._app_state.repo.store.data_dir, rule_events)
...
if all_alerts:
    self._broadcast_alerts(all_alerts)
...
if rule_events:
    self._maybe_send_webhook(rule_events, engine)
```

Replace the JSONL persistence call with durable operational alert-event insertion, but preserve this order exactly: evaluate/cooldown, persist event, broadcast SSE, enqueue delivery, persist delivery outcome. Delivery failure must never undo or block the persisted/SSE event.

**Subscriber fan-out:** `backend/app/services/quote_service.py` lines 310-355.
```python
def subscribe(self) -> QuoteSubscriber:
    sub = QuoteSubscriber()
    with self._lock:
        self._subscribers.add(sub)
    return sub

def _broadcast_alerts(self, alerts: list[dict]) -> None:
    for sub in self._snapshot_subscribers():
        sub.push_alerts(alerts)
```

Add a coalesced `portfolio_updated` flag/queue operation to `QuoteSubscriber`, a `QuoteService.notify_portfolio_updated(...)` fan-out method, and a named event in the one existing stream. Do not add an EventSource endpoint.

**Named event emission:** `backend/app/api/intraday.py` lines 137-190.
```python
sub = qs.subscribe()
try:
    while True:
        await asyncio.to_thread(sub.wait, 5.0)
        data = sub.pop()
        ...
        if data["quote_updated"]:
            yield {"event": "quotes_updated", "data": json.dumps({...})}
finally:
    qs.unsubscribe(sub)
```

Emit `portfolio_updated` in this generator using the same dictionary format; preserve unsubscribe in `finally`.

### Feishu/Telegram delivery adapter

**Apply to:** `backend/app/notifications/delivery.py` and `backend/app/services/webhook_adapter.py`.

**Nonblocking executor seam:** `backend/app/services/quote_service.py` lines 40-44 and 1135-1143.
```python
_WEBHOOK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="feishu-webhook")
...
_WEBHOOK_EXECUTOR.submit(webhook_adapter.send_feishu, feishu_url, title, body, feishu_secret)
```

Use a bounded executor after event persistence/SSE. The delivery worker must catch adapter exceptions, sanitize/store the error, and update one delivery row per channel rather than leaking failures into `_evaluate_monitors`.

**Feishu URL boundary and timeout:** `backend/app/services/webhook_adapter.py` lines 39-50 and 96-117.
```python
FEISHU_HOOK_PREFIX = "https://open.feishu.cn/open-apis/bot/v2/hook/"

def is_valid_feishu_url(url: str) -> bool:
    return bool(url) and url.startswith(FEISHU_HOOK_PREFIX)

resp = httpx.post(webhook_url, json=payload, timeout=5.0)
```

Retain the Feishu fixed-prefix validation and signing path. For Telegram, construct the fixed Bot API origin from token/chat configuration; do not accept an arbitrary request URL in production. Test-only receiver routing is configuration-gated and belongs only in the test Compose profile.

### Governed fixture sync and data-contract validation

**Apply to:** `backend/app/data_providers/fixture_provider.py`, `backend/app/contracts/{market_data,validator}.py`, and `backend/app/jobs/daily_pipeline.py`.

**Storage compatibility wrapper:** `backend/app/parquet.py` lines 39-55.
```python
def scan_parquet_compat(source: Any, **kwargs: Any) -> pl.LazyFrame:
    kwargs.setdefault("missing_columns", "insert")
    kwargs.setdefault("extra_columns", "ignore")
    return pl.scan_parquet(source, **kwargs)

def scan_daily_parquet(source: Any, **kwargs: Any) -> pl.LazyFrame:
    kwargs.setdefault("schema", DAILY_STORAGE_SCHEMA)
    kwargs.setdefault("cast_options", pl.ScanCastOptions(integer_cast="allow-float"))
    return scan_parquet_compat(source, **kwargs)
```

The validator must inspect the same partitioned Parquet datasets and explicit schemas. It must not create a SQLite time-series mirror. Report primary key, market-time, repair-window, and schema-drift violations deterministically.

**Pipeline progress and normal-path reuse:** `backend/app/jobs/daily_pipeline.py` lines 120-126 and 157-165 use `emit(stage, percent, message)` around existing sync services. Fixture mode should select an injected provider through an explicit test-only environment variable, then execute the normal sync/view/enrichment path and progress contract.

### Deterministic decision package and API

**Apply to:** `backend/app/decision/{playbook,adjustments,replay}.py` and `backend/app/api/decision.py`.

**No direct host analog.** Use `backend/app/api/monitor_rules.py` lines 132-168 for FastAPI/Pydantic/error shaping and `backend/app/main.py` lines 45-60 for data-lake ownership. Keep pure deterministic calculation separate from HTTP and persistence. Persist the baseline before optional adjustment; write baseline/final fields and per-field audit rows transactionally. Replay reads governed data only up to `as_of`, sorts inputs, derives time from the requested snapshot, and runs under an AI-call guard that raises on invocation.

### Frontend API, query keys, root stream, routes, and navigation

**Apply to:** `frontend/src/lib/{api,queryKeys,useQuoteStream}.ts`, `frontend/src/router.tsx`, and `frontend/src/components/Layout.tsx`.

**Typed API client convention:** `frontend/src/lib/api.ts` lines 1871-1886.
```typescript
monitorRulesList: () =>
  request<{ rules: MonitorRule[] }>('/api/monitor-rules'),
monitorRuleSave: (rule: MonitorRule) =>
  request<{ ok: boolean; rule: MonitorRule }>('/api/monitor-rules', {
    method: 'POST',
    body: JSON.stringify(rule),
  }),
monitorRuleDelete: (id: string) =>
  request<{ ok: boolean }>(`/api/monitor-rules/${encodeURIComponent(id)}`, { method: 'DELETE' }),
```

Define portfolio and decision response/request types beside existing API types and add all request methods to the existing `api` object. Use `encodeURIComponent` for IDs; do not add a second fetch client.

**Query key convention:** `frontend/src/lib/queryKeys.ts` lines 74-77.
```typescript
monitorRules: ['monitor-rules'] as const,
monitorRuleOptions: ['monitor-rule-options'] as const,
alerts: (source?: string) => ['alerts', source ?? ''] as const,
```

Add stable `portfolioAccounts`, `portfolioSummary(accountId)`, `portfolioHoldings(accountId)`, and decision keys before their consumers. Mutations must invalidate these keys, preserve filters, and rely on existing React Query cache behavior.

**Single root SSE hook:** `frontend/src/lib/useQuoteStream.ts` lines 102-168.
```typescript
const es = new EventSource('/api/intraday/stream')
...
es.addEventListener('strategy_alert', (e: MessageEvent) => {
  const data = JSON.parse(e.data)
  const alerts: StrategyAlertEvent[] = data.alerts || []
  if (alerts.length > 0) {
    handleAlerts(alerts)
    qc.invalidateQueries({ queryKey: ['alerts'] })
    qc.invalidateQueries({ queryKey: ['alerts-total'] })
  }
})
```

Handle `portfolio_updated` here only, invalidating affected portfolio keys, and extend existing `quotes_updated` invalidation to price-derived portfolio queries. Do not open an EventSource from Portfolio, Monitor, or a dialog.

**Lazy route registration:** `frontend/src/router.tsx` lines 12-29 and 69-95.
```typescript
const Monitor = lazy(() => import('./pages/Monitor').then(m => ({ default: m.Monitor })))
...
{ path: 'monitor', element: <Monitor /> },
```

Add `Portfolio` with the identical named-export/lazy mapping and `{ path: 'portfolio', element: <Portfolio /> }` under the existing shell.

**Navigation convention:** `frontend/src/components/Layout.tsx` lines 465-501. Add the `/portfolio` entry to the existing `nav` definition (above the read range) with `WalletCards`; it will automatically participate in user ordering/hiding and `NavLink` active state. Do not create a second shell.

### Portfolio page, dialogs, responsive holdings, and Monitor extension

**Apply to:** `frontend/src/pages/Portfolio.tsx`, `frontend/src/components/portfolio/*`, `frontend/src/pages/Monitor.tsx`, `frontend/src/components/monitor/{RuleEditor,DeliveryDetailDialog}.tsx`, `frontend/src/pages/Dashboard.tsx`, and `frontend/src/components/decision/PlaybookInspector.tsx`.

**Page query/mutation pattern:** `frontend/src/components/monitor/RuleEditor.tsx` lines 44-105.
```typescript
const qc = useQueryClient()
const options = useQuery({ queryKey: QK.monitorRuleOptions, queryFn: api.monitorRuleOptions })
const save = useMutation({
  mutationFn: () => api.monitorRuleSave(d),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: QK.monitorRules })
    onSaved?.()
    onClose()
  },
  onError: err => setError(String((err as any)?.message ?? err)),
})
```

Use this query/mutation lifecycle for accounts, holdings, rules, delivery detail, and playbook reads. Portfolio loading uses the existing `Skeleton` primitive; mutation success closes only its modal, invalidates affected keys, and retains the selected account filter.

**Modal accessibility primitive:** `frontend/src/components/Modal.tsx` lines 40-136.
```tsx
<div ref={panelRef} role="dialog" aria-modal="true"
  aria-labelledby={labelledBy} aria-label={labelledBy ? undefined : ariaLabel}
  tabIndex={-1} className={`outline-none ${panelClassName}`}>
  {children}
</div>
```

All account, holding, rule, delivery-detail, destructive-confirmation, and playbook inspector dialogs must use this primitive. Preserve focus trapping, Escape/backdrop semantics, focus restoration, and an initial focus on the non-destructive choice for confirmations.

**Page header primitive:** `frontend/src/components/PageHeader.tsx` lines 12-26.
```tsx
<PageHeader title="投资组合" right={...} />
```

Use `PageHeader` for Portfolio and retain Monitor's existing header instead of introducing local page-title chrome. Portfolio must implement the UI-SPEC table/card breakpoints with CSS, not a user-controlled view switch or horizontal overflow.

**Rule editor state style:** `frontend/src/components/monitor/RuleEditor.tsx` lines 25-42 and 400-510. Extend its single draft object and mutation path for position scope, active time, quiet bypass, and Feishu/Telegram channel selection. Keep existing price/market/strategy behavior independent; do not turn generic rules into holdings fan-out.

### Test and Compose acceptance patterns

**Apply to:** all Phase 1 pytest files, `frontend/playwright.config.ts`, desktop/mobile specs, `compose/phase1.test.yml`, receiver/verifier scripts/fixtures, and `docs/UPSTREAM-SYNC.md`.

**Pure deterministic pytest structure:** `backend/tests/test_pipeline_and_monitor_fixes.py` lines 1-14 and 64-99.
```python
import polars as pl
import pytest

from app.strategy import monitor_rules
from app.strategy.monitor import MonitorRuleEngine
...
with pytest.raises(ValueError):
    monitor_rules.validate(_base_price_rule("sector"))
```

**SSE fan-out regression structure:** `backend/tests/test_strategy_realtime_refresh.py` lines 49-57.
```python
service = QuoteService()
first = service.subscribe()
second = service.subscribe()

service.notify_strategy_results_updated()

assert first.pop()["strategy_results_updated"] is True
assert second.pop()["strategy_results_updated"] is True
```

Use independent subscribers for `strategy_alert` and `portfolio_updated`; assertions must prove neither client consumes the other's event. Keep fixtures offline and construct `SimpleNamespace` collaborators or temporary data directories as this test does.

**Compose topology:** `docker-compose.yml` lines 3-24.
```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "${PORT:-3018}:3018"
    environment:
      - DATA_DIR=/app/data
    volumes:
      - ./data:/app/data
```

`compose/phase1.test.yml` must override `DATA_DIR` with a disposable bind mount and introduce only test receiver/verifier services. It must be launched with the dedicated project name and port from `VALIDATION.md`; it cannot mutate production `data/`, request live market data, or run PanWatch/Hermes.

## Shared Patterns

### Authentication
**Source:** `backend/app/main.py` lines 242-272

All new `/api/*` routes automatically pass through the existing middleware. Do not add a Portfolio-specific auth mechanism or mark operational APIs public. `/health` remains the Compose-ready public endpoint.

### Error Handling
**Source:** `backend/app/api/monitor_rules.py` lines 150-153; `backend/app/services/quote_service.py` lines 1053-1054

Use `HTTPException(400, detail=str(e))` for validated request errors. Isolate background/event-driven failures with logging and preserve the user-visible persistence/SSE path. Never return raw adapter errors, URLs, tokens, chat IDs, or response bodies.

### Data Boundaries
**Source:** `backend/app/main.py` lines 45-56; `backend/app/parquet.py` lines 39-55

`DataStore`/`KlineRepository` remain the governed Parquet/DuckDB/Polars boundary for instruments, bars, factors, financials, enriched data, and latest close. SQLite operational state contains accounts, positions, rules, alert events, deliveries, and decision snapshots only.

### Frontend Feedback and Accessibility
**Source:** `frontend/src/components/Modal.tsx` lines 57-116; `frontend/src/components/data/Skeleton.tsx` lines 1-7

Reuse modal focus behavior and local skeletons. All icon-only controls need visible `title` plus `aria-label`, and Portfolio/Monitor must retain semantic table/card equivalents across responsive breakpoints.

## No Analog Found

| File/Area | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/app/operational/*` SQLite migration/repository | repository/migration | CRUD | Host operational state is JSON/JSONL today; Phase 1 is the first SQLite boundary. |
| `backend/app/decision/*` | service | transform/batch | No host-native deterministic playbook, bounded adjustment, or replay module exists. Adapt Hermes semantics only, not runtime/persistence. |
| `backend/app/contracts/*` | validation service | batch | Existing Parquet compatibility helpers exist, but no standalone contract manifest/validator exists. |
| `backend/app/data_providers/fixture_provider.py` | provider | file-I/O/batch | No current deterministic offline provider mode. |
| Playwright config/specs | test | browser request-response/streaming | No browser test harness is present; package installation requires the documented human legitimacy checkpoint. |
| Isolated receiver/verifier Compose harness | config/test harness | event-driven | Current Compose has only the production app service. |

## Metadata

**Analog search scope:** `backend/app/{api,services,strategy,jobs,data_providers}`, `backend/tests`, `frontend/src/{pages,components,lib}`, root Compose, and `docs`.

**Files scanned:** 24 source/config/test files plus all phase artifacts.

**Pattern extraction date:** 2026-07-11
