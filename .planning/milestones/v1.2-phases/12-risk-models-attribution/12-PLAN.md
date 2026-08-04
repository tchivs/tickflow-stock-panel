---
phase: 12-risk-models-attribution
plan: phase-plan
type: execute
requirements: [RSK-01, RSK-02, RSK-03]
wave_summary:
  wave_0: [12-02]
  wave_1: [12-01]
  wave_2: [12-03, 12-04]
  wave_3: [12-05]
  wave_4: [12-06]
must_haves:
  truths:
    - "Researcher can inspect risk exposure and marginal contribution attribution for an optimized portfolio, and the attribution reconciles exactly to portfolio variance (cross-module integrity check) (RSK-01)."
    - "Researcher can select among sample, semi-covariance, exponentially weighted, and Ledoit-Wolf risk models, and every PSD repair records method, epsilon, and eigenvalues before/after (RSK-02)."
    - "Researcher can inspect drawdown attribution decomposed by instrument and time segment (RSK-03)."
    - "Attribution consumes the Phase 11 run's checksum-verified covariance artifact (risk_model_detail.covariance_sha256 + covariance_artifact_relative_path) — never a recomputed live covariance — and every analysis lands as an append-only evidence row bound to a checksum-verified artifact."
    - "scikit-learn 1.8.0 is lazy-imported at the risk-model boundary only (never a module-top import); every one of the four risk models records explicit PSD-repair provenance (method/epsilon/eigenvalues before/after), never silent."
  artifacts:
    - path: backend/app/portfolio/risk.py
      provides: "semi_covariance / ewma_covariance / ledoit_wolf_covariance + make_risk_model_family dispatcher with per-model PSD provenance and the sklearn lazy-import boundary"
    - path: backend/app/portfolio/attribution.py
      provides: "portfolio_variance / portfolio_exposure / marginal_contributions / reconcile_attribution with the hard sum(MC) == variance assertion + attribution_report"
    - path: backend/app/portfolio/drawdown.py
      provides: "underwater_curve / drawdown_periods / drawdown_attribution (per-instrument × per-segment decomposition with the segment reconciliation identity)"
    - path: backend/app/portfolio/analyzer.py
      provides: "run_attribution / run_drawdown orchestrators — checksum-verified covariance load → compute → O_EXCL artifact → append-only evidence row (never any execution route)"
    - path: backend/app/portfolio/artifacts.py
      provides: "write_analysis_artifact — O_EXCL + fsync + sha256 analysis artifacts inside the run's existing namespace"
    - path: backend/app/portfolio/repository.py
      provides: "record/get/list attribution evidence — append-only rows over portfolio_risk_attribution_evidence with reconciliation + sha256 invariants"
    - path: backend/app/operational/migrations.py
      provides: "portfolio_risk_attribution_evidence append-only table (4-model risk_model CHECK, reconciliation invariant, triggers); portfolio_optimization_runs risk_model CHECK widened per approved decision"
    - path: backend/app/portfolio/optimizer.py
      provides: "risk_model_name dispatch in _build_risk_model + OptimizationRequest.risk_model selection recorded in risk_model_json / runs row (RSK-02 seam)"
    - path: backend/tests/portfolio/
      provides: "test_attribution / test_drawdown (new) + test_risk / test_pipeline / test_repository / conftest extensions + test_operational_migrations.py evidence-table cases"
  key_links:
    - from: portfolio/analyzer.py
      to: portfolio/artifacts.py
      via: "run_attribution loads the run's covariance ARTIFACT bytes checksum-verified against risk_model_detail['covariance_sha256'] — never a recomputed live covariance (cross-module integrity)"
      pattern: "read_artifact"
    - from: portfolio/attribution.py
      to: portfolio/analyzer.py
      via: "reconcile_attribution hard-asserts sum(marginal_contributions) == wᵀΣw (rtol 1e-12) before any evidence write — the cross-module integrity guard, never approximate"
      pattern: "reconcile_attribution"
    - from: portfolio/risk.py
      to: portfolio/optimizer.py
      via: "make_risk_model_family is the single PSD-provenance path all four models pass through; _build_risk_model dispatches on risk_model_name"
      pattern: "make_risk_model_family"
    - from: portfolio/repository.py
      to: operational/migrations.py
      via: "portfolio_risk_attribution_evidence append-only row; run_id FK → portfolio_optimization_runs; output_sha256 == analysis artifact bytes"
      pattern: "record_attribution_evidence"
    - from: portfolio/drawdown.py
      to: backtest/engine.py
      via: "underwater-curve semantics follow the equity-curve reference (engine.simulate_portfolio is reference-only; drawdown.py never calls the engine — returns/weights are passed in)"
      pattern: "drawdown_periods"
---

# Phase 12: Risk Models & Attribution — Executable Plan

## Phase Goal

Researchers can inspect risk exposure and marginal contribution attribution — reconciling exactly to portfolio variance — backed by a risk-model suite whose every PSD repair carries explicit provenance, plus drawdown attribution by instrument and time segment.

## Scope

**In scope (RSK-01..03):** risk exposure + marginal contribution attribution that reconciles EXACTLY to total portfolio variance (cross-module integrity check, hard assertion — never approximate); per-instrument contribution + summary; the extended risk-model suite (semi-covariance, exponentially weighted covariance/EWMA λ=0.94, Ledoit-Wolf shrinkage via lazy-imported scikit-learn 1.8.0) with explicit PSD-repair provenance for every model (method/epsilon/eigenvalues before/after — never silent); drawdown attribution decomposed by instrument AND time segment (underwater curve → drawdown periods → per-instrument contribution table); append-only attribution evidence rows bound to checksum-verified O_EXCL + fsync + sha256 artifacts; consumption of Phase 11 immutable run records (weights + checksum-bound covariance artifact by `covariance_sha256`) — never modifying them.

**Out of scope:** walk-forward validation + parameter search (Phase 13), RebalancePlan + paper rebalance (Phase 14), API/frontend panels (Phase 15). No execution authority anywhere — this is a read/analyze layer over immutable records. Deferred ideas from `12-CONTEXT.md` (Black-Litterman, ML expected returns, walk-forward/parameter search, frontend panels) MUST NOT appear in any task. PyPortfolioOpt / skfolio / riskfolio-lib remain design references only — never runtime dependencies (their contracts are the design spec; the Phase 12 suite is hand-rolled over numpy/scipy with sklearn only at the Ledoit-Wolf boundary).

## Source Coverage Audit

| Source | ID | Required behavior or constraint | Plans | Status |
|---|---|---|---|---|
| GOAL | Phase 12 | Exposure/contribution attribution reconciling exactly to portfolio variance; risk-model suite with PSD provenance; drawdown attribution by instrument and time segment | 12-01..12-06 | COVERED |
| REQ | RSK-01 | Risk exposure + marginal contribution attribution; attribution reconciles to portfolio variance (cross-module integrity check) | 12-01, 12-04, 12-05 | COVERED |
| REQ | RSK-02 | Risk-model suite: semi-covariance, exponentially weighted covariance, Ledoit-Wolf shrinkage with explicit PSD-repair provenance (P2) | 12-02, 12-03, 12-05 | COVERED |
| REQ | RSK-03 | Drawdown attribution decomposed by instrument and time segment (P2) | 12-01, 12-06 | COVERED |
| CONTEXT | Risk-model suite | Ledoit-Wolf uses scikit-learn 1.8.0 lazy-imported at the risk-model boundary (shadow extra — never module-top; Phase 10 import-audit contract); every model's PSD repair records explicit provenance (method/epsilon/eigenvalues before/after) reusing Phase 11 eigen-clip | 12-03 | COVERED |
| CONTEXT | Attribution | Exposure = weight · covariance per instrument; MC = weight · (covariance · weight); sum of contributions == portfolio variance as a HARD assertion, not approximate | 12-01, 12-04 | COVERED |
| CONTEXT | Drawdown | Standard underwater curve identifies drawdown periods; output = periods + per-instrument contribution table | 12-01, 12-06 | COVERED |
| CONTEXT | Integration | Risk models + PSD provenance recorded into risk_model_json (Phase 11 covariance_sha256 seam continues); attribution reads Phase 11 immutable run records, never modifies them (append-only contract); new models reuse the sample-covariance path + canonical hashing | 12-01, 12-03, 12-05 | COVERED |
| CONTEXT | Discretion | Exact semi/EWMA/Ledoit-Wolf formulas (standard implementations), EWMA λ=0.94 (RiskMetrics), shrinkage from sklearn; drawdown depth/duration thresholds (module constants, recorded in evidence); attribution/drawdown evidence schema (append-only, following existing conventions) | 12-02, 12-03, 12-06 | COVERED |
| CODE | Migrations | portfolio_optimization_runs.risk_model CHECK currently allows only sample_covariance_v1; RSK-02 selection needs the 4-model enum — one-way-door schema decision | 12-02 | COVERED (checkpoint:decision) |
| CODE | Lazy-import | `from sklearn.covariance import LedoitWolf` must appear only inside a risk.py function; subprocess gate asserts `"sklearn" not in sys.modules` after `import app.portfolio.risk` | 12-03 | COVERED |

**Exclusions (not gaps):** deferred ideas in `12-CONTEXT.md`; Phase 13-15 scope; PyPortfolioOpt / skfolio / riskfolio-lib as runtime deps (design spec only); walk-forward consuming risk models per-fold (Phase 13 — the `make_risk_model_family` seam is pre-built for it).

## Plan List

- [ ] 12-01: **Tracer** — end-to-end attribution on a fixture run: load a Phase 11 run record → checksum-verified covariance artifact → exposure + marginal contribution → hard variance reconciliation assertion → append-only evidence row; drawdown identity path (RSK-01/03)
- [ ] 12-02: **Wave 0 foundations** — append-only attribution evidence migration + risk-model enum decision (one-way-door checkpoint), 2 new test files + conftest fixtures + test_risk new-model RED cases
- [ ] 12-03: **Risk-model suite breadth** — semi_covariance / ewma_covariance / ledoit_wolf_covariance with per-model PSD provenance + make_risk_model_family + optimizer risk_model_name dispatch (RSK-02)
- [ ] 12-04: **Attribution breadth** — signed variance components (negative MC = diversifier), full summary report, evidence invariants (RSK-01)
- [ ] 12-05: **Cross-model attribution + reconciliation breadth** — run_attribution under all four risk models with the exact reconciliation per model, checksum-bound identity path, evidence list API (RSK-01/02)
- [ ] 12-06: **Drawdown attribution breadth** — per-instrument × per-segment decomposition with the segment reconciliation identity, full report + evidence (RSK-03)

## Wave Structure

| Wave | Plans | Purpose |
|------|-------|---------|
| 0 | 12-02 | Foundations: evidence-table migration + risk-model enum (one-way-door checkpoint), Wave 0 test scaffolding — prerequisites for the tracer. |
| 1 | 12-01 | The tracer: prove the whole attribution spine end-to-end on a fixture run (record → checksum-bound covariance → exposure/MC → hard reconciliation → evidence) before any breadth. |
| 2 | 12-03, 12-04 | Risk-model suite ∥ attribution breadth — parallel plans, zero file overlap (12-03: risk.py/optimizer.py/test_risk.py/test_pipeline.py; 12-04: attribution.py/analyzer.py/test_attribution.py). |
| 3 | 12-05 | Cross-model attribution + reconciliation breadth — the four-model reconciliation contract and the evidence API surface. |
| 4 | 12-06 | Drawdown attribution breadth — instrument × time-segment decomposition (sequential after 12-04: shares analyzer.py). |

## Artifacts this phase produces

| Artifact | Kind | Provides |
|---|---|---|
| `semi_covariance` / `ewma_covariance` / `ledoit_wolf_covariance` / `make_risk_model_family` (risk.py) | functions | 3 new risk models (PyPortfolioOpt contracts as design spec; EWMA λ=0.94 RiskMetrics; sklearn lazy-import boundary) + a single PSD-provenance dispatcher shared with Phase 13 (RSK-02) |
| `portfolio_variance` / `portfolio_exposure` / `marginal_contributions` / `reconcile_attribution` / `attribution_report` (attribution.py) | functions | exposure = w·(Σw) signed; MC = w·(Σw) as the variance decomposition; hard sum(MC) == wᵀΣw assertion (rtol 1e-12, never approximate); full summary report (RSK-01) |
| `underwater_curve` / `drawdown_periods` / `drawdown_attribution` (drawdown.py) | functions | underwater series → drawdown periods (depth ≥ 2%, duration ≥ 2 obs — module constants) → per-instrument × per-segment contributions with the segment reconciliation identity Σc_i == segment return (RSK-03) |
| `run_attribution` / `run_drawdown` (analyzer.py) | functions | orchestrators: checksum-verified covariance load → compute → O_EXCL artifact under the run namespace → append-only evidence row; no execution routes (RSK-01/03) |
| `write_analysis_artifact` (artifacts.py) | function | O_EXCL + fsync + sha256 analysis artifacts inside the run's existing namespace (never recreating it); reads via the existing checksum-verified `read_artifact` |
| `record_attribution_evidence` / `get_attribution_evidence` / `list_attribution_evidence` (repository.py) | methods | append-only evidence rows over `portfolio_risk_attribution_evidence` with attribution_type/risk_model enums, sha256 + reconciliation invariants, run_id FK |
| `portfolio_risk_attribution_evidence` + risk_model enum widening (migrations.py) | SQLite table + migration | append-only evidence rows (CHECKs + triggers); `portfolio_optimization_runs.risk_model` CHECK widened to the 4-model enum per the approved one-way-door decision |
| `OptimizationRequest.risk_model` + `_build_risk_model` dispatch (schemas.py / optimizer.py) | field + function | explicit risk-model selection recorded verbatim in the runs row + risk_model_json (RSK-02 seam) |
| tests/portfolio/{test_attribution,test_drawdown}.py + test_risk/test_pipeline/test_repository/conftest + tests/test_operational_migrations.py | test files | per-requirement unit contracts + the end-to-end tracer proof + evidence-table migration cases |

## Requirement → Plan Mapping

| Requirement | Behavior | Plans | Verification command |
|---|---|---|---|
| RSK-01 | Exposure + marginal contribution attribution reconciling exactly to portfolio variance (hard assertion) | 12-01, 12-04, 12-05 | `pytest tests/portfolio/test_attribution.py tests/portfolio/test_pipeline.py -q --tb=short` |
| RSK-02 | Semi / EWMA / Ledoit-Wolf with explicit PSD provenance; sklearn lazy-import | 12-02, 12-03, 12-05 | `pytest tests/portfolio/test_risk.py tests/portfolio/test_pipeline.py -q --tb=short` |
| RSK-03 | Drawdown attribution by instrument and time segment | 12-01, 12-06 | `pytest tests/portfolio/test_drawdown.py -q --tb=short` |
| Migration | Evidence table + 4-model enum + triggers; forward-only idempotence | 12-02 | `pytest tests/test_operational_migrations.py -q --tb=short` |
| Cross-module | Attribution covariance == the run's covariance artifact by sha256 checksum | 12-01, 12-05 | `pytest tests/portfolio/test_attribution.py -q --tb=short` |

All commands run from `backend/` with the project interpreter: `cd backend && .venv/bin/python -m pytest …`.

---

# Plan 12-01 — Tracer: End-to-End Attribution on a Fixture Run (RSK-01/03)

**wave:** 1 · **depends_on:** [12-02] · **autonomous:** true
**requirements:** [RSK-01, RSK-03]
**files_modified:**
- backend/app/portfolio/attribution.py (new)
- backend/app/portfolio/drawdown.py (new)
- backend/app/portfolio/analyzer.py (new)
- backend/app/portfolio/artifacts.py (extend — write_analysis_artifact)
- backend/app/portfolio/repository.py (extend — evidence methods)
- backend/tests/portfolio/test_pipeline.py (extend — end-to-end tracer test)

## Objective

Prove the complete Phase 12 spine on a fixture run, end to end, before any breadth: record a Phase 11 min-vol run on the fixture composite → load the run's checksum-verified covariance artifact (`covariance_sha256` verified against `risk_model_detail`) → compute per-instrument exposure + marginal contributions → assert sum(MC) == portfolio variance EXACTLY (rtol 1e-12 — the cross-module integrity guard, never approximate) → write the exposure/contribution artifact O_EXCL + fsync + sha256 under the run namespace → append an immutable evidence row (reconciliation_json recorded) → read it back. The drawdown identity path proves the same spine for drawdown (underwater curve + periods, empty on the fixture series, evidence row with period_count 0).

Purpose: This is the risk-analysis layer's keel. It forces the checksum-bound covariance consumption (attribution reads the SAME covariance bytes the run recorded — never a recomputed live covariance), the exact-reconciliation assertion (a hard invariant, not a tolerance story), and the append-only evidence discipline into existence on the first commit, and catches a dead-end (checksum drift, reconciliation failure, evidence-row write failure) before breadth is committed. Functionality is fixture-scoped (StubBacktestEngine fixture panel + fixture composite + tmp_path repository + tmp_path artifact root); no architectural gap is left.
Output: `attribution.py`, `drawdown.py`, `analyzer.py` (identity path), the `write_analysis_artifact` seam, the repository evidence methods, and the green tracer test that locks the contracts.

## Context

- @.planning/phases/12-risk-models-attribution/12-CONTEXT.md — locked decisions: exposure/MC formulas, hard reconciliation, checksum-bound covariance consumption, append-only evidence (never modifying run records)
- backend/app/portfolio/optimizer.py — `_build_risk_model` (L415-442, the `risk_model_json` shape the tracer reads: risk_model / window / dropna / psd_repair / covariance_sha256), the 11-06 `covariance_artifact_relative_path` seam (L751-757, L922), and `run_optimization`'s fail-closed wrapper (the pattern the analyzers follow: no silent aborts)
- backend/app/portfolio/artifacts.py — `_write_json` O_EXCL + fsync + sha256 (L140-181), `_namespace` (L153-163), `read_artifact` checksum-verified read (L120-138)
- backend/app/portfolio/repository.py — `record_optimization_run` + `_record` JSON unwrap pattern (L40-133) — the evidence methods mirror it
- backend/app/portfolio/risk.py — `covariance_sha256` canonical 8-decimal hashing (the round-8 byte identity the artifact checksum-verifies against)
- backend/tests/portfolio/conftest.py — `StubBacktestEngine` + `fixture_composite` + `portfolio_repository` + `artifact_root` fixtures; the `fixture_attribution_run` fixture lands in 12-02
- backend/tests/portfolio/test_pipeline.py — the Phase 11 end-to-end tracer test (the pattern this plan's tracer test mirrors)

## Tasks

- **build: Create `portfolio/attribution.py` — exposure + marginal contribution + hard reconciliation**
  - Files: backend/app/portfolio/attribution.py
  - Read first: 12-CONTEXT.md `## Specific Ideas` (the MC formula: `MC_i = w_i · (Σ·w)_i`, portfolio variance `wᵀΣw`), backend/app/portfolio/risk.py `covariance_sha256` (round-8 byte identity), backend/app/portfolio/optimizer.py `_build_risk_model` (risk_model_json shape)
  - Action: Module docstring states know/don't-know per CONVENTIONS.md (knows: variance/exposure/MC decomposition on a covariance matrix; does not know: solving, risk-model construction, artifacts, repository, market time series). Implement, pure numpy, no cvxpy/sklearn: `portfolio_variance(weights: np.ndarray, cov: np.ndarray) -> float` = `float(weights @ (cov @ weights))`; `portfolio_exposure(weights, cov) -> np.ndarray` = `weights * (cov @ weights)` (weight × covariance with the portfolio — kept SIGNED: negative = diversifier, never abs()ed); `marginal_contributions(weights, cov) -> np.ndarray` — the same product vector interpreted as the variance decomposition (per CONTEXT the exposure and MC share the formula; the distinction is semantic — exposure = risk footprint, MC = variance decomposition); `reconcile_attribution(weights, cov) -> dict` computes variance + MC and runs the HARD assertion `np.testing.assert_allclose(np.sum(mc), variance, rtol=1e-12, atol=1e-15)` — the cross-module integrity check, never approximate; returns `{"portfolio_variance": float, "marginal_contributions": dict[str, float] (symbol → value), "sum_contributions": float, "reconciliation_error": float}`. Reject non-finite weights/cov (raise ValueError — fail closed). Every function accepts weights/cov and returns plain numpy/dicts — no I/O.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py -q --tb=short` (the identity-path cases in the Wave 0 scaffold turn green)
  - Done: variance/MC/exposure match the analytical reference on a fixture; `np.sum(mc) == variance` holds to rtol 1e-12; the reconciliation is a hard assertion (a deliberately perturbed MC vector raises).

- **build: Create `portfolio/drawdown.py` — underwater curve + period detection (identity path)**
  - Files: backend/app/portfolio/drawdown.py
  - Read first: 12-CONTEXT.md `## Drawdown Attribution` (underwater curve → periods → per-instrument table), backend/app/backtest/engine.py `simulate_portfolio` (L755-903 — the equity-curve shape is the REFERENCE for the underwater semantics; drawdown.py NEVER calls the engine, returns/weights are passed in)
  - Action: Module docstring know/don't-know (knows: underwater-curve math on a portfolio-returns series; does not know: simulation, weights provenance, repository, artifacts). Module constants `DRAWDOWN_DEPTH_THRESHOLD = 0.02` and `DRAWDOWN_MIN_OBS = 2` (documented discretion — recorded in the evidence reconciliation_json). Implement `underwater_curve(portfolio_returns: np.ndarray) -> np.ndarray` = `equity / np.maximum.accumulate(equity) - 1` where `equity = np.cumprod(1 + portfolio_returns)`; `drawdown_periods(underwater: np.ndarray, *, depth_threshold: float = DRAWDOWN_DEPTH_THRESHOLD, min_obs: int = DRAWDOWN_MIN_OBS) -> list[dict]` — contiguous spans where `underwater < -depth_threshold` with length ≥ min_obs, each `{"start_idx": int, "end_idx": int, "depth": float}` (depth = min underwater in the span); flat/short/empty series → `[]`. Pure numpy; the tracer proves the empty path (fixture returns have no period at identity) + full wiring; breadth in 12-06.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_drawdown.py -q --tb=short`
  - Done: the underwater curve matches the cumprod reference; a flat series and a short series produce `[]`; the thresholds are module constants.

- **build: Extend `PortfolioArtifactService` with `write_analysis_artifact`**
  - Files: backend/app/portfolio/artifacts.py
  - Read first: backend/app/portfolio/artifacts.py `_write_json` (L140-181) + `_namespace` (L153-163) — the O_EXCL discipline the analysis writer must reuse
  - Action: Add `write_analysis_artifact(run_id: str, *, subdir: str, filename: str, payload: object) -> ArtifactDescriptor` — resolves the run's existing namespace (`research_artifacts/<run_id>/`); if the namespace does not exist raise `ArtifactWriteError` (the optimization bundle owns it — NEVER recreate, that would break the O_EXCL run namespace); write `research_artifacts/<run_id>/<subdir>/<filename>` through the existing `_write_json` (O_EXCL + fsync + sha256; `subdir`/`filename` must be managed basenames — reject `..` and separators, mirroring `_namespace`'s escape guard); return the descriptor. The read side already exists: `read_artifact(relative_path, checksum_sha256=...)`. No change to `write_bundle`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py -q --tb=short`
  - Done: an analysis artifact lands inside an existing run namespace without recreating it; a second write to the same path fails (O_EXCL); `write_analysis_artifact` on a missing run namespace raises; reads checksum-verify.

- **build: Extend `PortfolioRepository` with attribution-evidence methods**
  - Files: backend/app/portfolio/repository.py
  - Read first: backend/app/portfolio/repository.py `record_optimization_run` + `_record` (L40-133 — the canonical-JSON + unwrap pattern to mirror), the 12-02 evidence-table schema
  - Action: Add `_ATTRIBUTION_TYPES = frozenset({"exposure_contribution", "drawdown"})` and a 4-model `_RISK_MODELS_PHASE12 = frozenset({"sample_covariance_v1", "semi_covariance_v1", "ewma_covariance_v1", "ledoit_wolf_v1"})` (the evidence-table enum; `_RISK_MODELS` for the runs table stays as approved in 12-02). `record_attribution_evidence(**fields)` — required fields id/attribution_type/run_id/risk_model/as_of/output_sha256/artifact_relative_path/reconciliation_json/created_at; validate attribution_type in `_ATTRIBUTION_TYPES`, risk_model in `_RISK_MODELS_PHASE12`, `output_sha256` 64-hex, and the invariant `(attribution_type == "exposure_contribution") == (reconciliation_json is not None)` (mirrors the DB CHECK); canonical JSON via `_json`; atomic INSERT; return the row with `reconciliation_json` unwrapped to `reconciliation`. `get_attribution_evidence(evidence_id)` and `list_attribution_evidence(*, run_id=None, attribution_type=None, limit=200)` ordered by `created_at, id` with the same positive-int limit fail-closed as `list_optimization_runs`. No UPDATE/DELETE surface (table triggers enforce append-only).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_repository.py -q --tb=short`
  - Done: evidence rows round-trip through get/list; the reconciliation invariant and sha256 validation fail closed; UPDATE/DELETE on the evidence table raise (triggers); list filters by run_id/attribution_type and caps at limit.

- **build: Create `portfolio/analyzer.py` — run_attribution + run_drawdown orchestrators**
  - Files: backend/app/portfolio/analyzer.py
  - Read first: backend/app/portfolio/optimizer.py `run_optimization` (L460-523, the fail-closed orchestrator pattern — no silent aborts; the analyzer is read-only, never writes run records), backend/app/portfolio/artifacts.py `read_artifact`, 12-CONTEXT.md `## Integration with Phase 11`
  - Action: Module docstring know/don't-know (knows: how to load a run record + its checksum-bound covariance, compute attribution, write evidence; does not know: solving, optimization runs creation, market time series). `run_attribution(run_id: str, *, repository: PortfolioRepository, artifact_service_root: Path) -> dict` — (1) `run = repository.get_optimization_run(run_id)`; a missing run raises `ValueError` (caller error — no evidence row is fabricated); (2) load the checksum-verified covariance: `risk_model = run["risk_model_detail"]`, read `risk_model["covariance_artifact_relative_path"]` via `PortfolioArtifactService(artifact_service_root).read_artifact(relative_path, checksum_sha256=risk_model["covariance_sha256"])` and `json.loads` it to an (n, n) array — NEVER a recomputed live covariance (cross-module integrity: the attribution reconciles on the SAME bytes the run recorded); a checksum mismatch raises `ArtifactReadError`; (3) `reconcile_attribution(np.asarray(list(run["output_weights"].values())), cov)` with symbols aligned to `list(run["output_weights"].keys())`; (4) write `write_analysis_artifact(run_id, subdir="attribution", filename="exposure_contribution.json", payload={"weights", "exposure", "marginal_contributions", "portfolio_variance", "reconciliation"})`; (5) `repository.record_attribution_evidence(attribution_type="exposure_contribution", run_id=run_id, risk_model=run["risk_model"], as_of=run["as_of"], output_sha256=<descriptor.checksum_sha256>, artifact_relative_path=<descriptor.relative_path>, reconciliation_json={"portfolio_variance", "sum_contributions", "max_abs_error"})`; (6) return the evidence record. `run_drawdown(run_id: str, *, returns: np.ndarray, repository: PortfolioRepository, artifact_service_root: Path) -> dict` — identity path: weights from the run row, portfolio returns = `weights @ returns.T`, `underwater_curve` + `drawdown_periods` (empty on the fixture), write `drawdown.json` with `{"underwater", "periods", "max_depth": 0.0}`, record evidence `attribution_type="drawdown"` with `reconciliation_json={"period_count": 0, "max_depth": 0.0}`. Failures raise (evidence is only written for successful analyses); NO execution routes anywhere.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py -q --tb=short`
  - Done: `run_attribution` reads the run's own checksum-verified covariance artifact and reconciles exactly; both orchestrators write O_EXCL artifacts + append-only evidence rows; the evidence record read-back matches.

- **test: End-to-end tracer proof — `tests/portfolio/test_pipeline.py`**
  - Files: backend/tests/portfolio/test_pipeline.py
  - Read first: the existing Phase 11 pipeline test + `tests/portfolio/conftest.py` (`fixture_attribution_run` fixture from 12-02), backend/app/portfolio/analyzer.py (module under test)
  - Action: Write one integration test walking the full spine on a fixture: `fixture_attribution_run` (a min-vol run recorded on the fixture composite) → `run_attribution(run_id)` → assert `portfolio_variance == float(w @ (cov @ w))` on the round-8 artifact matrix, `abs(sum(marginal_contributions) - portfolio_variance) <= 1e-12 * portfolio_variance` (hard reconciliation), the evidence row exists with `risk_model == run["risk_model"]`, `output_sha256` verifies the artifact bytes, `reconciliation` present; a SECOND `run_attribution(run_id)` writes a SECOND evidence row (append-only — distinct evidence ids, no O_EXCL clash on the run namespace); `run_drawdown(run_id, returns=fixture_returns_long)` → evidence row `attribution_type="drawdown"` with `period_count == 0` and the artifact read-back checksum-verifies; tampering the covariance artifact bytes then re-running attribution raises `ArtifactReadError` and writes NO evidence row.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py -q --tb=short`
  - Done: the full Phase 11 run → checksum-verified covariance → exposure/MC → hard variance reconciliation → append-only evidence path works end-to-end on a fixture — the spine is proven before any breadth plan starts.

## Verification

```bash
cd backend && .venv/bin/python -m pytest \
  tests/portfolio/test_pipeline.py \
  tests/portfolio/test_attribution.py \
  tests/portfolio/test_drawdown.py \
  tests/portfolio/test_repository.py \
  -q --tb=short
```

All green. Grep gate: no `np.cov` / `sample_covariance` / `make_risk_model_family` call exists inside `portfolio/attribution.py` or `portfolio/drawdown.py` (the analyzers consume the run's covariance ARTIFACT, never recompute it); `simulate_portfolio` appears nowhere in `portfolio/` (the engine is reference-only).

## Success Criteria

- Attribution reconciles EXACTLY to portfolio variance (rtol 1e-12 hard assertion) on the run's own checksum-verified covariance bytes — the cross-module integrity guard.
- Every analysis lands as an append-only evidence row bound to an O_EXCL + fsync + sha256 artifact; run records are never modified.
- The drawdown identity path (underwater curve + empty periods + evidence row) is wired end-to-end on the fixture.
- The tracer test proves the full path on a fixture.

---

# Plan 12-02 — Wave 0: Evidence Migration, Risk-Model Enum, Test Scaffolding

**wave:** 0 · **depends_on:** [] · **autonomous:** false (one one-way-door checkpoint:decision gate)
**requirements:** [RSK-01, RSK-02, RSK-03]
**files_modified:**
- backend/app/operational/migrations.py
- backend/tests/test_operational_migrations.py
- backend/tests/portfolio/conftest.py
- backend/tests/portfolio/test_attribution.py (new — RED scaffold)
- backend/tests/portfolio/test_drawdown.py (new — RED scaffold)
- backend/tests/portfolio/test_risk.py (extend — 3 new-model RED cases)

## Objective

Land the irreversible foundations every other plan builds on: the append-only attribution-evidence table in the existing operational.db migration sequence, the risk-model enum decision (the one-way schema door RSK-02's "select among risk models" needs), and the base test scaffolding (2 new test files + conftest fixtures + new-model RED cases) that 12-01/12-03 turn green. The one-way-door decisions (new append-only table; the `portfolio_optimization_runs.risk_model` CHECK widening) are gated behind an explicit `checkpoint:decision` task BEFORE any implementation — per the reversibility contract both are `one-way` (undoing requires a follow-up schema migration that breaks the Phase 12 contract).

Purpose: Every later plan assumes this table and these test files exist. Wave 0 is the only place the migration sequence advances and the only place the Phase 12 evidence contract is pinned.
Output: the evidence table migrated with CHECKs and triggers, the risk-model enum decision applied, 2 new test files + conftest fixtures + test_risk extensions, and the migration test coverage.

## Context

- @.planning/phases/12-risk-models-attribution/12-CONTEXT.md — locked decisions: append-only evidence contract, per-model PSD provenance, RSK-02's 4-model selection
- backend/app/operational/migrations.py — the `MIGRATIONS` tuple closes at L1618 (the Phase 11 `portfolio_optimization_runs` script is the last entry); `migrate_operational_db` applies atomically with `PRAGMA user_version`; the Phase 7 rebuild pattern (L632-720: `ALTER TABLE ... RENAME TO ..._legacy` → recreate → copy → drop legacy) is the template for the runs-table CHECK widening
- backend/app/portfolio/repository.py — `_RISK_MODELS = frozenset({"sample_covariance_v1"})` (L29) — the runs-table enum the checkpoint decision may widen
- backend/tests/test_operational_migrations.py — the Phase 11 runs-table test (L454-563: `_run_row` + CHECK/trigger/idempotence cases) — the pattern for the evidence-table cases
- backend/tests/portfolio/conftest.py — `fixture_returns` (6-obs) + `fixture_composite` — the fixtures to extend with a long-horizon series and an attributed run
- backend/tests/portfolio/test_risk.py — the Phase 11 scaffold (sample covariance + PSD) — extend with the 3 new-model cases

## Tasks

- **checkpoint:decision — Approve the `portfolio_risk_attribution_evidence` append-only table + risk-model enum (one-way door)**
  - Decision: Land the evidence table in `operational/migrations.py` as ONE new migration script appended to the `MIGRATIONS` tuple, and decide whether to widen the `portfolio_optimization_runs.risk_model` CHECK from 1 to the 4 risk-model values (a table rebuild).
  - Context: This is a one-way door: the migration advances `PRAGMA user_version` for every operational.db (research + forecast + jobs share the same database); undoing requires a follow-up migration, and Phases 13-14 build on this audit contract. The evidence table is MANDATED by the append-only contract (every attribution analysis is an immutable fact bound to a checksum-verified artifact). The runs-table CHECK widening is the second door: RSK-02 requires "select among sample, semi-covariance, exponentially weighted, Ledoit-Wolf risk models" — the evidence rows carry the 4-model enum regardless, but recording a non-sample risk model ON THE RUN itself (the Phase 13 per-fold optimization seam) requires the widened CHECK. SQLite cannot ALTER a CHECK — the widening is a table rebuild (rename → recreate → copy → drop, preserving rows/triggers/index), following the Phase 7 rebuild pattern.
  - Options:
    - option-a: Evidence table per the schema below AND rebuild `portfolio_optimization_runs` with `risk_model CHECK (risk_model IN ('sample_covariance_v1','semi_covariance_v1','ewma_covariance_v1','ledoit_wolf_v1'))` — same columns/constraints/triggers/index, rows copied. Pros: run-level risk-model selection is fully supported (RSK-02 selection recorded on the run; Phase 13 re-runs optimization under alternate risk models and records them); one migration script covers both doors. Cons: the rebuild is one more one-way migration (Phase 11 rows must survive; test coverage must prove it).
    - option-b: Evidence table only; the runs-table CHECK stays `sample_covariance_v1`; risk-model selection lives at the attribution layer (evidence rows carry the 4-model enum). Pros: no rebuild; smaller migration. Cons: `run_optimization` cannot record a non-sample risk model on the run row; Phase 13 walk-forward must recompute covariance outside run records; the runs table's risk_model stays a single value while the product surface says "select among risk models".
  - Evidence-table schema (both options): `portfolio_risk_attribution_evidence` (id TEXT PK, attribution_type TEXT NOT NULL CHECK IN ('exposure_contribution','drawdown'), run_id TEXT NOT NULL REFERENCES portfolio_optimization_runs(id) ON DELETE RESTRICT, risk_model TEXT NOT NULL CHECK IN ('sample_covariance_v1','semi_covariance_v1','ewma_covariance_v1','ledoit_wolf_v1'), as_of TEXT NOT NULL, output_sha256 TEXT NOT NULL CHECK (length(output_sha256) = 64), artifact_relative_path TEXT NOT NULL, reconciliation_json TEXT NOT NULL, created_at TEXT NOT NULL, CHECK ((attribution_type = 'exposure_contribution') = (reconciliation_json IS NOT NULL))); index `idx_attribution_evidence_run ON (run_id, attribution_type)`; `no_update`/`no_delete` triggers (the Phase 10/11 convention).
  - Resume signal: Select: option-a or option-b

- **build: Append the evidence migration (+ runs-table CHECK widening per the approved option) + extend migration tests**
  - Files: backend/app/operational/migrations.py, backend/tests/test_operational_migrations.py
  - Read first: backend/app/operational/migrations.py (the last MIGRATIONS entry L1583-1618 — the Phase 11 runs table + triggers style; the tuple closes at L1618), the Phase 7 rebuild pattern (L632-720), backend/tests/test_operational_migrations.py (L454-563 — the Phase 11 runs-table test conventions)
  - Action: Append ONE new SQL script to the `MIGRATIONS` tuple: (1) create `portfolio_risk_attribution_evidence` per the approved schema (attribution_type/risk_model CHECK enums, run_id FK ON DELETE RESTRICT, output_sha256 64-hex CHECK, the reconciliation invariant CHECK, the (run_id, attribution_type) index, no_update/no_delete triggers); (2) per the approved option — option-a: rebuild `portfolio_optimization_runs` (drop the old triggers, `ALTER TABLE ... RENAME TO ..._legacy`, recreate with the identical DDL but the widened `risk_model` CHECK, `INSERT INTO ... SELECT` copying every column, drop the legacy table, recreate index + triggers) following the Phase 7 rebuild pattern exactly; option-b: no runs-table change. Extend `tests/test_operational_migrations.py`: (a) forward-only idempotence — table absent before the Phase 12 script, present after, `PRAGMA user_version` advances exactly once and a second migrate is a no-op; (b) evidence CHECKs — invalid attribution_type / risk_model / short output_sha256 / reconciliation-invariant violations each raise `sqlite3.IntegrityError`; (c) triggers block UPDATE/DELETE; (d) FK — an evidence row referencing a missing run_id raises; (e) option-a: the rebuild preserves an inserted Phase 11 run row verbatim (SELECT back the row, check the columns) and the widened CHECK accepts a `semi_covariance_v1` row while still rejecting `shrinkage_v1`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short`
  - Done: `portfolio_risk_attribution_evidence` migrates with the enum/sha256/reconciliation CHECKs and triggers; the runs-table risk_model CHECK accepts the 4 models when option-a is approved (Phase 11 rows survive the rebuild); the migration test proves constraints and forward-only idempotence.

- **test: Scaffold the new test files + extend fixtures (Wave 0 gaps)**
  - Files: backend/tests/portfolio/conftest.py, backend/tests/portfolio/test_attribution.py, backend/tests/portfolio/test_drawdown.py, backend/tests/portfolio/test_risk.py
  - Read first: backend/tests/portfolio/conftest.py (existing fixtures), backend/tests/portfolio/test_risk.py (existing scaffold style), backend/tests/research/conftest.py (the fixture-pattern home)
  - Action: Extend `tests/portfolio/conftest.py`: `fixture_returns_long` — a deterministic 24-obs × 4-symbol returns matrix (seeded rng) including a CONSTRUCTED drawdown segment (e.g. obs 8-11: returns that produce a −5% then −4% portfolio dip before recovery) so 12-06's period detection has a known target; `fixture_attribution_run` — records a min-vol run via `run_optimization` on the existing `fixture_composite` (fixture_mode=True) and returns the run dict. Create `tests/portfolio/test_attribution.py` (RED scaffold): portfolio_variance == wᵀΣw reference; sum(MC) == variance; evidence-row shape. Create `tests/portfolio/test_drawdown.py` (RED scaffold): underwater-curve reference; empty-period identity; period boundaries on the constructed segment. Extend `tests/portfolio/test_risk.py` with the 3 new-model RED cases: `semi_covariance` below-mean subset reference, `ewma_covariance` λ=1.0 → sample + λ=0.94 hand recursion, `ledoit_wolf_covariance` PSD + shrinkage range + the lazy-import subprocess gate (assert `"sklearn" not in sys.modules` after importing `app.portfolio.risk`).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short` — expected failures (RED) until 12-01/12-03 land
  - Done: `test_attribution.py` + `test_drawdown.py` exist with the Phase 12 cases; `test_risk.py` carries the 3 new-model cases; conftest provides `fixture_returns_long` + `fixture_attribution_run`; the scaffolds are provably RED (failing on the missing modules/functions) — the exact tests 12-01/12-03/12-04/12-06 turn green.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short
cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short   # expected RED (scaffolds) until 12-01/12-03
```

The evidence table migrates with its constraints and triggers; the 2 new test files are scaffolded RED with shared fixtures.

## Success Criteria

- `portfolio_risk_attribution_evidence` migrates atomically with the attribution_type/risk_model enums, sha256 + reconciliation CHECKs, FK, and immutability triggers; the runs-table CHECK is widened per the approved one-way-door option (Phase 11 rows preserved under option-a).
- The 2 new test files are scaffolded RED with `fixture_returns_long` + `fixture_attribution_run`; `test_risk.py` carries the 3 new-model cases.

---

# Plan 12-03 — Risk-Model Suite Breadth (RSK-02)

**wave:** 2 · **depends_on:** [12-01] · **autonomous:** true
**requirements:** [RSK-02]
**files_modified:**
- backend/app/portfolio/risk.py (extend — 3 models + make_risk_model_family)
- backend/app/portfolio/optimizer.py (extend — risk_model_name dispatch)
- backend/app/portfolio/schemas.py (extend — OptimizationRequest.risk_model)
- backend/tests/portfolio/test_risk.py (extend — green)
- backend/tests/portfolio/test_pipeline.py (extend — a run under each risk model)

## Objective

Harden the risk-model suite from the Phase 11 single sample-covariance path to the full RSK-02 surface: semi-covariance (downside co-movement, below-mean benchmark), exponentially weighted covariance (RiskMetrics λ=0.94), and Ledoit-Wolf shrinkage (scikit-learn 1.8.0 lazy-imported at the model boundary ONLY — never module-top, Phase 10 import-audit contract) — every model passing through the SAME check_psd + repair_psd + provenance discipline as sample covariance (never silent), exposed through a single `make_risk_model_family` dispatcher that `_build_risk_model` consumes (and Phase 13's per-fold covariance will reuse), with the selected model name recorded verbatim on the run row + risk_model_json.

Purpose: RSK-02 requires the 4-model suite with explicit PSD provenance; the tracer proved the sample-covariance path, this plan makes selection real and auditable end-to-end (covariance artifact checksum-bound per model).
Output: `semi_covariance` / `ewma_covariance` / `ledoit_wolf_covariance` / `make_risk_model_family`, the `_build_risk_model` dispatch, `OptimizationRequest.risk_model`, and green `test_risk.py` + `test_pipeline.py` breadth.

## Context

- @.planning/phases/12-risk-models-attribution/12-CONTEXT.md — locked decisions: semi/EWMA/Ledoit-Wolf added to `portfolio/risk.py`; sklearn lazy-import; every model's PSD repair records provenance; `risk_model_json` seam continues
- @.planning/phases/12-risk-models-attribution/12-CONTEXT.md `## Specific Ideas` — EWMA `Σ_t = λΣ_{t−1} + (1−λ)r_t r_tᵀ` with λ=0.94 (RiskMetrics standard); semi-covariance = covariance of below-mean return co-movement (PyPortfolioOpt `risk_models.semicovariance` contract as reference); Ledoit-Wolf via `sklearn.covariance.LedoitWolf`
- backend/app/portfolio/risk.py — `sample_covariance` / `check_psd` / `repair_psd` / `covariance_sha256` (the provenance discipline + canonical hashing every model inherits)
- backend/app/portfolio/optimizer.py — `_build_risk_model` (L415-442: builds sample covariance → PSD gate → risk_model_json with risk_model/window/dropna/psd_repair/covariance_sha256) — the seam to dispatch
- backend/app/portfolio/schemas.py — `OptimizationRequest` (the frozen DTO to extend with `risk_model`)
- backend/pyproject.toml — `shadow = ["scikit-learn==1.8.0"]` extra (the lazy-import floor; never a base dep)
- backend/tests/portfolio/test_risk.py / test_pipeline.py — the scaffolds to turn green

## Tasks

- **build: Extend `portfolio/risk.py` — semi / EWMA / Ledoit-Wolf + make_risk_model_family**
  - Files: backend/app/portfolio/risk.py
  - Read first: 12-CONTEXT.md `## Specific Ideas` (formulas + defaults), backend/app/portfolio/risk.py (the existing sample_covariance / check_psd / repair_psd / covariance_sha256), PyPortfolioOpt `risk_models.semicovariance` contract (DESIGN SPEC ONLY — never a runtime dependency)
  - Action: Implement `semi_covariance(returns: np.ndarray, *, benchmark: str = "mean") -> np.ndarray` — restrict to rows where the asset return is below the benchmark (benchmark `"mean"` = row-wise mean, `"zero"` = 0.0), compute the covariance of the below-benchmark subset (common finite window), normalize by the subset observation count (the PyPortfolioOpt contract as design spec; documented in the docstring); a degenerate subset (fewer observations than assets) still returns a finite covariance (the PSD gate downstream handles near-degeneracy with recorded provenance). Implement `ewma_covariance(returns: np.ndarray, *, lam: float = 0.94, adjust: bool = True) -> np.ndarray` — recursive `Σ_t = lam * Σ_{t−1} + (1 − lam) * outer(r_t, r_t)` with `adjust=True` normalization `1 / (1 − lam^t)` (the standard EWMA; λ=0.94 RiskMetrics default; `lam=1.0` must recover the sample covariance on demeaned data — a documented test contract). Implement `ledoit_wolf_covariance(returns: np.ndarray, *, block_size: int | None = None) -> tuple[np.ndarray, dict]` — `from sklearn.covariance import LedoitWolf` INSIDE the function body (Phase 10 lazy-import contract — never module-top; a subprocess gate enforces it), fit on the common finite window, return `(model.covariance_, {"shrinkage": float(model.shrinkage_), "sklearn_version": str})`. Add the public dispatcher `make_risk_model_family(returns: np.ndarray, *, risk_model_name: str, window: tuple[str, str], epsilon: float = PSD_EPSILON_DEFAULT) -> dict` — dispatch across the 4 builders (`sample_covariance_v1` | `semi_covariance_v1` | `ewma_covariance_v1` | `ledoit_wolf_v1`; unknown → ValueError), then for EVERY model run the SAME check_psd → repair_psd (eigen_clip, never silent) → provenance path as `_build_risk_model` today, and return `{"covariance", "risk_model_json"}` with `risk_model` = the selected name, model params (benchmark/lam/shrinkage) recorded, `window`, `dropna: True`, `psd_repair` provenance (method/epsilon/eigenvalues before/after — method "none" when no repair), `covariance_sha256`. This is the Phase 13 per-fold covariance seam.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_risk.py -q --tb=short`
  - Done: semi matches the manual below-mean `np.cov` reference on a fixture; EWMA λ=1.0 recovers the sample covariance and λ=0.94 matches a hand-computed 2-step recursion; Ledoit-Wolf returns a PSD matrix with shrinkage ∈ (0, 1]; all four models record full PSD provenance; `import app.portfolio.risk` leaves `"sklearn" not in sys.modules` (subprocess gate).

- **build: Extend `optimizer.py` + `schemas.py` — risk_model_name dispatch + selection recorded**
  - Files: backend/app/portfolio/optimizer.py, backend/app/portfolio/schemas.py
  - Read first: backend/app/portfolio/optimizer.py `_build_risk_model` (L415-442) + the three `risk_model="sample_covariance_v1"` record sites (L768, L862, and the HRP branch), backend/app/portfolio/schemas.py `OptimizationRequest`
  - Action: Add `risk_model: Literal["sample_covariance_v1", "semi_covariance_v1", "ewma_covariance_v1", "ledoit_wolf_v1"] = "sample_covariance_v1"` to `OptimizationRequest` (sample remains the default — RSK-02 selection is explicit, never accidental). Refactor `_build_risk_model(returns, *, window, epsilon, risk_model_name: str = "sample_covariance_v1")` to delegate to `make_risk_model_family` (identical output shape for sample — the existing tests keep passing). Thread `req.risk_model` through `_run_optimization_impl` into `_build_risk_model` and record the selected name in the runs row (`risk_model=req.risk_model`) + `risk_model_json["risk_model"]` (both sites: the HRP branch and the min-vol/max-sharpe branch). The `ensure_psd_provenance` gate still runs on the selected covariance before ANY solve (never silent — a semi/EWMA/LW covariance that needed repair must carry provenance like sample). Under option-b (runs CHECK not widened) a non-sample risk_model fails closed at the repository layer — leave the orchestrator's contract intact either way (the 12-02 decision settles which).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py -q --tb=short`
  - Done: `run_optimization(risk_model="semi_covariance_v1")` records the selected name on the run row + risk_model_json with model params; the PSD gate runs identically for all four; the covariance artifact is checksum-bound for every model; sample remains the default.

- **test: Turn the `test_risk.py` new-model cases green + lazy-import gate**
  - Files: backend/tests/portfolio/test_risk.py
  - Read first: backend/tests/portfolio/test_risk.py (the 12-02 RED cases), backend/app/portfolio/risk.py (module under test)
  - Action: Make the scaffolded cases pass: (1) `semi_covariance` below-mean matches the manual subset `np.cov` reference and `benchmark="zero"` uses the below-zero subset; (2) `ewma_covariance(lam=1.0)` recovers the sample covariance on demeaned data, `lam=0.94` matches the hand-computed 2-step recursion (start `Σ_1 = outer(r_1, r_1)`, recurse); (3) `ledoit_wolf_covariance` returns a PSD matrix (`eigvalsh(...).min() >= -1e-9`), `shrinkage` in (0, 1], and `sklearn_version` non-empty; (4) `make_risk_model_family` returns `{"covariance", "risk_model_json"}` for all 4 names with `risk_model` = the name and full `psd_repair` provenance (method in ("none", "eigen_clip"), eigenvalues before/after); an unknown name raises `ValueError`; (5) the lazy-import gate — a subprocess `python -c "import sys; import app.portfolio.risk; assert 'sklearn' not in sys.modules"` passes and the Ledoit-Wolf call imports it lazily inside the function.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_risk.py -q --tb=short`
  - Done: the three model contracts, per-model provenance, family dispatch, and the sklearn lazy-import gate are locked by green tests.

- **test: Extend `test_pipeline.py` — a run under each risk model**
  - Files: backend/tests/portfolio/test_pipeline.py
  - Read first: backend/tests/portfolio/test_pipeline.py (the existing Phase 11 + tracer tests), backend/app/portfolio/optimizer.py (run_optimization)
  - Action: Add a parameterized test over the 4 risk models: `run_optimization({... "risk_model": model, ...}, fixture_mode=True)` on the fixture composite → the run row's `risk_model == model`, `risk_model_detail["risk_model"] == model`, model params recorded (benchmark/lam/shrinkage as applicable), `risk_model_detail["psd_repair"]["method"]` in ("none", "eigen_clip"), `covariance_sha256` 64-hex, and the covariance artifact checksum-verifies against the digest (existing read_artifact seam); weights stay feasible (`sum <= 1 - min_cash`); the default request still records `sample_covariance_v1`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py -q --tb=short`
  - Done: all four risk models produce auditable, checksum-bound runs; selection is explicit and recorded verbatim on the run.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_risk.py tests/portfolio/test_pipeline.py -q --tb=short
```

All green. Grep gate: `from sklearn` / `import sklearn` appears ONLY inside `risk.py` function bodies (never module-top; `grep -n "sklearn" backend/app --include=*.py` matches only `risk.py`, and the import line is indented); `make_risk_model_family` is the only covariance-dispatch entry the optimizer calls.

## Success Criteria

- The 4-model suite ships with per-model PSD provenance (never silent); sklearn is lazy-imported at the model boundary only.
- `risk_model` selection is explicit, recorded on the run row + risk_model_json, and every model's covariance artifact is checksum-bound.
- `make_risk_model_family` is the shared dispatcher Phase 13's per-fold covariance reuses.

---

# Plan 12-04 — Attribution Breadth (RSK-01)

**wave:** 2 · **depends_on:** [12-01] · **autonomous:** true
**requirements:** [RSK-01]
**files_modified:**
- backend/app/portfolio/attribution.py (extend)
- backend/app/portfolio/analyzer.py (extend)
- backend/tests/portfolio/test_attribution.py (extend — green)

## Objective

Harden the attribution layer from the tracer's single-path proof to the full RSK-01 surface: signed variance components (negative marginal contribution = diversifier — never abs()ed, so the sum identity is preserved), the complete per-instrument contribution + summary report (portfolio variance, top contributors, diversifiers, instrument count), and the evidence invariants locked by green tests — including the negative-MC fixture proving the reconciliation holds exactly even when an instrument contributes negatively, and the tamper fail-closed path (a covariance artifact whose bytes were modified raises and writes NO evidence row).

Purpose: RSK-01's cross-module integrity check is only real when the report is complete and the assertion survives edge cases (negative contributions, tampered covariance bytes).
Output: `attribution_report`, the full exposure/contribution artifact payload, and green `test_attribution.py` breadth.

## Context

- @.planning/phases/12-risk-models-attribution/12-CONTEXT.md — locked decisions: exposure = weight · covariance; MC contributing to portfolio variance; hard reconciliation; per-instrument contribution + summary
- backend/app/portfolio/attribution.py (from 12-01) — `portfolio_variance` / `portfolio_exposure` / `marginal_contributions` / `reconcile_attribution`
- backend/app/portfolio/analyzer.py (from 12-01) — `run_attribution` (extend the artifact payload)
- backend/app/portfolio/artifacts.py — `read_artifact` (the tamper path the tests drive)
- backend/tests/portfolio/test_attribution.py (from 12-02 RED scaffold) — extend to green

## Tasks

- **build: Variance-signed components + the summary report**
  - Files: backend/app/portfolio/attribution.py
  - Read first: 12-CONTEXT.md `## Exposure & Contribution Attribution` (per-instrument contribution + summary), backend/app/portfolio/attribution.py (from 12-01)
  - Action: Add `attribution_report(weights: np.ndarray, symbols: list[str], cov: np.ndarray) -> dict` — computes variance + signed exposure + MC via the existing functions, then returns the full report: `{"portfolio_variance", "exposure": {symbol: value} (SIGNED — negative = diversifier, never abs()ed), "marginal_contributions": {symbol: value}, "sum_contributions", "reconciliation_error", "summary": {"instrument_count", "top_contributors": [symbols sorted by |MC| desc, top 5], "diversifiers": [symbols with MC < 0], "policy_version": "phase-12-attribution-v1"}}`. Document in the module docstring: exposure and marginal contribution share the formula `w_i · (Σw)_i` per CONTEXT; the labels are semantic (exposure = signed risk footprint, MC = the variance decomposition) — the sum identity `Σ MC_i == wᵀΣw` holds because neither is transformed. Extend `reconcile_attribution` to accept symbols and return the full report shape (backward-compatible with the 12-01 tracer calls).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py -q --tb=short`
  - Done: the report keeps signed components; `sum(MC) == variance` holds on a fixture with a negative-MC diversifier; the summary block (top contributors, diversifiers, instrument count, policy version) is present.

- **build: Extend `run_attribution` — full report payload + evidence breadth**
  - Files: backend/app/portfolio/analyzer.py
  - Read first: backend/app/portfolio/analyzer.py (from 12-01 — the checksum-bound covariance load), backend/app/portfolio/attribution.py (the report shape)
  - Action: Extend `run_attribution` so the `exposure_contribution.json` artifact payload carries the FULL report (weights, exposure, marginal_contributions, portfolio_variance, reconciliation, summary) — the evidence row stays compact: `reconciliation_json = {"portfolio_variance", "sum_contributions", "max_abs_error"}`. The checksum-bound covariance load, the hard reconciliation (aborts before any write on failure), and the no-evidence-row-on-failure contract from 12-01 are unchanged. A missing run or a covariance-artifact checksum mismatch raises (never a silent recompute, never an empty evidence row).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py -q --tb=short`
  - Done: the attribution artifact carries the complete report; evidence rows are append-only per (run, model) analysis; failures raise without writing evidence.

- **test: Turn `test_attribution.py` green — exact reconciliation, negative MC, evidence invariants**
  - Files: backend/tests/portfolio/test_attribution.py
  - Read first: backend/tests/portfolio/test_attribution.py (the 12-02 RED scaffold), backend/app/portfolio/attribution.py + analyzer.py (modules under test)
  - Action: Make the scaffolded cases pass and add: (1) reconciliation EXACT — on a fixture run, `sum(MC) == wᵀΣw` to rtol 1e-12 on the ROUND-8 covariance artifact matrix (cross-module: the SAME bytes the run recorded — read via `read_artifact` with the recorded digest); (2) negative-MC fixture — a diversifier with negative covariance to the portfolio produces a negative contribution and the identity still holds (the hard assertion does not abs); (3) exposure == MC numerically per symbol (the documented semantic distinction — same product vector); (4) evidence invariants — `exposure_contribution` requires `reconciliation_json`, `output_sha256` 64-hex, run_id FK to an existing run; (5) tamper fail-closed — flip a byte in the covariance artifact file, `run_attribution` raises `ArtifactReadError` and records NO evidence row; (6) the summary block (top_contributors by |MC|, diversifiers, policy_version) is populated on a 4-symbol fixture.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py -q --tb=short`
  - Done: the RSK-01 attribution contract — exact reconciliation on the run's own covariance bytes, signed components, summary, evidence invariants, tamper fail-closed — is locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py -q --tb=short
```

All green. Grep gate: `np.abs(` / `.abs()` never wraps the marginal-contribution or exposure vectors in `attribution.py` (the sum identity depends on signed components).

## Success Criteria

- The attribution report is complete (variance, signed exposure, MC, summary) and the reconciliation is exact on the run's checksum-bound covariance bytes.
- Negative contributions are honest (diversifiers), never abs()ed; the sum identity holds for them too.
- Tampered covariance bytes fail the analysis closed with no evidence row; evidence invariants are locked by tests.

---

# Plan 12-05 — Cross-Model Attribution + Reconciliation Breadth (RSK-01/02)

**wave:** 3 · **depends_on:** [12-03, 12-04] · **autonomous:** true
**requirements:** [RSK-01, RSK-02]
**files_modified:**
- backend/app/portfolio/analyzer.py (extend — risk_model selection + reconcile_all_models)
- backend/app/portfolio/risk.py (extend — load_covariance_artifact helper)
- backend/app/portfolio/repository.py (extend — list_attribution_evidence risk_model filter)
- backend/tests/portfolio/test_attribution.py (extend)
- backend/tests/portfolio/test_repository.py (extend)

## Objective

Close the two integrity gaps RSK-01/02 share: attribution under ALL FOUR risk models with the EXACT reconciliation asserted per model (the cross-model matrix: model × variance × sum(MC) × max abs error, internally consistent), and the Phase 15 evidence-list API surface (`list_attribution_evidence` by run/type/risk_model with the limit cap). The identity path stays checksum-bound — `run_attribution` with no model selection consumes ONLY the run's recorded covariance artifact; a model selection recomputes that model's covariance from the run's returns through `make_risk_model_family` + the same PSD gate, then reconciles exactly on it.

Purpose: RSK-01's "reconciles to portfolio variance" must hold for whichever of the four RSK-02 models the researcher selects — the cross-module integrity check is per-model, not just for sample covariance.
Output: model-selectable `run_attribution`, `reconcile_all_models`, the `load_covariance_artifact` helper, `list_attribution_evidence` breadth, and green cross-model tests.

## Context

- @.planning/phases/12-risk-models-attribution/12-CONTEXT.md — locked decisions: attribution reads immutable run records; every risk model's PSD repair records provenance; RSK-01 reconciliation is a hard assertion
- backend/app/portfolio/analyzer.py (from 12-01/12-04) — `run_attribution` (the checksum-bound identity path to extend)
- backend/app/portfolio/risk.py (from 12-03) — `make_risk_model_family` (the recompute path for model selection)
- backend/app/portfolio/repository.py (from 12-01) — `list_attribution_evidence` (extend the filter surface)
- backend/tests/portfolio/test_attribution.py / test_repository.py — extend

## Tasks

- **build: `run_attribution` risk-model selection + `reconcile_all_models` + `load_covariance_artifact`**
  - Files: backend/app/portfolio/analyzer.py, backend/app/portfolio/risk.py
  - Read first: backend/app/portfolio/analyzer.py (from 12-01/12-04), backend/app/portfolio/risk.py `make_risk_model_family` (from 12-03), backend/app/portfolio/artifacts.py `read_artifact`
  - Action: In `risk.py`, add `load_covariance_artifact(run: dict, artifact_service_root: Path) -> np.ndarray` — reads `run["risk_model_detail"]["covariance_artifact_relative_path"]` via `read_artifact(..., checksum_sha256=run["risk_model_detail"]["covariance_sha256"])` and `json.loads` to an (n, n) array; the ONLY covariance source for the identity path (raises `ArtifactReadError` on mismatch/absence). In `analyzer.py`, extend `run_attribution(run_id, *, repository, artifact_service_root, returns: np.ndarray | None = None, risk_model_name: str | None = None)` — when `risk_model_name is None` use `load_covariance_artifact` (identity, checksum-bound); when a name is given (and `returns` provided), recompute that model's covariance via `make_risk_model_family(returns, risk_model_name=..., window=(as_of, as_of))`, run the same `ensure_psd_provenance` gate, and reconcile EXACTLY on that covariance; the evidence row records the selected `risk_model` (4-model CHECK). Add `reconcile_all_models(run_id, *, returns, repository, artifact_service_root) -> dict` — runs the identity path + the 3 recompute paths and returns the cross-model matrix `{"models": {name: {"portfolio_variance", "sum_contributions", "max_abs_error"}}, "all_reconciled": bool}`; every model's `max_abs_error <= 1e-12 * variance` (the hard assertion per model; any failure raises before any evidence write).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py -q --tb=short`
  - Done: attribution runs under any of the 4 models with the exact reconciliation; the identity path stays checksum-bound (never recomputes sample covariance); `reconcile_all_models` reports the per-model matrix and aborts on any reconciliation failure; evidence rows per model are distinct append-only records.

- **build: `list_attribution_evidence` breadth (Phase 15 API)**
  - Files: backend/app/portfolio/repository.py
  - Read first: backend/app/portfolio/repository.py `list_attribution_evidence` (from 12-01)
  - Action: Extend `list_attribution_evidence(*, run_id=None, attribution_type=None, risk_model=None, limit=200)` with a `risk_model` equality filter and the same positive-int `limit` fail-closed as `list_optimization_runs`; ORDER BY `created_at, id`; JSON columns un-wrapped via the existing `_record`-style mapping.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_repository.py -q --tb=short`
  - Done: the evidence list API filters by run_id / attribution_type / risk_model and caps at limit.

- **test: Cross-model matrix + hard reconciliation per model + evidence filters**
  - Files: backend/tests/portfolio/test_attribution.py, backend/tests/portfolio/test_repository.py
  - Read first: backend/tests/portfolio/test_attribution.py (existing green cases), the modules under test
  - Action: Add to `test_attribution.py`: (1) for each of the 4 models on a fixture run — variance ≥ 0, `sum(MC) == variance` to rtol 1e-12, the evidence row carries the selected risk_model + a checksum-verified artifact; (2) `reconcile_all_models` returns all 4 rows with `all_reconciled == True` and the matrix is internally consistent (identity row matches the run's recorded digest path); (3) a run whose covariance artifact bytes were tampered fails the identity path closed (no evidence row) while the model-selection path (recompute from returns) still reconciles; (4) `list_attribution_evidence(risk_model="semi_covariance_v1")` returns only semi rows. Add to `test_repository.py`: the risk_model filter + limit fail-closed (limit=0 raises ValueError).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py tests/portfolio/test_repository.py -q --tb=short`
  - Done: the cross-model reconciliation contract — exact per model, checksum-bound identity path, tamper fail-closed, evidence-list filters — is locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py tests/portfolio/test_repository.py -q --tb=short
```

All green. Grep gate: `np.cov(` appears nowhere in `analyzer.py` (covariance comes only from `load_covariance_artifact` or `make_risk_model_family`).

## Success Criteria

- `run_attribution` reconciles EXACTLY under all four risk models; `reconcile_all_models` is the cross-model integrity report.
- The identity path is checksum-bound; tampered covariance bytes fail closed with no evidence row.
- `list_attribution_evidence` supports the Phase 15 API surface (run/type/risk_model filters + limit).

---

# Plan 12-06 — Drawdown Attribution Breadth (RSK-03)

**wave:** 4 · **depends_on:** [12-04] · **autonomous:** true
**requirements:** [RSK-03]
**files_modified:**
- backend/app/portfolio/drawdown.py (extend — per-instrument × per-segment attribution)
- backend/app/portfolio/analyzer.py (extend — run_drawdown full report)
- backend/tests/portfolio/test_drawdown.py (extend — green)

## Objective

Harden the drawdown layer from the tracer's identity path to the full RSK-03 surface: per-instrument × per-time-segment decomposition — each identified drawdown period carries the per-instrument contribution table `c_i = Σ_{t in period} w_i · r_{i,t}`, with the segment reconciliation identity `Σ_i c_i == segment cumulative portfolio return` asserted exactly (rtol 1e-10 — linear decomposition, exact in arithmetic), plus the summary (max depth, longest period, recovery) and the append-only evidence row.

Purpose: RSK-03 requires drawdown attribution decomposed by instrument AND time segment — the segment-level identity is this plan's hard integrity check (symmetric with RSK-01's variance reconciliation).
Output: `drawdown_attribution`, the full `run_drawdown` report + evidence, and green `test_drawdown.py` breadth.

## Context

- @.planning/phases/12-risk-models-attribution/12-CONTEXT.md — locked decisions: underwater curve → periods → per-instrument contribution table; thresholds are documented discretion
- backend/app/portfolio/drawdown.py (from 12-01) — `underwater_curve` / `drawdown_periods` + the depth/min-obs constants
- backend/app/portfolio/analyzer.py (from 12-01) — `run_drawdown` (extend to the full report)
- backend/app/portfolio/attribution.py (from 12-01/12-04) — the reconciliation-assertion pattern the segment identity mirrors
- backend/tests/portfolio/test_drawdown.py (from 12-02 RED scaffold) + conftest `fixture_returns_long` (the constructed drawdown segment)

## Tasks

- **build: Per-instrument × per-segment drawdown attribution**
  - Files: backend/app/portfolio/drawdown.py
  - Read first: 12-CONTEXT.md `## Drawdown Attribution`, backend/app/portfolio/drawdown.py (from 12-01), backend/app/portfolio/attribution.py `reconcile_attribution` (the hard-assertion pattern)
  - Action: Implement `drawdown_attribution(weights: np.ndarray, returns: np.ndarray, periods: list[dict]) -> dict` — for each period `{start_idx, end_idx, depth}`: per-instrument contribution `c_i = Σ_{t in [start,end]} w_i · r_{i,t}`, segment return `= Σ_t Σ_i w_i r_{i,t}`, and the HARD assertion `np.testing.assert_allclose(np.sum(c), segment_return, rtol=1e-10, atol=1e-15)` (linear decomposition — exact in arithmetic, never approximate); returns `{"periods": [{start_idx, end_idx, depth, segment_return, contributions: {symbol: value}}], "max_depth": float, "longest_period": int (obs), "segment_reconciliation_max_abs_error": float}`. Document in the module docstring: contributions are arithmetic (non-compounded) by design — the identity `Σ c_i == segment return` is exact because both are the same double sum; compounding effects are out of scope (documented, not hidden).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_drawdown.py -q --tb=short`
  - Done: per-segment contributions sum exactly to the segment return (rtol 1e-10); the period boundaries match the constructed fixture drawdown; the depth/min-obs thresholds are respected (a sub-threshold dip is not flagged).

- **build: Extend `run_drawdown` — full report + evidence**
  - Files: backend/app/portfolio/analyzer.py
  - Read first: backend/app/portfolio/analyzer.py (from 12-01 — the identity path), backend/app/portfolio/drawdown.py (the new attribution function)
  - Action: Extend `run_drawdown(run_id, *, returns: np.ndarray, repository, artifact_service_root) -> dict` — load the run's output weights (`run["output_weights"]`, aligned to `returns` columns/symbols order), compute portfolio returns `= weights @ returns.T`, `underwater_curve` + `drawdown_periods` + `drawdown_attribution(weights, returns, periods)` (empty periods → `{"periods": [], "max_depth": 0.0, "longest_period": 0, "segment_reconciliation_max_abs_error": 0.0}` — the identity is vacuous), write `attribution/drawdown.json` with the FULL report, record evidence `attribution_type="drawdown"` with `reconciliation_json = {"period_count", "max_depth", "longest_period", "segment_max_abs_error"}`. Non-finite returns or a missing run raise ValueError (no evidence row). The engine remains reference-only — `run_drawdown` never calls `simulate_portfolio`; a caller supplying a simulated equity-derived returns series (the Phase 15 panel seam) is a caller concern.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_drawdown.py -q --tb=short`
  - Done: drawdown attribution is an auditable analysis with a per-instrument × per-segment report and an append-only evidence row; the segment identity is asserted before any write.

- **test: Turn `test_drawdown.py` green — constructed drawdown, identity, thresholds**
  - Files: backend/tests/portfolio/test_drawdown.py
  - Read first: backend/tests/portfolio/test_drawdown.py (the 12-02 RED scaffold), conftest `fixture_returns_long`, backend/app/portfolio/drawdown.py + analyzer.py (modules under test)
  - Action: Make the scaffolded cases pass and add: (1) the underwater curve matches the `cumprod` reference on a fixture portfolio-returns series; (2) `drawdown_periods` finds exactly the CONSTRUCTED segment in `fixture_returns_long` with the expected `{start_idx, end_idx, depth}`; (3) the segment identity — per-instrument contributions sum to the segment return to rtol 1e-10 (hard); (4) thresholds — a −1% dip below the 2% depth threshold is NOT flagged; a flat series → no periods; (5) the end-to-end `run_drawdown` on a fixture run (weights from the run row + `fixture_returns_long`) writes the `drawdown.json` artifact (checksum-verified read-back) + the evidence row with `attribution_type="drawdown"` and the reconciliation payload; (6) a second `run_drawdown` writes a second append-only evidence row.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_drawdown.py -q --tb=short`
  - Done: the RSK-03 drawdown-attribution contract — instrument × time-segment decomposition with the segment reconciliation identity, thresholds, and append-only evidence — is locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_drawdown.py -q --tb=short
```

All green. Grep gate: `simulate_portfolio` appears nowhere in `portfolio/` (the engine is reference-only); the depth/min-obs thresholds are the module constants (no literal magic numbers in analyzer.py).

## Success Criteria

- Drawdown attribution decomposes by instrument AND time segment with the exact segment identity (Σ contributions == segment return).
- Thresholds are documented module constants recorded in the evidence; the report includes max depth and longest period.
- Every analysis is an append-only evidence row bound to a checksum-verified artifact; no execution routes.

---

# Consolidated Threat Model

> `workflow.security_enforcement: true` (config.json) — section required. Trust model: local single-user research host; no new auth/session surface (ASVS V2/V3 N/A). New records are server-issued only (V4 minimal). Pydantic strict DTOs + enum validation (V5); SHA-256 checksums for covariance artifacts, analysis artifacts, and evidence rows (V6).

## Trust Boundaries

| Boundary | Description |
|---|---|
| Phase 11 run record → attribution | The run's covariance crosses as FROZEN artifact bytes; every read is checksum-verified against `risk_model_detail["covariance_sha256"]`; fail-closed on mismatch — never a recomputed live covariance. |
| Analyzer → evidence table | Analysis artifacts are O_EXCL + fsync + sha256 under the run's existing namespace; evidence rows are append-only with `output_sha256` binding the artifact bytes. |
| risk.py → sklearn | Ledoit-Wolf crosses the lazy-import boundary only — `from sklearn.covariance import LedoitWolf` inside the function; never module-top; pinned 1.8.0 shadow extra. |
| Reconciliation → evidence write | The exact sum identity (variance / segment return) is a hard assertion that ABORTS before any evidence write — an approximate or falsified reconciliation can never be recorded. |

## STRIDE / ASVS L1 Traceability

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|---|---|---|---|---|---|
| T-12-01 | Tampering | Silent PSD repair in the 3 new risk models | high | mitigate | `make_risk_model_family` runs check_psd → repair_psd → provenance (method/epsilon/eigenvalues before/after) for EVERY model — the single dispatcher path, never a silent clip (12-03). Test: test_risk provenance cases. |
| T-12-02 | Spoofing | Covariance substitution (attribution uses a different covariance than the run) | high | mitigate | Identity path loads the run's covariance ARTIFACT by checksum (`covariance_sha256` vs bytes, read_artifact fail-closed); a mismatch raises and writes NO evidence row (12-01/12-05). Test: test_attribution tamper case, test_pipeline tracer. |
| T-12-03 | Tampering | Attribution/drawdown artifact tampering after the fact | medium | mitigate | O_EXCL + fsync + sha256 analysis artifacts (`write_analysis_artifact` under the run namespace); evidence row `output_sha256` binds the bytes; checksum-verified reads (12-01). |
| T-12-04 | Tampering | Evidence-row rewrite / fabrication | high | mitigate | `portfolio_risk_attribution_evidence` append-only + `no_update`/`no_delete` triggers; attribution_type/risk_model enums + reconciliation invariant CHECK + run_id FK (12-02). Test: test_operational_migrations evidence cases, test_repository. |
| T-12-05 | Tampering | Reconciliation falsified as approximate | medium | mitigate | `reconcile_attribution` hard-asserts sum(MC) == variance (rtol 1e-12) and `drawdown_attribution` hard-asserts Σc_i == segment return (rtol 1e-10) BEFORE any write; assertion failure aborts the analysis (12-01/12-04/12-06). |
| T-12-06 | Tampering | sklearn supply chain / lazy-import violation | medium | mitigate | scikit-learn==1.8.0 pinned shadow extra (Phase 10 package-legitimacy + import-audit gate); subprocess gate asserts `"sklearn" not in sys.modules` after `import app.portfolio.risk` (12-03). |
| T-12-07 | Information Disclosure | Drawdown thresholds hiding real drawdowns | low | accept | depth/min-obs thresholds are module constants (2% / 2 obs) recorded in the evidence `reconciliation_json`; documented discretion (12-01/12-06). |
| T-12-SC | Tampering | Python package supply chain (sklearn) | low | accept | No new installs in Phase 12; scikit-learn already pinned + import-audited in Phase 10 (`[ASSUMED]` legacy approval). |

# Phase Verification

```bash
# Per-wave gates (from backend/)
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short                                          # wave 0
cd backend && .venv/bin/python -m pytest tests/portfolio -q --tb=short                                                             # wave 0 (expected RED scaffolds)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_pipeline.py tests/portfolio/test_attribution.py tests/portfolio/test_drawdown.py tests/portfolio/test_repository.py -q --tb=short  # wave 1 (tracer)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_risk.py tests/portfolio/test_pipeline.py -q --tb=short                # wave 2 (risk-model suite)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py -q --tb=short                                         # wave 2 (attribution breadth)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_attribution.py tests/portfolio/test_repository.py -q --tb=short       # wave 3 (cross-model)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_drawdown.py -q --tb=short                                             # wave 4 (drawdown breadth)

# Phase gate (before /gsd-verify-work)
cd backend && .venv/bin/python -m pytest -x
```

Cross-module integrity checks:
- Attribution covariance bytes == the run's covariance artifact verified by `risk_model_detail["covariance_sha256"]` (checksum) — never a recomputed live covariance (12-01/12-05 tests).
- `sum(marginal_contributions) == portfolio variance` to rtol 1e-12 for EVERY risk model — the hard cross-module reconciliation (12-01/12-04/12-05 tests).
- Per-segment drawdown contributions sum to the segment return to rtol 1e-10 (12-06 tests).
- Evidence row `output_sha256` == analysis artifact bytes; `run_id` FK → `portfolio_optimization_runs` (12-01 tests).
- Grep gate hygiene: `sklearn` imports appear only inside `risk.py` function bodies (never module-top); `np.cov(` / `simulate_portfolio` absent from `attribution.py` / `drawdown.py` / `analyzer.py`; negative greps use `grep -v '^#'` filtering where comments could self-invalidate.

# Phase Success Criteria

- All 6 plans complete with their per-plan gates green.
- The full backend suite is green before `/gsd-verify-work` (phase gate).
- Every locked decision in 12-CONTEXT.md is implemented (see Source Coverage Audit): exposure + marginal contribution attribution reconciling EXACTLY to portfolio variance (RSK-01), the 4-model risk suite with explicit PSD provenance and lazy-imported sklearn (RSK-02), drawdown attribution by instrument and time segment (RSK-03), checksum-bound covariance consumption of Phase 11 immutable run records, and append-only evidence rows — with zero execution authority anywhere.
- Deferred ideas from CONTEXT (walk-forward, RebalancePlan, frontend panels, Black-Litterman, ML expected returns) do NOT appear in any delivered artifact.

# Output

After each plan completes, create the matching summary at `.planning/phases/12-risk-models-attribution/12-{NN}-SUMMARY.md` documenting what landed, the evidence, and any deviations from this plan. The phase gate is the full backend suite green before `/gsd-verify-work`.
