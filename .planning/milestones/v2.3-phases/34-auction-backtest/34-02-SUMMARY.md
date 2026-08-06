# 34-02 Summary — 验证报告激活 + 诚实 symbol 覆盖 (BT-08)

**Phase:** 34-auction-backtest · **Plan:** 34-02 · **Executor:** ExecutorP3402 · **Date:** 2026-08-06
**Status:** ✅ COMPLETE — 3/3 tasks, verification green, single atomic commit

## Deliverables

| Task | Artifact | Commit |
|------|----------|--------|
| 1 — coverage.symbols 子块 + per-strategy n_symbols_covered/n_symbols_hit | `backend/app/services/auction_validation.py` (extended) | committed below |
| 2 — 248 分区激活证明 + 4 新用例 | `backend/tests/test_auction_validation_report.py` (appended, 20 total) | committed below |
| 3 — D-06 验证 + 守卫/回归全量收尾 | 纯验证, 零源码改动 | committed below |
| Summary | `.planning/phases/34-auction-backtest/34-02-SUMMARY.md` (this file) | committed below |

## What was built

**`AuctionValidationService` 覆盖扩展 (BT-08 诚实覆盖, 读侧对账 34-01 写侧):**

1. **`_coverage_symbols(start, end, verification_panel, enriched_dates)`** — 私有只读助手 (放 `_enriched_coverage` 旁): 扫 `kline_auction/date=*/part.parquet` 窗口内分区 (复用 `auction_columns._dir_date` 严格解析, 坏目录/空分区/缺 symbol 列 fail-closed 跳过, 每分区 symbol 级去重防 fan-out — 镜像 `attach_auction_columns_range` 分区扫语义); `auction_symbol_count` = 窗口分区行 symbol 去重数, `auction_rows_present` = 窗口分区总行数, `enriched_symbol_count` = `verification_panel["symbol"].n_unique()`, `auction_rows_expected` = `enriched_symbol_count × len(enriched_dates)`, `symbol_coverage_ratio` = auction/enriched (0 除 → 0.0)。零写 token (glob/read 只读), 守卫兼容。
2. **build_report coverage 增补 `"symbols"` 子块** (日期级键零改动, 纯增量 — 既有字段级断言不破); 窗口用 effective 回夹后的 start/end。
3. **`_empty_report` coverage 同键扩展** `{auction_symbol_count:0, enriched_symbol_count:0, symbol_coverage_ratio:0.0, auction_rows_present:0, auction_rows_expected:0}` — 空态与实态同形状 (D-02)。
4. **`_evaluate_strategy` 增补 `n_symbols_covered`/`n_symbols_hit`**: real 分支 = 竞价列 (`auction_volume`) 非 null 的 symbol 去重数 (稀疏湖 = 2, 注入列缺席 → 0); derived/eod 分支 = 该分支评估宇宙 (全面板 symbol 集); 空面板 → 0; `n_symbols_hit` = hits symbol 去重数 (空 → 0)。branch/params/前瞻逻辑零改动。
5. **docstring 增补**: 模块 docstring BT-08 诚实覆盖段 + build_report 步骤 8 (coverage.symbols 语义 — 稀疏湖小宇宙如实, 绝不声称全市场规模)。

**零改动面 (契约遵守):** `data_gate` 闸门 `:184-191` 零改动 (激活是行为性的 — 248 分区 → available, 本计划只证明+锁死); `_build_candidate_mask`/`_forward_stats`/`_null_metric`/`_aggregate_metric`/`_FORWARD_METRICS` 签名行为未动 (34-01 共源契约, `test_auction_backtest.py` 回归锁); 既有测试行零改动 (只追加); `frontend/` 零触碰。

## 248 分区激活证明 (BT-08 核心)

fixture = 248 连续日 auction 分区 (2 symbol × 每分区 1 行) ∩ 248 日 enriched (5 symbol) → `build_report` 自动翻转:

- `data_gate == "available"`, `empty_reason is None`, `coverage_ratio == 1.0` (248∩248), `skipped_ids == []`
- 4 个真列策略 `branch=="real"` 且 `n_dates==248` (绝不 derived-downgrade, D-02); `auction_alpha` 翻转 real
- `coverage.symbols == {auction_symbol_count:2, enriched_symbol_count:5, ratio:0.4, auction_rows_present:496, auction_rows_expected:1240}` (测试 fixture 宇宙; 真实湖 = 2/5293 ≈ 0.04%)
- 竞价列依赖过滤策略 (fast_grab/allround/t1_flash) hits ⊆ 2 symbol (其余 3 symbol 竞价列 null 恒假 — 单 symbol 评估 0 命中证明)
- EOD 代理 `n_dates==248` 全窗口

## Key semantics locked

- **诚实稀疏**: coverage.symbols 实态 (2/5, rows 4/10) 与无分区空态 (auction 侧 0 / enriched 侧如实 5、rows 0/10) 同键不同值, `_empty_report` 全 0 — 三层形状逐层断言。
- **per-strategy 覆盖口径与 34-01 manifest 对账一致** (同一湖同一数字): real = 竞价列非 null symbol 数; derived/eod = 评估宇宙。
- **BT-10 回归**: coverage 扩展后全 9 策略 `minute_confirm:"not_applied"` 逐项断言不破。
- **D-06**: 模块 docstring「本报告区间不受回测 186 天 guard 限制」声明在位; 零 `_guard_server_backtest_range`/`BACKTEST_MAX_SERVER_DAYS` 引用; 新增 coverage 代码零写 token (守卫全绿)。

## Deviations applied

- **`auction_intraday_confirm` 命中宇宙 (pre-existing, 非本计划引入)**: 其日线 filter 仅门控 `open_gap` (不依赖竞价列; 分钟确认层未接, BT-10 `minute_confirm:"not_applied"` 注解诚实受限) → 248 fixture 下 `n_symbols_hit==5` (全 symbol, 5×248 行)。与 34-01 观察一致; 本计划对竞价列依赖策略 (fast_grab/allround/t1_flash) 断言 ⊆2-symbol 子集, 对 intraday_confirm 断言如实全 symbol 并注明 BT-10 注解。零服务代码改动。
- **`t1_flash` 在 248 fixture 下 0 命中**: META 默认 `min_auction_vol_ratio=2.0`, fixture 竞价量比 1.8 未达 — 诚实 0 命中 (阈值语义正确, 非缺陷)。
- W1-W5: W3 (full-run 248 天真实运行时) 属 34-03 Task 4 沙箱真实运行, 本计划不测量; W4/W5 属 34-03; 其余 n/a。

## Verification evidence

| Gate | Result |
|------|--------|
| 结构 `grep -c "coverage.symbols\|_coverage_symbols\|n_symbols_covered\|n_symbols_hit" app/services/auction_validation.py` | 15 |
| `ast.parse` service module | ok |
| D-06 `grep -c "本报告区间不受回测 186 天 guard 限制"` | 1 |
| D-06 `grep -c "_guard_server_backtest_range\|BACKTEST_MAX_SERVER_DAYS"` | **0** |
| 报告套件 `pytest tests/test_auction_validation_report.py -x -q` | **20 passed** (16 既有零改动 + 4 新: 248 激活真列实况 / coverage.symbols 稀疏诚实 / per-strategy symbol 覆盖 / 分钟注解回归) |
| 守卫+共源 `pytest tests/test_auction_validation.py tests/test_attach_auction_columns_range.py tests/test_auction_backtest.py -x -q` | **26 passed** (6 + 14 + 6) |
| 全量回归 (plan verify 逐字) | **46 passed** |

## Commits

```
(34-02) feat(34-02): BT-08 validation activation + honest symbol coverage (coverage.symbols + n_symbols)
```

## Watchlist proof

`frontend/src/pages/Watchlist.tsx` was **never read, touched, or committed** — it remains the only unstaged tracked-file change in the repo. Final state check below (run after this summary commit):

```
$ git status --short
M frontend/src/pages/Watchlist.tsx
?? backend/scripts/auction_backtest.py   (34-03 sibling in-flight, not mine)
```

## Zero-touch inventory

- No existing test lines modified (16 existing report cases untouched, all green).
- `data_gate` 闸门 (:184-191) 零改动; 模块级纯助手 5 个签名/行为零改动 (34-01 import 契约 intact).
- Zero new runtime dependencies (polars/duckdb locked stack only).
- `data/` never touched; coverage 统计纯只读 glob/read — 守卫写路径 token 全绿.
- 34-03 引用锚点: 报告面覆盖数字 = 248∩248 → `data_gate:"available"`; `coverage.symbols` 实况 (fixture 2/5/0.4/496/1240; 真实湖 2/5293 ≈ 0.04%); per-strategy `n_symbols_covered`/`n_symbols_hit` 字段名.
