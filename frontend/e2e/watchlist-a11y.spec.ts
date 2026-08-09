import { expect, test, type Page, type Route } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

const json = (route: Route, body: unknown) =>
  route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

/** 非空自选夹具 — 清空按钮仅在 allSymbols.length > 0 时渲染 */
const watchlistSymbols = [{ symbol: '600001.SH', added_at: '2026-08-01T00:00:00', note: '' }]
const enrichedPayload = {
  rows: [{
    symbol: '600001.SH', name: '浦发银行', close: 10.0, open: 9.9, high: 10.2, low: 9.8,
    pct: 1.01, chg: 0.1, amount: 1.2e8, volume: 1.2e7, turnover_rate: 1.5,
    pe_ttm: 6.0, pb: 0.6, market_cap: 2.9e11, source: 'mock',
  }],
  as_of: '2026-08-09T00:00:00',
  elapsed_ms: 0,
}

/**
 * 应用外壳 fixture — 复制 settings-a11y installShell (独立 spec, 不 import 跨文件耦合)。
 * 覆盖 watchlist 非空 + enriched 行, 使清空按钮渲染、表格有一行数据。
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
  await page.route('**/api/screener/strategies**', route => json(route, { presets: [] }))
  await page.route('**/api/watchlist**', route => json(route, { symbols: watchlistSymbols }))
  await page.route('**/api/watchlist/enriched**', route => json(route, enrichedPayload))
}

test.describe('Watchlist 工具条 / 清空确认对话框 可访问性', () => {
  test('清空确认 dialog: 焦点捕获 + Tab 陷阱 + ESC 关闭 + 还原', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.goto('/watchlist')
    const clearBtn = page.getByRole('button', { name: '清空自选' })
    await expect(clearBtn).toBeVisible()
    await clearBtn.click()

    const dialog = page.getByRole('dialog', { name: '清空自选确认' })
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAttribute('aria-modal', 'true')

    // 打开即捕获焦点到首个可聚焦元素 (取消)
    await expect(dialog.getByRole('button', { name: '取消' })).toBeFocused()

    // Tab 陷阱: 取消 → 确认清空 → 再 Tab 回卷到取消 (焦点不跑出对话框)
    await page.keyboard.press('Tab')
    await expect(dialog.getByRole('button', { name: '确认清空' })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(dialog.getByRole('button', { name: '取消' })).toBeFocused()

    // Shift+Tab 回卷到确认清空
    await page.keyboard.press('Shift+Tab')
    await expect(dialog.getByRole('button', { name: '确认清空' })).toBeFocused()

    // ESC 关闭 → 对话框消失 → 焦点还原到触发按钮
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(clearBtn).toBeFocused()
  })

  test('工具条图标可访问名 + 筛选面板 toggle 语义 + 板块 aria-pressed', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.goto('/watchlist')

    // 图标按钮可访问名 (title-only 缺口修复): 每个都能被 getByRole 找到
    await expect(page.getByRole('button', { name: '筛选' })).toBeVisible()
    await expect(page.getByRole('button', { name: '刷新' })).toBeVisible()
    await expect(page.getByRole('button', { name: '自定义列' })).toBeVisible()
    await expect(page.getByRole('button', { name: '卡片视图' })).toBeVisible()

    // 筛选面板 toggle: aria-expanded 同步
    const filterBtn = page.getByRole('button', { name: '筛选' })
    await expect(filterBtn).toHaveAttribute('aria-expanded', 'false')
    await filterBtn.click()
    await expect(filterBtn).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByRole('button', { name: '沪主板' })).toBeVisible()

    // 板块 chip: 默认全选 aria-pressed=true; 点击后翻转 false
    const sh = page.getByRole('button', { name: '沪主板' })
    await expect(sh).toHaveAttribute('aria-pressed', 'true')
    await sh.click()
    await expect(sh).toHaveAttribute('aria-pressed', 'false')
  })

  test('搜索框 combobox/listbox 语义: aria-expanded + activedescendant + selected 同步', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/kline/instruments/search**', route => json(route, {
      results: [
        { symbol: '600000.SH', name: '浦发银行', code: '600000', asset_type: 'stock' },
        { symbol: '600519.SH', name: '贵州茅台', code: '600519', asset_type: 'stock' },
      ],
    }))
    await page.goto('/watchlist')

    const combo = page.getByRole('combobox', { name: '搜索股票或 ETF' })
    await expect(combo).toBeVisible()
    await expect(combo).toHaveAttribute('aria-expanded', 'false')

    // 输入触发下拉 → aria-expanded 同步
    await combo.fill('600')
    await expect(combo).toHaveAttribute('aria-expanded', 'true')
    const listbox = page.getByRole('listbox')
    await expect(listbox).toBeVisible()
    await expect(page.getByRole('option')).toHaveCount(2)

    // ArrowDown → 首个 option aria-selected + combobox aria-activedescendant 同步
    await page.keyboard.press('ArrowDown')
    await expect(page.getByRole('option').first()).toHaveAttribute('aria-selected', 'true')
    await expect(combo).toHaveAttribute('aria-activedescendant', 'stock-search-0')
    await page.keyboard.press('ArrowDown')
    await expect(page.getByRole('option').nth(1)).toHaveAttribute('aria-selected', 'true')
    await expect(combo).toHaveAttribute('aria-activedescendant', 'stock-search-1')

    // Enter 选中 → 下拉关闭 (aria-expanded 归 false), 打开个股详情预览
    await page.keyboard.press('Enter')
    await expect(combo).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByRole('option')).toHaveCount(0)
    await expect(page.getByRole('dialog', { name: /个股详情 600519\.SH/ })).toBeVisible()
  })
})
