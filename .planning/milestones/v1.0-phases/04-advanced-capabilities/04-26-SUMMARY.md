---
phase: 04-advanced-capabilities
plan: "26"
subsystem: api-integration
tags: [fastapi, sqlite, authorization, provenance, sse, lifespan, pytest]
requires:
  - phase: 04-22
    provides: immutable research-asset strategy provenance and runner-side validation
  - phase: 04-23
    provides: task-specific durable policy quotas and pre-execution revalidation
  - phase: 04-24
    provides: fail-closed advanced-host fixture readiness preflight
  - phase: 04-25
    provides: canonical terminal viewpoint evaluation and calibration selection
provides:
  - public experiment route validation against one persisted installed-strategy binding
  - authenticated real-lifespan regression proof for mismatched lineage and independent task quotas
  - lifecycle-level proof that fixture readiness and repeated evaluation retain prior safeguards
affects: [ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02, advanced-api, host-lifespan]
tech-stack:
  added: []
  patterns:
    - route authorization resolves persisted immutable binding server-side before any specification service call
    - public denial tests compare durable side effects and scoped advanced-progress queues before and after rejected requests
key-files:
  created:
    - .planning/phases/04-advanced-capabilities/04-26-SUMMARY.md
  modified:
    - backend/app/advanced/api.py
    - backend/app/main.py
    - backend/tests/advanced/test_experiments.py
    - backend/tests/advanced/test_production_host.py
key-decisions:
  - "A valid research asset is not enough for experiment creation: the route must obtain its exact extant installed-strategy binding and reject scope mismatches as non-enumerating 404s."
  - "Real-lifespan tests use authenticated public routes and the existing scoped quote subscriber rather than browser authority, route interception, or alternate stores."
patterns-established:
  - "Public immutable-lineage checks precede service invocation while the service retains its independent resolver guard for direct callers."
  - "Asymmetric per-task quota evidence observes only safe audits and no advanced-progress events for rejected public requests."
requirements-completed: [ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02]
coverage:
  - id: D1
    description: "A mismatched authenticated experiment request is denied before an immutable specification, runner, sandbox fact, promotion evidence, runnable job, SSE event, or governed-lake change."
    requirement: ADV-02
    verification:
      - kind: integration
        ref: "backend/tests/advanced/test_experiments.py#test_experiment_api_mismatch_creates_no_immutable_or_governed_side_effects"
        status: pass
      - kind: integration
        ref: "backend/tests/advanced/test_production_host.py#test_main_host_enforces_public_binding_and_task_specific_quota_boundaries"
        status: pass
    human_judgment: false
  - id: D2
    description: "Authenticated public experiment and strategy-evaluation quota buckets exhaust independently while research_draft remains permitted and rejected attempts publish no advanced progress."
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: "backend/tests/advanced/test_production_host.py#test_main_host_enforces_public_binding_and_task_specific_quota_boundaries"
        status: pass
      - kind: unit
        ref: "backend/tests/advanced/test_authorization_jobs.py#test_asymmetric_task_quotas_reject_without_work_or_progress_and_leave_research_capacity"
        status: pass
    human_judgment: false
  - id: D3
    description: "Advanced host readiness remains fail-closed before governed-lake synchronization and accepts only a valid deployment-owned descriptor."
    requirement: SAFE-02
    verification:
      - kind: integration
        ref: "backend/tests/advanced/test_production_host.py -k 'fixture_readiness or task_specific_quota or repeated_viewpoint_evaluation'"
        status: pass
      - kind: integration
        ref: "backend/tests/test_market_data_fixture_contract.py tests/test_phase1_fixture_sync.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Repeated authenticated public viewpoint evaluation returns the canonical terminal outcome and contributes one calibration candidate."
    requirement: ADV-01
    verification:
      - kind: integration
        ref: "backend/tests/advanced/test_production_host.py#test_authenticated_main_host_repeated_viewpoint_evaluation_is_canonical"
        status: pass
      - kind: unit
        ref: "backend/tests/advanced/test_viewpoints.py"
        status: pass
    human_judgment: false
metrics:
  duration: 11m 20s
  completed: 2026-07-14
status: complete
---

# Phase 04 Plan 26: Public Boundary Proof Summary

**Authenticated public routes now resolve immutable experiment lineage server-side, while real FastAPI lifespan regressions prove mismatch, quota, readiness, and repeated-evaluation safeguards before prohibited work begins.**

## Performance

- **Duration:** 11m 20s
- **Started:** 2026-07-14T06:36:13Z
- **Completed:** 2026-07-14T06:47:33Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Added a private route-level persisted-binding resolver that requires the exact extant research asset, installed strategy, and revision before an experiment specification service call. Mismatches receive the existing safe 404 projection.
- Wired the lifecycle-owned reverse binding resolver through a public-route adapter that confirms both the immutable revision and installed strategy remain extant; direct service callers retain the same independent resolver invariant.
- Added authenticated API and real-lifespan regressions proving mismatched requests create no specification, run, sandbox fact, feedback, candidate, gate, promotion, runnable job, scoped advanced-progress event, or governed-lake change.
- Extended real-host proof with asymmetric public quotas: experiment and strategy-evaluation exhaust independently, denial leaves only safe quota audits with no progress event, and research_draft remains independently permitted.
- Re-ran lifecycle fixture-readiness and repeated public-viewpoint evaluation checks; valid readiness persists the existing binding while repeated evaluation returns the canonical terminal calibration contribution.

## Task Commits

1. **Task 1: Wire persisted strategy binding into the authenticated experiment route and lifecycle** - `e41078f` (feat)
2. **Task 2: Prove real-host denial-before-work safeguards and independent quota buckets** - `fc3cba5` (test)

## Files Created/Modified

- `backend/app/advanced/api.py` — Resolves the server-owned binding before dispatching public experiment creation.
- `backend/app/main.py` — Exposes an extant installed-strategy/revision lifecycle resolver to the authenticated route while preserving the injected direct-service resolver.
- `backend/tests/advanced/test_experiments.py` — Covers safe public mismatch denial and absence of immutable/governed side effects.
- `backend/tests/advanced/test_production_host.py` — Adds real-lifespan binding/quota/SSE proof and canonical repeated-evaluation coverage; names fixture-readiness boundary regressions for focused execution.

## Decisions Made

- Public route checks compare the submitted frozen scope to the server-resolved binding but never rewrite client authority or introduce a binding-write route.
- Rejected task requests are verified through the existing safe response/audit projection and authorized scoped subscriber queue; no route mock, external service, alternate datastore, automatic promotion, or broker path was added.

## Verification

Passed focused evidence:

```text
cd backend && timeout 30s uv run pytest tests/advanced/test_production_host.py -k 'fixture_readiness or task_specific_quota or repeated_viewpoint_evaluation' -q
4 passed, 10 deselected in 9.02s

cd backend && timeout 30s uv run pytest tests/advanced/test_experiments.py -q -k 'experiment_api_uses_server_owner or mismatched_persisted_binding or mismatch_creates_no'
3 passed, 20 deselected in 1.03s

cd backend && timeout 30s uv run pytest tests/advanced/test_authorization_jobs.py -q -k asymmetric_task_quotas
1 passed, 10 deselected in 0.91s

cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py -q
24 passed in 11.74s

cd backend && timeout 30s uv run pytest tests/test_market_data_fixture_contract.py tests/test_phase1_fixture_sync.py -q
20 passed in 3.28s
```

The plan aggregate command reported **2 pre-existing unrelated advanced-runner failures** and the final host gate reported those two plus **3 further stale runner-host expectations**. The exact failures and rationale for leaving unrelated runner behavior untouched are recorded in `deferred-items.md`.

## Deviations from Plan

None - plan implementation executed exactly as written. Existing aggregate-gate failures were out of scope and recorded without masking or changing them.

## Known Stubs

None. The modified runtime path resolves real persisted lifecycle data, and all new tests use real FastAPI lifespan, SQLite operational state, governed Parquet fixture synchronization, and scoped quote-service delivery.

## Threat Flags

None. This plan adds no endpoint, storage backend, external service, client authorization authority, or new trust-boundary surface; it narrows validation on an existing authenticated experiment endpoint.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The public boundary now proves the 04-22 through 04-25 safeguards end to end. The stale runner test expectations in `deferred-items.md` should be assigned separately before treating the broader historical runner suite as green.

## Self-Check: PASSED

Verified the summary and four modified runtime/test files exist, and task commits `e41078f` and `fc3cba5` resolve in repository history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-14*
