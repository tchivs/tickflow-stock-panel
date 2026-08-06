# 35-01 Summary — LG-01 R13 pipeline→refresh 配方回归 + LG-05 OQ-3 隔离冒烟

**Phase:** 35-legacy-completion · **Plan:** 35-01 · **Executor:** ExecutorP3501 · **Date:** 2026-08-06
**Status:** ✅ COMPLETE — 3/3 tasks, verification green, atomic commits

## Deliverables

| Task | Artifact | Commit |
|------|----------|--------|
| 1+2 — LG-01 R13 回归测试 (3 tests) | `backend/tests/test_daily_pipeline_refresh.py` (new) | `f1bcaf2` |
| 3 — LG-05 OQ-3 隔离冒烟 (零 repo 文件改动) | 运行记录见下 (输出在 /tmp/oq3-smoke) | — |
| Summary | `.planning/phases/35-legacy-completion/35-01-SUMMARY.md` (this file) | committed below |

## What was locked (LG-01)

新文件 `backend/tests/test_daily_pipeline_refresh.py`, 3 个确定性测试锁死 R13 的 pipeline→refresh 配方 (ce5c705/9aa96ed):

1. **`test_pipeline_then_refresh_refreshes_cache_on_success`** — stub `run_now` (零网络) 先落盘 EOD 帧再返回 `{"ok": True}`; spy 包 `repo.refresh_cache` → 断言返回值原样上抛、spy 被调 ≥1 (finally 必刷 — 成功路径)、`qs.paused()` 进入/退出各 1 次 (15:30 配方包裹), 且刷新后 latest-day enriched 资产持有今日 EOD close (`get_enriched_latest_asset("stock")` → `cache_date==T`, `close==[11.5]`, `enriched_latest_date()==T`)。
2. **`test_pipeline_then_refresh_refreshes_cache_in_finally_on_stage_error`** — stub `run_now` 先播种 enriched 分区再抛 `PipelineStageError` (daily_pipeline.py:36); `pytest.raises` 包裹 (异常继续上抛语义不变) + 异常后缓存已含新帧 (`close==[11.2]`) — 锁死 9aa96ed「部分成功也生效」, ce5c705 核心。
3. **`test_refresh_cache_loads_latest_enriched_eod_frame`** — 不经 `_pipeline_then_refresh` 直接调 `repo.refresh_cache(background=False)`, 断言缓存从真实 parquet 加载最新 EOD 帧 (`cache_date==T`, `close==[10.8]` 与前日 10.5 互异, `enriched_latest_date()==T`) — refresh_cache 真实性, 非 mock 假读。

recap 消费侧语义 (15:40 EOD change_pct / 15:10 pre-EOD 省略 / 标签判别) 已由既有 `test_auction_recap.py` 锁死, **零改动零新增** — 新测试 docstring 跨链引用 (:541-559 / :636-643 / :275-295) 并跑回归绿作证明。

## Key fixture decisions (W applied)

- **W-1 (inline paused fake):** RESEARCH 引用的 test_preopen_scheduling.py:60-84 fake 实际不存在 (该文件 :60-84 是 `_make_app_state_with_quoteservice`, 无 `paused()`); 按生产契约 `QuoteService.paused()` (quote_service.py:308-316: pause → yield → finally resume) 内联自写 `_FakeQuoteService`, 记录 pause/resume 次数供断言。
- **W-2 (closure access):** `_pipeline_then_refresh` 是 `start_scheduler` 内闭包 (daily_pipeline.py:1115-1136), 用 fake `AsyncIOScheduler` (monkeypatch `daily_pipeline.AsyncIOScheduler`) 捕获 `add_job` 的 daily_pipeline job lambda, 从 `__closure__` 提取目标函数体 — 闭包持有 start_scheduler 参数 repo/capset 单元格, `_get_app_state`/`run_now` 运行时 monkeypatch。从不启动真实调度器。
- **真实 repo (非 _FakeRepo):** `DataStore`+`KlineRepository` 于 tmp_path (test_minute_sync_verify `_seed_daily_lake` 配方), `refresh_cache` 真读 parquet。**发现并处理:** DataStore 空目录启动时 DuckDB 视图注册被跳过 (`read_parquet` glob 空 → IOException 降级), 数据落盘后需 `repo.store._register_views()` 重新注册 (镜像生产「同步写入后刷新视图」机制, repository.py:160-161 注释) — 已在 `_seed_lake` 内固化。
- 运行边界: `run_now` 恒 stub; `background=False` (全同步); 1 标的 × 2 日 fixture (ms 级); DataStore db 在测试 finally close; 零网络; 零真实湖接触。

## LG-05 OQ-3 隔离冒烟 (Task 3, 零 repo 文件改动)

**隔离** (W-3 — data/ext_data 在 REPO ROOT): `cp -r data/ext_data /tmp/oq3-smoke/`, 绝不在真实 data/ 下运行。

| 步骤 | 命令 | 结果 |
|------|------|------|
| 基线 | `sha256sum data/ext_data/ext_gn_ths/part.parquet data/ext_data/ext_hy_ths/part.parquet` + `test ! -e data/ext_history` | gn_ths `5d617a5c…df15e`, hy_ths `8e70e588…4c95`; 真实 ext_history 不存在 |
| 首次运行 | `cd backend && DATA_DIR=/tmp/oq3-smoke .venv/bin/python scripts/probe_concept_drift.py 2026-08-06` | `exit=0`; stdout: `probe 2026-08-06: gn_ths sha=5d617a5c… rows=5542 eff=2026-08-06; hy_ths sha=8e70e588… rows=5542 eff=2026-08-06; drift.jsonl lines=2` |
| 输出物断言 | `/tmp/oq3-smoke/ext_history/{gn_ths,hy_ths}/date=2026-08-06/{part.parquet,manifest.json}` 存在 | 4 文件全存在; drift.jsonl 2 行, 字段 date/kind/sha256/rows/effective_date 齐全 |
| 重跑幂等 | 二次运行同命令 | `exit=0`; 分区 sha 稳定 (逐字节不变); drift.jsonl 追加至 **lines=4** (append-only 语义, 文档化非 bug) |
| 零副作用 | `sha256sum -c /tmp/oq3-baseline.sha` + `test ! -e data/ext_history` (repo root) + 真实 ext_data 无归档目录泄漏 | 真实湖 sha 逐字节一致; 真实 ext_history 仍不存在; ext_data 未泄漏 |

**最终 verify (W-4 — 不再重跑探针):** drift.jsonl 恰 4 行 (2 次运行 × 2 行) + 分区/清单存在 + 真实湖 sha 一致 + 真实 ext_history 不存在 — 全部通过。

**诚实注记:** 冒烟只验证**机制** (单次前向归档 + drift 行)。周终报告 (≥5 交易日 sha 去重、概念增删样本、effective_date 校准) 属部署清单 D7, deploy-gated, 本计划文档化不执行; `--upstream` 模式不进冒烟 (实时网络, D7-4 可选)。

## Verification evidence

| Gate | Result |
|------|--------|
| New suite + recap 回归 `cd backend && .venv/bin/python -m pytest tests/test_daily_pipeline_refresh.py tests/test_auction_recap.py -x -q` | **21 passed** (3 new + 18 recap) |
| Structure `grep -c 'def test_pipeline_then_refresh_refreshes_cache_on_success\|def test_pipeline_then_refresh_refreshes_cache_in_finally_on_stage_error\|def test_refresh_cache_loads_latest_enriched_eod_frame' backend/tests/test_daily_pipeline_refresh.py` | **3** |
| recap 侧零改动 | `test_auction_recap.py` 未修改 (git diff 无此文件) |
| LG-05 冒烟 (Task 3 verify, W-4 变体) | drift lines==4, partitions present, real-lake sha OK, ext_history absent |
| 零新增依赖 | 仅 pytest/polars/SimpleNamespace/contextmanager (均既有) |

## Commits

```
f1bcaf2 test(phase-35): LG-01 R13 pipeline→refresh finally 配方回归 (3 tests)
```

## Watchlist proof

`frontend/src/pages/Watchlist.tsx` was **never read, touched, or committed** — it remains the only unstaged change at my end. Final state check below (run after the summary commit):

```
$ git status --short
M frontend/src/pages/Watchlist.tsx
```

## Zero-touch inventory

- No production source modified (`daily_pipeline.py` / `repository.py` / `auction_recap.py` / `screener.py` 零改动)。
- No existing test file modified — 唯一新增 `test_daily_pipeline_refresh.py`; `test_auction_recap.py` 零行改动保持绿 (LG-01 的「recap 消费已锁」证明)。
- Zero new runtime dependencies; `data/` 真实湖零副作用 (sha 逐字节一致 + ext_history 不出现)。
- 35-02/35-03 并发契约: 未触碰 frontend/ (含 `pool-hub.spec.ts` — 35-02 在改) 与 docs/ (35-03 在改)。
