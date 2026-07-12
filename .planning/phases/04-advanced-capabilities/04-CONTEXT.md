# Phase 4: Advanced Capabilities - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver controlled advanced research and automation workflows: attributed market viewpoints with auditable stance changes and confidence-aware outcomes; hypothesis experiments with frozen specifications and recorded feedback; strategy evolution with explicit promotion gates; and agent/custom-strategy execution constrained by authorization, audit, and sandbox safeguards.

The phase extends the governed research, analysis, strategy, operational-state, and shared-SSE foundation. It does not add live broker execution, a second deployment or datastore, unrestricted code execution, autonomous promotion, or automatic activation of a promoted strategy.

</domain>

<decisions>
## Implementation Decisions

### Attributed Viewpoints And Confidence-Aware Performance
- **D-01:** A tracked viewpoint is an immutable version identified by a controlled source profile, market/instrument scope, and publication time. Every version retains its evidence, conclusion, and confidence; later changes never overwrite it.
- **D-02:** A material stance change is detected from structured-field thresholds across direction, rating/conclusion, target range, horizon, or confidence. Minor wording and evidence-only revisions remain visible revisions but do not become stance changes.
- **D-03:** Each viewpoint version freezes a 20-, 60-, or 120-trading-day evaluation window, benchmark, and outcome metric at creation. The benchmark defaults by asset type and may be explicitly overridden only from an allowed set; the chosen benchmark remains part of the immutable record.
- **D-04:** Performance presents confidence calibration in low/medium/high buckets with hit rate, relative return, sample count, and coverage period. Insufficient samples must be marked rather than summarized as a reliable conclusion.
- **D-05:** Corrections append a new version with a correction reason; original content remains auditable. Missing prices, benchmarks, or unsupported scope produce an explicit unevaluable outcome, never an inferred, zero, or silently excluded result.

### Hypothesis Experiment And Feedback Cycle
- **D-06:** A hypothesis becomes an immutable experiment-specification version before its sandbox run. The specification records the hypothesis, data scope, method, metrics, and success/failure criteria.
- **D-07:** Runs reference a governed-data snapshot/fingerprint and execution manifest containing strategy/factor version, parameters, resource limits, and environment information; they do not copy raw market data into a second store.
- **D-08:** Research feedback is an append-only structured conclusion of supported, refuted, inconclusive, or needs-replication, linked to the run, metrics, artifacts, and explanatory notes.
- **D-09:** Validation, timeout, and resource-limit failures remain auditable with their constraint-trigger reason and sanitized diagnostics. A retry is a new run and, where configuration changes, a new specification version.

### Strategy Evolution And Promotion
- **D-10:** Strategy candidates arise only through constrained mutations of validated research assets. Each candidate persists parent version, mutation operation, seed, and resolved configuration.
- **D-11:** Promotion requires explicit gates for contract and sandbox safety, complete provenance, in-sample and out-of-sample evidence, robustness, and cost assumptions. A single aggregate ranking cannot substitute for these gates.
- **D-12:** After automated gates pass, a researcher must explicitly approve promotion with an auditable time and rationale. Promotion creates a reusable registered research-strategy version only; it does not activate monitoring, create a decision plan, or execute a market action.

### Scoped Agent Authorization
- **D-13:** Agent workflows require short-lived, server-validated scoped tokens that authorize only named task types and approved market/instrument ranges.
- **D-14:** The operator owns the authoritative allowlist policy. Server-side token issuance binds the permitted intersection to the authorization record, and task creation checks the request target again.
- **D-15:** Unauthorized, out-of-allowlist, and rate-limited requests are rejected before a runnable task or SSE work begins. They retain a security audit summary that explains the rejection without exposing sensitive policy detail.
- **D-16:** Pending agent tasks revalidate current token and allowlist policy immediately before execution. A revoked or newly out-of-scope request is rejected and audited rather than running under its original creation-time authorization.

### the agent's Discretion
- Exact SQLite schema, migration mechanism, API route names, source-profile ingestion workflow, structured-field threshold values, supported benchmark catalog, and UI composition remain open, provided immutable lineage, visible uncertainty, and evaluability rules are preserved.
- The planner determines detailed idempotency, rate-limit accounting, SSE event shapes, audit-summary projection, machine-readable custom-strategy contract, AST/import policy, process/container isolation, timeout/memory values, and diagnostic redaction. These designs MUST satisfy `SAFE-01` and `SAFE-02`, enforce checks before execution, and preserve the established single-container, local operational-state boundary.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product Scope And Phase Requirements
- `.planning/PROJECT.md` — single-container deployment, Parquet/DuckDB/Polars time-series, SQLite operational state, independent-module, and decision-safety boundaries.
- `.planning/REQUIREMENTS.md` — pending Phase 4 requirements `ADV-01` through `ADV-03` and `SAFE-01` through `SAFE-02`; also defines non-goals.
- `.planning/ROADMAP.md` — Phase 4 goal, fixed scope, and four observable success criteria.
- `docs/ARCHITECTURE.md` — source architecture and intended progressive delivery sequence for advanced research, automation, and sandbox safeguards.

### Prior-Phase Contracts
- `.planning/phases/01-core-merger/01-CONTEXT.md` — governed-data and operational-state boundaries, existing shared SSE, authentication host, local Compose deployment, and portfolio/monitor conventions.
- `.planning/phases/02-factor-and-strategy-research/02-CONTEXT.md` — restricted research execution precedent, immutable experiment provenance, factor/strategy result contracts, and explicit Phase 4 custom-strategy/evolution boundary.
- `.planning/phases/03-ai-analysis/03-CONTEXT.md` — immutable evidence and lifecycle governance, server-held authorization, SQLite append-only records, object-local UI integration, typed API projections, and controlled SSE progress.

### Existing Integration Points
- `backend/app/main.py` — FastAPI lifespan, authorization middleware, and module registration boundary.
- `backend/app/services/auth.py` and `backend/app/api/auth.py` — existing session/authentication conventions to extend without treating a client identity as authority.
- `backend/app/tickflow/repository.py` — sole governed Parquet/DuckDB/Polars data-access boundary.
- `backend/app/backtest/engine.py`, `backend/app/backtest/strategy.py`, and `backend/app/api/backtest.py` — existing registered-strategy execution, bounded backtest work, and result contracts.
- `backend/app/services/quote_service.py` and `backend/app/api/intraday.py` — existing shared SSE broadcast and subscription boundary.
- `frontend/src/lib/api.ts`, `frontend/src/pages/Backtest.tsx`, `frontend/src/pages/Analysis.tsx`, and `frontend/src/components/Layout.tsx` — unified typed client, established research/analysis surfaces, and application-shell integration points.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Governed TickFlow repository, enriched indicator pipeline, and existing backtest services can supply research inputs and evaluation evidence without a second market-data store.
- SQLite operational-state persistence and Phase 2/3 immutable provenance patterns provide the natural home for viewpoint versions, experiment specifications/runs, promotion decisions, authorization records, and audit summaries.
- Existing strategy result/task conventions, shared SSE path, FastAPI/Pydantic request contracts, typed `api.ts`, TanStack Query, and Backtest/Analysis workspaces can support controlled task status and result review.

### Established Patterns
- Time series remain in Parquet and are accessed through DuckDB/Polars; operational metadata and append-only audit history belong in SQLite and local managed artifacts.
- New behavior should be added as independently activatable domains rather than extending the large repository, backtest engine, quote service, or API client indiscriminately.
- The server derives and validates authorization and persisted scope; client-supplied identifiers are not authority. SSE communicates controlled progress, not unvalidated execution output or mutations.
- The app is a single-user, single-container deployment with bounded resources. This rules out requiring an external queue, database, or multi-approver service for Phase 4.

### Integration Points
- Register separate advanced-capability domains and FastAPI routes through the existing application lifecycle, persistence initialization, and authorization middleware.
- Reuse governed repository/backtest inputs to create frozen viewpoint and experiment records, then append outcomes, feedback, promotion, and audit events through SQLite.
- Extend existing Backtest and Analysis workspaces plus the unified API/SSE conventions instead of introducing a parallel shell or data-fetching model.

</code_context>

<specifics>
## Specific Ideas

- Historical viewpoint, experiment, and promotion records are evidence, not mutable “latest” records. Corrections and retries add attributable versions rather than rewrite prior outcomes.
- Confidence is useful only when its calibration, sample count, and coverage limits are visible.
- Promotion means a controlled research asset, never automatic monitoring, investment recommendation, or broker action.
- Authorization is enforced at creation and immediately before execution so policy revocation takes effect before a pending job starts.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 4 scope.

</deferred>

---

*Phase: 04-Advanced Capabilities*
*Context gathered: 2026-07-12*
