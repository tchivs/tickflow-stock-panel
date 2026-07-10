# Context Intel

## AthenaQuant target architecture

source: /root/source/AthenaQuant/docs/ARCHITECTURE.md
classification: DOC (confidence: medium)
scope: AthenaQuant; quantitative research platform; data lake; factor research; decision engine; AI analysis; agent orchestration; market monitoring; adoption roadmap

DATA_Q7M2X9LK_START
# AthenaQuant — 完全体架构文档

## 定位

AthenaQuant 是面向个人 A 股投资者的全栈量化研究平台，融合多个开源项目的核心能力，覆盖从数据底座、因子研究、策略进化、交易计划、AI 分析到持仓盯盘的全链路。

---

## 源项目索引

| 项目 | 源码路径 | 文档路径 | GitHub | 引入能力 |
|---|---|---|---|---|
| **tickflow-stock-panel** | `/root/source/AthenaQuant/tickflow-stock-panel/` | `/root/source/docs/aaa/tickflow-stock-panel/` | `tchivs/tickflow-stock-panel` | 核心数据湖 + 策略 + 回测 + UI |
| **PanWatch** | `/root/source/tmp/PanWatch/` | `/root/source/docs/aaa/panwatch/` | `tchivs/PanWatch` | 持仓 + AI 深度分析 + 通知 + 盯盘 |
| **HermesAlpha** | `/root/source/HermesAlpha/` | — | `tchivs/HermesAlpha` | 确定性决策引擎 + LLM 护栏 + 复盘 |
| **alphaagent** | `/root/source/tmp/AlphaAgent/alphaagent/` | `/root/source/docs/aaa/alphaagent/` | — | A 股因子 DSL + FactorZoo + IC/RankIC |
| **qlib** | `/root/source/tmp/qlib/` | `/root/source/docs/aaa/qlib/` | `microsoft/qlib` | 实验记录 + 模型 Zoo + 滚动训练 |
| **alpha-evolution-lab** | — (docs only) | `/root/source/docs/aaa/alpha-evolution-lab/` | — | 策略自进化 + 变异/交叉 + 晋升门控 |
| **rd-agent** | — (docs only) | `/root/source/docs/aaa/rd-agent/` | `microsoft/RD-Agent` | 自动化研发循环 + 假设沙箱 |
| **quantdinger** | — (docs only) | `/root/source/docs/aaa/quantdinger/` | — | Agent Gateway + 策略沙箱 + AST 校验 |
| **vibe-trading** | `/root/source/Vibe-Trading/` | `/root/source/docs/aaa/vibe-trading/` | `HKUDS/Vibe-Trading` | Shadow Account + 452 Alpha + 9 回测引擎 |
| **uzi-skill** | — (docs only) | `/root/source/docs/aaa/uzi-skill/` | — | 66 评委多流派评分 + DCF/LBO |
| **x2t** | `/root/source/tmp/x2t/` | `/root/source/docs/aaa/x2t/` | — | 博主立场跟踪 + Flip Radar + Wilson/FDR |
| **deepear** | `/root/source/tmp/DeepEar/skills/deepear/` | `/root/source/docs/aaa/deepear/` | — | 信号生命周期跟踪 |
| **ai-berkshire** | `/root/source/tmp/ai-berkshire/` | `/root/source/docs/aaa/ai-berkshire/` | `xbtlin/ai-berkshire` | 价值投资框架 + 信息质量分级 |
| **daily-stock-data** | `/root/source/tmp/daily_stock_data/` | `/root/source/docs/aaa/daily-stock-data/` | `bzcsk2/daily_stock_data` | 数据契约 + CI Schema 治理 |
| **tradingagents-family** | — (docs only) | `/root/source/docs/aaa/tradingagents-family/` | — | LangGraph 多 Agent 辩论框架 |
| **financial-timeseries-foundation** | — (docs only) | `/root/source/docs/aaa/financial-timeseries-foundation/` | — | Kronos 时序基础模型 |
| **tdx-market-data-clients** | `/root/source/tmp/eltdx/` (作为 eltdx) | `/root/source/docs/aaa/tdx-market-data-clients/` | `electkismet/eltdx` | 通达信行情协议备用 |
| **daily-stock-analysis** | `/root/source/tmp/daily_stock_analysis/` | `/root/source/docs/aaa/daily-stock-analysis/` | `ZhuLinsen/daily_stock_analysis` | 多数据源联邦 + YAML 策略 |
| **a-stock-data** | `/root/source/tmp/a-stock-data/` | `/root/source/docs/aaa/a-stock-data/` | `simonlin1212/a-stock-data` | 数据源优先级 + 限流治理 |

---

## 架构总览

前端交互层由 tickflow React 工作台承担看盘、策略、回测、复盘和数据管理；PanWatch PWA 用于移动端盯盘和通知。可选扩展包括 OpenAshare 轻量研究/Agent 对话和 JCP 多 Agent 会议室。

Agent 编排层由 quantdinger Agent Gateway（作用域 Token、四级权限、幂等 Job、审计、SSE 进度）和 tradingagents-family LangGraph（多分析师辩论、PM 决策聚合、Checkpoint）组成。

因子/策略研究层集成 alphaagent DSL、FactorZoo、IC/RankIC、LLM 因子挖掘，qlib 实验记录/模型 Zoo/滚动训练，alpha-evolution 策略进化，rd-agent 假设与实验循环，以及 vibe-trading Shadow Account、452 Alpha 和 9 回测引擎。

决策执行层使用 Hermes 的 PIT 因子、评分、质量筛选、池分层、交易计划、受限 LLM 护栏、纪律评分、LLM 审计和零 LLM 隔离的 PIT Replay；tickflow 提供内置/自定义/AI 策略；quantdinger 提供策略沙箱、Python 合约 AST 校验与沙箱执行。

AI 分析层使用 PanWatch TradingAgents、建议池/信号评分，ai-berkshire 信息质量分级/数值交叉校验/投资论点追踪，uzi-skill 66 评委评分与 DCF/LBO/IC Memo，deepear 信号生命周期，以及 x2t 博主观点跟踪、Flip Radar、Wilson 置信区间与 FDR 校正。

数据底座以 tickflow Parquet 数据湖、DuckDB 视图和 Polars 计算为主，daily-stock-data 负责表契约与 Schema drift CI。PanWatch SQLite 存储账户、持仓、规则、通知、建议、信号、模拟盘和聊天状态。tdx-market-data 提供备用行情源。Hermes PostgreSQL 将逐步迁移至 tickflow Parquet 与 SQLite。Kronos 时序模型提供预测服务。

---

## 核心数据流

### 盘前 (Pre-market)

每日 pipeline 由 AP Scheduler 触发：tickflow 同步股票列表、日K与复权因子、预计算技术指标、财务数据和指数/ETF；Hermes EOD pipeline 计算市场状态、PIT 因子、质量筛选、六因子综合评分、执行/观察/风险池和 playbook；PanWatch 生成 AI 日报、盘前展望并刷新策略信号。

### 盘中 (Intraday)

tickflow QuoteService 轮询行情，写入今日 Parquet，计算今日 Enriched，并通过 SSE 广播 quotes_updated、depth_updated 与 strategy_alert。PanWatch PriceAlertEngine 每 60 秒匹配规则、持久化 PriceAlertHit、通知 Telegram/钉钉/飞书等，并可触发 TradingAgents 深度分析；持仓监控自动感知异动和提醒盈亏；MonitorRuleEngine 持久化策略/价格/市场/连板规则告警并经 SSE 推送。

### 盘后 (Post-market)

tickflow 生成 AI market recap，涵盖大盘、情绪、概念/行业/连板复盘并可推送飞书。Hermes review 仅允许 LLM 受限调整 entry_low、entry_high、stop、target、position_pct，方向受限、越界 clamp、违规 veto，并保留引擎基线和审计日志。PanWatch 清理建议池、评估信号结果并完成模拟盘日终结算。x2t 可更新财经博主观点、检测立场 flip 并结算战绩。

---

## 集成模块说明

### 1. 因子/策略研究层 (Phase 2)

Factor DSL 是具备解析器和操作符白名单的受限制因子表达式语言；FactorZoo 提供因子存储、检索和相似度去重；IC/RankIC 提供分组收益与多空收益评价；LLM 因子挖掘将自然语言描述转换为 DSL 因子并回测验证。qlib 提供 MLflow 式 run 管理与模型注册/版本管理。alpha-evolution-lab 负责 ResearchAsset 到 Champion 的变异、评估和晋升门控。rd-agent 负责从假设到实验规格、沙箱、运行与反馈的循环。

### 2. 决策执行层

HermesAlpha 提供确定性引擎、受限字段调整/方向约束/clamp/veto/基线保留、零 LLM 隔离的 PIT Replay、实盘与计划对比的纪律评分和完整 LLM 调用留痕。quantdinger 提供 Python AST 校验、导入白名单、超时/内存守卫和机器可读策略合约。vibe-trading 提供实盘日志到策略蒸馏、回测和信号扫描的 Shadow Account。

### 3. AI 分析层

PanWatch 的 TradingAgents 进行多分析师辩论并产生 PM 决策与五级评级；建议池/信号组件做归一化管理、过期、防抖动与评分。uzi-skill 提供多流派评分矩阵以及 DCF/LBO/IC Memo。ai-berkshire 按 A/B/C 分级数据质量，执行跨源数值比对并追踪买入逻辑、估值锚和失效条件。deepear 跟踪 strengthened、weakened、falsified、priced_in 信号生命周期。x2t 跟踪立场并使用 Wilson 置信区间和 FDR 校正。

### 4. Agent 编排层

quantdinger 提供机器 API、作用域 Token、市场/标的白名单、限流、idempotency key、审计摘要、SSE 进度，以及 read、backtest、notify、trade 四级硬隔离。tradingagents-family 提供分析师/多空/风控角色的 LangGraph 辩论与长任务 Checkpoint 续跑。

### 5. 数据底座层

tickflow 存储日K、分钟K、复权、财务和扩展数据至 Parquet，使用 DuckDB 视图和 Polars 计算技术指标、信号和评分，并通过实时行情 SSE 推送。PanWatch SQLite 保存持仓、规则、建议、信号、模拟盘和聊天状态。daily-stock-data 定义表主键、时间语义、修复窗口并检测 schema drift、脚本语法和 secret 泄露。tdx-market-data 提供备用通达信协议。financial-timeseries-foundation 的 Kronos 提供分位数、样本路径和 checkpoint 的时序预测 API。

---

## 渐进式接入路线

### Phase 1 — 核心合并 (预计 2 周)

目标是打通数据底座和持仓盯盘闭环：以 tickflow-stock-panel 为基础，接入 PanWatch 的持仓/通知/盯盘，以及 Hermes 的 engines、llm 与 replay 决策内核。目录包含 upstream 同步的 tickflow-stock-panel 和 PanWatch forks、从 HermesAlpha 抽取的 hermes-core、tickflow Parquet 数据湖和本架构文档。

### Phase 2 — 因子/策略强化 (预计 1 周)

接入 alphaagent DSL、FactorZoo 与 qlib 实验记录，并扩展 tickflow 的因子注册、回测和实验管理。

### Phase 3 — AI 分析增强 (预计 1 周)

接入 uzi-skill 66 评委报告、deepear 信号生命周期和 ai-berkshire 质量分级与数值校验。

### Phase 4 — 进阶能力 (预计 1 周)

接入 x2t 观点追踪、rd-agent 研发循环、alpha-evolution 策略进化与 quantdinger 策略沙箱。

### Phase 5 — 锦上添花 (可选)

接入 vibe-trading Shadow Account、ai-berkshire 投资论点追踪与 Kronos 时序预测。

---

## 设计原则

1. **可弃可留** — 每个模块都是独立子包，不强制全上。个人用户可以从 Phase 1 跑起来，按需激活后续能力
2. **上游同步** — tickflow 和 PanWatch 保持 fork 关系，定期 `upstream merge`，不 fork-and-forget
3. **Hermes 内核化** — HermesAlpha 不再发展前端，只保留 `hermes-core/` 子包作为决策引擎
4. **数据湖优先** — 所有时序数据进 Parquet，SQLite 只存状态。不依赖 PostgreSQL
5. **单容器可跑** — Phase 1 部署不依赖外部 DB/消息队列，Docker Compose 一键启动
DATA_Q7M2X9LK_END
