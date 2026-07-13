---
phase: 04-advanced-capabilities
reviewed: 2026-07-13
depth: final-remediation
files_reviewed: 12
files_reviewed_list:
  - backend/app/advanced/api.py
  - backend/app/advanced/evolution.py
  - backend/app/advanced/governed_runner.py
  - backend/app/advanced/policy.py
  - backend/app/advanced/repository.py
  - backend/app/advanced/sandbox.py
  - backend/app/advanced/viewpoints.py
  - backend/app/operational/migrations.py
  - backend/tests/advanced/test_sandbox.py
  - backend/tests/advanced/test_viewpoints.py
  - backend/tests/advanced/test_experiments.py
  - backend/tests/advanced/test_evolution.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 04: Final Remediation Review

**Reviewed:** 2026-07-13
**Depth:** final remediation
**Status:** clean

## Scope and method

Static review of the remediation commits and current implementation for sandbox topology, sandbox-validation authorization, policy fingerprint/snapshot provenance and legacy migration, and governed split evidence. The focused contracts in `test_sandbox.py`, `test_viewpoints.py`, `test_experiments.py`, and `test_evolution.py` were read to establish intended behavior; they were **not run**. No formatter, linter, build, or test suite was run.

## Resolved historic findings

### Sandbox child topology is now fail-closed

`LinuxIsolationLauncher._bootstrap_script()` now constructs the child’s own recursive-private mount tree, tmpfs root/work directory, read-only governed input and strategy mounts, then verifies mountinfo before `chroot`/`execve` (`backend/app/advanced/sandbox.py:285-351`). Every mount operation raises on failure. The focused sandbox contract covers failed mounts and shared/non-read-only topology rejection before execution.

### Sandbox validation history is authorized per parent asset

`GET /sandbox/validations` requires an authenticated principal and filters each persisted validation through `_research_asset_allowed` using its immutable `parent_asset_id` (`backend/app/advanced/api.py:472-482`). The focused API contract seeds another asset’s validation and asserts none of its projected fields are disclosed.

### Policy facts are bound to canonical complete snapshots

The deployed policy fingerprint is computed from the complete normalized snapshot, including allowlist and rate-limit controls (`backend/app/advanced/policy.py:68-96`). Repository writes validate the canonical SHA-256 before persistence and reuse only a `(fingerprint, fact_schema_version)` match (`backend/app/advanced/repository.py:33-38, 423-439`). The focused viewpoint contracts cover changed rate limits/allowlists and reject mismatched snapshot/fingerprint pairs.

### Legacy partial policy facts cannot contaminate new attribution

The final migration preserves existing rows and foreign keys under `advanced_policy_snapshot_legacy_v1`, while current facts use `advanced_policy_snapshot_v2` with a composite uniqueness key (`backend/app/operational/migrations.py:697-716`; `backend/app/advanced/policy.py:10-11`). A current viewpoint therefore mints/reuses a distinct self-verifying v2 fact even when its complete-snapshot fingerprint equals a legacy partial row’s historical fingerprint; revision reuse rejects legacy facts (`backend/app/advanced/repository.py:85-100`). The focused migration contract seeds that real collision shape and verifies historic bytes/FK retention, distinct current attribution, and legacy revision rejection.

### Split evidence is produced by independent governed evaluations

The governed collaborator executes the full window plus two non-overlapping split windows and stores each split’s run ID, governed-input fingerprint, window, and metrics artifact (`backend/app/advanced/governed_runner.py:64-80, 139-159`). Promotion validation rejects missing or non-independent evidence and requires distinct split run IDs and governed fingerprints (`backend/app/advanced/evolution.py:314-357`). The focused contracts cover distinct execution windows and rejection of copied aggregate metrics without independent evaluation metadata.

## Active findings

None.

## Verification

Static review only. The focused test files were inspected for their behavioral contracts but were not executed; no runtime-test result is claimed.

## VERIFICATION PASSED

---
_Reviewed: 2026-07-13_
_Reviewer: FinalPhase04Review_
_Depth: final remediation_
