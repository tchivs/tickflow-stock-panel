# Phase 45: Durable Governed Run Contract - Context

**Gathered:** 2026-08-08  
**Status:** Ready for planning  
**Source:** User-approved v3.0 six-phase direction, existing v2.5 contracts, and `.planning/research/SUMMARY.md`.

<domain>
## Phase Boundary

Deliver the server-owned durable contract for a replayable Alpha Factory/FactorResearchAgent run: immutable run specification and input snapshot, append-only candidate/event/checkpoint facts, lifecycle transitions, idempotency, and restart-safe recovery cursors. A researcher must be able to create, inspect, retry, cancel, and replay run facts without mutating an earlier run or repeating a committed side effect.

This phase does not generate factor expressions, evaluate folds, call a provider, run Stage 1/2 Agent logic, promote a factor, add UI workbench views, or touch broker/execution paths.

</domain>

<decisions>
## Implementation Decisions

### Authority and persistence

- **D-01:** Keep `operational.db` as the authoritative store for small immutable run metadata, lifecycle transitions, candidate-attempt metadata, event envelopes, idempotency keys, and checkpoint cursors. Do not add Redis/Kafka/NATS/Celery/RQ or another database.
- **D-02:** Put the Phase 45 implementation in the `backend/app/research/` domain and reuse `backend/app/operational/migrations.py` plus the existing short-lived SQLite repository/transaction patterns. Do not place Alpha Factory tables in `advanced_*` strategy/authorization tables.
- **D-03:** Large evidence/response/checkpoint payloads are artifact references, not unbounded SQLite blobs: store a content-addressed key under `research_artifacts/alpha_runs/{run_id}/{sha256}.json` plus lowercase SHA-256, size/type metadata, and a bounded JSON summary; the digest-derived relative path is server-generated, never client-supplied. Inline checkpoint JSON is limited to 16 KiB UTF-8 and larger state must use a verified artifact; missing or mismatched artifacts fail closed.

### Immutable run and event contracts

- **D-04:** A run is created from a server-frozen specification containing DSL/grammar/vocabulary/policy versions, seed, candidate/expression budgets, objective/cost policy, universe, measured date range, fold geometry, and code/data manifest. The canonical JSON and digest are persisted before work starts; changing any input creates a new linked run.
- **D-05:** Candidate attempts and lifecycle events are append-only. Each event has a run-scoped monotonic sequence, event type, occurred-at, idempotency key, actor/source, bounded payload or artifact reference, and checksum; durable facts are committed before any in-process publisher is notified.
- **D-06:** Lifecycle transitions are server-owned and fail closed. Support at least `queued`, `preflight_failed`, `running`, `cancel_requested`, `cancelled`, `completed`, and `failed`; duplicate start/retry/cancel requests return the existing durable state rather than creating a second side effect.
- **D-07:** A checkpoint is a recovery cursor over committed run/candidate/event facts, bound to the run snapshot digest and input manifest. A cursor is written only after its referenced side effects commit; a stale, missing, or checksum-inconsistent cursor cannot advance work.

### Replay and integration surface

- **D-08:** Replay reads only the frozen manifest and durable event/candidate/checkpoint facts. It must be deterministic and read-only in Phase 45; it must not silently fetch current constituents, rewrite historical facts, or consume reserved OOS.
- **D-09:** Expose a minimal server API/service seam for create, get/replay, retry, cancel, event-history, candidate-history, and bounded progress reads so later Factory/Agent/UI phases consume one contract. Phase 45 need not provide a browser workbench or live SSE transport; Phase 50 owns the user-facing projection and reconnect transport. `backend/app/main.py` must initialize the shared `ResearchRepository`, construct `ResearchRunService`, store it in `app.state.research_run_service`, and include the typed router.
- **D-10:** Any background execution adapter is an untrusted worker around the research run service. Each `running` transition issues a server-generated opaque `attempt_token`; only its SHA-256 is persisted, and callbacks must supply the token plus expected `transition_version`. Terminal/cancel/retry/version changes invalidate older tokens. The adapter may request a transition/checkpoint/progress update but cannot choose policy, mutate frozen inputs, bypass idempotency, or grant execution/promotion authority.
- **D-11:** The run cursor exposes bounded `candidate_attempts_total`, `candidate_attempts_completed`, `folds_total`, and `folds_completed` counters through the safe projection/API. Phase 45 persists and tests these server-owned counters and allows a worker to report bounded progress; it does not calculate or evaluate factor folds. A fresh run may report zero/declared fold totals until later phases populate evidence.

### Claude's Discretion

- Exact table/column names, index names, enum representation, and repository class decomposition, provided the observable fields and constraints above are explicit and covered by tests.
- Whether a checkpoint is represented as a dedicated table or a typed append-only event plus current projection, provided restart recovery and uniqueness constraints are transactionally proven.
- Exact API route naming and response envelope, provided it follows existing FastAPI route and projection conventions and keeps raw internal diagnostics private.

</decisions>

<specifics>
## Specific Ideas

- Prefer the existing `AdvancedRepository`/`AdvancedWorkflow` transaction and checkpoint patterns as implementation references, but do not reuse their authorization or `advanced_*` domain authority.
- Prefer the existing `ResearchRepository` JSON/digest validation and immutable catalog conventions for research facts.
- Persist event history before publication. Later SSE/poll clients must be able to replay from a durable sequence instead of relying on an in-memory queue.
- Treat duplicate requests, process restart, stale checkpoint, and artifact mismatch as first-class acceptance scenarios, not logging-only paths.

</specifics>

<canonical_refs>
## Canonical References

### Milestone and phase contracts

- `.planning/PROJECT.md` — v3.0 goal, research-only and no-execution boundaries.
- `.planning/ROADMAP.md` §Locked Boundaries and §Phase 45 — phase goal, requirements, success criteria, dependencies, and non-goals.
- `.planning/REQUIREMENTS.md` — AF-REQ-01, AF-REQ-04, AF-REQ-10, AF-REQ-16 and global execution boundary.
- `.planning/research/SUMMARY.md` — synthesized architecture, persistence, replay, and risk decisions.
- `.planning/research/ARCHITECTURE.md` — target run/event/candidate/checkpoint contracts and integration seams.
- `.planning/research/PITFALLS.md` — immutability, event replay/cancellation, provenance, and stale-data failure modes.
- `.planning/research/STACK.md` — no-new-dependency recommendation and SQLite/LangGraph/SSE constraints.

### Existing implementation patterns

- `backend/app/operational/migrations.py` — versioned atomic SQLite migrations and foreign-key handling.
- `backend/app/operational/repository.py` — short-lived connections, transaction boundaries, validation, and row projection patterns.
- `backend/app/research/repository.py` — immutable research metadata, JSON canonicalization, and SHA-256 validation patterns.
- `backend/app/advanced/repository.py` — immutable advanced facts and transaction-safe state transitions; reference only, not domain authority.
- `backend/app/advanced/jobs.py` — lifecycle/idempotent transition and publisher seam patterns; authorization is out of scope.
- `backend/app/advanced/workflow.py` — SQLite checkpoint saver and server-owned workflow state patterns; Agent orchestration is out of scope.
- `backend/app/api/walkforward_sse.py` — existing progress replay behavior; its module-level volatile store is not sufficient as Phase 45 authority.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `migrate_operational_db` and the versioned `MIGRATIONS` tuple provide the existing SQLite schema evolution path.
- `OperationalRepository` and `ResearchRepository` provide parameterized connections, transaction context managers, canonical JSON, digest validation, and safe record conversion.
- `AdvancedRepository`/`AdvancedJobService` provide useful lifecycle transition, idempotency, and publisher seams that can be adapted without importing authorization authority.
- `PersistentAdvancedGraph` demonstrates a durable SQLite checkpoint integration, but Phase 45 should keep the generic run cursor contract independent of Agent graph execution.

### Established Patterns

- Operational state is SQLite-backed and migrations are applied on repository initialization.
- Research records retain immutable provenance and reject malformed/non-canonical SHA-256 values.
- Public projections are allowlisted; raw policy, paths, provider data, and internal diagnostics are not returned by default.
- Existing in-memory walk-forward job history is replayable only for a TTL; Phase 45 must establish durable event history before later SSE/poll projection.

### Integration Points

- New research run repository/service connects to `backend/app/operational/migrations.py` and the SQLite path/configuration used by existing repositories.
- Later Phase 46 candidate generation consumes the run specification, candidate ledger, event append, and checkpoint APIs.
- Later Phase 47 evidence/OOS services consume immutable input snapshot and lifecycle facts without rewriting them.
- Later Phase 48 Agent orchestration consumes preflight/run/event/checkpoint contracts; Phase 50 exposes event history through SSE/polling.
- No Phase 45 code may import broker/order/portfolio mutation or activate `frontend/src/pages/Watchlist.tsx`.

</code_context>

<deferred>
## Deferred Ideas

- Restricted vocabulary enumeration, mutation/crossover, lineage scoring, diversity, and budget scheduling — Phase 46.
- Shared-chain evaluation, admission evidence, cost/robustness, and reserved selection OOS — Phase 47.
- Provider preflight, Stage 1/2 schemas, retries, and Agent checkpoints — Phase 48.
- Promotion Ticket, reviewer refresh, and FactorRevision/catalog handoff — Phase 49.
- SSE/poll reconnect UI, comparison/lineage/stress views, degradation labels, and release scans — Phase 50.
- Neural/RL search, external queues, automatic promotion, broker/live execution, arbitrary Python, and second evaluator — deferred beyond v3.0.

</deferred>

---

*Phase: 45-durable-governed-run-contract*  
*Context gathered: 2026-08-08*
