---
phase: 11-portfolio-construction-optimization
plan: phase-plan
type: execute
requirements: [PFOL-01, PFOL-02, PFOL-03, PFOL-04]
wave_summary:
  wave_0: [11-02]
  wave_1: [11-01]
  wave_2: [11-03, 11-04]
  wave_3: [11-05]
  wave_4: [11-06]
must_haves:
  truths:
    - "Researcher can build sample covariance from a governed panel and inspect any PSD repair as an explicit recorded step (method, epsilon, eigenvalues before/after) in the immutable run record — never silent (PFOL-01)."
    - "Researcher can solve a long-only minimum-volatility portfolio and an HRP baseline side by side; max-Sharpe is available only as an explicit non-default option with baselines rendered alongside (PFOL-02)."
    - "Researcher can apply the constraint stack — long-only bounds, per-instrument cap, minimum cash, convex turnover cost — and an industry cap fails closed until a governed industry mapping exists (PFOL-03)."
    - "Researcher can retrieve any optimization run as an immutable record carrying input-snapshot SHA-256, expected-return method, risk model, solver name/version/options, problem status, and output weights; failed runs retain their failure reason (PFOL-04)."
    - "The composite expected-return input is consumed by snapshot (checksum-verified artifact + input_snapshot_sha256), never a live module hand-off; a missing/tampered artifact or a lookahead as_of fails the run closed with a recorded reason."
    - "Every run's output weights are checksum-verified immutable artifacts (O_EXCL + fsync + sha256) under the run's namespace; solver/options/status are recorded verbatim against pinned cvxpy 1.9.2."
  artifacts:
    - path: backend/app/portfolio/risk.py
      provides: "sample_covariance / check_psd / repair_psd with mandatory PSD provenance (method, epsilon, eigenvalues before/after)"
    - path: backend/app/portfolio/optimizer.py
      provides: "solve_min_vol / solve_max_sharpe QP (Clarabel default, solver_path fallback) with full audit capture + PSD fail-closed gate + run_optimization orchestrator"
    - path: backend/app/portfolio/constraints.py
      provides: "policy constants (cap/min-cash/turnover/PSD-epsilon/risk-aversion) + industry-cap fail-closed gate (phase-11-policy-v1)"
    - path: backend/app/portfolio/repository.py
      provides: "record_optimization_run / get_optimization_run / list_optimization_runs append-only methods over portfolio_optimization_runs"
    - path: backend/app/portfolio/artifacts.py
      provides: "PortfolioArtifactService — O_EXCL + fsync + sha256 weight/covariance artifacts under research_artifacts/<run_id>/"
    - path: backend/app/portfolio/schemas.py
      provides: "OptimizationRequest Pydantic DTO + SOLVER_OPTIONS_ALLOWLIST (V5 input validation)"
    - path: backend/app/portfolio/snapshot.py
      provides: "load_composite_snapshot — catalog.get_composite_model → checksum-verified artifact load → as_of cross-section (fail-closed)"
    - path: backend/app/portfolio/hrp.py
      provides: "deterministic HRP baseline over scipy.cluster.hierarchy (single linkage, optimal_ordering) + baseline rendering scaled by (1 - min_cash)"
    - path: backend/app/operational/migrations.py
      provides: "portfolio_optimization_runs append-only table + as_of index + no_update/no_delete triggers (PFOL-04)"
    - path: backend/pyproject.toml
      provides: "cvxpy==1.9.2 base dependency (exact pin; solver results are version-sensitive)"
    - path: backend/tests/portfolio/
      provides: "test_risk / test_optimizer / test_hrp / test_repository / test_snapshot_binding / test_pipeline + conftest fixtures"
  key_links:
    - from: portfolio/optimizer.py
      to: portfolio/risk.py
      via: "solve refuses to build the QP when a repaired covariance lacks PSD provenance — fail-closed gate, never a silent clip"
      pattern: "ensure_psd_provenance"
    - from: portfolio/snapshot.py
      to: research/catalog.py
      via: "expected returns consumed by snapshot (artifact bytes verified by output_sha256 + input_snapshot_sha256); never calls build_composite"
      pattern: "get_composite_model"
    - from: portfolio/repository.py
      to: operational/migrations.py
      via: "portfolio_optimization_runs append-only row; run.input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256 (cross-module integrity)"
      pattern: "record_optimization_run"
    - from: portfolio/optimizer.py
      to: portfolio/artifacts.py
      via: "weights persisted O_EXCL + fsync + sha256 under research_artifacts/<run_id>/; run row stores output_sha256 + artifact relative path"
      pattern: "PortfolioArtifactService"
    - from: portfolio/risk.py
      to: portfolio/optimizer.py
      via: "sample covariance from the governed panel (BacktestEngine.load_panel + per-date universe filter); PSD gate is a hard prerequisite for cp.quad_form"
      pattern: "repair_psd"
---

# Phase 11: Portfolio Construction & Optimization — Executable Plan

## Phase Goal

Researchers can build a sample covariance from governed data with explicit PSD repair, solve auditable long-only min-vol and HRP-baseline portfolios under a constraint stack, and retrieve every run as an immutable record.

## Scope

**In scope (PFOL-01..04):** sample covariance + explicit PSD check/repair with mandatory provenance; long-only minimum-volatility (default) + HRP baseline portfolios; max-Sharpe as an explicit non-default option with baselines rendered alongside; the constraint stack (long-only bounds, per-instrument cap, minimum cash, convex turnover penalty); an industry-cap fail-closed gate; immutable append-only run records (input-snapshot SHA-256, expected-return method, risk model, solver name/version/options, problem status, output weights; failed runs retained with reason); checksum-verified weight/covariance artifacts; composite-by-snapshot input binding (never a live module hand-off); cvxpy 1.9.2 as a new base dependency.

**Out of scope:** the risk-model suite beyond sample covariance (semi/exponential/Ledoit-Wolf + PSD provenance → Phase 12), drawdown/exposure/contribution attribution (Phase 12), walk-forward (Phase 13), RebalancePlan discretization (Phase 14), frontend panels (Phase 15). No execution authority anywhere. Deferred ideas from `11-CONTEXT.md` (industry cap until a governed industry mapping exists, Black-Litterman returns, max-Sharpe as first-class objective, short selling, auto-rebalance, ML-based expected returns OPT-01) MUST NOT appear in any task. PyPortfolioOpt / skfolio / riskfolio-lib are design references only — never runtime dependencies.

## Source Coverage Audit

| Source | ID | Required behavior or constraint | Plans | Status |
|---|---|---|---|---|
| GOAL | Phase 11 | Sample covariance + explicit PSD repair, auditable min-vol/HRP under the constraint stack, immutable run records | 11-01..11-06 | COVERED |
| REQ | PFOL-01 | Sample covariance from a governed panel with PSD check; any repair is an explicit recorded step (method, epsilon, eigenvalues before/after) in the immutable run record | 11-01, 11-06 | COVERED |
| REQ | PFOL-02 | Long-only min-vol portfolio + HRP baseline; max-Sharpe only as explicit non-default with baselines alongside | 11-01, 11-03, 11-04 | COVERED |
| REQ | PFOL-03 | Constraint stack: long-only bounds, per-instrument cap, minimum cash, convex turnover cost; industry cap fail-closed until a governed industry mapping exists | 11-01, 11-04, 11-06 | COVERED |
| REQ | PFOL-04 | Every run immutable with input-snapshot SHA-256, expected-return method, risk model, solver name/version/options, problem status, output weights; failed runs retain reason | 11-01, 11-02, 11-05 | COVERED |
| RESEARCH | Dependencies | cvxpy==1.9.2 base pin + empty-.venv Wave 0 gate; scipy stays HRP-clustering-only, never the general optimizer | 11-02 | COVERED |
| RESEARCH | Migrations | portfolio_optimization_runs append-only + CHECKs + immutability triggers appended to the MIGRATIONS tuple | 11-02 | COVERED |
| RESEARCH | Snapshot binding | catalog.get_composite_model → checksum-verified artifact load → as_of cross-section; fail-closed on every mismatch | 11-05 | COVERED |
| RESEARCH | Test scaffolding | 5 new test files + conftest (Wave 0 gaps); extend tests/test_operational_migrations.py + tests/research/test_models.py | 11-02, 11-05 | COVERED |
| CONTEXT | D-* | All locked decisions implemented (cvxpy primary QP, min-vol default, HRP baseline, PSD never silent, immutable runs, constraint stack, composite-by-snapshot); deferred ideas excluded | 11-01..11-06 | COVERED |

**Exclusions (not gaps):** deferred ideas in `11-CONTEXT.md`; Phase 12-15 scope; PyPortfolioOpt/skfolio/riskfolio-lib as runtime deps (design spec only); MLflow / external experiment tracking; storing full factor value matrices.

## Plan List

- [ ] 11-01: **Tracer** — end-to-end optimization pipeline on a fixture panel: composite snapshot → sample covariance + PSD gate → cvxpy min-vol under the constraint stack → immutable run record (PFOL-01..04)
- [ ] 11-02: **Wave 0 foundations** — cvxpy 1.9.2 base dep + empty-.venv gate, portfolio_optimization_runs migration, 5 new test files + conftest (RED scaffolds)
- [ ] 11-03: **HRP baseline** — deterministic hierarchical risk parity over scipy linkage + baseline rendering scaled by (1 − min_cash) (PFOL-02)
- [ ] 11-04: **Min-vol breadth + max-Sharpe non-default** — solver_path fallback, w_prev equal-weight anchor, max-Sharpe opt-in + baselines-rendered contract (PFOL-02/03)
- [ ] 11-05: **Snapshot binding + run-record breadth** — catalog.get_composite_model → checksum-verified artifact → as_of cross-section, run_optimization orchestrator, list_optimization_runs, fail-closed paths (PFOL-04)
- [ ] 11-06: **Constraint hardening + artifact breadth** — industry-cap fail-closed gate, covariance artifact + sha256 in risk_model_json (PFOL-01/03)

## Wave Structure

| Wave | Plans | Purpose |
|------|-------|---------|
| 0 | 11-02 | Foundations: cvxpy dependency + empty-.venv gate, runs-table migration, test scaffolding — prerequisites for the tracer. Two one-way-door checkpoint gates. |
| 1 | 11-01 | The tracer: prove the whole optimization spine end-to-end on a fixture before any breadth. |
| 2 | 11-03, 11-04 | HRP baseline ∥ min-vol/max-Sharpe breadth — parallel plans, zero file overlap. |
| 3 | 11-05 | Snapshot binding + run-record breadth — the production catalog seam and every fail-closed path recorded as failed runs. |
| 4 | 11-06 | Constraint hardening + artifact breadth — industry-cap fail-closed gate, covariance sha256 + artifact for Phase 12. |

## Artifacts this phase produces

| Artifact | Kind | Provides |
|---|---|---|
| `sample_covariance` / `check_psd` / `repair_psd` (risk.py) | functions | governed-panel sample covariance + explicit PSD check/repair with mandatory provenance (method/epsilon/eigenvalues before/after) (PFOL-01) |
| `solve_min_vol` / `solve_max_sharpe` / `run_optimization` (optimizer.py) | functions | Clarabel-default convex QP with solver_path fallback, full audit capture (status/solver_name/solve_time/num_iters/options/cvxpy_version/solver_version), PSD fail-closed gate, orchestrator (PFOL-02/03/04) |
| `hrp_weights` / `render_baseline` / `hrp_portfolio` (hrp.py) | functions | deterministic HRP baseline (scipy linkage single + optimal_ordering, recursive bisection inverse-variance) scaled by (1 − min_cash) (PFOL-02) |
| Policy constants + `assert_industry_cap_unavailable` (constraints.py) | constants + function | `phase-11-policy-v1` provenance: cap 0.10 / min-cash 0.05 / turnover-coef 0.0014 / PSD epsilon 1e-10 / risk-aversion 1.0; industry cap fail-closed gate (PFOL-03) |
| `PortfolioRepository` (repository.py) | class | record_optimization_run / get_optimization_run / list_optimization_runs — append-only, canonical JSON, sha256/status/failure-reason validation (PFOL-04) |
| `PortfolioArtifactService` (artifacts.py) | class | O_EXCL + fsync + sha256 weight/covariance artifacts under `research_artifacts/<run_id>/` + checksum-verified reads (PFOL-04) |
| `OptimizationRequest` + `SOLVER_OPTIONS_ALLOWLIST` (schemas.py) | Pydantic model + constant | strict DTO validation + fixed solver-options whitelist (V5) |
| `load_composite_snapshot` (snapshot.py) | function | catalog.get_composite_model → checksum-verified artifact → as_of cross-section; fail-closed paths (PFOL-04) |
| `portfolio_optimization_runs` (migrations.py) | SQLite table | append-only run records + CHECK enums + sha256 length checks + failed⇔failure_reason invariant + no_update/no_delete triggers (PFOL-04) |
| `cvxpy==1.9.2` (pyproject.toml) | base dependency | pinned QP engine with bundled OSQP/Clarabel/SCS/HiGHS (auditable `cp.__version__` per run) |
| tests/portfolio/{test_risk,test_optimizer,test_hrp,test_repository,test_snapshot_binding,test_pipeline,conftest}.py | test files | per-requirement unit contracts + end-to-end tracer proof (Wave 0 scaffolds turned green per plan) |

## Requirement → Plan Mapping

| Requirement | Behavior | Plans | Verification command |
|---|---|---|---|
| PFOL-01 | Sample covariance + PSD check/repair provenance (never silent) | 11-01, 11-06 | `pytest tests/portfolio/test_risk.py -q --tb=short` |
| PFOL-02 | Min-vol QP + HRP baseline; max-Sharpe non-default with baselines | 11-01, 11-03, 11-04 | `pytest tests/portfolio/test_optimizer.py tests/portfolio/test_hrp.py -q --tb=short` |
| PFOL-03 | Constraint stack (cap/min-cash/turnover); industry cap fail-closed | 11-01, 11-04, 11-06 | `pytest tests/portfolio/test_optimizer.py -q --tb=short` |
| PFOL-04 | Immutable run records incl. failure reason; snapshot binding | 11-01, 11-02, 11-05 | `pytest tests/portfolio/test_repository.py tests/portfolio/test_snapshot_binding.py tests/portfolio/test_pipeline.py -q --tb=short` |
| Migration | New table + CHECKs + triggers, forward-only idempotence | 11-02 | `pytest tests/test_operational_migrations.py -q --tb=short` |
| Cross-module | Composite snapshot == artifact bytes identified by input_snapshot_sha256 | 11-05 | `pytest tests/research/test_models.py -q --tb=short` |

All commands run from `backend/` with the project interpreter: `cd backend && .venv/bin/python -m pytest …`.

---

# Plan 11-01 — Tracer: End-to-End Optimization Pipeline (PFOL-01..04)

**wave:** 1 · **depends_on:** [11-02] · **autonomous:** true
**requirements:** [PFOL-01, PFOL-02, PFOL-03, PFOL-04]
**files_modified:**
- backend/app/portfolio/risk.py (new)
- backend/app/portfolio/optimizer.py (new)
- backend/app/portfolio/constraints.py (new)
- backend/app/portfolio/repository.py (new)
- backend/app/portfolio/artifacts.py (new)
- backend/app/portfolio/schemas.py (new)
- backend/app/portfolio/hrp.py (new)
- backend/tests/portfolio/test_risk.py (new — RED scaffold turned green)
- backend/tests/portfolio/test_optimizer.py (new — RED scaffold turned green)
- backend/tests/portfolio/test_hrp.py (new — RED scaffold turned green)
- backend/tests/portfolio/test_repository.py (new — RED scaffold turned green)
- backend/tests/portfolio/test_pipeline.py (new — end-to-end tracer test)

## Objective

Prove the complete Phase 11 spine on a fixture panel, end to end, before any breadth work: load a composite snapshot by checksum-verified artifact → build sample covariance from the governed panel → PSD check + repair with mandatory provenance → solve the long-only min-vol QP under the full constraint stack (per-instrument cap, min cash, convex turnover penalty) with Clarabel → persist an immutable append-only run record (with output weights + baseline HRP weights + PSD provenance in risk_model_json) → read it back. Every artifact on this path is immutable and checksum-bound.

Purpose: This is the architecture's keel. It forces the PSD-before-cvxpy ordering, the snapshot-bound input contract, the append-only run-record discipline, and the artifact checksum discipline into existence on the first commit, and catches a dead-end (e.g., indefinite covariance reaching cp.quad_form, run-row write failure, artifact checksum drift) before ten layers are committed. Functionality is fixture-scoped (StubBacktestEngine panel + fixture composite artifact + tmp_path SQLite repository + tmp_path artifact root); no architectural gap is left.
Output: `risk.py`, `optimizer.py`, `constraints.py`, `repository.py`, `artifacts.py`, `schemas.py`, `hrp.py` — each a minimal but production-shaped single path — and the green test files that lock the contracts.

## Context

- @.planning/phases/11-portfolio-construction-optimization/11-RESEARCH.md — ground truth: `## cvxpy QP Formulation`, `## PSD Check/Repair`, `## Immutable Run Records`, `## Constraint Stack`, `## Input Snapshot Binding`, `## Verification Plan`
- @.planning/phases/11-portfolio-construction-optimization/11-CONTEXT.md — locked decisions D-* (cvxpy primary QP, min-vol default, HRP baseline, PSD never silent, immutable runs, constraint stack, composite-by-snapshot)
- backend/app/portfolio/__init__.py — empty package init; the module docstring pattern (know/don't-know) per CONVENTIONS.md
- backend/app/research/catalog.py — `get_composite_model` (L451+), `CompositeModelRecord` (L172-205): model_id / input_snapshot_sha256 / latest_composite = {id, output_sha256, artifact_relative_path, input_snapshot_sha256, created_at}
- backend/app/research/artifacts.py — `EvaluationArtifactService._write_json` (L76-118): O_EXCL + fsync + sha256 pattern to mirror in `portfolio/artifacts.py`
- backend/app/operational/migrations.py — `MIGRATIONS` tuple + immutability-trigger convention (factor_model_composites_no_update/_no_delete, L1573-1576); the `portfolio_optimization_runs` table lands in 11-02
- backend/app/backtest/engine.py — `BacktestEngine.load_panel` (L191-200) governed-data seam; `MatcherConfig` fee model (L33-76) that the turnover coefficient derives from
- backend/tests/research/conftest.py — `StubBacktestEngine` + `fixture_panel` + `fixture_membership` + `research_repository` fixtures (the fixture panel pattern to mirror in `tests/portfolio/conftest.py`)

## Tasks

- **build: Create `portfolio/constraints.py` — policy constants + industry-cap gate**
  - Files: backend/app/portfolio/constraints.py
  - Read first: 11-RESEARCH.md `## Constraint Stack` (constants + provenance), backend/app/backtest/engine.py `MatcherConfig` (L33-76 — the fee model the turnover coefficient derives from)
  - Action: Define module constants with provenance comment `provenance: "phase-11-policy-v1"`: `PER_INSTRUMENT_CAP_DEFAULT = 0.10` (10% single-name cap), `MIN_CASH_DEFAULT = 0.05` (5% cash floor — `cp.sum(w) <= 1 - MIN_CASH_DEFAULT` is a floor, never strict equality), `TURNOVER_COEF_DEFAULT = 0.0014` (round-trip proxy: commission 2×2bp + slippage 2×5bps from `MatcherConfig`), `PSD_EPSILON_DEFAULT = 1e-10`, `MAX_SHARPE_RISK_AVERSION = 1.0`, `INDUSTRY_CAP_ENABLED = False` (fail-closed — the sector JOIN is not implemented). Add `def assert_industry_cap_unavailable(requested: bool) -> None` that raises `ValueError` when `requested` is True with the exact message "industry mapping unavailable" (never silently ignored). Module docstring states know/don't-know per CONVENTIONS.md.
  - Verify: `cd backend && .venv/bin/python -c "from app.portfolio.constraints import assert_industry_cap_unavailable; \
    assert_industry_cap_unavailable(False); \
    import pytest; \
    with pytest.raises(ValueError, match='industry mapping unavailable'): assert_industry_cap_unavailable(True)"`
  - Done: The five policy constants exist with `phase-11-policy-v1` provenance; requesting an industry cap raises `ValueError("industry mapping unavailable")`; the module imports without pandas at module top.

- **build: Create `portfolio/risk.py` — sample covariance + PSD check/repair (never silent)**
  - Files: backend/app/portfolio/risk.py
  - Read first: 11-RESEARCH.md `## PSD Check/Repair` (exact signatures + provenance contract), backend/app/research/universe.py (PIT per-date membership seam the panel window filters through)
  - Action: Implement `sample_covariance(returns: np.ndarray, *, dropna: bool = True) -> np.ndarray` — cross-sectional `np.cov(returns, rowvar=False)` over the common all-finite window. Implement `check_psd(cov: np.ndarray, *, tol: float = 1e-8) -> tuple[float, np.ndarray]` — symmetrize `(cov + cov.T) / 2`, return `(float(eigvals.min()), eigvals)` from `np.linalg.eigvalsh`. Implement `repair_psd(cov, *, method: str = "eigen_clip", epsilon: float = PSD_EPSILON_DEFAULT) -> tuple[np.ndarray, dict]` — `np.linalg.eigh`, clip eigenvalues to `max(eigvals, epsilon)`, reconstruct `(eigvecs * clipped) @ eigvecs.T`, re-symmetrize; return `(repaired, provenance)` where provenance is the dict with all four mandatory keys: `method`, `epsilon`, `min_eigenvalue_before`, `eigenvalues_before`, `eigenvalues_after` (research example). The module docstring states know/don't-know; never call `np.clip` on eigenvalues anywhere outside this module (pitfall 1 warning sign).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_risk.py -q --tb=short`
  - Done: `sample_covariance` matches the NumPy reference on a fixture returns matrix; `check_psd` reports the true minimum eigenvalue; `repair_psd` returns a PSD matrix plus the full provenance dict with eigenvalues before/after.

- **build: Create `portfolio/hrp.py` — deterministic HRP baseline**
  - Files: backend/app/portfolio/hrp.py
  - Read first: 11-RESEARCH.md `## HRP Baseline` (the full ~50-line reference implementation)
  - Action: Implement the four module-private helpers `_cov_to_corr`, `_cluster_weights` (inverse-variance within cluster), `_cluster_variance`, `_recursive_bisect` exactly per RESEARCH.md, plus the public `hrp_weights(cov: np.ndarray) -> np.ndarray` and `render_baseline(weights: np.ndarray, *, min_cash: float) -> np.ndarray` (scale a full-investment HRP vector by `(1 - min_cash)` so the comparison with the QP is apples-to-apples). `hrp_weights` computes correlation distance `squareform(np.sqrt((1 - corr) / 2), checks=False)`, `linkage(dist, method="single", optimal_ordering=True)`, `leaves_list(link).astype(int)`, then `_recursive_bisect`. Deterministic: identical inputs → identical weights (pure NumPy recursion). The PSD gate from `risk.py` MUST run before `hrp_weights` (a negative diagonal breaks `_cluster_weights` — pitfall 9); the caller (optimizer) enforces that ordering.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_hrp.py -q --tb=short`
  - Done: HRP weights on a 3-asset correlated fixture respect the known cluster ordering, sum to 1 before scaling, scale to `(1 - min_cash)` after `render_baseline`, and are deterministic across two calls.

- **build: Create `portfolio/repository.py` — append-only run records**
  - Files: backend/app/portfolio/repository.py
  - Read first: backend/app/research/repository.py (`_json` canonical serialization L37-44, `_record` JSON un-wrapping L46-57, transactional `with self._connection() as connection, connection:` inserts), 11-RESEARCH.md `## Immutable Run Records` (column contract + repository methods)
  - Action: Implement `PortfolioRepository` sharing the operational database file. Module-private `_json(value, field)` = `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` (canonical JSON) and `_record(row)` un-wraps the JSON columns (`risk_model_json`→`risk_model`, `constraint_stack_json`→`constraint_stack`, `solver_options_json`→`solver_options`, `output_weights_json`→`output_weights`, `baseline_weights_json`→`baseline_weights`). `__init__(self, db_path: Path)` calls `migrate_operational_db(connection)` (the runs table lands in 11-02). `record_optimization_run(**fields)` — atomic INSERT inside `with self._connection() as connection, connection:`; validates every sha256 field via `re.fullmatch(r"[0-9a-f]{64}")`, validates `problem_status` is set, raises `ValueError` when `problem_status in ("failed", "solver_error")` and `failure_reason` is missing. `get_optimization_run(run_id) -> dict | None` and `list_optimization_runs(*, objective=None, as_of=None) -> list[dict]` (ordered `created_at, id`; filters on objective/as_of). Every insert is INSERT-only; the triggers (11-02) block UPDATE/DELETE.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_repository.py -q --tb=short`
  - Done: `record_optimization_run` inserts a row whose JSON columns round-trip through `get_optimization_run`; a `failed` run without `failure_reason` raises `ValueError`; a non-hex sha256 raises `ValueError`; `list_optimization_runs` filters by objective and as_of.

- **build: Create `portfolio/artifacts.py` — immutable weight/covariance artifacts**
  - Files: backend/app/portfolio/artifacts.py
  - Read first: backend/app/research/artifacts.py (`_write_json` O_EXCL + fsync + sha256 L76-118, `_namespace` O_EXCL creation), backend/app/backtest/frozen_panel.py (`load` checksum-verified read pattern L75-137)
  - Action: Implement `PortfolioArtifactService(root: Path)` with `self.root = Path(root).resolve() / "research_artifacts"`. `write_bundle(*, run_id: str, weights: dict[str, float], baseline_weights: dict[str, float], covariance: np.ndarray | None = None) -> list[ArtifactDescriptor]` — validate `run_id` matches `re.compile(r"[0-9a-f]{32}\Z")`, create the namespace dir O_EXCL (fail if it exists), write each file via a private `_write_json(filename, obj)` that opens with O_EXCL, writes canonical JSON bytes, fsyncs the file, then fsyncs the directory; return `ArtifactDescriptor` records with `checksum_sha256` computed from the exact bytes written. Names: `weights.json`, `baseline_weights.json`, and `covariance.json` when covariance is provided (stored as a list-of-lists). `read_artifact(run_id, filename) -> bytes` verifies the descriptor checksum against the bytes and raises on mismatch (frozen_panel pattern). Weights JSON is serialized with `sort_keys=True` so `output_sha256` is canonical (research `_json` convention).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py -q --tb=short` (the artifact assertions — O_EXCL namespace, checksum-verified reads — live in test_pipeline; run `pytest tests/portfolio -q --tb=short` for the full set)
  - Done: `write_bundle` creates an O_EXCL namespace with fsynced, checksummed weights/baseline/covariance files; a second write to the same run_id fails (O_EXCL); `read_artifact` returns bytes only when the checksum matches, else raises.

- **build: Create `portfolio/schemas.py` — strict DTO + solver-options whitelist**
  - Files: backend/app/portfolio/schemas.py
  - Read first: 11-RESEARCH.md `## cvxpy QP Formulation` (options contract), backend/app/api/research.py (Pydantic request-model conventions, enums + date validation)
  - Action: Define `Objective = Literal["min_volatility", "hrp", "max_sharpe"]` and the frozen `OptimizationRequest` Pydantic model with fields `objective: Objective = "min_volatility"` (default min-vol — PFOL-02), `as_of: date`, `universe: str = "cn-a-share"`, `model_id: str | None = None` (required iff `expected_return_method == "composite-zscore-v1"`; repository enforces the invariant), `expected_return_method: Literal["composite-zscore-v1", "none"] = "composite-zscore-v1"`, `render_baselines: bool = True`, `per_instrument_cap: float = 0.10`, `min_cash: float = 0.05`, `turnover_coef: float = 0.0014`, `turnover_reference: Literal["equal_weight", "run_id"] = "equal_weight"`, `w_prev_run_id: str | None = None`. Define `SOLVER_OPTIONS_ALLOWLIST: Final[frozenset[str]] = frozenset({"solver", "solver_path", "eps_abs", "eps_rel", "max_iter", "verbose", "polish"})` — the ONLY keys a caller may pass to `solve()` (V5: no arbitrary solver-option injection; the verbatim options dict is recorded for audit).
  - Verify: `cd backend && .venv/bin/python -c "from app.portfolio.schemas import OptimizationRequest; r = OptimizationRequest(as_of='2026-08-01'); assert r.objective == 'min_volatility'; assert r.render_baselines"`
  - Done: `OptimizationRequest` defaults to min-vol with baselines rendered and validates enums/dates; `SOLVER_OPTIONS_ALLOWLIST` is the only accepted solve() options surface.

- **build: Create `portfolio/optimizer.py` — min-vol QP + PSD gate + run_optimization orchestrator**
  - Files: backend/app/portfolio/optimizer.py
  - Read first: 11-RESEARCH.md `## cvxpy QP Formulation` (exact formulation + audit capture, solver_version mapping) + `## PSD Check/Repair` (fail-closed gate semantics), backend/app/research/catalog.py `get_composite_model` (L451+), backend/app/research/models.py `_write_composite_artifact` (the artifact-consume pattern)
  - Action: Implement `ensure_psd_provenance(cov, provenance, *, epsilon) -> np.ndarray` — if `check_psd(cov)[0] < -epsilon` and `provenance` is missing/empty or lacks `eigenvalues_before`/`eigenvalues_after`, raise `ValueError("PSD repair provenance missing")` (fail-closed, never silent); returns the repaired covariance. Implement `solve_min_vol(cov: np.ndarray, symbols: list[str], *, per_instrument_cap: float, min_cash: float, turnover_coef: float, w_prev: np.ndarray, solver_options: dict | None = None) -> dict` per RESEARCH.md: `w = cp.Variable(n, nonneg=True)`, `constraints = [cp.sum(w) <= 1 - min_cash, w <= per_instrument_cap]`, `objective = cp.Minimize(cp.quad_form(w, cov) + turnover_coef * cp.norm1(w - w_prev))`, `options = {"solver": "CLARABEL", "eps_abs": 1e-8, "eps_rel": 1e-8, "max_iter": 20000}` merged with caller options (only whitelisted keys), `problem.solve(**options)`. Return dict with `status`, `solver_name` (from `problem.solver_stats`), `solve_time`, `num_iters`, `options` (verbatim), `cvxpy_version` (`cp.__version__`), `solver_version` (via `importlib.metadata.version` with the fixed mapping `{"CLARABEL": "clarabel", "OSQP": "osqp", "SCS": "scs", "HIGHS": "highspy"}` and a `"unknown"` fallback wrapped in try/except), and `weights` (`dict(zip(symbols, np.asarray(w.value).round(8)))`). Non-`optimal` status (e.g. `optimal_inaccurate`) is recorded as-is — never promoted (pitfall 4). Implement `run_optimization(request, *, snapshot, returns_panel, repository, artifacts, data_dir) -> str` (returns run_id) wiring the single path: resolve symbols from the panel → `sample_covariance` → `check_psd` → `repair_psd` if needed (provenance mandatory) → `hrp_weights` + `render_baseline` baseline → `solve_min_vol` → `PortfolioArtifactService.write_bundle` → `record_optimization_run` with `risk_model_json` = `{"risk_model": "sample_covariance_v1", "dropna": True, "psd_repair": provenance, "covariance_sha256": sha256(canonical bytes)}` and `input_snapshot_sha256` from the snapshot. `import cvxpy as cp` is at module top; importing this module MUST NOT pull pandas (numpy-only math path; pandas only at the optimization boundary per ADR-19) — assert `"pandas" not in sys.modules` after import in the Wave 1 gate.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_optimizer.py -q --tb=short`
  - Done: Min-vol on a 2-asset fixture matches the analytical solution; cap and min-cash are active constraints (weights respect both); the turnover penalty shifts weights toward `w_prev`; a non-PSD covariance without provenance fails the run closed; two identical runs → identical weights + identical solver options.

- **test: Turn `tests/portfolio/test_risk.py` green — covariance, PSD gate, never-silent**
  - Files: backend/tests/portfolio/test_risk.py
  - Read first: backend/tests/portfolio/test_risk.py (the 11-02 RED scaffold), backend/app/portfolio/risk.py (module under test)
  - Action: Make the scaffolded cases pass: (1) sample covariance matches `np.cov(returns, rowvar=False)` on the fixture returns matrix; (2) `check_psd` returns the true minimum eigenvalue for a PSD and a deliberately indefinite matrix; (3) `repair_psd` returns a PSD matrix (`np.linalg.eigvalsh(repaired).min() >= -1e-9`) and the provenance dict carries all four mandatory keys with eigenvalues before/after; (4) `method="none"` provenance records `eigenvalues_after=None`; (5) never-silent — a covariance that needed repair but whose provenance block is missing/empty is rejected by `ensure_psd_provenance` (test via `optimizer.ensure_psd_provenance` raising `ValueError`).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_risk.py -q --tb=short`
  - Done: The risk module's contracts — reference-matching covariance, true min-eigenvalue reporting, auditable eigen_clip repair, and the fail-closed provenance gate — are locked by green tests.

- **test: Turn `tests/portfolio/test_optimizer.py` green — min-vol analytical, constraints, determinism**
  - Files: backend/tests/portfolio/test_optimizer.py
  - Read first: backend/tests/portfolio/test_optimizer.py (the 11-02 RED scaffold), backend/app/portfolio/optimizer.py (module under test)
  - Action: Make the scaffolded cases pass: (1) min-vol on a 2-asset fixture with a known covariance matches the analytical solution (`w_i ∝ 1/σ_i²` when uncorrelated); (2) cap is active — with `per_instrument_cap=0.60` and 2 assets, no weight exceeds the cap; (3) min cash is a floor — assert `1 - sum(w) >= min_cash - 1e-8` and `sum(w) <= 1 + 1e-8` (pitfall 7); (4) turnover penalty — with a nonzero `turnover_coef` and `w_prev != 1/n`, weights shift toward `w_prev` vs the zero-coefficient solve; (5) determinism — two identical solves return identical weights and identical `options`; (6) `optimal_inaccurate` is recorded as-is, never promoted (build a fixture solve whose status is not `optimal` and assert the dict carries the real status).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_optimizer.py -q --tb=short`
  - Done: The min-vol QP contracts — analytical match, active cap/min-cash, turnover anchoring, determinism, honest status — are locked by green tests.

- **test: Turn `tests/portfolio/test_hrp.py` green — cluster ordering, scaling, determinism**
  - Files: backend/tests/portfolio/test_hrp.py
  - Read first: backend/tests/portfolio/test_hrp.py (the 11-02 RED scaffold), backend/app/portfolio/hrp.py (module under test)
  - Action: Make the scaffolded cases pass: (1) on a 3-asset correlated fixture (two highly correlated assets + one orthogonal), the quasi-diagonal leaf ordering clusters the correlated pair adjacently; (2) `hrp_weights` sums to 1 within 1e-8; (3) `render_baseline(hrp_weights(cov), min_cash=0.05)` sums to 0.95 within 1e-8 and is strictly ≤ the unscaled vector; (4) two calls return identical weights (determinism); (5) all weights in [0, 1] (pitfall 9 — positive diagonal enforced by the PSD gate).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_hrp.py -q --tb=short`
  - Done: The HRP baseline contract — cluster ordering, unit sum, min-cash scaling, determinism, [0,1] bounds — is locked by green tests.

- **test: Turn `tests/portfolio/test_repository.py` green — append-only runs, JSON round-trip, failure-reason invariant**
  - Files: backend/tests/portfolio/test_repository.py
  - Read first: backend/tests/portfolio/test_repository.py (the 11-02 RED scaffold), backend/app/portfolio/repository.py (module under test)
  - Action: Make the scaffolded cases pass: (1) a run row inserted via `record_optimization_run` round-trips through `get_optimization_run` with JSON columns unwrapped; (2) UPDATE and DELETE on `portfolio_optimization_runs` raise (immutability triggers); (3) `problem_status="failed"` without `failure_reason` raises `ValueError`; (4) a non-hex `input_snapshot_sha256` raises `ValueError`; (5) `list_optimization_runs` filters by objective and as_of and orders by `created_at, id`; (6) `model_id` absent with `expected_return_method="none"` is allowed (min-vol risk-only run).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_repository.py -q --tb=short`
  - Done: The append-only run-record contract — round-trip, immutability, failure-reason invariant, sha256 validation — is locked by green tests.

- **test: End-to-end tracer proof — `tests/portfolio/test_pipeline.py`**
  - Files: backend/tests/portfolio/test_pipeline.py
  - Read first: backend/tests/portfolio/test_pipeline.py, backend/tests/portfolio/conftest.py (StubBacktestEngine + fixture composite artifact fixtures), backend/app/portfolio/optimizer.py (run_optimization)
  - Action: Write one integration test that walks the full spine on a fixture: a fixture composite artifact (research_artifacts/<model_id>/signals.json with a recorded `output_sha256` in `factor_model_composites`) → `run_optimization` with `objective="min_volatility"` → assert the run row exists with `problem_status="optimal"`, `solver_name` in ("CLARABEL", "OSQP"), `solver_version` non-empty, `input_snapshot_sha256 == composite.input_snapshot_sha256`, `risk_model_json["psd_repair"]["method"]` in ("none", "eigen_clip"), `output_weights_json` sums ≤ `1 - min_cash`, `baseline_weights_json` present with HRP weights scaled by `(1 - min_cash)`; then `get_optimization_run(run_id)` returns the same row and the weights artifact loads checksum-verified. Use a `StubBacktestEngine` + fixture panel + tmp_path SQLite repository + tmp_path artifact root from `conftest.py`. The fixture composite is written through `EvaluationArtifactService` (research/artifacts.py) so the O_EXCL + sha256 contract is exercised for real.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py -q --tb=short`
  - Done: The full snapshot → covariance+PSD → min-vol QP → immutable run path works on a fixture with an immutable run row and checksum-verified artifacts — the spine is proven before any breadth plan starts.

## Verification

```bash
cd backend && .venv/bin/python -m pytest \
  tests/portfolio/test_pipeline.py \
  tests/portfolio/test_risk.py \
  tests/portfolio/test_optimizer.py \
  tests/portfolio/test_hrp.py \
  tests/portfolio/test_repository.py \
  -q --tb=short
```

All green. No `cp.quad_form` call exists anywhere that is not preceded by the PSD gate (grep: `quad_form` appears only in `portfolio/optimizer.py` and tests). `import app.portfolio.optimizer` pulls no pandas at module top (subprocess asserts `"pandas" not in sys.modules`).

## Success Criteria

- The composite snapshot feeds expected-return identity (`input_snapshot_sha256`) while covariance comes from the governed panel — distinct inputs with distinct provenance.
- Min-vol QP solves under the full constraint stack with Clarabel default and honest status capture; PSD repair is never silent.
- Every run lands as an append-only row with weights + HRP baseline weights + PSD provenance; artifacts are checksum-verified.
- The tracer test proves the full path on a fixture.

---

# Plan 11-02 — Wave 0: cvxpy Dependency, Runs Migration, Test Scaffolding

**wave:** 0 · **depends_on:** [] · **autonomous:** false (two one-way-door checkpoint:decision gates)
**requirements:** [PFOL-04]
**files_modified:**
- backend/pyproject.toml
- backend/uv.lock
- backend/app/operational/migrations.py
- backend/app/portfolio/repository.py (new — migrate() stub called by 11-01; the append-only methods land in 11-01)
- backend/tests/test_operational_migrations.py (extend)
- backend/tests/portfolio/conftest.py (new)
- backend/tests/portfolio/test_risk.py (new — RED scaffold)
- backend/tests/portfolio/test_optimizer.py (new — RED scaffold)
- backend/tests/portfolio/test_hrp.py (new — RED scaffold)
- backend/tests/portfolio/test_repository.py (new — RED scaffold)

## Objective

Land the irreversible foundations every other plan builds on: the cvxpy 1.9.2 base dependency with the empty-`.venv` Wave 0 gate, the `portfolio_optimization_runs` append-only table in the existing operational.db migration sequence, and the base test scaffolding (new test files + `tests/portfolio/conftest.py` fixtures) that 11-01 turns green. The two one-way-door decisions (new append-only table; cvxpy addition to base deps) are gated behind explicit `checkpoint:decision` tasks BEFORE any implementation — per the reversibility contract they are `one-way` (undoing requires a schema migration or a dependency revert that breaks the Phase 11 contract).

Purpose: Every later plan assumes this table, this dependency floor, and these test files exist. Wave 0 is the only place the migration sequence advances and the only place the fresh-environment dependency truth is verified (RESEARCH.md Wave 0 gate — not an assumption).
Output: cvxpy pinned + locked + verified in an empty `.venv`; the runs table migrated with CHECKs and triggers; 5 new test files + conftest fixtures; a `PortfolioRepository.migrate()` seam 11-01 fills with the append-only methods.

## Context

- @.planning/phases/11-portfolio-construction-optimization/11-RESEARCH.md — `## Dependency Changes (cvxpy)`, `## Schema/Migration Sketch`, `## Verification Plan` (Wave 0 gaps), `## Package Legitimacy Audit`, `## Common Pitfalls` (pitfall 6 — cvxpy version drift)
- @.planning/phases/11-portfolio-construction-optimization/11-CONTEXT.md — locked decisions (cvxpy 1.9.2 primary QP; immutable run records)
- backend/pyproject.toml — `[project] dependencies` (base) with the scipy comment at the `scipy>=1.17.1,<1.18` line; `requires-python = ">=3.11"`
- backend/app/operational/migrations.py — `MIGRATIONS` tuple (last entry L1510-1577 — the Phase 10 factor tables + triggers; the tuple closes at L1577), `migrate_operational_db` (L1607-1635) applies atomically with `PRAGMA user_version`
- backend/tests/test_operational_migrations.py — atomicity + Phase 10 append-only-table test conventions (L349+ pattern for the new table)
- backend/tests/research/conftest.py — `StubBacktestEngine` + `fixture_panel` + `research_repository` fixture pattern to mirror in `tests/portfolio/conftest.py`
- backend/app/research/repository.py — `ResearchRepository.__init__` + `migrate()` convention (calls `migrate_operational_db`)

## Tasks

- **checkpoint:decision — Approve the cvxpy 1.9.2 base dependency (one-way door)**
  - Decision: Add `"cvxpy==1.9.2"` (exact pin) to `[project] dependencies` in `backend/pyproject.toml` and lock it into `uv.lock`.
  - Context: CONTEXT resolves the engine decision — cvxpy is the primary QP solver (constraint stack is convex-QP territory where scipy SLSQP degrades). The exact pin is REQUIRED: solver results are version-sensitive and the audit record cites `cp.__version__` (pitfall 6). Package legitimacy is pre-verified (RESEARCH.md `## Package Legitimacy Audit`: PyPI-verified 1.9.2, cp311 wheels, bundled OSQP/Clarabel/SCS/HiGHS; the npm `SUS` results are documented cross-ecosystem false positives). This is a one-way door: it changes the published base-dependency contract and install surface.
  - Options:
    - option-a: Add `"cvxpy==1.9.2"` to base `[project] dependencies`; `uv lock` regenerates; the empty-`.venv` gate verifies. Pros: matches CONTEXT exactly, satisfies requires-python `>=3.11` with cp311 wheels; bundled solvers resolve transitively. Cons: grows the base install surface.
    - option-b: Add cvxpy as a `backtest`-style extra instead of base. Pros: smallest base install. Cons: violates the locked decision (base dependency); Phase 11 base installs would miss the optimizer.
  - Resume signal: Select: option-a or option-b

- **build: Add cvxpy 1.9.2 to base deps + run the empty-.venv Wave 0 gate**
  - Files: backend/pyproject.toml, backend/uv.lock
  - Read first: backend/pyproject.toml (`[project] dependencies` — insert `"cvxpy==1.9.2"` beside the scipy line with a short comment "Phase 11 QP solver"), 11-RESEARCH.md `## Dependency Changes (cvxpy)` + `## Verification Plan` (Wave 0 gate steps 1-7)
  - Action: Add `"cvxpy==1.9.2"` to `[project] dependencies` per the approved option (option-a). Run `cd backend && uv lock` to regenerate `uv.lock`. Then execute the RESEARCH.md Wave 0 gate in order: (1) `cd backend && uv venv --clear` — fresh empty environment; (2) `uv sync` — must resolve cvxpy 1.9.2 with its solver stack (numpy 2.4.6 / scipy 1.17.1 satisfy the `numpy>=2.0.0` / `scipy>=1.13.0` floors); (3) `uv pip check` — no conflicts; (4) `.venv/bin/python -c "import cvxpy as cp; print(cp.__version__, sorted(cp.installed_solvers()))"` → `1.9.2` and a list containing `CLARABEL`, `OSQP`, `SCS`, `HIGHS`; (5) `.venv/bin/python -c "import importlib.metadata as m; print(m.version('clarabel'), m.version('osqp'), m.version('scs'), m.version('highspy'))"` — record solver versions for `solver_version` in run records; (6) module-top import audit — a subprocess imports `app.portfolio.optimizer` (created by 11-01; until then audit `app.portfolio` import surface) and asserts `"pandas" not in sys.modules` (ADR-19 boundary — numpy-only math path); (7) smoke — a 5-symbol fixture QP solves to `status == "optimal"` with `sum(w) <= 1 - min_cash` and weights within caps.
  - Verify: `cd backend && uv sync && uv pip check && .venv/bin/python -c "import cvxpy as cp, sys; solvers = sorted(cp.installed_solvers()); sys.exit(0 if cp.__version__ == '1.9.2' and 'CLARABEL' in solvers and 'OSQP' in solvers else 1)"`
  - Done: `cvxpy==1.9.2` is in base deps and locked; the empty-`.venv` gate passes (1.9.2, CLARABEL + OSQP installed, solver versions recordable, no pandas on the portfolio module-top import path, 5-symbol smoke QP `optimal`).

- **checkpoint:decision — Approve the `portfolio_optimization_runs` append-only table (one-way door)**
  - Decision: Land the `portfolio_optimization_runs` append-only table in `operational/migrations.py` as a single new migration script appended to the `MIGRATIONS` tuple (PFOL-04).
  - Context: This is a one-way door: the migration advances `PRAGMA user_version` for every operational.db (research + forecast + jobs share the same database). Undoing requires a follow-up migration, and Phases 12-14 (risk suite, walk-forward, RebalancePlan) are built on this audit contract. The schema is specified in RESEARCH.md `## Schema/Migration Sketch`; the exact constraint/index names follow the Phase 10 trigger conventions (L1573-1576).
  - Options:
    - option-a: Ship the RESEARCH.md schema exactly — `portfolio_optimization_runs` (id TEXT PK, objective CHECK min_volatility|hrp|max_sharpe, as_of TEXT, universe TEXT, model_id TEXT REFERENCES factor_model_models(model_id) ON DELETE RESTRICT, composite_snapshot_id TEXT, input_snapshot_sha256 TEXT CHECK length=64, expected_return_method CHECK composite-zscore-v1|none, risk_model CHECK sample_covariance_v1, risk_model_json TEXT, constraint_stack_json TEXT, solver_name TEXT, solver_version TEXT, solver_options_json TEXT, problem_status CHECK optimal|optimal_inaccurate|infeasible|unbounded|solver_error|failed, failure_reason TEXT, output_weights_json TEXT, output_sha256 TEXT CHECK length=64 NULL, weights_artifact_relative_path TEXT, baseline_weights_json TEXT, created_at TEXT, CHECK (problem_status IN ('failed','solver_error')) = (failure_reason IS NOT NULL)) + idx on (as_of, objective) + no_update/no_delete triggers. Pros: matches the researched audit contract verbatim; the CHECK guarantees the failed⇔failure_reason invariant at the DB layer. Cons: none measured.
    - option-b: Adjust column names/types now (e.g., store risk_model_json flattened). Pros: could reduce JSON columns. Cons: diverges from the researched contract; more review; no measured benefit.
  - Resume signal: Select: option-a or option-b

- **build: Append the `portfolio_optimization_runs` migration + extend migration tests**
  - Files: backend/app/operational/migrations.py, backend/tests/test_operational_migrations.py
  - Read first: backend/app/operational/migrations.py (the last MIGRATIONS entry L1510-1577 — factor tables + triggers style; the tuple closes at L1577), backend/tests/test_operational_migrations.py (Phase 10 append-only-table test conventions, L349+)
  - Action: Append ONE new SQL script to the `MIGRATIONS` tuple creating `portfolio_optimization_runs` per the approved schema (option-a): the exact table DDL from RESEARCH.md `## Schema/Migration Sketch` — objective CHECK `IN ('min_volatility','hrp','max_sharpe')`, expected_return_method CHECK `IN ('composite-zscore-v1','none')`, risk_model CHECK `IN ('sample_covariance_v1')`, problem_status CHECK `IN ('optimal','optimal_inaccurate','infeasible','unbounded','solver_error','failed')`, `input_snapshot_sha256 TEXT NOT NULL CHECK (length(input_snapshot_sha256) = 64)`, `output_sha256 TEXT CHECK (output_sha256 IS NULL OR length(output_sha256) = 64)`, the table-level CHECK `(problem_status IN ('failed','solver_error')) = (failure_reason IS NOT NULL)` (failed ⇔ failure_reason present — PFOL-04), `model_id TEXT REFERENCES factor_model_models(model_id) ON DELETE RESTRICT` (NULL only when expected_return_method='none'; the model_id-present-iff-method-present invariant is enforced at the repository layer), `CREATE INDEX idx_portfolio_optimization_runs_as_of ON portfolio_optimization_runs(as_of, objective)`, and the two immutability triggers `portfolio_optimization_runs_no_update` / `portfolio_optimization_runs_no_delete` with `RAISE(ABORT, 'portfolio optimization runs are append-only')` (exact Phase 10 trigger style L1573-1576). Extend `tests/test_operational_migrations.py`: after applying the full MIGRATIONS to a fresh in-memory connection, assert the table exists, the CHECK constraints reject a bad objective enum and a bad sha256 length, the failed-without-reason invariant rejects, and UPDATE/DELETE raise.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short`
  - Done: `portfolio_optimization_runs` exists after migration with the enum/sha256/failed⇔reason CHECKs and immutability triggers; the migration test proves constraints and forward-only idempotence.

- **test: Scaffold the 5 new test files + shared fixtures (Wave 0 gaps)**
  - Files: backend/tests/portfolio/conftest.py, backend/tests/portfolio/test_risk.py, backend/tests/portfolio/test_optimizer.py, backend/tests/portfolio/test_hrp.py, backend/tests/portfolio/test_repository.py
  - Read first: backend/tests/research/conftest.py (StubBacktestEngine + fixture_panel + research_repository patterns), 11-RESEARCH.md `## Verification Plan` (Wave 0 gaps)
  - Action: Create `tests/portfolio/` with a `conftest.py` mirroring the research test fixtures: a `StubBacktestEngine` (governed-panel boundary substitute with a `load_panel(symbols, start, end, columns, asset_type)` returning a deterministic fixture panel of `[symbol, date, close, returns]` rows for FIXTURE_SYMBOLS over a short window), `fixture_panel` / `fixture_returns` (deterministic `np.ndarray` returns matrix with a known covariance), `portfolio_repository(tmp_path)` (a `PortfolioRepository` on a tmp_path operational.db — the 11-02 repository seam fills `migrate()`), `artifact_root(tmp_path)` (tmp_path app-data for `PortfolioArtifactService`), and `fixture_composite` (a recorded composite row + artifact bytes written through `EvaluationArtifactService` for the 11-01 tracer test). Create the 4 new test files as RED scaffolds per the RESEARCH.md Wave 0 gaps — `test_risk.py` (cases: covariance vs NumPy reference, check_psd true min-eigenvalue, repair_psd PSD + full provenance, method="none" provenance, never-silent rejection), `test_optimizer.py` (cases: 2-asset min-vol analytical match, cap active, min-cash floor, turnover anchoring, determinism, honest status), `test_hrp.py` (cases: cluster ordering, unit sum, render_baseline scaling, determinism, [0,1] bounds), `test_repository.py` (cases: run-row round-trip, UPDATE/DELETE blocked, failed-without-reason ValueError, sha256 validation, list filters, model_id-null-for-none) — each importing the target module lazily so the scaffold is provably RED (failing on the missing module) until 11-01.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short` — expected failures (RED) until 11-01 lands
  - Done: `tests/portfolio/` exists with the 5 test files carrying the RESEARCH.md cases and shared fixtures in conftest.py; the scaffolds are provably RED (failing on the missing modules) — the exact tests 11-01 turns green.

- **build: Add the `PortfolioRepository` seam with `migrate()`**
  - Files: backend/app/portfolio/repository.py
  - Read first: backend/app/research/repository.py (module docstring + `__init__` + `migrate()` convention), backend/app/operational/migrations.py (`migrate_operational_db`)
  - Action: Create `backend/app/portfolio/repository.py` with the module docstring stating know/don't-know per CONVENTIONS.md, the private helpers `_json(value, field)` (canonical `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`) and `_record(row)` (un-wrap the JSON columns), and the `PortfolioRepository` class: `__init__(self, db_path: Path)` opens the operational DB and calls `migrate_operational_db(connection)` (the runs table from the 11-02 migration lands before any insert), plus `migrate()` as the alias 11-01's tests call. Do NOT add the append-only insert/query methods here — 11-01 adds them (this plan only establishes the shared DB seam and migration wiring).
  - Verify: `cd backend && .venv/bin/python -c "from app.portfolio.repository import PortfolioRepository; r = PortfolioRepository('/tmp/pfol-w0.db'); r.migrate(); import sqlite3; c = sqlite3.connect('/tmp/pfol-w0.db'); assert c.execute(\"SELECT name FROM sqlite_master WHERE name='portfolio_optimization_runs'\").fetchone()"`
  - Done: `PortfolioRepository` opens the operational DB, applies the full migration sequence (runs table present), and exposes `migrate()`; no insert/query methods yet (11-01).

## Verification

```bash
cd backend && uv sync && uv pip check && .venv/bin/python -c "import cvxpy as cp, sys; sys.exit(0 if cp.__version__ == '1.9.2' and 'CLARABEL' in cp.installed_solvers() else 1)"   # wave 0 — 1.9.2 + CLARABEL (exit 1 on mismatch)
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short
cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short   # expected RED (scaffolds) until 11-01
```

The 5 new test files exist and are RED; the dependency and migration gates pass.

## Success Criteria

- `cvxpy==1.9.2` is in base deps, locked, and verified in an empty `.venv` with CLARABEL + OSQP installed; module-top import pulls no pandas.
- `portfolio_optimization_runs` migrates atomically with enum/sha256/failed⇔reason CHECKs and immutability triggers.
- The 5 new test files are scaffolded RED with shared fixtures in conftest.py.
- `PortfolioRepository` applies the migration sequence via `migrate()`.

---

# Plan 11-03 — HRP Baseline Breadth (PFOL-02)

**wave:** 2 · **depends_on:** [11-01] · **autonomous:** true
**requirements:** [PFOL-02]
**files_modified:**
- backend/app/portfolio/hrp.py (extend)
- backend/tests/portfolio/test_hrp.py (extend)
- backend/app/portfolio/optimizer.py (extend — hrp objective path)

## Objective

Harden the HRP baseline from the tracer's single-path proof to the full baseline contract: `hrp_portfolio(cov, *, min_cash)` as a first-class objective (`objective="hrp"` produces a run record with HRP weights and no solver), the baseline rendered alongside min-vol/max-Sharpe runs scaled by `(1 - min_cash)`, and the determinism / [0,1]-bounds / cluster-ordering guarantees locked by green tests. Runs with `objective="hrp"` are still immutable records (`problem_status="optimal"` with `solver_name="n/a"` — no solver involved) so the audit contract holds for every objective.

Purpose: PFOL-02 requires the HRP baseline to ship alongside min-vol, not as an afterthought; the tracer proved the min-vol path with a fixture HRP render, this plan makes HRP production-grade and auditable as its own objective.
Output: `hrp_portfolio`, the `objective="hrp"` run path, and green `test_hrp.py` breadth.

## Context

- @.planning/phases/11-portfolio-construction-optimization/11-RESEARCH.md — `## HRP Baseline` (the reference implementation + rendering contract), `## Common Pitfalls` (pitfall 9 — HRP on indefinite covariance)
- @.planning/phases/11-portfolio-construction-optimization/11-CONTEXT.md — locked decision: HRP baseline ships in Phase 11 (scipy linkage available)
- backend/app/portfolio/hrp.py (from 11-01) — `hrp_weights` / `render_baseline`
- backend/app/portfolio/optimizer.py (from 11-01) — `run_optimization` orchestrator (add the hrp branch)
- backend/tests/portfolio/test_hrp.py (from 11-02 RED scaffold, partially green from 11-01) — extend with the objective-path cases

## Tasks

- **build: Add `hrp_portfolio` + the `objective="hrp"` run path**
  - Files: backend/app/portfolio/hrp.py, backend/app/portfolio/optimizer.py
  - Read first: backend/app/portfolio/hrp.py (from 11-01), 11-RESEARCH.md `## HRP Baseline` (rendering contract), backend/app/portfolio/optimizer.py (the `run_optimization` signature from 11-01)
  - Action: In `hrp.py`, add `hrp_portfolio(cov: np.ndarray, *, min_cash: float, symbols: list[str]) -> dict` returning `{"weights": dict(zip(symbols, (render_baseline(hrp_weights(cov), min_cash=min_cash)).round(8))), "status": "optimal", "solver_name": "n/a"}` — the same PSD gate runs first (a negative diagonal breaks `_cluster_weights`; pitfall 9). In `optimizer.py`, extend `run_optimization` with an `objective="hrp"` branch that runs the PSD gate, computes `hrp_portfolio`, persists weights through `PortfolioArtifactService.write_bundle`, and records a run row with `objective="hrp"`, `problem_status="optimal"`, `solver_name="n/a"`, `solver_version="n/a"`, `solver_options_json={}` — the record is still append-only and auditable even though no solver ran. The min-vol path's `baseline_weights_json` must equal the HRP weights for the same covariance (rendered, scaled by `(1 - min_cash)`).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_hrp.py -q --tb=short`
  - Done: `objective="hrp"` produces an immutable run record with HRP weights, `solver_name="n/a"`, and no solver call; min-vol runs carry the HRP baseline in `baseline_weights_json`.

- **test: Extend `test_hrp.py` — objective path, baseline scaling, determinism**
  - Files: backend/tests/portfolio/test_hrp.py
  - Read first: backend/tests/portfolio/test_hrp.py (existing 11-01 green cases), backend/app/portfolio/hrp.py (module under test)
  - Action: Add tests: (1) `hrp_portfolio(cov, min_cash=0.05, symbols)` returns weights that sum to 0.95 within 1e-8 and lie in [0, 1]; (2) the min-vol run's `baseline_weights_json` equals `hrp_portfolio(...)["weights"]` for the same covariance (rendered baseline); (3) two `hrp_portfolio` calls return identical weights; (4) on a 3-asset correlated fixture the quasi-diagonal leaf ordering clusters the correlated pair (already green from 11-01 — keep); (5) an `objective="hrp"` run row records `solver_name="n/a"` and `problem_status="optimal"` with no solver version.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_hrp.py -q --tb=short`
  - Done: The HRP objective path, baseline scaling, determinism, and audit-record shape are locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_hrp.py tests/portfolio/test_pipeline.py -q --tb=short
```

All green. No `linkage` call exists outside `portfolio/hrp.py` (grep: `scipy.cluster.hierarchy` imports appear only there).

## Success Criteria

- `hrp_portfolio` is a first-class objective producing an auditable run record; min-vol/max-Sharpe runs render the HRP baseline alongside.
- HRP determinism, [0,1] bounds, unit-sum-then-scaled rendering, and cluster ordering are locked by tests.

---

# Plan 11-04 — Min-Vol Breadth + Max-Sharpe Non-Default (PFOL-02/03)

**wave:** 2 · **depends_on:** [11-01] · **autonomous:** true
**requirements:** [PFOL-02, PFOL-03]
**files_modified:**
- backend/app/portfolio/optimizer.py (extend)
- backend/app/portfolio/constraints.py (extend — w_prev reference provenance)
- backend/app/portfolio/schemas.py (extend — w_prev_run_id resolution)
- backend/tests/portfolio/test_optimizer.py (extend)

## Objective

Harden the min-vol QP from the tracer's single-path proof to the full PFOL-02/03 surface: the `solver_path=["CLARABEL", "OSQP"]` fallback with per-solver version capture, the `w_prev` equal-weight anchor for the first run and prior-run weights for subsequent runs (`turnover_reference` recorded in `constraint_stack_json`), and max-Sharpe as an explicit non-default objective that is rejected without `render_baselines=True` and always records min-vol + HRP baselines alongside (PyPortfolioOpt variable-substitution warning honored).

Purpose: The constraint stack and objective contract are PFOL-02/03's core; the tracer proved one path, this plan closes the non-default option surface and the turnover anchor semantics so Phase 14 rebalances inherit correct turnover reference semantics.
Output: solver_path fallback, `w_prev` resolution, the max-Sharpe opt-in contract, green `test_optimizer.py` breadth.

## Context

- @.planning/phases/11-portfolio-construction-optimization/11-RESEARCH.md — `## cvxpy QP Formulation` (solver_path, max-Sharpe contract, w_prev first-run equal-weight), `## Constraint Stack` (turnover_reference provenance), `## Common Pitfalls` (pitfall 2 — max-Sharpe default, pitfall 4 — optimal_inaccurate)
- @.planning/phases/11-portfolio-construction-optimization/11-CONTEXT.md — locked decisions: max-Sharpe explicit non-default with baselines rendered
- backend/app/portfolio/optimizer.py (from 11-01) — `solve_min_vol` + `run_optimization`
- backend/app/portfolio/schemas.py (from 11-01) — `OptimizationRequest` (turnover_reference / w_prev_run_id fields already declared)
- backend/tests/portfolio/test_optimizer.py (from 11-02 RED scaffold, partially green from 11-01) — extend

## Tasks

- **build: `solver_path` fallback + per-solver version capture**
  - Files: backend/app/portfolio/optimizer.py
  - Read first: 11-RESEARCH.md `## cvxpy QP Formulation` (solver_path + solver_version mapping notes), backend/app/portfolio/optimizer.py (from 11-01)
  - Action: Change `solve_min_vol`'s default options to `{"solver": "CLARABEL", "solver_path": ["CLARABEL", "OSQP"], "eps_abs": 1e-8, "eps_rel": 1e-8, "max_iter": 20000}` — the verbatim options dict is recorded, and `problem.solver_stats.solver_name` records whichever solver actually ran. Extend the `solver_version` capture: the fixed mapping `{"CLARABEL": "clarabel", "OSQP": "osqp", "SCS": "scs", "HIGHS": "highspy"}` via `importlib.metadata.version`, wrapped in try/except returning `"unknown"` (RESEARCH.md Code Example 1 note — `scs`/`highspy` distribution names differ). On `problem_status == "optimal_inaccurate"`, keep the honest status and record the options verbatim (pitfall 4 — never promote); the run row retains it.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_optimizer.py -q --tb=short`
  - Done: `solver_path` fallback is in the recorded options; `solver_name` reflects the solver that actually ran; `solver_version` resolves via the fixed mapping with `"unknown"` fallback; `optimal_inaccurate` is recorded as-is.

- **build: `w_prev` resolution — equal-weight anchor + prior-run reference**
  - Files: backend/app/portfolio/optimizer.py, backend/app/portfolio/constraints.py, backend/app/portfolio/schemas.py
  - Read first: 11-RESEARCH.md `## Constraint Stack` (w_prev reference: equal_weight | run_id, recorded in constraint_stack_json), backend/app/portfolio/optimizer.py (from 11-01)
  - Action: Implement `_resolve_w_prev(request, symbols, repository) -> tuple[np.ndarray, str]` in `optimizer.py`: when `turnover_reference == "equal_weight"` return the uniform vector `np.full(n, 1/n)` and reference `"equal_weight"`; when `"run_id"` with a `w_prev_run_id`, load the prior run via `repository.get_optimization_run`, checksum-verify its weights artifact, align to `symbols` (missing symbols → 0.0; extra → dropped), and reference `"run_id:<w_prev_run_id>"`; a missing prior run raises `ValueError` (fail closed, recorded as a `failed` run by the orchestrator). Add `turnover_reference` + `turnover_reference_detail` to the `constraint_stack_json` payload (alongside cap/min-cash/turnover-coef values and `policy_version: "phase-11-policy-v1"`) so the exact anchor is auditable. Update `OptimizationRequest` validation: `w_prev_run_id` is required iff `turnover_reference == "run_id"`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_optimizer.py -q --tb=short`
  - Done: First-run min-vol uses the equal-weight `1/n` anchor; a `turnover_reference="run_id"` run uses checksum-verified prior weights aligned to the current symbols; the anchor is recorded in `constraint_stack_json`.

- **build: Max-Sharpe — explicit non-default with baselines rendered**
  - Files: backend/app/portfolio/optimizer.py, backend/app/portfolio/constraints.py
  - Read first: 11-RESEARCH.md `## cvxpy QP Formulation` (max-Sharpe formulation + baselines contract, PyPortfolioOpt warning), backend/app/portfolio/optimizer.py (from 11-01)
  - Action: Implement `solve_max_sharpe(mu: np.ndarray, cov: np.ndarray, symbols: list[str], *, per_instrument_cap: float, min_cash: float, turnover_coef: float, w_prev: np.ndarray, risk_aversion: float, solver_options: dict | None = None) -> dict` — `objective = cp.Maximize(mu @ w - (risk_aversion / 2) * cp.quad_form(w, cov))` under the SAME constraint stack, with `risk_aversion = MAX_SHARPE_RISK_AVERSION (1.0)`. In `run_optimization`, gate it: `objective == "max_sharpe"` requires `render_baselines=True` (the `OptimizationRequest` Pydantic default is `True`; a caller passing `False` with max-sharpe gets a `ValueError` — never a silent skip, pitfall 2). The max-sharpe run record stores `objective="max_sharpe"` AND `baseline_weights_json` = `{"min_volatility": <min-vol weights>, "hrp": <hrp weights>}` (both baselines rendered alongside). `mu` comes from the composite cross-section (the snapshot binding lands in 11-05; until then `run_optimization` takes `mu` as a parameter the tracer/snapshot tests supply).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_optimizer.py -q --tb=short`
  - Done: `max_sharpe` is reachable only with `render_baselines=True`; the run records both min-vol and HRP baselines; the objective uses `risk_aversion=1.0` over the composite cross-section; min-vol remains the default objective.

- **test: Extend `test_optimizer.py` — solver_path, w_prev anchor, max-Sharpe gate**
  - Files: backend/tests/portfolio/test_optimizer.py
  - Read first: backend/tests/portfolio/test_optimizer.py (existing 11-01 green cases), backend/app/portfolio/optimizer.py (module under test)
  - Action: Add tests: (1) the recorded `options` dict contains `solver_path` and `solver` keys; (2) `solver_name` is in ("CLARABEL", "OSQP") and `solver_version` is a non-empty string; (3) equal-weight anchor — a first run with `turnover_reference="equal_weight"` records `constraint_stack_json["turnover_reference"] == "equal_weight"`; (4) prior-run reference — a `turnover_reference="run_id"` run loads the prior weights, aligns to the current symbols, and records `turnover_reference_detail`; a missing prior run raises `ValueError`; (5) max-Sharpe gate — `objective="max_sharpe"` with `render_baselines=False` raises `ValueError`; with `render_baselines=True` the run records `objective="max_sharpe"` and `baseline_weights_json` contains BOTH `min_volatility` and `hrp` keys; (6) min-vol default — `OptimizationRequest(as_of=...).objective == "min_volatility"` (already green from 11-01 — keep).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_optimizer.py -q --tb=short`
  - Done: The solver_path fallback, w_prev anchor semantics, and the max-Sharpe opt-in + baselines contract are locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_optimizer.py tests/portfolio/test_pipeline.py -q --tb=short
```

All green. Grep gate: `objective="max_sharpe"` appears only in `optimizer.py` (the gate) and tests; `render_baselines=False` with max-sharpe is always rejected.

## Success Criteria

- `solver_path=["CLARABEL", "OSQP"]` with per-solver version capture; `optimal_inaccurate` never promoted.
- First-run turnover anchor is equal-weight; prior-run references are checksum-verified and recorded.
- Max-Sharpe is explicit non-default; every max-Sharpe run carries min-vol + HRP baselines.

---

# Plan 11-05 — Snapshot Binding + Run-Record Breadth (PFOL-04)

**wave:** 3 · **depends_on:** [11-03, 11-04] · **autonomous:** true
**requirements:** [PFOL-04]
**files_modified:**
- backend/app/portfolio/snapshot.py (new)
- backend/app/portfolio/optimizer.py (extend — snapshot wiring into run_optimization)
- backend/app/portfolio/repository.py (extend — list_optimization_runs breadth)
- backend/tests/portfolio/test_snapshot_binding.py (new — RED scaffold turned green)
- backend/tests/research/test_models.py (extend — cross-module composite-snapshot consumption)

## Objective

Make the composite expected-return input a production, fail-closed snapshot binding and broaden the run-record surface: `load_composite_snapshot(model_id, as_of)` via `catalog.get_composite_model` → checksum-verified artifact load → as-of cross-section (never a live module hand-off); every fail-closed path (model missing, no snapshot, artifact absent/tampered, lookahead as_of) recorded as a `failed` run with reason; `run_optimization` wired end-to-end with the snapshot; and `list_optimization_runs` breadth for the Phase 15 API.

Purpose: PFOL-04's audit root — the run row's `input_snapshot_sha256` must equal the composite's `input_snapshot_sha256` (cross-module integrity), and every failure must be an auditable `failed` run, never a silent abort. The tracer used a fixture snapshot; this plan makes the real catalog seam production.
Output: `snapshot.py`, the wired `run_optimization`, `list_optimization_runs` breadth, green `test_snapshot_binding.py` + cross-module `test_models.py` extension.

## Context

- @.planning/phases/11-portfolio-construction-optimization/11-RESEARCH.md — `## Input Snapshot Binding` (the 5-step contract + fail-closed paths), `## Immutable Run Records` (list_optimization_runs), `## Common Pitfalls` (pitfall 5 — composite consumed live)
- @.planning/phases/11-portfolio-construction-optimization/11-CONTEXT.md — locked decisions: composite consumed BY SNAPSHOT, never a live module hand-off
- backend/app/research/catalog.py — `get_composite_model` (L451+), `CompositeModelRecord` (L172-205: model_id / input_snapshot_sha256 / latest_composite = {id, output_sha256, artifact_relative_path, input_snapshot_sha256, created_at})
- backend/app/backtest/frozen_panel.py — `load` checksum-verified read pattern (L75-137) for the artifact read
- backend/app/portfolio/optimizer.py (from 11-01/11-04) — `run_optimization` orchestrator
- backend/tests/research/conftest.py — `research_repository` fixture (tmp_path operational.db) for the cross-module test
- backend/tests/research/test_models.py — the existing composite snapshot tests (extend with the cross-module consumption assertion)

## Tasks

- **build: Create `portfolio/snapshot.py` — checksum-verified composite snapshot binding**
  - Files: backend/app/portfolio/snapshot.py
  - Read first: 11-RESEARCH.md `## Input Snapshot Binding` (the 5 steps), backend/app/research/catalog.py `get_composite_model` (L451+), backend/app/backtest/frozen_panel.py `load` (L75-137)
  - Action: Implement `load_composite_snapshot(catalog, *, model_id: str, as_of: date, data_dir: Path) -> dict` per RESEARCH.md: (1) `record = catalog.get_composite_model(model_id)` — a missing record raises `SnapshotBindingError("model not found")`; (2) `latest = record.latest_composite` — `None` raises `SnapshotBindingError("no composite snapshot recorded")`; (3) read `data_dir / latest["artifact_relative_path"]` (the Phase 10 `research_artifacts/<model_id>/signals.json` bytes) and verify `sha256(bytes).hexdigest() == latest["output_sha256"]` — absent/tampered/mismatch raises `SnapshotBindingError("composite artifact checksum mismatch")` (frozen_panel fail-closed pattern); (4) parse the `[symbol, date, composite]` rows, PIT-filter with `UniverseResolver.resolve_universe_daily` membership (post-seam inner join, Phase 10 `signal_chain._resolve_membership` pattern), and take the `as_of` date's cross-sectional composite z-scores as `mu`; (5) return `{"symbols": [...], "mu": {...}, "composite_snapshot_id": latest["id"], "input_snapshot_sha256": latest["input_snapshot_sha256"]}`. Add the lookahead guard: `as_of` preceding the composite artifact's `created_at` date raises `SnapshotBindingError("as_of precedes composite artifact")`. The module imports `catalog` lazily inside the function (research convention) and NEVER calls `build_composite` (pitfall 5). Define `class SnapshotBindingError(ValueError)`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_snapshot_binding.py -q --tb=short`
  - Done: `load_composite_snapshot` returns the symbol/mu/snapshot block for a checksum-verified artifact; model-missing, no-snapshot, checksum-mismatch, and lookahead all raise `SnapshotBindingError` with specific messages.

- **build: Wire the snapshot into `run_optimization` + record failed runs fail-closed**
  - Files: backend/app/portfolio/optimizer.py
  - Read first: 11-RESEARCH.md `## Input Snapshot Binding` (fail-closed paths all recorded as `failed` runs), backend/app/portfolio/optimizer.py (from 11-01/11-04)
  - Action: Extend `run_optimization` to accept `catalog` + `data_dir` and resolve expected returns via `load_composite_snapshot` when `expected_return_method == "composite-zscore-v1"` (the tracer's fixture-snapshot parameter is replaced by the real seam; the 11-01 fixture tests keep passing by having `run_optimization` accept a pre-resolved `snapshot` dict OR the catalog pair). The orchestrator wraps the ENTIRE run (snapshot load → covariance → solve → persist) in a try/except: any `SnapshotBindingError` / `ValueError` / solver failure is recorded as a `failed` run row with `failure_reason` (PFOL-04 — failed runs retained with reason) and `problem_status="failed"` — never a silent abort. The run row's `input_snapshot_sha256` comes from the snapshot dict (== composite's `input_snapshot_sha256`, the audit root); `composite_snapshot_id` is recorded. A `failed` run still gets `solver_name`/`solver_version` from what was reached (or "n/a").
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_snapshot_binding.py -q --tb=short`
  - Done: `run_optimization` consumes the snapshot through the real catalog seam; every fail-closed path produces a `failed` run row with `failure_reason`; `input_snapshot_sha256` on the row equals the composite's snapshot sha256.

- **build: `list_optimization_runs` breadth**
  - Files: backend/app/portfolio/repository.py
  - Read first: backend/app/portfolio/repository.py (from 11-01), 11-RESEARCH.md `## Immutable Run Records` (list_optimization_runs signature)
  - Action: Extend `PortfolioRepository.list_optimization_runs(*, objective: str | None = None, as_of: str | None = None, limit: int = 200) -> list[dict]` — SELECT ordered by `created_at, id` with optional equality filters on `objective` / `as_of`, and a `limit` cap (default 200) for the Phase 15 API; JSON columns un-wrapped via `_record`. Keep `get_optimization_run(run_id)` as the single-row path.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_repository.py -q --tb=short`
  - Done: `list_optimization_runs` filters by objective/as_of, orders by `created_at, id`, and caps at `limit`.

- **test: Turn `tests/portfolio/test_snapshot_binding.py` green — fail-closed binding**
  - Files: backend/tests/portfolio/test_snapshot_binding.py
  - Read first: backend/tests/portfolio/test_snapshot_binding.py (the Wave 0 RED scaffold), backend/app/portfolio/snapshot.py (module under test)
  - Action: Make the scaffolded cases pass: (1) model present + artifact checksum match → returns symbols/mu with `input_snapshot_sha256 == record.input_snapshot_sha256`; (2) model missing from catalog → `SnapshotBindingError`; (3) `latest_composite is None` → `SnapshotBindingError`; (4) artifact file absent / tampered bytes → `SnapshotBindingError` (checksum mismatch); (5) `as_of` precedes the artifact's `created_at` → `SnapshotBindingError` (lookahead guard); (6) the end-to-end `run_optimization` path records a `failed` run with `failure_reason` when the snapshot binding fails (the run row exists with `problem_status="failed"`).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_snapshot_binding.py -q --tb=short`
  - Done: The fail-closed snapshot-binding contract — checksum-verified artifact, lookahead guard, and every failure recorded as a `failed` run — is locked by green tests.

- **test: Cross-module — composite snapshot consumption in `test_models.py`**
  - Files: backend/tests/research/test_models.py
  - Read first: backend/tests/research/test_models.py (existing composite snapshot tests), backend/app/portfolio/snapshot.py (the consumer)
  - Action: Add one cross-module test: record a composite through `build_composite` (existing fixture path), then call `load_composite_snapshot(catalog, model_id=..., as_of=..., data_dir=...)` and assert the returned `input_snapshot_sha256` equals the `factor_model_composites` row's `input_snapshot_sha256` and the returned mu cross-section equals the artifact bytes' `[symbol, date, composite]` values at `as_of` — proving the optimizer consumes exactly the frozen artifact (RESEARCH.md cross-module integrity check 2).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/research/test_models.py -q --tb=short`
  - Done: The cross-module integrity check — snapshot consumption == artifact bytes identified by `input_snapshot_sha256` — is locked by a green test.

## Verification

```bash
cd backend && .venv/bin/python -m pytest \
  tests/portfolio/test_snapshot_binding.py \
  tests/portfolio/test_repository.py \
  tests/research/test_models.py \
  -q --tb=short
```

All green. Grep gate: `build_composite` appears nowhere in `backend/app/portfolio/` (pitfall 5 — never a live module hand-off).

## Success Criteria

- Expected returns are consumed by snapshot: checksum-verified artifact bytes, as-of cross-section, audit root `input_snapshot_sha256 == composite snapshot sha256`.
- Every fail-closed path (model missing, no snapshot, tampered artifact, lookahead) is an auditable `failed` run with reason.
- `list_optimization_runs` supports the Phase 15 API surface.

---

# Plan 11-06 — Constraint Hardening + Artifact Breadth (PFOL-01/03)

**wave:** 4 · **depends_on:** [11-05] · **autonomous:** true
**requirements:** [PFOL-01, PFOL-03]
files_modified:
- backend/app/portfolio/risk.py (extend — covariance sha256 helper)
- backend/app/portfolio/optimizer.py (extend — covariance artifact wiring)
- backend/app/portfolio/artifacts.py (extend — covariance.json read path)
- backend/app/portfolio/constraints.py (extend — industry-cap gate wired through run_optimization)
- backend/app/portfolio/schemas.py (extend — industry_cap field on OptimizationRequest)
- backend/tests/portfolio/test_risk.py (extend)
- backend/tests/portfolio/test_optimizer.py (extend)

## Objective

Close the last two hardening gaps: the industry-cap fail-closed gate wired through `run_optimization` (a caller requesting an industry cap gets a `failed` run with reason `"industry mapping unavailable"` — never silently ignored, PFOL-03), and the covariance artifact + sha256 breadth in `risk_model_json` (the covariance matrix persisted as `covariance.json` under the run namespace with its sha256 recorded — the Phase 12 risk-suite seam, PFOL-01).

Purpose: PFOL-03's fail-closed contract is only real when the orchestrator enforces it, and PFOL-01's "explicit recorded step" is only complete when the covariance itself is an immutable artifact Phase 12 can load by checksum.
Output: industry-cap gate wired through the orchestrator, covariance artifact + sha256 in `risk_model_json`, green breadth tests.

## Context

- @.planning/phases/11-portfolio-construction-optimization/11-RESEARCH.md — `## Constraint Stack` (industry-cap fail-closed gate), `## Immutable Run Records` (covariance sha256 in risk_model_json), `## Common Pitfalls` (pitfall 8 — industry cap on ungoverned data)
- @.planning/phases/11-portfolio-construction-optimization/11-CONTEXT.md — locked decisions: industry cap deferred fail-closed until a governed industry mapping exists
- backend/app/portfolio/constraints.py (from 11-01) — `assert_industry_cap_unavailable`
- backend/app/portfolio/risk.py (from 11-01) — `sample_covariance` / `check_psd` / `repair_psd`
- backend/app/portfolio/optimizer.py (from 11-01/11-04/11-05) — `run_optimization` orchestrator
- backend/app/portfolio/artifacts.py (from 11-01) — `write_bundle` (covariance.json already written when covariance is provided)
- backend/tests/portfolio/test_optimizer.py / test_risk.py — extend

## Tasks

- **build: Wire the industry-cap fail-closed gate through `run_optimization`**
  - Files: backend/app/portfolio/optimizer.py, backend/app/portfolio/constraints.py, backend/app/portfolio/schemas.py
  - Read first: 11-RESEARCH.md `## Constraint Stack` (INDUSTRY_CAP_ENABLED=False hard gate), backend/app/portfolio/constraints.py (from 11-01 — `assert_industry_cap_unavailable`)
  - Action: Add `industry_cap: float | None = None` to `OptimizationRequest` (schemas.py) and to `run_optimization`: at the top of the orchestrator, call `assert_industry_cap_unavailable(request.industry_cap is not None)` — when an industry cap IS requested, the raised `ValueError("industry mapping unavailable")` is caught by the 11-05 orchestrator's fail-closed wrapper and recorded as a `failed` run with `failure_reason="industry mapping unavailable"` (pitfall 8 — never silently ignored). When `industry_cap` is None, the constraint stack records `industry_cap: null` in `constraint_stack_json` with `policy_version: "phase-11-policy-v1"`. No sector JOIN exists anywhere in `portfolio/` (grep gate).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_optimizer.py -q --tb=short`
  - Done: Requesting an industry cap records a `failed` run with reason `"industry mapping unavailable"`; the constraint stack records `industry_cap: null` when unrequested; no sector JOIN code exists.

- **build: Covariance artifact + sha256 in `risk_model_json`**
  - Files: backend/app/portfolio/risk.py, backend/app/portfolio/optimizer.py, backend/app/portfolio/artifacts.py
  - Read first: 11-RESEARCH.md `## Immutable Run Records` (risk_model_json carries covariance_sha256; optional covariance.json under the same namespace), backend/app/portfolio/artifacts.py (from 11-01 — write_bundle already accepts covariance)
  - Action: In `risk.py`, add `covariance_sha256(cov: np.ndarray) -> str` — sha256 over the canonical JSON of the matrix as list-of-lists rounded to 8 decimals (sorted, canonical serialization matching `_json`). In `optimizer.py`, when the run writes artifacts, pass the repaired covariance to `PortfolioArtifactService.write_bundle(..., covariance=cov)` (covariance.json already supported from 11-01) and add `covariance_sha256` + `covariance_artifact_relative_path` (e.g. `research_artifacts/<run_id>/covariance.json`) to `risk_model_json` — alongside `risk_model`, `dropna`, `window`, and `psd_repair` provenance (PFOL-01: the full recorded step incl. the covariance identity). In `artifacts.py`, extend the read path so `read_artifact(run_id, "covariance.json")` checksum-verifies like the other files (already the generic path).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_risk.py -q --tb=short`
  - Done: Every successful run's `risk_model_json` records `covariance_sha256` + the artifact path; the covariance artifact is checksum-verified immutable; the matrix round-trips through `read_artifact`.

- **test: Extend `test_risk.py` + `test_optimizer.py` — covariance sha256 + industry-cap gate**
  - Files: backend/tests/portfolio/test_risk.py, backend/tests/portfolio/test_optimizer.py
  - Read first: backend/tests/portfolio/test_risk.py / test_optimizer.py (existing green cases), the modules under test
  - Action: Add to `test_risk.py`: (1) `covariance_sha256` is deterministic — identical matrices → identical hex digests; different matrices → different digests; (2) the repaired covariance's digest round-trips through `read_artifact("covariance.json")`. Add to `test_optimizer.py`: (1) a run with `industry_cap=0.05` records a `failed` run with `failure_reason == "industry mapping unavailable"` (via the orchestrator's fail-closed wrapper); (2) a run without an industry cap records `constraint_stack_json["industry_cap"] is None`; (3) the successful run's `risk_model_json` carries `covariance_sha256` (64 hex) and the artifact exists under the run namespace.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_risk.py tests/portfolio/test_optimizer.py -q --tb=short`
  - Done: The covariance identity contract and the industry-cap fail-closed gate are locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short
```

All green. Grep gate: no sector/industry JOIN appears in `backend/app/portfolio/` (pitfall 8); `np.clip` on eigenvalues appears only inside `repair_psd` in `risk.py` (pitfall 1 warning sign).

## Success Criteria

- Industry cap is fail-closed: requesting one records a `failed` run with `"industry mapping unavailable"`; the stack records `industry_cap: null` otherwise.
- `risk_model_json` records `covariance_sha256` + artifact path; the covariance matrix is an immutable, checksum-verified artifact (Phase 12 seam).

---

# Consolidated Threat Model

> `workflow.security_enforcement: true` (config.json) — section required. Trust model: local single-user research host; no new auth/session surface (ASVS V2/V3 N/A). New records are server-issued only (V4 minimal). Pydantic strict DTOs + solver-options whitelist (V5); SHA-256 checksums for snapshots/artifacts/run rows (V6).

## Trust Boundaries

| Boundary | Description |
|---|---|
| Composite artifact → optimizer | Expected returns cross the boundary as frozen bytes; every read is checksum-verified against `output_sha256`; fail-closed on mismatch. |
| Optimizer → cvxpy/Clarabel | Solver options cross as a fixed whitelist (`SOLVER_OPTIONS_ALLOWLIST`), never caller-supplied kwargs; verbatim options recorded for audit. |
| Covariance → cp.quad_form | Only PSD-verified matrices cross (fail-closed gate with provenance); an indefinite matrix must be repaired AND recorded before any solve. |
| Run records → operational.db | Append-only `portfolio_optimization_runs`; immutability triggers block UPDATE/DELETE; failed runs retained with reason. |
| Weights/covariance → artifact store | O_EXCL namespace + per-file O_EXCL + fsync + sha256; reads verify the descriptor checksum. |

## STRIDE / ASVS L1 Traceability

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|---|---|---|---|---|---|
| T-11-01 | Spoofing | Composite artifact substitution / tampering | high | mitigate | Checksum-verified artifact read (`output_sha256` vs bytes, frozen_panel pattern) in `snapshot.py`; fail closed on absent/tampered/mismatch — recorded as a `failed` run (11-05). Test: test_snapshot_binding cases 2-4. |
| T-11-02 | Tampering | Silent PSD repair hiding bad risk | high | mitigate | `repair_psd` provenance (method/epsilon/eigenvalues before/after) is a mandatory `risk_model_json` field; `ensure_psd_provenance` refuses to build the QP without it; `np.clip` on eigenvalues exists only inside `risk.py` (11-01, grep-gated in 11-06). |
| T-11-03 | Tampering | Run-record tampering after the fact | high | mitigate | Append-only table + `no_update`/`no_delete` triggers; `CHECK (problem_status IN ('failed','solver_error')) = (failure_reason IS NOT NULL)` (11-02). Test: test_repository UPDATE/DELETE + failed-reason cases. |
| T-11-04 | Tampering | Solver-option injection (arbitrary kwargs) | medium | mitigate | `SOLVER_OPTIONS_ALLOWLIST` fixed frozenset is the ONLY accepted `solve()` key surface; verbatim options recorded per run (11-01). |
| T-11-05 | Elevation of Privilege (data) | Lookahead (as_of before composite artifact) | medium | mitigate | `as_of`-vs-artifact `created_at` guard in `snapshot.py`; recorded `failed` run with reason (11-05). |
| T-11-06 | Tampering | Un-governed industry cap | medium | mitigate | `INDUSTRY_CAP_ENABLED=False` hard gate; `assert_industry_cap_unavailable` wired through `run_optimization`; requested cap → `failed` run with reason `"industry mapping unavailable"` (11-06). |
| T-11-07 | Spoofing | Weight/covariance artifact tampering | medium | mitigate | O_EXCL namespace + fsync + sha256 (`PortfolioArtifactService`); `output_sha256` on the run row; checksum-verified reads (11-01). |
| T-11-08 | Tampering | cvxpy version drift changing solver results | medium | mitigate | `cvxpy==1.9.2` exact pin; `cp.__version__` + solver package versions (`importlib.metadata.version` with fixed mapping) recorded in every run (11-02, 11-04). |
| T-11-09 | Information Disclosure | `optimal_inaccurate` treated as success | medium | mitigate | Honest `problem_status` capture from `problem.status`; never promoted; recorded verbatim (11-01/11-04). |
| T-11-SC | Tampering | Python package supply chain (cvxpy + solver stack) | high | mitigate | PyPI-verified package-legitimacy audit (RESEARCH.md — npm results are cross-ecosystem false positives); empty-`.venv` Wave 0 gate re-verifies versions + `installed_solvers()` at install time (11-02). |

# Phase Verification

```bash
# Per-wave gates (from backend/)
cd backend && uv sync && uv pip check && .venv/bin/python -c "import cvxpy as cp, sys; sys.exit(0 if cp.__version__ == '1.9.2' and 'CLARABEL' in cp.installed_solvers() else 1)"   # wave 0 — 1.9.2 + CLARABEL (exit 1 on mismatch)
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short                                          # wave 0
cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short                                                             # wave 0 (expected RED scaffolds)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py tests/portfolio/test_risk.py tests/portfolio/test_optimizer.py tests/portfolio/test_hrp.py tests/portfolio/test_repository.py -q --tb=short  # wave 1 (tracer)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_hrp.py tests/portfolio/test_pipeline.py -q --tb=short                # wave 2 (HRP)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_optimizer.py tests/portfolio/test_pipeline.py -q --tb=short          # wave 2 (min-vol/max-Sharpe)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_snapshot_binding.py tests/portfolio/test_repository.py tests/research/test_models.py -q --tb=short  # wave 3
cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short                                                             # wave 4 (full portfolio suite)

# Phase gate (before /gsd-verify-work)
cd backend && .venv/bin/python -m pytest -x
```

Cross-module integrity checks:
- Run `input_snapshot_sha256` == `factor_model_composites.input_snapshot_sha256` for the recorded snapshot (11-05 cross-module test).
- Library composite used as expected returns == artifact bytes verified by `output_sha256` (11-05 test_snapshot_binding + test_models extension).
- PSD provenance present in `risk_model_json` whenever the covariance was repaired (11-01 test_risk never-silent; Phase 12 risk suite inherits).
- Grep gate hygiene: negative greps (`build_composite` absent from `portfolio/`, sector JOIN absent, `np.clip` on eigenvalues only in `risk.py`) use `grep -v '^#'` filtering where comments could self-invalidate.

# Phase Success Criteria

- All 6 plans complete with their per-plan gates green.
- The full backend suite is green before `/gsd-verify-work` (phase gate).
- Every locked decision in 11-CONTEXT.md is implemented (see Source Coverage Audit): sample covariance + PSD check/repair with mandatory provenance (PFOL-01), long-only min-vol + HRP baseline with max-Sharpe explicit non-default (PFOL-02), the constraint stack with industry-cap fail-closed (PFOL-03), and immutable run records with snapshot sha256 / solver name-version-options / status / weights / failure reasons (PFOL-04).
- The composite expected-return input is consumed BY SNAPSHOT (checksum-verified artifact + `input_snapshot_sha256`), never a live module hand-off; `build_composite` appears nowhere in `backend/app/portfolio/`.
- Deferred ideas from CONTEXT (industry cap until a governed mapping exists, Black-Litterman, max-Sharpe first-class, short selling, auto-rebalance, ML expected returns) do NOT appear in any delivered artifact.

# Output

After each plan completes, create the matching summary at `.planning/phases/11-portfolio-construction-optimization/11-{NN}-SUMMARY.md` documenting what landed, the evidence, and any deviations from this plan. The phase gate is the full backend suite green before `/gsd-verify-work`.

