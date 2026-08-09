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
| **Config file** | `backend/pyproject.toml` (`asyncio_mode = "auto"`, importlib mode) |
| **Quick run command** | `cd backend && pytest tests/test_operational_migrations.py tests/research/test_run_contract.py tests/api/test_run_api.py tests/test_phase45_guard.py -q` |
| **Full suite command** | Not run during Phase 45 planning/execution; use only the focused commands below |
| **Estimated runtime** | <30 seconds for focused selections |

---

## Sampling Rate

- **After every task commit:** Run the task's focused command from the map; do not run broad validation.
- **After every plan wave:** Run only the Phase 45 focused selections plus migration checks listed below.
- **Before `/gsd:verify-work`:** Re-run all eight focused task commands and the complete-module guard; broad backend validation is outside this plan.
- **Max feedback latency:** 30 seconds for focused tests

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 45-01-01 | 01 | 1 | AF-REQ-01 | T-45-01, T-45-02, T-45-12 | Server-frozen D-04 manifest, `preflight_failed` run validation, deterministic clock/artifact-root fixtures, same-principal idempotency, and safe cross-principal boundary | integration | `cd backend && pytest tests/research/test_run_contract.py -k 'manifest or create or idempotency or replay or deterministic_clock or artifact_root' -q && pytest tests/api/test_run_api.py -k 'create or replay or principal or preflight' -q && pytest tests/test_operational_migrations.py -k 'atomic or restart or phase45' -q` | ❌ W0 | ⬜ pending |
| 45-01-02 | 01 | 1 | AF-REQ-01, AF-REQ-10 | T-45-08, T-45-12 | `AlphaSnapshotDTO` exposes every frozen D-04 group in bounded safe form; principal-scoped get/replay and identical not-found boundary | API integration | `cd backend && pytest tests/research/test_run_contract.py -k 'schema or projection or manifest or replay or preflight' -q && pytest tests/api/test_run_api.py -k 'projection or strict or principal or cross_principal or not_found' -q` | ❌ W0 | ⬜ pending |
| 45-02-01 | 02 | 2 | AF-REQ-04, AF-REQ-10 | T-45-02, T-45-03, T-45-12 | All eight candidate outcomes including `invalid`, duplicate attempts, append-only lineage/events, contiguous sequences, commit-before-publish, and principal-scoped histories | integration | `cd backend && pytest tests/research/test_run_contract.py -k 'candidate or lineage or append_only or invalid or principal' -q && pytest tests/test_operational_migrations.py -k 'atomic or restart or phase45' -q` | ❌ W0 | ⬜ pending |
| 45-02-02 | 02 | 2 | AF-REQ-10, AF-REQ-16 | T-45-04, T-45-05, T-45-12 | Exact digest-derived artifact key, 16 KiB canonical UTF-8 inline boundary, verified large artifact, fail-closed replay/checkpoint, and principal-safe reads | integration | `cd backend && pytest tests/research/test_run_contract.py -k 'replay or checkpoint or artifact or inline or content_addressed or principal' -q` | ❌ W0 | ⬜ pending |
| 45-03-01 | 03 | 3 | AF-REQ-16 | T-45-06, T-45-07, T-45-12 | Legal lifecycle matrix, `preflight_failed` versus candidate `invalid`, principal-scoped retry/cancel, idempotency, linked retry, and cancellation races | integration | `cd backend && pytest tests/research/test_run_contract.py -k 'lifecycle or cancel or retry or preflight or principal' -q` | ❌ W0 | ⬜ pending |
| 45-03-02 | 03 | 3 | AF-REQ-16 | T-45-08, T-45-12 | Opaque attempt token with persisted SHA-256 only, expected-version fencing/invalidation, restart recovery, and four bounded progress counters without fold evaluation | integration | `cd backend && pytest tests/research/test_run_contract.py -k 'restart or resume or worker or token or progress or retry or cancel' -q` | ❌ W0 | ⬜ pending |
| 45-04-01 | 04 | 4 | AF-REQ-10, AF-REQ-16 | T-45-08, T-45-10, T-45-11, T-45-12 | Shared app-state typed API for all operations, bounded history/progress, strict authority rejection, principal-scoped reads/writes, and same not-found boundary | API integration | `cd backend && pytest tests/api/test_run_api.py -k 'api or history or progress or retry or cancel or principal or cross_principal or redaction or strict' -q` | ❌ W0 | ⬜ pending |
| 45-04-02 | 04 | 4 | AF-REQ-10, AF-REQ-16 | T-45-09, T-45-12 | Complete Phase 45-owned module-graph AST/runtime guard rejects execution/provider/evaluator/OOS/promotion/queue/second-DB paths and verifies cross-principal boundary | security/integration | `cd backend && pytest tests/test_phase45_guard.py -q && pytest tests/api/test_run_api.py -k 'principal or cross_principal or progress or retry or cancel' -q` | ❌ W0 | ⬜ pending |
*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/research/test_run_contract.py` — manifest, candidate, event, checkpoint, artifact, lifecycle, idempotency, restart, cancellation, token/version, progress, and cross-principal contracts.
- [ ] `backend/tests/api/test_run_api.py` — strict DTO, safe projection, route status/error, event/candidate/progress history, app-state mounting, principal boundary, and server-owned identity contracts.
- [ ] Extend `backend/tests/test_operational_migrations.py` — Phase 45 rollback, trigger, FK, CHECK, unique sequence/idempotency, progress columns, and reapply coverage.
- [ ] `backend/tests/research/conftest.py` + `backend/tests/api/conftest.py` — deterministic test clock fixture with fixed timestamps used by every Wave 0 task.
- [ ] `backend/tests/research/conftest.py` + `backend/tests/api/conftest.py` — temporary managed artifact-root fixture under `tmp_path`, exact `research_artifacts/alpha_runs/{run_id}/{sha256}.json` path assertions, and traversal rejection.
- [ ] `backend/tests/test_phase45_guard.py` — complete owned-module graph enumeration including migration, all research modules, API, main wiring, and newly created modules.

---
## Required Focused Scenarios

1. Concurrent create calls with the same server-resolved principal/key/digest yield one run and one `run_created` event; same key/different digest yields conflict.
2. Malformed/incomplete run-level input returns `preflight_failed` before queueing; a generated candidate validation failure remains an `invalid` candidate outcome.
3. Competing transitions with one expected version commit only one transition; the loser appends no event, candidate, checkpoint, progress, or success side effect.
4. Event sequence is contiguous and idempotency keys/checksums are unique; publication occurs only after commit.
5. Duplicate, invalid, and failed candidate attempts remain in the ledger; parent links cannot cross runs and candidate/event history is principal-scoped.
6. Inline checkpoint JSON at `MAX_INLINE_CHECKPOINT_BYTES = 16 * 1024` is canonical UTF-8; oversized state uses exactly `research_artifacts/alpha_runs/{run_id}/{sha256}.json`, and client paths/traversal are rejected.
7. Missing candidate, future sequence, stale snapshot digest, changed artifact size/type, changed artifact bytes, wrong content-addressed key, or bad cursor checksum causes checkpoint failure and no cursor advance.
8. A crash after database commit but before publication still replays the committed event; an invalid cursor cannot resume after restart.
9. A running transition issues opaque `attempt_token` while only SHA-256 is stored; callbacks require token plus expected `transition_version`, and cancel/terminal/retry/version changes invalidate old tokens.
10. Progress persists/reports `candidate_attempts_total`, `candidate_attempts_completed`, `folds_total`, and `folds_completed` with bounded monotonic updates and zero declared fold totals; no fold evaluation occurs.
11. Cancellation before start, at a candidate boundary, after terminal completion, and repeated with one key remains durable and non-contradictory; cross-principal cancel/retry writes share the unknown-run 404 boundary.
12. Retry returns the existing child for the same retry key; changed declared input creates a new snapshot/run and leaves the parent unchanged; all get/replay/event/candidate/progress reads are principal-scoped.
13. Static/runtime guard enumerates the complete Phase 45-owned module graph and confirms no broker/order/portfolio/monitor/live-execution/provider/factor-evaluation/OOS/promotion/external-queue/second-database path.
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
