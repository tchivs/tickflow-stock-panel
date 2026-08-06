---
phase: 28-concept-pit
verified: 2026-08-06T16:10:00Z
status: passed
score: 7/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Real EOD run against production data — let the 盘后 EOD job fire (or invoke `_pool_eod_persist` once) with a live `data/` dir containing a populated `ext_data/ext_gn_ths` snapshot; then verify `data/ext_history/gn_ths/date={as_of}/part.parquet` + `manifest.json` exist with real rows and the `ext_data/ext_gn_ths/part.parquet` current file is byte-identical before/after."
    expected: "Partition + manifest (source_url/fetched_at/captured_at/rows/schema_version/sha256/dimension_field) appear under ext_history; current ext snapshot untouched; pool snapshot/cache still written when capture fails."
    why_human: "Requires production data dir + real EOD timing; hermetic tests use fixture dirs and fake captures."
  - test: "Visual pass in real browser against real backend — open 股池页 (PoolHubPage) on today's view and on a historical date; confirm the concept attribution badge renders (current_snapshot warning on today / as_of_snapshot '概念按当日快照 · 概念数据生效日期' on a dated partition) and that guest session renders zero badge without errors."
    expected: "Badge visible per server-frozen attribution; as_of_snapshot shows effective date; guest view clean."
    why_human: "e2e covers mocked payloads in real Chromium; a real-backend visual pass confirms server↔client contract end-to-end."
---

# Phase 28: 概念板块 PIT (Concept PIT) — Verification Report

**Phase Goal:** Historical pool concept labels become as-of accurate — a forward daily concept archive (`data/ext_history/gn_ths/date={as_of}/`) captured at EOD, read-side as-of resolution in `_build_concept_map`, and a three-state `concept_attribution` (`as_of_snapshot`/`current_snapshot`/`unavailable`), eliminating the today's `current_snapshot`-only labeling; shared seam extends to overview/RPS.
**Verified:** 2026-08-06T16:10:00Z
**Status:** human_needed (2 deploy/visual items — all code-level must-haves VERIFIED)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1: EOD hook captures concept snapshot to `ext_history/gn_ths/date={as_of}/part.parquet` (atomic, strict date, never blocks pool snapshot); `ext_gn_ths` current file untouched | ✓ VERIFIED | `_pool_eod_persist` (daily_pipeline.py:1013-1019) calls `concept_history.capture(data_dir, str(as_of))` inside `if results:` after `persist_point_snapshot`, wrapped in try/except BLE001 + logger.warning. `capture()`/`_write_partition()` use temp+os.replace atomic write, `_DATE_RE.fullmatch` + `date.fromisoformat` double validation, `_HISTORY_ROOT=="ext_history"`, honest skip on empty/missing snapshot, idempotent per as_of, zero `.tmp` residue. `_current_rows` only reads `ext_data/{id}/part.parquet` (no writes to current ext — manual-refresh design kept). Tests: `test_capture_writes_partition_and_manifest`, `test_capture_rejects_bad_as_of`, `test_capture_idempotent_no_tmp_residue`, `test_capture_honest_skip`, `test_pool_eod_persist_calls_concept_capture`, `test_pool_eod_persist_capture_failure_does_not_block` |
| 2 | SC2: Historical pool view resolves concept membership at `as_of`; missing partition falls back to current ext with `current_snapshot` attribution (honest, never fabricated) | ✓ VERIFIED | `_build_concept_map(data_dir, as_of)` (pool_hub.py) as_of branch → `concept_history.read_partition(data_dir, "gn_ths", as_of)`; partition hit + non-empty rows → map built from partition rows (attribution `as_of_snapshot`); else fallback loop over current ext unchanged. `read_partition` uses partition-existence gate (`part_path.exists()` → None) — no parquet date-column comparison, no fabrication. No backfill code exists anywhere (forward-only; ~247 legacy dates necessarily read `current_snapshot`). Tests: `test_build_pool_hub_snapshot_as_of_partition_priority`, `test_read_partition_primitives` |
| 3 | SC3: Attribution is three-state and never mixed per-row; write path AST-guarded (only `ext_history/`) | ✓ VERIFIED | Three-state machine in `_build_concept_map`: as_of_snapshot (partition hit) / current_snapshot (no config OR rows present) / unavailable (config present but rows empty). `_project_hub` emits one top-level `concept_attribution` per projection — never per-row, never merged. AST guard `test_concept_history_ast_guard_writes_only_ext_history` asserts `_HISTORY_ROOT=="ext_history"` and all write-path functions reference it; `test_concept_history_no_execution_imports_no_strategy_cache` asserts zero execution-module imports + zero `strategy_cache`/`write_cache` tokens (grep count 0). `pool_hub.py` has zero write patterns (`test_build_pool_hub_has_no_write_path`); `api/pool.py` untouched in phase diff (0 files) and GET-only guards green |
| 4 | SC4a: Frontend shows a badge/tooltip when not `as_of_snapshot`; `Watchlist.tsx` untouched | ✓ VERIFIED | `ConceptAttributionBadge` (StockListTable.tsx, exported, mirrors AuctionColumnStatusBadge): `as_of_snapshot` → 「概念按当日快照 · 概念数据生效日期 {date}」; all other states → 「概念归属为当前快照，非该日数据」; null/absent attribution → zero render. Rendered in PoolHubPage detail header (line ~336) guarded by `data?.concept_attribution &&`. e2e `concept-pit.spec.ts` 3 cases (current_snapshot / as_of_snapshot with effective date / unavailable) passed in real Chromium (3 passed desktop). **Watchlist.tsx untouched by all 16 phase-28 commits** — `git log 0fb4ce6..HEAD -- frontend/src/pages/Watchlist.tsx` is empty; working-tree modification is pre-existing user work (createPortal/useLayoutEffect, unrelated) |
| 5 | SC4b: Market overview + RPS use the same as-of seam | ✓ VERIFIED | `_dimension_rank(..., as_of=None)` (market_overview_builder.py) local-imports concept_history, reads `read_partition` (kind→gn_ths/hy_ths), honest empty degrade when partition missing; `build_market_overview` passes as_of at :518-519 when `explicit_as_of`. `rps_rotation._load_concept_map_df(repo, as_of)` bypasses 600s module cache via `_load_concept_map_from_partition` (zero cache pollution); `build_rps_rotation(repo, days, as_of)` shares `_build_rotation_full`; `GET /api/rps/rotation?as_of=` with `_AS_OF_RE.fullmatch` + `date.fromisoformat` double validation (400 on invalid), GET-only. Tests: `test_dimension_rank_as_of_partition_priority`, `test_dimension_rank_industry_maps_to_hy_ths`, `test_build_market_overview_as_of_wiring`, `test_overview_api_as_of_partition`, `test_load_concept_map_df_as_of_branch`, `test_build_rps_rotation_as_of_passthrough`, `test_rps_api_as_of_query` |
| 6 | CONCEPT-07: Each archived partition carries provenance manifest; API/UI exposes mapping effective date | ✓ VERIFIED | `_write_partition` writes `{as_of, kind, dimension_field, source_url, fetched_at, captured_at, rows, schema_version, sha256}` (all 9 fields present); `fetched_at` = `config.pull.last_run` → part mtime → captured_at fallback; `dimension_field` self-describing (所属概念/所属同花顺行业). `_project_hub` appends `concept_effective_date`/`concept_captured_at` only when `as_of_snapshot` (fallback states keep prior key set — regression locks `test_pool_history_snapshot`, `test_build_pool_hub_snapshot_has_concept_attribution` green). API passthrough test `test_pool_history_api_passthrough_as_of_snapshot` asserts all three fields; frontend consumes `concept_effective_date` only (zero client inference). Re-verified in 28-03: `test_concept07_history_passthrough_verify` |
| 7 | CONCEPT-05 probe + honesty invariants (no backfill, no strategy_cache writes, POOL-03 guards green) | ✓ VERIFIED | `probe_concept_drift.py` (84 lines) — manual-only OQ-3 probe: `capture`/`capture_from_upstream` + `partition_sha256` + `drift.jsonl` under `ext_history/_probe/`, `py_compile` passes, `test_probe_concept_drift_script_compiles_and_references` green. Honesty: zero backfill code (grep/read confirms forward-only), zero `strategy_cache` reference in concept_history.py, POOL-03 E1-E6 guards + `test_pool_api_is_get_only` + `test_pool_api_no_compute_trigger` all present in test_pool_hub.py. Empty-state exact dict preserved (build_pool_hub_snapshot :296-306) with `concept_attribution: current_snapshot` + `snapshot_origin: None` |

**Score:** 7/7 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | --------- | ------ | ------- |
| `backend/app/services/concept_history.py` | capture/read_partition/manifest/list/sha256 + `_HISTORY_ROOT` | ✓ VERIFIED | 324 lines, all primitives implemented, atomic write, strict date, honest skip, local imports for httpx/ext_presets |
| `backend/app/services/pool_hub.py` | `_build_concept_map` as_of + three-state + `_project_hub` passthrough | ✓ VERIFIED | Four-tuple return, as_of partition-priority, top-level attribution, effective/captured_at appended only on as_of_snapshot, zero write patterns |
| `backend/app/jobs/daily_pipeline.py` | EOD capture hook (non-fatal) | ✓ VERIFIED | Line 1013-1019, inside `if results:` after persist, try/except BLE001 |
| `backend/tests/test_concept_history.py` | 15 cases incl. AST guards | ✓ VERIFIED | capture/read/manifest/idempotent/skip/upstream/state-machine/API/AST guards/probe refs |
| `backend/tests/test_pool_eod_job.py` | EOD hook call + non-blocking cases | ✓ VERIFIED | 6 tests total; 2 new (calls_concept_capture, capture_failure_does_not_block); existing POOL-06 assertions untouched |
| `backend/scripts/probe_concept_drift.py` | OQ-3 drift probe | ✓ VERIFIED | capture/partition_sha256/drift.jsonl, `_probe/` output, py_compile clean |
| `backend/app/services/market_overview_builder.py` | `_dimension_rank` as_of branch + build_market_overview wiring | ✓ VERIFIED | Lines 265-272 partition read; :518-519 explicit_as_of wiring; as_of=None behavior unchanged |
| `backend/app/services/rps_rotation.py` | `_load_concept_map_df` as_of (cache bypass) + build_rps_rotation passthrough | ✓ VERIFIED | `_load_concept_map_from_partition`, `_build_rotation_full` helper, zero cache pollution |
| `backend/app/api/rps.py` | `GET /api/rps/rotation?as_of=` double-validated | ✓ VERIFIED | `_AS_OF_RE.fullmatch` + `date.fromisoformat` → 400; GET-only |
| `backend/tests/test_concept_seam.py` | CONCEPT-06 seam tests | ✓ VERIFIED | 8 cases covering dimension_rank/overview/API/RPS/cache pollution/CONCEPT-07 |
| `frontend/src/lib/api.ts` | PoolHubResponse concept fields | ✓ VERIFIED | `concept_attribution?` + `concept_effective_date?` + `concept_captured_at?` (all optional, backward compatible) |
| `frontend/src/components/pool-hub/StockListTable.tsx` | ConceptAttributionBadge | ✓ VERIFIED | Exported dual-state component + module-level copy consts |
| `frontend/src/pages/PoolHubPage.tsx` | Badge render site | ✓ VERIFIED | Detail header, guarded by `data?.concept_attribution &&`, zero render when absent |
| `frontend/e2e/concept-pit.spec.ts` | Three-state e2e | ✓ VERIFIED | 3 desktop tests passed (current_snapshot / as_of_snapshot+effective date / unavailable) |
| `docs/features.md` | 概念板块 PIT section | ✓ VERIFIED | `### 🧭 概念板块 PIT（历史映射）` section with forward archive, as_of three-state, effective date, honest boundary (~247 dates not backfilled) |

### Key Link Verification

| From | To | Via | Status |
| ---- | --- | --- | ------ |
| daily_pipeline.py | concept_history.py | `concept_history.capture(data_dir, str(as_of))` inside `if results:` (line 1017) | ✓ WIRED |
| pool_hub.py | concept_history.py | `read_partition(data_dir, "gn_ths", as_of)` in `_build_concept_map` as_of branch | ✓ WIRED |
| pool_hub.py | api/pool.py | `concept_attribution`/`concept_effective_date`/`concept_captured_at` in `_project_hub` output dict; history route returns hub unchanged (pool.py zero diff) | ✓ WIRED |
| StockListTable.tsx | backend pool_hub.py | `ConceptAttributionBadge` consumes `data.concept_attribution` (server-frozen, zero client inference) | ✓ WIRED |
| PoolHubPage.tsx | StockListTable.tsx | import + render `<ConceptAttributionBadge attribution=… effectiveDate=…>` | ✓ WIRED |
| market_overview_builder.py | concept_history.py | `_dimension_rank` local import → `read_partition` (gn_ths/hy_ths) | ✓ WIRED |
| rps_rotation.py | concept_history.py | `_load_concept_map_from_partition` → `read_partition(data_dir, "gn_ths", as_of)` | ✓ WIRED |
| api/rps.py | rps_rotation.py | `build_rps_rotation(repo, days, as_of=as_of)` with double validation | ✓ WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `_build_concept_map` as_of branch | `part["rows"]` | `read_partition` → `pl.read_parquet(ext_history/gn_ths/date={as_of}/part.parquet)` | Yes — real partition rows (fixture-written in tests, production EOD-written at runtime) | ✓ FLOWING |
| `_project_hub` | `concept_board`/`concept_attribution` | Partition or current ext via `_build_concept_map`; effective/captured_at from manifest | Yes — no hardcoded empty; empty-state dict is the honest `available:False` regression lock | ✓ FLOWING |
| `_dimension_rank` as_of | `ext_rows` | `read_partition` rows (partition) or `_read_ext_rows` (current ext); missing partition → `[]` honest degrade | Yes | ✓ FLOWING |
| `_load_concept_map_from_partition` | `(_sym_up, concept)` pairs | `read_partition` gn_ths rows | Yes; empty map → empty matrix (honest, no fallback mix) | ✓ FLOWING |

### Behavioral Spot-Checks

Behavior-dependent truths (state transitions / ordering invariants) all have named tests exercised by the orchestrator's run (81 backend passed; concept-pit e2e 3 passed; pool-hub e2e 40 passed; frontend build green — cited, not re-run per assignment):

| Behavior | Test (single named) | Result | Status |
| -------- | ------------------- | ------ | ------ |
| EOD hook non-fatal on capture failure | `test_pool_eod_persist_capture_failure_does_not_block` | orchestrator: passed (81 total) | ✓ PASS |
| EOD hook calls capture with `(data_dir, "2026-08-04")` | `test_pool_eod_persist_calls_concept_capture` | orchestrator: passed | ✓ PASS |
| as_of partition priority (partition ≠ current ext) | `test_build_pool_hub_snapshot_as_of_partition_priority` | orchestrator: passed | ✓ PASS |
| Three-state attribution transitions | `test_attribution_three_state_machine` | orchestrator: passed | ✓ PASS |
| Idempotent capture, zero .tmp residue | `test_capture_idempotent_no_tmp_residue` | orchestrator: passed | ✓ PASS |
| Strict date validation / path traversal | `test_capture_rejects_bad_as_of` + `test_pool_history_rejects_bad_as_of` | orchestrator: passed | ✓ PASS |
| _dimension_rank as_of reads partition (not current ext) | `test_dimension_rank_as_of_partition_priority` | orchestrator: passed | ✓ PASS |
| RPS as_of cache non-pollution | `test_load_concept_map_df_as_of_branch` | orchestrator: passed | ✓ PASS |
| RPS API invalid as_of → 400 | `test_rps_api_as_of_query` | orchestrator: passed | ✓ PASS |
| Frontend badge three states (real Chromium) | concept-pit.spec.ts 3 tests | orchestrator: 3 passed | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| `backend/scripts/probe_concept_drift.py` | `py_compile` + `test_probe_concept_drift_script_compiles_and_references` | orchestrator: passed (in 81) | ✓ PASS (compiles; manual operator run deferred — documented as `--upstream`-optional, zero side effects) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| CONCEPT-01 | 28-01 | Forward daily archive at EOD, atomic, strict date, non-blocking, no backfill | ✓ SATISFIED | capture + EOD hook + honest skip; no backfill code |
| CONCEPT-02 | 28-01 | as_of read-side resolution with current_snapshot fallback | ✓ SATISFIED | `_build_concept_map` as_of branch + fallback |
| CONCEPT-03 | 28-01 | Three-state attribution, never mixed, no merge/stitch | ✓ SATISFIED | State machine + single top-level attribution + tests |
| CONCEPT-04 (P2) | 28-02 | Frontend badge/tooltip when not as_of_snapshot + effective date; Watchlist.tsx untouched | ✓ SATISFIED | Badge + render site + e2e 3-state; git log proves Watchlist untouched |
| CONCEPT-05 | 28-01 | AST guard per module (only ext_history writes; no strategy_cache/execution imports) | ✓ SATISFIED | `test_concept_history_ast_guard_writes_only_ext_history` + `no_execution_imports_no_strategy_cache` + pool_hub zero-write |
| CONCEPT-06 | 28-03 | Same seam to overview `_dimension_rank` + RPS `_load_concept_map_df`; industry archived too | ✓ SATISFIED | Both consumers read_partition; hy_ths archived via `_KINDS`; API as_of |
| CONCEPT-07 (P2) | 28-01/02/03 | Provenance manifest + API/UI effective date | ✓ SATISFIED | 9-field manifest; passthrough test; frontend effective-date display |

No orphaned requirements — all 7 CONCEPT requirements claimed by plans 28-01/02/03 and verified.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TBD/FIXME/XXX/PLACEHOLDER in any phase file | — | None — grep across all 10 phase source files returned zero matches |
| — | — | No stub components/empty handlers/hardcoded empty data in phase files | — | None — badge renders real copy; capture writes real partitions; honest empty states are explicit regression locks |

### Human Verification Required

1. **Real EOD run against production data** — let the EOD job fire (or invoke `_pool_eod_persist` once) with a live `data/` dir containing a populated `ext_data/ext_gn_ths` snapshot; verify `data/ext_history/gn_ths/date={as_of}/part.parquet` + `manifest.json` exist with real rows, and the current `ext_data/ext_gn_ths/part.parquet` is byte-identical before/after. Expected: partition + manifest (9 fields) appear; current ext untouched; pool snapshot/cache still written on capture failure. Why human: requires production data dir + real EOD timing; hermetic tests use fixture dirs and fake captures.
2. **Visual pass in real browser against real backend** — open 股池页 on today's view and a historical date; confirm the badge renders (current_snapshot warning on today / as_of_snapshot + effective date on a dated partition) and guest session renders zero badge without errors. Expected: badge visible per server-frozen attribution; guest view clean. Why human: e2e covers mocked payloads in real Chromium; a real-backend pass confirms the server↔client contract end-to-end.

### Gaps Summary

No blockers, no failed truths, no missing/stub artifacts, no unwired links. All 7 must-have truths (4 roadmap success criteria + CONCEPT-07 manifest/API + probe/honesty cluster) verified against the actual code, not SUMMARY claims. Two deploy/visual items require human confirmation (real EOD with production data; real-browser visual pass) — these are external-environment checks hermetic tests cannot cover, consistent with Phase 27's precedent (real 09:26 cron deploy + premarket view visual). Status: **human_needed** per decision tree (human items present), with full code-level pass.

---

_Verified: 2026-08-06T16:10:00Z_
_Verifier: Claude (gsd-verifier)_
