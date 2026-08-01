"""Provider resolution helpers for the multi-source provider chain.

Adds the free-stockdb HTTP provider to the builtin provider set and exposes
a small chain resolver so callers can try providers in order and merge the
non-overlapping gaps (complementary sources), not just fail over.
"""
from __future__ import annotations

import logging
from typing import Callable

import polars as pl

from app.config import settings
from app.data_providers.free_stockdb_provider import FreeStockDBProvider

logger = logging.getLogger(__name__)

_BUILTIN_CHAIN: dict[str, list[str]] = {
    "daily": ["free_stockdb", "xyz", "tickflow"],
    "minute": ["free_stockdb", "xyz", "tickflow"],
    "adj_factor": ["free_stockdb", "tickflow"],
    "realtime": ["tickflow"],
    "financial": ["tickflow"],
    "instruments": ["tickflow"],
}

_provider_cache: dict[str, object] = {}


def free_stockdb_provider() -> FreeStockDBProvider:
    """Return the shared free-stockdb HTTP provider (lazy singleton)."""
    provider = _provider_cache.get("free_stockdb")
    if provider is None:
        provider = FreeStockDBProvider(base_url=settings.free_stockdb_url)
        _provider_cache["free_stockdb"] = provider
    return provider


def xyz_provider():
    """Return the shared xyz online MCP provider (lazy singleton)."""
    from app.data_providers.xyz_provider import XYZProvider

    provider = _provider_cache.get("xyz")
    if provider is None:
        provider = XYZProvider()
        _provider_cache["xyz"] = provider
    return provider


def _get_provider(name: str):
    if name == "tickflow":
        from app.data_providers.registry import get_provider as get_tf

        return get_tf("tickflow")
    if name == "free_stockdb":
        return free_stockdb_provider()
    if name == "fixture":
        from app.data_providers.fixture_provider import FixtureProvider

        return FixtureProvider(settings.data_dir / "fixtures")
    from app.data_providers import custom as custom_sources
    if name == "xyz":
        return xyz_provider()

    return custom_sources.get_provider(name)


def chain_for(dataset: str) -> list[str]:
    """Return the ordered provider names for a dataset (user overrides later)."""
    return list(_BUILTIN_CHAIN.get(dataset, ["tickflow"]))


def fetch_with_chain(
    dataset: str,
    fetch: Callable[[object], pl.DataFrame],
    providers: list[str] | None = None,
) -> pl.DataFrame:
    """Run ``fetch`` across the dataset's provider chain and merge gaps.

    Providers are tried in order. A provider that raises, returns an empty
    frame, or returns only rows already covered by an earlier provider is
    skipped. Rows are merged by the dataset's natural key (last writer wins)
    so complementary sources combine into one frame.

    Args:
        dataset: one of daily/minute/adj_factor/... (chain name)
        fetch: callable taking a provider instance and returning a normalized
            Polars frame (same schema across providers).
        providers: optional explicit chain; defaults to chain_for(dataset).

    Returns:
        The merged frame (possibly empty).
    """
    chain = providers or chain_for(dataset)
    key_cols = {"daily": ["symbol", "date"], "minute": ["symbol", "datetime"], "adj_factor": ["symbol", "trade_date"]}.get(
        dataset, ["symbol"]
    )
    merged = pl.DataFrame()
    for name in chain:
        try:
            provider = _get_provider(name)
        except Exception as e:  # noqa: BLE001
            logger.warning("chain[%s]: provider %s unavailable: %s", dataset, name, e)
            continue
        try:
            frame = fetch(provider)
        except Exception as e:  # noqa: BLE001
            logger.warning("chain[%s]: provider %s failed: %s", dataset, name, e)
            continue
        if frame is None or frame.is_empty():
            logger.info("chain[%s]: provider %s returned no rows", dataset, name)
            continue
        # Drop rows already covered by an earlier provider (gap merge).
        if not merged.is_empty() and key_cols and all(c in frame.columns for c in key_cols):
            covered = merged.select(key_cols).unique()
            frame = frame.join(covered, on=key_cols, how="anti")
            if frame.is_empty():
                logger.info("chain[%s]: provider %s fully covered", dataset, name)
                continue
        merged = pl.concat([merged, frame], how="diagonal_relaxed") if not merged.is_empty() else frame
        logger.info("chain[%s]: provider %s added %d rows", dataset, name, frame.height)
    return merged


def health_check(name: str) -> str:
    """Lightweight health probe for a chain provider. Returns ok/warn/error."""
    if name == "tickflow":
        return "ok"
    if name in {"free_stockdb", "xyz"}:
        try:
            provider = _get_provider(name)
            probe = provider.get_daily(["000001"]) if hasattr(provider, "get_daily") else None
            return "ok" if probe is not None and not probe.is_empty() else "warn"
        except Exception as e:  # noqa: BLE001
            logger.warning("health[%s]: %s", name, e)
            return "error"
    return "unknown"
