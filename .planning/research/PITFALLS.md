# Pitfalls Research

**Domain:** A股量化研究平台 v2.0「竞价深度与历史股池」— 历史股池日期导航 (POOL-04) + 竞价策略族扩展 (STRAT-04/05) + 真集合竞价数据列 (DATA-04/05)
**Researched:** 2026-08-04
**Confidence:** HIGH（基于 v1.3 落地代码逐条核验：pool_hub / strategy_cache / auction_probe / engine / free_stockdb_provider）

## Critical Pitfalls

### 一、历史股池日期导航 (POOL-04)

### Pitfall 1: 用「今日 ever 并集」冒充点时刻股池快照

**What goes wrong:**
日期导航上线后，用户选择历史交易日 D，看到的是"当天曾命中的并集"而非"D 日某个时刻的真实股池"。卡片计数与明细与当时的实际情况不符。

**Why it happens:**
`strategy_cache.write_cache` 的单日期合并语义是 **union**：同一天内多次 run_all 会把 `today_ever_rows` 做并集（`combined = {**old_map, **cur_map}`，注释明确写着"合并曾命中集合"）。也就是说 `strategy_cache.json` 里同一 as_of 的结果是**当日多次运行的累计并集**，不是任何单一时刻的点快照。POOL-04 若直接把缓存 JSON 按日期归档，就归档了 union，而非当天 09:30 / 盘后 15:00 的真实池子。

**How to avoid:**
POOL-04 必须引入**冻结式点快照**：在固定时刻（如每日盘后 run_all 完成后）把 `results` 原样序列化到 `screener_results/date={as_of}/` 或等价的新归档目录，快照携带 `as_of` + `computed_at` + 策略版本指纹，永不回填/追加。归档只落"当次计算的行集"，绝不落 `today_ever_rows`。若必须提供"盘中曾命中"视图，把它作为一个**独立语义字段**（ever_matched）展示，与点快照分开。

**Warning signs:**
- 快照文件里出现 `today_ever_matched` / `today_ever_rows` 字段或代码路径复用 `write_cache` 的合并分支
- 同一 as_of 两次浏览（如 10:00 与 14:00）返回不同 total，且没有 computed_at 区分
- 归档目录里每个日期只有一份文件，但策略行数随当天重跑次数增长

**Phase to address:** 日期导航阶段（POOL-04）。必须在数据持久化设计时就区分"点快照"与"当日并集"，否则归档格式定错后难以迁移。

---

### Pitfall 2: 回放滚动重算 — 用"现在"的数据重算"过去"的股池 (non-PIT)

**What goes wrong:**
浏览历史日期 D 时，策略用**今天**已修正/已复权的数据或 D 之后的数据重算，导致同一 as_of 在不同日期回看得到不同成员（历史上"当时看不到"的股票出现在"当时"的池子里）。

**Why it happens:**
- 日 K 层存在盘中/盘后刷新与复权因子（adj_factor）更新；若 D 的 `kline_daily_enriched/date=D` 分区被后来数据修正，重算 D 的 `open_gap` 就会变。
- 策略使用 `change_pct`（当日收盘 vs 前收）：盘前 09:30 尚未收盘，`change_pct` 不可知。若"盘前策略"用了 `change_pct`，要么拿不到数据，要么拿到的是**未来**（当天收盘后的值）——这是最典型的 lookahead。
- `vol_ratio_5d` 标准量比分母是"前 5 日均量（不含当天）"（`volume.shift(1).rolling_mean(5)`），本身 PIT 安全；但若回放时把 `volume.shift(1)` 的窗口错接到 D 之后的数据，同样污染。
- 概念板块（concept_board）来自 ext 配置：板块成员是**当下**快照，回放 D 日股池时用今天的板块归属标注 D 日股票，是向后漂移。

**How to avoid:**
日期导航的每次回放都走**点时刻加载**：只读 `date <= D` 的分区，历史窗口加载器 `_load_enriched_history(D, lookback)` 已按 `target_date` 前推——回放必须复用同一 PIT 语义并加回归锁。归档快照直接存**行集**（不存重算所需全部上游），浏览历史时只投影归档行，不重跑策略；如需重跑，必须冻结上游分区（sha256 指纹）并记录策略/因子版本。概念归属要么随快照冻结，要么在 UI 明确标注"当前板块归属"。

**Warning signs:**
- 回放路径调用了 `svc.latest_date()` 或任何"取最新"的加载器
- 策略 filter 里出现 `change_pct` / `close` 且被标为"盘前/09:30 可用"
- 同一 as_of 的归档快照能随上游 parquet 的 mtime 变化而改变内容（说明没有真正冻结）
- 回放代码里出现 `pl.col("volume").shift(...)` 但窗口边界没有按 D 截断

**Phase to address:** 日期导航阶段（POOL-04）优先；但 STRAT-04/05 阶段就要立规（见 Pitfall 7），否则回放时策略集本身就不 PIT。

---

### Pitfall 3: 交易日/自然日分区歧义 — 无交易日历的日期导航

**What goes wrong:**
用户选 2026-08-02（周日）或 2026-08-04 之后的"今天"，后端要么返回空池、要么静默跳到相邻交易日、要么报 404，前端日期选择器列出的日期与后端实际可用的 as_of 不一致。

**Why it happens:**
A股有节假日与调休，enriched 分区只存在于**交易日**（Phase 13 实测一年 241 个交易日，春节月仅 14 个）。日 K 分区 `date={D}`、分钟 K 分区 `date={D}`、竞价窗口行落在**同一日期分区**里——但自然日≠交易日。若日期导航用 `date` 参数直接查分区而不先经交易日历解析，"非交易日"会 miss；若实现方图省事用"前向/后向最近分区"的启发式，又会把用户选的日期静默改掉，破坏诚实性。

**How to avoid:**
引入**交易日历**（Phase 13 已实测 A股日历，可复用该测量方法）：`as_of → 最近的 <= 该日交易日` 的解析做成显式服务，解析结果（请求日期 vs 实际 as_of）在响应里**如实回显**，不允许静默改日。日期选择器的可选集合 = 实际存在归档快照的交易日集合（来自分区目录，而非臆测）。非交易日请求返回明确状态（如 `as_of` 为空 + 原因），而不是空池冒充有数据。

**Warning signs:**
- 前端日期下拉是连续自然日，后端实际只有交易日分区
- `build_pool_hub` 类逻辑出现 `min(latest, requested)` 或 `<=` 最近匹配的隐式跳日
- 没有独立的 `trading_calendar` / `resolve_trading_day` 服务，全靠分区探测

**Phase to address:** 日期导航阶段（POOL-04）。交易日历应在数据层（与竞价数据层相邻）先落地。

---

### Pitfall 4: 陈缓存被误标为当前 as_of（read_cache 已移除 mtime 校验）

**What goes wrong:**
日期导航的"最新"入口把一份好几天前的缓存当作"当前股池"展示，页面标题写 today 或 latest，实际行集是旧交易日 D。

**Why it happens:**
`strategy_cache.read_cache` **有意移除了** enriched mtime 过期校验（注释明确：实时行情会刷新 parquet → mtime 必然变 → 缓存被永久判死，故改为总是读缓存 + `/cached` 端点叠加监控内存结果）。这使单文件缓存可能长期停留在旧 as_of。POOL-04 若沿袭"读 `user_data/strategy_cache.json` 并显示其 as_of"的模式，就会把历史遗留缓存当最新。

**How to avoid:**
最新视图必须与服务端权威 `as_of` 对齐：`svc.latest_date()` 与 `strategy_cache` 的 `as_of` 不一致时，以 `latest_date()` 为最新日期，缓存日期仅在**完全一致**时被采纳（这正是 v1.3 `resolved_as_of = as_of if (as_of == cache_as_of) else cache_as_of` 的反漂移契约——日期导航必须延续，不能为了"能看旧数据"而破坏它）。历史浏览走归档快照目录，永远不把单文件缓存当历史数据源。

**Warning signs:**
- `GET /api/pool/hub` 的 `as_of` 与 `GET /api/screener/latest` 或 `svc.latest_date()` 长期不一致
- 历史归档与"最新"共用同一个 `strategy_cache.json` 文件
- 前端把响应里 `as_of` 字段忽略，用自己本地时间当标题

**Phase to address:** 日期导航阶段（POOL-04）的"最新 vs 历史"边界；验收时必须有"缓存陈旧仍正确回显缓存日期"的回归测试。

---

### Pitfall 5: 破坏当前 single-as_of 契约（pool_hub 回归守卫）

**What goes wrong:**
为支持日期导航，改动 `build_pool_hub` / `GET /api/pool/hub` 签名或缓存写入路径，导致 v1.3 已锁定的 single-as_of 反漂移契约失效：卡片 total 与明细 rows 来自不同日期、`total` 不再是权威全量、或客户端能传入任意日期伪造数据源。

**Why it happens:**
POOL-01/02/03 的核心保证是"单一 as_of 源 + 卡片与明细同一次读取 + 概念筛选只收窄 rows"。POOL-04 最容易犯的错是**原地扩写**现有端点（加 `date` 参数后按需重算或返回多日期混合），而不是**新增独立的日期导航端点/服务**。此外 `tests/test_pool_hub.py` 的 POOL-03 AST 守卫只禁止 mutating 路由；新增"按日期重算并写缓存"的路由不会触发 AST 守卫，但会在语义上破坏单一数据源。

**How to avoid:**
- 日期导航走**新端点/新服务**（如 `GET /api/pool/hub/history?date=D` 或 `GET /api/pool/dates`），只读归档快照，**不写** `strategy_cache.json`、不触发重算。
- 现有 `GET /api/pool/hub`（最新视图）保持原契约不动，`as_of` 请求参数的回显规则（不一致时回显缓存日期）保留，并为其补回归测试锁定。
- 归档快照的投影复用同一 `build_pool_hub` 纯函数（数据源参数化），保证 total/rows/概念筛选语义一致。
- 任何新路由保持只读；POOL-03 AST 守卫扩展覆盖新路由（禁止写库/重算副作用）。

**Warning signs:**
- `pool.py` 新增了带副作用的路由（调用 `write_cache`、触发 run_all）
- `GET /api/pool/hub` 的行为因为日期导航需求被改（签名、回显规则、total 语义）
- 前端日期导航复用了 `/api/pool/hub` 而不是独立端点

**Phase to address:** 日期导航阶段（POOL-04）。这是 v1.3→v2 最脆弱的接口边界，应列为该阶段的显式验收项。

---

### 二、更多竞价策略 (STRAT-04/05)

### Pitfall 6: 策略名暗示公开因子定义（产品标签 vs 第一性原理）

**What goes wrong:**
「竞价阿尔法 / 极速抢筹 / T+1闪电 / 竞价全面策略 / 金色两点半」在界面上出现，用户按名称理解成某个公开/收费策略配方，实际实现是第一性原理自定义因子——名字与内容不符，研究结论失去可信度。

**Why it happens:**
参考 UI 里的这些名称是**产品标签**，无公开规格（v1.3 STRAT-01 已明确"reference names are product labels, not public specs"，并把 陈星量化 排除出可复制范围）。v2 若沿袭"照名复刻"，会陷入两种错误：要么名字像、因子随意凑；要么为了"对得上名字"生造参数。同时 `docs/features.md` 与源码已存在计数漂移（v1.3 记录：文档写 20 个、源码 18 个），再加 5 个策略会继续恶化。

**How to avoid:**
延续 STRAT-01 的纪律：每个新策略以 `strategy/builtin/*.py` 落地，META 里写**第一性原理**的描述（用哪些因子、阈值、权重、何时可计算），名称与描述诚实对应；不声明与任何专有配方的等同关系。策略清单/计数在同一里程碑内与 `docs/features.md` 对账。

**Warning signs:**
- 新策略的 `description` 出现"对标 XX""复刻 XX 策略"字样
- META `name` 含品牌/收费策略名但 `description` 不含因子定义
- 提交里没有同步更新策略计数文档

**Phase to address:** 竞价策略族阶段（STRAT-04/05）。命名与文档纪律应在第一批新策略提交时就锁定。

---

### Pitfall 7: 未来 bar 回看 (lookahead) — STRAT-05 盘中确认与盘前可用性

**What goes wrong:**
09:30–10:00 盘中确认策略把 10:00 之后的分钟 bar 算进"当前确认"；盘前策略用了当日收盘类字段；T+1 类策略用未来日期的数据做信号。结果股池包含"当时拿不到"的标的，回测虚高、实盘不可复现。

**Why it happens:**
- `change_pct`（当日收盘 vs 前收）在 09:30 开盘时**不可知**。现有 `auction_bullish` 的 scoring/filter 用了 `change_pct`——它只在**盘后**成立。若 STRAT-04/05 在盘前/盘中复用该因子即 lookahead。
- STRAT-05"盘中确认"读 `kline_minute`，但分钟 K 的 `_bucket_minutes` 把 09:30 起的 bar 聚合到会话桶；若确认逻辑用"截至当前时间"之外的窗口（如整个上午桶）就会引入未来。
- 日内实时路径的 `vol_ratio_5d` 需要 `time_factor` 折算（`volume * time_factor / vol_ma5_prev`），盘中未折算就直接除以全天 5 日均量，量比被系统性低估/高估。

**How to avoid:**
- 为每个新策略声明**可计算时间窗**：`pre_open`（仅 open_gap/竞价量类，09:15–09:25）、`intraday`（09:30–10:00，仅分钟 bar ≤ 评估时刻 + 时点折算）、`post_close`（可含 change_pct）。策略 META 记录该窗口，引擎按窗口校验字段可用性。
- STRAT-05 的确认逻辑显式按 `evaluation_time` 截断分钟帧（`df.filter(pl.col("datetime") <= eval_time)`），并加"确认时刻之后无输入"的测试。
- 复用 v1.2 Factor DSL 的 no-lookahead 门禁思路：对每个新策略做一次"IC 在 shifted-label 下塌缩"或"用截至 T 的数据重算 == 当时结果"的回归。

**Warning signs:**
- 策略 filter/scoring 引用 `change_pct` 但 META 标称盘前/盘中
- STRAT-05 读取分钟帧后没有 `<= eval_time` 过滤
- 回放/回测中同一策略在不同"当前时间"得到不同结果（说明有未来输入）
- 日内量比代码里没有 `time_factor` 折算

**Phase to address:** 竞价策略族阶段（STRAT-04/05）。窗口声明与分钟截断是硬验收项；DATA-05（盘前可用性）阶段要复用同一窗口框架。

---

### Pitfall 8: 把 09:30 连续竞价 bar 当作集合竞价数据

**What goes wrong:**
新策略或新数据列把 09:30 起的连续竞价分钟 bar（或日 K open）标成"竞价量/竞价强度"，用户据此做盘前决策，实际用的是开盘后数据。

**Why it happens:**
分钟 K 的 09:30 是**连续竞价起点**，不是集合竞价成交：`_minute_ts` 把当日起点锚定到 `093000`，`_bucket_minutes` **丢弃** 09:25/09:29 等盘前 bar（回归测试 `test_minute_timestamp_convention` 锁定），因此分钟层**结构上没有** 9:15–9:25 数据。真集合竞价窗口是 `[09:15:00, 09:25:59]`，只有 probe 判定 `available` 且时间戳落在窗口内才是。v2 扩策略时最容易图省事：把 09:30 分钟 bar 的 volume 当"竞价量"喂给策略。

**How to avoid:**
延续 DATA-03/T-16-01 诚实规则并扩到**策略消费端**：策略若声明使用集合竞价数据，只能消费 `get_auction()` 的 canonical 列（`symbol, datetime, auction_volume, auction_amount`，provider 层已裁剪窗口）；09:30 分钟 bar 永不进竞价因子。给每个"竞价"策略加一条回归：输入只有 09:30+ bar 时策略必须 fail-closed 空或明确标 derived，绝不产出被标记为竞价的行。

**Warning signs:**
- 策略 filter 里直接读 `kline_minute` 的 volume 且注释/描述含"竞价"
- 09:30 bar 出现在竞价因子的依赖列里
- UI 上 09:30 行的标签出现"集合竞价"

**Phase to address:** 竞价数据层阶段（DATA-04/05）定义列语义，竞价策略族阶段（STRAT-04/05）在消费端强制执行。

---

### Pitfall 9: 评分权重和 != 1.0 / 缺失评分列导致分数失真

**What goes wrong:**
新策略的 `scoring` 权重和不是 1.0，或引用了 enriched 帧里不存在的列，导致 score 任意化、排序失真、跨策略不可比；个别策略静默产出空结果。

**Why it happens:**
`engine._apply_scoring` 会按 `w = weight / total_weight` 归一化（权重和不等于 1.0 时引擎会兜底），但**缺失列被静默跳过**（`if col not in df.columns: continue`），且 `total_weight <= 0` 时直接返回 df（**无 score 列**）→ 排序退回 `order_by` 或不变。新策略若有 5+ 因子，其中一个拼错列名或权重和写了 0，不会报错，只是分数悄悄变差/排序失效。

**How to avoid:**
- 新策略的 `scoring` 全部走既有 `strong_open.py` / `auction_*` 模式：权重显式、和为 1.0、每个列都在 enriched 列集中（对齐 `indicators/pipeline.py` 的列白名单）。
- 增加**策略自检**：加载时校验 scoring 列存在性 + 权重和 > 0，不符合的在 `load_errors` 里可见（现有机制已暴露 load 错误，扩展校验即可），而不是静默跳过。
- 为每个新策略写一条 fixture 测试：已知输入 → 确定 score 排序。

**Warning signs:**
- 新策略 `scoring` 键有拼写错误（如 `vol_ratio` 而非 `vol_ratio_5d`）
- 策略结果 `score` 列缺失或全部相等
- 日志出现"missing scoring column"类静默跳过但无警告

**Phase to address:** 竞价策略族阶段（STRAT-04/05）。策略加载自检应作为该阶段的工程质量项。

---

### 三、真集合竞价数据列 (DATA-04/05)

### Pitfall 10: 声称"真集合竞价"实为派生/延迟数据

**What goes wrong:**
平台把派生数据（open_gap、09:30 bar 的 volume、盘后拿到的当日总成交）或延迟数据包装成 9:15–9:25 集合竞价成交列，用户以为在看真实竞价匹配，实则是估计值。

**Why it happens:**
真集合竞价匹配数据（竞价量/金额/虚拟成交）需要数据源在 9:15–9:25 返回**窗口内时间戳**的行。免费源（stockdb 等）通常没有；`get_auction` 是 probe-gated 的 canonical 路径。v2 若在 probe 未确认 `available` 时就硬造列（把 09:30 分钟 bar 的 volume 映射为 `auction_volume`，或把当日量按比例折算"虚拟竞价量"），就破坏了 DATA-03 的诚实契约。

**How to avoid:**
- 真集合竞价列只出现在 probe `available` 且数据来自 `get_auction` canonical 列时；列名与 `auction_volume` / `auction_amount` 一一对应。
- probe 未 `available` 时，界面/API 只提供**明确标注派生**的列（如 `open_gap`），列描述写"派生（open/prev_close−1）"，绝不标注为集合竞价。
- "虚拟成交/虚拟匹配"若实现，必须显式命名（如 `auction_virtual_fill`）并声明是估算，不与真实 `auction_volume` 混排。
- 数据质量注解沿用 v1.3 纪律：宁可空列也不填近似值。

**Warning signs:**
- `auction_volume` 的数值与当日 09:30 分钟 bar 的 volume 相等（说明是复制的）
- 列注释/UI 描述出现"估算"但列名不带虚拟/派生前缀
- probe 状态不是 `available` 但 API 仍返回竞价列

**Phase to address:** 竞价数据层阶段（DATA-04/05）。列准入以 probe 判定为唯一闸门。

---

### Pitfall 11: probe 判不可用时静默 fail-open

**What goes wrong:**
probe 判定 `not_configured / fail_closed / error` 时，新代码仍把竞价列当可用处理（返回非空值、默认派生列被标为竞价、或前端不展示 probe 状态），用户看到的竞价数据实际是假的，且没有任何可见警告。

**Why it happens:**
DATA-03 的 fail-closed 词汇是服务端权威的（`AuctionProbeVerdict.status`），前端只渲染服务端状态。v2 在新增竞价列消费路径时最容易在**服务层**绕过 probe 判定：读不到 `auction` 数据集就回退到 09:30 bar / 派生值但**不改变状态标识**，前端于是继续渲染成"竞价可用"。

**How to avoid:**
- 竞价列的**生产路径**以 probe 判定为前置：非 `available` 时列值为 null/缺列，状态标识保持 probe 原值（`not_configured` 等）。
- 任何回退都必须是**显式 fail-closed**：回退到 `open_gap` 时状态与 UI 文案沿用 `FAIL_CLOSED_DETAIL` 原样，绝不静默。
- 新增一个回归测试：probe 四种状态 × 竞价列返回，断言"非 available 时竞价列永不为非空"。
- error 状态只透出截断异常（沿 `_ERROR_DETAIL_MAX=200` 防信息泄露），不允许把 error 当可用。

**Warning signs:**
- 代码路径里 `resolve_auction_probe` 的返回值没有被 switch 分发，而是被当作"尽力而为"
- UI 竞价列有值但 probe 面板显示 fail_closed/error
- 新增测试里没有覆盖 probe 状态 × 列返回的矩阵

**Phase to address:** 竞价数据层阶段（DATA-04/05）。

---

### Pitfall 12: 列身份/单位歧义（手 vs 股 vs 元，虚拟 vs 真实）

**What goes wrong:**
竞价量/金额在不同源或不同列间单位不一致（手 vs 股 vs 元 vs 万元），下游因子（量比、竞价强度、金额占比）全部失真；用户把"虚拟成交"当成真实成交量做决策。

**Why it happens:**
A股成交量惯例存在**手（100 股）与股**两种口径，金额存在**元与万元**两种口径；不同 provider 返回不同单位。`get_auction` canonical 列已固定列名（`auction_volume` / `auction_amount`），但**列上不携带单位元数据**；v2 若再加 `虚拟成交` 列，极容易把估算值与非估算值混入同一单位体系。

**How to avoid:**
- 定义**canonical 单位**：`auction_volume` = 股，`auction_amount` = 元，并在列 schema/文档/UI 表头**显式标注单位**（沿用 evidence 层 `unit` 字段的既有惯例：`unit: "shares" / "CNY"`）。
- provider 归一化在 `get_auction` 边界完成（转股/转元），越界后只认 canonical 单位；新源接入时必须做单位换算并记录 source 原始单位。
- `虚拟成交`（虚拟匹配量）独立命名（`auction_virtual_fill`），列描述声明"估算，非真实成交"，永远不与 `auction_volume` 相加或比较。
- 加一条 fixture 测试锁定单位换算（如 1 手 = 100 股）与列名稳定性。

**Warning signs:**
- 两个 provider 的 `auction_volume` 数量级差 ~100 倍（手/股混用）
- UI 表头没有单位标注，或 `auction_amount` 数值看起来像"万"级
- `虚拟成交` 与 `auction_volume` 在同一公式里直接相加

**Phase to address:** 竞价数据层阶段（DATA-04/05）。单位契约在 canonical 列定义时锁定，策略族阶段消费方不感知单位差异。

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| 日期导航直接复用 `strategy_cache.json`，加 `date` 字段区分 | 零新存储，改动最小 | 单文件缓存被 union 语义污染，历史≠点快照，漂移回归 | never — 点快照归档是 POOL-04 的地基 |
| 在 `GET /api/pool/hub` 上原地加日期参数 | 前端改动小 | 破坏 v1.3 锁定的 single-as_of 契约与回归测试 | never — 用独立只读端点 |
| probe 不可用时把 09:30 bar 的 volume 当竞价量 | 立刻有"数据" | 破坏诚实性契约，研究结论误导 | never |
| 新策略跳过 META 时间窗声明 | 写文件快 | 回放/回测 lookahead，不可复现 | never — 窗口是 PIT 前提 |
| 竞价列先填值、单位后续补 | 先看到数字 | 单位混用污染所有下游因子 | 仅内部实验阶段，进入 governed 列前必须归一化 |
| 用自然日连续列表当日期导航 | 不用写交易日历 | 非交易日空池/静默跳日 | never — 交易日历是数据层一部分 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `strategy_cache`（单文件缓存） | 把 union 后的 `today_ever_rows` 当历史快照归档 | 归档只落当次 `results` 行集，`computed_at` 冻结 |
| `resolve_auction_probe`（probe 判定） | 非 `available` 仍返回竞价列，或回退不更新状态 | 非 available → 列 null/缺列 + 状态标识保持 probe 原值 |
| `get_auction` canonical 列 | 直接消费未归一化的 provider 原始单位 | 在 provider 边界转 canonical 单位并记录 source 单位 |
| `kline_minute`（分钟 K） | 把 09:30 bar 当竞价数据喂策略 | 只有 `get_auction` 窗口内行是竞价；09:30+ 永不是 |
| `_load_enriched_history`（历史窗口） | 回放时窗口未按 D 截断 / 复用 `latest_date` | 只读 `<= D` 分区，窗口加载器按 target_date 前推 |
| `docs/features.md` 策略计数 | 加 5 个策略不更新文档 | 同一里程碑内对账，消除 20 vs 18 类漂移 |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| 日期导航每次请求**重算**历史日股池 | 浏览历史日期响应秒级→十秒级，并发卡死 | 只投影归档快照；重算走显式离线任务 | > 数十个历史日并发浏览 |
| 归档快照全量复制完整行集（含全部列） | `screener_results/` 体积线性膨胀，data 页统计变慢 | 快照只存投影所需列（symbol/open_gap/change_pct/concept/hit_factors） | 数百交易日 × 全市场 |
| 盘前/盘中策略全市场拉 `kline_minute` | 分钟读取放大 I/O | 沿用 `minute_sync_symbols` scope 旋钮，限制到策略池 | 全市场分钟扫描 |
| 竞价列探针每请求都跑 | 每次打开数据页都拉一次源 | probe 结果缓存 + 过期（如 60s）+ 服务端权威状态 | 高并发访问 Data 页 |
| 概念板块映射每个 hub 请求重建 | 响应延迟随 ext 配置数量上升 | 复用既有 ext 读取 seam + 进程级缓存（同 v1.3） | 多 ext 源 |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| 日期导航新路由引入写路径（重算写缓存/写归档） | 突破 POOL-03 零执行边界；AST 守卫未覆盖新路由 | 新路由保持只读；扩展 POOL-03 AST 守卫到全部 `/api/pool/*` |
| probe error 详情透出完整异常 | 数据源内部地址/凭据泄露 | 沿用 `_ERROR_DETAIL_MAX` 截断，只透出前 200 字符 |
| 历史快照暴露未脱敏字段 | guest 会话经日期导航读到代码/名称明文 | 归档快照同样走 `mask_guest_hub` 服务端脱敏（GUEST-01 扩展） |
| 客户端日期参数注入遍历任意分区 | 读取越界日期/探测目录结构 | 服务端解析为交易日并校验存在性，非交易日 fail-closed |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| 日期导航选非交易日得到空池 | 用户以为数据丢了 | 交易日历禁用非交易日 + 服务端回显"最近交易日"并明确标注 |
| 竞价列与派生列混排无标注 | 用户把 open_gap 当竞价量 | 表头/列标签区分"集合竞价(真)"与"派生(open_gap)" |
| "最新"视图长期停在旧 as_of | 用户对着旧股池做决策 | 显示缓存 `as_of` 日期 + 与 `latest_date()` 不一致时的提示 |
| 盘前策略在 09:30 前返回空池无解释 | 用户困惑"策略坏了" | 展示 probe/窗口状态（未到可计算时间窗） |
| 虚拟成交与真实成交同列比较 | 用户误读盘前强度 | 虚拟成交独立列 + 估算标注，不与 `auction_volume` 同公式 |

## "Looks Done But Isn't" Checklist

- [ ] **日期导航:** 归档的是点快照而非 `today_ever_rows` union — 验证归档文件里**没有** `today_ever_matched` 字段，且同一 as_of 多次浏览 total 稳定
- [ ] **日期导航:** 新端点不写 `strategy_cache.json`、不触发 run_all — 验证 `/api/pool/hub` 原契约回归测试仍绿
- [ ] **日期导航:** 非交易日 fail-closed（返回明确状态，非空池/非静默跳日）— 验证周日/春节请求
- [ ] **竞价策略:** 每个新策略 META 有可计算时间窗声明，`change_pct` 类字段只在 post_close 策略出现 — 验证"盘前/盘中"策略的字段白名单
- [ ] **竞价策略:** 策略评分列都在 enriched 列集内、权重和 > 0 — 验证 `load_errors` 无 scoring 告警
- [ ] **真竞价列:** 非 `available` 时 `auction_volume/amount` 永为 null/缺列 — 验证 probe 状态 × 列返回矩阵测试
- [ ] **真竞价列:** 单位 canonical（股/元）+ 表头标注 + `虚拟成交` 独立命名 — 验证 fixture 单位换算测试
- [ ] **全量:** `docs/features.md` 策略计数已对账（21 内置 + 新 5）

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| 归档存了 union 而非点快照 | HIGH（历史不可重建） | 立即冻结归档格式；从当日盘后 run_all 结果重新生成点快照；删除已污染的 union 归档并告知用户 |
| 回放 lookahead 污染历史池 | HIGH（研究结论不可信） | 定位污染因子（change_pct 等），用 PIT 重跑；对受影响日期打"重算"标记并保留旧快照审计 |
| 竞价列被标成真数据 | MEDIUM | 按 probe 状态重标列 + UI 标注；对已消费数据的策略重算并披露 |
| 单位混用 | MEDIUM | 在 canonical 边界统一换算，记录 source 单位；重算受影响因子 |
| 非交易日空池 | LOW | 补交易日历 + 前端禁用；对已发生的错误显示补提示 |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| #1 union 冒充点快照 | POOL-04（日期导航） | 归档文件无 `today_ever_matched`，同 as_of 多次浏览 total 稳定 |
| #2 回放滚动重算（non-PIT） | POOL-04 + STRAT-04/05 窗口规约 | 回放只读 `<=D` 分区；change_pct 只在 post_close 策略 |
| #3 交易日/自然日歧义 | POOL-04（交易日历在数据层落地） | 非交易日 fail-closed 回归 |
| #4 陈缓存误标最新 | POOL-04 | `latest_date()` vs 缓存 as_of 不一致时回显缓存日期的测试 |
| #5 破坏 single-as_of 契约 | POOL-04 | v1.3 `test_pool_hub.py` 全绿 + 新端点 AST 只读守卫 |
| #6 命名暗示公开配方 | STRAT-04/05 | 策略 META 描述含第一性原理因子定义；文档计数对账 |
| #7 未来 bar 回看 | STRAT-04/05（DATA-05 复用） | STRAT-05 分钟帧 `<= eval_time` 截断测试 + 字段窗口白名单 |
| #8 09:30 bar 当竞价数据 | DATA-04/05 定义 + STRAT-04/05 消费端 | 09:30+ 输入 → 策略 fail-closed 空/derived 回归 |
| #9 权重和/缺失评分列 | STRAT-04/05 | 策略加载自检：scoring 列存在 + 权重和 > 0 |
| #10 派生/延迟冒充真竞价 | DATA-04/05 | probe available 才出列；列名 canonical |
| #11 静默 fail-open | DATA-04/05 | probe 状态 × 竞价列返回矩阵测试 |
| #12 单位/身份歧义 | DATA-04/05 | canonical 单位 fixture 换算测试 + 表头标注 |

## Sources

- 代码核验（HIGH）：`backend/app/services/pool_hub.py`（single-as_of 契约、`resolved_as_of` 回显、概念投影）
- 代码核验（HIGH）：`backend/app/services/strategy_cache.py`（单文件缓存、`today_ever_rows` union 合并、read_cache 移除 mtime 校验的注释）
- 代码核验（HIGH）：`backend/app/services/auction_probe.py` + `tests/test_auction_probe.py`（[09:15,09:25] 窗口诚实规则、fail-closed 词汇、T-16-01 09:30 永不 available）
- 代码核验（HIGH）：`backend/app/strategy/engine.py` `_apply_scoring`（权重归一化、缺失列静默跳过、total<=0 无 score）
- 代码核验（HIGH）：`backend/app/data_providers/free_stockdb_provider.py` `_minute_ts`/`_bucket_minutes` + `tests/test_minute_timestamp_convention.py`（09:30 锚定、盘前 bar 丢弃）
- 代码核验（HIGH）：`backend/app/data_providers/custom/provider.py` `get_auction`（canonical 列 `auction_volume/auction_amount`、窗口裁剪）
- 代码核验（MEDIUM）：`backend/app/strategy/builtin/auction_bullish.py` 等（`change_pct` 用于盘后；`vol_ratio_5d` 前 5 日均量分母 PIT 安全）
- 代码核验（MEDIUM）：`backend/app/api/screener.py` run_all（单缓存写入、`latest_date` 兜底）
- v1.3 研究衔接（MEDIUM）：`.planning/research/v1.3-auction/PITFALLS.md`（#10 单一 as_of、#6 open-gap lookahead、#4 命名、#7 权重和、#2 免费源稳定性）
- 需求来源（HIGH）：`.planning/REQUIREMENTS.md`（DATA-04/05、STRAT-04/05、POOL-04 定义与 Out of Scope）
- 领域惯例（MEDIUM）：A股成交单位（手/股）与金额单位（元/万元）存在多口径；竞价虚拟匹配属估算值

---
*Pitfalls research for: AthenaQuant v2.0 竞价深度与历史股池*
*Researched: 2026-08-04*
