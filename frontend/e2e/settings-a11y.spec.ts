import { expect, test, type Page, type Route } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

const json = (route: Route, body: unknown) =>
  route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

/**
 * 应用外壳 fixture — 复制 data-sources.spec installShell (独立 spec, 不 import 跨文件耦合):
 * Layout 预取与全局轮询都命中 mock, 未显式覆盖的 /api 请求大声失败。
 */
async function installShell(page: Page, settingsOverrides: Record<string, unknown> = {}) {
  await page.route('**/api/**', unhandled)
  await page.route('**/api/settings', route => json(route, { onboarding_completed: true, theme: 'dark', ...settingsOverrides }))
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
  await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))
}

test.describe('Settings 小确认对话框 / 弹层 可访问性', () => {
  test('AI 清空确认 dialog: 焦点捕获 + Tab 陷阱 + ESC 关闭 + 还原', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page, { ai_configured: true })
    await page.goto('/settings?tab=ai')

    const clearBtn = page.getByRole('button', { name: '清空', exact: true })
    await expect(clearBtn).toBeVisible()
    await clearBtn.click()

    const dialog = page.getByRole('dialog', { name: '清空 AI 配置' })
    await expect(dialog).toBeVisible()

    // 焦点捕获到面板内首个可聚焦项 = 取消按钮
    const cancel = dialog.getByRole('button', { name: '取消' })
    await expect(cancel).toBeFocused()

    // Tab 陷阱: 焦点 8 轮循环始终留在 dialog 内
    const focusInDialog = () => page.evaluate(
      () => !!(document.activeElement as HTMLElement | null)?.closest?.('[role="dialog"][aria-label="清空 AI 配置"]'),
    )
    await expect.poll(focusInDialog).toBe(true)
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press('Tab')
      await expect.poll(focusInDialog).toBe(true)
    }

    // Shift+Tab 从首个元素回卷到末个元素 (陷阱两向)
    await page.keyboard.press('Shift+Tab')
    await expect.poll(focusInDialog).toBe(true)
    await expect(dialog.getByRole('button', { name: '确认' })).toBeFocused()

    // ESC 关闭 + 焦点还原到触发按钮
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(clearBtn).toBeFocused()
  })

  test('Keys 档位说明: 图标触发是键盘可达按钮 + aria-expanded 同步', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.goto('/settings') // 默认 tab = account → Keys 面板

    const trigger = page.getByRole('button', { name: '档位说明' })
    await expect(trigger).toBeVisible()
    await expect(trigger).toHaveAttribute('aria-expanded', 'false')

    // 纯键盘: focus → Enter 展开, 状态同步
    await trigger.focus()
    await page.keyboard.press('Enter')
    await expect(trigger).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByText('高等档位包含较低档位的全部权益。')).toBeVisible()

    // 再按 Enter 收起
    await page.keyboard.press('Enter')
    await expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })
})
