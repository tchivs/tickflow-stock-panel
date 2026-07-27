---
phase: 05-optional-enhancements
plan: "12"
subsystem: thesis-lifecycle
tags: [fastapi, sqlite, append-only, leases, idempotency, object-authorization, audit-projections]
requires:
  - phase: 05-optional-enhancements
    plan: "09"
    provides: immutable Thesis versions, structured conditions, governed evidence resolution, and append-only check schema
provides:
  - bounded restart-safe per-condition due acquisition with lease recovery and canonical check identity
  - matched-only pending conclusions plus server-principal confirm/reject authority
  - immutable version/check/pending/review history with deny-by-default display projections
  - authenticated stock-scoped Thesis routes with typed conflicts, validation, and local unavailability
  - safe paginated version, check, and pending resources for the Analysis UI
  - atomic current-version/current-state review conflict enforcement
  - safe resolver failure facts without exception or local-path leakage
  - independent daily, weekly, monthly, and quarterly timezone-aware cursor advancement
affects: [05-14-optional-host, 05-16-thesis-ui, THES-01]
tech-stack:
  added: []
  patterns:
    - BEGIN IMMEDIATE lease/review serialization with guarded monotonic schedule transitions
    - unique condition-and-due identity returning canonical persisted checks after replay or restart
    - official state derived only from immutable confirmed review events
    - opaque object IDs resolved to persisted instruments before authorization
key-files:
  created:
    - backend/app/theses/scheduler.py
    - backend/app/theses/service.py
    - backend/app/theses/projections.py
    - backend/app/theses/api.py
  modified:
    - backend/app/theses/repository.py
    - backend/app/theses/schemas.py
key-decisions:
  - "Expired Thesis leases are cleared as their own guarded transition before reacquisition because the migration trigger deliberately forbids direct lease-owner transfer."
  - "A check and its matched pending conclusion append in one immediate transaction; replay consults the unique (condition_id,due_at) identity before invoking governed evidence again."
  - "Confirm re-resolves governed evidence and requires the same matched fingerprint, while both confirm and reject transactionally re-read pending, current-version, processed-review, and official-state facts."
  - "Public projections expose complete anchors, condition cadence, checks, evidence summaries, pending/review lineage, and rationales while withholding reviewer principals, lease owners, SQL, raw evidence, and local paths."
patterns-established:
  - "Recovery cursor, not authority: the scheduler leases persisted due identities and advances cadence only after the service returns a canonical immutable check."
  - "One pending per matched check: database uniqueness and one transaction prevent duplicate proposals across retry, parallel execution, and restart."
  - "Non-enumerating object authorization: opaque IDs resolve to their persisted instrument before scope checks, and foreign resources return the same safe 404."
requirements-completed: [THES-01]
coverage:
  - id: D1
    description: "Each current condition advances independently through bounded lease acquisition, duplicate/parallel winner selection, interruption recovery, restart, and immutable canonical checks."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/theses/test_scheduler.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Only matched governed evidence creates one pending conclusion; human confirm/reject preserves immutable audit history and cannot invoke trading-domain actions."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/theses/test_lifecycle.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Stock-scoped Thesis HTTP routes expose deny-by-default paginated projections, strict review bodies, typed 409/404/422 outcomes, and Thesis-local typed 503 unavailability."
    requirement: THES-01
    verification: []
    human_judgment: true
    rationale: "The production optional-host registration and real HTTP matrix are explicitly owned by Plan 05-14; this plan supplies and imports the complete router contract."
metrics:
  duration: 14m 8s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 12: Thesis Evidence-Check Review Lifecycle Summary

**Restart-safe per-condition leases now produce one canonical immutable check and matched-only pending conclusion, while stock-scoped APIs reserve official invalidation for revalidated server-principal review.**

## Performance

- **Duration:** 14m 8s
- **Started:** 2026-07-16T06:17:44Z
- **Completed:** 2026-07-16T06:31:52Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Added bounded stable-order due scanning with independent timezone-aware cadence, guarded short leases, expired-lease recovery, parallel winner selection, and retry-safe cursor advancement.
- Made `(condition_id,due_at)` the immutable check identity and atomically linked only matched checks to one pending invalidation proposal; insufficient, error, and not-matched results never change official state.
- Added server-authoritative confirm/reject with bounded rationale, session principal, current-version/current-state conflict checks, governed evidence revalidation for confirmation, and zero trading-domain collaborators.
- Added complete deny-by-default audit projections and stock-scoped FastAPI resources for versions, condition cadence/checks, pending conclusions, history, review conflicts, and local typed unavailability.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement restart-safe per-condition checks and pending conclusions** — `a3847cb66bd865e22751505f0af56fe4703db956` (`feat`)
2. **Task 2: Add server-authoritative review, safe projection, and stock-scoped API** — `abc58805b16bb0c16fbe7b65590fbb079d60ba57` (`feat`)

The failing-first scheduler/lifecycle contracts were inherited from Plan 05-03. Before implementation, the exact focused command failed at the expected missing `app.theses.scheduler` production boundary; both task implementations then made all 49 Thesis nodes green.

## Files Created/Modified

- `backend/app/theses/scheduler.py` — bounded due lease scanner and timezone-aware daily/weekly/monthly/quarterly cursor advancement.
- `backend/app/theses/service.py` — governed check orchestration, one-pending semantics, server-principal review, official-state derivation, and immutable history assembly.
- `backend/app/theses/projections.py` — hand-written allowlists for complete version, anchor, condition, schedule, check, evidence, pending, and review display records.
- `backend/app/theses/api.py` — authenticated stock-scoped create/revise/read/check/history/confirm/reject routes with pagination and safe typed errors.
- `backend/app/theses/repository.py` — transactional due acquisition/recovery, canonical outcome append, pending/review facts, and review conflict primitives.
- `backend/app/theses/schemas.py` — minimum and maximum rationale bounds for typed review decisions.

## Decisions Made

- Recovered an expired lease by clearing it first and reacquiring it second. This preserves the Phase 05 migration trigger's invariant that lease ownership cannot transfer directly between workers.
- Checked canonical `(condition_id,due_at)` persistence before resolving evidence. Duplicate, retry, restart, and interruption-after-append paths therefore return the existing fact without reading evidence a second time.
- Appended the immutable check and matched pending proposal inside one immediate transaction. A pending conclusion cannot exist without its exact version, condition, due check, and evidence fingerprint.
- Revalidated confirmation against a fresh governed result and identical evidence fingerprint; rejection still revalidates processed/current-version/official-state facts transactionally while preserving the original evidence.
- Kept reviewer principals in the immutable internal review event for attribution but removed them from every public projection.

## Verification

```text
RED: cd backend && uv run pytest tests/theses/test_scheduler.py tests/theses/test_lifecycle.py -x
Result before implementation: expected ModuleNotFoundError for app.theses.scheduler

Task 1: cd backend && uv run pytest tests/theses/test_scheduler.py tests/theses/test_lifecycle.py -x
Result: 29 passed

Overall: cd backend && uv run pytest tests/theses -x
Result: 49 passed

Import/syntax smoke: cd backend && uv run python -m py_compile app/theses/repository.py app/theses/scheduler.py app/theses/service.py app/theses/projections.py app/theses/api.py
Result: passed
```

Only plan-declared focused Thesis commands and module import compilation were run. No formatter, linter, browser suite, unrelated host suite, or project-wide command was run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added the lifecycle persistence primitives required by the declared scheduler and review contracts**
- **Found during:** Task 1 (restart-safe per-condition checks and pending conclusions)
- **Issue:** Plan 05-09 had supplied immutable version/check storage, but the direct RED contracts required bounded due acquisition, lease recovery, atomic check-plus-pending append, and pending/review lookup methods that were not present in `ThesisRepository`; implementing them outside the repository would have duplicated unsafe SQL conventions.
- **Fix:** Extended the existing repository with immediate transactions, guarded cursor transitions, canonical replay, pending/review append and lookup, current-state conflict checks, and a backward-compatible injected-clock alias.
- **Files modified:** `backend/app/theses/repository.py`
- **Verification:** `test_scheduler.py` and `test_lifecycle.py` pass all duplicate, parallel, interruption, restart, review, and immutability cases.
- **Committed in:** `a3847cb66bd865e22751505f0af56fe4703db956`

**2. [Rule 2 - Missing Critical Validation] Enforced the UI and authority contract's minimum review rationale at the schema boundary**
- **Found during:** Task 2 (server-authoritative review and API)
- **Issue:** The inherited review schema bounded only maximum length, while the approved UI contract requires a substantive reason of at least ten characters.
- **Fix:** Raised `ReviewDecisionRequest.rationale` to `min_length=10`; the route-specific strict body uses the same bound and rejects all browser authority extras.
- **Files modified:** `backend/app/theses/schemas.py`, `backend/app/theses/api.py`
- **Verification:** All 49 Thesis contract nodes pass, including strict review body validation and lifecycle review behavior.
- **Committed in:** `abc58805b16bb0c16fbe7b65590fbb079d60ba57`

---

**Total deviations:** 2 auto-fixed (2 missing critical functionality/validation).
**Impact on plan:** Both changes are required to satisfy D-07/D-08 and the declared threat mitigations; they remain inside the Thesis domain and introduce no unrelated scope.

## Threat Mitigation Evidence

- **T-05-12-01:** Immediate write transactions, guarded leases, stable bounded ordering, expiry recovery, and unique due identity make duplicate/parallel/interrupted/restarted work converge on one canonical check.
- **T-05-12-02:** Strict request models reject undeclared browser principal/state/evidence fields; review operations require the session-derived server principal.
- **T-05-12-03:** Automation appends checks and pending proposals only. Official state derives exclusively from a confirmed immutable review event, and lifecycle action spies remain at zero.
- **T-05-12-04:** Exact version, condition, due time, evidence fingerprint, decision, rationale, and event time remain append-only and readable through allowlisted projections.
- **T-05-12-05:** Scanner batches and history pages are bounded; safe errors omit raw exceptions, paths, SQL, provider payloads, and principal internals.

## Issues Encountered

- The isolated worktree's virtual environment initially lacked the locked `pytest` executable. `uv sync --extra dev` installed only the repository's existing locked development extra without changing `pyproject.toml` or `uv.lock`.
- The assigned worktree began detached. Execution attached `worktree-agent-05-12` before every commit; no protected branch or primary checkout was modified.

## TDD Gate Compliance

Plan 05-03 had already committed the strict RED scheduler/lifecycle nodes. This execution first observed the declared `ModuleNotFoundError: app.theses.scheduler` RED boundary, then committed Task 1 GREEN behavior and verified 29/29 focused nodes. Task 2 retained those contracts, completed the projection/API surface, and the full focused Thesis suite passed 49/49.

## Known Stubs

None. Empty evidence lists represent explicit governed non-observation, `None` values represent legitimate absent evidence/review/schedule fields, and every route delegates to persisted Thesis services rather than mock or placeholder data.

## User Setup Required

None - no dependencies, migrations, external services, or environment variables were added.

## Next Phase Readiness

- Plan 05-14 can register `app.theses.api.router`, construct `ThesisRepository`/`ThesisService`/`ThesisDueScanner` on the shared operational database, and supply `resolve_thesis_subject_scope` plus the session reviewer principal.
- Plan 05-16 can consume paginated versions, checks, pending conclusions, complete history, and typed 409/404/422/503 outcomes without receiving scheduler leases, reviewer principals, or raw evidence.
- The descriptor-less THES-01 assumption remains explicitly flagged unverified; this plan did not fabricate or auto-dismiss any `check_*` descriptor.

## Self-Check: PASSED

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
