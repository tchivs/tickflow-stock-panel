---
phase: 04-advanced-capabilities
verified: 2026-07-14T07:29:15Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "Operator task quotas remain durably enforced at creation and execution-start revalidation, including when the deployment policy revision changes."
  gaps_remaining: []
  regressions: []
---

# Phase 04: Advanced Capabilities Verification Report

**Phase Goal:** Researchers and operators can use advanced research and automation workflows within explicit promotion, authorization, audit, and execution safeguards.

**Verified:** 2026-07-14T07:29:15Z  
**Status:** `passed`  
**Re-verification:** Yes — after Plan 04-27 policy-transition remediation

## Goal Achievement

The roadmap supplies four success criteria. This re-verification retains the prior report's five concrete observable truths so that the repaired SAFE-01 boundary and the already-passed provenance, calibration, sandbox, and fixture safeguards are each checked independently.

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | User can review an attributed market viewpoint, identify a material stance change, and inspect one confidence-aware performance result per immutable version. | ✓ VERIFIED | `ViewpointService._append_revision()` classifies direction/rating/target/horizon/confidence changes as `material_stance_change` (`backend/app/advanced/viewpoints.py:199-227`). `evaluate_viewpoint()` returns the first terminal fact before querying data again (`:76-85`); repository canonical selection and calibration each select one deterministic terminal fact per immutable version (`repository.py:611-642`). Focused regression: 5 passed. |
| 2 | A researcher can create and run an experiment only for the exact persisted research-asset strategy binding; divergent lineage cannot create run, sandbox, feedback, candidate, gate, or promotion evidence. | ✓ VERIFIED | The public API resolves the server-owned binding before specification creation (`backend/app/advanced/api.py:115-135,379-390`). `ExperimentService` persists and rechecks `bound_strategy_id` on create/run/retry (`experiments.py:49-98,110-150,269-290`); `_bound_scope()` stops divergent records before backtest-service construction (`governed_runner.py:30-41,72-76`). Focused provenance and promotion-gate regression: 12 passed. |
| 3 | Operator agent jobs use task-specific durable quotas at creation and execution-start revalidation; denial occurs before work or advanced-progress SSE, including an A-to-B deployment policy transition. | ✓ VERIFIED | Creation records the current immutable policy fact and passes it to `acquire_authorized_job()` (`jobs.py:57-91`). The acquisition transaction joins the authorization's immutable policy revision and requires equality before a rate-window write or job insert, then charges only the joined authorization revision (`repository.py:181-227`). At execution start, the durable job→authorization→policy lineage is compared to the current policy before `quota_is_current()` or `_advance()` (`jobs.py:119-172`; `repository.py:159-170`). The rejection branch uses `transition_job_with_audit()` and returns before either work path (`jobs.py:174-216`) or progress publishing (`:238-267`). Focused unit plus two-real-lifespan host regression: 5 passed. |
| 4 | A researcher can submit a custom strategy only through a hash-bound contract, AST/import checks, affirmative isolation probe, resource limits, and a safe terminal record. | ✓ VERIFIED | The authenticated API requires a server-authorized parent asset and returns safe projections only (`api.py:475-532`). `CustomStrategySandboxService.submit()` validates contract/hash/AST before probe or spawn and records safe terminal facts (`sandbox.py:384-495,497-550`). `LinuxIsolationLauncher` requires fresh affirmative namespace, filesystem, network, cleanup, and resource-limit evidence before spawn (`sandbox.py:57-214`). Focused sandbox suite: 44 passed. |
| 5 | Advanced-host fixture readiness rejects malformed bars, missing benchmark history, inadequate ordered coverage, and no eligible required signal before any governed-lake mutation; valid fixtures remain viable. | ✓ VERIFIED | Lifespan loads and validates the deployment-owned readiness descriptor before fixture synchronization and `DataStore` construction (`main.py:37-94`). The pipeline invokes provider preflight before it constructs a datastore or writes a lake file (`daily_pipeline.py:58-85`). Preflight validates finite positive OHLCV/amount, session timestamps, ordered unique histories, `000300.SH`, required coverage/warmup, and a real bullish-alignment signal (`market_data.py:213-301`). Fixture pipeline regression: 20 passed; real-host readiness/public-boundary regression: 4 passed. |

**Score:** **5/5** truths verified (0 present, behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/app/advanced/repository.py` | Immutable policy provenance, atomic authorization/current-policy acquisition, task windows, and canonical calibration facts. | ✓ VERIFIED | Substantive SQLite joins and transactions enforce revision equality before rate writes (`181-227`); durable job provenance resolves through foreign-key lineage (`159-170`); terminal calibration query is deterministic (`611-642`). |
| `backend/app/advanced/jobs.py` | Fail-closed job creation and execution-start policy transition denial. | ✓ VERIFIED | Creation invokes atomic acquisition; `prepare_to_start()` rejects a mismatched durable/current revision before quota inspection, `_advance()`, workflow, provider, sandbox, or SSE. |
| `backend/tests/advanced/test_authorization_jobs.py` | Unit proof of A-to-B acquisition and execution denial plus stable task buckets. | ✓ VERIFIED | The transition tests assert zero A/B consumption on acquisition denial, preserved A/empty B consumption on start denial, audited safe reason, no runnable work, and no collaborator/progress calls (`224-324`); asymmetric quota test covers independent stable buckets (`413-492`). |
| `backend/tests/advanced/test_production_host.py` | Real-lifespan A-to-B denial without advanced progress. | ✓ VERIFIED | Two actual FastAPI lifespans share SQLite while fixture policy changes from A to B; the test observes preserved A accounting, empty B, no lake/sandbox mutation, no work calls, audited denial, and empty scoped SSE (`889-993`). |
| `backend/app/advanced/api.py`, `experiments.py`, `governed_runner.py` | Server-owned experiment binding from public route through runner. | ✓ VERIFIED | Public, service, persisted, and runner boundaries independently enforce the same binding and are covered by focused tests. |
| `backend/app/advanced/sandbox.py` | Fail-closed custom-source validation and proven Linux isolation. | ✓ VERIFIED | No default permissive launcher exists; malformed, absent, or stale proof rejects before spawn, and terminal records use safe projections. |
| `backend/app/main.py`, `contracts/market_data.py`, `jobs/daily_pipeline.py` | Read-only advanced-host fixture preflight before governed writes. | ✓ VERIFIED | Lifecycle → pipeline → provider preflight is ordered before `DataStore` construction and all governed output paths. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `AdvancedJobService.create_job` | `AdvancedRepository.acquire_authorized_job` | Current persisted policy revision is supplied to the one acquisition transaction. | ✓ WIRED | `jobs.py:69-87` → `repository.py:181-227`; the SQL equality predicate executes before a rate-window insert or job insert. |
| `AdvancedRepository.policy_revision_for_job` | `AdvancedJobService.prepare_to_start` | Durable queued job authorization provenance is compared to the current persisted policy. | ✓ WIRED | `repository.py:159-170` → `jobs.py:131-150`; mismatch returns through audited rejection before quota inspection or `_advance()`. |
| Job lifecycle | scoped advanced-progress SSE | Only `_advance()` publishes; transition denial does not call it. | ✓ WIRED | `jobs.py:151-172` returns the rejected cursor before `_advance()`; `_publish()` is reached only from `_advance()` (`238-267`). Unit and real-host tests assert an empty progress queue. |
| Public experiment route | experiment service and governed runner | Request binding equality → persisted bound ID → runner scope equality. | ✓ WIRED | API check precedes service call; service and runner duplicate the fail-closed guard before construction/execution. |
| Advanced-host fixture | governed data lake | Lifespan descriptor → pipeline preflight → `DataStore` / lake writes. | ✓ WIRED | `main.py:80-94` and `daily_pipeline.py:75-85` place preflight before store construction. |
| Viewpoint evaluation | calibration projection | Canonical terminal lookup → one terminal candidate per immutable version. | ✓ WIRED | `viewpoints.py:76-85,160-183` consumes repository's deterministic terminal query. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| Policy-transition quota guard | authorization policy revision, current policy revision, and `consumed` task window | Immutable SQLite `advanced_authorizations` / `advanced_policy_revisions` / `advanced_rate_windows` rows | Yes | ✓ FLOWING — acquisition uses the authorization-linked revision only after equality; execution resolves the same durable lineage before any new-policy window lookup. |
| Experiment binding | `bound_strategy_id` | Server-owned research-asset binding, persisted in `advanced_experiment_specs` | Yes | ✓ FLOWING — the client cannot replace it at route, service, or runner boundaries. |
| Fixture readiness | descriptor plus raw fixture bars | Deployment JSON → typed readiness → read-only provider preflight | Yes | ✓ FLOWING — valid fixtures reach the existing governed pipeline only after semantic checks. |
| Calibration | terminal evaluation candidate | Immutable evaluation ledger | Yes | ✓ FLOWING — one first terminal observation per immutable version. |
| Sandbox review | validation/run terminal projection | SQLite sandbox validation/run and security-audit facts | Yes | ✓ FLOWING — the API returns redacted projections, not raw source or host diagnostics. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| A-to-B acquisition denial, queued A-to-B execution denial, stable independent task buckets, and worker revalidation | `cd backend && timeout 30s uv run pytest tests/advanced/test_authorization_jobs.py tests/advanced/test_production_host.py -q -k 'policy_transition or policy_acquisition or asymmetric_task_quotas or worker_revalidates'` | 5 passed, 23 deselected | ✓ PASS |
| Server-bound experiment provenance and explicit promotion gates | `cd backend && timeout 30s uv run pytest tests/advanced/test_experiments.py tests/advanced/test_evolution.py -q -k 'server_resolved_binding or runner_rejects_divergent or service_rechecks_persisted or experiment_api_mismatch or experiment_specification_freezes_reproducible or completed_run_records_server_derived or every_independent_gate or approval_requires_server_resolved'` | 12 passed, 23 deselected | ✓ PASS |
| Material stance, governed performance, repeat-evaluation idempotence, and calibration candidate selection | `cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py -q -k 'structured_stance_deltas or governed_collaborator_records or calibration_projects or calibration_candidates or repeated_empty_body'` | 5 passed, 19 deselected | ✓ PASS |
| AST/import/contract/isolation/resource custom-strategy controls | `cd backend && timeout 30s uv run pytest tests/advanced/test_sandbox.py -q` | 44 passed | ✓ PASS |
| Fixture contract/preflight and valid governed synchronization | `cd backend && timeout 30s uv run pytest tests/test_market_data_fixture_contract.py tests/test_phase1_fixture_sync.py -q` | 20 passed, 6 existing Polars warnings | ✓ PASS |
| Actual lifespan readiness, public binding/quota boundary, and canonical host evaluation | `cd backend && timeout 30s uv run pytest tests/advanced/test_production_host.py -q -k 'accepts_valid_fixture_readiness or rejects_invalid_fixture_readiness or enforces_public_binding_and_task_specific_quota_boundaries or repeated_viewpoint_evaluation_is_canonical'` | 4 passed, 11 deselected, 9 existing Polars warnings | ✓ PASS |

The warnings are existing Polars deprecation/sortedness warnings in indicator-pipeline calls; no focused check failed.

### Probe Execution

Step 7c: **SKIPPED** — Phase 04 plans declare pytest checks, no phase-declared probe is present, and `scripts/**/tests/probe-*.sh` does not exist in this repository.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| **ADV-01** | 04-25, 04-26 | Attributed viewpoints, material changes, confidence-aware performance, and honest calibration. | ✓ SATISFIED | Immutable stance/evaluation code and five focused viewpoint tests pass; host canonical-evaluation regression passes. |
| **ADV-02** | 04-22, 04-24, 04-26 | Frozen experiment specification, sandboxed governed run, and feedback cycle. | ✓ SATISFIED | Binding is enforced route/service/runner-side before an experiment can produce evidence; focused regression passes. |
| **ADV-03** | 04-22, 04-24, 04-26 | Evolved strategy evidence and explicit promotion gates. | ✓ SATISFIED | Selected evolution tests pass; every independent gate is required and server-resolved approval is checked. |
| **SAFE-01** | 04-23, 04-24, 04-26, 04-27 | Scoped authorization, allowlists, durable task quotas, idempotent jobs, audit, and SSE progress. | ✓ SATISFIED | Plan 04-27 closes both policy-transition boundaries with direct source inspection plus unit and two-lifespan behavioral proof; denial is audited and emits no advanced progress. |
| **SAFE-02** | 04-22, 04-24, 04-26 | Machine-readable custom-strategy contract and fail-closed controlled execution. | ✓ SATISFIED | Full focused sandbox suite passes and current source requires affirmative isolation proof before spawn. |

All five Phase 04 requirements are declared by one or more Phase 04 plans. No Phase 04 requirement is orphaned.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| — | — | No `TBD`, `FIXME`, or `XXX` marker in Plan 04-27's modified runtime and test files. | ℹ️ Info | No unresolved completion-debt marker found. |

**Disconfirmation checks:** The former bypass was tested against its two temporal boundaries rather than inferred from symbol presence: an authorization issued under A is denied at B acquisition, and a correctly queued A job is denied across a real host restart under B. The denial checks inspect the exact potential false-positive paths—B window remains empty, A accounting remains unchanged, collaborators remain uncalled, and the scoped SSE queue remains empty. No unresolved partial implementation, misleading passing regression, or untested required error branch was found for the five retained truths.

---

_Verified: 2026-07-14T07:29:15Z_  
_Verifier: Claude (gsd-verifier)_
