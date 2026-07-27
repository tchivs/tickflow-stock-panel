"""RED contracts for fail-closed custom-strategy admission and isolation."""
from __future__ import annotations

import json
import io
import sqlite3
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

SOURCE = "def run(panel):\n    return {'signal': 'hold'}\n"


@dataclass
class Spy:
    calls: list[dict[str, object]] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


@dataclass
class Probe:
    user_namespace: bool = True
    mount_namespace: bool = True
    pid_namespace: bool = True
    network_namespace: bool = True
    network_absent: bool = True
    private_root: bool = True
    governed_input_read_only: bool = True
    temporary_workdir_only: bool = True
    resource_limits: bool = True
    cleanup_verified: bool = True


class FakeLauncher:
    def __init__(self, probe: Probe | None = None) -> None:
        self.probe = probe or Probe()
        self.probed: list[dict[str, Path]] = []
        self.spawned: list[dict[str, object]] = []

    def capability_probe(self, *, governed_input: Path, workdir: Path) -> Probe:
        self.probed.append({"governed_input": governed_input, "workdir": workdir})
        return self.probe

    def spawn(self, **kwargs: object) -> None:
        self.spawned.append(kwargs)


class TerminalLauncher(FakeLauncher):
    terminal_outcome_contract = True

    def spawn(self, **kwargs: object) -> dict[str, object]:
        self.spawned.append(kwargs)
        return {
            "status": "completed",
            "terminal_reason": None,
            "proof_fingerprint": "safe-proof",
            "resources": {"wall_clock_seconds": 5, "memory_limit_mb": 128},
            "stdout": "must never leave the service",
            "workdir_path": "/private/sandbox/work",
        }


def _submission(source: str = SOURCE, **contract_overrides: object) -> dict[str, object]:
    source_sha256 = sha256(source.encode()).hexdigest()
    contract = {
        "contract_version": "advanced-strategy-v1",
        "parent_asset_id": "registered-research-asset-v1",
        "declared_inputs": ["governed_panel"],
        "declared_imports": [],
        "timeout_seconds": 5,
        "memory_limit_mb": 128,
        "source_sha256": source_sha256,
    }
    contract.update(contract_overrides)
    return {"contract": contract, "source": source}


def _service(tmp_path, *, probe: Probe | None = None):
    # Import inside the fixture keeps this Wave 0 file free of production imports at collection.
    from app.advanced.sandbox import CustomStrategySandboxService

    launcher = FakeLauncher(probe)
    feedback = Spy()
    promotion = Spy()
    broker = Spy()
    provider = Spy()
    strategy_engine = Spy()
    service = CustomStrategySandboxService(
        audit_path=tmp_path / "operational.db",
        governed_input=tmp_path / "governed-panel",
        launcher=launcher,
        feedback_recorder=feedback,
        promotion_service=promotion,
        broker=broker,
        provider=provider,
        strategy_engine=strategy_engine,
    )
    return service, launcher, feedback, promotion, broker, provider, strategy_engine


def _assert_safe_rejection(result: dict[str, object], launcher: FakeLauncher, *spies: Spy) -> None:
    assert result["status"] == "rejected"
    assert result["reason"] in {
        "contract_invalid",
        "source_hash_mismatch",
        "dynamic_execution_forbidden",
        "dynamic_import_forbidden",
        "module_reflection_forbidden",
        "attribute_chain_forbidden",
        "undeclared_import",
        "file_access_forbidden",
        "network_access_forbidden",
        "child_process_forbidden",
        "isolation_unavailable",
        "timeout_exceeded",
        "memory_limit_exceeded",
        "output_limit_exceeded",
        "strategy_program_forbidden",
        "governed_panel_unavailable",
    }
    assert launcher.spawned == []
    assert all(spy.calls == [] for spy in spies)
    assert set(result["diagnostics"]) <= {"reason", "audit_reference", "output_truncated"}
    assert "source" not in result and "traceback" not in result and "path" not in result


@pytest.mark.parametrize(
    ("payload", "expected_reason"),
    [
        ({"contract": {**_submission()["contract"], "unexpected": "field"}, "source": SOURCE}, "contract_invalid"),
        (_submission(source="print('different')\n", source_sha256="0" * 64), "source_hash_mismatch"),
        (_submission("eval('1 + 1')\n"), "dynamic_execution_forbidden"),
        (_submission("__import__('os')\n"), "dynamic_import_forbidden"),
        (
            _submission(
                textwrap.dedent(
                    """
                    import json

                    builtins = getattr(json, "__builtins__")
                    importer = builtins["__import__"]
                    module = importer("subprocess")
                    constructor = getattr(module, "Popen")
                    constructor(
                        ["/usr/bin/python3", "-c", "import os,time; os.setsid(); time.sleep(60)"]
                    )
                    """
                ),
                declared_imports=["json"],
            ),
            "module_reflection_forbidden",
        ),
        (
            _submission(
                "import json\nbuiltins = json.__builtins__\n",
                declared_imports=["json"],
            ),
            "module_reflection_forbidden",
        ),
        (
            _submission(
                "import json\nmodule_namespace = vars(json)\n",
                declared_imports=["json"],
            ),
            "module_reflection_forbidden",
        ),
        (_submission("import os\nos.system('id')\n"), "attribute_chain_forbidden"),
        (_submission("import json\ndef run(panel): return json.dumps({})\n"), "undeclared_import"),
        (_submission("def run(panel):\n    return open('/etc/passwd').read()\n"), "file_access_forbidden"),
        (_submission("import socket\ndef run(panel): return socket.create_connection(('example.test', 80))\n", declared_imports=["socket"]), "network_access_forbidden"),
        (_submission("import subprocess\ndef run(panel): return subprocess.run(['id'])\n", declared_imports=["subprocess"]), "child_process_forbidden"),
        (
            _submission(
                "import subprocess\ndef run(panel):\n    return getattr(subprocess, 'Popen')(['sleep', '60'], start_new_session=True)\n",
                declared_imports=["subprocess"],
            ),
            "module_reflection_forbidden",
        ),
        (
            _submission(
                "import socket\ndef run(panel):\n    return socket\n",
                declared_imports=["socket"],
            ),
            "undeclared_import",
        ),
    ],
)
def test_hostile_submission_is_rejected_before_any_host_execution(tmp_path, payload, expected_reason):
    service, launcher, feedback, promotion, broker, provider, strategy_engine = _service(tmp_path)

    result = service.submit(payload)

    _assert_safe_rejection(result, launcher, feedback, promotion, broker, provider, strategy_engine)
    assert result["reason"] == expected_reason


def test_r43_cr01_positive_interpreter_hold_program_runs_without_python_authority(tmp_path):
    from app.advanced.sandbox import CustomStrategySandboxService
    from app.advanced.strategy_policy import CompiledStrategyProgram

    launcher = TerminalLauncher()
    service = CustomStrategySandboxService(
        audit_path=tmp_path / "operational.db",
        governed_input=tmp_path / "governed-panel",
        launcher=launcher,
    )

    result = service.submit(_submission())

    assert result["status"] == "completed"
    assert len(launcher.spawned) == 1
    handoff = launcher.spawned[0]
    assert set(handoff) == {
        "program",
        "panel",
        "governed_input",
        "workdir",
        "timeout_seconds",
        "memory_limit_mb",
        "environment",
        "start_new_session",
    }
    assert handoff["panel"] == {}
    program = handoff["program"]
    assert isinstance(program, CompiledStrategyProgram)
    assert program.schema_version == "strategy-program-v1"
    assert program.interpret({}) == {"signal": "hold"}
    assert SOURCE not in repr(handoff)
    assert all(
        not callable(value) and not isinstance(value, type(sys))
        for key, value in handoff.items()
        if key not in {"program"}
    )


def test_strategy_panel_lookup_is_structurally_admitted_and_uses_the_governed_panel_once(
    tmp_path,
):
    from app.advanced.sandbox import CustomStrategySandboxService
    from app.advanced.strategy_policy import StrategyProgramPolicy

    source = "def run(panel):\n    return {'signal': panel['decision']}\n"
    program = StrategyProgramPolicy().compile(source)

    assert program.interpret({"decision": "buy"}) == {"signal": "buy"}

    class ChildInterpreterLauncher(TerminalLauncher):
        child_result: dict[str, object] | None = None

        def spawn(self, **kwargs: object) -> dict[str, object]:
            from app.advanced.sandbox import LinuxIsolationLauncher

            self.spawned.append(kwargs)
            script = LinuxIsolationLauncher._interpreter_script(
                program=kwargs["program"],
                panel=kwargs["panel"],
            )
            completed = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                check=False,
                text=True,
                timeout=3,
            )
            assert completed.returncode == 0
            assert completed.stderr == ""
            self.child_result = json.loads(completed.stdout)
            return {
                "status": "completed",
                "terminal_reason": None,
                "proof_fingerprint": "safe-proof",
                "resources": {
                    "wall_clock_seconds": 5,
                    "memory_limit_mb": 128,
                },
            }

    resolved: list[dict[str, object]] = []

    def governed_panel_resolver(**context: object) -> dict[str, object]:
        resolved.append(context)
        assert context["parent_asset_id"] == "registered-research-asset-v1"
        assert context["governed_input"] == tmp_path / "governed-panel"
        return {"decision": "buy"}

    launcher = ChildInterpreterLauncher()
    service = CustomStrategySandboxService(
        audit_path=tmp_path / "operational.db",
        governed_input=tmp_path / "governed-panel",
        launcher=launcher,
        governed_panel_resolver=governed_panel_resolver,
    )
    result = service.submit(_submission(source))

    assert result["status"] == "completed"
    assert len(launcher.spawned) == 1
    assert launcher.spawned[0]["program"] == program
    assert launcher.spawned[0]["panel"] == {"decision": "buy"}
    assert launcher.child_result == {"signal": "buy"}
    assert len(resolved) == 1


def test_panel_lookup_without_authoritative_resolver_fails_before_probe(tmp_path):
    from app.advanced.sandbox import CustomStrategySandboxService

    launcher = TerminalLauncher()
    source = "def run(panel):\n    return {'signal': panel['decision']}\n"
    service = CustomStrategySandboxService(
        audit_path=tmp_path / "operational.db",
        governed_input=tmp_path / "governed-panel",
        launcher=launcher,
    )

    result = service.submit(_submission(source))

    assert result["status"] == "rejected"
    assert result["reason"] == "governed_panel_unavailable"
    assert launcher.probed == []
    assert launcher.spawned == []


def test_compile_submit_and_launcher_handoff_never_interpret_in_the_parent(
    tmp_path, monkeypatch
):
    from app.advanced import strategy_policy
    from app.advanced.sandbox import CustomStrategySandboxService

    def forbidden_parent_interpret(*_args, **_kwargs):
        raise AssertionError("strategy evaluation escaped the resource-limited child")

    monkeypatch.setattr(strategy_policy, "_interpret", forbidden_parent_interpret)
    source = "def run(panel):\n    return {'signal': panel['decision']}\n"
    program = strategy_policy.StrategyProgramPolicy().compile(source)

    launcher = TerminalLauncher()
    service = CustomStrategySandboxService(
        audit_path=tmp_path / "operational.db",
        governed_input=tmp_path / "governed-panel",
        launcher=launcher,
        governed_panel_resolver=lambda **_context: {"decision": "buy"},
    )
    result = service.submit(_submission(source))

    assert result["status"] == "completed"
    assert launcher.spawned[0]["program"] == program


@pytest.mark.parametrize(
    "source",
    [
        "def run(panel):\n    return {'signal': " + ("9" * 100) + "}\n",
        "def run(panel):\n    return {'signal': 'x' * 100_000}\n",
        (
            "def run(panel):\n    return {"
            + ", ".join(
                f"'value_{index}': 1 + 1 + 1 + 1" for index in range(64)
            )
            + "}\n"
        ),
    ],
)
def test_strategy_ir_rejects_integer_string_and_instruction_budget_overflow(source):
    from app.advanced.strategy_policy import (
        StrategyProgramPolicy,
        StrategyProgramViolation,
    )

    with pytest.raises(StrategyProgramViolation):
        StrategyProgramPolicy().compile(source)


def test_strategy_runtime_bounds_panel_result_and_translates_memory_error(monkeypatch):
    from app.advanced import strategy_policy

    program = strategy_policy.StrategyProgramPolicy().compile(
        "def run(panel):\n    return {'signal': panel['signal']}\n"
    )
    with pytest.raises(strategy_policy.StrategyProgramViolation):
        program.interpret({"signal": "x" * 5_000})
    with pytest.raises(strategy_policy.StrategyProgramViolation):
        program.interpret({"signal": 1 << 300})

    monkeypatch.setattr(
        strategy_policy,
        "_interpret",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(MemoryError()),
    )
    with pytest.raises(strategy_policy.StrategyProgramViolation):
        program.interpret({"signal": "hold"})


def test_resource_limited_child_rejects_amplifying_string_multiplication():
    from app.advanced.sandbox import LinuxIsolationLauncher
    from app.advanced.strategy_policy import StrategyProgramPolicy

    program = StrategyProgramPolicy().compile(
        "def run(panel):\n    return {'signal': panel['text'] * panel['count']}\n"
    )
    script = LinuxIsolationLauncher._interpreter_script(
        program=program,
        panel={"text": "x" * 4_096, "count": 1_000_000},
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        timeout=3,
    )

    assert completed.returncode == 126
    assert completed.stdout == b""
    assert completed.stderr == b""


@pytest.mark.parametrize(
    "source",
    [
        "def run(panel):\n    alias = abs\n    return {'signal': alias(-1)}\n",
        "def run(panel=globals()):\n    return {'signal': 'hold'}\n",
        "def run(panel):\n    return (lambda: {'signal': 'hold'})()\n",
        "def outer():\n    def run(panel):\n        return {'signal': 'hold'}\n    return run\n",
        "def run(panel):\n    box = [getattr]\n    return box[0](panel, '__class__')\n",
        "def run(panel):\n    left, right = (globals, locals)\n    return {'signal': 'hold'}\n",
        "import json\ndef run(panel):\n    return {'signal': json.dumps(panel)}\n",
        "def run(panel):\n    return getattr(panel, '__' + 'class__')\n",
        "def run(panel):\n    return __builtins__['__import__']('subprocess')\n",
        "def run(panel):\n    return globals()\n",
        "class Run:\n    pass\n",
        "def run(panel):\n    return panel.__class__.__mro__\n",
    ],
)
def test_r43_cr01_alias_capture_storage_matrix_rejected_before_spawn(tmp_path, source):
    from app.advanced.sandbox import CustomStrategySandboxService

    launcher = TerminalLauncher()
    spies = [Spy() for _ in range(5)]
    service = CustomStrategySandboxService(
        audit_path=tmp_path / "operational.db",
        governed_input=tmp_path / "governed-panel",
        launcher=launcher,
        feedback_recorder=spies[0],
        promotion_service=spies[1],
        broker=spies[2],
        provider=spies[3],
        strategy_engine=spies[4],
    )

    result = service.submit(_submission(source))

    assert result["status"] == "rejected"
    assert result["reason"] in {
        "strategy_program_forbidden",
        "module_reflection_forbidden",
        "undeclared_import",
    }
    assert launcher.probed == []
    assert launcher.spawned == []
    assert all(spy.calls == [] for spy in spies)


def test_r43_cr01_linux_limits_remain_defense_in_depth(monkeypatch):
    from app.advanced import sandbox
    from app.advanced.strategy_policy import StrategyProgramPolicy

    calls: list[tuple[object, tuple[int, int]]] = []
    fake_resource = SimpleNamespace(
        RLIMIT_CPU="cpu",
        RLIMIT_AS="address-space",
        RLIMIT_FSIZE="file-size",
        setrlimit=lambda limit, values: calls.append((limit, values)),
    )
    monkeypatch.setattr(sandbox, "resource", fake_resource)

    program = StrategyProgramPolicy().compile(SOURCE)
    sandbox.LinuxIsolationLauncher._limits(5, 128)()

    assert program.interpret({}) == {"signal": "hold"}
    assert calls == [
        ("cpu", (5, 5)),
        ("address-space", (128 * 1024 * 1024, 128 * 1024 * 1024)),
        ("file-size", (16 * 1024, 16 * 1024)),
    ]


@pytest.mark.parametrize(
    "missing_capability",
    [
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
    ],
)
def test_absent_or_inconclusive_launcher_capability_is_a_durable_pre_spawn_rejection(tmp_path, missing_capability):
    probe = Probe()
    setattr(probe, missing_capability, False)
    service, launcher, feedback, promotion, broker, provider, strategy_engine = _service(tmp_path, probe=probe)

    result = service.submit(_submission())

    _assert_safe_rejection(result, launcher, feedback, promotion, broker, provider, strategy_engine)
    assert result["reason"] == "isolation_unavailable"
    assert result["audit_reference"]
    assert service.list_audits()[-1]["reason"] == "isolation_unavailable"


def test_linux_probe_rejects_legacy_boolean_claims_without_observable_evidence(tmp_path, monkeypatch):
    """A report cannot become affirmative merely by claiming every capability is true."""
    from app.advanced.sandbox import _PROBE_FIELDS, LinuxIsolationLauncher

    launcher = LinuxIsolationLauncher()
    monkeypatch.setattr("app.advanced.sandbox.sys.platform", "linux")
    monkeypatch.setattr("app.advanced.sandbox.shutil.which", lambda _name: "/usr/bin/unshare")
    monkeypatch.setattr("app.advanced.sandbox.os.access", lambda _path, _mode: True)
    monkeypatch.setattr(
        "app.advanced.sandbox.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({field: True for field in _PROBE_FIELDS}),
        ),
    )

    proof = launcher.capability_probe(governed_input=tmp_path / "governed-panel", workdir=tmp_path)

    assert proof == {field: False for field in _PROBE_FIELDS}


def test_resource_unavailable_import_and_probe_fail_closed(tmp_path):
    """A missing POSIX resource module is import-safe and can never reach child creation."""
    backend_root = Path(__file__).resolve().parents[2]
    script = textwrap.dedent(
        """
        from __future__ import annotations

        import importlib.abc
        import json
        import sys
        import tempfile
        import time
        from pathlib import Path

        class BlockResource(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                del path, target
                if fullname == "resource":
                    raise ImportError("resource intentionally unavailable")
                return None

        sys.meta_path.insert(0, BlockResource())

        from app.advanced import sandbox

        def unexpected_platform_probe(_name):
            raise AssertionError("resource absence must deny before platform binaries are inspected")

        sandbox.shutil.which = unexpected_platform_probe
        launcher = sandbox.LinuxIsolationLauncher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof = launcher.capability_probe(
                governed_input=root / "governed-input",
                workdir=root,
            )
            try:
                launcher._limits(3, 128)
            except OSError:
                limits_denied = True
            else:
                limits_denied = False

            launcher._proof = {
                **{field: True for field in sandbox._PROBE_FIELDS},
                "proof_fingerprint": "test-proof",
                "probed_at": time.monotonic(),
            }
            popen_calls = []
            sandbox.subprocess.Popen = lambda *args, **kwargs: popen_calls.append((args, kwargs))
            try:
                launcher.spawn(
                    source_path=root / "strategy.py",
                    governed_input=root / "governed-input",
                    workdir=root,
                    timeout_seconds=3,
                    memory_limit_mb=128,
                )
            except OSError:
                spawn_denied = True
            else:
                spawn_denied = False

        print(json.dumps({
            "resource_unavailable": sandbox.resource is None,
            "proof": proof,
            "limits_denied": limits_denied,
            "spawn_denied": spawn_denied,
            "popen_calls": len(popen_calls),
        }, sort_keys=True))
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    from app.advanced.sandbox import _PROBE_FIELDS

    assert payload == {
        "resource_unavailable": True,
        "proof": {field: False for field in _PROBE_FIELDS},
        "limits_denied": True,
        "spawn_denied": True,
        "popen_calls": 0,
    }


def test_linux_limit_callback_sets_cpu_address_space_and_file_size(monkeypatch):
    """The portable guard must not weaken the exact Linux resource-limit contract."""
    from app.advanced import sandbox

    calls: list[tuple[object, tuple[int, int]]] = []
    fake_resource = SimpleNamespace(
        RLIMIT_CPU="cpu",
        RLIMIT_AS="address-space",
        RLIMIT_FSIZE="file-size",
        setrlimit=lambda limit, values: calls.append((limit, values)),
    )
    monkeypatch.setattr(sandbox, "resource", fake_resource)

    sandbox.LinuxIsolationLauncher._limits(7, 256)()

    assert calls == [
        ("cpu", (7, 7)),
        ("address-space", (256 * 1024 * 1024, 256 * 1024 * 1024)),
        ("file-size", (16 * 1024, 16 * 1024)),
    ]


def test_linux_timeout_reap_has_a_final_deadline_when_descendant_holds_pipes(tmp_path, monkeypatch):
    """A detached descendant retaining inherited pipes cannot block request cleanup forever."""
    from app.advanced import sandbox

    class Pipe:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class Process:
        pid = 4242
        returncode = None

        def __init__(self) -> None:
            self.stdout = Pipe()
            self.stderr = Pipe()
            self.communicate_timeouts: list[float] = []
            self.wait_timeouts: list[float] = []
            self.kill_calls = 0

        def communicate(self, *, timeout):
            self.communicate_timeouts.append(timeout)
            raise subprocess.TimeoutExpired("sandbox", timeout)

        def wait(self, *, timeout):
            self.wait_timeouts.append(timeout)
            return -9

        def kill(self) -> None:
            self.kill_calls += 1

    process = Process()
    killed_groups: list[tuple[int, object]] = []
    launcher = sandbox.LinuxIsolationLauncher()
    launcher._proof = {
        **{field: True for field in sandbox._PROBE_FIELDS},
        "proof_fingerprint": "test-proof",
        "probed_at": sandbox.time.monotonic(),
    }
    monkeypatch.setattr(
        sandbox,
        "resource",
        SimpleNamespace(
            RLIMIT_CPU=1,
            RLIMIT_AS=2,
            RLIMIT_FSIZE=3,
            setrlimit=lambda *_args: None,
        ),
    )
    monkeypatch.setattr(sandbox.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(sandbox.os, "killpg", lambda pid, sig: killed_groups.append((pid, sig)), raising=False)
    monkeypatch.setattr(sandbox.signal, "SIGKILL", 9, raising=False)
    from app.advanced.strategy_policy import StrategyProgramPolicy

    outcome = launcher.spawn(
        program=StrategyProgramPolicy().compile(SOURCE),
        panel={},
        governed_input=tmp_path / "governed-input",
        workdir=tmp_path,
        timeout_seconds=3,
        memory_limit_mb=128,
    )

    assert outcome["status"] == "failed"
    assert outcome["terminal_reason"] == "timeout_exceeded"
    assert process.communicate_timeouts == [3, launcher._REAP_TIMEOUT_SECONDS]
    assert process.wait_timeouts == [launcher._REAP_TIMEOUT_SECONDS]
    assert process.stdout.closed is process.stderr.closed is True
    assert killed_groups == [(process.pid, 9)]



class _BootstrapExecveReached(BaseException):
    """Sentinel proving the bootstrap reached execve without running a child."""


def _bootstrap_state(monkeypatch, *, failed_mount: int | None = None, mountinfo: str | None = None) -> dict[str, object]:
    from app.advanced import sandbox

    root = "/sandbox/root"
    mount_calls: list[tuple[str, ...]] = []
    execve_calls: list[tuple[object, ...]] = []
    chroot_calls: list[str] = []

    def fake_mount(command, **_kwargs):
        mount_calls.append(tuple(command))
        return SimpleNamespace(returncode=int(failed_mount == len(mount_calls)))

    def fake_execve(*args):
        execve_calls.append(args)
        raise _BootstrapExecveReached()

    if mountinfo is None:
        mountinfo = "\n".join(
            (
                f"42 1 0:42 / {root} ro - tmpfs tmpfs rw",
                f"43 42 0:43 /governed {root}/input ro - ext4 /dev/loop0 rw",
                f"44 42 0:44 /source.py {root}/strategy.py ro - ext4 /dev/loop0 rw",
                f"45 42 0:45 / {root}/work rw - tmpfs tmpfs rw",
            )
        )
    monkeypatch.setattr("app.advanced.sandbox.subprocess.run", fake_mount)
    monkeypatch.setattr("app.advanced.sandbox.os.makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.advanced.sandbox.os.open", lambda *_args, **_kwargs: 9)
    monkeypatch.setattr("app.advanced.sandbox.os.close", lambda _descriptor: None)
    monkeypatch.setattr("app.advanced.sandbox.os.path.exists", lambda _path: True)
    monkeypatch.setattr("app.advanced.sandbox.os.path.ismount", lambda path: path == root)
    monkeypatch.setattr(
        sandbox.os, "chroot", lambda path: chroot_calls.append(path), raising=False
    )
    monkeypatch.setattr("app.advanced.sandbox.os.chdir", lambda _path: None)
    monkeypatch.setattr(sandbox.os, "execve", fake_execve, raising=False)

    return {
        "script": sandbox.LinuxIsolationLauncher._bootstrap_script(),
        "namespace": {
            "__name__": "__main__",
            "open": lambda path, **_kwargs: io.StringIO(mountinfo) if path == "/proc/self/mountinfo" else None,
        },
        "mount_calls": mount_calls,
        "execve_calls": execve_calls,
        "chroot_calls": chroot_calls,
    }


@pytest.mark.parametrize("failed_mount", range(1, 15))
def test_linux_bootstrap_rejects_every_failed_mount_before_execve(monkeypatch, failed_mount):
    state = _bootstrap_state(monkeypatch, failed_mount=failed_mount)
    monkeypatch.setattr("app.advanced.sandbox.sys.argv", ["bootstrap", "/sandbox/root", "/source.py", "/governed", "/work"])

    with pytest.raises(SystemExit) as failure:
        exec(state["script"], state["namespace"])

    assert failure.value.code == 126
    assert len(state["mount_calls"]) == failed_mount
    assert state["execve_calls"] == []
    assert state["chroot_calls"] == []


def test_linux_bootstrap_executes_only_after_private_read_only_topology_is_verified(monkeypatch):
    state = _bootstrap_state(monkeypatch)
    monkeypatch.setattr("app.advanced.sandbox.sys.argv", ["bootstrap", "/sandbox/root", "/source.py", "/governed", "/work"])

    with pytest.raises(_BootstrapExecveReached):
        exec(state["script"], state["namespace"])

    assert state["mount_calls"] == [
        ("/bin/mount", "--make-rprivate", "/"),
        ("/bin/mount", "-t", "tmpfs", "-o", "size=1m,nosuid,nodev,noexec", "tmpfs", "/sandbox/root"),
        ("/bin/mount", "--bind", "/governed", "/sandbox/root/input"),
        ("/bin/mount", "-o", "remount,bind,ro", "/sandbox/root/input"),
        ("/bin/mount", "-t", "tmpfs", "-o", "size=512k,nosuid,nodev,noexec", "tmpfs", "/sandbox/root/work"),
        ("/bin/mount", "--bind", "/source.py", "/sandbox/root/strategy.py"),
        ("/bin/mount", "-o", "remount,bind,ro", "/sandbox/root/strategy.py"),
        ("/bin/mount", "--bind", "/usr", "/sandbox/root/usr"),
        ("/bin/mount", "-o", "remount,bind,ro", "/sandbox/root/usr"),
        ("/bin/mount", "--bind", "/lib", "/sandbox/root/lib"),
        ("/bin/mount", "-o", "remount,bind,ro", "/sandbox/root/lib"),
        ("/bin/mount", "--bind", "/lib64", "/sandbox/root/lib64"),
        ("/bin/mount", "-o", "remount,bind,ro", "/sandbox/root/lib64"),
        ("/bin/mount", "-o", "remount,ro", "/sandbox/root"),
    ]
    assert state["chroot_calls"] == ["/sandbox/root"]
    assert state["execve_calls"] == [
        (
            "/usr/bin/python3",
            ["/usr/bin/python3", "/strategy.py"],
            {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        )
    ]


def test_linux_bootstrap_rejects_shared_or_non_read_only_root_topology_before_execve(monkeypatch):
    root = "/sandbox/root"
    shared_root_mountinfo = "\n".join(
        (
            f"42 1 0:42 / {root} ro shared:1 - tmpfs tmpfs rw",
            f"43 42 0:43 /governed {root}/input ro - ext4 /dev/loop0 rw",
            f"44 42 0:44 /source.py {root}/strategy.py ro - ext4 /dev/loop0 rw",
            f"45 42 0:45 / {root}/work rw - tmpfs tmpfs rw",
        )
    )
    state = _bootstrap_state(monkeypatch, mountinfo=shared_root_mountinfo)
    monkeypatch.setattr("app.advanced.sandbox.sys.argv", ["bootstrap", root, "/source.py", "/governed", "/work"])

    with pytest.raises(SystemExit) as failure:
        exec(state["script"], state["namespace"])

    assert failure.value.code == 126
    assert state["execve_calls"] == []
    assert state["chroot_calls"] == []

def test_sandbox_validation_persists_immutable_parent_asset_lineage(tmp_path):
    from app.advanced.repository import AdvancedRepository

    repository = AdvancedRepository(tmp_path / "operational.db")
    repository.migrate()
    audit = repository.append_security_audit(decision="recorded", reason="sandbox_completed")
    validation = repository.append_sandbox_validation(
        parent_asset_id="registered-research-asset-v1",
        contract_fingerprint="contract-fingerprint",
        source_sha256="a" * 64,
        status="validated",
        reason="completed",
        audit_reference=audit["reference"],
    )
    run = repository.append_sandbox_run(
        validation_id=validation["id"],
        runner_manifest={"status": "completed", "resources": {}},
        terminal_reason=None,
        artifact_reference=None,
    )

    assert validation["parent_asset_id"] == "registered-research-asset-v1"
    assert repository.get_sandbox_run(run["id"])["parent_asset_id"] == "registered-research-asset-v1"
    with repository._connection() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE advanced_sandbox_validations SET parent_asset_id = ? WHERE id = ?",
            ("other-asset", validation["id"]),
        )


def test_existing_operational_database_upgrades_sandbox_lineage_once_without_losing_rows(tmp_path):
    from app.operational.migrations import MIGRATIONS, migrate_operational_db

    database = tmp_path / "operational.db"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    for migration in MIGRATIONS[:-1]:
        connection.executescript(migration)
    connection.execute(f"PRAGMA user_version = {len(MIGRATIONS) - 1}")
    connection.execute(
        "INSERT INTO advanced_security_audit (id, reference, decision, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        ("audit-id", "audit-reference", "recorded", "sandbox_completed", "2026-01-01T00:00:00+00:00"),
    )
    connection.execute(
        """INSERT INTO advanced_sandbox_validations
           (id, contract_fingerprint, source_sha256, status, reason, audit_reference, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("validation-id", "contract", "a" * 64, "validated", "completed", "audit-reference", "2026-01-01T00:00:00+00:00"),
    )
    connection.commit()

    migrate_operational_db(connection)
    migrate_operational_db(connection)

    row = connection.execute(
        "SELECT source_sha256, parent_asset_id FROM advanced_sandbox_validations WHERE id = ?", ("validation-id",)
    ).fetchone()
    assert row == ("a" * 64, "")
    assert connection.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    connection.close()


@pytest.mark.parametrize(
    ("launcher_outcome", "expected_reason"),
    [
        ({"kind": "timeout", "output": "x" * 100_000}, "timeout_exceeded"),
        ({"kind": "memory", "output": "x" * 100_000}, "memory_limit_exceeded"),
        ({"kind": "output", "output": "x" * 100_000}, "output_limit_exceeded"),
    ],
)
def test_runtime_constraints_terminate_the_process_group_cleanup_handoff_and_redact_output(tmp_path, launcher_outcome, expected_reason):
    service, launcher, feedback, promotion, broker, provider, strategy_engine = _service(tmp_path)
    launcher.runtime_outcome = launcher_outcome

    result = service.submit(_submission())

    assert result["status"] == "rejected"
    assert result["reason"] == expected_reason
    assert result["diagnostics"]["output_truncated"] is True
    assert len(result["diagnostics"].get("summary", "")) <= 512
    assert service.temporary_handoffs() == []
    assert feedback.calls == []
    assert promotion.calls == []
    assert broker.calls == []
    assert provider.calls == []
    assert strategy_engine.calls == []


def test_admission_persists_only_source_hash_and_never_projects_source_or_host_execution_details(tmp_path):
    service, launcher, feedback, promotion, broker, provider, strategy_engine = _service(tmp_path)

    result = service.submit(_submission("def run(panel):\n    return 'sensitive custom code'\n"))

    _assert_safe_rejection(result, launcher, feedback, promotion, broker, provider, strategy_engine)
    audit = service.list_audits()[-1]
    projection = service.public_validation(result["audit_reference"])
    assert audit["source_sha256"] == sha256(b"def run(panel):\n    return 'sensitive custom code'\n").hexdigest()
    assert "source" not in audit
    assert "sensitive custom code" not in str(audit)
    assert "sensitive custom code" not in str(projection)
    assert {"source", "code", "token", "path", "traceback"}.isdisjoint(projection)


def test_sandbox_api_uses_strict_submission_and_returns_only_safe_validation(tmp_path):
    from app.advanced import api as advanced_api

    service, _launcher, _feedback, _promotion, _broker, _provider, _strategy_engine = _service(tmp_path)
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.advanced_sandbox_service = service
    app.state.resolve_advanced_research_asset = lambda _request, asset_id: asset_id == "registered-research-asset-v1"

    @app.middleware("http")
    async def authenticated(request: Request, call_next):
        request.state.reviewer_principal = "server-researcher"
        return await call_next(request)

    client = TestClient(app)
    invalid = client.post("/api/advanced/sandbox/submissions", json={**_submission(), "principal": "browser"})
    response = client.post("/api/advanced/sandbox/submissions", json=_submission())

    assert invalid.status_code == 422
    assert response.status_code == 200
    validation = response.json()["validation"]
    assert validation["status"] == "rejected"
    assert validation["source_sha256"] == sha256(SOURCE.encode()).hexdigest()
    assert {"source", "code", "path", "diagnostic", "token"}.isdisjoint(response.text.lower())


def test_authorized_sandbox_run_api_lists_safe_terminal_records_without_cross_asset_disclosure(tmp_path):
    from app.advanced import api as advanced_api
    from app.advanced.sandbox import CustomStrategySandboxService

    launcher = TerminalLauncher()
    service = CustomStrategySandboxService(
        audit_path=tmp_path / "operational.db",
        governed_input=tmp_path / "governed-panel",
        launcher=launcher,
    )
    completed = service.submit(_submission())
    audit = service._repository.append_security_audit(decision="recorded", reason="sandbox_completed")
    other_validation = service._repository.append_sandbox_validation(
        parent_asset_id="other-research-asset",
        contract_fingerprint="other-contract",
        source_sha256="b" * 64,
        status="constraint_failed",
        reason="timeout_exceeded",
        audit_reference=audit["reference"],
    )
    other_run = service._repository.append_sandbox_run(
        validation_id=other_validation["id"],
        runner_manifest={"status": "failed", "resources": {"memory_limit_mb": 128}, "stderr": "secret"},
        terminal_reason="timeout_exceeded",
        artifact_reference="internal-artifact",
    )
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.advanced_sandbox_service = service
    app.state.resolve_advanced_research_asset = lambda _request, asset_id: asset_id == "registered-research-asset-v1"

    @app.middleware("http")
    async def authenticated(request: Request, call_next):
        request.state.reviewer_principal = "server-researcher"
        return await call_next(request)

    client = TestClient(app)
    listed = client.get("/api/advanced/sandbox/runs")
    detail = client.get(f"/api/advanced/sandbox/runs/{completed['run_id']}")
    forbidden = client.get(f"/api/advanced/sandbox/runs/{other_run['id']}")
    validations = client.get("/api/advanced/sandbox/validations")

    assert listed.status_code == detail.status_code == 200
    assert forbidden.status_code == 404
    assert listed.json() == {"runs": [detail.json()["run"]]}
    assert detail.json()["run"] == {
        "run_id": completed["run_id"],
        "status": "completed",
        "terminal_reason": None,
        "proof_fingerprint": "safe-proof",
        "resources": {"wall_clock_seconds": 5, "memory_limit_mb": 128},
        "audit_reference": detail.json()["run"]["audit_reference"],
        "created_at": detail.json()["run"]["created_at"],
    }
    assert {"source", "code", "path", "environment", "stdout", "stderr", "traceback", "token"}.isdisjoint(detail.text.lower())
    assert validations.status_code == 200
    assert validations.json() == {
        "validations": [
            {
                "status": "validated",
                "reason": "completed",
                "audit_reference": completed["audit_reference"],
                "source_sha256": sha256(SOURCE.encode()).hexdigest(),
            }
        ]
    }
    assert other_validation["audit_reference"] not in validations.text
    assert other_validation["source_sha256"] not in validations.text
    assert other_validation["reason"] not in validations.text
    assert other_validation["status"] not in validations.text
