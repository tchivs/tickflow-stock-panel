# Phase 46 UAT — Deterministic Alpha Factory Core

**Phase:** 46 · **Requirements:** AF-REQ-02, AF-REQ-03, AF-REQ-19, AF-REQ-23 · **Date:** 2026-08-08
**Verifier:** `.planning/phases/46-deterministic-alpha-factory/46-VERIFICATION.md` — **passed** (score 100, 0 human_items)

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | Versioned vocabulary/grammar fingerprint; unsupported versions fail closed | ✅ | AF-REQ-02 SC1: vocabulary_fingerprint over live DSL (46 fields + 8 denied + 7 functions/arity + partition + MAX_ROLLING_WINDOW + DSL_VERSION); vocab_fp=90039f5b... grammar_fp=b95d365a...; verify_vocabulary_fingerprint fail-closed (VocabularyMismatchError) |
| UAT-2 | Replay produces identical candidates/IDs/order/checksums independent of worker timing | ✅ | AF-REQ-02 SC2: instance-local random.Random(seed) (no global draws); replay_to(k) rebuilds fresh factory; two independent AlphaFactory(42) → byte-identical 60-element streams; candidate_digest folds step+operation; seed_pool=327 |
| UAT-3 | Every expression parsed + validated before evaluation; invalid → explicit record with diagnostics | ✅ | AF-REQ-03 SC3: validate_candidate 3-gate (complexity→canonicalize→parse_factor); all 13 rejection modes; invalid_reason 5-key payload {diagnostic,location,dsl_version,vocab_version,raw_expression}; never-suppressed |
| UAT-4 | Structural diversity shown; similar candidates stay inspectable (no silent merge) | ✅ | AF-REQ-19: diversity_summary (Jaccard reuse factor_registry._jaccard); field/operator overlap; classify_candidate invalid/duplicate/generated; every candidate appended (one-row-per-attempt) |
| UAT-5 | Server-side budgets enforced; parallel workers cannot change order/winner/replay | ✅ | AF-REQ-23: BudgetGuard (candidate/wall-clock/expression/depth/nodes); terminal_reason='*_budget_exhausted'; token-fenced drive_alpha_generation loop; globally-unique IDs; single-threaded deterministic factory |
| UAT-6 | Explicit non-goals respected; Watchlist untouched | ✅ | No factor computation/fold-OOS/Agent/provider/PyTorch-RL/GPU/arbitrary-Python/broker; git log backend-only; Watchlist.tsx not among unstaged |

## Verdict

**UAT passed** — all 6 criteria satisfied. 377 tests passed (152 alpha_factory + 117 run_contract + 64 run_api + 24 guard + 20 migrations), 0 failures, 0 human_items. Foundation ready for Phase 47 (Governed Scoring, Admission & Selection OOS).
