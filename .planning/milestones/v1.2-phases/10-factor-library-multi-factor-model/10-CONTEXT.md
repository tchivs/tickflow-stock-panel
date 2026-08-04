# Phase 10: Factor Library & Multi-Factor Model - Context

**Gathered:** 2026-07-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 10 delivers the v1.2 milestone's foundations and shared backbone: factor **admission gates** that deterministically admit or reject candidate factors with immutable append-only verdicts, an **evaluation upgrade** exposing the full monthly evidence set (IC, RankIC, ICIR, monthly robustness, coverage), a **deterministic multi-factor composite model** (equal-weight or IC-weighted cross-sectional z-score, no ML), the **admitted-factor catalog** with summary storage and revision lineage, the **DSL partition-context contract** (every operator declares per-date/per-symbol/pointwise semantics; label fields denied; shifted-label leakage test as the gate), and the **shared factor signal chain** (`research/signal_chain.py`) that every downstream consumer — evaluation, models, walk-forward, expected returns, live as-of suggestions — uses identically.

It is the first phase of milestone v1.2 and must land the append-only audit contract and governed-data boundary that all later phases inherit. Everything downstream depends on the signal chain; admission gates MUST precede portfolio construction (unvalidated factors poison expected returns).

**In scope:** FACT-01, FACT-02, FACT-03, FACT-04, FACT-05, FACT-06.
**Out of scope:** portfolio optimization (Phase 11), risk models (Phase 12), walk-forward (Phase 13), RebalancePlan (Phase 14), frontend panels (Phase 15). No execution authority anywhere.

</domain>

<decisions>
## Implementation Decisions

### Admission Gates (FACT-01)
- Hard-threshold gating: fixed policy thresholds (train/val IC), deterministic, auditable — a rejection is as much a recorded verdict as an admission.
- Every verdict is an immutable append-only record with the candidate trail (source, evaluation evidence, gate results, reason).
- Train/val split is by date order (temporal), never random shuffle — random splits leak lookahead.
- Similarity dedup reuses the existing `discover_similar` Jaccard structural signature AND adds an IC-correlation check; both are part of the gate verdict.

### Evaluation Evidence & Storage (FACT-02, FACT-05)
- Evaluation reports expose the FULL monthly evidence set, not a scalar mean: IC, RankIC, ICIR, monthly robustness, coverage, with the monthly series retained in the evidence package.
- Summary storage only for factor values: coverage, finite counts, signature. Storing full factor value matrices is an anti-feature (rejected).
- Rebalance cadence is configurable (daily/weekly/monthly), reusing the existing `RebalanceCadence` literal.
- Coverage is defined as non-empty share (finite counts), consistent with summary storage.

### Multi-Factor Composite Model (FACT-03)
- Both equal-weight and IC-weighted cross-sectional z-score compositions supported; deterministic; no ML.
- Output is the composite z-score plus optional rank; the model is a first-class catalog record.
- Composite output is persisted immutably (with input snapshot signature) and consumed by Phase 11's optimizer by snapshot — not passed live across module boundaries.

### DSL Partition-Context Contract (FACT-04)
- Every DSL operator declares its partition semantics (per-date / per-symbol / pointwise) inside the compiler, alongside the existing `_FUNCTION_ARITY` table — not in a separate sidecar config.
- Label fields are denied in the allowlist (already the case — `ALLOWED_FIELDS` excludes label/date columns; this becomes an explicit contract check).
- A deterministic shifted-label leakage test is a hard gate: when the label is shifted by the forward-return horizon, IC must collapse to ~0; a DSL change that fails this is blocked.
- The contract is enforced at compile time and re-verified when the DSL version changes.

### Shared Signal Chain (FACT-06)
- New module `research/signal_chain.py` is the single factor-value implementation: revision ID → one governed panel (via `BacktestEngine.load_panel`) → cross-sectional values/rank/zscore.
- Evaluation, multi-factor models, walk-forward, expected returns, and live as-of rebalance suggestions ALL consume this same chain — a second implementation is a bug.
- The chain binds a revision ID to a governed panel snapshot so train/serve skew is structurally impossible.

### PIT Universe Snapshot Contract
- Phase 10 lands the MINIMAL point-in-time universe contract: persist validity ranges / delisted markers / membership-as-of in the existing governed lake (no second datastore), and record the resolved universe in every manifest.
- This is the largest open data gap; without it Phases 11–13 silently inherit survivorship bias. The minimal contract ships now; richer PIT tooling can follow.

### Claude's Discretion
- Exact gate threshold default values (train/val IC cutoffs) are at planner/researcher discretion, fixed as policy constants with recorded provenance.
- Exact schema column names and migration structure for the new append-only tables, within the existing `operational/migrations.py` conventions.
- scipy 1.17.1 promotion to base deps and sklearn 1.8.0 lazy-import verification in an empty `.venv` — exact packaging shape at planner discretion.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `research/factor_dsl.py` (497 lines) — restricted DSL, immutable AST, `ALLOWED_FIELDS` allowlist, `_FUNCTION_ARITY`, `parse_factor`/`compile_factor`, `FactorFeatures` structural signature, `discover_similar` Jaccard ranking. Keep; extend, don't rewrite (no pyparsing/lark).
- `research/evaluation.py` (470 lines) — `FactorEvaluationService`, `ResolvedEvaluationConfig`, `MetricSummary` (mean/std/information_ratio), `FactorEvaluationResult` immutable evidence package, reuses `BacktestEngine` for governed panel access.
- `research/factor_registry.py` (295 lines) — `FactorRegistry`, `FactorRevision`, `SimilarityCandidate`, Jaccard dedup.
- `research/catalog.py` (505 lines) — `ExperimentCatalog`, `FactorEvidencePackage`, `ExperimentSnapshot`, comparison machinery.
- `research/repository.py` (491 lines) — `ResearchRepository`, SQLite append-only rows, `research_factor_definitions/revisions/experiments` tables.
- `research/artifacts.py` (120 lines) — `EvaluationArtifactService`, immutable artifact descriptors.
- `backtest/frozen_panel.py` (137 lines) — `FrozenPanelArtifactStore` — checksum-verified immutable governed panels; the pattern for input snapshots.
- `backtest/engine.py` — `BacktestEngine.load_panel` — the ONLY governed-data access seam.
- `operational/migrations.py` — SQLite migration conventions; new tables added here.

### Established Patterns
- Append-only SQLite rows with signature checksums; `input_snapshot_sha256` for run provenance.
- `BacktestEngine.load_panel()` as the sole market-data boundary; never direct Parquet/repository reads in new research code.
- Module docstrings state what the module knows/doesn't know; Chinese user-facing comments, English technical rationale.
- Logged graceful degradation with `# noqa: BLE001`; `logger = logging.getLogger(__name__)`.

### Integration Points
- `research/evaluation.py` currently owns orchestration; the signal chain becomes the shared compute backbone it (and models/walk-forward/expected-returns) delegate to.
- `research/catalog.py` gains admitted-factor summary storage; `factor_registry.py` gains admission-gate verdict recording.
- `operational/migrations.py` gains `factor_model_*` / `admission_*` tables.
- `backend/pyproject.toml` + `uv.lock`: scipy 1.17.1 promoted to base deps.

</code_context>

<specifics>
## Specific Ideas

- Shared signal chain is the AlphaMaster flagship lesson (anti train/serve skew): one compile → evaluate → score path for every consumer.
- Admission gates mirror AlphaAgent's promotion-gate pattern: train/val IC thresholds, no-lookahead, no-label-leakage, similarity dedup, candidate trail including rejections.
- The shifted-label leakage test follows the knowledge-base's label-leakage guidance: IC must collapse when the label is shifted by the forward-return horizon.
- PIT universe contract persists validity ranges/delisted markers/membership-as-of in the existing governed lake (qlib `Instrument`/`UpdateMode` contract as design reference, no second datastore).

</specifics>

<deferred>
## Deferred Ideas

- Richer point-in-time universe tooling beyond the minimal validity-range contract (deferred to later phases).
- LLM proposes DSL expressions interactively through a mining loop (v2, FACT-07).
- Parameter optimization and strategy ensembling (Phase 13, WFWD-02/03).
- Black-Litterman, max-Sharpe as first-class objective, short selling (v2 portfolio).
- ML-based expected returns (OPT-01, v2).

</deferred>
