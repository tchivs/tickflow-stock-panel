# Phase 36 研究 — 全量竞价回填 (Full-Universe Auction Backfill)

**Researched:** 2026-08-07
**Source:** `.planning/research/v2.4-full-universe/AUCTION-FULL-BACKFILL.md` (ResearcherV24A, confidence HIGH, 实测驱动)
**Implementation-ready:** YES — 全部证据 file:line + 实测数字; 最小增量 3 项 (resume ~20 行 / 超时豁免 ~8 行 / CLI ~80 行)

## Verdict

**FEASIBLE** — 5537 宇宙 × 248 日, 3.5-5.5h (含裕量), 全湖 ~13 MB, 磁盘 1TB 余量, ext 原子 rename 无 overlay 顾虑。需修 1 个 HIGH 阻塞 (600s 自杀) + 2 个机械缺口 (resume/CLI)。BJ 333 上游恒空 → 覆盖上限 94.0% 诚实台账。

## 实测锚点 (2026-08-07, 全部本会话实测)

| 项 | 值 | 证据 |
|---|---|---|
| 宇宙 | 5537 (SZ 2894 / SH 2310 / BJ 333); kline_daily 1,326,996 行 | DuckDB 视图, `_lake_distinct_symbols` 同源 |
| 湖现状 | kline_auction 2 symbol × 248 日 = 496 行 = 0.04% | 32-02-SUMMARY.md:45-46 |
| 延迟 pilot | n=20 live: mean 0.96s / median 0.82s / p95 1.24s / max 2.49s; **0×429**; 全前缀 10/10 满 248 行 | 3.2 |
| BJ probe | 6 只 920xxx → 0 行; 5 替代格式 (BJ920016/920016.BJ/bj920016 等) → `请求参数错误`; **上游无 BJ 竞价数据** | 3.2 #3/#4 |
| 写路径 | 2-row 分区 0.67s/标的 → 满 5537-row 分区 1.15s/标的; 满分区 45 KiB → 全湖 ≈ 11-13 MB | 3.3 |
| 总时长 | rpm 30 ≈ 3.4-3.8h; 含裕量 **3.5-5.5h** (工作量主导, rpm 30/60 无差) | 3.4 |
| 磁盘 | data/ 134M; df 2.0T 1008G 可用; fs ext2/ext3 | 3.7 |

## 关键代码事实

- **HIGH 阻塞 — 600s 自杀**: `STALE_JOB_TIMEOUT_S = 600` (pipeline_jobs.py:29); `reap_stale()` 于轮询端点调用 (pipeline.py:45,132,173); 回填循环合作式取消 `j["status"]=="failed"` → break (auction_backfill.py:215-219)。**经 API 全量回填 ~10 分钟必死**。修复: `job_store.create(timeout_s=...)` + `reap_stale` 用 `j.get("timeout_s", STALE_JOB_TIMEOUT_S)` (pipeline_jobs.py:227-255); backfill API 传 21600。
- **无 resume**: `run_auction_backfill` 主循环 (auction_backfill.py:209-251) 无条件 fetch+write; 无覆盖扫描/only-missing/checkpoint。幂等 merge-upsert (auction_sync.py:99-104) 是唯一恢复资产 → 中断重跑浪费 3.5h。最小诚实形态 ~20 行: 开工前 `SELECT symbol, COUNT(*) FROM kline_auction WHERE datetime ∈ aligned_dates GROUP BY symbol`, 计数 == len(aligned_dates) 跳过 (镜像 `_lake_distinct_symbols` :67-88)。
- **CLI 缺口**: `backend/scripts/` 只有 auction_backtest.py (operator CLI 模板); 无回填 CLI。CLI 路径 job_id=None → 不触 job_store (无 reap/单飞/重启中断), 是 detached 全量跑的载体。
- **API 现状**: `POST /api/kline/auction/backfill` (api/auction_backfill.py:62-83 参数 symbols/start/end/rpm 1..60, `_MAX_SYMBOLS=6000` > 5537 合法; :97-119 run slot + executor + invalidate)。
- **EOD 无冲突**: `auction_sync_enabled` 默认 False (preferences.py:129-131); 回填绝不 consult 偏好 (auction_backfill.py:10-12); 写缝共享幂等 (已覆盖 symbol 重写 = no-op crop, 实测 496 行不变); 跨进程并发写无锁 → 调度纪律避开 EOD 窗口。
- **probe**: resolve_auction_probe 无缓存 (auction_probe.py:139-186); R3 短 TTL 缓存确认延期 (32-01-PLAN.md:28); 回填循环内不调 probe, 入口闸门 1 次。
- **限速**: rpm 默认 30, 校验 1..60 (api/auction_backfill.py:75); `rate_limits._reserve_slot` 进程级共享 (rate_limits.py:31-56); 429 → 2 次指数退避 2s→4s (auction_backfill.py:102-121)。

## 回填后解锁 (0.04% → ~94%)

Run B 重跑 coverage.symbols `{auction_symbol_count:5204, enriched:5537, ratio:0.94, rows:1290592/1373176}`; validation data_gate "available"; requires_auction_data 4 策略全市场真列 (engine.py:346-348); recap Block 1 活跃度 (auction_recap.py:275-289); pool_hub 真列 (pool_hub.py:179-225)。

## 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| 600s 自杀 (API 路径) | HIGH 阻塞 | FA-01 修复; CLI 天然绕过 |
| 上游 3-5h 持续限速/宕机 | MEDIUM | 429 退避; 宕机逐 symbol 台账继续; only-missing 续跑 |
| 服务重启中断 (API 路径) | MEDIUM | detached CLI 不受影响 |
| 跨进程并发写丢行 | MEDIUM | 调度纪律 (避开 EOD 窗口); 进程内 run slot 串行 |
| BJ 硬缺口 | LOW (预期) | 333 恒 empty_response; 覆盖 ≤94.0% 明示; 上游补号段后 only-missing 自动补 |
| 磁盘 | LOW | ~13 MB, 1TB 余量 |

## 验收口径

- 终态 dict: requested=5537, backfilled≈5204, failed=333 全为 `{symbol, reason:"empty_response"}` 且 symbol ∈ BJ 920 号段; rows≈1,290,592; dates=248。
- 抽查: ≥3 日期 × ≥3 symbol `auction_virtual_price` == kline_daily.open。
- 湖终态: 248 分区 × ~5204 行, 无 `.tmp` 残留; `--only-missing` 顶补稳定 (连续两次 0 新增)。
- 回归: 既有回填测试全绿 (test_auction_backfill*.py 系), 新增 FA-01/02/03 测试。

## 执行编排 (D7)

36-01 (代码 delta: FA-01/02/03) 落地 → **立即 detached 启动全量回填** (CLI, 日志 /tmp/auction-backfill-*.log, 3.5-5.5h) → 36-02/03 (文档/CLI 细化/回归) 并行 → 验证期回收结果 (进度/台账/顶补/交叉验证)。
