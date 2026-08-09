import { expect, test, type Page } from '@playwright/test'

const strategyDetail = (id: string, name: string) => ({
  id,
  name,
  description: '回归测试策略',
  source: 'builtin',
  params: [],
  params_defaults: {},
  basic_filter: {},
  entry_signals: [],
  exit_signals: [],
  scoring: {},
  stop_loss: null,
  take_profit: null,
  trailing_stop: null,
  trailing_take_profit_activate: null,
  trailing_take_profit_drawdown: null,
  score_min: null,
  score_max: null,
  max_hold_days: null,
})

const result = {
  run_id: 'backtest-regression-run',
  config: { strategy_id: 'first', start: '2026-01-01', end: '2026-01-02' },
  stats: { mode: 'position', total_return: 0.1, n_trades: 0 },
  equity_curve: [
    { date: '2026-01-01', value: 1_000_000 },
    { date: '2026-01-02', value: 1_100_000 },
  ],
  drawdown_curve: [{ date: '2026-01-02', value: -0.02 }],
  benchmark_curve: [],
  trades: [],
  per_symbol_stats: [],
  strategy_info: {
    ...strategyDetail('first', '第一个策略'),
    entry_signals: [],
    exit_signals: [],
  },
  elapsed_ms: 1,
  error: null,
}

async function installFixture(page: Page) {
  const json = (body: unknown, status = 200) => ({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })

  await page.route('**/api/**', route => route.fulfill(json({})))
  await page.route('**/api/settings', route => route.fulfill(json({ onboarding_completed: true })))
  await page.route('**/api/research/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/dsl/options')) return route.fulfill(json({ dsl_version: 'factor-dsl-v1', fields: ['close'], functions: {}, operators: [] }))
    if (path.endsWith('/factors')) return route.fulfill(json({ factors: [] }))
    if (path.endsWith('/experiments') || path.endsWith('/comparison/candidates')) return route.fulfill(json({ experiments: [] }))
    return route.fulfill(json({}))
  })
  await page.route('**/api/screener/strategies**', route => route.fulfill(json({
    presets: [
      { id: 'first', name: '第一个策略', description: '回归测试策略', source: 'builtin' },
      { id: 'second', name: '第二个策略', description: '回归测试策略', source: 'builtin' },
    ],
  })))
  await page.route('**/api/strategies/*', route => {
    const id = new URL(route.request().url()).pathname.split('/').pop() ?? 'first'
    return route.fulfill(json(strategyDetail(id, id === 'second' ? '第二个策略' : '第一个策略')))
  })
  await page.route('**/api/backtest/strategy/stream?**', route => route.fulfill({
    contentType: 'text/event-stream',
    body: `event: research\ndata: ${JSON.stringify({ execution_handle: 'regression-handle' })}\n\nevent: done\ndata: ${JSON.stringify(result)}\n\n`,
  }))
}

test('switching backtest modes preserves strategy configuration', async ({ page }) => {
  await installFixture(page)
  await page.goto('/backtest')

  await page.getByRole('button', { name: '第一个策略', exact: true }).click()
  await expect(page.getByRole('button', { name: '策略设置' })).toContainText('第一个策略')

  await page.getByRole('tab', { name: '因子回测' }).click()
  await page.getByRole('tab', { name: '策略回测' }).click()

  await expect(page.getByRole('button', { name: '策略设置' })).toContainText('第一个策略')
  await expect(page.getByRole('button', { name: '运行回测' })).toBeEnabled()
})

test('advanced settings drawer traps focus and restores it on ESC', async ({ page }) => {
  await installFixture(page)
  await page.goto('/backtest')

  const trigger = page.getByRole('button', { name: '策略设置' })
  await page.getByRole('button', { name: '第一个策略', exact: true }).click()
  await expect(trigger).toContainText('第一个策略')
  await trigger.click()

  const drawer = page.getByRole('dialog', { name: '高级策略设置' })
  await expect(drawer).toBeVisible()
  // 打开即捕获焦点到抽屉内 (首项 = 关闭按钮), Tab 循环不逃出抽屉 (WCAG 2.1.2)
  const focusInDrawer = () => page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null
    return el?.closest?.('[role="dialog"]')?.getAttribute('aria-label') === '高级策略设置'
  })
  await expect.poll(focusInDrawer).toBe(true)
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab')
    await expect.poll(focusInDrawer).toBe(true)
  }
  // ESC 关闭且焦点还原到触发按钮
  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test('changing strategy clears the previous result and mobile charts recover after being hidden', async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.startsWith('mobile-'), 'mobile chart regression')
  await installFixture(page)
  await page.goto('/backtest')

  await page.getByRole('button', { name: '第一个策略', exact: true }).click()
  await page.getByRole('button', { name: '运行回测' }).click()
  const chart = page.getByRole('img', { name: /策略净值曲线，共 2 个交易日/ })
  await expect(chart).toBeVisible()

  await page.getByRole('tab', { name: '回测配置', exact: true }).click()
  await page.getByLabel('最大持仓数').fill('0')
  await expect(page.getByRole('tabpanel', { name: '回测配置' }).getByRole('alert')).toContainText('最大持仓数必须大于 0')
  await expect(page.getByRole('button', { name: '运行回测' })).toBeDisabled()
  await page.getByLabel('最大持仓数').fill('10')
  await expect(chart).toBeHidden()
  await page.getByRole('tab', { name: '回测结果', exact: true }).click()
  await expect(chart).toBeVisible()
  expect((await chart.boundingBox())?.width ?? 0).toBeGreaterThan(0)

  await page.getByRole('button', { name: '全量模拟', exact: true }).click()
  await expect(page.getByText('当前配置已修改，下面仍是上一次回测结果。请点击“运行回测”刷新结果。', { exact: true })).toBeVisible()

  await page.getByRole('tab', { name: '回测配置', exact: true }).click()
  await page.getByRole('button', { name: '第二个策略', exact: true }).click()
  await page.getByRole('tab', { name: '回测结果', exact: true }).click()
  await expect(page.getByText('选择策略并开始回测')).toBeVisible()
})
