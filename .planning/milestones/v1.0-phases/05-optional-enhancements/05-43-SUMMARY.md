---
phase: 05-optional-enhancements
plan: 43
subsystem: security-runtime
tags: [controlled-interpreter, sqlite-cas, durable-dispatch, process-groups, lifecycle]

requires:
  - phase: 05-optional-enhancements
    provides: optional Shadow, Thesis, and Forecast production host with immutable evidence boundaries
provides:
  - Positive-parser strategy IR executed without arbitrary Python authority
  - Owner-first durable Forecast retry operation and atomic dispatch-ready publication
  - Caller-visible bounded shutdown outcomes with retained unresolved ownership
  - Explicit Windows fail-closed and Linux process-group test partitions
affects: [05-44-acceptance-closeout, forecast-retry, optional-module-host, strategy-sandbox]

tech-stack:
  added: []
  patterns:
    - positive parser to immutable instruction IR to fixed interpreter
    - reservation owner token and versioned SQLite publication CAS
    - durable publication as dispatch acceptance with wake as a hint
    - active and closing registries retain unresolved lifecycle ownership

key-files:
  created:
    - backend/app/advanced/strategy_policy.py
  modified:
    - backend/app/advanced/sandbox.py
    - backend/app/operational/migrations.py
    - backend/app/forecast/repository.py
    - backend/app/forecast/service.py
    - backend/app/forecast/runner.py
    - backend/app/optional_modules.py
    - backend/pyproject.toml
    - backend/tests/advanced/test_sandbox.py
    - backend/tests/forecast/test_runner.py
    - backend/tests/test_operational_migrations.py
    - backend/tests/test_phase5_optional_host.py

key-decisions:
  - "Submitted strategy source is provenance only; execution consumes immutable positive-parser IR through fixed value intrinsics."
  - "Forecast retry reservation is the first mutation, and only its persisted owner token can bind or publish."
  - "A fully bound dispatch-ready job appears only in the publication transaction; dispatcher wake failure never revokes accepted work."
  - "Shutdown timeout is unresolved ownership, so callers receive a retryable aggregate and the host retains the exact owner."

patterns-established:
  - "Positive authority: admit only documented operations instead of filtering dangerous Python syntax."
  - "Owner-first publication: reserve, bind, publish, then best-effort wake."
  - "Bounded close: remove an owner only after a stopped outcome; otherwise retain it for retry."

requirements-completed: [SHDW-01, THES-01, FORE-01]

coverage:
  - id: D1
    description: Strategy submissions lower to immutable IR and execute without source, code objects, modules, callables, or ambient builtins.
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: tests/advanced/test_sandbox.py R43-CR-01 nodes
        status: pass
    human_judgment: false
  - id: D2
    description: Forecast retries reserve one owner before freezing and atomically publish one fully bound dispatch-ready canonical job.
    requirement: FORE-01
    verification:
      - kind: integration
        ref: tests/forecast/test_runner.py R43-CR-02/R43-CR-03 nodes
        status: pass
      - kind: integration
        ref: tests/test_operational_migrations.py legacy quarantine node
        status: pass
    human_judgment: false
  - id: D3
    description: Optional host shutdown exposes unresolved ownership, retains the owner, and succeeds on bounded retry after release.
    requirement: THES-01
    verification:
      - kind: integration
        ref: tests/test_phase5_optional_host.py R43-CR-04 nodes
        status: pass
    human_judgment: false
  - id: D4
    description: Windows fails closed without POSIX primitives while Linux proves native PGID and descendant cleanup.
    requirement: FORE-01
    verification:
      - kind: integration
        ref: Windows four-file acceptance suite
        status: pass
      - kind: integration
        ref: WSL pytest -m linux_process_group
        status: unknown
    human_judgment: true
    rationale: "The execution host has no usable WSL distribution, so native Linux evidence must be run on WSL/Linux before ship."

duration: 30min
completed: 2026-07-27
status: complete
---

# Phase 05 Plan 43: Critical Runtime Boundary Closure Summary

**Controlled strategy IR, owner-first Forecast publication, and retained shutdown ownership replace arbitrary Python, freeze-first retry, and silent close semantics.**

## Performance

- **Duration:** 30 min
- **Started:** 2026-07-26T19:31:16Z
- **Completed:** 2026-07-26T20:00:47Z
- **Tasks:** 3
- **Files modified:** 12 implementation and test files

## Accomplishments

- Replaced the custom-strategy AST denylist authority with a positive parser, immutable canonical IR, and fixed controlled interpreter while retaining Linux isolation as defense in depth.
- Added a unique owner-leased retry operation whose bind and publish mutations are token/version guarded; publication creates the only dispatch-ready canonical retry job.
- Added a forward migration that conservatively terminal-quarantines legacy unbound queued jobs before restart recovery can claim them.
- Made dispatcher and optional-host close outcomes caller-visible, retained timed-out owners for bounded retry, and propagated cancellation through saved process-group ownership before immutable commit.
- Split portable Windows fail-closed evidence from explicitly marked native Linux process-group evidence.

## Task Commits

1. **Task 1 RED: controlled strategy interpreter contracts** - `d5bde57`
2. **Task 1 GREEN: positive IR interpreter and sandbox handoff** - `919e5ec`
3. **Task 2 RED: retry publication contracts** - `cc4e03b`
4. **Task 2 GREEN: owner-first durable retry publication** - `5d92fa6`
5. **Task 3 RED: shutdown ownership contracts** - `e4fd998`
6. **Task 3 GREEN: retained bounded shutdown ownership** - `b9f522b`

## Files Created/Modified

- `backend/app/advanced/strategy_policy.py` - Positive grammar, immutable IR, fixed intrinsics, and controlled evaluator.
- `backend/app/advanced/sandbox.py` - Canonical IR handoff with raw source retained only as provenance.
- `backend/app/operational/migrations.py` - Retry-operation schema, dispatch-ready fields, triggers, and legacy quarantine.
- `backend/app/forecast/repository.py` - Repository-owned terminal contract and owner-checked reserve/bind/publish/abort/recovery operations.
- `backend/app/forecast/service.py` - Owner-first retry orchestration and explicit dispatcher lifecycle outcomes.
- `backend/app/forecast/runner.py` - Shared stop-token checks and pre-commit process-group cancellation.
- `backend/app/optional_modules.py` - Aggregate close outcomes, retryable incomplete exception, retained closing registry, and expired-operation artifact cleanup.
- `backend/pyproject.toml` - Explicit `linux_process_group` and `windows_only` markers.
- `backend/tests/advanced/test_sandbox.py` - R43 strategy authority regressions.
- `backend/tests/forecast/test_runner.py` - Retry, dispatch, cancellation, and platform-partition regressions.
- `backend/tests/test_operational_migrations.py` - Old-schema quarantine and migration atomicity coverage.
- `backend/tests/test_phase5_optional_host.py` - Retained owner and bounded close retry coverage.

## Decisions Made

- Raw custom-strategy source is never executable input; only schema-versioned instructions and primitive panel values cross the launcher boundary.
- The creator alone receives the retry owner token. Replays receive canonical work or a typed bounded in-progress result and never freeze input.
- Durable publication, not in-memory submission, is dispatch acceptance. Polling/restart remains authoritative when a wake hint fails.
- The pre-R43 schema persisted no complete bind identity on queued jobs, so every legacy queued row is conservatively quarantined rather than guessed safe.
- Timed-out close is a retryable ownership state, not success. Active and closing registries together remain the authoritative owner set.

## Deviations from Plan

None - implementation followed the planned positive interpreter, owner-first publication, strict quarantine, and retained close ownership design.

## Verification

- Task 1 tracer: 14 passed; full sandbox file: 66 passed.
- Task 2 exact retry/migration contract: 6 passed; retry compatibility plus migration set: 16 passed.
- Task 3 exact Windows contract: 5 passed.
- Final Windows acceptance: **152 passed, 14 explicitly Linux-only skipped**.
- WSL/Linux native marker command: **not run** because `wsl.exe wslpath` and `wsl.exe --list --verbose` return exit code 1 with installation help and no usable distribution.

## Known Stubs

None.

## Issues Encountered

- The configured host lacks a usable WSL distribution. The unrun native `linux_process_group` verification is recorded in `.planning/WINDOWS.md` and `deferred-items.md`; Windows evidence was not used as a substitute.
- The optional-host suite emits pre-existing Polars deprecation and sortedness warnings from `backend/app/indicators/pipeline.py`; these were left out of scope and recorded for later maintenance.

## User Setup Required

None - no external service or dependency was added.

## Next Phase Readiness

- Plan 05-44 can consume deterministic R43 test names and closeout artifacts.
- Before ship, run `pytest -m linux_process_group` on WSL/Linux to close the open cross-platform evidence item.

## Self-Check: PASSED

- All implementation files and six task commits exist.
- No new source stub markers were found.
- Windows acceptance passed; the unavailable Linux verification is explicitly recorded rather than misreported.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-27*
