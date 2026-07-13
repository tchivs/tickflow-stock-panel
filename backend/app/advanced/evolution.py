"""Constrained strategy evolution and registered-research-only promotion."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any
from uuid import uuid4

from app.advanced.repository import AdvancedRepository

_ALLOWED_MUTATIONS = {
    "adjust_signal_threshold",
    "parameter_adjustment",
    "feature_subset",
    "signal_threshold",
    "portfolio_constraint",
}
_REQUIRED_GATES = {
    "contract_sandbox_safety",
    "provenance",
    "in_sample_out_of_sample_evidence",
    "robustness",
    "cost_feasibility",
}


class EvolutionService:
    """Persists constrained candidates and requires all gates before registration."""

    def __init__(
        self,
        *,
        repository: AdvancedRepository,
        reviewer_resolver: Callable[[str | None], str | None],
        monitoring_activator: Callable[..., object] | None = None,
        decision_plan_service: Callable[..., object] | None = None,
        broker_adapter: Callable[..., object] | None = None,
        execution_adapter: Callable[..., object] | None = None,
    ) -> None:
        self.repository = repository
        self.reviewer_resolver = reviewer_resolver
        # These compatibility arguments are deliberately never invoked. Promotion is registration only.
        self._excluded_dependencies = (monitoring_activator, decision_plan_service, broker_adapter, execution_adapter)

    def create_candidate(
        self,
        *,
        parent_research_asset: Mapping[str, object],
        mutation_operation: str,
        seed: int | None,
        resolved_configuration: Mapping[str, object],
    ) -> dict[str, Any]:
        parent_id = parent_research_asset.get("id")
        parent_version = parent_research_asset.get("version")
        if not parent_research_asset.get("validated") or not parent_id or not parent_version:
            raise ValueError("candidate requires a validated parent research asset")
        if mutation_operation not in _ALLOWED_MUTATIONS:
            raise ValueError("mutation operation is not allowlisted")
        if isinstance(seed, bool) or not isinstance(seed, int) or not resolved_configuration:
            raise ValueError("candidate requires a seed and resolved configuration")
        identifier = str(uuid4())
        with self.repository._connection() as connection, connection:
            connection.execute(
                """INSERT INTO advanced_strategy_candidates
                    (id, parent_research_asset_id, parent_version, mutation_operation, seed, resolved_configuration_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (identifier, str(parent_id), str(parent_version), mutation_operation, seed, self._json(resolved_configuration), self.repository.now()),
            )
            row = connection.execute("SELECT * FROM advanced_strategy_candidates WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return self._candidate_row(row)

    def create_candidate_from_completed_run(
        self,
        *,
        completed_run: Mapping[str, object],
        mutation_operation: str,
        seed: int | None,
        resolved_configuration: Mapping[str, object],
    ) -> dict[str, Any]:
        """Freeze only complete, server-produced experiment evidence into a candidate."""
        run = completed_run.get("run")
        specification = completed_run.get("specification")
        if not isinstance(run, Mapping) or not isinstance(specification, Mapping) or run.get("status") != "completed":
            raise ValueError("candidate requires a completed governed experiment run")
        parent_id = specification.get("research_asset_id")
        parent_version = run.get("asset_version")
        if not isinstance(parent_id, str) or not parent_id or parent_version != parent_id:
            raise ValueError("completed run provenance does not match its research asset")
        if not self._evidence_matrix_is_complete(run=run, specification=specification):
            raise ValueError("completed run lacks required immutable evolution evidence")
        candidate = self.create_candidate(
            parent_research_asset={"id": parent_id, "version": str(parent_version), "validated": True},
            mutation_operation=mutation_operation,
            seed=seed,
            resolved_configuration={
                **dict(resolved_configuration),
                "source_run": {
                    "id": str(run["id"]),
                    "governed_fingerprint": str(run["governed_fingerprint"]),
                    "asset_version": str(run["asset_version"]),
                    "resolved_parameters": dict(run.get("resolved_parameters", {})),
                    "metrics": dict(run.get("metrics", {})),
                    "artifacts": list(run.get("artifacts", [])),
                    "evolution_evidence": dict(run["evolution_evidence"]),
                    "sandbox_validation": dict(run["sandbox_validation"]),
                    "sandbox_run": dict(run["sandbox_run"]),
                },
                "source_specification": {
                    "id": str(specification["id"]),
                    "version": int(specification["version"]),
                    "research_asset_id": parent_id,
                    "data_scope": dict(specification["data_scope"]),
                },
            },
        )
        return candidate

    def evaluate_gate(self, *, candidate_id: str, gate: str) -> dict[str, Any]:
        """Record exactly one deterministic verdict derived from immutable candidate evidence."""
        if gate not in _REQUIRED_GATES:
            raise ValueError("promotion gate is invalid")
        candidate = self.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError("strategy candidate does not exist")
        status = "passed" if self._gate_passes(candidate=candidate, gate=gate) else "failed"
        return self.record_gate(
            candidate_id=candidate_id,
            gate=gate,
            status=status,
            evidence={"summary": f"server-derived {gate} evidence {status}"},
        )

    def record_gate(self, *, candidate_id: str, gate: str, status: str, evidence: Mapping[str, object]) -> dict[str, Any]:
        if gate not in _REQUIRED_GATES or status not in {"passed", "failed"} or not evidence:
            raise ValueError("promotion gate is invalid")
        identifier = str(uuid4())
        with self.repository._connection() as connection, connection:
            if connection.execute("SELECT 1 FROM advanced_strategy_candidates WHERE id = ?", (candidate_id,)).fetchone() is None:
                raise ValueError("strategy candidate does not exist")
            try:
                connection.execute(
                    "INSERT INTO advanced_promotion_gates (id, candidate_id, gate, status, evidence_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (identifier, candidate_id, gate, status, self._json(evidence), self.repository.now()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("promotion gate already recorded") from error
            row = connection.execute("SELECT * FROM advanced_promotion_gates WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return self._gate_row(row)

    def approve(
        self,
        *,
        candidate_id: str,
        session_token: str | None = None,
        rationale: str,
        aggregate_score: float | None = None,
        principal: str | None = None,
    ) -> dict[str, Any]:
        del aggregate_score  # Ranking can be displayed but never decides promotion eligibility.
        researcher_principal = principal or self.reviewer_resolver(session_token)
        if not researcher_principal:
            raise ValueError("server-resolved researcher principal is required")
        if len(rationale.strip()) < 10:
            raise ValueError("promotion rationale is required")
        promotion_id = str(uuid4())
        registered_strategy_id = str(uuid4())
        with self.repository._connection() as connection, connection:
            candidate = connection.execute("SELECT * FROM advanced_strategy_candidates WHERE id = ?", (candidate_id,)).fetchone()
            if candidate is None:
                raise ValueError("strategy candidate does not exist")
            gates = connection.execute(
                "SELECT gate, status FROM advanced_promotion_gates WHERE candidate_id = ?", (candidate_id,)
            ).fetchall()
            passed = {row["gate"] for row in gates if row["status"] == "passed"}
            if passed != _REQUIRED_GATES or len(gates) != len(_REQUIRED_GATES):
                raise ValueError("promotion gates are incomplete or failed")
            try:
                connection.execute(
                    """INSERT INTO advanced_promotions
                        (id, job_id, candidate_id, reviewer_principal, rationale, registered_strategy_id, created_at)
                        VALUES (?, NULL, ?, ?, ?, ?, ?)""",
                    (promotion_id, candidate_id, researcher_principal, rationale.strip(), registered_strategy_id, self.repository.now()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("promotion already recorded or state changed; refresh and retry") from error
            promotion = connection.execute("SELECT * FROM advanced_promotions WHERE id = ?", (promotion_id,)).fetchone()
        assert promotion is not None
        return {
            "approval": self._promotion_row(promotion),
            "registered_strategy": {
                "id": registered_strategy_id,
                "candidate_id": candidate_id,
                "status": "registered_research_only",
            },
        }

    def list_registered_strategies(self) -> list[dict[str, Any]]:
        with self.repository._connection() as connection:
            rows = connection.execute(
                "SELECT registered_strategy_id, candidate_id FROM advanced_promotions ORDER BY created_at, id"
            ).fetchall()
        return [
            {"id": row["registered_strategy_id"], "candidate_id": row["candidate_id"], "status": "registered_research_only"}
            for row in rows
        ]

    def list_candidates(self) -> list[dict[str, Any]]:
        with self.repository._connection() as connection:
            rows = connection.execute("SELECT * FROM advanced_strategy_candidates ORDER BY created_at DESC, id DESC").fetchall()
        return [self._candidate_row(row) for row in rows]

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self.repository._connection() as connection:
            row = connection.execute("SELECT * FROM advanced_strategy_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return None if row is None else self._candidate_row(row)

    def list_gates(self, *, candidate_id: str) -> list[dict[str, Any]]:
        with self.repository._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM advanced_promotion_gates WHERE candidate_id = ? ORDER BY created_at, id", (candidate_id,)
            ).fetchall()
        return [self._gate_row(row) for row in rows]

    @staticmethod
    def _json(value: Mapping[str, object]) -> str:
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _evidence_matrix_is_complete(*, run: Mapping[str, object], specification: Mapping[str, object]) -> bool:
        evidence = run.get("evolution_evidence")
        validation = run.get("sandbox_validation")
        sandbox_run = run.get("sandbox_run")
        return (
            all(isinstance(run.get(key), str) and run.get(key) for key in ("id", "governed_fingerprint", "asset_version"))
            and isinstance(run.get("resolved_parameters"), Mapping)
            and isinstance(run.get("metrics"), Mapping)
            and isinstance(run.get("artifacts"), list)
            and isinstance(evidence, Mapping)
            and all(key in evidence for key in ("split", "robustness_trials", "cost_feasibility"))
            and EvolutionService._valid_split(split=evidence.get("split"), scope=specification.get("data_scope"))
            and isinstance(validation, Mapping)
            and validation.get("status") == "validated"
            and isinstance(sandbox_run, Mapping)
            and sandbox_run.get("status") in {"completed", "failed"}
            and sandbox_run.get("validation_id") == validation.get("id")
            and isinstance(specification.get("id"), str)
            and isinstance(specification.get("version"), int)
            and isinstance(specification.get("data_scope"), Mapping)
        )

    def _gate_passes(self, *, candidate: Mapping[str, object], gate: str) -> bool:
        configuration = candidate.get("resolved_configuration")
        if not isinstance(configuration, Mapping):
            return False
        run = configuration.get("source_run")
        specification = configuration.get("source_specification")
        if not isinstance(run, Mapping) or not isinstance(specification, Mapping):
            return False
        if not self._evidence_matrix_is_complete(run=run, specification=specification):
            return False
        evidence = run["evolution_evidence"]
        assert isinstance(evidence, Mapping)
        if gate == "contract_sandbox_safety":
            validation = run["sandbox_validation"]
            sandbox_run = run["sandbox_run"]
            return (
                isinstance(validation, Mapping)
                and validation.get("parent_asset_id") == candidate.get("parent_research_asset_id")
                and validation.get("status") == "validated"
                and isinstance(sandbox_run, Mapping)
                and sandbox_run.get("validation_id") == validation.get("id")
                and sandbox_run.get("status") in {"completed", "failed"}
            )
        if gate == "provenance":
            return (
                specification.get("research_asset_id") == candidate.get("parent_research_asset_id")
                and run.get("asset_version") == candidate.get("parent_version")
                and bool(run.get("governed_fingerprint"))
                and bool(run.get("resolved_parameters"))
                and bool(run.get("artifacts"))
            )
        if gate == "in_sample_out_of_sample_evidence":
            split = evidence.get("split")
            scope = specification.get("data_scope")
            return self._valid_split(split=split, scope=scope)
        if gate == "robustness":
            trials = evidence.get("robustness_trials")
            return isinstance(trials, list) and bool(trials) and all(
                isinstance(trial, Mapping)
                and trial.get("status") == "completed"
                and isinstance(trial.get("metrics"), Mapping)
                and trial.get("threshold_met") is True
                for trial in trials
            )
        if gate == "cost_feasibility":
            cost = evidence.get("cost_feasibility")
            return (
                isinstance(cost, Mapping)
                and isinstance(cost.get("fee_model"), str)
                and isinstance(cost.get("commission"), (int, float))
                and isinstance(cost.get("slippage"), (int, float))
                and isinstance(cost.get("capacity_assumptions"), Mapping)
                and isinstance(cost.get("net_metrics"), Mapping)
                and cost.get("capacity_result") == "feasible"
                and cost.get("threshold_met") is True
            )
        return False

    @staticmethod
    def _valid_split(*, split: object, scope: object) -> bool:
        if not isinstance(split, Mapping) or not isinstance(scope, Mapping):
            return False
        in_sample = split.get("in_sample")
        out_sample = split.get("out_of_sample")
        if not isinstance(in_sample, Mapping) or not isinstance(out_sample, Mapping):
            return False
        try:
            scope_start = date.fromisoformat(str(scope["start"]))
            scope_end = date.fromisoformat(str(scope["end"]))
            in_start, in_end = date.fromisoformat(str(in_sample["start"])), date.fromisoformat(str(in_sample["end"]))
            out_start, out_end = date.fromisoformat(str(out_sample["start"])), date.fromisoformat(str(out_sample["end"]))
        except (KeyError, TypeError, ValueError):
            return False

        def independent_evaluation(sample: Mapping[str, object]) -> Mapping[str, object] | None:
            evaluation = sample.get("evaluation")
            if not isinstance(evaluation, Mapping):
                return None
            window = evaluation.get("window")
            artifact = evaluation.get("artifact")
            if (
                not isinstance(window, Mapping)
                or window.get("start") != sample.get("start")
                or window.get("end") != sample.get("end")
                or not isinstance(artifact, Mapping)
                or not all(isinstance(evaluation.get(key), str) and evaluation[key] for key in ("run_id", "governed_input_fingerprint"))
                or not all(isinstance(artifact.get(key), str) and artifact[key] for key in ("reference", "checksum"))
            ):
                return None
            return evaluation

        in_evaluation = independent_evaluation(in_sample)
        out_evaluation = independent_evaluation(out_sample)
        return (
            scope_start <= in_start <= in_end < out_start <= out_end <= scope_end
            and isinstance(in_sample.get("metrics"), Mapping)
            and bool(in_sample["metrics"])
            and isinstance(out_sample.get("metrics"), Mapping)
            and bool(out_sample["metrics"])
            and in_evaluation is not None
            and out_evaluation is not None
            and in_evaluation["run_id"] != out_evaluation["run_id"]
            and in_evaluation["governed_input_fingerprint"] != out_evaluation["governed_input_fingerprint"]
        )

    @staticmethod
    def _candidate_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["resolved_configuration"] = json.loads(value.pop("resolved_configuration_json"))
        return value

    @staticmethod
    def _gate_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["evidence"] = json.loads(value.pop("evidence_json"))
        return value

    @staticmethod
    def _promotion_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["researcher_principal"] = value.pop("reviewer_principal")
        return value
