---
phase: 05-optional-enhancements
plan: "03"
subsystem: thesis-contract-testing
tags: [pytest, red-contract, immutable-versions, valuation, condition-ast, scheduler, human-review]
requires:
  - phase: 03-ai-analysis
    provides: evidence-linked pending review, server-principal confirmation, and event-derived official-state precedents
  - phase: 04-advanced-capabilities
    provides: immutable version lineage, SQLite fact triggers, guarded transitions, and parallel acquisition precedents
provides:
  - strict valuation, condition-AST, immutable version, and predecessor-lineage RED contracts
  - deterministic per-condition cadence, lease, retry, interruption, restart, and unique-due RED contracts
  - pending-only evidence evaluation and server-principal confirm/reject authority RED contracts
  - exact 49-node harness accepting only declared missing app.theses production boundaries
  - descriptor-less THES-01 edge retained as explicitly flagged and unverified until downstream green plans
  - strict RED classifier that rejects syntax, collection, fixture, assertion, timeout, crash, xfail/xpass, inventory drift, unexpected pass, and unrelated imports
  - zero-network and zero-strategy/monitor/plan/portfolio/broker side-effect contracts
affects: [05-06-phase5-foundation, 05-09-thesis-domain, 05-12-thesis-lifecycle, THES-01]
tech-stack:
  added: []
  patterns:
    - exact path-qualified pytest node inventory before expected-RED execution
    - typed missing-module and missing-symbol allowlist with structured JUnit failure inspection
    - temporary operational SQLite contracts for append-only lineage and restart-safe due identities
    - scheduler as bounded recovery cursor rather than evidence or official-state authority
key-files:
  created:
    - backend/tests/theses/test_contracts.py
    - backend/tests/theses/test_versions.py
    - backend/tests/theses/test_scheduler.py
    - backend/tests/theses/test_lifecycle.py
    - backend/tests/theses/verify_red_contract.py
  modified: []
key-decisions:
  - "Expected RED is valid only after successful exact collection and when every one of 49 nodes fails at one allowlisted app.theses ModuleNotFoundError or ImportError boundary."
  - "Canonical valuation requires method, currency, as-of date, ordered finite low/high range, explicit assumptions, and limitations; target-only and AI-link-only inputs are invalid."
  - "Condition evaluation uses a fixed source/field/operator AST with independent cadence/timezone; missing evidence remains insufficient_evidence and matched evidence creates pending state only."
  - "Only a session-derived server principal may confirm or reject after current-version, official-state, and governed-evidence revalidation; automation has no downstream action authority."
patterns-established:
  - "Thesis RED harness: exact collect-only inventory followed by JUnit inspection of typed allowlisted missing-production failures."
  - "Thesis recovery contract: immutable checks are unique by condition and due time while only bounded schedule lease/due cursors may advance."
requirements-completed: [THES-01]
coverage:
  - id: THES-01-CONTRACTS-VERSIONS-RED
    description: Complete valuation anchors, restricted condition ASTs, predecessor-linked revisions, deterministic current selection, and immutable history are fixed as executable failing-first contracts.
    requirement: THES-01
    verification:
      - kind: other
        ref: uv run python tests/theses/verify_red_contract.py --group contracts-versions
        status: pass
    human_judgment: false
  - id: THES-01-SCHEDULER-LIFECYCLE-RED
    description: Independent cadence, bounded leases, unique due checks, restart recovery, pending-only matches, and server-principal review authority are fixed as executable failing-first contracts.
    requirement: THES-01
    verification:
      - kind: other
        ref: uv run python tests/theses/verify_red_contract.py --group scheduler-lifecycle
        status: pass
      - kind: other
        ref: uv run python tests/theses/verify_red_contract.py --group all
        status: pass
    human_judgment: false
metrics:
  duration: 14m 15s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 03: Thesis RED Contract Summary

**Forty-nine exact pytest nodes now pin complete valuation anchors, immutable thesis version lineage, restart-safe per-condition checks, pending-only evidence conclusions, and server-authoritative human review before production implementation.**

## Performance

- **Duration:** 14m 15s
- **Started:** 2026-07-16T04:06:39Z
- **Completed:** 2026-07-16T04:20:54Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Defined 20 strict DTO/version nodes covering complete canonical anchors, bounded source-specific condition ASTs, browser-authority rejection, atomic creation, predecessor-linked revisions, stale-write rejection, deterministic current selection, historical readability, foreign-key integrity, and direct fact mutation denial.
- Defined 29 scheduler/lifecycle nodes covering daily/weekly/monthly/quarterly cursors, bounded ordering, duplicate and two-acquirer races, interruption before/after append, retry, expired-lease restart, safe errors, inactive-version exclusion, all four evidence results, pending uniqueness, current-state/evidence revalidation, confirm/reject conflicts, and immutable audit lineage.
- Added a strict exact-inventory harness that collects before execution, parses structured JUnit cases, accepts only allowlisted `app.theses` module/symbol absence, and rejects every unrelated failure category or unexpected behavioral change.
- Kept all contract evidence local and deterministic: temporary SQLite paths, fixed governed resolvers, no network, and explicit strategy/monitor/plan/portfolio/broker action spies that must remain untouched.

## Task Commits

Each task was committed atomically:

1. **Task 1: Specify strict thesis contracts and immutable version chains** — `b719fe4` (`test`)
2. **Task 2: Specify per-condition restart-safe checks and server-authoritative invalidation review** — `14490ad` (`test`)

## Files Created/Modified

- `backend/tests/theses/test_contracts.py` — strict Pydantic valuation, revision, review-body, condition AST, injection, and missing-evidence result contracts.
- `backend/tests/theses/test_versions.py` — atomic version creation, predecessor/copy lineage, current derivation, immutable history, foreign-key, and safe projection contracts over temporary operational SQLite.
- `backend/tests/theses/test_scheduler.py` — cadence, bounded acquisition, lease race, interruption, retry, restart, inactive-version, unique-due, and immutable-check contracts.
- `backend/tests/theses/test_lifecycle.py` — four evidence outcomes, one pending per matched check, principal-authorized confirm/reject, stale/processed conflicts, audit projection, and zero-action contracts.
- `backend/tests/theses/verify_red_contract.py` — strict collection, exact inventory, timeout, structured failure, classifier self-check, and declared production-boundary verifier.

## Verification

```text
cd backend && uv run python tests/theses/verify_red_contract.py --group contracts-versions
THESIS RED CONTRACT VALID: contracts-versions has 20 exact nodes; all failures are declared missing app.theses production boundaries

cd backend && uv run python tests/theses/verify_red_contract.py --group scheduler-lifecycle
THESIS RED CONTRACT VALID: scheduler-lifecycle has 29 exact nodes; all failures are declared missing app.theses production boundaries

cd backend && uv run python tests/theses/verify_red_contract.py --group all
THESIS RED CONTRACT VALID: all has 49 exact nodes; all failures are declared missing app.theses production boundaries
```

Only the plan's focused verification commands were run. No formatter, linter, ordinary green Thesis suite, browser suite, or project-wide suite was run.

## Decisions Made

- The harness requires two independent gates: exact successful collection, then a normal run where every structured test case fails at exactly one typed allowlisted `app.theses` import boundary.
- Missing root/submodules are accepted only within `app.theses`; once modules exist, only the declared schema, repository, scanner, and service symbols remain valid RED boundaries. Missing third-party modules or similarly worded assertions are fatal.
- Draft validation and persistence are separate contracts: strict Pydantic models reject malformed/authoritative fields before a repository transaction can create a thesis identity, version, anchor, condition, or schedule.
- Omitted fields in a revision may be copied only after reloading and validating the current predecessor; copied conditions receive new version-local identities while old anchors, conditions, schedules, checks, and reviews remain readable.
- Scheduler recovery is explicitly non-authoritative: `(condition_id, due_at)` identifies one immutable check, leases only coordinate work, and only a matched check can create one pending conclusion.
- Internal review events retain exact opaque principal/evidence lineage, while public history must omit principal internals, raw evidence, local paths, SQL, and tracebacks.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The isolated worktree initially had a fresh base `uv` environment without pytest, so the first strict command correctly failed as an infrastructure/collection failure. The repository's existing locked `dev` extra was provisioned, after which the exact plan commands passed. No dependency declaration or lockfile changed.

## TDD Gate Compliance

This Wave 0 plan intentionally ends at the strict RED contract. It contains the required `test(05-03)` RED commits and no `feat(05-03)` GREEN commit because Plans 05-09 and 05-12 explicitly own production implementation and ordinary zero-exit pytest gates.

## Known Stubs

None. The absent `app.theses` production package is the declared expected-RED boundary owned by Plans 05-09/12, not a shipped placeholder, mock fallback, or fabricated THES-01 descriptor.

## Threat Flags

None. This plan adds test contracts and a local verification harness only; it introduces no endpoint, authentication path, file-access surface, runtime schema, external request, or production trust boundary.

## User Setup Required

None.

## Next Phase Readiness

- Plan 05-06 can create the shared Thesis tables, immutable triggers, RESTRICT relations, unique due/check constraints, and guarded monotonic schedule cursor directly against the declared storage contracts.
- Plan 05-09 can implement strict schemas, repository lineage, governed evidence, and fixed condition dispatch against the 20 contract/version nodes.
- Plan 05-12 can implement the bounded scanner and human review service/API against the 29 scheduler/lifecycle nodes.
- The descriptor-less THES-01 edge remains explicitly flagged and unverified until downstream ordinary-green commands pass; this plan does not fabricate or auto-dismiss a `check_*` descriptor.

## Self-Check: PASSED

Verified all five declared Thesis test/harness artifacts and this summary exist, focused strict RED commands pass, task commits `b719fe4` and `14490ad` resolve as commits, and no changed artifact contains TODO/FIXME/placeholder delivery stubs.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
