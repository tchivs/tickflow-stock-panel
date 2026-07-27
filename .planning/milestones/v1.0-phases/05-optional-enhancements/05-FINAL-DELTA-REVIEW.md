---
phase: 05-optional-enhancements
reviewed: 2026-07-26T21:43:35Z
depth: deep
diff_base: b8e2851
files_reviewed: 18
files_reviewed_list:
  - .github/workflows/phase5-linux-evidence.yml
  - backend/app/advanced/sandbox.py
  - backend/app/advanced/strategy_policy.py
  - backend/app/forecast/repository.py
  - backend/app/forecast/runner.py
  - backend/app/forecast/service.py
  - backend/app/operational/migrations.py
  - backend/app/optional_modules.py
  - backend/pyproject.toml
  - backend/scripts/verify_phase5_final_gate.py
  - backend/tests/advanced/test_sandbox.py
  - backend/tests/forecast/test_runner.py
  - backend/tests/test_operational_migrations.py
  - backend/tests/test_phase5_final_gate.py
  - backend/tests/test_phase5_optional_host.py
  - frontend/e2e/phase5-optional-enhancements.spec.ts
  - frontend/playwright.config.ts
  - frontend/playwright.phase5-real-host.config.ts
findings:
  critical: 5
  warning: 1
  info: 0
  total: 6
status: issues_found
---

# Phase 05 Final Delta: Code Review Report

**Reviewed:** 2026-07-26T21:43:35Z  
**Depth:** deep  
**Diff:** `b8e2851..2c313c1`  
**Files Reviewed:** 18  
**Status:** issues_found

## Summary

The final delta is blocked. The positive strategy interpreter still executes attacker-controlled value operations in the parent without value/resource bounds and rejects its own documented `panel[...]` grammar. Forecast retry reservations cannot recover from an expired owner while the process remains alive. The external Linux evidence path verifies a successful run but never proves that the supplied JUnit/attestation directory is the artifact uploaded by that run. The attestation workflow also executes mutable action tags. Producer subprocesses have no orchestration timeout.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Untrusted strategy arithmetic executes unbounded in the parent process

**File:** `backend/app/advanced/strategy_policy.py:96` (also `:102-110`, `:281-297`) and `backend/app/advanced/sandbox.py:530-531`

**Issue:** The positive parser accepts integers without a magnitude bound and permits string/integer multiplication. `compile()` immediately calls `execute()` in the API parent, and `submit()` executes the same program again before the isolated launcher. A payload such as `return {"signal": "x" * 1000000000}` can force a huge allocation in the parent before any namespace, rlimit, timeout, or child-process boundary applies. `_interpret()` catches `ArithmeticError` and `TypeError`, but not `MemoryError`, and there is no operation/result budget. This restores a request-triggered denial-of-service surface at the exact boundary the IR was intended to harden.

**Fix:** Do not evaluate submitted programs during compilation. Before any parent-side interpretation, enforce bounded integer magnitude, bounded string/result length, an instruction/operation budget, and catch/translate `MemoryError`. Prefer performing the only value evaluation in the already resource-limited child, while validating IR structurally in the parent.

### CR-02: Every strategy that reads the documented panel is rejected

**File:** `backend/app/advanced/strategy_policy.py:94-97` and `backend/app/advanced/sandbox.py:530-531`

**Issue:** The grammar explicitly lowers `panel["field"]` to `panel_value`, but `compile()` validates its output by executing against `{}`. `submit()` then again constructs `panel = {}`. Therefore every accepted-looking program that reads a panel field fails with `StrategyProgramViolation("panel field ... is unavailable")` before probe/spawn. A direct reproduction with `def run(panel): return {"signal": panel["signal"]}` fails in `compile()`. The advertised primitive-panel handoff is unreachable.

**Fix:** Separate structural IR validation from runtime evaluation. Load and validate the bounded governed panel, pass those primitive values to the launcher, and execute once against that actual panel. Add a regression that compiles and runs at least one direct `panel[...]` lookup.

### CR-03: Expired retry owners permanently strand an idempotency key until restart

**File:** `backend/app/forecast/repository.py:693-712` and `backend/app/forecast/service.py:424-453`

**Issue:** `reserve_retry_operation()` returns every existing `reserved`/`bound` operation as non-owner without comparing `owner_lease_until` or reclaiming/terminalizing an expired owner. `_wait_for_retry_operation()` likewise only checks `published` and `aborted`; after its short wait it returns `RetryOperationInProgress` forever. Expiration cleanup exists only in startup recovery. If a request thread dies, stalls past 30 seconds, or loses ownership while the service stays up, subsequent callers can never publish that retry under the same idempotency key.

**Fix:** Handle lease expiry atomically inside reservation/read retry flow. Under the immediate transaction, either transfer ownership with a new token/version under a safe state-specific protocol, or abort the expired operation and provide a deterministic way to create/retry canonical work. Add a no-restart takeover regression for both `reserved` and `bound`.

### CR-04: Supplied Linux reports are not bound to the GitHub artifact from the verified run

**File:** `backend/scripts/verify_phase5_final_gate.py:818-880`

**Issue:** The gate accepts an arbitrary local `evidence_dir`, validates its self-authored attestation/JUnit hash, and separately verifies that a GitHub run with the claimed ID succeeded. It never queries that run's artifacts, verifies artifact ID/name/digest, or downloads the artifact into a gate-owned directory. `artifactName` is only a field inside the untrusted attestation. Consequently a caller can pair any locally fabricated all-pass JUnit/attestation with a successful run for the same commit. The run conclusion alone does not prove the supplied report's exact nodes were non-skipped/non-xfailed, which is the reason the parser consumes JUnit.

**Fix:** Make the orchestrator fetch the artifact for `github_run_id` itself (or verify artifact metadata and archive digest through the GitHub API), require exactly one non-expired artifact with the expected name, and parse only bytes extracted into a newly created gate-owned directory. Bind the accepted sidecar to artifact ID and digest, not a caller-controlled source directory.

### CR-05: Mutable GitHub Action tags can forge the final attestation

**File:** `.github/workflows/phase5-linux-evidence.yml:39`, `:56`, and `:120`

**Issue:** The evidence authority executes `actions/checkout@v4`, third-party `astral-sh/setup-uv@v6`, and `actions/upload-artifact@v4` by mutable tags. A moved/compromised action tag can execute arbitrary code, skip or alter tests, and upload a forged attestation while the run still concludes success. This is a supply-chain integrity gap in the final fail-closed evidence root.

**Fix:** Pin every action to a reviewed full commit SHA (with the release tag retained in a comment), and use an update mechanism that reviews pin changes.

## Warnings

### WR-01: Local producer processes can hang the one-shot gate indefinitely

**File:** `backend/scripts/verify_phase5_final_gate.py:591-627`

**Issue:** `run_producer()` calls `subprocess.run()` without a timeout. A deadlocked pytest, Playwright, Vite, uv, or WSL child prevents the gate from returning either pass or fail and can leave child processes/services alive. The GitHub job has a 30-minute limit, but the authoritative local orchestration path has no corresponding bound.

**Fix:** Give each producer an explicit policy timeout, catch `subprocess.TimeoutExpired`, terminate/reap the spawned process tree, and raise `ReportError` with the producer label. Add a contract test with a runner that raises `TimeoutExpired`.

---

_Reviewed: 2026-07-26T21:43:35Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: deep_
