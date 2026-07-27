---
phase: 05-optional-enhancements
reviewed: 2026-07-26T22:59:13Z
diff_range: c1e88c3..cf819b2
verdict: BLOCKED
findings:
  critical: 1
  total: 1
---

# Phase 05 Final Delta Closure Addendum

## Verdict

**BLOCKED**

The requested matrix passes, but the canonical-time comparison remains incorrect for valid timestamps with different fractional-second precision.

## Required Verification

- `past-injected-clock × reserved`: PASS
- `past-injected-clock × bound`: PASS
- `future-injected-clock × reserved`: PASS
- `future-injected-clock × bound`: PASS
- unexpired direct-SQL takeover × `reserved`: rejected, PASS
- unexpired direct-SQL takeover × `bound`: rejected, PASS

Focused result: **6 passed**.

## Remaining Blocker

The repository now carries the same logical `now` through the CAS:

- Python expiration check uses `now_dt`.
- `updated_at` is set from its serialized `now`.
- CAS requires `owner_lease_until <= ?` with that same `now`.
- The trigger requires `OLD.owner_lease_until <= NEW.updated_at`.

However, `_timestamp()` uses variable-precision `datetime.isoformat()` (`backend/app/forecast/repository.py:119-120`), while the CAS and trigger compare timestamps as SQLite TEXT (`:277`, `:768`). A zero-microsecond timestamp is serialized without a fractional part. Lexicographically, `...01Z` sorts after the actually later `...01.500000Z`.

Exact reproduction:

```text
lease 2099-01-01T00:00:01Z
now   2099-01-01T00:00:01.500000Z
mixed_precision_error RuntimeError forecast retry ownership reclamation lost its race
```

Thus an operation that is expired according to the injected Python clock can still fail the SQL CAS/trigger.

**Required fix:** compare parsed temporal values using the passed canonical timestamp, e.g. `julianday(owner_lease_until) <= julianday(?)` and `julianday(OLD.owner_lease_until) <= julianday(NEW.updated_at)`, or migrate all stored timestamps and serialize them at a guaranteed fixed width. Using `julianday` preserves compatibility with existing variable-precision rows while avoiding SQLite wall-clock authority.

No source files or existing review artifacts were modified.
