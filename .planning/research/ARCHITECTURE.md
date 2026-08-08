# Architecture Patterns

**Project:** AthenaQuant v3.0 — replayable Alpha Factory + FactorResearchAgent  
**Domain:** A-share factor research and research-only candidate promotion  
**Researched:** 2026-08-08  
**Overall confidence:** HIGH for the current seams; MEDIUM for target contracts that require implementation

## Scope and assumptions

This document maps the v3.0 target onto the repository at `/home/orca/source/AthenaQuant`. It is an architecture recommendation, not a production implementation.

- **[ASSUMPTION]** Phase 44 is the current boundary; new milestone work starts at Phase 45, as requested. The phase numbers below are therefore recommendations for the next 4–6 phases, not a claim that they already exist.
- **[ASSUMPTION]** The first Alpha Factory implementation is deterministic and seeded: grammar/vocabulary enumeration, mutation, crossover, elite retention, lineage and cost pressure. It does not add PyTorch/RL, a broker, automatic execution, or arbitrary Python execution.
- **[ASSUMPTION]** SQLite `operational.db` remains the authoritative store for small immutable metadata and transitions. Parquet/JSON artifacts remain the evidence/data lake. A LangGraph/SQLite checkpoint file is resumable workflow state, not authoritative domain truth.
- **[ASSUMPTION]** A search candidate is a research-domain object until a Promotion Ticket is approved. It must not be represented by `advanced_strategy_candidates`, whose contract is explicitly strategy-specific.
- **[ASSUMPTION]** Candidate formulas are emitted as the existing restricted Factor DSL (canonical expression plus validated AST/signatures), not as executable source or a second formula runtime.

## Current architecture and seams

AthenaQuant already has the right separation for a governed factor factory. The data lake supplies governed panels; the research domain owns factor definitions and evidence; the backtest domain owns measured-calendar fold geometry; the UI reads strict projections. The missing piece is durable search/agent orchestration between these seams.

```text
Parquet / DuckDB / Polars data lake
             |
             v
  UniverseResolver (PIT membership) ---> FactorSignalChain
             |                                  |
             |                                  +--> factor DSL AST/Polars expression
             |                                  +--> values/rank/zscore + provenance
             v                                  v
     walkforward plan -----------------> fold_scorer / reserved OOS
             |                                  |
             +---------------------> ResearchRepository (SQLite metadata)
                                                |
                              evaluation -> admission -> catalog -> UI

v3.0 target additions:
  FactorResearchAgent: preflight -> diagnosis -> deterministic factory -> review
          |                                  |
          +--> durable run/event/checkpoint  +--> candidate/evidence/promotion ticket
```

### Existing module map

| Concern | Current source seam | Contract that must remain true |
|---|---|---|
| Restricted formula language | `backend/app/research/factor_dsl.py`: `parse_factor`, `compile_factor`, `compile_ast`, `FactorFeatures`, `ParsedFactor`, `DSL_VERSION`, `ALLOWED_FIELDS`, `_FUNCTION_PARTITION` | Parse and validate before constructing a Polars expression; denied label/identity fields and undeclared partition semantics fail closed. |
| Immutable factor identity | `backend/app/research/factor_registry.py`: `FactorRevision`, `FactorRegistry.create_factor/revise_factor/discover_similar` | Definitions and revisions are append-only; canonical expression, DSL version, AST signature, shape signature, fields/operators/functions and provenance are identity evidence. |
| One computation route | `backend/app/research/signal_chain.py`: `SignalChainConfig`, `FactorSignalFrame`, `FactorSignalChain.compute` | Revision-bound governed panel loading, PIT membership, warmup/missing-data treatment, factor values and signal metadata have one implementation. Alpha search must call or extend this chain, never implement a parallel factor evaluator. |
| Evaluation evidence | `backend/app/research/evaluation.py`: `ResolvedEvaluationConfig`, `FactorEvaluationResult`, `FactorEvaluationService.evaluate` | A valid run receives an ID before governed access; chain output becomes IC/RankIC, coverage, group/long-short evidence and checksum-backed artifacts. |
| Admission | `backend/app/research/admission.py`: `run_admission` | Structural no-lookahead, coverage, shifted-label leakage, similarity and temporal IC gates are deterministic; every verdict records gate results and resolved-universe evidence. |
| Catalog | `backend/app/research/catalog.py`: `ExperimentCatalog`, `ExperimentSnapshot`, `FactorEvidencePackage` | Evaluation evidence is immutable until explicitly retained; comparisons read retained snapshots only. |
| Research persistence | `backend/app/research/repository.py`: `ResearchRepository` and `backend/app/operational/migrations.py` research tables | `research_factor_*`, `research_experiments`, metrics, artifacts and provenance are FK-bound append-only metadata in `operational.db`; large payloads live under the managed data root. |
| Fold geometry and OOS | `backend/app/backtest/walkforward.py`: `build_plan`, `run_walk_forward`, `evaluate_best_params`, `fold_scorer` | Selection folds exclude the reserved segment; `evaluate_best_params` is the sole OOS write and exactly-once uniqueness binds the verdict to its OOS evidence. |
| Operational jobs | `backend/app/services/pipeline_jobs.py`: `JobStore.create/start/progress/succeed/fail/reap_stale` | It is a process-facing single-flight/progress cursor with JSON terminal files and a heavy-run mutex. It is not sufficient as the Alpha Factory event ledger. |
| Analysis workflow | `backend/app/analysis/service.py`: `AnalysisService.start_run`; `backend/app/analysis/graph.py`: `PersistentAnalysisGraph`, `build_analysis_graph` | Server freezes evidence, invokes a typed graph with a server-generated thread ID, validates output, then persists the report. Checkpoints are recovery state; report/run rows are domain facts. |
| Advanced lifecycle patterns | `backend/app/advanced/evolution.py`: `EvolutionService.create_candidate/evaluate_gate/approve`; `workflow.py`: `PersistentAdvancedGraph`, `AdvancedWorkflowState`; `repository.py` guarded transitions | Reusable: server-owned identity, allowlisted operations, deterministic gates, immutable evidence, explicit reviewer, idempotent terminal outcome, safe projections. Not reusable: strategy mutation semantics, arbitrary strategy sandbox, broker/monitor collaborators. |
| API projections | `backend/app/api/research.py`, `research_panels.py`, `walkforward_sse.py` | Existing manual factor and panel routes stay compatible. New routes should use strict DTOs and server-owned IDs, and streams should be replayable rather than browser-authoritative. |
| UI workbench | `frontend/src/pages/Backtest.tsx`, `backtest/FactorBacktest.tsx`, `backtest/ResearchLibrary.tsx`, `backtest/WalkForward.tsx`, `frontend/src/lib/api.ts`, `queryKeys.ts` | Add factory/run/ticket views to the existing research/backtest workspace; do not create a disconnected factor computation surface. |

## Current-to-target data flow

### 1. Freeze a research request before model or search work

`POST /api/research/alpha/runs` should accept a bounded research request: universe, asset type, date range, horizon, grammar/operator policy, population/budget limits, seed (or server-selected seed), and optional natural-language hypothesis. The browser supplies intent only; the server resolves the actual vocabulary, code/version, data snapshot and policy.

The service creates a `run_id` and immutable request digest, resolves `UniverseResolver.resolve_universe_daily`, and constructs a `ResearchInputSnapshot`. This snapshot should contain the data-lake source references/checksums, date/calendar semantics, PIT membership fingerprint, DSL/grammar/vocabulary versions, cost model, seed, and code/config versions. A stale or incomplete snapshot produces a terminal fail-closed run and no model call.

This follows `FactorEvaluationService` allocating an opaque evaluation ID before data access (`evaluation.py:184-187`) and `AnalysisService` freezing evidence before graph invocation (`analysis/service.py:81-94`). The Alpha Factory must not discover a fresh panel halfway through a run.

### 2. FactorResearchAgent stage 1: structured research diagnosis

The Agent is a research orchestrator, not the factor executor. Its first stage receives only the frozen snapshot summary and user hypothesis. A strict Pydantic model should produce diagnosis fields such as research question, permitted factor families, candidate constraints, expected failure modes, and evidence references. It may narrow an allowlisted search policy, but cannot add DSL fields/operators, alter the target horizon, expand dates, or override safety gates.

`PreflightResult` is deterministic and persisted before the stage-1 call. Missing dates, insufficient bars, invalid OHLC, missing required features, inconsistent membership, or unavailable artifacts return an explainable terminal state and do not call the provider. Raw provider output, parsed JSON, schema/semantic validation errors, retry count, provider/model/version, prompt template version and response hash are recorded in the run event/evidence trail.

The existing analysis graph (`analysis/graph.py:14-44`) is a useful graph/checkpoint boundary but its two nodes only validate frozen evidence and generate a report. Implement a separate FactorResearchGraph with typed nodes for `preflight`, `stage1_diagnosis`, `factory_search`, `stage2_review`, and `record_outcome`. Reuse the persistent SQLite saver and server-generated thread binding pattern, but keep all authoritative candidate, evidence, admission and promotion writes in injected domain services. Do not silently turn the existing stock-analysis graph into an autonomous search graph.

### 3. Deterministic Alpha Factory candidate generation

The factory resolves a stable `FormulaVocabulary` from the governed DSL field/function/operator registry. The vocabulary is a canonical ordered list plus `vocab_version = sha256(canonical_names_and_arity_and_partition)[:12]`; a changed field/operator order or grammar version makes old candidate tokens incompatible instead of silently reinterpreting them.

A bounded grammar emits only syntactically and semantically legal DSL ASTs. Candidate operators must be present in the current DSL policy, have declared arity/partition context, preserve `[N,T]` shape, and be causal. Generation may use:

- deterministic enumeration for a small initial population;
- seeded mutation (replace a field, operator, window or subtree);
- seeded crossover between compatible AST subtrees;
- a bounded elite pool with explicit diversity and factor-correlation penalties;
- cost pressure based on estimated window/operation complexity and measured execution time.

Every generated candidate receives a canonical expression, AST/shape signatures, seed and operation, parent IDs, generation/ordinal, grammar/vocabulary versions, and a status. Candidate generation itself must be replayable from `(run request digest, seed, parent candidate IDs, operation, ordinal)`; random state is metadata, not an opaque model artifact.

The candidate compiler should share `parse_factor`/`compile_ast` and the signal chain. A safe target extension is a source-binding seam in `FactorSignalChain` that accepts either a persisted `revision_id` or a validated transient candidate source, then funnels both through one private governed compute path. The chain may resolve a candidate's canonical AST/signatures without registering it as an admitted factor. It must not add a `StackVM`, direct-Polars candidate evaluator, strategy-specific signal path, or raw-data shortcut beside `FactorSignalChain.compute`.

### 4. Fold scoring and reserved OOS

Search candidates are evaluated through a factor-specific adapter at the existing `walkforward.run_walk_forward(..., fold_scorer=...)` seam. The adapter binds the candidate source to the shared chain, receives the fold's governed frame/membership, and returns compact metric evidence (IC/RankIC, coverage, turnover/exposure/cost pressure, invalid reason, and execution-time estimate). The default strategy scorer remains unchanged.

The measured-calendar geometry in `walkforward.py` is already the correct integrity boundary:

- `build_plan` pins actual trading dates and a reserved OOS fold;
- `run_walk_forward` evaluates selection folds by default and does not touch OOS;
- `evaluate_best_params` evaluates the chosen candidate/config on the reserved OOS exactly once;
- `wf_folds` uniqueness and `wf_validated_strategies.oos_evidence_fold_id` bind evidence to the one OOS write.

For Alpha Factory, avoid overloading `strategy_id` with a factor candidate. Either generalize the fold record to a typed `research_asset_kind/research_asset_id` binding, or create Alpha-specific evaluation rows that FK to `wf_plans` and reuse the same geometry/once-only service. In either case, OOS is a terminal, explicit action after search selection; no candidate ranking, elite replay, Agent review, threshold adjustment or promotion ticket may read or write it first.

### 5. Candidate evidence, admission and catalog

A completed selection evaluation stores a compact candidate-evaluation fact and checksum-backed artifacts. It links to the frozen input snapshot, the exact fold plan/manifests, candidate lineage, metric series and diagnostic reasons. A failed candidate is retained as a failed attempt, not dropped from the denominator of the search audit.

The final selected candidate is evaluated on the reserved OOS segment once. It then enters the existing admission service, with an admission policy version that includes both current factor gates and v3 cost/robustness/capacity gates. `run_admission` already records rejected and admitted verdicts and can link catalog evidence (`admission.py:129-134`); extend its evidence input rather than duplicating its checks in the factory.

The catalog retains evidence snapshots for explicit comparison. A candidate can be displayed and compared before promotion, but it is not a current factor catalog entry until a Promotion Ticket registers a new immutable `FactorRevision` (or a first-class composite model through the existing model/catalog path). Registration is the only clean cutover point from transient search identity to formal factor identity.

### 6. FactorResearchAgent stage 2: deterministic candidate review

Stage 2 receives only server-projected candidates and immutable evidence references from the run. It returns strict JSON containing candidate IDs, evidence-backed rationale, caveats, and a recommendation such as `reject`, `needs_replication`, or `request_promotion_review`. It cannot invent a metric, mark a gate passed, mutate a candidate, register a revision, or issue a promotion ticket.

The deterministic service validates that every referenced candidate belongs to the run, every evidence digest matches, the candidate has completed required folds, and the OOS/admission status is current. A provider failure or malformed response leaves the run and event history recoverable with an explicit failed stage. Cancel is a terminal domain event; resume starts from the last valid checkpoint/event cursor and never repeats an already committed OOS or promotion side effect.

## Durable contracts and persistence boundaries

### Run contract

`AlphaFactoryRun` is an immutable request envelope plus a guarded execution cursor:

```text
run_id, request_digest, principal, status,
research_input_snapshot_id, universe/data/feature snapshot references,
dsl_version, grammar_version, vocab_version, policy_version,
seed, cost_model, budget, created_at, started_at, finished_at,
terminal_reason, last_event_seq, checkpoint_ref
```

The run row is append-only for request identity and uses a narrow guarded cursor transition for status/progress. Status values should distinguish `queued`, `preflight_failed`, `running`, `cancel_requested`, `cancelled`, `completed`, `failed`, and `invalid`. A unique request/idempotency digest returns the existing active run rather than starting a duplicate.

### Candidate contract

`AlphaCandidate` is immutable and research-only:

```text
candidate_id, run_id, generation, ordinal,
canonical_expression, ast_signature, shape_signature,
dsl_version, grammar_version, vocab_version,
operation, seed, parent_candidate_ids,
complexity_json, status, invalid_reason,
selection_evaluation_id, oos_evaluation_id, created_at
```

The candidate payload contains data and references only. No Python source, pickle, estimator, broker intent, strategy callback or hidden executable state is persisted. Parent references and an operation/seed are enough to reproduce generation; evidence references are hashes/managed paths rather than unbounded raw frames.

### Event contract

`AlphaRunEvent` is the durable replay ledger, separate from `JobStore`:

```text
(run_id, seq) unique, event_id, event_type, stage,
entity_kind, entity_id, payload_json, payload_sha256,
recorded_at, producer_version
```

Events are INSERT-only and sequence-ordered. Payloads are bounded projections: `run_created`, `preflight_passed/failed`, `stage_started/completed/failed`, `candidate_generated/invalid/evaluated`, `fold_completed`, `oos_reserved/evaluated`, `review_completed`, `promotion_ticket_created`, `cancel_requested`, and terminal events. An event stream uses `Last-Event-ID`/sequence replay, so a reconnect does not depend on process memory. Event payloads never contain secrets, raw model prompts beyond the approved evidence policy, or arbitrary paths.

`pipeline_jobs.JobStore` remains the execution adapter: it supplies single-flight, progress, stale-job recovery and a job ID for worker dispatch. The Alpha run ID and event sequence remain the source of truth. A worker writes domain events transactionally with durable facts, then reports a bounded progress projection to JobStore; a JobStore JSON file disappearing must not erase a run, candidate or evidence.

### Checkpoint contract

A checkpoint is a resumable cursor, not a fact:

```text
(run_id, checkpoint_version, event_seq, stage,
 candidate_queue_ref, frontier_ref, rng_state_digest,
 committed_candidate_count, committed_evaluation_ids,
 checkpoint_payload_sha256, created_at)
```

Store compact queue/frontier references and hashes, not full market panels or arbitrary provider state. Write checkpoints atomically to a dedicated SQLite checkpoint file or managed artifact namespace, following `PersistentAnalysisGraph`/`PersistentAdvancedGraph`'s per-invocation saver pattern. On resume, verify run/request/vocabulary/data digests and reconstruct from immutable candidates/events; if the cursor is inconsistent, fail closed rather than rerun OOS or duplicate a terminal fact.

### Promotion Ticket contract

`ResearchPromotionTicket` is the explicit research-only handoff:

```text
ticket_id, candidate_id, selected_oos_evaluation_id,
admission_verdict_id, catalog_snapshot_id,
request_digest, evidence_refresh_digest, policy_version,
status (pending|approved|rejected|expired|consumed),
requested_by, reviewed_by, rationale, created_at, expires_at,
approved_at, registered_revision_id, idempotency_key
```

Creating a ticket requires completed selection evidence, exactly-once OOS evidence and an admission verdict. Approval must refresh current governed data and revalidate candidate/evidence digests before registering a formal immutable factor revision. Approval is atomic and idempotent; stale evidence expires the ticket. `consumed` means “registered research asset,” never “enabled strategy” or “executed order.” Registration may subsequently make the factor available as a signal source through the normal StrategyDef/backtest binding, but the ticket service must not call broker, monitor, portfolio, or strategy execution collaborators.

### Storage boundary table

| Data | Authoritative location | Retention/immutability | Do not do |
|---|---|---|---|
| Market panels and fold signal artifacts | Parquet/managed data root; DuckDB/Polars read path | Content-addressed manifest; artifacts are never silently overwritten | Do not embed full frames in SQLite or let Agent load raw files by path. |
| Factor definitions/revisions/admission/catalog | `operational.db` research tables via `ResearchRepository` | INSERT-only facts; FK-bound and trigger-protected where applicable | Do not treat a candidate as admitted merely because it scored well. |
| Alpha runs/candidates/events/tickets | New append-only research tables in `operational.db` | Immutable identity and evidence; guarded status cursor only | Do not use `advanced_*` strategy tables or JobStore files as the domain ledger. |
| Worker progress/stale recovery | `JobStore` JSON + in-process heavy-run lock | Operational/replaceable projection | Do not infer scientific completion or OOS truth from a progress bar. |
| Graph/factory restart cursor | Dedicated checkpoint SQLite/artifact namespace | Replaceable versioned checkpoints referencing domain facts | Do not let a graph checkpoint become authority to approve/publish. |
| API/UI state | Strict DTO projections, React Query/SSE cache | Re-fetchable projection | Do not accept browser-provided gate status, evidence, revision IDs for authority, or arbitrary paths. |

## Modified and new module map

| Module | Modification or addition | Boundary |
|---|---|---|
| `backend/app/research/factor_dsl.py` | Expose a deterministic vocabulary source and candidate AST validation metadata; preserve parser/compiler and deny-list behavior. | Formula syntax only; no search loop or persistence. |
| `backend/app/research/signal_chain.py` | Add a candidate-source binding that funnels stored revisions and transient validated candidates through the same governed compute implementation. | Single factor computation path. |
| `backend/app/research/alpha_factory/` **[NEW]** | `vocabulary`, `grammar`, `candidate lineage`, `search controller`, `cost/diversity policy`, and factor fold-scorer adapter. | Deterministic generation/evaluation orchestration; no strategy execution. |
| `backend/app/research/evaluation.py` / `admission.py` / `catalog.py` | Accept candidate identity and fold/OOS evidence references; keep existing metric/gate implementations as shared services. | Research evidence and policy decisions. |
| `backend/app/research/repository.py` | Add repositories for runs, events, candidates, checkpoints and promotion tickets; use parameterized short-lived SQLite connections like existing repositories. | Atomic insert/guarded transition/idempotency. |
| `backend/app/operational/migrations.py` | Append one or more versioned migrations for new tables, indexes, FKs, unique keys, immutable triggers and event sequence constraints. | Schema only; never migrate lake bytes in request handlers. |
| `backend/app/research/factor_agent/` **[NEW]** | Preflight, strict Stage 1/2 schemas, provider adapter, service orchestration and graph adapters. | Model output is untrusted proposal/review data. |
| `backend/app/analysis/graph.py` (pattern only) or a separate research graph | Reuse persistent saver/thread ownership pattern; do not change existing two-node stock analysis semantics. | Checkpoint/retry/cancel cursor only. |
| `backend/app/services/pipeline_jobs.py` | Add an adapter/callback contract if needed to report Alpha run progress and cancellation. | Execution cursor only; durable run events stay in research repository. |
| `backend/app/api/research.py` / `research_panels.py` | Keep existing manual DSL routes; add or mount typed Alpha Factory run/candidate/ticket routes and safe projections. | Server resolves scope, IDs, evidence and gate results. |
| `backend/app/api/walkforward_sse.py` | Reuse reconnect/progress conventions, but source Alpha events from durable sequence rather than only `_wf_jobs`. | UI timeline transport. |
| `backend/app/advanced/*` | No Alpha implementation. Reuse conceptual patterns from `EvolutionService` and `PersistentAdvancedGraph` only. | Strategy-specific advanced research remains isolated. |
| `frontend/src/pages/backtest/FactorBacktest.tsx` | Add deterministic factory launch/configuration, stage status and candidate results beside manual factor flow. | Existing manual factor workflow remains usable. |
| `frontend/src/pages/backtest/ResearchLibrary.tsx` | Add candidate/evidence comparison and Promotion Ticket status; distinguish candidate, admitted revision and registered research-only asset. | Read-only projections plus explicit reviewer action. |
| `frontend/src/pages/backtest/WalkForward.tsx` | Surface selection folds, reserved OOS, exact-once status and OOS evidence links for Alpha runs. | Never imply selection score is OOS. |
| `frontend/src/pages/Backtest.tsx`, `frontend/src/lib/api.ts`, `queryKeys.ts` | Add a tab/panel and typed API/query keys for Alpha runs, event streams and tickets. | Do not create a second backtest client or local authority. |

## Reusable patterns versus unsuitable/adversarial ideas

| Source/pattern | Reuse | Reject or adapt |
|---|---|---|
| AlphaMaster deterministic vocabulary/hash and constrained StackVM ideas (`../docs/aaa/alphamaster/DEEP-ANALYSIS.md`) | Stable versioned vocabulary, bounded grammar, shape/causality checks, elite/diversity/cost accounting, shared train/serve identity. | Do not copy source; do not introduce an alternate StackVM or RL/PyTorch dependency for the first milestone; use AthenaQuant's Factor DSL and SignalChain instead. AlphaMaster's same-dataset OOS is insufficient—use AthenaQuant's reserved exactly-once OOS. |
| PA_Agent two-stage flow (`../docs/aaa/pa-agent/DEEP-ANALYSIS.md`) | Preflight fail-closed, Stage 1 diagnosis → Stage 2 decision, strict JSON/schema/semantic validation, raw failure evidence, refresh-before-approval discipline. | Do not copy AGPL code; do not let LLM-produced diagnosis/decision override deterministic data, fold, admission or promotion gates. |
| `10-SYNTHESIS.md` pipeline and data-contract principles | Separate collect/freeze, analyze, evaluate, score, render stages; explicit contracts; replayable event/progress views; high-risk defaults constrained. | Avoid a sprawling autonomous multi-agent debate for a bounded factor research task. |
| `advanced/evolution.py` candidate/gate/promotion | Server-owned candidate creation, allowlisted operation, deterministic gate records, all-gates-required approval, reviewer principal, research-only registration. | `advanced_strategy_candidates`, strategy mutation operations, `strategy_policy`, arbitrary source sandbox and broker/monitor collaborators are not Alpha Factory boundaries. |
| `analysis/graph.py` and `advanced/workflow.py` checkpoint graphs | Per-invocation SQLite saver, server thread/job binding, compact typed state, graph as recovery cursor. | Do not make graph state the authoritative event/evidence ledger or accept browser-selected thread IDs/authority. |
| `JobStore` and walkforward SSE | Single-flight worker launch, status polling, stale recovery, reconnect UX and progress event naming. | JSON job files and in-memory SSE history cannot be the scientific run/candidate/OOS ledger. |

## API and UI integration points

### API surface

Keep existing manual factor routes unchanged: `/api/research/dsl/options`, `/dsl/validate`, `/factors`, `/factor-revisions/{revision_id}/evaluate`, `/experiments`, `/comparison`, and `/factor-catalog`. Add a typed, server-owned Alpha namespace, for example:

```text
POST /api/research/alpha/runs
GET  /api/research/alpha/runs/{run_id}
POST /api/research/alpha/runs/{run_id}/resume
POST /api/research/alpha/runs/{run_id}/cancel
GET  /api/research/alpha/runs/{run_id}/events       (Last-Event-ID replay/SSE)
GET  /api/research/alpha/runs/{run_id}/candidates
GET  /api/research/alpha/candidates/{candidate_id}
POST /api/research/alpha/candidates/compare
POST /api/research/alpha/candidates/{candidate_id}/promotion-ticket
GET  /api/research/alpha/promotion-tickets/{ticket_id}
POST /api/research/alpha/promotion-tickets/{ticket_id}/approve
POST /api/research/alpha/promotion-tickets/{ticket_id}/reject
```

Request models use `extra="forbid"`, bounded strings/lists, date and budget limits, and optional client idempotency keys. Evidence references, gate status, candidate parentage, selected revision IDs and reviewer identity are server-derived. API errors distinguish validation (`400`), missing authorized resource (`404`), state conflict/stale ticket (`409`), and unavailable provider/service (`503`) without exposing raw exceptions or filesystem paths.

The existing `research_panels.py` pattern—mapping repository rows to strict DTOs and exposing IC and RankIC separately—is the right projection model. Candidate DTOs should expose lineage, status, metric summaries, OOS/admission references, artifact checksums and safe diagnostics, but not raw panel bytes, prompts, secrets or worker paths.

### UI flow

1. **FactorBacktest / Alpha Factory panel:** choose bounded universe/date/horizon/budget/seed, review resolved vocabulary and constraints, launch or resume a run.
2. **Timeline:** show preflight, stage 1, candidate generation, fold progress, stage 2 and terminal status from replayable events. Make cancellation and reconnect states explicit.
3. **Candidate comparison:** show formula, lineage, complexity/cost, selection folds, exact OOS status, IC/RankIC, coverage, leakage and admission gates. Never color a selection score as OOS.
4. **ResearchLibrary:** separate transient candidates, retained experiment snapshots, admitted revisions and registered research-only assets. The existing explicit-retain model remains the default.
5. **Promotion Ticket dialog:** show refreshed evidence time/digest, policy version, gate reasons and a human confirmation action. Approval copy must state “registered research-only,” not “live” or “execute.”
6. **Strategy Backtest:** after registration, a factor can be selected as a normal signal source through the existing strategy/backtest binding. The factory cannot directly start strategy monitoring or execution.

## Dependency-ordered v3.0 phase graph

```text
Phase 45  Durable research run contracts
   |      schema, event ledger, checkpoint cursor, JobStore bridge, API skeleton
   v
Phase 46  Deterministic Alpha Factory core
   |      vocabulary, DSL grammar, candidate lineage, seed/mutation/crossover, cost/diversity
   v
Phase 47  Governed fold evaluation and promotion evidence
   |      factor scorer, shared SignalChain, measured calendar, reserved exactly-once OOS,
   |      admission/catalog integration
   v
Phase 48  FactorResearchAgent workflow
   |      preflight, Stage 1 diagnosis, factory invocation, Stage 2 review,
   |      strict JSON, failure/cancel/resume/checkpoint behavior
   v
Phase 49  Research-only Promotion Ticket and serving bridge
   |      refresh/revalidate, human approval, immutable FactorRevision/catalog registration,
   |      normal strategy signal binding with no execution authority
   v
Phase 50  Research workbench and replay UX
          FactorBacktest/ResearchLibrary/WalkForward integration, SSE timeline,
          candidate/OOS/ticket projections, end-to-end replay and boundary hardening
```

### Phase ordering rationale and research flags

| Phase | Why it must occur here | Main deliverable | Deeper research flag |
|---|---|---|---|
| 45 | Every later capability needs one run identity, event sequence, idempotency and restart model. | Durable contracts and migration foundation. | **Yes:** decide event/checkpoint transaction boundaries and checkpoint file lifecycle. |
| 46 | Candidate generation must be deterministic before scores or Agent output can be trusted. | Reproducible bounded factory and lineage. | **Yes:** calibrate grammar size, mutation/crossover legality, complexity cost and CPU budget against A-share panels. |
| 47 | Search selection must be unable to contaminate OOS before Agent review or promotion exists. | Fold adapter, candidate evidence, exact-once OOS and shared admission/catalog path. | **Yes:** factor-specific scorer metrics and whether to generalize `wf_folds` or add Alpha fold rows. |
| 48 | The Agent should orchestrate a proven factory, not define its own evaluator or gate semantics. | Recoverable two-stage structured workflow. | **Yes:** provider/schema retry policy and A-share diagnosis taxonomy; no new LLM framework is required by default. |
| 49 | Registration requires complete immutable evidence and explicit human authority. | Refresh-bound research-only Promotion Ticket. | **Yes:** candidate-to-DSL revision mapping and catalog/strategy signal binding compatibility. |
| 50 | UI should project stable contracts rather than drive design decisions. | Replayable workbench and user-visible boundaries. | Standard patterns; validate SSE reconnect, stale state and OOS/ticket labels with focused browser checks. |

### Explicit non-goals

- No automatic broker execution, paper/live order path, monitoring activation or portfolio mutation from Alpha Factory or FactorResearchAgent.
- No arbitrary Python, uploaded strategy source, pickle/model checkpoint execution or raw-data path authority.
- No AGPL source import from PA_Agent or other upstream projects; only documented patterns are absorbed.
- No second factor computation path, hidden strategy-specific factor registry, or silent OOS reuse.

## Sources and evidence

### Current AthenaQuant files/symbols

- `backend/app/research/factor_dsl.py`: `parse_factor`, `compile_ast`, `FactorFeatures`, `ParsedFactor`, DSL allow/deny and partition contracts.
- `backend/app/research/factor_registry.py`: `FactorRevision`, `FactorRegistry`, immutable revision and similarity seams.
- `backend/app/research/signal_chain.py`: `SignalChainConfig`, `FactorSignalFrame`, `FactorSignalChain.compute` shared computation path.
- `backend/app/research/evaluation.py`: `FactorEvaluationService.evaluate` and retention-ready evidence package.
- `backend/app/research/admission.py`: `run_admission` deterministic gates and catalog/evidence integration.
- `backend/app/research/catalog.py` and `repository.py`: immutable snapshots, comparison and SQLite persistence.
- `backend/app/backtest/walkforward.py`: `run_walk_forward`, `fold_scorer`, `evaluate_best_params`, reserved OOS exact-once semantics.
- `backend/app/services/pipeline_jobs.py`: `JobStore` single-flight/progress/stale recovery boundaries.
- `backend/app/analysis/service.py` and `analysis/graph.py`: freeze → typed graph → validate → persist and SQLite checkpoint pattern.
- `backend/app/advanced/evolution.py` and `advanced/workflow.py`: deterministic gates, reviewer promotion and checkpoint cursor patterns (strategy domain only).
- `backend/app/operational/migrations.py`: research tables (lines 148–230), append-only universe/admission/model records (1512–1577), and walk-forward records (1712–1808).
- `backend/app/api/research.py`, `research_panels.py`, `research_backtest.py`, `walkforward_sse.py`: current API and stream seams.
- `frontend/src/pages/Backtest.tsx`, `backtest/FactorBacktest.tsx`, `backtest/ResearchLibrary.tsx`, `backtest/WalkForward.tsx`, `frontend/src/lib/api.ts`, `queryKeys.ts`: existing workbench and typed client integration points.
- `.planning/PROJECT.md:11-20`: v3.0 goal, target features and platform boundary.
- `docs/v3-roadmap.md`: prior strategic AlphaMaster/PA_Agent synthesis; this artifact supersedes its strategy-specific/RL-first assumptions for the current deterministic-first milestone.

### Local upstream analysis (patterns only; no source copied)

- `../docs/aaa/alphamaster/DEEP-ANALYSIS.md`: deterministic vocabulary/versioning, constrained formula execution, fold scoring and train/serve identity; also documents its inadequate same-dataset OOS boundary.
- `../docs/aaa/pa-agent/DEEP-ANALYSIS.md`: preflight, two-stage JSON analysis, immutable process evidence and refresh-before-approval ticket model; AGPL license boundary explicitly noted.
- `../docs/aaa/10-SYNTHESIS.md`: pipeline/data-contract/checkpoint/projection principles and high-risk default constraints.
