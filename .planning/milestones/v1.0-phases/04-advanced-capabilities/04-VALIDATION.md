---
phase: 04
slug: advanced-capabilities
status: validated
nyquist_compliant: true
wave_0_complete: true
validated_at: 2026-07-27T09:15:39+08:00
plans_audited: 27
tasks_mapped: 57
requirements_covered: 5
test_gaps: 0
current_host_reproduction: partial
external_linux_evidence: attested-not-rerun
---

# Phase 04 Validation Strategy

## Validation verdict

**VALIDATED — Nyquist coverage is complete; current-host reproduction is partial.**

All 27 executed plans and all 57 plan tasks have a concrete automated evidence path. No missing test or untested Phase 04 requirement was found, so this audit adds no Wave 0 tests. The current Windows run passed the portable backend, TypeScript, fixture-browser, sandbox, and API-coverage gates. It did not reproduce the Linux-only governed-runner and real-host isolation gates; those remain supported by the accepted Linux evidence in `04-VERIFICATION.md`, not by this Windows run.

This distinction is intentional:

- **Coverage verdict:** complete. Every Phase 04 task and requirement has an automated test or deterministic gate.
- **Current Windows execution verdict:** partial. Three governed-runner assertions observed `resource_limited`, and the real-host Playwright harness did not reach readiness.
- **Linux isolation verdict:** previously proved. The 2026-07-15 verification records 213 passing backend tests, 10 passing fixture-browser tests, 3 passing real-host tests, and the `affirmative_isolation_proved` capability branch.
- **Manual-only evidence:** none is required for requirement closure. Responsive and keyboard semantics are asserted by the fixture-browser suite; visual/aesthetic review remains optional rather than a requirement gate.

## Scope and source inventory

| Source | Audit result |
|---|---|
| `04-01-PLAN.md` through `04-27-PLAN.md` | 27/27 read |
| `04-01-SUMMARY.md` through `04-27-SUMMARY.md` | 27/27 present; all report `status: complete` |
| Plan tasks | 57/57 mapped below |
| `04-VERIFICATION.md` | `status: passed`, score 5/5, no requirement gaps |
| Requirements | `ADV-01`, `ADV-02`, `ADV-03`, `SAFE-01`, `SAFE-02` all mapped |

## Current audit execution

| Gate | Command / evidence | Result | Classification |
|---|---|---|---|
| Advanced backend plus dependency contracts | `cd backend && .\.venv\Scripts\python.exe -m pytest tests\advanced tests\research\test_strategy_experiment_handoff.py tests\test_market_data_fixture_contract.py tests\test_phase1_fixture_sync.py -q` | **190 passed, 3 failed, 43 warnings** in 188.08s | PARTIAL — all three failures are Linux governed-runner expectations in `test_production_host.py`; Windows returned `resource_limited` |
| SAFE-02 portable sandbox matrix | `cd backend && .\.venv\Scripts\python.exe -m pytest tests\advanced\test_sandbox.py -q` | **74 passed** in 48.56s | PASS |
| TypeScript build | `cd frontend && .\node_modules\.bin\tsc.cmd -b` | PASS in 23.4s | PASS |
| Fixture-browser acceptance | `cd frontend && node .\node_modules\@playwright\test\cli.js test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium --reporter=list` | **10 passed** in 73.1s | PASS |
| Real-host browser acceptance | `cd frontend && node .\node_modules\@playwright\test\cli.js test e2e/phase4-advanced-capabilities.host.spec.ts --project=desktop-chromium --reporter=list` | First attempt: host readiness failure, 1 failed / 2 not run in 54.8s. Warm retry exceeded the 184s outer limit. | UNVERIFIED ON WINDOWS — no requirement result inferred |
| External SDK surface | `node C:\Users\Admin\.codex\gsd-core\bin\gsd-tools.cjs check api-coverage-verify-pre .planning\phases\04-advanced-capabilities --raw` | PASS: 18 capabilities, 8 integrated, 10 explicit opt-outs | PASS |

The three current backend failures are:

1. `test_governed_runner_persists_applied_limits_and_completed_feedback`
2. `test_spawned_governed_backtest_completes_split_evidence_within_budget`
3. `test_governed_runner_reaps_blocked_work_and_rejects_feedback`

They are retained as honest platform evidence rather than suppressed or relabeled. Both real-host attempts left an exact test-owned uvicorn process on port 3018; each residual process was identified by command line, stopped, and the port was verified clear. The package-manager-created untracked `frontend/pnpm-workspace.yaml` residue was also removed and is not part of this validation.

## Requirement coverage

| Requirement | Primary automated evidence | Current status | Accepted closure |
|---|---|---|---|
| `ADV-01` — immutable attributed viewpoints and calibrated outcomes | `test_viewpoints.py`, `test_experiments.py`, `test_market_data_fixture_contract.py`, fixture-browser viewpoint flow | PASS on current portable gates | COVERED |
| `ADV-02` — reproducible experiment execution and append-only feedback | `test_experiments.py`, `test_production_host.py`, strategy-experiment handoff test, fixture-browser experiment flow | Portable behavior passes; Linux runner completion not reproduced on Windows | COVERED by automated tests plus accepted Linux run |
| `ADV-03` — constrained evolution and explicit five-gate promotion | `test_evolution.py`, `test_workflow.py`, `test_production_host.py`, fixture-browser promotion flow | Portable behavior passes; governed runner branch is platform-partial | COVERED by automated tests plus accepted Linux run |
| `SAFE-01` — two-phase scoped authorization, durable revalidation, safe projection | `test_authorization_jobs.py`, `test_api_sse.py`, `test_workflow.py`, real-host denial tests | Portable authorization gates pass; current real-host gate did not start | COVERED by automated tests plus accepted Linux run |
| `SAFE-02` — fail-closed custom code and affirmative isolation proof | `test_sandbox.py` (74 current passes), `test_production_host.py`, real-host sandbox path | Fail-closed matrix passes; affirmative Linux capability not reproducible on Windows | COVERED by current fail-closed evidence plus accepted Linux proof |

## Complete plan-to-test map

Status legend:

- **PASS** — relevant current portable gates passed.
- **PLATFORM-PARTIAL** — tests exist and portable behavior passed, but a Linux governed-runner assertion did not reproduce on Windows.
- **LINUX-ATTESTED** — acceptance depends on the previously accepted Linux real-host evidence; the current Windows host run is not counted.

| Plan | Task IDs mapped | Requirements | Automated evidence | Status |
|---|---|---|---|---|
| 04-01 | 04-01-01, 04-01-02, 04-01-03 | ADV-01/02/03 | `test_viewpoints.py`, `test_experiments.py`, `test_evolution.py` | PASS |
| 04-02 | 04-02-01, 04-02-02, 04-02-03 | SAFE-01 | `test_authorization_jobs.py`, `test_api_sse.py`, `test_workflow.py` | PASS |
| 04-03 | 04-03-01, 04-03-02 | SAFE-02, ADV-01/02/03, SAFE-01 | `test_sandbox.py`; fixture-browser spec | PASS |
| 04-04 | 04-04-01, 04-04-02 | ADV-01/02/03, SAFE-01/02 | Full advanced backend suite exercises domain projections and SQLite repositories | PASS |
| 04-05 | 04-05-01, 04-05-02 | ADV-01 | `test_viewpoints.py` | PASS |
| 04-06 | 04-06-01, 04-06-02 | ADV-02/03 | `test_experiments.py`, `test_evolution.py` | PASS |
| 04-07 | 04-07-01, 04-07-02 | SAFE-01/02 | `test_authorization_jobs.py`, `test_sandbox.py`, `test_production_host.py` | PLATFORM-PARTIAL |
| 04-08 | 04-08-01, 04-08-03 | ADV-03, SAFE-01 | `test_workflow.py`, `test_api_sse.py` | PASS |
| 04-09 | 04-09-01, 04-09-02 | ADV-01/02/03, SAFE-01/02 | Advanced API, authorization, sandbox, and SSE tests | PASS |
| 04-10 | 04-10-01, 04-10-02 | ADV-01, SAFE-01 | TypeScript build; fixture-browser viewpoint and authorization flows | PASS |
| 04-11 | 04-11-01, 04-11-02 | ADV-02/03, SAFE-01/02 | TypeScript build; 10-case fixture-browser suite | PASS |
| 04-12 | 04-12-01, 04-12-02 | ADV-01/02/03 | `test_viewpoints.py`, `test_production_host.py` | PLATFORM-PARTIAL |
| 04-13 | 04-13-01, 04-13-02 | SAFE-01, ADV-03 | `test_authorization_jobs.py`, `test_workflow.py`, `test_api_sse.py` | PASS |
| 04-14 | 04-14-01, 04-14-02 | SAFE-02, ADV-01/02/03, SAFE-01 | `test_sandbox.py`; real-host browser spec | LINUX-ATTESTED |
| 04-15 | 04-15-01, 04-15-02, 04-15-03 | SAFE-02 | `test_sandbox.py`, terminal-run projection tests, real-host proof | LINUX-ATTESTED |
| 04-16 | 04-16-01, 04-16-02 | ADV-01 | `test_viewpoints.py`, viewpoint API tests | PASS |
| 04-17 | 04-17-01, 04-17-02 | ADV-02/03 | `test_experiments.py`, `test_evolution.py`, `test_production_host.py` | PLATFORM-PARTIAL |
| 04-18 | 04-18-01, 04-18-02 | ADV-01/02/03, SAFE-02 | TypeScript build; fixture-browser immutable revision and terminal-run flows | PASS |
| 04-19 | 04-19-01, 04-19-02 | ADV-01/02/03, SAFE-01/02 | `test_production_host.py`; real-host browser spec | LINUX-ATTESTED |
| 04-20 | 04-20-01 | ADV-01/02/03, SAFE-01/02 | `api-coverage-verify-pre` | PASS |
| 04-21 | 04-21-01, 04-21-02, 04-21-03 | ADV-01/02/03, SAFE-01/02 | Production-host fixture tests; real-host browser spec | LINUX-ATTESTED |
| 04-22 | 04-22-01, 04-22-02 | ADV-02/03, SAFE-02 | Strategy-experiment handoff, `test_experiments.py`, governed-runner binding tests | PASS |
| 04-23 | 04-23-01, 04-23-02 | SAFE-01 | `test_authorization_jobs.py`, authorization API quota tests | PASS |
| 04-24 | 04-24-01, 04-24-02 | ADV-01/02/03, SAFE-01/02 | `test_market_data_fixture_contract.py`, `test_phase1_fixture_sync.py` | PASS |
| 04-25 | 04-25-01, 04-25-02 | ADV-01 | Canonical evaluation, idempotency, and calibration cases in `test_viewpoints.py` | PASS |
| 04-26 | 04-26-01, 04-26-02 | ADV-01/02/03, SAFE-01/02 | Experiment binding, authorization, viewpoint, production-host denial tests | PLATFORM-PARTIAL |
| 04-27 | 04-27-01, 04-27-02 | SAFE-01 | Policy-consistent acquisition and queued revalidation cases in authorization/production-host tests | PASS |

All 57 task identifiers are present in the table. Plan 04-08 intentionally contains task IDs `01` and `03`, matching the executed plan rather than inventing a missing `02`.

## Linux and real-host evidence boundary

The current machine is Windows. It can prove fail-closed behavior, but it cannot produce the affirmative Linux namespace/cgroup/process-isolation evidence required by SAFE-02. The current real-host harness also failed to reach a usable readiness state, so none of its three browser cases is claimed as a current pass.

The accepted external evidence is the completed Phase 04 verification dated 2026-07-15:

- advanced plus backtest backend gate: **213 passed**
- fixture-browser gate: **10 passed**
- real FastAPI host gate: **3 passed**
- isolation capability: **`affirmative_isolation_proved`**
- human verification: **not required**

This audit trusts that recorded verification as historical Linux evidence and clearly separates it from current execution. Re-running the three real-host cases on a supported Linux production launcher remains the recommended release-host smoke check, but it is an environment reproduction item, not a Nyquist test-authoring gap.

## Gap classification

| Candidate gap | Classification | Action |
|---|---|---|
| Three Windows governed-runner failures | Platform mismatch / fail-closed observation | Keep visible; do not weaken Linux assertions |
| Current real-host suite did not become ready | Environment execution gap | Preserve prior Linux evidence; rerun on supported Linux host when available |
| Missing Phase 04 automated tests | None found | No Wave 0 work |
| Missing plan/task mapping | Closed by this audit | 57/57 mapped |
| Missing requirement mapping | None | 5/5 covered |

## Final checklist

- [x] All 27 plans and summaries audited.
- [x] All 57 plan tasks mapped to automated evidence.
- [x] All five Phase 04 requirements covered.
- [x] Portable SAFE-02 sandbox matrix passes on the current host.
- [x] TypeScript and fixture-browser gates pass.
- [x] API coverage matrix passes with no undecided capability.
- [x] Linux-only and current-host evidence are explicitly separated.
- [x] No synthetic pass was assigned to the failed current real-host run.
- [x] No new tests are required for Nyquist closure.
