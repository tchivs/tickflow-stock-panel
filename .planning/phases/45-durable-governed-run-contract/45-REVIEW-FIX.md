---
phase: 45-durable-governed-run-contract
fixed_at: 2026-08-08T18:12:00Z
review_path: .planning/phases/45-durable-governed-run-contract/45-REVIEW.md
iteration: 4
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 45: Code Review Fix Report

**Fixed at:** 2026-08-08T18:12:00Z  
**Source review:** `.planning/phases/45-durable-governed-run-contract/45-REVIEW.md`  
**Iteration:** 4

**Summary:**
- Findings in scope: 5
- Fixed: 5
- Skipped: 0

## Verification

All verification ran in the main checkout (`workflow.use_worktrees=false`); no broad project-wide suite was run.

```text
cd backend && .venv/bin/python -m compileall -q app/research app/api/research_alpha.py app/main.py app/operational/migrations.py
→ passed

cd backend && .venv/bin/pytest tests/research/test_alpha_factory.py -q
→ 152 passed

cd backend && .venv/bin/pytest tests/research/test_run_contract.py tests/api/test_run_api.py tests/test_phase45_guard.py -q
→ 205 passed

cd backend && .venv/bin/pytest tests/test_operational_migrations.py -q -k 'phase45 or alpha'
→ 4 passed, 16 deselected
```

## Fixed Issues

### CR-01: Checkpoint validation rejected artifact-backed event histories

**Files modified:** `backend/app/research/run_service.py`  
**Commit:** `411aedb` (retained in current service)  
**Applied fix:** The committed event-prefix read in `validate_checkpoint` passes the service-owned artifact verifier. Valid artifact-backed event histories can validate; missing or tampered artifacts still fail closed.

### CR-02: Worker candidate and lineage writes had a token-validation TOCTOU gap

**Files modified:** `backend/app/research/run_service.py`, `backend/app/research/run_worker.py`, `backend/app/research/repository.py`, `backend/tests/research/test_alpha_factory.py`, `backend/tests/research/test_run_contract.py`  
**Commits:** `5b48547`, `411aedb`, `86e46e5`  
**Applied fix:** Candidate and lineage service methods now require exact `expected_version` and attempt token values and pass the token digest, principal, and version into the repository's single `BEGIN IMMEDIATE` write transaction. The repository enforces principal ownership, `running` status, current version, and current attempt digest immediately before insertion. The worker no longer performs a standalone token read before writing. Regression coverage includes stale-token and post-cancel/recovery no-side-effect cases.

### CR-03: Durable `generated` candidates crashed the public history route

**Files modified:** `backend/app/research/run_schemas.py`, `backend/app/api/research_alpha.py`, `backend/tests/api/test_run_api.py`  
**Commit:** `5b46598`  
**Applied fix:** `AlphaCandidateDTO.status` includes `generated`, matching the durable contract and migration. Public candidate history serializes generated candidates as a typed response.

### WR-01: Recovery without an explicit idempotency key was not restart-safe

**Files modified:** `backend/app/research/run_service.py`, `backend/tests/research/test_run_contract.py`  
**Commit:** `86e46e5`  
**Applied fix:** The effective recovery key is resolved before the existing-event lookup for both explicit and derived keys. A repeated derived-key recovery returns the durable existing state without minting or exposing a new plaintext token.

### WR-02: Repository exposed a misleading unchecked `get_latest_valid_checkpoint` method

**Files modified:** `backend/app/research/repository.py`, `backend/app/research/run_service.py`, `backend/tests/research/test_run_contract.py`  
**Commits:** `5b48547`, `411aedb`  
**Applied fix:** The repository exposes only the explicitly private `_get_latest_checkpoint_unvalidated` raw read. Recovery uses the service-owned `get_latest_valid_checkpoint` seam, which validates the cursor before returning it.

---

_Fixed: 2026-08-08T18:12:00Z_  
_Fixer: Main session  
_Iteration: 4_
