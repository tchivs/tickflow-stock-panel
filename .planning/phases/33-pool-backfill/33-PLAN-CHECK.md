# Phase 33 股池回填 — Plan Check Report

**Checker:** PlanCheckerP33 (gsd-plan-checker) · **Date:** 2026-08-06
**Scope:** Goal-backward executability review of the 3 Phase 33 plans (PB-01..04), before execution.
**Artifacts reviewed:** `REQUIREMENTS.md` (PB-01..04), `RESEARCH.md`, `33-01/02/03-PLAN.md`, `32-PLAN-CHECK.md` (precedent).
**Method:** Live repo anchor spot-checks (read-only; no builds/tests run). Port, endpoint shapes, response field names, test-file helpers, and runbook commands verified against the current codebase and live lake state.

---

## Verdict

| Plan | Wave | Depends | Tasks | Files | Verdict |
|------|------|---------|-------|-------|---------|
| 33-01 | 1 | — | 3 | test_pool_backfill.py + 33-01-SUMMARY.md | **EXECUTABLE** — 1 warning (W-1) |
| 33-02 | 2 | 33-01 | 3 | test_pool_hub.py, test_concept_history.py + 33-02-SUMMARY.md | **EXECUTABLE** — 2 warnings (W-1, W-2) |
| 33-03 | 2 | 33-01 | 3 | docs/features.md, test_premarket_pool.py + 33-03-SUMMARY.md | **EXECUTABLE** — 2 warnings (W-1, W-4) |

**Overall: EXECUTABLE — 0 blockers, 4 warnings, 4 notes.** W-1 (response contract) touches verification gates in all three plans; the rest are spec-hint corrections. No structural, dependency, or scope changes needed.

---

## Requirement Coverage (PB-01..04)

| Requirement | Delivered by | Covered? |
|-------------|--------------|----------|
| PB-01 (sandbox subset E2E: provenance, cache byte-identical, /pool/history renders, idempotent) | 33-01 T1 (real 8-day run + 验收 1-4) + T2 Tests 1-3 (bounds / D2 endpoint-level / idempotent + /pool/dates) + T3 (auction honest rows 3-state) + 33-02 T1 (renders backfilled snapshot) | ✅ |
| PB-02 (full-248 runbook, deploy-gated, mechanics verified on subset) | 33-03 T1 (docs runbook) + T3 (runbook step-7 re-verify on sandbox) | ✅ |
| PB-03 (PIT interplay, honest `current_snapshot` fallback, no forgery) | 33-02 T1 (render + attribution) + T2 (key-set lock + positive control + origin-independence) + T3 (sandbox spot-check) | ✅ |
| PB-04 (`premarket_results` honest gap; no sandbox path) | 33-03 T2 (docs: deploy gate + data gate) + T3 (structural root-isolation test) | ✅ |

No requirement dropped; no scope reduction. **Dependencies:** 33-01 wave 1 → 33-02 ∥ 33-03 wave 2, acyclic; 33-02/33-03 sandbox spot-checks precondition-gated on 33-01 partitions. **File ownership disjoint:** 33-01 `test_pool_backfill.py`; 33-02 `test_pool_hub.py`+`test_concept_history.py`; 33-03 `docs/features.md`+`test_premarket_pool.py` — zero overlap, both wave-2 plans leave `test_pool_backfill.py` alone. `Watchlist.tsx`/`frontend/` untouched in all three.

---

## Executability Spot-Checks

### Port / runbook (Task-list item 4)

- **Port 3018 confirmed 3×**: `README.md:54` (`uv run uvicorn app.main:app --reload --port 3018`), `dev.sh:16` (BACKEND_PORT default 3018), `.env:14` / `.env.example:14` (PORT=3018). All `curl localhost:3018/...` targets and the runbook command are valid.
- **jq available** (`/usr/bin/jq` — jaq 2.3.0, jq-compatible). `data/**` gitignored (`.gitignore:44-47`) → Task 1 real run writes only ignored dirs.
- **Server lifecycle**: 33-01 T1 and 33-02 T3 state 起服务 + exact command + stop (hub-aware). 33-03 T3 **does not** start the server for its curl verifications (W-4).

### Backend anchors (all verified exact)

| Symbol | Actual | Plan claim |
|--------|--------|------------|
| `POST /api/pipeline/backfill` (validation `max_days` 1..500 + bool-excluded, single-flight, run slot, executor, `{"status":"started","job_id"}`) | `pipeline.py:89-162` | 33-01/33-03 ✅ |
| `GET /api/pipeline/jobs/{id}` / `POST .../cancel` (cooperative) | `pipeline.py:169-190` | ✅ |
| `run_pool_backfill` (gaps :57, bounds :58-63, cancel :77-81, `strategy_version="unknown"` engine=None :66-67, 6-key terminal :118-123, `if results:` gate) | `pool_backfill.py:30-123` | 33-01 ✅ |
| `persist_point_snapshot` payload `{as_of, computed_at, strategy_version, snapshot_type:"point", schema_version:1, snapshot_origin, results}` + origin ∈ {eod,backfill,manual} | `pool_snapshot.py:52-103` | 33-01 jq filters ✅ |
| `list_backfill_gaps` = enriched − snapshots, ISO asc | `pool_snapshot.py:157` | ✅ |
| `GET /api/pool/dates` → `{dates, count, latest, backfill_needed, backfill_examples}` | `pool.py:55-77` | 33-01/33-03 ✅ |
| `GET /api/pool/history` → `build_pool_hub_snapshot`; empty state `{as_of:None, available:False, ..., snapshot_origin:None}`; present state `_project_hub` out + `snapshot_origin` passthrough (:334) + `mode` | `pool.py:79-113` / `pool_hub.py:293-335` | ⚠️ W-1/W-2 |
| `concept_effective_date`/`concept_captured_at` only when `attribution == "as_of_snapshot"` (回退态不追加) | `pool_hub.py:245-253` | 33-02 key-set lock ✅ |
| engine short-circuit `requires_auction_data` + column absent → empty StrategyResult | `engine.py:345-348` | 33-01 T3 ✅ |
| `_attach_auction` dual gate: probe `resolve_auction_probe().status != AuctionProbeStatus.available` → return df; partition existence; per-symbol null | `auction_columns.py:93-112` | ⚠️ W-3 |
| `fixture_mode` scheduler gate + premarket job id/registration | `main.py:119,510-520` / `daily_pipeline.py:969,1024,1168-1173` | 33-03 ✅ |
| Auction-backfill section + `## 🧰 数据与扩展` in docs | `features.md:61-78, ~:194`; existing backfill one-liner :30-31 | 33-03 T1 insertion point ✅ |

### Test conventions (Task-list items 2)

- **All 7 planned test names absent today** (grep across `backend/tests`) — created by the plans; 33-01 = 9 existing + 4 new = 13; 33-02 = 47+1 / 15+1; 33-03 = 12+1. Counts match RESEARCH §4.1.
- **Monkeypatch convention correct**: existing tests patch `ScreenerService.run_all_with_hits` with signature `(self, as_of, strategy_ids=None, engine=None)` — matches `screener.py:723`. `_FakeRepo` :34-60, `_make_env` :62-75, `_write_strategy_cache` :78-88, `_make_backfill_app`/`_wait_job_terminal`/`_wait_slot_free` :114-160 all present.
- **D2 byte-identical reuse**: existing `test_backfill_never_touches_strategy_cache` already holds the exact pattern (`read_bytes() == before` + unlink → not recreated) — 33-01 T2 Test 2 mirrors it verbatim at endpoint level. ✅
- Helpers in other suites confirmed: `_write_snapshot(origin=)` :148-229, `_make_client` :615, `_FakeEngine` :602, `_strategies_by_id` :144 (test_pool_hub); `_write_partition_fixture` :440 + key-set-lock precedent (test_concept_history); `_FakeRepo` :64-90 + root-absence pattern :197-213 + `_write_canned_strategy` :33 (test_premarket_pool). Guard files `test_guest_masking.py`, `test_pool_eod_job.py` exist.

### Live lake facts (read-only)

- `kline_daily_enriched` = **248** partitions (2025-07-29..2026-08-05); `screener_results` = **0** → post-subset `count==8, backfill_needed==240` arithmetic holds. `premarket_results`/`ext_history` **absent** (PB-04/PB-03 facts hold). `strategy_cache.json` **exists** → D2 md5 before/after is a real check (plan's "若不存在则不创建" branch covers absence).

---

## Issues

### Blockers (must fix)

None.

### Warnings (should fix before execution)

**1. [data_contract] 33-01 T1 verify#4 + 33-02 T1 + 33-02 T3 — `/pool/history` present-state response has NO `available` key**
- Verified: present state = `_project_hub` out `{as_of, updated_at, strategies, resonance_count, concept_attribution, auction_columns}` + `snapshot_origin` + `mode` (`pool_hub.py:241-334`); `available` appears **only** in the missing-snapshot empty state (`pool_hub.py:314-321`). 33-01 T1 verify#4 and 33-02 T3 curl `jq '{available, ...}'` → `"available": null`; 33-02 T1 `assert available true` → KeyError. Existing suite asserts the present-state key subset *without* `available` (`test_pool_history_snapshot`, test_pool_hub.py:790).
- Fix: drop `available` from the jq filters/assertions; present-state contract = `snapshot_origin=="backfill"` + `(.strategies|length) ≥ 1` (empty state is distinguishable via `as_of:null`/`strategies:[]`).

**2. [spec_hint] 33-02 T1 — `snapshot_type=="point"` / `schema_version==1` 透传 (抽查) is not in the response**
- `snapshot_type`/`schema_version` live in the **partition payload** (`pool_snapshot.py:87-88`), never in the `/pool/history` projection (`pool_hub.py:241-249`). `body["snapshot_type"]` → KeyError.
- Fix: assert via `pool_snapshot.load_point_snapshot(tmp_path, d)["snapshot_type"]`/`["schema_version"]`, or drop (already covered by test_pool_snapshot suite).

**3. [task_completeness] 33-01 T3 — probe injection must match `auction_columns` consumption shape, not the premarket `to_dict` shape**
- Consumption is `resolve_auction_probe().status != AuctionProbeStatus.available` (`auction_columns.py:96-99`, enum compare). The cited precedent `test_premarket_pool.py:166-168` injects `SimpleNamespace(to_dict=...)` — a **different** shape (premarket reads `to_dict()`).
- Fix: state the injection explicitly — `monkeypatch.setattr(app.services.auction_columns, "resolve_auction_probe", lambda: SimpleNamespace(status=AuctionProbeStatus.available|fail_closed|error))` with `from app.services.auction_probe import AuctionProbeStatus` (patching `auction_probe.resolve_auction_probe` is equivalent — same function object).

**4. [verification_gap] 33-03 T3 — curl verifications assume the backend is up, but no start command is given**
- 33-01 T1 explicitly stops the service after verification; 33-03 T3's `<verify>` manual items (2-3) curl `localhost:3018` but its behavior section never starts it (33-01 T1 / 33-02 T3 do).
- Fix: add to 33-03 T3 behavior: 起服务 `cd backend && uv run uvicorn app.main:app --port 3018` (README:54) if not already running, and stop after; run service lifecycle via hub `op:start`/`op:stop`.

### Notes (advisory)

**1.** Line drift: `_FakeRepo` at `test_pool_backfill.py:34-60` (RESEARCH cites :32-50); `_write_strategy_cache` :78-88 correct. Symbols all exist — executors re-read by name.
**2.** Probe latency worst case: 8 days × 8s timeout = **+64s** if source down (RESEARCH §2.4), inside the 1-5min estimate's upper bound; probe fail-closed → `requires_auction_data` strategies total=0 (bimodal table already handles it). Record the verdict; do not treat fail-closed as a failure.
**3.** `_wait_job_terminal` default 5s timeout is fine for the real-`run_pool_backfill` + patched-`run_all_with_hits` fast path (5 daily persists ≈ ms); existing endpoint tests already rely on it.
**4.** `available` absence also means the `jq` in 33-01 verify#4 output `{"available": null, ...}` must not be misread as a failure — same root cause as W-1.

---

## Dimension Summary

1. Requirement coverage — ✅ PASS (PB-01..04, no leakage) · 2. Task completeness — ✅ PASS (9/9; W-3 injection shape, W-4 server start) · 3. Dependency correctness — ✅ PASS (33-01 → 33-02 ∥ 33-03, acyclic) · 4. Key links — ✅ PASS (endpoint→service→snapshot→read path→concept; doc↔service line refs) · 5. Scope sanity — ✅ PASS (3/3/3 tasks; estimates advisory, all confidence low) · 6. Verification derivation — ✅ PASS (W-1/W-2 correct two gates; W-4 completes one) · 7. Context compliance — ✅ PASS (zero new deps; honesty as tests/docs, no fabrication) · 8. Nyquist — ✅ PASS (every task has `<automated>` verify; no MISSING gates) · 9. Cross-plan contracts — ✅ PASS (6-key terminal, origin, key-set lock, D2, root isolation consistent across plans) · 10. CLAUDE.md — SKIPPED (absent, same as 28/29/32) · 11. Research alignment — ✅ PASS (RESEARCH facts re-verified live: 248 enriched, 0 snapshots, dirs absent, cache present).

---

## Recommendation

All three plans are **EXECUTABLE** as-is, 0 blockers. Before execution starts, apply the four warning fixes (spec-hint corrections; no structural or dependency changes):

1. 33-01 T1 verify#4 + 33-02 T1 + 33-02 T3: drop `available` from `/pool/history` assertions/jq (present state has no such key); use `snapshot_origin=="backfill"` + `n ≥ 1`.
2. 33-02 T1: drop or relocate the `snapshot_type`/`schema_version` passthrough assertion to the partition payload.
3. 33-01 T3: inject probe via `SimpleNamespace(status=AuctionProbeStatus.available|fail_closed|error)` on `app.services.auction_columns.resolve_auction_probe`.
4. 33-03 T3: add the server start command (and hub lifecycle) to the behavior section before the curl verifications.

Proceed to execute 33-01 (wave 1), then 33-02 + 33-03 in parallel (wave 2, precondition: 33-01 partitions in place).

---
*Plan-checked: 2026-08-06 — read-only review; only this PLAN-CHECK file written; no source/plan files modified; no builds/tests run; `Watchlist.tsx` untouched.*
