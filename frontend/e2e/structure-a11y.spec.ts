import { expect, test, type Page, type Route } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

const json = (route: Route, body: unknown) =>
  route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

async function installShell(page: Page) {
  await page.route('**/api/**', unhandled)
  await page.route('**/api/settings', route => json(route, { onboarding_completed: true, theme: 'dark' }))
  await page.route('**/api/capabilities', route => json(route, { label: 'Free+', capabilities: {} }))
  await page.route('**/api/data/version', route => json(route, { version: 'phase18-browser' }))
  await page.route('**/api/settings/preferences', route => json(route, {
    realtime_quotes_enabled: false, indices_nav_pinned: false, minute_sync_enabled: false,
    minute_sync_days: 5, pipeline_pull_a_share: true, pipeline_pull_etf: true, pipeline_pull_index: true,
    pipeline_index_symbols: '', pipeline_schedule: { hour: 15, minute: 30 },
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
  await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))
}

type Heading = { level: number; text: string }

function assertNoLevelSkips(headings: Heading[]) {
  for (let i = 1; i < headings.length; i++) {
    const prev = headings[i - 1]
    const cur = headings[i]
    if (cur.level > prev.level) {
      expect(cur.level - prev.level, `heading 跳级: h${prev.level}「${prev.text}」→ h${cur.level}「${cur.text}」`).toBeLessThanOrEqual(1)
    }
  }
}

async function assertPageStructure(page: Page, path: string) {
  await page.goto(path)
  await expect(page.locator('main#main-content')).toBeVisible()
  // 等待页面组件真正挂载（vite dev 按需编译 chunk + query 完成），随后断言结构
  await page.getByRole('heading', { level: 1 }).first().waitFor({ timeout: 20_000 })
  const headings = await page.locator('h1,h2,h3,h4,h5,h6').evaluateAll(nodes =>
    nodes.map(n => ({ level: Number(n.tagName[1]), text: (n.textContent ?? '').trim().slice(0, 40) })),
  )
  expect(headings.filter(h => h.level === 1), '每页必须恰好一个 h1').toHaveLength(1)
  assertNoLevelSkips(headings)
  // 无 label 的 nav landmark 全页至多一个（其余必须可辨识）
  const navs = await page.locator('nav').evaluateAll(ns =>
    ns.map(n => ({ name: n.getAttribute('aria-label') ?? '', id: n.getAttribute('id') ?? '' })),
  )
  const unlabeled = navs.filter(n => !n.name)
  expect(unlabeled.length, `未命名 nav landmark: ${JSON.stringify(unlabeled)}`).toBeLessThanOrEqual(1)
}

test.describe('页面结构可访问性', () => {
  test('Dashboard: 唯一 h1 + heading 无跳级 + nav 可辨识', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only')
    await installShell(page)
    await assertPageStructure(page, '/')
  })

  test('Indices: 唯一 h1 + heading 无跳级', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only')
    await installShell(page)
    await assertPageStructure(page, '/indices')
  })

  test('Settings: 分类 nav 有可访问名（本轮修复）', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only')
    await installShell(page)
    await page.goto('/settings')
    const settingsNav = page.getByRole('navigation', { name: '设置分类' })
    await expect(settingsNav).toBeVisible()
    await assertPageStructure(page, '/settings')
  })
})
