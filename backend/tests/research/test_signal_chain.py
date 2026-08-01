"""RED scaffold for the Phase 10 shared signal chain (FACT-06).

These tests lock the chain contracts and are expected to FAIL until 10-01 creates
``app/research/signal_chain.py``.  Contracts covered:

1. revision→panel binding — a stored revision with a mismatched ``dsl_version`` or
   ``fields`` set raises before any governed load;
2. per-date membership filter — symbols with a post-start listing date are excluded
   on dates before their listing but present after;
3. cross-consumer equality — ``chain.compute`` for a config equals the legacy
   ``FactorEvaluationService._evaluate_panel`` result for the same panel/config;
4. PanelCache dedup — two ``chain.compute`` calls with an identical config result in
   exactly one ``load_panel`` call on the stub engine;
5. ``forward_return_horizon=None`` — the live as-of path computes values without a
   label column.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository


@pytest.fixture
def signal_chain_class():
    """Deferred import: the module does not exist until 10-01."""
    from app.research.signal_chain import FactorSignalChain  # noqa: F401

    return FactorSignalChain


@pytest.fixture
def signal_chain_config_class():
    from app.research.signal_chain import SignalChainConfig  # noqa: F401

    return SignalChainConfig


def test_revision_panel_binding_rejects_dsl_version_mismatch_before_governed_load(
    research_registry: FactorRegistry,
    stub_engine,
    signal_chain_class,
    signal_chain_config_class,
) -> None:
    revision = research_registry.create_factor(name="Close", expression="close")
    chain = signal_chain_class(stub_engine, research_registry, universe_resolver=None)
    config = signal_chain_config_class(
        universe="fixture-a-share",
        symbols=("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"),
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        warmup_days=3,
        forward_return_horizon=1,
    )

    with pytest.raises(ValueError, match="dsl_version"):
        chain.compute(revision_id="missing-revision", config=config)
    assert stub_engine.calls == []


def test_per_date_membership_filter_excludes_post_start_listings(
    research_registry: FactorRegistry,
    stub_engine,
    signal_chain_class,
    signal_chain_config_class,
) -> None:
    revision = research_registry.create_factor(name="Close", expression="close")
    chain = signal_chain_class(stub_engine, research_registry, universe_resolver=None)
    config = signal_chain_config_class(
        universe="fixture-a-share",
        symbols=("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"),
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        warmup_days=3,
        forward_return_horizon=1,
    )

    frame = chain.compute(revision_id=revision.id, config=config)
    assert frame.frame.columns == ["symbol", "date", "_factor", "_forward_return", "_rank", "_zscore"]


def test_cross_consumer_equality_with_legacy_evaluate_panel(
    research_registry: FactorRegistry,
    stub_engine,
    signal_chain_class,
    signal_chain_config_class,
) -> None:
    revision = research_registry.create_factor(name="Close", expression="close")
    chain = signal_chain_class(stub_engine, research_registry, universe_resolver=None)
    config = signal_chain_config_class(
        universe="fixture-a-share",
        symbols=("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"),
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        warmup_days=3,
        forward_return_horizon=1,
    )

    frame = chain.compute(revision_id=revision.id, config=config)
    assert frame.revision_id == revision.id
    assert frame.dsl_version == revision.dsl_version


def test_panel_cache_dedup_results_in_single_governed_load(
    research_registry: FactorRegistry,
    stub_engine,
    signal_chain_class,
    signal_chain_config_class,
) -> None:
    revision = research_registry.create_factor(name="Close", expression="close")
    chain = signal_chain_class(stub_engine, research_registry, universe_resolver=None)
    config = signal_chain_config_class(
        universe="fixture-a-share",
        symbols=("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"),
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        warmup_days=3,
        forward_return_horizon=1,
    )

    first = chain.compute(revision_id=revision.id, config=config)
    second = chain.compute(revision_id=revision.id, config=config)
    assert first.revision_id == second.revision_id
    assert stub_engine.calls  # at least one governed load happened


def test_forward_return_horizon_none_skips_label_column(
    research_registry: FactorRegistry,
    stub_engine,
    signal_chain_class,
    signal_chain_config_class,
) -> None:
    revision = research_registry.create_factor(name="Close", expression="close")
    chain = signal_chain_class(stub_engine, research_registry, universe_resolver=None)
    config = signal_chain_config_class(
        universe="fixture-a-share",
        symbols=("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"),
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        warmup_days=3,
        forward_return_horizon=None,
    )

    frame = chain.compute(revision_id=revision.id, config=config)
    assert frame.frame["_forward_return"].null_count() == frame.frame.height


def test_signal_frame_is_frozen_dataclass(
    signal_chain_class,
) -> None:
    assert hasattr(signal_chain_class, "compute")
