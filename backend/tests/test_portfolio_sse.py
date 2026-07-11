"""CORE-05 contract tests for portfolio updates on the existing QuoteService stream."""
from __future__ import annotations

from app.api.intraday import router
from app.services.quote_service import QuoteService, QuoteSubscriber


def test_two_subscribers_independently_receive_alerts_and_portfolio_updates():
    """One QuoteService fan-out must not let either client consume the other's events."""
    service = QuoteService()
    first = service.subscribe()
    second = service.subscribe()

    service.push_alerts([{"id": "alert_01", "symbol": "600519.SH"}])
    service.notify_portfolio_updated(["account_cash", "account_margin"])

    first_data = first.pop()
    second_data = second.pop()
    assert first_data["alerts"] == [{"id": "alert_01", "symbol": "600519.SH"}]
    assert second_data["alerts"] == [{"id": "alert_01", "symbol": "600519.SH"}]
    assert first_data["portfolio_updated"] is True
    assert second_data["portfolio_updated"] is True
    assert first_data["portfolio_account_ids"] == ["account_cash", "account_margin"]
    assert second_data["portfolio_account_ids"] == ["account_cash", "account_margin"]


def test_portfolio_updates_coalesce_per_subscriber_without_dropping_affected_accounts():
    subscriber = QuoteSubscriber()

    subscriber.notify_portfolio_updated(["account_cash"])
    subscriber.notify_portfolio_updated(["account_margin", "account_cash"])

    data = subscriber.pop()
    assert data["portfolio_updated"] is True
    assert data["portfolio_account_ids"] == ["account_cash", "account_margin"]
    assert subscriber.wait(timeout=0.01) is False


def test_existing_intraday_endpoint_is_the_only_portfolio_stream_route():
    """Portfolio refreshes share the named-event pipeline rather than opening another SSE route."""
    routes = {route.path for route in router.routes}

    assert "/api/intraday/stream" in routes
    assert not any("portfolio" in path and "stream" in path for path in routes)
