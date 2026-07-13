---
phase: 04-advanced-capabilities
verified: 2026-07-13
status: passed
score: 4/4 roadmap truths verified; 5/5 requirements traced
plans_reviewed: 21/21
verification_scope:
  source_and_contracts: reviewed
  recorded_plan_21_backend_gate: 90 passed; 0 failed; 0 skipped
  recorded_plan_21_host_gate: 3 passed; 0 failed; 0 skipped
  recorded_plan_21_isolation_branch: affirmative_isolation_proved
  reported_api_coverage_gate: passed (18 capabilities; 8 integrate; 10 opt-out)
  commands_run_by_this_verification: none (per request)
re_verification:
  previous_status: gaps_found
  gaps_closed:
    - non_intercepted_host_full_workflows
    - host_execution_evidence_unknown
    - deployment_linux_private_root_proof
    - real_host_viewport_accessibility_evidence
---


# Phase 4: Advanced Capabilities Verification Report

**Phase goal:** Researchers and operators can use advanced research and automation workflows within explicit promotion, authorization, audit, and execution safeguards.

**Status: `passed`**

This goal-backward re-verification reads Plans and summaries 04-01 through 04-21, the roadmap, validation/coverage/review artifacts, current host acceptance source, and current advanced backend/frontend focused contracts. It supersedes the earlier `gaps_found` result: its Plan 19 blockers were accurate, but Plan 21 supplied later recorded execution evidence and the current three-scenario host suite.

No formatter, linter, build, or test command was run for this report. Test outcomes below are recorded Plan 21 evidence and the final backend-gate result supplied to this verifier, not newly executed results.

## Decision

**All four roadmap truths have current non-intercepted real-host evidence.** Plan 21's serial `phase4-fastapi-host` project passed all three scenarios against the spawned FastAPI lifespan, Vite same-origin reverse proxy, rendered authenticated session cookie, production API routes, operational SQLite state, governed fixture data, and root SSE. Its recorded deployment capability is `affirmative_isolation_proved`, not an inferred, unavailable, or unknown branch.

## Evidence Inventory

| Evidence | Recorded/observed result | Verification use and limit |
| --- | --- | --- |
| Plan 21 focused backend gate | **90 passed; 0 failed; 0 skipped; 29 warnings** in 70.96s | Exact final backend contract gate: production-host, viewpoints, evolution, and sandbox tests. Not rerun by this verifier. |
| Plan 21 real-host browser gate | **3 passed; 0 failed; 0 skipped** in 22.1s | Serial non-intercepted `phase4-fastapi-host` evidence for every roadmap workflow and rejection boundary. Not rerun by this verifier. |
| Current host acceptance source | **3 scenario contracts** | It starts real Uvicorn and uses browser-origin `/api` plus root `EventSource('/api/intraday/stream')`. Inspection found no `page.route`, `context.route`, or `route.fulfill` interception. |
| Plan 21 host capability classification | **`affirmative_isolation_proved`** | A real harmless sandbox submission reached a terminal record with a proof fingerprint and resource summary; the current spec also asserts the fail-closed alternative. |
| `04-REVIEW.md` | **clean; 0 active findings** | Static final-remediation review only; not runtime proof. |
| Plan 20 API-coverage gate | **passed** | `COVERAGE.md` records 18 LangGraph/checkpointer capabilities: 8 `INTEGRATE`, 10 `OPT-OUT`. |

## Roadmap Success Criteria

| # | Required truth | Current source/contract and recorded host evidence | Result |
| --- | --- | --- | --- |
| 1 | User can review an attributed viewpoint, material stance change, and confidence-aware performance. | Host scenario 1 uses the real Analysis UI for a material revision, correction, and server-owned evaluation; it renders immutable lineage, `材料立场变化`, correction reason, frozen `60`-day/`000300.SH` evaluation, and calibration. Current viewpoint contracts cover append-only facts, canonical policy provenance, governed/unevaluable outcomes, and low/medium/high calibration. | **VERIFIED** |
| 2 | Researcher can progress a hypothesis through a sandboxed experiment and recorded feedback, then evaluate an evolved strategy for promotion through explicit gates. | Host scenario 2 resolves the lifecycle-owned immutable `bullish_alignment` asset, creates and completes a frozen experiment, records feedback, creates a candidate, invokes five server-owned gates, and promotes with rationale to `registered_research_only`. Governed-run contracts require distinct aggregate/in-sample/out-of-sample executions; evolution contracts reject copied evidence and client gate authority. | **VERIFIED** |
| 3 | Operator can start an authorized agent job, observe scoped SSE/audit, while unauthorized, out-of-allowlist, or rate-limited work is rejected before start. | Host scenario 1 observes authorized root-SSE/audit state. Scenario 3 records unauthenticated `401`, out-of-scope `404`, revoked-before-execution rejection, rate-limit `409`, no non-rejected unauthorized SSE event, and safe audit projection. Current authorization/workflow/SSE contracts cover revalidation, durable stage-and-audit-before-publication, and scoped allowlisted projection. | **VERIFIED** |
| 4 | Researcher can submit a contract-bound strategy only after validation and inspect its constrained result or failure record. | Host scenario 2 submits a hash-bound harmless source through the actual sandbox UI. Plan 21 records a terminal affirmative proof record; the same scenario asserts the exact pre-spawn `isolation_unavailable` alternative with no new terminal run. Current sandbox contracts cover hostile-input rejection, observable proof, immutable terminal lineage, redaction, and cross-asset denial. | **VERIFIED** |

**Roadmap score: 4/4 fully verified.**

## Requirement Traceability

| Requirement | Current behavior verified | Evidence |
| --- | --- | --- |
| **ADV-01** | Immutable attributed lineage, material-change classification, correction, governed evaluation, and confidence-aware calibration are available from Analysis. | Plans 01/05/09/10/12/16/18/21; viewpoint/API contracts; host scenario 1. |
| **ADV-02** | Frozen runner scope produces a bounded completed governed experiment; feedback is append-only and completion-gated. | Plans 01/06/09/11/12/17/18/21; governed-run contracts; host scenario 2. |
| **ADV-03** | Candidate creation uses completed immutable evidence; five server-owned gates plus explicit rationale produce research-only registration without market action. | Plans 01/06/08/09/11/12/13/17/18/21; evolution contracts; host scenario 2. |
| **SAFE-01** | Server-derived authorization, rate enforcement, start-time revocation, durable audit/stage ordering, and root-SSE scope filtering reject prohibited work before execution. | Plans 02/04/07/08/09/10/13/19/21; API/SSE/host contracts; host scenarios 1 and 3. |
| **SAFE-02** | Same-request hash-bound admission, observable private-root isolation proof, resource limits, immutable terminal lineage, and authorized redacted run review are enforced. | Plans 03/04/07/09/14/15/18/21; sandbox/host contracts; host scenario 2 and recorded affirmative branch. |

Every Phase 4 requirement is traced to a current implementation contract and final real-host acceptance evidence.

## Prior-Gap Closure

| Prior gap | Closure evidence |
| --- | --- |
| Host suite covered only jobs/SSE and denials | The current host spec has three serial scenarios: viewpoint lifecycle plus job/SSE; immutable binding through experiment/feedback/five gates/promotion plus sandbox; and denial boundaries. Plan 21 records all three passed. |
| Plan 19 execution was `unknown` | `04-21-SUMMARY.md` records the exact focused backend and host commands, exit codes, elapsed times, pass/fail/skip counts, scenario coverage, and capability branch. |
| Positive Linux private-root proof was human-needed | Plan 21 records `affirmative_isolation_proved` from the real sandbox terminal branch. The implementation remains fail-closed if any host cannot establish the required observations. |
| Real-host viewport/accessibility evidence was human-needed | The current host scenarios exercise 1440×960, 1024×900, and 375×844 overflow instructions, 44px controls, tab keyboard navigation, alert/status states, and promotion-dialog focus containment/restoration; Plan 21 records this matrix as passed. |

## Non-Blocking Note

`ROADMAP.md` still has stale Phase 4 plan-count bookkeeping (`18/19`) despite the later Plan 20 and Plan 21 artifacts. It does not negate the observed roadmap truths; reconcile it through the planning workflow rather than in this verification report.

## VERIFICATION PASSED

---
_Verified: 2026-07-13_
_Verifier: Goal-backward phase verifier_
