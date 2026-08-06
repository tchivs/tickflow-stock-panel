# 功能手册

各功能模块的详细说明。配置见 [configuration.md](./configuration.md),部署见 [deployment.md](./deployment.md),策略相关见 [strategy.md](./strategy.md)。

> 首次使用建议顺序:**设置 → 凭据与能力**(重新检测) → **立即跑盘后管道**(拉日 K + 算指标) → **自选页**加标的 → **选股页**扫描 → **回测页**验证 → **监控中心**配规则。

---

## 🔍 选股引擎(Screener)

**27 个内置策略**,每个策略一个独立 Python 文件,基于 Polars 表达式向量化实现(`backend/app/strategy/builtin/`):

| 类型        | 代表策略                                                 |
| :---------- | :------------------------------------------------------- |
| 趋势 / 形态 | 趋势突破 · 均线多头 · MA 金叉 · MACD 金叉放量 · 布林突破 |
| 量价 / 涨停 | 量价齐升 · 高换手强势 · 连板股 · 断板反包 · 涨停动量     |
| 反转 / 波动 | 超跌反弹 · 超卖反转 · 新低反转 · 低波动龙头 · 回踩 MA20  |
| 竞价 / 盘前 | 竞价多头 · 盘前强势量化 · 早盘之星 · 极速抢筹 · 竞价阿尔法 · 金色两点半 · 竞价全面 · T+1闪电 · 盘中确认 |

全 A 股一次扫表,Polars 毫秒级返回。选股页点策略卡片即可扫描,结果支持导出。

**ETF 支持**:选股页顶部可切换 `股票 / ETF`。ETF 复用已算好的 `kline_etf_enriched` 技术指标,仅开放**技术类内置策略**(趋势/量价/反转/波动);依赖涨停信号的策略(连板股、断板反包)为股票专有,ETF 模式下不显示。需先在数据页开启 ETF 拉取(`pipeline_pull_etf`)并跑一次盘后管道。

扩展策略的三种方式见 [strategy.md → 扩展策略](./strategy.md#扩展策略的三种方式)。

### 🗓️ 股池日期导航

每次盘后 run_all 的结果以**冻结式点快照**落盘 `screener_results/date={as_of}/`(携带计算时刻与策略版本指纹),可经日期列表(`GET /api/pool/dates`)与按日取池(`GET /api/pool/history?as_of=`)浏览历史股池。快照由盘后 EOD job 自动预生成,无数据日显示诚实空态;概念板块默认为当前归属标注(`current_snapshot`),非当日快照归属(历史日若已有 as_of 归档则按当日快照归属,详见下文「概念板块 PIT」)。

历史缺口(有 enriched 数据但缺快照的交易日)可由运营经 `POST /api/pipeline/backfill` **一键批量回填**——后台 job 逐日重算并落快照,进度经 `/api/pipeline/jobs/{id}` 可见;`GET /api/pool/dates` 同时返回 `backfill_needed` 缺口计数与 `backfill_examples` 示例日,回填完成后缺口归零。每份快照带 **`snapshot_origin`** 来源标注(`eod`=盘后归档 / `backfill`=事后回填重算),历史视图经 `GET /api/pool/history` 透传;旧快照缺该字段按 `eod` 读,provenance 诚实不伪造。

### 🧭 概念板块 PIT（历史映射）

盘后 EOD job 将当日同花顺概念（`ext_gn_ths`）与行业（`ext_hy_ths`）快照**前向归档**到平台自有根 `data/ext_history/{gn_ths|hy_ths}/date={as_of}/part.parquet`，每分区旁带 provenance `manifest.json`（`source_url` / `fetched_at` / `captured_at` / `rows` / `schema_version` / `sha256` / `dimension_field`）。

- 历史股池视图（`GET /api/pool/history?as_of=`）概念归属按 **as_of 分区解析**：分区存在 → `as_of_snapshot`（该日存档归属，前端显示「概念按当日快照」+ 概念数据生效日期）；分区缺失 → 回退当前快照并标注 `current_snapshot` / `unavailable`（诚实，绝不伪造历史）；存量上线前 ~247 个历史日不回填，恒为当前归属标注。
- 前端股池页在明细区渲染概念归属徽标：非 `as_of_snapshot` → 「概念归属为当前快照，非该日数据」；`as_of_snapshot` → 「概念按当日快照 · 概念数据生效日期 {date}」。
- 诚实边界：归档仅前向（EOD 起），内容来自平台可见的当前 ext 快照（离线确定性），与实时 hub 的 `current_snapshot` 标注区分；概念归属单状态不混用。

### ⭐ 自选股联动（Watchlist Sync）

已登录研究员可在股池钻取明细表每行代码旁用自选星标一键加入/移出自选（在自选为实心高亮，不在为空心）；用钻取区 header 的「只看自选」开关把表格收窄到当前策略在自选清单中的行，或点「批量加自选」把当前可见行一次性加入自选。自选集合经共享 `QK.watchlist` 缓存与自选页/策略页/个股弹窗即时一致，匹配键为全后缀 `symbol` 精确匹配（无归一化/无 code 匹配）。游客会话不渲染任何自选控件、也不发起自选查询（仅服务端已脱敏的只读面）。

### 🕗 盘前预览 (Premarket Preview)

工作日上午 **09:26**（09:25 集合竞价撮合定盘后，北京时间）独立 job 经 `ScreenerService.run_all_with_hits(as_of=今日)` 生成**今日盘前预览股池**，写入独立分区 `premarket_results/date={T}/part.json` —— **绝不写** `strategy_cache.json` 最新指针，也不写 `screener_results` EOD 点快照（EOD 语义与归档日期不动）。

- 预览数据帧含补算的 `open_gap`（开盘涨幅，与盘后 EOD 同一公式），每份预览带 `window: "pre_open"`、`computed_at`、`provisional: true`（基于开盘/定盘价，**非收盘定稿**）、`degraded`（真实竞价列不可用时为 true）与 probe 判定。
- 只读端点 `GET /api/pool/premarket` 返回今日预览（缺失 → 200 `available:false` 诚实空态，非 404）；股池页「最新」视图在盘前预览存在且今日 EOD 快照未生成时展示预览池并标注「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」，15:35 EOD 后自动回退收盘池。
- **诚实边界**：真实竞价列仅在今日 probe `available` 且实时源返回今日窗口行时可用（第二档，依赖外部实时竞价源）；未配置时仅展示派生列（`degraded`），**绝不**把盘前预览标为收盘定稿、不把 09:30 bar 标为集合竞价数据；日期导航只列 EOD 快照日，盘前预览不进入归档日期。

### 🧪 竞价策略历史验证 (Auction Strategy Validation)

只读端点 `GET /api/research/auction/validation` 输出 9 个竞价/盘前策略（极速抢筹、竞价全面、T+1闪电、盘中确认、竞价阿尔法、金色两点半、竞价多头、盘前强势量化、早盘之星）在 enriched 历史窗口上的**信号质量报告**（POOL-03 零执行：GET-only，不写任何湖/缓存，不触发计算/同步/回填；报告区间不受回测 186 天 guard 限制，覆盖由 enriched 缓存边界决定，窗口超覆盖自动回夹并双字段回显 `window.requested_*/effective_*`）。

- **诚实数据门**：`data_gate: available|empty` —— `kline_auction` 湖空 → 200 `{data_gate:"empty", coverage:0}`（**绝不 404/500**），`empty_reason: no_auction_partitions|enriched_unavailable|no_dates_in_window`；`enabled` 日期 = `kline_auction` 分区 ∩ enriched 交易日；`probe` 为服务端权威状态透传（不参与历史闸门）。
- **分支标注（互斥）**：4 个真列策略（极速抢筹/竞价全面/T+1闪电/盘中确认）恒 `branch:"real"` —— 湖空时 `n_dates==0` 诚实报告，**绝不降级为派生**；竞价阿尔法按湖有无取 `real|derived`；4 个 EOD 代理（金色两点半/竞价多头/盘前强势量化/早盘之星）恒 `branch:"eod"`；`minute_confirm:"not_applied"` 显式（分钟确认层不在报告范围）。
- **前瞻口径（BT-04）**：信号日 T 以开盘价入场；`next_day_open_ret = open_{T+1}/open_T − 1`、`next_day_close_ret = close_{T+1}/open_T − 1`、`open_gap_outcome = open_{T+1}/close_T − 1`；结果日 = 全市场交易日历的下一交易日（绝不按标的行内 shift）；结果日缺行计入 `n_missing_outcomes`，统计排除，**绝不 0 填/前向填充**。
- **诚实边界**：真实竞价列验证以待 `kline_auction` 历史分区就位（当前 0 分区 —— 湖空时真列分支诚实空，不伪造真值）；本报告为纯 API 研究报告，无前端消费（D-05）。

### 📥 竞价历史回填（Auction History Backfill）

运营触发端点 `POST /api/kline/auction/backfill`，把 `kline_auction` 湖从 0 分区回填到与 `kline_daily` 对齐（竞价列是日 K 的补充面）。body：`{"symbols": ["000001.SZ", ...] | null(全量), "start"/"end": "YYYY-MM-DD" | null, "rpm": 1..60 | 30}`；立即返回 `{"status": "started"|"reused", "job_id"}`（单飞：已有同类任务在跑 → `reused`）。进度/终态/取消复用既有 `GET /api/pipeline/jobs/{id}`（轮询）与 `POST /api/pipeline/jobs/{id}/cancel`（合作式，每 symbol 检查）；与 pool backfill / EOD 重任务槽互斥（`已有数据任务在运行` 失败记录）。

- **诚实闸门（AQ-03）**：探针 `available` + 预检可达才写 —— 源不可达 → 0 写 fail-closed（`reason: "source_unavailable"`）；**只写 kline_daily 已对齐日期**（范围 = kline_daily 分区 ∩ [start,end]，写边界再过滤一次），绝不 phantom-write 日 K 没有的日期；per-symbol 失败台账 `failed_symbols: [{"symbol", "reason"}]`，`reason` 二选一 —— `"empty_response"`（上游空但有 kline_daily 覆盖，如 BJ 标的 R8）或截断异常消息（≤200 字），终态如实反映部分失败，**绝不伪造成功/0 填缺失**。
- **诚实 provenance（AQ-04）**：`origin="backfill"` 只存在于 job 终态 dict —— 湖无 provenance 列（回填与实时 EOD 同分区写，provenance 即分区存在性，per-分区 provenance 是 seam 变更，不在 Phase 32 范围）；`auction_unmatched_volume`/`auction_unmatched_amount` 上游无此字段 → 列缺席**永不 0 填**，派生 `auction_unmatched_amount` 仅当输入列可得时由读路径计算。
- **操作指引（AQ-05）**：rpm 1..60，默认 30（≈2s/码）；全 5537 码全量 ≈ 3-5.5h（rpm≈37 自然节流 ≈ 3h）；建议按子集 `symbols` 分批运行；重跑幂等（分区 merge-upsert 只填缺口）；出现 429 → 降 rpm 重跑；BJ 标的若上游无覆盖 → 诚实 `empty_response` 记录，不预填。触发示例：

  ```bash
  # 全量回填（默认 rpm=30）
  curl -X POST http://localhost:8000/api/kline/auction/backfill -H 'Content-Type: application/json' -d '{}'
  # 子集 + 日期范围 + 慢速（限流友好）
  curl -X POST http://localhost:8000/api/kline/auction/backfill -H 'Content-Type: application/json' \
       -d '{"symbols": ["000001.SZ", "600519.SH"], "start": "2026-07-01", "end": "2026-08-05", "rpm": 10}'
  # 响应: {"status": "started", "job_id": "..."} → GET /api/pipeline/jobs/{id} 轮询终态;
  # 取消: POST /api/pipeline/jobs/{id}/cancel (合作式)
  ```
- **AQ-06 注记（P2，doc-only）**：分钟历史回填已**正式关闭（CLOSED）** —— xyz 1m ≈ 21 交易日覆盖（实测）、ifzq/sina 仅尾随窗口、TickFlow 分钟档位 gated at pro+；`kline_minute` 保持增量 ≤30 日同步（`sync_and_persist_minute` 零改动）；证据：`research/v2.3-data-depth/AUCTION-BACKFILL.md` §4/§6。
- **R3 注记（probe 缓存）**：`capabilities.auction=True` 后 `resolve_auction_probe()` 每次调用一次实时 HTTP（1.6s 名义 / 8s 超时）——影响 `GET /api/kline/auction/history` 与 EOD 闸门延迟；短 TTL probe 缓存是**后续可选守卫**，不在 Phase 32 内实现。

---

## 📊 指标流水线(Indicators)

原生 Polars 向量化,全 A 股一次扫表落盘 enriched Parquet:

- **均线 / 趋势**:MA(5-60) · EMA · MACD · 动量 · 布林带
- **震荡 / 波动**:RSI · KDJ · ATR · 年化波动率 · 振幅
- **量能 / 涨跌停**:量比 · 量均线 · 涨停信号 · 连板数
- **原子信号**:MA / MACD 金叉死叉 · N 日新高新低 · 布林突破
- **复权**:基于除权因子自动前复权,回测与指标口径一致

盘后管道(15:30 CST 自动触发)会重新拉日 K + 重算 enriched 表。

---

## 🧪 回测引擎(Backtest)

基于 vectorbt(**三种模式**):

| 模式 | 说明 |
| :--- | :--- |
| 个股回测 | 单标的 + 策略,看个股历史表现 |
| 策略组合 | 一个策略扫描全市场,按组合约束回测 |
| 自由信号组合 | 多个自定义信号组合,自定义权重 |

**真实约束**:T+1 · 手续费 · 滑点 · 止损 · 最大持仓天数。

**组合管理**:最大持仓数 · 敞口控制 · 等权 / 自定义仓位。

输出净值曲线 · 夏普 · 最大回撤 · 胜率 · 交易明细。SSE 流式进度支持切页重连,不会丢失回测任务。

**ETF 支持**:三种模式的后端与 API 均支持 `asset_type=etf`,回测面板改从 `kline_etf_enriched` 读取(单次回测为单一资产类型,不混合股票与 ETF)。策略组合与因子回测页均有 `股票 / ETF` 切换,ETF 模式下策略列表与标的搜索跟随资产。需先开启 ETF 拉取并跑盘后管道。

---

## 📡 监控中心(Monitor)

统一规则引擎,一个页面管理**五类监控**:

| 类型 | 场景 |
| :--- | :--- |
| 策略监控 | 策略扫描结果有变化时触发(如新增符合标的) |
| 个股信号监控 | 特定个股的指标条件(如 `RSI > 80`) |
| 价格涨跌监控 | 涨跌幅 / 价格突破阈值 |
| 全市场异动 | 全市场异动(如快速拉升/跌停) |
| 盘前监控 | 09:26 盘前预览帧上的竞价白名单字段条件 (`open_gap` / `auction_*`), 事件带「盘前·非最终」标注 |

**ETF 支持**:规则可选资产类型 `股票 / ETF`。监控引擎按规则 `asset_type` 分轮评估——ETF 规则用 ETF enriched 快照评估(`engine.evaluate(..., asset_type="etf")`),策略型规则走 ETF 历史加载器(读 `kline_etf_enriched`)。盘中触发需开启 ETF 实时行情(`realtime_pull_etf`),使 ETF 报价进入 enriched 快照。

**特性:**

- 多条件 AND/OR + 冷却期去重 + 严重级别(info / warn / critical)
- 多入口配置:监控中心新建 / 个股详情页「加监控」/ 策略卡片一键开启
- 命中后右下角弹窗(可配声效)+ 持久化到 `alerts.jsonl`,菜单未读徽标
- **触发记录详情**:每条记录展示命中的具体条件(如 `RSI>80`)与当前价位,一眼看清为何触发
- **盘前监控 (preopen)**:规则字段仅限竞价白名单 (`open_gap` / `auction_volume` / `auction_amount` / `auction_volume_ratio` / `auction_unmatched_amount`),配置期即拒绝 EOD 列 (`change_pct` / `close` 等)——杜绝建出必失败的规则
- 盘前告警带「盘前·非最终」(provisional)标注;竞价数据源降级时竞价列规则 fail-closed 0 告警(绝不 0 填),并加「数据降级」(degraded)徽标
- 盘前评估挂在 09:26 预览 job 尾段,与盘中连续竞价告警互斥(盘中 `evaluate` 显式跳过 preopen 规则)

### 飞书 Webhook 推送

全局一处配置飞书群机器人地址,启用推送的规则命中即推送到飞书群(支持签名校验)。可在设置页设「默认推送渠道」,新建规则自动预填。

---

## 📈 个股分析(Beta)

以「行情 + 关键价位」为主体的单标的决策页:

- **专用日 K 图表**:主图 + 成交量 + 滑块,默认近 6 个月
- **9 类关键价位**(纯函数实时计算,毫秒级):压力支撑 · 成交密集区 · 枢轴点 · 前高前低 · Keltner 通道 · ATR 止损 · 缺口位 · 斐波那契 · 整数关口
- **AI 四维分析**:技术 / 基本面 / 财务 / 消息面流式生成,实战派交易员视角

---

## 🏆 连板梯队 & 概念分析

- **连板梯队**:实时统计各连板层级(首板 / 2 连板 / 3 连板...)的标的与封单,捕捉市场情绪与题材热度
- **概念涨幅轮动**:基于 ths 概念 / 行业,统计概念板块涨幅与 RPS 轮动,AI 分析资金主线
- **盘后 AI 复盘**:盘后自动生成市场复盘,可推送至飞书群

### 📊 竞价复盘 (Auction Recap)

确定性竞价复盘面板(REV-01..05):与 AI 复盘流内嵌面板共用同一装配函数
(`build_auction_recap`),**确定性数据,非 AI 生成** — 基于三类冻结资产的只读聚合,
不触发任何计算/同步/回填,绝不写任何存储(POOL-03 零执行权限)。

- **三块面板**:
  - **真实竞价活跃度**:集合竞价湖分区(`kline_auction`,09:15-09:25 窗口末行,09:30+
    连续竞价 bar 永不入列)的竞价总额 / 标的总数 / 金额 Top 10 / 竞价量比;
  - **开盘涨幅快照**:enriched 读时计算的 `open_gap` 高开分布(≥2% / ≥5%)、均值、
    Top 10(open_gap 基于 enriched 复权口径);
  - **盘前信号质量**:盘前预览(`premarket_results`)∩ 竞价族策略的信号命中统计 —
    平均 open_gap、**EOD 口径**收盘兑现率/收阳率(预览行绝不直接用作收盘兑现率;
    预览有行而 EOD 缺行计 `n_missing`,不填充)。
- **诚实性**:`data_completeness` 枚举 `{full, no_auction_lake, no_premarket_preview,
  pre_eod, partial}`;缺失块省略 + 显式注记;**pre_eod**(15:30 竞价同步完成前)诚实标注
  「盘后竞价同步未完成,建议 15:35 后重跑」;无数据日 → 诚实空态,绝不 0 填/404。
- **复盘集成**:面板 delta 在 done 前(事件序 meta → AI delta* → 面板 delta → done),
  经 delta 机制归档 / SSE / 飞书三跳全收;面板全缺席 → 退化为纯 AI 报告;默认调度
  **15:40**(15:30 竞价同步 + 15:35 股池持久化之后)。
- **可选 AI 点评**:`recap_auction_commentary` 默认关闭(设置 API 切换),开启时 AI
  仅可引用确定性切片中给出的数值(护栏:禁止编造,与面板冲突以面板为准)。
- **只读端点 (REV-05)**:`GET /api/market-recap/auction?as_of=YYYY-MM-DD` —
  独立只读端点,`as_of` 严格校验(非法 → 400),缺省取最新交易日;无数据 → 200
  `available:false` 诚实空态;**guest 会话 → 掩码视图**(逐标的身份 `******` + 竞价值
  剥离,聚合统计与状态标注保留);与复盘流内嵌面板同源。
- 零新增依赖;端点/服务受 POOL-03 AST 守卫锁定(GET-only、零写路径、零执行族 import、
  import 白名单)。

---

## 🧰 数据与扩展

### TickFlow 多源数据

日 K / 分钟 K / 指数 / 财务 / 实时行情,基于 [TickFlow](https://tickflow.org) 官方 SDK。

### 🔌 第三方数据接入(重点)

支持将自有量化项目的数据并入,与内置数据同台分析:

| 方式 | 说明 |
| :--- | :--- |
| HTTP 定时拉取 | Tushare 等 API,定时拉取并入库 |
| CSV / Excel 上传 | 页面直接上传文件 |
| JSON 写入 | 程序化写入 |

接入后自动 schema 发现 + 符号归一,页面可视化配置,最终并入 DuckDB 同台分析。

### 盘后定时管道

APScheduler 15:30 CST 自动:拉日 K → 重算 enriched 表 → 跑监控规则。

### 令牌桶限流

适配各档位 rpm / batch 限制,批量合并 + 增量拉取,避免触发数据源限流。
