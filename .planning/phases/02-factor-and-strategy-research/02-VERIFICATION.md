---
phase: 02-factor-and-strategy-research
verified: 2026-07-11
status: gaps_found
verification_ref: 86b7b8ff6477d06deb15acb6cfea6247fb2c04ea
---

# Phase 02 Verification

## Status: gaps_found

Phase 02 has automated evidence for its implemented paths, but it cannot be certified because two reproducibility/correctness gaps affect the governed factor-evaluation and strategy-experiment contracts. No human-only verification remains; both gaps require code and regression-test fixes.

## Scope and evidence basis

| Evidence | Result |
| --- | --- |
| `uv run --project backend pytest` over the seven Phase 2 research modules | **Passed:** 32 focused backend tests passed. |
| `pnpm --dir frontend exec playwright test e2e/phase2-research.spec.ts` | **Passed:** 1 deterministic desktop scenario passed; the mobile project was intentionally skipped because the scenario is desktop-only. |
| `pnpm --dir frontend build` | **Passed.** |
| Static verification of DSL evaluation partitioning | **Failed:** stateful factor operations are evaluated on the full panel without the required date/symbol partitions. |
| Static verification of strategy experiment manifests | **Failed:** strategy snapshots omit the governed-data revision/fingerprint comparison needs. |

## Requirement traceability

| Requirement | Plans | Status | Concrete evidence / gap |
| --- | --- | --- | --- |
| FACT-01 | 01, 02, 04, 05 | gaps_found | The restricted DSL, immutable revisions, discovery, evaluation API, and UI exist. `backend/app/research/evaluation.py:287-290` applies compiled DSL expressions over the full multi-symbol/date panel, while `backend/app/research/factor_dsl.py:488-495` compiles `rank`, `zscore`, and `rolling_mean` without `over("date")` or `over("symbol")`. Valid multi-symbol rolling/ranking expressions can cross symbol boundaries or omit cross-sectional date partitioning, making evaluated evidence incorrect. |
| FACT-02 | 02, 04, 05 | passed | Focused backend tests cover proposal-only hypothesis drafts, parser validation, explicit reviewed-draft promotion, controlled evaluation, and retention gating; the deterministic browser scenario covers the user-visible review path. |
| FACT-03 | 03, 04, 05 | gaps_found | Immutable retained catalog and transparent comparison paths exist, but `backend/app/api/backtest.py:344-355` creates strategy experiment manifests without a governed-data revision/fingerprint. `backend/app/research/catalog.py:488-492` can warn only from manifest fields, so revised strategy inputs cannot be distinguished or surfaced as a comparability warning. |

## Required gap closure

1. Partition DSL stateful semantics explicitly: cross-sectional `rank`/`zscore` by date and time-series `rolling_mean` by symbol in the governed evaluation contract. Add deterministic multi-symbol, multi-date tests proving no state leaks across either boundary.
2. Include a stable governed-data revision/fingerprint in each trusted strategy execution manifest. Add a comparison test proving changed strategy input revisions emit the existing data-manifest compatibility warning.

## Human verification

None. The remaining failures are deterministic code-level contracts and must be closed before UAT or Phase 2 completion.
