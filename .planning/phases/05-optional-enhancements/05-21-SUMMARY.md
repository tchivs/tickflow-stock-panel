---
phase: 05-optional-enhancements
plan: "21"
subsystem: thesis-lifecycle
tags: [fastapi, sqlite, pytest, timezone, pagination, immutable-history]
requires:
  - phase: 05-optional-enhancements
    plan: "18"
    provides: completed Phase 05 optional-host baseline and server-owned authority conventions
provides:
  - strict allowlisted Thesis condition resolution with separately persisted instrument authority
  - Asia/Shanghai local-calendar evidence lookup and instrument-bound observed fingerprints
  - current-version unreviewed actionable-pending query plus explicit all-version history states
  - repository-owned bounded versions, checks, pending, and history API pages
affects: [05-24, 05-32, THES-01, thesis-production]
tech-stack:
  added: []
  patterns:
    - explicit strict DTO construction at repository-to-resolver trust boundaries
    - ownership-filtered SQLite count and LIMIT/OFFSET before projection
    - separate actionable current work from immutable all-version review history
key-files:
  created:
    - backend/tests/theses/test_api.py
    - .planning/phases/05-optional-enhancements/05-21-SUMMARY.md
  modified:
    - backend/app/theses/evidence.py
    - backend/app/theses/repository.py
    - backend/app/theses/service.py
    - backend/app/theses/api.py
    - backend/tests/theses/test_lifecycle.py
    - backend/tests/theses/test_scheduler.py
key-decisions:
  - "ThesisService constructs the exact nine-field ThesisCondition payload and supplies the canonical persisted instrument as a separate resolver argument; repository metadata is never accepted as condition authority."
  - "All public Thesis ledgers use uniform offset/limit/items/total/has_more pages whose ownership predicate, count, ordering, LIMIT, and OFFSET are repository-owned."
  - "The actionable endpoint contains only current-version unreviewed pending conclusions; the history endpoint retains every version with actionable, superseded, confirmed, or rejected state."
patterns-established:
  - "Timezone identity: convert an aware due instant through ZoneInfo(condition.timezone) once, then use that local date for reader lookup and freshness bounds."
  - "Observed evidence identity: canonical instrument participates in the same fingerprint payload as source, revision, field, value, unit, and date."
requirements-completed: [THES-01]
coverage:
  - id: D1
    description: "Production-shaped augmented repository conditions resolve through an exact strict payload on the configured Shanghai calendar date, with instrument-bound evidence identity."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/theses/test_lifecycle.py#test_strict_resolver_payload_uses_condition_timezone_and_instrument_identity"
        status: pass
    human_judgment: false
  - id: D2
    description: "Only current-version unreviewed pending conclusions are actionable while superseded and reviewed facts remain immutable with explicit history state."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/theses/test_lifecycle.py#test_actionable_pending_contains_only_current_unreviewed_conclusions"
        status: pass
      - kind: integration
        ref: "backend/tests/theses/test_lifecycle.py#test_paged_history_preserves_superseded_reviewed_and_actionable_state"
        status: pass
    human_judgment: false
  - id: D3
    description: "Versions, checks, actionable pending, and all-version history are bounded in owned SQLite queries before projection and exposed through uniform public pages."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/theses/test_lifecycle.py#test_paged_history_executes_limit_and_offset_before_materialization"
        status: pass
      - kind: integration
        ref: "backend/tests/theses/test_api.py (5 named paging and ownership tests)"
        status: pass
    human_judgment: false
duration: 15m05s
completed: 2026-07-17
status: complete
---

# Phase 05 Plan 21: Strict Timezone-Correct Thesis Lifecycle Summary

**Strict server-owned Thesis conditions now resolve on their declared Shanghai calendar day, expose only current unreviewed work as actionable, and retain every conclusion in deterministic repository-bounded history pages.**

## Performance

- **Duration:** 15m 05s
- **Started:** 2026-07-17T10:10:55Z
- **Completed:** 2026-07-17T10:26:00Z
- **Tasks:** 1/1
- **Files modified:** 7 implementation/test files plus this summary

## Accomplishments

- Replaced augmented repository mappings at the evidence boundary with an exact nine-field `ThesisCondition` DTO and separately persisted canonical instrument.
- Converted each aware due instant through `ZoneInfo("Asia/Shanghai")` before reader lookup and freshness evaluation, and bound the instrument into observed fingerprints.
- Added exact-instrument SQLite pages for versions and checks, a current-version/unreviewed actionable-pending page, and an all-version pending history page with explicit immutable state.
- Removed route-side post-materialization slicing; all four public ledgers now pass validated `offset` and `limit` through service to repository and return `items`, `offset`, `limit`, `total`, and `has_more`.
- Preserved confirmation authority and immutable review facts: automation still proposes only, while confirmed/rejected and superseded conclusions remain audit-readable.

## Task Commits

TDD gates were committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Add strict lifecycle and owned paging contracts | `7132ea4` | Resolver degraded to error and routes omitted repository page arguments as expected |
| GREEN | Implement strict timezone-correct paged Thesis lifecycle | `e4cea3f` | Exact plan tests and all focused Thesis regressions pass |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/theses/evidence.py` — condition-local due dates, strict separate instrument input, and instrument-bound observed fingerprint payload.
- `backend/app/theses/repository.py` — deterministic exact-instrument count/LIMIT/OFFSET queries for versions, checks, actionable pending, and all-version pending history.
- `backend/app/theses/service.py` — exact condition DTO construction and safe page projection without fetch-all list expansion.
- `backend/app/theses/api.py` — uniform bounded `offset`/`limit` public ledger contracts without route-side slicing.
- `backend/tests/theses/test_lifecycle.py` — production-shaped resolver, local-calendar, actionable-state, immutable-history, and bounded-SQL contracts.
- `backend/tests/theses/test_api.py` — owned route pagination and authorization-before-query contracts.
- `backend/tests/theses/test_scheduler.py` — migrated the scheduler resolver fake and assertions to the strict separate-instrument contract.

## Decisions Made

- Repository IDs, version IDs, copied lineage fields, and thesis IDs remain internal storage metadata and never cross the strict evidence-condition validator.
- Instrument scope remains server-owned: API subject authorization occurs before service access, and the repository repeats exact instrument filtering before count and page selection.
- History is the immutable pending-conclusion lifecycle ledger. It returns `actionable`, `superseded`, `confirmed`, or `rejected` state while the actionable endpoint remains deliberately narrower.
- Page size is bounded to 1–100 at both FastAPI and repository boundaries; deterministic ordering uses semantic time/version fields followed by stable IDs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Migrated the scheduler's resolver test double to the new strict boundary**
- **Found during:** Task 1 focused Thesis regression run.
- **Issue:** The pre-existing scheduler fake accepted only condition and due time, and one assertion depended on forbidden `version_id` metadata inside the resolver payload.
- **Fix:** Added the separate instrument parameter and changed the assertion to prove canonical instrument authority plus the exact nine-field condition allowlist.
- **Files modified:** `backend/tests/theses/test_scheduler.py`
- **Verification:** `cd backend && uv run pytest tests/theses -x` passed all 58 tests.
- **Committed in:** `e4cea3f`

---

**Total deviations:** 1 auto-fixed (1 direct contract migration).
**Impact on plan:** The migration was required for a clean strict-resolver cutover and introduced no new production surface or authority.

## Verification

```text
cd backend && uv run pytest tests/theses/test_lifecycle.py -k "strict_resolver_payload or condition_timezone or actionable_pending or paged_history" -x
Result: PASS — 4 passed, 16 deselected.

cd backend && uv run pytest tests/theses/test_api.py -k "versions_page or checks_page or actionable_pending_page or all_version_history_page or ownership_before_pagination" -x
Result: PASS — 5 passed.

cd backend && uv run pytest tests/theses -x
Result: PASS — 58 passed.
```

## Threat Mitigation Evidence

- **T-05-21-01:** The service passes only the strict nine-field condition mapping and supplies the persisted instrument separately; tests assert the exact key set.
- **T-05-21-02:** The Shanghai-midnight contract proves a UTC instant resolves on the next local date, while identical evidence for another instrument produces a different fingerprint.
- **T-05-21-03:** Repository SQL requires current lineage, pending status, no review, and exact instrument before count/LIMIT; old and reviewed facts appear only in history.
- **T-05-21-04:** Every public ledger validates a maximum limit of 100 and delegates ownership-filtered count, deterministic ordering, LIMIT, and OFFSET to repository SQL.
- No new endpoint, database, queue, external network access, trading action, browser authority, or schema migration was introduced.

## TDD Gate Compliance

- RED commit `7132ea4` captured observable failures at the strict resolver and route pagination boundaries before production implementation.
- GREEN commit `e4cea3f` implemented the required behavior and passed the exact plan command plus all 58 focused Thesis regressions.
- No refactor-only commit was necessary.

## Known Stubs

None. Empty evidence and collection values matched by the stub scan are explicit typed absence, immutable no-fact outcomes, or test assertions; none can substitute for the implemented production lifecycle.

## Issues Encountered

- The isolated checkout inherited a `pytest` launcher whose shebang referenced the primary checkout. The ignored local launcher was corrected to the isolated interpreter before GREEN verification; no dependency, lockfile, or tracked project metadata changed.
- The SQL-tracing test fixture initially initialized its statement list after repository migration had already opened a traced connection. Initialization was moved before the base constructor, after which the bounded-query proof passed.

## User Setup Required

None.

## Next Phase Readiness

- Plan 05-24 can update the Thesis client/panel to consume the uniform repository-owned page envelope without reintroducing browser authority or retained previous-subject data.
- Plan 05-32 can compose the production readers/scanner/readiness path on this strict resolver and actionable/history boundary.
- Shared `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched as required by the Wave 10 executor contract.

## Self-Check: PASSED

- All seven implementation/test artifacts and this summary exist in the isolated checkout.
- RED `7132ea4` and GREEN `e4cea3f` resolve as commits.
- The exact post-commit plan verification passed both lifecycle and API legs.
- No task commit deleted a tracked file; scoped implementation paths are clean.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` were not modified.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
