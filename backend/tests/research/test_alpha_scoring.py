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