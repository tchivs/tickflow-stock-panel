# Phase 2: Factor And Strategy Research - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Mode:** Autonomous (`--auto`); all decisions below are locked conservative defaults.

<domain>
## Phase Boundary

On the governed Phase 1 market-data foundation, deliver one researcher workflow that turns a factor hypothesis into a restricted, validated factor definition; evaluates it with reproducible IC and RankIC evidence; backtests factors or existing strategies; and retains comparable experiment records. The workflow includes factor storage, similarity discovery, natural-language-to-DSL drafting, and experiment/model-version comparison.

This phase does **not** introduce arbitrary user code execution, strategy evolution or promotion, autonomous research agents, broker execution, a second research datastore, or an independently deployed research application.

## Scoped Acceptance Framing

Planning and verification MUST prove each roadmap outcome end-to-end:

1. A researcher can create a factor in the permitted DSL, receive validation before evaluation, store it, and see deterministic similarity candidates from stored factors.
2. A natural-language hypothesis produces a reviewable DSL draft; only a validated and completed backtest result may be retained for comparison, with IC and RankIC visible.
3. A researcher can run factor or existing-strategy experiments and compare the retained configuration, governed-data inputs, predictions, metrics, artifacts, and registered model version side-by-side.

</domain>

<decisions>
## Implementation Decisions

### Restricted Factor Language And Registry
- **D-01:** Factor definitions use a purpose-built, declarative DSL that is parsed and validated before execution. Its vocabulary is an explicit allowlist of governed/enriched numeric fields, approved operators, and a finite set of documented deterministic functions; it MUST NOT evaluate Python, imports, attribute access, filesystem/network access, user-defined functions, or arbitrary Polars expressions.
- **D-02:** The registry stores a canonical normalized expression, DSL-version identifier, factor name, human description/hypothesis, provenance, and immutable revision identity. Editing a stored definition creates a new revision; prior evaluations remain linked to the definition revision they used.
- **D-03:** Similar-factor discovery is deterministic and explainable: normalize the DSL AST and rank stored factors using structural signature plus referenced-field/operator overlap. Present candidates and the reason for the match; never auto-merge, overwrite, or block a valid factor merely because it is similar.
- **D-04:** Reuse the existing custom-signal allowlist/validation and Polars-expression safety ideas only as an input-validation precedent. Do not stretch its boolean JSON-condition format into the Phase 2 factor DSL.

### Evaluation And Natural-Language Hypotheses
- **D-05:** Evaluation validates the full definition and all run inputs before computing. Every run records the explicit universe, date range, forward-return horizon, rebalance cadence, asset type, missing-data/warmup treatment, and factor revision; no implicit defaults may be hidden from a retained result.
- **D-06:** IC and RankIC are mandatory factor-evaluation outputs, with their time series and summary statistics retained alongside the configuration. Existing grouping and long-short outputs may remain supporting evidence but cannot replace IC/RankIC.
- **D-07:** Natural-language input produces a non-persistent DSL draft plus explanation/provenance. The draft must pass the same parser and allowlist validation, then be explicitly reviewed and backtested before it can be stored as a comparable factor. Invalid or unsupported requests return actionable validation feedback rather than a permissive fallback expression.
- **D-08:** Any model/provider used to create a hypothesis is recorded as model provenance. The model cannot directly execute expressions, write factor records, or bypass validation/backtest gating.

### Reproducible Experiments And Comparison
- **D-09:** Treat a retained experiment as an immutable provenance snapshot, not a mutable “latest result.” It captures factor or strategy revision/identity, resolved configuration, governed-data manifest or stable input references, generated predictions/signals, metrics, managed artifacts, execution status, timestamps, and registered model version when applicable.
- **D-10:** Store operational experiment/factor/catalog metadata in the established SQLite operational-state boundary. Keep governed time series in Parquet/DuckDB/Polars; store experiment artifacts under the application data directory and reference them from metadata. Do not add an external database, queue, MLflow deployment, or separate data lake.
- **D-11:** A comparison is an explicit side-by-side selection of retained completed experiments. It must expose values and differences for configuration, data input identity, predictions, metrics, artifacts, and model version, and show a comparability warning when universe, time window, horizon, or data revision differs. It MUST NOT conceal those differences behind an aggregate “winner” score.
- **D-12:** Failed, cancelled, unvalidated, or draft runs may retain diagnostic status for auditability but are excluded from the comparable experiment set. A natural-language-derived factor is eligible only after D-07’s validation and completed backtest gate.

### Strategy And Workspace Boundaries
- **D-13:** Strategy experiments reuse the existing registered strategy and backtest contracts. Phase 2 records the strategy identity/version and run provenance; it does not add arbitrary strategy authoring or execution. Custom strategy AST/import/resource sandboxing and strategy evolution/promotion remain Phase 4 scope.
- **D-14:** Extend the existing Backtest workspace and unified frontend API/query patterns for the factor library, hypothesis draft/review, experiment history, and comparison flow. Do not create a parallel shell, second router hierarchy, or a distinct data-fetching convention.
- **D-15:** Preserve independently activatable module boundaries: factor registry/DSL, evaluation/backtesting, and experiment catalog/comparison must be separable domains that use the shared governed-data and existing backtest interfaces rather than becoming additions to the large repository or backtest-engine modules.

### Claude's Discretion
- Exact DSL syntax, AST schema, canonicalization algorithm, ranking weights, database schema/migration mechanism, artifact file format, API route shape, and component layout are open to the planner provided every locked decision and established project convention is honored.
- Exact default evaluation parameters are open only when exposed in the retained configuration and visibly labeled in the UI; they must not weaken validation, provenance, or comparability safeguards.

## Autonomous Selection Audit

`--auto` selected every identified Phase 2 gray area. No user prompt was issued.

| Area | Question resolved | Auto-selected conservative default | Rationale |
| --- | --- | --- | --- |
| Factor language boundary | Can researchers run free-form code or only safe expressions? | Restricted parsed DSL with explicit allowlists and no arbitrary execution (D-01). | Meets FACT-01 while preserving a later sandbox boundary and avoiding code injection. |
| Stored-factor identity | May edits rewrite historical evidence? | Canonical immutable revisions with provenance (D-02). | Keeps evaluations auditable and reproducible. |
| Similarity semantics | Should duplicate detection be opaque, automatic, or explainable? | Deterministic AST/field-overlap candidates with explanations; no auto-merge/block (D-03). | Meets FACT-01 without LLM/embedding dependence or destructive behavior. |
| Existing custom signals | Is the Phase 1 boolean signal format the new DSL? | Reuse validation principles only; build a dedicated factor DSL (D-04). | Avoids overloading a constrained signal feature into an incompatible language. |
| Evaluation provenance | Which inputs must a retained evaluation disclose? | Persist every resolved universe, window, horizon, cadence, data treatment, and factor revision (D-05). | Makes FACT-01/02/03 results reproducible. |
| Core evidence | Are IC/RankIC optional supporting metrics? | IC and RankIC are mandatory retained outputs (D-06). | Directly satisfies the requirement; grouping/long-short remain supplemental. |
| Natural-language flow | Can an LLM-generated factor save itself before proof? | Reviewable validated draft, explicit review, completed backtest, then retention (D-07/D-08). | Conservative retention gate prevents unchecked hypotheses entering comparison. |
| Experiment permanence | Should a result mutate as code/data changes? | Immutable provenance snapshots (D-09). | Enables reliable comparisons over time. |
| Persistence boundary | Add dedicated experiment services or reuse local architecture? | SQLite metadata, managed local artifacts, shared Parquet/DuckDB/Polars data lake (D-10). | Preserves mandated single-container, data-lake-first architecture. |
| Comparison behavior | Hide setup differences behind a score? | Side-by-side evidence plus comparability warnings, no opaque winner (D-11). | Keeps research conclusions inspectable. |
| Incomplete runs | Should drafts/failures enter retained comparisons? | Retain diagnostics separately; only completed validated runs compare (D-12). | Enforces FACT-02's validation-and-backtest gate. |
| Strategy scope | Add arbitrary strategy code or evolution now? | Reuse registered strategy backtests; defer sandboxing/evolution (D-13). | Delivers FACT-03 without consuming Phase 4 safeguards scope. |
| Research UI | Build a separate product surface? | Extend the existing Backtest workspace/API/query patterns (D-14). | Reuses working interfaces and avoids a second convention. |
| Module design | Add new logic to existing monoliths? | Independently activatable research domains over shared foundation (D-15). | Carries forward project-level modularity and Phase 1 architecture. |

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product And Phase Scope
- `.planning/PROJECT.md` — required single-container, Parquet/DuckDB/Polars time-series, SQLite operational-state, independent-module, and decision-safety boundaries.
- `.planning/REQUIREMENTS.md` — locked Phase 2 requirements `FACT-01` through `FACT-03` and the Phase 4 sandbox boundary.
- `.planning/ROADMAP.md` — Phase 2 goal and the three observable success criteria; defines fixed scope.
- `.planning/phases/01-core-merger/01-CONTEXT.md` — carried-forward host, persistence, frontend, data-governance, and upstream-boundary decisions.
- `.planning/phases/01-core-merger/01-VERIFICATION.md` — certified Phase 1 governed-data and backtest foundation evidence.
- `docs/ARCHITECTURE.md` §“因子/策略研究层 (Phase 2)” and §“Phase 2 — 因子/策略强化” — source architecture for Factor DSL, FactorZoo, IC/RankIC, LLM hypothesis drafting, experiment records, model versions, and the required Phase 2 sequence.

### Existing Research And Data Interfaces
- `backend/app/strategy/custom_signals.py` — current allowlisted field validation and safe Polars-expression construction precedent; not the Phase 2 DSL itself.
- `backend/app/api/signals.py` — current validated custom-signal persistence/API pattern.
- `backend/app/backtest/factor.py` — existing Polars factor evaluation, IC/IR, grouping, long-short outputs, and result configuration contract.
- `backend/app/backtest/strategy.py` — existing registered-strategy backtest configuration/result contract.
- `backend/app/backtest/engine.py` — shared governed-data panel loading and backtest computation boundary.
- `backend/app/api/backtest.py` — existing factor/strategy backtest routes, server safety limits, and strategy job lifecycle.
- `backend/app/tickflow/repository.py` — governed Parquet/DuckDB/Polars data-access boundary.
- `backend/app/indicators/pipeline.py` — enriched governed indicator inputs available to research.

### Existing Frontend Integration
- `frontend/src/pages/Backtest.tsx` — current factor, strategy, and optimization workspace to extend rather than duplicate.
- `frontend/src/pages/backtest/FactorBacktest.tsx` — current factor input/result interaction and chart integration.
- `frontend/src/pages/backtest/StrategyBacktest.tsx` — current strategy backtest interaction and persisted-view behavior.
- `frontend/src/lib/api.ts` — unified typed API contract for factor and strategy backtest results.
- `frontend/src/lib/backtestTask.ts` — existing strategy backtest task/reconnection semantics; reuse only where the planned run lifecycle needs it.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `FactorBacktestService` (`backend/app/backtest/factor.py`) already calculates factor IC/IR, RankIC-related evidence, grouped returns, long-short results, and serializable run configuration over Polars data.
- `StrategyBacktestService` and `BacktestEngine` already execute registered strategies against the governed repository and return configuration, metrics, curves, and trades.
- `custom_signals` plus `api/signals.py` provide a tested precedent for allowlisted fields, validation-before-persistence, JSON-backed definitions, and invalidating derived signal caches.
- `api/backtest.py` provides factor/strategy route conventions, bounded server backtest protection, progress/cancellation infrastructure for strategy runs, and typed request validation.
- The existing `Backtest` React page, `FactorBacktest`, `StrategyBacktest`, charts, typed `api.ts`, and TanStack Query conventions provide the natural workspace and interaction pattern.

### Established Patterns
- Time series stay in governed Parquet and are queried via DuckDB/Polars; operational state is local and is now SQLite-backed after Phase 1.
- Backend routes validate with Pydantic, delegate to services, and return structured error details; Python paths use typed dataclasses and explicit graceful errors.
- React pages use the unified `api.ts` client, TanStack Query for server state, and the existing responsive application shell; pages are lazy-loaded through the central router.
- Existing backtest execution uses stable configuration/result objects and limits concurrent server work because the single-container runtime has bounded memory.

### Integration Points
- Register factor-registry, hypothesis, and experiment APIs in the existing FastAPI application and persistence lifecycle; keep their modules separate from the large repository and backtest engine.
- Feed validated DSL compilation into the established governed-data/Polars evaluation boundary and reuse current factor/strategy result contracts where compatible.
- Extend `/backtest` with research library, draft/review, history, and side-by-side comparison views, retaining its typed API and React Query patterns.
- Capture experiment provenance against existing data-lake references and strategy/factor revisions, not copies of raw market data.

</code_context>

<specifics>
## Specific Ideas

- The user selected autonomous conservative defaults: validation and provenance take precedence over permissive expression authoring, automatic retention, opaque similarity, or aggregate experiment rankings.
- The phrase “backtest it before it is retained for comparison” is enforced as a hard retention gate for natural-language-derived factors.
- Phase 2 is the integration of DSL + FactorZoo-like registry + reproducible experiment records into the existing Tickflow-hosted application, not a new deployment or a forked external platform.

</specifics>

<deferred>
## Deferred Ideas

- Arbitrary custom strategy code, AST/import/resource sandbox enforcement, and custom-strategy execution belong to Phase 4 `SAFE-02`.
- Strategy evolution, mutation/crossover, promotion gates, champions, and automated research feedback loops belong to Phase 4 `ADV-02`/`ADV-03`.
- Autonomous agents, scoped agent tokens, allowlists, rate limits, idempotent agent jobs, and agent SSE progress belong to Phase 4 `SAFE-01`.
- Source-quality-graded AI market analysis, investment-committee reporting, and signal-lifecycle tracking belong to Phase 3.
- Automated live broker execution remains out of scope for the project.

</deferred>

---

*Phase: 02-Factor And Strategy Research*
*Context gathered: 2026-07-11*
