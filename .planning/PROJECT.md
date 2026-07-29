# AthenaQuant

## What This Is

AthenaQuant is a shipped, self-hosted quantitative research platform for individual A-share investors. Its v1.0 MVP unifies governed market data, portfolio monitoring, deterministic decision plans, factor and strategy research, evidence-grounded AI analysis, controlled advanced workflows, and independently activatable optional research modules.

## Core Value

An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## Current Milestone: v1.1 Operational Hardening

**Goal:** Make release evidence routinely reproducible across supported hosts, remove avoidable runtime and data-stack warnings, formalize the operator-controlled optional-model supply path, and add durable visual-regression evidence — without weakening v1.0 fail-closed safety boundaries.

**Target features:**
- Reproducible release evidence from current Windows and Linux environments without historical attestations
- Runtime, data-stack, and frontend validation free of avoidable deprecation and sortedness warnings
- Optional local-model supply stays fail-closed with an explicit, documented, testable operator approval path
- Durable screenshot-based visual regression for critical desktop and 375px responsive workflows

## Success Metric

The v1.0 release is successful when all 23 requirements are verified end to end, the five phases pass Nyquist validation, and one provenance-bound final gate proves the backend and browser contracts against the frozen release source. This was achieved on 2026-07-27.

## Requirements

### Active

- [ ] Release evidence is reproducible from current Windows and Linux environments without relying on historical attestations.
- [ ] Runtime, data-stack, and frontend validation complete without avoidable deprecation or sortedness warnings.
- [ ] Optional local-model supply remains fail-closed while an explicit operator approval path is documented and testable.
- [ ] Critical responsive workflows have durable screenshot-based visual regression evidence.

### Validated in v1.0

- [x] An investor can synchronize governed market data, maintain holdings, receive rule-based alerts, and inspect real-time updates from one deployment.
- [x] An investor can generate an auditable deterministic trade plan and distinguish it from bounded AI adjustments.
- [x] A researcher can create and evaluate factors and strategies against reproducible governed data.
- [x] An investor can assess AI-assisted research using visible data quality, numerical validation, and signal-lifecycle evidence.
- [x] An operator can use advanced agent and strategy workflows only within explicit authorization and sandbox controls.
- [x] Shadow Account strategy distillation and evaluation is independently activatable and research-only.
- [x] Investment-thesis tracking and evidence review preserves immutable lineage and human authority.
- [x] Kronos forecasting is local-only, provenance-bound, principal-scoped, and fail-closed when supply identity is incomplete.

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

v1.0 validated the host architecture and locked its safety boundaries: one FastAPI host, Parquet/DuckDB/Polars governed data, SQLite operational state, server-owned authorization and identity, append-only audit facts, bounded AI proposals, research-only promotion, and independently activatable optional modules. Future milestones may harden or simplify these seams but must not weaken their fail-closed behavior.

## Source Context

- Architecture source: `docs/ARCHITECTURE.md`
- Synthesized intake: `.planning/intel/SYNTHESIS.md`
- Shipped milestone archive: `.planning/milestones/v1.0-ROADMAP.md`
- Canonical release audit: `.planning/milestones/v1.0-MILESTONE-AUDIT.md`

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-29 — started milestone v1.1 Operational Hardening*
