# Phase 2: Factor And Strategy Research - Gap-Closure Pattern Map

**Mapped:** 2026-07-11  
**Scope:** the two deterministic defects reported by `02-VERIFICATION.md`; no application implementation was changed by this map.  
**Files classified:** 8 implementation/test targets plus 3 reference-only analogs  
**Analogs found:** 8 / 8 mandatory targets

## Verified Gaps

1. **FACT-01 — DSL state leaks across governed panel partitions.** `FactorEvaluationService._evaluate_panel()` sorts the panel by `symbol,date` and evaluates one compiled expression (`backend/app/research/evaluation.py:285-302`), but `factor_dsl._compile_node()` currently emits unpartitioned `rank`, `zscore`, and `rolling_mean` expressions (`backend/app/research/factor_dsl.py:488-495`). Therefore cross-sectional operations can span dates and rolling operations can span symbols.
2. **FACT-03 — trusted strategy snapshots lack governed-data revision/fingerprint.** `_strategy_input_manifest()` currently returns source, strategy, asset type, symbols, date window, and row count only (`backend/app/api/backtest.py:344-356`). `ExperimentCatalog._compatibility_warnings()` already emits the required warning when manifest `revision`/`data_revision` or `fingerprint`/`schema_fingerprint` values differ (`backend/app/research/catalog.py:456-501`), but a strategy snapshot supplies neither compatible identity field.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality | Gap status |
|---|---|---|---|---|---|
| `backend/app/research/factor_dsl.py` | DSL compiler / utility | transform | `backend/app/indicators/pipeline.py` and `backend/app/backtest/engine.py` | exact operation semantics | mandatory FACT-01 |
| `backend/app/research/evaluation.py` | governed evaluation service | request-response / transform | its own panel-loading and manifest boundary | exact integration seam | mandatory FACT-01 regression guard; source change only if compiler context requires it |
| `backend/tests/research/test_factor_dsl.py` | unit regression test | transform | existing compiler test in the same file | exact | mandatory FACT-01 |
| `backend/tests/research/test_factor_evaluation.py` | service regression test | request-response / transform | `StubBacktestEngine`, `_panel`, and `_config` in the same file | exact | mandatory FACT-01 |
| `backend/app/backtest/strategy.py` | registered strategy service / result contract | request-response | `FactorEvaluationService._manifest()` | role-match governed-manifest producer | mandatory FACT-03 if the manifest is produced from the loaded panel |
| `backend/app/api/backtest.py` | backtest API / catalog handoff | request-response | `_strategy_input_manifest()` and `_finalize_strategy_experiment()` in the same module | exact | mandatory FACT-03 |
| `backend/tests/research/test_strategy_experiment_handoff.py` | API handoff regression test | request-response | synchronous and SSE fixture paths in the same file | exact | mandatory FACT-03 |
| `backend/tests/research/test_experiment_catalog.py` | immutable catalog/comparison regression test | CRUD / transform | `test_registered_strategy_snapshot_and_comparison_expose_deltas_without_winner` | exact | mandatory FACT-03 |
| `backend/app/research/catalog.py` | immutable catalog/comparison service | CRUD / transform | existing `_compatibility_warnings()` | exact reference | preserve existing warning; no new warning convention |
| `backend/app/indicators/pipeline.py` | governed indicator transform | transform | `compute_indicators()` time-series windows | exact partition analog | reference only |
| `backend/app/backtest/engine.py` | governed backtest engine | transform | `cross_section_rank()` | exact partition analog | reference only |

## Pattern Assignments

### `backend/app/research/factor_dsl.py` — partitioned DSL compilation

**Relevant symbols:** `compile_ast()` (lines 447-450), `_compile_node()` (lines 453-497), `Call` handling (lines 476-496).

**Closest analog A — time-series windows:** `backend/app/indicators/pipeline.py:356-407`

```python
df = df.sort(["symbol", "date"])
prev_close = pl.col("close").shift(1).over("symbol")
_p1.append(pl.col("close").rolling_mean(20).over("symbol").alias("ma20"))
_p1.append(pl.col("volume").shift(1).rolling_mean(5).over("symbol").alias("_vol_ma5_prev"))
```

**Closest analog B — cross-sectional operations:** `backend/app/backtest/engine.py:1636-1647`

```python
return panel.with_columns(
    pl.col(col).rank(method="random").over("date").alias(f"{col}_rank")
)
```

**Current defective compiler evidence:** `backend/app/research/factor_dsl.py:488-495`

```python
if expression.name == "rank":
    return arguments[0].rank()
if expression.name == "zscore":
    value = arguments[0]
    return (value - value.mean()) / value.std()
if expression.name == "rolling_mean":
    return arguments[0].rolling_mean(window_size=window)
```

**Required convention:** keep the existing parser/allowlist/AST-dispatch model. At the three fixed constructors only, express cross-sectional `rank` and both aggregate terms of `zscore` over `"date"`; express `rolling_mean` over `"symbol"`. Do not introduce dynamic column access, `pl.sql_expr`, Python evaluation, caller-configurable partition names, or a parallel compiler.

**Integration cautions:**

- The partitioning is semantic, not merely an evaluation optimization: a nested stateful expression must retain the fixed partition at the actual `rank`, `mean`, `std`, or rolling node.
- `rolling_mean` requires deterministic symbol/date ordering. The existing governed evaluator sorts exactly `symbol,date` before compilation/execution; retain that boundary (`evaluation.py:285-289`).
- Direct compiler callers must supply `symbol` and `date` when exercising these stateful functions. Do not weaken the compiler test by testing only one symbol or one date.
- Preserve the existing `rank()` default and z-score arithmetic unless an existing Polars behavior requires an explicit equivalent; this closure is about partition boundaries, not an unrelated ranking-policy change.

### `backend/app/research/evaluation.py` — governed execution boundary

**Relevant symbols:** `FactorEvaluationService.evaluate()` (lines 132-223), `_evaluate_panel()` (lines 285-302), `_correlation_series()` (lines 317-334), `_manifest()` (lines 391-425).

**Concrete existing flow:**

```python
panel = self.engine.load_panel(
    list(sorted(config.symbols)), load_start, config.end,
    columns=panel_columns, asset_type=config.asset_type,
)
...
values = (
    panel.sort(["symbol", "date"])
    .with_columns(parsed.compile().cast(pl.Float64).alias("_factor"))
    .with_columns(
        (pl.col("close").shift(-config.forward_return_horizon).over("symbol") / pl.col("close") - 1.0)
        .cast(pl.Float64).alias("_forward_return")
    )
)
```

**Required convention:** retain `BacktestEngine.load_panel()` as the only governed-data read, retain the pre-expression `symbol,date` sort, and retain the independent forward-return `.over("symbol")` behavior. The DSL compiler supplies only a `pl.Expr`; evaluation remains responsible for governed loading, warmup, finite-value filtering, rebalancing, and IC/RankIC aggregation.

**Integration cautions:**

- Do not pre-split into Python per-symbol or per-date dataframes; the project convention is one Polars expression pipeline.
- Do not move date-grouped Pearson/RankIC code into the DSL. `_correlation_series()` already correctly groups the final factor and returns by `date` (`lines 317-334`).
- A source edit here is only justified if the selected compiler interface needs explicit partition context. The simplest established shape is fixed `over("date")`/`over("symbol")` in the compiler plus the existing sort.

### `backend/tests/research/test_factor_dsl.py` — compiler boundary regression

**Relevant symbols:** `test_compiler_uses_only_governed_dependencies()` (lines 38-47).

**Existing test style to copy:**

```python
parsed = parse_factor("clip(log1p(close / prev_close), -1, 1) + rolling_mean(volume, 2)")
expression = parsed.compile()
frame = pl.DataFrame({...})
result = frame.select(expression.alias("factor"))
```

**Required test shape:** add a deterministic, ordered fixture with at least two symbols and at least two dates. Assert independently that:

- `rank(close)` and `zscore(close)` use only peer rows from the same `date`, not the adjacent date;
- `rolling_mean(close, 2)` starts each symbol's window afresh and cannot consume the prior symbol's final observation;
- output remains tied to the source row order after a deliberate `sort(["symbol", "date"])`.

**Integration cautions:** choose values that make an accidental full-frame rank and an accidental cross-symbol rolling value observably different; do not use symmetric values or one-row groups. This is a regression test for compiled expression semantics, not a parser-validity test.

### `backend/tests/research/test_factor_evaluation.py` — end-to-end governed evaluation regression

**Relevant symbols:** `StubBacktestEngine` (lines 16-25), `_panel()` (lines 34-44), `_config()` (lines 47-68), `test_evaluation_reports_distinct_ic_rankic_and_reproducible_evidence()` (lines 71-125).

**Existing service test contract:**

```python
engine = StubBacktestEngine(_panel())
service = FactorEvaluationService(engine, registry, EvaluationArtifactService(tmp_path / "app-data"))
result = service.evaluate(_config(revision.id))

assert result.status == "completed"
assert engine.calls == [{... "columns": ["symbol", "date", "close"], ...}]
```

**Required test shape:** create a factor revision for each stateful case (or a carefully chosen combined expression) and use a multi-symbol, multi-date governed panel. Exercise `service.evaluate()`, not just `pl.DataFrame.select()`, then assert distinct expected factor evidence/metric records that fail if evaluation partitions are omitted. Keep the explicit engine call, artifact, and config assertions already established in this module.

**Integration cautions:** preserve the stub's enforced selected-column behavior. This catches attempts to bypass the governed panel interface and ensures the new expression does not silently depend on undeclared columns.

### `backend/app/backtest/strategy.py` — source-local governed identity, if needed by the handoff

**Relevant symbols:** `StrategyBacktestResult` (lines 56-68), `StrategyBacktestService.run()` panel load (lines 139-154), formal simulation panel selection (lines 189-196), completed result construction (lines 273-284), `_config_to_dict()` (lines 643-670).

**Closest stable-data identity analog:** `FactorEvaluationService._manifest()` in `backend/app/research/evaluation.py:397-425`:

```python
schema = {name: str(dtype) for name, dtype in loaded.schema.items()}
source_reference = {
    "loader": "BacktestEngine.load_panel",
    "source_kind": "governed_enriched_parquet",
    "asset_type": resolved_config["asset_type"],
    "required_columns": required_columns,
    "schema": schema,
    "observed_start": str(observed_start),
    "observed_end": str(observed_end),
    "loaded_row_count": loaded.height,
}
encoded = json.dumps(source_reference, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

**Required convention:** obtain any fingerprint at the existing `load_panel()` boundary while the governed panel and its schema/date/symbol context are available. Pass only a normalized mapping onward; do not copy raw rows, add a secondary data store, or have the catalog reread Parquet.

**Integration cautions:**

- The `result.config` currently omits `asset_type` even though `StrategyBacktestConfig` carries it (`strategy.py:46` and `643-670`). Ensure a strategy manifest uses the actual resolved asset type, rather than the current `None` from `api/backtest.py:351`.
- The loaded panel includes warmup (and may include a full-mode forward buffer); document whether its fingerprint identifies the full governed source loaded versus only `sim_panel`. Align the saved observed range/row count with the chosen identity and retain requested execution dates separately.
- Keep `StrategyBacktestResult` compatible with `dataclasses.asdict()` and `dataclasses.replace()` used by the API. If a new result field is necessary, give it an immutable/empty-safe default so existing error/cancellation construction remains valid.

### `backend/app/api/backtest.py` — trusted strategy manifest assembly and handoff

**Relevant symbols:** `_strategy_version()` (lines 314-326), `_strategy_input_manifest()` (lines 344-356), `_finalize_strategy_experiment()` (lines 359-427), `strategy_run()` (lines 216-257), and `strategy_stream()` finalization path (lines 508-557).

**Current manifest shape:**

```python
def _strategy_input_manifest(result, strategy_id: str) -> dict:
    config = result.config if isinstance(result.config, dict) else {}
    stats = result.stats if isinstance(result.stats, dict) else {}
    symbols = config.get("symbols")
    return {
        "source": "governed_backtest_engine",
        "strategy_id": strategy_id,
        "asset_type": config.get("asset_type"),
        "resolved_symbols": sorted(symbols) if isinstance(symbols, list) else None,
        "start": config.get("start"),
        "end": config.get("end"),
        "row_count": stats.get("panel_rows"),
    }
```

**Required convention:** extend this server-created mapping with stable governed identity fields under the exact compatibility keys `revision` and/or `fingerprint`. Use a normalized, deterministic source-reference fingerprint from the strategy execution path; retain existing source/strategy/config rows. `_finalize_strategy_experiment()` must pass that mapping unchanged into `catalog.record_strategy_backtest()` (`lines 405-410`) for both synchronous and SSE completions.

**Integration cautions:**

- The API must never accept a client-provided manifest. `StrategyBacktestRequest` has `extra="forbid"` (`lines 187-213`), and finalization is deliberately server-produced (`lines 359-360`). Preserve both boundaries.
- Keep `_strategy_version()` server-resolved; factor/strategy identity and governed-data identity are independent immutable provenance fields.
- Do not generate a fresh random value as a revision/fingerprint. It must be reproducible for identical governed input and change when the governed input reference changes.
- Do not create an alternative comparison route or warning string: this handoff feeds the existing catalog comparison.

### `backend/app/research/catalog.py` — existing immutable snapshot and comparison warning

**Relevant symbols:** `ExperimentSnapshot` (lines 130-195), `record_strategy_backtest()` (lines 277-322), `_record()` (lines 356-400), `compare()` (lines 416-433), `_compatibility_warnings()` (lines 456-501).

**Existing immutable-copy boundary:**

```python
return self._record(
    originating_run_id=_required_text(str(getattr(result, "run_id", "")), "strategy run_id"),
    status=COMPARABLE_STATUS,
    validated=True,
    strategy_id=_required_text(strategy_id, "strategy_id"),
    strategy_version=_required_text(strategy_version, "strategy_version"),
    resolved_config=_mapping(getattr(result, "config", None), "strategy config"),
    input_manifest=_mapping(input_manifest, "input_manifest"),
    ...
)
```

**Existing warning to reuse verbatim:**

```python
(
    "governed data manifest revision/fingerprint differs",
    [
        (
            _value_at(manifest, ("revision",), ("data_revision",)),
            _value_at(manifest, ("fingerprint",), ("schema_fingerprint",)),
        )
        for manifest in manifests
    ],
),
```

**Required convention:** no new comparison warning is needed. Supply the existing recognized key(s) in the strategy manifest and preserve the exact warning text, field order, delta output, completed/validated retention gate, and immutable `_normalise()` persistence path.

**Integration cautions:**

- Do not make comparison infer a winner or hide a mismatch; this violates D-11.
- The comparison already considers factor `schema_fingerprint` but not factor `source_fingerprint`. If the strategy producer chooses a source-reference digest, place it in the recognized `fingerprint` key (or deliberately extend the existing fallback list with focused tests); leaving it only under a new key will not close the verification gap.
- No migration is required solely for nested immutable JSON fields: `ResearchRepository.create_experiment()` persists `input_manifest_json` atomically (`backend/app/research/repository.py:230-279`) and the schema already reserves `input_manifest_json` (`backend/app/operational/migrations.py:172-190`).

### `backend/tests/research/test_strategy_experiment_handoff.py` — trusted API provenance regression

**Relevant symbols:** `StubStrategyBacktestService.run()` (lines 21-45), `_client()` (lines 48-67), `test_sync_registered_strategy_handoff_uses_server_snapshot_only()` (lines 70-93), `test_failed_cancelled_and_sse_strategy_runs_never_bypass_handoff_gates()` (lines 96-114).

**Existing test pattern:** the stub produces a deterministic `StrategyBacktestResult`, then both `/api/backtest/strategy/run` and `/api/backtest/strategy/stream` are exercised with a minimal FastAPI app. This is the closest test for proving finalization creates the retained snapshot from server data only.

**Required test shape:** update the deterministic stub/result fixture to expose the selected stable governed-data identity as the production contract requires. Assert the retained strategy experiment has the expected `input_manifest["revision"]` and/or `input_manifest["fingerprint"]`; retain two otherwise comparable strategy records with differing governed-data identity; compare them and assert the existing warning appears. Keep the forged-request rejection and cancelled/failed/SSE retention-gate assertions.

**Integration cautions:** do not turn the test into a live Parquet/data-directory test. The current focused API fixture intentionally isolates registered-strategy handoff and is the correct deterministic boundary.

### `backend/tests/research/test_experiment_catalog.py` — immutable comparison regression

**Relevant symbols:** `_factor_package()` (lines 34-51), `test_registered_strategy_snapshot_and_comparison_expose_deltas_without_winner()` (lines 117-194).

**Existing comparison contract:**

```python
strategy_snapshot = catalog.record_strategy_backtest(
    strategy_result,
    strategy_id="registered-mean-reversion",
    strategy_version="v3",
    input_manifest={"revision": "governed-v1", "fingerprint": "0" * 64, "rows": 50},
    ...,
)
...
assert rendered["warnings"] == [
    "universe differs",
    "date window differs",
    "forward-return horizon differs",
    "governed data manifest revision/fingerprint differs",
]
```

**Required test shape:** add a narrowly scoped comparison using matching universe/window/horizon and two distinct trusted strategy manifest revisions/fingerprints. Assert the only compatibility warning is exactly `"governed data manifest revision/fingerprint differs"`, and retain assertions that no winner/ranking is emitted. This isolates the catalog’s existing behavior from unrelated mismatches.

**Integration cautions:** the current cross-subject factor-versus-strategy test correctly proves multiple deltas, but it cannot by itself prove strategy input revision change is what triggered the warning. The new fixture must vary only governed identity.

## Shared Patterns

### Polars partition semantics

**Sources:** `backend/app/indicators/pipeline.py:356-407`; `backend/app/backtest/engine.py:1636-1647`  
**Apply to:** stateful DSL compiler functions only.

- Sort time-series panels by `["symbol", "date"]` once at the governed evaluation boundary.
- Time-series state (`shift`, rolling aggregates) uses `.over("symbol")`.
- Cross-sectional rank/group work uses `.over("date")` or date grouping.
- Maintain a vectorized Polars pipeline; do not split frames into Python loops.

### Deterministic governed-data manifest

**Source:** `backend/app/research/evaluation.py:391-425`  
**Apply to:** registered-strategy experiment handoff.

- Form a source-reference mapping from governed-loader identity, asset type, required/schema fields, observed window, and counts.
- Serialize deterministically: `json.dumps(..., sort_keys=True, separators=(",", ":"))`.
- Use SHA-256 for the stable identifier and persist only manifest metadata, never market rows.
- Feed comparison one of its recognized revision/fingerprint keys.

### Immutable experiment records and warning behavior

**Sources:** `backend/app/research/catalog.py:277-322`, `356-400`, `456-501`; `backend/app/research/repository.py:230-279`  
**Apply to:** all strategy retention paths.

- Catalog input is created only from a server-issued completed `StrategyBacktestResult` and a server-created manifest.
- Persist the entire input manifest into existing JSON snapshot storage; do not mutate an existing record or add a parallel table/API.
- Preserve the existing completed/validated/retained comparison gate and warning text.

## Mandatory Gap Closure vs. Out of Scope

### Mandatory now

1. Update the fixed DSL compiler semantics so `rank`/`zscore` are date-partitioned and `rolling_mean` is symbol-partitioned, while preserving governed panel sorting and vectorized Polars evaluation.
2. Add deterministic multi-symbol/multi-date compiler and evaluation regressions that prove both partition boundaries cannot leak.
3. Make trusted strategy handoff carry a reproducible governed-data revision/fingerprint using the existing factor-manifest convention and recognized comparison keys.
4. Add focused strategy handoff/catalog tests proving a changed strategy governed-data identity emits **the existing** `governed data manifest revision/fingerprint differs` warning.

### Explicitly out of scope — Phase 4 sandboxing

Do **not** add arbitrary strategy source/code, AST/import/resource sandboxing, custom strategy execution, strategy mutation/evolution/promotion, agents, broker execution, another datastore, or a new backtest/router lifecycle. The only strategy work here is immutable provenance for the already registered server-side strategy contract, as locked by D-13 and listed as deferred in `02-CONTEXT.md`.

## No Analog Found

None for the required gap closure. The project already contains direct analogs for every required behavior. There is no existing global governed-data revision provider; use the evaluator’s deterministic manifest construction at the strategy’s existing governed `load_panel()` boundary rather than inventing a second persistence or data-access convention.

## Metadata

**Analogs searched:** `backend/app/research`, `backend/app/backtest`, `backend/app/api`, `backend/app/indicators`, `backend/tests/research`, `backend/tests/backtest`  
**Primary evidence files read:** 14  
**Pattern extraction date:** 2026-07-11
