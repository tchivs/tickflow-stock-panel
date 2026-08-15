import { expect, test, type Page, type Route } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

const json = (route: Route, body: unknown) =>
  route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

const GROUP = { id: 'g1', name: '核心', color: 'rose' }

/** 状态化分组夹具 — 模拟 groups CRUD + group_id 分配, 断言前端按契约调用 API。 */
function installShell(page: Page) {
  let groups: Array<{ id: string; name: string; color: string }> = [GROUP]
  let symbols: Array<{ symbol: string; added_at: string; note: string; group_id: string | null }> = [
    { symbol: '600001.SH', added_at: '2026-08-01T00:00:00', note: '', group_id: 'g1' },
    { symbol: '600002.SH', added_at: '2026-08-02T00:00:00', note: '', group_id: null },
  ]
  const enrichedRows = (list: typeof symbols) => list.map(({ symbol, group_id }) => ({
    symbol, name: symbol === '600001.SH' ? '浦发银行' : '浦发银行B', close: 10.0, open: 9.9,
    high: 10.2, low: 9.8, pct: 1.01, chg: 0.1, amount: 1.2e8, volume: 1.2e7,
    turnover_rate: 1.5, pe_ttm: 6.0, pb: 0.6, market_cap: 2.9e11, source: 'mock', group_id,
  }))

  page.route('**/api/settings', route => json(route, { onboarding_completed: true, theme: 'dark' }))
  page.route('**/api/capabilities', route => json(route, { label: 'Free+', capabilities: {} }))
  page.route('**/api/data/version', route => json(route, { version: 'phase18-browser' }))
  page.route('**/api/settings/preferences', route => json(route, {
    realtime_quotes_enabled: false, indices_nav_pinned: false, minute_sync_enabled: false,
    minute_sync_days: 5, pipeline_pull_a_share: true, pipeline_pull_etf: true,
    pipeline_pull_index: true, pipeline_index_symbols: '',
    pipeline_schedule: { hour: 15, minute: 30 }, instruments_schedule: { hour: 9, minute: 10 },
  }))
  page.route('**/api/settings/data-sources', route => json(route, { builtin: [], plugins: [], custom: [], errors: [], config_dir: 'deployment-config' }))
  page.route('**/api/intraday/status', route => json(route, { enabled: false, running: false, interval_s: 5, symbol_count: 0, quote_age_ms: null, is_trading_hours: false, last_fetch_ms: null }))
  page.route('**/api/analysis-menus', route => json(route, { items: [] }))
  page.route('**/api/pipeline/jobs**', route => json(route, { active_id: null, jobs: [] }))
  page.route('**/api/intraday/indices**', route => json(route, { rows: [], count: 0 }))
  page.route('**/api/alerts**', route => json(route, { alerts: [], total: 0 }))
  page.route('**/api/screener/strategies**', route => json(route, { presets: [] }))

  page.route('**/api/watchlist/enriched**', route => json(route, { rows: enrichedRows(symbols), as_of: '2026-08-09T00:00:00', elapsed_ms: 0 }))
  page.route('**/api/watchlist/groups**', route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as { name: string; color: string }
      groups = [...groups, { id: `g${groups.length + 1}`, name: body.name, color: body.color }]
      return json(route, { groups, group: groups[groups.length - 1] })
    }
    return json(route, { groups })
  })
  page.route('**/api/watchlist/groups/*', route => {
    const id = new URL(route.request().url()).pathname.split('/').pop()!
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON() as { name: string; color: string }
      groups = groups.map(g => g.id === id ? { ...g, name: body.name, color: body.color } : g)
      return json(route, { groups })
    }
    if (route.request().method() === 'DELETE') {
      groups = groups.filter(g => g.id !== id)
      symbols = symbols.map(s => s.group_id === id ? { ...s, group_id: null } : s)
      return json(route, { groups, symbols })
    }
    return json(route, { groups })
  })
  page.route('**/api/watchlist/groups/*/clear', route => {
    const id = new URL(route.request().url()).pathname.split('/').slice(-2, -1)[0]
    symbols = symbols.map(s => s.group_id === id ? { ...s, group_id: null } : s)
    return json(route, { symbols })
  })
  page.route('**/api/watchlist/*/group', route => {
    const symbol = new URL(route.request().url()).pathname.split('/').slice(-2, -1)[0]
    const body = route.request().postDataJSON() as { group_id: string | null }
    symbols = symbols.map(s => s.symbol === symbol ? { ...s, group_id: body.group_id } : s)
    return json(route, { symbols })
  })
  page.route('**/api/watchlist', route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as { symbol: string; group_id?: string | null }
      if (!symbols.some(s => s.symbol === body.symbol)) {
        symbols = [...symbols, { symbol: body.symbol, added_at: '2026-08-10T00:00:00', note: '', group_id: body.group_id ?? null }]
      }
      return json(route, { symbols })
    }
    return json(route, { symbols })
  })
}

test.describe('Watchlist 自选分组 tab 栏 / 管理对话框 可访问性', () => {
  test('分组 tablist 语义 + 按分组过滤表格', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    installShell(page)
    await page.goto('/watchlist')

    const tablist = page.getByRole('tablist', { name: '自选分组' })
    await expect(tablist).toBeVisible()
    // 全部(2) / 未分组(1) / 核心(1)
    await expect(page.getByRole('tab', { name: '全部' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('tab', { name: '未分组' })).toHaveAttribute('aria-selected', 'false')
    await expect(page.getByRole('tab', { name: '核心' })).toHaveAttribute('aria-selected', 'false')
    await expect(page.getByText('600001.SH', { exact: true })).toBeVisible()
    await expect(page.getByText('600002.SH', { exact: true })).toBeVisible()

    // 切到「核心」→ 只显示组内股票, aria-selected 同步
    await page.getByRole('tab', { name: '核心' }).click()
    await expect(page.getByRole('tab', { name: '核心' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('tab', { name: '全部' })).toHaveAttribute('aria-selected', 'false')
    await expect(page.getByText('600001.SH', { exact: true })).toBeVisible()
    await expect(page.getByText('600002.SH', { exact: true })).toHaveCount(0)

    // 切到「未分组」→ 只剩未分组股票
    await page.getByRole('tab', { name: '未分组' }).click()
    await expect(page.getByText('600002.SH', { exact: true })).toBeVisible()
    await expect(page.getByText('600001.SH', { exact: true })).toHaveCount(0)

    // 回到「全部」
    await page.getByRole('tab', { name: '全部' }).click()
    await expect(page.getByText('600001.SH', { exact: true })).toBeVisible()
    await expect(page.getByText('600002.SH', { exact: true })).toBeVisible()
  })

  test('管理对话框: 创建/重命名/删除分组 + dialog 语义', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    installShell(page)
    await page.goto('/watchlist')

    const createPromise = page.waitForRequest(req => req.method() === 'POST' && req.url().endsWith('/api/watchlist/groups'))
    await page.getByRole('button', { name: '管理自选分组' }).click()
    const dialog = page.getByRole('dialog', { name: '管理自选分组' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByPlaceholder('新分组名称')).toBeFocused()

    // 创建
    await dialog.getByPlaceholder('新分组名称').fill('成长')
    await dialog.getByRole('button', { name: '新建' }).click()
    const createReq = await createPromise
    expect(createReq.postDataJSON()).toMatchObject({ name: '成长' })
    await expect(page.getByRole('tab', { name: '成长' })).toHaveAttribute('aria-selected', 'false')

    // 重命名 g1 (编辑按钮 title=编辑分组)
    const editBtn = page.locator('[title="编辑分组"]').first()
    await editBtn.click()
    const renameInput = dialog.locator('input').nth(1)
    await expect(renameInput).toHaveValue('核心')
    const renamePromise = page.waitForRequest(req => req.method() === 'PUT' && req.url().includes('/api/watchlist/groups/g1'))
    await renameInput.fill('蓝筹')
    await page.locator('[title="保存分组"]').click()
    const renameReq = await renamePromise
    expect(renameReq.postDataJSON()).toMatchObject({ name: '蓝筹', color: 'rose' })
    await expect(page.getByRole('tab', { name: '蓝筹' })).toBeVisible()

    // 删除 g1 → 组内成员回到未分组
    const deletePromise = page.waitForRequest(req => req.method() === 'DELETE' && req.url().includes('/api/watchlist/groups/g1'))
    await page.locator('[title="删除分组"]').first().click()
    await dialog.getByRole('button', { name: '确认' }).click()
    await deletePromise
    await expect(page.getByRole('tab', { name: '蓝筹' })).toHaveCount(0)
    await expect(page.getByText('600001.SH', { exact: true })).toBeVisible()

    // ESC 关闭对话框
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible()
  })

  test('行内分组选择器: 分配/改回未分组 + 清空分组确认', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    installShell(page)
    await page.goto('/watchlist')

    // 600002.SH 当前未分组 → 分配到「核心」
    const setGroupPromise = page.waitForRequest(req => req.method() === 'PUT' && req.url().includes('/api/watchlist/600002.SH/group'))
    await page.getByLabel('600002.SH 的分组').selectOption('g1')
    const setGroupReq = await setGroupPromise
    expect(setGroupReq.postDataJSON()).toMatchObject({ group_id: 'g1' })
    await expect(page.getByRole('tab', { name: '核心' })).toHaveAttribute('aria-selected', 'false')

    // 切到「核心」→ 两只都在
    await page.getByRole('tab', { name: '核心' }).click()
    await expect(page.getByText('600001.SH', { exact: true })).toBeVisible()
    await expect(page.getByText('600002.SH', { exact: true })).toBeVisible()

    // 清空分组 → 确认弹窗 → 成员转未分组
    await page.getByRole('button', { name: '清空当前分组' }).click()
    const clearDialog = page.getByRole('heading', { name: '清空分组' })
    await expect(clearDialog).toBeVisible()
    const clearPromise = page.waitForRequest(req => req.method() === 'POST' && req.url().includes('/api/watchlist/groups/g1/clear'))
    await page.getByRole('button', { name: '确认清空' }).click()
    await clearPromise
    // 清空后组内成员全部转未分组: 当前「核心」tab 下应为空
    await expect(page.getByRole('tab', { name: '核心' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByText('600001.SH', { exact: true })).toHaveCount(0)
    await expect(page.getByText('600002.SH', { exact: true })).toHaveCount(0)
    // 切到「未分组」→ 两只都在
    await page.getByRole('tab', { name: '未分组' }).click()
    await expect(page.getByText('600001.SH', { exact: true })).toBeVisible()
    await expect(page.getByText('600002.SH', { exact: true })).toBeVisible()
  })
})
