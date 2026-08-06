# 竞价复盘 — 盘后 AI 复盘接入竞价维度 — v2.2 research

**研究者:** ResearcherRecap
**日期:** 2026-08-06
**置信度:** HIGH(现状与数据装配全部源码核验 + 磁盘实测);唯一不可验证项 = 外部实时竞价源可用性,已标 [INFERENCE]

---

## 现状 (current state with code anchors)

### 1. 今日盘后复盘的结构 — 纯 AI 大盘复盘,无竞价维度

**调度与落盘链路**(`backend/app/jobs/daily_pipeline.py`):
- `REVIEW_JOB_ID = "scheduled_review"`(`daily_pipeline.py:760`);`_run_scheduled_review`(`:763-830`)→ `_stream_review_with_retry`(`:831-888`,LLM 断流最多重试 2 次)→ 归档 `market_recap_reports.save_report` → `quote_service.push_review_event(done)` → `_maybe_push_review`(`:891-933`,Feishu/WeCom)。
- 注册:`_register_review_job`(`:936-957`),`CronTrigger(mon-fri, hour/minute, Asia/Shanghai)`,`misfire_grace_time=7200`;调度时间 = `preferences.get_review_schedule()`(`preferences.py:433-444`,**默认 disabled,15:10,强制下限 15:00**,`set_review_schedule` `preferences.py:446-457`);设置 API `PUT /api/preferences/review-schedule`(`api/settings.py:1425-1465`)。
- AI key 未配置 → 诚实 skip(`_run_scheduled_review` L776-779),不报错刷日志。

**复盘生成**(`backend/app/services/market_recap.py`):
- 系统提示词 `_SYSTEM_PROMPT`(`market_recap.py:40-109`):固定 **8 节模板** — ①一句话定调+明日基调 ②盘面总览 ③指数结构 ④板块主线 ⑤资金与情绪 ⑥消息催化 ⑦明日交易计划 ⑧风险提示。**无竞价/盘前信号一节**。
- 用户提示词 `_build_user_prompt`(`:177-227`):复盘日期 + **主要指数 / 盘面数据 / 市场情绪 / 概念板块排名 / 行业板块排名 / 近期市场新闻 / 关注点** 七个精简切片。数据全部来自 `build_market_overview`。
- 数据装配 `build_market_overview`(`backend/app/services/market_overview_builder.py:345-580`):indices/breadth/amount/boards/limit/distribution/trend/activity/radar/emotion/top_gainers/top_losers/turnover_leaders/active_leaders/concept_rank/industry_rank。**返回键里没有任何竞价列**(`auction_volume/amount/ratio`、`premarket_results`、`screener_results` 均不出现)。
- 流式主入口 `recap_market_stream`(`market_recap.py:253-324`):NDJSON 协议 meta/delta/error/done;`stream_ai_text(messages, temperature=0.5, max_tokens=4500)`(`:308-322`);AI 失败 yield error(不产出确定性兜底)。`recap_market_once`(`:327-356`)累积 delta 供调用方。
- 报告存储 `market_recap_reports.py`:JsonReportStore `ai_market_recaps.json`,MAX 20,id 前缀 `mkr`。API `backend/app/api/market_recap.py`:POST `/analyze`(NDJSON 流)+ GET/POST/DELETE `/reports`。

**AI 装配**(`backend/app/services/ai_provider.py`):`stream_ai_text` 支持 openai_compat(AsyncOpenAI)与 codex_cli;配置经 secrets_store;`ai_reports.py` 是财务分析报告存储,与大盘复盘(`market_recap_reports.py`)完全独立。

### 2. v2.1 已交付的竞价/股池数据资产(复盘可消费的输入)

| 资产 | 存储 | 写入时机 | 内容 | 当前数据现状(磁盘实测) |
|---|---|---|---|---|
| **kline_auction 湖** | `data/kline_auction/date={d}/part.parquet` | EOD 管道 Step 2.6,~15:30,probe 门控(`auction_sync.py:96-137`) | 每 symbol 每窗口多行 `(symbol, datetime, auction_volume, auction_amount)` + 可选委托量列;读路径 `attach_auction_columns` 按 symbol 去重取末行(09:25 最终撮合)(`auction_columns.py:89-150`) | **0 分区**(目录为空) |
| **盘前预览股池** | `data/premarket_results/date={d}/part.json` | 工作日 09:26 job `_premarket_pool_preview`(`daily_pipeline.py:1017-1067`) | `run_all_with_hits(today)` 结果,`window:"pre_open"` / `computed_at` / `provisional:true` / `degraded` / probe 判定(`premarket_pool.py:32-74`);读 `load_premarket_snapshot`(`premarket_snapshot.py:61-88`);端点 GET `/api/pool/premarket`(`api/pool.py:117-163`) | **MISSING**(无预览文件) |
| **EOD 冻结股池快照** | `data/screener_results/date={d}/part.json` | 盘后管道完成后 +5min ~15:35 `_pool_eod_persist`(`daily_pipeline.py:973-1015`) | 当次 `run_all_with_hits` results(每策略 `{total, as_of, rows}`,行含 open_gap/change_pct/hit_factors)+ `snapshot_origin:"eod"`(`pool_snapshot.py:50-104`);读 `load_point_snapshot`;端点 GET `/api/pool/history` | **0 快照** |
| **enriched 湖** | `data/kline_daily_enriched/date={d}/part.parquet` | 盘后管道;盘中 live flush(`quote_service._flush_live_enriched`) | 日线 OHLCV + `open_gap` + 指标/信号列 | **248 分区**(2025-07-29 →) |

**关键点:**
- `open_gap` 是 enriched 存储列(ARCHIVE 核验),**恒在**——这是「竞价复盘」里唯一任何时候都真实可用的竞价维度代理(派生自 open/prev_close−1)。
- 真实竞价列(`auction_volume/amount/ratio`)只在 **probe available × 当日分区存在** 双闸门通过时注入(`auction_columns.py:89-150`);09:30+ 连续竞价 bar 被窗口谓词结构性排除(`auction_sync.py:107-115`)。
- 盘前预览是 **provisional(非收盘定稿)**:09:26 生成,`close=开盘价`,`change_pct ≈ open_gap`;`degraded:true` 表示 probe 非 available → 预览基于派生因子而非真实竞价列。**绝不能把预览当收盘事实**。
- EOD 快照是**当日冻结归档**,`snapshot_origin` 区分 eod/backfill/manual(HIST-02)。

### 3. 9 个竞价/盘前策略族(复盘信号质量面板的对象)

| 策略 id | 显示名 | time_window | 盘前可算? | 数据依赖 |
|---|---|---|---|---|
| `auction_alpha` | 竞价阿尔法 | pre_open | ✅(真列分支或派生回退) | 真列:auction_volume_ratio/amount;派生:open_gap/vol_ratio_5d/amount |
| `auction_fast_grab` | 极速抢筹 | pre_open | ✅(需真实竞价列,缺列空池) | auction_volume_ratio/amount + open_gap 甜点区 |
| `auction_allround` | 竞价全面 | pre_open | ✅(需真实竞价列,缺列空池) | open_gap + auction_volume_ratio + auction_amount |
| `t1_flash` | T+1闪电 | pre_open | ✅(需真实竞价列,缺列空池) | open_gap + auction_volume_ratio + auction_amount |
| `auction_preopen_quant` | 盘前强势量化 | (盘前) | ✅ | open_gap + vol_ratio_5d |
| `auction_early_star` | 早盘之星 | (盘前) | 部分(OR change_pct 分支走 EOD) | open_gap 或 change_pct |
| `auction_bullish` | 竞价多头 | (盘前) | ⚠️(需 change_pct=EOD) | open_gap **且** change_pct |
| `strong_open` | 强势高开 | (盘前) | ❌(需 close>open + change_pct) | open_gap + close>open + change_pct |
| `auction_intraday_confirm` | 盘中确认 | intraday 09:45 | ❌(分钟确认) | open_gap 初筛 + 09:30-09:45 分钟帧 |

锚点:`backend/app/strategy/builtin/{auction_alpha,auction_fast_grab,auction_allround,t1_flash,auction_preopen_quant,auction_early_star,auction_bullish,strong_open,auction_intraday_confirm}.py`。**盘前预览里能产出的策略 = 盘前可算集合**;`strong_open`/`auction_intraday_confirm` 在 09:26 预览里通常空池。

### 4. 关键时序缺口(复盘默认时刻 vs 竞价数据就绪)

```
09:26 盘前预览(premarket_results/T)   → 复盘可消费(provisional)
15:00 复盘下限 / 15:10 复盘默认调度     ← 此刻 kline_auction/T 分区还不存在!
15:30 EOD 管道(含 Step 2.6 竞价同步)   → kline_auction/T 落湖(probe 可用时)
15:35 EOD 股池持久化                   → screener_results/T 落盘
```

- `_run_scheduled_review` 默认 15:10 跑,而 T 日 `kline_auction` 分区要等 15:30 Step 2.6 才写。**默认调度的复盘拿不到当日真实竞价湖**,只有盘前预览(09:26)与盘中 live enriched(open_gap)。→ 竞价复盘设计**必须时序弹性**:早于 15:30 时诚实降级「盘后竞价同步未完成」,或建议把复盘默认时间移到 15:35 之后。
- 手动 `/api/market-recap/analyze` 可在任意时刻触发;`as_of` 缺省 = `svc.latest_date()`(盘中 live flush 后 = 今日,否则昨日)。竞价维度按解析出的 as_of 取数,历史日同样成立(历史 kline_auction/premarket/screener 分区存在则消费,不存在则诚实空)。

---

## 方案选项 (2-3 options with tradeoffs)

### 选项 A:确定性「竞价复盘」数据面板内嵌复盘 + 可选 AI 点评(推荐)

新只读装配服务(如 `auction_recap.py`)按 as_of 计算三块**确定性**聚合,渲染成 Markdown 数据面板,追加进复盘内容流(delta 事件,在 `done` 前 yield);**默认不喂给 LLM**,可选开关把同款精简切片喂给提示词做 AI 点评(带「只引用切片数值」护栏)。

- **真实竞价活跃度**:经 `attach_auction_columns` 双闸门从 `kline_auction/T` 注入竞价列 → 竞价金额/量比 Top N、竞价额分布;probe×分区缺失 → 整块省略 + 诚实注记。
- **开盘涨幅快照**:enriched `open_gap` 恒在 → 高开分布(≥2%/≥5%)、高开股数、Top N。这是无竞价源时也永远真实的一档。
- **盘前信号质量(核心卖点)**:盘前预览 T 的命中行(provisional)× EOD `change_pct` → 每个盘前策略的命中数、平均 open_gap、平均 change_pct、开盘兑现率(≥2%)、收盘兑现率(≥2%)、收阳率;标注「预览=盘前非定稿」与 `degraded`(派生因子)。

**成本/约束:零新增运行时依赖、零 AI 成本(默认)、POOL-03 零执行权(纯读 + 不触发 run_all)、Feishu 随复盘全文送达。** 前端零改动(报告本身是 Markdown)。

### 选项 B:全 AI 复盘扩展(提示词加竞价节 + 数据切片)

在 `_SYSTEM_PROMPT` 增「竞价复盘」节 + `_build_user_prompt` 增竞价数据切片,由 LLM 写竞价叙事。

**成本/约束:AI token 上升(prompt 变大,max_tokens 4500 需评估)、幻觉风险高(数据缺失时 LLM 倾向编造)、诚实性需极强护栏。** 数据缺失时仍要让 LLM 明确写「今日无竞价数据」——护栏成本高于收益。

### 选项 C:独立只读端点 `GET /api/market-recap/auction` 单独渲染

复用选项 A 的装配服务,暴露独立只读端点,前端 Review 页新增「竞价复盘」面板(或独立路由)单独渲染。

**成本/约束:需前端新面板(新 UI 面 + 新测试);竞价事实与 AI 叙事分离;Feishu 推送的仍是纯 AI 复盘,竞价面板不进推送。** POOL-03 干净(端点 GET-only + AST 守卫),但与「盘后复盘是唯一交付物」的现状割裂。

### 对比

| 维度 | A(确定性内嵌+可选点评) | B(全 AI 扩展) | C(独立端点) |
|---|---|---|---|
| AI 成本 | 默认 0;可选小切片 | ↑(token + 复核) | 0 |
| 诚实性 | **最高**(确定性=零编造,provenance 显式) | 低-中(需强护栏防幻觉) | 最高(与 A 同源) |
| 零新增依赖 | ✅ | ✅ | ✅ |
| POOL-03 | ✅(纯读、不触发计算) | ✅ | ✅(GET-only) |
| Feishu/归档送达 | ✅(随复盘全文) | ✅ | ❌(单独面) |
| 前端改动 | 零 | 零 | 新面板 |
| 与「决策闭环」契合 | **高**(信号质量回填进唯一复盘交付物) | 中 | 低(割裂) |

---

## 推荐方案 (with rationale, honest boundaries)

**推荐选项 A**:确定性「竞价复盘」数据面板内嵌到盘后复盘 + 可选 AI 点评(默认关)。

**理由:**
1. **诚实性即平台法(最高优先)。** 竞价数据是 probe 门控的「有才有列」数据;确定性聚合从冻结湖/冻结预览直接算,零编造空间。AI 点评默认关,避免 LLM 在数据缺失时脑补竞价事实;开启时带「只引用给定切片数值、数据缺失必须明说」护栏。
2. **复盘是盘后唯一交付物(SSE 实时 + 归档 + Feishu),竞价维度应在里面。** 选项 A 在 `recap_market_stream` 的 `done` 前追加 delta,三跳(SSE 视图/`ai_market_recaps.json`/Feishu/WeCom)自动全收,无需新 UI。
3. **信号质量是纯数字回测,确定性表比 LLM 散文更可信。** 「盘前 X 策略命中 N 只、平均高开 a%、收盘兑现率 b%」这类统计用表格呈现,可验证、可归档、可回溯。
4. **零新依赖 + 零执行权天然成立。** 全部复用 `attach_auction_columns` / `load_premarket_snapshot` / enriched 帧;服务不 import 执行族、不触发 run_all(用冻结预览,不重算)、不写盘。
5. **时序弹性内建。** 默认 15:10 调度跑在竞价同步前 → 面板只展示「开盘涨幅快照 + 盘前信号质量(预览已就绪)」,真实竞价活跃度块诚实省略并注明「盘后竞价同步未完成,建议 15:35 后重跑」;15:35 后重跑 → 三块全亮。**不做任何假装。**

**诚实边界(写入需求的硬约束):**
- 真实竞价列只在 `kline_auction/date={as_of}` 分区存在且有行时出现;probe 非 available 或分区缺失 → 整块省略,绝不 0 填充/绝不暗示有真实竞价数据。
- 盘前信号质量标注「基于盘前预览(非收盘定稿)」;预览 `degraded:true` → 明确「盘前信号基于派生因子(非真实竞价数据)」。
- 09:30+ 连续竞价 bar 永不进竞价列(既有窗口谓词,面板只消费湖里真实竞价行)。
- 面板顶部声明「竞价复盘为确定性数据,非 AI 生成」;可选 AI 点评单独落款,与面板事实冲突时以面板为准。

---

## 需求草案 (REV-0x: verifiable requirement drafts)

### REV-01:确定性竞价复盘数据装配(只读服务)

**作为** 复盘使用者,**我** 在盘后复盘里看到按当日 as_of 计算的竞价维度数据面板,数据来自冻结资产(湖/预览/enriched),而非请求时重算。

- 新只读服务(建议 `backend/app/services/auction_recap.py`)暴露 `build_auction_recap(repo, as_of) -> dict`:
  - `as_of` 与复盘解析口径一致(缺省 `svc.latest_date()`);
  - `real_auction_activity`:经 `attach_auction_columns`(`auction_columns.py:89-150`)注入竞价列后,竞价金额 Top N、竞价量比 Top N、竞价总额 vs 前 5 日均量;**
  - `open_gap_snapshot`(恒在):高开分布、高开 Top N;
  - `preopen_signal_quality`:读 `load_premarket_snapshot(data_dir, as_of)`(`premarket_snapshot.py:61-88`),每个盘前策略命中行 join EOD enriched `change_pct` → 命中数/平均 open_gap/平均 change_pct/开盘兑现率(≥2%)/收盘兑现率(≥2%)/收阳率;
  - 顶部 `data_completeness`:枚举 `{full, no_auction_lake, no_premarket_preview, pre_eod, partial}` + 各块 provenance。
- **验收:** 1) 无 `kline_auction/{as_of}` 分区 → `real_auction_activity` 缺席,`data_completeness` 含 `no_auction_lake`,响应 JSON 可序列化;2) 有预览 → 信号质量表只含预览里实际有行的策略,行数 = 预览命中行数(display_limit 有覆盖时标注「基于展示行」);3) 服务源文件 AST 守卫:不 import 执行族 token(`broker|order|execution|trade|portfolio|position|account|transaction`,镜像 `test_pool_hub.py:858-860`),无写路径 pattern(`_WRITE_PATTERNS`);4) **服务绝不调 `ScreenerService.run_all_with_hits`**(消费冻结预览,不触发计算)。

### REV-02:诚实标注与降级(provenance 铁律)

**作为** 研究员,**我** 能分辨面板里哪些是真实竞价数据、哪些是派生/暂定,绝不把盘前当收盘、把派生当真值。

- 面板每块携带来源标注:真实竞价列(`auction_columns.real` 词汇)、预览 `provisional:true`/`degraded`/`probe`(与 `/api/data/auction-probe` 同词汇,`auction_probe.py:32-44`)、`data_completeness`。
- 降级路径:probe 非 available / 分区缺失 → 块省略 + 明示;复盘时刻 < 当日竞价同步(默认 15:10 调度)→ `real_auction_activity` 注明「盘后竞价同步未完成」;预览 `degraded:true` → 「盘前信号基于派生因子」。
- **验收:** 1) fixture 注入假 probe 状态(镜像 `test_auction_probe.py` injectable 模式):`not_configured`/`fail_closed`/`available` 三态下面板标注逐字正确;2) 构造 09:30+ 行 → 永不进竞价列(回归锁死);3) 面板顶部含「确定性数据,非 AI 生成」标识;4) 游客/无竞价配置下面板仍显示 `open_gap_snapshot`(恒真)而不整块消失。

### REV-03:盘前信号质量面板(核心交付)

**作为** 决策闭环使用者,**我** 在收盘后能看到「今天 09:26 盘前预览标的实际走得怎么样」,量化每个盘前/竞价策略的信号质量。

- 策略级统计表(策略 = 预览里实际有命中行的盘前可算集合:`auction_alpha`/`auction_fast_grab`/`auction_allround`/`t1_flash`/`auction_preopen_quant` 等,`strong_open`/`auction_intraday_confirm` 盘前空池则不出现):N 命中 / 平均 open_gap / 平均 change_pct / 开盘兑现率(open_gap≥2%) / 收盘兑现率(change_pct≥2%) / 收阳率(close>open)。
- 交叉共振视角:预览行已带 `hit_factors`(`screener.py:803-811`),可加「多策略共振标的」兑现率(复用 `build_factor_hits` 语义,只读)。
- **验收:** 1) 用 fixture 盘前预览(3 策略、含 open_gap/hit_factors)+ fixture EOD enriched,统计数值与手算一致;2) 预览缺失 → 整块省略 + `data_completeness.no_premarket_preview`,不造假零行;3) 统计基于冻结预览行,标注「基于盘前预览·非收盘定稿」;4) display_limit 覆盖存在时标注「基于展示行(display_limit 截断)」或明确采样口径。

### REV-04:复盘集成(内嵌面板 + 可选 AI 点评)

**作为** 复盘使用者,**我** 在 AI 大盘复盘报告里直接看到竞价维度面板,并且(可选)AI 点评能引用竞价事实。

- `recap_market_stream` 在 `done` 前追加确定性面板 delta(与 AI 内容同流 → SSE/归档/Feishu 全收);面板独立成节,如 `---` + `## 📊 竞价复盘(确定性数据,非 AI 生成)`。
- 可选开关(默认关,建议存 `preferences`):开启时把精简竞价切片喂给 `_build_user_prompt`,系统提示词加一行硬护栏「竞价数据只引用本切片中给出的数值;数据缺失时明说,禁止编造」;AI 内容与面板冲突时以面板为准。
- **验收:** 1) `recap_market_stream` 事件流:AI delta → 面板 delta → `done`,顺序稳定;2) `recap_market_once` 累积内容含面板;3) 归档到 `ai_market_recaps.json` 的内容含面板,`GET /reports` 返回原样;4) Feishu/WeCom 推送含面板(端到端或 webhook fixture);5) 面板不可用时(所有块都诚实省略)复盘内容退化为现有纯 AI 报告,协议不破坏(回归锁 `test_*` 现行为)。6) AI 点评开启时,提示词切片与面板同源(同一装配函数输出),不双源漂移。

### REV-05(可选/P2):独立只读端点 `GET /api/market-recap/auction`

**作为** 前端,**我** 能单独拉取竞价复盘聚合,用于独立面板/导出。

- 端点复用 REV-01 装配服务,GET-only;as_of 可选(严格 `^\d{4}-\d{2}-\d{2}$` 校验,镜像 `api/pool.py:85-93`);无数据 → 200 `{available:false, data_completeness:...}` 诚实空态(非 404)。
- **验收:** 1) 端点只读、不触发任何计算/写路径;2) 纳入 POOL-03 AST 守卫词汇(执行族 token);3) 空态 200;4) 与 REV-04 面板同源(同一装配函数),不双源漂移。

---

## 风险 / 开放问题

| # | 风险/问题 | 级别 | 处置 |
|---|---|---|---|
| R1 | **时序缺口**:默认复盘 15:10 < 竞价同步 15:30 → 定时复盘通常无当日竞价湖 | 高 | 面板内建时序弹性(REV-02 `pre_eod` 诚实标注);或 roadmap 决策把复盘默认时间移到 15:35 后 / 推荐用户在竞价同步后重跑。**不在 15:10 假装有竞价数据** |
| R2 | **外部实时竞价源不可验证**:沙盒 `kline_auction` 0 分区,真实竞价列依赖外部源 probe([INFERENCE]) | 高 | `real_auction_activity` 条件式(有分区才亮);`open_gap_snapshot` + `preopen_signal_quality` 无源也可交付;验收全用 fixture/mock |
| R3 | **AI 点评幻觉**(REV-04 可选):LLM 可能在数据缺失时编造竞价事实 | 中 | 默认关;开启时带「只引用切片数值 + 缺失明说」护栏;面板为准,冲突以面板胜;AI 输出加校验(可选:非必须) |
| R4 | **预览行截断影响统计口径**:`display_limit` 覆盖存在时预览 rows 是子集(默认 None=不截断,`screener.py:614-622,779-786`) | 低-中 | 标注「基于展示行」;统计口径写死为冻结预览 rows,不重算 |
| R5 | **历史 as_of 的 probe 语义**:`attach_auction_columns` 第一闸门是**当前** probe;历史分区存在但当前 probe 非 available 时会被该闸门挡住,丢掉明明在湖里的历史竞价数据 | 中 | 面板读历史 as_of 时以**分区存在性**为主闸门(镜像 `auction_history.py` 语义),probe 仅作 provenance 标注;需在 REV-01 明确「T 日走 attach 双闸门、历史日走分区闸门」或提供统一读 helper |
| R6 | **预览 change_pct 语义漂移**:09:26 预览帧 `change_pct ≈ open_gap`(close=开盘价),EOD 才是真收盘;信号质量必须 join EOD enriched 的 change_pct | 中 | REV-01 信号质量明确「EOD 收盘口径」;预览列绝不作为收盘兑现率来源 |
| R7 | **除权日 prev_close 对齐**:盘前 open_gap 用原始前收 vs EOD 复权对齐,可能不一致(PREMARKET 风险 8) | 低 | 面板注明「open_gap 基于 enriched 复权口径」;验收 fixtures 覆盖 |
| R8 | **AI 失败时面板是否兜底交付**:当前 AI 失败 → 整个复盘无内容(只有 error 事件) | 决策点 | 建议 REV-04 不做「AI 失败兜底面板」(改变报告契约);若产品要,单独评审「AI 失败 → 仅确定性面板 + 诚实说明」 |
| R9 | **`_build_user_prompt` 签名变更**:REV-04 需把竞价切片传入 prompt(或改签名/加可选参数),牵动 `recap_market_stream`/`recap_market_once` 两处调用 | 中 | 用可选参数(默认 None)向后兼容,不破坏既有调用 |
| R10 | **盘前策略集合会漂移**:用户可加自定义策略;信号质量表若硬编码策略 id 会漏 | 低 | 表由「预览里实际有行的策略」驱动(`results` 的 key),不硬编码;显示名服务端解析(复用 `_strategy_display_name`) |

---

## 关键锚点 (exact files/symbols/lines for planning)

**复盘链路(改动面):**
- `backend/app/services/market_recap.py` — `_SYSTEM_PROMPT`(:40)、`_build_user_prompt`(:177)、`recap_market_stream`(:253,AI 调用 :308-322,`done` :324)、`recap_market_once`(:327)
- `backend/app/services/market_recap_reports.py` — JsonReportStore `ai_market_recaps.json`,MAX 20
- `backend/app/api/market_recap.py` — POST `/analyze`(:40-66)、reports CRUD
- `backend/app/jobs/daily_pipeline.py` — `_run_scheduled_review`(:763)、`_stream_review_with_retry`(:831)、`_maybe_push_review`(:891)、`_register_review_job`(:936)、`REVIEW_JOB_ID`(:760);参照 `_premarket_pool_preview`(:1017)、`_pool_eod_persist`(:973)
- `backend/app/api/settings.py` — `PUT /preferences/review-schedule`(:1425)、`/review-push`(:1468)
- `backend/app/services/preferences.py` — `get_review_schedule`(:433)、`set_review_schedule`(:446)、`get_review_push_channels`(:460)、`REVIEW_PUSH_CHANNELS`(:425)
- `backend/app/services/ai_provider.py` — `stream_ai_text`(temperature/max_tokens 由调用方定)

**数据装配(消费面,零改动):**
- `backend/app/services/market_overview_builder.py` — `build_market_overview`(:345-580;无竞价列,勿改,新增独立装配服务)
- `backend/app/services/auction_columns.py` — `attach_auction_columns`(:89-150,probe×分区双闸门 + 末行去重)、`_attach_auction_volume_ratio`(:52-83)
- `backend/app/services/auction_probe.py` — `AuctionProbeStatus`(:28-33)、`AuctionProbeVerdict.to_dict`(:46-56)
- `backend/app/services/auction_sync.py` — `CANONICAL_AUCTION_COLS`(:32-35)、`sync_and_persist_auction`(:96-137)
- `backend/app/services/premarket_snapshot.py` — `load_premarket_snapshot`(:61-88)、`_PREMARKET_ROOT`(:29)
- `backend/app/services/premarket_pool.py` — `build_premarket_preview`(:32-74,provisional/degraded/probe)
- `backend/app/services/pool_snapshot.py` — `load_point_snapshot`(:102)、`snapshot_origin`(:93-94)
- `backend/app/services/pool_hub.py` — `_project_hub`(:55-163,投影与竞价列透传语义可参照)
- `backend/app/services/screener.py` — `run_all_with_hits`(:723,预览/EOD 同源)、`_load_enriched_for_date`(:245)、`PRESET_STRATEGIES`(:30)、`_strategy_display_name`(:205)
- `backend/app/api/pool.py` — GET `/premarket`(:117)、`/history`(:79);as_of 校验样板(:85-93)
- `backend/app/api/auction_history.py` — 历史竞价聚合读湖样板(分区存在性闸门语义)
- `backend/app/api/data.py` — GET `/auction-probe`(:626)、POST `/redetect`(:641)

**守卫与测试样板:**
- `backend/tests/test_pool_hub.py` — `_EXECUTION_TOKEN`(:858-860)、`test_pool_hub_no_execution_imports`(:895)、`test_build_pool_hub_has_no_write_path`(:913)
- `backend/tests/test_auction_probe.py` — probe injectable 模式(三态判定样板)
- 前端 `frontend/src/pages/Review.tsx`(报告 Markdown 渲染,内嵌面板零改动)、`frontend/src/lib/reviewStore.ts`(SSE 事件消费)

**数据现状(磁盘实测,2026-08-06):** `data/kline_auction/` 0 分区;`data/screener_results/` 0 快照;`data/premarket_results/` MISSING;`data/kline_daily_enriched/` 248 分区。
