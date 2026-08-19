# v3.0 Tech Debt Registry — Phase 51 (BASE-04)

**Created:** 2026-08-19
**Source:** `.planning/milestones/v3.0-MILESTONE-AUDIT.md` tech_debt section
**Purpose:** Document each v3.0 tech debt item with its resolution or explicit closure.

## Tech Debt Items

### 1. Tier-2 Stress Matrix (Phase 50)

**Item:** Tier-2 stress matrix axes (calendar-regime, coverage, symbol-subset) deferred — returns bounded `422 NotImplementedError`; Tier-1 fee/slippage/rebalance delivered.

**Current State:** `backend/app/research/run_service.py:1254` raises `NotImplementedError("stress axis '{axis}' is not implemented (Tier-2 deferred)")` for `{"calendar_regime", "coverage", "symbol_subset"}`. Tier-1 stress (fee/slippage/rebalance) is fully implemented as pure arithmetic re-projection in `projections.py:stress_matrix`.

**Resolution: Closed (explicit)**
- Rationale: Tier-2 axes require either regime-labeled data (calendar-regime), universe coverage metadata (coverage), or per-symbol decomposition (symbol-subset) that are not part of the governed run contract. The governed Alpha Factory pipeline is deterministic and append-only; adding Tier-2 would require either new data dimensions or re-scoring through the signal chain, violating the "no re-score" boundary.
- The 422 is a fail-closed boundary, not a missing feature. Users who need regime/coverage analysis can use the walk-forward (Phase 13) or composite model (Phase 10) pathways which already have proper data isolation.
- No action needed in v3.1.

### 2. Vitest Unit Suites (Phase 50)

**Item:** 50-03 vitest unit suites runnable-ready but not executed (vitest not a dep; e2e is executable proof).

**Current State:** Fixed in this Phase 51 (BASE-02). Vitest 3.2.7 installed as devDependency. 51 unit tests across `format.test.ts` (43) and `cn.test.ts` (8) pass. `"test": "vitest run"` added to `package.json` scripts. Docker build now runs `pnpm test` as a hard gate before `pnpm build`.

**Resolution: Resolved**
- Vitest is now a dependency, the test suite runs, and it is wired into the Docker build (CI).
- Future phases add tests alongside features.

### 3. Partial Stage 1 Success Labeling (Phase 48)

**Item:** Partial Stage 1 success labeling linked to AF-REQ-25 Phase 50+ for full degradation UI.

**Current State:** `backend/app/research/agent_stage1.py:245-270` implements partial labeling (R2): degraded responses are distinctly labeled so they cannot masquerade as clean complete ones. Only server-confirmed hypotheses with `is_partial=True` flag reach the client.

**Resolution: Closed (explicit)**
- The partial labeling itself is complete and tested. The "full degradation UI" aspect (AF-REQ-25) was about making degradation visible in the Alpha Workbench — this was delivered in Phase 50's `AlphaWorkbench.tsx` which shows provider failure/degradation status.
- v3.1 Phase 52 (AUDIT-01..05) will further unify provider degradation visibility into the global audit page, making it available beyond the Alpha Workbench.
- No additional action needed in Phase 51.

### 4. Cost Diagnostic Turnover×Rate Approximation (Phase 47)

**Item:** Cost diagnostic is turnover×rate approximation (documented not execution P&L); full strategy backtest cost model remains in Phase 34 backtest engine.

**Current State:** `backend/app/research/projections.py:stress_matrix` projects Tier-1 stress as pure arithmetic re-projection of stored turnover at alternative fee/slippage/rebalance rates. `backend/app/backtest/strategy.py:463` tracks `turnover_rate` as a dependency. The cost diagnostic is intentionally a diagnostic, not an execution P&L.

**Resolution: Closed (explicit)**
- The turnover×rate approximation is a deliberate design choice: the stress matrix is a "what-if" re-projection, not a re-run of the backtest. It reads the frozen turnover from the immutable run record and applies alternative rates arithmetically.
- The full backtest cost model (with execution-level P&L) lives in the Phase 34 backtest engine (`backend/app/backtest/engine.py`) which is the authoritative source for real costs.
- These are two different things serving two different purposes: the stress matrix is for sensitivity analysis; the backtest engine is for actual P&L.
- No action needed in v3.1.

### 5. Post-Deploy Real LLM Validation (Phase 50)

**Item:** Deployment-time real LLM validation was not performed in v3.0 (offline fixtures were the executable proof).

**Current State:** Phase 51 (BASE-03) addresses this by creating a real LLM two-stage analysis smoke script that can be run against a deployed instance.

**Resolution: In progress (Phase 51 BASE-03)**
- Smoke scripts being created: real LLM two-stage analysis, Provider degradation, SSE reconnection.
- Each script outputs explicit PASS/FAIL, never silently skipping.

## Summary

| # | Item | Phase | Status | Resolution |
|---|------|-------|--------|------------|
| 1 | Tier-2 stress matrix 422 | 50 | Closed | Deliberate fail-closed boundary; no action |
| 2 | Vitest not a dep | 50 | Resolved | Phase 51 BASE-02: vitest installed, 51 tests pass, wired into Docker build |
| 3 | Partial Stage 1 labeling | 48 | Closed | Labeling complete; UI delivered in Phase 50; Phase 52 further unifies |
| 4 | Cost diagnostic approximation | 47 | Closed | Intentional design; full cost model in backtest engine |
| 5 | Post-deploy real LLM validation | 50 | In progress | Phase 51 BASE-03: smoke scripts being created |

**All items have a documented resolution or explicit closure with rationale.**

---
*Last updated: 2026-08-19 — Phase 51 BASE-04*
