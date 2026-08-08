# Plan 46-03 Summary: Validate-Before-Evaluate Boundary

**Plan:** 46-03 (wave 3)
**Phase:** 46-deterministic-alpha-factory
**Status:** Complete
**Date:** 2026-08-08

## Objective

Make every generated expression pass through the existing Factor DSL
parser/validator before it can enter the candidate ledger, and convert every
AF-REQ-03 rejection mode — including the depth/node complexity limits the DSL
does not enforce today — into an explicit, durable, budget-consuming `invalid`
candidate record with a structured diagnostic payload (AF-REQ-03 SC3).

This plan owns the validation surface that plan 46-04's worker loop consumes. It
reuses `parse_factor` / `canonicalize` / `extract_features` with no new parser,
no evaluator, no provider (D-01, D-08). Zero new runtime dependencies.

## Commits

| Hash | Message |
|------|---------|
| `789c5d4` | feat(phase-46): 46-03-01 validate every candidate through factor_dsl + complexity |
| `38a3999` | test(phase-46): 46-03-02 per-mode AF-REQ-03 rejection diagnostics |

## What Was Delivered

### `backend/app/research/alpha_factory.py` (extended)

The Wave 3 validate-before-evaluate boundary, added after the Wave 2 generation
engine. Exports (new in 46-03):

- **`measure_complexity(ast: Expression) -> tuple[int, int]`** — pure structural
  walk returning `(depth, node_count)` over the AST. No validation, no Polars:
  it reuses the existing `_all_paths` traversal; depth is one greater than the
  longest child path (leaves have depth 1). This enforces the complexity budget
  the DSL validator does not raise on its own (research §4). The AST is never
  mutated or re-validated.
- **`ValidationResult`** — frozen, slotted value object matching the shared
  contract exactly: `status: Literal["valid", "invalid"]`,
  `canonical_expression: str`, `features: FactorFeatures | None` (present iff
  valid), `reason: Mapping[str, Any]` (empty iff valid; structured diagnostic
  otherwise).
- **`validate_candidate(ast, *, max_depth, max_nodes) -> ValidationResult`** —
  the single validation entry point plan 46-04 calls. Complexity is the gate:
  depth/node count over the frozen limits is rejected first, then the surviving
  AST is canonicalized (which validates semantics) and re-parsed through
  `parse_factor` so the canonical form round-trips through the single text entry
  point — there is no second expression engine (D-01, D-08). Invalid candidates
  are never suppressed (T-46-09): they are explicit records the worker loop
  persists with `status="invalid"`.
- **`invalid_reason(error, raw_expression, vocab_version) -> dict[str, Any]`** —
  the structured diagnostic payload for a DSL-rejected expression
  (`{diagnostic, location, dsl_version, vocab_version, raw_expression}`), mapped
  directly to the `reason_json` column (research §4).
- **`validate_expression_text(source, *, max_depth, max_nodes) -> ValidationResult`** —
  thin helper that parses arbitrary source text via `parse_factor` and returns
  `invalid` through the same `invalid_reason` path on `FactorDslError`, with
  complexity measured on the parsed AST. Used by the per-mode tests; plan 46-04
  drives `validate_candidate` on ASTs.
- **`_dimension_exceeded_reason(...)`** — internal helper producing the
  complexity diagnostic (`"expression depth N exceeds max_depth M"` /
  `"expression nodes N exceeds max_nodes M"`) with the same five-key payload.

Import discipline unchanged: imports only `factor_dsl` + `run_contract` (+ stdlib
`dataclasses`/`collections.abc`/`typing`). The Wave 1 static import-discipline
guard (`TestImportDiscipline`) stays green — `FactorFeatures` and `Literal` were
added to the existing `factor_dsl` / `typing` import lines, no new authority
module.

### `backend/tests/research/test_alpha_factory.py` (extended)

48 new tests (Wave 1's 28 + Wave 2's 36 + Wave 3's 48 = **112** total):

- **`measure_complexity`** (11): correct depth/node counts for field, number,
  unary, binary, `rank`/`rolling_mean`/`clip` calls, nested trees; does not
  validate semantically-invalid ASTs (division-by-zero, denied field); does not
  mutate the AST.
- **`ValidationResult` shape** (2): frozen with the exact contract fields;
  invalid results carry `features=None`.
- **`validate_candidate`** (9): valid single field / binary round-trip through
  `parse_factor` with features and empty reason; invalid carries no features;
  excessive-depth / excessive-nodes complexity diagnostics naming the limit and
  measured value; within-limits is valid; **complexity gate runs before semantic
  validation** (an over-deep AST that also contains a denied field reports
  complexity, not the DSL error); DSL rejection (denied field) returns the full
  `invalid_reason`; every factory output validates.
- **Per-mode rejection coverage** (11 parametrized + 7 parametrized location +
  1 complexity-location + 3 AST-only + 1 payload + 3 never-suppressed = 26):
  denied field, unknown field, unknown function, invalid arity, partition
  semantics (monkeypatched invariant), excessive window, non-finite literal
  (`1e999`), division by literal zero, reversed clip bounds, malformed syntax,
  unsupported operator (constructed AST), excessive depth, excessive nodes.
  Each asserts a structured `reason` with `diagnostic`/`location`/`dsl_version`/
  `vocab_version` (and `raw_expression`); DSL-error locations match
  `line N, column M`; complexity locations name the measured dimension;
  rejections never raise past the boundary or return `None`; the payload
  round-trips to JSON for `reason_json`.

## Validation Contract (verified)

Every generated AST must clear three gates before it can become a ledger row:

1. **Complexity gate** — `measure_complexity` rejects depth/node count over the
   frozen `max_depth`/`max_nodes` (the one mode the DSL does not enforce).
2. **Semantic gate** — `factor_dsl.canonicalize` re-validates the AST (denied/
   unknown field, unknown function, arity, partition semantics, window, finite
   literal, division-by-zero, clip bounds, unsupported operator).
3. **Round-trip gate** — `factor_dsl.parse_factor(canonical_expression)`
   re-parses the canonical text, proving there is no second expression engine.

Only an AST that clears all three returns `status="valid"` with `features`; any
failure returns `status="invalid"` with a structured `reason` that the worker
loop persists verbatim as `reason_json`, consuming the declared budget.

## Test Totals

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/research/test_alpha_factory.py` (full file) | 112 | passed |
| `tests/research/test_alpha_factory.py` (`-k 'validation or complexity'`, task 01) | 19 selected | passed |
| `tests/research/test_alpha_factory.py` (`-k 'validation or invalid or diagnostic or complexity'`, task 02) | 47 selected | passed |

## Verification Commands (all green)

```
cd backend && pytest tests/research/test_alpha_factory.py -k 'validation or complexity' -q
→ 19 passed, 67 deselected

cd backend && pytest tests/research/test_alpha_factory.py -k 'validation or invalid or diagnostic or complexity' -q
→ 47 passed, 65 deselected

cd backend && pytest tests/research/test_alpha_factory.py -q
→ 112 passed
```

The plan's `<verification>` notes end-to-end persistence of invalid candidates
is exercised in plan 46-04; this plan proves the validation/diagnostic boundary
in isolation. The full backend suite was not run, per the plan.

## Must-Have Truths (verified)

- ✅ Every generated expression is parsed and semantically validated through the
  existing `factor_dsl.parse_factor` / `canonicalize` boundary before it can
  enter the candidate ledger; there is no second expression engine and no
  shortcut that bypasses validation (`validate_candidate`, `TestValidateCandidate`).
- ✅ Denied fields, unknown operators/functions, invalid arity, missing partition
  semantics, excessive rolling window, non-finite literals, division by literal
  zero, reversed clip bounds, malformed syntax, and excessive AST depth/node
  count each become an explicit `invalid` candidate record carrying a structured
  diagnostic payload (`test_each_rejection_mode_is_invalid`, `TestAstOnlyRejectionModes`).
- ✅ An invalid candidate carries a reason payload with `diagnostic`, `location`,
  `dsl_version`, `vocab_version`, and `raw_expression`; it is a durable fact that
  consumes the declared trial budget, never suppressed
  (`TestInvalidReasonPayload`, `TestInvalidCandidatesNeverSuppressed`).
- ✅ AST complexity (depth and node count) is measured and enforced against the
  frozen `max_depth`/`max_nodes`, producing an `invalid` record with a clear
  complexity diagnostic the existing `factor_dsl` validator does not raise on its
  own (`test_excessive_depth_returns_complexity_diagnostic`,
  `test_excessive_nodes_returns_complexity_diagnostic`,
  `test_complexity_gate_runs_before_semantic_validation`).

## Threat Model Mitigations

- **T-46-07 (Tampering/Elevation — expression acceptance):** a single
  `validate_candidate` path runs every expression through
  `factor_dsl.canonicalize` then `parse_factor`; there is no bypass or shortcut
  into the ledger. Complexity is the first gate, so even a semantically-invalid
  over-deep AST is rejected for complexity.
- **T-46-08 (Information disclosure — invalid reason payload):** the diagnostic
  carries the DSL message/location and the rejected raw expression; this is
  intentional provenance for an explicit invalid record, not a
  principal/secret/path leak.
- **T-46-09 (Repudiation — invalid candidate accounting):** invalid candidates
  are durable facts with `status="invalid"` and a structured reason; they are
  returned as explicit `ValidationResult`s (never raised past the boundary or
  swallowed to `None`) that the worker loop persists, consuming the declared
  budget — never `INSERT OR IGNORE`-dropped.

## Deviations

1. **`invalid_reason` + `validate_expression_text` landed in commit 46-03-01,
   not 46-03-02.** `validate_candidate` depends on `invalid_reason`, so both
   `invalid_reason` and the thin text helper `validate_expression_text` were
   implemented in the 46-03-01 commit alongside `validate_candidate` /
   `measure_complexity` / `ValidationResult`. The 46-03-02 commit adds the
   per-mode rejection coverage that fully exercises them. This is a commit-grouping
   refinement, not a scope change: the artifact set, signatures, and acceptance
   criteria are exactly as planned. Task-01's focused verify
   (`-k 'validation or complexity'`, 19 passed) and task-02's
   (`-k 'validation or invalid or diagnostic or complexity'`, 47 passed) are both
   green.
2. **`raw_expression` for a complexity failure in `validate_candidate` is `""`.**
   Complexity is the gate and is checked before canonicalization (per the plan),
   so an over-deep AST rejected at the complexity gate has no canonical form yet;
   the payload carries `raw_expression=""` (the key is present; the diagnostic
   names the exceeded limit and measured value, satisfying the acceptance). The
   text path (`validate_expression_text`) reports the parsed canonical expression
   because `parse_factor` succeeds first there.
3. **Pre-existing WIP isolation (concurrent collaboration):** the working tree
   carries ~65+ unstaged frontend files (components, e2e specs) and unstaged
   Phase-45 backend hardening from user/sibling work — **not**
   `frontend/src/pages/Watchlist.tsx`, which was zero-touch. Every 46-03 commit
   used explicit `git add` of only `backend/app/research/alpha_factory.py` and
   `backend/tests/research/test_alpha_factory.py`; no frontend or sibling-backend
   file entered a 46-03 commit. `frontend/src/pages/Watchlist.tsx` was never read
   or modified.

## Handoff (downstream plans)

- **Plan 46-04 (budget + diversity + worker persistence):** wrap each
  `GenerationResult` in `validate_candidate(ast, *, max_depth, max_nodes)` →
  `ValidationResult`. Persist `status="invalid"` candidates with `reason` as
  `reason_json` via `repository.append_candidate_attempt` (consuming the declared
  budget), and `status="generated"` valid candidates with their
  `canonical_expression` / `features`. `validate_candidate` is referenced by this
  exact signature and MUST NOT be redefined.

## Files Modified/Created

| File | Action |
|------|--------|
| `backend/app/research/alpha_factory.py` | Extended (measure_complexity, ValidationResult, invalid_reason, validate_candidate, validate_expression_text, _dimension_exceeded_reason) |
| `backend/tests/research/test_alpha_factory.py` | Extended (+48 tests; 112 total) |
| `.planning/phases/46-deterministic-alpha-factory/46-03-SUMMARY.md` | Created (this file) |
