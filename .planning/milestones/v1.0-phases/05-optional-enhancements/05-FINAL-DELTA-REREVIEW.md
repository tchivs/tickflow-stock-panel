---
phase: 05-optional-enhancements
reviewed: 2026-07-26T22:23:55Z
depth: deep
diff_range: 96dab5d..42d96c5
files_reviewed: 9
files_reviewed_list:
  - .github/workflows/phase5-linux-evidence.yml
  - backend/app/advanced/sandbox.py
  - backend/app/advanced/strategy_policy.py
  - backend/app/forecast/repository.py
  - backend/app/forecast/service.py
  - backend/scripts/verify_phase5_final_gate.py
  - backend/tests/advanced/test_sandbox.py
  - backend/tests/forecast/test_runner.py
  - backend/tests/test_phase5_final_gate.py
findings:
  critical: 2
  warning: 1
  info: 0
  total: 3
status: issues_found
verdict: BLOCKED
---

# Phase 05 Final Delta: Deep Re-review

**Reviewed:** 2026-07-26T22:23:55Z  
**Depth:** deep  
**Diff:** `96dab5d..42d96c5`  
**Verdict:** BLOCKED

## Summary

The artifact authority is materially hardened: the orchestrator now discovers exactly one run-scoped artifact, verifies its GitHub digest and downloaded byte size, extracts only two flat regular files into a gate-owned directory, and rechecks exact run/head/tree identity. The workflow actions are pinned to immutable SHAs. Strategy evaluation has also been removed from the parent submission path and bounded in the child.

The delta is nevertheless blocked. The documented `panel[...]` program still receives an empty panel in the real submission path, so the child exits with code 126. Retry reclamation also compares lease expiry with the repository's injected clock but authorizes the update with SQLite's unrelated wall clock, making valid takeovers fail. Producer execution is bounded, but WSL preflight remains unbounded and timeout cleanup does not prove that descendants were terminated.

## Closure Table

| Original finding | Verdict | Evidence |
|---|---|---|
| CR-01 — unbounded parent strategy evaluation | CLOSED | `StrategyProgramPolicy.compile()` performs structural `validate()` only (`backend/app/advanced/strategy_policy.py:98-100`); `submit()` no longer calls `execute()` (`backend/app/advanced/sandbox.py:576-579`); the fixed child interpreter enforces instruction, integer, text, mapping, and result budgets (`backend/app/advanced/sandbox.py:425-538`). |
| CR-02 — documented panel lookup always rejected | OPEN / BLOCKER | The compiler now admits `panel_value`, but `submit()` still constructs `panel = {}` and passes it unchanged to the launcher (`backend/app/advanced/sandbox.py:576-594`). A real generated child interpreter for `panel["decision"]` with that handoff exits 126. The added test evaluates a separate hand-built panel in the parent and only checks a recording launcher, never the real child (`backend/tests/advanced/test_sandbox.py:245-266`). |
| CR-03 — expired retry owners strand the key | OPEN / BLOCKER | Reclamation is implemented, but expiry is decided with `self._clock()` (`backend/app/forecast/repository.py:729-759`) while the trigger permits the same update only when `julianday(OLD.owner_lease_until) <= julianday('now')` (`backend/app/forecast/repository.py:273-279`). A valid future injected-clock takeover reproduces as `IntegrityError: forecast retry operation transition is invalid`. |
| CR-04 — Linux report not bound to the GitHub artifact | CLOSED | The gate requires one exact run-scoped artifact (`backend/scripts/verify_phase5_final_gate.py:913-1024`), verifies downloaded size and `sha256:` digest (`:1027-1097`), performs flat bounded ZIP extraction (`:1100-1143`), and parses only the downloaded evidence (`:1268-1321`). Run/head/tree/attempt are independently verified (`:830-910`). |
| CR-05 — mutable action tags | CLOSED | Checkout, setup-uv, and upload-artifact use full reviewed commit SHAs in `.github/workflows/phase5-linux-evidence.yml:39`, `:56`, and `:120`. |
| WR-01 — producer can hang indefinitely | PARTIAL / WARNING | `run_producer()` now applies a 1,800-second timeout (`backend/scripts/verify_phase5_final_gate.py:647-711`), but WSL path preflight still invokes `wsl.exe` without a timeout (`:2065-2075`). Timeout cleanup also returns as soon as the leader exits after SIGTERM and ignores nonzero `taskkill` results, so descendants are not proven reaped (`:599-644`). |

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-RR-01: Real submissions still execute every panel lookup against an empty panel

**Classification:** BLOCKER  
**File:** `backend/app/advanced/sandbox.py:576-594`  
**Related test gap:** `backend/tests/advanced/test_sandbox.py:245-266`

**Issue:** The compiler now structurally accepts `panel["field"]`, but the service unconditionally creates an empty dictionary and hands it to `LinuxIsolationLauncher`. The child interpreter explicitly rejects a missing field, so a submitted program such as `return {"signal": panel["decision"]}` cannot complete. The new regression is a false positive: it calls `program.interpret({"decision": "buy"})` separately, then submits through a recording `TerminalLauncher` that never runs the fixed child script and never asserts the handed-off panel.

**Reproduction:** Compiling that program and executing `LinuxIsolationLauncher._interpreter_script(program=program, panel={})` with the current Python interpreter returns exit code `126` with no output.

**Fix:** Load the governed panel from the authoritative input, validate it as a bounded primitive mapping without evaluating strategy operations, and pass that mapping to the isolated child. Add an integration test that executes the generated child interpreter (or the Linux launcher) through `CustomStrategySandboxService.submit()` and asserts the expected signal.

### CR-RR-02: Retry reclamation uses two clocks and rejects valid expired-owner takeovers

**Classification:** BLOCKER  
**File:** `backend/app/forecast/repository.py:273-279` and `backend/app/forecast/repository.py:729-777`

**Issue:** Python decides that the lease is expired using the repository's supported injected clock. The guarding SQLite trigger independently compares the old lease to SQLite's real `now`. When the injected clock is ahead of the database wall clock, Python enters the takeover branch but the trigger aborts the update. This preserves the original stranded-key failure for clock-skewed deployments and makes the new regression time-dependent: its fixed 2025 clock happens to be behind the current 2026 SQLite clock.

**Reproduction:** Create a reservation with repository clock `2030-01-01T00:00:00Z`, advance the injected clock by two seconds past a one-second lease, and reserve the same key. The current code raises `sqlite3.IntegrityError: forecast retry operation transition is invalid`.

**Fix:** Use one authoritative time value for both decision and guard. For example, bind the repository-generated `now` into the guarded `UPDATE` and make the trigger compare `OLD.owner_lease_until` with `NEW.updated_at`, while retaining the monotonic lease/version and immutable-binding checks. Add takeover tests with clocks both ahead of and behind the machine wall clock.

## Warnings

### WR-RR-01: The gate can still hang before producers and timeout cleanup can leave descendants

**Classification:** WARNING  
**File:** `backend/scripts/verify_phase5_final_gate.py:599-644` and `backend/scripts/verify_phase5_final_gate.py:2065-2075`

**Issue:** Producer leaders now have a bounded wait, but `_resolve_wsl_path()` performs an unbounded `subprocess.run()` twice before the Linux producer starts. A stalled WSL service still hangs the one-shot gate indefinitely. On POSIX, cleanup returns once the leader exits after `SIGTERM`, without checking whether group descendants remain; on Windows, a nonzero `taskkill /T /F` result is ignored before falling back to leader-only `process.kill()`.

**Fix:** Apply an explicit timeout to WSL path resolution and translate it to `ReportError`. During producer cleanup, inspect `taskkill` failure, and on POSIX always follow the grace period with a bounded group-existence check/SIGKILL path rather than treating leader exit as proof of tree cleanup. Add a real subprocess regression whose leader exits on termination while a descendant ignores SIGTERM.

## Verification Performed

- Focused closure tests: `9 passed, 206 deselected`.
- Full changed-test scope: `201 passed, 14 skipped`.
- Real child-script panel reproduction: exit code `126`.
- Future injected-clock retry takeover reproduction: `IntegrityError` from the guarded update.
- `git diff --check 96dab5d..42d96c5`: clean.

---

_Reviewed: 2026-07-26T22:23:55Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: deep_
