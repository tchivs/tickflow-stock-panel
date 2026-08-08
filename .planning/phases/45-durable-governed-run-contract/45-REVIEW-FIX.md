---
phase: 45-durable-governed-run-contract
fixed_at: 2026-08-08T18:38:28Z
review_path: .planning/phases/45-durable-governed-run-contract/45-REVIEW.md
iteration: 5
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 45: Code Review Fix Report

**Fixed at:** 2026-08-08T18:38:28Z  
**Source review:** `.planning/phases/45-durable-governed-run-contract/45-REVIEW.md`  
**Iteration:** 5

**Summary:**
- Findings in scope: 2
- Fixed: 2
- Skipped: 0

## Verification

The fix-report commands below are focused; the final session also ran the backend-wide suite with the repository's expected local stockdb defaults.

```text
cd backend && .venv/bin/pytest tests/research/test_run_contract.py tests/research/test_alpha_factory.py tests/api/test_run_api.py tests/test_phase45_guard.py -q
→ 360 passed

cd backend && .venv/bin/pytest tests/test_operational_migrations.py -q -k 'phase45 or alpha'
→ 4 passed, 16 deselected

cd backend && .venv/bin/python -m compileall -q app/research app/api/research_alpha.py app/main.py app/operational/migrations.py
→ passed

Final session backend-wide verification (run with the repository's expected local stockdb defaults):

```text
cd backend && LOCAL_STOCKDB_URL=http://127.0.0.1:8000 LOCAL_STOCKDB_API_KEY= ./.venv/bin/pytest -q
→ 2296 passed, 4 skipped, 10 warnings
```

## Fixed Issues

### WR-01: Concurrent idempotent create/start/recovery requests could conflict

**Files modified:** `backend/app/research/repository.py`, `backend/app/research/run_service.py`, `backend/tests/research/test_run_contract.py`  
**Commit:** `83193d0`  
**Applied fix:** Create idempotency lookup and insertion now share a `BEGIN IMMEDIATE` transaction, with a bounded SQLite busy timeout. Lifecycle start/recovery paths return the durable winner when concurrent requests race after token generation; server-generated loser tokens are discarded and never exposed. Recovery preserves cross-event idempotency-key conflicts. Regression coverage runs concurrent create, start, and recovery requests and asserts one durable event per operation and at most one plaintext winner token.

### CR-01: Token-stripped start replay could accept a different event type

**Files modified:** `backend/app/research/repository.py`, `backend/tests/research/test_run_contract.py`  
**Commit:** `ff37d46`  
**Applied fix:** The server-generated token-digest replay path now requires both the requested and existing lifecycle event to be `run_started`. A same-key non-`run_started` event follows the normal checksum conflict path and cannot leave a queued run falsely treated as started. Regression: `test_start_replay_requires_an_existing_run_started_event`.

---

## Final Review

`.planning/phases/45-durable-governed-run-contract/45-REVIEW.md` iteration 7 reports:

- Critical: 0
- Warning: 0
- Info: 0
- Status: `clean`

_Fixed: 2026-08-08T18:38:28Z_  
_Fixer: Main session  
_Iteration: 5_
