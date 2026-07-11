# Phase 3: AI Analysis - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver an AI-assisted research workflow for market and portfolio objects that makes evidence quality, material-number cross-checks, structured multi-perspective reasoning, valuation applicability, IC review, and a signal's lifecycle visible and auditable. Analysis is bounded decision support: evidence preparation and lifecycle transitions are deterministic and reviewable; no workflow may place orders, execute market actions, or autonomously advance an official research state.

The phase extends existing stock-analysis, Portfolio, and AI-report/history surfaces. It does not create a parallel application shell, a top-level AI dashboard, autonomous agents, live-execution controls, or mutable/rewriteable evidence history.

</domain>

<decisions>
## Implementation Decisions

### Evidence-Grounded Analysis Contract
- **D-01:** The locked AI design contract applies: deterministic services assign A/B/C source grades and cross-check material numbers before a model writes the report. Unresolved or conflicting facts remain visible and cannot be upgraded or hidden by the model.
- **D-02:** Model output is a validated structured report body only. Sources, source grade, cross-check state, lifecycle state, and audit metadata are server-owned; the workflow is a fixed bounded graph with no tools, autonomous loop, or action execution.
- **D-03:** The report must expose multi-perspective rationale, scoring explanation, valuation only when applicable, and an investment-committee memo. It is research material, not an execution instruction or promise of returns.

### Signal Lifecycle Governance
- **D-04:** New attributable evidence may cause the system to propose a lifecycle transition, but an investor or researcher must confirm it before the official signal state changes.
- **D-05:** Transition thresholds are state-specific: strengthened and weakened proposals require attributable new evidence; falsification requires a recorded invalidation condition or independently cross-checked contradictory evidence; priced-in requires explicit price/event context. Every proposal still requires human confirmation.
- **D-06:** Confirmation creates an immutable, auditable observation plan with one 20-, 60-, or 120-trading-day window, a benchmark, and an evaluation metric. The plan cannot be rewritten; later observations are appended.
- **D-07:** Preserve every lifecycle review outcome, including proposal, supporting evidence, reviewer, confirmation or rejection, and timestamp. Rejected proposals do not change the official state but remain reviewable for rule and model quality.

### Default Paths In Existing Workspaces
- **D-08:** Initiate new analysis in the current object's workspace: stock analysis for its selected instrument and Portfolio for its selected account or portfolio. The global AI host is for resuming or reviewing existing reports.
- **D-09:** When a usable report already exists, open the most recent evidence-backed report with its generation time and evidence limitations visible. Regeneration is an explicit user action.
- **D-10:** Preserve selected object, report version, time window, selected panel, and reading position when moving among report, evidence, and signal-history views. Panels load independently without clearing content already read.
- **D-11:** During an explicit regeneration, retain the prior report for reading and show update progress. Permit only one in-progress generation for an object; set the validated result as newest while preserving older reports in history.

### the agent's Discretion
- Exact SQLite schema/migration design, analysis API route names, report-version retention mechanics, analysis graph implementation, model-adapter internals, and precise component composition remain open, provided the locked AI, UI, provenance, and lifecycle decisions are met.
- The planner may choose the exact material-number schema, source-provider composition, report scoring dimensions, and display layout only where they preserve the evidence-first UI contract and never conceal uncertainty or cross-source conflicts.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product And Fixed Scope
- `.planning/PROJECT.md` — single-container, Parquet/DuckDB/Polars time-series, SQLite operational-state, independent-module, and AI decision-safety boundaries.
- `.planning/REQUIREMENTS.md` — Phase 3 requirements `ANLY-01` through `ANLY-03` and Phase 4/5 boundaries.
- `.planning/ROADMAP.md` — Phase 3 goal and its three observable success criteria.
- `docs/ARCHITECTURE.md` §“AI 分析层” and §“Phase 3 — AI 分析增强” — source architecture for source-quality grading, numerical cross-checking, committee reporting, and signal lifecycle.

### Locked Phase 3 AI And UI Contracts
- `.planning/phases/03-ai-analysis/03-AI-SPEC.md` — required bounded LangGraph workflow, server-controlled provenance/lifecycle state, structured-output validation, threat boundaries, domain failure modes, and evaluation expectations.
- `.planning/phases/03-ai-analysis/03-UI-SPEC.md` — approved UI contract: existing-surface integration, evidence-first hierarchy, accessibility, responsive behavior, copy, and verification scenarios.
- `.planning/phases/03-ai-analysis/03-DISCUSSION-LOG.md` — human-readable record of the decisions captured in this discussion.

### Prior Phase Contracts And Existing Integration Points
- `.planning/phases/01-core-merger/01-CONTEXT.md` — governed data, local persistence, SSE, Portfolio, and frontend-shell decisions carried forward.
- `.planning/phases/02-factor-and-strategy-research/02-CONTEXT.md` — reproducible research provenance, data-lake and SQLite boundaries, and Backtest workspace conventions.
- `backend/app/tickflow/repository.py` — governed Parquet/DuckDB/Polars data-access boundary for inputs.
- `backend/app/services/quote_service.py` and `backend/app/api/intraday.py` — existing controlled SSE/status-update path.
- `frontend/src/lib/api.ts` — unified typed frontend API contract.
- `frontend/src/components/Layout.tsx` — existing application shell and navigation boundary.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Governed TickFlow repository and enriched indicator pipeline: provide authoritative market, financial, and indicator inputs without creating a second data store.
- Existing SQLite operational-state boundary: suitable for report metadata, source/cross-check records, append-only lifecycle events, and outcome observations.
- Existing stock-analysis, Portfolio, AI host/history surfaces, typed `api.ts`, TanStack Query, and shared SSE pipeline: provide the required object-local entry and independently refreshed report/evidence/history panels.

### Established Patterns
- Backend routes validate Pydantic request/response contracts, delegate to focused services, and return structured error details.
- Time series remain in Parquet and are read through DuckDB/Polars; operational records belong in SQLite and artifacts under the application data directory.
- Frontend pages use the existing typed API client, TanStack Query cache/invalidation, lazy routing, local components, dark-first Tailwind tokens, and semantic native controls.
- New modules should remain separate from the existing large repository, quote-service, and backtest-engine modules.

### Integration Points
- Register an independently activatable `backend/app/analysis/` domain and its FastAPI routes with the existing application lifecycle and local persistence.
- Assemble frozen governed evidence before invoking the bounded analysis graph, then persist validated reports and append-only lifecycle events through the operational-state boundary.
- Extend existing stock-analysis and Portfolio result regions with analysis, evidence, and lifecycle panels; use the AI host/history entry to resume reports rather than create a new router or shell.
- Reuse existing SSE only for controlled generation-progress status, never unvalidated model tokens or lifecycle mutations.

</code_context>

<specifics>
## Specific Ideas

- Source quality and cross-check uncertainty must be visible before an AI narrative. A/B/C labels are attributes of individual sources, not a single overall report grade.
- A signal's lifecycle is governed evidence, not an AI self-assessment: official transitions require a human confirmation and each review remains auditable.
- The latest report is the default reading path, but it never erases older reports or interrupts reading while a replacement is being validated.

</specifics>

<deferred>
## Deferred Ideas

- Autonomous research agents, scoped agent tokens, allowlists, rate limits, idempotent agent jobs, and agent SSE progress belong to Phase 4 `SAFE-01`.
- Attributed external viewpoint tracking and stance-flip performance analysis belong to Phase 4 `ADV-01`.
- Investment-thesis tracking, valuation anchors, and periodic evidence checks beyond this phase's signal lifecycle belong to Phase 5 `THES-01`.
- Automated live broker execution remains out of scope for the project.

</deferred>

---

*Phase: 03-AI Analysis*
*Context gathered: 2026-07-11*
