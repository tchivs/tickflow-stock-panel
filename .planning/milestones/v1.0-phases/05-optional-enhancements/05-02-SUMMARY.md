---
phase: 05-optional-enhancements
plan: "02"
subsystem: shadow-contract-testing
tags: [pytest, red-contract, immutable-artifacts, csv, xlsx, explainable-rules, is-oos]
requires:
  - phase: 02-factor-and-strategy-research
    provides: governed frozen-panel, allowlisted DSL, and immutable research retention precedents
  - phase: 04-advanced-capabilities
    provides: bounded spawned runner and independent evidence-gate precedents
provides:
  - deterministic UTF-8, GB18030, and data-only XLSX execution-log fixtures
  - strict exact-node RED harness accepting only declared missing app.shadow boundaries
  - executable immutable import, frozen evidence-set, explainable candidate, IS/OOS, and research-only retention contracts
affects: [05-08-shadow-foundation, 05-11-shadow-evaluation, SHDW-01]
tech-stack:
  added: []
  patterns:
    - exact pytest node inventory before expected-RED execution
    - typed missing-boundary allowlist with fixture, collection, xpass, timeout, and unrelated-failure rejection
    - deterministic hostile broker-log fixtures with immutable SHA-256 inventory
key-files:
  created:
    - backend/tests/shadow/fixtures/executions_utf8.csv
    - backend/tests/shadow/fixtures/executions_gb18030.csv
    - backend/tests/shadow/fixtures/executions.xlsx
    - backend/tests/shadow/test_imports.py
    - backend/tests/shadow/test_evidence_sets.py
    - backend/tests/shadow/test_distillation.py
    - backend/tests/shadow/test_evaluation_retention.py
    - backend/tests/shadow/verify_red_contract.py
  modified: []
key-decisions:
  - "Expected RED is valid only when collection and the exact 31-node inventory succeed and every node terminates at one allowlisted app.shadow ModuleNotFoundError or ImportError boundary."
  - "Formula-, macro-, archive-path-, and traversal-shaped fixture values remain inert cell data; the XLSX package contains no formula nodes or VBA project."
  - "Shadow retention contracts expose only an immutable research event tied to canonical passing IS/OOS evidence and define no activation authority."
patterns-established:
  - "Shadow RED harness: verify fixture digests and shape, collect exact nodes, then inspect structured JUnit failures rather than accepting a nonzero pytest exit."
  - "Shadow fixtures: preserve partial fills and duplicate groups while giving each source row an independently testable identity contract."
requirements-completed: [SHDW-01]
coverage:
  - id: SHDW-01-IMPORT-EVIDENCE-RED
    description: Immutable bounded local execution imports and explicit frozen evidence-set behavior are fixed as executable failing-first contracts.
    requirement: SHDW-01
    verification:
      - kind: other
        ref: uv run python tests/shadow/verify_red_contract.py --group import-evidence
        status: pass
    human_judgment: false
  - id: SHDW-01-DISTILLATION-RETENTION-RED
    description: Explainable allowlisted candidates, separate chronological IS/OOS evidence, and research-only retention are fixed as executable failing-first contracts.
    requirement: SHDW-01
    verification:
      - kind: other
        ref: uv run python tests/shadow/verify_red_contract.py --group distillation-evaluation
        status: pass
      - kind: other
        ref: uv run python tests/shadow/verify_red_contract.py --group all
        status: pass
    human_judgment: false
metrics:
  duration: 19m 17s
  completed: 2026-07-16
status: complete
---

# Phase 05 Plan 02: Shadow RED Contract Summary

**Deterministic hostile broker-log fixtures and 31 exact pytest nodes now pin immutable Shadow evidence, explainable rule candidates, independent IS/OOS evaluation, and research-only retention before production implementation.**

## Performance

- **Duration:** 19m 17s
- **Started:** 2026-07-16T03:43:50Z
- **Completed:** 2026-07-16T04:03:07Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Added byte-stable UTF-8, GB18030, and XLSX broker-log fixtures covering broker and missing fill IDs, duplicate groups, partial fills, fees, Asia/Shanghai timestamps, long cells, and inert formula/macro/path-shaped values.
- Defined 15 immutable-import/evidence nodes and 16 distillation/evaluation/retention nodes without broker connectivity, manual entry, random splitting, executable candidate state, or completed-v1 action authority.
- Added a strict harness that validates fixture hashes and structure, requires successful exact collection, parses structured JUnit failures, and rejects syntax, fixture, collection, assertion, timeout, crash, skip/xfail/xpass, changed-node, unexpected-pass, and unrelated-import failures.

## Task Commits

Each task was committed atomically:

1. **Task 1: Specify immutable bounded log imports and frozen evidence sets** — `176aa34` (`test`)
2. **Task 2: Specify explainable distillation, chronological IS/OOS, and research-only retention** — `c2ec721` (`test`)
3. **Strict-harness correctness remediation** — `956fbe1` (`fix`)

## Files Created/Modified

- `backend/tests/shadow/fixtures/executions_utf8.csv` — canonical UTF-8 execution-log fixture.
- `backend/tests/shadow/fixtures/executions_gb18030.csv` — byte-distinct GB18030 encoding of the same execution evidence.
- `backend/tests/shadow/fixtures/executions.xlsx` — deterministic macro-free XLSX package with hostile values stored only as inline strings.
- `backend/tests/shadow/test_imports.py` — bounded format/media/parser, artifact integrity, lineage, safe diagnostic, and no-authority contracts.
- `backend/tests/shadow/test_evidence_sets.py` — exact membership, stable fingerprint, duplicate/partial preservation, invalid-batch exclusion, and immutable trigger contracts.
- `backend/tests/shadow/test_distillation.py` — governed feature, deterministic sampling, shallow-tree bound, allowlist, replay, provenance, and forbidden-state contracts.
- `backend/tests/shadow/test_evaluation_retention.py` — chronological split, independent metrics/artifacts, retry, eligibility, replay safety, safe projection, and zero-action contracts.
- `backend/tests/shadow/verify_red_contract.py` — strict fixture, collection, node-inventory, structured-failure, timeout, and missing-production-boundary verifier.

## Verification

```text
cd backend && uv run python tests/shadow/verify_red_contract.py --group import-evidence
SHADOW RED CONTRACT VALID: import-evidence has 15 exact nodes; all failures are declared missing app.shadow production boundaries

cd backend && uv run python tests/shadow/verify_red_contract.py --group distillation-evaluation
SHADOW RED CONTRACT VALID: distillation-evaluation has 16 exact nodes; all failures are declared missing app.shadow production boundaries

cd backend && uv run python tests/shadow/verify_red_contract.py --group all
SHADOW RED CONTRACT VALID: all has 31 exact nodes; all failures are declared missing app.shadow production boundaries
```

Only the plan's focused verification commands were run; no formatter, linter, ordinary green domain suite, browser suite, or project-wide suite was run.

## Decisions Made

- The harness uses two gates: successful `pytest --collect-only` with an exact path-qualified node set, then an ordinary run whose JUnit cases must all fail at one typed allowlisted production import boundary.
- Missing `app.shadow` package/submodules and specific declared public symbols are accepted; missing third-party modules, arbitrary exception text, assertion failures mentioning an allowed message, and any other failure category are rejected.
- The XLSX fixture is a deterministic, bounded OOXML package with no `<f>` formula elements and no VBA member; hostile spreadsheet content is represented as inert inline text so future imports must never execute it.
- Same-content attempts, corrections, duplicate groups, partial fills, evidence manifests, candidate descriptors, split runs, and retention events are independently attributable contracts rather than mutable ledger state.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Hardened expected-RED classification against assertion-message spoofing**
- **Found during:** Overall strict-harness review after Task 2.
- **Issue:** The initial classifier searched for an allowed missing-module substring, so an unrelated assertion message containing `No module named 'app.shadow'` could have been misclassified as valid RED.
- **Fix:** Required full typed `ModuleNotFoundError`/`ImportError` lines, rejected unrelated exception markers, deduplicated identical JUnit message/traceback lines, and added accepted/rejected classifier self-checks on every harness invocation.
- **Files modified:** `backend/tests/shadow/verify_red_contract.py`
- **Verification:** `uv run python tests/shadow/verify_red_contract.py --group all` passed with all 31 exact nodes after hardening.
- **Committed in:** `956fbe1`

**Total deviations:** 1 auto-fixed (1 Rule 1 bug).
**Impact on plan:** The correction strengthened the required strict RED distinction without changing public Shadow contracts or production scope.

## Issues Encountered

- The plan referenced `backend/tests/advanced/test_governed_runner.py`, which does not exist in the current tree. The corresponding governed runner split/spawn tests are in `backend/tests/advanced/test_experiments.py`; those exact relevant sections and `backend/app/advanced/governed_runner.py` were used as the read-first analog.
- The environment has no `python` alias; deterministic binary fixtures were generated with the repository runtime via `uv run --project backend python`, then the temporary generator was removed.
- The repository ignores `*.xlsx` globally. The plan-declared deterministic fixture was staged explicitly by its exact path; no unrelated ignored file was added.

## TDD Gate Compliance

This Wave 0 plan intentionally ends at the strict RED contract. It contains the required `test(05-02)` RED commits and no `feat(05-02)` GREEN commit because Plans 05-08 and 05-11 explicitly own the production implementation and ordinary zero-exit pytest gates.

## Known Stubs

None. The absent `app.shadow` production package is the declared expected-RED boundary owned by Plans 05-08/05-11, not a shipped placeholder or mock fallback.

## User Setup Required

None.

## Next Phase Readiness

- Plan 05-08 can implement schemas, artifacts, repository, importer, and distillation directly against the exact import/evidence/distillation nodes.
- Plan 05-11 can implement bounded evaluation and research-only retention against the exact split/retry/eligibility/no-action nodes.
- Production owners must replace the strict expected-RED command with their plan-declared ordinary green pytest commands; this plan does not treat RED as feature completion.

## Self-Check: PASSED

Verified all eight declared Shadow artifacts exist, focused strict RED commands pass, task commits `176aa34` and `c2ec721` exist, remediation commit `956fbe1` exists, and no changed artifact contains TODO/FIXME/placeholder delivery stubs.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-16*
