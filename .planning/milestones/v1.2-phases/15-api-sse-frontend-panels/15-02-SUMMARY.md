# Plan 15-02 Summary — Wave 0: Server-Owned DTOs + Route Scaffolding + Test Fixtures

**Status:** complete · **Committed:** dbbfe47

## What landed

- `contracts/panels.py`: all five panels' DTOs pinned as server-owned strict contracts (option-a, one module): OptimizationRunDTO, AttributionEvidenceDTO, RebalancePlanDTO, PaperTransitionDTO, PaperStateDTO, PaperActionRequest/Response, FactorRevisionDTO, AdmissionVerdictDTO, ModelDefinitionDTO, ModelCompositeDTO, WfPlanDTO, WfFoldDTO, WfSearchRunDTO, WfValidatedStrategyDTO, WfEnsembleDTO. Every model `extra="forbid"`, frozen.
- `api/research_panels.py` + `api/portfolio_panels.py`: both typed read routers scaffolded with `response_model` on every route; registered in `main.py`.
- `tests/api/conftest.py`: `panel_app` TestClient fixture with `app.state` repository injection over a tmp_path migrated operational.db (`research_repository` / `portfolio_repository` / `operational`).
- RED scaffold tests in both panel test files (empty-list 200s, strict-DTO extra-field rejection, 404 on missing run/plan).
- 15-UI-SPEC.md status → approved (design contract gate).

## Evidence

- Scaffold cases provably RED before 15-01/15-03/15-04 landed bodies; all turned green in the breadth plans.
- `pytest tests/api/test_research_panels.py tests/api/test_portfolio_panels.py` green at phase end (40 tests at wave-2 close, before 15-05 added 4 more).

## Deviations

None.
