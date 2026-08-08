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

from app.api import portfolio_panels, research_alpha, research_panels, walkforward_sse
from app.research.repository import ResearchRepository
from app.research.run_service import ResearchRunService
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


class DeterministicClock:
    """A controllable monotonic clock for reproducible Alpha run timestamps."""

    def __init__(self, start: str = "2026-08-08T00:00:00+00:00") -> None:
        from datetime import datetime

        self._moment = datetime.fromisoformat(start)

    def now_iso(self) -> str:
        return self._moment.isoformat()

    def advance(self, *, seconds: int = 0) -> str:
        from datetime import timedelta

        self._moment = self._moment + timedelta(seconds=seconds if seconds > 0 else 1)
        return self.now_iso()


def alpha_manifest(*, seed: int = 42) -> dict:
    """A complete D-04 manifest with every required group non-empty."""
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
        "code_manifest": {
            "fingerprint": "d" * 64,
            "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {
            "fingerprint": "g" * 64,
            "partition_fingerprint": "h" * 64,
        },
        "seed": seed,
    }


@pytest.fixture
def deterministic_clock() -> DeterministicClock:
    return DeterministicClock()


@pytest.fixture
def alpha_client(
    panel_db: Path,
    deterministic_clock: DeterministicClock,
    tmp_path: Path,
) -> TestClient:
    """Minimal FastAPI app with the Alpha run router + deterministic fixtures."""
    from app.research.repository import ResearchRepository

    repository = ResearchRepository(
        panel_db, clock=deterministic_clock, artifact_root=tmp_path / "alpha_artifacts"
    )
    repository.migrate()
    app = FastAPI()

    @app.middleware("http")
    async def inject_test_principal(request, call_next):
        """Translate the test-only principal header into server-resolved state."""
        principal = request.headers.get("X-Test-Principal")
        if principal:
            request.state.reviewer_principal = principal
        return await call_next(request)

    app.state.research_run_service = ResearchRunService(repository)
    app.state.research_repository = repository
    app.include_router(research_alpha.router)
    client = TestClient(app)
    client._alpha_repository = repository  # type: ignore[attr-defined]
    client._alpha_clock = deterministic_clock  # type: ignore[attr-defined]
    return client
