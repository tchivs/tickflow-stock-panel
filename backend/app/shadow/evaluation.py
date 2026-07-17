"""Chronological, evidence-bound Shadow candidate evaluation.

The browser never supplies governed fingerprints or eligibility verdicts.  This module
loads the immutable candidate and evidence facts, freezes each declared chronological
window independently, and gives a bounded collaborator only canonical rule data plus
the frozen input descriptor.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
from threading import Lock
from typing import Protocol

_REQUIRED_METRICS = (
    "precision",
    "recall",
    "coverage",
    "candidate_trades",
    "total_return",
    "max_drawdown",
    "costs",
    "actual_trade_consistency",
)
_TERMINAL_STATUSES = frozenset(
    {"passed", "failed", "failed_gate", "timeout", "resource_exhausted", "interrupted"}
)
_RETRYABLE_STATUSES = frozenset(
    {"failed", "failed_gate", "timeout", "resource_exhausted", "interrupted"}
)
_COST_FIELDS = frozenset({"commission_bps", "slippage_bps", "stamp_duty_bps"})
_PAIR_EXECUTION_LOCK = Lock()


class ShadowEvaluationError(ValueError):
    """An evaluation request or collaborator result violated the governed contract."""


class EvaluationRepository(Protocol):
    def get_candidate(self, candidate_id: str) -> dict[str, object] | None: ...

    def get_evidence_set(self, evidence_set_id: str) -> dict[str, object] | None: ...

    def get_evaluation_pair(self, payload: Mapping[str, object]) -> dict[str, object] | None: ...

    def reserve_evaluation_pair(self, payload: Mapping[str, object]) -> dict[str, object]: ...

    def reserve_evaluation_retry(
        self, *, pair_id: str, evaluation_id: str
    ) -> dict[str, object]: ...

    def complete_evaluation(
        self, evaluation_id: str, terminal: dict[str, object]
    ) -> dict[str, object]: ...

    def get_evaluation(self, evaluation_id: str) -> dict[str, object] | None: ...


class FeatureFreezer(Protocol):
    def freeze(
        self,
        *,
        evidence_set: Mapping[str, object],
        split_kind: str,
        window: Mapping[str, str],
        adjustment_policy: str,
    ) -> dict[str, object]: ...


class BoundedEvaluationRunner(Protocol):
    def run(
        self,
        *,
        candidate: Mapping[str, object],
        frozen_input: Mapping[str, object],
        cost_policy: Mapping[str, float],
    ) -> dict[str, object]: ...


class ShadowEvaluationService:
    """Append immutable terminal evidence for independent IS and OOS executions."""

    def __init__(
        self,
        *,
        repository: EvaluationRepository,
        feature_freezer: FeatureFreezer,
        runner: BoundedEvaluationRunner,
    ) -> None:
        self.repository = repository
        self.feature_freezer = feature_freezer
        self.runner = runner
        self._pair_lock = _PAIR_EXECUTION_LOCK

    def evaluate_candidate(
        self,
        *,
        candidate_id: str,
        evidence_set_id: str,
        in_sample_window: Mapping[str, object],
        out_of_sample_window: Mapping[str, object],
        split_policy: str,
        adjustment_policy: str,
        cost_policy: Mapping[str, object],
    ) -> dict[str, dict[str, object]]:
        candidate, evidence = self._canonical_subjects(
            candidate_id=candidate_id, evidence_set_id=evidence_set_id
        )
        in_sample = self._window(in_sample_window, "in-sample")
        out_of_sample = self._window(out_of_sample_window, "out-of-sample")
        if split_policy != "chronological":
            raise ShadowEvaluationError("Shadow evaluation requires a chronological split")
        if in_sample["end"] >= out_of_sample["start"]:
            raise ShadowEvaluationError("in-sample and out-of-sample windows must not overlap")
        adjustment = self._bounded_text(adjustment_policy, "adjustment policy", 256)
        costs = self._cost_policy(cost_policy)
        pair_request: dict[str, object] = {
            "candidate_id": str(candidate["id"]),
            "evidence_set_id": str(evidence["id"]),
            "evidence_set_fingerprint": str(evidence["fingerprint"]),
            "in_sample_window": in_sample,
            "out_of_sample_window": out_of_sample,
            "adjustment_policy": adjustment,
            "cost_policy": costs,
        }

        with self._pair_lock:
            pair = self.repository.get_evaluation_pair(pair_request)
            if pair is None:
                splits: dict[str, dict[str, object]] = {}
                for split_kind, window in (
                    ("in_sample", in_sample),
                    ("out_of_sample", out_of_sample),
                ):
                    frozen = self._frozen_input(
                        evidence=evidence,
                        split_kind=split_kind,
                        window=window,
                        adjustment_policy=adjustment,
                    )
                    splits[split_kind] = {
                        "window": frozen["window"],
                        "governed_fingerprint": frozen["governed_fingerprint"],
                        "artifact": frozen["artifact"],
                    }
                pair = self.repository.reserve_evaluation_pair({**pair_request, "splits": splits})
            pair_id = pair.get("id")
            if not isinstance(pair_id, str) or not pair_id:
                raise ShadowEvaluationError("evaluation repository returned an invalid pair")
            fresh = pair.get("created") is True
            results: dict[str, dict[str, object]] = {}
            for split_kind in ("in_sample", "out_of_sample"):
                current = pair.get(split_kind)
                if not isinstance(current, Mapping):
                    raise ShadowEvaluationError("evaluation repository returned an incomplete pair")
                status = current.get("status")
                if status == "passed":
                    results[split_kind] = dict(current)
                    continue
                if status not in _RETRYABLE_STATUSES:
                    raise ShadowEvaluationError("evaluation pair contains a non-retryable split")
                attempt = (
                    dict(current)
                    if fresh
                    else self.repository.reserve_evaluation_retry(
                        pair_id=pair_id, evaluation_id=str(current["id"])
                    )
                )
                if attempt.get("status") == "passed":
                    results[split_kind] = dict(attempt)
                    continue
                results[split_kind] = self._run_reserved_attempt(
                    candidate=candidate,
                    attempt=attempt,
                    cost_policy=costs,
                )
            return results

    def retry_evaluation(self, *, evaluation_id: str) -> dict[str, object]:
        evaluation_key = self._bounded_text(evaluation_id, "evaluation identifier", 128)
        with self._pair_lock:
            previous = self.repository.get_evaluation(evaluation_key)
            if previous is None or previous.get("status") not in _RETRYABLE_STATUSES:
                raise ShadowEvaluationError("only a failed terminal evaluation can be retried")
            candidate_id = previous.get("candidate_id")
            evidence_set_id = previous.get("evidence_set_id")
            pair_id = previous.get("pair_id")
            if (
                not isinstance(candidate_id, str)
                or not isinstance(evidence_set_id, str)
                or not isinstance(pair_id, str)
            ):
                raise ShadowEvaluationError("persisted evaluation attribution is invalid")
            candidate, evidence = self._canonical_subjects(
                candidate_id=candidate_id, evidence_set_id=evidence_set_id
            )
            if previous.get("evidence_set_fingerprint") != evidence.get("fingerprint"):
                raise ShadowEvaluationError("persisted evaluation evidence has changed")
            costs = self._cost_policy(previous.get("cost_policy"))
            attempt = self.repository.reserve_evaluation_retry(
                pair_id=pair_id, evaluation_id=evaluation_key
            )
            if attempt.get("status") == "passed":
                return dict(attempt)
            return self._run_reserved_attempt(
                candidate=candidate,
                attempt=attempt,
                cost_policy=costs,
            )

    def _run_reserved_attempt(
        self,
        *,
        candidate: Mapping[str, object],
        attempt: Mapping[str, object],
        cost_policy: dict[str, float],
    ) -> dict[str, object]:
        evaluation_id = attempt.get("id")
        split_kind = attempt.get("split_kind")
        if not isinstance(evaluation_id, str) or not evaluation_id:
            raise ShadowEvaluationError("evaluation repository returned an invalid attempt")
        if split_kind not in {"in_sample", "out_of_sample"}:
            raise ShadowEvaluationError("persisted evaluation split is invalid")
        window = self._window(attempt.get("window"), "persisted")
        fingerprint = self._sha256(attempt.get("governed_fingerprint"), "governed fingerprint")
        artifact = self._artifact(attempt.get("artifact"))
        if self._cost_policy(attempt.get("cost_policy")) != cost_policy:
            raise ShadowEvaluationError("persisted evaluation cost policy diverged")
        frozen_input = {
            "artifact": artifact,
            "governed_fingerprint": fingerprint,
            "window": window,
            "split_kind": split_kind,
        }
        try:
            outcome = self.runner.run(
                candidate=self._runner_candidate(candidate),
                frozen_input=frozen_input,
                cost_policy=dict(cost_policy),
            )
            terminal = self._terminal(outcome)
        except Exception:
            terminal = {
                "status": "failed",
                "reason": "bounded evaluation collaborator failed",
            }
        return self.repository.complete_evaluation(evaluation_id, terminal)

    def _canonical_subjects(
        self, *, candidate_id: str, evidence_set_id: str
    ) -> tuple[dict[str, object], dict[str, object]]:
        candidate_key = self._bounded_text(candidate_id, "candidate identifier", 128)
        evidence_key = self._bounded_text(evidence_set_id, "evidence identifier", 128)
        candidate = self.repository.get_candidate(candidate_key)
        evidence = self.repository.get_evidence_set(evidence_key)
        if candidate is None or evidence is None:
            raise ShadowEvaluationError("candidate or evidence is unavailable")
        if candidate.get("evidence_set_id") != evidence_key or candidate.get(
            "evidence_set_fingerprint"
        ) != evidence.get("fingerprint"):
            raise ShadowEvaluationError("candidate and frozen evidence do not match")
        self._sha256(evidence.get("fingerprint"), "evidence fingerprint")
        rules = candidate.get("rules")
        if not isinstance(rules, list) or not rules:
            raise ShadowEvaluationError("candidate rules are unavailable")
        return dict(candidate), dict(evidence)

    def _frozen_input(
        self,
        *,
        evidence: Mapping[str, object],
        split_kind: str,
        window: dict[str, str],
        adjustment_policy: str,
    ) -> dict[str, object]:
        try:
            frozen = self.feature_freezer.freeze(
                evidence_set=evidence,
                split_kind=split_kind,
                window=window,
                adjustment_policy=adjustment_policy,
            )
        except Exception as error:
            raise ShadowEvaluationError("governed feature input could not be frozen") from error
        if not isinstance(frozen, Mapping):
            raise ShadowEvaluationError("governed feature freezer returned an invalid result")
        if frozen.get("split_kind") != split_kind:
            raise ShadowEvaluationError("frozen split identity diverged")
        frozen_window = self._window(frozen.get("window"), "frozen")
        if frozen_window != window:
            raise ShadowEvaluationError("frozen window identity diverged")
        return {
            "artifact": self._artifact(frozen.get("artifact")),
            "governed_fingerprint": self._sha256(
                frozen.get("governed_fingerprint"), "governed fingerprint"
            ),
            "window": frozen_window,
            "split_kind": split_kind,
        }

    @staticmethod
    def _runner_candidate(candidate: Mapping[str, object]) -> dict[str, object]:
        """Pass only replayable rule data, never estimator or repository internals."""
        limitations = candidate.get("limitations")
        return {
            "id": str(candidate["id"]),
            "rules": candidate["rules"],
            "exit_assumptions": candidate.get("exit_assumptions"),
            "holding_assumptions": candidate.get("holding_assumptions"),
            "limitations": list(limitations) if isinstance(limitations, list) else [],
        }

    @classmethod
    def _terminal(cls, outcome: object) -> dict[str, object]:
        if not isinstance(outcome, Mapping):
            raise ShadowEvaluationError("bounded runner returned an invalid terminal result")
        status = outcome.get("status")
        if status not in _TERMINAL_STATUSES:
            raise ShadowEvaluationError("bounded runner returned an invalid terminal status")
        if status == "passed":
            return {"status": status, "metrics": cls._metrics(outcome.get("metrics"))}
        return {
            "status": status,
            "reason": cls._safe_reason(outcome.get("reason")),
        }

    @staticmethod
    def _metrics(value: object) -> dict[str, float | int]:
        if not isinstance(value, Mapping) or any(key not in value for key in _REQUIRED_METRICS):
            raise ShadowEvaluationError("passing evaluation lacks complete metrics")
        metrics: dict[str, float | int] = {}
        for key in _REQUIRED_METRICS:
            item = value[key]
            if (
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(float(item))
            ):
                raise ShadowEvaluationError("evaluation metrics must be finite numbers")
            metrics[key] = item
        for key in ("precision", "recall", "coverage", "actual_trade_consistency"):
            if not 0 <= float(metrics[key]) <= 1:
                raise ShadowEvaluationError(f"{key} must be between zero and one")
        if (
            int(metrics["candidate_trades"]) != metrics["candidate_trades"]
            or metrics["candidate_trades"] < 0
        ):
            raise ShadowEvaluationError("candidate trades must be a non-negative integer")
        if metrics["costs"] < 0 or metrics["max_drawdown"] > 0:
            raise ShadowEvaluationError("evaluation cost or drawdown metric is invalid")
        return metrics

    @staticmethod
    def _window(value: object, label: str) -> dict[str, str]:
        if not isinstance(value, Mapping) or set(value) != {"start", "end"}:
            raise ShadowEvaluationError(f"{label} window is invalid")
        start, end = value.get("start"), value.get("end")
        if not isinstance(start, str) or not isinstance(end, str):
            raise ShadowEvaluationError(f"{label} window is invalid")
        try:
            start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError as error:
            raise ShadowEvaluationError(f"{label} window is invalid") from error
        if start_date > end_date:
            raise ShadowEvaluationError(f"{label} window end precedes start")
        return {"start": start_date.isoformat(), "end": end_date.isoformat()}

    @staticmethod
    def _cost_policy(value: object) -> dict[str, float]:
        if not isinstance(value, Mapping) or set(value) != _COST_FIELDS:
            raise ShadowEvaluationError("cost policy is invalid")
        result: dict[str, float] = {}
        for key in sorted(_COST_FIELDS):
            item = value[key]
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ShadowEvaluationError("cost policy values must be numeric")
            number = float(item)
            if not math.isfinite(number) or number < 0 or number > 10_000:
                raise ShadowEvaluationError("cost policy values are out of bounds")
            result[key] = number
        return result

    @staticmethod
    def _artifact(value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise ShadowEvaluationError("frozen artifact descriptor is invalid")
        checksum = value.get("checksum_sha256")
        if not isinstance(checksum, str) or len(checksum) != 64:
            raise ShadowEvaluationError("frozen artifact checksum is invalid")
        relative_path = value.get("relative_path")
        if relative_path is not None and (
            not isinstance(relative_path, str)
            or not relative_path
            or relative_path.startswith(("/", "\\"))
            or ".." in relative_path.replace("\\", "/").split("/")
        ):
            raise ShadowEvaluationError("frozen artifact path is not contained")
        return dict(value)

    @staticmethod
    def _sha256(value: object, field: str) -> str:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ShadowEvaluationError(f"{field} is invalid")
        return value

    @staticmethod
    def _bounded_text(value: object, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ShadowEvaluationError(f"{field} is invalid")
        return value.strip()

    @staticmethod
    def _safe_reason(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            return "bounded evaluation did not pass"
        normalized = " ".join(value.strip().split())
        return normalized[:256]
