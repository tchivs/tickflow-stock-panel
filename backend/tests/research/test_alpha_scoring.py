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
