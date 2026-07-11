# Phase 3: AI Analysis - Research

**Researched:** 2026-07-11
**Domain:** Evidence-grounded, bounded AI investment research and governed signal lifecycle
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

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

### Deferred Ideas (OUT OF SCOPE)
- Autonomous research agents, scoped agent tokens, allowlists, rate limits, idempotent agent jobs, and agent SSE progress belong to Phase 4 `SAFE-01`.
- Attributed external viewpoint tracking and stance-flip performance analysis belong to Phase 4 `ADV-01`.
- Investment-thesis tracking, valuation anchors, and periodic evidence checks beyond this phase's signal lifecycle belong to Phase 5 `THES-01`.
- Automated live broker execution remains out of scope for the project.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ANLY-01 | User can review AI-assisted market or portfolio analysis whose depth reflects A/B/C source-quality grading and whose material numbers are cross-checked across sources. | Frozen `SourceRecord`/material-number contracts, deterministic grading and cross-check service, server-owned evidence APIs, evidence-first UI panels. |
| ANLY-02 | User can inspect a multi-perspective investment report with its scoring rationale, valuation analysis when applicable, and an investment-committee memo. | Fixed two-node LangGraph, `GeneratedAnalysis` schema, citation whitelist validation, valuation applicability invariant, report detail UI. |
| ANLY-03 | User can track a research signal as strengthened, weakened, falsified, or priced in and review its outcome over time. | Append-only lifecycle repository/events, explicit human confirmation endpoint, immutable observation plans, independently queried lifecycle/outcome panel. |
</phase_requirements>

## Summary

Phase 3 must be implemented as a new, independently activatable `backend/app/analysis/` domain that reads governed Parquet/DuckDB/Polars inputs through the existing repository and persists operational metadata in the existing SQLite database. The existing application already starts `OperationalRepository` and `ResearchRepository` against the same `operational.db`, and registers focused FastAPI routers in `backend/app/main.py`; this is the correct ownership pattern for the new domain. [VERIFIED: codebase]

The present stock and financial AI flows stream free-form Markdown and permit client-triggered report saving/deletion. They are useful entry-point UX, but cannot be used as the authoritative Phase 3 contract because provenance, material-number cross-check state, lifecycle state, and immutable version history would remain client-controlled or absent. Phase 3 must instead persist only a server-validated `AnalysisReport`, expose separately queryable report/evidence/lifecycle resources, and let the UI render those resources without inferring evidence facts. [VERIFIED: codebase]

**Primary recommendation:** Implement one fixed `START -> validate_frozen_input -> generate_validated_body -> END` LangGraph workflow behind an `AnalysisService`; prepare evidence and apply lifecycle changes outside the graph, and make SQLite append-only records the sole source of truth. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] [CITED: https://docs.langchain.com/oss/python/langgraph/graph-api]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Governed market, indicator, and financial input collection | API / Backend | Database / Storage | Use the existing TickFlow repository and financial data readers; browsers never assemble evidence. [VERIFIED: codebase] |
| A/B/C grading, independence detection, and material-number cross-check | API / Backend | Database / Storage | These are deterministic domain rules whose results must be frozen and auditable before generation. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Fixed report-generation workflow | API / Backend | Database / Storage | The graph validates frozen state and produces only a structured body; checkpoint data is not lifecycle truth. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] |
| Report/evidence/lifecycle persistence and version history | Database / Storage | API / Backend | Existing architecture reserves SQLite for operational state and immutable research metadata. [VERIFIED: codebase] |
| Lifecycle proposal, confirmation, and outcome recording | API / Backend | Database / Storage | Official state requires domain rule evaluation and a human confirmation transaction, never model output. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |
| Report/evidence/history rendering and local navigation state | Browser / Client | API / Backend | The frontend uses typed `api.ts`, TanStack Query, and local state; it renders server facts and preserves panels independently. [VERIFIED: codebase] |
| Generation progress | Frontend Server (SSR) | API / Backend | This SPA has no SSR tier; use the existing controlled application status/SSE route only for coarse server-owned progress, never token output. [VERIFIED: codebase] |

## Existing Integration Map

| Boundary | Exact module(s) | Phase 3 use | Do not do |
|----------|-----------------|-------------|-----------|
| Governed inputs | `backend/app/tickflow/repository.py`, `backend/app/api/financials.py`, `backend/app/services/financial_sync.py` | Build read-only evidence snapshots from daily/enriched series and latest financial tables. [VERIFIED: codebase] | Do not create a second market-data store or accept client-supplied financial facts. [CITED: .planning/PROJECT.md] |
| SQLite migration and immutable repository style | `backend/app/operational/migrations.py`, `backend/app/research/repository.py` | Add migrations to the shared sequence and an `AnalysisRepository` with short-lived parameterized connections. [VERIFIED: codebase] | Do not write analysis metadata to Parquet or rewrite report/event rows. [CITED: .planning/PROJECT.md] |
| AI provider settings/secrets | `backend/app/services/ai_provider.py`, `backend/app/decision/ai_review.py` | Reuse server-held OpenAI-compatible configuration and injectable offline transport pattern. [VERIFIED: codebase] | Do not accept model URL, API key, provider, prompt, or tool configuration in an analysis request. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Application lifecycle/router | `backend/app/main.py` | Instantiate `AnalysisRepository`, `AnalysisService`, and optional persistent graph saver during lifespan; include `analysis.router`. [VERIFIED: codebase] | Do not add a parallel application, worker, queue, or external database. [CITED: .planning/PROJECT.md] |
| Stock entry and history | `frontend/src/pages/StockAnalysis.tsx`, `frontend/src/lib/stockAnalysisStore.ts` | Replace/extend its CTA and history path to open a server-backed evidence report for the selected symbol. [VERIFIED: codebase] | Do not keep client-generated Markdown as the Phase 3 record or allow report deletion. [VERIFIED: codebase] |
| Financial/global host | `frontend/src/components/financials/AiAnalysisHost.tsx`, `frontend/src/components/Layout.tsx` | Use the existing global host/history entry to resume or review a report. [VERIFIED: codebase] | Do not introduce another top-level route, shell, or report modal. [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md] |
| Portfolio entry | `frontend/src/pages/Portfolio.tsx`, `backend/app/api/portfolio.py` | Add account/portfolio-local analysis CTA and report region using selected `account_id`. [VERIFIED: codebase] | Do not infer holdings/evidence in the browser or remove account-scoped query behavior. [VERIFIED: codebase] |
| Typed frontend data | `frontend/src/lib/api.ts`, `frontend/src/lib/queryKeys.ts` | Add interfaces and `QK.analysis*` factories, then use independent TanStack queries per panel. [VERIFIED: codebase] | Do not call `fetch` directly from components or make one query clear sibling panels. [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md] |
| Existing controlled progress | `backend/app/api/intraday.py`, `backend/app/services/quote_service.py`, `frontend/src/lib/useQuoteStream.ts` | Add a scoped `analysis_progress` status field/event only after server persistence of a safe progress state. [VERIFIED: codebase] | Do not stream model tokens, raw prompts, raw evidence, or lifecycle mutations. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic` | Existing `>=2.7,<3`; installed environment reports `2.13.4` | Validate requests, frozen evidence, generated body, and final server envelope. [VERIFIED: codebase] | `ConfigDict(extra='forbid')`, `model_validator(mode='after')`, and `model_validate_json()` support strict schemas and cross-field invariants. [CITED: https://docs.pydantic.dev/latest/concepts/models/] [CITED: https://docs.pydantic.dev/latest/concepts/validators/] |
| `langgraph` [WARNING: flagged as suspicious — verify before using.] | Pin exact compatible `1.2.9` after the approval checkpoint | Compile the fixed typed DAG and call it asynchronously. [CITED: https://docs.langchain.com/oss/python/langgraph/graph-api] | Official docs support named `StateGraph` nodes, explicit `START`/`END` edges, checkpointers, and per-run `thread_id`. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] |
| `langgraph-checkpoint-sqlite` [WARNING: flagged as suspicious — verify before using.] | Pin exact compatible `3.1.0` after the approval checkpoint | Persist local graph checkpoints in a dedicated SQLite file. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] | Official LangGraph documentation identifies it as the separately installed SQLite saver. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] |
| Existing `openai` SDK | Existing `>=1.40` | Keep OpenAI-compatible transport behind `app.services.ai_provider`. [VERIFIED: codebase] | Existing configuration, error sanitization, async client construction, and offline-injected test seams should be retained. [VERIFIED: codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `langchain-openai` [WARNING: flagged as suspicious — verify before using.] | Registry current `1.3.5`; do not add by default | Optional `with_structured_output()` adapter. [CITED: https://docs.langchain.com/oss/python/langchain/models] | Add only if an approved provider passes startup structured-output smoke tests; the direct existing SDK adapter plus `GeneratedAnalysis.model_validate_json()` is the default. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Existing `pytest` / `pytest-asyncio` | Existing dev dependencies `>=8.0` / `>=0.23` | Unit, repository, graph/service, and FastAPI contract tests. [VERIFIED: codebase] | Reuse the current temp SQLite and injected async gateway pattern. [VERIFIED: codebase] |
| Existing Playwright | `@playwright/test` `1.61.1` in frontend lock manifest | Evidence-first UI and keyboard/responsive end-to-end tests. [VERIFIED: codebase] | Extend the existing fixture-routed desktop workflow and add mobile viewport coverage. [VERIFIED: codebase] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Fixed LangGraph workflow | Direct service call sequence | A direct sequence is simpler but violates the locked LangGraph framework decision. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Direct SDK structured JSON adapter | `langchain-openai` | The direct adapter avoids an additional dependency and preserves the tested existing OpenAI-compatible boundary; it must still validate raw JSON with Pydantic. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Dedicated `analysis_checkpoints.db` | Shared `operational.db` for checkpoints | Separate checkpoint storage avoids mixing replayable graph state with append-only domain truth and reduces coupling; authoritative reports/events remain in `operational.db`. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |

**Installation:**
```bash
# HUMAN CHECKPOINT REQUIRED: both packages have a SUS verdict in the legitimacy audit.
cd backend
uv add "langgraph==1.2.9" "langgraph-checkpoint-sqlite==3.1.0"
uv lock
```

**Version verification:** PyPI reported `langgraph` `1.2.9` (published 2026-07-10), `langgraph-checkpoint-sqlite` `3.1.0` (published 2026-05-12), and `langchain-openai` `1.3.5` (published 2026-07-10). These registry observations must be rechecked at implementation time and the resolved compatibility set committed to `backend/uv.lock`. [VERIFIED: PyPI]

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `langgraph` | PyPI | Existing project under active releases; latest published 2026-07-10 | unknown to seam | `github.com/langchain-ai/langgraph` | SUS | Flagged — planner must add `checkpoint:human-verify` before install. [VERIFIED: PyPI] |
| `langgraph-checkpoint-sqlite` | PyPI | Existing project; latest published 2026-05-12 | unknown to seam | `github.com/langchain-ai/langgraph` | SUS | Flagged — planner must add `checkpoint:human-verify` before install. [VERIFIED: PyPI] |
| `langchain-openai` | PyPI | Existing project; latest published 2026-07-10 | unknown to seam | official LangChain OpenAI integration docs | SUS | Not in default install; if selected after smoke testing, planner must add `checkpoint:human-verify`. [VERIFIED: PyPI] |

**Packages removed due to [SLOP] verdict:** none. [VERIFIED: PyPI]

**Packages flagged as suspicious [SUS]:** `langgraph`, `langgraph-checkpoint-sqlite`, and optional `langchain-openai`. The package-legitimacy seam flagged the first and third for recency/unknown downloads and the SQLite saver for unknown downloads; the required human checkpoint cannot be skipped. [VERIFIED: PyPI]

## Architecture Patterns

### System Architecture Diagram
```text
Stock Analysis selected symbol ─┐
                                ├─ POST /api/analysis/runs ──────────────┐
Portfolio selected account ─────┘                                         │
                                                                          v
  Governed repository / financial Parquet ─> EvidencePreparationService ─> validate A/B/C
                                                        │                 └> material-number cross-check
                                                        │                         │
                                                        v                         v
                                             frozen EvidenceSnapshot ─> AnalysisService
                                                                                │
                                       fixed DAG: START -> validate -> generate structured body -> END
                                                                                │
                                                server injects evidence + lifecycle snapshot, validates citations
                                                                                │
                              ┌─────────────────────── success ───────────┴────────── validation failure ──┐
                              v                                                                              v
                  SQLite AnalysisRepository: immutable report version                              auditable failed run,
                  + source/material-number rows + model provenance                                  no partial report
                              │
       ┌──────────────────────┼───────────────────────────────────────┐
       v                      v                                       v
GET latest/history      GET evidence / differences           GET lifecycle / outcomes
       │                      │                                       │
       └───────────── independent TanStack Query panels ──────────────┘

New attributable evidence -> LifecycleRuleService -> proposed event -> human confirmation
                                                          │                    │
                                                          └── append rejected ─┴─ append confirmed official event
                                                                               -> immutable observation plan
                                                                               -> append-only outcome observations
```

### Recommended Project Structure
```text
backend/app/analysis/
├── schemas.py             # strict request/domain/API models; model body vs server envelope
├── evidence.py             # read-only governed snapshot, grades, material numbers, cross-checks
├── model_adapter.py        # one provider boundary; direct SDK by default; injected test transport
├── graph.py                # fixed two-node StateGraph, no ToolNode/agent/loop
├── repository.py           # parameterized SQLite inserts/queries for analysis tables
├── service.py              # run acquisition, persistence, report retrieval, progress publication
├── lifecycle.py            # proposal rules, human confirmation, immutable observation and outcome append
└── api.py                  # APIRouter request/response mapping only

frontend/src/components/analysis/
├── AnalysisWorkspace.tsx   # object-local detail region and tab state
├── ReportPanel.tsx         # perspectives, scoring, valuation, IC memo, disclaimer
├── EvidencePanel.tsx       # source grades, material-number table, native details
├── LifecyclePanel.tsx      # current server state, timeline, outcome and confirmation action
└── AnalysisStatus.tsx      # coarse server-owned generation status
```

### Pattern 1: Freeze Before Generate
**What:** Build an immutable evidence snapshot before graph invocation: source IDs, A/B/C grade, independence group, retrieval/as-of timestamps, material number definitions, normalized values, cross-check result, and the lifecycle snapshot. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md]

**When to use:** Every generation or regeneration. The browser sends only `subject_kind`, subject ID, and optional bounded research focus; it never sends source grades or numerical verdicts. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]

**Example:**
```python
# Source: Phase 3 AI-SPEC and existing ResearchRepository pattern
snapshot = evidence_service.prepare(subject=subject, focus=request.focus)
frozen = FrozenEvidenceSnapshot.model_validate(snapshot)
repository.create_run(run_id=run_id, evidence=frozen, status="validating")
report_body = await graph.ainvoke(
    {"run_id": run_id, "evidence": frozen.model_dump(mode="json")},
    {"configurable": {"thread_id": run_id}},
)
generated = GeneratedAnalysis.model_validate(report_body["generated"])
report = AnalysisReport.from_server_owned(generated, frozen, lifecycle_snapshot)
repository.append_validated_report(report)
```

### Pattern 2: Two Schema Boundaries
**What:** `GeneratedAnalysis` contains only model-generable perspectives, scoring rationale, valuation applicability, and IC memo. `AnalysisReport` wraps that body with server-owned sources, material numbers, cross-check states, lifecycle snapshot, run/model/prompt/schema versions, and validation metadata. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md]

**When to use:** Validate model output once before envelope assembly and validate the full report again after server injection. Citation IDs must be a subset of frozen source IDs. [CITED: https://docs.pydantic.dev/latest/concepts/models/] [CITED: https://docs.pydantic.dev/latest/concepts/validators/]

### Pattern 3: Append-Only Official Lifecycle
**What:** Model output may identify concerns in prose but cannot write signal status. `LifecycleRuleService` produces a proposal only when state-specific evidence rules pass; `POST .../confirm` records reviewer identity/time and appends the official transition plus exactly one immutable observation plan. Rejection appends a rejected review without changing the current state. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]

**When to use:** For `strengthened`, `weakened`, `falsified`, and `priced_in`; current status is derived from the latest confirmed event, not from report text, UI color, or performance. [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md]

### Concrete Persistence Contract

Use migration tables analogous to Phase 2's immutable `research_experiments`; insert new report versions and events, never `UPDATE` an existing report/evidence/event/observation row. [VERIFIED: codebase]

| Table group | Required records / invariants |
|-------------|-------------------------------|
| `analysis_runs` | `id`, subject kind/key, status, requested/started/finished timestamps, evidence fingerprint, prompt/schema/model/adapter versions, checkpoint reference, token/latency/error metadata. Enforce one `queued`/`running` row per subject in the same transaction. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |
| `analysis_evidence_snapshots`, `analysis_sources` | Snapshot is bound to one run; source rows hold grade, origin/independence group, retrieved/as-of time, report period, excerpt location/hash, and controlled raw-artifact reference. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| `analysis_material_numbers`, `analysis_number_observations` | Number label, normalized value/unit/currency/period/definition, source observations, cross-check state/reason, and affected conclusion IDs. A confirmed result must identify an independent peer source. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| `analysis_reports`, `analysis_report_versions` | Report is only persisted after both Pydantic validations; version ordering is per subject and newest is selected by validated completion time. No delete/overwrite API. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |
| `analysis_signals`, `analysis_lifecycle_reviews`, `analysis_lifecycle_events` | Retain all proposals/confirmations/rejections, evidence IDs, prior/next state, reviewer, rationale, and occurred/recorded timestamps. Only confirmed event changes current state. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |
| `analysis_observation_plans`, `analysis_outcome_observations` | Confirmation atomically inserts one unchangeable 20/60/120 trading-day plan with benchmark/metric; later observations append rather than modify it. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |

### Recommended HTTP Contract

| Endpoint | Purpose | Invariants |
|----------|---------|------------|
| `POST /api/analysis/runs` | Start or focus a single object-scoped generation. | Validates subject ownership/existence; deduplicates active object run; returns safe status/run/report reference, not token deltas. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |
| `GET /api/analysis/subjects/{kind}/{key}/reports` | List immutable report versions newest-first. | Default reader path returns newest validated version with generation time and evidence limitations. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |
| `GET /api/analysis/reports/{report_id}` | Read structured report envelope. | Never accepts/report-writes sources from the caller. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| `GET /api/analysis/reports/{report_id}/evidence` | Read grades, material numbers, source rows, and conflicts. | Supports independent panel loading and pagination/disclosure. [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md] |
| `GET /api/analysis/signals/{signal_id}/history` | Read derived current state plus append-only timeline/outcomes. | Current state comes from latest confirmed server event. [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md] |
| `POST /api/analysis/lifecycle-reviews/{review_id}/confirm` | Human-only official transition. | Applies state-specific rules server-side and creates immutable observation plan atomically. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |
| `POST /api/analysis/lifecycle-reviews/{review_id}/reject` | Preserve rejected review. | Appends rejection and leaves official state unchanged. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |

### Anti-Patterns to Avoid
- **Client-owned report persistence:** Existing stores save accumulated Markdown after the stream ends; Phase 3 must receive a fully server-issued report ID and render the persisted envelope. [VERIFIED: codebase]
- **Model-controlled provenance/lifecycle:** Never parse source grade, cross-check, official status, or reviewer outcome from model prose. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md]
- **Checkpoint as audit ledger:** LangGraph checkpoints support workflow persistence/replay but cannot replace append-only lifecycle history. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers]
- **A second SSE or AI route:** Controlled generation status may reuse the existing named-event route; do not create agent progress streaming or raw LLM token SSE. [VERIFIED: codebase] [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]
- **Parallel AI UI shell:** Do not retain the current gradient modal treatment for the Phase 3 detail view; integrate into the existing selected-object workspaces with the UI-SPEC's semantic panels. [VERIFIED: codebase] [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stateful bounded workflow | Ad hoc coroutine graph, dynamic agent loop, or tool executor | Fixed `StateGraph` with explicit nodes/edges. [CITED: https://docs.langchain.com/oss/python/langgraph/graph-api] | Typed state and explicit topology make the limited workflow reviewable; no `ToolNode`, `create_agent`, or conditional retry loop is permitted. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Model output parsing | Markdown/regex extraction or permissive dictionaries | Pydantic strict models plus `model_validate_json()`. [CITED: https://docs.pydantic.dev/latest/concepts/models/] | Extra fields, unknown evidence IDs, and invalid valuation applicability must fail closed. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Durable graph checkpoints | In-memory saver in production | Approved SQLite LangGraph saver in a dedicated local DB. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] | Process restart must not silently erase workflow state; the checkpoint still remains non-authoritative. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Historical integrity | Mutable current-state JSON blob | Normalized append-only SQLite report/event/observation rows. [VERIFIED: codebase] | Research evidence and rejected reviews must remain reconstructable. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |
| View state synchronization | New global state library or local synthesized evidence | Existing typed `api.ts`, `QK`, TanStack Query, local panel state, and URL/local-storage restoration where existing conventions require it. [VERIFIED: codebase] | UI-SPEC prohibits a second API client/state library and requires independent panel loading. [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md] |

**Key insight:** This phase's complexity is not narrative generation; it is preserving a deterministic, independently reviewable chain from governed input through report version to human-confirmed lifecycle result. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md]

## Common Pitfalls

### Pitfall 1: Reusing the existing free-text report protocol
**What goes wrong:** The browser receives Markdown, then invokes a save endpoint; server provenance and validation can be bypassed or omitted. [VERIFIED: codebase]

**How to avoid:** The new `POST /runs` returns a server run/report ID; only the service can insert a report after output and envelope validation. Preserve old reports read-only and remove Phase 3 delete semantics. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]

### Pitfall 2: False independent cross-checks and semantic mismatch
**What goes wrong:** Two syndicated pages, different reporting periods, units, adjustment methods, or consolidation scopes appear to confirm one number. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md]

**How to avoid:** Store origin/independence group, source/as-of date, period, unit/currency, definition, and normalization rule per observation; only deterministic rules assign `confirmed`, otherwise show `conflicting` or `unresolved`. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md]

### Pitfall 3: Letting an LLM resolve uncertainty
**What goes wrong:** The prose selects the convenient value or omits a conflict, making an uncertain conclusion look certain. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md]

**How to avoid:** Include frozen allowed evidence IDs and cross-check status in the prompt; post-validate all citations and render unresolved warnings ahead of affected conclusions and the IC memo. [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md]

### Pitfall 4: Treating a graph checkpoint as permanent audit state
**What goes wrong:** Replays or checkpoint pruning alter/re-execute nodes while lifecycle history has no immutable prior/next-state evidence. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers]

**How to avoid:** Persist immutable lifecycle review/event/observation records in `operational.db`; checkpoint references are metadata on an analysis run only. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md]

### Pitfall 5: Automatic lifecycle advancement
**What goes wrong:** A new report or model conclusion changes official signal state without a review trail. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]

**How to avoid:** Split proposal from confirmation; enforce transition threshold rules server-side; confirmation/rejection is a named human API action and every outcome remains visible. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]

### Pitfall 6: UI state coupling
**What goes wrong:** Reloading evidence/history clears a report the user was reading, or an active regeneration replaces older content before validation. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]

**How to avoid:** Give report, evidence, lifecycle, and progress their own query keys; retain old report selection/scroll/panel state while a new server run progresses. [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md]

## Code Examples

### Fixed Graph and Server Envelope
```python
# Source: LangGraph graph/checkpointer docs and Phase 3 AI-SPEC
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    run_id: str
    frozen_evidence: dict[str, object]
    generated: dict[str, object] | None


async def validate_frozen_input(state: GraphState) -> dict[str, object]:
    evidence = FrozenEvidenceSnapshot.model_validate(state["frozen_evidence"])
    return {"frozen_evidence": evidence.model_dump(mode="json")}


async def generate_validated_body(state: GraphState) -> dict[str, object]:
    body = await model_adapter.generate(GeneratedAnalysis, state["frozen_evidence"])
    return {"generated": body.model_dump(mode="json")}


builder = StateGraph(GraphState)
builder.add_node("validate_frozen_input", validate_frozen_input)
builder.add_node("generate_validated_body", generate_validated_body)
builder.add_edge(START, "validate_frozen_input")
builder.add_edge("validate_frozen_input", "generate_validated_body")
builder.add_edge("generate_validated_body", END)
graph = builder.compile(checkpointer=checkpointer)

# Service only: source and lifecycle data are attached after graph return.
result = await graph.ainvoke(initial_state, {"configurable": {"thread_id": run_id}})
body = GeneratedAnalysis.model_validate(result["generated"])
report = AnalysisReport.from_server_owned(body, frozen_evidence, lifecycle_snapshot)
```

### Strict Citation Boundary
```python
# Source: Pydantic docs and Phase 3 AI-SPEC
from pydantic import BaseModel, ConfigDict, model_validator


class GeneratedAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    perspectives: list[Perspective]
    valuation: ValuationAssessment
    ic_memo: ICMemo


class AnalysisReport(GeneratedAnalysis):
    source_records: list[SourceRecord]
    signal_lifecycle: SignalLifecycleSnapshot

    @model_validator(mode="after")
    def only_cites_frozen_evidence(self):
        allowed = {source.source_id for source in self.source_records}
        cited = {source_id for p in self.perspectives for source_id in p.evidence_ids}
        cited |= set(self.valuation.evidence_ids) | set(self.ic_memo.evidence_ids)
        if unknown := cited - allowed:
            raise ValueError(f"unknown evidence ids: {sorted(unknown)}")
        return self
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Free-text streamed Markdown persisted by the frontend | Server-validated structured report body plus server-owned immutable provenance/lifecycle envelope | Phase 3 contract | Makes ANLY-01/02/03 auditable and prevents model/client authority over evidence/state. [VERIFIED: codebase] [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| In-memory checkpoint demo saver | Persistent local SQLite checkpointer plus separate SQLite audit history | Phase 3 design | Supports restart/review without conflating replayable workflow data with official records. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] |
| Model narrative as status | Deterministic proposal rules and human-confirmed append-only lifecycle events | Phase 3 contract | A report can propose, but cannot autonomously advance official research state. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |

**Deprecated/outdated:** Existing `stock_analysis` and `financials` report CRUD endpoints are not an acceptable storage contract for new Phase 3 evidence-backed reports; retain legacy behavior only where necessary for unrelated surfaces and route new analysis through the dedicated domain. [VERIFIED: codebase] [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The existing authenticated session identity can supply a meaningful human reviewer identity for lifecycle confirmations. | Architecture Patterns | If unavailable, the phase must add a bounded reviewer identity field/audit policy before official confirmation is enabled. [ASSUMED] |
| A2 | A dedicated SQLite checkpoint database is acceptable alongside `operational.db` in the single-container deployment. | Standard Stack | If the deployment prohibits a second file, an approved saver/storage layout must be selected without making checkpoints authoritative. [ASSUMED] |
| A3 | The exact source-provider composition and material-number vocabulary will be resolved from currently governed inputs rather than introducing external web retrieval. | Existing Integration Map | If required source types are absent, planner must surface `context_insufficient` rather than fabricate A/B/C evidence. [ASSUMED] |

## Open Questions

1. **Confirmed reviewer identity**
   - What we know: all official state changes require a human reviewer and audit timestamp. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]
   - What's unclear: the current local session API's stable user/audit identifier was not confirmed in this research. [ASSUMED]
   - Recommendation: plan an explicit repository/API test proving that confirmation records a stable authenticated reviewer ID; block confirmation when identity is unavailable. [ASSUMED]

2. **Production checkpoint compatibility**
   - What we know: LangGraph documents a separately installed SQLite saver, and current package versions are available on PyPI. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] [VERIFIED: PyPI]
   - What's unclear: exact `langgraph`/SQLite-saver API compatibility under the selected lockfile has not been run. [ASSUMED]
   - Recommendation: make the human package checkpoint followed by a startup smoke test a Wave 0 gate before domain implementation. [ASSUMED]

3. **Official source grade policy**
   - What we know: grade assignment and cross-checking must be deterministic and source-grade is per source. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]
   - What's unclear: the concrete A/B/C mapping for every current governed provider is discretionary. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md]
   - Recommendation: define a versioned local grade-policy table and fixtures for A, B, C, duplicate-origin, conflict, and insufficient-evidence cases before UI work. [ASSUMED]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Backend/domain/graph | ✓ | 3.11.2 | — [VERIFIED: environment] |
| `uv` | Lockfile and package installation | ✓ | 0.9.30 | — [VERIFIED: environment] |
| Existing Pydantic | Schema validation | ✓ | 2.13.4 environment install; project declares `>=2.7` | — [VERIFIED: environment] [VERIFIED: codebase] |
| `langgraph` | Fixed workflow | ✗ | not installed | Human-verified installation, then lock/smoke test. [VERIFIED: environment] |
| `langgraph-checkpoint-sqlite` | Persistent local checkpointing | ✗ | not installed | Human-verified installation, then lock/smoke test. [VERIFIED: environment] |
| Node/pnpm | Frontend build/E2E | ✓ | Node 25.6.0; pnpm 11.1.1 | — [VERIFIED: environment] |
| Playwright CLI | Browser validation | ✓ | 1.58.0 CLI; project package is 1.61.1 | Run through `pnpm exec playwright` so project lockfile controls version. [VERIFIED: environment] [VERIFIED: codebase] |
| Docker | Existing compose acceptance | ✓ | 29.2.1 | — [VERIFIED: environment] |

**Missing dependencies with no fallback:** `langgraph` and `langgraph-checkpoint-sqlite` are missing and blocked behind the required human legitimacy verification. [VERIFIED: environment] [VERIFIED: PyPI]

**Missing dependencies with fallback:** none. [VERIFIED: environment]

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest>=8.0` + `pytest-asyncio>=0.23`; Playwright `@playwright/test` 1.61.1. [VERIFIED: codebase] |
| Config file | Backend `pyproject.toml` (`asyncio_mode = "auto"`); frontend `playwright.config.ts`. [VERIFIED: codebase] |
| Quick run command | `cd backend && uv run pytest tests/test_analysis_repository.py tests/test_analysis_service.py -q` |
| Full suite command | `cd backend && uv run pytest -q && cd ../frontend && pnpm exec playwright test e2e/phase3-ai-analysis.spec.ts --project=desktop-chromium` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ANLY-01 | Grade/source/period/unit/cross-check records are frozen; duplicate-origin and conflicts remain unresolved; unknown model citations fail. | unit + repository + API | `uv run pytest tests/test_analysis_evidence.py tests/test_analysis_service.py -q` | ❌ Wave 0 |
| ANLY-02 | Fixed graph has only two named nodes; structured body validates; valuation applicability and scoring/citation rules fail closed; invalid output creates no report. | unit + async service | `uv run pytest tests/test_analysis_graph.py tests/test_analysis_service.py -q` | ❌ Wave 0 |
| ANLY-03 | State-specific proposal rules, confirmation/rejection audit, immutable observation plan, and appended outcomes behave correctly. | repository + FastAPI | `uv run pytest tests/test_analysis_lifecycle.py tests/test_analysis_api.py -q` | ❌ Wave 0 |
| ANLY-01/02/03 | Stock and portfolio workflows render independent panels, evidence warning, report completeness, lifecycle history, keyboard/mobile states, and one-active-run behavior. | Playwright E2E | `pnpm exec playwright test e2e/phase3-ai-analysis.spec.ts --project=desktop-chromium` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** Relevant backend `uv run pytest ... -q` plus `cd frontend && pnpm run build` when TypeScript changes. [VERIFIED: codebase]
- **Per wave merge:** Backend full pytest and targeted Phase 3 Playwright desktop run. [ASSUMED]
- **Phase gate:** Full suite green plus desktop/mobile evidence-first UAT scenarios before `/gsd-verify-work`. [CITED: .planning/phases/03-ai-analysis/03-UI-SPEC.md]

### Wave 0 Gaps
- [ ] `backend/tests/test_analysis_evidence.py` — deterministic source grading, independence and material-number normalization/cross-check fixture matrix.
- [ ] `backend/tests/test_analysis_graph.py` — exact fixed topology and no tool/loop guard.
- [ ] `backend/tests/test_analysis_service.py` — injected offline adapter, schema/citation failures, immutable version persistence, one-active-run behavior.
- [ ] `backend/tests/test_analysis_lifecycle.py` and `test_analysis_api.py` — human confirmation/rejection and observation result append-only contracts.
- [ ] `frontend/e2e/phase3-ai-analysis.spec.ts` — fixture-routed UI-SPEC scenarios at 1440px, 1024px, and 375px.
- [ ] Framework install and startup smoke test: human-verify packages, `uv add`, `uv lock`, then compile/invoke the fixed graph with the SQLite saver.

## Security Domain

OWASP ASVS supplies a verification basis for web-application technical security controls; this phase uses the project's configured ASVS Level 1 enforcement. [CITED: https://owasp.org/www-project-application-security-verification-standard/] [VERIFIED: codebase]

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing `/api` authentication middleware protects the new router; lifecycle confirmation must record the authenticated reviewer, not a request body identity. [VERIFIED: codebase] |
| V3 Session Management | yes | Reuse existing session validation; do not expose report IDs as authorization grants. [VERIFIED: codebase] |
| V4 Access Control | yes | Validate subject/account ownership before run/read/confirm; scope report/signal IDs through server-side subject lookup. [ASSUMED] |
| V5 Input Validation | yes | Pydantic `extra="forbid"`, bounded focus/IDs/pagination, server-built prompts, citation whitelist, and parameterized SQLite queries. [CITED: https://docs.pydantic.dev/latest/concepts/models/] [VERIFIED: codebase] |
| V6 Cryptography | no new cryptographic design | Reuse existing secrets storage/transport configuration; never hand-roll encryption or log keys. [VERIFIED: codebase] |
| V7 Error Handling and Logging | yes | Sanitize provider errors, retain validation failure metadata, and do not log keys or full untrusted raw evidence/prompt text. [VERIFIED: codebase] [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |

### Known Threat Patterns for This Stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection in source text/focus | Tampering | Treat every retrieved string as data; fixed server prompt, no tools, no model-selected edges, bounded validated context, and citation whitelist. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Forged provenance or lifecycle state | Spoofing / Tampering | Generated schema excludes source grades/cross-check/lifecycle ownership; server loads and injects all authoritative fields; confirmation requires authenticated human action. [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |
| IDOR across report/account/signal IDs | Elevation of Privilege | Authorize every lookup against the selected subject/account; never trust a client-provided reviewer or source object. [ASSUMED] |
| SQL injection / mutable audit tampering | Tampering | Parameterized repository access and append-only domain inserts; no raw SQL built from request strings. [VERIFIED: codebase] |
| Sensitive provider data in logs/SSE | Information Disclosure | Reuse sanitized provider errors and emit only server-controlled progress, not prompts, evidence excerpts, model tokens, or secrets. [VERIFIED: codebase] [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] |
| Cost/denial through repeated generation | Denial of Service | One active run per object, deterministic input cap, timeout/token budget, limited schema-repair attempts, and auditable failure state; Phase 4 agent rate limits remain out of scope. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] [CITED: .planning/phases/03-ai-analysis/03-CONTEXT.md] |

## Sources

### Primary (HIGH confidence)
- Local codebase — `backend/app/main.py`, `backend/app/operational/migrations.py`, `backend/app/research/repository.py`, `backend/app/services/ai_provider.py`, `frontend/src/lib/api.ts`, and existing UI stores/integration surfaces. [VERIFIED: codebase]
- PyPI queries — current registry versions and package metadata for `langgraph`, `langgraph-checkpoint-sqlite`, and `langchain-openai`. [VERIFIED: PyPI]

### Secondary (MEDIUM confidence)
- [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) — typed `StateGraph`, explicit nodes and edges. [CITED: https://docs.langchain.com/oss/python/langgraph/graph-api]
- [LangGraph checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) — thread IDs, persistence, and SQLite checkpointer package. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers]
- [LangChain model docs](https://docs.langchain.com/oss/python/langchain/models) — Pydantic structured outputs and OpenAI-compatible `base_url`. [CITED: https://docs.langchain.com/oss/python/langchain/models]
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/) and [validators](https://docs.pydantic.dev/latest/concepts/validators/) — strict models, JSON validation, cross-field invariants. [CITED: https://docs.pydantic.dev/latest/concepts/models/] [CITED: https://docs.pydantic.dev/latest/concepts/validators/]
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) — security verification control basis. [CITED: https://owasp.org/www-project-application-security-verification-standard/]

### Tertiary (LOW confidence)
- None beyond the explicitly listed assumptions. [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — framework and validation behaviors were checked in official docs, but package-legitimacy seam marks planned packages SUS and exact lockfile compatibility needs a smoke test. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] [VERIFIED: PyPI]
- Architecture: HIGH — application lifecycle, persistence, APIs, client stores, and UI surfaces were read from the current codebase. [VERIFIED: codebase]
- Pitfalls: MEDIUM — domain/UI/AI contracts and official framework docs corroborate the primary risks; reviewer identity and provider-grade policy remain open. [CITED: .planning/phases/03-ai-analysis/03-AI-SPEC.md] [ASSUMED]

**Research date:** 2026-07-11
**Valid until:** 2026-07-18, because LangGraph and its companion packages are fast-moving. [VERIFIED: PyPI]
