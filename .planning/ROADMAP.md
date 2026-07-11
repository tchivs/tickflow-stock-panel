# Roadmap: AthenaQuant

## Overview

AthenaQuant first delivers a single-container, data-lake-first market and portfolio loop. It then builds reproducible factor research, evidence-grounded AI analysis, and controlled advanced workflows. The final phase preserves the source architecture's optional enhancements without making them prerequisites for the usable v1 system.

## Phases

**Phase Numbering:**

- Integer phases are planned delivery work.
- Decimal phases are reserved for urgent inserted work.

- [x] **Phase 1: Core Merger** - Deliver the self-hosted data, position, monitoring, decision-plan, and real-time notification loop. (completed 2026-07-11)
- [x] **Phase 2: Factor And Strategy Research** - Let researchers create, validate, evaluate, backtest, and compare factors and strategies. (completed 2026-07-11)
- [ ] **Phase 3: AI Analysis** - Make AI-assisted research evidence-grounded, quality-aware, and traceable over a signal's lifecycle.
- [ ] **Phase 4: Advanced Capabilities** - Provide controlled viewpoint tracking, research automation, strategy evolution, agent access, and sandbox execution.
- [ ] **Phase 5: Optional Enhancements** - Add nonessential Shadow Account, thesis-tracking, and forecasting capabilities without blocking v1.

## Phase Details

### Phase 1: Core Merger

**Goal**: Investors can operate the complete data-sync, position-maintenance, price-rule, notification, and real-time display loop from one Docker Compose deployment.
**Depends on**: Nothing (first phase)
**Requirements**: CORE-01, CORE-02, CORE-03, CORE-04, CORE-05, CORE-06, CORE-07, PLAN-01, PLAN-02
**Success Criteria** (what must be TRUE):

  1. Operator can start the application with one Docker Compose command and run an automated check that completes data synchronization, position maintenance, a price-rule trigger, notification delivery, and an SSE display update without an external database or queue.
  2. User can manage accounts and positions, then inspect current position profit and loss alongside synchronized market data.
  3. User can create a position, price, or market monitoring rule, receive a configured notification after a matching event, and review stored alert history.
  4. User can view current market and position changes in the main interface through the shared SSE pipeline.
  5. User can inspect a deterministic trade playbook, distinguish its baseline from bounded audited AI adjustments, and review an AI-free historical replay.

**Plans**: 15/15 plans complete
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Create governed-data Wave 1 contracts.
- [x] 01-13-PLAN.md — Create operational-loop Wave 1 contracts.
- [x] 01-14-PLAN.md — Create decision-safety Wave 1 contracts.
- [x] 01-06-PLAN.md — Obtain human Playwright package-legitimacy approval.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Implement governed fixture synchronization and lake contract validation.
- [x] 01-03-PLAN.md — Add SQLite operational persistence and Portfolio APIs.
- [x] 01-07-PLAN.md — Install approved browser tooling and define browser contracts.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-04-PLAN.md — Add deterministic decision baseline, API, and persistence.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-05-PLAN.md — Extend Monitor, delivery outcomes, and shared SSE.
- [x] 01-15-PLAN.md — Add configured-provider adjustments, audit, and replay guard.

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-12-PLAN.md — Add bounded notification delivery and shared SSE handoff.

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 01-08-PLAN.md — Wire typed frontend operational data, root SSE, and mobile shell.

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 01-09-PLAN.md — Build the responsive Portfolio workspace.
- [x] 01-10-PLAN.md — Extend Monitor and Dashboard decision inspection.

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 01-11-PLAN.md — Prove isolated Compose acceptance and document upstream sync.

**UI hint**: yes

### Phase 2: Factor And Strategy Research

**Goal**: Researchers can turn factor hypotheses into comparable, reproducible evaluations using the governed market-data foundation.
**Depends on**: Phase 1
**Requirements**: FACT-01, FACT-02, FACT-03
**Success Criteria** (what must be TRUE):

  1. Researcher can create a factor with the permitted expression language, validate it before evaluation, store it, and find similar existing factors.
  2. Researcher can convert a natural-language factor hypothesis into a validated expression, run its evaluation, and view IC and RankIC results.
  3. Researcher can run a factor or strategy backtest and compare retained configurations, data inputs, predictions, metrics, artifacts, and model versions across experiments.

**Plans**: 8/8 plans complete

- [x] 02-08-PLAN.md

**Wave 1**

- [x] 02-01-PLAN.md

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md
- [x] 02-03-PLAN.md

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-04-PLAN.md
- [x] 02-06-PLAN.md

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02-05-PLAN.md
- [x] 02-07-PLAN.md

**UI hint**: yes

### Phase 3: AI Analysis

**Goal**: Investors can consume AI-assisted research that makes quality, reasoning, and signal validity visible rather than opaque.
**Depends on**: Phase 2
**Requirements**: ANLY-01, ANLY-02, ANLY-03
**Success Criteria** (what must be TRUE):

  1. User can review market or portfolio analysis labeled with A/B/C source-quality context and see whether material numbers were cross-checked or unresolved.
  2. User can inspect a multi-perspective report with visible scoring rationale, applicable valuation analysis, and an investment-committee memo.
  3. User can view a signal's current lifecycle status and its recorded evolution or outcome over time.

**Plans**: TBD
**UI hint**: yes

### Phase 4: Advanced Capabilities

**Goal**: Researchers and operators can use advanced research and automation workflows within explicit promotion, authorization, audit, and execution safeguards.
**Depends on**: Phase 3
**Requirements**: ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02
**Success Criteria** (what must be TRUE):

  1. User can review an attributed market viewpoint, identify a material stance change, and inspect its confidence-aware performance result.
  2. Researcher can progress a hypothesis through a sandboxed experiment and recorded feedback, then evaluate an evolved strategy for promotion through explicit gates.
  3. Operator can start an authorized agent job for an allowed market and instrument, observe SSE progress, and inspect its audit summary; unauthorized, out-of-allowlist, or rate-limited requests are rejected before work starts.
  4. Researcher can submit a custom strategy only when its machine-readable contract, AST, imports, timeout, and memory constraints pass validation, and can review the constrained run's result or failure record.

**Plans**: TBD

### Phase 5: Optional Enhancements

**Goal**: Investors and researchers can optionally extend the platform with strategy distillation, thesis evidence, and forecast capabilities without changing the completed v1 operating loop.
**Depends on**: Phase 4
**Requirements**: SHDW-01, THES-01, FORE-01
**Success Criteria** (what must be TRUE):

  1. User can create and evaluate a Shadow Account-derived strategy from their actual trading logs.
  2. User can view an investment thesis with its valuation anchor, invalidation conditions, and periodic evidence checks.
  3. Researcher can request and inspect a time-series forecast that includes quantiles, sampled paths, and the associated model checkpoint.

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:** Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 (optional)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Merger | 15/15 | Complete    | 2026-07-11 |
| 2. Factor And Strategy Research | 8/8 | Complete   | 2026-07-11 |
| 3. AI Analysis | 0/TBD | Not started | - |
| 4. Advanced Capabilities | 0/TBD | Not started | - |
| 5. Optional Enhancements | 0/TBD | Optional | - |
