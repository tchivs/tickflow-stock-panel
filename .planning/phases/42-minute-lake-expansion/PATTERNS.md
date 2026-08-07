# Phase 42: 分钟湖扩湖 — Pattern Map

**Mapped:** 2026-08-07 · **Files:** 2 新增 / 8 修改 / 1 夹具扩展 · **Analogs:** 全 exact (无 No-Analog; 镜像面 = 36 回填 CLI / 38 loader / 40 stockdb 通道 / 29 覆盖 digest)

## File Classification

| File | Role | Closest Analog | Match |
|---|---|---|---|
| `backend/app/services/kline_sync.py` (改: 写面抽取 + 回填驱动) | service | 自身 :892-912 `sync_and_persist_minute` 分区写循环 (抽取为共享写面) + :735 `_latest_minute_datetime` DuckDB 查询面 (降为 per-symbol GROUP BY) | exact |
| `backend/scripts/backfill_minute_driver.py` (新增) | operator CLI | `scripts/auction_backfill.py` (argparse + DATA_DIR env + on_progress + 终态 dict JSON + 退出码 0/1/2) | exact |
| `backend/tests/test_minute_backfill_idempotency.py` (新增) | test | `test_minute_sync_verify.py` `_synthetic_minute_frame` (:31-62 合成 canonical 帧 + 09:30 anchor) + `test_auction_backfill_honesty.py` 幂等/跳过断言形态 | exact |
| `backend/tests/fixtures/stockdb/*.json` (扩展: 分钟回填夹具) | fixture | Phase 40 `tests/fixtures/stockdb/minute_sh600519_20260805.json` (冻结 live 实测体, 零网络 hermetic) | exact |
| `backend/app/services/auction_validation.py` (改: minute_stats 子块) | service | 自身 :260-309 `_coverage_symbols` (glob date=* + `_dir_date` 窗口过滤 + fail-closed + 诚实空态同键形状) | exact |
| `backend/scripts/verify_auction_backfill.py` (改: [6] 并列行) | script | 自身 :76-86 `_lake` (分区 glob + DuckDB 视图计数) + :281-283 [6] 覆盖行 | exact |
| `backend/tests/test_auction_validation_report.py` (改) | test | 自身 `repo_env` fixture + `_write_auction_partition` (:64-70 手工写分区种子) + `_seed_enriched_cache` | exact |
| `backend/tests/test_verify_auction_backfill.py` (改) | test | 自身 `_seed_daily` / `_seed_auction` (:21-53 分区种子) + `_run` (monkeypatch DATA_DIR) | exact |
| `backend/app/services/auction_backtest.py` (改: `_MINUTE_NOTE` 文本) | service | 自身 :66-70 `_MINUTE_NOTE` 硬编码文本 (MIN-03 诚实更新点) | exact |
| `backend/tests/test_auction_backtest.py` (改: minute_note 断言) | test | 自身 :488-489 manifest minute_note 锚点断言 (随新文本更新) | exact |

## Pattern Assignments

### 回填驱动镜像面 (MIN-01 机制) — 三个既有模式拼装, 无新架构

**决策: 镜像 `scripts/auction_backfill.py` 的 operator CLI 形态 + `sync_and_persist_minute` 的分区写面 + `_latest_minute_datetime` 的 DuckDB 查询面; 不复刻 stockdb 侧 `collect.py` 的 checkpoint 机制。**

- **为什么不是 stockdb `collect.py` 模式**: stockdb 服务端 (CLI backfill-minute / collectors / SQLite checkpoint) 已存在且**本阶段零改动** (RESEARCH 架构表: 服务端回填 = stockdb 进程内执行, AQ 不直接握 Tushare)。AQ 侧回填驱动 = **读侧编排** (GET /v1/minute → 湖), 镜像 Phase 36 `auction_backfill` 的「全宇宙 + 逐 symbol 幂等 + 台账终态」语义但落在 AQ 进程内。AQ 侧无 SQLite checkpoint — 幂等双保险 = ① 驱动逐 symbol 跳过判定 (湖内 latest 覆盖目标窗口 → skip) + ② `_persist_minute_partitions` merge-upsert 原子写 (重跑天然幂等, RESEARCH Pattern 4)。
- **写面抽取**: `sync_and_persist_minute` :892-912 的分区写循环 (partition_by date → concat existing → `unique(subset=["symbol","datetime"], keep="last")` → sort → `_atomic_write_parquet`) 原样抽取为模块级 `_persist_minute_partitions(df, repo) -> int`; `sync_and_persist_minute` 改为调用同一 helper — **行为零变化**, 回归 = `test_minute_sync_verify.py` 全绿。
- **per-symbol latest**: 镜像 `_latest_minute_datetime` (:735) 的 DuckDB 视图查询面, 降为 `_latest_minute_dates(repo) -> dict[str, datetime]` (`SELECT symbol, max(datetime) FROM kline_minute GROUP BY symbol`, 经 `repo.execute_all` :337); 异常 fail-closed 空 dict (绝不因查询失败误伤全量重拉 — RESEARCH Pitfall 4)。全局 `_latest_minute_datetime` 保留供 `sync_minute` 既有调用, 驱动**不得**复用 (会因单 symbol 新数据误伤全量窗口 — RESEARCH Pitfall 4)。
- **universe 解析**: `_resolve_minute_universe(repo) -> list[str]` = `SELECT DISTINCT symbol FROM kline_daily` (运行期动态分母, A4: 5538 实测 vs 5537 需求 — 计划/代码绝不硬编码 5537)。
- **fetch 注入契约**: 驱动签名 `backfill_minute_history(symbols, start_date, end_date, repo, *, rpm=120, batch_size=200, fetch=None, on_symbol_done=None)` — `fetch(symbols, start_time, end_time) -> pl.DataFrame` (canonical 列集); 缺省 = `stockdb_provider.get_minute` 包装 (end+1day 端日语义已在 provider 内, RESEARCH Pitfall 3 — 驱动不得绕过 provider 手拼 URL); 测试注入 canned 夹具帧 (零源依赖)。逐 symbol 粒度拉取 (5537 × 1 GET @120/min = 46min 读侧节奏, Open Question 4)。
- **空响应语义**: fetch 空帧 → 该 symbol 落 0 行、不落盘、**不伪 skip** (下次重跑重试); fetch 异常 (含 Tushare 40203 typed) → **上抛 fail-closed** (镜像 41-01 `SourceBlockedError` 上抛纪律, 绝不伪装「该窗口无数据」— RESEARCH Pitfall 1)。

### 覆盖 digest 并入面 (MIN-02) — 镜像 `_coverage_symbols` 骨架

- **位置**: `auction_validation.build_report` :221-233 的 `coverage` dict 新增 `minute_stats` 子块, 与既有 `symbols` (canonical) 子块**并列, 绝不相加** (RESEARCH Pattern 3); `_empty_report` 同键形状补齐 minute_stats 全 0 块 (D-02 空态与实态同形状)。
- **扫面**: 镜像 `_coverage_symbols` (:260-309) 的 glob 模式 — `(data_dir / "kline_minute").glob("date=*/part.parquet")` + `_dir_date` 严格解析 + 窗口过滤 + `except Exception: fail-closed skip` (T-29-01-05) + 空分区/缺列 skip; **不用** RESEARCH 骨架里不存在的 `self._date_range` (已修正为既有 glob 模式, 见 PLAN-CHECK W1)。
- **09:30-only 过滤**: `f.filter(pl.col("datetime").dt.time() == time(9, 30))` — 需补 `from datetime import time` import (现 :40 只有 date/datetime/timedelta/timezone)。
- **amount 派生诚实约束**: 仅 `open==high==low==close` (纯净竞价单价位) 的 09:30 bar 以 `volume × close × 100` 派生并计入 `auction_amount_yuan` (实测闭合 521×1328.36×100=69,207,556, RESEARCH Pattern 3); OHLC 不全等 → 该 bar 计入 `amount_unknown_count`, **绝不猜** (RESEARCH Pitfall 5)。
- **caliber 常量**: `"statistical_minute_0930"` (逐字可断言, 镜像 41 的 `SOURCE_BLOCKED_DETAIL` 常量纪律)。
- **解锁门**: digest 内 `unlock_threshold: 0.94` + `unlock_met: bool` (FA-04/RC-02 统计口径门可观测, 不假解锁; 未达 → 诚实 partial 双口径并列)。

### verify [6] 并列行 (MIN-02) — 镜像 `_lake` + 既有 [6] 行

- 新 helper `_minute_stats(data_dir) -> dict` 镜像 `_lake` (:76-86) 形态: 扫 `kline_minute` 分区 09:30 行 → `{symbols, rows, dates}`; [6] 行 (:281-283) 之后并列打印:
  `minute_stats: {m_syms}/{uni} = {m_ratio:.3f} (dates={m_dates}, caliber=statistical_minute_0930){' — PARTIAL' if m_ratio < 1.0 else ''}` — 分母 = 运行期 `uni["total"]` (A4)。
- 测试镜像 `_seed_daily`/`_seed_auction` 分区种子 + `_run` (DATA_DIR env 驱动 main) 断言双口径各行独立打印, 绝不出现 "100%" 字符串 (既有覆盖口径守卫沿用)。

### 夹具扩展面 — Phase 40 stockdb fixtures 扩展

- **冻结体**: `tests/fixtures/stockdb/` 新增分钟回填夹具 (如 `minute_backfill_20260803_20260804.json`), 形状 = 每行 `{"symbol","bar_time","freq","open","high","low","close","volume_hand","amount_yuan"}` (镜像 `minute_sh600519_20260805.json` 形状); 值 = 合法浮点/整数 + **每日期首根 bar_time == 09:30** (湖 09:30 anchor 约定, test_minute_sync_verify :130-147); 不编造「研究锚点」式数字。
- **消费**: 测试 helper `_load_canned_fetch()` 读夹具 → 包装为 `fetch(symbols, start_time, end_time)` (symbol 过滤 + 窗口过滤 + canonical 列集 cast) 注入驱动 — 零网络 hermetic, 镜像 Phase 40 `_load_fixture` + `_JsonTransport` 注入面。
- **分区种子**: 报告/digest 测试不依赖驱动 — 直接 `_write_auction_partition` 同款 helper 写 `kline_minute/date=*/part.parquet` (镜像 test_auction_validation_report :64-70 / test_verify_auction_backfill :21-53)。

### 源插件 seam (MIN-03) — 诚实覆盖声明

- `MINUTE_SOURCE_PROFILES` 常量 (kline_sync.py): 4 profile — `tushare-stk_mins` (全历史/09:30✓/amount✓)、`tencent-mkline` (≈3 日/09:30✓/amount 派生)、`tdx-pytdx` (≈90 日/**09:30✗**/amount✓)、`canned-fixture` (测试面) — 字段 `{label, depth_note, has_0930_bar, amount_available}`, 值 = 42-RESEARCH 实测矩阵冻结 (RESEARCH Pattern 1)。
- 驱动 `source_label: str | None = None` 可选参数 → 日志/台账透传; digest `minute_stats.source` = build_report 新参数 `minute_source` 或 `"unknown"` (**诚实默认未知** — 湖无 provenance 列铁律, 报告不猜源)。
- 覆盖不虚报: 腾讯 3 日深度 → digest `dates_covered` 只含实际分区 + `source` 标注 (RESEARCH Pitfall 2 的「3 日假象」被 dates_covered 显式暴露)。

## 命名与测试惯例

- **caliber 常量**: 字面量 `"statistical_minute_0930"` (digest + verify [6] 逐字一致, 测试可断言)。
- **source label 常量**: profile 键字面量 `tushare-stk_mins` / `tencent-mkline` / `tdx-pytdx` / `canned-fixture`; digest 缺省 `"unknown"`。
- **unlock 门常量**: `unlock_threshold = 0.94` (FA-04/RC-02, 测试断言 digest 字段值)。
- **注入面**:
  - 驱动: `fetch=` 参数注入 canned 帧 (零网络); 断言请求窗口用记录型 wrapper (`_RecordingFetch` 记录每次调用的 symbols/start/end)。
  - digest: 直接种子 `kline_minute/date=*` 分区 + `repo_env` fixture 跑 build_report。
  - verify: `_seed_*` 分区种子 + `_run` (monkeypatch DATA_DIR)。
- **回归锁**: 写面抽取后 `test_minute_sync_verify.py` / `test_minute_timestamp_convention.py` 必须全绿 (sync_and_persist_minute 行为不变); MIN-03 后诚实回归族 (test_0930_excluded / probe 窗口 / engine 截断族) 必须保持绿 — 统计口径只加报告面, 绝不动写湖/探针。
- **fetch 异常纪律**: 驱动不吞 fetch 异常 (40203/超时上抛), CLI 捕获 → exit 2 + stderr, 绝不伪装空帧/伪 skip (41-01 先例)。

## 关键差异点 (42 后 vs 现状反模式)

| 维度 | Phase 42 后 | 现状 (反模式) |
|---|---|---|
| 分钟历史回填 | 驱动 + per-symbol 跳过 + merge-upsert 写面 (零源依赖可测) | 只有 sync_and_persist_minute (全局 last_dt, 会误伤全量窗口) |
| 分钟覆盖报告 | 双口径并列 (canonical + minute_stats 统计口径, caliber 标注, dates_covered) | 只有 canonical 44/5538 ≈ 0.79% 单口径 |
| 09:30 bar 标注 | 「集合竞价统计 (非逐笔)」显式标注 (报告/manifest 面) | v1.3 绝对化「永不标集合竞价」+ `_MINUTE_NOTE` 声称历史 CLOSED |
| 源覆盖声明 | source profile + dates_covered + checkpoint gate (绝不虚报) | 假设 Tushare 全量可行 (未实测凭证档位) |
| 统计口径写入 | 只进报告 digest | (无 — 全新面; canonical 555..565 排除保持, test_0930_excluded 绿) |
