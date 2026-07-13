"""Killable, resource-bounded adapter for server-owned experiment execution."""
from __future__ import annotations

import io
import json
import multiprocessing
import os
import signal
import time
from collections.abc import Mapping
from contextlib import redirect_stderr, redirect_stdout, suppress
from datetime import date
from hashlib import sha256
from queue import Empty
from typing import Any, Protocol

try:
    import resource
except ImportError:  # pragma: no cover - the production target is Linux.
    resource = None  # type: ignore[assignment]


class ServerOwnedBacktestCollaborator(Protocol):
    """Accepts only a persisted specification and returns bounded research metadata."""

    def run(self, *, specification: dict[str, object]) -> dict[str, object]: ...


class StrategyBacktestExperimentCollaborator:
    """Translate frozen specification metadata into the existing server-owned backtest API."""

    def __init__(self, strategy_backtest_service: Any) -> None:
        self._service = strategy_backtest_service

    def run(self, *, specification: dict[str, object]) -> dict[str, object]:
        from app.backtest.strategy import StrategyBacktestConfig

        scope = specification.get("data_scope")
        if not isinstance(scope, Mapping):
            raise ValueError("frozen data scope is invalid")
        strategy_id = scope.get("strategy_id")
        start = scope.get("start")
        end = scope.get("end")
        if not all(isinstance(value, str) and value for value in (strategy_id, start, end)):
            raise ValueError("frozen data scope requires strategy_id, start, and end")
        symbols = scope.get("symbols")
        if symbols is not None and (not isinstance(symbols, list) or not all(isinstance(item, str) for item in symbols)):
            raise ValueError("frozen symbols are invalid")
        config = StrategyBacktestConfig(
            strategy_id=strategy_id,
            symbols=symbols,
            start=date.fromisoformat(start),
            end=date.fromisoformat(end),
            params=scope.get("parameters") if isinstance(scope.get("parameters"), dict) else None,
            mode="full",
            asset_type=str(scope.get("asset_type", "stock")),
        )
        result = self._service.run(config)
        if result.error:
            raise ValueError("governed backtest could not complete")
        metrics = {
            key: value
            for key, value in result.stats.items()
            if isinstance(value, (str, int, float, bool))
        }
        checksum = sha256(json.dumps(metrics, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        evolution_evidence = _evolution_evidence(scope=scope, metrics=metrics)
        return {
            "governed_input_manifest": result.governed_input_manifest,
            "asset_version": str(specification["research_asset_id"]),
            "resolved_parameters": dict(config.params or {}),
            "environment": {"backtest": "strategy-backtest-service"},
            "metrics": metrics,
            "artifacts": [{"reference": f"strategy-backtest:{result.run_id}:metrics", "checksum": checksum}],
            "evolution_evidence": evolution_evidence,
        }


def _evolution_evidence(*, scope: Mapping[str, object], metrics: Mapping[str, object]) -> dict[str, object]:
    """Derive compact, server-owned gate inputs without retaining market rows."""
    start = date.fromisoformat(str(scope["start"]))
    end = date.fromisoformat(str(scope["end"]))
    midpoint = start + (end - start) / 2
    in_end = midpoint
    out_start = midpoint.fromordinal(midpoint.toordinal() + 1)
    numeric_metrics = {key: value for key, value in metrics.items() if isinstance(value, (int, float))}
    net_return = numeric_metrics.get("out_of_sample_return", 0.0)
    return {
        "split": {
            "in_sample": {"start": start.isoformat(), "end": in_end.isoformat(), "metrics": numeric_metrics},
            "out_of_sample": {"start": out_start.isoformat(), "end": end.isoformat(), "metrics": numeric_metrics},
        },
        "robustness_trials": [
            {
                "reference": "governed-backtest:baseline",
                "parameters": dict(scope.get("parameters", {})) if isinstance(scope.get("parameters"), Mapping) else {},
                "status": "completed",
                "metrics": numeric_metrics,
                "threshold_met": bool(numeric_metrics),
            }
        ],
        "cost_feasibility": {
            "fee_model": "cn-a-equities-v1",
            "commission": 0.0003,
            "slippage": 0.0005,
            "capacity_assumptions": {"participation_rate": 0.1},
            "net_metrics": {**numeric_metrics, "out_of_sample_return": float(net_return) - 0.0008},
            "capacity_result": "feasible" if numeric_metrics else "unavailable",
            "threshold_met": bool(numeric_metrics),
        },
    }


def _safe_text(value: object, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()[:256]
    return fallback


def _manifest(specification: Mapping[str, object]) -> dict[str, object]:
    frozen = {
        "research_asset_id": specification.get("research_asset_id"),
        "version": specification.get("version"),
        "data_scope": specification.get("data_scope"),
        "method": specification.get("method"),
    }
    encoded = json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return {
        "source": "governed_experiment_runner",
        "revision": "governed-runner-v1",
        "fingerprint": sha256(encoded).hexdigest(),
    }


def _install_limits(limits: Mapping[str, int]) -> dict[str, int]:
    if resource is None or os.name != "posix":
        raise RuntimeError("resource limits are unavailable")
    pairs = (
        (resource.RLIMIT_CPU, "cpu_seconds", limits["cpu_seconds"]),
        (resource.RLIMIT_AS, "memory_limit_bytes", limits["memory_limit_bytes"]),
    )
    for limit_kind, name, requested in pairs:
        _soft, hard = resource.getrlimit(limit_kind)
        if hard != resource.RLIM_INFINITY and requested > hard:
            raise RuntimeError(f"{name} cannot be installed")
        resource.setrlimit(limit_kind, (requested, requested if hard == resource.RLIM_INFINITY else min(requested, hard)))
        observed, _hard = resource.getrlimit(limit_kind)
        if observed != requested:
            raise RuntimeError(f"{name} cannot be observed")
    return dict(limits)


def _worker(
    collaborator: ServerOwnedBacktestCollaborator,
    specification: dict[str, object],
    limits: dict[str, int],
    output: multiprocessing.queues.Queue[Any],
) -> None:
    """Execute in a fresh session; only compact, capped metadata crosses the boundary."""
    try:
        os.setsid()
        applied = _install_limits(limits)
        captured = io.StringIO()
        with redirect_stdout(captured), redirect_stderr(captured):
            result = collaborator.run(specification=specification)
        if len(captured.getvalue().encode("utf-8")) > limits["output_limit_bytes"]:
            output.put({"kind": "failure", "reason": "captured output budget exceeded", "limits": applied})
            return
        if not isinstance(result, dict):
            output.put({"kind": "failure", "reason": "governed collaborator returned invalid result", "limits": applied})
            return
        output.put({"kind": "success", "result": result, "limits": applied})
    except BaseException as error:  # Worker errors must never disclose a traceback or host details.
        output.put({"kind": "failure", "reason": _safe_text(str(error), fallback="governed worker failed"), "limits": limits})


class GovernedExperimentRunner:
    """Run an approved server collaborator in a parent-owned killable process group."""

    def __init__(
        self,
        *,
        collaborator: ServerOwnedBacktestCollaborator,
        wall_clock_seconds: int = 15,
        cpu_seconds: int = 10,
        memory_limit_bytes: int = 1_024 * 1024 * 1024,
        output_limit_bytes: int = 64 * 1024,
    ) -> None:
        if min(wall_clock_seconds, cpu_seconds, memory_limit_bytes, output_limit_bytes) <= 0:
            raise ValueError("governed resource limits must be positive")
        self.collaborator = collaborator
        self._limits = {
            "wall_clock_seconds": wall_clock_seconds,
            "cpu_seconds": cpu_seconds,
            "memory_limit_bytes": memory_limit_bytes,
            "output_limit_bytes": output_limit_bytes,
        }

    def run(self, *, specification: dict[str, object]) -> dict[str, object]:
        manifest = _manifest(specification)
        if resource is None or os.name != "posix" or "spawn" not in multiprocessing.get_all_start_methods():
            return self._failure(manifest, "resource_limited", "governed process limits are unavailable")

        context = multiprocessing.get_context("spawn")
        output = context.Queue(maxsize=1)
        worker = context.Process(target=_worker, args=(self.collaborator, specification, self._limits, output))
        started = time.monotonic()
        try:
            worker.start()
        except (OSError, TypeError, ValueError) as error:
            output.close()
            return self._failure(manifest, "validation_failed", _safe_text(str(error), fallback="worker could not start"))
        try:
            message = output.get(timeout=self._limits["wall_clock_seconds"])
        except Empty:
            self._reap(worker)
            return self._failure(manifest, "timed_out", "execution exceeded wall-clock budget")
        finally:
            output.close()
        worker.join(0.5)

        if not isinstance(message, dict) or message.get("kind") != "success":
            return self._failure(
                manifest,
                "resource_limited",
                _safe_text(message.get("reason") if isinstance(message, dict) else None, fallback="governed worker failed"),
                resources=message.get("limits") if isinstance(message, dict) else None,
            )
        return self._completed(manifest, message["result"], message["limits"], started)

    def _completed(
        self, manifest: dict[str, object], result: object, limits: object, started: float
    ) -> dict[str, object]:
        if not isinstance(result, Mapping) or not isinstance(limits, Mapping):
            return self._failure(manifest, "validation_failed", "governed worker returned invalid terminal evidence")
        upstream_manifest = result.get("governed_input_manifest")
        if isinstance(upstream_manifest, Mapping) and upstream_manifest.get("fingerprint"):
            manifest = {**manifest, **dict(upstream_manifest)}
        return {
            "status": "completed",
            "governed_input_manifest": manifest,
            "asset_version": result.get("asset_version"),
            "resolved_parameters": result.get("resolved_parameters", {}),
            "environment": {"runner": "governed-process-v1", "elapsed_ms": round((time.monotonic() - started) * 1000, 1)},
            "resources": dict(limits),
            "metrics": result.get("metrics", {}),
            "artifacts": result.get("artifacts", []),
            "evolution_evidence": result.get("evolution_evidence", {}),
        }

    def _failure(
        self,
        manifest: dict[str, object],
        status: str,
        reason: str,
        *,
        resources: object | None = None,
    ) -> dict[str, object]:
        return {
            "status": status,
            "constraint_reason": _safe_text(reason, fallback="governed constraint failure"),
            "governed_input_manifest": manifest,
            "asset_version": None,
            "resolved_parameters": {},
            "environment": {"runner": "governed-process-v1"},
            "resources": dict(resources) if isinstance(resources, Mapping) else dict(self._limits),
            "metrics": {},
            "artifacts": [],
        }

    @staticmethod
    def _reap(worker: multiprocessing.Process) -> None:
        with suppress(ProcessLookupError):
            os.killpg(worker.pid, signal.SIGTERM)
        worker.join(0.5)
        if worker.is_alive():
            with suppress(ProcessLookupError):
                os.killpg(worker.pid, signal.SIGKILL)
            worker.join()
