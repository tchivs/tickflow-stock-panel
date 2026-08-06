import type { Page, Route } from '@playwright/test'
import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

// ===== 共享 mock 载荷 (独立 spec — 复制 premarket-pool.spec.ts 常量/helpers, 不 import 跨文件耦合) =====

/** 盘中 EOD 阈值字段 — preopen 白名单之外 (断言字段下拉不含 EOD 字段用) */
const EOD_THRESHOLD_FIELDS = [
  { key: 'close', label: '现价' },
  { key: 'change_pct', label: '涨跌幅' },
  { key: 'vol_ratio_5d', label: '5日量比' },
  { key: 'amount', label: '成交额' },
]

/** preopen 竞价白名单 (30-02 /options 外露: PREOPEN_ALLOWED_FIELDS + ENRICHED_COLUMNS 中文标签) */
const PREOPEN_THRESHOLD_FIELDS = [
  { key: 'open_gap', label: '开盘涨幅' },
  { key: 'auction_volume', label: '竞价量' },
  { key: 'auction_amount', label: '竞价金额' },
  { key: 'auction_volume_ratio', label: '竞价量比' },
  { key: 'auction_unmatched_amount', label: '派生未匹配金额' },
]

/** 30-02 /api/monitor-rules/options 契约 (types 含 preopen + preopen_threshold_fields) */
const monitorOptions = {
  threshold_fields: EOD_THRESHOLD_FIELDS,
  builtin_signals: [{ key: 'signal_volume_surge', label: '放量异动' }],
  custom_signals: [],
  operators: ['>', '>=', '<', '<=', '==', '!='],
  types: [
    { key: 'signal', label: '个股信号监控' },
    { key: 'price', label: '价格监控' },
    { key: 'market', label: '市场异动监控' },
    { key: 'strategy', label: '策略监控' },
    { key: 'position', label: '持仓监控' },
    { key: 'preopen', label: '盘前异动' },
  ],
  scopes: [{ key: 'symbols', label: '指定股票' }, { key: 'all', label: '全市场' }],
  logics: [{ key: 'and', label: '且' }, { key: 'or', label: '或' }],
  severities: [{ key: 'info', label: '普通' }, { key: 'warn', label: '警告' }, { key: 'critical', label: '重要' }],
  directions: [{ key: 'entry', label: '买入' }, { key: 'exit', label: '卖出' }],
  preopen_threshold_fields: PREOPEN_THRESHOLD_FIELDS,
}

/** 旧 /options 载荷 (30-02 之前: 无 preopen_threshold_fields 键) — 兼容用例 */
function legacyMonitorOptions() {
  const o: Record<string, unknown> = { ...monitorOptions }
  delete o.preopen_threshold_fields
  return o
}

// ── 告警渲染载荷 (30-02 SSE dict 增量键: window/provisional/degraded/strategy_ids/preopen_metrics) ──
const preopenAlertPayload = {
  id: 'ev_preopen_1',
  ts: 1754316000000,
  occurred_at: '2026-08-06T09:26:05+08:00',
  rule_id: 'mr_preopen_gap5',
  rule_name: '盘前高开预警',
  source: 'preopen',
  type: 'preopen',
  symbol: '300750.SZ',
  name: '宁德时代',
  message: '盘前 open_gap>=0.05',
  price: null,
  change_pct: null,
  severity: 'warn',
  provisional: true,
  degraded: true,
  window: 'pre_open',
  strategy_ids: ['auction_allround'],
  preopen_metrics: { open_gap: 0.051, auction_volume_ratio: 3.2 },
  conditions: [{ field: 'open_gap', op: '>=', value: 0.05 }],
  logic: 'and',
}

/** 非降级盘前事件 (degraded=false — provisional 恒真) */
const preopenAlertNotDegraded = {
  ...preopenAlertPayload,
  id: 'ev_preopen_2',
  degraded: false,
}

/** 盘中 signal 事件 (无增量键 — 兼容用例: 旧载荷零回归) */
const signalAlertPayload = {
  id: 'ev_signal_1',
  ts: 1754312400000,
  occurred_at: '2026-08-06T14:02:00+08:00',
  rule_id: 'mr_signal_1',
  rule_name: '个股信号监控 · 300750.SZ',
  source: 'signal',
  type: 'signal',
  symbol: '300750.SZ',
  name: '宁德时代',
  message: '现价低于 RSI',
  price: 189.5,
  change_pct: 0.012,
  severity: 'info',
  signals: ['signal_volume_surge'],
  conditions: [{ field: 'rsi_14', op: '<', value: 30 }],
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

/**
 * 应用外壳 fixture — 复制 premarket-pool.spec.ts installShell (独立 spec, 不 import 跨文件耦合):
 * Layout 预取与全局轮询都命中 mock, 未显式覆盖的 /api 请求大声失败 (暴露意外依赖)。
 * MON-07: monitor-rules/options + monitor-rules 空态在 installShell 内注册, 用例以更精确 route 覆盖。
 */
async function installShell(page: Page) {
  await page.route('**/api/**', unhandled)
  await page.route('**/api/settings', route => json(route, { onboarding_completed: true, theme: 'dark' }))
  await page.route('**/api/capabilities', route => json(route, { label: 'Free+', capabilities: {} }))
  await page.route('**/api/data/version', route => json(route, { version: 'phase18-browser' }))
  await page.route('**/api/settings/preferences', route => json(route, {
    realtime_quotes_enabled: false,
    indices_nav_pinned: false,
    minute_sync_enabled: false,
    minute_sync_days: 5,
    pipeline_pull_a_share: true,
    pipeline_pull_etf: true,
    pipeline_pull_index: true,
    pipeline_index_symbols: '',
    pipeline_schedule: { hour: 15, minute: 30 },
    instruments_schedule: { hour: 9, minute: 10 },
  }))
  await page.route('**/api/settings/data-sources', route => json(route, { builtin: [], plugins: [], custom: [], errors: [], config_dir: 'deployment-config' }))
  await page.route('**/api/intraday/status', route => json(route, { enabled: false, running: false, interval_s: 5, symbol_count: 0, quote_age_ms: null, is_trading_hours: false, last_fetch_ms: null }))
  await page.route('**/api/analysis-menus', route => json(route, { items: [] }))
  await page.route('**/api/pipeline/jobs**', route => json(route, { active_id: null, jobs: [] }))
  await page.route('**/api/intraday/indices**', route => json(route, { rows: [], count: 0 }))
  await page.route('**/api/alerts**', route => json(route, { alerts: [], total: 0 }))
  await page.route('**/api/data/status', route => json(route, {
    daily: null, enriched: null, index_daily: null, index_enriched: null, index_instruments: null,
    etf_daily: null, etf_enriched: null, etf_instruments: null, minute: null, adj_factor: null,
    instruments: null, financials: null, storage: {},
  }))
  await page.route('**/api/screener/strategies**', route => json(route, { presets: [] }))
  // MON-07 默认空态: 规则列表空; options 契约 (后注册优先, 用例可覆盖)
  await page.route('**/api/monitor-rules**', route => json(route, { rules: [] }))
  await page.route('**/api/monitor-rules/options', route => json(route, monitorOptions))
  await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))
}

test.describe('Phase 30 preopen monitor (MON-07 frontend)', () => {
  test('MON-07: 规则编辑器 preopen 类型 — 白名单字段下拉 + 无 truth + open_gap 默认 + 保存载荷', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)

    type SavedRulePayload = { type?: string; conditions?: Array<{ field?: string }> }
    let savedBody: SavedRulePayload | null = null
    await page.route('**/api/monitor-rules', async route => {
      const req = route.request()
      if (req.method() === 'POST') {
        savedBody = req.postDataJSON()
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, rule: savedBody }) })
      } else {
        await json(route, { rules: [] })
      }
    })

    await page.goto('/monitor')
    await page.locator('button[title="新建规则"]').click()

    // 类型下拉出现「盘前异动」(30-02 /options types 契约被消费)
    await page.getByLabel('监控类型').selectOption('preopen')

    // preopen: 「信号条件」按钮与信号点选区不渲染
    await expect(page.getByRole('button', { name: '信号条件' })).toHaveCount(0)
    await expect(page.getByText('信号条件 (点选)')).toHaveCount(0)

    // 点「阈值条件」→ 默认字段 open_gap, 字段下拉为 5 白名单 label (不含 EOD 字段)
    await page.getByRole('button', { name: '阈值条件' }).click()
    const fieldSelect = page.locator('div.flex.items-center.gap-1\\.5 select').first()
    await expect(fieldSelect).toHaveValue('open_gap')
    expect(await fieldSelect.locator('option').allTextContents()).toEqual([
      '开盘涨幅', '竞价量', '竞价金额', '竞价量比', '派生未匹配金额',
    ])

    // 保存 → POST /api/monitor-rules 载荷 type=preopen + conditions[0].field=open_gap
    await page.locator('select.h-9.w-32').selectOption('all')
    await page.getByRole('button', { name: '保存规则' }).click()
    await expect(page.getByText('新建监控规则')).toHaveCount(0) // 对话框关闭 = 保存成功
    expect(savedBody).not.toBeNull()
    expect(savedBody?.type).toBe('preopen')
    expect(savedBody?.conditions?.[0]?.field).toBe('open_gap')
  })

  test('MON-07: 兼容 — 旧 /options 载荷 (无 preopen_threshold_fields) 零崩溃 + signal 路径 truth 回归', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/monitor-rules/options', route => json(route, legacyMonitorOptions()))

    await page.goto('/monitor')
    await page.locator('button[title="新建规则"]').click()
    await page.getByLabel('监控类型').selectOption('preopen')

    // preopen 仍可渲染 (零崩溃): 无 truth 按钮; 字段下拉回退空数组 (旧载荷无 preopen_threshold_fields)
    await expect(page.getByRole('button', { name: '信号条件' })).toHaveCount(0)
    await page.getByRole('button', { name: '阈值条件' }).click()
    const fieldSelect = page.locator('div.flex.items-center.gap-1\\.5 select').first()
    await expect(fieldSelect.locator('option')).toHaveCount(0)

    // signal 类型回归: truth 信号点选仍可用 (非 preopen 路径零回归)
    await page.getByLabel('监控类型').selectOption('signal')
    await expect(page.getByRole('button', { name: '信号条件' })).toBeVisible()
  })

  test('MON-07: preopen 告警渲染 — provisional/degraded 徽标 + 无价格/涨跌幅 chip', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/alerts**', route => json(route, { alerts: [preopenAlertPayload], total: 1 }))

    await page.goto('/monitor')

    // 源徽标: rule_name 优先 (「盘前高开预警」; TYPE_LABEL 回退 '盘前')
    await expect(page.getByText('盘前高开预警')).toBeVisible()
    // provisional + degraded 徽标
    await expect(page.getByText('盘前·非最终')).toBeVisible()
    await expect(page.getByText('数据降级')).toBeVisible()
    // 命中条件行 (渲染器字形: '>=' 非 '≥')
    await expect(page.getByText('open_gap>=0.05')).toBeVisible()
    // price/change_pct 恒 null → 无价格/涨跌幅 chip (fmtPrice/fmtPct 输出不出现)
    await expect(page.getByText('189.50')).toHaveCount(0)
    await expect(page.getByText('+1.20%')).toHaveCount(0)
  })

  test('MON-07: preopen 非降级事件 — 「数据降级」不出现, provisional 恒标注', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/alerts**', route => json(route, { alerts: [preopenAlertNotDegraded], total: 1 }))

    await page.goto('/monitor')

    await expect(page.getByText('盘前·非最终')).toBeVisible()
    await expect(page.getByText('数据降级')).toHaveCount(0)
  })

  test('MON-07: 兼容 — signal 事件 (无增量键) 渲染零回归', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/alerts**', route => json(route, { alerts: [signalAlertPayload], total: 1 }))

    await page.goto('/monitor')

    // 无盘前徽标
    await expect(page.getByText('盘前·非最终')).toHaveCount(0)
    await expect(page.getByText('数据降级')).toHaveCount(0)
    // 源徽标 (rule_name 切片) + 价格/涨跌幅 chip 正常渲染 (旧载荷零回归)
    await expect(page.getByText('300750.SZ').first()).toBeVisible()
    // 价格同时出现在头部 price chip 与详情行「现价」 — 任一可见即渲染正常
    await expect(page.getByText('189.50').first()).toBeVisible()
    await expect(page.getByText('+1.20%')).toBeVisible()
    // 命中条件行 (cnSignal: rsi_14 → RSI14)
    await expect(page.getByText('RSI14<30')).toBeVisible()
  })
})
