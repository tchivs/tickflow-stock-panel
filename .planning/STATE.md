---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 04
current_phase_name: advanced-capabilities
status: executing
stopped_at: Phase 3 context gathered
last_updated: "2026-07-13T05:20:11.472Z"
last_activity: 2026-07-13
last_activity_desc: Completed 04-17 governed experiment evolution
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 54
  completed_plans: 53
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-10)

**Core value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.
**Current focus:** Phase 04 — advanced-capabilities

## Current Position

Phase: 04 (advanced-capabilities) — EXECUTING
Plan: 5 of 19
Status: Ready to execute
Last activity: 2026-07-13 — Completed 04-17 governed experiment evolution

Progress: [██████████] 96%

## Performance Metrics

**Velocity:**

- Total plans completed: 35
- Average duration: N/A
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 15 | - | - |
| 02 | 8 | - | - |
| 03 | 12 | - | - |

**Recent Trend:**

- Last 5 plans: None
- Trend: N/A

| Phase 02-factor-and-strategy-research P07 | 4m 30s | 3 tasks | 5 files |
| Phase 02 P08 | 1258 | 3 tasks | 5 files |
| Phase 03 P01 | 3min | 1 tasks | 1 files |
| Phase 03 P02 | 4min | 2 tasks | 7 files |
| Phase 03 P03 | 7min | 2 tasks | 4 files |
| Phase 03 P04 | 301 | 2 tasks | 6 files |
| Phase 03 P05 | 7m 8s | 2 tasks | 8 files |
| Phase 03 P06 | 6m 49s | 2 tasks | 4 files |
| Phase 03 P07 | 529 | 2 tasks | 6 files |
| Phase 03 P09 | 6m | 1 tasks | 6 files |
| Phase 03 P08 | 11m 22s | 3 tasks | 9 files |
| Phase 03 P10 | 14m | 3 tasks | 7 files |
| Phase 03 P11 | 527 | 2 tasks | 5 files |
| Phase 03 P12 | 480 | 3 tasks | 5 files |
| Phase 04 P12 | 21m | 2 tasks | 6 files |
| Phase 04 P13 | 7m | 2 tasks | 5 files |
| Phase 04 P14 | 16m | 2 tasks | 10 files |
| Phase 04 P15 | 11m | 3 tasks | 7 files |
| Phase 04 P16 | 8m | 2 tasks | 6 files |
| Phase 04 P17 | 10m 52s | 2 tasks | 9 files |
| Phase 04 P18 | 12m | 2 tasks | 5 files |

## Accumulated Context

### Decisions

No implementation decision was explicitly locked by the architecture intake. Required planning guardrails:

- [Phase 1]: Phase 1 must run as one Linux Docker Compose container with no external database or message queue.
- [Phase 1]: Preserve Parquet/DuckDB/Polars for time-series data and SQLite for operational state.
- [All phases]: Preserve upstream synchronization paths and independently activatable module boundaries.
- [Phase ?]: Completed strategy results fingerprint the full governed panel loaded for execution, including warmup and any full-mode buffer.
- [Phase ?]: The catalog receives only revision and fingerprint copied from the server-issued result under its existing recognized keys.
- [Phase ?]: Catalog warning vocabulary and no-winner comparison semantics remain unchanged.
- [Phase ?]: Strategy retention eligibility requires the current successful SSE task and its server-issued handle.
- [Phase 03]: 批准 langgraph==1.2.9 与 langgraph-checkpoint-sqlite==3.1.0；保留直接 OpenAI SDK 适配器且不添加 langchain-openai。
- [Phase 03]: Wave 0 analysis contracts remain intentionally RED until plans 03-04 through 03-07 implement app.analysis. — Avoid placeholder production code while preserving executable evidence, graph, lifecycle, and trusted-reviewer invariants.
- [Phase 03]: Analysis client actions carry only bounded subject identifiers or server-issued review references; they never send reviewer, provenance, grade, or lifecycle authority.
- [Phase 03]: Every analysis cache key includes the subject so persisted progress invalidates only the affected object's panels.
- [Phase 03]: Phase 3 browser scenarios remain per-case expected failures until 03-08 removes the markers after delivering the UI.
- [Phase 03]: Analysis evidence is frozen server-side with provenance hashes and independent material-number cross-checks before model generation.
- [Phase 03]: Analysis audit records use append-only operational.db tables with SQLite immutable triggers; only run execution status may transition.
- [Phase 03]: Graph execution opens AsyncSqliteSaver per invocation so async ainvoke retains durable thread checkpoints without a process-global connection.
- [Phase 03]: Lifecycle remains a read-only fallback snapshot; lifecycle mutation integration is intentionally deferred to Plan 03-09.
- [Phase 03]: Lifecycle proposals are evidence-gated suggestions; only confirmed events determine official state.
- [Phase 03]: Reviewer principals are opaque, persisted per session, and resolved only from server-held session tokens.
- [Phase 03]: Confirmed events and one observation plan are committed atomically; rejection and outcomes remain append-only.
- [Phase 03]: Analysis route IDs resolve to a persisted subject before authorization; opaque IDs are never authority.
- [Phase 03]: Shared SSE binds immutable server-derived subject scope at subscription and filters analysis_progress before queueing.
- [Phase 03]: Lifecycle evaluation runs only after immutable report and completed run persistence.
- [Phase 03]: Completed-analysis proposal retries use deterministic run/report/snapshot attribution and never append official events.
- [Phase 03]: Analysis UI maps stock/portfolio display subjects to server-authorized instrument/account requests within the workspace.
- [Phase 03]: Analysis reports are read only in object-local workspaces; the legacy free-text global dialog host is disabled.
- [Phase 03]: Production analysis evidence is derived only from governed market, financial, and operational repositories; browser focus and notes never become facts.
- [Phase 03]: Only genuinely active runs are deduplicated; a new run without execution collaborators records a sanitized terminal failure.
- [Phase 03]: AsyncSqliteSaver is the production graph verification path; synchronous cross-thread SQLite saver checks remain excluded.
- [Phase 03]: Analysis API responses use explicit allowlisted projections rather than raw SQLite records or nested snapshots.
- [Phase 03]: Completed reports receive a server-issued signal only after subject authorization; legacy reports get no lifecycle transition.
- [Phase 03]: Rejected lifecycle proposals are inferred from append-only rejection records; confirmed events alone determine official state.
- [Phase 03]: Analysis UI keeps stock/portfolio display subjects separate from instrument/account API request subjects. — This preserves object-local UI semantics while preventing client calls from sending unsupported subject kinds.
- [Phase 04]: Viewpoint reads select the latest immutable evaluation by `created_at` then stable ID, never response ordering.
- [Phase 04]: Experiment execution uses a spawned, parent-owned process group and returns only bounded manifest metadata.
- [Phase 04]: Job-state mutation and its append-only audit fact commit together before scoped SSE publication.
- [Phase 04]: Production advanced workflows receive only persisted server bindings and remain recovery cursors rather than authority sources.
- [Phase 04]: Custom strategy source may spawn only after a fresh complete Linux isolation proof; unavailable or stale proof rejects before spawn.
- [Phase 04]: A root SSE subscriber sends a data-free ready event after scope-bound registration so host acceptance can avoid connection races.
- [Phase 04]: Linux sandbox proof accepts only parent/child namespace deltas, mount and write-boundary checks, network denial, rlimit observations, and verified cleanup before source spawn.
- [Phase 04]: Sandbox run disclosure reauthorizes the persisted opaque parent research asset and returns only an allowlisted terminal DTO.
- [Phase 04]: Viewpoint evaluation reads frozen historical windows through KlineRepository; revision, correction, and evaluation routes reauthorize the persisted instrument before append. — Preserves governed data boundaries and prevents browser-provided scope or market authority.
- [Phase 04]: Frozen experiment scopes and five evolution gates reload only immutable server-produced evidence; browser requests cannot supply authority or verdicts.
- [Phase 04]: Viewpoint mutations invalidate only the active subject's viewpoint version and calibration keys. — Preserves object-local cache ownership for immutable research records.
- [Phase 04]: Experiment and evolution controls submit bounded scope/configuration while gate verdicts and sandbox details remain server-projected. — Prevents browser-provided authority and sandbox disclosure.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1 planning must map the existing tickflow, PanWatch, and Hermes extension points before choosing package and synchronization boundaries.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Optional enhancement | Shadow Account, thesis tracking, and Kronos forecasting | Phase 5 / v2 | 2026-07-10 |

## Session Continuity

Last session: 2026-07-13T05:20:11.465Z
Stopped at: Phase 3 context gathered
Resume file: .planning/phases/03-ai-analysis/03-CONTEXT.md
