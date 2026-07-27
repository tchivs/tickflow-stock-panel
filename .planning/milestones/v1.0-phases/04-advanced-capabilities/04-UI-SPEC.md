---
phase: 04
slug: advanced-capabilities
status: draft
shadcn_initialized: false
preset: none
created: 2026-07-12
---

# Phase 04 — UI Design Contract

> 在既有回测、分析与运营工作区中呈现受控的高级研究能力。每一项结论、运行、拒绝、门禁和人工批准都必须有可定位的谱系与审计路径；本期只形成研究资产，不启用监控、创建交易计划或执行市场动作。

---

## Scope and Source Decisions

| Source | Binding UI decision |
|---|---|
| `REQUIREMENTS.md` ADV-01 | 归因观点显示版本、来源档案、适用范围、发布时间、证据、置信度和冻结表现；材料立场变化与普通修订必须区分，校准必须显示窗口、基准、样本数和覆盖期。 |
| `REQUIREMENTS.md` ADV-02 | 假设须经由冻结实验规格、受限运行和追加式反馈形成可审阅研究记录；每次失败、重试和反馈都可访问且不覆写历史。 |
| `REQUIREMENTS.md` ADV-03 | 策略演化显示父版本、变异、种子、解析配置与独立门禁；晋级只能在所有门禁通过后的明确人工批准下发生，并只生成注册研究策略版本。 |
| `REQUIREMENTS.md` SAFE-01 | 代理任务必须把授权范围、当前状态、受控 SSE 进度、审计摘要和拒绝结果作为一体呈现；越权、撤销、范围不匹配和限流均须在启动前明确拒绝。 |
| `REQUIREMENTS.md` SAFE-02 | 自定义策略先展示机器可读合同与验证结果；只在 AST、导入、超时、内存等检查通过后可提交沙箱运行。失败以约束原因和脱敏诊断显示，绝不伪装成研究结论。 |
| `04-CONTEXT.md` D-01--D-16 | 历史观点、实验规格、运行、反馈、候选和批准均为不可变、追加式证据；缺失行情、基准、样本或授权不是零值或成功的替代物。授权在创建与实际执行前均由服务端校验。 |
| `04-AI-SPEC.md` | 模型只产生非权威、经校验的研究草稿；UI 不展示原始 token、未验证草稿、令牌或策略/策略细节。确定性门禁和人工审批是权威状态来源。 |
| Phase 03 `03-UI-SPEC.md` | 延续现有工作区、证据优先顺序、局部 Query 状态、语义表格/`<details>`、暗色优先 token、移动端横向表格与不创建平行产品壳的约束。 |

### Phase boundary

- **In scope:** 归因观点及版本差异、置信度校准和不可评估结果；实验规格/运行/反馈；演化候选、门禁与人工晋级；受限代理的创建、受控进度和审计；自定义策略合同校验、沙箱运行与脱敏失败记录。
- **Out of scope:** 新顶级导航或独立高级能力仪表盘；实时券商执行、自动启用监控、自动晋级、自动采纳模型草稿、令牌/allowlist 编辑器、原始模型流、未隔离代码终端、删除或覆写历史证据、第三方组件注册表。

---

## Design System

| Property | Value |
|---|---|
| Tool | 现有手工系统：Tailwind CSS 3.4 tokens 和本地 React 组件 |
| Preset | 不适用；`components.json` 不存在，沿用 Phase 03 决定，不初始化 shadcn |
| Component library | 现有 `PageHeader`、`EmptyState`、`Skeleton`、本地对话框、语义表格、原生表单控件、`<details>`；不安装新组件库 |
| Icon library | `lucide-react`；14--16px 图标仅辅助完整文字状态和操作名称，不能单独传达门禁、授权、失败或晋级含义 |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, system sans；`JetBrains Mono`/`IBM Plex Mono` 仅用于数值、时间、版本、指纹、审计/运行标识 |
| Server state | 现有 typed `api.ts`、TanStack Query 和 `QK` factories；每个资源以对象/运行/版本标识隔离缓存，Mutation 成功后只失效受影响资源；禁止新 API 客户端、直接 `fetch` 或客户端推断授权/门禁/审计状态 |
| Existing surfaces | `Backtest` 的策略模式、研究库和实验比较区承载实验、演化、晋级与自定义策略；现有 stock/financial/Portfolio 分析详情承载对象相关的观点；运营审阅入口使用现有 Analysis/全局报告历史宿主的可组合审计抽屉或页面内区域。不得添加第二侧栏、平行路由壳或高级能力总览页。 |

### Existing visual tokens to preserve

严格沿用 `frontend/src/index.css` 与 `tailwind.config.ts`：`base`、`surface`、`elevated`、`border`、`foreground`、`secondary`、`muted`、`accent`、`warning`、`danger`、`bull`、`bear`。默认暗色，亮色由既有 token 反转。使用 1px `border-border`、`rounded-input` 4px、`rounded-btn` 6px、`rounded-card` 8px、`rounded-dialog` 12px。禁止为本期引入渐变、玻璃化、发光、专属紫色或“安全控制台”视觉语言；所有高级能力区域是既有数据工作区的正常 section。

---

## Information Hierarchy and Interaction Contract

### Surface placement

1. **对象相关观点，进入现有分析详情：** 在 stock、财务分析或 Portfolio 的 `分析详情` 内新增 `归因观点` tab/section，保留已选标的/账户、报告历史和证据上下文。没有对象时显示空状态，不能提供自由输入证券范围的快捷启动入口。
2. **实验、演化和自定义策略，进入 Backtest 策略模式：** 保持 `回测工作台` 和现有 `因子 / 策略 / 参数优化` 模式切换。在策略面板的现有研究库和实验比较之后，按 `实验规格与运行`、`演化候选与门禁`、`自定义策略沙箱` 的顺序追加页面内 section；不要新建“高级能力”顶级 tab。
3. **代理任务和安全审计，进入既有操作性审阅区域：** 从受限对象或 Backtest 上下文的明确动作打开当前任务区域；在现有 Analysis/AI 历史宿主中提供 `任务与审计` 可审阅区域，用任务筛选和详情替代独立运营 shell。默认查看当前对象或当前任务，跨任务列表必须显式显示筛选范围。
4. **审计详情始终为第二层，不可缺席：** 每个观点版本、实验规格/运行/反馈、候选、批准、代理任务和沙箱运行都显示“查看证据与审计”文字控制，打开页面内 `<details>` 或既有对话框。概览可压缩，谱系、输入指纹、时间、门禁证据和受限诊断不能只藏在 hover 中。

### Attributed viewpoints and calibration (ADV-01)

| Region | Required visible data and behavior |
|---|---|
| 归因观点首屏 | 固定标题 `归因观点与表现校准`；每个最新版本显示来源档案名称、市场/标的范围、发布时间、结论/方向、置信度、评价窗口、基准与状态。先显示 `立场已变化`、`不可评估` 或样本不足 warning，后显示结论摘要。来源版本不是 AI 推荐或交易指令。 |
| 版本时间线 | 倒序显示版本号、发布时间、修订/更正原因、结论、置信度和 `查看此版本证据`。更正明确为 `更正版本`；不会覆盖原版本。普通修订显示 `内容修订，未构成立场变化`；阈值命中的版本显示 `材料立场变化` 和变化字段（方向、评级/结论、目标范围、持有期或置信度）。 |
| 版本比较 | 选择两个版本后，以语义差异表显示上述结构字段的旧值/新值/变化类型；不使用红绿 diff 单独表达变化。相同版本、跨来源档案或服务端禁止比较的组合禁用并说明原因。 |
| 单一版本结果 | 显示冻结的 `20 / 60 / 120 个交易日`、评估起止日、基准名称、相对收益、命中状态和数据覆盖。每一项都有时间上下文；前端不得根据当前市场价格重算、补全或重解释。 |
| 置信度校准 | 低/中/高三个完整文字 bucket 各显示命中率、相对收益、样本数和覆盖期。样本不足显示 `样本不足，暂不能评价置信度校准。`，保留可用的计数和期间，不显示“可靠/不可靠”结论。 |
| 不可评估 | 缺价格、基准、支持范围或服务端标记的不可评估，显示 `不可评估：{reason}`，并显示相关版本、窗口和缺失项目。禁止显示 `0%`、空收益图、成功色或从汇总统计中静默省略。 |

### Experiment, evolution and promotion (ADV-02, ADV-03)

| Region | Required visible data and behavior |
|---|---|
| 实验规格 | `新建实验规格` 只能针对已选研究资产。表单按 `假设`、`数据范围`、`方法`、`指标`、`成功/失败标准` 顺序排列，所有字段有可见标签和服务端验证。提交成功后显示不可变规格版本、创建时间和数据范围摘要；后续更改应创建新版本，不能原地编辑已提交版本。 |
| 运行概览 | 每次运行一行/卡显示状态、规格版本、受治理数据快照/指纹、策略/因子版本、解析参数、环境、资源限制、开始/结束时间和 `查看运行清单`。排队/运行只显示允许的阶段状态，不显示模型 token 或命令输出。 |
| 运行结果与失败 | 成功运行显示服务端返回的指标、工件数量及 `记录研究反馈`；验证失败、超时、内存/资源限制则显示 `运行未完成：{constraint reason}` 与脱敏诊断、审计时间和 `以新运行重试`。失败不是 supported/refuted 反馈，也不能生成晋级证据。 |
| 研究反馈 | 只能从已完成可审阅运行创建，使用四个完整文字单选项：`支持`、`证伪`、`无结论`、`需要复现`。反馈固定关联运行、指标、工件与说明；提交后显示追加事件，禁用二次提交。历史反馈不提供删除或编辑。 |
| 演化候选 | 每个候选显示父策略版本、受限变异操作、随机种子、解析配置、生成时间、评估状态与 `查看谱系与运行证据`。候选排序仅按用户选定且服务端返回的单一度量，顶部固定提示 `排序不代表可晋级；所有门禁必须独立通过。` |
| 门禁矩阵 | 使用语义表格，固定五行：合同/沙箱安全、来源完整性、样本内与样本外、稳健性、成本与可实现性。每行有完整状态文字 `通过 / 未通过 / 缺少证据 / 评估中`、证据摘要及详情链接。聚合分数、夏普或排名绝不能替代这些行。 |
| 人工晋级 | 只有全部门禁为 `通过` 时才启用 `批准晋级为研究策略`。点击后打开现有确认对话框，复述候选名/版本、五个门禁和不可逆结果，要求填写最少 10 个中文或英文字符的批准理由；确认按钮为 `确认晋级为研究策略`。成功显示已批准人/时间/理由和新注册研究策略版本，并固定提示 `晋级不会启用监控、创建交易计划或执行市场动作。` |

### Scoped agent and sandbox execution (SAFE-01, SAFE-02)

| Region | Required visible data and behavior |
|---|---|
| 启动受限代理 | 主操作为 `启动受限研究任务`，仅在页面已有允许对象且服务端返回可启动状态时启用。启动前可见任务类型、目标市场/标的、服务器授予范围摘要、预估资源/预算（如返回）和“研究支持，不执行市场操作”说明；不显示令牌、allowlist 细节或可编辑授权范围。 |
| 任务进度 | 页面内当前任务卡固定显示任务 ID 的人类标签、目标、状态、最近受控事件时间和阶段序列：`已授权`、`已冻结输入`、`正在生成草稿`、`正在校验门禁`、`等待人工复核`、`已记录` 或 `已拒绝`。SSE 只能更新这些服务端 allowlist 状态；保持现有内容，不以流式文本替换页面。 |
| 启动前拒绝 | 未授权、令牌过期/撤销、范围不允许和限流，都显示 `任务未启动：{safe reason}`、请求时间、目标摘要与 `查看安全审计摘要`。不得创建“运行中”外观、倒计时或 SSE loader；错误中不得泄露 allowlist、令牌或内部策略规则。 |
| 执行前复核拒绝 | 等待任务在执行前复核失败时，状态更新为 `执行前授权复核未通过`，说明 `当前授权或允许范围已变化，任务未执行。`，提供审计详情和“返回对象审阅”。不能自动重试或沿用旧授权。 |
| 自定义策略合同 | `验证并运行受限策略` 前，在 Backtest 的策略上下文显示机器可读合同摘要、允许输入、资源限制和所有验证条目。AST、导入、超时、内存各自以文字状态显示；未通过项使运行按钮禁用，并将焦点引至首个失败项。禁止直接执行 textarea 内容、shell、文件或网络操作。 |
| 沙箱结果 | 成功显示受限运行的结果、资源消耗摘要（如服务端提供）、运行指纹和审计链接。校验拒绝、超时或内存终止使用 `策略未运行` 或 `沙箱已终止`，附脱敏原因；绝不显示完整异常堆栈、文件路径、环境变量、令牌、原始代码回显或“策略无效/被证伪”的研究判断。 |

### Interaction states and feedback

| Control / surface | Default, focus and interaction | Loading, empty, error and partial behavior |
|---|---|---|
| `新建实验规格` | accent 填充按钮；只在明确研究资产上下文可用。逐字段原生校验，焦点为 2px accent ring + 2px offset。提交后锁定版本，不复用同一表单修改历史。 | 提交中为 `正在冻结实验规格…`；失败保留用户输入及字段错误，显示 `无法创建实验规格：{safe reason}`。没有资产时显示规定空状态。 |
| `运行受限实验` / `以新运行重试` | 新运行显式显示其规格版本；重复点击聚焦同一活跃运行，不创建重复任务。 | 运行中显示当前受控阶段和 skeleton；失败保留规格、既有运行和诊断摘要。重试必定创建新运行，且配置改变时提示先新建规格版本。 |
| 研究反馈表单 | 原生 radio group，四种结论完整可见；选择不依赖颜色。提交后状态回写为只读事件。 | 未完成运行禁用并说明；保存失败保留选择和说明。一个运行已有反馈时显示记录，不能覆盖。 |
| 门禁矩阵与晋级 | 门禁详情为可见文字链接或 `<details>`；批准按钮只在全部通过时可用。确认对话框初始焦点在标题，Esc/关闭返回触发按钮，确认后以 `role=status` 宣布。 | 门禁加载使用固定高度 skeleton；任一门禁缺失/失败显示原因且禁用批准。批准冲突、过期或重放时显示 `晋级未记录：状态已变化，请重新查看门禁。` |
| `启动受限研究任务` | 仅当前已授权对象可用，点击后显示单一任务卡并禁用重复启动。状态变化不改变对象上下文。 | 启动请求中为 `正在验证授权范围…`；安全拒绝用 `role=alert`，不连接任务 SSE。普通网络失败提供重新尝试，不把错误解释为授权拒绝。 |
| 任务与审计详情 | 使用 task filter 的原生 `select`、状态 checkbox 和语义表格；展开条目保持当前筛选和滚动位置。 | 局部刷新失败时保留上次成功列表，`role=status` 显示 `刷新任务审计失败，正在显示上次结果。重新加载任务审计`。空任务和被拒绝任务分别显示不同规定文案。 |
| 自定义策略验证/运行 | 合同字段使用原生输入、select、checkbox 与明确帮助文本；验证先于运行。危险动作不以图标按钮替代文字。 | 验证中 `正在检查策略合同与限制…`；任何失败把焦点移至摘要并提供审计详情。沙箱运行状态不清除之前的验证结果与完成运行。 |

状态反馈使用 150--200ms `ease-smooth` 的颜色/透明度变化；不可动画化布局高度、SSE 数据到达、表格行重排或安全 warning。`prefers-reduced-motion: reduce` 下全部即时，加载仍以文字、骨架和受控阶段说明表达。

---

## Spacing Scale

Declared values（全部为 4 的倍数）：

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | 图标与文字、状态标签内部间距、表格辅助元数据 |
| sm | 8px | 紧凑表单字段、门禁行、时间线行、控件组 |
| md | 16px | 默认组件间距、移动端 section 内边距 |
| lg | 24px | 实验/观点 section 与桌面面板内边距 |
| xl | 32px | 工作流阶段之间的清晰分隔 |
| 2xl | 48px | 主要工作区内容块分隔 |
| 3xl | 64px | 页面级分隔；不得作为装饰性留白 |

**Exceptions:** 密集审计/门禁/版本表格使用 8px 单元格内边距。`<768px` 时主操作、tab、筛选、分页、`<details>` summary、radio/checkbox 标签和图标操作必须有至少 44×44px 命中区；相邻命中区至少 8px。确认对话框按钮与任务操作组不得因长中文文案挤压或重叠。

---

## Typography

本期新增内容使用既有 sans；版本、指纹、时间、资源数值和审计标识可用既有 mono。只声明以下四个字号和两个字重：

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Metadata / audit labels | 12px | 400 | 1.5 |
| Body / table evidence | 14px | 400 | 1.5 |
| Section heading | 16px | 600 | 1.2 |
| Page heading | 20px | 600 | 1.2 |

`600` 只用于页面/section 标题、已选 tab、任务或门禁状态名称和主操作；其余文字为 `400`。数字右对齐并使用 tabular numerals；版本、指纹和标识符使用可换行/可复制的等宽文本。安全状态、反馈结论、门禁结果和晋级限制必须是完整文字，不能仅依靠粗体、图标或颜色。

---

## Color

既有暗色优先 token 和 60/30/10 表面分配是约束；安全状态的清晰表达优先于装饰。

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `base`: dark `#0A0A0B`; light `#FAFAFA` | 应用背景、现有 Backtest/Analysis 工作区背景 |
| Secondary (30%) | `surface`: dark `#18181B`; light `#FFFFFF`; `elevated`: dark `#212126`; light `#F4F4F5` | section、运行/审计行、表头、非激活 tabs、确认对话框 |
| Accent (10%) | `accent` `#3B82F6` | `新建实验规格`、`运行受限实验`、`启动受限研究任务`、全部门禁通过后可用的批准动作、当前 tab、2px focus ring、显式证据/审计详情链接 |
| Warning | `warning` `#F79009` | 样本不足、不可评估、等待人工复核、普通约束失败、未完成门禁；必须有文字与图标 |
| Destructive | `danger` `#F04438` | 安全拒绝、执行前复核拒绝、沙箱终止、门禁未通过与真正破坏性确认；必须有文字与图标 |
| Market direction | `bull` `#F04438` 正收益/涨；`bear` `#12B76A` 负收益/跌 | 仅价格、相对收益和图表市场方向，绝不表示授权、门禁、置信度质量、研究反馈或晋级成功 |

Accent reserved for: 新建/运行/启动受限任务的主操作、所有门禁通过后可用的明确晋级操作、当前 tab、可见 keyboard focus ring、显式证据和审计详情链接。它不得用于每张卡边框、所有可点击项目、置信度 bucket、成功门禁、普通状态或装饰。

正常文本与交互标签对背景至少 4.5:1；大号/粗体文字与焦点指示至少 3:1。授权、拒绝、门禁、反馈、置信度和市场方向均以文字 + 图标/颜色冗余传达。

---

## Responsive Behavior

| Viewport | Required layout behavior |
|---|---|
| `>=1280px` | 保持现有 Backtest 内容区和研究库关系。观点摘要/校准可双列，实验规格/当前运行可双列，但每列至少 320px。门禁矩阵、版本差异和审计表保持语义表格；右侧细节不能压过安全 warning 或主内容。 |
| `768--1279px` | 先显示对象/运行状态和安全/不可评估信息，后显示版本、门禁、校准与审计。表单单列或在每列至少 320px 时双列；运行和候选列表维持完整元数据。 |
| `<768px` | 单列：`PageHeader` 标题/副标题先换行再显示操作；既有 tabs 横向滚动、标签不裁剪；安全拒绝/不可评估/门禁失败固定在受影响操作上方；批准确认、任务、规格和沙箱区按流程顺序堆叠。所有本期控件满足 44px 触区。 |
| Any evidence/audit table | 保留版本、时间、状态、范围、证据/原因和审计入口；`overflow-x-auto` 并显示 `左右滚动查看完整记录`。小屏不得把表格变成缺少安全状态、审计或时间上下文的卡片，亦不得隐藏门禁行。 |

不采用流式字号。长中文、英文公司名、标的代码、版本/指纹与脱敏诊断使用 `overflow-wrap:anywhere`；说明文本最大 65ch。对话框/Popover 采用既有 fixed/portal placement，不能被表格 overflow 容器裁切。

---

## Accessibility Contract

- 使用 `main`、`section`、`aside`、顺序 headings、原生 `button`、`input`、`textarea`、`select`、checkbox、radio、`table`、`details`、`summary`。筛选和表单字段同时有可见标签与程序化 label；表格具有 `<caption>`、`thead` 和 scoped `<th>`。
- 复用 Backtest 与分析详情的真实 `tablist`/`tab`/`tabpanel`、`aria-selected`、`aria-controls` 和 Left/Right 方向键；本期不使用只有图标的模式切换。小屏横向 tab 可见且可键盘到达。
- 每个键盘可到达控件使用可见 2px accent focus ring/2px offset；DOM 与 tab 顺序按视觉/任务顺序。图标复述文字时 `aria-hidden`；唯一图标操作必须有明确 `aria-label`、tooltip 与 44px 小屏触区。
- 代理进度、规格创建、运行和批准成功使用 `aria-live="polite"`/`role="status"`，每个受控阶段最多播报一次；安全拒绝、门禁阻断、提交错误和沙箱终止使用 `role="alert"`，说明下一步且不播报机密策略细节。
- 晋级确认是语义 `dialog`：焦点陷阱、初始焦点、Esc 关闭、关闭后焦点回到触发按钮；确认按钮须具完整动作名称。理由缺失/过短时显示字段级错误并聚焦该字段。
- 状态不依赖颜色：`通过 / 未通过 / 缺少证据 / 评估中`、`支持 / 证伪 / 无结论 / 需要复现`、`不可评估`、授权拒绝与市场涨跌均为文字 + 色彩/图标。无样式或色觉差异用户仍能辨别。
- 校准或收益图若实现，提供标题、窗口/基准、系列文字摘要及同等可读表格；关键样本数、覆盖期和不可评估原因不得只出现在 canvas 或 hover tooltip。
- 尊重 `prefers-reduced-motion`。明暗主题均满足规定对比度；长文本安全换行。不得以闪烁、自动滚动、颜色脉冲或 raw SSE 文本传达任务关键状态。

---

## Copywriting Contract

| Element | Copy |
|---|---|
| Primary CTA | `启动受限研究任务` |
| Experiment CTA | `新建实验规格` / `运行受限实验` |
| Sandbox CTA | `验证并运行受限策略` |
| Promotion CTA | `批准晋级为研究策略` |
| Viewpoint heading | `归因观点与表现校准` |
| Material change | `材料立场变化` |
| Minor revision | `内容修订，未构成立场变化` |
| Correction | `更正版本：{reason}` |
| Calibration insufficiency | `样本不足，暂不能评价置信度校准。` |
| Unevaluable | `不可评估：{reason}` |
| Viewpoint empty | `暂无可归因的市场观点` / `在支持的分析对象中导入或生成带来源档案、范围和发布时间的观点后，版本、变化和表现会在这里保留。` |
| Experiment empty | `尚无实验规格` / `从已选研究资产创建规格，先冻结假设、数据范围、方法、指标和成败标准。` |
| Run pending | `正在冻结输入并运行受限实验…` |
| Run failure | `运行未完成：{constraintReason}` |
| Retry | `以新运行重试` |
| Feedback heading | `记录研究反馈` |
| Feedback options | `支持` / `证伪` / `无结论` / `需要复现` |
| Feedback constraint | `此运行未完成，不能记录研究反馈。` |
| Gate heading | `晋级门禁` |
| Gate constraint | `排序不代表可晋级；所有门禁必须独立通过。` |
| Promotion result | `已晋级为研究策略版本；不会启用监控、创建交易计划或执行市场动作。` |
| Promotion conflict | `晋级未记录：状态已变化，请重新查看门禁。` |
| Authorization pending | `正在验证授权范围…` |
| Launch rejection | `任务未启动：{safeReason}` |
| Pre-execution rejection | `当前授权或允许范围已变化，任务未执行。` |
| Agent empty | `当前范围内暂无受限研究任务` / `从允许的研究对象启动任务后，可在这里查看受控进度与审计摘要。` |
| Audit refresh error | `刷新任务审计失败，正在显示上次结果。重新加载任务审计` |
| Contract validation pending | `正在检查策略合同与限制…` |
| Sandbox rejection | `策略未运行：{safeReason}` |
| Sandbox termination | `沙箱已终止：{safeReason}` |
| Audit disclosure | `查看证据与审计` / `查看运行清单` / `查看安全审计摘要` |
| Destructive confirmation | `确认晋级为研究策略`：`确认将候选 {candidateName} 作为新的研究策略版本晋级？此操作会保留批准时间与理由，不能自动启用策略或执行市场操作。` |

不向用户暴露原始 `job_id`、authorization/token、内部 allowlist、策略规则、文件路径、环境变量、完整异常堆栈或未验证模型草稿。可见的版本/运行/审计标识必须有中文人类标签，且可复制文本受脱敏和服务端投影约束。不得使用泛化的 `提交`、`保存`、`确定`、`取消` 作为本期主操作。

---

## UI Considerations

Applicable state considerations resolved: **31 covered, 0 backstop, 0 unresolved**。

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| empty | 归因观点 | covered | 使用规定观点空状态，说明需要来源档案、范围和发布时间，禁止用空收益或占位观点填充。 |
| loading | 归因观点/版本比较 | covered | 局部 skeleton 保持高度；不清除已读取的分析报告、证据或其他版本。 |
| error | 归因观点/校准 | covered | 服务端安全错误原位显示并可重试；不可评估是领域结果，不被误显示为网络错误。 |
| partial | 观点表现 | covered | 缺价格/基准/样本明确为不可评估或样本不足，保留范围、窗口和可用计数。 |
| zero-one-many | 观点版本 | covered | 零进入空状态；一版显示完整谱系和结果；多版倒序时间线并支持两版比较。 |
| long-text | 观点/更正原因 | covered | 结论、证据摘录和修正原因安全换行，标识符可复制/展开。 |
| empty | 实验规格/运行 | covered | 无规格与无运行分别给出规定下一步，不把历史运行当作可编辑草稿。 |
| loading | 实验运行 | covered | 显示受控阶段与 skeleton，保留规格和历史运行；重复请求聚焦活跃运行。 |
| error | 实验运行 | covered | 校验/超时/资源失败显示约束原因和脱敏诊断，失败不能产生研究反馈或晋级证据。 |
| populated | 运行清单 | covered | 显示规格、数据指纹、资产版本、参数、环境、资源限制、产物和审计入口。 |
| zero-one-many | 反馈记录 | covered | 零显示未记录；一条完整关联运行和指标；多条按时间保留，不提供覆盖。 |
| empty | 演化候选 | covered | 显示暂无候选及先完成受控实验的下一步；不显示虚构排名。 |
| partial | 门禁矩阵 | covered | 每个门禁独立显示通过/失败/缺证据/评估中，任一非通过即禁用晋级。 |
| error | 晋级批准 | covered | 并发/重放/状态变化显示规定冲突文案，保留门禁与理由输入。 |
| destructive | 晋级 | covered | 使用明确确认对话框、候选/门禁复述、必填理由和不自动执行限制；晋级只生成研究资产。 |
| empty | 受限代理任务 | covered | 当前范围无任务时使用规定任务空状态，不提供无对象范围的启动入口。 |
| loading | 授权与 SSE 进度 | covered | 启动前显示授权校验；启动后仅显示服务端允许阶段，不显示 raw token 或模型流。 |
| error | 任务拒绝 | covered | 创建前拒绝与执行前复核拒绝分开表达，均有审计入口但不泄露策略细节。 |
| partial | 任务审计 | covered | 刷新失败保留上次成功数据，以 status 文案可重试；单一任务失败不清空其他审计行。 |
| zero-one-many | 任务记录 | covered | 零进入空状态；一条完整显示范围、状态、时间、审计；多条使用筛选、分页及范围宣告。 |
| overflow | 任务/审计表 | covered | 保留安全状态、范围、时间、原因和审计列并横向滚动，不简化为无上下文卡片。 |
| empty | 自定义策略合同 | covered | 无可用策略资产时解释需先选择策略；禁止空白编辑器直接运行。 |
| loading | 合同验证/沙箱 | covered | 各验证项和沙箱状态独立更新，不清除已验证项和历史运行。 |
| error | 合同/沙箱 | covered | AST/import/资源限制明确失败原因与脱敏诊断；网络错误不表述为安全拒绝。 |
| populated | 沙箱结果 | covered | 显示结果、资源摘要（若有）、运行指纹与审计链接，不能输出受限环境细节。 |
| zero-one-many | 沙箱运行 | covered | 零显示规定下一步；一条完整结果/失败；多条按版本和时间可审阅且不覆盖。 |
| overflow | 规格、合同、指纹 | covered | 长 JSON 摘要、版本和指纹安全换行/可复制；完整机器合同放入可访问 details。 |
| mobile | 所有工作流控件 | covered | 小屏单列、44px 触区、横滚表格、无裁剪 tab 和可达对话框已定义。 |
| accessibility | 高风险状态与确认 | covered | 状态文字冗余、alert/status、语义表格、键盘 tabs、dialog 焦点管理和 reduced motion 均已定义。 |

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|---|---|---|
| shadcn official | None | Not applicable — `components.json` 不存在；Phase 04 复用本地组件且不初始化 shadcn（2026-07-12）。 |
| Third-party registry | None | 未声明或允许第三方 block；无需 registry vetting。 |

---

## Verification Scenarios

1. **ADV-01 viewpoint lineage and honesty:** 在既有对象分析中载入同一来源档案的普通修订、材料立场变化和更正版本。确认版本不会覆写、变化字段可辨，且 20/60/120 日窗口、基准、相对收益、样本数、覆盖期和低/中/高置信度校准完整可见。制造缺价格/基准与小样本情况，确认显示不可评估/样本不足，绝不显示零值或可靠结论。
2. **ADV-02 reproducible experiment feedback:** 从 Backtest 已选研究资产创建实验规格，确认假设、范围、方法、指标、成败标准在运行前冻结。检查运行清单中的数据指纹、参数、环境和资源；验证超时/资源失败不会形成反馈。对完成运行依次记录四种反馈，确认它们追加保留且重试创建新运行。
3. **ADV-03 independent promotion gates:** 载入候选策略，确认父版本、变异、种子和解析配置可查，五项独立门禁完整可见。缺任一门禁时无法批准；全通过后确认对话框要求理由并显示已注册研究策略版本。断言界面没有“启用监控”“创建交易计划”或市场执行入口。
4. **SAFE-01 authorization and task audit:** 分别提交有效、过期、撤销、allowlist 不匹配和限流请求。确认后三类在工作与 SSE 开始前显示不同的安全拒绝和脱敏审计；使已排队任务在执行前失去授权，确认其变为执行前复核拒绝且不自动重试。有效任务只展示受控阶段，任务审计筛选与局部刷新失败保留上次数据。
5. **SAFE-02 sandbox boundary:** 使用通过与失败的合同/AST/import/超时/内存用例。确认运行按钮只在验证通过后启用，所有拒绝/终止显示受限原因及审计链接而没有原始堆栈、路径、令牌或代码回显，且失败不能写为研究结论或晋级证据。
6. **Responsive and keyboard:** 在 1440px、1024px、375px 使用键盘操作 Backtest tabs、观点版本比较、规格表单、反馈 radio、门禁详情、批准 dialog、任务筛选、审计 details 和沙箱验证。确认焦点顺序、44px 小屏触区、横向表格、长文本、安全状态冗余、dialog 焦点管理和 reduced motion 合规。

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: 具体启动/运行/批准操作、空/错误/拒绝/不可评估文案与确认语义已定义
- [ ] Dimension 2 Visuals: 既有 Backtest、Analysis 和运营审阅集成、证据优先层级及无平行壳约束已定义
- [ ] Dimension 3 Color: 既有 60/30/10 token、受限 accent、warning/danger/市场色语义及对比度已定义
- [ ] Dimension 4 Typography: 四个字号、两个字重、行高、数值与长文本规则已定义
- [ ] Dimension 5 Spacing: 标准 4px scale、窄屏 44px 触区、密集审计表节奏与响应式行为已定义
- [ ] Dimension 6 Registry Safety: 未使用 shadcn 或第三方 registry，缺席证据已记录

**Approval:** pending
