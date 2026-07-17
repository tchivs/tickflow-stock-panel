---
phase: 05-optional-enhancements
plan: "32"
subsystem: thesis-production-readiness
tags: [fastapi, sqlite, polars, pytest, governed-evidence, lease-isolation, scheduler]
requires:
  - phase: 05-optional-enhancements
    plan: "21"
    provides: strict Thesis resolver payload, timezone semantics, actionable pending lifecycle, and repository-owned pagination
provides:
  - bounded allowlisted production readers for governed market, financial, and immutable analysis evidence
  - per-lease poison isolation with durable expiry-based retry and continued bounded scanning
  - truthful Thesis availability gated on repository, readers, service, scheduler, scanner readiness, and registration
  - real production-host proof that governed evidence creates human-review-only pending conclusions without live actions
  - independently local Thesis failure preserving Shadow, Forecast, and completed-v1 behavior
affects: [THES-01, thesis-production, optional-module-readiness, phase-05-verification]
tech-stack:
  added: []
  patterns:
    - pushed-down exact-instrument governed lake reads with allowlisted field and bounded date windows
    - one-row immutable analysis report lookup before safe score projection
    - per-lease exception isolation that preserves durable retry ownership and continues later acquired work
    - capability readiness published only after production scheduler registration succeeds
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-32-SUMMARY.md
  modified:
    - backend/app/theses/evidence.py
    - backend/app/theses/scheduler.py
    - backend/app/optional_modules.py
    - backend/tests/theses/test_scheduler.py
    - backend/tests/test_phase5_optional_host.py
key-decisions:
  - "Market evidence uses the existing KlineRepository with exact instrument, allowlisted columns, and bounded dates; financial evidence uses a pushed-down lazy scan of the existing governed metrics Parquet; neither creates a second authority store."
  - "Analysis report_score is the deterministic mean of the two-to-four validated perspective scores from the latest immutable instrument report selected by one bounded operational query."
  - "A non-interruption lease failure remains durably owned until expiry and cannot abort later leases; InterruptedError retains the established crash/restart propagation contract."
  - "Thesis initialization requires the real host scheduler, and availability remains true only after scanner collaborator readiness and successful job registration."
patterns-established:
  - "Governed reader output: exactly source_id, source_revision, value, unit, and as_of; resolver adds the strict source/instrument/field envelope and instrument-bound fingerprint."
  - "Truthful optional readiness: dependency probe success is necessary but insufficient; complete construction and scanner registration must also succeed."
requirements-completed: [THES-01]
coverage:
  - id: D1
    description: "Production market, financial, and analysis readers return only bounded allowlisted governed facts, while absent exact-subject evidence remains insufficient rather than fabricated."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/theses/test_scheduler.py#test_production_governed_readers_return_allowlisted_bounded_facts_and_missing_evidence"
        status: pass
    human_judgment: false
  - id: D2
    description: "A poison condition cannot starve a later acquired lease, and its durable lease expires into a successful exact-due retry."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/theses/test_scheduler.py#test_poison_condition_does_not_starve_later_leases_and_retries_after_expiry"
        status: pass
      - kind: unit
        ref: "backend/tests/theses/test_scheduler.py#test_scanner_readiness_requires_complete_repository_and_service_collaborators"
        status: pass
    human_judgment: false
  - id: D3
    description: "The production host advertises Thesis only with complete readers and registered scanning, creates one governed actionable pending fact, invokes zero actions, and fails Thesis locally without affecting peers or v1."
    requirement: THES-01
    verification:
      - kind: integration
        ref: "backend/tests/test_phase5_optional_host.py#test_production_thesis_readiness_and_governed_pending_are_real"
        status: pass
      - kind: integration
        ref: "backend/tests/test_phase5_optional_host.py#test_real_lifespan_preserves_v1_for_module_combination"
        status: pass
      - kind: integration
        ref: "backend/tests/test_phase5_optional_host.py#test_optional_capability_failures_are_typed_local_and_independent"
        status: pass
    human_judgment: false
duration: 16m21s
completed: 2026-07-17
status: complete
---

# Phase 05 Plan 32: Governed Thesis Readers and Truthful Readiness Summary

**Production Thesis checks now consume bounded facts from the existing governed lake and immutable analysis ledger, isolate poison leases, and advertise availability only after the real scheduler has registered a ready scanner.**

## Performance

- **Duration:** 16m 21s
- **Started:** 2026-07-17T10:47:06Z
- **Completed:** 2026-07-17T11:03:27Z
- **Tasks:** 1/1
- **Files modified:** 5 implementation/test files plus this summary

## Accomplishments

- Added source-specific governed readers for exact-instrument market bars, financial metrics, and immutable analysis reports with fixed field allowlists, bounded date selection, finite numeric validation, safe source identities, and content-bound revisions.
- Refactored the due scanner so one ordinary resolver/service/completion failure retains an attributable expiry-retry lease while later acquired conditions continue within the same batch bound; process interruption semantics remain restart-safe.
- Replaced production Thesis placeholder callbacks with complete repository, readers, strict resolver, service, scanner, scheduler, and registration composition.
- Proved a real production-scheduler lifespan turns governed ROE evidence into one current actionable pending conclusion without auto-confirmation or any strategy, monitor, plan, position, ledger, broker, provider, or market action.
- Proved Thesis scanner failure clears only Thesis while Shadow, Forecast, and the completed-v1 host surfaces remain operational.

## Task Commits

TDD gates were committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Add governed reader, poison lease, readiness, and real-host contracts | `6e85ae8` | Failed on missing production reader classes as expected |
| GREEN | Wire governed Thesis operational readiness | `ade452d` | Exact plan checks, all 61 Thesis regressions, and nine optional readiness regressions pass |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/theses/evidence.py` — bounded allowlisted K-line, financial-metrics, and immutable-analysis adapters feeding the strict Plan 05-21 resolver contract.
- `backend/app/theses/scheduler.py` — explicit scanner collaborator readiness and per-lease poison isolation with durable expiry retry.
- `backend/app/optional_modules.py` — complete production Thesis composition plus scheduler/scanner readiness and registration gates.
- `backend/tests/theses/test_scheduler.py` — governed reader, missing evidence, poison continuation/retry, and scanner readiness contracts.
- `backend/tests/test_phase5_optional_host.py` — real production-scheduler governed pending scenario, no-action proof, and Thesis-local failure evidence.

## Decisions Made

- Market reads remain on `KlineRepository`; financial reads scan only the governed metrics Parquet with predicate/column pushdown; analysis reads use one exact-subject `LIMIT 1` query against the existing immutable operational ledger. No provider, network, database, queue, runtime, or second authority store was introduced.
- `report_score` is a server-derived arithmetic mean of the validated perspective scores in the latest immutable report. Browser content cannot supply the score, revision, subject, or evidence identity.
- Ordinary poison failures do not advance or fabricate a check. The persisted lease ownership, expiry, and `last_attempt_at` form the established retryable state, while later leases continue. `InterruptedError` still propagates so existing crash/restart tests retain their stronger process-interruption semantics.
- Fixture data is pre-seeded before tests enter the normal production scheduler lifespan; Thesis is never declared ready under the scheduler-free fixture branch.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Exercised Thesis readiness through the real scheduler lifespan**
- **Found during:** Task 1 GREEN real-host verification.
- **Issue:** The shared Phase 1 fixture lifespan intentionally sets `app.state.scheduler = None`, which correctly caused the new truthful Thesis readiness gate to fail but could not prove successful scanner registration.
- **Fix:** Pre-seeded the same governed fixture through the normal fixture ingestion path, then started the ordinary production lifespan and scheduler for every Thesis-enabled host case.
- **Files modified:** `backend/tests/test_phase5_optional_host.py`
- **Verification:** The named production Thesis scenario passed, and all eight module combinations plus the independent failure matrix passed.
- **Committed in:** `ade452d`

---

**Total deviations:** 1 auto-fixed (1 blocking test-environment correction).
**Impact on plan:** The correction strengthened rather than weakened readiness evidence; production availability is never inferred from a scheduler-free fixture override.

## Verification

```text
cd backend && uv run pytest tests/theses/test_scheduler.py -k "poison_condition or production_governed_reader or scanner_readiness" -x
Result: PASS — 3 passed, 13 deselected.

cd backend && uv run pytest tests/test_phase5_optional_host.py::test_production_thesis_readiness_and_governed_pending_are_real -x
Result: PASS — 1 passed, 6 pre-existing Polars warnings.

cd backend && uv run pytest tests/theses -x
Result: PASS — 61 passed.

cd backend && uv run pytest tests/test_phase5_optional_host.py::test_real_lifespan_preserves_v1_for_module_combination tests/test_phase5_optional_host.py::test_optional_capability_failures_are_typed_local_and_independent -x
Result: PASS — 9 passed, 33 pre-existing Polars warnings.
```

## Acceptance Criteria

- **PASS — governed actionable pending:** The real host read exact-instrument `roe=0.09` from the existing metrics Parquet, persisted one matched check, and exposed exactly one current unreviewed pending conclusion through the repository-owned page.
- **PASS — poison continuation:** A poisoned first lease did not prevent the second leased condition from completing; after expiry the original exact due identity retried and completed once.
- **PASS — local failure:** Injected Thesis scanner failure removed Thesis service/scanner state only; Shadow, Forecast, v1 routes, shared database/lake/container, and zero-action assertions remained intact.

## Threat Mitigation Evidence

- **T-05-32-01:** Every reader rejects undeclared fields and invalid bounds before reading. Market selects exact instrument and two columns, financial uses exact symbol/date predicates with `head(1)`, and analysis uses exact instrument/date plus `LIMIT 1` before projection.
- **T-05-32-02:** Each acquired lease owns its own try/transition boundary. Ordinary poison failures retain durable expiry-based retry state and cannot abort later work in the bounded batch.
- **T-05-32-03:** Thesis creation fails without governed repository, reader readiness, scheduler `add_job`, scanner collaborators, or successful registration; capability status is sanitized and module-local.
- **T-05-32-04:** The real host produced a pending proposal only, left confirmation human-owned, and all live-action spies remained at zero calls.
- No unplanned endpoint, auth path, schema migration, writable file surface, external service, or live-action collaborator was introduced.

## TDD Gate Compliance

- RED commit `6e85ae8` captured observable missing-reader/readiness behavior before production implementation.
- GREEN commit `ade452d` implemented the behavior and passed both exact plan commands plus focused regression gates.
- No refactor-only commit was necessary.

## Known Stubs

None. Empty evidence collections and optional `None` values found by the scan are typed absence outcomes or pre-existing optional collaborator defaults. The empty action-collaborator map is the explicit zero-live-action seam required by THES-01, not a substitute for production behavior.

## Issues Encountered

- The isolated checkout inherited a `pytest` launcher whose shebang referenced the primary checkout. The ignored local launcher was corrected to the isolated interpreter before RED/GREEN verification; no tracked dependency or environment metadata changed.
- Exact host checks emit existing Polars streaming/sortedness warnings from the shared fixture pipeline; all requested assertions pass and the warnings are outside this plan's Thesis scope.

## User Setup Required

None.

## Next Phase Readiness

- Phase 05 verification can now re-evaluate THES-01 against real governed readers, poison-safe scanning, current actionable pending pages, and truthful production availability.
- Shadow and Forecast remain independently optional; no peer module readiness logic or completed-v1 authority was coupled to Thesis.
- Shared `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched as required by the Wave 11 executor contract.

## Self-Check: PASSED

- All five implementation/test artifacts and this summary exist in the isolated checkout.
- RED `6e85ae8` and GREEN `ade452d` resolve as plan commits.
- The exact post-commit plan verification passed both scheduler and real-host legs.
- All 61 Thesis regressions and nine independent optional-readiness regressions passed.
- Stub and threat-surface scans found no goal-blocking placeholder or unplanned security surface.
- No task commit deleted a tracked file; scoped implementation paths are clean.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` were not modified.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
