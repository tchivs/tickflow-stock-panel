---
phase: 05-optional-enhancements
plan: "22"
subsystem: forecast-production-integrity
tags: [forecast, kronos, governed-input, calendar, immutable-commit, fastapi, sqlite]
requires:
  - phase: 05-optional-enhancements
    plan: "21"
    provides: strict governed lifecycle and object-authority conventions
  - phase: 05-optional-enhancements
    plan: "32"
    provides: truthful optional-host readiness and scanner registration conventions
provides:
  - complete server-owned Forecast request, freeze, job, runner, recovery, actuals, calibration, path-reader, and scanner composition
  - canonical selected-frame and promoted-artifact input identity
  - exact governed open-session sequence anchoring
  - fail-closed immutable provenance, shape, and output-artifact commit boundary
affects: [FORE-01, forecast-production, 05-23, 05-27, phase-05-verification]
tech-stack:
  added: []
  patterns:
    - parent-owned Forecast run context revalidated before spawn and rebound before commit
    - non-circular canonical-frame then artifact-checksum input fingerprinting
    - exact sequence-based governed calendar horizons
    - configured-root regular-file checksum verification at the sole immutable commit point
key-files:
  created:
    - backend/app/forecast/service.py
    - .planning/phases/05-optional-enhancements/05-22-SUMMARY.md
  modified:
    - backend/app/forecast/input.py
    - backend/app/forecast/calendar.py
    - backend/app/forecast/repository.py
    - backend/app/forecast/runner.py
    - backend/app/optional_modules.py
    - backend/tests/forecast/test_input.py
    - backend/tests/forecast/test_runner.py
    - backend/tests/test_phase5_optional_host.py
key-decisions:
  - "Forecast availability requires every local catalog, calendar, input, runner, actuals, recovery, path-reader, scanner, and scheduler collaborator; missing supply or runtime components fail only Forecast."
  - "Input identity is computed after canonical frame-byte hashing and immutable artifact promotion, so the final fingerprint includes both independent digests without a circular scope dependency."
  - "The repository accepts a forecast only against a parent-bound server identity and a regular non-symlink artifact verified beneath its configured output root."
  - "The rejected 05-28/blocked 05-26 supply state remains authoritative; fixture checkpoint identities exist only in tests and no production catalog, dependency, lock, or provisioner identity was invented."
patterns-established:
  - "Forecast execution: authorize and freeze in the parent, revalidate catalog/input immediately before spawn, then compare the child descriptor against the parent-bound immutable record at commit."
  - "Calendar execution: resolve exactly one open CNA-YYYYMMDD anchor and select later open rows only by sequence under the same revision."
requirements-completed: [FORE-01]
coverage:
  - id: D1
    description: "An authenticated production Forecast request reaches one completed immutable record through the complete approved local composition while invoking no live actions."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/test_phase5_optional_host.py#test_production_forecast_factory_completes_approved_request_and_stays_independent"
        status: pass
      - kind: integration
        ref: "backend/tests/forecast/test_runner.py#test_production_service_revalidation_reloads_catalog_and_frozen_input_before_run"
        status: pass
    human_judgment: false
  - id: D2
    description: "Canonical selected frame bytes and the promoted immutable artifact checksum jointly determine the Forecast input fingerprint, with all-or-none finite amount coverage."
    requirement: FORE-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast/test_input.py -k 'frame_bytes or artifact_checksum or amount_coverage'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Forecast horizons require one exact open governed as-of row and advance only by sequence within its frozen calendar revision."
    requirement: FORE-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast/test_input.py#test_calendar_exact_as_of_sequence_rejects_missing_or_closed_anchor"
        status: pass
    human_judgment: false
  - id: D4
    description: "The immutable commit rejects absent or divergent provenance, non-finite sampling, inconsistent shapes, unsafe paths, symlinks, and checksum divergence."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_runner.py -k 'commit_rejects_missing_or_divergent_provenance or output_path_containment'"
        status: pass
    human_judgment: false
duration: 37m52s
completed: 2026-07-17
status: complete
---

# Phase 05 Plan 22: Governed Forecast Production Workflow Summary

**Authenticated Forecast requests now freeze exact governed bytes, revalidate approved local identities before bounded execution, and cross one fail-closed immutable commit bound to the selected calendar, checkpoint, sampling shape, and verified output artifact.**

## Performance

- **Duration:** 37m 52s
- **Started:** 2026-07-17T11:26:05Z
- **Completed:** 2026-07-17T12:03:57Z
- **Tasks:** 2/2
- **Files modified:** 9 implementation/test files plus this summary

## Accomplishments

- Added `ForecastService` as the server-owned request-to-record coordinator: approved catalog lookup, governed as-of resolution, exact input freeze, content-bound idempotent job allocation, parent-context binding, pre-spawn reauthorization/catalog/input verification, bounded runner invocation, restart revalidation, and canonical result reload.
- Replaced the repository-only Forecast placeholder and inert actuals adapter with complete optional-host composition over the shared operational database, governed lake, configured artifact roots, bounded runner, governed actual reader, maturity scanner, path reader, recovery, and scheduler registration.
- Bound each input fingerprint to deterministic schema/order/value bytes and the promoted Parquet payload checksum in a documented non-circular order; partially-null amount is omitted while complete finite amount remains an explicit feature.
- Anchored each 5/20/60 horizon to exactly one open `CNA-YYYYMMDD` as-of row and selected later open sessions by governed sequence rather than lexical identity.
- Replaced every provenance/sampling default at the immutable commit with strict validation against the persisted job and parent-bound catalog/input identity; output must be a regular non-symlink file beneath the configured root with exact size, SHA-256, horizon, sample, and feature shape.
- Preserved local-only optional and no-action boundaries. Production defaults remain unavailable without complete approved components, while the test-only local fixture proves composition without adding or approving any Kronos/PyTorch supply identity.

## Task Commits

TDD gates and regression migration were committed atomically with hooks enabled:

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1 production composition contracts | `49ee5a1` | Failed on missing `app.forecast.service` and queued placeholder behavior |
| GREEN | Task 1 governed Forecast production workflow | `3c6c773` | Production request, revalidation, local failure isolation, and eight module combinations passed |
| RED | Task 2 input/calendar/commit identity contracts | `920f547` | Failed on partial amount admission and missing artifact-root commit validation |
| GREEN | Task 2 byte, sequence, provenance, shape, and path binding | `a01c3aa` | Exact plan selectors plus full input/runner regressions passed |
| Regression | Approved-host fixture contract migration | `18ac59c` | Full optional-host regression passed in truthful production-scheduler mode |

**Plan metadata:** committed with this summary after self-check.

## Files Created/Modified

- `backend/app/forecast/service.py` — production request coordinator, parent-owned run context, governed K-line/actual adapters, contextual worker boundary, and output checksum verifier.
- `backend/app/forecast/input.py` — all-or-none finite amount selection and non-circular canonical-frame/artifact fingerprinting.
- `backend/app/forecast/calendar.py` — exact open as-of validation and sequence-based future-session selection.
- `backend/app/forecast/repository.py` — configured artifact root, parent identity binding, strict immutable record validation, and regular-file containment/checksum enforcement.
- `backend/app/forecast/runner.py` — strict complete deterministic worker manifest used by hostile-boundary tests.
- `backend/app/optional_modules.py` — complete Forecast factory, output-root binding, actuals, recovery, path reader, scanner, and scheduler readiness.
- `backend/tests/forecast/test_input.py` — canonical bytes/checksum, amount coverage, and exact calendar-anchor contracts.
- `backend/tests/forecast/test_runner.py` — production revalidation, strict provenance/shape, and output containment contracts.
- `backend/tests/test_phase5_optional_host.py` — authenticated production completion, local fixture composition, no-action evidence, and truthful production-mode regression handling.

## Decisions Made

- Local deployment components are explicit and complete-or-unavailable. A dependency-level probe cannot make Forecast available when catalog, calendar, worker, actuals, runner limits, scanner, or scheduler registration is absent.
- Parent-owned immutable identity is rebound on every request/recovery revalidation. The child can provide an output descriptor and bounded warning codes, but cannot author checkpoint, input, calendar, sampling, or shape authority.
- The managed input artifact is promoted before the final fingerprint is computed. Its payload checksum does not depend on metadata scope, avoiding circularity while preserving both canonical semantic bytes and physical artifact bytes.
- Output path validation is filesystem-backed, not lexical: normalized relative identity, configured-root resolution, regular-file type, no symlink, exact byte size, and full SHA-256 are all required before SQLite commit.
- Plan 05-28 remains `rejected` and Plan 05-26 remains blocked. No catalog entry, config digest, Torch build/index/hash, dependency, lock, provisioner, download, or remote-latest behavior was introduced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Repaired the ignored isolated pytest launcher**
- **Found during:** Task 1 GREEN verification.
- **Issue:** The isolated checkout's ignored `.venv/bin/pytest` shebang pointed to the primary checkout, so `uv run pytest` could not import the newly created `app.forecast.service`.
- **Fix:** Repointed only the ignored local launcher to the isolated interpreter, then reran the literal plan commands successfully.
- **Files modified:** `backend/.venv/bin/pytest` (ignored environment file; not committed)
- **Verification:** The exact four-part plan command passed under `uv run pytest`.
- **Committed in:** Not applicable — ignored local execution environment only.

**2. [Rule 1 - Bug] Migrated the shared host no-action fixture to the approved local catalog identity**
- **Found during:** Final `test_phase5_optional_host.py` regression.
- **Issue:** The existing no-action request used `approved-mini`, which is not a valid approved Forecast catalog ID under the production `kronos-*` request boundary.
- **Fix:** Switched the fixture request to the locally approved test-only `kronos-mini` identity and retained zero-action assertions.
- **Files modified:** `backend/tests/test_phase5_optional_host.py`
- **Verification:** Full optional-host file passed all 15 tests.
- **Committed in:** `18ac59c`

**3. [Rule 1 - Bug] Preserved fixture-only terminal routes as safe 404 under the real scheduler lifespan**
- **Found during:** Final `test_phase5_optional_host.py` regression.
- **Issue:** Truthful Forecast readiness now requires the real scheduler lifespan, which deliberately disables `PHASE1_FIXTURE_MODE`; the testing-only terminal route therefore correctly returns safe 404 while the old assertion required 200/201.
- **Fix:** Accepted and safety-projected the production-mode 404 branch while retaining the existing detailed terminal assertions when fixture mode is active.
- **Files modified:** `backend/tests/test_phase5_optional_host.py`
- **Verification:** Full optional-host file passed all 15 tests and all action spies remained at zero.
- **Committed in:** `18ac59c`

---

**Total deviations:** 3 auto-fixed (2 direct regression bugs, 1 blocking isolated-environment repair).
**Impact on plan:** All changes were required to verify the planned production contract without weakening availability, supply-chain, identity, or no-action boundaries.

## Verification

```text
cd backend && uv run pytest tests/test_phase5_optional_host.py::test_production_forecast_factory_completes_approved_request_and_stays_independent -x
Result: PASS — 1 passed, 3 pre-existing Polars warnings.

cd backend && uv run pytest tests/forecast/test_runner.py -k "production_service_revalidation" -x
Result: PASS — 1 passed, 28 deselected.

cd backend && uv run pytest tests/forecast/test_input.py -k "frame_bytes or artifact_checksum or exact_as_of_sequence or amount_coverage" -x
Result: PASS — 3 passed, 15 deselected.

cd backend && uv run pytest tests/forecast/test_runner.py -k "commit_rejects_missing_or_divergent_provenance or output_path_containment" -x
Result: PASS — 2 passed, 27 deselected.

cd backend && uv run pytest tests/forecast/test_input.py -x
Result: PASS — 18 passed.

cd backend && uv run pytest tests/forecast/test_runner.py -x
Result: PASS — 29 passed.

cd backend && uv run pytest tests/test_phase5_optional_host.py -x
Result: PASS — 15 passed, 53 pre-existing Polars warnings.
```

## Acceptance Criteria

- **PASS — production request to immutable record:** An authenticated `kronos-mini` request completed synchronously through catalog, exact governed freeze, persisted job, three pre-spawn checks, spawned bounded worker, verified artifact, and one immutable record with exact model/tokenizer/input identities.
- **PASS — truthful independent readiness:** Missing initialization, recovery, or scanner readiness remains a sanitized Forecast-only unavailable status; peer optional modules and the completed-v1 loop remain operational.
- **PASS — byte-bound input:** A one-value close mutation changes the fingerprint; metadata records both canonical frame SHA-256 and the exact promoted artifact SHA-256; partial amount is omitted and complete finite amount is retained.
- **PASS — sequence-bound calendar:** A missing or closed exact as-of row is rejected; future sessions are selected from sequence values greater than the exact open anchor under one revision.
- **PASS — strict immutable commit:** Missing digest, catalog divergence, NaN sampling, wrong future count, wrong descriptor horizon, input descriptor divergence, escaped/absolute/symlink paths, and checksum mismatch all fail before record creation.
- **PASS — supply-chain seal:** No 05-28 rejection or 05-26 fail-closed state was bypassed; no production supply identity or dependency mutation was authored.

## Threat Mitigation Evidence

- **T-05-22-01:** Factory construction and published availability now require the complete local service, actuals, runner, recovery, path reader, scanner, and successful scheduler registration.
- **T-05-22-02:** `frame_payload_sha256` and the promoted Parquet checksum both enter the server-derived fingerprint; browser values never do.
- **T-05-22-03:** Exact full-form as-of identity, one open row, and greater sequence values determine the horizon.
- **T-05-22-04:** Parent-bound identity equality, strict revisions/digests/sampling/cardinality, configured-root regular-file checks, and exact output shape protect the only commit point.
- **T-05-22-05:** Forecast service, runner, scanner, and host retain explicit empty action seams; all host action spies remained at zero.
- No unplanned network endpoint, schema migration, database, queue, container, provider, broker, market-action, dependency, lock, or provisioning surface was introduced.

## TDD Gate Compliance

- Task 1 RED `49ee5a1` preceded GREEN `3c6c773` and captured both missing service composition and queued placeholder behavior.
- Task 2 RED `920f547` preceded GREEN `a01c3aa` and captured partial amount admission plus absent strict commit/path contracts.
- Regression commit `18ac59c` migrated shared host fixtures after the full planned behavior was green; no refactor-only commit was necessary.

## Known Stubs

None. Empty deployment Forecast components intentionally mean unavailable under the still-rejected supply gate; they cannot produce records or masquerade as approved identities. Empty validation-warning lists and no-action collaborator maps are explicit bounded outcomes, not missing implementation.

## Issues Encountered

- The ignored isolated pytest launcher inherited a primary-checkout shebang. It was corrected locally without changing tracked dependencies or lock state.
- The host fixture originally had only future calendar rows because the prior implementation used lexical selection without an anchor. Tests now construct an explicit governed open sequence-zero as-of row before exercising the production calendar.
- Host regression warnings are the existing Polars streaming/sortedness warnings from the shared Phase 1 fixture pipeline; all requested assertions pass.

## User Setup Required

None. Real Kronos/PyTorch provisioning remains intentionally unavailable until a future independent human approval supplies every identity required by the rejected 05-28 gate.

## Next Phase Readiness

- Plan 05-23 can build path/cursor/SSE work on a strict completed record whose paths, sessions, and quantiles have trustworthy parent identities.
- Plan 05-27 can bind executed vendored/config bytes and child import origin without weakening this service's pre-spawn and commit checks.
- Plan 05-26 remains blocked by the complete 05-28 supply rejection; this plan provides no substitute identity.
- Shared `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` remain untouched as required by the Wave 12 executor contract.

## Self-Check: PASSED

- All nine implementation/test artifacts and this summary exist in the isolated checkout.
- RED/GREEN/regression commits `49ee5a1`, `3c6c773`, `920f547`, `a01c3aa`, and `18ac59c` resolve in history.
- The literal plan-level four-part verification and all three focused regression files passed.
- Stub scan found no goal-blocking placeholder marker in any created or modified plan file.
- No task commit deleted a tracked file; scoped implementation paths are clean.
- `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` were not modified.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-17*
