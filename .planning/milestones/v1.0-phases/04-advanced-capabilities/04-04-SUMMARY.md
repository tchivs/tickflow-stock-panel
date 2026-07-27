---
phase: 04-advanced-capabilities
plan: "04"
subsystem: database
tags: [sqlite, pydantic, policy, immutable-facts, advanced-domain]
requires:
  - phase: 04-01
    provides: immutable viewpoint, experiment, and promotion RED contracts
  - phase: 04-02
    provides: authorization, safe API/SSE, and replay-safe workflow RED contracts
  - phase: 04-03
    provides: strict sandbox admission RED contract
provides:
  - strict advanced request, policy, and response allowlist contracts
  - append-only advanced SQLite fact schema in the shared operational database
  - transactional idempotent job acquisition and guarded cursor transitions
affects: [04-05, 04-06, 04-07, 04-08, 04-09, advanced-backend]
tech-stack:
  added: []
  patterns:
    - deployment-owned policy bootstrap with deterministic fingerprint
    - hand-built public projections that omit authority and execution internals
    - immutable SQLite facts with a single guarded advanced job cursor
key-files:
  created:
    - backend/app/advanced/__init__.py
    - backend/app/advanced/schemas.py
    - backend/app/advanced/policy.py
    - backend/app/advanced/projections.py
    - backend/app/advanced/repository.py
  modified:
    - backend/app/operational/migrations.py
key-decisions:
  - "Custom strategy source keeps exact bytes for SHA-256 validation, while no response DTO can contain source content."
  - "Advanced policy is deployment-owned, versioned, fingerprinted, and fails closed for absent or malformed bootstrap data."
  - "All advanced facts use immutable SQLite triggers; only advanced_jobs performs explicitly guarded cursor transitions."
patterns-established:
  - "Advanced public records are constructed field-by-field instead of returning storage rows."
  - "Job idempotency and active-work exclusion are enforced transactionally in operational.db."
requirements-completed: [ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02]
coverage:
  - id: D1
    description: Strict advanced request contracts, server policy bootstrap, and response allowlists reject client authority and conceal sensitive execution data.
    requirement: SAFE-02
    verification:
      - kind: other
        ref: cd backend && uv run python -m compileall -q app/advanced app/operational/migrations.py && uv run ruff check app/advanced app/operational/migrations.py
        status: pass
    human_judgment: false
  - id: D2
    description: Shared operational SQLite contains foreign-keyed append-only advanced fact tables and an idempotent guarded job cursor.
    requirement: SAFE-01
    verification:
      - kind: other
        ref: temporary SQLite migration, immutable trigger, idempotent acquisition, and conflict-handling smoke checks
        status: pass
    human_judgment: false
metrics:
  duration: 6m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 04: Advanced Contracts and SQLite Foundation Summary

**Strict server-authoritative advanced-domain contracts now feed a single immutable operational SQLite ledger with fingerprinted policy snapshots, safe public projections, and transactional job cursors.**

## Performance

- **Duration:** 6m
- **Started:** 2026-07-12T14:16:36Z
- **Completed:** 2026-07-12T14:22:49Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Added bounded, `extra="forbid"` contracts for viewpoints, experiments, candidates, gates, approvals, authorization jobs, and same-request custom-strategy source/contract SHA-256 admission.
- Added fail-closed `advanced_policy_v1` bootstrap for the `operator-research-v1` CN-A profile, frozen benchmark policy, and deployment-owned agent limits.
- Added safe hand-built projections and a shared `operational.db` migration with foreign keys, `RESTRICT` deletion, immutable fact triggers, partial active-job uniqueness, and outcome uniqueness.
- Added repository primitives for policy snapshots, idempotent active job acquisition, conditional job state transitions, and redacted security audits.

## Task Commits

1. **Task 1: Define strict advanced domain and public projection contracts** - `d93ef24` (`feat`)
2. **Task 2: Add transactional advanced SQLite schema and repository primitives** - `1a01974` (`feat`)

## Files Created/Modified

- `backend/app/advanced/schemas.py` - Bounded request and safe public DTO contracts.
- `backend/app/advanced/policy.py` - Server-only `advanced_policy_v1` bootstrap and benchmark resolution.
- `backend/app/advanced/projections.py` - Explicit public field allowlists.
- `backend/app/advanced/repository.py` - Parameterized transactional advanced SQLite methods.
- `backend/app/operational/migrations.py` - Versioned advanced fact schema, indexes, and integrity triggers.

## Verification

```text
cd backend && uv run python -m compileall -q app/advanced app/operational/migrations.py && uv run ruff check app/advanced app/operational/migrations.py
passed

Temporary SQLite smoke checks
passed: migration, immutable fact trigger, idempotent job acquisition, and guarded state conflict handling

cd backend && uv run pytest tests/advanced -q
69 failures expected: remaining RED contracts import later-plan modules (viewpoints, experiments, evolution, authorization/jobs, sandbox, API, and workflow); no failure originated in the new contracts, migration, or repository module.
```

## Decisions Made

- Source bytes must not be stripped or normalized before custom-strategy SHA-256 validation.
- The deployment policy is the only source of profile, benchmark, allowlist, and rate defaults; browser inputs cannot derive any of them.
- Mutable execution state is restricted to `advanced_jobs`; all lineage, audit, policy, sandbox, and research facts are append-only.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved exact custom-strategy source bytes during hash validation**
- **Found during:** Task 1
- **Issue:** The inherited whitespace-stripping model configuration changed trailing source bytes before SHA-256 comparison.
- **Fix:** Overrode string stripping only for `CustomStrategySubmission`, retaining exact source bytes while preserving strict contract validation.
- **Files modified:** `backend/app/advanced/schemas.py`
- **Verification:** Source/hash binding smoke check passed; injected authority fields still raise Pydantic validation errors.
- **Committed in:** `d93ef24`

**2. [Rule 1 - Bug] Completed migration-level immutability coverage and corrected the job trigger**
- **Found during:** Task 2
- **Issue:** The initial cursor trigger referenced a nonexistent job column, and policy/rate facts lacked explicit immutable triggers.
- **Fix:** Restricted job transitions to valid status changes and added immutable triggers for policy and rate facts.
- **Files modified:** `backend/app/operational/migrations.py`
- **Verification:** Temporary SQLite migration and immutable-trigger smoke checks passed.
- **Committed in:** `1a01974`

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs).
**Impact on plan:** Both changes preserve the planned security and integrity guarantees without expanding the delivery surface.

## Known Stubs

None. The new package provides concrete contracts and persistence primitives; later services consume these foundations and no UI-facing empty data path was introduced.

## Issues Encountered

The plan-level advanced pytest suite remains RED because its service, API, sandbox, and workflow implementations belong to later Phase 4 plans. The failures are limited to imports of those absent modules; the completed foundation has focused static and temporary-database verification.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plans 04-05 through 04-09 can implement advanced domain services against one shared operational database, strict policy snapshots, and projection allowlists. `STATE.md` and `ROADMAP.md` were intentionally not modified per the execution request.

## Self-Check: PASSED

Verified the summary and advanced contract/repository files exist, task commits `d93ef24` and `1a01974` are present in git history, and `STATE.md` and `ROADMAP.md` remain untouched.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
