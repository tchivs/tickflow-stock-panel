---
phase: 47-governed-scoring-admission
verified: 2026-08-09
status: passed
score: 100
behavior_unverified: []
overrides_applied: []
human_verification: []
---

# Phase 47 — Governed Scoring, Admission & Selection OOS — Verification

**Verdict: PASS.** All five acceptance criteria (AF-REQ-05/06/07/08/09) are satisfied at
code level (file:line below) and the full verification batch is green.

## Verification batch (run 2026-08-09)

```
cd backend && .venv/bin/python -m pytest \
    tests/research/ tests/test_operational_migrations.py \
    tests/api/test_run_api.py tests/test_phase45_guard.py -x -q
→ 572 passed in 70.48s
```

This matches the orchestrator regression claim (572 passed across research + migrations +
API + architectural guard). No failures, no skips, no xfail.

| Batch file | Role |
|------------|------|
| `tests/research/` | Phase 47 scoring/admission/selection contracts + research regression |
| `tests/test_operational_migrations.py` | `research_alpha_fold_evidence` table + `selection_oos` rebuild (data preservation, UNIQUE, triggers, `foreign_keys`) |
| `tests/api/test_run_api.py` | Run-API authority/retry/idempotency contracts unaffected |
| `tests/test_phase45_guard.py` | Architectural boundary guards (no prohibited imports, no second DB, no watchlist import in phase modules, no SSE, no new router) |

Per-plan SUMMARY test totals (each wave's reported count, all green):

| Wave | Claimed | Scope |
|------|---------|-------|
| 47-01 | 396 passed | full research suite (18 new in `test_alpha_scoring.py`) |
| 47-02 | 445 passed | research + migrations (29 new) |
| 47-03 | 448 passed | full research sweep (24 new) |
| 47-04 | 192+20 passed | `test_alpha_scoring.py`+`test_run_contract.py` / `test_walkforward.py` |

## AF-REQ evidence table

### AF-REQ-05 — Governed scoring identity seam — PASS

The three load-bearing engines (chain / evaluation / admission) operate unchanged against
one candidate-bound evaluatable identity; no second signal engine, no forked `_binding`.

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| Exploratory revision binds candidate → identity | `backend/app/research/factor_registry.py:17` (`ALPHA_EXPLORATORY_KIND`); `:287-337` `create_exploratory_revision` — idempotent (`find`-before-mint, `:311-313`) + fail-closed DSL/fields round-trip mirroring `_binding` (`:314-325`); `:267-285` `find_exploratory_revision` |
| Catalog non-leakage (formal catalog + similarity pool) | `factor_registry.py:250-265` `list_current()` filters `alpha_exploratory` (covers `GET /factors` and `discover_similar` → `_jaccard_duplicate`) |
| Six declared fingerprints on chain frame | `signal_chain.py:66` `declared_fingerprints` field; `:351-396` `_declared_fingerprints` — exactly six SHA-256 keys `panel`/`membership`/`source_field`/`warmup`/`missing_data`/`signal` (`panel`/`membership` reuse existing values, no recompute); wired into `compute` (`:217-232`) and `_empty_frame` (`:454-462`) |
| Factory fold scorer via chain frame (no backtest) | `alpha_scoring.py:30-61` `factor_fold_scorer` — reuses `evaluation._per_date_correlation_series`/`_summary`/`_coverage`; reads only `fold.test_start/test_end`, **never** `oos_fold` |
| SC1 durable guard | `alpha_scoring.py:78-102` `assert_all_scoring_through_chain` — inspects `FactorEvaluationService.evaluate`, `admission.run_admission`, `walkforward._run_fold`; **verified PASS against live source** |

### AF-REQ-06 — Additive scoring/cost/fold manifest + per-state counts + cost diagnostic — PASS

Additive, scoring-gated validation (no-scoring manifest validates byte-for-byte); a
turnover×cost *diagnostic*, not execution P&L.

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| Scoring-gated manifest validation | `run_contract.py:151-198` `_validate_scoring_stage`; `:200-251` `validate_manifest` calls it only when `scoring` declared — `fold_geometry.oos_size`/`horizon` positive int (`:171-174`); `costs.commission_pct`/`stamp_tax_pct` ∈ [0,1) (`:179-182`); `slippage_bps` ∈ [0,1e4) basis points (`:183-188`); `scoring.rebalance`/`n_groups`/`warmup_days` (`:190-198`) |
| Per-state pre_filter_counts (7 keys) | `signal_chain.py:161-199` — partitions cross-section: `total`/`finite`/`non_finite`/`suspended`/`stale`/`source_quality_excluded`/`warmup_excluded`; warmup dates carry `warmup_excluded==total` (`:191-198`) |
| Cost/turnover diagnostic (NOT P&L) | `evaluation.py:105-171` `cost_diagnostics` — turnover `0.5·Σ|w_t−w_{t−1}|`, `cost_drag = total_turnover·cost_rate` (`:163`), `net_long_short_return` (`:170`); does not invoke `StrategyBacktestService`; wired into `evaluate` (`:312,328,365`) + `ResolvedEvaluationConfig.costs` (`:54-55`), `FactorEvaluationResult.cost_diagnostics` (`:209`) |

### AF-REQ-07 — Immutable per-candidate evidence + failure-as-reason — PASS

One content-addressed evidence artifact per candidate; a failed evaluation is a terminal
`failed` reason — never a zero score, never a `completed` evidence row.

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| Failure-as-reason mapping | `alpha_scoring.py:110-126` `_candidate_outcome` — `failed` + diagnostic, never zero score |
| Immutable evidence binding | `alpha_scoring.py:129-191` `record_candidate_evidence` — writes one content-addressed artifact (`:162`), records via service-owned `append_artifact` (`:164-173`), appends attempt with `evidence_artifact_id` + `artifact_verified=True` (`:189-190`), status from `_candidate_outcome` (`:174`) |
| Selection-fold evidence (is_oos=0, idempotent) | `alpha_scoring.py:194-241` `record_selection_fold_evidence` — find-before-record (`:214-222`), never the reserved OOS fold |
| Typed candidate-keyed fold table | `migrations.py:2197-2221` `research_alpha_fold_evidence` — `UNIQUE (run_id, candidate_digest, fold_index, is_oos)` (`:2212`), `no_update`/`no_delete` triggers (`:2216-2221`); `repository.py:1169-1235` `record_alpha_fold_evidence` INSERT raises "alpha fold evidence already recorded" (`:1224-1225`); `:1238-1262` `find_alpha_fold_evidence` idempotent read |

### AF-REQ-08 — Admission verdict + ledger linkage + no-edit fingerprint — PASS

Admission verdicts link to the candidate ledger; the no-edit guarantee is explicit and
fail-closed (frozen fingerprint + static guard).

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| Seven fixed thresholds + gate order | `admission.py:40-48` (7 constants); `:53-55` `ADMISSION_GATE_ORDER` = `no_lookahead, coverage, no_label_leakage, similarity_dedup, train_ic, val_ic` — **matches the live `run_admission` sequence** (gate entries at `:267,317,332,348,368,383`; admitted at `:403`) |
| Policy fingerprint (7 thresholds + version + gate order) | `admission.py:78-101` `admission_policy_fingerprint` — payload `policy_version` + `thresholds` (7) + `gate_order`; `:107` `ADMISSION_POLICY_FINGERPRINT` frozen at module load |
| Fail-closed verify | `admission.py:110-120` `verify_admission_policy_fingerprint` — raises `AdmissionPolicyMismatchError` on `None`/mismatch; **verified live**: `verify(frozen)` OK, `verify(None)` raises |
| Candidate-ledger-linked verdict | `alpha_scoring.py:287-418` `record_candidate_admission` — `verify_admission_policy_fingerprint` before scoring (`:332`); `run_admission` with **no** threshold/gate-order kwargs (`:349-366`); failure caught → `status='failed'` (`:367-393`); terminal status verbatim from verdict (`:396-417`); fingerprint resolved from run snapshot (`:270-284`) |
| Server-owned fingerprint at freeze | `run_contract.py:319-328` `freeze_input_snapshot` overwrites `policy.fingerprint` with live `ADMISSION_POLICY_FINGERPRINT`; `:242-248` validates shape; `:287-292` `ResearchInputSnapshot.policy_fingerprint` accessor |
| No-edit guard | `alpha_scoring.py:425-505` `assert_admission_no_edit` — `_run_admission_signature_clean` + `_source_mutates_policy` + `_source_inserts_verdict`; **verified PASS against live source** |

### AF-REQ-09 — Deterministic selection + exactly-once selection OOS — PASS

One winner chosen deterministically; the reserved OOS fold is evaluated exactly once and
labeled `selection_oos` — never a blind final validation.

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| Deterministic selection | `alpha_scoring.py:535-617` `select_winner` — loads `is_oos=0` rows (`:557`); union of fold indices (`:567-572`); incomplete candidates excluded fail-closed (`:577-578`); direction-aware sort primary (`:604-605`), `candidate_digest` lexicographic tie-break (`:603`); no-complete raises (`:595-599`) |
| Exactly-once + idempotent reconnect | `alpha_scoring.py:620-734` `evaluate_selection_oos` — find-before-write reconnect (`:655-662`); OOS computed once over `plan.oos_fold` (`:666-667`); WR-02 confirm `< 10` effective days (`:676-679`) **and** missing objective (`:685-688`) raise BEFORE write; record `is_oos=1` (`:693-706`, UNIQUE backstop); `selection_oos` ledger fact, fresh id/ordinal (`:711-733`); never `final_blind` |
| Selection-fold scorer never touches OOS | `alpha_scoring.py:30-61` `factor_fold_scorer` uses only `fold.test_start/test_end`; OOS inaccessibility enforced by `run_walk_forward(evaluate_oos=False)` |
| `selection_oos` status + rebuild | `run_contract.py:404-415` `CANDIDATE_STATUSES` includes `selection_oos` (`:414`), `final_blind` absent; `migrations.py:2224-2296` rebuild — CREATE `_v2` → INSERT…SELECT (all rows/ordinals/digests/statuses preserved) → DROP → RENAME; 4 triggers recreated (`:2273-2294` incl. cross-table lineage same-run); `selection_oos` in CHECK (`:2255`), `final_blind` absent; `PRAGMA foreign_keys` OFF→ON (`:2238,2295`) |
| Cache-only read for selection | `repository.py:1264+` `list_alpha_fold_evidence` (mirrors `list_wf_folds`, no re-validation) |

## Live-source guard execution (2026-08-09)

Both source-level guards were executed against the live source — neither raises:

```
assert_all_scoring_through_chain()  → PASS
assert_admission_no_edit()          → PASS
ADMISSION_POLICY_FINGERPRINT (frozen at load)  = f5420c5d…259576
admission_policy_fingerprint() (recomputed)     = f5420c5d…259576  (frozen == recomputed)
verify_admission_policy_fingerprint(frozen)     → OK
verify_admission_policy_fingerprint(None)       → AdmissionPolicyMismatchError (fail-closed)
```

## Non-goals (confirmed out of scope, correctly absent)

| Non-goal | Confirmation |
|----------|--------------|
| No Stage 1/2 two-stage workflow | Owned by Phase 48 (`ROADMAP.md:114`); Phase 47 delivers the evidence/OOS contracts handed to 48 |
| No catalog promotion | Owned by Phase 49; exploratory revisions are transient and excluded from the catalog (`factor_registry.py:250-265`); promotion not implemented |
| No execution / second P&L engine | `StrategyBacktestService` does not appear in the scoring path (only a docstring mention, `alpha_scoring.py:36`); `cost_diagnostics` is a turnover×cost diagnostic, explicitly "NOT execution P&L" (`evaluation.py:120-123`) |
| No threshold tuning / factory policy edit | `run_admission` exposes no threshold/gate-order kwargs; `assert_admission_no_edit` passes; thresholds are fixed module constants (`admission.py:40-48`) |
| No `final_blind` | Absent from `CANDIDATE_STATUSES` (`run_contract.py:404-415`) and the rebuild CHECK (`migrations.py:2252-2256`); grep confirms no occurrence in either file |

## Watchlist / frontend proof

- `frontend/src/pages/Watchlist.tsx` is **untouched**: it does not appear in `git status`
  (working tree). The constraint to never read it was honored.
- The last 8 commits (`d73a7b1` → `112945d`) are all `feat(phase-47)` / `docs(phase-47)`
  backend changes — **no Phase 47 commit touches `frontend/`**.
- The pre-existing uncommitted `frontend/` modifications in the working tree (DatePicker,
  ECharts, Layout, theme, WCAG contrast, etc.) are a separate frontend refactor unrelated
  to Phase 47; none are part of any Phase 47 commit.

## Cross-checks vs SUMMARY claims

1. **ADMISSION_GATE_ORDER vs live `run_admission` gate sequence** — MATCH. The declared
   tuple (`admission.py:53-55`) is `no_lookahead, coverage, no_label_leakage,
   similarity_dedup, train_ic, val_ic`; the live body appends `gate_results` in exactly
   that order (`:267,317,332,348,368,383`) and admits after all pass (`:403`). ✓
2. **Frozen == recomputed fingerprint** — MATCH. `ADMISSION_POLICY_FINGERPRINT` (module
   load) equals `admission_policy_fingerprint()` recomputed at call time; `verify` is
   fail-closed on `None`. ✓
3. **`factor_fold_scorer` OOS-inaccessibility** — CONFIRMED. The scorer reads only
   `fold.test_start/test_end` and never `oos_fold`/`plan.oos_fold`; only
   `evaluate_selection_oos` touches the reserved fold. ✓

**Observation (informational, not a defect):** the per-plan SUMMARY `-k` selector test
counts are keyword-dependent and do not sum to the file total (`test_alpha_scoring.py`
holds 55 test functions). A fresh `-k` collection today *meets or exceeds* each claimed
per-task count (e.g. 47-01 reports 7/7/4; live collection yields 9/10/6), because keyword
filters overlap across waves and tests were consolidated. All 55 pass in the green batch.

## Files of record (Phase 47)

| File | Phase 47 role |
|------|---------------|
| `backend/app/research/alpha_scoring.py` | fold scorer, evidence/admission/selection orchestration, both source guards |
| `backend/app/research/admission.py` | policy fingerprint, gate order, verify fail-closed |
| `backend/app/research/signal_chain.py` | declared fingerprints, per-state counts |
| `backend/app/research/factor_registry.py` | exploratory revision, catalog non-leakage |
| `backend/app/research/run_contract.py` | scoring-gated manifest validation, server-owned policy freeze, `selection_oos` status |
| `backend/app/research/evaluation.py` | `cost_diagnostics` diagnostic |
| `backend/app/research/repository.py` | candidate-keyed fold evidence record/find/list |
| `backend/app/operational/migrations.py` | `research_alpha_fold_evidence` table + `selection_oos` rebuild |
| `backend/tests/research/test_alpha_scoring.py` | 55 tests (folds, fingerprints, evidence, admission, selection/OOS) |
