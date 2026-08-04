---
phase: 17-auction-strategy-family
verified: 2026-08-04T00:00:00Z
status: passed
score: 9/9 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 17: 竞价策略族 (Auction Strategy Family) Verification Report

**Phase Goal:** Researchers can run at least 3 first-principles auction strategies (竞价多头, 盘前强势量化, 早盘之星) as builtin strategy files auto-discovered by the engine, each reporting per-stock factor hits without adding a third registration track.
**Verified:** 2026-08-04
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### 目标后向验证 (Goal-Backward)

从 ROADMAP Phase 17 的三个 Success Criteria 出发，验证代码库中确实实现了目标。SUMMARY.md 的声明不作为证据；以下全部结论来自对实际代码的直接检查与真实测试运行。

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 3 个第一性原理竞价策略以 builtin 文件存在于 `strategy/builtin/`，被 `StrategyEngine` 自动发现且 `source == "builtin"`，诚实的第一性原理因子定义 | ✓ VERIFIED | 三个文件 `auction_bullish.py` / `auction_preopen_quant.py` / `auction_early_star.py` 均含完整 `META`（id/name/description/tags/params/scoring）+ `filter()`。实测 `StrategyEngine(enriched_loader=…, strategy_dirs=[app/strategy/builtin])` 发现全部 3 个，`source=="builtin"`，`load_errors==[]`；`test_auction_strategies_auto_discovered_by_engine` 通过。描述为第一性原理中文文案（如 "开盘涨幅 (open/prev_close−1) 与日涨幅 (change_pct) 双动量同时达标"），无专有配方宣称 |
| 2 | 每个竞价策略返回的股池行携带受管列 开盘涨幅 (`open_gap`) 与涨跌幅 (`change_pct`)，永不从 raw bar 重推 | ✓ VERIFIED | 三个 `filter()` 只引用 `pl.col("symbol"/"open_gap"/"change_pct"/"vol_ratio_5d")`，无 raw bar rejoin/shift；`test_auction_strategies_only_use_governed_columns` 在仅含受管列的 fixture 上运行全部过滤器；`test_auction_bullish_run_returns_pool_with_governed_columns` 断言 run() 返回行含 `open_gap`/`change_pct`。无任何 09:30 连续 bar 标注为集合竞价数据 |
| 3 | strategies API 每个竞价 id 恰好列出一次且 `source: "builtin"`；id 与 `PRESET_STRATEGIES` 无碰撞；无第三条注册轨道 | ✓ VERIFIED | `screener.py strategies()` 的 `seen_ids` 去重循环（preset 优先、engine 其次）；实测 `PRESET_STRATEGIES` 12 个键中无 auction id；`grep` 全 `backend/app` 确认三个 id 仅出现在 `strategy/builtin/`；`test_auction_strategies_appear_once_in_strategies_api` / `test_auction_ids_never_collide_with_presets` / `test_no_third_registry_track` 全部通过 |
| 4 | 多因子竞价策略评分权重和恒为 1.0（沿用 strong_open.py 约定） | ✓ VERIFIED | 手工核算：bullish `0.5+0.5=1.0`、preopen `0.4+0.6=1.0`、early_star `0.5+0.5=1.0`；`test_auction_strategy_scoring_weights_sum_to_one` 断言 `pytest.approx(1.0)` 通过 |
| 5 | 无前收盘 (null `open_gap`) 的股票 fail-closed，永不误入选 | ✓ VERIFIED | Polars 中 `null >= 阈值` 求值为 null，filter 丢弃该行；`test_auction_bullish_requires_both_momentum` 断言 null `open_gap` 符号不在命中集；`test_auction_preopen_strength_requires_gap_and_volume` 同样断言 null `vol_ratio_5d` 不入选 |
| 6 | 策略族结果可报告 关联因子：每行携带 `hit_factors`，由纯函数聚合得出 | ✓ VERIFIED | `factor_hits.py` 提供 `HIT_FACTORS_COLUMN="hit_factors"`、`build_factor_hits`、`attach_factor_hits`（纯模块，无 I/O、不 import 策略文件）；`test_build_factor_hits_overlap_aggregation` / `test_attach_factor_hits_adds_column_without_mutation` 通过 |
| 7 | 聚合确定且服务端推导——标的只在其所属策略的结果行中才进入 hit_factors（无合成命中） | ✓ VERIFIED | `build_factor_hits` 只读 `result["rows"]` 的 `symbol` 成员关系；`test_build_factor_hits_deterministic_order`（逆序添加仍按码点排序）、`test_build_factor_hits_symbol_with_no_hits_absent`、`test_build_factor_hits_default_resolver_is_identity` 通过 |
| 8 | 关联因子为增量字段、向后兼容：`run_all` 响应 `total`/`as_of` 不变，`hit_factors` 为每行额外字段 | ✓ VERIFIED | `screener.py run_all` 在行消毒后、cache write 前追加 `hit_factors`（行 507-514），不触碰 `total`/`as_of`；`test_run_all_rows_carry_hit_factors` 断言两策略重叠标地携带两个显示名、total/as_of 不变、未命中标的不出现 |
| 9 | 契约经重叠策略 fixture 单测并在 screener API 接通 | ✓ VERIFIED | `test_factor_hits.py` 6 个测试全部通过，其中 `test_run_all_rows_carry_hit_factors` 以 FastAPI TestClient 驱动真实 `POST /api/screener/run_all` 端点，端到端证明行级 `hit_factors` 报告 |

**Score:** 9/9 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | --------- | ------ | ------- |
| `backend/app/strategy/builtin/auction_bullish.py` | META + filter，竞价多头 | ✓ VERIFIED | 严格 AND 双动量（open_gap≥2% AND change_pct≥2%），scoring 权重和 1.0，null fail-closed |
| `backend/app/strategy/builtin/auction_preopen_quant.py` | 盘前强势量化 | ✓ VERIFIED | open_gap≥3% AND vol_ratio_5d≥1.5 双阈值 |
| `backend/app/strategy/builtin/auction_early_star.py` | 早盘之星 | ✓ VERIFIED | open_gap/change_pct OR 组合 + 列守卫概念佐证（默认关闭） |
| `backend/app/strategy/factor_hits.py` | build_factor_hits + attach_factor_hits | ✓ VERIFIED | 纯函数聚合，确定性排序，不改输入行 |
| `backend/app/api/screener.py` | run_all 关联因子 wiring + 名称解析 | ✓ VERIFIED | `_strategy_display_name` 解析器 + run_all 后置处理（行 397-407, 507-514） |
| `backend/tests/test_auction_strategies.py` | 11 个 fixture 测试 | ✓ VERIFIED | 全部通过（见测试结果） |
| `backend/tests/test_factor_hits.py` | 5 个纯函数 fixture + 1 个 API 回归 | ✓ VERIFIED | 全部通过（见测试结果） |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `strategy/builtin/auction_*.py` filter | 受管列 open_gap/change_pct/vol_ratio_5d | `pl.col(...)` 仅引用受管列 | WIRED | 无 raw bar 引用；governed-column-only fixture 测试证明 |
| builtin 策略文件 | `StrategyEngine._load_all` | builtin 目录自动发现，source 推导 | WIRED | 实测 3 个策略全部加载，`source=="builtin"`，`load_errors==[]` |
| 引擎策略列表 | `/api/screener/strategies` | `seen_ids` 去重循环 | WIRED | preset 优先、engine 其次跳过 seen；API 测试断言每 id 恰好一次 |
| STRAT-03 去重 | `PRESET_STRATEGIES` | `screener.py strategies()` seen_ids | WIRED | 实测 12 个 preset 键无 auction id 碰撞 |
| `engine.run_all()`/`run()` 结果行 | `build_factor_hits` → `attach_factor_hits` | run_all 后置处理 | WIRED | 行 509-514；API 回归测试端到端证明 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| run_all 结果行 | `rows[].hit_factors` | `build_factor_hits` 从各策略 `results[sid]["rows"]` 的 symbol 成员关系聚合 | ✓ | `test_run_all_rows_carry_hit_factors` 验证真实端点返回重叠标地的双显示名 hit_factors，非空非硬编码 |
| strategies 列表 | auction 策略条目 | `engine.list_strategies()`（真实 builtin 目录） | ✓ | 实测返回 3 个 auction 策略，id/name/source 均真实 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 引擎自动发现 3 个竞价策略 | `.venv/bin/python -c "StrategyEngine(...app/strategy/builtin).list_strategies()"` | 3 个 `(auction_bullish,builtin,竞价多头)` 等，`load_errors==[]` | ✓ PASS |
| PRESET 无碰撞 | `.venv/bin/python -c "import PRESET_STRATEGIES; collisions=[]"` | 12 个 preset 键，0 碰撞 | ✓ PASS |
| strategies API 每 id 恰好一次 | `pytest test_auction_strategies.py::test_auction_strategies_appear_once_in_strategies_api` | PASSED | ✓ PASS |
| run_all 行携带 hit_factors | `pytest test_factor_hits.py::test_run_all_rows_carry_hit_factors` | PASSED | ✓ PASS |

### Probe Execution

Phase 17 非迁移/工具链阶段，PLAN 未声明 probe 脚本，无 `scripts/*/tests/probe-*.sh` 约定可执行。SKIPPED。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| STRAT-01 | 17-01-PLAN | Researcher 可运行 ≥3 个第一性原理竞价策略，builtin 文件 + 引擎发现 + 诚实因子定义 | ✓ SATISFIED | Truths 1-2,4-5；3 个 builtin 文件 + 引擎发现 + 受管列 fixture 测试 |
| STRAT-02 | 17-02-PLAN | 每策略暴露 per-stock factor-hit 标签，结果行可报告关联因子 | ✓ SATISFIED | Truths 6-9；`factor_hits.py` 纯聚合 + run_all 行级 `hit_factors` |
| STRAT-03 | 17-01-PLAN | 无第三条注册轨道；strategies API 去重 PRESET_STRATEGIES | ✓ SATISFIED | Truth 3；`seen_ids` 去重 + 无碰撞实测 + 无第三注册表扫描 |

无孤立需求（REQUIREMENTS.md 中 STRAT-01..03 均被两 plan 声明覆盖）。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | 无 TBD/FIXME/XXX/TODO/PLACEHOLDER/placeholder 标记 | — | 无 |
| — | — | 无空实现 / 硬编码空数据 / 仅 console.log 实现 | — | 无 |

### Frontend 未触碰确认

Phase 后端专用：`git diff HEAD~8..HEAD -- frontend/` 为空，最近 8 笔提交（含 17-01/17-02 全部 5 笔实现提交 + 2 笔 docs）未修改任何前端文件。

### Human Verification Required

无。本阶段为后端专用（策略文件、聚合模块、API wiring），全部 truth 均由自动化测试直接驱动真实行为（引擎加载、TestClient 端点调用、过滤器 fixture 语义），无 UI/视觉/外部服务/实时行为类需要人工判断的项目。

### Gaps Summary

无 gaps。9/9 must-haves 全部以代码存在性 + 行为测试双重验证。真实测试结果：主套件 `test_auction_strategies.py + test_factor_hits.py` **17 passed**；相关回归套件 `test_open_gap_factor.py + test_screener_etf.py + test_auction_probe.py + test_strategy_code_save.py` **32 passed**；合计 **49 passed，0 failed**。

---

_Verified: 2026-08-04_
_Verifier: Claude (gsd-verifier)_
