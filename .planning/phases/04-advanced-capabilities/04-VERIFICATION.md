---
phase: 04-advanced-capabilities
verified: 2026-07-14T03:39:01Z
status: gaps_found
score: 2/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
next_action: "Plan and implement the three server-side safeguard fixes below, add boundary regressions, then re-run Phase 04 verification."
gaps:
  - truth: "Researcher can progress a hypothesis through a sandboxed experiment and recorded feedback, then evaluate an evolved strategy for promotion through explicit gates."
    status: failed
    reason: "The authorized research asset is not server-bound to the strategy executed by the experiment runner; a caller can submit a different installed strategy_id."
    artifacts:
      - path: backend/app/advanced/api.py
        issue: "The specification route authorizes research_asset_id only and forwards the caller's complete data_scope unchanged."
      - path: backend/app/advanced/experiments.py
        issue: "The service validates scope shape but never verifies strategy_id against the persisted asset binding."
      - path: backend/app/advanced/governed_runner.py
        issue: "The runner passes the unverified strategy_id directly into StrategyBacktestConfig."
    missing:
      - "Resolve the persisted strategy-to-research-asset binding on the server and derive or require the matching strategy_id before any specification is created."
      - "Defend the invariant in ExperimentService or the runner and add a public-route regression proving a mismatched strategy creates no specification, worker, or sandbox evidence."
  - truth: "Operator can start an authorized agent job for an allowed market and instrument while rate-limited requests are rejected before work starts."
    status: failed
    reason: "Task-specific AdvancedPolicy.rate_limits are collapsed to max(...) and durable rate windows omit task_type, so lower-quota task classes can exceed their configured limit."
    artifacts:
      - path: backend/app/main.py
        issue: "advanced_operator_policy sets quota_per_window=max(advanced_policy.rate_limits.values())."
      - path: backend/app/advanced/repository.py
        issue: "Rate-window acquisition and start-time revalidation key only by principal/policy/window, not task_type."
      - path: backend/app/advanced/jobs.py
        issue: "Creation and prepare_to_start both use the collapsed policy quota."
    missing:
      - "Carry a task-specific quota through authorization, job acquisition, and execution-start revalidation."
      - "Add task_type to the durable rate-window identity/query and migration trigger, then prove experiment and strategy-evaluation buckets exhaust independently of research_draft."
  - truth: "The real-host fixture rejects malformed bars, absent required benchmark history, insufficient coverage, and no eligible signal before readiness."
    status: failed
    reason: "FixtureDailyBar and FixtureBundle validate only structure/read-only files and non-empty index_daily; invalid OHLC, finite/positive values, timestamp, chronological coverage, and configured benchmark are accepted and written to the governed lake."
    artifacts:
      - path: backend/app/contracts/market_data.py
        issue: "FixtureDailyBar has unconstrained floats/quote_ts and MarketDataFixtureFile accepts arbitrary index_daily contents."
      - path: backend/app/jobs/daily_pipeline.py
        issue: "The fixture pipeline appends daily/index bars without an advanced-host preflight."
      - path: backend/app/contracts/validator.py
        issue: "The fixture validation checks schema, primary keys, and market time, not OHLC/value/order/benchmark/readiness invariants."
    missing:
      - "Add an advanced-host fixture preflight that requires the configured benchmark, chronological unique coverage, finite positive values, valid OHLC ordering, positive in-session timestamps, and required history/window coverage before any lake write."
      - "Add startup regressions for every rejected shape, including missing 000300.SH and no eligible required signal."
---

# Phase 04: Advanced Capabilities Verification Report

**Phase Goal:** Researchers and operators can use advanced research and automation workflows within explicit promotion, authorization, audit, and execution safeguards.

**Verified:** 2026-07-14T03:39:01Z  
**Status:** `gaps_found`  
**Re-verification:** No — prior report contained no structured gaps; this is an independent goal-backward verification against committed `HEAD` and the current `04-REVIEW.md`.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | User can review an attributed market viewpoint, identify a material stance change, and inspect its confidence-aware performance result. | ✓ VERIFIED | The focused host Playwright scenario created an initial viewpoint, used visible revision/correction/evaluation controls, rendered `材料立场变化`, server evaluation, and calibration; it passed. `ViewpointPanel` receives server projections rather than calculating return values in the browser. |
| 2 | Researcher can progress a hypothesis through a sandboxed experiment and recorded feedback, then evaluate an evolved strategy for promotion through explicit gates. | ✗ FAILED | The happy-path host scenario passed, but `api.py:356-365` authorizes only `research_asset_id`; `experiments.py:36-81` persists an arbitrary schema-valid `strategy_id`; `governed_runner.py:93-118` executes it. This bypasses the persisted asset-to-strategy binding on direct API calls. |
| 3 | Operator can start an authorized agent job for an allowed market and instrument, observe SSE progress, and inspect its audit summary; unauthorized, out-of-allowlist, or rate-limited requests are rejected before work starts. | ✗ FAILED | The host scenario covers the configured one-per-hour fixture branch, but `main.py:243-253` converts the per-task policy to `max(...)`; `repository.py:164-205` has no task_type in rate-window identity or revalidation. The configured lower task limits are not enforced. |
| 4 | Researcher can submit a custom strategy only when its machine-readable contract, AST, imports, timeout, and memory constraints pass validation, and can review the constrained run's result or failure record. | ✓ VERIFIED | The host Playwright scenario submitted the hash-bound source to the real endpoint and observed `affirmative_isolation_proved`; the focused backend gate includes production-host and hostile sandbox contracts. The normal lifespan wires `LinuxIsolationLauncher` in `main.py:274-278`. |
| 5 | Real-host acceptance starts only after its governed fixture satisfies the documented market-data, benchmark, coverage, and eligible-signal safeguards. | ✗ FAILED | `market_data.py:28-60` has no numeric/order/timestamp validators; `FixtureBundle.load()` only requires a non-empty index_daily list in advanced-host mode; `daily_pipeline.py:88-93` writes it without a preflight. Invalid data can reach readiness. |

**Score:** **2/5** truths verified (0 present-but-behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/app/advanced/api.py` + `experiments.py` + `governed_runner.py` | Authorized immutable experiment lineage drives only the bound strategy. | ✗ WIRED BUT UNSAFE | The route, service, and runner are substantive and connected, but their data flow preserves a caller-controlled strategy ID rather than the server binding. |
| `backend/app/main.py` + `authorization.py` + `jobs.py` + `repository.py` | Policy-derived, task-specific quota is durable at creation and rechecked before work. | ✗ WIRED BUT UNSAFE | Durable acquisition, start-time revalidation, audit, and SSE paths exist; task quota identity is collapsed and cross-task. |
| `backend/app/contracts/market_data.py` + `jobs/daily_pipeline.py` | Advanced-host fixture input fails closed before lake ingestion. | ✗ INSUFFICIENT | The artifacts load and write fixture data, but required semantic market-data validation is missing. |
| `backend/app/advanced/sandbox.py` + `api.py` + `projections.py` | Strict custom-source admission and terminal safe run review. | ✓ VERIFIED | Substantive AST/hash/proof path is registered by lifespan; focused backend and real-host browser execution exercised its affirmative branch and safe projection. |
| `frontend/e2e/phase4-advanced-capabilities.host.spec.ts` | Non-intercepted real-host workflow coverage. | ✓ VERIFIED | Three serial scenarios passed against spawned FastAPI/Uvicorn through the Vite proxy and root SSE. Source inspection found no `page.route`, `context.route`, or `route.fulfill` handler. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| Advanced experiment specification route | `ExperimentService.create_specification` | `payload.model_dump()` at `api.py:360-362` | ✗ UNSAFE | The link forwards the browser-supplied `data_scope.strategy_id` rather than a server-resolved binding. |
| `ExperimentService` | `StrategyBacktestConfig` | Frozen scope → governed runner `_config()` | ✗ UNSAFE | `governed_runner.py:96-108` accepts and uses the unverified ID. |
| `AdvancedPolicy.rate_limits` | Durable rate window and start-time revalidation | `main.py` → `jobs.py` → `repository.py` | ✗ UNSAFE | `max(...)` and a window key without task_type defeat policy-specific limits at both endpoints. |
| Fixture bundle | Governed data lake | `FixtureProvider` → `run_phase1_fixture_sync` → `append_daily`/`append_index_daily` | ✗ UNSAFE | The path is active but no semantic fixture preflight protects it. |
| Sandbox form/API | `LinuxIsolationLauncher` terminal record | Same-origin host request to `/api/advanced/sandbox/submissions` | ✓ WIRED | The actual host test reached the terminal affirmative-isolation branch; unavailable capability remains an explicit pre-spawn branch in the scenario. |
| Job state/audit | Root scoped SSE | Job lifecycle → `QuoteService.notify_advanced_progress` → `/api/intraday/stream` | ✓ WIRED | The first and third host scenarios passed and observed authorized SSE/audit plus rejected-path non-delivery. This does not repair the independent quota-policy flaw. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `ViewpointPanel` | Immutable viewpoints/evaluations/calibration | Real advanced API and governed snapshot route in host test | Yes | ✓ FLOWING |
| `AdvancedResearchPanels` experiment flow | `research_asset_id` and `strategy_id` | Server binding endpoint plus browser request scope | Partially — binding is displayed, but API accepts mismatched strategy_id | ✗ HOLLOW SAFEGUARD |
| Job/SSE flow | Job/audit/stage projection | Operational SQLite and real root SSE | Yes | ✓ FLOWING, with unsafe per-task quota enforcement |
| Advanced-host governed fixture | Daily/index bars | Read-only JSON → fixture pipeline → Parquet lake | Yes, but invalid source values are not rejected | ✗ UNSAFE INPUT FLOW |

### Focused Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Phase 04 backend contracts and host integration | `cd backend && timeout 120s uv run pytest tests/advanced/test_production_host.py tests/advanced/test_viewpoints.py tests/advanced/test_evolution.py tests/advanced/test_sandbox.py -q` | `90 passed, 29 warnings in 50.97s` | ✓ PASS |
| Real FastAPI/Vite host workflows | `cd frontend && timeout 240s pnpm exec playwright test e2e/phase4-advanced-capabilities.host.spec.ts --project=phase4-fastapi-host` | `3 passed (18.3s)`; actual sandbox branch printed `affirmative_isolation_proved` | ✓ PASS |

These focused passes prove the exercised happy paths and denial scenarios, but do not override the directly observed server-side provenance, quota, and fixture-input violations above. The existing host quota fixture assigns every task type a quota of `1`, so it cannot distinguish the collapsed production policy buckets.

### Requirements Coverage

| Requirement | Source plans | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| **ADV-01** | 04-01, 04-05, 04-09, 04-10, 04-12, 04-16, 04-18, 04-21 | Attributed immutable viewpoints, material changes, and confidence-aware outcome review. | ✓ SATISFIED (warning below) | Focused host scenario 1 passed from revision/correction through governed evaluation/calibration. |
| **ADV-02** | 04-01, 04-06, 04-09, 04-11, 04-12, 04-17, 04-18, 04-21 | Frozen experiment specification, sandboxed governed run, and recorded feedback cycle. | ✗ BLOCKED | A valid asset authorization can be paired with a different strategy identifier and executed by the runner. |
| **ADV-03** | 04-01, 04-06, 04-08, 04-09, 04-11, 04-12, 04-13, 04-17, 04-18, 04-21 | Completed research evidence evolves through five explicit gates to research-only promotion. | ✗ BLOCKED | Candidate/gate evidence can originate from the mismatched strategy run described under CR-01. |
| **SAFE-01** | 04-02, 04-04, 04-07, 04-08, 04-09, 04-10, 04-13, 04-19, 04-21 | Scoped authorization, allowlists, rate limits, idempotent jobs, audit, and SSE progress. | ✗ BLOCKED | The authorization/SSE mechanisms work, but per-task deployment rate limits are not enforced. |
| **SAFE-02** | 04-03, 04-04, 04-07, 04-09, 04-14, 04-15, 04-18, 04-21 | Hash-bound contract, AST/import/resource validation, fail-closed sandbox, and safe result review. | ✓ SATISFIED | Host run used the real Linux launcher and terminal review; backend contracts passed. |

All five Phase 04 requirements are declared by at least one plan; no orphaned requirement was found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `backend/app/advanced/api.py` / `viewpoints.py` / `repository.py` | Review CR-04 trace | Repeated evaluation appends duplicate facts which calibration aggregates as independent samples. | ⚠️ Warning | Confidence buckets can be inflated by repeat evaluation of one immutable viewpoint version. Add idempotency or aggregate one deterministic terminal outcome per version. |

No `TBD`, `FIXME`, or `XXX` debt marker was found in the inspected Phase 04 runtime, UI, and host-test files. The limited `return {}`/`return null` matches are defensive helpers, graph node empty updates, optional query display, or blank optional form parsing; they are not user-visible stubs on an exercised Phase 04 flow.

## Gaps Summary

Phase 04's visible happy paths and its focused host suite work, but the phase goal is **not achieved** because three safeguard boundaries are observably violated in committed code:

1. **Provenance bypass:** research-asset authorization does not constrain the strategy that actually runs.
2. **Quota bypass:** task-specific limits become one highest shared quota bucket.
3. **Unsafe host readiness:** malformed or benchmark-inadequate fixture data can be ingested and served.

The Phase 4 `ROADMAP.md` still shows stale plan-count/status bookkeeping (`18/19`) despite plans 20 and 21 artifacts. This is informational and not used to defer any gap; Phase 5 does not explicitly schedule these safety fixes.

**Next action:** implement the three structured gaps above with public-boundary regressions, then re-run this verification. The calibration-duplicate warning should be fixed in the same remediation wave or explicitly accepted by the developer; it must not be silently treated as independent confidence evidence.

---

_Verified: 2026-07-14T03:39:01Z_  
_Verifier: Claude (gsd-verifier)_
