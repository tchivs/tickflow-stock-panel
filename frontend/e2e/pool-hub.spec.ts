import type { Page, Route } from '@playwright/test'
import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

// ===== 共享 mock 载荷 =====
const HUB_AS_OF = '2026-08-04'
const HUB_UPDATED_AT = 1_754_310_000

/** 交叉共振行: 被 竞价多头 + 盘前强势量化 同时命中 (hit_factors ≥ 2) */
const doublyHitRow = {
  symbol: '300750.SZ', code: '300750', open_gap: 0.0234, change_pct: 0.0512,
  concept_board: ['新能源', '人工智能'], hit_factors: ['竞价多头', '盘前强势量化'], cross_resonance: true,
}
/** 单策略命中行: 仅 竞价多头 */
const singleHitRow = {
  symbol: '600519.SH', code: '600519', open_gap: 0.0105, change_pct: -0.0012,
  concept_board: ['白酒'], hit_factors: ['竞价多头'], cross_resonance: false,
}

const hubPayload = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 2, rows: [doublyHitRow, singleHitRow] },
    { id: 'auction_preopen_quant', name: '盘前强势量化', total: 1, rows: [doublyHitRow] },
  ],
  resonance_count: 1,
}

const emptyHubPayload = { as_of: HUB_AS_OF, updated_at: HUB_UPDATED_AT, strategies: [], resonance_count: 0 }

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

/**
 * 应用外壳 fixture: 让 Layout 预取与全局轮询都命中 mock,
 * 未显式覆盖的 /api 请求大声失败, 便于发现意外依赖。
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
}

test.describe('Phase 18 pool hub', () => {
  test('populated hub renders strategy cards and drill-down table from one as_of payload', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')

    await expect(page.getByRole('heading', { name: '股池' })).toBeVisible()
    await expect(page.getByText('竞价策略 · 数据日期 2026-08-04 · 仅研究参考')).toBeVisible()

    // 两张策略卡片 + 当日池数
    const bullishCard = page.getByRole('button', { name: /竞价多头/ })
    await expect(bullishCard).toBeVisible()
    await expect(bullishCard.getByText('当日池', { exact: false })).toBeVisible()
    await expect(page.getByRole('button', { name: /当日池 2 只/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /当日池 1 只/ })).toBeVisible()

    // 明细表: 五个列头 + 默认第一个策略 (竞价多头, total=2) 的 footer 共 2 只
    const table = page.getByRole('table')
    await expect(table).toBeVisible()
    for (const header of ['代码', '开盘涨幅', '涨跌幅', '概念板块', '关联因子']) {
      await expect(table.getByRole('columnheader', { name: header })).toBeVisible()
    }
    await expect(page.getByText(/共 2 只/)).toBeVisible()

    // 点击第二张卡片 → 明细切到 盘前强势量化 (total=1)
    await page.getByRole('button', { name: /盘前强势量化/ }).click()
    await expect(page.getByText(/盘前强势量化 · 股池明细/)).toBeVisible()
    await expect(page.getByText(/共 1 只/)).toBeVisible()

    // 研究参考声明
    await expect(page.getByText('本页面仅用于研究参考，不提供任何交易执行功能。')).toBeVisible()
  })

  test('empty hub renders 当日无股池结果 with the as_of hint', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, emptyHubPayload))

    await page.goto('/pool-hub')

    await expect(page.getByRole('heading', { name: '当日无股池结果' })).toBeVisible()
    await expect(page.getByText('截至 2026-08-04，竞价策略均无命中个股。请先在策略页运行竞价策略，或确认数据日期。')).toBeVisible()
    await expect(page.getByText('本页面仅用于研究参考，不提供任何交易执行功能。')).toBeVisible()
  })

  test('hub error renders the alert with 重试 action', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, { detail: '数据源不可用' }, 500))

    await page.goto('/pool-hub')

    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByText(/股池加载失败：数据源不可用。请检查数据源后重试。/)).toBeVisible()
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible()
  })

  test('hub loading renders 股池加载中… with status role and disables refresh', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', async route => {
      await new Promise(resolve => setTimeout(resolve, 500))
      await json(route, hubPayload)
    })

    await page.goto('/pool-hub')

    await expect(page.getByRole('status')).toBeVisible()
    await expect(page.getByText('股池加载中…')).toBeVisible()
    await expect(page.getByRole('button', { name: '刷新股池' })).toBeDisabled()

    // 延迟返回后进入 populated 状态
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()
  })
})
