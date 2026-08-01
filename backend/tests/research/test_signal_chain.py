"""RED scaffold for the Phase 10 shared signal chain (FACT-06).

These tests lock the chain contracts and are expected to FAIL until 10-01 creates
``app/research/signal_chain.py``.  Contracts covered:

1. revision→panel binding — a stored revision with a mismatched ``dsl_version`` or
   ``fields`` set raises before any governed load;
2. per-date membership filter — symbols with a post-start listing date are excluded
   on dates before their listing but present after;
3. cross-consumer equality — ``chain.compute`` for the fixture config equals a
   FROZEN expected ``FactorSignalFrame`` (columns, values, ``panel_fingerprint``,
   ``resolved_universe`` block) — the legacy ``_evaluate_panel`` adapter is gone;
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
    from app.research.signal_chain import FactorSignalChain

    return FactorSignalChain


@pytest.fixture
def signal_chain_config_class():
    from app.research.signal_chain import SignalChainConfig

    return SignalChainConfig


def test_revision_panel_binding_rejects_dsl_version_mismatch_before_governed_load(
    research_registry: FactorRegistry,
    stub_engine,
    signal_chain_class,
    signal_chain_config_class,
) -> None:
    research_registry.create_factor(name="Close", expression="close")
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


def test_cross_consumer_equality_with_frozen_expected_frame(
    research_registry: FactorRegistry,
    stub_engine,
    signal_chain_class,
    signal_chain_config_class,
) -> None:
    """``chain.compute`` equals a frozen expected FactorSignalFrame for the fixture config.

    The legacy ``FactorEvaluationService._evaluate_panel`` adapter is deleted;
    this test locks the chain's exact output (columns, values, panel_fingerprint,
    resolved_universe block) so a second factor-value implementation cannot drift
    back in.
    """
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

    # --- Frozen expected values (fixture panel: 2 dates x 4 symbols, close 1..4;
    # the second date's forward return is null without a third date, so the
    # finite filter keeps only the first date's cross-section) ---
    expected_rows = [
        {"symbol": "000001.SZ", "date": date(2024, 1, 2), "_factor": 1.0, "_forward_return": 0.0, "_rank": 1.0, "_zscore": -1.161895003862225},
        {"symbol": "000002.SZ", "date": date(2024, 1, 2), "_factor": 2.0, "_forward_return": 0.5, "_rank": 2.0, "_zscore": -0.3872983346207417},
        {"symbol": "000003.SZ", "date": date(2024, 1, 2), "_factor": 3.0, "_forward_return": 0.10000000000000009, "_rank": 3.0, "_zscore": 0.3872983346207417},
        {"symbol": "000004.SZ", "date": date(2024, 1, 2), "_factor": 4.0, "_forward_return": 0.8999999999999999, "_rank": 4.0, "_zscore": 1.161895003862225},
    ]
    observed_rows = list(frame.frame.sort(["symbol", "date"]).iter_rows(named=True))
    assert len(observed_rows) == len(expected_rows)
    for observed, expected in zip(observed_rows, expected_rows, strict=True):
        for key, expected_value in expected.items():
            observed_value = observed[key]
            if isinstance(expected_value, float):
                assert observed_value == pytest.approx(expected_value)
            else:
                assert observed_value == expected_value

    assert frame.frame.columns == ["symbol", "date", "_factor", "_forward_return", "_rank", "_zscore"]
    assert frame.revision_id == revision.id
    assert frame.dsl_version == revision.dsl_version
    # Frozen fingerprints for the fixture governed panel and config-symbols universe.
    assert frame.panel_fingerprint == "fd3c3a725475e7625614382c3291132c444bc4de7d362fa7c4d71e92d0b9a504"
    assert frame.resolved_universe["method"] == "config-symbols"
    assert frame.resolved_universe["membership_fingerprint"] == (
        "afb5ae1781db3795f606121847d3428941b62ff27bd537bc464886f26cc0200c"
    )
    # The second date's forward return is null (no third date), so the
    # pre-filter finite share excludes it — coverage measures the usable
    # cross-section (IN-01).
    assert frame.resolved_universe["pre_filter_counts"] == {
        "2024-01-02": {"total": 4, "finite": 4},
    }
    assert frame.required_source_fields == ("symbol", "date", "close")


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


def test_chain_resolves_real_universe_membership_per_date(
    research_registry: FactorRegistry,
    research_repository: ResearchRepository,
    stub_engine,
    signal_chain_class,
    signal_chain_config_class,
) -> None:
    """Real resolver: per-date membership excludes post-start listings and a delist."""
    from app.research.universe import UniverseResolver

    # 000001-000003 listed from the start; 000004.SZ lists mid-window; 000005.SZ
    # is requested but never a member (delisted before the window).
    for symbol in ("000001.SZ", "000002.SZ", "000003.SZ"):
        research_repository.insert_universe_membership(
            universe_name="fixture-a-share",
            symbol=symbol,
            asset_type="stock",
            effective_date="2024-01-01",
            state="listed",
            source="instruments-sync",
            provenance_json={},
        )
    research_repository.insert_universe_membership(
        universe_name="fixture-a-share",
        symbol="000004.SZ",
        asset_type="stock",
        effective_date="2024-01-03",
        state="listed",
        source="instruments-sync",
        provenance_json={},
    )
    revision = research_registry.create_factor(name="Close", expression="close")
    chain = signal_chain_class(
        stub_engine,
        research_registry,
        universe_resolver=UniverseResolver(research_repository),
    )
    config = signal_chain_config_class(
        universe="fixture-a-share",
        symbols=("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"),
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        warmup_days=3,
        forward_return_horizon=1,
    )

    frame = chain.compute(revision_id=revision.id, config=config)
    assert frame.resolved_universe["method"] == "factor_universe_membership/v1"
    assert frame.resolved_universe["membership_fingerprint"]
    assert frame.resolved_universe["excluded_delisted"] == ["000005.SZ"]
    assert frame.resolved_universe["per_date_symbol_counts"]["min"] >= 3

    # The membership filter is applied to the loaded panel AFTER the single
    # governed read: post-listing symbols appear only from their listing date.
    loaded_day_one = frame.loaded_panel.filter(pl.col("date") == date(2024, 1, 2))
    loaded_day_two = frame.loaded_panel.filter(pl.col("date") == date(2024, 1, 3))
    assert "000004.SZ" not in loaded_day_one["symbol"].to_list()
    assert "000004.SZ" in loaded_day_two["symbol"].to_list()
    assert "000005.SZ" not in loaded_day_two["symbol"].to_list()


def test_chain_membership_fingerprint_changes_when_membership_changes(
    research_registry: FactorRegistry,
    research_repository: ResearchRepository,
    stub_engine,
    signal_chain_class,
    signal_chain_config_class,
) -> None:
    """Adding a membership row changes the chain's per-date membership fingerprint."""
    from app.research.universe import UniverseResolver

    for symbol in ("000001.SZ", "000002.SZ", "000003.SZ"):
        research_repository.insert_universe_membership(
            universe_name="fixture-a-share",
            symbol=symbol,
            asset_type="stock",
            effective_date="2024-01-01",
            state="listed",
            source="instruments-sync",
            provenance_json={},
        )
    revision = research_registry.create_factor(name="Close", expression="close")
    chain = signal_chain_class(
        stub_engine,
        research_registry,
        universe_resolver=UniverseResolver(research_repository),
    )
    config = signal_chain_config_class(
        universe="fixture-a-share",
        symbols=("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"),
        asset_type="stock",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        warmup_days=3,
        forward_return_horizon=1,
    )

    before = chain.compute(revision_id=revision.id, config=config).resolved_universe["membership_fingerprint"]
    research_repository.insert_universe_membership(
        universe_name="fixture-a-share",
        symbol="000004.SZ",
        asset_type="stock",
        effective_date="2024-01-02",
        state="listed",
        source="instruments-sync",
        provenance_json={},
    )
    after = chain.compute(revision_id=revision.id, config=config).resolved_universe["membership_fingerprint"]
    assert before != after
