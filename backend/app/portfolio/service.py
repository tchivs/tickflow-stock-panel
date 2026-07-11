"""Quote-projected valuation service for operational portfolio records."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.operational.repository import OperationalRepository


class PortfolioService:
    """Projects current values from the shared quote source without persisting prices."""

    def __init__(
        self,
        *,
        repository: OperationalRepository,
        quote_service: Any,
        governed_closes: Any,
        max_quote_age_seconds: float = 120,
    ) -> None:
        self.repository = repository
        self.quote_service = quote_service
        self.governed_closes = governed_closes
        self.max_quote_age_seconds = max_quote_age_seconds

    @staticmethod
    def _as_of(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return str(value)

    def _fresh_quote(self, symbol: str) -> dict[str, Any] | None:
        """Return a fresh shared quote, supporting the host's Polars snapshot seam."""
        latest_quotes = getattr(self.quote_service, "latest_quotes", None)
        if callable(latest_quotes):
            quote = latest_quotes().get(symbol)
            if quote and quote.get("fresh") and quote.get("price") is not None:
                return {
                    "price": float(quote["price"]),
                    "as_of": self._as_of(quote.get("as_of")),
                    "fresh": True,
                }
            return None

        get_enriched_today = getattr(self.quote_service, "get_enriched_today", None)
        if not callable(get_enriched_today):
            return None
        frame, as_of = get_enriched_today()
        if frame is None or frame.is_empty() or not {"symbol", "close"}.issubset(frame.columns):
            return None
        rows = frame.filter(frame["symbol"] == symbol).select(["close"]).to_dicts()
        if not rows or rows[0]["close"] is None:
            return None

        status = getattr(self.quote_service, "status", lambda: {})()
        age_ms = status.get("quote_age_ms")
        is_fresh = bool(status.get("is_trading_hours")) and isinstance(age_ms, (int, float)) and (
            age_ms <= self.max_quote_age_seconds * 1000
        )
        if not is_fresh:
            return None
        return {"price": float(rows[0]["close"]), "as_of": self._as_of(as_of), "fresh": True}

    def _governed_close(self, symbol: str) -> dict[str, Any] | None:
        latest_close = getattr(self.governed_closes, "latest_close", None)
        if callable(latest_close):
            close = latest_close(symbol)
            if close and close.get("price") is not None:
                return {"price": float(close["price"]), "as_of": self._as_of(close.get("as_of")), "fresh": False}
            return None

        get_daily = getattr(self.governed_closes, "get_daily", None)
        if not callable(get_daily):
            return None
        frame = get_daily(symbol, date.today() - timedelta(days=3650), date.today(), columns=["date", "close"])
        if frame is None or frame.is_empty() or "close" not in frame.columns:
            return None
        latest = frame.tail(1).to_dicts()[0]
        if latest.get("close") is None:
            return None
        return {"price": float(latest["close"]), "as_of": self._as_of(latest.get("date")), "fresh": False}

    def valuation_for_position(self, position: dict[str, Any]) -> dict[str, Any]:
        quote = self._fresh_quote(position["instrument_symbol"]) or self._governed_close(position["instrument_symbol"])
        if quote is None:
            return {
                "market_value": None,
                "unrealized_pnl": None,
                "pnl_pct": None,
                "source": "unavailable",
                "as_of": None,
                "fresh": False,
            }

        quantity = float(position["quantity"])
        cost = float(position["cost_price"]) * quantity
        market_value = quote["price"] * quantity
        unrealized_pnl = market_value - cost
        return {
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct": unrealized_pnl / cost if cost else None,
            "source": "shared_quote" if quote["fresh"] else "governed_close",
            "as_of": quote["as_of"],
            "fresh": quote["fresh"],
        }

    def valued_positions(
        self,
        *,
        account_id: int | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        positions = self.repository.list_positions(account_id=account_id, include_archived=include_archived)
        return [
            {
                **position,
                "position_id": position["id"],
                **self.valuation_for_position(position),
            }
            for position in positions
        ]

    def portfolio_summary(
        self,
        *,
        account_id: int | None = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        accounts = self.repository.list_accounts(include_archived=include_archived)
        if account_id is not None:
            accounts = [account for account in accounts if account["id"] == account_id]
        positions = self.valued_positions(account_id=account_id, include_archived=include_archived)
        valued = [position for position in positions if position["market_value"] is not None]
        unavailable_position_ids = [position["position_id"] for position in positions if position["market_value"] is None]
        values = {
            "available_funds": sum(float(account["available_funds"]) for account in accounts),
            "market_value": sum(float(position["market_value"]) for position in valued) if not unavailable_position_ids else None,
            "unrealized_pnl": sum(float(position["unrealized_pnl"]) for position in valued) if not unavailable_position_ids else None,
        }
        values["total_assets"] = (
            values["available_funds"] + values["market_value"] if values["market_value"] is not None else None
        )
        return {
            **values,
            "account_id": account_id,
            "accounts": accounts,
            "positions": positions,
            "unavailable_position_ids": unavailable_position_ids,
        }
