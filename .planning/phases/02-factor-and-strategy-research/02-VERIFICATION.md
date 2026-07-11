---
phase: 02-factor-and-strategy-research
verified: 2026-07-11T08:37:41Z
status: gaps_found
score: 8/9 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  gaps_closed:
    - "Stateful DSL rank/zscore date partitions and rolling_mean symbol partitions now prevent multi-symbol/multi-date state leakage."
    - "Registered-strategy snapshots now carry server-derived governed-data revision/fingerprint identity and surface the existing comparison warning."
  gaps_remaining:
    - "The Backtest strategy workspace does not expose or invoke the existing server-issued strategy-execution retention endpoint, so a browser user cannot make a completed strategy run comparable."
  regressions: []
gaps:
  - truth: "A researcher can retain a completed registered-strategy execution from the Backtest workspace and compare it with other retained experiments."
    status: failed
    reason: "The backend creates a trusted execution handle and the typed API client exposes its retention endpoint, but no frontend consumer preserves the SSE research handle, invokes the endpoint, or renders a strategy-retention action."
    artifacts:
      - path: "frontend/src/pages/backtest/StrategyBacktest.tsx"
        issue: "It starts the SSE backtest and stores the result, but contains no strategy-execution retention mutation or UI action."
      - path: "frontend/src/lib/backtestTask.ts"
        issue: "It handles progress, done, and error SSE events only; the server's research execution-handle event is discarded."
      - path: "frontend/src/lib/api.ts"
        issue: "retainStrategyResearchExecution() exists but has no call site outside its declaration."
    missing:
      - "Preserve the server-issued research execution handle from strategy POST/SSE completion."
      - "Expose an explicit retain action for completed strategy evidence and invalidate experiment/candidate query keys after retention."
      - "Add a deterministic browser scenario covering strategy run, explicit retention, and retained comparison."
---

# Phase 2: Factor And Strategy Research Verification Report

**Phase Goal:** Researchers can turn factor hypotheses into comparable, reproducible evaluations using the governed market-data foundation.
**Verified:** 2026-07-11T08:37:41Z
**Status:** gaps_found
**Re-verification:** Yes — after two prior gap-closure plans.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | A researcher can validate only the restricted factor DSL, save immutable revisions, and receive deterministic explained similarity candidates. | ✓ VERIFIED | `factor_dsl.py` parses before constructing Polars expressions and dispatches only allowlisted AST nodes; `factor_registry.py` appends revisions and deterministically sorts candidates. `test_factor_dsl.py`, `test_factor_registry.py`, and API coverage passed. |
| 2 | `rank` and `zscore` evaluate only among same-date peers in a multi-symbol governed panel. | ✓ VERIFIED | `factor_dsl.py:488-492` fixes both operations to `.over("date")`. Deterministic two-symbol/two-date compiler and managed-artifact tests assert exact reset values. |
| 3 | `rolling_mean` evaluates only over each symbol's chronological observations. | ✓ VERIFIED | `factor_dsl.py:493-495` uses `.rolling_mean(..., min_samples=1).over("symbol")`; the compiler and evaluation-artifact regressions prove no preceding-symbol window leakage. |
| 4 | Stored factors are evaluated through the governed `BacktestEngine` boundary, retain explicit configuration/input manifests/artifacts, and report separate Pearson IC and Spearman RankIC evidence. | ✓ VERIFIED | `evaluation.py` loads declared fields once through `load_panel`, sorts `symbol,date`, emits managed signal records, and computes both metric families. `test_factor_evaluation.py` passed under the focused suite. |
| 5 | A natural-language hypothesis remains a validated, provenance-bearing draft until explicit review, successful evaluation, and explicit retention. | ✓ VERIFIED | `hypotheses.py` has no registry/evaluator/artifact collaborators; `research.py` verifies an issued reviewed draft before creating a revision; API and browser coverage passed. |
| 6 | Every successful registered-strategy run derives a stable governed-panel revision/fingerprint from the actual `load_panel` result. | ✓ VERIFIED | `strategy.py:292-312` normalizes schema/source characteristics and SHA-256 hashes them. The strategy regression proves identical, row-count-only, observed-window-only, and schema-only cases. |
| 7 | Synchronous and SSE strategy completion persist only server-derived identity fields and reject forged client provenance. | ✓ VERIFIED | `backtest.py:329-431` allocates a server handle, copies only `revision`/`fingerprint` from the result manifest, and finalizes through the catalog. Handoff tests cover POST, SSE, forged payload rejection, failed, and cancelled runs. |
| 8 | Retained comparisons show all immutable evidence dimensions and warn, without a winner, when otherwise equivalent strategy snapshots differ only in governed-data identity. | ✓ VERIFIED | `catalog.py:416-501` compares retained completed snapshots and recognizes `revision`/`fingerprint`; `test_experiment_catalog.py` asserts the sole governed-data warning and no winner/ranking. |
| 9 | A browser user can retain a completed strategy execution and select it for comparison. | ✗ FAILED | `StrategyBacktest.tsx` calls `startBacktest()` only; `backtestTask.ts` drops the SSE `research` handle; `api.ts` exposes `retainStrategyResearchExecution()` with no frontend caller. The deterministic browser scenario covers factor evidence only. |

**Score:** 8/9 truths verified (0 present-but-behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/app/research/factor_dsl.py` | Closed parsed DSL with fixed stateful partition semantics | ✓ VERIFIED | Substantive compiler dispatch; date/symbol partitions are fixed rather than caller-controlled. |
| `backend/app/research/evaluation.py` | Governed factor evaluation, reproducibility manifest, IC/RankIC, artifacts | ✓ VERIFIED | Uses `BacktestEngine.load_panel`, vectorized Polars evaluation, artifact service, and explicit result evidence. |
| `backend/app/research/{factor_registry,repository,catalog,hypotheses}.py` | Immutable revisions/snapshots, retention gates, comparison, proposal-only hypothesis boundary | ✓ VERIFIED | Substantive domain code wired to research routes and SQLite migration lifecycle. |
| `backend/app/backtest/strategy.py` | Deterministic governed identity for successful registered-strategy runs | ✓ VERIFIED | Source-derived revision/fingerprint is attached immediately after governed panel loading. |
| `backend/app/api/{research,backtest}.py` | Validated research routes and trusted strategy handoff | ✓ VERIFIED | Existing FastAPI host wires factor workflows, server handles, POST, and SSE finalization. |
| `frontend/src/pages/backtest/{FactorBacktest,ResearchLibrary,ExperimentComparison}.tsx` | Factor review/evidence/retention and transparent retained comparison | ✓ VERIFIED | Browser scenario completed the factor review-to-retention-to-comparison flow. |
| `frontend/src/pages/backtest/StrategyBacktest.tsx` and `frontend/src/lib/backtestTask.ts` | User-visible strategy-retention handoff | ✗ UNWIRED | No code consumes the research execution handle or invokes `retainStrategyResearchExecution()`. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `ParsedFactor.compile()` | `FactorEvaluationService._evaluate_panel()` | Fixed Polars expression, governed sort, and managed `signals.json` | ✓ WIRED | End-to-end partition test reads exact signal-artifact factors. |
| `StrategyBacktestService.run()` | `ExperimentCatalog.record_strategy_backtest()` | Result manifest → `_strategy_input_manifest()` → server finalization | ✓ WIRED | Both synchronous and SSE handoff tests pass with only server-issued identity. |
| `ExperimentCatalog._compatibility_warnings()` | retained strategy comparison | immutable manifest `revision`/`fingerprint` | ✓ WIRED | Focused catalog regression verifies one identity-only warning and no ranking. |
| `FactorBacktest` | research API → catalog → comparison UI | typed API and TanStack Query mutations | ✓ WIRED | Deterministic Playwright scenario passes. |
| `StrategyBacktest` | `/api/research/strategy-executions/{handle}/retain` | SSE/POST handle preservation and explicit user action | ✗ NOT_WIRED | The endpoint exists but the workspace and SSE task client never call it. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| Factor evaluation | `_factor`, `_forward_return`, signal records | `BacktestEngine.load_panel()` → sorted Polars panel → managed artifact bundle | Yes | ✓ FLOWING |
| Registered strategy snapshot | `governed_input_manifest` | successful `StrategyBacktestService.run()` result → trusted finalizer → immutable SQLite snapshot | Yes | ✓ FLOWING |
| Strategy workspace retention | execution handle / retained experiment | SSE emits `event: research`, but `backtestTask.ts` ignores it | No consumer path | ✗ DISCONNECTED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| DSL safety, revisions, factor evaluation partitions/metrics, catalog gates/warnings, hypothesis review, API gates, trusted strategy POST/SSE handoff | `uv run --project backend pytest backend/tests/research/test_factor_dsl.py backend/tests/research/test_factor_registry.py backend/tests/research/test_factor_evaluation.py backend/tests/research/test_experiment_catalog.py backend/tests/research/test_hypothesis_workflow.py backend/tests/research/test_research_api.py backend/tests/research/test_strategy_experiment_handoff.py backend/tests/backtest/test_strategy_backtest_correctness.py -q` | 41 passed in 3.91s; 7 existing Polars `pivot(columns=...)` deprecation warnings | ✓ PASS |
| User-visible factor validation, reviewed-draft gate, IC/RankIC visibility, explicit retention, and mismatch warning | `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts` | Desktop scenario passed; its explicitly desktop-only mobile project was skipped | ✓ PASS |
| User-visible strategy retention | Static client/data-flow check | No handle listener, retention mutation caller, or CTA exists | ✗ FAIL |

### Probe Execution

No phase-declared or conventional Phase 2 probe script was found; no probe execution was required.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| FACT-01 | 02-01, 02-02, 02-04, 02-05, 02-06 | Restricted factor definition, immutable storage/discovery, and governed IC/RankIC evaluation | ✓ SATISFIED | Safe AST compiler, revision registry, controlled evaluation API, partition regressions, and factor browser flow are present and exercised. |
| FACT-02 | 02-02, 02-04, 02-05 | Natural-language hypothesis becomes a validated reviewed factor, is backtested, then explicitly retained | ✓ SATISFIED | Proposal-only gateway, reviewed-draft server verification, completed/retained catalog gates, API tests, and desktop scenario are exercised. |
| FACT-03 | 02-03, 02-04, 02-05, 02-07 | Researchers can run factor or registered-strategy experiments and compare retained provenance/evidence | ✗ BLOCKED | Backend strategy provenance/retention/comparison is correct, but the required strategy user flow is disconnected from the Backtest workspace. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| Phase 2 implementation files | — | No unreferenced `TBD`, `FIXME`, or `XXX` delivery markers found in the scanned Phase 2 paths | ℹ️ Info | No debt-marker blocker. |
| `backend/app/backtest/factor.py` | 412 | Polars `DataFrame.pivot(columns=...)` deprecation warning during focused tests | ℹ️ Info | Existing library API warning; it did not fail the Phase 2 behaviors exercised here. |

## Former Gap Closure Evidence

This report supersedes the prior verification report's two deterministic code-level gaps:

1. **Stateful factor DSL partitions — closed.** `rank`/`zscore` are date-partitioned and `rolling_mean` is symbol-partitioned in the closed AST-to-Polars compiler. The multi-symbol/multi-date tests inspect compiler results and immutable managed signals, so neither cross-date cross-sectional contamination nor cross-symbol rolling leakage is merely inferred.
2. **Strategy governed-data identity/comparability warning — closed.** Successful strategy results derive deterministic schema/source-reference identities at `load_panel`; API finalizers propagate only server-produced recognized fields for both POST and SSE; retained comparison emits the existing governed-data mismatch warning without a winner.

## Gaps Summary

The former two gaps are resolved, but the Phase 2 goal is still not achieved end-to-end for registered strategies. The backend correctly creates a completed, unretained strategy experiment and exposes a typed retention endpoint; however, the existing strategy workspace discards the server-issued handle and has no explicit retain action. Consequently, a browser researcher cannot make their own completed strategy backtest eligible for the existing retained comparison UI.

No later roadmap phase explicitly schedules this missing Phase 2 workspace wiring, so it is not deferred.

---
_Verified: 2026-07-11T08:37:41Z_
_Verifier: Claude (gsd-verifier)_
