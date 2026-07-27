---
phase: 02-factor-and-strategy-research
plan: "03"
subsystem: immutable-experiment-catalog
tags: [python, sqlite, experiment-catalog, provenance, comparison]

requires:
  - "02-01 immutable FactorRevision registry and operational SQLite migrations"
  - "02-02 completed FactorEvaluationResult evidence package and managed artifact descriptors"
provides:
  - "Immutable factor and registered-strategy experiment snapshots in operational SQLite"
  - "Explicit one-time retention gate for comparison candidates"
  - "Metadata-only comparison with normalized deltas and compatibility warnings"
affects: [02-04, research-api, backtest-workspace]

tech-stack:
  added: []
  patterns:
    - "Insert complete provenance snapshots transactionally; never update snapshot fields."
    - "Bind each artifact descriptor to its source run ID and managed relative path before persistence."
    - "Compare only explicit retained completed validated snapshots; no execution, provider call, artifact read, ranking, or winner."

key-files:
  created:
    - backend/app/research/catalog.py
    - backend/tests/research/test_experiment_catalog.py
  modified:
    - backend/app/research/repository.py

key-decisions:
  - "Completed evidence is stored unretained; retain sets retained_at exactly once."
  - "The factor handoff accepts only completed FactorEvaluationResult evidence, while strategy persistence accepts only StrategyBacktestResult with a matching registered identity."
  - "Comparison always exposes all selected snapshots and normalized values for configuration, governed input, predictions/signals, metrics, artifacts, and model provenance."
  - "Compatibility differences are warnings rather than a synthesized winner score."

requirements-completed: [FACT-03]

coverage:
  - id: FACT-03-CATALOG
    description: "Completed factor and registered strategy evidence is immutable, explicitly retained, and preserved despite source mutation."
    requirement: FACT-03
    verification:
      - kind: test
        ref: "uv run --project backend pytest backend/tests/research/test_experiment_catalog.py -q"
        status: pass
  - id: FACT-03-COMPARISON
    description: "Candidate filtering, artifact validation, normalized deltas, every compatibility warning, and no-winner semantics are enforced."
    requirement: FACT-03
    verification:
      - kind: test
        ref: "uv run --project backend pytest backend/tests/research/test_experiment_catalog.py -q"
        status: pass

completed: 2026-07-11
status: complete
---

# Phase 02 Plan 03: Immutable Experiment Catalog Summary

Implemented the local immutable experiment catalog over the shared operational SQLite database. Catalog records are self-contained snapshots of completed factor evidence or server-issued registered-strategy results; source definitions are never re-read or updated during retrieval and comparison.

## Accomplishments

- Added transactional snapshot persistence for factor and registered-strategy runs, including configuration, governed manifest, prediction/signal metadata, metrics, managed artifacts, diagnostics, and optional model/provider provenance.
- Enforced artifacts as unique managed relative paths under `research_artifacts/<originating-run-id>/`, bound to their run ID with a lowercase SHA-256 checksum, byte size, type, and timestamp.
- Added audit-only draft/running/failed/cancelled/invalid records and an explicit one-time retention operation restricted to completed validated records.
- Added candidate filtering and metadata-only side-by-side comparisons with normalized deltas for every required evidence dimension.
- Added stable universe, window, horizon, and governed manifest revision/fingerprint warnings without a winner or ranking field.
- Added focused temporary-SQLite tests covering evidence immutability, artifact binding, source mutation, strategy snapshot boundaries, retention, candidate exclusion, transparent deltas, and compatibility warnings.

## Task Commits

Each task was committed atomically:

1. **Task 1: Persist immutable factor and registered-strategy experiment snapshots** — `014000c`
2. **Task 2: Build retained-completed-only comparison with explicit deltas and warnings** — `8d69b1f`
3. **Task 3: Prove catalog immutability, status filtering, and comparison transparency** — `80b6771`

**Plan metadata:** committed with this summary.

## Verification

- `uv run --project backend pytest backend/tests/research/test_experiment_catalog.py -q` — **4 passed**

The focused tests prove immutable persisted factor and strategy snapshots, artifact bytes/checksums and descriptor binding preservation, explicit one-time retention, exclusion of unretained and diagnostic records, every required incompatibility warning, normalized comparison values, and absence of winner/ranking semantics.

## Deviations from Plan

None. Plan 02-01 supplied the required additive `prediction_signal_json` migration before catalog persistence was implemented.

## User Setup Required

None.

## Next Phase Readiness

Plan 02-04 can use `ExperimentCatalog.record_factor_evaluation` for completed `FactorEvaluationResult` values and `record_strategy_backtest` for successful server-issued `StrategyBacktestResult` values, then expose explicit retain/list/compare interactions without rerunning experiments.

---
*Phase: 02-factor-and-strategy-research*
*Completed: 2026-07-11*
