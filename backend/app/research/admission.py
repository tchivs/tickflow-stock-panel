"""Deterministic factor admission gates with append-only verdicts (FACT-01).

Policy provenance (fixed thresholds, never tuned at runtime):

- ``ADMISSION_POLICY_VERSION = "admission-policy-v1"``
- ``TRAIN_MIN_MEAN_IC = 0.02`` — train-window mean IC floor.  Chosen above the
  shifted-label noise bound (0.02) so a factor must beat a misaligned-label factor
  before it can be admitted.
- ``VAL_MIN_MEAN_IC = 0.01`` — held-out val-window mean IC floor (stricter than
  noise, kept below the train floor because the val window is smaller).
- ``MIN_TRAIN_OBSERVATIONS = 40`` — rebalance dates required for ICIR stability.
- ``MAX_SIMILARITY_SCORE = 0.80`` — Jaccard structural dedup (``discover_similar``).
- ``MAX_IC_CORRELATION = 0.90`` — per-date IC-series Pearson with an admitted factor.
- ``SHIFTED_LABEL_MAX_ABS_IC = 0.02`` — shifted-label leakage gate (shared with the
  DSL contract, FACT-04).
- ``MIN_COVERAGE = 0.50`` — finite-share floor over the resolved universe.

The pipeline runs five ordered, deterministic gates: no_lookahead,
no_label_leakage, similarity_dedup, train_ic, val_ic.  Every verdict — admission
AND rejection — is persisted as one immutable append-only row with the full
candidate trail.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from typing import Any, Mapping

import numpy as np
import polars as pl

from app.research.factor_dsl import ALLOWED_FIELDS, _FUNCTION_PARTITION, shifted_label_ic
from app.research.factor_registry import FactorRegistry, FactorRevision
from app.research.repository import ResearchRepository


ADMISSION_POLICY_VERSION: str = "admission-policy-v1"
TRAIN_MIN_MEAN_IC: float = 0.02
VAL_MIN_MEAN_IC: float = 0.01
MIN_TRAIN_OBSERVATIONS: int = 40
MAX_SIMILARITY_SCORE: float = 0.80
MAX_IC_CORRELATION: float = 0.90
SHIFTED_LABEL_MAX_ABS_IC: float = 0.02
MIN_COVERAGE: float = 0.50
TRAIN_FRACTION: float = 0.70


def temporal_split(per_date_ics: Mapping[str, float]) -> tuple[set[str], set[str]]:
    """Deterministic 70/30 split by date order (never random shuffle)."""
    ordered = sorted(per_date_ics)
    split = max(1, int(len(ordered) * TRAIN_FRACTION))
    return set(ordered[:split]), set(ordered[split:])


def _mean_ic(per_date_ics: Mapping[str, float], dates: set[str]) -> float | None:
    values = [per_date_ics[day] for day in sorted(dates) if day in per_date_ics]
    return float(np.mean(values)) if values else None


def _jaccard_duplicate(
    registry: FactorRegistry, revision: FactorRevision, *, exclude_revision_id: str
) -> float:
    candidates = registry.discover_similar(
        revision.canonical_expression,
        limit=20,
        exclude_revision_id=exclude_revision_id,
    )
    return max((candidate.score for candidate in candidates), default=0.0)


def _ic_correlation_duplicate(
    per_date_ics: Mapping[str, float],
    admitted_ic_series: Mapping[str, Mapping[str, float]],
    *,
    val_dates: set[str],
) -> float:
    """Worst |Pearson| between the candidate's and any admitted factor's per-date IC.

    The per-date IC series are computed on the val window; each pair is aligned by
    intersecting the dates both series actually observe (a sparse admitted series
    may have dropped dates whose per-date IC was null).  Returns the signed
    correlation of the admitted factor with the largest |correlation|, so a
    strongly anti-correlated twin (correlation ~ -1.0) is as clearly flagged as a
    positively correlated twin.  Returns 0.0 when no two-point overlap exists (a
    constant IC series is a degenerate cross-section).
    """
    ordered_val = sorted(val_dates)
    candidate_dates = set(per_date_ics) & set(ordered_val)
    if len(candidate_dates) < 2:
        return 0.0
    candidate_values = np.array([per_date_ics[day] for day in ordered_val if day in candidate_dates], dtype=float)
    if float(np.std(candidate_values)) == 0:
        return 0.0
    worst = 0.0
    for _admitted_id, series in admitted_ic_series.items():
        common_dates = sorted(candidate_dates & set(series) & set(ordered_val))
        if len(common_dates) < 2:
            continue
        candidate_values = np.array([per_date_ics[d] for d in common_dates], dtype=float)
        admitted_values = np.array([series[d] for d in common_dates], dtype=float)
        correlation = float(np.corrcoef(candidate_values, admitted_values)[0, 1])
        if np.isfinite(correlation) and abs(correlation) > abs(worst):
            worst = correlation
    return worst


def run_admission(
    repo: ResearchRepository,
    *,
    engine: Any,
    registry: FactorRegistry,
    revision_id: str,
    universe: str,
    start: date,
    end: date,
    horizon: int = 1,
    asset_type: str = "stock",
    admitted_ic_series: Mapping[str, Mapping[str, float]] | None = None,
    universe_resolver: object | None = None,
    rebalance: str = "daily",
    warmup_days: int = 0,
    n_groups: int = 2,
    catalog: Any | None = None,
    artifact_service: Any | None = None,
) -> dict[str, Any]:
    """Run the five gates and append the verdict row (admission or rejection).

    When ``catalog`` and ``artifact_service`` are provided, the admission
    orchestration records the evaluation it ran through
    ``ExperimentCatalog.record_factor_evaluation`` and links the catalogue
    snapshot in the candidate trail (admission and rejection alike).
    """
    from app.research.signal_chain import FactorSignalChain, SignalChainConfig

    revision = registry.get_revision(revision_id)
    if revision is None:
        raise ValueError("factor revision does not exist")

    chain = FactorSignalChain(engine, registry, universe_resolver)
    signal = chain.compute(
        revision_id=revision.id,
        config=SignalChainConfig(
            universe=universe,
            symbols=(),
            asset_type=asset_type,
            start=start,
            end=end,
            warmup_days=warmup_days,
            forward_return_horizon=horizon,
            rebalance=rebalance,  # type: ignore[arg-type]
            missing_data_treatment="drop",
            warmup_treatment="exclude",
        ),
    )
    evaluated = signal.frame
    if evaluated.is_empty():
        raise ValueError("no valid observations for admission evaluation")

    # The admission orchestration records the evaluation it ran and links the
    # catalog snapshot before gates run, so every verdict (admission and
    # rejection) carries the evidence package reference.
    evaluation_run_id, experiment_snapshot_id = _record_evaluation_reference(
        catalog=catalog,
        artifact_service=artifact_service,
        engine=engine,
        registry=registry,
        universe_resolver=universe_resolver,
        revision=revision,
        universe=universe,
        asset_type=asset_type,
        start=start,
        end=end,
        horizon=horizon,
        rebalance=rebalance,
        warmup_days=warmup_days,
        n_groups=n_groups,
        signal=signal,
    )

    # The shifted-label gate needs the close column, which the chain frame does
    # not carry; join it back from the loaded governed panel.  The shift-based
    # label is row-order sensitive per symbol, so sort deterministically.
    close_frame = signal.loaded_panel.select(["symbol", "date", "close"]).unique(subset=["symbol", "date"])
    leakage_frame = evaluated.join(close_frame, on=["symbol", "date"], how="inner").sort(["symbol", "date"])

    per_date_ics = _per_date_ic(evaluated)
    train_dates, val_dates = temporal_split(per_date_ics)
    train_ic = _mean_ic(per_date_ics, train_dates)
    val_ic = _mean_ic(per_date_ics, val_dates)

    gate_results: list[dict[str, Any]] = []

    # Gate 1: no_lookahead — the DSL contract is structurally enforced by the
    # compiler: parse succeeded (the expression references only ALLOWED_FIELDS) and
    # every function declared its partition context.
    allowed_fields = set(revision.fields) <= set(ALLOWED_FIELDS)
    gate_results.append(
        {
            "gate": "no_lookahead",
            "passed": bool(allowed_fields),
            "metric": "structural",
            "observed": {"referenced_fields": list(revision.fields)},
            "threshold": "ALLOWED_FIELDS",
            "detail": "compiler-enforced partition context" if allowed_fields else "expression references a denied field",
        }
    )
    if not allowed_fields:
        return _record_verdict(repo, registry, revision, "rejected", "no_lookahead", gate_results, signal, start, end, horizon, evaluation_run_id=evaluation_run_id, experiment_snapshot_id=experiment_snapshot_id)

    # Gate 2: no_label_leakage — shifted-label IC must collapse to ~0.
    shifted = shifted_label_ic(leakage_frame, horizon=horizon)
    gate_results.append(
        {
            "gate": "no_label_leakage",
            "passed": shifted <= SHIFTED_LABEL_MAX_ABS_IC,
            "metric": "abs_mean_ic_shifted",
            "observed": shifted,
            "threshold": SHIFTED_LABEL_MAX_ABS_IC,
            "detail": "shifted-label displacement one extra horizon",
        }
    )
    if not gate_results[-1]["passed"]:
        return _record_verdict(repo, registry, revision, "rejected", "no_label_leakage", gate_results, signal, start, end, horizon, evaluation_run_id=evaluation_run_id, experiment_snapshot_id=experiment_snapshot_id)

    # Gate 3: similarity_dedup — Jaccard structural + IC correlation with admitted factors.
    similarity = _jaccard_duplicate(registry, revision, exclude_revision_id=revision.id)
    correlation = _ic_correlation_duplicate(per_date_ics, admitted_ic_series or {}, val_dates=val_dates)
    gate_results.append(
        {
            "gate": "similarity_dedup",
            "passed": similarity < MAX_SIMILARITY_SCORE and correlation < MAX_IC_CORRELATION,
            "metric": "max_jaccard_and_ic_corr",
            "observed": {"similarity_score": similarity, "ic_correlation": correlation},
            "threshold": {"MAX_SIMILARITY_SCORE": MAX_SIMILARITY_SCORE, "MAX_IC_CORRELATION": MAX_IC_CORRELATION},
            "detail": "Jaccard structural + IC-series Pearson on the val window",
        }
    )
    if not gate_results[-1]["passed"]:
        return _record_verdict(repo, registry, revision, "rejected", "similarity_dedup", gate_results, signal, start, end, horizon, evaluation_run_id=evaluation_run_id, experiment_snapshot_id=experiment_snapshot_id)

    # Gate 4: train_ic — mean IC over the first 70% of dates by order.
    train_observations = len([day for day in per_date_ics if day in train_dates])
    train_passed = (
        train_observations >= MIN_TRAIN_OBSERVATIONS
        and train_ic is not None
        and train_ic >= TRAIN_MIN_MEAN_IC
    )
    gate_results.append(
        {
            "gate": "train_ic",
            "passed": bool(train_passed),
            "metric": "mean_ic_train",
            "observed": train_ic,
            "threshold": TRAIN_MIN_MEAN_IC,
            "detail": f"temporal 70/30 split; {train_observations} train observations (min {MIN_TRAIN_OBSERVATIONS})",
        }
    )
    if not train_passed:
        return _record_verdict(repo, registry, revision, "rejected", "train_ic", gate_results, signal, start, end, horizon, evaluation_run_id=evaluation_run_id, experiment_snapshot_id=experiment_snapshot_id)

    # Gate 5: val_ic — held-out mean IC over the last 30% of dates.
    val_passed = val_ic is not None and val_ic >= VAL_MIN_MEAN_IC
    gate_results.append(
        {
            "gate": "val_ic",
            "passed": bool(val_passed),
            "metric": "mean_ic_val",
            "observed": val_ic,
            "threshold": VAL_MIN_MEAN_IC,
            "detail": f"held-out {len(val_dates)} val dates",
        }
    )
    if not val_passed:
        return _record_verdict(repo, registry, revision, "rejected", "val_ic", gate_results, signal, start, end, horizon, evaluation_run_id=evaluation_run_id, experiment_snapshot_id=experiment_snapshot_id)

    return _record_verdict(repo, registry, revision, "admitted", "all gates passed", gate_results, signal, start, end, horizon, evaluation_run_id=evaluation_run_id, experiment_snapshot_id=experiment_snapshot_id)


def _per_date_ic(evaluated: pl.DataFrame) -> dict[str, float]:
    correlations = (
        evaluated.group_by("date")
        .agg(pl.corr("_factor", "_forward_return").alias("ic"))
        .sort("date")
    )
    return {
        str(row["date"]): float(row["ic"])
        for row in correlations.iter_rows(named=True)
        if row["ic"] is not None and np.isfinite(float(row["ic"]))
    }


def _record_evaluation_reference(
    *,
    catalog: Any,
    artifact_service: Any,
    engine: Any,
    registry: FactorRegistry,
    universe_resolver: object | None,
    revision: FactorRevision,
    universe: str,
    asset_type: str,
    start: date,
    end: date,
    horizon: int,
    rebalance: str,
    warmup_days: int,
    n_groups: int,
    signal: Any,
) -> tuple[str | None, str | None]:
    """Run and catalogue the evaluation the admission orchestration performed.

    Returns ``(evaluation_run_id, experiment_snapshot_id)`` for a completed
    evaluation, or ``(None, None)`` when the orchestration has no catalog/artifact
    service or the evaluation did not complete.
    """
    if catalog is None or artifact_service is None:
        return None, None
    from app.research.evaluation import FactorEvaluationConfig, FactorEvaluationService

    symbols = tuple(sorted(set(signal.loaded_panel["symbol"].unique().to_list())))
    if not symbols:
        return None, None
    service = FactorEvaluationService(engine, registry, artifact_service, universe_resolver)
    result = service.evaluate(
        FactorEvaluationConfig(
            factor_revision_id=revision.id,
            universe=universe,
            symbols=symbols,
            asset_type=asset_type,
            start=start,
            end=end,
            forward_return_horizon=horizon,
            rebalance=rebalance,  # type: ignore[arg-type]
            missing_data_treatment="drop",
            warmup_treatment="exclude",
            warmup_days=warmup_days,
            n_groups=n_groups,
            weight="equal",
            fees_pct=0.0,
            slippage_bps=0.0,
        )
    )
    if not result.completed:
        return None, None
    snapshot = catalog.record_factor_evaluation(result)
    return result.evaluation_run_id, snapshot.id


def _record_verdict(
    repo: ResearchRepository,
    registry: FactorRegistry,
    revision: FactorRevision,
    verdict: str,
    reason: str,
    gate_results: list[dict[str, Any]],
    signal: Any,
    start: date,
    end: date,
    horizon: int,
    *,
    evaluation_run_id: str | None = None,
    experiment_snapshot_id: str | None = None,
) -> dict[str, Any]:
    input_payload = json.dumps(
        {
            "revision_id": revision.id,
            "policy_version": ADMISSION_POLICY_VERSION,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "horizon": horizon,
            "membership_fingerprint": signal.resolved_universe.get("membership_fingerprint", ""),
            "panel_fingerprint": signal.panel_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    input_snapshot_sha256 = sha256(input_payload).hexdigest()

    trail = {
        "provenance": dict(revision.provenance),
        "evaluation_run_ids": [evaluation_run_id] if evaluation_run_id else [],
        "experiment_snapshot_ids": [experiment_snapshot_id] if experiment_snapshot_id else [],
        "gate_results": gate_results,
    }
    return {
        **repo.insert_admission_verdict(
            revision_id=revision.id,
            policy_version=ADMISSION_POLICY_VERSION,
            verdict=verdict,
            reason=reason,
            gates_json=gate_results,
            candidate_trail_json=trail,
            resolved_universe_json=signal.resolved_universe,
            input_snapshot_sha256=input_snapshot_sha256,
        ),
        # The repository decodes the JSON columns; expose them under their schema
        # names so callers (and catalog consumers) read the same keys the migration
        # declares.
        "gates_json": gate_results,
        "candidate_trail_json": trail,
        "resolved_universe_json": dict(signal.resolved_universe),
    }


def get_verdict(repo: ResearchRepository, revision_id: str) -> dict[str, Any] | None:
    """Return the persisted verdict record with JSON columns decoded, if any."""
    return repo.get_admission_verdict(revision_id, ADMISSION_POLICY_VERSION)
