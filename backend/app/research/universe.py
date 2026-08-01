"""PIT 标的池解析器 — 最小 point-in-time 合约 (PIT contract).

职责: 从 append-only 的 ``factor_universe_membership`` 事件表解析"as-of 某日"的
标的池成员, 并把成员关系按日展开成 ``[symbol, date]`` 帧, 供信号链在单个
governed ``load_panel`` 之后做按日 membership 过滤 (幸存者偏差守卫, pitfall 1)。
同时实现种子/关闭规则: 以 ``listing_date`` (缺失时取首个 bar 日期) 播种
``listed``, 由确认的退市事件追加 ``delisted`` 行; ``symbols_lagging`` 停牌
启发式**不会**触发自动退市 (停牌 ≠ 退市, RESEARCH A4)。

不知道: 行情/K线数据、DSL、评估指标、任何网络或外部数据源。读取的唯一入口是
传入的 ``ResearchRepository`` 与种子用的 ``pl.DataFrame``。
"""
from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
from typing import Any

import polars as pl

from app.research.repository import ResearchRepository

_MEMBERSHIP_METHOD = "factor_universe_membership/v1"
_SEED_SOURCE = "instruments-sync"

_EMPTY_MEMBERSHIP = pl.DataFrame({"symbol": [], "date": []}, schema={"symbol": pl.Utf8, "date": pl.Date})


def _symbols_fingerprint(symbols: frozenset[str]) -> str:
    """Deterministic membership fingerprint: sha256 over the sorted symbol tuple."""
    return sha256(",".join(sorted(symbols)).encode("utf-8")).hexdigest()


def _as_date(value: Any, *, field: str) -> date:
    """Cast a date-ish value to ``date``, tolerating ``date``/``datetime``/ISO strings."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as error:
            raise ValueError(f"{field} is not an ISO date: {value!r}") from error
    raise ValueError(f"{field} must be a date or ISO string, got {type(value).__name__}")


def resolve_universe(
    repo: ResearchRepository,
    *,
    universe_name: str,
    as_of: date,
    asset_type: str = "stock",
) -> tuple[frozenset[str], str]:
    """Membership as-of: the latest event per symbol with ``effective_date <= as_of``.

    A symbol is a member when that latest event is ``listed``; a delist event
    closes membership as-of without deleting the earlier row (append-only).
    Returns ``(symbols, membership_fingerprint)`` where the fingerprint is the
    sha256 of the sorted symbol tuple — reproducible and comparable across runs.
    """
    events = repo.resolve_universe_memberships(
        universe_name=universe_name, as_of=as_of.isoformat(), asset_type=asset_type
    )
    symbols = frozenset(event["symbol"] for event in events if event["state"] == "listed")
    return symbols, _symbols_fingerprint(symbols)


def resolve_universe_daily(
    repo: ResearchRepository,
    *,
    universe_name: str,
    start: date,
    end: date,
    asset_type: str = "stock",
) -> pl.DataFrame:
    """Per-date membership over ``[start, end]`` as a ``[symbol, date]`` frame.

    Each symbol's ``listed`` intervals come from its event history: an event is
    in effect from its ``effective_date`` until the next event for the same
    symbol (exclusive), or ``end`` when open-ended.  Every date in the window
    inside a ``listed`` interval yields one row.  Interval overlap is evaluated
    Polars-natively and dates are exploded from the clipped interval endpoints —
    no market calendar is required; the chain's ``load_panel`` join supplies the
    actual trading dates.
    """
    events = repo.list_universe_memberships(universe_name=universe_name, asset_type=asset_type)
    if not events:
        return _EMPTY_MEMBERSHIP.clone()

    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_symbol.setdefault(str(event["symbol"]), []).append(event)

    intervals: list[tuple[str, date, date]] = []  # (symbol, listed_from, listed_to_exclusive)
    for symbol, symbol_events in by_symbol.items():
        symbol_events.sort(key=lambda item: item["effective_date"])
        for index, event in enumerate(symbol_events):
            if event["state"] != "listed":
                continue
            listed_from = _as_date(event["effective_date"], field="effective_date")
            next_effective = (
                _as_date(symbol_events[index + 1]["effective_date"], field="effective_date")
                if index + 1 < len(symbol_events)
                else None
            )
            listed_to_exclusive = next_effective if next_effective is not None else end + timedelta(days=1)
            intervals.append((symbol, listed_from, listed_to_exclusive))

    if not intervals:
        return _EMPTY_MEMBERSHIP.clone()

    interval_frame = pl.DataFrame(
        intervals, schema={"symbol": pl.Utf8, "_from": pl.Date, "_to_excl": pl.Date}, orient="row"
    )
    # Clip intervals to the window and keep only those that overlap it.
    interval_frame = interval_frame.with_columns(
        pl.max_horizontal(pl.col("_from"), pl.lit(start)).alias("_lo"),
        pl.min_horizontal(pl.col("_to_excl"), pl.lit(end + timedelta(days=1))).alias("_hi_excl"),
    ).filter(pl.col("_lo") < pl.col("_hi_excl"))
    if interval_frame.is_empty():
        return _EMPTY_MEMBERSHIP.clone()
    daily = (
        interval_frame.with_columns(
            pl.struct(["_lo", "_hi_excl"])
            .map_elements(
                lambda bounds: pl.date_range(
                    bounds["_lo"], bounds["_hi_excl"] - timedelta(days=1), interval="1d", eager=True
                ),
                return_dtype=pl.List(pl.Date),
            )
            .alias("_date")
        )
        .explode("_date")
        .select([pl.col("symbol"), pl.col("_date").alias("date")])
        .unique(subset=["symbol", "date"])
        .sort(["symbol", "date"])
    )
    return daily


def seed_membership(
    repo: ResearchRepository,
    instruments: pl.DataFrame,
    enriched: pl.DataFrame,
    *,
    universe_name: str,
    source: str = _SEED_SOURCE,
) -> int:
    """Seed ``listed`` membership from the instruments dimension (append-only).

    For each instrument row: ``effective_date = listing_date`` when present
    (String ``'YYYY-MM-DD'`` normalized per Open Question 5), else the symbol's
    first bar date in the enriched lake (first-bar fallback).  A row already
    present for the same (universe, symbol, effective_date, state) is skipped —
    the seed is idempotent.  Returns the number of rows actually inserted.
    """
    if instruments.is_empty():
        return 0
    normalized = _normalize_instruments(instruments, enriched)
    inserted = 0
    for record in normalized:
        try:
            repo.insert_universe_membership(
                universe_name=universe_name,
                symbol=record["symbol"],
                asset_type=record["asset_type"],
                effective_date=record["effective_date"].isoformat(),
                state="listed",
                source=source,
                provenance_json={"method": _MEMBERSHIP_METHOD, "rule": "instruments-sync-seed"},
            )
        except ValueError:
            # UNIQUE(universe_name, symbol, effective_date, state) collision — the
            # event already exists, which is the desired idempotent state.
            continue
        inserted += 1
    return inserted


def close_membership(
    repo: ResearchRepository,
    *,
    universe_name: str,
    symbol: str,
    effective_date: date,
    asset_type: str = "stock",
    source: str = "delist-event",
    provenance_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a ``delisted`` event closing membership on/after ``effective_date``.

    A delist is a NEW row, never an UPDATE (append-only).  ``symbols_lagging``
    (suspension heuristic) is deliberately NOT a delist trigger — suspension is
    not delisting; a long suspension simply drops out of per-date cross-sections
    because the enriched panel has no rows for the suspended dates.
    """
    return repo.insert_universe_membership(
        universe_name=universe_name,
        symbol=symbol,
        asset_type=asset_type,
        effective_date=effective_date.isoformat(),
        state="delisted",
        source=source,
        provenance_json=provenance_json or {"method": _MEMBERSHIP_METHOD, "rule": "confirmed-delist"},
    )


def _normalize_instruments(instruments: pl.DataFrame, enriched: pl.DataFrame) -> list[dict[str, Any]]:
    """listing_date String cast normalization + first-bar fallback (Open Question 5)."""
    symbol_col = "symbol" if "symbol" in instruments.columns else "code"
    if symbol_col not in instruments.columns:
        raise ValueError("instruments must carry a symbol/code column")
    listing_col = "listing_date" if "listing_date" in instruments.columns else "list_date"
    asset_col = "asset_type" if "asset_type" in instruments.columns else "type"

    frame = instruments.with_columns(pl.col(symbol_col).cast(pl.Utf8, strict=False).alias("_symbol"))
    if listing_col in instruments.columns:
        frame = frame.with_columns(pl.col(listing_col).cast(pl.Utf8, strict=False).alias("_listing"))
    else:
        frame = frame.with_columns(pl.lit(None, dtype=pl.Utf8).alias("_listing"))
    if asset_col in instruments.columns:
        frame = frame.with_columns(pl.col(asset_col).cast(pl.Utf8, strict=False).alias("_asset_type"))
    else:
        frame = frame.with_columns(pl.lit("stock", dtype=pl.Utf8).alias("_asset_type"))

    first_bars = (
        enriched.filter(pl.col("symbol").is_not_null())
        .group_by("symbol")
        .agg(pl.col("date").min().alias("_first_bar"))
        if not enriched.is_empty() and "date" in enriched.columns and "symbol" in enriched.columns
        else pl.DataFrame({"symbol": [], "_first_bar": []})
    )
    frame = frame.join(
        first_bars.rename({"symbol": "_symbol"}),
        on="_symbol",
        how="left",
    )

    records: list[dict[str, Any]] = []
    for row in frame.iter_rows(named=True):
        symbol = str(row["_symbol"]).strip()
        if not symbol:
            continue
        asset_type = str(row["_asset_type"] or "stock").strip().lower()
        if asset_type not in {"stock", "etf"}:
            continue
        effective = _normalize_listing_date(row.get("_listing")) or _normalize_first_bar(row.get("_first_bar"))
        if effective is None:
            continue
        records.append({"symbol": symbol, "asset_type": asset_type, "effective_date": effective})
    return records


def _normalize_listing_date(value: Any) -> date | None:
    """Normalize a ``'YYYY-MM-DD'`` String listing date (or date/datetime) to ``date``."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _normalize_first_bar(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return _as_date(value, field="first bar")
    except ValueError:
        return None
