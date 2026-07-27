---
phase: 04-advanced-capabilities
plan: "22"
subsystem: database
status: complete
tags: [sqlite, immutable-provenance, strategy-binding, governed-runner, pytest]
requires:
  - phase: 04-advanced-capabilities
    provides: immutable experiment, research-asset, and governed-runner workflows
provides:
  - Server-resolved immutable installed-strategy provenance on new experiment specifications
  - Service and runner guards that reject unbound or divergent strategy lineage before execution
  - Reverse research-asset binding resolver and focused regression coverage
affects: [advanced experiments, strategy evolution, promotion evidence, governed backtest]
tech-stack:
  added: []
  patterns:
    - Inject a narrow reverse binding resolver instead of querying lifecycle bindings from advanced code.
    - Revalidate persisted immutable binding before runner admission and terminal evidence writes.
key-files:
  created: []
  modified:
    - backend/app/research/repository.py
    - backend/app/advanced/experiments.py
    - backend/app/advanced/governed_runner.py
    - backend/app/operational/migrations.py
    - backend/tests/advanced/test_experiments.py
key-decisions:
  - "The research repository exclusively resolves research_asset_id to its installed strategy; advanced code receives only the injected resolver."
  - "Legacy specifications expose null bound strategy provenance and remain readable, but cannot be executed."
  - "The governed runner rejects an absent or divergent binding before strategy-service construction or process spawning."
patterns-established:
  - "Server-derived provenance is persisted beside immutable client-shaped scope and independently checked at every execution trust boundary."
requirements-completed: [ADV-02, ADV-03, SAFE-02]
coverage:
  - id: D1
    description: New experiment specifications retain only the exact immutable installed strategy bound to their research asset.
    requirement: ADV-02
    verification:
      - kind: unit
        ref: backend/tests/research/test_strategy_experiment_handoff.py#test_reverse_strategy_asset_binding_resolver_is_exact_and_fails_closed
        status: pass
      - kind: unit
        ref: backend/tests/advanced/test_experiments.py#test_server_resolved_binding_is_immutable_and_denials_precede_all_experiment_evidence
        status: pass
    human_judgment: false
  - id: D2
    description: Missing, mismatched, legacy, and changed bindings cannot create executable experiment or downstream evidence.
    requirement: ADV-03
    verification:
      - kind: unit
        ref: backend/tests/advanced/test_experiments.py#test_legacy_specifications_remain_readable_but_lack_executable_binding
        status: pass
      - kind: unit
        ref: backend/tests/advanced/test_experiments.py#test_service_rechecks_persisted_binding_before_runner_or_terminal_evidence
        status: pass
    human_judgment: false
  - id: D3
    description: The governed runner refuses divergent strategy lineage before strategy loading or worker spawning.
    requirement: SAFE-02
    verification:
      - kind: unit
        ref: backend/tests/advanced/test_experiments.py#test_runner_rejects_divergent_persisted_binding_before_loading_or_spawning
        status: pass
    human_judgment: false
metrics:
  duration: 8m 41s
  completed: 2026-07-14
---

# Phase 04 Plan 22: Immutable Experiment Strategy Binding Summary

**Experiment specifications now freeze the exact server-resolved installed strategy for their persisted research asset, and both service and runner deny divergent lineage before governed work begins.**

## Performance

- **Duration:** 8m 41s
- **Started:** 2026-07-14T05:47:36Z
- **Completed:** 2026-07-14T05:56:17Z
- **Tasks:** 2/2
- **Files modified:** 9

## Accomplishments

- Added an additive SQLite migration for immutable `bound_strategy_id` provenance, including an indexed retrieval field while retaining empty legacy values for historical rows.
- Made `ResearchRepository` the sole reverse resolver from a research asset revision to its one extant installed strategy; `ExperimentService` validates it before specification insertion, retries, runner invocation, and terminal evidence appends.
- Added independent collaborator and parent-runner checks that reject absent or divergent binding before strategy loading, engine configuration, or process spawning.
- Added focused regression coverage for exact resolution, matching creation, mismatch/unbound denial, legacy reads, direct service revalidation, and runner pre-worker denial.

## Task Commits

1. **Task 1: Persist a server-resolved strategy binding with each new experiment specification** — `df1e405` (`feat`)
2. **Task 2: Enforce the binding independently in experiment orchestration and the governed runner** — `0952075` (`fix`)

## Files Created/Modified

- `backend/app/advanced/schemas.py` — Defines the strict server-owned binding contract.
- `backend/app/research/repository.py` — Resolves an exact extant lifecycle binding from `research_asset_id`.
- `backend/app/operational/migrations.py` — Adds immutable, indexed strategy provenance without rewriting legacy facts.
- `backend/app/advanced/experiments.py` — Persists and rechecks server-derived binding before any experiment evidence path.
- `backend/app/advanced/governed_runner.py` — Rejects invalid lineage before loading a strategy or spawning a worker.
- `backend/app/main.py` — Wires the lifecycle resolver into the production experiment service.
- `backend/tests/advanced/test_experiments.py` — Covers service and runner denial-before-work invariants.
- `backend/tests/research/test_strategy_experiment_handoff.py` — Covers the reverse binding owner contract.

## Decisions Made

- The strategy identifier sent in a browser-shaped frozen scope is checked against, never trusted over, the research repository’s persisted lifecycle binding.
- Existing records are readable with `bound_strategy_id: null`; they fail closed for future execution because no server-owned binding was frozen with them.
- A persisted record is checked twice: by the service before any evidence append and by the runner before its strategy service or child process exists.

## Deviations from Plan

None - plan implementation executed as specified.

## Issues Encountered

- The plan-mandated aggregate command (`cd backend && timeout 30s uv run pytest tests/research/test_strategy_experiment_handoff.py tests/advanced/test_experiments.py -q`) remains blocked by two pre-existing, unrelated tests: stale split-evidence expectations and an absent `StrategyBacktestExperimentCollaborator.prepare()` method. The same two failures occurred before implementation. All five new provenance contract tests pass (`5 passed`).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Research assets now constrain both specification creation and runner admission to their immutable installed strategy binding. The two unrelated advanced test failures are recorded in the phase deferred-items log for separate ownership.

## Self-Check: PASSED

- All nine modified implementation and test files exist.
- Task commits `df1e405` and `0952075` exist in repository history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-14*
