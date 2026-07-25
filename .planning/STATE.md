---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 05
current_phase_name: optional-enhancements
status: executing
stopped_at: "05-27 complete; executing 05-39 CR-06/CR-07"
last_updated: "2026-07-25T15:13:34.000Z"
last_activity: 2026-07-24
last_activity_desc: "Completed 05-27 runtime byte bind and bounded IPC"
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 103
  completed_plans: 101
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-10)

**Core value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.
**Current focus:** Phase 05 — optional-enhancements

## Current Position

Phase: 05 (optional-enhancements) — EXECUTING
Plan: 05-39 recovery dispatch and PGID finalizer
Status: executing
Last activity: 2026-07-24 — Removed personal-project human approval gate

Progress: [██████████] 98%

## Performance Metrics

**Velocity:**

- Total plans completed: 66
- Average duration: N/A
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 15 | - | - |
| 02 | 8 | - | - |
| 03 | 12 | - | - |
| 04 | 27 | - | - |
| 05 | 17 | - | - |

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
| Phase 04-advanced-capabilities P22 | 521 | 2 tasks | 9 files |
| Phase 04-advanced-capabilities P24 | 773 | 2 tasks | 9 files |
| Phase 04-advanced-capabilities P23 | 9m 37s | 2 tasks | 6 files |
| Phase 04 P25 | 314 | 2 tasks | 3 files |
| Phase 04 P26 | 11m 20s | 2 tasks | 4 files |
| Phase 04 P27 | 7m 18s | 2 tasks | 4 files |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 05 P05 | 920 | 2 tasks | 5 files |
| Phase 05 P07 | 12m 30s | 3 tasks | 13 files |
| Phase 05 P08 | 15m 9s | 2 tasks | 6 files |
| Phase 05 P11 | 15m 17s | 2 tasks | 5 files |
| Phase 05 P14 | 20m | 2 tasks | 7 files |
| Phase 05-optional-enhancements P15 | 18m30s | 2 tasks | 6 files |
| Phase 05-optional-enhancements P16 | 25m33s | 3 tasks | 3 files |
| Phase 05 P17 | 14m25s | 2 tasks | 11 files |
| Phase 05 P40 | 1m | 1 tasks | 3 files |
| Phase 05 P36 | 25min | 2 tasks | 6 files |
| Phase 05 P27 | 45min | 2 tasks | 6 files |

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
- [Phase ?]: ResearchRepository exclusively resolves immutable research assets to installed strategies; advanced workflows receive an injected resolver.
- [Phase ?]: Legacy experiment specifications remain readable but fail closed for execution without frozen server-bound strategy provenance.
- [Phase ?]: Advanced-host readiness is deployment-owned and validates 000300.SH, fixed evaluation windows, coverage, splits, and bullish_alignment warmup before any governed-lake write.
- [Phase ?]: Host fixture eligibility derives bounded MA and momentum inputs from raw bars and reuses the production bullish_alignment expression rather than copying strategy logic.
- [Phase ?]: Historical aggregate rate windows use reserved __legacy_rate_window__ identity and cannot be consumed by live policy.
- [Phase ?]: Rejected task quota checks persist audit state without emitting advanced-progress SSE.
- [Phase ?]: Viewpoint calibration selects the first terminal immutable fact by created-at and stable ID, excluding the awaiting fact.
- [Phase ?]: Terminal viewpoint evaluation retries reuse the frozen ledger fact and cannot invoke governed evaluation or alter calibration.
- [Phase ?]: Public experiment creation resolves an extant persisted asset-to-installed-strategy binding before service invocation and returns safe 404 on mismatch.
- [Phase ?]: Authenticated real-lifespan tests prove task-specific quota denials produce no advanced SSE event while independent research capacity remains available.
- [Phase ?]: Queue acquisition requires immutable authorization policy provenance to equal the current persisted policy in the same transaction; mismatches never charge or create work.
- [Phase ?]: Queued jobs compare durable authorization policy provenance with the current revision before quota inspection, workflow work, or advanced-progress publication.
- [Phase ?]: Phase 05 optional-host contracts start the single production FastAPI lifespan and limit test overrides to independent deployment probes and failure injection.
- [Phase ?]: Phase 05 browser RED accepts exactly one scenario-specific missing production locator per UI-SPEC scenario; all fixture, syntax, launch, skip, retry, timeout, external-request, and unexpected-pass failures remain fatal.
- [Phase ?]: Descriptor-less SHDW-01 and THES-01 edges remain flagged-unverified until final named green host/browser scenarios; no probe descriptor is invented in Wave 0.
- [Phase ?]: Kronos-base revision 2b554741eca47781b64468546e77fef3e85130e6 is cataloged only with Tokenizer-base and remains explicit-provisioning-only.
- [Phase ?]: Provisioning admits only config.json and model.safetensors at immutable revisions, verifies full SHA-256 in temporary staging, and atomically publishes the deployment catalog.
- [Phase ?]: Checkpoint verification and routine runtime paths stay local-only; existing mismatched assets are rejected rather than overwritten.
- [Phase ?]: Same-content retries and corrections always receive distinct Shadow batch and artifact identities; hashes record lineage without deduplicating facts.
- [Phase ?]: A Shadow evidence set freezes only when every trade in each attributable completed batch is explicitly included or excluded.
- [Phase ?]: Shadow estimators are transient; only canonical allowlisted rule data, provenance, metrics, assumptions, limitations, and replay evidence persist.
- [Phase ?]: Shadow retries reuse exact frozen split identities but append new immutable attempts and terminal evaluations; failed evidence is never rewritten or promoted.
- [Phase ?]: Shadow retention is one idempotent research event with no strategy, monitor, plan, position, ledger, broker, provider, or market-action collaborator.
- [Phase ?]: Shadow public history uses hand-written allowlists and omits managed paths, raw data, account aliases, runner internals, exceptions, and client verdicts.
- [Phase ?]: Forecast maturity uses the existing unique forecast/horizon fact identity and one atomic outcome-plus-calibration transaction without another store.
- [Phase ?]: Forecast SSE queues are bounded transport only; every subscription and reconnect re-authorizes and reads committed persisted job state.
- [Phase ?]: Optional route shapes install once while each lifespan independently probes initializes recovers schedules and closes module-local services.
- [Phase ?]: Phase 05 frontend exports one status-aware shared request wrapper; no parallel transport library was introduced.
- [Phase ?]: Forecast SSE is hook-local transport only; terminal state is refreshed from persisted job status before object-local invalidation.
- [Phase ?]: Shadow retainability is derived only from two persisted passing IS/OOS evaluations; browser verdict and activation authority remain absent.
- [Phase ?]: Shadow normalizes bounded safe Wave 0 fixture fields but keeps production /evaluations authoritative and does not fabricate legacy /runs facts or a SHDW descriptor.
- [Phase ?]: Thesis and Forecast mount only for stock subjects; Portfolio keeps the original three-tab behavior and no optional requests.
- [Phase ?]: Optional panels stay mounted behind semantic tabpanels so object-local selection and scroll state survive tab switches without a global store.
- [Phase ?]: Phase 05 capability probes use QK.phase5Capabilities and never share the unrelated global capabilities cache identity.
- [Phase ?]: Forecast charts remain progressive enhancement; captioned quantile, path, provenance, history, and calibration tables are the accessible evidence surface.
- [Phase ?]: Lazy optional imports are checked against the process baseline so full-suite order cannot invalidate the real lifespan no-new-heavy-runtime guarantee.
- [Phase ?]: Forecast freshness is projected from the existing governed Kline repository; no second calendar, store, or browser-authored as-of authority is introduced.
- [Phase ?]: Real Kronos acceptance stays opt-in and local-only: absent approved assets report unavailable, while provisioned assets must pass exact provenance, network denial, and resource observation.
- [Phase ?]: Personal-project exception: 05-26 no longer requires a human supply approval record. Existing rejected 05-28/05-40 summaries remain historical records only.
- [Phase ?]: Forecast supply remains fail-closed on missing or mismatched immutable revision and SHA-256 values, but those values are no longer gated by reviewer identity or approval paperwork.
- [Phase ?]: Thesis check/history pages self-identify with instrument/version display identity (WR-03)
- [Phase ?]: Executable Kronos identity is destination SHA-256 map + config/weight digests, not UPSTREAM revision alone.
- [Phase ?]: Modules load via unique _athena_kronos_* package names from source_dir; preloaded shadows outside source are rejected.
- [Phase ?]: IPC is length-capped JSON frames over a one-way Pipe; cleanup terminate/kill reaps process group.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1 planning must map the existing tickflow, PanWatch, and Hermes extension points before choosing package and synchronization boundaries.
- 05-26, 05-27, 05-39, and 05-29 remain to be implemented and verified; their former 05-40 approval dependency was removed for this personal project.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Optional enhancement | Shadow Account, thesis tracking, and Kronos forecasting | Phase 5 / v2 | 2026-07-10 |
| Supply identity | Human approval paperwork | Removed for personal project | 2026-07-24 |

## Session Continuity

Last session: 2026-07-25T15:13:34.000Z
Stopped at: Executing 05-39 after 05-27
Resume file: None
