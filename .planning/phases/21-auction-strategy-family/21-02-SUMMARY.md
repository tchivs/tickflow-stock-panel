---
phase: 21-auction-strategy-family
plan: 2
subsystem: strategy
tags: [auction, pre-open, intraday, minute-confirm, t1-flash, docs-reconciliation, polars]

# Dependency graph
requires:
  - phase: 21-auction-strategy-family (21-01)
    provides: engine seam (minute_loader / minute_confirm_fn single-point truncation, requires_auction_data short-circuit, time_window/evaluation_time META) + managed column auction_volume_ratio + P1 strategies
provides:
  - STRAT-07 auction_allround (竞价全面): pre_open whitelist full-factor composite with optional EOD-labeled turnover (default off)
  - STRAT-08 t1_flash (T+1闪电): T-day auction buy-signal pool, T+1 sell as EXIT/MAX_HOLD_DAYS=1 semantics (never in pool)
  - STRAT-09 auction_intraday_confirm (盘中确认): engine single-point truncated minute confirm, cum_volume × time_factor (09:45→15→16.0), minute-absent → empty pool
  - docs reconciliation: features.md 21→27, strategy.md 18→27, strategy-guide.md time-window/minute-confirm contract
  - STRAT-03 regression: P2 three ids builtin-only discovery, PRESET zero-collision, strategies API exactly once
affects: [22-pool-date-navigation, 23-frontend, future AI/custom strategy generation (strategy-guide contract)]

# Actuals (#2632) — same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 6090    # chars/4 over realized diff (24,360 added chars across 7 files)
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pre_open whitelist filter: forbidden EOD cols change_pct/vol_ratio_5d/amount/close + pl.lit(False) missing-col guard"
    - "engine single-point minute truncation consumer: minute_confirm(df_minute, params) with time_factor = 240/elapsed (market_time)"
    - "optional column narrowing gated on params flag AND column presence (auction_early_star semantics)"
    - "EXIT_SIGNALS/MAX_HOLD_DAYS=1 as T+1 sell semantics, pool computed only from T-day as-of frame"
    - "hermetic P2 tests: production imports inside test functions, shared _engine/_run_auction/_minute_frame helpers"

key-files:
  created:
    - backend/app/strategy/builtin/auction_allround.py
    - backend/app/strategy/builtin/t1_flash.py
    - backend/app/strategy/builtin/auction_intraday_confirm.py
    - backend/tests/test_auction_strategy_family_p2.py
  modified:
    - docs/features.md
    - docs/strategy.md
    - backend/app/strategy/prompts/strategy-guide.md

key-decisions:
  - "P2 three ids discovered only via strategy/builtin auto-discovery; PRESET zero-collision; STRAT-03 regression locked"
  - "auction_allround optional turnover_rate is EOD-labeled 盘后参考 default-off; narrows only when column present and flag on"
  - "t1_flash T+1 sell is EXIT_SIGNALS=[signal_ma20_breakdown] + MAX_HOLD_DAYS=1 semantics; never participates in pool computation"
  - "auction_intraday_confirm consumes the 21-01 engine seam with zero engine changes: truncation point is engine-only"
  - "docs count reconciled to 27 = actual builtin/*.py file count (PITFALLS #6 drift closed for both features.md and strategy.md)"

patterns-established:
  - "fail-closed filter guard: missing required auction column -> pl.lit(False) (empty pool, never partial/0-fill)"
  - "minute_confirm computes time_factor via trading_minutes_elapsed_from_dt(datetime.combine(as_of, dt_time(9,45))); eval 09:45 → elapsed 15 → tf 16.0 fixture"
  - "pre_open filter grep gate: assert filter body has no pl.col(\"change_pct\"/\"vol_ratio_5d\"/\"amount\"/\"close\")"

requirements-completed: [STRAT-07, STRAT-08, STRAT-09]

coverage:
  - id: D1
    description: "STRAT-07 竞价全面 (auction_allround): pre_open whitelist composite open_gap>=2% & auction_volume_ratio>=1.2 & auction_amount>=1M; optional turnover_rate (EOD, default off) narrows only when column present; missing cols → empty pool; filter body free of EOD columns"
    requirement: STRAT-07
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_allround_core_and_optional_turnover"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_allround_fail_closed"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_p2_preopen_no_eod_cols"
        status: pass
    human_judgment: false
  - id: D2
    description: "STRAT-08 T+1闪电 (t1_flash): pool from T-day auction signals open_gap>=2.5% & auction_volume_ratio>=2.0 & auction_amount>=2M; EXIT_SIGNALS/MAX_HOLD_DAYS=1 semantics; no T+1 data in pool; missing cols → empty pool"
    requirement: STRAT-08
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_t1_flash_no_lookahead"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_t1_flash_fail_closed"
        status: pass
    human_judgment: false
  - id: D3
    description: "STRAT-09 盘中确认 (auction_intraday_confirm): engine single-point truncation to evaluation_time=09:45 (no future bars), minute_confirm computes cum_volume × time_factor (16.0) + no-break-open; minute data absent → empty pool; daily prefilter only open_gap"
    requirement: STRAT-09
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_intraday_truncation"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_time_factor"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_intraday_minute_absent_empty"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_intraday_prefilter_no_eod"
        status: pass
    human_judgment: false
  - id: D4
    description: "STRAT-03 registry regression: P2 three ids (auction_allround/t1_flash/auction_intraday_confirm) auto-discovered source=builtin, absent from PRESET_STRATEGIES, strategies API exactly once, load_errors clean; scoring weights sum to 1.0"
    requirement: STRAT-07
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_no_third_registry_p2"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_strategy_family_p2.py#test_p2_scoring_weights_sum_to_one"
        status: pass
    human_judgment: false
  - id: D5
    description: "Docs reconciliation: features.md 21→27 and strategy.md 18→27 both equal builtin/*.py file count (27); strategy-guide.md documents time_window/evaluation_time/requires_auction_data/minute_confirm_required/minute_confirm contract + pre_open EOD-col ban"
    verification:
      - kind: other
        ref: "[ $(grep -l '27 个内置策略' docs/features.md docs/strategy.md | wc -l) = 2 ] && [ $(ls backend/app/strategy/builtin/*.py | grep -vc __init__) = 27 ]"
        status: pass
      - kind: other
        ref: "grep -c 'time_window' strategy-guide.md >= 1 && grep -c 'minute_confirm' strategy-guide.md >= 1"
        status: pass
    human_judgment: false

# Metrics
duration: 45min
completed: 2026-08-05
status: complete
---

# Phase 21 Plan 2: P2 竞价策略族 (STRAT-07/08/09) + 文档对账 Summary

**竞价全面 / T+1闪电 / 盘中确认 三个 P2 策略落地（pre_open 白名单 + fail-closed + 引擎单点截断分钟确认），文档计数对账到 27，strategy-guide.md 补时间窗/分钟确认契约字段**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-08-05T06:05:00Z (approx)
- **Completed:** 2026-08-05T06:59:35Z
- **Tasks:** 3
- **Files modified:** 7 (3 new strategies + 1 new test file + 3 docs)

## Accomplishments

- **STRAT-09 盘中确认 (`auction_intraday_confirm`)**：日线初筛只用 `open_gap`（pre_open 可算列，EOD 列一票否决）；`minute_confirm` 消费 21-01 引擎 seam 单点截断到 `evaluation_time=09:45` 的分钟帧，`cum_volume × time_factor`（09:45→elapsed=15→tf=16.0，`market_time` 折算）与不破开盘价双确认；`minute_confirm_required=True` → 分钟数据缺席空池。零引擎改动。
- **STRAT-07 竞价全面 (`auction_allround`)**：pre_open 白名单全因子复合（`open_gap>=2% & auction_volume_ratio>=1.2 & auction_amount>=100万`）；可选 `turnover_rate` 为**盘后参考（EOD，默认关）**，仅当参数开启且帧已含该列才收窄；缺竞价列 → `pl.lit(False)` 空池；scoring 权重和=1.0。
- **STRAT-08 T+1闪电 (`t1_flash`)**：池只由 T 日竞价买入信号计算（`open_gap>=2.5% & auction_volume_ratio>=2.0 & auction_amount>=200万`）；T+1 次日早盘卖出为 `EXIT_SIGNALS=["signal_ma20_breakdown"]` + `MAX_HOLD_DAYS=1` 语义，绝不参与池成员计算（无 lookahead）。
- **文档计数对账**：`docs/features.md` 21→27、`docs/strategy.md` 18（已漂移）→27，两处与 `builtin/*.py` 实际文件数 27 一致（PITFALLS #6 关闭）；`strategy-guide.md` 补 `time_window`/`evaluation_time`/`requires_auction_data`/`minute_confirm_required` META 契约 + `minute_confirm` 契约小节 + 规则 10（pre_open 禁 EOD 列）。
- **STRAT-03 回归**：P2 三 id 仅经 `strategy/builtin/` 自动发现、`PRESET_STRATEGIES` 零碰撞、strategies API 恰好一次、load_errors 不含 P2 文件（与 21-01 的 P1 同形测试互补）。

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer, TDD): STRAT-09 盘中确认 `auction_intraday_confirm`** — `d9849fc` (feat) + `4e4aa51` (test RED, shared with Task 2)
2. **Task 2: P2 pre_open 策略 `auction_allround` / `t1_flash`** — `3098097` (feat) + `4e4aa51` (test RED)
3. **Task 3: 文档计数对账 + strategy-guide 契约** — `a759252` (docs)

**Plan metadata:** (final summary commit follows this file)

## Files Created/Modified

- `backend/app/strategy/builtin/auction_allround.py` - STRAT-07 竞价全面: pre_open 白名单复合 filter + 可选换手(默认关) + fail-closed
- `backend/app/strategy/builtin/t1_flash.py` - STRAT-08 T+1闪电: T 日竞价买入信号池 + EXIT/MAX_HOLD_DAYS=1 语义
- `backend/app/strategy/builtin/auction_intraday_confirm.py` - STRAT-09 盘中确认: open_gap 初筛 + minute_confirm (cum×time_factor, 不破开盘价)
- `backend/tests/test_auction_strategy_family_p2.py` - P2 测试: 11 tests (allround/t1/intraday/scoring/registry/grep gates)
- `docs/features.md` - 内置策略计数 21→27 + 竞价/盘前行补六策略
- `docs/strategy.md` - 内置策略计数 18→27 + 竞价/尾盘行补六策略
- `backend/app/strategy/prompts/strategy-guide.md` - META 契约字段表 + minute_confirm 契约小节 + pre_open 禁 EOD 列规则

## Decisions Made

- **顺序调整**：Task 1 有 `<precondition>`（21-01 引擎 seam 需合入）。初始检查 `minute_confirm` 计数=0 → 先执行 seam 无关的 Task 2（TDD RED+GREEN），21-01 Task 1 seam 合入（`f08f3b9`）后立即完成 Task 1；Task 3 的 27 计数校验等 21-01 P1 三文件落地后通过。最终 `grep -c minute_confirm`=10、builtin 计数=27。
- **TDD 门禁**：Task 1/2 均 tdd="true"。RED 提交 `4e4aa51`（测试文件，ImportError 失败）→ GREEN 提交 `3098097`/`d9849fc`。计划级 TDD 门禁（type: tdd）不适用于本 execute 计划。
- **gsd-tools no-op**：`gsd-tools query commit` 在本环境静默 no-op（无提交产出），按任务指令回退到 plain git 原子提交（已授权 fallback）。
- **共享测试文件**：`test_p2_scoring_weights_sum_to_one` 与 `test_no_third_registry_p2`（计划列在 Task 2 action 7/9）需要 `auction_intraday_confirm` 存在（三策略齐全），随 Task 1 提交（`d9849fc`）落盘。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_allround_fixture` 基准 fixture 误含 600105**
- **Found during:** Task 2 GREEN 验证
- **Issue:** 基准 fixture（`with_turnover=False`）含 600105（三因子全达标），导致核心 AND 断言 `hits == {"600101"}` 失败（实际含 600105）。
- **Fix:** 重构 `_allround_fixture`——基准 fixture 只含 600101–600104；600105（换手 1% 用例）仅在 `with_turnover=True` 变体出现。
- **Files modified:** backend/tests/test_auction_strategy_family_p2.py
- **Verification:** Task 2 GREEN 全部通过（5 passed）
- **Committed in:** `3098097`

**2. [Rule 1 - Bug] 宽范围 Edit 误删 `_t1_fixture` helper**
- **Found during:** Task 2 GREEN 验证
- **Issue:** 修复 fixture 的 SWAP 范围过宽，连带删除了 `_t1_fixture`，`test_t1_flash_no_lookahead` NameError。
- **Fix:** 重新插入 `_t1_fixture`（T 日四列 fixture）。
- **Files modified:** backend/tests/test_auction_strategy_family_p2.py
- **Verification:** Task 2 GREEN 全部通过
- **Committed in:** `3098097`

### Sequencing / Tooling Deviations

**3. [Sequencing] P2 scoring/registry 测试随 Task 1 提交**
- **原因:** 共享测试文件 + Task 1 precondition 阻塞；`test_p2_scoring_weights_sum_to_one`/`test_no_third_registry_p2` 断言三个 P2 策略的 META/发现，需 `auction_intraday_confirm` 存在。
- **Files modified:** backend/tests/test_auction_strategy_family_p2.py
- **Committed in:** `d9849fc` (Task 1 commit)

**4. [Tooling] gsd-tools commit no-op → plain git fallback**
- **原因:** `GSD_TOOLS=... node "$GSD_TOOLS" query commit ...` 静默无输出无提交；按任务契约"silently no-ops → fall back to plain git"执行。
- **Committed in:** 全部 4 个任务提交（`4e4aa51`/`3098097`/`d9849fc`/`a759252`）

**5. [Doc cleanup] features.md 竞价/盘前行去掉过时后缀**
- **原因:** 追加六策略时顺带移除 `(v1.3 竞价选股引擎)` 过时括注，行内容改为九策略完整列举。
- **Files modified:** docs/features.md
- **Committed in:** `a759252`

---

**Total deviations:** 5 (2 Rule 1 bug auto-fix, 1 sequencing, 1 tooling, 1 doc cleanup)
**Impact on plan:** 全部为保证正确性/可执行性的必要调整，无 scope creep；三策略功能与文档交付按计划完整落地。

## Issues Encountered

- **21-01 并行合并竞态**：`test_auction_strategy_family.py::test_golden_230_window` 在 21-01 修改 `golden_230.py` 描述中途失败一次（瞬时状态，描述缺"隔夜"）；21-01 Task 3 提交（`80c99a3`）后复跑全绿。非本计划回归。
- **gsd-tools 不可用**：`query commit` 与 `query state.load` 均静默 no-op，改用 plain git + 手写 SUMMARY 完成交付契约。
- **回归竞态**：Task 3 文档 27 计数在 21-01 P1 文件以 untracked 形式存在时即通过（FS 计数=27）；21-01 提交后重新确认仍为 27。

## User Setup Required

None - 零新增外部运行时依赖，无环境变量/外部服务配置。

## Next Phase Readiness

- 六策略（P1 三 + P2 三）全部落地，builtin 计数 27 与文档对账一致。
- 引擎 seam（`minute_loader`/`minute_confirm_fn` 单点截断 + `requires_auction_data` 短路 + `auction_volume_ratio` 受管列）已由 21-01 交付并被 STRAT-09 端到端消费验证。
- Phase 22 股池日期导航 / Phase 23 前端可直接消费 `time_window`/`evaluation_time`/`requires_auction_data` META 透传（API 自动携带）。
- `strategy-guide.md` 契约字段供 AI/自定义策略生成器引用，未来策略须遵守 pre_open 禁 EOD 列规则。

## Self-Check: PASSED

- 4 个新文件存在：`auction_allround.py`/`t1_flash.py`/`auction_intraday_confirm.py`/`test_auction_strategy_family_p2.py` ✓
- 4 个任务提交存在：`4e4aa51`/`3098097`/`d9849fc`/`a759252` ✓
- 全部测试绿：P2 11 tests + 回归 62 tests = 73 passed ✓
- Watchlist.tsx 未被本计划触碰 ✓

---
*Phase: 21-auction-strategy-family*
*Completed: 2026-08-05*
