# Project Research Summary

**Project:** AthenaQuant v3.0 — Replayable Alpha Factory + FactorResearchAgent  
**Domain:** Governed A-share quantitative factor discovery, evidence evaluation, and research-only AI orchestration  
**Researched:** 2026-08-08  
**Confidence:** HIGH for current repository seams and safety contracts; MEDIUM for ecosystem methodology and target implementation details

## Executive Summary

AthenaQuant v3.0 should extend the existing governed factor workflow into a replayable Alpha Factory and a two-stage FactorResearchAgent, not introduce a second research platform. Experts would freeze a point-in-time data and policy manifest, generate only bounded expressions in a versioned grammar, evaluate every candidate through one semantic signal path, retain the complete trial/evidence ledger, and admit or promote only through deterministic gates plus explicit human review. The Agent should be an untrusted research orchestrator: deterministic preflight and code own data scope, DSL validity, candidate generation, metrics, OOS reservation, gates, persistence, and authority.

The recommended implementation reuses the current Python 3.11+, FastAPI, Pydantic v2, SQLite, Parquet/PyArrow, Polars/DuckDB, LangGraph SQLite checkpoint, SSE, and React Query stack. No new base runtime dependency is needed: begin with a seeded standard-library grammar/evolution search and existing `factor_dsl`, `FactorSignalChain`, evaluation, admission, catalog, repository, and walk-forward seams. Durable SQLite rows are the authoritative run/candidate/event facts; checkpoints are replaceable recovery cursors, and an in-memory SSE hub only wakes subscribers. The work remains research-only: a Promotion Ticket can register an immutable research asset after evidence refresh and human approval, but nothing can place orders or activate live execution.

The dominant risks are multiple-comparison/OOS contamination, train–serve skew, vocabulary/data/provenance drift, nondeterministic scheduling, incomplete replay after interruption, and accidental model or broker authority. Mitigate them by freezing manifests before generation or model calls, counting invalid/rejected/retried trials, structurally excluding reserved OOS until one explicit evaluation, versioning grammar/DSL semantics, sorting deterministic results independent of worker timing, persisting append-only events with idempotency, and making strict schemas plus server-owned identity fail closed. Absorb design patterns from AlphaMaster and PA_Agent independently; do not copy their source, domain assumptions, execution paths, or dependencies.

## Key Findings

### Recommended Stack

Use the current runtime unchanged at the dependency level. The lockfile is the reproducible baseline; broad `pyproject.toml` lower bounds are not an upgrade policy.

**Core technologies:**
- **Python 3.11+ standard library** (`random.Random`, `hashlib`, `json`, dataclasses): deterministic seeded grammar, candidate identity, canonical digests, bounded search without an ML or distributed-runtime dependency.
- **Existing restricted Factor DSL** (`factor_dsl.py`): canonical AST, parser/compiler, deny-list, arity/partition semantics, and `DSL_VERSION`; generated candidates must be canonical DSL, never Python source or `eval`.
- **`FactorSignalChain` + Polars/DuckDB/Parquet/PyArrow**: one governed factor computation path over frozen panels and PIT membership, with existing evidence/artifact boundaries; no search-specific evaluator.
- **FastAPI + Pydantic v2**: strict, bounded request/event/Stage 1/Stage 2 DTOs with `ConfigDict(extra="forbid")`, strict fields where required, and `model_validate_json()` at the provider boundary.
- **Operational SQLite + `ResearchRepository` + migrations**: append-only run, candidate, event, evidence, and Promotion Ticket facts with transactional idempotency and immutable triggers; large artifacts remain in the managed data lake.
- **LangGraph 1.2.9 + `langgraph-checkpoint-sqlite` 3.1.0**: resumable graph cursor only, bound to server-owned job/thread identity; never the authoritative audit ledger.
- **SSE (`sse-starlette`), native `EventSource`, React Query**: durable sequence replay using `Last-Event-ID` plus bounded GET polling; no WebSocket, broker, or SSE client package.

Important locked versions observed in the current lock include FastAPI 0.136.1, Pydantic 2.13.4, Polars 1.40.1, DuckDB 1.5.3, PyArrow 24.0.0, `sse-starlette` 3.4.4, LangGraph 1.2.9, and checkpoint-sqlite 3.1.0. Keep the LangGraph/checkpointer pair together and treat SQLite one-writer concurrency, WAL deployment constraints, and SSE/Starlette behavior as implementation concerns.

**Explicit stack decisions:** do not add PyTorch/JAX/TensorFlow/RL/GPU runtimes, Optuna/Ray/Dask, Celery/RQ/Redis/Kafka/NATS, `jsonschema`/instructor/pydantic-ai/provider agent frameworks, WebSocket clients, pandas-first search, a second expression engine, or `sqlite-vec` as a design requirement. A future optional dependency requires a separately justified capability and is outside v3.0.

### Expected Features

**Must have (table stakes):**
- **Immutable run specification and manifest:** freeze DSL/grammar/vocabulary/policy versions, seed, bounded grammar, budget, universe, measured date/fold geometry, costs, code/data/artifact provenance before generation or provider calls.
- **Deterministic restricted search:** same frozen inputs and seed reproduce canonical candidate expressions, IDs/digests, order, statuses, and artifacts; use bounded enumeration/mutation/crossover and stable tie-breaking.
- **Complete candidate ledger and lineage:** retain generated, invalid, duplicate, failed, rejected, low-coverage, and admitted candidates with parent/mutation metadata and reasons; never retain only top-K.
- **Single governed signal/evaluation path:** all factory, Agent-requested, admission, walk-forward, composite, and as-of factor values use `FactorSignalChain.compute()` and existing evaluation evidence.
- **PIT A-share semantics and honest temporal separation:** measured trading calendar, daily PIT membership, warmup/missing-data policy, search-fold-only scoring, reserved OOS excluded from generation and Agent context, and exactly-once OOS evaluation.
- **Deterministic admission and evidence:** preserve ordered no-lookahead, coverage, leakage, similarity, train IC, and validation IC gates with visible observed values/reasons; failures are terminal evidence, not zero scores.
- **Two-stage Agent with deterministic preflight:** Stage 0 checks data/provider/policy/DSL/calendar/budget and makes zero model calls on failure; Stage 1 emits parser-confirmed structured hypothesis/proposal; Stage 2 receives only frozen evidence and emits evidence-linked bounded review.
- **Complete Agent trace and strict failure handling:** persist schema/template/provider/model provenance, response hash/size, validation errors, retries, latency, cancellation, and partial failures; no fabricated fallback draft.
- **Explicit human research promotion:** compare and review, refresh evidence, bind approval to immutable candidate/evidence/policy digests, then register a new immutable `FactorRevision`; unreviewed output cannot enter the catalog.
- **Lifecycle and replay transport:** queued/running/completed/failed/cancelled states, cooperative cancellation, checkpointed resume/new linked run, append-only monotonic events, SSE replay and polling fallback.
- **Research-only boundary:** inspect, compare, retain, or register research assets only; no broker, order, position, portfolio, monitor, or live execution authority.

**Should have (competitive, after table stakes are durable):**
- Lineage-aware replay UI with expression diffs and branch replay.
- Diversity/redundancy frontier using structural similarity and factor-output/IC-series correlation without changing gate policy at runtime.
- A-share robustness/cost stress board across rebalance, fee/slippage, regimes, coverage, and symbol subsets, with trials recorded.
- Evidence-linked Stage 2 challenges and bounded follow-up run requests.
- Immutable experiment templates/cloning with field-level diffs, candidate-family comparison, and visible data-quality/degradation/OOS labels.
- Budget-aware parallel throughput where workers change speed only, never candidate order or winner; offline Agent fixture mode only when explicitly declared and labeled.

**Defer (v2+ or separately approved):**
- Neural/RL/AlphaGPT policy search, GPU infrastructure, and distributed optimization.
- Broad grammar expansion before a narrow grammar is replayable and statistically accounted for.
- Multi-agent debate, self-modifying prompts, autonomous/unbounded research loops, or model-selected tools.
- Any live or paper execution integration, automatic promotion, broker/monitor activation, or portfolio mutation.
- A separate final-blind holdout unless a later product requirement funds its distinct contract; selection OOS is never relabeled as blind final OOS.

**Absorb from AlphaMaster and PA_Agent, but do not copy:**
- From **AlphaMaster**, absorb the *ideas*: stable ordered vocabulary/fingerprint, bounded AST/grammar and formula-length/complexity limits, mutation/crossover/lineage, diversity/cost accounting, checkpoints, and one execution identity. Reimplement them over AthenaQuant's Factor DSL and `FactorSignalChain`. Do **not** copy a StackVM, RL/REINFORCE/PyTorch search loop, reward assumptions, same-dataset OOS interpretation, or incomplete provenance; AlphaMaster is an analysis reference, not a dependency or source import.
- From **PA_Agent**, absorb the *workflow patterns*: fail-closed preflight, diagnosis-before-decision two stages, strict structured JSON plus semantic validation, durable partial-failure records, cancellation/resume, and refresh-before-approval evidence binding. Do **not** copy AGPL-3.0-or-later code, prompts/assets, crypto/Price Action rules, paper-execution assumptions, or any execution authority into the MIT backend. Implement equivalent behavior against A-share contracts independently.

### Architecture Approach

Keep the existing data lake, research domain, backtest fold geometry, and UI projection boundaries. Add Alpha Factory and FactorResearchAgent as research subdomains connected through durable server-owned contracts rather than modifying the strategy-specific `advanced_*` domain or turning the existing stock-analysis graph into an autonomous search graph.

**Major components and responsibilities:**
1. **Frozen `ResearchInputSnapshot` / `AlphaFactoryRun`:** resolve PIT universe, measured calendar, panel/data hashes, DSL/grammar/vocabulary/policy, costs, seed, budget, code/provider metadata, and request digest before work; fail closed if incomplete.
2. **Deterministic Alpha Factory:** ordered vocabulary and bounded legal AST grammar; seeded mutation/crossover/enumeration, lineage, complexity/diversity cost, deduplication, canonical candidate IDs, and deterministic candidate order independent of completion timing.
3. **Shared signal/evaluation adapter:** bind transient validated candidates or stored revisions into the same `FactorSignalChain` private compute path, then reuse walk-forward fold scorer, `FactorEvaluationService`, `run_admission`, and `ExperimentCatalog`; never add StackVM/direct-Polars/search-only semantics.
4. **Durable research repository and migrations:** append-only run/candidate/evidence/event/checkpoint/ticket tables with FK/unique constraints, short transactions, immutable triggers, and event idempotency. `JobStore` remains only worker progress/single-flight/stale recovery.
5. **FactorResearchGraph and strict Agent service:** typed `preflight → stage1_diagnosis → factory_search → stage2_review → record_outcome`; frozen evidence in, strict Pydantic JSON out, semantic reference checks, bounded retries, partial failures, and server-owned authority. LangGraph SQLite is only the recovery cursor.
6. **Research Promotion Ticket:** bind candidate, canonical AST, selection/OOS evidence, admission verdict, catalog snapshot, policy, and refreshed evidence digest; atomically approve/expire/consume to register a research-only immutable revision. It cannot call execution collaborators.
7. **API/UI projection and replay:** typed Alpha routes, candidate/ticket projections, durable `Last-Event-ID` SSE plus GET polling, native EventSource/React Query workbench, lineage/evidence/OOS/degradation labels, and explicit research-only copy.

**Data flow:**

```text
Intent + bounded scope
  -> server resolves/freeze snapshot + preflight
  -> Stage 1 structured diagnosis (optional Agent proposal)
  -> deterministic DSL grammar generates canonical candidates + full ledger
  -> PIT/measured-calendar folds -> FactorSignalChain -> evaluation evidence
  -> fixed admission gates (search folds only)
  -> deterministic selection -> reserved selection-OOS exactly once
  -> Stage 2 evidence-linked review
  -> catalog/compare -> refreshed Promotion Ticket -> explicit research-only revision
```

Durable domain facts are authoritative in SQLite; Parquet/Arrow artifacts are content-addressed by manifest/checksum; checkpoints contain compact cursor/frontier references and hashes; UI/SSE state is re-fetchable projection. Event rows are committed before publish, and reconnect replays from persisted sequence before live wakeups.

## Critical Pitfalls and Guardrails

1. **P0 — Multiple comparison and OOS contamination:** count every valid, invalid, failed, rejected, retried candidate and provider/prompt attempt in the trial ledger; freeze non-OOS search folds before generation; keep final OOS inaccessible to Agent/search and enforce one successful OOS evidence row.
2. **P0 — Train–serve skew:** all computations go through `FactorSignalChain`; bind revision/DSL, PIT membership, source fields, warmup, horizon, rebalance, costs, panel and universe fingerprints in the manifest; use golden-panel comparisons across factory, admission, walk-forward, catalog and as-of semantics.
3. **P0 — DSL/vocabulary drift:** hash ordered field/operator/function/arity/partition vocabulary; version semantic changes; reject unsupported versions rather than reinterpreting token IDs or silently reordering operators.
4. **P0 — Stale or incomplete provenance/data quality:** freeze content-level partition/data/membership/provider hashes and as-of bounds; represent `ready`, `empty`, `stale`, `blocked`, `schema_error`, and `partial` explicitly; never substitute current constituents/full lake/latest data.
5. **P0 — Accidental execution authority:** keep broker/order imports and calls out of Alpha/Agent services; enforce research-only task types, server-owned scope, static import/call guards, runtime collaborator mocks, and registration wording that never says execute/live.
6. **P1 — Candidate explosion and nondeterministic parallelism:** cap AST size/depth/windows, candidates, lineage, retries, provider calls, time/memory/artifacts; derive per-candidate deterministic randomness and merge immutable results by canonical total order, not worker completion.
7. **P1 — Replay/cancellation defects:** append run/event/candidate/stage/cancellation/terminal facts with monotonic sequence and idempotency; cooperative cancellation at stage/candidate boundaries; resume skips committed work and never turns cancelled into done.
8. **P1 — Partial provider failure and prompt/schema injection:** model output is optional untrusted evidence; strict bounded schemas with `extra="forbid"`, evidence-reference subset checks, separate instructions/data, bounded retries, raw-response hash and explicit failed/partial status; no model-selected tools, paths, IDs, metrics, gates, or authority.
9. **P1 — Model metric override and stale promotion:** recompute all metrics/gates in server code; model claims are annotations only. Approval refreshes data/evidence and atomically conflicts/expairs when candidate, policy, vocabulary, or snapshot changes.
10. **P1/P2 — License contamination and identity drift:** implement patterns independently, keep an attribution/license inventory, never copy PA_Agent/AlphaMaster source or AGPL-derived code, and identify candidates by immutable run/AST/vocabulary/evidence identity rather than display name or model score.

## Implications for Roadmap

The roadmap should continue from Phase 45 with six dependency-ordered phases. The first three build a trustworthy deterministic factory before Agent orchestration; the last three connect review, promotion, and UX only after the evidence contracts are stable.

### Phase 45: Durable run contract and replay ledger

**Rationale:** Every replay, OOS, Agent, and UI claim needs one immutable run identity, snapshot, event sequence, idempotency model, and bounded lifecycle before candidate generation exists.  
**Delivers:** migrations/repository models for run manifests, snapshots, candidates, events, checkpoints, cancellation, and terminal states; JobStore bridge; typed API skeleton; full-outcome ledger.  
**Addresses:** immutable run spec, provenance, lifecycle/retry/resume, candidate ledger foundations (AF-REQ-01/04/10/16).  
**Avoids:** lost in-memory history, mutable runs, duplicate POSTs, stale data, and undercounted trials.  
**Research flag:** **Yes** — settle event/checkpoint transaction boundaries, sequence/idempotency constraints, and checkpoint file lifecycle.

### Phase 46: Deterministic Alpha Factory core

**Rationale:** Candidate identity and ordering must be replayable before their scores, Agent recommendations, or OOS evidence can be trusted.  
**Delivers:** canonical vocabulary/grammar fingerprint, bounded AST generation, seeded enumeration/mutation/crossover, lineage, dedupe, diversity/complexity cost, deterministic scheduler and cancellation budgets.  
**Addresses:** restricted generation and seeded search (AF-REQ-02/03/04/18/19/23).  
**Uses:** existing DSL parser/compiler metadata and candidate source binding, not a second VM.  
**Avoids:** arbitrary execution, candidate explosion, RL/GPU dependency, vocabulary reinterpretation, and worker-timing winners.  
**Research flag:** **Yes** — calibrate grammar size, legal mutations/crossovers, complexity costs, and CPU/memory budgets against governed A-share panels.

### Phase 47: Governed fold scoring, admission, and honest OOS

**Rationale:** Search output must be tied to the existing statistical and semantic controls before Agent review or promotion.  
**Delivers:** factor fold scorer through `FactorSignalChain`, measured-calendar/PIT fold manifests, bounded metric/artifact evidence, all fixed admission gates, selection-fold-only search, reserved selection OOS exactly once, rejection/failed trail, catalog links, and explicit OOS labels.  
**Addresses:** one signal path, evidence, deterministic gates, PIT semantics, temporal separation (AF-REQ-05/06/07/08/09).  
**Avoids:** train–serve skew, survivor/look-ahead bias, multiple comparison leakage, silent zero scores, and selection OOS mislabeled as blind final evidence.  
**Research flag:** **Yes** — decide whether to generalize `wf_folds` to typed research assets or add Alpha-specific fold rows; define factor scorer metrics/cost evidence without duplicating gates.

### Phase 48: FactorResearchAgent preflight, Stage 1, and Stage 2 workflow

**Rationale:** The Agent should orchestrate a proven factory and evidence path, never define its own evaluator or policy.  
**Delivers:** separate typed research graph/service with deterministic preflight, strict Stage 1 diagnosis/proposal, factory invocation, frozen-evidence Stage 2 review, provider adapter, schema/semantic validation, partial-failure trace, bounded retries, cancellation, resume, and checkpoint recovery.  
**Addresses:** AF-REQ-11 through AF-REQ-14 and evidence-linked review (AF-REQ-21/26).  
**Avoids:** provider calls after failed preflight, prompt injection, raw text creating revisions, model metric/gate overrides, autonomous loops, and discarded partial evidence.  
**Research flag:** **Yes** — settle provider retry/failure taxonomy, A-share diagnosis fields, model response retention policy, and stage-to-event transaction boundaries. No new LLM framework is required.

### Phase 49: Research-only Promotion Ticket and serving bridge

**Rationale:** Formal factor identity must be the final controlled handoff, after complete selection/OOS/admission evidence and Agent review.  
**Delivers:** candidate-to-DSL revision mapping, catalog/retention integration, evidence refresh, immutable ticket with approval/expiry/idempotent consume, explicit human reviewer, new immutable `FactorRevision`, and normal research/backtest signal binding without execution.  
**Addresses:** explicit review/promotion and research-only delivery (AF-REQ-15/17), stale approval protection.  
**Avoids:** automatic promotion, stale approvals, browser-selected authority, strategy-domain table misuse, and broker/monitor/portfolio calls.  
**Research flag:** **Yes** — verify transient candidate to registry mapping and compatibility with catalog/strategy signal binding.

### Phase 50: Research workbench, replay UX, and operational hardening

**Rationale:** UI should project stable durable contracts after the backend semantics are fixed; hardening then proves boundaries end to end.  
**Delivers:** FactorBacktest/ResearchLibrary/WalkForward Alpha panels, timeline via replayable SSE and polling, candidate lineage/comparison, evidence and rejection trail, OOS/ticket/degradation banners, reconnect/resume/cancel views, license/dependency/import audit, and focused browser/restart/replay checks.  
**Addresses:** lineage/frontier/stress/comparison/data-quality UX (AF-REQ-18–26) and release boundary.  
**Avoids:** UI as authority, SSE gaps/duplicates, confusing selection OOS, hidden degraded data, and release-time license or execution regressions.  
**Research flag:** Standard implementation patterns for most UI, but focused research/verification is still needed for SSE reconnect semantics, stale state, browser projection, and OOS/ticket labels.

### Phase Ordering Rationale

- Freeze identity, data, and policy before generation; generation before scoring; scoring/admission/OOS before Agent synthesis; complete evidence before human promotion; stable contracts before UX polish.
- Keep deterministic factory, Agent orchestration, persistence, and UI as separate seams so a provider outage cannot alter factor computation and a browser cannot establish scientific authority.
- Use existing Phase 10 factor gates and Phase 13 measured-calendar/OOS contracts rather than parallel v3 implementations. Keep selection OOS distinct from any future final-blind holdout.
- Treat all invalid/rejected/failed/retried work as evidence. A replay is not credible if it only reproduces a champion.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **MEDIUM-HIGH** | Existing repository versions, seams, and no-new-dependency conclusion are strongly grounded; exact future library behavior still depends on the current lock and focused integration checks. |
| Features | **HIGH** | Table stakes and anti-features map directly to current DSL, registry, evaluation, admission, hypothesis, catalog, and walk-forward contracts; competitive features are medium-confidence prioritization. |
| Architecture | **HIGH for seams; MEDIUM for additions** | Current boundaries and data flow are observed in code; new Alpha tables, transient candidate binding, fold-row choice, and graph contracts remain design work. |
| Pitfalls | **HIGH for AthenaQuant controls; MEDIUM for external methodology/security** | Existing OOS, append-only, signal-chain, and authority controls are concrete; arXiv/OWASP references corroborate practices but do not prove profitability or implementation correctness. |

**Overall confidence:** **HIGH for the direction and roadmap ordering; MEDIUM for sizing and target-schema details.**

### Gaps to Address

- **Alpha fold persistence shape:** decide typed generalization of `wf_folds` versus Alpha-specific rows while preserving exact-once uniqueness and existing strategy behavior; resolve in Phase 47 planning.
- **Transient candidate binding:** define how an unregistered canonical AST enters `FactorSignalChain` without weakening revision provenance or creating a second evaluator; resolve with a golden-panel contract in Phase 46/47.
- **Grammar and budget calibration:** measure a narrow A-share grammar's candidate count, memory, runtime, and artifact volume before broadening it; Phase 46 research must produce explicit limits.
- **Provider contracts:** choose bounded retry categories, response retention/hash policy, schema versions, and Stage 1/2 diagnosis taxonomy without introducing another Agent framework; Phase 48 must fault-inject malformed, refused, rate-limited, and timed-out responses.
- **Checkpoint/event atomicity:** define which facts commit together and how a restart detects inconsistent cursors; Phase 45 must test process crash and duplicate invocation.
- **Promotion binding:** specify candidate-to-`FactorRevision` mapping and catalog/normal strategy signal compatibility; Phase 49 must test changed data/policy/candidate and concurrent approval.
- **Final-blind claims:** v3.0 should not promise a blind final holdout; if required later, reserve a separate range unavailable to factory, Agent, feature selection, and threshold tuning.
- **Operational scale:** SQLite is appropriate for this research-only, single-host boundary, but worker/artifact limits and WAL/filesystem deployment must be validated before any scale-out proposal.

## Sources

### Primary (HIGH confidence)

- Current AthenaQuant repository: `backend/app/research/factor_dsl.py`, `factor_registry.py`, `signal_chain.py`, `evaluation.py`, `admission.py`, `catalog.py`, `hypotheses.py`, `repository.py`, `backtest/walkforward.py`, `backtest/optimizer.py`, `operational/migrations.py`, `analysis/graph.py`, `advanced/workflow.py`, `advanced/jobs.py`, `forecast/api.py`, `forecast/repository.py`, and existing frontend research/EventSource components.
- `.planning/PROJECT.md:11-20,84-103,126-133` — locked v3.0 goal, no-execution boundary, shared signal chain, admission, and walk-forward/OOS decisions.
- `.planning/research/STACK.md` — current lock baseline, integration seams, dependency decisions, and version compatibility notes.
- `.planning/research/FEATURES.md` — REQ-ready table stakes, differentiators, anti-features, workflows, and dependency graph.
- `.planning/research/ARCHITECTURE.md` — target data flow, durable contracts, storage boundary, module map, API/UI seams, and phase graph.
- `.planning/research/PITFALLS.md` — prioritized risk table and phase-specific enforcement/verification matrix.

### Secondary (MEDIUM confidence)

- `../docs/aaa/alphamaster/DEEP-ANALYSIS.md` and `QUICK-START.md` — constrained vocabulary/generation, lineage/diversity/cost patterns, train/serve identity, and provenance/OOS limitations; patterns only, no source reuse.
- `../docs/aaa/pa-agent/DEEP-ANALYSIS.md` and `QUICK-START.md` — preflight, staged structured analysis, partial records, approval refresh, and AGPL boundary; patterns only, no source reuse.
- `../docs/aaa/10-SYNTHESIS.md` — data-contract, quality-state, replayable event, scoped-tool, and research/paper-only principles.
- Official documentation: [LangGraph SQLite checkpoint](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-sqlite/README.md), [Pydantic JSON](https://github.com/pydantic/pydantic/blob/main/docs/concepts/json.md), [Pydantic models/strictness](https://github.com/pydantic/pydantic/blob/main/docs/concepts/models.md), [SSE-Starlette](https://github.com/sysid/sse-starlette/blob/main/_autodocs/01-eventsourceresponse.md), [Polars Parquet](https://github.com/pola-rs/polars/blob/main/docs/source/user-guide/io/parquet.md), [SQLite transactions](https://www.sqlite.org/lang_transaction.html), and [SQLite WAL](https://www.sqlite.org/wal.html).

### Tertiary (LOW confidence / corroboration only)

- [Interpretable Hypothesis-Driven Trading: A Rigorous Walk-Forward Validation Framework](https://arxiv.org/html/2512.12924v1) — methodology reference for information-set discipline, rolling validation, realistic costs, and honest non-significant reporting; not profitability evidence.
- [OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) — security corroboration for instruction/data separation, structured validation, least privilege, and human approval; repository controls remain authoritative.

---
*Research completed: 2026-08-08*  
*Ready for roadmap: yes*
