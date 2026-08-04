---
phase: 16-auction-data
slug: 16
verified: 2026-08-04T17:30:00Z
status: passed
score: 13/13
verified_truths: 13
failed_truths: 0
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: failed
  previous_score: 12/13
  gaps_closed:
    - "The Data page minute-K StatCard renders `分钟K同步中·覆盖{N}天` with `{N}` in mono/tabular numerals when sync is enabled and a coverage count is present (plus the muted `分钟K未启用` disabled sibling)."
  gaps_remaining: []
  regressions: []
---

# Phase 16: 竞价数据层 (Auction Data) — Verification Report (Re-verification)

**Phase Goal:** Researchers can sync minute-K without corrupting the daily lake, compute and persist a governed open-gap factor, and know — via an honest capability probe — whether true 9:15–9:25 集合竞价 match data is available before committing strategy breadth.
**Verified:** 2026-08-04
**Status:** passed — all 13 must-have truths VERIFIED. The sole prior blocker (minute-K StatCard UI-SPEC copy) is closed by fix commit `b41de34`.
**Re-verification:** Yes — after gap closure.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | DATA-01: Researcher can enable minute-K sync and 1m bars land in `data/kline_minute/date=*/part.parquet` with canonical columns and morning bars stamped >= 09:30:00 (never 09:15-09:29). | ✓ VERIFIED (regression) | `backend/tests/test_minute_sync_verify.py#test_minute_sync_enable_persists_and_leaves_daily_lake_unchanged` green in re-run (25/25 passed). Asserts canonical cols == `CANONICAL_MINUTE_COLS`, `Datetime("us")`, `datetime.min() == 2026-08-04 09:30`. |
| 2 | DATA-01: Enabling/running minute sync leaves the daily-K lake (`kline_daily`, `kline_daily_enriched`) byte-for-byte unchanged. | ✓ VERIFIED (regression) | Same test snapshots partition sets + per-file sha256 before/after and asserts equality — green in re-run. |
| 3 | DATA-01: Timestamp convention regression-locked: `_minute_ts` anchors start-of-day to 09:30; `_bucket_minutes` never buckets a pre-09:30 bar into the morning session. | ✓ VERIFIED (regression) | `test_minute_timestamp_convention.py` (3 tests) green in re-run; source impl at `free_stockdb_provider.py`. |
| 4 | DATA-01: Minute sync can be scoped to an operator-chosen symbol list (empty = full universe, default unchanged). | ✓ VERIFIED (regression) | `preferences.get_minute_sync_symbols/set_minute_sync_symbols` (preferences.py:117,122), `MinuteSyncPrefs.minute_sync_symbols` (settings.py:320,380,685,693), `daily_pipeline._resolve_minute_symbols` (656) — presence re-confirmed; unit tests green in re-run. |
| 5 | DATA-01: Data page minute-K StatCard renders `分钟K同步中·覆盖{N}天` with `{N}` mono/tabular when sync enabled and coverage present; disabled sibling renders muted `分钟K未启用`. | ✓ VERIFIED | Fix commit `b41de34`. `Data.tsx:492-500`: UI-SPEC comment; `minuteDays = s?.minute?.trading_days ?? 0`; `minuteSyncing = hasMinuteCap && minuteAuto`; hint ternary renders `<span className="text-secondary">分钟K同步中·覆盖</span><span className="font-mono tabular-nums text-secondary">{minuteDays}</span><span className="text-secondary">天</span>` when `minuteSyncing && minuteDays > 0`, else `<span className="text-muted">分钟K未启用</span>`. `StatCard.tsx:99` `hint: React.ReactNode` (allows JSX); rendered at `StatCard.tsx:240` `{hint}`. `minuteAuto = prefs.data?.minute_sync_enabled ?? false` (Data.tsx:190); `hasMinuteCap = !!caps.data?.capabilities?.['kline.minute.batch']` (Data.tsx:233); `minuteDays` from data-status minute payload (Data.tsx:493). `npx tsc --noEmit` exit 0 (JSX type-valid). Exact strings present verbatim. |
| 6 | DATA-01: Minute-K toggle disabled at 40% opacity with `需 Pro+` chip without `kline.minute.batch`; stale coverage never displayed as fresh. | ✓ VERIFIED (regression) | `MinuteSyncConfig.tsx` capability gate + `_safe_aggregate_minute` partition counting (data.py) — presence re-confirmed; tsc clean. |
| 7 | DATA-02: Governed `open_gap` (`open/prev_close−1`) computed, persisted in enriched storage, provably consumable by strategy filters. | ✓ VERIFIED (regression) | Registries re-confirmed at pipeline.py:66,95,165,304,317,491-498; `test_open_gap_factor.py` (7 tests) green in re-run. |
| 8 | DATA-03: Platform exposes honest auction-probe verdict (not_configured/available/fail_closed/error) from a backend service via `/api/data/auction-probe`; Data page renders approved UI-SPEC vocabulary. | ✓ VERIFIED (regression) | `auction_probe.py` (AuctionProbeStatus/AuctionProbeVerdict/resolve_auction_probe — 3 symbols confirmed); GET `/auction-probe` (data.py:626) + POST `/auction-probe/redetect` (641); `AuctionProbeCard.tsx` (11 UI-SPEC state strings); `test_auction_probe.py` (11 tests) green in re-run. |
| 9 | DATA-03: When true 9:15-9:25 集合竞价 data unavailable, system fails closed to derived `open_gap` baseline and NEVER labels the 09:30 continuous bar as 集合竞价 data. | ✓ VERIFIED (regression) | `_has_in_window_rows` window guard + verbatim `FAIL_CLOSED_DETAIL`; regression tests green in re-run. |
| 10 | DATA-03: Provider returning only >= 09:30 bars can never produce `available`; probe window always `09:15-09:25`. | ✓ VERIFIED (regression) | Window constants + `_normalize_auction` filter; `test_verdict_window_and_fallback_are_fixed_for_every_status` green in re-run. |
| 11 | DATA-03: Probe panel renders `竞价数据探测中…` with `role="status"` and disables `重新探测` while in flight (no concurrent runs). | ✓ VERIFIED (regression) | `AuctionProbeCard.tsx` spinner + `role="status"` + `disabled={running}` — presence re-confirmed. |
| 12 | DATA-03: Probe failure renders `竞价数据探测失败：{message}。已按未接入处理，当前使用派生开盘涨幅因子。请重试。` with `role="alert"`; status never downgrades to `竞价数据可用`. | ✓ VERIFIED (regression) | `AuctionProbeCard.tsx` `role="alert"` danger treatment; `available` reachable ONLY from server `status === 'available'` — presence re-confirmed. |
| 13 | DATA-03: Probe panel renders `竞价数据未配置` with hint copy and no probe action when no source configured; panel never blanks. | ✓ VERIFIED (regression) | `AuctionProbeCard.tsx` muted heading + hint; `showRetry` excludes `not_configured`; panel `min-h` — presence re-confirmed. |

**Score:** 13/13 truths verified (0 present-behavior-unverified).

**Roadmap Success Criteria (the contract):**
1. ✅ Enable minute-K sync → 1m bars land with correct 09:30+ timestamps; daily partitions unchanged — behavioral test passed (re-run).
2. ✅ 开盘涨幅 governed column, unit-tested on fixture, consumed by strategy filters — behavioral tests passed (re-run).
3. ✅ Auction-data probe verdict observable; when unavailable, no UI or strategy labels the 09:30 bar as auction data — behavioral tests passed (re-run).

### Backstop Rows (verification: backstop → insufficient_spec → human_needed — carried forward, non-gate)

The 12 plan backstop rows (3 in 16-01, 9 in 16-02) were routed to human verification in the initial report and remain outstanding human items. They are **not** must-have truths and do not affect the 13/13 must-have score. They are documented here so they are not silently dropped:

| # | Backstop | Status |
|---|----------|--------|
| B1-B3 (16-01) | Minute-K copy wraps (`overflow-wrap:anywhere`); 44px touch targets <768px with >=8px gaps; `prefers-reduced-motion` instant transitions | 🧪 human item (carried forward) |
| B4-B12 (16-02) | Probe verdict wrap/height reservation/touch targets/reduced-motion/single-state-row/accent-available/retry-affordance/partial-config honesty | 🧪 human item (carried forward) |

Note: several backstop rows remain partially observable in code (e.g. `[overflow-wrap:anywhere]`, `min-h-[44px]` in AuctionProbeCard; `transition-colors duration-150 ease-smooth`), but per the backstop contract no explicit evidence is recordable at verify time — all 12 route to the separate human-verify track.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `frontend/src/pages/Data.tsx` minute case | UI-SPEC minute-K copy (`分钟K同步中·覆盖{N}天` mono/tabular / `分钟K未启用` muted) | ✓ VERIFIED | Data.tsx:492-500; gated on `hasMinuteCap && minuteAuto` + `trading_days > 0`. |
| `frontend/src/components/data/StatCard.tsx` | `hint` accepts JSX (`React.ReactNode`) and renders it | ✓ VERIFIED | StatCard.tsx:99 (`hint: React.ReactNode`), :240 (`{hint}`). |
| `backend/tests/test_minute_sync_verify.py` | Hermetic DATA-01 integration + gate + scope tests | ✓ VERIFIED | 4 test functions, green in re-run. |
| `backend/tests/test_minute_timestamp_convention.py` | `_minute_ts`/`_bucket_minutes` 09:30 convention regression | ✓ VERIFIED | 3 tests, green in re-run. |
| `backend/tests/test_auction_probe.py` | 4 probe states + API GET/POST + honesty regressions | ✓ VERIFIED | 11 tests, green in re-run. |
| `backend/tests/test_open_gap_factor.py` | Fixture values, lookahead guard, filter/persistence proofs | ✓ VERIFIED | 7 tests, green in re-run. |
| `backend/app/services/auction_probe.py` | AuctionProbeStatus / AuctionProbeVerdict / resolve_auction_probe | ✓ VERIFIED | 3 symbols confirmed. |
| `backend/app/indicators/pipeline.py` open_gap | In all 5 registries + Pass-4 compute | ✓ VERIFIED | pipeline.py:66,95,165,304,317,491-498. |
| `preferences.get/set_minute_sync_symbols` | Scope knob, empty=full universe | ✓ VERIFIED | preferences.py:117,122. |
| `MinuteSyncPrefs.minute_sync_symbols` | Settings API round-trip | ✓ VERIFIED | settings.py:320,380,685,693. |
| `daily_pipeline._resolve_minute_symbols` | Honors scope, falls back to universe | ✓ VERIFIED | daily_pipeline.py:656. |
| GET/POST `/api/data/auction-probe[/redetect]` | Verdict + cache bypass | ✓ VERIFIED | data.py:626,641. |
| `ProviderCapabilities.auction` | Capability flag | ✓ VERIFIED | base.py:26. |
| `frontend/.../AuctionProbeCard.tsx` | Full UI-SPEC vocabulary, total mapping | ✓ VERIFIED | 11 UI-SPEC state strings present. |
| `api.ts` / `queryKeys.ts` / `useSharedQueries.ts` | AuctionProbeVerdict + hooks | ✓ VERIFIED | api.ts:2139-2140; queryKeys.ts:130; useSharedQueries.ts:85,94. |
| `frontend/src/pages/Data.tsx` 竞价数据 panel | SectionTitle panel + AuctionProbeCard | ✓ VERIFIED | Data.tsx:903-907. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | -- | ------ | ------- |
| `minuteAuto` + `hasMinuteCap` | minute-K StatCard hint | Data.tsx:190,233,494 → `StatCard hint={...}` | ✓ WIRED | tsc clean; JSX renders UI-SPEC strings. |
| `auction_probe.resolve_auction_probe` | `/api/data/auction-probe` | GET handler calls resolver (data.py:626-638) | ✓ WIRED | 30s TTL cache; POST/redetect bypasses. |
| `/api/data/auction-probe` | `AuctionProbeCard` | `api.auctionProbe` + `useAuctionProbe` + `QK.auctionProbe` | ✓ WIRED | tsc clean; mutation invalidates cache. |
| `resolve_auction_probe` | `custom_sources.provider_has_dataset("auction")` + `ProviderCapabilities.auction` | `_default_sources` enumerates both | ✓ WIRED | No builtin sets `auction=True` → default `not_configured`. |
| `indicators.pipeline` open_gap | strategy filter expressions | `pl.col("open_gap") > 0.03` proven in `test_strategy_filter_consumes_open_gap` | ✓ WIRED | Behavioral test green. |
| `preferences.get_minute_sync_enabled` | `kline_minute` parquet | `run_now` sync_minute → `sync_and_persist_minute` (hermetic test) | ✓ WIRED | Behavioral test green. |
| `_minute_ts` 09:30 anchor | `_bucket_minutes` morning session | `test_minute_timestamp_convention` (3 tests) | ✓ WIRED | Behavioral tests green. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| Minute-K StatCard coverage `{N}` | `s.minute.trading_days` | `/api/data/status` minute payload → `_safe_aggregate_minute` counts real `date=*` partition dirs | Yes — real partition state, never stale | ✓ FLOWING |
| AuctionProbeCard verdict | `probe.data` | `GET /api/data/auction-probe` → `resolve_auction_probe()` → real provider or `not_configured` | Yes — server-authoritative, timestamp-classified | ✓ FLOWING |
| `open_gap` in enriched | `open_gap` column | Pass-4 compute from Pass-1 `prev_close` | Yes — fixture-verified, persisted via `_select_storage_cols` | ✓ FLOWING |

### Behavioral Spot-Checks (Step 7b)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| DATA-01 + DATA-02 + DATA-03 backend suites (re-run) | `cd backend && .venv/bin/python -m pytest tests/test_minute_sync_verify.py tests/test_minute_timestamp_convention.py tests/test_auction_probe.py tests/test_open_gap_factor.py -q` | `25 passed in 1.25s` | ✓ PASS |
| Frontend type contract (re-run) | `cd frontend && npx tsc --noEmit` | exit 0 | ✓ PASS |
| Probe window honesty | `test_all_0930_rows_can_never_produce_available` (in suite) | green | ✓ PASS |
| Fail-closed copy verbatim | `test_fail_closed_detail_matches_approved_copy_verbatim` (in suite) | green | ✓ PASS |

### Probe Execution (Step 7c)

No probe scripts declared or conventional (`scripts/**/tests/probe-*.sh` does not exist). SKIPPED — not a migration/tooling phase; the "probe" is the auction-data feature itself, whose behavioral evidence is the passing `test_auction_probe.py` suite above (re-run green).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| DATA-01 | 16-01 | Enable minute-K sync; 1m bars land with correct 09:30+ timestamps; no daily-lake corruption; Data page shows approved minute-K UI copy | ✓ SATISFIED | Hermetic tests green (re-run); UI copy truth now VERIFIED (Data.tsx:498-500 + StatCard.tsx:99,240). |
| DATA-02 | 16-02 | Governed, unit-tested `open_gap` consumed by strategy filters | ✓ SATISFIED | 7 green tests; registered in all registries; filter consumption proven. |
| DATA-03 | 16-02 | Capability-gated probe with honest fail-closed labels; 09:30 bar never labeled auction data | ✓ SATISFIED | 11 green tests; service/API/UI wired; honesty regressions green. |

No orphaned requirements for Phase 16.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | None | — | No TBD/FIXME/XXX/HACK/PLACEHOLDER markers in any phase-modified file (re-scanned after fix). |

### Prohibitions (honesty contract)

| Statement | Verification | Status |
| --------- | ------------ | ------ |
| No code path labels the 09:30 continuous-trading bar as 集合竞价 data | judgment + test | ✓ VERIFIED — structural guards (`_has_in_window_rows`, `_normalize_auction`, `_bucket_minutes`), total UI mapping in AuctionProbeCard, and regression tests all enforce it. |
| Fail-closed copy matches approved UI-SPEC copy verbatim | test | ✓ VERIFIED — `FAIL_CLOSED_DETAIL` / `NOT_CONFIGURED_DETAIL` constants match UI-SPEC verbatim; enforced server-side by `test_fail_closed_detail_matches_approved_copy_verbatim`. |
| `available` is reachable ONLY from observed `[09:15:00, 09:25:59]` rows | test | ✓ VERIFIED — classification is a pure function of row timestamps; provider labels/capability claims cannot grant availability. |

### Human Verification Still Outstanding (non-gate, carried forward from initial verification)

The must-have gate is closed (13/13). The following human-verification items from the initial report remain for the separate human-verify track and are **not** counted against this phase's status:

1. **Data page 竞价数据 panel browser smoke (all verdict states)** — visual/interaction contract (colors, icons, touch targets, motion) cannot be verified by grep or type-check.
2. **Minute-K StatCard + 同步设置 modal browser smoke** — visual wrap behavior, disabled opacity, reduced-motion are backstop rows requiring visual confirmation.
3. **All 12 plan backstop rows (B1–B12)** — `verification: backstop`; no explicit evidence is recordable at verify time (#1154).

### Gaps Summary

**No blocking gaps remain.** The single blocker from the initial verification — the minute-K StatCard missing the UI-SPEC copy — is closed by fix commit `b41de34`:

- `frontend/src/pages/Data.tsx:498-500` now renders `分钟K同步中·覆盖` + `<span className="font-mono tabular-nums text-secondary">{minuteDays}</span>` + `天` when `hasMinuteCap && minuteAuto && trading_days > 0`, and `<span className="text-muted">分钟K未启用</span>` otherwise — the exact UI-SPEC vocabulary, verbatim.
- `frontend/src/components/data/StatCard.tsx:99` widens `hint` to `React.ReactNode` so the JSX hint is accepted; rendered at line 240.
- Re-run evidence: backend `25 passed in 1.25s`; `npx tsc --noEmit` exit 0.
- All 12 previously-VERIFIED truths regression-checked (presence + wiring) and remain green.

---

_Verified: 2026-08-04_
_Verifier: Claude (gsd-verifier, adversarial goal-backward, re-verification)_
