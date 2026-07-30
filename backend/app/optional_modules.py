"""Independent lazy lifecycle host for optional Phase 05 capabilities."""

from __future__ import annotations

import importlib.util
import logging
import re
import sqlite3
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, Request

from app.operational.migrations import migrate_operational_db

logger = logging.getLogger(__name__)

_SAFE_CODE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")
_UNSAFE_STATUS_MARKERS = (
    "/",
    "\\",
    "traceback",
    "password",
    "secret",
    "token=",
    "environment",
)


class OptionalModuleName(str, Enum):
    """Fixed identities for independently deployable Phase 05 modules."""

    SHADOW = "shadow"
    THESIS = "thesis"
    FORECAST = "forecast"


class OptionalModuleProbe:
    """Lightweight deployment probe value used without importing optional packages."""

    def __init__(self, *, available: bool, code: str, reason: str, install_hint: str) -> None:
        self.available = available
        self.code = code
        self.reason = reason
        self.install_hint = install_hint

    @classmethod
    def available(cls, *, code: str = "optional_available") -> "OptionalModuleProbe":
        return cls(
            available=True,
            code=code,
            reason="optional capability is available",
            install_hint="optional capability is enabled",
        )

    @classmethod
    def unavailable(
        cls,
        *,
        code: str = "optional_unavailable",
        reason: str = "optional capability is unavailable",
        install_hint: str = "enable the optional deployment capability",
    ) -> "OptionalModuleProbe":
        return cls(
            available=False,
            code=code,
            reason=reason,
            install_hint=install_hint,
        )


def _default_probe(name: str) -> OptionalModuleProbe:
    if name == "thesis":
        return OptionalModuleProbe.available(code="thesis_available")
    if name == "shadow" and importlib.util.find_spec("sklearn") is not None:
        return OptionalModuleProbe.available(code="shadow_available")
    if name == "forecast":
        from app.config import settings

        if not settings.forecast_enabled:
            return OptionalModuleProbe.unavailable(
                code="forecast_disabled",
                reason="forecast optional capability is disabled",
                install_hint="enable and provision the forecast deployment capability",
            )
        if importlib.util.find_spec("torch") is None:
            return OptionalModuleProbe.unavailable(
                code="forecast_dependency_missing",
                reason="forecast optional dependency is not installed",
                install_hint="build the forecast optional dependency group",
            )
        if not OPTIONAL_MODULE_FORECAST_COMPONENTS:
            return OptionalModuleProbe.unavailable(
                code="forecast_checkpoint_unavailable",
                reason="approved local forecast supply is unavailable",
                install_hint="provision the approved local forecast checkpoint",
            )
        return OptionalModuleProbe.available(code="forecast_available")
    return OptionalModuleProbe.unavailable(
        code=f"{name}_dependency_missing",
        reason=f"{name} optional dependency is not installed",
        install_hint=f"enable the {name} optional deployment capability",
    )


OPTIONAL_MODULE_PROBES: Mapping[str, Callable[[], OptionalModuleProbe]] = {
    name: (lambda module=name: _default_probe(module)) for name in ("shadow", "thesis", "forecast")
}
OPTIONAL_MODULE_TEST_FAILURES: Mapping[str, str | None] = {
    "init": None,
    "recovery": None,
    "scanner": None,
}
OPTIONAL_MODULE_ACTION_COLLABORATORS: Mapping[str, Callable[..., object]] = {}
OPTIONAL_MODULE_FORECAST_COMPONENTS: Mapping[str, object] = {}


@dataclass(frozen=True, slots=True)
class OptionalModuleStatus:
    """Safe deployment availability projection for one optional module."""

    available: bool
    code: str
    reason: str
    install_hint: str

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool):
            raise TypeError("optional module availability must be boolean")
        if not _SAFE_CODE.fullmatch(self.code):
            raise ValueError("optional module status code is invalid")
        for value in (self.reason, self.install_hint):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError("optional module status text is invalid")
            lowered = value.lower()
            if any(marker in lowered for marker in _UNSAFE_STATUS_MARKERS):
                raise ValueError("optional module status text contains unsafe detail")

    @classmethod
    def ready(
        cls,
        name: OptionalModuleName,
        *,
        code: str | None = None,
        reason: str | None = None,
        install_hint: str | None = None,
    ) -> OptionalModuleStatus:
        module = _coerce_name(name)
        return cls(
            available=True,
            code=code or f"{module.value}_available",
            reason=reason or f"{module.value} optional capability is available",
            install_hint=install_hint or f"{module.value} optional capability is enabled",
        )

    @classmethod
    def unavailable(
        cls,
        name: OptionalModuleName,
        *,
        code: str | None = None,
        reason: str | None = None,
        install_hint: str | None = None,
    ) -> OptionalModuleStatus:
        module = _coerce_name(name)
        return cls(
            available=False,
            code=code or f"{module.value}_unavailable",
            reason=reason or f"{module.value} optional capability is unavailable",
            install_hint=install_hint
            or f"enable the {module.value} optional deployment capability",
        )

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OptionalModuleServices:
    """Shared runtime identities supplied to each available factory."""

    database_path: Path
    data_root: Path
    scheduler: object | None = None
    quote_service: object | None = None
    runtime_identity: int | None = None
    governed_repository: object | None = None


@dataclass(frozen=True, slots=True)
class OptionalModuleCloseOutcome:
    """Caller-visible bounded shutdown result."""

    stopped: tuple[str, ...]
    unresolved: tuple[str, ...]


class OptionalModuleCloseIncomplete(RuntimeError):
    """Retryable shutdown result that retains every unresolved owner."""

    def __init__(self, outcome: OptionalModuleCloseOutcome) -> None:
        super().__init__("optional module shutdown is incomplete")
        self.outcome = outcome


@runtime_checkable
class OptionalModuleFactory(Protocol):
    """Deployment adapter that probes and lazily creates one module service."""

    def probe(self) -> OptionalModuleStatus:
        """Check local deployment availability without loading heavy packages."""

    def create(self, services: OptionalModuleServices) -> object:
        """Create the module service only after its independent probe succeeds."""

    def close(self, service: object) -> object:
        """Release a previously created module service."""


@dataclass(slots=True)
class _RuntimeBundle:
    name: OptionalModuleName
    database_path: Path
    data_root: Path
    repository: object
    service: object
    scanner: object | None = None
    request_service: object | None = None
    path_reader: object | None = None
    dispatcher: object | None = None
    catalog_entries: tuple[Mapping[str, object], ...] = ()


class _ConcreteFactory:
    def __init__(self, name: OptionalModuleName) -> None:
        self.name = name

    def probe(self) -> OptionalModuleStatus:
        probe = OPTIONAL_MODULE_PROBES[self.name.value]()
        if not isinstance(probe, OptionalModuleProbe):
            raise TypeError("optional module probe returned an invalid value")
        return OptionalModuleStatus(
            available=bool(probe.available),
            code=probe.code,
            reason=probe.reason,
            install_hint=probe.install_hint,
        )

    def create(self, services: OptionalModuleServices) -> _RuntimeBundle:
        if OPTIONAL_MODULE_TEST_FAILURES.get("init") == self.name.value:
            raise RuntimeError("optional module initialization failed")
        if self.name is OptionalModuleName.SHADOW:
            return self._create_shadow(services)
        if self.name is OptionalModuleName.THESIS:
            return self._create_thesis(services)
        return self._create_forecast(services)

    @staticmethod
    def _create_shadow(services: OptionalModuleServices) -> _RuntimeBundle:
        from app.backtest.frozen_panel import FrozenPanelArtifactStore
        from app.shadow.artifacts import ShadowArtifactStore
        from app.shadow.distillation import ShadowDistiller
        from app.shadow.evaluation import ShadowEvaluationService
        from app.shadow.importer import ShadowImporter
        from app.shadow.production import (
            ProductionShadowEvaluationRunner,
            ProductionShadowFeatureFreezer,
            ProductionShadowFeatureSource,
            assert_shadow_runtime_ready,
        )
        from app.shadow.repository import ShadowRepository
        from app.shadow.service import ShadowService

        assert_shadow_runtime_ready(services.governed_repository)
        repository = ShadowRepository(services.database_path)
        raw_artifacts = ShadowArtifactStore(services.data_root / "shadow-artifacts")
        repository.set_artifact_verifier(raw_artifacts.load)
        importer = ShadowImporter(repository=repository, artifact_store=raw_artifacts)
        governed_panels = FrozenPanelArtifactStore(
            services.data_root / "shadow-artifacts" / "evaluation-panels"
        )
        distiller = ShadowDistiller(
            repository=repository,
            governed_feature_source=ProductionShadowFeatureSource(
                shadow_repository=repository,
                governed_repository=services.governed_repository,
            ),
        )
        evaluation_service = ShadowEvaluationService(
            repository=repository,
            feature_freezer=ProductionShadowFeatureFreezer(
                shadow_repository=repository,
                governed_repository=services.governed_repository,
                artifact_store=governed_panels,
            ),
            runner=ProductionShadowEvaluationRunner(
                governed_repository=services.governed_repository,
                artifact_store=governed_panels,
            ),
        )
        service = ShadowService(
            repository=repository,
            evaluation_service=evaluation_service,
            importer=importer,
            distiller=distiller,
        )
        return _RuntimeBundle(
            name=OptionalModuleName.SHADOW,
            database_path=services.database_path,
            data_root=services.data_root,
            repository=repository,
            service=service,
        )

    @staticmethod
    def _create_thesis(services: OptionalModuleServices) -> _RuntimeBundle:
        from app.theses.evidence import (
            GovernedAnalysisReader,
            GovernedEvidenceResolver,
            GovernedFinancialReader,
            GovernedMarketReader,
        )
        from app.theses.repository import ThesisRepository
        from app.theses.scheduler import ThesisDueScanner
        from app.theses.service import ThesisService

        if services.governed_repository is None:
            raise RuntimeError("thesis governed repository is unavailable")
        if not callable(getattr(services.scheduler, "add_job", None)):
            raise RuntimeError("thesis scheduler is unavailable")
        repository = ThesisRepository(services.database_path)
        market_reader = GovernedMarketReader(repository=services.governed_repository)
        financial_reader = GovernedFinancialReader(data_root=services.data_root)
        analysis_reader = GovernedAnalysisReader(database_path=services.database_path)
        for reader in (market_reader, financial_reader, analysis_reader):
            reader.assert_ready()
        resolver = GovernedEvidenceResolver(
            market_reader=market_reader,
            financial_reader=financial_reader,
            analysis_reader=analysis_reader,
        )
        service = ThesisService(repository=repository, evidence_resolver=resolver)
        scanner = ThesisDueScanner(repository=repository, service=service)
        scanner.assert_ready()
        return _RuntimeBundle(
            name=OptionalModuleName.THESIS,
            database_path=services.database_path,
            data_root=services.data_root,
            repository=repository,
            service=service,
            scanner=scanner,
        )

    @staticmethod
    def _create_forecast(services: OptionalModuleServices) -> _RuntimeBundle:
        from functools import partial

        from app.forecast.artifacts import ForecastPathReader
        from app.forecast.calibration import ForecastMaturityScanner
        from app.forecast.input import ForecastInputFreezer
        from app.forecast.repository import ForecastRepository
        from app.forecast.runner import ForecastRunner, ForecastRunnerLimits
        from app.forecast.service import (
            ContextualForecastWorker,
            DurableForecastDispatcher,
            ForecastService,
            GovernedForecastActuals,
            GovernedForecastDataSource,
            verify_output_artifact,
        )

        components = OPTIONAL_MODULE_FORECAST_COMPONENTS
        catalog = components.get("catalog")
        calendar = components.get("calendar")
        worker = components.get("worker")
        if catalog is None or calendar is None or not callable(worker):
            raise RuntimeError("Forecast local runtime dependencies are unavailable")

        input_root = Path(components.get("input_root", services.data_root / "forecast-inputs"))
        output_root = Path(components.get("output_root", services.data_root / "forecast-outputs"))
        output_root.mkdir(parents=True, exist_ok=True)
        repository = ForecastRepository(services.database_path, artifact_root=output_root)
        repository.migrate()
        input_repository = components.get("input_repository")
        if input_repository is None:
            input_repository = GovernedForecastDataSource(services.governed_repository)
        readiness = getattr(input_repository, "assert_ready", None)
        if callable(readiness):
            readiness()

        freezer = ForecastInputFreezer(
            repository=input_repository,
            calendar=calendar,
            artifact_root=input_root,
        )
        as_of_session = components.get("as_of_session")
        if not callable(as_of_session):
            as_of_session = getattr(input_repository, "latest_session_id", None)
        if not callable(as_of_session):
            raise RuntimeError("Forecast governed as-of resolver is unavailable")

        contexts: dict[str, Mapping[str, object]] = {}
        request_service = ForecastService(
            repository=repository,
            catalog=catalog,
            freezer=freezer,
            runner=None,
            as_of_session=as_of_session,
            device=str(components.get("device", "cpu")),
            worker_contexts=contexts,
        )
        limits = components.get("limits")
        if limits is None:
            limits = ForecastRunnerLimits()
        if not isinstance(limits, ForecastRunnerLimits):
            raise RuntimeError("Forecast runner limits are invalid")
        verifier = components.get("artifact_verify")
        if not callable(verifier):
            verifier = partial(verify_output_artifact, root=output_root)
        stop_token = threading.Event()
        runner = ForecastRunner(
            repository=repository,
            limits=limits,
            reauthorize=request_service.reauthorize,
            catalog_revalidate=request_service.catalog_revalidate,
            input_revalidate=request_service.input_revalidate,
            worker=ContextualForecastWorker(delegate=worker, contexts=contexts),
            artifact_verify=verifier,
            action_collaborators=OPTIONAL_MODULE_ACTION_COLLABORATORS,
            final_input_revalidate=request_service.final_input_revalidate,
            stop_token=stop_token,
        )
        request_service.attach_runner(runner)
        request_service.assert_ready()
        dispatcher = DurableForecastDispatcher(
            repository=repository,
            runner=runner,
            stop_token=stop_token,
        )

        actuals = components.get("actuals")
        if actuals is None:
            if not isinstance(input_repository, GovernedForecastDataSource):
                raise RuntimeError("Forecast governed actual reader is unavailable")
            actuals = GovernedForecastActuals(input_repository)
        actuals_ready = getattr(actuals, "assert_ready", None)
        if callable(actuals_ready):
            actuals_ready()
        if not callable(getattr(actuals, "load_actual", None)):
            raise RuntimeError("Forecast governed actual reader is incomplete")

        scanner = ForecastMaturityScanner(
            repository=repository,
            actuals=actuals,
            max_items_per_scan=32,
            action_collaborators=OPTIONAL_MODULE_ACTION_COLLABORATORS,
        )
        if not callable(getattr(scanner, "scan", None)) or not callable(
            getattr(scanner, "evaluate", None)
        ):
            raise RuntimeError("Forecast maturity scanner is incomplete")
        return _RuntimeBundle(
            name=OptionalModuleName.FORECAST,
            database_path=services.database_path,
            data_root=services.data_root,
            repository=repository,
            service=request_service,
            scanner=scanner,
            request_service=request_service,
            path_reader=ForecastPathReader(output_root),
            dispatcher=dispatcher,
            catalog_entries=tuple(components.get("catalog_entries", ())),
        )

    def close(self, service: object) -> None:
        if isinstance(service, _RuntimeBundle):
            close = getattr(service.dispatcher, "close", None)
            if callable(close):
                outcome = close()
                if getattr(outcome, "value", outcome) == "timed_out":
                    raise RuntimeError("forecast_dispatcher_close_incomplete")


def production_optional_factories() -> dict[OptionalModuleName, OptionalModuleFactory]:
    return {name: _ConcreteFactory(name) for name in OptionalModuleName}


class OptionalModuleHost:
    """Caches local probe results and lazily owns independent module services."""

    def __init__(
        self,
        *,
        services: OptionalModuleServices,
        factories: Mapping[OptionalModuleName, OptionalModuleFactory] | None = None,
    ) -> None:
        self._shared = services
        self._factories: dict[OptionalModuleName, OptionalModuleFactory] = {}
        for raw_name, factory in (factories or {}).items():
            name = _coerce_name(raw_name)
            if name in self._factories:
                raise ValueError(f"duplicate optional module factory: {name.value}")
            self._factories[name] = factory
        self._statuses: dict[OptionalModuleName, OptionalModuleStatus] = {}
        self._module_services: dict[OptionalModuleName, object] = {}
        self._closing_services: dict[OptionalModuleName, object] = {}
        self._closed = False

    @property
    def database_path(self) -> Path:
        return self._shared.database_path

    @property
    def data_root(self) -> Path:
        return self._shared.data_root

    @property
    def scheduler(self) -> object | None:
        return self._shared.scheduler

    @property
    def quote_service(self) -> object | None:
        return self._shared.quote_service

    @property
    def runtime_identity(self) -> int | None:
        return self._shared.runtime_identity

    @property
    def initialized_services(self) -> tuple[object, ...]:
        active = tuple(self._module_services.values())
        closing = tuple(
            service
            for module, service in self._closing_services.items()
            if module not in self._module_services
        )
        return active + closing

    @property
    def external_databases(self) -> tuple[()]:
        return ()

    @property
    def external_queues(self) -> tuple[()]:
        return ()

    @property
    def external_services(self) -> tuple[()]:
        return ()

    @property
    def child_containers(self) -> tuple[()]:
        return ()

    def mark_unavailable(self, name: OptionalModuleName, *, code: str) -> None:
        module = _coerce_name(name)
        service = self._module_services.get(module)
        if service is None:
            service = self._closing_services.get(module)
        unresolved = False
        if service is not None:
            factory = self._factories.get(module)
            if factory is not None:
                try:
                    factory.close(service)
                except Exception:
                    unresolved = True
                    self._module_services.pop(module, None)
                    self._closing_services[module] = service
                else:
                    self._module_services.pop(module, None)
                    self._closing_services.pop(module, None)
        self._statuses[module] = OptionalModuleStatus.unavailable(
            module,
            code=code,
            reason=f"{module.value} optional capability failed safely",
        )
        if unresolved:
            raise OptionalModuleCloseIncomplete(
                OptionalModuleCloseOutcome(stopped=(), unresolved=(module.value,))
            )

    def status(self, name: OptionalModuleName | str) -> OptionalModuleStatus:
        """Probe one capability only, caching deployment availability afterward."""
        module = _coerce_name(name)
        cached = self._statuses.get(module)
        if cached is not None:
            return cached
        if self._closed:
            status = OptionalModuleStatus.unavailable(
                module,
                code=f"{module.value}_host_closed",
                reason=f"{module.value} optional capability host is closed",
            )
            self._statuses[module] = status
            return status
        factory = self._factories.get(module)
        if factory is None:
            status = OptionalModuleStatus.unavailable(module)
            self._statuses[module] = status
            return status
        try:
            probed = factory.probe()
            status = self._validated_status(module, probed)
        except Exception:
            status = OptionalModuleStatus.unavailable(
                module,
                code=f"{module.value}_probe_failed",
                reason=f"{module.value} optional capability probe failed safely",
            )
        self._statuses[module] = status
        return status

    def service(self, name: OptionalModuleName | str) -> object | None:
        """Return one lazily initialized service without affecting peer modules."""
        module = _coerce_name(name)
        existing = self._module_services.get(module)
        if existing is not None:
            return existing
        status = self.status(module)
        if not status.available or self._closed:
            return None
        factory = self._factories[module]
        try:
            created = factory.create(self._shared)
            if created is None:
                raise RuntimeError("factory returned no service")
        except Exception:
            self._statuses[module] = OptionalModuleStatus.unavailable(
                module,
                code=f"{module.value}_initialization_failed",
                reason=f"{module.value} optional capability initialization failed safely",
            )
            return None
        self._module_services[module] = created
        return created

    def close(self) -> OptionalModuleCloseOutcome:
        """Close each initialized service independently and make the host unavailable."""
        self._closed = True
        stopped: list[str] = []
        unresolved: list[str] = []
        owned: dict[OptionalModuleName, object] = dict(self._module_services)
        owned.update(self._closing_services)
        for module, service in reversed(tuple(owned.items())):
            factory = self._factories[module]
            try:
                factory.close(service)
            except Exception:
                self._module_services.pop(module, None)
                self._closing_services[module] = service
                unresolved.append(module.value)
            else:
                self._module_services.pop(module, None)
                self._closing_services.pop(module, None)
                stopped.append(module.value)
        outcome = OptionalModuleCloseOutcome(
            stopped=tuple(stopped),
            unresolved=tuple(unresolved),
        )
        if unresolved:
            raise OptionalModuleCloseIncomplete(outcome)
        self._statuses.clear()
        return outcome

    @staticmethod
    def _validated_status(name: OptionalModuleName, status: object) -> OptionalModuleStatus:
        if not isinstance(status, OptionalModuleStatus):
            return OptionalModuleStatus.unavailable(
                name,
                code=f"{name.value}_probe_invalid",
                reason=f"{name.value} optional capability probe returned an invalid status",
            )
        try:
            return OptionalModuleStatus(**status.as_dict())
        except (TypeError, ValueError):
            return OptionalModuleStatus.unavailable(
                name,
                code=f"{name.value}_probe_invalid",
                reason=f"{name.value} optional capability probe returned an invalid status",
            )


def build_optional_module_host(
    *,
    database_path: Path,
    data_root: Path,
    factories: Mapping[OptionalModuleName, OptionalModuleFactory] | None = None,
    scheduler: object | None = None,
    quote_service: object | None = None,
    runtime_identity: int | None = None,
    governed_repository: object | None = None,
) -> OptionalModuleHost:
    """Migrate the shared operational database and build a light, unwired host."""
    operational_path = Path(database_path).resolve()
    governed_root = Path(data_root).resolve()
    try:
        operational_path.parent.mkdir(parents=True, exist_ok=True)
        governed_root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(operational_path)
        try:
            migrate_operational_db(connection)
        finally:
            connection.close()
    except (OSError, sqlite3.DatabaseError) as error:
        raise RuntimeError("optional module operational foundation is unavailable") from error
    services = OptionalModuleServices(
        database_path=operational_path,
        data_root=governed_root,
        scheduler=scheduler,
        quote_service=quote_service,
        runtime_identity=runtime_identity,
        governed_repository=governed_repository,
    )
    return OptionalModuleHost(services=services, factories=factories)


_capability_router = APIRouter()


@_capability_router.get("/api/optional-modules")
def optional_module_capabilities(request: Request) -> dict[str, object]:
    host = getattr(request.app.state, "optional_module_host", None)
    if not isinstance(host, OptionalModuleHost):
        return {
            "modules": {
                name.value: OptionalModuleStatus.unavailable(name).as_dict()
                for name in OptionalModuleName
            }
        }
    return {"modules": {name.value: host.status(name).as_dict() for name in OptionalModuleName}}


class _AuthenticatedInstrumentScope:
    def allows(self, subject_kind: str, subject_key: str) -> bool:
        return subject_kind == "instrument" and bool(re.fullmatch(r"[0-9A-Z.-]{1,32}", subject_key))


def install_optional_module_routes(app: Any) -> None:
    """Install optional route shapes once before any catch-all route."""
    if getattr(app.state, "phase5_optional_routes_installed", False):
        return
    from app.forecast.api import router as forecast_router
    from app.shadow.api import router as shadow_router
    from app.theses.api import router as thesis_router

    app.include_router(_capability_router)
    app.include_router(shadow_router)
    app.include_router(thesis_router)
    app.include_router(forecast_router)
    app.state.phase5_optional_routes_installed = True


def install_optional_module_host(app: Any, host: OptionalModuleHost) -> None:
    """Install routes and publish only completely initialized module readiness."""
    install_optional_module_routes(app)
    app.state.optional_module_host = host
    scope = _AuthenticatedInstrumentScope()
    app.state.resolve_thesis_subject_scope = lambda _request: scope
    app.state.resolve_forecast_subject_scope = lambda _request: scope

    for name in OptionalModuleName:
        bundle = host.service(name)
        if isinstance(bundle, _RuntimeBundle):
            if name is OptionalModuleName.SHADOW:
                app.state.shadow_repository = bundle.repository
                app.state.shadow_service = bundle.service
            elif name is OptionalModuleName.THESIS:
                app.state.thesis_repository = bundle.repository
                app.state.thesis_service = bundle.service
                app.state.thesis_due_scanner = bundle.scanner
            else:
                from app.forecast.api import ForecastProgressHub

                app.state.forecast_repository = bundle.repository
                app.state.forecast_request_service = bundle.request_service
                app.state.forecast_maturity_scanner = bundle.scanner
                app.state.forecast_path_reader = bundle.path_reader
                app.state.forecast_progress_hub = ForecastProgressHub()
                app.state.forecast_catalog_entries = bundle.catalog_entries
        else:
            _clear_module_state(app, name)

    app.state.forecast_recovery_outcomes = ()
    forecast = host.service(OptionalModuleName.FORECAST)
    if isinstance(forecast, _RuntimeBundle):
        if OPTIONAL_MODULE_TEST_FAILURES.get("recovery") == "forecast":
            host.mark_unavailable(OptionalModuleName.FORECAST, code="forecast_recovery_failed")
            _clear_module_state(app, OptionalModuleName.FORECAST)
        else:
            try:
                recovery = forecast.repository.recover_after_restart(
                    revalidate=forecast.request_service.revalidate
                )
                outcomes: list[dict[str, str]] = []
                for outcome in recovery:
                    job_id = outcome.get("job_id")
                    operation_id = outcome.get("operation_id")
                    action = outcome.get("action")
                    if action == "aborted" and isinstance(operation_id, str):
                        _cleanup_expired_retry_artifact(forecast, outcome)
                        outcomes.append(
                            {
                                "operation_id": operation_id,
                                "action": action,
                                "status": str(outcome.get("status", "")),
                            }
                        )
                        continue
                    if not isinstance(job_id, str) or not isinstance(action, str):
                        raise RuntimeError("Forecast recovery outcome is invalid")
                    if action == "requeue":
                        dispatched = forecast.request_service.run_recovered_job(job_id)
                        outcomes.append(
                            {
                                "job_id": job_id,
                                "action": str(dispatched.get("action")),
                                "status": str(dispatched.get("status")),
                            }
                        )
                    else:
                        outcomes.append(
                            {
                                "job_id": job_id,
                                "action": action,
                                "status": str(outcome.get("status", "")),
                            }
                        )
                app.state.forecast_recovery_outcomes = tuple(outcomes)
                if forecast.dispatcher is not None:
                    forecast.request_service.attach_dispatcher(forecast.dispatcher)
            except Exception:
                host.mark_unavailable(OptionalModuleName.FORECAST, code="forecast_recovery_failed")
                _clear_module_state(app, OptionalModuleName.FORECAST)

    for name in (OptionalModuleName.THESIS, OptionalModuleName.FORECAST):
        bundle = host.service(name)
        if not isinstance(bundle, _RuntimeBundle):
            continue
        if OPTIONAL_MODULE_TEST_FAILURES.get("scanner") == name.value:
            host.mark_unavailable(name, code=f"{name.value}_scanner_failed")
            _clear_module_state(app, name)
            continue
        try:
            _register_scanner(host, name, bundle)
        except Exception:
            host.mark_unavailable(name, code=f"{name.value}_scanner_failed")
            _clear_module_state(app, name)

    # Background consumption begins only after the scanner and all readiness
    # registrations succeed. A failed module is never published with a live worker.
    forecast = host.service(OptionalModuleName.FORECAST)
    if isinstance(forecast, _RuntimeBundle) and forecast.dispatcher is not None:
        try:
            forecast.dispatcher.start()
        except Exception:
            scheduler = host.scheduler
            if scheduler is not None:
                try:
                    scheduler.remove_job("phase5_forecast_maturity_scan")
                except Exception:
                    pass
            host.mark_unavailable(OptionalModuleName.FORECAST, code="forecast_dispatcher_failed")
            _clear_module_state(app, OptionalModuleName.FORECAST)

    for name in OptionalModuleName:
        _publish_module_status(app, host, name)


def shutdown_optional_module_host(app: Any) -> None:
    host = getattr(app.state, "optional_module_host", None)
    if not isinstance(host, OptionalModuleHost):
        return
    scheduler = host.scheduler
    if scheduler is not None:
        for job_id in ("phase5_thesis_due_scan", "phase5_forecast_maturity_scan"):
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
    host.close()


def _cleanup_expired_retry_artifact(bundle: _RuntimeBundle, outcome: Mapping[str, object]) -> None:
    """Reference-check and discard only an expired operation-owned input."""
    artifact_id = outcome.get("input_artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        return
    repository = bundle.repository
    referenced = getattr(repository, "input_artifact_is_referenced", None)
    if not callable(referenced) or referenced(artifact_id):
        return
    freezer = getattr(bundle.request_service, "freezer", None)
    store = getattr(freezer, "_store", None)
    descriptor = getattr(store, "descriptor", None)
    discard = getattr(store, "discard_unbound_invocation_owned", None)
    if not callable(descriptor) or not callable(discard):
        return
    managed = descriptor(artifact_id)
    discard(
        managed,
        owned_artifact_ids={artifact_id},
        is_referenced=referenced,
    )


def _register_scanner(
    host: OptionalModuleHost, name: OptionalModuleName, bundle: _RuntimeBundle
) -> None:
    scheduler = host.scheduler
    if scheduler is None:
        raise RuntimeError(f"{name.value} scanner registration is unavailable")
    if not callable(getattr(scheduler, "add_job", None)):
        raise RuntimeError("optional scanner registration is unavailable")
    if name is OptionalModuleName.THESIS:
        readiness = getattr(bundle.scanner, "assert_ready", None)
        if not callable(readiness):
            raise RuntimeError("thesis scanner readiness is unavailable")
        readiness()
        callback = lambda: bundle.scanner.scan_once(
            now=datetime.now(UTC), owner="phase5-thesis-scanner"
        )
        job_id = "phase5_thesis_due_scan"
    else:
        callback = lambda: bundle.scanner.scan(as_of_session_id=_forecast_as_of(bundle.repository))
        job_id = "phase5_forecast_maturity_scan"
    scheduler.add_job(
        callback,
        trigger="interval",
        minutes=60,
        id=job_id,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )


def _forecast_as_of(repository: object) -> str:
    records = repository.list_forecasts()
    if not records:
        return "no-governed-session"
    sessions = records[-1].get("future_session_ids", [])
    return str(sessions[-1]) if sessions else "no-governed-session"


def _publish_module_status(app: Any, host: OptionalModuleHost, name: OptionalModuleName) -> None:
    setattr(app.state, f"{name.value}_module_status", host.status(name))


def _clear_module_state(app: Any, name: OptionalModuleName) -> None:
    names = {
        OptionalModuleName.SHADOW: ("shadow_repository", "shadow_service"),
        OptionalModuleName.THESIS: ("thesis_repository", "thesis_service", "thesis_due_scanner"),
        OptionalModuleName.FORECAST: (
            "forecast_repository",
            "forecast_request_service",
            "forecast_maturity_scanner",
            "forecast_path_reader",
            "forecast_progress_hub",
            "forecast_recovery_outcomes",
        ),
    }[name]
    for attribute in names:
        setattr(app.state, attribute, None)


def _configure_production_forecast(data_root: Path) -> None:
    """Populate production components only after all local supply checks pass."""
    global OPTIONAL_MODULE_FORECAST_COMPONENTS
    if OPTIONAL_MODULE_FORECAST_COMPONENTS:
        return
    from app.config import settings

    if not settings.forecast_enabled or importlib.util.find_spec("torch") is None:
        return
    try:
        from app.forecast.bootstrap import build_production_forecast_components

        OPTIONAL_MODULE_FORECAST_COMPONENTS = build_production_forecast_components(
            checkpoint_root=settings.forecast_checkpoint_root,
            data_root=data_root,
            device=settings.forecast_device,
        )
    except Exception as error:  # startup must fail closed, not fail the host
        logger.warning("Forecast production supply rejected: %s", error)
        OPTIONAL_MODULE_FORECAST_COMPONENTS = {}


def build_and_install_optional_module_host(
    *,
    app: Any,
    database_path: Path,
    data_root: Path,
    scheduler: object | None,
    quote_service: object | None,
    governed_repository: object | None,
) -> OptionalModuleHost:
    _configure_production_forecast(data_root)
    host = build_optional_module_host(
        database_path=database_path,
        data_root=data_root,
        factories=production_optional_factories(),
        scheduler=scheduler,
        quote_service=quote_service,
        runtime_identity=id(app),
        governed_repository=governed_repository,
    )
    install_optional_module_host(app, host)
    return host


def _coerce_name(name: OptionalModuleName | str) -> OptionalModuleName:
    if isinstance(name, OptionalModuleName):
        return name
    try:
        return OptionalModuleName(name)
    except (TypeError, ValueError) as error:
        raise ValueError("unknown optional module identity") from error
