# AthenaQuant

## What This Is

AthenaQuant is a self-hosted quantitative research platform for individual A-share investors. It brings governed market data, portfolio monitoring, deterministic decision plans, factor research, and AI-assisted analysis into a progressively adoptable system.

## Core Value

An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## Success Metric

Phase 1 starts with a single Docker Compose command and completes the data-sync, position-maintenance, price-rule-trigger, and real-time notification/SSE display loop in one single-container deployment.

## Requirements

### Active

- [ ] An investor can synchronize governed market data, maintain holdings, receive rule-based alerts, and inspect real-time updates from one deployment.
- [ ] An investor can generate an auditable deterministic trade plan and distinguish it from any bounded AI adjustment.
- [ ] A researcher can create and evaluate factors and strategies against reproducible governed data.
- [ ] An investor can assess AI-assisted research using visible data quality, numerical validation, and signal-lifecycle evidence.
- [ ] An operator can use advanced agent and strategy workflows only within explicit authorization and sandbox controls.

### Optional After v1

- Shadow Account strategy distillation and evaluation.
- Investment-thesis tracking and evidence review.
- Kronos time-series forecasting.

### Out of Scope

- Automated live broker order execution.
- A mandatory all-modules deployment; later capabilities remain independently activatable.
- External database or message queue dependencies in the Phase 1 Docker Compose deployment.

## Architecture Constraints

- **Runtime**: Phase 1 runs on Linux through one Docker Compose command as a single container, with no external database or message queue.
- **Data lake first**: Time-series market data is stored in Parquet and accessed through DuckDB and Polars. SQLite stores operational state such as positions, rules, and notification history.
- **Upstream synchronization**: Tickflow and PanWatch integrations retain a practical upstream synchronization path; changes must avoid fork-and-forget ownership.
- **Independent modules**: Integrated capabilities remain separately owned packages or domains that can be activated progressively rather than becoming an inseparable monolith.
- **Decision safety**: Hermes remains a core decision package. AI adjustments are field-bounded, direction-constrained, clamped or vetoed when invalid, audited, and comparable with a deterministic baseline and LLM-free replay.
- **Delivery sequence**: Preserve the source architecture's progression: core merger, factor and strategy research, AI analysis, advanced capabilities, then optional enhancements.

## Decision Status

No architecture implementation decisions were explicitly locked by the intake. The constraints above are required delivery boundaries from the user and source architecture; concrete host-application, package-boundary, and integration choices remain to be validated during phase planning.

## Source Context

- Architecture source: `docs/ARCHITECTURE.md`
- Synthesized intake: `.planning/intel/SYNTHESIS.md`
- No ADR, PRD, or specification supplied a locked implementation decision.

---
*Last updated: 2026-07-10 during roadmap generation from architecture ingest*
