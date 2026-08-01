"""Shared factor signal chain — the single compile-to-compute path (FACT-06).

Every consumer that needs factor values — evaluation, composite models,
walk-forward, expected returns, live as-of suggestions — calls
:meth:`FactorSignalChain.compute` and nothing else.  A second implementation of
factor values is a bug.

The chain binds a stored revision id to exactly one governed panel (loaded through
``BacktestEngine.load_panel``), then computes cross-sectional ``_factor``,
``_forward_return``, ``_rank`` and ``_zscore`` columns with the DSL's declared
partition semantics.  Panel loads are deduplicated through ``PanelCache`` so
multiple consumers over the same window share one governed read.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from typing import Any, Literal, TypeAlias

import polars as pl

from app.backtest.engine import BacktestEngine, PanelCache
from app.research.factor_dsl import parse_factor
from app.research.factor_registry import FactorRegistry

RebalanceCadence: TypeAlias = Literal["daily", "weekly", "monthly"]
MissingDataTreatment: TypeAlias = Literal["drop"]
WarmupTreatment: TypeAlias = Literal["exclude"]


class SignalChainError(ValueError):
    """A governed-load or factor-computation failure (a failed run, not invalid input)."""


@dataclass(frozen=True, slots=True)
class SignalChainConfig:
    """Fully resolved inputs for one chain compute; no implicit retained defaults."""

    universe: str
    symbols: tuple[str, ...]
    asset_type: str
    start: date
    end: date
    warmup_days: int
    forward_return_horizon: int | None  # None = live as-of path (no label yet)
    rebalance: RebalanceCadence = "daily"
    missing_data_treatment: MissingDataTreatment = "drop"
    warmup_treatment: WarmupTreatment = "exclude"


@dataclass(frozen=True, slots=True)
class FactorSignalFrame:
    """A revision bound to one governed panel with computed values/rank/zscore."""

    revision_id: str
    dsl_version: str
    panel_fingerprint: str
    resolved_universe: Mapping[str, Any]
    frame: pl.DataFrame
    loaded_panel: pl.DataFrame
    required_source_fields: tuple[str, ...]


def _symbols_fingerprint(symbols: frozenset[str]) -> str:
    """Deterministic membership fingerprint: sha256 over the sorted symbol tuple."""
    return sha256(",".join(sorted(symbols)).encode("utf-8")).hexdigest()


def _membership_fingerprint(membership: pl.DataFrame) -> str:
    """sha256 over the canonical per-date membership frame ``[symbol, date]``.

    The frame is sorted by (symbol, date) before hashing so identical per-date
    resolutions hash identically across runs — the reproducibility contract that
    feeds ``catalog._compatibility_warnings``.
    """
    ordered = membership.select(["symbol", "date"]).sort(["symbol", "date"])
    payload = "|".join(f"{row['symbol']}:{row['date']}" for row in ordered.iter_rows(named=True))
    return sha256(payload.encode("utf-8")).hexdigest()


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float(ordered[middle - 1] + ordered[middle]) / 2.0


class FactorSignalChain:
    """Binds a revision id to one governed panel and computes factor values."""

    def __init__(
        self,
        engine: BacktestEngine,
        registry: FactorRegistry,
        universe_resolver: object | None,
    ) -> None:
        self._engine = engine
        self._registry = registry
        self._universe_resolver = universe_resolver
        self._panel_cache = PanelCache(max_size=4, ttl_seconds=180)

    def compute(self, *, revision_id: str, config: SignalChainConfig) -> FactorSignalFrame:
        """Compile the revision, load one governed panel, and compute the signal frame."""
        self._validate_config(config)
        revision, parsed = self._binding(revision_id)
        required = self._required_columns(parsed)
        load_start = config.start - timedelta(days=config.warmup_days)

        membership = self._resolve_membership(config)
        symbols = self._union_symbols(config, membership)

        panel = self._load_panel(list(sorted(symbols)), load_start, config.end, required, config.asset_type)
        if panel.is_empty():
            return self._empty_frame(revision, config, required, panel)
        missing = sorted(set(required) - set(panel.columns))
        if missing:
            raise SignalChainError(f"governed panel does not provide required fields: {', '.join(missing)}")

        if membership is not None:
            panel = panel.join(membership, on=["symbol", "date"], how="inner")
        loaded = panel
        panel = panel.sort(["symbol", "date"])

        horizon = config.forward_return_horizon
        frame = panel.with_columns(parsed.compile().cast(pl.Float64).alias("_factor"))
        if horizon is None:
            frame = frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("_forward_return"))
        else:
            frame = frame.with_columns(
                (pl.col("close").shift(-horizon).over("symbol") / pl.col("close") - 1.0)
                .cast(pl.Float64)
                .alias("_forward_return")
            )

        # Pre-filter finite counts over the evaluation window: coverage measures the
        # resolved cross-section, never the post-filter frame (pitfall 5).
        windowed = frame.filter((pl.col("date") >= config.start) & (pl.col("date") <= config.end))
        finite_counts = (
            windowed.with_columns(pl.col("_factor").is_finite().alias("_finite"))
            .group_by("date")
            .agg(pl.len().alias("total"), pl.col("_finite").sum().alias("finite"))
            .sort("date")
        )
        pre_filter_counts = {
            str(row["date"]): {"total": int(row["total"]), "finite": int(row["finite"])}
            for row in finite_counts.iter_rows(named=True)
        }

        frame = frame.filter((pl.col("date") >= config.start) & (pl.col("date") <= config.end))
        finite_condition = pl.col("_factor").is_finite() & pl.col("close").is_finite() & (pl.col("close") > 0)
        if horizon is not None:
            finite_condition = finite_condition & pl.col("_forward_return").is_finite()
        frame = frame.filter(finite_condition)

        frame = frame.with_columns(
            pl.col("_factor").rank(method="average").over("date").cast(pl.Float64).alias("_rank"),
            ((pl.col("_factor") - pl.col("_factor").mean().over("date")) / pl.col("_factor").std().over("date"))
            .alias("_zscore"),
        )
        frame = self._rebalance(frame, config.rebalance)
        frame = frame.select(["symbol", "date", "_factor", "_forward_return", "_rank", "_zscore"])

        resolved_universe = self._resolved_universe(config, membership, pre_filter_counts)
        return FactorSignalFrame(
            revision_id=revision.id,
            dsl_version=revision.dsl_version,
            panel_fingerprint=self._panel_fingerprint(loaded),
            resolved_universe=resolved_universe,
            frame=frame,
            loaded_panel=loaded,
            required_source_fields=tuple(required),
        )

    @staticmethod
    def _validate_config(config: SignalChainConfig) -> None:
        if not isinstance(config, SignalChainConfig):
            raise TypeError("signal chain config must be a SignalChainConfig")
        if not isinstance(config.universe, str) or not config.universe.strip():
            raise ValueError("universe is required")
        if config.asset_type not in {"stock", "etf"}:
            raise ValueError("asset_type must be stock or etf")
        if not isinstance(config.start, date) or not isinstance(config.end, date) or config.start > config.end:
            raise ValueError("start and end must be an ordered date range")
        if not isinstance(config.warmup_days, int) or config.warmup_days < 0:
            raise ValueError("warmup_days must be a non-negative integer")
        if config.forward_return_horizon is not None and (
            not isinstance(config.forward_return_horizon, int) or config.forward_return_horizon < 1
        ):
            raise ValueError("forward_return_horizon must be a positive integer or None")
        if config.rebalance not in {"daily", "weekly", "monthly"}:
            raise ValueError("rebalance must be daily, weekly, or monthly")
        if config.missing_data_treatment != "drop":
            raise ValueError("missing_data_treatment must be explicit and supported")
        if config.warmup_treatment != "exclude":
            raise ValueError("warmup_treatment must be explicit and supported")
        if any(not isinstance(symbol, str) or not symbol.strip() for symbol in config.symbols):
            raise ValueError("resolved symbols must be non-empty strings")
        if len(set(config.symbols)) != len(config.symbols):
            raise ValueError("resolved symbols must not contain duplicates")

    def _binding(self, revision_id: str):
        revision = self._registry.get_revision(revision_id)
        if revision is None:
            raise ValueError("factor revision does not exist (dsl_version binding rejected)")
        parsed = parse_factor(revision.canonical_expression)
        if parsed.dsl_version != revision.dsl_version:
            raise ValueError("stored factor revision DSL version is not supported")
        if tuple(sorted(parsed.referenced_fields)) != tuple(sorted(revision.fields)):
            raise ValueError("stored factor revision dependency fields are invalid")
        return revision, parsed

    @staticmethod
    def _required_columns(parsed) -> list[str]:
        return ["symbol", "date", "close", *sorted(field for field in parsed.referenced_fields if field != "close")]

    def _resolve_membership(self, config: SignalChainConfig) -> pl.DataFrame | None:
        """Per-date membership over the window (or start-warmup when set).

        The chain derives the symbol set from this frame, passes the union to the
        single governed ``load_panel``, then filters rows per date with an inner
        join — the per-date filter is applied AFTER the governed read, leaving
        ``load_panel`` byte-identical (RESEARCH PIT contract §4).
        """
        if self._universe_resolver is None:
            return None
        resolve = getattr(self._universe_resolver, "resolve_universe_daily", None)
        if resolve is None:
            return None
        membership_start = config.start - timedelta(days=config.warmup_days) if config.warmup_days else config.start
        membership = resolve(
            universe_name=config.universe,
            start=membership_start,
            end=config.end,
            asset_type=config.asset_type,
        )
        if membership is None or getattr(membership, "is_empty", lambda: True)():
            return None
        return membership.select(["symbol", "date"]).unique()

    @staticmethod
    def _union_symbols(config: SignalChainConfig, membership: pl.DataFrame | None) -> set[str]:
        symbols = set(config.symbols)
        if membership is not None:
            symbols |= set(membership["symbol"].unique().to_list())
        return symbols

    def _load_panel(self, symbols: list[str], start: date, end: date, columns: list[str], asset_type: str) -> pl.DataFrame:
        load_symbols = symbols if symbols else None

        def compute(symbols_arg, start_arg, end_arg, columns_arg, asset_type_arg):  # type: ignore[no-untyped-def]
            return self._engine.load_panel(
                symbols_arg, start_arg, end_arg, columns=columns_arg, asset_type=asset_type_arg
            )

        return self._panel_cache.get_or_compute(load_symbols, start, end, columns, compute, asset_type=asset_type)

    @staticmethod
    def _rebalance(panel: pl.DataFrame, cadence: RebalanceCadence) -> pl.DataFrame:
        if cadence == "daily":
            return panel
        if cadence == "weekly":
            return panel.filter(pl.col("date").dt.weekday() == 1)
        return (
            panel.with_columns(pl.col("date").dt.strftime("%Y-%m").alias("_month"))
            .filter(pl.col("date") == pl.col("date").min().over("_month"))
            .drop("_month")
        )

    @staticmethod
    def _panel_fingerprint(panel: pl.DataFrame) -> str:
        schema = {name: str(dtype) for name, dtype in panel.schema.items()}
        try:
            observed_start = str(panel.select(pl.col("date").min()).item())
            observed_end = str(panel.select(pl.col("date").max()).item())
        except Exception:
            observed_start = ""
            observed_end = ""
        payload = json.dumps(
            {
                "schema": schema,
                "observed_start": observed_start,
                "observed_end": observed_end,
                "row_count": panel.height,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    def _resolved_universe(
        self,
        config: SignalChainConfig,
        membership: pl.DataFrame | None,
        pre_filter_counts: Mapping[str, Mapping[str, int]],
    ) -> dict[str, Any]:
        if membership is not None:
            symbol_set = frozenset(membership["symbol"].unique().to_list())
            counts = membership.group_by("date").agg(pl.len().alias("count")).sort("date")
            lengths = [int(row["count"]) for row in counts.iter_rows(named=True)]
            per_date_symbol_counts = {"min": min(lengths), "median": _median(lengths), "max": max(lengths)} if lengths else {}
            method = "factor_universe_membership/v1"
            excluded_delisted = sorted(set(config.symbols) - symbol_set)
        else:
            symbol_set = frozenset(config.symbols)
            per_date_symbol_counts = {"min": len(config.symbols), "median": float(len(config.symbols)), "max": len(config.symbols)}
            method = "config-symbols"
            excluded_delisted = []
        return {
            "method": method,
            "membership_fingerprint": (
                _membership_fingerprint(membership) if membership is not None else _symbols_fingerprint(symbol_set)
            ),
            "per_date_symbol_counts": per_date_symbol_counts,
            "excluded_delisted": excluded_delisted,
            "pre_filter_counts": dict(pre_filter_counts),
        }

    def _empty_frame(
        self,
        revision,
        config: SignalChainConfig,
        required: list[str],
        panel: pl.DataFrame,
    ) -> FactorSignalFrame:
        frame = panel.select([pl.col("symbol"), pl.col("date")]).with_columns(
            [
                pl.lit(None, dtype=pl.Float64).alias("_factor"),
                pl.lit(None, dtype=pl.Float64).alias("_forward_return"),
                pl.lit(None, dtype=pl.Float64).alias("_rank"),
                pl.lit(None, dtype=pl.Float64).alias("_zscore"),
            ]
        )
        return FactorSignalFrame(
            revision_id=revision.id,
            dsl_version=revision.dsl_version,
            panel_fingerprint=self._panel_fingerprint(panel),
            resolved_universe=self._resolved_universe(config, None, {}),
            frame=frame,
            loaded_panel=panel,
            required_source_fields=tuple(required),
        )
