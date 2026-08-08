---
phase: 46
slug: deterministic-alpha-factory
type: plan-check
created: 2026-08-08
verdict: PASS
blockers: 0
warnings: 3
---

# Phase 46 — Plan Check (Goal-Backward Verification)

> Goal-backward verification of plans 46-01/02/03/04 against AF-REQ-02, AF-REQ-03,
> AF-REQ-19, AF-REQ-23. Each requirement is traced to a plan and task; each plan's
> key engineering claims are checked against the live `factor_dsl.py` /
> `run_contract.py` / `factor_registry.py` source.

---

## Verdict

**PASS — 0 blockers, 3 warnings.** All four AF-REQs map to at least one plan+task,
every plan reuses the existing DSL / canonicalization / repository / Jaccard seams
(no second expression engine, no evaluator, no provider, no PyTorch/RL), the wave
graph is acyclic and topologically sound, and the non-goals are respected. Warnings
are documentation/orchestration hygiene, not correctness defects.

---

## Goal-Backward Findings

### 1. Test file name
`backend/tests/research/test_alpha_factory.py` does **not** exist today (verified:
the `tests/research/` dir holds `test_run_contract.py`, `test_factor_dsl.py`, etc.,
but no `test_alpha_factory.py`). All four plans create it. **No collision** with
`test_run_contract.py` or any sibling. The 46-01 verify step additionally re-runs
`test_run_contract.py -k 'manifest or freeze or digest or idempotent'` to prove the
Phase 45 freeze contract is untouched.

### 2. Vocabulary fingerprint (46-01)
`vocabulary_fingerprint()` is computed from the **live** `factor_dsl` module
(`ALLOWED_FIELDS`, `DENIED_FIELDS`, `_FUNCTION_ARITY`, `_FUNCTION_PARTITION`,
`DSL_VERSION`, `MAX_ROLLING_WINDOW`), not hardcoded — so the digest tracks the real
grammar. `verify_vocabulary_fingerprint` recomputes from the live DSL and raises
`VocabularyMismatchError` on any mismatch; the fail-closed path is explicit.
`normalize_manifest_fingerprints` is wired into `freeze_input_snapshot` between the
canonical copy (run_contract.py:239) and the `component_digests` block (run_contract.py:243),
after `validate_manifest`, overriding any client-supplied value — a forged slot
cannot survive freeze (T-46-01).

### 3. Determinism & seed isolation (46-02)
The plan uses a **single instance-local** `random.Random(seed)`, never the global
`random.seed()` / module-level draws (truth #1 + acceptance: "no `random.*`
module-level calls exist in the generation path"). This is the correct isolation
pattern: instance-local state cannot leak between tests. Candidate digest =
`digest_bytes({expression, vocab_version, seed, step, operation})` over `canonical_json`
(sorted keys) → stable and provenance-encoding (two same-expression/different-step
candidates get distinct digests). Replay is tested by **two independent factory
instances over identical frozen inputs producing byte-identical expression / digest /
operation / parent_steps sequences** (Tasks 46-02-01/02) — the AF-REQ-02 SC2 contract.

### 4. Validation / AF-REQ-03 rejection modes (46-03)
Every AF-REQ-03 failure mode is raised by the existing validator
(factor_dsl.py:335-377) and converted to an explicit `invalid` `ValidationResult` with a
structured payload `{diagnostic, location, dsl_version, vocab_version, raw_expression}`
(research §4; maps to `reason_json`). Modes covered: denied field (337-338), unknown
field (339-340), unknown function (365), invalid arity (365), partition semantics
(312-317, 367-372), excessive window (325-328), non-finite literal (345-346), division
by literal zero (361-362), reversed clip bounds (321-322), malformed syntax (208, 233-237,
283-291), unsupported operator (352-353, 357-358) — **plus** the two the DSL does not
enforce today (excessive depth, excessive node count via `measure_complexity`). No gap.

### 5. Budgets + diversity (46-04)
Server-side budget enforcement lives in `BudgetGuard` at the **top of each step** inside
`drive_alpha_generation` (alpha_factory.py loop), checking candidate-count, wall-clock
(`time.monotonic`), and expression-count before generating; exhaustion records a
`budget_exhausted` candidate and requests `completed` (not `failed`). Persistence is
token/version-fenced through `run_worker` → `run_service` (T-46-10). Diversity reuses
`_jaccard` **imported from `factor_registry`** (factor_registry.py:115-117) — confirmed,
no re-implementation. Parallel-invariance is tested by asserting identical
ordinals/expressions/digests/statuses and ordinal-order replay independent of append
timing (Task 46-04-03 acceptance).

### 6. Wave dependencies & parallel safety
Acyclic, sound: 46-01 → wave1 (dep `[]`); 46-02 → wave2 (dep `[46-01]`);
46-03 → wave3 (dep `[46-02]`); 46-04 → wave3 (dep `[46-02]`). All `requirements:`
frontmatter matches the goal (verified programmatically). Verify commands are
syntactically valid (`cd backend && pytest … -k '…' -q`; the `&amp;&amp;` is XML entity
encoding). 46-03 and 46-04 are wave-3 siblings that both edit `alpha_factory.py` +
`test_alpha_factory.py`; ownership is partitioned by a shared contract (46-03 owns
`validate_candidate`/`ValidationResult`/`measure_complexity`/`invalid_reason`; 46-04
imports them and owns budget/diversity/loop) and their `-k` filters are disjoint, so
pytest selection cannot collide.

### 7. Non-goals respected
No factor computation (AST build + `canonicalize` only, no Polars eval), no fold/OOS
scoring, no Agent (AF-REQ-11..14 untouched), no provider calls, no PyTorch/RL
(`random.Random(seed)`; explicit "NOT RL"). Import guards (T-46-03/T-46-14) restrict
`alpha_factory.py` to `factor_dsl` + `run_contract` (+ `factor_registry` in 46-04 for
`_jaccard`), proven by a static guard test. `low_coverage`/`admitted`/`rejected`/`failed`
correctly deferred to Phase 47; only the additive `generated` status is added.

---

## Warnings

| # | Severity | Plan | Issue | Resolution |
|---|----------|------|-------|-----------|
| W1 | low | 46-01 (truth #1), RESEARCH §1 | Narrative states **44** allowed fields; the live `ALLOWED_FIELDS` (factor_dsl.py:27-36) has **46** (verified by count). Cosmetic only — the fingerprint reads `sorted(ALLOWED_FIELDS)` from the live module, so it correctly digests 46 fields. | Update the "44" to "46" in the 46-01 truth and RESEARCH §1 table to match source; no code change. |
| W2 | low | 46-01 (Task 46-01-01) | The binary/unary operator lists (`["+","-","*","/"]`, `["-"]`) are **hardcoded literals** in `vocabulary_fingerprint` because the DSL exposes operators only inline in `_validate_expression` (factor_dsl.py:352,357), not as named constants. A future operator added to the validator without updating the fingerprint literal would not change the digest. | Acceptable (operators are extremely stable); optionally hoist them to a module-level constant so the fingerprint and validator share one source. |
| W3 | medium | 46-04 (`depends_on`, shared_contract) | 46-04 declares `depends_on: [46-02]` but functionally **imports** 46-03's `validate_candidate`/`ValidationResult`/`measure_complexity`/`invalid_reason`. Under strict-parallel wave-3 dispatch, 46-04's worker-loop tests reference undefined names until 46-03 lands. The shared contract anticipates this ("if executed before 46-03 lands"). | Ensure the executor merges 46-03's `alpha_factory.py` additions before running 46-04's `budget/worker/replay` verification (the executor's same-wave file auto-resolve handles this), or add `46-03` to 46-04's `depends_on` for a strict topological executor. |

---

## AF-REQ Coverage Matrix

| AF-REQ | Sub-criterion | Plan(s) | Task(s) | Verdict |
|--------|---------------|---------|---------|---------|
| AF-REQ-02 | SC1 — versioned vocab/grammar fingerprint, server-populated, fail-closed | 46-01 | 46-01-01, 46-01-02 | PASS |
| AF-REQ-02 | SC2 — replay determinism (expressions, digests, order, lineage) | 46-02 | 46-02-01, 46-02-02 | PASS |
| AF-REQ-03 | SC3 — validate before evaluate; all rejection modes → `invalid` + diagnostics | 46-03 | 46-03-01, 46-03-02 | PASS |
| AF-REQ-19 | SC4 — structural similarity recorded, no silent merge | 46-04 | 46-04-02 | PASS |
| AF-REQ-23 | SC4 — server-side budgets; parallelism cannot change order/replay | 46-04 | 46-04-03 (+46-04-01 migration) | PASS (W3) |

---

## Notes

- `canonical_json` (run_contract.py:68) and `digest_bytes` (run_contract.py:134) are
  reused for both the vocabulary fingerprint and the candidate digest; the plan's
  read-first citation "run_contract.py:61-72 — canonical_json / digest_bytes" is slightly
  imprecise (`digest_bytes` lives at :134) — cosmetic, functions exist and are reused correctly.
- `validate_manifest` runs on the original manifest before the canonical copy, so the
  placeholder `"a"*64`/`"b"*64` slots pass `validate_sha256` and are then overwritten by
  `normalize_manifest_fingerprints` — the existing Phase 45 freeze/idempotency tests
  assert structural equality + 64-length, so server-side population does not break them.
- IC-series correlation is correctly deferred to Phase 47 (requires evaluation);
  Phase 46 records field/operator Jaccard + structural/shape signatures only.
