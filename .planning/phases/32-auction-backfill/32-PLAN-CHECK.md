# Phase 32 竞价历史回填 — Plan Check Report

**Checker:** PlanCheckerP32 (gsd-plan-checker) · **Date:** 2026-08-06
**Scope:** Goal-backward executability review of the 3 Phase 32 plans (AQ-01..06), before execution.
**Artifacts reviewed:** `REQUIREMENTS.md` (AQ-01..06), `RESEARCH.md`, `PATTERNS.md`, `32-01/02/03-PLAN.md`.
**Method:** Live repo anchor spot-checks (read-only; no builds/tests run). Every file/symbol/line the plans name was verified against the current codebase.

---

## Verdict

| Plan | Wave | Depends | Tasks | Files | Estimate (conf) | Verdict |
|------|------|---------|-------|-------|-----------------|---------|
| 32-01 | 1 | — | 3 | 5 | 60k (low) | **EXECUTABLE** — notes only |
| 32-02 | 2 | 32-01 | 3 | 4 | 66k (low) | **EXECUTABLE** — 3 warnings |
| 32-03 | 2 | 32-01 (+32-02 gates) | 3 | 2 | 46k (low) | **EXECUTABLE** — 2 warnings |

**Overall: EXECUTABLE — 0 blockers, 5 warnings, 6 notes.** All warnings are spec-hint corrections (missing method/import declarations, one monkeypatch-target mismatch, one `-k` filter gap, one cross-plan key-set contract) — recoverable during execution, but fix before starting. Estimate note (ADR-2629): all `confidence: low`, uncalibrated; no budget configured → advisory only.

---

## Requirement Coverage (AQ-01..06)

| Requirement | Delivered by | Covered? |
|-------------|--------------|----------|
| AQ-01 (xyz capability + `get_auction` + probe auto-discovery) | 32-01 T1 + T3 (discovery + available flip) | ✅ |
| AQ-02 (backfill job + `POST /api/kline/auction/backfill`) | 32-02 T1 (service) + T3 (endpoint + main.py) | ✅ |
| AQ-03 (probe/preflight fail-closed, kline_daily-aligned dates, per-symbol ledger) | 32-02 T1 | ✅ |
| AQ-04 (write-seam reuse, idempotent/atomic, honest column absence, origin dict) | 32-01 T2 (seam extraction) + 32-02 T1/T2 + 32-03 T1 (ledger/origin/absent cols) | ✅ |
| AQ-05 (1 symbol/request, rpm pacing, subset runs, cooperative cancel) | 32-02 T1 (serial loop + bounds) + T2 (pacing + cancel) | ✅ |
| AQ-06 (P2 minute-history CLOSED, doc-only) | 32-03 T3 (docs + evidence pointer) | ✅ |
| Success criterion 4 (virtual price == daily open) | 32-03 T2 (canned always-on + network-gated) | ✅ |

No requirement dropped; no scope reduction (probe cache, per-partition provenance explicitly deferred). **Dependencies:** 32-01 wave 1; 32-02/32-03 wave 2 parallel, `depends_on: [32-01]`, 32-03 additionally `<precondition>`-gated on 32-02 (`run_auction_backfill`, `@router.post`) — acyclic, wave-consistent, no forward refs. Test-file ownership disjoint (32-02 owns `test_auction_backfill.py`, 32-03 owns `test_auction_backfill_honesty.py`).

---

## Executability Spot-Checks

### New files (must be created — verified the plan says so)

| File | Plan creates it? |
|------|------------------|
| `backend/tests/test_xyz_provider.py` | ✅ 32-01 T1 (absent today, glob-verified) |
| `backend/app/services/auction_backfill.py` + `backend/app/api/auction_backfill.py` | ✅ 32-02 T1 / T3 (absent today) |
| `backend/tests/test_auction_backfill.py` / `test_auction_backfill_honesty.py` | ✅ 32-02 T1 / 32-03 T1 (absent today) |

### Backend anchors (must already exist — all verified)

| Symbol | Actual | Plan claim | Status |
|--------|--------|------------|--------|
| `ProviderCapabilities.auction: bool = False` | `base.py:26` | base.py zero-change | ✅ exact |
| xyz `capabilities` / `_price_frame` / `_call_tool` / `_parse_*` | `xyz_provider.py:48-56 / 107-149 / 151-177 / 179-215` | 32-01 must_haves | ✅ exact |
| `_SYMBOL_RE` + router prefix `/api/kline/auction` | `auction_history.py:31 / 28` | 32-02 T3 | ✅ exact |
| Write-seam segment (555..565 → crop → merge-upsert `unique(["symbol","datetime"], keep="last")` → `.tmp` rename → `return df.height`) | `auction_sync.py:126-164` | 32-01 T2 pure-move source | ✅ exact (matches extraction spec verbatim) |
| `_first_auction_provider` / `can_sync_auction` (probe gate) | `auction_sync.py:57-84 / 87-95` | 32-01/32-02 | ✅ exact |
| `PROBE_SYMBOL` / `_ERROR_DETAIL_MAX=200` / `_default_sources` / `_default_fetcher` (single-date) / `resolve_auction_probe(source_resolver=, fetcher=)` | `auction_probe.py:17 / 29-30 / 86-116 / 116-118 / 139-186` | 32-01 T3 / 32-02 T1 | ✅ exact |
| `run_pool_backfill` shape (cancel :88-91, terminal :66-77) | `pool_backfill.py:30-123` | 32-02 mirror | ✅ exact |
| `_long_task_executor` / pool_backfill endpoint (validation :104-122, single-flight, executor task) | `pipeline.py:17 / 89-173` | 32-02 T3 template | ✅ exact |
| `job_store` lifecycle + run slot / `sleep_between_batches(i, rpm)` + `_reserve_slot` | `pipeline_jobs.py:99-267` / `rate_limits.py:76-83, 18-32` | 32-02 | ✅ symbols exist |
| `kline_auction` DuckDB view (`union_by_name=true`) + `repo.store.data_dir` | `repository.py:162-164 / 290` | 32-02 scope | ✅ (⚠️ `repo.query()` — W-1) |
| `_GUEST_READ_GET_PATHS` GET-only / auction_history registration | `main.py:779-793 / 852-853` | 32-02 T3 | ✅ exact |
| `_noop` / `logger` module pattern (mirror source) | `pool_backfill.py:23-27` | 32-02 T1 | ✅ exists as precedent |

### Runtime / hermeticity

- `backend/.venv` present; `polars 1.40.1`, `httpx 0.28.1` importable ✅.
- **Probe hermeticity after the capability flip (R3):** every existing auction suite already patches the probe (`test_auction_sync.py:80-81,113-114,148-149,180-181,228-229`, `test_auction_history.py:48-51`, `test_auction_probe.py` injects resolver/fetcher) — "既有用例零改动保持绿" survives `resolve_auction_probe()` becoming live-HTTP ✅.
- `Watchlist.tsx` exists; absent from all `files_modified`; no `frontend/` file in any plan ✅. No `CLAUDE.md` in repo root → Dimension 10 **SKIPPED** (same as 28/29).

---

## Hidden-blocker sweep

| Check | Result |
|-------|--------|
| Test file named but not created | ✅ none — 3 new files explicitly created; 5 named existing suites all present |
| `Watchlist.tsx` / frontend touched | ✅ none |
| Writes `strategy_cache` | ✅ none — E3 guard (32-03 T2 Test 5); service/endpoint docstring templates verified to avoid the literal |
| POOL-03 violated | ✅ none — POST in separate `api/auction_backfill.py` router; `auction_history.py` stays GET-only (existing guard untouched; 32-03 adds independent re-check) |
| Circular import | ✅ acyclic — backfill service is a leaf (auction_sync/auction_probe/rate_limits/pipeline_jobs); endpoint imports `_SYMBOL_RE` from auction_history (which imports only auction_probe) |
| `write_auction_partitions` extraction feasible | ✅ segment matches verbatim; helper after `_atomic_write_parquet` has all constants in scope; existing suite patches only `resolve_auction_probe`/`_first_auction_provider`, unaffected |
| Verify command syntax | ✅ `grep -c` gates fail-closed; `-k` filters match planned names (W-4 gap aside); no shell tricks |

---

## Issues

### Blockers (must fix)

None.

### Warnings (should fix before execution)

**1. [task_completeness] 32-02 T1 — `repo.query(...)` does not exist on `KlineRepository`**
- Specced `repo.query("SELECT DISTINCT symbol FROM kline_daily").iter_rows(named=True)`; live repo has **zero** `def query(` in `backend/app`. Established patterns: `repo.db.execute(...).fetchall()` (thread-safe wrapper `repository.py:340`) or the plan's own fallback `pl.scan_parquet(...).select("symbol").unique()` (RESEARCH §2, drift-safe for `quote_ts`).
- Fix: state one concrete mechanism in the action step; keep `_FakeRepo.query()` as a test-only shape.

**2. [task_completeness] 32-02 T1 — service import list omits `date`, `logger`, `_noop`**
- As specced (`logging` + `typing` + `polars` + `KlineRepository`) the module raises `NameError`: `aligned_dates_as_date = {date.fromisoformat(d) …}` needs `from datetime import date`; `logger.exception` needs `logger = logging.getLogger(__name__)`; `emit = on_progress or _noop` needs `_noop` defined.
- Fix: mirror `pool_backfill.py:20-27` (module `logging` + `logger` + `_noop(stage, pct, msg, **kwargs)`; function-level `from datetime import date`).

**3. [verification_derivation] 32-02 T1/T2 — pacing-test monkeypatch target mismatch**
- T1 specced `sleep_between_batches` as a **function-level** import (rebinds local name each call), but T2 Test 1 patches the module attribute `auction_backfill.sleep_between_batches` → patch ineffective → real 2s sleeps run, `calls == [(0,30),(1,30),(2,30)]` fails.
- Fix: module-level import in the service (then the module-attr patch works) or patch `app.tickflow.rate_limits.sleep_between_batches`.

**4. [verification_derivation] 32-03 T1 — `-k "ledger or origin or bj or empty"` skips Test 2 (部分失败如实)**
- A natural name like `test_auction_backfill_partial_failure_honest` matches none of the four tokens → T1's own gate skips it (T3's full-file run covers it).
- Fix: name Test 2 with a covered token or add `partial`/`honest` to the `-k` filter.

**5. [data_contract] 32-02 ↔ 32-03 — terminal-dict key-set: fail-closed 9 keys vs success 8 keys**
- Fail-closed dict adds `reason` (9 keys); 32-03 T1 asserts the success terminal's key set == exactly the 8 keys. Coexists only because the assertion is scoped to the success path — never stated.
- Fix: one sentence in 32-02 T1: 8-key invariant applies to the success terminal; fail-closed adds `reason` (and `reason` never leaks into the success path).

### Notes (advisory)

**1. Real-MCP-vs-mocked network test policy (sandbox determinism).** Consistent across plans: hermetic suites patch `resolve_auction_probe` / `_first_auction_provider` / `_call_tool`; live HTTP only under `RUN_NETWORK_TESTS=1` (32-01 T3 Test 4, 32-03 T2 Test 2) with verdicts accepted as `available|fail_closed|error` (never asserted unconditionally); real `kline_daily` read-only, writes only into tmp lakes → deterministic CI.
**2.** 32-03 T2 verify `-k "cross_check or ast_guard or get_only or strategy_cache"` doesn't match `test_auction_virtual_price_equals_daily_open` — harmless (self-skips without env; verification runs it via `-k virtual_price`).
**3.** 32-02 T3 Test 6 — assert `"已有数据任务在运行" in job["error"]` (substring); endpoint writes the longer message.
**4.** R3 accepted: `resolve_auction_probe()` = 1 live HTTP (1.6s/8s) per call on history endpoint + EOD gate; probe-cache is a documented follow-up, not Phase 32 scope — no scope creep.
**5.** Line-ref hygiene: `chain._get_provider :74-75` (actual `:62`), `pool_snapshot.list_enriched_dates :144` (actual ~`:150`), `main.py :853`, `pipeline_jobs` line numbers — symbols all exist; executors re-read by name.
**6.** `get_auction` row mapping doesn't skip `None` `time` rows (unlike `_price_frame`'s `continue`) — null `datetime` rows are structurally dropped by the seam's window filter; no correctness impact, optionally mirror `_price_frame`.

---

## Dimension Summary

1. Requirement coverage — ✅ PASS (AQ-01..06 + criterion 4; no leakage) · 2. Task completeness — ✅ PASS (9/9; W-1/W-2 imports, W-3 patch target) · 3. Dependency correctness — ✅ PASS (32-01 → 32-02 ∥ 32-03, gated, acyclic) · 4. Key links — ✅ PASS (provider→probe/sync, seam→job, job→endpoint, endpoint→main, honesty→guard) · 5. Scope sanity — ✅ PASS (3/3/3 tasks, 5/4/2 files; estimates advisory) · 6. Verification derivation — ✅ PASS (W-3/W-4 refine two gates) · 7. Context compliance — ✅ PASS (zero new deps; honesty as tests, not comments) · 8. Nyquist — ✅ PASS (every task `<automated>` verify; no watch/MISSING/30s+ gates) · 9. Cross-plan contracts — ✅ PASS (seam/terminal/ledger consistent; W-5 is a scoping clarification) · 10. CLAUDE.md — SKIPPED · 11. Research resolution — ✅ PASS (R1/R2 gated, R3/R7 accepted, R8 BJ recorded not fabricated) · 12. Pattern compliance — ✅ PASS (8/8 analogs; pure-move + one-flag unlocks verified) · Verify syntax — ✅ PASS (fail-closed `grep -c`, matching `-k`, no shell tricks)

---

## Recommendation

All three plans are **EXECUTABLE** as-is, 0 blockers. Before execution starts, apply the five warning fixes (spec-hint corrections; no structural or dependency changes):

1. 32-02 T1: replace `repo.query(...)` with `repo.db.execute("SELECT DISTINCT symbol FROM kline_daily").fetchall()` or the scan_parquet fallback.
2. 32-02 T1: declare `from datetime import date`, module `logger`, `_noop` (mirror `pool_backfill.py:20-27`).
3. 32-02 T1/T2: module-level `sleep_between_batches` import (or patch `rate_limits` attr) so the pacing test's patch takes effect.
4. 32-03 T1: name Test 2 with a `-k`-covered token or extend the filter.
5. 32-02 T1: state the 8-key invariant applies to the success terminal; fail-closed adds `reason`.

Proceed to `/gsd-execute-phase 32` (wave 1: 32-01; wave 2: 32-02 + 32-03 in parallel, precondition gates enforced).

---
*Plan-checked: 2026-08-06 — read-only review; no source/plan files modified; no builds/tests run; `Watchlist.tsx` untouched.*
