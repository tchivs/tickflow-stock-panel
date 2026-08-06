# Phase 28 概念板块 PIT — Plan Check Report

**Checker:** PlanCheckerP28 (gsd-plan-checker)
**Date:** 2026-08-06
**Scope:** Goal-backward executability review of the 3 Phase 28 plans, before execution.
**Artifacts reviewed:** `.planning/ROADMAP.md` (Phase 28), `.planning/REQUIREMENTS.md` (CONCEPT-01..07), `.planning/phases/28-concept-pit/RESEARCH.md`, `.planning/phases/28-concept-pit/PATTERNS.md`, `28-01-PLAN.md`, `28-02-PLAN.md`, `28-03-PLAN.md`.
**Method:** Live repo anchor spot-checks (read-only; no builds/tests run). Every file/symbol/line the plans name was verified against the current codebase.

---

## Verdict

| Plan | Wave | Depends | Tasks | Files | Estimate (conf) | Verdict |
|------|------|---------|-------|-------|-----------------|---------|
| 28-01 | 1 | — | 3 | 6 | 68k tokens (low) | **EXECUTABLE** — 1 warning |
| 28-02 | 2 | 28-01 | 3 | 5 | 56k tokens (low) | **EXECUTABLE** — notes only |
| 28-03 | 2 | 28-01 | 2 | 4 | 52k tokens (low) | **EXECUTABLE** — 2 warnings |

**Overall: EXECUTABLE — 0 blockers, 3 warnings, 4 notes.**

No structural blocker prevents the phase goal from being achieved. The warnings are spec-hint corrections (missing import source declaration, stale line numbers, cross-plan rationale mismatch) — all recoverable during execution, but should be fixed by the planner before execution starts to avoid executor inference.

> **Estimate note (ADR-2629):** All three estimates carry `confidence: low` (<3 completed phases with actuals → uncalibrated for this project). Treat figures as directional only; none is a blocker. `gsd-tools query estimate-check` was not run (advisory only).

---

## Requirement Coverage (CONCEPT-01..07)

| Requirement | Delivered by | Covered? |
|-------------|--------------|----------|
| CONCEPT-01 (forward archive + EOD hook + honest skip) | 28-01 T1 (capture/write) + T2 (EOD hook) | ✅ |
| CONCEPT-02 (as_of read-side resolution in `_build_concept_map`) | 28-01 T2 | ✅ |
| CONCEPT-03 (three-state attribution machine) | 28-01 T2 | ✅ |
| CONCEPT-04 (frontend badge/tooltip, P2) | 28-02 T1 + T2 | ✅ |
| CONCEPT-05 (AST guard, `ext_history`-only write) | 28-01 T3 | ✅ |
| CONCEPT-06 (shared seam → overview + RPS) | 28-03 T1 (overview) + T2 (RPS + API) | ✅ |
| CONCEPT-07 (manifest provenance + effective date exposure) | 28-01 T1 (write) + 28-02 T1/T2 (display) + 28-03 T2 (re-verify) | ✅ |

- All 7 roadmap requirements map to at least one task; no requirement is dropped.
- No deferred-idea leakage: historical backfill (~247 pre-launch dates) and `ext_gn_ths` auto-refresh are correctly excluded.
- No scope reduction: plans deliver the full decision scope (industry `ext_hy_ths` archived alongside concept per OQ-2; manual-refresh design kept per OQ-1; OQ-3 drift probe included).

---

## Executability Spot-Checks (live repo anchors)

### New files (must be created by the plan — verified the plan says so)

| File | Plan creates it? |
|------|------------------|
| `backend/app/services/concept_history.py` | ✅ 28-01 T1 (does not exist today) |
| `backend/tests/test_concept_history.py` | ✅ 28-01 T1 (does not exist today) |
| `backend/scripts/probe_concept_drift.py` | ✅ 28-01 T3 (does not exist today) |
| `backend/tests/test_concept_seam.py` | ✅ 28-03 T1 (does not exist today) |
| `frontend/e2e/concept-pit.spec.ts` | ✅ 28-02 T2 (does not exist today) |

### Backend anchors (must already exist — all verified)

| Symbol | Actual location | Plan claim | Status |
|--------|-----------------|------------|--------|
| `_build_concept_map` | `pool_hub.py:60` | RESEARCH :38-56 / 28-01 read_first L38-56 | ⚠️ stale line, symbol ✅ |
| `_project_hub` | `pool_hub.py:83` (takes `data_dir` param) | RESEARCH :96-187 / 28-01 :96-99 | ⚠️ stale line, symbol ✅ |
| `build_pool_hub` (empty-cache dict :210) | `pool_hub.py:189` / empty dict at :211-212 | 28-01 :210 | ✅ |
| `build_pool_hub_snapshot` (empty-state dict) | `pool_hub.py:225` / empty dict at :250-254 | 28-01 :246 | ⚠️ stale line, dict ✅ |
| `pool_hub.py` imports `_dimension_field/_dimension_values/_read_ext_rows/_symbol_keys` from `market_overview_builder` | `pool_hub.py:36-39` | PATTERNS :20-24 | ✅ |
| `_pool_eod_persist` (`if results:` :1006, `persist_point_snapshot` :1008-1011) | `daily_pipeline.py:973` / `if results:` :1003 | RESEARCH/28-01 :1006 | ⚠️ stale line, hook point ✅ |
| `_dimension_rank` | `market_overview_builder.py:243` | 28-03 :243 | ✅ |
| **`_dimension_rank` call sites** | **`:503` (concept), `:504` (industry)** | **28-03 :505-506** | ❌ **line numbers wrong** |
| `_read_ext_rows` / `_dimension_field` / `_dimension_values` / `_symbol_keys` | `market_overview_builder.py:184/165/216/223` | RESEARCH :82-117/121-230 | ⚠️ stale lines, symbols ✅ |
| `build_market_overview` (`explicit_as_of` :372) | `market_overview_builder.py:355` | 28-03 :355-360 | ✅ |
| `_load_concept_map_df` (600s cache `_concept_map_cache/_concept_map_ts`) | `rps_rotation.py:54` / cache :70-73, :112-114 | 28-03 :54-109 | ✅ |
| `build_rps_rotation` | `rps_rotation.py:117` | 28-03 :111-200 | ✅ |
| `get_rotation` | `api/rps.py:19` | 28-03 :26-31 | ⚠️ stale line, route ✅ |
| `_build_overview` → `build_market_overview(..., as_of=as_of)` | `api/overview.py:350-362` | 28-03 :356-361 | ✅ |
| `market_recap` `build_market_overview(...)` | `market_recap.py:283` | RESEARCH :282-283 | ✅ |
| `_concept_preset` / `_industry_preset` (`enabled=False`, concepts.json URL) | `ext_presets.py:37/66` / enabled :61/:90 | RESEARCH :37-64/:66-92 | ✅ |
| `_flatten_concept_rows` / `_flatten_industry_rows` | `ext_presets.py:108/130` | RESEARCH :117-147 | ⚠️ stale line, symbols ✅ |
| `_fetch_json` (async — probe must NOT reuse) | `ext_presets.py:155` | RESEARCH :156-165 | ✅ |
| `ExtConfigStore.load_all()` / `.get()` / `ExtConfig.fields` / `PullConfig.last_run` | `ext_data.py:191/212/113/36` | 28-01 read_first | ✅ |
| `cast_df_to_schema` / `write_ext_parquet` | `ext_data.py:453/467` | RESEARCH :453-464/:466-497 | ✅ |
| `pool_snapshot._SNAPSHOT_ROOT`/`_DATE_RE`/`_SCHEMA_VERSION`/`_json_default` | `pool_snapshot.py:31/35/36/39` | 28-01 read_first :29-46 | ✅ |
| `probe_phase13.py` skeleton (docstring, sys.path, main()->int) | `probe_phase13.py:1-15` | 28-01 read_first :1-10 | ✅ |
| `test_pool_snapshot.py` hermetic conventions (`_AS_OF`, `_write_snapshot_payload`) | `test_pool_snapshot.py:1-63` | 28-01 read_first :1-63 | ✅ |
| `test_pool_eod_job._FakeRepo`/`_make_app_state` / result `{"as_of","strategies"}` | `test_pool_eod_job.py:51/73/124` | 28-01 Task 2 :24-133 | ✅ |
| `test_pool_hub` regression locks (`:469/:486/:377/:775/:841/:858/:884/:905/:913/:960`) | all present at claimed lines | 28-01 read_first | ✅ |
| `_write_concept_fixture` | `test_pool_hub.py:113` | RESEARCH :113-132 | ✅ |

### Frontend anchors

| Anchor | Actual location | Plan claim | Status |
|--------|-----------------|------------|--------|
| `PoolHubResponse.concept_attribution?: string` | `api.ts:765` (interface :752-766) | 28-02 :752-766 / :764-766 | ✅ |
| `AuctionColumnStatusBadge` export | `StockListTable.tsx:107` | 28-02 :102-160 | ✅ |
| `ConceptChips` (render site) | `StockListTable.tsx:49` / rendered :373 | 28-02 :49-56/:373 | ✅ |
| `AlertTriangle` / `CheckCircle2` already imported | `StockListTable.tsx:2` | 28-02 (assertion) | ✅ |
| `AuctionColumnStatusBadge` render site in detail header | `PoolHubPage.tsx:~331-336` (`{data?.auction_columns && ...}`) | 28-02 :328-333 | ✅ |
| `PoolHubPage` history fetch → `api.poolHistory(selectedDate)` | `PoolHubPage.tsx:38-41` | 28-02 (badge data source) | ✅ |
| `DateNavigator` `<select aria-label="选择日期">` | `DateNavigator.tsx:61-62` | 28-02 e2e combobox selector | ✅ |
| `fmtDate` | `format.ts:35` | 28-02 read_first | ✅ (unused in badge, see N-3) |
| `installShell` / `DESKTOP_PROJECT` / `json` / `unhandled` / `localTodayISO` / desktop-skip | `premarket-pool.spec.ts:4/19/101-133` | 28-02 Task 2 (copy source) | ✅ (see N-1) |
| `Watchlist.tsx` | exists at `frontend/src/pages/Watchlist.tsx` | **off-limits** — absent from all `files_modified` | ✅ not touched |

### Runtime environment

- `backend/.venv` present; `pytest 9.0.3`, `polars 1.40.1`, `httpx 0.28.1` importable ✅
- `frontend` `npm run build` = `tsc -b && vite build`; `@playwright/test 1.61.1`; `playwright`/`tsc`/`vite` binaries present; `lucide-react ^0.439.0` (has `AlertTriangle`/`CheckCircle2`) ✅
- No `CLAUDE.md` / `.claude/skills` / `.agents/skills` in repo root → Dimension 10 (CLAUDE.md compliance) **SKIPPED**.

---

## Hidden-blocker sweep (assignment item 2d)

| Check | Result |
|-------|--------|
| Plan names a test file that doesn't exist AND doesn't say it creates it | ✅ none — `test_concept_history.py`, `test_concept_seam.py`, `concept-pit.spec.ts` all explicitly created by their plans; `test_pool_eod_job.py`/`test_pool_snapshot.py`/`test_pool_hub.py`/`test_guest_masking.py` all exist |
| Plan touches `Watchlist.tsx` | ✅ none — off-limits in all three plans; e2e never `goto('/watchlist')` |
| Plan implies writing `strategy_cache` | ✅ none — CONCEPT-05 E3 guard (no strategy_cache import in concept_history) + `_pool_eod_persist` hook only *reads* ext snapshots; `strategy_cache.write_cache` untouched (existing line) |
| POOL-03 guard violated | ✅ none — `pool_hub.py` stays zero-write (`test_build_pool_hub_has_no_write_path` :913 respected; plan explicitly forbids write-pattern literals in comments/strings), `api/pool.py` untouched (GET-only), `concept_history` write root AST-guarded to `ext_history` |
| Circular import risk | ✅ verified acyclic — `market_overview_builder` imports only `ext_data`/`screener`; `ext_data` does not import back; `concept_history` → `market_overview_builder` (module-level) + `market_overview_builder`/`rps_rotation` → `concept_history` (function-body local) is safe; the local-import rule in 28-03 is correct |

---

## Issues

### Blockers (must fix)

None.

### Warnings (should fix before execution)

**1. [task_completeness] 28-01 T1 — `_dimension_field` import source unspecified in `concept_history.py`**
- Action step 1 imports only `from app.services.ext_data import ExtConfigStore, cast_df_to_schema`, but action step 7 calls `_dimension_field(config, ...)` (defined in `market_overview_builder.py:165`). As specced the module would raise `NameError` at runtime on the capture path.
- Fix: explicitly add `from app.services.market_overview_builder import _dimension_field` (module-level) to the import list in 28-01 T1 action step 1. Verified acyclic (see hidden-blocker sweep). This also makes W-3's rationale true.

**2. [numeric_authority] 28-03 T1 — `_dimension_rank` call-site line numbers are wrong**
- Objective, `must_haves`, `read_first`, and action all state `:505-506` for the two `_dimension_rank` calls in `build_market_overview`. Live repo: `concept_rank` is at `:503`, `industry_rank` at `:504`; `:505` is blank, `:506` is `strong_diff_pct = ...`.
- Fix: correct to `:503-504` (or "the two `_dimension_rank(rows, repo, …)` call sites in `build_market_overview`"). Executors re-read the file, so this is a hint correction, not a structural one.

**3. [dependency_correctness] 28-03 — cycle rationale references a fact 28-01 does not establish**
- The 28-03 objective justifies the local-import rule with "`concept_history.py` 模块级 import 了 `market_overview_builder` (`_dimension_field` 等)" — but 28-01's specced module imports only `ext_data`. The rule itself is correct and safe either way, but the two plans disagree about the module's import surface.
- Fix: apply W-1 (28-01 explicitly imports `_dimension_field` from `market_overview_builder`), which makes 28-03's rationale accurate; otherwise reword 28-03's rationale.

### Notes (advisory)

**1. 28-02 T2 — `installShell` "含 … history … 默认路由" overstates the copy source**
`premarket-pool.spec.ts`'s `installShell` (L101-133) registers `/api/pool/dates`, `/api/pool/hub`, `/api/pool/premarket`, `/api/data/auction-probe`, `/api/watchlist` — but **not** `/api/pool/history`. The new spec defines its own defaults and the `as_of_snapshot` test registers `**/api/pool/history**` explicitly, so execution is unaffected; just add the history default when copying.

**2. All plans — RESEARCH line numbers are stale vs current code**
`_build_concept_map` at `pool_hub.py:60` (RESEARCH :38-56); `_project_hub` at `:83` (RESEARCH :96); `if results:` at `daily_pipeline.py:1003` (RESEARCH :1006); `_flatten_*` at `ext_presets.py:108/130` (RESEARCH :117-147). Plans copied these stale hints into `read_first`. Non-blocking (executors re-read files), but updating RESEARCH's §8 anchor table would improve accuracy.

**3. 28-03 T2 — "复用 28-01 `_write_snapshot` + `_write_partition_fixture`"**
`test_concept_seam.py` is a new module; cross-importing fixtures from `test_concept_history.py` is brittle (rootdir-conftest dependent). T1 already mandates self-built fixtures ("镜像 … 形"); T2's "复用" should mean the same. 28-01 T2 step 7 does define `_write_snapshot`/`_write_strategy_cache` in `test_concept_history.py`, so a mirror source exists.

**4. 28-02 T1 — `fmtDate` read_first reference unused**
The badge JSX renders `effectiveDate` directly; `fmtDate` (`format.ts:35`, exists) is not called. Harmless.

---

## Dimension Summary

| Dimension | Result |
|-----------|--------|
| 1. Requirement coverage (CONCEPT-01..07) | ✅ PASS — all 7 covered, no scope reduction |
| 2. Task completeness (files/action/verify/done per task) | ✅ PASS — every task has all four; one import-source omission (W-1) |
| 3. Dependency correctness | ✅ PASS — 28-01 wave1; 28-02/28-03 wave2 → 28-01; acyclic; no forward refs |
| 4. Key links planned | ✅ PASS — EOD hook→capture; pool_hub→read_partition; badge→attribution; overview/RPS→read_partition |
| 5. Scope sanity | ✅ PASS — 3/3/2 tasks, 6/5/4 files; estimates present but low-confidence (advisory) |
| 6. Verification derivation | ✅ PASS — truths user-observable (files written, attribution values, guards green) |
| 7. Context compliance | ✅ PASS — OQ-1 manual-refresh kept, OQ-2 concept+industry, OQ-3 probe; deferred items excluded |
| 7c. Architectural tier compliance | ✅ PASS — writes in backend service/job; frontend renders server-frozen attribution only |
| 8. Nyquist | ✅ PASS — every task has `<automated>` verify; no watch-mode, no MISSING, no 30s+ gates |
| 9. Cross-plan data contracts | ✅ PASS — `read_partition`/`concept_attribution` contracts consistent across 28-01→02→03; no conflicting transforms |
| 10. CLAUDE.md compliance | SKIPPED — no CLAUDE.md in repo |
| 11. Research resolution | ✅ PASS — RESEARCH.md `Ready for planning: yes`; OQ-1/2/3 resolved (probe deferred to operator-run script by design) |
| 12. Pattern compliance | ✅ PASS — analogs referenced correctly; phantom `test_premarket_snapshot.py` correctly avoided |
| Verify command format sanity | ✅ PASS — no `^`-anchored tree greps, no `2>/dev/null || echo` comparisons, no `|| true`; `grep -c` gates fail-closed on zero |

---

## Recommendation

All three plans are **EXECUTABLE** as-is, with 0 blockers. Before/at execution start, apply the three warning fixes (they are spec-hint corrections — no structural or dependency changes are required):

1. 28-01 T1: declare the `_dimension_field` import source in `concept_history.py` (module-level from `market_overview_builder`).
2. 28-03 T1: correct the `_dimension_rank` call-site line references to `:503-504`.
3. 28-03: align the cycle rationale with 28-01's import surface (resolved by fix 1).

Proceed to `/gsd-execute-phase 28` (wave 1: 28-01; wave 2: 28-02 + 28-03 in parallel).

---
*Plan-checked: 2026-08-06 — read-only review; no source/plan files modified; no builds/tests run; `Watchlist.tsx` untouched.*
