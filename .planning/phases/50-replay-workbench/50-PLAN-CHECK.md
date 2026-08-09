# Phase 50 Plan Check — Replay Workbench & Release Hardening

**Phase:** 50-replay-workbench
**Plans:** 50-01 (SSE + lineage/evidence read), 50-02 (compare/stress/replay/clone), 50-03 (frontend workbench), 50-04 (release guard + smoke evidence)
**Requirements:** AF-REQ-18, AF-REQ-20, AF-REQ-22, AF-REQ-24, AF-REQ-25
**Checked:** 2026-08-09 — goal-backward verification against codebase `main` (Phases 45–49 complete)

## Verdict: **PASS — ready to execute** (0 blockers, 3 warnings)

All five pending requirements map to plan tasks with correct, evidence-grounded designs. Test/page files are all NEW with no collisions. Every cited codebase precedent (replay_to determinism, digest-change-creates-new-run, cost_diagnostics arithmetic, Phase 45/49 guard scaffold, pre-existing sse-starlette dep) verifies against `main`. Three warnings are sequencing/formula-precision notes, none of which block a successful phase ship.

## Goal-backward verification

### 1. Test files — all NEW, zero collisions ✓
Verified absent from the tree: `backend/tests/research/test_alpha_lineage.py`, `test_research_alpha_sse.py`, `test_alpha_compare.py`, `test_alpha_replay_clone.py`; `backend/tests/test_phase50_guard.py`; `frontend/e2e/alpha-workbench.spec.ts`; `frontend/src/pages/backtest/AlphaWorkbench.tsx`. No collision with the existing 80+ research/api tests.

### 2. 50-01 SSE — durable Last-Event-ID design ✓
- `Last-Event-ID` header → `after_seq = k`, reconnect resumes from `k+1`; per-event `id=<seq>`; terminal-status termination (`completed`/`failed`/`cancelled`); keepalive on empty polls. ✓
- `research_alpha_sse.py` is a **NEW** module; `research_alpha.py` is never edited to add the stream → Phase 45 guard `test_no_sse_streaming_route_added` (test_phase45_guard.py:198-206, asserts `StreamingResponse`/`text/event-stream` absent from `research_alpha.py`) **stays GREEN unamended**. Confirmed: that test's body scopes only to `research_alpha.py`, and `test_no_new_router_in_main_beyond_research_alpha` (208-214) only forbids the literal `"workbench"` token — adding the SSE router to `main.py` violates neither.
- Zero module-level state confirmed as the decisive contrast: `walkforward_sse.py:168` (`cursor = 0`) + module-level `_wf_jobs`/`_wf_jobs_lock`/`_WfJob` is the in-memory gap this closes; 50-01 recovers every cursor from the durable ledger.
- Bounded-polling fallback: pre-existing `GET /runs/{id}/progress` + `GET /runs/{id}/events?after_sequence=` — SC1 "SSE **or** bounded polling" satisfied without new work.

### 3. 50-01 lineage read projection ✓
Confirmed `append_candidate_lineage` is **write-only** (repository.py:2447, run_service.py:599, run_worker.py:143) — no `list_run_lineage`/`list_lineage` exists today. 50-01-01 adds the missing read projection over the append-only `research_alpha_candidate_lineage` (no_update/no_delete triggers, migrations.py:1984-1987). `evidence_classification.clean` flag flips false on any of stale/degraded cache, non-empty missing_fields, low coverage, fixture, final_blind_unavailable — every value sourced from existing declared fingerprints (no new collection).

### 4. 50-02 compare / stress / replay / clone ✓
- **No opaque winner:** compare exposes config + per-fold evidence + admission verdict + gate_trail_digest + artifact refs + diversity per candidate, side-by-side; acceptance asserts NO winner/rank/score key. ✓
- **Stress Tier-1 pure arithmetic:** re-arithmetic over stored `turnover_per_rebalance` + `cost_diagnostics` (evaluation.py:105-171); injects raising fakes for signal_chain/evaluation/admission — never recomputes factor values, never touches thresholds. Tier-2 (calendar-regime/coverage/symbol-subset) explicitly **deferred** (returns bounded 422). ✓
- **replay_branch** via `AlphaFactory.replay_to(parent_step+1)` (alpha_factory.py:349-365 — fresh factory from frozen seed, equals live prefix) → continues into a new child run through the **existing** `run_worker` path (no second generation path, risk #2 mitigated). ✓
- **clone** overridable = scoring/costs/budgets only; `seed`/`universe` rejected with 422 `CloneOverrideForbidden`. No-op clone returns parent id (unchanged-inputs-keep-their-hashes, run_contract.py:160-162). ✓

### 5. 50-03 frontend — new page, Watchlist zero-touch ✓
- `AlphaWorkbench.tsx` is a NEW page (sibling to `WalkForward.tsx`) + NEW route `backtest/alpha-workbench`. `files_modified` lists api.ts, AlphaWorkbench.tsx, router.tsx, e2e spec — **Watchlist.tsx absent**. ✓
- Native `EventSource` (WalkForward.tsx:21,30,76 precedent — browser auto-sends `Last-Event-ID`) + React Query (`request<T>` fetcher); e2e mocks reconnect and asserts no dup/gap. No new npm dep (ROADMAP.md:12). ✓
- Compare panel renders no winner column; data-quality banner binds `evidence_classification.clean` (red on false). ✓

### 6. 50-04 release guard ✓
`test_phase50_guard.py` reuses Phase 45 token regex + Phase 49 `_RaisingFake` (test_phase49_guard.py:208-228). Streaming tokens (`StreamingResponse`/`text/event-stream`/`EventSourceResponse`/`sse_starlette`) permitted in `research_alpha_sse.py` **only**. Broker/execution AST scan over the **union** Phase-50 + Phase-45–49 Alpha/Agent/promotion/workbench/SSE module set (app.portfolio, app.strategy engine, broker/order/position/portfolio). Dep-manifest diff asserts `[project.dependencies]` unchanged (`sse-starlette>=2.0` is pre-existing at pyproject.toml:15, NOT new). AGPL/AlphaMaster/PA_Agent provenance content scan (MIT only). `docs/phase50_release_evidence.md` records the four smoke facts (SC5).

### 7. Wave deps + file overlap ✓
- 50-01 wave 1 (depends_on []); 50-02 wave 2 (depends_on [50-01]); 50-03 wave 2/3 (depends_on [50-01,50-02]); 50-04 wave 1 parallel.
- File overlap: 50-01 & 50-02 both edit `repository.py`/`run_service.py`/`projections.py`/`run_schemas.py`/`research_alpha.py` — but they are in **separate waves** (50-02 runs after 50-01 completes), so no concurrent edit collision; executor re-reads each file before appending.
- Verify commands are syntactically valid `pytest -k`, `vitest run`, `playwright test`, `tsc --noEmit`, `git diff --name-only` invocations. ✓

### 8. Explicit non-goals honored ✓
No WebSocket/external broker (native EventSource + sse-starlette only); no second transport (EventSource or bounded polling); no hidden browser authority (deterministic server owns cursor); no final-blind (labeled `final_blind_unavailable`, never fabricated); no AGPL source (patterns only, MIT); no PyTorch/RL/GPU; no automatic live/paper; no broker integration; **Watchlist.tsx zero-touch** (declared non-goal ROADMAP.md:171, asserted by 50-03 e2e + 50-04 guard).

## AF-REQ coverage matrix

| REQ | SC | Plan | Task(s) | Coverage |
|---|---|---|---|---|
| AF-REQ-18 | SC1 (durable SSE progress) | 50-01 | 50-01-04 | FULL — Last-Event-ID resume, zero module state, terminal termination, bounded-poll fallback |
| AF-REQ-18 | SC2 (lineage read half) | 50-01 | 50-01-01/02/03 | FULL — list_run_lineage read projection + projection.lineage + endpoint |
| AF-REQ-18 | SC2 (replay/clone) | 50-02 | 50-02-03/04 | FULL — replay_to branch replay + clone (scoring/costs/budgets only) + field-level diff |
| AF-REQ-20 | SC3 (stress Tier-1) | 50-02 | 50-02-02 | FULL — pure arithmetic over stored turnover, no admission touch; Tier-2 deferred (422) |
| AF-REQ-22 | SC3 (compare, no winner) | 50-02 | 50-02-01 | FULL — all candidates side-by-side, no opaque aggregate |
| AF-REQ-24 | SC4 (degradation labels) | 50-01 | 50-01-02/03 | FULL — evidence_classification.clean flag, every value from existing fingerprints |
| AF-REQ-25 | SC5 (release hardening) | 50-04 | 50-04-01/02/03/04 | FULL — AST + broker/execution scan + _RaisingFake + dep diff + AGPL scan + smoke doc |
| (UI projection SC1–SC4) | SC1–SC4 | 50-03 | 50-03-01..04 | FULL — EventSource progress, lineage tree, compare panel, stress matrix, data-quality banner, e2e, Watchlist zero-touch |

## Blockers
**0.**

## Warnings
- **W1 (sequencing) — 50-04 declares `wave:1`/`depends_on:[]` but its guard green is gated on 50-01/02/03 modules existing.** Task 50-04-01 acceptance ("every PHASE50 module exists on disk and parses — module-graph completeness") and 50-04-02 (`_RaisingFake` across "every new workbench/SSE/compare/stress/replay/clone handler") require `research_alpha_sse.py` (50-01), the 50-02 compare/stress/replay/clone handlers, and the 50-03 frontend modules. Run in declared wave 1 the guard goes RED (modules absent). **Recommend:** set `depends_on:[50-01,50-02,50-03]` (→ final wave), OR have the guard discover `PHASE50_MODULES` dynamically so it passes for whatever subset exists. Test authorship itself is independent and can proceed in parallel.
- **W2 (formula precision) — Tier-1 stress must reuse `_cost_rate` semantics for the baseline to match.** The 50-02-02 body shorthand `cost_drag_alt = turnover * (fee + slippage)/1e4` omits the double-sided factors and stamp tax that `_cost_rate` (evaluation.py:92-102) applies: `commission_pct*2 + stamp_tax_pct + slippage_bps*2/1e4`, `cost_drag = total_turnover * cost_rate`. The acceptance criterion "baseline row equals the frozen cost_diagnostics" forces the executor to reuse `_cost_rate` (self-correcting), but the literal shorthand risks a baseline mismatch if copied verbatim.
- **W3 (wave label loose) — 50-03 is wave 2 with `depends_on:[50-01,50-02]`, but 50-02 is also wave 2.** 50-03 effectively serializes after 50-02 within wave 2 (research anticipated "w2/3"). `depends_on` makes the orchestrator sequence it correctly regardless; the wave label is informational only. No action required.

## Notes
- `sse-starlette>=2.0` is at pyproject.toml:15 (MIT) — correctly treated as pre-existing, not new (ROADMAP.md:12 zero-new-base-dep constraint holds).
- The Phase 45 guard's `test_no_new_router_in_main_beyond_research_alpha` only forbids the literal `"workbench"` token; including `research_alpha_sse.router` in `main.py` keeps it green (verified).
- 50-01 edits `research_alpha.py` for two **read-only** endpoints (lineage, evidence-classification) — these add no `StreamingResponse`/`text/event-stream`, so Phase 45 guard's 198-206 assertion stays green.
- 50-02 `replay_branch` determinism is load-bearing on `replay_to` being single-threaded; it reuses the existing token-fenced `run_worker` path (risk #2) — no second generation path is introduced.

---
*Plan-checked 2026-08-09 — all citations verified against `main` (Phases 45–49 complete).*
