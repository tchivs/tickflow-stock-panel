"""Independent lazy lifecycle host for optional Phase 05 capabilities."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from fastapi import APIRouter, Request

from app.operational.migrations import migrate_operational_db


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

    def __init__(
        self, *, available: bool, code: str, reason: str, install_hint: str
    ) -> None:
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
    return OptionalModuleProbe.unavailable(
        code=f"{name}_dependency_missing",
        reason=f"{name} optional dependency is not installed",
        install_hint=f"enable the {name} optional deployment capability",
    )


OPTIONAL_MODULE_PROBES: Mapping[str, Callable[[], OptionalModuleProbe]] = {
    name: (lambda module=name: _default_probe(module))
    for name in ("shadow", "thesis", "forecast")
}
OPTIONAL_MODULE_TEST_FAILURES: Mapping[str, str | None] = {
    "init": None,
    "recovery": None,
    "scanner": None,
}
OPTIONAL_MODULE_ACTION_COLLABORATORS: Mapping[str, Callable[..., object]] = {}


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
            install_hint=install_hint or f"enable the {module.value} optional deployment capability",
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


@runtime_checkable
class OptionalModuleFactory(Protocol):
    """Deployment adapter that probes and lazily creates one module service."""

    def probe(self) -> OptionalModuleStatus:
        """Check local deployment availability without loading heavy packages."""

    def create(self, services: OptionalModuleServices) -> object:
        """Create the module service only after its independent probe succeeds."""

    def close(self, service: object) -> None:
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


class _UnavailableShadowEvaluation:
    def evaluate_candidate(self, **_request: object) -> dict[str, object]:
        raise ValueError("Shadow evaluation collaborator is unavailable")

    def retry_evaluation(self, **_request: object) -> dict[str, object]:
        raise ValueError("Shadow evaluation collaborator is unavailable")


class _ForecastRequestService:
    def __init__(self, repository: object, data_root: Path) -> None:
        self.repository = repository
        self.data_root = data_root

    def create_or_get_job(
        self,
        *,
        principal: str,
        instrument: str,
        horizon: int,
        catalog_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        identity = json.dumps(
            {
                "instrument": instrument,
                "horizon": horizon,
                "catalog_id": catalog_id,
                "governed_root": self.data_root.name,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return self.repository.create_or_get_active_job(
            principal=principal,
            instrument_id=instrument,
            horizon=horizon,
            catalog_id=catalog_id,
            idempotency_key=idempotency_key,
            input_fingerprint=sha256(identity).hexdigest(),
        )

    @staticmethod
    def revalidate(job: Mapping[str, object]) -> bool:
        return (
            job.get("horizon") in {5, 20, 60}
            and isinstance(job.get("instrument_id"), str)
            and isinstance(job.get("catalog_id"), str)
            and isinstance(job.get("input_fingerprint"), str)
            and len(str(job["input_fingerprint"])) == 64
        )


class _ForecastActuals:
    """Read-only adapter; absent governed rows become explicit unevaluable facts."""

    def load_actual(self, **_identity: object) -> None:
        return None


class _ForecastPathReader:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def read_page(
        self, *, record: Mapping[str, object], offset: int, limit: int
    ) -> tuple[list[dict[str, object]], int]:
        descriptor = record.get("output_artifact_descriptor")
        if not isinstance(descriptor, Mapping):
            raise ValueError("Forecast output descriptor is unavailable")
        relative = descriptor.get("relative_path")
        checksum = descriptor.get("checksum_sha256")
        if not isinstance(relative, str) or not isinstance(checksum, str):
            raise ValueError("Forecast output descriptor is invalid")
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Forecast output artifact escapes its managed root")
        payload = candidate.read_bytes()
        if sha256(payload).hexdigest() != checksum:
            raise ValueError("Forecast output artifact checksum mismatch")
        import polars as pl

        frame = pl.read_parquet(candidate)
        return frame.slice(offset, limit).to_dicts(), frame.height


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
        from app.shadow.artifacts import ShadowArtifactStore
        from app.shadow.importer import ShadowImporter
        from app.shadow.repository import ShadowRepository
        from app.shadow.service import ShadowService

        repository = ShadowRepository(services.database_path)
        importer = ShadowImporter(
            repository=repository,
            artifact_store=ShadowArtifactStore(services.data_root / "shadow-artifacts"),
        )
        service = ShadowService(
            repository=repository,
            evaluation_service=_UnavailableShadowEvaluation(),
            importer=importer,
            distiller=None,
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
        from app.theses.evidence import GovernedEvidenceResolver
        from app.theses.repository import ThesisRepository
        from app.theses.scheduler import ThesisDueScanner
        from app.theses.service import ThesisService

        repository = ThesisRepository(services.database_path)
        empty_reader = lambda **_request: None
        resolver = GovernedEvidenceResolver(
            market_reader=empty_reader,
            financial_reader=empty_reader,
            analysis_reader=empty_reader,
        )
        service = ThesisService(repository=repository, evidence_resolver=resolver)
        scanner = ThesisDueScanner(repository=repository, service=service)
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
        from app.forecast.calibration import ForecastMaturityScanner
        from app.forecast.repository import ForecastRepository

        repository = ForecastRepository(services.database_path)
        repository.migrate()
        request_service = _ForecastRequestService(repository, services.data_root)
        scanner = ForecastMaturityScanner(
            repository=repository,
            actuals=_ForecastActuals(),
            max_items_per_scan=32,
            action_collaborators=OPTIONAL_MODULE_ACTION_COLLABORATORS,
        )
        return _RuntimeBundle(
            name=OptionalModuleName.FORECAST,
            database_path=services.database_path,
            data_root=services.data_root,
            repository=repository,
            service=request_service,
            scanner=scanner,
            request_service=request_service,
            path_reader=_ForecastPathReader(services.data_root),
        )

    def close(self, service: object) -> None:
        del service


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
        return tuple(self._module_services.values())

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
        self._statuses[module] = OptionalModuleStatus.unavailable(
            module,
            code=code,
            reason=f"{module.value} optional capability failed safely",
        )
        self._module_services.pop(module, None)

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

    def close(self) -> None:
        """Close each initialized service independently and make the host unavailable."""
        if self._closed:
            return
        self._closed = True
        for module, service in reversed(tuple(self._module_services.items())):
            factory = self._factories[module]
            try:
                factory.close(service)
            except Exception:
                pass
        self._module_services.clear()
        self._statuses.clear()

    @staticmethod
    def _validated_status(
        name: OptionalModuleName, status: object
    ) -> OptionalModuleStatus:
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
        with sqlite3.connect(operational_path) as connection:
            migrate_operational_db(connection)
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
    return {
        "modules": {name.value: host.status(name).as_dict() for name in OptionalModuleName}
    }


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
    """Install route shapes, then initialize each optional module independently."""
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
        else:
            _clear_module_state(app, name)
        _publish_module_status(app, host, name)

    forecast = host.service(OptionalModuleName.FORECAST)
    if isinstance(forecast, _RuntimeBundle):
        if OPTIONAL_MODULE_TEST_FAILURES.get("recovery") == "forecast":
            host.mark_unavailable(OptionalModuleName.FORECAST, code="forecast_recovery_failed")
            _clear_module_state(app, OptionalModuleName.FORECAST)
        else:
            try:
                forecast.repository.recover_after_restart(
                    revalidate=forecast.request_service.revalidate
                )
            except Exception:
                host.mark_unavailable(OptionalModuleName.FORECAST, code="forecast_recovery_failed")
                _clear_module_state(app, OptionalModuleName.FORECAST)

    for name in (OptionalModuleName.THESIS, OptionalModuleName.FORECAST):
        bundle = host.service(name)
        if not isinstance(bundle, _RuntimeBundle):
            _publish_module_status(app, host, name)
            continue
        if OPTIONAL_MODULE_TEST_FAILURES.get("scanner") == name.value:
            host.mark_unavailable(name, code=f"{name.value}_scanner_failed")
            _clear_module_state(app, name)
            _publish_module_status(app, host, name)
            continue
        try:
            _register_scanner(host, name, bundle)
        except Exception:
            host.mark_unavailable(name, code=f"{name.value}_scanner_failed")
            _clear_module_state(app, name)
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


def _register_scanner(
    host: OptionalModuleHost, name: OptionalModuleName, bundle: _RuntimeBundle
) -> None:
    scheduler = host.scheduler
    if scheduler is None:
        return
    if name is OptionalModuleName.THESIS:
        callback = lambda: bundle.scanner.scan_once(
            now=datetime.now(UTC), owner="phase5-thesis-scanner"
        )
        job_id = "phase5_thesis_due_scan"
    else:
        callback = lambda: bundle.scanner.scan(
            as_of_session_id=_forecast_as_of(bundle.repository)
        )
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


def _publish_module_status(
    app: Any, host: OptionalModuleHost, name: OptionalModuleName
) -> None:
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
        ),
    }[name]
    for attribute in names:
        setattr(app.state, attribute, None)


def build_and_install_optional_module_host(
    *,
    app: Any,
    database_path: Path,
    data_root: Path,
    scheduler: object | None,
    quote_service: object | None,
    governed_repository: object | None,
) -> OptionalModuleHost:
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
