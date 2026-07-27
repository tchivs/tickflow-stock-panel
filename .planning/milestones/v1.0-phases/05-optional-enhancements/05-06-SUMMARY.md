---
phase: 05-optional-enhancements
plan: "06"
subsystem: operational-foundation
tags: [sqlite, migrations, append-only, immutable-artifacts, sha256, optional-modules, lazy-factory]
requires:
  - phase: 05-optional-enhancements
    plan: "02"
    provides: Shadow immutable import, evidence-set, candidate, evaluation, and retention contracts
  - phase: 05-optional-enhancements
    plan: "03"
    provides: Thesis immutable version, condition schedule, pending review, and lifecycle contracts
  - phase: 05-optional-enhancements
    plan: "04"
    provides: Forecast catalog, runner CAS, immutable record, outcome, and calibration contracts
  - phase: 05-optional-enhancements
    plan: "05"
    provides: Independent optional-capability availability and completed-v1 host contracts
provides:
  - one forward operational.db migration for all Phase 05 facts and guarded recovery cursors
  - domain-neutral immutable managed artifacts with atomic promotion and multi-layer digest verification
  - independent typed optional capability identities, lazy probes, factories, services, and lifecycle ownership
  - ten focused foundation tests without Shadow, Thesis, Forecast, main.py, router, or model wiring
affects: [05-08, 05-09, 05-10, 05-11, 05-12, 05-13, 05-14, SHDW-01, THES-01, FORE-01]
tech-stack:
  added: []
  patterns:
    - append-only SQLite facts with RESTRICT foreign keys and abort triggers
    - narrowly guarded monotonic schedule and forecast-job cursors
    - exclusive temporary namespace followed by atomic artifact promotion
    - independent cached deployment probes with lazy per-module service creation
key-files:
  created:
    - backend/app/optional_artifacts.py
    - backend/app/optional_modules.py
    - backend/tests/test_phase5_foundation.py
  modified:
    - backend/app/operational/migrations.py
key-decisions:
  - "Phase 05 persists every operational fact in the existing operational.db; only thesis schedules, forecast jobs, and the forecast inference lease have guarded update paths."
  - "Managed artifacts use server-generated UUID namespaces, relative public descriptors, canonical metadata and scope hashes, payload hashes, owner-only permissions, and atomic directory promotion."
  - "Optional module probes are independent and cached as deployment availability only; service creation stays lazy and probe or initialization failures are replaced with safe module-local status."
patterns-established:
  - "Phase 05 fact schema: every evidence, lineage, outcome, calibration, and review table rejects direct UPDATE and DELETE."
  - "Optional artifact verification: descriptor, metadata sidecar, scope digest, relative path, byte size, and payload digest must all agree before reads."
  - "Optional host isolation: probing or initializing one fixed capability identity cannot import, create, disable, or close another."
requirements-completed: [SHDW-01, THES-01, FORE-01]
coverage:
  - id: D1
    description: "Fresh and Phase 4 operational databases converge on one Phase 05 schema while preserving prior rows and rejecting fact mutation, orphan insertion, stale schedule movement, and illegal forecast transitions."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/test_phase5_foundation.py -k migration -x"
        status: pass
    human_judgment: false
  - id: D2
    description: "Managed bytes and Parquet remain root-contained and immutable, use private permissions and atomic promotion, and fail closed on collisions, escape descriptors, partial records, metadata changes, and payload tampering."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/test_phase5_foundation.py -k 'artifact or optional_identity' -x"
        status: pass
    human_judgment: false
  - id: D3
    description: "Shadow, Thesis, and Forecast expose independent typed lazy availability and service lifecycles while the base foundation remains free of sklearn, torch, Hugging Face, and Kronos imports."
    requirement: THES-01
    verification:
      - kind: unit
        ref: "backend/tests/test_phase5_foundation.py#test_optional_identity_is_independent_lazy_cached_and_light"
        status: pass
      - kind: unit
        ref: "backend/tests/test_phase5_foundation.py#test_optional_identity_probe_failure_is_sanitized_and_local"
        status: pass
    human_judgment: false
metrics:
  duration: 12m 40s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 06: Shared Optional Foundation Summary

**A single append-only operational migration, atomically promoted immutable artifact store, and independent lazy OptionalModuleHost now provide the shared failure-isolated foundation for all three optional vertical slices.**

## Performance

- **Duration:** 12m 40s
- **Started:** 2026-07-16T04:26:38Z
- **Completed:** 2026-07-16T04:39:18Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Appended one cohesive Phase 05 migration without changing prior migration bytes. It creates Shadow import/evidence/candidate facts, immutable Thesis versions and review lineage, durable Forecast jobs/records/outcomes/calibration, known lookup indexes, RESTRICT relations, immutable triggers, and narrowly guarded cursor transitions.
- Added `ManagedImmutableArtifactStore` for bytes and Parquet with server-only UUID identities, exclusive owner-only temporary namespaces, canonical metadata, scope and payload SHA-256 checks, relative public descriptors, atomic promotion, exact namespace validation, and fail-closed loads.
- Added fixed Shadow/Thesis/Forecast capability identities, safe typed statuses, a factory protocol, shared runtime service identity, independent cached probes, lazy service creation, module-local failure sanitization, and idempotent close behavior without heavy optional imports.
- Kept the scope at the shared foundation: no domain package, router, main lifespan wiring, model catalog, optional dependency, lockfile, container, queue, or second database was introduced.

## Task Commits

Each TDD task was committed at its RED and GREEN gates:

1. **Task 1 RED: Phase 05 migration contracts** — `3bf78bcd2af27a2c451501faf1ee420adc696293` (`test`)
2. **Task 1 GREEN: Append-only operational migration** — `4137fd4b47ddde45f438f45d9671d3a676e3f438` (`feat`)
3. **Task 2 RED: Artifact and optional-host contracts** — `6ace822021ddcde66d8ea3526893bcfa1a56e3e8` (`test`)
4. **Task 2 GREEN: Managed artifacts and lazy module host** — `f237cd4599460faab9d7cce843ce89130ff47ab2` (`feat`)
5. **Task 2 verification hardening: Owner-only artifact permissions** — `2ded01933f966bd7ba9f3560d0bb39e8b4a0f56e` (`test`)

## Files Created/Modified

- `backend/app/operational/migrations.py` — one appended migration containing all shared Phase 05 operational facts, indexes, immutable guards, and cursor transition constraints.
- `backend/app/optional_artifacts.py` — immutable descriptor plus atomic byte/Parquet artifact creation, lookup, verification, and loading.
- `backend/app/optional_modules.py` — fixed module identities, safe status DTO, factory/services protocols, lazy host lifecycle, and shared operational migration builder.
- `backend/tests/test_phase5_foundation.py` — focused migration, artifact, containment, tamper, permission, lazy-probe, failure-isolation, and light-import coverage.

## Verification

```text
cd backend && uv run pytest tests/test_phase5_foundation.py -k migration -x
pytest: 5 passed

cd backend && uv run pytest tests/test_phase5_foundation.py -k 'artifact or optional_identity' -x
pytest: 5 passed, 5 deselected

cd backend && uv run pytest tests/test_phase5_foundation.py -x
pytest: 10 passed
```

Only the plan-declared focused foundation suite was run. No formatter, linter, domain suite, host suite, browser suite, or project-wide suite was run.

## Threat Mitigation Evidence

- **T-05-06-01:** Upgrade/fresh/idempotent migration tests verify preservation and convergence; every fact table has update/delete guards, foreign keys are RESTRICT, schedule cursors are monotonic, and forecast jobs enforce legal transitions plus immutable identity columns.
- **T-05-06-02:** Artifact tests verify server-generated collision behavior, relative root containment, no overwrite, no temporary residue, atomic promotion, owner-only permissions, incomplete metadata rejection, descriptor escape rejection, and metadata/payload tamper rejection.
- **T-05-06-03:** Public descriptors contain relative paths only; module statuses contain exactly safe deployment availability fields and replace raw probe/initialization exceptions with fixed local codes and reasons.
- **T-05-06-04:** Tests prove probes are one-at-a-time and cached, services initialize only on demand, a broken Shadow probe does not affect Thesis, and base imports add no sklearn, torch, Hugging Face, or Kronos module.
- **T-05-06-SC:** No dependency declaration, lockfile, vendor source, container, or provisioning file changed. The existing locked `dev` extra was synced only into the isolated worktree environment so the declared pytest commands could run.

## Decisions Made

- Used composite Thesis predecessor and condition-check foreign keys where lineage requires same-parent identity, rather than relying on repository checks alone.
- Represented retry attempts and terminal Shadow evaluation attempts as append-only facts; mutation is reserved for operational cursors, not evidence.
- Kept artifact scope inside verified metadata but outside the public descriptor; the descriptor carries only its digest so callers can prove identity without disclosing bounded internal scope details.
- Made `status()` probe only the requested module and made `service()` initialize only after an available status, preserving independent module fate and a light base host.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used the surviving immutable artifact analog after the named frozen-panel file was absent**
- **Found during:** Task 2 read-first grounding
- **Issue:** `backend/app/backtest/frozen_panel.py`, named by the plan, is absent from this worktree.
- **Fix:** Used the plan's preserved pattern extract plus `backend/app/research/artifacts.py` for exclusive-create, permission, canonical serialization, checksum, and relative descriptor conventions.
- **Files modified:** `backend/app/optional_artifacts.py`, `backend/tests/test_phase5_foundation.py`
- **Verification:** All five artifact/optional-identity focused tests pass.
- **Committed in:** `f237cd4599460faab9d7cce843ce89130ff47ab2`, `2ded01933f966bd7ba9f3560d0bb39e8b4a0f56e`

---

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking reference).
**Impact on plan:** The replacement is the exact surviving artifact pattern already cited by the plan and did not expand production scope.

## Issues Encountered

- The isolated worktree initially lacked pytest in its freshly created default `uv` environment. The repository's already-declared, locked `dev` extra was synced without modifying `pyproject.toml`, `uv.lock`, or any provisioning artifact; the exact plan commands then ran unchanged.
- The worktree arrived with detached HEAD. Before the first commit, execution attached it to the required isolated `worktree-agent-05-06` branch; no primary-checkout path or protected branch was inspected or modified.

## TDD Gate Compliance

Both task-level RED/GREEN sequences are present and ordered: `3bf78bc` precedes `4137fd4` for Task 1, and `6ace822` precedes `f237cd4` for Task 2. The post-GREEN `2ded019` commit adds explicit permission evidence without changing production behavior.

## Known Stubs

None. Empty mappings and optional `None` values in `OptionalModuleHost` are lifecycle state, not rendered mock data or fallback services. Every delivered production API is exercised by the focused suite.

## User Setup Required

None. Optional capability factories are intentionally unregistered until their owning vertical-slice plans; the completed v1 application remains unaffected.

## Next Phase Readiness

- Plans 05-08 through 05-13 can build Shadow, Thesis, and Forecast repositories/adapters against one migrated operational path and the shared artifact primitive.
- Plan 05-14 can register real factories and wire the production lifespan/API status boundary without changing the foundation's independent typed availability contract.
- No full domain module or `main.py` wiring was pulled forward into this plan.

## Self-Check: PASSED

Verified all four declared implementation/test artifacts and this summary exist, all five task commits resolve as commits, the final focused suite passes 10/10, no tracked dependency or provisioning file changed, and no changed artifact contains a delivery-blocking stub.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
