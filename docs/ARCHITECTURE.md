# AthenaQuant — 完全体架构文档

## 定位

AthenaQuant 是面向个人 A 股投资者的全栈量化研究平台，融合多个开源项目的核心能力，覆盖从数据底座、因子研究、策略进化、交易计划、AI 分析到持仓盯盘的全链路。

---

## 实现现状(先读)

> **本文档描述的是「完全体」目标蓝图**, 源项目索引指向规划期的外部仓库路径(他机), **不代表当前仓库结构**。
> 当前仓库是**自研单体**, 不是多仓库集成。

### 当前代码形态

- **后端**: 单体 FastAPI — `backend/app/`(`main.py` 组装 + `bootstrap.py` lifespan + 40 个 API 模块 + 55 个 services)。
- **前端**: 单体 React SPA — `frontend/src/`(Vite + TanStack Query + ECharts)。
- **存储**: 本地 Parquet 数据湖 + DuckDB + SQLite(operational.db)。单容器可跑。

### 蓝图能力落地状态

| 蓝图能力 | 状态 | 代码位置 |
|---|---|---|
| Parquet 数据湖 + DuckDB/Polars 计算 | ✅ 已落地 | `backend/app/tickflow/`, `parquet.py` |
| 实时行情轮询 + SSE 广播 | ✅ 已落地 | `services/quote_service.py`, `api/research_alpha_sse.py` |
| 多数据源联邦 + 能力探测 + typed 降级 | ✅ 已落地 | `data_providers/`(6 providers) |
| 确定性决策引擎 + LLM 护栏(受限字段/clamp/veto/审计) | ✅ 已落地 | `decision/`, `theses/`, `advanced/` |
| Shadow Account(交易日志→蒸馏→回测→信号) | ✅ 已落地 | `shadow/`, `backtest/` |
| 因子 DSL + IC/RankIC + 策略进化晋升门控 | ✅ 已落地 | `research/` |
| 竞价数据捕获/回填/验证 | ✅ 已落地 | `services/auction_*.py`, `api/auction_*.py` |
| Kronos 时序预测(分位数/样本路径) | ✅ 已落地 | `forecast/` |
| LangGraph 多 Agent 工作流 | 🟡 部分(单机 bounded 工作流) | `advanced/workflow.py` |
| 66 评委/博主立场跟踪/信息质量分级 | 🟡 规划中, 未在代码 | — |
| PWA 移动端 / 桌面端 / 多 Agent 会议室 | ❌ 未落地(蓝图前端扩展) | — |

### 导航建议

- 看应用如何组装: `backend/app/main.py` → `bootstrap.py` → 各 `api/*.py`。
- 看数据链路: `data_providers/` → `tickflow/repository.py` → `services/*_sync.py`。
- 看前端结构: `frontend/src/lib/api.ts`(统一 API 客户端)+ `router.tsx` + `pages/`。

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

```
┌───────────────────────────────────────────────────────────────────────┐
│                         前端交互层                                      │
│                                                                       │
│  主界面: tickflow React 工作台  (看盘/策略/回测/复盘/数据管理)           │
│  扩展:   PanWatch PWA            (移动端盯盘/通知)                      │
│  可选:   OpenAshare              (轻量研究/Agent 对话)                  │
│          JCP 桌面端              (多 Agent 会议室)                      │
├───────────────────────────────────────────────────────────────────────┤
│                         Agent 编排层                                    │
│                                                                       │
│  quantdinger Agent Gateway        tradingagents-family LangGraph       │
│  · 作用域 Token / 四级权限         · 多分析师辩论                        │
│  · 幂等 Job / 完整审计            · PM 决策聚合                         │
│  · SSE 进度推送                   · Checkpoint 断点续跑                 │
└────────────────────────┬──────────────────────────────────────────────┘
                         │
┌────────────────────────┼──────────────────────────────────────────────┐
│  ┌─────────────────┐ │ ┌──────────────┐ ┌────────────────────────┐   │
│  │ 因子/策略研究层   │ │ │  决策执行层   │ │     AI 分析层          │   │
│  │                 │ │ │              │ │                        │   │
│  │ alphaagent DSL  │ │ │ Hermes       │ │ PanWatch               │   │
│  │ · FactorZoo     │ │ │ · 确定性引擎  │ │ · TradingAgents        │   │
│  │ · IC/RankIC     │ │ │ · PIT 复权   │ │ · 建议池/信号评分       │   │
│  │ · LLM 因子挖掘  │ │ │ · 受限 LLM   │ │                        │   │
│  │                 │ │ │   护栏       │ │ ai-berkshire           │   │
│  │ qlib            │ │ │ · 纪律评分   │ │ · 信息质量 A/B/C 分级   │   │
│  │ · 实验记录      │ │ │ · LLM 审计   │ │ · 数值交叉校验          │   │
│  │ · 模型 Zoo      │ │ │ · Replay    │ │ · 投资论点追踪          │   │
│  │ · 滚动训练      │ │ │   零 LLM    │ │                        │   │
│  │                 │ │ │   隔离      │ │ uzi-skill              │   │
│  │ alpha-evolution │ │ │              │ │ · 66 评委评分          │   │
│  │ · 变异/交叉     │ │ │ tickflow     │ │ · DCF/LBO/IC Memo      │   │
│  │ · 晋升门控      │ │ │ · 18 内置    │ │                        │   │
│  │ · 轨迹池        │ │ │   策略       │ │ deepear                │   │
│  │                 │ │ │ · 自定义/   │ │ · 信号生命周期          │   │
│  │ rd-agent        │ │ │   AI 策略   │ │   (strengthened/       │   │
│  │ · 假设循环      │ │ │              │ │    weakened/falsified  │   │
│  │ · 实验沙箱      │ │ │ quantdinger  │ │    /priced_in)         │   │
│  │ · 反馈闭环      │ │ │ · 策略沙箱  │ │                        │   │
│  │                 │ │ │ · Python    │ │ x2t                    │   │
│  │ vibe-trading    │ │ │   合约 AST  │ │ · 博主立场标注          │   │
│  │ · Shadow Account│ │ │   校验      │ │ · Flip Radar           │   │
│  │ · 452 Alpha     │ │ │ · 沙箱     │ │ · Wilson 置信区间       │   │
│  │ · 9 回测引擎    │ │ │   执行     │ │ · FDR 多重比较校正      │   │
│  └─────────────────┘ │ └──────────────┘ └────────────────────────┘   │
└────────────────────────┼──────────────────────────────────────────────┘
                         │
┌────────────────────────┴──────────────────────────────────────────────┐
│                         数据底座层                                      │
│                                                                       │
│  tickflow Parquet 数据湖             daily-stock-data 治理层           │
│  · DuckDB 视图 + Polars 计算         · 表契约 (主键/时间语义)          │
│  · 日K / 分钟K / 复权因子 / 财务     · Schema drift CI 检测            │
│  · 概念 / 行业 / 连板 / 池           · 修复窗口同步                    │
│  · 扩展数据 (外部数据接入)            · CSV/PG 迁移模式                 │
│                                                                       │
│  PanWatch SQLite (状态持久层)         tdx-market-data (备用行情源)      │
│  · 账户 / 持仓 / 仓位                · 通达信二进制解码                  │
│  · 价格规则 / 通知通道               · 连接池 / 主机探测                │
│  · 建议池 / 信号 / 评估              · VIPDOC / F10 / MCP              │
│  · 模拟盘 / 聊天                     · 日线 / 分钟线 / 盘口            │
│                                                                       │
│  Hermes PostgreSQL → 逐步迁移到       financial-timeseries-model        │
│  tickflow Parquet + SQLite           · Kronos 时序预测服务              │
│  · 引擎基线 / 信号历史               · K 线 Tokenization               │
│  · LLM 审计日志 / Prompt 版本        · MoE / 分位数预测                │
│  · 研报信号 / 投研候选               · Qlib 微调接口                   │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 核心数据流

### 盘前 (Pre-market)

```
每日 pipeline (AP Scheduler 触发):
  tickflow 数据同步
    ├─ sync_instruments → 更新股票列表
    ├─ sync_daily_all    → 拉取日K + 复权因子
    ├─ compute_enriched  → 技术指标预计算
    ├─ sync_financials   → 财务数据
    └─ sync_index/etf    → 指数/ETF
       │
       ▼
  Hermes EOD pipeline:
    ├─ market_state      → 市场状态判定 (趋势/震荡/弱势)
    ├─ factors           → PIT 因子计算
    ├─ quality_screen    → 质量筛选
    ├─ score             → 6 因子综合评分
    ├─ pool              → 执行池/观察池/风险池分层
    └─ playbook          → 入场区间/止损/目标/仓位
       │
       ▼
  PanWatch:
    ├─ daily_report     → AI 日报生成
    ├─ premarket_outlook → 盘前展望
    └─ strategy_signals  → 策略信号刷新
```

### 盘中 (Intraday)

```
tickflow QuoteService:
  ┌─ 轮询行情 → 写入今日 Parquet → 计算今日 Enriched
  │
  ├→ SSE 广播 (quotes_updated / depth_updated / strategy_alert)
  │    └→ 前端实时更新看板
  │
  ├→ PanWatch PriceAlertEngine (每 60s):
  │    ├─ 条件匹配 (AND/OR/时段/冷却)
  │    ├─ 命中 → PriceAlertHit → 通知 (Telegram/钉钉/飞书…)
  │    └─ 触发 TradingAgents 深度分析 (可选)
  │
  ├→ PanWatch 持仓监控:
  │    ├─ 持仓异动感知
  │    └─ 自动盈亏提醒
  │
  └→ MonitorRuleEngine (策略/价格/市场/连板规则)
       └─ 告警事件持久化 + SSE 推送
```

### 盘后 (Post-market)

```
tickflow:
  └─ 复盘报告生成 (AI market recap)
       ├─ 大盘回顾 / 情绪指标 / 雷达图
       ├─ 概念/行业/连板复盘
       └─ 推送飞书 (可选)

Hermes:
  └─ review → LLM 受限调整 playbook
       ├─ 仅允许调整 entry_low/entry_high/stop/target/position_pct
       ├─ 方向受限 / 越界 clamp / 违规 veto
       ├─ 保留 engine 基线用于对比
       └─ 审计日志记录每次调整

PanWatch:
  ├─ 建议池过期清理
  ├─ 信号结果评估 (entry_candidate_outcomes)
  └─ 模拟盘日终结算

x2t (可选):
  └─ 财经博主观点日更 → 立场 flip 检测 → 战绩结算
```

---

## 集成模块说明

### 1. 因子/策略研究层 (Phase 2)

| 组件 | 职责 | 来源 |
|---|---|---|
| **Factor DSL** | 受限制的因子表达式语言，解析器 + 操作符白名单 | `alphaagent` |
| **FactorZoo** | 因子存储/检索/相似度去重 | `alphaagent` |
| **IC/RankIC** | 因子评价指标，分组收益/多空收益 | `alphaagent` |
| **LLM 因子挖掘** | 自然语言描述 → DSL 因子 → 回测验证 | `alphaagent` |
| **实验记录** | MLflow 式 run 管理 (config/dataset/prediction/metrics/artifact) | `qlib` |
| **模型 Zoo** | 预训练/微调模型注册与版本管理 | `qlib` |
| **策略进化** | ResearchAsset → Mutation → Evaluation → PromotionGate → Champion | `alpha-evolution-lab` |
| **研发循环** | Hypothesis → Experiment Spec → Sandbox → Run → Feedback | `rd-agent` |

### 2. 决策执行层

| 组件 | 职责 | 来源 |
|---|---|---|
| **确定性引擎** | PIT 因子 → 评分 → 质量筛选 → 池分层 → 交易计划 | `HermesAlpha` |
| **LLM 护栏** | 受限字段调整 + 方向约束 + clamp + veto + 基线保留 | `HermesAlpha` |
| **PIT Replay** | 零 LLM 物理隔离的历史重放 | `HermesAlpha` |
| **纪律评分** | 实盘 vs 计划对比: 追高/超仓/计划外交易 | `HermesAlpha` |
| **LLM 审计** | 每次调用 prompt/config/call/version 全留痕 | `HermesAlpha` |
| **策略沙箱** | Python AST 校验 + 导入白名单 + 超时/内存守卫 | `quantdinger` |
| **策略合约** | 策略上传前的机器可读合约 + 结构化校验 | `quantdinger` |
| **Shadow Account** | 实盘交易日志 → 策略蒸馏 → 回测 → 信号扫描 | `vibe-trading` |

### 3. AI 分析层

| 组件 | 职责 | 来源 |
|---|---|---|
| **TradingAgents** | 多分析师辩论 → PM 决策 → 5 级评级 | `PanWatch` |
| **建议池/信号** | 归一化管理 + 过期 + 防抖动 + 信号评分 | `PanWatch` |
| **66 评委** | 多流派评分矩阵 + DCF/LBO/IC Memo | `uzi-skill` |
| **信息质量分级** | A/B/C 三级数据质量 → 分析深度自适应 | `ai-berkshire` |
| **数值交叉校验** | 从报告提取数值 → 跨源比对 → 发现偏差则拒绝 | `ai-berkshire` |
| **投资论点追踪** | 买入逻辑/估值锚/失效条件/季度核验 | `ai-berkshire` |
| **信号生命周期** | strengthened / weakened / falsified / priced_in | `deepear` |
| **博主观点跟踪** | 立场标注 + flip radar + Wilson 置信区间 + FDR 校正 | `x2t` |

### 4. Agent 编排层

| 组件 | 职责 | 来源 |
|---|---|---|
| **Agent Gateway** | 机器 API, 作用域 Token, 市场/标的白名单, 限流 | `quantdinger` |
| **幂等 Job** | idempotency key + 审计摘要 + SSE 进度 | `quantdinger` |
| **四级权限** | read / backtest / notify / trade 硬隔离 | `quantdinger` |
| **多 Agent 辩论** | LangGraph 分析师/多空/风控角色辩论 | `tradingagents-family` |
| **Checkpoint** | 长任务断点续跑 + 状态恢复 | `tradingagents-family` |

### 5. 数据底座层

| 组件 | 职责 | 来源 |
|---|---|---|
| **Parquet 数据湖** | 日K/分钟K/复权/财务/扩展数据的 Parquet 存储 | `tickflow` |
| **DuckDB 视图** | 内存级 SQL 查询层 | `tickflow` |
| **Polars 计算** | 技术指标/信号/评分的高性能计算 | `tickflow` |
| **实时行情 SSE** | 盘中行情轮询 + 增量 enriched 计算 + 广播 | `tickflow` |
| **SQLite 状态** | 持仓/规则/建议/信号/模拟盘/聊天 | `PanWatch` |
| **数据契约** | 表主键/时间语义/修复窗口 | `daily-stock-data` |
| **Schema CI** | 检测 schema drift / 脚本语法 / secret 泄露 | `daily-stock-data` |
| **通达信协议** | 备用行情源 (二进制解码/连接池/主机探测) | `tdx-market-data-clients` |
| **Kronos 模型** | 时序预测 API (分位数/样本路径/checkpoint) | `financial-timeseries-foundation` |

---

## 渐进式接入路线

### Phase 1 — 核心合并 (预计 2 周)

**目标:** 跑通数据底座 + 持仓盯盘闭环

```
tickflow-stock-panel (基础)
  + PanWatch (持仓 + 通知 + 盯盘)
  + Hermes 决策内核 (engines + llm + replay)
```

目录结构:

```
AthenaQuant/
├── tickflow-stock-panel/   ← fork, 保持 upstream 同步
│   ├── backend/
│   └── frontend/
├── PanWatch/               ← fork, 保持 upstream 同步
│   ├── src/
│   └── frontend/
├── hermes-core/            ← 从 HermesAlpha 抽取
│   ├── engines/            (factor → score → pool → playbook → discipline)
│   ├── llm/                (gateway + review_agent + report_agent)
│   ├── services/           (replay + signal_performance)
│   ├── models/             (signals/scores/factors/pool/replay/llm_audit)
│   └── tests/
├── data/                   ← tickflow Parquet 湖
│   ├── kline_daily/
│   ├── kline_minute/
│   ├── financials/
│   └── ...
└── docs/
    └── ARCHITECTURE.md
```

### Phase 2 — 因子/策略强化 (预计 1 周)

```
+ alphaagent DSL + FactorZoo
+ qlib 实验记录
+ tickflow 扩展: 因子注册 → 回测 → 实验管理
```

### Phase 3 — AI 分析增强 (预计 1 周)

```
+ uzi-skill 66 评委报告
+ deepear 信号生命周期
+ ai-berkshire 质量分级 + 数值校验
```

### Phase 4 — 进阶能力 (预计 1 周)

```
+ x2t 观点追踪
+ rd-agent 研发循环
+ alpha-evolution 策略进化
+ quantdinger 策略沙箱
```

### Phase 5 — 锦上添花 (可选)

```
+ vibe-trading Shadow Account
+ ai-berkshire 投资论点追踪
+ Kronos 时序预测
```

---

## 设计原则

1. **可弃可留** — 每个模块都是独立子包，不强制全上。个人用户可以从 Phase 1 跑起来，按需激活后续能力
2. **上游同步** — tickflow 和 PanWatch 保持 fork 关系，定期 `upstream merge`，不 fork-and-forget
3. **Hermes 内核化** — HermesAlpha 不再发展前端，只保留 `hermes-core/` 子包作为决策引擎
4. **数据湖优先** — 所有时序数据进 Parquet，SQLite 只存状态。不依赖 PostgreSQL
5. **单容器可跑** — Phase 1 部署不依赖外部 DB/消息队列，Docker Compose 一键启动
