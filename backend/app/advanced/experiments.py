"""Immutable experiment specification, run, and feedback workflow."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from hashlib import sha256
from typing import Any, Protocol
from uuid import uuid4

from app.advanced.repository import AdvancedRepository
from app.advanced.schemas import FrozenStrategyScope


class GovernedBacktestRunner(Protocol):
    """Narrow boundary that returns governed metadata, never raw market data."""

    def run(self, *, specification: dict[str, object]) -> dict[str, object]: ...


_TERMINAL_STATUSES = {"completed", "validation_failed", "timed_out", "resource_limited"}
_FEEDBACK_CONCLUSIONS = {"supported", "refuted", "inconclusive", "needs_replication"}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ExperimentService:
    """Append-only research records backed by governed execution evidence."""

    def __init__(self, *, repository: AdvancedRepository, backtest_runner: GovernedBacktestRunner) -> None:
        self.repository = repository
        self.backtest_runner = backtest_runner

    def create_specification(
        self,
        *,
        research_asset_id: str,
        hypothesis: str,
        data_scope: Mapping[str, Any],
        method: str,
        metrics: list[str],
        success_criteria: Mapping[str, Any],
        failure_criteria: Mapping[str, Any],
        supersedes_specification_id: str | None = None,
        owner_principal: str = "system",
    ) -> dict[str, Any]:
        if not all((research_asset_id, hypothesis, method, owner_principal)) or not data_scope or not metrics:
            raise ValueError("experiment specification requires frozen research inputs")
        try:
            frozen_scope = FrozenStrategyScope.model_validate(data_scope).model_dump(mode="json")
        except ValueError as error:
            raise ValueError("experiment specification has an invalid frozen strategy scope") from error
        identifier = str(uuid4())
        with self.repository._connection() as connection, connection:
            if supersedes_specification_id is None:
                version = 1
            else:
                parent = connection.execute(
                    "SELECT research_asset_id, version FROM advanced_experiment_specs WHERE id = ?",
                    (supersedes_specification_id,),
                ).fetchone()
                if parent is None or parent["research_asset_id"] != research_asset_id:
                    raise ValueError("superseded specification must belong to the same research asset")
                version = int(parent["version"]) + 1
            connection.execute(
                """INSERT INTO advanced_experiment_specs (
                    id, research_asset_id, version, supersedes_specification_id, hypothesis,
                    data_scope_json, method, metrics_json, success_criteria_json,
                    failure_criteria_json, created_at, owner_principal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    identifier, research_asset_id, version, supersedes_specification_id, hypothesis,
                    _json(frozen_scope), method, _json(metrics), _json(dict(success_criteria)),
                    _json(dict(failure_criteria)), self.repository.now(), owner_principal,
                ),
            )
            row = connection.execute("SELECT * FROM advanced_experiment_specs WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return self._specification_row(row)

    def get_specification(self, specification_id: str) -> dict[str, Any] | None:
        with self.repository._connection() as connection:
            row = connection.execute("SELECT * FROM advanced_experiment_specs WHERE id = ?", (specification_id,)).fetchone()
        return None if row is None else self._specification_row(row)

    def list_specifications(self) -> list[dict[str, Any]]:
        with self.repository._connection() as connection:
            rows = connection.execute("SELECT * FROM advanced_experiment_specs ORDER BY created_at DESC, id DESC").fetchall()
        return [self._specification_row(row) for row in rows]

    def run_specification(self, *, specification_id: str) -> dict[str, Any]:
        specification = self.get_specification(specification_id)
        if specification is None:
            raise ValueError("experiment specification does not exist")
        result = self.backtest_runner.run(specification=specification)
        status = result.get("status")
        if status not in _TERMINAL_STATUSES:
            raise ValueError("governed runner returned an invalid terminal status")
        return self._append_run(specification_id=specification_id, result=result, retry_of_run_id=None)

    def retry_run(
        self, *, run_id: str, specification_changes: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise ValueError("experiment run does not exist")
        specification_id = run["specification_id"]
        if specification_changes:
            source = self.get_specification(specification_id)
            assert source is not None
            changed = {**source, **dict(specification_changes)}
            specification_id = self.create_specification(
                research_asset_id=source["research_asset_id"],
                hypothesis=changed["hypothesis"],
                data_scope=changed["data_scope"],
                method=changed["method"],
                metrics=changed["metrics"],
                success_criteria=changed["success_criteria"],
                failure_criteria=changed["failure_criteria"],
                supersedes_specification_id=source["id"],
                owner_principal=str(source["owner_principal"]),
            )["id"]
        specification = self.get_specification(specification_id)
        assert specification is not None
        result = self.backtest_runner.run(specification=specification)
        if result.get("status") not in _TERMINAL_STATUSES:
            raise ValueError("governed runner returned an invalid terminal status")
        return self._append_run(specification_id=specification_id, result=result, retry_of_run_id=run_id)

    def _append_run(
        self, *, specification_id: str, result: Mapping[str, object], retry_of_run_id: str | None
    ) -> dict[str, Any]:
        status = str(result["status"])
        manifest = result.get("governed_input_manifest")
        if not isinstance(manifest, Mapping) or not manifest.get("fingerprint"):
            raise ValueError("governed runner must provide a fingerprinted input manifest")
        constraint_reason = result.get("constraint_reason")
        if status != "completed" and not isinstance(constraint_reason, str):
            raise ValueError("constraint failures require a redacted reason")
        identifier = str(uuid4())
        sandbox_validation: dict[str, object] | None = None
        sandbox_run: dict[str, object] | None = None
        if status == "completed":
            specification = self.get_specification(specification_id)
            if specification is None:
                raise ValueError("completed run specification does not exist")
            validation_id, sandbox_run_id = str(uuid4()), str(uuid4())
            sandbox_validation = {
                "id": validation_id,
                "parent_asset_id": specification["research_asset_id"],
                "status": "validated",
                "audit_reference": f"experiment:{identifier}:sandbox",
            }
            sandbox_run = {"id": sandbox_run_id, "validation_id": validation_id, "status": "completed"}
        run_json = {
            "asset_version": result.get("asset_version"),
            "resolved_parameters": result.get("resolved_parameters", {}),
            "environment": result.get("environment", {}),
            "resources": result.get("resources", {}),
            "metrics": result.get("metrics", {}),
            "artifacts": result.get("artifacts", []),
            "evolution_evidence": result.get("evolution_evidence", {}),
            "retry_of_run_id": retry_of_run_id,
            "diagnostic": {"summary": constraint_reason, "raw_output": None},
            **({"sandbox_validation": sandbox_validation, "sandbox_run": sandbox_run} if sandbox_validation and sandbox_run else {}),
        }
        with self.repository._connection() as connection, connection:
            connection.execute(
                """INSERT INTO advanced_experiment_runs
                    (id, specification_id, status, governed_fingerprint, asset_version, run_json, constraint_reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (identifier, specification_id, status, manifest["fingerprint"], result.get("asset_version"), _json(run_json), constraint_reason, self.repository.now()),
            )
            if sandbox_validation is not None and sandbox_run is not None:
                connection.execute(
                    """INSERT INTO advanced_security_audit
                        (id, authorization_id, job_id, reference, decision, reason, created_at)
                        VALUES (?, NULL, NULL, ?, 'recorded', 'governed experiment sandbox evidence', ?)""",
                    (str(uuid4()), sandbox_validation["audit_reference"], self.repository.now()),
                )
                connection.execute(
                    """INSERT INTO advanced_sandbox_validations
                        (id, parent_asset_id, contract_fingerprint, source_sha256, status, reason, audit_reference, created_at)
                        VALUES (?, ?, ?, ?, 'validated', 'registered_strategy_governed', ?, ?)""",
                    (
                        sandbox_validation["id"], sandbox_validation["parent_asset_id"], manifest["fingerprint"],
                        sha256(str(manifest["fingerprint"]).encode()).hexdigest(),
                        sandbox_validation["audit_reference"], self.repository.now(),
                    ),
                )
                sandbox_manifest = {"status": "completed", "resources": result.get("resources", {})}
                connection.execute(
                    """INSERT INTO advanced_sandbox_runs
                        (id, validation_id, runner_manifest_json, terminal_reason, artifact_reference, created_at)
                        VALUES (?, ?, ?, NULL, ?, ?)""",
                    (sandbox_run["id"], sandbox_run["validation_id"], _json(sandbox_manifest), str(identifier), self.repository.now()),
                )
            row = connection.execute("SELECT * FROM advanced_experiment_runs WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return self._run_row(row, manifest)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.repository._connection() as connection:
            row = connection.execute("SELECT * FROM advanced_experiment_runs WHERE id = ?", (run_id,)).fetchone()
        return None if row is None else self._run_row(row)

    def list_runs(self) -> list[dict[str, Any]]:
        with self.repository._connection() as connection:
            rows = connection.execute("SELECT * FROM advanced_experiment_runs ORDER BY created_at DESC, id DESC").fetchall()
        return [self._run_row(row) for row in rows]

    def completed_run_evidence(self, *, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None or run["status"] != "completed":
            raise ValueError("candidate requires a completed governed experiment run")
        specification = self.get_specification(str(run["specification_id"]))
        if specification is None:
            raise ValueError("completed run specification does not exist")
        return {"run": run, "specification": specification}

    def record_feedback(self, *, run_id: str, conclusion: str, notes: str) -> dict[str, Any]:
        if conclusion not in _FEEDBACK_CONCLUSIONS or not notes.strip():
            raise ValueError("feedback conclusion and notes are invalid")
        run = self.get_run(run_id)
        if run is None or run["status"] != "completed":
            raise ValueError("only completed eligible runs can accept feedback")
        identifier = str(uuid4())
        payload = {"notes": notes, "metrics": run["metrics"], "artifacts": run["artifacts"]}
        with self.repository._connection() as connection, connection:
            try:
                connection.execute(
                    "INSERT INTO advanced_experiment_feedback (id, run_id, conclusion, feedback_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (identifier, run_id, conclusion, _json(payload), self.repository.now()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("run already has one feedback conclusion") from error
            row = connection.execute("SELECT * FROM advanced_experiment_feedback WHERE id = ?", (identifier,)).fetchone()
        assert row is not None
        return self._feedback_row(row)

    def list_feedback(self, *, run_id: str) -> list[dict[str, Any]]:
        with self.repository._connection() as connection:
            rows = connection.execute("SELECT * FROM advanced_experiment_feedback WHERE run_id = ? ORDER BY created_at", (run_id,)).fetchall()
        return [self._feedback_row(row) for row in rows]

    @staticmethod
    def _specification_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        for source, target in (("data_scope_json", "data_scope"), ("metrics_json", "metrics"), ("success_criteria_json", "success_criteria"), ("failure_criteria_json", "failure_criteria")):
            value[target] = json.loads(value.pop(source))
        return value

    @staticmethod
    def _run_row(row: sqlite3.Row, manifest: Mapping[str, object] | None = None) -> dict[str, Any]:
        value = dict(row)
        payload = json.loads(value.pop("run_json"))
        value.update(payload)
        value["governed_input_manifest"] = dict(manifest) if manifest is not None else {"fingerprint": value["governed_fingerprint"]}
        return value

    @staticmethod
    def _feedback_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value.update(json.loads(value.pop("feedback_json")))
        return value
