# Requirements: AthenaQuant v2.1 历史深度与自选联动

**Defined:** 2026-08-05
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## v2.1 Requirements

Requirements for the v2.1 milestone. Each maps to a roadmap phase. Research basis: `.planning/research/v2.1-depth/SUMMARY.md` (data-first ordering; zero new runtime deps; honest provenance + POOL-03 zero-execution + strategy_cache single-as_of integrity as cross-cutting guards).

### 逐日全量存档 (Historical Archive) — Phase 24

- [x] **HIST-01**: Operator can backfill missing historical pool snapshots with a user-triggered batch job that replays `run_all_with_hits` per historical as_of into `screener_results/date={as_of}/` and **never** writes `strategy_cache.json` (the single-as_of pointer must not be polluted by backfill); the job is cancelable, bounded (recent-N or date range), and amortizes warmup in ascending date order.
- [x] **HIST-02**: Every snapshot records honest provenance — a `snapshot_origin` field distinguishing `eod` (scheduled post-close) from `backfill` (recomputed later); existing snapshots without the field read as `eod` (backward compatible).
- [x] **HIST-03**: Archive completeness is visible — a `backfill_needed` gap signal surfaces dates with no snapshot for the selected trading-day range (API + DateNavigator empty-state), and backfill progress is observable (not silent).
- [x] **HIST-04**: Backfill adheres to platform guards — POOL-03 zero execution authority (GET-only surface), no first-request blocking replay, no silent disk writes outside the job's explicit scope; the manual `run_all` historical-as_of cache-pointer pollution (`api/screener.py` writing `strategy_cache` for historical dates) is also fixed.

### 自选股联动 (Watchlist Sync) — Phase 25

- [x] **WATCH-01**: In the pool drill-down (VIP mode), each stock row shows a watchlist star that toggles membership via the existing `/api/watchlist` CRUD; guest rendering is pixel-identical to v2.0 (no watch controls, no watchlist queries issued for guests).
- [x] **WATCH-02**: A "只看自选" filter switch narrows the pool to watchlisted rows (VIP); the strategy-card `total` remains authoritative (filtering never alters totals), applies identically to latest and historical as_of views, and shows an honest empty state when no watchlisted stocks match.
- [x] **WATCH-03**: Watchlist membership is consistent across pages via the shared `QK.watchlist` cache; the join key is the fully-suffixed `symbol` (e.g. `603221.SH`) exact match.
- [x] **WATCH-04** (P2): Operator can batch-add all visible rows to the watchlist (scope = rows within the current display limit), reusing the existing batch-add endpoint.

### 历史竞价图 + 派生列复活 (Auction History Chart) — Phase 26

- [ ] **CHART-01**: Researcher can query per-symbol historical auction aggregates via a read-only `GET /api/kline/auction/history?symbol=&days=` endpoint — last-row (09:25 final call) semantics per trading day; empty lake returns honest 200 `available: false` (never 404); POOL-03-style GET-only, zero execution.
- [ ] **CHART-02**: User can view the auction history chart in the stock drill-down popup — ECharts dual-axis (柱=竞价量, 线=竞价金额), honest empty state + 09:15–09:25 window annotation, zero new npm dependencies, no changes to the user-pending `Watchlist.tsx`.
- [ ] **CHART-03**: The auction lake ingestion path preserves the delegation-volume input columns (canonical schema widened from 4 required to 4 required + 2 optional `auction_unmatched_volume`/`auction_virtual_price`), activating the existing derived `auction_unmatched_amount` branch so the Phase 23 "派生·虚拟成交" UI group becomes live data rather than absent columns; schema/UI maintain the "估算" annotation and stay backward compatible.

### 盘前股池 (Premarket Pool) — Phase 27

- [ ] **PM-01**: A scheduled premarket job (09:26, after the 09:25 call-auction fix) generates a same-day premarket pool preview via `run_all_with_hits(as_of=T)` into an independent store (`premarket_results/date={T}/`) — it never writes `strategy_cache`/`screener_results` (EOD semantics untouched).
- [ ] **PM-02**: The premarket data frame is complete for strategy evaluation — `open_gap` is computed for the today frame (single implementation, no drift from the EOD Pass 4 source); absent real auction columns fail closed to derived factors; ex-dividend-day `open_gap` caliber (raw prev-close vs adjusted) is covered by fixtures.
- [ ] **PM-03**: Premarket auction-column semantics are probe-honest — when today's probe is `available`, real auction columns are injected at read time; otherwise they are absent and the UI shows a `degraded`/window status (never implying real auction data exists premarket).
- [ ] **PM-04**: The frontend presents the premarket view distinctly from EOD — window annotation (pre-open preview vs post-close archive), honest empty state, and DateNavigator continues to list EOD snapshot dates (premarket preview never masquerades as an archived day).

## Out of Scope (v2.1)

| Feature | Reason |
|---------|--------|
| 虚拟成交实时列 (CHART-04) — intraday/premarket live refresh | Blocked on external real-time auction source; [INFERENCE] unverifiable in this environment. Formal defer; gate = custom auction source probe returning in-window virtual unmatched/reference price rows |
| 历史撮合价格曲线 (intraday auction price curve) | Lake stores no price column (`kline_auction` canonical = 4 cols); requires upstream price rows |
| 盘前真实竞价列注入 (PM tier-2) | Gated on today-probe `available` with a real-time source; tier-1 (derived open_gap preview) is the deliverable |
| 历史自选快照 (historical watchlist membership) | Watchlist is not a time series; stars/filter annotate current membership only |
| Automated live broker execution | Platform-wide boundary since v1.0; all `/api/pool/*` + new endpoints stay GET-only zero execution (POOL-03) |
| External database or message queue | Architecture constraint since v1.0 |
| New npm/pip runtime dependencies | Zero new deps: ECharts already in-tree; all backend uses existing seams (`run_all_with_hits`, `pool_snapshot`, `attach_auction_columns`, `/api/watchlist`) |

## Traceability

Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| HIST-01 | Phase 24 | Complete |
| HIST-02 | Phase 24 | Complete |
| HIST-03 | Phase 24 | Complete |
| HIST-04 | Phase 24 | Complete |
| WATCH-01 | Phase 25 | Complete |
| WATCH-02 | Phase 25 | Complete |
| WATCH-03 | Phase 25 | Complete |
| WATCH-04 | Phase 25 | Complete (P2) |
| CHART-01 | Phase 26 | Open |
| CHART-02 | Phase 26 | Open |
| CHART-03 | Phase 26 | Open |
| PM-01 | Phase 27 | Open |
| PM-02 | Phase 27 | Open |
| PM-03 | Phase 27 | Open |
| PM-04 | Phase 27 | Open |

**Coverage:**

- v2.1 requirements: 15 total (11 P1, 4 P2)
- Mapped to phases: 15 (roadmap created — Phases 24-27)
- Unmapped: 0

---
*Requirements defined: 2026-08-05*
*Last updated: 2026-08-05 — v2.1 milestone started; research synthesized (4 domains → 4 phases)*
