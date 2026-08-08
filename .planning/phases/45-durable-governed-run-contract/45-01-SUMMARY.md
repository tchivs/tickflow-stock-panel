# Plan 45-01 Summary: Immutable Run/Input Snapshot + Append-Only Foundation

**Plan:** 45-01 (wave 1)
**Phase:** 45-durable-governed-run-contract
**Status:** Complete
**Date:** 2026-08-08

## Objective

Create the first production-quality vertical slice of the Phase 45 durable governed run contract: bounded researcher intent → server-frozen manifest/snapshot → durable run and `run_created` event → typed inspect/replay read. This proves the Phase 45 architecture before candidate, checkpoint, retry, and worker expansions.

## Commits

| Hash | Message |
|------|---------|
| `bbe3e1e` | feat(45-01): add Phase 45 durable Alpha run SQLite schema |
| `5b34ed0` | feat(45-01): frozen snapshot value objects + repository create/get/replay seam |
| `13d411d` | feat(45-01): service seam + strict DTOs + safe projections + typed routes |
| `9eb06a2` | test(45-01): harden schema/projection/preflight contract coverage |
| `9d2cb0b` | fix(45-01): restore PortfolioRepository import in API conftest |

## What Was Delivered

### Migration (`backend/app/operational/migrations.py`)

Appended one additive Phase 45 migration (31st entry) with seven tables:

- `research_alpha_input_snapshots` — immutable server-frozen D-04 snapshot with canonical JSON, manifest/snapshot SHA-256, and all component digests (DSL, grammar, vocabulary, policy, data, partition, membership, code, build, dependency). INSERT-only triggers.
- `research_alpha_runs` — immutable identity + guarded lifecycle cursor. Identity columns (id, principal, idempotency_key, snapshot binding, manifest digest, retry linkage, created_at) are guarded by a `BEFORE UPDATE ... FOR EACH ROW WHEN` trigger; only status/transition_version/last_event_seq/counters/timestamps may UPDATE. DELETE blocked.
- `research_alpha_candidate_attempts` — append-only per-attempt ledger (8 outcome statuses: invalid, duplicate, low_coverage, failed, rejected, admitted, cancelled, budget_exhausted).
- `research_alpha_candidate_lineage` — append-only parent/child edges with same-run FK.
- `research_alpha_events` — append-only lifecycle events with `UNIQUE (run_id, seq)` and `UNIQUE (run_id, idempotency_key)`, payload checksum, producer version.
- `research_alpha_checkpoints` — append-only recovery cursors bound to snapshot+manifest digests.
- `research_alpha_artifacts` — content-addressed artifact references with `UNIQUE (run_id, checksum_sha256, logical_kind)`.

All tables use `ON DELETE RESTRICT` FKs, lowercase SHA-256 CHECK constraints, immutability triggers, and replay indexes.

### Value objects (`backend/app/research/run_contract.py`)

`ResearchInputSnapshot`, `AlphaFactoryRun`, `AlphaRunEvent` frozen dataclasses; `freeze_input_snapshot()` validates manifest completeness (all 11 required D-04 groups non-empty), canonicalizes JSON, and derives component digests; `validate_sha256()`, `validate_manifest()`, canonical JSON/digest helpers; `RUN_STATUSES`, `TERMINAL_STATUSES`, `MANIFEST_SCHEMA_VERSION`, `PRODUCER_VERSION` constants.

### Repository (`backend/app/research/repository.py`)

Extended `ResearchRepository` with optional `clock`/`artifact_root` constructor params (backward-compatible), `AlphaClock` protocol, and:
- `create_alpha_run()` — atomic snapshot + queued run + sequence-1 `run_created` event transaction with idempotency check before write and conflict detection (`AlphaRunConflictError`).
- `get_alpha_run()` — principal-scoped read returning `None` for unknown/cross-principal.
- `list_run_events()` — ordered replay by `(seq, id)`.
- `get_run_snapshot()` — read-only frozen manifest/snapshot retrieval.

### Service (`backend/app/research/run_service.py`)

`ResearchRunService` — server-owned create/get/replay seam. `create()` validates intent, freezes snapshot (preflight failure → `AlphaRunPreflightError`, no queued row), delegates atomic commit, invokes optional post-commit publisher. `get()`/`replay()` are principal-scoped and read-only. `RunEventPublisher` protocol for optional D-05 notification.

### Schemas (`backend/app/research/run_schemas.py`)

`StrictAlphaModel` (`extra="forbid"`), `AlphaRunCreateRequest` (bounded idempotency key + manifest), `AlphaRunReadDTO`, `AlphaSnapshotDTO` (every D-04 group, no policy internals), `AlphaRunEventDTO`, `AlphaRunReplayDTO`. All digest fields validated with lowercase 64-hex pattern.

### Projections (`backend/app/research/projections.py`)

Deny-by-default `run()`, `snapshot()`, `event()`, `replay()` allowlists. No projection returns principal, idempotency key, raw payload, policy internals (thresholds), filesystem paths, secrets, or diagnostics.

### API (`backend/app/api/research_alpha.py`)

Three typed routes resolving `app.state.research_run_service`:
- `POST /api/research/alpha/runs` (201) — bounded intent → server-generated run ID, queued status, committed sequence 1; preflight failure → 422 with bounded `preflight_failed` reason.
- `GET /api/research/alpha/runs/{run_id}` (200/404) — safe run projection.
- `GET /api/research/alpha/runs/{run_id}/replay` (200/404) — read-only run + snapshot + ordered events.

Principal resolved from `request.state.reviewer_principal` (existing auth middleware).

### Main wiring (`backend/app/main.py`)

`ResearchRunService` constructed from `operational.database_path`, stored in `app.state.research_run_service`; typed router included.

### Test fixtures

- `backend/tests/research/conftest.py` — `DeterministicClock`, `alpha_artifact_root`, `alpha_run_repository` fixtures.
- `backend/tests/api/conftest.py` — `DeterministicClock`, `alpha_manifest`, `deterministic_clock`, `alpha_client` fixtures with test principal middleware.

## Test Totals

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/research/test_run_contract.py` | 18 | passed |
| `tests/api/test_run_api.py` | 12 | passed |
| `tests/test_operational_migrations.py` (phase45 + atomic) | 5 of 16 selected | passed |
| `tests/api/test_research_panels.py` (regression) | 21 | passed |
| **Total (4 files)** | **67** | **all passed** |

## Verification Commands (all green)

```
cd backend && pytest tests/research/test_run_contract.py -k 'manifest or create or idempotency or replay or deterministic_clock or artifact_root' -q
→ 11 passed, 7 deselected

cd backend && pytest tests/api/test_run_api.py -k 'create or replay or principal or preflight' -q
→ 11 passed, 1 deselected

cd backend && pytest tests/test_operational_migrations.py -k 'atomic or restart or phase45' -q
→ 5 passed, 11 deselected
```

Task 45-01-02 selections also green:
```
pytest tests/research/test_run_contract.py -k 'schema or projection or manifest or replay or preflight' -q  → 13 passed
pytest tests/api/test_run_api.py -k 'projection or strict or principal or cross_principal or not_found' -q   → 5 passed
```

## Must-Have Truths (verified)

- ✅ A bounded create request produces one server-owned immutable Alpha run and snapshot in `operational.db` before the run is queued.
- ✅ A fresh repository/service instance can read the same frozen snapshot and replay its committed event history without consulting current data or executing work.
- ✅ Repeating the same principal/idempotency key and canonical intent returns the original run; a changed declared input cannot mutate that run (conflict).
- ✅ Wave 0 tests use a deterministic clock and a temporary managed artifact root, so timestamp and artifact-path assertions are reproducible.

## Threat Model Mitigations

- **T-45-01 (Tampering/Elevation):** Server canonicalizes D-04 fields; `UNIQUE (principal, idempotency_key)` returns same fact or raises conflict; SQL trigger guards identity columns.
- **T-45-02 (Tampering/Repudiation):** Append-only triggers on all fact tables; lowercase digest CHECKs; FK RESTRICT; server sequence allocation; commit-before-return.
- **T-45-08 (Information disclosure):** Deny-by-default projections omit principal, policy internals, paths, secrets, raw diagnostics, payloads.
- **T-45-12 (Principal-scoped reads):** Principal resolved only from middleware state; repository predicates scope every read; same 404 boundary for unknown and cross-principal.
- **T-45-09 (Elevation via imports):** Static + runtime collaborator guard confirms no provider/OOS/promotion/broker/portfolio/monitor/execution import.

## Deviations

None. The plan was followed exactly: test-first per task, atomic commits, additive migration only, zero new runtime dependencies, Watchlist zero-touch.

## Orchestrator-Owned Unstaged

At completion, `git status --short` is clean — the 4 orchestrator-owned planning docs (45-02/03/04-PLAN.md, 45-VALIDATION.md) were committed separately by the orchestrator as `596f4e7 docs(45): finalize durable run contract plans`. All Phase 45-01 deliverables are committed and the working tree is clean.

## Files Modified/Created

| File | Action |
|------|--------|
| `backend/app/operational/migrations.py` | Modified (appended Phase 45 migration) |
| `backend/app/research/run_contract.py` | Created |
| `backend/app/research/repository.py` | Modified (constructor + Phase 45 methods) |
| `backend/app/research/run_service.py` | Created |
| `backend/app/research/run_schemas.py` | Created |
| `backend/app/research/projections.py` | Created |
| `backend/app/api/research_alpha.py` | Created |
| `backend/app/main.py` | Modified (import + app.state + router) |
| `backend/tests/research/conftest.py` | Modified (Wave 0 fixtures) |
| `backend/tests/api/conftest.py` | Modified (Alpha fixtures) |
| `backend/tests/research/test_run_contract.py` | Created |
| `backend/tests/api/test_run_api.py` | Created |
| `backend/tests/test_operational_migrations.py` | Modified (Phase 45 tests) |
