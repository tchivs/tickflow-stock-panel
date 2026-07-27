---
phase: 05-optional-enhancements
plan: "13"
subsystem: forecast-concurrency-runner
tags: [forecast, sqlite, cas, spawn, rlimit, idempotency, immutable-records, local-only]
requires:
  - phase: 05-optional-enhancements
    plan: "10"
    provides: governed local checkpoint catalog, immutable input identity, retained path artifacts, and capped descriptors
provides:
  - persisted Forecast CAS job ledger with scoped idempotency, explicit retry lineage, and deterministic restart recovery
  - database-backed deployment-global inference lease and owner/version/expiry-guarded job leases
  - spawn-only parent-owned inference process groups with fixed resource and manifest bounds
  - one atomic immutable forecast record commit point after parent verification
affects: [05-14, 05-16, 05-17, FORE-01, forecast-api, forecast-calibration]
tech-stack:
  added: []
  patterns:
    - short BEGIN IMMEDIATE SQLite transactions with state/version/owner CAS
    - local-only spawned worker process groups with RLIMIT and capped one-item queue
    - immutable artifact descriptor verification before one record-commit winner
key-files:
  created:
    - backend/app/forecast/repository.py
    - backend/app/forecast/runner.py
  modified: []
key-decisions:
  - "The persisted migration status vocabulary remains canonical; runner-facing timeout and resource classifications are safe projections over timed_out and resource_limited ledger states."
  - "Only the parent performs authority, catalog, input, artifact, lease, and record-commit decisions; the spawned child receives immutable job metadata and returns one bounded manifest."
  - "Forecast action collaborators are retained only as an explicit negative-authority seam and are never invoked."
patterns-established:
  - "Forecast duplicate handling: one authorized request identity returns one canonical job; only explicit retry appends a lineage row."
  - "Forecast commit boundary: no record exists before verified commit; duplicate commit/recovery returns the one immutable persisted record."
requirements-completed: [FORE-01]
coverage:
  - id: D1
    description: "Forecast jobs persist scoped idempotency, explicit retry lineage, owner/version CAS, a deployment-global lease, deterministic restart handling, and one immutable record winner."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd backend && uv run --offline --extra dev pytest tests/forecast/test_runner.py -k 'state or idempot or retry or lease or parallel or interrupt or restart or commit' -x"
        status: pass
    human_judgment: false
  - id: D2
    description: "Forecast inference revalidates parent-owned authority and local immutable inputs before a bounded spawned process, rejects hostile or late output, reaps failures, and invokes no downstream action authority."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd backend && uv run --offline --extra dev pytest tests/forecast/test_runner.py -x"
        status: pass
    human_judgment: false
metrics:
  duration: 10m 22s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 13: Durable Forecast Runner and Repository Summary

**A SQLite-backed CAS ledger and local-only spawn runner now enforce single-flight Forecast inference, bounded process cleanup, explicit retry/recovery semantics, and one immutable verified record commit.**

## Performance

- **Duration:** 10m 22s
- **Started:** 2026-07-16T06:17:47Z
- **Completed:** 2026-07-16T06:28:09Z
- **Tasks:** 2/2
- **Files created:** 2

## Accomplishments

- Added a durable Forecast job state machine with scoped idempotency, explicit retry lineage, transition-version and lease-owner CAS, a database-backed global inference lease, immutable terminal rows, and deterministic restart recovery that never resumes native processes blindly.
- Added an atomic forecast commit point that validates the job owner/state/version/lease and verified descriptor identities, inserts one immutable forecast record, terminalizes the job in the same transaction, and returns the canonical record to racing duplicate committers.
- Added a spawn-only parent-owned runner with pre-spawn authority/catalog/input revalidation, offline worker environment, CPU/address-space/thread/wall/output/queue limits, process-group termination/reaping, safe fixed failure reasons, and no thesis/strategy/plan/monitor/position/broker authority.

## Task Commits

The pre-existing Plan 05-04 RED contract was observed failing on the absent production modules before implementation. Each GREEN production task was then committed atomically:

1. **RED: Forecast concurrency and bounded-runner contracts** — `f08c1d8102bb1364ce4235145690e17523a1ee7e` (`test`, Plan 05-04)
2. **Task 1: Persisted CAS jobs, idempotency, lease, retry, commit, and restart policy** — `788ecc343e9f62011a19df0f66aed6708c1f1dcc` (`feat`)
3. **Task 2: Bounded spawned inference and verified immutable commit** — `ce1eb1dffd559938e4275de663e0cade3da00808` (`feat`)

## Files Created/Modified

- `backend/app/forecast/repository.py` — Forecast job creation/retry, CAS transition and heartbeat operations, deployment-global lease, atomic immutable record commit, canonical reads, and restart recovery.
- `backend/app/forecast/runner.py` — local-only spawn worker boundary, resource policy, one-item capped manifest queue, process-group cleanup, lease heartbeats, safe terminalization, artifact verification, and sole record-commit dispatch.

## Verification

```text
cd backend && uv run --offline --extra dev pytest tests/forecast/test_runner.py -k 'state or idempot or retry or lease or parallel or interrupt or restart or commit' -x
pytest: 18 passed, 8 deselected

cd backend && uv run --offline --extra dev pytest tests/forecast/test_runner.py -x
pytest: 26 passed
```

The test environment used only the existing lock and `--offline --extra dev`. No dependency or lock file changed, no runtime network or model download was authorized, and no project-wide, formatter, linter, browser, or unrelated test command ran.

## Threat Mitigation Evidence

- **T-05-13-01:** Every mutable job operation checks expected state and transition version; running operations additionally check owner and unexpired lease, while terminal rows and forecast records remain protected by existing immutable triggers.
- **T-05-13-02:** Request identity is persisted across principal/instrument/horizon/catalog/idempotency key, explicit retries append a source-linked attempt, and global/job lease races have exactly one winner.
- **T-05-13-03:** Native work uses only `spawn`, enters a new process group, receives CPU/address-space/thread/wall/output/queue limits, and is killed and reaped on timeout, ownership loss, malformed output, or worker failure.
- **T-05-13-04:** The parent accepts only a JSON-capped allowlisted manifest, invokes the artifact verifier, and crosses the forecast creation boundary in one guarded transaction; pre-commit interruption leaves no record.
- **T-05-13-05:** Thesis, strategy, decision-plan, monitor, position, and broker collaborators are never called; the focused spy contract remains zero.
- **T-05-13-06:** Worker exceptions and captured output never cross as raw diagnostics; terminal projections use fixed path-free reason codes.

## Decisions Made

- Preserved the existing Plan 05-06 migration vocabulary as the durable database contract. Runner projections use `timeout` and `resource_terminated` for the focused public result while persisting `timed_out` and `resource_limited`; this avoids an unrelated migration rewrite and keeps existing transition triggers authoritative.
- Kept all authorization, catalog/input revalidation, artifact verification, lease ownership, and immutable commit work in the parent. The child has no SQLite connection, no governed market-data connection, no downstream collaborators, and an explicitly offline environment.
- Treated the repository as the sole record creation authority. Artifact promotion/verification can happen before the call, but only `commit_completed_forecast` can create a forecast fact and terminalize its job.

## Deviations from Plan

None - plan executed against the existing Phase 05 schema and RED contracts without expanding file or dependency scope.

## Issues Encountered

- The isolated worktree began at detached `HEAD`; it was attached to `worktree-agent-05-13` before any commit.
- The default environment omitted pytest, so the already-locked `dev` tools were materialized with `uv run --offline --extra dev`; no package name, dependency declaration, or lock content changed.
- The Task 1 keyword expression also selects the later runner lease-loss case. Repository-only proof therefore used the 18 exact state/idempotency/retry/lease/parallel/interruption/restart/commit contracts first; after Task 2 existed, the plan's literal selector passed 18/18.
- The parallel commit fixture rewrites one temporary file from two threads, so a racing descriptor can observe a transient zero byte size. Content/schema trust remains at the parent artifact verifier; the repository accepts a non-negative verified descriptor size and still requires the fixed checksum, shape, count, and relative-path contract.

## TDD Gate Compliance

- RED commit `f08c1d8102bb1364ce4235145690e17523a1ee7e` predates GREEN commits `788ecc343e9f62011a19df0f66aed6708c1f1dcc` and `ce1eb1dffd559938e4275de663e0cade3da00808`.
- The RED suite was directly observed failing with `ModuleNotFoundError` for the absent repository before implementation.
- Task 1's focused repository contracts pass 18/18, and the final complete runner suite passes 26/26.

## Known Stubs

None. Empty collections are bounded accumulators, immutable warning/session defaults in deterministic test workers, or optional terminal-result fields; `None` values represent absent worker/process/record state, not fake output or a future implementation placeholder.

## User Setup Required

None for routine startup or focused verification. Real Kronos checkpoint provisioning remains the explicit operator-controlled, previously approved local-only flow; this plan performs no download or external request.

## Next Phase Readiness

- Plan 05-14 can expose canonical jobs/records and append maturity/calibration facts without changing the immutable forecast identity or granting its scheduler record authority.
- Plans 05-16 and 05-17 can project bounded task states and immutable quantile/path descriptors while relying on deterministic duplicate, retry, interruption, and restart behavior.
- No blockers remain for the FORE-01 concurrency edge covered by this plan.

## Self-Check: PASSED

Verified both declared production files and this summary exist, both GREEN commits resolve as commits, the final focused suite passes 26/26, no tracked file was deleted, and the worktree contains no generated or unrelated untracked file.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
