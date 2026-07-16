# Requirements: AthenaQuant

**Defined:** 2026-07-10
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## v1 Requirements

### Core Merger

- [x] **CORE-01**: User can synchronize A-share instruments, daily prices, adjustment factors, financial data, and enriched indicators into the governed Parquet data lake.
- [x] **CORE-02**: Operator can verify the time-series data contract, including primary keys, time semantics, repair windows, and schema-drift checks for synchronized data.
- [x] **CORE-03**: User can manage accounts and positions and view current position-level profit and loss.
- [x] **CORE-04**: User can define position, price, and market monitoring rules; receive a notification when a rule matches; and review persisted alert history.
- [x] **CORE-05**: User can view current market and position updates through the shared real-time SSE pipeline.
- [x] **CORE-06**: Operator can start the Phase 1 workflow with one Docker Compose command and run an automated check covering data sync, position maintenance, a price-rule trigger, notification delivery, and SSE display without an external database or queue.
- [x] **CORE-07**: Operator can update each adopted upstream integration through a documented synchronization path without replacing the shared data-lake or operational-state boundaries.
- [x] **PLAN-01**: User can generate deterministic market state, quality-screened pools, and a playbook with entry range, stop, target, and position sizing.
- [x] **PLAN-02**: User can compare a deterministic playbook baseline with field-bounded, audited AI adjustments and replay historical decisions with AI influence disabled.

### Factor And Strategy Research

- [x] **FACT-01**: Researcher can define a factor through a restricted expression language, store it, find similar stored factors, and evaluate it with IC and RankIC metrics.
- [x] **FACT-02**: Researcher can turn a natural-language factor hypothesis into a validated factor expression and backtest it before it is retained for comparison.
- [x] **FACT-03**: Researcher can run factor or strategy experiments and compare retained configuration, data inputs, predictions, metrics, artifacts, and registered model versions.

### AI Analysis

- [x] **ANLY-01**: User can review AI-assisted market or portfolio analysis whose depth reflects A/B/C source-quality grading and whose material numbers are cross-checked across sources.
- [x] **ANLY-02**: User can inspect a multi-perspective investment report with its scoring rationale, valuation analysis when applicable, and an investment-committee memo.
- [x] **ANLY-03**: User can track a research signal as strengthened, weakened, falsified, or priced in and review its outcome over time.

### Advanced Capabilities

- [x] **ADV-01**: User can track attributed market viewpoints, identify material stance changes, and review confidence-aware performance results.
- [x] **ADV-02**: Researcher can progress a hypothesis through an experiment specification, sandbox run, and recorded feedback cycle.
- [x] **ADV-03**: Researcher can evaluate and promote an evolved strategy from research asset through mutation, evaluation, and explicit promotion gates.
- [x] **SAFE-01**: Operator can invoke agent workflows through scoped tokens, market and instrument allowlists, rate limits, idempotent jobs, audit summaries, and SSE progress updates.
- [x] **SAFE-02**: Researcher can validate and run custom strategies only through a machine-readable contract and sandbox with AST, import, timeout, and memory controls.

## v2 Requirements

### Optional Enhancements

- [x] **SHDW-01**: User can derive and evaluate strategies from a Shadow Account built from actual trading logs.
- [x] **THES-01**: User can track investment theses, valuation anchors, invalidation conditions, and periodic evidence checks.
- [x] **FORE-01**: Researcher can request Kronos time-series forecasts with quantiles, sampled paths, and model checkpoints.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automated live broker order execution | v1 is a research, decision-planning, and monitoring product. Live execution needs separately approved safety and broker-integration scope. |
| External PostgreSQL or message queue in Phase 1 | The target runtime is a single Docker Compose container backed by Parquet and SQLite. |
| Mandatory deployment of all modules | The architecture requires independently activatable modules and a usable Phase 1 baseline. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 1 | Complete |
| CORE-02 | Phase 1 | Complete |
| CORE-03 | Phase 1 | Complete |
| CORE-04 | Phase 1 | Complete |
| CORE-05 | Phase 1 | Complete |
| CORE-06 | Phase 1 | Complete |
| CORE-07 | Phase 1 | Complete |
| PLAN-01 | Phase 1 | Complete |
| PLAN-02 | Phase 1 | Complete |
| FACT-01 | Phase 2 | Complete |
| FACT-02 | Phase 2 | Complete |
| FACT-03 | Phase 2 | Complete |
| ANLY-01 | Phase 3 | Complete |
| ANLY-02 | Phase 3 | Complete |
| ANLY-03 | Phase 3 | Complete |
| ADV-01 | Phase 4 | Complete |
| ADV-02 | Phase 4 | Complete |
| ADV-03 | Phase 4 | Complete |
| SAFE-01 | Phase 4 | Complete |
| SAFE-02 | Phase 4 | Complete |
| SHDW-01 | Phase 5 | Optional v2 |
| THES-01 | Phase 5 | Optional v2 |
| FORE-01 | Phase 5 | Optional v2 |

**Coverage:**

- v1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0
- Optional v2 requirements: 3, reserved for Phase 5

---
*Last updated: 2026-07-10 during roadmap generation from architecture ingest*
