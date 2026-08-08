# Technology Stack

**Project:** AthenaQuant v3.0 Alpha Factory + FactorResearchAgent
**Researched:** 2026-08-08
**Recommendation:** Reuse the existing Python/FastAPI/SQLite/LangGraph/Polars stack. Add no new base runtime dependency for this milestone.
**Overall confidence:** MEDIUM (HIGH for repository integration points; MEDIUM for versioned library behavior verified against current official documentation)

## Executive Recommendation

The v3.0 milestone is implementable inside the current runtime. Deterministic factor search needs a small, ordered grammar/evolution runner using Python standard-library primitives (`random.Random`, `hashlib`, `json`, dataclasses) and the already governed `factor_dsl`/`FactorSignalChain`. It does not need Optuna, Ray, a neural search model, PyTorch, or a second expression engine. Candidate evaluation must call the existing `FactorSignalChain.compute()` and then the existing factor evaluation/admission boundaries; a search-specific evaluator must not become a second signal implementation.

Durable search events and checkpoints should use the operational SQLite database and the already installed `langgraph==1.2.9` plus `langgraph-checkpoint-sqlite==3.1.0`. LangGraph's SQLite saver is appropriate for resumable graph state, but it is a recovery cursor, not the authoritative audit/event history. Add append-only, versioned research tables through `app.operational.migrations` and repository methods; keep a separate event sequence for replay, idempotency, and audit. The existing forecast job transition design is the closest in-repository precedent.

The two FactorResearchAgent stages should use existing Pydantic v2 models with `ConfigDict(extra="forbid")`, bounded fields, immutable server-owned input, and `model_validate_json()` on raw provider output. Stage 1 should produce a validated diagnosis/hypothesis envelope; Stage 2 should consume only the validated Stage 1 result plus frozen factor/data evidence and produce a validated research plan or candidate proposal. Neither stage may directly mutate the registry, bypass OOS reservations, or trigger execution.

Progress should remain HTTP SSE plus polling. `sse-starlette==3.4.4`, FastAPI, native browser `EventSource`, and React Query are already present. The persisted event table is the source of truth; an in-memory subscriber hub is only a wake-up optimization. Implement `Last-Event-ID`/monotonic sequence replay and a bounded GET-events endpoint, following the existing forecast API, rather than adding WebSockets, Redis pub/sub, Celery, Kafka, or another broker.

## Current Runtime Baseline

The declarations below are from `backend/pyproject.toml`; exact versions are the current `backend/uv.lock` resolution observed on 2026-08-08. The lock is the reproducible baseline for v3.0; broad lower bounds in `pyproject.toml` must not be mistaken for a tested upgrade policy.

### Core Framework and Runtime

| Technology | Declared requirement | Current lock | v3.0 use | Guidance |
|------------|----------------------|--------------|-----------|----------|
| Python | `>=3.11` | Project constraint | All search, agent, and job code | Preserve; use typing/dataclasses/stdlib rather than a new runtime framework. |
| Hatchling | build backend | Current lock/build metadata | Package `app` | No change. |
| FastAPI | `>=0.115` | `0.136.1` | Factor-search/agent REST and event endpoints | Reuse existing routers and request models. |
| Uvicorn | `>=0.30` with `standard` | `0.47.0` | ASGI host | No separate worker server for research jobs. |
| Pydantic | `>=2.7` | `2.13.4` (`pydantic-core 2.46.4`) | Strict request, stage, event, and result DTOs | Reuse v2 APIs; avoid `jsonschema` as a parallel validation system. |
| `sse-starlette` | `>=2.0` | `3.4.4` | SSE response, heartbeat, disconnect handling | Already used by `app.api.intraday`; no new stream protocol. |
| `httpx` | `>=0.27` | `0.28.1` | Existing AI/provider transport | Agent stages call the existing provider adapter; do not add an agent-specific HTTP client. |
| APScheduler | `>=3.10` | `3.11.2` | Existing scheduling boundary where a research run is scheduled | Do not add Celery/RQ merely to launch a search. |

### Data, Evaluation, and Persistence

| Technology | Declared requirement | Current lock | v3.0 use | Compatibility note |
|------------|----------------------|--------------|-----------|-------------------|
| Polars | `>=1.0` | `1.40.1` (runtime 32-bit package) | Factor panels, DSL expressions, candidate evaluation | Keep the existing panel/schema contract; use lazy Parquet scans where useful. |
| DuckDB | `>=1.0` | `1.5.3` | Existing lake/query boundary | Search reads governed snapshots/panels; it should not introduce a separate warehouse. |
| PyArrow | `>=16.0` | `24.0.0` | Parquet artifacts and metadata | Preserve artifact checksums and manifests. |
| NumPy | Transitive | `2.4.6` | Existing numerical dependencies | Do not make it the public search API or add a competing array framework. |
| SciPy | `>=1.17.1,<1.18` | `1.17.1` | Existing HRP/dependency surface | Keep the upper bound; do not upgrade while changing search semantics. |
| SQLite (`sqlite3`) | Python standard library | SQLite runtime supplied by Python/OS | Immutable registry, research facts, job transitions, new search events | Use existing operational DB and migration sequence; one writer at a time remains a design constraint. |
| `langgraph` | `==1.2.9` | `1.2.9` | Existing fixed agent graph orchestration | Reuse only for explicit two-stage state/recovery; do not create a second orchestration stack. |
| `langgraph-checkpoint-sqlite` | `==3.1.0` | `3.1.0` (`aiosqlite 0.22.1`) | Existing SQLite graph checkpoints | Already a base dependency. Keep pinned as a unit with LangGraph. |

### Frontend Runtime

`frontend/package.json` already provides React `18.3.1`, React Query `5.55.0`, native browser `EventSource` usage, and TypeScript/Vite. `frontend/src/lib/useQuoteStream.ts` parses allowlisted progress events, tracks reconnecting/disconnected state, and applies exponential backoff. No frontend dependency is required for v3.0 progress. Add a research-specific hook/query only; do not add an SSE client package or WebSocket library.

## Existing Integration Points

| Need | Current seam | Reuse contract |
|------|--------------|----------------|
| Restricted factor representation | `backend/app/research/factor_dsl.py`: `DSL_VERSION`, `parse_factor()`, `compile_factor()`, AST/signature extraction, denied fields, partition context, shifted-label IC gate | Search emits canonical DSL expressions only. Every candidate is parsed/compiled through this module before evaluation. Never evaluate generated Python source or arbitrary expressions. |
| Immutable factor identity | `backend/app/research/factor_registry.py`: `FactorRevision`, `FactorRegistry` | Candidate identity should carry parent revision/DSL version, canonical expression, AST/shape signatures, and provenance; registration remains a post-gate action. |
| One signal implementation | `backend/app/research/signal_chain.py`: `SignalChainConfig`, `FactorSignalChain.compute()` | Search, backtest, catalog, and future serving must share this path. Include its panel/universe fingerprints in candidate/run metadata. |
| Governed evaluation | `backend/app/research/evaluation.py`: `ResolvedEvaluationConfig`, `FactorEvaluationService.evaluate()`, `FactorEvaluationResult` | Candidate scores are evidence packages, including failed/invalid outcomes and artifacts. Do not select on an untracked ad-hoc score. |
| Durable facts/artifacts | `backend/app/research/repository.py`: `ResearchRepository`, `create_experiment()`, append-only WF plan/fold/search records; `app.operational.migrations.migrate_operational_db()` | Add migration-backed search run/candidate/event/checkpoint records using the existing transaction and immutable-trigger conventions. Keep Parquet/DuckDB artifacts in the lake and SQLite metadata/checksums in the DB. |
| Reserved OOS | `ResearchRepository.create_wf_plan()` and `wf_*` tables | Search must consume only non-OOS folds. The reserved exactly-once OOS path remains a hard boundary, not a configurable search option. |
| Durable graph state | `backend/app/analysis/graph.py:PersistentAnalysisGraph`, `backend/app/advanced/workflow.py:PersistentAdvancedGraph` | Reuse the per-invocation `AsyncSqliteSaver` setup and server-owned `thread_id` discipline. Store compact, bounded state; persist authoritative events separately. |
| Strict model output | `backend/app/analysis/model_adapter.py:ConfiguredAnalysisAdapter.ainvoke()` and `backend/app/analysis/schemas.py:GeneratedAnalysis` | Reuse `model_validate_json()` and `extra="forbid"`; create v3 stage DTOs rather than accepting free-form text. |
| Existing job authorization/progress | `backend/app/advanced/jobs.py:AdvancedJobService`, `set_progress_publisher()`, `_publish()` | Use its server-owned job lifecycle and committed progress semantics where FactorResearchAgent is hosted; do not let browser payloads establish authority. |
| Durable progress replay | `backend/app/forecast/api.py:ForecastProgressHub`, `job_events()`, and `forecast/repository.py:owned_job_transitions_after()` | This is the preferred pattern: persisted monotonic transitions are authoritative, hub queues wake live subscribers, and `Last-Event-ID` resumes from a sequence. |
| Current SSE transport | `backend/app/api/walkforward_sse.py` and `backend/app/api/intraday.py` | Replace module-level-only replay for new search jobs with repository-backed history; retain `EventSourceResponse`/`StreamingResponse` conventions and explicit disconnect handling. |
| Browser progress | `frontend/src/lib/useQuoteStream.ts` (`parseAdvancedProgress`, `EventSource`, reconnect/backoff) and React Query | Add an allowlisted event DTO and a GET polling fallback. Keep event payloads coarse and safe; UI never becomes a source of status authority. |

## Recommended Additions (Code and Schema, Not Packages)

1. **Deterministic search runner.** Implement an ordered grammar/AST mutation layer over the restricted DSL. Use a dedicated seed and a stable candidate order; record seed, grammar/operator registry version, parent candidate, mutation, canonical expression, and candidate digest. Use `random.Random(seed)` only if randomized exploration is desired; never use process-global RNG or hash iteration order. A deterministic exhaustive grammar for small budgets is preferable to a probabilistic optimizer in the first slice.
2. **Search run manifest.** Persist resolved data scope, calendar/fold geometry, DSL version, feature/operator vocabulary fingerprint, cost/slippage policy, execution timing, code/config provenance, seed, and resource limits before evaluating candidates. A rerun with the same manifest must either reuse an idempotent run or create a new run with a different identity, never silently mutate the old one.
3. **Append-only search records.** Add migration tables for a run, candidate attempts, ordered events, and resumable search checkpoints. Include `run_id`, monotonic `sequence`, event type, candidate identity/digest, stage, status, occurred time, compact payload JSON, and idempotency key. Add unique constraints and no-update/no-delete triggers matching `wf_*`/factor admission tables. Persist invalid, rejected, timeout, and failed candidates as first-class results.
4. **Two strict Agent stage contracts.** Add bounded Pydantic models with `ConfigDict(extra="forbid")` (and `frozen=True` for server-owned envelopes). Stage 1 consumes only a frozen factor/data context and emits structured diagnosis/hypothesis plus evidence references. Stage 2 consumes the validated Stage 1 model and emits a constrained search specification/candidate proposal. Validate raw JSON with `model_validate_json()`; on schema/semantic failure, record the raw-response hash, bounded diagnostics, retry count, and terminal failure event. Never let the model choose paths, tools, registry IDs, OOS folds, or execution authority.
5. **Event publisher plus replay endpoint.** Publish only after the durable transition commits. Use a bounded in-process hub to wake SSE subscribers, then read persisted events after `Last-Event-ID` (or a query cursor) to catch up. Add a polling endpoint with the same scope and sequence semantics for clients without a live stream. A queue overflow must force a reconnect/replay, not silently drop research evidence.
6. **Resource boundary.** Run long searches through the existing research/advanced job/process boundary with bounded candidate count, wall-clock budget, and cancellation. Keep Alpha Factory research-only: no broker imports, no automatic promotion, no execution side effects. A candidate can become a factor revision only through existing admission/retention gates and explicit operator action.

## Option Comparison and Decisions

| Concern | Recommended | Alternatives considered | Decision |
|---------|-------------|-------------------------|----------|
| Candidate search | Stdlib seeded grammar/evolution over `factor_dsl` | Optuna; Ray; AlphaMaster RL/AlphaGPT; PyTorch | **Use stdlib first.** It is deterministic, explainable, cheap to replay, and adds no dependency. Optuna/Ray introduce optimization state and version drift that are not needed for a first governed search. AlphaMaster's RL sampler and PyTorch are explicitly outside the v3.0 default and its reward/cost assumptions are not A-share contracts. |
| Formula representation | Existing restricted DSL + canonical AST/signatures | Python source; arbitrary `eval`; a new token VM | **Use existing DSL.** AlphaMaster's token/StackVM and vocabulary fingerprint are useful patterns, but reimplementing a second VM would split train/backtest/serve semantics. |
| Graph checkpointing | Existing LangGraph SQLite saver, pinned as a pair | Raw pickle files; Redis saver; cloud checkpoint store | **Use existing saver only for graph recovery state.** Raw pickle is unsafe/non-portable; Redis/cloud persistence violates the self-hosted SQLite boundary. |
| Authoritative events | Existing operational SQLite with append-only migrations/triggers | Redis streams/pubsub; Kafka; NATS; Celery result backend | **Use SQLite rows.** The repository already has immutable facts, idempotent transitions, and OOS records. A hub can be ephemeral; no broker is required for the research-only scale. |
| Agent JSON | Existing Pydantic v2 | `jsonschema`; marshmallow; provider-specific structured-output SDK | **Use Pydantic.** It is already the API/schema boundary and supports direct raw JSON validation. Provider structured output may be an optimization later, never the trust boundary. |
| Progress transport | Existing SSE + native `EventSource` + polling fallback | WebSockets; GraphQL subscriptions; frontend SSE package | **Use existing SSE.** It already has heartbeats, disconnect handling, reconnect/backoff, and typed event parsing. |
| Data compute | Existing Parquet/PyArrow + Polars + DuckDB | pandas-first search; vectorbt; Arrow Dataset rewrite | **Use shared data lake and chain.** pandas is intentionally a BacktestService boundary dependency, not a reason to add another search path; vectorbt remains optional and is not needed for factor candidate evaluation. |

## Explicit No-New-Dependency Recommendation

Do **not** add any new base or optional runtime dependency for v3.0. In particular:

- Do not add **PyTorch, JAX, TensorFlow, RL libraries, or GPU runtimes**. The milestone's default is deterministic seeded grammar/evolution; AlphaMaster's neural/RL search is an analysis reference, not a dependency requirement.
- Do not add **Optuna, Ray, Dask, or distributed task runners** before deterministic single-host search and durable replay are proven. They make scheduling and reproducibility harder and do not solve the provenance contract.
- Do not add **Celery, RQ, Redis, Kafka, NATS, or a separate event broker** for progress. SQLite transitions plus a bounded wake hub already cover durable replay and polling for this research-only scope.
- Do not add **jsonschema, instructor, pydantic-ai, or provider-specific agent frameworks**. Pydantic v2 already provides strict, versioned JSON contracts; another validator would create divergent acceptance semantics.
- Do not add **websocket/SSE client packages**. Browser `EventSource` and the current React Query stack are sufficient.
- Do not add **a second factor expression engine, arbitrary Python evaluator, or AlphaMaster source code**. PA_Agent is AGPL-3.0-or-later and AlphaMaster/PA_Agent are analysis references; current backend licensing is MIT. Absorb patterns, not upstream code.
- Do not promote `sqlite-vec`, already visible as a transitive lock artifact, into the search design. Candidate similarity is deterministic structural signatures/Jaccard and existing registry discovery, not a vector database requirement.

The only acceptable dependency change would be a future, separately justified capability that cannot be implemented with the current stack and is isolated behind an optional extra. That is not required for the v3.0 Alpha Factory + FactorResearchAgent scope.

## Compatibility Risks and Guardrails

1. **Dependency drift:** `pyproject.toml` exposes floors (`fastapi>=0.115`, `polars>=1.0`, etc.) while the lock captures tested versions. Keep the lock committed and update LangGraph plus checkpoint-sqlite together. Do not claim a new library API from a floor alone.
2. **LangGraph checkpoint schema/API:** `AsyncSqliteSaver` owns its checkpoint/writes tables and requires a valid server-generated `thread_id`. Keep its checkpoint DB path and application event tables deliberately separated or namespaced; do not query internal saver tables as the product event log. Test resume after process restart and duplicate invocation.
3. **SQLite concurrency and filesystem:** SQLite permits many readers but one writer. Event writes must be short, transactional, and serialized by the repository boundary. WAL can improve same-host reader/writer concurrency, but official SQLite documentation warns that WAL relies on same-host shared memory and is unsuitable for network filesystems; enabling it is a deployment decision, not a silent migration assumption.
4. **Event replay correctness:** In-memory queues can overflow or disappear on restart. Every event delivered by SSE must correspond to an already committed row; a client-provided cursor ahead of the stored transition version must be rejected. Reconnect must replay by sequence before switching to live notifications.
5. **Pydantic coercion:** `extra="forbid"` rejects undeclared fields, but default Pydantic parsing can coerce some primitive values. Use strict field types/`strict=True` where the stage contract requires exact numeric/bool semantics, then separately run semantic gates (evidence IDs, allowed operators, bounds, stage ordering).
6. **A-share temporal leakage:** Search must preserve `FactorSignalChain` warmup, calendar, membership, forward horizon, measured walk-forward, and reserved exactly-once OOS semantics. AlphaMaster's single-file reward, costs, and target timing cannot be transplanted without an A-share contract.
7. **SSE transport/version interaction:** FastAPI `0.136.1`, Starlette `1.0.1`, and `sse-starlette 3.4.4` are the current lock combination. Keep response headers, ping behavior, disconnect checks, and `Last-Event-ID` parsing covered together; do not mix examples written for older Starlette/SSE versions without checking the lock.
8. **Artifact provenance:** Polars/Arrow/DuckDB may optimize execution, but a changed schema, feature registry, code commit, data snapshot, or numeric dependency can change scores. Hash the input manifest and persist versions/config with every run; never treat a checkpoint alone as reproducibility evidence.
9. **License boundary:** Local PA_Agent analysis explicitly identifies AGPL-3.0-or-later. Use its two-stage/preflight/recording concepts only; do not copy code, assets, prompts, or strategy rules into the MIT backend.

## Roadmap Impact (4–6 Phases Starting at Phase 45)

1. **Phase 45 — Search contract and deterministic grammar.** Freeze candidate DSL grammar, canonical ordering, seed semantics, candidate digest, resource budget, and manifest fields. Reuse `factor_dsl`, `FactorRegistry`, and `FactorSignalChain`; explicitly leave PyTorch/Optuna out.
2. **Phase 46 — Durable Alpha Factory run state.** Add SQLite migrations/repository methods for run manifests, candidate attempts, append-only events, and checkpoints. Integrate measured-calendar walk-forward and reserved OOS before search reuse; verify idempotent restart and failed-candidate retention.
3. **Phase 47 — FactorResearchAgent strict stages.** Define Stage 1/Stage 2 Pydantic contracts, deterministic preflight, provider adapter calls, semantic gates, bounded evidence/provenance, and durable stage outcomes. Reuse LangGraph SQLite checkpoints only for recovery and preserve research-only authority.
4. **Phase 48 — Progress API and workbench.** Add replayable SSE plus polling using the existing forecast progress pattern (`Last-Event-ID`, monotonic sequence, bounded hub), and React Query/native `EventSource` rendering of stage/candidate progress, data date, degraded state, and failure reason.
5. **Phase 49 — Admission, replay, and operational hardening.** Connect accepted candidates to existing factor evaluation/admission/catalog and immutable revisions; exercise cancellation, crash recovery, duplicate events, OOS fail-closed behavior, stream reconnect, and artifact/provenance checks. Keep any future dependency experiment outside the base runtime and outside automatic execution.

**Ordering rationale:** deterministic representation and provenance must precede persistence; persistence must precede resumable Agent stages and progress because both depend on authoritative run identity/event sequences; admission comes last so search output cannot bypass existing governance. All phases are research-only and must not add broker execution.

## Sources

### Current repository (primary, inspected)

- `backend/pyproject.toml:1-39,41-76` — Python/runtime requirements and current dependency policy.
- `backend/uv.lock:120-146,181-213,632-705,1335-1425,1835-1934,2315-2505,3208-3425,3724-3751` — exact lock resolutions cited above.
- `backend/app/research/factor_dsl.py:17-69,138-166,311-377,443-525,580-606` — restricted DSL, signatures, partitions, compilation, and leakage gate.
- `backend/app/research/factor_registry.py:13-29,71-92,120-296` — immutable revisions and deterministic similarity discovery.
- `backend/app/research/signal_chain.py:38-64,92-170,213-267,282-328` — shared compute path, panel loading, universe and fingerprints.
- `backend/app/research/evaluation.py:36-65,103-170,184-260` — resolved evaluation config and evidence-producing evaluator.
- `backend/app/research/repository.py:74-138,319-404,901-1032` — SQLite transactions, immutable experiments, and idempotent OOS plan reservation.
- `backend/app/operational/migrations.py:1890-1918` and migration blocks around `1508-1812` — versioned migrations, append-only triggers, and walk-forward schema.
- `backend/app/analysis/graph.py:1-76`, `backend/app/advanced/workflow.py:1-188` — existing LangGraph SQLite checkpoint patterns.
- `backend/app/analysis/model_adapter.py:1-73`, `backend/app/analysis/schemas.py:1-161` — strict JSON provider boundary and immutable evidence contracts.
- `backend/app/forecast/api.py:1-165,339-371`, `backend/app/forecast/repository.py:443-477,512-527` — durable transitions, bounded progress hub, cursor replay, and SSE/poll precedent.
- `backend/app/api/intraday.py:17,144-241` and `backend/app/api/walkforward_sse.py:1-188` — current SSE implementations and their differing durability characteristics.
- `frontend/package.json:12-40`, `frontend/src/lib/useQuoteStream.ts:19-39,79-223` — existing React/EventSource dependency and progress parsing/reconnect.

### Local upstream analyses (pattern references only)

- `../docs/aaa/alphamaster/DEEP-ANALYSIS.md:71-145,164-179,198-236` and `QUICK-START.md:60-114` — restricted token/StackVM, vocabulary versioning, walk-forward/cost gates, shared signal chain; RL/PyTorch and execution assumptions are not adopted.
- `../docs/aaa/pa-agent/DEEP-ANALYSIS.md:6-35,72-90` and `QUICK-START.md:25-56` — preflight → two strict JSON stages → durable analysis record; AGPL and crypto/Price Action execution assumptions prohibit code reuse.
- `../docs/aaa/10-SYNTHESIS.md:25-44,80-129,219-239` — pipeline/data-contract/event-envelope/quality-gate/SSE principles and high-risk action boundaries.

### Official documentation (version behavior; MEDIUM confidence, cross-checked against source)

- LangGraph SQLite checkpoint README and replay examples: <https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-sqlite/README.md>
- Pydantic JSON validation: <https://github.com/pydantic/pydantic/blob/main/docs/concepts/json.md>
- Pydantic `extra="forbid"` and strict configuration: <https://github.com/pydantic/pydantic/blob/main/docs/concepts/models.md>
- SSE Starlette response/disconnect behavior: <https://github.com/sysid/sse-starlette/blob/main/_autodocs/01-eventsourceresponse.md>
- Polars Parquet scanning: <https://github.com/pola-rs/polars/blob/main/docs/source/user-guide/io/parquet.md>
- SQLite transactions: <https://www.sqlite.org/lang_transaction.html>
- SQLite WAL/concurrency/checkpointing: <https://www.sqlite.org/wal.html>

The research-plan web-search question on generic durable event designs returned no usable result; no low-confidence web claim is used to justify the recommendation. SQLite guidance above is based on the official SQLite documentation and the repository's existing migration/event patterns.
