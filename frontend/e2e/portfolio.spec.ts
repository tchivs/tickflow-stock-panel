import { expect, test, type Page } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

function position(id: number, symbol: string) {
  return {
    id,
    instrument_symbol: symbol,
    quantity: 100,
    cost_price: 1400,
    market_value: 150000 + id * 100,
    unrealized_pnl: 1000 + id * 50,
    account_id: 1,
    trading_style: 'long',
    source: 'governed_close',
    as_of: '2024-07-01T10:00:00Z',
    fresh: false,
  }
}

const POSITIONS = Array.from({ length: 15 }, (_, i) => position(i + 1, `${String(600001 + i)}.SH`))

async function installPortfolioFixture(page: Page) {
  const json = (body: unknown) => ({ contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', route => route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }),
  }))
  await page.route('**/api/settings', route => route.fulfill(json({ onboarding_completed: true })))
  await page.route('**/api/portfolio/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/accounts')) return route.fulfill(json({ accounts: [{ id: 1, name: '测试账户', archived_at: null }] }))
    if (path.endsWith('/summary')) return route.fulfill(json({ total_assets: 2500000, available_funds: 10000, market_value: 2400000, unrealized_pnl: 15000, positions: [] }))
    if (path.endsWith('/positions')) return route.fulfill(json({ positions: POSITIONS }))
    return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled portfolio fixture route: ${path}` }) })
  })
  await page.route('**/api/monitor/rules**', route => route.fulfill(json({ rules: [] })))
}

test.describe('Portfolio holdings keyboard row navigation', () => {
  test('roving tabindex: arrow/Home/End/PageUp/PageDown move rows, Tab enters row controls', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium only')
    await installPortfolioFixture(page)
    await page.goto('/portfolio')

    const rows = page.locator('table[aria-keyshortcuts] tbody tr')
    await expect(rows).toHaveCount(15)

    // 初始 roving 停靠点 = 首行 (tabIndex 0 / 其余 −1)
    await expect(rows.nth(0)).toHaveJSProperty('tabIndex', 0)
    await expect(rows.nth(1)).toHaveJSProperty('tabIndex', -1)

    // ↓ → 第 2 行 (roving 迁移: 目标行 0, 原行 −1)
    await rows.nth(0).focus()
    await page.keyboard.press('ArrowDown')
    await expect(rows.nth(1)).toBeFocused()
    await expect(rows.nth(1)).toHaveJSProperty('tabIndex', 0)
    await expect(rows.nth(0)).toHaveJSProperty('tabIndex', -1)

    // End → 末行 (idx 14)
    await page.keyboard.press('End')
    await expect(rows.nth(14)).toBeFocused()

    // ↑ → 倒数第 2
    await page.keyboard.press('ArrowUp')
    await expect(rows.nth(13)).toBeFocused()

    // Home → 首行
    await page.keyboard.press('Home')
    await expect(rows.nth(0)).toBeFocused()

    // PageDown 步长 10 → 第 11 行 (0 + 10)
    await page.keyboard.press('PageDown')
    await expect(rows.nth(10)).toBeFocused()

    // PageUp → 下限钳制回首行
    await page.keyboard.press('PageUp')
    await expect(rows.nth(0)).toBeFocused()

    // Tab 进入行内控件 → 行首控件 = 监控按钮 (DOM 顺序最前的 button)
    await page.keyboard.press('Tab')
    await expect(page.getByRole('button', { name: '查看 600001.SH 的持仓监控' })).toBeFocused()
  })
})
