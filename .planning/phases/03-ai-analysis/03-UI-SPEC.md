---
phase: 03
slug: ai-analysis
status: approved
shadcn_initialized: false
preset: none
created: 2026-07-11
reviewed_at: 2026-07-11
---

# Phase 03 — UI Design Contract

> 以现有研究工作区呈现 AI 辅助分析的证据、推理与信号演化；任何 AI 结论都必须能被定位到来源质量、核验状态和时间上下文，而不是以不可审计的推荐卡片出现。

---

## Scope and Source Decisions

| Source | Binding UI decision |
|---|---|
| `REQUIREMENTS.md` ANLY-01 | 市场或组合分析必须逐项显示 A/B/C 来源质量、材料数字的来源和交叉核验状态；未解决差异不得被隐藏或表述为确定事实。 |
| `REQUIREMENTS.md` ANLY-02 | 报告必须同时提供多视角结论、可追溯评分理由、仅在适用时出现的估值分析，以及投资委员会备忘录。 |
| `REQUIREMENTS.md` ANLY-03 | 信号要同时显示当前生命周期状态、带时间戳的演变和记录结果；“强化/弱化/证伪/已计价”不是颜色或 AI 自评。 |
| Phase 02 `02-UI-SPEC.md` | 沿用 React/Vite/Tailwind、typed `api.ts`、TanStack Query `QK`、Lucide、现有暗色优先 tokens、语义表格与 `<details>` 证据披露；不新增设计系统、图表库、全局状态库或第二个 API 客户端。 |
| Existing `StockAnalysis`, `Portfolio`, `AiAnalysisHost` | 在已有个股分析、财务分析、组合和全局 AI 分析对话框/历史入口中扩展“分析详情 / 证据 / 信号历史”面板；保留当前标的、持仓和报告历史上下文，不创建平行顶级导航、独立仪表盘或第二个报告弹窗。 |

### Phase boundary

- **In scope:** A/B/C 来源质量上下文；材料数字跨源核验和未解决差异；多视角报告、评分理由、适用估值和 IC 备忘录；信号的当前状态、时间线和结果；对以上对象的加载、空、局部失败和可访问反馈。
- **Out of scope:** 自动交易、自动采纳/执行 AI 建议、人工改写或删除既有证据、伪造缺失估值、给报告/视角排名为“唯一正确答案”、新顶级路由/壳层、第三方组件注册表。

---

## Design System

| Property | Value |
|---|---|
| Tool | 现有手工系统：Tailwind CSS 3.4 tokens 和本地 React 组件 |
| Preset | 不适用；`components.json` 不存在，Phase 03 不初始化 shadcn |
| Component library | 现有本地组件与原生语义控件；使用现有 `PageHeader`、`EmptyState`、`Skeleton`、对话框、表格和 `<details>` 模式 |
| Icon library | `lucide-react`；14–16px 轮廓图标仅作文字标签辅助，绝不单独传达来源等级、核验、状态或操作含义 |
| Font | `Inter`, `HarmonyOS Sans SC`, `PingFang SC`, system sans；`JetBrains Mono`/`IBM Plex Mono` 仅用于数值、日期、报告/信号/来源标识与原文定位 |
| Server state | 现有 typed `api.ts`、TanStack Query 和 `QK` factories；禁止直接 `fetch`、本地合成来源/核验结果，或把 AI Markdown 当成唯一证据源 |
| Existing surfaces | `StockAnalysis` 主板与历史侧栏、`Portfolio` 摘要/持仓、`AiAnalysisHost` 全局宿主及现有历史报告入口；新增内容为这些表面的可组合区域，不改变其路由/壳层 |

### Existing visual tokens to preserve

严格沿用 `frontend/src/index.css`：`base`、`surface`、`elevated`、`border`、`foreground`、`secondary`、`muted`、`accent`、`warning`、`danger`、`bull`、`bear`。默认暗色、亮色使用既有 token 反转。使用 1px `border-border`、现有 `rounded-input` 4px、`rounded-btn` 6px、`rounded-card` 8px、`rounded-dialog` 12px。不得为 AI 功能加入渐变、玻璃化、发光、悬浮阴影或专属紫色体系；Phase 03 面板与现有 `bg-surface` 数据工作区等同。

---

## Information Hierarchy and Evidence Workflow

### Surface hierarchy

1. **既有页面标题和对象上下文：** 保留 `PageHeader`、股票名称/代码或已选账户、时间窗和数据新鲜度。标题右侧只出现一枚文本化的分析状态标签，例如 `报告已就绪`、`正在生成` 或 `需要核验`；不得把 A/B/C 等级误作报告总体质量分。
2. **分析详情首屏（视觉焦点）：** 在现有个股分析/财务分析/组合的结果区域内，首先显示 `分析结论与证据状态`：对象、生成时间、覆盖期间、报告状态、材料数字核验汇总和可见的 `查看来源与差异` 控件。先显示核验/未解决风险，再显示 AI 摘要；不能让摘要视觉上压过未核验材料数字。
3. **报告工作区：** 使用现有页面内 section 或现有全局 AI 对话框的完整详情态，而非新弹窗。按固定顺序呈现 `多视角` → `评分理由` → `估值（如适用）` → `投资委员会备忘录` → `来源与核验`。每段有可链接的标题和对象/期间上下文；折叠只适用于原始证据，不适用于核验失败、关键结论或 IC memo 主结论。
4. **信号历史：** 在与标的/组合上下文相邻的已有历史区域中加入 `信号生命周期`。视觉焦点为当前状态和最近一条有日期的状态变化；之后才是倒序时间线和结果。历史回答“何时、依据什么变化”，不能被单一当前状态徽章替代。

### Required evidence disclosure contract (ANLY-01)

| Surface | Required visible data and behavior |
|---|---|
| 来源质量汇总 | 显示 `A / B / C` 的文字等级、来源类型/名称、抓取或生效时间和本报告覆盖项数；等级旁的帮助文本解释：A=原始或已治理来源、B=可追溯二级来源、C=待验证辅助来源。等级绝不只以颜色表示。 |
| 材料数字行 | 每个进入结论、评分或估值的数字都显示人类标签、值/单位、期间、来源数量和 `已交叉核验`、`存在差异` 或 `尚未核验` 的文字状态；标识符与时间使用等宽字。 |
| 跨源核验 | 默认展示汇总 `已交叉核验 {n}/{total} 项`；激活 `查看来源与差异` 后在语义表格中展示每项数字的来源、提取值、期间/口径、核验结果和差异说明。两个同值来源不等同于独立核验：服务端必须给出独立来源/核验依据，UI 仅渲染该事实。 |
| 未解决差异 | 状态用 `存在未解决差异` 和 warning icon/text 直接呈现，置于受影响结论和 IC memo 前；显示差异字段及 `查看差异依据`。受影响结论标记 `受未解决来源差异影响`，不得显示“已确认”或升格为确定性操作建议。 |
| 原始证据 | 使用原生 `<details>`，摘要如 `查看收入同比的 2 个来源`；内含来源名称、链接/内部引用、时间、口径、摘录/定位与核验说明。链接在同一安全导航约定下打开，不能仅把不可访问的 URL 放进 AI Markdown。 |
| 报告来源说明 | 摘要结尾固定出现：`AI 结论基于所列证据生成；来源等级和核验状态限制其可采信程度，不构成投资建议。` 该说明不能被折叠或在移动端省略。 |

### Multi-perspective report and IC memo (ANLY-02)

| Region | Contract |
|---|---|
| 多视角 | 至少按服务端返回的视角逐个呈现（如基本面、估值、技术/市场、风险）；每张视角区显示视角名称、结论、置信/评分输入、引用证据计数和限制。没有返回的视角显示 `此报告未提供{视角}证据`，不得填充推测内容。视角 chips/页签仅用于定位，不合并成“综合赢家”。 |
| 评分理由 | 显示总分（若领域模型提供）及每个评分维度的名称、贡献/权重、证据引用、计算/判定说明和不确定性。没有可解释理由时显示 `评分暂不可解释，不能用于比较。`，而不是渲染裸分。UI 不能自行计算、排序或归一化分数。 |
| 估值 | 仅在服务端判断适用且返回方法/输入/期间时显示 `估值分析`；显示方法、关键输入、基准日期、估值范围/情景、来源和限制。若不适用，显示 `本报告不适用估值分析：{服务端原因}`；若缺少材料输入，显示 `估值输入不完整，未形成估值结论。`，不得显示空图表、`0` 或占位目标价。 |
| IC memo | 以固定的结构化 section 展示 `投资要点`、`支持证据`、`主要反方观点/风险`、`待解决问题`、`估值锚点（若适用）`、`失效条件（若返回）` 和 `来源与核验限制`。memo 顶部重复材料差异 warning；“待解决问题”不可被折叠。它是决策审阅材料而非执行指令。 |
| 复制/导出 | 现有 `复制全文` 操作若保留，必须复制报告元数据、生成时间、来源限制和未解决差异提示；控件标签为 `复制含证据说明的报告`，成功以 `已复制报告与证据说明。` 的 `role=status` 反馈。 |

### Signal lifecycle and outcome (ANLY-03)

| State | Visible treatment and allowed behavior |
|---|---|
| `强化` | 文字 `信号已强化` 加图标和语义状态色；显示导致变化的最近证据、时间、来源等级/核验状态。 |
| `弱化` | 文字 `信号已弱化` 加图标和语义状态色；显示与原假设相冲突或降低把握的可定位证据。 |
| `证伪` | 文字 `信号已证伪` 加 danger treatment；显示证伪条件、触发证据和日期。它不是可忽略的负面徽章，必须在时间线和当前状态中保留。 |
| `已计价` | 文字 `信号已计价` 加中性/警示 treatment；显示判断时点、价格/事件上下文和证据限制。绝不将其混同为“成功”或“过期”。 |
| 结果待定 | 文字 `结果待观察`；显示最近检查时间和下一可用观察点（如果服务端提供）。不得以空收益或默认成功替代。 |
| 已记录结果 | 显示 `已记录结果`、观察窗口、截至日期、结果值/单位、对比基准（如有）、数据新鲜度及证据引用；缺少任一必要结果字段时显示 `结果记录不完整：{缺失项}。`。 |

信号时间线按事件时间倒序，行内固定为状态、事件时间、证据摘要、来源/核验标签和 `查看事件依据`。相同信号的重复事件保留原始时间戳而不合并；筛选只能隐藏视图，不能改变当前状态或历史。当前状态由最新服务端记录确定，前端不得根据颜色、收益或报告文本推断。

---

## Interaction States and Feedback

| Control / surface | Default, focus and interaction | Loading, empty, error and partial behavior |
|---|---|---|
| `生成含证据说明的分析` | 现有页面内主操作，accent 填充；仅在已选标的/组合且服务端允许时启用。焦点为 2px accent ring + 2px offset。重复请求聚焦同一进行中任务，不创建第二份同对象并发报告。 | 请求中标签 `正在整理来源与生成分析…`，禁用重复提交但保留最小化/恢复现有任务；流式文本每次增量到达可见但首屏先保留核验占位。失败显示服务端消息和 `重新生成含证据说明的分析`，AI 配置错误另显示 `前往配置 AI`。 |
| 分析详情 tabs / anchors | 采用真实 `tablist`/`tab`/`tabpanel`，包含 `分析结论`、`来源与核验`、`信号历史`；`aria-selected`、`aria-controls` 完整，左右箭头切换。若使用页内锚点，保留可见标题和 keyboard focus 目标。 | 每个面板独立 skeleton 与错误，失败不得清空已加载的兄弟面板。切换时保留选中对象、滚动上下文与已读历史。 |
| `查看来源与差异` / 原始证据 `<details>` | 有可见文字、可访问 name 和箭头状态；打开后将焦点移动到 disclosure summary，关闭不丢失当前数字行。 | 来源延迟加载时维持行高并显示 `正在读取来源记录…`；仅该 disclosure 失败时显示 `无法读取该数字的来源记录。重新加载来源记录`。 |
| 视角筛选和报告折叠 | 默认所有返回视角可见；筛选标签是 toggle button，带 `aria-pressed` 和视角全名，不能以单个色块区分。 | 视角缺失是领域事实而非网络错误；显示规定的未提供证据文本和空位说明。 |
| 信号时间线筛选、翻页 | 使用原生 checkbox/select，状态文字全写；语义表格用 `<caption>` 说明当前信号与筛选。分页宣布 `显示第 {start}–{end} 条，共 {total} 条事件`，边界禁用前后页，改变后焦点回到表格标题。 | 加载显示事件行 skeleton；无历史与结果待定分别使用不同空状态；刷新失败保留上次成功记录并以 `role=status` 显示 `刷新信号历史失败，正在显示上次结果。重新加载信号历史`。 |
| 报告/信号长文本 | 解释文字 max 65ch；证据摘录默认换行，`overflow-wrap:anywhere`；标识符/来源 URL 的可复制文本使用截断+title/展开，而不能让卡片溢出。 | 长表格采用 `overflow-x-auto`，顶部提示 `左右滚动查看全部证据列`；绝不转换成删失来源列的卡片。 |

使用 150–200ms `ease-smooth` 的颜色/透明度状态反馈，不能动画化布局高度、数据到达、报告文本或核验 warning。`prefers-reduced-motion: reduce` 下全部即时，加载继续使用文字/骨架/进度，不依赖旋转或闪烁传达状态。

---

## Spacing Scale

Declared values（全部为 4 的倍数）：

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | 图标—文字间距、紧凑来源标签内边距 |
| sm | 8px | 数字行内证据标签、控件组间距 |
| md | 16px | 默认组件间距、窄屏面板内边距 |
| lg | 24px | 相邻报告 section 与桌面面板内边距 |
| xl | 32px | 分析/信号区块分隔 |
| 2xl | 48px | 主要工作流边界 |
| 3xl | 64px | 页面级分隔；不得作为装饰性留白 |

**Exceptions:** 现有密集证据/时间线表格维持 8px 单元格内边距。`<768px` 时主要操作、tabs、筛选、分页、`<details>` summary 和任何图标操作必须有 44×44px 命中区；相邻命中区至少 8px。可见内容可密集，但不得缩小可触达区域。

---

## Typography

Phase 03 新增内容使用现有 sans；标识/日期/数值/来源定位可用现有 mono，但不增加字号或字重。只声明以下四个字号和两个字重：

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Metadata / source labels | 12px | 400 | 1.5 |
| Body / table evidence | 14px | 400 | 1.5 |
| Section heading | 16px | 600 | 1.2 |
| Page heading | 20px | 600 | 1.2 |

`600` 仅用于页面/section 标题、已选 tab、状态名称和主操作；其他内容为 `400`。A/B/C、核验和生命周期状态以完整文字表达，不能依赖加粗或颜色。材料数字右对齐并使用 tabular numerals；长来源和证据摘要安全换行。

---

## Color

既有暗色优先 token 和 60/30/10 表面分配是约束，不是给所有控件上色的理由。

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `base`：dark `#0A0A0B`；light `#FAFAFA` | 应用与现有分析工作区背景 |
| Secondary (30%) | `surface`：dark `#18181B`；light `#FFFFFF`；`elevated`：dark `#212126`；light `#F4F4F5` | 报告 section、证据 disclosure、历史面板、表头和非激活 tabs |
| Accent (10%) | `accent` `#3B82F6` | `生成含证据说明的分析`、当前 tab、2px focus ring、显式来源/历史详情链接和中性已选筛选项 |
| Warning | `warning` `#F79009` | `存在未解决差异`、`尚未核验`、结果待观察和提醒；必须伴随图标与文字 |
| Destructive | `danger` `#F04438` | `信号已证伪`、报告/来源加载失败与真正破坏性操作；必须伴随文字 |
| Market direction | `bull` `#F04438` 正收益/涨；`bear` `#12B76A` 负收益/跌 | 仅价格、收益和图表市场方向，绝不表示来源质量、核验成功或生命周期成功 |

Accent reserved for: 生成分析主操作、当前分析 tab、可见 keyboard focus ring、显式的证据/历史详情链接和已选中性筛选项。它不得用于每张卡边框、通用可点击项、A/B/C 等级、所有信号状态或装饰。

所有正常文本及交互标签对所在背景至少 4.5:1；大号/粗体文字与焦点指示至少 3:1。来源等级、核验、生命周期、错误和市场涨跌均须有文字/图标冗余。

---

## Responsive Behavior

| Viewport | Required layout behavior |
|---|---|
| `≥1280px` | 保持既有内容区与历史侧栏关系；分析结论/核验汇总可双列，只有当每列至少 320px。报告主内容优先于历史列表，信号时间线可在右侧但不遮挡来源 warning。 |
| `768–1279px` | 主报告在前、历史/信号区在后；评分理由与估值摘要可在各列至少 320px 时双列，否则堆叠。来源与差异表格保持语义表格和横向滚动。 |
| `<768px` | 单列：`PageHeader` 标题/副标题先换行后操作；分析 tabs 横向可滚动且标签不可裁剪；核验 warning 固定在受影响结论上方；报告 section、IC memo 和时间线按单列顺序。所有 phase 控件满足 44px。 |
| Any evidence table | 保留数字、期间、来源、核验、差异和状态列；`overflow-x-auto` 并显示横滚提示，不能因小屏隐藏质量/来源/证伪信息或将材料数字转换成无上下文卡片。 |

不采用流式字号。沿用现有 `xl` 以上 split 与小屏单列模式；modal/popover 采用固定/portal placement，不能被证据表的 overflow 容器裁切。

---

## Accessibility Contract

- 使用 `main`、`section`、`aside`、顺序 headings、原生 `button`、`input`、`select`、checkbox、`table`、`details`、`summary`。可筛选控件必须有可见标签和程序化 label；表格具有 `<caption>`、`thead`、scoped `<th>`。
- 分析 tabs 遵守 `tablist`/`tab`/`tabpanel`、`aria-selected`、`aria-controls` 和 Left/Right navigation；筛选使用原生控件或带 `aria-pressed` 的可见文字按钮，不使用仅图形 chips。
- 每个键盘可到达控件有可见 2px accent focus ring/2px offset；DOM 及 tab 顺序跟随视觉顺序。图标复述文字时 `aria-hidden`；图标唯一操作有明确 `aria-label`、tooltip 与 44px 窄屏触区。
- 生成/流式状态和局部刷新使用 `aria-live="polite"`/`role="status"`，不重复播报每个 token；提交/加载失败与未解决来源差异使用 `role="alert"` 并指向可重试或查看证据的下一步。
- A/B/C、核验状态、信号状态、市场方向都使用视觉文字 + 图标/颜色；色盲或无样式用户仍能区分。来源表可通过标题、caption、数字的行/列标题和 details 摘要理解，不要求 hover tooltip。
- 估值图/时间序列若实现，提供标题、轴/系列文字、日期/值文本摘要和同等的表格/明细；不得把决策相关证据锁在 canvas、颜色或 hover 中。
- 尊重 `prefers-reduced-motion`，不以动画隐藏警告/证据。现有明暗主题均保持指定对比度；长中文、英文公司名、代码、URL 和服务端错误使用安全换行。

---

## Copywriting Contract

| Element | Copy |
|---|---|
| Primary CTA | `生成含证据说明的分析` |
| Generation pending | `正在整理来源与生成分析…` |
| Retry CTA | `重新生成含证据说明的分析` |
| Analysis focus heading | `分析结论与证据状态` |
| Cross-check summary | `已交叉核验 {checked}/{total} 项材料数字` |
| Unresolved difference | `存在未解决差异：{field} 的来源口径或数值不一致。查看差异依据后再判断结论。` |
| Unchecked material number | `尚未核验：{field} 仅有 {sourceCount} 个可用来源。` |
| Evidence disclosure | `查看来源与差异` / `查看{field}的 {count} 个来源` |
| Source quality help | `A=原始或已治理来源；B=可追溯二级来源；C=待验证辅助来源。` |
| No selected object | `选择标的或账户后开始证据分析` / `分析会显示来源质量、材料数字核验、报告理由与信号历史。` |
| No report | `尚无含证据说明的分析报告` / `选择标的或账户后生成分析；报告会保留生成时间、来源限制和可审阅证据。` |
| Source empty | `此报告没有可展示的来源记录` / `该结论不能视为已核验；请查看报告限制或重新生成分析。` |
| Source load error | `无法读取来源与核验记录。请检查服务连接后重新加载来源记录。` |
| Report load error | `无法读取分析报告。请检查服务连接后重新加载分析报告。` |
| AI configuration error CTA | `前往配置 AI` |
| Viewpoint missing | `此报告未提供{perspective}证据。` |
| Unexplained score | `评分暂不可解释，不能用于比较。` |
| Valuation not applicable | `本报告不适用估值分析：{reason}` |
| Valuation incomplete | `估值输入不完整，未形成估值结论。` |
| IC memo heading | `投资委员会备忘录` |
| Lifecycle heading | `信号生命周期` |
| Strengthened / weakened | `信号已强化` / `信号已弱化` |
| Falsified / priced in | `信号已证伪` / `信号已计价` |
| Outcome pending / recorded | `结果待观察` / `已记录结果` |
| Lifecycle empty | `该标的尚无可追溯信号事件` / `生成或导入带证据的研究信号后，状态变化和结果会在这里按时间保留。` |
| Lifecycle partial | `结果记录不完整：{missingFields}。` |
| Lifecycle refresh error | `刷新信号历史失败，正在显示上次结果。重新加载信号历史` |
| Copy action | `复制含证据说明的报告` / `已复制报告与证据说明。` |
| Disclaimer | `AI 结论基于所列证据生成；来源等级和核验状态限制其可采信程度，不构成投资建议。` |
| Destructive confirmation | Phase 03 不声明用户可删除、覆盖或采纳信号/证据的动作；现有历史与证据为只读审阅，故无 destructive confirmation。 |

不向用户暴露未经解释的 `run_id`、source ID、signal ID 或内部核验代码；这些可作为等宽可复制元数据出现，但必须有中文人类标签。`关闭`、`复制` 等局部既有图标操作保留明确 aria-label/title；Phase 03 新增主操作不得使用 `提交`、`保存`、`确定`、`取消` 或单词式标签。

---

## UI Considerations

> UI-consideration probe post-verification coverage。空/错误文案引用上方 Copywriting Contract，避免重复；每行是实现和计划的具体状态真值。

Applicable state considerations resolved: **28 covered, 0 backstop, 0 unresolved**。

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| empty | 分析详情、报告历史 | ✅ covered | 未选对象和无报告分别显示规定的 `选择标的或账户后开始证据分析` 与 `尚无含证据说明的分析报告`，并提供生成下一步。 |
| loading | 分析详情、报告生成 | ✅ covered | 每个查询面板保留高度 skeleton；生成中显示 `正在整理来源与生成分析…`，禁用重复提交并允许现有任务最小化/恢复。 |
| error | 分析详情、报告生成 | ✅ covered | 报告/生成失败显示服务端原因、规定的重试 CTA；AI 配置错误额外给出 `前往配置 AI`。 |
| partial | 分析详情、材料数字 | ✅ covered | 已加载内容保持可见；任何缺少独立核验或存在差异的材料数字显式标记，不被摘要或评分掩盖。 |
| populated | 分析详情、报告工作区 | ✅ covered | 正常报告按多视角、评分理由、适用估值、IC memo 和来源限制的固定顺序显示；视角/段落均给出证据计数和限制，不合并成“赢家”。 |
| zero-one-many | 分析详情、报告工作区 | ✅ covered | 零报告进入规定空状态；一份报告完整显示所有可用段落与限制；多份历史报告按现有历史入口按时间保留，视角计数/来源计数以明确数字展示。 |
| overflow | 分析详情、来源/差异表 | ✅ covered | 解释文本最大 65ch 并安全换行；证据表在 `overflow-x-auto` 中保留全部来源、期间、核验和差异列，前置横滚提示。 |
| long-text | 分析详情、IC memo、材料数字 | ✅ covered | AI 文字、中文/英文公司名、来源 URL、服务端错误和标识符使用 `overflow-wrap:anywhere`；截断标识提供 title/展开或可复制路径。 |
| empty | 来源与核验记录 | ✅ covered | 没有来源时显示规定的来源空状态，明确该结论不能视为已核验，禁止以空 disclosure 表示成功。 |
| loading | 来源与核验记录 | ✅ covered | 展开 disclosure 时保留行高并显示 `正在读取来源记录…`，只影响该数字行。 |
| error | 来源与核验记录 | ✅ covered | 单一来源记录失败显示 `无法读取该数字的来源记录。重新加载来源记录`，不清除其他报告内容。 |
| populated | 来源与核验记录 | ✅ covered | 每项数字以语义表格呈现人类标签、值/单位、期间、来源、独立核验结果与差异说明；原始证据可在 details 内审阅。 |
| partial | 来源与核验记录 | ✅ covered | 来源/期间/口径不完整或数值冲突显示具体字段与差异依据；受影响结论固定附 `受未解决来源差异影响`。 |
| overflow | 来源与核验记录 | ✅ covered | 长来源、摘录和 URL 换行；横表不删列，窄屏通过横向滚动访问。 |
| zero-one-many | 来源与核验记录 | ✅ covered | disclosure 文案使用 `{count} 个来源`；零来源进入来源空状态，一源显示尚未核验，多源仍以服务端独立核验事实决定状态。 |
| long-text | 来源与核验记录 | ✅ covered | 原始摘录和来源定位允许折行，来源标识有 title/复制或展开，不溢出表格。 |
| loading | 报告导航 tabs | ✅ covered | tabs 可立即切换；各 panel 独立 skeleton，当前对象和已加载面板不因相邻请求 pending 而清空。 |
| error | 报告导航 tabs | ✅ covered | panel 失败在原位显示带下一步的错误，不把失败伪装为空报告或重置其他 tabs。 |
| overflow | 报告导航 tabs | ✅ covered | 小屏 tabs 横向可达、标签不裁剪，焦点和可见选中状态保持。 |
| long-text | 报告导航 tabs | ✅ covered | 视角标签和对象名可换行/横滚，完整 accessible name 始终可读。 |
| empty | 信号生命周期 | ✅ covered | 无事件时使用规定 lifecycle empty 文案，说明生成/导入带证据信号后才会出现时间线。 |
| loading | 信号生命周期 | ✅ covered | 时间线/表格使用事件行 skeleton，保留标题、当前对象和筛选控件。 |
| error | 信号生命周期 | ✅ covered | 刷新失败保留上次成功数据，用 `role=status` 提示并提供 `重新加载信号历史`。 |
| populated | 信号生命周期 | ✅ covered | 典型列表每行固定显示状态、事件时间、证据摘要、来源/核验和事件依据；当前状态来自最新服务端事件。 |
| partial | 信号生命周期 | ✅ covered | 缺少结果字段显示 `结果记录不完整：{missingFields}。`；待观察与已记录结果明确区分，未返回证据不得推断状态。 |
| overflow | 信号生命周期 | ✅ covered | 时间线摘要安全换行；事件表保留关键列并可横向滚动，不能压缩掉证伪/来源信息。 |
| zero-one-many | 信号生命周期 | ✅ covered | 零条进入空状态；一条仍完整显示当前状态与依据；多条倒序分页并公布范围/总数，边界控制禁用。 |
| long-text | 信号生命周期 | ✅ covered | 长证据摘要、状态原因和标的名使用安全换行；标识符有完整 title/展开或复制路径。 |

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|---|---|---|
| shadcn official | None | Not applicable — `components.json` 不存在；Phase 03 复用本地组件且不初始化 shadcn（2026-07-11）。 |
| Third-party registry | None | 未声明或允许第三方 block；无需 registry vetting。 |

---

## Verification Scenarios

1. **ANLY-01 evidence honesty:** 在个股和组合各打开一份报告，确认 A/B/C 文字解释、材料数字的期间/来源/核验和来源 disclosure 可审阅。制造一个服务端标记的口径差异，确认它在摘要、受影响结论和 IC memo 前可见，不能显示为已确认或隐藏。
2. **ANLY-02 report completeness:** 打开返回多视角、解释性评分、适用估值和 IC memo 的报告；确认每个评分维度的理由/证据可见，估值有方法/输入/日期/限制。再验证不适用和输入不完整两种估值状态不会渲染假数字/图表，且无“最佳视角/唯一建议”排序。
3. **ANLY-03 lifecycle traceability:** 载入同一信号的强化、弱化、证伪、已计价和待观察/已记录结果样本；确认当前状态来自最新服务端事件，时间线保留事件、证据、来源核验和日期，结果不完整被明确标注。刷新失败时仍可见上次结果并可重试。
4. **State isolation:** 分别使报告、单一来源 disclosure、信号历史和一个 report tab 失败/加载/为空；确认局部 skeleton/错误不清空已加载的其他面板，空状态有具体下一步，重复生成聚焦既有任务而不重复创建。
5. **Responsive and keyboard:** 在 1440px、1024px、375px 以键盘操作生成、tabs、来源 details、视角筛选、时间线筛选/分页和复制；确认焦点、44px 小屏触区、横向证据表、长文本、语义状态和 reduced motion 合规。

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: 具体主操作、空/错误/部分状态、核验/生命周期文字和无 destructive action 边界已定义
- [x] Dimension 2 Visuals: 既有研究壳层、首屏核验焦点、报告/信号层级和无平行仪表盘约束已定义
- [x] Dimension 3 Color: 既有 60/30/10 token、单一受限 accent、warning/danger/市场颜色语义及对比度已定义
- [x] Dimension 4 Typography: 四个字号、两个字重、行高、数值与长文本规则已定义
- [x] Dimension 5 Spacing: 仅使用标准 4px scale、窄屏 44px 触区和证据表节奏已定义
- [x] Dimension 6 Registry Safety: 未使用 shadcn 或第三方 registry，缺席证据已记录

**Approval:** approved 2026-07-11 — gsd-ui-checker 6/6 PASS
