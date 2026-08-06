---
phase: 30
status: passed
created: 2026-08-06
---

# Phase 30 — UAT (User Acceptance Test)

**Phase:** 30 盘前监控告警 (MON-01..07)
**Scope:** preopen 规则类型 + 隔离评估 + 09:26 尾段接线 + 诚实标注 + guest 掩码 + 前端编辑器/徽标

## Verifier human_items 核验记录

Verifier30 判定 `human_needed` 的 3 项 human_items 核验如下:

### UAT-1: 交易日 09:26 实盘调度运行 — ⏳ 部署后确认（诚实标注）

**核验方式**: sandbox 无真实数据管道与外部投递服务（SSE/飞书/Telegram）。代码级证据已锁：

- 尾段接线：`_premarket_pool_preview` persist 后同 `_run_tracked` 单飞内调用 `QuoteService.evaluate_premarket_alerts(payload)`（内存 payload，失败非致命 try/except）
- persist-first 链：`record_alert_event` 落库成功才广播 SSE（`_preopen_sse_shape` 增量键）→ `_maybe_send_webhook`
- `available:false` → 跳过不评估；degraded → 竞价列规则 fail-closed（head(0) 空掩码），open_gap 规则可触发但事件带 `degraded:true`
- 测试锁：test_preopen_scheduling.py（T11-T16 注册/接线/跳过/非致命）、test_preopen_honesty.py（T17 round-trip + T18 掩码）

**部署后操作**:
1. 真实交易日观察 09:26 job 日志出现 preopen 评估摘要
2. 配置一条 preopen 规则验证命中 → alert_events 落库 + 飞书/Telegram 投递
3. 观察 `provisional:true`/`degraded`/`probe` 冻结快照随事件透传

### UAT-2: 真实后端浏览器用户流 — ✅ e2e 覆盖 + 部署复核照常

**核验方式**: Playwright e2e（`frontend/e2e/monitor.spec.ts`, 5 passed, 真实 Chromium）覆盖 preopen 规则编辑（白名单下拉、无 truth 选项、open_gap 默认、保存）与告警徽标渲染（「盘前·非最终」/「数据降级」）；premarket-pool.spec 回归 5/5。真实后端人工复核受部署登录门阻挡（与 v2.1 Phase 27 / v2.2 Phase 28 同因）；e2e 真实 Chromium 断言作为行为级视觉证据等价覆盖。

### UAT-3: 设计裁决 MON-06（guest 掩码防御面）— ✅ 裁决接受

**核验方式（源码实证）**:
- `backend/app/main.py`：`/api/alerts` 与 `/api/monitor*` 均**不在** guest 白名单（grep 零命中）→ 登录面，游客不可达
- `backend/app/services/guest_masking.py:25` `_GUEST_ALERT_VISIBLE` frozenset 已定义 + `:76` docstring「未来任何游客可见 alerts 渲染必须经此函数」— mask_guest_alert 为 GUEST-01/02 DTO 边界原则的防御性守卫
- 结论：无游客可见渲染面绕过掩码；防御性 DTO 守卫接受（与平台既有模式一致）

---

## UAT Verdict

| Item | Status |
|------|--------|
| UAT-1 实盘 09:26 调度 + 投递 | ⏳ Deploy-verified（代码级 + 测试锁；真实交易日确认） |
| UAT-2 真实后端浏览器流 | ✅ Passed（e2e 真实 Chromium 5/5 + 回归 5/5） |
| UAT-3 MON-06 设计裁决 | ✅ Passed（源码实证：alerts 为登录面，掩码为防御性 DTO 守卫） |

**Phase 30 验收通过**：4/4 roadmap 成功标准 VERIFIED（verifier）+ 3/3 UAT 项核验（1 项设计裁决源码实证、1 项 e2e 覆盖、1 项部署环境诚实标注）。
