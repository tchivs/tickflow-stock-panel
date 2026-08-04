# v1.3 Auction Feature Analysis

**Scope:** Features the reference attachment's 竞价选股 UI implies, mapped to what AthenaQuant can build with its existing strategy engine and data seams.

## Reference UI Feature Inventory

The attachment ("策略选股" workspace) shows:

| Feature | Reference UI | AthenaQuant today | Gap |
|---|---|---|---|
| Strategy cards | 竞价多头/盘前强势/陈星量化/竞价阿尔法/早盘之星/极速抢筹/T+1闪电/竞价全面策略/金色两点半 with 股池 N | `Screener.tsx` strategy cards, 18 builtin strategies | Strategy family does not exist; must be authored |
| Pool count per strategy | 股池 6/7/0... | `pools/` dir + `screener_results/` exist; no per-strategy pool hub | Pool projection service + UI |
| Per-stock row | 开盘涨幅, 涨跌幅, 关联因子 N 个, 概念板块 | Screener results show scores; concepts in ConceptAnalysis | Open-gap factor in results; factor-hit tagging; concept join |
| Cross-resonance (交叉共振) | multi-strategy hits on one stock | none | Aggregation over `run_all()` per-symbol |
| Concept filter | 概念筛选 | ConceptAnalysis has concept data; Screener lacks filter | Filter layer on pool page |
| Date navigation | 交易日 2026/08/04 ‹ › | Screener has as_of date | Reuse + day stepping |
| Guest mode | 游客: 涨跌幅+概念 only, code/name masked `******`; VIP 明文 | Auth layer exists; no masking | Server-side DTO masking |
| Search | 搜索代码/名称 | Screener has symbol search | Minor |

## Feature Categories

### Table stakes (must have)

1. **Auction strategy family** — at minimum 竞价多头, 盘前强势量化, 早盘之星 as builtin strategies with `open_gap`, `change_pct`, volume-ratio, and any available auction-volume factors. Each is a first-principles factor definition (reference names are product labels, not public specs).
2. **Pool hub** — strategy cards with当日 pool counts; per-strategy stock list.
3. **Open-gap factor** — 开盘涨幅 = (open/prev_close − 1), derivable from daily-K enriched immediately; this alone matches the reference display columns.
4. **Cross-resonance** — for each stock, list which strategies hit it (关联因子).
5. **Date navigation** — per-trading-day pool view.

### Differentiators

6. **True auction match data** (竞价量/金额/虚拟成交) — only if a probe finds a working source; otherwise derived factors only.
7. **Concept filter + 交叉共振 view** — pool page concept filter and multi-hit highlighting.
8. **Guest/VIP masking** — server-authoritative 脱敏.

### Anti-features / avoid

- Pretending to replicate proprietary strategy recipes (陈星量化 etc.) without a public spec — define ours, name ours.
- Silently approximating 集合竞价 volume with the 09:30 continuous-trading bar.
- A third strategy registration track (use `strategy/builtin/`, dedup `PRESET_STRATEGIES`).

## Dependency Map

- Auction strategy family → (1) open-gap factors from enriched [exists], (2) optional auction data [probe]
- Pool hub → strategy family results + `screener_results/` persistence
- Cross-resonance → strategy family running all members per symbol
- Concept filter → concept data (ConceptAnalysis seam) + pool rows
- Guest masking → auth/identity + DTO transform

## Build Order

1. Data layer: probe auction availability; enable minute sync; define open-gap factor columns.
2. Strategy family: author 3–5 builtin auction strategies with unit-tested filters.
3. Pool hub service + cross-resonance aggregation + concept join.
4. Frontend pool page + guest/VIP masking.
5. Docs/features reconciliation (18 vs 20 count) + E2E verification.
