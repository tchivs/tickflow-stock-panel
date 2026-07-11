---
phase: 02-factor-and-strategy-research
plan: "02"
subsystem: governed-factor-evaluation
tags: [python, polars, backtest, reproducibility, artifacts, factor-research]

requires:
  - "02-01 immutable FactorRevision registry and restricted factor DSL"
provides:
  - "Validated stored-factor evaluation through BacktestEngine and Polars"
  - "Separate Pearson IC and Spearman RankIC series and summaries"
  - "Explicit resolved configuration and governed input manifest"
  - "Immutable checksummed evaluation artifacts under the application data root"
affects: [02-03, 02-04, research-catalog, research-api]

tech-stack:
  added: []
  patterns:
    - "Validate full configuration and stored revision before loading a governed panel."
    - "Load only identity, price, and validated DSL dependency columns through BacktestEngine."
    - "Use exclusive artifact namespaces and files; collisions fail without replacing prior bytes."

key-files:
  created:
    - backend/app/research/artifacts.py
    - backend/app/research/evaluation.py
    - backend/tests/research/test_factor_evaluation.py
  modified:
    - backend/app/backtest/factor.py

key-decisions:
  - "IC always denotes Pearson cross-sectional correlation; RankIC always denotes Spearman cross-sectional correlation."
  - "An evaluation result is retention-ready metadata and artifact descriptors, not a raw market-data copy or a catalog write."
  - "Every valid attempt receives an opaque run ID before BacktestEngine data access; invalid requests make no load attempt."

requirements-completed: [FACT-01, FACT-02]

coverage:
  - id: FACT-01-EVALUATION
    description: "Validated factor revisions load governed dependency columns and produce separate IC/RankIC evidence with explicit provenance."
    requirement: FACT-01
    verification:
      - kind: test
        ref: "uv run pytest tests/research/test_factor_evaluation.py -q"
        status: pass
  - id: FACT-02-ARTIFACTS
    description: "Evaluation artifacts are run-bound, checksummed, managed-path references written with no-replace semantics."
    requirement: FACT-02
    verification:
      - kind: test
        ref: "uv run pytest tests/research/test_factor_evaluation.py -q"
        status: pass

completed: 2026-07-11
status: complete
---

# Phase 02 Plan 02: Governed Factor Evaluation Summary

Implemented governed factor-revision evaluation as a separable research service. It validates the stored immutable revision and every resolved run input before calling `BacktestEngine.load_panel`, compiles only the validated DSL through Polars, and returns retention-ready evidence without writing catalog metadata.

## Accomplishments

- Added explicit resolved configuration, factor revision provenance, governed input manifest, warmup/rebalance/horizon handling, required-source-field loading, and structured invalid/failed diagnostics.
- Added distinct daily Pearson IC and Spearman RankIC series plus independent summaries; preserved grouped and long-short evidence as supplemental results.
- Corrected the existing factor backtest contract so its former rank-only `ic` output is now truthfully exposed as `rank_ic_*`, alongside new Pearson `ic_*` fields.
- Added managed JSON evidence bundles under `data_dir/research_artifacts/<opaque-run-id>/`, with relative paths, content types, sizes, SHA-256 checksums, and exclusive no-replace writes.
- Added offline contract coverage using a stub governed panel, temporary SQLite factor registry, and temporary application data root.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend factor computation for compiled expressions and distinct IC/RankIC evidence** — `b680c6b`
2. **Task 2: Write managed immutable evaluation artifacts with verifiable references** — `a8d040a`
3. **Task 3: Prove metric truthfulness, reproducibility data, and artifact boundaries** — `8e860e1`

**Plan metadata:** committed with this summary.

## Verification

- `uv run pytest tests/research/test_factor_evaluation.py -q` — **5 passed** (two existing Polars pivot deprecation warnings)
- `uv run pytest tests/test_st_limit_and_sharpe.py -q` — **5 passed**

The focused contracts prove distinct numerical IC/RankIC values, no data load for invalid configuration or missing revision, dependency-only panel requests, resolved manifest/config presence, opaque run allocation, checksum/size verification, managed relative artifact paths, empty-data failure behavior, and no-replace collision protection.

## Deviations from Plan

None. `BacktestEngine` itself needed no source change: its existing `load_panel` boundary already provided the required governed access seam.

## User Setup Required

None.

## Next Phase Readiness

Plan 02-03 can accept `FactorEvaluationResult` only when its `status` is `completed`, persisting its factor revision, resolved configuration, input manifest, separate metric evidence, supplemental outputs, and artifact descriptors without rerunning the evaluation.

---
*Phase: 02-factor-and-strategy-research*
*Completed: 2026-07-11*
