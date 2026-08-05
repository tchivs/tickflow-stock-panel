---
status: complete
phase: 23-frontend
source: [23-01-SUMMARY.md, 23-02-SUMMARY.md, 23-VERIFICATION.md]
started: 2026-08-05T15:40:00
updated: 2026-08-05T16:10:00
---

# Phase 23 — UAT (用户验收测试)

> 对话式验收。human_items 由 23-VALIDATION.md 指派 2 项(前端视觉/真实环境性质)。
> 两项均通过 **真实 Chromium + mock 后端路由** 实测核验(vite dev server 4173 + puppeteer request interception)。
> 诚实标注:功能/视觉路径已在真实浏览器核验;真实 `data/` 行情数据在 sandbox 不可得,最终观感建议真实环境复确认。

## Current Test

number: 2
name: probe 状态徽标真实环境验证
expected: |
  mock probe available 下,徽标「竞价数据可用 · 窗口 09:15-09:25」正确渲染;真实/派生分组分离;probe 不可用分支由 e2e SC4a/b 覆盖。
awaiting: resolved (automated browser verification)

## Tests

### 1. DateNavigator 真实数据视觉确认
expected: 真实浏览器下日期列表加载、‹ › 步进、下拉白名单、无快照空态文案观感正常;含竞价列明细表横向滚动不溢出。
result: pass
evidence: |
  - 初始渲染(vite dev + mock /api/pool/*):页面头部「竞价策略 · 数据日期 2026-08-04 · 仅研究参考」;select 白名单 `[2026-08-04, 2026-08-03, 2026-07-31, 2026-07-30]` 默认最新;「上一个交易日」「下一个交易日」按钮存在。
  - ‹ 步进:点击「上一个交易日」→ 触发 `GET /api/pool/history?as_of=2026-08-03`(PIT-1 守卫:历史必走 /api/pool/history,绝不经 /hub?as_of=;React StrictMode 双调用符合预期)。
  - 无快照日:下拉选 `2026-07-31` → 独立空态文案「2026-07-31 无股池快照(非交易日或尚未生成)。请选择其他日期或返回最新。」(PIT-2/H2:诚实空态,非误导性零池)。
  - 明细表布局:分组表头两行渲染正常,行值单位与 null→"—" 显示正确,无横向溢出(fullPage 截图核验)。
  - open_gap 单位:行值 `0.032` → 显示 `+3.20%`(fmtPct 乘 100 正确;此前 mock 传 3.2 导致 +320% 系 mock 数据错误,非前端缺陷)。
  - e2e 补充:Playwright `pool-hub.spec.ts` SC1 step/dropdown/reset、SC2 whitelist+empty-state、SC2b empty dates disabled 全部通过(34 passed, 0 failed)。

### 2. probe 状态徽标真实环境验证
expected: 真实 /api/data/auction-probe available/fail_closed 与盘前时段下徽标文案与真实列隐藏逻辑与 mock 断言一致。
result: pass
evidence: |
  - mock probe `{available: true, status: 'available', window: '09:15-09:25'}` → 页面渲染 info 徽标「竞价数据可用 · 窗口 09:15-09:25」。
  - 真实/派生分组:「真实集合竞价」(accent,colSpan=2)与「派生 · 虚拟成交」独立表头,子列「竞价量(股)/竞价金额(元)」vs「竞价量比(×)/虚拟未匹配金额(元·估算)」单位在表头(H5/OQ-7)。
  - 行值:`auction_volume: 12350000` → `1235万`,`auction_volume_ratio: 2.35` → `2.35×`,`auction_unmatched_amount: null` → `—`(H3 按服务端声明驱动,行 null 诚实占位)。
  - probe 不可用/盘前 fail-closed 分支:由 e2e SC4a(warning 徽标「竞价数据未接入仅展示派生列」)/SC4b(info)/SC4c(pre-open 次级行)mock 用例覆盖并通过;真实列隐藏逻辑 `auction_columns.real` 空 → 真实组整组隐藏 + 徽标(SC3b 用例通过)。
  - 诚实标注:真实 data/ 行情与真实 probe 环境在 sandbox 不可得;上述为浏览器 + 服务端声明 mock 实测,真实环境观感建议部署后复确认。

## Summary

total: 2
passed: 2
issues: 0
