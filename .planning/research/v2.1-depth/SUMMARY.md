# 研究合成摘要:AthenaQuant v2.1 历史深度与自选联动

**项目:** AthenaQuant
**里程碑:** v2.1 历史深度与自选联动
**研究日期:** 2026-08-06
**置信度:** MEDIUM-HIGH(四份研究均以仓库实读代码 + 磁盘实测为据;唯一不可验证项 = 实时竞价源可行性,已统一标 [INFERENCE] 并给出判定条件)

## Executive Summary

v2.1 在 v2.0「竞价深度与历史股池」(4 phases 20-23,14 需求 Complete)已归档基础上深化四个领域:逐日全量存档(非回放)、自选股联动、盘前股池、历史竞价图/虚拟成交实时列。四份研究的一致结论:**存储载体与查询契约全部已存在,缺口是「生成策略」与「诚实标注」,不是新存储或新依赖**——零新增运行时依赖是可达成且应坚持的硬约束。当前数据现状:`kline_daily_enriched/` 247 个分区(~51 MiB)vs `screener_results/` 0 个快照、`kline_auction/` 0 分区——「历史深度」的核心交付就是把缺口从 0 补到全覆盖。

推荐做法按依赖关系分四阶段(Phase 24 起,延续 v2.0 顺序编号),数据优先 + 核心优先:

- **Phase 24 逐日全量存档(HIST-01..04)** — 在现有 `screener_results/date=*/` 冻结快照湖上补「用户触发批量回填 job」,复用 `run_all_with_hits` + `persist_point_snapshot` 单条代码路径,**绝不调 `write_cache`**(防污染 single-as_of 最新指针,有 v2.0 实测陈旧 as_of 先例);补 `snapshot_origin: eod|backfill` 字段 + `backfill_needed` 缺口信号。这是里程碑名称「历史深度」的数据主体,置信度最高。
- **Phase 25 自选股联动(WATCH-01..04)** — 纯前端 join:复用服务端 `watchlist.parquet` + `/api/watchlist` API + 共享 `QK.watchlist` 缓存,在股池钻取表加星标/「只看自选」开关。刻意**零后端改动**以绕开 POOL-03 AST 守卫与 guest 掩码两条锁死测试边界。与 Phase 24 无依赖。
- **Phase 26 历史竞价图(CHART-01..03)** — 只读聚合 API + ECharts 多日竞价量/金额图 + 复活 DATA-06 派生列数据流。当前 `kline_auction` 湖 0 分区,**条件式交付**(有数据就画、无数据诚实空态);CHART-04 虚拟成交实时列 **defer**。
- **Phase 27 盘前股池第一档(PM-01..04)** — 09:26 独立调度 job 生成盘前预览,写入独立 `premarket_results/` 存储,补算 `open_gap`,前端诚实标注「盘前预览·非收盘定稿」。第一档(无实时竞价源)可交付;第二档(真实竞价列注入) **gate** 在外部实时竞价源。

最大风险与一致护栏:**任何非「最新日 EOD」路径(回填/盘前预览/历史 as_of 手动 run_all)都不得写 `strategy_cache.json` 的 single-as_of 指针**——四条研究独立得出同一结论。其次是「诚实性」铁律:回填快照 ≠ 当日归档(`snapshot_origin`)、盘前预览 ≠ 收盘定稿(`provisional`)、09:30 bar 永不标为集合竞价数据、虚拟成交列不冒充真实成交(分列永不相加)——全部由显式 provenance 字段 + fail-closed 空态表达,而非第二份存储或静默填充。

## 领域一页摘要

### 领域一:逐日全量存档 / 批量回填(ARCHIVE.md)

**推荐方案:** 方案 A——现有快照湖 + 用户触发批量回填 job + `snapshot_origin` 字段 + `backfill_needed` 缺口信号。不建独立归档层(方案 B 被否:双存储 = 双 source of truth),不做请求内回放(方案 C 被否:正是 POOL-06「自给自足、首个历史日请求不被阻塞」要消灭的问题)。

**关键决策:**
- 存储零改动:`screener_results/date={as_of}/part.json` 已是正确存档载体(POOL-04 冻结、原子写、无 union 键);缺口只是「0 个快照 vs 247 个 enriched 日」。
- 写路径纪律:**回填 job 对每个历史日只做 `run_all_with_hits(d)` + `persist_point_snapshot(d, origin="backfill")`,绝不调 `write_cache`**(ARCHIVE R1,高优先级)。既有手动 `POST /api/screener/run_all` 对任意历史 as_of 也写 cache(`api/screener.py:443-447`),是潜在指针污染,建议一并修复或文档化。
- 触发方式:用户触发 `POST /api/pool/backfill`(镜像 `extend_history` 手动触发模式),非 EOD 内隐式、非启动即回填;后台 job 单飞 + 可取消 + 升序摊销 warmup。
- 诚实性:回填快照 `strategy_version` = 回填时刻策略集,`snapshot_origin:"backfill"` 显式标注,不伪装 as_of 时刻指纹。

**需求清单:** HIST-01(批量回填 job + 零指针污染)、HIST-02(snapshot_origin 诚实性)、HIST-03(缺口/进度可见)、HIST-04(护栏与规模化)。

### 领域二:自选股联动(WATCHLIST.md)

**推荐方案:** 方案 (c)——复用现有服务端 `watchlist.parquet` + `/api/watchlist` API,股池前端做 join(星标/过滤),自选集合经共享 `QK.watchlist` 缓存「本地持有一致」。**零后端改动**。

**关键决策:**
- 自选清单唯一事实来源已是服务端 Parquet(`watchlist.py:21-24`),且被实时监控/自选池/盘后兜底四处服务端消费;localStorage 方案(方案 a)制造双源自漂移,否决。
- 服务端标注 `is_watched`(方案 b)触碰两条锁死测试边界(POOL-03 AST 守卫 token 含 `watchlist`、guest 掩码 T-19-03),否决。
- 匹配键 = 全后缀 `symbol`,实测股池行与自选 parquet 同格式,`Set.has(row.symbol)` 精确 join;前端已有完全相同的先例(Screener.tsx:429-447),直接抄。
- guest 语义:股池页 `mode==='vip'` 才发 `QK.watchlist` 查询(否则 401 跳登录),guest 不渲染星标/开关。
- **POOL-05 编号冲突:** v2.0 已 shipped 的 POOL-05 =「历史视图独立只读端点」;v2.1 PROJECT.md 又把「自选股联动」标为 POOL-05。需求清单须用 **WATCH-** 前缀。

**需求清单:** WATCH-01(股池明细行星标+切换,VIP)、WATCH-02(「只看自选」过滤开关,VIP)、WATCH-03(自选集合一致性 + 匹配键契约)、WATCH-04(批量加自选,可选/边界)。

### 领域三:盘前股池(PREMARKET.md)

**推荐方案:** 方案 (b)——盘前预览股池 + 诚实 pre_open 标注,**分两档**。第一档(默认,无实时竞价源):工作日 09:26(09:25 撮合定盘后)盘前 job 经 `run_all_with_hits(as_of=today)`,数据 = quote 实时帧(今日 open 定盘)+ 昨日 enriched,**补算 `open_gap`**;竞价列诚实缺席;预览写**独立存储** `premarket_results/date={as_of}/part.json`(`window:"pre_open"` + `computed_at` + `provisional:true`)。第二档(可选,gate):自定义 auction 源 probe 对今日 `available` 时读时注入真实竞价列,不新增盘前写湖路径。

**关键决策:**
- 股池现状 = T 日盘后 15:35 生成(T 日完整收盘数据),T+1 09:30 前看到的是昨日收盘池——盘前预览填补「今日盘前可用」窗口。
- 盘前 live 帧缺口:**`compute_enriched_today`(`pipeline.py:1250-1540`)不计算 `open_gap`**,而竞价策略族几乎全引用它 → 预览必须补算(单一实现,勿与 EOD Pass 4 双源漂移)。
- 盘前 `vol_ratio_5d` 失真(`trading_minutes_elapsed=0 → time_factor=1.0`,竞价量被当全天量)→ 预览禁用,优先 `auction_volume_ratio`(PIT-safe)。
- 盘前预览**绝不写 `strategy_cache`**(单 as_of + today_ever union 语义)也不写 `screener_results` EOD 快照。
- 前端已有诚实钩子:`AuctionColumnStatusBadge` 盘前分支(StockListTable.tsx:72-122)+ `market_phase:"preopen"` + `is_trading_hours`;消费 `market_phase` 而非仅布尔以区分「竞价窗口进行中」与「休市」。

**需求清单:** PM-01(盘前预览 job:调度+生成+独立存储)、PM-02(数据帧完整性:open_gap 补算 + 诚实列语义)、PM-03(probe 盘前语义:今日窗口实时判定 + fail-closed 降级)、PM-04(前端盘前视图:诚实窗口标注 + 预览/EOD 分离)。

### 领域四:历史竞价图 / 虚拟成交实时列(CHART.md)

**推荐方案:** 做 (a) 历史竞价图(多日趋势,条件式)+ 一个「复活 DATA-06」小后端改动;虚拟成交实时列 **defer** 到外部源 probe 验证之后。

**关键决策:**
- 湖只有 canonical 4 列(`CANONICAL_AUCTION_COLS = ["symbol","datetime","auction_volume","auction_amount"]`,`auction_sync.py:32-35`),**无价格列 → 单日撮合价格曲线不可重建**,只能画量/额趋势;`auction_unmatched_amount` 在真实数据流是死代码路径(写路径 `_normalize_auction`/`sync_and_persist_auction` 裁剪集丢弃输入列)。
- 当前环境 `kline_auction` 湖 **0 分区**(目录不存在)→ CHART-01/02 条件式交付(有数据就画、无数据诚实空态);验收用 fixture/mock。
- 窗口内行粒度歧义:默认「取末行(09:25 最终撮合)」,随行数/时间窗返回;接入真实源后按源语义钉死。
- CHART-03 把写路径 canonical 集扩为「4 必需 + 2 可选」(源提供 `auction_unmatched_volume/auction_virtual_price` 时保留),激活读路径 `compute_auction_unmatched_amount` 分支——Phase 23 已交付的「派生·虚拟成交」UI 分组因此有真实值,不依赖新源。
- CHART-04 虚拟成交实时列:前置条件 = 存在返回窗口内行且含虚拟未匹配/参考价字段的自定义源;**本期只研究不实现**,产出 probe 实测报告,不满足则正式 defer 归档。

**需求清单:** CHART-01(历史竞价聚合只读 API)、CHART-02(历史竞价图前端)、CHART-03(湖摄入保留委托量输入列,复活 DATA-06)、CHART-04(候选/条件式,本期研究门)。

## 跨领域依赖与冲突

1. **POOL-05 编号冲突(高,必须解决):** v2.0 已 shipped 的 POOL-05 =「历史视图独立只读端点」(`.planning/milestones/v2.0-REQUIREMENTS.md` 与 `pool.py`/`pool_hub.py` docstring 为证);v2.1 `PROJECT.md` Target features 把「自选股联动」复用为 POOL-05(WATCHLIST.md 明确标出)。**建议:v2.1 自选股联动一律用 `WATCH-` 前缀**,避免追溯/验证串号;`POOL-05` 数字在 v2.1 内不得再指代自选联动。
2. **write_cache 指针污染纪律(跨 ARCHIVE + PREMARKET + screener API):** 三条路径独立得出同一结论——`strategy_cache.json` 是 single-as_of「最新指针」,任何非「最新日 EOD」写入都会让 `/api/pool/hub` 回显陈旧日期(v2.0 实测先例 as_of=2026-07-31)。受影响路径:HIST-01 回填 job(绝不 write_cache)、PM-01 盘前预览(独立存储)、既有手动 `run_all` 历史 as_of(`api/screener.py:445`,潜在 bug)。**建议在 requirements 层加统一护栏回归,并评估是否一并修复手动 run_all 的历史 as_of 写 cache 行为。**
3. **watchlist 与 pool 守卫(架构约束):** WATCH 方案刻意前端 join 而非服务端标注,因为 `test_pool_hub.py:788-791` 的 POOL-03 AST 守卫 token 含 `watchlist`(pool 特性 import watchlist 即红)+ `test_guest_masking.py` T-19-03 锁死游客面。任何服务端方案都触碰其一。**WATCH-01..04 必须保持零后端改动**(新增后端字段/端点 = 重开守卫评审)。
4. **盘前与 cache 指针(PREMARKET PM-01):** 盘前预览若误写 `strategy_cache` 会污染「最新」指针并与 EOD 同日合并「曾命中」;PM-01 强制独立存储 `premarket_results/`,与 `screener_results`(EOD 快照)和 `strategy_cache`(最新指针)三权分离。
5. **竞价湖共享(CHART + PM 第二档 + probe):** CHART-01/02 消费 `kline_auction` 湖(空);PM-02 第二档读时注入真实竞价列复用 `attach_auction_columns` 双闸门;两者都依赖 probe 判定词汇。当前湖 0 分区 → CHART 条件式、PM 第二档 gate。CHART-03 扩展写路径 canonical 集不得破坏 `auction_sync` 既有 4 列契约(向后兼容:源不提供即列缺席)。
6. **诚实语义统一(跨四领域不变量):** probe fail-closed(09:30 bar 永不标集合竞价)、回填快照不冒充当日归档(`snapshot_origin`)、盘前预览不冒充收盘定稿(`provisional`/`window`)、派生列不冒充真实成交(CHART-03 分列永不相加)。全部由显式字段 + 诚实空态表达,不靠第二份存储或静默填充。
7. **POOL-03 零执行权(新写路径的边界):** HIST-01 `POST /api/pool/backfill` 与 PM-01 盘前 job 都是**研究数据写路径**(写快照/预览分区),非实盘执行;POOL-03 AST 守卫词汇须扩展覆盖新端点(禁 import 执行族),且 `backfill_needed`(HIST-03)保持 GET-only 游客可读。

## Roadmap 建议

延续 v2.0 顺序编号(v2.0 结束于 Phase 23),**数据优先 + 核心优先**:先「历史深度」数据层,再自选联动,再两个候选项按条件式交付。

### Phase 24: 逐日全量存档(HIST-01..04)
**Rationale:** 里程碑核心交付「历史深度」——把 `screener_results/` 从 0 快照补到 247 日全覆盖;数据层,零外部依赖,研究置信度最高(ARCHIVE.md 全部源码核验)。存储/查询契约已就绪,前端 DateNavigator 零改动即可消费。
**Delivers:** 用户触发回填 job(`POST /api/pool/backfill`)+ `snapshot_origin` 字段 + `backfill_needed` 缺口信号 + 护栏(单飞/可取消/限界/升序)。
**Addresses:** HIST-01..04(v2.0 Deferred「逐日全量存档模式」)。
**Avoids:** ARCHIVE R1(write_cache 指针污染——回填绝不 write_cache)、R2(慢路径 30-120 分钟后台化)、R3(origin 诚实性)。
**Research flag:** 需要 `--research-phase`(中)——回填 job 设计细节(触发端点形状、max_days 边界、进度回调、与手动 run_all 并发)需规划研究;同时决策 R6 触发方式与 R1 附带的手动 run_all 历史 as_of 污染是否一并修复。

### Phase 25: 自选股联动(WATCH-01..04)
**Rationale:** 里程碑另一半核心「自选联动」;纯前端、零后端改动,复用 Screener.tsx 现成链路,风险最低;与 Phase 24 无依赖(可独立交付)。
**Delivers:** 股池钻取行星标+切换、只看自选过滤开关、跨页一致(QK.watchlist 全局缓存)、批量加自选(可选)。
**Addresses:** WATCH-01..04(PROJECT.md「POOL-05 自选股联动」——注意改号)。
**Avoids:** POOL-03 AST 守卫 + guest 掩码两条锁死边界(方案 b 必触碰)、方案 a 双源自漂移。
**Research flag:** 标准模式,跳过 research-phase;但**执行前须确认用户未提交改动 `frontend/src/pages/Watchlist.tsx` 未改 `QK.watchlist` 契约或引入第二套自选存储**(WATCHLIST.md 开放问题 2)——此为用户预存改动,绝不触碰。

### Phase 26: 历史竞价图 + 派生列复活(CHART-01..03)
**Rationale:** 与既有湖/视图/probe/诚实缺列机制完全同构,零新依赖,POOL-03 零执行权模式现成;即便空湖,诚实空态 + 未来配置源自动点亮,是低成本不烂尾交付。CHART-03 把 Phase 23 已交付但无真实值的「派生·虚拟成交」UI 分组补全,不依赖新源。
**Delivers:** `GET /api/kline/auction/history` 只读聚合 API + `AuctionHistoryChart` ECharts 组件(挂 StockPreviewDialog)+ 写路径保留委托量输入列。
**Addresses:** CHART-01..03。
**Avoids:** 空湖误导(诚实空态而非零值柱)、窗口行粒度歧义(默认末行语义,随行数返回)、CHART-03 canonical 集扩展的向后兼容风险。
**Research flag:** 中等——窗口行粒度「末行 vs 求和」需在验收中钉死;当前空湖,验收全用 fixture/mock。

### Phase 27: 盘前股池第一档(PM-01..04)
**Rationale:** 「09:30 前可用」的候选特性经研究确认第一档(无实时竞价源)可交付——数据依赖已具备(quote 实时 + 昨日 enriched);第二档 gate 在外部实时源。范围最大(新调度 job + 新存储 + 前端视图),排在核心项之后。
**Delivers:** 09:26 盘前预览 job + 独立 `premarket_results/` 存储 + `open_gap` 补算 + probe 今日窗口语义 + 前端诚实盘前视图。
**Addresses:** PM-01..04(PROJECT.md「盘前股池(09:30 前可用)」候选)。
**Avoids:** 09:25 前指示价漂移(09:26 调度)、盘前 `vol_ratio_5d` 失真(禁用/换 auction_volume_ratio)、strategy_cache 污染(独立存储)、PM 第二档 gate(实时源不可验证则不注入竞价列)。
**Research flag:** 需要 `--research-phase`(高)——`compute_enriched_today` 补算 open_gap 的 seam、probe 今日窗口改造、预览存储 schema、前端 market_phase 消费粒度、与 quote 轮询并发控制。

### Phase Ordering Rationale
- **数据优先 + 核心优先:** Phase 24(HIST)是里程碑名称「历史深度」的数据主体;Phase 25(WATCH)是「自选联动」主体,与 24 无依赖,先于两个候选项(26/27)交付核心价值。候选项按「代码面可完成度」排序:CHART-01..03(条件式、零新依赖)先于 PM 第一档(新调度+新存储+前端,范围最大)。
- **跨阶段共享的指针污染纪律:** Phase 24 与 27 各自落地「非 EOD 路径不写 strategy_cache」——HIST-01(绝不 write_cache)与 PM-01(独立存储)是同一纪律的两面;建议在 REQUIREMENTS 层抽象为统一护栏回归。
- **诚实语义在每阶段数据入口定死,消费端强制执行:** origin/provisional/probe fail-closed 在各阶段存储 schema 写入,前端只读透传,不另起第二套逻辑。
- **与 v2.0 的衔接零破坏:** 全部新端点/存储是**新增**——`/api/pool/backfill`(POST)、`/api/pool/dates` 扩展(backfill_needed)、`premarket_results/`、`/api/kline/auction/history`;既有 `/api/pool/hub`、`/api/pool/history`、`screener_results` EOD 快照、`strategy_cache` 单 as_of 契约全部保持不变(回归锁)。

### Defer / 条件式汇总
- **CHART-04 虚拟成交实时列(盘前):** **建议 defer**。阻塞在外部实时竞价源(返回窗口内行且含虚拟未匹配/参考价字段),本环境不可验证;本期只做 probe 实测报告(CHART.md §四 CHART-04 研究门)。
- **PM 第二档(真实竞价列注入盘前):** **gate**。判定条件 = 自定义 auction 源 probe 对今日 `available` 且返回今日窗口行;不满足则预览自动回落第一档(派生列,诚实标注 `degraded:true`)。
- **历史撮合价格曲线:** defer(湖无价格列,需写路径先加价格列,属 CHART-03 之外的增强)。
- **历史自选快照(某历史日我自选了哪些):** defer(自选是用户偏好非时间序列,WATCHLIST.md 开放问题 6)。

## 风险与开放问题汇总

| # | 风险/问题 | 级别 | 来源 | 处置 |
|---|-----------|------|------|------|
| 1 | **write_cache 指针污染**: 回填/盘前/历史 as_of 手动 run_all 若写 `strategy_cache.json` → `/api/pool/hub` 回显陈旧 as_of(v2.0 实测先例 2026-07-31) | 高 | ARCHIVE R1 / PREMARKET 风险 5 | HIST-01 绝不 write_cache + PM-01 独立存储 + 评估修复 `api/screener.py:445`;grep/AST 守卫锁死 |
| 2 | **外部实时竞价源不可验证**: 内置源全部无 `auction=True`(`base.py:25-26` 默认 False),`data/kline_auction` 空;PM 第二档与 CHART-04 完全依赖它 | 高 | CHART OQ-1 / PREMARKET 风险 1 | [INFERENCE];判定条件已写明;不满足则 PM 回落第一档、CHART-04 正式 defer 归档;不假装可得 |
| 3 | **空湖误导**: 当前 `kline_auction` 0 分区,CHART-01/02 无点可画 | 中 | CHART 风险 2 | 条件式交付:UI 诚实空态 + 文档标注「需配置 auction 源并开启 EOD 竞价同步」;验收用 fixture/mock |
| 4 | **POOL-05 编号冲突**: v2.0 已用 POOL-05 = 历史视图独立端点;v2.1 又标自选联动 | 中 | WATCHLIST 风险 1 | requirements 层统一用 WATCH- 前缀;PROJECT.md 措辞修正 |
| 5 | **Watchlist.tsx 用户未提交改动**: 规划/执行前需确认未改 QK.watchlist 契约或引入第二套自选存储 | 中 | WATCHLIST 风险 2 | 绝不触碰该文件;执行前由 Main 与用户确认 |
| 6 | **回填慢路径成本**: 247 日 × 秒级-数十秒 ≈ 30-120 分钟 [INFERENCE] | 中 | ARCHIVE R2 | 后台 job + 可取消 + 升序摊销 warmup + max_days 限界;过慢再加只读 warmup 复用优化 |
| 7 | **回填快照 = 重算产物非当日冻结**: strategy_version 反映回填时刻 | 中 | ARCHIVE R3 | HIST-02 `snapshot_origin:"backfill"` 显式标注,读侧透传;不做第二份存储 |
| 8 | **窗口行粒度歧义**: 湖内每 symbol 每日可能多行(末行 vs 求和) | 中 | CHART 风险 3 | 默认末行(09:25 最终撮合),随行数/时间窗返回;接入真实源后按源语义钉死 |
| 9 | **盘前 open_gap 缺失**: `compute_enriched_today` 不算 open_gap → 竞价策略盘前静默空池 | 中 | PREMARKET 风险 4 | PM-02 补算(单一实现,勿与 EOD Pass 4 双源漂移);fixture 断言数值 |
| 10 | **盘前 vol_ratio_5d 失真**: `trading_minutes_elapsed=0 → time_factor=1.0` | 中 | PREMARKET 风险 3 | 预览禁用 vol_ratio_5d,优先 auction_volume_ratio(PIT-safe) |
| 11 | **09:25 前 open 为指示价**: 手动提前触发预览数据漂移 | 中 | PREMARKET 风险 2 | 09:26 调度缓解主路径;手动触发须诚实标注「开盘价未定盘」 |
| 12 | **存储量级**: 快照 ~0.3-2 MiB/日 [INFERENCE],247 日 ≈ 79-693 MiB(enriched 湖 51 MiB) | 低-中 | ARCHIVE R4 | 接受;未来膨胀再走 JSON→Parquet/压缩(与 OQ-2 缩放路径一致) |
| 13 | **除权日 prev_close 对齐**: 盘前 open_gap 用原始前收 vs EOD 复权对齐 | 低 | PREMARKET 风险 8 | PM-02 验收覆盖 fixtures;预览标注「基于原始前收」 |
| 14 | **CHART-03 改变 canonical 集**: 扩为「4 必需 + 2 可选」 | 低 | CHART 风险 5 | 向后兼容(源不提供即列缺席);派生列与真实列永不相加(回归) |
| 15 | **交易日历缺失**: 无独立日历,as_of 来源 = enriched 分区 glob | 低 | ARCHIVE R7 | 数据驱动日期集,不引入日历依赖;脏数据日由 freshness 判据兜底 |

## 给 Requirements 定义者的建议

统一编号建议(四领域前缀互斥,避免 POOL-05 式串号):

**HIST-(Phase 24,建议 4 条)**
- **HIST-01** 批量回填 job:用户触发后台回填(enriched 分区 − 快照分区 = 缺口集,幂等跳过已快照日);对每目标日 `run_all_with_hits` + `persist_point_snapshot`;**绝不调 `write_cache`**(AST/grep 守卫锁死);单飞 + 可取消 + 请求内零阻塞;完成后 `/pool/dates` 返回全部缺口日、`/pool/history?as_of=` 均 `available:true`。
- **HIST-02** 快照来源诚实性:`part.json` 增 `snapshot_origin:"eod"|"backfill"`(旧文件默认按 `"eod"` 容错);EOD 写 eod、回填写 backfill、手动 run_all 显式 `"manual"`;读侧至少透传,`strategy_version` = 产生快照时刻的策略集指纹。
- **HIST-03** 存档完整性可见:`/api/pool/dates` 增补 `backfill_needed` 计数与示例;回填进度经既有 job 查询端点可见;端点 GET-only、零执行权、纳入 POOL-03 守卫词汇。
- **HIST-04** 回填护栏与规模化:默认 as_of 升序(摊销 150 天 warmup);`max_days`/`start`/`end` 限界;`job_store` 单飞 + 执行槽互斥(与手动 run_all/EOD 互斥);失败日记录并继续,终态如实反映部分失败;零新增运行时依赖。

**WATCH-(Phase 25,建议 3 条 P1 + 1 条 P2)**
- **WATCH-01** 股池明细行自选星标 + 切换(VIP):`mode==='vip'` 时 `useQuery(QK.watchlist)`;星标 = `watchlistSet.has(row.symbol)` 全等;点击调 `api.watchlistAdd/Remove` + invalidate `QK.watchlist`(+`watchlistEnriched`);guest 不发该查询、不渲染任何控件(无 401、逐像素不变)。
- **WATCH-02** 「只看自选」过滤开关(VIP):与概念子串筛选 AND 组合;命中 0 行 → 诚实空态;对最新/历史视图同样生效(行形状 bit-identical);开关状态存 `storage`(UI 偏好),不落后端;guest 不渲染。
- **WATCH-03** 自选集合一致性与匹配键契约:复用 `QK.watchlist` + `api.watchlistList`(无独立查询键/存储);跨页增删经 react-query 缓存即时反映(非硬刷新);`row.symbol` 全等比较,无模糊匹配;新入口传 symbol 沿用全后缀格式。
- **WATCH-04**(可选/P2)批量加自选:仅对当前策略**可见 rows**(受 display_limit 截断),绝不按未展开 total;复用 `watchlistBatchAdd`;幂等去重;成功 invalidate 同 key。

**PM-(Phase 27 第一档,建议 4 条)**
- **PM-01** 盘前预览 job(调度 + 生成 + 独立存储):工作日 09:26(Asia/Shanghai)触发,`_run_tracked` 单飞 + JobStore;无昨日 enriched / 无 app state → 诚实 skip;写 `premarket_results/date={as_of}/part.json`(`window:"pre_open"`/`computed_at`/`provisional:true`);**断言 `strategy_cache.json` 与 `screener_results/` 在 job 运行后不被改动**。
- **PM-02** 盘前数据帧完整性:每行 `open_gap` 非空且 = open/prev_close−1;竞价列仅在「probe 对今日 available 且源返回今日窗口行」时注入,否则诚实缺列(非 0 填充);09:30+ bar 永不进竞价列(回归锁死);close 派生指标标 provisional。
- **PM-03** probe 盘前语义:盘前探测目标日 = 今日(非 `_last_trade_date`);源不可用/未配置/仅 09:30+ 行 → 降级派生列预览,响应带 probe 判定 + `degraded:true`;绝不静默把 09:30 bar 标为竞价数据。
- **PM-04** 前端盘前视图:查看日 == 今日且预览存在 → 显示预览池 + 「盘前预览·竞价窗口 09:15-09:25·非收盘定稿」标注(`market_phase` 驱动);独立只读端点 + 独立白名单;15:35 EOD 后切回收盘池(`/api/pool/hub` 不变);无预览日 → 200 诚实空态非 404。

**CHART-(Phase 26,建议 3 条 P1 + CHART-04 研究门)**
- **CHART-01** 历史竞价聚合只读 API:`GET /api/kline/auction/history?symbol=&days=`(1..120);数据源 `kline_auction` 视图按 symbol 过滤、按 date 升序;每窗口默认末行(09:25 最终撮合),行数与 min/max datetime 一并返回;响应含 probe 判定 + coverage;空湖 → 200 `{available:false, rows:[]}`;GET-only 零执行权守卫。
- **CHART-02** 历史竞价图前端:`AuctionHistoryChart`(ECharts 柱+线双 y 轴,量=柱/金额=线),挂 `StockPreviewDialog`/`StockPanel` 新 toggle;probe 非 available 或空湖 → 诚实空态文案「无历史竞价数据 · 需配置集合竞价数据源」+ 窗口标注;只画真实量/额,不画/不混排派生列;零新增 npm 依赖;不触碰 Watchlist.tsx。
- **CHART-03** 湖摄入保留委托量输入列(复活 DATA-06):写路径 canonical 集扩为「4 必需 + 2 可选」(源提供时保留 `auction_unmatched_volume`/`auction_virtual_price`);读路径 `compute_auction_unmatched_amount` 分支激活;schema 补「估算」标注;派生列与真实列分列永不相加;不带输入列的分区仍 4 列(向后兼容,回归锁死)。
- **CHART-04**(研究门,不写代码):产出 probe 实测报告——候选源是否在 09:15-09:25 返回含虚拟未匹配/参考价的行;满足则开 phase 实现,不满足则正式 defer 归档,UI 保持诚实空态。

## 置信度评估

| 领域 | 置信度 | 说明 |
|------|--------|------|
| Stack/依赖 | HIGH | 四领域全部结论基于仓库实读代码 + 磁盘实测(`uv.lock` 既有栈,零新增运行时依赖已核实);无新包引入 |
| 逐日存档 (HIST) | HIGH | `pool_snapshot`/`strategy_cache`/`pool_hub`/`daily_pipeline` 逐行核验;唯一估算为回填耗时(30-120 分钟 [INFERENCE])与存储量级(79-693 MiB [INFERENCE]) |
| 自选联动 (WATCH) | HIGH | 纯前端,服务端 watchlist 体系与 Screener 先例全部源码核验;残余项为用户 Watchlist.tsx 未提交改动(执行前确认) |
| 历史竞价图 (CHART) | MEDIUM | 代码 seam 逐行核验(HIGH);但外部实时源可行性与窗口行粒度无法本环境验证(MEDIUM/LOW);空湖条件式交付 |
| 盘前股池 (PM) | MEDIUM-HIGH | 现状结论 HIGH(quote preopen/live 帧、probe、EOD job 全部源码核验);实时竞价源可行性为 [INFERENCE] MEDIUM;第一档可交付,第二档 gate |

**总体置信度:MEDIUM-HIGH。** 除「外部实时竞价源可得性」这一本环境不可验证项外,全部结论均以落地代码与磁盘实测为据;不可验证项已统一按 [INFERENCE] + 判定条件处理,不假装可得。

### Gaps to Address
- **实时竞价源可行性(PM 第二档 + CHART-04):** 规划/执行时保持 fail-closed;PM 默认第一档,CHART-04 只做研究门。判定条件已写入上文。
- **POOL-05 编号:** REQUIREMENTS 定义时统一 WATCH-/HIST-/PM-/CHART- 前缀,修订 PROJECT.md 的「POOL-05 自选股联动」措辞。
- **手动 run_all 历史 as_of 写 cache(`api/screener.py:445`):** 是否在本里程碑一并修复(「非最新日不写 cache」)需 roadmap 决策;至少文档化。
- **Watchlist.tsx 用户未提交改动:** Phase 25 规划前由 Main 与用户确认 QK.watchlist 契约未变。
- **snapshot_origin schema 演进:** HIST-02 需定 schema_version 递增 vs 向后兼容容错策略,规划时细化。
- **回填触发方式与默认边界(ARCHIVE R6):** 手动端点 vs 空闲自动、全量 vs 最近 N 日——requirements 定义时与用户确认。
- **PM 调度时间:** 09:26 需与既有 `pre_market_instruments`(09:10)与 quote 轮询并发协调;`compute_enriched_today` 补算 open_gap 的单点实现防双源漂移。
- **CHART 窗口行粒度:** 在 CHART-01 验收中把「末行」语义写死,标注待真实源验证;若源是逐分钟累计快照则末行=最终撮合。

## Sources

### 领域研究(本里程碑,全部为仓库实读代码 + 磁盘实测)
- **ARCHIVE.md** — `backend/app/services/pool_snapshot.py`、`strategy_cache.py`、`pool_hub.py`、`screener.py`、`api/pool.py`、`api/screener.py`、`jobs/daily_pipeline.py`、`pipeline_jobs.py`、`extend_history.py`;磁盘实测 `kline_daily_enriched/` 247 分区、`screener_results/` 0 快照
- **WATCHLIST.md** — `backend/app/services/watchlist.py`、`api/watchlist.py`、`api/pool.py`、`services/pool_hub.py`、`services/guest_masking.py`、`main.py:776-847`、`tests/test_pool_hub.py:788-833`、`tests/test_guest_masking.py`;`frontend/src/pages/Screener.tsx:429-447`、`lib/queryKeys.ts`、`lib/storage.ts`
- **PREMARKET.md** — `jobs/daily_pipeline.py:1-6,962-1085`、`services/screener.py:245-297,723-812`、`indicators/pipeline.py:36-67,1250-1540`、`services/quote_service.py:1099-1157,1459-1563`、`services/auction_sync.py`、`services/auction_columns.py:89-150`、`services/auction_probe.py`、`data_providers/base.py:25-26`、`frontend/.../StockListTable.tsx:72-122`
- **CHART.md** — `services/auction_sync.py:32-35,128-133`、`services/auction_columns.py:35-51,89-150`、`services/auction_probe.py`、`data_providers/custom/provider.py:150-160`、`data_providers/tencent_provider.py`、`repository.py:162-163`、`api/data.py:489-502,626-650,769-774`、`frontend/package.json`(echarts/lightweight-charts)

### 规划文档(交叉核验编号与决策)
- `.planning/STATE.md`(Deferred Items 四项)、`.planning/PROJECT.md`(v2.1 目标与「POOL-05 自选股联动」措辞)、`.planning/milestones/v2.0-REQUIREMENTS.md`(POOL-05 = 历史视图独立端点)、`v2.0-ROADMAP.md`(Phase 20-23 与顺序编号)、`v2.0-MILESTONE-AUDIT.md`(OQ-1 有意决策)、`milestones/v2.0-phases/22-pool-date-navigation/22-RESEARCH.md`(RQ2/A5 backfill_needed、RQ3/OQ-1)

---
*研究合成完成:2026-08-06*
*Ready for roadmap: yes*
