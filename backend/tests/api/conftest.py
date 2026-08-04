"""Shared TestClient + app-state injection fixtures for Phase 15 panel tests.

The panels read from ResearchRepository + PortfolioRepository over a migrated
tmp_path operational.db.  We build a minimal FastAPI app with ONLY the panel
routers (no production auth middleware, no lifespan side-effects) and inject
the repositories into app.state.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import portfolio_panels, research_panels, walkforward_sse
from app.portfolio.repository import PortfolioRepository
from app.research.repository import ResearchRepository


@pytest.fixture
def panel_db(tmp_path: Path) -> Path:
    """A fresh migrated operational.db path for panel tests."""
    return tmp_path / "operational.db"


@pytest.fixture
def portfolio_repository(panel_db: Path) -> PortfolioRepository:
    return PortfolioRepository(panel_db)


@pytest.fixture
def research_repository(panel_db: Path) -> ResearchRepository:
    return ResearchRepository(panel_db)


@pytest.fixture
def panel_client(
    portfolio_repository: PortfolioRepository,
    research_repository: ResearchRepository,
) -> TestClient:
    """Minimal FastAPI app with panel routers + repositories injected."""
    app = FastAPI()
    app.state.portfolio_repository = portfolio_repository
    app.state.research_repository = research_repository
    app.include_router(research_panels.router)
    app.include_router(portfolio_panels.router)
    app.include_router(walkforward_sse.router)
    yield TestClient(app)
