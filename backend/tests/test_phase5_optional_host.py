"""Final real-host acceptance for independently optional Phase 05 research modules."""
from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
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



@dataclass(frozen=True, slots=True)
class ApprovedForecastCheckpointFixture:
    catalog_id: str = "kronos-mini"
    source_revision: str = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
    source_digest_sha256: str = "1" * 64
    model_revision: str = "f4e68697d9d5aed55cef5c96aabc3376bcad9f81"
    model_weight_sha256: str = "2" * 64
    tokenizer_revision: str = "26966d0035065a0cae0ebad7af8ece35bc1fb51c"
    tokenizer_weight_sha256: str = "3" * 64
    max_context: int = 512


class ApprovedForecastCatalogFixture:
    def __init__(self) -> None:
        self.entry = ApprovedForecastCheckpointFixture()

    def require_local(self, catalog_id: str, *, device: str) -> ApprovedForecastCheckpointFixture:
        if catalog_id != self.entry.catalog_id or device != "cpu":
            raise ValueError("approved local Forecast checkpoint is unavailable")
        return self.entry

    def revalidate_before_spawn(
        self, entry: ApprovedForecastCheckpointFixture
    ) -> ApprovedForecastCheckpointFixture:
        if entry != self.entry:
            raise ValueError("checkpoint catalog identity changed")
        return entry


class HostForecastInputRepository:
    frequency = "daily"

    def __init__(self) -> None:
        fixture = Path(__file__).parent / "forecast" / "fixtures" / "governed_daily.parquet"
        self.frame = pl.read_parquet(fixture).filter(pl.col("case_id") == "valid").drop("case_id")

    def assert_ready(self) -> None:
        assert self.frame.height >= 64

    def resolve_instrument(self, *, principal: str, instrument_id: str) -> dict[str, object]:
        if not principal or instrument_id != "600000.SH":
            raise LookupError("instrument not found")
        return {
            "instrument_id": instrument_id,
            "symbol": instrument_id,
            "market": "CN-A",
            "asset_type": "stock",
        }

    def get_daily(self, *, symbol: str, as_of: str) -> pl.DataFrame:
        if symbol != "600000.SH":
            raise LookupError("instrument not found")
        return self.frame.filter(
            pl.col("trade_date") <= pl.lit(as_of).str.to_date()
        ).with_columns(
            pl.lit(symbol).alias("instrument_id"),
            pl.lit(symbol).alias("symbol"),
        )


class HostForecastActuals:
    def assert_ready(self) -> None:
        return None

    def load_actual(self, **_identity: object) -> None:
        return None


@dataclass(frozen=True, slots=True)
class HostForecastWorker:
    root: Path

    def __call__(
        self,
        *,
        job: dict[str, object],
        context: dict[str, object],
        limits: dict[str, int],
    ) -> dict[str, object]:
        del limits
        future = [str(value) for value in context["future_session_ids"]]
        features = [str(value) for value in context["feature_schema"]]
        rows = [
            {
                "sample_index": sample,
                "session_id": session,
                "feature": feature,
                "value": float(sample + horizon_index + feature_index),
            }
            for sample in range(32)
            for horizon_index, session in enumerate(future)
            for feature_index, feature in enumerate(features)
        ]
        relative = f"{job['id']}/paths.parquet"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=False)
        pl.DataFrame(rows).write_parquet(target)
        payload = target.read_bytes()
        from hashlib import sha256

        return {
            "output_descriptor": {
                "artifact_id": f"forecast-{job['id']}",
                "relative_path": relative,
                "schema_version": "forecast-paths-v1",
                "byte_size": len(payload),
                "checksum_sha256": sha256(payload).hexdigest(),
                "sample_count": 32,
                "horizon": len(future),
                "feature_count": len(features),
            },
            "validation_warnings": [],
        }


def _forecast_components(data_dir: Path) -> dict[str, object]:
    from app.forecast.calendar import GovernedTradingCalendar
    from app.forecast.runner import ForecastRunnerLimits
    from tests.forecast.test_input import _calendar_frame

    output_root = data_dir / "forecast-outputs"
    return {
        "catalog": ApprovedForecastCatalogFixture(),
        "calendar": GovernedTradingCalendar(_calendar_frame()),
        "input_repository": HostForecastInputRepository(),
        "as_of_session": lambda _instrument: "CNA-20250430",
        "actuals": HostForecastActuals(),
        "worker": HostForecastWorker(output_root),
        "output_root": output_root,
        "limits": ForecastRunnerLimits(
            wall_clock_seconds=10,
            cpu_seconds=5,
            address_space_bytes=8 * 1024 * 1024 * 1024,
            thread_count=2,
            output_bytes=16 * 1024,
            queue_items=1,
        ),
    }

def _phase5_host_contract():
    """Load the production optional-module host contract."""
    from app.optional_modules import OptionalModuleProbe, build_optional_module_host

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
    optional_module_probe, _ = _phase5_host_contract()
    if module == fail:
        raise RuntimeError(f"{module} fixture probe failed with local detail that must be sanitized")
    if module in enabled:
        return optional_module_probe.available(code=f"{module}_available")
    return optional_module_probe.unavailable(
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
    production_scheduler: bool = False,
) -> Iterator[tuple[Any, TestClient]]:
    """Start the one production app/lifespan with deterministic probe overrides.

    The override is limited to deployment probes/failure injection.  The returned
    services, routers, repositories, recovery and scanners are the production ones.
    """
    production_scheduler = production_scheduler or bool({"thesis", "forecast"} & enabled)
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
    if production_scheduler:
        from app.jobs import daily_pipeline

        daily_pipeline.run_phase1_fixture_sync(data_dir)
        monkeypatch.setenv("PHASE1_FIXTURE_MODE", "0")
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
    monkeypatch.setattr(
        optional_modules,
        "OPTIONAL_MODULE_FORECAST_COMPONENTS",
        _forecast_components(data_dir) if "forecast" in enabled else {},
    )
    static_dir = tmp_path / "frontend-dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>phase-5-host</html>", encoding="utf-8")
    monkeypatch.setattr(settings, "static_dir", static_dir)

    from app.main import app

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
    assert isinstance(monitor.json()["rules"], list)
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
    heavy_modules_before = {name for name in ("torch", "sklearn", "kronos") if name in sys.modules}
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
                if module == "forecast":
                    latest = app.state.repo.latest_daily_date()
                    expected_session = f"CNA-{latest:%Y%m%d}" if latest is not None else None
                    assert response.json()["latest_governed_session_id"] == expected_session
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
        assert {name for name in ("torch", "sklearn", "kronos") if name in sys.modules} == heavy_modules_before


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
            ("/api/shadow/evidence-sets/server-evidence/candidates/server-candidate/retain", {
                "in_sample_evaluation_id": "server-is",
                "out_of_sample_evaluation_id": "server-oos",
                "rationale": "research-only retention evidence",
            }),
            ("/api/theses/pending/server-pending/confirm", {"rationale": "人工确认理由至少十个字符。"}),
            ("/api/theses/pending/server-pending/reject", {"rationale": "人工驳回理由至少十个字符。"}),
            ("/api/forecast/instruments/600000.SH/jobs", {"horizon": 20, "catalog_id": "kronos-mini", "idempotency_key": "phase5-host"}),
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
            assert response.status_code in {200, 201, 404}
            _assert_safe_projection(response.json())
            spies.assert_zero_calls()
            if response.status_code == 404:
                continue
            job = response.json()["job"]
            assert job["status"] == terminal
            assert "record_id" not in job


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


def test_production_shadow_browser_contract_distills_and_evaluates_with_complete_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spies = LiveActionSpies()
    with _real_host(tmp_path, monkeypatch, frozenset({"shadow"}), spies=spies) as (app, client):
        _authenticate(client)

        sessions: list[date] = []
        cursor = date(2024, 1, 2)
        while cursor <= date(2024, 12, 31):
            if cursor.weekday() < 5:
                sessions.append(cursor)
            cursor += timedelta(days=1)
        trade_indexes = {60, 80, 180, 200}
        governed_rows = []
        for index, session in enumerate(sessions):
            is_trade_session = index in trade_indexes
            close = 10.0 + index * 0.01
            governed_rows.append(
                {
                    "symbol": "600001.SH",
                    "date": session,
                    "open": close - 0.02,
                    "high": close + (0.8 if is_trade_session else 0.05),
                    "low": close - (0.8 if is_trade_session else 0.05),
                    "close": close,
                    "volume": 8_000.0 if is_trade_session else 1_000.0 + index % 10,
                    "amount": close * (8_000.0 if is_trade_session else 1_000.0 + index % 10),
                    "quote_ts": 1_704_180_600_000 + index * 86_400_000,
                }
            )
        app.state.repo.append_enriched(pl.DataFrame(governed_rows))
        app.state.repo.rebuild_views()

        csv_rows = [
            "broker_fill_id,symbol,side,executed_at,quantity,price,fees,currency,account_alias"
        ]
        for ordinal, index in enumerate(sorted(trade_indexes), start=1):
            csv_rows.append(
                f"FILL-{ordinal:03d},600001.SH,buy,{sessions[index].isoformat()} 09:31:00,100,10.00,1.00,CNY,local-shadow"
            )
        mapping = {
            "broker_fill_id": "broker_fill_id",
            "symbol": "symbol",
            "side": "side",
            "executed_at": "executed_at",
            "quantity": "quantity",
            "price": "price",
            "fees": "fees",
            "currency": "currency",
            "account_alias": "account_alias",
        }
        csv_bytes = "\n".join(csv_rows).encode()
        previewed = client.post(
            "/api/shadow/imports/preview",
            files={"file": ("executions.csv", csv_bytes, "text/csv")},
            data={
                "mapping": json.dumps(mapping),
                "source_timezone": "Asia/Shanghai",
            },
        )
        assert previewed.status_code == 200, previewed.text
        imported = client.post(
            "/api/shadow/imports/confirm",
            files={"file": ("executions.csv", csv_bytes, "text/csv")},
            data={
                "mapping": json.dumps(mapping),
                "source_timezone": "Asia/Shanghai",
                "source_label": "deterministic local executions",
                "preview_identity": previewed.json()["preview"]["preview_identity"],
            },
        )
        assert imported.status_code == 201, imported.text
        batch_id = imported.json()["batch"]["id"]
        trade_ids = [
            item["id"]
            for item in app.state.shadow_repository.list_trade_facts(batch_id=batch_id)
        ]
        frozen = client.post(
            "/api/shadow/evidence-sets",
            json={
                "included_batch_ids": [batch_id],
                "included_trade_ids": trade_ids,
                "exclusions": [],
            },
        )
        assert frozen.status_code == 201, frozen.text
        evidence = frozen.json()["evidence_set"]

        strict_body = {
            "feature_names": [
                "close_return_5d",
                "volume_ratio_20d",
                "intraday_range",
            ],
            "seed": 17,
            "max_depth": 3,
            "min_leaf_support": 2,
            "exit_assumptions": {"kind": "fixed_holding_days", "days": 20},
            "holding_assumptions": {
                "price_adjustment": "unadjusted_execution_vs_forward_adjusted_research"
            },
        }
        distilled = client.post(
            f"/api/shadow/evidence-sets/{evidence['id']}/candidates", json=strict_body
        )
        assert distilled.status_code == 201, distilled.text
        candidate = distilled.json()["candidate"]
        assert candidate["features"] == strict_body["feature_names"]
        assert candidate["parameters"]["min_leaf_support"] == 2
        assert candidate["exit_assumptions"] == strict_body["exit_assumptions"]
        assert candidate["holding_assumptions"] == strict_body["holding_assumptions"]
        assert candidate["rules"]

        evaluated = client.post(
            f"/api/shadow/evidence-sets/{evidence['id']}/candidates/{candidate['id']}/evaluations",
            json={
                "in_sample_window": {"start": "2024-01-02", "end": "2024-06-28"},
                "out_of_sample_window": {"start": "2024-07-01", "end": "2024-12-31"},
                "split_policy": "chronological",
                "adjustment_policy": "governed_adjusted_daily",
                "cost_policy": {
                    "commission_bps": 3,
                    "slippage_bps": 5,
                    "stamp_duty_bps": 5,
                },
            },
        )
        assert evaluated.status_code == 201, evaluated.text
        evaluations = evaluated.json()["evaluations"]
        assert set(evaluations) == {"in_sample", "out_of_sample"}
        assert {item["status"] for item in evaluations.values()} == {"passed"}
        assert all(item["governed_fingerprint"] for item in evaluations.values())
        assert all(item["artifact"]["checksum_sha256"] for item in evaluations.values())
        spies.assert_zero_calls()
        _assert_completed_v1_loop(app, client)

    from app.optional_modules import (
        OptionalModuleName,
        build_optional_module_host,
        production_optional_factories,
    )

    incomplete = build_optional_module_host(
        database_path=tmp_path / "missing-governed" / "operational.db",
        data_root=tmp_path / "missing-governed" / "data",
        factories=production_optional_factories(),
        governed_repository=None,
    )
    assert incomplete.service(OptionalModuleName.SHADOW) is None
    status = incomplete.status(OptionalModuleName.SHADOW)
    assert status.available is False
    assert status.code == "shadow_initialization_failed"
    incomplete.close()


def test_production_thesis_readiness_and_governed_pending_are_real(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spies = LiveActionSpies()
    with _real_host(
        tmp_path,
        monkeypatch,
        frozenset(MODULE_NAMES),
        spies=spies,
        production_scheduler=True,
    ) as (app, client):
        _authenticate(client)
        capabilities = client.get(CAPABILITY_PATH)
        assert capabilities.status_code == 200
        for module in MODULE_NAMES:
            _assert_typed_status(capabilities.json(), module, True)

        payload = {
            "instrument": "600000.SH",
            "core_judgment": "Governed profitability remains a reviewable thesis input.",
            "rationale": "The existing governed financial lake supplies the immutable observation.",
            "change_reason": "Initial governed production thesis",
            "anchors": [{
                "method": "return_on_equity_range",
                "currency": "CNY",
                "as_of": "2023-09-30",
                "low": 8.0,
                "high": 12.0,
                "assumptions": [{"name": "roe_floor", "value": 0.1, "unit": "ratio"}],
                "limitations": ["The fixture contains one governed reporting period."],
            }],
            "conditions": [{
                "source_kind": "financial",
                "field": "roe",
                "operator": "lt",
                "threshold": 0.1,
                "unit": "ratio",
                "lookback_days": 3650,
                "cadence": "quarterly",
                "timezone": "Asia/Shanghai",
                "description": "Return on equity falls below the review floor.",
            }],
        }
        created = client.post("/api/theses/instruments/600000.SH/versions", json=payload)
        assert created.status_code == 201, created.text

        checks = app.state.thesis_due_scanner.scan_once(
            now=datetime.now(UTC) + timedelta(seconds=2), owner="host-acceptance"
        )
        assert len(checks) == 1
        assert checks[0]["result"] == "matched"
        assert checks[0]["observed_value"] == 0.09
        assert len(checks[0]["evidence"]) == 1
        assert set(checks[0]["evidence"][0]) == {
            "source_id",
            "source_revision",
            "source_kind",
            "instrument",
            "field",
            "observed_value",
            "unit",
            "as_of",
        }
        assert checks[0]["evidence"][0]["instrument"] == "600000.SH"
        assert checks[0]["evidence"][0]["field"] == "roe"

        pending = client.get("/api/theses/instruments/600000.SH/pending?offset=0&limit=1")
        assert pending.status_code == 200, pending.text
        assert pending.json()["total"] == 1
        assert pending.json()["has_more"] is False
        assert len(pending.json()["items"]) == 1
        assert pending.json()["items"][0]["status"] == "pending"
        assert pending.json()["items"][0]["proposed_state"] == "invalidated"
        spies.assert_zero_calls()
        _assert_completed_v1_loop(app, client)

    failure_root = tmp_path / "thesis-scanner-failure"
    failure_root.mkdir()
    with _real_host(
        failure_root,
        monkeypatch,
        frozenset(MODULE_NAMES),
        fail_scanner="thesis",
        spies=spies,
        production_scheduler=True,
    ) as (app, client):
        _authenticate(client)
        failed = client.get(CAPABILITY_PATH)
        assert failed.status_code == 200
        _assert_typed_status(failed.json(), "thesis", False)
        _assert_typed_status(failed.json(), "shadow", True)
        _assert_typed_status(failed.json(), "forecast", True)
        assert app.state.thesis_service is None
        assert app.state.thesis_due_scanner is None
        spies.assert_zero_calls()
        _assert_completed_v1_loop(app, client)

    from app.optional_modules import OptionalModuleName, build_optional_module_host, production_optional_factories

    no_scheduler = build_optional_module_host(
        database_path=tmp_path / "no-scheduler" / "operational.db",
        data_root=tmp_path / "no-scheduler" / "data",
        factories=production_optional_factories(),
        governed_repository=object(),
    )
    assert no_scheduler.service(OptionalModuleName.THESIS) is None
    assert no_scheduler.status(OptionalModuleName.THESIS).available is False
    no_scheduler.close()


def test_production_forecast_factory_completes_approved_request_and_stays_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spies = LiveActionSpies()
    with _real_host(
        tmp_path,
        monkeypatch,
        frozenset({"forecast"}),
        spies=spies,
    ) as (app, client):
        _authenticate(client)
        created = client.post(
            "/api/forecast/instruments/600000.SH/jobs",
            json={
                "horizon": 5,
                "catalog_id": "kronos-mini",
                "idempotency_key": "production-approved-request",
            },
        )
        assert created.status_code == 201, created.text
        job = created.json()["job"]
        assert job["status"] == "completed"
        assert job["record_id"]

        record = client.get(f"/api/forecast/records/{job['record_id']}")
        assert record.status_code == 200
        body = record.json()["record"]
        assert body["catalog_id"] == "kronos-mini"
        assert body["input_fingerprint"]
        checkpoint = ApprovedForecastCheckpointFixture()
        assert body["model_revision"] == checkpoint.model_revision
        assert body["tokenizer_revision"] == checkpoint.tokenizer_revision
        assert body["input_artifact"]["checksum_sha256"]

        assert app.state.forecast_request_service.__class__.__name__ == "ForecastService"
        spies.assert_zero_calls()
