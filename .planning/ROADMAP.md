# Roadmap: AthenaQuant

## Milestones

### v1.0 MVP — shipped 2026-07-27

Five phases delivered the governed data and portfolio loop, deterministic decision safety, reproducible factor and strategy research, evidence-grounded AI analysis, controlled advanced workflows, and independently activatable Shadow, Thesis, and Forecast modules.

Archive:

- [v1.0 roadmap](./milestones/v1.0-ROADMAP.md)
- [v1.0 requirements](./milestones/v1.0-REQUIREMENTS.md)
- [v1.0 milestone audit](./milestones/v1.0-MILESTONE-AUDIT.md)
- [v1.0 phase artifacts](./milestones/v1.0-phases/)

---

### v1.1 Operational Hardening — shipped 2026-07-29

Four phases hardened the shipped MVP: reproducible release evidence, validation hygiene (zero application-code warnings), verified optional-model supply path, and visual regression baselines.

Archive:

- [v1.1 roadmap](./milestones/v1.1-ROADMAP.md)
- [v1.1 requirements](./milestones/v1.1-REQUIREMENTS.md)

---

### v1.2 End-to-End Factor Portfolio Pipeline — shipped 2026-08-03

Six phases extended the research platform from single-factor evaluation into an auditable factor → portfolio → risk → walk-forward → rebalance-suggestion pipeline with zero execution authority.

Archive:

- [v1.2 roadmap](./milestones/v1.2-ROADMAP.md)
- [v1.2 phase artifacts](./milestones/v1.2-phases/)

---

### v1.3 竞价选股引擎 — planning

Four phases add 集合竞价-driven quantitative stock selection to the shipped screener engine: an auction data layer, an auction strategy family, a pool hub with cross-resonance, and guest/VIP masking plus the frontend pool page — all research-only, zero execution authority.

## Phases

**Phase Numbering:**

- v1.2 ended at Phase 15; v1.3 continues at Phase 16 (`phase_naming: sequential`)

- [ ] **Phase 16: 竞价数据层 (Auction Data)** - Enable minute-K sync, land the governed open-gap factor, and probe true 集合竞价 match data behind a capability gate — DATA-01..03
- [ ] **Phase 17: 竞价策略族 (Auction Strategy Family)** - Author ≥3 auction strategies (竞价多头/盘前强势量化/早盘之星) as builtin strategy files with factor-hit tagging — STRAT-01..03
- [ ] **Phase 18: 股池 Hub (Pool Hub)** - Strategy cards with pool counts, drill-down stock lists, concept filter, 交叉共振 multi-hit highlight — POOL-01..03
- [ ] **Phase 19: 游客/VIP 脱敏 + 前端 (Guest Access & Frontend)** - Server-authoritative guest masking, VIP plaintext, frontend pool page — GUEST-01..02

## Phase Details

### Phase 16: 竞价数据层 (Auction Data)

**Goal**: Researchers can sync minute-K without corrupting the daily lake, compute and persist a governed open-gap factor, and know — via an honest capability probe — whether true 9:15–9:25 集合竞价 match data is available before committing strategy breadth.
**Depends on**: v1.2 completion (Phase 15)
**Requirements**: DATA-01, DATA-02, DATA-03
**Success Criteria** (what must be TRUE):

  1. Researcher can enable minute-K sync and verify 1m bars land in `kline_minute` Parquet with correct 09:30+ timestamps; existing daily-K partitions are unchanged.
  2. Researcher can compute 开盘涨幅 (`open / prev_close − 1`) as a governed column, unit-tested on a known fixture and consumed by strategy filters.
  3. Researcher can run the auction-data probe and observe the verdict (available / fail-closed to derived factors); when unavailable, no UI or strategy labels the 09:30 bar as auction data.

### Phase 17: 竞价策略族 (Auction Strategy Family)

**Goal**: Researchers can run at least 3 first-principles auction strategies (竞价多头, 盘前强势量化, 早盘之星) as builtin strategy files auto-discovered by the engine, each reporting per-stock factor hits without adding a third registration track.
**Depends on**: Phase 16 (open-gap factor)
**Requirements**: STRAT-01, STRAT-02, STRAT-03
**Success Criteria** (what must be TRUE):

  1. At least 3 auction strategies exist in `strategy/builtin/`, appear in the screener strategies API, and return stock pools with 开盘涨幅/涨跌幅.
  2. Each strategy exposes factor-hit tags so a results row can report 关联因子 (which strategies hit it).
  3. No new strategy registry exists; auction strategies are discovered from the builtin dir and the strategies API dedups against `PRESET_STRATEGIES`.

### Phase 18: 股池 Hub (Pool Hub)

**Goal**: Users can open a pool hub showing strategy cards with per-day pool counts, drill into each strategy's stock list (code, 开盘涨幅, 涨跌幅, 概念板块, 关联因子), filter by 概念, and highlight 交叉共振 — all research-only.
**Depends on**: Phase 17 (strategy results)
**Requirements**: POOL-01, POOL-02, POOL-03
**Success Criteria** (what must be TRUE):

  1. User can open the pool hub and see strategy cards with当日 pool counts and drill into a per-strategy stock list backed by `screener_results/` persistence with a single as_of source of truth.
  2. User can filter the pool by 概念 and see 交叉共振 (stocks hit by multiple auction strategies) highlighted.
  3. No execution authority exists anywhere in the pool feature — no API endpoint, UI affordance, or service path can push a pool to a live broker.

### Phase 19: 游客/VIP 脱敏 + 前端 (Guest Access & Frontend)

**Goal**: Guests see only 涨跌幅 and 概念板块 with stock code/name masked server-authoritatively; VIP sessions see明文; the frontend pool page composes cards, lists, filtering, and resonance into one workspace.
**Depends on**: Phase 18 (pool hub API)
**Requirements**: GUEST-01, GUEST-02
**Success Criteria** (what must be TRUE):

  1. Guest session responses mask stock code/name (`******`) at the API DTO boundary and expose only 涨跌幅/概念板块; VIP responses are明文. No client-side masking is trusted.
  2. Masking is display-only — underlying factor computation and strategy results remain unmasked and correct for all sessions.

## Progress

**Execution Order:**
Phases execute in numeric order: 16 → 17 → 18 → 19

| Phase | Requirements | Status |
|-------|-------------|--------|
| 16. 竞价数据层 | DATA-01..03 | Not started |
| 17. 竞价策略族 | STRAT-01..03 | Not started |
| 18. 股池 Hub | POOL-01..03 | Not started |
| 19. 游客/VIP 脱敏 + 前端 | GUEST-01..02 | Not started |

---
*Last updated: 2026-08-04 — v1.3 roadmap created (Phases 16-19, 11/11 requirements mapped)*
