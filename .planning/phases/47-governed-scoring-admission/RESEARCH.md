# Phase 47: Governed Scoring, Admission & Selection OOS — Research

**Researched:** 2026-08-08
**Domain:** Governed candidate scoring, deterministic admission exposure, and exactly-once selection-OOS over the existing `FactorSignalChain` + measured-calendar walk-forward engine
**Confidence:** HIGH for chain/admission/evaluation reuse and the typed-fold-evidence decision; MEDIUM for the cost/turnover diagnostic shape and the candidate→revision binding seam

## Summary

Phase 47 turns the Phase 46 generated candidate population (`status='generated'`, `backend/app/research/alpha_factory.py:873`) into **reproducible governed evidence + fixed admission verdicts + a single honest selection-OOS evaluation**. The good news: the three load-bearing engines already exist and already route through the shared chain. `FactorEvaluationService` already calls `FactorSignalChain.compute` (`evaluation.py:168,202`), `run_admission` already builds its own chain (`admission.py:142-157`), and `walkforward._run_fold` already calls `chain.compute` per fold (`walkforward.py:564`). The failure path already returns a terminal reason rather than a zero score (`evaluation.py:493-508`), and every admission gate already exposes its observed value, threshold, pass/fail, and detail (`admission.py:243-320`).

The real work is **identity binding and missing fingerprints**, not new engines. Four gaps dominate:

1. **Candidate ↔ revision impedance mismatch.** The chain, evaluation, and admission all bind to a *`factor_revision_id` in the registry* (`signal_chain.py:109,213-222`; `admission.py:138`; `evaluation.py:174`), but Phase 46 emits `AlphaCandidateAttempt` rows keyed by `(run_id, candidate_digest, canonical_expression)` (`run_contract.py:362-380`). A `generated` candidate has no `FactorRevision`. Phase 47 must bind each candidate to an evaluatable identity (a transient/exploratory revision or a candidate-expression compute entry) so it can flow through the existing chain.
2. **Incomplete fingerprint set (SC1).** The chain exposes `panel_fingerprint` and `resolved_universe.membership_fingerprint` (`signal_chain.py:60,179,322-324`), but SC1 demands explicit *source-field, warmup, missing-data, and signal* fingerprints. These are partly scattered across `evaluation._manifest` (`evaluation.py:417-468`); they must be consolidated into one declared fingerprint set.
3. **Typed Alpha fold evidence (research flag).** `wf_folds` is keyed by `(plan_id, fold_index, is_oos, strategy_id, params_sha256)` (`migrations.py:1733-1748`) — *strategy-parameter-shaped*. A factor candidate is keyed by `(run_id, candidate_digest)`. Reusing `wf_folds` would weaken the existing exactly-once UNIQUE and mix two identity models. **Verdict: reuse the fold GEOMETRY engine, add typed Alpha fold-evidence rows** (see §4).
4. **Cost/turnover diagnostics (SC3).** The A-share cost model exists in `BacktestConfig` (`engine.py:39-77`: commission + sell-only stamp tax + slippage), but the factor supplemental path (`_calc_group_nav`/`_calc_long_short`, `factor.py:402-552`) compounds raw forward returns — it neither applies costs nor computes turnover, and admission passes `fees_pct=0.0, slippage_bps=0.0` (`admission.py:436-437`). Phase 47 must add a factor-scoped cost/turnover diagnostic *without* a second backtest engine.

**Primary recommendation:** four dependency-ordered plans. 47-01 wires every scoring path through the chain and completes the fingerprint set + candidate→evaluatable binding; 47-02 produces immutable per-candidate evaluation evidence (metrics + failure-as-reason + cost/turnover) bound to the candidate ledger and extends the frozen manifest with `oos_size`, `horizon`, costs, rebalance, n_groups, warmup; 47-03 exposes admission verdicts against candidate identities and hardens the no-edit guarantee; 47-04 implements deterministic selection + exactly-once `selection_oos` over typed fold rows. No new dependencies, no second signal engine, no threshold tuning.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AF-REQ-05 | All factor computation (Factory scoring, Agent evaluation, admission, composite, walk-forward, as-of serving) goes through `FactorSignalChain` and exposes panel/universe/source/warmup/missing-data/signal fingerprints. | Chain already exists and is already called by evaluation/admission/walkforward; candidate binding + missing fingerprints are the gap (§1, §2). |
| AF-REQ-06 | Measured A-share trading dates + PIT membership per fold; missing/suspended/non-finite/warmup/stale follow declared policy; current-constituent/full-lake substitution fails closed. | `trading_calendar()` + `resolve_universe_daily()` + chain membership join already fail-closed; stale/suspended/source-quality states need explicit declaration (§5). |
| AF-REQ-07 | Per-candidate immutable evidence: per-date IC/RankIC, ICIR, positive rate, coverage, monthly robustness, group/long-short, fees/slippage, cost/turnover, artifacts, terminal failure reason. | `FactorEvaluationResult` already carries IC/RankIC/ICIR/robustness/coverage/group/long-short + failure diagnostics; cost/turnover + per-candidate durable binding are the gap (§2, §7). |
| AF-REQ-08 | Admission exposes observed value/threshold/pass-fail/reason per gate; factory/Agent cannot edit thresholds/reorder gates/convert rejection→admission; rejected/failed linked to candidate ledger. | Gates already expose all four fields; thresholds are module constants; linkage to candidate ledger + no-edit hardening are the gap (§3). |
| AF-REQ-09 | Selection-fold evidence only during search/Agent review; after selection, reserved fold gets ONE `selection_oos` evaluation with exactly-once durable binding; reconnect/retry returns existing; never labeled blind final validation. | `evaluate_best_params` is the existing exactly-once pattern but strategy/params-shaped; needs typed candidate-keyed OOS + `selection_oos` status (§4, §6). |

## 1. FactorSignalChain — what exists, what must be wired (AF-REQ-05 SC1)

### Current exposure

`FactorSignalChain.compute(revision_id, config) -> FactorSignalFrame` (`signal_chain.py:106`) is the single compile-to-compute path. It compiles the revision's canonical expression via `parsed.compile()` (`signal_chain.py:132`), loads one governed panel through `BacktestEngine.load_panel` (`signal_chain.py:259-267`), resolves per-date PIT membership by **inner-join after the governed read** (`signal_chain.py:113-127`), computes `_factor`/`_rank`/`_zscore`/`_forward_return` (`signal_chain.py:132-173`), and returns a frame carrying:

- `panel_fingerprint` — sha256 over schema + observed_start/end + row_count (`signal_chain.py:60,179,282-300`).
- `resolved_universe` — a mapping with `method` (`factor_universe_membership/v1` or `config-symbols`), `membership_fingerprint` (`signal_chain.py:322-324`), `per_date_symbol_counts`, `excluded_delisted`, and `pre_filter_counts` (`signal_chain.py:320-328`).
- `required_source_fields` — the tuple of source columns the expression reads (`signal_chain.py:64,225-226`).

### Already used by the scoring paths

- `FactorEvaluationService` holds one chain (`evaluation.py:168`) and calls `compute` (`evaluation.py:202`).
- `run_admission` builds its own chain and calls `compute` (`admission.py:142-157`).
- `walkforward._run_fold` calls `chain.compute(revision_id=strategy_id, config=fold.chain_config)` per fold (`walkforward.py:564`); `evaluate_best_params` calls it for the OOS fold (`walkforward.py:278-280`).

So "all scoring through the chain" is **largely true today** for revision/strategy identities. The Phase 47 gap is (a) the factory scoring path does not yet exist (Phase 46 only *generates*; `drive_alpha_generation` never evaluates, `alpha_factory.py:1094-1101`), and (b) it must bind to candidate identities, not pre-existing revisions.

### Wiring required

1. **Candidate → evaluatable identity.** `compute`'s first line is `_binding(revision_id)` → `registry.get_revision` (`signal_chain.py:109,213-214`). A `generated` candidate is an `AlphaCandidateAttempt`, not a registry revision. Two options:
   - **(A) Transient exploratory revision:** register a non-catalog `FactorRevision` per generated candidate (research-only, exploratory provenance) so the existing chain/evaluation/admission operate unchanged. Lowest churn; reuses `FactorRegistry.create_revision` provenance path; the revision's `provenance` links back to `(run_id, candidate_id)`.
   - **(B) Candidate-expression compute entry point:** add `FactorSignalChain.compute_expression(canonical_expression, dsl_version, config)` that parses inline (bypassing `_binding`), so candidates compute without a registry row. Cleaner identity model but forks one code path off `_binding`'s DSL-version/field-binding checks.
   - **Recommend (A):** it preserves the single `_binding` validation surface (DSL-version + referenced-fields consistency, `signal_chain.py:217-221`) and lets admission verdicts and evaluation artifacts attach to a stable revision id that already carries provenance. The exploratory revision is research-only and never enters the formal catalog (Phase 49 owns catalog admission).
2. **Complete the fingerprint set** (§2). Consolidate panel/PIT/source/warmup/missing-data/signal fingerprints into one declared block on `FactorSignalFrame` (or its evaluation wrapper).
3. **Factory fold scorer seam.** `walkforward._run_fold` already accepts an injectable `fold_scorer(fold, *, frame, membership) -> dict` (`walkforward.py:578-581`). Phase 47 supplies a factor scorer that turns the `FactorSignalFrame` into per-fold IC/coverage evidence via the existing `evaluation._per_date_correlation_series`/`_coverage` helpers (`evaluation.py:68-88,376-387`), rather than the default `_default_fold_score` strategy backtest (`walkforward.py:642-681`).

## 2. Evaluation evidence — what exists, what's missing (AF-REQ-07 SC3)

### Metrics that exist today

`FactorEvaluationResult` (`evaluation.py:103-152`) is already a retention-ready immutable evidence package:

| Evidence | Source | Status |
|----------|--------|--------|
| Per-date IC + RankIC | `_per_date_correlation_series` (`evaluation.py:68-88`) | ✓ present |
| IC/RankIC summary (mean/std/IR/positive_rate/observations) | `_summary` (`evaluation.py:332-345`) | ✓ present |
| ICIR | `_monthly_evidence` (`evaluation.py:367-370`) | ✓ present |
| Monthly robustness | `_monthly_evidence` (`evaluation.py:371-373`) | ✓ present |
| Coverage (mean + per-date series) | `_coverage` (`evaluation.py:376-387`) | ✓ present |
| Monthly IC series | `_monthly_evidence` (`evaluation.py:358-365`) | ✓ present |
| Group stats + group NAV | `_supplemental_evidence` → `_calc_group_nav`/`_calc_group_stats` (`evaluation.py:403-408`) | ✓ present |
| Long-short stats + NAV | `_calc_long_short` (`evaluation.py:409`) | ✓ present |
| Terminal failure reason (not a zero score) | `_failed` returns `status="failed"` with `diagnostics` (`evaluation.py:493-508,201-222`) | ✓ present |
| Artifacts (Parquet signals/metrics) | `artifact_service.write_bundle` (`evaluation.py:244-258`) | ✓ present |
| Resolved config + input manifest | `ResolvedEvaluationConfig.as_dict` (`evaluation.py:56-61`), `_manifest` (`evaluation.py:417-468`) | ✓ present |

### Gaps for SC3

1. **Cost/turnover diagnostics — MISSING.** `ResolvedEvaluationConfig` carries `fees_pct`/`slippage_bps` (`evaluation.py:53-54`) and `_supplemental_evidence` builds a `FactorConfig` with them (`evaluation.py:391-402`), but `_calc_group_nav`/`_calc_long_short` (`factor.py:402-552`) compound raw `_forward_return` and never apply costs or measure turnover. The real cost model lives in `BacktestConfig` (`engine.py:39-77`: commission_pct + sell-only stamp_tax_pct + slippage_bps) and is only exercised by the strategy backtest. **Design (§7):** add a factor-scoped turnover/cost diagnostic computed from the same rebalance-dated chain frame (rank/zscore already present, `signal_chain.py:167-173`), expressed as `turnover × cost_rate`, *without* a second backtest. Robustness beyond monthly-IC-share (e.g. group monotonicity) is a low-cost add on the existing `group_stats`.
2. **Per-candidate durable binding — MISSING.** `FactorEvaluationResult` is an in-memory package; artifacts are written to Parquet (`evaluation.py:244`) but the candidate ledger has only a single `evidence_artifact_id` slot (`run_contract.py:379`; `migrations.py:1947`). Today that slot is always `None` for generated candidates. Phase 47 must bind the evaluation artifact (or a compact metrics artifact) to each evaluated candidate attempt and record the `failed`/`rejected`/`admitted` outcome + reason. Recommendation: write one immutable evidence artifact per candidate via the existing `AlphaRunArtifactService` and set `evidence_artifact_id` (+ `artifact_verified=True`, `repository.py:2237-2238,2247-2248`) on the candidate attempt.
3. **Manifest cost/fold declaration — MISSING.** `validate_manifest` requires `fold_geometry.{train_size,gap_size,test_size,n_folds}` and `objective.{name,direction}` only (`run_contract.py:162-168`). It does **not** require `oos_size`, `horizon`, costs, `rebalance`, `n_groups`, or `warmup_days` — all of which scoring needs. AF-REQ-01 already promises "objective/cost policy … fold geometry". Phase 47 extends the manifest (additive fields under `fold_geometry` + a `costs`/`objective` sub-group) and validates them at freeze; a changed cost/fold input changes the digest and creates a new run (no mutation).

## 3. Admission policy — exposure and the no-edit guarantee (AF-REQ-08 SC4)

### What already exists

`admission.py` runs six ordered deterministic gates with **fixed module-level thresholds** (`admission.py:40-48`): `no_lookahead`, `coverage`, `no_label_leakage`, `similarity_dedup`, `train_ic`, `val_ic` (`admission.py:187-320`). Every gate appends a result dict with `{gate, passed, metric, observed, threshold, detail}` (e.g. `admission.py:243-252,258-267,294-303`). On the first failure it records a `rejected` verdict naming the failing gate; only all-pass records `admitted` (`admission.py:204,254,269,285,305,320,331`). Verdicts are append-only via `insert_admission_verdict` (`admission.py:482`; `repository.py:712`) with an `input_snapshot_sha256` over `{revision_id, policy_version, window, horizon, membership_fingerprint, panel_fingerprint}` (`admission.py:461-473`).

So **observed/threshold/pass-fail/reason per gate is already exposed**, and **thresholds are structurally immutable** (module constants, not function parameters — `run_admission` takes no threshold kwargs, `admission.py:110-128`).

### Gaps for SC4

1. **Candidate-ledger linkage.** `run_admission` operates on a `revision_id` (`admission.py:115,138`) and verdicts attach to `revision_id` (`admission.py:483`), not to an Alpha candidate. Phase 47 must record the admission outcome back onto the candidate attempt: `append_candidate_attempt` with `status='rejected'`/`'admitted'`/`'failed'` + a `reason` carrying the gate trail (`run_contract.py:317-327`; `repository.py:2254-2256` validates status against the enum). With option (A) from §1 (transient exploratory revision), the revision id is the stable join key between the verdict row and the candidate attempt.
2. **No-edit hardening.** The manifest's `policy` group today carries `{"version": "admission-v1", "thresholds": {"min_ic": 0.02}}` in fixtures (`test_run_contract.py:35`). That `thresholds` field is **informational provenance only** — the live gates read `admission.py` constants, never `manifest["policy"]["thresholds"]` (`[VERIFIED: no consumer of policy.thresholds in app/]`). To make the no-edit guarantee explicit and fail-closed: (a) compute an `ADMISSION_POLICY_FINGERPRINT` (sha256 over the six thresholds + policy version + gate order) at module load; (b) freeze that fingerprint into the manifest `policy` group; (c) on scoring, recompute and compare — a mismatch (someone changed a constant or a gate order) fails closed before any candidate is scored. This makes "factory/Agent cannot edit thresholds/reorder gates" a verifiable invariant, not a convention.
3. **Failure → rejection, never admission.** `run_admission` raises `ValueError` on empty panels (`admission.py:159-160`). Phase 47 must catch evaluation/chain failures and record them as `status='failed'` with a terminal `reason` (consistent with AF-REQ-07 "failure is never a zero score"), distinct from a clean `rejected` (a gate legitimately failed).

## 4. Walk-forward folds — the research-flag decision (AF-REQ-06 SC2, research flag)

### Existing fold machinery (fully reusable)

- `trading_calendar(engine, …)` — measured A-share trading dates re-read from the lake each run (`walkforward.py:74-93`); fail-closed on empty.
- `build_plan(…)` — pure geometry from the measured-date list: rolling `step=test_size` folds, train/gap/test by trading-day count, edges snap to measured calendar, `oos_size` reserved, fail-closed below 2 folds (`walkforward.py:96-189`).
- `WalkForwardPlan` carries `folds`, `oos_fold`, and the full `trading_dates` tuple (`walkforward.py:54-71`); `WalkForwardFold` carries the train/gap/test rectangle + a per-fold `chain_config` + `membership_fingerprint` (`walkforward.py:38-51`).
- `_resolve_fold_membership` resolves per-fold PIT membership (`walkforward.py:630-639`); `_run_fold` calls `chain.compute` per fold (`walkforward.py:564`) and records `effective_days` (`walkforward.py:567-575`).
- OOS pre-pinned before any search reuse: `create_wf_plan` is idempotent append-only (`walkforward.py:220`; `repository.py:931-1042`).

### Research flag: generalize `wf_folds` or typed Alpha rows?

**Verdict: typed Alpha fold-evidence rows; reuse the geometry engine.**

`wf_folds` is keyed `UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)` (`migrations.py:1733-1748`); `wf_validated_strategies` binds the verdict to the once-evaluated OOS via `oos_evidence_fold_id UNIQUE` (`migrations.py:1776-1789`). Both are *strategy-parameter-shaped* (a `params_sha256` identifies a param set; `strategy_id` identifies a strategy). A factor candidate is identified by `(run_id, candidate_digest, canonical_expression)` — there is no `params_sha256`, and `strategy_id` would be a misnomer. Generalizing `wf_folds` would require making `strategy_id`/`params_sha256` nullable and adding `run_id`/`candidate_digest` columns, which:

- weakens the existing exactly-once UNIQUE (a strategy row and a candidate row could coexist ambiguously),
- changes the `fold_scorer` contract (`walkforward.py:578`) and `_default_fold_score` (`walkforward.py:642`) which assume strategy backtests,
- conflates two provenance models in one append-only table.

Instead: keep `wf_plans` as the **shared geometry** table (it is universe/asset_type/fold-size keyed, already carries `trading_dates_json`/`oos_pinned_at`, and one plan can serve both a strategy search and a candidate run over the same window). Add a **typed `research_alpha_fold_evidence` table** mirroring `wf_folds`' append-only discipline (INSERT-only triggers, `no_update`/`no_delete`) but keyed `UNIQUE (run_id, candidate_digest, fold_index, is_oos)`. The OOS exactly-once then becomes a UNIQUE over the candidate-keyed row. The fold scorer is the Phase 47 factor scorer (§1.3), not the strategy backtest. `walkforward.build_plan` + `trading_calendar` + `_resolve_fold_membership` are reused unchanged.

**Manifest gap:** `wf_plans` requires `oos_size` + `horizon` (`migrations.py:1721-1722`), but the manifest `fold_geometry` declares only `train_size/gap_size/test_size/n_folds` (`run_contract.py:162-165`). Phase 47 must add `oos_size` and `horizon` to the frozen `fold_geometry` group so a `WalkForwardPlan` can be built from the frozen manifest.

## 5. PIT membership + measured dates + policy states (AF-REQ-06 SC2)

- **Measured trading dates:** `trading_calendar` (`walkforward.py:74-93`) via `BacktestEngine.load_panel(columns=["date"])`, dedup-sorted, re-measured per run. The chain's `end = test_end + horizon` label buffer snaps to the measured calendar so weekends/holidays never shorten a test segment (`walkforward.py:485-510`).
- **PIT membership per fold:** `resolve_universe_daily` (`universe.py:67-137`) expands `listed`/`delisted` membership events into a per-date `[symbol, date]` frame. The chain inner-joins membership **after** the governed load, keeping `load_panel` byte-identical (`signal_chain.py:126-127,228-250`).
- **Current-constituent / full-lake substitution fails closed:** when membership is empty, the chain returns `_empty_frame` preserving the resolved `method` and an empty `pre_filter_counts` — it never silently falls back to all symbols (`signal_chain.py:117-121,330-358`). An empty panel still records the universe fingerprint (IN-08, `signal_chain.py:118-120`).
- **Declared policy states today:** `missing_data_treatment="drop"` (`signal_chain.py:30,204-205`) and `warmup_treatment="exclude"` (`signal_chain.py:31,206-207`) are the only two non-finite/warmup policies and both are validated explicitly (no implicit default). The finite filter drops non-finite `_factor`, non-positive `close`, and (when labeled) non-finite `_forward_return` (`signal_chain.py:162-165`).
- **Gap — explicit stale/suspended/source-quality states.** "Suspended" is currently implicit (a row simply has no close/forward-return on that date and is dropped by the finite filter). "Stale" and "source-quality" are not tracked as named states. SC2 wants these to "follow the declared policy." Phase 47 should declare the policy enum on the chain config (e.g. extend `MissingDataTreatment`/add a `SuspendedTreatment`/`StaleTreatment` literal, currently `Literal["drop"]` only, `signal_chain.py:30`) and record per-state counts in `pre_filter_counts` so the evidence names *why* a row was excluded, not just that it was.

## 6. Selection OOS exactly-once (AF-REQ-09 SC5)

### The existing exactly-once pattern (strategy-shaped)

`evaluate_best_params` (`walkforward.py:245-365`) is the template: it (1) re-pins the plan (`walkforward.py:275`), (2) resolves OOS membership + computes the frame once (`walkforward.py:277-280`), (3) confirms the objective metric exists *before* consuming the OOS slot (`walkforward.py:312-317`, so a failed OOS backtest never burns the once-only slot, WR-02), (4) records the OOS fold row whose UNIQUE makes a second evaluation raise `"OOS segment already evaluated"` (`walkforward.py:318-331`; `repository.py:1078-1127`), and (5) binds the verdict to that fold via `oos_evidence_fold_id UNIQUE` (`walkforward.py:345-355`). Search reconnect returns the existing fold via `_find_existing_fold` (`walkforward.py:560-562,602-627`).

### Phase 47 adaptation to candidates

1. **Deterministic selection.** After all candidates are scored over the selection folds, the winner is chosen deterministically by the frozen `objective.name`/`direction` (`run_contract.py:168`) with a declared tie-break (e.g. candidate_digest lexicographic) so worker timing cannot change the winner (mirrors AF-REQ-23, already satisfied for generation). Only the winner proceeds to OOS.
2. **Typed OOS row + status.** Add `selection_oos` to `CANDIDATE_STATUSES` (`run_contract.py:317-327`) via the Phase 46 rebuild pattern (`migrations.py:2128-2184`: CREATE `_v2` → INSERT → DROP → RENAME; SQLite CHECK constraints are immutable). Record the winner's OOS evidence in `research_alpha_fold_evidence` with `is_oos=1`; the `UNIQUE (run_id, candidate_digest, fold_index, is_oos=1)` makes a second OOS evaluation raise. A reconnect/retry of the *same* run/candidate returns the existing OOS row (idempotent read before write, mirroring `_find_existing_fold`).
3. **Never labeled blind final validation.** The status enum value is `selection_oos` (not `final_blind`); the explicit non-goal rules out a separate final-blind holdout (`ROADMAP.md:106`). UI/projection labels (Phase 50, AF-REQ-25) consume this status string verbatim. Phase 47's job is to ensure the data model carries exactly one OOS outcome per winning candidate and never emits a `final_blind` label.
4. **OOS inaccessibility during search.** `run_walk_forward(..., evaluate_oos=False)` is the default (`walkforward.py:202,222`); the candidate scorer over selection folds never includes the OOS fold. Phase 47 enforces the same: the selection-fold scorer iterates `plan.folds` only, never `plan.oos_fold`.

## 7. Cost / robustness evidence (AF-REQ-07, research flag "without duplicating gates")

The factor evaluation path does not currently model cost or turnover (`factor.py:402-552` compounds raw returns). Phase 47 must add factor-scoped cost/turnover diagnostics **without** running the full `StrategyBacktestService` (which would be a second engine and a cost-shape mismatch — factors have no entry/exit rules, only rebalance-dated cross-sectional weights).

**Recommended diagnostic (single pass over the chain frame):** the chain already produces rebalance-dated `_rank`/`_zscore` per `(symbol, date)` (`signal_chain.py:167-173`). Long-short weight turnover at each rebalance is `½·Σ_sym |w_t − w_{t−1}|` over the rebalance dates. Multiply by the frozen cost rate (commission + stamp + slippage from the manifest `costs` group, sourced from the same `buy_cost_pct`/`sell_cost_pct` formulas at `engine.py:69-76`) to get a per-rebalance and total cost drag. Record `{turnover_per_rebalance, total_turnover, cost_drag, net_long_short_return}` as a `cost_diagnostics` block on the evidence. This is a diagnostic computed from the same frame, not a backtest. Robustness is already covered by `monthly_robustness` (`evaluation.py:371`); add group-monotonicity (do higher groups have higher mean returns across `group_stats`, `evaluation.py:436-493`) as a cheap monotonicity score. Stress matrices (rebalance/fee/symbol-subset) are explicitly Phase 50 (`ROADMAP.md:165`); Phase 47 only ensures the evidence *shape* can later carry them without re-evaluation.

## 8. Recommended plan split

**Wave 1**
- **47-01 — FactorSignalChain wiring + complete fingerprint set + candidate binding.** Bind each `generated` candidate to an evaluatable identity (transient exploratory revision, option A §1). Consolidate panel/PIT/source-field/warmup/missing-data/signal fingerprints into one declared block on the evaluation wrapper. Supply the factory fold scorer via the existing `fold_scorer` seam (`walkforward.py:578`). Assert (test) that every scoring entry point routes through `FactorSignalChain.compute`.

**Wave 2** *(blocked on 47-01)*
- **47-02 — Immutable per-candidate evaluation evidence + manifest extension.** Extend the frozen manifest with `oos_size`, `horizon`, `costs` (commission/stamp/slippage), `rebalance`, `n_groups`, `warmup_days` (additive, validated at freeze). Produce one immutable evidence artifact per candidate (per-date IC/RankIC, ICIR, positive rate, coverage, monthly robustness, group/long-short, cost/turnover diagnostics) bound to `evidence_artifact_id` on the candidate attempt. Terminal failure → `status='failed'` + reason, never a zero score.

**Wave 3** *(blocked on 47-02)*
- **47-03 — Admission policy exposure + candidate-ledger linkage + no-edit hardening.** Wire `run_admission` to candidate identities (via the exploratory revision), record `rejected`/`admitted`/`failed` + gate trail onto the candidate attempt. Add an `ADMISSION_POLICY_FINGERPRINT` (thresholds + version + gate order) frozen into the manifest and verified fail-closed at scoring time. Confirm factory/Agent paths never pass thresholds/gate-order inputs.

**Wave 4** *(blocked on 47-02 + 47-03)*
- **47-04 — Deterministic selection + exactly-once selection-OOS.** Add `selection_oos` to `CANDIDATE_STATUSES` (rebuild pattern). Add `research_alpha_fold_evidence` (candidate-keyed, INSERT-only). Deterministic winner selection by frozen objective + tie-break. Evaluate the winner on `plan.oos_fold` exactly once (confirm-objective-before-slot, mirroring `walkforward.py:312-317`). Idempotent reconnect/retry returns the existing OOS row. Status/label discipline: `selection_oos`, never `final_blind`.

## Risks

- **Transient-revision catalog leakage (47-01 option A).** An exploratory revision must be invisible to the formal catalog until Phase 49 promotion. Mitigate with an explicit `provenance.kind="alpha_exploratory"` flag and ensure `discover_similar`/admission treat it as a candidate, not an admitted factor. If this proves awkward, fall back to option B (candidate-expression compute entry point).
- **Manifest extension invalidates frozen snapshots.** Adding required manifest fields (`oos_size`, `horizon`, costs) changes `validate_manifest` (`run_contract.py:145-180`); existing Phase 45/46 fixtures and stored runs must be migrated or the new fields must be additive-with-defaults. Prefer additive validation (required only when a `scoring` stage is declared) to avoid invalidating completed Phase 45/46 runs.
- **`selection_oos` rebuild risk.** The candidate-status rebuild (`migrations.py:2128-2184`) must re-create every dependent trigger (`research_alpha_candidates_no_update/no_delete`, the same-run artifact guard, the lineage same-run trigger). The Phase 46 rebuild already proved this path; replicate it exactly.
- **Cost diagnostic vs. real backtest divergence.** A turnover×rate diagnostic is an approximation of the strategy backtest's cost model; document it as a diagnostic, not a P&L claim, so AF-REQ-07's "cost/turnover diagnostics" is not mistaken for execution P&L (consistent with the no-execution boundary, `REQUIREMENTS.md:69`).
- **Per-fold evaluation cost.** Evaluating every candidate across N selection folds × M candidates could be expensive. The chain's `PanelCache` (`signal_chain.py:104`, max 4, TTL 180s) and the fold-membership union read (`walkforward.py:689-699`) mitigate, but budgets (AF-REQ-23) must account for fold×candidate fan-out. The frozen `budgets` group already exists; fold evaluation is bounded by the frozen `n_folds`.

## Confidence

- **HIGH:** chain/evaluation/admission/walkforward reuse (all verified against current source); the typed-fold-evidence verdict (wf_folds identity mismatch is structural); failure-as-reason (already implemented); exactly-once pattern (proven by `evaluate_best_params`).
- **MEDIUM:** candidate→revision binding choice (option A vs B needs a prototype against `FactorRegistry.create_revision`); cost/turnover diagnostic shape (approximation must not overstate); manifest extension migration safety.
- **Valid until:** 2026-09-07 for the chain/evaluation/admission/walkforward/repository/migration contracts; re-check if the candidate ledger schema, `CANDIDATE_STATUSES`, or the manifest `fold_geometry`/`policy` groups change before planning.
