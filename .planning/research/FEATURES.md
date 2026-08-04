# Feature Research: AthenaQuant v2.0 竞价深度与历史股池

**Domain:** A-share 竞价选股 (call-auction stock screening) — historical pool browsing, auction strategy family, true auction match-data columns
**Researched:** 2026-08-04
**Confidence:** MEDIUM (web research cross-checked across multiple Chinese quant sources; existing-seam claims HIGH, grounded in shipped v1.3 code)

## Scope Note

本文件只研究 **v2.0 新增能力**(POOL-04 日期导航 / STRAT-04 竞价策略族扩展 / STRAT-05 盘中确认 / DATA-04 真集合竞价数据列 / DATA-05 盘前股池)。v1.3 已验证的能力**不重复研究**,作为既有基线被依赖:

- 分钟 K 同步(`kline_minute`,09:30 起,`minute_sync_symbols` 作用域旋钮) — DATA-01
- `open_gap`(open/prev_close−1)受管 enriched 列 — DATA-02
- 竞价探测服务(`not_configured/available/fail_closed/error`,30s TTL,09:30 bar 永不标竞价) — DATA-03
- 3 个核心竞价策略(竞价多头 / 盘前强势量化 / 早盘之星)+ 每策略 `hit_factors` 因子命中聚合 — STRAT-01/02/03
- 股池 Hub:单一 as_of 投影、五列下钻、概念筛选、交叉共振、`GET /api/pool/hub`、guest 脱敏服务端权威 — POOL-01/02/03, GUEST-01/02
- 21 内置策略、Polars 向量化、Parquet/DuckDB 数据湖、SQLite 运行态、FastAPI 单宿主

---

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **日期导航(历史股池浏览,POOL-04)** | 参考 UI 有 `交易日 2026/08/04 ‹ ›`;短线打板/复盘文化(开盘啦「竞价页面选日期」、淘股吧历史竞价图)默认可回看任意交易日的股池。单一 as_of 视图让"今天选出的池子昨天什么样"无从回答,产品显得残缺。 | MEDIUM | 引擎已支持按日回放(`run_all(body.as_of)` → `_load_enriched_for_date`),enriched 按 `date=YYYY-MM-DD` 分区(实测 246 个交易日分区)。真正的成本在:把 `strategy_cache.json` 的**单一 as_of 结构**泛化为按日缓存/按日回放,以及**历史日概念标签的 PIT 问题**(见 PITFALL 一节)。 |
| **真集合竞价数据列:竞价量 / 竞价金额(DATA-04)** | v2.0 的核心卖点,也是参考 UI 之外产品差异化的数据地基。Tushare `stk_auction_o`(盘后更新,vol/amount/vwap)与 BigQuant `cn_stock_factors_auction`(`open_auction_trade_volume/amount`)**真实 09:25 撮合成交**是权威语义。probe-gated:仅当 DATA-03 探测 `available` 时作为一级列。 | MEDIUM | 与 v1.3 canonical 列 `auction_volume/auction_amount`(自定义源 09:15–09:25 窗口)同构,可直接落为 enriched 受管列。**真实成交 vs 派生的边界**必须严格区分(见下)。 |
| **5 个策略标签落成第一性原理因子定义(STRAT-04)** | 参考产品把「竞价阿尔法/极速抢筹/T+1闪电/竞价全面策略/金色两点半」当策略卡片列出,用户期待竞价策略族完整;但这些都是**产品标签,无公开配方** — 必须像 v1.3 三个核心策略一样,用自己的因子/阈值/权重诚实定义。 | MEDIUM | 每个策略一个 `strategy/builtin/*.py`,进 `strategy/builtin/` 唯一注册轨道(STRAT-03 铁律)。**金色两点半不是竞价策略**(见 Differentiators/Anti-Features),必须诚实归类。 |
| **交易日历约束的日期步进** | 日期导航的 ‹ › 必须落在**真实交易日**,且跳过无数据日(停牌同步缺口/未同步日期)给出空态而非报错。用户期待像看历史行情一样翻交易日。 | LOW | 复用 `research/calendar.py`(实测 241 交易日/年 的 A 股日历校准)+ enriched 分区集合求交集;非交易日禁用步进按钮。 |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **历史股池「确定性回放」+ 可选「逐日存档」双模式** | 大多数零售工具要么只有当日竞价、要么要手动保存。回放模式=今天策略定义在 D 日数据上的确定性重算(等于小回测,零存储);存档模式=当日真实计算结果逐日落盘(等于历史记录)。区分两者是对"历史股池"语义的诚实回答。 | MEDIUM | 回放直接复用 `run_all(as_of)` + `_load_enriched_for_date`,确定性、可审计。存档需要每日写入任务(扩 `strategy_cache.write_cache` 为按日键)。**推荐回放优先**,存档为可选增强。 |
| **竞价未匹配金额 / 竞价换手(派生列)** | 零售抢筹文化的核心代理:同花顺问财「竞价抢筹」= 竞价未匹配金额 > 0 + 竞价量比;SuperMind「竞价量能双指标」= 量比 + 竞价成交额(杜绝无量虚涨)。这些**可从 委托量−成交量 派生**,不需要 Level-2,是大多数免费平台不做、但短线用户认的指标。 | MEDIUM | 需要 `order_volume/order_amount`(委托量)输入 — 来自 BigQuant 级因子源或自定义 auction 源扩展;无委托量时 fail-closed 回退到 竞价量比/竞价金额。 |
| **STRAT-05 盘中确认(09:30–10:00 分钟 K 复评)** | 竞价信号是**开盘瞬间的猜测**;用 09:30–10:00 分钟 K 确认(量价齐升、不破开盘价、分钟级回踩不深)再收窄池子,显著降低 竞价高开低走 的假阳性。这是「早盘之星/盘前策略」的增强,也是平台已有分钟 K 能力(Data-01)的差异化复用。 | MEDIUM | 依赖 `kline_minute` + 交易日历;策略形态为「竞价初筛 → 盘中确认收窄」两阶段。与 T+1闪电 的「次日早盘卖出」共享分钟 K。 |
| **虚拟成交(虚拟匹配量)的实时采集或诚实派生** | 09:15–09:25 界面上滚动的「虚拟成交/虚拟匹配量」是**实时盘口快照,盘后 EOD 源不持久化**。能把它作为实时列(竞价时段)或从撮合/委托差派生(盘后近似)是少数产品才有的能力。 | HIGH | 实时路径需竞价时段数据源(Tushare `stk_auction` 09:26–09:29 可拉当日;实时行情源 09:15 起快照);盘后只能派生/标注为估计值,**绝不冒充历史观测**。 |
| **DATA-05 盘前股池(09:30 前可用)** | 竞价策略的价值在开盘前;若竞价源支持实时盘前评估,股池在 09:30 前即可浏览 — 对齐 开盘啦「早盘竞价/竞价涨停委买」的实时模式,是 T+0 工作流差异点。 | HIGH | 依赖:实时竞价源 + 交易日当天的盘中判定;与平台「研究建议、零执行权」边界不冲突(仍是只读股池)。 |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **把「金色两点半」当 09:15–09:25 竞价策略实现** | 参考产品把五个标签并排;表面看都属"竞价策略族"。 | 金色两点半是**尾盘(14:30 后)策略**:选当天涨幅 3%–5%、尾盘走强的票,14:30–15:00 买入,隔夜持有,次日 09:30–10:00 卖出(大智慧金色两点半股票池、尾盘选股法)。它需要的是 T 日盘中/日 K 数据,**不是竞价窗口数据**;塞进竞价窗口 = 语义造假。 | 诚实归类:实现为 T 日尾盘选股策略(依赖 `change_pct` + 分钟 K),命名与描述明确「尾盘/隔夜」而非「竞价」;或从"竞价策略族"卡片组移出单独成组。 |
| **用 09:30 连续竞价 bar 充当竞价量/金额** | 免费分钟数据只有 09:30 起,取巧最快。 | v1.3 已用回归测试锁死「09:30 bar 永不标集合竞价」(T-16-01);任何把 09:30 成交量当竞价成交量的实现都违反平台契约且误导用户。 | 探测 `available` 时用真实竞价列;否则 fail-closed 到派生 `open_gap`/量比。 |
| **把「虚拟成交」作为历史序列持久化** | 用户想要历史竞价图(开盘啦/淘股吧有)。 | 虚拟成交是 09:15–09:25 的**实时预撮合估计,不是最终成交**;EOD 源无历史虚拟序列。用 09:25 最终成交或委托差反推并标注"估计",否则是编造历史。 | 历史图只画**真实竞价量/金额/未匹配金额**(可持久化);虚拟成交仅实时展示,标注「实时估计」。 |
| **逐日全量存档每个交易日的股池 JSON,永久保留** | "历史记录"听起来可靠。 | 单宿主 Parquet+SQLite 部署下,存储随交易日线性膨胀;而 enriched 分区已冻结历史数据,**确定性回放**随时可重建同一池子。 | 回放优先(零存储,可审计);存档仅作为可选增强,按天键控(如按日 `strategy_cache.{date}.json`),支持清理策略。 |
| **复刻专有策略配方(陈星量化等)** | 参考产品有这些名字,用户点名。 | 无公开规格,复刻=猜测+可能侵权;v1.3 已确立「第一性原理 + 诚实命名」铁律。 | 用自己的因子定义,名字用自己能解释的标签;META.description 写清"参考标签的诚实解读"。 |
| **日期导航放行任意日期(含无数据日)** | 输入框自由输日期。 | 无 enriched 分区/未同步的日期返回空池,用户误以为策略"失效";非交易日导航无意义。 | 导航受限在「有 enriched 分区」的真实交易日集合内;无数据日给空态文案而非报错。 |
| **在 DATA-04 探测确认前一次性实现全部 5 个策略** | "一起做完"。 | 竞价全面策略/极速抢筹/竞价阿尔法 的因子价值高度依赖真实竞价列;无真列时它们退化为 open_gap+量比 的重复组合,产品同质化。 | 顺序化:先探测 → 先落地 2 个真列可支撑的策略,其余按数据可用性分批。 |

---

## Feature Dependencies

```
[竞价量/金额一级列 (DATA-04)]
    └──requires──> [竞价探测 available (DATA-03 既有 seam)]
                       └──requires──> [自定义 auction 数据集 or 内置 auction 能力源 (v1.3 已建)]
                           └──enhances──> [极速抢筹 / 竞价阿尔法 / 竞价全面策略 (STRAT-04)]

[竞价未匹配金额 / 竞价换手 (派生列)]
    └──requires──> [委托量 order_volume/amount 输入]  ──可选──> [DATA-04 源扩展]
                    (无委托量 → fail-closed 回退 量比+金额)

[极速抢筹] ──requires──> [竞价量比 / 竞价金额 / 竞价涨幅甜点区 (2.8%–3.5%,>7% 风险)]
[竞价阿尔法] ──requires──> [open_gap + 竞价量比/金额强度 综合]
[T+1闪电] ──requires──> [open_gap + change_pct + 分钟K(次日卖出择时)]
[金色两点半] ──requires──> [T 日 change_pct + 分钟K(尾盘)]  ──NOT──> [竞价数据]
[STRAT-05 盘中确认] ──requires──> [分钟K同步 (DATA-01 既有)] ──enhances──> [早盘之星/盘前/极速抢筹]

[日期导航 (POOL-04)]
    └──requires──> [引擎按日回放 run_all(as_of) (既有) + enriched date 分区 (既有)]
    └──requires──> [strategy_cache 按日键泛化 or 直接回放不落 today 缓存]
    └──requires──> [交易日历 ∩ 分区集合]
    └──conflicts──> [概念板块 PIT: 当前概念映射是快照,历史日池子概念标签 = T 日标签而非 D 日标签]

[DATA-05 盘前股池] ──requires──> [实时竞价源 + 当日盘中判定]  ──deferred──> [DATA-04 稳定后]
```

### Dependency Notes

- **DATA-04 是 STRAT-04 的价值前置**:极速抢筹/竞价阿尔法/竞价全面策略 的区分度来自真实竞价量/金额/量比;没有真列,这五个策略彼此塌缩为同一组 open_gap+量比 组合,无法支撑"策略族完整"的卖点。因此**先探测、先落列,再批量做策略**。
- **金色两点半与竞价数据无依赖**:它需要的是 T 日涨跌幅与尾盘分钟 K — 这是它与竞价策略族最大的语义断裂,必须体现在命名/描述/分组上。
- **日期导航零新数据依赖**:`run_all(body.as_of)` 已支持任意日回放,enriched 已有 246 个交易日分区 — POOL-04 的工程量在缓存结构泛化与 PIT 概念处理,不在数据采集。
- **PIT 概念是 POOL-04 唯一的真陷阱**:`pool_hub` 的 `_build_concept_map` 读**当前** ext 概念快照;历史日回放若直接 join,会拿今天的板块标签贴过去的票。规避:历史视图要么标注"概念为当前快照",要么用当日概念快照(需历史 ext 分区,目前没有)。
- **DATA-05 依赖 DATA-04 的源能力**:实时盘前池需要同一竞价源在 09:15–09:29 窗口可拉数;盘后源(EOD 更新)满足不了盘前场景,所以 DATA-05 排在 DATA-04 稳定之后。
- **STRAT-05 增强而非替换**:盘中确认收窄的是竞价初筛池,不改初筛语义;它复用 `kline_minute`,不新增数据轨道。

---

## MVP Definition

### Launch With (v2.0 core)

最小可用 v2.0 — 验证「竞价深度 + 历史回看」概念:

- [ ] **竞价量/金额一级列(DATA-04,probe-gated)** — 探测 `available` 时把 `auction_volume/auction_amount`(09:15–09:25 窗口,真实 09:25 撮合)落为受管列,在股池/明细展示;不可用则维持 open_gap 派生降级。**这是全部下游的入口。**
- [ ] **日期导航(POOL-04,回放模式)** — 交易日历步进 + 日期选择;按日调用 `run_all(as_of)` 确定性回放;strategy_cache 泛化为按日键(不污染今日缓存);无数据日空态;概念标签标注「当前快照」。
- [ ] **极速抢筹 + 竞价阿尔法(STRAT-04 前 2 个)** — 第一性原理因子定义(竞价量比/竞价金额/竞价涨幅甜点区 与 open_gap+量比+金额强度综合),落 `strategy/builtin/`,带 hit_factors。
- [ ] **金色两点半(诚实归类)** — 尾盘(14:30+)选股因子(T 日涨幅 3%–5% + 尾盘分钟确认),命名/描述明确「尾盘隔夜」,不混入竞价窗口。
- [ ] **派生列:竞价未匹配金额(可选输入)** — 委托量可得时派生;无委托量回退量比+金额。

### Add After Validation (v2.0.x)

- [ ] **竞价全面策略(STRAT-04 综合版)** — 全因子加权复合(open_gap+量比+金额+换手+未匹配金额);触发:DATA-04 稳定、用户需要"一把梭"综合池。
- [ ] **T+1闪电(STRAT-04)** — 竞价强信号买入 + 次日早盘分钟 K 卖出择时;触发:STRAT-05 分钟确认能力落地。
- [ ] **STRAT-05 盘中确认(09:30–10:00 复评)** — 竞价初筛 + 分钟 K 确认收窄;触发:竞价池已有、用户反馈高开低走假阳性多。
- [ ] **竞价换手/委托失衡派生列** — 需委托量输入;触发:auction 源扩展出 order 字段。

### Future Consideration (v2.1+)

- [ ] **虚拟成交实时列 / 历史竞价图** — 需实时竞价源 + 盘中快照采集;EOD 源无法支撑,标注「实时估计」。
- [ ] **DATA-05 盘前股池(09:30 前可用)** — 需实时竞价源;触发:找到稳定的盘前数据通道。
- [ ] **逐日存档模式(非回放)** — 每日写入当日池子快照;触发:回放被验证、用户要求"当日真实记录"审计语义。
- [ ] **POOL-05 自选股联动/异动提醒** — 池成员变化进 watchlist;独立需求,不在本次竞价深度范围。

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| 竞价量/金额一级列(DATA-04,probe-gated) | HIGH | MEDIUM | P1 |
| 日期导航 · 回放模式(POOL-04) | HIGH | MEDIUM | P1 |
| 极速抢筹(STRAT-04) | HIGH | LOW–MEDIUM | P1 |
| 竞价阿尔法(STRAT-04) | HIGH | LOW–MEDIUM | P1 |
| 金色两点半 · 尾盘诚实归类(STRAT-04) | MEDIUM | LOW–MEDIUM | P1 |
| 竞价未匹配金额派生列 | MEDIUM | MEDIUM | P2 |
| 竞价全面策略(STRAT-04 综合) | MEDIUM | MEDIUM | P2 |
| T+1闪电(STRAT-04) | MEDIUM | MEDIUM | P2 |
| STRAT-05 盘中确认(09:30–10:00) | MEDIUM–HIGH | MEDIUM | P2 |
| 竞价换手 / 委托失衡派生列 | MEDIUM | MEDIUM | P2 |
| 虚拟成交实时列 / 历史竞价图 | MEDIUM | HIGH | P3 |
| DATA-05 盘前股池 | MEDIUM | HIGH | P3 |
| 逐日存档模式 | LOW–MEDIUM | MEDIUM | P3 |
| POOL-05 自选股联动 | MEDIUM | MEDIUM | P3 |

**Priority key:**
- P1: 必须随 v2.0 发布 — 数据地基 + 最高价值策略 + 参考 UI 已见的日期导航
- P2: 应有,数据/分钟确认能力到位后补
- P3: 未来 — 依赖实时源或独立需求

---

## Competitor Feature Analysis

| Feature | 开盘啦 (kaipanla) | 同花顺问财 (iwencai) | Tushare / BigQuant (数据侧) | 参考 UI(策略选股附件) | Our Approach |
|---------|-------------------|----------------------|------------------------------|------------------------|--------------|
| 竞价选股策略 | 竞价系统(早盘竞价/板块竞价/竞价涨停委买),实时竞价多维分析 | 自然语言竞价选股(涨幅/量比/未匹配金额/竞价成交额公式) | 数据接口,无策略 UI | 策略卡片 + 股池 N | 内置策略族(第一性原理因子),`strategy/builtin/` 唯一轨道 |
| 历史股池/竞价回看 | 历史竞价图:选日期+代码查询个股竞价 | 日期限定自然语言筛选 | 盘后 EOD 数据可回放 | 日期导航 `‹ ›`(参考) | 确定性回放(按日 `run_all`)+ 交易日历约束 + PIT 概念标注 |
| 真实竞价数据列 | 实时竞价(自有行情) | 指标计算(部分付费) | `stk_auction_o` / `cn_stock_factors_auction`(真实撮合成交) | 开盘涨幅/涨跌幅/关联因子 | probe-gated 一级列(竞价量/金额),可用即升,不可用 fail-closed |
| 虚拟成交 | 实时展示 | 不持久化 | 无历史 | — | 仅实时/派生估计,不伪造历史 |
| 盘中确认 | 实时分时 | — | 分钟数据(09:30 bar=竞价聚合) | — | STRAT-05:竞价初筛 + 09:30–10:00 分钟 K 收窄 |
| 研究边界 | 资讯/工具属性 | 选股工具 | 数据服务 | 选股建议 | 零执行权研究建议(平台自 v1.0 边界,POOL-03 延续) |

---

## Sources

**数据与规则(MEDIUM–HIGH,多源交叉 + 官方文档直取):**
- Tushare `stk_auction_o` 开盘集合竞价数据(官方文档直取,字段 close/open/high/low/vol/amount/vwap,盘后更新) — https://tushare.pro/document/2?doc_id=353
- Tushare `stk_auction` 当日集合竞价成交(09:26–09:29 可取,历史自 2025-01) — https://tushare.pro/document/2?doc_id=369
- Tushare `stk_mins` 分钟数据(09:30:00 bar 标注为集合竞价统计) — http://tushare.xcsc.com:7173/document/2?doc_id=10222
- BigQuant `cn_stock_factors_auction` 集合竞价因子表(官方数据页直取:open_auction_trade_volume/amount, order_volume/amount, cancel_volume, turnover, overnight_change_ratio, limit_up/down) — https://bigquant.com/data/datasources/cn_stock_factors_auction
- 集合竞价规则(多源:知乎/雪球/百度百科;09:15–09:20 可撤单、09:20–09:25 不可撤单、09:25 撮合、最大成交量优先) — https://zhuanlan.zhihu.com/p/137762677 ; https://xueqiu.com/1009642805/192622908

**策略标签文化(MEDIUM,web 交叉):**
- 金色两点半 = 尾盘 14:30 后选股、隔夜持有、次日早盘卖(复盘网/新浪/东方财富/大智慧金色两点半股票池) — https://www.fupanwang.com/zhishi/1248.html ; https://www.sina.cn/news/detail/5289750221293652.html ; https://baike.baidu.com/item/大智慧金色两点半股票池
- 竞价抢筹/未匹配金额/竞价量比(同花顺问财公式、55188、SuperMind) — https://www.55188.com/keywords-集合竞价抢筹量比选股.html ; https://k.sina.cn/article_7879922977_1d5ae152101901dscg.html
- 竞价量比与涨幅甜点区(SuperMind:量比+竞价成交额、2.8%–3.5% 甜点、>7% 风险) — https://quant.10jqka.com.cn/view/community

**竞品 UX(MEDIUM):**
- 开盘啦 竞价系统 + 历史竞价图(选日期+代码) — https://apps.apple.com/cn/app/开盘啦/id1071188962 ; https://www.tgb.cn/dialog/1LTvSi3O5wI_54540345_1

**既有基线(HIGH,直接检视 v1.3 代码):**
- `backend/app/services/auction_probe.py`(DATA-03 探测服务)、`backend/app/services/pool_hub.py`(单一 as_of 投影)、`backend/app/services/strategy_cache.py`(单一 as_of 缓存结构)
- `backend/app/api/screener.py::run_all`(`as_of` 任意日回放 + `_load_enriched_for_date`)、`backend/app/strategy/builtin/auction_*.py`(3 核心策略)
- `backend/app/data_providers/custom/provider.py::get_auction`(09:15–09:25 canonical 列)、`data/kline_daily_enriched/`(246 个 date 分区)

---
*Feature research for: AthenaQuant v2.0 竞价深度与历史股池*
*Researched: 2026-08-04*
