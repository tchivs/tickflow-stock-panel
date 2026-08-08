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
