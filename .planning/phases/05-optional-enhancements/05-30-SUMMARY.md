---
phase: 05-optional-enhancements
plan: "30"
subsystem: shadow-api
status: complete
tags: [pydantic, fastapi, sqlite, canonical-json, validation, security]
requires:
  - phase: 05-optional-enhancements
    plan: "17"
    provides: immutable Shadow facts, real-host acceptance baseline, and descriptor-less SHDW-01 status
provides:
  - strict extra-forbid exit and holding assumption schemas
  - shared structural and canonical-byte validation at API, service, repository, hydration, and projection boundaries
  - focused bypass and zero-durable-work contracts for malformed assumptions
affects: [05-18, 05-19, 05-29, SHDW-01, shadow-production]
tech-stack:
  added: []
  patterns:
    - one shared canonical assumption serializer at every callable boundary
    - fail-closed typed hydration and public projection for immutable facts
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-30-SUMMARY.md
  modified:
    - backend/app/shadow/schemas.py
    - backend/app/shadow/api.py
    - backend/app/shadow/service.py
    - backend/app/shadow/repository.py
    - backend/app/shadow/projections.py
    - backend/tests/shadow/test_distillation.py
key-decisions:
  - "Shadow assumptions admit only the existing fixed_holding_days exit contract and governed price-adjustment holding contract; there is no free-form escape field."
  - "The same 2-level/16-key/32-item/128-UTF-8-byte/finite-number walker and 4096/8192 canonical-byte gates execute before service work, repository append, historical hydration, and projection."
patterns-established:
  - "Canonical assumption boundary: validate raw structure and bytes, validate exact Pydantic allowlists, then serialize sorted compact JSON once."
  - "Historical Shadow assumption JSON must already be canonical and schema-valid; malformed stored mappings fail closed instead of being truncated."
requirements-completed: [SHDW-01]
coverage:
  - id: D1
    description: "Shadow exit and holding assumptions cross API, service, persistence, hydration, and projection only through one strict bounded canonical contract, while invalid direct calls append zero candidate facts."
    requirement: SHDW-01
    verification:
      - kind: unit
        ref: "cd backend && uv run pytest tests/shadow/test_distillation.py -k 'bounded_assumption_schema or assumption_byte_ceiling or direct_boundary_rejects_oversize' -x (3 passed)"
        status: pass
    human_judgment: false
duration: 13m
completed: 2026-07-17
---

# Phase 05 Plan 30: Strict Bounded Shadow Assumption Boundary Summary

**Strict allowlisted Shadow assumptions now use one canonical, resource-bounded contract from request parsing through immutable persistence, replay hydration, and public projection.**

## Performance

- **Duration:** 13 minutes
- **Started:** 2026-07-17T07:13:23Z
- **Completed:** 2026-07-17T07:26:23Z
- **Tasks:** 1/1
- **Files modified:** 6

## Accomplishments

- Added frozen, extra-forbid `ExitAssumptions` and `HoldingAssumptions` models limited to the existing consumed fixed-horizon and governed price-adjustment facts.
- Centralized depth, key-count, collection-length, UTF-8 string, finite-number, per-object byte, combined-byte, sorted-JSON, and canonical historical replay checks.
- Enforced the same validated records before distiller invocation, repository lookup/append, row hydration, and candidate projection so direct callers and malformed storage cannot bypass the API model.
- Added focused RED/GREEN contracts for valid replay identity, extra keys, depth 3, 17 keys, 33 items, 129-byte strings, non-finite numbers, 4097-byte objects, 8193-byte combined payloads, zero distiller calls, and zero invalid candidate rows.

## Task Commits

Each TDD gate was committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: Add failing bounded assumption contracts | `df5a1a5` | Focused contract failed against unrestricted dictionaries |
| GREEN | Task 1: Enforce the bounded assumption contract across every Shadow boundary | `8ed9e31` | Focused selector passed 3 tests; full file passed 10 tests |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/shadow/schemas.py` — exact assumption DTOs, structural gates, canonical serializers, byte ceilings, and persisted replay validation.
- `backend/app/shadow/api.py` — typed `DistillRequest` assumption fields plus combined validation.
- `backend/app/shadow/service.py` — direct-call validation and canonical model dumps before invoking the distiller.
- `backend/app/shadow/repository.py` — repeated pre-append validation, canonical persistence, and fail-closed row hydration.
- `backend/app/shadow/projections.py` — same typed allowlist for candidate responses instead of recursive best-effort projection.
- `backend/tests/shadow/test_distillation.py` — API, service, repository, replay, projection, and no-durable-work boundary contracts.

## Decisions Made

- Kept the public assumption surface deliberately small: `kind=fixed_holding_days` plus bounded `days`, and the existing `unadjusted_execution_vs_forward_adjusted_research` price-adjustment declaration. Future production wiring must consume this contract rather than reopen generic JSON.
- Applied raw resource checks before Pydantic schema checks. This ensures hostile oversized or deeply recursive data is rejected before model normalization and lets direct service/repository callers receive the same boundary as HTTP callers.
- Required persisted JSON bytes to equal the shared compact sorted serialization. Historical facts with whitespace/order divergence, non-canonical values, extra fields, or excess resources fail closed rather than materializing a different public fact.

## Deviations from Plan

None - plan executed exactly as written.

## Verification

```text
cd backend && uv run pytest tests/shadow/test_distillation.py -k "bounded_assumption_schema or assumption_byte_ceiling or direct_boundary_rejects_oversize" -x
Result: PASS — 3 passed, 7 deselected.

cd backend && uv run pytest tests/shadow/test_distillation.py -x
Result: PASS — 10 passed.

cd backend && uv run ruff check app/shadow/schemas.py app/shadow/api.py app/shadow/service.py app/shadow/repository.py app/shadow/projections.py tests/shadow/test_distillation.py
Result: PASS — no diagnostics.
```

## Threat Mitigation Evidence

- **T-05-30-01:** `DistillRequest` now resolves both assumption objects to exact extra-forbid Pydantic models; browser-supplied additional authority is rejected.
- **T-05-30-02:** Raw structural validation rejects recursive depth, oversized mappings/lists/UTF-8 strings, non-finite or excessive numbers, and canonical byte overruns before work.
- **T-05-30-03:** `ShadowRepository.append_candidate` repeats validation before evidence lookup or transaction work, persists the shared canonical strings, and revalidates canonical bytes during hydration.
- **T-05-30-04:** Candidate projection reuses the typed assumption pair and cannot recursively expose unknown or unbounded stored mappings.
- No new endpoint, database, data lake, container, external request, action collaborator, or market authority was introduced.

## TDD Gate Compliance

- RED commit `df5a1a5` established the failing API/direct-boundary/resource contracts before production changes.
- GREEN commit `8ed9e31` implemented the shared contract and passed both the exact plan selector and the complete distillation test file.
- No refactor-only commit was needed after targeted Ruff and test verification.

## Known Stubs

None. The models, validation paths, repository enforcement, hydration, and projection are all wired to production boundaries; no mock or empty fallback satisfies the acceptance path.

## Issues Encountered

- The local `uv` environment initially retained the previously built backend package while the source changed. Refreshing the existing local package and dev/shadow extras made the exact `uv run pytest` command load the current source; no dependency or project metadata changed.

## User Setup Required

None.

## Next Phase Readiness

- Plan 05-18 can consume the exact bounded DTO without duplicating schema, service, repository, or projection work.
- SHDW-01 remains explicitly descriptor-less and flagged for end-to-end production verification until the named Plan 05-18 host/browser tracer passes; this plan does not synthesize a descriptor or grant activation authority.

## Self-Check: PASSED

- Summary and all six implementation/test artifacts exist in the isolated worktree.
- RED `df5a1a5` and GREEN `8ed9e31` resolve as commits.
- The exact plan selector, complete distillation file, and targeted Ruff check passed.
- Neither task commit deleted a tracked file; scoped implementation paths are clean.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
