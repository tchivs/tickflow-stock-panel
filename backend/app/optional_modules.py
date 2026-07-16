"""Independent lazy lifecycle host for optional Phase 05 capabilities."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
import re
import sqlite3
from typing import Mapping, Protocol, runtime_checkable

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


@runtime_checkable
class OptionalModuleFactory(Protocol):
    """Deployment adapter that probes and lazily creates one module service."""

    def probe(self) -> OptionalModuleStatus:
        """Check local deployment availability without loading heavy packages."""

    def create(self, services: OptionalModuleServices) -> object:
        """Create the module service only after its independent probe succeeds."""

    def close(self, service: object) -> None:
        """Release a previously created module service."""


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
        for module, service in tuple(self._module_services.items()):
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
    )
    return OptionalModuleHost(services=services, factories=factories)


def _coerce_name(name: OptionalModuleName | str) -> OptionalModuleName:
    if isinstance(name, OptionalModuleName):
        return name
    try:
        return OptionalModuleName(name)
    except (TypeError, ValueError) as error:
        raise ValueError("unknown optional module identity") from error
