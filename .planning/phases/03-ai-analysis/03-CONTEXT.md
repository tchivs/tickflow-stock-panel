# Phase 3: AI Analysis - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver AI-assisted market and portfolio research that makes evidence quality, material-number verification, reasoning, and signal validity visible and reviewable. The phase produces a source-grounded multi-perspective report, valuation only when supported by the supplied evidence, an investment-committee memo, and an append-only signal lifecycle/outcome record.

It does not add automated trading, automatic adoption or execution of AI conclusions, model-controlled lifecycle changes, unbounded tool use, a parallel top-level workspace, or a second persistence/data boundary.

</domain>

<decisions>
## Implementation Decisions

### Signal Lifecycle Governance
- **D-01:** The system may propose `strengthened`, `weakened`, `falsified`, or `priced_in` transitions from newly available evidence, but an investor or researcher must explicitly confirm a proposal before the official lifecycle state changes.
- **D-02:** Use state-specific proposal thresholds: strengthened/weakened proposals require attributable new evidence; falsification requires either a pre-recorded invalidation condition or independently cross-checked contradictory evidence; priced-in proposals require explicit price and event context. Every proposal remains subject to D-01's human confirmation.
- **D-03:** At confirmation, create an immutable, auditable outcome-observation plan containing exactly one horizon of 20, 60, or 120 trading days, the benchmark, and the evaluation metric. Later observations append to that plan; they do not rewrite it.
- **D-04:** Retain every proposed transition with its evidence, reviewer, confirmation/rejection result, and timestamp. Rejected proposals cannot change the official lifecycle but remain available to audit and improve rule/model quality.

### Existing Workspace Paths
- **D-05:** Enter AI research from the current investment object: the stock-analysis surface opens the selected security's analysis, and Portfolio opens the selected account or aggregate-portfolio analysis. Report history is for review and must not replace this object-first entry.
- **D-06:** The initial object view prioritizes analysis conclusion and evidence state: source/cross-check summary and unresolved differences appear before a concise summary. Perspectives, valuation, IC memo, and raw evidence remain available in the established detail structure.
- **D-07:** Default to the newest completed, reviewable report for the active object. Keep chronological history, and preserve a user-selected historical report for the current session rather than replacing it during refresh.
- **D-08:** Bind each portfolio report explicitly to the active account or aggregate portfolio. Show that scope's conclusion and evidence before a drill-down into holdings; persist the object scope and never silently combine data across accounts.

### Claude's Discretion
- Exact A/B/C source admission rules, source-independence detection algorithm, material-number schema, conflict presentation mechanics, report API shape, LangGraph/checkpointer integration, database schema and migration mechanism, observation-plan UI control, and historical-report persistence mechanism are open to the planner.
- The planner may choose exact page sections and component composition only within `03-UI-SPEC.md`'s existing-surface, accessibility, copy, responsive, and evidence-first contracts.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product Scope And Constraints
- `.planning/PROJECT.md` — self-hosted investment-research boundary; single-container, Parquet/DuckDB/Polars, SQLite, independent-module, and no-live-execution constraints.
- `.planning/REQUIREMENTS.md` — Phase 3 requirements `ANLY-01` through `ANLY-03` and the project-wide exclusions.
- `.planning/ROADMAP.md` — Phase 3 goal and observable success criteria; defines the fixed phase boundary.
- `docs/ARCHITECTURE.md` — source architecture and progressive module/adoption constraints.

### Phase 3 Binding Contracts
- `.planning/phases/03-ai-analysis/03-AI-SPEC.md` — required bounded LangGraph workflow, structured-output boundary, evidence/lifecycle safety rules, framework lock, evaluation plan, and production guardrails.
- `.planning/phases/03-ai-analysis/03-UI-SPEC.md` — required existing-surface UI integration, evidence disclosure, lifecycle rendering, interaction states, accessibility, copy, responsive behavior, and verification scenarios.

### Carried-Forward Decisions And Integration Boundaries
- `.planning/phases/01-core-merger/01-CONTEXT.md` — Tickflow host, governed data, SQLite operational state, shared SSE, portfolio, and frontend integration decisions.
- `.planning/phases/02-factor-and-strategy-research/02-CONTEXT.md` — immutable provenance, validated AI drafting, experiment-comparison, typed API/query, and independently activatable-module decisions.
- `.planning/phases/01-core-merger/01-VERIFICATION.md` — certified governed-data and backtest foundation evidence.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Existing `StockAnalysis`, `Portfolio`, and `AiAnalysisHost` surfaces provide the constrained places for object-bound reports, evidence disclosure, and signal history; do not introduce a top-level AI dashboard or second report dialog.
- `frontend/src/lib/api.ts` and TanStack Query factories are the existing typed client/server-state path.
- The FastAPI/Pydantic application architecture and current OpenAI-compatible provider boundary can host the bounded analysis adapter.
- Governed Parquet/DuckDB/Polars data, enriched indicators, and SQLite operational metadata supply the evidence/provenance boundary.

### Established Patterns
- Python routes validate with Pydantic and delegate to focused services; React uses the existing API client and TanStack Query rather than direct `fetch` or a second state convention.
- Time series remain in Parquet/DuckDB/Polars; operational metadata and append-only research records belong in SQLite and managed application storage.
- Reports, evidence, source grades, and lifecycle state must be server-authoritative. The model may generate only validated report body content; it cannot assign source grades, claim cross-checks, or mutate lifecycle state.
- New backend responsibilities belong in a dedicated analysis domain rather than expanding large repository, backtest, or strategy modules.

### Integration Points
- Add analysis-domain schemas, fixed graph, model adapter, service, and append-only lifecycle logic to the existing FastAPI application and operational-state lifecycle.
- Extend the existing stock, portfolio, and global-analysis surfaces with object-scoped report details, source/verification disclosure, and lifecycle history.
- Reuse existing SSE/reconnection patterns only where an analysis-generation task needs progress; duplicate requests must resolve to the same active task.

</code_context>

<specifics>
## Specific Ideas

- The user chose object-first research: selected security, selected account, or explicit aggregate portfolio defines the report's identity and scope.
- Trust is visible before prose: evidence status and unresolved differences precede the report summary.
- Lifecycle automation may suggest but never self-confirm; rejected suggestions remain auditable without changing official state.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 3 scope.

</deferred>

---

*Phase: 3-AI Analysis*
*Context gathered: 2026-07-11*
