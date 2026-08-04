---
phase: 17-auction-strategy-family
plan: 1
subsystem: strategy
tags: [auction, strategy, polars, fastapi, builtin, open_gap]

# Dependency graph
requires:
  - phase: 16-auction-data
    provides: governed enriched columns open_gap / change_pct / vol_ratio_5d + ENRICHED_STORAGE_COLS shape
provides:
  - 3 first-principles auction strategies (竞价多头 / 盘前强势量化 / 早盘之星) auto-discovered by StrategyEngine with source=builtin
  - STRAT-03 regression lock: strategies API dedup vs PRESET_STRATEGIES, builtin-only discovery, no third registry
affects: [18-pool-hub, screener API consumers, strategy/builtin conventions]

# Actuals (#2632) — pairs with plan estimate (estimateTokens: 64000). chars/4 over the realized diff.
actuals:
  tokens: 3593
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []  # 纯 Polars 表达式, 无新依赖
  patterns:
    - "first-principles auction strategy file: META (id/name/description/tags/params/scoring/order_by/descending/limit) + ENTRY_SIGNALS/EXIT_SIGNALS/STOP_LOSS/MAX_HOLD_DAYS/ALERTS + filter(df, params) -> pl.Expr"
    - "过滤器只消费受管列 (open_gap/change_pct/vol_ratio_5d), 空值 fail-closed; 概念佐证列可选且列存在性守卫"
    - "引擎自动发现 (strategy/builtin/*.py) + strategies API seen_ids 去重 = 唯一注册轨道"

key-files:
  created:
    - backend/app/strategy/builtin/auction_bullish.py
    - backend/app/strategy/builtin/auction_preopen_quant.py
    - backend/app/strategy/builtin/auction_early_star.py
    - backend/tests/test_auction_strategies.py
  modified: []

key-decisions:
  - "竞价多头/盘前强势量化/早盘之星的名称是产品标签; 因子定义全部第一性原理 (CONTEXT #1), 不宣称与任何专有配方一致"
  - "所有过滤器消费 Phase 16 受管列, 永不从 raw bar 重推 open_gap 或 rejoin 前收盘 (T-17-01, PITFALL #6)"
  - "早盘之星概念板块佐证默认关闭, 且仅当 enriched 实际含 concept_board 列时生效 (列存在性守卫), 避免 OR 组合被不存在的列破坏"
  - "评分权重和恒为 1.0, 沿用 strong_open.py 约定 (PITFALL #7)"

patterns-established:
  - "竞价策略族文件 = 独立可发现 .py 模块, 由 StrategyEngine._load_all 从 strategy/builtin 目录自动加载, source 推导为 builtin"
  - "null 受管列在 AND 过滤中 fail-closed (Polars null >= 阈值 为 null, filter 丢弃该行)"

requirements-completed: [STRAT-01, STRAT-03]

coverage:
  - id: D1
    description: "3 个第一性原理竞价策略文件位于 strategy/builtin/, 被 StrategyEngine 自动发现且 source==builtin (STRAT-01)"
    requirement: STRAT-01
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_strategies.py#test_auction_strategies_auto_discovered_by_engine"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategies.py#test_auction_strategies_appear_once_in_strategies_api"
        status: pass
    human_judgment: false
  - id: D2
    description: "每个竞价策略返回的股池行携带受管 开盘涨幅/涨跌幅, 过滤器只在受管列 fixture 上运行 (无 raw bar 重推)"
    requirement: STRAT-01
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_strategies.py#test_auction_bullish_run_returns_pool_with_governed_columns"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategies.py#test_auction_strategies_only_use_governed_columns"
        status: pass
    human_judgment: false
  - id: D3
    description: "strategies API 每个竞价 id 恰好出现一次且 source==builtin; id 不落入 PRESET_STRATEGIES; 无第三条注册轨道"
    requirement: STRAT-03
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_strategies.py#test_auction_ids_never_collide_with_presets"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategies.py#test_no_third_registry_track"
        status: pass
    human_judgment: false
  - id: D4
    description: "多因子评分权重和恒为 1.0 (PITFALL #7)"
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_strategies.py#test_auction_strategy_scoring_weights_sum_to_one"
        status: pass
    human_judgment: false
  - id: D5
    description: "null open_gap / change_pct / vol_ratio_5d fail-closed, 永不误入选 (DATA-03 承继)"
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_strategies.py#test_auction_bullish_requires_both_momentum"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategies.py#test_auction_preopen_strength_requires_gap_and_volume"
        status: pass
    human_judgment: false

# Metrics
duration: 26min
completed: 2026-08-04
status: complete
---

# Phase 17 Plan 1: 竞价策略族 — 3 个内置竞价策略 + STRAT-03 去重回归 Summary

**三个第一性原理竞价策略 (竞价多头 / 盘前强势量化 / 早盘之星) 落地 `strategy/builtin/`, 引擎自动发现、仅消费 Phase 16 受管列 (open_gap/change_pct/vol_ratio_5d)、评分权重和恒为 1.0, 并以 11 个 fixture 测试锁死 STRAT-03: API 去重 + 无第三条注册轨道。**

## Performance

- **Duration:** 26 min
- **Started:** 2026-08-04T13:03:00Z
- **Completed:** 2026-08-04T13:29:02Z
- **Tasks:** 3
- **Files modified:** 4 (3 strategy files + 1 test module)

## Accomplishments
- **竞价多头 (auction_bullish)**: `open_gap >= 2% AND change_pct >= 2%` 严格 AND 双动量, 第一性原理阈值; 作为 tracer 打通 文件 → 引擎发现 → `run()` 返回带受管列股池 的整条链路。
- **盘前强势量化 (auction_preopen_quant)**: `open_gap >= 3% AND vol_ratio_5d >= 1.5` 盘前强度双阈值, 量比作集合竞价活跃度代理。
- **早盘之星 (auction_early_star)**: `open_gap >= 1.5% OR change_pct >= 3%` OR 组合, 概念板块佐证参数默认关闭且带列存在性守卫 (enriched 无概念列时不崩溃、不收窄)。
- **STRAT-03 回归锁**: strategies API 每个竞价 id 恰好出现一次 `source: builtin`; 三个 id 均不在 `PRESET_STRATEGIES`; 扫描 `engine.py` + `builtin/__init__.py` 证明无第三条注册轨道。
- **空值 fail-closed**: null `open_gap`/`change_pct`/`vol_ratio_5d` 在 AND 过滤中全部丢弃 (DATA-03 承继)。

## Task Commits

每个任务原子提交:

1. **Task 1: 竞价多头 tracer (文件→引擎发现→run 股池带受管列)** - `1b99483` (feat)
2. **Task 2: 盘前强势量化 + 早盘之星 builtin 策略 + fixture 测试** - `2ea0088` (feat)
3. **Task 3: STRAT-03 回归 — builtin-only 发现 + PRESET_STRATEGIES 去重, 无第三注册表** - `e990f84` (test)

**Plan metadata:** (见下方 `## Plan Complete` — 本 SUMMARY 单独 docs 提交)

## Files Created/Modified
- `backend/app/strategy/builtin/auction_bullish.py` — 竞价多头: AND 双动量 filter + scoring {open_gap:0.5, change_pct:0.5}
- `backend/app/strategy/builtin/auction_preopen_quant.py` — 盘前强势量化: open_gap + vol_ratio_5d 双阈值 filter + scoring {open_gap:0.4, vol_ratio_5d:0.6}
- `backend/app/strategy/builtin/auction_early_star.py` — 早盘之星: OR 组合 filter + 列守卫概念佐证 + scoring {open_gap:0.5, change_pct:0.5}
- `backend/tests/test_auction_strategies.py` — 11 个测试: 过滤器语义 / 引擎发现 / run 股池 / 权重和 / 受管列-only / 概念佐证 / API 去重 / 无冲突 / 无第三注册表

## Decisions Made
- 竞价策略名称 (竞价多头/盘前强势量化/早盘之星) 是产品标签, 因子定义全部按第一性原理撰写, 中文描述诚实标注, 不宣称与任何专有配方一致 (CONTEXT #1)。
- 过滤器只消费 Phase 16 受管列; 无概念列时早盘之星佐证参数静默降级为纯 OR 组合 (列存在性守卫)。
- 测试模块按 引擎构造路径 = `backend/app/strategy/builtin` 解析 (见 Deviations)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 引擎构造路径 `parents[2]` 在本仓库解析到错误目录**
- **Found during:** Task 1 (tracer)
- **Issue:** PLAN 中的引擎发现测试写 `Path(__file__).resolve().parents[2] / "app" / "strategy" / "builtin"`, 假定测试位于仓库根的 `tests/` 下。本仓库测试在 `backend/tests/`, `parents[2]` 解析到仓库根 `/app/strategy/builtin` (不存在), 引擎静默跳过该目录 → `engine.has("auction_bullish")` 为 False, 首次运行 2 个测试失败。
- **Fix:** 改为 `parents[1]` (backend 目录), 解析到真实的 `backend/app/strategy/builtin`。
- **Files modified:** backend/tests/test_auction_strategies.py
- **Verification:** `test_auction_strategies_auto_discovered_by_engine` / `test_auction_bullish_run_returns_pool_with_governed_columns` 转绿。
- **Committed in:** 1b99483 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** 仅修正测试内的路径解析常量, 属计划允许的"保持测试绿的小实现细节"。无范围蔓延。

## Issues Encountered
- 并发执行器 17-02 同时修改 `backend/app/api/screener.py` (run_all 关联因子 STRAT-02)。该改动不触及 `strategies` 端点与 `PRESET_STRATEGIES`, 与 17-01 无冲突; 本执行器只读 screener.py, 三笔提交均未误纳入该文件。
- 计划提到 builtin 目录 "18 existing + 3 new", 实为 19 个可加载策略文件 (18 .py + 未计数 __init__.py); 无测试断言具体数量, 不影响结果。

## User Setup Required

None - 无外部服务配置要求。

## Next Phase Readiness
- 三个竞价策略已在 `strategy/builtin/` 落地且可被引擎发现, Phase 18 (股池 Hub) 可直接调用。
- STRAT-03 去重契约已回归锁定, 后续新增内置策略沿用同一注册轨道 (builtin 目录 + API seen_ids 去重)。
- 概念板块佐证为可选参数, enriched 一旦提供 `concept_board` 列即可启用, 无需改策略代码。

## Plan Complete
- SUMMARY: `.planning/phases/17-auction-strategy-family/17-01-SUMMARY.md` (docs 提交在下一阶段由 orchestrator 或本执行器的 final commit 记录)
- 未调用 `phase complete` (会整阶段标记完成, 与并行的 17-02 冲突); 按约束采用"提交 SUMMARY"方案。

---
*Phase: 17-auction-strategy-family*
*Completed: 2026-08-04*

## Self-Check: PASSED

- 文件存在: auction_bullish.py / auction_preopen_quant.py / auction_early_star.py / test_auction_strategies.py / 17-01-SUMMARY.md
- 提交存在: `1b99483` / `2ea0088` / `e990f84`
- 最终验证: `cd backend && .venv/bin/python -m pytest tests/test_auction_strategies.py -q` → **11 passed**
