# Phase 31 Plan Check — 竞价复盘 (REV-01..05)

**Checker:** PlanCheckerP31
**Date:** 2026-08-06
**Plans checked:** 3 (31-01 / 31-02 / 31-03)
**Method:** Goal-backward verification — ROADMAP Phase 31 goal + success criteria + REQUIREMENTS.md REV-01..05 traced into each PLAN; all named anchors spot-checked at current HEAD (read-only, no source modified, Watchlist.tsx untouched).
**Gate type:** Revision Gate (bounded loop; this is pass 1).

---

## 1. Verdicts

| Plan | Verdict | Tasks | Files | Wave | Depends on |
|------|---------|-------|-------|------|------------|
| 31-01 | **PASS** (2 warnings, 2 notes) | 3 | 2 | 1 | — |
| 31-02 | **PASS** (1 warning, 1 note) | 3 | 5 | 2 | 31-01 |
| 31-03 | **PASS** (1 warning, 1 note) | 3 | 5 | 3 | 31-01, 31-02 |

**Overall: VERIFICATION PASSED — no blockers.** Phase goal (deterministic auction panel in recap stream + honest data_completeness/pre_eod + optional AI commentary + 15:40 default + REV-05 endpoint) is fully covered by executable tasks. 3 warnings to fix (recommended before execution, not strictly blocking); 5 notes.

---

## 2. Goal-Backward Trace

ROADMAP Phase 31 goal/success criteria → requirement → plan/task mapping:

| Success criterion / requirement | Plan | Tasks |
|---------------------------------|------|-------|
| Read-only `auction_recap.py`, 3 blocks from frozen assets, never `run_all_with_hits`; historical as_of = partition-existence gate (REV-01) | 31-01 | T1 (signature/injection + gates), T2 (Block 1), T3 (Block 3) |
| `data_completeness` enum + missing-block note; 09:30+ bar never labeled auction; `pre_eod`; 「确定性数据，非 AI 生成」 marker (REV-02) | 31-01 | T1 (enum/pre_eod/render), T2 (window predicate regression), T3 (pre-EOD change_pct notes) |
| Signal-quality block: strategies with actual preview rows only (族∩预览), EOD `change_pct` caliber join, n_missing, display_limit/degraded notes (REV-03) | 31-01 | T3 |
| Panel delta before `done`; same stream → SSE/archive/Feishu; optional AI commentary default OFF, slice-only citations + guardrail; `_build_user_prompt` backward compatible; default schedule 15:40 (REV-04) | 31-02 | T1 (event order + degradation + AI-failure), T2 (commentary/pref/PUT/guardrail/single-source), T3 (15:40 default + Review.tsx:105 + regression) |
| Standalone read-only `GET /api/market-recap/auction` (REV-05, P2) | 31-03 | T1 (endpoint + as_of validation + empty state + guest mask + main.py), T2 (POOL-03 guards), T3 (docs + full regression) |

All 5 REV requirements appear in plan `requirements` frontmatter (31-01: REV-01..03; 31-02: REV-04; 31-03: REV-05). No PROJECT.md requirement relevant to this phase is dropped (PROJECT.md lists only the REV-xx recap extension + zero-execution boundary, both honored).

## 3. Anchor Spot-Checks (all verified at current HEAD)

| Anchor | State |
|--------|-------|
| `market_recap.py` `_SYSTEM_PROMPT` :40, `_build_user_prompt(overview, news, focus)` :177, `recap_market_stream` :253, `recap_market_once` :327 | present |
| `recap_market_stream` event structure: meta → AI try/except (error+return) → `done` at **:324** (note: RESEARCH/31-02 cite :354 — stale by 30 lines, see W-3) | present |
| `preferences.py` `get_review_schedule` :433 (default literal + `.get("minute", 10)` fallback), `set_review_schedule` :446 (15:00 floor), `get_pipeline_schedule` :329, `get/set_review_push_channels` :460/:483 | present |
| `settings.py` `update_review_push` :1469 (no-job PUT template), `update_review_schedule` :1426 (job variant), GET /preferences :374-422 | present |
| `frontend/src/pages/Review.tsx:105` fallback literal `{ enabled: false, hour: 15, minute: 10 }` (single occurrence) | present |
| `api/auction_history.py` GET-only module + `reviewer_principal` guest gate :97 | present |
| `api/pool.py` `_AS_OF_RE` :24 + double as_of validation :101-105 | present |
| `main.py` import block :20-45; `app.include_router(market_recap.router)` at **:871** | present |
| `auction_validation.py` `_AUCTION_FAMILY_IDS` frozenset :46-49 (9 ids, no `strong_open`) | present, shipped Phase 29 |
| `auction_columns.py` `attach_auction_columns` :93, `attach_auction_columns_range(df, start, end, repo)` :174 | present |
| `premarket_snapshot.py` `load_premarket_snapshot(data_dir, as_of) -> dict|None` :83, `persist_premarket_snapshot` :48 | present |
| `screener.py` `ScreenerService` :230, `_load_enriched_for_date` :245, `_strategy_display_name` :205, `latest_date` :704, `run_all_with_hits` :723 | present |
| `repository.py` `get_enriched_range` :966, `get_instruments_asset` :1059 | present |
| `daily_pipeline.py` `REVIEW_JOB_ID` :760, `_run_scheduled_review` :763, `_stream_review_with_retry` :831, `_maybe_push_review` :891, `_register_review_job` :936, `_POOL_EOD_OFFSET_MIN=5` :964 | present |
| `market_time.py` `cn_now` :21 / `cn_today` :26 | present |
| `guest_masking.py` `MASKED_IDENTITY` :17, `mask_guest_hub` :31, `mask_guest_alert` :65 | present |
| Fixture templates: `test_attach_auction_columns_range.py` `repo_env`/`_write_auction_partition`/`_multi_day_panel`/`_auction_rows`/`_patch_probe`; `test_premarket_pool.py` `_FakeRepo`/`_fake_verdict`/`_write_premarket_preview` | present |
| `test_hhxg_market.py:158-180` existing 3-arg `_build_user_prompt` calls (backward-compat regression anchor) | present |
| New files (auction_recap.py, api/market_recap_auction.py, 4 test files) do NOT exist yet → created by plans | confirmed |
| Existing market_recap/review tests: **zero** for stream/schedule/push (only `_build_user_prompt` unit calls in test_hhxg_market.py) — RESEARCH's "零命中" claim slightly overstates (see N-1) | confirmed |

## 4. Structural Verification (gsd-tools `verify.plan-structure`)

All 3 plans: `valid: true`, 0 errors, 0 warnings, 3 tasks each; every task has Files/Action/Verify/Done; frontmatter complete (phase/plan/type/wave/depends_on/files_modified/autonomous/requirements/user_setup/estimate/must_haves). Tracer-first decomposition is genuinely vertical (T1 = end-to-end slice with honest empty path, T2/T3 = block expansions); each task ends with atomic commit; verify commands match created test files exactly.

**Dependency graph:** 31-01 (w1, deps ∅) → 31-02 (w2, deps [31-01]) → 31-03 (w3, deps [31-01, 31-02]). Acyclic, wave = max(deps)+1, no forward references (31-01/31-02 mention 31-03 only as downstream consumer). Cross-plan data contract (panel dict `{as_of, data_completeness, blocks, built_at}`) is stable: 31-02 and 31-03 both consume the same read-only dict; no conflicting transforms; preferences file touched only by 31-02 (default change) while 31-01 only *reads* `get_pipeline_schedule` — no conflict.

**Scope sanity:** 3 tasks / 2-5 files per plan (targets 2-3 / 5-8). Smart-zone estimate-check verb is unavailable in this gsd-tools version (no `estimate-check` command; no `smart_zone_tokens` in config.json) — advisory only: 31-01 ≈ 50k tokens, 31-02 ≈ 48k, 31-03 ≈ 44k, all `confidence: low` (uncalibrated); task/file thresholds comfortably pass, no scope blocker.

## 5. Hidden-Blocker Sweep (context item 2d)

| Check | Result |
|-------|--------|
| Watchlist.tsx off-limits; only Review.tsx:105 literal allowed | ✅ No plan lists Watchlist.tsx in files_modified; sole frontend touch = 31-02 Review.tsx:105 (1 line, verified single occurrence) |
| strategy_cache / write_cache | ✅ Forbidden in all plans; 31-03 guard test 5 asserts absence in import surface and source |
| POOL-03 forbidden calls (run_all / run_preset / write_cache / persist_point_snapshot / save_report) | ✅ Forbidden in 31-01 objective + 31-03 guard tokens (adds save_report); allowed imports premarket_snapshot/screener/preferences deliberately re-tuned vs Phase 29 whitelist, with documented rationale |
| Import cycles (auction_recap ↔ auction_validation) | ✅ `auction_validation` imports only auction_columns/auction_probe/strategy.engine/tickflow.repository — cannot import auction_recap (new file); acyclic by construction |
| Schedule default 15:40 vs saved-pref retention | ✅ 31-02 T3 Test 2 locks `load().get("review_schedule", default)` semantics (saved 15:10 retained); actual code :438 confirms the semantic |
| Event order meta → AI delta → panel delta → done locked | ✅ 31-02 T1 Test 1 asserts exact sequence; actual code structure verified (panel built pre-meta per RESEARCH §2.2, yielded post-AI) |
| Test file names ↔ verify commands | ✅ 31-01→test_auction_recap.py; 31-02→test_market_recap_delta.py (+test_hhxg_market.py regression); 31-03→test_auction_recap_guard.py + test_auction_recap_endpoint.py (+ full suite) |
| R8: no panel fallback on AI failure | ✅ Kept as research decision (not a plan leak): 31-02 T1 Test 3 asserts error+return, no panel delta, no done; AI-failure path untouched |

## 6. Dimension Status

| Dimension | Status |
|-----------|--------|
| 1 Requirement Coverage | ✅ PASS |
| 2 Task Completeness | ✅ PASS (structure-validated) |
| 3 Dependency Correctness | ✅ PASS |
| 4 Key Links Planned | ✅ PASS (imports/calls/wiring explicit in actions) |
| 5 Scope Sanity | ✅ PASS (advisory estimates, tool unavailable) |
| 6 Verification Derivation | ✅ PASS (truths are contract/user-observable: event order, honest empty, default 15:40, read-only) |
| 7 Context Compliance | ⏭ SKIPPED (no CONTEXT.md) |
| 7b Scope Reduction | ✅ PASS — no v1/static/placeholder reduction language; R8 (no panel fallback) is research-sanctioned; R12 guest DTO is **locked** in 31-03 T1; REV-05 (P2) fully included, not deferred |
| 7c Architectural Tier | ⏭ SKIPPED (no responsibility map in RESEARCH) |
| 8 Nyquist | ⏭ SKIPPED (RESEARCH has no "Validation Architecture" section; note: no VALIDATION.md exists either — see N-4) |
| 9 Cross-Plan Data Contracts | ✅ PASS (1 warning: import-form mismatch, W-1) |
| 10 CLAUDE.md Compliance | ⏭ SKIPPED (no CLAUDE.md) |
| 11 Research Resolution | ✅ PASS (no Open Questions section; §9 risks R1-R15 all dispositioned; R13 INFERENCE has handling rule) |
| 12 Pattern Compliance | ✅ PASS (all 12 files mapped to analogs; plans reference analogs in read_first/action) |
| Verify Command Sanity | ✅ PASS (pytest only; no `^`-anchored grep on tree output, no `2>/dev/null || echo` feeding comparisons, no hard-coded counts) |
| Numeric/Factual Claim Authority | ✅ PASS with W-3 (line-anchor drift; live measurement used as ground truth) |

---

## 7. Issues

### Blockers

None.

### Warnings (should fix before execution)

**W-1 [cross-plan contract / dependency_correctness] — 31-01 prescribed import form will fail 31-03's own guard**
- Plan: 31-01 Task 1 action A.3 prescribes `from app.services import preferences` (lazy, inside `build_auction_recap`); 31-03 Task 2 step 6 mirrors `test_auction_validation._imported_module_names`, which appends **only `node.module`** (verified :71-80) — for `from app.services import preferences` that yields `"app.services"`, which matches neither `_IMPORT_EXACT` nor any of the 11 `_IMPORT_PREFIXES` (including `app.services.preferences`). → `test_recap_import_whitelist` fails deterministically in Wave 3.
- Fix: change 31-01 action A.3 to `from app.services.preferences import get_pipeline_schedule` (module name `app.services.preferences` ∈ whitelist) — or add `"app.services"` as a whitelist prefix (weaker; not recommended). Align the two plans now so Wave 3 does not burn a guard-failure cycle (31-03 T2 step 8's "fix the module" path exists, but the plans should agree up front).

**W-2 [task_completeness / executability] — `pre_eod` comparison is tz-aware vs naive → TypeError on production path**
- Plan: 31-01 Task 1 action A.3 `pre_eod = (now.time() < time(sched["hour"], sched["minute"]))` with `now = now or cn_now()` (aware, CN_TZ). Comparing aware `time` to naive `time(15, 30)` raises `TypeError` in Python. Test 3 injects **naive** `now=datetime(FIXED_DATE, 15, 0)` so unit tests stay green; the 31-03 endpoint calls `build_auction_recap(repo, as_of, engine)` **without** `now` injection, so the today+missing-partition path would 500 until caught by endpoint Test 2.
- Fix: minutes arithmetic, matching the plan's own window-predicate idiom: `pre_eod = (now.hour * 60 + now.minute) < (sched["hour"] * 60 + sched["minute"])`. (Alternative: `now.replace(tzinfo=None)`.) Update the fixture note to say injected `now` is wall-clock.

**W-3 [numeric/factual authority] — stale line anchors for `recap_market_stream` (done at :324, not :354)**
- Plan: 31-02 Task 1 cites "yield done (:354)" / RESEARCH §1.1 "done(:354)" / PATTERNS ":285-354". Live measurement: meta :297-303, AI try/except :305-320, `done` at **:324**, `recap_market_once` :327. Structural instructions are correct and unambiguous ("在 AI try/except 之后、yield done 之前"), so execution will not misbehave — but anchors should be refreshed so executors don't trust stale numbers.
- Fix: update the three anchors to :324 (and meta/try ranges to :297-303/:305-320) in 31-02 and RESEARCH/PATTERNS.

### Notes

**N-1 [factual] — RESEARCH/PATTERNS "no market_recap tests exist" is overstated.** `test_hhxg_market.py:158-180` exercises `market_recap._build_user_prompt` (3-arg). The plans handle this *correctly* (31-02 T3 verify includes test_hhxg_market.py as the backward-compat regression anchor), so no plan defect — but the "grep 零命中" claim in RESEARCH §0/PATTERNS should be corrected to "no stream/schedule/push tests".

**N-2 [task_completeness] — 31-01 Task 2 Test 4 fixture composition risk.** The ratio sub-block calls `attach_auction_columns_range(panel, as_of, as_of, repo)` on the real function (verified :174), which reads the lake partition through `repo`; the plan's `_FakeRepo` (mirror of test_premarket_pool, which exposes `data_dir` but not `.store`) may not satisfy it → sub-block fail-closed → Test 4's ratio assertion could fail. Plan has the fallback note ("分母不可得 → 子块省略"), but pin the fixture path: either extend `_FakeRepo` with a minimal `.store` or drive the real `repo_env` + multi-day enriched parquet (mirroring test_attach_auction_columns_range's own pattern).

**N-3 [wording] — 31-01 Task 1 action A.1 self-contradictory parenthetical** "…`yield meta` 之前 (或 meta 之后 — 以 RESEARCH §2.2 为准: 面板构建在 meta 前)". Resolves to RESEARCH §2.2 (panel built before meta, meta yielded first) and matches 31-02 T1 Test 1's expected sequence — but delete the "或 meta 之后" clause to avoid executor ambiguity.

**N-4 [process] — No VALIDATION.md exists for Phase 31** (`has_verification: false`). Nyquist dimension is skipped by rule (RESEARCH has no "Validation Architecture" section), but if the workflow intends per-phase validation architecture, re-run `/gsd-plan-phase 31 --research` to regenerate with the section.

**N-5 [advisory] — Smart-zone estimate check not runnable here** (`estimate-check` verb absent from installed gsd-tools; no `smart_zone_tokens` in config.json). Estimates 50k/48k/44k tokens at low confidence are uncalibrated; task/file thresholds (3 tasks, ≤5 files per plan) pass comfortably, so no scope concern.

---

## 8. Structured Issues

```yaml
issues:
  - plan: "31-01"
    dimension: cross_plan_data_contracts
    severity: warning
    description: "Action A.3 prescribes `from app.services import preferences`; 31-03 guard's _imported_module_names appends only node.module ('app.services'), which fails the import whitelist. Guaranteed guard failure in Wave 3."
    task: 1
    fix_hint: "Use `from app.services.preferences import get_pipeline_schedule` in 31-01 and confirm the whitelist prefix app.services.preferences in 31-03."
  - plan: "31-01"
    dimension: task_completeness
    severity: warning
    description: "pre_eod comparison `now.time() < time(...)` compares tz-aware cn_now() time to naive time -> TypeError on production path; naive injected-now fixtures mask it in unit tests; 31-03 endpoint (no now injection) would 500 until its empty-state test catches it."
    task: 1
    fix_hint: "Use minutes arithmetic: (now.hour*60+now.minute) < (sched['hour']*60+sched['minute']), matching the plan's own window-predicate idiom."
  - plan: "31-02"
    dimension: numeric_factual_authority
    severity: warning
    description: "Stale anchors: done yield is at market_recap.py:324, not :354 (meta :297-303, AI try/except :305-320). RESEARCH §1.1 and PATTERNS share the drift. Structural insertion point is correct."
    task: 1
    fix_hint: "Refresh line anchors to :324 / :297-303 / :305-320 in 31-02, RESEARCH, PATTERNS."
  - plan: "31-01"
    dimension: task_completeness
    severity: info
    description: "Task 2 Test 4 ratio sub-block: attach_auction_columns_range needs repo.store access; _FakeRepo (data_dir only) may not compose -> pin fixture path or rely on fail-closed note."
    task: 2
    fix_hint: "Extend _FakeRepo with minimal .store or use real repo_env + multi-day enriched parquet (mirror test_attach_auction_columns_range)."
  - plan: "31-01"
    dimension: task_completeness
    severity: info
    description: "Action A.1 parenthetical '或 meta 之后' contradicts the operative RESEARCH §2.2 placement (panel built before meta)."
    task: 1
    fix_hint: "Remove the '或 meta 之后' clause; keep RESEARCH §2.2 placement."
  - plan: null
    dimension: research_resolution
    severity: info
    description: "RESEARCH §0 / PATTERNS claim zero market_recap/review tests; test_hhxg_market.py:158-180 does call _build_user_prompt. Plans already use it as the correct backward-compat regression anchor."
    fix_hint: "Correct the 'grep 零命中' claim to 'no stream/schedule/push tests'."
  - plan: null
    dimension: nyquist_compliance
    severity: info
    description: "No VALIDATION.md and no Validation Architecture section in RESEARCH.md; Nyquist dimension skipped by rule. Verify workflow intent."
    fix_hint: "If validation architecture is required, re-run /gsd-plan-phase 31 --research."
```

## 9. Recommendation

No blockers — plans are executable and goal-complete. Recommended before execution (W-1..W-3):
1. Align the `preferences` import form between 31-01 (action A.3) and 31-03 (guard whitelist) — W-1.
2. Replace the tz-aware/naive time comparison with minutes arithmetic — W-2.
3. Refresh `recap_market_stream` line anchors (:324) in 31-02/RESEARCH/PATTERNS — W-3.

Proceed with `/gsd-execute-phase 31` after addressing the three warnings (or during execution, since each is self-correcting via the plan's own test gates).
