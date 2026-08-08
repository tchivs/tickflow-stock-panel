# Roadmap: AthenaQuant v3.0

**Milestone:** v3.0 可回放 Alpha Factory 与 FactorResearchAgent  
**Goal:** Deliver a replayable, deterministic, research-only factor discovery workflow over the existing governed Factor DSL, `FactorSignalChain`, measured-calendar walk-forward, admission, catalog, and human-review boundaries.  
**Phase numbering:** Continues from completed v2.5 Phase 44 (`phase_naming: sequential`).  
**Granularity:** Standard (six dependency-ordered delivery boundaries).

## Locked Boundaries

- Candidate formulas use the existing restricted Factor DSL and canonical AST; no arbitrary Python, imports, `eval`, or second expression engine.
- Every factor value is computed through the single governed `FactorSignalChain`; search does not create a StackVM or direct-Polars evaluator.
- The default factory is deterministic seeded grammar/evolution on the existing Python 3.11+/FastAPI/Pydantic/SQLite/Parquet/Polars/DuckDB/LangGraph/SSE/React Query stack; no new base runtime dependency, PyTorch, RL, GPU, distributed queue, or WebSocket requirement.
- Run inputs, data/universe, DSL/grammar/vocabulary, policy, costs, seed, fold geometry, provider metadata, and provenance are frozen before generation or provider calls.
- Search and Agent review cannot access reserved walk-forward selection OOS; the selected candidate is evaluated there exactly once and it is never called a blind final holdout.
- Agent output is untrusted proposal/review data. Deterministic server code owns parsing, metrics, gates, persistence, and authority; promotion requires explicit human review and evidence refresh.
- Promotion is research-only. No broker, order, portfolio, position, monitor, live execution, or automatic promotion authority is added. AlphaMaster and PA_Agent provide patterns only; no AGPL source, prompts, domain rules, or derived implementation is copied.

## Phases

- [x] **Phase 45: Durable Governed Run Contract** - Freeze immutable run/input snapshots and establish the append-only candidate, event, checkpoint, lifecycle, and idempotency foundation. (completed 2026-08-08)
- [ ] **Phase 46: Deterministic Alpha Factory Core** - Generate only restricted canonical candidates with versioned vocabulary, lineage, bounded budgets, and stable replay order.
- [ ] **Phase 47: Governed Scoring, Admission & Selection OOS** - Score candidates through the shared chain, retain evidence and gate trails, stress cost/robustness, and consume reserved selection OOS exactly once.
- [ ] **Phase 48: FactorResearchAgent Two-Stage Workflow** - Add deterministic preflight, strict Stage 1/Stage 2 contracts, provider failure traces, bounded retry, cancellation, and checkpointed orchestration.
- [ ] **Phase 49: Research-Only Promotion Ticket** - Refresh evidence at approval and hand an explicitly reviewed candidate to an immutable `FactorRevision`/catalog record without execution authority.
- [ ] **Phase 50: Replay Workbench & Release Hardening** - Project durable progress and evidence through SSE/polling, expose lineage/comparison/stress/degradation views, and harden release/license/execution boundaries.

## Phase Details

### Phase 45: Durable Governed Run Contract

**Goal**: A researcher can create and replay an immutable, provenance-complete Alpha run whose lifecycle and every attempted outcome remain durable after retries, cancellation, or process restart.

**Depends on**: Phase 44 (completed); no v3.0 phase dependency.

**Requirements**: AF-REQ-01, AF-REQ-04, AF-REQ-10, AF-REQ-16

**Success Criteria** (what must be TRUE):

1. Before any generation or provider call, the researcher can inspect a server-frozen run specification and `ResearchInputSnapshot` containing DSL/grammar/vocabulary/policy versions, seed, expression and candidate limits, objective/cost policy, universe, measured dates, fold geometry, and code/data/artifact manifest; editing inputs creates a new run rather than mutating the old one.
2. The run retains every candidate attempt and terminal reason—including invalid, duplicate, low-coverage, failed, rejected, admitted, cancelled, and budget-exhausted outcomes—with immutable IDs, bounded diagnostics, evidence references, and a durable parent/child ledger rather than only a champion.
3. Duplicate start/retry/cancel requests are idempotent and lifecycle states (`queued`, `running`, `cancel_requested`, `cancelled`, `completed`, `failed`, and invalid/preflight failure) remain consistent across process restart; a retry resumes a recorded cursor or creates a linked immutable run without overwriting prior facts.
4. Durable events have a monotonic per-run sequence and idempotency key, and checkpoints are bounded recovery cursors referencing committed facts and checksums; a crash or inconsistent cursor fails closed instead of duplicating committed work or an OOS/promotion side effect.

**Research flag**: **Yes** — settle SQLite transaction boundaries between run/candidate/event/checkpoint facts, sequence allocation and idempotency conflicts, JobStore bridging, and checkpoint file/artifact lifecycle before implementation.

**Explicit non-goals**: No factory grammar/evolution search, fold scoring, Agent provider call, promotion, UI workbench, broker/order path, or strategy-specific `advanced_*` tables in this phase.

**Plans:** 4/4 plans complete

Plans:
**Wave 1**

- [x] 45-01-PLAN.md — create-to-replay durable tracer and frozen manifest contract

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 45-02-PLAN.md — append-only candidate/event ledger and fail-closed checkpoint recovery

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 45-03-PLAN.md — guarded lifecycle, idempotent retry/cancel, restart, and worker adapter

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 45-04-PLAN.md — typed API/history seam and research-only no-execution guard

### Phase 46: Deterministic Alpha Factory Core

**Goal**: Given a frozen run, the system emits a bounded, canonical, fully accounted candidate population whose expressions, IDs, lineage, and ordering are reproducible independent of worker timing.

**Depends on**: Phase 45

**Requirements**: AF-REQ-02, AF-REQ-03, AF-REQ-19, AF-REQ-23

**Success Criteria** (what must be TRUE):

1. A researcher can inspect a stable, versioned vocabulary/grammar fingerprint covering fields, operators, functions, arity, partition semantics, windows, and complexity limits; unsupported or semantically incompatible versions fail closed rather than reinterpreting stored tokens.
2. Replaying the same frozen snapshot, seed, grammar, and budget produces identical canonical expressions, candidate IDs/digests, parent/mutation/crossover metadata, candidate order, and checksums with one or many workers and with delayed worker completion.
3. Every generated expression is parsed and semantically validated before evaluation; denied fields, unknown operators/functions, invalid arity/partition semantics, excessive depth/window, non-finite literals, and malformed expressions become explicit invalid records with diagnostics and consume the declared trial budget.
4. Candidate, lineage, diversity, complexity, wall-clock, memory, artifact, and worker budgets are enforced server-side; objective score is shown beside structural/field/operator overlap and factor-output/IC-series redundancy without silently merging similar candidates or allowing parallelism to change the winner.

**Research flag**: **Yes** — calibrate the narrow A-share grammar, legal mutation/crossover operations, complexity/diversity cost model, candidate population, and CPU/memory/artifact budgets against governed panels. No ML/RL search is required.

**Explicit non-goals**: No direct factor computation, search-specific evaluator, fold/OOS scoring, Agent autonomy, provider calls, automatic admission/promotion, PyTorch/RL/GPU/distributed queue, arbitrary Python, or broker/execution integration.

**Plans**: TBD

### Phase 47: Governed Scoring, Admission & Selection OOS

**Goal**: Every valid candidate receives reproducible governed evidence and fixed admission decisions, while selection remains temporally honest and the reserved selection OOS is evaluated exactly once only after deterministic selection.

**Depends on**: Phase 46

**Requirements**: AF-REQ-05, AF-REQ-06, AF-REQ-07, AF-REQ-08, AF-REQ-09

**Success Criteria** (what must be TRUE):

1. Factory scoring, Agent-requested evaluation seam, admission, composite use, walk-forward folds, and later as-of serving all compute factor values through the existing `FactorSignalChain`, exposing panel, PIT-universe, source-field, warmup, missing-data, and signal fingerprints.
2. A run uses measured A-share trading dates and point-in-time membership per fold; missing, suspended, non-finite, warmup, stale, and source-quality states follow the declared policy, while current-constituent/full-lake substitution fails closed.
3. For every evaluated candidate, the researcher can inspect immutable resolved configuration and evidence including per-date IC/RankIC, summaries, ICIR, positive rate, coverage, monthly robustness, group/long-short evidence, fees/slippage, cost/turnover diagnostics, artifacts, and a terminal failure reason when evaluation fails; failure is never converted to a zero score.
4. The existing ordered deterministic admission policy exposes every observed value, threshold, pass/fail result, and reason; factory/Agent inputs cannot edit thresholds, reorder gates, or turn rejection into admission, and all rejected/failed verdicts remain linked to the candidate ledger.
5. Search and Agent review receive only selection-fold evidence; after selection, the reserved fold receives one explicit `selection_oos` evaluation with an exactly-once durable binding. Reconnect/retry returns the existing result, and the UI/data model never labels it a blind final validation.

**Research flag**: **Yes** — decide whether Alpha fold facts generalize existing `wf_folds` or require typed Alpha rows, and define factor-specific cost/robustness evidence without duplicating or weakening existing gates and exactly-once OOS constraints.

**Explicit non-goals**: No Stage 1/Stage 2 provider orchestration, human promotion, live/paper execution, separate signal engine, threshold tuning, or separate final-blind holdout contract.

**Plans**: TBD

### Phase 48: FactorResearchAgent Two-Stage Workflow

**Goal**: A FactorResearchAgent can safely orchestrate the proven factory and evidence path: deterministic preflight, strict bounded proposals/reviews, and durable recoverable failure traces without gaining scientific or operational authority.

**Depends on**: Phase 47

**Requirements**: AF-REQ-11, AF-REQ-12, AF-REQ-13, AF-REQ-14, AF-REQ-21, AF-REQ-26

**Success Criteria** (what must be TRUE):

1. Before a model call, deterministic preflight checks data availability/freshness and quality, measured calendar, PIT universe scope, required fields/sample length, DSL/grammar compatibility, budgets, provider availability, and policy mode; failure returns machine-readable reasons and makes zero provider calls.
2. Stage 1 accepts a bounded thesis and permitted grammar/DSL options and returns versioned, strict schema-validated JSON with hypotheses/expressions, explanation, assumptions, scope, uncertainty, and evidence references; the server parser/canonicalizer confirms expressions and the result remains transient proposal data.
3. Stage 2 receives only frozen run inputs and server-produced candidate/evaluation/gate evidence and returns schema-validated evidence-linked caveats and a bounded recommendation; it cannot change expressions, metrics, thresholds, OOS state, or admission status, and each challenge links to valid candidate/evaluation/gate/artifact IDs.
4. Every Stage 1/2 attempt records template/schema/provider/model provenance, request scope, bounded raw-response checksum or approved response, parsed output, validation errors, retries, cancellation, latency, and partial/terminal failure state; malformed, refused, timed-out, unavailable, or rate-limited providers never create a fabricated fallback draft.
5. Cancellation, retry, and restart resume from a server-owned checkpoint/event cursor without repeating committed candidate/OOS/promotion side effects. An explicitly declared offline fixture can produce a known full trace only when no provider is configured, is labeled non-production, and is never an implicit production fallback.

**Research flag**: **Yes** — settle provider failure/retry taxonomy, response retention/hash policy, A-share diagnosis fields, strict schema/semantic bounds, and stage-to-event/checkpoint transaction boundaries. Do not add another Agent framework.

**Explicit non-goals**: No model-selected tools/paths/IDs, model-owned metrics or gates, autonomous/unbounded loops, new evaluator, direct registry mutation, automatic promotion, broker/order/portfolio/monitor access, or silent provider fallback.

**Plans**: TBD

### Phase 49: Research-Only Promotion Ticket

**Goal**: A researcher can explicitly approve a complete, current, evidence-bound candidate and register only a new immutable research `FactorRevision`/catalog handoff; stale or modified approvals fail closed.

**Depends on**: Phase 48 (and the Phase 47 evidence/OOS contracts)

**Requirements**: AF-REQ-15, AF-REQ-17

**Success Criteria** (what must be TRUE):

1. The reviewer can compare a proposal's canonical expression, assumptions, evidence, gate trail, OOS status, and provenance, then create a Promotion Ticket bound to candidate/AST, run and snapshot digests, admission/OOS evidence, catalog state, policy/vocabulary versions, reviewer identity, and an expiry/idempotency key.
2. Approval refreshes governed data and required evidence/gates; changed candidate expression, explanation/provenance, policy, vocabulary, membership, or snapshot expires/conflicts the ticket, and concurrent approval/consume requests register at most one revision.
3. Only an explicitly reviewed and exact-bound ticket can create a new immutable `FactorRevision` and catalog entry with preserved candidate lineage and evidence references; unreviewed or altered Agent output is absent from the formal catalog and prior runs remain unchanged.
4. The complete action surface is visibly research-only—inspect, compare, retain evidence, or register a research asset—and the promotion service has no broker, order, position, portfolio, monitor, live-execution, or automatic-promotion collaborator or route.

**Research flag**: **Yes** — verify transient canonical-candidate to `FactorRevision` mapping, catalog snapshot identity, normal signal/backtest binding compatibility, stale-refresh conflict semantics, and atomic reviewer handoff.

**Explicit non-goals**: No automatic or model-authorized promotion, strategy-specific `advanced_*` candidate tables, broker/order submission, portfolio mutation, monitor activation, live/paper execution, or execution permit derived from admission/OOS.

**Plans**: TBD

### Phase 50: Replay Workbench & Release Hardening

**Goal**: Researchers can inspect, compare, replay, and understand Alpha/Agent runs through durable progress and evidence projections, while release checks make degraded data, temporal labels, licensing, dependencies, and research-only boundaries explicit.

**Depends on**: Phases 45–49

**Requirements**: AF-REQ-18, AF-REQ-20, AF-REQ-22, AF-REQ-24, AF-REQ-25

**Success Criteria** (what must be TRUE):

1. The workbench reconnects to a run using durable monotonic SSE `Last-Event-ID` replay or bounded polling and shows queued/running/terminal/cancelled progress without missing, duplicating, or inventing events; reconnect/restart never becomes UI authority.
2. A researcher can inspect parent-to-child mutation/crossover lineage, canonical expression diffs, seed/step and branch termination reasons, replay one branch under the same frozen inputs, clone a completed run while changing only declared dimensions, and see field-level differences plus parent/child hashes.
3. Candidate families and retained experiment snapshots can be compared side by side with configuration, evidence, provenance, gate status, artifacts, diversity/redundancy outcomes, and no opaque hidden winner; a candidate family can display the exact rebalance, fee/slippage, calendar-regime, coverage, and symbol-subset stress matrix without rewriting primary admission thresholds.
4. The UI visibly distinguishes data date, source/provider, cache/degradation state, missing fields, membership coverage, exploratory evidence, selection-fold evidence, `selection_oos`, and unavailable final-blind evidence; stale, partial, blocked, or fixture results cannot look like clean production evidence.
5. Release verification finds no AGPL-derived source, prohibited new base runtime dependency, arbitrary code path, or broker/execution import/call in Alpha/Agent/promotion surfaces; documented smoke evidence proves the shipped workbench exposes research-only actions and preserves the no-execution boundary.

**Research flag**: **No dedicated research phase** — use standard React Query/native `EventSource` and existing API patterns; focused implementation verification must cover reconnect cursors, stale/degraded projections, OOS/ticket labels, restart replay, and license/import/execution scans.

**Explicit non-goals**: No WebSocket or external event broker, second client/transport, hidden browser authority, final-blind holdout, AGPL source copying, PyTorch/RL/GPU/distributed runtime, automatic live/paper execution, broker integration, or changes to `frontend/src/pages/Watchlist.tsx`.

**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 45. Durable Governed Run Contract | 4/4 | Complete    | 2026-08-08 |
| 46. Deterministic Alpha Factory Core | 0/TBD | Not started | - |
| 47. Governed Scoring, Admission & Selection OOS | 0/TBD | Not started | - |
| 48. FactorResearchAgent Two-Stage Workflow | 0/TBD | Not started | - |
| 49. Research-Only Promotion Ticket | 0/TBD | Not started | - |
| 50. Replay Workbench & Release Hardening | 0/TBD | Not started | - |

**Execution order:** 45 → 46 → 47 → 48 → 49 → 50. Each phase consumes durable, server-owned contracts from its predecessors; no phase grants execution authority.

---
*Last updated: 2026-08-08 — v3.0 roadmap created; 26/26 requirements mapped.*
