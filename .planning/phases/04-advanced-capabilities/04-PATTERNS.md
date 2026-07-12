# Phase 04: Advanced Capabilities - Pattern Map

**Mapped:** 2026-07-12
**Files analyzed:** 29 planned file groups (34 concrete files when advanced React components are expanded)
**Analogs found:** 29 / 29

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/app/advanced/schemas.py` | model | transform | `backend/app/analysis/api.py` | role-match |
| `backend/app/advanced/repository.py` | repository | CRUD | `backend/app/analysis/repository.py` | exact |
| `backend/app/advanced/viewpoints.py` | service | CRUD | `backend/app/analysis/repository.py` | role-match |
| `backend/app/advanced/experiments.py` | service | CRUD | `backend/app/research/repository.py` | role-match |
| `backend/app/advanced/evolution.py` | service | CRUD | `backend/app/analysis/repository.py` | role-match |
| `backend/app/advanced/authorization.py` | service | request-response | `backend/app/analysis/api.py` | role-match |
| `backend/app/advanced/jobs.py` | service | event-driven | `backend/app/analysis/repository.py` | role-match |
| `backend/app/advanced/audit.py` | service | CRUD | `backend/app/analysis/projections.py` | role-match |
| `backend/app/advanced/projections.py` | utility | transform | `backend/app/analysis/projections.py` | exact |
| `backend/app/advanced/sandbox.py` | service | process / file-I/O | `backend/app/backtest/strategy.py` | partial-match |
| `backend/app/advanced/workflow.py` | service | event-driven | `backend/app/analysis/graph.py` | exact |
| `backend/app/advanced/api.py` | route | request-response | `backend/app/analysis/api.py` | exact |
| `backend/app/operational/migrations.py` | migration | CRUD | existing analysis migration block | exact |
| `backend/app/main.py` | config | request-response | existing analysis lifecycle registration | exact |
| `backend/app/services/quote_service.py` | service | pub-sub | existing analysis progress publisher | exact |
| `backend/app/api/intraday.py` | route | streaming | existing scoped `analysis_progress` SSE | exact |
| `backend/tests/advanced/test_viewpoints.py` | test | CRUD | `backend/tests/test_analysis_lifecycle.py` | role-match |
| `backend/tests/advanced/test_experiments.py` | test | CRUD | research repository tests / `ResearchRepository` | role-match |
| `backend/tests/advanced/test_evolution.py` | test | CRUD | `backend/tests/test_analysis_lifecycle.py` | role-match |
| `backend/tests/advanced/test_authorization_jobs.py` | test | request-response | `backend/tests/test_analysis_api.py` | role-match |
| `backend/tests/advanced/test_sandbox.py` | test | process / file-I/O | backtest strategy fixture tests | partial-match |
| `backend/tests/advanced/test_workflow.py` | test | event-driven | `backend/tests/test_analysis_graph.py` | exact |
| `backend/tests/advanced/test_api_sse.py` | test | streaming | `backend/tests/test_analysis_host_integration.py` | role-match |
| `frontend/src/lib/api.ts` | client/service | request-response | existing analysis and research API surface | exact |
| `frontend/src/lib/queryKeys.ts` | config/utility | transform | existing analysis query-key factory | exact |
| `frontend/src/components/advanced/{ViewpointPanel,ExperimentRunPanel,EvolutionPromotionPanel,AgentTaskPanel,SandboxStrategyPanel,AuditDetails}.tsx` | component | request-response / streaming | `AnalysisWorkspace.tsx`, `ResearchLibrary.tsx` | role-match |
| `frontend/src/pages/Backtest.tsx` | component/page | request-response | existing strategy-mode composition | exact |
| object analysis host (`StockAnalysis`/portfolio analysis integration) | component/page | request-response | `AnalysisWorkspace.tsx` | exact |
| `frontend/e2e/phase4-advanced-capabilities.spec.ts` | test | request-response / streaming | existing Phase 3 Playwright conventions | role-match |

## Pattern Assignments

### `backend/app/advanced/repository.py`, `viewpoints.py`, `experiments.py`, `evolution.py`, `jobs.py`, and `audit.py` (repository/services, CRUD/event-driven)

**Primary analog:** `backend/app/analysis/repository.py`

**Connection and JSON pattern** (lines 19-57):
```python
def _now() -> str:
    return datetime.now(UTC).isoformat()

def _json(value: object, field: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be JSON serializable") from error

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

**Atomic active-job acquisition and conflict recovery** (lines 59-92):
```python
with self._connection() as connection, connection:
    active = connection.execute(
        """SELECT * FROM analysis_runs WHERE subject_kind = ? AND subject_key = ?
           AND status IN ('queued', 'running') ORDER BY created_at DESC, id DESC LIMIT 1""",
        (subject_kind, subject_key),
    ).fetchone()
    if active is not None:
        return dict(active)
    try:
        connection.execute("INSERT INTO analysis_runs (...) VALUES (?, ?, ?, ?, 'queued', ?)", (...))
    except sqlite3.IntegrityError as error:
        # Re-read the unique active record; never create a competing runnable item.
        ...
```

**Conditional status transition** (lines 124-154):
```python
updated = connection.execute(
    f"UPDATE analysis_runs SET {fields} WHERE id = ? AND status = ?",
    values,
).rowcount
if updated != 1:
    raise ValueError(f"analysis run cannot transition from {from_status} to {to_status}")
```

Use this only for the mutable execution cursor in `advanced_jobs`. Viewpoint versions, evidence, experiment specifications/runs/feedback, candidate provenance, gates, promotions, authorizations, and audits are insert-only facts. A terminal event must be written with its job-state conditional update and idempotency uniqueness in one transaction.

**Immutable version increment** (lines 202-236):
```python
version = int(connection.execute(
    "SELECT COALESCE(MAX(version), 0) FROM analysis_reports WHERE subject_kind = ? AND subject_key = ?",
    (subject_kind, subject_key),
).fetchone()[0]) + 1
connection.execute(
    """INSERT INTO analysis_reports (id, run_id, subject_kind, subject_key, version, report_json, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)""",
    (identifier, run_id, subject_kind, subject_key, version, _json(payload, "validated report"), now),
)
```

For `advanced_viewpoint_versions`, derive the next version inside the transaction and store structured conclusion, confidence, frozen evaluation plan, material-change classification, correction reason, and frozen evidence reference in that inserted row. Do not provide an update path.

**Complete immutable experiment snapshot** (secondary analog: `backend/app/research/repository.py`, lines 230-315):
```python
with self._connection() as connection, connection:
    connection.execute(
        """INSERT INTO research_experiments (... resolved_config_json, input_manifest_json,
               prediction_signal_json, diagnostics_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)""",
        (..., _json(dict(resolved_config), "resolved configuration"),
         _json(dict(input_manifest), "input manifest"), ...),
    )
    connection.execute(
        "INSERT INTO research_experiment_metrics (experiment_id, metric_json, created_at) VALUES (?, ?, ?)",
        (experiment_id, _json(dict(metrics), "metrics"), now),
    )
    for artifact in artifacts:
        connection.execute("INSERT INTO research_experiment_artifacts (...) VALUES (?, ?, ?, ?, ?, ?)", (...))
```

Apply the same all-or-nothing transaction to advanced experiment runs: persist server-derived governed manifest/fingerprint, source asset version, resolved parameters, environment/resource manifest, artifact references, terminal status, and sanitized diagnostic projection together. Store reference/hash metadata only, never raw market time series or unbounded output.

### `backend/app/operational/migrations.py` (migration, CRUD)

**Analog:** existing analysis migration in `backend/app/operational/migrations.py`

**Schema, partial unique index, and immutability-trigger pattern** (lines 232-388):
```sql
CREATE TABLE analysis_runs (
    id TEXT PRIMARY KEY,
    subject_kind TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    ...
);
CREATE UNIQUE INDEX idx_analysis_active_run_subject
ON analysis_runs(subject_kind, subject_key)
WHERE status IN ('queued', 'running');

CREATE TRIGGER analysis_reports_no_update BEFORE UPDATE ON analysis_reports
BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
CREATE TRIGGER analysis_reports_no_delete BEFORE DELETE ON analysis_reports
BEGIN SELECT RAISE(ABORT, 'analysis audit records are immutable'); END;
```

**Migration runner** (lines 396-406):
```python
current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
if current_version > len(MIGRATIONS):
    raise RuntimeError("operational database is newer than this application")
for version, migration in enumerate(MIGRATIONS[current_version:], start=current_version + 1):
    with connection:
        connection.executescript(migration)
        connection.execute(f"PRAGMA user_version = {version}")
```

Append exactly one or more ordered SQL strings to `MIGRATIONS`; do not create a separate database. Apply immutable triggers to all fact tables and reserve `UPDATE` only for legal `advanced_jobs` state transitions and revocation fields where the state contract explicitly needs it. Use foreign keys, `ON DELETE RESTRICT`, enum checks, partial unique active-job indexes, and a unique outcome/idempotency constraint such as `advanced_promotions(job_id)`.

### `backend/app/advanced/workflow.py` (service, event-driven)

**Analog:** `backend/app/analysis/graph.py`

**Async SQLite checkpoint facade** (lines 21-44):
```python
class PersistentAnalysisGraph:
    def __init__(self, *, builder: StateGraph, checkpoint_path: Path, adapter: ConfiguredAnalysisAdapter) -> None:
        self._builder = builder
        self._checkpoint_path = checkpoint_path
        self.adapter = adapter
        self._topology_graph = builder.compile()

    async def ainvoke(self, state: AnalysisGraphState, config: dict[str, Any] | None = None):
        thread_id = (config or {}).get("configurable", {}).get("thread_id")
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("analysis graph requires a server-generated thread_id")
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(self._checkpoint_path)) as saver:
            await saver.setup()
            graph = self._builder.compile(checkpointer=saver)
            return await graph.ainvoke(state, config)
```

**Fixed typed topology** (lines 58-75):
```python
async def validate_frozen_input(state: AnalysisGraphState) -> dict[str, FrozenEvidenceSnapshot]:
    snapshot = FrozenEvidenceSnapshot.model_validate(state["frozen_evidence"])
    if snapshot.context_status != "ready":
        raise ValueError("analysis generation requires ready frozen evidence")
    return {"frozen_evidence": snapshot}

builder = StateGraph(AnalysisGraphState)
builder.add_node("validate_frozen_input", validate_frozen_input)
builder.add_node("generate_validated_body", generate_validated_body)
builder.add_edge(START, "validate_frozen_input")
builder.add_edge("validate_frozen_input", "generate_validated_body")
builder.add_edge("generate_validated_body", END)
```

Phase 4 expands the node sequence to `authorize_and_freeze -> optional_draft -> deterministic_gates -> human_interrupt -> record_once`, but retains these rules: server-generated `thread_id`, async saver per invocation, compact validated state only, and narrow node adapters. The interrupt node is pure; its successor calls the repository's idempotent transaction. Checkpoint state is never an authorization, promotion, or audit source of truth.

### `backend/app/advanced/api.py`, `schemas.py`, `authorization.py`, and `projections.py` (route/model/service/utility, request-response)

**Primary analog:** `backend/app/analysis/api.py`

**Strict request contract** (lines 32-52):
```python
class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_kind: Literal["instrument", "account"]
    subject_key: str = Field(min_length=1, max_length=128)
    focus: str = Field(default="", max_length=256)
```

Use the same `extra="forbid"`, bounded fields, and explicit literal enums for viewpoint input, experiment specs, feedback, approval rationale, task request, and sandbox contract. Do not allow caller-supplied principal, authorization ownership, trusted job/thread IDs, allowlist policy, gate result, or executable authority.

**Server-derived scope and non-enumerating denial** (lines 58-74):
```python
def _scope(request: Request) -> AnalysisSubjectScope:
    resolver = getattr(request.app.state, "resolve_analysis_subject_scope", None)
    if not callable(resolver):
        raise _unavailable()
    try:
        scope = resolver(request)
    except Exception as error:
        raise _unavailable() from error
    if not callable(getattr(scope, "allows", None)):
        raise _unavailable()
    return scope

def _require_subject(request: Request, subject_kind: str, subject_key: str) -> None:
    if not _scope(request).allows(subject_kind, subject_key):
        raise HTTPException(status_code=404, detail="analysis subject not found")
```

Advanced routes resolve `request.state.reviewer_principal` then call the advanced authorization service to derive policy intersection. At creation and again immediately before starting work, reject before a job, graph call, sandbox spawn, or SSE publication exists. Return a stable safe reason and audit reference, never policy or token details.

**Subject ownership before record disclosure, and error translation** (lines 105-129):
```python
report = _repository(request).get_report(report_id)
if report is None:
    raise HTTPException(status_code=404, detail="analysis report not found")
_require_subject(request, str(report["subject_kind"]), str(report["subject_key"]))

def _translate(error: ValueError) -> HTTPException:
    message = str(error)
    if "already" in message or "cannot transition" in message or "no longer matches" in message:
        return HTTPException(status_code=409, detail="analysis state changed; refresh and retry")
    return HTTPException(status_code=400, detail=message)
```

Every advanced lookup must resolve its backing subject/job ownership before projecting a result. Translate state races/replay/approval conflicts to a safe `409`; never return SQL exceptions, sandbox paths, token data, raw model data, or full diagnostics.

**Allowlisted DTO projection** (secondary analog: `backend/app/analysis/projections.py`, lines 8-18 and 72-105):
```python
def report_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = _snapshot(record)
    return {
        "id": str(record["id"]),
        "subject": _subject(record),
        "version": int(record["version"]),
        "status": "validated",
        "generated_at": str(record["created_at"]),
        "evidence_limitations": _limitations(snapshot),
    }
```

Build DTOs explicitly from approved fields. Advanced public projections expose version/human label, stage, target summary, gate/unevaluable/constraint status, timestamps, fingerprints where permitted, and audit references. They must omit raw evidence, source code, model drafts/tokens, token hashes, allowlist internals, file paths, environment, and raw runner output.

### `backend/app/main.py` (config, request-response)

**Analog:** existing analysis domain lifecycle setup at `backend/app/main.py` lines 64-106 and router registration at lines 357-383.

```python
operational = OperationalRepository(store.data_dir / "operational.db")
operational.migrate()
app.state.operational = operational
...
analysis_repository = AnalysisRepository(operational.database_path)
analysis_repository.migrate()
app.state.analysis_repository = analysis_repository
app.state.analysis_graph = build_analysis_graph(
    checkpoint_path=store.data_dir / "analysis_checkpoints.db"
)
...
app.include_router(analysis_api.router)
```

Create the advanced repository/services/checkpoint graph in the same lifespan after `operational` is available, attach narrowly named dependencies to `app.state`, and include one advanced router. It remains one FastAPI app, one container, and one operational SQLite file. Advanced services read market data only through the existing governed repository/backtest service boundary.

### `backend/app/services/quote_service.py` and `backend/app/api/intraday.py` (service/route, pub-sub/streaming)

**Primary analog:** existing scoped analysis progress channel.

**Scope filter before queueing plus bounded queue** (`quote_service.py` lines 153-162):
```python
def push_analysis_progress(self, progress: dict[str, str]) -> None:
    scope = self._analysis_scope
    if scope is None or not scope.allows(progress["subject_kind"], progress["subject_key"]):
        return
    with self._lock:
        self._analysis_progress.append(progress)
        if len(self._analysis_progress) > self._max_analysis_progress:
            self._analysis_progress = self._analysis_progress[-self._max_analysis_progress:]
        self._event.set()
```

**Fan-out only durable state** (`quote_service.py` lines 393-404):
```python
def notify_analysis_progress(self, *, run_id: str, subject_kind: str, subject_key: str, status: str) -> None:
    progress = {"run_id": run_id, "subject_kind": subject_kind, "subject_key": subject_key, "status": status}
    for sub in self._snapshot_subscribers():
        sub.push_analysis_progress(progress)
```

**SSE subscription lifecycle** (`api/intraday.py` lines 142-155 and 187-221):
```python
analysis_scope = _analysis_scope(request) if qs is not None else None
...
sub = qs.subscribe(analysis_scope=analysis_scope)
try:
    while True:
        await asyncio.to_thread(sub.wait, 5.0)
        data = sub.pop()
        for progress in data["analysis_progress"]:
            yield {"event": "analysis_progress", "data": json.dumps(progress)}
finally:
    qs.unsubscribe(sub)
```

Add a separate `advanced_progress` list/event and an `advanced_scope` resolver; do not overload analysis event semantics. Publish only committed, allowlisted advanced job stage (`authorized`, `frozen`, `drafted`, `gates_complete`, `awaiting_review`, `recorded`, `rejected`), human-safe subject label/reference, and timestamp. No raw tokens, model content, strategy code, policy, or diagnostics. The advanced persistent job state is the source of truth; the in-memory queue is delivery-only.

### `backend/app/advanced/sandbox.py` (service, process/file-I/O)

**Closest analog:** `backend/app/backtest/strategy.py` lines 74-98 and 156-161.

```python
class StrategyBacktestService:
    def __init__(self, engine: BacktestEngine, strategy_engine: StrategyEngine) -> None:
        self.engine = engine
        self.strategy_engine = strategy_engine

    def run(self, config: StrategyBacktestConfig, ...) -> StrategyBacktestResult:
        t0 = time.perf_counter()
        run_id = uuid.uuid4().hex[:10]
        def _err(msg: str) -> StrategyBacktestResult:
            return StrategyBacktestResult(
                run_id=run_id, config=self._config_to_dict(config), error=msg,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
        ...
        panel = self.engine.load_panel(config.symbols, load_start, load_end, asset_type=config.asset_type)
        if panel.is_empty():
            return _err("无数据，请检查日期范围或先运行盘后管道")
        governed_input_manifest = self._governed_input_manifest(panel, config)
```

**Governed manifest pattern** (`strategy.py` lines 291-312):
```python
source_reference = {
    "loader": "BacktestEngine.load_panel",
    "source_kind": "governed_enriched_parquet",
    "asset_type": config.asset_type,
    "schema": schema,
    "observed_start": str(observed_start),
    "observed_end": str(observed_end),
    "loaded_row_count": loaded.height,
}
return {
    **source_reference,
    "source": "governed_backtest_engine",
    "revision": sha256(encode(schema)).hexdigest(),
    "fingerprint": sha256(encode(source_reference)).hexdigest(),
}
```

Reuse only the bounded result/manifest interface and governed-data access, not `StrategyEngine` module loading. The existing engine dynamically imports registered files and is explicitly unsafe for SAFE-02. Phase 4 validates a strict Pydantic contract, AST and import allowlists, then runs only after a harmless capability probe confirms Linux isolation; launch a fresh process group with minimal environment, no network, constrained filesystem, CPU/memory/wall time, output cap, timeout kill, and redacted terminal result. Capability uncertainty is a fail-closed validation rejection, not a host-process fallback.

### `frontend/src/lib/api.ts` and `frontend/src/lib/queryKeys.ts` (client/config, request-response)

**API client analog:** `frontend/src/lib/api.ts` lines 10-37 and the Phase 3 analysis type family at lines 177-342.

```typescript
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  if (!(init?.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  Object.assign(headers, init?.headers as Record<string, string> | undefined)
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    // normalize FastAPI detail, toast except global-auth 401, then throw
    ...
  }
  return res.json() as Promise<T>
}
```

Add exact advanced request/response DTO unions and `api.advanced*` methods here. Do not add direct `fetch` from components or pass client-derived authority. Model status as explicit unions such as unevaluable, insufficient-sample, rejected, constraint-failed, awaiting-review, and recorded so UI cannot infer success from missing data.

**Resource-scoped cache keys:** `frontend/src/lib/queryKeys.ts` lines 46-63.
```typescript
analysisReports: (subjectKind: string, subjectKey: string) => ['analysis', 'reports', subjectKind, subjectKey] as const,
analysisReport: (subjectKind: string, subjectKey: string, reportId: string) => ['analysis', 'report', subjectKind, subjectKey, reportId] as const,
analysisSignalHistory: (subjectKind: string, subjectKey: string, signalId: string) => ['analysis', 'signal-history', subjectKind, subjectKey, signalId] as const,
```

Use `advanced` namespace keys that retain every object/version/run/task identifier. Mutations invalidate only affected viewpoint/spec/run/candidate/task/audit keys, not a global advanced cache.

### `frontend/src/components/advanced/*.tsx` and object analysis integration (components, request-response/streaming)

**Primary analog:** `frontend/src/components/analysis/AnalysisWorkspace.tsx`

**Local resource queries and localized mutation state** (lines 15-30):
```tsx
const reportsQuery = useQuery({ queryKey: QK.analysisReports(subject.kind, subject.key), queryFn: () => api.analysisReports(serverSubject), placeholderData: keepPreviousData })
const reportQuery = useQuery({ queryKey: QK.analysisReport(subject.kind, subject.key, latestReport?.id ?? 'none'), queryFn: () => api.analysisReport(latestReport!.id), enabled: !!latestReport, placeholderData: keepPreviousData })
const startRun = useMutation({
  mutationFn: () => api.analysisStartRun(serverSubject),
  onSuccess: result => { sessionStorage.setItem(`${storageKey}:run`, result.run.id) },
})
```

**Accessible in-place states and tabs** (lines 44-62):
```tsx
<section aria-label={`${title} 分析工作区`} className="space-y-4">
  ...
  {reportsQuery.isError && reportsQuery.data && <p role="status">刷新分析报告失败，正在显示上次结果。...</p>}
  <div id={`${ids}-${tab}-panel`} role="tabpanel" aria-labelledby={`${ids}-${tab}`}>
    {tab === 'report' && (...)}
  </div>
</section>
```

Follow this for `ViewpointPanel` in the selected stock/financial/portfolio analysis host: per-subject keys, `keepPreviousData`, no free-form subject scope, real tabs, local loading/error/empty states, and `<details>` or existing dialog for evidence/audit. The browser renders server DTOs and never recomputes frozen outcomes, material stance changes, calibration, gates, or authorization.

**Backtest composition analog:** `frontend/src/pages/Backtest.tsx` lines 36-97.
```tsx
<main className="flex-1 min-h-0 px-3 pb-3 pt-3 lg:px-4 lg:pb-4">
  {activeTab === 'strategy' && (
    <div id="backtest-mode-panel-strategy" role="tabpanel" ... className="space-y-4">
      <StrategyBacktest /><ResearchLibrary /><ExperimentComparison />
    </div>
  )}
</main>
```

Append the experiment-run, evolution/promotion, and sandbox panels to the existing `strategy` mode after the research library/comparison. Do not add a top-level advanced route, sidebar, shell, or a parallel data client.

**Dense immutable record disclosure analog:** `frontend/src/pages/backtest/ResearchLibrary.tsx` line 14.
```tsx
<details className="mt-2 text-[11px] text-muted">
  <summary className="cursor-pointer">工件 {experiment.artifacts.length} 个</summary>
  <ul className="mt-1 space-y-1">...</ul>
</details>
```

Use semantic tables for versions, runs, gates, and audit lists; retain visible status/time/range/reason/audit columns under horizontal overflow on small screens. Reuse `<details>` for manifests, evidence, gate detail, and sanitized diagnostics. Promotion requires the existing modal/dialog pattern with a ten-character rationale validation, focus handling, and no implicit mutation.

### `backend/tests/advanced/*` and `frontend/e2e/phase4-advanced-capabilities.spec.ts` (tests)

**Graph test analog:** `backend/tests/test_analysis_graph.py` lines 30-44, 47-79, and 82-96.
```python
topology = graph.get_graph()
node_names = set(topology.nodes)
edges = {(edge.source, edge.target) for edge in topology.edges}
assert edges == {
    ("__start__", "validate_frozen_input"),
    ("validate_frozen_input", "generate_validated_body"),
    ("generate_validated_body", "__end__"),
}
with pytest.raises(ValueError, match="thread_id"):
    await graph.ainvoke({"frozen_evidence": _snapshot()}, {"configurable": {}})
```
Test the concrete Phase 4 topology, absence of authority side effects in the interrupt node, server-generated thread ID requirement, persistence resume, and repository `record_once` uniqueness.

**Repository/lifecycle test analog:** `backend/tests/test_analysis_lifecycle.py` lines 85-130 and 133-155.
```python
proposal = service.evaluate_completed_analysis(
    subject_kind="stock", subject_key="600519.SH", run_id=run["id"], report_id=report["id"]
)
repeated = service.evaluate_completed_analysis(
    subject_kind="stock", subject_key="600519.SH", run_id=run["id"], report_id=report["id"]
)
assert repeated["id"] == proposal["id"]
assert len(repository.list_lifecycle_reviews(subject_kind="stock", subject_key="600519.SH")) == 1
```
Use temp SQLite, assert foreign keys/triggers/partial indexes, and test valid plus conflict transitions through public services/routes rather than inspecting implementation-only state.

**API/SSE test analog:** `backend/tests/test_analysis_api.py` lines 168-186, 189-210, and 263-279.
```python
response = client.post(
    "/api/analysis/reviews/review-1/confirm",
    json={"window_days": 20, "reviewer": "browser-controlled"},
)
assert response.status_code == 422
...
assert allowed.pop()["analysis_progress"] == [{
    "run_id": "run-600519", "subject_kind": "instrument",
    "subject_key": "600519.SH", "status": "completed",
}]
assert denied.pop()["analysis_progress"] == []
```

**Required hostile matrix:** AST/import/dynamic execution/file/network/process/timeout/memory outputs; expired/revoked/out-of-scope/rate-limited creation; revoke after enqueue before start; repeated request/approval/resume. In every denied case assert no sandbox/provider invocation, no runnable job/SSE start, safe audit exists, and no raw diagnostic disclosure.

**Frontend/E2E analog:** `AnalysisWorkspace.tsx` lines 44-62 and `Backtest.tsx` lines 48-81. Use fixtures for immutable versions, unevaluable data, incomplete gates, successful promotion with dialog rationale, and task-stage updates. Assert the specified 1440px/1024px/375px behavior, keyboard tabs/dialog focus, `role=alert` for security rejections, and no presentation of raw identifiers, tokens, code, paths, or model text.

## Shared Patterns

### Immutable SQLite Facts
**Sources:** `backend/app/operational/migrations.py` lines 232-388; `backend/app/analysis/repository.py` lines 202-236.

Apply to all viewpoint/evidence/evaluation/spec/run/feedback/candidate/gate/promotion/audit/sandbox fact tables. Facts are appended with a version or foreign-key lineage; trigger blocks `UPDATE`/`DELETE`. Only the explicit execution cursor has conditional state updates.

### Authoritative Session Principal and Scope
**Sources:** `backend/app/main.py` lines 323-354; `backend/app/services/auth.py` lines 189-201; `backend/app/analysis/api.py` lines 58-74.

```python
token = request.cookies.get(auth_api.COOKIE_NAME)
if token and auth_service.is_valid_session(token):
    request.state.reviewer_principal = auth_service.resolve_authenticated_reviewer(token)
    return await call_next(request)
```

Every Phase 4 creation, read, approval, and resume derives its principal from `request.state`. The advanced token/policy is an additional server-side authorization record, never a browser authority claim. Revalidate at runnable-job creation and immediately before work.

### Safe Projections and Errors
**Sources:** `backend/app/analysis/projections.py` lines 8-18 and 72-105; `backend/app/analysis/api.py` lines 125-129.

DTOs are hand-built allowlists. Safe errors distinguish conflict, unavailable, field validation, authorization rejection, and terminal constraint reason without exposing policy contents, tokens, raw prompt/model output, source code, paths, environment, traceback, or raw process output.

### Governed Backtest Inputs
**Source:** `backend/app/backtest/strategy.py` lines 156-161 and 291-312.

Advanced experiments/evolution use `BacktestEngine` and its returned governed-input manifest/reference. Persist fingerprints, schema/revision, observed dates, parameters, cost assumptions and artifacts; never copy market prices into SQLite or bypass the engine.

### Scoped Durable SSE
**Sources:** `backend/app/services/quote_service.py` lines 153-162 and 393-404; `backend/app/api/intraday.py` lines 142-155 and 187-221.

Commit state first, publish an allowlisted persisted stage second, scope filter before every subscriber queue, bound the queue, and unsubscribe in `finally`. Advanced tasks do not inherit the backtest stream's `_running_jobs` in-memory semantics.

### Frontend Query Ownership and Workspace Placement
**Sources:** `frontend/src/lib/queryKeys.ts` lines 46-63; `frontend/src/components/analysis/AnalysisWorkspace.tsx` lines 15-55; `frontend/src/pages/Backtest.tsx` lines 84-97.

Keep query state scoped by resource identity, use typed `api.ts`, preserve last successful data during local refresh, surface domain uncertainty/rejection before optimistic conclusions, and place advanced panels in existing Analysis and Backtest workspaces.

## Important Non-Analog

| Existing code | Why it must not be copied as the Phase 4 security implementation |
|---|---|
| `backend/app/api/backtest.py` lines 266-611 | `_running_jobs` is process memory, serves raw progress/result SSE, and is intentionally only a short-lived reconnect UX mechanism. It cannot provide durable authorization, revalidation, audit, replay safety, or advanced task truth. |
| `backend/app/strategy/engine.py` dynamic strategy loading (referenced by `main.py` lines 225-235) | Registered strategy loading includes filesystem modules in the host application process. SAFE-02 must never save arbitrary custom code into those directories or execute it via `importlib`; use it only as a read-only registered-parent strategy source. |

## No Analog Found

| File / concern | Role | Data Flow | Reason / planner direction |
|---|---|---|---|
| Linux isolation capability probe and fail-closed launcher | security service | process / file-I/O | No existing subprocess sandbox. Establish the harmless probe first; refuse all custom execution if namespace/network/filesystem isolation cannot be demonstrated. |
| `advanced_progress` stage contract | SSE DTO | pub-sub | Existing analysis progress gives delivery/scope pattern but not advanced stages. Define a narrow new persisted-stage enum; never proxy raw graph/model/runner events. |

## Metadata

**Analog search scope:** `backend/app/{analysis,backtest,research,operational,api,services}`, `frontend/src/{lib,pages,components}`, `backend/tests`

**Files scanned:** 22 concrete source/test files plus phase artifacts

**Pattern extraction date:** 2026-07-12
