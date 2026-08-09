# Plan 46-01 Summary: Versioned Vocabulary + Grammar Fingerprint Authority

**Plan:** 46-01 (wave 1)
**Phase:** 46-deterministic-alpha-factory
**Status:** Complete
**Date:** 2026-08-08

## Objective

Establish the versioned grammar/vocabulary authority for Phase 46 (AF-REQ-02 SC1): a stable,
deterministic SHA-256 fingerprint over the complete restricted Factor DSL vocabulary and the
expression-space structural constraints, server-owned population of the reserved manifest
fingerprint slots at freeze time, and fail-closed verification when a stored run's vocabulary
no longer matches the live DSL. This is the foundational Wave 1 layer every downstream plan
anchors on (candidate digests, determinism, and replay all anchor on the frozen fingerprint).

No second grammar engine, no parser, no evaluator, no provider, no OOS, no admission
(D-01, D-02, D-04, D-08, D-09). Zero new runtime dependencies.

## Commits

| Hash | Message |
|------|---------|
| `3963711` | feat(46-01): versioned vocabulary + grammar fingerprint from live DSL |
| `e09053d` | feat(46-01): server-owned manifest fingerprints + fail-closed vocab verify |

## What Was Delivered

### `backend/app/research/alpha_factory.py` (created)

The Wave 1 fingerprint authority. Exports:

- **Versioning constants** — `FACTORY_VERSION = "alpha-factory-v1"`, `PRNG_ALGORITHM =
  "python-random-MT19937-v1"` (pins the cross-process replay contract for plan 46-02),
  `CANONICAL_FORM = "factor-dsl-canonical-v1"`, `DEFAULT_MAX_DEPTH = 6`,
  `DEFAULT_MAX_NODES = 40`.
- **`vocabulary_fingerprint() -> str`** — `digest_bytes(...)` (reused from `run_contract`)
  over the *live* `factor_dsl` constants: `DSL_VERSION`, `sorted(ALLOWED_FIELDS)`,
  `sorted(DENIED_FIELDS)`, the binary-operator list `["+", "-", "*", "/"]`, the unary list
  `["-"]`, `dict(sorted(_FUNCTION_ARITY.items()))`, `dict(sorted(_FUNCTION_PARTITION.items()))`,
  and `MAX_ROLLING_WINDOW`. Any field/operator/arity/partition/window change alters the digest.
- **`grammar_fingerprint(*, max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES) -> str`** —
  `digest_bytes(...)` over the canonical-form id, max AST depth, max node count, and the pinned
  PRNG algorithm id, so any change to the legal candidate space mints a new frozen run.
- **`normalize_manifest_fingerprints(manifest) -> dict`** — shallow-copied manifest whose
  `grammar.fingerprint` and `vocabulary.fingerprint` are set server-side from the live DSL
  (honouring declared `max_depth`/`max_nodes`), overriding any client-supplied value; never
  mutates the caller's mapping.
- **`verify_vocabulary_fingerprint(frozen) -> None`** — recomputes from the live DSL and raises
  `VocabularyMismatchError` on any mismatch or missing value.
- **`VocabularyMismatchError`** — `ValueError` subclass carrying `frozen`/`live` attributes.

Import discipline: imports only `factor_dsl` and `run_contract`; no evaluation/provider/
admission/broker/repository/worker import (T-46-03; guard is enforced by a static test and
tightened in plan 46-04).

### `backend/app/research/run_contract.py` (modified — 2-line hook)

`freeze_input_snapshot` now normalizes the canonical manifest copy between the canonical copy
and the `component_digests` block:

```python
canonical_manifest = json.loads(canonical_json(manifest))
from app.research.alpha_factory import normalize_manifest_fingerprints   # lazy: breaks the cycle
canonical_manifest = normalize_manifest_fingerprints(canonical_manifest)
```

The import is **lazy inside the function** to break the `alpha_factory` ↔ `run_contract` cycle
(`alpha_factory` needs `digest_bytes` from `run_contract`; `run_contract` needs
`normalize_manifest_fingerprints` from `alpha_factory`). `alpha_factory` keeps a clean top-level
`factor_dsl` + `run_contract` import; the lazy import lives only in `run_contract`, so the
alpha_factory import-discipline guard stays green. Verified import-safe in both module-load orders.

### `backend/tests/research/test_alpha_factory.py` (created)

Focused fingerprint coverage (28 tests): versioning-constant pinning; vocabulary stability,
lowercase-64-hex, live-DSL equality, full-vocabulary coverage, field/arity sensitivity; grammar
stability, default usage, max-depth/max-node sensitivity, vocabulary-distinctness; static
import-discipline guard; normalization overwrite/non-mutation/declared-limits; freeze population
of placeholder slots, refreeze determinism, forged-fingerprint override, seed-distinctness
preserved; verify pass/mismatch/missing/attribute-recording/`ValueError`-subclass.

## Canonical Fingerprint Values (live DSL, for downstream handoff)

```
vocabulary_fingerprint() = 90039f5b0f1490840532b62e383e87b606589151e83623309f7078877648b18c
grammar_fingerprint()    = b95d365a724a3d0a5ca4d10a814cf4fa04e5c057712b4f270c6f37891fae20ee
FACTORY_VERSION          = alpha-factory-v1
PRNG_ALGORITHM           = python-random-MT19937-v1
CANONICAL_FORM           = factor-dsl-canonical-v1
DEFAULT_MAX_DEPTH        = 6
DEFAULT_MAX_NODES        = 40
```

## Test Totals

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/research/test_alpha_factory.py` | 28 | passed |
| `tests/research/test_run_contract.py` (`-k 'manifest or freeze or digest or idempotent'`) | 15 selected | passed |
| `tests/research/test_run_contract.py` (full file, final HEAD) | 101 | passed |
| **Total** | **28 + 101** | **all passed** |

## Verification Commands (all green)

```
cd backend && pytest tests/research/test_alpha_factory.py -k 'vocabulary or grammar or fingerprint' -q
→ 23 passed, 5 deselected

cd backend && pytest tests/research/test_alpha_factory.py -k 'vocabulary or fingerprint or normalize or mismatch' -q
→ 23 passed, 5 deselected

cd backend && pytest tests/research/test_run_contract.py -k 'manifest or freeze or digest or idempotent' -q
→ 15 passed, 84 deselected   (Phase 45 freeze contract unaffected)
```

Round-trip + import-order smoke (manual): freeze populates a server-owned `vocabulary.fingerprint`;
`verify_vocabulary_fingerprint` passes on it and rejects `"0"*64`; both `run_contract`-first and
`alpha_factory`-first module-load orders import cleanly.

## Must-Have Truths (verified)

- ✅ A stable, versioned vocabulary fingerprint is computed from the live Factor DSL constants
  (46 allowed fields, 8 denied fields, 7 functions + arity, 7 partition-semantics entries,
  4 binary + 1 unary operators, MAX_ROLLING_WINDOW, and DSL_VERSION) and is deterministic across
  calls; two independent calls in the same process return identical bytes.
- ✅ A grammar fingerprint folds the expression-space structural constraints (canonical-form id,
  max AST depth, max node count, and the pinned PRNG algorithm id) so any change to the legal
  candidate space mints a new frozen run instead of mutating the original.
- ✅ `freeze_input_snapshot` populates the manifest `grammar.fingerprint` and `vocabulary.fingerprint`
  slots server-side from the live DSL, overriding any client-supplied value, before the canonical
  digest is computed.
- ✅ On replay or load the live vocabulary fingerprint is recomputed and compared against the
  frozen value; a mismatch fails closed (`VocabularyMismatchError`) rather than reinterpreting
  stored tokens.

## Threat Model Mitigations

- **T-46-01 (Tampering — client-supplied fingerprints):** `normalize_manifest_fingerprints`
  overwrites both slots from live DSL constants inside `freeze_input_snapshot`, so a forged value
  cannot survive freeze (proven by the forged-fingerprint override test).
- **T-46-02 (Tampering/Repudiation — stored expressions vs live DSL):** `verify_vocabulary_fingerprint`
  recomputes from the live DSL and fails closed on mismatch/missing, preventing silent
  reinterpretation of stored tokens.
- **T-46-03 (Elevation — imports):** `alpha_factory.py` imports only `factor_dsl` and
  `run_contract`; a static guard test enforces no evaluation/provider/admission/broker/repository
  import (tightened further in plan 46-04).

## Deviations

1. **Plan-check W1 (field count):** the live `ALLOWED_FIELDS` has **46** entries, not the 44 cited
   in the early narrative/truth. The fingerprint reads the *live* module (`sorted(ALLOWED_FIELDS)`),
   so it is correct either way; test names/comments and this summary use 46. No code change beyond
   the narrative.
2. **Pre-existing WIP isolation (concurrent collaboration):** when 46-01 began, the working tree
   carried uncommitted Phase-45 hardening WIP (bounded-JSON validation in `run_contract.py`, plus
   `repository.py`/`run_schemas.py`/`run_service.py`/`migrations.py`). To avoid misattributing that
   WIP under a 46-01 commit, `run_contract.py` was **partial-staged** so the task-02 commit
   (`e09053d`) contains only the 2-line freeze hook (+2); the bounded-JSON WIP was left uncommitted.
   A sibling Phase-45 agent subsequently committed that WIP as `6508cd7..49d4fe7` (six `fix(45)`/
   `test(45)` commits) layered cleanly on top of `e09053d` — so the hook and the WIP now live in
   separate, correctly-attributed commits. The current HEAD `run_contract.py` carries both.
3. **Blocking syntax-error repair:** the pre-existing `repository.py` WIP had an unterminated
   `raise ValueError(` that prevented `conftest.py` (and therefore every research test) from
   importing. The single missing `)` was repaired so the suite could run; `repository.py` is not a
   46-01 file. That paren repair is now committed within the sibling's `6508cd7`.

## Phase-45 Interaction (resolved; not introduced by 46-01)

During 46-01, a full-suite run of `tests/research/test_run_contract.py` transiently showed 2
failures in `TestReviewFixInvariants` (artifact cross-run bind, checkpoint canonical-object) — a
test-ordering surface that **passed in isolation**. Worktree proof confirmed these were caused by
the Phase-45 WIP, **not** by 46-01:

- Worktree at the pre-46 baseline `3de27f7`: `test_run_contract.py` → 89 passed, 0 failed.
- Worktree at the 46-01 commit `e09053d` (all 46-01 work, **no** uncommitted WIP):
  `test_run_contract.py` → 89 passed, 0 failed; `test_alpha_factory.py` → 28 passed, 0 failed.

The sibling Phase-45 commits (`6508cd7..49d4fe7`) resolved those failures; at the final HEAD the
full `tests/research/test_run_contract.py` is **101 passed, 0 failed**.

## Files Modified/Created

| File | Action |
|------|--------|
| `backend/app/research/alpha_factory.py` | Created (fingerprint + normalize + verify + error surface) |
| `backend/app/research/run_contract.py` | Modified (+2-line freeze normalization hook, partial-staged) |
| `backend/tests/research/test_alpha_factory.py` | Created (28 tests) |
| `.planning/phases/46-deterministic-alpha-factory/46-01-SUMMARY.md` | Created (this file) |
