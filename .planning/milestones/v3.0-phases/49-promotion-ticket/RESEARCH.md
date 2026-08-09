# Phase 49 Research — Research-Only Promotion Ticket

**Status:** Draft · **Phase goal:** A researcher can explicitly approve a complete, current, evidence-bound candidate and register *only* a new immutable research `FactorRevision`/catalog handoff; stale or modified approvals fail closed.
**Requirements:** AF-REQ-15 (explicit review → immutable `FactorRevision`; changed draft rejected; unreviewed absent from catalog), AF-REQ-17 (research-only action surface; no broker/order/portfolio/monitor/live/automatic promotion).
**Pattern source:** PA_Agent `ApprovalService.consume_ticket()` (docs/v3-roadmap.md:74-78, 84, 259 — APT-02: check status+timeliness → re-collect evidence → verify candidate digest → re-run risk → atomic permit). Phase 49 keeps the *ticket shape* and *atomic consume* and **replaces the execution permit with an immutable research `FactorRevision`/catalog entry** — patterns only, no AGPL source (REQUIREMENTS.md:19, 76).

---

## 0. Findings at a glance

| # | Question | Verdict | Strongest evidence |
|---|---|---|---|
| 1 | FactorRevision + catalog mapping | **Promotion = new formal `FactorRevision` via `create_factor` (new factor_id, non-exploratory provenance) + a promotion `ExperimentSnapshot`**; exploratory revision stays excluded from the formal catalog | `factor_registry.py:17,250-337`; `catalog.py:356-413,557-601` |
| 2 | Promotion Ticket design | **Ticket binds the full identity/evidence triple; consume re-reads + re-verifies every bound digest/fingerprint/verdict (fail-closed), NOT re-computes** | `hypotheses.py:227-246`; `admission.py:78-120`; `run_contract.py:252-292` |
| 3 | Atomic handoff | **`BEGIN IMMEDIATE` + partial `UNIQUE(run_id,candidate_digest) WHERE status='consumed'`** → at most one revision per candidate; idempotent reconnect returns the existing revision | `repository.py:2405-2444,519-538`; `alpha_scoring.py:654-662` |
| 4 | Catalog snapshot identity | **Formal revision + promotion summary snapshot (admission verdict ref + selection/OOS evidence ref + frozen manifest)**; prior runs untouched (new rows only) | `catalog.py:134-169,295-354`; `migrations.py:173-190` |
| 5 | Signal/backtest binding | **Identical** — `FactorSignalChain.compute(revision_id=…)` binds via `registry.get_revision` + `parse_factor`; a formal revision has the same shape as exploratory, no special wiring | `signal_chain.py:108-111,262-271` |
| 6 | Research-only boundary | **New `test_phase49_guard.py`** modeled on `test_phase45_guard.py`; promotion module imports ONLY factor_registry/catalog/run_contract/admission/repository — drops `promotion`/`admit_factor` from the prohibited set (legit here), KEEPS broker/order/portfolio/monitor/execution/oos/evaluator | `test_phase45_guard.py:34-89`; `run_service.py:10-11` |
| 7 | Plan split | **2 plans**: 49-01 ticket create+bind+refresh/expire/conflict · 49-02 atomic consume → FactorRevision+catalog+lineage+boundary guard | — |

---

## 1. FactorRevision + catalog mapping (Q1)

### 1.1 Exploratory vs formal revision

Phase 47-01 already mints a transient, research-only `FactorRevision` per candidate via `FactorRegistry.create_exploratory_revision` (`factor_registry.py:287-337`): it carries `provenance.kind="alpha_exploratory"` plus `(run_id, candidate_id, candidate_digest, step)`, is **idempotent** on `(run_id, candidate_digest)` (`find_exploratory_revision`, `factor_registry.py:267-285,311-313`), and is deliberately **excluded** from the formal catalog:

- `list_current()` (`factor_registry.py:250-265`) filters out `kind == ALPHA_EXPLORATORY_KIND` → exploratory revisions never appear in the formal factor catalog.
- `discover_similar()` (`factor_registry.py:339-362`) iterates `list_current()` → exploratory revisions are also excluded from the admission similarity pool.

A *formal* `FactorRevision` is the **same frozen dataclass** (`factor_registry.py:20-36`: `factor_id`, `revision_number`, `canonical_expression`, `dsl_version`, `ast_signature`, `shape_signature`, `fields`, `operators`, `functions`, `provenance`) — the ONLY difference is `provenance.kind != "alpha_exploratory"`, which makes `list_current()` include it.

### 1.2 The promotion mapping (candidate → formal revision)

`AlphaCandidateAttempt` (`run_contract.py:450-468`) identity is `(run_id, candidate_digest)`; a formal `FactorRevision` identity is `(factor_id, revision_number)`. Phase 49 bridges them by **minting a new formal factor** (not appending to the exploratory factor_id):

- **Use `FactorRegistry.create_factor`** (`factor_registry.py:133-149` → `repository.create_factor_with_revision` with a fresh `uuid4` factor_id, `revision_number=1`, `repository.py:122-165`). Provenance is `{kind: "alpha_promoted", source_run_id, candidate_id, candidate_digest, source_exploratory_revision_id, admission_verdict_id, selection_oos_fold_evidence_id, promotion_ticket_id, reviewer}`.
- **Rejected alternative — `revise_factor` on the exploratory factor_id** (`factor_registry.py:177-209`): would make the formal revision `revision_number=2` under the exploratory factor_id, misrepresenting a transient research binding as the *ancestor* of a first-class catalog factor. A clean new factor_id keeps "exploratory identity" and "formal catalog asset" as distinct immutable records linked only by provenance.
- **New `FactorRevision` ⇒ prior runs unchanged**: every table is append-only with `no_update`/`no_delete` triggers (`migrations.py:1531-1548,1945-1970,2197-2222`); the exploratory revision, the candidate ledger, and the fold evidence are never mutated. Promotion only INSERTs.

### 1.3 Formal catalog entry

`ExperimentCatalog` already has the two surfaces Phase 49 needs:

- `record_factor_evidence(FactorEvidencePackage)` (`catalog.py:120-131,338-354`) persists a completed, validated `ExperimentSnapshot` bound to `factor_revision_id`. The promotion snapshot reuses this with `factor_revision_id = <new formal revision>` and a `metrics.summary_kind="promoted-factor"` discriminator (mirroring `summary_kind="admitted-factor"` at `catalog.py:378,412`).
- `record_admitted_factor_summary` (`catalog.py:356-413`) is the **precedent for a summary-only catalog entry** carrying `factor_lineage` + `factor_signature` + `input_snapshot_sha256` (`catalog.py:144-169`).

**Important nuance (FACT-05 boundary):** admission already records an *admitted-factor summary* during the run (`admission._record_admitted_summary`, `admission.py:419-458`) bound to the **exploratory** revision. That summary is *run evidence*, not a formal factor — its revision is excluded from `list_current`. Phase 49's promotion summary is bound to the **formal** revision and is the ONLY path that produces a formal catalog factor. SC3 ("unreviewed output absent from the formal catalog") is therefore satisfied structurally: formal factors come exclusively from `kind != alpha_exploratory` revisions, which only promotion creates.

---

## 2. Promotion Ticket design — SC1, SC2 (Q2)

### 2.1 PA_Agent pattern, adapted

PA_Agent `consume_ticket()` (v3-roadmap.md:259): *check status+timeliness → re-collect evidence → verify candidate digest → re-run RiskEngine → atomic permit*. Phase 49 keeps the **ticket lifecycle + atomic consume** and substitutes:

| PA_Agent (trading) | Phase 49 (research) |
|---|---|
| re-collect *fresh prices* | re-read the **frozen immutable snapshot** + re-assert its digest (data is frozen, not live) |
| verify candidate digest | re-verify `(candidate_digest, canonical_expression, ast_signature)` vs the append-only candidate ledger |
| re-run RiskEngine | **re-verify** the persisted admission verdict + live policy fingerprint (see §2.3) |
| atomic dispatch permit | atomic **new `FactorRevision` + catalog entry** (no execution) |

### 2.2 Ticket bindings (SC1)

A `PromotionTicket` is a frozen value object bound, at issue time, to the complete evidence triple:

```
candidate identity : run_id, candidate_id, candidate_digest,
                     canonical_expression, ast_signature, shape_signature, dsl_version
issued draft       : stage1 proposal (explanation/assumptions/scope/uncertainty) digest,
                     stage2 review (caveats/recommendation) digest   ← AF-REQ-15 "issued draft"
frozen context     : snapshot_sha256, manifest_sha256,
                     vocabulary_fingerprint, grammar_fingerprint, membership_fingerprint,
                     data_fingerprint
admission/OOS      : admission_verdict_id, verdict(="admitted"), policy_version, gate_trail digest,
                     selection_oos status, selection_oos_fold_evidence_id
policy/vocab ver   : admission policy_fingerprint (live, ADMISSION_POLICY_FINGERPRINT)
reviewer + expiry  : reviewer principal, issued_at, expires_at, idempotency_key
```

Sources: candidate identity from `AlphaCandidateAttempt` (`run_contract.py:450-468`); frozen context from `ResearchInputSnapshot.as_storage_record` component digests (`run_contract.py:264-285`); admission from `factor_admission_verdicts` (`migrations.py:1531-1543`); vocabulary/grammar/policy from the frozen manifest groups (`run_contract.py:53-65`).

### 2.3 "Refresh" = deterministic re-read + re-verify (NOT re-compute)

**Decision: consume re-reads persisted immutable facts and re-verifies them byte-for-byte; it does NOT re-run admission or re-load panels.** Rationale:

1. The verdict row is append-only (`migrations.py:1545-1548`) and bound by `UNIQUE(revision_id, policy_version)` (`migrations.py:1542`). Re-running admission (`admission.run_admission`, `admission.py:182-403`) would require a `FactorSignalChain` + governed panel load to reproduce an identical verdict over the **same frozen** snapshot — wasteful, and it would grant the promotion path *computation authority over a completed run's evidence*, blurring the "no automatic re-scoring" boundary (ROADMAP non-goal, ROADMAP.md:149).
2. PA_Agent re-runs RiskEngine because **trading prices go stale in real time**. Research promotion is bound to a **frozen historical snapshot** (`research_alpha_input_snapshots` is append-only, `migrations.py:1893-1896`) — there are no stale prices; the frozen evidence *is* the authoritative evidence.
3. The one thing that CAN drift between issue and consume is the **live admission policy code**: `ADMISSION_POLICY_FINGERPRINT` is computed at module load (`admission.py:107`), and `verify_admission_policy_fingerprint(frozen)` (`admission.py:110-120`) raises `AdmissionPolicyMismatchError` on divergence. The promotion consume re-runs exactly this check against the ticket's bound `policy_fingerprint` (`alpha_scoring._frozen_policy_fingerprint`, `alpha_scoring.py:270-284`, is the precedent).

**Issued-draft re-validation** mirrors `FactorHypothesisService.reviewed_draft` (`hypotheses.py:227-246`): expression/explanation/provenance must byte-match the issued draft. Phase 49 binds a digest of the Stage 1 proposal (`agent_stage1.record_stage1_proposal` fields: `canonical_expression`, `explanation`, `assumptions`, `scope`, `uncertainty`, `agent_stage1.py:52-55,312-330`) + Stage 2 review, and re-compares at consume.

> **Open decision (R1, plan-time):** "changed draft → expire (re-issue) vs conflict (reject)." Recommendation: candidate-expression / snapshot / policy divergence = **conflict** (hard reject, SC2 "conflicts"); wall-clock past `expires_at` or a superseding proposal = **expire** (re-issueable). Both terminalize the ticket without producing a revision.

---

## 3. Atomic handoff — SC2 "at most one revision" (Q3)

### 3.1 Consume transaction

`consume_promotion_ticket(idempotency_key)` runs under `BEGIN IMMEDIATE` (the established write-fence, `repository.py:2405-2444,2474-2513`):

1. `BEGIN IMMEDIATE` (serializes writers).
2. Load ticket by `idempotency_key`.
3. **Idempotent reconnect**: if `status='consumed'`, return the existing `produced_factor_revision_id` verbatim (mirrors `evaluate_selection_oos`'s existing-fold cache, `alpha_scoring.py:654-662`). Reconnect/retry never repeats the side effect (AF-REQ-16 precedent).
4. **Expiry**: if `now > expires_at` → `status='expired'`, raise.
5. **Refresh/re-verify** (§2.3): snapshot digest, candidate `(digest, expression, ast)`, `verify_admission_policy_fingerprint`, verdict still `admitted` w/ matching `policy_version`, vocabulary/grammar/membership re-derived from the frozen manifest, selection-OOS status, issued-draft digest. Any divergence → `status='conflicted'`, raise.
6. Create formal `FactorRevision` (§1.2) + promotion `ExperimentSnapshot` (§1.3) — INSERTs only.
7. `UPDATE ticket SET status='consumed', consumed_at=now, produced_factor_revision_id=…` — the partial unique index (§3.2) is the final gate.
8. `COMMIT`.

### 3.2 At-most-one-revision guarantee

A **partial unique index** on the ticket table enforces "one consumed revision per candidate" even across *different* tickets (reviewer double-submits):

```sql
CREATE UNIQUE INDEX ux_promotion_tickets_consumed_candidate
  ON research_alpha_promotion_tickets (run_id, candidate_digest)
  WHERE status = 'consumed';
```

- **Same ticket, two concurrent consumes**: `BEGIN IMMEDIATE` serializes; first commits (`consumed`), second sees `consumed` → idempotent return (step 3).
- **Two tickets, same candidate**: both pass re-verify and create their revision (step 6, uncommitted); the second to set `status='consumed'` (step 7) hits the partial unique → `IntegrityError` → rollback → that ticket goes to `conflicted`. The created-but-uncommitted revision is discarded by the rollback. Net: exactly one revision survives.

The partial index is preferred over a `UNIQUE` on `research_factor_revisions.provenance` (provenance is freeform JSON, `migrations.py:167`) — it keeps the constraint local to the promotion table and untouched by unrelated factors.

### 3.3 Idempotency key + append-only shape

`UNIQUE(idempotency_key)` on issue (the ticket INSERT) gives exactly-once issue; `no_update`/`no_delete` triggers everywhere *except* the narrow `status`/`consumed_at`/`produced_factor_revision_id` consume transition (mirrors `research_alpha_runs_guard_cursor` which allows only declared mutable columns, `migrations.py:1930-1941`). A dedicated `research_alpha_promotion_tickets_guard_transition` trigger permits only the consume columns to change; every identity/binding column is immutable post-issue.

---

## 4. Catalog snapshot identity — SC3 (Q4)

The catalog state captured on consume (all sourced from frozen/append-only facts, never recomputed):

| Captured field | Source (file:line) |
|---|---|
| canonical_expression, dsl_version, ast_signature, shape_signature, fields, operators, functions | new formal `FactorRevision` (`factor_registry.py:20-36`) |
| admission verdict summary (verdict, policy_version, gate_trail digest, input_snapshot_sha256) | `factor_admission_verdicts` (`migrations.py:1531-1543`); `AdmittedFactorSummary` shape `catalog.py:144-169` |
| selection-fold + selection-OOS evidence refs | `research_alpha_fold_evidence` (`migrations.py:2197-2213`); `evaluate_selection_oos` label `alpha_scoring.py:708-733` |
| resolved config + input manifest | frozen `ResearchInputSnapshot` (`run_contract.py:252-285`) |
| promotion lineage | provenance `{source_run_id, candidate_id, candidate_digest, source_exploratory_revision_id, admission_verdict_id, selection_oos_fold_evidence_id, promotion_ticket_id, reviewer}` |

**Prior runs unchanged:** every produced row is a fresh INSERT (new `factor_id`, new `experiment_id`); the `originating_run_id UNIQUE` constraint (`migrations.py:178`) is satisfied by using a promotion-scoped run-id namespace (e.g. `promotion:{ticket_id}`), the same pattern `record_admitted_factor_summary` uses (`admitted-factor-summary:{revision_id}`, `catalog.py:392`).

---

## 5. Signal/backtest binding compatibility — research flag (Q5)

`FactorSignalChain.compute(*, revision_id, config)` (`signal_chain.py:108-111`) → `_binding(revision_id)` (`signal_chain.py:262-271`): `registry.get_revision(revision_id)` → `parse_factor(revision.canonical_expression)` → assert `parsed.dsl_version == revision.dsl_version` and `parsed.referenced_fields == revision.fields`.

A formal `FactorRevision` has the **identical** fields an exploratory one does (`factor_registry.py:20-36`). Therefore the formal revision binds through the chain **with no special wiring** — the same path factory scoring, admission, walk-forward folds, and as-of serving already use (`run_admission` calls `chain.compute(revision_id=revision.id, …)`, `admission.py:210-229`; `evaluate_selection_oos` likewise, `alpha_scoring.py:667`). The promotion catalog entry is consumable by every existing signal/backtest path because they resolve by `revision_id` through the registry, which returns the formal revision.

**Verdict:** no new signal path, no second evaluator, no binding fork. AF-REQ-05 ("single shared `FactorSignalChain`") is preserved.

---

## 6. Research-only boundary — SC4 (Q6)

### 6.1 Action surface (SC4 left half)

SC4 names exactly four actions — inspect, compare, retain, register — all already present or cleanly additive:

- **inspect** → `catalog.get` / `list_history` (`catalog.py:603-608`), run/candidate reads (`api/research_alpha.py:88-260`).
- **compare** → `catalog.compare` (`catalog.py:617-634`).
- **retain** → `catalog.retain` (`catalog.py:610-612`; `retain_experiment`, `repository.py:519-538`).
- **register a research asset** → the new `consume_promotion_ticket` (the ONLY new action).

No broker/order/position/portfolio/monitor/live/automatic-promotion route is added (explicit non-goal, ROADMAP.md:149).

### 6.2 Boundary guard test — `test_phase49_guard.py`

Modeled on `test_phase45_guard.py` (`test_phase45_guard.py:34-89`):

- **`PHASE49_MODULES`** = `{research/promotion_service.py, api/research_promotion.py}` (+ ticket module).
- **Prohibited import tokens** — KEEP the execution/second-engine set: `broker, order, position, portfolio, monitor, execution, live_trade, provider, openai, anthropic, llm, evaluator, factor_evaluation, oos, out_of_sample, catalog_mut, redis, kafka, nats, celery, rq.`. **DROP** `promotion` (promotion is this phase's job) — note Phase 45 lists `promotion` precisely to keep *itself* promotion-free (`test_phase45_guard.py:64`).
- **Prohibited call tokens** — keep `execute_order/place_order/submit_order/cancel_order`, `eval(/exec(/compile(/__import__`, `redis/kafka`. **DROP** `promote_factor`/`admit_factor` from the prohibited-call regex (admission + promotion are legit here); name the service method `consume_promotion_ticket`/`register_research_factor` regardless, to stay lexically clear.
- **Allowed imports for the promotion module** (the allowlist the test asserts): `factor_registry`, `catalog`, `run_contract`, `admission`, `repository` ONLY. Conspicuously **not** `signal_chain`, `evaluation`, `walkforward`, `alpha_scoring` — the promotion path re-reads verdicts, it does not re-compute (§2.3), which also keeps `evaluator`/`oos` import tokens satisfactorily absent.
- **Runtime fake-collaborator test** (mirrors `TestRuntimeNoExecutionCollaborator`, `test_phase45_guard.py:231-367`): pass `_RaisingFake` broker/order/portfolio/monitor/execution doubles into the promotion service; assert consume completes (creating a revision) and **never invokes any fake**.

The result visibly proves SC4: the promotion service has no execution collaborator or route.

---

## 7. Recommended plan split (Q7)

**2 plans** (Phase 49 is 2 requirements, smaller than the 4-plan 45/47/48 phases):

### 49-01 — PromotionTicket: create, bind, refresh/expire/conflict
- New append-only `research_alpha_promotion_tickets` table + guard-transition trigger (migration following the Phase 45/46/47 rebuild pattern, `migrations.py:2129-2166,2224-2256`).
- `PromotionTicket` frozen dataclass + `issue_promotion_ticket(...)` binding the full §2.2 triple; `UNIQUE(idempotency_key)`.
- Repository `issue_ticket` / `get_ticket` / `consume_ticket` row methods under `BEGIN IMMEDIATE`.
- Refresh/re-verify predicate (§2.3): snapshot digest, candidate triple, `verify_admission_policy_fingerprint`, verdict, vocab/grammar/membership, OOS, issued-draft digest; expiry + conflict transitions.
- Covers **SC1** (create+bind) and the **expire/conflict half of SC2**.

### 49-02 — Atomic consume → immutable FactorRevision + catalog + boundary guard
- `consume_promotion_ticket`: the §3.1 transaction; partial `UNIQUE(run_id,candidate_digest) WHERE status='consumed'` for at-most-one-revision (§3.2); idempotent reconnect.
- Formal `FactorRevision` via `registry.create_factor` with `kind="alpha_promoted"` provenance (§1.2) + promotion `ExperimentSnapshot` (`summary_kind="promoted-factor"`, §1.3/§4).
- `test_phase49_guard.py` (§6.2): AST/import boundary + runtime fake-collaborator + module-graph completeness.
- API seam `POST /runs/{run_id}/candidates/{candidate_id}/promotion-ticket` (issue) + `POST /promotion-tickets/{id}:consume` (register), principal-scoped (`api/research_alpha.py:42-52`).
- Covers **SC2 concurrent half**, **SC3** (reviewed+exact-bound ⇒ revision+catalog; unreviewed absent), **SC4** (research-only surface + guard).

> Alternative 3-plan split (if the planner wants isolation): pull the boundary guard into **49-03**. Not recommended — the guard is small and naturally proves 49-02's surface.

---

## 8. Risks & open questions

- **R1 — expire vs conflict taxonomy** (§2.3): which divergences expire (re-issueable) vs conflict (hard reject). Recommendation given; ratify at plan time.
- **R2 — re-run-admission temptation**: a reviewer may expect "refresh" to mean re-scoring. The research-only, frozen-snapshot rationale (§2.3) says re-verify only. Document this explicitly in the plan so it is not "fixed" into re-computation later.
- **R3 — duplicate formal factors**: two promotions of structurally-identical candidates produce two formal factors with identical `ast_signature`. This is **correct** (no silent merge, AF-REQ-19 precedent) — `discover_similar` (`factor_registry.py:339-362`) surfaces `exact_structural_match` so the reviewer sees the duplication. No dedup at promotion time.
- **R4 — cross-run promotion of the same candidate family**: out of scope here (a candidate is bound to one `run_id`); Phase 50 family comparison (`catalog.compare`) is the lens, not promotion-time merging.
- **R5 — admission verdict bound to exploratory revision**: the verdict row's `revision_id` is the exploratory revision (`alpha_scoring.record_candidate_admission`, `alpha_scoring.py:338-353`). The promotion summary must cite `admission_verdict_id` (not re-bind the verdict to the formal revision, which would imply re-admitting). The formal factor's catalog identity is the promotion snapshot, not the verdict row.
- **R6 — `originating_run_id UNIQUE` on `research_experiments`** (`migrations.py:178`): the promotion snapshot must use a promotion-scoped run-id (`promotion:{ticket_id}`) to avoid colliding with the evaluation run's own snapshot. Precedent: `admitted-factor-summary:{revision_id}` (`catalog.py:392`).

---

## 9. Confidence

**High** on the mapping (Q1), atomic handoff (Q3), catalog identity (Q4), signal compatibility (Q5), and boundary guard (Q6): all reuse frozen, file-evidenced, append-only contracts from Phases 45-48 with no new engine. **Medium-High** on ticket design (Q2): the binding set is clear; the expire-vs-conflict taxonomy (R1) and the explicit re-verify-not-recompute stance (R2) need plan-time ratification. **No new dependency, no new framework, no second evaluator, no execution authority, no AGPL source** — every locked boundary (ROADMAP.md:8-16, REQUIREMENTS.md:10-20) is honored.
