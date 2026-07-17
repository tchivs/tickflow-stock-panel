---
phase: 05-optional-enhancements
plan: "31"
subsystem: shadow-cleanup-retention-accessibility
status: complete
tags: [shadow, parquet, polars, cleanup, accessibility, playwright]
requires:
  - phase: 05-optional-enhancements
    plan: "20"
    provides: exact Shadow preview identity, immutable import lifecycle, principal-owned bounded histories
provides:
  - attributable cleanup-specific failures for uncommitted Shadow import namespaces
  - guaranteed invocation-owned managed-artifact temporary cleanup with Polars exception translation
  - exact trimmed Shadow retention rationale and keyboard-safe accessible confirmation
  - focused backend and browser regression evidence preserving preview and pagination contracts
affects: [SHDW-01, shadow-imports, managed-artifacts, shadow-retention]
tech-stack:
  added: []
  patterns:
    - cleanup in finally guarded by explicit invocation ownership
    - cleanup-specific exception identities for durable operational attribution
    - shared Modal primitive for focus trap, safe Escape, and focus restoration
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-31-SUMMARY.md
  modified:
    - backend/app/shadow/importer.py
    - backend/app/optional_artifacts.py
    - backend/tests/shadow/test_imports.py
    - backend/tests/test_phase5_foundation.py
    - frontend/src/pages/backtest/ShadowAccount.tsx
    - frontend/e2e/phase5-optional-enhancements.spec.ts
key-decisions:
  - "Cleanup runs only after the invocation proves it created the temporary namespace; pre-existing, committed, and shared namespaces are never cleanup candidates."
  - "Cleanup failure supersedes a generic persistence failure with an attributable cleanup-specific exception carrying only the opaque batch or artifact identity and retaining the library cause."
  - "Shadow retention submits the exact trimmed rationale after both disabled-state and submit-time validation, while mutation state remains inside the active shared Modal."
patterns-established:
  - "Owned finally cleanup: set ownership immediately after exclusive temporary creation, then remove only that exact root-contained namespace in finally."
  - "Accessible retention decision: first field focus, trapped Tab order, pending-safe Escape, automatic trigger focus restoration, and in-dialog aria-live status/error."
requirements-completed: [SHDW-01]
coverage:
  - id: D1
    description: "Failed Shadow persistence removes only its invocation-owned uncommitted namespace, reports cleanup failures by opaque batch identity, and preserves committed assets byte-for-byte."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_imports.py -k 'cleanup_failure_is_auditable or failed_import_temp_cleanup' -x (2 passed)"
        status: pass
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_imports.py -x (16 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Managed Parquet read/write failures translate from PolarsError with causes retained, temporary promotion cleanup is guaranteed and attributable, and final assets remain immutable."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/test_phase5_foundation.py -k 'polars_error_cleanup or managed_artifact_temp_finally' -x (4 passed)"
        status: pass
      - kind: integration
        ref: "cd backend && uv run pytest tests/test_phase5_foundation.py -x (14 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Shadow retention requires the exact trimmed server-valid rationale and keeps focus, pending state, and mutation errors inside a keyboard-safe labelled modal without action authority."
    requirement: SHDW-01
    verification:
      - kind: automated_ui
        ref: "playwright: Shadow retention dialog validates rationale and contains errors (1 passed)"
        status: pass
      - kind: automated_ui
        ref: "playwright: preview identity, non-first page refresh, explainability, retention dialog regressions (4 passed)"
        status: pass
    human_judgment: false
duration: 11m55s
completed: 2026-07-17
---

# Phase 05 Plan 31: Shadow Cleanup and Retention Accessibility Summary

**Shadow import and Parquet failures now clean only invocation-owned temporary evidence with attributable reconciliation errors, while retention approval submits an exact trimmed rationale through a focus-safe accessible modal.**

## Performance

- **Duration:** 11m 55s
- **Started:** 2026-07-17T11:24:32Z
- **Completed:** 2026-07-17T11:36:27Z
- **Tasks:** 1/1
- **Files modified:** 6

## Accomplishments

- Replaced swallowed Shadow artifact cleanup failures with `ShadowImportCleanupError`, carrying the opaque failed batch identity while retaining the cleanup cause.
- Moved uncommitted import cleanup into a guaranteed `finally` boundary without touching successfully committed batches or unrelated shared assets.
- Made managed-artifact temporary cleanup root-contained, ownership-gated, guaranteed in `finally`, and attributable through `ManagedArtifactCleanupError` instead of silently discarding removal failures.
- Translated the documented `polars.exceptions.PolarsError` base for both Parquet reads and writes into `ManagedArtifactError` with the original cause retained.
- Reused the established shared `Modal` primitive for labelled aria-modal semantics, initial rationale focus, focus trapping, safe Escape, and trigger-focus restoration.
- Enforced trimmed rationale parity before enablement and again at submit, sent exactly the trimmed value, and announced pending/mutation errors inside the active dialog.
- Preserved Plan 05-20 preview identity and non-first bounded-history refresh behavior in browser regression coverage.

## Task Commits

TDD gates and focused coverage were committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: Cleanup and retention contracts | `2e9e851` | Failed on absent cleanup attribution, raw Polars errors, and missing rationale focus |
| GREEN | Task 1: Auditable cleanup and accessible retention | `a4182b7` | Focused backend/browser contracts and TypeScript passed |
| COVERAGE | Task 1: Parquet read and cleanup attribution | `ee63b16` | Read translation, removal failure identity, and final-byte preservation passed |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/shadow/importer.py` — guaranteed cleanup of only failed uncommitted import namespaces and cleanup-specific batch attribution.
- `backend/app/optional_artifacts.py` — Polars read/write translation plus ownership-gated, non-swallowing temporary cleanup.
- `backend/tests/shadow/test_imports.py` — database and cleanup fault injection with committed/shared asset preservation.
- `backend/tests/test_phase5_foundation.py` — Polars read/write, metadata promotion, cleanup failure, and immutable final-asset coverage.
- `frontend/src/pages/backtest/ShadowAccount.tsx` — exact trimmed rationale and shared accessible modal retention flow.
- `frontend/e2e/phase5-optional-enhancements.spec.ts` — keyboard, focus, rationale payload, pending, and in-dialog mutation error acceptance.

## Decisions Made

- Used exception-based reconciliation attribution rather than adding a table or queue: the plan explicitly permits raising or recording, and the opaque batch/artifact identity is sufficient for the existing operational ownership seam without an architectural migration.
- Guarded managed cleanup with `temporary_created` immediately after exclusive creation. This prevents a collision or race from deleting a namespace the current invocation did not create.
- Kept successfully promoted/final namespaces outside temporary cleanup, so later failures cannot delete committed or shared immutable content.
- Reused `Modal` rather than maintaining a second bespoke focus implementation; pending state makes Escape, backdrop close, and cancel inert until the mutation is safe to dismiss.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The copied isolated `.venv/bin/pytest` launcher retained a primary-checkout shebang. Reinstalling the already locked `pytest==9.0.3` into the isolated environment repaired the launcher; no dependency metadata or tracked project file changed.
- Scoped Ruff reported pre-existing import-order/modernization and raw-regex findings in `optional_artifacts.py` and `test_phase5_foundation.py`. Re-running with only those established findings ignored returned `OK`; no unrelated formatting or modernization was applied.

## Verification

```text
cd backend && uv run pytest tests/shadow/test_imports.py -k "cleanup_failure_is_auditable or failed_import_temp_cleanup" -x
Result: PASS — 2 passed, 14 deselected.

cd backend && uv run pytest tests/test_phase5_foundation.py -k "polars_error_cleanup or managed_artifact_temp_finally" -x
Result: PASS — 4 passed, 10 deselected.

cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "Shadow retention dialog validates rationale and contains errors"
Result: PASS — 1 passed.

cd backend && uv run pytest tests/shadow/test_imports.py -x
Result: PASS — 16 passed.

cd backend && uv run pytest tests/test_phase5_foundation.py -x
Result: PASS — 14 passed.

cd frontend && pnpm exec playwright test e2e/phase5-optional-enhancements.spec.ts --project=desktop-chromium --grep "Shadow retention dialog validates rationale and contains errors|Shadow preview identity follows current bytes mapping and timezone|Shadow non-first history page refreshes after append|scenario 3: SHDW-01 explainability"
Result: PASS — 4 passed.

cd frontend && pnpm exec tsc --noEmit
Result: PASS — no diagnostics.

cd backend && uv run ruff check --ignore I001,UP035,UP017,RUF043 app/shadow/importer.py app/optional_artifacts.py tests/shadow/test_imports.py tests/test_phase5_foundation.py
Result: PASS — OK.
```

## Threat Mitigation Evidence

- **T-05-31-01:** database, Parquet writer, metadata promotion, Parquet reader, and cleanup removal fault tests prove owned temporary payloads are removed or surfaced with an attributable reconciliation identity.
- **T-05-31-02:** every fault test freezes a committed/shared asset first and verifies its content remains byte-identical; cleanup paths accept only the current invocation's exact server-generated namespace.
- **T-05-31-03:** browser acceptance proves trimmed rationale parity, disabled short rationale, submit-time revalidation, focus trap, safe Escape, trigger focus restoration, pending announcement, and in-dialog mutation error visibility.
- No endpoint, schema, authorization rule, retention authority, strategy activation, monitor, plan, position, ledger, broker, provider, or market-action collaborator was added.

## TDD Gate Compliance

- RED `2e9e851` failed before production changes on the missing cleanup-specific exception, untranslated Polars compute failure, and retention textarea focus.
- GREEN `a4182b7` followed RED and passed the exact plan verification.
- Coverage `ee63b16` extended passing evidence to Parquet read failures and cleanup-removal attribution without changing production behavior.

## Known Stubs

None. Empty lists and strings matched by the mechanical scan are bounded parser/test accumulators or explicit validation states; no mock, empty fallback, placeholder, TODO, FIXME, or no-op can satisfy the delivered contracts.

## User Setup Required

None.

## Next Phase Readiness

- SHDW-01 now has named cleanup, immutable-asset preservation, exact-rationale, keyboard, focus, pending, and in-dialog error evidence.
- Plan 05-20 exact preview identity and bounded-history behavior remains green.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched for orchestrator reconciliation.

## Self-Check: PASSED

- Summary and all six scoped implementation/test artifacts exist in the isolated checkout.
- RED/GREEN/coverage commits `2e9e851`, `a4182b7`, and `ee63b16` resolve as commits.
- All three coverage deliverables carry passing automated evidence.
- No task commit deleted a tracked file; every scoped implementation path is clean.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` have no diff.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
