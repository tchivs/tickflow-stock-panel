# Phase 49 Plan Check — Promotion Ticket (49-01 / 49-02)

**Status:** PASS · **Verdict:** Goal-achieving, no blockers · **Checked against:** AF-REQ-15, AF-REQ-17 (REQUIREMENTS.md:48-50), RESEARCH.md, 49-01-PLAN.md, 49-02-PLAN.md, live source.

---

## Verdict

| Item | Result |
|---|---|
| Blockers | **0** |
| Warnings | 1 (verify-command path typo in 49-01) |
| Notes | 3 |
| Goal coverage | AF-REQ-15 (SC1, SC2, SC3) + AF-REQ-17 (SC4) — COMPLETE |

The two-plan split is goal-backward sound: 49-01 establishes the frozen evidence-bound ticket + re-verify predicate + expire/conflict taxonomy (SC1, SC2 expire/conflict half); 49-02 atomically consumes it to one immutable formal `FactorRevision` + catalog entry with preserved lineage and a mechanically-proven research-only boundary (SC2 concurrent half, SC3, SC4). Every locked boundary (frozen snapshot authority, append-only, no second evaluator, no execution authority, no AGPL source) is honored.

## Verification detail (7 checks)

**1. Test files — NEW, no collision.** `backend/tests/research/test_promotion_ticket.py`, `backend/tests/research/test_promotion_consume.py`, `backend/tests/research/test_research_promotion_api.py`, and `backend/tests/test_phase49_guard.py` are all absent from the tree → greenfield, no collision with existing suites. `tests/research/` exists (peers: `test_factor_registry.py`, `test_experiment_catalog.py`); `test_phase49_guard.py` sits at `tests/` root beside `test_phase45_guard.py` (the mirrored precedent).

**2. Ticket binding (49-01) — full evidence triple.** `PromotionTicket` + the migration bind the complete triple verified against RESEARCH §2.2: candidate identity (`run_id, candidate_id, candidate_digest, canonical_expression, ast_signature, shape_signature, dsl_version`), issued draft (`stage1/stage2 digests`), frozen context (`snapshot/manifest/vocabulary/grammar/membership/data` fingerprints), admission/OOS (`admission_verdict_id, verdict='admitted' [DB CHECK], policy_version, gate_trail_digest, selection_oos_status, selection_oos_fold_evidence_id`), live `policy_fingerprint` (= `ADMISSION_POLICY_FINGERPRINT`, admission.py:107 ✓), and `reviewer/issued_at/expires_at/idempotency_key`. Refresh = deterministic re-read + re-verify (R2 ✓): the ONLY live check is `verify_admission_policy_fingerprint` (admission.py:110-120 ✓); no `run_admission`/panel-load/chain-compute/scoring. Expire-vs-conflict taxonomy ratified (R1 ✓): conflict = expression/AST/snapshot/manifest/policy/vocab/grammar/membership/verdict/OOS drift (hard reject); expire = `now > expires_at` or superseding proposal (re-issueable). Both terminalize with no revision.

**3. Partial unique index + guard trigger (49-01) — correct.** `CREATE UNIQUE INDEX ux_promotion_tickets_consumed_candidate ON research_alpha_promotion_tickets(run_id, candidate_digest) WHERE status='consumed'` is valid SQLite partial-index syntax (≥3.8.0). The `guard_transition` `BEFORE UPDATE` trigger mirrors `research_alpha_runs_guard_cursor` (migrations.py:1930-1941 ✓), permitting only `{status, conflict_reason_json, consumed_at, produced_factor_revision_id}` to mutate; every identity/binding column is immutable post-issue. `UNIQUE(idempotency_key)` gives exactly-once issue (append_run_event precedent).

**4. Atomic consume (49-02-01) — 8-step under `BEGIN IMMEDIATE`.** Matches RESEARCH §3.1: (1) BEGIN IMMEDIATE; (2) load by idempotency_key; (3) idempotent reconnect — `status='consumed'` returns existing `produced_factor_revision_id` verbatim (mirrors `evaluate_selection_oos`, alpha_scoring.py:654-662 ✓); (4) non-`issued` → raise; (5) inline refresh/re-verify (49-01 predicate); (6) mint formal revision + snapshot; (7) flip to `consumed` (partial index = final gate); (8) COMMIT. Uses `create_factor` (factor_registry.py:133-149 ✓), NOT `revise_factor`. Snapshot uses `originating_run_id='promotion:{ticket_id}'` (R6 ✓, catalog.py:392 `admitted-factor-summary:{revision_id}` precedent ✓), satisfying `originating_run_id UNIQUE` (migrations.py:178 ✓). Prior runs unchanged — INSERTs only across append-only `no_update`/`no_delete` tables.

**5. Boundary guard (49-02-04).** `PHASE49_MODULES = {research/promotion_service.py, api/research_promotion.py}` ✓. Prohibited import tokens DROP `promotion` (legit here; Phase 45 listed it to keep *itself* promotion-free) and KEEP the execution/second-engine set (broker/order/position/portfolio/monitor/execution/live_trade/evaluator/oos/redis/kafka/…). Prohibited call tokens DROP `promote_factor`/`admit_factor`. Import allowlist = `{factor_registry, catalog, run_contract, admission, repository}` ONLY — `signal_chain`/`evaluation`/`walkforward`/`alpha_scoring` provably absent (the re-read-not-recompute invariant). Runtime `_RaisingFake` doubles for broker/order/portfolio/monitor/execution; consume must succeed invoking zero fakes.

**6. Wave deps + file overlap.** 49-01 wave 1 (depends_on []); 49-02 wave 2 (depends_on [49-01]) — correct sequencing. `promotion_service.py` is shared but across waves (49-01 creates, 49-02 extends) → sequential, not a concurrent collision; 49-02 reads 49-01's symbols as `read_first`. `repository.py`/`migrations.py` are 49-01-only; `research_promotion.py`/new tests are 49-02-only. No same-wave file overlap. Within 49-02, task ordering 01→02→03→04 is an internal dependency, not a parallel hazard.

**7. Non-goals — explicit & honored.** No automatic/model-authorized promotion (consume is principal-triggered, deterministic; model output is untrusted review only). No `advanced_*` tables (only `research_alpha_promotion_tickets` added). No broker/order/portfolio/monitor/live/paper route or collaborator (SC4). No execution permit from admission/OOS — the verdict is re-read and re-verified, never re-run for authority.

## Warnings

- **W1 (49-01 verify-command path).** Tasks 49-01-01 `<verify>` and the 49-01 `<verification>` section cite `tests/operational/test_operational_migrations.py`, but **no `tests/operational/` directory exists** — the real file is `backend/tests/test_operational_migrations.py`. The 49-02 plan uses correct paths. Mechanical typo; does not affect implementation correctness (the `read_first` correctly targets `migrations.py` source). Executor should run the operational-migrations test at `tests/test_operational_migrations.py`.

## Notes

- **N1.** `ux_promotion_tickets_consumed_candidate` is the **first partial index** (`WHERE status='consumed'`) in the codebase — syntax is valid SQLite, but there is no in-repo precedent; the executor's temp-DB test (49-01-01 acceptance) directly validates it.
- **N2.** The `guard_transition` trigger is described as "mirroring" `research_alpha_runs_guard_cursor`, which uses a `WHEN OLD.x IS NOT NEW.x` mutable-column allowlist. The plan leaves the exact trigger-body form to the executor; either the allowlist-allow form or an explicit `IF NEW.<col> IS NOT OLD.<col> THEN RAISE` form satisfies the acceptance criteria (only the 4 consume columns may change).
- **N3.** 49-02's verify selections reference `test_promotion_consume.py` and `test_research_promotion_api.py`, which that plan creates — consistent with the 49-01 pattern of verifying the test file the plan itself produces.

## AF-REQ coverage matrix

| Requirement / sub-criterion | 49-01 | 49-02 | Evidence |
|---|:--:|:--:|---|
| **AF-REQ-15** save immutable `FactorRevision` | — | ✅ | consume → `create_factor` (49-02-02) |
| AF-REQ-15 compare expression/assumptions/evidence/gate trail/provenance | ✅ | ✅ | full triple bound (49-01); inspect/compare API (49-02-03) |
| AF-REQ-15 changed draft rejected | ✅ | ✅ | refresh re-verifies issued-draft digests → conflict (49-01-04) |
| AF-REQ-15 unreviewed absent from catalog | — | ✅ | `list_current` excludes `alpha_exploratory`; only promotion mints formal (49-02-02) |
| AF-REQ-15 SC1 bind / SC2 expire-conflict | ✅ | — | 49-01 SC1 + SC2 expire/conflict half |
| AF-REQ-15 SC2 concurrent + SC3 | — | ✅ | 49-02-01 partial-unique at-most-one + 49-02-02 formal catalog |
| **AF-REQ-17** inspect/compare/retain/register only | — | ✅ | action surface (49-02-03) + existing catalog methods |
| AF-REQ-17 no broker/order/portfolio/monitor/live/automatic | — | ✅ | SC4 boundary guard (49-02-04) |

**Recommendation:** Proceed to execution. Fix W1 (verify path) at execution time — `tests/operational/...` → `tests/test_operational_migrations.py`.
