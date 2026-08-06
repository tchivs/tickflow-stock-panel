# Requirements: AthenaQuant v2.2 决策闭环与历史纵深

**Defined:** 2026-08-06
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## v2.2 Requirements

Requirements for the v2.2 milestone. Each maps to a roadmap phase. Research basis: `.planning/research/v2.2-decision-loop/SUMMARY.md` (data-first ordering; zero new runtime deps; honest provenance + POOL-03 zero-execution + strategy_cache single-as_of integrity as cross-cutting guards).

### 概念板块 PIT 历史映射 (Concept PIT) — Phase 28

- [x] **CONCEPT-01**: A forward daily concept archive — the EOD hook (`_pool_eod_persist` tail) captures the current `ext_gn_ths` concept snapshot into a platform-owned root `data/ext_history/gn_ths/date={as_of}/part.parquet` (atomic write, strict date validation, mirrors `screener_results`/`premarket_results` precedent); capture failure never blocks the pool snapshot; existing ~247 pre-launch historical dates are **not** backfilled (upstream has no historical endpoint — forward-only archive, honest `current_snapshot` fallback, never fabricated).
- [x] **CONCEPT-02**: The concept join in the historical pool view is upgraded to as-of read-side resolution — `_build_concept_map` gains an `as_of` parameter, prefers the `date==as_of` partition, and falls back to the current ext snapshot with the `current_snapshot` attribution when the partition is missing.
- [x] **CONCEPT-03**: Concept attribution is a three-state machine — `as_of_snapshot` (date partition present) / `current_snapshot` (fallback) / `unavailable` (no concept data at all); rows are never mixed by attribution within a response, partitions are never merged/stitched, and backfill forgery is structurally impossible.
- [x] **CONCEPT-04** (P2): The frontend renders the attribution state visibly — a badge/tooltip when `current_snapshot`/`unavailable` (never when `as_of_snapshot`), showing the mapping effective date; no changes to the user-pending `Watchlist.tsx`.
- [x] **CONCEPT-05**: The new write path is guarded — POOL-03-style AST guard scoped per module: `concept_history` may only write `data/ext_history/` (never `strategy_cache`/`screener_results`/`premarket_results`/`ext_data`), mirroring the `test_pool_hub` E-guard pattern.
- [ ] **CONCEPT-06**: The same as-of resolution seam is extended to the other consumers — market overview `_dimension_rank` (historical recap concept board) and `rps_rotation._load_concept_map_df` (RPS matrix) — eliminating the today-unlabeled drift; industry archive (`ext_hy_ths`) is archived alongside concept.
- [x] **CONCEPT-07** (P2): Each archived partition carries a provenance manifest (`source_url`/`captured_at`/`fetched_at`) and the API/UI exposes the mapping effective date.

### 竞价策略历史验证 (Auction Strategy Validation) — Phase 29

- [ ] **BT-01**: A read-only `GET /api/research/auction/validation` signal-quality report with an honest data gate — `kline_auction` empty or probe unavailable returns 200 `{data_gate: "empty", coverage: 0, strategies: [], probe}` (never 404/500); `data_gate: "available"` when enabled dates exist.
- [ ] **BT-02**: A vectorized `attach_auction_columns_range` injection primitive (multi-date) mirroring `attach_auction_columns` probe×partition dual gate with PIT-safe denominators (`volume.shift(1).rolling_mean(5).over("symbol")`); dates without partitions are never null-as-present; does not touch the governed backtest panel seam.
- [ ] **BT-03**: Per-strategy report rows `{branch: real|derived|eod, n_dates, n_hits, coverage, forward_stats, per_date, data_gate}` — auction strategies that require real columns report honestly when the lake is empty (`n_dates == 0`, never downgraded to derived); the 5 derived/EOD-proxy strategies still get validated on the enriched history with explicit branch labeling.
- [ ] **BT-04**: Forward-outcome semantics are locked — entry = T open; `next_day_open_ret = open_{T+1}/open_T − 1`; `next_day_close_ret = close_{T+1}/open_T − 1`; `open_gap_outcome = open_{T+1}/close_T − 1`; missing outcome days are counted in `n_missing_outcomes`, never 0-filled or forward-filled (no lookahead, no silent fill).
- [ ] **BT-05**: Branch labels are mutually exclusive — real/derived/eod never mixed within a strategy's stats; each branch computed and labeled independently.
- [ ] **BT-06**: The validation surface is zero-execution + zero-dependency — GET-only, AST-guarded (mirror `test_pool_hub` E3), never writes `strategy_cache`/`screener_results`, never touches the frozen-panel scope/checksum.

### 盘前监控告警 (Premarket Monitoring) — Phase 30

- [ ] **MON-01**: A new `preopen` monitor rule type with a validated field whitelist (`open_gap`/`auction_volume`/`auction_amount`/`auction_volume_ratio`/`auction_unmatched_amount`, `op=truth` supported; EOD-only fields `change_pct`/`close`/`vol_ratio_5d`/`amount` banned); pre-open frame semantics verified at implementation (`compute_enriched_today` + quote_service preopen flush) before shipping alerts.
- [ ] **MON-02**: `evaluate_premarket(payload)` evaluates the premarket preview payload in isolation — reconstructs the DataFrame from `payload["results"]` rows with `change_pct` set to `None` (honest missing column), never touching `_strategy_pools`/`_latest_strategy_results` (no pool-baseline pollution of the 09:30 intraday first round).
- [ ] **MON-03**: Evaluation is wired to the tail of the 09:26 `_premarket_pool_preview` job (same `_run_tracked` single-flight, after persist) — no new job race; reuses the existing operational → SSE → webhook delivery sequence.
- [ ] **MON-04**: Honest provisional/degraded/probe annotation — events carry `provisional: true`/`degraded`/`probe`; when `degraded` or probe non-available, auction-dependent rules fail closed (0 alerts, never 0-fill silence — the degraded state is surfaced in the alert record/UI); preview `available: false` → no evaluation, no alerts.
- [ ] **MON-05**: Zero-execution + store isolation — the preopen evaluate module is AST-guarded (execution-family token absent; read-only on `premarket_results`), never writes `strategy_cache`/`screener_results`.
- [ ] **MON-06**: Guest surfaces stay masked — preopen alert records rendered through the existing guest masking path (`mask_guest_hub` semantics); guests see no auction values.
- [ ] **MON-07** (P2): `/api/monitor-rules/options` exposes the `preopen` type + field whitelist; the frontend rule editor/alerts page renders the new type (no changes to `Watchlist.tsx`).

### 竞价复盘 (Auction Recap) — Phase 31

- [ ] **REV-01**: A deterministic auction-recap assembly service (`auction_recap.py`) builds the recap blocks from frozen assets only — `load_premarket_snapshot` + `attach_auction_columns` + enriched `open_gap` — read-only, AST-guarded, never triggers `run_all_with_hits`; historical as_of uses partition-existence as the primary gate (probe dual-gate applies to today only).
- [ ] **REV-02**: Honest annotation/degradation — `data_completeness` enum `{full, no_auction_lake, no_premarket_preview, pre_eod, partial}`; missing blocks are omitted with explicit note; the 09:30+ continuous bar is never labeled auction data; the panel carries a "确定性数据，非 AI 生成" marker; pre-EOD runs (before the 15:30 auction sync) are labeled `pre_eod` and never imply auction data exists.
- [ ] **REV-03**: A premarket signal-quality block — per-strategy `{n, avg open_gap, avg change_pct, 开盘兑现率, 收盘兑现率, 收阳率}` driven by strategies that actually have rows in the premarket preview (never hardcoded strategy lists); joins preview against EOD enriched `change_pct` caliber.
- [ ] **REV-04**: Recap integration — the deterministic panel is appended as a delta before the `done` event in `recap_market_stream` (same stream → SSE/archive/Feishu all receive it, zero frontend change); optional AI commentary defaults OFF and, when enabled, may only cite the panel's slice values with explicit gaps; `_build_user_prompt` stays backward compatible (optional param, default None); the default recap schedule moves to 15:40 (after 15:30 auction sync + 15:35 pool persist) so the full blocks light up.
- [ ] **REV-05** (P2): A standalone read-only `GET /api/market-recap/auction` endpoint for the deterministic panel (independent of the AI recap stream).

## Out of Scope (v2.2)

| Feature | Reason |
|---------|--------|
| BT-07 全量竞价回测（frozen-panel 竞价列 + minute_confirm_fn 接入） | Explicitly deferred to v2.3+ — needs `kline_auction` lake with sufficient historical partitions (currently 0) |
| 真实竞价活跃度 / 真列验证（BT real branch, REV real_auction_activity） | Gated on `kline_auction` partitions + probe `available`; empty lake → BT `data_gate:"empty"`, REV block honestly omitted — conditional delivery |
| CONCEPT 历史回填（~247 pre-launch dates） | Upstream `concepts.json` has no historical endpoint [INFERENCE]; forward-only archive; pre-launch dates fall back to `current_snapshot` (never fabricated) |
| 盘前预览基线 vs 实际开盘对比、盘前异动告警直喂复盘 | Cross-domain optional links — v2.2 later or v2.3 |
| 复用 type=strategy 指向盘前行（MON option B） | Rejected — `_strategy_pools` baseline pollution causes spurious 09:30 dropped/new_entry alerts |
| 独立归档层 / 查询时回放（CONCEPT/BT） | Double source of truth / reverse of POOL-06; rejected |
| 自动刷新 `ext_gn_ths` 当前快照（CONCEPT OQ-1 选项 a） | Keeps existing manual-refresh ext design; concept archive writes only platform-owned `ext_history/` |
| Automated live broker execution | Platform-wide boundary since v1.0; all new endpoints stay GET-only / read-only (POOL-03) |
| External database or message queue | Architecture constraint since v1.0 |
| New npm/pip runtime dependencies | Zero new deps: all reuse existing stack (ext_presets, write_ext_parquet, Polars partitions, monitor rule engine, recap stream) |

## Traceability

Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONCEPT-01 | Phase 28 | Open |
| CONCEPT-02 | Phase 28 | Open |
| CONCEPT-03 | Phase 28 | Open |
| CONCEPT-04 | Phase 28 | Open (P2) |
| CONCEPT-05 | Phase 28 | Open |
| CONCEPT-06 | Phase 28 | Open |
| CONCEPT-07 | Phase 28 | Open (P2) |
| BT-01 | Phase 29 | Open |
| BT-02 | Phase 29 | Open |
| BT-03 | Phase 29 | Open |
| BT-04 | Phase 29 | Open |
| BT-05 | Phase 29 | Open |
| BT-06 | Phase 29 | Open |
| MON-01 | Phase 30 | Open |
| MON-02 | Phase 30 | Open |
| MON-03 | Phase 30 | Open |
| MON-04 | Phase 30 | Open |
| MON-05 | Phase 30 | Open |
| MON-06 | Phase 30 | Open |
| MON-07 | Phase 30 | Open (P2) |
| REV-01 | Phase 31 | Open |
| REV-02 | Phase 31 | Open |
| REV-03 | Phase 31 | Open |
| REV-04 | Phase 31 | Open |
| REV-05 | Phase 31 | Open (P2) |

**Coverage:**

- v2.2 requirements: 25 total (21 P1, 4 P2)
- Mapped to phases: 25 (roadmap created — Phases 28-31)
- Unmapped: 0

---
*Requirements defined: 2026-08-06*
*Last updated: 2026-08-06 — v2.2 milestone started; research synthesized (4 domains → 4 phases)*
