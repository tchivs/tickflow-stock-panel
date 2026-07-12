"""RED contracts for fail-closed custom-strategy admission and isolation."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

import pytest

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
    network_namespace: bool = True
    network_absent: bool = True
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
        "network_namespace",
        "network_absent",
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
