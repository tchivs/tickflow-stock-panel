"""Governed evaluation of immutable factor revisions.

This module deliberately owns orchestration and evidence only.  Market panels are
loaded exclusively through :class:`BacktestEngine`; factor source is parsed by the
restricted DSL and evaluated by Polars expressions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from hashlib import sha256
import json
from typing import Any, Literal, Mapping
import uuid

import numpy as np
import polars as pl

from app.backtest.engine import BacktestEngine
from app.backtest.factor import FactorBacktestService, FactorConfig
from app.research.artifacts import ArtifactDescriptor, ArtifactWriteError, EvaluationArtifactService
from app.research.factor_dsl import FactorDslError, ParsedFactor, parse_factor
from app.research.factor_registry import FactorRegistry, FactorRevision


RebalanceCadence = Literal["daily", "weekly", "monthly"]
MissingDataTreatment = Literal["drop"]
WarmupTreatment = Literal["exclude"]


@dataclass(frozen=True, slots=True)
class ResolvedEvaluationConfig:
    """All inputs that affect a factor result, with no implicit retained defaults."""

    factor_revision_id: str
    universe: str
    symbols: tuple[str, ...]
    asset_type: str
    start: date
    end: date
    forward_return_horizon: int
    rebalance: RebalanceCadence
    missing_data_treatment: MissingDataTreatment
    warmup_treatment: WarmupTreatment
    warmup_days: int
    n_groups: int
    weight: Literal["equal", "factor_weight"]
    fees_pct: float
    slippage_bps: float

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["symbols"] = sorted(self.symbols)
        value["start"] = self.start.isoformat()
        value["end"] = self.end.isoformat()
        return value


# A concise public spelling for API and catalog callers.
FactorEvaluationConfig = ResolvedEvaluationConfig


@dataclass(frozen=True, slots=True)
class MetricSummary:
    mean: float | None
    std: float | None
    information_ratio: float | None
    positive_rate: float | None
    observations: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FactorEvaluationResult:
    """A retention-ready, immutable evidence package (not SQLite persistence)."""

    evaluation_run_id: str | None
    status: Literal["completed", "failed", "invalid"]
    factor_revision: Mapping[str, Any] | None
    resolved_config: Mapping[str, Any] | None
    input_manifest: Mapping[str, Any] | None = None
    ic_series: tuple[Mapping[str, Any], ...] = ()
    rank_ic_series: tuple[Mapping[str, Any], ...] = ()
    ic_summary: Mapping[str, Any] | None = None
    rank_ic_summary: Mapping[str, Any] | None = None
    group_stats: tuple[Mapping[str, Any], ...] = ()
    group_nav: tuple[Mapping[str, Any], ...] = ()
    long_short_stats: Mapping[str, Any] = field(default_factory=dict)
    long_short_nav: tuple[Mapping[str, Any], ...] = ()
    artifacts: tuple[ArtifactDescriptor, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_run_id": self.evaluation_run_id,
            "status": self.status,
            "factor_revision": None if self.factor_revision is None else dict(self.factor_revision),
            "resolved_config": None if self.resolved_config is None else dict(self.resolved_config),
            "input_manifest": None if self.input_manifest is None else dict(self.input_manifest),
            "ic_series": [dict(item) for item in self.ic_series],
            "rank_ic_series": [dict(item) for item in self.rank_ic_series],
            "ic_summary": None if self.ic_summary is None else dict(self.ic_summary),
            "rank_ic_summary": None if self.rank_ic_summary is None else dict(self.rank_ic_summary),
            "group_stats": [dict(item) for item in self.group_stats],
            "group_nav": [dict(item) for item in self.group_nav],
            "long_short_stats": dict(self.long_short_stats),
            "long_short_nav": [dict(item) for item in self.long_short_nav],
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
            "diagnostics": list(self.diagnostics),
        }


class FactorEvaluationService:
    """Evaluates one stored factor revision without bypassing governed panel access."""

    def __init__(
        self,
        engine: BacktestEngine,
        registry: FactorRegistry,
        artifact_service: EvaluationArtifactService,
    ) -> None:
        self.engine = engine
        self.registry = registry
        self.artifact_service = artifact_service

    def evaluate(self, config: ResolvedEvaluationConfig) -> FactorEvaluationResult:
        """Validate everything before the one and only market-panel load."""
        try:
            resolved_config = self._validate_config(config)
            revision, parsed = self._validated_revision(config.factor_revision_id)
        except (TypeError, ValueError, FactorDslError) as error:
            return FactorEvaluationResult(
                evaluation_run_id=None,
                status="invalid",
                factor_revision=None,
                resolved_config=None,
                diagnostics=(str(error),),
            )

        # Allocation precedes governed access, giving every attempted valid run an
        # opaque identity even when the lake has no usable data.
        evaluation_run_id = uuid.uuid4().hex
        revision_provenance = self._revision_provenance(revision)
        panel_columns = self._required_columns(parsed)
        load_start = config.start - timedelta(days=config.warmup_days)
        panel = self.engine.load_panel(
            list(sorted(config.symbols)),
            load_start,
            config.end,
            columns=panel_columns,
            asset_type=config.asset_type,
        )
        if panel.is_empty():
            return self._failed(evaluation_run_id, revision_provenance, resolved_config, "governed panel is empty")

        missing = sorted(set(panel_columns) - set(panel.columns))
        if missing:
            return self._failed(
                evaluation_run_id,
                revision_provenance,
                resolved_config,
                f"governed panel does not provide required fields: {', '.join(missing)}",
            )

        try:
            evaluated = self._evaluate_panel(panel, parsed, config)
        except (pl.exceptions.PolarsError, ValueError) as error:
            return self._failed(evaluation_run_id, revision_provenance, resolved_config, f"factor computation failed: {error}")
        if evaluated.is_empty():
            return self._failed(evaluation_run_id, revision_provenance, resolved_config, "no valid observations after treatments")

        manifest = self._manifest(panel, evaluated, resolved_config, panel_columns)
        ic_series, rank_ic_series = self._correlation_series(evaluated)
        if not ic_series and not rank_ic_series:
            return self._failed(
                evaluation_run_id,
                revision_provenance,
                resolved_config,
                "no cross-sectional observations available for IC or RankIC",
                manifest,
            )

        supplemental = self._supplemental_evidence(evaluated, config)
        ic_summary = self._summary(ic_series, "ic")
        rank_ic_summary = self._summary(rank_ic_series, "rank_ic")
        compact_result = {
            "evaluation_run_id": evaluation_run_id,
            "factor_revision": revision_provenance,
            "resolved_config": resolved_config,
            "input_manifest": manifest,
            "ic_summary": ic_summary,
            "rank_ic_summary": rank_ic_summary,
            "group_stats": supplemental["group_stats"],
            "long_short_stats": supplemental["long_short_stats"],
        }
        try:
            artifacts = self.artifact_service.write_bundle(
                evaluation_run_id,
                signals=self._signal_records(evaluated),
                metric_series=self._combined_metric_series(ic_series, rank_ic_series),
                result=compact_result,
            )
        except ArtifactWriteError as error:
            return self._failed(
                evaluation_run_id,
                revision_provenance,
                resolved_config,
                f"artifact write failed: {error}",
                manifest,
            )

        return FactorEvaluationResult(
            evaluation_run_id=evaluation_run_id,
            status="completed",
            factor_revision=revision_provenance,
            resolved_config=resolved_config,
            input_manifest=manifest,
            ic_series=tuple(ic_series),
            rank_ic_series=tuple(rank_ic_series),
            ic_summary=ic_summary,
            rank_ic_summary=rank_ic_summary,
            group_stats=tuple(supplemental["group_stats"]),
            group_nav=tuple(supplemental["group_nav"]),
            long_short_stats=supplemental["long_short_stats"],
            long_short_nav=tuple(supplemental["long_short_nav"]),
            artifacts=tuple(artifacts),
        )

    @staticmethod
    def _validate_config(config: ResolvedEvaluationConfig) -> dict[str, Any]:
        if not isinstance(config, ResolvedEvaluationConfig):
            raise TypeError("evaluation config must be fully resolved")
        if not isinstance(config.factor_revision_id, str) or not config.factor_revision_id:
            raise ValueError("factor_revision_id is required")
        if not isinstance(config.universe, str) or not config.universe.strip():
            raise ValueError("universe is required")
        if not config.symbols or any(not isinstance(symbol, str) or not symbol.strip() for symbol in config.symbols):
            raise ValueError("resolved symbols are required")
        if len(set(config.symbols)) != len(config.symbols):
            raise ValueError("resolved symbols must not contain duplicates")
        if config.asset_type not in {"stock", "etf"}:
            raise ValueError("asset_type must be stock or etf")
        if not isinstance(config.start, date) or not isinstance(config.end, date) or config.start > config.end:
            raise ValueError("start and end must be an ordered date range")
        if not isinstance(config.forward_return_horizon, int) or config.forward_return_horizon < 1:
            raise ValueError("forward_return_horizon must be a positive integer")
        if config.rebalance not in {"daily", "weekly", "monthly"}:
            raise ValueError("rebalance must be daily, weekly, or monthly")
        if config.missing_data_treatment != "drop":
            raise ValueError("missing_data_treatment must be explicit and supported")
        if config.warmup_treatment != "exclude":
            raise ValueError("warmup_treatment must be explicit and supported")
        if not isinstance(config.warmup_days, int) or config.warmup_days < 0:
            raise ValueError("warmup_days must be a non-negative integer")
        if not isinstance(config.n_groups, int) or config.n_groups < 2:
            raise ValueError("n_groups must be at least 2")
        if config.weight not in {"equal", "factor_weight"}:
            raise ValueError("weight must be equal or factor_weight")
        if config.fees_pct < 0 or config.slippage_bps < 0:
            raise ValueError("execution costs must be non-negative")
        return config.as_dict()

    def _validated_revision(self, revision_id: str) -> tuple[FactorRevision, ParsedFactor]:
        revision = self.registry.get_revision(revision_id)
        if revision is None:
            raise ValueError("factor revision does not exist")
        parsed = parse_factor(revision.canonical_expression)
        if parsed.dsl_version != revision.dsl_version:
            raise ValueError("stored factor revision DSL version is not supported")
        if tuple(sorted(parsed.referenced_fields)) != tuple(sorted(revision.fields)):
            raise ValueError("stored factor revision dependency fields are invalid")
        return revision, parsed

    @staticmethod
    def _required_columns(parsed: ParsedFactor) -> list[str]:
        return ["symbol", "date", "close", *sorted(field for field in parsed.referenced_fields if field != "close")]

    @staticmethod
    def _evaluate_panel(panel: pl.DataFrame, parsed: ParsedFactor, config: ResolvedEvaluationConfig) -> pl.DataFrame:
        values = (
            panel.sort(["symbol", "date"])
            .with_columns(parsed.compile().cast(pl.Float64).alias("_factor"))
            .with_columns(
                (pl.col("close").shift(-config.forward_return_horizon).over("symbol") / pl.col("close") - 1.0)
                .cast(pl.Float64)
                .alias("_forward_return")
            )
            .filter((pl.col("date") >= config.start) & (pl.col("date") <= config.end))
            .filter(
                pl.col("_factor").is_finite()
                & pl.col("_forward_return").is_finite()
                & pl.col("close").is_finite()
                & (pl.col("close") > 0)
            )
        )
        return FactorEvaluationService._rebalance(values, config.rebalance)

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
    def _correlation_series(panel: pl.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        correlations = (
            panel.group_by("date")
            .agg(
                pl.corr("_factor", "_forward_return").alias("ic"),
                pl.corr(pl.col("_factor").rank(method="average"), pl.col("_forward_return").rank(method="average")).alias("rank_ic"),
            )
            .sort("date")
        )
        ic_series: list[dict[str, Any]] = []
        rank_ic_series: list[dict[str, Any]] = []
        for row in correlations.iter_rows(named=True):
            date_text = str(row["date"])
            if row["ic"] is not None and np.isfinite(float(row["ic"])):
                ic_series.append({"date": date_text, "ic": float(row["ic"])})
            if row["rank_ic"] is not None and np.isfinite(float(row["rank_ic"])):
                rank_ic_series.append({"date": date_text, "rank_ic": float(row["rank_ic"])})
        return ic_series, rank_ic_series

    @staticmethod
    def _combined_metric_series(
        ic_series: list[Mapping[str, Any]], rank_ic_series: list[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        ic_by_date = {str(row["date"]): row["ic"] for row in ic_series}
        rank_by_date = {str(row["date"]): row["rank_ic"] for row in rank_ic_series}
        return [
            {"date": date_text, "ic": ic_by_date.get(date_text), "rank_ic": rank_by_date.get(date_text)}
            for date_text in sorted(ic_by_date.keys() | rank_by_date.keys())
        ]

    @staticmethod
    def _summary(series: list[Mapping[str, Any]], field: str) -> dict[str, Any]:
        values = [float(row[field]) for row in series]
        if not values:
            return MetricSummary(None, None, None, None, 0).as_dict()
        mean = float(np.mean(values))
        std = float(np.std(values))
        return MetricSummary(
            mean=mean,
            std=std,
            information_ratio=mean / std if std > 1e-12 else None,
            positive_rate=sum(value > 0 for value in values) / len(values),
            observations=len(values),
        ).as_dict()

    @staticmethod
    def _supplemental_evidence(panel: pl.DataFrame, config: ResolvedEvaluationConfig) -> dict[str, Any]:
        backtest_config = FactorConfig(
            factor_name="_factor",
            symbols=list(config.symbols),
            start=config.start,
            end=config.end,
            n_groups=config.n_groups,
            rebalance=config.rebalance,
            weight=config.weight,
            fees_pct=config.fees_pct,
            slippage_bps=config.slippage_bps,
            asset_type=config.asset_type,
        )
        grouped = FactorBacktestService._add_groups(panel, "_factor", config.n_groups)
        # Existing supplemental helpers use the legacy temporary name; retain no
        # ambiguity in public metrics, where IC and RankIC are separate.
        supplemental_panel = grouped.rename({"_forward_return": "_next_return"})
        group_nav = FactorBacktestService._calc_group_nav(supplemental_panel, backtest_config)
        group_stats = FactorBacktestService._calc_group_stats(group_nav, config.start, config.end, config.rebalance)
        long_short_nav, long_short_stats = FactorBacktestService._calc_long_short(group_nav, backtest_config)
        return {
            "group_stats": group_stats,
            "group_nav": group_nav,
            "long_short_stats": long_short_stats,
            "long_short_nav": long_short_nav,
        }

    @staticmethod
    def _manifest(
        loaded: pl.DataFrame,
        evaluated: pl.DataFrame,
        resolved_config: Mapping[str, Any],
        required_columns: list[str],
    ) -> dict[str, Any]:
        schema = {name: str(dtype) for name, dtype in loaded.schema.items()}
        observed_start = loaded.select(pl.col("date").min()).item()
        observed_end = loaded.select(pl.col("date").max()).item()
        source_reference = {
            "loader": "BacktestEngine.load_panel",
            "source_kind": "governed_enriched_parquet",
            "asset_type": resolved_config["asset_type"],
            "required_columns": required_columns,
            "schema": schema,
            "observed_start": str(observed_start),
            "observed_end": str(observed_end),
            "loaded_row_count": loaded.height,
            "evaluated_row_count": evaluated.height,
        }
        encoded = json.dumps(source_reference, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {
            "asset_type": resolved_config["asset_type"],
            "universe": resolved_config["universe"],
            "resolved_symbols": list(resolved_config["symbols"]),
            "requested_start": resolved_config["start"],
            "requested_end": resolved_config["end"],
            "required_source_fields": required_columns,
            "observed_start": str(observed_start),
            "observed_end": str(observed_end),
            "row_count": loaded.height,
            "schema_fingerprint": sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "source_fingerprint": sha256(encoded).hexdigest(),
            "source_reference": "BacktestEngine.load_panel/governed_enriched_parquet",
        }

    @staticmethod
    def _signal_records(panel: pl.DataFrame) -> list[dict[str, Any]]:
        return [
            {
                "symbol": str(row["symbol"]),
                "date": str(row["date"]),
                "factor": float(row["_factor"]),
                "forward_return": float(row["_forward_return"]),
            }
            for row in panel.select(["symbol", "date", "_factor", "_forward_return"]).sort(["date", "symbol"]).iter_rows(named=True)
        ]

    @staticmethod
    def _revision_provenance(revision: FactorRevision) -> dict[str, Any]:
        return {
            "id": revision.id,
            "factor_id": revision.factor_id,
            "revision_number": revision.revision_number,
            "dsl_version": revision.dsl_version,
            "canonical_expression": revision.canonical_expression,
            "ast_signature": revision.ast_signature,
        }

    @staticmethod
    def _failed(
        evaluation_run_id: str,
        revision: Mapping[str, Any],
        config: Mapping[str, Any],
        diagnostic: str,
        manifest: Mapping[str, Any] | None = None,
    ) -> FactorEvaluationResult:
        return FactorEvaluationResult(
            evaluation_run_id=evaluation_run_id,
            status="failed",
            factor_revision=revision,
            resolved_config=config,
            input_manifest=manifest,
            diagnostics=(diagnostic,),
        )


# The adapter name is intentionally explicit for callers that distinguish catalog
# orchestration from governed factor execution.
ResearchFactorEvaluator = FactorEvaluationService
