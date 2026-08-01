"""PortfolioRepository seam contract (11-02 deliverable — GREEN).

Verifies the Wave 0 seam: the shared operational DB is migrated on construction,
``migrate()`` is idempotent, and the portfolio_optimization_runs table is
present for 11-01's append-only methods. The append-only method-level tests live
in test_repository.py (RED until 11-01).
"""
from __future__ import annotations

from pathlib import Path

from app.portfolio.repository import PortfolioRepository


def test_constructor_migrates_and_exposes_runs_table(tmp_path: Path) -> None:
    repository = PortfolioRepository(tmp_path / "operational.db")
    with repository._connection() as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'portfolio_optimization_runs'"
        ).fetchone()
    assert row is not None


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    repository = PortfolioRepository(tmp_path / "operational.db")
    repository.migrate()  # second application is a no-op
    with repository._connection() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        assert version > 0


def test_runs_table_has_append_only_guards(tmp_path: Path) -> None:
    from app.operational import migrations

    repository = PortfolioRepository(tmp_path / "operational.db")
    with repository._connection() as connection:
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND name LIKE 'portfolio_optimization_runs_%'"
            )
        }
    assert {
        "portfolio_optimization_runs_no_update",
        "portfolio_optimization_runs_no_delete",
    }.issubset(triggers)
    assert migrations.MIGRATIONS  # smoke: module importable
