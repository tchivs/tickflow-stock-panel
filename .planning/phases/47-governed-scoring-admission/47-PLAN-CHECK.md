# Phase 47 — Plan Check (goal-backward verification)

**Checked:** 2026-08-08
**Plans:** 47-01 (AF-REQ-05), 47-02 (AF-REQ-06/07), 47-03 (AF-REQ-08), 47-04 (AF-REQ-09)
**Method:** Goal-backward per requirement → plan → task; every load-bearing source claim re-verified against current `backend/`.

## Verdict: **APPROVE — 0 blockers**

All five AF-REQs map 1:1 to concrete, verifiable tasks. Test-file placement is collision-free, the exploratory-revision / admission-fingerprint / exactly-once mechanisms are sound and match the live code, and the wave graph is acyclic. Four warnings below are implementable within the plans as written (placement/coordination notes, not correctness gaps).

## Test-file placement (Q1) — OK

| File | Status | Owners |
|---|---|---|
| `tests/research/test_alpha_scoring.py` | **NEW** (absent on disk) — no collision | 47-01 creates; 47-02/03/04 extend |
| `tests/research/test_admission.py` | present | 47-03 extends |
| `tests/research/test_run_contract.py` | present | 47-02 extends |
| `tests/test_operational_migrations.py` | present | 47-02 (fold-evidence table), 47-04 (status rebuild) — different waves |
| `backend/app/research/alpha_scoring.py` | **NEW module** | 47-01 creates; 47-02/03/04 extend |

## Mechanism verification (Q2–Q5) — OK

- **Q2 (47-01 OQ1 binding):** `create_exploratory_revision` delegates to the verified `FactorRegistry.create_revision(expression, *, hypothesis, provenance)` (factor_registry.py:130-142), which stores provenance verbatim via `create_factor_with_revision`. The revision id flows unchanged into `chain.compute(revision_id=…)`, `FactorEvaluationService.evaluate`, and `run_admission` (no signature change — confirmed `run_admission` binds on `revision_id`). `_binding` stays the single validation surface (option A; no `compute_expression` fork). `fold_scorer` seam matches live `walkforward.py:578` (`fold_scorer(fold=…, frame=…, membership=…)`). `assert_all_scoring_through_chain` covers all five scoring entry points (evaluate / run_admission / `_run_fold` / `evaluate_best_params` / factory scoring). → **See W2** for the leakage-filter placement nuance.
- **Q3 (47-02 OQ2 additive):** `validate_manifest` (run_contract.py:145-180) validates only the `required_types` tuple; a scoring-gated block appended after it cannot invalidate a no-`scoring` manifest → Phase 45/46 frozen snapshots are byte-for-byte safe (verified the loop only enforces listed triples). `research_alpha_fold_evidence` is additive (new migration string appended to `MIGRATIONS`), candidate-keyed `UNIQUE (run_id, candidate_digest, fold_index, is_oos)`, INSERT-only triggers mirroring `wf_folds`. `wf_folds` confirmed strategy/params-shaped (`UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)`, migrations.py:1748) → the typed-table verdict is correct; `wf_folds`/`wf_validated_strategies` untouched.
- **Q4 (47-03 fingerprint + no-edit):** Inputs = seven threshold constants (TRAIN_MIN_MEAN_IC, VAL_MIN_MEAN_IC, MIN_TRAIN_OBSERVATIONS, MAX_SIMILARITY_SCORE, MAX_IC_CORRELATION, SHIFTED_LABEL_MAX_ABS_IC, MIN_COVERAGE — admission.py:41-47) + `ADMISSION_POLICY_VERSION="admission-policy-v1"` (line 40) + gate order. **Declared `ADMISSION_GATE_ORDER` exactly matches the live gate sequence** verified at admission.py:195/245/260/276/296/311. `verify_admission_policy_fingerprint` recomputes from live constants and raises on mismatch, called before any candidate is scored; `freeze_input_snapshot` populates `policy.fingerprint` server-side (client value cannot survive). No-edit guard is structural: `run_admission` confirmed to expose **no threshold/gate-order kwargs** (admission.py:110-128); guard also forbids direct `insert_admission_verdict` from scoring modules.
- **Q5 (47-04 exactly-once):** Status rebuild replicates the verified Phase 46 pattern (migrations.py:2128-2184: PRAGMA off → drop lineage trigger → CREATE `_v2` → INSERT…SELECT → DROP → RENAME → recreate index + 4 triggers → PRAGMA on); adds `selection_oos` as 10th CHECK value, `final_blind` absent. `evaluate_selection_oos` mirrors `evaluate_best_params`: idempotent read-first (`find_alpha_fold_evidence`) → `chain.compute` → effective_days<10 reject → factor `fold_scorer` → **confirm-objective-before-slot (WR-02, walkforward.py:312-317)** → `record_alpha_fold_evidence(is_oos=1)` (UNIQUE raises on second) → `status='selection_oos'`. `select_winner` is deterministic (frozen objective + `candidate_digest` tie-break), fail-closed on incomplete fold evidence.

## Warnings (numbered + resolution)

- **W1 — Wave-2 shared-file overlap (47-02 ∩ 47-03).** Both declare `run_contract.py`, `alpha_scoring.py`, `test_alpha_scoring.py`. The material overlap is `validate_manifest` / `freeze_input_snapshot`: 47-02-01 appends the scoring-gated block; 47-03-02 adds `policy.fingerprint` validation + server-side population. `migrations.py` is NOT shared (47-02 adds the fold-evidence table; 47-03 touches none). *Resolution:* the executor must treat `run_contract.py` as a coordinated shared write — either sequence 47-03's `run_contract.py` edit after 47-02's, or merge the two `validate_manifest` additions in one pass. The edits target adjacent-but-distinct regions, so a clean merge is achievable.
- **W2 — Exploratory-revision leakage filter placement (47-01).** `discover_similar` iterates `list_current()` over **all** registry revisions (factor_registry.py:258), so an exploratory revision registered via `create_revision` WILL appear in the similarity pool — the exclusion filter is genuinely required (confirmed, not theoretical). The plan's action says "Ensure `_jaccard_duplicate` … EXCLUDES `provenance.kind==alpha_exploratory`" but `_jaccard_duplicate` lives in `admission.py`, which is **not** in 47-01's `files_modified`. *Resolution:* place the `provenance.kind` filter at `discover_similar`/`list_current` in `factor_registry.py` (in declared scope) so all registry consumers are covered and 47-01's `files_modified` stays accurate; widen the similarity-pool test to assert `discover_similar` itself excludes exploratory revisions. If the executor filters in `_jaccard_duplicate` instead, `admission.py` must be added to 47-01's `files_modified`.
- **W3 — Static-guard scope (47-01, 47-03).** `assert_all_scoring_through_chain` and `assert_admission_no_edit` are import-graph + call-site guards: they prove source-level routing/no-edit but cannot see dynamic dispatch or runtime monkeypatching. This is acceptable for the stated threats (factory/Agent source edits) but the guards are structural, not behavioral. *Resolution:* document the guards as source-level in their docstrings; no code change.
- **W4 — `missing_data` fingerprint forward-compat (47-01 → 47-02).** 47-01-02 defines `missing_data` over `pre_filter_counts`; 47-02-02 changes that shape from `{total, finite}` to seven per-state keys. 47-01 correctly flags this as forward-compatible, but since 47-01 is wave 1 and 47-02 wave 2, the `missing_data` digest computed in 47-01 will change once 47-02 lands. No frozen snapshot references it yet (all new in Phase 47), so nothing breaks. *Resolution:* 47-01's fingerprint-sensitivity test should pin the current `{total, finite}` shape and explicitly note the 47-02 enrichment intentionally changes the digest; the wave-2 shape is what ships.

## Notes

- Wave graph is acyclic and matches `depends_on`: 47-01 w1 (no deps); 47-02 w2 + 47-03 w2 (both `depends_on: ["47-01"]`); 47-04 w3 (`depends_on: ["47-02","47-03"]`). Verify commands are syntactically valid `cd backend && pytest … -k '…' -q` chains (including the `&&`-joined ones in 47-02-03 / 47-03-02 / 47-04-01).
- Failure-as-reason is consistent across 47-02 (`status='failed'` from evaluation failure) and 47-03 (`run_admission` `ValueError`/`SignalChainError` → `status='failed'`), both honoring AF-REQ-07 "failure is never a zero score." `run_admission` confirmed to raise on empty panels (admission.py:160) — the catch path is reachable.
- **Non-goals (Q7) honored:** no Stage 1/2 provider orchestration (handoff explicitly defers two-stage workflow to Phase 48); no human promotion (catalog promotion → Phase 49, T-47-01); no live/paper execution (cost item is a documented diagnostic, not P&L; admission group-NAV unchanged at fees=0); no separate signal engine (option A reuses `_binding`/`compute`); no threshold tuning (fixed constants + fail-closed fingerprint); no final-blind holdout (`selection_oos` only, `final_blind` absent — consistent with ROADMAP.md:106).

## AF-REQ coverage matrix

| Req | Plan | Success Criterion | Tasks | Coverage |
|---|---|---|---|---|
| AF-REQ-05 | 47-01 | SC1 — all scoring through chain + panel/universe/source/warmup/missing-data/signal fingerprints | 47-01-01 (exploratory binding), 47-01-02 (declared_fingerprints), 47-01-03 (fold_scorer + chain-routing guard) | FULL |
| AF-REQ-06 | 47-02 | SC2 — measured dates/PIT/policy states fail-closed on substitution | 47-02-01 (scoring-gated manifest oos_size/horizon/costs/scoring), 47-02-02 (per-state pre_filter_counts) | FULL |
| AF-REQ-07 | 47-02 | SC3 — immutable evidence + costs/turnover + failure-as-reason | 47-02-02 (cost_diagnostics), 47-02-03 (artifact binding + fold-evidence table + failed status) | FULL |
| AF-REQ-08 | 47-03 | SC4 — admission gates observed/threshold/reason + no-edit + ledger linkage | 47-03-01 (ledger linkage via revision id), 47-03-02 (ADMISSION_POLICY_FINGERPRINT + no-edit guard) | FULL |
| AF-REQ-09 | 47-04 | SC5 — selection OOS exactly-once, never blind | 47-04-01 (selection_oos status + exactly-once OOS), 47-04-02 (deterministic select_winner) | FULL |

No orphan requirements; no orphan tasks. Plans are ready for execution subject to the W1/W2 coordination notes.
