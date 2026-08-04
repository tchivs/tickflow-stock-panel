# Phase 17: 竞价策略族 (Auction Strategy Family) - Context

**Gathered:** 2026-08-04
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous smart discuss — user requested automated GSD flow)

<domain>
## Phase Boundary

**Goal**: Researchers can run at least 3 first-principles auction strategies (竞价多头, 盘前强势量化, 早盘之星) as builtin strategy files auto-discovered by the engine, each reporting per-stock factor hits without adding a third registration track.

**Depends on**: Phase 16 (open-gap factor `open / prev_close − 1` governed column)

**Success Criteria** (must be TRUE):
1. At least 3 auction strategies exist in `strategy/builtin/`, appear in the screener strategies API, and return stock pools with 开盘涨幅/涨跌幅.
2. Each strategy exposes factor-hit tags so a results row can report 关联因子 (which strategies hit it).
3. No new strategy registry exists; auction strategies are discovered from the builtin dir and the strategies API dedups against `PRESET_STRATEGIES`.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion — Authorized Constraints

1. **First-principles factor definitions.** Reference names (竞价多头/盘前强势量化/早盘之星) are product labels, NOT public factor specs. Each strategy is authored from first principles with honest names/descriptions. Do NOT claim parity with a proprietary recipe. (STRAT-01, PITFALL #4)
2. **Derived-factor baseline.** True 9:15–9:25 集合竞价 match data is probe-gated (DATA-03); when unavailable the strategy family fails closed to derived open-gap factors (`open / prev_close − 1` from daily-K enriched, landed in Phase 16) and 涨跌幅. Never label the 09:30 continuous bar as auction data.
3. **Factor-hit tagging (STRAT-02).** Each strategy exposes per-stock factor-hit tags so a results row reports 关联因子 — feeding Phase 18 cross-resonance. Follow the existing engine's hit/reason pattern; keep the contract unit-testable.
4. **One registration track (STRAT-03).** New strategies land in `strategy/builtin/` ONLY. The strategies API dedups against `PRESET_STRATEGIES`. No third registry. (PITFALL #5)
5. **Score weight stability (PITFALL #7).** Engine normalizes scoring weights to 1.0; follow the existing builtin pattern (`strong_open.py`) so multi-factor strategies stay weight-sum stable.
6. **Open-gap lookahead guard (PITFALL #6).** `open vs prev_close` must use same-day open and prior-day close — the Phase 16 governed column already contract-tested this; strategies consume the column, never rejoin raw bars.

### Strategy Slate (v1.3 core 3)

- **竞价多头**: 开盘涨幅 + 涨跌幅 momentum, first-principles threshold ranking.
- **盘前强势量化**: pre-open strength — open-gap magnitude + 量比/成交活跃 proxy, quant-threshold based.
- **早盘之星**: early-session star — 开盘涨幅/涨跌幅 combo with 概念板块 corroboration optional.

Others (竞价阿尔法/极速抢筹/T+1闪电/竞价全面策略/金色两点半) → STRAT-04 (v2), deferred.

</decisions>

<code_context>
## Existing Code Insights

- `backend/app/strategy/builtin/strong_open.py` — the canonical open-gap builtin strategy; pattern for META/filter/scoring, weight-sum stability.
- `backend/app/strategy/engine.py` — StrategyEngine auto-discovers builtin dir; `run_all()` per-symbol aggregation feeds 关联因子.
- `backend/app/api/screener.py` — strategies API; `PRESET_STRATEGIES` must dedup against new builtin auction strategies.
- `backend/app/indicators/pipeline.py` — Phase 16 landed governed `open_gap` column.
- Phase 16 test conventions: `backend/tests/test_open_gap_factor.py`, `backend/tests/test_auction_probe.py`.

</code_context>

<specifics>
## Specific Ideas

- 3 builtin strategy files under `strategy/builtin/`, each with META, filter, scoring, and factor-hit tag emission.
- Strategies API returns the new strategies; dedup against PRESET_STRATEGIES by name; no duplicate listings.
- Per-strategy unit tests on known fixtures: pool returned, 开盘涨幅/涨跌幅 columns present, factor-hit tags correct.
- 关联因子 aggregation contract tested so Phase 18 can consume it.

</specifics>

<deferred>
## Deferred Ideas

- 竞价阿尔法, 极速抢筹, T+1闪电, 竞价全面策略, 金色两点半 → STRAT-04 (v2)
- True auction match data as first-class columns → DATA-04 (v2), gated on source availability
- 日期导航 (per-day historical pool browsing) → POOL-04 (v2)
</deferred>
