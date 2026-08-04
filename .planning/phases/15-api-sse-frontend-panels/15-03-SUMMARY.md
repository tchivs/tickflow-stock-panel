# Plan 15-03 Summary — Backtest Panels Breadth: ModelLibrary + WalkForward (UI-01)

**Status:** complete · **Committed:** 3316241

## What landed

- `api/research_panels.py` route bodies over `ResearchRepository`:
  - `GET /api/research/factor-catalog` — current revisions with admission status (from `latest_admission_verdicts`) and **DISTINCT `ic` + `rank_ic` fields** (from `latest_experiment_metrics`), never conflated.
  - `GET /factors/{revision_id}/verdict`, `GET /models` + `/models/{model_id}/composites`, `GET /wf/plans`, `GET /wf/folds` (plan_id/is_oos filters), `GET /wf/search-runs`, `GET /wf/validated`, `GET /wf/ensembles`.
  - Per-DTO mappers (column → field projection), not naive key filters; `WfPlanDTO` surfaces OOS reservation (oos_start/oos_end from fold geometry + `pinned`).
- `research/repository.py`: `latest_admission_verdicts` + `latest_experiment_metrics` (batch read surfaces).
- `api.ts` typed methods (`listFactors`/`getAdmissionVerdict`/`listModels`/`listModelComposites`/`listWfPlans`/`listWfFolds`/`listWfSearchRuns`/`listWfValidated`/`listWfEnsembles`) + `queryKeys.ts` `panel*` factories (distinct `research-panel` prefix, no cache collision with the legacy research workspace).
- `pages/backtest/ModelLibrary.tsx` — factor catalog table (IC column + RankIC column separate, admission chip, expandable verdict evidence) + composite models (weighting, revision lineage, weights, input snapshot sha256, expandable composites with mean IC).
- `pages/backtest/WalkForward.tsx` — plan list (geometry + pinned chip), plan detail (train/gap/test, **reserved OOS visually distinct + labeled "仅评估一次"**), fold breakdown, OOS-scored search runs, validated strategies (gate chips + OOS score), ensembles.
- `pages/Backtest.tsx`: 模型库 + 走步验证 tabs wired into the workspace switcher (arrow-key navigation included).

## Evidence

- `tests/api/test_research_panels.py` breadth green (projection, IC≠RankIC distinctness, null-evidence handling, verdict seeding, folds OOS filtering, search/validated/ensemble seeding) — 21 tests.
- Frontend `tsc -b` + `vite build` clean; live smoke test against the real operational.db: catalog returned 7 real revisions, wf plan + 18 folds rendered in-browser.
- Zero-execution-UI grep gate == 0 matches in both panels.

## Deviations

- **Route path:** the plan specified `GET /api/research/factors` for the panel catalog, but the legacy research router already owns that exact path (registered earlier in `main.py`, returning a `{"factors": [...]}` dict envelope consumed by `api.researchFactors` in ResearchLibrary/FactorBacktest). FastAPI first-match-wins shadowed the typed route in production (the panel-only test app masked it). The panel catalog moved to `/api/research/factor-catalog`; the legacy surface is untouched. `getAdmissionVerdict` kept `/factors/{revision_id}/verdict` (no collision).
