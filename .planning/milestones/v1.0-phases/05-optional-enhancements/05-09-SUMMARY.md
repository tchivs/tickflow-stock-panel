---
phase: 05-optional-enhancements
plan: "09"
subsystem: thesis-domain
tags: [pydantic, sqlite, immutable-versions, optimistic-locking, condition-ast, evidence-fingerprints]
requires:
  - phase: 05-optional-enhancements
    plan: "03"
    provides: strict failing-first Thesis contracts for schemas, immutable versions, conditions, and history
  - phase: 05-optional-enhancements
    plan: "06"
    provides: append-only Thesis tables, RESTRICT foreign keys, immutable triggers, and guarded schedule cursor schema
provides:
  - strict canonical valuation-anchor, revision, condition-AST, evidence, check-result, and review DTOs
  - atomic predecessor-linked immutable Thesis versions with stale-write rejection and deterministic latest derivation
  - governed source-specific evidence resolution with bounded provenance and SHA-256 fingerprints
  - fixed typed condition dispatch preserving missing evidence as insufficient rather than false or zero
affects: [05-12-thesis-lifecycle, 05-14-optional-host, 05-16-thesis-ui, THES-01]
tech-stack:
  added: []
  patterns:
    - one BEGIN IMMEDIATE append transaction for identity, version, anchors, conditions, and schedules
    - optimistic predecessor compare under a SQLite write lock
    - lineage-head selection by successor absence with deterministic ordering
    - source-specific allowlists and fixed callable comparison dispatch
key-files:
  created:
    - backend/app/theses/__init__.py
    - backend/app/theses/schemas.py
    - backend/app/theses/repository.py
    - backend/app/theses/evidence.py
    - backend/app/theses/conditions.py
  modified: []
key-decisions:
  - "Current Thesis version is the predecessor-chain head selected by successor absence, then deterministic version/created-at/id ordering; response order and mutable status never decide it."
  - "Revisions take an expected predecessor and acquire a SQLite immediate write transaction before comparing it, so stale writers fail before any version, anchor, condition, or schedule row is appended."
  - "Governed readers return bounded source facts only; missing, stale, malformed, non-finite, or failing sources map to insufficient_evidence or safe error with no fabricated observation."
patterns-established:
  - "Immutable Thesis revision: omitted anchors are revalidated and re-appended canonically, omitted conditions receive new version-local IDs linked through copied_from_condition_id, and all old facts remain readable."
  - "Condition execution boundary: Pydantic validates a source-specific field/unit/operator AST before fixed Python callables compare typed finite evidence."
requirements-completed: [THES-01]
coverage:
  - id: D1
    description: "Canonical anchors and source-specific condition ASTs reject incomplete, non-finite, hostile, free-form, global-cadence, and browser-authority inputs before persistence."
    requirement: THES-01
    verification:
      - kind: unit
        ref: "backend/tests/theses/test_contracts.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Thesis creation and revision atomically append immutable predecessor-linked facts, reject stale predecessors, select the chain head deterministically, and preserve complete old history."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/theses/test_versions.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Governed evidence and fixed condition dispatch preserve bounded fingerprints and explicit insufficient/error outcomes without executable condition text or fabricated values."
    requirement: THES-01
    verification:
      - kind: unit
        ref: "cd backend && uv run pytest tests/theses/test_contracts.py -k 'condition or evidence or insufficient' -x"
        status: pass
    human_judgment: false
metrics:
  duration: 9m 23s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 09: Immutable Thesis Domain Summary

**Predecessor-guarded SQLite transactions now append canonical Thesis versions while fixed source resolvers and typed condition dispatch preserve auditable evidence, deterministic lineage, and explicit insufficiency.**

## Performance

- **Duration:** 9m 23s
- **Started:** 2026-07-16T05:53:26Z
- **Completed:** 2026-07-16T06:02:49Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Added strict Pydantic contracts for complete valuation ranges, canonical assumptions and limitations, source-specific conditions, per-condition cadence/timezone, revisions, reviews, evidence facts, and the four safe check results.
- Implemented atomic immutable creation and revision over the Phase 05 operational schema, including persisted instrument identity, predecessor optimistic locking, canonical JSON, condition-local schedules, copied-condition lineage, old-schedule deactivation, and server-safe projections.
- Derived latest versions from the predecessor graph rather than response order or mutable state, while database triggers preserve versions, anchors, conditions, and checks against direct update/delete.
- Added governed market/financial/analysis reader dispatch that freezes bounded observation identity, revision, as-of, unit, value, and SHA-256 fingerprint before fixed operator evaluation.
- Kept absent, stale, malformed, non-finite, or failing evidence explicit as `insufficient_evidence` or safe `error`; no path coerces it to zero, false, matched, or official state.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement immutable thesis versions, valuation anchors, and structured conditions** — `9fe1ec5f26656ac99ce84656e757aa454f59c97b` (`feat`)
2. **Task 2: Resolve governed evidence and evaluate the restricted condition AST** — `3fe521222711c709d67a2b5b3effc74737768329` (`feat`)

The failing-first contract gates were previously committed by Plan 05-03 as `b719fe466a903828e3e46e409d2c9b7ce4cc181d` and `14490ad5dba7d82f8cfc44ecff6d67fc15f7a30b`; this plan supplied their GREEN production boundary.

## Files Created/Modified

- `backend/app/theses/__init__.py` — declares the Thesis domain package.
- `backend/app/theses/schemas.py` — strict canonical anchors, assumptions, condition AST, revision, review, evidence, and result contracts.
- `backend/app/theses/repository.py` — short-lived parameterized SQLite transactions, immutable lineage, optimistic predecessor checks, safe projections, schedules, and condition checks.
- `backend/app/theses/evidence.py` — fixed governed-reader boundary with bounded provenance, freshness checks, explicit missing/error semantics, and deterministic fingerprints.
- `backend/app/theses/conditions.py` — fixed scalar/range operator dispatch over validated typed evidence.

## Verification

```text
cd backend && uv run pytest tests/theses/test_contracts.py tests/theses/test_versions.py -x
pytest: 20 passed

cd backend && uv run pytest tests/theses/test_contracts.py -k 'condition or evidence or insufficient' -x
pytest: 5 passed, 5 deselected
```

Only the plan-declared focused Thesis commands were run. No formatter, linter, browser suite, lifecycle/scheduler suite, or project-wide command was run.

## Decisions Made

- Used `BEGIN IMMEDIATE` before reading the current predecessor so concurrent revisers serialize at the database boundary; the expected predecessor remains the explicit optimistic-lock token.
- Defined current as the unique predecessor-chain head (`NOT EXISTS` successor), with version, created-at, and opaque ID ordering as deterministic corruption-safe tie breakers rather than trusting insertion or response order.
- Re-appended omitted anchors as identical canonical content because anchors are version-owned facts; re-appended omitted conditions with new IDs and `copied_from_condition_id` lineage so each active version owns independent cadence while prior checks remain attached to their exact historical condition.
- Kept official state derived from immutable confirmed review events for the exact version. Neither version rows, schedules, evidence resolvers, nor browser payloads can write official state.
- Limited source readers to one fixed call shape after schema validation and projected only bounded evidence fields. Raw provider payloads, exceptions, source paths, SQL, and principal internals are not exposed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The fresh isolated worktree environment did not initially contain pytest. The repository's existing locked `dev` extra was synced without changing `pyproject.toml` or `uv.lock`, after which the original RED and GREEN commands ran unchanged.
- The assigned worktree began detached. Execution attached `worktree-agent-05-09` before any commit, as required; no primary checkout or protected branch was modified.

## TDD Gate Compliance

Plan 05-03 supplied the strict RED contracts in `b719fe466a903828e3e46e409d2c9b7ce4cc181d` and `14490ad5dba7d82f8cfc44ecff6d67fc15f7a30b`. Before implementation, the focused suite was observed failing at the declared `ModuleNotFoundError: app.theses` boundary. Task commits `9fe1ec5f26656ac99ce84656e757aa454f59c97b` and `3fe521222711c709d67a2b5b3effc74737768329` then supplied GREEN behavior, and the exact 20-node suite passed.

## Threat Mitigation Evidence

- **T-05-09-01:** `extra="forbid"`, bounded enums, source-specific field/unit maps, canonical JSON, and fixed comparison callables reject hostile SQL/Python/free-form condition input before lookup or persistence.
- **T-05-09-02:** one immediate append transaction plus expected-predecessor comparison prevents partial/stale revisions; Phase 05 triggers reject direct mutation while old projections and checks stay readable.
- **T-05-09-03:** request DTOs reject official state, reviewer, evidence, creator, version, and predecessor authority; repository projections omit creator principals and resolve the persisted instrument identity.
- **T-05-09-04:** typed evidence statuses and finite/freshness validation ensure missing and malformed observations never become false, zero, or matched.
- **T-05-09-05:** public projections contain canonical bounded facts only and omit local database paths, SQL, raw exceptions, raw provider payloads, tracebacks, and principal internals.

## Known Stubs

None. Optional `None` values model legitimate missing/error evidence and absent schedule leases; empty evidence lists are the explicit non-observation contract, not mock data or a UI placeholder.

## User Setup Required

None - no dependencies, external services, migrations, or environment variables were added.

## Next Phase Readiness

- Plan 05-12 can build bounded due scanning, pending conclusions, and server-principal review over immutable versions, per-condition schedules, append-only checks, and governed resolver results.
- Later host/API/UI plans can expose object-scoped projections without granting browser authority over identity, evidence fingerprints, official state, or review principals.
- The descriptor-less THES-01 assumption remains flagged unverified; this plan did not fabricate or auto-dismiss any `check_*` descriptor.

## Self-Check: PASSED

Verified all five declared production files and this summary exist, both task commits and both inherited RED commits resolve, the exact focused suite passes 20/20, no tracked dependency or provisioning file changed, and no changed source contains TODO/FIXME/placeholder delivery stubs.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
