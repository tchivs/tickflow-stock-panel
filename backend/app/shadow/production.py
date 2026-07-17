"""Production adapters for governed Shadow feature derivation and evaluation."""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256

import polars as pl

from app.backtest.engine import BacktestEngine, MatcherConfig
from app.backtest.frozen_panel import FrozenPanelArtifactStore
from app.shadow.distillation import ShadowRuleValidator
from app.shadow.schemas import validate_assumption_pair

_FEATURES = ("close_return_5d", "volume_ratio_20d", "intraday_range")
_REQUIRED_DAILY_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume")
_ADJUSTMENT_POLICY = "governed_adjusted_daily"
_MAX_GOVERNED_ROWS = 20_000
_MAX_EVIDENCE_TRADES = 10_000


class ShadowProductionError(RuntimeError):
    """A production Shadow collaborator is absent or crossed its bounded contract."""


def assert_shadow_runtime_ready(governed_repository: object | None) -> None:
    """Fail module-locally unless the existing governed daily repository is usable."""
    if governed_repository is None:
        raise ShadowProductionError("governed Shadow repository is unavailable")
    for method_name in ("get_daily", "latest_daily_date"):
        if not callable(getattr(governed_repository, method_name, None)):
            raise ShadowProductionError("governed Shadow repository contract is incomplete")
    try:
        latest = governed_repository.latest_daily_date()
    except Exception as error:
        raise ShadowProductionError("governed Shadow repository readiness failed") from error
    if not isinstance(latest, date):
        raise ShadowProductionError("governed Shadow daily input is unavailable")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    ).encode("utf-8")


class _GovernedShadowPanels:
    """Derive the fixed Shadow feature allowlist from the existing governed K-line lake."""

    def __init__(self, *, shadow_repository: object, governed_repository: object) -> None:
        self._shadow_repository = shadow_repository
        self._governed_repository = governed_repository

    def evidence_context(
        self, evidence_set: Mapping[str, object]
    ) -> tuple[str, str, str, frozenset[date]]:
        evidence_id = evidence_set.get("id")
        fingerprint = evidence_set.get("fingerprint")
        if (
            not isinstance(evidence_id, str)
            or not evidence_id
            or not isinstance(fingerprint, str)
            or len(fingerprint) != 64
        ):
            raise ShadowProductionError("Shadow evidence attribution is invalid")
        resolver = getattr(self._shadow_repository, "resolve_evidence_trades", None)
        if not callable(resolver):
            raise ShadowProductionError("Shadow evidence resolver is unavailable")
        trades = resolver(evidence_set_id=evidence_id)
        if not isinstance(trades, list) or not trades or len(trades) > _MAX_EVIDENCE_TRADES:
            raise ShadowProductionError("Shadow evidence trades are unavailable or unbounded")

        symbols: set[str] = set()
        entry_dates: set[date] = set()
        for trade in trades:
            if not isinstance(trade, Mapping):
                raise ShadowProductionError("Shadow evidence trade is invalid")
            symbol = trade.get("symbol")
            executed_at = trade.get("executed_at")
            side = trade.get("side")
            if not isinstance(symbol, str) or not symbol or not isinstance(executed_at, str):
                raise ShadowProductionError("Shadow evidence trade attribution is invalid")
            try:
                executed_date = datetime.fromisoformat(executed_at).date()
            except ValueError as error:
                raise ShadowProductionError("Shadow evidence trade time is invalid") from error
            symbols.add(symbol)
            if side == "buy":
                entry_dates.add(executed_date)
        if len(symbols) != 1 or not entry_dates:
            raise ShadowProductionError(
                "bounded Shadow distillation requires one attributable instrument with entries"
            )
        return evidence_id, fingerprint, next(iter(symbols)), frozenset(entry_dates)

    def feature_panel(
        self,
        *,
        symbol: str,
        entry_dates: frozenset[date],
        start: date,
        end: date,
    ) -> pl.DataFrame:
        if start > end or (end - start).days > 800:
            raise ShadowProductionError("Shadow governed window is invalid or unbounded")
        loader = getattr(self._governed_repository, "get_daily", None)
        if not callable(loader):
            raise ShadowProductionError("governed Shadow daily loader is unavailable")
        try:
            daily = loader(symbol, start - timedelta(days=60), end)
        except Exception as error:
            raise ShadowProductionError("governed Shadow daily input could not be loaded") from error
        if not isinstance(daily, pl.DataFrame) or daily.is_empty():
            raise ShadowProductionError("governed Shadow daily input is empty")
        missing = set(_REQUIRED_DAILY_COLUMNS) - set(daily.columns)
        if missing:
            raise ShadowProductionError("governed Shadow daily input schema is incomplete")
        if daily.height > _MAX_GOVERNED_ROWS:
            raise ShadowProductionError("governed Shadow daily input exceeds the bounded row limit")

        panel = (
            daily.select(_REQUIRED_DAILY_COLUMNS)
            .with_columns(
                pl.col("symbol").cast(pl.String),
                pl.col("date").cast(pl.Date),
                *[pl.col(name).cast(pl.Float64) for name in ("open", "high", "low", "close", "volume")],
            )
            .sort(["symbol", "date"])
            .unique(subset=["symbol", "date"], keep="none")
            .with_columns(
                (pl.col("close") / pl.col("close").shift(5).over("symbol") - 1.0).alias(
                    "close_return_5d"
                ),
                (
                    pl.col("volume")
                    / pl.col("volume").shift(1).rolling_mean(window_size=20).over("symbol")
                ).alias("volume_ratio_20d"),
                ((pl.col("high") - pl.col("low")) / pl.col("close")).alias(
                    "intraday_range"
                ),
            )
            .filter((pl.col("date") >= start) & (pl.col("date") <= end))
            .drop_nulls(_FEATURES)
            .filter(pl.all_horizontal(pl.col(name).is_finite() for name in _FEATURES))
        )
        if panel.is_empty():
            raise ShadowProductionError("governed Shadow feature window is empty")
        labels = pl.DataFrame(
            {
                "symbol": [symbol] * len(entry_dates),
                "date": list(entry_dates),
                "actual_trade": [True] * len(entry_dates),
            },
            schema={"symbol": pl.String, "date": pl.Date, "actual_trade": pl.Boolean},
        )
        return (
            panel.join(labels, on=["symbol", "date"], how="left")
            .with_columns(pl.col("actual_trade").fill_null(False))
            .sort(["symbol", "date"])
        )


class ProductionShadowFeatureSource:
    """Supply transient explainable-training rows from frozen local evidence and K-lines."""

    def __init__(self, *, shadow_repository: object, governed_repository: object) -> None:
        self._panels = _GovernedShadowPanels(
            shadow_repository=shadow_repository,
            governed_repository=governed_repository,
        )

    def load(
        self,
        *,
        evidence_set: dict[str, object],
        feature_names: tuple[str, ...],
    ) -> list[dict[str, object]]:
        if not feature_names or any(name not in _FEATURES for name in feature_names):
            raise ShadowProductionError("Shadow feature selection is invalid")
        _evidence_id, _fingerprint, symbol, entry_dates = self._panels.evidence_context(
            evidence_set
        )
        panel = self._panels.feature_panel(
            symbol=symbol,
            entry_dates=entry_dates,
            start=min(entry_dates) - timedelta(days=180),
            end=max(entry_dates) + timedelta(days=180),
        )
        return [
            {
                "date": row["date"].isoformat(),
                "actual_trade": bool(row["actual_trade"]),
                **{name: float(row[name]) for name in feature_names},
            }
            for row in panel.select(["date", "actual_trade", *feature_names]).iter_rows(
                named=True
            )
        ]


class ProductionShadowFeatureFreezer:
    """Freeze each chronological split with the existing immutable panel store."""

    def __init__(
        self,
        *,
        shadow_repository: object,
        governed_repository: object,
        artifact_store: FrozenPanelArtifactStore,
    ) -> None:
        self._panels = _GovernedShadowPanels(
            shadow_repository=shadow_repository,
            governed_repository=governed_repository,
        )
        self._artifact_store = artifact_store

    def freeze(
        self,
        *,
        evidence_set: Mapping[str, object],
        split_kind: str,
        window: Mapping[str, str],
        adjustment_policy: str,
    ) -> dict[str, object]:
        if split_kind not in {"in_sample", "out_of_sample"}:
            raise ShadowProductionError("Shadow split identity is invalid")
        if adjustment_policy != _ADJUSTMENT_POLICY:
            raise ShadowProductionError("Shadow adjustment policy is unsupported")
        try:
            start = date.fromisoformat(str(window["start"]))
            end = date.fromisoformat(str(window["end"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ShadowProductionError("Shadow split window is invalid") from error
        evidence_id, fingerprint, symbol, entry_dates = self._panels.evidence_context(
            evidence_set
        )
        panel = self._panels.feature_panel(
            symbol=symbol,
            entry_dates=entry_dates,
            start=start,
            end=end,
        )
        scope = {
            "evidence_set_id": evidence_id,
            "evidence_set_fingerprint": fingerprint,
            "symbol": symbol,
            "split_kind": split_kind,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "adjustment_policy": adjustment_policy,
        }
        reference = self._artifact_store.create(scope=scope, panel=panel)
        artifact_id = reference["artifact_id"]
        panel_path = self._artifact_store.root / artifact_id / "panel.parquet"
        descriptor: dict[str, object] = {
            "artifact_id": artifact_id,
            "content_type": "application/x-parquet",
            "byte_size": panel_path.stat().st_size,
            "checksum_sha256": reference["panel_checksum"],
            "schema_version": reference["schema_version"],
            "scope_sha256": reference["scope_checksum"],
            "created_at": datetime.now(UTC).isoformat(),
            "reference": reference,
            "scope": scope,
        }
        governed_fingerprint = sha256(
            _canonical_bytes(
                {
                    "scope": scope,
                    "panel_checksum": reference["panel_checksum"],
                    "metadata_checksum": reference["metadata_checksum"],
                }
            )
        ).hexdigest()
        return {
            "artifact": descriptor,
            "governed_fingerprint": governed_fingerprint,
            "window": scope["window"],
            "split_kind": split_kind,
        }


class ProductionShadowEvaluationRunner:
    """Replay canonical rules and delegate bounded trade simulation to BacktestEngine."""

    def __init__(self, *, governed_repository: object, artifact_store: FrozenPanelArtifactStore) -> None:
        self._engine = BacktestEngine(governed_repository)  # type: ignore[arg-type]
        self._artifact_store = artifact_store
        self._validator = ShadowRuleValidator()

    def run(
        self,
        *,
        candidate: Mapping[str, object],
        frozen_input: Mapping[str, object],
        cost_policy: Mapping[str, float],
    ) -> dict[str, object]:
        artifact = frozen_input.get("artifact")
        if not isinstance(artifact, Mapping):
            raise ShadowProductionError("Shadow frozen artifact is invalid")
        reference = artifact.get("reference")
        scope = artifact.get("scope")
        if not isinstance(reference, Mapping) or not isinstance(scope, Mapping):
            raise ShadowProductionError("Shadow frozen artifact authority is incomplete")
        panel = self._artifact_store.load(reference=reference, expected_scope=scope)
        if panel.is_empty() or panel.height > _MAX_GOVERNED_ROWS:
            raise ShadowProductionError("Shadow frozen panel is empty or unbounded")

        assumptions = validate_assumption_pair(
            exit_assumptions=candidate.get("exit_assumptions"),
            holding_assumptions=candidate.get("holding_assumptions"),
        )
        if (
            assumptions.exit.get("kind") != "fixed_holding_days"
            or assumptions.holding.get("price_adjustment")
            != "unadjusted_execution_vs_forward_adjusted_research"
        ):
            raise ShadowProductionError("Shadow candidate assumptions are unsupported")
        rules = candidate.get("rules")
        rows = panel.select([*(_FEATURES), "actual_trade"]).to_dicts()
        predictions = self._validator.replay(rules, rows)
        actual = [bool(row["actual_trade"]) for row in rows]
        predicted = sum(predictions)
        positives = sum(actual)
        true_positives = sum(
            expected and observed
            for expected, observed in zip(predictions, actual, strict=True)
        )

        commission_bps = float(cost_policy["commission_bps"])
        slippage_bps = float(cost_policy["slippage_bps"])
        stamp_duty_bps = float(cost_policy["stamp_duty_bps"])
        result = self._engine.simulate(
            panel,
            entries=pl.Series("shadow_entry", predictions, dtype=pl.Boolean),
            exits=None,
            config=MatcherConfig(
                matching="close_t",
                commission_pct=commission_bps / 10_000.0,
                stamp_tax_pct=stamp_duty_bps / 10_000.0,
                slippage_bps=slippage_bps,
                max_hold_days=int(assumptions.exit["days"]),
                max_positions=1,
                position_sizing="equal",
            ),
        )
        candidate_trades = len(result.trades)
        realized_costs = candidate_trades * (
            2 * commission_bps + 2 * slippage_bps + stamp_duty_bps
        ) / 10_000.0
        metrics = {
            "precision": true_positives / predicted if predicted else 0.0,
            "recall": true_positives / positives if positives else 0.0,
            "coverage": predicted / len(rows),
            "candidate_trades": candidate_trades,
            "total_return": float(result.stats.get("total_return", 0.0)),
            "max_drawdown": float(result.stats.get("max_drawdown", 0.0)),
            "costs": realized_costs,
            "actual_trade_consistency": true_positives / positives if positives else 0.0,
        }
        return {"status": "passed", "metrics": metrics}
