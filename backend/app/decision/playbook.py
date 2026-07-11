"""Pure deterministic baseline calculations over governed historical inputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from app.tickflow.repository import KlineRepository


_Q4 = Decimal("0.0001")
_DEFAULT_ACCOUNT_VALUE = Decimal("100000")
_REQUIRED_CONFIG_KEYS = frozenset({"entry_band", "stop_k", "tp_ratios", "per_trade_risk_pct", "rr_threshold"})


@dataclass(frozen=True)
class DecisionBaseline:
    """Immutable deterministic playbook result and its governed provenance."""

    symbol: str
    entry_low: Decimal
    entry_high: Decimal
    stop: Decimal
    target1: Decimal
    target2: Decimal
    position_pct: Decimal
    action: str
    score: Decimal
    risk_reward: Decimal
    reason_snapshot: dict[str, str]
    data_as_of: date
    engine_config_version: str

    def to_snapshot(self) -> dict[str, Any]:
        """Return the immutable decision facts, excluding run-level provenance."""
        return {
            "symbol": self.symbol,
            "entry_low": self.entry_low,
            "entry_high": self.entry_high,
            "stop": self.stop,
            "target1": self.target1,
            "target2": self.target2,
            "position_pct": self.position_pct,
            "action": self.action,
            "score": self.score,
            "risk_reward": self.risk_reward,
            "reason_snapshot": dict(self.reason_snapshot),
        }


class DecisionPlaybookService:
    """Build deterministic baselines without HTTP, SQLite, or provider dependencies."""

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal:
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError(f"{field} must be numeric") from error
        if not decimal.is_finite():
            raise ValueError(f"{field} must be finite")
        return decimal

    @classmethod
    def _config_decimal(cls, config: Mapping[str, Any], field: str) -> Decimal:
        if field not in config:
            raise ValueError(f"configuration requires {field}")
        return cls._decimal(config[field], field)

    @classmethod
    def _config_pair(cls, config: Mapping[str, Any], field: str) -> tuple[Decimal, Decimal]:
        values = config.get(field)
        if not isinstance(values, (list, tuple)) or len(values) != 2:
            raise ValueError(f"configuration {field} must contain two values")
        return cls._decimal(values[0], f"{field}[0]"), cls._decimal(values[1], f"{field}[1]")

    @staticmethod
    def _validate_symbol(symbol: Any) -> str:
        if not isinstance(symbol, str) or not (symbol := symbol.strip().upper()):
            raise ValueError("symbol is required")
        return symbol

    @classmethod
    def _atr(cls, bars: list[Mapping[str, Any]]) -> Decimal:
        if len(bars) < 2:
            raise ValueError("governed history requires at least two bars")
        ranges: list[Decimal] = []
        previous_close: Decimal | None = None
        for bar in bars:
            high = cls._decimal(bar.get("high"), "bar high")
            low = cls._decimal(bar.get("low"), "bar low")
            close = cls._decimal(bar.get("close"), "bar close")
            if low > high:
                raise ValueError("bar low must not exceed high")
            components = [high - low]
            if previous_close is not None:
                components.extend([abs(high - previous_close), abs(low - previous_close)])
            ranges.append(max(components))
            previous_close = close
        return (sum(ranges, Decimal()) / Decimal(len(ranges))).quantize(_Q4)

    @classmethod
    def build_baseline(
        cls,
        *,
        snapshot: Mapping[str, Any],
        data_as_of: date,
        engine_config_version: str,
    ) -> DecisionBaseline:
        """Calculate a reproducible plan from an already-governed historical snapshot."""
        if not isinstance(data_as_of, date):
            raise ValueError("data_as_of must be a date")
        if not isinstance(engine_config_version, str) or not (engine_config_version := engine_config_version.strip()):
            raise ValueError("engine_config_version is required")
        if not isinstance(snapshot, Mapping):
            raise ValueError("snapshot is required")

        symbol = cls._validate_symbol(snapshot.get("symbol"))
        bars = snapshot.get("bars")
        if not isinstance(bars, list) or not bars:
            raise ValueError("governed history requires bars")
        normalized_bars = [bar for bar in bars if isinstance(bar, Mapping)]
        if len(normalized_bars) != len(bars):
            raise ValueError("bars must be records")
        latest_close = cls._decimal(normalized_bars[-1].get("close"), "bar close")
        atr = cls._atr(normalized_bars)

        config = snapshot.get("config")
        if not isinstance(config, Mapping) or not _REQUIRED_CONFIG_KEYS.issubset(config):
            raise ValueError("configuration is incomplete")
        entry_high_pct, entry_low_pct = cls._config_pair(config, "entry_band")
        tp1_ratio, tp2_ratio = cls._config_pair(config, "tp_ratios")
        stop_k = cls._config_decimal(config, "stop_k")
        risk_pct = cls._config_decimal(config, "per_trade_risk_pct")
        rr_threshold = cls._config_decimal(config, "rr_threshold")
        if not (Decimal() <= entry_high_pct <= entry_low_pct < Decimal(1)):
            raise ValueError("configuration entry_band is invalid")
        if stop_k <= 0 or risk_pct < 0 or tp1_ratio <= 0 or tp2_ratio <= 0 or rr_threshold < 0:
            raise ValueError("configuration values are invalid")

        factors = snapshot.get("factors") or {}
        if not isinstance(factors, Mapping):
            raise ValueError("factors must be a record")
        ma5 = cls._decimal(factors.get("ma5", latest_close), "ma5")
        ma10 = cls._decimal(factors.get("ma10", latest_close), "ma10")
        ma20 = cls._decimal(factors.get("ma20", latest_close), "ma20")
        score = cls._decimal(snapshot.get("score", 0), "score")
        position_cap = cls._decimal(snapshot.get("position_cap", 0), "position_cap")
        if not Decimal() <= position_cap <= Decimal(1):
            raise ValueError("position_cap must be between zero and one")

        entry_low = (latest_close * (Decimal(1) - entry_low_pct)).quantize(_Q4)
        entry_high = (latest_close * (Decimal(1) + entry_high_pct)).quantize(_Q4)
        atr_stop = (entry_low - stop_k * atr).quantize(_Q4)
        structure_stop = ma20.quantize(_Q4)
        stop = max(atr_stop, structure_stop).quantize(_Q4)
        risk_per_share = (entry_low - stop).quantize(_Q4)
        if risk_per_share <= 0:
            risk_per_share = (entry_low * Decimal("0.01")).quantize(_Q4)
            stop = (entry_low - risk_per_share).quantize(_Q4)

        target1 = (entry_high + tp1_ratio * risk_per_share).quantize(_Q4)
        target2 = (entry_high + tp2_ratio * risk_per_share).quantize(_Q4)
        entry_mid = ((entry_low + entry_high) / Decimal(2)).quantize(_Q4)
        weighted_target = ((target1 + target2) / Decimal(2)).quantize(_Q4)
        risk_reward = ((weighted_target - entry_mid) / risk_per_share).quantize(_Q4)

        # The governed market-state cap is the deterministic allocation envelope.
        # Risk-per-share still constrains stop construction and provenance, while the
        # executable percentage is expressed as whole shares within that envelope.
        if position_cap == 0:
            position_pct = Decimal("0.0000")
        else:
            shares = max(1, int((_DEFAULT_ACCOUNT_VALUE * position_cap / entry_low).to_integral_value(rounding=ROUND_DOWN)))
            position_pct = (Decimal(shares) * entry_low / _DEFAULT_ACCOUNT_VALUE).quantize(_Q4)

        market_state = snapshot.get("market_state")
        if score < Decimal("5") or market_state == "分歧":
            action = "放弃"
        elif market_state in {"冰点", "退潮"}:
            action = "风险剔除"
        elif risk_reward < rr_threshold:
            action = "只观察"
        elif latest_close > ma20 and market_state in {"主升", "震荡", "修复"}:
            action = "突破确认"
        elif abs(latest_close - ma10) / ma10 <= Decimal("0.02") if ma10 else False:
            action = "回踩观察"
        else:
            action = "只观察"

        return DecisionBaseline(
            symbol=symbol,
            entry_low=entry_low,
            entry_high=entry_high,
            stop=stop,
            target1=target1,
            target2=target2,
            position_pct=position_pct,
            action=action,
            score=score,
            risk_reward=risk_reward,
            reason_snapshot={
                "atr": f"{atr:.4f}",
                "risk_per_share": f"{risk_per_share:.4f}",
                "source": "governed_history",
            },
            data_as_of=data_as_of,
            engine_config_version=engine_config_version,
        )

    def snapshot_from_governed_history(
        self,
        *,
        repository: KlineRepository,
        symbol: str,
        data_as_of: date,
        configuration: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Read only Tickflow-governed bars and derive the baseline input snapshot."""
        if not isinstance(data_as_of, date):
            raise ValueError("data_as_of must be a date")
        symbol = self._validate_symbol(symbol)
        frame = repository.get_daily(
            symbol,
            data_as_of - timedelta(days=120),
            data_as_of,
            columns=["date", "open", "high", "low", "close", "ma5", "ma10", "ma20"],
        )
        if frame is None or frame.is_empty():
            raise ValueError("no governed historical data exists for symbol and as_of")
        rows = frame.sort("date").to_dicts()
        latest = rows[-1]
        return {
            "symbol": symbol,
            "bars": [
                {
                    "trade_date": str(row["date"]),
                    "open": str(row["open"]),
                    "high": str(row["high"]),
                    "low": str(row["low"]),
                    "close": str(row["close"]),
                }
                for row in rows
                if all(row.get(field) is not None for field in ("open", "high", "low", "close"))
            ],
            "factors": {
                key: str(latest[key])
                for key in ("ma5", "ma10", "ma20")
                if latest.get(key) is not None
            },
            "score": str(configuration.get("score", "0")),
            "market_state": configuration.get("market_state", "震荡"),
            "position_cap": str(configuration.get("position_cap", "0.50")),
            "config": dict(configuration),
        }
