---
phase: 21-auction-strategy-family
plan: 1
subsystem: strategy-engine
tags: [polars, engine-seam, auction, managed-column, builtin-strategies]

# Dependency graph
requires:
  - phase: 20-auction-data
    provides: probe-gated auction columns (auction_volume/auction_amount) via attach_auction_columns double-gate
provides:
  - 引擎 seam: time_window/evaluation_time/requires_auction_data/minute_confirm_required META 字段 + requires_auction_data 短路空池 + minute_loader/confirm_minute 单点截断
  - 受管列 auction_volume_ratio (竞价量/前5日均量, 不含当日, PIT-safe)
  - P1 三策略: auction_fast_grab / auction_alpha / golden_230
  - test_auction_strategy_family.py (16 tests) + 回归门禁全绿
affects: [21-02, phase-22, phase-23]

# Actuals (#2632) — pairs with the plan's `estimate` (62000) to calibrate future estimates.
actuals:
  tokens: 11593    # chars/4 over the realized diff of this plan's 7 files
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns: [engine minute seam (filter_history_fn 镜像), requires_auction_data fail-closed short-circuit, PIT-safe managed column (prior-5d avg), branch-exclusive filter (真实/派生互斥), grep gate regression locks]

key-files:
  created:
    - backend/app/strategy/builtin/auction_fast_grab.py
    - backend/app/strategy/builtin/auction_alpha.py
    - backend/app/strategy/builtin/golden_230.py
    - backend/tests/test_auction_strategy_family.py
  modified:
    - backend/app/strategy/engine.py
    - backend/app/services/auction_columns.py
    - backend/app/indicators/pipeline.py

key-decisions:
  - "StrategyDef 新字段 (minute_confirm_fn/evaluation_time/minute_confirm_required) 置于 file_path 之后 — dataclass 默认值字段必须尾随非默认字段"
  - "test_engine_short_circuit 用临时 seam_probe 策略验证短路 (Task 3 前, 计划显式授权); 真实策略 fail-closed 由 test_fast_grab_fail_closed 覆盖"
  - "_seed_history_cache 注入早期行 (trade_date-140d) 满足 get_enriched_history 覆盖校验 (cache_min <= warmup_start)"
  - "golden_230 description 用 '隔夜/次日持有' 同时满足诚实归类断言 ('尾盘'/'隔夜'/'非竞价窗口')"
  - "B-1 grep 门禁用 \bword\b 词边界正则, 避免误伤 auction_amount/min_auction_amount 中的 amount 子串"

requirements-completed: [STRAT-04, STRAT-05, STRAT-06]

# Coverage metadata (#1602) — per-deliverable traceability for deterministic UAT routing.
coverage:
  - id: D1
    description: "引擎 seam — time_window 白名单校验 + requires_auction_data 短路空池 (fail-closed) + 分钟单点截断 datetime.time() <= evaluation_time + minute_confirm_required 语义"
    requirement: STRAT-04
    verification:
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_engine_short_circuit"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_minute_truncation_no_future"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_time_window_default_and_validation"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_missing_minute_required_fail_closed"
        status: pass
    human_judgment: false
  - id: D2
    description: "受管列 auction_volume_ratio — 前 5 日均量分母 (不含当日 EOD, PIT-safe), 注册进 ENRICHED_COLUMNS + BY_CATEGORY['auction'], 绝不进存储窄表/计算闭包"
    requirement: STRAT-04
    verification:
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_auction_volume_ratio_prior_5d"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_auction_volume_ratio_excludes_today_eod"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_auction_volume_ratio_absent_without_history"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_auction_volume_ratio_registry_discipline"
        status: pass
    human_judgment: false
  - id: D3
    description: "STRAT-04/05 极速抢筹 + 竞价阿尔法 — 甜点带/>7% 剔除/量比金额阈值 + 缺列空池; 真列/派生分支互斥 + scoring 超集和=1.0 缺列重归一化; pre_open 禁 EOD 列"
    requirement: STRAT-05
    verification:
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_fast_grab_bands"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_fast_grab_fail_closed"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_alpha_branch_exclusive"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_alpha_scoring_renormalize"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_preopen_no_eod_cols"
        status: pass
    human_judgment: false
  - id: D4
    description: "STRAT-06 金色两点半 — post_close 诚实归类 (id 无竞价前缀/描述尾盘隔夜) + 3%-5% 带/收阳 + 分钟确认可选增强 + W-5 无 auction_ 列引用 grep 门禁; P1 三 id 仅 builtin 发现 + PRESET 零碰撞"
    requirement: STRAT-06
    verification:
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_golden_230_window"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_golden_230_minute_confirm_optional"
        status: pass
      - kind: unit
        ref: "tests/test_auction_strategy_family.py#test_no_third_registry"
        status: pass
    human_judgment: false

# Metrics
duration: 36min
completed: 2026-08-05
status: complete
---

# Phase 21 Plan 1: 引擎 seam + auction_volume_ratio + P1 三策略 Summary

**引擎 seam (time_window/evaluation_time/requires_auction_data META + requires_auction_data 短路空池 + minute_loader/confirm_minute 单点截断)、受管列 auction_volume_ratio (前 5 日均量分母, PIT-safe)、P1 三策略 auction_fast_grab / auction_alpha / golden_230 落地, test_auction_strategy_family.py 16 tests + 四项回归门禁全绿**

## Performance

- **Duration:** ~36 min
- **Started:** 2026-08-05T06:52:56Z
- **Completed:** 2026-08-05T07:29:00Z
- **Tasks:** 3
- **Files modified:** 7 (3 modified / 4 created)

## Accomplishments

- **Task 1 引擎 seam:** `_load_file` 为四个新 META 字段补默认 (`time_window="intraday"` / `evaluation_time=None` / `requires_auction_data=False` / `minute_confirm_required=False`) + `time_window` 白名单校验 (非法 → `load_errors` 可见); `StrategyDef` 增 `minute_confirm_fn`/`evaluation_time`/`minute_confirm_required`; `__init__` 增 `minute_loader` 形参; `run()` 数据加载后、基础过滤前插入 `requires_auction_data` 短路 (缺 `auction_volume` → 空 `StrategyResult`, 绝不 ColumnNotFoundError); Stage 2 后插入分钟确认 seam — 引擎单点 `datetime.time() <= evaluation_time` 截断, `minute_confirm_required` 决定缺分钟数据是空池还是跳过。
- **Task 2 受管列:** `auction_columns.attach_auction_columns` 在双闸门通过后调 `_attach_auction_volume_ratio` (分母 = `repo.get_enriched_history(trade_date, 6)` 过滤 `date < trade_date` 后 `tail(5)` 均值, 绝不含当日 EOD); 注册进 `ENRICHED_COLUMNS["auction_volume_ratio"]` + `ENRICHED_COLUMNS_BY_CATEGORY["auction"]`, 不进 `ENRICHED_STORAGE_COLS`/`_ALL_INDICATOR_COLS`; 无历史 → 列缺席 (诚实缺列)。
- **Task 3 P1 三策略:** `auction_fast_grab` (甜点带 2.8%–3.5% + >7% 剔除 + 量比≥1.5 + 金额≥200万, 缺列空池); `auction_alpha` (真列/派生分支按列存在性互斥, scoring 超集和=1.0); `golden_230` (post_close 诚实归类, id 无竞价前缀, 描述尾盘/隔夜/非竞价窗口, 分钟确认可选增强)。
- **回归:** `test_auction_strategies.py` (11) + `test_auction_columns.py` (12) + `test_auction_probe.py` + `test_auction_sync.py` (46 合计) 全绿, 既有 23 个 builtin 策略加载零 load_errors。

## Task Commits

1. **Task 1: 引擎 seam — META 时间窗 + requires_auction_data 短路 + 分钟单点截断** - `f08f3b9` (feat)
2. **Task 2: 受管列 auction_volume_ratio (前 5 日均量分母, PIT-safe)** - `28de2ff` (feat)
3. **Task 3: P1 三策略 auction_fast_grab / auction_alpha / golden_230 + 策略族测试** - `80c99a3` (feat)

## Files Created/Modified

- `backend/app/strategy/engine.py` - META 四字段 setdefault + time_window 白名单校验; `StrategyDef` 三新字段; `__init__` minute_loader; `run()` requires_auction_data 短路 + 分钟确认 seam (单点截断)
- `backend/app/services/auction_columns.py` - `_attach_auction_volume_ratio` 派生 (前 5 日均量分母, PIT-safe); keep 元组追加 ratio 列
- `backend/app/indicators/pipeline.py` - `ENRICHED_COLUMNS` + `ENRICHED_COLUMNS_BY_CATEGORY["auction"]` 注册 `auction_volume_ratio`
- `backend/app/strategy/builtin/auction_fast_grab.py` - STRAT-04 极速抢筹 (pre_open, requires_auction_data=True)
- `backend/app/strategy/builtin/auction_alpha.py` - STRAT-05 竞价阿尔法 (真列/派生分支互斥)
- `backend/app/strategy/builtin/golden_230.py` - STRAT-06 金色两点半 (post_close, minute_confirm 可选增强)
- `backend/tests/test_auction_strategy_family.py` - 16 tests (引擎 seam 4 / 受管列 4 / P1 策略 8)

## Decisions Made

- StrategyDef 新字段置于 `file_path` 之后 (dataclass 默认值字段必须尾随非默认字段, 与计划"沿 filter_history_fn"字面位置不同但无行为差异)。
- `test_engine_short_circuit` 用临时 `seam_probe` 策略 (Task 1 计划步骤 8 显式授权); 真实 `auction_fast_grab` 的 fail-closed 由 Task 3 的 `test_fast_grab_fail_closed` 覆盖。
- B-1 grep 门禁用 `\bword\b` 词边界正则, 避免 `auction_amount`/`min_auction_amount` 中的 `amount` 子串被误判为 EOD `amount` 列引用。
- `_seed_history_cache` 注入早期行 (trade_date−140d) 以满足 `get_enriched_history` 的覆盖校验 (`cache_min <= warmup_start`), 使 hermetic 缓存种子真实返回数据。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] golden_230 description 缺 "隔夜" 字面串**
- **Found during:** Task 3 (test_golden_230_window)
- **Issue:** 计划 META 描述文本写 "次日持有" 而测试断言 `"隔夜" in description`, 首次运行断言失败。
- **Fix:** description 改为 "尾盘 14:30 后选股、隔夜/次日持有, 非竞价窗口", 同时满足 "尾盘"/"隔夜"/"非竞价窗口" 三断言。
- **Files modified:** backend/app/strategy/builtin/golden_230.py
- **Verification:** `pytest tests/test_auction_strategy_family.py::test_golden_230_window` 绿
- **Committed in:** 80c99a3

**2. [Rule 1 - Bug] test_fast_grab_bands fixture 缺 `auction_volume` (短路闸门列)**
- **Found during:** Task 3 (test_fast_grab_bands)
- **Issue:** `auction_fast_grab` 的 `requires_auction_data` 短路检查 `auction_volume` 列存在性; fixture 只有 `auction_volume_ratio`/`auction_amount` → 引擎短路返回空池。
- **Fix:** fixture 增加 `auction_volume` 列 (值 8000), 短路闸门通过, 回到 filter 行为断言。
- **Files modified:** backend/tests/test_auction_strategy_family.py
- **Verification:** `pytest tests/test_auction_strategy_family.py::test_fast_grab_bands` 绿
- **Committed in:** 80c99a3

**3. [Rule 1 - Bug] 临时策略 file 编辑落点漂移**
- **Found during:** Task 3 (测试文件编辑)
- **Issue:** 基于过期行号的编辑触发自动修复, 吞掉 `def test_fast_grab_bands` 函数头; golden_230 META 一次编辑误落 `"params": [` 行。
- **Fix:** 重新读取后恢复函数头与 META 块结构; 语法校验 + 全量测试确认。
- **Files modified:** backend/tests/test_auction_strategy_family.py, backend/app/strategy/builtin/golden_230.py
- **Verification:** 16 tests 全绿 + ast.parse 语法 OK
- **Committed in:** 80c99a3

---

**Total deviations:** 3 auto-fixed (全部 Rule 1 bug)
**Impact on plan:** 全部为测试/描述文本与实现的局部对齐, 无 scope creep, 无行为偏离计划规格。

## Issues Encountered

- 并行 executor (21-02) 在同一工作树提交了 `auction_allround.py`/`t1_flash.py`/`test_auction_strategy_family_p2.py` 等文件; 本计划严格按 `--files` 精确暂存, 未误纳 21-02 文件, 亦未触碰用户未提交的 `frontend/src/pages/Watchlist.tsx` (经 `git log -- Watchlist.tsx` 验证本计划 3 次提交均未涉该文件)。

## User Setup Required

None - 零新增外部运行时依赖, 无环境变量配置。

## Next Phase Readiness

- 21-02 的 STRAT-09 (auction_intraday_confirm) 已可复用本计划的引擎 seam (engine.py 分钟确认单点截断 + minute_loader) 与受管列 `auction_volume_ratio`。
- P2 三策略 (auction_allround / t1_flash / auction_intraday_confirm) 已由 21-02 并行落地, 文档计数对账 (21→27) 已完成 (见 21-02 提交 a759252)。
- 策略 API `list_strategies()` 已透传 `time_window`/`evaluation_time`/`requires_auction_data`/`minute_confirm_required` (test_no_third_registry 断言), Phase 23 前端可展示。

---
*Phase: 21-auction-strategy-family*
*Completed: 2026-08-05*

## Self-Check: PASSED

- 创建的 4 个文件 (3 策略 + 1 测试) 全部存在 (`[ -f ]` 逐一验证)。
- 3 个 task commit + 1 个 metadata commit 全部存在于 git 历史:
  - `f08f3b9` (Task 1) / `28de2ff` (Task 2) / `80c99a3` (Task 3) / `c6f73a3` (docs)。
- 测试证据: `pytest tests/test_auction_strategy_family.py -q` 16 passed; 四项回归门禁
  `test_auction_probe.py` + `test_auction_columns.py` + `test_auction_sync.py` +
  `test_auction_strategies.py` 46 passed (62 合计)。
- `frontend/src/pages/Watchlist.tsx` 未被本计划触碰 (`git log -- <file>` 0 hits)。
