import type { Page, Route } from '@playwright/test'
import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import path from 'node:path'

const DESKTOP_PROJECT = 'desktop-chromium'

// ===== 共享 mock 载荷 =====
const HUB_AS_OF = '2026-08-04'
const HUB_UPDATED_AT = 1_754_310_000

/** 交叉共振行: 被 竞价多头 + 盘前强势量化 同时命中 (hit_factors ≥ 2) */
const doublyHitRow = {
  symbol: '300750.SZ', code: '300750', name: '宁德时代', open_gap: 0.0234, change_pct: 0.0512,
  concept_board: ['新能源', '人工智能'], hit_factors: ['竞价多头', '盘前强势量化'], cross_resonance: true,
}
/** 单策略命中行: 仅 竞价多头 */
const singleHitRow = {
  symbol: '600519.SH', code: '600519', name: '贵州茅台', open_gap: 0.0105, change_pct: -0.0012,
  concept_board: ['白酒'], hit_factors: ['竞价多头'], cross_resonance: false,
}

const hubPayload = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  mode: 'vip',
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 2, rows: [doublyHitRow, singleHitRow] },
    { id: 'auction_preopen_quant', name: '盘前强势量化', total: 1, rows: [doublyHitRow] },
  ],
  resonance_count: 1,
}

const emptyHubPayload = { as_of: HUB_AS_OF, updated_at: HUB_UPDATED_AT, mode: 'vip', strategies: [], resonance_count: 0 }

const zeroHitHubPayload = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  mode: 'vip',
  strategies: [
    ...hubPayload.strategies,
    { id: 'auction_early_star', name: '早盘之星', total: 0, rows: [] as typeof doublyHitRow[] },
  ],
  resonance_count: 1,
}

const noResonanceHubPayload = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  mode: 'vip',
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 1, rows: [singleHitRow] },
  ],
  resonance_count: 0,
}

// ===== 游客夹具: 服务端脱敏 (code/name/symbol = ******, open_gap 键省略) =====
// 注意: ****** 字面量只允许出现在 e2e 夹具里断言服务端输出, 生产源码禁止 (grep guard)。
const guestDoublyHitRow = {
  symbol: '******', code: '******', name: '******',
  change_pct: 0.0512, concept_board: ['新能源', '人工智能'], hit_factors: ['竞价多头', '盘前强势量化'], cross_resonance: true,
}
const guestSingleHitRow = {
  symbol: '******', code: '******', name: '******',
  change_pct: -0.0012, concept_board: ['白酒'], hit_factors: ['竞价多头'], cross_resonance: false,
}
const hubPayloadGuest = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  mode: 'guest',
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 2, rows: [guestDoublyHitRow, guestSingleHitRow] },
    { id: 'auction_preopen_quant', name: '盘前强势量化', total: 1, rows: [guestDoublyHitRow] },
  ],
  resonance_count: 1,
}
const emptyHubPayloadGuest = { as_of: HUB_AS_OF, updated_at: HUB_UPDATED_AT, mode: 'guest', strategies: [], resonance_count: 0 }

/** 已知策略全集 (preset 列表) — 不在 hub 载荷里的策略渲染 数据不可用 */
const knownStrategies = [
  { id: 'auction_bullish', name: '竞价多头', description: '竞价高开强度', source: 'builtin' },
  { id: 'auction_preopen_quant', name: '盘前强势量化', description: '盘前量化强度', source: 'builtin' },
  { id: 'auction_early_star', name: '早盘之星', description: '早盘强势', source: 'builtin' },
  { id: 'auction_momentum', name: '动量增强', description: '开盘动量', source: 'builtin' },
]

// ===== Task 3: 视觉证据 (UI-SPEC 5 个 backstop 标量) =====
const VISUAL_LONG_NAME = '竞价高开强度叠加盘前量能与连板因子共振筛选策略（超长名称用于截断演示）'

const visualRows: typeof doublyHitRow[] = [
  { symbol: '300750.SZ', code: '300750', name: '宁德时代', open_gap: 0.0234, change_pct: 0.0512, concept_board: ['新能源', '人工智能', '动力电池', '固态电池', '超级充电', '锂电池隔膜'], hit_factors: ['竞价多头', '盘前强势量化'], cross_resonance: true },
  { symbol: '600519.SH', code: '600519', name: '贵州茅台', open_gap: 0.0105, change_pct: null, concept_board: ['白酒'], hit_factors: ['竞价多头'], cross_resonance: false },
  { symbol: '000001.SZ', code: '000001', name: '平安银行', open_gap: null, change_pct: -0.0012, concept_board: [], hit_factors: [], cross_resonance: false },
  { symbol: '688981.SH', code: '688981', name: '中芯国际', open_gap: 0.0188, change_pct: 0.002, concept_board: ['半导体', '芯片'], hit_factors: ['竞价多头'], cross_resonance: false },
  { symbol: '832566.BJ', code: '832566', name: '北证样本', open_gap: -0.004, change_pct: -0.02, concept_board: ['北交所'], hit_factors: ['盘前强势量化'], cross_resonance: false },
  { symbol: '000010.SZ', code: '000010', name: '招商银行', open_gap: 0.003, change_pct: 0.011, concept_board: ['银行'], hit_factors: ['竞价多头'], cross_resonance: false },
  { symbol: '000011.SZ', code: '000011', name: '中信证券', open_gap: 0.006, change_pct: 0.018, concept_board: ['券商'], hit_factors: ['竞价多头'], cross_resonance: false },
  { symbol: '000012.SZ', code: '000012', name: '万科A', open_gap: 0.009, change_pct: 0.024, concept_board: ['地产'], hit_factors: ['竞价多头'], cross_resonance: false },
  { symbol: '000013.SZ', code: '000013', name: '宝钢股份', open_gap: -0.002, change_pct: -0.008, concept_board: ['钢铁'], hit_factors: ['竞价多头'], cross_resonance: false },
  { symbol: '000014.SZ', code: '000014', name: '中国神华', open_gap: 0.014, change_pct: 0.031, concept_board: ['煤炭'], hit_factors: ['竞价多头'], cross_resonance: false },
  { symbol: '000015.SZ', code: '000015', name: '中国石化', open_gap: 0.001, change_pct: 0.005, concept_board: ['石油'], hit_factors: ['竞价多头'], cross_resonance: false },
  { symbol: '000016.SZ', code: '000016', name: '中国船舶', open_gap: 0.02, change_pct: 0.045, concept_board: ['军工'], hit_factors: ['竞价多头'], cross_resonance: false },
]

/** 游客版视觉载荷: 大量共享 ****** 身份的行 (Backstop 3: 视觉可区分) */
const visualGuestRows: typeof guestDoublyHitRow[] = visualRows.map(r => ({
  symbol: '******', code: '******', name: '******',
  change_pct: r.change_pct, concept_board: r.concept_board, hit_factors: r.hit_factors, cross_resonance: r.cross_resonance,
}))

const visualHubPayload = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  mode: 'vip',
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: visualRows.length, rows: visualRows },
    { id: 'auction_long_name', name: VISUAL_LONG_NAME, total: 1, rows: [doublyHitRow] },
    { id: 'auction_early_star', name: '早盘之星', total: 0, rows: [] as typeof doublyHitRow[] },
  ],
  resonance_count: 1,
}
const visualHubPayloadGuest = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  mode: 'guest',
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: visualGuestRows.length, rows: visualGuestRows },
    { id: 'auction_long_name', name: VISUAL_LONG_NAME, total: 1, rows: [guestDoublyHitRow] },
    { id: 'auction_early_star', name: '早盘之星', total: 0, rows: [] as typeof guestDoublyHitRow[] },
  ],
  resonance_count: 1,
}

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

    await expect(page.getByRole('heading', { name: '股池', exact: true })).toBeVisible()
    await expect(page.getByText('竞价策略 · 数据日期 2026-08-04 · 仅研究参考')).toBeVisible()

    // 两张策略卡片 + 当日池数
    const bullishCard = page.getByRole('button', { name: /竞价多头/ })
    await expect(bullishCard).toBeVisible()
    await expect(bullishCard.getByText('当日池', { exact: false })).toBeVisible()
    await expect(page.getByRole('button', { name: /当日池 2 只/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /当日池 1 只/ })).toBeVisible()

    // 明细表: VIP 六列头 + 默认第一个策略 (竞价多头, total=2) 的 footer 共 2 只
    const table = page.getByRole('table')
    await expect(table).toBeVisible()
    for (const header of ['代码', '名称', '开盘涨幅', '涨跌幅', '概念板块', '关联因子']) {
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

  test('guest mode renders banner, masked cells, and the 5-column guest set', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayloadGuest))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 横幅: 精确文案 + role=status
    const banner = page.getByRole('status').filter({ hasText: '游客模式：股票代码与名称已脱敏' })
    await expect(banner).toBeVisible()
    await expect(page.getByText('游客模式：股票代码与名称已脱敏')).toBeVisible()
    await expect(page.getByText('仅展示涨跌幅与概念板块。')).toBeVisible()

    // 5 列游客列头 — 无 开盘涨幅
    const table = page.getByRole('table')
    for (const header of ['代码', '名称', '涨跌幅', '概念板块', '关联因子']) {
      await expect(table.getByRole('columnheader', { name: header })).toBeVisible()
    }
    await expect(table.getByRole('columnheader', { name: '开盘涨幅' })).toHaveCount(0)

    // 脱敏单元格原样渲染: 2 行 × (代码+名称) = 4 处 ******
    await expect(page.getByText('******', { exact: true })).toHaveCount(4)
    await expect(page.getByText('300750', { exact: true })).toHaveCount(0)
    await expect(page.getByText('宁德时代', { exact: true })).toHaveCount(0)

    // footer 计数不变
    await expect(page.getByText(/共 2 只/)).toBeVisible()
    // 研究参考声明
    await expect(page.getByText('本页面仅用于研究参考，不提供任何交易执行功能。')).toBeVisible()
  })

  test('guest empty hub still renders the guest banner (session-policy state)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, emptyHubPayloadGuest))

    await page.goto('/pool-hub')

    await expect(page.getByRole('heading', { name: '当日无股池结果' })).toBeVisible()
    const banner = page.getByRole('status').filter({ hasText: '游客模式：股票代码与名称已脱敏' })
    await expect(banner).toBeVisible()
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

  test('vip mode renders 明文 with 名称 and 开盘涨幅', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 无游客横幅
    await expect(page.getByText('游客模式：股票代码与名称已脱敏')).toHaveCount(0)

    // VIP 6 列头
    const table = page.getByRole('table')
    for (const header of ['代码', '名称', '开盘涨幅', '涨跌幅', '概念板块', '关联因子']) {
      await expect(table.getByRole('columnheader', { name: header })).toBeVisible()
    }

    // 明文: 真实代码 + 名称 + 开盘涨幅 fmtPct
    await expect(page.getByText('300750', { exact: true })).toBeVisible()
    await expect(page.getByText('宁德时代', { exact: true })).toBeVisible()
    await expect(page.getByText('600519', { exact: true })).toBeVisible()
    await expect(page.getByText('贵州茅台', { exact: true })).toBeVisible()
    await expect(page.getByText('+2.34%', { exact: true })).toBeVisible()
    await expect(page.getByText('+1.05%', { exact: true })).toBeVisible()
  })

  test('guest↔vip mode switch toggles the 开盘涨幅 column from the server mode field', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    let hubCalls = 0
    const pageErrors: string[] = []
    page.on('pageerror', err => pageErrors.push(err.message))
    await page.route('**/api/pool/hub**', route => {
      hubCalls += 1
      // 第一次调用 = guest, 刷新后 = vip (mode 完全由服务端声明)
      if (hubCalls === 1) return json(route, hubPayloadGuest)
      return json(route, hubPayload)
    })

    await page.goto('/pool-hub')
    await expect(page.getByText('游客模式：股票代码与名称已脱敏')).toBeVisible()

    // guest: 5 列, 无 开盘涨幅
    let table = page.getByRole('table')
    await expect(table.getByRole('columnheader', { name: '开盘涨幅' })).toHaveCount(0)
    for (const header of ['代码', '名称', '涨跌幅', '概念板块', '关联因子']) {
      await expect(table.getByRole('columnheader', { name: header })).toBeVisible()
    }

    // 刷新 → 服务端改声明 vip → 横幅消失 + 6 列 + 明文
    await page.getByRole('button', { name: '刷新股池' }).click()
    await expect(page.getByText('游客模式：股票代码与名称已脱敏')).toHaveCount(0)
    table = page.getByRole('table')
    for (const header of ['代码', '名称', '开盘涨幅', '涨跌幅', '概念板块', '关联因子']) {
      await expect(table.getByRole('columnheader', { name: header })).toBeVisible()
    }
    await expect(page.getByText('300750', { exact: true })).toBeVisible()

    // 大量共享 ****** 身份的行不得触发 duplicate-key 或任何未捕获错误
    expect(pageErrors).toEqual([])
  })

  test('guest 交叉共振 badge and legend remain visible', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayloadGuest))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 交叉共振徽标 + legend 在游客模式仍渲染 (关联因子是策略标签, 非 PII)
    await expect(page.getByText(/交叉共振 · 2 策略/)).toBeVisible()
    await expect(page.getByText('交叉共振：被 ≥2 个竞价策略同时命中的个股')).toBeVisible()
    // 单命中行不渲染徽标
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
  test('pool page renders zero execution affordances (POOL-03)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/screener/strategies**', route => json(route, { presets: knownStrategies }))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 作用域限定在 main (布局侧边栏的「交易」导航不属于股池功能面)
    const main = page.getByRole('main')
    const EXECUTION_RE = /买入|卖出|委托|下单|交易|buy|sell|order|trade|execute/i
    await expect(main.getByRole('button', { name: EXECUTION_RE })).toHaveCount(0)
    await expect(main.getByRole('link', { name: EXECUTION_RE })).toHaveCount(0)

    // 研究参考声明
    await expect(page.getByText('本页面仅用于研究参考，不提供任何交易执行功能。')).toBeVisible()

    // 白名单: 股池页唯一交互 = 刷新 / 卡片钻取 / 概念输入 / 清除筛选
    const ALLOWED_RE = /刷新股池|当日池|当日无命中|数据不可用|清除筛选|清除概念筛选|重试|收起|\+\d+/
    const btnCount = await main.getByRole('button').count()
    for (let i = 0; i < btnCount; i++) {
      const btn = main.getByRole('button').nth(i)
      const name = (await btn.getAttribute('aria-label')) ?? (await btn.textContent()) ?? ''
      expect(name.trim(), `unexpected interactive control: ${name.trim()}`).toMatch(ALLOWED_RE)
    }
  })

  test('pool page never issues a mutating request (POOL-03)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    const captured: string[] = []
    page.on('request', r => {
      const url = new URL(r.url())
      if (url.pathname.startsWith('/api/')) captured.push(`${r.method()} ${url.pathname}`)
    })
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/screener/strategies**', route => json(route, { presets: knownStrategies }))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 交互: 刷新 / 概念输入 / 卡片钻取 — 全部只读
    await page.getByRole('button', { name: '刷新股池' }).click()
    await page.getByLabel('概念筛选').fill('新能源')
    await page.getByRole('button', { name: /盘前强势量化/ }).click()

    const nonGet = captured.filter(c => !/^GET /.test(c))
    expect(nonGet, `non-GET requests: ${nonGet.join(', ')}`).toEqual([])
    const execPaths = captured.filter(c => /order|trade|broker|portfolio|execution|deals/.test(c))
    expect(execPaths, `execution-family endpoints hit: ${execPaths.join(', ')}`).toEqual([])
  })

  test('pool page source contains no execution API call or form', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    const frontendRoot = process.cwd()
    const files = [
      'src/pages/PoolHubPage.tsx',
      'src/components/pool-hub/StrategyCardGrid.tsx',
      'src/components/pool-hub/ConceptFilter.tsx',
      'src/components/pool-hub/StockListTable.tsx',
    ]
    const EXEC_API_RE = /api\.\w*(order|trade|execute|broker|transaction|deals)\w*/i
    for (const f of files) {
      const src = readFileSync(path.join(frontendRoot, f), 'utf8')
      expect(src, `${f} contains <form>`).not.toMatch(/<form/i)
      expect(src, `${f} calls an execution-family API`).not.toMatch(EXEC_API_RE)
      expect(src, `${f} contains a mutating fetch verb`).not.toMatch(/fetch\([^)]*,\s*\{\s*method:\s*['"](POST|PUT|DELETE|PATCH)/)
    }
  })

  test('drill-down refresh failure renders inline 股池明细加载失败 alert with 重试', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    let hubCalls = 0
    await page.route('**/api/pool/hub**', route => {
      hubCalls += 1
      if (hubCalls === 1) return json(route, hubPayload)
      return json(route, { detail: '后台刷新失败' }, 500)
    })

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 刷新失败 (已有载荷) → 行内明细 alert, 页面不整体崩溃
    await page.getByRole('button', { name: '刷新股池' }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByText(/股池明细加载失败：后台刷新失败。请重试。/)).toBeVisible()
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible()
    // 卡片仍在
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()
  })

  test('accessibility and copy compliance on the pool surface', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, visualHubPayload))
    await page.route('**/api/screener/strategies**', route => json(route, { presets: knownStrategies }))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 可见 label 关联真实 input (aria-describedby 关联帮助文本)
    const input = page.getByLabel('概念筛选')
    await expect(page.locator('label[for="pool-concept-filter"]')).toBeVisible()
    await expect(input).toBeVisible()
    await expect(input).toHaveAttribute('placeholder', '输入概念名筛选…')
    await expect(input).toHaveAttribute('aria-describedby', 'pool-concept-filter-help')

    // 涨跌方向: 符号 + 颜色并存 (绝不只靠颜色)
    await expect(page.getByText('+2.34%', { exact: true })).toBeVisible()
    await expect(page.getByText('-0.12%', { exact: true })).toBeVisible()

    // 交叉共振行: accent 底色 + 左边框 + 徽标文本并存 (不只靠颜色)
    const resonanceRow = page.getByRole('row').filter({ hasText: '300750' })
    const rowClass = await resonanceRow.getAttribute('class')
    expect(rowClass ?? '').toContain('bg-accent')
    await expect(resonanceRow.getByText(/交叉共振 · 2 策略/)).toBeVisible()

    // Backstop 1: 数据不可用 卡片 40% 不透明度 + 无点击
    const unavailableCard = page.getByRole('button', { name: /动量增强/ })
    await expect(unavailableCard.getByText('数据不可用')).toBeVisible()
    const cardClass = await unavailableCard.getAttribute('class')
    expect(cardClass ?? '').toContain('opacity-40')
    await expect(unavailableCard).toBeDisabled()

    // Backstop 2: 长策略名 truncate (卡片名行)
    const longCard = page.getByRole('button', { name: new RegExp(VISUAL_LONG_NAME) })
    const nameSpan = longCard.locator('span').first()
    expect((await nameSpan.getAttribute('class')) ?? '').toContain('truncate')

    // Backstop 3: 缺失单元格渲染 — (开盘/概念/因子 3 处), 单命中行无徽标
    const missingRow = page.getByRole('row').filter({ hasText: '000001' })
    await expect(missingRow.getByText('—')).toHaveCount(3)
    await expect(missingRow.getByText(/交叉共振/)).toHaveCount(0)

    // Backstop 4: 多行在 overflow-x-auto 容器内滚动, 代码列不被截断
    const scrollContainer = page.getByRole('table').locator('..')
    const containerClass = await scrollContainer.getAttribute('class')
    expect(containerClass ?? '').toContain('overflow-x-auto')
    const codeCell = page.getByRole('cell', { name: /688981/ }).first()
    const codeCellClass = await codeCell.getAttribute('class')
    expect(codeCellClass ?? '').toContain('whitespace-nowrap')
    // Backstop 5: 长概念 chip truncate (展开后检查隐藏的长概念)
    await resonanceRow.getByRole('button', { name: '+3' }).click()
    const longChip = page.getByText('锂电池隔膜')
    const chipClass = await longChip.getAttribute('class')
    expect(chipClass ?? '').toContain('truncate')
  })

  test('captures visual evidence for the five UI-SPEC backstop scalars', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, visualHubPayload))
    await page.route('**/api/screener/strategies**', route => json(route, { presets: knownStrategies }))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()
    // 等 250ms motion reveal 完成, 截取稳定帧
    await page.waitForTimeout(400)

    // (1)(2) 卡片网格: populated + 数据不可用卡片 + 长名截断
    await expect(page.getByRole('region', { name: '策略卡片' })).toHaveScreenshot('pool-grid-populated.png', { maxDiffPixelRatio: 0.02 })
    // (3)(4) 明细表: 交叉共振行 + — 单元格 + 多行滚动容器
    await expect(page.getByRole('region', { name: /竞价多头 · 股池明细/ })).toHaveScreenshot('pool-table-resonance.png', { maxDiffPixelRatio: 0.02 })

    // 概念筛选激活: 筛选后 1 只 / 共 12 只 (客户端投影)
    await page.getByLabel('概念筛选').fill('新能源')
    await expect(page.getByText(/筛选后 1 只 \/ 共 12 只/)).toBeVisible()
    await page.waitForTimeout(300)
    await expect(page.getByRole('region', { name: /竞价多头 · 股池明细/ })).toHaveScreenshot('pool-table-filter-active.png', { maxDiffPixelRatio: 0.02 })

    // 零命中钻取空态
    await page.getByRole('button', { name: /清除筛选/ }).click()
    await page.getByRole('button', { name: /早盘之星/ }).click()
    await expect(page.getByRole('region', { name: /早盘之星 · 股池明细/ })).toBeVisible()
    await expect(page.getByRole('region', { name: /早盘之星 · 股池明细/ }).getByText('当日无命中')).toBeVisible()
    await page.waitForTimeout(300)
    await expect(page.getByRole('region', { name: /早盘之星 · 股池明细/ })).toHaveScreenshot('pool-empty-zero-hit.png', { maxDiffPixelRatio: 0.02 })

    // 数据不可用 卡片 (40% 不透明度 + tooltip)
    await expect(page.getByRole('button', { name: /动量增强/ })).toHaveScreenshot('pool-card-unavailable.png', { maxDiffPixelRatio: 0.02 })
  })

  test('frontend contains no client-side masking code (grep guard)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    const frontendRoot = process.cwd()
    const files = [
      'src/pages/PoolHubPage.tsx',
      'src/components/pool-hub/GuestModeBanner.tsx',
      'src/components/pool-hub/StockListTable.tsx',
      'src/components/pool-hub/ConceptFilter.tsx',
      'src/components/pool-hub/StrategyCardGrid.tsx',
      'src/lib/api.ts',
    ]
    // GUEST-01 / PITFALL #8: 生产源码零客户端掩码能力 —
    // 无掩码字面量, 无 row-value 模式推导, 无 mask 标识符/函数。
    const MASKED_LITERAL_RE = /\*{6,}/
    const ROW_MODE_DERIVATION_RE = /\.(?:code|symbol)\s*===\s*['"`]\*{6,}['"`]/
    const MASK_IDENT_RE = /\bmask/i
    for (const f of files) {
      const src = readFileSync(path.join(frontendRoot, f), 'utf8')
      expect(src, `${f} contains a masked literal`).not.toMatch(MASKED_LITERAL_RE)
      expect(src, `${f} derives guest mode from row values`).not.toMatch(ROW_MODE_DERIVATION_RE)
      expect(src, `${f} contains a masking function/constant`).not.toMatch(MASK_IDENT_RE)
    }
  })

  test('guest accessibility and copy contract', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayloadGuest))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 横幅 role=status + 可访问文本精确匹配 UI-SPEC
    const banner = page.getByRole('status').filter({ hasText: '游客模式：股票代码与名称已脱敏' })
    await expect(banner).toHaveAccessibleName('游客模式：股票代码与名称已脱敏，仅展示涨跌幅与概念板块。')

    // 脱敏单元格是真实文本节点 (非空、非 —), 且不携带任何身份泄露 affordance
    const maskedCells = page.getByText('******', { exact: true })
    await expect(maskedCells).toHaveCount(4)
    const cellCount = await maskedCells.count()
    for (let i = 0; i < cellCount; i++) {
      const cell = maskedCells.nth(i)
      await expect(cell).toBeVisible()
      await expect(cell).not.toBeEmpty()
      await expect(cell).not.toHaveText('—')
      expect(await cell.getAttribute('title'), `masked cell ${i} leaks via title`).toBeNull()
      expect(await cell.getAttribute('aria-label'), `masked cell ${i} leaks via aria-label`).toBeNull()
    }
  })

  test('captures visual evidence for guest mode backstops', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, visualHubPayloadGuest))
    await page.route('**/api/screener/strategies**', route => json(route, { presets: knownStrategies }))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()
    await page.waitForTimeout(400)

    // Backstop 1/2: 游客横幅与卡片网格共存; 长策略名仍 truncate
    await expect(page.getByRole('region', { name: '策略卡片' })).toHaveScreenshot('pool-guest-grid.png', { maxDiffPixelRatio: 0.02 })
    // 游客脱敏明细表 + 横幅
    await expect(page.getByRole('region', { name: /竞价多头 · 股池明细/ })).toHaveScreenshot('pool-guest-masked.png', { maxDiffPixelRatio: 0.02 })

    // Backstop 3: 大量共享脱敏身份的行保持视觉可区分 (行数 + footer 计数)
    const maskedCount = await page.getByText('******', { exact: true }).count()
    expect(maskedCount).toBeGreaterThanOrEqual(24)
    await expect(page.getByText(/共 12 只/)).toBeVisible()

    // Backstop 4: 服务端改声明 vip → 6 列明文, 无整页 reflow (刷新后覆盖路由)
    await page.route('**/api/pool/hub**', route => json(route, visualHubPayload))
    await page.getByRole('button', { name: '刷新股池' }).click()
    await expect(page.getByRole('columnheader', { name: '开盘涨幅' })).toBeVisible()
    await expect(page.getByText('300750', { exact: true })).toBeVisible()
    await page.waitForTimeout(300)
    await expect(page.getByRole('region', { name: /竞价多头 · 股池明细/ })).toHaveScreenshot('pool-vip-plaintext.png', { maxDiffPixelRatio: 0.02 })
  })
})
