import type { Locator, Page, Route } from '@playwright/test'
import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'
const SHADOW_HEADING = 'Shadow 成交证据与策略候选'
const THESIS_TAB = '投资论点'
const FORECAST_TAB = '概率预测'
const STOCK = { symbol: '600519.SH', name: '贵州茅台' }
const LONG_ID = `sha256:${'a'.repeat(96)}`

const SCENARIO_TITLES = [
  'scenario 1: 独立能力与 v1 不回归',
  'scenario 2: SHDW-01 不可变导入',
  'scenario 3: SHDW-01 explainability 与资格',
  'scenario 4: Shadow stale/terminal/long content',
  'scenario 5: THES-01 版本与估值锚',
  'scenario 6: THES-01 evidence checks',
  'scenario 7: THES-01 人工权威',
  'scenario 8: FORE-01 approved checkpoint gate',
  'scenario 9: FORE-01 概率结果',
  'scenario 10: Forecast immutable/stale/terminal',
  'scenario 11: Later calibration',
  'scenario 12: Responsive、keyboard、contrast 与 reduced motion',
  'scenario 13: 跨模块无权威副作用',
] as const

type ModuleName = 'shadow' | 'thesis' | 'forecast'
type ModuleAvailability = Record<ModuleName, boolean>
type FixtureOptions = {
  availability?: Partial<ModuleAvailability>
  shadowState?: 'empty' | 'populated' | 'stale' | 'terminal' | 'partial'
  thesisState?: 'empty' | 'populated' | 'pending' | 'conflict'
  forecastState?: 'empty' | 'populated' | 'stale' | 'terminal' | 'partial'
  chartFailure?: boolean
  forecastGate?: 'verified' | 'missing' | 'pair_mismatch' | 'digest_mismatch' | 'calendar_short' | 'coverage_short'
}

type Telemetry = {
  apiRequests: string[]
  externalRequests: string[]
  mutationBodies: Array<{ method: string; path: string; body: unknown }>
  requestsFor(pathPrefix: string): number
}

const defaultAvailability: ModuleAvailability = { shadow: true, thesis: true, forecast: true }
const capability = (name: ModuleName, available: boolean) => ({
  available,
  code: available ? `${name}_available` : `${name}_dependency_missing`,
  reason: available ? `${name} production service is available` : `${name} optional dependency is unavailable`,
  install_hint: available ? 'No action required' : `Enable the ${name} optional deployment capability`,
})

const shadowBatch = (id: string, label: string, overrides: Record<string, unknown> = {}) => ({
  id,
  label,
  original_filename: `${label}-超长但必须完整显示的本地成交记录.csv`,
  source_label: '本地券商导出',
  imported_by: 'server-session-user',
  created_at: '2026-07-15T09:00:00Z',
  content_digest: LONG_ID,
  mapping_version: 'shadow-map-v1',
  total_rows: 5,
  valid_rows: 4,
  invalid_rows: 1,
  duplicate_groups: 1,
  partial_fills: 2,
  same_content_as: null,
  supersedes_batch_id: null,
  status: 'completed',
  diagnostics: ['第 5 行费用字段缺失，该行未纳入证据集。'],
  ...overrides,
})

const candidate = {
  id: 'candidate-server-1',
  label: '候选 S-001',
  evidence_set_id: 'evidence-server-1',
  evidence_fingerprint: LONG_ID,
  eligibility: 'eligible',
  rules: [{ if: 'close > ma20 且 volume_ratio >= 1.50', then: 'enter', support: 0.42, precision: 0.71, recall: 0.63 }],
  features: ['close', 'ma20', 'volume_ratio'],
  parameters: { max_depth: 3, min_samples_leaf: 20 },
  assumptions: ['退出规则证据有限，固定最长持有 20 个交易日。'],
  source_batch_ids: ['batch-server-1'],
  limitations: ['样本只覆盖一个完整市场周期，不能推断实盘收益。'],
  seed: 17,
  class_balance: { positive: 40, negative: 60 },
  in_sample: { run_id: 'is-run-1', start: '2024-01-02', end: '2024-06-28', status: 'passed', precision: 0.72, recall: 0.64, coverage: 0.58, trades: 24, return: 0.12, drawdown: -0.05, after_cost: 0.09, actual_consistency: 0.68 },
  out_of_sample: { run_id: 'oos-run-1', start: '2024-07-01', end: '2024-12-31', status: 'passed', precision: 0.66, recall: 0.57, coverage: 0.49, trades: 18, return: 0.07, drawdown: -0.04, after_cost: 0.05, actual_consistency: 0.61 },
}

const thesisVersion = (version: number, overrides: Record<string, unknown> = {}) => ({
  id: `thesis-version-${version}`,
  instrument: STOCK.symbol,
  version,
  predecessor_id: version === 1 ? null : `thesis-version-${version - 1}`,
  official_status: 'active',
  core_judgment: '高端白酒品牌力与渠道质量仍支持长期现金流，但估值必须保留安全边际。',
  rationale: '治理后的财务与渠道证据支持当前判断，同时需求恢复节奏仍有不确定性。',
  change_reason: version === 1 ? '建立首版研究账本' : '追加年度报告证据并调整估值区间',
  created_by: 'server-session-user',
  created_at: `2026-07-${10 + version}T09:00:00Z`,
  effective_at: `2026-07-${10 + version}T09:00:00Z`,
  anchors: [{ method: 'DCF', currency: 'CNY', as_of: '2026-07-15', low: 1380, high: 1720, assumptions: ['收入复合增长 8%', '终值增长 3%'], limitations: ['未计入极端渠道库存冲击'] }],
  conditions: [
    { id: `condition-${version}-1`, name: '核心单品批价跌破阈值', source_kind: 'market', field: 'wholesale_price', operator: '<', threshold: 850, unit: 'CNY', lookback: 20, cadence: 'weekly', timezone: 'Asia/Shanghai', next_due_at: '2026-07-22T01:00:00Z' },
    { id: `condition-${version}-2`, name: '经营现金流恶化', source_kind: 'financial', field: 'operating_cash_flow_yoy', operator: '<', threshold: -0.2, unit: 'ratio', lookback: 4, cadence: 'quarterly', timezone: 'Asia/Shanghai', next_due_at: '2026-10-01T01:00:00Z' },
  ],
  ...overrides,
})

const thesisChecks = [
  { id: 'check-matched', condition_id: 'condition-2-1', version_id: 'thesis-version-2', due_at: '2026-07-14T01:00:00Z', checked_at: '2026-07-14T01:02:00Z', result: 'matched', observed_value: 840, unit: 'CNY', cadence: 'weekly', evidence_label: '受治理批价快照', evidence_fingerprint: LONG_ID },
  { id: 'check-not-matched', condition_id: 'condition-2-1', version_id: 'thesis-version-2', due_at: '2026-07-07T01:00:00Z', checked_at: '2026-07-07T01:01:00Z', result: 'not_matched', observed_value: 880, unit: 'CNY', cadence: 'weekly', evidence_label: '受治理批价快照', evidence_fingerprint: LONG_ID },
  { id: 'check-insufficient', condition_id: 'condition-2-2', version_id: 'thesis-version-2', due_at: '2026-07-01T01:00:00Z', checked_at: '2026-07-01T01:03:00Z', result: 'insufficient_evidence', observed_value: null, unit: 'ratio', cadence: 'quarterly', evidence_label: '缺少已披露季度值', evidence_fingerprint: LONG_ID },
  { id: 'check-error', condition_id: 'condition-2-2', version_id: 'thesis-version-2', due_at: '2026-04-01T01:00:00Z', checked_at: '2026-04-01T01:04:00Z', result: 'error', observed_value: null, unit: 'ratio', cadence: 'quarterly', evidence_label: '安全检查错误', evidence_fingerprint: LONG_ID },
]

const pending = {
  id: 'pending-server-1',
  instrument: STOCK.symbol,
  version_id: 'thesis-version-2',
  condition_id: 'condition-2-1',
  check_id: 'check-matched',
  condition_name: '核心单品批价跌破阈值',
  observed_value: 840,
  threshold: 850,
  unit: 'CNY',
  evidence_label: '受治理批价快照',
  evidence_at: '2026-07-14T01:02:00Z',
  evidence_fingerprint: LONG_ID,
  official_status: 'active',
}

const forecastPaths = Array.from({ length: 32 }, (_, pathIndex) => ({
  id: `path-${String(pathIndex + 1).padStart(2, '0')}`,
  seed_label: `seed-17-${pathIndex + 1}`,
  warnings: pathIndex === 3 ? ['volume is economically unusual'] : [],
  rows: Array.from({ length: 20 }, (_, dayIndex) => ({
    session: `2026-08-${String(dayIndex + 1).padStart(2, '0')}`,
    open: 1450 + pathIndex + dayIndex,
    high: 1460 + pathIndex + dayIndex,
    low: 1440 + pathIndex + dayIndex,
    close: 1455 + pathIndex + dayIndex,
    volume: 100000 + pathIndex * 100 + dayIndex,
  })),
}))
const quantiles = Array.from({ length: 20 }, (_, index) => ({
  session: `2026-08-${String(index + 1).padStart(2, '0')}`,
  p10: 1410 + index,
  p50: 1480 + index,
  p90: 1560 + index,
  unit: 'CNY',
}))
const forecastRecord = {
  id: 'forecast-record-1',
  label: '预测 F-001',
  instrument: STOCK.symbol,
  created_at: '2026-07-15T09:00:00Z',
  as_of: '2026-07-15',
  horizon: 20,
  status: 'completed',
  checkpoint: { catalog_id: 'kronos-mini-approved', model: 'Kronos-mini', tokenizer: 'Kronos-Tokenizer-2k', source_revision: '67b630e', model_revision: 'f4e6869', tokenizer_revision: '26966d0', digest: LONG_ID, pairing: 'mini/2k', max_context: 2048, device: 'cpu', integrity: 'verified' },
  input: { fingerprint: LONG_ID, coverage_start: '2024-01-02', coverage_end: '2026-07-15', session_count: 512, schema: 'daily OHLCV' },
  sample_count: 32,
  quantiles,
  paths: forecastPaths,
  warnings: ['第 4 条路径成交量存在经济关系 warning，原值未被静默修正。'],
  calibration: [
    { horizon: 5, status: 'evaluated', actual_session: '2026-07-22', actual_value: 1492, close_mae: 12.4, interval_coverage: 1, p10_pinball: 2.1, p50_pinball: 4.2, p90_pinball: 1.7, sample_count: 1, coverage_start: '2026-07-22', coverage_end: '2026-07-22' },
    { horizon: 20, status: 'pending', target_session: '2026-08-12' },
    { horizon: 60, status: 'unevaluable', reason: 'missing_actual' },
  ],
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function installPhase5Fixture(page: Page, options: FixtureOptions = {}): Promise<Telemetry> {
  const availability = { ...defaultAvailability, ...options.availability }
  const apiRequests: string[] = []
  const externalRequests: string[] = []
  const mutationBodies: Array<{ method: string; path: string; body: unknown }> = []
  let batchCounter = 3
  let forecastCounter = 1
  const batches = [
    shadowBatch('batch-server-3', '修正批次 3', { supersedes_batch_id: 'batch-server-1' }),
    shadowBatch('batch-server-2', '同内容批次 2', { same_content_as: 'batch-server-1' }),
    shadowBatch('batch-server-1', '原始批次 1'),
  ]
  const versions = [thesisVersion(2), thesisVersion(1)]
  const records = [forecastRecord]

  page.on('request', request => {
    const url = new URL(request.url())
    const local = url.hostname === '127.0.0.1' || url.hostname === 'localhost'
    const existingFont = ['rsms.me', 'fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname)
    if (!local && !existingFont) externalRequests.push(request.url())
    if (url.pathname.startsWith('/api/')) {
      apiRequests.push(`${request.method()} ${url.pathname}`)
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
        let body: unknown = request.postData()
        try { body = request.postDataJSON() } catch { /* multipart remains opaque */ }
        mutationBodies.push({ method: request.method(), path: url.pathname, body })
      }
    }
  })

  await page.route('**/api/**', route => json(route, { detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }, 500))
  await page.route('**/api/settings', route => json(route, { onboarding_completed: true, theme: 'dark' }))
  await page.route('**/api/analysis/subjects/**/reports', route => json(route, { reports: [{ id: 'existing-report', subject: { kind: 'stock', key: STOCK.symbol }, version: 1, status: 'validated', generated_at: '2026-07-10T00:00:00Z', evidence_limitations: [] }] }))
  await page.route('**/api/analysis/reports/existing-report', route => json(route, { report: { id: 'existing-report', signal_id: 'existing-signal', subject: { kind: 'stock', key: STOCK.symbol }, version: 1, status: 'validated', generated_at: '2026-07-10T00:00:00Z', perspectives: [], score: null, valuation: null, ic_memo: { thesis: '既有分析仍可读取', risks: [], open_questions: [] } } }))
  await page.route('**/api/analysis/reports/existing-report/evidence', route => json(route, { report_id: 'existing-report', sources: [], material_numbers: [] }))
  await page.route('**/api/analysis/signals/existing-signal/history', route => json(route, { signal_id: 'existing-signal', current_state: null, events: [], pending_review_id: null, reviews: [], plans: [] }))
  await page.route('**/api/screener/strategies**', route => json(route, { presets: [{ id: 'registered-demo', name: '既有策略回测', description: 'completed v1 fixture', source: 'builtin' }] }))
  await page.route('**/api/strategies/registered-demo', route => json(route, { id: 'registered-demo', name: '既有策略回测', description: 'completed v1 fixture', source: 'builtin', tags: [], version: '1', basic_filter: {}, params: [], params_defaults: {}, scoring: {}, entry_signals: [], exit_signals: [], stop_loss: null, take_profit: null, trailing_stop: null, trailing_take_profit_activate: null, trailing_take_profit_drawdown: null, max_hold_days: null, alerts: [], order_by: 'score', descending: true, limit: 20 }))
  await page.route('**/api/strategies', route => json(route, { presets: [{ id: 'registered-demo', name: '既有策略回测', description: 'completed v1 fixture', source: 'builtin' }] }))
  await page.route('**/api/research**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/experiments')) return json(route, { experiments: [] })
    if (path.endsWith('/comparison/candidates')) return json(route, { experiments: [] })
    if (path.endsWith('/factors')) return json(route, { factors: [] })
    return json(route, {})
  })
  await page.route('**/api/intraday/stream', route => route.fulfill({ contentType: 'text/event-stream', body: 'event: stream_ready\ndata: {}\n\n' }))

  await page.route('**/api/optional-modules', route => json(route, { modules: { shadow: capability('shadow', availability.shadow), thesis: capability('thesis', availability.thesis), forecast: capability('forecast', availability.forecast) } }))
  await page.route('**/api/shadow/**', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (!availability.shadow) return json(route, { detail: capability('shadow', false) }, 503)
    if (path.endsWith('/capability')) return json(route, capability('shadow', true))
    if (path.endsWith('/batches') && request.method() === 'GET') return json(route, { batches: options.shadowState === 'empty' ? [] : batches })
    if (path.endsWith('/imports/preview')) return json(route, { preview_id: 'preview-server-1', original_filename: 'executions.csv', format: 'CSV', timezone: 'Asia/Shanghai', mapping: [{ target: 'symbol', source: '证券代码', sample: '600519.SH', unit_timezone: '代码', status: 'mapped' }], rows: [{ symbol: STOCK.symbol, side: 'buy', executed_at: '2026-07-15T09:31:00+08:00', quantity: 100, price: 1450 }], diagnostics: [] })
    if (path.endsWith('/imports/confirm')) { batchCounter += 1; return json(route, { batch: shadowBatch(`batch-server-${batchCounter}`, `不可变批次 ${batchCounter}`) }, 201) }
    if (path.endsWith('/evidence-sets')) return request.method() === 'POST' ? json(route, { evidence_set: { id: 'evidence-server-1', included_batch_ids: ['batch-server-1'], excluded_trade_ids: [], trade_count: 4, duplicate_groups: 1, partial_fills: 2, fingerprint: LONG_ID, created_at: '2026-07-15T09:10:00Z' } }, 201) : json(route, { evidence_sets: [{ id: 'evidence-server-1', fingerprint: LONG_ID, batch_count: 1, trade_count: 4 }] })
    if (path.includes('/candidates') && path.endsWith('/retain')) return json(route, { retention: { id: 'retention-server-1', candidate_id: candidate.id, status: 'retained_research_only', created_at: '2026-07-15T09:30:00Z' } }, 201)
    if (path.endsWith('/candidates')) return json(route, { candidates: options.shadowState === 'empty' ? [] : [candidate] })
    if (path.endsWith('/runs')) return json(route, { runs: options.shadowState === 'terminal' ? [{ id: 'run-timeout', status: 'timeout', reason: 'time limit reached' }, { id: 'run-resource', status: 'resource_terminated', reason: 'memory limit reached' }] : [] })
    return json(route, { detail: `Unhandled Shadow fixture route: ${path}` }, 500)
  })

  await page.route('**/api/theses/**', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (!availability.thesis) return json(route, { detail: capability('thesis', false) }, 503)
    if (path.endsWith('/capability')) return json(route, capability('thesis', true))
    if (path.endsWith('/versions') && request.method() === 'GET') return json(route, { versions: options.thesisState === 'empty' ? [] : versions, current_version_id: 'thesis-version-2' })
    if (path.endsWith('/versions') && request.method() === 'POST') return json(route, { version: thesisVersion(3) }, 201)
    if (path.endsWith('/checks')) return json(route, { checks: thesisChecks })
    if (path.endsWith('/pending')) return json(route, { pending: options.thesisState === 'pending' || options.thesisState === 'conflict' ? [pending] : [] })
    if (path.endsWith('/confirm') || path.endsWith('/reject')) {
      if (options.thesisState === 'conflict') return json(route, { detail: 'state changed' }, 409)
      return json(route, { review: { id: 'review-server-1', decision: path.endsWith('/confirm') ? 'confirmed' : 'rejected', principal: 'server-session-user', reason: '人工理由完整保留', created_at: '2026-07-15T10:00:00Z' }, official_status: path.endsWith('/confirm') ? 'invalidated' : 'active' })
    }
    return json(route, { detail: `Unhandled Thesis fixture route: ${path}` }, 500)
  })

  await page.route('**/api/forecast/**', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (!availability.forecast) return json(route, { detail: capability('forecast', false) }, 503)
    if (path.endsWith('/capability')) return json(route, capability('forecast', true))
    if (path.endsWith('/catalog')) {
      const gate = options.forecastGate ?? 'verified'
      return json(route, { entries: gate === 'missing' ? [] : [{ ...forecastRecord.checkpoint, integrity: gate, available: gate === 'verified', reason: gate === 'verified' ? null : gate }] })
    }
    if (path.endsWith('/records') && request.method() === 'GET') return json(route, { records: options.forecastState === 'empty' ? [] : records })
    if (path.endsWith('/jobs') && request.method() === 'POST') { forecastCounter += 1; return json(route, { job: { id: `forecast-job-${forecastCounter}`, status: 'completed', stage: '已完成', record_id: `forecast-record-${forecastCounter}`, created_at: '2026-07-15T10:00:00Z' } }, 201) }
    if (path.includes('/records/') && path.endsWith('/paths')) return json(route, { paths: forecastPaths, total: 32, page: 1, page_size: 12 })
    if (path.includes('/records/') && path.endsWith('/calibration')) return json(route, { calibration: forecastRecord.calibration })
    if (path.includes('/records/')) return json(route, { record: forecastRecord })
    if (path.includes('/jobs/')) return json(route, { job: { id: 'forecast-job-1', status: options.forecastState === 'terminal' ? 'timeout' : 'completed', stage: options.forecastState === 'terminal' ? 'resource_terminated' : '已完成', safe_reason: options.forecastState === 'terminal' ? 'time limit reached' : null, record_id: options.forecastState === 'terminal' ? null : forecastRecord.id } })
    return json(route, { detail: `Unhandled Forecast fixture route: ${path}` }, 500)
  })
  await page.route('**/api/forecast/jobs/**/stream', route => route.fulfill({ contentType: 'text/event-stream', body: options.forecastState === 'terminal' ? 'event: forecast_progress\ndata: {"job_id":"forecast-job-1","stage":"resource_terminated","status":"timeout"}\n\n' : 'event: forecast_progress\ndata: {"job_id":"forecast-job-1","stage":"completed","status":"completed","record_id":"forecast-record-1"}\n\n' }))

  return {
    apiRequests,
    externalRequests,
    mutationBodies,
    requestsFor: pathPrefix => apiRequests.filter(value => value.includes(pathPrefix)).length,
  }
}

function futurePhase5Ui(testInfo: import('@playwright/test').TestInfo) {
  test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium owns the explicit viewport/theme matrix')
  test.fail(true, 'Phase 05 production panels are delivered by Plans 05-15 and 05-16')
}

async function requireSurface(locator: Locator) {
  await expect(locator).toBeVisible({ timeout: 750 })
}

async function selectStock(page: Page) {
  await page.addInitScript(stock => localStorage.setItem('last_stock:stock-analysis', JSON.stringify(stock)), STOCK)
}

async function openAnalysisTab(page: Page, name: string) {
  const tab = page.getByRole('tab', { name, exact: true })
  await requireSurface(tab)
  await tab.click()
  await expect(tab).toHaveAttribute('aria-selected', 'true')
  await expect(tab).toHaveAttribute('tabindex', '0')
  return page.getByRole('tabpanel', { name, exact: true })
}

async function expectSemanticTable(panel: Locator, caption: string) {
  const table = panel.getByRole('table', { name: caption })
  await expect(table).toBeVisible()
  await expect(table.locator('caption')).toContainText(caption)
  expect(await table.getByRole('columnheader').count()).toBeGreaterThan(0)
  const overflow = table.locator('xpath=..')
  await expect(overflow).toHaveAttribute('tabindex', '0')
  await expect(overflow).toHaveAttribute('aria-describedby')
}

async function expectTouchTarget(locator: Locator) {
  const box = await locator.boundingBox()
  expect(box, 'control must have rendered geometry').not.toBeNull()
  expect(box!.width).toBeGreaterThanOrEqual(44)
  expect(box!.height).toBeGreaterThanOrEqual(44)
}

async function contrastRatio(locator: Locator): Promise<number> {
  return locator.evaluate(element => {
    const parse = (color: string) => color.match(/[\d.]+/g)!.slice(0, 3).map(Number)
    const luminance = (rgb: number[]) => {
      const linear = rgb.map(channel => {
        const value = channel / 255
        return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
      })
      return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    }
    const style = getComputedStyle(element)
    const foreground = luminance(parse(style.color))
    let parent: Element | null = element
    let background = [0, 0, 0]
    while (parent) {
      const candidate = getComputedStyle(parent).backgroundColor
      const values = candidate.match(/[\d.]+/g)?.map(Number) ?? []
      if (values.length >= 3 && (values[3] ?? 1) > 0) { background = values.slice(0, 3); break }
      parent = parent.parentElement
    }
    const backgroundLuminance = luminance(background)
    return (Math.max(foreground, backgroundLuminance) + 0.05) / (Math.min(foreground, backgroundLuminance) + 0.05)
  })
}

function expectNoAuthorityRequests(telemetry: Telemetry) {
  const serialized = JSON.stringify(telemetry.mutationBodies)
  for (const field of ['principal', 'reviewer_principal', 'fingerprint', 'digest', 'verdict', 'official_status', 'quantiles', 'paths', 'checkpoint_revision']) {
    expect(serialized).not.toContain(`"${field}"`)
  }
  expect(telemetry.apiRequests.filter(path => /broker|market-action|positions\/sync|monitor-rules|decision\/runs|strategies\/install/.test(path))).toEqual([])
  expect(telemetry.externalRequests).toEqual([])
}

test.describe('Phase 05 optional enhancement browser contracts', () => {
  test(SCENARIO_TITLES[0], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    for (const availability of [
      { shadow: true, thesis: true, forecast: true },
      { shadow: false, thesis: true, forecast: true },
      { shadow: true, thesis: false, forecast: true },
      { shadow: true, thesis: true, forecast: false },
      { shadow: false, thesis: false, forecast: false },
    ]) {
      const telemetry = await installPhase5Fixture(page, { availability })
      await page.goto('/backtest')
      const shadow = page.getByRole('heading', { name: SHADOW_HEADING, exact: true })
      await requireSurface(shadow)
      await expect(page.getByRole('tab', { name: '策略回测' })).toBeVisible()
      await expect(page.getByText('现有回测、研究库和 v1 工作流仍可使用。')).toHaveCount(availability.shadow ? 0 : 1)

      await selectStock(page)
      await page.goto('/stock-analysis')
      const thesisTab = page.getByRole('tab', { name: THESIS_TAB, exact: true })
      const forecastTab = page.getByRole('tab', { name: FORECAST_TAB, exact: true })
      await expect(thesisTab).toBeEnabled()
      await expect(forecastTab).toBeEnabled()
      await expect(page.getByRole('tab', { name: '分析结论' })).toBeVisible()
      await expect(page.getByRole('tab', { name: '来源与核验' })).toBeVisible()
      await expect(page.getByRole('tab', { name: '信号历史' })).toBeVisible()
      await expect(page.getByRole('navigation').getByText(/Shadow|投资论点|概率预测|可选模块总览/)).toHaveCount(0)
      await expect(page.locator('aside').filter({ hasText: /高级研究中心|可选模块总览/ })).toHaveCount(0)
      expect(telemetry.externalRequests).toEqual([])
    }
  })

  test(SCENARIO_TITLES[1], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { shadowState: 'populated' })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
    await expect(panel.getByText('仅从本地实际成交日志形成研究证据，不连接券商、不同步持仓、不执行交易。')).toBeVisible()
    await expect(panel.getByText(/支持.*CSV.*XLSX.*大小.*行数.*Asia\/Shanghai/)).toBeVisible()
    const file = panel.getByLabel('选择本地成交日志')
    await file.setInputFiles({ name: 'executions.csv', mimeType: 'text/csv', buffer: Buffer.from('symbol,side,time,quantity,price\n600519.SH,buy,2026-07-15 09:31,100,1450') })
    await expect(panel.getByRole('status')).toContainText(/executions\.csv|正在解析日志/)
    await expectSemanticTable(panel, 'Shadow 字段映射预览')
    await expect(panel.getByText('仅为预览')).toBeVisible()
    await expect(panel.getByText(/重复组/)).toBeVisible()
    await expect(panel.getByText(/partial fill|部分成交/i)).toBeVisible()
    await panel.getByRole('button', { name: '确认不可变导入' }).click()
    const dialog = page.getByRole('dialog', { name: '确认不可变导入' })
    await expect(dialog).toContainText(/原文件名|来源标签|时区|映射|行数|不可覆写/)
    await dialog.getByRole('button', { name: '确认不可变导入' }).click()
    await expectSemanticTable(panel, 'Shadow 不可变导入批次')
    for (const text of ['原始批次 1', '同内容批次 2', '修正批次 3', 'same content', '修正自']) await expect(panel.getByText(text).first()).toBeVisible()
    await expect(panel.getByText(/1 行未纳入/)).toBeVisible()
    await expect(panel.getByText(/\/tmp\/|C:\\|account_secret|broker_token|raw_path/i)).toHaveCount(0)
    const evidence = await panel.getByRole('button', { name: '创建新证据集' })
    await evidence.click()
    await expect(panel.getByText(LONG_ID)).toBeVisible()
    expect(telemetry.mutationBodies.some(entry => entry.path.endsWith('/imports/confirm'))).toBeTruthy()
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[2], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { shadowState: 'populated' })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
    for (const text of ['close > ma20', 'volume_ratio', 'max_depth', '退出规则证据有限', 'seed', 'class balance', '样本内', '样本外', LONG_ID]) {
      await expect(panel.getByText(new RegExp(text, 'i')).first()).toBeVisible()
    }
    await expectSemanticTable(panel, 'Shadow 候选规则与限制')
    await expectSemanticTable(panel, 'Shadow 样本内与样本外证据')
    const retain = panel.getByRole('button', { name: '保留为 Shadow 研究候选' })
    await expect(retain).toBeEnabled()
    await retain.click()
    const dialog = page.getByRole('dialog', { name: '保留为 Shadow 研究候选' })
    await expect(dialog).toContainText('不会注册或启用策略，也不会创建监控、计划或市场动作。')
    await dialog.getByRole('button', { name: '保留为 Shadow 研究候选' }).click()
    await expect(panel.getByRole('status')).toContainText(/研究候选|已保留/)
    await expect(page.getByRole('button', { name: /启用策略|同步持仓|添加监控|生成交易计划|据此交易/ })).toHaveCount(0)
    expect(telemetry.mutationBodies.filter(entry => entry.path.endsWith('/retain'))).toHaveLength(1)
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[3], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { shadowState: 'terminal' })
    await page.setViewportSize({ width: 375, height: 844 })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
    await expect(panel.getByText('存在较新成交批次；当前候选仍基于已冻结证据。')).toBeVisible()
    await expect(panel.getByText('Shadow 候选蒸馏失败')).toBeVisible()
    await expect(panel.getByText('Shadow 样本内/样本外评估失败')).toBeVisible()
    await expect(panel.getByText(/timeout|resource_terminated/)).toHaveCount(2)
    await expect(panel.getByRole('button', { name: '基于相同证据集创建新蒸馏运行' })).toBeVisible()
    await expect(panel.getByRole('button', { name: '创建新评估运行' })).toBeVisible()
    await expect(panel.getByText(new RegExp('a{40}'))).toBeVisible()
    const identifier = panel.getByText(LONG_ID).first()
    expect(await identifier.evaluate(element => getComputedStyle(element).overflowWrap)).toMatch(/anywhere|break-word/)
    const table = panel.getByRole('table').first()
    const wrapper = table.locator('xpath=..')
    await expect(wrapper).toHaveAttribute('tabindex', '0')
    await wrapper.focus()
    await page.keyboard.press('End')
    await expect(wrapper).toBeFocused()
    expect((await panel.boundingBox())!.width).toBeLessThanOrEqual(375)
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[4], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { thesisState: 'populated' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, THESIS_TAB)
    await expect(panel.getByRole('heading', { name: THESIS_TAB, exact: true })).toBeVisible()
    await expect(panel.getByText(`${STOCK.name} ${STOCK.symbol}`)).toBeVisible()
    await expect(panel.getByText('自动检查只能提出待确认结论，不能替你改变论点状态。')).toBeVisible()
    await panel.getByRole('button', { name: '基于此版本创建新版本' }).click()
    await panel.getByLabel('估值下限').fill('1720')
    await panel.getByLabel('估值上限').fill('1380')
    await panel.getByRole('button', { name: '进入审阅' }).click()
    await expect(panel.getByRole('alert')).toContainText(/上限.*不得低于下限/)
    await expect(panel.getByLabel('估值下限')).toBeFocused()
    await panel.getByLabel('估值下限').fill('1380')
    await panel.getByLabel('估值上限').fill('1720')
    await expect(panel.getByLabel('估值币种')).toHaveValue('CNY')
    await expect(panel.getByLabel('估值截至日')).toHaveValue('2026-07-15')
    await expect(panel.getByLabel(/估值假设/)).not.toHaveValue('')
    await expect(panel.getByLabel('条件 1 检查周期')).toHaveValue('weekly')
    await expect(panel.getByLabel('条件 2 检查周期')).toHaveValue('quarterly')
    await expect(panel.getByLabel(/统一检查周期|全局 cadence/i)).toHaveCount(0)
    await expect(panel.getByText('历史版本，不再执行定期检查')).toBeVisible()
    await expectSemanticTable(panel, '投资论点版本历史')
    await expect(panel.getByText(/目标价|自由文本条件/)).toHaveCount(0)
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[5], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { thesisState: 'pending' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, THESIS_TAB)
    for (const result of ['命中', '未命中', '证据不足', '检查错误']) await expect(panel.getByText(result, { exact: true })).toBeVisible()
    await expectSemanticTable(panel, '投资论点证据检查历史')
    const insufficient = panel.getByRole('row', { name: /证据不足/ })
    await expect(insufficient).toContainText(/缺少已披露季度值/)
    await expect(insufficient.getByText(/^0(?:\.0+)?$/)).toHaveCount(0)
    for (const label of ['到期时间', '检查时间', '观测值', '证据', '版本', '检查周期']) await expect(panel.getByRole('columnheader', { name: label })).toBeVisible()
    await expect(panel.getByRole('heading', { name: '待确认失效结论' })).toHaveCount(1)
    await expect(panel.getByText('当前官方状态未改变，等待你的确认。')).toBeVisible()
    expect(telemetry.mutationBodies).toEqual([])
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[6], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { thesisState: 'conflict' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, THESIS_TAB)
    await expect(panel.getByText('当前官方状态未改变，等待你的确认。')).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const trigger = panel.getByRole('button', { name: '确认论点失效' })
    await trigger.focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: '确认论点失效' })
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    await expect(dialog).toContainText(`确认将 ${STOCK.name}（${STOCK.symbol}）的论点版本 2 记录为已失效？`)
    const rationale = dialog.getByLabel('确认理由（至少 10 个字符）')
    await expect(rationale).toBeFocused()
    await rationale.fill('短理由')
    await expect(dialog.getByRole('button', { name: '确认论点失效' })).toBeDisabled()
    await rationale.fill('这是至少十个字符的人工确认理由。')
    await page.keyboard.press('Shift+Tab')
    await page.keyboard.press('Tab')
    await expect(rationale).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
    await trigger.click()
    await rationale.fill('这是至少十个字符的人工确认理由。')
    await dialog.getByRole('button', { name: '确认论点失效' }).click()
    await expect(panel.getByRole('alert')).toContainText('结论未记录：状态已变化，请重新查看当前论点。')
    await expect(rationale).toHaveValue('这是至少十个字符的人工确认理由。')
    await expect(page.getByRole('button', { name: /交易|创建计划|添加监控/ })).toHaveCount(0)
    expect(telemetry.requestsFor('/api/theses/')).toBeGreaterThan(1)
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[7], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { forecastGate: 'digest_mismatch' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    await expect(panel.getByRole('heading', { name: 'Kronos 概率预测' })).toBeVisible()
    await expect(panel.getByText('预测是不确定性研究记录，不会自动改变论点、策略、计划、监控或市场动作。')).toBeVisible()
    const horizon = panel.getByRole('radiogroup', { name: '预测范围' })
    expect(await horizon.getByRole('radio').allTextContents()).toEqual(expect.arrayContaining(['5', '20', '60']))
    expect(await horizon.getByRole('radio').count()).toBe(3)
    for (const text of ['Kronos-mini', 'Kronos-Tokenizer-2k', 'f4e6869', '26966d0', LONG_ID, '完整性校验']) await expect(panel.getByText(new RegExp(text))).toBeVisible()
    await expect(panel.getByRole('button', { name: '生成概率预测' })).toBeDisabled()
    await expect(panel.getByRole('alert')).toContainText(/digest mismatch|完整性/)
    await expect(panel.getByRole('button', { name: /下载|latest|绕过|远程/ })).toHaveCount(0)
    await expect(page.getByRole('tab', { name: '分析结论' })).toBeEnabled()
    await expect(page.getByRole('tab', { name: THESIS_TAB })).toBeEnabled()
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[8], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { forecastState: 'populated' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    for (const quantile of ['P10', 'P50', 'P90']) await expect(panel.getByText(quantile, { exact: true }).first()).toBeVisible()
    await expect(panel.getByText('32 条采样路径')).toBeVisible()
    await expect(panel.getByText('20 个交易日')).toBeVisible()
    await expectSemanticTable(panel, '逐日 P10 P50 P90 分位数')
    await expect(panel.getByRole('img', { name: /历史 close.*P10.*P90.*P50.*actual/i })).toBeVisible()
    const pathChoices = panel.getByRole('checkbox', { name: /采样路径/ })
    expect(await pathChoices.count()).toBeLessThanOrEqual(12)
    await panel.getByRole('button', { name: '查看采样路径' }).click()
    await expect(panel.getByText('共 32 条路径')).toBeVisible()
    await expectSemanticTable(panel, '选中采样路径 OHLCV')
    await panel.getByText('查看检查点与输入谱系').click()
    for (const text of ['67b630e', 'f4e6869', '26966d0', 'mini/2k', LONG_ID, 'daily OHLCV']) await expect(panel.getByText(new RegExp(text)).first()).toBeVisible()
    await expect(panel.getByText(/local_model_dir|\/tmp\/|worker command|token/i)).toHaveCount(0)
    await page.evaluate(() => document.querySelectorAll('canvas').forEach(canvas => canvas.remove()))
    await expect(panel.getByRole('table', { name: '逐日 P10 P50 P90 分位数' })).toBeVisible()
    await expect(panel.getByRole('table', { name: '选中采样路径 OHLCV' })).toBeVisible()
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[9], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { forecastState: 'terminal' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    await expect(panel.getByText('已有更新行情；此预测仍保留其原始数据截至日。')).toBeVisible()
    const immutableBefore = await panel.getByRole('table', { name: '逐日 P10 P50 P90 分位数' }).textContent()
    await panel.getByRole('button', { name: '基于相同配置创建新预测' }).click()
    await expect(panel.getByText(/预测 F-001/)).toBeVisible()
    expect(await panel.getByRole('table', { name: '逐日 P10 P50 P90 分位数' }).textContent()).toBe(immutableBefore)
    await expect(panel.getByText('进度连接已中断，正在按记录状态重新连接。')).toBeVisible()
    for (const terminal of ['timeout', 'OOM', 'shape failure', 'artifact failure']) await expect(panel.getByText(new RegExp(terminal, 'i'))).toBeVisible()
    await expect(panel.getByText('预测未完成')).toBeVisible()
    const terminalRows = panel.getByRole('row', { name: /timeout|OOM|shape failure|artifact failure/i })
    expect(await terminalRows.count()).toBe(4)
    for (let index = 0; index < await terminalRows.count(); index += 1) {
      await expect(terminalRows.nth(index).getByText(/P10|P50|P90/)).toHaveCount(0)
    }
    expect(telemetry.mutationBodies.filter(entry => entry.path.endsWith('/jobs'))).toHaveLength(1)
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[10], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { forecastState: 'partial' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    await expectSemanticTable(panel, '预测校准证据')
    const evaluated = panel.getByRole('row', { name: /5 个交易日.*已评估/ })
    for (const text of ['1492', '12.4', '100%', '2.1', '4.2', '1.7', '1', '2026-07-22']) await expect(evaluated.getByText(new RegExp(text))).toBeVisible()
    await expect(panel.getByText('尚未到达目标交易日，校准将在受治理实际值可用后追加。')).toBeVisible()
    const missing = panel.getByRole('row', { name: /60 个交易日/ })
    await expect(missing).toContainText('暂不可评估：缺少受治理实际值。')
    await expect(missing.getByText(/^0(?:\.0+)?$/)).toHaveCount(0)
    await expect(panel.getByText(LONG_ID).first()).toBeVisible()
    await expect(panel.getByText(/f4e6869/)).toBeVisible()
    expect(telemetry.mutationBodies).toEqual([])
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[11], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { thesisState: 'pending', forecastState: 'populated' })
    for (const viewport of [{ width: 1440, height: 960 }, { width: 1024, height: 900 }, { width: 375, height: 844 }]) {
      await page.setViewportSize(viewport)
      await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' })
      await page.goto('/backtest')
      const shadow = page.getByRole('region', { name: SHADOW_HEADING })
      await requireSurface(shadow.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
      const file = shadow.getByLabel('选择本地成交日志')
      if (viewport.width === 375) await expectTouchTarget(file)
      await expectSemanticTable(shadow, 'Shadow 不可变导入批次')

      await selectStock(page)
      await page.goto('/stock-analysis')
      const tablist = page.getByRole('tablist', { name: /分析/ })
      await expect(tablist).toBeVisible()
      const thesisTab = page.getByRole('tab', { name: THESIS_TAB })
      const forecastTab = page.getByRole('tab', { name: FORECAST_TAB })
      await thesisTab.focus()
      await page.keyboard.press('ArrowRight')
      await expect(forecastTab).toBeFocused()
      if (viewport.width === 375) {
        await expectTouchTarget(thesisTab)
        await expectTouchTarget(forecastTab)
        expect(await tablist.evaluate(element => element.scrollWidth >= element.clientWidth)).toBeTruthy()
      }
      const thesis = await openAnalysisTab(page, THESIS_TAB)
      const trigger = thesis.getByRole('button', { name: '确认论点失效' })
      await trigger.click()
      await page.keyboard.press('Escape')
      await expect(trigger).toBeFocused()
      const forecast = await openAnalysisTab(page, FORECAST_TAB)
      const chart = forecast.getByRole('img', { name: /P10.*P50.*P90/ })
      const chartBox = await chart.boundingBox()
      expect(chartBox!.height).toBe(viewport.width === 375 ? 280 : viewport.width === 1024 ? 320 : 360)
      await expect(forecast.getByRole('table', { name: '逐日 P10 P50 P90 分位数' })).toBeVisible()
      expect(await forecast.getByText(LONG_ID).first().evaluate(element => getComputedStyle(element).overflowWrap)).toMatch(/anywhere|break-word/)
      const transition = await forecast.evaluate(element => getComputedStyle(element).transitionDuration)
      expect(transition.split(',').every(value => parseFloat(value) === 0)).toBeTruthy()
      await expect(forecast.locator('[class*="animate-spin"], [class*="animate-pulse"]')).toHaveCount(0)
      expect(await contrastRatio(forecast.getByRole('heading', { name: 'Kronos 概率预测' }))).toBeGreaterThanOrEqual(4.5)
      await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'light' })
      await page.evaluate(() => document.documentElement.classList.remove('dark'))
      expect(await contrastRatio(forecast.getByText('P50', { exact: true }).first())).toBeGreaterThanOrEqual(4.5)
      const fontContracts = await page.locator('[data-phase5-typography]').evaluateAll(elements => elements.map(element => ({ size: getComputedStyle(element).fontSize, weight: getComputedStyle(element).fontWeight })))
      expect(new Set(fontContracts.map(item => item.size))).toEqual(new Set(['24px', '16px', '14px', '12px']))
      expect(new Set(fontContracts.map(item => item.weight))).toEqual(new Set(['400', '600']))
      expect((await page.locator('main').boundingBox())!.width).toBeLessThanOrEqual(viewport.width)
    }
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[12], async ({ page }, testInfo) => {
    futurePhase5Ui(testInfo)
    const telemetry = await installPhase5Fixture(page, { shadowState: 'populated', thesisState: 'pending', forecastState: 'populated' })
    await page.goto('/backtest')
    const shadow = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(shadow.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
    await shadow.getByRole('button', { name: '保留为 Shadow 研究候选' }).click()
    await page.getByRole('dialog', { name: '保留为 Shadow 研究候选' }).getByRole('button', { name: '保留为 Shadow 研究候选' }).click()

    await selectStock(page)
    await page.goto('/stock-analysis')
    const thesis = await openAnalysisTab(page, THESIS_TAB)
    await thesis.getByRole('button', { name: '驳回待确认结论' }).click()
    const reject = page.getByRole('dialog', { name: '驳回待确认结论' })
    await reject.getByLabel(/理由/).fill('这是至少十个字符的人工驳回理由。')
    await reject.getByRole('button', { name: '驳回待确认结论' }).click()
    const forecast = await openAnalysisTab(page, FORECAST_TAB)
    await forecast.getByRole('radio', { name: '20 个交易日' }).check()
    await forecast.getByRole('button', { name: '生成概率预测' }).click()
    await expect(forecast.getByText('已完成')).toBeVisible()
    await expect(forecast.getByRole('table', { name: '预测校准证据' })).toBeVisible()

    await expect(page.getByRole('button', { name: /应用到论点|应用到策略|设为目标价|据此交易|启用策略|同步持仓|添加监控|生成交易计划/ })).toHaveCount(0)
    expect(telemetry.mutationBodies.filter(entry => /shadow/.test(entry.path))).toHaveLength(1)
    expect(telemetry.mutationBodies.filter(entry => /theses/.test(entry.path))).toHaveLength(1)
    expect(telemetry.mutationBodies.filter(entry => /forecast/.test(entry.path))).toHaveLength(1)
    const mutationIndex = telemetry.apiRequests.findIndex(entry => entry.startsWith('POST /api/forecast/'))
    const afterForecast = telemetry.apiRequests.slice(mutationIndex + 1)
    expect(afterForecast.filter(entry => /shadow|theses|portfolio|monitor-rules|decision|strategies/.test(entry))).toEqual([])
    expect(afterForecast.every(entry => entry.includes('/api/forecast/') || entry.includes('/api/intraday/stream'))).toBeTruthy()
    expectNoAuthorityRequests(telemetry)
  })
})
