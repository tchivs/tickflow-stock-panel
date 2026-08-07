# 部署验证清单 — 真实交易日确认项 (DEPLOY-VERIFICATION-CHECKLIST)

**Consolidated:** 2026-08-06 · **Owner:** 部署运维 (deploy operator：可访问后端日志、data 目录、设置页、外部投递)
**来源:** v2.1 audit open items + v2.2 audit tech_debt + Phase 27/30/31 UAT（详见 LEGACY-COMPLETION.md §4）
**纪律:** 每一项都是「真实交易日观察」，sandbox 已用注册形 grep / 存储隔离测试 / e2e 锁死代码侧；本清单只确认部署环境的真实行为。诚实铁律：探到不可用 → 列出缺失 + fail-closed；空湖 → 200 `{data_gate:"empty"}`；绝不伪造/静默回填。

---

> **Orchestrator 批准 (2026-08-06):** 合并 v2.1/v2.2 audit open items + Phase 27/30/31 UAT（详见 LEGACY-COMPLETION.md §4），批准为本部署操作手册。
> **Owner:** 部署运维 (deploy operator)。**来源纪律:** 与源文件三行一致 — 每一项都是「真实交易日观察」，诚实铁律不变。
> **D3 为条件项:** 依赖外部实时竞价源 gate（需提供 `auction_unmatched_volume` + `auction_virtual_price` 两输入列，判定见 features.md「竞价列与派生列」节）；当前未配置 → fail-closed 通过态（probe 非 available → 全链路诚实降级，系统不报错），不影响 D1/D2/D4-D7。
> source: .planning/research/v2.3-data-depth/DEPLOY-CHECKLIST.md — 更新时两处同步。

---

## 时序总览（单交易日节奏，Asia/Shanghai）

| 时刻 | 系统动作 | 本清单项 |
|------|----------|----------|
| 09:10 | instruments 同步（偏好） | — |
| **09:26** | 盘前预览 job + 盘前监控尾段 | **D1**（09:26 cron）+ **D4**（监控 payload/close 语义） |
| 15:00 | 收盘 | — |
| 15:02 | depth 定版（默认） | — |
| **15:30** | EOD 管道（偏好默认） | **D2**（EOD cron + 缓存刷新）+ **D6**（R13 语义） |
| 15:35 | EOD 股池持久化（管道+5min） | D2 |
| **15:40** | 定时复盘（默认关，启用后） | **D5**（复盘 + LLM 点评） |
| 任意日 | 概念 drift 探针（operator 手动） | **D7**（OQ-3） |
| 条件触发 | 外部实时竞价源接入后 | **D3**（tier-2 盘前真实竞价列 + kline_auction 湖 + BT-07 gate） |

> 调度时间均可经设置页偏好调整（`preferences.py:329-332` 管道 / `:434-444` 复盘 / `:405-407` depth）；以下以默认值为准。09:26 为硬边界固定（daily_pipeline.py:966-968）。

---

## D1 — 09:26 盘前预览 cron 真实触发（v2.1 PM-01；v2.1 audit open #1）

**验证什么**：09:26 调度真实运行盘前预览 job，独立存储落盘，绝不污染 strategy_cache/screener_results。

**在哪看**：
- 后端日志：`scheduled premarket_pool_preview completed: job_id=…`（`_run_tracked` daily_pipeline.py:723-753）；单飞语义（若 09:26 有手动任务在跑 → 日志「跳过」）。
- 数据目录：`data/premarket_results/date={T}/part.json` 存在。

**通过标准（pass criteria）**：
1. `premarket_results/date={T}/part.json` 存在，payload 含 `window:"pre_open"`、`provisional:true`、`computed_at`、`probe` 判定、`degraded`（`premarket_pool.py:80-90`）。
2. `degraded` 诚实：外部竞价源未配置 → `degraded:true` + probe status 非 available（`:86`）；配置后应翻 `false`（联动 D3）。
3. **隔离断言**：当日 `data/strategy_cache/` 与 `data/screener_results/date={T}/` 无盘前 job 写入（比对 09:25 前后目录状态；EOD 15:30 之后 screener_results 有 T 是正常的——那是 EOD 快照，非盘前）。
4. 前端盘前视图可见该日预览（窗口标注 + 15:35 回退 EOD 语义不变）。

**顺序**：D1 在任何竞价源接入前即可做（诚实 degraded 也是通过态）。

---

## D2 — 15:30 EOD 管道 cron + 缓存刷新 + 15:35 股池持久化

**验证什么**：调度 EOD 管道完整跑完（日K/enriched/指数/ETF/竞价 stage/视图刷新），管道后内存缓存刷新（live_agg 基准正确），EOD 股池冻结快照落盘。

**在哪看**：
- 后端日志：`scheduled daily_pipeline completed` + 各 stage emit（sync_daily/compute_enriched/refresh_views…）。
- 数据目录：`data/kline_daily_enriched/date={T}/part.parquet` 存在（15 列）；`data/screener_results/date={T}/` EOD 冻结快照（15:35+5min 的 `pool_eod_persist` job，daily_pipeline.py:1154-1162）。

**通过标准**：
1. 当日 enriched 分区落盘且可读（`pl.read_parquet` 成功，行数 >0）。
2. 日志出现缓存刷新（`_pipeline_then_refresh` finally 必刷，daily_pipeline.py:1135）；**次日开盘连板梯队正确**（live_agg 基准 = 上一交易日，不整体少算一档 —— 这是 ce5c705 修复的原始症状，repository.py:770-784 `_live_agg_baseline_date`）。
3. EOD 股池快照 `screener_results/date={T}/` 落盘带 `snapshot_origin:"eod"`。
4. `data/kline_auction/` 行为按竞价源配置：未配置 → 0 分区（stage 记 skipped）；配置 → 当日分区出现（联动 D3）。

**顺序**：首个真实交易日与 D1 同天观察。

---

## D3 — tier-2 盘前真实竞价列 + kline_auction 湖数据流（v2.1 audit / v2.2 audit 共享 gate；BT-07 前置）

**验证什么**：外部实时竞价源接入后（配置自定义源 auction 数据集 + `auction_sync_enabled` 偏好，daily_pipeline.py:695-705 双闸门），竞价数据全链路真实点亮；未接入 → fail-closed 诚实（本项跳过，判定条件已写）。

**在哪看**：
- `GET /api/data/auction-probe`（data.py:626-640，30s TTL）→ `status:"available"`。
- 数据目录：`data/kline_auction/date={T}/part.parquet` 累积分区（源提供委托量输入列时为 6 列：canonical 4 + `auction_unmatched_volume`/`auction_virtual_price`；否则 4 列，诚实缺列）。
- UI：股池钻取 VIP 行出现「真实集合竞价」组（真量/真额）+ 派生组「派生 · 虚拟成交」（输入列可得时）+ 竞价徽标；竞价历史图（`GET /api/kline/auction/history`）有行。

**通过标准**：
1. probe available 且 /api/kline/auction/history 返回真实行（末行聚合 09:25 最终撮合 + row_count/min/max_datetime 粒度）。
2. `attach_auction_columns` 读路径注入（auction_columns.py:107-151）；池 hub `auction_columns:{real,derived}` 声明与分区实际列一致（PIT-3：声明驱动 UI）。
3. 派生 `auction_unmatched_amount` 仅在两输入列可得时出现，UI 标「估算」。
4. 09:30 连续竞价 bar 绝不标集合竞价（窗口谓词回归锁）。
5. **BT-07 再评估**（v2.2 audit:25/84）：湖积累足够历史分区后（建议 ≥20 交易日），复评「全量竞价回测」是否纳入 v2.4；gate = 湖有足够历史分区。

**未配置时的通过态**：probe 非 available → 全链路 fail-closed（空态 200 available:false / 无竞价列 / degraded 徽标），系统不报错不 500。这也是通过（诚实），无需 action。

**顺序**：独立于 D1/D2，何时接入竞价源何时做。

---

## D4 — 09:26 盘前监控 payload / close 语义 + 外部投递（v2.2 MON UAT-1 + OQ-1）

**验证什么**：盘前监控规则在 09:26 真实评估、事件落库并投递；payload 的 close/change_pct 语义与 fail-closed 双保险在真实数据下成立。

**在哪看**：
- 后端日志：`premarket_pool_preview` 尾段 preopen 评估摘要（daily_pipeline.py:1064-1078 `evaluate_premarket_alerts`，失败非致命 → `preopen_eval.skipped`）。
- 数据库：`alert_events` 落库（`record_alert_event` persist-first，落库成功才广播 SSE → webhook）。
- 投递：SSE（开着 Monitor 页可见）+ 飞书/Telegram（若配置）。
- 前端：Monitor 页事件徽标「盘前 · 非最终」（provisional）与「数据降级」（degraded）。

**通过标准**：
1. 配置一条 preopen 规则（白名单 5 字段之一：open_gap/auction_volume/auction_amount/auction_volume_ratio/auction_unmatched_amount，monitor_rules.py:47-50）→ 09:26 命中 → alert_events 行存在 + 投递到达。
2. 事件携带 `provisional:true` + `degraded=<payload.degraded>` + `probe`（monitor.py:590-598）；`change_pct`/`price` 恒 None（EOD 列禁用 + eval 帧 change_pct=None 双 fail-closed，preopen_eval.py）。
3. **OQ-1 首次真实 payload 核验**：确认今日 enriched 帧在 09:26 的 close 语义（[INFERENCE] change_pct≈open_gap）——观察预览行 open_gap 与当日 EOD change_pct 的关系，记录到运维笔记；若发现异常语义（close=盘中/前收混入），报回开发按 fail-closed 收紧白名单。
4. degraded 路径：竞价源未配置时 auction 类规则 0 命中（`_build_condition_mask` 缺列 → head(0)，monitor.py:283），open_gap 规则仍可命中且事件带 `degraded:true`。

**顺序**：首个真实交易日；D1 通过后立即做。

---

## D5 — 15:40 定时复盘 + 可选 LLM 点评（v2.2 REV UAT-1/2）

**验证什么**：15:40 定时复盘真实触发，确定性竞价面板随数据完整性亮起，归档/投递同含面板；开启 AI 点评后 live-model 只引用切片值。

**在哪看**：
- 设置页：复盘调度默认 15:40、默认**关**（preferences.py:434-444）——先启用。
- 后端日志：`scheduled_review` 流式事件（meta → AI delta → 面板 delta → done，事件序锁死）；`scheduled review saved: as_of=…`。
- 数据目录：复盘归档（market_recap 存档）。
- 前端：Review 页复盘正文尾部「📊 竞价复盘(确定性数据，非 AI 生成)」面板。
- 投递：归档报告 + 飞书推送含面板（delta 机制三跳全收）。

**通过标准**：
1. 15:40 后（15:30 同步 + 15:35 持久化之后）复盘面板三块按 data_completeness 亮起：
   - Block 1 真实竞价活跃度：竞价源已配置 → present（湖分区 + 窗口谓词）；未配置 → `{present:false, note:"当日无竞价湖数据"}` 诚实。
   - Block 2 开盘涨幅快照：恒在块（open_gap 读时计算，enriched 可得时 present）。
   - Block 3 盘前信号质量：当日预览存在时 present；缺失 → `no_premarket_preview` 注记。
   - 头标签诚实：`pre_eod`（早于 15:30 跑）/ `no_auction_lake` / `partial` / `full`。
2. **D5 早跑验证（可选）**：手动在 15:31 前生成一次复盘 → 面板标 `pre_eod` + Block 1 注记「盘后竞价同步未完成,建议 15:35 后重跑」——证明 pre-EOD 规则真实生效（是特性不是错误）。
3. LLM 点评（UAT-2）：设置页启用「竞价复盘 AI 点评」→ 下次复盘点评仅引用面板切片数值 + 缺失明说（护栏行运行时附加）；观察 live-model 输出无编造切片外数字。
4. 事件序：SSE 事件 meta → AI → 面板 → done 顺序稳定（前端不出现「卡生成中」）。

**顺序**：D2 通过后（同交易日）；LLM 点评可在次日启用。

---

## D6 — R13：15:30→15:40 缓存语义（v2.2 audit）

**验证什么**：代码已修复（daily_pipeline.py:1135 finally refresh_cache，ce5c705 2026-07-01）；部署确认 15:40 复盘读到的是 EOD 终值缓存而非盘中帧。

**在哪看**：复盘面板 Block 3 的 `avg_change_pct`（EOD 口径）与当日 enriched 分区手动计算对比；日志 `scheduled daily_pipeline completed` 后无异常。

**通过标准**：
1. 15:40 复盘 Block 3 `avg_change_pct` ≈ 用 `data/kline_daily_enriched/date={T}/part.parquet` 手动算的 EOD change_pct 均值（±0.1% 容差，允许复权口径差）。
2. 与 15:30 前生成的复盘对比：早跑版省略 change_pct 统计 + `pre_eod` 标签（D5 第 2 条）——两版并存证明「EOD 前省略 / EOD 后使用终值」语义闭环。
3. 次日开盘：连板梯队/基准列正常（D2 第 2 条同源）。

**顺序**：D2 + D5 同交易日；若偏差超容差 → 报回开发（疑似 quote_service 恢复后覆写缓存，ddde2b9 竞态防护需要复查）。

---

## D7 — 概念 drift 探针 OQ-3（v2.2 CONCEPT-07；manual-only）

**验证什么**：`python scripts/probe_concept_drift.py` 每交易日运行，ext_history 逐日前向归档 + drift.jsonl 累加；一周后出周终报告，校准上游 concepts.json 更新节奏。

**在哪看**：
- 数据目录：`data/ext_history/{gn_ths,hy_ths}/date={T}/part.parquet` + manifest.json（首次真实 capture 创建该目录）；`data/ext_history/_probe/drift.jsonl` 逐日追加。
- 脚本输出：`probe {as_of}: gn_ths sha=… rows=… eff=…; hy_ths …; drift.jsonl lines=N`。

**通过标准（连续 ≥5 个交易日）**：
1. 每个交易日两个 kind 各一行 drift.jsonl；sha256 逐日去重后：无上游更新的日子哈希稳定（可接受重复），上游更新日哈希变化。
2. 周终报告：去重哈希清单 + 逐日概念增删样本 + `effective_date` 与上游发布时间差（校准更新节奏）。
3. **零副作用断言**：`ext_data/` 当前快照（ext_gn_ths/ext_hy_ths）、strategy_cache、screener_results 无任何探针写入（比对目录 mtime/内容）。
4. `--upstream` 模式（可选）：一次独立测量上游，确认离线 capture 与上游抓取差异；抓取失败 → 诚实 skip 不抛（concept_history.py:217-224）。

**顺序**：部署后第一个交易日起每日跑；周终（第 5 个交易日收盘后）出报告。operator 可脚本化 `cron` 或手动。

---

## D8 — 信息项（无 action，仅确认立场）

- **OQ-1 批量回填 stance**（v2.1 audit:27）：回填 job 仍绝无回填——回填走手动 `POST /api/pipeline/backfill` 逐日 `run_all_with_hits`，不写 strategy_cache（byte-identical 断言）。部署不新增任何自动回填。
- **WATCH-04**（v2.1 audit:24）：已交付，无部署项；可选真实后端浏览器 smoke（VIP 星标/只看自选/批量加自选 + guest 零控件），e2e 已覆盖等价行为。
- **BT-07**：见 D3 第 5 条，湖积累后复评，不属本次部署验证。
- **分钟确认点亮（Phase 38 接线落地）**：`make_minute_loader` 已接 app 引擎 + research runner（沙箱接线已测，空湖 fail-closed 不变）；真实点亮观察项 = **同步后** `data/kline_minute/date={T}/part.parquet` 存在（15:30 EOD 管道或手动同步后，**非盘中 09:45**）+ `auction_intraday_confirm` 命中行非空（引擎日志/结果）；分钟湖仍空 → `total=0` 空池为诚实通过态（同 D3「未配置时」通过态），无需 action。

---

## 执行顺序总结（建议 runbook）

| 步 | 时间 | 项 | 前置 |
|----|------|----|------|
| 1 | 部署首日 09:26 | D1（cron + 落盘隔离） | — |
| 2 | 首日 09:26 后 | D4（监控 payload + 投递 + OQ-1 close 语义） | D1 |
| 3 | 首日 15:30-15:40 | D2（EOD cron + 缓存）+ D6（R13 对比） | D1 |
| 4 | 首日 15:40（+次日 LLM） | D5（复盘 + 点评） | D2 |
| 5 | 每交易日 | D7 探针运行 | 部署后 |
| 6 | 第 5 交易日收盘后 | D7 周终报告 | D7 连续 5 日 |
| 7 | 竞价源接入后 | D3（tier-2 真列 + 湖流 + BT-07 复评） | 外部源配置 |
| — | 随时 | D8 立场确认 | — |

**Fail-closed 总则**：任何一项观察到「数据不可用但系统装作有数据」（空湖出非空断言、pre_eod 缺块无注记、探针影响 ext_data、09:26 落盘进 strategy_cache、复盘引用切片外数字）→ 记 BLOCKER 并报回开发，绝不静默放行。

---

### v2.4 实测事实 (2026-08-07)

> 本小节为 v2.4 里程碑实测事实快照 (沙箱/研究实测, 非真实交易日观察), 供部署决策引用; 与 `.planning/research/v2.4-full-universe/` 与 36-02/37-03/38-03 阶段 SUMMARY parity。事实日期 2026-08-07, HEAD `2453366`。来源: AUCTION-FULL-BACKFILL.md / REAL-COLUMN-BACKTEST.md / DEPLOY-MINUTE-LEGACY.md §3.8 / 36-02-SUMMARY / 37-03-SUMMARY / 38-03-SUMMARY (容器 diff 回退 RESEARCH.md §3.8 — RUN-EVIDENCE-39-01.md 落地后以 39-01 实测为准)。

**pilot 延迟 (竞价回填上游)**: mean 0.96s / median 0.82s / p95 1.24s 每请求 (n=20, min 0.38 / max 2.49), 28 请求 0×429 (AUCTION-FULL-BACKFILL.md §3.2 行 59-60)。全量 5537 标的校准 3.5-5.5h (含裕量, 行 81-84); rpm 30/60 吞吐几乎无差 — 瓶颈在 fetch+write 工作量而非限速 (同 §3.4)。

**配额窗口与 campaign 纪律 (实测校准)**: 上游为 ~2h 滚动窗 + 窗口内累计配额 ~70-100 请求, 达额后冷却 ~2h (非永久封禁, tools/list 已复现 200)。纪律: 每 ~2h 窗跑 1 次 burst (≤40 symbols, rpm 30, ~90s); 达额即停等窗复位; 续跑永远 `--symbols <uncovered-chunk>` 或 `--only-missing` (merge-upsert 幂等); 全量 5537 ≈ 数周持续 (诚实估计, 36-02-SUMMARY:127-128)。

**湖覆盖现状**: kline_auction covered=**40/5537** (0.72%), rows=10,904, 248 分区 (36-02-SUMMARY:129)。RC rerun `298d743e8083`: part.parquet **382,398 行** = gated-4 720 + EOD 329,087 + intraday 52,591; coverage 37/5537 = 0.67%, rows_present 8,951/1,373,176 honest partial (回填未完成, 绝不 claim ≥0.94); 只读 API 全规模 detail 0.052s / pushdown 0.015s (37-03-SUMMARY:42-50)。

**容器 diff 证据 (D8 重建依据)**: image `athenaquant-app:latest` created 2026-08-04T10:59:12+04:00 vs HEAD 2026-08-07 (`2453366`); 4 个运行时文件 md5 全 DIFFER (详见 RESEARCH.md §3.8 / DEPLOY-MINUTE-LEGACY.md §3.8; 39-01 RUN-EVIDENCE 落地后以实测为准):

| 文件 | 陈旧 3018 md5 | HEAD md5 |
|---|---|---|
| app/main.py | 641003ae8faab1c67201e9d2754da766 | 32468e1554898be3ed1a09ec7ac42e1b |
| app/strategy/engine.py | 165b95a71850f71356766c0bb7fb974a | 4e33c236ef5b0cb6c6ea6c6c03e6c35a |
| app/jobs/daily_pipeline.py | 72e17c3c2592570a9ec563ab040b631c | 1be3288bd34f8cea212f9446ebeef75f |
| app/services/preferences.py | 23122ca0141152875091bdf83c152e46 | 901d11a9a5af364eac181d7aed5b8e75 |

→ 运行中容器落后 HEAD (Phase 32-34 运行时提交 08-06 晚间晚于镜像), 重建对齐属部署动作; DV-01 预检配方 (build+boot+md5 parity) 在沙箱验证 (RUN-EVIDENCE-39-01.md)。

**分钟接线状态 (BT-10, Phase 38)**: `make_minute_loader` 工厂 + 双构造点接线 (main.py:551/567 + governed_runner.py:55/72), 11 hermetic 测试全绿, 空湖行为逐字节保持 (required→空池 / optional→跳过确认); **点亮 deploy-gated** — kline_minute 湖当前 0 分区, 真点亮 = live 日同步后 (15:30 EOD 或手动) `data/kline_minute/date={T}/part.parquet` 存在 + `auction_intraday_confirm` 非空, **非盘中 09:45** (见上文 D8 bullet, 38-03-SUMMARY §4)。`minute_confirm='not_applied'` 报告语义冻结。
