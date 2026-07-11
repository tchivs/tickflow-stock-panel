import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

const revision = {
  id: 'revision-manual', factor_id: 'factor-manual', revision_number: 1, name: '短期动量', description: '收盘价相对20日均线', hypothesis: '价格相对均线反映趋势强度',
  canonical_expression: 'close / ma20', dsl_version: 'factor-dsl-v1', ast_signature: 'divide(close,ma20)', shape_signature: 'divide(field,field)', fields: ['close', 'ma20'], operators: ['/'], functions: [], provenance: { source: 'manual' }, created_at: '2024-07-01T10:00:00Z',
}
const reviewedRevision = { ...revision, id: 'revision-reviewed', factor_id: 'factor-reviewed', name: '审阅趋势', provenance: { source: 'reviewed_hypothesis' } }
const artifact = { evaluation_run_id: 'run-completed', relative_path: 'research_artifacts/run-completed/metrics.json', content_type: 'application/json', byte_size: 128, checksum_sha256: 'abc123', created_at: '2024-07-01T10:05:00Z' }
const config = { universe: '沪深A股样本', symbols: ['600519.SH', '000001.SZ'], start: '2024-01-01', end: '2024-06-30', forward_return_horizon: 5, data_revision: 'lake-r17' }
const manifest = { universe: '沪深A股样本', revision: 'lake-r17', row_count: 100, observed_min_date: '2024-01-01', observed_max_date: '2024-06-30' }
const metrics = { ic_series: [{ date: '2024-01-02', ic: 0.12 }], rank_ic_series: [{ date: '2024-01-02', rank_ic: 0.34 }], ic_summary: { mean: 0.12, std: 0.01, information_ratio: 12, positive_rate: 1, observations: 1 }, rank_ic_summary: { mean: 0.34, std: 0.02, information_ratio: 17, positive_rate: 1, observations: 1 } }
const makeExperiment = (id: string, retained: boolean, overrides: Record<string, unknown> = {}) => ({
  id, originating_run_id: id === 'experiment-completed' ? 'run-completed' : 'run-baseline', status: 'completed', validated: true, retained_at: retained ? '2024-07-01T10:06:00Z' : null,
  subject: { kind: 'factor' as const, revision_id: id === 'experiment-completed' ? 'revision-reviewed' : 'revision-baseline' }, resolved_config: { ...config, ...overrides }, input_manifest: { ...manifest, ...(id === 'experiment-baseline' ? { revision: 'lake-r16' } : {}) }, prediction_signals: { signal_artifact_paths: [artifact.relative_path] }, metrics, artifacts: [artifact], diagnostics: {}, model_provenance: { provider: 'offline_fake', model: 'offline-fixture', model_version: 'offline-v1', provenance: { prompt_template_version: 'factor-hypothesis-v1' } }, created_at: '2024-07-01T10:05:00Z',
})

test.describe('Phase 2 researcher workflow', () => {
  test('manual validation and reviewed draft retain explicit evidence before a mismatched comparison', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop workflow')
    let completedRetained = false
    const baseline = makeExperiment('experiment-baseline', true, { end: '2024-05-31' })
    const completed = makeExperiment('experiment-completed', false)

    await page.route('**/api/**', route => route.fulfill({ contentType: 'application/json', body: '{}' }))
    await page.route('**/api/settings', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ onboarding_completed: true }) }))
    await page.route('**/api/research**', async route => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname
      const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
      if (path.endsWith('/dsl/options')) return json({ dsl_version: 'factor-dsl-v1', fields: ['close', 'ma20'], functions: {}, operators: ['+', '-', '*', '/'] })
      if (path.endsWith('/dsl/validate')) return json({ valid: true, normalized_expression: 'close / ma20', dsl_version: 'factor-dsl-v1', fields: ['close', 'ma20'], operators: ['/'], functions: [] })
      if (path.endsWith('/factors/similarity')) return json({ candidates: [{ revision: { ...revision, id: 'revision-similar', name: '相似趋势因子' }, score: 0.82, components: { exact_structural_match: false, shape_match: 1, field_overlap: 1, operator_function_overlap: 1 }, reason: '相同表达式形状和字段重叠' }] })
      if (path.endsWith('/hypotheses/drafts')) return json({ draft_id: 'draft-1', hypothesis: '寻找价格相对均线的趋势因子', expression: 'close / ma20', normalized_expression: 'close / ma20', explanation: '趋势强度的确定性假设。', assumptions: ['使用收盘价'], provenance: { provider: 'offline_fake', model: 'offline-fixture', model_version: 'offline-v1' } })
      if (path.endsWith('/hypotheses/reviewed-factor')) return json(reviewedRevision)
      if (path.endsWith('/factors') && request.method() === 'POST') return json(revision)
      if (path.endsWith('/factors')) return json({ factors: [revision, reviewedRevision] })
      if (path.includes('/factor-revisions/') && path.endsWith('/evaluate')) return json({ evaluation: { evaluation_run_id: 'run-completed', status: 'completed', factor_revision: reviewedRevision, resolved_config: config, input_manifest: manifest, ...metrics, group_stats: [], group_nav: [], long_short_stats: {}, long_short_nav: [], artifacts: [artifact], diagnostics: [] }, experiment: completed })
      if (path.endsWith('/experiments/experiment-completed/retain')) { completedRetained = true; return json({ ...completed, retained_at: '2024-07-01T10:06:00Z' }) }
      if (path.endsWith('/experiments')) return json({ experiments: [baseline, completedRetained ? { ...completed, retained_at: '2024-07-01T10:06:00Z' } : completed] })
      if (path.endsWith('/comparison/candidates')) return json({ experiments: completedRetained ? [baseline, { ...completed, retained_at: '2024-07-01T10:06:00Z' }] : [baseline] })
      if (path.endsWith('/comparison')) return json({ experiments: [baseline, { ...completed, retained_at: '2024-07-01T10:06:00Z' }], deltas: { resolved_config: { end: { 'experiment-baseline': '2024-05-31', 'experiment-completed': '2024-06-30' } }, input_manifest: { revision: { 'experiment-baseline': 'lake-r16', 'experiment-completed': 'lake-r17' } } }, warnings: ['date window differs', 'data revision differs'] })
      return json({ detail: `Unhandled fixture route: ${path}` }, 500)
    })

    await page.goto('/backtest')
    await page.getByRole('tab', { name: '因子回测' }).click()
    await page.getByRole('button', { name: '验证表达式' }).click()
    await expect(page.getByText('已验证：close / ma20')).toBeVisible()
    await expect(page.getByText('相同表达式形状和字段重叠')).toBeVisible()
    await page.getByRole('button', { name: '保存修订版' }).click()
    await expect(page.getByText(/已保存修订版 #1/)).toBeVisible()

    await page.getByRole('button', { name: '生成审阅草稿' }).click()
    await expect(page.getByText('草稿：不可比较')).toBeVisible()
    await expect(page.getByText('趋势强度的确定性假设。')).toBeVisible()
    await expect(page.getByRole('button', { name: '确认审阅并保存修订版' })).toBeDisabled()
    await page.getByRole('checkbox', { name: '我已审阅草稿' }).check()
    await page.getByRole('button', { name: '确认审阅并保存修订版' }).click()
    await expect(page.getByText(/已保存修订版 #1/).last()).toBeVisible()

    await page.getByRole('button', { name: '运行受治理因子评估' }).click()
    await expect(page.getByRole('region', { name: '研究证据' }).getByText('Pearson IC')).toBeVisible()
    await expect(page.getByRole('region', { name: '研究证据' }).getByText('RankIC（Spearman）')).toBeVisible()
    await expect(page.getByText('已完成，未保留')).toBeVisible()
    await expect(page.getByRole('button', { name: /比较已选实验/ })).toBeDisabled()

    await page.getByRole('button', { name: '显式保留此完成证据以供比较' }).click()
    await expect(page.getByText('已保留：此完成快照现在可在比较中选择。')).toBeVisible()
    await page.getByRole('checkbox', { name: '选择实验 experiment-baseline' }).check()
    await page.getByRole('checkbox', { name: '选择实验 experiment-completed' }).check()
    await page.getByRole('button', { name: '比较已选实验（2）' }).click()
    await expect(page.getByRole('complementary', { name: '兼容性警告' })).toContainText('date window differs')
    await expect(page.getByRole('complementary', { name: '兼容性警告' })).toContainText('data revision differs')
    await expect(page.getByText('度量（Pearson IC 与 RankIC 独立）').first()).toBeVisible()
  })
})

const strategyDetail = {
  id: 'registered-demo', name: '注册策略', description: '确定性测试策略', source: 'builtin', params: [], params_defaults: {}, basic_filter: {}, entry_signals: [], exit_signals: [], scoring: {}, stop_loss: null, take_profit: null, trailing_stop: null, trailing_take_profit_activate: null, trailing_take_profit_drawdown: null, score_min: null, score_max: null, max_hold_days: null,
}
const strategyTrades = Array.from({ length: 12 }, (_, index) => ({ symbol: `6000${index}.SH`, name: `测试${index}`, entry_date: `2024-01-${String(index + 1).padStart(2, '0')}`, exit_date: `2024-01-${String(index + 2).padStart(2, '0')}`, entry_price: 10, exit_price: 11, pnl_pct: 0.1, pnl_amount: 100, duration: 1, exit_reason: 'signal', shares: 100, lots: 1, position_pct: 0.1, entry_value: 1000, exit_value: 1100 }))
const strategyResult = {
  run_id: 'strategy-run', config: { start: '2024-01-01', end: '2024-01-31' }, stats: { mode: 'position', final_equity: 1100000, n_trades: strategyTrades.length }, equity_curve: [{ date: '2024-01-01', value: 1000000 }, { date: '2024-01-31', value: 1100000 }], drawdown_curve: [], benchmark_curve: [], trades: strategyTrades, per_symbol_stats: [{ symbol: '600000.SH', n_trades: 12, total_return: 0.1, win_rate: 1, best: 0.1, worst: 0.1 }], strategy_info: { ...strategyDetail, entry_signals: [], exit_signals: [] }, elapsed_ms: 1, error: null,
}
const retainedStrategy = { ...makeExperiment('strategy-retained', true), subject: { kind: 'strategy' as const, id: 'registered-demo', version: 'v1' } }

async function installStrategyFixture(page: Page, retainStatus = 200) {
  let retained = false
  await page.route('**/api/**', route => route.fulfill({ contentType: 'application/json', body: '{}' }))
  await page.route('**/api/screener/strategies?**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ presets: [{ id: 'registered-demo', name: '注册策略', description: '确定性测试策略', source: 'builtin' }] }) }))
  await page.route('**/api/strategies/registered-demo', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(strategyDetail) }))
  await page.route('**/api/backtest/strategy/stream?**', route => route.fulfill({ contentType: 'text/event-stream', body: `event: research\ndata: {"execution_handle":"sse-only-handle"}\n\nevent: done\ndata: ${JSON.stringify({ ...strategyResult, research_execution_handle: 'sse-only-handle' })}\n\n` }))
  await page.route('**/api/research**', async route => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.endsWith('/dsl/options') || path.endsWith('/dsl/options/')) return json({ dsl_version: 'factor-dsl-v1', fields: ['close', 'ma20'], functions: {}, operators: ['+', '-', '*', '/'] })
    if (path.endsWith('/strategy-executions/sse-only-handle/retain')) {
      if (retainStatus !== 200) return json({ detail: '执行句柄已过期或已保留' }, retainStatus)
      retained = true
      return json(retainedStrategy)
    }
    if (path.endsWith('/experiments') || path.endsWith('/experiments/')) return json({ experiments: retained ? [retainedStrategy] : [] })
    if (path.endsWith('/comparison/candidates') || path.endsWith('/comparison/candidates/')) return json({ experiments: retained ? [retainedStrategy, { ...makeExperiment('baseline-strategy', true), subject: { kind: 'strategy', id: 'baseline', version: 'v1' } }] : [] })
    if (path.endsWith('/comparison') || path.endsWith('/comparison/')) return json({ experiments: [retainedStrategy], warnings: ['data revision differs'], deltas: { input_manifest: {} } })
    if (path.endsWith('/factors') || path.endsWith('/factors/')) return json({ factors: [] })
    return json({})
  })
}

test('strategy retention keyboard flow keeps an SSE handle scoped at every required viewport', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium only')
  for (const viewport of [{ width: 1440, height: 960 }, { width: 1024, height: 900 }, { width: 375, height: 844 }]) {
    await installStrategyFixture(page)
    await page.setViewportSize(viewport)
    await page.goto('/backtest')
    const strategyTab = page.getByRole('tab', { name: '策略回测' })
    await expect(strategyTab).toHaveAttribute('aria-selected', 'true')
    await strategyTab.press('ArrowLeft')
    await expect(page.getByRole('tab', { name: '因子回测' })).toHaveAttribute('aria-selected', 'true')
    await page.getByRole('tab', { name: '因子回测' }).press('ArrowRight')
    await expect(strategyTab).toHaveAttribute('aria-selected', 'true')
    await page.getByRole('button', { name: '注册策略', exact: true }).press('Enter')
    await expect(page.getByRole('button', { name: '运行回测' })).toBeEnabled()
    await page.getByRole('button', { name: '运行回测' }).press('Enter')
    const retain = page.getByRole('button', { name: '保留此完成策略实验以供比较' })
    await expect(retain).toBeVisible()
    if (viewport.width === 375) {
      const box = await retain.boundingBox()
      expect(box?.width).toBeGreaterThanOrEqual(44)
      expect(box?.height).toBeGreaterThanOrEqual(44)
    }
    await retain.press('Enter')
    await expect(page.getByText('已保留：此完成快照现在可在比较中选择。')).toBeVisible()
    await expect(page.getByText('实验 ID：')).toBeVisible()
    const daily = page.getByRole('tab', { name: /每日交易/ })
    await daily.press('ArrowRight')
    await expect(page.getByRole('tab', { name: /交易明细/ })).toHaveAttribute('aria-selected', 'true')
    await page.getByRole('tab', { name: /交易明细/ }).press('ArrowLeft')
    const wrapper = page.getByLabel('每日交易结果表，可使用左右方向键或 End 键查看全部列')
    await wrapper.focus()
    await expect(wrapper).toBeFocused()
    if (viewport.width === 375) {
      await expect(wrapper).toHaveJSProperty('scrollLeft', 0)
      await wrapper.press('ArrowRight')
      await expect(wrapper).not.toHaveJSProperty('scrollLeft', 0)
      await wrapper.press('End')
      await expect(page.getByRole('columnheader', { name: '累计收益' })).toBeInViewport()
    }
  }
})

test('stale strategy retention restores retryable state without promotion', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium only')
  await installStrategyFixture(page, 409)
  await page.goto('/backtest')
  await page.getByRole('button', { name: '注册策略', exact: true }).press('Enter')
  await expect(page.getByRole('button', { name: '运行回测' })).toBeEnabled()
  await page.getByRole('button', { name: '运行回测' }).press('Enter')
  await page.getByRole('button', { name: '保留此完成策略实验以供比较' }).press('Enter')
  await expect(page.getByRole('alert')).toHaveText('无法保留此完成策略实验：执行句柄已过期或已保留。请重试。')
  await expect(page.getByRole('button', { name: '保留此完成策略实验以供比较' })).toBeEnabled()
  await expect(page.getByText('实验 ID：')).toHaveCount(0)
})
