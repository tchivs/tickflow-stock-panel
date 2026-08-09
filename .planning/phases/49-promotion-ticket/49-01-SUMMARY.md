# Phase 49-01 Summary — PromotionTicket create + bind + refresh/expire/conflict (Wave 1)

**Plan:** 49-01 · **Wave:** 1 (depends_on: []) · **Requirements:** AF-REQ-15 (SC1, SC2 expire/conflict half)
**Status:** Complete · **Verified:** 2026-08-09

## What shipped

| Task | Artifact | Commit |
|---|---|---|
| 49-01-01 | `research_alpha_promotion_tickets` migration + guard-transition trigger + partial consumed-candidate unique index (migrations.py) + `test_phase49_promotion_tickets_migrate_with_constraints_and_idempotence` | `465eacb` |
| 49-01-02 | `promotion_service.py` frozen `PromotionTicket` value object + repository `issue_promotion_ticket` / `get_promotion_ticket` / `get_promotion_ticket_by_key` / `set_promotion_ticket_status` under `BEGIN IMMEDIATE` + `get_candidate_attempt` read helper | `799c37f` |
| 49-01-03 | `issue_promotion_ticket` — binds the complete candidate/evidence/policy triple from frozen/append-only facts, exactly-once via idempotency key, fail-closed | `799c37f` |
| 49-01-04 | `refresh_promotion_ticket` — deterministic re-read + re-verify (no re-compute) with the ratified expire (re-issueable) vs conflict (hard reject) taxonomy | `799c37f` |

## Success-criteria evidence

- **SC1 (AF-REQ-15 create + bind):** `issue_promotion_ticket` binds every column of the evidence triple from persisted rows or a live module constant — candidate identity (`run_id, candidate_id, candidate_digest, canonical_expression, ast_signature, shape_signature, dsl_version`), frozen context (`snapshot_sha256, manifest_sha256, vocabulary/grammar/membership/data fingerprints` from the append-only snapshot record), admission/OOS (`admission_verdict_id, verdict='admitted' [DB CHECK], policy_version, gate_trail_digest, selection_oos_status, selection_oos_fold_evidence_id`), the live `ADMISSION_POLICY_FINGERPRINT` (bound at issue so a later policy change is detectable), the issued Stage 1 proposal digest, and `reviewer/issued_at/expires_at/idempotency_key`. The bound `policy_fingerprint` equals `admission.ADMISSION_POLICY_FINGERPRINT`; issuing for a non-admitted candidate / missing verdict / missing selection-OOS / missing snapshot raises `PromotionTicketUnavailable` and writes no row.
- **SC2 expire/conflict half (AF-REQ-15):** `refresh_promotion_ticket` re-reads and re-verifies every bound immutable fact byte-for-byte and routes divergence into the ratified taxonomy (R1). **Conflict** (hard reject, `status='conflicted'`): candidate `canonical_expression`/`ast_signature`/`candidate_digest`, any snapshot/manifest/component digest, live admission policy fingerprint (`verify_admission_policy_fingerprint` mismatch), the admission verdict (`id`/`verdict`/`policy_version`/`gate_trail_digest`), the selection-OOS status/evidence id, or a bound Stage 1 digest no longer present. **Expire** (re-issueable, `status='expired'`): wall-clock past `expires_at` or a superseding Stage 1 proposal. A terminal ticket is returned unchanged; a valid current ticket is returned unchanged (read-only). Each reason is a bounded machine-readable mapping.

## Verification output

| Selection | Result |
|---|---|
| `pytest tests/test_operational_migrations.py tests/research/test_promotion_ticket.py -k 'promotion_ticket or promotion_table or guard_transition or consumed_unique'` (49-01-01) | **28 passed** |
| `pytest tests/research/test_promotion_ticket.py -k 'issue or idempotent or get_ticket or set_status or frozen'` (49-01-02) | **9 passed** |
| `pytest tests/research/test_promotion_ticket.py -k 'issue_triple or fail_closed or no_recompute or idempotent_reissue'` (49-01-03) | **8 passed** |
| `pytest tests/research/test_promotion_ticket.py -k 'refresh or expire or conflict or policy_drift or no_recompute'` (49-01-04) | **10 passed** |
| `pytest tests/test_operational_migrations.py tests/research/test_run_contract.py tests/research/test_experiment_catalog.py` (additive — new table, `user_version` +1, snapshot/catalog contracts unaffected) | **170 passed** |
| `pytest tests/research/test_promotion_ticket.py tests/research/test_agent_stage2.py tests/research/test_admission.py tests/research/test_alpha_scoring.py` (regression on touched modules) | **171 passed** |

`test_promotion_ticket.py` = 28 tests; `test_operational_migrations.py` gains one Phase 49 test. The new table is additive; `PRAGMA user_version` advances by exactly one.

## Deviations & decisions

1. **W1 (verify-command path) — corrected.** Tasks 49-01-01 `<verify>` and the `<verification>` section cite `tests/operational/test_operational_migrations.py`, but no such directory exists. The real file is `backend/tests/test_operational_migrations.py`; used the correct path throughout (49-PLAN-CHECK W1).
2. **Test names aligned to plan verify keywords.** The plan's `-k` expressions use keywords (`issue_triple`, `fail_closed`, `idempotent_reissue`, `no_recompute`, `policy_drift`). Test names were chosen to contain those exact substrings so each plan verify selection exercises real coverage rather than deselecting all tests.
3. **`policy_version` added to `list_admission_verdicts_for_run` projection.** Issue/refresh bind `policy_version` from the verdict row; the existing projection omitted it. The field is additive (the Stage 2 `ServerEvidence` consumer holds the list opaquely), so no consumer breaks.
4. **`selection_oos_status` = `'evaluated'`.** The deterministic value bound when the reserved selection-OOS fold evidence row exists for the candidate; refresh re-asserts both it and the bound `selection_oos_fold_evidence_id` against the append-only fold-evidence ledger.
5. **`gate_trail_digest` = `digest_bytes(verdict["gates"])`.** A canonical SHA-256 over the verdict's gate trail (the persisted `gates_json`), recomputed identically on refresh — a stable, append-only fingerprint that catches a forged/unaligned gate trail.
6. **Circular import broken by lazy admission import.** `repository` imports `PromotionTicket` from `promotion_service` at module load (so the row methods can construct the value object). A top-level `admission` import in `promotion_service` would close the cycle `admission → factor_registry → repository → promotion_service → admission`. `promotion_service` therefore imports `admission` symbols lazily inside `issue_promotion_ticket` / `_verify_conflicts` (R2 re-verify stays a call-time, not load-time, dependency).
7. **Verdict-drift test models a forgeable binding.** The `admission_verdict` column has a DB `CHECK = 'admitted'` constraint, so it cannot be mutated to `'rejected'` even with the guard trigger dropped. The verdict-drift test instead forges the nullable `gate_trail_digest` (no CHECK) and asserts refresh detects the gate-trail divergence → `conflicted`.
8. **Policy-drift test patches `admission_policy_fingerprint`.** `verify_admission_policy_fingerprint` recomputes the live fingerprint via `admission_policy_fingerprint()` (not the cached `ADMISSION_POLICY_FINGERPRINT` constant), so the policy-drift tests patch the recomputing function to model a genuine live-policy change.

## Handoff to 49-02

- `PromotionTicket` (frozen value object) + `issue_promotion_ticket` / `refresh_promotion_ticket` (service) + `issue_promotion_ticket` / `get_promotion_ticket` / `get_promotion_ticket_by_key` / `set_promotion_ticket_status` (repository) — the frozen, evidence-bound, idempotent ticket 49-02 consumes.
- `consume_promotion_ticket` (49-02) re-asserts via `refresh_promotion_ticket`, then atomically flips `status → 'consumed'` (`set_promotion_ticket_status`) while minting the formal `FactorRevision` + catalog entry in one `BEGIN IMMEDIATE` transaction; the partial `ux_promotion_tickets_consumed_candidate` index is the final at-most-one gate.
- `R2` boundary (re-verify, not re-compute) is established here and must be preserved by 49-02's consume — no `run_admission` / panel load / chain compute / scoring in the consume path.
