---
phase: 45-durable-governed-run-contract
verified: 2026-08-08
status: passed
score: 100
behavior_unverified: []
overrides_applied: []
human_verification: []
---

# Phase 45 — Durable Governed Run Contract — Verification

> Goal-backward, behavior-level verification of the Phase 45 durable run
> contract. Verifier: independent of the executor agents. Read-only; only this
> VERIFICATION file was written.

## Verdict

**PASSED** — score 100/100. All four Phase 45 requirements (AF-REQ-01,
AF-REQ-04, AF-REQ-10, AF-REQ-16) are satisfied at the behavior level, backed by
143 passing tests across the three required suites plus 52 boundary-guard tests,
and corroborated by direct code-level spot checks of the schema, repository,
service, worker adapter, API, and projections. No human-only items; no
overrides. Working tree clean; `frontend/src/pages/Watchlist.tsx` untouched.

## Test Totals (recorded)

Command (run by verifier):
`cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py tests/research/test_run_contract.py tests/api/test_run_api.py -x -q`

```
.................................................. [ 50%]
..................................................  [100%]
143 passed in 19.64s
```

Per-file (collected):
| Suite | Tests | Status |
|-------|------:|--------|
| `tests/test_operational_migrations.py` | 18 | passed |
| `tests/research/test_run_contract.py` | 89 | passed |
| `tests/api/test_run_api.py` | 36 | passed |
| **Subtotal (required batch)** | **143** | **all passed** |

Boundary guard (run by verifier, separate file):
`cd backend && .venv/bin/python -m pytest tests/test_phase45_guard.py -q` → **52 passed in 1.91s**

## Requirement-by-Requirement Evidence

| REQ | Phase scope | Status | Evidence (file:line) |
|-----|-------------|--------|----------------------|
| **AF-REQ-01** immutable run spec; changing inputs creates a new run | 45-01 | PASS | `run_contract.py:58` `REQUIRED_MANIFEST_GROUPS` = 11 groups (dsl, grammar, vocabulary, policy, budgets, objective, universe, measured_window, fold_geometry, code_manifest, data_manifest); `validate_manifest` (run_contract.py:81-93) fails closed on missing/empty group; `freeze_input_snapshot` (run_contract.py:140) canonicalizes + digests server-side; `ResearchInputSnapshot`/`AlphaFactoryRun` frozen dataclasses (run_contract.py:96,182); `create_alpha_run` (repository.py:1413) does idempotency check **before** write and raises `AlphaRunConflictError` on changed digest (repository.py:1459-1463); identity immutability trigger (migrations.py:1930-1941) guards id/principal/key/snapshot/digests/retry linkage/created_at. |
| **AF-REQ-04** retain every attempted candidate w/ lineage | 45-02 | PASS | `CANDIDATE_STATUSES` = 8 outcomes (run_contract.py:230-239); `append_candidate_attempt` (repository.py:1980) one row per attempt, no `INSERT OR IGNORE`/expression-uniqueness erasing duplicates; `append_candidate_lineage` (repository.py:2053) same-run FK for both child+parent; append-only no_update/no_delete triggers (migrations.py:1967-1987); `projections.candidate` (projections.py:88) exposes ordinal/digest/expression/seed/step/status; `list_candidates` (repository.py:2112) principal-scoped. |
| **AF-REQ-10** replay reproduces frozen identity; missing manifest fails closed | 45-01/02/04 | PASS | `get_run_snapshot` (repository.py:1853) read-only frozen retrieval; `list_run_events` (repository.py:1819) ordered by (seq,id); `ResearchRunService.replay` read-only; `checkpoint_state_checksum` (run_contract.py:324) + `validate_checkpoint` fail-closed on stale/future/gap/missing-candidate/bad-checksum; `append_run_event` (repository.py:1873) `BEGIN IMMEDIATE` + `last_event_seq+1` sequencing; replay is deterministic across a fresh repository/service instance (covered by restart tests). |
| **AF-REQ-16** workbench states, cooperative cancel, idempotent retry, checkpointed resume; never overwrites an earlier run or repeats a committed side effect | 45-03/04 | PASS | `LIFECYCLE_EDGES` explicit legal matrix (run_service.py:121-126); `transition_alpha_run` guarded `WHERE id=? AND principal=? AND status=? AND transition_version=?` under `BEGIN IMMEDIATE`, illegal/stale/cross-principal → 0 rows, rollback, no event (repository.py:1587-1694); `cancel_alpha_run` cooperative + idempotent (repository.py:1696-1727); `retry_alpha_run` creates linked child with `retry_of_run_id`, parent never mutated (repository.py:1789-1817); opaque attempt token — only SHA-256 persisted (run_service.py:209-218), validated by `_validate_attempt_token` (run_service.py:293-327); four bounded progress counters (repository.py:1729-1787). |

## Code-Level Spot Checks (file:line)

1. **Schema — 7 tables + immutability triggers** (`operational/migrations.py`):
   `research_alpha_input_snapshots` (1872), `research_alpha_runs` (1898),
   `research_alpha_candidate_attempts` (1945), `research_alpha_candidate_lineage`
   (1972), `research_alpha_events` (1989), `research_alpha_checkpoints` (2014),
   `research_alpha_artifacts` (2033). All FKs `ON DELETE RESTRICT`; append-only
   `no_update`/`no_delete` triggers on each; run identity columns guarded by
   `research_alpha_runs_guard_cursor` (1930-1941); `UNIQUE (principal,
   idempotency_key)` (1921), `UNIQUE (run_id, seq)` + `UNIQUE (run_id,
   idempotency_key)` on events (2005-2006), `UNIQUE (run_id,
   checkpoint_version)` (2025). 7 tables confirmed via `grep -c`.

2. **Repository create/get/replay** (`repository.py`): `create_alpha_run`
   (1413) atomic snapshot+run+`run_created` event, server-allocated seq 1,
   cursor advanced to `last_event_seq=1, transition_version=1` (1553-1558);
   `get_alpha_run` (1563) principal predicate → identical `None` boundary for
   unknown and cross-principal; `append_run_event` (1873) contiguous sequence +
   idempotency-checksum conflict.

3. **Value objects** (`run_contract.py`): frozen `@dataclass(frozen=True,
   slots=True)` for `ResearchInputSnapshot` (97), `AlphaFactoryRun` (183),
   `AlphaRunEvent` (208), `AlphaArtifactReference` (255), `AlphaCandidateAttempt`
   (275), `AlphaCandidateLineage` (296), `AlphaRunCheckpoint` (309);
   `MAX_INLINE_CHECKPOINT_BYTES = 16 * 1024` (227); `attempt_token_digest` (366)
   + `validate_progress_counters` (377) + `PROGRESS_COUNTERS` (363).

4. **Worker token fence** (`run_worker.py`): `ResearchRunWorkerAdapter`
   requires `attempt_token` on every callback (raises ValueError if absent);
   `request_transition` verifies token+version via
   `service._validate_attempt_token` **before** any transition, stale/invalid →
   `None` (run_worker.py:72-108); module imports only `run_service` (TYPE_CHECKING).

5. **API routes** (`api/research_alpha.py`): POST/GET `/api/research/alpha/runs`,
   `/runs/{id}/replay`, `/runs/{id}/retry`, `/runs/{id}/cancel`,
   `/runs/{id}/events`, `/runs/{id}/candidates`, GET/POST `/runs/{id}/progress`.
   Conflict mapping: 422 `preflight_failed` (84-90), 409 idempotency conflict
   (92-93, retry 145-152), 404 for unknown/cross-principal. Resolves
   `app.state.research_run_service` + `request.state.reviewer_principal`.

6. **Projections deny-by-default** (`projections.py`): every projector is a
   hand-built allowlist. `run` (14), `snapshot` (36), `event` (64), `replay`
   (79), `candidate` (88), `progress` (104). No projection exposes `principal`,
   `idempotency_key`, raw payload, policy internals (only `policy_version` +
   `policy_digest`), filesystem paths, attempt-token, or diagnostics.

7. **Boundary guard** (`tests/test_phase45_guard.py`): AST import/call/attribute
   scan over the complete Phase 45 module graph rejects broker/order/portfolio/
   monitor/provider/evaluator/OOS/promotion/queue/second-DB tokens
   (_PROHIBITED_IMPORT_TOKENS at 48, _PROHIBITED_CALL_RE at 76,
   _PROHIBITED_ATTR_RE at 87); runtime raising-fake collaborators for create/
   replay/retry/cancel/history/progress (257-371); no-SSE, no-Watchlist, no-new-router,
   main.py wiring checks. **52 passed.**

## Watchlist Proof

- `git status --short` → **clean** (no output).
- `git log --oneline -15` → the 15 most recent commits are all `feat/test/fix/docs(45…)` Phase 45 work; **no frontend/Watchlist commit present**.
- `frontend/src/pages/Watchlist.tsx` was never read or touched by the verifier (per constraint).

## SUMMARY Cross-Checks (2-3 claims vs code)

1. **45-03 SUMMARY: "89 tests in test_run_contract.py, 18 in migrations = 107"** —
   CONFIRMED. Collected counts: 89 run_contract + 18 migrations = 107; full
   3-file batch = 143 (adds 36 run_api). All pass.
2. **45-04 SUMMARY: "52 guard tests + 36 API via focused -k filter"** —
   CONFIRMED. `test_phase45_guard.py` → 52 passed; `test_run_api.py` collected =
   36. 409 conflict mapping exists at `research_alpha.py:92-93` (create) and
   `145-152` (retry), matching the "Rule 2 follow-up" claim.
3. **45-02 SUMMARY: "exact server-derived content-addressed key
   `research_artifacts/alpha_runs/{run_id}/{sha256}.json`"** — CONFIRMED at
   `run_contract.py:271` `AlphaArtifactReference.expected_relative_path`, and
   `AlphaRunArtifactService` server-derives the key (verified by the
   content-addressed test selection in the 89-test run_contract suite).

## Observations (informational; not failures; no human_items)

- **SHA-256 CHECK granularity:** The SQL-layer digest constraints are
  `CHECK (length(col) = 64)` (migrations.py:1876-1889 etc.), i.e. length-64,
  not a lowercase-hex GLOB. Lowercase-hex integrity is enforced one layer up by
  `validate_sha256` regex `[0-9a-f]{64}` (run_contract.py:44,75-78) and
  `_wf_sha256` (repository.py:59-61), and all digests originate from
  `sha256().hexdigest()` (lowercase). Behavior holds; the SUMMARY phrasing
  "lowercase SHA-256 CHECKs" describes the combined invariant, not a SQL GLOB.
- **Traceability:** AF-REQ-01 and AF-REQ-04 are listed "Pending" in the
  REQUIREMENTS.md traceability table while AF-REQ-10/AF-REQ-16 are "Complete",
  although all four are behaviorally satisfied by Phase 45 and claimed by the
  45-01/45-02 plans. This is a STATE/traceability update item (the 45-04 summary
  notes STATE.md was intentionally left for the state-update step), not a
  behavior gap. No code change required.

## human_items

None. `45-VALIDATION.md` explicitly states "All Phase 45 contract behaviors
have focused automated verification" with no manual-only entries; browser/SSE
work is deferred to Phase 50.
