---
phase: 05-optional-enhancements
plan: "19"
subsystem: shadow-audit
status: complete
tags: [sqlite, canonical-json, idempotency, restart-recovery, concurrency, shadow]
requires:
  - phase: 05-optional-enhancements
    plan: "18"
    provides: governed production Shadow distillation and chronological evaluation path
  - phase: 05-optional-enhancements
    plan: "30"
    provides: strict bounded canonical Shadow assumption contract
provides:
  - content-complete canonical candidate and attributable retention replay identities
  - one append-only IS/OOS pair identity with both split attempts reserved before execution
  - directly queryable interrupted attempts and linked immutable retry recovery
  - concurrency-safe canonical pair reuse without duplicate split terminals
  - forward migration of legacy attempt manifests into indexed attempt identities
  - conflict-on-divergence semantics for candidate, pair, terminal, and retention replay
  - preservation of the completed-v1 no-action boundary
  - focused restart, interruption, and parallel-request evidence
  - no alternate database, evaluator authority, assumption schema, or identity system
affects: [05-20, 05-24, 05-25, SHDW-01, shadow-production, shadow-retention]
tech-stack:
  added: []
  patterns:
    - append-only logical-key digest plus complete-payload digest
    - durable pair reservation before bounded split execution
    - direct indexed attempt hydration instead of manifest-table scans
    - immutable retry lineage linked to one canonical evaluation pair
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-19-SUMMARY.md
  modified:
    - backend/app/operational/migrations.py
    - backend/app/shadow/repository.py
    - backend/app/shadow/evaluation.py
    - backend/tests/shadow/test_distillation.py
    - backend/tests/shadow/test_evaluation_retention.py
key-decisions:
  - "Candidate and retention replay metadata lives in new append-only identity records, so existing immutable facts are never rewritten while exact historical payloads remain readable."
  - "Evaluation lookup uses a logical pair key before freezing; the complete pair digest additionally binds both server-frozen split identities and conflicts if those immutable inputs diverge."
  - "Both initial attempts reserve atomically before runner work, while restart creates a linked retry only for the latest missing or retryable split and never rewrites an earlier terminal."
  - "The production service reuses the existing freezer, bounded runner, strict assumptions, operational SQLite database, and no-action collaborator boundary."
patterns-established:
  - "Two-level replay identity: stable logical-operation digest selects the canonical fact, and a complete canonical payload digest proves whether reuse is exact or conflicting."
  - "Paired restart recovery: reserve pair and both attempts first, hydrate attempts directly, reuse passed terminals, and append linked retries only for retryable work."
requirements-completed: [SHDW-01]
coverage:
  - id: D1
    description: "Material candidate or attributable retention divergence conflicts, while byte-equivalent logical replay returns the canonical immutable fact."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_distillation.py::test_candidate_replay_digest_covers_all_identity_defining_content tests/shadow/test_evaluation_retention.py::test_retention_replay_requires_exact_principal_and_rationale -x (2 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "One durable IS/OOS pair reserves both directly queryable attempts before execution and resumes only interrupted or retryable work across restart and parallel requests."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_evaluation_retention.py -k 'paired_operation or interrupted_attempt or parallel_pair' -x (3 passed)"
        status: pass
      - kind: integration
        ref: "cd backend && uv run pytest tests/test_phase5_optional_host.py::test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory -x (1 passed)"
        status: pass
    human_judgment: false
duration: 29m16s
completed: 2026-07-17
---

# Phase 05 Plan 19: Restart-Safe Shadow Replay Identities Summary

**Shadow candidate, paired evaluation, and retention retries now resolve through one content-complete append-only identity chain that survives interruption without substituting divergent facts or granting action authority.**

## Performance

- **Duration:** 29m 16s
- **Started:** 2026-07-17T10:10:53Z
- **Completed:** 2026-07-17T10:40:09Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Bound candidate replay to every material request and exported-rule field, including strict assumptions, features, parameters, training window, seed, negative sampling, rules, rule fingerprint, metrics, and replay evidence.
- Bound retention replay to candidate, both evaluation IDs, reviewer principal, and trimmed rationale; divergent attributable decisions now produce conflict instead of silently reusing another review fact.
- Added one append-only paired evaluation operation whose complete digest includes candidate/evidence attribution, both windows, policies, and both server-frozen split identities.
- Reserved both split attempt identities in one SQLite transaction before the first bounded runner call, made interrupted attempts directly queryable, and recovered only the latest missing/retryable split through immutable retry lineage.
- Preserved the Plan 05-18 production freezer/runner path, Plan 05-30 bounded assumptions, the sole operational database, and zero completed-v1 action collaborators.

## Task Commits

TDD gates were committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: Bind candidate and retention replay to complete canonical payloads | `5d91e7f` | Candidate feature divergence silently replayed the prior fact before implementation |
| GREEN | Task 1: Bind candidate and retention replay to complete canonical payloads | `32d38f1` | Exact replay is canonical; material candidate and reviewer-decision divergence conflicts |
| RED | Task 2: Reserve, discover, and recover the IS/OOS pair | `f9acd3d` | First runner invocation observed no reserved peer split under the independent-loop behavior |
| GREEN | Task 2: Reserve, discover, and recover the IS/OOS pair | `72e0a0d` | Pair, interruption, restart, and parallel winner contracts pass |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/operational/migrations.py` — forward-only immutable candidate/retention digest records, evaluation pair identities, directly indexed attempts, and legacy attempt normalization.
- `backend/app/shadow/repository.py` — complete canonical digests, conflict-safe replay, atomic pair reservation, direct attempt hydration, immutable retry lineage, and same-pair retention eligibility.
- `backend/app/shadow/evaluation.py` — pair-first orchestration, completed-split reuse, missing/retryable split recovery, and parallel canonical winner reuse.
- `backend/tests/shadow/test_distillation.py` — named complete candidate replay-digest contract.
- `backend/tests/shadow/test_evaluation_retention.py` — attributable retention replay, before-run pair reservation, interruption/restart, and cross-service parallel pair contracts.

## Decisions Made

- Kept logical operation lookup distinct from complete immutable payload proof: the logical key finds a replay candidate before expensive freezing, while the full digest prevents changed frozen inputs or outputs from aliasing that operation.
- Used append-only identity tables rather than altering or updating Phase 05 facts. Legacy run manifests are normalized forward into the direct attempt index without mutating their source rows.
- Kept each terminal immutable. Duplicate completion is accepted only when its canonical terminal payload matches; a different result conflicts, and a retry receives a new linked attempt ID.
- Serialized pair execution across service instances in one process and combined that with SQLite immediate transactions and uniqueness constraints, while leaving all market/action collaborators absent.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The inherited isolated `.venv/bin/pytest` launcher referenced the primary checkout. Re-syncing the already locked `dev` and `shadow` extras rewrote the launcher to this isolated checkout; no dependency version or project metadata changed.
- The edit tool twice parsed a second operation header as literal file content in a multi-operation patch. Both anomalies were reported through `xd://report_issue`, immediately re-read, and corrected before verification or commit.

## Verification

```text
cd backend && uv run pytest tests/shadow/test_distillation.py::test_candidate_replay_digest_covers_all_identity_defining_content tests/shadow/test_evaluation_retention.py::test_retention_replay_requires_exact_principal_and_rationale -x
Result: PASS — 2 passed.

cd backend && uv run pytest tests/shadow/test_evaluation_retention.py -k "paired_operation or interrupted_attempt or parallel_pair" -x
Result: PASS — 3 passed, 10 deselected.

cd backend && uv run pytest tests/shadow/test_distillation.py -k "replay_digest" -x && uv run pytest tests/shadow/test_evaluation_retention.py -k "retention_replay or paired_operation or interrupted_attempt or parallel_pair" -x
Result: PASS — 1 passed/10 deselected, then 4 passed/9 deselected.

cd backend && uv run pytest tests/shadow/test_evaluation_retention.py -x
Result: PASS — 13 passed.

cd backend && uv run pytest tests/test_phase5_optional_host.py::test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory -x
Result: PASS — 1 passed, 3 pre-existing Polars warnings.

cd backend && uv run ruff check app/operational/migrations.py app/shadow/repository.py app/shadow/evaluation.py tests/shadow/test_evaluation_retention.py
Result: PASS — no diagnostics.
```

## Threat Mitigation Evidence

- **T-05-19-01:** Candidate logical reuse compares a complete canonical request/output digest; changed features, parameters, assumptions, window, sampling, rules, fingerprint, or metrics conflicts.
- **T-05-19-02:** Retention canonical identity includes the normalized reviewer principal and trimmed rationale in addition to candidate and both evaluation IDs.
- **T-05-19-03:** One immediate SQLite transaction appends the pair and both split attempt identities before runner work; replay reuses passed terminals and appends only linked retryable work.
- **T-05-19-04:** `get_evaluation`, `list_evaluations`, completion, retry, and pair hydration query indexed normalized attempt rows directly; no whole-manifest-table scan remains.
- No new endpoint, database, queue, external network access, evaluator authority, assumption schema, browser verdict, strategy activation, monitor, plan, position, ledger, broker, provider, or market-action collaborator was introduced.

## TDD Gate Compliance

- Task 1 RED `5d91e7f` failed because candidate replay ignored changed features; GREEN `32d38f1` made the complete candidate and retention replay contract pass.
- Task 2 RED `f9acd3d` failed because the first runner invocation could not discover both split reservations; GREEN `72e0a0d` made all pair/interruption/parallel contracts pass.
- No refactor-only commit was necessary after focused formatting, Ruff, domain regression, and production-host verification.

## Known Stubs

None. The only scoped `placeholder` text match is the existing SQL bind-variable name `placeholders`; it is executable query construction, not a delivery stub. No mock, empty fallback, placeholder output, or no-op can satisfy the new production contracts.

## User Setup Required

None.

## Next Phase Readiness

- Later Shadow pagination, principal-scoping, and UI invalidation gap plans can reuse these canonical operation identities without reopening the strict assumption or evaluator contracts.
- SHDW-01 now has named passing canonical replay, interruption, parallel-pair, and production-host evidence for this gap scope.

## Self-Check: PASSED

- All five scoped implementation/test artifacts and this summary exist in the isolated checkout.
- RED `5d91e7f` / `f9acd3d` and GREEN `32d38f1` / `72e0a0d` resolve as commits.
- Final paired-operation selector passed 3 tests and targeted Ruff reported no diagnostics.
- Neither task commit deleted a tracked file.
- `.planning/STATE.md` and `.planning/ROADMAP.md` remain untouched.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
