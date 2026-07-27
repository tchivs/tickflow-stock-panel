---
phase: 02-factor-and-strategy-research
verified: 2026-07-11T10:46:05Z
status: passed
score: 12/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 8/9
  gaps_closed:
    - "A researcher can retain a completed registered-strategy SSE execution from the Backtest workspace and select its immutable snapshot for comparison."
  gaps_remaining: []
  regressions: []
---

# Phase 2: Factor And Strategy Research Verification Report

**Phase Goal:** Researchers can turn factor hypotheses into comparable, reproducible evaluations using the governed market-data foundation.
**Verified:** 2026-07-11T10:46:05Z
**Status:** passed
**Re-verification:** Yes — after Plan 02-08 closed the prior browser-flow gap and post-review remediation was applied.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | A researcher can create a factor with the permitted expression language, validate it before evaluation, save immutable revisions, and receive deterministic explained similarity candidates. | ✓ VERIFIED | `factor_dsl.py` parses/validates before fixed AST-to-Polars dispatch; `factor_registry.py` parses before transactions, appends revisions, and deterministically orders explained candidates. The focused backend suite exercised unsafe-source rejection, revision history, and similarity behavior. |
| 2 | Stateful DSL operations preserve governed-panel semantics: `rank`/`zscore` use same-date peers and `rolling_mean` uses each symbol's chronological rows. | ✓ VERIFIED | `factor_dsl.py:488-495` fixes the partitions with `.over("date")` and `.over("symbol")`; deterministic compiler and managed-artifact regressions passed in the focused backend suite. |
| 3 | A stored factor evaluation loads governed data through `BacktestEngine`, retains explicit configuration/input/artifact provenance, and exposes distinct Pearson IC and Spearman RankIC evidence. | ✓ VERIFIED | `evaluation.py:152-207` calls `load_panel`, builds a manifest, calculates separate correlation series/summaries, and writes managed artifact descriptors. `test_factor_evaluation.py` passed, including divergent metric values, pre-load validation, artifact checksums, and collision handling. |
| 4 | A natural-language hypothesis remains a validated provenance-bearing draft until issued-draft review creates a revision; it must then complete evaluation and explicit retention before comparison. | ✓ VERIFIED | `hypotheses.py:190-246` validates provider text with the DSL and verifies an issued draft's expression/explanation/provenance. `api/research.py:232-304` performs reviewed promotion before evaluation; focused API/hypothesis tests and the browser flow passed. |
| 5 | Factor and registered-strategy snapshots retain immutable configuration, governed inputs, predictions/signals, metrics, artifacts, and model/provider provenance; only completed, validated, explicitly retained snapshots are candidates. | ✓ VERIFIED | `catalog.py:220-432` records immutable snapshots, limits candidates/comparison to completed validated retained records, and returns all evidence dimensions. Focused catalog/API tests passed. |
| 6 | Successful registered-strategy results carry deterministic governed-panel revision/fingerprint identity, and synchronous/SSE handoff persists only server-generated recognized fields. | ✓ VERIFIED | `strategy.py:160,292+` derives provenance from the loaded panel; `api/backtest.py:344-415` transfers only `revision`/`fingerprint` from that server result. Focused strategy correctness and handoff tests passed, including forged client-field rejection. |
| 7 | Comparison makes incompatibilities visible across all retained evidence dimensions and does not produce a winner or ranking. | ✓ VERIFIED | `catalog.py:435-501` emits normalized deltas plus universe/window/horizon/revision/fingerprint warnings; `ExperimentComparison.tsx` renders all six dimensions and explicitly states that it computes no winner/score. Catalog tests and browser comparison assertions passed. |
| 8 | A browser researcher can retain a completed registered-strategy SSE execution only after the same task has a validated successful result and a non-empty server-issued `research` handle. | ✓ VERIFIED | `backtestTask.ts:146-228` validates complete terminal payloads, accepts handles only from a matching SSE `research` event, and clears them on malformed/error/cancel paths. `StrategyBacktest.tsx:863-887` gates the CTA on the current completed task and task-owned handle. The focused Playwright suite passed its positive, missing-done, and malformed-nested-payload cases. |
| 9 | Retention is explicit, single-flight, and non-destructive: it sends only the task-owned handle, shows retained state only from the immutable server response, and refreshes history/candidates without rerunning or mutating the displayed result. | ✓ VERIFIED | `StrategyBacktest.tsx:791-801,868-887` calls `api.retainStrategyResearchExecution(handle)`, scopes pending/success to the task, and invalidates `QK.researchExperiments` and `QK.researchComparisonCandidates`. `Backtest.tsx:94-96` renders the existing history/comparison surfaces in strategy mode. Playwright verified the one SSE-handle POST, returned experiment ID, and candidate selection. |
| 10 | Malformed, missing-done, failed/cancelled, stale/already-retained, and old-task outcomes never promote a retained comparison candidate. | ✓ VERIFIED | The parser failure branch clears the handle in `backtestTask.ts:226-228`; terminal errors/cancellation clear it at lines 235-265 and 360-362. The mutation only associates a response with the same task at `StrategyBacktest.tsx:793-797`. Four focused Playwright tests passed for malformed payload, no matching done, delayed old-task success, and 409 retry/no-promotion. |
| 11 | At 1440px, 1024px, and 375px, the approved mode/result tab, explicit retention, candidate selection, disclosure, pagination, and narrow-table keyboard contracts are operable; 375px retention has a 44px target. | ✓ VERIFIED | `Backtest.tsx:39-67` and `StrategyBacktest.tsx:891-920,1792-1910` implement tab keyboard navigation, focusable overflow wrappers, Arrow/Home/End scrolling, and focus rings. The Scenario-5 Playwright test passed through all three exact viewports, including 44px geometry and real keyboard-induced horizontal scroll to `累计收益`. |
| 12 | The three roadmap success criteria and FACT-01/FACT-02/FACT-03 are available through the existing Backtest workspace rather than a parallel API client, route, datastore, or strategy-authoring path. | ✓ VERIFIED | Factor and strategy modes share `Backtest.tsx`; research requests use typed `api.ts` and `QK` conventions. Source inspection found no parallel workspace/client in Phase 2 paths; the focused backend and browser commands both passed. |

**Score:** 12/12 truths verified (0 present-but-behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/app/research/factor_dsl.py`, `factor_registry.py`, `repository.py` | Closed DSL, immutable revisions, deterministic similarity | ✓ VERIFIED | Substantive parser/compiler and insert-only registry code; exercised by focused DSL/registry/API tests. |
| `backend/app/research/evaluation.py`, `artifacts.py` | Governed evaluation, explicit manifest, separate IC/RankIC, managed immutable artifacts | ✓ VERIFIED | Uses the `BacktestEngine` loading seam and checksummed `research_artifacts/<run-id>` descriptors; focused evaluation tests passed. |
| `backend/app/research/hypotheses.py`, `backend/app/api/research.py` | Proposal-only draft/review/evaluation/retention workflow | ✓ VERIFIED | The proposal service lacks registry/evaluator/artifact collaborators; API requires issued review and routes retention/comparison through the catalog. |
| `backend/app/research/catalog.py`, `backend/app/backtest/strategy.py`, `backend/app/api/backtest.py` | Immutable strategy/factor snapshots, trusted strategy provenance and handoff | ✓ VERIFIED | Server-derived manifest and server-only finalization feed completed-only retained comparison candidates; focused strategy/catalog/API tests passed. |
| `frontend/src/lib/backtestTask.ts`, `frontend/src/lib/api.ts` | Validated task-scoped SSE-handle lifecycle and typed retention call | ✓ VERIFIED | Research handles originate only in the `research` event; malformed/error/cancel paths clear them; the typed API is the sole retention caller. |
| `frontend/src/pages/Backtest.tsx`, `frontend/src/pages/backtest/StrategyBacktest.tsx` | Explicit strategy retention, comparison reachability, responsive keyboard semantics | ✓ VERIFIED | Task/handle-scoped mutation, status/error states, tab semantics, 44px target styling, and focusable semantic tables are wired into the existing workspace. |
| `frontend/e2e/phase2-research.spec.ts` | Deterministic user-visible proof for factor workflow and strategy lifecycle | ✓ VERIFIED | Six named desktop-Chromium tests enumerate all required positive and rejection paths and passed in this verification. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `ParsedFactor.compile()` | `FactorEvaluationService._evaluate_panel()` | Validated AST expression over `BacktestEngine.load_panel()` data | ✓ WIRED | `evaluation.py` loads declared columns then calculates separate metrics/artifacts; partitioned artifact tests passed. |
| `FactorHypothesisService.draft()` | reviewed-factor API → immutable revision → evaluation → catalog | Parser-confirmed issued draft and explicit `reviewed: true` transition | ✓ WIRED | Route verifies the exact issued draft/provenance before registry persistence; API tests passed. |
| `StrategyBacktestService.run()` | `_strategy_input_manifest()` → `_finalize_strategy_experiment()` → `ExperimentCatalog.record_strategy_backtest()` | Server-produced governed manifest/result only | ✓ WIRED | Synchronous and SSE handoff test assertions passed; client-provided metrics/manifest fields are rejected. |
| SSE `research` event | `BacktestTask.researchExecutionHandle` → `StrategyBacktest` retention mutation | Current EventSource task state and non-empty opaque handle | ✓ WIRED | Source enforces the lifecycle; Playwright passed the valid handle, malformed payload, no-done, stale, and old-task cases. |
| Retention success | `ResearchLibrary` and `ExperimentComparison` | Query invalidation plus strategy-mode composition | ✓ WIRED | Existing history/candidate queries render beneath `StrategyBacktest`; Playwright selected the retained snapshot and compared it. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| Factor evaluation | validated expression, panel, manifest, IC/RankIC, artifact descriptors | `BacktestEngine.load_panel()` → Polars evaluation → managed artifact bundle → catalog snapshot | Yes | ✓ FLOWING |
| Strategy snapshot | governed revision/fingerprint, config, metrics, curves/trades, artifact descriptors | `StrategyBacktestService.run()` → server finalizer → immutable catalog record | Yes | ✓ FLOWING |
| Browser retention | task-owned execution handle and returned immutable experiment | server SSE `research` → validated task state → retention endpoint → invalidated history/candidate queries | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| DSL safety, immutable revisions/similarity, governed IC/RankIC evaluation/artifacts, draft review gates, catalog filtering/comparison, server-only strategy provenance/handoff | `uv run --project backend pytest backend/tests/research/test_factor_dsl.py backend/tests/research/test_factor_registry.py backend/tests/research/test_factor_evaluation.py backend/tests/research/test_experiment_catalog.py backend/tests/research/test_hypothesis_workflow.py backend/tests/research/test_research_api.py backend/tests/research/test_strategy_experiment_handoff.py backend/tests/backtest/test_strategy_backtest_correctness.py -q` | **41 passed** in 3.61s; 7 existing Polars `pivot(columns=...)` deprecation warnings | ✓ PASS |
| Typed production frontend build | `pnpm --dir frontend build` | TypeScript and Vite production build completed; existing large-chunk advisory only | ✓ PASS |
| Factor UI plus trusted strategy retention/rejection and responsive keyboard workflow | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts --project=desktop-chromium` | **6 passed** in 49.8s: manual factor/draft flow; 1440/1024/375 Scenario 5; malformed terminal; no done; old-task delay; stale 409 | ✓ PASS |

### Probe Execution

No Phase-2-declared probe reference exists, and `scripts/**/tests/probe-*.sh` is absent. No probe execution was required.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| FACT-01 | 02-01, 02-02, 02-04, 02-05, 02-06 | Restricted factor definition; immutable storage/discovery; governed IC and RankIC evaluation | ✓ SATISFIED | Closed AST DSL rejects unsafe syntax; revisions and similarity are deterministic; evaluation records distinct metrics, manifest, and checksummed artifacts. The 41-test backend run and factor browser flow passed. |
| FACT-02 | 02-02, 02-04, 02-05 | Natural-language hypothesis becomes a reviewed, validated factor, is backtested, then explicitly retained | ✓ SATISFIED | Draft service is proposal-only and parser-confirmed; issued-draft review is required before revision persistence; completed evidence must be explicitly retained. API/hypothesis and browser workflow coverage passed. |
| FACT-03 | 02-03, 02-04, 02-05, 02-07, 02-08 | Run factor/registered-strategy experiments and compare retained configuration, inputs, predictions, metrics, artifacts, and model versions | ✓ SATISFIED | Immutable catalog exposes all six evidence dimensions and warnings/no winner; server-only strategy provenance is retained; the browser flow now carries SSE completion through explicit retention to selectable comparison candidates. Backend and all six focused Playwright tests passed. |

All Phase 02 plans declare only FACT-01, FACT-02, and FACT-03; REQUIREMENTS.md maps exactly those three requirements to Phase 02. No orphaned Phase-02 requirement was found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| Phase 02 implementation/test paths | — | No `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, placeholder, or empty-rendering delivery marker was found by the targeted scan. | ℹ️ Info | No debt-marker blocker. |
| `backend/app/backtest/factor.py` | 412 | Polars `DataFrame.pivot(columns=...)` deprecation warning during focused tests | ℹ️ Info | Existing upstream API deprecation; it did not invalidate the verified Phase 02 contracts. |
| Frontend build | — | Existing Rollup chunk-size advisory for bundles over 500 kB | ℹ️ Info | Build succeeds; unrelated bundle-splitting optimization, not a Phase 02 functional gap. |

## Gaps Summary

No blocking gaps remain. The prior failure — strategy execution evidence existed server-side but could not be explicitly retained by a browser user — is closed. The current implementation preserves only a validated current-task SSE handle, requires an explicit immutable retention action, rejects malformed/missing/stale/old-task outcomes without promotion, refreshes retained comparison candidates, and passes the required keyboard/responsive coverage.

---
_Verified: 2026-07-11T10:46:05Z_
_Verifier: Claude (gsd-verifier)_
