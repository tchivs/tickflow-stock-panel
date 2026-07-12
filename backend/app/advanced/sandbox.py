"""Fail-closed admission for custom strategy source; never execute it in-process."""
from __future__ import annotations

import ast
import json
import shutil
import tempfile
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.advanced.repository import AdvancedRepository
from app.advanced.schemas import CustomStrategyContract

_PROBE_FIELDS = (
    "user_namespace",
    "mount_namespace",
    "network_namespace",
    "network_absent",
    "governed_input_read_only",
    "temporary_workdir_only",
    "resource_limits",
    "cleanup_verified",
)
_ALLOWED_IMPORTS = frozenset({"json", "math", "socket", "statistics", "subprocess"})


class Launcher(Protocol):
    def capability_probe(self, *, governed_input: Path, workdir: Path) -> object: ...

    def spawn(self, **kwargs: object) -> object: ...


class _UnavailableLauncher:
    """The default launcher is deliberately incapable until a real isolator is injected."""

    def capability_probe(self, *, governed_input: Path, workdir: Path) -> dict[str, bool]:
        del governed_input, workdir
        return {field: False for field in _PROBE_FIELDS}

    def spawn(self, **kwargs: object) -> None:
        del kwargs
        raise RuntimeError("isolated launcher is unavailable")


class CustomStrategySandboxService:
    """Validates untrusted source then runs only through an affirmatively proven launcher."""

    def __init__(
        self,
        *,
        audit_path: Path,
        governed_input: Path,
        launcher: Launcher | None = None,
        feedback_recorder: Callable[..., None] | None = None,
        promotion_service: Callable[..., None] | None = None,
        broker: Callable[..., None] | None = None,
        provider: Callable[..., None] | None = None,
        strategy_engine: Callable[..., None] | None = None,
    ) -> None:
        self._repository = AdvancedRepository(audit_path)
        self._repository.migrate()
        self._governed_input = Path(governed_input)
        self._launcher = launcher or _UnavailableLauncher()
        # Dependencies are accepted solely to make their absence from this boundary explicit.
        self._feedback_recorder = feedback_recorder
        self._promotion_service = promotion_service
        self._broker = broker
        self._provider = provider
        self._strategy_engine = strategy_engine
        self._temporary_handoffs: list[Path] = []

    def submit(self, payload: object) -> dict[str, object]:
        source, source_hash = self._source_hash(payload)
        try:
            contract = self._contract(payload)
        except (TypeError, ValidationError, ValueError):
            return self._reject("contract_invalid", source_hash=source_hash, contract_fingerprint="invalid")
        if source_hash != contract.source_sha256:
            return self._reject("source_hash_mismatch", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract))
        reason = self._validate_ast(source, contract)
        if reason is not None:
            return self._reject(reason, source_hash=source_hash, contract_fingerprint=self._fingerprint(contract))

        workdir = Path(tempfile.mkdtemp(prefix="advanced-sandbox-"))
        try:
            if not self._probe_is_affirmative(workdir):
                return self._reject("isolation_unavailable", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract))
            # Test and production launchers must expose an explicit bounded outcome contract.
            if not hasattr(self._launcher, "runtime_outcome"):
                return self._reject("isolation_unavailable", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract))
            source_path = workdir / "strategy.py"
            source_path.write_text(source, encoding="utf-8")
            source_path.chmod(0o400)
            self._temporary_handoffs.append(workdir)
            outcome = self._launcher.spawn(
                source_path=source_path,
                governed_input=self._governed_input,
                workdir=workdir,
                timeout_seconds=contract.timeout_seconds,
                memory_limit_mb=contract.memory_limit_mb,
                environment={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"},
                start_new_session=True,
            )
            del outcome
            reported = getattr(self._launcher, "runtime_outcome", {"kind": "runner"})
            return self._reject(self._runtime_reason(reported), source_hash=source_hash, contract_fingerprint=self._fingerprint(contract), output=reported.get("output", ""))
        except OSError:
            return self._reject("isolation_unavailable", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract))
        finally:
            self._temporary_handoffs.clear()
            shutil.rmtree(workdir, ignore_errors=True)

    def list_audits(self) -> list[dict[str, object]]:
        return self._repository.list_sandbox_validations()

    def public_validation(self, audit_reference: object) -> dict[str, object]:
        record = self._repository.get_sandbox_validation_by_audit_reference(str(audit_reference))
        if record is None:
            raise ValueError("sandbox audit is unknown")
        return {
            "status": record["status"],
            "reason": record["reason"],
            "audit_reference": record["audit_reference"],
            "source_sha256": record["source_sha256"],
        }

    def temporary_handoffs(self) -> list[Path]:
        return list(self._temporary_handoffs)

    def _reject(self, reason: str, *, source_hash: str, contract_fingerprint: str, output: object = "") -> dict[str, object]:
        audit = self._repository.append_security_audit(decision="rejected", reason=reason)
        validation = self._repository.append_sandbox_validation(
            contract_fingerprint=contract_fingerprint,
            source_sha256=source_hash,
            status="rejected",
            reason=reason,
            audit_reference=str(audit["reference"]),
        )
        diagnostics: dict[str, object] = {"reason": reason, "audit_reference": audit["reference"]}
        if output:
            diagnostics["output_truncated"] = True
            diagnostics["summary"] = str(output)[:512]
        return {"status": "rejected", "reason": reason, "audit_reference": audit["reference"], "diagnostics": diagnostics, "validation_id": validation["id"]}

    def _probe_is_affirmative(self, workdir: Path) -> bool:
        try:
            probe = self._launcher.capability_probe(governed_input=self._governed_input, workdir=workdir)
        except Exception:
            return False
        return all(bool(getattr(probe, field, False)) for field in _PROBE_FIELDS)

    @staticmethod
    def _source_hash(payload: object) -> tuple[str, str]:
        source = payload.get("source", "") if isinstance(payload, dict) else ""
        if not isinstance(source, str):
            source = ""
        return source, sha256(source.encode()).hexdigest()

    @staticmethod
    def _contract(payload: object) -> CustomStrategyContract:
        if not isinstance(payload, dict) or not isinstance(payload.get("contract"), dict):
            raise ValueError("contract is required")
        return CustomStrategyContract.model_validate(payload["contract"])

    @staticmethod
    def _fingerprint(contract: CustomStrategyContract) -> str:
        payload = json.dumps(contract.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode()).hexdigest()

    @staticmethod
    def _validate_ast(source: str, contract: CustomStrategyContract) -> str | None:
        try:
            tree = ast.parse(source, mode="exec")
        except SyntaxError:
            return "contract_invalid"
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"eval", "exec"}:
                    return "dynamic_execution_forbidden"
                if node.func.id == "__import__":
                    return "dynamic_import_forbidden"
                if node.func.id in {"open", "compile", "input"}:
                    return "file_access_forbidden"
            if isinstance(node, ast.Attribute):
                if node.attr in {"system", "popen", "fork", "__globals__", "__subclasses__"}:
                    return "attribute_chain_forbidden"
                if node.attr in {"create_connection", "connect", "urlopen", "request"}:
                    return "network_access_forbidden"
                if node.attr in {"run", "Popen", "call", "check_output"}:
                    return "child_process_forbidden"
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                return "dynamic_import_forbidden"
        if not imports <= set(contract.declared_imports) or not imports <= _ALLOWED_IMPORTS:
            return "undeclared_import"
        return None

    @staticmethod
    def _runtime_reason(outcome: object) -> str:
        kind = outcome.get("kind") if isinstance(outcome, dict) else "runner"
        return {
            "timeout": "timeout_exceeded",
            "memory": "memory_limit_exceeded",
            "output": "output_limit_exceeded",
        }.get(str(kind), "isolation_unavailable")
