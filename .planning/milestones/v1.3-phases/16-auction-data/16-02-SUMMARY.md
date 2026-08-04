---
phase: 16-auction-data
plan: 2
subsystem: api
tags: [auction-probe, open-gap, polars, indicators, fail-closed, data-lake, fastapi, react]
requires: []
provides:
  - Server-authoritative auction-data probe verdict (not_configured/available/fail_closed/error) from app.services.auction_probe, exposed via GET/POST /api/data/auction-probe[/redetect]
  - Governed persisted open_gap column (open / prev_close − 1) in the indicators pipeline, consumable by strategy filters and shown in the enriched schema table with its Chinese label
  - Custom-source "auction" dataset whitelist + GenericHTTPProvider.get_auction (09:15–09:25 window filter) + ProviderCapabilities.auction capability flag
  - Data-page 竞价数据 panel (AuctionProbeCard) rendering the UI-SPEC honest fail-closed vocabulary; the 09:30 continuous bar is never labeled 集合竞价 data
affects: [17-strategy-family, 18-pool-hub, DATA-02, DATA-03]
actuals:
  tokens: 8200
  tasks: 3
  commits: 3
tech-stack:
  added: []
  patterns:
    - Server-authoritative probe verdict with injectable source_resolver/fetcher so hermetic tests force every state without network
    - Fail-closed timestamp classification: available ONLY from observed [09:15:00, 09:25:59] rows; 09:30+ bars structurally cannot be available
    - Governed factor registration across every column registry (storage / columns / category / deps / all) plus Pass-4 compute using Pass-1 prev_close
    - Int32 cast before wall-clock minute arithmetic (dt.hour() returns Int8 — overflow bug caught and fixed)
key-files:
  created:
    - backend/app/services/auction_probe.py
    - backend/tests/test_auction_probe.py
    - backend/tests/test_open_gap_factor.py
    - frontend/src/components/data/AuctionProbeCard.tsx
  modified:
    - backend/app/indicators/pipeline.py
    - backend/app/api/data.py
    - backend/app/data_providers/base.py
    - backend/app/data_providers/custom/config.py
    - backend/app/data_providers/custom/loader.py
    - backend/app/data_providers/custom/provider.py
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/lib/useSharedQueries.ts
    - frontend/src/pages/Data.tsx
key-decisions:
  - "source_resolver yields provider instances (not names) so hermetic tests inject fake providers without resolving real ones; the default resolver enumerates custom auction-dataset sources + builtin providers with capabilities.auction"
  - "open_gap is computed with Pass-1 prev_close (close.shift(1).over('symbol')); open is never shifted — no cross-day lookahead (T-16-03)"
  - "available classification uses minute-level [09:15, 09:25] bounds which match [09:15:00, 09:25:59] window semantics exactly"
patterns-established:
  - "AuctionProbeVerdict frozen dataclass with .to_dict() + StrEnum status; the frontend maps only server status values and never synthesizes a verdict"
  - "Error detail is bounded ([:200]) so provider exception messages cannot leak unboundedly (T-16-05)"
requirements-completed: [DATA-02, DATA-03]
coverage:
  - id: D1
    description: "Auction-probe verdict service: not_configured with no source; available only from in-window [09:15:00,09:25:59] rows; fail_closed for 09:30+ only or empty rows; error with bounded detail; window always '09:15-09:25' and fallback always 'open_gap'"
    requirement: DATA-03
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_probe.py#test_no_source_is_not_configured"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_probe.py#test_in_window_rows_are_available"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_probe.py#test_0930_only_rows_are_fail_closed_never_available"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_probe.py#test_raising_provider_is_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /api/data/auction-probe returns 200 verdict JSON and POST /api/data/auction-probe/redetect bypasses the 30s TTL cache to return a fresh verdict"
    requirement: DATA-03
    verification:
      - kind: integration
        ref: "backend/tests/test_auction_probe.py#test_get_auction_probe_returns_verdict_json"
        status: pass
      - kind: integration
        ref: "backend/tests/test_auction_probe.py#test_redetect_bypasses_cache"
        status: pass
    human_judgment: false
  - id: D3
    description: "Honesty regression: window/fallback fixed for every status; all-09:30 rows can never produce available; fail-closed and not-configured detail strings match the approved UI-SPEC copy verbatim server-side"
    requirement: DATA-03
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_probe.py#test_verdict_window_and_fallback_are_fixed_for_every_status"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_probe.py#test_all_0930_rows_can_never_produce_available"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_probe.py#test_fail_closed_detail_matches_approved_copy_verbatim"
        status: pass
    human_judgment: false
  - id: D4
    description: "open_gap governed column: values on a known 2-symbol x 3-day fixture (day2=0.03, day3=-0.0667), null on the first day, no cross-day lookahead when day2 open is mutated, registered in all column registries, consumed by a strategy filter expression, and persisted through the storage path"
    requirement: DATA-02
    verification:
      - kind: unit
        ref: "backend/tests/test_open_gap_factor.py#test_open_gap_values_on_known_fixture"
        status: pass
      - kind: unit
        ref: "backend/tests/test_open_gap_factor.py#test_first_day_open_gap_is_null"
        status: pass
      - kind: unit
        ref: "backend/tests/test_open_gap_factor.py#test_mutating_day2_open_only_changes_day2"
        status: pass
      - kind: unit
        ref: "backend/tests/test_open_gap_factor.py#test_strategy_filter_consumes_open_gap"
        status: pass
      - kind: unit
        ref: "backend/tests/test_open_gap_factor.py#test_open_gap_persists_via_storage_path"
        status: pass
    human_judgment: false
  - id: D5
    description: "Data page 竞价数据 panel renders the approved UI-SPEC vocabulary (竞价数据未配置 / 竞价数据可用 / 未接入竞价数据（已退化派生因子） / 竞价数据探测失败… role=alert / 竞价数据探测中… role=status with 重新探测 disabled) and the available treatment is reachable ONLY from server status === 'available'"
    requirement: DATA-03
    verification:
      - kind: automated_ui
        ref: "frontend npx tsc --noEmit (type-level contract of AuctionProbeCard + api/query hooks)"
        status: pass
    human_judgment: true
    rationale: "The plan's done criteria call for a Data-page browser smoke of the panel visuals (accent/warning/danger treatments, spinner, touch targets). This headless executor ran the automated type-check and backend tests only; a browser smoke is required to sign off the visual/interaction contract."
duration: 20min
completed: 2026-08-04
status: complete
---

# Phase 16 Plan 2: Governed open-gap factor + auction-data probe & honest fail-closed labels Summary

**Server-authoritative auction-data probe (not_configured / available / fail_closed / error) wired service → GET/POST /api/data/auction-probe → Data-page 竞价数据 panel with the approved honest vocabulary, plus a governed persisted `open_gap` column (`open / prev_close − 1`) that strategy filters can consume — and regression-locked proof that a 09:30 continuous bar is never labeled 集合竞价 data**

## Performance

- **Duration:** 20 min
- **Started:** 2026-08-04T12:35:00Z
- **Completed:** 2026-08-04T12:54:24Z
- **Tasks:** 3
- **Files modified:** 14

## Accomplishments

- **Auction probe service (`backend/app/services/auction_probe.py`)** — `AuctionProbeStatus` StrEnum, frozen `AuctionProbeVerdict` (window `"09:15-09:25"`, fallback `"open_gap"`), and `resolve_auction_probe(*, source_resolver, fetcher)` whose default resolver enumerates custom `auction`-dataset sources plus builtin providers declaring `capabilities.auction`. Classification is strictly timestamp-based: `available` only from observed `[09:15:00, 09:25:59]` rows; all-`>=09:30` or empty input fails closed with the verbatim approved copy; exceptions become `error` with a bounded ([:200]) detail.
- **Provider surface** — `ProviderCapabilities.auction: bool = False` (backward compatible), `"auction"` added to the custom-source whitelist (`config.py` load + `loader.py` sanitize), and `GenericHTTPProvider.get_auction(symbols, trade_date)` that fetches via the existing `_request_rows`/`_mapped_frame` seam, filters to the 09:15–09:25 window, and returns canonical `symbol, datetime, auction_volume, auction_amount`.
- **API** — `GET /api/data/auction-probe` (30s TTL in-process cache) and `POST /api/data/auction-probe/redetect` (bypasses cache) added to the existing `/api/data` router.
- **Data page** — new `AuctionProbeCard` renders only server verdicts with the UI-SPEC vocabulary: `竞价数据未配置` (muted, no probe action), `竞价数据可用` (accent + CheckCircle2, ONLY for `status === "available"`), `未接入竞价数据（已退化派生因子）` (warning + AlertTriangle + body), `竞价数据探测失败：{message}。已按未接入处理，当前使用派生开盘涨幅因子。请重试。` (danger, `role="alert"`), and a transient `竞价数据探测中…` (Loader2, `role="status"`, 重新探测 disabled). Mounted in a new `竞价数据` SectionTitle panel on `/data` without changing the existing shell or panel order.
- **Governed `open_gap` factor (DATA-02)** — registered in `ENRICHED_STORAGE_COLS`, `ENRICHED_COLUMNS` (`开盘涨幅 (open/prev_close−1, 小数)`), `ENRICHED_COLUMNS_BY_CATEGORY["basic"]`, `_INDICATOR_DEPS`, and `_ALL_INDICATOR_COLS`; computed in Pass 4 as `when(prev_close > 0).then(open / prev_close − 1)` using Pass-1 `prev_close` (never shifting `open`); persisted via the existing `_select_storage_cols` path and surfaced in `/api/data/schema/enriched` with its Chinese label.
- **Tests** — `test_auction_probe.py` (11 tests: 4 states + API GET/POST + honesty regressions) and `test_open_gap_factor.py` (7 tests: fixture values, first-day null, lookahead guard, strategy-filter consumption, persistence).

## Task Commits

Each task was committed atomically:

1. **Task 1: Auction-probe verdict end-to-end — service -> API -> Data-page 竞价数据 panel** - `81cc323` (feat)
2. **Task 2: open_gap governed column in the indicators pipeline + fixture tests** - `0862de8` (feat)
3. **Task 3: Honest-label regression — 09:30 bar never 集合竞价; fail-closed copy verbatim** - `d25a3a6` (test)

**Plan metadata:** (final metadata commit follows in the state-update step)

## Files Created/Modified

- `backend/app/services/auction_probe.py` - New: probe status enum, frozen verdict, `resolve_auction_probe` with injectable resolver/fetcher, strict timestamp classification
- `backend/app/api/data.py` - Added `GET /api/data/auction-probe` + `POST /api/data/auction-probe/redetect` with 30s TTL cache
- `backend/app/data_providers/base.py` - Added `ProviderCapabilities.auction: bool = False`
- `backend/app/data_providers/custom/config.py` - Added `"auction"` to `DatasetName` and load_config whitelist
- `backend/app/data_providers/custom/loader.py` - Added `"auction"` to `_sanitize_for_yaml` whitelist
- `backend/app/data_providers/custom/provider.py` - Added `get_auction` + `_normalize_auction` (09:15–09:25 window filter)
- `backend/app/indicators/pipeline.py` - Governed `open_gap` in all five registries + Pass-4 computation
- `backend/tests/test_auction_probe.py` - New: 4 probe states, API GET/POST, honesty regressions
- `backend/tests/test_open_gap_factor.py` - New: fixture values, lookahead guard, filter/persistence proofs
- `frontend/src/components/data/AuctionProbeCard.tsx` - New: total, auditable status mapping per UI-SPEC
- `frontend/src/lib/api.ts` - `AuctionProbeVerdict` interface + `auctionProbe`/`redetectAuctionProbe`
- `frontend/src/lib/queryKeys.ts` - `QK.auctionProbe`
- `frontend/src/lib/useSharedQueries.ts` - `useAuctionProbe` (30s staleTime) + `useRedetectAuctionProbe` mutation
- `frontend/src/pages/Data.tsx` - New `竞价数据` SectionTitle panel rendering `<AuctionProbeCard/>`

## Decisions Made

- `source_resolver` yields provider **instances** rather than names so hermetic tests can inject `FakeAuctionProvider` without a real provider registry; the production default enumerates custom sources + builtin `capabilities.auction` providers.
- `open_gap` reuses Pass-1 `prev_close` (`close.shift(1).over("symbol")`); `open` is never shifted, so the factor is same-day-open over prior-day-close by construction and cannot leak cross-day lookahead into Phase 17 strategies (T-16-03).
- The `available` verdict is a pure function of observed row timestamps within `[09:15:00, 09:25:59]`; no provider label, capability claim, or client state can grant it (T-16-01/T-16-02).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Polars Int8 overflow in wall-clock minute arithmetic**
- **Found during:** Task 1 (auction-probe service smoke test)
- **Issue:** `datetime.dt.hour()` returns an Int8 series; `9 * 60 + 16 = 556` overflowed to `44`, so an in-window 09:16 row was misclassified as `fail_closed`.
- **Fix:** Cast `.dt.hour()`/`.dt.minute()` to `pl.Int32` before arithmetic in both `auction_probe._has_in_window_rows` and `GenericHTTPProvider._normalize_auction`.
- **Files modified:** `backend/app/services/auction_probe.py`, `backend/app/data_providers/custom/provider.py`
- **Verification:** 09:16 → `available`, 09:25:59 → `available`, 09:14:59/09:26:00/09:31 → `fail_closed`; full test suite green.
- **Committed in:** `81cc323` (task 1 commit)

**2. [Rule 1 - Bug] `open_gap > 0.03` float64 boundary selects day2 rows**
- **Found during:** Task 2 (strategy-consumption proof test)
- **Issue:** `10.30 / 10.00 - 1` is `0.030000000000000071` in float64, so `pl.col("open_gap") > 0.03` legitimately matched the day2 rows (2 rows), contradicting a naive "empty" expectation.
- **Fix:** Asserted the actual honest subset (both symbols' day2 rows survive; day1 None and day3 negatives are excluded) and added a `> 0` sanity assertion; documented the float64 boundary in the test.
- **Files modified:** `backend/tests/test_open_gap_factor.py`
- **Verification:** 7/7 open_gap tests green.
- **Committed in:** `0862de8` (task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes were correctness requirements for the delivered tests/classification. No scope creep.

## Issues Encountered

- Two `edit` insertions initially landed inside adjacent code (the `/status` dict in `api/data.py` and `test_raising_provider_is_error` in `test_auction_probe.py`); both were repaired by re-reading the region and issuing a corrected swap. Final files verified by their test suites.

## Unrun Verification

- **Data-page browser smoke** (plan-level): the 竞价数据 panel visual/interaction contract (accent/warning/danger treatments, spinner, 44px touch targets, `prefers-reduced-motion`) and the minute-K coverage copy were not exercised in a real browser by this headless executor. Automated coverage is `npx tsc --noEmit` + the backend suites; a visual smoke is tracked via coverage D5 and the broken-windows ledger.
- **Plan backstops** (UI-SPEC "backstop" rows): all are visual-only checks (wrap behavior, row-height reservation, touch targets, reduced-motion, plural-free copy). Not run headlessly; surfaced via D5 human judgment.

## User Setup Required

None - no external service configuration required. The probe's default path is `not_configured`/`fail_closed` until an operator configures a custom source with an `auction` dataset (or a builtin provider declares `capabilities.auction`).

## Next Phase Readiness

- DATA-02 is ready for Phase 17: `open_gap` is a governed, persisted, unit-tested column that strategy filter expressions consume directly (`pl.col("open_gap") > threshold`), matching the `strong_open.py` filter pattern.
- DATA-03 gives Phase 17/18 an honest availability gate: strategies must not claim true 集合竞价 match data unless the probe returns `available`; the platform fails closed to the derived open-gap baseline and the 09:30 bar is never labeled auction data.
- When a real auction-capable source is added later, only a custom YAML `auction` dataset (or `capabilities.auction=True`) needs to be configured — no code change.

---
*Phase: 16-auction-data*
*Completed: 2026-08-04*

## Self-Check: PASSED

- Created files verified: `backend/app/services/auction_probe.py`, `backend/tests/test_auction_probe.py`, `backend/tests/test_open_gap_factor.py`, `frontend/src/components/data/AuctionProbeCard.tsx`, `.planning/phases/16-auction-data/16-02-SUMMARY.md`
- Commits verified: `81cc323`, `0862de8`, `d25a3a6`
