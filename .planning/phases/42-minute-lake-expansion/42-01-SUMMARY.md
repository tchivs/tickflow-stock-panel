# 42-01-SUMMARY.md — MIN-01 回填驱动 + 幂等 (Wave 1)

**Phase:** 42-minute-lake-expansion · **Wave:** 01 (MIN-01 机制: 回填驱动 + 幂等) · **Date:** 2026-08-07
**Executor:** ExecP4201 · **Status:** DONE — 3 commits (T1 RED → T1 GREEN → T3), 42-01 电池 30 passed / 0 failed, kline_sync 消费面 21 passed

## 交付物

| Artifact | Path | 说明 |
|---|---|---|
| 写面抽取 | `backend/app/services/kline_sync.py` | `_persist_minute_partitions(df, repo)` (唯一分区写面, merge-upsert unique keep=last, 空帧 0 行, written = 增量 `merged.height - before` 镜像 adj_factor 语义) + `_refresh_minute_view(repo)` (视图重建收敛, DuckDB 视图 connection-scoped 跨进程续跑必需); `sync_and_persist_minute` 改为调用共享 helper, 行为零变化 (回归绿) |
| 回填驱动 | `backend/app/services/kline_sync.py` | `backfill_minute_history(symbols, start, end, repo, *, rpm, batch_size, fetch, on_symbol_done)` — 逐 symbol 幂等跳过 (latest.date() >= end → skipped) + 增量窗口 `[max(start, latest+1day), end]` + 空响应诚实 0 行不伪 skip + fetch 异常原样上抛 fail-closed; fetch 缺省 = stockdb_provider.get_minute 包装 (端日语义 end+1day 内置) |
| per-symbol 覆盖面 | `backend/app/services/kline_sync.py` | `_latest_minute_dates(repo)` (GROUP BY 查询面, 异常 → 空 dict fail-closed 宁可全量重拉不静默错判) |
| 全宇宙解析 | `backend/app/services/kline_sync.py` | `_resolve_minute_universe(repo)` — kline_daily DISTINCT symbol 运行期动态解析 (绝不硬编码 5537/5538); 视图缺失 → polars 列限扫描兜底 (镜像 auction_backfill._lake_distinct_symbols) |
| operator CLI | `backend/scripts/backfill_minute_driver.py` | argparse + DATA_DIR env + 进度 stdout + 终态 dict JSON 原子落盘 + 退出码 0/2; 调度纪律 (避开 EOD) + 诚实覆盖声明 (覆盖 = 源插件深度, 绝不虚报 46min) 写入 docstring |
| 夹具 | `backend/tests/fixtures/stockdb/minute_backfill_20260803_20260804.json` | 冻结体: 2 标的 × 2 交易日 × 每日 09:30 起 5 根 1m bar; 每日期首根 bar_time == 09:30 (湖 anchor), 09:30 根 OHLC 全等 + volume_hand × close × 100 == amount_yuan 闭合 (600519 09:30 复用研究锚点 1328.36/521/69,207,556) |
| 契约测试 | `backend/tests/test_minute_backfill_idempotency.py` | 8 用例 (端到端落盘 / 重跑跳过 / upsert 幂等 / 增量窗口 / 空态诚实 / 进度回调 / 异常 fail-closed / universe 动态) |
| CLI 测试 | `backend/tests/test_backfill_minute_driver.py` | 4 用例 (全 skipped 幂等续跑 / 缺省窗口 / 异常 exit 2 / --symbols 子集), 模块测试钩子 `_fetch` 注入 canned, 零网络 |

## Commit 链 (RED → GREEN 可回溯)

| Commit | Sha | 内容 |
|---|---|---|
| T1 (RED) | `07f76f7` | 夹具冻结 + 契约测试 ×8 — 收集期红: `AttributeError: no attribute 'backfill_minute_history'` |
| T1 (GREEN) | `44cdcd4` | 写面抽取 + backfill_minute_history + per-symbol 增量 + universe 动态解析 (Task 1+2) |
| T3 | `e4fc8b4` | operator CLI — scripts/backfill_minute_driver.py + 4 CLI 测试 |

## Verify 命令输出摘录

**T1 (RED, 验收第一步行):**
```
tests/test_minute_backfill_idempotency.py:147: AttributeError: module 'app.services.kline_sync' has no attribute 'backfill_minute_history'
1 failed in 0.20s
```

**T1 (GREEN, 契约 + 增量 + 写面回归):**
```
tests/test_minute_backfill_idempotency.py tests/test_minute_sync_verify.py tests/test_minute_timestamp_convention.py
15 passed in 0.76s
```

**T3 (CLI):**
```
tests/test_backfill_minute_driver.py  [100%]
4 passed in 0.36s
```

**42-01 电池 (最终, 零网络):**
```
tests/test_minute_backfill_idempotency.py tests/test_backfill_minute_driver.py
tests/test_minute_sync_verify.py tests/test_minute_timestamp_convention.py tests/test_minute_loader_wiring.py
30 passed in 0.93s
```

**写面抽取消费面回归:**
```
tests/test_stocksdk_provider.py (sync_and_persist_minute 消费面 + custom provider 路由)
21 passed in 0.81s
```

## 契约锁死点 (可执行规范)

- **幂等双保险:** 重跑同参 → 已覆盖 symbol 全部 skip (`skipped` 列表), `written==0`, 分区文件 sha256 与首跑逐字节一致; 写面 unique(subset=[symbol, datetime], keep=last) + `_atomic_write_parquet` (tmp+rename) 原子。
- **增量窗口:** per-symbol latest (GROUP BY 查询面) → 窗口 `[max(start, latest+1day), end]`; 记录型 fetch 断言: A 已覆盖至 08-04 → 只收 `[08-05, 08-05]`, B 无覆盖 → 收全窗 `[start, end]`。
- **空态诚实:** 空响应 → 0 行不落盘、symbol 不在 skipped 也不计 written (下次重跑重试); 重跑有数据 → 正常落盘 (空态不毒化)。
- **fail-closed:** fetch 异常原样上抛 (Tushare 40203 绝不伪装「该窗口无数据」); CLI 捕获 → exit 2 + stderr traceback; `_latest_minute_dates`/`_resolve_minute_universe` 查询异常 → 空 dict/空列表 fail-closed。
- **全宇宙:** `_resolve_minute_universe` = kline_daily DISTINCT symbol 运行期排序 (测试 3 symbol 动态种子断言), 双通道 (视图 → polars 扫描兜底)。
- **写面抽取零回归:** `sync_and_persist_minute` 行为不变 (test_minute_sync_verify 绿); written 语义 = 增量 (`merged.height - before`, 镜像 adj_factor merge), 多 symbol 首跑 written == 20 诚实计数。
- **视图纪律:** `backfill_minute_history` 开头/结尾各刷新 kline_minute 视图 (DuckDB 视图 connection-scoped, 跨进程续跑必须重建才能读到既有覆盖)。

## 约束复核

- **零新增依赖:** 3 commits 不触碰 `backend/pyproject.toml` / `backend/uv.lock`。
- **Watchlist 零触碰:** commits 不触及 `frontend/src/pages/Watchlist.tsx` (保持唯一 unstaged, 非本 executor 所为)。
- **零新机制:** 全部镜像既有模式 — 分区写 (sync_and_persist_minute 原样迁移), universe 兜底 (auction_backfill._lake_distinct_symbols), CLI 形态 (auction_backfill), repo_env/夹具/进度 (minute_sync_verify / stockdb_provider 测试惯例), fail-closed 上抛纪律 (41-01 SourceBlockedError 先例)。
- **本 plan 不承诺真实源覆盖:** 覆盖 = 源插件深度, 42-03 checkpoint 门声明; 全部验收 canned 夹具零网络。

## 协作注记

- 与 ExecP4203 (42-03) 已通过 hub 锁定契约: `backfill_minute_history` kwargs-only 参数尾追加 `source_label: str | None = None`; CLI `main(argv=None, _fetch=None)` 测试钩子 + argparse 加 `--source-label`; `on_symbol_done(i+1, total)` 每 symbol 恰一次 (含 skipped)。42-03 将在此 3 commits 之上叠加, 无预期冲突。
- ExecP4202 (42-02) 的 `backend/app/services/auction_validation.py` + `backend/tests/test_auction_validation_report.py` 改动保持 unstaged, 本 executor 未触碰 (针对性 `git add` 隔离)。

## Next Phase Readiness

- 42-02 (统计口径双报告): 可基于 `_persist_minute_partitions` 唯一写面做分钟侧统计口径核对。
- 42-03 (诚实标注 + 源插件 seam + checkpoint): `backfill_minute_history` 的 fetch 注入面即源插件 seam 挂载点; `--source-label` kwarg 契约已锁定。
