# 领域研究:部署就绪度 + 分钟接线 (BT-10) + 遗留残留 (Deploy Readiness, Minute Wiring & Legacy Residue)

**Research domain:** v2.4 全量数据解锁 (Full-Universe Data Unlock) — 部署验证 D1..D8 沙箱可执行子集 / BT-10 分钟确认接线可行性 / v2.3 tech_debt 遗留项归类
**Researched:** 2026-08-07
**Researcher:** ResearcherV24C
**Confidence:** HIGH (全部结论基于文件:行核验 + 容器 md5 实测 + 湖目录实测 + git 日志真实日期) / MEDIUM (分钟接线实盘点亮时刻为推理, 依赖真实交易日观察)

---

## 0. Verdict

**部署验证 D1..D8:沙箱子集 = {D3 湖流/PROBE 部分, D6 语义, D7 冒烟} 已锁定;{D1, D2, D4, D5, D8} 为真实交易日/部署动作 → CLOSED in sandbox。BT-10 分钟接线 = SANDBOX-IMPLEMENTABLE NOW(纯代码增量, 空湖 fail-closed 已有测试锁死, 实盘点亮需交易日观察)。遗留残留 = 多数 deploy-gated, 唯一 sandbox-actionable 代码项即 BT-10 接线。文档 parity = OK(两份文件正文逐字节一致, 仅 docs/ 多批准横幅)。**

逐项 verdict(详见 §4 矩阵):

| 项 | 沙箱 verdict | 生产 verdict | 证据锚点 |
|---|---|---|---|
| D1 09:26 盘前 cron | **CLOSED**(需真实交易日 + 09:15-09:25 实时数据; `data/premarket_results` 缺失 = 双门禁) | 首交易日 09:26 | test_premarket_pool.py; daily_pipeline.py:966-972,1168-1172 |
| D2 15:30 EOD cron + 缓存 + 15:35 持久化 | **CLOSED**(调度路径实盘观察; 机械路径已证: Phase 33 实测 8 日/13s) | 首交易日 15:30-15:40 | preferences.py:331; daily_pipeline.py:1115-1136,1138-1142 |
| D3 tier-2 真列 + 湖流 | **PARTIAL**(湖流/probe 沙箱已证: 248 分区、probe 30s TTL、回填实测; 真列被上游缺列 gate 卡死) | 竞价源提供两输入列后 | data.py:56-58,627-634; CHART-04 stance |
| D4 09:26 监控 payload/close 语义 | **CLOSED**(真实交易日; 代码侧 preopen fail-closed 双保险已锁) | D1 通过后同日 | test_premarket_pool.py probe 三态 |
| D5 15:40 复盘 + LLM | **CLOSED**(真实交易日 + AI key; 面板 EOD/pre-EOD 语义已锁) | D2 通过后同日(+次日 LLM) | preferences.py:436-441; daily_pipeline.py:779-781; test_auction_recap.py |
| D6 R13 实盘观察 | **PARTIAL**(finally-refresh 语义被 test_daily_pipeline_refresh.py 锁死, 成功+异常双路径) | ±0.1% 对比需交易日 | test_daily_pipeline_refresh.py; daily_pipeline.py:1135 |
| D7 OQ-3 周终报告 | **PARTIAL**(探针冒烟已过, 零副作用; 周报需 ≥5 交易日) | 第 5 交易日收盘后 | 沙箱无 data/ext_history |
| D8 生产 e2e vs 陈旧容器 | **CLOSED**(3018 容器运行中且代码陈旧, 不可触碰; 对齐 = 部署动作) | 部署时 rebuild | 容器 md5 vs HEAD 实测(§3.8) |

---

## 1. 目标

回答三个问题并产出部署分相建议:

1. **部署就绪度**:docs/deploy-verification.md(Phase 35 成册)D1..D8 各项, 沙箱今日可执行子集是什么, 各自 CLOSED/PARTIAL 的依据。
2. **BT-10 分钟接线**:engine.py:376-390 分钟确认 seam 存在但 `_minute_loader` 未接线(main.py:561-565);kline_minute 湖 0 分区。接线现在是否可实现(诚实空湖 + fixture 测试), 还是必须等真实交易日才有数据可产。
3. **遗留残留**:v2.3-MILESTONE-AUDIT.md tech_debt 清单逐项归类(部署动作 vs 沙箱可动);DEPLOY-CHECKLIST.md 与 docs/deploy-verification.md parity 核查。

---

## 2. 背景

- Phase 35 将部署验证 8 项成册为 docs/deploy-verification.md(D1..D8), 纪律 = 「真实交易日观察」, 诚实铁律(空湖 → `{data_gate:"empty"}` 200, 绝不伪造/静默回填)。
- v2.3 audit(v2.3-MILESTONE-AUDIT.md, 2026-08-06 passed)tech_debt 列出: 竞价全宇宙回填(5537, 3-5.5h)、分钟历史 CLOSED(BT-10)、screener_results 8/248、premarket_results 缺失、真列分支 0.04%、auction_intraday_confirm 恒空(分钟未接线)、D1..D8 待执行、3018 陈旧 root 容器。
- BT-10 背景: xyz 1m 仅 ~21 日 / ifzq/sina 尾随 / TickFlow pro+ 门 → 分钟历史回填 CLOSED, kline_minute 维持 ≤30 日增量; 引擎 minute_confirm seam 自 v2.1 (STRAT-06/09) 存在但生产构造未注入 loader, 恒 fail-closed。

---

## 3. 证据

### 3.1 D1 — 09:26 盘前预览: 代码侧已锁, 沙箱无数据路径

- 硬边界常量: `_PREMARKET_JOB_ID = "premarket_pool_preview"`, `_PREMARKET_HOUR, _PREMARKET_MINUTE = 9, 26`(daily_pipeline.py:969-970), mon-fri Asia/Shanghai cron 注册(daily_pipeline.py:1168-1172), 不可偏好化(注释「09:25 是硬边界」:968)。
- 诚实 skip: 无 app state / 无 enriched 基准日 → 不写任何文件(daily_pipeline.py:1032-1033, 镜像 pool_eod_persist skip 语义)。
- 沙箱隔离断言: `data/premarket_results` **不存在**(ls 实测)→ 部署 doc 所述「部署 + 实时 09:15-09:25 数据双门禁」在沙箱成立。
- Hermetic 锁: test_premarket_pool.py(690 行)锁 PM-01/02/03 — 注册形 grep 门禁(断 `_PREMARKET_JOB_ID` 常量, 不断字面)、存储隔离(仅落 premarket_results/date={T}/part.json, strategy_cache/screener_results 不被改动)、诚实 skip、probe 三态(not_configured/fail_closed → `degraded:true`)、open_gap 补算单一公式、只读 API + guest 掩码。

### 3.2 D2 — EOD 管道: 机械路径已实测, 调度实盘观察 deploy-gated

- 默认调度 15:30: `pipeline_schedule` 默认 `{"hour": 15, "minute": 30}`(preferences.py:331); cron 注册 daily_pipeline.py:1138-1142。
- R13 语义已锁: `_pipeline_then_refresh` finally 必刷 `repo.refresh_cache()`(daily_pipeline.py:1131-1135, ce5c705/9aa96ed), test_daily_pipeline_refresh.py 用 fake scheduler 从闭包提取函数体锁成功+异常双路径。
- 管道机械执行已在沙箱证过: Phase 33 真实子集回填 8 日 = 13s(1.6s/日, ~650MiB 全量锚点), 走手动 `POST /api/pipeline/backfill` 逐日 `run_all_with_hits`, strategy_cache md5 字节一致。
- EOD 股池持久化: `pool_eod_persist` job(管道+5min, daily_pipeline.py:1154-1162 per deploy doc)。
- 竞价 stage 双闸门: `_run_auction_sync` = `auction_sync_enabled`(默认 False, preferences.py:129-131)+ probe available 双闸门, 未开 → 0 写计入 skipped(daily_pipeline.py:696-708)。**全宇宙回填(Phase 32 CLI/API)明确不 consult 该偏好**(auction_backfill.py:10-12), 与 EOD 定时路径互不干扰。

### 3.3 D3 — 湖流沙箱已点亮, tier-2 真列被外部 gate 卡死

- Probe: `_AUCTION_PROBE_TTL = 30.0`(data.py:58), `auction_probe()` 30s TTL 缓存(data.py:627-634); Phase 32/33 实测 probe available(source xyz)。
- 湖: `data/kline_auction` = **248 个 date= 分区, 2.0M, 2 symbols × 248 日**(ls + du 实测); 写路径单一化 `write_auction_partitions`(auction_sync.py:57, 窗口谓词/存在性裁剪/merge-upsert/原子 rename)。
- tier-2 真列: 上游 xyz **无 `auction_unmatched_volume`/`auction_virtual_price` 字段**(v2.3 audit: 「上游无字段 — 派生列维持估算诚实态 (CHART-04 stance)」)→ D3 的「真列」分支外部 gate 未满足, 沙箱无法点亮; 湖流分支已证。
- BT-07 复评 gate(≥20 交易日湖历史): 回填后 248 日(全宇宙, R1 交付)即满足 → 复评可沙箱执行(Phase 34 Run B rerun), 不依赖实盘。

### 3.4 D4 — 09:26 监控 payload: 双 fail-closed 已锁, 实盘核验 deploy-gated

- 白名单 5 字段 + 缺列 mask → head(0) 零命中(monitor.py:283 per deploy doc); `change_pct`/`price` 恒 None(preopen_eval 帧 fail-closed)。
- 事件 `provisional:true` + `degraded=<payload.degraded>` + probe 透传(monitor.py:590-598 per deploy doc)。
- 沙箱侧: test_premarket_pool.py probe 三态覆盖 degraded 判定; OQ-1 close 语义核验(open_gap vs EOD change_pct)是首个真实交易日 payload 观察 → deploy-gated。

### 3.5 D5 — 15:40 复盘: 默认关 + 需 AI key, 实盘 deploy-gated

- `review_schedule` 默认 `{"enabled": False, "hour": 15, "minute": 40}`(preferences.py:441); 注册 mon-fri(daily_pipeline.py:946-950); AI key 未配置 → skip(daily_pipeline.py:779-781)。
- 面板语义(EOD/pre-EOD 标签、Block 1-3 data_completeness)由 test_auction_recap.py 锁死(test_daily_pipeline_refresh.py:7 声明「recap 消费侧语义已由 test_auction_recap.py 锁死」)。
- 沙箱无 AI key / 无交易日 → live 观察 CLOSED。

### 3.6 D6 — R13: 语义 hermetic 锁定, 数值对比 deploy-gated

- test_daily_pipeline_refresh.py 锁: `_pipeline_then_refresh` 成功路径刷新(`spy refresh_cache` 被调 ≥1 + 刷新后 latest-day enriched 持有 EOD close)+ 异常路径(finally 必刷)。零网络、零调度器、真 parquet tmp_path。
- 实盘 ±0.1% 对比(15:40 复盘 avg_change_pct vs enriched 手动计算)→ 首交易日。

### 3.7 D7 — OQ-3 探针: 冒烟已过零副作用, 周报需 5 交易日

- 沙箱 `data/ext_history` **不存在**(ls 实测)→ Phase 35 冒烟为 fixture 隔离(「探针隔离冒烟 (追加式, 零副作用)」), 未触碰真实 data/。
- 周终报告(≥5 交易日 sha256 去重 + effective_date 校准)→ 部署后连续交易日。

### 3.8 D8 — 3018 陈旧容器: 实测确认 stale 且不可触碰

- 容器: `athenaquant` (cb9800570dde), image `athenaquant-app:latest` **built 2026-08-04T10:59:12+04:00**, running, `0.0.0.0:3018->3018`; `Config.User` 空 = 容器内 root。
- 挂载: bind `/home/orca/source/AthenaQuant/data → /app/data` + `tiers.yaml → /app/tiers.yaml` → **与沙箱共享同一 data/ 湖**(audit 所述「共享 data/ 湖」证实)。
- Stale 实证(docker exec md5sum 只读比对): `app/main.py`、`app/strategy/engine.py`、`app/jobs/daily_pipeline.py`、`app/services/preferences.py` **四个关键运行时文件 md5 全部 DIFFER**(容器 641003ae/165b95a7/72e17c3c/23122ca0 vs HEAD bf3ba575/4e33c236/1be3288b/901d11a9)。
- 缺口内容: git log 真实日期显示 Phase 32-34 运行时提交(1ec11a5..e80e8b0)全部落在 **2026-08-06 20:51-22:34 +0400**, 晚于镜像 build → 容器**缺竞价回填端点、回测只读端点、验证激活、写缝抽取**等。HEAD = c1c9912 (2026-08-07)。
- 沙箱不可触碰: 运行中的 3018 服务 + 共享湖, 重建/对齐 = 部署动作。**可选沙箱预检**: Dockerfile + docker-compose.yml 在仓库根, image 本地存在(2.59GB) → 沙箱可 `docker build` HEAD + 独立端口/临时 data 目录起新容器做 boot smoke, 验证部署重建配方(但不能替代 D1/D2/D4/D5/D7 真实日观察)。

### 3.9 BT-10 分钟接线: seam 完整、loader 未接线、湖 0 分区、测试已具备

- Seam: `StrategyEngine.__init__(..., minute_loader: Callable[[list[str], date], pl.DataFrame] | None = None)`(engine.py:154), `self._minute_loader = minute_loader`(:163)。运行分支 engine.py:373-392: `minute_confirm_fn` + `evaluation_time` 存在 → `_minute_loader is None` → required 则空 StrategyResult(fail-closed), 可选则跳过确认保留日线核心池; loader 注入后: 空帧 → required 空池/可选跳过; 非空 → 单点截断 `datetime.time() <= evaluation_time` → `minute_confirm_fn(truncated)` → 保留确认 symbol(T-21-01「确认时刻之后无输入」硬验收)。
- 未接线构造点(**2 处 live**): main.py:562-565(enriched_loader + enriched_history_loader + strategy_dirs, 无 minute_loader); advanced/governed_runner.py:63-66(同形, 无 minute_loader)。scripts/auction_backtest.py:199-202 **刻意**不传(BT-10 诚实注记, 逐行 `minute_confirm="not_applied"`)。
- 策略侧: `auction_intraday_confirm` `minute_confirm_required: True`(builtin/auction_intraday_confirm.py:16); `golden_230` `minute_confirm_required: False`(:20, 可选增强)。
- 湖: `data/kline_minute` 目录存在(2026-07-16 创建)但 **0 分区**(ls 实测); `CANONICAL_MINUTE_COLS = [symbol, datetime, open, high, low, close, volume, amount]`(kline_sync.py:535-537)。
- 写路径与触发时机: `sync_and_persist_minute`(kline_sync.py:829, date= 分区 + merge-upsert + DuckDB view); **唯一自动触发 = EOD 管道 sync_minute stage**(`minute_sync_enabled` 默认 False + capability 双条件, daily_pipeline.py:564-583, 区间 [today-minute_days, today], `minute_sync_days` 默认 5 钳 1..30, preferences.py:98-99)+ 手动 `POST /api/kline/sync_minute`(kline.py:575-577)。kline 图表 API 的盘中补拉 `sync_minute_batch` **不落库**(kline.py:380-384)。
- Hermetic 测试已就绪(可直接复用/镜像): test_auction_strategy_family.py(loader 注入 :31-39、分钟分区 fixture :59-62、截断断言 :146-162、`test_missing_minute_required_fail_closed` :199-225); test_auction_strategy_family_p2.py(`test_intraday_truncation` :222-249、`test_time_factor` :252-267、`test_intraday_minute_absent_empty` :269-273); test_minute_sync_verify.py(DATA-01 写路径 + 日K湖 byte-identical :104-149, 闸门 skip :152-187)。

### 3.10 磁盘与文件系统

- `/` = ext4 /dev/vda2, 2.0T, 949G used, **1007G avail (48%)** — 无 btrfs/overlayfs 顾虑(直连 ext4)。
- `data/` 总计 134M; kline_auction 2.0M(248 分区/2 symbols); 全宇宙外推(5537 symbols × 248 日 ≈ 1.37M 行)naive 线性 ≈ 5.5G —— 精确估计归 R1 研究, 但无论 5.5G 还是更高, 相对 1TB avail 无风险。

### 3.11 文档 parity

- `diff docs/deploy-verification.md .planning/research/v2.3-data-depth/DEPLOY-CHECKLIST.md`(2026-08-07 实测): **唯一差异 = 4 行批准横幅块**(Orchestrator 批准 2026-08-06 / Owner 部署运维 / D3 条件项注记 / source 引用注), 仅存在于 docs/ 版; 其余正文逐字节一致。两份均带「更新时两处同步」纪律 → 单源(研究版)+ 批准镜像(docs 版), parity OK。

---

## 4. 结论

### 4.1 沙箱 vs 生产矩阵(部署项)

| 项 | 沙箱可执行子集 | 沙箱 CLOSED 部分 | 生产(真实交易日) |
|---|---|---|---|
| D1 | —(代码侧 test_premarket_pool.py 已锁注册/隔离/skip/degraded) | cron 触发 + 落盘隔离观察(premarket_results 双门禁) | 首日 09:26 |
| D2 | 管道机械(Phase 33 已证 8日/13s); R13 语义(test_daily_pipeline_refresh.py) | 调度 cron + 缓存刷新 + 15:35 持久化 + 次日连板梯队 | 首日 15:30-15:40 |
| D3 | 湖流 248 分区 + probe 30s TTL + 回填实测 | tier-2 真列(上游缺两输入列, CHART-04) | 竞价源提供输入列后 |
| D4 | probe 三态/白名单 fail-closed(测试) | 09:26 真实评估 + 投递 + OQ-1 close 语义核验 | D1 通过后同日 |
| D5 | 面板 EOD/pre-EOD 语义(测试) | 15:40 定时触发 + LLM 点评实盘 | D2 通过后同日(+次日 LLM) |
| D6 | finally-refresh 语义(test_daily_pipeline_refresh.py 双路径) | ±0.1% 数值对比 | D2 同日 |
| D7 | 探针隔离冒烟(已过, 零副作用) | 周终报告(≥5 交易日) | 第 5 交易日收盘后 |
| D8 | [可选] docker build HEAD + 新容器 boot smoke | 3018 陈旧容器对齐(运行中 + 共享湖, 不可触碰) | 部署时 rebuild |

### 4.2 BT-10 接线结论

**SANDBOX-IMPLEMENTABLE NOW(推荐: 接线 + hermetic 测试 + 诚实空湖, 实盘点亮 deploy-gated 观察)。** 依据:

1. Seam 完整且已有空态语义(engine.py:373-392): 不接线 = `_minute_loader None`; 接线 + 0 分区 = 空帧 → 语义**与今天逐字节相同**(required → 空池, 可选 → 跳过确认)。即接线在沙箱是**行为保持**的纯增量, 非行为变更。
2. 测试配方已存在(fixture 分钟分区 + loader 注入 + 截断/空态断言), 生产 loader 工厂可 1:1 镜像。
3. 真实数据点亮**不需要**「接线本身等交易日」—— 接线是代码; 但**湖数据只由交易日写入**(EOD sync_minute 或手动 sync), 所以「看到确认生效」是 deploy-gated 观察。
4. **盘中时机诚实注记**: 湖只读 loader 下, as_of=T 的分钟帧在 T 日 15:30 同步(或手动 sync)前不存在 → 09:45 盘中评估 auction_intraday_confirm 仍为空池(fail-closed, 不产生错误输出); 同步后(盘后评估)才有数据。这是数据新鲜度事实, 不是缺陷 —— 写入文档供实盘观察比对。

### 4.3 遗留残留归类(v2.3-MILESTONE-AUDIT.md tech_debt)

**deploy-gated(部署/外部动作):**
- kline_auction 全宇宙回填(5537, 3-5.5h, rpm30/429 退避)→ R1 研究域, operator 动作; 完成后 Phase 34 Run B 重跑 + 真列分支/竞价活跃度/竞价图全量解锁。
- screener_results 全量 248 回填(~6-7min, ~650MiB)→ operator 动作。
- premarket_results 缺失 → 真实交易日 + 09:15-09:25 实时数据双门禁。
- 真列分支 0.04% → 回填后重跑(沙箱可执行, 依赖 R1 交付)。
- D1..D8 部署验证 → 真实交易日 runbook。
- 3018 陈旧容器对齐 → 部署时 rebuild(§3.8 实证 stale)。
- auction_unmatched_volume 上游字段 → 外部源 gate(CHART-04 stance 已文档化, 无需代码动作)。

**sandbox-actionable(本阶段可做):**
- **BT-10 分钟确认接线**(唯一代码项, §5.1 增量清单)。
- 文档 parity 维护(两处同步纪律, 当前 OK)。
- [可选] D8 预检: docker build HEAD + 独立端口/临时 data 新容器 boot smoke(验证重建配方)。
- [可选, 依赖 R1] BT-07 复评(湖 ≥20 日已由回填满足)。

---

## 5. 建议

### 5.1 最小代码增量 — BT-10 接线(一个沙箱 phase)

1. **loader 工厂**: 新增 `make_minute_loader(data_dir) -> Callable[[list[str], date], pl.DataFrame]`, 读 `data/kline_minute/date={as_of}/part.parquet`, filter `symbol.is_in(candidates)`, sort `[symbol, datetime]`(镜像 test_auction_strategy_family.py:153-156 fixture 配方); 分区不存在 → 返回空帧(诚实)。
2. **接线 2 处 live 构造点**: main.py:562-565 与 advanced/governed_runner.py:63-66 传入 `minute_loader=make_minute_loader(store.data_dir)`。
3. **Hermetic 测试**(新): 用生产工厂 + tmp_path fixture 分区 → 断言 (a) 0 分区 → 空帧 → `auction_intraday_confirm` 空池 / `golden_230` 保留日线池(行为保持); (b) fixture 分区存在 → `auction_intraday_confirm` 出池且截断 ≤09:45(点亮路径); (c) 湖无写(loader 只读)。
4. **诚实注记不动**: scripts/auction_backtest.py / auction_validation.py 报告层**继续** `minute_confirm="not_applied"`(历史日无分钟湖, 不假装生效)—— 接线 live 引擎不得静默改变报告语义。
5. 文档: 在两份部署清单同步「BT-10 接线状态」一行(parity 纪律)。

### 5.2 分相建议

- **沙箱 phase「BT-10 分钟确认接线 + 部署预检」**: §5.1 全量 + 可选 D8 boot smoke + parity 维护。验收 = 新测试绿 + 全量测试不回归 + 空湖行为保持(与未接线等价)。
- **交易日月 phase「D1..D7 真实交易日验证」**(operator runbook, 按 deploy doc 顺序): D1 → D4 → D2/D6 → D5 → D7(第 5 日周报); D3 条件触发; 前置 = D8 容器对齐(rebuild HEAD)。
- **回填后沙箱动作**: Phase 34 Run B 重跑 + BT-07 复评(依赖 R1 交付, 不依赖交易日)。

---

## 6. 风险

| 风险 | 等级 | 说明与缓解 |
|---|---|---|
| 陈旧容器共享湖(写并发) | LOW | 3018 容器 bind 同一 data/(§3.8)。沙箱回填只写历史日期分区, 容器 EOD 只写当日 → 分区不重叠; 原子 rename 保证单分区无半写。缓解: 回填期间不重建容器; 部署时先对齐容器再开 EOD 竞价闸门。 |
| 分钟接线实盘不亮(盘中评估空池) | LOW | 湖只读 loader 在当日同步前无数据 → 盘中 09:45 确认仍空(fail-closed 正确, 无错误输出)。缓解: 文档明示「同步后点亮」, 实盘观察以盘后/同步后评估为准; 若需盘中确认是独立数据新鲜度需求(超出 BT-10 范围, 记录不扩)。 |
| 上游稳定性(数小时回填 429) | MEDIUM | R1 域; probe 端点是 30s TTL(data.py:58), 但回填 CLI 循环每次调用实时 HTTP, 无短 TTL 缓存(R3 defer)。缓解: 现有限速/退避已实现(Phase 32), 运行时长预算含 margin。 |
| 文档 parity 漂移 | LOW | 两份文件同步纪律; 建议沙箱 phase 顺带加一行状态同步, 保持 diff 只有批准横幅。 |
| D6 ±0.1% 超差 | LOW | 若 15:40 avg_change_pct 与 enriched 手动计算偏差超容差 → 疑似 quote_service 恢复后覆写缓存(ddde2b9 竞态防护需复查), 报回开发(fail-closed 纪律)。 |
| 磁盘 | NONE | 1TB avail; 全量外推 ≤ ~6G。 |

---

## 7. 附录

### 7.1 关键文件:行索引

| 事实 | 位置 |
|---|---|
| 09:26 硬边界 + cron | daily_pipeline.py:969-970, 1168-1172 |
| 盘前预览诚实 skip | daily_pipeline.py:1032-1033 |
| pipeline 默认 15:30 / review 默认 15:40 关 | preferences.py:331, 441 |
| _pipeline_then_refresh finally 刷新 | daily_pipeline.py:1115-1136(:1135) |
| 竞价 EOD 双闸门 | daily_pipeline.py:696-708; preferences.py:129-131 |
| 回填不 consult 偏好 | auction_backfill.py:10-12 |
| probe 30s TTL | data.py:56-58, 627-634 |
| 分钟确认 seam | engine.py:154, 163, 373-392 |
| 未接线构造点 | main.py:562-565; governed_runner.py:63-66; 刻意: scripts/auction_backtest.py:199-202 |
| 分钟策略 required/可选 | builtin/auction_intraday_confirm.py:16; builtin/golden_230.py:20 |
| 分钟写路径/触发 | kline_sync.py:829(写), 535-537(列); daily_pipeline.py:564-583(EOD stage); kline.py:575(手动); kline.py:380-384(盘中补拉不落库) |
| R13 回归 | test_daily_pipeline_refresh.py(成功+异常双路径) |
| 分钟 seam 测试 | test_auction_strategy_family.py:31-39,59-62,146-162,199-225; test_auction_strategy_family_p2.py:222-273 |
| D1/D4 代码侧锁 | test_premarket_pool.py(PM-01/02/03) |
| 容器实证 | docker inspect cb9800570dde; docker image inspect athenaquant-app:latest(2026-08-04T10:59:12+04:00); docker exec md5sum × 4 文件全 DIFFER |

### 7.2 实测数字

- data/ = 134M; kline_auction = 2.0M / 248 分区 / 2 symbols; kline_minute = 0 分区(空目录, 2026-07-16); premarket_results = 不存在; ext_history = 不存在。
- 磁盘: / ext4 2.0T, 949G used, 1007G avail(48%)。
- 容器: athenaquant(cb9800570dde) image built 08-04T10:59+04:00; repo HEAD c1c9912 08-07; Phase 32-34 运行时提交 08-06 20:51-22:34 +0400(晚于镜像) → 4 个运行时文件 md5 全 DIFFER。
- Phase 33 锚点: 8 日回填 13s(1.6s/日)。

### 7.3 方法学注记

- 未读 `frontend/src/pages/Watchlist.tsx`(assignment 禁令); 前端相关结论(Watch 页/D5 面板 UI)仅引用既有测试/文档证据。
- 容器比对用只读 `docker exec md5sum`(无写操作); 未触碰运行中容器。
- 沙箱未运行任何真实交易日依赖的调度项; 所有 live 触发点均标注 deploy-gated。
