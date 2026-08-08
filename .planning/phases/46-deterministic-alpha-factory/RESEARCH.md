# Phase 46: Deterministic Alpha Factory Core - Research

**Researched:** 2026-08-08
**Domain:** Deterministic, replay-stable candidate generation over the existing Factor DSL
**Confidence:** HIGH for DSL/vocabulary, canonicalization, and Phase 45 repository seams; MEDIUM for generation pipeline decomposition and budget enforcement boundaries

## Summary

Phase 46 is a **deterministic expression-generation engine**, not an RL search. Given a frozen run snapshot, seed, grammar, and budget, it must emit a bounded, canonical, fully accounted candidate population whose expressions, IDs, lineage, and ordering are reproducible independent of worker timing. The existing `factor_dsl.py` already provides a complete restricted grammar (44 fields, 7 functions with declared arity and partition semantics, 4 binary + 1 unary operator, AST types, a `canonicalize()` serializer, and a `parse_factor()` validator), and `factor_registry.py` already provides Jaccard-based structural similarity. Phase 45 already provides append-only candidate/lineage/event tables, a token-fenced worker adapter, server-side budget counter columns, and a `budget_exhausted` candidate status. Phase 46's job is to wire a seeded deterministic generator into these seams — populating the `vocabulary.fingerprint` and `grammar.fingerprint` manifest slots with real DSL-derived digests, generating expressions in canonical form with stable candidate digests, recording invalid candidates with diagnostics, computing structural diversity, and enforcing budgets server-side.

**Primary recommendation:** add one new module `backend/app/research/alpha_factory.py` (the deterministic generator + vocabulary fingerprint) plus service-level budget enforcement, consuming the Phase 45 `append_candidate_attempt` + `append_candidate_lineage` repository methods. No new dependencies, no evaluator, no provider, no OOS, no admission. The generator uses `random.Random(seed)` for all nondeterministic choices, produces one candidate per step (one `attempt_ordinal`), and writes each candidate as an atomic fact before the next step.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AF-REQ-02 | Given the same frozen specification, seed, and governed input manifest, a replay produces the same canonical candidate expressions, candidate IDs/digests, order, statuses, and checksums. | Versioned vocabulary fingerprint from live DSL constants, deterministic `random.Random(seed)` generator, canonical expression form via existing `canonicalize()`, candidate digest = `sha256(canonical_expression + seed + step + vocab_version)`, server-side ordinal allocation. |
| AF-REQ-03 | Every generated expression is parsed and validated before evaluation; unsupported fields/functions/operators, invalid arity or partition semantics, excessive depth/window, non-finite literals, and malformed expressions become explicit invalid candidate records with diagnostics. | Existing `parse_factor()` + `_validate_expression()` rejects all listed failure modes; Phase 46 catches `FactorDslError` and records `invalid` status with `{diagnostic, location, vocab_version}` reason payload. |
| AF-REQ-19 | Search results show objective score with structural similarity, field/operator overlap, factor-output/IC-series correlation, coverage, and diversity outcomes; similar candidates remain inspectable. | Phase 46 records structural similarity only (Jaccard on field sets + operator/function sets via existing `_jaccard()` + `extract_features()`); IC-series correlation is Phase 47 (requires evaluation). No silent merging. |
| AF-REQ-23 | Candidate, wall-clock, memory, provider-call, retry, artifact, and worker budgets are enforced server-side; parallel workers cannot change candidate order, score reduction, winner, or replay result. | Server-side budget counters already in run schema (`candidate_attempts_total`); Phase 46 adds wall-clock/memory/candidate-count enforcement in the generation loop; deterministic ordering via `attempt_ordinal`; `budget_exhausted` status already exists. |

## 1. Grammar and Vocabulary (AF-REQ-02 SC1)

### Existing DSL inventory

The restricted Factor DSL in `factor_dsl.py` is the single legal grammar for Phase 46 expressions — no StackVM, no second engine (`[VERIFIED: factor_dsl.py:1-5]`).

**Versioned components** (`[VERIFIED: factor_dsl.py:17-69]`):

| Component | Value | Evidence |
|-----------|-------|----------|
| DSL version | `"factor-dsl-v2"` | `factor_dsl.py:17` |
| Max rolling window | `252` | `factor_dsl.py:18` |
| Allowed fields | 44 governed numeric columns (`open`..`rsi_24`) | `factor_dsl.py:27-36` |
| Denied fields | 8 label/identity columns (`date`, `symbol`, `label`, `forward_return`, ...) | `factor_dsl.py:41-44` |
| Functions + arity | `abs:1`, `sign:1`, `log1p:1`, `clip:3`, `rank:1`, `zscore:1`, `rolling_mean:2` | `factor_dsl.py:46-54` |
| Partition semantics | `pointwise`, `per_date` (rank, zscore), `per_symbol` (rolling_mean) | `factor_dsl.py:61-69` |
| Binary operators | `+`, `-`, `*`, `/` | `factor_dsl.py:357` |
| Unary operator | `-` (negation) | `factor_dsl.py:352` |
| AST node types | `Number`, `Field`, `Unary`, `Binary`, `Call` | `factor_dsl.py:135` |

The grammar is self-consistent by construction: `_FUNCTION_ARITY` and `_FUNCTION_PARTITION` are tested for key-set equality (documented in `factor_dsl.py:58-60`), so adding a function without its partition context is a test failure.

### Versioned vocabulary fingerprint design

Phase 45 already reserves two manifest slots — `grammar.fingerprint` and `vocabulary.fingerprint` — both stored as `CHECK(length(...) = 64)` SHA-256 columns (`[VERIFIED: run_contract.py:46-58; migrations.py:1880-1881]`). Test manifests currently use placeholder `"a" * 64` (`[VERIFIED: test_run_contract.py:32-33]`). Phase 46 must populate these from live DSL constants.

**Recommended vocabulary fingerprint** (computed from the live DSL at freeze time):

```python
def vocabulary_fingerprint() -> str:
    """Deterministic SHA-256 over the complete restricted vocabulary.

    Any change to fields, operators, functions, arity, partition semantics,
    windows, or complexity limits changes the fingerprint, making stored
    expressions fail-closed on vocab mismatch (AlphaMaster FORMULA_VOCAB.verify()
    pattern adapted for the existing DSL, not StackVM).
    """
    from app.research.factor_dsl import (
        ALLOWED_FIELDS, DENIED_FIELDS, _FUNCTION_ARITY, _FUNCTION_PARTITION,
        DSL_VERSION, MAX_ROLLING_WINDOW,
    )
    return digest_bytes({
        "dsl_version": DSL_VERSION,
        "fields": sorted(ALLOWED_FIELDS),
        "denied_fields": sorted(DENIED_FIELDS),
        "binary_operators": ["+", "-", "*", "/"],
        "unary_operators": ["-"],
        "functions": dict(sorted(_FUNCTION_ARITY.items())),
        "partition_semantics": dict(sorted(_FUNCTION_PARTITION.items())),
        "max_rolling_window": MAX_ROLLING_WINDOW,
    })
```

The `grammar.fingerprint` should cover expression-level structural constraints (max AST depth, max node count, canonical form rules). Phase 45's `freeze_input_snapshot` computes these digests via `_component_digest(manifest, "vocabulary", key="fingerprint")` (`[VERIFIED: run_contract.py:159-160]`), so the manifest's `vocabulary.fingerprint` and `grammar.fingerprint` keys must match these computed values.

**Fail-closed verification on replay/load:** When replaying or loading a stored run, recompute the vocabulary fingerprint from the live DSL and compare against the stored `vocabulary_fingerprint` column. A mismatch (e.g. a field was added or a function arity changed) means stored canonical expressions may reference tokens the live grammar interprets differently — the run must fail closed rather than reinterpreting tokens (`[VERIFIED: docs/v3-roadmap.md:55,212]` — AlphaMaster's `FORMULA_VOCAB.verify()` rejects inconsistent versions).

### Expression canonicalization

The DSL already provides `canonicalize(expression)` (`[VERIFIED: factor_dsl.py:392-415]`) which serializes the validated AST without harmless whitespace or redundant parentheses, using precedence-aware parenthesization. `parse_factor()` calls it to produce `ParsedFactor.canonical_expression` (`[VERIFIED: factor_dsl.py:504-506]`).

**Gap: commutative operand order.** The current `canonicalize()` does **not** sort operands of commutative operators (`+`, `*`). This means `close + open` and `open + close` produce different canonical strings and different `structural_signature` digests. For Phase 46 determinism, this is acceptable as-is: the generator produces one canonical form per step deterministically, and duplicates are intentionally retained as `duplicate` status records (`[VERIFIED: run_contract.py:232; repository.py:2000-2004]`). However, if Phase 46 wants exact-structural-duplicate detection to catch algebraically equivalent expressions, it should add an optional commutative-normalization pass that sorts `Binary(+, a, b)` and `Binary(*, a, b)` children by their serialized form before computing signatures. **Recommendation: do NOT add algebraic normalization in Phase 46** — it risks introducing bugs and the diversity requirement (AF-REQ-19) is satisfied by Jaccard overlap, not algebraic equivalence. Keep `duplicate` detection based on exact `canonical_expression` string equality.

**Complexity limits** (for the grammar fingerprint): the DSL enforces window limits (`MAX_ROLLING_WINDOW`, `factor_dsl.py:18,325`) and division-by-literal-zero (`factor_dsl.py:361-362`) but does **not** enforce a max AST depth or max node count. Phase 46 should add complexity limits at the generation layer (max depth, max nodes) as part of the grammar fingerprint, since they constrain the legal candidate space.

## 2. Deterministic Candidate Generation (AF-REQ-02 SC2)

### Strategy: seeded enumeration + mutation + crossover (NOT RL)

Phase 46 is explicitly a deterministic pipeline — "the default factory is deterministic seeded grammar/evolution" (`[VERIFIED: ROADMAP.md:12; REQUIREMENTS.md:14]`). No PyTorch, no RL, no GPU, no REINFORCE. The AlphaMaster RL patterns (`[VERIFIED: docs/v3-roadmap.md:44,58,186-188]`) are **architectural references only** — their StackVM/ConstrainedSampler/REINFORCE approach is explicitly out of scope.

**Recommended pipeline** (all randomness from `random.Random(seed)`):

```text
frozen snapshot + seed + grammar + budget
      |
      v
random.Random(snapshot.seed)         -- single PRNG, deterministic
      |
      v
Wave 1: seed pool generation         -- enumerate simple expressions
  (single fields, unary fields, rank/zscore of fields, rolling_mean variants)
      |                                each assigned step=0..N-1
      v
Wave 2: mutation                     -- for each parent, apply legal mutations
  (point_mutation, subtree_replacement)
      |                                each child gets parent lineage edge
      v
Wave 3: crossover                    -- pair parents, graft subtrees
      |                                each child gets 2 parent lineage edges
      v
... repeat until budget exhausted or max depth reached
      |
      v
each candidate: validate -> canonicalize -> compute digest -> append_attempt + lineage
```

Every random draw — field selection, operator choice, subtree depth, mutation point, crossover pair — comes from the single seeded `random.Random` instance. Replay with the same seed reproduces the exact draw sequence.

### Candidate IDs and digests

**Candidate digest** must be deterministic and reproducible from the frozen inputs alone:

```python
candidate_digest = sha256(canonical_json({
    "expression": canonical_expression,   # from factor_dsl.canonicalize()
    "vocab_version": vocabulary_fingerprint(),
    "seed": snapshot_seed,
    "step": step,
    "operation": operation,  # "seed", "mutate", "crossover"
}))
```

This ensures: (a) same frozen snapshot + seed + grammar → same digest sequence; (b) the digest encodes provenance (seed/step/operation) so two structurally identical expressions from different steps get different digests (matching the one-row-per-attempt model, `[VERIFIED: repository.py:1998-2004]`).

The `ast_signature` and `shape_signature` columns should reuse `extract_features().structural_signature` and `.shape_signature` (`[VERIFIED: factor_dsl.py:466-468]`) — these are SHA-256 over the AST payload (full and shape-only respectively), already used by `factor_registry.py` for similarity (`[VERIFIED: factor_registry.py:161-162]`).

### Ordering stability

Candidate order is governed by `attempt_ordinal` — a positive integer with `UNIQUE(run_id, attempt_ordinal)` (`[VERIFIED: migrations.py:1948,1964`). The generator assigns ordinals in step order: step 0 → ordinal 1, step 1 → ordinal 2, etc. Because the PRNG sequence is deterministic and ordinals are assigned in generation order, replay reproduces the same ordinal → expression mapping regardless of worker timing.

Phase 45's `BEGIN IMMEDIATE` sequence allocation (`[VERIFIED: repository.py:1624]`) ensures two workers cannot claim the same ordinal. But **Phase 46's determinism contract is stronger**: the generator itself is single-threaded within one worker run. Parallel workers improve throughput across *different runs*, not within one run's candidate sequence. A single run's generation loop is sequential by design — the worker generates candidate N+1 only after candidate N's append commits.

## 3. Mutation and Crossover Operations (AF-REQ-18, AF-REQ-04)

### Legal operations

All operations are constrained to produce valid DSL expressions — every output is re-parsed via `parse_factor()` before it enters the candidate ledger. An operation that produces an invalid expression is recorded as an `invalid` candidate (consuming budget), not silently dropped.

| Operation | Description | Lineage edge(s) |
|-----------|-------------|-----------------|
| `seed` | Generate a new expression from scratch (field, unary, single function call, or small binary tree) | 0 parents |
| `point_mutation_field` | Replace one `Field` node with another allowed field | 1 parent |
| `point_mutation_operator` | Replace one binary operator with another (`+`↔`-`, `*`↔`/`) | 1 parent |
| `point_mutation_literal` | Replace or perturb a `Number` literal | 1 parent |
| `subtree_replacement` | Replace a subtree with a newly generated valid subtree | 1 parent |
| `crossover` | Graft a subtree from parent B into parent A at a compatible type position | 2 parents |

### Grammar constraint enforcement

The generator builds AST nodes directly (`Number`, `Field`, `Unary`, `Binary`, `Call`) and then validates via `parse_factor(canonicalize(ast))` or `_validate_expression(ast)`. This guarantees:
- Fields are always from `ALLOWED_FIELDS` (`factor_dsl.py:339-340`)
- Denied fields are never produced (`factor_dsl.py:337-338`)
- Functions always have correct arity (`factor_dsl.py:365`)
- Partition context is always declared (`factor_dsl.py:367-372`)
- `rolling_mean` windows are always `[1, 252]` integers (`factor_dsl.py:324-328`)
- `clip` bounds are always `low <= high` (`factor_dsl.py:321-322`)
- Division by literal zero is rejected (`factor_dsl.py:361-362`)

### Lineage recording

Phase 45 already provides `append_candidate_lineage(run_id, child_attempt_id, parent_attempt_id, edge_ordinal, operation)` (`[VERIFIED: repository.py:2053-2110]`) with same-run FK validation. A crossover child gets two lineage edges (edge_ordinal 0 and 1). The `operation` column records the mutation type string. A seed candidate has zero lineage edges. The schema enforces `UNIQUE(child_attempt_id, parent_attempt_id)` (`[VERIFIED: migrations.py:1980]`), so a child can have at most one edge to each parent.

## 4. Validation Before Evaluation (AF-REQ-03 SC3)

### What `parse_factor` rejects today

The existing validator covers every AF-REQ-03 failure mode (`[VERIFIED: factor_dsl.py:343-377]`):

| Failure mode | Detection | Evidence |
|-------------|-----------|----------|
| Unsupported/denied field | `_validate_field_name`: denied set check, then allowed set check | `factor_dsl.py:335-340` |
| Unknown function | `_call`: function not in `_FUNCTION_ARITY` | `factor_dsl.py:282-283` |
| Invalid arity | `_call`: argument count != declared arity | `factor_dsl.py:292-297,365` |
| Missing partition semantics | `_validate_call`: function not in `_FUNCTION_PARTITION` | `factor_dsl.py:312-317,367-372` |
| Excessive window | `_validate_call`: `rolling_mean` window not in `[1, 252]` | `factor_dsl.py:323-328` |
| Non-finite literal | `_validate_expression`: `math.isfinite` check | `factor_dsl.py:345-346` |
| Division by literal zero | `_validate_expression`: `_is_zero_literal` check | `factor_dsl.py:361-362` |
| clip bounds reversed | `_validate_call`: `low > high` | `factor_dsl.py:321-322` |
| Malformed syntax | Tokenizer/parser: unexpected character, empty, unbalanced parens | `factor_dsl.py:208,233-237,277,283-291` |
| Unsupported operator | `_validate_expression`: operator not in `{-,+,*,/}` | `factor_dsl.py:357-358` |

### What's missing (Phase 46 adds)

The DSL validator does **not** enforce a max AST depth or max node count. Phase 46's generator must enforce these as complexity limits (part of the grammar fingerprint), rejecting candidates that exceed `max_depth` or `max_nodes` as `invalid` with a diagnostic like `"expression depth 8 exceeds max_depth 6"`.

### Invalid candidate diagnostic payload

When `FactorDslError` is raised, it carries `diagnostic.message` and `diagnostic.location` (line, column) (`[VERIFIED: factor_dsl.py:85-98]`). Phase 46 should structure the `reason` JSON on the `invalid` candidate attempt as:

```python
{
    "diagnostic": str(error.diagnostic.message),
    "location": error.diagnostic.location.display(),  # "line N, column M"
    "dsl_version": DSL_VERSION,
    "vocab_version": vocabulary_fingerprint(),
    "raw_expression": canonical_expression,  # the rejected expression text
}
```

This maps directly to the `reason_json` column (`[VERIFIED: migrations.py:1961]`). Invalid candidates consume the declared trial budget — they are durable facts, not suppressed (`[VERIFIED: REQUIREMENTS.md:27; repository.py:2000-2004]`).

## 5. Diversity and Redundancy (AF-REQ-19 SC4)

### Structural similarity only in Phase 46

AF-REQ-19 requires "objective score together with structural similarity, field/operator overlap, factor-output/IC-series correlation." IC-series correlation requires **evaluation** (Phase 47, AF-REQ-05/07), which is an explicit Phase 46 non-goal. Therefore Phase 46 records **structural similarity only**; IC-series correlation is deferred to Phase 47.

### Reuse existing similarity machinery

`factor_registry.py` already provides Jaccard-based structural similarity (`[VERIFIED: factor_registry.py:115-117,246-296]`):

- `_jaccard(left, right)` — intersection over union on field/operator sets
- `SimilarityCandidate` — `exact_structural_match`, `shape_match`, `field_overlap`, `operator_function_overlap` (`[VERIFIED: factor_registry.py:71-79]`)
- `extract_features()` produces `FactorFeatures` with `fields`, `operators`, `functions`, `partition_context` (`[VERIFIED: factor_dsl.py:443-473]`)

Phase 46 should compute pairwise diversity for each new candidate against the existing population within the same run:

| Metric | Computation | Phase |
|--------|------------|-------|
| Field overlap (Jaccard) | `_jaccard(candidate.features.fields, other.features.fields)` | 46 |
| Operator/function overlap (Jaccard) | `_jaccard(candidate.operator_function_set, other.operator_function_set)` | 46 |
| Structural signature exact match | `candidate.ast_signature == other.ast_signature` → `duplicate` | 46 |
| Shape signature match | `candidate.shape_signature == other.shape_signature` | 46 |
| Factor-output/IC-series correlation | Pearson on per-date IC series | **47** (requires evaluation) |

These metrics are stored in the candidate's `reason` JSON (or a bounded diversity summary), **not** used to silently merge or drop candidates. AF-REQ-19 explicitly states "similar candidates remain inspectable rather than being silently merged" (`[VERIFIED: REQUIREMENTS.md:55]`). Exact structural duplicates get `duplicate` status but are retained as separate attempt rows (`[VERIFIED: repository.py:2000-2004]`).

### Admission boundary

Phase 46 must **not** pre-admit candidates. The existing admission policy (`admission.py`) has `MAX_SIMILARITY_SCORE = 0.80` and `MAX_IC_CORRELATION = 0.90` (`[VERIFIED: admission.py:44-45]`) as thresholds, but those are Phase 47 admission gates — Phase 46 only records the metrics beside candidates, it does not apply thresholds. Candidate status in Phase 46 is limited to `invalid`, `duplicate`, `low_coverage` (informational, no evaluation), `cancelled`, and `budget_exhausted`. The `admitted`/`rejected`/`failed` statuses require evaluation and are Phase 47's responsibility.

## 6. Budget Enforcement (AF-REQ-23 SC4)

### Budget dimensions

The manifest's `budgets` group (`[VERIFIED: test_run_contract.py:35]`) carries `max_expressions` and `max_candidates`. Phase 46 should extend this with wall-clock and memory bounds, all enforced server-side.

| Budget | Enforcement point | Exhausted action |
|--------|-------------------|------------------|
| Candidate count | Generator loop counter vs `budgets.max_candidates` | Stop generation; remaining budget → run `completed` |
| Expression count | Unique expression counter vs `budgets.max_expressions` | Stop generating new expressions; mutations of existing ones continue until candidate budget |
| Wall-clock | `time.monotonic()` check at each step boundary vs declared `budgets.max_wallclock_seconds` | Transition to `completed` with `terminal_reason="wallclock_budget_exhausted"` |
| Memory | Bounded AST depth/node count + bounded population frontier (no unbounded accumulation) | Structural; no runtime check needed if frontier is bounded |
| Artifact | Reuse Phase 45 artifact service for large payloads; inline checkpoint ≤16 KiB (`[VERIFIED: run_contract.py:227]`) | Fail closed on artifact write failure |
| Worker | Token/version fence already in place (`[VERIFIED: run_worker.py:59-70,88-98]`) | Invalid token → no side effect |

### Budget-exhausted terminal state

When the candidate or wall-clock budget is reached, the generator records the last candidate with `budget_exhausted` status (`[VERIFIED: run_contract.py:238]`) and the worker requests a `completed` transition. Budget exhaustion is a **normal** terminal outcome — the run is `completed`, not `failed`. The `terminal_reason` records which budget was exhausted.

### Parallelism cannot change winner/order/replay

The determinism contract (AF-REQ-23) is satisfied because:
1. **Order:** candidate ordinals are assigned by the single-threaded generator in step order; `UNIQUE(run_id, attempt_ordinal)` prevents collision (`[VERIFIED: migrations.py:1964]`).
2. **Winner:** Phase 46 does not select a winner — no scoring, no reduction, no champion. That is Phase 47's responsibility.
3. **Replay:** replay reads stored facts in ordinal order (`[VERIFIED: repository.py:2112-2143]`), independent of when workers appended them.

Parallel workers across **different runs** improve throughput; within a single run, generation is sequential by design. The Phase 45 `BEGIN IMMEDIATE` transaction fence (`[VERIFIED: repository.py:1624]`) ensures that even if two workers somehow target the same run, only one ordinal advance succeeds per transaction.

## 7. Worker Integration

### Step boundary: one candidate per step

Phase 45's `append_candidate()` takes one candidate attempt per call (`[VERIFIED: run_service.py:480-524]`). The natural step boundary for Phase 46 is **one candidate per step**: the worker generates one expression, validates it, computes its digest/features/diversity, and appends it as a single atomic fact before generating the next.

This maximizes determinism (each step is independently reproducible), matches the `attempt_ordinal` model, and allows coarse-grained checkpointing (the frontier state = PRNG state + generated expression set + current step) written periodically via `append_checkpoint`.

### Factory plug-in to the worker adapter

```text
Worker (untrusted):
  1. start_or_resume(run_id) → gets attempt_token + transition_version
  2. Factory = AlphaFactory(snapshot, seed, grammar, budget)
  3. for step in range(budget.max_candidates):
       a. expression = Factory.generate_next()          -- deterministic from seed+step
       b. validate: parse_factor(canonicalize(expression.ast))
       c. if invalid: append_candidate(status="invalid", reason=diagnostic)
          else: append_candidate(status="duplicate"|"low_coverage"|..., reason=diversity)
       d. append_candidate_lineage(parents)
       e. worker.report_progress(candidate_attempts_completed=step+1)
       f. check budget/cancel boundaries
  4. worker.request_transition(to_status="completed", terminal_reason="budget_exhausted"|None)
```

The worker adapter (`ResearchRunWorkerAdapter`) is token-fenced and untrusted (`[VERIFIED: run_worker.py:23-108]`). The Factory itself does not call the repository directly — it produces expression/digest/feature tuples, and the worker adapter calls `service.append_candidate()` + `service.append_candidate_lineage()`. The Factory has no policy, evaluator, provider, or execution authority.

### Checkpoint and resume

Phase 45's checkpoint contract (`[VERIFIED: run_contract.py:308-321,324-354]`) supports resume. The Factory's frontier state (PRNG state + step counter + seen-expression set) must be serialized as a bounded checkpoint artifact when it exceeds 16 KiB (`[VERIFIED: run_contract.py:227]`). On resume, the Factory re-seeds from the frozen snapshot, regenerates to the checkpointed step, and continues — guaranteeing identical output. Alternatively (and simpler), since generation is fully deterministic from seed+step, resume can re-derive the frontier from scratch by replaying steps 0..N-1 and continuing at step N, making the checkpoint a pure recovery optimization rather than a correctness requirement.

## 8. Recommended Plan Split

| Plan | Scope | Primary req | Test file | Verify command |
|------|-------|-------------|-----------|----------------|
| **46-01** | Vocabulary fingerprint from live DSL + expression canonicalization validation + fail-closed vocab mismatch on replay | AF-REQ-02 SC1 | `tests/research/test_alpha_factory.py` (vocab + canonicalization cases) | `cd backend && pytest tests/research/test_alpha_factory.py -k 'vocabulary or canonical or fingerprint' -q` |
| **46-02** | Deterministic generation engine: seeded PRNG, seed pool, mutation, crossover, candidate digest/ID computation, ordering stability, replay determinism (same seed → same expressions/order/digests) | AF-REQ-02 SC2 | `tests/research/test_alpha_factory.py` (generation + replay determinism cases) | `cd backend && pytest tests/research/test_alpha_factory.py -k 'generation or determinism or replay or mutation or crossover' -q` |
| **46-03** | Validation + diagnostics: every expression parsed/validated before append, invalid candidates with diagnostic reason, complexity limits (depth/nodes), budget consumption by invalid candidates | AF-REQ-03 SC3 | `tests/research/test_alpha_factory.py` (validation + diagnostic cases) | `cd backend && pytest tests/research/test_alpha_factory.py -k 'validation or invalid or diagnostic or complexity' -q` |
| **46-04** | Budget enforcement (candidate/wall-clock/memory) + structural diversity metrics (Jaccard field/operator overlap, structural signature duplicate detection, no silent merge) + worker integration (step loop, progress reporting, checkpoint, budget_exhausted terminal) | AF-REQ-19, AF-REQ-23 SC4 | `tests/research/test_alpha_factory.py` (budget + diversity + worker cases) | `cd backend && pytest tests/research/test_alpha_factory.py -k 'budget or diversity or worker or checkpoint' -q` |

**Wave structure:** 46-01 is Wave 1 (foundational — vocabulary/canonicalization). 46-02 depends on 46-01 (generation needs the vocabulary fingerprint for candidate digests). 46-03 and 46-04 both depend on 46-02 (validation and budgets apply to generated candidates). 46-03 and 46-04 can run in parallel as Wave 3.

## Architectural Responsibility Map

| Capability | Primary tier | Rationale |
|------------|-------------|-----------|
| Vocabulary fingerprint + grammar versioning | Factory module (new) | Computed from live DSL constants; stored in manifest at freeze time; verified on replay |
| Deterministic expression generation | Factory module (new) | Seeded PRNG, single-threaded per run, produces canonical expressions |
| Validation + canonicalization | Existing `factor_dsl.py` | Reuse `parse_factor()` + `canonicalize()` + `extract_features()` — no new parser |
| Structural diversity | Factory module (new), reuses `factor_registry._jaccard` | Jaccard on field/operator sets; IC correlation deferred to Phase 47 |
| Candidate/lineage persistence | Existing Phase 45 repository | `append_candidate_attempt` + `append_candidate_lineage` — append-only, never deduped |
| Budget enforcement | Factory module + service seam | Server-side counters in generation loop; `budget_exhausted` status |
| Worker orchestration | Existing Phase 45 worker adapter | Token-fenced, untrusted; Factory produces, adapter persists |

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| Expression parsing/validation | New parser, StackVM, Python eval | Existing `factor_dsl.parse_factor()` | Locked boundary: no second expression engine |
| Expression canonicalization | Custom serializer | Existing `factor_dsl.canonicalize()` | Already precedence-aware, stable bytes |
| Structural features | Custom feature extractor | Existing `factor_dsl.extract_features()` | Produces fields/operators/functions/partition_context + signatures |
| Similarity scoring | New similarity metric | Existing `factor_registry._jaccard()` + `discover_similar` pattern | Jaccard on field/operator sets already proven |
| Candidate persistence | New candidate table | Existing `append_candidate_attempt` + `append_candidate_lineage` | Phase 45 append-only schema with FK/unique/trigger guards |
| Worker fencing | New token system | Existing `ResearchRunWorkerAdapter` + `_validate_attempt_token` | Token SHA-256 + transition_version fence already proven |
| Budget counters | New counter columns | Existing `candidate_attempts_total/completed` run columns + progress API | Server-owned, token-fenced progress updates |
| SHA-256 / canonical JSON | Custom hashing | Existing `run_contract.digest_bytes()` / `canonical_json()` | Sorted keys, no whitespace, lowercase hex |

## Common Pitfalls

### Pitfall 1: Non-deterministic PRNG across Python versions

**What goes wrong:** `random.Random(seed)` produces different sequences across Python minor versions or when mixed with `random` module calls.
**How to avoid:** Use a single `random.Random(snapshot.seed)` instance for ALL draws within a run. Never use the global `random` module. Document that replay requires the same Python version. Consider freezing the PRNG algorithm in the grammar fingerprint if cross-version stability is required.

### Pitfall 2: Crossover produces structurally invalid expressions

**What goes wrong:** Grafting a subtree from parent B into parent A at a type-incompatible position (e.g., putting a `Field` where a `Number` literal is expected for `rolling_mean`'s window argument).
**How to avoid:** Type-tag crossover positions (expression-position vs literal-position). Validate every crossover output via `parse_factor(canonicalize(ast))` before appending. Invalid crossovers become `invalid` candidates with diagnostics, consuming budget.

### Pitfall 3: Duplicate detection erases candidates

**What goes wrong:** A duplicate canonical expression is silently dropped, violating complete candidate accounting.
**How to avoid:** Never use `INSERT OR IGNORE` for candidates. Phase 45's `append_candidate_attempt` is explicitly one-row-per-attempt (`[VERIFIED: repository.py:1998-2004]`). Duplicates get `duplicate` status but are retained. The `UNIQUE(run_id, attempt_ordinal)` constraint is on ordinal, not on expression.

### Pitfall 4: Budget enforcement races with generation

**What goes wrong:** A worker generates past the candidate budget before checking.
**How to avoid:** Check budget at the top of each step loop iteration, before generating. The check is: `if step >= budget.max_candidates: record budget_exhausted; break`. Wall-clock is checked via `time.monotonic()` at each step boundary.

### Pitfall 5: Vocab fingerprint computed from client-supplied vocabulary

**What goes wrong:** A client supplies a fake vocabulary fingerprint in the manifest, and stored expressions later fail to validate against the live DSL.
**How to avoid:** The vocabulary fingerprint is computed server-side from live DSL constants at freeze time. The manifest's `vocabulary.fingerprint` must equal `vocabulary_fingerprint()`. Phase 45's `freeze_input_snapshot` already resolves server-owned digests (`[VERIFIED: run_contract.py:140-179]`).

### Pitfall 6: Phase 46 leaks into evaluation/admission

**What goes wrong:** The Factory computes factor values, applies admission thresholds, or calls the signal chain.
**How to avoid:** The Factory imports only `factor_dsl` (parsing/canonicalization/features) and `factor_registry` (Jaccard). It must not import `signal_chain`, `admission`, provider, broker, or evaluation modules. Static import guard + test assertions prove no evaluation path.

## Assumptions Log

| # | Claim | Risk if wrong |
|---|-------|---------------|
| A1 | A single new module `alpha_factory.py` is sufficient decomposition for the generator, vocabulary fingerprint, and budget enforcement. | Planner may split into multiple modules; the non-negotiable contract is reuse of existing DSL + Phase 45 repository. |
| A2 | `random.Random(seed)` is sufficiently stable across Python 3.11+ patch versions for replay within one deployment. | Cross-major-version replay may need a frozen PRNG algorithm (e.g. a custom LCG) — verify deployment constraints. |
| A3 | Candidate digest = `sha256(canonical_expression + seed + step + operation + vocab_version)` is stable and collision-free for the expected population sizes (hundreds to low thousands). | SHA-256 collision probability is negligible; proven for this scale. |
| A4 | Commutative operand normalization is NOT needed in Phase 46 — duplicate detection on exact `canonical_expression` string is sufficient. | Algebraically equivalent duplicates (e.g. `a+b` vs `b+a`) will appear as distinct candidates. Acceptable: they are inspectable and diversity metrics catch the overlap. |
| A5 | The `budgets` manifest group can be extended with `max_wallclock_seconds`, `max_depth`, `max_nodes` without breaking Phase 45 manifest validation. | Phase 45 validates required groups are non-empty but does not constrain sub-keys (`[VERIFIED: run_contract.py:81-93]`), so additive sub-keys are safe. |
| A6 | Structural similarity (Jaccard) is sufficient for AF-REQ-19 in Phase 46; IC-series correlation is explicitly Phase 47. | Confirmed by requirements mapping (`[VERIFIED: REQUIREMENTS.md:55]` mentions IC-series but it requires evaluation = AF-REQ-05/07). |

## Open Questions

| # | Question | Resolution path |
|---|----------|----------------|
| O1 | Should the grammar fingerprint include AST complexity limits (max_depth, max_nodes) or should those be a separate manifest budget field? | Recommend: include in grammar fingerprint (they define the legal expression space), but also enforce as a budget. Planner decides. |
| O2 | Should the Factory's frontier/checkpoint re-derive state from seed+step (replay-based resume) or serialize the PRNG state directly? | Recommend: replay-based resume (re-derive by replaying steps) — simpler, provably deterministic, no PRNG state serialization. The checkpoint is a recovery optimization. |
| O3 | What is the initial seed-pool generation strategy (which expression templates to enumerate first)? | Recommend: start with single fields, then unary fields, then rank/zscore of single fields, then rolling_mean variants, then small binary trees. The exact enumeration order is part of the generator's determinism contract and must be frozen. |
| O4 | Should `low_coverage` status be assigned in Phase 46 (structural: expression references fields known to have low coverage) or only in Phase 47 (measured: actual evaluation coverage)? | Recommend: Phase 47 only. Phase 46 does not have panel data to measure coverage. Phase 46 candidates default to a pending/unevaluated state that Phase 47 resolves. The `low_coverage` status in the Phase 46 schema is available but should not be assigned without evaluation evidence. |

## Sources

### Primary (HIGH confidence)

- `backend/app/research/factor_dsl.py:17-69,135,176-300,303-377,392-473,500-519` — DSL version, fields, functions, arity, partition semantics, tokenizer, parser, validation, canonicalization, features, parse_factor.
- `backend/app/research/factor_registry.py:71-93,115-117,246-296` — SimilarityCandidate, Jaccard, discover_similar, similarity scoring.
- `backend/app/research/admission.py:40-49,63-71,110-331` — Admission policy version, thresholds, gate structure (Phase 47 boundary).
- `backend/app/research/run_contract.py:24-58,61-72,96-179,182-239,254-355` — Manifest schema, canonical JSON/digest, snapshot freeze, candidate statuses, candidate/lineage DTOs, checkpoint checksum, progress counters.
- `backend/app/research/repository.py:1413-1561,1587-1694,1980-2143` — create_alpha_run, transition_alpha_run (BEGIN IMMEDIATE), append_candidate_attempt (one row per attempt), append_candidate_lineage (FK + same-run validation), list_candidates.
- `backend/app/research/run_service.py:130-178,180-223,293-327,329-371,480-524` — transition, start_or_resume (attempt token), _validate_attempt_token, update_progress, append_candidate.
- `backend/app/research/run_worker.py:23-108` — ResearchRunWorkerAdapter: token/version-fenced report_progress and request_transition.
- `backend/app/operational/migrations.py:1862-1987` — Phase 45 schema: input snapshots, runs (guarded cursor), candidate attempts (append-only, status CHECK), candidate lineage (FK, same-run), events.
- `backend/tests/research/test_run_contract.py:28-50` — Sample manifest structure (budgets, objective, universe, fold_geometry).
- `.planning/ROADMAP.md:67-87` — Phase 46 goal, requirements, success criteria, research flag, non-goals.
- `.planning/REQUIREMENTS.md:26-27,55,59,86-107` — AF-REQ-02/03/19/23 full text, traceability.
- `.planning/phases/45-durable-governed-run-contract/45-RESEARCH.md` — Phase 45 foundation (schema, transitions, idempotency, checkpoints, worker contract).
- `docs/v3-roadmap.md:38-60,183-194,211-212` — AlphaMaster vocabulary fingerprint pattern (reference only; StackVM/REINFORCE explicitly out of scope).

### Secondary (MEDIUM confidence)

- `.planning/research/STACK.md` — no-new-dependency constraint, no RL/GPU/queue.
- `.planning/phases/45-durable-governed-run-contract/45-CONTEXT.md:19-36` — locked decisions D-01 through D-12.

## Metadata

**Confidence breakdown:**
- DSL/vocabulary/canonicalization: HIGH — all constants, parser, validator, and serializer inspected with line-level evidence.
- Phase 45 repository/service seams: HIGH — all append/transition/checkpoint methods inspected.
- Generation pipeline design: MEDIUM — the deterministic PRNG + mutation/crossover approach is sound but the exact enumeration order and complexity limits need planner calibration.
- Budget enforcement: MEDIUM — server-side counters exist; exact wall-clock/memory enforcement boundaries need planner decision.

**Research date:** 2026-08-08
**Valid until:** 2026-09-07 for stable DSL/repository contracts; re-check if the Factor DSL vocabulary (fields/functions/operators) changes before planning.
