"""Phase 47 wave 1 — governed scoring identity seam (AF-REQ-05 SC1).

Covers plan 47-01:
- 47-01-01: transient exploratory FactorRevision binding for generated candidates
  (idempotent, catalog/similarity non-leakage, DSL-version fail-closed).
- 47-01-02: consolidated declared_fingerprints block on the chain frame.
- 47-01-03: factory factor fold scorer + chain-routing assertion guard.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from typing import Any


from app.research.factor_dsl import DSL_VERSION
from app.research.factor_registry import ALPHA_EXPLORATORY_KIND, FactorRegistry
from app.research.signal_chain import FactorSignalChain, SignalChainConfig

_FIXTURE_SYMBOLS = ("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ")


def _make_exploratory(
    registry: FactorRegistry,
    *,
    run_id: str = "run-a",
    candidate_digest: str = "dig-a",
    canonical_expression: str = "close",
    dsl_version: str = DSL_VERSION,
    candidate_id: str = "acand_a",
    step: int = 0,
):
    return registry.create_exploratory_revision(
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        canonical_expression=canonical_expression,
        dsl_version=dsl_version,
        fields=("close",),
        step=step,
    )


def _fixture_chain_config() -> SignalChainConfig:
    return SignalChainConfig(
        universe="fixture-a-share",
        symbols=_FIXTURE_SYMBOLS,
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        warmup_days=3,
        forward_return_horizon=1,
    )


# ----------------------------------------------------------------------
# 47-01-01 — transient exploratory revision binding
# ----------------------------------------------------------------------


def test_exploratory_revision_binds_candidate_to_evaluatable_identity(
    research_registry, stub_engine
) -> None:
    revision = _make_exploratory(research_registry)
    assert revision.provenance.get("kind") == ALPHA_EXPLORATORY_KIND
    assert revision.provenance.get("run_id") == "run-a"
    assert revision.provenance.get("candidate_id") == "acand_a"
    assert revision.provenance.get("candidate_digest") == "dig-a"
    assert revision.provenance.get("step") == 0

    # The exploratory revision id flows unchanged through the existing chain.
    chain = FactorSignalChain(stub_engine, research_registry, universe_resolver=None)
    frame = chain.compute(revision_id=revision.id, config=_fixture_chain_config())
    assert frame.revision_id == revision.id


def test_create_exploratory_revision_is_idempotent(research_registry) -> None:
    first = _make_exploratory(research_registry)
    second = _make_exploratory(research_registry)
    assert first.id == second.id


def test_find_exploratory_revision_returns_none_when_absent(research_registry) -> None:
    assert research_registry.find_exploratory_revision("missing-run", "missing-digest") is None


def test_find_exploratory_revision_locates_existing(research_registry) -> None:
    revision = _make_exploratory(research_registry)
    found = research_registry.find_exploratory_revision("run-a", "dig-a")
    assert found is not None
    assert found.id == revision.id


def test_exploratory_revision_excluded_from_similarity_pool(research_registry) -> None:
    """The admission similarity pool never contains an exploratory revision.

    ``_jaccard_duplicate`` returns 0.0 when the only registered revisions are
    exploratory, and ``discover_similar`` never surfaces one.
    """
    from app.research.admission import _jaccard_duplicate

    exploratory = _make_exploratory(research_registry)
    similarity = _jaccard_duplicate(
        research_registry, exploratory, exclude_revision_id=exploratory.id
    )
    assert similarity == 0.0
    candidates = research_registry.discover_similar(exploratory.canonical_expression)
    assert all(
        c.revision.provenance.get("kind") != ALPHA_EXPLORATORY_KIND for c in candidates
    )


def test_exploratory_revision_excluded_from_formal_catalog(research_registry) -> None:
    """``list_current`` (the formal catalog) never lists an alpha_exploratory revision."""
    _make_exploratory(research_registry)
    research_registry.create_factor(name="Momentum", expression="close")
    current = research_registry.list_current()
    assert all(r.provenance.get("kind") != ALPHA_EXPLORATORY_KIND for r in current)
    assert any(r.name == "Momentum" for r in current)


def test_exploratory_revision_dsl_version_mismatch_fails_closed(research_registry) -> None:
    """A candidate dsl_version that disagrees with the parsed expression raises; no revision minted."""
    with pytest.raises(ValueError, match="dsl_version"):
        research_registry.create_exploratory_revision(
            run_id="run-b",
            candidate_id="acand_b",
            candidate_digest="dig-b",
            canonical_expression="close",
            dsl_version="factor-dsl-v999",
            fields=("close",),
            step=0,
        )
    assert research_registry.find_exploratory_revision("run-b", "dig-b") is None


# ----------------------------------------------------------------------
# 47-01-02 — consolidated declared-fingerprint block
# ----------------------------------------------------------------------

_DECLARED_KEYS = ("panel", "membership", "source_field", "warmup", "missing_data", "signal")


class _PanelEngine:
    """Minimal governed-panel boundary mirroring ``StubBacktestEngine`` over a fixed panel."""

    def __init__(self, panel: pl.DataFrame) -> None:
        self.panel = panel

    def load_panel(self, symbols, start, end, *, columns, asset_type):  # type: ignore[no-untyped-def]
        return self.panel.select([c for c in columns if c in self.panel.columns])


def _rich_panel() -> pl.DataFrame:
    """Four-date, four-symbol panel with close + volume for fingerprint tests."""
    from datetime import timedelta

    first = date(2024, 1, 2)
    rows: list[dict[str, object]] = []
    for i, symbol in enumerate(_FIXTURE_SYMBOLS, start=1):
        for d in range(4):
            day = first + timedelta(days=d)
            rows.append(
                {"symbol": symbol, "date": day, "close": float(i + d), "volume": float((i + d) * 10)}
            )
    return pl.DataFrame(rows)


def _compute_declared(
    registry: FactorRegistry,
    engine,
    *,
    expression: str = "close",
    warmup_days: int = 3,
    horizon: int = 1,
    rebalance: str = "daily",
    end: date = date(2024, 1, 5),
):
    rev = registry.create_factor(name=f"f-{expression}-{warmup_days}-{horizon}-{rebalance}-{end}", expression=expression)
    chain = FactorSignalChain(engine, registry, universe_resolver=None)
    config = SignalChainConfig(
        universe="fixture-a-share",
        symbols=_FIXTURE_SYMBOLS,
        asset_type="stock",
        start=date(2024, 1, 2),
        end=end,
        warmup_days=warmup_days,
        forward_return_horizon=horizon,
        rebalance=rebalance,  # type: ignore[arg-type]
    )
    return chain.compute(revision_id=rev.id, config=config)


def test_declared_fingerprints_have_six_stable_keys(research_registry) -> None:
    engine = _PanelEngine(_rich_panel())
    first = _compute_declared(research_registry, engine)
    second = _compute_declared(research_registry, engine)
    block = first.declared_fingerprints
    assert set(block) == set(_DECLARED_KEYS)
    for key in _DECLARED_KEYS:
        assert isinstance(block[key], str) and len(block[key]) == 64
        assert block[key] == block[key].lower()
    # Two computes over identical inputs yield identical blocks.
    assert first.declared_fingerprints == second.declared_fingerprints


def test_declared_fingerprints_reuse_panel_and_membership(research_registry) -> None:
    engine = _PanelEngine(_rich_panel())
    frame = _compute_declared(research_registry, engine)
    assert frame.declared_fingerprints["panel"] == frame.panel_fingerprint
    assert frame.declared_fingerprints["membership"] == frame.resolved_universe["membership_fingerprint"]


def test_source_field_fingerprint_changes_with_required_fields(research_registry) -> None:
    engine = _PanelEngine(_rich_panel())
    close_block = _compute_declared(research_registry, engine, expression="close").declared_fingerprints
    volume_block = _compute_declared(research_registry, engine, expression="volume").declared_fingerprints
    assert close_block["source_field"] != volume_block["source_field"]


def test_warmup_fingerprint_changes_with_warmup_days(research_registry) -> None:
    engine = _PanelEngine(_rich_panel())
    a = _compute_declared(research_registry, engine, warmup_days=3).declared_fingerprints
    b = _compute_declared(research_registry, engine, warmup_days=5).declared_fingerprints
    assert a["warmup"] != b["warmup"]
    # Warmup days do not alter the governed panel or source read set.
    assert a["panel"] == b["panel"]
    assert a["source_field"] == b["source_field"]


def test_missing_data_fingerprint_changes_with_counts(research_registry) -> None:
    """A longer horizon drops more label-null dates from the finite counts -> different digest."""
    engine = _PanelEngine(_rich_panel())
    h1 = _compute_declared(research_registry, engine, horizon=1).declared_fingerprints
    h2 = _compute_declared(research_registry, engine, horizon=2).declared_fingerprints
    assert h1["missing_data"] != h2["missing_data"]
    # The signal/read-set/panel are unaffected by the horizon.
    assert h1["signal"] == h2["signal"]
    assert h1["source_field"] == h2["source_field"]


def test_signal_fingerprint_changes_with_expression_and_rebalance(research_registry) -> None:
    engine = _PanelEngine(_rich_panel())
    by_expr = _compute_declared(research_registry, engine, expression="close").declared_fingerprints
    by_other = _compute_declared(research_registry, engine, expression="volume").declared_fingerprints
    assert by_expr["signal"] != by_other["signal"]
    daily = _compute_declared(research_registry, engine, expression="close", rebalance="daily").declared_fingerprints
    weekly = _compute_declared(research_registry, engine, expression="close", rebalance="weekly").declared_fingerprints
    assert daily["signal"] != weekly["signal"]


def test_empty_frame_records_full_declared_fingerprints_block(research_registry) -> None:
    """IN-08: the empty-panel path still records all six fingerprints (never empty)."""
    empty_panel = pl.DataFrame(schema={"symbol": pl.Utf8, "date": pl.Date, "close": pl.Float64})
    engine = _PanelEngine(empty_panel)
    revision = research_registry.create_factor(name="EmptyClose", expression="close")
    chain = FactorSignalChain(engine, research_registry, universe_resolver=None)
    config = SignalChainConfig(
        universe="fixture-a-share",
        symbols=_FIXTURE_SYMBOLS,
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        warmup_days=3,
        forward_return_horizon=1,
    )
    frame = chain.compute(revision_id=revision.id, config=config)
    assert frame.frame.is_empty()
    assert set(frame.declared_fingerprints) == set(_DECLARED_KEYS)
    for key in _DECLARED_KEYS:
        assert frame.declared_fingerprints[key]  # present, non-empty



# ----------------------------------------------------------------------
# 47-01-03 — factory factor fold scorer + chain-routing guard
# ----------------------------------------------------------------------

from types import SimpleNamespace


def _compute_rich_frame(research_registry, *, expression="close", end=date(2024, 1, 5)):
    engine = _PanelEngine(_rich_panel())
    rev = research_registry.create_factor(
        name=f"scorer-{expression}-{end}", expression=expression
    )
    chain = FactorSignalChain(engine, research_registry, universe_resolver=None)
    config = SignalChainConfig(
        universe="fixture-a-share",
        symbols=_FIXTURE_SYMBOLS,
        asset_type="stock",
        start=date(2024, 1, 2),
        end=end,
        warmup_days=3,
        forward_return_horizon=1,
    )
    return chain.compute(revision_id=rev.id, config=config)


def test_factor_fold_scorer_produces_per_fold_ic_coverage_from_frame(research_registry) -> None:
    """The scorer yields factor-shaped per-fold stats from a chain frame, no backtest."""
    import inspect

    from app.research.alpha_scoring import factor_fold_scorer

    frame = _compute_rich_frame(research_registry)
    fold = SimpleNamespace(test_start=date(2024, 1, 2), test_end=date(2024, 1, 4), is_oos=False, fold_index=0)
    result = factor_fold_scorer(fold, frame=frame, membership=None)
    assert set(result) == {"test_stats", "membership_fingerprint", "declared_fingerprints"}
    test_stats = result["test_stats"]
    assert {"mean_ic", "rank_ic", "coverage", "effective_days"} <= set(test_stats)
    assert test_stats["effective_days"] == 3  # Jan 2/3/4 carry finite IC (Jan 5 label is null)
    assert test_stats["mean_ic"] is not None
    assert result["membership_fingerprint"] == frame.resolved_universe["membership_fingerprint"]
    assert result["declared_fingerprints"] == dict(frame.declared_fingerprints)
    # The scorer never references the reserved OOS fold (only selection folds score).
    assert "oos_fold" not in inspect.getsource(factor_fold_scorer)


def test_factor_fold_scorer_respects_test_window(research_registry) -> None:
    """A narrower test window yields fewer effective days."""
    from app.research.alpha_scoring import factor_fold_scorer

    frame = _compute_rich_frame(research_registry)
    full = factor_fold_scorer(
        SimpleNamespace(test_start=date(2024, 1, 2), test_end=date(2024, 1, 4)),
        frame=frame,
        membership=None,
    )
    narrow = factor_fold_scorer(
        SimpleNamespace(test_start=date(2024, 1, 2), test_end=date(2024, 1, 2)),
        frame=frame,
        membership=None,
    )
    assert narrow["test_stats"]["effective_days"] < full["test_stats"]["effective_days"]


def test_assert_all_scoring_through_chain_passes_today() -> None:
    from app.research.alpha_scoring import assert_all_scoring_through_chain

    assert_all_scoring_through_chain()  # must not raise against the live source


def test_routes_through_chain_detects_bypass() -> None:
    from app.research.alpha_scoring import _routes_through_chain

    def _bypassed() -> int:
        return 1

    def _routed() -> None:
        chain.compute(revision_id="r", config=None)  # type: ignore[arg-type]

    assert not _routes_through_chain(_bypassed)
    assert _routes_through_chain(_routed)


# ----------------------------------------------------------------------
# 47-02-02 — per-state exclusion counts + cost/turnover diagnostic
# ----------------------------------------------------------------------


def _dated_panel(*, dates, closes, volumes=None, expression_fields=("close",)):
    """Build a governed panel over ``dates`` x ``_FIXTURE_SYMBOLS``.

    ``closes``/``volumes`` map symbol -> tuple of per-date values (None = absent).
    """
    rows: list[dict[str, object]] = []
    for si, symbol in enumerate(_FIXTURE_SYMBOLS):
        for di, day in enumerate(dates):
            close = closes[symbol][di]
            if close is None:
                continue
            row: dict[str, object] = {"symbol": symbol, "date": day, "close": float(close)}
            if volumes is not None:
                vol = volumes[symbol][di]
                row["volume"] = float(vol) if vol is not None else 0.0
            rows.append(row)
    return pl.DataFrame(rows)


def _compute_with_panel(registry, panel, *, expression, start, end, warmup_days, horizon=1, rebalance="daily"):
    rev = registry.create_factor(name=f"p47-{expression}-{start}-{end}-{warmup_days}-{horizon}", expression=expression)
    chain = FactorSignalChain(_PanelEngine(panel), registry, universe_resolver=None)
    config = SignalChainConfig(
        universe="fixture-a-share",
        symbols=_FIXTURE_SYMBOLS,
        asset_type="stock",
        start=start,
        end=end,
        warmup_days=warmup_days,
        forward_return_horizon=horizon,
        rebalance=rebalance,  # type: ignore[arg-type]
    )
    return chain.compute(revision_id=rev.id, config=config)


_PRE_FILTER_KEYS = (
    "total", "finite", "non_finite", "suspended", "stale", "source_quality_excluded", "warmup_excluded",
)


def test_pre_filter_counts_carry_named_per_state_buckets(research_registry) -> None:
    """Each date's counts partition the cross-section: the five states sum to total."""
    panel = _dated_panel(
        dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        closes={s: (10.0, 11.0, 12.0) for s in _FIXTURE_SYMBOLS},
    )
    # start=2024-01-03, warmup_days=1 -> load_start=2024-01-02 is a warmup date;
    # horizon=1 drops 2024-01-04 (null forward return) from the finite window.
    frame = _compute_with_panel(
        research_registry, panel, expression="close",
        start=date(2024, 1, 3), end=date(2024, 1, 4), warmup_days=1, horizon=1,
    )
    counts = frame.resolved_universe["pre_filter_counts"]
    # Evaluation window keeps 2024-01-03 (forward-return finite); 2024-01-02 is warmup.
    assert set(counts) == {"2024-01-02", "2024-01-03"}
    for entry in counts.values():
        assert set(entry) == set(_PRE_FILTER_KEYS)
        assert (
            entry["finite"] + entry["non_finite"] + entry["suspended"]
            + entry["stale"] + entry["source_quality_excluded"] + entry["warmup_excluded"]
            == entry["total"]
        )
    assert counts["2024-01-03"] == {
        "total": 4, "finite": 4, "non_finite": 0, "suspended": 0,
        "stale": 0, "source_quality_excluded": 0, "warmup_excluded": 0,
    }
    assert counts["2024-01-02"]["warmup_excluded"] == 4
    assert counts["2024-01-02"]["finite"] == 0


def test_pre_filter_counts_name_non_finite_drops(research_registry) -> None:
    """A non-finite factor value (close/volume with volume=0) is named non_finite."""
    closes = {s: (10.0, 11.0, 12.0) for s in _FIXTURE_SYMBOLS}
    volumes = {s: (1.0, 1.0, 1.0) for s in _FIXTURE_SYMBOLS}
    volumes["000003.SZ"] = (1.0, 0.0, 1.0)  # volume=0 on the eval date -> _factor = inf
    panel = _dated_panel(
        dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        closes=closes, volumes=volumes,
    )
    frame = _compute_with_panel(
        research_registry, panel, expression="close / volume",
        start=date(2024, 1, 3), end=date(2024, 1, 4), warmup_days=0, horizon=1,
    )
    counts = frame.resolved_universe["pre_filter_counts"]
    entry = counts["2024-01-03"]
    assert entry["total"] == 4
    assert entry["finite"] == 3
    assert entry["non_finite"] == 1
    assert entry["finite"] + entry["non_finite"] == entry["total"]


def test_coverage_skips_warmup_dates(research_registry) -> None:
    """Coverage is measured over the evaluation window only (warmup excluded)."""
    from app.research.evaluation import FactorEvaluationService

    resolved = {"pre_filter_counts": {
        "2024-01-02": {"total": 4, "finite": 0, "non_finite": 0, "suspended": 0,
                       "stale": 0, "source_quality_excluded": 0, "warmup_excluded": 4},
        "2024-01-03": {"total": 4, "finite": 4, "non_finite": 0, "suspended": 0,
                       "stale": 0, "source_quality_excluded": 0, "warmup_excluded": 0},
    }}
    coverage = FactorEvaluationService._coverage(resolved)
    assert [row["date"] for row in coverage["coverage_series"]] == ["2024-01-03"]
    assert coverage["mean"] == 1.0


def test_missing_data_fingerprint_reflects_per_state_counts(research_registry) -> None:
    """The missing_data digest changes when the non_finite count changes (47-01 W4 resolved)."""
    base_closes = {s: (10.0, 11.0, 12.0) for s in _FIXTURE_SYMBOLS}
    clean_volumes = {s: (1.0, 1.0, 1.0) for s in _FIXTURE_SYMBOLS}
    clean = _dated_panel(
        dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        closes=base_closes, volumes=clean_volumes,
    )
    clean_frame = _compute_with_panel(
        research_registry, clean, expression="close / volume",
        start=date(2024, 1, 3), end=date(2024, 1, 4), warmup_days=0, horizon=1,
    )
    dirty_volumes = {s: (1.0, 1.0, 1.0) for s in _FIXTURE_SYMBOLS}
    dirty_volumes["000003.SZ"] = (1.0, 0.0, 1.0)
    dirty = _dated_panel(
        dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        closes=base_closes, volumes=dirty_volumes,
    )
    dirty_frame = _compute_with_panel(
        research_registry, dirty, expression="close / volume",
        start=date(2024, 1, 3), end=date(2024, 1, 4), warmup_days=0, horizon=1,
    )
    assert clean_frame.declared_fingerprints["source_field"] == dirty_frame.declared_fingerprints["source_field"]
    assert clean_frame.declared_fingerprints["missing_data"] != dirty_frame.declared_fingerprints["missing_data"]


# -- cost / turnover diagnostic (47-02 OQ4) --


def _long_short_frame() -> pl.DataFrame:
    """Two-date, four-symbol rebalance-dated frame with cross-sectional zscore."""
    z = {"000001.SZ": -1.161895003862225, "000002.SZ": -0.3872983346207417,
         "000003.SZ": 0.3872983346207417, "000004.SZ": 1.161895003862225}
    rows: list[dict[str, object]] = []
    for day in (date(2024, 1, 2), date(2024, 1, 3)):
        for symbol in _FIXTURE_SYMBOLS:
            rows.append({
                "symbol": symbol, "date": day,
                "_zscore": z[symbol], "_forward_return": 0.01 * z[symbol],
            })
    return pl.DataFrame(rows)


def test_cost_diagnostics_zero_cost_rate_yields_zero_drag() -> None:
    from app.research.evaluation import cost_diagnostics

    diag = cost_diagnostics(_long_short_frame(), costs={}, rebalance="daily")
    assert diag["cost_rate"] == 0.0
    assert diag["cost_drag"] == 0.0
    assert diag["net_long_short_return"] == pytest.approx(diag["raw_long_short_return"])
    assert diag["total_turnover"] > 0.0


def test_cost_diagnostics_positive_cost_reduces_net_return() -> None:
    from app.research.evaluation import cost_diagnostics

    costs = {"commission_pct": 0.0003, "stamp_tax_pct": 0.001, "slippage_bps": 5.0}
    diag = cost_diagnostics(_long_short_frame(), costs=costs, rebalance="daily")
    # commission*2 + stamp + slippage*2/1e4 = 0.0006 + 0.001 + 0.001 = 0.0026
    assert diag["cost_rate"] == pytest.approx(0.0026)
    assert diag["cost_drag"] > 0.0
    assert diag["net_long_short_return"] < diag["raw_long_short_return"]
    assert diag["net_long_short_return"] == pytest.approx(
        diag["raw_long_short_return"] - diag["cost_drag"]
    )
    assert {r["date"] for r in diag["turnover_per_rebalance"]} == {"2024-01-02", "2024-01-03"}


def test_cost_diagnostics_empty_frame_returns_empty_diagnostic() -> None:
    from app.research.evaluation import cost_diagnostics

    empty = pl.DataFrame({"symbol": [], "date": [], "_zscore": [], "_forward_return": []})
    diag = cost_diagnostics(empty, costs={"commission_pct": 0.0003}, rebalance="daily")
    assert diag["total_turnover"] == 0.0
    assert diag["cost_drag"] == 0.0
    assert diag["cost_rate"] == pytest.approx(0.0006)
    assert diag["turnover_per_rebalance"] == []


def test_cost_diagnostics_docstring_states_diagnostic_not_pnl() -> None:
    from app.research.evaluation import cost_diagnostics

    assert "DIAGNOSTIC" in cost_diagnostics.__doc__
    assert "NOT execution P&L" in cost_diagnostics.__doc__


def test_evaluate_populates_cost_diagnostics_on_result(tmp_path) -> None:
    """evaluate() wires the declared costs into the result's cost_diagnostics."""
    from app.research.artifacts import EvaluationArtifactService
    from app.research.evaluation import FactorEvaluationService, ResolvedEvaluationConfig
    from app.research.repository import ResearchRepository

    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    registry = FactorRegistry(repository)
    revision = registry.create_factor(name="Close", expression="close")
    closes = {
        "000001.SZ": (1.0, 1.5, 2.0), "000002.SZ": (2.0, 2.6, 4.0),
        "000003.SZ": (3.0, 3.6, 6.0), "000004.SZ": (4.0, 4.4, 8.0),
    }
    panel = _dated_panel(
        dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        closes=closes,
    )
    service = FactorEvaluationService(_PanelEngine(panel), registry, EvaluationArtifactService(tmp_path / "app-data"))
    config = ResolvedEvaluationConfig(
        factor_revision_id=revision.id,
        universe="fixture-a-share",
        symbols=_FIXTURE_SYMBOLS,
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        forward_return_horizon=1,
        rebalance="daily",
        missing_data_treatment="drop",
        warmup_treatment="exclude",
        warmup_days=0,
        n_groups=2,
        weight="equal",
        fees_pct=0.0002,
        slippage_bps=5.0,
        costs={"commission_pct": 0.0003, "stamp_tax_pct": 0.001, "slippage_bps": 5.0},
    )
    result = service.evaluate(config)
    assert result.status == "completed"
    assert result.cost_diagnostics["cost_rate"] == pytest.approx(0.0026)
    assert result.cost_diagnostics["cost_drag"] > 0.0


# ----------------------------------------------------------------------
# 47-02-03 — per-candidate immutable evidence binding + typed fold evidence
# ----------------------------------------------------------------------


def _run_manifest(*, seed: int = 42) -> dict:
    """A complete D-04 manifest for freezing an Alpha run in evidence tests."""
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {"name": "cn-a-share", "asset_type": "stock", "membership_fingerprint": "c" * 64},
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {"fingerprint": "d" * 64, "build_fingerprint": "e" * 64, "dependency_fingerprint": "f" * 64},
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": seed,
    }


def _make_run(repo, *, run_id: str = "run-evidence") -> str:
    from app.research.run_contract import freeze_input_snapshot

    snapshot = freeze_input_snapshot(manifest=_run_manifest(), created_at="2026-08-08T00:00:00+00:00")
    repo.create_alpha_run(
        run_id=run_id,
        principal="researcher@example.com",
        idempotency_key=f"idem-{run_id}",
        snapshot=snapshot,
        event_id=f"evt-{run_id}",
    )
    return run_id


def _attempt(run_id: str = "run-evidence", *, candidate_id: str = "cand-1", ordinal: int = 1, status: str = "generated", candidate_digest: str = "a" * 64):
    from app.research.run_contract import AlphaCandidateAttempt

    return AlphaCandidateAttempt(
        id=candidate_id, run_id=run_id, attempt_ordinal=ordinal,
        candidate_digest=candidate_digest, canonical_expression="close",
        ast_signature="ast-sig", shape_signature="shape-sig",
        dsl_version=DSL_VERSION, operation="generate", seed=0, step=0,
        status=status, reason={}, evidence_artifact_id=None, created_at="2026-08-08T00:00:00Z",
    )


def _result(*, status: str = "completed", revision_id: str = "rev-1") -> Any:
    from app.research.evaluation import FactorEvaluationResult

    diagnostics = ()
    if status in ("failed", "invalid"):
        diagnostics = (f"factor computation failed: {status}-boom",)
    return FactorEvaluationResult(
        evaluation_run_id="erun-1", status=status,
        factor_revision={"id": revision_id, "dsl_version": DSL_VERSION},
        resolved_config={"universe": "fixture-a-share"},
        cost_diagnostics={"cost_rate": 0.0026, "cost_drag": 0.001},
        diagnostics=diagnostics,
    )


def test_record_alpha_fold_evidence_inserts_candidate_keyed_row(research_repository) -> None:
    from app.research.alpha_scoring import record_selection_fold_evidence  # noqa: F401 (import sanity)

    row = research_repository.record_alpha_fold_evidence(
        run_id="run-x", candidate_digest="a" * 64, fold_index=0, is_oos=False,
        revision_id="rev-1", train_start=date(2024, 1, 1), train_end=date(2024, 1, 31),
        test_start=date(2024, 2, 1), test_end=date(2024, 2, 28),
        membership_fingerprint="b" * 64,
        declared_fingerprints={"panel": "p" * 64}, stats={"mean_ic": 0.03},
    )
    assert row["run_id"] == "run-x"
    assert row["candidate_digest"] == "a" * 64
    assert row["is_oos"] == 0
    assert row["stats"] == {"mean_ic": 0.03}
    assert row["declared_fingerprints"] == {"panel": "p" * 64}


def test_record_alpha_fold_evidence_unique_raises_on_duplicate(research_repository) -> None:
    kwargs = dict(
        run_id="run-x", candidate_digest="a" * 64, fold_index=0, is_oos=False,
        revision_id="rev-1", train_start=date(2024, 1, 1), train_end=date(2024, 1, 31),
        test_start=date(2024, 2, 1), test_end=date(2024, 2, 28),
        membership_fingerprint="b" * 64, declared_fingerprints={}, stats={},
    )
    research_repository.record_alpha_fold_evidence(**kwargs)
    with pytest.raises(ValueError, match="already recorded"):
        research_repository.record_alpha_fold_evidence(**kwargs)
    # The OOS slot (is_oos=1) is a distinct row under the same key.
    research_repository.record_alpha_fold_evidence(**{**kwargs, "is_oos": True})


def test_find_alpha_fold_evidence_is_idempotent_read(research_repository) -> None:
    assert research_repository.find_alpha_fold_evidence(
        run_id="run-x", candidate_digest="a" * 64, fold_index=0, is_oos=False
    ) is None
    research_repository.record_alpha_fold_evidence(
        run_id="run-x", candidate_digest="a" * 64, fold_index=2, is_oos=False,
        revision_id="rev-1", train_start=date(2024, 1, 1), train_end=date(2024, 1, 31),
        test_start=date(2024, 2, 1), test_end=date(2024, 2, 28),
        membership_fingerprint="b" * 64, declared_fingerprints={}, stats={"effective_days": 5},
    )
    found = research_repository.find_alpha_fold_evidence(
        run_id="run-x", candidate_digest="a" * 64, fold_index=2, is_oos=False
    )
    assert found is not None
    assert found["stats"] == {"effective_days": 5}
    # is_oos=1 for the same fold is a separate (absent) row.
    assert research_repository.find_alpha_fold_evidence(
        run_id="run-x", candidate_digest="a" * 64, fold_index=2, is_oos=True
    ) is None


def test_record_selection_fold_evidence_records_is_oos_zero_and_is_idempotent(
    research_registry, research_repository
) -> None:
    from app.research.alpha_scoring import record_selection_fold_evidence
    from types import SimpleNamespace

    closes = {
        "000001.SZ": (1.0, 1.5, 2.0), "000002.SZ": (2.0, 2.6, 4.0),
        "000003.SZ": (3.0, 3.6, 6.0), "000004.SZ": (4.0, 4.4, 8.0),
    }
    panel = _dated_panel(
        dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)], closes=closes,
    )
    rev = research_registry.create_factor(name="CloseSel", expression="close")
    frame = _compute_with_panel(
        research_registry, panel, expression="close",
        start=date(2024, 1, 2), end=date(2024, 1, 3), warmup_days=0, horizon=1,
    )
    folds = [
        (SimpleNamespace(fold_index=0, train_start=date(2024, 1, 1), train_end=date(2024, 1, 1),
                         test_start=date(2024, 1, 2), test_end=date(2024, 1, 2)), frame, None),
        (SimpleNamespace(fold_index=1, train_start=date(2024, 1, 1), train_end=date(2024, 1, 1),
                         test_start=date(2024, 1, 3), test_end=date(2024, 1, 3)), frame, None),
    ]
    recorded = record_selection_fold_evidence(
        repo=research_repository, run_id="run-x", candidate_digest="a" * 64,
        revision_id=rev.id, folds=folds,
    )
    assert len(recorded) == 2
    assert all(row["is_oos"] == 0 for row in recorded)
    # Reconnect/retry: a second pass records nothing new (idempotent skip).
    again = record_selection_fold_evidence(
        repo=research_repository, run_id="run-x", candidate_digest="a" * 64,
        revision_id=rev.id, folds=folds,
    )
    assert again == []


def test_record_candidate_evidence_completed_binds_artifact_and_keeps_status(
    research_registry, research_repository, tmp_path
) -> None:
    from app.research.alpha_scoring import record_candidate_evidence
    from app.research.artifacts import AlphaRunArtifactService

    run_id = _make_run(research_repository)
    revision = research_registry.create_factor(name="CloseEv", expression="close")
    artifact_service = AlphaRunArtifactService(tmp_path / "app-data")
    attempt = _attempt(run_id=run_id)
    result = _result(status="completed", revision_id=revision.id)

    recorded = record_candidate_evidence(
        repo=research_repository, artifact_service=artifact_service,
        attempt=attempt, revision=revision, result=result,
        declared_fingerprints={"panel": "p" * 64, "membership": "m" * 64},
        costs={"commission_pct": 0.0003, "stamp_tax_pct": 0.001, "slippage_bps": 5.0},
    )
    # A completed evaluation preserves the candidate's prior status (pending admission).
    assert recorded["status"] == "generated"
    assert recorded["evidence_artifact_id"] is not None
    # The evidence artifact is durably bound to the candidate's run.
    assert recorded["reason"]["evaluation"] == "completed"
    # The evidence artifact is durably bound to the candidate's run and verifies.
    rows = research_repository.list_candidates(run_id, artifact_service=artifact_service)
    assert any(r["evidence_artifact_id"] == recorded["evidence_artifact_id"] for r in rows)


def test_record_candidate_evidence_failed_records_terminal_reason(
    research_registry, research_repository, tmp_path
) -> None:
    from app.research.alpha_scoring import record_candidate_evidence
    from app.research.artifacts import AlphaRunArtifactService

    run_id = _make_run(research_repository, run_id="run-failed")
    revision = research_registry.create_factor(name="CloseFail", expression="close")
    artifact_service = AlphaRunArtifactService(tmp_path / "app-data")
    attempt = _attempt(run_id=run_id, candidate_id="cand-fail")
    result = _result(status="failed", revision_id=revision.id)

    recorded = record_candidate_evidence(
        repo=research_repository, artifact_service=artifact_service,
        attempt=attempt, revision=revision, result=result,
        declared_fingerprints={"panel": "p" * 64}, costs={},
    )
    assert recorded["status"] == "failed"
    assert "failed-boom" in recorded["reason"]["reason"]
    assert recorded["evidence_artifact_id"] is not None


def test_record_candidate_evidence_invalid_becomes_failed(
    research_registry, research_repository, tmp_path
) -> None:
    from app.research.alpha_scoring import record_candidate_evidence
    from app.research.artifacts import AlphaRunArtifactService

    run_id = _make_run(research_repository, run_id="run-invalid")
    revision = research_registry.create_factor(name="CloseInv", expression="close")
    artifact_service = AlphaRunArtifactService(tmp_path / "app-data")
    attempt = _attempt(run_id=run_id, candidate_id="cand-inv")
    result = _result(status="invalid", revision_id=revision.id)

    recorded = record_candidate_evidence(
        repo=research_repository, artifact_service=artifact_service,
        attempt=attempt, revision=revision, result=result,
        declared_fingerprints={"panel": "p" * 64}, costs={},
    )
    assert recorded["status"] == "failed"
    assert recorded["reason"]["evaluation"] == "invalid"


# ----------------------------------------------------------------------
# 47-03-01 — candidate-ledger-linked admission verdict (AF-REQ-08 SC4)
# ----------------------------------------------------------------------


def _seed7_panel(n_dates: int, *, seed: int = 7) -> pl.DataFrame:
    """Deterministic 8-symbol panel whose ``close`` factor clears every gate."""
    import numpy as np
    from datetime import timedelta

    rng = np.random.default_rng(seed)
    n_syms = 8
    prices = np.empty((n_dates, n_syms))
    for i in range(n_syms):
        walk = rng.normal(0, 0.02, n_dates)
        prices[:, i] = np.exp(np.cumsum(walk) + 0.001 * np.arange(n_dates))
    start = date(2024, 1, 2)
    rows = []
    for day_idx in range(n_dates):
        day = start + timedelta(days=day_idx)
        for symbol_idx in range(n_syms):
            rows.append({"symbol": f"S{symbol_idx:02d}", "date": day, "close": float(prices[day_idx, symbol_idx])})
    return pl.DataFrame(rows)


def test_record_candidate_admission_admitted_records_terminal_status_and_gate_trail(
    research_registry, research_repository
) -> None:
    from app.research.alpha_scoring import record_candidate_admission
    from tests.research.conftest import StubBacktestEngine
    from datetime import timedelta

    digest = "d" * 64
    run_id = _make_run(research_repository, run_id="run-admit")
    revision = research_registry.create_exploratory_revision(
        run_id=run_id, candidate_id="acand_admit", candidate_digest=digest,
        canonical_expression="close", dsl_version=DSL_VERSION, fields=("close",), step=0,
    )
    engine = StubBacktestEngine(_seed7_panel(60))
    attempt = _attempt(run_id=run_id, candidate_id="acand_admit_rec", candidate_digest=digest, ordinal=2)

    recorded = record_candidate_admission(
        repo=research_repository, registry=research_registry,
        attempt=attempt, revision=revision,
        universe="fixture-a-share", start=date(2024, 1, 2), end=date(2024, 1, 2) + timedelta(days=59),
        horizon=1, asset_type="stock", engine=engine,
    )
    assert recorded["status"] == "admitted"
    assert recorded["reason"]["verdict"] == "admitted"
    assert recorded["reason"]["failing_gate"] is None
    assert [g["gate"] for g in recorded["reason"]["gate_trail"]] == [
        "no_lookahead", "coverage", "no_label_leakage", "similarity_dedup", "train_ic", "val_ic",
    ]
    assert recorded["admission_verdict"]["verdict"] == "admitted"


def test_record_candidate_admission_rejected_records_failing_gate_and_trail(
    research_registry, research_repository
) -> None:
    from app.research.alpha_scoring import record_candidate_admission
    from tests.research.conftest import StubBacktestEngine

    digest = "e" * 64
    run_id = _make_run(research_repository, run_id="run-reject")
    revision = research_registry.create_exploratory_revision(
        run_id=run_id, candidate_id="acand_reject", candidate_digest=digest,
        canonical_expression="close", dsl_version=DSL_VERSION, fields=("close",), step=0,
    )
    # The 2-date fixture panel cannot clear the train_ic observation floor → clean rejection.
    engine = StubBacktestEngine(_seed7_panel(2))
    attempt = _attempt(run_id=run_id, candidate_id="acand_reject_rec", candidate_digest=digest, ordinal=2)

    recorded = record_candidate_admission(
        repo=research_repository, registry=research_registry,
        attempt=attempt, revision=revision,
        universe="fixture-a-share", start=date(2024, 1, 2), end=date(2024, 1, 3),
        horizon=1, asset_type="stock", engine=engine,
    )
    assert recorded["status"] == "rejected"
    assert recorded["reason"]["verdict"] == "rejected"
    assert recorded["reason"]["failing_gate"]  # names the gate that rejected
    assert recorded["reason"]["gate_trail"]  # full trail up to the failing gate


def test_record_candidate_admission_chain_failure_records_failed_not_rejection(
    research_registry, research_repository
) -> None:
    from app.research.alpha_scoring import record_candidate_admission
    from tests.research.conftest import StubBacktestEngine

    digest = "f" * 64
    run_id = _make_run(research_repository, run_id="run-fail-chain")
    revision = research_registry.create_exploratory_revision(
        run_id=run_id, candidate_id="acand_fail", candidate_digest=digest,
        canonical_expression="close", dsl_version=DSL_VERSION, fields=("close",), step=0,
    )
    # An empty governed panel → run_admission raises ValueError (no valid observations),
    # which is a terminal `failed` outcome, never a clean rejection or a zero score.
    engine = StubBacktestEngine(pl.DataFrame({"symbol": [], "date": [], "close": []}))
    attempt = _attempt(run_id=run_id, candidate_id="acand_fail_rec", candidate_digest=digest, ordinal=2)

    recorded = record_candidate_admission(
        repo=research_repository, registry=research_registry,
        attempt=attempt, revision=revision,
        universe="fixture-a-share", start=date(2024, 1, 2), end=date(2024, 1, 3),
        horizon=1, asset_type="stock", engine=engine,
    )
    assert recorded["status"] == "failed"
    assert recorded["reason"]["verdict"] == "failed"
    assert recorded["admission_verdict"] is None
    assert recorded["reason"]["error"]


def test_record_candidate_admission_links_verdict_to_ledger_by_revision(
    research_registry, research_repository
) -> None:
    from app.research.admission import get_verdict
    from app.research.alpha_scoring import record_candidate_admission
    from tests.research.conftest import StubBacktestEngine
    from datetime import timedelta

    digest = "1" * 64
    run_id = _make_run(research_repository, run_id="run-link")
    revision = research_registry.create_exploratory_revision(
        run_id=run_id, candidate_id="acand_link", candidate_digest=digest,
        canonical_expression="close", dsl_version=DSL_VERSION, fields=("close",), step=0,
    )
    engine = StubBacktestEngine(_seed7_panel(60))
    attempt = _attempt(run_id=run_id, candidate_id="acand_link_rec", candidate_digest=digest, ordinal=2)

    recorded = record_candidate_admission(
        repo=research_repository, registry=research_registry,
        attempt=attempt, revision=revision,
        universe="fixture-a-share", start=date(2024, 1, 2), end=date(2024, 1, 2) + timedelta(days=59),
        horizon=1, asset_type="stock", engine=engine,
    )
    # The verdict row joins the candidate ledger via the exploratory revision id.
    verdict = get_verdict(research_repository, revision.id)
    assert verdict is not None
    assert verdict["revision_id"] == revision.id
    assert verdict["verdict"] == "admitted"
    # The candidate attempt reason carries the same gate trail (the ledger side of the join).
    assert recorded["run_id"] == run_id
    assert recorded["candidate_digest"] == digest
    assert recorded["reason"]["gate_trail"] == verdict["gates"]


# ----------------------------------------------------------------------
# 47-03-02 — no-edit hardening guard (AF-REQ-08 SC4)
# ----------------------------------------------------------------------


def test_assert_admission_no_edit_passes_today() -> None:
    from app.research.alpha_scoring import assert_admission_no_edit

    assert_admission_no_edit()  # must not raise against the live source


def test_no_edit_signature_helper_detects_threshold_param() -> None:
    from app.research.alpha_scoring import _run_admission_signature_clean

    def _bad(*, train_min_mean_ic: float = 0.02) -> None:
        return None

    def _good(*, horizon: int = 1) -> None:
        return None

    assert not _run_admission_signature_clean(_bad)
    assert _run_admission_signature_clean(_good)


def test_no_edit_guard_detects_threshold_mutation_in_source() -> None:
    from app.research.alpha_scoring import _source_mutates_policy

    def _mutates() -> None:
        TRAIN_MIN_MEAN_IC = 0.5  # noqa: F841, N806 — uppercase constant on purpose

    def _clean() -> None:
        ...

    assert _source_mutates_policy(_mutates)
    assert not _source_mutates_policy(_clean)


def test_no_edit_guard_detects_direct_verdict_insert() -> None:
    from app.research.alpha_scoring import _source_inserts_verdict

    def _forges(repo) -> None:
        repo.insert_admission_verdict(verdict="admitted")  # forbidden direct write

    def _clean() -> None:
        return None  # no direct verdict insert

    assert _source_inserts_verdict(_forges)
    assert not _source_inserts_verdict(_clean)


# ----------------------------------------------------------------------
# 47-04-01 — exactly-once selection OOS evaluation (AF-REQ-09 SC5)
# ----------------------------------------------------------------------


def _trading_days(n: int, start: date = date(2024, 1, 2)) -> list[date]:
    """First ``n`` weekday dates from ``start`` (measured-calendar substitute)."""
    from datetime import timedelta

    days: list[date] = []
    cur = start
    while len(days) < n:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _oos_chain_setup(registry, *, n_dates: int = 18, expression: str = "close"):
    """Build a chain + resolver + revision over an ``n_dates`` panel for OOS tests."""
    from tests.research.conftest import StubBacktestEngine, StubUniverseResolver

    dates = _trading_days(n_dates)
    closes = {
        sym: tuple(float(10 + si + i + (i * (si + 1)) % 3) for i in range(n_dates))
        for si, sym in enumerate(_FIXTURE_SYMBOLS)
    }
    panel = _dated_panel(dates=dates, closes=closes)
    membership = pl.DataFrame({
        "symbol": [s for s in _FIXTURE_SYMBOLS for _ in range(n_dates)],
        "date": [d for _ in _FIXTURE_SYMBOLS for d in dates],
    })
    engine = StubBacktestEngine(panel)
    resolver = StubUniverseResolver(membership)
    chain = FactorSignalChain(engine=engine, registry=registry, universe_resolver=resolver)
    rev = registry.create_factor(name=f"CloseOos{n_dates}", expression=expression)
    return chain, resolver, rev, dates


def _oos_plan(dates: list[date], *, fold_index: int = 99, test_size: int | None = None,
              horizon: int = 1):
    """A minimal plan whose ``oos_fold`` test window is ``dates[4:4+test_size]``."""
    from types import SimpleNamespace

    size = test_size if test_size is not None else len(dates) - 4
    test_start = dates[4]
    test_end = dates[4 + size - 1]
    oos_fold = SimpleNamespace(
        fold_index=fold_index, is_oos=True,
        train_start=dates[0], train_end=dates[3],
        test_start=test_start, test_end=test_end,
        chain_config=SignalChainConfig(
            universe="fixture-a-share", symbols=(), asset_type="stock",
            start=dates[0], end=dates[-1], warmup_days=0,
            forward_return_horizon=horizon, rebalance="daily",
        ),
    )
    return SimpleNamespace(
        plan_id="plan-oos", universe="fixture-a-share", asset_type="stock",
        horizon=horizon, trading_dates=tuple(dates), oos_fold=oos_fold,
    )


def test_evaluate_selection_oos_records_exactly_once_is_oos_row(
    research_registry, research_repository
) -> None:
    from app.research.alpha_scoring import evaluate_selection_oos

    run_id = _make_run(research_repository, run_id="run-oos-1")
    chain, resolver, rev, dates = _oos_chain_setup(research_registry)
    plan = _oos_plan(dates)
    attempt = _attempt(run_id=run_id, candidate_digest="a" * 64)

    recorded = evaluate_selection_oos(
        repo=research_repository, chain=chain, resolver=resolver, plan=plan,
        attempt=attempt, revision=rev, objective="mean_ic",
    )
    assert recorded["is_oos"] == 1
    assert recorded["candidate_digest"] == "a" * 64
    assert recorded["fold_index"] == plan.oos_fold.fold_index
    assert "mean_ic" in recorded["stats"]

    # The outcome is labeled selection_oos on the candidate ledger.
    ledger = research_repository.list_candidates(run_id)
    assert any(c["status"] == "selection_oos" for c in ledger)


def test_evaluate_selection_oos_reconnect_returns_existing_row(
    research_registry, research_repository
) -> None:
    from app.research.alpha_scoring import evaluate_selection_oos

    run_id = _make_run(research_repository, run_id="run-oos-2")
    chain, resolver, rev, dates = _oos_chain_setup(research_registry)
    plan = _oos_plan(dates)
    attempt = _attempt(run_id=run_id, candidate_digest="b" * 64)

    first = evaluate_selection_oos(
        repo=research_repository, chain=chain, resolver=resolver, plan=plan,
        attempt=attempt, revision=rev,
    )
    # Reconnect/retry: returns the existing OOS row — no recompute, no duplicate.
    second = evaluate_selection_oos(
        repo=research_repository, chain=chain, resolver=resolver, plan=plan,
        attempt=attempt, revision=rev,
    )
    assert second["id"] == first["id"]
    # Exactly one is_oos=1 row for this candidate.
    rows = research_repository.list_alpha_fold_evidence(
        run_id=run_id, candidate_digest="b" * 64, is_oos=True,
    )
    assert len(rows) == 1
    # Exactly one selection_oos ledger fact (the reconnect did not duplicate it).
    ledger = [c for c in research_repository.list_candidates(run_id)
              if c["status"] == "selection_oos"]
    assert len(ledger) == 1


def test_selection_oos_unique_constraint_raises_on_second_insert(
    research_repository,
) -> None:
    """The DB-level UNIQUE is the exactly-once backstop: a second is_oos=1 INSERT raises."""
    kwargs = dict(
        run_id="run-uniq", candidate_digest="c" * 64, fold_index=99,
        revision_id="rev-1", train_start=date(2024, 1, 1), train_end=date(2024, 1, 31),
        test_start=date(2024, 2, 1), test_end=date(2024, 2, 28),
        membership_fingerprint="d" * 64, declared_fingerprints={}, stats={"mean_ic": 0.01},
    )
    research_repository.record_alpha_fold_evidence(is_oos=True, **kwargs)
    with pytest.raises(ValueError, match="already recorded"):
        research_repository.record_alpha_fold_evidence(is_oos=True, **kwargs)


def test_evaluate_selection_oos_failed_short_window_raises_before_slot(
    research_registry, research_repository
) -> None:
    """WR-02: an OOS with < 10 effective days raises BEFORE the once-only slot is written."""
    from app.research.alpha_scoring import evaluate_selection_oos

    run_id = _make_run(research_repository, run_id="run-oos-short")
    chain, resolver, rev, dates = _oos_chain_setup(research_registry)
    plan = _oos_plan(dates, test_size=3)  # effective_days < 10
    attempt = _attempt(run_id=run_id, candidate_digest="e" * 64)

    with pytest.raises(ValueError, match="effective days"):
        evaluate_selection_oos(
            repo=research_repository, chain=chain, resolver=resolver, plan=plan,
            attempt=attempt, revision=rev,
        )
    # The once-only slot was NOT burned by the failure.
    assert research_repository.list_alpha_fold_evidence(
        run_id=run_id, candidate_digest="e" * 64, is_oos=True,
    ) == []


def test_evaluate_selection_oos_missing_objective_raises_before_slot(
    research_registry, research_repository
) -> None:
    """WR-02: a missing objective metric raises BEFORE the once-only slot is written."""
    from app.research.alpha_scoring import evaluate_selection_oos

    run_id = _make_run(research_repository, run_id="run-oos-obj")
    chain, resolver, rev, dates = _oos_chain_setup(research_registry)
    plan = _oos_plan(dates)
    attempt = _attempt(run_id=run_id, candidate_digest="f" * 64)

    with pytest.raises(ValueError, match="no objective"):
        evaluate_selection_oos(
            repo=research_repository, chain=chain, resolver=resolver, plan=plan,
            attempt=attempt, revision=rev, objective="no_such_metric",
        )
    assert research_repository.list_alpha_fold_evidence(
        run_id=run_id, candidate_digest="f" * 64, is_oos=True,
    ) == []


def test_factor_fold_scorer_never_references_oos_fold_durable() -> None:
    """The selection-fold scorer stays OOS-inaccessible even after 47-04 lands."""
    import inspect
    from app.research.alpha_scoring import factor_fold_scorer

    assert "oos_fold" not in inspect.getsource(factor_fold_scorer)


# ----------------------------------------------------------------------
# 47-04-02 — deterministic winner selection (AF-REQ-09 SC5)
# ----------------------------------------------------------------------


def _seed_candidate(repo, run_id, *, digest, status="generated"):
    ordinal = max(
        (int(c["attempt_ordinal"]) for c in repo.list_candidates(run_id)), default=0
    ) + 1
    return repo.append_candidate_attempt(
        run_id=run_id, candidate_id=f"c-{digest[:8]}-{ordinal}",
        attempt_ordinal=ordinal, candidate_digest=digest,
        canonical_expression="close", ast_signature="ast", shape_signature="shape",
        dsl_version=DSL_VERSION, operation="generate", seed=0, step=0,
        status=status, reason={},
    )


def _seed_fold_evidence(repo, run_id, digest, fold_index, mean_ic, *, is_oos=False):
    return repo.record_alpha_fold_evidence(
        run_id=run_id, candidate_digest=digest, fold_index=fold_index, is_oos=is_oos,
        revision_id="rev-x", train_start=date(2024, 1, 1), train_end=date(2024, 1, 31),
        test_start=date(2024, 2, 1), test_end=date(2024, 2, 28),
        membership_fingerprint="0" * 64, declared_fingerprints={}, stats={"mean_ic": mean_ic},
    )


def test_select_winner_picks_higher_score_under_max_direction(research_repository) -> None:
    from app.research.alpha_scoring import select_winner

    run_id = _make_run(research_repository, run_id="run-sel-1")
    hi, lo = "1" * 64, "9" * 64
    for digest in (hi, lo):
        _seed_candidate(research_repository, run_id, digest=digest)
    for digest, score in ((hi, 0.05), (lo, 0.02)):
        for fi in (0, 1):
            _seed_fold_evidence(research_repository, run_id, digest, fi, score)

    winner = select_winner(repo=research_repository, run_id=run_id, objective="mean_ic", direction="max")
    assert winner.candidate_digest == hi


def test_select_winner_is_order_independent(research_repository) -> None:
    """Worker timing cannot change the winner: insertion order is irrelevant."""
    from app.research.alpha_scoring import select_winner

    run_id = _make_run(research_repository, run_id="run-sel-2")
    a, b = "a" * 64, "b" * 64
    for digest, score in ((a, 0.04), (b, 0.03)):
        _seed_candidate(research_repository, run_id, digest=digest)
        for fi in (0, 1):
            _seed_fold_evidence(research_repository, run_id, digest, fi, score)

    w1 = select_winner(repo=research_repository, run_id=run_id, objective="mean_ic", direction="max")
    # Re-selecting (a second call, simulating a different worker order) is identical.
    w2 = select_winner(repo=research_repository, run_id=run_id, objective="mean_ic", direction="max")
    assert w1.candidate_digest == w2.candidate_digest == a


def test_select_winner_tie_breaks_on_candidate_digest_lexicographic(research_repository) -> None:
    from app.research.alpha_scoring import select_winner

    run_id = _make_run(research_repository, run_id="run-sel-3")
    big, small = "f" * 64, "a" * 64  # equal scores; smaller digest must win
    for digest in (big, small):
        _seed_candidate(research_repository, run_id, digest=digest)
        for fi in (0, 1):
            _seed_fold_evidence(research_repository, run_id, digest, fi, 0.03)

    winner = select_winner(repo=research_repository, run_id=run_id, objective="mean_ic", direction="max")
    assert winner.candidate_digest == small


def test_select_winner_min_direction_picks_lower_score(research_repository) -> None:
    from app.research.alpha_scoring import select_winner

    run_id = _make_run(research_repository, run_id="run-sel-4")
    hi, lo = "1" * 64, "9" * 64
    for digest in (hi, lo):
        _seed_candidate(research_repository, run_id, digest=digest)
    for digest, score in ((hi, 0.05), (lo, 0.02)):
        for fi in (0, 1):
            _seed_fold_evidence(research_repository, run_id, digest, fi, score)

    winner = select_winner(repo=research_repository, run_id=run_id, objective="mean_ic", direction="min")
    assert winner.candidate_digest == lo


def test_select_winner_excludes_candidate_with_incomplete_evidence(research_repository) -> None:
    """A candidate missing a fold is excluded (fail closed), never a partial winner."""
    from app.research.alpha_scoring import select_winner

    run_id = _make_run(research_repository, run_id="run-sel-5")
    complete, partial = "c" * 64, "d" * 64
    for digest in (complete, partial):
        _seed_candidate(research_repository, run_id, digest=digest)
    # `complete` has both folds; `partial` has only fold 0 (higher score).
    for fi in (0, 1):
        _seed_fold_evidence(research_repository, run_id, complete, fi, 0.02)
    _seed_fold_evidence(research_repository, run_id, partial, 0, 0.99)

    winner = select_winner(repo=research_repository, run_id=run_id, objective="mean_ic", direction="max")
    assert winner.candidate_digest == complete


def test_select_winner_raises_when_no_candidate_is_complete(research_repository) -> None:
    """No candidate covers the full fold set → fail closed (raise)."""
    from app.research.alpha_scoring import select_winner

    run_id = _make_run(research_repository, run_id="run-sel-6")
    a, b = "a" * 64, "b" * 64
    _seed_candidate(research_repository, run_id, digest=a)
    _seed_candidate(research_repository, run_id, digest=b)
    # Disjoint folds: union is {0,1} but neither candidate covers both.
    _seed_fold_evidence(research_repository, run_id, a, 0, 0.02)
    _seed_fold_evidence(research_repository, run_id, b, 1, 0.02)

    with pytest.raises(ValueError, match="no candidate with complete"):
        select_winner(repo=research_repository, run_id=run_id, objective="mean_ic", direction="max")


def test_only_winner_proceeds_to_selection_oos(research_registry, research_repository) -> None:
    """End-to-end: select_winner then evaluate_selection_oos for the winner only."""
    from app.research.alpha_scoring import evaluate_selection_oos, select_winner

    run_id = _make_run(research_repository, run_id="run-e2e")
    chain, resolver, rev, dates = _oos_chain_setup(research_registry)
    plan = _oos_plan(dates)
    winner_digest, loser_digest = "a" * 64, "b" * 64
    for digest, score in ((winner_digest, 0.05), (loser_digest, 0.01)):
        _seed_candidate(research_repository, run_id, digest=digest)
        for fi in (0, 1):
            _seed_fold_evidence(research_repository, run_id, digest, fi, score)

    winner = select_winner(repo=research_repository, run_id=run_id, objective="mean_ic", direction="max")
    assert winner.candidate_digest == winner_digest

    recorded = evaluate_selection_oos(
        repo=research_repository, chain=chain, resolver=resolver, plan=plan,
        attempt=winner, revision=rev, objective="mean_ic",
    )
    assert recorded["is_oos"] == 1
    assert recorded["candidate_digest"] == winner_digest
    # The loser never consumed the OOS fold.
    assert research_repository.list_alpha_fold_evidence(
        run_id=run_id, candidate_digest=loser_digest, is_oos=True,
    ) == []