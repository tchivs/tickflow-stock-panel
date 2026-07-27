---
phase: 02
slug: factor-and-strategy-research
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-11
validated: 2026-07-27T08:59:43+08:00
audited_plans: [02-01, 02-02, 02-03, 02-04, 02-05, 02-06, 02-07, 02-08]
requirements: [FACT-01, FACT-02, FACT-03]
gaps_found: 0
manual_only: 0
---

# Phase 2 — Nyquist Validation

> Retrospective requirement-to-test audit for all eight completed Phase 02 plans. This replaces the historical pre-execution strategy that covered only Plan 02-08 and still marked its tasks pending.

## Validation Verdict

**VALIDATED — NYQUIST COMPLIANT**

FACT-01, FACT-02, and FACT-03 each have automated domain/API coverage and a current green user-visible browser path where applicable. The audit found no missing or partial requirement coverage, so no new tests or manual-only exceptions were required.

## Test Infrastructure

| Layer | Framework / config | Current audit command | Observed result |
|-------|--------------------|-----------------------|-----------------|
| Backend domain and API | Pytest; `backend/pyproject.toml` | From `backend/`: `.\.venv\Scripts\python.exe -m pytest tests\research\test_factor_dsl.py tests\research\test_factor_registry.py tests\research\test_factor_evaluation.py tests\research\test_experiment_catalog.py tests\research\test_hypothesis_workflow.py tests\research\test_research_api.py tests\research\test_strategy_experiment_handoff.py tests\backtest\test_strategy_backtest_correctness.py -q` | **42 passed** in 56.69s; 7 existing Polars `pivot(columns=...)` deprecation warnings |
| TypeScript | TypeScript project references; `frontend/tsconfig.json` | From `frontend/`: `.\node_modules\.bin\tsc.cmd -b` | **PASS** in 21.3s |
| Browser integration | Playwright Test 1.61.1; `frontend/playwright.config.ts` | From `frontend/`: `node .\node_modules\@playwright\test\cli.js test e2e/phase2-research.spec.ts --project=desktop-chromium` | **6 passed** in 78.3s |

All commands are deterministic and offline. They use temporary SQLite/application-data roots and controlled browser route fixtures; no provider credentials, external database, production data lake, or network service is required.

## Requirement Coverage

| Requirement | Source plans | Automated evidence | Classification |
|-------------|--------------|--------------------|----------------|
| FACT-01 | 02-01, 02-02, 02-04, 02-05, 02-06 | Restricted DSL rejection/canonicalization/partition semantics, immutable revision history and similarity, governed evaluation with distinct IC/RankIC and immutable artifacts, API workflow, and browser validate/save/evaluate/retain flow | **COVERED** |
| FACT-02 | 02-02, 02-04, 02-05 | Governed factor evidence/artifacts, proposal-only hypothesis validation, issued-draft review gate, provenance-bound revision creation, explicit retention, and browser evidence disclosure | **COVERED** |
| FACT-03 | 02-03, 02-04, 02-05, 02-07, 02-08 | Immutable completed-only catalog and comparison, server-only strategy handoff, governed panel identity, SSE-handle lifecycle, explicit retention/rejection, comparison warnings/no winner, and responsive keyboard workflow | **COVERED** |

`REQUIREMENTS.md` maps exactly FACT-01, FACT-02, and FACT-03 to Phase 02. No orphaned or unmapped Phase 02 requirement was found.

## Automated Command Registry

The per-task map references these current commands:

- **B1 — Phase 02 backend:** the eight-module Pytest command in Test Infrastructure.
- **T1 — TypeScript:** `.\node_modules\.bin\tsc.cmd -b` from `frontend/`.
- **P1 — Phase 02 browser:** `node .\node_modules\@playwright\test\cli.js test e2e/phase2-research.spec.ts --project=desktop-chromium` from `frontend/`.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Primary automated proof | Command | Status |
|---------|------|------|-------------|-------------------------|---------|--------|
| 02-01-01 | 01 | 1 | FACT-01 | Unsafe syntax rejection, canonical expression/signature, governed dependency compilation, date/symbol partitions | B1 | ✅ green |
| 02-01-02 | 01 | 1 | FACT-01 | Fresh migration, insert-only revisions, preserved history, stable explained similarity | B1 | ✅ green |
| 02-01-03 | 01 | 1 | FACT-01 | Combined DSL and registry domain boundary suite | B1 | ✅ green |
| 02-02-01 | 02 | 2 | FACT-01, FACT-02 | Governed loading, explicit config/manifest, separate Pearson IC and Spearman RankIC | B1 | ✅ green |
| 02-02-02 | 02 | 2 | FACT-02 | Checksummed run-bound artifacts and no-replace collision behavior | B1 | ✅ green |
| 02-02-03 | 02 | 2 | FACT-01, FACT-02 | Invalid-before-load, empty-data failure, metric truthfulness, artifact integrity | B1 | ✅ green |
| 02-03-01 | 03 | 2 | FACT-03 | Immutable factor/strategy snapshots and explicit one-time retention | B1 | ✅ green |
| 02-03-02 | 03 | 2 | FACT-03 | Completed/validated/retained-only candidates, deltas, warnings, no winner | B1 | ✅ green |
| 02-03-03 | 03 | 2 | FACT-03 | Diagnostic exclusion, artifact binding, source-mutation immutability | B1 | ✅ green |
| 02-04-01 | 04 | 3 | FACT-02 | Proposal-only provider boundary, strict draft JSON/DSL validation, provenance | B1 | ✅ green |
| 02-04-02 | 04 | 3 | FACT-01, FACT-02, FACT-03 | Manual and reviewed-draft API workflows, explicit retention/comparison, trusted strategy handoff | B1 | ✅ green |
| 02-04-03 | 04 | 3 | FACT-01, FACT-02, FACT-03 | API gate, impersonation, forged/stale/failed/cancelled handle regressions | B1 | ✅ green |
| 02-05-01 | 05 | 4 | FACT-01, FACT-02, FACT-03 | Typed research/evidence contracts and cache ownership compile | T1 | ✅ green |
| 02-05-02 | 05 | 4 | FACT-01, FACT-02 | Browser manual factor and reviewed-draft lifecycle with six evidence disclosures | P1 | ✅ green |
| 02-05-03 | 05 | 4 | FACT-03 | Retained history, explicit candidate selection, mismatch warning and no-winner comparison | P1 | ✅ green |
| 02-05-04 | 05 | 4 | FACT-01, FACT-02, FACT-03 | Deterministic full researcher browser scenario | P1, T1 | ✅ green |
| 02-06-01 | 06 | 3 | FACT-01 | Same-date rank/zscore and per-symbol rolling mean compiler regression | B1 | ✅ green |
| 02-06-02 | 06 | 3 | FACT-01 | Partition semantics through governed evaluation and managed signal artifacts | B1 | ✅ green |
| 02-07-01 | 07 | 4 | FACT-03 | Stable governed-panel revision/fingerprint derived at `load_panel` boundary | B1 | ✅ green |
| 02-07-02 | 07 | 4 | FACT-03 | POST/SSE server-only manifest handoff and forged evidence rejection | B1 | ✅ green |
| 02-07-03 | 07 | 4 | FACT-03 | Governed-data mismatch warning isolation and equal-identity control | B1 | ✅ green |
| 02-08-01 | 08 | 5 | FACT-03 | Matching-task SSE handle preservation; malformed/no-done/old-task clearing | P1, T1 | ✅ green |
| 02-08-02 | 08 | 5 | FACT-03 | Single-flight explicit retention, immutable returned state, query refresh, retry-safe rejection | P1, T1 | ✅ green |
| 02-08-03 | 08 | 5 | FACT-03 | 1440/1024/375 keyboard Scenario 5, comparison, pagination, 44px action, horizontal table access | P1 | ✅ green |

## Focused Scenario Ledger

| Scenario | Observable proof | Current status |
|----------|------------------|----------------|
| Manual factor lifecycle | Validate restricted expression, save immutable revision, render similarity, evaluate distinct IC/RankIC evidence, retain explicitly | ✅ automated |
| Reviewed hypothesis lifecycle | Provider draft remains non-persistent; exact issued draft and provenance are required before revision/evaluation/retention | ✅ automated |
| Immutable experiment comparison | Only completed validated retained snapshots are selectable; all evidence dimensions and incompatibility warnings render without winner/ranking | ✅ automated |
| Stateful DSL correctness | `rank`/`zscore` reset per date and `rolling_mean` resets per symbol through compiler and governed artifact output | ✅ automated |
| Trusted strategy provenance | Actual governed panel identity is deterministic and survives both synchronous and SSE server-only catalog handoff | ✅ automated |
| Strategy retention lifecycle | Matching SSE `research` handle enables one explicit retention POST only after successful completion; stale 409 remains retryable and unpromoted | ✅ automated |
| Ineligible strategy terminals | Malformed nested result, missing matching `done`, cancelled/failed, and delayed old-task success never promote the current task | ✅ automated |
| Responsive keyboard contract | Factor/strategy tabs, evidence disclosures, retention, candidate comparison, pagination, and table scrolling pass at 1440px, 1024px, and 375px | ✅ automated |

## Wave 0 and Execution State

Historical Wave 0 prerequisites are present and operational:

- [x] `backend/pyproject.toml` and the existing Pytest environment.
- [x] `frontend/tsconfig.json` and the installed local TypeScript compiler.
- [x] `frontend/playwright.config.ts` with the existing `desktop-chromium` project and local Vite server.
- [x] `frontend/e2e/phase2-research.spec.ts` with deterministic Phase 02 route fixtures.

There is no pending Wave 0 work. All Plans 02-01 through 02-08 have summaries with `status: complete`, the phase verification report is `status: passed` with 12/12 truths, and every row in this validation map was rerun or covered by the current aggregate commands above.

## Manual-Only Verifications

None. All required Phase 02 behaviors have deterministic automated coverage. Visual screenshots are not used as substitutes for assertions; browser checks use accessible roles/names, native keyboard events, DOM geometry, and observed network-backed state transitions.

## Validation Audit 2026-07-27

| Metric | Count |
|--------|-------|
| Plans audited | 8 |
| Tasks mapped | 24 |
| Requirements audited | 3 |
| Gaps found | 0 |
| Gaps resolved with new tests | 0 |
| Escalated / manual-only | 0 |
| Backend tests passed | 42 |
| Browser tests passed | 6 |
| TypeScript builds passed | 1 |

The only runtime notices were seven pre-existing Polars deprecation warnings for `DataFrame.pivot(columns=...)`; they do not weaken any Phase 02 assertion and are not a Nyquist gap.

## Validation Sign-Off

- [x] All eight completed plans and summaries were audited.
- [x] Every Phase 02 task has an automated command.
- [x] FACT-01, FACT-02, and FACT-03 are covered by current green tests.
- [x] Backend domain/API, TypeScript, and browser integration commands passed.
- [x] No missing, partial, flaky, or manual-only requirement remains.
- [x] No new test was added without a demonstrated coverage gap.
- [x] `nyquist_compliant: true` and `status: validated` reflect current execution evidence.

**Approval:** validated on 2026-07-27.
