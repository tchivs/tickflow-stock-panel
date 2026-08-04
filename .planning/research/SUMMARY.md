# Research Summary

**Project:** AthenaQuant
**Milestone:** v2.0 竞价深度与历史股池 (POOL-04 / STRAT-04·05 / DATA-04·05)
**Domain:** A股集合竞价选股引擎深化 — 按交易日浏览历史股池、竞价策略族扩展、真集合竞价数据列
**Researched:** 2026-08-04
**Confidence:** HIGH (栈/架构/陷阱均以 v1.3 落地代码逐条核验); DATA-04 数据源可用性为 MEDIUM (probe 门控, 取决于探测结果)

## Executive Summary

AthenaQuant v2.0 是在 v1.3 已锁定的 A股量化研究平台（单容器、data-lake-first、研究建议零执行权）之上深化集合竞价选股。用户（短线打板/复盘文化，参照开盘啦、淘股吧、同花顺问财）默认三件事：能按**交易日**回看任意一天的历史股池（POOL-04）、看到**完整的竞价策略族**（STRAT-04/05）、并拥有**真实的 09:25 撮合成交数据列**（DATA-04/05）——这些不是增值特性而是产品地基。专家构建此类系统的三个不可妥协点：(1) **诚实标签铁律**——真竞价列只在 probe 判定 `available` 时存在，09:30 连续竞价 bar 永不标"竞价量"；(2) **冻结式点快照**——历史股池归档"当次计算的行集"而非当日多次运行累计的 union；(3) **确定性回放 vs 逐日存档的诚实区分**——回放优先（零存储、可审计），存档仅作可选增强。

推荐做法：三项特性**全部复用 v1.3 锁定栈，新增运行时依赖为零**（Polars 1.40.1 + DuckDB 1.5.3 + Parquet/pyarrow 24.0.0 + SQLite + FastAPI 0.136.1 + React Query 5.55 已含全部所需原语）。构建顺序必须**数据优先**：先 DATA-04/05（probe 门控的真竞价列 + `kline_auction/` 湖 + 交易日历），再 STRAT-04/05（5 个第一性原理策略 + 可计算时间窗声明），然后 POOL-04（`strategy_cache` 日期分区 + 最新指针 + 独立只读端点 + EOD 持久化 job），最后前端 DateNavigator。理由：竞价列是策略筛选的价值前置（无真列则 5 个策略塌缩为同一组 open_gap+量比 组合），逐日缓存是历史浏览的前提，日期导航是纯展示层消费。

最大风险是 DATA-04 数据源可用性未知：probe 未确认 `available` 前，全部策略与 UI 必须以 fail-closed 为前提设计（竞价列缺列、降级到派生 `open_gap`）。其次是历史股池的语义陷阱：`strategy_cache.write_cache` 的单日合并是 **union** 语义（`today_ever_rows` 并集），若直接按日归档会把"当日累计并集"冒充"点时刻快照"，必须引入冻结式点快照（`as_of` + `computed_at` + 策略版本指纹，永不回填/追加）；回放必须 PIT（只读 `<= D` 分区），否则用今天已修正的数据重算过去的池子，研究结论不可信。另有一个必须诚实处理的归类问题：**金色两点半是尾盘/隔夜策略（14:30 后选股、隔夜持有、次日早盘卖），不是 09:15–09:25 竞价策略**，塞进竞价窗口即语义造假。

## Key Findings

### Recommended Stack

v2.0 不需要任何新运行时包：历史股池的缺口不是"缺库"而是"缺按日持久化"——`strategy_cache.py` 只保留单一 as_of（read-merge-write 覆盖 `results`/`as_of`），而 `screener_results/` 目录在数据湖布局中只作为空占位目录存在，全仓无写入方。因此 POOL-04 的落点是新的**持久化 seam**：把每日 `run_all` 结果写成按 `date=` 分区的 Parquet 湖表，用 Polars `scan_parquet(hive_partitioning=True)` 读单日、用 DuckDB 冷 SQL 做日期索引。DATA-04 的 provider 契约已存在（`ProviderCapabilities.auction` 能力位、`custom/provider.py::get_auction` 已返回 canonical 列 `symbol/datetime/auction_volume/auction_amount` 且严格限定 09:15–09:25 窗口、探针判定状态机 + 30s TTL 的 `/api/data/auction-probe`），缺的只是湖内持久化与读路径门控。

**Core technologies:**
- **Polars 1.40.1**: 历史股池单日投影读取、策略引擎帧、竞价列入 enriched 面板 — `pl.scan_parquet(<dir>, hive_partitioning=True)` 传目录自动开 hive 分区推断，`filter(date==d)` 谓词下推只读目标分区（Context7 验证）
- **DuckDB 1.5.3**: `screener_results/` / `kline_auction/` 的冷查询日期索引 — `read_parquet('dir/**/*.parquet', hive_partitioning=true)` + `SELECT DISTINCT date` 列可用交易日与每日计数，与既有 "DuckDB 冷 → Polars 温 → 内存热" 分层一致
- **FastAPI 0.136.1**: 扩展 `GET /api/pool/hub?as_of=` 语义、新增 `GET /api/pool/dates` — 可选 query param `= None` / Pydantic query-param model，现有 `Optional[str] as_of` 模式已达标
- **SQLite (operational.db, stdlib)**: 竞价可用性的按日门控标记与历史簿记 — 只存操作状态不存研究行，延续平台 "SQLite 存状态 / 湖存研究数据" 分工
- **Parquet (pyarrow) 24.0.0**: `screener_results/` + `kline_auction/` 两个新湖表按 `date=` hive 分区 — 追加式按日写（temp + `os.replace` 原子替换，延续 `kline_sync._atomic_write_parquet` 模式）
- **React + TanStack Query** (react 18.3.1 / 5.55.0): 前端日期导航 ‹ › 步进 + 日期列表、as_of 重取 — `PoolHubPage` 已按 `data.as_of` 做 `key` 重渲染，复用现有 `useQuery` 缓存

**Supporting / conditional:** apscheduler 3.11.2（仅当 STRAT-05 盘中确认纳入本期）、sse-starlette 3.4.4（仅池页实时刷新）、exchange-calendars 4.13.2（默认**不用**——日期列表以湖分区为准；仅跨节假日 step 才从 `forecast` extra 提升）、pydantic 2.13.4（query-param model）、Playwright 1.61.1（e2e 视觉回归）。

**What NOT to use:** 新数据库（Postgres/Redis/MongoDB）；akshare/tushare 整包 SDK（provider 链 + `get_auction` seam 已是集成点）；Arrow/Feather 存历史（IPC 是暂态格式）；前端交易日历库/日期选择器组件库（日期由后端权威给出）；第三个策略注册轨（STRAT-03：只进 `strategy/builtin/` 自动发现）；ML/forecast 栈进入池路径（竞价策略是确定性因子过滤，池路径零 AI 执行权）；ORM 管 operational.db（既有版本化迁移足够）；把 09:30 连续竞价 bar 当竞价量（T-16-01 锁死，严格窗口分类）。

### Expected Features

**Must have (P1 / v2.0 核心):**
- **竞价量/金额一级列 (DATA-04, probe-gated)** — 探测 `available` 时把 `auction_volume/auction_amount`（真实 09:25 撮合，窗口 09:15–09:25）落为 enriched 受管列；不可用则缺列 + fail-closed 降级 `open_gap`。**全部下游的入口。**
- **日期导航 · 确定性回放 (POOL-04)** — 交易日历步进 + 日期选择；按日 `run_all(as_of)` 回放（引擎已支持，enriched 已有 246 个交易日分区）；`strategy_cache` 泛化为按日键；无数据日空态；概念标签标注「当前快照」。
- **极速抢筹 + 竞价阿尔法 (STRAT-04 前 2)** — 第一性原理因子（竞价量比/竞价金额/竞价涨幅甜点区 2.8%–3.5%、>7% 风险；open_gap+量比+金额强度综合），落 `strategy/builtin/`，带 hit_factors。
- **金色两点半（诚实归类）** — 尾盘（14:30+）选股因子（T 日涨幅 3%–5% + 尾盘分钟确认），命名/描述明确「尾盘隔夜」，**不混入竞价窗口**。
- **派生列：竞价未匹配金额（可选输入）** — 委托量可得时派生；无委托量回退量比+金额。

**Should have (P2 / add-after validation):** 竞价全面策略（综合版，DATA-04 稳定后）；T+1闪电（次日早盘分钟 K 卖出择时，STRAT-05 落地后）；STRAT-05 盘中确认（09:30–10:00 分钟 K 复评收窄，复用 `kline_minute`，不加新数据轨道）；竞价换手/委托失衡派生列（需 auction 源扩展 order 字段）。

**Defer (v2.1+ / P3):** 虚拟成交实时列/历史竞价图（需实时竞价源 + 盘中快照，EOD 源无法支撑）；DATA-05 盘前股池（09:30 前可用，需实时源，排在 DATA-04 稳定后）；逐日存档模式（非回放，触发后才做）；POOL-05 自选股联动。

**Anti-features（明确拒绝）:** 把金色两点半当 09:15–09:25 竞价策略实现；用 09:30 连续竞价 bar 充当竞价量/金额；把「虚拟成交」作为历史序列持久化（实时预撮合估计，非最终成交）；逐日全量存档无限膨胀（回放优先，零存储）；复刻专有策略配方（陈星量化等——第一性原理 + 诚实命名，META 写清"参考标签的诚实解读"）；日期导航放行任意日期（受限在真实交易日集合内，空态而非报错）；在 DATA-04 探测确认前一次性实现全部 5 个策略（顺序化，先探测先落 2 个）。

### Architecture Approach

v2.0 的三个特性线程全部挂接在既有分层上，不引入新存储或第三方注册轨道。三条数据主链：

```
[A] 真竞价列: provider.get_auction → auction_sync [NEW] → kline_auction/date=*/ 湖
    → indicators.pipeline 按 (symbol,date) 窗口聚合 → auction_* 受管列（probe 门控）
    → 竞价策略 filter（probe 不可用 → 列缺席, 策略空安全退化 open_gap）
[B] 历史股池: run_all(as_of) → strategy_cache/{as_of}.json [NEW]（最新指针 + 日期分区）
    → pool_hub 按日期投影 → GET /api/pool/hub?as_of → DateNavigator
[C] 新策略族: strategy/builtin/*.py 自动发现 → engine.run_all
    → build_factor_hits 逐日期聚合 → hit_factors/交叉共振（无改动）
```

**Major components:**
1. `services/auction_sync.py` (NEW) — 从 provider `get_auction()` 拉取 09:15–09:25 匹配行，按 `date=` 分区写入 `kline_auction/`，镜像 `kline_sync` 的原子写+分区+视图刷新模式
2. `services/auction_probe.py` (MOD) — 判定（not_configured/available/fail_closed/error）下沉为进程内可复用结果（`auction_available_for(date)`），供 pipeline 与策略消费，30s TTL 缓存语义不变
3. `indicators/pipeline.py` (MOD) — probe 门控的 `auction_volume/auction_amount/auction_virtual_fill` 受管列；窗口内按 symbol 聚合为每日一行，**绝不从 09:30 bar 取数**
4. `strategy/engine.py` (MOD) — `META["requires_auction_data"]` + 空安全约定（列缺席→过滤器整体为假→空池）
5. `strategy/builtin/*.py` (NEW, 5 文件) — 竞价阿尔法/极速抢筹/T+1闪电/竞价全面策略/金色两点半，遵守 STRAT-03 只进 builtin 自动发现
6. `services/strategy_cache.py` (MOD) — 按日期分区写（`{as_of}.json`）+ 保留 `strategy_cache.json` 为最新指针；锁/原子替换语义不变
7. `services/pool_history.py` (NEW) — 枚举可用股池日期（分区缓存 ∩ enriched 日期）、触发历史回填
8. `services/pool_hub.py` (MOD) — 按请求 as_of 读对应日期缓存；无 as_of → 最新指针（现契约不变）
9. `api/pool.py` (MOD+NEW) — `GET /api/pool/hub` 真实多日期语义 + 新增 `GET /api/pool/dates`
10. `frontend/.../DateNavigator.tsx` (NEW) — 交易日前后翻页 + 日期列表

关键架构模式：(1) **Probe 门控的受管列**——列族可用性由服务端权威判定，available 才物化，否则列缺席（fail-closed）；(2) **最新指针 + 日期分区缓存**——`strategy_cache.json` 语义保持"最新一天"不变，历史浏览读分区文件，不破坏 single-as_of 契约（D-01/D-02）与 monitor 叠加路径；(3) **日期分区湖 + 窗口内聚合**——原始多时间戳行情按 (symbol, trade_date) 聚合为每日一行，保持 enriched 日线框架基数 1 行/股/日。缩放优先序：先解决历史回填的同步阻塞（EOD 预生成 job + 首日一次性后台回填），再解决日期列表扫描（缓存已排序列表）。

### Critical Pitfalls

1. **union 冒充点快照（Pitfall #1）** — `strategy_cache.write_cache` 的单日合并语义是 union（`today_ever_rows` 并集）。规避：POOL-04 必须引入**冻结式点快照**——固定时刻（盘后 run_all 完成后）把当次 `results` 原样序列化到 `screener_results/date={as_of}/` 或等价归档目录，快照携带 `as_of` + `computed_at` + 策略版本指纹，永不回填/追加，绝不落 `today_ever_rows`。
2. **回放滚动重算 non-PIT（Pitfall #2）** — 用今天已修正/已复权的数据重算过去股池（`change_pct` 是典型的未来 bar——盘前不可知）。规避：回放只读 `<= D` 分区，复用 `_load_enriched_history(D, lookback)` 的 PIT 语义并加回归锁；归档快照直接存行集，浏览历史只投影不重跑；概念归属标注「当前板块归属」。
3. **未来 bar 回看 lookahead（Pitfall #7）** — STRAT-05 盘中确认把 10:00 后分钟 bar 算进"当前确认"；盘前策略用当日收盘字段。规避：每个策略声明**可计算时间窗**（`pre_open` / `intraday` / `post_close`），STRAT-05 按 `evaluation_time` 截断分钟帧（`df.filter(datetime <= eval_time)`），日内量比做 `time_factor` 折算，引擎按窗口校验字段可用性。
4. **09:30 bar 当集合竞价数据（Pitfall #8/#10）** — 分钟层 `_bucket_minutes` 结构上丢弃 09:15–09:25 盘前 bar，09:30 是连续竞价起点。规避：策略只能消费 `get_auction()` canonical 列（provider 层已裁剪窗口）；真竞价列只在 probe `available` 时出现；给每个"竞价"策略加回归——输入只有 09:30+ bar 时必须 fail-closed 空或明确标 derived。
5. **破坏 single-as_of 契约（Pitfall #5）** — 为支持日期导航原地扩写 `GET /api/pool/hub`（加 date 参数重算/写缓存）。规避：日期导航走**独立只读端点**（`/api/pool/dates` + hub 的 as_of 多日期投影），不写 `strategy_cache.json`、不触发 run_all；既有 `resolved_as_of` 反漂移契约保留并补回归测试；POOL-03 AST 守卫扩展到全部 `/api/pool/*`。
6. **probe 静默 fail-open（Pitfall #11）** — 非 `available` 时新代码仍返回竞价列或回退不更新状态标识。规避：竞价列生产路径以 probe 判定为前置，非 available → 列 null/缺列 + 状态标识保持 probe 原值；任何回退显式 fail-closed（沿用 `FAIL_CLOSED_DETAIL` 文案）；新增 probe 四状态 × 竞价列返回矩阵测试。

其他要点：交易日/自然日歧义（非交易日必须显式回显最近交易日，禁止静默跳日）；陈缓存误标最新（`latest_date()` 与缓存 as_of 不一致时回显缓存日期）；策略命名暗示公开配方（第一性原理描述 + 文档计数对账，现有 20 vs 18 漂移）；评分权重和 != 1.0 / 缺失评分列静默跳过（策略加载自检）；列单位歧义（手 vs 股、元 vs 万元，canonical 单位在 `get_auction` 边界锁定 + 表头标注 + `虚拟成交` 独立命名 `auction_virtual_fill`）。

## Implications for Roadmap

基于组合研究，v2.0 建议按**数据 → 策略 → 股池 → 前端**四阶段推进（延续 v1.3 的 Phase 编号，DATA-04 是 STRAT-04 的价值前置，逐日缓存是 POOL-04 的前提，前端是纯展示消费）。EOD 股池持久化 job 在股池层落地，保证日期导航自给自足。

### Phase 1: 数据层 — 真集合竞价数据列 (DATA-04/05)
**Rationale:** 竞价列是策略筛选的前提；probe 判定决定后续全部策略与 UI 的形态（可用即一级列，不可用则全程 fail-closed）。交易日历应在本层相邻落地，作为日期导航的解析底座。
**Delivers:** `sync_auction` 阶段 + `kline_auction/date=*/` 湖 + probe 门控的 `auction_*` 受管列；交易日历解析服务（`as_of → 最近的 <= 该日交易日`，显式回显）；canonical 单位契约（股/元）。
**Addresses:** DATA-04 (P1)、交易日历约束 (P1)。
**Avoids:** Pitfalls #8/#10 (09:30 bar 永不产生竞价值)、#11 (probe 矩阵测试)、#12 (单位 fixture)、#3 (交易日/自然日歧义)。
**Uses:** Parquet 湖 + Polars/DuckDB（STACK.md 既有栈，零新依赖）。
**Research flag:** **需要 `--research-phase`** — DATA-04 数据源可用性是本期最大不确定项；规划前必须先做 probe 探测（Tushare `stk_auction_o` vs 自定义 auction 数据集），虚拟成交（`auction_virtual_fill`）字段语义依赖具体上游，物化前实测确认，不做来源推测。

### Phase 2: 策略层 — 竞价策略族 (STRAT-04/05)
**Rationale:** 依赖数据层竞价列；5 个新策略的区分度来自真实竞价量/金额/量比，无真列则彼此塌缩。命名与时间窗纪律应在第一批提交时就锁定。
**Delivers:** 5 个 `strategy/builtin/*.py`（竞价阿尔法/极速抢筹/T+1闪电/竞价全面策略/金色两点半——金色两点半诚实归类为尾盘/隔夜）；`requires_auction_data` 空安全；可计算时间窗声明；策略加载自检（scoring 列存在 + 权重和 > 0）；STRAT-05 盘中确认（分钟帧 `<= eval_time` 截断，复用 `kline_minute` + apscheduler，不加新数据轨道）。
**Addresses:** STRAT-04 前 2 个 (P1，极速抢筹/竞价阿尔法)、金色两点半 (P1)、STRAT-05/T+1闪电/竞价全面策略 (P2，按数据可用性分批)。
**Avoids:** Pitfalls #6 (命名暗示公开配方 + 文档计数对账)、#7 (lookahead 窗口规约 + 截断测试)、#9 (scoring 自检)。
**Research flag:** **中等** — 第一性原理因子阈值（量比/甜点区/金额强度）需按 A 股历史校准；STRAT-05 的 `eval_time` 截断与 `time_factor` 折算规则需要专门规划研究。

### Phase 3: 股池层 — 历史股池日期导航 (POOL-04)
**Rationale:** 依赖策略层 `run_all` 可逐日期产出；这是 v1.3→v2.0 最脆弱的接口边界，点快照语义必须在持久化设计时定死，否则归档格式定错后难以迁移。
**Delivers:** `strategy_cache` 日期分区写（`{as_of}.json`）+ 最新指针（`strategy_cache.json` 语义不变）；冻结式点快照（`as_of` + `computed_at` + 策略版本指纹，不落 `today_ever_rows`）；`pool_history.py` 日期列表/回填；`GET /api/pool/dates` + `GET /api/pool/hub?as_of` 真实多日期投影；EOD 持久化 job（盘后自动 `run_all(当日)` 落日期缓存，请求只读缓存不阻塞）；PIT 概念标注（「当前快照」或随快照冻结）。
**Addresses:** POOL-04 (P1)、历史股池双模式（回放优先，存档可选）。
**Avoids:** Pitfalls #1 (union 冒充点快照)、#2 (non-PIT 回放)、#4 (陈缓存误标最新)、#5 (破坏 single-as_of 契约——独立只读端点 + AST 守卫扩展)。
**Research flag:** **需要 `--research-phase`** — 回填策略（首日一次性后台回填 vs 请求内同步）与日期列表缓存失效设计需要细化；概念板块 PIT 的历史 ext 分区目前不存在，历史视图概念标注方案需专门研究。

### Phase 4: 前端层 — DateNavigator 与竞价列展示
**Rationale:** 纯展示层消费；等股池层 API 契约（`/api/pool/dates`、hub as_of 投影）稳定后再接线，避免返工。
**Delivers:** `DateNavigator.tsx` ‹ › 步进 + 日期列表（来源 `GET /api/pool/dates`）；卡片计数/明细随 as_of 重取（复用现有 `useQuery` 缓存）；竞价列（probe=available 且 VIP 时显示，表头标注单位与「集合竞价(真) vs 派生(open_gap)」）；guest 历史视图仍只显 涨跌幅+概念；无数据日空态文案。
**Addresses:** POOL-04 的 UX 面、DATA-04 的展示面。
**Avoids:** UX 陷阱（非交易日禁用、虚拟成交与真实成交分列、「最新」视图显示缓存 as_of 与不一致提示、盘前策略空态展示 probe/窗口状态）。
**Research flag:** 标准模式 — 既有 typed `api.ts`/`queryKeys.ts`/SSE hooks/Playwright 截图断言；跳过 research-phase。

### Phase Ordering Rationale
- **严格依赖链：数据 → 策略 → 股池 → 前端。** 竞价列是策略筛选的前提（STRAT-04 的区分度来自真实量/金额）；逐日缓存是历史浏览的前提（POOL-04 需要 `run_all` 逐日期产出）；日期导航是纯展示消费。这是 FEATURES 依赖图给出的最强约束。
- **诚实边界在数据层定死，消费端强制执行。** 诚实标签（probe 门控 + 09:30 bar 永不标竞价）由 pipeline 列定义与策略空安全双重锁定；点快照语义（union vs 点快照）必须在 POOL-04 持久化设计时定死，不能等归档格式落地后再迁移。
- **probe 先行、分批做策略。** 先探测 → 先落 2 个真列可支撑的策略（极速抢筹/竞价阿尔法），其余按数据可用性分批，避免无真列时 5 个策略同质化。
- **金色两点半不依赖竞价数据**（需要 T 日 change_pct + 分钟 K），其语义断裂体现在命名/描述/分组，而非数据依赖顺序。
- **EOD 持久化 job 属于股池层**，保证日期导航自给自足，首请求不阻塞在请求内 run_all。

### Research Flags

Phases likely needing deeper research during planning (`/gsd-plan-phase --research-phase`):
- **Phase 1 (DATA-04/05):** 数据源可用性探测与虚拟成交字段语义——本期最大不确定项；Tushare `stk_auction_o`/`stk_auction` vs BigQuant `cn_stock_factors_auction` vs 自定义 auction 数据集的可达性与窗口内时间戳。
- **Phase 2 (STRAT-04/05):** 第一性原理因子阈值校准 + STRAT-05 的 `eval_time` 截断/`time_factor` 折算规约。
- **Phase 3 (POOL-04):** 历史回填策略（EOD 预生成 job 设计）+ 概念板块 PIT 的历史 ext 分区缺口。

Phases with standard patterns (skip research-phase):
- **Phase 4 (前端):** 既有 typed 客户端 + `useQuery` 缓存 + Playwright 截图断言惯例。
- **Phase 1 的子项（湖写入）:** `kline_sync` 的原子写+分区+视图刷新模式已证明，直接复用。

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH (DATA-04 源可用性 MEDIUM) | `backend/uv.lock` 锁定版本仓库内验证 + Context7 佐证；probe 门控使数据源可用性本身为运行期变量 |
| Features | MEDIUM | Tushare/BigQuant 官方文档直取 + 多中文量化源 web 交叉；既有 seam（`run_all(as_of)` 回放、`get_auction` canonical 列、246 日分区）为 HIGH |
| Architecture | HIGH (虚拟成交语义 MEDIUM) | 全部集成路径源码核实（auction_probe / strategy_cache / engine / pool_hub / custom provider / daily_pipeline）；虚拟成交字段依赖具体上游 |
| Pitfalls | HIGH | 逐条代码核验（`write_cache` union 合并、`read_cache` 移除 mtime 校验、`_apply_scoring` 静默跳列、`_bucket_minutes` 丢弃盘前 bar） |

**Overall confidence:** HIGH —— 除 DATA-04 数据源可用性（probe 门控，属运行期变量）与虚拟成交字段语义外，栈/架构/陷阱均以 v1.3 落地代码核验。本次里程碑规划可直接基于本摘要进行。

## Gaps to Address

- **DATA-04 数据源可用性未知：** 规划时先做 probe 探测；全部下游（STRAT-04 区分度、UI 竞价列）以 fail-closed 为前提设计，探测 available 是"启用"而非"假设"。
- **虚拟成交（`auction_virtual_fill`）语义依赖上游：** 物化前以 probe 实测确认（实时盘口快照 vs 盘后派生）；盘后只能派生并标注"估计"，绝不冒充历史观测。
- **概念板块 PIT：** 当前 ext 概念映射是当下快照，历史日池子的概念标签 = T 日标签而非 D 日标签；历史视图需标注「当前快照」或引入历史 ext 分区（目前不存在）。这是 POOL-04 唯一的数据语义缺口。
- **单位契约：** 手 vs 股、元 vs 万元多口径；canonical 单位（股/元）必须在 `get_auction` 边界锁定 + 表头标注 + fixture 换算测试，否则污染所有下游因子。
- **exchange-calendars 是否提升：** 默认不用（日期列表以湖分区为准）；仅当 UI 需要跨节假日 step 推算 prev/next 交易日时从 `forecast` extra 提升（与 numpy 2.4.6 兼容性需确认）。
- **STRAT-05 是否纳入本期：** 影响是否需要 apscheduler 新 stage（09:30–10:00 复评）；FEATURES 将其列为 P2（竞价池已有、假阳性反馈后触发）。
- **策略计数文档对账：** 现有 `docs/features.md` 20 vs 源码 18 的漂移；新增 5 策略必须同里程碑内对账，消除"Looks Done But Isn't"检查清单项。
- **历史回填的同步阻塞：** 首请求某历史日无缓存时在请求内跑 run_all 会卡页面；必须由 EOD 持久化 job 预生成 + 首日一次性后台回填解决。

## Sources

### Primary (HIGH confidence)
- **Stack:** `backend/uv.lock`（polars 1.40.1 / duckdb 1.5.3 / fastapi 0.136.1 / pyarrow 24.0.0 / apscheduler 3.11.2 / exchange-calendars 4.13.2 等锁定版本）；Context7（Polars `scan_parquet` hive_partitioning/try_parse_hive_dates、DuckDB `read_parquet` glob + 分区剪枝、FastAPI 可选 query param）；仓库 seam 核验（`strategy_cache.py`、`pool_hub.py`、`auction_probe.py`、`custom/provider.py`、`indicators/pipeline.py`、`PoolHubPage.tsx`）
- **Features:** Tushare `stk_auction_o` / `stk_auction` / `stk_mins` 官方文档；BigQuant `cn_stock_factors_auction` 官方数据页；集合竞价规则多源；金色两点半尾盘选股法多源；v1.3 代码核验（`auction_probe.py`、`pool_hub.py`、`strategy_cache.py`、`run_all`、`kline_daily_enriched/` 246 日分区）
- **Architecture:** 源码核实（`auction_probe.py`、`strategy/engine.py`、`factor_hits.py`、`builtin/auction_*.py`、`strategy_cache.py`、`pool_hub.py`、`api/pool.py`、`api/screener.py`、`api/data.py`、`indicators/pipeline.py`、`custom/provider.py`、`jobs/daily_pipeline.py`、`PoolHubPage.tsx`）；`.planning/REQUIREMENTS.md` / `ROADMAP.md` / `PROJECT.md`
- **Pitfalls:** 代码核验（`pool_hub.py` single-as_of 契约、`strategy_cache.py` union 合并与 read_cache 注释、`auction_probe.py` + `test_auction_probe.py`、`engine.py::_apply_scoring`、`free_stockdb_provider.py::_minute_ts/_bucket_minutes` + `test_minute_timestamp_convention.py`）；`.planning/research/v1.3-auction/PITFALLS.md`

### Secondary (MEDIUM confidence)
- 同花顺问财/55188/SuperMind 竞价抢筹与量比甜点区公式；开盘啦竞价系统 + 历史竞价图 UX；`docs/features.md` 策略计数漂移观察；A股成交单位多口径惯例（手/股、元/万元）

### Tertiary (LOW confidence)
- 无 —— 四份研究文件均以仓库代码核验为主；残余不确定项（DATA-04 源可用性、虚拟成交语义、概念 PIT）已落入 Gaps to Address，而非源质量不足

---
*Research completed: 2026-08-04*
*Ready for roadmap: yes*
