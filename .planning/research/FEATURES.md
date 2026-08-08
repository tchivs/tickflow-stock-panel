# Feature Landscape: v3.0 Alpha Factory + FactorResearchAgent

**Domain:** Replayable automatic factor mining and two-stage factor research for an A-share quantitative research workbench  
**Milestone:** v3.0 (expected roadmap phases 45 onward)  
**Researched:** 2026-08-08  
**Scope confidence:** HIGH for current AthenaQuant contracts; MEDIUM for patterns synthesized from local AlphaMaster/PA_Agent analyses; LOW for general web corroboration (web results were used only as a sanity check).

## Scope and product boundary

v3.0 should turn the existing governed factor workflow into a replayable **Alpha Factory** and add a two-stage **FactorResearchAgent** without weakening the existing research boundaries. The factory searches only a deterministic, seeded grammar/evolution space and emits restricted factor expressions. The Agent proposes and explains research candidates, then synthesizes measured evidence; it does not become the owner of factor computation, admission policy, OOS reservation, or trading execution.

The current stack already supplies the hard boundaries that v3.0 should consume rather than replace:

- `backend/app/research/factor_dsl.py`: `DSL_VERSION`, `ALLOWED_FIELDS`, `DENIED_FIELDS`, parser/compiler, declared partition semantics, and no source-text escape hatch.
- `backend/app/research/factor_registry.py`: immutable `FactorRevision`, canonical expression/signature metadata, revisions, and deterministic `discover_similar` results.
- `backend/app/research/signal_chain.py`: `FactorSignalChain.compute()` as the single compile-to-compute path, governed panel loading, PIT universe resolution, warmup/missing-data handling, and panel/universe fingerprints.
- `backend/app/research/evaluation.py`: fully resolved evaluation configuration and retention-ready evidence (`IC`, `RankIC`, `ICIR`, monthly robustness, coverage, group and long-short evidence, input manifest, and artifacts).
- `backend/app/research/admission.py`: ordered deterministic gates (`no_lookahead`, `coverage`, `no_label_leakage`, `similarity_dedup`, `train_ic`, `val_ic`) with append-only admission or rejection verdicts.
- `backend/app/research/catalog.py`: immutable experiment/evidence snapshots, explicit retention, comparison candidates, and summary-only admitted catalog entries.
- `backend/app/research/hypotheses.py`: a proposal-only, parser-confirmed hypothesis draft and explicit `reviewed_draft` transition; the configured provider has no registry/evaluator/filesystem authority.
- `backend/app/api/research.py` and `frontend/src/pages/backtest/FactorBacktest.tsx`: the observable baseline of validate → save revision → optional hypothesis review → evaluate → retain, with `ResearchLibrary.tsx` showing revision/history/evidence state.
- `backend/app/backtest/walkforward.py` and its Phase 13 migration: measured-calendar rolling folds, a structurally reserved OOS fold, and exactly-once OOS evidence. A walk-forward selection OOS is still selection evidence, not a final blind holdout.

Local analysis supports the same direction. AlphaMaster's restricted token/grammar generation, bounded candidate scoring, diversity pressure, checkpoints, and shared execution path are reusable patterns, but its own analysis warns that heuristics are not statistical guarantees, that one-file walk-forward OOS is not final blind evidence, and that its manifest is incomplete (`../docs/aaa/alphamaster/DEEP-ANALYSIS.md`). PA_Agent's preflight → structured stage 1 → validation → stage 2 → validation → persisted record flow is reusable as an architectural pattern only; its AGPL license, Price Action assumptions, crypto-specific risk rules, and paper execution are not product code or domain defaults (`../docs/aaa/pa-agent/DEEP-ANALYSIS.md`). The cross-project synthesis reinforces data contracts, replayable tool envelopes, fail-closed gates, visible evidence/failure state, and read-only or paper-only high-risk boundaries (`../docs/aaa/10-SYNTHESIS.md`).

## Table stakes

Missing any of these makes the Alpha Factory or Agent unsuitable for controlled research. Complexity is an implementation estimate for v3.0, not a claim that the current code already provides the feature.

| REQ-ID | Feature | Observable behavior / acceptance signal | Complexity | Dependencies and grounding |
|---|---|---|---|---|
| AF-REQ-01 | **Immutable factory run specification** | Before generation starts, the user can inspect a frozen run record containing DSL/grammar version, ordered field/operator/function vocabulary, seed, maximum expression length/depth, candidate budget, objective weights, universe, measured date range, fold geometry, cost policy, and code/data manifest. Editing the form after start creates a new run rather than mutating the old one. | High | Depends on `FactorRevision` provenance, `ResolvedEvaluationConfig`, artifact/catalog persistence, and `walkforward.py` geometry. |
| AF-REQ-02 | **Deterministic seeded grammar/evolution search** | Given the same frozen run specification, seed, and governed input manifest, a replay produces the same candidate canonical expressions and candidate IDs/hashes in the same order. The default implementation is seeded grammar/evolution search; no PyTorch or RL dependency is required. | High | `factor_dsl.py` parser/canonicalization; AlphaMaster grammar/constrained-sampler pattern is reusable, but not its neural/RL dependency. |
| AF-REQ-03 | **Restricted candidate generation** | Every generated expression is parsed before evaluation. Unsupported fields/functions/operators, invalid arity/partition semantics, excessive windows/depth, non-finite literals, and malformed expressions become explicit `invalid` candidate records with diagnostics; no arbitrary Python, imports, source text, or executable fallback can enter the factory. | Medium | Reuse `parse_factor`, `FactorDslError`, `ALLOWED_FIELDS`, `DENIED_FIELDS`, and `DSL_VERSION`; mirrors current `/api/research/dsl/validate`. |
| AF-REQ-04 | **Candidate ledger, not top-K-only output** | The run records every attempted candidate, including invalid, duplicate, low-coverage, leakage, failed-evaluation, rejected, and admitted outcomes. Each record includes candidate expression/signatures, parent/mutation lineage, seed/step, status, reason, and links to evaluation/gate evidence. A user can answer “why was this candidate discarded?” without rerunning the search. | High | Requires append-only SQLite operational state and catalog/artifact links; extends `admission.py`'s persisted rejection trail rather than replacing it. |
| AF-REQ-05 | **One governed signal path** | Factory scoring, Agent-requested evaluation, admission, composite use, walk-forward folds, and any later as-of signal all call `FactorSignalChain.compute()` for factor values. A run exposes the revision ID, panel fingerprint, resolved-universe fingerprint, source fields, warmup, and missing-data policy it used. | High | Directly grounded in `FactorSignalChain.compute()` and its “single compile-to-compute path” contract. |
| AF-REQ-06 | **Point-in-time A-share universe and calendar semantics** | A replay resolves membership as of each date, uses measured trading dates rather than synthetic weekdays, and displays the resolved symbol counts/fingerprint and date coverage. Suspended/missing/non-finite observations follow the declared policy; silently substituting the full lake or current constituents is a run failure. | High | `signal_chain.py`, `universe.py`, `walkforward.py`; protects against survivor/look-ahead bias. |
| AF-REQ-07 | **Bounded evaluation evidence** | For every evaluated candidate, the user can inspect the resolved config and immutable evidence: per-date IC/RankIC, summaries/observations, ICIR, positive rate, coverage, monthly robustness, group statistics/NAV, long-short statistics/NAV, fees/slippage, and diagnostics. Evaluation failure is a terminal state with a reason, not a zero score. | High | Reuse `FactorEvaluationService.evaluate()` and `FactorEvaluationResult`; UI shape exists in `FactorBacktest.tsx`'s `Evidence`. |
| AF-REQ-08 | **Deterministic admission gates** | Candidate status is produced by the existing ordered gate policy, with each gate's observed value, threshold, and pass/fail reason visible. The Agent and factory can request a gate run but cannot edit thresholds, reorder gates, or convert rejection to admission. Every rejection is retained. | Medium | `run_admission`, `ADMISSION_POLICY_VERSION`, fixed thresholds, and append-only verdicts in `admission.py`. |
| AF-REQ-09 | **Honest temporal separation** | Search/tuning never consumes the reserved OOS fold. The UI labels fold-level test results as selection evidence and labels the reserved OOS result separately; it never calls the walk-forward selection OOS a “blind final validation.” A final blind holdout, if configured, is a distinct data range unavailable to search, feature selection, threshold tuning, and Agent synthesis. | High | `walkforward.py` and migration constraints structurally exclude OOS from search; AlphaMaster analysis explicitly warns that same-file walk-forward OOS is not final blind evidence. |
| AF-REQ-10 | **Replayable artifact/provenance manifest** | A run can be replayed from stored identifiers/hashes for data files/partitions, universe resolution, factor revision/DSL version, grammar vocabulary, seed, configuration, code/build version, candidate ordering, model/provider metadata (if Agent used), and artifact checksums. Missing required manifest fields fail closed rather than being filled with “unknown.” | High | Extends `FactorEvidencePackage`, `input_manifest`, artifact descriptors, catalog snapshots, and local synthesis's replayable tool-envelope principle. |
| AF-REQ-11 | **Two-stage Agent with deterministic preflight** | Stage 0/preflight checks data availability/freshness, measured calendar, universe scope, required fields, sample length, DSL/grammar compatibility, budget, provider availability, and policy mode. A failed preflight returns machine-readable reasons and makes zero model calls. | Medium | PA_Agent pattern (`check_preflight_data()` described in `../docs/aaa/pa-agent/DEEP-ANALYSIS.md`); current `FactorHypothesisService` already rejects unavailable providers. |
| AF-REQ-12 | **Stage 1: structured candidate/hypothesis proposal** | Stage 1 consumes a user thesis and permitted DSL/grammar options, and returns schema-validated JSON containing hypothesis, canonical expression(s), explanation, assumptions, requested scope, and uncertainty. The response is parser-confirmed; it remains a transient proposal until an explicit review/promotion action. | Medium | Reuse `FactorHypothesisService.draft()`, `HypothesisDraft`, `_decode_provider_draft`, and `reviewed_draft`; no raw natural-language text may create a revision. |
| AF-REQ-13 | **Stage 2: evidence-aware research synthesis** | Stage 2 receives only frozen run inputs and measured candidate/evaluation/gate evidence. It returns schema-validated JSON with candidate references, evidence citations, observed metrics, rejection/gate reasons, caveats, and a bounded recommendation (`reject`, `needs_review`, or `eligible_for_explicit_review`). It cannot change expressions, metrics, thresholds, data windows, OOS state, or admission status. | High | Depends on AF-REQ-07/08/09/10 and PA_Agent's diagnosis-before-decision separation; model output is explanatory/proposal data only. |
| AF-REQ-14 | **Complete Agent trace and failure records** | For every Stage 1/2 call, the run stores prompt/template version, provider/model/version, request scope, raw-response checksum or bounded raw response, parsed output, validation errors/retries, cancellation, token/latency metadata, and links to the input run. Partial failures remain inspectable; provider failure is not silently replaced with a fake draft. | High | Extends current hypothesis provenance (`provider`, `model`, `model_version`, `prompt_template_version`, `draft_id`) using PA_Agent's persisted `AnalysisRecord` pattern. |
| AF-REQ-15 | **Explicit human review and promotion** | A researcher can compare proposal, expression, assumptions, evidence, gate trail, and provenance, then explicitly save a new immutable revision. Unreviewed Agent output is absent from the factor catalog and comparison candidates. Modified expression/explanation/provenance is rejected if it no longer matches the issued draft. | Medium | Current UI already requires “reviewed” before `/api/research/hypotheses/reviewed-factor`; current server `reviewed_draft` verifies exact match. |
| AF-REQ-16 | **Run lifecycle, retry, cancellation, and resume** | The workbench shows queued/running/completed/failed/cancelled states and progress by candidate/fold. Cancellation leaves a terminal, replayable partial ledger. A retry either resumes from a recorded deterministic checkpoint or creates a new run linked to its parent; it never overwrites an earlier run. | High | Needs operational SQLite job state and event/replay contract; local synthesis recommends explicit task state and replayable calls. |
| AF-REQ-17 | **Research-only delivery boundary** | The final action available from an Alpha Factory/Agent run is inspect, compare, retain research evidence, or explicitly promote a factor revision. There is no route from Agent output or admission success to a live broker order. UI copy and API responses state research-only status. | Low | Existing workbench copy (`PoolHubPage.tsx`) and local synthesis's read-only/paper-only default; preserves the milestone non-goal. |

## Differentiators

These features make v3.0 materially more useful than a batch formula generator while staying inside the governed stack. They should be scheduled only after the table stakes above are durable.

| REQ-ID | Feature | Observable behavior / acceptance signal | Complexity | Dependencies and rationale |
|---|---|---|---|---|
| AF-REQ-18 | **Lineage-aware evolution and replay UI** | A researcher can see parent → mutation/crossover → child lineage, canonical expression diffs, seed/step, and the exact reason a branch stopped. Selecting “replay this branch” reproduces only that branch under the same frozen inputs. | High | Depends on AF-REQ-02/04/10/16; adapts AlphaMaster's elite/restart lineage without inheriting its model. |
| AF-REQ-19 | **Diversity and redundancy frontier** | Search ranking shows objective score beside structural similarity, field/operator overlap, factor-output/IC-series correlation, and coverage. The researcher can inspect Pareto-like candidates rather than only the highest IC; candidates too similar to admitted factors are visibly penalized/rejected under fixed policy. | Medium | Reuses `FactorRegistry.discover_similar()` and admission IC-correlation gate; turns current explanatory similarity into search feedback without changing policy at runtime. |
| AF-REQ-20 | **A-share robustness/cost stress board** | For a candidate family, the workbench displays results across rebalance cadence, fees/slippage stress, calendar regimes, coverage bands, and symbol subsets, with the exact trial matrix recorded. Stress trials cannot tune or rewrite the primary admission thresholds. | High | Builds on `FactorEvaluationResult` group/long-short evidence, resolved configs, and governed data; helps expose high-turnover or narrow-universe illusions. |
| AF-REQ-21 | **Evidence-linked Agent challenge/review** | Stage 2 can identify a missing assumption, contradictory metric, gate failure, narrow coverage period, or likely redundancy and link each statement to a candidate/evaluation/gate/artifact ID. It may ask for a new explicitly scoped experiment but cannot launch an unbounded search or alter the frozen run. | High | Depends on AF-REQ-13/14 and catalog IDs. Uses PA_Agent's “diagnosis then decision” pattern, not a free-form debate swarm. |
| AF-REQ-22 | **Experiment templates and deterministic cloning** | Users can clone a completed run into a new immutable spec while changing exactly declared dimensions (for example, horizon or cost stress). The UI shows a field-level diff and retains parent/child links; unchanged inputs retain their hashes. | Medium | Requires AF-REQ-01/10 and existing revision/experiment history in `ResearchLibrary.tsx`. |
| AF-REQ-23 | **Budget-aware parallel evaluation** | The run enforces candidate/time/memory/evaluation budgets server-side, reports consumption, and prevents a retry or Agent loop from bypassing them. Parallel scheduling changes throughput only; candidate ordering and replay result remain deterministic. | High | Needs job state and deterministic scheduler contract; AlphaMaster's CPU observations suggest measuring this workload before adding GPU/ML infrastructure. |
| AF-REQ-24 | **Candidate-family and admitted-factor comparison** | The researcher can compare explicitly retained experiment snapshots and candidate families side by side, including configuration, evidence, provenance, gate status, and artifacts, without a hidden winner score. | Medium | Extends `ExperimentCatalog`, `/api/research/comparison`, `ResearchLibrary.tsx`, and `ExperimentComparison.tsx`, whose current copy already says comparison does not compute a winner. |
| AF-REQ-25 | **Visible data-quality and degradation banners** | The UI displays data date, provider/source, cache/degradation state, missing fields, membership coverage, and whether a result is exploratory, selection-OOS, or final-blind. A stale/degraded run cannot look equivalent to a clean completed run. | Medium | Directly follows `../docs/aaa/10-SYNTHESIS.md` quality-banner principle and current governed input manifests. |
| AF-REQ-26 | **Offline deterministic Agent fixture mode** | With no configured provider, users/tests can run a declared offline fixture that produces a known proposal and full validation trace; production paths never silently switch to it. The UI labels fixture output as non-production evidence. | Low | Current `OfflineFakeHypothesisGateway` is test-only and provider failures are availability boundaries; useful for replay/UI acceptance without weakening production semantics. |

## Anti-features (explicitly do not build in v3.0)

| Anti-feature | Why it is unsafe or out of scope | Required alternative / guard |
|---|---|---|
| **Arbitrary Python, imports, generated source, or unrestricted expression execution** | It defeats the restricted DSL's parser/compiler boundary, creates code-execution and reproducibility risk, and makes candidate provenance impossible to normalize. The existing advanced strategy sandbox is not permission to add arbitrary code to factor mining. | Generate only the versioned grammar/DSL AST; reject unknown tokens before any Polars expression is allocated (AF-REQ-03). |
| **PyTorch/RL/neural policy as the default search engine** | Adds an unnecessary dependency and nondeterministic training surface to a milestone whose default decision is deterministic seeded search. It would make replay and debugging harder before the grammar/evidence contract is proven. | Seeded grammar/evolution search with explicit budgets, checkpoints, and candidate ledger; reserve ML search for a separately approved milestone. |
| **Agent authority over deterministic gates or policy thresholds** | A model can explain weak evidence but cannot make look-ahead, coverage, leakage, similarity, train IC, val IC, PIT, or reserved-OOS failures disappear. | Program-owned `FactorSignalChain`, evaluation, walk-forward, and `run_admission`; Agent output is proposal/synthesis only (AF-REQ-08/13). |
| **Raw LLM text directly creating or changing a factor revision** | Free text can contain invalid DSL, hidden assumptions, prompt injection, or a changed expression that no longer matches the reviewed draft. | Schema validation → DSL parse/canonicalization → explicit human review → immutable registry revision (AF-REQ-12/15). |
| **Automatic live broker actions, order submission, or “signal implies execution”** | The milestone is a research workbench, not an execution system. Admission is not a risk approval, broker acknowledgement, or live-trading authorization. | Research-only result and explicit no-broker boundary (AF-REQ-17); any future paper/live path needs a separate scoped design. |
| **Calling walk-forward selection OOS a blind final OOS** | The selection OOS can still influence interpretation, promotion, or future choices. Mislabeling it inflates confidence and defeats honest statistical separation. | Reserve it structurally, label it `selection_oos`, evaluate once, and require a separately frozen final-blind holdout for any final claim (AF-REQ-09). |
| **Dropping rejected/invalid candidates or retaining only the champion** | Survivorship in the research log prevents audit, hides search breadth/multiple comparisons, and makes a replay claim unverifiable. | Append every candidate and rejection reason to the ledger (AF-REQ-04). |
| **Mutable factor definitions or in-place experiment updates** | Historical evidence would silently change when an expression, data scope, or policy is edited. | New immutable `FactorRevision`/run/snapshot with parent link; no overwrite (AF-REQ-01/10/22). |
| **Synthetic, current-constituent, or full-lake fallback when PIT data is missing** | It introduces survivor bias and makes an apparently successful run incomparable with prior runs. | Fail closed with resolved-universe and data-quality diagnostics (AF-REQ-06/11/25). |
| **Provider fallback that fabricates a draft or silently changes model semantics** | A provider outage must not create an untraceable candidate or mix evidence across models. | Return `HYPOTHESIS_PROVIDER_UNAVAILABLE`/Agent failure, or use an explicitly labeled offline fixture only (AF-REQ-14/26). |
| **Unbounded multi-agent swarm, self-modifying prompts, or autonomous research loops** | More roles do not make a factor valid; hidden state and repeated search multiply comparisons and make budget/OOS boundaries porous. | Two stages with narrow schemas, frozen inputs, bounded budgets, persisted trace, and explicit new-run requests (AF-REQ-13/16/23). |
| **Copying PA_Agent source or domain rules** | PA_Agent is AGPL-3.0-or-later and its Price Action/crypto rules are not the A-share factor domain; direct reuse conflicts with the current MIT backend declaration. | Absorb public architectural patterns only; implement AthenaQuant contracts independently (`../docs/aaa/pa-agent/QUICK-START.md`). |
| **Treating high IC or model confidence as a trading recommendation** | Cross-sectional metrics, Agent confidence, and admission status are research evidence, not execution authorization or guaranteed returns. | UI explicitly distinguishes metrics, gates, selection OOS, final-blind evidence, and research-only status. |

## Observable user workflows and REQ-ready behavior

### Workflow A — Seeded Alpha Factory run

1. The researcher chooses a governed A-share universe, measured date window, horizon/rebalance/cost policy, grammar vocabulary, candidate limit, fold geometry, and seed.
2. The server validates the specification and creates an immutable `AF-REQ-01` run before any candidate generation. The UI displays the run ID, DSL/grammar version, data/universe manifest, budget, and OOS reservation state.
3. The factory generates candidates deterministically. Each candidate is canonicalized or rejected before evaluation. The ledger records candidate order, lineage, seed/step, status, and diagnostics (`AF-REQ-02`–`AF-REQ-04`).
4. Valid candidates are evaluated through `FactorSignalChain.compute()` only. Search folds use PIT membership and measured dates; the reserved OOS fold is not touched (`AF-REQ-05`, `AF-REQ-06`, `AF-REQ-09`).
5. The factory records IC/RankIC/ICIR/coverage/robustness/cost evidence and executes fixed admission gates. The researcher can filter by admitted, rejected, invalid, failed, duplicate, and “not evaluated due to budget” (`AF-REQ-07`, `AF-REQ-08`).
6. The user selects a candidate for explicit review. Retention creates a catalog snapshot; it never mutates the source run or silently promotes a candidate (`AF-REQ-10`, `AF-REQ-15`).
7. Choosing “replay” with the same manifest and seed produces the same canonical candidate sequence, statuses, and checksums; a changed input creates a new run and visible diff (`AF-REQ-02`, `AF-REQ-22`).

**Measurable acceptance:** same spec/seed produces identical ordered candidate hashes; all attempted candidates have terminal or resumable ledger states; no search record references the reserved OOS fold; every retained candidate references a completed evidence package and gate verdict.

### Workflow B — FactorResearchAgent two-stage review

1. The researcher enters a thesis and permitted scope. Deterministic preflight checks provider availability, data freshness, required DSL fields, universe/calendar/sample sufficiency, and policy mode. On failure, the UI shows the reason and records zero provider calls (`AF-REQ-11`).
2. Stage 1 returns strict JSON proposals (expression, explanation, assumptions, scope, uncertainty). The server parses/canonicalizes the expression and presents it as a non-persistent draft with provider/model/template provenance. Invalid or malformed output is rejected; no fallback draft is invented (`AF-REQ-12`, `AF-REQ-14`).
3. The researcher edits only through an explicit review flow. Exact expression, explanation, and provenance binding are revalidated before creating an immutable revision (`AF-REQ-15`).
4. The server evaluates the revision and runs deterministic gates. Stage 2 receives frozen evidence and can summarize, identify contradictions, and request a bounded follow-up run, but cannot rewrite evidence or gate status (`AF-REQ-13`).
5. The UI shows each Stage 2 claim beside candidate/evaluation/gate/artifact IDs, plus data quality and OOS labels. The researcher may retain evidence or explicitly promote the reviewed revision; there is no “execute” button (`AF-REQ-17`, `AF-REQ-21`, `AF-REQ-25`).

**Measurable acceptance:** no model call occurs after failed preflight; all successful stages validate against a versioned schema; a model output cannot change a deterministic gate result; a modified draft/provenance is rejected; every Agent run has a replayable trace and terminal failure state.

### Workflow C — Reserved OOS and final evidence honesty

1. Before search, the system reserves a measured-calendar OOS interval and records its fold manifest.
2. Search and Agent synthesis use only non-reserved folds. Any request that includes `is_oos` in a search fold fails closed.
3. The reserved fold is evaluated once after candidate selection under the frozen candidate/config and receives an explicit `selection_oos` label. Reconnect/retry returns the existing evidence rather than scoring it again.
4. If a final blind claim is needed, the user must configure a separate holdout not present in any factory, Agent, feature-selection, or threshold-tuning input. The UI reports “not available” rather than inferring final validity from selection OOS.

**Measurable acceptance:** a run's search manifest excludes the reserved OOS fold; one immutable OOS evidence row is linked to the candidate; repeated run requests cannot create a second OOS attempt; UI labels selection OOS and final blind separately.

## Feature dependencies

```text
Frozen run spec + grammar/version + seed + data manifest
    -> deterministic candidate generation
    -> parse/canonicalize + candidate ledger/lineage
    -> PIT universe + measured calendar
    -> FactorSignalChain.compute (single factor-value path)
    -> fold evaluation/evidence + cost/stability stress
    -> deterministic admission gates
    -> catalog snapshot / explicit retention / comparison

Agent preflight
    -> Stage 1 structured proposal
    -> DSL parse + explicit human review
    -> immutable FactorRevision
    -> governed evaluation + admission + OOS boundaries
    -> Stage 2 evidence synthesis
    -> research-only decision / bounded follow-up run
```

The critical ordering is intentional: the Agent cannot bypass the DSL or registry; the factory cannot bypass the signal chain or admission; selection cannot consume reserved OOS; and no research result implies broker execution.

## MVP recommendation and 4–6 phase roadmap implications

Prioritize a five-phase vertical sequence (starting at Phase 45 as requested):

1. **Phase 45 — Frozen run contract and replay ledger** (High): define the immutable spec, manifest, seed/checkpoint, candidate identity/lineage, lifecycle, cancellation, and all-outcome ledger. This is the prerequisite for every later claim of replayability and prevents a UI-only search feature.
2. **Phase 46 — Deterministic Alpha Factory search** (High): implement restricted grammar/evolution generation, bounded scheduling, canonicalization, duplicate/diversity accounting, and candidate diagnostics. Keep generation deterministic and ML-free; do not wire Agent autonomy or OOS until the ledger is trustworthy.
3. **Phase 47 — Governed scoring, admission, and honest OOS** (High): connect candidates to the existing signal chain/evaluation/admission/catalog, enforce PIT and measured calendar, reserve and evaluate OOS exactly once, and expose evidence/gate trails. Add cost/coverage/stability stress only after the primary path is immutable.
4. **Phase 48 — FactorResearchAgent Stage 1 and explicit review** (Medium/High): turn the current proposal-only hypothesis flow into a run-bound structured proposal stage with deterministic preflight, schema/versioned provenance, parser confirmation, and explicit revision promotion. No Stage 2 should be allowed to imply execution.
5. **Phase 49 — Stage 2 evidence synthesis and workbench UX** (High): persist complete stage traces, evidence-linked bounded recommendations, replay/failure views, lineage explorer, comparison, degradation/OOS banners, and bounded follow-up run creation. Validate that model output cannot alter deterministic verdicts.
6. **Optional Phase 50 — Robustness/frontier and operational hardening** (Medium/High): add multi-objective candidate frontiers, cost/regime/symbol-subset stress, resumable parallelism, and a separate final-blind holdout contract if product users need stronger research claims. Keep live broker integration out of this milestone.

**MVP must include:** AF-REQ-01 through AF-REQ-17, with a narrow candidate grammar, one A-share universe, one measured-calendar fold policy, one deterministic seed path, and explicit review. **Defer:** broad grammar expansion, neural/RL search, multi-agent debate, live/paper execution, and a separate final-blind holdout until the immutable evidence and replay contracts have been exercised.

## Sources and confidence notes

### Current AthenaQuant evidence — HIGH confidence (observed in repository)

- `backend/app/research/factor_dsl.py` — `DSL_VERSION`, allowed/denied fields, parser/compiler and partition semantics.
- `backend/app/research/factor_registry.py` — `FactorRevision`, `FactorRegistry.create_factor`, `revise_factor`, `discover_similar`.
- `backend/app/research/signal_chain.py` — `FactorSignalChain.compute`, `SignalChainConfig`, PIT membership and fingerprints.
- `backend/app/research/evaluation.py` — `ResolvedEvaluationConfig`, `FactorEvaluationService.evaluate`, `FactorEvaluationResult`.
- `backend/app/research/admission.py` — fixed admission constants, `temporal_split`, `run_admission`, append-only gate trail.
- `backend/app/research/catalog.py` — `FactorEvidencePackage`, `ExperimentCatalog.record_factor_evaluation`, retention/comparison behavior.
- `backend/app/research/hypotheses.py` — `FactorHypothesisService`, `HypothesisDraft`, `reviewed_draft`, configured/offline gateway boundaries.
- `backend/app/api/research.py` — `/dsl/validate`, factor/revision, hypothesis draft/review, evaluate, retain, and comparison endpoints.
- `frontend/src/pages/backtest/FactorBacktest.tsx`, `ResearchLibrary.tsx`, `ExperimentComparison.tsx` — current user-visible validate/review/evaluate/retain/history/comparison workflow.
- `backend/app/backtest/walkforward.py`, `backend/app/backtest/optimizer.py`, `backend/app/operational/migrations.py` — measured-calendar fold geometry, reserved OOS exclusion, exactly-once/append-only persistence contracts.

### Local upstream analyses — MEDIUM confidence (static analyses, not source reuse)

- `../docs/aaa/alphamaster/DEEP-ANALYSIS.md` and `QUICK-START.md` — constrained formula generation, candidate scoring, factor diversity, checkpoints, shared execution, and explicit limitations around heuristics/manifests/OOS.
- `../docs/aaa/pa-agent/DEEP-ANALYSIS.md` and `QUICK-START.md` — two-stage orchestration, deterministic preflight, schema/semantic validation, persisted partial failures, and approval boundaries; AGPL/domain-specific portions excluded.
- `../docs/aaa/10-SYNTHESIS.md` — data-contract-first, replayable tool calls, visible quality/degradation state, bounded Agent roles, and research/paper-only safety posture.

### General web corroboration — LOW confidence

Search results on formulaic alpha mining and deterministic agent workflows were directionally consistent with bounded grammars, walk-forward caution, structured outputs, and replay/audit records, but were not used as authoritative requirements. The v3.0 feature decisions above are grounded in the current repository and the local analyses instead.
