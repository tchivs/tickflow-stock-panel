# Phase 49-02 Summary — Atomic consume → immutable FactorRevision + catalog + boundary guard (Wave 2, final)

**Plan:** 49-02 · **Wave:** 2 (depends_on: [49-01]) · **Requirements:** AF-REQ-15 (SC2 concurrent half, SC3), AF-REQ-17 (SC4)
**Status:** Complete · **Verified:** 2026-08-09

## What shipped

| Task | Artifact | Commit |
|---|---|---|
| 49-02-01 | `consume_promotion_ticket` / `register_research_factor` — the §3.1 8-step transaction under `BEGIN IMMEDIATE` (load → idempotent reconnect → status gate → re-verify → atomic mint+flip), with the partial `ux_promotion_tickets_consumed_candidate` unique index as the final at-most-one gate; `consume_promotion_ticket_atomic` repository handoff | `e9e81fd` |
| 49-02-02 | `_mint_promoted_factor` — formal `alpha_promoted` `FactorRevision` (NEW uuid4 `factor_id`, `revision_number=1`, full candidate lineage provenance) + promotion `ExperimentSnapshot` (`summary_kind='promoted-factor'`, `originating_run_id='promotion:{ticket_id}'`); prior runs unchanged | `e9e81fd` |
| 49-02-03 | `api/research_promotion.py` — principal-scoped issue (201) / inspect / register (200) routes; server-resolved principal is the only identity source; expired/conflicted → 409, missing → 404, unpromotable → 422; wired into `main.py` | `85d6870` |
| 49-02-04 | `tests/test_phase49_guard.py` — AST/import boundary + research-allowlist + runtime fake-collaborator + module-graph completeness (SC4) | `00783ff` |
| boundary | `tests/test_phase45_guard.py` — scoped exemption: the shared `repository.py` persistence layer may import `promotion_service` (Phase 49's job); Phase 45 logic modules stay promotion-free | `b8b7d8d` |

## Success-criteria evidence

- **AF-REQ-15 SC2 (concurrent half — at-most-one revision):** `consume_promotion_ticket` runs the mint (formal factor + revision + promotion snapshot) and the ticket consume-flip under ONE `BEGIN IMMEDIATE` (`consume_promotion_ticket_atomic`). Same-ticket concurrent consumes serialize: the winner mints + flips; the loser reconnects under the lock and returns the existing revision verbatim. Two distinct tickets for one candidate both mint uncommitted, but only the first `status='consumed'` commit survives the partial `ux_promotion_tickets_consumed_candidate` index; the loser hits `IntegrityError`, rolls back its uncommitted revision + snapshot, and goes to `conflicted`. Net: exactly one revision survives. Proven by deterministic + threaded tests (`test_consume_two_distinct_tickets_same_candidate_only_one_survives`, `test_consume_same_ticket_concurrent_threads_serialize_to_one_revision`, `test_consume_two_distinct_tickets_concurrent_threads_one_wins`).
- **AF-REQ-15 SC3 (reviewed+exact-bound ⇒ revision+catalog; unreviewed absent):** consume mints a NEW formal `FactorRevision` (`revision_number=1`, `provenance.kind='alpha_promoted'`, never `revise_factor` on the exploratory `factor_id`) with preserved lineage (`source_run_id, candidate_id, candidate_digest, source_exploratory_revision_id, admission_verdict_id, selection_oos_fold_evidence_id, promotion_ticket_id, reviewer`). The formal revision appears in `registry.list_current()`; the exploratory revision remains excluded (`test_formal_revision_in_list_current_exploratory_excluded`) — formal factors come exclusively from `kind != alpha_exploratory`, which only promotion mints. The promotion snapshot cites `admission_verdict_id` + `selection_oos_fold_evidence_id` by id (R5 — it does not re-bind the verdict to the formal revision). Prior runs are byte-identical before/after (`test_prior_runs_unchanged_only_new_rows_after_consume`).
- **AF-REQ-17 SC4 (research-only surface):** the action surface is inspect / register only. `test_phase49_guard.py` mechanically proves the Phase 49 module graph imports no broker/order/position/portfolio/monitor/execution/provider/evaluator/redis/kafka/... collaborator, the promotion module imports ONLY `{factor_registry, catalog, run_contract, admission, repository}` (re-read-not-recompute, R2 — `signal_chain`/`evaluation`/`walkforward`/`alpha_scoring` are provably absent), and a runtime `_RaisingFake` test proves consume registers a revision without ever invoking an execution collaborator.

## Verification output

| Selection | Result |
|---|---|
| `pytest tests/research/test_promotion_consume.py -k 'consume or idempotent_reconnect or at_most_one or concurrent or expired_or_conflicted'` (49-02-01) | **15 passed** |
| `pytest tests/research/test_promotion_consume.py -k 'formal_revision or lineage or catalog or prior_runs_unchanged or list_current'` (49-02-02) | **4 passed** |
| `pytest tests/research/test_research_promotion_api.py -k 'issue or consume or inspect or cross_principal or idempotent'` (49-02-03) | **11 passed** |
| `pytest tests/test_phase49_guard.py` (49-02-04) | **10 passed** |
| `pytest tests/research/test_experiment_catalog.py tests/research/test_factor_registry.py tests/research/test_promotion_ticket.py tests/test_phase49_guard.py` (plan `<verification>`) | **51 passed** |
| `pytest tests/test_phase45_guard.py` (boundary-evolution fix) | **52 passed** |
| `pytest tests/research/` (full research regression) | **726 passed** |

`test_promotion_consume.py` = 15 tests; `test_research_promotion_api.py` = 11 tests; `test_phase49_guard.py` = 10 tests.

## Deviations & decisions

1. **Mint+flip is ONE atomic repository transaction (`consume_promotion_ticket_atomic`), not separate `registry.create_factor` + `catalog.record_factor_evidence` calls.** The at-most-one-revision guarantee (T-49-02a) requires the formal-revision INSERT, the promotion-snapshot INSERT, and the ticket consume-flip to share ONE `BEGIN IMMEDIATE`. Separate transactions (the literal prose of task 49-02-02) would let a losing concurrent consume persist a duplicate revision before the partial-unique-index gate on the ticket flip. The single atomic handoff mirrors the established `append_stage_boundary` / `create_experiment` multi-write pattern. The formal revision still has the exact required shape (NEW `factor_id`, `revision_number=1`, `alpha_promoted` provenance, parsed features sourced from the exploratory revision so no DSL parse/re-score occurs) and the snapshot is structured via `FactorEvidencePackage` before the atomic INSERT.
2. **`consume_promotion_ticket` returns `PromotionTicketConsumed` (revision + ticket_id + experiment_id), not a bare `FactorRevision`.** The artifact export list requires `PromotionTicketConsumed`; the `.revision` field provides the verbatim `FactorRevision` for idempotent reconnect. This is the one deviation from the literal `-> FactorRevision` task signature.
3. **Consume re-surfaces a terminal expired/conflicted ticket as `PromotionTicketExpired`/`PromotionTicketConflict`** (not `PromotionTicketUnavailable`), so the API maps an already-terminal ticket to 409 (bounded reason) per the SC4 acceptance; `PromotionTicketUnavailable` is reserved for the genuinely-missing ticket (→ 404).
4. **Re-verify is inlined in `consume_promotion_ticket`** (expiry + stage-1 supersession + `_verify_conflicts`) rather than delegating to `refresh_promotion_ticket`, giving the 8-step transaction a single self-contained narrative; the predicate itself is the unchanged 49-01 logic (R2: re-read, never re-compute).
5. **`_mint` is injectable** (`_mint=_mint_promoted_factor` default) for the idempotent-reconnect call-count test; the real default provides true atomicity for the concurrency tests.
6. **Phase 45 guard boundary evolution.** `repository.py` materializes Phase 49 `PromotionTicket` value objects (`from_record`), so it imports `promotion_service` at module load — which tripped Phase 45's `promotion` import token. The fix scopes the exemption to `repository.py` (the shared append-only persistence authority) only; every Phase 45 logic module (run_service, run_worker, research_alpha, …) remains promotion-free, and no execution/second-engine token is exempted (RESEARCH §6.2 — promotion is Phase 49's job).
7. **API DTOs are defined inline in `research_promotion.py`** (not in `run_schemas.py`, which is outside `files_modified`); the router imports only the promotion service + FastAPI/Pydantic, resolving `repo`/`registry`/`catalog` from `app.state` via `getattr` (no execution/scoring/provider imports).

## Handoff to Phase 50

- The formal `alpha_promoted` `FactorRevision` + promotion `ExperimentSnapshot` (`summary_kind='promoted-factor'`, lineage provenance, verdict/OOS evidence refs by id) are the catalog assets Phase 50 (Replay Workbench & Release Hardening) consumes for lineage/comparison views.
- The promotion snapshot's `originating_run_id='promotion:{ticket_id}'` namespace + `factor_lineage` metrics are the join keys for cross-run factor lineage and the release execution-boundary scan.
- The research-only action surface (inspect/compare/retain/register) is provably bounded by `test_phase49_guard.py`; Phase 50 must preserve it (no execution/second-engine import in the promotion path).
