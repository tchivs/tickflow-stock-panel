---
phase: 29-auction-validation
plan: 2
subsystem: api
tags: [polars, report-service, forward-stats, branch, honest-empty, BT-03, BT-04, BT-05]

requires:
  - phase: 29-auction-validation
    provides: "BT-02 attach_auction_columns_range(df, start, end, repo) -> (df, enabled_dates) — 区间注入原语 (29-01)"
  - phase: 20-auction-data
    provides: kline_auction/date=* lake + probe verdict types (auction_probe)
  - phase: 21-auction-strategy-family
    provides: 9 竞价族策略定义 (engine builtin, META params + filter_fn)
provides:
  - "BT-03 AuctionValidationService.build_report — 窗口解析/回夹回显、warmup 面板装载、9 策略枚举+branch、候选掩码镜像、per_date、诚实 gate"
  - "BT-04 前瞻口径锁死 — 全局交易日历 next-date + 三公式 + n_missing_outcomes (绝不 0 填)"
  - "BT-05 branch 互斥标注 — 4 real 恒 real (湖空 n_dates==0 不落 derived), auction_alpha real|derived 翻转, 4 eod"
affects: [29-03-auction-validation, RESEARCH 2.2 report-service contract]

actuals:
  tokens: 12406        # chars/4 over realized diff (49625 bytes / 4); estimate 63000 → 大幅低实现 (向量化+镜像简化, 无端点/守卫面)
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Report assembly: window parse+clamp (requested_*/effective_* dual echo, no 186d guard D-06) -> warmup panel load (get_enriched_range fast path, W1 clamp) -> attach_auction_columns_range injection -> enumeration -> branch -> mirrored mask -> forward stats"
    - "Forward stats: global trading-calendar next-date via calendar join (never per-symbol shift(-1)); per-metric independent n; missing outcomes counted never filled"
    - "Candidate mask: semantic mirror of backtest/strategy.py:522-570 filter_fn path (fill_null(False).cast(Boolean), fail-closed all-False on exception) — documented anchor, never imported"

key-files:
  created:
    - backend/app/services/auction_validation.py
    - backend/tests/test_auction_validation_report.py
  modified: []

key-decisions:
  - "skipped_ids 语义 (计划 action 4e 与 Task 3 Test 3 张力调和): 请求集不含任何可解析竞价族策略 → 回落默认竞价族范围 (未知 id 记 skipped_ids, 已知竞价族仍正常报告); 显式 [] → strategies: []; None → 9 族 ∩ engine (引擎缺失的族 id 也记 skipped)"
  - "probe 在 build_report 顶部解析一次, 所有路径 (含 enriched_unavailable) 均携带 probe 字段 — 200 形全形状一致 (29-03 端点集成测试空湖全形状前置)"
  - "全局日历 next-date 用 calendar 帧 join 而非 map_dict — polars 1.40.1 无 Series.map_dict; 结果日全部为 null 时 outcome_date 列降级 Null 型, 显式 cast(pl.Date, strict=False) 修复 join schema (Rule 1 bug)"
  - "docstring 字面量纪律 (BT-06 预埋): 模块 docstring/注释避开全部禁 token (含 run_all/screener 字面串), grep 0 命中 — 29-03 AST 守卫就绪"

requirements-completed: [BT-03, BT-04, BT-05]

coverage:
  - id: R1
    description: "空湖诚实报告 (BT-01/BT-05): data_gate==empty + no_auction_partitions, 4 real n_dates==0 branch==real (绝不落 derived), auction_alpha derived + eod 真实统计, probe 透传, window/coverage 齐全"
    requirement: BT-03
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_empty_lake_honest_report_all_9_strategies"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_enriched_unavailable_empty_cache"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_probe_passthrough_not_gate"
        status: pass
    human_judgment: false
  - id: R2
    description: "BT-04 前瞻口径锁死 — 三公式手算断言 / 停牌缺失 n_missing_outcomes / 全局日历 next-date vs shift(-1) / close_T 边界独立 n"
    requirement: BT-04
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_forward_formula_next_day_returns"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_outcome_missing_halted_symbol_no_zero_fill"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_outcome_global_calendar_next_date_not_shift"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_forward_close_t_boundary_independent_n"
        status: pass
    human_judgment: false
  - id: R3
    description: "窗口回夹回显 (D-06 + W1) / skipped_ids + 空列表 / auction_alpha branch 翻转互斥 / per-strategy coverage + per_date / minute_confirm / symbols 裁剪"
    requirement: BT-05
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_window_clamp_requested_effective_echo"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_auction_alpha_branch_flip_mutual_exclusion"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_skipped_ids_and_empty_list"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_per_strategy_coverage_and_minute_confirm"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_validation_report.py#test_symbols_filter_limits_evaluation"
        status: pass
    human_judgment: false
  - id: R4
    description: "29-01 契约回归 — attach_auction_columns_range 全套 14 测试保持绿"
    requirement: BT-03
    verification:
      - kind: unit
        ref: "backend/tests/test_attach_auction_columns_range.py (14 tests, full file)"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-08-06
status: complete
---

# Phase 29 Plan 2: AuctionValidationService 报告装配 (BT-03/BT-04/BT-05) Summary

**只读竞价策略历史验证报告服务 `AuctionValidationService.build_report` 落地: 窗口解析/回夹双字段回显 (D-06, W1 夹 warmup) → warmup 面板装载 → attach_auction_columns_range 注入 → 9 策略枚举 + 互斥 branch (BT-05) → 候选掩码镜像 (backtest/strategy.py:522-570, 绝不 import) → 前瞻统计 (BT-04 全局日历 next-date + 三公式 + n_missing_outcomes) → per_date → 诚实 gate 报告 — 12 服务级测试 + 14 原语回归全绿, 零新依赖、零写、docstring 无禁 token (BT-06 守卫就绪).**

## Performance

- **Duration:** 55 min
- **Started:** 2026-08-06T16:20Z
- **Completed:** 2026-08-06T17:15Z
- **Tasks:** 3 (tracer + 2 expansion)
- **Files modified:** 2 (both created by this plan)

## Accomplishments
- `backend/app/services/auction_validation.py` — `AuctionValidationService.build_report` 全栈装配 (镜像 premarket_pool probe 注入点 + pool_hub 权威回显 + screener 枚举形):
  - **窗口 (D-06)**: end 缺省 = enriched 缓存最新日, start 缺省 = end−120 自然日; 回夹到 `[cache_min, cache_max]`; `requested_*`/`effective_*` 双字段回显; 缓存空 → 回退扫 `kline_daily_enriched/date=*`; 绝不套 186 天 guard。**W1 (PLAN-CHECK)**: `warmup_start = max(start − 14d, cache_min)` — 近缓存边界的超覆盖请求产出回夹报告而非误报 enriched_unavailable (Task 3 Test 1 锁死)。
  - **诚实空态**: enriched_unavailable / no_dates_in_window / no_auction_partitions 全部 200 形 dict, 绝不 404/500/0 填; `strategies==[]` 仅当 enriched 窗口本身空。
  - **枚举 (D-07)**: 9 竞价族 id ∩ engine; 参数恒 META 默认; 未知 id → skipped_ids; 请求集无任何可解析族策略 → 回落默认族范围 (已知竞价族仍正常报告)。
  - **branch (BT-05)**: 4 个 requires_auction_data 恒 real (湖空 n_dates==0 不调掩码, 绝不落 derived); auction_alpha real|derived 按 enabled 非空翻转; 4 个 EOD 代理恒 eod; 每策略单 branch。
  - **候选掩码**: `_build_candidate_mask` 语义镜像 backtest/strategy.py:522-570 filter_fn 路径 (fill_null(False).cast(Boolean), 异常 fail-closed 全 False 仅记日志), docstring 标注锚点, 绝不 import app.backtest。
  - **前瞻 (BT-04)**: 结果日 = 全局交易日历 next-date (calendar 帧 join, 绝不 per-symbol shift(-1)); 三公式 open_T>0 / close_T>0 守卫; 缺失 → n_missing_outcomes 且统计排除, 绝不 0 填/前向填充; 每指标独立 n; 无有效行 → mean/median/win_rate 全 null。
  - **import 面**: 仅 polars + stdlib (datetime/logging/collections.abc) + auction_columns/auction_probe/tickflow.repository/strategy.engine — 白名单内; 全文件 0 个禁 token 字面串 (BT-06 守卫就绪)。
- `backend/tests/test_auction_validation_report.py` — 12 服务级测试 (hermetic: repo_env + 直接 seed `_enriched_history_cache` + 手工写 kline_auction 分区 + probe 注入固定 verdict), 覆盖空湖诚实报告 / enriched 空态 / probe 透传 / BT-04 四测试 / 窗口回夹 / branch 翻转 / skipped_ids / coverage+per_date / minute_confirm / symbols 裁剪。

## Task Commits

1. **Task 1: AuctionValidationService 空湖诚实报告垂直切片 (tracer, tdd)** —
   - `0549e60` (test: RED — 空湖诚实报告 / enriched 空态 / probe 透传 3 测试)
   - `a739041` (feat: GREEN — 服务模块全栈实现)
2. **Task 2: BT-04 前瞻口径锁死** — `3f4f815` (test: 三公式手算 / 停牌缺失 / 全局日历 vs shift(-1) / close_T 边界)
3. **Task 3: 窗口回夹/skipped_ids/空列表/branch 翻转/coverage/minute_confirm 收尾** — `cde0a9f` (test: 5 测试 + W1 断言)

## Files Created/Modified
- `backend/app/services/auction_validation.py` — 新, ~437 行: `AuctionValidationService` (build_report/_resolve_strategy_ids/_evaluate_strategy/_build_per_date/_forward_stats/_enriched_coverage/_empty_report) + 模块级 `_build_candidate_mask`/`_aggregate_metric`/`_null_metric`; 模块 docstring 声明只读/零写/零执行/不套 186 天 guard/掩码镜像锚点
- `backend/tests/test_auction_validation_report.py` — 新, ~635 行: hermetic helpers (repo_env/_write_auction_partition/_auction_rows/_available_verdict/_make_engine/_seed_enriched_cache) + 12 测试

## Decisions Made
- **skipped_ids 语义调和** (Rule 3, 计划 action 4e 与 Task 3 Test 3 的字面张力): 实现取「selector hint, 绝不静默清空」— 非空请求集不含任何可解析竞价族策略 → 回落默认 9 族范围 (未知 id 记 skipped, 已知竞价族仍正常报告); 显式 `[]` → `strategies: []`; `None` → 9 族 ∩ engine (引擎缺失的族 id 也记 skipped_ids)。同时满足 BT-03 must-have 与计划测试字面断言。
- **probe 顶部解析一次**: 所有路径 (含 enriched_unavailable) 的响应均携带 `probe` 字段 — 与 29-03 端点「空湖 200 全形状」断言前置一致。
- **calendar 帧 join 替代 map_dict**: polars 1.40.1 无 `Series.map_dict`/`Expr.map_dict` (实测 AttributeError); 全局日历 next-date 用 `pl.DataFrame({date, outcome_date})` 左联实现, 等价且 schema 可控。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 全部结果日缺失时 outcome_date 列降级 Null 型 → join SchemaError**
- **Found during:** Task 2 (停牌缺失测试)
- **Issue:** 单日窗口 (结果日不存在) 时, calendar join 后 hits 的 outcome_date 全为 null, polars 1.40.1 把该列降级为 Null 型; 与结果面板 (Date 型) join 报 `datatypes of join keys don't match`.
- **Fix:** calendar 帧 outcome_date 显式 `cast(pl.Date)`, join 后 hits 侧 `cast(pl.Date, strict=False)` 兜底 (容忍全 null). 
- **Files modified:** backend/app/services/auction_validation.py
- **Verification:** `pytest tests/test_auction_validation_report.py -k "forward or outcome or missing or formula or halt" -x -q` → 4 passed
- **Committed in:** 3f4f815 (Task 2 commit)

**2. [Rule 1 - Bug] 测试 fixture 手算错误 (600000 close = 20×1.05 = 21.0 而非 20.5)**
- **Found during:** Task 2 (公式断言)
- **Issue:** seed helper 默认 `close = open × 1.05`; 600000 的 close_T = 21.0, 手算公式按 20.5 预期 → open_gap_outcome 实际 21.0/21.0−1 = 0.0 (实现正确, 测试期望错).
- **Fix:** fixture 对 600000 T 行显式 override `close: 20.5`, 恢复计划的手算公式值.
- **Files modified:** backend/tests/test_auction_validation_report.py
- **Verification:** 同 1 → 4 passed
- **Committed in:** 3f4f815 (Task 2 commit)

**3. [Rule 3 - Blocking] 计划 action 4e 与 Task 3 Test 3 的 skipped_ids 语义张力**
- **Found during:** Task 1 (实现前设计)
- **Issue:** action 4e (`ids = 族 ∩ 请求集` → `strategy_ids=["no_such_strategy"]` 得 `strategies: []`) 与 Test 3 字面断言 (`skipped_ids==["no_such_strategy"]` 且已知竞价族仍正常报告) 冲突.
- **Fix:** 取 Test 3 字面语义 — 非空请求集全未知时回落默认族范围; 详见 Decisions. 两处断言均绿.
- **Files modified:** backend/app/services/auction_validation.py
- **Verification:** `test_skipped_ids_and_empty_list` passed
- **Committed in:** a739041 (Task 1 GREEN commit)

---

**Total deviations:** 3 auto-fixed (2 bugs + 1 plan-internal contract tension)
**Impact on plan:** None — 全部为执行期修正, 无范围变更; 验收口径 (BT-03/BT-04/BT-05) 全部满足.

## TDD Gate Compliance

- Plan frontmatter `type: execute` (not `tdd`) → plan-level RED/GREEN/REFACTOR gate sequence not applicable.
- Task 1 (`tdd="true"`): RED commit `0549e60` (服务缺失 → ModuleNotFoundError) → GREEN commit `a739041` (服务实现 → 3 passed) — both present in order. ✅
- Task 2 (`tdd="true"`, **test-only files**): 被测 feature (forward-stats) 已由 Task 1 交付, 测试即写即绿 — RED 无法构造 (与 29-01 Task 2 同型); 记为单 `test(...)` commit. 测试暴露 1 个真 bug (Null 型 join) 并已修入服务 (deviation 1). ✅

## Issues Encountered
- polars 1.40.1 无 `map_dict` (Expr 与 Series 均无) — calendar 帧 join 替代 (Decisions).
- 计划 estimate 63k tokens vs actual 12.4k (chars/4) — 服务端装配面无端点/守卫/文档, 且大量代码为镜像既有模式; 实际实现显著小于估算 (confidence low, 记录 actuals 供 ADR-2629 校准).

## Known Stubs
None — 12 测试全部断言真实值; 无占位/跳过/未接线数据源.

## Threat Flags
None — 新增面为只读投影: 窗口回夹 (T-29-02-01), 零写+import 白名单+0 禁 token (T-29-02-02), 前瞻不 0 填 (T-29-02-03), real 不降级 (T-29-02-04), 单面板向量化+symbols 裁剪 (T-29-02-05), filter 异常仅日志 (T-29-02-06) — 全部按 threat_model mitigate 实现并由测试锁死.

## User Setup Required
None.

## Next Phase Readiness
- 29-03 (BT-01/BT-06) 消费 `AuctionValidationService(repo, engine, probe_resolver=None).build_report(*, start, end, strategy_ids, symbols)` 契约 + 本测试文件扩展端点用例 (同文件跨 wave, depends_on 排序无冲突); 服务模块 docstring/注释 0 禁 token → AST 守卫直接就绪.
- 服务模块 import 面 = {polars, collections.abc, datetime, logging, __future__} + {auction_columns, auction_probe, tickflow.repository, strategy.engine} — 29-03 Test 6 白名单前置满足.

## Self-Check: PASSED
- FOUND: backend/app/services/auction_validation.py, backend/tests/test_auction_validation_report.py
- FOUND commits: 0549e60 (RED), a739041 (GREEN), 3f4f815 (Task 2), cde0a9f (Task 3)
- Final suites: test_auction_validation_report.py 12 passed; test_attach_auction_columns_range.py 14 passed (29-01 契约回归)

---
*Phase: 29-auction-validation*
*Completed: 2026-08-06*
