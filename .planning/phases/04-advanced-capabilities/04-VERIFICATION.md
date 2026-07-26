---
phase: 04-advanced-capabilities
verified: 2026-07-15T06:28:58Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
behavior_unverified_items: []
gaps: []
---

# Phase 04: Advanced Capabilities Verification Report

**Phase Goal:** Researchers and operators can use advanced research and automation workflows within explicit promotion, authorization, audit, and execution safeguards.

**Verified:** 2026-07-15T06:28:58Z
**Status:** `passed`
**Re-verification:** Yes - all previously reported backend, browser, build, and deployment-host gaps were reproduced, corrected, and rerun.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | User can review an attributed market viewpoint, identify a material stance change, and inspect a confidence-aware performance result. | ✓ VERIFIED | `AnalysisWorkspace` renders `ViewpointPanel` ([frontend/src/components/analysis/AnalysisWorkspace.tsx](/root/source/AthenaQuant/frontend/src/components/analysis/AnalysisWorkspace.tsx:50)); it calls typed server DTO methods and invalidates object-scoped keys. `ViewpointService.evaluate_viewpoint()` reuses the canonical terminal fact before new evaluation ([backend/app/advanced/viewpoints.py](/root/source/AthenaQuant/backend/app/advanced/viewpoints.py:76)). Targeted stance test passed and the public host selection passed. |
| 2 | Researcher can progress a hypothesis through a sandboxed experiment and recorded feedback, then evaluate an evolved strategy for promotion through explicit gates. | ✓ VERIFIED | The governed runner freezes aggregate and split panels before spawning, verifies artifact scope/checksums in the worker, and returns independent execution evidence. The full advanced/backtest suite, fixture browser workflow, and real-host experiment → feedback → five gates → promotion flow pass. |
| 3 | Operator can start an authorized scoped agent job, observe SSE progress and audit; unauthorized, out-of-allowlist, or rate-limited requests are rejected before work. | ✓ VERIFIED | `AdvancedJobService.prepare_to_start()` validates durable authorization and current policy before `_advance()` ([backend/app/advanced/jobs.py](/root/source/AthenaQuant/backend/app/advanced/jobs.py:119)). The real-host gate proves unauthenticated/out-of-scope denial, revoked-before-work behavior without unauthorized SSE, independent task quota capacity, and same-task rate limiting. |
| 4 | Researcher can submit a custom strategy only through contract, AST/import, timeout, memory and isolation controls, and review a constrained terminal result or failure. | ✓ VERIFIED | `CustomStrategySandboxService.submit()` checks hash, contract and AST before isolation proof/spawn and returns allowlisted terminal facts. The real FastAPI host exercised the production Linux launcher and recorded `affirmative_isolation_proved`; hostile, constraint, cleanup, and redaction tests also pass. |
| 5 | Phase 04's declared LangGraph SDK surface has explicit integration or opt-out decisions tied to its implementation. | ✓ VERIFIED | `node /root/.omp/agent/gsd-core/bin/gsd-tools.cjs check api-coverage.verify-pre .planning/phases/04-advanced-capabilities --raw` passed: `18` capabilities, `8` integrated, `10` explicitly opted out in `COVERAGE.md`. |

**Score:** **5/5** truths verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/app/advanced/viewpoints.py` and `frontend/src/components/advanced/ViewpointPanel.tsx` | Immutable viewpoint evaluation and review UI | ✓ VERIFIED | Substantive, wired through Analysis workspace, and targeted behavior tests pass. |
| `backend/app/advanced/experiments.py`, `governed_runner.py`, `evolution.py` | Server-bound experiment, feedback, candidate and gates | ✓ VERIFIED | Mandatory server binding remains fail-closed. Parent-frozen, checksum-verified aggregate/split panels cross the spawned worker boundary; full backend and real-host workflows pass. |
| `frontend/src/components/advanced/AdvancedResearchPanels.tsx` and `frontend/e2e/phase4-advanced-capabilities.spec.ts` | Backtest experiment/evolution/sandbox review workflow | ✓ VERIFIED | Installed strategy selection resolves the read-only server binding before advanced data/actions. All 10 desktop contracts pass. |
| `backend/app/advanced/jobs.py`, `repository.py`, and authorization tests | Scoped job authorization, audit, quota and SSE rejection-before-work | ✓ VERIFIED | Durable policy provenance is checked before quota/start work; focused unit and real-host checks pass. |
| `backend/app/advanced/sandbox.py` and `test_sandbox.py` | Fail-closed sandbox admission and safe terminal DTOs | ✓ VERIFIED | Hostile/terminal-redaction coverage passes and the real-host production launcher observed `affirmative_isolation_proved`. |
| `frontend/src/pages/Backtest.tsx` | Buildable host of advanced Backtest UI | ✓ VERIFIED | The optimizer tab now renders `StrategyOptimizer`; `pnpm build` succeeds. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `AnalysisWorkspace` | `ViewpointPanel` | Render with object-local display/server subject mapping | ✓ WIRED | [AnalysisWorkspace.tsx](/root/source/AthenaQuant/frontend/src/components/analysis/AnalysisWorkspace.tsx:50) passes server-authorized subject; panel calls typed `api.advanced*` methods. |
| `Backtest` | `AdvancedResearchPanels` | Installed strategy ID -> server binding query -> typed panel props | ✓ WIRED | Browser contracts select the installed strategy, assert the read-only server strategy identity, and exercise bound experiments/candidates without browser-supplied research authority. |
| `ExperimentService` | `StrategyBacktestExperimentCollaborator` | Server-bound persisted specification -> parent-frozen panels -> governed worker | ✓ WIRED | `ExperimentService` rechecks the immutable binding; the collaborator freezes aggregate/split panels in the parent and the worker verifies scope and all checksums before execution. |
| `AdvancedJobService` | scoped advanced-progress SSE | `_advance()` only after durable authorization/current-policy revalidation | ✓ WIRED | Policy-transition and real-host task-specific quota checks pass with no rejected unauthorized work event. |
| `CustomStrategySandboxService` | Linux launcher -> safe terminal projection | Pre-spawn proof gates `spawn`, then persists/provides allowlisted terminal record | ✓ WIRED | Real-host execution produced `affirmative_isolation_proved` and a bounded terminal projection; fail-closed unit branches remain covered. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| Viewpoint panel | `viewpoints`, `calibration`, evaluation DTO | Authorized advanced API and immutable SQLite evaluation ledger | Yes | ✓ FLOWING |
| Advanced research panel | binding, experiment runs, candidates, sandbox terminal DTOs | Server binding endpoint and advanced APIs | Yes | ✓ FLOWING |
| Agent job service | authorization policy revision, task window, audit cursor | Immutable SQLite authorization/policy/job/rate-window lineage | Yes | ✓ FLOWING |
| Sandbox | contract/source hash, proof, terminal record | Request contract -> isolated launcher -> immutable SQLite facts | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Full advanced and backtest regression | `cd backend && uv run pytest tests/advanced tests/backtest -q` | `213 passed, 40 warnings` in 89.31s | ✓ PASS |
| Changed Python lint gate | `cd backend && uv run ruff check app/backtest/frozen_panel.py app/backtest/strategy.py app/advanced/governed_runner.py tests/backtest/test_frozen_panel_artifact.py tests/advanced/test_experiments.py tests/advanced/test_production_host.py` | `OK` | ✓ PASS |
| Frontend production build | `cd frontend && pnpm build` | TypeScript and Vite production build completed successfully | ✓ PASS |
| Phase 04 desktop browser contract | `cd frontend && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium --reporter=list` | `10 passed` in 22.6s | ✓ PASS |
| Phase 04 real FastAPI host gate | `cd frontend && pnpm exec playwright test e2e/phase4-advanced-capabilities.host.spec.ts --project=phase4-fastapi-host --reporter=list` | `3 passed` in 19.7s; capability branch `affirmative_isolation_proved` | ✓ PASS |
| Material stance behavior | `cd backend && timeout 30s uv run pytest -q tests/advanced/test_viewpoints.py::test_structured_stance_deltas_classify_material_changes_but_keep_minor_revisions_visible` | `1 passed` | ✓ PASS |
| Five independent promotion gates | `cd backend && timeout 30s uv run pytest -q tests/advanced/test_evolution.py::test_every_independent_gate_is_required_and_aggregate_score_never_authorizes_promotion` | `5 passed` | ✓ PASS |
| Policy change denial before work | `cd backend && timeout 30s uv run pytest -q tests/advanced/test_authorization_jobs.py::test_policy_transition_rejects_queued_job_before_current_policy_quota_or_work` | `1 passed` | ✓ PASS |
| Bound experiment denial before evidence | `cd backend && timeout 30s uv run pytest -q tests/advanced/test_experiments.py::test_server_resolved_binding_is_immutable_and_denials_precede_all_experiment_evidence` | `1 passed` | ✓ PASS |
| Sandbox hostile admission, limits and safe projection | `cd backend && timeout 30s uv run pytest -q tests/advanced/test_sandbox.py::test_hostile_submission_is_rejected_before_any_host_execution tests/advanced/test_sandbox.py::test_runtime_constraints_terminate_the_process_group_cleanup_handoff_and_redact_output tests/advanced/test_sandbox.py::test_authorized_sandbox_run_api_lists_safe_terminal_records_without_cross_asset_disclosure` | `13 passed` | ✓ PASS |
| Public real-lifespan readiness/quota/calibration boundaries | `cd backend && timeout 45s uv run pytest -q tests/advanced/test_production_host.py -k 'accepts_valid_fixture_readiness or rejects_invalid_fixture_readiness or enforces_public_binding_and_task_specific_quota_boundaries or repeated_viewpoint_evaluation_is_canonical'` | `4 passed, 11 deselected, 9 existing Polars warnings` | ✓ PASS |

### Probe Execution

Step 7c: **SKIPPED**. No `scripts/**/tests/probe-*.sh` or phase-declared shell probe exists.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| **ADV-01** | 04-05, 04-12, 04-16, 04-18, 04-25, 04-26 | Attributed viewpoints, material changes and confidence-aware results | ✓ SATISFIED | UI/API wiring and targeted behavior plus public lifespan checks pass. |
| **ADV-02** | 04-06, 04-17, 04-18, 04-22, 04-26 | Frozen experiment, sandboxed run and feedback | ✓ SATISFIED | Full backend regression and both fixture/real-host browser workflows pass with independent aggregate and split evidence. |
| **ADV-03** | 04-01, 04-06, 04-08, 04-11, 04-17, 04-18, 04-22, 04-26 | Evolution and explicit promotion gates | ✓ SATISFIED | Real-host feedback, candidate creation, all five server-owned gates, and research-only promotion pass. |
| **SAFE-01** | 04-02, 04-07, 04-08, 04-10, 04-13, 04-23, 04-26, 04-27 | Scoped authorization, allowlists, quotas, idempotency, audit and SSE | ✓ SATISFIED | Current-policy and task-specific quota behavior pass before prohibited work/SSE. |
| **SAFE-02** | 04-03, 04-07, 04-11, 04-14, 04-15, 04-18, 04-22, 04-24, 04-26 | Contract- and sandbox-controlled strategy execution | ✓ SATISFIED | The production Linux launcher reached `affirmative_isolation_proved`; hostile/fail-closed and safe terminal DTO branches remain covered. |

No Phase 04 requirement is orphaned or deferred to Phase 05.

### Resolved Anti-Patterns

| File | Previous Pattern | Resolution |
| --- | --- | --- |
| `frontend/src/pages/Backtest.tsx` | Imported optimizer without rendering it | Optimizer tab now renders `StrategyOptimizer`; production build passes. |
| `frontend/e2e/phase4-advanced-capabilities.spec.ts` | Filled a read-only strategy projection and skipped installed-strategy selection | Scenarios select the installed strategy and assert the server-projected read-only identity. |
| `backend/app/advanced/governed_runner.py` | Spawned worker lacked parent-frozen governed panels | Parent prepares immutable Parquet artifacts; worker verifies schema, scope, metadata and panel checksums before use. |

### Human Verification Required

None. The real FastAPI/Vite host gate exercised the current Linux deployment environment and observed `affirmative_isolation_proved` from the production sandbox launcher.

### Gaps Summary

Phase 04 verification passes. The frontend builds, all fixture browser contracts pass, the complete advanced/backtest regression set passes, and the non-intercepted real-host workflow proves viewpoint, experiment/evolution, scoped job/SSE, and production sandbox behavior.

---

_Verified: 2026-07-15T06:28:58Z_
_Verifier: OMP gap-closure re-verification_
