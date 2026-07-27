---
phase: 04-advanced-capabilities
plan: "15"
subsystem: advanced-sandbox-security
tags: [linux-namespaces, sqlite, fastapi, sandbox, authorization]
requires:
  - phase: 04-14
    provides: fail-closed Linux launcher and durable terminal sandbox facts
provides:
  - observable Linux isolation capability proof with pre-spawn rejection
  - immutable sandbox validation-to-asset lineage in operational.db
  - authorized allowlisted terminal sandbox run list and detail DTOs
affects: [SAFE-02, advanced-api, advanced-research]
tech-stack:
  added: []
  patterns:
    - child isolation claims are accepted only when structured observations validate against parent state
    - opaque persisted parent assets are server-authorized before sandbox-run disclosure
key-files:
  created: []
  modified:
    - backend/app/advanced/sandbox.py
    - backend/app/advanced/repository.py
    - backend/app/advanced/projections.py
    - backend/app/advanced/api.py
    - backend/app/operational/migrations.py
    - backend/tests/advanced/test_sandbox.py
    - backend/tests/advanced/test_production_host.py
key-decisions:
  - "Linux proof accepts namespace deltas, mounts, write boundaries, network denial, rlimits, and parent cleanup evidence rather than child-reported booleans."
  - "Sandbox parent assets remain opaque server-authorized identifiers; the existing validation-to-run foreign key preserves immutable execution lineage without adding a second asset datastore."
requirements-completed: [SAFE-02]
coverage:
  - id: D1
    description: Custom strategy code remains pre-spawn rejected unless observable Linux namespace, filesystem, network, resource, and cleanup evidence is complete and fresh.
    requirement: SAFE-02
    verification:
      - kind: integration
        ref: cd backend && timeout 60s uv run pytest tests/advanced/test_sandbox.py tests/advanced/test_production_host.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: Authorized researchers can review only safe terminal sandbox-run list and detail DTOs scoped by the persisted parent research asset.
    requirement: SAFE-02
    verification:
      - kind: unit
        ref: backend/tests/advanced/test_sandbox.py#test_authorized_sandbox_run_api_lists_safe_terminal_records_without_cross_asset_disclosure
        status: pass
    human_judgment: false
metrics:
  duration: 11m
  completed: 2026-07-13
status: complete
---

# Phase 04 Plan 15: Observable Sandbox Proof and Run Review Summary

**Linux sandbox admission now requires observable isolation evidence, and authorized researchers can review sanitized immutable terminal run records.**

## Performance

- **Duration:** 11m
- **Started:** 2026-07-13T03:08:37Z
- **Completed:** 2026-07-13T03:19:13Z
- **Tasks:** 3/3
- **Files modified:** 7

## Accomplishments

- Replaced fixed affirmative probe values with structured namespace, mount, filesystem, network, rlimit, and parent-cleanup observations that fail closed before strategy spawn.
- Added a forward operational SQLite migration that keeps immutable sandbox validation lineage bound to the strict contract's parent research asset and queryable from terminal runs.
- Added asset-scoped `GET /api/advanced/sandbox/runs` and `GET /api/advanced/sandbox/runs/{run_id}` endpoints plus safe terminal DTOs; successful submissions now return the same run projection.

## Task Commits

1. **Task 1: 用逐项可观测证据重建 Linux 隔离 capability proof** - `5109f38` (test RED), `08386b9` (feat GREEN)
2. **Task 2: 迁移 sandbox lineage 并验证升级与不可变约束** - `1408196` (test RED), `99c034a` (feat GREEN), `68665ae` (migration upgrade coverage)
3. **Task 3: 暴露授权且脱敏的 terminal sandbox-run 列表与详情** - `b083118` (test RED), `ccf8282` (feat GREEN)

## Verification

```text
cd backend && timeout 60s uv run pytest tests/advanced/test_sandbox.py tests/advanced/test_production_host.py -q
35 passed, 12 warnings

cd backend && uv run ruff check app/advanced/sandbox.py app/advanced/repository.py app/advanced/projections.py app/advanced/api.py tests/advanced/test_sandbox.py
All checks passed

cd backend && uv run python -m compileall -q app/advanced
passed
```

## Files Created/Modified

- `backend/app/advanced/sandbox.py` - Observable Linux capability validation, immutable parent-asset persistence, and raw run record accessors.
- `backend/app/advanced/repository.py` - Indexed terminal-run lineage joins and stable run ordering.
- `backend/app/advanced/projections.py` - Deny-by-default terminal run DTO with safe status, reason, resource, audit, and timestamp fields.
- `backend/app/advanced/api.py` - Server-authorized sandbox run list/detail routes and successful submission projection.
- `backend/app/operational/migrations.py` - Forward immutable sandbox parent-asset lineage migration.
- `backend/tests/advanced/test_sandbox.py` - Probe, migration, authorization, leakage, and API regression coverage.
- `backend/tests/advanced/test_production_host.py` - Production terminal DTO contract coverage.

## Decisions Made

- Linux capability evidence is considered affirmative only after child observations corroborate parent namespace state and the parent verifies cleanup; unprovable environments reject without starting submitted code.
- The parent research asset is persisted only from the strict server-validated contract. It remains opaque and is reauthorized by the server for every list/detail disclosure.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Verification] Added upgrade and idempotency migration coverage**
- **Found during:** Task 2
- **Issue:** The original new-database test did not prove preservation of existing sandbox validation facts during an operational SQLite upgrade.
- **Fix:** Added an old-schema fixture that upgrades once, preserves the validation row, and proves a repeated migration is idempotent.
- **Files modified:** `backend/tests/advanced/test_sandbox.py`
- **Verification:** Focused sandbox suite passed with the new migration scenario.
- **Committed in:** `68665ae`

**Total deviations:** 1 auto-fixed (1 Rule 2 missing critical verification).
**Impact on plan:** The added regression closes the plan's explicit upgrade guarantee without changing runtime authority or storage scope.

## Issues Encountered

None. The production-host suite emits 12 pre-existing Polars deprecation/sortedness warnings; no verification command failed.

## Known Stubs

None. Sandbox run data is persisted through the append-only validation/run relation and every API response uses an explicit field allowlist.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

SAFE-02 now has observable pre-spawn proof validation and authorized terminal-record review. The API maintains the single-container, `operational.db` boundary and exposes no source, path, environment, output, or traceback data.

## TDD Gate Compliance

Each task has a failing `test(04-15)` commit before its corresponding `feat(04-15)` implementation commit.

## Self-Check: PASSED

Verified all seven modified source/test files exist and task commits `5109f38`, `08386b9`, `1408196`, `99c034a`, `68665ae`, `b083118`, and `ccf8282` are present in git history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-13*
