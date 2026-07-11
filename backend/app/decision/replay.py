"""Historical, deterministic decision replay with an AI-call fail-closed guard."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time, timezone
from hashlib import sha256
import json
from typing import Any, Iterator, Mapping, Protocol, Sequence


_replay_active: ContextVar[bool] = ContextVar("decision_replay_active", default=False)


class ReplayAIInvocationError(RuntimeError):
    """Raised before any review/provider work can execute during replay."""


@contextmanager
def replay_guard() -> Iterator[None]:
    """Forbid the optional review path for the duration of a historical replay."""
    token = _replay_active.set(True)
    try:
        yield
    finally:
        _replay_active.reset(token)


def assert_review_allowed() -> None:
    """Fail closed at the review boundary rather than depending on gateway behavior."""
    if _replay_active.get():
        raise ReplayAIInvocationError("AI review is disabled during historical replay")


class GovernedDecisionHistory(Protocol):
    """Narrow historical input boundary used by replay."""

    def decision_rows(self, *, symbols: list[str], as_of: date) -> Sequence[Mapping[str, Any]]: ...


class KlineGovernedDecisionHistory:
    """Adapter exposing only as-of-bounded Tickflow governed daily rows."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def decision_rows(self, *, symbols: list[str], as_of: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            frame = self._repository.get_daily(
                symbol,
                date(1970, 1, 1),
                as_of,
                columns=["date", "open", "high", "low", "close"],
            )
            if frame is None or frame.is_empty():
                continue
            rows.extend(
                {
                    "symbol": symbol,
                    "trade_date": str(row["date"]),
                    **{field: str(row[field]) for field in ("open", "high", "low", "close") if row.get(field) is not None},
                }
                for row in frame.sort("date").to_dicts()
            )
        return rows


class HistoricalReplayService:
    """Persist a stable governed-history snapshot without any proposal collaborator."""

    def __init__(self, *, repository: Any, governed_history: GovernedDecisionHistory) -> None:
        self._repository = repository
        self._governed_history = governed_history

    @staticmethod
    def _symbols(symbols: Sequence[str]) -> list[str]:
        if not isinstance(symbols, Sequence) or isinstance(symbols, str):
            raise ValueError("replay symbols are required")
        normalized = sorted({symbol.strip().upper() for symbol in symbols if isinstance(symbol, str) and symbol.strip()})
        if not normalized or len(normalized) != len(symbols):
            raise ValueError("replay symbols are invalid")
        return normalized

    @staticmethod
    def _trade_date(value: Any) -> date:
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise ValueError("governed replay row is missing trade_date")
        return date.fromisoformat(value)

    @classmethod
    def _snapshot(cls, *, symbols: list[str], as_of: date, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        ordered: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            symbol = row.get("symbol")
            if not isinstance(symbol, str) or symbol.upper() not in symbols:
                continue
            trade_date = cls._trade_date(row.get("trade_date"))
            if trade_date > as_of:
                continue
            ordered.append(
                {
                    key: str(value)
                    for key, value in row.items()
                    if key != "symbol" and value is not None
                }
                | {"symbol": symbol.upper(), "trade_date": trade_date.isoformat()}
            )
        ordered.sort(key=lambda row: (row["symbol"], row["trade_date"], json.dumps(row, sort_keys=True, separators=(",", ":"))))
        latest_trade_date = max((row["trade_date"] for row in ordered), default=as_of.isoformat())
        return {
            "symbols": symbols,
            "rows": ordered,
            "latest_trade_date": latest_trade_date,
            "created_at": datetime.combine(as_of, time(), tzinfo=timezone.utc).isoformat(),
        }

    def replay(self, *, symbols: Sequence[str], as_of: date, engine_config_version: str) -> dict[str, Any]:
        if not isinstance(as_of, date):
            raise ValueError("replay as_of must be a date")
        if not isinstance(engine_config_version, str) or not engine_config_version.strip():
            raise ValueError("replay engine_config_version is required")
        ordered_symbols = self._symbols(symbols)
        with replay_guard():
            rows = self._governed_history.decision_rows(symbols=ordered_symbols, as_of=as_of)
            snapshot = self._snapshot(symbols=ordered_symbols, as_of=as_of, rows=rows)
        result_hash = sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return self._repository.record_replay_run(
            as_of=as_of.isoformat(),
            engine_config_version=engine_config_version.strip(),
            result_hash=result_hash,
            snapshot=snapshot,
        )
