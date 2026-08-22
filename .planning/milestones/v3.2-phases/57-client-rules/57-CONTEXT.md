# Phase 57: 客户端实时规则引擎 - Context

**Gathered:** 2026-08-22
**Status:** Ready for planning

<domain>
## Phase Boundary

浏览器端价格阈值规则引擎 — 用户在浏览器配置标的 + 价格阈值 (涨跌幅 % 或绝对价格), 规则存 localStorage 不落盘后端; 通过 WebSocket 实时行情流本地评估命中后立即弹窗 + toast; 与服务端监控规则独立共存。

**In scope:**
- 客户端规则 CRUD (localStorage 存储, 页面刷新恢复)
- 规则类型: 涨跌幅 % 阈值 + 绝对价格阈值
- WS quotes 频道实时行情 tick → 本地规则评估
- 命中后 Notification API 弹窗 + 页内 toast
- 命中后可标记已处理或继续监控
- UI 明确标注 "客户端规则" vs "服务端规则"

**Out of scope:**
- 客户端规则云同步
- 规则市场/分享
- 改变服务端监控规则评估语义

</domain>

<decisions>
## Implementation Decisions

### 规则存储
- **D-01:** 规则存储在 localStorage, 使用 `storage.ts` 的 `makeStorage` 模式 (key=`client_rules`), 与 `screenerResultColumns` / `stockInfoBarFields` 等完全对称。规则数据结构: `{id, name, symbol, type: 'pct'|'price', op: '>'|'<'|'>='|'<=', value: number, enabled: boolean, createdAt: string}`。页面刷新后自动从 localStorage 恢复。 — **Reversibility:** reversible — 删除 storage key 即回退

### 规则评估
- **D-02:** 通过 `subscribe('quotes', handler)` 订阅 WS quotes 频道, 每次 `quotes_updated` tick 在浏览器端评估所有 enabled 规则。评估逻辑: 取 tick 中对应 symbol 的 price/pct_change, 按 op + value 判断是否命中。命中后: 1) Notification API 弹窗 (请求权限 → 显示通知), 2) 页内 toast (复用现有 `toast()` from `@/components/Toast`), 3) 播放声效 (复用 `playNotificationSound`)。 — **Reversibility:** reversible — 退订 quotes 频道即停止评估

### 命中后处理
- **D-03:** 规则命中后进入 "triggered" 状态, 记录命中时间 + 命中价格。用户可选择: 1) "标记已处理" → 规则保持 enabled 但清除 triggered 状态 (下次命中再触发), 2) "关闭规则" → `enabled=false`。同一规则 5 分钟内不重复触发 (防抖)。 — **Reversibility:** reversible

### UI 布局
- **D-04:** 在监控中心页面新增 "客户端规则" tab/section, 与服务端规则列表并列但视觉分隔 (标题标注 "客户端规则 (浏览器本地)" + 图标区分)。规则编辑器: 标的输入 + 规则类型选择 (涨跌幅/绝对价格) + 操作符 + 阈值 + 启用开关。命中列表: 显示命中规则 + 命中时间 + 命中价格 + 操作按钮。 — **Reversibility:** reversible — UI 组件可删除

### Notification API 权限
- **D-05:** 首次创建客户端规则时请求 Notification 权限 (`Notification.requestPermission()`)。权限被拒绝时降级为仅 toast + 声效 (不阻断)。设置页显示权限状态, 允许用户手动重新请求。 — **Reversibility:** reversible

### 与服务端规则共存
- **D-06:** 客户端规则与服务端规则完全独立: 服务端规则走后端 `quote_service._maybe_send_webhook` + 通知渠道 (feishu/telegram/sct), 客户端规则走浏览器评估 + Notification API。两者不共享数据、不互相调用。UI 上明确标注来源: 服务端规则标注 "服务端" badge, 客户端规则标注 "客户端" badge。 — **Reversibility:** reversible

### Claude's Discretion
- 防抖时间窗口 (5 分钟, 可配置)
- toast 显示时长
- Notification 通知标题/正文格式
- 规则列表排序方式
- 是否支持多条规则批量操作

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### WebSocket 行情流
- `frontend/src/lib/useWsStream.ts` §`subscribe()` — 频道订阅 API, `subscribe('quotes', handler)` 接收 `{data, type}` 回调
- `frontend/src/lib/useWsStream.ts` §`STATIC_CHANNEL_EVENTS` — `quotes` 频道路由 `quotes_updated` + `strategy_results_updated`

### localStorage 存储模式
- `frontend/src/lib/storage.ts` — `makeStorage(key, fallback)` 工厂函数, 类型安全 localStorage 持久化
- `frontend/src/lib/storage.ts` — 现有 storage 对象 (各 key 注册)

### 现有通知模式
- `frontend/src/components/AlertToast.tsx` — 告警 toast 容器, `playNotificationSound()` + `speakAlerts()`
- `frontend/src/lib/notificationSound.ts` — `playNotificationSound()` 声效播放 (localStorage 配置开关)
- `frontend/src/components/Toast.tsx` — `toast()` 全局 toast API

### 监控规则 UI
- `frontend/src/components/monitor/RuleEditor.tsx` — 服务端规则编辑器 (参考 UI 布局, 不复用逻辑)
- `frontend/src/pages/Monitoring.tsx` — 监控中心页面 (客户端规则 tab 挂载点)

### 项目规范
- `CONTRIBUTING.md` — 项目架构、前端插槽、测试矩阵
- `docs/secondary-development.md` — 可替换策略与扩展注册

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `subscribe('quotes', handler)` (useWsStream.ts): 已有的 WS quotes 频道订阅, handler 收到 `quotes_updated` 消息时评估规则
- `storage.ts` `makeStorage()`: localStorage 持久化工厂, 新增 `client_rules` key 即可
- `toast()` (Toast.tsx): 全局 toast 通知 API, 直接调用
- `playNotificationSound()` (notificationSound.ts): 声效播放, 直接调用
- `AlertToast.tsx`: 现有告警 toast 模式参考

### Established Patterns
- **localStorage 存储模式:** `storage.ts` 的 `makeStorage(key, fallback)` → `{get, set}` 接口, JSON 序列化
- **WS 订阅模式:** `subscribe(channel, handler) → unsubscribe()`, handler 签名 `(data, type)`
- **规则编辑器 UI:** `RuleEditor.tsx` 的表单布局 (标的 + 类型 + 操作符 + 阈值)
- **Notification API:** 浏览器原生 `Notification.requestPermission()` + `new Notification(title, options)`

### Integration Points
- `useWsStream.subscribe('quotes', ...)` — 行情 tick 订阅
- `storage.ts` — 新增 `client_rules` storage key
- `Monitoring.tsx` — 客户端规则 tab 挂载点
- `Layout.tsx` — 已有的 toast/通知容器 (AlertToastContainer)

</code_context>

<specifics>
## Specific Ideas

- 规则类型简化为两种: `pct` (涨跌幅 %) 和 `price` (绝对价格), 操作符 `> >= < <=`
- quotes_updated 消息的 data 结构: `{symbols: [{symbol, price, pct_change, ...}], ...}` — 需要确认实际字段名
- 防抖: 同一规则 5 分钟内不重复触发, 但用户可手动 "重置" 后立即重新评估
- Notification 权限被拒绝时静默降级, 不报错

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 57-客户端实时规则引擎*
*Context gathered: 2026-08-22*
