"""Bounded application of reviewed decision-plan adjustments."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


ALLOWED_ADJUSTMENT_FIELDS = frozenset(
    {"entry_low", "entry_high", "stop", "target1", "target2", "position_pct"}
)


class DecisionAdjustmentService:
    """Apply only bounded numeric changes while retaining immutable baseline facts."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError("adjustment value must be numeric") from error
        if not result.is_finite():
            raise ValueError("adjustment value must be finite")
        return result

    @staticmethod
    def _serialize(value: Decimal) -> str:
        return format(value, "f")

    @staticmethod
    def _rationale(value: Any) -> str:
        return value if isinstance(value, str) else ""

    @classmethod
    def _bounds(cls, field: str, final: Mapping[str, Any], baseline: Mapping[str, Any]) -> tuple[Decimal, Decimal]:
        entry_low = cls._decimal(final["entry_low"])
        entry_high = cls._decimal(final["entry_high"])
        target1 = cls._decimal(final["target1"])
        target2 = cls._decimal(final["target2"])
        baseline_stop = cls._decimal(baseline["stop"])
        baseline_position = cls._decimal(baseline["position_pct"])
        if field == "entry_low":
            return baseline_stop, entry_high
        if field == "entry_high":
            return entry_low, target1
        if field == "stop":
            return baseline_stop, entry_low
        if field == "target1":
            return entry_high, target2
        if field == "target2":
            return target1, target2
        if field == "position_pct":
            return Decimal(), baseline_position
        raise ValueError("adjustment field is not allowed")

    def apply(self, *, run_id: str, proposal: Mapping[str, Any]) -> dict[str, Any]:
        """Persist a disposition for every supplied field and update only final plan fields."""
        run = self._repository.get_decision_run(run_id)
        if run is None:
            raise ValueError("decision run not found")
        if not isinstance(proposal, Mapping):
            raise ValueError("proposal must be a record")

        baseline = run["baseline"]
        final = dict(run["final"])
        audit: list[dict[str, Any]] = []
        for field, payload in proposal.items():
            value = payload.get("value") if isinstance(payload, Mapping) else None
            rationale = self._rationale(payload.get("rationale") if isinstance(payload, Mapping) else None)
            proposed_value = None if value is None else str(value)
            final_value: str | None = None
            disposition = "rejected"
            if field in ALLOWED_ADJUSTMENT_FIELDS:
                try:
                    proposed = self._decimal(value)
                    lower, upper = self._bounds(field, final, baseline)
                    bounded = min(max(proposed, lower), upper)
                    final[field] = bounded
                    final_value = self._serialize(bounded)
                    disposition = "applied" if bounded == proposed else "clamped"
                except (KeyError, ValueError):
                    pass
            audit.append(
                self._repository.record_adjustment_audit(
                    run_id=run_id,
                    field=str(field),
                    proposed_value=proposed_value,
                    final_value=final_value,
                    disposition=disposition,
                    rationale=rationale,
                )
            )

        persisted = self._repository.replace_decision_final(run_id, final)
        return {"final": persisted["final"], "audit": audit}
