# Architecture Research

**Domain:** A股量化研究平台 v2.0 — 历史股池导航 + 竞价策略族扩展 + 真集合竞价数据列
**Researched:** 2026-08-04
**Confidence:** HIGH（既有组件集成路径全部源码核实）/ MEDIUM（真竞价数据源可用性为 probe 门控，未知）

## 标准架构（现有 + v2.0 增量）

### 系统总览

v2.0 的三个特性线程都挂接在既有分层上，不引入新的数据存储或第三方注册轨道。
下面用 `[NEW]` 标注新建组件、`[MOD]` 标注修改组件、`(无标注)` 标注既有组件。

```
┌────────────────────────────── 前端交互层 ───────────────────────────────┐
│  PoolHubPage.tsx [MOD]                                                  │
│    ├─ DateNavigator [NEW]        ← 交易日前后翻页 + 日期列表             │
│    ├─ StrategyCardGrid.tsx [MOD] ← 卡片总数跟随 as_of                   │
│    └─ StockListTable.tsx [MOD]   ← 竞价列(probe=available 时 VIP 可见)   │
├────────────────────────────── API 层 ──────────────────────────────────┤
│  api/pool.py [MOD]                                                      │
│    ├─ GET /api/pool/hub?as_of=YYYY-MM-DD  [MOD] 真实多日期投影          │
│    └─ GET /api/pool/dates                [NEW] 可用股池日期列表          │
│  api/screener.py [MOD]  run_all 写入日期分区缓存                         │
│  api/data.py        (auction-probe 端点不变, 判定语义复用)               │
├────────────────────────────── 服务层 ──────────────────────────────────┤
│  services/pool_hub.py [MOD]     按日期读缓存, 单日期投影不变             │
│  services/strategy_cache.py[MOD] 最新指针 + 日期分区文件                 │
│  services/pool_history.py [NEW] 日期列表 / 回填调度                      │
│  services/auction_probe.py [MOD] 判定下沉到 pipeline/策略可读            │
│  services/auction_sync.py [NEW] 拉取竞价匹配 → kline_auction 湖          │
├────────────────────────────── 策略/指标层 ──────────────────────────────┤
│  strategy/engine.py [MOD]  requires_auction_data 元数据 + 空安全         │
│  strategy/builtin/ [MOD] +5 文件: 竞价阿尔法/极速抢筹/T+1闪电/           │
│                              竞价全面策略/金色两点半  (STRAT-04)         │
│  strategy/factor_hits.py (无标注)  逐日期聚合, 天然按 as_of 工作          │
│  indicators/pipeline.py [MOD]  probe 门控的 auction_* 受管列             │
├────────────────────────────── 数据底座层 ──────────────────────────────┤
│  data/kline_auction/date={d}/part.parquet  [NEW] 竞价匹配数据湖          │
│  data/kline_daily_enriched/date={d}/part.parquet (无标注) 已有日期分区    │
│  data/user_data/strategy_cache/{as_of}.json [NEW] 逐日股池缓存           │
│  data/user_data/strategy_cache.json (无标注) 最新 as_of 指针(兼容)       │
└─────────────────────────────────────────────────────────────────────────┘
```

**三条数据主链（v2.0）：**

```
[A] 真竞价列: provider.get_auction → auction_sync → kline_auction 湖
        → indicators.pipeline 按 (symbol,date) 窗口聚合 → enriched 受管列
        → 竞价策略 filter（probe 不可用 → 列缺席, 策略空安全退化 open_gap）

[B] 历史股池: run_all(as_of) → strategy_cache/{as_of}.json
        → pool_hub 按日期投影 → GET /api/pool/hub?as_of → DateNavigator

[C] 新策略族: strategy/builtin/*.py 自动发现 → engine.run_all
        → build_factor_hits 逐日期聚合 → hit_factors/交叉共振 (无改动)
```

### 组件职责

| 组件 | 职责 | 类型 |
|-----------|----------------|--------|
| `services/auction_sync.py` | 从 provider `get_auction()` 拉取 09:15–09:25 匹配行，按 `date=YYYY-MM-DD` 分区写入 `kline_auction/`，重放既有 `kline_sync.sync_and_persist_minute` 的原子写+视图刷新模式 | NEW |
| `services/auction_probe.py` | 判定 竞价数据可用性（not_configured/available/fail_closed/error）；v2.0 把判定下沉为进程内可复用结果（不再仅 API 30s 缓存），供 pipeline 与策略消费 | MOD |
| `indicators/pipeline.py` | 新增 probe 门控的 `auction_volume/auction_amount/auction_virtual_fill` 受管列；窗口内(09:15–09:25)按 symbol 聚合成每日一行，绝不从 09:30 bar 取数 | MOD |
| `strategy/engine.py` | 支持 `META["requires_auction_data"]` 与空安全约定（列缺席→过滤器整体为假→空池），不改变加载/评分主链 | MOD |
| `strategy/builtin/auction_alpha.py` 等 5 文件 | 竞价阿尔法/极速抢筹/T+1闪电/竞价全面策略/金色两点半，均落在 builtin 目录自动发现，遵守 STRAT-03 不建第三轨道 | NEW |
| `services/strategy_cache.py` | 增加按日期分区写（`{as_of}.json`）+ 保留 `strategy_cache.json` 为最新指针；锁/原子替换语义不变 | MOD |
| `services/pool_history.py` | 枚举可用股池日期（分区缓存 ∩ enriched 日期）、触发历史回填（run_all 逐日期） | NEW |
| `services/pool_hub.py` | 按请求 as_of 读对应日期缓存；无 as_of → 最新指针（保持现契约）；可选透出竞价列 | MOD |
| `api/pool.py` | `GET /api/pool/hub` 增加真实多日期语义；新增 `GET /api/pool/dates` | MOD+NEW |
| `frontend/.../DateNavigator.tsx` | 交易日前后翻页，来源 `GET /api/pool/dates`；切换后 hub 带 as_of 重取 | NEW |

## 推荐的项目结构（v2.0 增量落点）

```
backend/app/
├── data_providers/
│   ├── custom/provider.py        # (已含) get_auction + _normalize_auction 窗口过滤
│   └── base.py                   # (已含) ProviderCapabilities.auction 能力位
├── services/
│   ├── auction_probe.py          # [MOD] 判定下沉 + 逐日期可用性
│   ├── auction_sync.py           # [NEW] 竞价匹配同步 → kline_auction 湖
│   ├── pool_history.py           # [NEW] 日期列表 / 历史回填
│   ├── strategy_cache.py         # [MOD] 日期分区缓存 + 最新指针
│   └── pool_hub.py               # [MOD] 多 as_of 投影
├── indicators/
│   └── pipeline.py               # [MOD] auction_* 受管列(probe 门控)
├── strategy/
│   ├── engine.py                 # [MOD] requires_auction_data + 空安全
│   └── builtin/
│       ├── auction_alpha.py      # [NEW] 竞价阿尔法
│       ├── fast_grab.py          # [NEW] 极速抢筹
│       ├── t1_flash.py           # [NEW] T+1闪电
│       ├── auction_allround.py   # [NEW] 竞价全面策略
│       └── golden_230.py         # [NEW] 金色两点半
├── api/
│   ├── pool.py                   # [MOD+NEW] hub 多日期 + /pool/dates
│   └── screener.py               # [MOD] run_all 写日期分区
└── jobs/
    └── daily_pipeline.py         # [MOD] sync_auction 阶段 + EOD 股池持久化 job

data/
├── kline_auction/date={YYYY-MM-DD}/part.parquet   # [NEW] 竞价匹配数据湖
└── user_data/
    ├── strategy_cache.json                        # 最新 as_of 指针(兼容)
    └── strategy_cache/{YYYY-MM-DD}.json           # [NEW] 逐日股池缓存

frontend/src/
├── pages/PoolHubPage.tsx                          # [MOD] 集成 DateNavigator
└── components/pool-hub/DateNavigator.tsx          # [NEW]
```

### 结构理由

- **竞价同步独立成 service**：与 `kline_sync` 平行，复用其 原子写/分区/视图刷新 约定；竞价是 09:15–09:25 窗口数据，与 09:30+ 分钟 K 时间语义不同，不能混入 `kline_minute`。
- **受管列进 `indicators/pipeline.py`**：`open_gap` 已示范"governed + 单元测试 + 被策略消费"的路径，竞价列走同一受管注册表（`ENRICHED_COLUMNS`/`ENRICHED_STORAGE_COLS`/标签/`DENIED`），保证因子 DSL 与自定义信号一致可见。
- **逐日缓存放 `user_data/`**：股池结果是运行态快照（研究投影），不是时间序列；JSON 分区文件 + 最新指针满足"日期导航"同时不破坏现有 single-as_of 消费者（pool_hub、guest masking、monitor overlay 均只认 `strategy_cache.json`）。
- **新策略只落 builtin**：STRAT-03 硬规则延续——`StrategyEngine._load_all` 扫目录自动发现，`PRESET_STRATEGIES` 去重由 strategies API 负责，绝不新增注册表。

## 架构模式

### Pattern 1: Probe 门控的受管列（诚实标签规则）

**What:** 一个列族的可用性由服务端权威判定（`resolve_auction_probe`）决定；判定为 available 才把列物化进 enriched，否则列缺席（fail-closed）。09:30 起的连续竞价 bar 永远不产生 `auction_*` 值。

**When to use:** 数据源能力是运行期变量（用户是否配置、免费源是否稳定）且列语义有被冒充的风险（把日线开盘量当竞价量）时。

**Trade-offs:** 好处是"诚实"由数据管线和列定义双重锁定，策略不可能在无源时伪造竞价信号；代价是策略必须对缺席列做空安全（`is_not_null()` 守卫），描述文本需注明"依赖真竞价数据"。

**Example:**
```python
# indicators/pipeline.py — 窗口聚合, 永远单日单行, 绝不取 09:30 bar
if "auction_volume" in want and auction_available:
    df = df.join(
        auction_summary,                 # 按 (symbol, trade_date) 预聚合的窗口总量
        on=["symbol", "trade_date"], how="left",
    )
# 诚实标签: probe=available 才产生列; 否则该列不在 df.columns

# strategy/builtin/auction_alpha.py — 空安全消费
expr = pl.col("symbol").is_not_null()
if "auction_volume" in df.columns:
    expr &= pl.col("auction_volume").fill_null(0) >= min_vol   # 缺席→0→过滤为假
```

### Pattern 2: 最新指针 + 日期分区缓存（不破坏 single-as_of）

**What:** `strategy_cache.json` 语义保持"最新一天"不变；每次 `run_all(as_of)` 同时写 `strategy_cache/{as_of}.json`，并原子更新 `strategy_cache.json` 的 as_of/results 为该天（即最新指针）。历史浏览读分区文件，默认视图读指针。

**When to use:** 需要新增"按交易日回看"但不允许破坏既有单一数据源契约（D-01/D-02）与 monitor 实时叠加路径时。

**Trade-offs:** 文件数随交易日线性增长（JSON 每日期仅几十 KB，个人部署可忽略）；首次浏览某历史日若无缓存需触发回填（一次 run_all ≈ 单日 enriched 加载 + 21 策略过滤，秒级）。

**Example:**
```python
# services/strategy_cache.py — 新增签名(保持旧签名委托)
def write_cache(data_dir, as_of, results):
    _atomic_write(data_dir / "user_data" / "strategy_cache" / f"{as_of}.json", results)
    _atomic_write(data_dir / "user_data" / "strategy_cache.json",  # 最新指针
                  {"as_of": as_of, "results": results, "updated_at": now_ms})

def read_cache(data_dir, as_of=None):
    return _read(as_of and data_dir/"user_data"/"strategy_cache"/f"{as_of}.json"
                 or data_dir/"user_data"/"strategy_cache.json")
```

### Pattern 3: 日期分区数据湖 + 窗口内聚合入受管列

**What:** 竞价匹配原始行按 `date=` 分区存湖（镜像 `kline_minute`），进入 enriched 前先按 (symbol, trade_date) 聚合为每日一行，保持 enriched 日线框架基数 1 行/股/日不变。

**When to use:** 原始数据是 09:15–09:25 内多时间戳行情，而消费端（日线策略/股池行）需要"当日竞价总量/金额/虚拟成交"单一数值时。

**Trade-offs:** 聚合会丢失窗口内时序（盘中回放除外，v2.0 不做）；换取零 join 放大、与现有日线 enriched 完全兼容。

## 数据流

### 请求流 A：历史股池浏览

```
用户点 DateNavigator ← /api/pool/dates (已缓存日期列表)
    ↓ 选 as_of
GET /api/pool/hub?as_of=YYYY-MM-DD&concept=
    ↓
pool_hub.build_pool_hub(data_dir, as_of)
    ↓ 读 strategy_cache/{as_of}.json (缺 → 触发 pool_history.backfill 或返回空标记)
project 五列 + hit_factors + cross_resonance + 概念筛选
    ↓
guest masking (as_of 历史视图也走 GUEST-01: 游客仅涨跌幅+概念)
    ↓
PoolHubPage: 卡片计数与明细同源(D-02), 永不漂移
```

### 请求流 B：真竞价列 → 策略 → 股池

```
daily_pipeline: sync_auction (probe=available 时)
    → kline_auction/date={d}/part.parquet
    → indicators.pipeline: 窗口聚合 → auction_* 受管列 (available 才物化)
    → engine.run_all(as_of): 竞价策略 filter 消费 (空安全)
    → run_all 结果写 strategy_cache/{as_of}.json
    → build_factor_hits 逐日期聚合 → 股池行可选透出 auction_volume/amount
```

### 状态管理

```
策略结果: run_all(API/定时) → strategy_cache/{as_of}.json(持久) ← read 仅读
最新视图: strategy_cache.json(指针) + monitor 引擎内存叠加(仅当日, 不落盘)
竞价判定: auction_probe 30s TTL 缓存 + 每日期可用性(进程内)
竞价原始: kline_auction parquet 湖 (不可变, 重拉按日期分区替换)
```

## 缩放考量

| 规模 | 架构调整 |
|-------|--------------------------|
| 个人/单容器（现状） | 逐日 JSON 缓存 + 按需回填足够；回填默认限制最近 N 个交易日 |
| 1k-10k 用户 | `strategy_cache/` 改 parquet/duckdb 分区查询；历史回填改后台 job 而非请求内同步 |
| 10k+ 用户 | 竞价同步与日线同步解耦独立调度；缓存移到对象存储 |

### 缩放优先序

1. **首个瓶颈：历史回填的同步阻塞**。首请求某历史日无缓存时，在请求内跑 run_all 会卡住页面。修复：预生成 EOD 持久化 job（每个交易日盘后自动 `run_all(当日)` 落日期缓存），首日一次性后台回填，请求只读缓存。
2. **次个瓶颈：日期列表扫描**。`/api/pool/dates` 若每次 `glob` 全目录，随日期增长变慢。修复：缓存已排序日期列表，仅在新写后失效。

## 反模式

### 反模式 1：把 09:30 连续竞价 bar 标记为"竞价量"

**What people do:** 无真竞价数据时，用分钟 K 09:30 或日线开盘量近似竞价量/竞价金额。
**Why it's wrong:** 违反诚实标签规则（T-16-01），策略与 UI 会对用户撒谎，审计失效。
**Do this instead:** probe 判 unavailable 时列缺席 + fail-closed 到 `open_gap`；策略描述写明"派生开盘涨幅"。窗口过滤（`_mins 555..565`）是摄取层的硬闸。

### 反模式 2：在 run_all 内对历史日期做"就地重算最新"

**What people do:** 用户浏览历史日期时直接改 `strategy_cache.json` 的 as_of，导致单一数据源漂移。
**Why it's wrong:** 破坏 D-02（卡片与明细同源）与 monitor 实时叠加；并发写丢更新。
**Do this instead:** 日期分区文件 + 最新指针分离；历史请求永不写指针文件。

### 反模式 3：第三策略注册轨道

**What people do:** 为 5 个新竞价策略另建 registry/config 清单。
**Why it's wrong:** 与 `PRESET_STRATEGIES` + `builtin/*.py` 并存造成漂移（STRAT-03 / 既往 PITFALL #5）。
**Do this instead:** 全部落 `strategy/builtin/`，自动发现；strategies API 去重。

### 反模式 4：客户端推导 as_of 或竞价款

**What people do:** 前端从行值推断日期、或在历史视图自行叠加今日 monitor 结果。
**Why it's wrong:** as_of 一致性是服务端职责（GUEST-01 同源精神）；历史视图叠加实时结果会污染回看。
**Do this instead:** 服务端回显 `resolved_as_of`；monitor 叠加只作用于无 as_of 的默认视图。

## 集成点

### 外部服务

| 服务 | 集成模式 | 备注 |
|---------|---------------------|-------|
| 自定义 HTTP 数据源 `auction` 数据集 | `CustomSourceProvider.get_auction()` → 窗口过滤 → `kline_auction` 湖 | 沿用 `DatasetName` 白名单；无 auction 数据集时 probe=not_configured |
| 内置 provider（TickFlow 等） | `ProviderCapabilities.auction=True` 能力位进入 `_default_sources()` | 现状已支持能力枚举；仅缺实际竞价端点实现 |

### 内部边界

| 边界 | 通信 | 备注 |
|----------|---------------|-----------|
| auction_probe ↔ pipeline | 进程内判定（`auction_available_for(date)`） | 不可在请求内重探测（30s TTL 缓存语义保持） |
| pipeline ↔ strategy engine | enriched 列契约（`auction_*` 出席/缺席） | 缺席必须被 `is_not_null()` 守卫兜住 |
| run_all ↔ strategy_cache | 分区写 + 指针更新（同一锁） | 与 monitor 叠加路径隔离 |
| pool_hub ↔ guest_masking | DTO 边界脱敏 | 历史视图同样脱敏；竞价列仅 VIP 可见（对齐开盘涨幅） |
| pool_hub ↔ pool_history | 缓存缺失 → 回填信号 | 默认 EOD 预生成，请求不阻塞 |

## 建议的构建顺序（数据 → 策略 → 股池 → 前端）

1. **数据层** — `sync_auction` 阶段 + `kline_auction` 湖 + `auction_*` probe 门控受管列（DATA-04）；pre-open 可用性管线（DATA-05）。依赖：既有 `auction_probe`、`indicators.pipeline`、`custom/provider.get_auction`。
   - 交付可验证点：`enriched.parquet` 在 probe=available 时含 `auction_volume/auction_amount`，unavailable 时列缺席；单元测试断言 09:30 bar 永不产生竞价值。
2. **策略层** — 5 个 builtin 竞价策略（STRAT-04）+ `requires_auction_data` 空安全 + 分钟 K 确认（STRAT-05，复用 `filter_history` + monitor 叠加路径）。依赖：数据层竞价列。
   - 交付可验证点：新策略自动出现于 strategies API；无竞价列时策略诚实返回空池/退化，不 500。
3. **股池层** — `strategy_cache` 日期分区 + `pool_history` + `GET /api/pool/dates` + `GET /api/pool/hub?as_of` 真实多日期（POOL-04）。依赖：策略层 run_all 可逐日期产出。
   - 交付可验证点：默认视图行为与 v1.3 完全一致；历史日返回该日权威 as_of 与逐日 hit_factors/交叉共振。
4. **前端层** — `DateNavigator` 翻页 + 卡片/明细随 as_of 重取 + 竞价列（probe=available 且 VIP 时显示）。依赖：股池层 API。
   - 交付可验证点：375px 与桌面日期切换视觉回归；guest 模式历史视图仍只显 涨跌幅+概念。

**Phase 顺序理由：** 竞价列是策略筛选的前提（数据→策略）；逐日缓存是历史浏览的前提（策略→股池）；日期导航是纯展示层消费（股池→前端）。EOD 股池持久化 job 在股池层落地，保证日期导航自给自足、无需用户手动逐日 run_all。

## 来源

- 源码核实（HIGH）：`backend/app/services/auction_probe.py`、`strategy/engine.py`（`_load_all`/`run_all`）、`strategy/factor_hits.py`、`strategy/builtin/auction_*.py`、`services/strategy_cache.py`、`services/pool_hub.py`、`api/pool.py`、`api/screener.py`（run_all 附 hit_factors 写缓存）、`api/data.py`（auction-probe 30s TTL）、`indicators/pipeline.py`（`ENRICHED_STORAGE_COLS`/`open_gap` 受管列）、`data_providers/custom/provider.py`（`get_auction` 窗口过滤）、`data_providers/custom/config.py`（`DatasetName` 含 auction）、`jobs/daily_pipeline.py`（调度结构，无 EOD 策略持久化 job）、`frontend/src/pages/PoolHubPage.tsx`、`components/pool-hub/*`、`lib/api.ts`（`PoolHubResponse`）
- 规划文档（HIGH）：`.planning/REQUIREMENTS.md`（DATA-04/05、STRAT-04/05、POOL-04）、`.planning/ROADMAP.md`（v1.3 Phase 16–19 结构）、`.planning/PROJECT.md`（架构约束：数据湖优先、独立模块、零执行权）、`.planning/research/v1.3-auction/PITFALLS.md`
- 可信度说明（MEDIUM）：真竞价数据源的"虚拟成交（virtual fill）"字段语义依赖具体上游，物化前需在数据层阶段以 probe 实测确认；列定义以"窗口内已观测时间戳"为准，不做来源推测。

---
*Architecture research for: AthenaQuant v2.0 竞价深度与历史股池*
*Researched: 2026-08-04*
