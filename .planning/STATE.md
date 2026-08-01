---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: End-to-End Factor Portfolio Pipeline — in progress
current_phase: 12
current_phase_name: Risk Models & Attribution
status: executing
stopped_at: Completed 11-05-PLAN.md
last_updated: "2026-08-01T23:01:51.953Z"
last_activity: 2026-08-02
last_activity_desc: Phase 11 complete, transitioned to Phase 12
progress:
  total_phases: 6
  completed_phases: 0
  total_plans: 3
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-31)

**Core value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.
**Current focus:** v1.2 End-to-End Factor Portfolio Pipeline (Phases 10-15); roadmap created 2026-07-31

## Current Position

Phase: 12 — Risk Models & Attribution
Plan: Not started
Status: Ready to execute
Last activity: 2026-08-02 — Phase 11 complete, transitioned to Phase 12

Progress: [██████████] 100%

## v1.2 Phase Summary

| Phase | Requirements | Status |
|-------|-------------|--------|
| 10 Factor Library & Multi-Factor Model | FACT-01..06 | In progress (10-01..10-06 complete) |
| 11 Portfolio Construction & Optimization | PFOL-01..04 | In progress (11-01, 11-02, 11-03, 11-04, 11-05, 11-06 complete) |
| 12 Risk Models & Attribution | RSK-01..03 | Not started |
| 13 Walk-Forward Validation & Parameter Search | WFWD-01..03 | Not started |
| 14 Output & Boundary (RebalancePlan + Paper Rebalance) | RBAL-01..02 | Not started |
| 15 API/SSE + Frontend Panels | UI-01..02 | Not started |

## Performance Metrics

**Velocity:**

- Total plans completed: 70 (v1.0: 66, v1.1: 4)
- v1.1 plans: 4 plans, all complete

**v1.1 Key Metrics:**

- Backend tests: 961 passed, 3 skipped, 0 failed (down from 9 failures)
- Test warnings: 143 → 84 (all remaining are pytest GC artifacts, 0 application-code warnings)
- Frontend: tsc clean, vite build clean
- Visual regression: 4 baselines committed (desktop + mobile)

**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 10 P10-04 | 45 | 5 tasks | 6 files |
| Phase 10 P10-05 | 4500 | 7 tasks | 8 files |
| Phase 10 P10-06 | 4680 | 4 tasks | 4 files |
| Phase 11 P11-02 | 12 | 4 tasks | 13 files |
| Phase 11 P11-01 | 45 | 12 tasks | 13 files |
| Phase 11 P11-03 | 21 | 2 tasks | 3 files |
| Phase 11 P11-04 | 44 | 4 tasks | 4 files |
| Phase 11 P11-05 | 55 | 5 tasks | 6 files |
| Phase 11 P11-06 | 75 | 3 tasks | 7 files |

## Accumulated Context

### v1.1 Decisions

- [Phase 6]: Release evidence paths resolve dynamically from repo root; Linux evidence producer runs natively (no WSL dependency); historical approval-paperwork gate removed from sync_kronos.py — supply is fail-closed on SHA-256/identity.
- [Phase 7]: Polars `collect(engine="streaming")` and `check_sortedness=False` on `join_asof` are safe given pre-sorted data; SSL ResourceWarning is a pytest `gc.collect()` artifact, not an application leak.
- [Phase 8]: Optional supply path was already complete from v1.0; Phase 8 verified it meets all criteria (24 tests pass).
- [Phase 9]: Visual regression uses `maxDiffPixelRatio: 0.01` — 1% pixel drift threshold.

### v1.2 Decisions

- [Roadmap]: Phases 10-15 follow research SUMMARY.md structure; every v1.2 requirement maps to exactly one phase (20/20, no orphans).
- [Roadmap]: v1.2 continues v1.1 numbering (no reset); phase IDs are sequential (`phase_naming: sequential`).
- [Roadmap]: No execution authority is a hard acceptance criterion for Phase 14 — RebalancePlan is a research-only artifact; paper rebalance is a separate approved state machine (PA_Agent ApprovalTicket pattern).
- [Roadmap]: Shared factor signal chain (`signal_chain.py`) lands in Phase 10 and is consumed identically by evaluation, models, walk-forward, expected returns, and live as-of plans (anti train/serve skew).
- [Roadmap]: Industry cap deferred until a governed industry mapping exists (fail-closed); max-Sharpe is an explicit non-default option with baselines rendered.

### Pending Todos

None.

### Blockers/Concerns

- [v1.2 / Phase 11]: Optimizer engine choice — cvxpy 1.9.2 vs scipy SLSQP — unresolved; must be decided during Phase 11 planning (cvxpy addition must pass the package-legitimacy approval gate).
- [v1.2 / Phase 10]: Point-in-time universe snapshot design is the largest open data gap; without it Phases 11-13 silently inherit survivorship bias. Flag during Phase 10 planning.
- [v1.2 / Phase 10]: Runtime install verification deferred — local `.venv` is empty; scipy 1.17.1 promotion to base deps and sklearn 1.8.0 lazy import must be verified in Phase 10, not assumed.
- [v1.2 / Phase 13]: Walk-forward fold geometry (train/test size, gap) must be calibrated to available A-share history during Phase 13 planning.

## Deferred Items

| Category | Item | Status |
|----------|------|--------|
| verification | Real Windows/WSL Phase 06 evidence run | Deferred by user; native Linux verified 659/659 |
| Optional enhancement | Shadow Account, thesis tracking, and Kronos forecasting | Phase 5 / v2 |
| Supply identity | Human approval paperwork | Removed for personal project |

## Session Continuity

Last session: 2026-08-01T18:58:01.000Z
Stopped at: Completed 11-05-PLAN.md
Resume file: None

## Operator Next Steps

- Run `/gsd-plan-phase 10` to plan Phase 10 (Factor Library & Multi-Factor Model)
- Run the phase gate (full backend suite) after all Wave 2/3/4 plans (11-05, 11-06) — all Phase 11 plans complete; run `cd backend && .venv/bin/python -m pytest -x` before /gsd-verify-work

## Decisions

- [Phase ?]: PIT universe: membership_fingerprint hashes the sorted per-date [symbol,date] frame
- [Phase ?]: Candidate trails: every admission verdict (admitted AND rejected) carries provenance, evaluation_run_id, ExperimentSnapshot.id, and ordered gate results; evaluation references are optional when no catalog/artifact_service is wired
- [Phase ?]: IC-correlation dedup: per-date IC Pearson on the val window, series aligned on sorted val dates; degenerate constant series yield 0.0; discover_similar untouched
- [Phase ?]: evaluation.py delegates fully to FactorSignalChain.compute; legacy _evaluate_panel/_rebalance/_required_columns/_correlation_series deleted; parse_factor/compile_factor no longer imported
- [Phase ?]: Composite weights derive from catalog-recorded mean IC for the same revision + resolved config (cross-module integrity); a revision with missing recorded mean IC fails the build closed, never equal-weight silently
- [Phase ?]: Composite outputs are snapshot-immutable: input_snapshot_sha256 binds (sorted revision_ids, weighting, membership_fingerprint, panel fingerprints, mean ICs); output written via EvaluationArtifactService.write_bundle (O_EXCL + fsync + sha256); factor_model_composites rows append-only bound by input_snapshot_sha256
- [Phase ?]: Admitted-factor catalog entries are summary-only (coverage mean + series, finite counts, ast/shape signature) with revision lineage (factor_id, revision_id, revision_number); full factor-value matrices are an anti-feature; the composite model is a first-class catalog record with its latest snapshot reference
- [Phase ?]: cvxpy==1.9.2 pinned to base deps (one-way door, pre-approved) — solver results version-sensitive, audit cites cp.__version__
- [Phase ?]: portfolio_optimization_runs migrated per RESEARCH schema (one-way door, pre-approved) — CHECK enums + sha256 + failed-reason invariant + immutability triggers
- [Phase 11]: Min-vol QP uses budget equality cp.sum(w) == 1 - min_cash (fully-deployed floor) — the analytical scaffold test requires full deployment; the cash floor (1 - sum(w) >= min_cash) holds exactly, and pitfall 7 double-counting is avoided.
- [Phase 11]: Clarabel 1.9.2 solver options are tol_gap_abs/tol_gap_rel (not OSQP eps_abs/eps_rel, per Wave 0 finding); options dict recorded verbatim in solver_options_json.
- [Phase 11]: HRP baseline rendered scaled by (1 - min_cash) so it compares apples-to-apples with the QP under the cash floor.
- [Phase 11]: run_optimization accepts a pre-resolved snapshot dict (model_id/input_snapshot_sha256/composite_snapshot_id) in 11-01; the production catalog seam (load_composite_snapshot) lands in 11-05.
- [Phase 11]: solver_path=['CLARABEL','OSQP'] fallback is resolved manually (_solve_problem): cvxpy 1.9.2 native solver_path raises SolverError when all solvers return non-optimal, so the manual path retries OSQP only on SolverError (solver crash) and records any status the first solver returns verbatim (pitfall 4 — infeasible recorded as-is, never promoted).
- [Phase 11]: recorded options dict stays policy-verbatim (solver_path + eps_abs/eps_rel in solver_options_json); _solve_kwargs maps tolerance keys to the active solver's namespace (CLARABEL tol_gap_abs/tol_gap_rel, OSQP eps_abs/eps_rel).
- [Phase 11]: w_prev run_id reference reads the prior run's weights ARTIFACT via read_artifact with output_sha256 checksum verification (never trusts the DB JSON alone); missing symbols align to 0.0, extra dropped; constraint_stack_json records turnover_reference + turnover_reference_detail.
- [Phase 11]: max_sharpe explicit non-default — render_baselines=False raises ValueError (never silent); every max_sharpe run records baseline_weights_json={'min_volatility','hrp'} both rendered to (1 - min_cash); mu is an explicit run_optimization parameter (snapshot binding lands in 11-05).
- [Phase 11]: Expected returns are consumed BY SNAPSHOT — catalog.get_composite_model → checksum-verified artifact load (sha256(bytes) == output_sha256, frozen_panel fail-closed pattern) → as_of cross-section → mu; run row's input_snapshot_sha256 == composite's input_snapshot_sha256 (audit root, cross-module integrity). Never a live module hand-off (pitfall 5).
- [Phase 11]: run_optimization fail-closed wrapper records SnapshotBindingError / ValueError / RuntimeError / cp.error.SolverError as failed runs with failure_reason (PFOL-04) — never a silent abort; model-not-found FK-degrades the row (model_id→None, expected_return_method→'none') so the append-only INSERT satisfies the factor_model_models FK.
- [Phase 11]: The lookahead guard keys on artifact DATA COVERAGE (earliest [symbol,date,composite] date), not created_at — a backtest composite's created_at is later than its data dates (RESEARCH.md 'as_of precedes ... the panel window' clause).
- [Phase 11]: list_optimization_runs gains a limit cap (default 200, positive-int fail-closed) for the Phase 15 API; objective/as_of filters + ORDER BY created_at, id preserved.
- [Phase 11]: Industry-cap fail-closed gate wired through run_optimization — assert_industry_cap_unavailable(requested=req.industry_cap is not None) at the top of _run_optimization_impl; a requested cap raises ValueError("industry mapping unavailable") caught by the 11-05 wrapper and recorded as a failed run (pitfall 8, T-11-06). constraint_stack_json records industry_cap: null when unrequested (HRP / non-optimal / success paths).
- [Phase 11]: Covariance artifact + sha256 in risk_model_json — covariance_sha256(cov) hashes the canonical 8-decimal JSON (byte-identical to write_bundle's covariance.json rounding); artifact bytes hash to the recorded digest, so Phase 12 loads covariance.json by checksum (covariance_artifact_relative_path = research_artifacts/<run_id>/covariance.json).
- [Phase ?]: HRP objective outputs baseline == weights (no QP to compare against) — objective=hrp run row: solver_name/solver_version=n/a, solver_options_json={}, problem_status=optimal, still append-only immutable
- [Phase ?]: hrp_portfolio runs the same fail-closed PSD gate as the QP path — non-PSD covariance raises ValueError (pitfall 9), never silent
- [Phase ?]: solver_path=['CLARABEL','OSQP'] fallback resolved manually (_solve_problem): cvxpy 1.9.2 native solver_path raises SolverError when all solvers return non-optimal, so OSQP is retried only on SolverError (solver crash) and any status the first solver returns is recorded verbatim (pitfall 4)
- [Phase ?]: Recorded options dict stays policy-verbatim (solver_path + eps_abs/eps_rel in solver_options_json); _solve_kwargs maps tolerance keys to the active solver's namespace (CLARABEL tol_gap_abs/tol_gap_rel, OSQP eps_abs/eps_rel)
- [Phase ?]: w_prev run_id reference reads the prior run's weights ARTIFACT via read_artifact with output_sha256 checksum verification (never trusts the DB JSON alone); missing symbols align to 0.0, extra dropped; constraint_stack_json records turnover_reference + turnover_reference_detail
- [Phase ?]: max_sharpe explicit non-default — render_baselines=False raises ValueError (never silent); every max_sharpe run records baseline_weights_json={'min_volatility','hrp'} both rendered to (1 - min_cash); mu is an explicit run_optimization parameter (snapshot binding lands in 11-05)
