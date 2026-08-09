---
phase: 50
title: Replay Workbench & Release Hardening (AF-REQ-18, AF-REQ-20, AF-REQ-22, AF-REQ-24, AF-REQ-25)
status: passed
verified: 2026-08-09
verifier: VerifierP50
requirements: [AF-REQ-18, AF-REQ-20, AF-REQ-22, AF-REQ-24, AF-REQ-25]
plans: [50-01, 50-02, 50-03, 50-04]
test_total: 1007
---

# Phase 50 Verification — Replay Workbench & Release Hardening

**Verdict: PASS** — AF-REQ-18/20/22/24/25 are fully delivered at the code level. The full orchestrator regression batch is green (1007 passed, 0 failures, 0 skips), all three boundary guards hold (Phase 45 + 49 + 50 → 141 passed), the frontend production build is green with the `AlphaWorkbench` lazy chunk present, and `Watchlist.tsx` is genuinely zero-touch across every Phase 50 commit. No blocking human items.

## 1. Test batch

Command (run in `backend/`):

```
.venv/bin/python -m pytest tests/research/ tests/test_operational_migrations.py \
  tests/api/test_run_api.py tests/test_phase45_guard.py tests/test_phase49_guard.py \
  tests/test_phase50_guard.py -x -q
```

**Result: 1007 passed in 186.15s** (no failures, no skips). Matches the orchestrator-reported regression total.

Phase 50 new-test counts (`--co -q`, post-migrate):

| File | Plan | Tests |
|---|---|---:|
| `tests/research/test_alpha_lineage.py` (50-01) | 50-01 | 23 |
| `tests/research/test_research_alpha_sse.py` (50-01) | 50-01 | 15 |
| `tests/research/test_alpha_compare.py` (50-02) | 50-02 | 18 |
| `tests/research/test_alpha_replay_clone.py` (50-02) | 50-02 | 24 |
| `tests/test_phase50_guard.py` (50-04) | 50-04 | 79 |
| **backend total** | | **159** |
| `frontend/e2e/alpha-workbench.spec.ts` (50-03) | 50-03 | 7 scenarios × 3 projects = 21 runs |

Boundary guards run in isolation: `tests/test_phase45_guard.py tests/test_phase49_guard.py tests/test_phase50_guard.py` → **141 passed** (cross-checks the 50-04 SUMMARY block claim exactly).

## 2. AF-REQ-by-AF-REQ code-level evidence

### AF-REQ-18 — durable SSE replay stream + lineage read API — PASS

| Sub-criterion | Evidence (file:line) | Status |
|---|---|:--:|
| Durable `Last-Event-ID` SSE stream; zero module-level state; cursor recovered from the ledger | NEW module `app/api/research_alpha_sse.py`; `_parse_last_event_id` resolves the cursor from the `Last-Event-ID` header (`:61-73`); `_stream_events` carries no module-level dict, advances `cursor = last_seq` per row (`:95-120`); `GET /runs/{run_id}/stream` → `EventSourceResponse` (`:123-146`) | ✅ |
| Read-only generator (no write path); terminal termination; keepalive | generator calls only `service.list_events` + `service.get` (`:98,111`); emits a `terminal` event + `return` on terminal status (`:112-118`); `: ping` keepalive on empty poll (`:119`) | ✅ |
| SSE lives in a NEW file so the Phase 45 guard stays GREEN unamended | `test_phase45_guard.py:198-206` asserts `research_alpha.py` carries no `StreamingResponse`/`text/event-stream`; SSE tokens are scoped to `research_alpha_sse.py` only (`test_phase50_guard.py` `_SSE_MODULE`, `_STREAMING_TOKENS`) | ✅ |
| Lineage read API (read-only counterpart to the write-only append) | `repository.list_run_lineage`: plain SELECT over append-only `research_alpha_candidate_lineage` joined to child/parent candidate rows, principal-fenced (cross-principal == unknown → `[]`): `app/research/repository.py:2517-2572`; `service.list_lineage`: `app/research/run_service.py:530-541`; deny-by-default `projections.lineage`: `app/research/projections.py:121-134`; `GET /runs/{run_id}/lineage`: `app/api/research_alpha.py:300-318` | ✅ |
| Replay-branch seed re-derivation into a NEW child run (determinism) | `service.replay_branch` reconstructs `AlphaFactory(seed).replay_to(parent_step+1)`, **asserts** the re-derived prefix digests equal the parent's first `parent_step+1` candidates (`:1387-1393`), then continues via the EXISTING `create()` path — no second generation path: `app/research/run_service.py:1342-1408`; `POST /runs/{run_id}/replay-branch`: `app/api/research_alpha.py:430-457` | ✅ |
| Durable resume / no-dup / no-gap proven server-side | `test_research_alpha_sse.py`: `test_last_event_id_resumes_from_k_plus_1`, restart-resume, keepalive, terminal, no-module-state (15 tests) | ✅ |

### AF-REQ-20 — Tier-1 stress matrix (pure arithmetic) — PASS

| Sub-criterion | Evidence (file:line) | Status |
|---|---|:--:|
| Tier-1 fee/slippage/rebalance stress over STORED turnover (no factor re-score) | `service.stress_matrix`: reads frozen `cost_diagnostics`, `_stress_rows` re-projects `cost_drag`/`net` by pure arithmetic (`:1296-1329`); `_TIER1_STRESS_AXES = {fee_bps, slippage_bps, rebalance}` (`:1107`); `app/research/run_service.py:1225-1340`; `projections.stress_matrix`: `app/research/projections.py:332-345`; `GET /runs/{run_id}/stress-matrix`: `app/api/research_alpha.py:379-428` | ✅ |
| cost-rate helper mirrors `evaluation._cost_rate` EXACTLY | `evaluation._cost_rate = commission*2 + stamp + slippage_bps*2/1e4` (`evaluation.py:92-102`); service `_round_trip_cost_rate` is byte-identical (`run_service.py:1196-1209`); fee_bps axis `rate = fee_bps/1e4 + frozen_slippage*2/1e4` reproduces the frozen rate at baseline (`:1314-1317`); baseline row = frozen `cost_diagnostics` verbatim (`_stress_baseline :1278-1294`) | ✅ |
| Tier-2 axes are an explicit bounded deferral (never a fake result) | `_TIER2_STRESS_AXES = {calendar_regime, coverage, symbol_subset}` raise `NotImplementedError` → bounded 422 (`:1111-1113`, `:1247-1251`) | ✅ |
| No admission write / no chain re-score in the stress path | runtime `_RaisingFake` proof across the stress handler: `test_phase50_guard.py::TestRuntimeNoExecutionCollaborator` (raising fakes for evaluation/signal_chain/admission never invoked) | ✅ |

### AF-REQ-22 — side-by-side compare (no opaque winner) — PASS

| Sub-criterion | Evidence (file:line) | Status |
|---|---|:--:|
| Exposes config + per-fold evidence + admission verdict + gate trail + artifacts + diversity equally | `service.compare_candidates` → `_compare_entry` assembles canonical_expression/seed/step/operation/digest, `projections.fold_evidence` (IC/RankIC/ICIR/coverage/monthly robustness + cost diagnostics), admission verdict + `gate_trail_digest`, artifact refs, `projections.diversity`: `app/research/run_service.py:1117-1194`; `GET /runs/{run_id}/compare`: `app/api/research_alpha.py:347-377` | ✅ |
| NEVER an opaque aggregate / winner / rank / score | deny-by-default `_COMPARE_CANDIDATE_KEYS` allowlist has no winner/rank/score field: `app/research/projections.py:289-302`; `projections.compare` returns only `run_id` + `candidates` (`:305-318`); frontend `AlphaCandidateComparison` type carries no winner/rank/score field; e2e asserts no winner/rank/score header | ✅ |
| Unknown candidate among the set is a graceful partial; cross-principal == unknown → same 404 (no leak) | `compare_candidates` skips unknown ids (`selected` filter `:1141`), returns `None` for unknown/cross-principal run (`:1134-1136`) | ✅ |

### AF-REQ-24 — temporal / degradation labels (clean flag) — PASS

| Sub-criterion | Evidence (file:line) | Status |
|---|---|:--:|
| Evidence classification sourced from EXISTING declared fingerprints (no new data collection) | `projections.evidence_classification` reads measured_window → `data_date`, source_field fingerprint → `source_label`, declared-fingerprint block completeness → `cache_state`, declared missing list → `missing_fields`, fold `stats.coverage` → `membership_coverage`, candidate status + fold presence → `evidence_role`: `app/research/projections.py:137-236` | ✅ |
| `clean` flag — degraded results can never look like clean production | `clean = cache_state=="fresh" AND not missing_fields AND coverage≥0.9 AND not fixture AND evidence_role≠final_blind_unavailable` (`:219-225`); `_BLOCKED_BLIND_STATUSES` maps terminally-blocked candidates to `final_blind_unavailable` (`:115-118`); `_COVERAGE_CLEAN_THRESHOLD=0.9` (`:112`) | ✅ |
| Endpoint + service seam | `service.candidate_evidence_classification` (loads declared fingerprints, prefers OOS fold): `run_service.py:543+`; `GET /runs/{run_id}/candidates/{cid}/evidence-classification`: `app/api/research_alpha.py:319-345` | ✅ |

### AF-REQ-25 — release verification guard (SC5) — PASS

| Sub-criterion | Evidence (file:line) | Status |
|---|---|:--:|
| AST import/call/attr scan over the union module graph (12 modules) | `PHASE50_MODULES` = new SSE module ∪ Phase 45 Alpha graph (9) ∪ Phase 49 promotion graph (2): `test_phase50_guard.py:56-72`; `_PROHIBITED_IMPORT_TOKENS` (broker/order/position/portfolio/monitor/execution/provider/llm/evaluator/oos/redis/kafka/...): `:81-103`; `_PROHIBITED_CALL_RE` (eval/exec/compile/__import__): `:108-115`; `_PROHIBITED_ATTR_RE` (subprocess/pickle/marshal/ctypes): `:118-120`; `TestPhase50ModuleGraphImportBoundary` (50 tests) | ✅ |
| Broker/execution AST scan + runtime `_RaisingFake` proof | `TestNoExecutionSurfaceImport` AST-scans `_EXECUTION_PACKAGES` (`:284-298`); `TestRuntimeNoExecutionCollaborator` injects raising broker/order/position/portfolio/monitor/execution fakes and exercises inspect/evidence/compare/stress/replay-branch/clone/SSE-stream end-to-end, asserting zero execution-collaborator calls (`:454-528`) | ✅ |
| Dependency-manifest diff empty (zero new base deps) | `TestNoNewBaseDependency` parses `pyproject.toml [project.dependencies]` (tomllib) and asserts equality with `_DEPENDENCY_BASELINE`; `sse-starlette>=2.0` is pre-existing (`pyproject.toml:15`), deliberately in the baseline (`:534-601`) | ✅ |
| AGPL-derived-source scan + MIT license | `TestNoAgplDerivedSource` scans for agpl/alphamaster/pa_agent/affero provenance tokens over the module graph (`:611-639`); LICENSE is MIT | ✅ |
| Documented smoke evidence | `docs/phase50_release_evidence.md` records all four SC5 facts (guard pass, empty dep diff, no-execution runtime proof, research-only action surface) + license; `TestReleaseEvidenceDocument` asserts existence + required sections | ✅ |

## 3. Frontend — build, e2e, Watchlist proof

| Check | Evidence | Status |
|---|---|:--:|
| Production build green | `cd frontend && npm run build` → `✓ built in 11.60s`, EXIT 0; `dist/assets/AlphaWorkbench-Bz04Y0pI.js` lazy chunk present (81 JS chunks, favicon present) | ✅ |
| AlphaWorkbench page exists | `frontend/src/pages/backtest/AlphaWorkbench.tsx` (sibling to WalkForward); lazy route `backtest/alpha-workbench`; all SC1–SC4 surfaces: EventSource progress + bounded-polling fallback (SC1), lineage tree + replay/clone (SC2), compare panel with no winner column (SC3), data-quality banner bound to `evidence_classification.clean` (SC4), Tier-1 stress matrix | ✅ |
| e2e spec covers SC1–SC4 + Watchlist isolation | `frontend/e2e/alpha-workbench.spec.ts` — 7 scenarios × 3 projects (desktop-chromium / mobile-chromium-320 / phase4-fastapi-host) = 21 runs: page shell, EventSource ordered+dedup+terminal (SC1), compare no-winner (SC3), data-quality banner red-when-dirty (SC4), lineage tree (SC2), stress grid (AF-REQ-20), Watchlist zero-touch (no `Watchlist` token in AlphaWorkbench) | ✅ |
| Watchlist.tsx zero-touch (the real test) | `git log --oneline 2a18c1b^..70aecb6 -- frontend/src/pages/Watchlist.tsx` → **EMPTY** (no Phase 50 commit touched it). The working-tree `+1 -1` is a pre-existing unstaged change from commit `96e3c4d` (the 91-file `lightweight-charts`/WCAG refactor), not Phase 50. | ✅ |
| Zero new runtime/dev deps | native `EventSource` + React Query + existing `request<T>`; Playwright already a devDependency; vitest unit suites are runnable-ready but not executed (vitest is not a dep — adding it would violate the zero-new-deps constraint; e2e is the executable proof) | ✅ |

## 4. Boundary guards

All three guards are green, run together and in isolation:

```
tests/test_phase45_guard.py tests/test_phase49_guard.py tests/test_phase50_guard.py -q → 141 passed
```

- **Phase 45 guard** (Alpha run-contract boundary): the SSE assertion on `research_alpha.py` (`test_phase45_guard.py:198-206`) stays GREEN unamended because SSE lives in the separate `research_alpha_sse.py`; the router assertion (`test_no_new_router_in_main_beyond_research_alpha`) confirms `main.py` wires `research_alpha_sse.router` without a `"workbench"` token leak.
- **Phase 49 guard** (promotion boundary): unchanged, green.
- **Phase 50 guard** (79 tests): AST import/call/attr + execution-surface + runtime `_RaisingFake` + dep diff + AGPL/license + release-evidence doc.

Phase 50 adds surfaces without weakening the existing boundary.

## 5. SUMMARY cross-checks

| SUMMARY claim | Verification method | Result |
|---|---|:--:|
| 50-01: "90 passed" (lineage + sse + phase45 guard verification block) | collected 38 new tests (23 lineage + 15 sse); combined with phase45 guard → matches | ✅ |
| 50-02: "42 new tests" (compare + replay/clone) | `--co -q` → **42 collected** (18 compare + 24 replay_clone) | ✅ |
| 50-04: "141 passed" (phase45+49+50 guards) | re-ran the triple-guard batch → **141 passed** | ✅ |
| 50-04: "79 tests" guard | `--co -q` → **79 collected** | ✅ |
| 50-01: cost-rate `_cost_rate` mirror (plan-check W2) | `evaluation._cost_rate` (`evaluation.py:92-102`) == service `_round_trip_cost_rate` (`run_service.py:1196-1209`) byte-for-byte | ✅ |
| 50-03: "21 passed" e2e | spec has 7 scenarios × 3 projects = 21 runs; build green with AlphaWorkbench chunk (e2e re-execution requires a live dev server + Chromium — not re-run here; the SUMMARY records it green on a dedicated :4199 server) | ✅* |

`*` e2e execution is recorded green in 50-03-SUMMARY (dedicated vite :4199 + real FastAPI host); re-running requires browser/server infra. The spec, build, and chunk are confirmed present.

## 6. human_items

None blocking. Two minor, non-blocking observations for the record:

1. **50-01-SUMMARY internal test-count inconsistency (cosmetic).** The per-task table sums to "33" (5+12+7+9) while the prose and hand-off say "38". The actual file count is **38** (23 lineage + 15 sse). The "33" reflects focused `-k` selections that overlap; the real delivered total is 38. No code/test impact.
2. **50-03 unit suites are runnable-ready, not executed.** `frontend/tests/unit/alpha-workbench-{api,progress,views}.test.ts` target vitest, which is not a dependency (zero-new-deps constraint). The Playwright e2e is the executable proof of SC1–SC4. Wiring vitest later is a follow-up, not a Phase 50 gap.

No action required from a human operator; Phase 50 may be marked complete with AF-REQ-18, AF-REQ-20, AF-REQ-22, AF-REQ-24, and AF-REQ-25 satisfied.
