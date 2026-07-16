"""Versioned, Parquet-backed governed CN-A trading sessions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl


_COLUMNS = {
    "calendar_id",
    "calendar_revision",
    "market",
    "session_id",
    "trade_date",
    "is_open",
    "sequence",
}


@dataclass(frozen=True, slots=True)
class TradingSession:
    session_id: str
    trade_date: date
    sequence: int


class GovernedTradingCalendar:
    """Resolves only locally synchronized, versioned session rows."""

    def __init__(self, frame: pl.DataFrame) -> None:
        if set(frame.columns) != _COLUMNS:
            raise ValueError("governed calendar schema is invalid")
        if frame.is_empty():
            raise ValueError("governed calendar coverage is empty")
        if frame.null_count().sum_horizontal().item() > 0:
            raise ValueError("governed calendar contains incomplete rows")
        self._frame = frame

    @classmethod
    def from_parquet(cls, path: Path) -> GovernedTradingCalendar:
        candidate = Path(path)
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("governed calendar Parquet is unavailable")
        try:
            frame = pl.read_parquet(candidate)
        except (OSError, TypeError, ValueError) as error:
            raise ValueError("governed calendar Parquet is invalid") from error
        return cls(frame)

    def future_sessions(
        self,
        *,
        calendar_id: str,
        after_session_id: str,
        count: int,
    ) -> tuple[TradingSession, ...]:
        if count not in {5, 20, 60}:
            raise ValueError("Forecast horizon must be 5, 20, or 60 sessions")
        calendar = self._calendar(calendar_id)
        if not isinstance(after_session_id, str) or not after_session_id.startswith("CNA-"):
            raise ValueError("as-of session identity is invalid")
        future = (
            calendar.filter(
                (pl.col("session_id") > after_session_id) & pl.col("is_open")
            )
            .sort("sequence")
            .head(count)
        )
        if future.height != count:
            raise ValueError("insufficient governed future session coverage")
        if future["session_id"].n_unique() != future.height or future["sequence"].n_unique() != future.height:
            raise ValueError("governed future sessions are duplicated")
        return tuple(
            TradingSession(session_id=str(session_id), trade_date=trade_date, sequence=int(sequence))
            for session_id, trade_date, sequence in future.select(
                ["session_id", "trade_date", "sequence"]
            ).iter_rows()
        )

    def revision(self, calendar_id: str) -> str:
        calendar = self._calendar(calendar_id)
        revisions = calendar["calendar_revision"].unique().to_list()
        if len(revisions) != 1:
            raise ValueError("governed calendar revision is ambiguous")
        revision = revisions[0]
        if not isinstance(revision, str) or not revision:
            raise ValueError("governed calendar revision is invalid")
        return revision

    def _calendar(self, calendar_id: str) -> pl.DataFrame:
        if not isinstance(calendar_id, str) or not calendar_id:
            raise ValueError("governed calendar identity is invalid")
        calendar = self._frame.filter(
            (pl.col("calendar_id") == calendar_id) & (pl.col("market") == "CN-A")
        )
        if calendar.is_empty():
            raise ValueError("governed calendar is unavailable")
        if calendar["session_id"].n_unique() != calendar.height:
            raise ValueError("governed calendar contains duplicate sessions")
        sequences = calendar["sequence"].to_list()
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise ValueError("governed calendar sessions are not sorted and unique")
        revisions = calendar["calendar_revision"].unique().to_list()
        if len(revisions) != 1 or not isinstance(revisions[0], str) or not revisions[0]:
            raise ValueError("governed calendar revision is ambiguous")
        return calendar
