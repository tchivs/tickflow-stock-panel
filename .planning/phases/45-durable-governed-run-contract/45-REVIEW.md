---
phase: 45-durable-governed-run-contract
reviewed: 2026-08-08T18:19:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - backend/app/operational/migrations.py
  - backend/app/research/run_contract.py
  - backend/app/research/repository.py
  - backend/app/research/artifacts.py
  - backend/app/research/run_service.py
  - backend/app/research/run_worker.py
  - backend/app/research/run_schemas.py
  - backend/app/research/projections.py
  - backend/app/api/research_alpha.py
  - backend/app/main.py
  - backend/tests/research/test_run_contract.py
  - backend/tests/research/test_alpha_factory.py
  - backend/tests/api/test_run_api.py
  - backend/tests/test_operational_migrations.py
  - backend/tests/test_phase45_guard.py
findings:
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 45: Code Review Report

**Reviewed:** 2026-08-08T18:19:00Z  
**Depth:** standard  
**Files Reviewed:** 15  
**Status:** issues_found

## Summary

The iteration-4 fixes are present and the required focused verification passed: AlphaFactory 152 passed, the Phase45 contract/API/guard batch 205 passed, the Phase45/Alpha migration selection 4 passed with 16 deselected, and the reviewed modules compile. The prior checkpoint artifact-verifier, atomic candidate/lineage fence, generated DTO, explicit/derived recovery idempotency, and private raw-checkpoint-read findings are addressed. One residual concurrency correctness defect remains: duplicate lifecycle/create requests can race after their preflight lookup and return a conflict instead of the already-committed durable state.

## Warnings

### WR-01: Concurrent idempotent requests can conflict instead of returning durable state

**File:** `backend/app/research/repository.py:1454-1469,1508-1533`; `backend/app/research/run_service.py:228-247,272-285`

**Issue:** The repository opens a fresh SQLite connection for each operation, performs the create idempotency lookup before entering the write transaction, and only then inserts the run. Two same-principal requests with the same canonical input can both observe no existing row; one commits and the other reaches the unique `(principal, idempotency_key)` constraint and is converted to `AlphaRunConflictError`, so the duplicate receives a conflict instead of the existing run. The same race exists in `start_or_resume`: both callers read `queued`, mint different random token digests, and use the same default transition key; the second sees the existing event but its checksum differs because the token digest is in the payload, producing an idempotency conflict rather than existing running state. `recover_running_attempt` has the analogous lookup/mint gap when concurrent callers use the same explicit or derived recovery key. This violates the D-06 requirement that duplicate requests return the existing durable state and makes restart/concurrent worker callbacks nondeterministically fail despite identical intent.

**Fix:** Move the idempotency check and the corresponding write into one `BEGIN IMMEDIATE` transaction, or catch the unique-key race and re-read the owned row/event under a write-locked transaction before returning. For start and recovery, resolve an existing lifecycle event under that same lock before minting a token; if the event already exists, return its durable run state without minting or exposing a new plaintext token. If a winning event is discovered after token generation, discard the generated token and return the existing state rather than comparing a new random digest as a changed request.

## Info

No informational findings.

---

_Reviewed: 2026-08-08T18:19:00Z_  
_Reviewer: Claude (gsd-code-reviewer)  
_Depth: standard_
