# Phase 43: T-day 竞价采集 sidecar — Pattern Map

**Mapped:** 2026-08-07 · **Files:** 6 新增 / 4 修改 / 1 夹具新增 / 2 文档同步 · **Analogs:** 全 exact (镜像面 = 40 stockdb 通道 / 36 回填 CLI+台账 / 30 告警链 / 27 独立分区+调度 / 20 canonical 写面; 无 No-Analog)

## File Classification

| File | Role | Closest Analog | Match |
|---|---|---|---|
| `backend/app/data_providers/stockdb_provider.py` (改: get_ticks) | provider | 自身 `get_minute` (:209-235: `_get_json` + X-API-Key header-only + typed 异常 + 限频) — tick 方法在其上加, 禁 URL 传参 | exact |
| `backend/app/services/auction_capture.py` (新增) | service | `premarket_snapshot.py` (`_DATE_RE` 守卫 + 独立分区 + temp+os.replace 原子写) + 40 限频纪律 + `_run_tracked` job 函数形态 | exact |
| `backend/app/services/auction_reconcile.py` (新增) | service | 42-02 `_minute_stats_coverage` amount 派生规则 (OHLC 全等 → vol×close×100) + stockdb /v1/minute 对账 | exact |
| `backend/app/services/auction_promote.py` (新增) | service | `auction_sync.write_auction_partitions` (555..565 谓词 + merge-upsert + 原子写 — 直接复用, probe 闸门不在其内, Pitfall 6) | exact |
| `backend/app/services/auction_sidecar_ledger.py` (新增) | service | `alert_store.py:1-41` (JSONL 追加 + 滚动清理 + 锁) + 36/41 台账 W-5 终态 dict 键集 | exact |
| `backend/app/jobs/daily_pipeline.py` (改: 三 job 注册) | jobs | 自身 :1140-1174 (CronTrigger mon-fri Asia/Shanghai + `_run_tracked` 单飞 + replace_existing) + :969-970 `_PREMARKET_JOB_ID` 09:26 同槽位先例 | exact |
| `backend/tests/fixtures/ticks/sh600519_20260807_window.json` (新增) | fixture | Phase 40 `tests/fixtures/stockdb/minute_sh600519_20260805.json` (冻结 live 实测体, 零网络 hermetic) | exact |
| `backend/tests/test_auction_capture.py` (新增) | test | `test_minute_backfill_idempotency.py` (canned fetch 注入 + repo_env + 契约断言) + `test_premarket_pool.py` 原子写断言 | exact |
| `backend/tests/test_auction_reconcile.py` (新增) | test | `test_minute_backfill_idempotency.py` `_RecordingFetch` (记录请求窗口) + 42-02 amount 派生断言 | exact |
| `backend/tests/test_auction_promote.py` (新增) | test | `test_auction_sync.py` (canonical 分区种子 + 幂等断言) + `test_verify_auction_backfill.py` `_seed_daily` (kline_daily 交叉验证种子) | exact |
| `backend/tests/test_auction_sidecar_ledger.py` (新增) | test | `test_premarket_monitor.py` / alert_store 测试 (告警事件断言) + 41 台账 reason 键集断言 | exact |
| `backend/tests/test_daily_pipeline_refresh.py` (扩展) | test | 自身 (fake scheduler 捕获 add_job + 闭包提取, 恒 stub run_now 零网络) | exact |
| `docs/features.md` / `docs/deploy-verification.md` (改: 一行状态) | docs | Phase 38 MN-04 惯例 (docs 一行状态同步, 与代码并行交付) | exact |

## Pattern Assignments

### 采集驱动镜像面 (SDC-01) — fetch-on-miss 一次 GET 全窗口, 绝无盘中轮询

**决策: 09:26 定时 GET 触发服务端 fetch-on-miss; 完整性校验 fail-closed; staging 独立湖。**

- **provider 扩展**: `StockDBProvider.get_ticks(symbol, trade_date) -> list[dict]` — GET `/v1/ticks/{symbol}?date=YYYYMMDD` (60/min/key), 走既有 `_get_json` 唯一请求面 (X-API-Key header-only, 禁 URL 传参; 401→StockDBAuthError / 429→Retry-After / 400→StockDBBadRequest typed 异常, 绝不吞错); 请求必带 `?date=T` (**09:15 前无 date 会拿到昨日数据** — eastmoney `_em_trading_day` 回退, Pitfall 3)。返回原始 JSON list (TickBar 10 字段), 归一化交给 capture 层 (staging 契约单点)。
- **采集机制**: 服务端 `service.tick` fetch-on-miss (kernel/service.py:488-490 源码核实) — 湖文件缺失 → 全窗口一次采集落盘; 文件存在 → 只读不刷新。→ sidecar 必须当日首个请求者, **09:26 一次 GET 即全窗口**; 重复 GET 内容一致 (轮询 = 纯浪费限频额度, [CRITICAL] 反模式)。
- **完整性校验** (`_validate_tick_window(rows, trade_date)`): 归属日==T ∧ `09:25:00` 行 num_trades>0 ∧ 窗口行数 ≥ 40 (3s 快照级 × 10min ≈ 200 理论 / 85 实测) — 任一失败 → 该 symbol fail-closed 不落分区 + reason。**「逐秒快照」验收 = 「3s 快照级逐条捕获」** (A1, 源原生粒度 TDX L1 3s 实测, 绝不伪造每秒 1 行)。
- **staging 布局**: `data/tick_staging/date={T}/part.parquet` (10 列 TickBar 全保留) + `manifest.json`; 目录名 `_DATE_RE` fullmatch 防路径穿越 (T-27-01-02, 镜像 premarket_snapshot); temp + `os.replace` 原子写; **绝不写 canonical kline_auction** (虚拟量非成交, 555..565 谓词物理排除 + 提审过滤双保险)。
- **池构成 (A2)**: `resolve_sidecar_pool()` = preferences `auction_sidecar_symbols` 配置白名单 (非空优先) → 缺省 watchlist (`tickflow.pools.get_pool("watchlist")` 读 `data/user_data/watchlist.parquet`); **硬 cap ≤200** (pool-gated, 5537 全量盘中不可行 descope); symbol 归一 suffix→prefix (`_to_prefix`), 归一失败 → failed reason (不猜)。

### 三重对账镜像面 (SDC-01 对账闭合) — 两条独立端点互证

- **对账源**: stockdb `/v1/minute` 09:30 bar (120/min; end=T+1 端日语义 — Phase 40 Pitfall 3, provider 内置) — **09:40 时点 AQ kline_minute 湖无当日分区** (15:30 EOD 才同步), 对账绝不读 AQ 湖 (Pitfall 4); EOD 复核可另以 AQ 湖 (第二独立来源, 可选)。
- **三重闭合** (全部 live 实测锚定 SH600519@2026-08-07): `price_eq` (09:25 price vs 09:30 close, 1e-6) / `vol_eq` (vol_hand 恒等, 手) / `amount_closure` (`price×vol_hand×100` vs `volume×close×100` — **仅 OHLC 全等时派生**, 实测 173×100×1308.66 = 22,639,818; 非全等 → amount UNKNOWN, 绝不猜, 42-02 规则)。腾讯分钟 `amount_yuan=None` 不直读 (Pitfall 7)。
- **失败处理**: mismatch → 当日不升 canonical + 台账 + 告警; 09:30 bar 缺失 → 300s 重试 1 次 → 仍无 → 台账 `pending` + EOD 复核 (A5 边缘)。

### 台账 JSON 惯例 (SDC-03) — W-5 终态键集 + JSONL 滚动清理

- **终态 dict 键集** (镜像 36/41 auction_backfill W-5 风格): 成功 `{job, trade_date, requested, ok, failed_symbols, started_at, finished_at}`; fail-closed 追加 `reason` (9 键); 键形恒定, 测试逐键断言。
- **存储**: `data/user_data/auction_sidecar_ledger.jsonl` — JSONL 追加 + 滚动清理 (镜像 `alert_store.py:1-41`: MAX_DAYS=7 / MAX_RECORDS=5000 / PRUNE_EVERY=20 / threading.Lock), 每 job 跑完一行; `manifest.json` (date={T} 目录内) 同日沉淀完整性/对账/提审状态。
- **告警接线**: `alert_store.append(data_dir, event)` → `data/user_data/alerts.jsonl` + `/api/alerts` 既有查询面 (可选 `webhook_adapter` WeCom)。事件: `auction_sidecar_capture_missing` (交易日确认 ∧ 采集缺失/不完整) / `auction_sidecar_reconcile_fail` (对账 mismatch)。**非交易日 → 无告警** + 台账 `skipped_no_data` (假日不告警风暴)。

### 交易日判定 (SDC-03) — 数据在场, 无日历服务缺口下的诚实方案

- AQ 无交易日历 (market_time.py 仅周末注释; stockdb trading_calendar 无 HTTP 端点); 调度 = `CronTrigger(day_of_week="mon-fri")` 既有模式。
- **交易日确认 = 数据在场** (分钟 09:30 bar 存在 ⇒ 交易日; 与对账同一确认点); stockdb `trading_days.json` (host 文件, 无端点) 仅作可选日历 oracle, DEP-01 连通性前置相关, **本阶段不依赖** (A5)。
- 假日 (mon-fri 但非交易日): 采集 GET 返回非当日数据 → 归属日校验拒绝 → 无分区; 09:40 无 09:30 bar → skipped_no_data 无告警 — 自然诚实。

### 调度注册镜像面 (SDC-03) — CronTrigger + _run_tracked 单飞

- 三 job (daily_pipeline.py:1140-1174 注册模式): `auction_sidecar_capture` 09:26 / `auction_sidecar_reconcile` 09:40 (内部 09:45 重试 1 次) / `auction_sidecar_promote` EOD 15:40 — 全 `CronTrigger(day_of_week="mon-fri", timezone="Asia/Shanghai")` + `lambda: _run_tracked(fn, job_label)` + `replace_existing=True`; capture/reconcile `misfire_grace_time=1800` (盘前窗口窄, 镜像 `_PREMARKET_JOB_ID` 09:26 job :1140-1174)。
- 09:26 与盘前预览 job 同槽位不同 id (APScheduler 多 job 并发, 互不冲突); job 函数形态 = `fn(on_progress=None) -> dict` (镜像 `_premarket_pool_preview` :1016-1080: `_get_app_state()` → repo → 终态 dict; 无 app state → 诚实 skip)。
- 提审闸门 = staging manifest `completeness.ok ∧ reconciliation.closed` — **不用** `resolve_auction_probe().status == available` (probe 枚举 xyz 源, tick 源不在枚举 → 恒不过 → 静默 0 写, Pitfall 6); 既有 probe/写湖测试零改动绿。

### canonical 写面复用 (SDC-02) — write_auction_partitions 直接调用

- `write_auction_partitions(df, repo)` (auction_sync.py:36-93): 555..565 窗口谓词 (09:30+ 连续竞价 bar 结构性排除) + canonical 裁剪 (4 必需 + 2 可选, 存在性 crop — **unmatched_volume 缺失天然缺列**) + merge-upsert (`unique(subset=["symbol","datetime"], keep="last")` 幂等) + .tmp 原子写。**probe 闸门在 `sync_and_persist_auction` 不在写函数内** — promote 直调写函数, 闸门自定 (staging 判定)。
- 单位映射锁死: `auction_volume = vol_hand×100` (股, data.py:772「单位: 股」逐字) / `auction_amount = price×vol_hand×100` (元, 实测闭合 22,639,818) / `auction_virtual_price = price` (xyz `current` 同语义, xyz_provider.py:247); `num_trades` 只进 staging 元数据/manifest (canonical 无此列)。
- 仅撮合行升湖: 过滤 `time∈09:25:00..09:25:59 ∧ num_trades>0` → sort(time) → `unique(subset=["symbol"], keep="first")` (09:25:00 撮合行; 同值 09:25:04 重复行 dedupe → **单 symbol 单日单行**, canonical 一 symbol 一撮合行不变量, xyz 路径同语义); 虚拟快照行 (09:15-09:24, num_trades=0) + 09:25:01 回显行永不入湖。
- symbol 形态: staging 保留前缀形态 (`SH600519` 服务端原样) → promote 转后缀 (`_to_suffix`) 写 canonical (湖内 600519.SH 形态); datetime = `trade_date.date() + "09:25:00"` naive (北京墙钟, Phase 40 归一化契约), cast Datetime("us")。

### 夹具扩展面 — 冻结 live 实测体 (零网络 hermetic)

- `tests/fixtures/ticks/sh600519_20260807_window.json`: 冻结 2026-08-07 SH600519 竞价窗口 85 行 (09:15:07 起 3s 快照级, 全 num_trades=0) + 09:25:00 撮合行 (1308.66/173手/120笔) + 09:25:01 回显行 (num_trades=0) + 09:25:04 重复撮合行 (同值) + 09:30:00 首根连续竞价行 (num_trades=19) — 采集/校验/对账/提审四组消费同一冻结体。
- 测试注入: `_FakeTickProvider` 实现 `get_ticks(symbol, date)` 从夹具返回子集/空/昨日归属日/窗口截断 (镜像 42 `_RecordingFetch`); reconcile 用 `_RecordingMinuteFetch` 断言请求窗口 `end=T+1`; promote 用 `_seed_staging` 直接写 staging parquet (镜像 `_write_auction_partition` :64-70)。
- 回归锁: `test_auction_sync.py` (555..565 / test_0930_excluded) / `test_auction_columns.py` (DATA-06 缺列语义) / `test_auction_probe.py` (probe 枚举零改动) / `test_daily_pipeline_refresh.py` (既有 job 断言零回归) — **全绿保持**。

## 命名与测试惯例

- **job id 常量**: `_SIDECAR_CAPTURE_JOB_ID = "auction_sidecar_capture"` / `_SIDECAR_RECONCILE_JOB_ID = "auction_sidecar_reconcile"` / `_SIDECAR_PROMOTE_JOB_ID = "auction_sidecar_promote"` (镜像 `_PREMARKET_JOB_ID` 常量纪律); 时点常量 `_SIDECAR_CAPTURE_HOUR/_MINUTE = (9, 26)` 等。
- **alert rule_id**: `"auction_sidecar_capture_missing"` / `"auction_sidecar_reconcile_fail"` (逐字可断言)。
- **ledger 键集**: `{job, trade_date, requested, ok, failed_symbols, reason?, started_at, finished_at}` (W-5 风格; fail-closed 追加 reason, 9 键)。
- **manifest 键集**: `{trade_date, captured_at, pool_size, symbols_ok, symbols_failed, completeness, reconciliation, promoted, promoted_at}`。
- **容差常量**: `_PRICE_TOL = 1e-6` (镜像 verify_auction_backfill [4] 既有 1e-6 断言); `_WINDOW_MIN_ROWS = 40` (3s×10min 理论 ≈200 / 实测 85 的保守阈值); `_POOL_CAP = 200` (A2 pool-gated)。
- **测试惯例**: 生产 import 放测试函数内 (模块收集期不 import DuckDB 单例); `repo_env(tmp_path, monkeypatch)` fixture (monkeypatch settings.data_dir); 断言用行数/文件存在/键集而非实现细节; 每 task 提交级 verify 命令可运行 (<60s, canned 零网络)。

## 关键差异点 (43 后 vs 现状反模式)

| 维度 | Phase 43 后 | 现状 (反模式) |
|---|---|---|
| 盘中竞价采集 | 09:26 单次 GET 触发 fetch-on-miss 全窗口 + 完整性校验 | (无 — 无盘中采集基础设施; collect_loop tick=0s 禁用) |
| 逐秒快照验收 | 3s 快照级逐条捕获 (窗口行数 ≥ 40, 源原生粒度如实) | 需求文本「逐秒」硬验收 (源不可达, A1) |
| 采集覆盖 | 池 ≤200 pool-gated (配置白名单默认自选池) | 5537 全量盘中 (60/min ÷ 5537 = 92min/轮, 不可行, A2) |
| 竞价数据面 | tick 3s 全窗口 + 09:25 撮合行 + num_trades 元数据 → staging 逐日累积 | 仅 xyz 09:25 撮合行 (配额窗约束, 无虚拟窗口数据) |
| 对账 | tick 09:25 vs 分钟 09:30 bar 三重闭合 (22,639,818 实测锚定) | (无 — 无 live 对账面) |
| 诚实门 | fail-closed 无分区 + 台账 JSONL + 告警 (09:26 后缺失可告, 交易日数据在场判定) | (无 — 盘中面无观测) |
