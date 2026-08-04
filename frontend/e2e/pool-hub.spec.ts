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

const zeroHitHubPayload = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  strategies: [
    ...hubPayload.strategies,
    { id: 'auction_early_star', name: '早盘之星', total: 0, rows: [] as typeof doublyHitRow[] },
  ],
  resonance_count: 1,
}

const noResonanceHubPayload = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 1, rows: [singleHitRow] },
  ],
  resonance_count: 0,
}

/** 已知策略全集 (preset 列表) — 不在 hub 载荷里的策略渲染 数据不可用 */
const knownStrategies = [
  { id: 'auction_bullish', name: '竞价多头', description: '竞价高开强度', source: 'builtin' },
  { id: 'auction_preopen_quant', name: '盘前强势量化', description: '盘前量化强度', source: 'builtin' },
  { id: 'auction_early_star', name: '早盘之星', description: '早盘强势', source: 'builtin' },
  { id: 'auction_momentum', name: '动量增强', description: '开盘动量', source: 'builtin' },
]

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
  test('concept filter projects client-side over the loaded payload with 筛选后/共 footer', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    let hubRequests = 0
    page.on('request', r => {
      if (new URL(r.url()).pathname === '/api/pool/hub') hubRequests += 1
    })
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 输入 新能源 → 仅 300750 (新能源) 保留, 600519 (白酒) 消失; 不发第二次 fetch
    await page.getByLabel('概念筛选').fill('新能源')
    await expect(page.getByText(/筛选后 1 只 \/ 共 2 只/)).toBeVisible()
    await expect(page.getByText('600519', { exact: true })).toHaveCount(0)
    await expect(page.getByText('300750', { exact: true })).toBeVisible()
    expect(hubRequests).toBe(1)

    // 清除筛选 → 恢复全量
    await page.getByRole('button', { name: '清除筛选' }).click()
    await expect(page.getByText(/共 2 只/)).toBeVisible()
    await expect(page.getByText('600519', { exact: true })).toBeVisible()
    expect(hubRequests).toBe(1)
  })

  test('交叉共振 row renders the badge and legend; single-hit row omits it', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')

    // 默认选中 竞价多头 (total=2): 300750 被 2 个策略命中 → 徽标 + legend
    await expect(page.getByText(/交叉共振 · 2 策略/)).toBeVisible()
    await expect(page.getByText('交叉共振：被 ≥2 个竞价策略同时命中的个股')).toBeVisible()
    // 单命中行 600519 不渲染徽标
    await expect(page.getByText('交叉共振 · 2 策略')).toHaveCount(1)
  })

  test('concept filter with no match renders 无符合「{概念}」的个股 with 清除筛选', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')
    await page.getByLabel('概念筛选').fill('不存在的概念')

    await expect(page.getByText('无符合「不存在的概念」的个股')).toBeVisible()
    await expect(page.getByText('试试切换其他概念或清除筛选。')).toBeVisible()
    await expect(page.getByRole('button', { name: '清除筛选' }).first()).toBeVisible()
  })

  test('zero-hit strategy drills to 当日无命中 empty state', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, zeroHitHubPayload))
    await page.route('**/api/screener/strategies**', route => json(route, { presets: knownStrategies }))

    await page.goto('/pool-hub')

    const earlyStar = page.getByRole('button', { name: /早盘之星/ })
    await expect(earlyStar).toBeVisible()
    await expect(earlyStar.getByText('当日无命中')).toBeVisible()
    await earlyStar.click()
    await expect(page.getByText('早盘之星 · 股池明细')).toBeVisible()
    const drill = page.getByRole('region', { name: /早盘之星 · 股池明细/ })
    await expect(drill.getByText('该策略当日无命中个股。')).toBeVisible()
  })

  test('strategy absent from the payload renders 数据不可用 with no click', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/screener/strategies**', route => json(route, { presets: knownStrategies }))

    await page.goto('/pool-hub')

    const unavailableCard = page.getByRole('button', { name: /动量增强/ })
    await expect(unavailableCard.getByText('数据不可用')).toBeVisible()
    await expect(unavailableCard).toBeDisabled()
    await expect(unavailableCard.locator('..')).toHaveAttribute('title', '该策略无 2026-08-04 的持久化结果')

    // 其余卡片保持可用, 默认选中策略仍是 竞价多头
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeEnabled()
    await expect(page.getByText('竞价多头 · 股池明细')).toBeVisible()
  })

  test('no cross resonance renders 今日无交叉共振 footnote', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, noResonanceHubPayload))

    await page.goto('/pool-hub')

    await expect(page.getByText(/今日无交叉共振/)).toBeVisible()
    await expect(page.getByText('暂无个股被 ≥2 个竞价策略同时命中。')).toBeVisible()
    await expect(page.getByText(/交叉共振 · \d+ 策略/)).toHaveCount(0)
  })
})
