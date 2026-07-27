"""Fail-closed admission for custom strategy source; never execute it in-process."""
from __future__ import annotations

import ast
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.advanced.repository import AdvancedRepository
from app.advanced.schemas import CustomStrategyContract
from app.advanced.strategy_policy import (
    CompiledStrategyProgram,
    StrategyInstruction,
    StrategyProgramPolicy,
    StrategyProgramViolation,
)

try:
    import resource
except ImportError:  # pragma: no cover - exercised by a fresh interpreter regression
    resource = None  # type: ignore[assignment]

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
_ALLOWED_IMPORTS = frozenset({"json", "math", "statistics"})
_REFLECTION_BUILTINS = frozenset(
    {"delattr", "dir", "getattr", "globals", "locals", "setattr", "vars"}
)
_MAX_PANEL_ITEMS = 64
_MAX_PANEL_INT_BITS = 256
_MAX_PANEL_TEXT_BYTES = 4 * 1024
_MAX_PANEL_BYTES = 16 * 1024


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
    _REAP_TIMEOUT_SECONDS = 1.0
    terminal_outcome_contract = True

    def __init__(self) -> None:
        self._proof: dict[str, object] | None = None

    def capability_probe(self, *, governed_input: Path, workdir: Path) -> dict[str, object]:
        evidence = {field: False for field in _PROBE_FIELDS}
        if (
            sys.platform != "linux"
            or resource is None
            or shutil.which("unshare") is None
            or not os.access("/bin/mount", os.X_OK)
        ):
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
        if resource is None:
            raise OSError("POSIX resource limits are unavailable")
        program = kwargs.get("program")
        panel = kwargs.get("panel")
        if not isinstance(program, CompiledStrategyProgram) or not isinstance(panel, dict):
            raise OSError("controlled strategy program handoff is invalid")
        StrategyProgramPolicy.validate(program)
        governed_input = Path(str(kwargs["governed_input"]))
        workdir = Path(str(kwargs["workdir"]))
        timeout_seconds = int(kwargs["timeout_seconds"])
        memory_limit_mb = int(kwargs["memory_limit_mb"])
        proof = self._proof
        if proof is None or time.monotonic() - float(proof["probed_at"]) > 30:
            raise OSError("isolation proof is unavailable or stale")
        private_root = workdir / "root"
        private_root.mkdir(mode=0o700, exist_ok=True)
        source_path = workdir / "strategy.py"
        source_path.write_text(
            self._interpreter_script(program=program, panel=panel),
            encoding="utf-8",
        )
        source_path.chmod(0o400)
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
            self._terminate_with_deadline(process)
            return self._outcome("failed", "timeout_exceeded", proof, timeout_seconds, memory_limit_mb)
        finally:
            shutil.rmtree(private_root, ignore_errors=True)
        if len(stdout) + len(stderr) > 16 * 1024:
            return self._outcome("failed", "output_limit_exceeded", proof, timeout_seconds, memory_limit_mb)
        reason = None if process.returncode == 0 else "runner_failed"
        return self._outcome("completed" if reason is None else "failed", reason, proof, timeout_seconds, memory_limit_mb)

    def _terminate_with_deadline(self, process: object) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=self._REAP_TIMEOUT_SECONDS)
            return
        except subprocess.TimeoutExpired:
            # A descendant that escaped the process group can retain inherited
            # stdout/stderr descriptors. Closing our pipe endpoints prevents
            # that descendant from turning timeout cleanup into an unbounded wait.
            for pipe in (getattr(process, "stdout", None), getattr(process, "stderr", None)):
                if pipe is not None:
                    pipe.close()
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=self._REAP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            pass

    @staticmethod
    def _limits(timeout_seconds: int, memory_limit_mb: int):
        if resource is None:
            raise OSError("POSIX resource limits are unavailable")

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
    private_tree = mount('--make-rprivate', '/')
    root_ok = private_tree and mount('-t', 'tmpfs', '-o', 'size=1m,nosuid,nodev,noexec', 'tmpfs', root)
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
        return """import os, subprocess, sys
root, source, governed, work = sys.argv[1:]
del work

def mount(*args):
    completed = subprocess.run(['/bin/mount', *args], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if completed.returncode != 0:
        raise OSError('sandbox mount setup failed')

def make_file(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    os.close(descriptor)

def isolated_topology(root):
    try:
        with open('/proc/self/mountinfo', encoding='utf-8') as handle:
            mountinfo = handle.readlines()
    except OSError:
        return False
    entries = {}
    for line in mountinfo:
        before, separator, after = line.partition(' - ')
        fields = before.split()
        if not separator or len(fields) < 6 or fields[4] not in (root, root + '/input', root + '/strategy.py', root + '/work'):
            continue
        entries[fields[4]] = (fields, after.split())
    if set(entries) != {root, root + '/input', root + '/strategy.py', root + '/work'}:
        return False
    root_fields, _ = entries[root]
    input_fields, _ = entries[root + '/input']
    source_fields, _ = entries[root + '/strategy.py']
    work_fields, work_filesystem = entries[root + '/work']
    propagation = root_fields[6:]
    return (
        os.path.ismount(root)
        and 'ro' in root_fields[5].split(',')
        and 'ro' in input_fields[5].split(',')
        and 'ro' in source_fields[5].split(',')
        and 'rw' in work_fields[5].split(',')
        and work_filesystem[:1] == ['tmpfs']
        and not any(value.startswith(('shared:', 'master:', 'propagate_from:')) for value in propagation)
    )

try:
    mount('--make-rprivate', '/')
    mount('-t', 'tmpfs', '-o', 'size=1m,nosuid,nodev,noexec', 'tmpfs', root)
    os.makedirs(root + '/input', mode=0o700, exist_ok=True)
    os.makedirs(root + '/work', mode=0o700, exist_ok=True)
    mount('--bind', governed, root + '/input')
    mount('-o', 'remount,bind,ro', root + '/input')
    mount('-t', 'tmpfs', '-o', 'size=512k,nosuid,nodev,noexec', 'tmpfs', root + '/work')
    make_file(root + '/strategy.py')
    mount('--bind', source, root + '/strategy.py')
    mount('-o', 'remount,bind,ro', root + '/strategy.py')
    for path in ('/usr', '/lib', '/lib64'):
        if os.path.exists(path):
            target = root + path
            os.makedirs(target, exist_ok=True)
            mount('--bind', path, target)
            mount('-o', 'remount,bind,ro', target)
    mount('-o', 'remount,ro', root)
    if not isolated_topology(root):
        raise OSError('sandbox root topology verification failed')
    os.chroot(root)
    os.chdir('/work')
    os.execve('/usr/bin/python3', ['/usr/bin/python3', '/strategy.py'], {'PATH': '/usr/bin:/bin', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
except Exception:
    raise SystemExit(126)
"""

    @staticmethod
    def _interpreter_script(
        *, program: CompiledStrategyProgram, panel: dict[str, object]
    ) -> str:
        """Return a fixed interpreter with the immutable IR embedded only as JSON data."""
        payload = json.dumps(
            {"program": program.to_payload(), "panel": panel},
            sort_keys=True,
            separators=(",", ":"),
        )
        encoded_payload = json.dumps(payload)
        return f"""import json, math
PAYLOAD = json.loads({encoded_payload})
MAX_CONTAINER_ITEMS = 64
MAX_INSTRUCTIONS = 256
MAX_INT_BITS = 256
MAX_TEXT_BYTES = 4096
MAX_RESULT_BYTES = 16384
steps = 0

def primitive(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value.bit_length() > MAX_INT_BITS:
            raise ValueError('integer limit exceeded')
        return value
    if isinstance(value, str):
        if len(value.encode('utf-8')) > MAX_TEXT_BYTES:
            raise ValueError('text limit exceeded')
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ValueError('non-primitive value')

def interpret(node, panel):
    global steps
    steps += 1
    if steps > MAX_INSTRUCTIONS:
        raise ValueError('instruction limit exceeded')
    if not isinstance(node, dict) or set(node) != {{'opcode', 'operands'}}:
        raise ValueError('invalid instruction')
    opcode = node['opcode']
    operands = node['operands']
    if not isinstance(opcode, str) or not isinstance(operands, list):
        raise ValueError('invalid instruction shape')
    if opcode == 'literal' and len(operands) == 1:
        return primitive(operands[0])
    if opcode == 'mapping' and operands and len(operands) % 2 == 0:
        return {{str(operands[index]): interpret(operands[index + 1], panel) for index in range(0, len(operands), 2)}}
    if opcode == 'panel_value' and len(operands) == 1 and isinstance(operands[0], str):
        if operands[0] not in panel:
            raise ValueError('panel field unavailable')
        return primitive(panel[operands[0]])
    if opcode == 'intrinsic' and operands and isinstance(operands[0], str):
        name = operands[0]
        values = [interpret(item, panel) for item in operands[1:]]
        if name == 'abs' and len(values) == 1:
            return primitive(abs(values[0]))
        if name == 'min' and 1 <= len(values) <= 8:
            return primitive(min(values))
        if name == 'max' and 1 <= len(values) <= 8:
            return primitive(max(values))
        if name == 'round' and 1 <= len(values) <= 2:
            return primitive(round(*values))
        raise ValueError('invalid intrinsic')
    values = [interpret(item, panel) for item in operands]
    if opcode == 'positive' and len(values) == 1:
        return primitive(+values[0])
    if opcode == 'negative' and len(values) == 1:
        return primitive(-values[0])
    if opcode == 'not' and len(values) == 1:
        return not values[0]
    if opcode == 'all' and 2 <= len(values) <= 8:
        return all(values)
    if opcode == 'any' and 2 <= len(values) <= 8:
        return any(values)
    if opcode == 'choose' and len(values) == 3:
        return values[1] if values[0] else values[2]
    if len(values) != 2:
        raise ValueError('invalid opcode arity')
    if opcode == 'multiply':
        left, right = values
        text = left if isinstance(left, str) else right if isinstance(right, str) else None
        count = right if isinstance(left, str) else left if isinstance(right, str) else None
        if isinstance(text, str) and isinstance(count, int) and not isinstance(count, bool):
            if max(count, 0) * len(text.encode('utf-8')) > MAX_TEXT_BYTES:
                raise ValueError('text multiplication limit exceeded')
    binary = {{
        'add': lambda: values[0] + values[1],
        'subtract': lambda: values[0] - values[1],
        'multiply': lambda: values[0] * values[1],
        'divide': lambda: values[0] / values[1],
        'modulo': lambda: values[0] % values[1],
        'equal': lambda: values[0] == values[1],
        'not_equal': lambda: values[0] != values[1],
        'less': lambda: values[0] < values[1],
        'less_equal': lambda: values[0] <= values[1],
        'greater': lambda: values[0] > values[1],
        'greater_equal': lambda: values[0] >= values[1],
    }}
    if opcode not in binary:
        raise ValueError('invalid opcode')
    return primitive(binary[opcode]())

program = PAYLOAD['program']
if program.get('schema_version') != 'strategy-program-v1' or set(program) != {{'schema_version', 'result'}}:
    raise SystemExit(126)
try:
    panel = PAYLOAD['panel']
    if not isinstance(panel, dict) or len(panel) > MAX_CONTAINER_ITEMS:
        raise ValueError('panel limit exceeded')
    panel = {{str(key): primitive(value) for key, value in panel.items()}}
    if any(not key or len(key) > 64 for key in panel):
        raise ValueError('panel key invalid')
    result = interpret(program['result'], panel)
    if not isinstance(result, dict) or not result or 'signal' not in result or len(result) > MAX_CONTAINER_ITEMS:
        raise ValueError('result invalid')
    result = {{str(key): primitive(value) for key, value in result.items()}}
    encoded = json.dumps(result, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > MAX_RESULT_BYTES:
        raise ValueError('result limit exceeded')
except (ArithmeticError, KeyError, MemoryError, TypeError, ValueError):
    raise SystemExit(126)
print(encoded)
"""


class CustomStrategySandboxService:
    """Validates untrusted source then runs only through an affirmatively proven launcher."""

    def __init__(
        self,
        *,
        audit_path: Path,
        governed_input: Path,
        launcher: Launcher | None = None,
        governed_panel_resolver: Callable[..., Mapping[str, object]] | None = None,
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
        self._governed_panel_resolver = governed_panel_resolver
        # Dependencies are accepted solely to make their absence from this boundary explicit.
        self._feedback_recorder = feedback_recorder
        self._promotion_service = promotion_service
        self._broker = broker
        self._provider = provider
        self._strategy_engine = strategy_engine
        self._temporary_handoffs: list[Path] = []
        self._strategy_policy = StrategyProgramPolicy()

    def submit(self, payload: object) -> dict[str, object]:
        source, source_hash = self._source_hash(payload)
        try:
            contract = self._contract(payload)
        except (TypeError, ValidationError, ValueError):
            return self._reject("contract_invalid", source_hash=source_hash, contract_fingerprint="invalid", parent_asset_id="")
        if source_hash != contract.source_sha256:
            return self._reject("source_hash_mismatch", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract), parent_asset_id=contract.parent_asset_id)
        try:
            program = self._strategy_policy.compile(source)
        except StrategyProgramViolation:
            # Legacy diagnostic codes remain presentation compatibility only.
            # Admission authority is exclusively the positive compiler above.
            reason = self._validate_ast(source, contract) or StrategyProgramViolation.code
            return self._reject(reason, source_hash=source_hash, contract_fingerprint=self._fingerprint(contract), parent_asset_id=contract.parent_asset_id)
        try:
            panel = self._resolve_governed_panel(program, contract)
        except Exception:
            return self._reject(
                "governed_panel_unavailable",
                source_hash=source_hash,
                contract_fingerprint=self._fingerprint(contract),
                parent_asset_id=contract.parent_asset_id,
            )

        workdir = Path(tempfile.mkdtemp(prefix="advanced-sandbox-"))
        try:
            if not self._probe_is_affirmative(workdir):
                return self._reject("isolation_unavailable", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract), parent_asset_id=contract.parent_asset_id)
            if not getattr(self._launcher, "terminal_outcome_contract", False) and not hasattr(self._launcher, "runtime_outcome"):
                return self._reject("isolation_unavailable", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract), parent_asset_id=contract.parent_asset_id)
            self._temporary_handoffs.append(workdir)
            outcome = self._launcher.spawn(
                program=program,
                panel=panel,
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
                        parent_asset_id=contract.parent_asset_id,
                        output=reported.get("output", ""),
                    )
                return self._reject("isolation_unavailable", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract), parent_asset_id=contract.parent_asset_id)
            validation = self._repository.append_sandbox_validation(
                parent_asset_id=contract.parent_asset_id,
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
            return self._reject("isolation_unavailable", source_hash=source_hash, contract_fingerprint=self._fingerprint(contract), parent_asset_id=contract.parent_asset_id)
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

    def sandbox_run(self, run_id: object) -> dict[str, object] | None:
        return self._repository.get_sandbox_run(str(run_id))

    def sandbox_runs(self) -> list[dict[str, object]]:
        return self._repository.list_sandbox_runs()

    def temporary_handoffs(self) -> list[Path]:
        return list(self._temporary_handoffs)

    def _reject(self, reason: str, *, source_hash: str, contract_fingerprint: str, parent_asset_id: str, output: object = "") -> dict[str, object]:
        audit = self._repository.append_security_audit(decision="rejected", reason=reason)
        validation = self._repository.append_sandbox_validation(
            parent_asset_id=parent_asset_id,
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

    def _resolve_governed_panel(
        self,
        program: CompiledStrategyProgram,
        contract: CustomStrategyContract,
    ) -> dict[str, object]:
        required_fields = self._required_panel_fields(program.result)
        resolver = self._governed_panel_resolver
        if resolver is None:
            if required_fields:
                raise ValueError("authoritative governed panel is unavailable")
            return {}
        raw_panel = resolver(
            contract=contract,
            parent_asset_id=contract.parent_asset_id,
            governed_input=self._governed_input,
        )
        panel = self._bounded_primitive_panel(raw_panel)
        if not required_fields <= panel.keys():
            raise ValueError("authoritative governed panel is incomplete")
        return panel

    @staticmethod
    def _required_panel_fields(
        instruction: StrategyInstruction,
    ) -> frozenset[str]:
        fields: set[str] = set()
        pending = [instruction]
        while pending:
            current = pending.pop()
            if current.opcode == "panel_value":
                field = current.operands[0]
                if not isinstance(field, str):
                    raise ValueError("governed panel instruction is invalid")
                fields.add(field)
            pending.extend(
                operand
                for operand in current.operands
                if isinstance(operand, StrategyInstruction)
            )
        return frozenset(fields)

    @staticmethod
    def _bounded_primitive_panel(
        value: Mapping[str, object],
    ) -> dict[str, object]:
        if not isinstance(value, Mapping) or len(value) > _MAX_PANEL_ITEMS:
            raise ValueError("governed panel mapping is invalid")
        panel: dict[str, object] = {}
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or not key
                or len(key) > 64
                or not key.replace("_", "").isalnum()
            ):
                raise ValueError("governed panel key is invalid")
            if item is None or isinstance(item, bool):
                primitive = item
            elif isinstance(item, int):
                if item.bit_length() > _MAX_PANEL_INT_BITS:
                    raise ValueError("governed panel integer is too large")
                primitive = item
            elif isinstance(item, float):
                if not math.isfinite(item):
                    raise ValueError("governed panel number is not finite")
                primitive = item
            elif isinstance(item, str):
                if len(item.encode("utf-8")) > _MAX_PANEL_TEXT_BYTES:
                    raise ValueError("governed panel text is too large")
                primitive = item
            else:
                raise ValueError("governed panel value is not primitive")
            panel[key] = primitive
        encoded = json.dumps(
            panel, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded) > _MAX_PANEL_BYTES:
            raise ValueError("governed panel mapping is too large")
        return panel

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
                if node.func.id in _REFLECTION_BUILTINS:
                    return "module_reflection_forbidden"
                if node.func.id in {"open", "compile", "input"}:
                    return "file_access_forbidden"
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                return "module_reflection_forbidden"
            if isinstance(node, ast.Attribute):
                if node.attr.startswith("__") or node.attr.endswith("__"):
                    return "module_reflection_forbidden"
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
