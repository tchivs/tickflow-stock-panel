# Project Research Summary

**Project:** AthenaQuant
**Milestone:** v1.3 竞价选股引擎 (Auction Stock-Selection Engine)
**Domain:** A-share 集合竞价 (9:15–9:25 call auction) driven quantitative stock selection, 盘前/早盘 strategy family, pool display with concept filtering and cross-resonance.
**Researched:** 2026-08-04
**Confidence:** MEDIUM — data-source feasibility is the dominant uncertainty and must be verified in Phase 1 before strategy breadth is committed.

## Executive Summary

AthenaQuant already ships a production screener engine (`backend/app/strategy/engine.py`, 18 builtin strategies + custom signals + AI generation) plus minute-K sync infrastructure (`kline_minute` Parquet, provider capability `minute=True`, APScheduler stage `sync_minute`). What it does **not** have is any 集合竞价 (call-auction) data: minute-K bars start at 09:30 continuous trading (`_minute_ts` anchors start-of-day at `093000`, and `_bucket_minutes` defines the morning session as 09:30+). The 9:15–9:25 auction match (竞价量 / 竞价金额 / 虚拟成交 / 开盘涨幅) — the exact factors the reference attachment's strategies (竞价多头策略, 盘前强势量化, 陈星量化, 竞价阿尔法, 早盘之星, 极速抢筹, T+1闪电, 竞价全面策略, 金色两点半) are built on — is a genuine data gap.

Two viable data paths, to be probed in Phase 1:

1. **开盘涨幅/竞价强度 derivable today.** `strong_open.py` already proves `open vs prev_close` and `change_pct` compute from daily-K enriched. A "竞价多头/盘前强势" family can ship on these derived factors with zero new data source — lowest risk, closes the feature gap for the display columns the reference UI shows (开盘涨幅, 涨跌幅).
2. **真集合竞价匹配数据 (竞价量/金额/虚拟成交).** Requires a new provider capability or a reverse-interface snapshot (wudao-mcp lists 集合竞价 as a market-intelligence capability; free_stockdb minute bars do NOT carry it). Must probe availability early; if unavailable, scope to derived factors and mark true-auction columns as future.

The strategy system's extension seam is ideal for this milestone: a builtin strategy is one Python file with `META`/`filter`/`scoring`, auto-discovered by `StrategyEngine`. The reference UI's per-card "关联因子" (which strategies hit a stock) maps to running the auction-strategy family per symbol and tagging factor hits — a small aggregation over existing `run_all()`.

Frontend: the reference shows a 股池 (pool) hub — strategy cards with pool counts, date navigation, concept filter, cross-resonance, guest-mode masking. AthenaQuant has `Screener.tsx` (strategy cards + results) and `ConceptAnalysis.tsx` (concept data). The pool page is a new workspace that composes them, plus a guest/脱敏 layer consistent with the existing auth model.

## Key Findings

### Recommended Stack

- **No new heavy dependency.** All strategy work stays in the existing Polars strategy engine. Minute-K sync exists (`kline_sync.sync_and_persist_minute`) and needs only enabling + capacity verification.
- **Auction data probe**: a small capability-gated collector for 集合竞价 match data if a source is available (wudao-mcp-style reverse endpoint or a provider `auction=True` capability). Fail-closed when absent — derived open-gap factors are the baseline.
- **Pools & cross-resonance**: reuse the existing `pools/` directory (already present in data lake) and `screener_results/` Parquet; add a pool-hub projection service, not a new datastore.
- **Guest masking**: reuse existing auth/identity layer; a display-only 脱敏 transform (stock code/name → `******`) applied at the API boundary for non-VIP sessions.

### Feature table stakes (from reference attachment)

- Strategy cards: 策略名 + 当日股池数 + 涨跌幅排序
- Per-stock rows: 开盘涨幅, 涨跌幅, 关联因子 (hit strategies), 概念板块
- 日期导航 (交易日), 概念筛选, 交叉共振 (multi-strategy hits)
- 游客模式: 仅展示涨跌幅与概念, 股票代码/名称脱敏; VIP 明文
- 盘前可用性: strategies whose factors are computable pre-open (open-gap family) must run on当日竞价数据 before 09:30 where source allows

### Data gaps / pitfalls

- **No auction match data today** — minute K starts 09:30. True 竞价量/金额/虚拟成交 require a new source. Do not silently approximate with the 09:30 bar.
- **Document drift**: `docs/features.md` claims "20 个内置策略", source has 18 — milestone should reconcile docs with reality.
- **Reference strategy names are product labels, not factor definitions** — 竞价多头/陈星量化/早盘之星 have no public spec. Each must be defined from first principles (which factors, thresholds, weights) as a builtin strategy; do not pretend to replicate a proprietary recipe.
- **Two strategy paths already exist** (`PRESET_STRATEGIES` in `screener.py` + `strategy/builtin/*.py`) — new strategies must land in ONE place (builtin dir) and `PRESET_STRATEGIES` dedup handled, not a third track.
- **Guests vs VIP**: masking must be server-authoritative (apply at API DTO boundary), never client-side, to be trustworthy.

## Implications for Roadmap

Phase order follows dependency: (1) data source — probe auction availability, enable minute sync, define derived open-gap factors; (2) strategy family — 3–5 core auction strategies as builtin files with unit-tested factor contracts; (3) pool hub — pool projection + cross-resonance + concept filter + date nav; (4) guest/VIP masking + frontend pool page; (5) docs/features reconciliation and end-to-end verification.

## Sources

- Reference UI attachment: 策略选股 strategies (竞价多头/盘前强势/陈星量化/竞价阿尔法/早盘之星/极速抢筹/T+1闪电/竞价全面策略/金色两点半), pool counts, 开盘涨幅/关联因子/概念 display, guest-mode masking.
- `docs/aaa/` knowledge base: `a-share-watch-butler/DEEP-ANALYSIS.md` (premarket/postmarket feedback loop), `tickflow-stock-panel/DEEP-ANALYSIS.md` (StrategyDef contract, minute-K sync), `08-数据采集与流水线篇.md` (provider capability probes), `wudao-mcp/QUICK-START.md` (集合竞价 as market-intelligence capability).
- AthenaQuant source: `backend/app/strategy/engine.py`, `backend/app/strategy/builtin/strong_open.py`, `backend/app/data_providers/free_stockdb_provider.py`, `backend/app/jobs/daily_pipeline.py`, `backend/app/api/screener.py`, `frontend/src/pages/Screener.tsx`.
