# Plan 15-01 Summary — Tracer: Optimization Panel End-to-End (UI-02 spine)

**Status:** complete · **Committed:** 2d0ab4b

## What landed

- `contracts/panels.py`: `OptimizationRunDTO` (strict `extra="forbid"`, frozen) — id, objective, as_of, universe, model_id, input_snapshot_sha256, expected_return_method, risk_model(+detail), constraint_stack, solver name/version/options, problem_status, failure_reason, output_weights, baseline_weights, output_sha256, weights_artifact_relative_path, created_at.
- `api/portfolio_panels.py`: `GET /api/portfolio/optimization-runs` (limit ge=1 le=500 fail-closed, objective/as_of filters) + `GET /optimization-runs/{run_id}` (404 on missing), both `response_model=OptimizationRunDTO`.
- `api.ts`: `listOptimizationRuns` / `getOptimizationRun` typed methods; `queryKeys.ts`: `optimizationRuns` / `optimizationRun` factories.
- `pages/portfolio/Optimization.tsx`: immutable-run list (objective chip, status chip, failure reason banner for failed runs) + detail with output weights **always rendered with baselines (min-vol + HRP)** for max_sharpe / baseline-carrying runs — never "optimal" alone; expandable constraint stack / solver / risk-model audit sections; mono identifiers + checksums.
- `router.tsx` route + `Portfolio.tsx` nav entry (研究面板 → 优化运行).

## Evidence

- `tests/api/test_portfolio_panels.py` tracer cases green (fixture run → DTO → route → panel spine; failed run renders failure_reason; missing id → 404; strict DTO rejects extra field).
- Frontend `tsc -b` + `vite build` clean.
- Zero-execution-UI grep gate == 0 matches.

## Deviations

None.
