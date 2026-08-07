# Phase 36 模式映射 (Patterns)

**Mapped:** 2026-08-07 (orchestrator, from repo reads + v2.3 execution experience)

| # | 需求对象 | 现有模式 (file:line) | 复用方式 |
|---|---|---|---|
| 1 | 超时豁免 (FA-01) | `job_store.create` 单飞 + 记录 (pipeline_jobs.py:99-113); `reap_stale` (pipeline_jobs.py:227-255); `STALE_JOB_TIMEOUT_S=600` (:29); 轮询端点 (pipeline.py:45,132,173); backfill API 入口 (api/auction_backfill.py:89) | `create(timeout_s=...)` 持久化到 job 记录; `reap_stale` 改 `j.get("timeout_s", STALE_JOB_TIMEOUT_S)`; API 传 21600; 测试用 fake job dict 直接调 reap_stale |
| 2 | resume/only-missing (FA-02) | `_lake_distinct_symbols` DuckDB 视图查询 (auction_backfill.py:67-88); 主循环 (auction_backfill.py:209-251); API 参数校验 (api/auction_backfill.py:62-83) | 开工前覆盖扫描 `SELECT symbol, COUNT(*) … GROUP BY symbol` (COUNT == len(aligned_dates) 跳过); `only_missing` 参数贯穿 run_auction_backfill → API body |
| 3 | operator CLI (FA-03) | `scripts/auction_backtest.py` (CLI 模板: argparse, `--symbols/--range`, META 默认, 终态 dict JSON, `_preload_full_enriched`) | 镜像 CLI: `--symbols\|--all/--start/--end/--rpm/--only-missing`; job_id=None → 无 job_store; 进度 stdout; terminal dict (8 键) + failed_symbols → JSON 文件 |
| 4 | 全量实跑 (FA-04) | `run_auction_backfill` 完整循环 (auction_backfill.py:124-251); 写缝 `write_auction_partitions` (auction_sync.py:57-112, 窗口谓词/裁剪/merge-upsert/原子 .tmp); 取消检查 (:215-219) | detached bash 启动 (nohup, 日志落盘); 进度 poll 日志; `--only-missing` 顶补; 幂等重跑安全 |
| 5 | BJ 诚实 (FA-05) | `test_auction_backfill_bj_stock_empty_response_recorded` (test_auction_backfill_honesty.py:262); empty-vs-宕机启发式 (auction_backfill.py:222-235); 交叉验证测试 (:359) | BJ 333 恒 empty_response 台账已锚定; 文档 stance (5 格式实测) + coverage ≤94.0% 表述 |
| 6 | EOD 交织 (FA-06) | EOD 双闸门 (daily_pipeline.py:696-708); 幂等 crop (auction_sync.py:137-141); 偏好默认 False (preferences.py:129-131) | 回归测试: 重写已覆盖 symbol 行数不变; 纪律注记 (避开 EOD 窗口, 跨进程无锁) |
| 7 | 测试惯例 | module-object monkeypatch (非 string-target); 测试名嵌 token (`-k` 过滤); terminal dict 8/9 键契约 (auction_backfill.py:52-63,255-261) | 新测试照此: `test_full_backfill_*` 名嵌 token (timeout/reap/only_missing); fixture 用 tmp_path 湖 |
| 8 | 限速/重试 | `rate_limits._reserve_slot` (rate_limits.py:31-56); rpm 1..60 (api/auction_backfill.py:75); 429 退避 2s→4s ×2 (auction_backfill.py:102-121) | 不变; CLI 复用同一模块级限速 |

## 契约 (跨任务)

- `run_auction_backfill(symbols, start, end, rpm, only_missing=False, ...)` 签名向后兼容 (既有 API 路径不断)。
- terminal dict 键: `requested/backfilled/failed/dates/rows/elapsed_seconds/status/canceled` (8) + failed 时 `reason` (9)。
- job 记录新增键 `timeout_s` (可选, 缺省 600); 不影响旧记录。
- CLI 独立于 API (不 import job_store), 仅 import services (auction_backfill/auction_sync/rate_limits)。
