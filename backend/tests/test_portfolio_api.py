"""CORE-03 contract tests for SQLite-backed portfolio operations and valuations."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.portfolio import router as portfolio_router

from app.operational.repository import OperationalRepository
from app.portfolio.service import PortfolioService


def _quotes(*, fresh: bool = True):
    as_of = datetime(2026, 7, 10, 1, 30, tzinfo=timezone.utc)

    class _QuoteSource:
        def latest_quotes(self):
            return {
                "600519.SH": {
                    "price": 1600.0,
                    "as_of": as_of,
                    "fresh": fresh,
                }
            }

    return _QuoteSource()


class _GovernedCloses:
    def latest_close(self, symbol: str):
        assert symbol == "600519.SH"
        return {"price": 1500.0, "as_of": "2026-07-09"}


def _service(tmp_path, *, quotes=None):
    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository, PortfolioService(
        repository=repository,
        quote_service=quotes or _quotes(),
        governed_closes=_GovernedCloses(),
    )


def test_accounts_positions_and_summary_remain_account_scoped_and_aggregate(tmp_path):
    """Accounts retain own funds while aggregate P&L joins the shared quote once."""
    repository, service = _service(tmp_path)
    cash = repository.create_account(name="Cash", available_funds=1000.0)
    margin = repository.create_account(name="Margin", available_funds=2500.0)

    cash_position = repository.create_position(
        account_id=cash["id"],
        instrument_symbol="600519.SH",
        cost_price=1400.0,
        quantity=10,
        invested_amount=14000.0,
        trading_style="swing",
    )
    margin_position = repository.create_position(
        account_id=margin["id"],
        instrument_symbol="600519.SH",
        cost_price=1500.0,
        quantity=2,
        invested_amount=3000.0,
        trading_style="long",
    )

    assert repository.list_accounts() == [cash, margin]
    assert repository.list_positions(account_id=cash["id"])[0]["id"] == cash_position["id"]

    summary = service.portfolio_summary()
    assert summary["available_funds"] == 3500.0
    assert summary["market_value"] == 19200.0
    assert summary["unrealized_pnl"] == 2200.0
    assert {row["position_id"] for row in summary["positions"]} == {
        cash_position["id"],
        margin_position["id"],
    }
    assert {row["source"] for row in summary["positions"]} == {"shared_quote"}
    assert {row["as_of"] for row in summary["positions"]} == {"2026-07-10T01:30:00+00:00"}


def test_position_requires_valid_values_unique_account_instrument_and_supported_style(tmp_path):
    """Untrusted portfolio inputs are validated before parameter-bound SQLite writes."""
    repository, _ = _service(tmp_path)
    account = repository.create_account(name="Primary", available_funds=0.0)

    with pytest.raises(ValueError, match="quantity"):
        repository.create_position(
            account_id=account["id"], instrument_symbol="600519.SH", cost_price=1.0,
            quantity=0, invested_amount=1.0, trading_style="swing",
        )
    with pytest.raises(ValueError, match="trading_style"):
        repository.create_position(
            account_id=account["id"], instrument_symbol="600519.SH", cost_price=1.0,
            quantity=1, invested_amount=1.0, trading_style="intraday",
        )

    repository.create_position(
        account_id=account["id"], instrument_symbol="600519.SH", cost_price=1.0,
        quantity=1, invested_amount=1.0, trading_style="short",
    )
    with pytest.raises(ValueError, match="instrument"):
        repository.create_position(
            account_id=account["id"], instrument_symbol="600519.SH", cost_price=1.0,
            quantity=1, invested_amount=1.0, trading_style="short",
        )


def test_stale_quote_falls_back_to_governed_close_with_explicit_freshness(tmp_path):
    """A stale quote never masquerades as live valuation."""
    repository, service = _service(tmp_path, quotes=_quotes(fresh=False))
    account = repository.create_account(name="Primary", available_funds=0.0)
    position = repository.create_position(
        account_id=account["id"], instrument_symbol="600519.SH", cost_price=1400.0,
        quantity=2, invested_amount=2800.0, trading_style="swing",
    )

    valuation = service.valuation_for_position(position)

    assert valuation == {
        "market_value": 3000.0,
        "unrealized_pnl": 200.0,
        "pnl_pct": pytest.approx(200.0 / 2800.0),
        "source": "governed_close",
        "as_of": "2026-07-09",
        "fresh": False,
    }


def test_referenced_records_archive_and_empty_records_delete_without_losing_ids(tmp_path):
    """Historical account and position references remain addressable after archival."""
    repository, _ = _service(tmp_path)
    empty = repository.create_account(name="Empty", available_funds=0.0)
    assert repository.delete_account(empty["id"]) is True

    account = repository.create_account(name="History", available_funds=0.0)
    position = repository.create_position(
        account_id=account["id"], instrument_symbol="600519.SH", cost_price=1000.0,
        quantity=1, invested_amount=1000.0, trading_style="long",
    )
    repository.record_alert_reference(position_id=position["id"], rule_id="rule_01")

    assert repository.delete_position(position["id"]) is False
    archived_position = repository.archive_position(position["id"])
    assert archived_position["id"] == position["id"]
    assert archived_position["archived_at"] is not None

    assert repository.delete_account(account["id"]) is False
    archived_account = repository.archive_account(account["id"])
    assert archived_account["id"] == account["id"]
    assert archived_account["archived_at"] is not None


def test_portfolio_api_returns_quote_projected_positions_and_archive_guards(tmp_path):
    """HTTP mutations use the same archive-safe repository and valuation projection."""
    repository, service = _service(tmp_path)
    app = FastAPI()
    app.include_router(portfolio_router)
    app.state.operational = repository
    app.state.portfolio_service = service
    app.state.quote_service = _quotes()
    client = TestClient(app)

    created_account = client.post("/api/portfolio/accounts", json={"name": "Cash", "available_funds": 500}).json()["account"]
    created_position = client.post(
        "/api/portfolio/positions",
        json={
            "account_id": created_account["id"],
            "instrument_symbol": "600519.SH",
            "cost_price": 1500,
            "quantity": 2,
            "invested_amount": 3000,
            "trading_style": "swing",
        },
    ).json()["position"]

    summary = client.get(f"/api/portfolio/summary?account_id={created_account['id']}").json()
    positions = client.get("/api/portfolio/positions").json()["positions"]
    assert summary["market_value"] == 3200.0
    assert positions[0]["source"] == "shared_quote"
    assert positions[0]["as_of"] == "2026-07-10T01:30:00+00:00"

    repository.record_alert_reference(position_id=created_position["id"], rule_id="rule_01")
    assert client.delete(f"/api/portfolio/positions/{created_position['id']}").status_code == 400
    archived = client.post(f"/api/portfolio/positions/{created_position['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["position"]["id"] == created_position["id"]


def test_main_application_registers_portfolio_router():
    """The operational boundary is reachable from the single host application."""
    from app.main import app

    assert any(route.path == "/api/portfolio/summary" for route in app.routes)
