# Phase 10: Factor Library & Multi-Factor Model - Research

**Researched:** 2026-08-01
**Domain:** A-share factor research — point-in-time universe, factor admission gates, monthly evaluation evidence, deterministic multi-factor composites, shared signal chain, DSL partition semantics
**Confidence:** HIGH

## Summary

Phase 10 is the v1.2 foundations phase: it must land the **append-only audit contract** and the **governed-data boundary** that Phases 11–15 inherit. Everything downstream depends on the shared signal chain; admission gates MUST precede portfolio construction (unvalidated factors poison expected returns). The research is grounded in the shipped v1.0/v1.1 host (`research/`, `backtest/`, `operational/migrations.py`, `tickflow/repository.py`) and the milestone research (`SUMMARY.md`).

The **largest open data gap is the point-in-time (PIT) universe**: the governed lake stores a *current-snapshot* instrument table (`data/instruments/instruments.parquet`, `as_of=2026-07-31`, 5537 rows, no delist column — verified) plus a ~1-year enriched lake (`kline_daily_enriched`, 2025-07-29→2026-07-30, 5535 symbols). Measured in the live lake: 144 current instruments have `listing_date` after the enriched range start — a naive "today's universe for all history" cross-section silently inflates IC. The minimal contract: an **append-only `factor_universe_membership` table in the existing operational.db** (no second datastore), seeded from `listing_date`/first-last-bar, closed by delist events, resolved per evaluation date before the single `BacktestEngine.load_panel` seam, and the **resolved universe recorded in every evaluation/admission/model manifest**. This is forward-compatible with Phase 13 per-fold resolution.

**Primary recommendation:** one shared `research/signal_chain.py` (revision → one governed panel → cross-sectional values/rank/zscore) consumed identically by evaluation, composite models, walk-forward, expected returns, and live as-of suggestions; admission gates as a fixed-threshold pipeline over the chain with append-only verdicts (rejections recorded identically); evaluation upgraded to expose ICIR + monthly robustness + coverage with the monthly series retained; multi-factor composite as deterministic equal/IC-weighted cross-sectional z-score persisted as a first-class catalog record; DSL partition-context contract enforced at compile time beside `_FUNCTION_ARITY` with a deterministic shifted-label leakage gate. scipy 1.17.1 promoted to base deps (`<1.18`; 1.18 requires Python ≥3.12 vs project floor ≥3.11 — verified uv.lock has cp311 wheels for 1.17.1); scikit-learn 1.8.0 stays in the `shadow` extra and must remain lazy-imported.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Admission Gates (FACT-01)
- Hard-threshold gating: fixed policy thresholds (train/val IC), deterministic, auditable — a rejection is as much a recorded verdict as an admission.
- Every verdict is an immutable append-only record with the candidate trail (source, evaluation evidence, gate results, reason).
- Train/val split is by date order (temporal), never random shuffle — random splits leak lookahead.
- Similarity dedup reuses the existing `discover_similar` Jaccard structural signature AND adds an IC-correlation check; both are part of the gate verdict.

#### Evaluation Evidence & Storage (FACT-02, FACT-05)
- Evaluation reports expose the FULL monthly evidence set, not a scalar mean: IC, RankIC, ICIR, monthly robustness, coverage, with the monthly series retained in the evidence package.
- Summary storage only for factor values: coverage, finite counts, signature. Storing full factor value matrices is an anti-feature (rejected).
- Rebalance cadence is configurable (daily/weekly/monthly), reusing the existing `RebalanceCadence` literal.
- Coverage is defined as non-empty share (finite counts), consistent with summary storage.

#### Multi-Factor Composite Model (FACT-03)
- Both equal-weight and IC-weighted cross-sectional z-score compositions supported; deterministic; no ML.
- Output is the composite z-score plus optional rank; the model is a first-class catalog record.
- Composite output is persisted immutably (with input snapshot signature) and consumed by Phase 11's optimizer by snapshot — not passed live across module boundaries.

#### DSL Partition-Context Contract (FACT-04)
- Every DSL operator declares its partition semantics (per-date / per-symbol / pointwise) inside the compiler, alongside the existing `_FUNCTION_ARITY` table — not in a separate sidecar config.
- Label fields are denied in the allowlist (already the case — `ALLOWED_FIELDS` excludes label/date columns; this becomes an explicit contract check).
- A deterministic shifted-label leakage test is a hard gate: when the label is shifted by the forward-return horizon, IC must collapse to ~0; a DSL change that fails this is blocked.
- The contract is enforced at compile time and re-verified when the DSL version changes.

#### Shared Signal Chain (FACT-06)
- New module `research/signal_chain.py` is the single factor-value implementation: revision ID → one governed panel (via `BacktestEngine.load_panel`) → cross-sectional values/rank/zscore.
- Evaluation, multi-factor models, walk-forward, expected returns, and live as-of rebalance suggestions ALL consume this same chain — a second implementation is a bug.
- The chain binds a revision ID to a governed panel snapshot so train/serve skew is structurally impossible.

#### PIT Universe Snapshot Contract
- Phase 10 lands the MINIMAL point-in-time universe contract: persist validity ranges / delisted markers / membership-as-of in the existing governed lake (no second datastore), and record the resolved universe in every manifest.
- This is the largest open data gap; without it Phases 11–13 silently inherit survivorship bias. The minimal contract ships now; richer PIT tooling can follow.

### Claude's Discretion
- Exact gate threshold default values (train/val IC cutoffs) are at planner/researcher discretion, fixed as policy constants with recorded provenance.
- Exact schema column names and migration structure for the new append-only tables, within the existing `operational/migrations.py` conventions.
- scipy 1.17.1 promotion to base deps and sklearn 1.8.0 lazy-import verification in an empty `.venv` — exact packaging shape at planner discretion.

### Deferred Ideas (OUT OF SCOPE)
- Richer point-in-time universe tooling beyond the minimal validity-range contract (deferred to later phases).
- LLM proposes DSL expressions interactively through a mining loop (v2, FACT-07).
- Parameter optimization and strategy ensembling (Phase 13, WFWD-02/03).
- Black-Litterman, max-Sharpe as first-class objective, short selling (v2 portfolio).
- ML-based expected returns (OPT-01, v2).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FACT-01 | Admission gates (train/val IC, no-lookahead, no-label-leakage, similarity dedup) with immutable append-only verdicts incl. candidate trail | `## Admission Gates` — fixed policy constants, temporal split, `discover_similar` reuse + IC-correlation, `factor_admission_verdicts` table |
| FACT-02 | Evaluation reports ICIR, monthly robustness, coverage alongside IC/RankIC with full monthly evidence set | `## Evaluation Upgrade` — formulas, Polars impl, `FactorEvaluationResult` extension, monthly series artifact |
| FACT-03 | Deterministic multi-factor composite (equal/IC-weighted cross-sectional z-score, no ML), consumed by portfolio optimization | `## Multi-Factor Composite` — `research/models.py`, deterministic weights, `factor_model_models` + immutable output |
| FACT-04 | DSL partition-context contract; label fields denied; deterministic shifted-label leakage gate | `## DSL Partition-Context Contract + Leakage Test` — `_FUNCTION_PARTITION`, `DENIED_FIELDS`, shifted-label IC collapse test |
| FACT-05 | Admitted factors stored in immutable catalog with summary storage (coverage, finite counts, signature) and revision lineage | `## Admission Gates` + `## Schema/Migration Sketch` — catalog `metrics` extension, admission→catalog linkage |
| FACT-06 | Single shared factor signal chain used identically by evaluation, models, walk-forward, expected returns, live as-of | `## Shared Signal Chain` — `FactorSignalChain.compute`, revision→panel binding, PanelCache dedup |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PIT universe resolution | API/Backend | Database/Storage | Resolver reads append-only membership (SQLite) + instruments dim (Parquet) and returns a per-date symbol set; the result feeds the existing `BacktestEngine.load_panel` seam (`engine.py:191-200`), never a new data path |
| Factor signal computation | API/Backend | — | One `research/signal_chain.py` over governed panels; no client/SSR involvement (research-only, single user) |
| Admission gates / verdicts | API/Backend | Database/Storage | Gate pipeline is server logic; verdicts are append-only SQLite rows with signature checksums |
| Monthly evaluation evidence | API/Backend | — | ICIR/robustness/coverage computed Polars-native in the research service; full matrices stay as immutable artifacts |
| Multi-factor composite | API/Backend | Database/Storage | Deterministic z-score composition; model definition + outputs persisted immutably |
| DSL compile-time contract | API/Backend | — | Compiler-side table beside `_FUNCTION_ARITY` (`factor_dsl.py:36-43`); no runtime sidecar config |

## Overview

The phase is deliberately layered so every later phase inherits a stable backbone:

1. **Governed-data boundary:** every new computation reads market data exclusively through `BacktestEngine.load_panel` (`engine.py:191-200`, `_load_panel_inner` at `:202-272`). Phase 10 adds a *universe-resolution step before* that seam — never a parallel read of the enriched parquet.
2. **Shared signal chain:** `research/signal_chain.py` is the single implementation of "compile a factor revision → apply it to one governed panel → cross-sectional values/rank/zscore". Evaluation (`evaluation.py`), composite models, walk-forward (Phase 13), expected returns, and live as-of suggestions all delegate to it.
3. **Append-only audit:** all new state is append-only SQLite rows (`research/repository.py` conventions) + immutable artifacts (`research/artifacts.py`, `backtest/frozen_panel.py` checksum pattern).
4. **Admission gates:** a fixed-threshold pipeline whose verdicts (including rejections) are immutable records carrying the candidate trail.
5. **PIT universe:** the minimal membership contract closes the survivorship-bias gap before Phases 11–13 consume it.

## PIT Universe Contract (PRIMARY)

### Problem (measured, not theoretical)

- The lake stores a **current snapshot** instrument table: `data/instruments/instruments.parquet` has 5537 rows, `as_of=2026-07-31`, columns `symbol, name, code, exchange, region, type, listing_date, total_shares, float_shares, tick_size, limit_up, limit_down, as_of` — **no delist/status column, no validity range** (verified via venv polars read).
- The enriched lake is short: `kline_daily_enriched` holds 1,305,493 rows, 5535 symbols, date range `2025-07-29 → 2026-07-30`, per-day median 5349 symbols, start/end symbol counts 5291/5528 (verified via DuckDB).
- **144 current instruments have `listing_date` after the enriched range start** (verified). A naive "today's universe for all history" cross-section includes stocks that were not tradeable at the start of the evaluation window — inflating IC and, downstream, returns. This is the survivorship-bias magnitude the contract must close.
- `instrument_sync.sync_instruments` (`services/instrument_sync.py`) **overwrites** `instruments.parquet` daily with a fresh snapshot (`as_of = date.today()`), so the lake retains no history of delisted symbols; delist detection today is only the laggard heuristic `KlineRepository.symbols_lagging(reference_date, min_gap_days)` (`tickflow/repository.py:1501`).

### Contract design (minimal, no second datastore)

**1. Append-only membership table in the existing operational.db** (new migration, `operational/migrations.py` convention — append a script to the `MIGRATIONS` tuple):

```sql
-- PIT universe membership: append-only validity events per (universe, symbol).
-- A symbol is "in the universe as-of date D" when its latest event with
-- effective_date <= D is 'listed'.
CREATE TABLE factor_universe_membership (
    id TEXT PRIMARY KEY,
    universe_name TEXT NOT NULL,                 -- e.g. 'cn-a-share', later 'hs300'
    symbol TEXT NOT NULL,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('stock','etf')),
    effective_date TEXT NOT NULL,                -- ISO date the membership state takes effect
    state TEXT NOT NULL CHECK (state IN ('listed','delisted')),
    source TEXT NOT NULL,                        -- 'instruments-sync' | 'delist-event' | 'manual'
    provenance_json TEXT NOT NULL,               -- checksum, originating run, reasoning
    created_at TEXT NOT NULL,
    UNIQUE (universe_name, symbol, effective_date, state)
);
CREATE INDEX idx_universe_membership_resolve
    ON factor_universe_membership(universe_name, symbol, effective_date);
```

This is the qlib `Instrument`/`UpdateMode` contract referenced in CONTEXT, distilled to one table. Append-only: a delist is a **new row**, never an UPDATE.

**2. Seed + close rules** (a `research/universe.py` resolver, or a method on `ResearchRepository`):
- **Seed (`listed`)**: for each row in `get_instruments()` (`tickflow/repository.py:1032`), `effective_date = listing_date` when present, else the symbol's first bar date in the enriched lake; `source='instruments-sync'`.
- **Close (`delisted`)**: appended when a delist is *confirmed* — provider data carrying a delist signal, or operator-confirmed (`source='manual'`). The existing `symbols_lagging` heuristic is **not** an automatic delist trigger (suspension ≠ delist); a long suspension simply drops out of per-date cross-sections because the enriched panel has no rows for the suspended dates.

**3. Resolver** (new, consumed by the signal chain):

```python
def resolve_universe(repo, *, universe_name: str, as_of: date,
                     asset_type: str = "stock") -> tuple[frozenset[str], str]:
    """Membership as-of: listed events <= as_of with no prior delist event.
    Returns (symbols, membership_fingerprint) where fingerprint = sha256(sorted symbols)."""
```

For evaluation windows the chain needs **per-date** membership: `resolve_universe_daily(...) -> pl.DataFrame[symbol, date]` exploded from the interval endpoints over the window's trading dates. Implementation stays Polars-native (interval overlap predicate).

**4. How `BacktestEngine.load_panel` consumers resolve the universe (survivorship guard):**
- The signal chain computes the **union of per-date eligible symbols** across `[start-warmup, end]`, passes that list as `symbols` to `load_panel` (`engine.py:191-200`), then **filters rows per date** with a membership join (`panel.join(membership_daily, on=["symbol","date"], how="inner")`). Per-date cross-sections (IC on date *t*) then use exactly the universe as-of *t*.
- `PanelCache._make_key` (`engine.py:169-175`) hashes the sorted symbol list, so identical calls are deduped; the per-date filter is cheap and happens after the single governed read.
- **No change to `load_panel` itself** — the seam stays the only governed-data access.

**5. Manifest extension (every evaluation/admission/model manifest):**
`evaluation._manifest` (`evaluation.py:341-378`) already records `universe`, `resolved_symbols`, `requested_start/end`, `observed_start/end`, `schema_fingerprint`, `source_fingerprint`. Extend it with:

```json
"universe_resolution": {
    "method": "factor_universe_membership/v1",
    "membership_fingerprint": "<sha256 of the per-date membership frame>",
    "per_date_symbol_counts": {"min": 5284, "median": 5349, "max": 5528},
    "excluded_delisted": ["<symbol>", "..."]
}
```

The `membership_fingerprint` makes the resolved universe reproducible and comparable across runs (feeds `catalog._compatibility_warnings`, `catalog.py:360-398`).

**6. Phase 13 forward-compat (design only, not implemented):**
A walk-forward fold is a `(train_start, train_end, test_start, test_end)` rectangle with a gap. Per-fold resolution = `resolve_universe_daily(universe, fold_start, fold_end)`; the reserved final OOS segment = `resolve_universe_daily(universe, oos_start, oos_end)` evaluated exactly once. The resolver signature and manifest fields are sufficient; Phase 13 adds fold geometry on top.

**Tradeoff / honest limitation:** historical delistings *before* Phase 10 cannot be reconstructed from the lake (overwritten snapshot). The contract fixes bias **going forward** and corrects the *listed-after-start* class (144 symbols measured) immediately via `listing_date`. Backfilling pre-Phase-10 delists requires a provider pull — recorded as an Open Question, not a Phase 10 blocker.

## Admission Gates

### Design

New module `research/admission.py`. The pipeline mirrors the shipped `advanced_promotion_gates` pattern (`migrations.py:492-500`: one row per gate with a fixed gate-name CHECK) but is factor-specific and fully append-only.

**Fixed policy thresholds** (constants with recorded provenance; values at Claude's discretion per CONTEXT):

```python
ADMISSION_POLICY_VERSION = "admission-policy-v1"
TRAIN_MIN_MEAN_IC = 0.02          # train-window mean IC floor
VAL_MIN_MEAN_IC = 0.01            # val-window mean IC floor (held-out, stricter)
MIN_TRAIN_OBSERVATIONS = 40       # rebalance dates required for ICIR stability
MAX_SIMILARITY_SCORE = 0.80       # Jaccard structural dedup (discover_similar)
MAX_IC_CORRELATION = 0.90         # per-date IC-series Pearson with an admitted factor
SHIFTED_LABEL_MAX_ABS_IC = 0.02   # shifted-label leakage gate
MIN_COVERAGE = 0.50               # finite-share floor (optional gate)
```

**Gate stages (ordered, deterministic):**

| # | Gate | Metric | Pass condition | Implementation seam |
|---|------|--------|----------------|---------------------|
| 1 | `no_lookahead` | structural | compiled expr references only `ALLOWED_FIELDS` (`factor_dsl.py:12-29`) and all stateful functions declare their partition context | DSL contract (FACT-04) — compiler enforced |
| 2 | `no_label_leakage` | shifted-label | `abs(mean(IC_shifted)) <= SHIFTED_LABEL_MAX_ABS_IC` | shifted-label test (FACT-04 section) |
| 3 | `similarity_dedup` | Jaccard + IC-corr | top `discover_similar` candidate score < `MAX_SIMILARITY_SCORE` AND max |IC-corr with admitted factors| < `MAX_IC_CORRELATION` | reuse `FactorRegistry.discover_similar` (`factor_registry.py:186-221`) + new IC-series correlation on val window |
| 4 | `train_ic` | mean IC / ICIR | `mean_IC_train >= TRAIN_MIN_MEAN_IC` | temporal split, first 70% of dates (fixed policy) |
| 5 | `val_ic` | mean IC / ICIR | `mean_IC_val >= VAL_MIN_MEAN_IC` | last 30% of dates, never touched by gates 1–4 |

**Temporal split:** by date order only (CONTEXT decision). Fixed policy: `TRAIN_FRACTION = 0.7` of the *evaluation window's* trading dates, applied identically each run → deterministic.

**Verdict record (append-only):**

```sql
CREATE TABLE factor_admission_verdicts (
    id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL REFERENCES research_factor_revisions(id) ON DELETE RESTRICT,
    policy_version TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('admitted','rejected')),
    reason TEXT NOT NULL,
    gates_json TEXT NOT NULL,          -- [ {gate, passed, metric, observed, threshold, detail} ] incl. rejections
    candidate_trail_json TEXT NOT NULL,-- source, evaluation_run_ids, experiment snapshot ids, gate results
    resolved_universe_json TEXT NOT NULL,
    input_snapshot_sha256 TEXT NOT NULL CHECK (length(input_snapshot_sha256) = 64),
    created_at TEXT NOT NULL,
    UNIQUE (revision_id, policy_version)
);
CREATE INDEX idx_admission_verdicts_revision ON factor_admission_verdicts(revision_id);
```

**Candidate trail incl. rejections:** `candidate_trail_json` carries (a) factor provenance from the revision (`FactorRevision.provenance`, `factor_registry.py:15-36`; e.g. `{"source": "manual", "ticket": "R-42"}` from the registry test), (b) each evaluation evidence package reference (`evaluation_run_id` + `ExperimentSnapshot.id` from `ExperimentCatalog.record_factor_evaluation`, `catalog.py:230-258`), (c) every gate result in order. A rejection is a full verdict row exactly like an admission — CONTEXT: "a rejection is as much a recorded verdict as an admission."

**IC-correlation dedup** (the new check beyond `discover_similar`): compute the candidate's per-date IC series and each admitted factor's per-date IC series on the *val* window; `pearson(IC_cand, IC_admitted)`; both the Jaccard structural score and the IC correlation are written into the gate verdict. `discover_similar` is untouched (`similarity never changes this path` per `factor_registry.py:169-184`), the correlation check is added at the admission layer.

## Evaluation Upgrade

### Formulas (all Polars-native, monthly series retained)

Base inputs already exist per rebalance date *t*: `ic_t` and `rank_ic_t` from `_correlation_series` (`evaluation.py:268-284`, `pl.corr` over the per-date cross-section). Extend:

| Metric | Formula | Note |
|--------|---------|------|
| **ICIR** | `mean(ic_m) / std(ic_m)` over **monthly** means `ic_m` | Current `MetricSummary.information_ratio` (`evaluation.py:299-306`) is `mean/std` over the raw series — same shape, new period. Expose explicitly as `icir`. |
| **Monthly robustness** | `count(ic_m > 0) / count(months)` | Positive-month share; report best/worst month alongside. |
| **Coverage** | per date: `mean(is_finite(_factor))` over the **resolved universe** that date; overall = mean over dates | Computed **before** the finite filter (`_evaluate_panel` currently drops non-finite rows at `evaluation.py:252-260`), so coverage measures the resolved cross-section, consistent with "summary storage only: coverage, finite counts" (CONTEXT). |

**Polars implementation sketch** (fits inside `evaluation.py` after `_correlation_series`):

```python
monthly = (
    evaluated
    .with_columns(pl.col("date").dt.strftime("%Y-%m").alias("_month"))
    .group_by("_month")
    .agg(
        pl.col("ic").mean().alias("ic_monthly"),
        pl.col("rank_ic").mean().alias("rank_ic_monthly"),
    )
)
icir = (monthly["ic_monthly"].mean() / monthly["ic_monthly"].std()).item()  # None when std ~ 0
monthly_robustness = (monthly["ic_monthly"] > 0).mean().item()
coverage_by_date = evaluated.group_by("date").agg(pl.col("_factor").is_finite().mean().alias("coverage"))
```

Coverage requires the *pre-filter* panel; the chain (FACT-06 section) returns both the finite-filtered frame and the pre-filter row count per date so coverage is computed on the resolved universe.

### Evidence package shape

- Extend `FactorEvaluationResult` (`evaluation.py:80-110`) with: `icir: float | None`, `monthly_robustness: float | None`, `coverage: Mapping[str, Any]` (mean + `coverage_series`), `monthly_ic_series: tuple[Mapping, ...]`.
- `_combined_metric_series` (`evaluation.py:286-297`) gains a `monthly_series.json` file in the artifact bundle (`artifacts.py:42-65` `write_bundle` adds one descriptor) — additive, existing descriptors unchanged.
- Catalog linkage: `ExperimentCatalog.record_factor_evaluation` (`catalog.py:230-258`) builds `FactorEvidencePackage.metrics`; add `icir`, `monthly_robustness`, `coverage`, `monthly_ic_series` keys. `_compatibility_warnings` (`catalog.py:360-398`) is unaffected (new keys are additive).
- The `compact_result` written to `result.json` gains the three scalar metrics.

## Multi-Factor Composite

### Design

New module `research/models.py`. Deterministic, no ML (CONTEXT decision).

```python
CompositeWeighting = Literal["equal", "ic_weighted"]

@dataclass(frozen=True, slots=True)
class CompositeModel:
    model_id: str
    name: str
    revision_ids: tuple[str, ...]           # sorted → determinism
    weighting: CompositeWeighting
    weights: Mapping[str, float]            # frozen at build: equal=1/n; ic_weighted=mean_ic_r/sum(mean_ic)
    input_snapshot_sha256: str              # sha256 of (revision_ids, weighting, membership_fingerprint, panel fingerprints)
    created_at: str
```

**Computation** (each revision via the signal chain, one shared governed read thanks to `PanelCache`):
- Per revision *r*, per date *t*, per symbol *i*: `z_{r,t,i}` = cross-sectional z-score — identical semantics to the DSL `zscore()` compile: `(x - x.mean().over("date")) / x.std().over("date")` (`factor_dsl.py:415-417`).
- **Equal-weight:** `composite_{t,i} = mean_r z_{r,t,i}`.
- **IC-weighted:** `w_r = mean_ic_r / sum_r' mean_ic_r'`, where `mean_ic_r` is the factor's evaluation mean IC (recorded evidence, not live). `composite_{t,i} = sum_r w_r * z_{r,t,i}`.
- Optional rank of the composite (`.rank().over("date")`).
- Determinism: revision ids sorted, float64 accumulation, no randomness anywhere.

**Persistence (immutable, snapshot-consumed):**
- Definition → `factor_model_models` table (append-only, schema below).
- Output → one immutable artifact per computation under `data/research_artifacts/<run_id>/` via the `EvaluationArtifactService` pattern (`artifacts.py:42-65`), with `input_snapshot_sha256` bound (mirrors `FrozenPanelArtifactStore` checksum discipline, `frozen_panel.py:38-137`).
- Phase 11 consumes the composite **by snapshot** (artifact + sha256), never a live module hand-off (CONTEXT).

## Shared Signal Chain

### Surface (new `research/signal_chain.py`)

```python
@dataclass(frozen=True, slots=True)
class SignalChainConfig:
    universe: str
    symbols: tuple[str, ...]                 # resolved PIT symbol list (union across window)
    asset_type: str                          # 'stock' | 'etf'
    start: date
    end: date
    warmup_days: int
    forward_return_horizon: int | None       # None for live as-of (no label yet)
    rebalance: RebalanceCadence = "daily"    # reuse evaluation.RebalanceCadence
    missing_data_treatment: MissingDataTreatment = "drop"
    warmup_treatment: WarmupTreatment = "exclude"

@dataclass(frozen=True, slots=True)
class FactorSignalFrame:
    revision_id: str
    dsl_version: str
    panel_fingerprint: str                   # sha256 over schema + observed range + row count
    resolved_universe: Mapping[str, Any]     # membership_fingerprint + per-date counts
    frame: pl.DataFrame                      # [symbol, date, _factor, _forward_return, _rank, _zscore]

class FactorSignalChain:
    def __init__(self, engine: BacktestEngine, registry: FactorRegistry,
                 universe_resolver: object) -> None: ...
    def compute(self, *, revision_id: str, config: SignalChainConfig) -> FactorSignalFrame:
        # 1. validate config (mirror evaluation._validate_config, evaluation.py:201-229)
        # 2. revision -> parse_factor -> compile  (the ONE compile path)
        # 3. resolve universe per date -> union symbol list
        # 4. engine.load_panel(symbols, start-warmup, end, columns=required, asset_type)
        # 5. values/rank/zscore with partition semantics + forward return
        # 6. per-date membership filter + finite/close filters + rebalance cadence
        # 7. bind panel_fingerprint + resolved_universe; return FactorSignalFrame
```

### Revision → panel binding (anti train/serve skew)

The chain reuses `FactorEvaluationService._validated_revision` logic (`evaluation.py:231-245`: `registry.get_revision` → `parse_factor` → DSL-version + fields cross-check) so a revision ID always resolves to exactly one canonical expression, one DSL version, one governed panel. Consumers never re-parse or re-derive the expression — the binding is structural. The live as-of path (`forward_return_horizon=None`) reuses the identical compile + universe resolution, differing only in skipping the label column.

### Consumers (identical consumption)

- **Evaluation**: `evaluation.py` delegates its `_evaluate_panel` + `_correlation_series` to the chain; `FactorEvaluationService` keeps config validation + artifact orchestration.
- **Composite models**: one `chain.compute` per admitted revision (PanelCache dedups the load).
- **Walk-forward (Phase 13)**: per-fold `SignalChainConfig` with per-fold resolved symbols.
- **Expected returns (Phase 11)**: composite z-score comes from the model artifact produced via the chain.
- **Live as-of suggestions (Phase 14)**: `start = end = as_of`, `forward_return_horizon=None`.
- A second implementation of factor values is a bug (CONTEXT FACT-06).

## DSL Partition-Context Contract + Leakage Test

### Compiler-side partition table

Extend `factor_dsl.py` beside `_FUNCTION_ARITY` (`factor_dsl.py:36-43`) — the contract lives **in the compiler**, never a sidecar config (CONTEXT):

```python
PartitionContext = Literal["pointwise", "per_date", "per_symbol"]

_FUNCTION_PARTITION: Final[dict[str, PartitionContext]] = {
    "abs": "pointwise",
    "sign": "pointwise",
    "log1p": "pointwise",
    "clip": "pointwise",
    "rank": "per_date",        # matches .over("date") in _compile_node
    "zscore": "per_date",      # matches .over("date")
    "rolling_mean": "per_symbol",  # matches .over("symbol")
}
```

- **Compile-time enforcement**: `_validate_call` (`factor_dsl.py:160-181`) and `_validate_expression` (`:214-247`) additionally require every call name ∈ `_FUNCTION_PARTITION`. A function added to `_FUNCTION_ARITY` without a partition entry is a compile error (enforced by a table-consistency unit test asserting `set(_FUNCTION_ARITY) == set(_FUNCTION_PARTITION)`).
- Binary `+ - * /` and fields are pointwise; `extract_features` (`factor_dsl.py:347-373`) computes the expression's **effective partition context** as the union of leaf contexts and surfaces it in `FactorFeatures` (new `partition_context: frozenset[str]`), so the admission `no_lookahead` gate and the leakage test can inspect semantics structurally.
- Bump `DSL_VERSION` (`factor_dsl.py:10`) to `factor-dsl-v2` when the contract lands; stored revisions keep their `dsl_version` and `_validated_revision` rejects cross-version reuse.

### Label fields denied (explicit contract check)

`ALLOWED_FIELDS` (`factor_dsl.py:12-29`) already excludes `date`/`symbol`/label columns. Make it an explicit, tested contract:
- Add `DENIED_FIELDS: Final[frozenset[str]] = frozenset({"date", "symbol", "label", "forward_return", "_forward_return", "_factor", "_rank", "_zscore"})` and a specific `FactorDslError` in `_validate_expression`/`_compile_node` when a field resolves to a denied name.
- Test: `parse_factor("close + label")` raises a *denied label field* diagnostic; `parse_factor("date")` / `"symbol"` also rejected (already true today).

### Deterministic shifted-label leakage test

Rationale (knowledge-base guidance, CONTEXT): a lookahead factor shows nonzero correlation with a **misaligned** label; a clean factor's IC collapses to ~0.

```python
def shifted_label_ic(evaluated: pl.DataFrame, *, horizon: int) -> float:
    """Label displaced by one extra horizon: close[t+2H]/close[t+H] - 1."""
    displaced = evaluated.with_columns(
        (pl.col("close").shift(-2 * horizon).over("symbol")
         / pl.col("close").shift(-horizon).over("symbol") - 1.0).alias("_shifted_label")
    )
    ic = displaced.group_by("date").agg(
        pl.corr(pl.col("_factor"), pl.col("_shifted_label")).alias("ic")
    )["ic"].drop_nulls()
    return float(abs(ic.mean())) if len(ic) else float("inf")
```

- Gate: `shifted_label_ic <= SHIFTED_LABEL_MAX_ABS_IC` (admission stage 2 and a hard pytest for every DSL change).
- **Deterministic**: same panel, same compiled factor, only the label displaced — the value changes only if the factor embeds future information.
- **Re-verified when DSL_VERSION changes**: the test matrix iterates all functions in `_FUNCTION_PARTITION` so a new operator cannot silently acquire full-panel/lookahead semantics (pitfall 1 in `SUMMARY.md`).

## Dependency Changes (scipy/sklearn)

### scipy 1.17.1 → base deps

- **Current state (verified):** `backend/pyproject.toml` has **no** direct scipy dependency; scipy 1.17.1 exists in `backend/uv.lock` only transitively (via `vectorbt` in the `backtest` extra and `scikit-learn` in the `shadow` extra — lock lines 3481-3491, 2910-2918).
- **Change:** add to base `[project] dependencies`: `"scipy>=1.17.1,<1.18"`.
- **Rationale:** Phase 11 HRP needs `scipy.cluster.hierarchy.linkage`; CONTEXT mandates the promotion now. `requires-python = ">=3.11"` (pyproject.toml); scipy **1.18.0 requires Python ≥3.12** `[CITED: .planning/research/SUMMARY.md]`, so the floor is pinned `<1.18`. `[VERIFIED]`: uv.lock shows scipy 1.17.1 with **cp311 wheels** (manylinux/win/macOS, lines ~2975+) and PyPI `pip index versions scipy` reports **1.17.1 as the latest** available (checked 2026-08-01).
- `uv.lock` regenerates after the edit (`uv lock`); the transitive pin is already 1.17.1 so resolution is stable.

### scikit-learn 1.8.0 → stay lazy-imported in `shadow` extra

- **Current state (verified):** pyproject `shadow = ["scikit-learn==1.8.0"]` with the comment "runtime code must lazy-import scikit-learn"; uv.lock pins 1.8.0 (`shadow` marker, line 206). PyPI latest is 1.9.0 (checked 2026-08-01); the project pins 1.8.0 deliberately.
- **Change:** **no promotion**. Phase 10 consumes no sklearn (Ledoit-Wolf is Phase 12). The lazy-import contract: sklearn may only be imported *inside* the function that needs it (risk-model boundary), never at module top. Phase 10 enforces this by an import audit in the empty-`.venv` verification (below).

### Empty-.venv verification plan (planned — NOT executed during research)

1. `cd backend && uv venv --clear` — fresh empty environment (current `.venv` already carries scipy 1.17.1 / sklearn 1.8.0 / polars 1.40.1 / numpy 2.4.6 under python3.14, but the plan must not assume that).
2. `uv sync --extra shadow` (or base + all extras) — assert resolution succeeds with scipy `1.17.1`.
3. `uv pip check` / `uv lock --check` — no dependency conflicts.
4. `python -c "import scipy; print(scipy.__version__)"` → `1.17.1`.
5. **Lazy-import audit:** `python -X importtime -c "import app.research.signal_chain, app.research.admission, app.research.evaluation"` and assert `sklearn`/`scikit_learn` never appears; equivalently a subprocess asserting `"sklearn" not in sys.modules` after importing the research package (module-top imports only).
6. Smoke: `ResearchRepository(path).migrate()` + `FactorRegistry.create_factor` + `FactorSignalChain.compute` over a fixture panel — no `sklearn` import on the path.
7. Marked in the plan as a **Wave 0 gate**, not an assumption.

## Schema/Migration Sketch

All new tables are appended to `MIGRATIONS` in `operational/migrations.py` (one new script; `migrate_operational_db` applies atomically with `PRAGMA user_version`, `migrations.py:1547-1564`). `ResearchRepository` (`research/repository.py`) gains the insert/query methods, following `_insert_revision`/`create_experiment` append-only conventions (`repository.py:95-150`, `251-330`) and `_json` canonical serialization.

| Table | Purpose | Key columns | Append-only rule |
|-------|---------|-------------|------------------|
| `factor_universe_membership` | PIT membership events | universe_name, symbol, asset_type, effective_date, state, source, provenance_json | INSERT only; delist = new row |
| `factor_admission_verdicts` | Gate verdicts incl. rejections | revision_id FK, policy_version, verdict, gates_json, candidate_trail_json, input_snapshot_sha256 | INSERT only; UNIQUE(revision_id, policy_version) |
| `factor_model_models` | Composite model definitions | model_id, name, weighting CHECK, revision_ids_json, weights_json, input_snapshot_sha256, created_at | INSERT only |
| `factor_model_composites` | Immutable composite outputs | id, model_id FK, output_sha256, artifact_relative_path, input_snapshot_sha256, created_at | INSERT only; one row per computation |

Manifest extension is **JSON-only** (no migration): `evaluation._manifest` (`evaluation.py:341-378`) gains the `universe_resolution` block; `FactorEvidencePackage.metrics` (`catalog.py:105-116`) gains the new evidence keys.

## Standard Stack

### Core (already in the host — reuse, don't change)

| Library | Version (verified) | Purpose | Why Standard |
|---------|--------------------|---------|--------------|
| Polars | 1.40.1 (lock; PyPI latest 1.43.1) | All factor/evaluation/composite computation | Already the host's data layer; `pl.corr`, `group_by`, `over` cover IC/ICIR/robustness/coverage natively |
| SQLite (operational.db) | stdlib | Append-only research records | Existing `ResearchRepository` + `migrations.py` contract |
| FastAPI / Pydantic v2 | existing | Research API (`api/research.py`) | Host API layer; no new surface needed in Phase 10 |

### Supporting (Phase 10 additions)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scipy | `>=1.17.1,<1.18` (base) | HRP + PSD helpers (Phase 11); promoted now per CONTEXT | Declared in base deps; not consumed by Phase 10 code itself |
| scikit-learn | `==1.8.0` (shadow extra) | Ledoit-Wolf (Phase 12) | Lazy-import at risk-model boundary only; never module-top |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Append-only SQLite membership | Per-date Parquet universe snapshots (`data/universe/date=…`) | Parquet sidecar needs a **new** governed-data seam and a new sync stage; SQLite slots into the existing `ResearchRepository` + append-only convention with no second datastore (CONTEXT constraint) |
| Inline per-date filter after `load_panel` | Add a `universe` param to `load_panel` | Modifying the seam risks every existing backtest consumer; filtering post-seam keeps `load_panel` byte-identical |
| IC-weighted by ICIR | IC-weighted by mean IC | CONTEXT says "IC-weighted"; mean IC is the literal reading and is already recorded evidence. ICIR weighting is a documented variant |

## Package Legitimacy Audit

> Ecosystem verification. The gsd-tools `package-legitimacy` seam defaults to **npm**; the npm records for `scipy`/`scikit-learn`/`polars` are squatted low-download packages (the seam returned `SUS` for all three) — a **cross-ecosystem false positive** (protocol Step 2). The correct registry is PyPI; verified below via `pip index` + `backend/uv.lock`.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| scipy | PyPI | ~23 yrs (2001) | ~100M+/wk | github.com/scipy/scipy | OK | Approved — promote `>=1.17.1,<1.18` to base |
| scikit-learn | PyPI | ~16 yrs (2010) | ~50M+/wk | github.com/scikit-learn/scikit-learn | OK | Approved — stays `shadow` extra, lazy-import |
| polars | PyPI | ~5 yrs | high | github.com/pola-rs/polars | OK | Unchanged (existing base dep) |
| scipy / scikit-learn / polars | **npm** | n/a | low (squats) | unrelated | SUS (cross-ecosystem) | **Inapplicable** — npm is the wrong registry for Python packages |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none on the correct (PyPI) registry. The npm `SUS` results are documented false positives from a wrong-ecosystem lookup.

## Common Pitfalls

### Pitfall 1: Today's universe used for all history (survivorship bias)
**What goes wrong:** IC and downstream returns are inflated because post-start listings are included and pre-end delistings excluded.
**Why:** `instruments.parquet` is a current snapshot overwritten daily (`instrument_sync.sync_instruments`, `as_of=today`); no per-date membership exists.
**How to avoid:** `factor_universe_membership` + per-date resolution before `load_panel`; record `membership_fingerprint` in every manifest.
**Warning signs:** evaluation `resolved_symbols` contains symbols with `listing_date` after `requested_start`; `per_date_symbol_counts.max > instruments.count` never reconciles.

### Pitfall 2: Scalar mean-IC hides a few hot months
**What goes wrong:** a factor with 3 strong months and 40 weak months passes a mean-IC gate.
**Why:** only `MetricSummary.mean` was exposed (`evaluation.py:66-74,299-306`).
**How to avoid:** ICIR + monthly robustness + the monthly series as a hard gate input.
**Warning signs:** `monthly_robustness < 0.5` while `mean_ic > threshold`.

### Pitfall 3: A second factor-value implementation drifts from evaluation (train/serve skew)
**What goes wrong:** live as-of or walk-forward scores differ from evaluation because the compile/zscore path was re-implemented.
**Why:** no shared chain existed.
**How to avoid:** `signal_chain.py` is the only path; evaluation, models, walk-forward, expected returns all call `chain.compute`; cross-consumer equality test (same config → identical frames).
**Warning signs:** any module importing `parse_factor`/`compile_factor` other than the chain and the DSL itself.

### Pitfall 4: New DSL operator silently acquires full-panel/lookahead semantics
**What goes wrong:** a new function uses `.over()` incorrectly or references future bars, leaking the label.
**Why:** arity-only table (`_FUNCTION_ARITY`) doesn't declare partition semantics.
**How to avoid:** `_FUNCTION_PARTITION` required for every function + shifted-label leakage gate on every DSL change.
**Warning signs:** a function added to `_FUNCTION_ARITY` without a `_FUNCTION_PARTITION` entry compiles (regression test must fail).

### Pitfall 5: Coverage measured on the post-filter panel
**What goes wrong:** coverage reads 100% because non-finite rows were already dropped by `_evaluate_panel` (`evaluation.py:252-260`).
**How to avoid:** compute coverage on the resolved-universe pre-filter panel in the chain.
**Warning signs:** coverage never below 1.0.

### Pitfall 6: scipy 1.18 auto-resolves and breaks Python 3.11
**What goes wrong:** `uv sync` resolves scipy 1.18.0, which requires Python ≥3.12 (project floor 3.11).
**How to avoid:** pin `scipy>=1.17.1,<1.18` in base deps and lock; empty-`.venv` verification asserts `scipy.__version__ == 1.17.1`.
**Warning signs:** fresh-venv resolution picks `1.18.x`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-sectional z-score / rank | Custom per-date loops | DSL `zscore()`/`rank()` compile (`factor_dsl.py:415-417`, `.over("date")`) + chain | Deterministic, already tested, single implementation |
| IC / RankIC / ICIR / robustness | Reimplemented statistics | Polars `pl.corr`, `group_by`, `is_finite` — extended `_correlation_series`/`_summary` | Native, lazy, matches shipped evidence |
| Structural factor similarity | New fingerprint scheme | `discover_similar` + `SimilarityCandidate` (`factor_registry.py:186-246`) | Shipped, deterministic, Jaccard components recorded |
| Immutable snapshot/checksum | Roll-your-own hashing | `EvaluationArtifactService.write_bundle` (`artifacts.py:42-65`) + `FrozenPanelArtifactStore` pattern | O_EXCL + fsync + sha256 discipline already proven |
| SQLite append-only rows | New persistence layer | `ResearchRepository` + `migrations.py` conventions | `_json` canonical serialization, atomic inserts, UNIQUE guards |
| A-share universe membership | A second datastore | `factor_universe_membership` in operational.db | CONTEXT: no second datastore; qlib contract distilled to one table |

**Key insight:** every hard problem here (determinism, audit, PIT, no-leakage) is solved by *reusing* shipped seams — the DSL compiler, the panel cache, the artifact store, the repository — and adding only thin, append-only contracts on top.

## Verification Plan

> Read-only plan for the planner; nothing below is executed during research.

### Unit / integration tests (map to Wave 0)
- **DSL contract:** `tests/research/test_factor_dsl.py` — extend: partition-table consistency (`set(_FUNCTION_ARITY) == set(_FUNCTION_PARTITION)`), denied-label diagnostics, effective partition context on composite expressions.
- **Leakage gate:** shifted-label test over all `_FUNCTION_PARTITION` functions — assert `|IC_shifted|` collapses for clean factors and is blocked for a deliberately lookahead expression.
- **Signal chain:** `tests/research/test_signal_chain.py` (new) — revision→panel binding, DSL-version/fields mismatch rejection, per-date membership filter excludes post-listing symbols, cross-consumer equality (chain output == evaluation `_evaluate_panel` on same config).
- **Evaluation upgrade:** `tests/research/test_factor_evaluation.py` — extend — ICIR/monthly-robustness/coverage match a NumPy reference on a fixture panel; coverage is computed on the resolved universe (pre-filter).
- **Admission:** `tests/research/test_admission.py` (new) — every gate result recorded; a rejection produces a full verdict row with candidate trail; temporal split deterministic; IC-correlation dedup catches a near-duplicate that Jaccard misses.
- **Composite:** `tests/research/test_models.py` (new) — equal vs IC-weighted weights; two identical builds → identical `input_snapshot_sha256`; output artifact immutable.
- **Universe resolver:** `tests/research/test_universe_resolution.py` (new) — listed-after-start excluded per date; delist event closes membership as-of; fingerprint changes when membership changes.
- **Migrations:** `tests/test_operational_migrations.py` — extend for the four new tables + UNIQUE/FK enforcement.

### Cross-module integrity checks
- Library IC used by composite weights == evaluation-recorded mean IC for the same revision/config.
- Composite output consumed by Phase 11 == artifact bytes identified by `input_snapshot_sha256`.

### Phase gate
- Full backend suite green before `/gsd-verify-work` (not run during research).

## Open Questions

1. **Historical delist backfill (pre-Phase 10).** The lake overwrote the instruments snapshot daily; delisted-before-now symbols are unrecoverable without a provider pull. *What we know:* enriched lake only spans 2025-07-29→2026-07-30. *Recommendation:* Phase 10 ships forward-recording + listing-date correction; backfill is a follow-up (deferred tooling).
2. **IC-weighted definition.** CONTEXT says "IC-weighted"; equal-weight vs IC-weighting by **mean IC** vs **ICIR** — *recommendation:* mean IC (literal reading, already recorded); document ICIR-weighting as a variant. Needs a one-line user confirm in discuss-phase.
3. **Gate threshold defaults.** `TRAIN_MIN_MEAN_IC=0.02`, `VAL_MIN_MEAN_IC=0.01`, `MAX_IC_CORRELATION=0.90`, `SHIFTED_LABEL_MAX_ABS_IC=0.02` are Claude's-discretion proposals; the planner should surface them as policy constants with recorded provenance for user confirmation.
4. **Suspension handling.** Long suspensions drop out of per-date cross-sections automatically (no rows); whether the membership table should *explicitly* record `suspended` state is richer tooling — deferred.
5. **`listing_date` dtype.** The live instruments file stores `listing_date` as a String (`'YYYY-MM-DD'`), while the provider schema (`data_providers/schemas.py:11-13`) declares `list_date`/`status`. The resolver must normalize this (cast + fallback) — a small implementation detail to pin at plan time.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | scipy 1.18.0 requires Python ≥3.12 (project floor ≥3.11), so `<1.18` pin is required | Dependency Changes | 1.18 could auto-resolve on a 3.12+ interpreter and change numerical results; pin keeps lock stable regardless |
| A2 | IC-weighted means weight ∝ mean IC (not ICIR) | Multi-Factor Composite | Wrong weighting method — low risk; both deterministic, needs user confirmation (Open Question 2) |
| A3 | Default gate thresholds (0.02/0.01/0.90/0.02) are reasonable for A-share daily factors | Admission Gates | Thresholds too loose/tight admit/reject differently; they are fixed policy constants the user can revise |
| A4 | `symbols_lagging` (suspension) must NOT auto-delist | PIT Universe | Auto-delisting suspended names would shrink the universe wrongly; manual/provider-confirmed delist only |
| A5 | `.venv` empty-verify will pass on a clean python3.11 target | Dependency Changes | scipy 1.17.1 cp311 wheels verified in uv.lock, but a clean-3.11 build should be executed in Wave 0 to confirm |

## Environment Availability

> Phase 10 has no new external services; the Python stack is already provisioned.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python runtime | all | ✓ | 3.14 (`.venv/bin/python`) / 3.11.2 (host) | — |
| scipy | Phase 11 promotion + empty-`.venv` gate | ✓ (installed in current `.venv`) | 1.17.1 | `uv sync` in Wave 0 |
| scikit-learn | lazy-import audit (Phase 12 consumer) | ✓ (installed) | 1.8.0 | shadow extra |
| polars | all factor computation | ✓ | 1.40.1 | — |
| SQLite / operational.db | append-only records | ✓ | stdlib | — |
| Governed lake (Parquet) | `load_panel` | ✓ | enriched 2025-07-29→2026-07-30 | — |

**Missing dependencies with no fallback:** none — the stack is already installed in `.venv` (verified: scipy 1.17.1, scikit-learn 1.8.0, polars 1.40.1, numpy 2.4.6, python 3.14).

## Validation Architecture

> `workflow.nyquist_validation: true` (config.json) → section required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8+ (dev extra, `pyproject.toml`) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (`--import-mode=importlib`, asyncio auto) |
| Quick run command | `cd backend && .venv/bin/python -m pytest tests/research -x` |
| Full suite command | `cd backend && .venv/bin/python -m pytest -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FACT-01 | Admission gates + immutable verdicts | unit | `pytest tests/research/test_admission.py -x` | ❌ Wave 0 |
| FACT-02 | ICIR / monthly robustness / coverage | unit | `pytest tests/research/test_factor_evaluation.py -x` | ✅ extend |
| FACT-03 | Deterministic composite | unit | `pytest tests/research/test_models.py -x` | ❌ Wave 0 |
| FACT-04 | DSL partition contract + leakage gate | unit | `pytest tests/research/test_factor_dsl.py -x` | ✅ extend |
| FACT-05 | Catalog summary + revision lineage | unit | `pytest tests/research/test_experiment_catalog.py -x` | ✅ extend |
| FACT-06 | Shared signal chain | unit | `pytest tests/research/test_signal_chain.py -x` | ❌ Wave 0 |
| PIT contract | Per-date universe resolution + manifest | unit | `pytest tests/research/test_universe_resolution.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/research -x` (or the touched test file).
- **Per wave merge:** `pytest tests/research tests/test_operational_migrations.py -x`.
- **Phase gate:** full backend suite green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/research/test_admission.py` — FACT-01 (new)
- [ ] `tests/research/test_models.py` — FACT-03 (new)
- [ ] `tests/research/test_signal_chain.py` — FACT-06 (new)
- [ ] `tests/research/test_universe_resolution.py` — PIT contract (new)
- [ ] Extend `tests/research/test_factor_dsl.py` — FACT-04 partition + leakage matrix
- [ ] Extend `tests/research/test_factor_evaluation.py` — FACT-02 evidence
- [ ] Extend `tests/research/test_experiment_catalog.py` — FACT-05 metrics
- [ ] Extend `tests/test_operational_migrations.py` — four new tables
- [ ] Wave 0 gate: empty-`.venv` `uv sync --extra shadow` + scipy version + lazy-import audit (Dependency Changes)

## Security Domain

> `workflow.security_enforcement: true` (config.json) → section required.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Local single-user research host; no new auth surface |
| V3 Session Management | no | No new sessions |
| V4 Access Control | minimal | New records are server-issued only (no browser-selected revision IDs — matches `research_strategy_asset_bindings` fail-closed pattern, `migrations.py:726-732`) |
| V5 Input Validation | yes | DSL restricted grammar (no escape hatch — `factor_dsl.py` docstring); new admission/model DTOs use Pydantic strict models like `FactorEvaluationRequest` (`api/research.py:58-73`) |
| V6 Cryptography | yes | SHA-256 checksums for snapshots/manifests (`_signature`, `_checksum`, artifact checksums) |

### Known Threat Patterns for {FastAPI + Polars + SQLite}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| DSL expression injection | Tampering | Tokenizer/parser allowlist (`ALLOWED_FIELDS`, `_FUNCTION_ARITY`, `_FUNCTION_PARTITION`); no eval/exec; compile-boundary validation repeated (`factor_dsl.py:385-423`) |
| Lookahead / label leakage via new operators | Elevation of Privilege (data) | `_FUNCTION_PARTITION` compile contract + shifted-label leakage gate (FACT-04) |
| PIT universe tampering | Tampering | Append-only membership rows + `membership_fingerprint` in manifests; UNIQUE constraints |
| Artifact substitution | Spoofing | O_EXCL creation + fsync + sha256 (`artifacts.py:76-118`); checksum-verified reads |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Scalar mean-IC evaluation (`MetricSummary.mean/std`, `evaluation.py:66-74`) | Full monthly evidence set (IC, RankIC, ICIR, robustness, coverage + monthly series) | Phase 10 | Hot-month overfitting becomes visible; gates use the full set |
| No universe history (current-snapshot instruments) | Append-only PIT membership + per-date resolution + manifest fingerprint | Phase 10 | Survivorship bias closed going forward (qlib `Instrument`/`UpdateMode` contract distilled) |
| Evaluation owns compile + compute (`evaluation.py:_evaluate_panel`) | Shared `signal_chain.py` single implementation | Phase 10 | Train/serve skew structurally impossible (AlphaMaster lesson) |
| Arity-only DSL table | Arity + partition-context table (`_FUNCTION_PARTITION`) | Phase 10 | Lookahead DSL changes blocked at compile time |

**Deprecated/outdated:**
- `MetricSummary.information_ratio` as the sole robustness stat — superseded by explicit `icir` + `monthly_robustness` + monthly series (kept for backward compatibility of the field name).
- Direct `_evaluate_panel` consumption outside the chain — evaluation must delegate to `FactorSignalChain.compute` (a second implementation is a bug, FACT-06).

## Sources

### Primary (HIGH confidence — code-verified this session)
- `backend/app/research/factor_dsl.py` — `ALLOWED_FIELDS` (l.12-29), `_FUNCTION_ARITY` (l.36-43), `_validate_expression` (l.214-247), `_compile_node` (l.400-423), `extract_features` (l.347-373), `DSL_VERSION` (l.10)
- `backend/app/research/evaluation.py` — `ResolvedEvaluationConfig` (l.37-52), `MetricSummary` (l.66-74), `FactorEvaluationResult` (l.80-110), `evaluate` (l.115-199), `_correlation_series` (l.268-284), `_summary` (l.299-306), `_manifest` (l.341-378), `_evaluate_panel` (l.247-260)
- `backend/app/research/factor_registry.py` — `discover_similar` (l.186-221), `_candidate`/`_jaccard` (l.66-69, 223-246), `FactorRevision.provenance` (l.15-36)
- `backend/app/research/catalog.py` — `FactorEvidencePackage` (l.105-116), `record_factor_evaluation` (l.230-258), `_compatibility_warnings` (l.360-398)
- `backend/app/research/repository.py` — `create_factor_with_revision` (l.95+), `_insert_revision`, `create_experiment` (l.251-330), `_json` canonicalization
- `backend/app/research/artifacts.py` — `write_bundle` (l.42-65), O_EXCL + fsync + sha256 (l.76-118)
- `backend/app/backtest/frozen_panel.py` — `FrozenPanelArtifactStore.create/load` checksum verification (l.38-137)
- `backend/app/backtest/engine.py` — `load_panel` (l.191-200), `_load_panel_inner` (l.202-272), `PanelCache.get_or_compute/_make_key` (l.110-176)
- `backend/app/operational/migrations.py` — `MIGRATIONS` tuple + `migrate_operational_db` (l.1547-1564), `advanced_promotion_gates` (l.492-500)
- `backend/app/tickflow/repository.py` — `get_enriched_range` (l.963-1000), `get_instruments` (l.1032-1040), `symbols_lagging` (l.1501)
- `backend/app/services/instrument_sync.py` — `_flatten_instruments` (listing_date), `sync_instruments` (as_of=date.today)
- `backend/app/data_providers/schemas.py` — `INSTRUMENT_COLUMNS` (l.11-13)
- `backend/pyproject.toml` — base deps, `shadow` extra (`scikit-learn==1.8.0`), `requires-python = ">=3.11"`
- `backend/uv.lock` — scipy 1.17.1 (l.2961+, cp311 wheels), scikit-learn 1.8.0 (l.2911), numpy 2.4.6 (l.1676)
- Live lake probe (venv polars/duckdb): instruments.parquet 5537 rows `as_of=2026-07-31` no delist col; enriched 1,305,493 rows / 5535 symbols / 2025-07-29→2026-07-30; 144 instruments listed after enriched start

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` — milestone research: PIT gap (largest open data gap), scipy 1.17.1 pin rationale (`<1.18`, Python ≥3.12 floor), AlphaMaster train/serve-skew lesson, qlib `Instrument`/`UpdateMode` design reference, AlphaAgent promotion-gate pattern
- PyPI registry via `pip index versions scipy|scikit-learn|polars` (2026-08-01): scipy latest 1.17.1; sklearn latest 1.9.0 (1.8.0 pinned); polars latest 1.43.1 (lock 1.40.1)

### Tertiary (LOW confidence)
- None — all code-verified; remaining uncertainty captured in `## Open Questions` and `## Assumptions Log`.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against `backend/uv.lock` + PyPI + installed `.venv`.
- Architecture: HIGH — every recommendation mapped to a shipped seam with file:line references.
- Pitfalls: HIGH — each pitfall anchored to a measured fact (PIT bias magnitude, current-snapshot overwrite) or a shipped code path (`_evaluate_panel` finite-filter, `_FUNCTION_ARITY`).

**Research date:** 2026-08-01
**Valid until:** 2026-08-31 (30 days; stack facts stable, scipy/sklearn versions re-verify at Wave 0)
