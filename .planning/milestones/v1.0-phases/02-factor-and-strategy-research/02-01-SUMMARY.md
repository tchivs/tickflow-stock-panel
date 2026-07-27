---
phase: 02-factor-and-strategy-research
plan: "01"
subsystem: factor-dsl-and-registry
tags: [python, polars, sqlite, factor-dsl, immutable-revisions]

requires: []
provides:
  - "Restricted parsed factor DSL with explicit AST-to-Polars dispatch"
  - "Immutable SQLite factor definition/revision registry with deterministic similarity"
  - "Research registry attached to the existing operational database lifecycle"
affects: [02-02, 02-03, research-evaluation, experiment-catalog]

tech-stack:
  added: []
  patterns:
    - "Validate and parse factor source before any Polars expression is constructed."
    - "Append factor revisions only; use stable AST signatures and explainable overlap scores."
    - "Reuse the established operational.db migration and connection boundary for research metadata."

key-files:
  created:
    - backend/app/research/__init__.py
    - backend/app/research/factor_dsl.py
    - backend/app/research/factor_registry.py
    - backend/app/research/repository.py
    - backend/tests/research/test_factor_dsl.py
    - backend/tests/research/test_factor_registry.py
  modified:
    - backend/app/operational/migrations.py
    - backend/app/main.py

key-decisions:
  - "Only governed/enriched numeric fields, numeric literals, arithmetic, parentheses, unary minus, and seven fixed functions can enter the DSL."
  - "Structural exact matches sort before weighted shape, governed-field, and operator/function overlap; candidates never alter save behavior."
  - "Phase 2 experiment metadata tables are reserved in the operational migration without adding a datastore or time-series copy."

patterns-established:
  - "Factor DSL AST nodes are immutable and canonicalize harmless whitespace and parentheses before persistence."
  - "ResearchRepository uses parameterized, short-lived SQLite connections with operational foreign-key semantics."

requirements-completed: [FACT-01]

coverage:
  - id: FACT-01-DSL
    description: "Unsafe syntax rejection, canonicalization, dependency reporting, and explicit Polars compilation"
    requirement: FACT-01
    verification:
      - kind: test
        ref: "uv run pytest tests/research/test_factor_dsl.py tests/research/test_factor_registry.py -q"
        status: pass
  - id: FACT-01-REGISTRY
    description: "Immutable revision history and deterministic explained similarity"
    requirement: FACT-01
    verification:
      - kind: test
        ref: "uv run pytest tests/research/test_factor_dsl.py tests/research/test_factor_registry.py -q"
        status: pass

# Metrics
completed: 2026-07-11
status: complete
---

# Phase 02 Plan 01: Factor DSL and Registry Summary

Implemented the safe factor-definition foundation on the existing operational SQLite boundary.

## Accomplishments

- Added a versioned parser/tokenizer, typed immutable AST, canonical serialization, stable structural signatures, dependency extraction, and fixed AST-to-Polars dispatch for the restricted factor DSL.
- Added an immutable factor definition/revision repository and registry. Changed definitions append revisions, preserve prior rows, and return deterministic explainable similarity candidates.
- Appended the Phase 2 research schema—including reserved experiment catalog tables and immutable prediction/signal references—to the existing migration sequence, then attached `ResearchRepository` and `FactorRegistry` to the existing FastAPI lifespan after `OperationalRepository` migration.
- Added focused offline domain tests using temporary SQLite databases, a small Polars frame, and fresh-migration evidence-reference coverage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build the restricted parsed factor DSL and deterministic similarity primitives** - `d00b6b0` (feat)
2. **Task 2: Add immutable factor definitions, revisions, and explainable deterministic discovery** - `b415766` (feat)
3. **Task 3: Prove the safety and immutable-registry contracts at domain boundaries** - `9d3c456` (test)

4. **Schema reservation follow-up: immutable prediction/signal references for Plans 02-02/02-03** - `e1660e4` (fix)

**Plan metadata:** committed with this summary.

## Verification

- `uv run pytest tests/research/test_factor_dsl.py tests/research/test_factor_registry.py -q` — **15 passed**
- The tests create a fresh temporary `operational.db`, apply the complete migration sequence (including `research_experiments.prediction_signal_json`), reject unsafe DSL source before compilation, exercise actual Polars compilation, preserve an earlier revision byte-for-byte after a revision append, and verify repeated explained similarity ordering including a deterministic tie-break.

## Deviations from Plan

None.

## User Setup Required

None.

## Next Phase Readiness

Plans 02-02 and 02-03 can consume validated immutable factor revisions, their governed field dependencies, and the reserved experiment metadata schema without modifying the operational database boundary.

---
*Phase: 02-factor-and-strategy-research*
*Completed: 2026-07-11*
