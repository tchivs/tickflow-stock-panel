from __future__ import annotations

from pathlib import Path
import sqlite3

from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository


def _registry(database_path: Path) -> FactorRegistry:
    repository = ResearchRepository(database_path)
    repository.migrate()
    return FactorRegistry(repository)


def test_fresh_migration_reserves_prediction_signal_references(tmp_path: Path) -> None:
    database_path = tmp_path / "operational.db"
    _registry(database_path)
    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(research_experiments)")}

    assert "prediction_signal_json" in columns


def test_factor_revisions_are_insert_only_and_history_is_preserved(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "operational.db")
    first = registry.create_factor(
        name="Close premium",
        expression="close / ma20",
        description="Price relative to moving average",
        hypothesis="Premium mean reverts",
        provenance={"author": "researcher"},
    )
    original = first.as_dict()

    second = registry.revise_factor(first.factor_id, expression="close / ma60")

    assert second.factor_id == first.factor_id
    assert second.id != first.id
    assert second.revision_number == 2
    assert registry.get_revision(first.id).as_dict() == original  # type: ignore[union-attr]
    assert [revision.id for revision in registry.list_history(first.factor_id)] == [first.id, second.id]


def test_saved_factor_contains_required_immutable_provenance(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "operational.db")

    factor = registry.create_factor(
        name="Momentum",
        expression="momentum_20d + rank(volume)",
        description="Volume-supported momentum",
        hypothesis="Persisting momentum is investable",
        provenance={"source": "manual", "ticket": "R-42"},
    )

    assert factor.name == "Momentum"
    assert factor.description == "Volume-supported momentum"
    assert factor.hypothesis == "Persisting momentum is investable"
    assert factor.canonical_expression == "momentum_20d + rank(volume)"
    assert factor.dsl_version == "factor-dsl-v1"
    assert factor.provenance == {"source": "manual", "ticket": "R-42"}
    assert factor.created_at


def test_similarity_is_deterministic_explained_and_never_blocks_save(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "operational.db")
    exact = registry.create_factor(name="Exact", expression="close + ma20")
    close_ma30 = registry.create_factor(name="Close 30", expression="close + ma30")
    close_only = registry.create_factor(name="Close 60", expression="close + ma60")
    volume = registry.create_factor(name="Volume", expression="rank(volume)")

    first = registry.discover_similar("(close + ma20)")
    second = registry.discover_similar("close+ma20")

    assert [candidate.revision.id for candidate in first] == [candidate.revision.id for candidate in second]
    assert first[0].revision.id == exact.id
    assert first[0].exact_structural_match is True
    assert first[0].score == 1.0
    assert first[0].reason == "exact AST structural signature"
    assert all(candidate.reason for candidate in first)
    assert all(candidate.as_dict()["components"] for candidate in first)
    assert {candidate.revision.id for candidate in first} == {exact.id, close_ma30.id, close_only.id, volume.id}
    assert [candidate.revision.id for candidate in first[1:3]] == [close_ma30.id, close_only.id]

    saved = registry.create_factor(name="Allowed duplicate", expression="close + ma20")
    assert saved.id != exact.id
