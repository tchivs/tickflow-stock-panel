import type { Page, Route } from '@playwright/test'
import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

// ===== 共享 mock 载荷 =====

// /screener 钻取载荷 (B1 修订: 竞价历史钻取走 /screener 打开弹窗 —
// 点击 ScreenerTable 行情行 (ScreenerTable.tsx:173) → onPreview → StockPreviewDialog。
// /pool-hub 现已同样挂载 StockPreviewDialog (名称列点击), 但本夹具保留 /screener 路径)。
const screenerStrategy = {
  id: 'auction_bullish',
  name: '竞价多头',
  description: '竞价高开强度',
  source: 'builtin',
}
const screenerRow = {
  symbol: '300750.SZ', code: '300750', name: '宁德时代',
  open_gap: 0.0234, change_pct: 0.0512,
  concept_board: ['新能源'], hit_factors: ['竞价多头'], cross_resonance: false,
}
const screenerCachedPayload = {
  as_of: '2026-08-04',
  results: {
    auction_bullish: { id: 'auction_bullish', as_of: '2026-08-04', rows: [screenerRow], total: 1 },
  },
  today_ever_matched: null,
  today_ever_rows: null,
  updated_at: null,
}
/** /screener asOf 由 enriched.latest_date 驱动 (Screener.tsx:110-113) */
const dataStatusPayload = {
  daily: { rows: 0, earliest_date: null, latest_date: null, symbols_covered: 0, trading_days: 0 },
  enriched: { rows: 10, earliest_date: '2026-08-01', latest_date: '2026-08-04', symbols_covered: 100, trading_days: 3 },
  index_daily: null, index_enriched: null, index_instruments: null,
  etf_daily: null, etf_enriched: null, etf_instruments: null,
  minute: null, adj_factor: null, instruments: null, financials: null,
  storage: {
    daily_files: 0, daily_size_mb: 0, enriched_files: 0, enriched_size_mb: 0,
    minute_files: 0, minute_size_mb: 0, adj_factor_files: 0, adj_factor_size_mb: 0,
    instruments_files: 0, instruments_size_mb: 0,
  },
}

// ===== 竞价历史夹具 (镜像 pool-hub.spec.ts:127-184 的 auction fixtures 风格) =====
const auctionHistoryRow = (date: string, volume: number, amount: number) => ({
  date,
  datetime: `${date}T09:25:00`,
  auction_volume: volume,
  auction_amount: amount,
  row_count: 3,
  min_datetime: `${date}T09:16:00`,
  max_datetime: `${date}T09:25:00`,
})

const probeAvailable = {
  status: 'available',
  source: 'fake',
  probed_at: null,
  window: '09:15-09:25',
  fallback: 'open_gap',
  detail: '',
}

/** 有数据: available:true + probe available + 4 日真实量/额 */
const auctionHistoryPayload = {
  symbol: '300750.SZ',
  name: '宁德时代',
  available: true,
  probe: probeAvailable,
  mode: 'vip',
  coverage: 4,
  window: '09:15-09:25',
  unit: { auction_volume: '股', auction_amount: '元' },
  rows: [
    auctionHistoryRow('2026-08-04', 1_234_567, 234_567_890),
    auctionHistoryRow('2026-08-01', 980_000, 189_000_000),
    auctionHistoryRow('2026-07-31', 1_100_000, 215_000_000),
    auctionHistoryRow('2026-07-30', 850_000, 162_000_000),
  ],
}

/** available:false: 湖空 / 该 symbol 无行 → 200 诚实空态 (probe 仍 available) */
const emptyHistoryPayload = {
  symbol: '300750.SZ',
  name: '宁德时代',
  available: false,
  probe: probeAvailable,
  mode: 'vip',
  coverage: 0,
  window: '09:15-09:25',
  unit: { auction_volume: '股', auction_amount: '元' },
  rows: [],
}

/** probe 非 available: 数据源未配置 → 空态 + 降级窗口标注 */
const probeFailPayload = {
  ...emptyHistoryPayload,
  probe: {
    status: 'not_configured',
    source: null,
    probed_at: null,
    window: '09:15-09:25',
    fallback: 'open_gap',
    detail: '尚未配置竞价数据源',
  },
}

/** guest 会话: 服务端 D5 掩码 → available:false 空态, 量/价零泄露 */
const guestHistoryPayload = { ...emptyHistoryPayload, mode: 'guest' }

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

/**
 * 应用外壳 fixture (复制 pool-hub.spec.ts installShell): 让 Layout 预取与全局轮询
 * 都命中 mock, 未显式覆盖的 /api 请求大声失败, 便于发现意外依赖。
 * 追加 CHART-02 默认竞价历史空态路由 (后注册用例覆盖优先)。
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
  await page.route('**/api/pool/dates**', route => json(route, { dates: [], count: 0, latest: null }))
  await page.route('**/api/pool/history**', route => json(route, { as_of: null, available: false, strategies: [], resonance_count: 0, updated_at: null, mode: 'vip', concept_attribution: 'current_snapshot' }))
  await page.route('**/api/data/auction-probe**', route => json(route, { status: 'fail_closed', source: null, probed_at: null, window: '09:15-09:25', fallback: 'open_gap', detail: '' }))
  await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))
  // CHART-02: 默认竞价历史空态 (available:false, probe available) — 具体用例后注册覆盖
  await page.route('**/api/kline/auction/history**', route => json(route, emptyHistoryPayload))
}

/**
 * 打开个股弹窗: 注入 strategy-pool → /screener → 点策略卡 → 点行情行 (ScreenerTable.tsx:173) → 弹窗。
 * (B1 修订后 /pool-hub 名称列也已挂载 StockPreviewDialog, 但本夹具保留 /screener 路径不变。)
 * 返回后调用方可注册具体 auction-history 路由再点「竞价历史」。
 */
async function openPreviewDialog(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('strategy-pool', JSON.stringify(['auction_bullish']))
  })
  await installShell(page)
  await page.route('**/api/data/status**', route => json(route, dataStatusPayload))
  await page.route('**/api/screener/strategies**', route => json(route, { presets: [screenerStrategy] }))
  await page.route('**/api/screener/cached**', route => json(route, screenerCachedPayload))
  await page.route('**/api/screener/run_all**', route => json(route, { as_of: '2026-08-04', results: screenerCachedPayload.results }))
  await page.route('**/api/screener/run_preset**', route => json(route, { as_of: '2026-08-04', strategy: 'auction_bullish', rows: [screenerRow], total: 1, elapsed_ms: 0 }))
  await page.route('**/api/kline/daily**', route => json(route, { symbol: '300750.SZ', name: '宁德时代', rows: [], source: 'mock' }))

  await page.goto('/screener')

  // 策略卡 → handleRun (缓存覆盖池时从 effectiveResults 秒渲染结果表)
  await page.getByRole('button', { name: /竞价多头/ }).click()
  // 行情行 symbol 按钮 (ScreenerTable.tsx:173) → onPreview → StockPreviewDialog
  await page.getByRole('button', { name: /300750/ }).click()
  // 弹窗可观测锚点: 「竞价历史」toggle 仅 StockPreviewDialog 挂载时存在 (本弹窗无 role=dialog)
  await expect(page.getByRole('button', { name: '竞价历史' })).toBeVisible()
}

const auctionChartRegion = (page: Page) =>
  page.getByRole('img', { name: '历史竞价量/金额趋势图' })

test.describe('Phase 26 auction history chart (CHART-02)', () => {
  test('有数据: 双轴柱线图渲染 + 轴单位 + 09:15-09:25 窗口标注', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await openPreviewDialog(page)
    await page.route('**/api/kline/auction/history**', route => json(route, auctionHistoryPayload))

    await page.getByRole('button', { name: '竞价历史' }).click()

    const region = auctionChartRegion(page)
    // ECharts canvas 可见
    await expect(region.locator('canvas').first()).toBeVisible()
    // 轴单位 DOM 标注: 柱·竞价量(股) / 线·竞价金额(元)
    await expect(region.getByText('股')).toBeVisible()
    await expect(region.getByText('元')).toBeVisible()
    // 窗口标注 chip
    await expect(region.getByText('09:15-09:25')).toBeVisible()
  })

  test('available:false → 诚实空态「无历史竞价数据」+ 无画布', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await openPreviewDialog(page)
    // 默认 installShell 路由已返 emptyHistoryPayload (available:false); 显式注册更精确覆盖
    await page.route('**/api/kline/auction/history**', route => json(route, emptyHistoryPayload))

    await page.getByRole('button', { name: '竞价历史' }).click()

    const region = auctionChartRegion(page)
    await expect(page.getByText('无历史竞价数据')).toBeVisible()
    await expect(region.locator('canvas')).toHaveCount(0)
  })

  test('probe 非 available → 空态 + 降级窗口标注「数据源未配置」', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await openPreviewDialog(page)
    await page.route('**/api/kline/auction/history**', route => json(route, probeFailPayload))

    await page.getByRole('button', { name: '竞价历史' }).click()

    await expect(page.getByText('无历史竞价数据')).toBeVisible()
    await expect(page.getByText('数据源未配置')).toBeVisible()
  })

  test('guest → 空态 (量/价零泄露)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await openPreviewDialog(page)
    await page.route('**/api/kline/auction/history**', route => json(route, guestHistoryPayload))

    await page.getByRole('button', { name: '竞价历史' }).click()

    await expect(page.getByText('无历史竞价数据')).toBeVisible()
    const region = auctionChartRegion(page)
    await expect(region.locator('canvas')).toHaveCount(0)
    // guest 掩码: 量/价绝不渲染 (诚实空态)
    await expect(region).not.toContainText('1,234,567')
    await expect(region).not.toContainText('234,567,890')
  })
})
