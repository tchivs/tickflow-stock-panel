# Plan 45-03 Summary: Checkpoint Lifecycle + Run Worker

**Plan:** 45-03 (wave 3)
**Phase:** 45-durable-governed-run-contract
**Status:** Complete
**Date:** 2026-08-08

## Objective

Add the server-owned lifecycle state machine and untrusted worker boundary over the durable ledger from 45-02: guarded transitions, idempotent start/retry/cancel, cooperative cancellation, restart recovery, linked child runs, opaque token/version fencing, and bounded four-counter progress updates — all without allowing a worker or JobStore to become the run ledger or execution authority. Satisfies AF-REQ-16 and decisions D-06, D-07, D-10, D-11, D-12.

## Commits

| Hash | Message |
|------|---------|
| `c431824` | feat(45-03): guarded lifecycle transitions with idempotent retry and cooperative cancellation |
| `779074f` | feat(45-03): token-fenced worker adapter with bounded four-counter progress seam |

## What Was Delivered

### Task 45-03-01: Guarded lifecycle transitions and idempotent retry/cancel

**`backend/app/research/run_service.py`** — lifecycle matrix and orchestration:

- `LIFECYCLE_EDGES` — explicit legal matrix: `queued → running|preflight_failed|cancel_requested|failed`, `running → cancel_requested|completed|failed`, `cancel_requested → cancelled|failed`; all four terminal states (`preflight_failed`, `cancelled`, `completed`, `failed`) are one-way.
- `transition()` — validates the edge against the legal matrix, then delegates to the repository's guarded SQL update + event append. Illegal edges raise `ValueError`; stale expected-version raises `ValueError` when the run exists; cross-principal/unknown returns `None`.
- `start_or_resume()` — transitions `queued → running`, issues an opaque server-owned attempt token (32 random bytes, hex-encoded). Only the token's SHA-256 is durable (embedded in the `run_started` event payload). Duplicate start of an already-running run returns existing state without reissuing a token; terminal runs raise "illegal lifecycle".
- `cancel()` — idempotently requests cooperative cancellation (`queued`/`running → cancel_requested`). Terminal runs return current state with no new event.
- `retry()` — creates a linked child run with `retry_of_run_id` set to the parent, preserving the immutable parent. Idempotency on `(principal, idempotency_key)`; changed input creates a new snapshot/digest.

**`backend/app/research/repository.py`** — guarded cursor methods:

- `transition_alpha_run()` — guarded `WHERE id = ? AND principal = ? AND status = ? AND transition_version = ?`, atomic event + cursor update under `BEGIN IMMEDIATE`. Illegal/stale/cross-principal matches zero rows → no event, no cursor change (rolls back). Idempotency on `(run_id, idempotency_key)` with semantic checksum conflict detection. Embeds `extra_payload` (token digest) in the event.
- `cancel_alpha_run()` — idempotent cancellation request; terminal/already-requested runs return current state.
- `retry_alpha_run()` — linked child creation via `create_alpha_run` with `retry_of_run_id` and incremented `retry_attempt`.
- `update_progress()` — persists the four bounded counters with `WHERE id = ? AND principal = ? AND transition_version = ?` guard.

### Task 45-03-02: Untrusted worker adapter and progress seam

**`backend/app/research/run_worker.py`** — new file:

- `ResearchRunWorkerAdapter` — replaceable, untrusted wrapper around the service seam. Accepts only server-issued run ID/token, expected version, bounded stage/candidate metadata, bounded progress deltas, and idempotency key. Every callback requires a valid attempt token plus expected `transition_version`.
- `report_progress()` — requests a bounded progress update; requires valid token + version.
- `request_transition()` — requests a lifecycle transition; validates token + version before delegating. Stale/invalid token fails closed (returns `None`, no side effect).
- No policy, evaluator, provider, OOS, promotion, broker, order, portfolio, monitor, or live-execution authority or collaborator. The only import is `run_service` (TYPE_CHECKING).

**`backend/app/research/run_service.py`** — token validation and progress:

- `_validate_attempt_token()` — validates opaque token + expected version against the `run_started` event's persisted SHA-256 digest. Cancel, terminal transition, retry, or any version change invalidates older tokens (the version guard ensures only the current running version's token is valid).
- `update_progress()` — validates token + version, then persists the four bounded server-owned counters (`candidate_attempts_total`, `candidate_attempts_completed`, `folds_total`, `folds_completed`). Does NOT evaluate folds.

**`backend/app/research/run_contract.py`** — extended contracts:

- `attempt_token_digest()` — lowercase SHA-256 over an opaque attempt token (only the digest is durable).
- `validate_progress_counters()` — fail-closed validation that every provided counter is a non-negative integer.
- `PROGRESS_COUNTERS` — the four counter names.

**`backend/app/research/repository.py`** — `update_progress()` added (guarded cursor update for the four counters, only non-`None` values updated).

## Test Coverage (89 tests in `test_run_contract.py`)

### New Wave 3 tests (30 tests)

**Lifecycle transitions (6):** legal queued→running with version increment + event; illegal queued→completed rejected with no side effect; stale expected-version rejected; terminal state cannot transition back; preflight_failed terminal with reason; cross-principal returns None.

**Start/resume idempotency (1):** duplicate start returns running with no duplicate event.

**Cooperative cancellation (4):** cancel_requested → cancelled flow; late worker completion after cancel rejected; cancel idempotent (no duplicate event); cancel queued before start.

**Retry (4):** linked child preserving parent; idempotent same-key returns existing child; changed input creates new digest; cross-principal returns None.

**Attempt token fencing (4):** opaque token issued with only SHA-256 persisted (raw token never in durable plaintext); valid callback requires token + version; stale token rejected after version change; invalid token fails closed.

**Progress counters (4):** all four counters persist; zero totals valid for fresh run; negative counter rejected; stale version progress rejected.

**Restart recovery (2):** fresh repository recovers status/events/counters; restart does not trust worker memory.

**Worker adapter (3):** valid-token transition succeeds; stale-token transition fails closed; no authority collaborators imported.

**Commit-before-publish crash (2):** committed transition survives publisher failure; retrying adapter returns existing event (no duplicate).

## Test Totals

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/research/test_run_contract.py` | 89 | passed |
| `tests/test_operational_migrations.py` | 18 | passed |
| **Total (2 files)** | **107** | **all passed** |

### Per-task verification (all green)

```
# Task 45-03-01
pytest tests/research/test_run_contract.py -k 'lifecycle or cancel or retry or preflight or principal' -q
→ 23 passed, 66 deselected

# Task 45-03-02
pytest tests/research/test_run_contract.py -k 'restart or resume or worker or token or progress or retry or cancel' -q
→ 24 passed, 65 deselected

# Wave boundary
pytest tests/test_operational_migrations.py tests/research/test_run_contract.py -q
→ 107 passed
```

## Must-Have Truths (verified)

- ✅ Only server-owned legal lifecycle edges can change a run cursor; illegal or stale competing transitions append no event and change no status/version/count.
- ✅ Duplicate start, retry, and cancel requests return existing durable state; retry resumes a verified cursor or creates a linked immutable child and never mutates the parent.
- ✅ Cancellation is cooperative and durable, restart recovery fences stale workers, and the JobStore/worker adapter cannot choose policy, mutate frozen inputs, or grant execution/promotion authority.
- ✅ A running attempt is fenced by an opaque server token plus expected transition version; only the token SHA-256 is durable, and stale tokens cannot append work.
- ✅ The safe run cursor persists and reports bounded `candidate_attempts_total`, `candidate_attempts_completed`, `folds_total`, and `folds_completed` counters without evaluating folds.

## Threat Model Mitigations

- **T-45-06 (Tampering/Elevation):** Explicit legal matrix enforced in both service validation and repository SQL guard (`WHERE id = ? AND principal = ? AND status = ? AND transition_version = ?`); atomic event+cursor writes; terminal one-way checks.
- **T-45-07 (Tampering/Denial):** Principal/request-key idempotency lookup; linked child semantics for retry; cooperative cancellation boundary; no late terminal overwrite (cancel_requested → completed rejected).
- **T-45-08 (Tampering/Denial):** Each `running` transition generates an opaque server token; only SHA-256 persisted in the `run_started` event payload; callbacks require token plus expected `transition_version`; cancel/terminal/retry/version changes invalidate older tokens via the version guard.
- **T-45-12 (Information disclosure/Tampering):** Every repository predicate scoped to principal; same safe not-found boundary for cross-principal access; bounded server-owned counters only.

## Deviations

None. The plan was followed exactly: test-first per task, atomic commits via explicit `git add`, zero new runtime dependencies, Watchlist zero-touch, clean working tree.

## Files Modified

| File | Action |
|------|--------|
| `backend/app/research/run_service.py` | Modified (lifecycle matrix, transition/start_or_resume/cancel/retry, token validation, update_progress) |
| `backend/app/research/repository.py` | Modified (transition_alpha_run, cancel_alpha_run, retry_alpha_run, update_progress) |
| `backend/app/research/run_contract.py` | Modified (attempt_token_digest, validate_progress_counters, PROGRESS_COUNTERS) |
| `backend/app/research/run_worker.py` | Created (ResearchRunWorkerAdapter) |
| `backend/tests/research/test_run_contract.py` | Modified (+30 lifecycle/retry/cancel/token/progress/restart/worker tests) |
