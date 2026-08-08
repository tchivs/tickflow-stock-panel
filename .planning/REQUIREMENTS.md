# Requirements: AthenaQuant v3.0 可回放 Alpha Factory 与 FactorResearchAgent

**Defined:** 2026-08-08  
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## Milestone Scope

v3.0 extends the existing governed factor workflow into a replayable Alpha Factory and a two-stage FactorResearchAgent.

Locked boundaries:

- Candidate formulas use the existing restricted Factor DSL and canonical AST; no arbitrary Python, imports, `eval`, or second expression engine.
- Candidate computation uses the single shared `FactorSignalChain`; no search-only evaluator or StackVM fork.
- The default search is deterministic seeded grammar/evolution using the existing Python/runtime stack; no new base dependency, PyTorch, RL, GPU, distributed queue, or WebSocket requirement.
- Search and Agent runs freeze data, universe, DSL/grammar/vocabulary, policy, costs, seed, fold geometry, and provenance before generation or provider calls.
- Reserved walk-forward OOS is inaccessible during search and Agent review, then evaluated exactly once after selection.
- Agent output is untrusted proposal/review data. Deterministic code owns parsing, metrics, admission gates, persistence, and authority.
- Promotion is research-only and requires explicit human review plus approval-time evidence refresh. No broker, order, portfolio, monitor, or live execution authority is added.
- AlphaMaster and PA_Agent contribute architectural patterns only. Their source, prompts, domain rules, and AGPL-derived implementation are not copied into this MIT backend.

## Active Requirements

### Alpha Factory Contract and Determinism

- [x] **AF-REQ-01**: A researcher can create an immutable factory run specification containing DSL/grammar/vocabulary versions, seed, expression limits, candidate budget, objective policy, universe, measured date range, fold geometry, costs, and code/data manifest; changing inputs creates a new run instead of mutating the original.
- [x] **AF-REQ-02**: Given the same frozen specification, seed, and governed input manifest, a replay produces the same canonical candidate expressions, candidate IDs/digests, order, statuses, and checksums.
- [x] **AF-REQ-03**: Every generated expression is parsed and validated before evaluation; unsupported fields/functions/operators, invalid arity or partition semantics, excessive depth/window, non-finite literals, and malformed expressions become explicit invalid candidate records with diagnostics.
- [x] **AF-REQ-04**: The run retains every attempted candidate, including invalid, duplicate, low-coverage, failed, rejected, and admitted outcomes, with parent/mutation lineage, seed/step, status, reason, and evidence references; the system never retains only the champion.
- [ ] **AF-REQ-05**: Factory scoring, Agent-requested evaluation, admission, composite use, walk-forward folds, and later as-of serving all compute factor values through the existing governed `FactorSignalChain` and expose the panel/universe/source/warmup fingerprints used.
- [ ] **AF-REQ-06**: A replay uses measured A-share trading dates and point-in-time membership; missing, suspended, non-finite, warmup, and source-quality states follow the declared policy, and current-constituent/full-lake substitution fails closed.

### Evaluation, Admission, OOS, and Provenance

- [ ] **AF-REQ-07**: For every evaluated candidate, a researcher can inspect resolved configuration and immutable evidence including per-date IC/RankIC, summaries, ICIR, positive rate, coverage, monthly robustness, group/long-short evidence, costs, and diagnostics; evaluation failure is a terminal reason, not a zero score.
- [ ] **AF-REQ-08**: Candidate status is produced by the existing deterministic admission policy with each gate's observed value, threshold, and reason visible; the Factory and Agent cannot edit thresholds, reorder gates, or convert rejection into admission.
- [ ] **AF-REQ-09**: Search and Agent review never consume the reserved OOS fold; the UI distinguishes selection-fold evidence, selection OOS, and any future final-blind holdout, and never labels selection OOS as blind final validation.
- [x] **AF-REQ-10**: A run can be replayed from stored data/partition, universe, factor/DSL, grammar/vocabulary, seed, configuration, code/build, provider/model, candidate-order, and artifact checksums; missing required manifest fields fail closed.

### FactorResearchAgent

- [ ] **AF-REQ-11**: Before any model call, deterministic preflight checks data availability/freshness, source quality, measured calendar, universe scope, required fields, sample length, DSL/grammar compatibility, budget, provider availability, and policy mode; a failed preflight makes zero provider calls and returns machine-readable reasons.
- [ ] **AF-REQ-12**: Stage 1 accepts a bounded research thesis and permitted DSL/grammar options, then returns versioned schema-validated JSON containing hypotheses/expressions, explanation, assumptions, scope, uncertainty, and evidence references; it remains a transient proposal until explicit review.
- [ ] **AF-REQ-13**: Stage 2 receives only frozen run inputs and server-produced candidate/evaluation/gate evidence, then returns schema-validated evidence-linked review with caveats and a bounded recommendation; it cannot change expressions, metrics, thresholds, OOS state, or admission status.
- [ ] **AF-REQ-14**: Every Stage 1/2 call records prompt/template/schema version, provider/model/version, request scope, response checksum or bounded raw response, parsed output, validation errors, retries, cancellation, latency, and partial-failure state; provider failure never creates a fabricated fallback draft.

### Human Review and Research-only Delivery

- [ ] **AF-REQ-15**: A researcher can compare a proposal's expression, assumptions, evidence, gate trail, and provenance, then explicitly save a new immutable `FactorRevision`; changed expression/explanation/provenance that no longer matches the issued draft is rejected, and unreviewed output is absent from the formal catalog.
- [x] **AF-REQ-16**: The workbench exposes queued/running/completed/failed/cancelled states, candidate/fold progress, cooperative cancellation, idempotent retry, and checkpointed resume; retry resumes or creates a linked run and never overwrites an earlier run or repeats a committed OOS/promotion side effect.
- [ ] **AF-REQ-17**: Alpha Factory and Agent runs expose only inspect, compare, retain, and research-only promotion actions; no route, collaborator, UI action, or model output can place broker orders, mutate positions/portfolios, activate monitors, or enable live execution.

### Research Workbench and Differentiators

- [ ] **AF-REQ-18**: A researcher can inspect parent-to-child mutation/crossover lineage, canonical expression diffs, seed/step, and branch termination reasons, then replay one branch under the same frozen inputs.
- [x] **AF-REQ-19**: Search results show objective score together with structural similarity, field/operator overlap, factor-output/IC-series correlation, coverage, and fixed-policy diversity/redundancy outcomes; similar candidates remain inspectable rather than being silently merged.
- [ ] **AF-REQ-20**: A candidate family can be evaluated across declared rebalance, fee/slippage, calendar-regime, coverage, and symbol-subset stress cases, with the exact trial matrix and evidence recorded without changing primary admission thresholds.
- [ ] **AF-REQ-21**: Stage 2 can identify missing assumptions, contradictory metrics, gate failures, narrow coverage, or redundancy and link each claim to candidate/evaluation/gate/artifact IDs; follow-up work is a bounded new run, never an unbounded autonomous loop.
- [ ] **AF-REQ-22**: A completed run can be cloned into a new immutable specification while changing only declared dimensions; the UI shows field-level differences and parent/child links, and unchanged inputs retain their hashes.
- [x] **AF-REQ-23**: Candidate, wall-clock, memory, provider-call, retry, artifact, and worker budgets are enforced server-side; parallel workers may improve throughput but cannot change candidate order, score reduction, winner, or replay result.
- [ ] **AF-REQ-24**: Researchers can compare explicitly retained experiment snapshots and candidate families side by side, including configuration, evidence, provenance, gate status, and artifacts without an opaque hidden winner score.
- [ ] **AF-REQ-25**: The workbench displays data date, provider/source, cache/degradation state, missing fields, membership coverage, and whether evidence is exploratory, selection-fold, selection-OOS, or final-blind; degraded results cannot look equivalent to clean completed results.
- [ ] **AF-REQ-26**: Tests and operators can run an explicitly declared offline Agent fixture with known proposal and validation trace when no provider is configured; production paths never silently switch to the fixture, and the UI labels fixture evidence as non-production.

## Future Requirements (Deferred)

- Neural/RL/AlphaGPT policy search, GPU infrastructure, and distributed optimization.
- Broad grammar expansion before the narrow grammar is replayable and statistically accounted for.
- Multi-agent debate, self-modifying prompts, model-selected tools, and autonomous/unbounded research loops.
- Automatic factor promotion, paper/live execution, broker integration, monitor activation, portfolio mutation, and order submission.
- A separate final-blind holdout unless a later milestone defines and funds a distinct data contract.
- External event brokers, Redis/Kafka/NATS, Celery/RQ, WebSockets, or a second Agent/validation framework.

## Out of Scope

- Investment return guarantees or claims that high IC/Agent confidence implies a trading recommendation.
- Copying AlphaMaster or PA_Agent source, prompts, assets, crypto/Price Action rules, or AGPL-derived implementation.
- Arbitrary code generation or execution through the Alpha Factory/FactorResearchAgent.
- Changes to the existing broker/execution boundary or the user's `frontend/src/pages/Watchlist.tsx`.
- Replacing the existing Parquet/DuckDB/Polars/SQLite architecture with an external database or queue.

## Traceability

| REQ-ID | Phase | Status |
|---|---:|---|
| AF-REQ-01 | Phase 45 | Complete |
| AF-REQ-02 | Phase 46 | Complete |
| AF-REQ-03 | Phase 46 | Complete |
| AF-REQ-04 | Phase 45 | Complete |
| AF-REQ-05 | Phase 47 | Pending |
| AF-REQ-06 | Phase 47 | Pending |
| AF-REQ-07 | Phase 47 | Pending |
| AF-REQ-08 | Phase 47 | Pending |
| AF-REQ-09 | Phase 47 | Pending |
| AF-REQ-10 | Phase 45 | Complete |
| AF-REQ-11 | Phase 48 | Pending |
| AF-REQ-12 | Phase 48 | Pending |
| AF-REQ-13 | Phase 48 | Pending |
| AF-REQ-14 | Phase 48 | Pending |
| AF-REQ-15 | Phase 49 | Pending |
| AF-REQ-16 | Phase 45 | Complete |
| AF-REQ-17 | Phase 49 | Pending |
| AF-REQ-18 | Phase 50 | Pending |
| AF-REQ-19 | Phase 46 | Complete |
| AF-REQ-20 | Phase 50 | Pending |
| AF-REQ-21 | Phase 48 | Pending |
| AF-REQ-22 | Phase 50 | Pending |
| AF-REQ-23 | Phase 46 | Complete |
| AF-REQ-24 | Phase 50 | Pending |
| AF-REQ-25 | Phase 50 | Pending |
| AF-REQ-26 | Phase 48 | Pending |

---
*Requirements defined: 2026-08-08 — v3.0 Alpha Factory + FactorResearchAgent*
