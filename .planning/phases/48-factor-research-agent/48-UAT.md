# Phase 48 UAT — FactorResearchAgent Two-Stage Workflow

**Phase:** 48 · **Requirements:** AF-REQ-11, AF-REQ-12, AF-REQ-13, AF-REQ-14, AF-REQ-21, AF-REQ-26 · **Date:** 2026-08-09
**Verifier:** `.planning/phases/48-factor-research-agent/48-VERIFICATION.md` — **passed** (score 100, 0 human_items)

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | Deterministic preflight before model call; failure → zero provider calls + machine-readable reasons | ✅ | AF-REQ-11: preflight.py pure function (8 checks, sub-reason discriminators, zero provider calls on fail, fail-closed) |
| UAT-2 | Stage 1 bounded thesis → strict schema JSON + server parse_factor confirmation + transient | ✅ | AF-REQ-12: Stage1Service (extra=forbid schema, parse_factor canonical, transient proposals catalog-isolated, partial labeling R2) |
| UAT-3 | Stage 2 read-only review; cannot change expressions/metrics/thresholds/OOS/admission; referential integrity | ✅ | AF-REQ-13: Stage2Service (frozen inputs + server evidence, MUTABLE_FIELD_NAMES 7-token blacklist, evidence_refs referential check, advisory recommend-only) |
| UAT-4 | Every Stage 1/2 attempt recorded; provider failure NEVER creates fabricated fallback | ✅ | AF-REQ-14: ProviderFailure 9-class taxonomy, AgentProviderSeam (bounded retry/backoff/cancel), research_alpha_analysis_attempts append-only, no-fallback invariant (all failure paths raise) |
| UAT-5 | Cancellation/retry/restart resume from checkpoint without repeating side effects; offline fixture explicit-only | ✅ | AF-REQ-21: resume_agent_stage (Phase 45 cursor reuse), append_stage_boundary (BEGIN IMMEDIATE), agent_orchestrator.py extracted for boundary guard compliance |
| UAT-6 | Offline fixture explicit-declaration-only; ExperienceLibrary empty-production default; known full trace | ✅ | AF-REQ-26: OfflineFixtureProvider (never I/O, is_fixture_explicitly_selected gate), FixtureTrace (deterministic), ExperienceLibrary Protocol + EmptyExperienceLibrary default |
| UAT-7 | Explicit non-goals respected; Phase 45 boundary guard green; Watchlist untouched | ✅ | No model-tools/metrics/loops/evaluator/mutation/promotion/broker/fallback; test_phase45_guard.py green (provider token not in Phase 45 modules); Watchlist.tsx unmodified |

## Verdict

**UAT passed** — all 7 criteria satisfied. 783 tests passed (full research+migrations+API+guard), 0 failures, 0 human_items. Foundation ready for Phase 49 (Research-Only Promotion Ticket).
