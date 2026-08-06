# 34-03 Summary — 竞价回测查询面 + 触发面 + 文档 + 沙箱真实双跑 (BT-09/BT-10/BT-07 验收)

**Phase:** 34-auction-backtest · **Plan:** 34-03 · **Executor:** ExecutorP3403 · **Date:** 2026-08-06
**Status:** ✅ COMPLETE — 4/4 tasks, verification green, commits atomic per task

## Deliverables

| Task | Artifact | Commit |
|------|----------|--------|
| 1 — operator CLI (O1 触发面) | `backend/scripts/auction_backtest.py` (new) | `e80e8b0` |
| 2 — BT-09 只读查询端点 + 注册 | `backend/app/api/research_backtest.py` (new) + `backend/app/main.py` (2 行) | `e80e8b0` |
| 3 — AST 守卫 (7) + API 行为测试 (4) | `backend/tests/test_research_backtest_guard.py` + `test_research_backtest_api.py` (new) | `e80e8b0` |
| 4 — docs + 沙箱真实双跑 + 前瞻抽查 | `docs/features.md` (竞价回测节) + 本 SUMMARY | below |

## Task 1 — CLI `backend/scripts/auction_backtest.py`

argparse 全参数 (`--strategies`/`--range N|START,END` 缺省 248/`--symbols`/`--rpm` 保留无操作注) → 真 repo/engine 构造 (镜像 main.py:551-565: `ScreenerService` 快路径 loader, 不传 minute_loader) → `run_full_backtest` → 终态摘要 (run_id/wrote|reused/窗口双字段/每策略 branch+dates+hits+sym_covered+sym_hit+missing/coverage.symbols/落盘路径/耗时/BT-10 注) → exit 0/1 (异常 → stderr traceback + 1; 诚实空态 no_enriched/no_dates_in_window → 1)。

**偏差 (W-note, 34-01 契约边界的诚实补齐)**: 仓库默认 `_refresh_enriched` 只缓存最近 300 自然日 (~205 交易日), 覆盖不了 `--range 248` 全量窗口 → CLI 新增 `_preload_full_enriched(repo)`: 镜像 refresh 装配形 (scan_enriched_parquet → compute_indicators → compute_signals → compute_limit_signals), 窗口 = kline_daily_enriched **全分区** (248 交易日) → `run_full_backtest` 覆盖边界 = 全量 enriched 交易日。零改动 34-01 服务; 实测 preload ≈ 2-3s。

## Task 2 — BT-09 只读查询端点

`GET /api/research/backtest` (列运行): 扫 `backtest_results/run_id=*` 目录, **仅含 manifest.json 的目录计入** (vectorbt 平面 `run_id={id}.parquet` 文件 is_dir 天然排除, 诚实跳过); 每 run `{run_id, created_at, origin, strategy_version, window, n_strategies, n_hits, coverage}` (n_hits = manifest per_date 汇总); `?strategy=`/`?branch=` 按 manifest.strategies 过滤; created_at 降序; 空湖 → 200 `{runs:[], count:0}`。

`GET /api/research/backtest/{run_id}` (详情): run_id 严格 `^[0-9a-f]{12}$` → 坏格式 400, 不存在 → 404 `RESEARCH_BACKTEST` (T-34-03-06); manifest 全文 + `part.parquet` 谓词下推 `?strategy=&branch=&as_of=&symbol=` (polars scan, 缺列 → 400 而非 500); stats `{n_rows, n_hits, per_date, per_strategy}` + 采样 ≤20 行; 空/坏 parquet → 200 诚实空态 (绝不 500)。

main.py: import 块 `research_backtest` (research_auction 旁, 字母序) + include_router (research_auction.router 旁, `# BT-09 竞价回测结果只读查询 (POOL-03 零执行)`); 路由前缀 `/api/research` 无冲突 (research.py 无 /backtest 路径)。

## Task 3 — 守卫 + API 行为测试

`tests/test_research_backtest_guard.py` (7 用例, 镜像 test_auction_validation.py 六项 + E2):
- `test_backtest_modules_exist` / `test_backtest_no_execution_imports` (api 全量禁 token 含 pool_snapshot; 服务面豁免 pool_snapshot — fingerprint 共源白名单例外) / `test_backtest_api_is_get_only` (E4 形) / `test_backtest_no_write_path` (api 面零写 token + 禁调用 token; 服务面豁免但受 E2) / `test_backtest_service_writes_only_backtest_results` (**E2 根隔离**: AST 提取全部写调用点目标 (mkdir/write_parquet/write_text/replace/os.replace/unlink) → 赋值+实参绑定闭包展开 → 每条含 `backtest_results` 字面量且不含 strategy_cache/screener_results/kline_auction/kline_daily_enriched) / `test_backtest_no_strategy_cache_reference` / `test_backtest_import_whitelist` (api: fastapi/polars/stdlib/app.config; 服务: polars/stdlib/auction_columns/auction_validation/pool_snapshot)。

**守卫范围偏差 (W-note, 34-01 冻结面约束)**: E3 字面量检查 (strategy_cache/screener_results) 对 **api 面** import+源码全查; 对**服务面**仅 import 面查 —— 34-01 服务 docstring 以散文形式声明 E2 纪律 (「绝不触碰 strategy_cache / screener_results / kline_auction / kline_daily_enriched 等湖」), 属文档非引用; 本计划零改动 34-01 文件 (34-01 契约冻结), 实际契约由 E2 写目标闭包断言锁死 (写目标展开后逐条不含禁湖字面量)。

`tests/test_research_backtest_api.py` (4 用例, hermetic: tmp data_dir + 手工写 34-01 布局湖, 零网络):
- `test_backtest_query_list_and_detail` (两 run + 1 vectorbt 平面文件 → runs==2 平面诚实跳过, count==2, created_at 降序, 字段集 8 键; 详情 manifest 回显 + n_rows + 采样 ≤20; 空湖 200 诚实空)
- `test_backtest_query_filters` (列运行 ?strategy=/?branch= 过滤 + 详情谓词下推 strategy/branch/as_of/symbol → n_rows 手算子集精确收缩)
- `test_backtest_query_unknown_run_404` (未知 → 404 RESEARCH_BACKTEST; 坏格式 → 400; 坏日期 → 422)
- `test_backtest_query_skips_vectorbt_flat_files` (仅平面文件 → runs 空 200; 平面 run_id 详情 → 404 诚实 not-found)

## Task 4 — docs + 沙箱真实双跑

docs/features.md 新增 `### 🧪 竞价回测 (Auction Backtest)` 节 (紧随竞价策略历史验证节): ① operator CLI 触发 (O1, 零 POST, META 默认 O2, 幂等 reused, `--rpm` 无操作注); ② 只读查询 GET-only 零执行 (7 项 AST 守卫); ③ 湖面共存诚实 (目录形 vs vectorbt 平面文件); ④ 诚实覆盖 (34-02 字段名同源: coverage.symbols 5 键 + n_symbols_covered/n_symbols_hit, 今日真列宇宙 2 symbol, 全量回填 3-5.5h 解锁全宇宙真列); ⑤ 186 天 guard 非适用 (D-06); ⑥ BT-10 分钟限制 (kline_minute CLOSED / minute_confirm not_applied / auction_intraday_confirm 恒空); ⑦ 沙箱实测数字锚定 (Run A/B 行数/耗时/覆盖)。

### 沙箱真实双跑 (BT-07 验收, 2026-08-06, data/ 未提交)

| Run | 命令 | 结果 | 耗时 (wall) |
|-----|------|------|------------|
| A | `python scripts/auction_backtest.py --strategies golden_230,auction_bullish,auction_preopen_quant,auction_early_star` | run_id=`be4ce9bc038b`, wrote=True, 4 EOD × 248 日 × 全市场, **329,087 命中行** | **4s** (含全量 preload; 34-01 [INFERENCE] ~1-3min 估算已被实测取代) |
| B | `python scripts/auction_backtest.py --strategies auction_fast_grab,auction_allround,t1_flash,auction_alpha --symbols 000001.SZ,000002.SZ` | run_id=`191642f83b2d`, wrote=True, 4 real × 248 日 × 2 symbol, **12 命中行**, `auction_symbol_count==2` | **3s** |
| B 幂等 | 同命令重跑 | 同 run_id, **wrote=False, reused=True** | 3s |
| 冒烟 | `--strategies auction_bullish --range 5 --symbols 000001.SZ,000002.SZ` | run_id=`0f2b91e93975`, 0 行 (诚实空命中) | 3s |

**终态摘要摘录 (Run A)**: `auction_bullish eod dates=248 hits=32686 sym_hit=5041 missing=219`; `auction_early_star eod hits=203221 sym_hit=5508 missing=1733`; `auction_preopen_quant eod hits=11926 sym_hit=4216 missing=76`; `golden_230 eod hits=81254 sym_hit=5454 missing=664`; `coverage: auction_symbols=2 enriched_symbols=5537 ratio=0.04% rows_present=496/1373176`; `strategy_version=7affa346e5e586c5` (与 33-01/34-01 记录一致)。

**终态摘要摘录 (Run B)**: `auction_allround real hits=3 sym_hit=2`; `auction_alpha real hits=6 sym_hit=2`; `auction_fast_grab real hits=1 sym_hit=1`; `t1_flash real hits=2 sym_hit=2`; `coverage: auction_symbols=2 enriched_symbols=2 ratio=100.00% rows_present=496/496`。

**分支互斥 (BT-05)**: 两 run part.parquet 逐策略 group_by 验证 —— Run A 4 策略全 `branch="eod"`, Run B 4 策略全 `branch="real"` (无 derived 降级, D-02 锁)。

**前瞻抽查 (对账 kline_daily, 3 信号日 × 2 symbol, 手核通过)**:

| as_of | symbol | open_T | close_T | T+1 | open_T1 | close_T1 | 手核 n_d_o_ret / n_d_c_ret / gap | 落盘行 (Run B) 一致 |
|-------|--------|-------:|--------:|-----|--------:|--------:|----------------------------------|--------------------|
| 2026-01-28 | 000002.SZ | 4.88 | 4.86 | 2026-01-29 | 4.82 | 5.13 | -0.012295 / +0.051230 / -0.008230 | ✅ (auction_allround/alpha/t1_flash) |
| 2026-04-27 | 000001.SZ | 11.33 | 11.38 | 2026-04-28 | 11.36 | 11.46 | +0.002648 / +0.011474 / -0.001757 | ✅ (auction_allround/alpha/fast_grab/t1_flash) |
| 2026-07-03 | 000002.SZ | 3.13 | 3.09 | 2026-07-06 | 3.08 | 3.07 | -0.015974 / -0.019169 / -0.003236 | ✅ (auction_allround/alpha) |

`outcome_missing=False` 全部抽查行 (结果日存在); 公式三列与 kline_daily 手算逐位一致 (BT-04 全局日历 join 验证)。

**真列命中少的诚实解读 (发现与风险)**: Run B 真列 4 策略 248 日仅 12 命中 (auction_fast_grab 1 / t1_flash 2 / allround 3 / alpha 6) —— 稀疏 2-symbol 宇宙 + 真实阈值过滤的诚实结果 (与 33-01 报告面「真列族最多命中稀疏湖 2 标的, 多数日未过阈值」一致); `coverage.symbols.ratio=100%` (2/2, 小宇宙内全覆盖) + `n_symbols_covered=2` 如实标注, 绝不伪造全市场规模; 全量竞价回填 (运营 3-5.5h) 后真列分支解锁全宇宙。

## Verification evidence

| Gate | Result |
|------|--------|
| `pytest tests/test_research_backtest_guard.py tests/test_research_backtest_api.py tests/test_auction_validation.py -x -q` | **17 passed** (7 guard + 4 api + 6 既有守卫回归) |
| CLI 结构 `--help \| grep -c "strategies\|range\|symbols\|rpm"` / `grep -c "def main"` / `grep -c "run_full_backtest"` | 6 / 1 / 6 |
| API 结构 `ast.parse` / `grep -c "def list_backtest_runs\|def get_backtest_run"` / `grep -c "research_backtest" app/main.py` | ok / 2 / 2 |
| 真实湖 API 冒烟 (TestClient 只读) | list 3 runs 降序; branch=real → Run B; detail 谓词 12→6→4; 404/400 诚实 |
| docs `grep -c "竞价回测\|Auction Backtest"` | ≥1 (新节) |
| `ls data/backtest_results/` | 3 × `run_id=` 目录 (gitignored, 未提交) |

## Commits

```
e80e8b0 feat(34-03): operator CLI + BT-09 read-only query endpoints + AST guard/api tests
(34-03-SUMMARY commit below — 文档/摘要)
```

## Watchlist proof

`frontend/src/pages/Watchlist.tsx` was **never read, touched, or committed** — it remains the only unstaged change in the repo:

```
$ git status --short
M frontend/src/pages/Watchlist.tsx
```

## Zero-touch inventory

- No existing source files modified except `backend/app/main.py` (+2 行: import + include_router, 34-03 独占面).
- `services/auction_backtest.py` (34-01) / `auction_validation.py` (34-02) / `research.py` / `research_auction.py` / `backtest.py` 源码零改动; 既有测试行零改动 (回归绿).
- Zero new runtime dependencies.
- `data/backtest_results/` 产物 gitignored, 未提交; 沙箱运行只写 backtest_results/ (E2).
- 34-02 并行面 (auction_validation.py + test_auction_validation_report.py) 未触碰.
