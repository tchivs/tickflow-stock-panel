---
phase: 05
slug: optional-enhancements
status: draft
shadcn_initialized: false
preset: none
created: 2026-07-15
---

# Phase 05 — UI Design Contract

> 在已完成的 AthenaQuant v1 回路中，以可独立启用的方式加入 Shadow 成交证据蒸馏、版本化投资论点和 Kronos 概率预测。三个模块只生成可审阅研究记录或待人工确认结论；不得改变既有应用壳、自动激活策略、修改论点、创建监控/计划、同步持仓或执行市场动作。

---

## Scope and Source Decisions

| Source | Binding UI decision |
|---|---|
| `REQUIREMENTS.md` SHDW-01 | 用户从本地真实成交日志建立不可变导入批次，冻结证据集，查看可解释候选及独立样本内/样本外评估；保留候选不等于注册、启用或执行策略。 |
| `REQUIREMENTS.md` THES-01 | 用户在标的对象内查看不可变论点版本、带假设的估值区间、结构化失效条件、每条件检查周期、追加式检查与人工确认历史。 |
| `REQUIREMENTS.md` FORE-01 | 研究者在单一 A 股标的内请求 5/20/60 个交易日预测，并可同时检查 P10/P50/P90、采样路径、受治理输入与固定 checkpoint 谱系。 |
| `05-CONTEXT.md` D-01–D-04 | Shadow 只接受本地执行日志；每次导入均追加；候选必须解释规则、特征、参数、来源和限制；保留资格必须有冻结证据与时间顺序 IS/OOS 评估。 |
| `05-CONTEXT.md` D-05–D-08 | 论点与版本不可变；估值锚必须是带显式假设的区间；条件命中只产生待确认结论；每个条件独立配置 cadence，检查结果追加而不覆写。 |
| `05-CONTEXT.md` D-09–D-12 | Kronos 仅处理对象绑定的日线 OHLCV 和 5/20/60 日范围；P10/P50/P90 与采样路径均为首要结果；运行冻结批准 checkpoint 身份/修订/摘要；后续实际结果和校准追加到原记录。 |
| `05-RESEARCH.md` | 复用 typed `api.ts`、TanStack Query、对象局部缓存、受控 SSE、ECharts、不可变工件和 Phase 2–4 证据模式；三个模块分别呈现 typed unavailable，不引入第二状态库、图表库、壳或远程 checkpoint 下载体验。 |
| `PRODUCT.md` / `DESIGN.md` | “研究账本”、证据先于主张、明确权限、历史可见、可选能力独立；暗色优先、完整亮色、单一电光蓝、市场红绿与系统状态隔离、WCAG 2.2 AA、44px 小屏触区和 reduced motion 为规范。 |
| Phase 04 `04-UI-SPEC.md` | 延续现有 Backtest/Analysis 放置、PageHeader、语义 tab、原生表单、表格/`details`、对象局部失效、不可用/部分/终态表达；不初始化 shadcn，不增加顶级导航或“高级研究中心”。 |

### Phase boundary

- **In scope:** 不可变 Shadow 导入/映射/诊断/证据集、可解释候选、IS/OOS 评估和候选保留；标的论点版本、估值锚、条件 cadence、检查、待确认与确认/驳回历史；单标的 Kronos 请求、P10/P50/P90、可检查路径、checkpoint 谱系、不可变预测历史和成熟后校准。
- **Out of scope:** 新顶级导航、第二侧栏或平行应用壳；券商连接、逐笔手工录入、持仓同步；自动注册/启用 Shadow 策略；单点目标价论点；自动确认失效；组合批量、盘中或任意 horizon 预测；运行时下载/选择未批准 checkpoint；预测驱动论点、策略、计划、监控、持仓或交易；删除/覆写历史。
- **Independence invariant:** `Shadow`、`Thesis`、`Forecast` 能力分别探测、分别加载、分别失败。一个模块 unavailable/error/loading 时，既有 v1 与另外两个模块仍可操作；页面不得用一个总开关或整页错误替代三个局部状态。

---

## Design System

| Property | Value |
|---|---|
| Tool | 现有手工系统：Tailwind CSS 3.4 token + 本地 React 组件 |
| Preset | 不适用；根目录和 `frontend/` 均无 `components.json`，沿用 Phase 04 决定，不初始化 shadcn |
| Component library | 现有 `PageHeader`、`EmptyState`、`Skeleton`、本地 dialog、语义表格、原生表单、`details/summary`；不安装新组件库 |
| Icon library | `lucide-react`；14–16px 图标只辅助完整文字，不单独表达不可用、失效、保留、校准或预测方向 |
| Chart library | 现有 ECharts 5.5；Forecast 图表必须同时提供可读摘要和数据表，不增加第二图表库 |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, system sans；`JetBrains Mono` / `IBM Plex Mono` 仅用于数值、标的、版本、时间、参数、指纹和摘要 |
| Server state | 统一 typed `api.ts` + TanStack Query + `QK` factories；缓存键至少包含模块、标的/研究对象、不可变记录或版本 ID；SSE 完成只失效受影响对象，客户端不得推断 fingerprint、checkpoint、quantile、门禁或官方状态 |
| Existing surfaces | Backtest `策略回测` 面板承载 Shadow；Stock `AnalysisWorkspace` 的既有 tablist 承载 `投资论点` 和 `概率预测`；Portfolio 不显示 Forecast，Phase 05 不创建新 shell |

### Existing visual tokens to preserve

严格沿用 `frontend/src/index.css`、`frontend/tailwind.config.ts` 与 `DESIGN.md` 的 `base`、`surface`、`elevated`、`border`、`foreground`、`secondary`、`muted`、`accent`、`warning`、`danger`、`bull`、`bear`。默认暗色且亮色语义一致；静态容器使用 1px 边界和色阶，不以宽阴影制造层级。保留 `rounded-input` 4px、`rounded-btn` 6px、`rounded-card` 8px、`rounded-dialog` 12px。禁止渐变、渐变文字、发光、玻璃化、粗侧边色条、嵌套卡片、赌场式预测视觉和“AI/模型控制台”装饰。

---

## Information Architecture and Placement

### Existing shell integration

1. **Shadow → Backtest / 策略回测：** 保持 `回测工作台` 的 `因子回测 / 策略回测 / 参数优化` 顶部模式不变。在策略 panel 中，按 `StrategyBacktest → ResearchLibrary → ExperimentComparison → Shadow 成交证据与候选 → AdvancedResearchPanels` 排列。Shadow 是一个页面内 section，不增加第四个回测模式或顶级导航。
2. **Thesis → Stock AnalysisWorkspace：** 仅在 `subject.kind === stock` 时，在现有 `分析结论 / 来源与核验 / 信号历史` tablist 后追加 `投资论点` tab。当前标的名称/代码来自既有对象上下文，表单不允许自由改写标的。Portfolio 的 AnalysisWorkspace 保持原样。
3. **Forecast → 同一 Stock AnalysisWorkspace：** 在 `投资论点` 后追加 `概率预测` tab；它与论点并列而非嵌入论点，避免预测被误认作论点证据或自动动作。只在 stock 对象显示；不在 Portfolio、Dashboard 或 Backtest 提供批量入口。
4. **独立 unavailable：** Shadow section、`投资论点` tab panel、`概率预测` tab panel 各自查询 capability。能力未启用时保留该模块的位置和说明，但不禁用现有 tab、报告、回测或其他可选模块。
5. **历史是每个模块的第二层主区域：** 当前状态和下一步在前，当前记录的来源/不确定性紧随其后；不可变批次、版本、检查、预测、校准和终态运行通过语义表格、时间线和 `details` 展开。重要谱系不得只在 tooltip 或 hover 中。

### Workspace tab contract

- 继续使用真实 `tablist/tab/tabpanel`、roving `tabIndex`、`aria-selected`、`aria-controls` 和 Left/Right 键；切换 tab 保留各 tab 对象局部滚动位置和已选不可变记录。
- 小屏 tablist 可见横向滚动，不裁剪 `投资论点`、`概率预测` 或可用性文字；tab 的命中区至少 44px 高。
- unavailable 不是 disabled tab：用户必须能进入 panel 读取原因、影响范围和恢复路径。加载 capability 时显示稳定宽度的状态占位，不让 tab 顺序跳动。

---

## Shadow Account Contract (SHDW-01)

### Page hierarchy

| Region | Required visible data and behavior |
|---|---|
| 模块头 | 标题 `Shadow 成交证据与策略候选`；固定说明 `仅从本地实际成交日志形成研究证据，不连接券商、不同步持仓、不执行交易。`；显示模块 `可用 / 不可用` 完整文字。 |
| 导入工作流 | 按 `1 选择日志 → 2 映射与预览 → 3 确认不可变导入` 呈现真实顺序。接受格式、大小/行数上限和源时区在文件选择前可见；不提供手工逐笔录入。 |
| 不可变批次 | 倒序表显示批次人类标签、原文件名、来源标签、导入人、创建时间、内容摘要、映射版本、总行/有效/诊断数量、`same content`/`supersedes` 谱系和状态。每次重导入均为新行；无编辑、覆盖或删除。 |
| 证据集 | 用户选择已完成批次及明确排除项；摘要先显示纳入批次/成交数、重复组和部分成交提示，再显示冻结 fingerprint。创建后只读；变更必须 `创建新证据集`。 |
| 可解释候选 | 先显示资格与限制，再显示 if/then 进入规则、特征、阈值、支持度、precision/recall、参数、退出/持有假设、时间窗口、seed、class balance、来源批次和 evidence fingerprint。禁止只显示综合分数、自然语言“风格”或黑盒相似度。 |
| IS/OOS 评估 | 固定两列或两行 `样本内`、`样本外`，均显示不重叠窗口、状态、precision/recall、coverage、候选成交数、收益、回撤、成本后指标、实际成交一致度、数据调整口径与工件入口。全样本指标只能作为补充，不能替代。 |
| 保留与历史 | 只有 IS 和 OOS 都为服务端 `通过` 且证据完整时启用 `保留为 Shadow 研究候选`。确认内容复述证据集、两段评估和“不会注册或启用策略”。成功追加保留事件；旧候选、失败、重试和批次始终可访问。 |

### Import interaction sequence

1. 点击 `选择本地成交日志` 触发原生 file input；文件尚未上传前显示支持格式和隐私说明。
2. 上传解析期间按钮文字为 `正在解析日志…`；固定 skeleton 预留映射表高度，既有批次历史保持可读。
3. 映射表按 `目标字段 / 来源列 / 样例值 / 单位与时区 / 状态` 排列。必需字段为标的、方向、成交时间、数量和价格；费用、币种、账户别名、成交 ID 明确标为可选或缺失限制。错误聚合摘要链接到首个问题字段。
4. 预览最多显示受限样例行，并在表头显示“仅为预览”；重复组和 partial fills 以完整文字提示，默认不自动删除/合并。原始账户秘密由服务端安全投影，不能回显本地路径。
5. 点击 `确认不可变导入` 前，确认区复述原文件名、来源标签、时区、映射、行数和不可覆写说明；确认后创建新 batch。解析失败批次保留诊断但不能进入证据集。
6. 用户以已有批次为参考修正时，动作名为 `导入修正批次`；新 batch 显示 `修正自 {batchLabel}`，旧 batch 不变。

### Shadow states

| State | Contract |
|---|---|
| loading | capability、批次、候选分别局部 loading；映射/蒸馏/评估显示明确阶段，不清空历史。SSE 只更新允许的阶段文字。 |
| empty | 三种空态必须分别使用 Copywriting Contract 中的精确标题、说明和操作：无批次、已有完成批次但无证据集、已有证据集但无候选；不得合并或以通用“暂无数据”替代。 |
| unavailable | `此部署未启用 Shadow 蒸馏模块。现有回测、研究库和 v1 工作流仍可使用。请联系部署维护者启用 Shadow 可选依赖。` 无伪上传按钮、spinner 或自动重试。 |
| stale | 新批次出现后，既有证据集/候选显示 `存在较新成交批次；当前候选仍基于已冻结证据。`；提供 `创建新证据集`，不得静默纳入新批次或改旧 candidate。 |
| partial | 可读批次包含字段诊断、重复组、缺费用或部分行失败时，显示有效/无效计数与限制；不把部分成功说成完整成功，禁止异常行静默进入证据集。 |
| error | 导入解析使用 `Shadow import error`；网络/加载、候选蒸馏、IS/OOS 评估分别使用 Copywriting Contract 中的 `Shadow network/load failure`、`Shadow distillation failure`、`Shadow IS/OOS evaluation failure` 精确标题、说明、保留状态、终态记录规则和恢复操作。不得以通用错误或普通重试替代。 |
| pending confirmation | `确认不可变导入` 与 `保留为 Shadow 研究候选` 均使用显式确认；对话框复述对象、证据和不可变/不激活后果。 |
| terminal | 成功、验证失败、超时、资源终止均成为只读运行记录；`Shadow distillation failure` 与 `Shadow IS/OOS evaluation failure` 不生成候选或保留资格，失败运行只读保留，重试创建新运行。加载失败不创建运行记录。 |
| long content | 长文件名、批次/候选 ID、fingerprint、规则与限制安全换行；规则表和历史表横向滚动且保留字段标题，完整 JSON 只在可访问 `details` 中。 |

---

## Investment Thesis Contract (THES-01)

### Page hierarchy

| Region | Required visible data and behavior |
|---|---|
| 对象与官方状态 | 标题 `投资论点`，紧随当前标的名称/代码、当前版本、官方状态、创建/生效时间和前序版本。固定说明 `自动检查只能提出待确认结论，不能替你改变论点状态。` |
| 待确认结论 | 若存在，置于 tab panel 首个操作区，显示 `待确认失效结论`、命中条件、观测值/阈值、证据来源/时间/fingerprint、对应版本和检查记录；官方状态仍明确显示 `未改变，等待你的确认`。 |
| 核心判断 | 显示版本化判断、理由和限制；只读版本使用 `基于此版本创建新版本`，不提供“编辑当前版本”。 |
| 估值锚 | 每个 anchor 必须显示方法、币种、截至日、低值/高值区间、显式假设和限制。没有区间或假设的草稿不能创建版本；单一目标价或 AI 报告链接不能替代 canonical anchor。 |
| 结构化条件 | 每行显示条件名称、来源类型、字段、运算符、阈值/区间、单位、lookback/period、独立 cadence、时区、next due、最近检查结果。自由文本仅作说明，机器检查依赖可见结构字段。 |
| 检查历史 | 按条件筛选的追加式时间线/表格显示 due time、checked time、结果 `命中 / 未命中 / 证据不足 / 检查错误`、观测值、证据、版本和待确认/确认/驳回关系；历史不可编辑或删除。 |
| 版本时间线 | 倒序显示版本号、前序版本、创建人/时间、变更理由、anchor 数、condition 数、当时官方状态与 `查看完整版本`。选中旧版本时固定标记 `历史版本，不再执行定期检查`。 |

### Create/version interaction sequence

1. 无论新建或 `基于此版本创建新版本`，表单都在当前对象 panel 内展开；依次填写 `核心判断与理由 → 估值锚 → 失效条件与各自 cadence → 版本变更理由`。
2. 估值 low/high、币种、截至日和至少一条非空假设为必填；`high < low`、缺单位或缺假设时显示字段错误并聚焦首错。
3. 条件使用受限 select/number/date 控件；source 变化后清理不兼容 field/operator，并通过 `role=status` 说明。每一条条件独立选择 daily/weekly/monthly/quarterly cadence，不出现全局 cadence 控件。
4. 提交前显示只读审阅摘要；主动作 `创建不可变论点版本`。确认对话框说明旧版本继续保留、旧检查历史不变、新版本条件从新 cadence 开始。
5. 成功后选中新版本并以 polite status 宣布；TanStack Query 只失效当前 instrument 的 thesis 列表/版本/条件，不刷新其他对象或 Forecast。

### Pending confirmation sequence

1. condition `matched` 仅显示待确认结论，不改变官方状态，不自动打开 dialog，不自动滚动。
2. `确认论点失效` 打开危险确认 dialog，复述标的、版本、条件、证据和“此操作记录官方失效事件，但不会交易或修改其他研究对象”；要求至少 10 个字符理由。
3. `驳回待确认结论` 使用次级确认，要求理由并说明条件/检查记录仍保留；驳回后官方状态不变。
4. 并发冲突或已处理 proposal 显示 `结论未记录：状态已变化，请重新查看当前论点。`，保留用户理由并重新拉取当前 instrument。
5. 已确认失效的版本进入 terminal read-only；可 `基于此版本创建新论点版本`，但不能重开或改写该版本。

### Thesis states

| State | Contract |
|---|---|
| loading | 当前版本、pending、检查历史分别使用稳定 skeleton；已有版本不因后台刷新消失。 |
| empty | `尚无投资论点`，说明先记录判断、带假设估值区间和可检查条件；CTA `创建第一版投资论点`。 |
| unavailable | `此部署未启用投资论点模块。当前分析报告、证据和信号历史仍可使用。请联系部署维护者启用投资论点可选依赖并恢复条件检查调度。` 不影响 Forecast tab。 |
| stale | 旧版本显示 `历史版本，不再执行定期检查`；当前条件超过 next due 且尚无检查显示 `检查已逾期，等待调度恢复`；缓存刷新失败则显示上次成功时间。不得把 stale 当最新。 |
| partial | anchor/条件/check 任一来源缺失时显示具体 `证据不足`、缺失字段和可用内容；缺证据不等于未命中，也不创建 pending。 |
| error | 读取失败与证据检查失败分别使用 Copywriting Contract 中的精确合同；版本创建和确认/驳回传输不确定分别使用 `Thesis immutable-version creation failure`、`Thesis confirm/reject transport uncertainty` 的精确标题、说明、保留状态、终态记录规则和恢复操作。字段验证与确认冲突继续分别表达；检查错误作为追加事实保留，不改变官方状态。 |
| pending confirmation | warning 语义、完整证据和两个明确动作；官方状态文字保持不变，绝不只用橙色或时钟图标。 |
| terminal | 已确认失效、已被新版本取代的旧版本均只读；显示事件人、时间、理由和相关证据。terminal 不隐藏创建新版本入口。 |
| long content | 判断/理由/假设最多 65–75ch 行宽并自然换行；条件表、版本表横向滚动；fingerprint/ID 可复制和 `overflow-wrap:anywhere`。 |

---

## Kronos Forecast Contract (FORE-01)

### Page hierarchy

| Region | Required visible data and behavior |
|---|---|
| 对象与边界 | 标题 `Kronos 概率预测`；显示唯一标的、数据截至日、日线 OHLCV、研究用途说明：`预测是不确定性研究记录，不会自动改变论点、策略、计划、监控或市场动作。` 不提供标的自由输入或组合批量。 |
| 请求控制 | 原生 radio group 固定 `5 / 20 / 60 个交易日`；批准 checkpoint select 只显示部署目录项。选中项下方先显示模型/Tokenizer 名称、不可变 revision、摘要短值、最大上下文、设备和安装校验状态，再允许 `生成概率预测`。 |
| 任务状态 | 当前运行显示人类任务标签、请求 horizon、checkpoint、输入 as-of 和阶段：`正在验证批准检查点 / 正在冻结受治理日线 / 正在生成采样路径 / 正在计算 P10/P50/P90 / 正在保存不可变记录 / 已完成`。不展示 raw token、终端日志或自动滚动流。 |
| 结果摘要 | 首屏先显示状态、as-of、horizon、输入覆盖、样本数和 validation warnings；随后固定三列/三行 P10、P50、P90 的终点 close、相对 as-of close 的变化和目标交易日。不得以单点“目标价”命名或把 P50 写成确定预测。 |
| 概率图 | ECharts 主图显示历史 close、未来 P10–P90 半透明 band、P50 实线和 actual（成熟后）；图例为完整文字。band 不隐藏 sampled paths。图下固定提供 `查看采样路径` 控制和等价 quantile 数据表。 |
| 采样路径 | artifact 保存的全部路径数量可见；UI 最多同时绘制 12 条，由 checkbox list 选择。每条路径可打开/选择并查看 path 编号、seed 派生标签、各交易日 OHLCV 表和 validation warning。不得只在 hover tooltip 中提供值。 |
| Checkpoint 谱系 | `查看检查点与输入谱系` details 显示 Kronos source revision、model/tokenizer repo identity、immutable revision、integrity digest、pairing、运行配置（lookback、seed、T、top_k、top_p、sample_count）、受治理 input fingerprint、日历/session 范围和 artifact descriptor；不显示本地路径。 |
| 不可变历史 | 倒序表显示预测标签、创建时间、as-of、horizon、状态、checkpoint、P50 终点、样本数、输入 fingerprint 短值、校准状态和详情。切换历史记录只读，不覆盖当前结果；相同输入重试仍创建新任务/记录。 |
| 后续实际与校准 | 每个已成熟 horizon 追加 actual session/value、close MAE、P10–P90 interval coverage、P10/P50/P90 pinball loss、样本数和 coverage period。未成熟显示目标交易日；缺 actual 显示 `暂不可评估：缺少受治理实际值`，绝不填 0。 |

### Forecast interaction sequence

1. 进入 tab 后并行读取 capability、批准 catalog 和当前 instrument 历史；三者局部失败，不清空其他成功数据。
2. 用户选择 5/20/60 horizon 和一个 `verified` checkpoint；前端只发送 instrument context、horizon 和 catalog ID，所有输入范围、fingerprint、revision、digest、quantile 和路径由服务端解析。
3. checkpoint 缺失、model/tokenizer 错配、摘要失败、未来交易日不足或日线覆盖不足时，主动作禁用并在其上方显示完整原因；不能提供远程下载、`latest` 或绕过校验入口。
4. 点击 `生成概率预测` 后禁用重复启动并显示受控阶段；重新进入/断线后按任务引用恢复。SSE 断开保留最后阶段并显示 `进度连接已中断，正在按记录状态重新连接`，不能把它误写为推理失败。
5. 成功后先渲染文字摘要和 quantile 表，再渐进装配图；图加载失败仍能通过表格和路径明细完成检查。失败/超时/OOM/shape 无效只生成 terminal job，不出现伪预测图或空 P10/P50/P90。
6. 选择历史记录时 URL/对象上下文不变；`基于相同配置创建新预测` 只预填 horizon/catalog，不复用旧输入 fingerprint 或覆盖旧结果。
7. actual 成熟或校准追加后，仅失效当前 forecast record/calibration key；图上 actual 与表格同步追加，原 quantile/path 不变。

### Chart and path visual contract

- P50 使用 `accent` 实线（2px）；P10/P90 使用 secondary 1px 虚线并围成 `accent` 12% opacity band。历史/实际 close 使用 foreground 1.5px；采样路径默认使用 muted/secondary 30–55% opacity 的 1px 线，选中路径提升为 foreground 1.5px。
- 不为 32 条路径分配彩虹色，不用 bull/bear 表示模型“好/坏”。bull/bear 只可用于表格中相对实际 close 的市场涨跌数值，并配 `上涨/下跌` 文字。
- 图表首屏固定高度：桌面 360px、平板 320px、小屏 280px；图例可换行。tooltip 只辅助，键盘用户可通过 quantile/path 表获得同等日期和值。
- P10/P50/P90 必须在同一视觉组内，排序始终为 P10 → P50 → P90；quantile crossing 或 OHLC 关系 warning 置于图前，不静默 clamp、重排或隐藏路径。

### Forecast states

| State | Contract |
|---|---|
| loading | capability/catalog/history/record/图表分别局部 skeleton；任务使用受控阶段文字并保留历史。禁止空白 canvas 和全页 spinner。 |
| empty | 无预测时显示 `尚无此标的的概率预测`，解释选择 horizon 与批准 checkpoint 后生成不可变记录；没有 approved catalog 属 unavailable，不是 empty。 |
| unavailable | `此部署未启用 Kronos 预测，或没有通过完整性校验的批准检查点。现有个股分析、投资论点和 v1 工作流仍可使用。请联系部署维护者预装并批准固定检查点。` 不提供联网下载或伪 fallback。 |
| stale | 若 governed 日线已晚于 forecast as-of，显示 `已有更新行情；此预测仍保留其原始数据截至日。`；提供新建预测，不重算/改写旧记录。 |
| partial | 图表失败但表格可用、部分 calibration 已成熟、某 path 有 validation warning、或 actual 缺失时，保留可审阅部分并列明缺项；不得把 partial 说成完整完成。 |
| error | catalog、受治理输入、worker/resource、输出结构、artifact integrity、网络六类错误分别使用 Copywriting Contract 中的精确安全原因、保存范围和不同恢复动作；checkpoint integrity 失败为不可用/终态安全错误，不能普通重试绕过。 |
| pending confirmation | Forecast 本身不需要人工采纳确认；开始运行前以审阅摘要明确对象/horizon/checkpoint。任何“用于论点/策略”动作均不在本期 UI 中，故无隐式采纳状态。 |
| terminal | completed、validation_failed、timeout、resource_terminated、checkpoint_mismatch、artifact_failed 均为只读任务记录；只有 completed 关联 forecast record。失败按错误类型完成恢复后创建新任务，不复用或覆写 terminal 任务。 |
| long content | digest、revision、fingerprint、artifact 元数据可复制并安全换行；路径/quantile/calibration 表横向滚动；完整 path 数据分页/虚拟化读取，不一次渲染全部 32×60×字段单元。 |

---

## Cross-Module Interaction and State Rules

| Control / surface | Default/focus behavior | Loading/error/stale behavior |
|---|---|---|
| Module capability | panel 标题旁显示完整 `可用/不可用`；图标 `aria-hidden`，原因在正文。 | capability 查询失败显示 `暂时无法确认模块状态` 和局部重试；不得推断为 available。 |
| Primary actions | 每个局部流程最多一个 accent 主动作；2px accent focus ring + 2px offset；disabled 邻近显示原因。 | pending 保留按钮宽度并改为阶段动词；失败保留用户输入/选择。 |
| Immutable record selector | 选择只改变当前详情；不改变历史数据或对象上下文。 | keepPreviousData 保留上次成功记录，顶部说明刷新失败/上次更新时间。 |
| Tables/timelines | 默认 newest first；列含状态、范围/版本、时间、来源/证据和详情入口。 | 单行/单记录失败不清空全表；分页边界和总数由服务端提供。 |
| Confirmation dialog | 只用于不可变导入、候选保留、论点版本创建和确认/驳回失效；明确动作名与后果。 | conflict 保留理由，重新读取当前对象；Escape/关闭回到 trigger。 |
| SSE task | 只显示服务端 allowlist 阶段；当前工作区其余内容保持稳定。 | 断线是连接状态，不是任务失败；重连后从持久记录恢复，不重复启动。 |

### No-authority crossover

- Shadow candidate UI 不出现 `启用策略`、`同步持仓`、`添加监控`、`生成交易计划` 或 broker 操作。
- Thesis pending UI 不出现自动确认；Forecast result 不出现 `应用到论点`、`应用到策略`、`设为目标价` 或 `据此交易`。
- 模块间可以通过普通证据链接打开只读记录，但不得由浏览器把 Forecast 数值直接写成 thesis anchor/condition，也不得把 Shadow candidate 直接写成已安装策略。

### Motion

- 颜色、透明度、focus 和 details disclosure 使用 150–200ms `ease-smooth`；任务阶段文字切换可用即时更新或轻微 crossfade。
- 禁止路径绘制动画、量化 band 呼吸/脉冲、批次/版本/校准行自动重排动画、数字滚动、庆祝效果、自动滚动和 raw SSE 打字效果。
- `prefers-reduced-motion: reduce` 下所有非必要过渡即时完成；spinner 停止旋转并以静态图标 + 阶段文字表达，图表无入场动画。

---

## Spacing Scale

Declared values（全部为 4 的倍数）：

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | 图标/文字、quantile 标记、表格辅助元数据 |
| sm | 8px | 紧凑字段、状态组、条件/路径选择项、表格 cell |
| md | 16px | 默认组件间距、标准 panel 内边距、小屏 section 内边距 |
| lg | 24px | 导入步骤、版本/结果 section、桌面 panel 内边距 |
| xl | 32px | 模块内主要阶段分隔 |
| 2xl | 48px | Backtest/Analysis 主要内容块分隔 |
| 3xl | 64px | 页面级分隔；只用于既有壳节奏，不作为装饰留白 |

**Exceptions:** 密集证据、路径、条件、校准表使用 8px 垂直 / 8–12px 水平 cell padding。`<768px` 时 button、tab、file trigger、select、radio/checkbox label、`summary`、分页、路径选择和图标操作至少 44×44px；相邻触区至少 8px。图表本身不计为唯一交互目标。

---

## Typography

Phase 05 的完整规范字号严格为以下四个尺寸、两个字重；`Workspace module heading` 映射到既有 16px/600 `Title`，不创建额外字号层级：

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| PageHeader | 24px | 600 | 1.25 |
| Title / Workspace module heading / Section / record heading | 16px | 600 | 1.4 |
| Body / evidence / form | 14px | 400 | 1.6 |
| Metadata / table label / numeric | 12px | 400 | 1.5 |

Phase 05 不新增任何全局字体 token；实现只复用既有字体族并在本期表面映射上述角色。`600` 只用于 PageHeader、Title、当前 tab、关键状态名和主动作；其余为 `400`。真正需要逐位比较的数值、日期、代码、版本、digest 和 fingerprint 使用既有 mono + tabular numerals；普通说明和状态不用 mono。数字列右对齐，单位与数值不可在行尾拆分。连续判断/理由/假设限制 65–75ch；长 ID 使用 `overflow-wrap:anywhere` 与复制按钮，不以省略号隐藏唯一值。

---

## Color

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `base`: dark `#0A0A0B`; light `#FAFAFA` | 既有应用背景、Backtest/Analysis 工作区底层 |
| Secondary (30%) | `surface`: dark `#18181B`; light `#FFFFFF`; `elevated`: dark `#212126`; light `#F4F4F5` | module section、工具带、表头、选中记录、dialog、quantile/path 控制 |
| Accent (10%) | `accent` `#3B82F6` | 每个局部流程的单一主动作、当前 tab/记录、focus ring、证据链接、Forecast P50 与 P10–P90 band |
| Warning | `warning` `#F79009` | stale、partial、待确认、证据不足、validation warning、未成熟 calibration；必须配文字/图标 |
| Destructive | `danger` `#F04438` | 解析/任务终态失败、checkpoint integrity 拒绝、确认论点失效及真正破坏性确认；必须配文字/图标 |
| Market direction | `bull` `#F04438`; `bear` `#12B76A` | 只用于实际/预测数值相对基准的上涨/下跌，并有完整文字；不得表示候选通过、论点有效、模型质量或运行成功 |

**Accent reserved for:** `确认不可变导入`、`创建新证据集`、`开始候选蒸馏`、具备资格后的 `保留为 Shadow 研究候选`、`创建不可变论点版本`、`生成概率预测`、当前 tab/选中记录、可见 keyboard focus、明确证据链接、P50 和 uncertainty band。不得装饰所有卡、所有可点击行、成功状态或全部 sampled paths。

正文/标签与背景对比至少 4.5:1；大文本和 focus indicator 至少 3:1。muted 不承载关键原因、quantile 值、pending 状态或 checkpoint 校验结果。暗色与亮色均使用文字 + 图标/线型/形状冗余。

---

## Responsive Behavior

| Viewport | Required layout behavior |
|---|---|
| `>=1280px` | 保持现有壳和内容宽度。Shadow 映射摘要/预览、Thesis 当前版本/条件、Forecast 图/右侧摘要可双列，但每列至少 360px；历史、规则、路径、校准保持语义表格。 |
| `768–1279px` | 单列优先；对象/官方状态/unavailable/warning 在操作前。IS/OOS 可两列（每列至少 320px）；Forecast 图在摘要与 warning 后全宽；details 不占固定侧栏。 |
| `<768px` | 全部单列；PageHeader 和既有对象上下文先换行；tablist 横向滚动；主动作全宽或自然换行且 44px；mapping、condition、history、path、calibration 表横向滚动，滚动提示可见；dialog 不超出 viewport。 |
| `375px` verification | 文件名/标的/版本/digest 不撑破容器；P10/P50/P90 按三行显示；图 280px 高；horizon radio 可三列但每项至少 44px，否则纵向堆叠；确认按钮不与取消/驳回重叠。 |
| Any table | 保留状态、对象/版本、范围、时间、证据/原因和详情列，`overflow-x-auto`，前置文字 `左右滚动查看完整记录`；不得在小屏改成缺失谱系的简化卡片。 |

不采用流式字号。长中文、英文文件名、规则、assumption、revision、digest、fingerprint 和安全诊断使用自然换行/`overflow-wrap:anywhere`。Popover/dialog 通过既有 fixed/portal 脱离 overflow 容器；tooltip 不是唯一内容载体。

---

## Accessibility Contract

- 目标 WCAG 2.2 AA。使用 `main/section/article/aside`、顺序 headings、原生 `button/input/select/textarea/fieldset/legend/table/details/summary`；所有 field 有可见 label、错误关联 `aria-describedby`，必填/单位/格式不只靠 placeholder。
- Analysis tabs 复用真实 `tablist/tab/tabpanel` 与 Left/Right 键；Backtest 原有模式键盘语义不变。新增 module section 不截获全局快捷键；Escape 只关闭当前 dialog/popover，关闭后焦点回 trigger。
- mapping、IS/OOS、条件、检查、quantile、path、checkpoint、历史和 calibration 表有 `<caption>`、`thead`、scoped `<th>`；横滚容器可键盘聚焦并由说明关联。
- file input 通过文字按钮触发并保持程序化 label；选中文件后播报文件名/大小，解析错误聚焦摘要并提供到首个错误字段/行的链接。文件拖放如实现，只是额外方式，键盘选择必须完整。
- `radio` horizon、path checkbox、condition cadence 以 `fieldset/legend` 分组；禁用项通过邻近文本解释，不能只用 `disabled`/tooltip。
- 所有可操作控件有 2px accent focus ring + 2px offset。DOM/tab 顺序与视觉/任务顺序一致；图标复述文字时 `aria-hidden`，唯一图标操作须 `aria-label`、可见 tooltip 和小屏 44px 触区。
- `role=status` / `aria-live=polite` 用于 capability 变更、导入/任务阶段、版本创建、保留成功、calibration 追加；同一阶段只播报一次。`role=alert` 用于字段提交错误、不可恢复 terminal、integrity mismatch、确认冲突；不得播报本地路径、原始堆栈或内部策略。
- pending thesis 不是自动弹窗；panel 顶部 warning 可由 heading 导航到达。确认/驳回 dialog 具有 `role=dialog`、`aria-modal`、标题/说明、焦点陷阱、初始焦点、Escape 和焦点返回。危险确认初始焦点不放在最终确认按钮。
- Forecast ECharts 提供可读 `aria-label`，并始终配 quantile 表、selected path 表和 calibration 表。hover tooltip、canvas、线色或线宽不是唯一证据；P10/P50/P90、日期、单位、sample count 和 warning 可在无图环境完整读取。
- 状态不依赖颜色：`可用/不可用`、`样本内/样本外通过/未通过`、`待确认/已确认/已驳回`、`命中/未命中/证据不足/检查错误`、`completed/timeout/integrity failure` 均有完整中文文字与图标/色彩冗余。
- 尊重 `prefers-reduced-motion`；无闪烁、自动滚动、路径绘制动画、颜色脉冲或 raw SSE。长内容可放大至 200% 不丢操作；375px 不要求二维页面滚动，只有明确数据表可横滚。

---

## Copywriting Contract

| Element | Exact copy |
|---|---|
| Shadow heading | `Shadow 成交证据与策略候选` |
| Shadow boundary | `仅从本地实际成交日志形成研究证据，不连接券商、不同步持仓、不执行交易。` |
| Shadow primary sequence | `选择本地成交日志` → `确认不可变导入` → `创建新证据集` → `开始候选蒸馏` |
| Shadow empty | `尚无 Shadow 成交批次` / `选择本地真实成交日志，完成字段映射后会追加一条不可变导入记录。` |
| Shadow empty — completed batches, no evidence set | 标题 `尚未创建 Shadow 证据集`；说明 `已有完成的成交批次，但尚未冻结用于候选蒸馏的证据。请选择要纳入的已完成批次和排除项；创建后证据集不可修改。`；操作 `创建新证据集`。 |
| Shadow empty — evidence set, no candidate | 标题 `尚无 Shadow 策略候选`；说明 `当前证据集已冻结，但尚未生成可解释候选。开始蒸馏后，候选将记录规则、参数、来源、限制和独立样本内/样本外评估。`；操作 `开始候选蒸馏`。 |
| Shadow unavailable | `此部署未启用 Shadow 蒸馏模块。现有回测、研究库和 v1 工作流仍可使用。请联系部署维护者启用 Shadow 可选依赖。` |
| Shadow stale | `存在较新成交批次；当前候选仍基于已冻结证据。` |
| Shadow partial | `导入包含需要处理的诊断：{validCount} 行有效，{invalidCount} 行未纳入。查看诊断` |
| Shadow import error | `无法解析成交日志：{safeReason}。请检查格式、字段映射和源时区后重试。` |
| Shadow network/load failure | 标题 `无法加载 Shadow 记录`；说明 `无法加载 Shadow 记录：{safeReason}。`；保留状态 `此前显示的批次不会被清空，当前批次、证据集或候选选择保持不变。`；终态记录 `本次加载失败不创建运行记录，也不改变任何既有只读终态记录。`；操作 `重新加载 Shadow 记录`。 |
| Shadow distillation failure | 标题 `Shadow 候选蒸馏失败`；说明 `Shadow 候选蒸馏失败：{safeReason}。`；保留状态 `本次未创建候选，冻结证据集及其 fingerprint 保持不变。`；终态记录 `失败运行作为只读终态保留；重试必须基于相同冻结证据集创建新运行，不复用或覆盖失败运行。`；操作 `基于相同证据集创建新蒸馏运行`。 |
| Shadow IS/OOS evaluation failure | 标题 `Shadow 样本内/样本外评估失败`；说明 `Shadow 样本内/样本外评估失败：{safeReason}。`；保留状态 `本次不产生保留资格；候选和既有评估记录保持不变。`；终态记录 `失败运行作为只读终态保留；重试必须创建新评估运行，不复用或覆盖失败运行。`；操作 `创建新评估运行`。 |
| Shadow retain CTA | `保留为 Shadow 研究候选` |
| Shadow retain constraint | `必须先完成相互独立的样本内与样本外评估，且两者均通过。` |
| Shadow retain confirmation | `确认保留候选 {candidateLabel}？系统将记录冻结证据集和样本内/样本外评估；不会注册或启用策略，也不会创建监控、计划或市场动作。` |
| Thesis heading | `投资论点` |
| Thesis boundary | `自动检查只能提出待确认结论，不能替你改变论点状态。` |
| Thesis empty | `尚无投资论点` / `为当前标的记录核心判断、带假设的估值区间和可定期检查的失效条件。` |
| Thesis first CTA | `创建第一版投资论点` |
| Thesis version CTA | `创建不可变论点版本` |
| Thesis unavailable | `此部署未启用投资论点模块。当前分析报告、证据和信号历史仍可使用。请联系部署维护者启用投资论点可选依赖并恢复条件检查调度。` |
| Thesis read failure | 标题 `无法读取投资论点`；说明 `无法读取投资论点：{safeReason}。已显示的版本、待确认结论和检查历史将保留，当前官方状态不会改变。`；操作 `重新加载投资论点`。 |
| Thesis evidence-check failure | 标题 `证据检查失败`；说明 `证据检查失败：{safeReason}。本次失败将作为检查错误追加；既有检查证据、待确认结论和当前官方状态均保持不变。`；操作 `重新检查此条件`。 |
| Thesis immutable-version creation failure | 标题 `无法创建不可变论点版本`；说明 `无法创建不可变论点版本：{safeReason}。`；保留状态 `已填写的表单和审阅内容保留；既有版本与当前官方状态保持不变。`；终态记录 `本次未创建新版本；失败提交不作为论点版本写入，也不改写任何既有只读版本。`；操作 `返回并重试创建版本`。 |
| Thesis confirm/reject transport uncertainty | 标题 `无法确认论点操作结果`；说明 `确认或驳回请求的传输状态不确定：{safeReason}。`；保留状态 `已填写的理由保留。`；终态记录 `不得假定服务端未处理本次请求，也不得在本地创建、回滚或改写确认/驳回记录；重试前必须重新读取当前论点及待确认结论，并以服务端当前记录为准。`；操作 `重新加载当前论点`。 |
| Thesis history marker | `历史版本，不再执行定期检查` |
| Thesis due stale | `检查已逾期，等待调度恢复。` |
| Pending heading | `待确认失效结论` |
| Pending authority | `当前官方状态未改变，等待你的确认。` |
| Pending actions | `确认论点失效` / `驳回待确认结论` |
| Pending conflict | `结论未记录：状态已变化，请重新查看当前论点。` |
| Thesis destructive confirmation | `确认将 {instrument} 的论点版本 {version} 记录为已失效？命中条件与证据会永久保留；此操作不会执行交易或修改其他研究对象。` |
| Forecast heading | `Kronos 概率预测` |
| Forecast boundary | `预测是不确定性研究记录，不会自动改变论点、策略、计划、监控或市场动作。` |
| Forecast primary CTA | `生成概率预测` |
| Forecast empty | `尚无此标的的概率预测` / `选择 5、20 或 60 个交易日与一个已批准检查点，生成包含 P10/P50/P90 和采样路径的不可变记录。` |
| Forecast unavailable | `此部署未启用 Kronos 预测，或没有通过完整性校验的批准检查点。现有个股分析、投资论点和 v1 工作流仍可使用。请联系部署维护者预装并批准固定检查点。` |
| Forecast stale | `已有更新行情；此预测仍保留其原始数据截至日。` |
| Forecast reconnect | `进度连接已中断，正在按记录状态重新连接。` |
| Forecast calibration pending | `尚未到达目标交易日，校准将在受治理实际值可用后追加。` |
| Forecast unevaluable | `暂不可评估：缺少受治理实际值。` |
| Forecast terminal error | 标题 `预测未完成`；说明 `预测未完成：{safeReason}。未创建概率预测记录；此任务已作为只读终态保留。请按错误类型完成下方恢复操作后创建新任务。`；操作 `查看恢复方式`。 |
| Forecast catalog error | 标题 `无法读取批准检查点目录`；说明 `无法读取批准检查点目录：{safeReason}。尚未开始预测，当前标的和 horizon 选择已保留。`；操作 `重新加载批准检查点目录`；若仍失败，联系部署维护者检查目录配置。 |
| Forecast governed-input error | 标题 `受治理日线输入不可用`；说明 `受治理日线输入不可用：{safeReason}。未创建概率预测记录，当前标的、horizon 和检查点选择已保留。`；操作 `重新检查受治理输入`；覆盖或交易日历恢复后创建新任务。 |
| Forecast worker/resource error | 标题 `预测工作进程未完成`；说明 `预测工作进程未完成：{safeReason}。未创建概率预测记录；当前任务已作为只读终态保留。`；操作 `基于相同配置创建新预测`；资源持续不足时联系部署维护者恢复 worker。 |
| Forecast output-shape error | 标题 `预测输出结构无效`；说明 `预测输出结构无效：{safeReason}。未创建概率预测记录，也未绘制 P10/P50/P90；当前任务已作为只读终态保留。`；操作 `复制输出诊断`，交由部署维护者检查模型与运行配置；修复后创建新任务。 |
| Forecast artifact-integrity error | 标题 `预测工件完整性校验失败`；说明 `预测工件完整性校验失败：{safeReason}。未创建概率预测记录，失败工件不会作为结果开放；当前任务已作为只读终态保留。`；操作 `复制完整性诊断`，联系部署维护者修复存储或检查点；不得以普通重试绕过校验。 |
| Forecast network error | 标题 `预测状态连接中断`；说明 `预测状态连接中断：{safeReason}。已显示的历史和最后已知任务阶段将保留；连接中断不代表推理失败，也不会重复启动任务。`；操作 `重新连接并刷新任务状态`。 |
| Evidence/details controls | `查看导入诊断` / `查看规则与限制` / `查看样本内与样本外证据` / `查看完整版本` / `查看检查证据` / `查看采样路径` / `查看检查点与输入谱系` / `查看校准证据` |
| Generic stale refresh | `刷新失败，正在显示 {lastUpdatedAt} 的上次结果。重新加载` |

主操作不得使用泛化的 `提交`、`保存`、`确定`；取消按钮可使用 `返回审阅` 或 `暂不处理`。不得把 Forecast 写成“目标价”“预测会涨/跌”“AI 建议”，不得把 Shadow 写成“复制交易高手”，不得把 condition match 写成“论点已失效”。可见 ID 使用人类标签 + 可复制短 ID；不暴露本地路径、账户秘密、raw exception、worker command、环境变量、远程 latest 或内部 allowlist。

---

## UI Considerations

Applicable state considerations resolved: **40 covered, 0 backstop, 0 unresolved**。

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| empty | Shadow 批次 | ✅ covered | 使用规定空态和文件选择下一步；不提供手工成交或虚构批次。 |
| loading | Shadow capability/解析 | ✅ covered | capability、映射解析和历史局部 loading；稳定 skeleton 且不清空历史。 |
| error | Shadow 导入/加载/蒸馏/IS-OOS 评估 | ✅ covered | 精确引用 Copywriting Contract 的 `Shadow import error`、`Shadow network/load failure`、`Shadow distillation failure`、`Shadow IS/OOS evaluation failure`；分别规定安全原因、保留状态、终态记录与恢复操作。 |
| partial | Shadow 批次 | ✅ covered | 显示有效/无效/重复/partial-fill 数量与限制；异常行不静默纳入。 |
| zero-one-many | Shadow 批次/候选 | ✅ covered | 零态教学；一条完整谱系；多条倒序表、筛选/分页且全部不可变。 |
| overflow | 映射/批次/规则表 | ✅ covered | 保留状态、来源、时间和证据列，横向滚动并显示说明。 |
| long-text | 文件名/规则/限制/fingerprint | ✅ covered | 安全换行、可复制；完整 JSON 放可访问 details，不以省略号隐藏唯一值。 |
| populated | Shadow 候选 | ✅ covered | 展示规则、特征、参数、来源、限制、seed/class balance 与 IS/OOS，不只展示总分。 |
| unavailable | Shadow 模块 | ✅ covered | 独立 typed unavailable；既有 Backtest 和其他模块不受影响。 |
| stale | Shadow 证据/候选 | ✅ covered | 新批次只标记 stale 并提供新证据集；不改旧记录。 |
| pending-confirmation | Shadow 导入/保留 | ✅ covered | 显式确认复述不可变与不激活后果。 |
| terminal | Shadow 运行 | ✅ covered | `Shadow distillation failure` 与 `Shadow IS/OOS evaluation failure` 明定失败运行只读保留且重试新建运行；`Shadow network/load failure` 明定不创建运行记录。 |
| empty | Thesis | ✅ covered | 规定第一版空态，要求判断、估值区间/假设和可检查条件。 |
| loading | Thesis 版本/pending/checks | ✅ covered | 局部 skeleton、keep previous data，不闪空。 |
| error | Thesis 读取/创建/确认 | ✅ covered | 精确引用 `Thesis read failure`、`Thesis evidence-check failure`、`Thesis immutable-version creation failure`、`Thesis confirm/reject transport uncertainty`；版本/官方状态、表单/理由和终态记录恢复规则分别明确。 |
| partial | Thesis anchor/check | ✅ covered | 缺证据为 `证据不足`，不等于未命中且不生成 pending。 |
| zero-one-many | Thesis 版本/条件/checks | ✅ covered | 零态；单版本完整；多版本倒序、按条件筛选和分页。 |
| overflow | 条件/检查/版本表 | ✅ covered | 横滚时保留条件、cadence、时间、结果、证据和版本。 |
| long-text | 判断/理由/假设/证据 | ✅ covered | 65–75ch、自然换行、fingerprint 可复制。 |
| unavailable | Thesis 模块 | ✅ covered | tab 可进入并解释，Analysis/Forecast 保持可用。 |
| stale | Thesis 旧版本/逾期检查 | ✅ covered | 旧版本和 due overdue 明确标记，不冒充当前/已检查。 |
| pending-confirmation | 失效结论 | ✅ covered | warning 置顶、官方状态未变、证据完整、确认/驳回分离。 |
| terminal | 已失效/被取代版本 | ✅ covered | 只读显示事件人/时间/理由；只能创建新版本，不能重开旧版。 |
| empty | Forecast 历史 | ✅ covered | 规定空态并指导 horizon + approved checkpoint；无 catalog 不冒充 empty。 |
| loading | Forecast catalog/task/record/chart | ✅ covered | 局部 skeleton 和阶段文字；文字/表格先于图，历史不清空。 |
| error | Forecast catalog/input/worker/artifact | ✅ covered | 每层安全原因与恢复路径；失败无伪 quantile/图。 |
| partial | Forecast 图/path/calibration | ✅ covered | 图失败保留表、部分成熟保留已知值、缺 actual 显式不可评估。 |
| zero-one-many | Forecast records/paths | ✅ covered | 零态；一条完整；多记录倒序分页；最多绘 12 条但全部路径可检查。 |
| overflow | Forecast history/path/calibration | ✅ covered | 横滚表与分页/虚拟化，关键日期、单位、状态、checkpoint 不丢失。 |
| long-text | revision/digest/fingerprint | ✅ covered | 可复制、anywhere wrap、details，不暴露本地路径。 |
| populated | Forecast result | ✅ covered | P10/P50/P90、采样路径、input/checkpoint provenance、warnings、history 和校准完整。 |
| unavailable | Forecast 模块/catalog | ✅ covered | 缺 extra/checkpoint typed unavailable，只影响 Forecast。 |
| stale | Forecast as-of | ✅ covered | 新行情只提示创建新预测；旧 quantile/path 保持不变。 |
| pending-confirmation | Forecast authority | ✅ covered | 明确本模块无采纳动作；运行前审阅输入，结果不写入其他对象。 |
| terminal | Forecast job | ✅ covered | 多种 terminal 状态只读；只有 completed 关联 forecast record。 |
| mobile | 三个模块 | ✅ covered | 单列、44px 触区、无裁剪 tabs、横滚语义表、280px 图和安全 dialog 已定义。 |
| accessibility | tabs/forms/tables/dialogs/charts | ✅ covered | 键盘、焦点、live region、文字冗余、表格等价、WCAG AA 和 reduced motion 已定义。 |
| responsive | 1440/1024/375 | ✅ covered | 三个明确 viewport 布局和长内容行为已定义。 |
| motion | task/chart/history | ✅ covered | 150–200ms 状态过渡；无路径动画/脉冲/自动滚动；reduce 下即时。 |
| independence | module availability | ✅ covered | 三 capability 分离；任一 unavailable/error 不遮挡 v1 或另两模块。 |

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|---|---|---|
| shadcn official | None | Not applicable — `components.json` 不存在；沿用既有手工系统，不初始化 shadcn（2026-07-15）。 |
| Third-party registry | None | 未声明或允许第三方 UI block；无需 registry vetting。 |

---

## Browser-Verifiable Scenarios

1. **独立能力与 v1 不回归：** 分别模拟全部可用、仅 Shadow unavailable、仅 Thesis unavailable、仅 Forecast unavailable、三者 unavailable。确认每个状态只出现在自己的 section/tab panel；Backtest 核心回测、现有分析报告/证据/信号历史和 completed v1 导航始终可操作；页面无新顶级导航、第二侧栏或 optional 总览 shell。
2. **SHDW-01 不可变导入：** 上传有效 CSV/XLSX、同内容再次导入、带修正关系的再导入、字段缺失、时区错误、重复组和 partial fill。确认映射预览/单位可检查，每次确认产生新 batch，旧行不变，partial fills 不被合并，失败行不进入证据集，历史显示文件/映射/时间/摘要/谱系且无本地路径。
3. **SHDW-01 explainability 与资格：** 从冻结证据集生成候选，确认 if/then 规则、features/parameters/source/limitations、seed/class balance、IS/OOS 独立窗口和指标完整可见。只有两段均通过才可保留；全样本优秀但 OOS 失败不能保留。确认保留后只出现研究候选事件，无策略注册、监控、计划、持仓或执行入口。
4. **Shadow stale/terminal/long content：** 候选产生后再导入新批次，确认旧候选标记 stale 但内容不变。制造超时/资源失败并重试，确认两条 terminal 记录并存。以超长文件名、规则、diagnostic、fingerprint 在 375px 验证换行、复制和表横滚。
5. **THES-01 版本与估值锚：** 在已选标的创建第一版，验证 low/high/currency/as-of/assumptions 约束和每 condition 独立 cadence。基于 v1 创建 v2，确认 v1 anchor/conditions/checks 仍可读且标记历史版本；没有单一 target 或自由文本 condition 冒充 canonical 结构。
6. **THES-01 evidence checks：** 分别加载 matched、not_matched、insufficient_evidence、error 检查。确认只有 matched 创建待确认结论；证据不足不显示 false/zero；每条记录显示 due/checked time、observed value、证据、version 和 cadence，旧检查不被下一次覆盖。
7. **THES-01 人工权威：** pending 出现时确认官方状态仍未改变且没有自动 dialog。键盘打开确认 dialog，检查焦点陷阱、Escape/返回焦点、10 字符理由、危险文案；确认后进入 terminal 失效事件但不交易。另一路驳回后状态不变、检查保留；模拟并发冲突，确认规定文案和对象局部刷新。
8. **FORE-01 approved checkpoint gate：** 在单一 stock 对象中验证 horizon 只能 5/20/60；catalog 显示 model/tokenizer identity、revision、digest 和校验状态。模拟缺 checkpoint、错配、digest mismatch、未来交易日不足和输入覆盖不足，确认 CTA 禁用、typed unavailable/安全原因明确、无远程下载/latest/绕过入口，其他 Analysis tabs 可用。
9. **FORE-01 概率结果：** 完成一次 20 日预测，确认 P10/P50/P90 终点摘要、逐日 quantile 表、P10–P90 band、P50、sample count、最多 12 条可选绘制路径、全部路径明细、checkpoint/input provenance 同时可达。关闭 canvas 或制造图加载失败，仍能通过表格读取日期、值、单位和 warnings。
10. **Forecast immutable/stale/terminal：** 新行情到来后确认旧预测显示原 as-of stale 提示且不重算。用同配置重试产生新任务/record，旧路径/quantile 不变。模拟 SSE 断线恢复、timeout、OOM、shape failure 和 artifact failure；只有 completed 记录显示 quantile/path，所有 terminal job 可审阅且不出现伪结果。
11. **Later calibration：** 依次模拟 5/20/60 horizon 未成熟、成熟、部分成熟、missing actual。确认 actual、MAE、interval coverage、三项 pinball loss、样本数和 coverage period 追加到原 record；未成熟/不可评估文字明确，缺值不显示 0，原预测与 checkpoint 谱系不变。
12. **Responsive、keyboard、contrast 与 reduced motion：** 在 1440px、1024px、375px 使用键盘遍历 Backtest mode、Shadow file/mapping/history、Analysis tabs、Thesis version/condition/pending dialog、Forecast horizon/path/details/table。确认 44px 小屏触区、焦点顺序、横滚说明、长文本、dialog 焦点返回、chart 等价表、明暗主题 WCAG 2.2 AA、状态文字冗余；开启 reduced motion 后无路径动画、spinner 旋转、脉冲或自动滚动。
13. **跨模块无权威副作用：** 在浏览器完成 Shadow 保留、Thesis 确认/驳回和 Forecast 完成/校准。确认 UI 和请求中不存在把 Forecast 写入 thesis、把 Shadow 写入已安装策略、创建监控/计划、同步持仓或市场执行的动作；一个模块 mutation 只刷新当前对象的对应 Query keys。

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: 三模块操作、边界、空/不可用/stale/partial/error/pending/terminal 文案与确认后果已精确定义
- [ ] Dimension 2 Visuals: 既有 Backtest/Stock Analysis 放置、研究账本层级、Forecast chart/table/path、响应式与无平行壳已定义
- [ ] Dimension 3 Color: 既有 60/30/10、受限 accent、warning/danger、Forecast 线型和市场色职责已定义
- [ ] Dimension 4 Typography: Phase 05 完整规范严格为 PageHeader 24px/600、Title 16px/600、Body 14px/400、Metadata/Numeric 12px/400；Workspace module heading 映射 Title，不新增全局字体 token；mono/tabular、65–75ch 和长标识规则已定义
- [ ] Dimension 5 Spacing: 4px 基数、标准 panel 节奏、表格密度、44px 小屏触区和 1440/1024/375 布局已定义
- [ ] Dimension 6 Registry Safety: shadcn/第三方 registry 均未使用，缺席证据与日期已记录

**Approval:** pending
