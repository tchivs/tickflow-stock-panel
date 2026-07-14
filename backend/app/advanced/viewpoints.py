"""Immutable attributed viewpoint lineage and frozen outcome calculations."""
from __future__ import annotations

import json
from datetime import date
from hashlib import sha256
from typing import Any, Protocol
from uuid import uuid4

from app.advanced.policy import AdvancedPolicy
from app.advanced.repository import AdvancedRepository
from app.advanced.schemas import ViewpointRequest, ViewpointRevisionRequest


class GovernedMarketSnapshot(Protocol):
    """Narrow governed-data boundary; implementations must not use current quotes."""

    def price_at_window(self, instrument: str, trading_days: int) -> float | None: ...

    def benchmark_at_window(self, benchmark: str, trading_days: int) -> float | None: ...


class GovernedViewpointEvaluation(Protocol):
    """Production collaborator returns only frozen, governed evaluation inputs."""

    def evaluate_viewpoint(self, version: dict[str, Any]) -> dict[str, Any]: ...


class ViewpointService:
    def __init__(self, *, repository: AdvancedRepository, policy: AdvancedPolicy) -> None:
        self.repository = repository
        self.policy = policy

    def create_viewpoint(self, **payload: Any) -> dict[str, Any]:
        request = ViewpointRequest.model_validate(payload)
        benchmark = self.policy.resolve_benchmark(
            source_profile=request.source_profile,
            market_scope=request.market_scope,
            asset_type=request.asset_type,
            requested=request.benchmark,
        )
        row = self.repository.append_viewpoint_version(
            viewpoint_id=str(uuid4()), source_profile=request.source_profile, market_scope=request.market_scope,
            instrument=request.instrument, policy_revision=self.policy.version, policy_fingerprint=self.policy.fingerprint,
            policy_snapshot=self.policy.snapshot(), asset_type=request.asset_type, published_at=request.published_at.isoformat(),
            direction=request.direction, rating=request.rating, conclusion=request.conclusion, target_range=request.target_range,
            horizon_days=request.horizon_days, confidence=request.confidence, revision_kind="initial", correction_reason=None,
            evaluation_window_days=request.evaluation_window_days, benchmark=benchmark,
            evidence=self._evidence(request.evidence),
        )
        persisted = self.repository.viewpoint_version(row["id"])
        assert persisted is not None
        return self._projection(persisted, evidence=self._evidence(request.evidence))

    def revise_viewpoint(self, *, viewpoint_id: str, **changes: Any) -> dict[str, Any]:
        previous = self._latest(viewpoint_id)
        request = ViewpointRevisionRequest.model_validate(changes)
        return self._append_revision(previous, request, revision_kind=None, correction_reason=None)

    def correct_viewpoint(self, *, viewpoint_id: str, correction_reason: str, **changes: Any) -> dict[str, Any]:
        if not correction_reason.strip():
            raise ValueError("correction reason is required")
        previous = self._latest(viewpoint_id)
        request = ViewpointRevisionRequest.model_validate(changes)
        return self._append_revision(previous, request, revision_kind="correction", correction_reason=correction_reason)

    def list_versions(self, viewpoint_id: str) -> list[dict[str, Any]]:
        return [self._projection(row, evidence=row.pop("evidence")) for row in self.repository.viewpoint_versions(viewpoint_id)]

    def list_for_instrument(self, instrument: str) -> list[dict[str, Any]]:
        return [self._projection(row, evidence=row.pop("evidence")) for row in self.repository.viewpoint_versions_for_instrument(instrument)]

    def get_viewpoint_version(self, viewpoint_version_id: str) -> dict[str, Any] | None:
        return self.repository.viewpoint_version(viewpoint_version_id)

    def evaluate_viewpoint(self, *, viewpoint_version_id: str, market_snapshot: GovernedMarketSnapshot) -> dict[str, Any]:
        version = self.repository.viewpoint_version(viewpoint_version_id)
        if version is None:
            raise ValueError("viewpoint version not found")
        terminal = self.repository.canonical_terminal_viewpoint_evaluation(viewpoint_version_id)
        if terminal is not None:
            return self._terminal_outcome(version, terminal)
        governed_evaluator = getattr(market_snapshot, "evaluate_viewpoint", None)
        if callable(governed_evaluator):
            return self._record_governed_evaluation(version, governed_evaluator(version))
        window = version["evaluation_window_days"]
        price = market_snapshot.price_at_window(version["instrument"], window)
        benchmark_price = market_snapshot.benchmark_at_window(version["benchmark"], window)
        if price is None or benchmark_price is None:
            reason = "missing_price" if price is None else "missing_benchmark"
            self.record_evaluation(
                viewpoint_version_id=viewpoint_version_id, status="unevaluable", reason=reason,
                governed_input_fingerprint=self._input_fingerprint(version, price, benchmark_price),
            )
            return {"status": "unevaluable", "reason": reason, "relative_return": None}
        instrument_return = round(price / 100.0 - 1.0, 10)
        benchmark_return = round(benchmark_price / 100.0 - 1.0, 10)
        relative_return = round(instrument_return - benchmark_return, 10)
        as_of = date.fromisoformat(version["published_at"][:10])
        self.record_evaluation(
            viewpoint_version_id=viewpoint_version_id, status="evaluated", relative_return=relative_return,
            coverage_start=as_of, coverage_end=as_of,
            governed_input_fingerprint=self._input_fingerprint(version, price, benchmark_price),
        )
        return {"status": "evaluated", "window_days": window, "benchmark": version["benchmark"],
                "instrument_return": instrument_return, "benchmark_return": benchmark_return,
                "relative_return": relative_return, "as_of": as_of}

    def _record_governed_evaluation(self, version: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        status = result.get("status")
        if status == "unevaluable":
            reason = result.get("reason")
            if reason not in {"missing_price", "missing_benchmark", "unsupported_scope"}:
                raise ValueError("governed evaluator returned an invalid outcome")
            self.record_evaluation(
                viewpoint_version_id=version["id"], status="unevaluable", reason=reason,
                governed_input_fingerprint=self._input_fingerprint(version, result.get("instrument_end"), result.get("benchmark_end")),
            )
            return {"status": "unevaluable", "reason": reason, "relative_return": None}
        if status != "evaluated":
            raise ValueError("governed evaluator returned an invalid outcome")
        instrument_start = result.get("instrument_start")
        instrument_end = result.get("instrument_end")
        benchmark_start = result.get("benchmark_start")
        benchmark_end = result.get("benchmark_end")
        coverage_start = result.get("coverage_start")
        coverage_end = result.get("coverage_end")
        if not all(isinstance(value, (int, float)) and value > 0 for value in (
            instrument_start, instrument_end, benchmark_start, benchmark_end,
        )) or not isinstance(coverage_start, date) or not isinstance(coverage_end, date):
            raise ValueError("governed evaluator returned incomplete inputs")
        instrument_return = round(instrument_end / instrument_start - 1.0, 10)
        benchmark_return = round(benchmark_end / benchmark_start - 1.0, 10)
        relative_return = round(instrument_return - benchmark_return, 10)
        self.record_evaluation(
            viewpoint_version_id=version["id"], status="evaluated", relative_return=relative_return,
            coverage_start=coverage_start, coverage_end=coverage_end,
            governed_input_fingerprint=self._input_fingerprint(version, instrument_end, benchmark_end),
        )
        return {
            "status": "evaluated", "window_days": version["evaluation_window_days"], "benchmark": version["benchmark"],
            "instrument_return": instrument_return, "benchmark_return": benchmark_return,
            "relative_return": relative_return, "as_of": coverage_end,
        }

    def record_evaluation(self, *, viewpoint_version_id: str, status: str, relative_return: float | None = None,
                          coverage_start: date | None = None, coverage_end: date | None = None, reason: str | None = None,
                          governed_input_fingerprint: str | None = None) -> dict[str, Any]:
        if status == "evaluated" and relative_return is None:
            raise ValueError("evaluated outcome requires relative return")
        if status == "unevaluable" and not reason:
            raise ValueError("unevaluable outcome requires a reason")
        return self.repository.append_viewpoint_evaluation(
            viewpoint_version_id=viewpoint_version_id, status=status, reason=reason, relative_return=relative_return,
            coverage_start=coverage_start.isoformat() if coverage_start else None,
            coverage_end=coverage_end.isoformat() if coverage_end else None,
            governed_input_fingerprint=governed_input_fingerprint,
        )

    def calibration(self, *, source_profile: str, minimum_sample_count: int = 2) -> dict[str, Any]:
        if source_profile not in self.policy.source_profiles:
            raise ValueError("source profile is not permitted")
        grouped: dict[str, list[dict[str, Any]]] = {"low": [], "medium": [], "high": []}
        excluded_unevaluable = 0
        for item in self.repository.calibration_viewpoint_evaluations(source_profile):
            if item["status"] == "evaluated":
                grouped[item["confidence"]].append(item)
            else:
                excluded_unevaluable += 1
        result: dict[str, Any] = {}
        for confidence, items in grouped.items():
            returns = [item["relative_return"] for item in items]
            count = len(items)
            result[confidence] = {
                "status": "calibrated" if count >= minimum_sample_count else "insufficient_sample",
                "sample_count": count,
                "hit_rate": sum(value > 0 for value in returns) / count if count else None,
                "mean_relative_return": sum(returns) / count if count else None,
                "coverage_start": min((item["coverage_start"] for item in items if item["coverage_start"]), default=None),
                "coverage_end": max((item["coverage_end"] for item in items if item["coverage_end"]), default=None),
            }
        result["excluded_unevaluable"] = excluded_unevaluable
        return result

    @staticmethod
    def _terminal_outcome(version: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
        """Project a persisted terminal fact without revisiting governed market inputs."""
        if evaluation["status"] == "unevaluable":
            return {"status": "unevaluable", "reason": evaluation["reason"], "relative_return": None}
        coverage_end = evaluation["coverage_end"]
        return {
            "status": "evaluated",
            "window_days": version["evaluation_window_days"],
            "benchmark": version["benchmark"],
            "relative_return": evaluation["relative_return"],
            "as_of": date.fromisoformat(coverage_end) if coverage_end else None,
        }

    def _append_revision(self, previous: dict[str, Any], request: ViewpointRevisionRequest, *, revision_kind: str | None,
                         correction_reason: str | None) -> dict[str, Any]:
        values = {field: getattr(request, field) if getattr(request, field) is not None else previous[field]
                  for field in ("conclusion", "direction", "rating", "target_range", "horizon_days", "confidence")}
        evidence = self._evidence(request.evidence) if request.evidence is not None else previous["evidence"]
        changed_fields = [field for field, value in values.items() if value != previous[field]]
        if evidence != previous["evidence"]:
            changed_fields.append("evidence")
        material_fields = {"direction", "rating", "target_range", "horizon_days", "confidence"}
        actual_kind = revision_kind or ("material_stance_change" if material_fields.intersection(changed_fields) else "non_material_revision")
        historical_policy = self.repository.policy_revision_for_viewpoint_version(previous["id"])
        if historical_policy is None:
            raise ValueError("viewpoint policy revision not found")
        row = self.repository.append_viewpoint_version(
            viewpoint_id=previous["viewpoint_id"], source_profile=previous["source_profile"], market_scope=previous["market_scope"],
            instrument=previous["instrument"], policy_revision=historical_policy["revision"],
            policy_fingerprint=previous["policy_fingerprint"], policy_snapshot=historical_policy["snapshot"],
            asset_type=previous["asset_type"], published_at=previous["published_at"],
            direction=values["direction"], rating=values["rating"], conclusion=values["conclusion"], target_range=values["target_range"],
            horizon_days=values["horizon_days"], confidence=values["confidence"], revision_kind=actual_kind,
            correction_reason=correction_reason, evaluation_window_days=previous["evaluation_plan"]["window_days"],
            benchmark=previous["evaluation_plan"]["benchmark"], evidence=evidence,
        )
        persisted = self.repository.viewpoint_version(row["id"])
        assert persisted is not None
        projection = self._projection(persisted, evidence=evidence)
        projection["changed_fields"] = changed_fields
        projection["material_change"] = actual_kind == "material_stance_change"
        return projection

    def _latest(self, viewpoint_id: str) -> dict[str, Any]:
        versions = self.list_versions(viewpoint_id)
        if not versions:
            raise ValueError("viewpoint not found")
        return versions[0]

    def _projection(self, row: dict[str, Any], *, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": row["id"], "viewpoint_id": row["viewpoint_id"], "version": row["version"],
            "source_profile": row["source_profile"], "market_scope": row["market_scope"], "instrument": row["instrument"],
            "policy_version": row["policy_version"], "policy_fingerprint": row["policy_fingerprint"], "asset_type": row["asset_type"],
            "published_at": row["published_at"], "direction": row["direction"], "rating": row["rating"], "conclusion": row["conclusion"],
            "target_range": [row["target_low"], row["target_high"]], "horizon_days": row["horizon_days"], "confidence": row["confidence"],
            "revision_kind": row["revision_kind"], "correction_reason": row["correction_reason"], "evidence": evidence,
            "evaluation_plan": {"window_days": row["evaluation_window_days"], "benchmark": row["benchmark"], "metric": row["metric"]},
            "evaluation": row.get("evaluation"),
        }


    @staticmethod
    def _evidence(items: Any) -> list[dict[str, Any]]:
        return [
            {"id": item.id, **({"published_at": item.published_at.isoformat()} if item.published_at else {})}
            for item in items
        ]

    @staticmethod
    def _input_fingerprint(version: dict[str, Any], price: float | None, benchmark_price: float | None) -> str:
        payload = {"instrument": version["instrument"], "benchmark": version["benchmark"], "window_days": version["evaluation_window_days"], "price": price, "benchmark_price": benchmark_price}
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
