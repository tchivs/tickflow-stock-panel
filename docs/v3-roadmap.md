# AthenaQuant v3.0 战略规划 — 智能因子挖掘与审计闭环

> 基于 AlphaMaster(RL 公式搜索)、PA_Agent(两阶段分析+审批票据)、UZI-Skill(防再犯工程)、QuantDinger(Agent 闸门)的核心思想,结合 AthenaQuant v2.x 已落地能力,规划下一阶段升级方向。
>
> **制定日期:** 2026-08-08 · **当前版本:** v2.3(Phase 35 执行中) · **目标版本:** v3.0

---

## 一、当前能力基线

### 已落地(v1.0→v2.3)

| 层 | 能力 | 状态 |
|----|------|------|
| **数据底座** | Parquet 数据湖 + DuckDB 视图 + Polars 热计算 + CapabilitySet provider 抽象 + 竞价/分钟/股池/概念多湖 + 回填管道 | ✅ 成熟 |
| **策略层** | 28+ builtin 规则策略 + AI 单文件生成器(AST 白名单) + engine(builtin/custom/ai 三源) + 监控规则引擎(盘中/盘前/持仓) | ✅ 成熟 |
| **因子研究** | factor_registry(immutable revision + DSL + ast/shape signature) + admission 晋升门控 + factor_dsl + evaluation + hypotheses + signal_chain + catalog | ✅ 地基已有,**缺自动化搜索** |
| **回测层** | StrategyEngine + walkforward + frozen_panel + ensemble + optimizer + 竞价回测 + backtest_results 湖 | ✅ 成熟 |
| **AI 分析** | 盘后复盘 + 个股分析 + 概念/行业分析 + LLM 护栏 + market_recap 流 | ✅ 基础完整 |
| **UI 工作台** | 24 React pages + SSE 实时 + e2e 回归 + Docker 部署 | ✅ 成熟 |
| **诚实护栏** | data_gate/三态归属/provenance manifest/POOL-03 零执行 AST 守卫/strategy_cache single-as_of | ✅ 贯穿全局 |

### 关键缺口(v3.0 要补的)

| 缺口 | 影响 | 参考项目 |
|------|------|----------|
| **因子挖掘无自动化搜索** | 因子全靠人写/AI 单文件生成,无 RL 搜索/词表/StackVM/walk-forward 自动选优 | AlphaMaster |
| **无 Agent 编排层** | 无 Moderator/多角色/BaseAgent 生命周期;LLM 分析是单次调用非可追溯流程 | PA_Agent / JCP |
| **无审计 envelope** | 工具调用只留最终文本,无 command/params/session/version/response_shape/raw_hash 留痕 | Privora/quant-buddy |
| **无审批/风控/paper-only** | AI 建议→交易动作无票据/风控/审批/paper 隔离;HermesAlpha 决策引擎未接入 paper 工作区 | PA_Agent / QuantDinger |
| **无 BUGS-LOG 防再犯** | bug 修完不留"未来注意事项+回归测试"checklist,同类问题可能再犯 | UZI-Skill |
| **无特征提取隔离层** | 策略/分析直接读 raw_data,未隔离到标准化 features → 口径漂移风险 | UZI-Skill |

---

## 二、三个参考项目的核心思想提炼

### AlphaMaster — RL 公式搜索闭环

```
数据层: Parquet → OHLCV tensors
    ↓
公式层: feature registry + operator registry → 确定性词表 (vocab_version = sha256(joined names)[:12])
    → AlphaGPT 受限 token 生成 → ConstrainedSampler (栈深/感染掩码) → StackVM 逆波兰式执行 [N,T]→[N,T]
    ↓
评估层: walk-forward 5 折 → IC direction gate → turnover/correlation penalty → train reward + validation score
    → champion gate: 训练验证差距 + 最小暴露 + 验证分比较
    ↓
产物层: strategy JSON (vocab_version + formula + formula_decoded + best_score + train_steps)
    ↓
服务层: 同一份 feature/VM/signal → backtest 和线上共用 (train-serve 一致)
```

**最高价值:**
- 确定性词表消除 token 兼容性隐患(特征/算子顺序变 → vocab_version 变 → 旧 token 失效)
- StackVM `[N,T]→[N,T]` 契约 + 恒正感染检查(防止因子退化为单边 beta)
- train-serve 一致(一份实现服务训练/回测/线上)
- REINFORCE + EMA baseline + entropy floor + elite replay + factor correlation penalty + adaptive restart

**AlphaMaster 缺失(AthenaQuant 要补):**
- 策略 JSON 未记录 raw data hash / feature registry snapshot / 训练 seed / commit / backtest report hash → **不可审计**
- OOS 分数仍同数据集 walk-forward,**非真正盲测**
- CORS `allow_origins=["*"]` + 无认证 → **安全薄弱**

### PA_Agent — 两阶段分析 + 审批票据 + paper-only

```
KlineFrame → PreflightDataGate (fail-closed 纯函数门)
    → Stage 1 诊断 (LLM → JSON → schema/semantic validation)
    → 路由策略文件 + 加载经验记录
    → Stage 2 决策 (LLM → JSON → schema/semantic validation)
    → AnalysisRecord (prompts/raw outputs/usage/errors — 不可删除证据)
    ↓ (persisted analysis)
ProposalService → candidate intent → FreshEvidenceCollector (重新取证,不复用陈旧价格)
    → RiskEngine.assess() (纯函数: precision/qty/notional/敞口/挂单/频率/日内损失/回撤/quote偏离/价差/费率/绑定)
    → ApprovalTicket (durabl, 原子 consume)
    → dispatch permit → PaperGateway operation
    → SQLiteExecutionLedger + Projection + Recovery + KillSwitch
```

**最高价值:**
- 两阶段分离:诊断可检查,决策可引用诊断中间态;JSON 截断/字段不符有明确错误路径
- PreflightDataGate:**LLM 前纯函数 fail-closed**;可计算事实(数据新鲜度/交易日/指标/仓位/价格)由程序主导,模型只能解释
- 审批票据:**批准时重新取证 + 重新跑 RiskEngine + 原子换取 permit**(陈旧价格/风险变化 → 票据失效)
- RiskEngine **纯函数**:表驱动测试 + 审计复算,不依赖 UI/gateway/ledger
- 经验库:按市场形态(broad_channel/spike/trending_tr/...)分类检索历史案例
- AnalysisRecord:**不可删除的过程证据**(不只报告正文)

**PA_Agent 需 A 股适配:**
- RiskPolicy 替换:整手/T+1/可卖数量/涨跌停/停牌/临停/可用资金/费用/行业集中度/调仓时间
- AGPL-3.0 → **不直接引入源码**,只复用模式

### UZI-Skill / QuantDinger — 审计与防再犯工程

**UZI-Skill BUGS-LOG(最高价值工程文件):**
```
每条 bug: 症状 → 位置 → 根因(3-5行) → 影响 → 修法 → 验证(N测试) → 回归测试文件名 → ⚠️未来改该区域注意事项
```
核心教训:**"优雅降级可以隐藏 bug"** — `.get(g, 1.0)` 让 6 个缺陷潜伏两版本;要硬断言不要优雅降级。

**特征提取隔离层:**
```
raw_data → extract_features(raw, dims) → ~60 标准化特征 (财务/估值/技术/规模/行业/衍生)
Criteria/策略 永远不直接读 raw_data,只读 features
特征名是接口契约,改动需同步 data-contracts + 测试
```

**QuantDinger Agent Gateway 六层闸门:**
```
scope (R/W/B/N/C/T) → allowlist (markets/instruments) → idempotency → audit (route/method/scope/request/response)
    → safe_exec (AST lint + 沙箱) → paper-only gate (实盘需 token+env+confirm 多重解锁)
```

---

## 三、v3.0 里程碑规划

### 总体方向

```
v2.x 已完成: 数据底座 + 固定策略 + 回测 + UI 工作台 + 诚实护栏
    ↓
v3.0 目标: 从"人写策略 + 单次 LLM 分析" → "自动因子挖掘 + Agent 决策闭环 + 全链路审计"
    ↓
阶段门禁: 审计底座 → 因子搜索 → Agent 决策 (先边界后智能)
```

### 里程碑命名

**v3.0 「智能因子挖掘与审计闭环」(Intelligent Factor Mining & Audit Loop)**

### Phase 分解(5 phases,36-40)

```
Phase 36: 审计底座 (Audit Foundation)        — ToolCallEnvelope + scope audit + BUGS-LOG + 特征隔离层
    ↓ (审计 envelope 是后续 Agent/因子的地基)
Phase 37: 因子搜索引擎 (Factor Search Engine)  — StackVM + 确定性词表 + RL 搜索 + walk-forward
    ↓ (搜索引擎产出因子,需要晋升门控)
Phase 38: 因子晋升与服役 (Factor Promotion)    — promotion gate + train-serve 一致 + 审计 manifest + catalog 整合
    ↓ (因子可用了,Agent 才有更丰富的信号源)
Phase 39: 两阶段 Agent 分析 (Two-Stage Agent)  — PA_Agent 诊断→决策 + PreflightGate + AnalysisRecord + 经验库
    ↓ (Agent 能分析了,需要安全地落地到动作)
Phase 40: 审批与模拟盘 (Approval & Paper Trading) — 审批票据 + RiskEngine 纯函数 + PaperGateway + KillSwitch
```

---

### Phase 36: 审计底座 (Audit Foundation)

**Goal:** 为所有工具调用、Agent 动作、因子实验建立统一留痕,让后续所有能力都可追溯、可重放、可审计。

**来源:** UZI-Skill BUGS-LOG + 特征隔离层;Privora/quant-buddy ToolCallEnvelope;QuantDinger scope audit;daily-stock-data 数据契约。

**Requirements (AUD-01..08):**

| # | 需求 | 来源 |
|---|------|------|
| AUD-01 | `ToolCallEnvelope` schema: 每次 CLI/gateway/API/skill 调用记录 `tool/command + params + session_id + version + auth_scope + response_shape + raw_hash + timestamp` | Privora/quant-buddy |
| AUD-02 | Agent scope audit 字段: `token_id + scope_class(R/W/B/N/C/T) + market/instrument_allowlist + paper_only + rate_limit + status_code` | QuantDinger |
| AUD-03 | 统一调用记录层: CLI/gateway/MCP/skill 调用都映射到 ToolCallEnvelope,落 Parquet 审计窄表 `data/audit/tool_calls/` | snowball/Privora |
| AUD-04 | BUGS-LOG 防再犯机制: 每个 bug 修复 PR 必须登记 `症状/位置/根因/影响/修法/验证/回归测试/⚠️未来注意事项`,关联回归测试文件 | UZI-Skill |
| AUD-05 | 特征提取隔离层 `extract_features(raw, dims)`: 策略/分析/因子 Criteria 只读标准化 features,不直接读 raw_data;特征名是接口契约 | UZI-Skill |
| AUD-06 | 数据质量 Banner: 报告/分析输出顶部显示 `最近交易日 / 缺失字段 / 降级状态 / cache 状态 / data_gate` | UZI/hhxg |
| AUD-07 | claim-to-source mapping: 报告中每个关键数字/判断有 `citation_key` 或明确标注为观点 | UZI/Awesome |
| AUD-08 | BUGS-LOG + audit 表 + features 的回归测试: 每个审计能力有命名测试,critical 字段 hard gate(不优雅降级) | UZI-Skill |

**验收:** ToolCallEnvelope 覆盖所有外部调用;一条 bug 从修复到 BUGS-LOG 到回归测试的完整闭环可演示;特征隔离层阻止策略直接读 raw_data(AST lint)。

**风险:** 审计开销(每次调用 +写入);features 迁移影响面大(所有策略/分析要改)。

---

### Phase 37: 因子搜索引擎 (Factor Search Engine)

**Goal:** 引入 AlphaMaster 风格的 RL 公式搜索,在已有 factor_registry/DSL/admission 地基上补上自动化搜索闭环。

**来源:** AlphaMaster StackVM + 词表 + REINFORCE + walk-forward;AthenaQuant 已有 research/factor_*。

**Requirements (SFE-01..09):**

| # | 需求 | 来源 |
|---|------|------|
| SFE-01 | 确定性词表: 从 `feature_registry.feature_names + operator_registry.operator_names` 派生 `FormulaVocab`,版本号 `vocab_version = "v" + sha256(joined)[:12]`;feature token `[0,F-1]`,operator token `[F,...)`;段内+跨段名称唯一性校验 | AlphaMaster |
| SFE-02 | StackVM 逆波兰式执行器: token 序列 → `[N,T]` 因子张量;feature push / operator pop-arity-execute-push / end 栈必须=1;NaN/Inf 规范化;未知 token/栈深不足/异常→候选失效;恒正感染检查 | AlphaMaster |
| SFE-03 | 算子注册表: 移动窗口/EMA/rank/correlation 采用历史窗口或递推;二元/三元校验形状一致;`[N,T]→[N,T]` 契约;因果性(无未来函数) | AlphaMaster + AthenaQuant factor_dsl |
| SFE-04 | AlphaGPT 受限 token 生成 + ConstrainedSampler: 根据栈深/剩余 token/感染状态生成合法掩码;最大长度 `MAX_FORMULA_LEN`(默认 8);REINFORCE 更新 token 概率 | AlphaMaster |
| SFE-05 | 搜索控制: EMA reward baseline(避免全负 batch 误选)+ entropy floor(防模式坍塌)+ elite replay pool(历史高分重放)+ factor correlation penalty(去冗余)+ adaptive restart(长期无改进扰动) | AlphaMaster |
| SFE-06 | walk-forward 评分: 5 折 rolling window(非 expanding);每折 IC direction gate → turnover/exposure/beta 中性/correlation 惩罚 → train reward + validation score;champion gate: 训练验证差距 + 最小暴露 + 验证分比较 | AlphaMaster |
| SFE-07 | 多目标回测目标: position=tanh(factor);pnl=position*target_ret-abs(delta)*cost;评分综合年化/Sortino/Calmar/IC/换手/暴露/前后一致性/beta 中性;A 股 target_ret = log(open_{T+2}/open_{T+1}) | AlphaMaster |
| SFE-08 | 因果性保证: target = T+2 open / T+1 open(可执行开盘后收益);特征窗口无未来泄漏;StackVM 恒正感染检查报告;**OOS 真正盲测段**(不参与任何搜索/选择) | AlphaMaster(补盲测) |
| SFE-09 | 搜索实验记录: 每次搜索保存 config + 随机种子 + 数据版本 + 候选分布 + 精英池快照 + 最终筛选阈值 → Parquet `data/research/search_runs/` | AlphaMaster(补审计) |

**验收:** 给定 Parquet 数据 + seed,搜索可复现产出同一最优公式;StackVM 对非法 token/栈溢出/未来函数 fail-closed;walk-forward 5 折评分通过;搜索实验可审计(config/seed/数据版本/候选分布)。

**风险:** RL 训练时间(AlphaMaster CPU 默认,公式评估由小张量构成);GPU 可能更慢(需实测);A 股 target_ret 定义需与执行时点一致(开盘竞价 vs 集合竞价)。

---

### Phase 38: 因子晋升与服役 (Factor Promotion & Serving)

**Goal:** 搜索产出的因子经过晋升门控后进入服役,train-serve 一致 + 审计 manifest,与已有 factor_registry/catalog/admission 整合。

**来源:** AlphaMaster train-serve 一致;AthenaQuant admission/catalog;AlphaMaster 审计缺失(补齐)。

**Requirements (FPR-01..07):**

| # | 需求 | 来源 |
|---|------|------|
| FPR-01 | 晋升门控: parser validity + OOS(真盲测段) + exposure + turnover + correlation + capacity(容量);不达标不晋升,有明确拒绝理由 | AlphaMaster + AthenaQuant admission |
| FPR-02 | train-serve 一致: 同一份 feature/VM/signal 实现服务训练/回测/线上;线上信号 = 最后一根已收盘 bar 的因子值 → 方向+强度;最少 MIN_BARS 历史预热 | AlphaMaster |
| FPR-03 | 不可变策略 manifest: 策略 JSON 包含 `vocab_version + formula + formula_decoded + best_score + train_steps + **raw_data_hash + feature_registry_snapshot + seed + code_commit + backtest_report_hash**` | AlphaMaster(补审计) |
| FPR-04 | 词表版本兼容: 加载策略时 `FORMULA_VOCAB.verify()` 拒绝不一致版本;运行时 feature/operator 顺序变更 → vocab_version 变 → 旧 token 失效(不静默误释) | AlphaMaster |
| FPR-05 | catalog 整合: 晋升因子注册到已有 `factor_registry`(immutable revision + ast/shape signature);catalog 可查询/比较/去重 | AthenaQuant research |
| FPR-06 | 策略侧整合: 晋升因子可作为 builtin 策略的 signal source(StrategyDef 的 factor 引用);回测引擎可消费 factor 策略 | AthenaQuant engine |
| FPR-07 | 服役监控: 因子上线后 IC 衰减/因子失效(deepear strengthened/weakened/falsified/priced_in 生命周期)追踪 | deepear + AlphaMaster |

**验收:** 一个因子从搜索→晋升→manifest→catalog→回测→线上信号的完整闭环;词表版本不兼容时 fail-closed 拒绝;manifest 可审计(raw_data_hash 可复算)。

**风险:** factor_registry 已有 immutable revision 机制 — 需确认 StackVM formula 能否映射到已有 DSL/ast_signature(可能需要扩展 DSL)。

---

### Phase 39: 两阶段 Agent 分析 (Two-Stage Agent Analysis)

**Goal:** 引入 PA_Agent 风格的两阶段分析(诊断→决策),PreflightGate fail-closed,AnalysisRecord 不可删除证据,经验库按市场形态检索。

**来源:** PA_Agent orchestrator/two_stage;PA_Agent preflight + decision_nodes;PA_Agent experience 库。

**Requirements (TSA-01..08):**

| # | 需求 | 来源 |
|---|------|------|
| TSA-01 | PreflightDataGate: LLM 前纯函数 fail-closed — 检查 frame 存在/OHLC 有效/K线数≥20/EMA20·ATR14 非全 NaN;失败输出可解释状态,不发 LLM 请求 | PA_Agent |
| TSA-02 | 两阶段分析: Stage 1 诊断(市场诊断 JSON)→ 路由策略文件+经验记录 → Stage 2 决策(交易决策 JSON);每阶段 JSON/schema/semantic validation + 截断修复 + 失败重试 | PA_Agent |
| TSA-03 | AnalysisRecord: 每次分析保存 `prompts + raw_outputs + usage(token/cost) + errors + diagnosis_json + decision_json + preflight_result` — 不可删除的过程证据 | PA_Agent |
| TSA-04 | 确定性门控: 可计算事实(数据新鲜度/交易日/指标缺失/仓位上限/价格阈值)由程序填充(decision_nodes),模型只能解释或补充;不可覆盖/可覆盖/模型主导/安全 gate 四级分类 | PA_Agent |
| TSA-05 | 经验库: 按市场形态(broad_channel/spike/trending_tr/micro_channel/normal_channel/tight_channel/trading_range/extreme_tr)分类检索历史案例;成功/失败分库;分析时自动检索同类形态案例供参考 | PA_Agent |
| TSA-06 | Moderator 路由: 先判断问题意图→选专家→分配任务(JCP 模式);保存 `intent + expert_list + task_map + 专家发言`;后续专家能看到前序发言 | JCP |
| TSA-07 | 持仓上下文: 同一股票在有/无持仓时上下文不同;分析能说明组合影响;建议包含组合约束 | PanWatch/Privora |
| TSA-08 | 增量分析: 新增 K 线时复用上次结论(增量);`keep_analysis` 模式新 K 线收盘自动触发新一轮分析 | PA_Agent |

**验收:** 一只股票从数据→PreflightGate→两阶段分析→AnalysisRecord 的完整链路;PreflightGate 失败时不发 LLM 请求(fail-closed 成本节约);经验库按形态检索可演示。

**风险:** LLM 成本(两阶段 = 2×调用);经验库初始为空(需积累或种子);A 股市场形态分类(PA_Agent 的 8 类是 Price Action 导向,A 股可能需要适配:连板/断板/低吸/打板/反包等)。

---

### Phase 40: 审批与模拟盘 (Approval & Paper Trading)

**Goal:** 从 AI 建议→审批票据→RiskEngine→PaperGateway→模拟盘的完整闭环,A 股 RiskPolicy,paper-only 不碰实盘。

**来源:** PA_Agent ApprovalService/RiskEngine/PaperTradingRuntime;QuantDinger paper-only gate;PanWatch suggestion pool。

**Requirements (APT-01..09):**

| # | 需求 | 来源 |
|---|------|------|
| APT-01 | Suggestion pool: AI 建议先入池(`proposed/accepted/rejected/expired`),有权重约束;不让 AI 建议直接变交易动作 | PanWatch |
| APT-02 | 审批票据模型: `ApprovalService.consume_ticket()` — 检查状态+时效 → **重新收集 evidence(不复用陈旧价格)** → 验证 candidate digest → **重新运行 RiskEngine** → 原子换取 dispatch permit | PA_Agent |
| APT-03 | RiskEngine 纯函数: 不依赖 UI/gateway/ledger;输入 immutable candidate+target+policy+evidence → 接受/拒绝;表驱动测试 + 审计复算 | PA_Agent |
| APT-04 | A 股 RiskPolicy: 整手(100股)/T+1/可卖数量/涨跌停(±10%/±20%科创创业板/±30%北交所)/停牌/临停/可用资金/费用(佣金+印花+过户费)/行业集中度/调仓时间(9:30-15:00) | PA_Agent(适配) |
| APT-05 | PaperGateway: 本地模拟账户执行;SQLiteExecutionLedger 记录;PaperProjectionBridge 投影;submission/recovery 接同一 gateway | PA_Agent |
| APT-06 | KillSwitch: 一键停止所有模拟盘操作;紧急撤退机制 | PA_Agent |
| APT-07 | paper-only gate: 实盘需 token+环境变量+确认参数多重解锁;默认 paper;UI 明确标注"模拟盘" | QuantDinger |
| APT-08 | 模拟盘对账: SQLiteExecutionLedger + 日终对账;projection vs 实际 fill 偏差记录;恢复机制(中断后可恢复) | PA_Agent |
| APT-09 | 审计留痕: 每个审批票据+风控评估+模拟操作记录到 audit 表(Phase 36 的 ToolCallEnvelope);可追溯从建议→审批→执行→结果 | PA_Agent + Phase 36 |

**验收:** 一个 AI 建议→入池→审批票据→RiskEngine 通过→PaperGateway 执行→模拟盘记录的完整链路;陈旧价格触发票据失效;RiskEngine 拒绝涨跌停/停牌/资金不足;KillSwitch 可演示紧急停止。

**风险:** paper broker 状态对账复杂(分布式事务 PA_Agent 也未完全覆盖);A 股 T+1 规则与日内模拟的交互;模拟盘与未来实盘的口径一致性。

---

## 四、与 v2.x 的衔接

```
v2.3 (当前,Phase 35 执行中)
    └─ 数据纵深解锁: 竞价回填 + 股池回填 + BT-07 回测 + 遗留补全
        └─ 产出: kline_auction 湖对齐 + backtest_results 湖 + 竞价验证报告
            ↓ 为 v3.0 提供数据底座
v3.0 Phase 36 (审计底座)
    └─ ToolCallEnvelope + scope audit + BUGS-LOG + 特征隔离层
        └─ 为 v3.0 所有后续 Phase 提供审计地基
            ↓
v3.0 Phase 37 (因子搜索)
    └─ StackVM + 词表 + RL 搜索
        └─ 消费 v2.x 的数据湖 (enriched + auction)
        └─ 产出: 可晋升因子
            ↓
v3.0 Phase 38 (因子晋升)
    └─ promotion gate + train-serve + manifest
        └─ 整合已有 factor_registry/catalog/admission
        └─ 产出: 服役因子 → StrategyDef signal source
            ↓
v3.0 Phase 39 (两阶段 Agent)
    └─ PreflightGate + 诊断→决策 + AnalysisRecord + 经验库
        └─ 消费 v3.0 因子信号 + v2.x 策略信号
        └─ 产出: 可审计的分析决策记录
            ↓
v3.0 Phase 40 (审批与模拟盘)
    └─ 票据 + RiskEngine + PaperGateway + KillSwitch
        └─ 消费 Agent 分析决策
        └─ 产出: paper-only 模拟盘记录
```

---

## 五、暂缓事项(不在 v3.0)

| 事项 | 暂缓理由 | 升级条件 |
|------|----------|----------|
| 实盘交易执行 | 风控/合规/责任边界未建立 | paper-only 运行 ≥3 个月 + 审批/风控/审计全链路验证 |
| LangGraph 完整状态机 | 流程未稳定,引入过早增加复杂度 | Agent 编排流程稳定 + 需要 checkpoint/replay/branch |
| 多用户/多租户 | 当前是个人自托管 | 出现真实多用户需求 |
| PostgreSQL 运行态 | 个人单机 SQLite + Parquet 足够 | 出现并发写/细粒度权限需求 |
| MCP 工具暴露 | 工具生态未稳定 | 稳定工具 + 需要 Claude/Cursor 原生发现 |
| WebSocket 双向交互 | 只读 SSE 足够 | 出现双向实时交互需求 |
| 完整多市场支持 | 当前聚焦 A 股 | A 股能力成熟 + 有跨市场需求 |

---

## 六、技术选型决策(遵循模式决策矩阵)

| 选择题 | v3.0 决策 | 理由 |
|--------|-----------|------|
| 因子搜索计算 | CPU(AlphaMaster 实测 CPU 更快 for 小张量公式) | 公式长度短 + Python 调度为主;GPU kernel 启动开销 > 并行收益;迁移前重新测量 |
| Agent 编排 | Moderator + 单 Agent(非 LangGraph) | 流程未稳定;Moderator 先选专家再串行讨论(JCP 模式)足够 |
| 审计存储 | Parquet 窄表 `data/audit/` | 冷查询 + DuckDB + 与现有湖一致 |
| 模拟盘状态 | SQLite | 本地单用户 + 与 PanWatch 一致 |
| 风控引擎 | 纯函数 + 表驱动 | 可测试 + 可审计复算(PA_Agent 模式) |
| 因子词表 | sha256 版本 + verify() 拒绝不一致 | AlphaMaster 确定性词表消除 token 兼容性隐患 |
| LLM 两阶段 | 2× 调用(诊断 + 决策) | 可检查中间态 > 节省成本;PreflightGate fail-closed 减少无效调用 |
| 外部依赖 | **零新增运行时依赖**(延续 v2.x) | StackVM/RL/审计/风控全用 stdlib + polars/numpy(已有) |

---

## 七、风险与缓解

| 风险 | 级别 | 缓解 |
|------|------|------|
| RL 搜索过拟合(AlphaMaster 也未解决) | HIGH | walk-forward + 真盲测段 + 因子相关性惩罚 + 多重比较校正 |
| 特征隔离层迁移影响面大 | HIGH | 渐进迁移:新策略强制 features,旧策略 grandfather;AST lint 只拦新增 |
| LLM 两阶段成本翻倍 | MEDIUM | PreflightGate fail-closed 减少无效调用;增量分析复用上次结论 |
| A 股 RiskPolicy 规则复杂 | MEDIUM | 表驱动 + 纯函数 + 穷举测试(涨跌停/停牌/T+1/整手边界) |
| paper broker 对账偏差 | MEDIUM | 日终对账 + projection vs fill 偏差记录 + 恢复机制 |
| AGPL 许可证(AlphaMaster/PA_Agent) | LOW | **不引入源码**,只复用设计模式;AthenaQuant 独立实现 |

---

## 八、成功指标

v3.0 成功当且仅当:

1. **因子搜索可复现**:给定数据 + seed,产出同一最优公式;walk-forward 通过;OOS 盲测段表现不崩
2. **Agent 分析可审计**:一次分析从数据→PreflightGate→两阶段→AnalysisRecord→建议 全链路可追溯;过程证据不可删除
3. **模拟盘闭环安全**:AI 建议→入池→审批→RiskEngine→PaperGateway 完整链路;陈旧价格/风控变化触发票据失效;KillSwitch 可紧急停止
4. **审计底座贯通**:所有外部调用有 ToolCallEnvelope;bug 修复有 BUGS-LOG + 回归测试;策略不直接读 raw_data(AST lint)
5. **零新增运行时依赖;POOL-03 零执行权边界不被突破;用户 Watchlist.tsx 零触碰**(延续 v2.x 护栏)

---

*本规划为战略性文档,具体 GSD 里程碑/Phase/Requirements 在 v3.0 里程碑启动时按研究→需求→路线→执行的 GSD 流程细化。*
