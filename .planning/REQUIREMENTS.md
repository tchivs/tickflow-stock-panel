# Requirements: AthenaQuant v1.3 竞价选股引擎

**Defined:** 2026-08-04
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## v1 Requirements

Requirements for the v1.3 milestone. Each maps to a roadmap phase.

### 竞价数据层 (Auction Data)

- [x] **DATA-01**: Researcher can enable minute-K sync and verify 1m bars land in `kline_minute` Parquet with correct 09:30+ timestamps and no corruption of the existing daily-K lake.
- [x] **DATA-02**: Researcher can compute and persist an 开盘涨幅 (open-gap) factor — `open / prev_close − 1` — as a governed, unit-tested column consumed by strategy filters (derivable today from daily-K enriched).
- [x] **DATA-03**: Platform probes for true 集合竞价 match data (9:15–9:25 竞价量/金额/虚拟成交) behind a capability gate; when unavailable, the feature fails closed to derived open-gap factors and never labels the 09:30 continuous-trading bar as auction data (P2).

### 竞价策略族 (Auction Strategy Family)

- [x] **STRAT-01**: Researcher can run at least 3 auction strategies (竞价多头, 盘前强势量化, 早盘之星) authored as builtin strategy files in `strategy/builtin/`, auto-discovered by `StrategyEngine`, each with honest first-principles factor definitions (reference names are product labels, not public specs).
- [x] **STRAT-02**: Auction strategies expose per-stock factor-hit tagging so a results row reports which strategies hit it (关联因子), feeding cross-resonance.
- [x] **STRAT-03**: No third strategy registration track is introduced — auction strategies land in `strategy/builtin/` only, and the strategies API dedups against `PRESET_STRATEGIES` (P2).

### 股池 Hub (Pool Hub)

- [x] **POOL-01**: User can open a pool hub showing strategy cards with当日 per-strategy pool counts, and drill into each strategy's stock list (code, 开盘涨幅, 涨跌幅, 概念板块, 关联因子) backed by `screener_results/` persistence with a single as_of source of truth.
- [x] **POOL-02**: User can filter the pool by 概念 and highlight 交叉共振 — stocks hit by multiple auction strategies.
- [x] **POOL-03**: Pool data is a research-only projection; no execution authority or order routing exists anywhere in the pool feature (P2).

### 游客/VIP 脱敏 (Guest Access)

- [ ] **GUEST-01**: Non-VIP (guest) sessions see only 涨跌幅 and 概念板块, with stock code/name masked (`******`) applied server-authoritatively at the API DTO boundary; VIP sessions receive明文. No client-side masking is trusted.
- [ ] **GUEST-02**: Guest masking does not degrade the strategy engine's own internal correctness — masked fields are display-only, underlying factor computation remains unmasked (P2).

## v2 Requirements (Future)

Deferred to later releases. Tracked but not in current roadmap.

### Auction Data

- **DATA-04**: True 集合竞价 match data columns (竞价量/金额/虚拟成交) become first-class when a reliable source is confirmed.
- **DATA-05**: Pre-open (before 09:30) pool availability when an auction data source supports real-time pre-market evaluation.

### Strategy

- **STRAT-04**: Additional auction strategies beyond the core 3 (竞价阿尔法, 极速抢筹, T+1闪电, 竞价全面策略, 金色两点半) as factor definitions are derived and validated.
- **STRAT-05**: 早盘之星/盘前策略 intraday confirmation — strategies that re-evaluate during 09:30–10:00 based on minute-K confirmation.

### Pool Hub

- **POOL-04**: 日期导航 (per-trading-day historical pool browsing) — deferred; as_of single-date view ships first.
- **POOL-05**: Pool watchlist integration and alerting from pool membership changes.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automated live broker execution | Platform-wide boundary since v1.0; pool feature carries zero execution authority (POOL-03) |
| Replicating proprietary strategy recipes verbatim (陈星量化 etc.) | No public spec; strategies are first-principles and honestly named |
| Client-side guest masking | Bypassable; masking is server-authoritative at the DTO boundary |
| Adding a third strategy registration track | Causes drift; builtin dir + preset dedup only (STRAT-03) |
| External database or message queue | Architecture constraint since v1.0 |
| Storing full intraday tick data | Minute-K buckets suffice; full-tick is a different cost class |

## Traceability

Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 16 (竞价数据层) | Complete |
| DATA-02 | Phase 16 (竞价数据层) | Complete |
| DATA-03 | Phase 16 (竞价数据层) | Complete |
| STRAT-01 | Phase 17 (竞价策略族) | Complete |
| STRAT-02 | Phase 17 (竞价策略族) | Complete |
| STRAT-03 | Phase 17 (竞价策略族) | Complete |
| POOL-01 | Phase 18 (股池 Hub) | Complete |
| POOL-02 | Phase 18 (股池 Hub) | Complete |
| POOL-03 | Phase 18 (股池 Hub) | Complete |
| GUEST-01 | Phase 19 (游客/VIP 脱敏 + 前端) | Pending |
| GUEST-02 | Phase 19 (游客/VIP 脱敏 + 前端) | Pending |

**Coverage:**

- v1 requirements: 11 total (9 P1, 2 P2)
- Mapped to phases: 11
- Unmapped: 0 ✓

---
*Requirements defined: 2026-08-04*
*Last updated: 2026-08-04 — Phase 16 complete (DATA-01..03)*
