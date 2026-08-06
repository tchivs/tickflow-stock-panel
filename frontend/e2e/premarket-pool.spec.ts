import type { Page, Route } from '@playwright/test'
import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

// ===== 共享 mock 载荷 (独立 spec — 复制 pool-hub.spec.ts 常量/helpers, 不 import 跨文件耦合) =====
const HUB_UPDATED_AT = 1_754_310_000

const premarketRow = {
  symbol: '300750.SZ', code: '300750', name: '宁德时代', open_gap: 0.02, change_pct: 0.01,
  concept_board: [], hit_factors: ['open_gap'], cross_resonance: false,
}
const hubSecondRow = {
  symbol: '600519.SH', code: '600519', name: '贵州茅台', open_gap: 0.0105, change_pct: -0.0012,
  concept_board: ['白酒'], hit_factors: ['open_gap'], cross_resonance: false,
}

/** 本地时区今天的 ISO 串 — 用于「查看今日」盘前判定 (与应用 isToday 同机同 TZ) */
function localTodayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** dates 白名单不含今日 (盘前预览场景: 今日 EOD 快照未生成 → hasTodayEod=false) */
const DATES_NO_TODAY = {
  dates: ['2026-08-04', '2026-08-01', '2026-07-31'],
  count: 3,
  latest: '2026-08-04',
}

/** dates 白名单含今日 (15:35 EOD 后: today ∈ dates → hasTodayEod=true → 回退 hub) */
const DATES_WITH_TODAY = {
  dates: [localTodayISO(), '2026-08-04', '2026-08-01'],
  count: 3,
  latest: localTodayISO(),
}

/** 盘前预览有数据 (27-01 端点契约: available:true + window:'pre_open' + provisional + auction_columns) */
const premarketPayload = {
  as_of: localTodayISO(),
  available: true,
  window: 'pre_open',
  provisional: true,
  degraded: false,
  updated_at: '2026-08-06T09:26:00+08:00',
  mode: 'vip',
  strategies: [
    { id: 'auction_allround', name: '竞价全面', total: 1, rows: [premarketRow] },
  ],
  resonance_count: 0,
  auction_columns: { real: [], derived: ['open_gap'] },
}

/** 降级预览 (27-01: probe 非 available → degraded:true + real:[] — 前端强制诚实警告分支) */
const premarketDegradedPayload = {
  ...premarketPayload,
  degraded: true,
  probe: {
    status: 'not_configured', source: null, probed_at: null,
    window: '09:15-09:25', fallback: 'open_gap', detail: '尚未配置竞价数据源, 盘前预览仅派生列',
  },
  auction_columns: { real: [], derived: ['open_gap'] },
}

/** 诚实空态 (200 语义, 非 404, 非零池伪装): 今日预览尚未生成 */
const premarketEmptyPayload = {
  as_of: localTodayISO(),
  available: false,
  degraded: true,
  window: 'pre_open',
  strategies: [],
  resonance_count: 0,
  updated_at: null,
  probe: null,
  auction_columns: { real: [], derived: [] },
  mode: 'vip',
}

/** hub 流夹具 (15:35 回退断言): 策略卡 竞价全面 渲染, 无盘前标注 */
const hubPayload = {
  as_of: localTodayISO(),
  updated_at: HUB_UPDATED_AT,
  mode: 'vip',
  strategies: [
    { id: 'auction_allround', name: '竞价全面', total: 2, rows: [premarketRow, hubSecondRow] },
  ],
  resonance_count: 0,
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

/**
 * 应用外壳 fixture — 复制 pool-hub.spec.ts installShell 全文 (独立 spec, 不 import 跨文件耦合):
 * Layout 预取与全局轮询都命中 mock, 未显式覆盖的 /api 请求大声失败 (暴露意外依赖)。
 * PM-04 默认路由在 installShell 内注册 (后注册优先), 各用例以更精确 route 覆盖。
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
  // PM-04 盘前预览: dates 白名单 (EOD 快照日, 盘前日绝不枚举) + hub 回退流 + 盘前预览默认空态
  await page.route('**/api/pool/dates**', route => json(route, DATES_NO_TODAY))
  await page.route('**/api/pool/hub**', route => json(route, hubPayload))
  await page.route('**/api/pool/premarket**', route => json(route, premarketEmptyPayload))
  await page.route('**/api/data/auction-probe**', route => json(route, {
    status: 'not_configured', source: null, probed_at: null,
    window: '09:15-09:25', fallback: 'open_gap', detail: '尚未配置竞价数据源',
  }))
  await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))
}

test.describe('Phase 27 premarket pool', () => {
  test('PM-04: 盘前预览 + 窗口标注 (available:true, 今日 EOD 未生成)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/premarket**', route => json(route, premarketPayload))
    await page.route('**/api/pool/dates**', route => json(route, DATES_NO_TODAY))

    await page.goto('/pool-hub')

    // 窗口标注「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」(诚实标注: 预览 ≠ 收盘定稿)
    await expect(page.getByText('盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿')).toBeVisible()
    // 预览策略卡 (payload 为 hub 同形状 → 复用既有渲染)
    await expect(page.getByRole('button', { name: /竞价全面/ })).toBeVisible()
    // 空态/零池文案不出现
    await expect(page.getByRole('heading', { name: '今日盘前预览尚未生成' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: '该日期无股池快照' })).toHaveCount(0)
  })

  test('PM-04: 诚实空态 (available:false, 200 语义非 404 非零池伪装)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/premarket**', route => json(route, premarketEmptyPayload))
    await page.route('**/api/pool/dates**', route => json(route, DATES_NO_TODAY))

    await page.goto('/pool-hub')

    // 「今日盘前预览尚未生成」空态可见 (盘前空态优先于 hub 流, 绝不伪装零池)
    await expect(page.getByRole('heading', { name: '今日盘前预览尚未生成' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '当日无股池结果' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /当日池/ })).toHaveCount(0)
  })

  test('PM-04: degraded 徽标诚实 (绝不渲染「竞价数据可用」)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/premarket**', route => json(route, premarketDegradedPayload))
    await page.route('**/api/pool/dates**', route => json(route, DATES_NO_TODAY))
    await page.route('**/api/data/auction-probe**', route => json(route, {
      status: 'not_configured', source: null, probed_at: null,
      window: '09:15-09:25', fallback: 'open_gap', detail: '尚未配置竞价数据源',
    }))

    await page.goto('/pool-hub')

    // 页面标注「仅派生列 · 竞价数据源未配置」(degraded 透传)
    await expect(page.getByText('仅派生列 · 竞价数据源未配置')).toBeVisible()
    // 页面/徽标绝不出现「竞价数据可用」
    await expect(page.getByText('竞价数据可用')).toHaveCount(0)
  })

  test('PM-04: 15:35 回退 hub (今日 ∈ dates → 无盘前标注)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/premarket**', route => json(route, premarketPayload))
    await page.route('**/api/pool/dates**', route => json(route, DATES_WITH_TODAY))
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')

    // hub 流策略卡可见 (15:35 EOD 后回退既有 /api/pool/hub 流)
    await expect(page.getByRole('button', { name: /竞价全面/ })).toBeVisible()
    // 无盘前标注
    await expect(page.getByText('盘前预览 · 非收盘定稿')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: '今日盘前预览尚未生成' })).toHaveCount(0)
  })

  test('PM-04: DateNavigator EOD-only (dates 白名单, 无盘前伪日)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/premarket**', route => json(route, premarketPayload))
    await page.route('**/api/pool/dates**', route => json(route, DATES_WITH_TODAY))
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')

    // DateNavigator 下拉只列 EOD 白名单日期 (含今日, 无盘前伪日 — 盘前预览绝不枚举额外日期项)
    const select = page.getByRole('combobox', { name: '选择日期' })
    const options = select.locator('option')
    await expect(options).toHaveCount(3)
    expect(await options.allTextContents()).toEqual([localTodayISO(), '2026-08-04', '2026-08-01'])
    // 步进: 今日 ∈ dates (idx=0) → › (更近) disabled, ‹ (更早) enabled
    await expect(page.getByRole('button', { name: '上一个交易日' })).toBeEnabled()
    await expect(page.getByRole('button', { name: '下一个交易日' })).toBeDisabled()
  })
})
