---
phase: 49
title: Research-Only Promotion Ticket (AF-REQ-15, AF-REQ-17)
status: passed
verified: 2026-08-09
verifier: VerifierP49
requirements: [AF-REQ-15, AF-REQ-17]
plans: [49-01, 49-02]
test_total: 848
---

# Phase 49 Verification — Research-Only Promotion Ticket

**Verdict: PASS** — AF-REQ-15 and AF-REQ-17 are fully delivered at the code level. The full regression batch is green (848 passed), both boundary guards hold, and the Watchlist out-of-scope guarantee is honored. No blocking human items.

## 1. Test batch

Command (run in `backend/`):

```
.venv/bin/python -m pytest tests/research/ tests/test_operational_migrations.py \
  tests/api/test_run_api.py tests/test_phase45_guard.py tests/test_phase49_guard.py -x -q
```

**Result: 848 passed in 149.95s** (no failures, no skips). Matches the orchestrator-reported regression total.

Phase 49 test-file counts (post-migrate, `--co -q`):

| File | Tests |
|---|---:|
| `tests/research/test_promotion_ticket.py` (49-01) | 28 |
| `tests/research/test_promotion_consume.py` (49-02-01/02) | 15 |
| `tests/research/test_research_promotion_api.py` (49-02-03) | 11 |
| `tests/test_phase49_guard.py` (49-02-04) | 10 |
| `tests/test_phase45_guard.py` (boundary evolution) | 52 |

Boundary guards run in isolation: `tests/test_phase45_guard.py tests/test_phase49_guard.py` → **62 passed**.

## 2. AF-REQ-by-AF-REQ code-level evidence

### AF-REQ-15 — compare + save immutable FactorRevision; changed draft rejected; unreviewed absent — PASS

| Sub-criterion | Evidence (file:line) | Status |
|---|---|:--:|
| Frozen ticket binds the **full evidence triple** (candidate identity + frozen fingerprints + admission verdict + selection_oos + reviewer + expiry + idempotency_key) | `PromotionTicket` dataclass: `app/research/promotion_service.py:43-78`; `issue_promotion_ticket` binds every column from persisted rows / live constant: `app/research/promotion_service.py:189-259`; DB columns + CHECKs (`admission_verdict='admitted'`, 64-byte digest CHECKs): `app/operational/migrations.py:2409-2444` | ✅ |
| Compare/inspect a proposal's expression/assumptions/evidence/gate trail/provenance | GET inspect route: `app/api/research_promotion.py:171-184`; deny-by-default read-only projection `_ticket_projection`: `app/api/research_promotion.py:55-77` | ✅ |
| **Save** a new immutable `FactorRevision` | `_mint_promoted_factor` mints a NEW `factor_id` + `revision_number=1` + `alpha_promoted` provenance via the atomic repository handoff (NOT `revise_factor`): `app/research/promotion_service.py:478-602`; `consume_promotion_ticket_atomic` INSERTs factor definition + revision + promotion snapshot + ticket flip under ONE `BEGIN IMMEDIATE`: `app/research/repository.py:3281-3431` | ✅ |
| Changed expression/explanation/provenance that no longer matches the issued draft is **rejected** | `_verify_conflicts` re-reads + byte-compares every bound immutable fact and routes drift to `conflicted` (hard reject): `canonical_expression`/`ast_signature`/`candidate_digest` `:348-357`, snapshot/manifest/vocab/grammar/membership/data digests `:326-342`, stage1 issued-draft digest `:442-454`, `gate_trail_digest` `:404-411`, admission verdict id/verdict/policy_version `:378-403`, live policy fingerprint `:361-375`; wall-clock / superseding Stage-1 proposal ⇒ re-issueable `expired` (refresh `:283-305`, consume `:651-678`) | ✅ |
| **Unreviewed output is absent from the formal catalog** | `FactorRegistry.list_current` excludes `alpha_exploratory`: `app/research/factor_registry.py:250-265` (filter `:264`); only promotion mints `kind != alpha_exploratory`; exploratory revisions remain locatable only via `find_exploratory_revision` (raw store): `app/research/factor_registry.py:267-285` | ✅ |
| Idempotent issue / refresh / consume (exactly-once) | `issue_promotion_ticket` under `BEGIN IMMEDIATE` + `UNIQUE(idempotency_key)` backstop: `app/research/repository.py:3105-3227`; idempotent consume reconnect returns existing revision verbatim: `consume_promotion_ticket` `:633-640`, atomic reconnect under lock `:3331-3339` | ✅ |
| Refresh = deterministic **re-read + re-verify**, NOT re-compute (R2) | `refresh_promotion_ticket`: `app/research/promotion_service.py:267-316`; the only live computation is `admission_policy_fingerprint()` re-read (`:361-375`) — no `run_admission` / panel load / chain compute / scoring | ✅ |
| Ticket table immutability | `guard_transition` BEFORE-UPDATE trigger freezes every identity/binding column (only status/conflict_reason_json/consumed_at/produced_factor_revision_id may mutate): `migrations.py:2458-2489`; `no_delete` trigger enforces append-only: `migrations.py:2452-2454` | ✅ |

### AF-REQ-15 SC2 (concurrent half) — at-most-one revision — PASS

| Sub-criterion | Evidence (file:line) | Status |
|---|---|:--:|
| Partial unique index = final at-most-one gate across distinct tickets | `CREATE UNIQUE INDEX ux_promotion_tickets_consumed_candidate … WHERE status='consumed'`: `migrations.py:2449-2451`; present on a migrated DB (verified) | ✅ |
| Losing concurrent consume rolls back uncommitted revision + snapshot | `consume_promotion_ticket_atomic` catches `IntegrityError` on the flip, ROLLBACKs, returns `concurrent_loss`: `app/research/repository.py:3410-3414`; `_mint_promoted_factor` routes `concurrent_loss` → `conflicted`: `:578-588` | ✅ |
| Same-ticket concurrent consumes serialize to one revision | idempotent reconnect under the lock `:3331-3339` | ✅ |
| Concurrency proof (deterministic + threaded) | `test_consume_two_distinct_tickets_same_candidate_only_one_survives` `test_promotion_consume.py:464`; `test_consume_same_ticket_concurrent_threads_serialize_to_one_revision` `:499` (`ThreadPoolExecutor`); `test_consume_two_distinct_tickets_concurrent_threads_one_wins` `:530` (`ThreadPoolExecutor`) | ✅ |
| Prior runs unchanged (INSERT only) | `test_prior_runs_unchanged_only_new_rows_after_consume`: `test_promotion_consume.py:637` | ✅ |

### AF-REQ-17 — inspect/compare/retain/register only; no broker/order/portfolio/monitor/live/automatic — PASS

| Sub-criterion | Evidence (file:line) | Status |
|---|---|:--:|
| Research-only action surface (issue 201 / inspect 200 / register 200) | `app/api/research_promotion.py:137-225`; router wired into the app: `app/main.py:50` (import), `:898` (`include_router`) | ✅ |
| Server-resolved principal is the only identity source; cross-principal = same 404 boundary | `_principal` `app/api/research_promotion.py:43-52`; run-scoped issue `:151-153`, ticket-scoped inspect `:182`, key-scoped consume `:200-202` | ✅ |
| Bounded status mapping (expired/conflicted → 409, missing → 404, unpromotable → 422) | consume route exception handlers `:207-216`; issue route `:163-167` | ✅ |
| Lexically clear register alias | `register_research_factor = consume_promotion_ticket`: `app/research/promotion_service.py:692`; alias-identity test `test_promotion_consume.py:338` | ✅ |
| No broker/order/position/portfolio/monitor/execution/live_trade/provider/oos/redis/kafka/… import in the Phase 49 module graph | AST boundary guard `_PROHIBITED_IMPORT_TOKENS` (drops only `promotion`, keeps the full execution/second-engine set): `tests/test_phase49_guard.py:52-74`; import + call + attr scans `:140-187` | ✅ |
| Promotion module imports ONLY the re-read collaborators (R2/SC4 allowlist) | `_PROMOTION_IMPORT_ALLOWLIST = {factor_registry, catalog, run_contract, admission, repository}`; `_PROMOTION_FORBIDDEN_IMPORTS = {signal_chain, evaluation, walkforward, alpha_scoring}`: `tests/test_phase49_guard.py:95-100`; allowlist test `:168-187`; confirmed `promotion_service.py` top-level imports only `run_contract` (`:20`) + lazy `admission`/`catalog`/`factor_registry` | ✅ |
| Runtime proof: consume registers a revision invoking zero execution collaborators | `_RaisingFake` broker/order/position/portfolio/monitor/execution injected on every surface; `test_consume_never_invokes_execution_collaborator`: `tests/test_phase49_guard.py:344-390` | ✅ |
| No second database / external queue connection | `TestNoSecondDatabaseOrQueue`: `tests/test_phase49_guard.py:190-200` | ✅ |

## 3. Non-goals — explicit & honored

| Non-goal | Verification |
|---|---|
| No automatic / model-authorized promotion | Consume is principal-triggered: the API requires an explicit researcher `POST :consume` + `idempotency_key`; the reviewer bound at issue is the server-resolved principal only (`research_promotion.py:159`, `:198`). No model output is treated as a promotion authority. |
| No `advanced_*` tables added by Phase 49 | Phase 49 is migration #39 and adds exactly one table, `research_alpha_promotion_tickets` (`migrations.py:2409`). The pre-existing `advanced_promotion_gates` / `advanced_promotions` live in migration #10 (the operational deferred-features schema) — confirmed via `MIGRATIONS` index scan; untouched by Phase 49. |
| No broker/order/portfolio/monitor/live/paper route or collaborator | Mechanically proven by `tests/test_phase49_guard.py` (AST + runtime fake) — see AF-REQ-17 row. |
| No execution permit from admission/OOS | The admission verdict is re-read and re-verified (`_verify_conflicts`), never re-run. Consume calls `set_promotion_ticket_status` + `consume_promotion_ticket_atomic`; no `run_admission`/`evaluate_factor`/scoring path is invoked (R2). |

## 4. Phase 45 + 49 boundary guards

- **Phase 49 guard** (`tests/test_phase49_guard.py`, 10 tests): PHASE49_MODULES = `{research/promotion_service.py, api/research_promotion.py}`; prohibited-import token set drops `promotion` (legit here) and keeps the execution/second-engine set; import allowlist = re-read collaborators only; runtime `_RaisingFake` proves zero execution-collaborator invocation; module-graph completeness + no-second-DB. **10 passed.**
- **Phase 45 guard** (`tests/test_phase45_guard.py`, 52 tests): the shared persistence authority `research/repository.py` is the only module exempt from the `promotion` import token (it materializes ticket value objects); every Phase 45 *logic* module (run_service, run_worker, research_alpha, …) remains promotion-free, and **no execution/second-engine token is exempted**. **52 passed.**

## 5. Watchlist out-of-scope guarantee

`git status --porcelain | grep "Watchlist.tsx"` → **NOT PRESENT**.
`git diff --stat -- frontend/src/pages/Watchlist.tsx` → **0 files, 0 lines changed**.

`frontend/src/pages/Watchlist.tsx` is untouched by Phase 49 (not read, not modified — per the verification constraint).

## 6. Schema / migration facts

- `PRAGMA user_version = 39` on a migrated DB (Phase 49 = migration #39; advances by exactly one from 38).
- New table `research_alpha_promotion_tickets` with `UNIQUE(idempotency_key)` (exactly-once issue), `CHECK (admission_verdict = 'admitted')`, and 64-byte digest CHECKs on all fingerprint columns.
- Indexes present on a migrated DB: `sqlite_autoindex_…_1/2`, `idx_promotion_tickets_run`, `ux_promotion_tickets_consumed_candidate` (the partial unique index — the codebase's first partial `WHERE` index).
- Triggers present: `research_alpha_promotion_tickets_no_delete` (append-only), `research_alpha_promotion_tickets_guard_transition` (identity-column immutability).
- The table is additive (new table + index + trigger; no existing column changed) — `user_version` +1, snapshot/catalog/run contracts unaffected (170-additive regression per 49-01 SUMMARY).

## 7. SUMMARY claim cross-check (3 claims vs code)

| # | SUMMARY claim | Code finding | Match |
|---|---|---|:--:|
| 1 | "49-01 deviation #3 — `policy_version` added to `list_admission_verdicts_for_run` projection" | SELECT now includes `policy_version` (`repository.py:3035`) and the result dict carries it (`:3052`). Additive; no consumer breaks. | ✅ |
| 2 | "49-01 SC1 — the live `ADMISSION_POLICY_FINGERPRINT` is bound at issue so a later policy change is detectable" | `ADMISSION_POLICY_FINGERPRINT` is a module-level constant (`admission.py:107`); bound at issue (`promotion_service.py:251`); refresh re-verifies via `verify_admission_policy_fingerprint` + `admission_policy_fingerprint()` re-read (`:361-375`). | ✅ |
| 3 | "49-02 SC3 — formal factors come exclusively from `kind != alpha_exploratory`, which only promotion mints; unreviewed output is structurally absent from `list_current`" | `list_current` filters `provenance.kind != alpha_exploratory` (`factor_registry.py:264`); consume mints `alpha_promoted` via `consume_promotion_ticket_atomic` (NEW `factor_id`, `revision_number=1`) — never `revise_factor`. Exploratory revisions stay in the raw store, locatable only via `find_exploratory_revision`. | ✅ |

## 8. human_items

None blocking. Two non-blocking observations for record:

- **[INFO] W1 inherited from plan-check (already resolved).** The 49-01 plan cited the operational-migrations test at the non-existent `tests/operational/test_operational_migrations.py`; the executor corrected it to the real `tests/test_operational_migrations.py`. No code/test impact.
- **[INFO] Mint+flip is a single atomic repository transaction.** `consume_promotion_ticket_atomic` (not separate `create_factor` + `record_factor_evidence` calls) is a deliberate deviation from the literal 49-02-02 task prose — required so the formal-revision INSERT, promotion-snapshot INSERT, and ticket consume-flip share one `BEGIN IMMEDIATE` (the partial unique index is the final at-most-one gate). The formal revision still has the exact required shape (NEW `factor_id`, `revision_number=1`, `alpha_promoted` provenance, full lineage). Documented in 49-02-SUMMARY deviation #1; behavior verified by the concurrency tests.

No action required from a human operator; Phase 49 may be marked complete with AF-REQ-15 and AF-REQ-17 satisfied.
