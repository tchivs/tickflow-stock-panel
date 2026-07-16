---
phase: 05-optional-enhancements
plan: "08"
subsystem: shadow-immutable-evidence
tags: [sqlite, immutable-artifacts, csv, xlsx, pydantic, scikit-learn, canonical-json, tdd]
requires:
  - phase: 05-optional-enhancements
    plan: "02"
    provides: executable RED contracts and hostile deterministic Shadow fixtures
  - phase: 05-optional-enhancements
    plan: "06"
    provides: Phase 05 append-only migration and shared managed immutable artifact store
  - phase: 05-optional-enhancements
    plan: "07"
    provides: approved optional scikit-learn dependency boundary
provides:
  - bounded UTF-8, GB18030, and data-only XLSX execution-log normalization
  - immutable attributable import batches, normalized trade facts, and correction/same-content lineage
  - exact frozen evidence manifests with explicit exclusions and artifact integrity verification
  - deterministic shallow-tree export to canonical replayable allowlisted rule JSON
  - data-only immutable candidate persistence with complete evidence and limitation provenance
affects: [05-11, 05-14, 05-15, 05-16, SHDW-01]
tech-stack:
  added: []
  patterns:
    - shared managed immutable artifact store wrapped in one server-generated batch namespace per import attempt
    - exact evidence membership as canonical JSON plus stable SHA-256 fingerprint
    - optional estimator discarded immediately after allowlisted rule export and replay equivalence validation
key-files:
  created:
    - backend/app/shadow/__init__.py
    - backend/app/shadow/schemas.py
    - backend/app/shadow/artifacts.py
    - backend/app/shadow/repository.py
    - backend/app/shadow/importer.py
    - backend/app/shadow/distillation.py
  modified: []
key-decisions:
  - "Same-content retries and corrections always receive distinct batch and artifact identities; content hashes record lineage but never deduplicate facts."
  - "Every trade in an included completed batch must be explicitly included or excluded before an evidence set can be frozen."
  - "The optional learner is transient: only fixed fields, operators, thresholds, metrics, assumptions, seed, source batches, and replay evidence cross the persistence boundary."
patterns-established:
  - "Shadow import boundary: validate byte/media/path bounds, atomically finalize raw bytes, then append the batch and normalized rows in one short SQLite transaction."
  - "Shadow candidate boundary: export positive leaf paths, validate canonical rule JSON, compare data-only replay to estimator decisions, and discard the estimator before persistence."
requirements-completed: [SHDW-01]
coverage:
  - id: D1
    description: "Bounded local CSV/XLSX logs become distinct attributable immutable batches while preserving raw values, timezone, duplicate groups, partial fills, corrections, diagnostics, and raw-artifact integrity."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "cd backend && uv run pytest tests/shadow/test_imports.py tests/shadow/test_evidence_sets.py tests/shadow/test_distillation.py -x"
        status: pass
    human_judgment: false
  - id: D2
    description: "Evidence sets freeze exact completed-batch and trade membership with explicit exclusions, stable fingerprints, and append-only database enforcement."
    requirement: SHDW-01
    verification:
      - kind: integration
        ref: "backend/tests/shadow/test_evidence_sets.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Deterministic bounded distillation retains only replayable allowlisted canonical rule data and complete evidence, parameter, metric, and limitation provenance."
    requirement: SHDW-01
    verification:
      - kind: unit
        ref: "backend/tests/shadow/test_distillation.py"
        status: pass
    human_judgment: false
metrics:
  duration: 15m 9s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 08: Immutable Shadow Import And Distillation Summary

**Bounded broker-log normalization now freezes every execution attempt into attributable immutable evidence and converts transient shallow trees into canonical replayable rule facts with no executable model state.**

## Performance

- **Duration:** 15m 9s
- **Started:** 2026-07-16T05:54:08Z
- **Completed:** 2026-07-16T06:09:17Z
- **Tasks:** 2/2
- **Files created:** 6

## Accomplishments

- Added strict frozen Pydantic contracts, a batch-scoped adapter over the shared immutable store, and a bounded importer for UTF-8/GB18030 CSV plus data-only XLSX. Source values, Asia/Shanghai normalization, fees, row ordinals, partial fills, duplicate groups, and missing-fill identities remain independently reviewable.
- Added append-only repository boundaries for new import attempts, same-content/correction lineage, normalized fills, safe rejected diagnostics, exact evidence membership, explicit exclusions, stable fingerprints, and immutable candidate data.
- Added deterministic governed-feature distillation with fixed seed, balanced classes, depth/leaf bounds, fixed feature/operator allowlists, canonical JSON, replay equivalence, complete provenance/limitations, and immediate estimator discard.

## Task Commits

The Wave 0 failing contracts were preserved and each production task was committed atomically at GREEN:

1. **Task 1 RED contract: Immutable import and evidence behavior** — `176aa34319e6b257ba64622232bf141a22f58864` (`test(05-02)`)
2. **Task 1 GREEN: Immutable Shadow import evidence** — `bf6fb85232310a11709c1888375b1f2eb2b3e5aa` (`feat(05-08)`)
3. **Task 2 RED contract: Explainable distillation behavior** — `c2ec721c9b9e0fb6cfbc9b13f5f18f689e7c0d37` (`test(05-02)`)
4. **Task 2 GREEN: Replayable Shadow rules** — `9c842e8713465130668802f46103074e339f9786` (`feat(05-08)`)

## Files Created/Modified

- `backend/app/shadow/__init__.py` — Narrow domain exports for import, artifact, evidence, and repository boundaries.
- `backend/app/shadow/schemas.py` — Strict frozen mapping, artifact, evidence-exclusion, rule, and candidate DTOs with undeclared fields forbidden.
- `backend/app/shadow/artifacts.py` — Batch-scoped wrapper over `ManagedImmutableArtifactStore` with contained public descriptors, metadata/scope/payload verification, and uncommitted cleanup.
- `backend/app/shadow/repository.py` — Parameterized short SQLite transactions and safe reconstruction for immutable batches, trades, evidence manifests, and candidates.
- `backend/app/shadow/importer.py` — Bounded media/path/byte/row/column/cell validation, inert CSV/XLSX parsing, canonical fill normalization, and atomic confirm/reject persistence.
- `backend/app/shadow/distillation.py` — Lazy optional learner, governed feature validation, deterministic negative sampling, bounded tree export, fixed rule replay, and data-only candidate construction.

## Verification

```text
cd backend && uv run pytest tests/shadow/test_imports.py tests/shadow/test_evidence_sets.py tests/shadow/test_distillation.py -x
pytest: 22 passed
```

The exact Task 1 gate separately passed 15/15 nodes and the exact Task 2 gate separately passed 7/7 nodes. Only the plan-declared focused Shadow files were exercised; no formatter, linter, browser suite, unrelated domain suite, or project-wide command was run.

## Threat Mitigation Evidence

- **T-05-08-01:** Client paths never select storage paths; media/suffix and pre-parse limits fail closed; shared descriptor, metadata, scope, size, and payload digests are reverified before evidence selection.
- **T-05-08-02:** Only CSV and macro-free `.xlsx` packages are accepted. Archive members are bounded and containment-checked; formula-shaped values remain strings and no subprocess, shell, macro, or formula engine is invoked.
- **T-05-08-03:** Same-content and correction imports append distinct facts; duplicate groups never merge rows; exact evidence selection is canonicalized; Phase 05 database triggers reject direct UPDATE and DELETE.
- **T-05-08-04:** The tree is lazy and transient. Exported paths accept only three fixed fields, two fixed operators, finite thresholds, and bounded schema; replay must equal estimator decisions before the data-only candidate is appended.
- **T-05-08-05:** Public descriptors are relative and projections omit raw bytes, absolute paths, exceptions, account secrets, and executable model representations.

## Decisions Made

- Broker fill identifiers own row identity when present. Missing identifiers use the canonical account/symbol/side/time/quantity/price/fees/currency tuple plus row ordinal, while a separate tuple without ordinal forms the duplicate-review group.
- An evidence set is valid only when the selected completed batches belong to the principal and every trade is named exactly once as included or excluded; equivalent ordering replays to the same fingerprint and record.
- Candidate-only metadata not represented by dedicated migration columns is retained as canonical data inside the immutable parameters record and reconstructed through a deny-by-default repository projection; no estimator object or arbitrary source is accepted.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added the Shadow package initializer required for Python imports**
- **Found during:** Task 1 GREEN implementation
- **Issue:** The plan named five domain modules but the absent `app.shadow` package also required an initializer before any declared public boundary could import.
- **Fix:** Added a narrow `backend/app/shadow/__init__.py` that exports only the implemented artifact, importer, evidence, and repository contracts.
- **Files modified:** `backend/app/shadow/__init__.py`
- **Verification:** All 22 focused Shadow nodes import and pass.
- **Committed in:** `bf6fb85232310a11709c1888375b1f2eb2b3e5aa`

---

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking package boundary).
**Impact on plan:** The initializer is the minimum required Python package seam and adds no authority, dependency, endpoint, or unrelated scope.

## Issues Encountered

- The isolated worktree began on detached `HEAD`; it was attached to `worktree-agent-05-08` before any commit.
- The fresh worktree environment did not initially contain the already-declared `dev` and `shadow` extras. They were synchronized through `uv run --extra dev --extra shadow` without changing `pyproject.toml`, `uv.lock`, or any provisioning file; the exact plan commands then passed unchanged.

## TDD Gate Compliance

- Task 1 began from the preserved `176aa34319e6b257ba64622232bf141a22f58864` RED contract and was observed failing at the absent `app.shadow` boundary before GREEN commit `bf6fb85232310a11709c1888375b1f2eb2b3e5aa` made all 15 import/evidence nodes pass.
- Task 2 began from the preserved `c2ec721c9b9e0fb6cfbc9b13f5f18f689e7c0d37` RED contract and was observed failing at absent `app.shadow.distillation` before GREEN commit `9c842e8713465130668802f46103074e339f9786` made all 7 distillation nodes pass.

## Known Stubs

None. Empty lists are bounded accumulators or safe rejected outcomes, optional `None` values are explicit absent input/state, and the `pickle`/`joblib` strings occur only in the denylist that rejects forbidden retained state.

## User Setup Required

None. Shadow distillation remains an independently selectable approved optional extra; default application operation is unchanged.

## Next Phase Readiness

- Plan 05-11 can consume frozen evidence sets and replayable candidate facts for chronological IS/OOS evaluation and research-only retention.
- Plans 05-14 through 05-16 can wire module availability, safe projections, API, and UI without weakening import or candidate authority.
- No broker, manual ledger, position mutation, strategy registration, monitor, playbook, or live market action path was introduced.

## Self-Check: PASSED

Verified all six Shadow implementation files and this summary exist, both Plan 05-08 task commits resolve as commits, the exact 22-node focused suite passes, no tracked dependency or provisioning file changed, and no delivery-blocking stub remains.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
