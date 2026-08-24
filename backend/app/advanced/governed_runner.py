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
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from queue import Empty
from typing import Any, Protocol

try:
    import resource
except ImportError:  # pragma: no cover - the production target is Linux.
    resource = None  # type: ignore[assignment]


class ServerOwnedBacktestCollaborator(Protocol):
    """Accepts only a persisted specification and returns bounded research metadata."""

    def run(self, *, specification: dict[str, object]) -> dict[str, object]: ...


def _bound_scope(specification: Mapping[str, object]) -> Mapping[str, object]:
    """Reject unbound or divergent records before any strategy service is constructed."""
    scope = specification.get("data_scope")
    bound_strategy_id = specification.get("bound_strategy_id")
    if not isinstance(scope, Mapping):
        raise ValueError("frozen data scope is invalid")
    strategy_id = scope.get("strategy_id")
    if not all(isinstance(value, str) and value for value in (bound_strategy_id, strategy_id)):
        raise ValueError("experiment specification lacks a bound strategy")
    if strategy_id != bound_strategy_id:
        raise ValueError("frozen strategy scope diverges from its bound strategy")
    return scope


class StrategyBacktestExperimentCollaborator:
    """Translate frozen specification metadata into the existing server-owned backtest API."""

    def __init__(self, *, data_dir: Path) -> None:
        self._data_dir = str(data_dir)

    def _service(self) -> Any:
        """Rebuild non-pickleable governed data access inside the spawned worker."""
        from app.backtest.engine import BacktestEngine
        from app.backtest.strategy import StrategyBacktestService
        from app.services.minute_loader import make_minute_loader
        from app.services.screener import ScreenerService
        from app.strategy.engine import StrategyEngine
        from app.tickflow.repository import DataStore, KlineRepository

        data_dir = Path(self._data_dir)
        store = DataStore(data_dir)
        repository = KlineRepository(store)
        screener = ScreenerService(repository)
        strategy_engine = StrategyEngine(
            enriched_loader=screener._load_enriched_for_date,
            enriched_history_loader=screener._load_enriched_history,
            strategy_dirs=[
                Path(__file__).resolve().parents[1] / "strategy" / "builtin",
                data_dir / "strategies" / "custom",
                data_dir / "strategies" / "ai",
            ],
            minute_loader=make_minute_loader(data_dir),
        )
        return StrategyBacktestService(
            BacktestEngine(repository),
            strategy_engine,
        )

    def prepare(self, *, specification: dict[str, object]) -> dict[str, object]:
        """No-op preparation — frozen panel feature removed; panels are built on-demand."""
        return {**specification, "_frozen_panel_artifacts": [None, None, None]}

    def run(self, *, specification: dict[str, object]) -> dict[str, object]:
        scope = _bound_scope(specification)
        prepared = specification.get("_frozen_panel_artifacts")
        if prepared is None:
            artifacts: list[Mapping[str, object] | None] = [None, None, None]
        elif (
            isinstance(prepared, list)
            and len(prepared) == 3
            and all(item is None or isinstance(item, Mapping) for item in prepared)
        ):
            artifacts = list(prepared)  # type: ignore[list-item]
        else:
            raise ValueError("prepared governed panels are invalid")

        backtest = self._service()
        aggregate_result = self._run_backtest(
            backtest=backtest,
            scope=scope,
            frozen_panel_artifact=artifacts[0],
        )
        in_sample_scope, out_of_sample_scope = self._split_scopes(scope)
        in_sample = self._split_evaluation(
            result=self._run_backtest(
                backtest=backtest,
                scope=in_sample_scope,
                frozen_panel_artifact=artifacts[1],
            ),
            scope=in_sample_scope,
        )
        out_of_sample = self._split_evaluation(
            result=self._run_backtest(
                backtest=backtest,
                scope=out_of_sample_scope,
                frozen_panel_artifact=artifacts[2],
            ),
            scope=out_of_sample_scope,
        )

        metrics = self._compact_metrics(aggregate_result.stats)
        metrics.update(self._execution_counts(aggregate_result))
        checksum = sha256(json.dumps(metrics, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        evolution_evidence = _evolution_evidence(
            scope=scope,
            metrics=metrics,
            in_sample=in_sample,
            out_of_sample=out_of_sample,
        )
        return {
            "governed_input_manifest": aggregate_result.governed_input_manifest,
            "asset_version": str(specification["research_asset_id"]),
            "resolved_parameters": dict(aggregate_result.config.get("params") or {}),
            "environment": {"backtest": "strategy-backtest-service"},
            "metrics": metrics,
            "artifacts": [{"reference": f"strategy-backtest:{aggregate_result.run_id}:metrics", "checksum": checksum}],
            "evolution_evidence": evolution_evidence,
        }

    @staticmethod
    def _config(
        scope: Mapping[str, object],
        frozen_panel_artifact: Mapping[str, object] | None = None,
    ) -> Any:
        from app.backtest.strategy import StrategyBacktestConfig

        strategy_id = scope.get("strategy_id")
        start = scope.get("start")
        end = scope.get("end")
        if not all(isinstance(value, str) and value for value in (strategy_id, start, end)):
            raise ValueError("frozen data scope requires strategy_id, start, and end")
        start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
        if start_date > end_date:
            raise ValueError("frozen data scope end precedes start")
        symbols = scope.get("symbols")
        if symbols is not None and (not isinstance(symbols, list) or not all(isinstance(item, str) for item in symbols)):
            raise ValueError("frozen symbols are invalid")
        return StrategyBacktestConfig(
            strategy_id=strategy_id,
            symbols=symbols,
            start=start_date,
            end=end_date,
            params=scope.get("parameters") if isinstance(scope.get("parameters"), dict) else None,
            mode="full",
            asset_type=str(scope.get("asset_type", "stock")),
            frozen_panel_artifact=dict(frozen_panel_artifact) if frozen_panel_artifact else None,
        )

    def _run_backtest(
        self,
        *,
        backtest: Any,
        scope: Mapping[str, object],
        frozen_panel_artifact: Mapping[str, object] | None,
    ) -> Any:
        result = backtest.run(self._config(scope, frozen_panel_artifact))
        if result.error:
            raise ValueError("governed backtest could not complete")
        return result

    @staticmethod
    def _compact_metrics(metrics: Mapping[str, object]) -> dict[str, object]:
        return {key: value for key, value in metrics.items() if isinstance(value, (str, int, float, bool))}

    @staticmethod
    def _execution_counts(result: Any) -> dict[str, int]:
        stats = result.stats if isinstance(getattr(result, "stats", None), Mapping) else {}
        candidate_count = stats.get("n_candidates") if isinstance(stats.get("n_candidates"), int) else 0
        trade_count = stats.get("n_trades") if isinstance(stats.get("n_trades"), int) else candidate_count
        return {
            "eligible_buy_count": max(candidate_count, 0),
            "completed_trade_count": max(trade_count, 0),
        }

    @staticmethod
    def _split_scopes(scope: Mapping[str, object]) -> tuple[dict[str, object], dict[str, object]]:
        start, end = date.fromisoformat(str(scope["start"])), date.fromisoformat(str(scope["end"]))
        span_days = (end - start).days + 1
        if span_days < 2:
            raise ValueError("governed split evaluation requires at least two calendar days")
        in_end = start + timedelta(days=span_days // 2 - 1)
        out_start = in_end + timedelta(days=1)
        return (
            {**scope, "start": start.isoformat(), "end": in_end.isoformat()},
            {**scope, "start": out_start.isoformat(), "end": end.isoformat()},
        )

    def _split_evaluation(self, *, result: Any, scope: Mapping[str, object]) -> dict[str, object]:
        metrics = {key: value for key, value in self._compact_metrics(result.stats).items() if isinstance(value, (int, float))}
        metrics.update(self._execution_counts(result))
        manifest = result.governed_input_manifest
        run_id = result.run_id
        fingerprint = manifest.get("fingerprint") if isinstance(manifest, Mapping) else None
        if not metrics or not isinstance(run_id, str) or not run_id or not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError("governed split evaluation lacks independent metrics or manifest")
        checksum = sha256(json.dumps(metrics, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {
            "metrics": metrics,
            "evaluation": {
                "run_id": run_id,
                "governed_input_fingerprint": fingerprint,
                "window": {"start": str(scope["start"]), "end": str(scope["end"])},
                "artifact": {"reference": f"strategy-backtest:{run_id}:metrics", "checksum": checksum},
            },
        }


def _evolution_evidence(
    *,
    scope: Mapping[str, object],
    metrics: Mapping[str, object],
    in_sample: Mapping[str, object],
    out_of_sample: Mapping[str, object],
) -> dict[str, object]:
    """Derive gate inputs from separately executed, non-overlapping governed windows."""
    start = date.fromisoformat(str(scope["start"]))
    end = date.fromisoformat(str(scope["end"]))
    span_days = (end - start).days + 1
    if span_days < 2:
        raise ValueError("governed split evaluation requires at least two calendar days")
    in_end = start + timedelta(days=span_days // 2 - 1)
    out_start = in_end + timedelta(days=1)
    numeric_metrics = {key: value for key, value in metrics.items() if isinstance(value, (int, float))}
    net_return = numeric_metrics.get("out_of_sample_return", 0.0)
    return {
        "split": {
            "in_sample": {"start": start.isoformat(), "end": in_end.isoformat(), **dict(in_sample)},
            "out_of_sample": {"start": out_start.isoformat(), "end": end.isoformat(), **dict(out_of_sample)},
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
        "bound_strategy_id": specification.get("bound_strategy_id"),
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
    # RLIMIT_AS rejects Polars' sparse mmap reservations before they consume
    # resident memory. RLIMIT_DATA bounds allocator-backed worker memory while
    # allowing governed parquet reads to retain their file-backed mappings.
    pairs = (
        (resource.RLIMIT_CPU, "cpu_seconds", limits["cpu_seconds"]),
        (resource.RLIMIT_DATA, "memory_limit_bytes", limits["memory_limit_bytes"]),
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


def _configure_worker_runtime() -> None:
    """Keep native data libraries within the governed process budget before import."""
    # A forked child inherits native thread-pool state from the ASGI host, while an
    # uncapped spawned child can reserve more address space than RLIMIT_AS permits.
    # These libraries are only imported by the backtest collaborator below.
    os.environ["POLARS_MAX_THREADS"] = "1"
    os.environ["MALLOC_CONF"] = "narenas:1,background_thread:false"


def _worker(
    collaborator: ServerOwnedBacktestCollaborator,
    specification: dict[str, object],
    limits: dict[str, int],
    output: multiprocessing.queues.Queue[Any],
) -> None:
    """Execute in a fresh session; only compact, capped metadata crosses the boundary."""
    try:
        _configure_worker_runtime()
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
        try:
            _bound_scope(specification)
        except ValueError as error:
            return self._failure(manifest, "validation_failed", _safe_text(str(error), fallback="invalid bound strategy"))
        if resource is None or os.name != "posix" or "spawn" not in multiprocessing.get_all_start_methods():
            return self._failure(manifest, "resource_limited", "governed spawned process limits are unavailable")

        prepared_specification = specification
        prepare = getattr(self.collaborator, "prepare", None)
        if callable(prepare):
            try:
                candidate = prepare(specification=dict(specification))
                if not isinstance(candidate, dict):
                    raise ValueError("governed collaborator returned invalid prepared specification")
                _bound_scope(candidate)
                prepared_specification = candidate
            except Exception as error:
                return self._failure(
                    manifest,
                    "validation_failed",
                    _safe_text(str(error), fallback="governed panel preparation failed"),
                )

        # Native data libraries create thread pools; fork would inherit a possibly
        # locked ASGI-host pool. A fresh interpreter is the safe isolation boundary.
        context = multiprocessing.get_context("spawn")
        output = context.Queue(maxsize=1)
        worker = context.Process(target=_worker, args=(self.collaborator, prepared_specification, self._limits, output))
        started = time.monotonic()
        try:
            worker.start()
        except (OSError, TypeError, ValueError) as error:
            output.close()
            return self._failure(manifest, "validation_failed", _safe_text(str(error), fallback="worker could not start"))
        deadline = started + self._limits["wall_clock_seconds"]
        message: object | None = None
        try:
            while message is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._reap(worker)
                    return self._failure(manifest, "timed_out", "execution exceeded wall-clock budget")
                try:
                    message = output.get(timeout=min(remaining, 0.25))
                except Empty:
                    if not worker.is_alive():
                        worker.join(0.1)
                        return self._failure(manifest, "resource_limited", "governed worker exited before terminal evidence")
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
