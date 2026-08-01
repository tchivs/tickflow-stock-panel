---
phase: 10-factor-library-multi-factor-model
plan: 10-03
subsystem: research
tags: [FACT-04, DSL, partition-context, leakage-gate, wave-0]
requires: []
provides: ["_FUNCTION_PARTITION", "DENIED_FIELDS", "FactorFeatures.partition_context", "shifted_label_ic", "DSL_VERSION=factor-dsl-v2"]
affects: [backend/app/research/factor_dsl.py, backend/app/api/research.py, backend/tests/research/test_factor_dsl.py, backend/tests/research/test_factor_registry.py, backend/tests/research/test_factor_evaluation.py]
tech-stack:
  added: ["PartitionContext Literal type", "shifted_label_ic leakage gate"]
  patterns: ["compiler-side partition contract beside _FUNCTION_ARITY", "denied-field explicit diagnostics", "effective-context union computation"]
key-files:
  created: []
  modified: ["backend/app/research/factor_dsl.py", "backend/app/api/research.py", "backend/tests/research/test_factor_dsl.py", "backend/tests/research/test_factor_registry.py", "backend/tests/research/test_factor_evaluation.py"]
decisions:
  - "DSL_VERSION bumped factor-dsl-v1 -> factor-dsl-v2 (user pre-approved one-way door; stored v1 revisions keep their recorded version and remain readable)"
  - "partition_context defaults to {'pointwise'} for a pure pointwise expression (fields/operators); a call contributes its declared _FUNCTION_PARTITION context"
  - "shifted_label_ic returns inf when no finite per-date correlation survives (empty cross-section cannot be measured); NaN per-date corr rows dropped and non-finite filtered before the mean"
  - "test_factor_registry and test_factor_evaluation version assertions updated to factor-dsl-v2; /dsl/options now surfaces DSL_VERSION instead of the hard-coded v1 string"
metrics:
  duration: "~35m"
  completed_date: "2026-08-01"
status: complete
---

# Phase 10 Plan 3: DSL Partition-Context Contract + Leakage Gate Summary

DSL v2 compiler contract: every operator declares its partition semantics beside `_FUNCTION_ARITY`, label/identity fields are denied with specific diagnostics, the effective partition context is surfaced on `FactorFeatures`, and a deterministic shifted-label IC gate blocks lookahead expressions — locked by a test matrix keyed off `_FUNCTION_PARTITION`.

## What Was Built

- **`_FUNCTION_PARTITION` table** beside `_FUNCTION_ARITY` mapping `abs/sign/log1p/clip → pointwise`, `rank/zscore → per_date`, `rolling_mean → per_symbol` (each matches the actual `.over(...)` compile semantics in `_compile_node`).
- **Compile-time enforcement**: `_validate_call`, `_validate_expression`, and `_compile_node` all raise a specific `FactorDslError` when a function is in `_FUNCTION_ARITY` but not in `_FUNCTION_PARTITION`. `_validate_expression` also enforces it so manually constructed ASTs cannot bypass.
- **`DENIED_FIELDS`** explicit frozenset (`date`, `symbol`, `label`, `forward_return`, `_forward_return`, `_factor`, `_rank`, `_zscore`) with `_validate_field_name` raising `"denied label/identity field {name!r} cannot enter a factor expression"` — enforced at the parser, the validator, and the compile boundary (repeated validation for manually built ASTs).
- **`FactorFeatures.partition_context`** — new frozen field computed by `_partition_context`: union of leaf call contexts; pure pointwise expressions yield `{"pointwise"}`. Structural/shape signatures unchanged (verified by the existing signature test still passing).
- **`shifted_label_ic(evaluated, *, horizon)`** — deterministic leakage gate per RESEARCH.md: label displaced one extra horizon (`close[t+2H]/close[t+H] - 1`), per-date `pl.corr("_factor", "_shifted_label")`, NaN rows dropped, non-finite filtered, returns `abs(mean(ic))`, `inf` when empty.
- **`SHIFTED_LABEL_MAX_ABS_IC = 0.02`** constant in `factor_dsl.py` (kept in the DSL so every DSL change re-verifies against it; admission's no_label_leakage stage consumes the same value in 10-01).
- **`DSL_VERSION = "factor-dsl-v2"`** — the user pre-approved this one-way door. Stored v1 revisions keep their recorded `dsl_version`; `_validated_revision` still rejects cross-version reuse (verified by evaluation tests passing). `factor_registry.create_factor/revise_factor` store `parsed.dsl_version` unchanged — no code change needed there.
- **`/api/research/dsl/options`** now surfaces `DSL_VERSION` instead of the hard-coded `"factor-dsl-v1"` string (no other module hard-codes the v1 string; remaining `factor-dsl-v1` literals are test fixtures for stored-v1 revision records).

## Test Results

Wave-0 per-plan gate:

```bash
cd backend && .venv/bin/python -m pytest tests/research/test_factor_dsl.py tests/research/test_factor_registry.py -q --tb=short
# 36 passed
```

New/extended tests in `test_factor_dsl.py` (32 tests in file):
- `test_function_partition_table_is_consistent_with_arity` — `set(_FUNCTION_ARITY) == set(_FUNCTION_PARTITION)` (CI fails if a future operator lacks a partition entry).
- `test_denied_label_identity_fields_raise_specific_diagnostic` — parametrized over every `DENIED_FIELDS` member.
- `test_denied_label_field_is_identified_inside_a_composite_expression` — `close + label`, bare `date`, bare `symbol` all identify the denied field by name.
- `test_effective_partition_context_is_union_of_leaf_contexts` — composite `zscore + rolling_mean` → `{"per_date", "per_symbol"}`; pure `abs`/bare field → `{"pointwise"}`; mixed `rank + abs` → `{"per_date", "pointwise"}`.
- `test_shifted_label_ic_collapses_for_clean_factors` — parametrized matrix over **all** `_FUNCTION_PARTITION` functions on a deterministic zero-crossing panel; every clean factor `<= 0.02` (observed: abs 0.0015, sign 0.0049, log1p 0.0019, clip 0.0028, rank 0.0006, zscore 0.0021, rolling_mean 0.0024).
- `test_shifted_label_ic_blocks_a_lookahead_expression` — the displaced label's own window as a factor yields IC ≈ 1.0, far above the 0.02 gate.
- `test_shifted_label_ic_is_inf_for_an_empty_cross_section`.

Also updated: `test_factor_registry` and `test_factor_evaluation` version assertions → `factor-dsl-v2`. Full affected-suite run (57 tests across dsl/registry/evaluation/api/handoff/migrations) passed.

## Deviations from Plan

None - plan executed exactly as written. Notes (not deviations):
- `SHIFTED_LABEL_MAX_ABS_IC` lives in `factor_dsl.py` (the plan lists it under admission.py's policy constants; the DSL-side copy keeps the leakage gate self-contained and re-verified on every DSL change, per RESEARCH.md).
- The leakage fixture uses a zero-crossing price path (cumsum-clip) instead of a positive lognormal walk so `sign(close)` is non-constant; deterministic seed `np.random.default_rng(20260801)`.
- The `I001` import-order / `UP037` quoted-annotation / `UP035` Mapping-import findings on `factor_dsl.py` and `api/research.py` are pre-existing (verified by linting the pre-change checkout); test files I touched were auto-fixed with `ruff --fix`.

## Known Stubs

None.

## Threat Flags

None - no new network endpoints, auth paths, file access patterns, or schema changes. The compiler-side contract (FACT-04) closes the "lookahead / label leakage via new operators" elevation-of-privilege path in the plan's threat model.

## Self-Check: PASSED

- Files created/modified verified present via `git diff --stat` and `git status`.
- Commits verified: `c0f8476` (feat), `2b8b8bd` (test) both in `git log`.
- Wave gate re-run post-commit: 36 passed.
