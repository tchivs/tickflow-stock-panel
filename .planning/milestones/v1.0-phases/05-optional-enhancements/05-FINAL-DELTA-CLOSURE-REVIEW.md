---
phase: 05-optional-enhancements
reviewed: 2026-07-26T22:48:20Z
depth: deep
diff_range: 42d96c5..c1e88c3
files_reviewed: 6
files_reviewed_list:
  - backend/app/advanced/sandbox.py
  - backend/app/forecast/repository.py
  - backend/scripts/verify_phase5_final_gate.py
  - backend/tests/advanced/test_sandbox.py
  - backend/tests/forecast/test_runner.py
  - backend/tests/test_phase5_final_gate.py
findings:
  critical: 1
  warning: 0
  info: 0
  total: 1
status: issues_found
verdict: BLOCKED
---

# Phase 05 Final Delta: Closure Re-review

**Reviewed:** 2026-07-26T22:48:20Z  
**Depth:** deep  
**Diff:** `42d96c5..c1e88c3`  
**Verdict:** BLOCKED

## Summary

Two of the three requested closures are complete. A server-owned resolver now supplies a bounded primitive panel before any capability probe, the generated child interpreter executes a real panel lookup exactly once, and absence/failure of that authority rejects before probe or spawn. WSL preflight is bounded, and process-tree cleanup now retries and fails closed when cleanup cannot be proven.

The retry-owner fix is still blocked. Normal repository calls now work with injected clocks both before and after the machine clock, but the database trigger achieves that by removing the lease-expiry predicate entirely. The guarded table therefore permits a same-state owner takeover while the current owner's lease is still valid. This weakens the durable ownership invariant and can reintroduce concurrent owners.

## Closure Table

| Prior finding | Verdict | Evidence |
|---|---|---|
| CR-RR-01 — real panel lookups receive an empty panel | CLOSED | `submit()` resolves the panel before creating a work directory or probing (`backend/app/advanced/sandbox.py:592-601`). `_resolve_governed_panel()` derives required fields from immutable IR and accepts only a server-injected resolver (`:707-747`); `_bounded_primitive_panel()` enforces item, key, integer, finite-float, text, primitive-type, and encoded-size bounds (`:749-790`). The focused test executes the actual generated child script and obtains `{"signal":"buy"}`; missing authority rejects with no probe/spawn. |
| CR-RR-02 — injected clock conflicts with SQLite wall clock | OPEN / BLOCKER | Repository API takeovers now pass with past and future injected clocks, but the trigger's takeover arm only checks same state, a changed owner, extended lease, and immutable binding (`backend/app/forecast/repository.py:273-281`). It no longer requires the old lease to be expired. A direct guarded-table update successfully replaced the owner one second into a still-valid one-hour lease. |
| WR-RR-01 — unbounded WSL preflight / unproven descendant cleanup | CLOSED | `_resolve_wsl_path()` uses a 30-second timeout and translates timeout/unavailability to `ReportError` (`backend/scripts/verify_phase5_final_gate.py:2111-2124`). `_terminate_process_tree()` retries Windows `taskkill`, fails closed on unproved cleanup, and on POSIX checks the process group, escalates to SIGKILL, waits, and polls for group disappearance (`:601-683`). Windows and timeout regressions pass. |

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-CL-01: The retry trigger permits takeover before the owner lease expires

**Classification:** BLOCKER  
**File:** `backend/app/forecast/repository.py:273-281`

**Issue:** The application-level branch correctly compares `owner_lease_until` with the injected repository clock at line 757, but the database guard no longer validates expiration. Any direct SQL writer that preserves state and immutable binding, increments the version, changes the token, and extends the lease passes the trigger even while the original lease is active. The trigger is the durable last line of defense for this state machine; permitting an early takeover defeats the single-owner invariant and can allow the displaced owner and replacement owner to prepare or publish concurrently.

**Reproduction:** Reserve an operation at injected time `2099-01-01T00:00:00Z` with a one-hour lease. At `00:00:01Z`, directly update the same row to a new owner token, a two-hour lease, and `transition_version + 1` while preserving all binding fields. The update commits successfully:

```text
unexpired_before 2099-01-01T01:00:00Z
early_takeover_allowed stolen-owner 1
```

**Fix:** Keep the repository clock as the sole time authority but carry it into the guarded transition. Require the old lease to be expired relative to the new canonical update timestamp, for example `OLD.owner_lease_until <= NEW.updated_at`, while retaining the lease-extension, version, state, and immutable-binding checks. Also include `owner_lease_until <= ?` with the same repository-generated `now` in the reclamation `UPDATE` predicate. Add a direct-SQL regression proving takeover before expiry is rejected for both `reserved` and `bound`, alongside the existing past/future-clock success matrix.

## Verification Performed

- Exact focused closure nodes: `12 passed, 1 skipped`.
- Real generated child execution: completed with `{"signal": "buy"}`.
- Missing panel authority: rejected before probe and spawn.
- Past injected clock (`2000`) expired takeover: passed with same operation and new owner.
- Future injected clock (`2099`) expired takeover: passed with same operation and new owner.
- Early unexpired direct-SQL takeover: unexpectedly succeeded, establishing the blocker.
- WSL preflight timeout and Windows taskkill retry/fail-closed regressions: passed.
- POSIX real-descendant regression is present but skipped on this Windows host; a WSL rerun was unavailable because no Linux distribution is installed.
- The broader three-file suite exceeded the outer 120-second review harness without a test failure result; closure-specific nodes above completed successfully.

## Residual Nonblocking Risks

- `app.main.lifespan` does not currently inject a governed panel resolver. Default production-host panel lookups therefore remain deliberately unavailable and reject before probe; enabling this capability requires wiring an authoritative server resolver. No client-controlled fallback exists.
- POSIX descendant cleanup was source-reviewed but could not be executed locally. It should remain mandatory in Linux CI evidence.

---

_Reviewed: 2026-07-26T22:48:20Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: deep_
