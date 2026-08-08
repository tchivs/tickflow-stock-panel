# Phase 45 UAT — Durable Governed Run Contract

**Phase:** 45 · **Requirements:** AF-REQ-01, AF-REQ-04, AF-REQ-10, AF-REQ-16 · **Date:** 2026-08-08
**Verifier:** `.planning/phases/45-durable-governed-run-contract/45-VERIFICATION.md` — **passed** (score 100, 0 human_items)

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | Immutable run specification — create with full manifest; changing inputs creates new run | ✅ | AF-REQ-01: REQUIRED_MANIFEST_GROUPS=11 (run_contract.py:58); validate_manifest fail-closed (:81); create_alpha_run idempotent-before-write + AlphaRunConflictError on changed digest (repository.py:1413,1459); identity immutability trigger (migrations.py:1930) |
| UAT-2 | Append-only candidate ledger — retains every attempt (invalid/duplicate/failed/rejected/admitted) with lineage | ✅ | AF-REQ-04: CANDIDATE_STATUSES=8 (run_contract.py:230); append_candidate_attempt one-row-per-attempt no INSERT-OR-IGNORE (repository.py:1980); same-run lineage FK (:2053); append-only triggers (migrations.py:1967) |
| UAT-3 | Replay from stored artifacts — same inputs produce same candidates/order/checksums; missing manifest fail-closed | ✅ | AF-REQ-10: get_run_snapshot read-only (repository.py:1853); ordered list_run_events (:1819); checkpoint checksum validation (run_contract.py:324); BEGIN IMMEDIATE last_event_seq+1 sequencing (repository.py:1873,1910) |
| UAT-4 | Guarded lifecycle — idempotent retry, cooperative cancel, checkpointed resume, never overwrites earlier run | ✅ | AF-REQ-16: LIFECYCLE_EDGES matrix (run_service.py:121); guarded transition WHERE id/principal/status/version (repository.py:1641); idempotent cancel (:1696); linked retry child parent-never-mutated (:1789); opaque token SHA-256-only (run_service.py:209); 4 bounded progress counters (repository.py:1729) |
| UAT-5 | Typed principal-scoped API + safe projections + research-only boundary guard | ✅ | POST/GET /api/research/alpha/runs + replay/retry/cancel/events/candidates/progress; 422 preflight / 409 conflict / 404 unknown+cross-principal; 6 deny-by-default projection allowlists (projections.py:14-104); AST import/call/attr + runtime boundary guard 52 passed |
| UAT-6 | Zero execution-surface violations; strategy_cache/portfolio untouched; Watchlist zero-touch | ✅ | Boundary guard green (research-only, no broker/order/position mutation); git status clean; no frontend commit in log |

## Verdict

**UAT passed** — all 6 acceptance criteria satisfied. 143 contract/migration/API tests + 52 boundary guard = 195 passed, 0 failures, 0 human_items. Foundation ready for Phase 46 (Deterministic Alpha Factory Core).
