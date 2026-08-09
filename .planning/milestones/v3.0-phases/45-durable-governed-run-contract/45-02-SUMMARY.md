# Plan 45-02 Summary: Append-Only Candidate/Lineage/Event Foundation

**Plan:** 45-02 (wave 2)
**Phase:** 45-durable-governed-run-contract
**Status:** Complete
**Date:** 2026-08-08

## Objective

Expand the proven Phase 45 tracer into the durable append-only ledger and fail-closed recovery contract: candidate attempts and lineage, event sequencing/idempotency, immutable managed artifacts, and bounded checkpoint cursors. This satisfies AF-REQ-04 and AF-REQ-10 while preserving D-03, D-05, D-07, and D-08. Facts are stored only; no candidate generation, evaluation, or provider invocation occurs.

## Commits

| Hash | Message |
|------|---------|
| `037fcfe` | feat(45-02): append-only candidate/lineage/event ledger with idempotent sequencing |
| `78e602d` | feat(45-02): verified artifacts and bounded checkpoint replay recovery |

## What Was Delivered

### Task 45-02-01: Candidate, lineage, and event facts

**`backend/app/research/run_contract.py`** — new value objects and helpers:

- `AlphaCandidateAttempt` — immutable projection of one append-only candidate attempt (id, run_id, attempt_ordinal, candidate_digest, canonical_expression, ast/shape signatures, dsl_version, operation, seed, step, status, reason, evidence_artifact_id, created_at).
- `AlphaCandidateLineage` — immutable parent/child lineage edge.
- `AlphaArtifactReference` — content-addressed artifact reference with `expected_relative_path` property computing exactly `research_artifacts/alpha_runs/{run_id}/{checksum_sha256}.json`.
- `AlphaRunCheckpoint` — recovery cursor projection.
- `CANDIDATE_STATUSES` — all 8 required outcomes: invalid, duplicate, low_coverage, failed, rejected, admitted, cancelled, budget_exhausted.
- `MAX_INLINE_CHECKPOINT_BYTES = 16 * 1024`, `CHECKPOINT_SCHEMA_VERSION`, `ARTIFACT_SCHEMA_VERSION` constants.
- `event_checksum()` — semantic SHA-256 over payload + idempotency key + event type (same fact → same digest; changed fact → conflict).
- `checkpoint_state_checksum()` — canonical SHA-256 over run/version/seq/stage/digests/candidate-IDs/summary/frontier-artifact.

**`backend/app/research/repository.py`** — new append-only methods:

- `append_run_event()` — allocates a contiguous run-scoped sequence under `BEGIN IMMEDIATE` via the run cursor's `last_event_seq + 1` (not an unlocked `MAX(seq)`). Idempotency on `(run_id, idempotency_key)`: same semantic checksum returns original event; changed checksum raises `AlphaRunConflictError`.
- `append_candidate_attempt()` — one row per attempt; no `INSERT OR IGNORE` or expression-uniqueness rule erases a duplicate attempt (AF-REQ-04, D-05). An `invalid` candidate is distinct from run-level `preflight_failed`.
- `append_candidate_lineage()` — same-run FK validation for both child and parent; rejects cross-run and self-lineage.
- `list_candidates()` — principal-scoped ordered read (same empty boundary for unknown and cross-principal).
- `append_artifact()` — enforces the exact server-derived content-addressed key.
- `append_checkpoint()` / `get_latest_valid_checkpoint()` — bounded recovery cursor persistence and read.
- `list_run_events()` — extended with optional `principal` parameter for T-45-12 boundary.

**`backend/app/research/run_service.py`** — service orchestration:

- `append_event()` — principal-scoped event append with commit-before-publish (publisher exception does not erase the committed event).
- `append_candidate()` — principal-scoped candidate-attempt append.
- `validate_checkpoint()` — fail-closed D-07 cursor validation (snapshot/manifest digest match, future-sequence rejection before contiguity check, missing candidate rejection, frontier artifact verification wrapped as `AlphaCheckpointValidationError`, state checksum recompute).
- `validate_inline_checkpoint_payload()` — 16 KiB bound; rejects oversized, non-UTF-8, non-JSON, and pickle payloads.
- `replay()` — extended with `include_candidates` for deterministic read-only replay.

**`backend/app/research/artifacts.py`** — Alpha run artifact namespace:

- `AlphaRunArtifactService` — server-derived content-addressed keys (`research_artifacts/alpha_runs/{run_id}/{sha256}.json`), exclusive canonical-byte writes, read-side `verify_artifact()` recomputing content type, byte size, and lowercase SHA-256.
- `AlphaArtifactVerificationError` — fail-closed verification failure.

### Task 45-02-02: Verified artifacts and bounded checkpoint replay

Tests cover: exact content-addressed path, client-supplied path rejection, verify_artifact missing/changed-bytes/bad-size/path-traversal rejection, `AlphaArtifactReference.expected_relative_path`; inline checkpoint 16 KiB exact-bound accepted, oversized/non-UTF-8/non-JSON/pickle rejected; checkpoint stale snapshot/manifest digest, future event sequence, non-contiguous, missing referenced candidate, bad cursor checksum, cross-principal access all rejected; valid checkpoint recovered after fresh repository restart; frontier artifact verified-then-tampered rejected; deterministic read-only replay with candidates across restart.

### Migration test coverage (`backend/tests/test_operational_migrations.py`)

- `test_phase45_candidate_lineage_artifact_checkpoint_constraints` — candidate/lineage/artifact/checkpoint tables: CHECK enums + sha256 + FK graph + UNIQUE + immutability triggers.
- `test_phase45_candidate_lineage_same_run_fk_enforced` — lineage FK graph confirmation (same-run invariant enforced at repository layer).

## Test Totals

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/research/test_run_contract.py` | 70 | passed |
| `tests/test_operational_migrations.py` | 7 (phase45 + atomic) | passed |
| **Total (2 files)** | **77** | **all passed** |

### Per-task verification (all green)

```
# Task 45-02-01
pytest tests/research/test_run_contract.py -k 'candidate or lineage or append_only or invalid or principal' -q
→ 19 passed, 40 deselected

pytest tests/test_operational_migrations.py -k 'atomic or restart or phase45' -q
→ 7 passed, 11 deselected

# Task 45-02-02
pytest tests/research/test_run_contract.py -k 'replay or checkpoint or artifact or inline or content_addressed or principal' -q
→ 32 passed, 27 deselected

# Wave boundary
pytest tests/test_operational_migrations.py tests/research/test_run_contract.py -q
→ 77 passed
```

## Must-Have Truths (verified)

- ✅ Every candidate attempt — invalid, duplicate, low_coverage, failed, rejected, admitted, cancelled, budget_exhausted — remains queryable as an immutable fact with ordinal, reason, lineage, and evidence reference. Two attempts with the same canonical expression remain two rows when attempt identity differs.
- ✅ Events have contiguous run-scoped monotonic sequences (1 through latest) and durable idempotency/checksum identity; the same committed fact is not reinserted by a repeated delivery.
- ✅ Replay and recovery reject missing, future, non-contiguous, stale, or checksum-mismatched candidate/event/checkpoint/artifact references without advancing work.
- ✅ A valid checkpoint can be written only after referenced facts commit and recovered after constructing a new repository/service instance.
- ✅ Inline checkpoint bytes at exactly 16 KiB are accepted only as canonical UTF-8 JSON; oversized, malformed, client-supplied paths, or unmanaged artifact keys are rejected before persistence.
- ✅ Cross-principal reads return the same safe not-found boundary as an unknown run for candidates, events, and checkpoints.

## Threat Model Mitigations

- **T-45-02 (Tampering/Repudiation):** Immutable triggers on candidate/lineage/artifact/checkpoint tables; append-only attempt identity preserves every outcome; FK RESTRICT; lowercase digest CHECKs.
- **T-45-03 (Tampering/Denial):** `BEGIN IMMEDIATE` sequence allocation via `last_event_seq + 1`; guarded run cursor; `(run_id, seq)` and `(run_id, idempotency_key)` uniqueness; semantic checksum conflict on changed payload.
- **T-45-04 (Tampering/Information disclosure):** Run-bound managed relative paths (`research_artifacts/alpha_runs/{run_id}/{sha256}.json`), exclusive writes, recomputed size/type/SHA-256, path-traversal hardening, fail-closed replay.
- **T-45-05 (Elevation/Code execution):** Typed bounded JSON cursor (16 KiB); verified artifact references; pickle/executable/raw-frame/prompt payloads excluded.
- **T-45-12 (Information disclosure):** Principal predicates on every candidate/event/checkpoint history query; same safe not-found boundary for cross-principal.

## Deviations

None. The plan was followed exactly: test-first per task, atomic commits via explicit `git add`, zero new runtime dependencies, Watchlist zero-touch, clean working tree.

## Files Modified

| File | Action |
|------|--------|
| `backend/app/research/run_contract.py` | Modified (value objects, constants, checksum helpers) |
| `backend/app/research/repository.py` | Modified (candidate/lineage/event/artifact/checkpoint methods, principal scoping) |
| `backend/app/research/run_service.py` | Modified (orchestration, validation, fail-closed recovery) |
| `backend/app/research/artifacts.py` | Modified (AlphaRunArtifactService, verify_artifact) |
| `backend/tests/research/test_run_contract.py` | Modified (candidate/lineage/event/artifact/checkpoint/replay tests) |
| `backend/tests/test_operational_migrations.py` | Modified (candidate/lineage/artifact/checkpoint constraint tests) |
