"""Immutable local experiment catalog and transparent evidence comparison.

The catalog stores provenance snapshots only.  It neither executes experiments nor
reads managed artifacts, so comparison remains a metadata-only operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, TYPE_CHECKING
import uuid

from app.research.artifacts import ArtifactDescriptor
from app.research.repository import ResearchRepository

if TYPE_CHECKING:
    from app.backtest.strategy import StrategyBacktestResult
    from app.research.evaluation import FactorEvaluationResult


EXPERIMENT_STATUSES = frozenset({"draft", "running", "completed", "failed", "cancelled", "invalid"})
COMPARABLE_STATUS = "completed"


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise ValueError(f"{field} is required")
    return normalized


def _mapping(value: Mapping[str, Any] | None, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    return dict(value)


def _normalise(value: Any) -> Any:
    """Return stable JSON-shaped metadata without invoking arbitrary serializers."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _normalise(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    raise ValueError("experiment metadata must contain only JSON values")


def _value_at(record: Mapping[str, Any], *paths: Sequence[str]) -> Any:
    for path in paths:
        current: Any = record
        for key in path:
            if not isinstance(current, Mapping) or key not in current:
                break
            current = current[key]
        else:
            return current
    return None


def _diagnostics(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (list, tuple)):
        return {"messages": list(value)}
    raise ValueError("diagnostics must be a mapping or sequence")


def _artifact_descriptor(value: ArtifactDescriptor | Mapping[str, Any]) -> ArtifactDescriptor:
    if isinstance(value, ArtifactDescriptor):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("artifact descriptor must be a managed ArtifactDescriptor")
    return ArtifactDescriptor(
        evaluation_run_id=_required_text(str(value.get("evaluation_run_id", "")), "artifact evaluation_run_id"),
        relative_path=_required_text(str(value.get("relative_path", "")), "artifact relative_path"),
        content_type=_required_text(str(value.get("content_type", "")), "artifact content_type"),
        byte_size=value.get("byte_size", -1),
        checksum_sha256=_required_text(str(value.get("checksum_sha256", "")), "artifact checksum_sha256"),
        created_at=_required_text(str(value.get("created_at", "")), "artifact created_at"),
    )

@dataclass(frozen=True, slots=True)
class ModelProvenance:
    provider: str
    model: str
    model_version: str | None
    provenance: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ModelProvenance":
        if not isinstance(value, Mapping):
            raise ValueError("model provenance must be a mapping")
        model_version = value.get("model_version")
        if model_version is not None and not isinstance(model_version, str):
            raise ValueError("model_version must be a string when supplied")
        return cls(
            provider=_required_text(str(value.get("provider", "")), "model provider"),
            model=_required_text(str(value.get("model", "")), "model"),
            model_version=model_version,
            provenance=_mapping(value.get("provenance"), "model provenance payload"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "provenance": _normalise(self.provenance),
        }


@dataclass(frozen=True, slots=True)
class FactorEvidencePackage:
    """Trusted boundary payload for a completed factor-evaluation evidence package."""

    evaluation_run_id: str
    factor_revision_id: str
    resolved_config: Mapping[str, Any]
    input_manifest: Mapping[str, Any]
    metrics: Mapping[str, Any]
    prediction_signals: Mapping[str, Any]
    artifacts: tuple[ArtifactDescriptor, ...]
    diagnostics: Mapping[str, Any]
    model_provenance: ModelProvenance | None = None


@dataclass(frozen=True, slots=True)
class ExperimentSnapshot:
    """Self-contained immutable snapshot returned from the catalog, never a live definition."""

    id: str
    originating_run_id: str
    status: str
    validated: bool
    retained_at: str | None
    factor_revision_id: str | None
    strategy_id: str | None
    strategy_version: str | None
    resolved_config: Mapping[str, Any]
    input_manifest: Mapping[str, Any]
    prediction_signals: Mapping[str, Any]
    metrics: Mapping[str, Any]
    artifacts: tuple[ArtifactDescriptor, ...]
    diagnostics: Mapping[str, Any]
    model_provenance: ModelProvenance | None
    created_at: str

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ExperimentSnapshot":
        model = record.get("model_provenance")
        return cls(
            id=str(record["id"]),
            originating_run_id=str(record["originating_run_id"]),
            status=str(record["status"]),
            validated=bool(record["validated"]),
            retained_at=record.get("retained_at"),
            factor_revision_id=record.get("factor_revision_id"),
            strategy_id=record.get("strategy_id"),
            strategy_version=record.get("strategy_version"),
            resolved_config=dict(record["resolved_config"]),
            input_manifest=dict(record["input_manifest"]),
            prediction_signals=dict(record["prediction_signals"]),
            metrics=dict(record["metrics"]),
            artifacts=tuple(_artifact_descriptor(item) for item in record["artifacts"]),
            diagnostics=dict(record["diagnostics"]),
            model_provenance=None if model is None else ModelProvenance.from_mapping(model),
            created_at=str(record["created_at"]),
        )

    @property
    def subject(self) -> Mapping[str, str]:
        if self.factor_revision_id is not None:
            return {"kind": "factor", "revision_id": self.factor_revision_id}
        return {"kind": "strategy", "id": self.strategy_id or "", "version": self.strategy_version or ""}

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "originating_run_id": self.originating_run_id,
            "status": self.status,
            "validated": self.validated,
            "retained_at": self.retained_at,
            "subject": dict(self.subject),
            "resolved_config": _normalise(self.resolved_config),
            "input_manifest": _normalise(self.input_manifest),
            "prediction_signals": _normalise(self.prediction_signals),
            "metrics": _normalise(self.metrics),
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
            "diagnostics": _normalise(self.diagnostics),
            "model_provenance": None if self.model_provenance is None else self.model_provenance.as_dict(),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class ExperimentComparison:
    """Side-by-side retained snapshots, normalized differences, and compatibility warnings."""

    experiments: tuple[ExperimentSnapshot, ...]
    deltas: Mapping[str, Mapping[str, Any]]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "experiments": [experiment.as_dict() for experiment in self.experiments],
            "deltas": _normalise(self.deltas),
            "warnings": list(self.warnings),
        }


class ExperimentCatalog:
    """Creates immutable evidence snapshots and compares only explicitly retained evidence."""

    def __init__(self, repository: ResearchRepository) -> None:
        self.repository = repository

    def record_factor_evaluation(
        self,
        result: "FactorEvaluationResult",
        *,
        model_provenance: Mapping[str, Any] | None = None,
        prediction_signals: Mapping[str, Any] | None = None,
    ) -> ExperimentSnapshot:
        """Persist a completed evaluator result through the trusted server-side boundary."""
        status = getattr(result, "status", None)
        if status != COMPARABLE_STATUS:
            raise ValueError("only completed factor evaluation results can be catalogued")
        revision = getattr(result, "factor_revision", None)
        revision_id = revision.get("id") if isinstance(revision, Mapping) else getattr(revision, "id", None)
        package = FactorEvidencePackage(
            evaluation_run_id=_required_text(str(getattr(result, "evaluation_run_id", "")), "evaluation_run_id"),
            factor_revision_id=_required_text(str(revision_id or ""), "factor_revision_id"),
            resolved_config=_mapping(getattr(result, "resolved_config", None), "resolved_config"),
            input_manifest=_mapping(getattr(result, "input_manifest", None), "input_manifest"),
            metrics={
                "ic_series": getattr(result, "ic_series", []),
                "rank_ic_series": getattr(result, "rank_ic_series", []),
                "ic_summary": getattr(result, "ic_summary", {}),
                "rank_ic_summary": getattr(result, "rank_ic_summary", {}),
                "icir": getattr(result, "icir", None),
                "monthly_robustness": getattr(result, "monthly_robustness", None),
                "coverage": getattr(result, "coverage", {}),
                "monthly_ic_series": getattr(result, "monthly_ic_series", []),
                "group_stats": getattr(result, "group_stats", {}),
                "group_nav": getattr(result, "group_nav", []),
                "long_short_stats": getattr(result, "long_short_stats", {}),
                "long_short_nav": getattr(result, "long_short_nav", []),
            },
            prediction_signals=(
                _mapping(prediction_signals, "prediction_signals")
                if prediction_signals is not None
                else {"signal_artifact_paths": [artifact.relative_path for artifact in getattr(result, "artifacts", ())]}
            ),
            artifacts=tuple(_artifact_descriptor(item) for item in getattr(result, "artifacts", ())),
            diagnostics=_diagnostics(getattr(result, "diagnostics", None)),
            model_provenance=None if model_provenance is None else ModelProvenance.from_mapping(model_provenance),
        )
        return self.record_factor_evidence(package)

    def record_factor_evidence(self, package: FactorEvidencePackage) -> ExperimentSnapshot:
        """Persist completed, validated factor evidence without retaining it automatically."""
        return self._record(
            originating_run_id=package.evaluation_run_id,
            status=COMPARABLE_STATUS,
            validated=True,
            factor_revision_id=package.factor_revision_id,
            strategy_id=None,
            strategy_version=None,
            resolved_config=package.resolved_config,
            input_manifest=package.input_manifest,
            prediction_signals=package.prediction_signals,
            metrics=package.metrics,
            artifacts=package.artifacts,
            diagnostics=package.diagnostics,
            model_provenance=package.model_provenance,
        )

    def record_strategy_backtest(
        self,
        result: "StrategyBacktestResult",
        *,
        strategy_id: str,
        strategy_version: str,
        input_manifest: Mapping[str, Any],
        artifacts: Sequence[ArtifactDescriptor | Mapping[str, Any]] = (),
        validated: bool = True,
        model_provenance: Mapping[str, Any] | None = None,
    ) -> ExperimentSnapshot:
        """Persist only an existing, successful server-issued registered strategy result."""
        from app.backtest.strategy import StrategyBacktestResult

        if not isinstance(result, StrategyBacktestResult):
            raise ValueError("strategy result must be a server-issued StrategyBacktestResult")
        if not isinstance(validated, bool) or not validated:
            raise ValueError("strategy result must be validated before cataloguing")
        if getattr(result, "error", None):
            raise ValueError("only successful strategy backtest results can be catalogued")
        source = getattr(result, "strategy_info")
        if not isinstance(source, Mapping) or source.get("id") != strategy_id:
            raise ValueError("strategy identity must match the registered server result")
        descriptors = tuple(
            _artifact_descriptor(artifact) for artifact in artifacts
        )
        return self._record(
            originating_run_id=_required_text(str(getattr(result, "run_id", "")), "strategy run_id"),
            status=COMPARABLE_STATUS,
            validated=True,
            factor_revision_id=None,
            strategy_id=_required_text(strategy_id, "strategy_id"),
            strategy_version=_required_text(strategy_version, "strategy_version"),
            resolved_config=_mapping(getattr(result, "config", None), "strategy config"),
            input_manifest=_mapping(input_manifest, "input_manifest"),
            prediction_signals={
                "trades": getattr(result, "trades", []),
                "equity_curve": getattr(result, "equity_curve", []),
                "drawdown_curve": getattr(result, "drawdown_curve", []),
                "benchmark_curve": getattr(result, "benchmark_curve", []),
            },
            metrics={"stats": getattr(result, "stats", {}), "per_symbol_stats": getattr(result, "per_symbol_stats", [])},
            artifacts=descriptors,
            diagnostics={"elapsed_ms": getattr(result, "elapsed_ms", 0.0), "strategy_source": source.get("source")},
            model_provenance=None if model_provenance is None else ModelProvenance.from_mapping(model_provenance),
        )

    def record_diagnostic(
        self,
        *,
        originating_run_id: str,
        status: str,
        validated: bool,
        factor_revision_id: str | None = None,
        strategy_id: str | None = None,
        strategy_version: str | None = None,
        resolved_config: Mapping[str, Any] | None = None,
        input_manifest: Mapping[str, Any] | None = None,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> ExperimentSnapshot:
        """Retain an audit-only draft/failure/cancellation record, never comparable evidence."""
        if status not in EXPERIMENT_STATUSES or status == COMPARABLE_STATUS:
            raise ValueError("diagnostic status must be draft, running, failed, cancelled, or invalid")
        return self._record(
            originating_run_id=_required_text(originating_run_id, "originating_run_id"),
            status=status,
            validated=validated,
            factor_revision_id=factor_revision_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            resolved_config=_mapping(resolved_config, "resolved_config"),
            input_manifest=_mapping(input_manifest, "input_manifest"),
            prediction_signals={},
            metrics={},
            artifacts=(),
            diagnostics=_mapping(diagnostics, "diagnostics"),
            model_provenance=None,
        )

    def _record(
        self,
        *,
        originating_run_id: str,
        status: str,
        validated: bool,
        factor_revision_id: str | None,
        strategy_id: str | None,
        strategy_version: str | None,
        resolved_config: Mapping[str, Any],
        input_manifest: Mapping[str, Any],
        prediction_signals: Mapping[str, Any],
        metrics: Mapping[str, Any],
        artifacts: Sequence[ArtifactDescriptor],
        diagnostics: Mapping[str, Any],
        model_provenance: ModelProvenance | None,
    ) -> ExperimentSnapshot:
        if status not in EXPERIMENT_STATUSES:
            raise ValueError("invalid experiment status")
        subject_is_factor = factor_revision_id is not None
        subject_is_strategy = strategy_id is not None or strategy_version is not None
        if subject_is_factor == subject_is_strategy:
            raise ValueError("exactly one immutable factor revision or registered strategy identity is required")
        if subject_is_factor:
            factor_revision_id = _required_text(factor_revision_id or "", "factor_revision_id")
        else:
            strategy_id = _required_text(strategy_id or "", "strategy_id")
            strategy_version = _required_text(strategy_version or "", "strategy_version")
        record = self.repository.create_experiment(
            experiment_id=uuid.uuid4().hex,
            originating_run_id=_required_text(originating_run_id, "originating_run_id"),
            status=status,
            validated=validated,
            factor_revision_id=factor_revision_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            resolved_config=_normalise(_mapping(resolved_config, "resolved_config")),
            input_manifest=_normalise(_mapping(input_manifest, "input_manifest")),
            prediction_signals=_normalise(_mapping(prediction_signals, "prediction_signals")),
            metrics=_normalise(_mapping(metrics, "metrics")),
            artifacts=[artifact.as_dict() for artifact in artifacts],
            diagnostics=_normalise(_mapping(diagnostics, "diagnostics")),
            model_provenance=None if model_provenance is None else model_provenance.as_dict(),
        )
        return ExperimentSnapshot.from_record(record)

    def get(self, experiment_id: str) -> ExperimentSnapshot | None:
        record = self.repository.get_experiment(_required_text(experiment_id, "experiment_id"))
        return None if record is None else ExperimentSnapshot.from_record(record)

    def list_history(self) -> list[ExperimentSnapshot]:
        return [ExperimentSnapshot.from_record(record) for record in self.repository.list_experiments()]

    def retain(self, experiment_id: str) -> ExperimentSnapshot:
        record = self.repository.retain_experiment(_required_text(experiment_id, "experiment_id"))
        return ExperimentSnapshot.from_record(record)

    def list_comparison_candidates(self) -> list[ExperimentSnapshot]:
        return [ExperimentSnapshot.from_record(record) for record in self.repository.list_comparison_candidates()]

    def compare(self, experiment_ids: Sequence[str]) -> ExperimentComparison:
        if len(experiment_ids) < 2:
            raise ValueError("select at least two experiment IDs to compare")
        if len(set(experiment_ids)) != len(experiment_ids):
            raise ValueError("experiment IDs must be unique")
        snapshots: list[ExperimentSnapshot] = []
        for experiment_id in experiment_ids:
            snapshot = self.get(experiment_id)
            if snapshot is None:
                raise ValueError(f"experiment {experiment_id} does not exist")
            if snapshot.status != COMPARABLE_STATUS or not snapshot.validated or snapshot.retained_at is None:
                raise ValueError(f"experiment {experiment_id} is not a retained completed validated result")
            snapshots.append(snapshot)
        return ExperimentComparison(
            experiments=tuple(snapshots),
            deltas=self._deltas(snapshots),
            warnings=self._compatibility_warnings(snapshots),
        )

    @staticmethod
    def _deltas(snapshots: Sequence[ExperimentSnapshot]) -> dict[str, dict[str, Any]]:
        fields: dict[str, list[Any]] = {
            "resolved_configuration": [_normalise(snapshot.resolved_config) for snapshot in snapshots],
            "governed_data_input": [_normalise(snapshot.input_manifest) for snapshot in snapshots],
            "predictions_signals": [_normalise(snapshot.prediction_signals) for snapshot in snapshots],
            "metrics": [_normalise(snapshot.metrics) for snapshot in snapshots],
            "artifact_descriptors": [[artifact.as_dict() for artifact in snapshot.artifacts] for snapshot in snapshots],
            "provider_model_version": [
                None if snapshot.model_provenance is None else snapshot.model_provenance.as_dict() for snapshot in snapshots
            ],
        }
        return {
            name: {
                "values": {snapshot.id: value for snapshot, value in zip(snapshots, values, strict=True)},
                "equal": all(value == values[0] for value in values[1:]),
            }
            for name, values in fields.items()
        }

    @staticmethod
    def _compatibility_warnings(snapshots: Sequence[ExperimentSnapshot]) -> tuple[str, ...]:
        configs = [snapshot.resolved_config for snapshot in snapshots]
        manifests = [snapshot.input_manifest for snapshot in snapshots]
        warnings: list[str] = []
        dimensions = (
            (
                "universe differs",
                [_value_at(config, ("universe",), ("symbols",), ("selection", "universe")) for config in configs],
            ),
            (
                "date window differs",
                [
                    (
                        _value_at(config, ("start",), ("start_date",), ("window", "start")),
                        _value_at(config, ("end",), ("end_date",), ("window", "end")),
                    )
                    for config in configs
                ],
            ),
            (
                "forward-return horizon differs",
                [
                    _value_at(
                        config,
                        ("forward_return_horizon",),
                        ("forward_horizon",),
                        ("horizon",),
                    )
                    for config in configs
                ],
            ),
            (
                "governed data manifest revision/fingerprint differs",
                [
                    (
                        _value_at(manifest, ("revision",), ("data_revision",)),
                        _value_at(manifest, ("fingerprint",), ("schema_fingerprint",)),
                    )
                    for manifest in manifests
                ],
            ),
        )
        for warning, values in dimensions:
            if len({_comparison_key(value) for value in values}) > 1:
                warnings.append(warning)
        return tuple(warnings)


def _comparison_key(value: Any) -> str:
    return repr(_normalise(value))
