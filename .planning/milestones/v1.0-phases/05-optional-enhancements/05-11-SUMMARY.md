---
phase: 05-optional-enhancements
plan: "11"
subsystem: shadow-evaluation-api
tags: [shadow, chronological-evaluation, immutable-events, fastapi, authorization, tdd]
requires:
  - phase: 05-optional-enhancements
    plan: "08"
    provides: immutable Shadow batches, evidence sets, replayable candidate rules, repository, importer, and distiller
  - phase: 05-optional-enhancements
    plan: "02"
    provides: executable Shadow evaluation/retention RED contracts and optional-host API RED contract
provides:
  - separately frozen chronological non-overlapping IS and OOS evaluation attempts with complete immutable terminal metrics
  - canonical both-pass candidate eligibility and replay-safe research-only retention with zero operational authority
  - authenticated object-authorized bounded Shadow workflow API and deny-by-default immutable history projections
affects: [05-14, 05-15, 05-16, SHDW-01]
tech-stack:
  added: []
  patterns:
    - append-only attempt reservation followed by an immutable terminal evaluation fact
    - canonical persisted candidate/evidence/evaluation reload before research-only retention
    - opaque child authorization through persisted evidence ownership before safe projection
key-files:
  created:
    - backend/app/shadow/evaluation.py
    - backend/app/shadow/service.py
    - backend/app/shadow/projections.py
    - backend/app/shadow/api.py
  modified:
    - backend/app/shadow/repository.py
key-decisions:
  - "Every retry reuses the exact frozen split identity but appends a new attempt and terminal evaluation; failed evidence is never rewritten or promoted."
  - "Retention is one idempotent Shadow research event and deliberately has no strategy, monitor, decision-plan, position, ledger, broker, provider, or market-action collaborator."
  - "Public history is manually allowlisted and artifact projections expose checksums and safe metadata but never managed relative paths, raw bytes, account aliases, runner manifests, exceptions, or client verdicts."
patterns-established:
  - "Shadow eligibility boundary: same candidate/evidence fingerprint, distinct independently frozen chronological IS/OOS identities, both terminal passed, complete metrics, and no overlap."
  - "Shadow API boundary: derive principal from middleware, resolve opaque children to persisted owner evidence, return non-enumerating 404, and paginate immutable newest-first history."
requirements-completed: [SHDW-01]
coverage:
  - id: D1
    description: "Candidate evaluation freezes and executes independent chronological non-overlapping IS and OOS inputs, records complete terminal metrics/artifacts, and makes retries append rather than mutate."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_evaluation_retention.py -x"
        status: pass
    human_judgment: false
  - id: D2
    description: "Candidate retention requires canonical passing IS and OOS evidence and appends one replay-safe research-only event with no completed-v1 action side effect."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "backend/tests/shadow/test_evaluation_retention.py#retention, replay, failure, and zero-action contracts"
        status: pass
    human_judgment: false
  - id: D3
    description: "Authenticated Shadow APIs expose bounded object-authorized workflow/history through safe projections and reject browser-supplied authority."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow -x (31 passed); uv run python -m app.shadow.api; uv run ruff check changed Shadow modules; uv run mypy new Shadow modules"
        status: pass
    human_judgment: false
metrics:
  duration: 15m 17s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 11: Shadow Chronological Evaluation And Safe API Summary

**Shadow candidates now earn research-only retention solely from separately frozen, chronological, non-overlapping IS/OOS terminal evidence, exposed through authenticated deny-by-default immutable APIs without acquiring operational authority.**

## Performance

- **Duration:** 15m 17s
- **Started:** 2026-07-16T06:17:41Z
- **Completed:** 2026-07-16T06:32:58Z
- **Tasks:** 2/2
- **Files created:** 4
- **Files modified:** 1 production file plus planning outputs

## Accomplishments

- Added strict parent-side validation for candidate/evidence identity, chronological disjoint windows, adjustment and cost policy, independently frozen governed fingerprints/artifacts, bounded collaborator output, complete precision/recall/coverage/trade/return/drawdown/cost/consistency metrics, safe terminal failures, and retry-as-new-attempt behavior.
- Extended the append-only Shadow repository with immutable attempt reservations, terminal evaluation facts, canonical reconstruction, transactional retention revalidation, and unique replay-safe research retention while preserving every failed or interrupted fact.
- Added a narrow Shadow workflow service, strict multipart/JSON request models, middleware-derived reviewer identity, persisted object authorization, bounded upload/history pagination, newest-first history, typed Shadow-only unavailability, non-enumerating 404s, immutable conflicts, and hand-written projections that exclude raw/internal data.

## Task Commits

The Wave 0 RED contracts were preserved and each production task was committed atomically at GREEN:

1. **Task 1 inherited RED: Explainable Shadow retention gates** — `c2ec721c9b9e0fb6cfbc9b13f5f18f689e7c0d37` (`test(05-02)`)
2. **Task 1 GREEN: Chronological Shadow evaluation and retention** — `7be02f542991eae25edec4e5f96f502af34964a9` (`feat(05-11)`)
3. **Task 2 inherited RED: Optional-host API authority contract** — `d7e3df2eb66e834f02546fb2408c58dd927709ff` (Wave 0 contract)
4. **Task 2 GREEN: Safe authorized Shadow workflow API** — `1f43b4ec791ac3b06b6fcf64337492faa8e8a99d` (`feat(05-11)`)

## Files Created/Modified

- `backend/app/shadow/evaluation.py` — Canonical candidate/evidence resolution, chronological split validation, independent freezing, bounded execution, terminal metric validation, and immutable retry orchestration.
- `backend/app/shadow/service.py` — Import/evidence/distillation/evaluation delegation plus exact both-pass research-retention authority.
- `backend/app/shadow/projections.py` — Bounded allowlisted preview, batch, evidence, candidate, evaluation, retention, artifact, metric, and pagination DTOs.
- `backend/app/shadow/api.py` — Strict authenticated multipart/workflow/history routes with opaque-object ownership resolution and typed local failures.
- `backend/app/shadow/repository.py` — Append-only evaluation attempt, terminal evidence, retention transaction, replay, and safe reconstruction primitives.

## Verification

```text
cd backend && uv run pytest tests/shadow/test_evaluation_retention.py -x
pytest: 9 passed

cd backend && uv run pytest tests/shadow -x
pytest: 31 passed

cd backend && uv run python -m app.shadow.api
router import: passed

cd backend && uv run ruff check app/shadow/evaluation.py app/shadow/service.py app/shadow/projections.py app/shadow/api.py app/shadow/repository.py
ruff: OK

cd backend && uv run mypy app/shadow/evaluation.py app/shadow/service.py app/shadow/projections.py app/shadow/api.py
mypy: OK
```

The complete Shadow suite passed once after the full API implementation. A later cleanup run exposed a pre-existing Plan 05-08 UUID-order flake in evidence-member ordering; it is documented in `deferred-items.md` and was not modified because this plan does not own evidence creation order. The exact 05-11 evaluation/retention command passed again after final changes.

## Threat Mitigation Evidence

- **T-05-11-01:** Evaluation rejects random, missing, full-sample, overlapping, divergent candidate/evidence, fingerprint, split, artifact, window, cost, and metric inputs before eligibility; retention reloads exact persisted identities and requires distinct independently frozen passing splits.
- **T-05-11-02:** `ShadowService` owns no strategy registration, monitor, decision-plan, position, manual-ledger, broker, provider, playbook, or market-action dependency; all zero-action spies pass.
- **T-05-11-03:** Request schemas forbid extra authority fields, reviewer identity comes only from middleware, opaque children resolve through persisted evidence ownership, and missing/foreign resources share one safe 404.
- **T-05-11-04:** Projections are explicit allowlists. Managed paths, raw artifacts/bytes/values, account aliases/secrets, runner manifests, commands, environment, traces, and exceptions do not enter public DTOs.
- **T-05-11-05:** Upload bytes, preview rows, diagnostics, request collections, nested projection depth, list pages, and returned page size are bounded; collaborator failures become local terminal facts with sanitized reasons.

## Decisions Made

- A pre-worker reservation is persisted as an immutable interrupted run boundary because the existing Phase 05 schema intentionally permits only terminal run statuses. The separately appended evaluation row owns the actual terminal outcome; a process interruption therefore leaves truthful immutable evidence rather than an orphaned mutable `running` row.
- Failed terminal evaluations retain their frozen identity and safe reason but no partial metrics. Retry consumes that canonical frozen identity and appends a new attempt/evaluation linked through `retry_of_evaluation_id`.
- Retention eligibility is status- and identity-based, not browser verdict- or full-sample score-based. Both complete metric sets must be attached to persisted `passed` IS/OOS facts for the same candidate and evidence fingerprint.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added append-only repository primitives required by the planned production service**
- **Found during:** Task 1 GREEN implementation
- **Issue:** Plan 05-08's repository persisted imports/evidence/candidates but exposed no evaluation attempt, terminal evaluation, retry reconstruction, or retention transaction methods, so the new production service would work only against the test fake.
- **Fix:** Added schema-compatible immutable run/evaluation/retention primitives and canonical transaction-time revalidation to `backend/app/shadow/repository.py` without changing migrations or existing facts.
- **Verification:** Exact evaluation/retention contracts pass; full Shadow suite passed 31/31; changed modules compile/lint/type-check at their declared boundaries.
- **Committed in:** `7be02f542991eae25edec4e5f96f502af34964a9` and narrow Task 2 type hardening in `1f43b4ec791ac3b06b6fcf64337492faa8e8a99d`

---

**Total deviations:** 1 auto-fixed (1 Rule 2 missing critical persistence boundary).
**Impact on plan:** The repository additions are the minimum production implementation of the plan's immutable-attempt and transactional-retention requirements; no schema, dependency, host, operational domain, or unrelated behavior changed.

## Issues Encountered

- The isolated worktree began on detached `HEAD`; it was attached to `worktree-agent-Execute05-11` before every commit.
- The fresh worktree environment lacked already-declared test executables. `uv sync --extra dev --extra shadow` synchronized only locked approved extras and changed no dependency declaration or lock file.
- A later full-suite cleanup run exposed a pre-existing nondeterministic evidence-member ordering assertion. The earlier complete 31-node run and final exact 9-node 05-11 run are green; the unrelated flake is recorded in `deferred-items.md`.

## TDD Gate Compliance

- Task 1 began from committed RED contract `c2ec721c9b9e0fb6cfbc9b13f5f18f689e7c0d37`; the declared test was observed failing at absent `app.shadow.evaluation`, then GREEN commit `7be02f542991eae25edec4e5f96f502af34964a9` made all 9 chronological evaluation/retention nodes pass.
- Task 2 consumed the committed optional-host authority contract `d7e3df2eb66e834f02546fb2408c58dd927709ff`; Plan 05-11 implemented the router/projection side while Plan 05-14 retains real-host registration ownership. The plan-declared Shadow suite passed 31/31 after GREEN commit content was present.

## Known Stubs

None. Empty collections are bounded accumulators or safe projections, and optional importer/distiller references are explicit independently unavailable deployment components that fail closed through the typed Shadow-only 503 path.

## User Setup Required

None. Shadow remains an independently enabled approved optional capability; no new dependency, environment variable, service, database, container, broker, or network access was added.

## Next Phase Readiness

- Plan 05-14 can lazily construct `ShadowRepository`, importer/distiller/freezer/runner, `ShadowEvaluationService`, and `ShadowService`, install `app.shadow.api.router`, and expose typed module status against the existing database and governed data roots.
- Plans 05-15/05-16 can consume safe newest-first batches, evidence, candidates, IS/OOS evaluations, retries, and retention history without client-derived authority.
- SHDW-01 now has a complete backend eligibility and research-retention boundary; no live action path exists.

## Self-Check: PASSED

Verified all four created Shadow modules, the modified repository, this summary, and both full task commit hashes exist. The worktree remains attached to `worktree-agent-Execute05-11`; focused behavioral, import, lint, and type checks completed with the documented evidence.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
