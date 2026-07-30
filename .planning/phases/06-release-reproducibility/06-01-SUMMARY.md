---
phase: 06-release-reproducibility
plan: 01
status: complete
requirements_completed: [REL-01]
commit: pending
---

# 06-01 SUMMARY: Release Reproducibility Root-Cause Fixes

## What Changed

Four root causes that made v1.0 release evidence irreproducible were fixed:

### 1. Archival-layout-independent path resolution (BLOCKER 0)
The v1.0 milestone archival moved `.planning/phases/05-optional-enhancements/` → `.planning/milestones/v1.0-phases/05-optional-enhancements/`, but no code was updated. Added `_find_phase05_dir()` to `verify_phase5_final_gate.py` that dynamically resolves the Phase 05 directory by searching archived milestone layouts first, then falling back to active phases. All hardcoded paths in the gate script, its tests, and `sync_kronos.py` now use dynamic resolution.

### 2. Supply-approval gate decoupled from historical paperwork
Removed `_require_complete_approval()` and `APPROVAL_SUMMARY` from `sync_kronos.py`. This function required reading a specific `05-01-SUMMARY.md` approval record that (a) moved during archival and (b) contradicts STATE.md's decision that supply is fail-closed on identity/SHA-256, not on approval paperwork. All SHA-256, config-digest, and weight-digest fail-closed checks are preserved unchanged.

### 3. POSIX process-tree test mock fixed
Fixed `fake_killpg` in `test_phase5_final_gate.py` to (a) handle signal 0 (process-existence probe) without crashing on `signal.Signals(0)`, (b) simulate process group disappearance after SIGKILL by raising `ProcessLookupError`, and (c) use platform-aware termination assertions.

### 4. Linux evidence producer local-first (Task 2)
The Linux producer always prefixed its argv with `wsl.exe`, making it fail on native Linux. Added platform detection in `orchestrate()`: on native Linux the producer runs directly (cwd=backend, no WSL wrapper); on Windows it uses WSL as before; on Windows-without-WSL it prints a clear actionable error guiding the operator to install WSL or use `--github-run-id`. The `--github-run-id` CI download path is documented as optional in CLI help. Added `test_producer_specs_linux_native_runs_directly_without_wsl` to verify the native path.

## Before/After Test Counts

| Module | Before | After |
|--------|--------|-------|
| test_phase5_final_gate.py | 5 failed (4 path-drift + 1 signal) | 0 failed |
| test_kronos_vendor_sync.py | 5 failed (approval gate) | 0 failed |
| test_phase5_optional_dependencies.py | 2 failed (pin assertion) | 0 failed |
| **Total pre-existing failures** | **11** | **0** |

## Files Modified

- `backend/scripts/verify_phase5_final_gate.py` — dynamic path resolver, local-first Linux producer with `linux_native` mode, platform-aware `orchestrate()`, updated CLI help
- `backend/scripts/sync_kronos.py` — removed approval gate and APPROVAL_SUMMARY constant
- `backend/tests/test_phase5_final_gate.py` — dynamic paths, fixed fake_killpg, platform-aware assertions, native Linux spec test

## Operator Command

On any clean checkout (Windows or Linux), the operator regenerates the full release evidence bundle with:

```bash
cd backend
uv run python scripts/verify_phase5_final_gate.py orchestrate \
  --repo-root /path/to/AthenaQuant \
  --validation-path .planning/milestones/v1.0-phases/05-optional-enhancements/05-VALIDATION.md \
  --phase43-summary .planning/milestones/v1.0-phases/05-optional-enhancements/05-43-SUMMARY.md \
  --plan-path .planning/milestones/v1.0-phases/05-optional-enhancements/05-44-PLAN.md
``+
This runs all four producers locally (pytest-windows, pytest-linux, playwright-fixture, playwright-real-host).
On Linux the pytest-linux producer runs natively; on Windows it runs via WSL.

For CI-sourced Linux evidence instead of local execution, append `--github-run-id <run-id>`.
This is optional — the default is local-first.

Paths resolve dynamically via `_find_phase05_dir()`, so the command works regardless of whether
Phase 05 artifacts are in the active `.planning/phases/` or archived `.planning/milestones/` layout.
