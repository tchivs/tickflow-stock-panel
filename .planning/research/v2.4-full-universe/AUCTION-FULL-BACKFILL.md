# 领域 R1 研究:全量竞价回填与长作业 (Full-Universe Auction Backfill & Long-Job Mechanics)

**Research domain:** v2.4 全量数据解锁 (Full Data Unlock) — 领域 R1 全量竞价回填 (5537 标的 × 248 交易日)
**Researched:** 2026-08-07
**Researcher:** ResearcherV24A
**Confidence:** HIGH (代码 seam 逐行核验 + 20 次 live probe 实测 + 写路径基准实测) / MEDIUM (3-5h 持续限速为外推, 未做小时级长跑)

---

## 0. Verdict

**FEASIBLE — 全量竞价回填可落地, 预估 3.5–5.5h (含裕量), 需 3 项最小代码增量 (resume/only-missing、job 超时豁免、operator CLI); 存在一个硬覆盖上限:BJ 板块 333 只上游无数据, 最高覆盖 94.0% (5204/5537), 余下如实记 empty_response 台账。**

- 机械可行性已实测: 上游 `xyz` MCP `stockdb_get_call_auction` 对 SZ/SH 全前缀 (000/001/002/300/301/600/601/603/605/688) 单请求返回满 248 行, 延迟中位 0.82s (n=20, min 0.38 / max 2.49 / mean 0.96); 写路径基准: 当前 2-symbol 分区 0.67s/标的, 满规模 5537-row 分区 (45 KiB) 1.15s/标的 → 全湖终态仅 ~11 MB。
- **机械缺口 (无 resume/checkpoint)**: `run_auction_backfill` 无「跳过已写标的」逻辑, 无 `--only-missing`; 重跑幂等但全量重抓 (浪费 ~3.5h)。中断后恢复需手工续跑。
- **长作业阻塞点 (必须修)**: `STALE_JOB_TIMEOUT_S = 600` (pipeline_jobs.py:29) — 轮询端点 `reap_stale()` 在运行 600s 后把 job 标记 failed (pipeline.py:173), 回填循环的合作式取消 (auction_backfill.py:215-219) 随即 break → **经 API 触发 + 前端轮询的全量回填会在 ~10 分钟处自杀**。
- **BJ 硬缺口 (实测)**: 湖内全部 333 只 BJ 均为 920xxx 新号段, 上游对裸码 `920016` 返回 0 行, 5 种替代格式 (BJ920016/920016.BJ/bj920016 等) 均 `请求参数错误` → BJ 覆盖率为 0, 已由 `test_auction_backfill_bj_stock_empty_response_recorded` (tests/test_auction_backfill_honesty.py:262) 固化为预期诚实行为。
- **推荐**: 沙箱与 operator 双跑可行; 首选 operator 在沙箱内以 detached CLI 跑全量 (零 POST、无 auth 闸门、日志落盘、无 reap 干扰), API POST 路径在超时豁免落地后作为运营备选。回填时间窗避开 EOD run_all (跨进程写缝未加锁)。

---

## 1. 目标

1. 全量回填机械可行性: 宇宙数复测、每请求延迟复测、resume/checkpoint 现状、`--only-missing`/symbol-list 输入是否存在。
2. 长作业运行时风险: 2.5–5.5h 任务的进程模型 (API 线程 vs detached CLI)、磁盘投影、文件系统原子性。
3. probe 长跑稳定性: 每调用一次 HTTP? 有无缓存? R3 短 TTL 缓存确认延期; 3–5h 限速风险 (rpm 默认 30, 1..60 可配位置)。
4. EOD 双闸门交织: `auction_sync_enabled` 默认 False; 248 天全量回填是否与 EOD 实时同步冲突; 分区存在性 crop; 并发写原子性 (单写者假设)。
5. operator vs 沙箱分工: 沙箱网络已证可达; 以 ≤10 标的 pilot 复测延迟 + 429 行为。
6. 回填后解锁盘点: 覆盖 0.04% → ~94% 翻转; Phase 34 Run B 重跑; validation data_gate; auction-active/活跃度表面。

## 2. 背景

- v2.3 已落地竞价写湖全链路 (Phase 32/33/34): `xyz_provider.get_auction` (xyz_provider.py:169-225)、`auction_probe` available 翻转、`auction_backfill.run_auction_backfill` (auction_backfill.py:124-251)、单一写路径 `write_auction_partitions` (auction_sync.py:57-112)。
- 当前湖态: kline_auction = **2 symbol × 248 日 = 496 行**, 覆盖 2/5537 ≈ 0.04% (Phase 32-02 以 `{"symbols":["000001.SZ","000002.SZ"],"rpm":60}` 回填, 32-02-SUMMARY.md:45-46)。
- v2.3 研究 (AUCTION-BACKFILL.md) 已给「单 symbol 单请求取满 248 行、1.6s/请求、~5500 symbols → 1.5-3h」估计; 本研究的任务是**实测校准** (含写路径成本) 并审计长作业机械。
- Phase 34-03 已注明「全量回填 3-5.5h 解锁全宇宙真列」(34-03-SUMMARY.md:44)。
- BT-07 全量竞价回测 gate 仍 defer, 依赖湖有足够历史分区 (v2.2-REQUIREMENTS.md:60)。

## 3. 证据

### 3.1 宇宙复测 (repo 实测, DuckDB 视图)

```
backend/.venv/bin/python: CREATE VIEW kline_daily AS read_parquet('../data/kline_daily/**/*.parquet')
→ distinct symbols = 5537 (SZ 2894 / SH 2310 / BJ 333)   # 与 Phase 32 逐字一致
→ total daily rows = 1,326,996                            # 平均 239.6 行/标的 (含新股/停牌短历史)
```
- 方法: `_lake_distinct_symbols` 同源 (`auction_backfill.py:67-88`, DuckDB 视图优先)。
- 湖内 BJ 号段全为 `920xxx` (`SELECT DISTINCT symbol WHERE '%.BJ'` → {'92': 333})。

### 3.2 上游 live 实测 (2026-08-07, 共 28 次请求, 全部直连 `http://8.138.149.215:7898/mcp`)

| # | 采样 | 结果 |
|---|---|---|
| 1 | 随机 10 标的 (SZ/SH 混合, `random.seed(7)`) × 248 日区间 | **10/10 返回满 248 行**, 列 = symbol/datetime/auction_volume/auction_amount/auction_virtual_price (current 恒有值) |
| 2 | 10 前缀采样 (688/300/002/000/600/601/603/605/001/301) | **10/10 满 248 行** → SZ/SH 全前缀无缺口 |
| 3 | BJ 6 只 (920016/920029/920033/920047/920066/920089) | **6/6 返回 0 行** (0.38-1.78s) |
| 4 | BJ 替代格式 (920016 裸码 / BJ920016 / 920016.BJ / bj920016 / "bj 920016" / "BJ 920016") | 裸码 0 行; 其余 5 种 `请求参数错误` → **上游无 BJ 竞价数据, 且非格式问题** |
| 5 | 延迟统计 (n=20 SZ/SH) | min 0.38s / max 2.49s / **mean 0.96s / median 0.82s / p95 1.24s** (首批含连接预热) |
| 6 | 429/限速观测 | 28 次请求 **零 429**, 1 req/s 突发无节流迹象; 单 symbol 强制 (multi-symbol → `带宽限制批量请求`) 与 v2.3 实测一致 |

校准结论: 每请求名义 1.6s (v2.3) → 实测 mean 0.96s, 但尾长明显 (2.0-2.5s 偶发), 全量 5537 请求的真实均值预计高于 pilot (1.0-1.2s 量级)。

### 3.3 写路径基准 (repo 实测, 真实湖 + 临时满规模湖)

```
write 1 symbol (248 分区, 当前 2-row 分区):  0.67s  → 5537 标的投影 1.0h
write 1 symbol (248 分区, 5537-row 满分区):  1.15s  → 5537 标的投影 1.8h (上界)
满分区文件实测 45 KiB → 全湖 248 分区 ≈ 11 MB  (现 2.0M → 终态 ~13 MB)
```
- 写路径 = 每 symbol 248 次分区 read-modify-write (`write_auction_partitions` :87-112: 存在则读旧 → concat → `unique([symbol,datetime], keep="last")` → `.tmp` 原子 rename)。
- 成本随分区增长近线性 (2.7ms/op → 4.6ms/op), 全程均值 ~0.9s/标的。

### 3.4 时长估计 (实测驱动)

| 项 | 值 | 来源 |
|---|---|---|
| 请求数 | 5537 (SZ/SH 5204 + BJ 333 空返回) | 3.1 |
| fetch | ~1.0s/标的 (mean 0.96 + 尾长) | 3.2 |
| write | ~0.9s/标的 (0.67→1.15 增长均值) | 3.3 |
| 限速 (rpm 30) | 2.0s/slot 与工作量 (~1.9s) 相抵 → 节奏 ≈ 2.2-2.5s/标的 | rate_limits.py `_reserve_slot` |
| 限速 (rpm 60) | 1.0s/slot < 工作量 → 节奏 ≈ 2.0-2.2s/标的 | 同上 |
| **总时长** | rpm 30 ≈ 3.4-3.8h; rpm 60 ≈ 3.1-3.4h | 5537 × 节奏 |
| **含裕量** | **3.5-5.5h** (上游尾长 2.5s、429 退避重试 2+4s、网络抖动) | +30-50% |

注: rpm 30 vs 60 对总时长几乎无差 —— 工作量 (~2s) 已吞掉 1-2s 的限速间隔; 吞吐瓶颈在 fetch+write, 不在 rpm。BJ 333 只约浪费 3-6 分钟请求并产生 333 条预期失败台账。

### 3.5 resume/checkpoint 审计 (机械缺口)

- **无跳过已写逻辑**: `run_auction_backfill` 主循环 (auction_backfill.py:209-251) 对每个 symbol 无条件 `_fetch_auction` + `write_auction_partitions`; 无 kline_auction 存在性扫描、无 `--only-missing`、无 checkpoint 文件。CLI/API 均无 symbol-list 之外的续跑参数 (API body 仅 `symbols/start/end/rpm`, auction_backfill.py:62-83)。
- **幂等是唯一的「resume 资产」**: 分区 merge-upsert (auction_sync.py:99-104) 保证重跑只补差、不重复、不损坏 → 中断后可整体重跑, 代价是已完成的 3.5h 重来一遍。
- **resume 的最小诚实形态** (实现成本 ~20 行): 开工前 `SELECT symbol, COUNT(*) FROM kline_auction WHERE date ∈ [start,end] GROUP BY symbol`, 计数 == len(aligned_dates) 的 symbol 跳过 (镜像 `_lake_distinct_symbols` 的 DuckDB 视图查询)。语义: 覆盖即跳过, 部分覆盖 (中断残留) 重抓 — 与 merge-upsert 幂等互补。
- **`_MAX_SYMBOLS = 6000`** (api/auction_backfill.py:37): 全量 5537 < 6000, 显式传全列表合法; `symbols: null` 走湖 DISTINCT 全量。

### 3.6 长作业进程模型与单飞

- **API 路径**: `POST /api/kline/auction/backfill` → `job_store.create()` 单飞 (pending∨running 复用, pipeline_jobs.py:99-113) → `try_acquire_run_slot()` 重任务槽 (与 EOD/run_all/pool backfill 互斥, pipeline_jobs.py:314-322) → `_long_task_executor` (max_workers=2) 线程跑 `run_auction_backfill` (api/auction_backfill.py:108-115) → `invalidate_storage_cache()`。
- **⚠ 600s 自杀陷阱 (本研究会话新发现)**: `STALE_JOB_TIMEOUT_S = 600` (pipeline_jobs.py:29); `reap_stale()` 在 `/run`、`/run_all`、`/jobs/{id}` 轮询端点调用 (pipeline.py:45,132,173); 回填循环合作式取消检查 `j["status"] == "failed"` → break (auction_backfill.py:215-219)。**前端轮询 600s 后即触发: job 标记 failed → 循环 break → 全量回填死于 ~10 分钟 (~400-600 标的处)**。这是经 API 跑全量的**硬阻塞**, 必须随回填落地一并修复。
- **进程重启**: running/pending job 仅存内存 (pipeline_jobs.py:10-14, 终态才落盘 data/job_store/*.json); 服务重启后 `job_store.get(job_id)` 为 None → 循环 break (auction_backfill.py:217)。API 路径要求服务进程 3.5-5.5h 不重启。
- **detached CLI 路径**: 绕开 job_store → 无 reap、无重启中断、无单飞, 但也没有进度 UI 与并发写保护 (与 EOD 的互斥仅靠调度纪律)。当前 `backend/scripts/` 无 auction 回填 CLI (仅 auction_backtest.py) → 属最小增量。

### 3.7 磁盘与文件系统

- `data/` 现 134M; kline_daily 30M / kline_auction 2.0M。全量后 kline_auction ≈ 13 MB (3.3 实测投影) — **磁盘无压力**。
- `df -h`: /dev/vda2 2.0T, 可用 **1008G** (48% 已用)。
- 文件系统 `stat -f` → **ext2/ext3** (非 btrfs/overlayfs); `.tmp` 同目录 rename 在 POSIX ext 上原子 (auction_sync.py:45-55), 无 overlayfs 写时复制/页面缓存顾虑 — 预期无问题, 实证为 ext。

### 3.8 probe 长跑稳定性 (R3)

- `resolve_auction_probe()` 每次调用 1 次实时 HTTP (auction_probe.py:139-186), **无任何缓存** (无 lru_cache/ttl); 返回后即弃。实测 probe 状态 available, source=xyz。
- **R3 短 TTL probe 缓存确认仍延期**: 32-01-PLAN.md:28 与 T-32-01-06 明言「短 TTL probe 缓存是 32-03 文档化后续守卫」; 32-03-PLAN.md:29 注记为 doc-only 不实现; 当前代码仍无缓存 → 确认延期, 与本任务无关 (回填循环内不调 probe, 只有入口闸门 1 次)。
- 限速: rpm 默认 30, 端点校验 1..60 (api/auction_backfill.py:75); 节流走 `rate_limits.sleep_between_batches` → 进程级共享 `_reserve_slot` 时间轴 (rate_limits.py:31-56), 跨调用方聚合不超速; 429/限速文案 → 指数退避重试 2 次 (2s→4s, auction_backfill.py:102-121 `_RETRY_MARKERS`/`_RETRY_BASE_WAIT_S`)。
- 3-5h 持续 1 req/s 的 rpm 上限 UNKNOWN (28 请求短窗零 429); 上游宕机 → 每 symbol 记异常台账继续 (fail-closed 语义, 湖不损坏); 恢复后 resume 补抓。

### 3.9 EOD 双闸门交织 (无冲突, 已验证)

- `auction_sync_enabled` 默认 False (preferences.py:129-131); EOD `_run_auction_sync` 双闸门 = 偏好 + probe (daily_pipeline.py:696-708); 回填**绝不 consult** 该偏好 (auction_backfill.py:7-12 docstring 铁律) — 全量回填与 EOD 定时路径互不触发。
- **写缝共享**: 回填与 EOD 都经 `write_auction_partitions` 单一写路径 (auction_sync.py:57-112) — 窗口谓词 (555..565) → canonical 裁剪 → 分区 merge-upsert → `.tmp` 原子 rename。EOD 对已覆盖 symbol 的当日写 = 与湖内同键行 merge (keep="last" 同值) → **幂等 no-op crop, 无损坏** (实测: 对已含 000002.SZ 的湖重写 000002.SZ → 496 行前后不变)。
- **并发写原子性 / 单写者假设**: 分区写入是 read-modify-write, 仅最终 rename 原子 → 同分区并发写者可能丢行 (last-rename-wins)。进程内由 run slot 串行 (API 路径, `_heavy_run_lock`); **跨进程 (CLI 回填 × API EOD) 无锁** → 调度纪律: 回填避开 EOD run_all 窗口 (盘后 15:00-15:30 前后), 或经 API 路径持有 run slot。
- **EOD 时间窗**: 回填写的是 [start,end] 历史日; 当日实时行仍依赖当日 probe+sync 链路 (sync_and_persist_auction 当日路径, auction_sync.py:154-180) — 回填不会冒充当日行 (写边界 = kline_daily 分区 ∩ 范围, auction_backfill.py:164-173; 上游多返回日期绝不 phantom-write)。

### 3.10 回填后解锁盘点 (覆盖 0.04% → ~94%)

| 表面 | 现状 (2-symbol 湖) | 全量后 (5204 symbol 真列) | 证据 |
|---|---|---|---|
| Phase 34 Run B 回测 | auction_symbol_count=2, ratio 0.04%, 496/1373176 | ~5204/5537, ratio ≈ 0.94; fast_grab/allround/t1_flash pre_open 池从 2 标的 → 全市场 | 34-02-SUMMARY.md:33, 34-03-SUMMARY.md:51-55 |
| 验证报告 data_gate | `"empty"` (no_auction_partitions 仅在无分区时; 现 2-symbol 时 enabled_dates 全有但 symbol 覆盖 2) | `"available"` (auction_validation.py:196-199); coverage.symbols 5 键翻转 | auction_validation.py:196-201, 260-309 |
| BT-07 全量竞价回测 gate | defer (湖分区不足) | 解锁 (v2.2-REQUIREMENTS.md:60) | — |
| 策略引擎真列分支 | requires_auction_data 4 策略 (fast_grab/allround/t1_flash/alpha) 全市场真列分支生效 | engine.py:346-348; auction_alpha.py:53-61 |
| 复盘 Block 1 竞价活跃度 | auction_volume_ratio 仅 2 symbol | 全市场真实 活跃度 (auction_recap.py:275-289; auction_columns.py:58-88) | — |
| 盘前监控 PM-01 | 2-symbol degraded | 全市场真实竞价列 (pool_hub.py:179-225) | — |
| 研究 API | data_gate empty 或 2-symbol 覆盖 | 全市场覆盖; D-02 诚实数字翻转 | research_auction.py:11-13 |
| **BJ 上限** | — | 333 只 BJ 永远空 (上游无数据) → **最高 94.0%**, 不可声称 100% | 3.2 #3/#4 |

## 4. 结论

1. **机械可行**: SZ/SH 5204 只单请求满覆盖 (248 行, mean 0.96s), 写路径满规模 1.15s/标的, 全湖仅 ~13 MB; 磁盘 1TB 余量, ext 原子 rename 无 overlay 顾虑。
2. **时长实测校准**: 5537 标的 × ~2.2s (fetch 1.0 + write 0.9 + 节奏) ≈ 3.1-3.8h; 含裕量 **3.5-5.5h** — 与 34-03 既有注记一致。rpm 30/60 差异可忽略 (工作量主导)。
3. **resume/checkpoint 缺口存在**: 无跳过已写、无 only-missing、无 CLI; 幂等重跑是唯一恢复手段 (浪费全程)。最小增量 = 开工前 kline_auction 覆盖扫描 (~20 行)。
4. **长作业机制阻塞**: `STALE_JOB_TIMEOUT_S=600` + 轮询端 `reap_stale` + 合作式取消 → API 路径全量回填 ~10 分钟自杀, **必须修**; 进程重启中断 (内存 job 态)。
5. **BJ 硬缺口 (新实测)**: 333/5537 (6.0%) 上游恒空 (920 号段, 5 种替代格式均失败) → 覆盖上限 94.0%, 已由既有测试固化为诚实台账。
6. **EOD 无冲突**: 双闸门默认关; 回填不 consult 偏好; 写缝共享且幂等 (merge-upsert crop); 单写者假设进程内成立 (run slot), 跨进程靠调度纪律。
7. **probe 每调用 1 次 HTTP, 无缓存**: R3 短 TTL 缓存确认延期 (32-01/32-03 注记, 代码实证); 回填循环内不调 probe, 无影响。

## 5. 建议

### 5.1 最小代码增量 (可一 phase 落地, 全部小改)

1. **resume/only-missing (~20 行, 优先)**: `run_auction_backfill` 增加 `only_missing: bool = False`; 为 True 时开工前 `SELECT symbol, COUNT(*) FROM kline_auction WHERE CAST(datetime AS DATE) ∈ aligned_dates GROUP BY symbol` (镜像 `_lake_distinct_symbols` 的 DuckDB 视图), 计数 == len(aligned_dates) 的 symbol 跳过; API body 增 `only_missing` 键。与 merge-upsert 幂等互补 (部分覆盖重抓)。
2. **job 超时豁免 (~8 行, 阻塞级)**: `job_store.create(timeout_s=...)` 存入 job 记录; `reap_stale` 用 `j.get("timeout_s", STALE_JOB_TIMEOUT_S)` (pipeline_jobs.py:227-255); backfill API 传 `timeout_s=21600` (6h)。防止 600s 自杀。
3. **operator CLI `backend/scripts/auction_backfill.py` (~80 行)**: 镜像 `auction_backtest.py` (O1 零 POST, META 默认 O2): `--symbols|--all --start --end --rpm --only-missing`; job_id=None → 不触 job_store (无 reap/无单飞, 进度打 stdout + 终态 dict 落 JSON 文件)。detached 运行的载体, 也是沙箱全量跑的通道。
4. **(可选) `--exclude-bj`**: 跳过 333 只 BJ 省 3-6 分钟并让台账 100% 干净; 默认保持诚实全量 (BJ 记 empty_response, 既有测试锚定行为)。

### 5.2 运行分工 (sandbox vs operator)

- **推荐: operator 在沙箱以 detached CLI 跑全量** — 沙箱网络已证可达 (3.2 全程本沙箱直连实测); repo `data/` 本沙箱可写; CLI 路径无 auth 闸门 (live server :3018 需登录, 且其 cwd 在 /app 容器路径, 与 repo data 关系无法取证); 日志落盘 + 终态 dict JSON, 3.5-5.5h 无交互。
- **备选: API POST** (rpm 30, 轮询进度 UI, 单飞 + run slot 内建) — 需先落地 5.1-2 (超时豁免), 否则 600s 自杀。
- **调度纪律**: 回填时间窗避开 EOD run_all 与 pool backfill (跨进程写缝无锁; 同进程内 run slot 已互斥); 建议盘后 15:30 后启动或周末。
- 进度: CLI 每 symbol emit (stage_pct), 每 100 标的可加一条累计日志行; 中断后用 `--only-missing` 续跑, 预计续跑 ≤ 剩余量。

### 5.3 验收口径

- 终态 dict: `requested=5537, backfilled_symbols≈5204, failed≈333, failed_symbols` 全为 `{symbol, reason:"empty_response"}` 且 symbol ∈ BJ 920 号段; `rows=1,290,592` (5204 × 248) 量级; `dates=248`。
- 抽查: 5-10 只 SZ/SH 的 `auction_virtual_price` 与该日 kline_daily open 逐值相等 (既有 test_auction_backfill_cross_check 同法)。
- 覆盖翻转: Phase 34 Run B 重跑, coverage.symbols → `{auction_symbol_count:5204, enriched_symbol_count:5537, symbol_coverage_ratio:0.94, auction_rows_present:1290592, auction_rows_expected:1373176}`。
- 湖终态: 248 分区, 每分区 5204 行 (BJ 缺席), 无 `.tmp` 残留。

## 6. 风险

| 风险 | 等级 | 说明 / 缓解 |
|---|---|---|
| 上游 3-5h 持续限速/宕机 | MEDIUM | rpm 上限 UNKNOWN (短窗零 429); 429 → 2 次指数退避, 宕机 → 每 symbol 台账继续; 湖幂等不损坏; `--only-missing` 续跑 |
| 600s 自杀 (API 路径) | **HIGH (阻塞)** | `reap_stale` + 合作式取消联动; 5.1-2 修复; CLI 路径天然绕过 |
| 服务重启中断 | MEDIUM | API 路径内存 job 态 → 循环 break; detached CLI 不受影响; `--only-missing` 续跑 |
| 跨进程并发写丢行 | MEDIUM | read-modify-write 仅 rename 原子, last-rename-wins; 进程内 run slot 串行, 跨进程靠调度 (避开 EOD 窗口) |
| BJ 硬缺口 | LOW (预期) | 333/5537 恒 empty_response; 覆盖上限 94.0%; 既有测试锚定; 未来上游补 BJ 后 `--only-missing` 自动补 |
| 上游代码格式漂移 | LOW | 5 种 BJ 替代格式已实测失败; 若上游改号段, resume 重跑即补 |
| 磁盘 | LOW | 全湖 ~13 MB (实测 45 KiB/满分区); 1TB 余量 |
| 上游吞请求 (无响应/空串) | LOW | `_call_tool` 空串 → 空 df → `_has_daily_rows` 启发式区分空 vs 宕机 (auction_backfill.py:90-99,222-235) |

## 7. 附录

### 7.1 证据索引 (file:line)

- `backend/app/services/auction_backfill.py:124-251` (run_auction_backfill 主循环; 无 skip/resume) / `:102-121` (429 指数退避) / `:67-88` (universe) / `:215-219` (合作式取消 break) / `:222-235` (empty vs 宕机启发式)
- `backend/app/services/auction_sync.py:57-112` (write_auction_partitions: 窗口谓词 + canonical 裁剪 + merge-upsert + `.tmp` rename) / `:45-55` (_atomic_write_parquet) / `:154-180` (EOD 当日 sync)
- `backend/app/services/pipeline_jobs.py:29` (STALE_JOB_TIMEOUT_S=600) / `:99-113` (create 单飞) / `:227-255` (reap_stale) / `:314-322` (run slot)
- `backend/app/api/auction_backfill.py:62-83` (参数校验, rpm 1..60, _MAX_SYMBOLS=6000) / `:89` (reap_stale) / `:97-119` (run slot + executor + invalidate)
- `backend/app/api/pipeline.py:45,132,173` (reap_stale 调用点)
- `backend/app/services/auction_probe.py:139-186` (resolve_auction_probe, 无缓存) 
- `backend/app/data_providers/xyz_provider.py:57` (auction=True) / `:169-225` (get_auction) / `:258-269` (_call_tool 空串吞错)
- `backend/app/services/preferences.py:129-131` (auction_sync_enabled 默认 False)
- `backend/app/jobs/daily_pipeline.py:696-708` (EOD 双闸门)
- `backend/app/tickflow/rate_limits.py:31-56` (_reserve_slot 共享限速) / `:118-128` (sleep_between_batches)
- `backend/app/services/auction_validation.py:196-201` (data_gate) / `:260-309` (coverage.symbols) / `:419-427` (n_symbols_covered)
- `backend/app/services/auction_columns.py:58-88,130-135,261-272` (auction_volume_ratio 派生, PIT-safe)
- `backend/app/services/auction_recap.py:275-289` (复盘活跃度)
- `backend/app/api/research_auction.py:11-13` (data_gate D-02)
- `backend/scripts/auction_backtest.py` (operator CLI 模板)
- `backend/tests/test_auction_backfill_honesty.py:262` (BJ empty_response 锚定测试) / `:359` (virtual_price == open 交叉验证)
- `.planning/milestones/v2.3-phases/32-auction-backfill/32-02-SUMMARY.md:45-46` (2-symbol 回填终态) / `32-01-PLAN.md:28, T-32-01-06` (R3 延期) / `32-03-PLAN.md:29` (probe 缓存 doc-only)
- `.planning/milestones/v2.3-phases/34-auction-backtest/34-02-SUMMARY.md:33` (0.04% 锚点) / `34-03-SUMMARY.md:44,51-55` (全量 3-5.5h 注记 + Run B 数字)
- `.planning/milestones/v2.2-REQUIREMENTS.md:60` (BT-07 gate)

### 7.2 实测命令

```
# 宇宙复测
python -c "duckdb ':memory:' → CREATE VIEW kline_daily AS read_parquet('../data/kline_daily/**/*.parquet', union_by_name=true);
SELECT COUNT(DISTINCT symbol); SELECT substr(symbol,-2), COUNT(DISTINCT symbol) GROUP BY 1; SELECT COUNT(*)"
# 结果: 5537 (SZ 2894 / SH 2310 / BJ 333); 1,326,996 行

# 湖态
SELECT COUNT(DISTINCT symbol), COUNT(*) FROM kline_auction  → 2, 496; 分区 248 个

# 延迟 pilot (20 次 live)
random 10 (seed=7) + 前缀 10 → mean 0.96s / median 0.82s / p95 1.24s / max 2.49s; 0 429

# BJ probe (9 次 live)
920xxx ×6 → 0 行; 裸码 + 5 替代格式 → 0 行 / 请求参数错误

# 写路径基准
write_auction_partitions 1 symbol vs 当前 2-row 分区: 0.67s
写满 5537-row 临时分区 (45 KiB/分区) 后追加 1 symbol: 1.15s
全湖终态投影 ≈ 11 MB; data/ 现 134M; df: 2.0T 盘 1008G 可用; fs=ext2/ext3

# 服务器现状
:3018 有 uvicorn app.main:app (root, cwd=/app, 容器路径, 需登录鉴权); repo data/job_store/ 存有 Phase 32 回填 job 记录 (requested 1/2/5)
```

### 7.3 UNKNOWN / 未尽事项

- 上游 3-5h 持续 1 req/s 的 rpm 上限 (短窗实测零 429, 未做小时级长跑) → 回填 job 内已有退避 + resume, 最坏退化为分批续跑。
- 2010-至今完整覆盖在更早日期未抽验 (本任务范围只到 248 日窗; 诚实空返回 → 台账跳过, 不预填充)。
- 8.138.149.215 公网可达性漂移 → 全部闸门 fail-closed 已设计兼容。
