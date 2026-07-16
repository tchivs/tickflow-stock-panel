"""Phase 05 real-host RED contracts for independently optional research modules.

The tests intentionally target the production ``app.optional_modules`` seam that Plan
05-14 owns.  Until that seam exists every node fails at the same declared import;
``verify_phase5_host_red.py`` rejects every other kind of RED result.
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

MODULE_NAMES = ("shadow", "thesis", "forecast")
MODULE_COMBINATIONS = (
    pytest.param(frozenset(), id="none"),
    pytest.param(frozenset({"shadow"}), id="shadow-only"),
    pytest.param(frozenset({"thesis"}), id="thesis-only"),
    pytest.param(frozenset({"forecast"}), id="forecast-only"),
    pytest.param(frozenset({"shadow", "thesis"}), id="shadow-thesis"),
    pytest.param(frozenset({"shadow", "forecast"}), id="shadow-forecast"),
    pytest.param(frozenset({"thesis", "forecast"}), id="thesis-forecast"),
    pytest.param(frozenset(MODULE_NAMES), id="all"),
)

CAPABILITY_PATH = "/api/optional-modules"
BUSINESS_PATHS = {
    "shadow": "/api/shadow/batches",
    "thesis": "/api/theses/instruments/600000.SH/versions",
    "forecast": "/api/forecast/instruments/600000.SH/records",
}
FORBIDDEN_PUBLIC_FIELDS = {
    "absolute_path",
    "account_secret",
    "broker_token",
    "checkpoint_local_dir",
    "environment",
    "raw_exception",
    "stacktrace",
    "worker_command",
}
FORGED_AUTHORITY_FIELDS = {
    "principal": "browser-principal",
    "reviewer_principal": "browser-reviewer",
    "fingerprint": "browser-fingerprint",
    "digest": "browser-digest",
    "verdict": "passed",
    "status": "completed",
}


@dataclass
class CallSpy:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


@dataclass
class LiveActionSpies:
    strategy_install: CallSpy = field(default_factory=CallSpy)
    monitor: CallSpy = field(default_factory=CallSpy)
    decision_plan: CallSpy = field(default_factory=CallSpy)
    position: CallSpy = field(default_factory=CallSpy)
    manual_ledger: CallSpy = field(default_factory=CallSpy)
    broker: CallSpy = field(default_factory=CallSpy)
    provider_network: CallSpy = field(default_factory=CallSpy)
    market_action: CallSpy = field(default_factory=CallSpy)

    def as_mapping(self) -> dict[str, CallSpy]:
        return {
            "strategy_install": self.strategy_install,
            "monitor": self.monitor,
            "decision_plan": self.decision_plan,
            "position": self.position,
            "manual_ledger": self.manual_ledger,
            "broker": self.broker,
            "provider_network": self.provider_network,
            "market_action": self.market_action,
        }

    def assert_zero_calls(self) -> None:
        assert {name: len(spy.calls) for name, spy in self.as_mapping().items()} == {
            name: 0 for name in self.as_mapping()
        }


def _phase5_host_contract():
    """Load only the declared future production seam, never a fallback app."""
    from app.optional_modules import (  # type: ignore[import-not-found]
        OptionalModuleProbe,
        build_optional_module_host,
    )

    return OptionalModuleProbe, build_optional_module_host


def _write_phase1_fixture(fixtures_dir: Path) -> None:
    """Use a minimal governed fixture accepted by the existing real lifespan."""
    from tests.test_analysis_host_integration import _write_phase1_fixture as write_fixture

    write_fixture(fixtures_dir)


def _assert_safe_projection(value: object) -> None:
    rendered = json.dumps(value, ensure_ascii=False).lower()
    assert not any(field.lower() in rendered for field in FORBIDDEN_PUBLIC_FIELDS)
    assert "/tmp/" not in rendered
    assert "traceback" not in rendered


def _assert_typed_status(payload: dict[str, Any], module: str, available: bool) -> None:
    status = payload["modules"][module]
    assert set(status) == {"available", "code", "reason", "install_hint"}
    assert status["available"] is available
    assert isinstance(status["code"], str) and status["code"]
    assert isinstance(status["reason"], str) and status["reason"]
    assert isinstance(status["install_hint"], str) and status["install_hint"]
    _assert_safe_projection(status)


def _optional_probe(module: str, enabled: frozenset[str], *, fail: str | None = None):
    OptionalModuleProbe, _ = _phase5_host_contract()
    if module == fail:
        raise RuntimeError(f"{module} fixture probe failed with local detail that must be sanitized")
    if module in enabled:
        return OptionalModuleProbe.available(code=f"{module}_available")
    return OptionalModuleProbe.unavailable(
        code=f"{module}_dependency_missing",
        reason=f"{module} optional dependency is not installed",
        install_hint=f"enable the {module} optional deployment capability",
    )


@contextmanager
def _real_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    enabled: frozenset[str],
    *,
    fail_probe: str | None = None,
    fail_init: str | None = None,
    fail_recovery: str | None = None,
    fail_scanner: str | None = None,
    spies: LiveActionSpies | None = None,
) -> Iterator[tuple[Any, TestClient]]:
    """Start the one production app/lifespan with deterministic probe overrides.

    The override is limited to deployment probes/failure injection.  The returned
    services, routers, repositories, recovery and scanners are the production ones.
    """
    from app import optional_modules
    from app.config import settings
    from app.services import auth as auth_service

    _, build_optional_module_host = _phase5_host_contract()
    fixture_dir = tmp_path / "phase1-fixtures"
    data_dir = tmp_path / "governed-data"
    _write_phase1_fixture(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    probe_overrides = {
        module: (lambda name=module: _optional_probe(name, enabled, fail=fail_probe))
        for module in MODULE_NAMES
    }
    monkeypatch.setattr(optional_modules, "OPTIONAL_MODULE_PROBES", probe_overrides)
    monkeypatch.setattr(optional_modules, "OPTIONAL_MODULE_TEST_FAILURES", {
        "init": fail_init,
        "recovery": fail_recovery,
        "scanner": fail_scanner,
    })
    monkeypatch.setattr(optional_modules, "OPTIONAL_MODULE_ACTION_COLLABORATORS", (spies or LiveActionSpies()).as_mapping())

    from app.main import app

    # The main lifespan must call this exact production builder once.  Keeping a
    # reference here also makes a renamed/missing factory a declared RED failure.
    assert callable(build_optional_module_host)
    with TestClient(app) as client:
        yield app, client


def _authenticate(client: TestClient) -> None:
    unauthenticated = client.get(CAPABILITY_PATH)
    assert unauthenticated.status_code == 401
    login = client.post("/api/auth/login", json={"password": "host-test-password"})
    assert login.status_code == 200
    assert "tf_session" in login.headers.get("set-cookie", "")


def _assert_completed_v1_loop(app: Any, client: TestClient) -> None:
    """Smoke the completed data/portfolio/monitor/decision/root-SSE host surfaces."""
    data_status = client.get("/api/data/status")
    portfolio = client.get("/api/portfolio/accounts")
    monitor = client.get("/api/monitor-rules")
    missing_decision = client.get("/api/decision/runs/phase5-missing-v1-record")
    intraday = client.get("/api/intraday/status")
    assert data_status.status_code == portfolio.status_code == monitor.status_code == intraday.status_code == 200
    assert missing_decision.status_code == 404
    assert isinstance(portfolio.json()["accounts"], list)
    assert isinstance(monitor.json(), list)
    assert any(route.path == "/api/intraday/stream" for route in app.routes)
    subscriber = app.state.quote_service.subscribe(
        analysis_scope=app.state.resolve_analysis_subject_scope(None),
        advanced_scope=app.state.resolve_advanced_subject_scope(None),
    )
    try:
        snapshot = subscriber.pop()
        assert set(snapshot) >= {"alerts", "analysis_progress", "advanced_progress"}
    finally:
        app.state.quote_service.unsubscribe(subscriber)


@pytest.mark.parametrize("enabled", MODULE_COMBINATIONS)
def test_real_lifespan_preserves_v1_for_module_combination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: frozenset[str]
) -> None:
    with _real_host(tmp_path, monkeypatch, enabled) as (app, client):
        _authenticate(client)
        capabilities = client.get(CAPABILITY_PATH)
        assert capabilities.status_code == 200
        payload = capabilities.json()
        assert set(payload["modules"]) == set(MODULE_NAMES)
        for module in MODULE_NAMES:
            _assert_typed_status(payload, module, module in enabled)
            response = client.get(BUSINESS_PATHS[module])
            if module in enabled:
                assert response.status_code == 200
            else:
                assert response.status_code == 503
                detail = response.json()["detail"]
                assert set(detail) == {"available", "code", "reason", "install_hint"}
                assert detail["available"] is False
                _assert_safe_projection(detail)
        _assert_completed_v1_loop(app, client)
        assert app.state.operational.database_path == app.state.optional_module_host.database_path
        assert app.state.datastore.data_dir == app.state.optional_module_host.data_root
        assert app.state.optional_module_host.runtime_identity == id(app)
        assert not any(name in sys.modules for name in ("torch", "sklearn", "kronos"))


def test_optional_capability_failures_are_typed_local_and_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure_cases = (
        {"fail_probe": "shadow"},
        {"fail_init": "thesis"},
        {"fail_recovery": "forecast"},
        {"fail_scanner": "forecast"},
    )
    for index, failure in enumerate(failure_cases):
        case_root = tmp_path / str(index)
        case_root.mkdir()
        with _real_host(case_root, monkeypatch, frozenset(MODULE_NAMES), **failure) as (app, client):
            _authenticate(client)
            payload = client.get(CAPABILITY_PATH).json()
            failed_module = next(value for value in failure.values() if value)
            for module in MODULE_NAMES:
                _assert_typed_status(payload, module, module != failed_module)
                response = client.get(BUSINESS_PATHS[module])
                assert response.status_code == (503 if module == failed_module else 200)
            _assert_completed_v1_loop(app, client)


def test_optional_routes_reject_browser_authority_and_foreign_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _real_host(tmp_path, monkeypatch, frozenset(MODULE_NAMES)) as (_app, client):
        _authenticate(client)
        forged_requests = (
            ("/api/shadow/evidence-sets/server-evidence/candidates/server-candidate/retain", {}),
            ("/api/theses/pending/server-pending/confirm", {"rationale": "这是足够长的人工确认理由。"}),
            ("/api/forecast/instruments/600000.SH/jobs", {"horizon": 20, "catalog_id": "approved-mini", "idempotency_key": "server-selector"}),
        )
        for path, bounded_body in forged_requests:
            forged = client.post(path, json={**bounded_body, **FORGED_AUTHORITY_FIELDS})
            assert forged.status_code == 422
            assert all(field not in json.dumps(forged.json()) for field in FORBIDDEN_PUBLIC_FIELDS)

        foreign_paths = (
            "/api/shadow/batches/foreign-opaque-id",
            "/api/theses/versions/foreign-opaque-id",
            "/api/forecast/records/foreign-opaque-id",
        )
        for path in foreign_paths:
            response = client.get(path)
            assert response.status_code == 404
            _assert_safe_projection(response.json())

        malformed_upload = client.post(
            "/api/shadow/imports/preview",
            files={"file": ("unsafe.zip", b"PK\x03\x04", "application/zip")},
            data={"source_timezone": "../../browser"},
        )
        assert malformed_upload.status_code in {400, 413, 415, 422}
        _assert_safe_projection(malformed_upload.json())


def test_optional_success_failure_and_terminal_paths_call_no_live_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spies = LiveActionSpies()
    with _real_host(tmp_path, monkeypatch, frozenset(MODULE_NAMES), spies=spies) as (_app, client):
        _authenticate(client)
        operations = (
            ("/api/shadow/evidence-sets/server-evidence/candidates/server-candidate/retain", {}),
            ("/api/theses/pending/server-pending/confirm", {"rationale": "人工确认理由至少十个字符。"}),
            ("/api/theses/pending/server-pending/reject", {"rationale": "人工驳回理由至少十个字符。"}),
            ("/api/forecast/instruments/600000.SH/jobs", {"horizon": 20, "catalog_id": "approved-mini", "idempotency_key": "phase5-host"}),
            ("/api/forecast/records/server-record/calibration", {}),
        )
        for path, body in operations:
            response = client.post(path, json=body)
            assert response.status_code in {200, 201, 404, 409}
            _assert_safe_projection(response.json())
            spies.assert_zero_calls()

        for terminal in ("validation_failed", "timeout", "resource_terminated", "checkpoint_mismatch", "artifact_failed"):
            response = client.post(
                "/api/forecast/testing/terminal-jobs",
                json={"instrument": "600000.SH", "terminal": terminal},
            )
            assert response.status_code in {200, 201}
            job = response.json()["job"]
            assert job["status"] == terminal
            assert "record_id" not in job
            _assert_safe_projection(job)
            spies.assert_zero_calls()


def test_optional_host_uses_one_runtime_database_lake_and_scheduler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _real_host(tmp_path, monkeypatch, frozenset(MODULE_NAMES)) as (app, client):
        _authenticate(client)
        host = app.state.optional_module_host
        assert host.database_path == app.state.operational.database_path
        assert host.data_root == app.state.datastore.data_dir
        assert host.scheduler is app.state.scheduler
        assert host.quote_service is app.state.quote_service
        assert host.external_databases == ()
        assert host.external_queues == ()
        assert host.external_services == ()
        assert host.child_containers == ()
        assert len({service.database_path for service in host.initialized_services}) == 1
        assert len({service.data_root for service in host.initialized_services}) == 1
        assert len([route for route in app.routes if route.path == CAPABILITY_PATH]) == 1
        _assert_completed_v1_loop(app, client)
