# Phase 47 UAT — Governed Scoring, Admission & Selection OOS

**Phase:** 47 · **Requirements:** AF-REQ-05, AF-REQ-06, AF-REQ-07, AF-REQ-08, AF-REQ-09 · **Date:** 2026-08-09
**Verifier:** `.planning/phases/47-governed-scoring-admission/47-VERIFICATION.md` — **passed** (score 100, 0 human_items)

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | All factor computation through FactorSignalChain with declared fingerprints | ✅ | AF-REQ-05: exploratory revision binding (catalog non-leakage via list_current filter); 6 declared fingerprints (panel/membership/source_field/warmup/missing_data/signal); factor_fold_scorer (no backtest); assert_all_scoring_through_chain guard passes live |
| UAT-2 | Measured A-share dates + PIT membership per fold; policy states declared; substitution fails closed | ✅ | AF-REQ-06: additive scoring/cost/fold manifest (required only when scoring declared); 7-key per-state pre_filter_counts; PIT membership fail-closed (empty→_empty_frame, never all-symbols) |
| UAT-3 | Per-candidate immutable evidence; failure = terminal reason, never zero score | ✅ | AF-REQ-07: record_candidate_evidence (content-addressed artifact); typed research_alpha_fold_evidence table (candidate-keyed UNIQUE, INSERT-only); failed→status='failed'+reason; cost/turnover diagnostic (not P&L) |
| UAT-4 | Admission gates expose observed/threshold/reason; factory/Agent cannot edit | ✅ | AF-REQ-08: record_candidate_admission (verdict+gate trail); ADMISSION_POLICY_FINGERPRINT (7 thresholds+version+gate order, frozen+verify fail-closed); assert_admission_no_edit source guard; no threshold kwargs in run_admission signature |
| UAT-5 | Selection OOS evaluated exactly once after deterministic selection; never labeled blind | ✅ | AF-REQ-09: select_winner (deterministic, direction-aware, digest tie-break, incomplete excluded); evaluate_selection_oos (idempotent reconnect, confirm-objective-before-slot, UNIQUE backstop, is_oos=1, selection_oos status); final_blind absent from CHECK |
| UAT-6 | Explicit non-goals respected; Watchlist untouched | ✅ | No Stage 1/2/promotion/execution/second-engine/tuning/final-blind; git log backend-only; Watchlist.tsx untouched |

## Verdict

**UAT passed** — all 6 criteria satisfied. 572 tests passed (full research+migrations+API+guard), 0 failures, 0 human_items. Foundation ready for Phase 48 (FactorResearchAgent Two-Stage Workflow).
