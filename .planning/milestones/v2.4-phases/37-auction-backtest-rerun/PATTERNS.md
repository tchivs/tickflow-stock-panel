# Phase 37 模式映射 (Patterns)

**Mapped:** 2026-08-07 (orchestrator, from R2 doc + repo reads)

| # | 需求对象 | 现有模式 (file:line) | 复用方式 |
|---|---|---|---|
| 1 | 指纹修复 (RC-01) | `_compute_run_id` (auction_backtest.py:614-640); `_persist_run` (:712-743) reused=True 跳写; 先例注释 :624-628 | digest 加 `auction_symbol_count` + `len(auction_enabled_dates)`; 注入步骤 ④ (attach_auction_columns_range :426) 顺带取; 测试扩展 :357 |
| 2 | 覆盖快照 (RC-02) | `_coverage_symbols` (auction_backtest.py:260); `attach_auction_columns_range` (auction_columns.py:146-217, 分区存在性闸门零 probe) | 重跑 CLI 全市场 (scripts/auction_backtest.py:134-157 `_preload_full_enriched` ~3.5s); 诚实 X/5537 报告 |
| 3 | 分支互斥 (RC-03) | `_evaluate_strategy_rows` (:284-372) branch 互斥 BT-05; mask `_build_candidate_mask` (auction_validation.py:85-108) fill_null(False) | 不变; intraday_confirm 注记 (filter 仅 open_gap, intraday_confirm.py:42-45, test :186-188) |
| 4 | 覆盖报告块 (RC-03) | coverage.symbols 5 键 (auction_validation.py:260-309); `_coverage_symbols` :260; n_symbols :406-427 | 规模下同构; rows_present<expected 部分态 |
| 5 | CLI (RC-04) | scripts/auction_backtest.py argparse (--range/--symbols/--strategies, META 默认, terminal dict JSON, DATA_DIR env) | 加 `--force` 绕过指纹; 既有 `--range 248` 全市场 |
| 6 | 只读面 (RC-04) | GET /api/research/backtest + /{run_id} (api/research_backtest.py, run_id `^[0-9a-f]{12}$`→400) | 全规模查询验证 (40-60 万行); vectorbt flat 诚实跳过 |
| 7 | AST guard (RC-04) | test_pool_hub E3 镜像守卫 (router AST guard / 无 strategy_cache 引用 / GET-only) | 保持绿; delta 限于 backtest_results 写根 |
| 8 | 测试惯例 | module-object monkeypatch; 测试名嵌 token (run_id/coverage/force); fixture 用 tmp_path 湖 | 新测试照此 |

## 契约

- `_compute_run_id` 签名不变; digest 仅新增成员 → 同湖同输入幂等语义保持 (既有 run_id 不失效)。
- run_id 前缀 12 hex 不变 (`^[0-9a-f]{12}$` API 校验)。
- `--force` 仅 CLI (零 API 面, O1 维持); 强制重写后 provenance 相同 (run_id 可重复, 目录覆盖语义 = manifest 记录 rewritten_at)。
- coverage 报告键集不变 (5 键), 值诚实 (当前 37/5537)。
