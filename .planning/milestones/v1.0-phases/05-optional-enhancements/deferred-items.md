# Deferred Items

## 2026-07-27 — Plan 05-42

- `backend/tests/test_phase5_foundation.py::test_artifact_bytes_are_atomic_root_contained_and_descriptor_verified` assumes POSIX mode-bit reporting (`0o700`) on Windows, where `Path.stat()` reports `0o777`. The plan-owned Windows optional-host verification is green; make this permission assertion platform-aware in a future foundation-test maintenance task.

## 2026-07-27 — Plan 05-43

- The configured Windows host has no usable WSL distribution: `wsl.exe wslpath` and `wsl.exe --list --verbose` return exit code 1 with installation help. The explicit `linux_process_group` suite remains unrun here and must be executed on WSL/Linux before ship.
- The optional-host suite reports pre-existing Polars deprecation/sortedness warnings from `backend/app/indicators/pipeline.py`; they are outside this plan's shutdown, retry, and interpreter scope.
