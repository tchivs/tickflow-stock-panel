---
phase: 03-ai-analysis
plan: 06
subsystem: lifecycle-governance
tags: [sqlite, audit, authentication, lifecycle]
requires:
  - 03-04 immutable analysis repository
provides:
  - deterministic evidence-gated lifecycle proposals
  - server-resolved reviewer attribution and atomic confirmation
  - immutable observation plans with append-only outcomes
affects:
  - backend/app/analysis/repository.py
  - backend/app/services/auth.py
tech_stack:
  added: []
  patterns: [SQLite transactions, append-only audit history, server-owned reviewer identity]
key_files:
  created:
    - backend/app/analysis/lifecycle.py
  modified:
    - backend/app/analysis/repository.py
    - backend/app/services/auth.py
    - backend/tests/test_analysis_lifecycle.py
decisions:
  - Lifecycle proposals are evidence-gated suggestions; only confirmed events determine official state.
  - Reviewer principals are opaque, persisted per session, and resolved only from server-held session tokens.
  - Confirmed events and one observation plan are committed atomically; rejection and outcomes remain append-only.
metrics:
  duration: 6m 49s
  completed_date: 2026-07-12
status: complete
---

# Phase 03 Plan 06: Lifecycle Governance Summary

Deterministic, evidence-attributed lifecycle proposals now require trusted human confirmation before an official signal state can change.

## Completed Work

- Added `LifecycleRuleService` with state-specific gates for strengthened, weakened, falsified, and priced-in proposals. Proposals carry frozen evidence IDs, rule version, rationale, and server-recorded timestamps.
- Extended the analysis repository with immutable proposal, event, observation-plan, and outcome persistence. Confirmation rechecks state and writes exactly one event plus one 20/60/120 trading-day plan in a single SQLite transaction.
- Persisted an opaque reviewer principal with each authentication session, including compatible recovery of existing valid sessions. The principal is resolved server-side and is never accepted as a lifecycle method argument.
- Added targeted tests for lifecycle gates, stale/repeated confirmations, missing identity, rejection history, immutable plans, append-only outcomes, and persisted reviewer principals.

## Verification

- `cd backend && uv run pytest tests/test_analysis_lifecycle.py -q` -> 8 passed
- `cd backend && uv run ruff check app/analysis/lifecycle.py app/analysis/repository.py app/services/auth.py tests/test_analysis_lifecycle.py` -> passed
- `git diff --check 4e20bde^..HEAD` -> passed

## Decisions Made

- Lifecycle official state remains derived solely from confirmed immutable events; proposals and rejected reviews have no authority.
- The service receives only a session token and resolves the reviewer principal internally, preventing browser-supplied reviewer attribution.
- Observation plans are created only during confirmation and expose no update path; later results append to the existing plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Serialized confirmation/rejection ordering**
- **Found during:** Task 2 verification
- **Issue:** Rejection originally checked whether a proposal was confirmed outside its insert transaction, allowing a concurrent confirmation to interleave.
- **Fix:** Moved the confirmed-state check and rejected-review insert into one SQLite transaction; added a regression test that rejects a confirmed review.
- **Files modified:** `backend/app/analysis/repository.py`, `backend/tests/test_analysis_lifecycle.py`
- **Commit:** f9a9c5f

## Known Stubs

None.

## Self-Check: PASSED

- Found `backend/app/analysis/lifecycle.py`.
- Found commits `4e20bde`, `3f0741d`, `300cf39`, `b62ee52`, and `f9a9c5f`.
