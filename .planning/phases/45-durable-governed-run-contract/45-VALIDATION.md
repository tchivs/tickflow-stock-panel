---
phase: 45
slug: durable-governed-run-contract
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-08
---

# Phase 45 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0, pytest-asyncio >=0.23 |
| **Config file** | `backend/pyproject.toml` (`asyncio_mode = "auto"`, importlib mode) |
| **Quick run command** | `cd backend && pytest tests/test_operational_migrations.py tests/research/test_run_contract.py -q` |
| **Full suite command** | `cd backend && pytest -q` |
| **Estimated runtime** | <30 seconds for focused selection; full suite measured during execution |

---

## Sampling Rate

- **After every task commit:** Run the focused migration/repository/API selection for the changed contract.
- **After every plan wave:** Run Phase 45 focused tests plus migration tests.
- **Before `/gsd:verify-work`:** Full backend suite must be green.
- **Max feedback latency:** 30 seconds for focused tests.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 45-01-01 | 01 | 1 | AF-REQ-01 | T-45-01 | Canonical server-frozen manifest; same-key replay idempotent; changed input links a new run | integration | `cd backend && pytest tests/research/test_run_contract.py -k 'manifest or create or idempotency' -q` | ❌ W0 | ⬜ pending |
| 45-01-02 | 01 | 1 | AF-REQ-04 | T-45-02 | Every attempt and lineage edge is retained; immutable facts reject UPDATE/DELETE | integration | `cd backend && pytest tests/research/test_run_contract.py -k 'candidate or lineage or append_only' -q` | ❌ W0 | ⬜ pending |
| 45-01-03 | 01 | 1 | AF-REQ-10 | T-45-03 | Replay verifies stored manifest, contiguous events, checkpoint, and artifact digests; mismatch fails closed | integration | `cd backend && pytest tests/research/test_run_contract.py -k 'replay or checkpoint or artifact' -q` | ❌ W0 | ⬜ pending |
| 45-01-04 | 01 | 1 | AF-REQ-16 | T-45-04 | Legal lifecycle transitions, duplicate requests, cooperative cancellation, restart recovery, and linked retry are durable | integration | `cd backend && pytest tests/research/test_run_contract.py -k 'lifecycle or cancel or retry or restart' -q` | ❌ W0 | ⬜ pending |
| 45-02-01 | 02 | 1 | AF-REQ-01, AF-REQ-04 | T-45-05 | Migration rollback/reapply, foreign keys, checks, unique sequences/keys, and immutable triggers hold | SQLite migration | `cd backend && pytest tests/test_operational_migrations.py -k 'atomic or restart or phase45' -q` | ⚠ existing file; extend | ⬜ pending |
| 45-02-02 | 02 | 1 | AF-REQ-10, AF-REQ-16 | T-45-06 | Strict DTOs reject extras/oversized/client authority fields; public projections redact paths/raw diagnostics; conflicts map to 409 | API integration | `cd backend && pytest tests/api/test_run_api.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/research/test_run_contract.py` — manifest, candidate, event, checkpoint, artifact, lifecycle, idempotency, restart, and cancellation contracts.
- [ ] `backend/tests/api/test_run_api.py` — strict DTO, safe projection, route status/error, event-history, and server-owned identity contracts.
- [ ] Extend `backend/tests/test_operational_migrations.py` — Phase 45 rollback, trigger, FK, CHECK, unique sequence/idempotency, and reapply coverage.
- [ ] Deterministic test clock and temporary managed artifact-root fixture following existing `tmp_path` research fixtures.

---

## Required Focused Scenarios

1. Concurrent create calls with the same principal/key/digest yield one run and one `run_created` event; same key/different digest yields conflict.
2. Competing transitions with one expected version commit only one transition; the loser appends no event.
3. Event sequence is contiguous and idempotency keys/checksums are unique; publication occurs only after commit.
4. Duplicate and failed candidate attempts remain in the ledger; parent links cannot cross runs.
5. Every legal lifecycle edge succeeds and every illegal edge rolls back without status/version/event-count mutation.
6. Missing candidate, future sequence, stale snapshot digest, changed artifact size, or changed artifact bytes causes checkpoint failure and no cursor advance.
7. A crash after database commit but before publication still replays the committed event; an invalid cursor cannot resume after restart.
8. Cancellation before start, at a candidate boundary, after terminal completion, and repeated with one key remains durable and non-contradictory.
9. Retry returns the existing child for the same retry key; changed declared input creates a new snapshot/run and leaves the parent unchanged.
10. Static/runtime guard confirms Phase 45 does not import broker/order/portfolio/monitor or invoke factor evaluation/provider/OOS/promotion.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|---|---|---|---|
| None | — | All Phase 45 contract behaviors have focused automated verification; browser/SSE work is Phase 50. | — |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
