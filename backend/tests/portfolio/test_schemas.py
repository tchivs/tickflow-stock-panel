"""RED scaffold for portfolio/schemas.py — OptimizationRequest DTO.

Wave 0 (11-02) scaffold: the strict Pydantic DTO + solver-options whitelist is
created by 11-01 (V5 input validation); this file is RED until then.
"""
from __future__ import annotations

import pytest
from app.portfolio.schemas import SOLVER_OPTIONS_ALLOWLIST, OptimizationRequest


def test_request_defaults_to_min_vol_with_baselines() -> None:
    request = OptimizationRequest(as_of="2026-08-01")
    assert request.objective == "min_volatility"
    assert request.render_baselines is True


def test_request_validates_enum_and_date() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OptimizationRequest(as_of="2026-08-01", objective="max-alpha")
    with pytest.raises(ValidationError):
        OptimizationRequest(as_of="not-a-date")


def test_max_sharpe_requires_explicit_opt_in() -> None:
    request = OptimizationRequest(as_of="2026-08-01", objective="max_sharpe")
    assert request.objective == "max_sharpe"


def test_solver_options_allowlist_is_frozen_surface() -> None:
    assert isinstance(SOLVER_OPTIONS_ALLOWLIST, frozenset)
    assert "solver" in SOLVER_OPTIONS_ALLOWLIST
