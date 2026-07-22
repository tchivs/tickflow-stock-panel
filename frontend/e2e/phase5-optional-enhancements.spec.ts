import type { Locator, Page, Route } from '@playwright/test'
import { expect, test } from '@playwright/test'

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
  'Shadow production distillation contract',
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
  retentionFailure?: boolean
  evidenceFailure?: boolean
  /** CR-04 identity join fixtures: default healthy 5/20/60 outcomes; malformed modes fail closed. */
  calibrationIdentity?: 'healthy' | 'missing' | 'duplicate' | 'foreign' | 'out_of_range'
}

type Telemetry = {
  apiRequests: string[]
  externalRequests: string[]
  unexpectedRequests: string[]
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
const terminalEvaluations = [
  {
    id: 'evaluation-timeout', candidate_id: candidate.id, evidence_set_id: candidate.evidence_set_id,
    split_kind: 'in_sample', window: { start: '2024-01-02', end: '2024-06-28' },
    governed_fingerprint: LONG_ID, artifact: { artifact_id: 'artifact-timeout' }, status: 'timeout',
    metrics: {}, terminal_reason: 'timeout', adjustment_policy: 'forward_adjusted', cost_policy: {}, created_at: '2026-07-15T09:20:00Z',
  },
  {
    id: 'evaluation-resource', candidate_id: candidate.id, evidence_set_id: candidate.evidence_set_id,
    split_kind: 'out_of_sample', window: { start: '2024-07-01', end: '2024-12-31' },
    governed_fingerprint: LONG_ID, artifact: { artifact_id: 'artifact-resource' }, status: 'resource_terminated',
    metrics: {}, terminal_reason: 'resource_terminated', adjustment_policy: 'forward_adjusted', cost_policy: {}, created_at: '2026-07-15T09:21:00Z',
  },
]

const thesisVersion = (version: number, overrides: Record<string, unknown> = {}) => ({
  id: `thesis-version-${version}`,
  thesis_id: 'thesis-ledger-1',
  instrument: STOCK.symbol,
  version,
  predecessor_id: version === 1 ? null : `thesis-version-${version - 1}`,
  official_state: 'active',
  core_judgment: '高端白酒品牌力与渠道质量仍支持长期现金流，但估值必须保留安全边际。',
  rationale: '治理后的财务与渠道证据支持当前判断，同时需求恢复节奏仍有不确定性。',
  change_reason: version === 1 ? '建立首版研究账本' : '追加年度报告证据并调整估值区间',
  created_by: 'server-session-user',
  created_at: `2026-07-${10 + version}T09:00:00Z`,
  effective_at: `2026-07-${10 + version}T09:00:00Z`,
  anchors: [{ method: 'DCF', currency: 'CNY', as_of: '2026-07-15', low: 1380, high: 1720, assumptions: [{ name: '收入复合增长', value: 8, unit: '%' }, { name: '终值增长', value: 3, unit: '%' }], limitations: ['未计入极端渠道库存冲击'] }],
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
  thesis_id: 'thesis-ledger-1',
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
  proposed_state: 'invalidated',
  reason: '受治理条件命中，等待人工确认。',
  status: 'pending',
  created_at: '2026-07-14T01:02:00Z',
  review: null,
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
const futureSessionIds = Array.from({ length: 60 }, (_, index) => {
  const day = new Date(Date.UTC(2026, 6, 16 + index)) // 2026-07-16 + index
  return day.toISOString().slice(0, 10)
})
const forecastOutcomes = [
  {
    id: 'outcome-h5',
    forecast_id: 'forecast-record-1',
    horizon: 5 as const,
    status: 'evaluated',
    actual_session_id: '2026-07-22',
    actual_close: 1492,
    observed_at: '2026-07-22T16:00:00Z',
  },
  {
    id: 'outcome-h20',
    forecast_id: 'forecast-record-1',
    horizon: 20 as const,
    status: 'pending',
    actual_session_id: '',
    actual_close: null,
    observed_at: '2026-07-15T09:00:00Z',
  },
  {
    id: 'outcome-h60',
    forecast_id: 'forecast-record-1',
    horizon: 60 as const,
    status: 'unevaluable',
    actual_session_id: '',
    actual_close: null,
    observed_at: '2026-07-15T09:00:00Z',
    reason: 'missing_actual',
  },
]
const forecastCalibrationFacts = [
  {
    id: 'cal-h5',
    forecast_id: 'forecast-record-1',
    outcome_id: 'outcome-h5',
    metric_schema: 'forecast-close-calibration-v1',
    metric_version: 1,
    close_mae: 12.4,
    p10_p90_interval_covered: true,
    pinball_p10: 2.1,
    pinball_p50: 4.2,
    pinball_p90: 1.7,
    coverage_start: '2026-07-22',
    coverage_end: '2026-07-22',
    created_at: '2026-07-22T16:05:00Z',
  },
  {
    id: 'cal-h20',
    forecast_id: 'forecast-record-1',
    outcome_id: 'outcome-h20',
    metric_schema: 'forecast-close-calibration-v1',
    metric_version: 1,
    close_mae: null,
    p10_p90_interval_covered: null,
    pinball_p10: null,
    pinball_p50: null,
    pinball_p90: null,
    coverage_start: null,
    coverage_end: null,
    created_at: '2026-07-15T09:00:00Z',
  },
  {
    id: 'cal-h60',
    forecast_id: 'forecast-record-1',
    outcome_id: 'outcome-h60',
    metric_schema: 'forecast-close-calibration-v1',
    metric_version: 1,
    close_mae: null,
    p10_p90_interval_covered: null,
    pinball_p10: null,
    pinball_p50: null,
    pinball_p90: null,
    coverage_start: null,
    coverage_end: null,
    created_at: '2026-07-15T09:00:00Z',
  },
]
const forecastRecord = {
  id: 'forecast-record-1',
  label: '预测 F-001',
  instrument: STOCK.symbol,
  created_at: '2026-07-15T09:00:00Z',
  as_of: 'CNA-20260715',
  origin_session_id: 'CNA-20260715',
  horizon: 60,
  future_session_ids: futureSessionIds,
  catalog_id: 'kronos-mini-approved',
  status: 'completed',
  checkpoint: { catalog_id: 'kronos-mini-approved', model: 'Kronos-mini', tokenizer: 'Kronos-Tokenizer-2k', source_revision: '67b630e', model_revision: 'f4e6869', tokenizer_revision: '26966d0', digest: LONG_ID, pairing: 'mini/2k', max_context: 2048, device: 'cpu', integrity: 'verified' },
  input: { fingerprint: LONG_ID, coverage_start: '2024-01-02', coverage_end: '2026-07-15', session_count: 512, schema: 'daily OHLCV' },
  sample_count: 32,
  quantiles,
  paths: forecastPaths,
  warnings: ['第 4 条路径成交量存在经济关系 warning，原值未被静默修正。'],
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function installPhase5Fixture(page: Page, options: FixtureOptions = {}): Promise<Telemetry> {
  const availability = { ...defaultAvailability, ...options.availability }
  const apiRequests: string[] = []
  const externalRequests: string[] = []
  const unexpectedRequests: string[] = []
  const mutationBodies: Array<{ method: string; path: string; body: unknown }> = []
  let batchCounter = 3
  let forecastCounter = 1
  let previewCounter = 0
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

  await page.route('**/api/**', route => {
    const request = route.request()
    unexpectedRequests.push(`${request.method()} ${new URL(request.url()).pathname}`)
    return json(route, { detail: `Unhandled fixture route: ${new URL(request.url()).pathname}` }, 500)
  })
  await page.route('**/api/settings', route => json(route, { onboarding_completed: true, theme: 'dark' }))
  await page.route('**/api/capabilities', route => json(route, { label: 'Free+', capabilities: {} }))
  await page.route('**/api/data/version', route => json(route, { version: 'phase5-browser' }))
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
  await page.route('**/api/data/status', route => json(route, { daily: null, enriched: null, index_daily: null, index_enriched: null, index_instruments: null, etf_daily: null, etf_enriched: null, etf_instruments: null, minute: null, adj_factor: null, instruments: null, financials: null, storage: {} }))
  await page.route('**/api/stock-analysis/reports', route => json(route, { reports: [] }))
  await page.route('**/api/kline/daily**', route => json(route, { symbol: STOCK.symbol, name: STOCK.name, rows: [] }))
  await page.route('**/api/stock-analysis/levels**', route => json(route, { symbol: STOCK.symbol, levels: {}, close: null, summary: '浏览器验收无行情档位' }))
  await page.route('**/api/advanced/viewpoints**', route => json(route, { viewpoints: [] }))
  await page.route('**/api/analysis/subjects/**/reports', route => json(route, { reports: [{ id: 'existing-report', subject: { kind: 'instrument', key: STOCK.symbol }, version: 1, status: 'validated', generated_at: '2026-07-10T00:00:00Z', evidence_limitations: [] }] }))
  await page.route('**/api/analysis/reports/existing-report', route => json(route, { report: { id: 'existing-report', signal_id: 'existing-signal', subject: { kind: 'instrument', key: STOCK.symbol }, version: 1, status: 'validated', generated_at: '2026-07-10T00:00:00Z', perspectives: [], score: null, valuation: null, ic_memo: { thesis: '既有分析仍可读取', risks: [], open_questions: [] } } }))
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
    const url = new URL(request.url())
    const path = url.pathname
    if (!availability.shadow) return json(route, { detail: capability('shadow', false) }, 503)
    if (path.endsWith('/capability')) return json(route, capability('shadow', true))
    if (path.endsWith('/batches') && request.method() === 'GET') {
      const offset = Number(url.searchParams.get('offset') ?? 0)
      const limit = Number(url.searchParams.get('limit') ?? 50)
      return json(route, { batches: options.shadowState === 'empty' ? [] : batches, page: { offset, limit, total: 75, has_more: offset + limit < 75 } })
    }
    if (path.endsWith('/imports/preview')) {
      previewCounter += 1
      return json(route, { preview_identity: `preview-server-${previewCounter}`, original_filename: 'executions.csv', format: 'CSV', timezone: 'Asia/Shanghai', mapping: [{ target: 'symbol', source: '证券代码', sample: '600519.SH', unit_timezone: '代码', status: 'mapped' }], rows: [{ symbol: STOCK.symbol, side: 'buy', executed_at: '2026-07-15T09:31:00+08:00', quantity: 100, price: 1450 }], diagnostics: [] })
    }
    if (path.endsWith('/imports/confirm')) { batchCounter += 1; return json(route, { batch: shadowBatch(`batch-server-${batchCounter}`, `不可变批次 ${batchCounter}`) }, 201) }
    if (path.endsWith('/evidence-sets')) {
      if (request.method() === 'POST') {
        const body = request.postDataJSON() as Record<string, unknown>
        if (
          body.membership_mode !== 'all_authorized_batch_trades'
          || 'included_trade_ids' in body
          || !Array.isArray(body.included_batch_ids)
          || !Array.isArray(body.exclusions)
        ) return json(route, { detail: 'strict server-resolved membership is required' }, 422)
        if (options.evidenceFailure) return json(route, { detail: 'evidence ownership changed' }, 409)
        return json(route, {
          evidence_set: {
            id: 'evidence-server-1',
            fingerprint: LONG_ID,
            included_batch_ids: body.included_batch_ids,
            included_trade_ids: ['server-resolved-trade-1', 'server-resolved-trade-2', 'server-resolved-trade-3', 'server-resolved-trade-4'],
            included_trade_count: 4,
            exclusions: body.exclusions,
            created_at: '2026-07-15T09:10:00Z',
          },
        }, 201)
      }
      return json(route, {
        evidence_sets: [{
          id: 'evidence-server-1', fingerprint: LONG_ID, included_batch_ids: ['batch-server-1'],
          included_trade_ids: ['server-resolved-trade-1', 'server-resolved-trade-2', 'server-resolved-trade-3', 'server-resolved-trade-4'],
          included_trade_count: 4, exclusions: [], created_at: '2026-07-15T09:10:00Z',
        }],
      })
    }
    if (path.includes('/candidates') && path.endsWith('/retain')) {
      if (options.retentionFailure) {
        const { promise, resolve } = Promise.withResolvers<void>()
        setTimeout(resolve, 100)
        return promise.then(() => json(route, { detail: 'retention state changed; review current evidence' }, 409))
      }
      return json(route, { retention: { id: 'retention-server-1', candidate_id: candidate.id, status: 'retained_research_only', created_at: '2026-07-15T09:30:00Z' } }, 201)
    }
    if (path.endsWith('/candidates') && request.method() === 'POST') return options.shadowState === 'terminal'
      ? json(route, { detail: 'bounded distillation timeout' }, 409)
      : json(route, { candidate }, 201)
    if (path.endsWith('/candidates')) return json(route, { candidates: options.shadowState === 'empty' ? [] : [candidate] })
    if (path.endsWith('/evaluations')) return json(route, { evaluations: options.shadowState === 'terminal' ? terminalEvaluations : [] })
    if (path.endsWith('/retentions')) return json(route, { retentions: [] })
    unexpectedRequests.push(`${request.method()} ${path}`)
    return json(route, { detail: `Unhandled Shadow fixture route: ${path}` }, 500)
  })

  await page.route('**/api/theses/**', route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 50)
    if (!availability.thesis) return json(route, { detail: capability('thesis', false) }, 503)
    if (path.endsWith('/capability')) return json(route, capability('thesis', true))
    if (path.endsWith('/versions') && request.method() === 'GET') return json(route, { items: options.thesisState === 'empty' ? [] : versions, offset, limit, total: options.thesisState === 'empty' ? 0 : versions.length, has_more: false })
    if (path.endsWith('/versions') && request.method() === 'POST') return json(route, { version: thesisVersion(3) }, 201)
    if (path.endsWith('/checks')) return json(route, { items: thesisChecks, offset, limit, total: thesisChecks.length, has_more: false })
    if (path.endsWith('/pending')) { const items = options.thesisState === 'pending' || options.thesisState === 'conflict' ? [pending] : []; return json(route, { items, offset, limit, total: items.length, has_more: false }) }
    if (path.endsWith('/history')) return json(route, { items: [], offset, limit, total: 0, has_more: false })
    if (path.endsWith('/confirm') || path.endsWith('/reject')) {
      if (options.thesisState === 'conflict') return json(route, { detail: 'state changed' }, 409)
      return json(route, { review: { id: 'review-server-1', decision: path.endsWith('/confirm') ? 'confirmed' : 'rejected', principal: 'server-session-user', reason: '人工理由完整保留', created_at: '2026-07-15T10:00:00Z' }, official_status: path.endsWith('/confirm') ? 'invalidated' : 'active' })
    }
    unexpectedRequests.push(`${request.method()} ${path}`)
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
    if (path.endsWith('/records') && request.method() === 'GET') return json(route, {
      records: options.forecastState && options.forecastState !== 'empty' ? records : [],
      page: { offset: 0, limit: 25, total: options.forecastState && options.forecastState !== 'empty' ? records.length : 0, has_more: false },
      latest_governed_session_id: options.forecastState === 'terminal' ? 'CNA-20260716' : 'CNA-20260715',
    })
    if (path.endsWith('/jobs') && request.method() === 'GET') return json(route, {
      jobs: options.forecastState === 'terminal' ? [
        { id: 'job-timeout', instrument: STOCK.symbol, status: 'timeout', stage: 'timeout', safe_reason: 'timeout', record_id: null, created_at: '2026-07-15T10:01:00Z' },
        { id: 'job-oom', instrument: STOCK.symbol, status: 'resource_terminated', stage: 'resource_terminated', safe_reason: 'OOM', record_id: null, created_at: '2026-07-15T10:02:00Z' },
        { id: 'job-shape', instrument: STOCK.symbol, status: 'validation_failed', stage: 'validation_failed', safe_reason: 'shape failure', record_id: null, created_at: '2026-07-15T10:03:00Z' },
        { id: 'job-artifact', instrument: STOCK.symbol, status: 'artifact_failed', stage: 'artifact_failed', safe_reason: 'artifact failure', record_id: null, created_at: '2026-07-15T10:04:00Z' },
      ] : [],
      page: { offset: 0, limit: 25, total: options.forecastState === 'terminal' ? 4 : 0, has_more: false },
    })
    if (path.endsWith('/jobs') && request.method() === 'POST') {
      forecastCounter += 1
      const terminal = options.forecastState === 'terminal'
      return json(route, { job: { id: `forecast-job-${forecastCounter}`, instrument: STOCK.symbol, horizon: 20, catalog_id: 'kronos-mini-approved', status: terminal ? 'running' : 'completed', stage: terminal ? 'generating_paths' : 'completed', stage_recorded_at: '2026-07-15T10:00:00Z', attempt: 1, record_id: terminal ? null : `forecast-record-${forecastCounter}`, created_at: '2026-07-15T10:00:00Z', updated_at: '2026-07-15T10:00:00Z' } }, 201)
    }
    if (path.includes('/records/') && path.endsWith('/paths')) return json(route, { paths: { items: [], offset: 0, limit: 12, total: 32, has_more: true } })
    if (path.includes('/records/') && path.endsWith('/calibration')) {
      const mode = options.calibrationIdentity ?? 'healthy'
      if (mode === 'missing') {
        return json(route, {
          outcomes: forecastOutcomes.filter(item => item.id !== 'outcome-h5'),
          calibration: forecastCalibrationFacts,
        })
      }
      if (mode === 'duplicate') {
        return json(route, {
          outcomes: [...forecastOutcomes, { ...forecastOutcomes[0], status: 'evaluated' }],
          calibration: forecastCalibrationFacts,
        })
      }
      if (mode === 'foreign') {
        return json(route, {
          outcomes: forecastOutcomes.map(item => item.id === 'outcome-h5'
            ? { ...item, forecast_id: 'foreign-forecast' }
            : item),
          calibration: forecastCalibrationFacts,
        })
      }
      if (mode === 'out_of_range') {
        return json(route, {
          outcomes: forecastOutcomes.map(item => item.id === 'outcome-h60'
            ? { ...item, horizon: 120 as any }
            : item),
          calibration: forecastCalibrationFacts,
        })
      }
      return json(route, { outcomes: forecastOutcomes, calibration: forecastCalibrationFacts })
    }
    if (path.includes('/records/')) return json(route, { record: forecastRecord })
    if (path.includes('/jobs/')) return json(route, { job: { id: path.split('/').at(-1), instrument: STOCK.symbol, horizon: 20, catalog_id: 'kronos-mini-approved', status: options.forecastState === 'terminal' ? 'running' : 'completed', stage: options.forecastState === 'terminal' ? 'generating_paths' : 'completed', stage_recorded_at: '2026-07-15T10:00:00Z', attempt: 1, safe_reason: null, record_id: options.forecastState === 'terminal' ? null : forecastRecord.id, created_at: '2026-07-15T10:00:00Z', updated_at: '2026-07-15T10:00:00Z' } })
    unexpectedRequests.push(`${request.method()} ${path}`)
    return json(route, { detail: `Unhandled Forecast fixture route: ${path}` }, 500)
  })
  await page.route('**/api/forecast/jobs/**/stream', route => options.forecastState === 'terminal'
    ? route.abort('connectionreset')
    : route.fulfill({ contentType: 'text/event-stream', body: 'id: 1\nevent: forecast_progress\ndata: {"job_id":"forecast-job-1","stage":"completed","status":"completed","stage_recorded_at":"2026-07-15T10:00:00Z"}\n\n' }))

  return {
    apiRequests,
    externalRequests,
    unexpectedRequests,
    mutationBodies,
    requestsFor: pathPrefix => apiRequests.filter(value => value.includes(pathPrefix)).length,
  }
}


async function requireSurface(locator: Locator) {
  await expect(locator).toBeVisible()
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
    const gamma = (value: number) => {
      const channel = Math.min(1, Math.max(0, value))
      return (channel <= 0.0031308 ? 12.92 * channel : 1.055 * channel ** (1 / 2.4) - 0.055) * 255
    }
    const parseAlpha = (value: string | undefined) => {
      if (!value) return 1
      return value.trim().endsWith('%') ? Number.parseFloat(value) / 100 : Number.parseFloat(value)
    }
    const oklabToRgb = (lightness: number, a: number, b: number) => {
      const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
      const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
      const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3
      return [
        gamma(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
        gamma(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
        gamma(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
      ]
    }
    const parse = (color: string) => {
      if (color.startsWith('oklab(') || color.startsWith('oklch(')) {
        const functionNameLength = color.startsWith('oklab(') ? 6 : 6
        const [components, alphaValue] = color.slice(functionNameLength, -1).split('/')
        const [lightnessValue, secondValue, thirdValue] = components.trim().split(/\s+/)
        const lightness = lightnessValue.endsWith('%') ? Number.parseFloat(lightnessValue) / 100 : Number.parseFloat(lightnessValue)
        let a = Number.parseFloat(secondValue)
        let b = Number.parseFloat(thirdValue)
        if (color.startsWith('oklch(')) {
          const chroma = a
          const hue = b * Math.PI / 180
          a = chroma * Math.cos(hue)
          b = chroma * Math.sin(hue)
        }
        return { rgb: oklabToRgb(lightness, a, b), alpha: parseAlpha(alphaValue) }
      }
      if (color.startsWith('color(srgb ')) {
        const [components, alphaValue] = color.slice(11, -1).split('/')
        return { rgb: components.trim().split(/\s+/).map(value => Number.parseFloat(value) * 255), alpha: parseAlpha(alphaValue) }
      }
      const values = color.match(/[\d.]+/g)?.map(Number) ?? []
      return { rgb: values.slice(0, 3), alpha: values[3] ?? 1 }
    }
    const luminance = (rgb: number[]) => {
      const linear = rgb.map(channel => {
        const value = channel / 255
        return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
      })
      return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    }

    const layers: Array<{ rgb: number[]; alpha: number }> = []
    let parent: Element | null = element
    while (parent) {
      const layer = parse(getComputedStyle(parent).backgroundColor)
      if (layer.rgb.length === 3 && layer.alpha > 0) layers.push(layer)
      if (layer.alpha === 1) break
      parent = parent.parentElement
    }
    let background = [255, 255, 255]
    for (const layer of layers.reverse()) {
      background = layer.rgb.map((channel, index) => channel * layer.alpha + background[index] * (1 - layer.alpha))
    }
    const foregroundLayer = parse(getComputedStyle(element).color)
    const foreground = foregroundLayer.rgb.map((channel, index) => channel * foregroundLayer.alpha + background[index] * (1 - foregroundLayer.alpha))
    const foregroundLuminance = luminance(foreground)
    const backgroundLuminance = luminance(background)
    return (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) / (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
  })
}

function expectNoAuthorityRequests(telemetry: Telemetry) {
  const serialized = JSON.stringify(telemetry.mutationBodies)
  for (const field of ['principal', 'reviewer_principal', 'fingerprint', 'digest', 'verdict', 'official_status', 'quantiles', 'paths', 'checkpoint_revision']) {
    expect(serialized).not.toContain(`"${field}"`)
  }
  expect(telemetry.apiRequests.filter(path => /broker|market-action|positions\/sync|monitor-rules|decision\/runs|strategies\/install/.test(path))).toEqual([])
  expect(telemetry.externalRequests).toEqual([])
  expect(telemetry.unexpectedRequests).toEqual([])
}

test.describe('Phase 05 optional enhancement browser contracts', () => {
  test(SCENARIO_TITLES[0], async ({ page }) => {
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

  test(SCENARIO_TITLES[1], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { shadowState: 'populated' })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
    await expect(panel.getByText('仅从本地实际成交日志形成研究证据，不连接券商、不同步持仓、不执行交易。')).toBeVisible()
    await expect(panel.getByText(/支持.*CSV.*XLSX.*大小.*行数.*Asia\/Shanghai/)).toBeVisible()
    const file = panel.getByLabel('选择本地成交日志')
    await file.setInputFiles({ name: 'executions.csv', mimeType: 'text/csv', buffer: Buffer.from('symbol,side,time,quantity,price\n600519.SH,buy,2026-07-15 09:31,100,1450') })
    await expect(panel.getByRole('status').filter({ hasText: /executions\.csv|正在解析日志/ })).toBeVisible()
    await expectSemanticTable(panel, 'Shadow 字段映射预览')
    await expect(panel.getByText(/^仅为预览；/)).toBeVisible()
    const previewNotice = panel.getByText(/^仅为预览；重复组和 partial fill/)
    await expect(previewNotice).toContainText('重复组')
    await expect(previewNotice).toContainText(/partial fill|部分成交/i)
    await panel.getByRole('button', { name: '确认不可变导入' }).click()
    const dialog = page.getByRole('dialog', { name: '确认不可变导入' })
    await expect(dialog).toContainText(/原文件名|来源标签|时区|映射|行数|不可覆写/)
    await dialog.getByRole('button', { name: '确认不可变导入' }).click()
    await expectSemanticTable(panel, 'Shadow 不可变导入批次')
    for (const text of ['原始批次 1', '同内容批次 2', '修正批次 3', 'same content', '修正自']) await expect(panel.getByText(text).first()).toBeVisible()
    await expect(panel.getByText(/1 行未纳入/).first()).toBeVisible()
    await expect(panel.getByText(/\/tmp\/|C:\\|account_secret|broker_token|raw_path/i)).toHaveCount(0)
    const evidence = panel.getByRole('button', { name: '创建新证据集' })
    await evidence.click()
    await expect(panel.getByText('证据集已冻结：evidence-server-1。后续变更需创建新证据集。')).toBeVisible()
    await expect(panel.getByText('1 / 4')).toBeVisible()
    const evidenceRequest = telemetry.mutationBodies.find(
      entry => entry.method === 'POST' && entry.path.endsWith('/evidence-sets'),
    )
    expect(evidenceRequest?.body).toEqual({
      included_batch_ids: ['batch-server-4'],
      membership_mode: 'all_authorized_batch_trades',
      exclusions: [],
    })
    expect(Object.keys(evidenceRequest?.body as Record<string, unknown>)).not.toEqual(expect.arrayContaining([
      'included_trade_ids', 'principal', 'fingerprint', 'verdict', 'strategy', 'monitor', 'plan',
      'position', 'broker', 'market_action',
    ]))
    await panel.getByRole('button', { name: '基于相同证据集创建新蒸馏运行' }).click()
    await expect(panel.getByText(/已创建可解释候选/)).toBeVisible()
    expect(telemetry.mutationBodies.some(entry => entry.path.endsWith('/imports/confirm'))).toBeTruthy()
    expectNoAuthorityRequests(telemetry)
  })

  test('Shadow evidence rejection preserves selected batches and immutable history', async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { shadowState: 'populated', evidenceFailure: true })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
    const selectedBatch = panel.getByLabel('纳入批次 修正批次 3')
    await selectedBatch.check()
    await panel.getByRole('button', { name: '创建新证据集' }).click()
    await expect(panel.getByRole('alert')).toContainText('批次选择保持不变')
    await expect(selectedBatch).toBeChecked()
    await expect(panel.getByText(LONG_ID).first()).toBeVisible()
    expectNoAuthorityRequests(telemetry)
  })

  test('Shadow preview identity follows current bytes mapping and timezone', async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { shadowState: 'populated' })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
    const file = panel.getByLabel('选择本地成交日志')

    await file.setInputFiles({ name: 'executions.csv', mimeType: 'text/csv', buffer: Buffer.from('symbol,side,time,quantity,price\n600519.SH,buy,2026-07-15 09:31,100,1450') })
    await expect.poll(() => telemetry.requestsFor('/api/shadow/imports/preview')).toBe(1)

    await panel.getByLabel('费用来源列').fill('手续费金额')
    await expect.poll(() => telemetry.requestsFor('/api/shadow/imports/preview')).toBe(2)
    await panel.getByLabel('源时区').selectOption('UTC')
    await expect.poll(() => telemetry.requestsFor('/api/shadow/imports/preview')).toBe(3)
    await file.setInputFiles({ name: 'executions.csv', mimeType: 'text/csv', buffer: Buffer.from('symbol,side,time,quantity,price\n600519.SH,buy,2026-07-15 09:31,200,1450') })
    await expect.poll(() => telemetry.requestsFor('/api/shadow/imports/preview')).toBe(4)

    await panel.getByRole('button', { name: '确认不可变导入' }).click()
    const dialog = page.getByRole('dialog', { name: '确认不可变导入' })
    await expect(dialog).toContainText('preview-server-4')
    await dialog.getByRole('button', { name: '确认不可变导入' }).click()

    const confirmation = telemetry.mutationBodies.findLast(entry => entry.path.endsWith('/imports/confirm'))
    expect(confirmation?.body).toContain('preview-server-4')
    expectNoAuthorityRequests(telemetry)
  })

  test('Shadow non-first history page refreshes after append', async ({ page }) => {
    const batchOffsets: number[] = []
    page.on('request', request => {
      const url = new URL(request.url())
      if (request.method() === 'GET' && url.pathname === '/api/shadow/batches') {
        batchOffsets.push(Number(url.searchParams.get('offset') ?? 0))
      }
    })
    await installPhase5Fixture(page, { shadowState: 'populated' })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))

    await panel.getByRole('navigation', { name: 'Shadow 历史分页' }).first().getByRole('button', { name: '下一页' }).click()
    await expect.poll(() => batchOffsets.filter(offset => offset === 50).length).toBe(1)

    const file = panel.getByLabel('选择本地成交日志')
    await file.setInputFiles({ name: 'executions.csv', mimeType: 'text/csv', buffer: Buffer.from('symbol,side,time,quantity,price\n600519.SH,buy,2026-07-15 09:31,100,1450') })
    await panel.getByRole('button', { name: '确认不可变导入' }).click()
    await page.getByRole('dialog', { name: '确认不可变导入' }).getByRole('button', { name: '确认不可变导入' }).click()

    await expect.poll(() => batchOffsets.filter(offset => offset === 50).length).toBeGreaterThan(1)
  })

  test(SCENARIO_TITLES[2], async ({ page }) => {
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
    await expect(panel.getByText('Shadow 研究候选已保留；未注册或启用策略。')).toBeVisible()
    await expect(page.getByRole('button', { name: /启用策略|同步持仓|添加监控|生成交易计划|据此交易/ })).toHaveCount(0)
    expect(telemetry.mutationBodies.filter(entry => entry.path.endsWith('/retain'))).toHaveLength(1)
    expectNoAuthorityRequests(telemetry)
  })

  test('Shadow retention dialog validates rationale and contains errors', async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { shadowState: 'populated', retentionFailure: true })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
    const trigger = panel.getByRole('button', { name: '保留为 Shadow 研究候选' })

    await trigger.focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: '保留为 Shadow 研究候选' })
    const rationale = dialog.getByLabel('保留理由（至少 10 个字符）')
    const confirm = dialog.getByRole('button', { name: '保留为 Shadow 研究候选' })
    const live = dialog.locator('[aria-live]')
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    await expect(rationale).toBeFocused()
    await rationale.fill('   短理由   ')
    await expect(confirm).toBeDisabled()

    const exactRationale = '这是至少十个字符的 Shadow 保留理由。'
    await rationale.fill(`   ${exactRationale}   `)
    await page.keyboard.press('Shift+Tab')
    await page.keyboard.press('Tab')
    await expect(rationale).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()

    await trigger.click()
    await rationale.fill(`   ${exactRationale}   `)
    await Promise.all([
      expect(live).toContainText('正在记录'),
      confirm.click(),
    ])
    await expect(dialog.getByRole('alert')).toContainText('retention state changed')
    await expect(rationale).toHaveValue(`   ${exactRationale}   `)
    const retention = telemetry.mutationBodies.findLast(entry => entry.path.endsWith('/retain'))
    expect(retention?.body).toMatchObject({ rationale: exactRationale })
    await expect(page.getByRole('button', { name: /启用策略|同步持仓|添加监控|生成交易计划|据此交易/ })).toHaveCount(0)
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[3], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { shadowState: 'terminal' })
    await page.setViewportSize({ width: 375, height: 844 })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))
    await expect(panel.getByText('存在较新成交批次；当前候选仍基于已冻结证据。')).toBeVisible()
    await panel.getByRole('button', { name: '基于相同证据集创建新蒸馏运行' }).click()
    await expect(panel.getByRole('heading', { name: 'Shadow 候选蒸馏失败', exact: true })).toBeVisible()
    await expect(panel.getByRole('heading', { name: 'Shadow 样本内/样本外评估失败', exact: true }).first()).toBeVisible()
    const evaluationFailures = panel.getByRole('heading', { name: 'Shadow 样本内/样本外评估失败', exact: true })
    await expect(evaluationFailures).toHaveCount(2)
    await expect(evaluationFailures.nth(0).locator('..')).toContainText('timeout')
    await expect(evaluationFailures.nth(1).locator('..')).toContainText('resource_terminated')
    await expect(panel.getByRole('button', { name: '基于相同证据集创建新蒸馏运行' }).first()).toBeVisible()
    await expect(panel.getByRole('button', { name: '创建新评估运行' }).first()).toBeVisible()
    await panel.getByText('查看规则与限制').click()
    await expect(panel.getByText(new RegExp('a{40}')).first()).toBeVisible()
    const identifier = panel.getByText(LONG_ID).filter({ visible: true }).last()
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

  test(SCENARIO_TITLES[4], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { thesisState: 'populated' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, THESIS_TAB)
    await expect(panel.getByRole('heading', { name: THESIS_TAB, exact: true })).toBeVisible()
    await expect(panel.getByText(`${STOCK.name} ${STOCK.symbol}`)).toBeVisible()
    await expect(panel.getByText('自动检查只能提出待确认结论，不能替你改变论点状态。')).toBeVisible()
    await panel.getByRole('button', { name: '基于此版本创建新版本' }).click()
    await panel.getByLabel('版本变更理由').fill('追加年度报告证据并调整估值区间')
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
    await panel.getByRole('row', { name: /^版本 1 / }).getByRole('button', { name: '查看完整版本' }).click()
    await expect(panel.getByText('历史版本，不再执行定期检查')).toBeVisible()
    await expectSemanticTable(panel, '投资论点版本历史')
    await expect(panel.getByText(/目标价|自由文本条件/)).toHaveCount(0)
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[5], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { thesisState: 'pending' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, THESIS_TAB)
    for (const result of ['命中', '未命中', '证据不足', '检查错误']) await expect(panel.getByText(result, { exact: true })).toBeVisible()
    await expectSemanticTable(panel, '投资论点证据检查历史')
    const insufficient = panel.getByRole('row', { name: /证据不足/ })
    await expect(insufficient).toContainText(/缺少已披露季度值/)
    await expect(insufficient.getByText(/^0(?:\.0+)?$/)).toHaveCount(0)
    for (const label of ['到期时间', '检查时间', '观测值', '证据', '版本', '检查周期']) await expect(panel.getByRole('table', { name: '投资论点证据检查历史' }).getByRole('columnheader', { name: label, exact: true })).toBeVisible()
    await expect(panel.getByRole('heading', { name: '待确认失效结论' })).toHaveCount(1)
    await expect(panel.getByText('当前官方状态未改变，等待你的确认。')).toBeVisible()
    expect(telemetry.mutationBodies).toEqual([])
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[6], async ({ page }) => {
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

  test(SCENARIO_TITLES[7], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { forecastGate: 'digest_mismatch' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    await expect(panel.getByRole('heading', { name: 'Kronos 概率预测' })).toBeVisible()
    await expect(panel.getByText('预测是不确定性研究记录，不会自动改变论点、策略、计划、监控或市场动作。')).toBeVisible()
    const horizon = panel.getByRole('radiogroup', { name: '预测范围' })
    for (const value of [5, 20, 60]) await expect(horizon.getByRole('radio', { name: `${value} 个交易日`, exact: true })).toBeVisible()
    expect(await horizon.getByRole('radio').count()).toBe(3)
    for (const text of ['Kronos-mini', 'Kronos-Tokenizer-2k', 'f4e6869', '26966d0', LONG_ID, '完整性校验']) await expect(panel.getByText(new RegExp(text)).filter({ visible: true }).first()).toBeVisible()
    await expect(panel.getByRole('button', { name: '生成概率预测' })).toBeDisabled()
    await expect(panel.getByRole('alert')).toContainText(/digest mismatch|完整性/)
    await expect(panel.getByRole('button', { name: /下载|latest|绕过|远程/ })).toHaveCount(0)
    await expect(page.getByRole('tab', { name: '分析结论' })).toBeEnabled()
    await expect(page.getByRole('tab', { name: THESIS_TAB })).toBeEnabled()
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[8], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { forecastState: 'populated' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    for (const quantile of ['P10', 'P50', 'P90']) await expect(panel.getByText(quantile, { exact: true }).first()).toBeVisible()
    await expect(panel.getByText('32 条采样路径')).toBeVisible()
    await expect(panel.getByRole('radio', { name: '20 个交易日', exact: true })).toBeChecked()
    await expectSemanticTable(panel, '逐日 P10 P50 P90 分位数')
    await expect(panel.getByRole('img', { name: /历史 close.*P10.*P90.*P50.*actual/i })).toBeVisible()
    const pathChoices = panel.getByRole('checkbox', { name: /采样路径/ })
    expect(await pathChoices.count()).toBeLessThanOrEqual(12)
    await panel.getByRole('button', { name: '查看采样路径' }).click()
    await expect(panel.getByText('共 32 条路径')).toBeVisible()
    await expectSemanticTable(panel, '选中采样路径 OHLCV')
    await panel.getByText('查看检查点与输入谱系').click()
    for (const text of ['67b630e', 'f4e6869', '26966d0', 'mini/2k', LONG_ID, 'daily OHLCV']) await expect(panel.getByText(new RegExp(text)).first()).toBeVisible()
    await expect(panel.getByText(/local_model_dir|\/tmp\/|worker command|raw token|broker_token|account_secret/i)).toHaveCount(0)
    await page.evaluate(() => document.querySelectorAll('canvas').forEach(canvas => canvas.remove()))
    await expect(panel.getByRole('table', { name: '逐日 P10 P50 P90 分位数' })).toBeVisible()
    await expect(panel.getByRole('table', { name: '选中采样路径 OHLCV' })).toBeVisible()
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[9], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { forecastState: 'terminal' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    await expect(panel.getByText('已有更新行情；此预测仍保留其原始数据截至日。')).toBeVisible()
    const immutableBefore = await panel.getByRole('table', { name: '逐日 P10 P50 P90 分位数' }).textContent()
    await panel.getByRole('button', { name: '基于相同配置创建新预测' }).click()
    await expect(panel.getByRole('heading', { name: '预测 F-001', exact: true })).toBeVisible()
    expect(await panel.getByRole('table', { name: '逐日 P10 P50 P90 分位数' }).textContent()).toBe(immutableBefore)
    await expect(panel.getByText('进度连接已中断，正在按记录状态重新连接。')).toBeVisible()
    await expect(panel.getByText('预测未完成', { exact: true })).toBeVisible()
    const terminalRows = panel.getByRole('row', { name: /timeout|OOM|shape failure|artifact failure/i })
    expect(await terminalRows.count()).toBe(4)
    for (const terminal of ['timeout', 'OOM', 'shape failure', 'artifact failure']) {
      await expect(terminalRows.filter({ hasText: new RegExp(terminal, 'i') })).toHaveCount(1)
    }
    for (let index = 0; index < await terminalRows.count(); index += 1) {
      await expect(terminalRows.nth(index).getByText(/P10|P50|P90/)).toHaveCount(0)
    }
    expect(telemetry.mutationBodies.filter(entry => entry.path.endsWith('/jobs'))).toHaveLength(1)
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[10], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { forecastState: 'partial' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    await expectSemanticTable(panel, '预测校准证据')
    const evaluated = panel.getByRole('row', { name: /5 个交易日.*已评估/ })
    for (const text of ['1492', '12.4', '100%', '2.1', '4.2', '1.7', '1', '2026-07-22']) await expect(evaluated).toContainText(text)
    await expect(panel.getByText('尚未到达目标交易日，校准将在受治理实际值可用后追加。')).toBeVisible()
    const missing = panel.getByRole('row', { name: /60 个交易日/ })
    await expect(missing).toContainText('暂不可评估：缺少受治理实际值。')
    await expect(missing.getByText(/^0(?:\.0+)?$/)).toHaveCount(0)
    await expect(panel.getByText(LONG_ID).first()).toBeVisible()
    await panel.getByText('查看检查点与输入谱系').click()
    await expect(panel.getByText('f4e6869', { exact: true })).toBeVisible()
    expect(telemetry.mutationBodies).toEqual([])
    expectNoAuthorityRequests(telemetry)
  })

  test('CR-04 calibration outcome identity renders 5 20 60 and fails closed', async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { forecastState: 'partial' })
    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    await expectSemanticTable(panel, '预测校准证据')

    const evaluated = panel.getByRole('row', { name: /5 个交易日.*已评估/ })
    await expect(evaluated).toContainText('2026-07-22')
    await expect(evaluated).toContainText('1492')
    await expect(evaluated).toContainText('12.4')
    await expect(evaluated).toContainText('100%')
    await expect(evaluated).toContainText('2.1')
    await expect(evaluated).toContainText('4.2')
    await expect(evaluated).toContainText('1.7')

    // target = future_session_ids[horizon - 1] — distinct for 5 / 20 / 60
    const target5 = futureSessionIds[4]
    const target20 = futureSessionIds[19]
    const target60 = futureSessionIds[59]
    expect(new Set([target5, target20, target60]).size).toBe(3)

    const pending = panel.getByRole('row', { name: /20 个交易日.*未成熟/ })
    await expect(pending).toContainText(`目标 ${target20}`)
    await expect(panel.getByText('尚未到达目标交易日，校准将在受治理实际值可用后追加。')).toBeVisible()

    const missing = panel.getByRole('row', { name: /60 个交易日/ })
    await expect(missing).toContainText('暂不可评估：缺少受治理实际值。')
    await expect(missing.getByText(/^0(?:\.0+)?$/)).toHaveCount(0)

    // horizons must be distinct labels, never all record-total horizon
    await expect(panel.getByRole('row', { name: /5 个交易日/ })).toHaveCount(1)
    await expect(panel.getByRole('row', { name: /20 个交易日.*未成熟/ })).toHaveCount(1)
    await expect(panel.getByRole('row', { name: /60 个交易日/ })).toHaveCount(1)

    // chart-independent table remains after canvas removal
    await page.evaluate(() => document.querySelectorAll('canvas').forEach(canvas => canvas.remove()))
    await expect(panel.getByRole('table', { name: '预测校准证据' })).toBeVisible()
    await expect(panel.getByText('左右滚动查看完整记录。校准只追加受治理实际值，不改写原分位数或采样路径。')).toBeVisible()
    await expect(page.getByRole('button', { name: /应用到论点|应用到策略|设为目标价|据此交易|启用策略|同步持仓|添加监控|生成交易计划/ })).toHaveCount(0)
    expectNoAuthorityRequests(telemetry)

    // missing outcome identity fails closed
    await installPhase5Fixture(page, { forecastState: 'partial', calibrationIdentity: 'missing' })
    await page.goto('/stock-analysis')
    const missingPanel = await openAnalysisTab(page, FORECAST_TAB)
    await expect(missingPanel.getByText('校准身份不完整').first()).toBeVisible()
    await expect(missingPanel.getByRole('row', { name: /校准身份不完整/ }).first()).toBeVisible()

    // duplicate outcome identity fails closed
    await installPhase5Fixture(page, { forecastState: 'partial', calibrationIdentity: 'duplicate' })
    await page.goto('/stock-analysis')
    const dupPanel = await openAnalysisTab(page, FORECAST_TAB)
    await expect(dupPanel.getByText('校准身份不完整').first()).toBeVisible()

    // foreign forecast_id fails closed
    await installPhase5Fixture(page, { forecastState: 'partial', calibrationIdentity: 'foreign' })
    await page.goto('/stock-analysis')
    const foreignPanel = await openAnalysisTab(page, FORECAST_TAB)
    await expect(foreignPanel.getByText('校准身份不完整').first()).toBeVisible()

    // out-of-range horizon fails closed
    await installPhase5Fixture(page, { forecastState: 'partial', calibrationIdentity: 'out_of_range' })
    await page.goto('/stock-analysis')
    const rangePanel = await openAnalysisTab(page, FORECAST_TAB)
    await expect(rangePanel.getByText('校准身份不完整').first()).toBeVisible()
  })


  test(SCENARIO_TITLES[11], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { thesisState: 'pending', forecastState: 'populated' })
    for (const viewport of [{ width: 1440, height: 960 }, { width: 1024, height: 900 }, { width: 375, height: 844 }]) {
      await page.setViewportSize(viewport)
      await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' })
      await page.goto('/backtest')
      await page.evaluate(() => document.documentElement.classList.add('dark'))
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
      await expect.poll(() => contrastRatio(forecast.getByText('P50', { exact: true }).first())).toBeGreaterThanOrEqual(4.5)
      const fontContracts = await page.locator('[data-phase5-typography]').evaluateAll(elements => elements.map(element => ({ size: getComputedStyle(element).fontSize, weight: getComputedStyle(element).fontWeight })))
      expect(new Set(fontContracts.map(item => item.size))).toEqual(new Set(['24px', '16px', '14px', '12px']))
      expect(new Set(fontContracts.map(item => item.weight))).toEqual(new Set(['400', '600']))
      expect((await page.locator('main').boundingBox())!.width).toBeLessThanOrEqual(viewport.width)
    }
    expectNoAuthorityRequests(telemetry)
  })

  test(SCENARIO_TITLES[12], async ({ page }) => {
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

  test(SCENARIO_TITLES[13], async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { shadowState: 'populated' })
    await page.goto('/backtest')
    const panel = page.getByRole('region', { name: SHADOW_HEADING })
    await requireSurface(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true }))

    await panel.getByRole('button', { name: '基于相同证据集创建新蒸馏运行' }).click()
    await expect(panel.getByText(/已创建可解释候选/)).toBeVisible()

    const distillation = telemetry.mutationBodies.find(
      entry => entry.method === 'POST' && entry.path.endsWith('/candidates'),
    )
    expect(distillation?.body).toEqual({
      feature_names: ['close_return_5d', 'volume_ratio_20d', 'intraday_range'],
      seed: 17,
      max_depth: 3,
      min_leaf_support: 20,
      exit_assumptions: { kind: 'fixed_holding_days', days: 20 },
      holding_assumptions: {
        price_adjustment: 'unadjusted_execution_vs_forward_adjusted_research',
      },
    })
    expect(Object.keys(distillation?.body as Record<string, unknown>)).not.toEqual(
      expect.arrayContaining(['min_samples_leaf', 'min_support', 'min_precision', 'training_window']),
    )

    await panel.getByRole('button', { name: '创建新的样本内与样本外评估' }).click()
    await expect(panel.getByText(/样本内与样本外评估已分别记录/)).toBeVisible()
    const evaluation = telemetry.mutationBodies.find(
      entry => entry.method === 'POST' && entry.path.endsWith('/evaluations'),
    )
    expect(evaluation?.body).toEqual({
      in_sample_window: { start: '2024-01-02', end: '2024-06-28' },
      out_of_sample_window: { start: '2024-07-01', end: '2024-12-31' },
      adjustment_policy: 'governed_adjusted_daily',
      cost_policy: { commission_bps: 3, slippage_bps: 5, stamp_duty_bps: 5 },
    })
    expectNoAuthorityRequests(telemetry)
  })

  test('rapid stock switch keeps Phase 05 object authority local', async ({ page }) => {
    const alternate = { symbol: '000001.SZ', name: '平安银行' }
    const telemetry = await installPhase5Fixture(page, { thesisState: 'pending', forecastState: 'populated' })
    await page.route('**/api/kline/instruments/search**', route => json(route, { results: [alternate] }))
    await page.route('**/api/analysis/subjects/instrument/000001.SZ/reports', async route => {
      const { promise, resolve } = Promise.withResolvers<void>()
      setTimeout(resolve, 600)
      await promise
      return json(route, { reports: [] })
    })
    await page.route('**/api/theses/instruments/000001.SZ/**', async route => {
      const { promise, resolve } = Promise.withResolvers<void>()
      setTimeout(resolve, 600)
      await promise
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/versions')) return json(route, { items: [], offset: 0, limit: 25, total: 0, has_more: false, current_version_id: null })
      if (path.endsWith('/checks')) return json(route, { items: [], offset: 0, limit: 50, total: 0, has_more: false })
      if (path.endsWith('/pending')) return json(route, { items: [], offset: 0, limit: 50, total: 0, has_more: false })
      if (path.endsWith('/history')) return json(route, { items: [], offset: 0, limit: 50, total: 0, has_more: false })
      return json(route, { detail: 'alternate thesis route not found' }, 404)
    })
    await page.route('**/api/forecast/instruments/000001.SZ/**', async route => {
      const { promise, resolve } = Promise.withResolvers<void>()
      setTimeout(resolve, 600)
      await promise
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/records')) return json(route, { records: [], page: { offset: 0, limit: 25, total: 0, has_more: false }, latest_governed_session_id: 'CNA-20260715' })
      if (path.endsWith('/jobs')) return json(route, { jobs: [], page: { offset: 0, limit: 25, total: 0, has_more: false } })
      return json(route, { detail: 'alternate forecast route not found' }, 404)
    })

    await selectStock(page)
    await page.goto('/stock-analysis')
    const thesis = await openAnalysisTab(page, THESIS_TAB)
    await expect(thesis.getByRole('button', { name: '确认论点失效' })).toBeVisible()
    const forecast = await openAnalysisTab(page, FORECAST_TAB)
    await expect(forecast.getByRole('heading', { name: '预测 F-001', exact: true })).toBeVisible()

    const search = page.getByPlaceholder('输入股票代码或名称，如 600000 / 浦发')
    await search.fill('000001')
    await expect(page.getByRole('button', { name: /000001\.SZ.*平安银行/ })).toBeVisible()
    await search.press('Enter')
    await expect(page.getByText(`${alternate.name}（${alternate.symbol}）`).first()).toBeVisible()
    await expect(page.getByRole('tab', { name: '分析结论' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('button', { name: '确认论点失效' })).toHaveCount(0, { timeout: 300 })
    await expect(page.getByRole('heading', { name: '预测 F-001', exact: true })).toHaveCount(0, { timeout: 300 })

    await openAnalysisTab(page, FORECAST_TAB)
    await expect(page.getByText('尚无此标的的概率预测')).toBeVisible()
    await page.route('**/api/kline/instruments/search**', route => json(route, { results: [STOCK] }))
    await search.fill(STOCK.symbol)
    await expect(page.getByRole('button', { name: /600519\.SH.*贵州茅台/ })).toBeVisible()
    await search.press('Enter')
    await expect(page.getByRole('tab', { name: FORECAST_TAB })).toHaveAttribute('aria-selected', 'true')
    expectNoAuthorityRequests(telemetry)
  })

  test('StockAnalysis narrow dialog focus contract', async ({ page }) => {
    const report = {
      id: 'stock-report-today', symbol: STOCK.symbol, name: STOCK.name,
      created_at: new Date().toISOString(), focus: '今日关键价位', summary: '历史报告只读摘要', close: 1450,
    }
    await installPhase5Fixture(page)
    await page.route('**/api/stock-analysis/reports', route => json(route, { reports: [report] }))
    await page.setViewportSize({ width: 375, height: 844 })
    await selectStock(page)
    await page.goto('/stock-analysis')

    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375)
    const deleteControl = page.getByRole('button', { name: '删除' })
    await deleteControl.focus()
    await expect(deleteControl).toBeFocused()
    await expect.poll(() => deleteControl.evaluate(element => Number(getComputedStyle(element).opacity))).toBe(1)

    const trigger = page.getByRole('button', { name: 'AI 个股分析' })
    await trigger.focus()
    await trigger.press('Enter')
    const dialog = page.getByRole('dialog', { name: '该个股已有分析报告' })
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    const firstAction = dialog.getByRole('button', { name: '查看历史' })
    const lastAction = dialog.getByRole('button', { name: '重新分析' })
    await expect(firstAction).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(lastAction).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(firstAction).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
  })

  test('complete path pages and durable retry', async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { forecastState: 'populated' })
    const pagedRecord = { ...forecastRecord, paths: undefined, horizon: 5, catalog_id: 'record-approved' }
    const submissions: Array<Record<string, unknown>> = []
    const requestedOffsets: number[] = []
    await page.route('**/api/forecast/catalog', route => json(route, {
      entries: [
        { ...forecastRecord.checkpoint, catalog_id: 'request-default', available: true, integrity: 'verified' },
        { ...forecastRecord.checkpoint, catalog_id: 'record-approved', available: true, integrity: 'verified' },
      ],
    }))
    await page.route(`**/api/forecast/instruments/${STOCK.symbol}/records**`, route => json(route, {
      records: [pagedRecord],
      page: { offset: 0, limit: 25, total: 1, has_more: false },
      latest_governed_session_id: 'CNA-20260715',
    }))
    await page.route(`**/api/forecast/instruments/${STOCK.symbol}/jobs**`, route => {
      const request = route.request()
      if (request.method() === 'GET') return json(route, { jobs: [], page: { offset: 0, limit: 25, total: 0, has_more: false } })
      const body = request.postDataJSON() as Record<string, unknown>
      submissions.push(body)
      if (submissions.length === 1) return route.abort('connectionreset')
      return json(route, { job: { id: 'forecast-retry-job', instrument: STOCK.symbol, horizon: body.horizon, catalog_id: body.catalog_id, status: 'completed', stage: 'completed', stage_recorded_at: '2026-07-17T09:30:00Z', attempt: 1, created_at: '2026-07-17T09:30:00Z', updated_at: '2026-07-17T09:30:00Z', record_id: pagedRecord.id } }, 201)
    })
    await page.route(`**/api/forecast/records/${pagedRecord.id}/paths**`, route => {
      const url = new URL(route.request().url())
      const offset = Number(url.searchParams.get('offset') ?? 0)
      const limit = Number(url.searchParams.get('limit') ?? 12)
      requestedOffsets.push(offset)
      const selected = Array.from({ length: Math.min(limit, 32 - offset) }, (_, index) => offset + index)
      const items = selected.flatMap(pathIndex => ['CNA-20260801', 'CNA-20260804'].flatMap((sessionId, sessionIndex) => [
        { path_index: pathIndex, session_id: sessionId, feature: 'close', value: 1450 + pathIndex + sessionIndex },
        { path_index: pathIndex, session_id: sessionId, feature: 'volume', value: 100000 + pathIndex * 100 + sessionIndex },
      ]))
      return json(route, { paths: { items, offset, limit, total: 32, has_more: offset + selected.length < 32 } })
    })

    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    await panel.getByRole('button', { name: '查看采样路径' }).click()
    await expect(panel.getByText('共 32 条路径 · 第 1/3 页')).toBeVisible()
    await panel.getByRole('button', { name: '下一页采样路径' }).click()
    await expect(panel.getByText('共 32 条路径 · 第 2/3 页')).toBeVisible()
    await panel.getByRole('button', { name: '下一页采样路径' }).click()
    await expect(panel.getByText('共 32 条路径 · 第 3/3 页')).toBeVisible()
    await expect(panel.getByRole('checkbox', { name: '采样路径 25' })).toBeVisible()
    expect(requestedOffsets).toEqual(expect.arrayContaining([0, 12, 24]))

    await panel.getByRole('button', { name: '基于相同配置创建新预测' }).click()
    await expect(panel.getByRole('button', { name: '查看恢复方式' })).toBeVisible()
    await panel.getByRole('button', { name: '查看恢复方式' }).click()
    await expect.poll(() => submissions.length).toBe(2)
    expect(submissions[0].idempotency_key).toBe(submissions[1].idempotency_key)
    expect(submissions[1]).toMatchObject({ horizon: 5, catalog_id: 'record-approved' })
    expectNoAuthorityRequests(telemetry)
  })

  test('paged Thesis history and strict condition review', async ({ page }) => {
    const telemetry = await installPhase5Fixture(page, { thesisState: 'populated' })
    const routeOffsets: Record<string, number[]> = { versions: [], checks: [], pending: [], history: [] }
    await page.route(`**/api/theses/instruments/${STOCK.symbol}/**`, route => {
      const url = new URL(route.request().url())
      const resource = url.pathname.split('/').at(-1) as keyof typeof routeOffsets
      const offset = Number(url.searchParams.get('offset') ?? 0)
      const limit = Number(url.searchParams.get('limit') ?? 1)
      routeOffsets[resource].push(offset)
      if (resource === 'versions') {
        const items = offset === 0 ? [thesisVersion(2)] : [thesisVersion(1)]
        return json(route, { items, current_version_id: 'thesis-version-2', offset, limit, total: 2, has_more: offset === 0 })
      }
      if (resource === 'checks') {
        const items = offset === 0 ? thesisChecks.slice(0, 2) : thesisChecks.slice(2)
        return json(route, { items, offset, limit, total: 4, has_more: offset === 0 })
      }
      if (resource === 'pending') return json(route, { items: [], offset, limit, total: 0, has_more: false })
      if (resource === 'history') {
        const item = { ...pending, id: offset === 0 ? 'history-current' : 'history-superseded', status: offset === 0 ? 'pending' : 'confirmed', actionable: offset === 0, superseded: offset > 0 }
        return json(route, { items: [item], offset, limit, total: 2, has_more: offset === 0 })
      }
      return json(route, { detail: 'unknown thesis page' }, 404)
    })

    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, THESIS_TAB)
    await panel.getByRole('button', { name: '加载更多论点版本' }).click()
    await expect(panel.getByRole('row', { name: /^版本 1 / })).toBeVisible()
    await panel.getByRole('button', { name: '加载更多检查记录' }).click()
    await expect(panel.getByText('检查错误', { exact: true })).toBeVisible()
    await panel.getByRole('button', { name: '加载更多论点历史' }).click()
    await expect(panel.getByRole('row', { name: /history-superseded.*已确认/ })).toBeVisible()
    expect(routeOffsets.versions).toEqual(expect.arrayContaining([0, 1]))
    expect(routeOffsets.checks).toEqual(expect.arrayContaining([0, 2]))
    expect(routeOffsets.history).toEqual(expect.arrayContaining([0, 1]))

    await panel.getByRole('button', { name: '基于此版本创建新版本' }).click()
    await panel.getByLabel('版本变更理由').fill('严格校验区间与 lookback')
    await panel.getByLabel('运算符').first().selectOption('between')
    await panel.getByLabel('阈值').first().fill('850')
    await panel.getByRole('button', { name: '进入审阅' }).click()
    await expect(panel.getByRole('alert')).toContainText('区间阈值必须恰好包含两个有限数字')
    await panel.getByLabel('阈值').first().fill('900,850')
    await panel.getByRole('button', { name: '进入审阅' }).click()
    await expect(panel.getByRole('alert')).toContainText('区间下限必须小于或等于上限')
    await panel.getByLabel('阈值').first().fill('850,900')
    await panel.getByLabel('lookback（日）').first().fill('0')
    await panel.getByRole('button', { name: '进入审阅' }).click()
    await expect(panel.getByRole('alert')).toContainText('lookback 必须是正整数')
    await panel.getByLabel('lookback（日）').first().fill('1.5')
    await panel.getByRole('button', { name: '进入审阅' }).click()
    await expect(panel.getByRole('alert')).toContainText('lookback 必须是正整数')
    expectNoAuthorityRequests(telemetry)
  })

  test('Forecast SSE persisted resume and flapping budget', async ({ page }) => {
    await page.clock.install()
    const telemetry = await installPhase5Fixture(page, { forecastState: 'terminal' })
    const resumeHeaders: Array<string | undefined> = []
    let streamRequests = 0
    await page.route('**/api/forecast/jobs/**/stream', route => {
      streamRequests += 1
      resumeHeaders.push(route.request().headers()['last-event-id'])
      if (streamRequests === 1) {
        return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'id: 3\nevent: forecast_progress\ndata: {"job_id":"forecast-job-2","stage":"generating_paths","status":"running","stage_recorded_at":"2026-07-17T09:30:00Z"}\n\n' })
      }
      if (streamRequests === 2) return json(route, { detail: { code: 'forecast_subscription_capacity', retryable: true } }, 429)
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: stream_ready\ndata: {}\n\n' })
    })

    await selectStock(page)
    await page.goto('/stock-analysis')
    const panel = await openAnalysisTab(page, FORECAST_TAB)
    await panel.getByRole('button', { name: '生成概率预测' }).click()
    await page.clock.runFor(40_000)
    await expect.poll(() => streamRequests).toBe(6)
    expect(resumeHeaders[0]).toBeUndefined()
    expect(resumeHeaders.slice(1)).toEqual(['3', '3', '3', '3', '3'])
    await expect(panel.getByText('进度连接已中断，正在按记录状态重新连接。')).toBeVisible()
    expectNoAuthorityRequests(telemetry)
  })
})
