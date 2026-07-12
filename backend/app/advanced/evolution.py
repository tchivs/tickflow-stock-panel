"""Constrained strategy evolution and registered-research-only promotion."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
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
