---
phase: 05-optional-enhancements
plan: "42"
subsystem: cross-platform-optional-host-regressions
tags: [windows, posix-resource, playwright, thesis, fail-closed, portability]
requires:
  - phase: 05-optional-enhancements
    plan: "29"
    provides: Phase 05 UAT verifier and diagnosed regression gap register
  - phase: 05-optional-enhancements
    plan: "36"
    provides: optional-host recovery and platform capability contracts
provides:
  - import-safe Linux isolation launcher that denies execution when POSIX resource controls are absent
  - five independently collected Playwright availability cases with stable report identities
  - canonical ThesisCheck rendering boundary with required numeric version identity
  - Windows-safe immutable artifact descriptors without weakening POSIX durability
affects: [05-29, SHDW-01, THES-01, FORE-01, windows-uat]
tech-stack:
  added: []
  patterns:
    - capability probes return complete all-false evidence when a required isolation primitive is unavailable
    - platform-sensitive optional compute tests assert Linux completion or non-POSIX fail-closed zero side effects
    - one readonly availability fixture per top-level Playwright test
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-42-SUMMARY.md
  modified:
    - backend/app/advanced/sandbox.py
    - backend/app/optional_artifacts.py
    - backend/tests/advanced/test_sandbox.py
    - backend/tests/test_phase5_optional_host.py
    - frontend/e2e/phase5-optional-enhancements.spec.ts
    - frontend/src/components/analysis/ThesisPanel.tsx
key-decisions:
  - "Missing POSIX resource support makes custom-strategy isolation unavailable and blocks limits/spawn; it never enables an unbounded fallback."
  - "Windows uses writable binary file descriptors for payload fsync and skips unsupported directory fsync, while POSIX durability behavior stays unchanged."
  - "Every availability combination owns a fresh Playwright Page, route fixture, telemetry object, timeout budget, and stable case ID."
  - "ChecksTable consumes the authoritative ThesisCheck[] contract instead of a local widened row shape."
patterns-established:
  - "Cross-platform fail-closed: module readiness may remain available while resource-limited work terminates with no record and no live action."
requirements-completed: [SHDW-01, THES-01, FORE-01]
coverage:
  - id: D1
    description: "Windows and resource-less runtimes import the production app and complete real lifespan while custom strategy isolation remains denied."
    requirement: SHDW-01
    verification:
      - kind: automated
        ref: "backend tests/advanced/test_sandbox.py + tests/test_phase5_optional_host.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Linux limit callbacks retain exact CPU, address-space, and file-size constraints before child execution."
    requirement: SHDW-01
    verification:
      - kind: automated
        ref: "test_linux_limit_callback_sets_cpu_address_space_and_file_size"
        status: pass
    human_judgment: false
  - id: D3
    description: "The five Phase 05 availability combinations collect and pass as independent browser tests."
    requirement: SHDW-01
    verification:
      - kind: automated_ui
        ref: "frontend/e2e/phase5-optional-enhancements.spec.ts scenario 1 stable IDs"
        status: pass
    human_judgment: false
  - id: D4
    description: "Thesis checks render from the canonical ThesisCheck contract under strict TypeScript and targeted browser coverage."
    requirement: THES-01
    verification:
      - kind: automated_ui
        ref: "frontend TypeScript + scenario 5-7 + WR-03"
        status: pass
    human_judgment: false
duration: 20m
completed: 2026-07-27
status: complete
---

# Phase 05 Plan 42: Optional Regression Closure Summary

**The production host now starts on Windows without POSIX `resource`, Linux isolation stays rigorously fail-closed, availability coverage has five independent browser budgets, and Thesis checks compile against their canonical persisted identity.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-26T17:15:15Z
- **Completed:** 2026-07-26T17:34:23Z
- **Tasks:** 3/3
- **Files modified:** 6 implementation/test files plus this summary

## Accomplishments

- Guarded the platform-only `resource` import and added explicit denial in capability probing, limit construction, and process spawn.
- Added fresh-interpreter, exact-limit, and real-lifespan regressions proving that missing resource support is local to custom strategy isolation.
- Replaced the shared scenario-1 callback loop with five top-level Playwright nodes: `all-available`, `shadow-unavailable`, `thesis-unavailable`, `forecast-unavailable`, and `all-unavailable`.
- Restored `ChecksTable` to the authoritative `ThesisCheck[]` contract.
- Fixed Windows immutable artifact I/O uncovered by the exact optional-host run: binary reads no longer truncate at control bytes, file fsync uses a writable descriptor, and unsupported directory fsync is POSIX-only.

## Task Commits

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1 failing portability coverage | `c3cd27e` | Four expected failures established the unconditional `resource` import defect |
| GREEN | Task 1 import-safe fail-closed sandbox | `383a843` | Tracer verification passed twice |
| GREEN | Task 2 isolated availability scenarios | `9b7c75c` | Five stable scenario-1 IDs collected once each |
| GREEN | Task 3 canonical Thesis check contract | `b1b75e7` | Strict TypeScript passed |
| Rule 1 | Windows optional-host portability | `8d6f7d9` | Exact backend plan verification passed, 32 tests |

**Plan metadata:** committed separately after validation.

## Files Created/Modified

- `backend/app/advanced/sandbox.py` — guarded platform import plus fail-closed probe, limit, and spawn gates.
- `backend/app/optional_artifacts.py` — Windows-safe binary descriptors and platform-correct directory durability.
- `backend/tests/advanced/test_sandbox.py` — fresh-import denial and exact Linux rlimit regressions.
- `backend/tests/test_phase5_optional_host.py` — real lifespan proof and platform-sensitive zero-side-effect assertions.
- `frontend/e2e/phase5-optional-enhancements.spec.ts` — five independent availability nodes.
- `frontend/src/components/analysis/ThesisPanel.tsx` — canonical `ThesisCheck[]` prop.

## Decisions Made

- Kept resource absence observable as an all-false capability proof and explicit `OSError`; no permissive or unbounded fallback was added.
- Kept Shadow and Forecast module readiness independent from per-job resource-limited execution. On non-POSIX hosts the work fails closed, produces no immutable result record, and invokes no live action.
- Preserved POSIX directory fsync exactly; Windows skips the unsupported directory-descriptor operation after the file and metadata payloads themselves are synced.
- Used stable bracketed case IDs in titles so collection/reporting failures identify one availability combination precisely.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Managed immutable artifacts were not portable to Windows**
- **Found during:** Overall backend verification
- **Issue:** Windows rejected read-only file fsync and directory descriptors, and text-mode `os.open` could truncate binary payloads at control bytes.
- **Fix:** Open payloads with `O_BINARY`, fsync writable file descriptors, and retain directory fsync only on POSIX.
- **Files modified:** `backend/app/optional_artifacts.py`
- **Commit:** `8d6f7d9`

**2. [Rule 1 - Bug] Optional compute success tests assumed POSIX resource limits**
- **Found during:** Overall backend verification
- **Issue:** Shadow distillation, Forecast requests, and queued recovery correctly failed closed on Windows but tests required Linux-only completion.
- **Fix:** Preserve Linux completion assertions while requiring non-POSIX resource termination, no result record, healthy v1 loop, and zero live actions.
- **Files modified:** `backend/tests/test_phase5_optional_host.py`
- **Commit:** `8d6f7d9`

---

**Total deviations:** 2 auto-fixed bugs
**Impact on plan:** Required for the plan's Windows real-host acceptance; no authority, network, schema, or execution scope was expanded.

## Issues Encountered

- An additional full `test_phase5_foundation.py` run passed 15 tests and exposed one pre-existing Windows-only mode-bit assertion (`0o700` appears as `0o777` under Windows stat semantics). The exact plan verification is green; this unrelated assertion is recorded in `deferred-items.md`.
- Existing Polars deprecation/sortedness warnings remain outside this plan.

## Test Results

```text
Backend exact plan command:
32 passed, 81 warnings in 74.57s

Frontend strict TypeScript:
node node_modules/typescript/bin/tsc --noEmit
PASS

Targeted Chromium:
5 independent scenario-1 cases + scenario 5-7 + WR-03
9 passed in 32.6s
```

## Acceptance Criteria

- **PASS — Windows lifespan:** production app imports and real optional-host lifespan completes when sandbox `resource` support is absent.
- **PASS — Linux isolation contract:** exact CPU, address-space, and file-size limit calls remain verified before spawn.
- **PASS — failure-local browser evidence:** five availability cases collect independently with unchanged timeout policy.
- **PASS — canonical Thesis identity:** strict TypeScript and targeted Thesis browser coverage pass without casts or local DTO widening.
- **PASS — authority boundaries:** resource-limited work creates no output record and all live-action spies remain zero.

## Threat Mitigation Evidence

- **T-05-42-01:** missing resource support cannot produce capability proof, limits, or child execution.
- **T-05-42-02:** real production lifespan and v1 loop complete on Windows while optional failures stay local.
- **T-05-42-03:** fake-resource regression verifies all three exact Linux rlimits.
- **T-05-42-04:** each availability result has a unique Playwright report identity and fresh Page.
- **T-05-42-05:** Thesis check rows retain canonical numeric version identity through strict type checking and browser rendering.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All diagnosed Phase 05 gaps G-05-96, G-05-97, and G-05-99 are closed by automated evidence.
- Phase 05 is ready for final verification/audit and milestone closeout.

## Self-Check: PASSED

- All six implementation/test files and this summary exist.
- Commits `c3cd27e`, `383a843`, `9b7c75c`, `b1b75e7`, and `8d6f7d9` exist in repository history.
- Exact backend, strict TypeScript, and targeted Chromium verification all passed.
