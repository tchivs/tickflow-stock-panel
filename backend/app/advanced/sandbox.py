"""Fail-closed admission for custom strategy source; never execute it in-process."""
from __future__ import annotations

import ast
import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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
    "pid_namespace",
    "network_namespace",
    "network_absent",
    "private_root",
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


class LinuxIsolationLauncher:
    """Linux namespace launcher that refuses execution without a fresh full probe."""

    _PROBE_TIMEOUT_SECONDS = 3
    terminal_outcome_contract = True

    def __init__(self) -> None:
        self._proof: dict[str, object] | None = None

    def capability_probe(self, *, governed_input: Path, workdir: Path) -> dict[str, object]:
        evidence = {field: False for field in _PROBE_FIELDS}
        if sys.platform != "linux" or shutil.which("unshare") is None or not os.access("/bin/mount", os.X_OK):
            return evidence
        probe_root = workdir / "probe-root"
        shutil.rmtree(probe_root, ignore_errors=True)
        probe_root.mkdir(mode=0o700, exist_ok=True)
        parent_namespaces = self._namespace_links()
        if set(parent_namespaces) != {"user", "mnt", "pid", "net"}:
            shutil.rmtree(probe_root, ignore_errors=True)
            return evidence
        command = [
            "unshare", "--user", "--map-root-user", "--mount", "--pid", "--net", "--fork", "--mount-proc",
            sys.executable, "-c", self._probe_script(), str(probe_root), str(governed_input),
            json.dumps(parent_namespaces, sort_keys=True), "3", str(128 * 1024 * 1024), str(16 * 1024),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._PROBE_TIMEOUT_SECONDS,
                env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"},
                preexec_fn=self._limits(3, 128),
            )
            reported = json.loads(completed.stdout) if completed.returncode == 0 else {}
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            reported = {}
        finally:
            shutil.rmtree(probe_root, ignore_errors=True)
        if not self._probe_evidence_is_affirmative(reported, parent_namespaces, cleanup_verified=not probe_root.exists()):
            return evidence
        fingerprint = sha256(json.dumps(reported, sort_keys=True).encode()).hexdigest()
        self._proof = {
            **{field: True for field in _PROBE_FIELDS},
            "proof_fingerprint": fingerprint,
            "probed_at": time.monotonic(),
        }
        return dict(self._proof)

    @staticmethod
    def _namespace_links() -> dict[str, str]:
        try:
            return {name: os.readlink(f"/proc/self/ns/{name}") for name in ("user", "mnt", "pid", "net")}
        except OSError:
            return {}

    @staticmethod
    def _probe_evidence_is_affirmative(
        reported: object, parent_namespaces: dict[str, str], *, cleanup_verified: bool
    ) -> bool:
        if not isinstance(reported, dict):
            return False
        namespaces = reported.get("namespaces")
        mounts = reported.get("mounts")
        filesystem = reported.get("filesystem")
        network = reported.get("network")
        limits = reported.get("limits")
        if not all(isinstance(value, dict) for value in (namespaces, mounts, filesystem, network, limits)):
            return False
        assert isinstance(namespaces, dict) and isinstance(mounts, dict)
        assert isinstance(filesystem, dict) and isinstance(network, dict) and isinstance(limits, dict)
        namespace_checks = {
            "user_namespace": "user",
            "mount_namespace": "mnt",
            "pid_namespace": "pid",
            "network_namespace": "net",
        }
        namespaces_are_distinct = all(
            isinstance(namespaces.get(name), str)
            and namespaces[name] != parent_namespaces.get(name)
            for name in namespace_checks.values()
        )
        expected_limits = {"cpu": 3, "address_space": 128 * 1024 * 1024, "file_size": 16 * 1024}
        limits_are_enforced = all(limits.get(name) == value for name, value in expected_limits.items())
        checks = {
            "user_namespace": namespaces_are_distinct,
            "mount_namespace": namespaces_are_distinct,
            "pid_namespace": namespaces_are_distinct,
            "network_namespace": namespaces_are_distinct,
            "network_absent": network.get("connect_blocked") is True and network.get("only_loopback") is True,
            "private_root": mounts.get("private_root") is True and mounts.get("mountinfo_contains_root") is True,
            "governed_input_read_only": filesystem.get("governed_write_blocked") is True,
            "temporary_workdir_only": filesystem.get("workdir_write_succeeds") is True and filesystem.get("outside_write_blocked") is True,
            "resource_limits": limits_are_enforced,
            "cleanup_verified": cleanup_verified,
        }
        return all(checks.values())

    def spawn(self, **kwargs: object) -> dict[str, object]:
        source_path = Path(str(kwargs["source_path"]))
        governed_input = Path(str(kwargs["governed_input"]))
        workdir = Path(str(kwargs["workdir"]))
        timeout_seconds = int(kwargs["timeout_seconds"])
        memory_limit_mb = int(kwargs["memory_limit_mb"])
        proof = self._proof
        if proof is None or time.monotonic() - float(proof["probed_at"]) > 30:
            raise OSError("isolation proof is unavailable or stale")
        private_root = workdir / "root"
        private_root.mkdir(mode=0o700, exist_ok=True)
        bootstrap = workdir / "bootstrap.py"
        bootstrap.write_text(self._bootstrap_script(), encoding="utf-8")
        bootstrap.chmod(0o500)
        command = [
            "unshare", "--user", "--map-root-user", "--mount", "--pid", "--net", "--fork", "--mount-proc",
            sys.executable, str(bootstrap), str(private_root), str(source_path), str(governed_input), str(workdir),
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                close_fds=True,
                start_new_session=True,
                preexec_fn=self._limits(timeout_seconds, memory_limit_mb),
            )
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            return self._outcome("failed", "timeout_exceeded", proof, timeout_seconds, memory_limit_mb)
        finally:
            shutil.rmtree(private_root, ignore_errors=True)
        if len(stdout) + len(stderr) > 16 * 1024:
            return self._outcome("failed", "output_limit_exceeded", proof, timeout_seconds, memory_limit_mb)
        reason = None if process.returncode == 0 else "runner_failed"
        return self._outcome("completed" if reason is None else "failed", reason, proof, timeout_seconds, memory_limit_mb)

    @staticmethod
    def _limits(timeout_seconds: int, memory_limit_mb: int):
        def apply() -> None:
            resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds, timeout_seconds))
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit_mb * 1024 * 1024, memory_limit_mb * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024, 16 * 1024))

        return apply

    @staticmethod
    def _outcome(status: str, reason: str | None, proof: dict[str, object], timeout_seconds: int, memory_limit_mb: int) -> dict[str, object]:
        return {
            "status": status,
            "terminal_reason": reason,
            "proof_fingerprint": proof["proof_fingerprint"],
            "resources": {"wall_clock_seconds": timeout_seconds, "memory_limit_mb": memory_limit_mb, "output_limit_bytes": 16 * 1024},
        }

    @staticmethod
    def _probe_script() -> str:
        return """import json, os, resource, socket, subprocess, sys
root, governed, parent_json, expected_cpu, expected_as, expected_fsize = sys.argv[1:]
parent = json.loads(parent_json)

def mount(*args):
    return subprocess.run(['/bin/mount', *args], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

def blocked_write(path, data='x'):
    try:
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(data)
    except OSError:
        return True
    return False

def namespace(name):
    try:
        return os.readlink('/proc/self/ns/' + name)
    except OSError:
        return ''

try:
    mount('--make-rprivate', '/')
    root_ok = mount('-t', 'tmpfs', '-o', 'size=1m,nosuid,nodev,noexec', 'tmpfs', root)
    os.makedirs(root + '/input', mode=0o700, exist_ok=True)
    os.makedirs(root + '/work', mode=0o700, exist_ok=True)
    input_ok = root_ok and mount('--bind', governed, root + '/input') and mount('-o', 'remount,bind,ro', root + '/input')
    work_ok = root_ok and mount('-t', 'tmpfs', '-o', 'size=512k,nosuid,nodev,noexec', 'tmpfs', root + '/work')
    root_read_only = mount('-o', 'remount,ro', root)
    work_file = root + '/work/probe-write'
    try:
        with open(work_file, 'w', encoding='utf-8') as handle:
            handle.write('ok')
        workdir_write_succeeds = True
    except OSError:
        workdir_write_succeeds = False
    try:
        interfaces = [name for _, name in socket.if_nameindex()]
    except OSError:
        interfaces = ['unknown']
    try:
        socket.create_connection(('203.0.113.1', 9), timeout=0.2).close()
        connect_blocked = False
    except OSError:
        connect_blocked = True
    cpu = resource.getrlimit(resource.RLIMIT_CPU)[0]
    address_space = resource.getrlimit(resource.RLIMIT_AS)[0]
    file_size = resource.getrlimit(resource.RLIMIT_FSIZE)[0]
    with open('/proc/self/mountinfo', encoding='utf-8') as handle:
        mountinfo = handle.read()
    print(json.dumps({
        'namespaces': {name: namespace(name) for name in ('user', 'mnt', 'pid', 'net')},
        'mounts': {'private_root': root_ok and root_read_only and os.path.ismount(root), 'mountinfo_contains_root': root in mountinfo},
        'filesystem': {
            'governed_write_blocked': input_ok and blocked_write(root + '/input/.sandbox-write'),
            'workdir_write_succeeds': work_ok and workdir_write_succeeds,
            'outside_write_blocked': root_read_only and blocked_write(root + '/outside-write'),
        },
        'network': {'only_loopback': interfaces == ['lo'], 'connect_blocked': connect_blocked},
        'limits': {'cpu': cpu, 'address_space': address_space, 'file_size': file_size},
    }))
except Exception:
    print('{}')
    raise SystemExit(1)
"""

    @staticmethod
    def _bootstrap_script() -> str:
        return """import os, sys
root, source, governed, work = sys.argv[1:]
for path in ('/usr', '/lib', '/lib64'):
    if os.path.exists(path):
        target = root + path
        os.makedirs(target, exist_ok=True)
        os.system('/bin/mount --bind ' + path + ' ' + target)
        os.system('/bin/mount -o remount,bind,ro ' + target)
os.makedirs(root + '/input', exist_ok=True); os.makedirs(root + '/work', exist_ok=True)
os.system('/bin/mount --bind ' + source + ' ' + root + '/input/strategy.py')
os.system('/bin/mount -o remount,bind,ro ' + root + '/input/strategy.py')
os.system('/bin/mount --bind ' + governed + ' ' + root + '/input/governed')
os.system('/bin/mount -o remount,bind,ro ' + root + '/input/governed')
os.system('/bin/mount --bind ' + work + ' ' + root + '/work')
os.chroot(root); os.chdir('/work')
os.execve('/usr/bin/python3', ['/usr/bin/python3', '/input/strategy.py'], {'PATH': '/usr/bin:/bin', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
"""


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
        self._launcher = launcher or LinuxIsolationLauncher()
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
            if not getattr(self._launcher, "terminal_outcome_contract", False) and not hasattr(self._launcher, "runtime_outcome"):
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
            if not isinstance(outcome, dict):
                reported = getattr(self._launcher, "runtime_outcome", None)
                if isinstance(reported, dict):
                    return self._reject(
                        self._runtime_reason(reported),
                        source_hash=source_hash,
                        contract_fingerprint=self._fingerprint(contract),
                        output=reported.get("output", ""),
                    )
                return self._reject("isolation_unavailable", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract))
            validation = self._repository.append_sandbox_validation(
                contract_fingerprint=self._fingerprint(contract),
                source_sha256=source_hash,
                status="validated" if outcome.get("status") == "completed" else "constraint_failed",
                reason=str(outcome.get("terminal_reason") or "completed"),
                audit_reference=str(self._repository.append_security_audit(
                    decision="recorded" if outcome.get("status") == "completed" else "rejected",
                    reason=str(outcome.get("terminal_reason") or "sandbox_completed"),
                )["reference"]),
            )
            run = self._repository.append_sandbox_run(
                validation_id=str(validation["id"]),
                runner_manifest=outcome,
                terminal_reason=outcome.get("terminal_reason") if isinstance(outcome.get("terminal_reason"), str) else None,
                artifact_reference=None,
            )
            return self.public_run(str(run["id"]))
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

    def public_run(self, run_id: object) -> dict[str, object]:
        record = self._repository.get_sandbox_run(str(run_id))
        if record is None:
            raise ValueError("sandbox run is unknown")
        from app.advanced.projections import sandbox_run

        return sandbox_run(record)

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
        return all(bool(getattr(probe, field, False) if not isinstance(probe, dict) else probe.get(field, False)) for field in _PROBE_FIELDS)

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
