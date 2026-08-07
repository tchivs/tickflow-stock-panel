# Phase 37 研究 — 全量真列回测重跑 (Full Real-Column Backtest Rerun)

**Researched:** 2026-08-07
**Source:** `.planning/research/v2.4-full-universe/REAL-COLUMN-BACKTEST.md` (ResearcherV24B, confidence HIGH, 实测驱动)
**Implementation-ready:** YES — 指纹缺口实测 + 全部运行时/磁盘数字实测

## Verdict

**FEASIBLE** — 全市场真列重跑是秒级本地向量化作业 (全市场 9 策略 248 日 compute=2.3s, 381,690 行实测)。**唯一结构性阻断**: `_compute_run_id` 指纹不含湖覆盖态 → 回填后同命令重跑 reused=True 静默保留旧数据 (实测)。~5 行修复 + 测试。

## 实测锚点 (2026-08-07)

| 项 | 值 | 证据 |
|---|---|---|
| 既有运行 | be4ce9bc038b (Run A eod 329,087 行) / 191642f83b2d (Run B real 12 行 @2 symbols) / 1cbb901a5637 (全市场 9 策略 381,690 行, compute 2.3s, CLI 5.3s) / 45fb75b65731 (50-symbol 2,221 行) | 3.1/3.2 |
| **指纹缺口 (实测)** | 同命令重跑 → `reused=True wrote=False` — 新结果在内存计算但旧 part.parquet/manifest 保留 | 0. 关键缺口 |
| 指纹构成 | `_compute_run_id` (auction_backtest.py:614-640) = strategy_ids\|start\|end\|params\|strategy_version\|symbols — **无湖覆盖态**; 先例注释 :624-628 "symbols 纳入哈希…防幂等跳过遮蔽小宇宙运行" | 0/2.1 |
| 湖读规模 | 248 分区全量读 0.31s; 注入 (symbol,date) 左联, 分区行数不构成瓶颈 | 3.1 |
| 磁盘 | 全市场 kline_auction 248 分区 ≈ 36 MB (26 B/行); backtest_results ~11-20 MB/run; 1TB 空闲 | 3.4 |
| 分支语义 | 4 列门控策略 (fast_grab/allround/t1_flash/alpha) 恒 real; auction_intraday_confirm **filter 仅用 open_gap** (intraday_confirm.py:42-45, 测试显式 :186-188) → 52,591 行在稀疏湖已全市场, 回填后不变 | 3.2 |
| 覆盖报告 | coverage.symbols 双块 (auction_validation.py:260-292 同构); `_coverage_symbols` auction_backtest.py:260; n_symbols :406-427 | 3.5 |

## 2026-08-07 湖态更新 (Phase 36 后)

- kline_auction = **37 symbols × 248 日 = 8,951 真实行** (Phase 36 实跑 35 新 symbol 后上游 403 封锁)。
- 覆盖 = 37/5537 = **0.67%** (非 0.036%) — 真列分支 hits 将真实增长约 18× (12 → ~200+ 量级 [投影])。
- FA-04 全量 (≥5204) source-gated defer → 本 phase 的全市场重跑 = **当前湖态诚实重跑** + 指纹修复 + post-recovery 全量重跑为 operator 命令 (运行一次, 5-10s, 无新代码)。

## 最小代码增量 (RC-01, ~5 行 + 测试)

1. `_compute_run_id` 摘要加**湖覆盖 digest**: `auction_symbol_count` (kline_auction 去重 symbol 数) + `len(auction_enabled_dates)` (分区存在日期数) — 轻量查询 (248 分区读 0.31s 量级或 DuckDB count)。
2. run_id 计算时点: 覆盖步骤 (step ⑦) 之后或步骤 ④ 注入时顺带取 digest。
3. 测试扩展 `test_full_backtest_deterministic_run_id_idempotent` (test_auction_backtest.py:357): 同输入 + 湖覆盖不同 → 不同 run_id; 同湖 → 仍幂等 reused。
4. (RC-04 P2) `--force` CLI flag: 绕过指纹检查强制重写 (operator escape hatch)。

## 验收口径 (诚实, 源受限后)

- RC-01: 指纹修复测试绿 (覆盖翻转 → 新 run_id; 同湖 → reused)。
- RC-02: 当前湖态全市场重跑: coverage 0.67% 诚实报告 (37/5537); 4 列门控策略 hits 12 → ~200+ 量级 [投影, 实测记录]; EOD 4 策略 329,087 **不变**; intraday_confirm 52,591 不变; runtime ≤10s 实测。全量 (≥0.94) 重跑 = post-recovery operator 命令 (已文档化)。
- RC-03: rows_present < expected 诚实部分态; intraday_confirm branch=real 无列消费注记; verifier 前瞻抽查 9dp。
- RC-04: backtest_results run_id 目录 + GET /api/research/backtest/{run_id} 全规模查询; --force; AST guard E3 绿。

## 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| 指纹修复后旧 run_id 语义变化 | LOW | 新 digest 只影响未运行输入; 既有 run_id 不失效 (幂等键新增成员, 同湖同输入仍 reused) |
| 覆盖快照与 run 之间湖变化 (并发回填) | LOW | digest 取于注入时点; 沙箱无并发回填 (403 封锁期) |
| 全量重跑被上游门控 | MEDIUM (预期) | 诚实部分态 + post-recovery operator 命令 (一次 5-10s) |
| intraday_confirm 52,591 "real" 误导 | MEDIUM | 摘要注记 (branch=real 无竞价列消费, BT-10) |
| AST guard 漂移 | LOW | delta 限于 backtest_results 写根 (auction_backtest.py), 镜像守卫测试绿 |
