"""Restart-safe append-only Forecast maturity and calibration scanner."""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import math
from typing import Any


_HORIZONS = (5, 20, 60)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _pinball(actual: float, predicted: float, quantile: float) -> float:
    error = actual - predicted
    return max(quantile * error, (quantile - 1.0) * error)


class ForecastMaturityScanner:
    """Resolve frozen future sessions and append one canonical terminal fact."""

    def __init__(
        self,
        *,
        repository: Any,
        actuals: Any,
        max_items_per_scan: int = 32,
        metric_schema: str = "forecast-close-calibration-v1",
        action_collaborators: Mapping[str, object] | None = None,
    ) -> None:
        if (
            isinstance(max_items_per_scan, bool)
            or not isinstance(max_items_per_scan, int)
            or not 1 <= max_items_per_scan <= 256
        ):
            raise ValueError("Forecast maturity batch size must be between 1 and 256")
        if not isinstance(metric_schema, str) or not metric_schema.strip() or len(metric_schema) > 128:
            raise ValueError("Forecast calibration metric schema is invalid")
        self.repository = repository
        self.actuals = actuals
        self.max_items_per_scan = max_items_per_scan
        self.metric_schema = metric_schema.strip()
        # Explicit negative-authority seam: calibration never calls these collaborators.
        self.action_collaborators = dict(action_collaborators or {})
        self.interrupt_at: str | None = None

    def evaluate(
        self, *, forecast_id: str, horizon: int, as_of_session_id: str
    ) -> dict[str, Any]:
        if horizon not in _HORIZONS:
            raise ValueError("Forecast maturity horizon is invalid")
        canonical = self.repository.outcome_for_horizon(forecast_id, horizon)
        if canonical is not None:
            return canonical
        record = self.repository.get_forecast(forecast_id)
        if record is None:
            raise ValueError("Forecast record does not exist")
        if horizon > int(record["horizon"]):
            raise ValueError("Forecast maturity horizon exceeds the immutable record")
        future_sessions = record.get("future_session_ids")
        if not isinstance(future_sessions, list) or len(future_sessions) < horizon:
            raise ValueError("Forecast future-session identity is incomplete")
        target_session = future_sessions[horizon - 1]
        if not isinstance(target_session, str) or not target_session:
            raise ValueError("Forecast target session identity is invalid")
        if not self._has_matured(
            future_sessions=future_sessions,
            target_session=target_session,
            as_of_session_id=as_of_session_id,
        ):
            return {"status": "not_mature", "forecast_id": forecast_id, "horizon": horizon}

        actual = self.actuals.load_actual(
            instrument_id=str(record["instrument_id"]),
            session_id=target_session,
            calendar_revision=str(record["calendar_revision"]),
        )
        close = self._finite_close(actual)
        quantiles = self._quantiles(record, horizon)
        if close is None:
            status = "unevaluable"
            reason = "missing_actual"
            actual_fingerprint = None
            close_mae = None
            covered = None
            losses = (None, None, None)
        elif quantiles is None:
            status = "unevaluable"
            reason = "missing_quantiles"
            actual_fingerprint = self._actual_fingerprint(record, target_session, close)
            close_mae = None
            covered = None
            losses = (None, None, None)
        else:
            p10, p50, p90 = quantiles
            status = "evaluated"
            reason = None
            actual_fingerprint = self._actual_fingerprint(record, target_session, close)
            close_mae = abs(close - p50)
            covered = p10 <= close <= p90
            losses = (
                _pinball(close, p10, 0.1),
                _pinball(close, p50, 0.5),
                _pinball(close, p90, 0.9),
            )
        if self.interrupt_at == "before_append":
            raise RuntimeError("Forecast maturity scan interrupted before append")
        return self.repository.append_maturity_fact(
            forecast_id=forecast_id,
            horizon=horizon,
            status=status,
            actual_session_id=target_session,
            actual_close=close,
            actual_fingerprint=actual_fingerprint,
            reason=reason,
            observed_at=self.repository.now(),
            metric_schema=self.metric_schema,
            close_mae=close_mae,
            interval_covered=covered,
            pinball_p10=losses[0],
            pinball_p50=losses[1],
            pinball_p90=losses[2],
        )

    def scan(self, *, as_of_session_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for record in self.repository.list_forecasts():
            for horizon in _HORIZONS:
                if horizon > int(record["horizon"]):
                    continue
                if len(results) >= self.max_items_per_scan:
                    return results
                results.append(
                    self.evaluate(
                        forecast_id=str(record["id"]),
                        horizon=horizon,
                        as_of_session_id=as_of_session_id,
                    )
                )
        return results

    def restart_scan(self, *, as_of_session_id: str) -> list[dict[str, Any]]:
        self.repository.expire_maturity_leases(now=self.repository.now())
        return self.scan(as_of_session_id=as_of_session_id)

    @staticmethod
    def _has_matured(
        *, future_sessions: list[object], target_session: str, as_of_session_id: str
    ) -> bool:
        if not isinstance(as_of_session_id, str) or not as_of_session_id:
            raise ValueError("Forecast maturity as-of session is invalid")
        try:
            target_index = future_sessions.index(target_session)
            as_of_index = future_sessions.index(as_of_session_id)
        except ValueError:
            return False
        return as_of_index >= target_index

    @staticmethod
    def _finite_close(actual: object) -> float | None:
        if not isinstance(actual, Mapping):
            return None
        value = actual.get("close")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        close = float(value)
        return close if math.isfinite(close) else None

    @staticmethod
    def _quantiles(record: Mapping[str, object], horizon: int) -> tuple[float, float, float] | None:
        all_quantiles = record.get("quantiles")
        if not isinstance(all_quantiles, Mapping):
            return None
        values = all_quantiles.get(str(horizon))
        if not isinstance(values, Mapping):
            return None
        raw = (values.get("p10"), values.get("p50"), values.get("p90"))
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in raw):
            return None
        quantiles = tuple(float(value) for value in raw)
        if not all(math.isfinite(value) for value in quantiles):
            return None
        return quantiles  # type: ignore[return-value]

    @staticmethod
    def _actual_fingerprint(
        record: Mapping[str, object], session_id: str, close: float
    ) -> str:
        return sha256(
            _canonical_json(
                {
                    "instrument_id": record["instrument_id"],
                    "session_id": session_id,
                    "calendar_revision": record["calendar_revision"],
                    "close": close,
                }
            )
        ).hexdigest()
