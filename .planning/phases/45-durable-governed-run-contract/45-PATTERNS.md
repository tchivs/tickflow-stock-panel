# Phase 45: Durable Governed Run Contract - Pattern Map

**Mapped:** 2026-08-08  
**Phase directory:** `.planning/phases/45-durable-governed-run-contract`  
**Files analyzed:** 11 mandated implementation files, 5 supporting API/analysis files, and 8 focused test files  
**Analogs found:** 10 / 10 likely artifact groups (exact matches for persistence, migration, artifact, lifecycle, checkpoint, DTO, projection, API, and tests; new run-domain composition has no one-file equivalent)

## Scope and Grounding

`45-CONTEXT.md` is locked: `operational.db` remains authoritative; new Alpha run work belongs under `backend/app/research/`; run specifications/snapshots are immutable; candidates/events are append-only; lifecycle transitions are server-owned; duplicate requests are idempotent; checkpoints are recovery cursors rather than authority; and large payloads are bounded artifact references. There is no `45-RESEARCH.md` in the phase directory, so the file/symbol list below is derived from the locked context plus `.planning/research/ARCHITECTURE.md` and current repository seams.

Names marked **[RECOMMENDATION]** are likely Phase 45 file/symbol names, not existing code. Existing analog names and line references are observed in the repository. Phase 45 must not copy the `advanced_*` domain authority: those files provide transaction, lifecycle, checkpoint, and projection patterns only.

## File Classification

| Likely new/modified file or symbol | Role | Data flow | Closest analog | Match quality | Reusable behavior | Adaptation needed | Anti-pattern to avoid |
|---|---|---|---|---|---|---|---|
| `backend/app/operational/migrations.py` — append a Phase 45 `MIGRATIONS` entry | migration/config | schema transform | `MIGRATIONS` and `migrate_operational_db` (lines 7, 1864-1919) | exact infrastructure | Versioned scripts, FK/UNIQUE/CHECK/indexes, immutable triggers, atomic `user_version` update | Add run/snapshot/candidate/event/checkpoint tables in research naming; keep only small metadata in SQLite; explicitly model guarded cursor columns separately from immutable facts | Editing old migration entries, doing schema work in request handlers, using `advanced_*` tables, or storing unbounded payloads |
| `backend/app/research/repository.py` — `ResearchRepository` run/snapshot/candidate/event/checkpoint methods **[RECOMMENDATION]** | repository | CRUD + append-only event stream | `ResearchRepository.create_experiment`, `insert_universe_membership`, `create_wf_plan`, `record_wf_fold` | exact role; closest mixed data flow | Short-lived parameterized connections, canonical JSON, FK-bound writes, append-only rows, JSON row unpacking, precise `IntegrityError` mapping | Add narrow methods for frozen run identity, input snapshot, candidate ledger, event sequence/idempotency, checkpoint verification, and guarded lifecycle cursor; event+fact commit must happen before publish | Treating `JobStore`/SSE memory as the ledger, updating candidate/event rows in place, returning an existing run when the request digest differs, or collapsing all candidate outcomes into a winner |
| `backend/app/research/models.py` extension or `backend/app/research/run_contract.py` **[RECOMMENDATION]** — `ResearchInputSnapshot`, `AlphaFactoryRun`, `AlphaCandidate`, `AlphaRunEvent`, `AlphaRunCheckpoint` | model/value object | transform / request-response | `CompositeModel` frozen dataclass and `_input_snapshot_sha256` (models.py:34-76) | role-match | Frozen dataclasses, stable canonical input digest, explicit snapshot identity, no live hand-off | Define bounded fields for DSL/grammar/vocabulary/policy, seed/budgets, universe/date/fold geometry, costs, code/data manifest, run/candidate/event/checkpoint status; canonicalize before persistence and bind checkpoint to snapshot + manifest digests | Mutable dicts as authority, digesting only display names, serializing Python/pickle/provider state, or resolving current constituents during replay |
| `backend/app/research/artifacts.py` — generic run artifact descriptor verification **[RECOMMENDATION]** | utility/artifact I/O | file I/O | `ArtifactDescriptor`, `EvaluationArtifactService.write_bundle`, `_namespace`, `_write_json` (lines 17-126) | exact file-I/O | Managed root, opaque run ID validation, path containment, canonical bytes, SHA-256/size/type metadata, `O_EXCL`, `fsync`, collision/partial-write failure | Keep existing evaluation namespace compatibility; add read/verify behavior that checks managed relative path, bytes, size and lowercase SHA-256 before a checkpoint/event can advance; failure must be terminal/closed | Accepting an arbitrary absolute/path-traversal path, overwriting an existing artifact, trusting only a stored checksum without reading bytes, or embedding market/provider payloads in SQLite |
| `backend/app/research/run_service.py` — `ResearchRunService` **[RECOMMENDATION]** | service/controller | request-response + event-driven | `AnalysisService.start_run` (analysis/service.py:33-124) plus `AdvancedJobService.run_authorized_job` (jobs.py:182-267) | role/data-flow composite | Server allocates identity, freezes evidence before work, short-circuits duplicate acquisition, records safe failure, invokes untrusted adapter, and publishes only after durable commit | Make the run service policy/lifecycle owner: create/get/replay/retry/cancel, append event/candidate/checkpoint, check idempotency and stale cursors, and link retry runs without mutating prior facts; do not import authorization or execution collaborators | Letting a worker/provider select scope, mutate frozen inputs, mark gates/OOS, or publish before its transaction commits; treating a provider exception as a fabricated success |
| `backend/app/research/schemas.py` or `backend/app/research/run_schemas.py` **[RECOMMENDATION]** — strict create/retry/cancel/event DTOs | schema/contract | request-response | `StrictAdvancedModel`, `FrozenStrategyScope`, `ExperimentRunRequest`, `AuthorizationTaskRequest` (schemas.py:10-13, 65-98, 123-173) | exact validation style | `extra="forbid"`, bounded strings/lists/maps, literals, lowercase SHA-256 regexes, cross-field validators | Accept intent only; server derives run ID, policy, manifest, evidence refs, event sequence, statuses and actor/source; reject client-supplied authority/checkpoint/event status; preserve raw diagnostics privately | `dict` request bodies with browser-supplied IDs/status/gates, permissive extra fields, unbounded JSON, or allowing a model/worker to provide authority |
| `backend/app/research/projections.py` **[RECOMMENDATION]** — `run`, `snapshot`, `candidate`, `event`, `checkpoint` safe projections | projection | transform/read | `backend/app/advanced/projections.py` functions `job`, `sandbox_run`, `experiment_specification`, `candidate`, `gate` (lines 8-22, 56-84, 126-174) | exact role | Hand-built allowlists, safe scalar/mapping helpers, explicit terminal/status/evidence fields, omission of principal/policy/source/path/diagnostics | Expose run status, bounded progress, sequence/checksum and artifact descriptors only; expose diagnostics as bounded safe reason codes; never return raw prompts, provider secrets, filesystem paths, raw panels, or internal policy | `dict(record)` passthrough, leaking raw manifest/provider data, exposing artifact paths as authority, or accepting projection values back into mutation endpoints |
| `backend/app/api/research_alpha.py` or `backend/app/api/research.py` **[RECOMMENDATION]** — create/get/retry/cancel/history routes | API route | request-response; history read | `research_panels._repository` + typed routes (research_panels.py:31-40, 81-115, 217-250), and `walkforward_sse` route (walkforward_sse.py:77-188) | exact route/projection style; SSE transport only conceptual | Router prefix/tags, app-state repository lookup with 503, typed `response_model`, bounded `Query` limits, repository-row-to-DTO mapping, replay then terminal event | Phase 45 needs minimal create/get/replay/retry/cancel/event-history seam; API must call service, not write tables; Phase 50 owns live SSE, so history may be JSON/polling now and should preserve monotonic sequence semantics | Reusing `/api/research/wf` volatile `_wf_jobs` as authority, browser-provided run/event IDs, raw exception/path responses, or adding execution/broker actions |
 `backend/app/services/pipeline_jobs.py` adapter or a thin research worker bridge **[RECOMMENDATION]** | adapter/worker | event-driven / single-flight | `AdvancedJobService` workflow/publisher seam (jobs.py:47-55, 182-216, 260-267) | role-match | Worker is a replaceable untrusted adapter; it requests transitions/checkpoints and receives committed progress; service owns policy | Keep JobStore progress/stale recovery separate from run facts; bridge worker job ID to server-owned run ID and durable cursor; retries must query durable state first | Inferring scientific completion from a progress file, allowing worker policy overrides, or deleting/restarting a run when a JobStore file disappears |
| `backend/tests/test_phase45_migrations.py` **[RECOMMENDATION]** | test | schema/invariant | `test_operational_migrations.py::test_phase10_append_only_tables_migrate_with_constraints_and_idempotence` and `::test_phase13_wf_tables_migrate_with_constraints_and_idempotence` (lines 339-451, 736-861) | exact test structure | In-memory SQLite, migration prefix/full migration, rerun no-op, FK/CHECK/UNIQUE/triggers, direct `IntegrityError` assertions | Assert all Phase 45 tables, composite uniqueness keys, event sequence/idempotency constraints, run status checks, snapshot digest/FK binding, checkpoint stale/mismatch rejection, and immutable UPDATE/DELETE triggers | Testing only table existence, testing only happy paths, weakening checks to application-only validation, or using a live/shared DB in unit tests |
| `backend/tests/research/test_run_contract.py` and `backend/tests/research/test_run_service.py` **[RECOMMENDATION]** | test | CRUD/event-driven/recovery | `test_authorization_jobs.py` idempotency/revalidation (lines 167-222), `test_analysis_lifecycle.py` immutable/idempotent lifecycle, `test_advanced/test_workflow.py` checkpoint/replay (lines 85-185) | exact scenario patterns | Fake clocks/spies, duplicate invocation assertions, no-work-on-denial, repeated resume/outcome exactly once, process-independent repository reads | Add crash/restart simulation, duplicate start/retry/cancel, new linked retry, append every candidate outcome, commit-before-publish, stale/missing/checksum-bad artifact/cursor fail-closed cases | Asserting logs or implementation details instead of durable observable facts; using a fake in-memory ledger that cannot survive a new repository instance |
| `backend/tests/api/test_research_alpha.py` **[RECOMMENDATION]** | API test | request-response/replay | `test_research_panels.py` typed route tests (lines 270-330, 338-398, 441-526) and `test_walkforward_sse.py` replay tests (lines 32-161) | exact API test style | `TestClient`, isolated temporary repository/app state, empty-list/404/DTO-extra-field tests, replayed progress and terminal event assertions | Verify 400/404/409/503 boundaries, server-owned IDs/status, durable event ordering after a fresh repository, safe projection redaction, and no duplicate event on repeated request | Only asserting status 200, accepting browser authority, or asserting an in-memory event list after restart |

## Pattern Assignments

### 1. Migration and schema: `backend/app/operational/migrations.py`

**Analog:** existing versioned `MIGRATIONS` tuple and `migrate_operational_db`.

Append a new migration script; do not edit historical scripts. The current migration runner splits complete SQL statements so compound triggers are preserved, wraps each version in `BEGIN … PRAGMA user_version … COMMIT`, rolls back on any exception, and restores foreign keys in `finally`:

```python
# backend/app/operational/migrations.py:1864-1919
MIGRATIONS: tuple[str, ...] = (...)


def _migration_statements(script: str) -> tuple[str, ...]:
    ...
    if sqlite3.complete_statement(candidate):
        statements.append(candidate)
    ...


def migrate_operational_db(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version > len(MIGRATIONS):
        raise RuntimeError("operational database is newer than this application")
    for version, migration in enumerate(MIGRATIONS[current_version:], start=current_version + 1):
        ...
        transactional_sql = f"BEGIN;\n{transactional_sql}\nPRAGMA user_version = {version};\nCOMMIT;"
        try:
            connection.executescript(transactional_sql)
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.execute("PRAGMA foreign_keys = ON")
```

Use the existing Phase 10/13 DDL shape: PK identity, FK `ON DELETE RESTRICT`, enum `CHECK`s, lowercase SHA-256 length checks, indexes for replay queries, and `BEFORE UPDATE`/`BEFORE DELETE` triggers for immutable facts. The existing walk-forward migration specifically separates plans/folds, indexes them, and makes facts append-only; its test verifies forward-only creation, rerun idempotence, FK failures, unique exactly-once keys, SHA checks, and triggers (`test_operational_migrations.py:736-861`).

**Phase 45 schema adaptation:**

- Immutable fact tables should include run snapshot digest and bounded JSON/reference columns; candidate/event/checkpoint references must have FK/UNIQUE constraints.
- Keep the run's mutable portion narrow: status, timestamps, terminal reason, last committed event sequence, and perhaps a guarded cursor. Do not make the entire run row mutable.
- Event uniqueness should enforce `(run_id, seq)` and a durable idempotency key. If a retry has the same idempotency key but a different canonical request, return a conflict rather than silently returning the old row.
- Checkpoint rows should bind `run_id`, snapshot digest, manifest digest, referenced event sequence/checksum and cursor checksum. A stale/mismatched cursor must fail closed before work is requested.
- Use triggers on snapshots/candidates/events/checkpoint facts to block UPDATE/DELETE. If a current checkpoint projection needs replacement, append a new cursor fact or use a narrowly guarded current cursor table with explicit invariants.

**Do not copy:** `advanced_*` table names or authorization facts. Context D-02 explicitly keeps Alpha tables in research, even though advanced migrations demonstrate useful trigger syntax.

### 2. Repository: `ResearchRepository` in `backend/app/research/repository.py`

**Analog:** `ResearchRepository` connection and append-only methods. Every repository owns the same operational database and enables foreign keys per short-lived connection:

```python
# backend/app/research/repository.py:74-93
class ResearchRepository:
    """Parameterized, short-lived SQLite access for immutable research metadata."""

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

    def migrate(self) -> None:
        with self._connection() as connection:
            migrate_operational_db(connection)
```

Reuse `_json`/`_unpack_json` and `_wf_sha256` rather than introducing a second serializer or digest convention:

```python
# backend/app/research/repository.py:25-60

def _json(value: object, field: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be JSON serializable") from error


def _unpack_json(row: sqlite3.Row | None, columns: Mapping[str, str]) -> dict[str, Any] | None:
    ...


def _wf_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
```

For complete immutable facts, follow `create_experiment`: validate all descriptors before opening the transaction, insert the parent and child facts in one `with self._connection() as connection, connection:` block, select the fully decoded row before returning, and map only the relevant uniqueness conflict to a domain `ValueError` (`repository.py:319-404`). For append-only events, follow `insert_universe_membership`: validate enum/domain fields, insert one row, map conflicts, then return the persisted row with decoded provenance (`repository.py:577-623`). For pinned geometry and exactly-once folds, follow `create_wf_plan`/`record_wf_fold`: a same-identity reinsert may return the existing immutable row only after comparing canonical geometry; a changed geometry must raise; OOS uniqueness and malformed checksum/FK errors must not be conflated (`repository.py:907-1110`).

**Recommended Phase 45 repository symbol decomposition [RECOMMENDATION]:**

- `create_alpha_run(...)` / `get_alpha_run(...)` / `list_alpha_runs(...)`: canonical request digest idempotency, immutable snapshot linkage, guarded lifecycle cursor.
- `append_candidate_attempt(...)` / `list_candidates(...)`: one append-only row per attempted candidate, including invalid/duplicate/failed/rejected/admitted/cancelled/budget-exhausted outcomes and lineage/evidence references.
- `append_run_event(...)` / `list_run_events(after_seq=...)`: assign sequence inside the same transaction as the fact, enforce idempotency, and return rows ordered by `(seq, event_id)`.
- `append_checkpoint(...)` / `get_latest_valid_checkpoint(...)`: verify referenced event/candidate facts and snapshot/manifest checksums before returning a resumable cursor.
- `transition_alpha_run(...)`: guarded `WHERE id = ? AND status = ?`; transitions and corresponding event/audit facts commit atomically.
- `retry_alpha_run(...)` / `cancel_alpha_run(...)`: duplicate request returns existing durable state; retry either resumes a validated cursor or creates a linked child run, never overwrites the parent.

The exact decomposition is discretionary, but every method should preserve the repository's parameterized SQL and short transaction style. A worker-facing method must not expose direct SQL mutation outside this repository.

### 3. Run contract models: `backend/app/research/models.py` or a dedicated `run_contract.py`

**Analog:** `CompositeModel` and `_input_snapshot_sha256` in `backend/app/research/models.py:34-76`.

```python
# backend/app/research/models.py:34-76
@dataclass(frozen=True, slots=True)
class CompositeModel:
    model_id: str
    name: str
    revision_ids: tuple[str, ...]
    weighting: CompositeWeighting
    weights: Mapping[str, float]
    input_snapshot_sha256: str
    created_at: str
    frame: pl.DataFrame = field(default_factory=pl.DataFrame)


def _input_snapshot_sha256(...):
    payload = json.dumps(
        {...}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload).hexdigest()
```

The new run objects should be frozen (`dataclass(frozen=True, slots=True)` where appropriate), explicit about status literals and bounded JSON payloads, and expose canonical serialization/digest helpers. The snapshot digest must include all D-04 identity dimensions, not merely the user request: DSL/grammar/vocabulary/policy versions, seed, budgets, objective/cost policy, universe and measured date range, fold geometry, code/data manifest, artifact manifest and any provider metadata relevant to replay. A changed input must produce a distinct run identity or a linked retry child.

`CompositeModel` is only a model/value-object analog. It is not a reason to put a Polars frame, executable AST object, provider response, or arbitrary Python state in the Phase 45 SQLite run contract. Replay reads frozen manifest/facts; it does not call current universe resolution or mutate historical rows.

### 4. Artifact references: `EvaluationArtifactService` in `backend/app/research/artifacts.py`

**Analog:** immutable managed artifact writes, `ArtifactDescriptor`, `_namespace`, and `_write_json` (lines 17-126).

```python
# backend/app/research/artifacts.py:51-75, 78-126
namespace = self._namespace(evaluation_run_id)
namespace.mkdir(parents=True, exist_ok=False)
...
content = json.dumps(
    payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
).encode("utf-8")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "wb") as handle:
    handle.write(content)
    handle.flush()
    os.fsync(handle.fileno())
...
return ArtifactDescriptor(
    evaluation_run_id=evaluation_run_id,
    relative_path=path.relative_to(self.root.parent).as_posix(),
    content_type="application/json",
    byte_size=len(content),
    checksum_sha256=sha256(content).hexdigest(),
    created_at=datetime.now(UTC).isoformat(),
)
```

For Phase 45, retain the path containment and exclusive creation behavior, then add a read-side verification seam (or keep it in the new run service) that opens only a managed relative path and recomputes SHA-256/size/type. The transaction that appends an event/checkpoint must occur only after required artifact verification succeeds. If a path is missing, bytes differ, JSON is not bounded/canonical, or metadata mismatches, persist a fail-closed reason where appropriate and do not advance the cursor. Do not reuse an existing namespace for a second run or checkpoint.

### 5. Lifecycle service: `ResearchRunService` **[RECOMMENDATION]**

**Closest analogs:** `AnalysisService.start_run` and `AdvancedJobService`.

`AnalysisService.start_run` establishes the important ordering: validate and authorize, atomically acquire a server run, return the existing run when acquisition lost a race, freeze evidence before graph/provider work, persist a failure on configuration/validation errors, and complete only after the report is persisted (`backend/app/analysis/service.py:33-124`). Use that ordering, but replace analysis-specific evidence with the Phase 45 snapshot and durable event/candidate/checkpoint facts.

`AdvancedJobService.run_authorized_job` supplies the worker seam: non-queued jobs return existing state, a before-work hook runs before transition, the workflow gets a server-generated thread ID, and failures become an explicit terminal state rather than a fabricated result (`backend/app/advanced/jobs.py:182-216`). Its `_advance` persists the transition and audit fact before `_publish`, and passes `committed=True` to the publisher (`jobs.py:238-267`). This is the exact commit-before-notify principle required by D-05.

**Adaptation:**

- `create`: validate bounded intent; server resolves/finalizes snapshot; transaction inserts run + `run_created` event and returns durable projection.
- `start`/`resume`: guarded transition to `running`; worker can request only a server-owned transition/checkpoint.
- `retry`: idempotency lookup first; resume only from a verified cursor, otherwise create a new linked run with a new digest.
- `cancel`: append `cancel_requested`, then cooperative `cancelled` terminal event; never turn a terminal run back into running.
- `replay`: read only frozen snapshot and durable facts; no current-data lookup, no OOS consumption, no writes.
- `publish`: callback/JobStore notification only after transaction exits successfully; publisher failure cannot roll back committed facts or create a second event.

Do not carry over advanced authorization/policy/research-strategy semantics. Phase 45's worker adapter is untrusted and cannot grant execution or promotion authority.

### 6. Strict schemas: `research/run_schemas.py` **[RECOMMENDATION]**

**Analog:** `StrictAdvancedModel` and bounded requests in `backend/app/advanced/schemas.py:10-13, 65-98, 113-173`.

```python
class StrictAdvancedModel(BaseModel):
    """Reject undeclared fields at every browser or provider trust boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
```

`FrozenStrategyScope` demonstrates bounded identifiers, unique symbol lists, bounded parameter maps and cross-field date validation (`schemas.py:65-98`). `ExperimentRunRequest` demonstrates a lowercase 64-character governed fingerprint, bounded parameters and a bounded resource manifest (`schemas.py:123-128`). `AuthorizationTaskRequest` demonstrates a bounded idempotency key (`schemas.py:168-173`). Use these as validation building blocks, but do not expose browser authority fields such as `status`, `event_seq`, `policy_version`, `snapshot_digest`, `candidate_id` for mutation, or `checkpoint_ref`.

Recommended request models include `AlphaRunCreateRequest`, `AlphaRunRetryRequest`, `AlphaRunCancelRequest`, and read DTOs for run/event/candidate/checkpoint. Use Pydantic validation for shape and bounds; server/service code validates ownership, run membership, digest equality, transition legality, artifact presence and idempotency semantics.

### 7. Public projections: `research/projections.py` **[RECOMMENDATION]**

**Analog:** deny-by-default functions in `backend/app/advanced/projections.py`.

```python
# backend/app/advanced/projections.py:8-22

def job(record: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": str(record["id"]),
        "subject": {"kind": str(record["subject_kind"]), "key": str(record["subject_key"])},
        "status": str(record["status"]),
        "stage": str(record["stage"]),
        "stage_recorded_at": str(record["stage_recorded_at"]),
        "audit_reference": _optional_text(record.get("audit_reference")),
    }


def audit(record: Mapping[str, Any]) -> dict[str, object]:
    return {"reference": str(record["reference"]), "decision": str(record["decision"]), "reason": str(record["reason"])}
```

The existing experiment projection explicitly allowlists status, fingerprints, bounded parameters/environment/resources, metrics, evidence and artifact count while omitting runner diagnostics (`projections.py:126-143`). The candidate/gate projection exposes only safe lineage/config/status/evidence fields (`projections.py:156-174`). Apply the same approach to Alpha runs: expose immutable IDs, status, stage, timestamps, safe terminal reason, committed event sequence, bounded progress counts, snapshot digest (if product-safe), artifact descriptors and links. Redact principal identity, policy internals, raw provider prompt/response, raw market data, worker paths, secrets and exception text.

### 8. API surface: minimal research route **[RECOMMENDATION]**

**Closest analog:** `backend/app/api/research_panels.py` typed read routes plus `backend/app/api/walkforward_sse.py` replay mechanics.

The research panel API obtains the repository from `request.app.state` and fails with 503 when it is not initialized (`research_panels.py:31-40`). It projects rows through typed DTO constructors and bounded `Query` limits (`research_panels.py:56-115, 199-250`). Follow this for `GET /api/research/alpha/runs/{run_id}`, candidates, and event history. POST endpoints should call the run service and return a strict response DTO; they must not mutate a repository directly in the route.

The existing SSE endpoint demonstrates route and replay shape:

```python
# backend/app/api/walkforward_sse.py:145-188
@router.get("/plans/{plan_id}/stream")
async def stream_walk_forward(request: Request, plan_id: str):
    ...
    cursor = 0
    try:
        while True:
            prog = list(job.progress)
            while cursor < len(prog):
                msg = prog[cursor]
                cursor += 1
                if msg.get("type") == "done":
                    yield f"event: done\\ndata: {json.dumps(msg, ensure_ascii=False, default=str)}\\n\\n"
                    return
                yield f"event: progress\\ndata: {json.dumps(msg, ensure_ascii=False, default=str)}\\n\\n"
            ...
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

For Phase 45, use its event naming/replay intuition but do **not** use `_wf_jobs` as durable authority. The walk-forward implementation is explicitly module-level, TTL-bound and replaceable: `_WfJob.progress` is a list, `_wf_jobs` is process memory, and completed reruns clear history (`walkforward_sse.py:26-74, 89-108`). That is unsuitable for an immutable run ledger. Phase 50 may later add durable `Last-Event-ID` SSE; Phase 45 should expose a durable sequence read seam and preserve sequence ordering for that consumer.

### 9. Checkpoint/recovery adapter: generic, not `advanced` authority

**Analog:** `PersistentAdvancedGraph`, `AdvancedWorkflowState`, `AdvancedWorkflowServices` (`backend/app/advanced/workflow.py:18-94`).

```python
class AdvancedWorkflowState(TypedDict):
    """Compact server-derived state persisted by the checkpoint cursor."""
    job_id: str
    authorization_id: str
    subject_ref: str
    frozen_evidence_refs: NotRequired[list[str]]
    ...

class PersistentAdvancedGraph:
    """Open a SQLite saver for each invocation and enforce server thread binding."""
    async def ainvoke(...):
        thread_id = (config or {}).get("configurable", {}).get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            raise ValueError("advanced graph requires a server-generated thread_id")
        ...
        async with AsyncSqliteSaver.from_conn_string(str(self._checkpoint_path)) as saver:
            await saver.setup()
            graph = self._builder.compile(checkpointer=saver)
            return await graph.ainvoke(state, config)
```

Reuse compact server-derived state, per-invocation SQLite saver setup, server-owned run/thread binding and no client-selected authority. Phase 45's checkpoint contract must be independent of LangGraph/Agent state: the cursor references committed run/candidate/event facts and verifies snapshot/manifest/checksum before resume. A checkpoint cannot approve, publish, mutate policy, or be the only audit record. If Phase 45 has no graph yet, a dedicated repository checkpoint row or managed cursor artifact is sufficient; Phase 48 can adapt the same seam to LangGraph.

The workflow's `_safe_draft` is also a useful boundary pattern: it checks evidence references are a subset of frozen server references, bounds rationale/assumptions, validates confidence and returns a narrow allowlist (`workflow.py:97-122`). For Phase 45, apply the same subset/checksum discipline to event payload references and checkpoint references, not provider draft fields.

### 10. Lifecycle/idempotency: adapt `AdvancedRepository`

**Analog:** `AdvancedRepository.acquire_job` and `transition_job_with_audit` (`backend/app/advanced/repository.py:106-136, 347-392`).

```python
# acquire_job: existing idempotency before active-work check and insert
existing = connection.execute(
    "SELECT * FROM advanced_jobs WHERE principal = ? AND idempotency_key = ?",
    (principal, idempotency_key),
).fetchone()
if existing is not None:
    return dict(existing)
...
try:
    connection.execute("""INSERT INTO advanced_jobs (..., idempotency_key, status, ...)
                       VALUES (..., 'queued', ...)""", values)
except sqlite3.IntegrityError:
    row = connection.execute(...).fetchone()
    if row is not None:
        return dict(row)
    raise ValueError("advanced job conflict")
```

```python
# transition_job_with_audit: one transaction for durable audit + guarded cursor
with self._connection() as connection, connection:
    connection.execute("INSERT INTO advanced_security_audit (...) VALUES (...)", ...)
    changed = connection.execute(
        """UPDATE advanced_jobs SET status = ?, stage = ?, ...
           WHERE id = ? AND status = ?""",
        (..., job_id, from_status),
    ).rowcount
    if changed != 1:
        raise ValueError("advanced job state changed; refresh and retry")
```

For Alpha runs, use the same `SELECT-existing → insert → catch race → select` shape, but key the idempotency scope to server principal/request digest and preserve a conflict if the canonical payload differs. For transitions, check allowed edges in service and enforce them again with SQL trigger or guarded `WHERE status = from_status`; insert the corresponding event in the same transaction. Do not import advanced authorization, quota, or strategy mutation tables.

### 11. Artifacts, replay, and event publication risks

The implementation must explicitly cover the following locked risks rather than treating them as logging concerns:

| Risk | Existing pattern to reuse | Required Phase 45 adaptation |
|---|---|---|
| Transaction ordering | `AdvancedRepository.transition_job_with_audit` commits audit + cursor atomically; `AdvancedJobService._advance` publishes afterward (`jobs.py:238-267`) | Insert run/candidate/checkpoint fact and event in one short transaction; notify/publish only after commit. Publisher failure cannot erase durable history. |
| Duplicate start/retry/cancel | `acquire_job` idempotency lookup and race handling; `test_authorization_jobs.py:167-191` | Same idempotency key returns same durable run/state. A changed canonical request or snapshot digest is a conflict/new linked run, never mutation. |
| Lifecycle race | `transition_job` `WHERE id AND status` (`advanced/repository.py:347-360`) | Guard every status transition and reject stale worker requests. Terminal states are one-way; cancellation cannot be overwritten by completion. |
| Event replay | `_WfJob.progress` replay loop (`walkforward_sse.py:168-184`) | Preserve event ordering/cursor behavior, but read rows from SQLite by durable sequence and never clear old history on rerun. |
| Checkpoint stale/missing | Server thread ownership + compact state in `PersistentAdvancedGraph` (`workflow.py:70-94`) | Validate run/snapshot/manifest/event/checksum references before resume; invalid cursor yields a terminal fail-closed reason and no duplicate side effect. |
| Artifact mismatch | `EvaluationArtifactService._write_json` canonical bytes + checksum/fsync; `ResearchRepository._validate_artifacts` path/checksum checks (`repository.py:406-437`) | Verify bytes from managed path, size/type and lowercase SHA-256 before event/checkpoint advancement. Missing/mismatched artifacts are not silently skipped. |
| Complete candidate accounting | Append-only membership/fold facts and `record_wf_fold` uniqueness | Persist every attempt and terminal reason, including invalid, duplicate, low-coverage, failed, rejected, admitted, cancelled and budget-exhausted. |
| Restart safety | `ResearchRepository.create_wf_plan` idempotent pinned plan and `AnalysisRepository.acquire_run` durable active lookup (`analysis/repository.py:59-92`) | A new repository/process instance reconstructs state from SQLite facts; no in-memory queue is authoritative. |

### 12. Test pattern assignments

#### Migration tests

Copy the structure of `test_operational_migrations.py::test_phase10_append_only_tables_migrate_with_constraints_and_idempotence` (`backend/tests/test_operational_migrations.py:339-451`) and `::test_phase13_wf_tables_migrate_with_constraints_and_idempotence` (`:736-861`):

1. Use `sqlite3.connect(":memory:")` with `PRAGMA foreign_keys = ON`.
2. Use migration prefixes to prove Phase 45 objects do not exist before the new version, then apply the full tuple and assert `PRAGMA user_version`.
3. Re-run migration and assert no-op/idempotence.
4. Insert valid parent/child rows; assert bad enum, FK, checksum, uniqueness and boolean/check values raise `sqlite3.IntegrityError`.
5. Assert UPDATE and DELETE on each immutable fact table raise `sqlite3.IntegrityError`.
6. Monkeypatch failing migrations to prove schema and `user_version` roll back together, as the file's atomicity tests do at lines 41-78.

Add focused assertions for `(run_id, seq)`, idempotency key, snapshot digest, checkpoint event sequence/checksum, linked retry parent, and terminal transition constraints.

#### Repository/service tests

`test_authorization_jobs.py::test_quota_rejection_is_audited_without_creating_work_and_idempotency_consumes_once` proves a duplicate request returns the same job, consumes quota once, leaves one runnable row, and does no provider/sandbox work (`:167-191`). Adapt this to duplicate run creation and duplicate lifecycle commands. `test_worker_revalidates_revocation_and_current_policy_before_provider_or_sandbox_work` (`:194-222`) proves revalidation denies work before collaborators; adapt to stale snapshot/checkpoint/artifact and cancellation checks.

`test_advanced/test_workflow.py` provides focused checkpoint tests: exact graph topology and no authority edges (`:85-110`), absent/mismatched server thread rejection without collaborator calls (`:112-128`), prompt/provider output unable to change scope/gates/authority (`:131-164`), and repeated resume recording exactly one outcome (`:167-185`). Phase 45 should test the equivalent with a fake worker and a fresh repository instance, asserting durable event/candidate/checkpoint facts rather than just spy calls.

The analysis lifecycle tests (`backend/tests/test_analysis_lifecycle.py:85-130`) are a useful model for asserting a completed operation requires fresh attributable frozen evidence, is idempotent, and leaves no events on denied/stale requests. Keep tests deterministic with fake clocks/spies and temporary SQLite/artifact roots; do not run broad suites in this research wave.

#### API/projection tests

Use the research panel tests' empty-list/404/strict DTO cases (`backend/tests/api/test_research_panels.py:270-330`) and seeded projection cases (`:338-398, 441-526`) as the route skeleton. Add:

- strict rejection of extra request fields and browser-supplied authority fields;
- 404 for unknown run/candidate/event references and 409 for stale/conflicting idempotency/transition requests;
- 503 when app state lacks the research repository, matching `research_panels._repository`;
- run/event/candidate projections redact principal, policy internals, raw paths, prompts, secrets and diagnostics;
- history remains identical and ordered after constructing a new repository/service instance;
- duplicate retry/cancel does not append a second side-effect event.

The SSE tests (`backend/tests/api/test_walkforward_sse.py:32-161`) show direct endpoint invocation, stream replay, idle keepalive, run-after-connect, terminal `done`, and rerun behavior. Phase 45 should borrow only the observable replay sequencing; unlike `test_walk_forward_rerun_replaces_history`, Alpha retry must preserve prior run facts and create a linked child/resume cursor rather than replace history.

## Shared Patterns

### Shared SQLite boundary

All repository analogs use `Path`-based database configuration, short-lived connections, `sqlite3.Row`, `PRAGMA foreign_keys = ON`, and `with connection:` transaction scopes (`OperationalRepository._connection`, lines 52-71; `ResearchRepository._connection`, lines 74-93; `AdvancedRepository._connection`, lines 45-68). New research run methods should preserve this exactly and call `migrate_operational_db` through repository initialization.

### Canonical JSON and digest validation

Use sorted, compact, UTF-8 JSON (`ResearchRepository._json`, lines 25-29; `CompositeModel` digest, models.py:57-76). Lowercase SHA-256 validation is explicit (`_wf_sha256`, repository.py:58-60; artifact descriptors, artifacts.py:119-125). Digest input must be complete and canonical; do not use `default=str` for identity fields where it can reinterpret dates/objects silently.

### Immutable facts plus narrow guarded cursor

Research membership, experiment, fold, artifact and advanced facts are inserted and trigger-protected. Only a lifecycle cursor may update under a guarded status predicate (`AdvancedRepository.transition_job`, lines 347-360). Phase 45 must keep immutable snapshot/candidate/event facts separate from mutable run status/last-sequence cursor and test both SQL triggers and race behavior.

### Commit before publication

`AdvancedJobService._advance` receives the repository's committed transition, then calls `_publish` with `committed=True` (`jobs.py:238-267`). A Phase 45 event publisher/JobStore bridge must receive only durable projections after the transaction closes. Event consumers must be able to reconstruct history when publisher notifications are dropped.

### Safe public surface

`advanced/projections.py` is hand-built and deny-by-default; `research_panels.py` uses typed response models and bounded limits. New projections must be explicit allowlists. API request DTOs use `extra="forbid"` and bounded Pydantic fields (`advanced/schemas.py:10-13, 113-173`).

## Unsuitable or Adversarial Analogs

| Existing file/pattern | Why it is tempting | Phase 45 decision |
|---|---|---|
| `backend/app/api/walkforward_sse.py:_wf_jobs` | Already has progress replay and reconnect behavior | **Do not use as authority.** It is process memory with 300-second TTL and rerun history replacement (`walkforward_sse.py:47-64, 97-108`). Use SQLite durable event history; Phase 50 may build transport on top. |
| `backend/app/advanced/repository.py` `advanced_*` tables | Has strong idempotency/transition/audit code | **Pattern only.** D-02 prohibits Alpha tables in strategy/authorization domain; copy transaction shape, not names, policies or collaborators. |
| `backend/app/advanced/jobs.py` authorization revalidation | Good untrusted worker and publisher seam | **Adapt without authorization authority.** Phase 45 workers can request a server transition/checkpoint but cannot select policy, mutate snapshot, or grant promotion/execution. |
| `backend/app/advanced/workflow.py` LangGraph saver | Good server thread binding and resumability | **Cursor only.** LangGraph checkpoint state is not the Alpha audit ledger; Phase 45 generic cursor must validate committed research facts. |
| `backend/app/research/models.py:CompositeModel.frame` | Frozen model and snapshot persistence | **Do not persist frames in run metadata.** Use immutable artifact references and bounded summaries. |
| `backend/app/research/artifacts.py:write_bundle` | Strong write-side immutability | **Add read-side verification.** A descriptor alone is not proof that bytes still exist/match; missing/mismatch must fail closed. |
| `backend/app/operational/repository.py` mutable account/position updates | Shows basic parameterized SQL | **Do not apply mutable CRUD to snapshots/candidates/events.** Only the narrow run cursor can update, and only with an allowed transition. |

## No Analog Found / New Composition Required

There is no existing single module that combines immutable run snapshot + complete candidate ledger + monotonic event log + idempotency + checkpoint verification + replay API. The planner should compose the concrete patterns above rather than clone one domain:

| New concern | Why no exact analog exists | Planning implication |
|---|---|---|
| Run-scoped monotonic event sequence with commit-before-publish | Existing SSE history is volatile; existing advanced audit is lifecycle-specific | Design SQL sequence/idempotency constraints and repository transaction boundary first. |
| Checkpoint bound to snapshot/manifest/event checksums | Existing LangGraph saver binds server thread/job, not Alpha run facts | Add explicit verification and fail-closed tests; checkpoint cannot be authority. |
| Full candidate-attempt ledger | Existing advanced candidates are strategy mutations and current research catalog stores retained experiments | Create Alpha-specific append-only research rows; retain invalid/duplicate/failed outcomes. |
| Replay-safe retry | Existing `create_wf_plan` is idempotent same-geometry, while SSE rerun replaces history | Choose resume-vs-linked-child semantics and preserve parent facts; test both duplicate and changed-input cases. |

## Metadata

**Analog search scope:** `backend/app/operational/`, `backend/app/research/`, `backend/app/advanced/`, `backend/app/api/`, `backend/app/analysis/`, and focused `backend/tests/` migration/research/API/advanced/analysis suites.  
**Mandated implementation files inspected:** `migrations.py`, operational `repository.py`, research `repository.py`, `models.py`, `artifacts.py`, advanced `repository.py`, `jobs.py`, `workflow.py`, `schemas.py`, `projections.py`, and `api/walkforward_sse.py`.  
**Supporting files inspected for closest API/service/test analogs:** `api/research_panels.py`, `analysis/repository.py`, `analysis/service.py`, and the focused test files named above.  
**Out of scope:** source edits, broad validation, new dependencies, Alpha generation/evaluation, provider calls, promotion, SSE UI, broker/order/portfolio paths.
