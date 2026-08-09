---
phase: 48-factor-research-agent
verified: 2026-08-09
status: passed
score: 100
behavior_unverified: []
overrides_applied: []
human_verification: []
---

# Phase 48 — FactorResearchAgent Two-Stage Workflow — Verification

**Verdict: PASS.** All six acceptance criteria (AF-REQ-11/12/13/14/21/26) are satisfied at
code level (file:line below) and the full verification batch is green (783 passed, zero
failures/skips/xfail).

## Verification batch (run 2026-08-09)

```
cd backend && .venv/bin/python -m pytest \
    tests/research/ tests/test_operational_migrations.py \
    tests/api/test_run_api.py tests/test_phase45_guard.py -x -q
→ 783 passed in 109.96s (0:01:49)
```

This matches the orchestrator regression claim (783 passed across research + migrations +
API + architectural guard). No failures, no skips, no xfail.

| Batch file | Role |
|------------|------|
| `tests/research/` | Phase 48 preflight/seam/stage1/stage2/fixture contracts + research regression |
| `tests/test_operational_migrations.py` | `research_alpha_analysis_attempts` + `research_alpha_proposals` tables (append-only triggers, CHECK constraints, `foreign_keys`, artifact same-run) |
| `tests/api/test_run_api.py` | Run-API authority/retry/idempotency contracts unaffected |
| `tests/test_phase45_guard.py` | Architectural boundary guards (no prohibited imports, no second DB, no watchlist import in phase modules, no SSE, no new router) |

Per-plan SUMMARY test totals cross-checked against live `pytest --co` collection (all green):

| File | SUMMARY claim | Collected | Match |
|------|---------------|-----------|-------|
| `test_preflight.py` | 17 | 17 | ✓ |
| `test_agent_provider.py` | 46 | 46 | ✓ |
| `test_agent_stage1.py` | 36 | 36 | ✓ |
| `test_agent_stage2.py` | 68 | 68 | ✓ |
| `test_agent_fixture.py` | 44 | 44 | ✓ |

Phase 48 new-test total = 17 + 46 + 36 + 68 + 44 = **211 tests**, all in `tests/research/`.

`len(MIGRATIONS) = 38` (37 after 48-01's analysis-attempts table, +1 from 48-02's proposals
table — additive; `PRAGMA user_version` advances by exactly one per table).
`tests/test_operational_migrations.py` = 23 passed.

## AF-REQ evidence table

### AF-REQ-11 — Preflight pure-function gate (fail-closed, zero provider on fail) — PASS

A pure, fail-closed gate over the frozen snapshot; `passed=False` means the caller MUST NOT
reach the provider seam. Zero provider calls on the failed-preflight path (the gate never
invokes a provider — it runs only read-only checks over the frozen snapshot).

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| `PreflightCheck` / `PreflightResult` frozen value objects | `backend/app/research/preflight.py:42-60` (`@dataclass(frozen=True, slots=True)`; `failed_checks` accessor `:59-60`) |
| Pure `preflight()` entry point | `preflight.py:291-335` — accepts `connection` as a forward hook then `del connection` (`:308`); docstring "Pure: performs no provider call, no write" (`:298-304`); `passed=False` short-circuits before any seam (`:332-334`) |
| 8 checks covering all 10 capabilities (folded) | `preflight.py:310-331` — `data_availability_freshness`, `measured_calendar`, `pit_universe_scope`, `required_fields_sample_length`, `dsl_grammar_compatibility`, `budgets`, `provider_availability`, `policy_mode` |
| Sub-reason discriminators for folded sub-items | `preflight.py:106-132` (`data_fingerprint`/`partition_fingerprint`/`measured_window`), `:173-200` (`required_fields`/`sample_length`) |
| Zero provider calls on fail | Structurally guaranteed: `preflight()` calls only `_check_*` read-only fns; no `generate_text`/seam reference anywhere in the module (verified by `read`) |
| Fail-closed unexpected-exception → fail | `preflight.py:280-288` `_run_check` converts any exception into a bounded failed reason |
| Provider-availability gate (D-48-04 fixture) | `preflight.py:251-266` `_check_provider_availability` — passes only on real provider OR explicit fixture selector |

### AF-REQ-14 — AnalysisRecord + ProviderFailure taxonomy + AgentProviderSeam (no-fallback) — PASS

The seam is the only path from the deterministic pipeline to the provider: bounded
retry/backoff, cooperative cancellation, checksum-by-default, one append-only
`AnalysisRecord` row per attempt, and NO `except` branch that returns a synthesized payload.

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| `ProviderFailure` taxonomy (9 classes) | `backend/app/research/agent_provider.py:28-38` `FAILURE_CLASSES` (malformed_json/schema_violation/parse_failure/timeout/rate_limited/unavailable/refused/partial/cancelled); `:41-51` `_FAILURE_PROPS` (transient/terminal matrix) |
| Deterministic classifier (ordering honours type hierarchy) | `agent_provider.py:118-171` `classify_provider_failure` — `JSONDecodeError`→malformed_json (`:143`), `FactorDslError`→parse_failure (`:145-146`), schema-marker→schema_violation (`:147`), status/class heuristics (`:149-156`), `partial` only with `raw_response`+`partial_failure` marker (`:157-158`), unknown→`unavailable` transient (`:159-162`) |
| Bounded retry/backoff policy | `agent_provider.py:174-178` `retry_policy`; `:87` `_RETRY_TRANSIENT` (max_retries=3, base 1.0, factor 2.0, cap 30.0); `:53` `_RETRYABLE_CLASSES` = {timeout, rate_limited, unavailable} |
| `AgentProviderSeam.request` (only transport) | `agent_provider.py:255-392` |
| No-fallback (only success path is a real response) | `agent_provider.py:346` every exhausted-retry raises `ProviderCallError`; `:348-392` success path is the ONLY return; cancel → cancelled row + raise (`:295-319`) |
| Bounded retry loop with jittered backoff | `agent_provider.py:281-345` (attempt counter, `min(cap, base*factor**(n-1)) * (0.5+rand)` `:340-343`, `await sleep` `:344`) |
| Cooperative cancellation before retry | `agent_provider.py:294-319` |
| Transport outcome always `proposed` (Stage service sets terminal) | `agent_provider.py:377-382` |
| `AnalysisAttempt` value object (checksum-by-default) | `agent_provider.py:210-220` (raw, ordinal, response_sha256, response_byte_size); `:350-360` raw artifact retain hook |
| Append-only ledger table + CHECK + artifact same-run | `backend/app/operational/migrations.py:2305-2350` — `research_alpha_analysis_attempts`; `research_alpha_analysis_no_update`/`_no_delete` triggers (`:2337-2342`); `research_alpha_analysis_artifact_same_run` (`:2343-2350`); `attempt_ordinal CHECK > 0` (`:2308`) |

### AF-REQ-12 — Stage 1 bounded request + strict schema + parse_factor confirmation + transient proposals — PASS

Bounded thesis → strict versioned schema (extra=forbid at every nesting level) → server
`parse_factor` confirmation (canonical form) → append-only transient proposal store
(isolated from the catalog). Partial labeling (R2); no fallback (SC4).

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| `StageOneRequest` bounded thesis + permitted grammar | `backend/app/research/agent_stage1.py:63-113`; `:42-44` bounds (`MAX_STAGE1_EXPRESSIONS=3`); `:51-55` closed allowlist sets |
| `decode_stage1_payload` strict (extra=forbid, every level) | `agent_stage1.py:204-236` — pure (no provider call/mutation); field-specific `ValueError`s at top (`:51` `_TOP_ALLOWED`) + per-hypothesis (`:52-54` `_HYPOTHESIS_ALLOWED`); `:149-201` `_decode_hypothesis` |
| Server `parse_factor` canonical confirmation | `agent_stage1.py:254-361` `confirm_stage1_hypotheses` — `:280` `parse_factor(hypothesis.expression).canonical_expression`; kept rows store canonical (`:317`), raw retained as provenance only (`:316`) |
| Transient exploratory store (catalog-isolated) | `migrations.py:2359-2391` — `research_alpha_proposals`; `stage CHECK = 'stage1'` (`:2362`); `research_alpha_proposals_no_update`/`_no_delete` triggers (`:2386-2391`); `status CHECK IN ('proposed','partial','dropped')` (`:2378`) |
| Partial labeling R2 (distinct flag on every row) | `agent_stage1.py:302-303` (`partial`/`partial_flag`), `:329`/`:351` (every row carries `partial=partial_flag`); `:355-361` `Stage1Confirmed` |
| `Stage1Service.run` no-fallback (SC4) | `agent_stage1.py:416-537` — provider exception propagates via seam with zero proposal rows (`:456-470`); decode failure → distinct failed row + raise (`:483-501`); all-dropped → permanent `parse_failure` + raise (`:512-530`) |
| Decode/all-dropped distinct `+1` failed attempt row | `agent_stage1.py:487-500`, `:514-527` (ordinal = transport+1, append-only audit trail) |

### AF-REQ-13 — Stage 2 read-only evidence + no-mutable-field schema + referential integrity — PASS

Frozen inputs + read-only server evidence; closed schema (`extra='forbid'` at every nesting
level) plus a second-layer mutable-field blacklist; every cited evidence id resolves within
the run; advisory recommendation only (`propose_new_run` never spawns a run).

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| `Stage2Service.run` read-only over server evidence | `backend/app/research/agent_stage2.py:580-781` — no candidate/OOS/promotion write; advisory-only docstring (`:586-591`) |
| Read-only server-evidence projection | `agent_stage2.py:461-481` `assemble_server_evidence` (reads `list_candidates` + `list_alpha_fold_evidence` + `list_admission_verdicts_for_run`); `:162-174` `ServerEvidence`; `:177-214` frozen `StageTwoRequest` |
| Strict decode (extra=forbid, every level) | `agent_stage2.py:354-389` `decode_stage2_payload` — pure; allowlists `:85-90` (top/caveat/ref/recommendation); `_decode_caveat` `:257-294`, `_decode_recommendation` `:297-351` |
| No-mutable-field second-layer blacklist (7 tokens × 3 locations) | `agent_stage2.py:73-83` `MUTABLE_FIELD_NAMES` = {expression, metric, threshold, oos, admission, score, override}; `:103-122` `_reject_mutable_fields` (recursive top/caveat/recommendation) |
| Referential integrity (OQ-2) | `agent_stage2.py:398-436` `ReferentialIntegrityError` + `verify_evidence_refs`; candidate→`candidate_exists_in_run`, evaluation→`fold_evidence_exists_in_run`, gate→`admission_verdict_exists_in_run` (verdict ROW bound via `candidate_trail.provenance.run_id`), artifact→`artifact_exists_in_run`; bounded `{kind,id,run_id}` detail |
| No-mutable + no-fallback in service | `agent_stage2.py:660-706` — decode failure → failed row + raise (`:663-681`); referential failure → failed row (`schema_violation`/`referential_integrity`) + raise (`:687-706`) |
| Terminal `validated` only after decode + referential pass | `agent_stage2.py:708-726` (parsed-output digest + `outcome='validated'`) |
| Advisory recommendation (propose_new_run never spawns) | `agent_stage2.py:590-591` docstring; no run-creation call in service (verified by `read`) |
| Stage-boundary checkpoint (terminal event + checkpoint, one tx) | `agent_stage2.py:728-774` `append_stage_boundary` (after_stage='stage2', `checkpoint_stage='stage2'`, attempt-token/version fence, `BEGIN IMMEDIATE` in `ResearchRepository.append_stage_boundary`) |

### AF-REQ-21 — Stage-boundary checkpoint + resume-from-checkpoint (Phase 45 cursor reuse) — PASS

The contiguous stage-boundary checkpoint (terminal event + checkpoint in one `BEGIN
IMMEDIATE` transaction) plus resume-from-checkpoint reusing the Phase 45 cursor. No new
Agent/validation framework is introduced.

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| `resume_agent_stage` reads Phase 45 cursor | `backend/app/research/run_service.py:977-1028` — validates run `running` + current attempt token (`:1010-1018`); reads `get_latest_valid_checkpoint` stage discriminator (`:1019-1022`); maps none/early→`stage1`, `stage2_pending`→`stage2`, `stage2`→`complete` (`:1020-1028`) |
| Resume does NOT recompute committed evidence | `run_service.py:1000-1005` docstring — candidate/OOS/promotion are append-only idempotent |
| `append_stage_boundary` (Stage 2 terminal) | `run_service.py:690` `ResearchRunService.append_stage_boundary`; invoked `agent_stage2.py:750-774` (stage2 checkpoint, attempt-token fence) |
| `_append_stage1_boundary` (Stage 1 → stage2_pending) | `backend/app/research/agent_orchestrator.py:152-198` — `checkpoint_stage='stage2_pending'` (`:189`), `checkpoint_state_checksum` (`:167-177`), `BEGIN IMMEDIATE` via `service.append_stage_boundary` (`:178-198`) |
| State checksum recomputation | `agent_stage2.py:739-749`, `agent_orchestrator.py:167-177` (`checkpoint_state_checksum`) |
| Stale-token fence | `append_stage_boundary` `expected_attempt_token_digest` fence (`agent_stage2.py:771`, `agent_orchestrator.py:195`); `resume_agent_stage` rejects stale token (`run_service.py:1012-1018`) |
| No new Agent/validation framework | `run_service.py:985-988` docstring — "introduces NO new Agent/validation framework (ROADMAP.md:71)" |

### AF-REQ-26 — Offline fixture (explicit-declaration-only) + ExperienceLibrary — PASS

An offline fixture provider selectable ONLY by explicit declaration (never an implicit
fallback), producing a known full deterministic trace with zero network I/O; a read-only
`ExperienceLibrary` Protocol with a valid empty production default.

| Requirement | Evidence (file:line) |
|-------------|----------------------|
| `OfflineFixtureProvider` (peer provider, never I/O) | `backend/app/research/agent_fixture.py:140-184` — `generate_text_for` returns canned bytes, never network (`:165-184`); non-production constants `:30-32` (`offline_fixture`/`offline-fixture-v1`/`offline-v1`) |
| Explicit-declaration-only (never fallback, R3) | `agent_fixture.py:121-137` `is_fixture_explicitly_selected` — `True` only on truthy `fixture_mode` AND non-empty `fixture_name`; `False` for every missing/default/None/empty selector |
| Preflight provider-availability gate honors fixture | `preflight.py:251-266` `_check_provider_availability` (real provider OR explicit fixture) |
| `FixtureTrace` + known full deterministic trace | `agent_fixture.py:80-118` `default_fixture()` (canned momentum stage1 + clean advisory stage2, schema-valid under live DSL/schema versions) |
| `ExperienceLibrary` Protocol (read-only, never provider) | `backend/app/research/agent_experience.py:97-109` (`@runtime_checkable`, single `lookup()`) |
| `EmptyExperienceLibrary` (valid production default) | `agent_experience.py:112-123` (yields `()`; no provider call) |
| `OfflineFixtureExperienceLibrary` (fixture-seeded) | `agent_experience.py:126-159` (returns canned entry for matching `(factor_family, objective)`; nothing otherwise) |
| `derive_factor_family` (deterministic, declaration-stable) | `agent_experience.py:62-83` |
| E2E fixture run (resumable, deterministic, idempotent) | `agent_orchestrator.py:34-149` `run_fixture_mode` — preflight→stage1→stage2→AnalysisRecord; fail-closed fixture gate (`:61-64`); resume reads `resume_agent_stage` (`:82-87`); `stop_after_stage` resume path (`:121-123`) |
| Fixture wiring extracted to Phase 48 module | `agent_orchestrator.py:1-8` module docstring — lives OUTSIDE Phase 45 guard scope; `run_service.py:1030-1033` confirms the move |

## Explicit non-goals — PASS

| Non-goal | Evidence |
|----------|----------|
| No model-selected tools | Closed schema `extra='forbid'` at every nesting level (stage1 `agent_stage1.py:51-55`, stage2 `agent_stage2.py:85-90`); model only emits caveats/recommendation/hypotheses — no tool surface |
| No model-owned metrics/gates | `MUTABLE_FIELD_NAMES` (`agent_stage2.py:73-83`) blocks `expression`/`metric`/`threshold`/`oos`/`admission`/`score`/`override` (incl. aliased substrings) at top/caveat/recommendation; `disposition` is the only action and is advisory |
| No autonomous loops | Bounded retry `max_retries=3` (`agent_provider.py:87,337`); the `while True` exits via success-return or `raise ProviderCallError` — no unbounded re-prompt |
| No new evaluator | Stage 2 reads the Phase 47 evidence ledger read-only (`assemble_server_evidence`, `agent_stage2.py:461-481`); no new scoring/evaluation engine |
| No registry mutation | `research_alpha_proposals` is append-only (`migrations.py:2386-2391` no_update/no_delete triggers), separate from `factor_registry`; catalog lookup by `canonical_expression` returns nothing for a proposal |
| No promotion | Explicitly deferred to Phase 49 (AF-REQ-15); `propose_new_run` is advisory inline-summary only (`agent_stage2.py:590-591`) |
| No broker/order/portfolio/monitor | `run_service.py:10-11` module docstring asserts none imported; no such imports in any Phase 48 module (verified by `grep`) |
| No silent fallback | Every failure path raises `ProviderCallError` (`agent_provider.py:346`, `agent_stage1.py:501,528`, `agent_stage2.py:681,704`); fixture requires explicit declaration (`agent_fixture.py:121-137`, `agent_orchestrator.py:61-64`) |

## Phase 45 boundary guard — PASS

`tests/test_phase45_guard.py` is green (part of the 783 batch). The guard's module set
(`PHASE45_MODULES`, `test_phase45_guard.py:34-44`) includes `research/run_service.py` but
**not** any Phase 48 module (`agent_orchestrator.py`, `agent_provider.py`, `agent_stage1.py`,
`agent_stage2.py`, `agent_fixture.py`, `agent_experience.py`, `preflight.py`) — they live
outside the guard's scope.

The boundary-fix note is confirmed: 48-04 originally placed `run_fixture_mode` /
`_append_stage1_boundary` in `run_service.py` (a Phase 45 guard module); the `provider` token
in their lazy imports tripped the guard's `_PROHIBITED_IMPORT_TOKENS` (`test_phase45_guard.py:56`).
The fix extracted both to `backend/app/research/agent_orchestrator.py` (a Phase 48 module,
documented at `agent_orchestrator.py:1-8` as outside the guard scope). `run_service.py:1030-1033`
records the move. The only 48-04 surface remaining in `run_service.py` is `resume_agent_stage`
(`run_service.py:977-1028`) and `append_stage_boundary` (`run_service.py:690`), neither of which
imports a prohibited token at module level — hence the guard passes.

## Watchlist — PASS

`git status` shows no modification to `frontend/src/pages/Watchlist.tsx`. The only
watchlist-related working-tree change is an untracked visual-regression snapshot
(`frontend/visual-regression.spec.ts-snapshots/mobile-watchlist-mobile-chromium-320-linux.png`),
a pre-existing QA artifact unrelated to Phase 48. The constraint never to read
`Watchlist.tsx` was honored.

## SUMMARY claim cross-checks

1. **Per-file test counts** — `test_preflight.py`=17, `test_agent_provider.py`=46,
   `test_agent_stage1.py`=36, `test_agent_stage2.py`=68, `test_agent_fixture.py`=44 (all
   collected via `pytest --co`; match every wave SUMMARY exactly). ✓
2. **`ProviderFailure` taxonomy = 9 classes** — `agent_provider.py:28-38` lists exactly
   malformed_json/schema_violation/parse_failure/timeout/rate_limited/unavailable/refused/
   partial/cancelled. ✓
3. **`MUTABLE_FIELD_NAMES` = 7 tokens** — `agent_stage2.py:73-83` lists
   expression/metric/threshold/oos/admission/score/override. ✓

## Verdict

**PASS — score 100.** All six AF-REQs verified at code level with file:line evidence; the
783-test batch is green; the Phase 45 boundary guard holds; no behavior is left unverified;
no human follow-up items.
