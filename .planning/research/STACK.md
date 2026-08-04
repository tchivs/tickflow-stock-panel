# Stack Research — AthenaQuant v2.0 竞价深度与历史股池

**Domain:** A-share 集合竞价选股引擎深化 — 按交易日浏览历史股池 (POOL-04)、补充 5 个竞价策略 (STRAT-04/05)、真集合竞价数据列 (DATA-04/05, probe-gated)
**Researched:** 2026-08-04
**Confidence:** HIGH (技术选型, 仓库内已验证 + Context7 佐证); DATA-04 数据源可用性本身为 MEDIUM (取决于探测结果)

## 核心结论 (Executive Position)

v2.0 的三个特性**全部复用 v1.3 已锁定栈, 新增运行时依赖为零**。Polars 1.40.1 + DuckDB 1.5.3 + Parquet/pyarrow 24.0.0 + SQLite + FastAPI 0.136.1 + React Query 5.55 已经包含实现这三件事所需的每一种原语:

1. **POOL-04 (历史股池导航)** 的真正缺口不是缺库, 而是缺"按日持久化"。`strategy_cache.py` 只保留**单一 as_of** —— 每次 `write_cache` 用 read-merge-write 覆盖 `results`/`as_of`, 历史被丢弃; 而 `screener_results/` 目录在数据湖布局里**只存在为空占位目录** (由 `KlineRepository`/DataStore 创建, 全仓无写入方)。因此"按交易日浏览历史股池"需要一个**新的持久化 seam**: 把每日 `run_all` 结果写成按 `date=` 分区的 Parquet 湖表, 用 Polars `scan_parquet(hive_partitioning=True)` 读单日、用 DuckDB 冷 SQL 做日期索引。
2. **STRAT-04/05 (更多竞价策略)** 是纯增量: 5 个新策略 = 5 个 `strategy/builtin/*.py` 文件, 由 `StrategyEngine` 自动发现, 复用 `open_gap` / `change_pct` / `vol_ratio_5d` 等受管列。唯一契约是**探针门控**——引用竞价匹配列的策略必须写 fail-closed (探针非 `available` 时退化为派生因子), 这与 `auction_early_star.py` 处理可选概念列的模式一致。
3. **DATA-04/05 (真集合竞价数据列)** 的 provider 契约已经存在: `ProviderCapabilities.auction` 能力位 (base.py)、自定义源的 `get_auction()` 已返回 canonical 列 `symbol, datetime, auction_volume, auction_amount` 且严格限定 09:15–09:25 窗口 (custom/provider.py `_normalize_auction`)、探针判定 `not_configured/available/fail_closed/error` (auction_probe.py) 与 30s TTL 的 `/api/data/auction-probe`。缺的是**湖内持久化** (`kline_auction/` 分区) 与**读路径门控** (可用才把竞价列作为一级列暴露)。"虚拟成交" 是派生量 (指示性匹配价 = auction_amount/auction_volume), 无需新数据源。

> **选型判断: "Use X because Y"** —— 历史股池用 **Parquet 湖表 + DuckDB 冷索引**, 因为这是平台自 v1.0 锁定的 "data lake first" 架构约束、`screener_results/` 占位目录早已预留、且 Polars/DuckDB 对 hive 分区的剪枝读取 (Context7 已验证) 正好匹配"按日浏览"。**不要** 用一坨 `strategy_cache_YYYY-MM-DD.json` 文件家族, 也不要给 SQLite 塞研究投影行。

## Recommended Stack

### Core Technologies

| Technology | Version (locked) | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Polars** | 1.40.1 | 历史股池单日投影读取、策略引擎帧、竞价列入 enriched 面板 | `pl.scan_parquet(<dir>, hive_partitioning=True)` 传目录自动开 hive 分区推断, `filter(pl.col("date")==d)` 谓词下推只读目标分区 (Context7 验证); 策略热路径保持 Polars 单语言 (延续 v1.2 决策: 因子/选股评估不迁 DuckDB SQL)。 |
| **DuckDB** | 1.5.3 | `screener_results/` / `kline_auction/` 的冷查询日期索引 | `read_parquet('dir/**/*.parquet', hive_partitioning=true)` 让分区列成为可查询列, `SELECT DISTINCT date, ...` 列可用交易日 + 每日每策略计数, 免全量加载 (Context7 验证); 与 `KlineRepository` 既有的 "DuckDB 冷 → Polars 温 → 内存热" 分层完全一致。 |
| **FastAPI** | 0.136.1 | 扩展 `GET /api/pool/hub?as_of=` 语义; 新增 `GET /api/pool/dates` | 可选 query param 用 `= None` / `Query(default=None)`, 结构化校验用 Pydantic query-param model (Context7 验证); 现有 `Optional[str] as_of` 模式 (pool.py) 已达标, 无需新依赖。 |
| **SQLite (operational.db)** | — (stdlib) | 竞价可用性的**按日门控标记**与历史簿记 (仅操作状态, 不存研究行) | 平台既定的 "SQLite 存操作状态 / 湖存研究数据" 分工; 探针判定是服务端权威, 落到 SQLite 做 per-date 缓存避免每面板重复探测。 |
| **Parquet (pyarrow)** | 24.0.0 | `screener_results/` + `kline_auction/` 两个新湖表, 按 `date=` hive 分区 | 湖内唯一受管列存格式; 追加式按日写 (temp + `os.replace` 原子替换, 延续 `kline_sync._atomic_write_parquet` 模式) 契合平台 append-only 审计哲学。 |
| **React + TanStack Query** | react 18.3.1 / @tanstack/react-query 5.55.0 | 前端日期导航 (‹ › 步进 + 日期列表), as_of 重取 | `PoolHubPage` 已按 `data.as_of` 做 `key` 重渲染; 日期状态 + `as_of` query param 即接入现有 `useQuery` 缓存, 零新库。 |

### Supporting Libraries

| Library | Version (locked) | Purpose | When to Use |
|---------|---------|---------|-------------|
| **apscheduler** | 3.11.2 | STRAT-05 盘中确认 (09:30–10:00 用分钟 K 复评) 的调度 | 仅当 STRAT-05 纳入本期; 已有 `daily_pipeline` 阶段编排, 只加一个 stage。 |
| **sse-starlette** | 3.4.4 | 刷新后的股池/探针判定推送 | 已有 SSE 端点 (walkforward_sse/research_panels); 池页若做实时刷新才需要。 |
| **exchange-calendars** | 4.13.2 | 交易日历 (仅 forecast extra 内) | **默认不用** —— 日期列表以湖分区为准 (有 `run_all` 持久化才叫"有股池")。仅当 UI 需要在跨节假日 step 时推算 prev/next 交易日才把它从 `forecast` extra 提升。 |
| **pydantic** | 2.13.4 | 新端点 query-param model / DTO 校验 | `/api/pool/dates` 返回体、`as_of` 日期格式校验。 |
| **Playwright** | 1.61.1 (dev) | 日期导航 + 竞价列的 e2e 视觉回归 | 延续 pool-hub.spec.ts 的截图断言模式。 |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | 依赖锁定 | v2.0 基线**无新依赖**; 若提升 exchange-calendars 用 `uv add` 并 `uv lock --check` |
| pytest | RED-contract: 池历史写/读、日期索引、竞价列门控 | 仿 `test_pool_hub.py` / `test_auction_probe.py` 的 AST 守卫 + 冻结 fixture 模式 |
| ruff / mypy | 既有 lint/类型 | 延续 pyproject 现有配置 |

## Installation

```bash
# v2.0 基线: 无新增运行时包 —— 现有 uv.lock 已满足 POOL-04 / STRAT-04 / DATA-04。
# 唯一可能的新增 (默认不需要):
# 仅当日期导航要跨节假日推算 prev/next 交易日 (默认从湖分区派生日期, 不推日历):
uv add "exchange-calendars==4.13.2"
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **Parquet 湖表 `screener_results/date=*/` (选型)** | 一坨 `strategy_cache_YYYY-MM-DD.json` 文件家族 | JSON 每日期一个文件会无界膨胀、不可 SQL 查询、与湖的受管格式重复; 仅当历史深度 ≤ 数天且无跨日聚合需求时才可接受 —— 不符合 POOL-04 "浏览历史交易日"。 |
| **独立湖表 (选型)** | 在 `strategy_cache.json` 里塞历史 dict | 单文件 JSON 每次 hub 加载都整读, 今日热缓存与历史冷数据耦合; 独立湖表保持 `strategy_cache.json` 小、单 as_of 契约 (D-02) 不变。 |
| **湖表存研究行 (选型)** | SQLite 存池成员/计数 | SQLite 是操作状态 (位置/规则/通知), 研究投影属湖 —— 平台架构约束 "data lake first"; SQLite 只做门控标记/簿记。 |
| **Polars 读单日 + DuckDB 做日期索引 (选型)** | DuckDB 一统读写 | 策略热路径 (引擎帧、竞价列 enrich) 必须留在 Polars 单语言; DuckDB 只做冷 SQL 日期索引 —— 两者都已存在, 各司其职。 |
| **湖分区派生日期 (选型)** | 交易日历库 (`exchange-calendars`) 推 prev/next | 有 `run_all` 持久化才算"有股池" —— 日历说交易日但湖里没数据是空视图; 日历只在跨节假日 UX 步进时需要, 且该库已在 `forecast` extra 内, 提升成本一行。 |
| **服务端权威门控 (选型)** | 前端按探针/列自行决定 | GUEST-01 已锁定脱敏服务端权威; 竞价列可用性同样必须服务端判定 (probe verdict + per-date 门控), 前端只渲染。 |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **新数据库** (Postgres/Redis/MongoDB) | 自 v1.0 的单容器无外部库/队列约束; 湖 + SQLite 已覆盖 | Parquet/DuckDB/Polars + SQLite operational.db |
| **akshare/tushare 等整包 SDK 作为运行时依赖** | provider 链抽象 + 自定义源 `get_auction()` seam 已是竞价数据集成点; 整包 SDK 重复链、引入脆弱性 | 现有 `data_providers/chain.py` + `custom/provider.py` 的 auction 数据集 |
| **Arrow/Feather IPC 存历史** | IPC 是进程间暂态格式, 非湖内受管列存 | Parquet (hive 分区) |
| **前端交易日历库** (date-fns/chinese-calendar) | 日期列表由后端从湖分区权威给出; 前端不该自算交易日 | `GET /api/pool/dates` + 现有组件 |
| **日期选择器组件库** | 原生 `<input type="date">` 或 ‹ › 步进 + 后端日期列表足够 | 既有 Tailwind 组件 |
| **第三个策略注册轨** | STRAT-03 已锁定: 只进 `strategy/builtin/`, `PRESET_STRATEGIES` 去重 | `StrategyEngine` 自动发现 |
| **ML/forecast 栈进入池路径** (torch/langgraph 等) | 竞价策略是确定性因子过滤; 池路径零 AI 执行权 (POOL-03) | Polars 表达式 + 既有引擎 |
| **ORM (SQLAlchemy) 管 operational.db** | 既有版本化迁移 (`operational/migrations.py`) + 原生 sqlite 足够 | 延续现有迁移 tuple 模式 |
| **把 09:30 连续竞价 bar 当竞价量** | T-16-01 / DATA-03 已锁定: 严格窗口分类, 永不误标 | `auction_probe._has_in_window_rows` + 09:15–09:25 canonical 列 |

## Stack Patterns by Variant

**若探针判定 = `available` (DATA-04 落地):**
- 把 `kline_auction/date=*/` 的 `auction_volume` / `auction_amount` 作为一级列 join 进策略引擎的 enriched 帧, 派生 虚拟成交 (指示性匹配价 = amount/volume)。
- 因为 provider canonical 列已就绪 (`custom/provider.py`), 剩下的只是持久化 + 读路径门控。

**若探针判定 = `not_configured` / `fail_closed` / `error` (默认现状):**
- 竞价列一律不暴露, 策略 fail-closed 到派生 `open_gap`; 09:30 bar 永不标"竞价量"。
- 因为数据源可用性是本里程碑最大不确定项 (v1.3 研究 MEDIUM), 策略与 UI 必须以此为前提设计。

**若 STRAT-05 盘中确认纳入:**
- 复用 `kline_minute` + `apscheduler` 加一个 09:30–10:00 stage 做复评; 不加新库。
- 因为分钟 K 同步 (`sync_and_persist_minute`) 与调度编排均已存在。

**若历史池深度增长到数百交易日:**
- DuckDB 冷索引 `SELECT DISTINCT date ...` + Polars 分区剪枝保持单日读取 O(当日行), 与湖规模无关。
- 因为 hive 分区剪枝把读压到目标分区 (Context7 验证)。

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| polars 1.40.1 | Python >=3.10, pyarrow >=24 | `scan_parquet` 传**单个目录**时自动启用 hive_partitioning; `try_parse_hive_dates` 把 `date=` 分区值解析为 date 类型 (Context7 验证) |
| duckdb 1.5.3 | Python >=3.10 | `read_parquet` glob + `hive_partitioning=true`; 分区列即查询列 |
| fastapi 0.136.1 | pydantic 2.13.4 | 可选 query param `= None`; Pydantic query-param model 做结构化校验 |
| exchange-calendars 4.13.2 | Python >=3.11 | 当前仅 `forecast` extra; 提升到 base 需确认与 numpy 2.4.6 兼容 (未锁定期不引入) |
| pyarrow 24.0.0 | polars 1.40.1, duckdb 1.5.3 | 湖内 parquet 读写的底层 |
| @tanstack/react-query 5.55.0 | react 18.3.1, vite 5.4.3 | 日期导航复用现有 useQuery 缓存; 无新前端依赖 |

## Sources

- [Context7: Polars Python API (docs.pola.rs)] — `scan_parquet` `hive_partitioning`/`try_parse_hive_dates`/谓词与投影下推; 单目录自动开分区推断 — MEDIUM (已缓存 digest 6f3c420a…)
- [Context7: DuckDB docs (duckdb/duckdb-web)] — `read_parquet` glob/多文件/hive_partitioning 分区剪枝、`SELECT DISTINCT date` 冷索引 — MEDIUM (已缓存 digest a33c03ab…)
- [Context7: FastAPI docs (fastapi.tiangolo.com)] — 可选 query param (`= None`)、Pydantic query-param model — MEDIUM (已缓存 digest 826bb15b…)
- [backend/uv.lock (2026-08-04 现状)] — locked: polars 1.40.1, duckdb 1.5.3, fastapi 0.136.1, pydantic 2.13.4, pyarrow 24.0.0, apscheduler 3.11.2, sse-starlette 3.4.4, exchange-calendars 4.13.2 (forecast extra), Python floor >=3.11 — HIGH (仓库内验证)
- [backend/app/services/strategy_cache.py] — 单一 as_of 覆盖写、`screener_results/` 形状即 results 形状 — HIGH (仓库内验证)
- [backend/app/services/pool_hub.py, app/api/pool.py] — 单 as_of 投影契约 D-02、`as_of` query param — HIGH (仓库内验证)
- [backend/app/data_providers/base.py, custom/provider.py, chain.py, app/services/auction_probe.py] — `auction` 能力位、`get_auction()` canonical 列 (symbol/datetime/auction_volume/auction_amount)、09:15–09:25 窗口严格分类、探针判定状态机 — HIGH (仓库内验证)
- [backend/app/indicators/pipeline.py] — `open_gap` 受管列 (open/prev_close−1, 无 lookahead) — HIGH (仓库内验证)
- [backend/app/api/data.py, screener.py, jobs/daily_pipeline.py] — 探针端点 30s TTL、`run_all` 结果形状、APScheduler 阶段编排 — HIGH (仓库内验证)
- [frontend/src/pages/PoolHubPage.tsx, lib/api.ts, package.json] — 单 as_of 渲染 + React Query; react 18.3.1 / @tanstack/react-query 5.55.0 / vite 5.4.3 — HIGH (仓库内验证)

---
*Stack research for: AthenaQuant v2.0 竞价深度与历史股池 (POOL-04 / STRAT-04·05 / DATA-04·05)*
*Researched: 2026-08-04*
