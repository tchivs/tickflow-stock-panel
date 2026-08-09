# Phase 45: Durable Governed Run Contract - Research

**Researched:** 2026-08-08  
**Domain:** Durable, replayable, research-only Alpha Factory run contracts over SQLite/FastAPI/Pydantic  
**Confidence:** HIGH for existing repository seams and safety boundaries; MEDIUM for the proposed Phase 45 schema and service decomposition

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Keep `operational.db` as the authoritative store for small immutable run metadata, lifecycle transitions, candidate-attempt metadata, event envelopes, idempotency keys, and checkpoint cursors. Do not add Redis/Kafka/NATS/Celery/RQ or another database.
- **D-02:** Put the Phase 45 implementation in the `backend/app/research/` domain and reuse `backend/app/operational/migrations.py` plus the existing short-lived SQLite repository/transaction patterns. Do not place Alpha Factory tables in `advanced_*` strategy/authorization tables.
- **D-03:** Large evidence/response/checkpoint payloads are artifact references, not unbounded SQLite blobs: store a content-addressed path/key plus lowercase SHA-256, size/type metadata, and bounded JSON summaries; missing or mismatched artifacts fail closed.
- **D-04:** A run is created from a server-frozen specification containing DSL/grammar/vocabulary/policy versions, seed, candidate/expression budgets, objective/cost policy, universe, measured date range, fold geometry, and code/data manifest. The canonical JSON and digest are persisted before work starts; changing any input creates a new linked run.
- **D-05:** Candidate attempts and lifecycle events are append-only. Each event has a run-scoped monotonic sequence, event type, occurred-at, idempotency key, actor/source, bounded payload or artifact reference, and checksum; durable facts are committed before any in-process publisher is notified.
- **D-06:** Lifecycle transitions are server-owned and fail closed. Support at least `queued`, `preflight_failed`, `running`, `cancel_requested`, `cancelled`, `completed`, and `failed`; duplicate start/retry/cancel requests return the existing durable state rather than creating a second side effect.
- **D-07:** A checkpoint is a recovery cursor over committed run/candidate/event facts, bound to the run snapshot digest and input manifest. A cursor is written only after its referenced side effects commit; a stale, missing, or checksum-inconsistent cursor cannot advance work.
- **D-08:** Replay reads only the frozen manifest and durable event/candidate/checkpoint facts. It must be deterministic and read-only in Phase 45; it must not silently fetch current constituents, rewrite historical facts, or consume reserved OOS.
- **D-09:** Expose a minimal server API/service seam for create, get/replay, retry, cancel, and event-history reads so later Factory/Agent/UI phases consume one contract. Phase 45 need not provide a browser workbench or live SSE transport; Phase 50 owns the user-facing projection and reconnect transport.
- **D-10:** Any background execution adapter is an untrusted worker around the research run service. It may request a transition/checkpoint but cannot choose policy, mutate frozen inputs, bypass idempotency, or grant execution/promotion authority.

### Claude's Discretion

- Exact table/column names, index names, enum representation, and repository class decomposition, provided the observable fields and constraints above are explicit and covered by tests.
- Whether a checkpoint is represented as a dedicated table or a typed append-only event plus current projection, provided restart recovery and uniqueness constraints are transactionally proven.
- Exact API route naming and response envelope, provided it follows existing FastAPI route and projection conventions and keeps raw internal diagnostics private.

### Deferred Ideas (OUT OF SCOPE)

- Restricted vocabulary enumeration, mutation/crossover, lineage scoring, diversity, and budget scheduling — Phase 46.
- Shared-chain evaluation, admission evidence, cost/robustness, and reserved selection OOS — Phase 47.
- Provider preflight, Stage 1/2 schemas, retries, and Agent checkpoints — Phase 48.
- Promotion Ticket, reviewer refresh, and FactorRevision/catalog handoff — Phase 49.
- SSE/poll reconnect UI, comparison/lineage/stress views, degradation labels, and release scans — Phase 50.
- Neural/RL search, external queues, automatic promotion, broker/live execution, arbitrary Python, and second evaluator — deferred beyond v3.0.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AF-REQ-01 | A researcher can create an immutable factory run specification containing DSL/grammar/vocabulary versions, seed, expression limits, candidate budget, objective policy, universe, measured date range, fold geometry, costs, and code/data manifest; changing inputs creates a new run instead of mutating the original. | The manifest/snapshot contract, canonical JSON digest, immutable run rows, request idempotency, and linked-child retry design below. |
| AF-REQ-04 | The run retains every attempted candidate, including invalid, duplicate, low-coverage, failed, rejected, and admitted outcomes, with parent/mutation lineage, seed/step, status, reason, and evidence references; the system never retains only the champion. | Append-only candidate-attempt and lineage tables, bounded diagnostics, artifact references, and transactionally paired event writes. |
| AF-REQ-10 | A run can be replayed from stored data/partition, universe, factor/DSL, grammar/vocabulary, seed, configuration, code/build, provider/model, candidate-order, and artifact checksums; missing required manifest fields fail closed. | Snapshot completeness checks, per-component digests, read-only replay, artifact verification, and stale-cursor fail-closed rules. |
| AF-REQ-16 | The workbench exposes queued/running/completed/failed/cancelled states, candidate/fold progress, cooperative cancellation, idempotent retry, and checkpointed resume; retry resumes or creates a linked run and never overwrites an earlier run or repeats a committed OOS/promotion side effect. | Server-owned lifecycle matrix, durable sequence/idempotency, cancellation boundary, linked retry semantics, and checkpoint recovery contract. |
</phase_requirements>

## Summary

Phase 45 should add one research-domain durability boundary, not another job platform. Extend the existing `ResearchRepository`/migration path with server-owned run snapshots, append-only candidate attempts, append-only events, immutable artifact references, and bounded checkpoint cursors in `operational.db`. A small service should be the only writer of lifecycle transitions and should commit the domain fact and event in one SQLite transaction before invoking any optional worker publisher. `[VERIFIED: backend/app/research/repository.py:25-29]` The current JSON helper uses `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`; `[VERIFIED: backend/app/research/repository.py:58-63]` the repository validates lowercase 64-character SHA-256 strings. These are the correct foundations for canonical manifests and checksums.

The current migration runner already wraps each migration in `BEGIN`/`COMMIT`, rolls back on any exception, restores foreign keys, and advances `PRAGMA user_version` inside the same transaction. `[VERIFIED: backend/app/operational/migrations.py:1890-1918]` Existing immutable research and walk-forward tables use foreign keys, uniqueness constraints, `CHECK` constraints, and no-update/no-delete triggers. `[VERIFIED: backend/app/operational/migrations.py:1705-1811]` Existing advanced jobs show guarded status updates and an atomic transition-plus-audit write, while the current walk-forward SSE store is explicitly module-level and five-minute TTL. `[VERIFIED: backend/app/advanced/repository.py:347-392]` `[VERIFIED: backend/app/api/walkforward_sse.py:47-64]` Reuse the transaction and projection ideas, but do not reuse advanced authorization authority or volatile SSE state.

**Primary recommendation:** implement a single `AlphaRunService` over a `ResearchRepository` extension, with an additive migration for immutable snapshot/run/candidate/event/checkpoint/artifact facts, guarded run status cursor, deterministic sequence allocation under `BEGIN IMMEDIATE`, and a read-only replay API; keep `JobStore`/worker state as an untrusted adapter and keep Phase 45 free of generation, evaluation, provider calls, OOS, promotion, SSE, and execution.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Freeze run specification and input manifest | API / Backend | Database / Storage | The server resolves and freezes policy, data, code, and identity before work; the browser supplies intent only. The immutable canonical JSON/digest belongs in SQLite. |
| Run/candidate/event/checkpoint persistence | Database / Storage | API / Backend | `operational.db` is the locked authority for small immutable facts; repository transactions enforce uniqueness, foreign keys, and guarded transitions. |
| Replay and recovery cursor validation | API / Backend | Database / Storage | Replay reads only stored facts and verifies digest/artifact bindings; a worker may request resume but cannot make policy or authority decisions. |
| Candidate-attempt lineage and diagnostics | Database / Storage | API / Backend | Every attempt, including invalid/duplicate/failed/rejected outcomes, is durable; the service validates bounded fields and the repository persists references. |
| Progress projection | API / Backend | Browser / Client | Phase 45 exposes bounded history reads only; Phase 50 may add SSE/polling projection. In-memory notification is never scientific authority. |
| Artifact bytes and checkpoint payloads | CDN / Static | Database / Storage | Large payloads remain in the managed data root; SQLite stores safe relative reference, type, byte count, digest, and bounded summary. |
| Research-only authority boundary | API / Backend | Browser / Client | No route, worker, candidate, or model output may call broker/order/position/portfolio/live-monitor collaborators. |

## Project Constraints (from CLAUDE.md)

No `./CLAUDE.md` or `./.claude/CLAUDE.md` exists in the working tree; therefore no additional repository-specific directives were discoverable in this session. The locked context remains authoritative: research-only, no source edits in this research wave, Python 3.11+/FastAPI/Pydantic/SQLite/Parquet/Polars/DuckDB/LangGraph/SSE, new work under `backend/app/research/`, and no external queue or new base dependency.

## Standard Stack

### Core

| Library / seam | Version or constraint | Purpose | Why standard |
|---|---|---|---|
| Python + `sqlite3` | `>=3.11`; project declares `requires-python = ">=3.11"` `[VERIFIED: backend/pyproject.toml:1-7]` | Repository transactions, SHA-256, canonical JSON, bounded domain services | Already the runtime and database authority; no new persistence service. |
| FastAPI + Pydantic v2 | `fastapi>=0.115`, `pydantic>=2.7` `[VERIFIED: backend/pyproject.toml:8-15]` | Strict create/retry/cancel request and safe response DTOs | Existing route patterns use `ConfigDict(extra="forbid")`. `[VERIFIED: backend/app/api/research.py:14-39]` |
| `ResearchRepository` + `migrate_operational_db` | Existing source seams | SQLite access, migrations, canonical JSON, immutable research facts | All repositories initialize against the shared operational migration sequence. `[VERIFIED: backend/app/research/repository.py:74-93]` |
| Managed research artifact store | Existing `EvaluationArtifactService` | Content-addressed evidence/checkpoint bytes outside SQLite | Its root is application-owned `research_artifacts`. `[VERIFIED: backend/app/research/artifacts.py:36-40]` |

### Supporting

| Library / seam | Version or constraint | Purpose | When to use |
|---|---|---|---|
| `hashlib.sha256` | Python standard library | Manifest, payload, artifact, and checkpoint checksums | Use for integrity identity only, not secrecy or authorization. |
| `JobStore` | Existing `backend/app/services/pipeline_jobs.py` | Optional worker single-flight/progress/stale recovery adapter | Use only as replaceable execution bookkeeping; never as the run/event ledger. `[VERIFIED: backend/app/services/pipeline_jobs.py:44-52]` |
| LangGraph SQLite saver | Existing locked pair (`langgraph==1.2.9`, `langgraph-checkpoint-sqlite==3.1.0`) `[CITED: .planning/research/STACK.md:44-46]` | Future Agent graph recovery state only | Not needed for Phase 45 API/replay; if later attached, bind server-generated thread/run identity and keep domain events separate. |
| Parquet/Polars/DuckDB | Existing project stack | Future data/artifact reads | Phase 45 records references and manifests only; it must not evaluate factors or fetch a fresh panel. |

**Installation:** No installation. The phase adds no package and changes no dependency declaration. `[VERIFIED: .planning/research/STACK.md:90-102]`

**Alternatives rejected:** Redis/Kafka/NATS/Celery/RQ and another database violate D-01; a second evaluator or StackVM violates the one-signal-path boundary; raw pickle or opaque local state cannot provide safe replay; WebSockets/SSE transport belongs to Phase 50. `[VERIFIED: .planning/phases/45-durable-governed-run-contract/45-CONTEXT.md:19-36]`

## Architecture Patterns

### System Architecture Diagram

```text
bounded API intent
      |
      v
AlphaRunService -- resolve server-owned policy/data/code refs --> canonical snapshot + manifest digest
      |                                                               |
      | one BEGIN IMMEDIATE transaction                                  | no work until committed
      v                                                               v
run row (guarded status cursor) <--> snapshot row <--> artifact refs/checksums
      |
      +--> candidate attempt + lineage rows + event(seq,idempotency) -- commit --> optional wake publisher
      |
      +--> checkpoint(cursor, committed event/candidate refs, snapshot digest, checksum)
      |
      +--> read-only replay: manifest + events + candidates + checkpoint + verified artifacts
      |
      +--> worker adapter / JobStore (replaceable, untrusted; requests only)

API GET history/replay reads durable rows; Phase 50 may project the same sequence through SSE/polling.
No provider, factor evaluator, OOS evaluator, promotion service, broker, order, position, or live monitor is in this phase.
```

### Recommended Project Structure

```text
backend/app/research/
├── repository.py          # extend ResearchRepository with run/snapshot/candidate/event/checkpoint methods
├── run_contract.py        # bounded immutable DTOs, canonicalization, digest and artifact-reference validation [ASSUMED]
├── run_service.py         # create/replay/retry/cancel/transition/checkpoint orchestration [ASSUMED]
└── run_api.py             # minimal typed routes mounted by the existing FastAPI host [ASSUMED]
backend/app/operational/migrations.py  # one additive Phase 45 migration [VERIFIED: backend/app/operational/migrations.py:7-8]
backend/tests/research/test_run_contract.py  # repository/service contract tests [ASSUMED]
backend/tests/api/test_run_api.py            # route/projection/idempotency tests [ASSUMED]
```

The exact module split is discretionary; the non-negotiable integration point is a single repository/service contract under `backend/app/research/`. Do not create Alpha tables in `backend/app/advanced/`.

### Pattern 1: Atomic schema migration

**What:** Append one versioned SQL migration containing all Phase 45 tables, indexes, foreign keys, checks, and immutable/guarded triggers. Keep the migration self-contained so partial schema objects and `user_version` cannot survive a failure. `[VERIFIED: backend/tests/test_operational_migrations.py:41-74]` Existing tests assert that a mid-script failure leaves no probe objects and `PRAGMA user_version` at zero, then a corrected migration applies cleanly.

**How to implement:** Use the existing `MIGRATIONS` tuple and migration runner; do not execute schema changes from a request handler. Add a migration test that injects a failing statement after each new table family, verifies rollback, then reapplies successfully. Preserve `PRAGMA foreign_keys = ON` after success/failure. `[VERIFIED: backend/app/operational/migrations.py:1890-1918]`

### Pattern 2: Canonical frozen manifest

**What:** Normalize only server-resolved fields into one canonical object. Serialize with the existing sorted-key/no-whitespace JSON convention, hash UTF-8 bytes with lowercase SHA-256, and persist both JSON and digest. The run and snapshot are immutable; any changed field gets a new linked run. `[VERIFIED: backend/app/research/repository.py:25-29]`

**Required manifest groups:** DSL version; grammar and ordered vocabulary fingerprints; policy version and canonical policy snapshot; seed; expression/node/window and candidate budgets; objective and cost/slippage policy; universe and asset type; measured start/end/calendar and fold geometry; data/partition/panel/membership fingerprints and quality state; code/build/dependency fingerprints; provider/model metadata when applicable; candidate-order rule; artifact descriptors; manifest schema version. Every required group must be non-empty and every digest must be lowercase 64-hex before `queued` is returned.

**Important boundary:** A client may request a bounded universe/date/budget/seed, but the server resolves actual membership, data snapshot, policy, code version, and vocabulary. Never hash an untrusted client JSON blob as the authoritative manifest.

### Pattern 3: Append-only facts plus guarded lifecycle cursor

**What:** Keep immutable identity and outcome rows INSERT-only; permit only a narrow status/progress cursor update on the run row using `WHERE id = ? AND status = ? AND transition_version = ?`. Pair that update with an event insert and incremented sequence in one transaction. This mirrors the existing guarded advanced transition. `[VERIFIED: backend/app/advanced/repository.py:347-392]`

**Recommended event envelope fields:** run ID, sequence, event ID, event type/stage, entity kind/entity ID, occurred-at, idempotency key, actor/source, bounded payload JSON or artifact reference, payload checksum, producer/schema version. Use unique `(run_id, sequence)` and `(run_id, idempotency_key)`; a reused key with a different event checksum is a conflict, not a second event. Events are committed before any publisher callback.

**Candidate accounting:** Use one row per attempt, not one row per unique expression. A duplicate canonical expression is a durable `duplicate` attempt with its own ordinal/seed/parent metadata and event; it must not be silently ignored. Store parent edges in a separate append-only lineage table with foreign keys so every child-to-parent link is queryable and cannot point outside the run.

### Pattern 4: Transactionally safe sequence allocation

**Recommendation [ASSUMED]:** Allocate a run sequence under `BEGIN IMMEDIATE`, using the run cursor's current `last_event_seq + 1` rather than `MAX(sequence)` from an unlocked read. In the same transaction insert the event and update the run cursor. A uniqueness violation or stale expected version rolls back both. `BEGIN IMMEDIATE` is consistent with the existing forecast repository's explicit transaction pattern. `[VERIFIED: backend/app/forecast/repository.py:230-240]`

Do not use an in-process counter, timestamp ordering, SQLite `rowid` as the public sequence, or a publisher callback to allocate sequence. A client-supplied sequence is rejected. If a duplicate idempotency key already exists, return its original event/result; if its semantic payload differs, fail closed with conflict.

### Pattern 5: Checkpoint as a bounded recovery cursor

**What:** Prefer a dedicated append-only checkpoint table because Phase 45 needs explicit cursor validation independent of future Agent graph state. Each checkpoint records run ID, checkpoint schema/version, committed event sequence, stage, candidate queue/frontier artifact references, deterministic order/cursor data, committed candidate IDs/evaluation references (bounded list or artifact), snapshot/manifest digest, state checksum, and created-at. Store a content-addressed artifact for large frontier/queue payloads; never store a pickle, market frame, provider prompt, or arbitrary executable state.

A checkpoint can be written only in a transaction that has already inserted the referenced candidate/event facts. On recovery, require: run identity matches; snapshot and manifest digests match; event sequence exists and is contiguous through the checkpoint; referenced candidate IDs belong to the run; artifact exists, size matches, and SHA-256 matches; checkpoint checksum recomputes; status is resumable. Missing, stale, future, non-contiguous, or mismatched cursors fail closed and transition to `failed` with a durable reason rather than rerunning work.

### Pattern 6: Artifact references and safe paths

**What:** Validate artifact descriptors before persistence and verify bytes before replay. Existing research experiments require artifact paths to be relative, POSIX, rooted under `research_artifacts/<originating_run_id>/`, free of `.`/`..`/backslash traversal, unique per experiment, with non-negative integer size and lowercase SHA-256. `[VERIFIED: backend/app/research/repository.py:406-435]` Existing artifact storage roots under the application-owned data directory. `[VERIFIED: backend/app/research/artifacts.py:36-40]`

**Recommendation [ASSUMED]:** Apply the same path rules to Alpha run/checkpoint artifacts, but use a distinct namespace such as `research_artifacts/alpha_runs/<run_id>/...`; never accept an absolute path or arbitrary client path. Write a new object atomically (temporary file, flush/fsync, exclusive create/rename), then verify size/hash and insert the descriptor. Do not overwrite an existing digest/path. A failed DB transaction may leave an unreferenced file; retain a bounded orphan-cleanup procedure, but never delete a referenced artifact during request handling.

### Pattern 7: Safe projections and minimal API

Follow existing research API conventions: strict Pydantic models with `extra="forbid"`, bounded strings/lists, explicit `400` validation and `409` state conflicts, and server state resolved through `request.app.state`. `[VERIFIED: backend/app/api/research.py:14-20,79-91]` Keep raw prompts, internal paths, secrets, unbounded diagnostics, and arbitrary provider responses out of public projections.

Suggested seam (route names remain discretionary):

| Operation | Suggested route | Durable behavior |
|---|---|---|
| Create | `POST /api/research/alpha/runs` | Resolve/freeze, insert snapshot+run+`queued` event atomically; same principal/idempotency key returns existing identical run. |
| Inspect/replay | `GET /api/research/alpha/runs/{run_id}` and `GET .../{run_id}/replay` | Return allowlisted run/snapshot summary and bounded candidate/event/checkpoint pages; no writes or current-data fetch. |
| Retry/resume | `POST /api/research/alpha/runs/{run_id}/retry` | If resumable, return existing cursor/run; otherwise create linked immutable child run with copied manifest digest and new attempt identity. Never overwrite the parent. |
| Cancel | `POST /api/research/alpha/runs/{run_id}/cancel` | Idempotently append `cancel_requested`; worker observes it at a boundary and records `cancelled`. Terminal runs return current state. |
| Event history | `GET /api/research/alpha/runs/{run_id}/events?after_sequence=...` | Bounded ordered rows from SQLite. Phase 50 may layer `Last-Event-ID` SSE over the same query. |

The client may provide an idempotency key and bounded intent only. Candidate IDs, event sequence, evidence references, status, policy, manifest, and cancellation authority are server-owned.

## Proposed Durable Schema Contract

The exact names below are recommendations, not current tables (`[ASSUMED]`), but each constraint is required by D-01 through D-07.

| Table | Key fields and constraints | Mutability |
|---|---|---|
| `research_alpha_input_snapshots` | `id`, `schema_version`, canonical `snapshot_json`, `snapshot_sha256`, `manifest_json`, `manifest_sha256`, all required component digests, created-at; unique digest; lowercase SHA-256 checks | INSERT-only; no update/delete triggers |
| `research_alpha_runs` | `id`, principal, request idempotency key, snapshot ID/FK, status, transition version, last event sequence, retry parent/attempt, started/finished timestamps, terminal reason, created-at; unique `(principal,idempotency_key)` and active-run identity as required | Immutable identity; only guarded lifecycle/recovery cursor columns update |
| `research_alpha_candidate_attempts` | `id`, run FK, attempt ordinal, candidate digest/canonical expression, AST/shape signature, DSL/grammar/vocabulary versions, operation, seed/step, status, bounded reason/diagnostics JSON, evidence/artifact reference, created-at; unique `(run_id,attempt_ordinal)` | INSERT-only |
| `research_alpha_candidate_lineage` | child attempt FK, parent attempt FK, edge ordinal, operation metadata, created-at; same-run validation | INSERT-only |
| `research_alpha_events` | event ID, run FK, sequence, stage/entity IDs, event type, occurred-at, idempotency key, actor/source, bounded payload JSON, payload checksum, artifact reference, producer version; unique `(run_id,sequence)` and `(run_id,idempotency_key)` | INSERT-only |
| `research_alpha_checkpoints` | checkpoint ID, run FK, checkpoint version, committed event sequence, stage, candidate/frontier refs, snapshot/manifest digests, state checksum, payload artifact ref, created-at; unique run+cursor identity | INSERT-only |
| `research_alpha_artifacts` | artifact ID, run FK, logical kind, safe relative path/key, content type, byte size, lowercase SHA-256, schema version, created-at; unique `(run_id,checksum_sha256,logical_kind)` | INSERT-only |

Use `ON DELETE RESTRICT` for all cross-fact references. Add indexes for run status/created-at, event `(run_id,sequence)`, candidate `(run_id,attempt_ordinal)`, lineage child/parent, and checkpoint `(run_id,committed_event_sequence DESC)`. Add no-update/no-delete triggers to immutable tables. The run cursor trigger must reject changes to IDs, principal, idempotency key, snapshot ID, retry parent/attempt, creation time, manifest digest, and any other identity field; it must require exactly one transition-version increment and only legal statuses.

### Lifecycle transition matrix

Use `preflight_failed` for invalid/preflight terminal outcomes rather than inventing a second mutable invalid cursor; preserve the exact invalid reason in `terminal_reason` and a bounded event payload. `[ASSUMED]`

| From | Allowed next state | Trigger/meaning | Duplicate or stale request |
|---|---|---|---|
| `queued` | `running`, `preflight_failed`, `cancel_requested`, `failed` | Start after committed snapshot; preflight failure before any generation/provider call; cancellation may arrive before worker start. | Same idempotency key returns current state; stale expected version is `409`/retry-read. |
| `running` | `cancel_requested`, `completed`, `failed` | Worker owns no policy; service records progress/outcome. | Duplicate start returns current `running`; late completion after cancel request is rejected unless service atomically proves cancellation was not accepted. |
| `cancel_requested` | `cancelled`, `failed` | Cooperative boundary observes cancellation; inability to verify cursor/artifact becomes failed closed. | Repeated cancel returns `cancel_requested` or terminal state; no new event for same cancel key. |
| `preflight_failed` | terminal only | Invalid/incomplete snapshot or preflight prerequisite; no generation/provider call. | Retry creates a linked child run; parent facts remain unchanged. |
| `cancelled` | terminal only | Cancellation is durable and not equivalent to successful completion. | Retry creates/resumes only through a new idempotent request; never mutates cancelled row. |
| `completed` | terminal only | All Phase 45-owned work/cursor facts committed. | Retry is a new linked run or returns existing retry child; no duplicate side effect. |
| `failed` | terminal only | Provider/worker/artifact/cursor failure, retained with reason. | Retry is a new linked run or safe cursor resume only when the checkpoint validates; never rewrite failure. |

`preflight_failed`, `cancelled`, `completed`, and `failed` must not transition back to `running`. A worker callback that attempts an illegal or stale transition must produce no candidate/event side effect and must fail closed. The `cancel_requested` event is not itself proof that work stopped; terminal `cancelled` is recorded only at a worker boundary.

## Transaction, Idempotency, and Event Semantics

1. **Create:** Validate intent; resolve all server-owned snapshot fields; canonicalize and hash; under one transaction insert snapshot, run, and `run_created` event with sequence 1. The response is not `queued` until commit succeeds. If the principal/idempotency key exists with the same request/manifest digest, return the original run; if the key is reused with a different digest, return conflict.
2. **Transition:** Under `BEGIN IMMEDIATE`, read current status/version; verify the matrix; allocate `last_event_seq + 1`; insert event; guarded-update status/version/timestamps; commit; only then notify a process-local publisher. The publisher is best effort and cannot make a committed fact disappear.
3. **Candidate attempt:** Validate bounded canonical fields, lineage, status, and artifact references; insert candidate plus lineage edges and its event in one transaction. Do not use `INSERT OR IGNORE` for attempts because duplicate/invalid outcomes are required evidence. Idempotency applies to a request/event key, not to suppressing a distinct duplicate candidate attempt.
4. **Checkpoint:** Verify all referenced rows are committed and the payload/artifact digest is valid; write checkpoint and checkpoint event in one short transaction after the candidate/event transaction that produced the referenced cursor. On crash, the absence of the checkpoint means replay from the preceding committed sequence; never assume an in-memory frontier survived.
5. **Artifact:** Materialize and verify artifact bytes before inserting a reference. A DB row without a verified artifact is not a valid checkpoint/evidence binding. A missing or mismatched artifact makes replay fail closed and records a bounded terminal reason if the run is being resumed.
6. **Retry:** Same retry idempotency key returns the existing child or cursor. A new retry request either resumes a valid non-terminal cursor (without redoing committed attempts) or inserts a new child run linked by `retry_of_run_id`, preserving the parent manifest and adding a new attempt/request identity. Never copy mutable status or overwrite parent facts.
7. **OOS/promotion:** Phase 45 does not evaluate OOS or promote. Its contract must nevertheless prohibit event types or service dependencies that could perform those side effects. Later phases bind those effects to their own exactly-once facts and call them only after deterministic selection.

## Replay, Restart, Cancel, and Failure Semantics

- **Replay:** Read the stored manifest/snapshot, then events and candidate attempts in sequence/ordinal order, verify contiguous sequences, recompute payload/checkpoint checksums, and verify every referenced artifact. Replay is read-only and never resolves current membership, latest code, current provider output, or current policy.
- **Process restart:** A new process reads SQLite, treats any `running` row without a valid lease/checkpoint as recoverable only through the service's explicit retry/recovery path, and never trusts a vanished `JobStore` JSON file. `[VERIFIED: backend/app/services/pipeline_jobs.py:53-75]` The current `JobStore` stores terminal JSON files but keeps active jobs in memory. `[VERIFIED: backend/app/services/pipeline_jobs.py:44-52,219-225]` Therefore it cannot be the authority.
- **Stale cursor:** Reject a cursor whose snapshot/manifest digest differs, whose sequence is ahead of the event ledger, whose event range has a gap, whose candidate/artifact reference is absent, or whose checksum is wrong. Record a `failed` reason only through the service's guarded transition; do not auto-repair by changing historical rows.
- **Cancel:** API cancellation is idempotent and cooperative. It records `cancel_requested`; the worker checks before each future stage/candidate boundary and records `cancelled` after no further work is committed. A late callback must not append a success after terminal cancellation. Cancellation is not reported as `completed` or 100% success.
- **Crash window:** If a process dies before the domain transaction commits, no event/candidate/checkpoint exists and the unit may be retried. If it dies after commit but before publish, replay sees the fact and the publisher can catch up. If it dies after an artifact write but before DB commit, the artifact is unreferenced and may be collected later; it must not be treated as evidence.
- **Bounded diagnostics:** Keep safe reason codes and short summaries in SQLite; store larger provider/worker/checkpoint payloads as verified artifact descriptors. Do not expose raw paths, prompts, secrets, or untrusted executable state.

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| Atomic schema evolution | Request-time `CREATE TABLE`, ad-hoc startup SQL, or a second schema version | `MIGRATIONS` + `migrate_operational_db` | Existing runner provides per-migration atomicity and version rollback. |
| Canonical JSON/digest | String concatenation, unordered dict serialization, display-name identity | Existing sorted-key `_json`, `hashlib.sha256`, explicit digest validation | Stable bytes are required for replay and idempotency. |
| Safe artifact storage | Arbitrary client paths, SQLite blobs, overwriting files, trusting path names | Managed artifact service plus relative-path/size/hash validation | Prevents traversal, tampering, unbounded DB growth, and stale evidence. |
| Lifecycle transitions | In-memory enum/state machine without DB guards | SQL `CHECK`/triggers plus guarded repository transition | Survives competing workers and process restart. |
| Event delivery | Queue as source of truth, timestamp ordering, in-memory history | SQLite append-only sequence; optional hub only as wake-up | Durable replay must survive restart and dropped subscribers. |
| Recovery state | Pickle/full data frame/provider state in a checkpoint | Bounded cursor plus verified artifact reference and committed fact IDs | Avoids code execution, portability, and stale-state hazards. |
| Factor semantics | Direct Polars evaluator, StackVM, Python `eval`, generated source | Later `factor_dsl`/`FactorSignalChain` path; not Phase 45 | A second evaluator creates train/serve skew and authority escalation. |
| Job execution | Redis/Kafka/Celery/RQ or a new queue | Existing worker/`JobStore` adapter, with SQLite run facts authoritative | Locked single-host scope does not need an external queue. |

## Explicit Rejections and Authority Boundary

- **External queues/databases:** Reject Redis, Kafka, NATS, Celery, RQ, and a second database. The phase is explicitly constrained to the existing `operational.db` and short-lived SQLite repositories. `[VERIFIED: .planning/phases/45-durable-governed-run-contract/45-CONTEXT.md:19-24]`
- **Second evaluator:** Reject any new factor interpreter, StackVM, direct-Polars candidate evaluator, or search-specific scorer. Phase 45 stores contracts only; later scoring must use the existing governed chain. `[VERIFIED: .planning/research/STACK.md:8-16]`
- **Arbitrary code:** Reject Python source, `eval`, imports, pickle checkpoints, model-selected tools/paths, or executable payloads. Candidate rows contain canonical expression/signature metadata and references only.
- **Execution authority:** Reject broker/order/position/portfolio/monitor collaborators, live activation, automatic promotion, and execution routes. The locked project boundary says v3.0 remains research-only and has “零自动实盘执行权”. `[VERIFIED: .planning/PROJECT.md:11-20]`
- **Advanced-domain reuse:** Reject putting Alpha rows into `advanced_*` strategy/authorization tables. Advanced repository/job/workflow are pattern references only; their authorization and strategy mutation contracts are not Alpha authority.
- **Volatile walk-forward store:** Reject `_wf_jobs` as the event ledger. It resets history on rerun and removes completed jobs after a five-minute TTL. `[VERIFIED: backend/app/api/walkforward_sse.py:47-64,97-106]`

## Runtime State Inventory

This phase is an additive SQLite schema migration, so runtime state was inspected explicitly.

| Category | Items found | Action required |
|---|---|---|
| Stored data | `data/operational.db` exists and contains existing factor, walk-forward, forecast, and research experiment rows; no Phase 45 Alpha run/candidate/event/checkpoint tables are present in the inspected schema. `[VERIFIED: data/operational.db]` | Add only the forward migration. No historical Alpha data migration is required. Do not rewrite existing `wf_*`, `advanced_*`, or research rows. |
| Live service config | No repository-visible external service configuration for Alpha runs was found; live deployment UI/database configuration is not observable from this checkout. | No code migration. Before release, confirm there is no external scheduler/worker configured to treat a Phase 45 run ID as execution authority. |
| OS-registered state | No Phase 45 service/task registration exists in the repository. | None for this phase; any future worker registration must use server-owned run IDs and must not be treated as durable domain state. |
| Secrets/env vars | No Alpha-specific secret or environment-key rename is in scope. Existing data directory wiring resolves `operational.db` from the server-owned data directory. `[VERIFIED: backend/app/main.py:130-135]` | No secret migration. Do not persist secrets in manifest/event payloads. |
| Build artifacts / installed packages | No new package is required. Existing analysis checkpoint files are separate from the Alpha domain ledger. `[VERIFIED: backend/app/main.py:145-150]` | No package reinstall. If checkpoint files are introduced later, namespace them and verify their manifest/checksum binding; do not use them as event history. |

## Common Pitfalls

### Pitfall 1: Snapshot created after work begins

**What goes wrong:** A worker reads current data/policy or a changed vocabulary halfway through a run.  
**Why:** The request handler schedules work before the canonical snapshot transaction commits.  
**How to avoid:** Create and digest the complete snapshot, insert `queued` run and first event, commit, then permit a worker request. Missing fields fail closed.  
**Warning signs:** Run row lacks one of the required manifest groups; worker input differs from stored digest; replay consults current “latest” data.

### Pitfall 2: `MAX(sequence)+1` race or publisher-first event

**What goes wrong:** Two workers allocate the same sequence, or a client sees an event that rolled back.  
**Why:** Sequence allocation occurs outside a write lock or publication precedes commit.  
**How to avoid:** `BEGIN IMMEDIATE`, run cursor increment, event insert, and fact transition in one transaction; publish only after commit.  
**Warning signs:** gaps/duplicates for committed sequence, an event with no DB row, or a terminal event without a matching status cursor.

### Pitfall 3: Idempotency suppresses legitimate duplicate evidence

**What goes wrong:** A duplicate expression disappears from the denominator, violating complete candidate accounting.  
**Why:** Uniqueness is incorrectly imposed on canonical expression instead of request/event identity.  
**How to avoid:** Retain each candidate attempt with a distinct ordinal and `duplicate` status; use idempotency only for repeated delivery of the same request.  
**Warning signs:** candidate count equals unique-expression count despite duplicate attempts, or retry changes an existing attempt row.

### Pitfall 4: Mutable run row becomes an audit log

**What goes wrong:** A retry/cancel overwrites what happened before restart.  
**Why:** Status, terminal reason, and progress are updated without append-only events or version guards.  
**How to avoid:** Keep immutable run identity and append events/attempts; allow only a narrow guarded cursor update, with transition version and legal matrix.  
**Warning signs:** `UPDATE` changes snapshot/digest/parent fields; terminal states can return to `running`.

### Pitfall 5: Checkpoint claims uncommitted work

**What goes wrong:** Resume skips a candidate or repeats a committed side effect.  
**Why:** A cursor is persisted before its event/candidate/artifact or after a partial file write.  
**How to avoid:** Verify referenced facts and artifacts, then commit checkpoint metadata atomically; on any mismatch fail closed.  
**Warning signs:** checkpoint sequence is ahead of event history, referenced IDs are missing, or a checksum differs after restart.

### Pitfall 6: Artifact path/hash is metadata-only

**What goes wrong:** Replay reads an overwritten, missing, or wrong file under a valid-looking path.  
**Why:** The repository stores a path without checking file bytes, size, or traversal.  
**How to avoid:** Managed relative paths, exclusive immutable writes, size/hash verification before reference insertion, and verification on every replay.  
**Warning signs:** path escapes the run namespace, file size differs, uppercase/non-hex digest, or an artifact row has no readable bytes.

### Pitfall 7: Restart and cancel create a second worker

**What goes wrong:** A stale worker continues after cancellation/restart and appends success or duplicate candidates.  
**Why:** `JobStore` active state is in memory and a late callback lacks a durable expected version/lease.  
**How to avoid:** Worker callbacks supply run ID plus expected cursor/version and idempotency key; service rejects stale/terminal transitions. `JobStore` disappearance never erases domain facts.  
**Warning signs:** two active workers for one run, events after terminal cancellation, or progress from a run whose manifest differs.

### Pitfall 8: Phase leakage into provider/OOS/promotion

**What goes wrong:** A “run contract” endpoint starts evaluation, calls a provider, reads reserved OOS, or registers a factor.  
**Why:** The contract service imports future collaborators or accepts client-supplied authority flags.  
**How to avoid:** Phase 45 creates/replays facts only; keep generation/evaluation/provider/promotion imports out; static import guard and runtime collaborator mocks prove no execution path.  
**Warning signs:** API request contains gate status/evidence/revision IDs that server accepts, or Phase 45 tests need broker/provider fixtures.

## Code Examples

### Existing canonical JSON convention

The repository already provides the intended deterministic serialization primitive:

```python
json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

`[VERIFIED: backend/app/research/repository.py:25-29]` Use the same convention for the snapshot JSON, manifest digest input, event payload checksum input, and checkpoint state checksum. Do not hash a pretty-printed or client-preserved representation.

### Existing atomic migration convention

```python
transactional_sql = f"BEGIN;\n{transactional_sql}\nPRAGMA user_version = {version};\nCOMMIT;"
try:
    connection.executescript(transactional_sql)
except BaseException:
    if connection.in_transaction:
        connection.execute("ROLLBACK")
    raise
```

`[VERIFIED: backend/app/operational/migrations.py:1905-1918]` Phase 45 should append SQL to `MIGRATIONS`; it should not duplicate this runner inside the Alpha repository.

### Existing guarded transition convention

```python
changed = connection.execute(
    """UPDATE advanced_jobs SET status = ?, stage = ?, stage_recorded_at = ?,
       rejection_reason = ?, audit_reference = ?, updated_at = ?
       WHERE id = ? AND status = ?""",
    values,
).rowcount
if changed != 1:
    raise ValueError("advanced job state changed; refresh and retry")
```

`[VERIFIED: backend/app/advanced/repository.py:347-360]` Adapt the pattern with an expected transition version and an append-only Alpha event in the same transaction; do not copy its authorization/audit semantics.

## State of the Art

| Old approach in this repository | Phase 45 approach | Impact |
|---|---|---|
| Module-level walk-forward progress with five-minute TTL | SQLite event ledger with run sequence/idempotency and bounded history reads | Restart/reconnect can recover facts instead of stale or lost in-memory history. |
| `JobStore` terminal JSON and in-memory active cursor | `JobStore` as optional worker adapter behind durable Alpha run facts | Operational worker recovery cannot rewrite scientific history. |
| Separate immutable tables with no-update/no-delete triggers | Same triggers plus one guarded run status cursor and transition version | Lifecycle can progress while identity/evidence remains immutable. |
| LangGraph saver/checkpoint as graph-local recovery state | Dedicated Alpha checkpoint contract bound to snapshot/event/candidate digests | Resume detects stale/inconsistent cursor and does not become authority. |

**Deprecated/outdated for Phase 45:** treating `_wf_jobs`, process memory, or terminal JSON files as the Alpha run ledger; accepting current/latest data on replay; using a client-provided status/event sequence; storing raw checkpoint/provider payloads in SQLite.

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | The proposed table names and module names are suitable decomposition (`research_alpha_*`, `run_contract.py`, `run_service.py`, `run_api.py`). | Recommended Project Structure / Schema | Planner may need to choose different names while preserving the listed constraints. |
| A2 | A dedicated append-only checkpoint table is preferable to an event-only projection for Phase 45. | Architecture Patterns | A typed event plus latest projection could reduce tables but must prove the same uniqueness and cursor checks. |
| A3 | `preflight_failed` is the run-level terminal status for invalid/incomplete preflight; candidate attempts retain a distinct `invalid` outcome. | Lifecycle matrix | Resolved by D-06 and AF-REQ-04; API tests must assert both scopes. |
| A4 | Alpha artifact references share the existing managed `research_artifacts` root with a distinct digest-derived namespace. | Artifact references | Resolved: server generates `research_artifacts/alpha_runs/{run_id}/{sha256}.json`; clients cannot choose paths. |
| A5 | A linked retry may safely reuse the exact frozen manifest digest while receiving a new run ID/attempt identity. | Retry semantics | A retry that changes a declared dimension creates a new snapshot/digest and records the changed field. |
| A6 | `BEGIN IMMEDIATE` is acceptable for short run/event/checkpoint writes at the expected single-host research scale. | Sequence allocation | Keep transactions short and validate deployment filesystem assumptions. |

## Resolved Decisions

1. **Invalid versus preflight status — (RESOLVED):** A malformed or incomplete run specification fails before queueing with run status `preflight_failed` and a bounded machine-readable terminal reason. A generated candidate that fails expression validation is retained as candidate status `invalid`; it never becomes a run status. The enum and projection tests cover both scopes.
2. **Checkpoint inline/artifact boundary — (RESOLVED):** A checkpoint may carry only a canonical UTF-8 JSON summary no larger than 16 KiB (`MAX_INLINE_CHECKPOINT_BYTES = 16 * 1024`). Frontier/queue/state beyond that limit must be written first to a verified managed artifact whose server-generated relative key is `research_artifacts/alpha_runs/{run_id}/{sha256}.json`; the descriptor stores type, size, and lowercase SHA-256. Oversized inline input and client-supplied paths are rejected.
3. **Stale-worker fencing — (RESOLVED):** Every transition to `running` generates an opaque server-owned `attempt_token`; only its SHA-256 is persisted. Worker callbacks must provide the token and expected `transition_version`. Any cancel, terminal transition, retry, or version change invalidates the old token. No separate lease is needed for Phase 45 because the token/version pair is the concurrency fence.
4. **Application mounting — (RESOLVED):** `backend/app/main.py` initializes `ResearchRepository` from the existing `operational.database_path`, constructs `ResearchRunService`, stores it as `app.state.research_run_service`, and includes the typed Phase 45 router. Routes never call repository SQL directly. The service exposes bounded candidate/fold progress counters but does not evaluate folds.

These resolutions replace the former open questions and are incorporated into `45-CONTEXT.md` D-03, D-09, D-10, and D-11. No unresolved Phase 45 research decision remains.

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|---|---|---:|---|---|
| Python | Repository/service/tests | ✓ | 3.11.2 observed | None; project requires `>=3.11`. |
| SQLite CLI/runtime | Migration and operational DB | ✓ | SQLite CLI 3.40.1 observed; Python `sqlite3` is the application API | Use Python `sqlite3` through existing repository if CLI is absent in deployment. |
| FastAPI/Pydantic | Typed API DTOs | Declared and used by the project | Existing lock baseline; do not upgrade for this phase | None needed; reuse current environment. |
| Managed data directory | Artifact references | ✓ in current app wiring | `store.data_dir`-derived | Fail closed if root cannot be created/read or artifact verification fails. |
| External queue/provider | Not required by Phase 45 | Intentionally absent | — | Do not add a fallback queue; synchronous durable contract operations remain available. |

No external dependency installation is required. The phase is code/schema-only over existing runtime services; no provider, broker, or external database is a prerequisite.

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest `>=8.0`, pytest-asyncio `>=0.23` `[VERIFIED: backend/pyproject.toml:78-83]` |
| Config file | `backend/pyproject.toml`; `asyncio_mode = "auto"`, import mode `importlib` `[VERIFIED: backend/pyproject.toml:108-115]` |
| Quick run command | `cd backend && pytest tests/test_operational_migrations.py tests/research/test_run_contract.py -q` [ASSUMED future test path] |
| Full suite command | `cd backend && pytest -q` [existing project command; not run in this research wave] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test type | Automated command | File exists? |
|---|---|---|---|---|
| AF-REQ-01 | Complete server-frozen manifest is canonical/digest-bound; duplicate same request is idempotent; changed input creates linked new run; missing required field fails closed | Repository/service integration | `pytest tests/research/test_run_contract.py -k 'manifest or create or idempotency' -q` | No — Wave 0 |
| AF-REQ-04 | Every attempt status/reason/seed/step/lineage/evidence reference persists, including duplicate/invalid/failed/rejected/admitted/cancelled/budget exhaustion; no update/delete | Repository integration/property-style bounded cases | `pytest tests/research/test_run_contract.py -k 'candidate or lineage or append_only' -q` | No — Wave 0 |
| AF-REQ-10 | Replay from stored manifest/events/candidates/checkpoints reproduces order and rejects missing/mismatched artifact or cursor | Repository/service integration | `pytest tests/research/test_run_contract.py -k 'replay or checkpoint or artifact' -q` | No — Wave 0 |
| AF-REQ-16 | Transition matrix, cooperative cancel, duplicate start/retry/cancel, restart recovery, and no repeated committed side effect | Repository/service/API integration | `pytest tests/research/test_run_contract.py tests/api/test_run_api.py -k 'lifecycle or cancel or retry or restart' -q` | No — Wave 0 |
| Migration safety | New migration rolls back all objects/version on injected failure and reapplies idempotently | SQLite migration test | `pytest tests/test_operational_migrations.py -k 'atomic\|restart\|phase45' -q` | Existing migration file; add Phase 45 cases |
| API safety | Strict DTOs reject extras/oversized fields; projections hide paths/raw diagnostics; state conflicts map to 409 | FastAPI `TestClient` | `pytest tests/api/test_run_api.py -q` | No — Wave 0 |

### Required focused scenarios

1. Two concurrent create calls with the same principal/key/digest yield one run and one `run_created` event; same key/different digest yields conflict.
2. Two transition attempts with the same expected version produce one committed transition; the loser cannot append an event.
3. The event ledger has contiguous per-run sequence, unique idempotency keys, stable payload checksums, and no published-before-commit callback.
4. Attempt insertion retains a duplicate and a failed candidate rather than `INSERT OR IGNORE` dropping them; parent links cannot cross runs.
5. Every legal lifecycle edge succeeds and every illegal edge rolls back without changing status/version/event count.
6. A checkpoint referencing a missing candidate, future sequence, stale snapshot digest, changed artifact size, or changed artifact bytes fails closed and does not advance the run.
7. Crash simulation between transaction commit and publisher callback still replays the committed event; restart with an invalid cursor cannot resume.
8. Cancel requested before start, during a candidate boundary, after terminal completion, and repeated with the same key all return durable, non-contradictory states.
9. Retry returns the existing child for the same retry key; a changed declared input creates a new snapshot/run and leaves the parent byte-for-byte unchanged.
10. Static/runtime guard confirms no Phase 45 route/service imports broker/order/portfolio/monitor or invokes factor evaluation/provider/OOS/promotion.

### Sampling Rate

- **Per task commit:** targeted migration/repository/API test selection under 30 seconds.
- **Per wave merge:** Phase 45 focused tests plus migration tests.
- **Phase gate:** full backend suite and end-to-end verification before `/gsd-verify-work`; not run in this research wave.

### Wave 0 Gaps

- [ ] `backend/tests/research/test_run_contract.py` — migration/repository/service manifest, candidate, event, checkpoint, artifact, lifecycle, idempotency, restart, and cancellation contracts.
- [ ] `backend/tests/api/test_run_api.py` — strict DTO, safe projection, route status/error, event-history, and server-owned identity contracts.
- [ ] Extend `backend/tests/test_operational_migrations.py` — Phase 45 rollback, trigger, FK, check, unique sequence/idempotency, and reapply coverage.
- [ ] A deterministic test clock and temporary managed artifact root fixture, following existing `tmp_path` repository fixtures. `[VERIFIED: backend/tests/research/conftest.py:107-112]`

## Security Domain

Security enforcement is enabled in `.planning/config.json` (`security_enforcement: true`, ASVS level 1). `[VERIFIED: .planning/config.json:46-50]`

### Applicable ASVS Categories

| ASVS Category | Applies | Standard control |
|---|---|---|
| V2 Authentication | Yes | Derive principal from existing authenticated request middleware; never accept principal/authority from run payload. |
| V3 Session Management | Yes | Scope every get/replay/event/cancel/retry query to authenticated principal where the host requires it; use server-generated run IDs and worker tokens. |
| V4 Access Control | Yes | Server owns status, manifest, candidate/evidence IDs, transition, cancellation, and retry authority; reject browser-selected policy/OOS/promotion/execution fields. |
| V5 Input Validation | Yes | Strict Pydantic `extra="forbid"`, bounded text/list/JSON sizes, strict digest/path validation, allowed status/event enums, and artifact subset/reference checks. |
| V6 Cryptography | Integrity only | Use SHA-256 for canonical identity/integrity, never as password encryption or authorization; do not hand-roll cryptographic signing. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard mitigation |
|---|---|---|
| Idempotency-key collision/replay | Tampering / Repudiation | Unique principal+key and event key constraints; same payload returns original fact, different payload conflicts. |
| Client-forged status/sequence/evidence | Elevation of privilege | Server-owned DTO fields, guarded SQL transition, monotonic sequence allocation, allowlisted projection. |
| Artifact traversal/tampering | Tampering / Information disclosure | Managed relative paths, run namespace, exclusive writes, byte-size and lowercase SHA-256 verification. |
| Stale worker callback | Tampering / Denial of service | Expected version/run token, terminal-state guard, no side effect on failed transition. |
| Checkpoint deserialization/code execution | Elevation of privilege | No pickle/arbitrary code; bounded JSON cursor plus content-addressed artifact with schema/checksum. |
| Raw diagnostics/secrets in events | Information disclosure | Bounded reason codes/summaries; private storage policy for raw responses; public DTO allowlist. |
| Accidental broker/live execution | Elevation of privilege | No imports/collaborators/routes; static import scan and runtime mocks in focused tests. |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/45-durable-governed-run-contract/45-CONTEXT.md:19-77` — locked persistence, manifest, event, lifecycle, checkpoint, replay, worker, API, and scope decisions.
- `.planning/ROADMAP.md:29-44` — Phase 45 goal, requirements, success criteria, and research flag.
- `.planning/REQUIREMENTS.md:25-50` — AF-REQ-01, AF-REQ-04, AF-REQ-10, AF-REQ-16 and research-only boundary.
- `backend/app/operational/migrations.py:1705-1811,1890-1918` — append-only walk-forward schema, triggers, checks, and atomic migration runner.
- `backend/app/research/repository.py:25-63,74-93,319-435` — canonical JSON, SHA-256 validation, short-lived SQLite repository, immutable experiment/artifact transactions.
- `backend/app/research/artifacts.py:21-40,43-76` — immutable descriptor shape and application-owned artifact root.
- `backend/app/advanced/repository.py:45-136,347-392` — short-lived connection, idempotent acquisition, guarded transition, atomic audit/transition pattern.
- `backend/app/advanced/jobs.py:182-267` — server-owned workflow invocation, transition and post-commit publisher seam; authorization-specific behavior is not reused.
- `backend/app/advanced/workflow.py:18-94,97-188` — compact server state, server thread binding, SQLite checkpoint saver, bounded untrusted draft projection.
- `backend/app/api/walkforward_sse.py:26-74,77-142,145-188` — current volatile replay implementation and its TTL/reset limitations.
- `backend/app/services/pipeline_jobs.py:44-75,103-187,219-280` — JobStore active-memory/terminal-file lifecycle and stale-job limitation.
- `backend/app/main.py:130-150,187-190` — shared data directory, `operational.db`, repository, and separate checkpoint wiring.
- `backend/tests/test_operational_migrations.py:41-74,115-150` — existing atomic rollback/reapply test pattern.
- `backend/pyproject.toml:1-39,78-115` — Python/dependency/test configuration.
- `data/operational.db` — inspected current schema/data inventory; no Phase 45 Alpha tables present.

### Secondary (MEDIUM confidence)

- `.planning/research/SUMMARY.md:8-14,69-96,115-121` — v3.0 synthesized architecture and Phase 45 rationale.
- `.planning/research/ARCHITECTURE.md:122-204,238-261` — target run/event/checkpoint/storage/API contracts; additions are recommendations, not existing implementation.
- `.planning/research/STACK.md:8-16,52-76,90-113` — no-new-dependency, SQLite/LangGraph/SSE boundaries and compatibility risks.
- `.planning/research/PITFALLS.md:18-32,64-78,93-102` — OOS, provenance, replay/cancellation, artifact, and authority risks.
- Official SQLite transaction and WAL guidance cited by `.planning/research/STACK.md:150-158` (cross-check deployment locking/filesystem assumptions before enabling WAL).

### Tertiary (LOW confidence / not used as implementation authority)

- No low-confidence web claim is required for the Phase 45 recommendation. Local v3.0 analyses are pattern references only; no AlphaMaster/PA_Agent source or code is to be copied.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — existing `pyproject.toml`, repositories, migration runner, and locked no-new-dependency decision were inspected.
- Architecture: HIGH for current seams; MEDIUM for new schema/module names and checkpoint representation, explicitly marked `[ASSUMED]`.
- Pitfalls: HIGH — current code demonstrates the relevant migration, guarded-transition, artifact, JobStore, and volatile-SSE boundaries.
- Validation: HIGH for pytest configuration and existing migration fixtures; MEDIUM for exact Wave 0 filenames until the planner locks decomposition.

**Research date:** 2026-08-08  
**Valid until:** 2026-09-07 for stable repository contracts; re-check if SQLite/LangGraph/FastAPI lock versions or deployment topology changes.
