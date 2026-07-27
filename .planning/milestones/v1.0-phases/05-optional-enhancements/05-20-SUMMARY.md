---
phase: 05-optional-enhancements
plan: "20"
subsystem: shadow-import-history
status: complete
tags: [fastapi, react, sqlite, sha256, authorization, pagination, playwright]
requires:
  - phase: 05-optional-enhancements
    plan: "18"
    provides: governed production Shadow import, distillation, and evaluation path
  - phase: 05-optional-enhancements
    plan: "19"
    provides: canonical append-only Shadow replay and retry identities
  - phase: 05-optional-enhancements
    plan: "30"
    provides: strict bounded Shadow assumption and projection contracts
provides:
  - principal-bound deterministic preview identities over exact bytes, canonical mapping, timezone, format, and importer versions
  - conflict-before-persistence confirmation for changed preview inputs
  - principal-scoped duplicate-content lineage
  - aggregate evidence membership COUNT gate before trade-row materialization
  - owned newest-first SQL pages for every public Shadow history collection
  - resource-prefix invalidation that refreshes the visible nonzero page
  - focused API, repository, production-host, and browser regression evidence
  - preservation of canonical candidate, evaluation-pair, retry, and retention replay contracts
affects: [05-24, 05-25, SHDW-01, shadow-production, shadow-audit]
tech-stack:
  added: []
  patterns:
    - deterministic server-issued transform identity recomputed from authoritative confirmation inputs
    - count plus bounded owned SQL page before projection or hydration
    - React mutation revision guard for stale asynchronous preview responses
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-20-SUMMARY.md
  modified:
    - backend/app/shadow/importer.py
    - backend/app/shadow/repository.py
    - backend/app/shadow/api.py
    - backend/app/shadow/projections.py
    - backend/tests/shadow/test_imports.py
    - backend/tests/shadow/test_evidence_sets.py
    - backend/tests/test_phase5_optional_host.py
    - frontend/src/lib/phase5Api.ts
    - frontend/src/pages/backtest/ShadowAccount.tsx
    - frontend/e2e/phase5-optional-enhancements.spec.ts
key-decisions:
  - "The preview identity is a bounded canonical SHA-256 over exact content digest, format/media pair, sorted canonical mapping, source timezone, importer and mapping versions, and the server-resolved principal; confirmation recomputes every field before any artifact or SQLite append."
  - "Public histories use dedicated owner-aware SQL page methods while existing internal canonical replay readers remain unchanged."
  - "Evidence membership is capped at 200,000 total included-plus-excluded trade facts and rejected by SQL COUNT before fetching any selected trade rows."
patterns-established:
  - "Preview revision guard: every file, mapping, or timezone change invalidates display and dialog state; only the latest mutation revision may install a confirmation identity."
  - "Owned ledger page: authorize in the SQL join, order by created_at DESC plus stable ID DESC, apply LIMIT/OFFSET, then hydrate and allowlist-project only that bounded page."
requirements-completed: [SHDW-01]
coverage:
  - id: D1
    description: "Shadow import confirmation is bound to the exact successful preview and changed bytes, mapping, timezone, or principal fail before persistence."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_imports.py -k 'preview_identity or same_content_lineage' -x (3 passed)"
        status: pass
      - kind: automated_ui
        ref: "cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep 'Shadow preview identity|Shadow non-first history page' (2 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Duplicate-content lineage and every public Shadow history are principal-scoped, deterministic, and SQL-bounded before materialization."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_evidence_sets.py -k 'aggregate_member_limit or repository_pagination' -x (3 passed)"
        status: pass
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_imports.py tests/shadow/test_evidence_sets.py -x (23 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The stricter import and bounded-history cutover preserves canonical Shadow candidate, evaluation-pair, retry, retention, and production-host contracts."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_distillation.py tests/shadow/test_evaluation_retention.py -x (24 passed)"
        status: pass
      - kind: integration
        ref: "cd backend && uv run pytest tests/test_phase5_optional_host.py::test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory -x (1 passed)"
        status: pass
    human_judgment: false
duration: 29m11s
completed: 2026-07-17
---

# Phase 05 Plan 20: Shadow Import Attribution and Bounded History Summary

**Shadow confirmation now proves the exact reviewed transformation, while duplicate lineage, evidence construction, and every public ledger page remain principal-owned and bounded before materialization.**

## Performance

- **Duration:** 29m 11s
- **Started:** 2026-07-17T10:46:53Z
- **Completed:** 2026-07-17T11:16:04Z
- **Tasks:** 2/2
- **Files modified:** 10

## Accomplishments

- Added one deterministic 64-character preview identity over exact content SHA-256, approved format/media pair, sorted canonical mapping, source timezone, importer/mapping versions, and server-resolved principal.
- Required the identity on the multipart confirmation endpoint and used constant-time comparison before raw-artifact creation or immutable batch append.
- Added a browser mutation-revision guard: file, mapping, and timezone changes clear the prior preview/dialog, ignore stale asynchronous responses, and re-preview only the current input before confirmation.
- Scoped `same_content_as` to the current principal in both detail and page queries, preventing cross-principal identifier disclosure.
- Added a configurable 200,000-member evidence ceiling enforced through SQL `COUNT(*)` before loading trade facts.
- Replaced API fetch-all/reverse/project/slice paths with principal-owned, newest-first `COUNT + LIMIT/OFFSET` repository pages for batches, evidence sets, candidates, evaluations, and retentions.
- Changed mutation invalidation from concrete page-zero keys to resource prefixes so active nonzero pages refresh after append.
- Kept the Plan 05-19 logical/complete replay digests, pair reservations, retry lineage, terminal facts, and retention decisions unchanged and green.

## Task Commits

TDD gates and focused coverage were committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: Importer/browser preview identity contracts | `c76dabf` | Importer rejected the principal input and the browser retained a stale mapping preview |
| RED | Task 1: Public API stale-preview contract | `e6dbdfb` | Preview projection omitted the required identity |
| GREEN | Task 1: Bind confirmation to exact preview | `8ca9248` | Importer, API, projection, typed client, and browser contracts passed |
| RED | Task 2: Ownership, aggregate limit, page, and active-page refresh contracts | `99b8f7b` | Repository lacked bounded page APIs and nonzero pages remained stale |
| GREEN | Task 2: Owned bounded histories | `d6b8dcc` | Principal, ceiling, public page, and browser refresh contracts passed |
| COVERAGE | Task 2: Exercise every actual owned SQL page | `175a5b9` | Candidate, evaluation, and retention SQL pages passed for owner and denied peer |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/shadow/importer.py` — canonical preview identity derivation and pre-persistence confirmation verification.
- `backend/app/shadow/api.py` — required multipart identity plus repository-owned public page routing.
- `backend/app/shadow/projections.py` — bounded preview identity allowlist projection.
- `backend/app/shadow/repository.py` — principal-scoped lineage, aggregate count gate, and five owned bounded page methods.
- `backend/tests/shadow/test_imports.py` — exact transform, stale confirmation, API conflict, and cross-principal lineage contracts.
- `backend/tests/shadow/test_evidence_sets.py` — aggregate ceiling and real/fake repository page contracts.
- `backend/tests/test_phase5_optional_host.py` — production tracer migrated through preview-before-confirm.
- `frontend/src/lib/phase5Api.ts` — required typed preview identity and multipart handoff.
- `frontend/src/pages/backtest/ShadowAccount.tsx` — current-preview revision guard, exact token dialog, and resource-prefix invalidation.
- `frontend/e2e/phase5-optional-enhancements.spec.ts` — bound-input token and active nonzero-page refresh scenarios.

## Decisions Made

- Used deterministic canonical SHA-256 instead of adding another deployment secret. Confirmation recomputes exact bytes and every authoritative transform field, while the server-resolved principal prevents cross-principal replay.
- Included the approved suffix and media type because parser selection changes the transformation even when content bytes are identical.
- Kept unbounded internal repository readers used by canonical replay tests intact, but removed every public API dependency on them; all public histories now enter through explicit owned page methods.
- Used resource-specific React Query prefixes rather than module-global invalidation, refreshing all pages of only the changed ledger.

## Deviations from Plan

None - plan executed exactly as written. The preview projection, typed client form, and production-host test caller were migrated as required by the declared end-to-end contract even though some were omitted from the frontmatter file list.

## Issues Encountered

- The isolated `.venv/bin/pytest` launcher initially pointed at the primary checkout. Reinstalling the already locked `pytest==9.0.3` package repaired the launcher without changing dependencies or project metadata.
- One multi-file Edit call injected the second patch section as literal importer text. The tool anomaly was reported to `xd://report_issue`; the exact injected lines were removed immediately before any verification or commit.
- The plan Task 2 command applies its final `-k` expression to the explicitly named lineage test as well, so the final plan-level selector separately ran `same_content_lineage` and recorded its passing result.

## Verification

```text
cd backend && uv run pytest tests/shadow/test_imports.py -k "preview_identity or same_content_lineage" -x
Result: PASS — 3 passed, 11 deselected.

cd backend && uv run pytest tests/shadow/test_evidence_sets.py -k "aggregate_member_limit or repository_pagination" -x
Result: PASS — 3 passed, 6 deselected.

cd backend && uv run pytest tests/shadow/test_imports.py::test_same_content_lineage_is_principal_scoped tests/shadow/test_evidence_sets.py -k "aggregate_member_limit or repository_pagination" -x
Result: PASS — 3 passed, 7 deselected (the command's `-k` filters the explicitly named lineage test).

cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "Shadow preview identity|Shadow non-first history page"
Result: PASS — 2 passed.

cd backend && uv run pytest tests/shadow/test_imports.py tests/shadow/test_evidence_sets.py -x
Result: PASS — 23 passed.

cd backend && uv run pytest tests/shadow/test_distillation.py tests/shadow/test_evaluation_retention.py -x
Result: PASS — 24 passed.

cd backend && uv run pytest tests/test_phase5_optional_host.py::test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory -x
Result: PASS — 1 passed, 3 pre-existing Polars warnings.

cd frontend && pnpm exec tsc --noEmit
Result: PASS — no diagnostics.

cd backend && uv run ruff check --ignore SIM105 app/shadow/importer.py app/shadow/api.py app/shadow/projections.py app/shadow/repository.py tests/shadow/test_imports.py tests/shadow/test_evidence_sets.py tests/test_phase5_optional_host.py
Result: PASS — no diagnostics; SIM105 is the pre-existing discarded-artifact cleanup finding outside this gap plan.
```

## Threat Mitigation Evidence

- **T-05-20-01:** Confirmation requires a 64-character server-issued identity, recomputes the exact canonical transform from uploaded bytes and server principal, and compares before artifact creation or SQLite work.
- **T-05-20-02:** Both single-batch and paged duplicate lookup include the batch principal; cross-principal same-content tests expose neither identifier nor count.
- **T-05-20-03:** Evidence creation validates attributable completed batches, executes aggregate `COUNT(*)`, rejects above the ceiling, and only then fetches member rows.
- **T-05-20-04:** Every public history route delegates to an owner-aware `COUNT + ORDER BY created_at DESC, id DESC + LIMIT/OFFSET` repository method before hydration/projection.
- No new endpoint, database, queue, external request, action collaborator, strategy authority, or market authority was introduced.

## TDD Gate Compliance

- Task 1 RED commits `c76dabf` and `e6dbdfb` failed at the missing principal/token and stale browser-preview boundaries before production changes; GREEN `8ca9248` passed the exact backend and browser selectors.
- Task 2 RED `99b8f7b` failed at the absent aggregate ceiling/page methods and concrete page-zero invalidation; GREEN `d6b8dcc` passed ownership, bounded repository, API, and active-page tests.
- Coverage commit `175a5b9` adds persisted owner/peer SQL-page evidence after GREEN without changing production behavior.

## Known Stubs

None. The scoped `placeholders` match is the executable SQL bind-marker variable, and React Query `placeholderData` is the established bounded-page continuity option; neither is a delivery stub. No mock, empty fallback, TODO, or no-op can satisfy the new production contracts.

## User Setup Required

None.

## Next Phase Readiness

- Later Shadow UI and audit plans can consume principal-owned bounded page metadata without reopening the Plan 05-19 replay identity chain.
- SHDW-01 now has named preview mismatch, cross-principal lineage, aggregate ceiling, five-ledger page, production-host, and active nonzero-page browser evidence.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched for orchestrator reconciliation.

## Self-Check: PASSED

- All ten implementation/test artifacts and this summary exist in the isolated checkout.
- RED/GREEN/coverage commits `c76dabf`, `e6dbdfb`, `8ca9248`, `99b8f7b`, `d6b8dcc`, and `175a5b9` resolve as commits.
- All three coverage deliverables validate as automatically covered with passing evidence.
- No task commit deleted a tracked file; all scoped implementation paths are clean.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` have no diff.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
