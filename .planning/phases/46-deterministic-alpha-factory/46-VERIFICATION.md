---
phase: 46-deterministic-alpha-factory
verified: 2026-08-08
status: passed
score: 100
behavior_unverified: []
overrides_applied: []
human_verification: []
---

# Phase 46 — Deterministic Alpha Factory Core — Verification

> Goal-backward, behavior-level verification of the Phase 46 deterministic alpha
> factory. Verifier: independent of the four executor agents. Read-only; only this
> VERIFICATION file was written (and pytest run). `frontend/src/pages/Watchlist.tsx`
> was never read.

## Verdict

**PASSED** — score 100/100. All four Phase 46 requirements (AF-REQ-02, AF-REQ-03,
AF-REQ-19, AF-REQ-23) are satisfied at the behavior level, backed by **377 passing
tests** across the five required suites, corroborated by direct code-level spot
checks (file:line) of the fingerprint authority, generation engine, validation
boundary, diversity accounting, budget guard, and worker driver loop, plus live
runtime cross-checks of replay determinism and the frozen fingerprint values.

All explicit non-goals are respected: no factor computation, no fold/OOS scoring,
no Agent, no provider calls, no PyTorch/RL/GPU, no arbitrary Python, no
broker/execution inside the Phase 46 surface. No human-only items; no overrides.
Working tree has pre-existing unstaged frontend files; `Watchlist.tsx` is **not**
among them and is untouched; no Phase 46 frontend commits exist.

## Test Totals (recorded)

Command (run by verifier):
`cd backend && .venv/bin/python -m pytest tests/research/test_alpha_factory.py tests/research/test_run_contract.py tests/test_operational_migrations.py tests/api/test_run_api.py tests/test_phase45_guard.py -x -q`

```
........................................................................ [ 19%]
........................................................................ [ 38%]
........................................................................ [ 57%]
........................................................................ [ 76%]
........................................................................ [ 95%]
.................                                                        [100%]
377 passed in 42.42s
```

Per-file (collected by verifier):

| Suite | Tests | Status |
|-------|------:|--------|
| `tests/research/test_alpha_factory.py` | 152 | passed |
| `tests/research/test_run_contract.py` | 117 | passed |
| `tests/test_operational_migrations.py` | 20 | passed |
| `tests/api/test_run_api.py` | 64 | passed |
| `tests/test_phase45_guard.py` | 24 | passed |
| **Total (required 5-file batch)** | **377** | **all passed** |

(152 + 117 + 20 = 289 = the executor's claimed integration total; the two
Phase-45-API/guard files add the orchestrator-regression coverage.)

## Requirement-by-Requirement Evidence

| REQ | Phase scope | Status | Evidence (file:line) |
|-----|-------------|--------|----------------------|
| **AF-REQ-02** replay-stable, vocabulary-versioned deterministic generation | 46-01/02 | PASS | **Fingerprint authority:** `vocabulary_fingerprint()` (`alpha_factory.py:43-62`) = `digest_bytes` over the *live* `factor_dsl` constants — `DSL_VERSION`, `sorted(ALLOWED_FIELDS)` (46), `sorted(DENIED_FIELDS)` (8), binary `(+ - * /)` + unary `(-)` operators, `dict(sorted(_FUNCTION_ARITY.items()))` (7 fns: abs/sign/log1p/clip/rank/zscore/rolling_mean), `dict(sorted(_FUNCTION_PARTITION.items()))` (7), `MAX_ROLLING_WINDOW` (252); `grammar_fingerprint()` (`:65-81`) folds `CANONICAL_FORM`/`max_depth`/`max_nodes`/`PRNG_ALGORITHM`. Versioning constants pinned (`:29-33`: `FACTORY_VERSION=alpha-factory-v1`, `PRNG_ALGORITHM=python-random-MT19937-v1`, `CANONICAL_FORM=factor-dsl-canonical-v1`, `DEFAULT_MAX_DEPTH=6`, `DEFAULT_MAX_NODES=40`). **Instance-local PRNG:** `self._rng = random.Random(self._seed)` (`:323`); grep for `random.seed\|random.choice\|random.randrange...` at module level → **no matches** (global `random` never drawn from — single host-state-free stream). **Replay:** `replay_to(k)` (`:349-364`) rebuilds a *fresh* factory from the seed (no serialized PRNG state) and replays; `generate_next()` (`:334-347`) seed-pool → mutation → crossover. **Digest:** `candidate_digest` (`:173-197`) = SHA-256 over canonical JSON `{expression, vocab_version, seed, step, operation}` (step+operation fold ⇒ distinct digests for identical expressions at different steps). **Freeze/verify:** `normalize_manifest_fingerprints` (`:104-124`) overwrites both slots server-side from live DSL (no client-forged value survives); `verify_vocabulary_fingerprint` (`:127-138`) recomputes and raises `VocabularyMismatchError` (`:84`) on mismatch/missing — fail-closed. **Live cross-check (verifier):** `vocabulary_fingerprint() == 90039f5b0f1490840532b62e383e87b606589151e83623309f7078877648b18c`; two independent `AlphaFactory(42)` instances produce byte-identical 60-element streams (canonical/digest/operation/parent_steps); distinct seeds diverge; `replay_to(25)` from a half-consumed factory equals a fresh factory's first 25; `seed_pool_size == 327` (= 4·46 + 3·46 + 5). |
| **AF-REQ-03** every candidate validated through the single DSL before ledger entry; all rejection modes → durable invalid record | 46-03 | PASS | `validate_candidate(ast, *, max_depth, max_nodes)` (`:732-802`) is the single entry point, three gates in order: **complexity gate** first (`measure_complexity` `:660-672`; depth>`max_depth` at `:749`, nodes>`max_nodes` at `:763` — the one mode the DSL does not raise), then **semantic gate** `factor_dsl.canonicalize` (`:778`), then **round-trip gate** `factor_dsl.parse_factor(canonical_expression)` (`:789`) — no second expression engine. `invalid_reason` (`:691-706`) emits the 5-key payload `{diagnostic, location, dsl_version, vocab_version, raw_expression}`; `_dimension_exceeded_reason` (`:709-729`) the complexity variant. **Rejection-mode coverage (all):** parametrized `test_each_rejection_mode_is_invalid` (`test_alpha_factory.py:877-907`) covers denied field, unknown field, unknown function, invalid arity, excessive rolling window, non-finite literal (`1e999`), division by literal zero, reversed clip bounds, malformed syntax, excessive depth, excessive nodes; AST-only `TestAstOnlyRejectionModes` adds missing partition semantics (`:954`), unsupported binary operator (`:963`), unsupported unary operator (`:970`). Never-suppressed + JSON-round-trip (`test_alpha_factory.py:992-1010`): rejections are durable `status="invalid"` `ValidationResult`s, never raised past the boundary or swallowed to `None`; payload serializes to `reason_json`. Complexity gate runs before semantics (over-deep + denied-field AST reports complexity, not the DSL error — `test_complexity_gate_runs_before_semantic_validation`). |
| **AF-REQ-19** structural diversity recorded beside each candidate; similar candidates stay inspectable (no silent merge/drop) | 46-04 | PASS | `diversity_summary(candidate_features, population_features)` (`:878-924`) reports max Jaccard `field_overlap` and `operator_function_overlap`, `exact_structural_match`, `shape_match`, `most_similar_step`, `population_size` — reusing the **single** similarity definition `factor_registry._jaccard` (import `:25`; def `factor_registry.py:115-117`) so there is no second metric. `classify_candidate` (`:927-945`) → `invalid`/`duplicate`/`generated`; `ALPHA_GENERATION_STATUSES` (`:873-875`). **No silent merge:** the driver loop `drive_alpha_generation` calls `adapter.append_candidate` for **every** candidate regardless of status (`:1194-1202`) and appends to `produced` (`:1218`) — a `duplicate` remains its own one-row-per-attempt. IC-series correlation/coverage/admission are explicitly Phase 47's responsibility (`:870-871`, `:938-939`), never computed here. Diversity tests assert hand-computed Jaccard values, exact-duplicate vs generated classification, shape-match-without-exact, and JSON serializability. |
| **AF-REQ-23** server-side budgets (candidate/wall-clock/memory/artifact/worker); exhaustion terminal; parallelism cannot change order/winner/replay | 46-04 | PASS | `BudgetLimits.from_manifest` (`:976-1015`) parses the frozen envelope: `max_candidates` (candidate-count), `max_expressions` (unique-expression/artifact frontier), `max_wallclock_seconds` (wall-clock via `time.monotonic`), and `max_depth`/`max_nodes` (structural memory bound — `:952-953, 967`). `BudgetGuard.exhausted(candidates=)` (`:1047-1065`) is checked at the **top** of each step in precedence: candidate-count (`:1055`), wall-clock (`:1057-1059`), expression-count (`:1060-1064`); `terminal_reason` = `f"{name}_budget_exhausted"` (`:1067-1069`). `drive_alpha_generation` (`:1084-1230`) is the token-fenced driver loop: generate → validate → diversity → persist (candidate+lineage+progress) → repeat; on exhaustion it emits a final `budget_exhausted` candidate (non-candidate budgets, `:1136-1158`) and `request_transition(to_status="completed", terminal_reason=…)` (`:1220-1224`) — **never** `"failed"`. **Worker budget/fence:** every adapter callback requires `attempt_token` and validates via `_validate_attempt_token` — `append_candidate` (`run_worker.py:110-141`), `append_candidate_lineage` (`:143-164`), `report_progress` (`:59-65`), `request_transition` (`:88-99`); missing/stale token → no side effect. **Parallel-invariance:** candidate IDs are globally unique `acand_{run_id}_{digest}` (`:1185`) and the factory is single-threaded deterministic, so concurrent workers cannot change ordinal order, winner, or replay. Driver tests cover candidate/wallclock/expression exhaustion, ordinal order, lineage edges, stale-token fencing, and two-run-same-seed identical streams. |

## Code-Level Spot Checks (verifier)

- **Import discipline / non-goals** (`alpha_factory.py:15-26`): top-level imports are only `random`, `time`, stdlib `collections.abc`/`dataclasses`/`typing`, `factor_dsl`, `factor_registry._jaccard`, `run_contract.digest_bytes`. No Polars, no `torch`/`tensorflow`, no provider/agent/broker/admission/evaluation/fold/OOS module import anywhere in the file. (The `torch` references found by grep live in `forecast/kronos_adapter.py` — an unrelated forecast module, not the Phase 46 surface.)
- **No global PRNG draw** (`alpha_factory.py`): grep for `random.(seed|choice|randrange|random|randint|uniform|sample|shuffle)(` over the file → **no matches**; every nondeterministic draw is `self._rng.…` (instance-local `random.Random(seed)`).
- **Vocabulary fingerprint inputs** (`alpha_factory.py:53-62`): confirmed live — `ALLOWED_FIELDS=46`, `DENIED_FIELDS=8`, `_FUNCTION_ARITY`=7 functions, `_FUNCTION_PARTITION`=7, `MAX_ROLLING_WINDOW=252`, `DSL_VERSION=factor-dsl-v2`. Output `90039f5b…` matches `46-01-SUMMARY.md` exactly.
- **Additive `generated` migration** (`migrations.py:2116-2145`): Phase 46 rebuild of `research_alpha_candidate_attempts` adds `'generated'` to the status CHECK (data-preserving CREATE`_v2`→INSERT→DROP→RENAME; dependent `same_run` trigger dropped/recreated). `CANDIDATE_STATUSES` (`run_contract.py:317-324`) and the Pydantic schema (`run_schemas.py:178-182`) both carry `generated`; `repository.append_candidate` (`repository.py:2228-2230`) validates status against the tuple.

## SUMMARY Claim Cross-Checks (verifier, 3)

1. **46-01 fingerprint values** — SUMMARY states `vocab_fp=90039f5b0f149084…`, `grammar_fp=b95d365a724a3d0a…`. **CONFIRMED** live: recomputed values are byte-identical.
2. **46-02 replay determinism + seed pool = 327** — SUMMARY claims two independent instances produce byte-identical full streams and `seed_pool_size = 4·N + 3·N + 5 = 327` for N=46. **CONFIRMED** live: two-instance stream equality `True`; `seed_pool_size == 327`; `replay_to(25)` from a half-consumed factory matches a fresh factory's prefix.
3. **46-04 test totals** — SUMMARY claims 152 `test_alpha_factory.py` + 20 migrations + 117 `run_contract.py` = 289. **CONFIRMED**: verifier-collected counts are exactly 152 / 20 / 117 = 289.

## Non-Goals Respected (verifier)

| Non-goal | Finding |
|----------|---------|
| No factor computation | PASS — no Polars import; `measure_complexity` is a pure structural walk (`:660-672`); no numeric evaluation. |
| No fold / OOS scoring | PASS — no fold/OOS logic; diversity docstring defers IC-series correlation to Phase 47 (`:870-871`). |
| No Agent | PASS — no langgraph/agent/LLM import or call. |
| No provider calls | PASS — no provider import; `adapter` is a structural sink, concrete type never imported (`:1103-1107`). |
| No PyTorch / RL / GPU | PASS — `alpha_factory.py` has zero torch/RL; factory is a pure-Python AST generator over `factor_dsl`. |
| No arbitrary Python | PASS — only `factor_dsl` AST nodes constructed/edited; canonical text round-trips through `parse_factor`. |
| No broker / execution | PASS — no broker/order/execution import or call. |

## Watchlist Proof (verifier)

- `git status --porcelain`: 65 unstaged frontend files modified; **`frontend/src/pages/Watchlist.tsx` is NOT among them** (modified pages are Auth, Backtest, Dashboard, Data, LimitUpLadder, Monitor, Onboarding, Portfolio, Review, StockAnalysis, plus settings/backtest/data dirs).
- `git log -- frontend/src/pages/Watchlist.tsx`: most recent commit touching it is `96e3c4d` (a pre-existing refactor) — **no Phase 46 commit** touches it.
- `git log` for Phase 46 (`feat(phase-46)`/`fix(phase-46)`/`docs(phase-46)`): all 11 commits are backend-only (`alpha_factory.py`, `test_alpha_factory.py`, `run_contract.py`, `run_service.py`, `run_worker.py`, `migrations.py`, SUMMARY/PLAN docs); **no frontend file** enters any Phase 46 commit.

The unstaged frontend files are pre-existing user/sibling work noted in every Phase 46 SUMMARY; they are unrelated to this phase and were never committed by the Phase 46 executors.

## Human Verification Items

None. All four requirements are verified at the behavior level by passing tests plus
direct code-level and live-runtime evidence. No items deferred to human review.
