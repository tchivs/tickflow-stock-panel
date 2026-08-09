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

// ===== Phase 23 (FRONT-01/02): DateNavigator + 竞价列夹具 =====
const DATES_PAYLOAD = {
  dates: ['2026-08-04', '2026-08-01', '2026-07-31'],
  count: 3,
  latest: '2026-08-04',
}

/** 历史快照 (08-01): 与 hub (total 2) 不同的 total, 用于断言步进后卡片刷新 */
const historyPayload0801 = {
  as_of: '2026-08-01',
  updated_at: '2026-08-01T09:25:00+08:00',
  mode: 'vip',
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 5, rows: [doublyHitRow] },
  ],
  resonance_count: 0,
}

const historyPayload0731 = {
  as_of: '2026-07-31',
  updated_at: '2026-07-31T09:25:00+08:00',
  mode: 'vip',
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 1, rows: [singleHitRow] },
  ],
  resonance_count: 0,
}

/** 无快照日诚实空态 (200 语义, PIT-2): 无 reason 键, available:false */
const missingSnapshotPayload = {
  as_of: null,
  available: false,
  strategies: [],
  resonance_count: 0,
  updated_at: null,
  mode: 'vip',
  concept_attribution: 'current_snapshot',
}

// 竞价列 (FRONT-02/OQ-2): 服务端冻结声明 + 行级竞价值
const auctionRow = {
  symbol: '300750.SZ', code: '300750', name: '宁德时代',
  open_gap: 0.0234, change_pct: 0.0512,
  concept_board: ['新能源'], hit_factors: ['竞价多头'], cross_resonance: false,
  auction_volume: 1_234_567,
  auction_amount: 234_567_890,
  auction_volume_ratio: 2.35,
  auction_unmatched_amount: 12_345_678,
}
/** 行级 null: 列存在但该标的在分区缺席 (PIT-3 服务端声明消歧) */
const auctionNullRow = {
  symbol: '600519.SH', code: '600519', name: '贵州茅台',
  open_gap: 0.0105, change_pct: -0.0012,
  concept_board: ['白酒'], hit_factors: ['竞价多头'], cross_resonance: false,
  auction_volume: null,
  auction_amount: null,
  auction_volume_ratio: null,
  auction_unmatched_amount: null,
}
const auctionColumnsFull = {
  real: ['auction_volume', 'auction_amount'],
  derived: ['auction_volume_ratio', 'auction_unmatched_amount', 'open_gap'],
}
const auctionColumnsDerivedOnly = {
  real: [],
  derived: ['auction_volume_ratio', 'auction_unmatched_amount', 'open_gap'],
}
const auctionHubPayload = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  mode: 'vip',
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 2, rows: [auctionRow, auctionNullRow] },
  ],
  resonance_count: 0,
  auction_columns: auctionColumnsFull,
}
const auctionHubPayloadDerivedOnly = {
  ...auctionHubPayload,
  auction_columns: auctionColumnsDerivedOnly,
}
/** 历史快照 (08-01) 带真实竞价列 — 用于 H3 历史快照诚实断言 */
const auctionHistoryPayload0801 = {
  as_of: '2026-08-01',
  updated_at: '2026-08-01T09:25:00+08:00',
  mode: 'vip',
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 1, rows: [auctionRow] },
  ],
  resonance_count: 0,
  auction_columns: auctionColumnsFull,
}

const probePayloadAvailable = {
  status: 'available',
  source: 'kline_auction',
  probed_at: '2026-08-05T09:00:00+08:00',
  window: '09:15-09:25',
}
const probePayloadFailClosed = {
  status: 'fail_closed',
  source: null,
  probed_at: '2026-08-05T09:00:00+08:00',
  window: '09:15-09:25',
}

// ===== Phase 25 (WATCH-01..04): 自选清单夹具 (WatchlistEntry 对齐: symbol 全后缀 / added_at / note) =====
const watchlistEntry = (symbol: string) => ({ symbol, added_at: '2026-08-01T00:00:00', note: '' })
/** 自选含 300750.SZ (hub 双行中第一行) — VIP 星标/toggle/只看自选主夹具 */
const watchlistPayloadSingle = { symbols: [watchlistEntry('300750.SZ')] }
/** toggle 后缓存失效重取的集合 (含 600519.SH) */
const watchlistPayloadBoth = {
  symbols: [watchlistEntry('300750.SZ'), watchlistEntry('600519.SH')],
}
const watchlistPayloadEmpty = { symbols: [] }
/** 自选不含任何策略行 — 只看自选诚实空态 (P4 防线: 绝不渲染「无符合『』的个股」) */
const watchlistPayloadNoMatch = { symbols: [watchlistEntry('000001.SZ')] }

/** 本地时区今天的 ISO 串 — 用于「查看今日」盘前断言 (与应用 isToday 同机同 TZ) */
function localTodayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

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
  // Phase 23 (FRONT-01/02): 日期白名单 + 历史 as_of 只读 + 竞价 probe — 各用例按需覆盖 (后注册优先)
  await page.route('**/api/pool/dates**', route => json(route, DATES_PAYLOAD))
  await page.route('**/api/pool/history**', route => {
    const asOf = new URL(route.request().url()).searchParams.get('as_of') ?? ''
    const body = asOf === '2026-07-31' ? historyPayload0731 : historyPayload0801
    return json(route, body)
  })
  await page.route('**/api/data/auction-probe**', route => json(route, probePayloadFailClosed))
  // Phase 25 (WATCH-01..04): 默认 watchlist 空集 mock (P5) — VIP 用例自动发 GET /api/watchlist 时不落
  // `**/api/**` unhandled 500; 具体用例在 installShell 之后以更精确 route (`**/api/watchlist/batch` 等)
  // 后注册覆盖 (Playwright 后注册优先)。
  await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))
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

    await expect(page.getByRole('status').filter({ hasText: '股池加载中…' })).toBeVisible()
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

  test('vip name click opens StockPreviewDialog (watchlist-style detail popup)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    // 弹窗内日 K 请求 mock 成功 (2 根 K, 验证读屏数据摘要)
    await page.route('**/api/kline/daily**', route => json(route, {
      symbol: '300750.SZ', name: '宁德时代', source: 'mock', stock_info: { name: '宁德时代' },
      rows: [
        { date: '2026-08-06', open: 180, high: 185, low: 179, close: 184, volume: 100000 },
        { date: '2026-08-07', open: 184, high: 190, low: 183, close: 188, volume: 120000 },
      ],
    }))

    await page.goto('/pool-hub')
    await expect(page.getByText('宁德时代', { exact: true })).toBeVisible()

    // 点击名称 → 弹窗出现 (可观测锚点: 「竞价历史」toggle 仅 StockPreviewDialog 挂载时存在, 同 auction-history.spec)
    await page.getByRole('button', { name: /宁德时代/ }).click()
    await expect(page.getByRole('button', { name: '竞价历史' })).toBeVisible()

    // 弹窗内日K 图读屏可达: role=img + 数据摘要 aria-label (区间/收盘/涨跌幅)
    const dialog = page.locator('div.fixed.inset-0')
    await expect(dialog.getByRole('img', { name: /宁德时代.*日K 蜡烛图，2026-08-06 至 2026-08-07，共 2 根。最新收盘 188，较上一交易日 \+2\.17%/ })).toBeVisible()

    // 详情漏斗: 弹窗内「个股分析」链接直达 /stock-analysis (携带 symbol+name)
    // 侧边栏导航也有 个股分析 项 → 用弹窗遮罩层作用域消歧
    const escalate = page.locator('div.fixed.inset-0').getByRole('link', { name: /个股分析/ })
    await expect(escalate).toHaveAttribute('href', '/stock-analysis?symbol=300750.SZ&name=%E5%AE%81%E5%BE%B7%E6%97%B6%E4%BB%A3')

    // ESC 关闭 → 弹窗消失
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: '竞价历史' })).toHaveCount(0)
  })

  test('K-line chart keyboard zoom: focus + arrow keys pan and update aria-label', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    // 80 根 → 默认 visibleBars=60 初始窗口非全量 (start=25), 方向键平移才有效
    const rows = Array.from({ length: 80 }, (_, i) => {
      const d = new Date(Date.UTC(2026, 4, 1 + i)).toISOString().slice(0, 10)
      return { date: d, open: 100 + i, high: 105 + i, low: 98 + i, close: 102 + i, volume: 10000 }
    })
    await page.route('**/api/kline/daily**', route => json(route, { symbol: '300750.SZ', name: '宁德时代', source: 'mock', stock_info: { name: '宁德时代' }, rows }))

    await page.goto('/pool-hub')
    await page.getByRole('button', { name: /宁德时代/ }).click()
    const chart = page.locator('div.fixed.inset-0').getByRole('img', { name: /日K 蜡烛图/ })
    await expect(chart).toBeVisible()

    // 键盘可达: tabIndex 聚焦 + aria-keyshortcuts 声明; 初始 summary 无缩放区间
    await expect(chart).toHaveAttribute('tabindex', '0')
    await expect(chart).toHaveAttribute('aria-keyshortcuts', 'ArrowLeft ArrowRight PageUp PageDown Home End')
    await expect(chart).not.toHaveAttribute('aria-label', /当前显示/)

    await chart.focus()
    // 左移 → 可见区间变化并同步进读屏 label
    await page.keyboard.press('ArrowLeft')
    await expect(chart).toHaveAttribute('aria-label', /当前显示/)
    // 放大 (PageDown)
    await page.keyboard.press('PageDown')
    await expect(chart).toHaveAttribute('aria-label', /当前显示/)
    // Home 复位到初始窗口 (最近 60 根: 2026-05-20 至 2026-07-19)
    await page.keyboard.press('Home')
    await expect(chart).toHaveAttribute('aria-label', /当前显示 2026-05-20 至 2026-07-19/)
  })

  test('info-bar column drawer traps focus and restores it on ESC', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    // StockInfoBar 在 rows 为空时整行不渲染 → 必须给非空日K (2 根即可)
    await page.route('**/api/kline/daily**', route => json(route, {
      symbol: '300750.SZ', name: '宁德时代', source: 'mock', stock_info: { name: '宁德时代' },
      rows: [
        { date: '2026-08-06', open: 180, high: 185, low: 179, close: 184, volume: 100000 },
        { date: '2026-08-07', open: 184, high: 190, low: 183, close: 188, volume: 120000 },
      ],
    }))

    await page.goto('/pool-hub')
    await page.getByRole('button', { name: /宁德时代/ }).click()
    await expect(page.getByRole('button', { name: '竞价历史' })).toBeVisible()
    const trigger = page.getByRole('button', { name: /自定义信息条/ })
    await trigger.click()

    const drawer = page.getByRole('dialog', { name: '信息条指标' })
    await expect(drawer).toBeVisible()
    // 打开即捕获焦点到抽屉内首个可聚焦项 (标题栏关闭按钮)
    const focusInDrawer = () => page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      return el?.closest?.('[role="dialog"]')?.getAttribute('aria-label') === '信息条指标'
    })
    await expect.poll(focusInDrawer).toBe(true)
    // Tab 循环 8 次: 焦点始终不逃出抽屉 (WCAG 2.1.2 焦点不困住 = 模态必须困住)
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press('Tab')
      await expect.poll(focusInDrawer).toBe(true)
    }
    // ESC 关闭且焦点还原到触发按钮
    await page.keyboard.press('Escape')
    await expect(drawer).toHaveCount(0)
    await expect(trigger).toBeFocused()
  })

  test('drill-down table arrow-key roving row navigation', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    // 15 行 → PageDown/PageUp (步长 10) 可测中间行; VIP 行首控件 = 选择 checkbox
    const manyRows = Array.from({ length: 15 }, (_, i) => {
      const code = `6000${String(i).padStart(2, '0')}`
      return {
        symbol: `${code}.SH`, code, name: `测试股${String(i).padStart(2, '0')}`,
        open_gap: 0.01, change_pct: 0.01, concept_board: ['测试'], hit_factors: ['竞价多头'], cross_resonance: false,
      }
    })
    await page.route('**/api/pool/hub**', route => json(route, {
      as_of: HUB_AS_OF, updated_at: HUB_UPDATED_AT, mode: 'vip',
      strategies: [{ id: 'auction_bullish', name: '竞价多头', total: manyRows.length, rows: manyRows }],
      resonance_count: 0,
    }))

    await page.goto('/pool-hub')
    const tbody = page.locator('tbody')
    await expect(tbody.locator('tr')).toHaveCount(15)
    const row = (i: number) => tbody.locator('tr').nth(i)

    // 打开即 roving 停靠点在第 1 行 (tabIndex=0), 其余行 -1
    await expect(row(0)).toHaveAttribute('tabindex', '0')
    await expect(row(1)).toHaveAttribute('tabindex', '-1')
    await row(0).focus()
    await expect(row(0)).toBeFocused()

    // ↓ → 第 2 行 (roving 迁移)
    await page.keyboard.press('ArrowDown')
    await expect(row(1)).toBeFocused()
    await expect(row(1)).toHaveAttribute('tabindex', '0')
    await expect(row(0)).toHaveAttribute('tabindex', '-1')

    // End → 末行
    await page.keyboard.press('End')
    await expect(row(14)).toBeFocused()
    await expect(row(14)).toHaveAttribute('tabindex', '0')

    // ↑ → 倒数第 2 行
    await page.keyboard.press('ArrowUp')
    await expect(row(13)).toBeFocused()

    // Home → 首行
    await page.keyboard.press('Home')
    await expect(row(0)).toBeFocused()

    // PageDown 步长 10 → 第 11 行
    await page.keyboard.press('PageDown')
    await expect(row(10)).toBeFocused()

    // PageUp 回退 10 → 首行 (0 下限钳制)
    await page.keyboard.press('PageUp')
    await expect(row(0)).toBeFocused()

    // 行内 Tab: 第 1 行首控件 = 选择 checkbox; 行仍保持 roving 停靠点
    await page.keyboard.press('Tab')
    await expect(page.getByRole('checkbox', { name: '选择600000' })).toBeFocused()
  })

  test('preview dialog DatePicker arrow-key APG grid navigation', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/kline/daily**', route => json(route, { symbol: '300750.SZ', name: '宁德时代', rows: [], source: 'mock' }))

    await page.goto('/pool-hub')
    await page.getByRole('button', { name: /宁德时代/ }).click()
    await expect(page.getByRole('button', { name: '竞价历史' })).toBeVisible()

    const dialog = page.locator('div.fixed.inset-0')
    const pickers = dialog.getByRole('button', { name: /^\d{4}-\d{2}-\d{2}$/ })
    await expect(pickers).toHaveCount(2)
    await pickers.first().click()

    // 日期格断言辅助
    const cellLabel = () => page.evaluate(() => document.activeElement?.getAttribute('aria-label') ?? null)
    const parseLabel = (s: string) => {
      const m = /^(\d{4})年(\d{1,2})月(\d{1,2})日$/.exec(s)
      return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null
    }
    const fmtLabel = (d: Date) => `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
    const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
    const monday = (d: Date) => addDays(d, -((d.getDay() + 6) % 7))
    const pad2 = (n: number) => String(n).padStart(2, '0')
    const iso = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`

    // 打开后 roving tabindex 聚焦「选中日」 (tabIndex=0 单停靠点)
    const initial = await cellLabel()
    expect(initial).toMatch(/^\d{4}年\d{1,2}月\d{1,2}日$/)
    expect(await page.evaluate(() => (document.activeElement as HTMLElement)?.tabIndex)).toBe(0)

    // → 下一天
    await page.keyboard.press('ArrowRight')
    const d1 = await cellLabel()
    expect(parseLabel(d1)!.getTime()).toBe(parseLabel(initial)!.getTime() + 86_400_000)

    // ↓ +7 天 (同一列下行)
    await page.keyboard.press('ArrowDown')
    const d2 = await cellLabel()
    expect(parseLabel(d2)!.getTime()).toBe(parseLabel(d1)!.getTime() + 7 * 86_400_000)

    // Home → 当周周一
    await page.keyboard.press('Home')
    expect(await cellLabel()).toBe(fmtLabel(monday(parseLabel(d2)!)))

    // Enter 选中 → 日历关闭, 触发按钮显示新日期 (本周一)
    await page.keyboard.press('Enter')
    await expect(dialog.getByRole('button', { name: /^\d{4}年\d{1,2}月\d{1,2}日$/ })).toHaveCount(0)
    await expect(pickers.first()).toHaveText(iso(monday(parseLabel(d2)!)))
  })

  test('preview dialog DatePicker year-grid APG arrow-key navigation', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/kline/daily**', route => json(route, { symbol: '300750.SZ', name: '宁德时代', rows: [], source: 'mock' }))

    await page.goto('/pool-hub')
    await page.getByRole('button', { name: /宁德时代/ }).click()
    await expect(page.getByRole('button', { name: '竞价历史' })).toBeVisible()

    const dialog = page.locator('div.fixed.inset-0')
    const pickers = dialog.getByRole('button', { name: /^\d{4}-\d{2}-\d{2}$/ })
    await expect(pickers).toHaveCount(2)
    // 用「结束日期」picker: 只有 min 没有 max, 选远期年份后日格仍可用, 焦点可落
    await pickers.nth(1).click()

    const initial = (await pickers.nth(1).textContent())!
    const initialYear = Number(initial.slice(0, 4))

    // 进入年份选择
    const header = dialog.getByRole('button', { name: /^\d{4} 年 \d{1,2} 月$/ })
    await header.click()
    await expect(dialog.getByRole('button', { name: /^\d{4} - \d{4}$/ })).toBeVisible()

    const activeYear = () => page.evaluate(() => document.activeElement?.textContent?.trim() ?? null)

    // roving tabindex 落在「选中年」
    expect(Number(await activeYear())).toBe(initialYear)
    expect(await page.evaluate(() => (document.activeElement as HTMLElement)?.tabIndex)).toBe(0)

    // → +1 年; ↓ +4 年 (4 列网格同列下行); ↑ -4 回原位
    await page.keyboard.press('ArrowRight')
    expect(Number(await activeYear())).toBe(initialYear + 1)
    await page.keyboard.press('ArrowDown')
    expect(Number(await activeYear())).toBe(initialYear + 5)
    await page.keyboard.press('ArrowUp')
    expect(Number(await activeYear())).toBe(initialYear + 1)

    // Home → 批首; End → 批末 (viewYear±5/±6)
    await page.keyboard.press('Home')
    expect(Number(await activeYear())).toBe(initialYear - 5)
    await page.keyboard.press('End')
    expect(Number(await activeYear())).toBe(initialYear + 6)

    // Escape → 回日视图, 标题恢复「年 月」
    await page.keyboard.press('Escape')
    await expect(dialog.getByRole('button', { name: /^\d{4} 年 \d{1,2} 月$/ })).toBeVisible()

    // 再次进入 → PageDown 出批, 12 年批窗口平移, 焦点落新批末
    await dialog.getByRole('button', { name: /^\d{4} 年 \d{1,2} 月$/ }).click()
    await page.keyboard.press('PageDown')
    expect(Number(await activeYear())).toBe(initialYear + 12)
    await expect(dialog.getByRole('button', { name: new RegExp(`^${initialYear + 1} - ${initialYear + 12}$`) })).toBeVisible()

    // Enter 选中 → 回日视图, 视图切到选中年, 焦点回日格
    await page.keyboard.press('Enter')
    await expect(dialog.getByRole('button', { name: new RegExp(`^${initialYear + 12} 年 `) })).toBeVisible()
    expect(await page.evaluate(() => document.activeElement?.getAttribute('aria-label') ?? null)).toMatch(/^\d{4}年\d{1,2}月\d{1,2}日$/)
  })

  test('preview dialog: role=dialog + focus-on-open + Tab trap + focus return', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/kline/daily**', route => json(route, { symbol: '300750.SZ', name: '宁德时代', rows: [], source: 'mock' }))

    await page.goto('/pool-hub')
    await page.getByRole('button', { name: /宁德时代/ }).click()

    // 语义 + 打开即聚焦 (关闭按钮)
    const dialog = page.getByRole('dialog', { name: /个股详情 300750\.SZ/ })
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    await expect(dialog.getByRole('button', { name: '关闭' })).toBeFocused()

    // Tab 陷阱: 聚焦最后一个可聚焦元素后 Tab → 焦点仍留在对话框内
    await page.evaluate(() => {
      const panel = document.querySelector('[role="dialog"][aria-modal="true"]') as HTMLElement
      const f = Array.from(panel.querySelectorAll<HTMLElement>('button, a[href], [tabindex]:not([tabindex="-1"])'))
        .filter(el => el.getClientRects().length > 0)
      f[f.length - 1]?.focus()
    })
    await page.keyboard.press('Tab')
    const stillInDialog = await page.evaluate(() => {
      const panel = document.querySelector('[role="dialog"][aria-modal="true"]')
      return panel ? panel.contains(document.activeElement) : false
    })
    expect(stillInDialog).toBe(true)

    // 关闭 → 焦点还给触发元素
    await dialog.getByRole('button', { name: '关闭' }).click()
    await expect(page.getByRole('button', { name: /宁德时代/ })).toBeFocused()
  })

  test('light theme token contrast passes WCAG AA (muted/bull/bear/accent on surface)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.addInitScript(() => localStorage.setItem('tf-theme', 'light'))
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/kline/daily**', route => json(route, { symbol: '300750.SZ', name: '宁德时代', rows: [], source: 'mock' }))

    await page.goto('/pool-hub')
    await expect(page.getByText('宁德时代', { exact: true })).toBeVisible()

    // 计算实际渲染色的 WCAG 对比度 (token 级回归: :root 亮色 token 必须 ≥4.5:1 on surface)
    const ratios = await page.evaluate(() => {
      const probe = (sel: string) => {
        const el = document.querySelector(sel)
        if (!el) return null
        const color = getComputedStyle(el).color
        const rgb = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
        if (!rgb) return null
        return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])] as const
      }
      const lum = ([r, g, b]: readonly number[]) => {
        const f = (c: number) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
      }
      const ratio = (a: readonly number[], b: readonly number[]) => {
        const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x)
        return (hi + 0.05) / (lo + 0.05)
      }
      // 行内价格单元格 (text-bull) 与弹窗按钮 (text-accent) 覆盖两种 token 场景
      const bull = probe('.text-bull') ?? probe('.num.tabular-nums')
      const muted = probe('.text-muted')
      const accent = probe('.text-accent')
      const surface = getComputedStyle(document.body).backgroundColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)?.slice(1).map(Number) ?? [255, 255, 255]
      const bg = surface as readonly number[]
      return {
        bullOnSurface: bull ? ratio(bull, bg) : null,
        mutedOnSurface: muted ? ratio(muted, bg) : null,
        accentOnSurface: accent ? ratio(accent, bg) : null,
      }
    })
    for (const [name, r] of Object.entries(ratios)) {
      expect(r, `${name} contrast`).not.toBeNull()
      expect(r!, `${name} ≥ 4.5:1`).toBeGreaterThanOrEqual(4.5)
    }
  })

  test('keyboard Tab shows a visible focus ring (global :focus-visible)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')
    await expect(page.getByText('宁德时代', { exact: true })).toBeVisible()

    // 首个可聚焦元素是跳过链接, 再 Tab 一次到页面首个内容控件 (刷新股池按钮), 断言获得可见焦点环
    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: '跳到主要内容' })).toBeFocused()
    await page.keyboard.press('Tab')
    const outline = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement
      const s = getComputedStyle(el)
      return { tag: el.tagName, width: s.outlineWidth, style: s.outlineStyle }
    })
    expect(outline.style).not.toBe('none')
    expect(Number.parseFloat(outline.width)).toBeGreaterThan(0)
  })

  test('skip link jumps keyboard focus to main content (WCAG 2.4.1)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')
    await expect(page.getByText('宁德时代', { exact: true })).toBeVisible()

    await page.keyboard.press('Tab')
    const skip = page.getByRole('link', { name: '跳到主要内容' })
    await expect(skip).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.locator('main#main-content')).toBeFocused()
  })

  test('prefers-reduced-motion disables CSS animations globally (WCAG 2.3.3)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.emulateMedia({ reducedMotion: 'reduce' })

    await page.goto('/pool-hub')
    await expect(page.getByText('宁德时代', { exact: true })).toBeVisible()

    // 全局 CSS 重置: 任意元素的 spin 动画在 reduce 偏好下不得按原时长运行
    const duration = await page.evaluate(() => {
      const el = document.createElement('div')
      el.style.animation = 'spin 1s linear infinite'
      document.body.appendChild(el)
      const d = getComputedStyle(el).animationDuration
      el.remove()
      return d
    })
    expect(duration).not.toBe('1s')
  })

  test('preview dialog fits 375px viewport without horizontal overflow', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.setViewportSize({ width: 375, height: 800 })
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/kline/daily**', route => json(route, { symbol: '300750.SZ', name: '宁德时代', rows: [], source: 'mock' }))

    await page.goto('/pool-hub')
    await page.getByRole('button', { name: /宁德时代/ }).click()
    await expect(page.getByRole('button', { name: '竞价历史' })).toBeVisible()

    const overflow = await page.evaluate(() => {
      const panel = [...document.querySelectorAll('div')].find(d => d.classList.contains('w-[92vw]'))
      if (!panel) return null
      return { scrollW: panel.scrollWidth, clientW: panel.clientWidth, bodyScrollW: document.body.scrollWidth, winW: window.innerWidth }
    })
    expect(overflow).not.toBeNull()
    expect(overflow!.scrollW, 'dialog panel must not overflow horizontally').toBeLessThanOrEqual(overflow!.clientW)
    expect(overflow!.bodyScrollW, 'page must not overflow horizontally').toBeLessThanOrEqual(overflow!.winW)
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
    // (?!交易日): DateNavigator 步进 aria-label 含「交易日」, 非执行动作 — 排除误报
    const main = page.getByRole('main')
    const EXECUTION_RE = /买入|卖出|委托|下单|(?!交易日)交易|buy|sell|order|trade|execute/i
    await expect(main.getByRole('button', { name: EXECUTION_RE })).toHaveCount(0)
    await expect(main.getByRole('link', { name: EXECUTION_RE })).toHaveCount(0)

    // 研究参考声明
    await expect(page.getByText('本页面仅用于研究参考，不提供任何交易执行功能。')).toBeVisible()

    // 白名单: 股池页唯一交互 = 刷新 / 卡片钻取 / 概念输入 / 清除筛选 / DateNavigator 步进
    // WATCH-01/02/04 控件可访问名全部登记 (P1): 星标 移出自选/加入自选 + 开关 只看自选 + 批量加自选
    // WATCH-04 复选框列 (LG-04): checkbox 只允许 选择{6位code} / 全选
    // 名称列详情按钮: aria-label = 查看{名称}详情 → 打开只读个股弹窗 (Watchlist 同款交互, 非执行动作)
    const ALLOWED_RE = /刷新股池|当日池|当日无命中|数据不可用|清除筛选|清除概念筛选|重试|收起|\+\d+|上一个交易日|下一个交易日|最新|只看自选|批量加自选|加入自选|移出自选|选择\d{6}|全选|查看.{1,32}详情/
    const btnCount = await main.getByRole('button').count()
    for (let i = 0; i < btnCount; i++) {
      const btn = main.getByRole('button').nth(i)
      const name = (await btn.getAttribute('aria-label')) ?? (await btn.textContent()) ?? ''
      expect(name.trim(), `unexpected interactive control: ${name.trim()}`).toMatch(ALLOWED_RE)
    }
    // 并行 checkbox-name 循环: 新增可访问名必须登记 ALLOWED_RE, 守卫不弱化
    const cbCount = await main.getByRole('checkbox').count()
    for (let i = 0; i < cbCount; i++) {
      const cb = main.getByRole('checkbox').nth(i)
      const cbName = (await cb.getAttribute('aria-label')) ?? ''
      expect(cbName.trim(), `unexpected checkbox: ${cbName.trim()}`).toMatch(ALLOWED_RE)
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
    // POOL-03 语义放宽 (25-02): VIP 放行 watchlist 写族 (POST /api/watchlist[/batch], DELETE /api/watchlist/{symbol});
    // 但本用例不点击星标/批量 → watchlist 写也应为空; 其余 non-GET 仍必须为零 (guest 面由 WATCH-01 guest 用例锁死)。
    const watchlistWrites = nonGet.filter(c => /^POST \/api\/watchlist|^DELETE \/api\/watchlist/.test(c))
    const otherWrites = nonGet.filter(c => !/^POST \/api\/watchlist|^DELETE \/api\/watchlist/.test(c))
    expect(otherWrites, `non-watchlist non-GET requests: ${otherWrites.join(', ')}`).toEqual([])
    expect(watchlistWrites, `unexpected watchlist writes without star/batch click: ${watchlistWrites.join(', ')}`).toEqual([])
    const execPaths = captured.filter(c => /order|trade|broker|portfolio|execution|deals/.test(c))
    expect(execPaths, `execution-family endpoints hit: ${execPaths.join(', ')}`).toEqual([])
  })

  test('pool page source contains no execution API call or form', async ({ page: _page }, testInfo) => {
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
    // WATCH-04 复选框列前置后按文本内容定位代码格 (checkbox 格可访问名含 code 但无文本内容)
    const codeCell = page.getByRole('cell').filter({ hasText: '688981' })
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

  test('frontend contains no client-side masking code (grep guard)', async ({ page: _page }, testInfo) => {
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

  test('SC1: DateNavigator 步进/下拉/最新复位 + 历史必走 /api/pool/history (PIT-1)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    const historyDates: string[] = []
    page.on('request', r => {
      const url = new URL(r.url())
      if (url.pathname === '/api/pool/history') historyDates.push(url.searchParams.get('as_of') ?? '')
    })
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')

    // 初始: 最新日 subtitle; › (更近) disabled, ‹ (更早) enabled
    await expect(page.getByText('竞价策略 · 数据日期 2026-08-04 · 仅研究参考')).toBeVisible()
    const prevBtn = page.getByRole('button', { name: '上一个交易日' })
    const nextBtn = page.getByRole('button', { name: '下一个交易日' })
    await expect(nextBtn).toBeDisabled()
    await expect(prevBtn).toBeEnabled()

    // ‹ → 2026-08-01: subtitle 更新 + history 请求 + 卡片计数刷新 (mock 不同 total)
    await prevBtn.click()
    await expect(page.getByText('竞价策略 · 数据日期 2026-08-01 · 仅研究参考')).toBeVisible()
    await expect(page.getByRole('button', { name: /当日池 5 只/ })).toBeVisible()
    await expect(page.getByText(/共 5 只/)).toBeVisible()
    expect(historyDates).toContain('2026-08-01')
    // PIT-1: 最新日 (2026-08-04) 绝不打 history 端点; 历史绝不用 /hub?as_of= 反漂移
    expect(historyDates).not.toContain('2026-08-04')

    // 下拉选 2026-07-31 → subtitle + history 请求
    await page.getByRole('combobox', { name: '选择日期' }).selectOption('2026-07-31')
    await expect(page.getByText('竞价策略 · 数据日期 2026-07-31 · 仅研究参考')).toBeVisible()
    await expect(page.getByRole('button', { name: /当日池 1 只/ })).toBeVisible()
    await expect(page.getByText(/共 1 只/)).toBeVisible()
    expect(historyDates).toContain('2026-07-31')

    // ‹ 到最旧 (idx = length-1) → disabled
    await expect(prevBtn).toBeDisabled()

    // 「最新」→ 回 /api/pool/hub, subtitle 最新, 按钮消失
    await page.getByRole('button', { name: '最新' }).click()
    await expect(page.getByText('竞价策略 · 数据日期 2026-08-04 · 仅研究参考')).toBeVisible()
    await expect(page.getByRole('button', { name: '最新' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /当日池 2 只/ })).toBeVisible()
    await expect(nextBtn).toBeDisabled()
    await expect(prevBtn).toBeEnabled()
  })

  test('SC2: 白名单下拉 + available:false 空态先于零池短路 (PIT-2/PIT-5)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, emptyHubPayload))
    await page.route('**/api/pool/history**', route => {
      const asOf = new URL(route.request().url()).searchParams.get('as_of') ?? ''
      if (asOf === '2026-08-01') return json(route, missingSnapshotPayload)
      return json(route, historyPayload0801)
    })

    await page.goto('/pool-hub')

    // 零池日: 当日无股池结果 出现, 该日期无股池快照 不出现
    await expect(page.getByRole('heading', { name: '当日无股池结果' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '该日期无股池快照' })).toHaveCount(0)

    // 下拉只含 dates 白名单日期 (无白名单外/周末节假日日期)
    const select = page.getByRole('combobox', { name: '选择日期' })
    const options = select.locator('option')
    await expect(options).toHaveCount(3)
    expect(await options.allTextContents()).toEqual(['2026-08-04', '2026-08-01', '2026-07-31'])

    // ‹ → 08-01 (available:false) → 独立空态, 零池文案不出现, 无策略卡片/明细表
    await page.getByRole('button', { name: '上一个交易日' }).click()
    await expect(page.getByRole('heading', { name: '该日期无股池快照' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '当日无股池结果' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /当日池/ })).toHaveCount(0)
    await expect(page.getByRole('table')).toHaveCount(0)
  })

  test('SC2b: dates 为空 → 双按钮 disabled + 下拉 暂无历史日期', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/dates**', route => json(route, { dates: [], count: 0, latest: null }))
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')

    await expect(page.getByRole('button', { name: '上一个交易日' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '下一个交易日' })).toBeDisabled()
    const select = page.getByRole('combobox', { name: '选择日期' })
    await expect(select).toBeDisabled()
    await expect(select.locator('option')).toHaveText('暂无历史日期')
    // 最新 hub 查询照常
    await expect(page.getByRole('button', { name: /当日池 2 只/ })).toBeVisible()
  })

  test('SC3: 竞价列分组表头 + 单位 + tooltip + 行值 (真实 vs 派生)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, auctionHubPayload))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    const table = page.getByRole('table')
    // 组带
    await expect(table.getByRole('columnheader', { name: '真实集合竞价' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: '派生 · 虚拟成交' })).toBeVisible()
    // 成员列 (单位在列头)
    for (const header of ['竞价量（股）', '竞价金额（元）', '竞价量比（×）', '虚拟未匹配金额（元·估算）']) {
      await expect(table.getByRole('columnheader', { name: header })).toBeVisible()
    }
    // tooltip
    await expect(table.getByRole('columnheader', { name: '真实集合竞价' })).toHaveAttribute('title', /集合竞价撮合成交/)
    await expect(table.getByRole('columnheader', { name: '派生 · 虚拟成交' })).toHaveAttribute('title', /派生/)
    await expect(table.getByRole('columnheader', { name: '竞价量（股）' })).toHaveAttribute('title', /单位：股/)
    await expect(table.getByRole('columnheader', { name: '竞价量比（×）' })).toHaveAttribute('title', /前 5 日均量/)
    // 行值: fmtBigNum (万/亿) + 量比 toFixed(2)+'×'; 无涨跌色 (由单元格 class 承载)
    await expect(page.getByText('2.35×', { exact: true })).toBeVisible()
    await expect(page.getByText('123万', { exact: true })).toBeVisible()
    await expect(page.getByText('2.35亿', { exact: true })).toBeVisible()
    await expect(page.getByText('1235万', { exact: true })).toBeVisible()
    // 行级 null → — (列存在但该标的缺席)
    const nullRow = page.getByRole('row').filter({ hasText: '600519' })
    await expect(nullRow.getByText('—')).toHaveCount(4)
  })

  test('SC3b: real 空 → 真实组整组不渲染 + warning 徽标 + 派生组保留', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, auctionHubPayloadDerivedOnly))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    const table = page.getByRole('table')
    await expect(table.getByRole('columnheader', { name: '真实集合竞价' })).toHaveCount(0)
    await expect(table.getByRole('columnheader', { name: '竞价量（股）' })).toHaveCount(0)
    await expect(table.getByRole('columnheader', { name: '竞价金额（元）' })).toHaveCount(0)
    // 派生组保留
    await expect(table.getByRole('columnheader', { name: '派生 · 虚拟成交' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: '竞价量比（×）' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: '虚拟未匹配金额（元·估算）' })).toBeVisible()
    // warning 徽标 (默认 probe fail_closed) — 诚实: 仅派生列
    await expect(page.getByText('竞价数据未接入，仅展示派生列')).toBeVisible()
  })

  test('SC3c: guest 载荷 → 无竞价列/无分组表头/无徽标', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayloadGuest))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    const table = page.getByRole('table')
    await expect(table.getByRole('columnheader', { name: '真实集合竞价' })).toHaveCount(0)
    await expect(table.getByRole('columnheader', { name: '竞价量（股）' })).toHaveCount(0)
    await expect(table.getByRole('columnheader', { name: '派生 · 虚拟成交' })).toHaveCount(0)
    await expect(page.getByText('竞价数据可用 · 窗口 09:15-09:25')).toHaveCount(0)
    await expect(page.getByText('竞价数据未接入，仅展示派生列')).toHaveCount(0)
    // 既有 5 列结构不变
    for (const header of ['代码', '名称', '涨跌幅', '概念板块', '关联因子']) {
      await expect(table.getByRole('columnheader', { name: header })).toBeVisible()
    }
  })

  test('SC4a: probe available + real 非空 → info 徽标', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, auctionHubPayload))
    await page.route('**/api/data/auction-probe**', route => json(route, probePayloadAvailable))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()
    await expect(page.getByText('竞价数据可用 · 窗口 09:15-09:25')).toBeVisible()
  })

  test('SC4b: probe fail_closed + real 空 → warning 徽标', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, auctionHubPayloadDerivedOnly))
    await page.route('**/api/data/auction-probe**', route => json(route, probePayloadFailClosed))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()
    await expect(page.getByText('竞价数据未接入，仅展示派生列')).toBeVisible()
  })

  test('SC4c: 查看今日 + 非交易时段 → 盘前 secondary 行', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, { ...auctionHubPayload, as_of: localTodayISO() }))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()
    await expect(page.getByText('盘前/休市 · 竞价窗口 09:15-09:25 未开始')).toBeVisible()
    // info 徽标仍并列 (real 非空)
    await expect(page.getByText('竞价数据可用 · 窗口 09:15-09:25')).toBeVisible()
  })

  test('SC4d: 历史快照诚实 (H3) — 今日 probe fail_closed 不抹掉历史真实竞价列', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/pool/history**', route => {
      const asOf = new URL(route.request().url()).searchParams.get('as_of') ?? ''
      if (asOf === '2026-08-01') return json(route, auctionHistoryPayload0801)
      return json(route, historyPayload0801)
    })
    await page.route('**/api/data/auction-probe**', route => json(route, probePayloadFailClosed))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 步进到历史日 (08-01, real 非空)
    await page.getByRole('button', { name: '上一个交易日' }).click()
    await expect(page.getByText('竞价策略 · 数据日期 2026-08-01 · 仅研究参考')).toBeVisible()

    // 今日 probe fail_closed, 但历史快照 real 非空 → 真实竞价列仍渲染 (H3 双轨)
    const table = page.getByRole('table')
    await expect(table.getByRole('columnheader', { name: '真实集合竞价' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: '竞价量（股）' })).toBeVisible()
    await expect(page.getByText('2.35×', { exact: true })).toBeVisible()
    // 徽标按 auction_columns.real 显示 info, 不被今日 probe 状态重写
    await expect(page.getByText('竞价数据可用 · 窗口 09:15-09:25')).toBeVisible()
  })

  // ===== Phase 25 (WATCH-01..04): 自选联动 =====

  test('WATCH-01: VIP 星标渲染 + toggle 调 POST /api/watchlist + 共享缓存失效重取', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    let watchlistGetCount = 0
    const addBodies: { symbol: string }[] = []
    await page.route('**/api/watchlist**', route => {
      const req = route.request()
      const url = new URL(req.url())
      if (req.method() === 'GET' && url.pathname === '/api/watchlist') {
        watchlistGetCount += 1
        // 第一次返回 仅 300750.SZ; 缓存失效后的重取返回 both → 600519 星标翻转 (WATCH-03)
        return json(route, watchlistGetCount === 1 ? watchlistPayloadSingle : watchlistPayloadBoth)
      }
      if (req.method() === 'POST' && url.pathname === '/api/watchlist') {
        addBodies.push(JSON.parse(req.postData() ?? '{}') as { symbol: string })
        return json(route, watchlistPayloadBoth)
      }
      return unhandled(route)
    })

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 星标渲染: 300750 行在自选 (移出自选), 600519 行不在 (加入自选)
    const row300 = page.getByRole('row').filter({ hasText: '300750' })
    const row600 = page.getByRole('row').filter({ hasText: '600519' })
    await expect(row300.getByTitle('移出自选')).toBeVisible()
    await expect(row600.getByTitle('加入自选')).toBeVisible()

    // 点 600519 星标 → POST /api/watchlist body.symbol=600519.SH
    const getsBefore = watchlistGetCount
    await row600.getByTitle('加入自选').click()
    await expect.poll(() => addBodies.length).toBe(1)
    expect(addBodies[0].symbol).toBe('600519.SH')

    // 星标翻转 + 出现第二次 GET /api/watchlist (WATCH-03 共享 key 失效重取, I1 计数式避免 exact-count 脆弱)
    await expect.poll(() => watchlistGetCount).toBeGreaterThan(getsBefore)
    await expect(row600.getByTitle('移出自选')).toBeVisible()
  })

  test('WATCH-01 guest: 零 watchlist 查询 + 零自选控件/switch', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    const captured: string[] = []
    page.on('request', r => {
      const url = new URL(r.url())
      if (url.pathname.startsWith('/api/')) captured.push(`${r.method()} ${url.pathname}`)
    })
    await page.route('**/api/pool/hub**', route => json(route, hubPayloadGuest))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // guest 零 /api/watchlist 查询 (若误发则 401 全局跳登录, 页面早失败 — WATCH-01 guest 语义锁死)
    expect(captured.filter(c => c.includes('/api/watchlist'))).toEqual([])

    // main 内零自选控件 + 零 switch (guest 逐像素不变的面)
    const main = page.getByRole('main')
    await expect(main.getByTitle('加入自选')).toHaveCount(0)
    await expect(main.getByTitle('移出自选')).toHaveCount(0)
    await expect(main.getByRole('switch')).toHaveCount(0)
    // WATCH-04 复选框列 VIP-only (LG-04): guest 表内零 checkbox (游客零控件契约, T-35-02-03)
    await expect(page.getByRole('table').getByRole('checkbox')).toHaveCount(0)
  })

  test('WATCH-02: 只看自选收窄到自选行 + total 权威不变', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/watchlist**', route => json(route, watchlistPayloadSingle))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()
    const table = page.getByRole('table')
    await expect(table.getByRole('row')).toHaveCount(3) // header + 2 行
    await expect(page.getByText(/共 2 只/)).toBeVisible()

    // 开「只看自选」→ 仅剩 300750 行
    await page.getByRole('switch', { name: '只看自选' }).click()
    await expect(table.getByRole('row')).toHaveCount(2) // header + 1 行
    await expect(page.getByText('300750', { exact: true })).toBeVisible()
    await expect(page.getByText('600519', { exact: true })).toHaveCount(0)
    await expect(page.getByText(/筛选后 1 只 \/ 共 2 只/)).toBeVisible()

    // 关开关 → 2 行恢复
    await page.getByRole('switch', { name: '只看自选' }).click()
    await expect(table.getByRole('row')).toHaveCount(3)
    await expect(page.getByText(/共 2 只/)).toBeVisible()
  })

  test('WATCH-02: 诚实空态 — 自选不含策略行时显示专属文案 (P4)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/watchlist**', route => json(route, watchlistPayloadNoMatch))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()
    await expect(page.getByText(/共 2 只/)).toBeVisible()

    // 开开关 → 诚实空态 (绝不渲染「无符合『』的个股」— filterText 空时文案荒谬, P4 防线)
    await page.getByRole('switch', { name: '只看自选' }).click()
    await expect(page.getByText('自选清单中无该策略个股')).toBeVisible()
    await expect(page.getByText('试试关闭「只看自选」或切换策略。')).toBeVisible()
    await expect(page.getByText(/无符合/)).toHaveCount(0)

    // 关开关 → 行恢复
    await page.getByRole('switch', { name: '只看自选' }).click()
    await expect(page.getByText('自选清单中无该策略个股')).toHaveCount(0)
    await expect(page.getByText(/共 2 只/)).toBeVisible()
  })

  test('WATCH-02: 历史同构 — 开关跨日期保持生效, footer 按历史 total 权威', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/watchlist**', route => json(route, watchlistPayloadSingle))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 先开开关 (hub 2 行, 自选含 300750 → 筛选后 1 只 / 共 2 只)
    await page.getByRole('switch', { name: '只看自选' }).click()
    await expect(page.getByText(/筛选后 1 只 \/ 共 2 只/)).toBeVisible()

    // 切历史 2026-08-01 (historyPayload0801: 竞价多头 total 5, rows [300750])
    await page.getByRole('button', { name: '上一个交易日' }).click()
    await expect(page.getByText('竞价策略 · 数据日期 2026-08-01 · 仅研究参考')).toBeVisible()
    // 开关保持生效 + footer 按历史 total 权威 (H1/H7: 最新/历史天然同构)
    await expect(page.getByRole('switch', { name: '只看自选' })).toHaveAttribute('aria-checked', 'true')
    await expect(page.getByText(/筛选后 1 只 \/ 共 5 只/)).toBeVisible()
  })

  test('WATCH-04: 批量加自选 body = 可见行 symbols + 成功 toast', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/watchlist**', route => json(route, watchlistPayloadEmpty))
    let batchBody: { symbols: string[] } | null = null
    await page.route('**/api/watchlist/batch', route => {
      batchBody = JSON.parse(route.request().postData() ?? '{}') as { symbols: string[] }
      return json(route, { symbols: [], added: 2 })
    })

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // WATCH-04 scope=选中行 (LG-04): 先全选可见行 → 批量加自选 → POST /api/watchlist/batch body.symbols = 可见行 (300750 + 600519)
    await page.getByRole('checkbox', { name: '全选' }).check()
    await page.getByRole('button', { name: '批量加自选' }).click()
    await expect.poll(() => batchBody !== null).toBe(true)
    // 顺序不敏感集合比较 (WATCH-04: body 恰为可见行 symbol 数组)
    expect(new Set(batchBody!.symbols)).toEqual(new Set(['300750.SZ', '600519.SH']))
    // 成功 toast (mock 返回 added:2)
    await expect(page.getByText(/已添加 2 只到自选/)).toBeVisible()

    // watchlistOnly 开启 → 批量按钮隐藏 (D6: 可见行全在自选; 只断言按钮 — 行 checkbox 保留可见是允许的)
    await page.getByRole('switch', { name: '只看自选' }).click()
    await expect(page.getByRole('button', { name: '批量加自选' })).toHaveCount(0)
  })

  test('WATCH-04: 勾选单行批量加自选 — body=选中行 + toast', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/watchlist**', route => json(route, watchlistPayloadEmpty))
    let batchBody: { symbols: string[] } | null = null
    await page.route('**/api/watchlist/batch', route => {
      batchBody = JSON.parse(route.request().postData() ?? '{}') as { symbols: string[] }
      return json(route, { symbols: [], added: 1 })
    })

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 勾选单行 300750 → 批量加自选 → body.symbols 恰为选中行 (单元素保序)
    await page.getByRole('checkbox', { name: '选择300750' }).check()
    await expect(page.getByRole('button', { name: '批量加自选' })).toBeEnabled()
    await page.getByRole('button', { name: '批量加自选' }).click()
    await expect.poll(() => batchBody !== null).toBe(true)
    expect(batchBody!.symbols).toEqual(['300750.SZ'])
    // 成功 toast (mock 返回 added:1)
    await expect(page.getByText(/已添加 1 只到自选/)).toBeVisible()
  })

  test('WATCH-04: 全选可见行 + 空选禁用', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/watchlist**', route => json(route, watchlistPayloadEmpty))
    let batchBody: { symbols: string[] } | null = null
    await page.route('**/api/watchlist/batch', route => {
      batchBody = JSON.parse(route.request().postData() ?? '{}') as { symbols: string[] }
      return json(route, { symbols: [], added: 2 })
    })

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 初始空选 → 批量按钮禁用
    await expect(page.getByRole('button', { name: '批量加自选' })).toBeDisabled()

    // 表头全选 → 两行均勾选 + aria-checked=true; 批量按钮启用 (click: 每次触发 change → toggle)
    const selectAll = page.getByRole('checkbox', { name: '全选' })
    await expect(selectAll).toHaveAttribute('aria-checked', 'false')
    await selectAll.click()
    await expect(selectAll).toHaveAttribute('aria-checked', 'true')
    await expect(page.getByRole('checkbox', { name: '选择300750' })).toBeChecked()
    await expect(page.getByRole('checkbox', { name: '选择600519' })).toBeChecked()
    await expect(page.getByRole('button', { name: '批量加自选' })).toBeEnabled()

    await page.getByRole('button', { name: '批量加自选' }).click()
    await expect.poll(() => batchBody !== null).toBe(true)
    // 顺序不敏感集合比较 (WATCH-04: body 恰为可见行 symbol 数组)
    expect(new Set(batchBody!.symbols)).toEqual(new Set(['300750.SZ', '600519.SH']))

    // 再点全选 → 全不选 + 按钮回到禁用
    await selectAll.click()
    await expect(selectAll).toHaveAttribute('aria-checked', 'false')
    await expect(page.getByRole('checkbox', { name: '选择300750' })).not.toBeChecked()
    await expect(page.getByRole('button', { name: '批量加自选' })).toBeDisabled()
  })

  test('WATCH-04: 切换策略清空选中 (无跨视图 stale selection)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/watchlist**', route => json(route, watchlistPayloadEmpty))

    await page.goto('/pool-hub')
    await expect(page.getByRole('button', { name: /竞价多头/ })).toBeVisible()

    // 勾选 300750 → 切策略 (盘前强势量化, 行 = 300750 交叉共振) → 选择被清空 (T-35-02-05)
    await page.getByRole('checkbox', { name: '选择300750' }).check()
    await expect(page.getByRole('checkbox', { name: '选择300750' })).toBeChecked()
    await page.getByRole('button', { name: /盘前强势量化/ }).click()
    await expect(page.getByText('盘前强势量化 · 股池明细')).toBeVisible()
    await expect(page.getByRole('checkbox', { name: '选择300750' })).not.toBeChecked()
    // 批量按钮回到空选禁用 — stale 选择不残留
    await expect(page.getByRole('button', { name: '批量加自选' })).toBeDisabled()
  })
})

// ===== 移动端 e2e 契约 (mobile-chromium-320) — 补全 phase1 之外的移动覆盖 (ResponsiveAudit P2) =====
// 设计规范: 移动端触控目标 ≥44px (h-11); 页面/弹窗不得横向溢出。
test.describe('Phase 18 mobile contracts @320', () => {
  const MOBILE_PROJECT = 'mobile-chromium-320'

  test('hub fits 320px and star toggle hit-area ≥ 44×44', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== MOBILE_PROJECT, 'mobile-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))

    await page.goto('/pool-hub')
    await expect(page.getByText('宁德时代', { exact: true })).toBeVisible()

    // 无横向溢出 (表内可滚动, 但 document 不得水平滚动)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    expect(overflow, 'hub must not overflow viewport horizontally').toBeLessThanOrEqual(0)

    // 星标触控目标 ≥ 44×44 (DESIGN §触控)
    const star = page.getByRole('button', { name: '加入自选' }).first()
    const box = await star.boundingBox()
    expect(box, 'star button must be visible').not.toBeNull()
    expect(box!.width).toBeGreaterThanOrEqual(44)
    expect(box!.height).toBeGreaterThanOrEqual(44)
  })

  test('preview dialog no overflow + DatePicker trigger ≥ 44px tall at 320', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== MOBILE_PROJECT, 'mobile-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayload))
    await page.route('**/api/kline/daily**', route => json(route, { symbol: '300750.SZ', name: '宁德时代', rows: [], source: 'mock' }))

    await page.goto('/pool-hub')
    await page.getByRole('button', { name: /宁德时代/ }).click()
    await expect(page.getByRole('button', { name: '竞价历史' })).toBeVisible()

    // 弹窗面板不横向溢出
    const panelOverflow = await page.evaluate(() => {
      const panel = [...document.querySelectorAll('div')].find(d => d.classList.contains('w-[92vw]'))
      return panel ? panel.scrollWidth - panel.clientWidth : null
    })
    expect(panelOverflow, 'dialog panel must not overflow').not.toBeNull()
    expect(panelOverflow!).toBeLessThanOrEqual(0)

    // 日期选择触发按钮 (移动端 max-md:min-h-11) — CSS 契约: min-height 44px; box 允许亚像素取整
    const picker = page.locator('div.fixed.inset-0').getByRole('button', { name: /^\d{4}-\d{2}-\d{2}$/ }).first()
    const box = await picker.boundingBox()
    expect(box, 'DatePicker trigger must be visible').not.toBeNull()
    expect(box!.height, 'touch target ≈ 44px (subpixel)').toBeGreaterThanOrEqual(43.5)
    const minH = await picker.evaluate(el => getComputedStyle(el).minHeight)
    expect(minH).toBe('44px')
  })
})
