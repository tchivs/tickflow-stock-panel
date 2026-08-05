---
phase: 21-auction-strategy-family
verified: 2026-08-05T08:02:02Z
status: passed
score: 9/9 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 21: 竞价策略族 (Auction Strategy Family) Verification Report

**Phase Goal:** 研究者可以运行六个第一性原理策略族——极速抢筹、竞价阿尔法、金色两点半、竞价全面策略、T+1闪电、盘中确认——全部作为 `strategy/builtin/` 内置策略自动发现，诚实命名、声明可计算时间窗，缺列时整池 fail-closed 为空。
**Verified:** 2026-08-05T08:02:02Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | STRAT-04 极速抢筹 (`auction_fast_grab`, pre_open, requires_auction_data=True)：甜点区 2.8%–3.5% + >7% 风险带剔除 + `auction_volume_ratio>=1.5` + `auction_amount>=200万`；缺列空池 | ✓ VERIFIED | `backend/app/strategy/builtin/auction_fast_grab.py` META+filter 参数化阈值全齐；`test_fast_grab_bands`（甜点区/风险带/量比/金额行为断言）+ `test_fast_grab_fail_closed`（probe 三态 → 短路空池）通过 |
| 2 | STRAT-05 竞价阿尔法 (`auction_alpha`, pre_open, requires_auction_data=False)：真列分支与派生分支按列存在性**互斥**、永不混用；probe 不可用 fail-closed 回退派生因子；scoring 超集权重和=1.0 + 缺列重归一化 | ✓ VERIFIED | `auction_alpha.py` filter 分支互斥实现；`test_alpha_branch_exclusive`（真列/派生阈值各自生效、同帧不混用）+ `test_alpha_scoring_renormalize`（权重和=1.0、缺真列不崩溃）通过；engine `_apply_scoring` 缺列跳过 + `weight/total_weight` 重归一化 (engine.py:558-562) |
| 3 | STRAT-06 金色两点半 (`golden_230`, post_close)：诚实归类尾盘/隔夜（id 无 `auction_` 前缀、描述含尾盘/隔夜/非竞价窗口、filter 无任何 `auction_*` 列引用）；分钟确认可选增强 | ✓ VERIFIED | `golden_230.py` META+filter+minute_confirm；`test_golden_230_window`（post_close/15:00/minute_confirm_required=False/描述断言 + W-5 grep 门禁 `"auction_" not in src`）+ `test_golden_230_minute_confirm_optional`（缺分钟数据 → 日线核心池仍产出）通过 |
| 4 | STRAT-07/08/09：`auction_allround`/`t1_flash`/`auction_intraday_confirm` 均落地；STRAT-09 引擎单点截断 `datetime.time() <= evaluation_time` 绝不 lookahead；T+1 次日卖出为 EXIT/MAX_HOLD_DAYS=1 语义、绝不参与池成员 | ✓ VERIFIED | 三策略文件全形；engine.py:385-387 单点截断；`test_intraday_truncation`（09:45 后 bar 断言未参与）+ `test_time_factor`（09:45→elapsed 15→tf 16.0 fixture）+ `test_intraday_minute_absent_empty` + `test_t1_flash_no_lookahead`（池只含 T 日列；EXIT_SIGNALS=["signal_ma20_breakdown"]/MAX_HOLD_DAYS=1）+ `test_allround_core_and_optional_turnover` 全部通过 |
| 5 | 每个策略声明可计算时间窗（pre_open/intraday/post_close）且所需列缺席返回空池（fail-closed）；策略仅经 `strategy/builtin/` 自动发现，无第三条注册轨道 | ✓ VERIFIED | 六策略 META 分别声明 pre_open×4 / intraday×1 / post_close×1；缺列 `pl.lit(False)` 守卫（fast_grab/alpha/allround/t1_flash/intraday）+ engine requires_auction_data 短路双保险；`_load_all` 仅 glob `strategy_dirs/*.py` (engine.py:175-192)；`test_no_third_registry` + `test_no_third_registry_p2`（builtin-only 发现、PRESET 零碰撞、API 恰好一次）通过 |
| 6 | 受管列 `auction_volume_ratio` 分母 = 前 5 个交易日 volume 均值（`get_enriched_history(trade_date, 6)` 过滤 `date < trade_date` 后 `tail(5)` 均值，**不含当日** EOD，PIT-safe）；无历史 → 列缺席 | ✓ VERIFIED | `auction_columns.py:_attach_auction_volume_ratio` (54-86) 实现；`test_auction_volume_ratio_prior_5d` + `test_auction_volume_ratio_excludes_today_eod`（当日 EOD 巨量不污染分母）+ `test_auction_volume_ratio_absent_without_history` 通过 |
| 7 | `auction_volume_ratio` 注册进 `ENRICHED_COLUMNS` + `ENRICHED_COLUMNS_BY_CATEGORY["auction"]`，**绝不进** `ENRICHED_STORAGE_COLS`/`_ALL_INDICATOR_COLS` | ✓ VERIFIED | pipeline.py:161（ENRICHED_COLUMNS）、184（BY_CATEGORY["auction"]）；STORAGE_COLS 14 列 (57-71) 与 _ALL_INDICATOR_COLS (315-329) 均无 auction_* 列；`test_auction_volume_ratio_registry_discipline` 四项断言通过 |
| 8 | 零新增外部运行时依赖 | ✓ VERIFIED | 六策略 + engine/auction_columns/pipeline 无任何外部新 import（grep 无 numpy/pandas/scipy/requests/httpx 等）；`pyproject.toml` 本阶段零改动；唯一新增 import 为内部 `app.market_time` 与 stdlib `datetime` |
| 9 | 文档计数对账：`docs/features.md`/`docs/strategy.md` 均声明 27 个内置策略，与 `builtin/*.py` 实际文件数 27 一致；`strategy-guide.md` 补齐时间窗/分钟确认契约字段 | ✓ VERIFIED | 两文档各含 `27 个内置策略`；`ls builtin/*.py | grep -vc __init__` = 27；两文档均列出六新策略；strategy-guide.md 含 time_window(1)/minute_confirm(6)/evaluation_time(5)/requires_auction_data(1) |

**Score:** 9/9 truths verified (0 present-but-behavior-unverified, 0 overrides)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | --------- | ------ | ------- |
| `backend/app/strategy/engine.py` | META setdefaults + time_window 白名单 + StrategyDef 三新字段 + requires_auction_data 短路 + minute_loader/confirm 单点截断 | ✓ VERIFIED | `_parse_eval_time` (96)；StrategyDef 字段 (132-134) 位于 file_path 之后（默认值尾随非默认）；`__init__` minute_loader (154)；setdefaults (213-216)；白名单校验 (219-223)；短路 (345-348)；分钟 seam (371-392)；list_strategies 透传 `{**s.meta, "source"}` (280) |
| `backend/app/services/auction_columns.py` | attach_auction_columns 增 auction_volume_ratio 派生（前5日均量, PIT-safe） | ✓ VERIFIED | `_attach_auction_volume_ratio` (54-86)；attach 调用 (128) |
| `backend/app/indicators/pipeline.py` | ENRICHED_COLUMNS + BY_CATEGORY["auction"] 注册 ratio 列；不进存储窄表/计算闭包 | ✓ VERIFIED | 161/184 注册；STORAGE/INDICATOR 集无 auction_* |
| `backend/app/strategy/builtin/auction_fast_grab.py` | STRAT-04 极速抢筹 | ✓ VERIFIED | 全形 + 参数化阈值 + fail-closed |
| `backend/app/strategy/builtin/auction_alpha.py` | STRAT-05 竞价阿尔法 | ✓ VERIFIED | 真列/派生分支互斥 + 权重和 1.0 |
| `backend/app/strategy/builtin/golden_230.py` | STRAT-06 金色两点半 | ✓ VERIFIED | post_close 诚实归类 + 可选分钟确认 |
| `backend/app/strategy/builtin/auction_allround.py` | STRAT-07 竞价全面 | ✓ VERIFIED | pre_open 白名单复合 + 可选换手(默认关) |
| `backend/app/strategy/builtin/t1_flash.py` | STRAT-08 T+1闪电 | ✓ VERIFIED | T 日池 + EXIT/MAX_HOLD_DAYS=1 语义 |
| `backend/app/strategy/builtin/auction_intraday_confirm.py` | STRAT-09 盘中确认 | ✓ VERIFIED | open_gap 初筛 + 引擎截断分钟确认 + time_factor |
| `backend/tests/test_auction_strategy_family.py` | P1 引擎 seam + 受管列 + 三策略测试 | ✓ VERIFIED | 16 tests，全部通过 |
| `backend/tests/test_auction_strategy_family_p2.py` | P2 三策略 + 截断/time_factor 回归 | ✓ VERIFIED | 11 tests，全部通过 |
| `docs/features.md` / `docs/strategy.md` | 策略计数 27 对账 + 六策略补写 | ✓ VERIFIED | 各 1 处 `27 个内置策略`；六策略行存在 |
| `backend/app/strategy/prompts/strategy-guide.md` | 时间窗/分钟确认契约字段 | ✓ VERIFIED | time_window/minute_confirm/evaluation_time/requires_auction_data 字段齐全 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `requires_auction_data` META | engine.run() 短路 | `if s.meta.get(...) and "auction_volume" not in df.columns` (engine.py:345-348) | WIRED | 短路返回空 StrategyResult；策略侧 `pl.lit(False)` 为第二层 |
| `minute_confirm_fn`+`evaluation_time` META | 引擎单点截断 | `truncated = minute.filter(datetime.time() <= s.evaluation_time)` (engine.py:385-387) | WIRED | STRAT-09 端到端消费：日线初筛 → 分钟确认 → 池收窄 |
| `auction_volume_ratio` 注入 | 策略 filter 真列分支 | `attach_auction_columns` (auction_columns.py:89-151) → `_attach_auction_volume_ratio` → `get_enriched_history(trade_date,6)` | WIRED | fast_grab/allround/t1_flash/alpha 真列分支消费 |
| t1_flash EXIT 语义 | 池成员计算 | `EXIT_SIGNALS=["signal_ma20_breakdown"]` + `MAX_HOLD_DAYS=1`，filter 只引用 T 日 as-of 列 | WIRED | `test_t1_flash_no_lookahead` 断言池列集无 T+1/EOD 参与 |
| docs 计数 | `builtin/*.py` 实际文件数 | 27 = 27 | WIRED | features.md/strategy.md 对账一致 |
| `strategy-guide.md` 契约 | engine `_load_file` setdefault | 文档字段与 engine.py:213-216 一致 | WIRED | AI/自定义策略生成可消费 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `auction_volume_ratio` 派生 | `_prior_5d_avg_volume` | `repo.get_enriched_history(trade_date, 6)` → `date < trade_date` → `tail(5).mean()` | ✓ 真实历史 volume 均值（非静态/非硬编码）；无历史 → 列缺席 | ✓ FLOWING |
| `auction_intraday_confirm.minute_confirm` | `cum_volume`/`volume_scale` | 引擎截断分钟帧 → `volume.sum() * time_factor` | ✓ 真实分钟 bar 统计；time_factor 16.0 fixture 锁死 | ✓ FLOWING |
| `auction_fast_grab` 池成员 | `open_gap`/`auction_volume_ratio`/`auction_amount` | 受管增强列注入 + 参数化阈值 | ✓ 真实竞价列 + PIT-safe 量比 | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 全量目标测试（6 文件） | `.venv/bin/python -m pytest tests/test_auction_strategy_family.py tests/test_auction_strategy_family_p2.py tests/test_auction_probe.py tests/test_auction_columns.py tests/test_auction_sync.py tests/test_auction_strategies.py -q` | `73 passed, 2 warnings in 1.44s` | ✓ PASS |
| 行为关键测试（9 个命名测试） | `pytest <9 named tests> -q`（截断/无未来/PIT-safe/分支互斥/甜点区/诚实归类/T+1无lookahead/time_factor/缺分钟空池） | `9 passed in 0.24s` | ✓ PASS |
| 测试文件计数对账 | `pytest --collect-only` 两文件 | family=16, p2=11（合计 27 阶段测试，+46 回归 = 73） | ✓ PASS |

### Probe Execution

N/A — Phase 21 无 probe 脚本（`find scripts -path '*/tests/probe-*.sh'` 无输出；VALDATION.md 无 probe 声明）。自动化验证由 pytest 单测承担。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| STRAT-04 | 21-01 | 极速抢筹 builtin + 甜点区/风险带 + 诚实命名 | ✓ SATISFIED | auction_fast_grab.py + test_fast_grab_bands + test_fast_grab_fail_closed |
| STRAT-05 | 21-01 | 竞价阿尔法，probe 可用真实列 / 否则派生 fail-closed | ✓ SATISFIED | auction_alpha.py + test_alpha_branch_exclusive + test_alpha_scoring_renormalize |
| STRAT-06 | 21-01 | 金色两点半诚实归类尾盘/隔夜 | ✓ SATISFIED | golden_230.py + test_golden_230_window + W-5 门禁 |
| STRAT-07 | 21-02 | 竞价全面全因子复合 | ✓ SATISFIED | auction_allround.py + test_allround_core_and_optional_turnover + test_allround_fail_closed |
| STRAT-08 | 21-02 | T+1闪电 次日早盘卖出为 EXIT 语义 | ✓ SATISFIED | t1_flash.py + test_t1_flash_no_lookahead + test_t1_flash_fail_closed |
| STRAT-09 | 21-02 | 盘中确认分钟帧截断 evaluation_time 绝不 lookahead | ✓ SATISFIED | auction_intraday_confirm.py + test_intraday_truncation + test_time_factor + test_intraday_minute_absent_empty |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | 无 TBD/FIXME/XXX 债务标记 | — | — |
| — | — | 无 placeholder/coming soon/not yet implemented | — | — |
| — | — | 无空实现（return null/{}/[] / 空 handler / console.log-only） | — | — |
| — | — | 无硬编码空数据（`= []` / `= {}` / 空 props） | — | — |

**Informational (非阻断，流程状态而非代码缺口)：**
1. `.planning/REQUIREMENTS.md` 中 STRAT-07/08/09 仍标 `Open`（行 60-62）——代码已交付且测试全绿，该标记属阶段完成后的书面对账步骤（phase-completion bookkeeping），不构成代码缺口。
2. `.planning/ROADMAP.md` Phase 21 显示 `1/2 plans executed`、21-02 复选框未勾——两计划均有 SUMMARY 与提交（`f1d7dbc`/`a759252`/`d9849fc`/`3098097`/`4e4aa51`），为状态书面对账滞后。
3. `21-VALIDATION.md` 仍为 draft、`nyquist_compliant: false` 未签核——验证策略文档未完成签核流程，但其规定的测试基础设施已实际落地并通过（Wave 0 两测试文件存在、回归门禁全绿）。

### Human Verification Required

无。本阶段为后端纯代码阶段：
- 两 PLAN `backstops: []`（无 backstop 真相需人工裁决）；
- 无 `<verify><human-check>` 延后项；
- 全部 9 条 must-have 真相均有代码存在性 + 行为测试证据（行为相关真相——无 lookahead、PIT-safe、分支互斥——均有通过的行为测试）。
- VALIDATION.md 唯一 manual-only 项（策略卡片/API 透传 META 字段的可视呈现）明确归属 Phase 23 前端面（`list_strategies()` DTO 契约由 test_no_third_registry 断言保持绿），非 Phase 21 缺口。

### Gaps Summary

无阻断性缺口。9/9 must-have 真相在代码与测试中全部证实；73 项目标测试全绿；硬边界（PIT-safe 量比、注册纪律、零新增依赖、文档 27 对账、builtin-only 发现）逐一核实。仅存的差异为 REQUIREMENTS/ROADMAP/VALIDATION 三处流程状态标记滞后（见 Anti-Patterns informational），与目标达成无关，建议在阶段收尾书面对账时一并刷新。

---

_Verified: 2026-08-05T08:02:02Z_
_Verifier: Claude (gsd-verifier)_
