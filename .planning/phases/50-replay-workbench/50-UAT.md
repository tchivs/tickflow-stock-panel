# Phase 50 UAT — Replay Workbench & Release Hardening

**Phase:** 50 · **Requirements:** AF-REQ-18, AF-REQ-20, AF-REQ-22, AF-REQ-24, AF-REQ-25 · **Date:** 2026-08-09
**Verifier:** `.planning/phases/50-replay-workbench/50-VERIFICATION.md` — **passed** (0 blocking human_items)

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | Durable SSE reconnect (Last-Event-ID); no missing/duplicate/invented events | ✅ | AF-REQ-18: research_alpha_sse.py (zero module-state, terminal termination, read-only); lineage read API (list_run_lineage); replay-branch seed re-derivation |
| UAT-2 | Lineage inspection + branch replay + clone with field-level diffs | ✅ | AF-REQ-20: compare (no opaque winner); Tier-1 stress (formula matches _cost_rate); replay-branch (AlphaFactory.replay_to); clone (scoring/costs/budgets overridable) |
| UAT-3 | Side-by-side compare; stress matrix; no hidden winner | ✅ | AF-REQ-22: compare exposes config/evidence/gate/artifacts/diversity; deny-by-default keys; no winner/rank/score |
| UAT-4 | Temporal/degradation labels; stale/partial cannot look clean | ✅ | AF-REQ-24: evidence_classification clean flag (cache+missing+coverage+fixture+role); data quality banner in AlphaWorkbench |
| UAT-5 | Release verification: no AGPL/deps/execution; research-only boundary | ✅ | AF-REQ-25: test_phase50_guard.py (79 tests, 12-module AST scan + runtime raising-fake + dep diff empty + AGPL scan); release evidence doc |
| UAT-6 | Frontend workbench; Watchlist untouched; zero new deps | ✅ | AlphaWorkbench.tsx (NEW); build green 11.60s; 21 e2e passed; Watchlist.tsx zero-touch (git log empty); sse-starlette pre-existing |

## Verdict

**UAT passed** — all 6 criteria satisfied. 1007 backend tests passed, 21 e2e passed, 141 boundary guard tests green. v3.0 milestone complete.
