"""RED contracts for fail-closed custom-strategy admission and isolation."""
from __future__ import annotations

import json
import io
import sqlite3
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
        self.spawned: list[dict[str, object]] = []

    def capability_probe(self, *, governed_input: Path, workdir: Path) -> Probe:
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
        "attribute_chain_forbidden",
        "undeclared_import",
        "file_access_forbidden",
        "network_access_forbidden",
        "child_process_forbidden",
        "isolation_unavailable",
        "timeout_exceeded",
        "memory_limit_exceeded",
        "output_limit_exceeded",
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
        (_submission("import os\nos.system('id')\n"), "attribute_chain_forbidden"),
        (_submission("import json\ndef run(panel): return json.dumps({})\n"), "undeclared_import"),
        (_submission("def run(panel):\n    return open('/etc/passwd').read()\n"), "file_access_forbidden"),
        (_submission("import socket\ndef run(panel): return socket.create_connection(('example.test', 80))\n", declared_imports=["socket"]), "network_access_forbidden"),
        (_submission("import subprocess\ndef run(panel): return subprocess.run(['id'])\n", declared_imports=["subprocess"]), "child_process_forbidden"),
    ],
)
def test_hostile_submission_is_rejected_before_any_host_execution(tmp_path, payload, expected_reason):
    service, launcher, feedback, promotion, broker, provider, strategy_engine = _service(tmp_path)

    result = service.submit(payload)

    _assert_safe_rejection(result, launcher, feedback, promotion, broker, provider, strategy_engine)
    assert result["reason"] == expected_reason


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



class _BootstrapExecveReached(BaseException):
    """Sentinel proving the bootstrap reached execve without running a child."""


def _bootstrap_state(monkeypatch, *, failed_mount: int | None = None, mountinfo: str | None = None) -> dict[str, object]:
    from app.advanced.sandbox import LinuxIsolationLauncher

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
    monkeypatch.setattr("app.advanced.sandbox.os.chroot", lambda path: chroot_calls.append(path))
    monkeypatch.setattr("app.advanced.sandbox.os.chdir", lambda _path: None)
    monkeypatch.setattr("app.advanced.sandbox.os.execve", fake_execve)

    return {
        "script": LinuxIsolationLauncher._bootstrap_script(),
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
