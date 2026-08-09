import type { Page, Route } from '@playwright/test'
import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

// ===== 共享 mock 载荷 (独立 spec — 复制 monitor.spec.ts 常量/helpers, 不 import 跨文件耦合) =====

/** /api/settings/data-sources 载荷: 内置 tickflow + 未装依赖插件 + 自定义源 */
const dataSourcesPayload = {
  builtin: [
    { name: 'tickflow', display_name: 'TickFlow', datasets: ['daily', 'minute', 'realtime', 'adj_factor', 'financial'] },
  ],
  plugins: [
    {
      name: 'py-plugin', display_name: 'Python 插件', datasets: ['daily'],
      runtime: 'python', available: false, status: '依赖未安装',
      description: '测试插件', install_hint: 'pip install example',
    },
  ],
  custom: [
    { name: 'my-custom', display_name: '我的自定义源', datasets: ['daily'] },
  ],
  errors: [],
  config_dir: 'deployment-config',
}

/** /api/settings/data-sources/my-custom — 编辑器加载的完整配置 */
const customDetail = {
  name: 'my-custom',
  display_name: '我的自定义源',
  auth: { type: 'none' },
  datasets: {
    daily: { url: 'https://example.com/daily', method: 'GET', response_path: 'data', field_map: { date: 'date' } },
  },
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

/**
 * 应用外壳 fixture — 复制 monitor.spec.ts installShell (独立 spec, 不 import 跨文件耦合):
 * Layout 预取与全局轮询都命中 mock, 未显式覆盖的 /api 请求大声失败 (暴露意外依赖)。
 * data-sources 路由在 installShell 内注册空态, 用例以更精确 route 覆盖 (后注册优先)。
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
  await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))
}

test.describe('Settings data-sources 卡片主操作可访问性', () => {
  test('键盘: 自定义源卡片按钮 focus + Enter 打开编辑器并加载配置', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/settings/data-sources', route => json(route, dataSourcesPayload))
    await page.route('**/api/settings/data-sources/my-custom', route => json(route, customDetail))

    await page.goto('/settings?tab=data-sources')

    // stretched-link 语义按钮可达 (读屏名 = 配置 + 显示名)
    const cardBtn = page.getByRole('button', { name: '配置 我的自定义源' })
    await expect(cardBtn).toBeVisible()

    // 纯键盘: focus → Enter
    await cardBtn.focus()
    await page.keyboard.press('Enter')

    // 编辑器打开且已加载该源配置 (显示名输入框填充了 detail.display_name)
    await expect(page.getByRole('heading', { name: '编辑数据源' })).toBeVisible()
    await expect(page.getByPlaceholder('我的 Tushare')).toHaveValue('我的自定义源')
  })

  test('鼠标: 点卡片内容区 (pointer-events-none) 仍触发 stretched-link 打开编辑器', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/settings/data-sources', route => json(route, dataSourcesPayload))
    await page.route('**/api/settings/data-sources/my-custom', route => json(route, customDetail))

    await page.goto('/settings?tab=data-sources')
    const cardBtn = page.getByRole('button', { name: '配置 我的自定义源' })
    await expect(cardBtn).toBeVisible()

    // 鼠标点卡片: 内容区 pointer-events-none, 浏览器 hit-test 落到 stretched-link 覆盖按钮
    // (链编辑区「可启用」chips 也含同名文本, 故直接以按钮为鼠标目标而非卡片文本)
    await cardBtn.click()

    await expect(page.getByRole('heading', { name: '编辑数据源' })).toBeVisible()
    await expect(page.getByPlaceholder('我的 Tushare')).toHaveValue('我的自定义源')
  })

  test('插件卡 安装 按钮在 stretched-link 覆盖之上仍可点击 (不触发卡片选中)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/settings/data-sources', route => json(route, dataSourcesPayload))
    let installHit = false
    await page.route('**/api/settings/plugins/py-plugin/install', route => {
      installHit = true
      return json(route, { ...dataSourcesPayload, install_ok: true, install_message: 'ok' })
    })

    await page.goto('/settings?tab=data-sources')
    // unavailable 插件卡不渲染覆盖按钮, 安装 是唯一可点控件
    await expect(page.getByRole('button', { name: '配置 Python 插件' })).toHaveCount(0)

    await page.getByRole('button', { name: '安装', exact: true }).click()
    await expect.poll(() => installHit).toBe(true)

    // 点击落到了 安装 而非卡片选中 → 编辑器未打开
    await expect(page.getByRole('heading', { name: '编辑数据源' })).toHaveCount(0)
  })
})
