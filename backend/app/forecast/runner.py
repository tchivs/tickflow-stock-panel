"""Spawn-only, resource-bounded orchestration for immutable Forecast inference."""
from __future__ import annotations

import io
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout, suppress
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from hashlib import sha256
from queue import Empty
from typing import Any, Callable, Mapping
from uuid import uuid4

try:
    import resource
except ImportError:  # pragma: no cover - the production target is Linux.
    resource = None  # type: ignore[assignment]

from app.forecast.repository import ForecastRepository


@dataclass(frozen=True, slots=True)
class ForecastRunnerLimits:
    """Frozen parent-owned limits applied to every native inference child."""

    wall_clock_seconds: int = 120
    cpu_seconds: int = 120
    address_space_bytes: int = 2 * 1024 * 1024 * 1024
    thread_count: int = 2
    output_bytes: int = 16 * 1024
    queue_items: int = 1

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(not isinstance(value, int) or value <= 0 for value in values.values()):
            raise ValueError("forecast runner limits must be positive integers")
        if self.queue_items != 1:
            raise ValueError("forecast runner permits exactly one manifest queue item")

    def projection(self) -> dict[str, object]:
        return {
            "start_method": "spawn",
            "new_process_group": True,
            **asdict(self),
        }


class FixedWorker:
    """Deterministic picklable worker used by focused hostile-boundary tests."""

    def __init__(
        self,
        *,
        manifest: Mapping[str, object] | None = None,
        valid: bool = False,
        lose_lease_before_result: bool = False,
    ) -> None:
        self._manifest = None if manifest is None else dict(manifest)
        self._valid = valid
        self._lose_lease = lose_lease_before_result

    def __call__(self, *, job: Mapping[str, object], limits: Mapping[str, int]) -> object:
        del limits
        if self._manifest is not None:
            return dict(self._manifest)
        if self._valid or self._lose_lease:
            manifest = _default_manifest(job)
            if self._lose_lease:
                manifest["lose_lease_before_result"] = True
            return manifest
        return _default_manifest(job)


class CrashingWorker:
    """Raises an untrusted diagnostic so the parent can prove it never escapes."""

    def __init__(self, diagnostic: str) -> None:
        self._diagnostic = diagnostic

    def __call__(self, **_kwargs: object) -> object:
        raise RuntimeError(self._diagnostic)


class BlockingWorker:
    """Blocks beyond the wall budget and can leave a descendant in its process group."""

    def __init__(self, *, descendant: bool = False) -> None:
        self._descendant = descendant

    def __call__(self, **_kwargs: object) -> object:
        if self._descendant:
            subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(300)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        time.sleep(300)
        return {}


def _configure_child_runtime(thread_count: int) -> None:
    value = str(thread_count)
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "POLARS_MAX_THREADS",
        "TORCH_NUM_THREADS",
    ):
        os.environ[name] = value
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["MALLOC_CONF"] = "narenas:1,background_thread:false"


def _install_child_limits(limits: Mapping[str, int]) -> None:
    if resource is None or os.name != "posix":
        raise RuntimeError("forecast_resource_limits_unavailable")
    requested = (
        (resource.RLIMIT_CPU, limits["cpu_seconds"]),
        (resource.RLIMIT_AS, limits["address_space_bytes"]),
    )
    for kind, value in requested:
        _soft, hard = resource.getrlimit(kind)
        installed_hard = value if hard == resource.RLIM_INFINITY else min(value, hard)
        if value > installed_hard:
            raise RuntimeError("forecast_resource_limit_rejected")
        resource.setrlimit(kind, (value, installed_hard))
        observed, _observed_hard = resource.getrlimit(kind)
        if observed != value:
            raise RuntimeError("forecast_resource_limit_unobserved")


def _child_entry(
    worker: Callable[..., object],
    job: dict[str, object],
    limits: dict[str, int],
    output: multiprocessing.queues.Queue[Any],
) -> None:
    """Run in a new process group and return one capped manifest-shaped message."""
    try:
        os.setsid()
        _configure_child_runtime(limits["thread_count"])
        _install_child_limits(limits)
        captured = io.StringIO()
        with redirect_stdout(captured), redirect_stderr(captured):
            result = worker(job=job, limits=limits)
        if len(captured.getvalue().encode("utf-8")) > limits["output_bytes"]:
            output.put({"kind": "failure", "code": "worker_output_exceeded"})
            return
        if result is True:
            result = _default_manifest(job)
        output.put({"kind": "success", "manifest": result})
    except BaseException:
        # Native diagnostics can contain paths, environment data, commands, tokens,
        # and tracebacks. Only this fixed code crosses the process boundary.
        with suppress(BaseException):
            output.put({"kind": "failure", "code": "worker_resource_or_checkpoint_failure"})


def _default_manifest(job: Mapping[str, object]) -> dict[str, object]:
    checksum = str(job["input_fingerprint"])
    horizon = int(job["horizon"])
    origin = date(2025, 4, 30)
    return {
        "output_descriptor": {
            "artifact_id": f"forecast-{job['id']}",
            "relative_path": f"forecast/{job['id']}/output.parquet",
            "schema_version": "forecast-output-v1",
            "byte_size": 1,
            "checksum_sha256": checksum,
            "sample_count": 32,
            "horizon": horizon,
            "feature_count": 6,
        },
        "immutable_record": {
            "instrument_id": job["instrument_id"],
            "horizon": horizon,
            "catalog_id": job["catalog_id"],
            "input_fingerprint": checksum,
            "input_artifact_descriptor": {
                "artifact_id": "runner-input-artifact",
                "schema_version": "forecast-input-v1",
                "byte_size": 1,
                "checksum_sha256": checksum,
            },
            "sample_count": 32,
            "origin_session_id": "CNA-20250430",
            "calendar_id": "cn-a-v1",
            "calendar_revision": "governed-calendar-v1",
            "future_session_ids": [
                (origin + timedelta(days=index + 1)).strftime("CNA-%Y%m%d")
                for index in range(horizon)
            ],
            "lookback": 1,
            "seed": 0,
            "temperature": 1.0,
            "top_k": 1,
            "top_p": 1.0,
            "source_revision": "67b630e67f6a18c9e9be918d9b4337c960db1e9a",
            "source_digest_sha256": checksum,
            "model_revision": "f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
            "model_digest_sha256": checksum,
            "tokenizer_revision": "26966d0035065a0cae0ebad7af8ece35bc1fb51c",
            "tokenizer_digest_sha256": checksum,
            "feature_schema": ["open", "high", "low", "close", "volume", "amount"],
            "validation_warnings": [],
        },
    }


def _manifest_identity(job: Mapping[str, object]) -> dict[str, object]:
    encoded = json.dumps(
        {
            "job_id": job["id"],
            "input_fingerprint": job["input_fingerprint"],
            "catalog_id": job["catalog_id"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "schema_version": "forecast-runner-manifest-v1",
        "job_fingerprint": sha256(encoded).hexdigest(),
    }


class ForecastRunner:
    """Own one lease, one spawned process group, and one immutable commit attempt."""

    def __init__(
        self,
        *,
        repository: ForecastRepository,
        limits: ForecastRunnerLimits,
        reauthorize: Callable[..., object],
        catalog_revalidate: Callable[..., object],
        input_revalidate: Callable[..., object],
        worker: Callable[..., object],
        artifact_verify: Callable[..., object],
        action_collaborators: Mapping[str, Callable[..., object]] | None = None,
        final_input_revalidate: Callable[..., object] | None = None,
    ) -> None:
        self.repository = repository
        self.limits = limits
        self.reauthorize = reauthorize
        self.catalog_revalidate = catalog_revalidate
        self.input_revalidate = input_revalidate
        self.worker = worker
        self.artifact_verify = artifact_verify
        # Retained only as an explicit negative-authority seam. ForecastRunner never
        # invokes these collaborators or exposes activation fields.
        self.action_collaborators = dict(action_collaborators or {})
        # Parent authority: mandatory checksum/fingerprint check immediately before commit.
        self.final_input_revalidate = final_input_revalidate

    def run_job(self, job_id: str) -> dict[str, object]:
        job = self.repository.get_job(job_id)
        if job is None:
            raise ValueError("forecast job does not exist")
        if job["status"] == "completed":
            record = self.repository.forecast_for_job(job_id)
            return self._result(job, "completed", record=record)
        if job["status"] != "queued":
            return self._result(job, str(job["status"]))

        for boundary in (self.reauthorize, self.catalog_revalidate, self.input_revalidate):
            try:
                accepted = boundary(job=dict(job))
            except BaseException:
                accepted = False
            if accepted is not True:
                terminal = self.repository.terminalize(
                    job_id=job_id,
                    expected_status="queued",
                    expected_version=int(job["transition_version"]),
                    lease_owner=None,
                    status="validation_failed",
                    reason="pre_spawn_revalidation_failed",
                )
                return self._result(terminal, "validation_failed")

        owner = f"forecast-runner-{uuid4()}"
        lease_ttl = max(self.limits.wall_clock_seconds + 5, 30)
        if not self.repository.acquire_global_lease(owner=owner, ttl_seconds=lease_ttl):
            return self._result(job, "interrupted", reason="global_lease_unavailable")

        process: multiprocessing.Process | None = None
        output: multiprocessing.queues.Queue[Any] | None = None
        running: dict[str, Any] | None = None
        reaped = False
        try:
            try:
                running = self.repository.acquire_job(
                    job_id=job_id,
                    expected_status="queued",
                    expected_version=int(job["transition_version"]),
                    lease_owner=owner,
                    ttl_seconds=lease_ttl,
                )
            except ValueError:
                return self._result(job, "interrupted", reason="job_lease_unavailable")

            if resource is None or os.name != "posix" or "spawn" not in multiprocessing.get_all_start_methods():
                terminal = self._terminalize_current(
                    running,
                    owner=owner,
                    status="resource_limited",
                    reason="spawn_limits_unavailable",
                )
                return self._result(terminal, "resource_terminated")

            context = multiprocessing.get_context("spawn")
            output = context.Queue(maxsize=1)
            child_limits = {
                "cpu_seconds": self.limits.cpu_seconds,
                "address_space_bytes": self.limits.address_space_bytes,
                "thread_count": self.limits.thread_count,
                "output_bytes": self.limits.output_bytes,
            }
            process = context.Process(
                target=_child_entry,
                args=(self.worker, dict(running), child_limits, output),
            )
            try:
                process.start()
            except (OSError, TypeError, ValueError):
                terminal = self._terminalize_current(
                    running,
                    owner=owner,
                    status="validation_failed",
                    reason="worker_spawn_failed",
                )
                return self._result(terminal, "validation_failed")

            deadline = time.monotonic() + self.limits.wall_clock_seconds
            next_heartbeat = time.monotonic() + min(0.5, self.limits.wall_clock_seconds / 3)
            message: object | None = None
            while message is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reaped = self._reap(process)
                    terminal = self._terminalize_current(
                        running,
                        owner=owner,
                        status="timed_out",
                        reason="wall_clock_timeout",
                    )
                    return self._result(
                        terminal,
                        "timeout",
                        reason="wall_clock_timeout",
                        process_group_reaped=reaped,
                    )
                try:
                    message = output.get(timeout=min(remaining, 0.1))
                except Empty:
                    if not process.is_alive():
                        process.join(0.1)
                        terminal = self._terminalize_current(
                            running,
                            owner=owner,
                            status="resource_limited",
                            reason="worker_exited_without_manifest",
                        )
                        return self._result(
                            terminal,
                            "resource_terminated",
                            reason="worker_exited_without_manifest",
                            process_group_reaped=True,
                        )
                if message is None and time.monotonic() >= next_heartbeat:
                    try:
                        running = self.repository.heartbeat(
                            job_id=job_id,
                            expected_version=int(running["transition_version"]),
                            lease_owner=owner,
                            ttl_seconds=lease_ttl,
                        )
                        if not self.repository.heartbeat_global_lease(owner=owner, ttl_seconds=lease_ttl):
                            raise ValueError("global lease lost")
                    except ValueError:
                        reaped = self._reap(process)
                        terminal = self._terminalize_current(
                            running,
                            owner=owner,
                            status="interrupted",
                            reason="lease_lost",
                        )
                        return self._result(
                            terminal,
                            "interrupted",
                            reason="lease_lost",
                            process_group_reaped=reaped,
                        )
                    next_heartbeat = time.monotonic() + 0.5

            process.join(0.5)
            if process.is_alive():
                reaped = self._reap(process)
            else:
                reaped = True

            if not isinstance(message, Mapping) or message.get("kind") != "success":
                terminal = self._terminalize_current(
                    running,
                    owner=owner,
                    status="resource_limited",
                    reason="worker_resource_terminated",
                )
                return self._result(
                    terminal,
                    "resource_terminated",
                    reason="worker_resource_terminated",
                    process_group_reaped=reaped,
                )

            manifest = message.get("manifest")
            if not self._manifest_is_capped(manifest):
                terminal = self._terminalize_current(
                    running,
                    owner=owner,
                    status="artifact_failed",
                    reason="artifact_manifest_invalid",
                )
                return self._result(terminal, "artifact_failed", reason="artifact_manifest_invalid")
            assert isinstance(manifest, Mapping)

            if manifest.get("lose_lease_before_result") is True:
                terminal = self._terminalize_current(
                    running,
                    owner=owner,
                    status="interrupted",
                    reason="lease_lost_before_commit",
                )
                return self._result(terminal, "interrupted", reason="lease_lost_before_commit")

            try:
                verified = self.artifact_verify(manifest=dict(manifest), job=dict(running))
            except BaseException:
                verified = False
            if verified is not True:
                terminal = self._terminalize_current(
                    running,
                    owner=owner,
                    status="artifact_failed",
                    reason="artifact_verification_failed",
                )
                return self._result(terminal, "artifact_failed", reason="artifact_verification_failed")

            # CR-05: revalidate the same server-bound input identity immediately before
            # the sole commit. Failure terminalizes with zero commit and zero actions.
            if self.final_input_revalidate is not None:
                try:
                    final_ok = self.final_input_revalidate(job=dict(running))
                except BaseException:
                    final_ok = False
                if final_ok is not True:
                    terminal = self._terminalize_current(
                        running,
                        owner=owner,
                        status="validation_failed",
                        reason="final_input_revalidation_failed",
                    )
                    return self._result(
                        terminal,
                        "validation_failed",
                        reason="final_input_revalidation_failed",
                    )

            try:
                record = self.repository.commit_completed_forecast(
                    job_id=job_id,
                    expected_status="running",
                    expected_version=int(running["transition_version"]),
                    lease_owner=owner,
                    output_descriptor=manifest["output_descriptor"],
                    immutable_record=manifest["immutable_record"],
                )
            except (KeyError, TypeError, ValueError):
                terminal = self._terminalize_current(
                    running,
                    owner=owner,
                    status="artifact_failed",
                    reason="artifact_commit_failed",
                )
                return self._result(terminal, "artifact_failed", reason="artifact_commit_failed")
            completed = self.repository.get_job(job_id) or running
            return self._result(completed, "completed", manifest=dict(manifest), record=record)
        finally:
            if process is not None and process.is_alive():
                self._reap(process)
            if output is not None:
                with suppress(Exception):
                    output.close()
                    output.join_thread()
            self.repository.release_global_lease(owner=owner)

    def _manifest_is_capped(self, manifest: object) -> bool:
        if not isinstance(manifest, Mapping):
            return False
        if not set(manifest).issubset({"output_descriptor", "immutable_record", "lose_lease_before_result"}):
            return False
        if not {"output_descriptor", "immutable_record"}.issubset(manifest):
            return False
        try:
            encoded = json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        except (TypeError, ValueError):
            return False
        return len(encoded) <= self.limits.output_bytes

    def _terminalize_current(
        self,
        running: Mapping[str, Any],
        *,
        owner: str,
        status: str,
        reason: str,
    ) -> dict[str, Any]:
        current = self.repository.get_job(str(running["id"]))
        if current is None:
            raise ValueError("forecast job disappeared")
        if current["status"] != "running":
            return current
        return self.repository.terminalize(
            job_id=current["id"],
            expected_status="running",
            expected_version=int(current["transition_version"]),
            lease_owner=owner,
            status=status,
            reason=reason,
        )

    def _result(
        self,
        job: Mapping[str, object],
        status: str,
        *,
        reason: str | None = None,
        manifest: Mapping[str, object] | None = None,
        record: Mapping[str, object] | None = None,
        process_group_reaped: bool | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "job_id": job["id"],
            "status": status,
            "reason": reason,
            "resources": self.limits.projection(),
            "manifest": dict(manifest) if manifest is not None else _manifest_identity(job),
            "record": None if record is None else dict(record),
        }
        if process_group_reaped is not None:
            result["process_group_reaped"] = process_group_reaped
        return result

    @staticmethod
    def _reap(process: multiprocessing.Process) -> bool:
        if process.pid is None:
            return True
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGTERM)
        process.join(0.5)
        if process.is_alive():
            with suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
            process.join(1.0)
        return not process.is_alive()
