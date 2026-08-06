# Phase 31 竞价复盘(REV-01..05)实施研究

**研究者:** ResearcherP31
**日期:** 2026-08-06
**前置输入:** `.planning/research/v2.2-decision-loop/RECAP-AUCTION.md`(领域研究,选项 A)+ `SUMMARY.md` Phase 31 段 + `.planning/REQUIREMENTS.md` REV-01..05
**研究方式:** 全部锚点源码实读核验(当前 HEAD = Phase 30 complete,即 Phase 28-30 已实现落地)
**置信度:** HIGH(所有装配/集成/调度锚点逐行核验;仅外部实时竞价源可用性与「盘后管道是否刷新 repo 最新日缓存」两处 [INFERENCE]/实施时核实)

---

## 0. 与 RECAP-AUCTION.md 相比的现状修正(研究时点 2026-08-06,HEAD 已含 Phase 28-30)

| 项 | RECAP-AUCTION.md 时点 | 当前实际(本次核验) | 对 Phase 31 的影响 |
|---|---|---|---|
| `attach_auction_columns_range` | 不存在(仅单日双闸门版) | **已存在**(`auction_columns.py:166-278`,BT-02,历史闸门=分区存在性,probe 不参与;docstring 明言「D-03 / REV-01」) | REV-01 历史 as_of 直接复用该原语,零新读逻辑 |
| 竞价族策略 id 集 | RECAP 列表含 `strong_open` | 实现落地为 `auction_validation.py:44-52` `_AUCTION_FAMILY_IDS` frozenset(9 个,含 `golden_230`、**不含** `strong_open`) | REV-03 族过滤**直接 import 该集合**(单一事实源,零漂移),不另立一份 |
| `open_gap` 是否存储列 | 「enriched 存储列,恒在」 | **非存储列**:`ENRICHED_STORAGE_SCHEMA`(backend/app/parquet.py:20-33)只有 15 列;`open_gap`/`change_pct` 由读路径 `compute_indicators` 即时计算(`indicators/pipeline.py:499-507,1328-1334`) | 「恒在」结论不变(由存储的 open/prev_close 恒可导出、确定性),但装配必须走 `_load_enriched_for_date` 等计算入口,不能期望 parquet 物理列 |
| market_recap 既有测试 | 「find them」 | **不存在任何 market_recap/review 测试**(全 tests 目录 grep `market_recap|recap_market_stream|ai_market_recaps|review_schedule|push_review_event` 零命中) | 现有行为无测试锁定 → REV-04 必须自带回归锁(协议不破坏的测试),并新增调度/集成测试 |
| `Review.tsx` 前端 | 「前端零改动」 | 大体零改动,但 **`Review.tsx:105` 有硬编码兜底字面量** `{ enabled:false, hour:15, minute:10 }`(prefs 拉取失败时展示) | 调度默认改 15:40 时此兜底字面量须同步改(1 行,非 Watchlist.tsx,允许触碰) |
| `premarket_results` 磁盘现状 | MISSING | 仍无真实预览文件(09:26 job 尚未在真实交易日产出过) | 验收全用 fixture(镜像 `test_premarket_pool.py` / `test_attach_auction_columns_range.py` 写盘模式) |

---

## 1. 现状核验(全部锚点)

### 1.1 复盘链路(`backend/app/services/market_recap.py`,共 356 行)

- `_SYSTEM_PROMPT`(:40-109):8 节编号模板(①定调 ②盘面总览 ③指数结构 ④板块主线 ⑤资金与情绪 ⑥消息催化 ⑦明日交易计划 ⑧风险提示)。**无任何竞价/盘前维度节**。模块 docstring 写「七节」实为 8 节(以代码为准)。
- `_build_user_prompt(overview, news, focus)`(:177-227):纯位置参数,内部拼「复盘日期/主要指数/盘面数据/市场情绪/概念板块排名/行业板块排名/近期市场新闻/关注点」。调用点唯一:`recap_market_stream` :313 `_build_user_prompt(overview, news or [], focus)`。
- `recap_market_stream(repo, quote_service=None, depth_service=None, as_of=None, focus="", news=None)`(:253-356):事件序 = `meta` → (AI 失败:`error` + `return`,**不发 done**) → AI `delta`* → `done`(:354)。as_of 解析:`build_market_overview` 内 `svc.latest_date()`(market_overview_builder.py:386),`overview["as_of"]` 为已解析字符串。
- `recap_market_once`(:327-356):累积全部 `delta` 成 content,`error` → 返回 `(None, meta)`。

### 1.2 调度链路(`backend/app/jobs/daily_pipeline.py`)

- `REVIEW_JOB_ID="scheduled_review"`(:760);`_run_scheduled_review`(:763-830):AI key 缺失 → 诚实 skip;成功 → `market_recap_reports.save_report` + `push_review_event(done archived)` + `_maybe_push_review`。异常全吞只记日志。
- `_stream_review_with_retry`(:831-888):最多 3 次(初次+2 重试),重试推 `retry` 事件清空前端累积;任何 `delta.content` 都累积进 content(→ 面板 delta 天然被归档/推送捕获)。
- `_maybe_push_review`(:891-933):按 `get_review_push_channels()` 推飞书/企微,**推全量 content**(→ 面板随全文送达)。
- `_register_review_job`(:936-957):`CronTrigger(mon-fri, Asia/Shanghai)`,misfire 7200。
- 相关时序锚点:`_POOL_EOD_JOB_ID`(:963)+ `_POOL_EOD_OFFSET_MIN=5`(管道后 +5min 落 EOD 股池);`_PREMARKET_JOB_ID`(:969-970)固定 09:26;盘后管道注册(:1139-1143)用 `preferences.get_pipeline_schedule()`。

### 1.3 调度偏好(`backend/app/services/preferences.py`)

- `get_review_schedule`(:433-444):**默认 `{"enabled": False, "hour": 15, "minute": 10}`**;已存偏好优先(`load().get("review_schedule", default)`)。
- `set_review_schedule`(:446-457):时间下限钳到 15:00(A 股收盘);`enabled=False` 时时间仍保存。
- `get_pipeline_schedule`(:329-342):**默认 `{"hour": 15, "minute": 30}`**(EOD 管道)。→ pre_eod 判定锚点。
- `get_review_push_channels`(:460+):渠道白名单 {feishu, wecom}。

### 1.4 设置 API(`backend/app/api/settings.py`)

- `GET /preferences`(:371-422):`review_schedule` 直接透传 `preferences.get_review_schedule()` → **后端默认值改动自动传播到前端**。
- `PUT /preferences/review-schedule`(:1425-1465):`ReviewScheduleIn{enabled, hour, minute}`;enabled 时 AI key 缺失 → 400;动态 `_register_review_job` / `remove_job(REVIEW_JOB_ID)`。

### 1.5 归档与 API(`market_recap_reports.py` + `api/market_recap.py`)

- 归档:`JsonReportStore("ai_market_recaps.json", MAX_REPORTS=20, id_prefix="mkr")`;报告结构 `{id, as_of, focus, content, summary, emotion_score, emotion_label, created_at}`。**content 是唯一正文载体 → 面板并入 content 即三跳全收,存储格式零改动**。
- API:`POST /analyze`(NDJSON 流)、`GET/POST/DELETE /reports`。手动路径:前端累积 delta 后 `POST /reports` 存全文 → 面板随手动归档。
- SSE:`api/intraday.py:196-199` `review_progress` 事件原样透传 `quote_service.push_review_event` 收到的 JSON。

### 1.6 前端(`frontend/src/lib/reviewStore.ts` + `pages/Review.tsx`)

- `reviewStore.ts`:手动流 `startReviewGeneration` 对**任意** `delta` 事件带 `content` 即追加(`evt.type === 'delta' && evt.content`),面板 markdown 无需任何「未知块」处理;`feedReviewEvent`(SSE 定时流)同语义,`retry` 清空累积。→ **delta 协议天然兼容,前端零解析改动**。
- `Review.tsx:721-725`:`MarkdownRenderer` 渲染全量 content(markdown),面板作为 `---` + `## 📊 竞价复盘` 独立节随流显示。
- `Review.tsx:105`:**硬编码兜底 `{ enabled: false, hour: 15, minute: 10 }`**(仅 prefs 拉取失败时生效)→ 默认改 15:40 时同步改此字面量。

### 1.7 数据装配(消费面,零改动)

- `auction_columns.py`:
  - `attach_auction_columns(df, trade_date, repo)`(:89-150):probe×分区双闸门(probe `available` + `kline_auction/date={d}/part.parquet` 存在且有行),symbol 级去重 `keep="last"`(09:25 最终撮合);`auction_volume_ratio` = 竞价量 ÷ 前5日均量(PIT-safe);canonical 列 `_AUCTION_REAL_COLS=("auction_volume","auction_amount")`。
  - `attach_auction_columns_range(df, start, end, repo) -> (df, enabled_dates)`(:166-278):历史闸门 = **分区存在性**(probe 不参与),返回 enabled_dates;注入按 (symbol,date) 左联;PIT-safe 向量化分母。**REV-01 历史 as_of 主闸门原语,直接复用**。
- `auction_probe.py`:`AuctionProbeStatus`(not_configured/fail_closed/available/error)、`AuctionProbeVerdict.to_dict` → `{status, source, probed_at, window:"09:15-09:25", fallback:"open_gap", detail}`;`resolve_auction_probe()`。
- `premarket_snapshot.py`:`load_premarket_snapshot(data_dir, as_of)`(:61-88):返回全量 payload(含 `results`),缺失/非法 → None(不抛);`_PREMARKET_ROOT="premarket_results"`、`_DATE_RE` 防路径穿越。
- `premarket_pool.py`:`build_premarket_preview`(:32-74):payload `{as_of, available, window:"pre_open", computed_at, provisional:true, degraded(=probe.status!="available"), probe, strategy_version, results}`;`results={sid:{total,as_of,rows}}` 来自 `run_all_with_hits`(与 EOD 同源单条代码路径)。行含 enriched 列(`open_gap`/`change_pct`/`close`)+ `hit_factors`。**绝不自算 open_gap**。
- `screener.py`:`run_all_with_hits`(:723-811;display_limit 截断 `dl>0 → rows[:dl], total=min(total,dl)`,带「基于展示行」语义);`_strategy_display_name(engine, sid)`(:205-216);`ScreenerService.latest_date()`(:~215);`_load_enriched_for_date(as_of)`(:245-280,所有路径均即时计算 open_gap/change_pct 且 JOIN instruments 补 name;**market_overview_builder.py:412 已有跨服务调用该私有方法的先例**)。
- `indicators/pipeline.py`:`open_gap = open/prev_close−1`(:499-507/:1328-1334);`change_pct = close/prev_close−1`。**均非存储列,读时计算**。
- `factor_hits.py`:`build_factor_hits(results, name_for)` → `{symbol: sorted[names]}`、`attach_factor_hits`(:19-55)。预览行已带 hit_factors → 共振统计只读复用。
- `pool_snapshot.py`:`load_point_snapshot`(:102-133),EOD 快照 payload 含 `snapshot_origin`。
- `guest_masking.py`:`mask_guest_hub`(symbol/name/code→`******`,剥 `open_gap`,pop `auction_columns` 存在性声明,保留 `change_pct/concept_board/hit_factors`)、`mask_guest_alert`(MON-06;保留 `provisional/degraded/window` 等状态标注,剥 `probe`/竞价值)。

### 1.8 Phase 29 可复用样板(REV-01/05 的镜像模板)

- `services/auction_validation.py`:只读装配服务 + `_AUCTION_FAMILY_IDS`(:44-52);probe 只解析一次作 provenance 透传。
- `api/research_auction.py`:`GET /api/research/auction/validation`;`Query date` 参数(非法 → FastAPI 422);`start>end → 400`;空态 → 200 `data_gate:"empty"`(绝不 404/500/0 填)。
- `tests/test_auction_validation.py`:6 项 AST 守卫(存在性/E1 无执行族 import/E4 GET-only/E3 无写路径+禁调用/E3 无 strategy_cache/import 白名单)。**注意其禁 import token 含 `premarket_snapshot|screener`** —— REV 需要 import 这两个面,守卫白名单必须按 REV 语义重订(见 §7.3)。

---

## 2. 实现方案(选项 A 定稿:确定性内嵌面板 + 可选 AI 点评,默认关)

### 2.1 新只读服务 `backend/app/services/auction_recap.py`

```python
def build_auction_recap(repo, as_of: date, engine=None, *,
                        probe_resolver=None, now=None) -> dict
def render_auction_recap_markdown(panel: dict) -> str        # dict → markdown(纯函数)
def build_auction_slice(panel: dict) -> str                  # 同一 dict → 精简切片(喂 LLM,单源)
```

- **as_of 单一来源**:`recap_market_stream` 场景由调用方传入 `overview["as_of"]`(与 AI 复盘同一天,绝不复解析);REV-05 端点解析自 query 或 `ScreenerService.latest_date()`。
- `engine` 仅用于显示名解析(`_strategy_display_name(engine, sid)`,元数据读,绝不计算);`None` 时非 PRESET 策略名退化为 sid(诚实)。
- `probe_resolver` / `now` 为测试注入点(镜像 `premarket_pool.build_premarket_preview` 的注入模式与 `test_auction_probe.py` 三态 fixture)。
- 返回 dict(非 markdown):`{as_of, data_completeness, blocks: {real_auction_activity?, open_gap_snapshot, preopen_signal_quality?}, built_at}`;渲染与 AI 切片是独立纯函数 → 服务可单测、切片与面板天然同源(REV-04 验收 6 的「不双源漂移」由构造保证)。

### 2.2 复盘集成(REV-04)

`recap_market_stream` 内改动(其余文件不动):

```
overview = build_market_overview(...)
as_of_str = overview.get("as_of"); if not as_of_str: error+return
panel = build_auction_recap(repo, date.fromisoformat(as_of_str))   # 与 overview 同日
yield meta
try:
    slice = build_auction_slice(panel) if preferences.recap_auction_commentary else None
    sys = _SYSTEM_PROMPT + (GUARDRAIL 行 if slice else "")
    user = _build_user_prompt(overview, news or [], focus, auction_slice=slice)
    ... AI delta 流 ...
except: error + return          # AI 失败 → 不发面板(契约保持,见 §6.5)
if panel 存在任何 present 块:
    yield delta(render_auction_recap_markdown(panel))   # 面板 delta,在 done 前
yield done
```

- 事件序锁死:**AI delta → 面板 delta → done**(REV-04 验收 1)。
- 面板三块全缺席 → **不 yield 面板 delta**,复盘退化为现有纯 AI 报告(REV-04 验收 5,协议不破坏;回归锁测试)。
- `_build_user_prompt` 签名:`(overview, news, focus, auction_slice: str | None = None)`(R9:可选参数默认 None,现有调用零改动)。
- 归档/SSE/飞书:content 累积即含面板(delta 机制天然覆盖三跳,`market_recap_reports.py`/`api/market_recap.py`/`_maybe_push_review` **零改动**)。

---

## 3. 三块装配细节

### 3.1 Block 1 `real_auction_activity`(条件式:湖有数据才亮)

**闸门(按 as_of 分治,REV-01/R5 铁律):**

| as_of | 闸门 | 实现 |
|---|---|---|
| `== cn_today()` | **probe×分区双闸门**(镜像 `attach_auction_columns` :95-121) | 直接读湖分区 + probe 判定;probe 非 available 或分区缺失 → 块省略 |
| `< cn_today()`(历史) | **分区存在性主闸门**(probe 不参与,镜像 `attach_auction_columns_range` :178-182 语义) | 分区存在且有行 → 亮;否则省略(历史日绝无 `pre_eod`,只有 `no_auction_lake`) |

**装配(纯读湖):**
1. 分区路径 `data/kline_auction/date={as_of}/part.parquet`;读入后按窗口谓词过滤(见下)再 `unique(subset=["symbol"], keep="last")`(09:25 最终撮合,镜像 auction_columns.py:146)。
2. 竞价金额 Top N:按 `auction_amount` desc 取 10,JOIN instruments(`repo.get_instruments_asset`)补 name(历史日可复用 `_load_enriched_for_date` 帧的 name 列)。
3. 竞价总额:sum(auction_amount);竞价标的总数:n_symbols。
4. 竞价量比子块(条件):`auction_volume_ratio` 需前 5 日均量分母(不含当日,PIT-safe)。**优先路径**:在 as_of 的 enriched 帧上复用 `attach_auction_columns_range([start,as_of] 6 交易日窗口, as_of, as_of, repo)` 取注入后的 ratio 列(零新 ratio 代码);实现时二选一(见 §9 风险 R11)。分母不可得 → 子块省略 + 注记,绝不 0 填。

**读时窗口谓词(REV-02 验收 2 的回归锁,防御纵深):**
- 湖写路径(`auction_sync.py:107-115`)已结构性排除 09:30+ 连续竞价 bar(既有测试锁定写侧);面板读侧再加一道**只读窗口过滤** `[09:15:00, 09:25:59]`(镜像 `auction_probe._has_in_window_rows` 语义),然后才 `keep="last"` —— 保证 fixture 注入 09:30+ 行时面板仍取 09:25 行,「09:30+ 永不进竞价列」在面板级可测。

**provenance:** `source:"kline_auction"` + 行级标注「真实竞价列」;probe 判定透传(仅 provenance,历史日不参与闸门)。

### 3.2 Block 2 `open_gap_snapshot`(恒在,唯一恒真档)

- 数据源:`ScreenerService(repo)._load_enriched_for_date(as_of)` 的 `open_gap` 列(读时计算,恒可导出;历史日/EOD 口径与 09:26 预览口径**一致**——open 在 09:25 撮合已定盘,prev_close 同日不变)。
- 输出:高开分布(≥2% / ≥5% 家数与占比)、高开家数、均值、open_gap Top N(带 name)。
- enriched 帧缺失 → 块省略 + 显式注记(理论上复盘能跑即有 overview,此情形为防御分支;不入枚举专名)。
- provenance:`source:"kline_daily_enriched(open_gap 读时计算)"`;注记「open_gap 基于 enriched 复权口径」(R7)。

### 3.3 Block 3 `preopen_signal_quality`(核心卖点,条件式:预览在才亮)

**装配:**
1. `load_premarket_snapshot(data_dir, as_of)`;None → 块省略 + `no_premarket_preview`。
2. 策略集 = **`_AUCTION_FAMILY_IDS`(import 自 auction_validation.py:44,单一事实源,零硬编码漂移)∩ payload["results"].keys()**(REV-03 验收 1/REV-10:只含预览里实际有行的竞价族策略;`strong_open`/`auction_intraday_confirm` 盘前空池 → 不出现,天然满足)。
3. 逐策略统计(行 = 预览冻结命中行):
   - `n`(命中数;`display_limit>0` 截断时标注「基于展示行(display_limit 截断)」)
   - 平均 `open_gap`、平均 `change_pct`(**EOD 口径**,见下)、开盘兑现率(open_gap≥2%)、收盘兑现率(change_pct≥2%)、收阳率(close>open)
4. **EOD 口径 join(R6 铁律)**:预览行 `change_pct ≈ open_gap`(09:26 close=开盘价),绝不直接用作收盘兑现率 → 按 symbol 左联 EOD enriched 帧的 `change_pct`/`close`/`open`(与 Block 2 同一帧)。预览行有而 EOD 帧缺行(停牌/退市 T+1)→ 计 `n_missing`,不 0 填/不前向填充(镜像 Phase 29 `n_missing_outcomes` 语义)。
5. 交叉共振子块(读预览行自带 `hit_factors`):`len(hit_factors) >= 2` 的标的聚合同一组兑现率(复用 `build_factor_hits` 语义,只读)。
6. 前 EOD 时刻(as_of==今日 且 now < 管道调度时刻):close 非终值 → `change_pct` 系统计(收盘兑现率/收阳率)**省略 + 注记「EOD 收盘兑现率待盘后管道完成后更新」**,`open_gap` 系统计照常(open 已定盘)。
7. provenance:`provisional:true`(预览非定稿)+ `degraded:true → 「盘前信号基于派生因子(非真实竞价数据)」` + 表头注记「基于盘前预览·非收盘定稿」。

### 3.4 面板 markdown 结构(确定性数据,REV-02 验收 3)

```markdown
---
## 📊 竞价复盘(确定性数据,非 AI 生成)

> 数据来源:冻结资产(kline_auction 湖 / 盘前预览 / enriched)。本面板为确定性聚合,非 AI 生成。

### 真实竞价活跃度(当块 present)
- 竞价总额 / 竞价标的总数 / 竞价金额 Top 10 / (竞价量比子块)
- 注记:pre_eod →「盘后竞价同步未完成,建议 15:35 后重跑」;no_auction_lake →「当日无竞价湖数据」

### 开盘涨幅快照(恒在)
- 高开分布(≥2% / ≥5%)/ 高开家数 / open_gap Top 10

### 盘前信号质量(当块 present)
- 表:策略 | N | 平均 open_gap | 平均 change_pct(EOD) | 开盘兑现率 | 收盘兑现率 | 收阳率
- 表头注记:「基于盘前预览·非收盘定稿」;degraded 注记;display_limit 注记;n_missing 注记
```

---

## 4. data_completeness 语义(REV-02,定稿)

枚举 `{full, no_auction_lake, no_premarket_preview, pre_eod, partial}`。**单头标签按优先级取值,块级 provenance 保真,两者互补:**

```
优先级(高→低):
1. pre_eod           as_of==cn_today() 且 kline_auction/{as_of} 分区缺失
                     且 now < preferences.get_pipeline_schedule()(默认 15:30)
                     → 「盘后竞价同步未完成」;real_auction_activity 省略
2. no_auction_lake   分区缺失但非 pre_eod(历史日;或今日已过同步点、湖仍空/probe 不可用)
3. no_premarket_preview  premarket_results/{as_of} 缺失 → preopen_signal_quality 省略
4. partial           防御性兜底(当前规则下 1-3 覆盖所有缺块场景,保留枚举值)
5. full              三块全在
```

- **pre_eod 探测答案(上下文问题)**:分区存在性为**主闸门**,probe 仅作 provenance;`pre_eod` vs `no_auction_lake` 的判别 = `(as_of==今日) ∧ (分区缺失) ∧ (now < 管道调度时刻)`。历史日永不 pre_eod。
- 每块 `blocks[name] = {present: bool, note: str, source: str}`:缺失理由逐块显式,不依赖头标签反推(信息零丢失)。
- 语义全部可注入 `now` 与 probe fixture 确定性测试(镜像 test_auction_probe 三态)。

---

## 5. 调度变更(默认 15:40,向后兼容)

- `preferences.get_review_schedule`(:433-444):默认 `minute` 10 → **40**(docstring 同步:理由 = 竞价同步 15:30 + 股池持久化 15:35 之后,三块全亮);`set_review_schedule` 下限 15:00 **不动**(早跑 → `pre_eod` 诚实标注,是特性不是错误)。
- **向后兼容铁律**:`load().get("review_schedule", default)` 语义保证——已保存过调度的用户**保留原值**(可能仍是 15:10 → pre_eod 标签兜住诚实性);只改「未设置过」用户的默认。GET /preferences 透传后端默认 → 前端自动跟随。
- **前端 1 行改动**:`Review.tsx:105` 兜底字面量 `minute: 10 → 40`(仅 prefs 拉取失败时生效;非 Watchlist.tsx)。
- 注册/API 面(`_register_review_job` / `PUT /preferences/review-schedule`)零改动。

---

## 6. 复盘集成契约(REV-04,定稿)

| 契约 | 规则 |
|---|---|
| 事件序 | `meta` → AI `delta`* → 面板 `delta`(有 present 块时)→ `done` |
| 归档 | content 含面板(recap_market_once / 定时 `_stream_review_with_retry` / 手动前端累积,三路全收);`ai_market_recaps.json` 结构与字段**零改动** |
| 飞书/企微 | `_maybe_push_review(content, meta)` 推全量 content → 面板送达,零改动 |
| SSE 实时 | `push_review_event` 原样透传面板 delta → `review_progress` → `feedReviewEvent` 按 delta 累积,前端零改动 |
| 面板全缺席 | 不 yield 面板 delta → 退化为现有纯 AI 报告(协议不破坏,回归锁) |
| AI 失败 | 现契约保持:`error` + return,**不发面板兜底**(R8 决策点:若产品要「AI 失败 → 仅确定性面板 + 诚实说明」,须单独评审改契约,本期不做) |
| AI 点评(可选,默认关) | 偏好 `recap_auction_commentary`(bool,默认 False,preferences.py 新增 + settings API `PUT /preferences/recap-auction-commentary`;前端开关为 P2,API-first);开启时切片 = `build_auction_slice(panel)`(**与面板同一 dict,构造性单源,REV-04 验收 6**) |
| 护栏 | 开启点评时,调用侧在 system 内容末尾追加一行:`「竞价数据只引用下方切片中给出的数值;数据缺失时明说『今日无竞价数据』,禁止编造;与确定性面板冲突时以面板为准。」`(`_SYSTEM_PROMPT` 常量本身**不动**,向后兼容) |
| `_build_user_prompt` | 加可选参数 `auction_slice: str|None=None`,非 None 时追加 `## 竞价复盘数据(确定性切片)` 节(默认 None → 输出与现状逐位一致,R9) |

---

## 7. REV-05 独立只读端点(P2,本期纳入)

### 7.1 新模块 `backend/app/api/market_recap_auction.py`(与 research_auction.py 同款独立面)

```python
router = APIRouter(prefix="/api/market-recap", tags=["market-recap"])
@router.get("/auction")
def get_auction_recap(request: Request, as_of: str | None = Query(None)) -> dict
```

- **不把 GET 塞进现有 `api/market_recap.py`**:该模块有 POST/DELETE 路由,GET-only 守卫断言整模块会破坏现状;独立模块使守卫可整体断言(镜像 `research_auction.py` 模式)。main.py:871 后追加 `include_router(market_recap_auction.router)`。
- `as_of` 严格校验:`^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat`(镜像 `api/pool.py:85-100` 双重校验防路径穿越);缺失 → `ScreenerService.latest_date()`(与复盘缺省口径一致);非法 → 400。
- 复用 `build_auction_recap` + `render_auction_recap_markdown`(端点返回 dict + markdown 双形或仅 dict,与面板同源,REV-05 验收 4)。
- **诚实空态**:无任何块 → `200 {available:false, data_completeness, blocks:{}, reason:"..."}`,绝不 404/500/0 填(镜像 auction_history 空态契约)。
- **guest 脱敏**:镜像 `mask_guest_hub`/`mask_guest_alert` 语义——per-symbol 身份(symbol/name/code → `******`)、per-symbol 竞价值与 open_gap **剥离**;聚合统计(家数/占比/兑现率)与状态标注(`provisional/degraded/data_completeness`)保留;`probe` verdict 剥离(镜像 mask_guest_alert 剥 probe 先例)。**精确 guest DTO 字段清单留待实现/规划锁定**(见 §9 风险 R12)。

### 7.2 POOL-03 AST 守卫(镜像 test_auction_validation.py 6 项,按 REV 语义重订白名单)

- 守卫目标:`api/market_recap_auction.py` + `services/auction_recap.py`。
- `_EXECUTION_TOKEN`(broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托)照抄。
- 禁 import token(REV 版):`auction_sync|pool_snapshot|pool_backfill`(**不再含 premarket_snapshot/screener** —— REV 必须 import 二者:预览装载 + `_load_enriched_for_date`/`_strategy_display_name`)。
- 禁调用 token:`run_all|run_preset|write_cache|persist_point_snapshot|save_report`(import screener/auction_validation 是惰性元数据面,调用触发面才禁;与 E5 语义一致)。
- `_WRITE_PATTERNS` 照抄(open w/wb/a、write_parquet、os.replace、unlink、mkdir)。
- import 白名单:`_IMPORT_PREFIXES = {app.services.auction_probe, app.services.auction_columns, app.services.auction_validation, app.services.premarket_snapshot, app.services.screener, app.services.auction_recap, app.services.guest_masking, app.tickflow.repository, app.strategy.engine, app.market_time}`;`_IMPORT_EXACT = {polars, fastapi, __future__, datetime, typing, logging, pathlib, re, ast, collections.abc}`。
- GET-only 断言仅作用于新 api 模块。
- 守卫必须「存在且非空」防悬空(镜像 test_validation_modules_exist)。

---

## 8. 验收口径(REV-01..05 → 测试映射)

| 需求 | 验收 | 测试 |
|---|---|---|
| REV-01 | 无分区 → real 块缺席 + `no_auction_lake` + JSON 可序列化;有预览 → 信号表只含预览有行的族策略;AST 守卫;绝不调 `run_all_with_hits` | `test_auction_recap.py::test_no_auction_partition_omits_block` 等 + `test_auction_recap_guard.py` |
| REV-02 | probe 三态标注逐字正确;09:30+ 行永不进竞价列(回归锁);「确定性数据,非 AI 生成」标识;游客/无配置下 open_gap_snapshot 仍在 | `test_auction_recap.py`(probe 三态 fixture 镜像 test_auction_probe;窗口谓词 fixture 写 09:31 行) |
| REV-03 | fixture 预览(3 策略含 open_gap/hit_factors)+ fixture EOD enriched → 手算一致;预览缺失 → 块省略 + `no_premarket_preview`;EOD 口径注记;display_limit 注记 | `test_auction_recap.py::test_signal_quality_hand_computed`(手算断言,镜像 test_attach_auction_columns_range 的 hand-computed 风格) |
| REV-04 | 事件序 AI delta→面板 delta→done;`recap_market_once` 含面板;归档含面板;飞书 webhook fixture 含面板;面板全缺席 → 退化为纯 AI(回归锁);点评开启 → 切片与面板同源 | `test_market_recap_delta.py`(monkeypatch stream_ai_text 假流;webhook fixture 镜像既有推送测试) |
| REV-05 | 端点只读、GET-only、无写路径;空态 200;as_of 严格校验 400;guest 掩码;与 REV-04 面板同源(同一装配函数) | `test_auction_recap_endpoint.py`(TestClient + guest/vip stub 中间件镜像 test_auction_history.py:79-92) |

---

## 9. 风险与开放问题

| # | 风险/问题 | 级别 | 处置 |
|---|---|---|---|
| R1 | 时序缺口(默认调度 < 竞价同步) | 高 | **已由调度默认 15:40 决策消解**;早跑/用户旧偏好 → `pre_eod` 诚实标注 |
| R2 | 外部竞价源不可验证(`kline_auction` 空湖,probe 依赖外部源 [INFERENCE]) | 高 | 条件式交付;验收全 fixture;`open_gap_snapshot` + 信号质量无源也可交付 |
| R3 | AI 点评幻觉 | 中 | 默认关 + 切片护栏 + 面板为准(§6) |
| R5 | 历史 as_of 的 probe 闸门语义 | 中 | **已定稿**:今日走双闸门(镜像 attach_auction_columns)、历史日走分区闸门(镜像 attach_auction_columns_range);面板直接读湖 + 自持窗口谓词/去重,不动 Phase 29 原语 |
| R6 | 预览 change_pct ≈ open_gap 漂移 | 中 | 信号质量一律 join EOD enriched 口径;预览列绝不作收盘兑现率来源 |
| R7 | 除权日 prev_close 对齐 | 低 | 注记「open_gap 基于 enriched 复权口径」;fixture 覆盖 |
| R8 | AI 失败时面板是否兜底 | 决策点 | 本期**不做兜底**(保持契约);如产品要,单独评审 |
| R9 | `_build_user_prompt` 签名变更 | 中 | 可选参数默认 None,向后兼容 |
| R10 | 盘前策略集合漂移 | 低 | 族过滤 = `_AUCTION_FAMILY_IDS`(import 单一事实源)∩ 预览 keys;自定义盘前策略不进面板(与 Phase 29 同范围,文档注明) |
| R11 | 竞价量比子块分母来源 | 低-中 | 优先复用 `attach_auction_columns_range`(6 交易日窗口)取 ratio;实现时二选一(该原语 vs 窄读 volume 自算),分母不可得 → 子块省略 + 注记 |
| R12 | REV-05 guest DTO 精确字段清单 | 低 | 语义已定(mask_guest_hub/mask_guest_alert 镜像);清单实现/规划时锁定 |
| R13 | **[INFERENCE]** 盘后管道(15:30)是否刷新 repo 最新日缓存:15:40 复盘时 `_load_enriched_for_date(T)` 可能命中 live 内存帧(close=盘中值)而非 EOD 终值 | 中 | 实施时核实 `run_pipeline`/quote_service flush 是否刷新缓存(与 MON R1 同族);若未刷新,`change_pct` 系统计按 §3.3 第 6 条「前 EOD 时刻」规则处理(注记+省略),或管道侧补刷新(另评) |
| R14 | `attach_auction_columns_range` 签名/行为以当前实现为准 | 低 | 本文件已逐行核验(:166-278);实施时直接调用,不再假设 |
| R15 | Review.tsx:105 兜底字面量 | 低 | 1 行改动(非 Watchlist.tsx) |

---

## 10. 新增测试 + 保持绿色

### 新增(3 个测试文件,镜像既有样板)

1. **`backend/tests/test_auction_recap.py`** — 服务单测:
   - fixture:`repo_env`(镜像 test_attach_auction_columns_range.py:24-38)+ `_write_auction_partition`(含 09:30+ 行变体)+ `_write_premarket_preview`(3 策略,含 open_gap/hit_factors/degraded 变体)+ EOD enriched 写盘 + probe 三态 monkeypatch + 冻结 `now`。
   - 覆盖:REV-01(无分区/JSON 可序列化/策略集 = 族∩预览)、REV-02(三态标注逐字/09:30+ 回归锁/「确定性数据,非 AI 生成」/open_gap_snapshot 恒在)、REV-03(手算一致/预览缺失/n_missing/display_limit 注记/pre-EOD change_pct 注记)、pre_eod vs no_auction_lake 判别(注入 now 与管道调度)。
2. **`backend/tests/test_auction_recap_guard.py`** — POOL-03 AST 守卫(§7.2 六项,镜像 test_auction_validation.py 结构)。
3. **`backend/tests/test_market_recap_delta.py`** — 集成:事件序(monkeypatch `stream_ai_text` 假流)/`recap_market_once` 含面板/归档含面板(JsonReportStore tmp 目录)/面板全缺席退化回归锁/`_build_user_prompt` 向后兼容(无 auction_slice 输出逐位不变)/点评开启 → system 护栏 + user 切片/调度默认 15:40 + 已存偏好保留 + 下限 15:00。
4. **`backend/tests/test_auction_recap_endpoint.py`** — REV-05:GET-only 守卫已在 guard 文件;端点 200 空态/as_of 400/guest 掩码(镜像 test_auction_history.py guest/vip stub 中间件)/与面板同源。

### 保持绿色(现有,零改动)

`test_pool_hub.py`(守卫不涉 REV 模块)、`test_auction_validation.py`(Phase 29 守卫:禁 import 面含 premarket_snapshot/screener,REV 不触碰该模块 import 面)、`test_attach_auction_columns_range.py`、`test_premarket_pool.py`、`test_auction_history.py`、`test_auction_probe.py`、`test_auction_sync.py`、`test_auction_columns.py`、`test_auction_strategy_family*.py`、`test_guest_masking.py` 及全仓其余。**现状无任何 review/market_recap 测试**(已核验)→ 不存在会被调度默认值/复盘协议改动破坏的既有测试,新测试自带回归锁补位。

---

## 11. 关键锚点(实施/规划引用)

**改动面(6 个文件):**
- `backend/app/services/auction_recap.py`(新建,§2.1/§3/§4)
- `backend/app/services/market_recap.py` — `recap_market_stream`(:253-356,面板 delta 在 :354 done 前)、`_build_user_prompt`(:177-227,可选参)、AI 失败路径(:322-325 保持)
- `backend/app/services/preferences.py` — `get_review_schedule`(:433-444 默认 40)、新增 `recap_auction_commentary`(get/set,默认 False)
- `backend/app/api/settings.py` — 新增 `PUT /preferences/recap-auction-commentary`(镜像 :1425-1465 结构)
- `backend/app/api/market_recap_auction.py`(新建,§7.1)
- `backend/app/main.py`(:871 后 include router)
- `frontend/src/pages/Review.tsx`(:105 兜底字面量 minute 10→40;P2 可加点评开关,不做也行——API-first)

**零改动(消费面):** `auction_columns.py`、`auction_probe.py`、`premarket_snapshot.py`、`premarket_pool.py`、`screener.py`、`auction_validation.py`(仅 import 其 `_AUCTION_FAMILY_IDS`)、`market_recap_reports.py`、`api/market_recap.py`、`guest_masking.py`、`frontend/src/lib/reviewStore.ts`、`frontend/src/pages/Watchlist.tsx`(off-limits,全程不触碰)

**测试样板:** `test_pool_hub.py:858-963`、`test_auction_validation.py:1-140`(守卫结构)、`test_attach_auction_columns_range.py:24-83`(repo_env/写盘 fixture)、`test_premarket_pool.py:1-63`(FIXED_DATE/写 canned 策略)、`test_auction_history.py:79-92`(guest/vip stub 中间件)、`test_auction_probe.py`(probe 三态注入)

**时序事实(调度决策依据):** 09:10 instruments / 09:26 盘前预览(固定) / 15:02 depth 定版(默认) / **15:30 EOD 管道(默认)** / **15:35 EOD 股池持久化(管道+5min)** / 复盘默认 15:10(disabled)→ **改 15:40**。
