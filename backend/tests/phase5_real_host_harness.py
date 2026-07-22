"""Test-only production optional-host launcher for Phase 05 CR-01 real-browser proof.

Launches the real FastAPI lifespan with:
- temporary DATA_DIR / operational.db / artifact roots
- deterministic Phase-1 governed market fixture large enough for Shadow distillation
- authenticated principal via AUTH_PASSWORD
- live-action collaborator spies (must remain zero)
- repository-ID bypass and unexpected external-request telemetry (must remain zero)

Never seeds or exposes Shadow trade/evidence repository IDs for request construction.
Intended only for Playwright webServer process startup.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

# Ensure backend package imports resolve when spawned from frontend cwd.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

HOST = os.environ.get("PHASE5_REAL_HOST_BIND", "127.0.0.1")
PORT = int(os.environ.get("PHASE5_REAL_HOST_PORT", "3019"))
PASSWORD = os.environ.get("PHASE5_REAL_HOST_PASSWORD", "phase5-real-host-password")
TELEMETRY_PATH = Path(
    os.environ.get(
        "PHASE5_REAL_HOST_TELEMETRY",
        str(Path(tempfile.gettempdir()) / "phase5-real-host-telemetry.json"),
    )
)


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

    def counts(self) -> dict[str, int]:
        return {name: len(spy.calls) for name, spy in self.as_mapping().items()}


# Process-wide telemetry mutated only by this harness / installed patches.
_SPIES = LiveActionSpies()
_REPOSITORY_ID_BYPASS = 0
_UNEXPECTED_EXTERNAL = 0
_ORIGINAL_SOCKET_CONNECT: Callable[..., Any] | None = None
_TMP_ROOT: Path | None = None


def _weekday_sessions(start: date, end: date) -> list[date]:
    sessions: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor += timedelta(days=1)
    return sessions


def _write_governed_shadow_fixture(fixtures_dir: Path) -> None:
    """Write a year of deterministic daily bars for one instrument used by CR-01 CSV trades."""
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    fixtures_dir.mkdir(parents=True, exist_ok=True)
    shanghai = ZoneInfo("Asia/Shanghai")
    symbol = "600001.SH"
    sessions = _weekday_sessions(date(2023, 10, 2), date(2025, 3, 31))

    def quote_ts_for(session: date) -> int:
        return int(datetime.combine(session, time(15, 0), tzinfo=shanghai).timestamp() * 1000)

    daily: list[dict[str, object]] = []
    adj: list[dict[str, object]] = []
    trade_indexes = {40 + i * 10 for i in range(22)}  # ~22 buy-capable sessions inside 2024
    for index, session in enumerate(sessions):
        is_trade = index in trade_indexes
        close = 10.0 + index * 0.01
        volume = 8_000.0 if is_trade else 1_000.0 + index % 10
        daily.append(
            {
                "symbol": symbol,
                "date": session.isoformat(),
                "open": round(close - 0.02, 4),
                "high": round(close + (0.8 if is_trade else 0.05), 4),
                "low": round(close - (0.8 if is_trade else 0.05), 4),
                "close": round(close, 4),
                "volume": volume,
                "amount": round(close * volume, 4),
                "quote_ts": quote_ts_for(session),
            }
        )
        adj.append({"symbol": symbol, "trade_date": session.isoformat(), "adj_factor": 1.0})

    # Keep a second liquid instrument so general fixture validation stays happy.
    for index, session in enumerate(sessions[:5]):
        daily.append(
            {
                "symbol": "600000.SH",
                "date": session.isoformat(),
                "open": 7.1,
                "high": 7.3,
                "low": 7.05,
                "close": 7.25,
                "volume": 1000.0,
                "amount": 7250.0,
                "quote_ts": quote_ts_for(session),
            }
        )
        adj.append({"symbol": "600000.SH", "trade_date": session.isoformat(), "adj_factor": 1.0})

    index_daily = [
        {
            "symbol": "000300.SH",
            "date": session.isoformat(),
            "open": 3500.0 + index,
            "high": 3510.0 + index,
            "low": 3490.0 + index,
            "close": 3505.0 + index,
            "volume": 1_000_000.0,
            "amount": 3_500_000_000.0,
            "quote_ts": quote_ts_for(session),
        }
        for index, session in enumerate(sessions)
    ]

    instruments = {
        "instruments": [
            {"symbol": "600001.SH", "name": "邯郸钢铁", "code": "600001", "exchange": "SH"},
            {"symbol": "600000.SH", "name": "浦发银行", "code": "600000", "exchange": "SH"},
        ]
    }
    market = {
        "daily": daily,
        "index_daily": index_daily,
        "adjustment_factors": adj,
        "financials": [
            {"symbol": "600001.SH", "report_date": "2023-09-30", "roe": 0.08},
            {"symbol": "600000.SH", "report_date": "2023-09-30", "roe": 0.09},
        ],
    }
    (fixtures_dir / "instruments.json").write_text(
        json.dumps(instruments, ensure_ascii=False), encoding="utf-8"
    )
    (fixtures_dir / "market-data.json").write_text(
        json.dumps(market, ensure_ascii=False), encoding="utf-8"
    )
    for path in fixtures_dir.iterdir():
        path.chmod(0o444)
    fixtures_dir.chmod(0o555)


def _install_network_guard() -> None:
    """Count non-loopback TCP connects as unexpected external traffic."""
    global _ORIGINAL_SOCKET_CONNECT, _UNEXPECTED_EXTERNAL
    if _ORIGINAL_SOCKET_CONNECT is not None:
        return
    _ORIGINAL_SOCKET_CONNECT = socket.socket.connect

    def guarded_connect(self: socket.socket, address: Any) -> Any:  # noqa: ANN401
        global _UNEXPECTED_EXTERNAL
        host: str | None = None
        if isinstance(address, tuple) and address:
            host = str(address[0])
        elif isinstance(address, str):
            host = address
        if host and host not in {"127.0.0.1", "::1", "localhost"}:
            # DNS / unix sockets and internal control sockets may appear as non-IP labels.
            try:
                packed = socket.inet_pton(
                    socket.AF_INET6 if ":" in host else socket.AF_INET, host
                )
                is_loopback = packed in {
                    socket.inet_pton(socket.AF_INET, "127.0.0.1"),
                    socket.inet_pton(socket.AF_INET6, "::1"),
                }
            except OSError:
                is_loopback = host.endswith(".local") or host.startswith("/")
            if not is_loopback and os.environ.get("ATHENA_ALLOW_NETWORK", "0") != "1":
                _UNEXPECTED_EXTERNAL += 1
                raise OSError(f"unexpected external network connect blocked: {host}")
        assert _ORIGINAL_SOCKET_CONNECT is not None
        return _ORIGINAL_SOCKET_CONNECT(self, address)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign]


def _mark_repository_id_bypass() -> None:
    """Explicit harness helper — must never be called by CR-01 request construction."""
    global _REPOSITORY_ID_BYPASS
    _REPOSITORY_ID_BYPASS += 1


def telemetry_snapshot() -> dict[str, Any]:
    return {
        "repository_id_bypass": _REPOSITORY_ID_BYPASS,
        "live_action_counts": _SPIES.counts(),
        "unexpected_external_requests": _UNEXPECTED_EXTERNAL,
        "ready": True,
    }


def write_telemetry() -> None:
    TELEMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    TELEMETRY_PATH.write_text(json.dumps(telemetry_snapshot()), encoding="utf-8")


def _install_telemetry_route(app: Any) -> None:
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/api/__phase5_real_host__/telemetry")
    def phase5_real_host_telemetry() -> dict[str, Any]:
        snapshot = telemetry_snapshot()
        write_telemetry()
        return snapshot

    @router.get("/api/__phase5_real_host__/health")
    def phase5_real_host_health() -> dict[str, Any]:
        return {"status": "ok", "module": "phase5_real_host_harness"}

    # SPA catch-all is registered at import time; prepend so these win first-match.
    for route in reversed(list(router.routes)):
        app.router.routes.insert(0, route)


def prepare_environment() -> Path:
    """Create temp storage, fixture market data, env vars, and collaborator spies."""
    global _TMP_ROOT
    root = Path(tempfile.mkdtemp(prefix="phase5-real-host-"))
    _TMP_ROOT = root
    data_dir = root / "governed-data"
    fixture_dir = root / "phase1-fixtures"
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_governed_shadow_fixture(fixture_dir)

    os.environ["AUTH_PASSWORD"] = PASSWORD
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["PHASE1_FIXTURE_MODE"] = "1"
    os.environ["PHASE1_FIXTURE_DIR"] = str(fixture_dir)
    os.environ.setdefault("ATHENA_ALLOW_NETWORK", "0")
    # Keep optional forecast unavailable without torch; shadow/thesis stay on default probes.
    os.environ.setdefault("PHASE5_REAL_HOST", "1")

    from app import optional_modules

    optional_modules.OPTIONAL_MODULE_ACTION_COLLABORATORS = _SPIES.as_mapping()
    # Force forecast probe unavailable so lifespan does not require Kronos bytes.
    optional_modules.OPTIONAL_MODULE_PROBES = {
        "shadow": lambda: optional_modules.OptionalModuleProbe.available(code="shadow_available"),
        "thesis": lambda: optional_modules.OptionalModuleProbe.available(code="thesis_available"),
        "forecast": lambda: optional_modules.OptionalModuleProbe.unavailable(
            code="forecast_dependency_missing",
            reason="forecast optional dependency is not installed",
            install_hint="enable the forecast optional deployment capability",
        ),
    }
    _install_network_guard()
    write_telemetry()

    def _cleanup() -> None:
        write_telemetry()
        if _TMP_ROOT and _TMP_ROOT.exists():
            shutil.rmtree(_TMP_ROOT, ignore_errors=True)

    atexit.register(_cleanup)
    return root


def create_app() -> Any:
    """Import production app after environment preparation and attach telemetry routes."""
    prepare_environment()
    from app.main import app

    _install_telemetry_route(app)

    # Periodic telemetry flush so Playwright teardown can read the file even if the
    # last request did not hit the telemetry endpoint.
    def _flush_loop() -> None:
        while True:
            write_telemetry()
            threading.Event().wait(1.0)

    threading.Thread(target=_flush_loop, name="phase5-telemetry-flush", daemon=True).start()
    return app


def main() -> None:
    import uvicorn

    app = create_app()
    write_telemetry()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


# Expose intentional non-use of repository bypass helper for static clarity.
__all__ = [
    "CallSpy",
    "LiveActionSpies",
    "create_app",
    "main",
    "telemetry_snapshot",
    "write_telemetry",
    "_mark_repository_id_bypass",
]


if __name__ == "__main__":
    main()
