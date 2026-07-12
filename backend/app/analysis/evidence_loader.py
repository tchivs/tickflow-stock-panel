"""Read-only adapter from governed host boundaries to analysis evidence records."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
import math
from pathlib import Path
from typing import Any

import polars as pl

from app.services.financial_sync import FINANCIAL_TABLES, get_financial_df

FinancialLoader = Callable[[Path, str], pl.DataFrame]
RetrievedAt = Callable[[], datetime]

_MARKET_FIELDS = frozenset({"symbol", "date", "datetime", "asset_type", "source"})
_FINANCIAL_PERIOD_FIELDS = ("report_date", "period", "end_date", "date")


def _as_date(value: object, fallback: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    return fallback


def _finite_fields(row: Mapping[str, Any], *, excluded: frozenset[str]) -> Sequence[tuple[str, float]]:
    return tuple(
        (field, float(value))
        for field, value in row.items()
        if field not in excluded
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


class GovernedEvidenceLoader:
    """Build JSON-safe facts without accepting browser or external-provider evidence."""

    def __init__(
        self,
        *,
        repository: Any,
        operational_repository: Any,
        financial_loader: FinancialLoader = get_financial_df,
        retrieved_at: RetrievedAt | None = None,
    ) -> None:
        self._repository = repository
        self._operational_repository = operational_repository
        self._financial_loader = financial_loader
        self._retrieved_at = retrieved_at or (lambda: datetime.now(UTC))

    def __call__(self, subject_kind: str, subject_key: str, _focus: str) -> list[dict[str, Any]]:
        """Return only server-derived, provenance-bounded records for an authorized subject."""
        if subject_kind == "instrument":
            return self._instrument_records(subject_key)
        if subject_kind == "account":
            return self._account_records(subject_key)
        raise ValueError("analysis subject kind is unsupported")

    def _account_records(self, subject_key: str) -> list[dict[str, Any]]:
        try:
            account_id = int(subject_key)
        except (TypeError, ValueError):
            return []
        positions = self._operational_repository.list_positions(account_id=account_id)
        records: list[dict[str, Any]] = []
        symbols: set[str] = set()
        retrieved_at = self._retrieved_at()
        as_of = retrieved_at.date()
        for position in positions:
            position_id = position.get("id")
            symbol = position.get("instrument_symbol")
            if isinstance(symbol, str) and symbol:
                symbols.add(symbol)
            for field in ("cost_price", "quantity", "invested_amount"):
                value = position.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                    continue
                records.append(
                    {
                        "source_id": f"operational-holdings:{account_id}:{position_id}:{field}",
                        "origin": "operational-holdings",
                        "independence_group": "operational-account-ledger",
                        "value": float(value),
                        "unit": "shares" if field == "quantity" else "CNY",
                        "period": as_of.isoformat(),
                        "definition": field,
                        "retrieved_at": retrieved_at,
                        "as_of": as_of,
                        "source_locator": f"operational.db#positions/{position_id}/{field}",
                    }
                )
        for symbol in sorted(symbols):
            records.extend(self._instrument_records(symbol))
        return records

    def _instrument_records(self, symbol: str) -> list[dict[str, Any]]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return []
        records = self._market_records(normalized_symbol)
        records.extend(self._financial_records(normalized_symbol))
        return records

    def _market_records(self, symbol: str) -> list[dict[str, Any]]:
        frame, latest = self._repository.get_enriched_latest()
        if frame.is_empty() or "symbol" not in frame.columns:
            return []
        selected = frame.filter(pl.col("symbol") == symbol)
        if selected.is_empty():
            return []
        retrieved_at = self._retrieved_at()
        as_of = _as_date(latest, retrieved_at.date())
        records: list[dict[str, Any]] = []
        for row in selected.to_dicts():
            row_as_of = _as_date(row.get("date"), as_of)
            for field, value in _finite_fields(row, excluded=_MARKET_FIELDS):
                records.append(
                    {
                        "source_id": f"governed-market-data:{symbol}:{row_as_of.isoformat()}:{field}",
                        "origin": "governed-market-data",
                        "independence_group": "governed-market-data",
                        "value": value,
                        "unit": "CNY" if field in {"open", "high", "low", "close"} else "count",
                        "period": row_as_of.isoformat(),
                        "definition": field,
                        "retrieved_at": retrieved_at,
                        "as_of": row_as_of,
                        "source_locator": f"kline_daily_enriched/{row_as_of.isoformat()}/{symbol}/{field}",
                    }
                )
        return records

    def _financial_records(self, symbol: str) -> list[dict[str, Any]]:
        data_dir = Path(self._repository.store.data_dir)
        retrieved_at = self._retrieved_at()
        records: list[dict[str, Any]] = []
        for table in FINANCIAL_TABLES:
            frame = self._financial_loader(data_dir, table)
            if frame.is_empty() or "symbol" not in frame.columns:
                continue
            selected = frame.filter(pl.col("symbol") == symbol)
            for row_index, row in enumerate(selected.to_dicts()):
                period_value = next((row[field] for field in _FINANCIAL_PERIOD_FIELDS if field in row), None)
                as_of = _as_date(period_value, retrieved_at.date())
                period = str(period_value) if period_value is not None else as_of.isoformat()
                excluded = frozenset({"symbol", *_FINANCIAL_PERIOD_FIELDS})
                for field, value in _finite_fields(row, excluded=excluded):
                    records.append(
                        {
                            "source_id": f"audited-financials:{table}:{symbol}:{row_index}:{field}",
                            "origin": "audited-financials",
                            "independence_group": f"governed-financials-{table}",
                            "value": value,
                            "unit": "CNY",
                            "period": period,
                            "definition": f"{table}_{field}",
                            "retrieved_at": retrieved_at,
                            "as_of": as_of,
                            "source_locator": f"financials/{table}/part.parquet#{symbol}:{row_index}:{field}",
                        }
                    )
        return records
