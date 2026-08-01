"""Deterministic multi-factor composite models (FACT-03).

Composite computation is deterministic and ML-free: each revision's values come
exclusively from the shared signal chain, and the composite is a cross-sectional
z-score combination across revisions.  Equal-weight uses the mean of per-revision
z-scores; IC-weighted uses ``w_r = mean_ic_r / sum(mean_ic)`` where mean IC comes
from recorded evaluation evidence (NOT ICIR — CONTEXT decision).

Every model definition is persisted immutably to ``factor_model_models`` and each
computation appends one immutable output row to ``factor_model_composites`` with
``input_snapshot_sha256`` and ``output_sha256``.  Phase 11 consumes composites by
snapshot, never a live module hand-off.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Literal, Mapping
import uuid

import polars as pl

from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository
from app.research.signal_chain import FactorSignalChain, SignalChainConfig


CompositeWeighting = Literal["equal", "ic_weighted"]


@dataclass(frozen=True, slots=True)
class CompositeModel:
    """Immutable composite-model definition bound to its input snapshot."""

    model_id: str
    name: str
    revision_ids: tuple[str, ...]
    weighting: CompositeWeighting
    weights: Mapping[str, float]
    input_snapshot_sha256: str
    created_at: str
    frame: pl.DataFrame = field(default_factory=pl.DataFrame)

    @property
    def composite(self) -> pl.DataFrame:
        """The deterministic [symbol, date, composite] output frame."""
        return self.frame


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _input_snapshot_sha256(
    *,
    revision_ids: tuple[str, ...],
    weighting: CompositeWeighting,
    membership_fingerprint: str,
    panel_fingerprints: Mapping[str, str],
    mean_ics: Mapping[str, float],
) -> str:
    payload = json.dumps(
        {
            "revision_ids": sorted(revision_ids),
            "weighting": weighting,
            "membership_fingerprint": membership_fingerprint,
            "panel_fingerprints": panel_fingerprints,
            "mean_ics": mean_ics,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _chain_config(universe: str, start, end, symbols: tuple[str, ...]) -> SignalChainConfig:
    return SignalChainConfig(
        universe=universe,
        symbols=symbols,
        asset_type="stock",
        start=start,
        end=end,
        warmup_days=0,
        forward_return_horizon=1,
    )


def _collect_mean_ics(repo: ResearchRepository, revision_ids: tuple[str, ...]) -> dict[str, float]:
    """Resolve per-revision mean IC from the latest recorded evaluation evidence."""
    experiments = repo.list_experiments()
    latest_by_revision: dict[str, Mapping[str, Any]] = {}
    for experiment in experiments:
        if experiment.get("factor_revision_id") in revision_ids:
            latest_by_revision[experiment["factor_revision_id"]] = experiment
    mean_ics: dict[str, float] = {}
    for revision_id in revision_ids:
        snapshot = latest_by_revision.get(revision_id)
        if snapshot is None:
            raise ValueError(f"no recorded evaluation evidence for factor revision: {revision_id}")
        summary = snapshot.get("metrics", {}).get("ic_summary", {})
        mean = summary.get("mean")
        if mean is None:
            raise ValueError(f"recorded evaluation evidence for {revision_id} has no mean IC")
        mean_ics[revision_id] = float(mean)
    return mean_ics


def build_composite(
    repo: ResearchRepository,
    *,
    engine: Any,
    registry: FactorRegistry,
    revision_ids: tuple[str, ...] | list[str],
    weighting: CompositeWeighting,
    universe: str,
    start,
    end,
    symbols: tuple[str, ...] | None = None,
    universe_resolver: object | None = None,
    name: str | None = None,
    persist: bool = True,
) -> CompositeModel:
    """Build a deterministic composite over the given admitted revisions."""
    if weighting not in {"equal", "ic_weighted"}:
        raise ValueError("weighting must be equal or ic_weighted")
    ordered = tuple(sorted(set(revision_ids)))
    if not ordered:
        raise ValueError("at least one factor revision is required")
    for revision_id in ordered:
        if registry.get_revision(revision_id) is None:
            raise ValueError(f"factor revision does not exist: {revision_id}")

    chain = FactorSignalChain(engine, registry, universe_resolver)
    signal_frames = []
    panel_fingerprints: dict[str, str] = {}
    membership_fingerprint = ""
    for revision_id in ordered:
        if symbols is None:
            revision = registry.get_revision(revision_id)
            assert revision is not None
            resolved_symbols = tuple(sorted(revision.fields)) if revision.fields else ()
        else:
            resolved_symbols = symbols
        config = _chain_config(universe, start, end, resolved_symbols)
        signal = chain.compute(revision_id=revision_id, config=config)
        signal_frames.append(signal)
        panel_fingerprints[revision_id] = signal.panel_fingerprint
        if not membership_fingerprint:
            membership_fingerprint = signal.resolved_universe.get("membership_fingerprint", "")

    if weighting == "ic_weighted":
        mean_ics = _collect_mean_ics(repo, ordered)
        total = sum(mean_ics.values())
        if total <= 0:
            raise ValueError("sum of mean IC weights must be positive")
        weights = {revision_id: mean_ics[revision_id] / total for revision_id in ordered}
    else:
        mean_ics = {}
        weights = {revision_id: 1.0 / len(ordered) for revision_id in ordered}

    input_snapshot_sha256 = _input_snapshot_sha256(
        revision_ids=ordered,
        weighting=weighting,
        membership_fingerprint=membership_fingerprint,
        panel_fingerprints=panel_fingerprints,
        mean_ics=mean_ics,
    )

    zframes = []
    for revision_id, signal in zip(ordered, signal_frames):
        weight = weights[revision_id]
        z = signal.frame.select(
            [
                pl.col("symbol"),
                pl.col("date"),
                (pl.col("_zscore") * weight).cast(pl.Float64).alias(f"_z_{revision_id}"),
            ]
        )
        zframes.append(z)
    combined = zframes[0]
    for z in zframes[1:]:
        combined = combined.join(z, on=["symbol", "date"], how="full")

    if weighting == "equal":
        composite_expr = pl.mean_horizontal(
            [pl.col(f"_z_{revision_id}") for revision_id in ordered]
        ).alias("composite")
    else:
        composite_expr = sum(
            pl.col(f"_z_{revision_id}") for revision_id in ordered
        ).alias("composite")
    composite = combined.with_columns(composite_expr.cast(pl.Float64)).select(
        ["symbol", "date", "composite"]
    )
    composite = composite.sort(["date", "symbol"])

    model = CompositeModel(
        model_id=uuid.uuid4().hex,
        name=name or f"composite-{'-'.join(ordered[:2])}",
        revision_ids=ordered,
        weighting=weighting,
        weights=weights,
        input_snapshot_sha256=input_snapshot_sha256,
        created_at=_now(),
        frame=composite,
    )
    if persist:
        repo.insert_model_definition(
            model_id=model.model_id,
            name=model.name,
            weighting=weighting,
            revision_ids=ordered,
            weights=weights,
            input_snapshot_sha256=input_snapshot_sha256,
        )
    return model
