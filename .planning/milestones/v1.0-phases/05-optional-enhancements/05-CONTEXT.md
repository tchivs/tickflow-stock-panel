# Phase 05: Optional Enhancements - Context

**Gathered:** 2026-07-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver three independently activatable, optional extensions on the completed v1 loop: derive an explainable strategy candidate from immutable actual-trading-log evidence; track versioned investment theses with valuation, invalidation, and scheduled evidence review; and run reproducible Kronos forecasts over governed A-share daily K-lines with visible probabilistic outputs and checkpoint provenance.

This phase does not alter the completed v1 operating loop, add automated broker execution, make forecasts or thesis checks authoritative trading actions, require every optional module at deployment, introduce a second data lake or external database/queue, or permit opaque evidence rewriting.

</domain>

<decisions>
## Implementation Decisions

### Shadow Account Strategy Distillation
- **D-01:** Actual trades enter through imported local execution logs. The initial workflow does not depend on broker connectivity or manual trade-by-trade entry.
- **D-02:** Every import is an immutable, attributable batch. Corrections or re-imports append a new batch and preserve the earlier evidence rather than editing or overwriting account history.
- **D-03:** Distillation produces an explainable strategy candidate whose inferred rules, features, parameters, source batches, and limitations are reviewable. A black-box behavior clone is not an acceptable retained result.
- **D-04:** Candidate retention requires frozen evidence plus explicit in-sample and out-of-sample evaluation. Full-sample fit or a single summary metric cannot establish eligibility, and retention does not activate monitoring or execution.

### Investment Thesis Lifecycle
- **D-05:** A thesis is immutable and versioned. New evidence or a changed core judgment creates a new version linked to its predecessor; prior valuation and reasoning remain auditable.
- **D-06:** Valuation anchors contain explicit assumptions and a value range. A single target price or link to an AI report is insufficient as the canonical anchor.
- **D-07:** Invalidation conditions are structured and machine-checkable. When evidence matches a condition, the system creates a pending, evidence-linked conclusion; only the user can confirm that the thesis is invalidated.
- **D-08:** Evidence-check cadence is configured per condition rather than by one global schedule. Each completed check appends its evidence, result, and time to the active thesis version without rewriting earlier checks.

### Kronos Forecast Delivery
- **D-09:** The first forecast workflow is object-bound to one A-share instrument and uses governed daily OHLCV data. It exposes bounded 5-, 20-, and 60-trading-day horizons rather than adding intraday or portfolio-batch forecasting.
- **D-10:** Every result visibly presents fixed P10/P50/P90 quantiles and a bounded set of inspectable sampled paths. The interface may emphasize an uncertainty band, but it cannot hide the sampled paths required by `FORE-01`.
- **D-11:** Models come from a deployment-owned approved checkpoint catalog. A run freezes the selected model and tokenizer identities, immutable revisions, and integrity digests; it never follows an unpinned remote `latest` checkpoint.
- **D-12:** Forecasts are immutable research records containing the governed input fingerprint, resolved horizon and sampling configuration, checkpoint provenance, quantiles, and sampled paths. As horizons mature, actual outcomes and calibration/error evidence append to the original record; forecasts do not automatically mutate a thesis, strategy, decision plan, monitor, or market action.

### Claude's Discretion
- Exact import formats and field mapping UI, duplicate-trade identity rules, distillation algorithm, candidate schema, and evaluation metrics are open to planning provided D-01 through D-04 remain enforceable and auditable.
- Exact thesis schema, supported valuation assumptions, condition language, scheduler mechanism, and evidence-check presentation are open provided versioning and user confirmation remain authoritative.
- Exact Kronos package boundary, optional dependency packaging, approved-checkpoint manifest format, model capacity defaults, sample count, resource limits, artifact format, chart composition, and asynchronous task mechanics are open provided D-09 through D-12 and the single-container/independent-module constraints hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product Scope And Requirements
- `.planning/PROJECT.md` — defines optional-after-v1 scope, single-container/data-lake constraints, independent modules, and the no-live-execution boundary.
- `.planning/REQUIREMENTS.md` — defines `SHDW-01`, `THES-01`, and `FORE-01` plus project-wide exclusions.
- `.planning/ROADMAP.md` — defines the Phase 05 goal and its three observable success criteria.
- `docs/ARCHITECTURE.md` — identifies Shadow Account, thesis tracking, and Kronos as optional Phase 05 capabilities and specifies Kronos quantile/path/checkpoint delivery.

### Carried-Forward Research And Governance Contracts
- `.planning/phases/02-factor-and-strategy-research/02-CONTEXT.md` — immutable experiment provenance, governed inputs, comparison warnings, registered-strategy boundaries, and existing Backtest integration.
- `.planning/phases/03-ai-analysis/03-CONTEXT.md` — object-first analysis, append-only evidence, human-confirmed lifecycle changes, and server-authoritative research records.
- `.planning/phases/04-advanced-capabilities/04-CONTEXT.md` — frozen experiment evidence, explicit promotion gates, bounded execution, sandbox controls, and no automatic activation.

### External Forecast Contract
- `https://github.com/shiyu-coder/Kronos` — official model family, tokenizer/model pairing, OHLCV input, context limits, sampling parameters, and checkpoint loading API. Pin a reviewed upstream revision during planning/implementation rather than consuming a moving branch implicitly.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/tickflow/repository.py` and the governed Parquet/DuckDB/Polars layer can supply daily OHLCV, historical outcomes, and stable data identities without a second market-data store.
- `backend/app/backtest/strategy.py`, `backend/app/backtest/frozen_panel.py`, and Phase 2 experiment records provide frozen-panel, provenance, evaluation, and artifact patterns for Shadow candidates and forecast records.
- Phase 3 analysis lifecycle and Phase 4 advanced repositories/services provide append-only version, pending-confirmation, immutable run, and safe projection precedents for thesis checks and forecast evaluation.
- `frontend/src/lib/api.ts`, TanStack Query, `frontend/src/lib/backtestTask.ts`, and the existing Backtest/Analysis workspaces provide typed request, task progress, reconnection, object-scoped cache, and result-display paths.

### Established Patterns
- Time series stay in governed Parquet and are computed with DuckDB/Polars; operational metadata, version lineage, schedules, and audit facts stay in SQLite with managed local artifacts.
- Browser requests select bounded inputs, while the server resolves authority, source identity, data fingerprints, evaluation evidence, checkpoint provenance, and lifecycle state.
- New responsibilities belong in separate optional domains registered through the existing FastAPI lifespan and frontend workspaces; do not enlarge the large repository, backtest engine, or API client into a second monolith.
- Long-running work uses bounded server tasks and controlled SSE projections. Failure, retry, and correction append new attributable records instead of rewriting terminal evidence.

### Integration Points
- Add a Shadow import/distillation domain that converts validated immutable batches into candidate specifications and delegates evaluation to existing governed backtest contracts.
- Add thesis version, condition, schedule, check, and confirmation services to the established operational-state lifecycle, then surface them in the active stock-analysis object rather than a parallel shell.
- Add Kronos as an optional forecast adapter behind a deployment-owned checkpoint catalog and bounded task service; connect governed K-lines at input and append actual-outcome evaluation when each horizon matures.
- Extend the unified typed API/query layer and existing Backtest/Analysis surfaces with module-aware loading, unavailable states, immutable history, and object-local invalidation.
- No Kronos implementation currently exists in the indexed application; planning must introduce the adapter and packaging boundary rather than assuming an existing forecast service.

</code_context>

<specifics>
## Specific Ideas

- Shadow Account is evidence imported from actual local trading logs, not a broker-control feature or a manually reconstructed paper account.
- Thesis invalidation is a reviewable evidence event: automation may detect and propose, but cannot silently change the official thesis state.
- Kronos uncertainty must remain inspectable: P10/P50/P90 and sampled paths are first-class results, with exact checkpoint provenance and later calibration evidence.
- All three enhancements remain optional and must degrade cleanly when their dependencies or checkpoints are not installed.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 05 scope.

</deferred>

---

*Phase: 05-Optional Enhancements*
*Context gathered: 2026-07-15*
