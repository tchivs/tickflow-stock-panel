# Plan 46-02 Summary: Deterministic Generation Engine

**Plan:** 46-02 (wave 2)
**Phase:** 46-deterministic-alpha-factory
**Status:** Complete
**Date:** 2026-08-08

## Objective

Build the deterministic candidate-generation engine (AF-REQ-02 SC2): given a frozen
seed and complexity limits, emit a bounded, canonical candidate stream whose
expressions, digests, operation labels, parent/child lineage, and ordering are
reproducible from the seed alone — independent of wall-clock or worker timing.

The engine uses a single instance-local `random.Random(seed)` over the existing
Factor DSL AST, re-canonicalizing every output through `factor_dsl.canonicalize`
(the single validator / serializer — no second expression engine). No RL, no
PyTorch, no GPU, no queue, no evaluator (D-01, D-02, D-08). Zero new runtime
dependencies. Validation-as-rejection (plan 46-03) and diversity/budget/worker
persistence (plan 46-04) layer on top.

## Commits

| Hash | Message |
|------|---------|
| `b496d35` | feat(phase-46): 46-02-01 deterministic seeded PRNG, seed pool, candidate digest |
| `647a3c7` | feat(phase-46): 46-02-02 mutation, crossover, lineage, full replay determinism |

## What Was Delivered

### `backend/app/research/alpha_factory.py` (extended)

The Wave 2 generation engine, added after the Wave 1 fingerprint authority.
Exports (new in 46-02):

- **`candidate_digest(*, canonical_expression, seed, step, operation, vocab_version) -> str`** —
  `digest_bytes(...)` (reused from `run_contract`) over
  `{expression, vocab_version, seed, step, operation}`. The digest folds in `step`
  and `operation`, so two structurally identical expressions emitted at different
  steps (or via different operations) get distinct digests, while the same frozen
  inputs always reproduce the same digest sequence (one-row-per-attempt model).
- **`GenerationResult`** — frozen, slotted value object:
  `step` (0-based attempt ordinal), `operation`, `ast` (Factor DSL `Expression`),
  `canonical_expression`, `parent_steps` (empty for seed, one for mutation, two
  distinct for crossover), `seed`; plus read-only `digest` and `attempt_ordinal`
  (`step + 1`) properties.
- **`AlphaFactory(seed, *, max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES, max_candidates=256)`** —
  the deterministic generator:
  - **Single instance-local PRNG:** `random.Random(seed)` drives every
    nondeterministic draw; the global `random` module is never drawn from, so the
    whole stream is reproducible from the seed (T-46-04; enforced by a static
    guard test).
  - **Frozen seed pool (no PRNG draws):** deterministic enumeration order (O3) —
    (1) single allowed fields, (2) unary negation of fields, (3) `rank`/`zscore`
    of single fields, (4) `rolling_mean` variants over a field with legal windows
    `(5, 20, 60)`, (5) small binary trees over field/field and field/literal.
    Size = `4·N + 3·N + 5` (N = `len(ALLOWED_FIELDS)` = 46) = **327**.
  - **Mutation wave:** `point_mutation_field` / `_operator` / `_literal` /
    `subtree_replacement`; each selects a parent step from the produced frontier,
    applies one PRNG-driven edit, and re-canonicalizes. Invalid products (rare
    clip-bound ordering) retry within a bounded budget; a guaranteed-valid
    field-swap fallback bounds termination.
  - **Crossover wave:** graft a PRNG-chosen subtree from parent B into parent A
    at a PRNG-chosen position; two distinct preceding parents, re-canonicalized.
  - **`generate_next()`** — produces one candidate per step (seed pool → mutation
    wave → crossover wave, splitting the remaining budget evenly), `None` at the
    budget boundary.
  - **`replay_to(k)`** — re-derives the first `k` candidates by rebuilding a
    fresh factory from the seed (no serialized PRNG state; O2). Preserves the
    budget so the mutation/crossover dispatch reproduces exactly.
- **AST traversal/rebuild helpers** (`_children`, `_all_paths`, `_node_at`,
  `_replace_child`, `_replace_at`) — because every Factor DSL node is a frozen
  dataclass, mutation/crossover rebuild only the edited path to the root and share
  unchanged subtrees by reference (no deep copy).

Import discipline unchanged: imports only `factor_dsl` + `run_contract` (+ stdlib
`random`/`dataclasses`); no evaluation/provider/admission/broker/repository/worker
import. The Wave 1 static import-discipline guard stays green.

### `backend/tests/research/test_alpha_factory.py` (extended)

36 new tests (Wave 1's 28 + Wave 2's 36 = **64** total):

- **Digest** (6): lowercase-64-hex, identical-input stability, step/operation/
  vocab/seed provenance sensitivity.
- **GenerationResult** (3): `digest` matches `candidate_digest`, ordinal = step+1,
  seed candidates carry empty `parent_steps`.
- **Seed pool** (4): every seed canonicalizes + uses only allowed fields;
  `generate_next` returns `None` past budget; frozen enumeration order (single →
  unary → rank/zscore → rolling_mean → binary trees); size is vocab-derived.
- **PRNG isolation** (1): static guard that no draw comes from the global
  `random` module — only `random.Random(seed)`.
- **Worker-timing independence** (2): two instances produce identical prefixes;
  `replay_to` matches the live prefix.
- **Budget / waves** (3): stops at `max_candidates`; steps are 0-based contiguous;
  operations within the allowed label set; seed → mutation → crossover ordering.
- **Output validity** (1): every output re-canonicalizes and references only
  governed numeric fields.
- **Mutation kinds** (4): deterministic white-box coverage of each operation on
  applicable parents (field/operator/literal/subtree).
- **Lineage invariants** (4): seed → 0 parents; mutation → exactly 1 preceding
  parent; crossover → 2 distinct preceding parents; every parent step produced
  earlier.
- **Full replay determinism** (3): two instances produce byte-identical full
  streams (canonical / digest / operation / parent_steps); distinct
  provenance-encoded digest sequence; different seeds diverge.
- **Replay determinism** (2): `replay_to` reproduces the prefix into the mutation
  wave; rebuilds from the seed with no serialized state (incl. from a
  fully-consumed factory).

## Determinism Contract (verified)

Replaying the same frozen seed + limits produces, for the full budget, byte-identical:

- canonical expressions,
- candidate digests,
- operation labels,
- parent/step lineage tuples,
- attempt-ordinal order (`attempt_ordinal = step + 1`),

independent of worker timing — proven by `TestFullReplayDeterminism` (two
independent `AlphaFactory` instances over identical inputs).

Lineage: seed → `()`, mutation → `(parent,)`, crossover → `(a, b)` with
`a != b`, every parent step strictly less than the child step and produced
earlier in the same run.

## Test Totals

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/research/test_alpha_factory.py` (full file) | 64 | passed |
| `tests/research/test_alpha_factory.py` (`-k 'digest or seed_pool or prng'`, task 01) | 13 selected | passed |
| `tests/research/test_alpha_factory.py` (`-k 'generation or determinism or replay or mutation or crossover or lineage'`, task 02) | 19 selected | passed |

## Verification Commands (all green)

```
cd backend && pytest tests/research/test_alpha_factory.py -k 'digest or seed_pool or prng' -q
→ 13 passed, 33 deselected

cd backend && pytest tests/research/test_alpha_factory.py -k 'generation or determinism or replay or mutation or crossover or lineage' -q
→ 19 passed, 45 deselected

cd backend && pytest tests/research/test_alpha_factory.py -q
→ 64 passed
```

The plan's `<verification>` notes the candidate-attempt and lineage persistence
paths are exercised end-to-end in plan 46-04; this plan proves determinism at the
factory boundary (in-memory replay). The full backend suite was not run, per the
plan.

## Must-Have Truths (verified)

- ✅ All nondeterministic generation draws come from a single
  `random.Random(snapshot.seed)` instance; the global `random` module is never
  used, so the draw sequence is reproducible from the frozen seed alone
  (`TestPRNGIsolation`).
- ✅ Replaying the same frozen snapshot, seed, and grammar produces byte-identical
  canonical expressions, candidate digests, operation labels, parent/step
  lineage, and attempt-ordinal order, independent of wall-clock or worker timing
  (`TestFullReplayDeterminism`, `TestWorkerTimingIndependence`).
- ✅ A candidate digest equals SHA-256 over the canonical JSON of
  `{canonical_expression, vocab_version, seed, step, operation}`, so two
  structurally identical expressions from different steps get distinct digests
  while the same frozen inputs always reproduce the same digest sequence
  (`TestCandidateDigest`, `TestFullReplayDeterminism`).
- ✅ Mutation children carry exactly one parent step and crossover children carry
  exactly two distinct parent steps, all strictly preceding the child; seed
  candidates carry none (`TestLineageInvariants`).

## Threat Model Mitigations

- **T-46-04 (Tampering — PRNG source):** a single instance-local
  `random.Random(seed)` drives every draw; the global `random` module is never
  drawn from (static guard test). The draw sequence is host-state-free and
  reproducible from the seed.
- **T-46-05 (Repudiation/Tampering — candidate ordering):** steps are assigned in
  generation order (`attempt_ordinal = step + 1`); the generator is
  single-threaded per run, so replay reproduces the same ordinal → expression
  mapping regardless of when workers persist (`UNIQUE(run_id, attempt_ordinal)`
  in Phase 45 prevents collision).
- **T-46-06 (Tampering — crossover type compatibility):** every mutation /
  crossover output is re-canonicalized through `factor_dsl.canonicalize`
  (type-tagged positions, single validator); structurally incompatible grafts
  retry and surface at the plan-46-03 validation boundary, never silently dropped.

## Deviations

1. **Seed-pool window set (O3):** O3 specifies "rolling_mean variants over a
   field with legal windows" without pinning the windows. This plan freezes a
   small canonical set `(5, 20, 60)` — every value a legal integer in
   `[1, 252]` — so each seed canonicalizes by construction and the pool size is a
   stable function of the vocabulary. The exact window tuple is part of the
   determinism contract (frozen in source, asserted by enumeration-order tests);
   changing it is a new frozen run, not a silent mutation.
2. **Mutation/crossover wave split:** the remaining budget (after the seed pool)
   is split evenly — first half mutation, second half crossover. The split
   depends on the frozen budget (part of the spec), so `replay_to` preserves the
   budget to reproduce the exact dispatch. This matches the research pipeline
   ("Wave 2 mutation → Wave 3 crossover") and gives clean lineage assertions.
3. **Validity handling:** because the generator builds legal DSL nodes and uses
   only non-zero, finite, in-range literals, every output canonicalizes except
   the rare clip-bound-ordering case after a graft/literal mutation. Such
   products retry within a bounded budget (16 attempts) and fall back to a
   guaranteed-valid operation, so termination and the "every output canonicalizes"
   acceptance always hold here. Full rejection-as-`invalid` remains plan 46-03.
4. **Pre-existing WIP isolation (concurrent collaboration):** the working tree
   carries ~37 unstaged frontend files (components, e2e specs) plus unstaged
   Phase-45 backend hardening (`run_contract.py`, `repository.py`,
   `run_service.py`, `run_worker.py`, `migrations.py`, `main.py`,
   `research_alpha.py`) from user/sibling work — **not** `frontend/src/pages/Watchlist.tsx`,
   which was zero-touch. Every 46-02 commit used explicit `git add` of only
   `backend/app/research/alpha_factory.py` and
   `backend/tests/research/test_alpha_factory.py`; no frontend or sibling-backend
   file entered a 46-02 commit. `frontend/src/pages/Watchlist.tsx` was never read
   or modified.

## Handoff (downstream plans)

- **Plan 46-03 (validation/diagnostics):** wrap each `GenerationResult` in
  `validate_candidate` → `ValidationResult` (valid / `invalid` with a structured
  `{diagnostic, location, dsl_version, vocab_version, raw_expression}` payload);
  add `measure_complexity` for the depth/node limits the DSL does not enforce.
- **Plan 46-04 (budget + diversity + worker persistence):** drive the factory from
  the token-fenced worker adapter, mapping `step → attempt_ordinal`,
  `parent_steps → candidate IDs` against
  `repository.append_candidate_attempt` / `append_candidate_lineage`, enforce
  server-side budgets, and record structural similarity (no silent merge).

## Files Modified/Created

| File | Action |
|------|--------|
| `backend/app/research/alpha_factory.py` | Extended (candidate_digest, GenerationResult, AlphaFactory, AST helpers) |
| `backend/tests/research/test_alpha_factory.py` | Extended (+36 tests; 64 total) |
| `.planning/phases/46-deterministic-alpha-factory/46-02-SUMMARY.md` | Created (this file) |
