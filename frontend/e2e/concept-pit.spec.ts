import type { Page, Route } from '@playwright/test'
import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

// ===== 共享 mock 载荷 (独立 spec — 复制 premarket-pool.spec.ts 常量/helpers, 不 import 跨文件耦合) =====
const HUB_AS_OF = '2026-08-04'
const HUB_UPDATED_AT = 1_754_310_000

/** 命中行 (pool-hub.spec doublyHitRow 形) — 明细表渲染所需, 概念徽标断言与其内容无关 */
const conceptRow = {
  symbol: '300750.SZ', code: '300750', name: '宁德时代', open_gap: 0.0234, change_pct: 0.0512,
  concept_board: ['新能源', '人工智能'], hit_factors: ['竞价多头', '盘前强势量化'], cross_resonance: true,
}

/** current_snapshot 载荷: 服务端冻结概念归属 = 当前快照 (无 concept_effective_date 键) */
const hubPayloadCurrentSnapshot = {
  as_of: HUB_AS_OF,
  updated_at: HUB_UPDATED_AT,
  mode: 'vip' as const,
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 1, rows: [conceptRow] },
  ],
  resonance_count: 0,
  auction_columns: { real: [] as string[], derived: ['open_gap'] },
  concept_attribution: 'current_snapshot',
}

/** unavailable 载荷: 概念数据源已安装但当前快照缺失/空 — 诚实警告 (与 current_snapshot 同文案) */
const hubPayloadUnavailable = {
  ...hubPayloadCurrentSnapshot,
  concept_attribution: 'unavailable',
}

/** as_of_snapshot 载荷: 历史日分区命中 (28-01) — 按日快照 + 概念数据生效日期 (CONCEPT-07) */
const historyPayloadAsOf = {
  as_of: HUB_AS_OF,
  updated_at: '2026-08-04T15:30:00+08:00',
  mode: 'vip' as const,
  strategies: [
    { id: 'auction_bullish', name: '竞价多头', total: 1, rows: [conceptRow] },
  ],
  resonance_count: 0,
  concept_attribution: 'as_of_snapshot',
  concept_effective_date: '2026-08-04',
  concept_captured_at: '2026-08-06T15:35:12+08:00',
}

/** 无快照日诚实空态 (200 语义, PIT-2) — history 兜底 + as_of 用例的 hub 覆盖 */
const missingSnapshotPayload = {
  as_of: null,
  available: false,
  strategies: [],
  resonance_count: 0,
  updated_at: null,
  mode: 'vip' as const,
}

/** 日期白名单 (FRONT-01): 2026-08-04 为最新日 — as_of_snapshot 用例经它导航到历史分区 */
const DATES_PAYLOAD = {
  dates: ['2026-08-04', '2026-08-01', '2026-07-31'],
  count: 3,
  latest: '2026-08-04',
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const unhandled = (route: Route) =>
  route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) })

/**
 * 应用外壳 fixture — 独立 spec 自足 (复制 premarket-pool.spec.ts installShell 全文, 不 import):
 * Layout 预取与全局轮询命中 mock, 未显式覆盖的 /api 请求大声失败 (暴露意外依赖)。
 * CONCEPT-04/07 默认路由: hub → current_snapshot 载荷; history → as_of 分发
 * (2026-08-04 → as_of_snapshot 载荷, 其他 → 诚实空态); dates 白名单含 2026-08-04。
 * 注: 不注册 /api/pool/premarket — 预览查询 500 → showPremarket 保持 false, 既有 hub 流正常渲染
 * (pool-hub.spec 同款外壳, 盘前空态不会压过 hub 流)。
 */
async function installShell(page: Page) {
  await page.route('**/api/**', unhandled)
  await page.route('**/api/settings', route => json(route, { onboarding_completed: true, theme: 'dark' }))
  await page.route('**/api/capabilities', route => json(route, { label: 'Free+', capabilities: {} }))
  await page.route('**/api/data/version', route => json(route, { version: 'phase28-browser' }))
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
  // CONCEPT-04/07: 日期白名单 + hub 默认 (current_snapshot) + history as_of 分发 (as_of_snapshot 载荷)
  await page.route('**/api/pool/dates**', route => json(route, DATES_PAYLOAD))
  await page.route('**/api/pool/hub**', route => json(route, hubPayloadCurrentSnapshot))
  await page.route('**/api/pool/history**', route => {
    const asOf = new URL(route.request().url()).searchParams.get('as_of') ?? ''
    const body = asOf === '2026-08-04' ? historyPayloadAsOf : missingSnapshotPayload
    return json(route, body)
  })
  await page.route('**/api/data/auction-probe**', route => json(route, {
    status: 'not_configured', source: null, probed_at: null,
    window: '09:15-09:25', fallback: 'open_gap', detail: '尚未配置竞价数据源',
  }))
  await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))
}

test.describe('Phase 28 concept pit (CONCEPT-04/07)', () => {
  test('current_snapshot 载荷 → 回退警告徽标 (概念归属为当前快照，非该日数据)', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)

    await page.goto('/pool-hub')

    // 实时 hub 视图: 概念归属 = 当前快照 (非该日数据) → 诚实警告徽标
    await expect(page.getByText('概念归属为当前快照，非该日数据')).toBeVisible()
    // 绝不出现「按当日快照」文案 (回退态不冒充 as_of_snapshot)
    await expect(page.getByText(/概念按当日快照/)).toHaveCount(0)
  })

  test('as_of_snapshot 载荷 → 按日文案 + 概念数据生效日期, 无回退徽标', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    // hub 覆盖为空态 — 本用例只测历史分区 (as_of_snapshot), 初始最新视图不渲染徽标
    await page.route('**/api/pool/hub**', route => json(route, missingSnapshotPayload))

    await page.goto('/pool-hub')

    // 经 DateNavigator 导航到历史日: 先选 2026-07-31 (确保 select value 真实变化 → change 事件必触发),
    // 再选 2026-08-04 → 触发 /api/pool/history?as_of=2026-08-04 (PIT-1 历史必走 history 端点)
    const dateSelect = page.getByRole('combobox', { name: '选择日期' })
    await dateSelect.selectOption('2026-07-31')
    await dateSelect.selectOption('2026-08-04')

    // 正向断言先行 (auto-wait 到历史载荷落地), 再断言回退徽标不出现 — 同一渲染 commit, 防 placeholder 竞态
    await expect(page.getByText('概念按当日快照 · 概念数据生效日期 2026-08-04')).toBeVisible()
    await expect(page.getByText('概念归属为当前快照，非该日数据')).toHaveCount(0)
  })

  test('unavailable 载荷 → 诚实警告徽标', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')
    await installShell(page)
    await page.route('**/api/pool/hub**', route => json(route, hubPayloadUnavailable))

    await page.goto('/pool-hub')

    // unavailable 与 current_snapshot 同文案 — 功能存在、数据缺失的真实诚实态
    await expect(page.getByText('概念归属为当前快照，非该日数据')).toBeVisible()
  })
})
