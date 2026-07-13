import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'
import { parseAdvancedProgress } from '../src/lib/useQuoteStream'

const DESKTOP_PROJECT = 'desktop-chromium'
const advancedProgress = {
  job_id: 'advanced-job-fixture',
  subject_kind: 'instrument',
  subject_key: '600519.SH',
  stage: 'awaiting_review',
  occurred_at: '2026-07-12T10:00:00Z',
  audit_reference: 'audit-fixture',
}

const advancedFixture = {
  viewpoints: [{
    id: 'advanced-viewpoint-version-fixture', viewpoint_id: 'advanced-viewpoint-fixture',
    version: 3,
    source_profile: 'operator-research-v1',
    scope: 'CN-A / 600519.SH',
    published_at: '2026-06-01T10:00:00Z',
    conclusion: '中性观察', direction: 'neutral', rating: 'neutral', target_range: [1000, 1100], horizon_days: 60, confidence: 'medium',
    status: 'unevaluable', revision_kind: 'material_stance_change', correction_reason: null, audit_reference: 'audit-fixture',
    evaluation: { status: 'unevaluable', reason: '缺少冻结基准价格', window_days: 60, benchmark: '000300.SH', relative_return: null },
  }],
  calibration: { low: { status: 'calibrated', hit_rate: 0.4, mean_relative_return: -0.01, sample_count: 3, coverage_start: '2026-01-01', coverage_end: '2026-03-31' }, medium: { status: 'insufficient_sample', hit_rate: 0.5, mean_relative_return: 0.02, sample_count: 2, coverage_start: '2026-01-01', coverage_end: '2026-03-31' }, high: { status: 'insufficient_sample', hit_rate: 0.7, mean_relative_return: 0.04, sample_count: 1, coverage_start: '2026-01-01', coverage_end: '2026-03-31' }, excluded_unevaluable: 0 },
  run: { id: 'advanced-run-fixture', specification_id: 'advanced-spec-fixture', governed_fingerprint: 'sha256:governed', asset_version: 'factor-v1', parameters: { lookback: 20 }, environment: { runtime: 'fixture' }, resource_limits: { timeout_seconds: 5, memory_limit_mb: 128 }, artifact_count: 0, metrics: {}, status: 'timed_out', constraint_reason: 'timeout_exceeded', created_at: '2026-07-12T10:00:00Z' },
  completedRun: { id: 'advanced-completed-run-fixture', specification_id: 'advanced-spec-fixture', governed_fingerprint: 'sha256:completed', asset_version: 'strategy-v2', parameters: { lookback: 20 }, environment: { runtime: 'fixture' }, resource_limits: { timeout_seconds: 5, memory_limit_mb: 128 }, artifact_count: 2, metrics: { sharpe: 1.4 }, status: 'completed', constraint_reason: null, created_at: '2026-07-12T11:00:00Z' },
  candidate: { id: 'advanced-candidate-fixture', parent_asset_id: 'strategy-fixture', parent_version: 'v1', mutation: 'parameter_adjustment', seed: 7, resolved_config: { lookback: 20 }, created_at: '2026-07-12T10:00:00Z', gates: ['合同/沙箱安全', '来源完整性', '样本内与样本外', '稳健性', '成本与可实现性'].map(name => ({ name, status: 'passed', evidence: 'fixture evidence' })) },
  pendingCandidate: { id: 'advanced-pending-candidate-fixture', parent_asset_id: 'strategy-fixture', parent_version: 'v2', mutation: 'adjust_signal_threshold', seed: 9, resolved_config: { lookback: 10 }, created_at: '2026-07-12T11:00:00Z', gates: [] as { name: string; status: string; evidence: string }[] },
  sandbox: { status: 'rejected', reason: 'isolation_unavailable', audit_reference: 'audit-fixture', source_sha256: 'a'.repeat(64) },
  sandboxRun: { run_id: 'sandbox-terminal-fixture', status: 'failed', terminal_reason: 'resource limit reached', proof_fingerprint: 'proof-fixture', resources: { memory_mb: 128, timeout_seconds: 5 }, audit_reference: 'audit-fixture', created_at: '2026-07-12T10:00:00Z' },
}

async function installAdvancedFixture(page: Page, { rejected = false }: { rejected?: boolean } = {}) {
  const externalRequests: string[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    const isLocal = url.hostname === '127.0.0.1' || url.hostname === 'localhost'
    const isExistingFont = ['rsms.me', 'fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname)
    if (!isLocal && !isExistingFont) externalRequests.push(request.url())
  })
  await page.route('**/api/**', route => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) }))
  await page.route('**/api/intraday/stream', route => route.fulfill({ contentType: 'text/event-stream', body: `event: advanced_progress\ndata: ${JSON.stringify(advancedProgress)}\n\n` }))
  await page.route('**/api/settings', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ onboarding_completed: true }) }))
  await page.route('**/api/analysis/subjects/**/reports', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ reports: [] }) }))
  await page.route('**/api/advanced/**', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.endsWith('/progress')) {
      return route.fulfill({ contentType: 'text/event-stream', body: `event: advanced_progress\ndata: ${JSON.stringify(advancedProgress)}\n\n` })
    }
    if (path.endsWith('/viewpoints')) return json({ viewpoints: advancedFixture.viewpoints })
    if (path.includes('/viewpoints/calibration/')) return json({ calibration: advancedFixture.calibration })
    if (path.includes('/viewpoints/') && path.endsWith('/revisions') && request.method() === 'POST') {
      return json({ viewpoint: { ...advancedFixture.viewpoints[0], version: 4, revision_kind: 'non_material_revision' } })
    }
    if (path.includes('/viewpoints/') && path.endsWith('/corrections') && request.method() === 'POST') {
      return json({ viewpoint: { ...advancedFixture.viewpoints[0], version: 5, revision_kind: 'correction', correction_reason: '修正来源日期' } })
    }
    if (path.includes('/viewpoints/versions/') && path.endsWith('/evaluate') && request.method() === 'POST') {
      return json({ viewpoint: { ...advancedFixture.viewpoints[0], evaluation: { status: 'evaluated', reason: null, window_days: 60, benchmark: '000300.SH', relative_return: 0.02 } } })
    }
    if (path.endsWith('/experiments')) return json({ specifications: [], runs: [advancedFixture.run, advancedFixture.completedRun], feedback: [] })
    if (path.endsWith('/candidates')) return json({ candidates: [advancedFixture.candidate, advancedFixture.pendingCandidate] })
    if (path.endsWith('/sandbox/runs')) return json({ runs: [advancedFixture.sandboxRun] })
    if (path.endsWith('/sandbox/validations')) return json({ validations: [advancedFixture.sandbox] })
    if (path.endsWith('/sandbox/submissions')) return json({ validation: advancedFixture.sandbox }, rejected ? 409 : 200)
    if (path.includes('/evolution/candidates/') && path.endsWith('/promote')) return json({ approval: { created_at: '2026-07-12T10:00:00Z' }, registered_strategy: { id: 'registered-fixture', status: 'registered_research_only' } })
    if (path.includes('/subjects/') && path.endsWith('/jobs') && request.method() === 'POST') return rejected ? json({ detail: 'scope_denied' }, 403) : json({ job: { id: advancedProgress.job_id, subject: { kind: 'instrument', key: '600519.SH' }, status: advancedProgress.stage, stage: advancedProgress.stage, stage_recorded_at: advancedProgress.occurred_at, audit_reference: advancedProgress.audit_reference } })
    if (path.includes('/jobs/')) return json({ job: { id: advancedProgress.job_id, subject: { kind: 'instrument', key: '600519.SH' }, status: advancedProgress.stage, stage: advancedProgress.stage, stage_recorded_at: advancedProgress.occurred_at, audit_reference: advancedProgress.audit_reference } })
    if (path.endsWith('/audits/audit-fixture')) return json({ audit: { reference: 'audit-fixture', decision: rejected ? 'rejected' : 'recorded', reason: rejected ? 'scope_denied' : 'safe_fixture' } })
    return json({ detail: `Unhandled advanced fixture route: ${path}` }, 500)
  })
  return { externalRequests }
}

function futurePhase4Ui(testInfo: import('@playwright/test').TestInfo, implemented = false) {
  test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium owns the explicit viewport matrix')
  if (!implemented) test.fail(true, 'This browser contract is implemented by the subsequent 04-11 Backtest workspace plan')
}

test.describe('Phase 4 advanced capability browser contracts', () => {
  test('strict advanced progress parser rejects browser scope and unknown stages', () => {
    expect(parseAdvancedProgress(JSON.stringify(advancedProgress))).toEqual(advancedProgress)
    expect(parseAdvancedProgress(JSON.stringify({ ...advancedProgress, subject_key: 'browser-supplied' }))).toBeNull()
    expect(parseAdvancedProgress(JSON.stringify({ ...advancedProgress, stage: 'running' }))).toBeNull()
    expect(parseAdvancedProgress(JSON.stringify({ ...advancedProgress, token: 'browser-secret' }))).toBeNull()
  })

  test('scenario 1: immutable viewpoint lineage preserves calibration uncertainty', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo, true)
    const fixture = await installAdvancedFixture(page)
    await page.addInitScript(() => localStorage.setItem('last_stock:stock-analysis', JSON.stringify({ symbol: '600519.SH', name: '贵州茅台' })))
    await page.goto('/stock-analysis')
    await expect(page.getByRole('heading', { name: '归因观点与表现校准' })).toBeVisible()
    await expect(page.getByText('材料立场变化').first()).toBeVisible()
    await expect(page.getByText('不可评估：缺少冻结基准价格')).toBeVisible()
    await expect(page.getByText('样本不足，暂不能评价置信度校准。').first()).toBeVisible()
    await expect(page.getByText('60 个交易日，000300.SH，不可评估')).toBeVisible()
    await expect(page.getByText(/000300\.SH/)).toBeVisible()
    await expect(page.getByRole('region', { name: '归因观点与表现校准' }).getByText(/^0%$/)).toHaveCount(0)
    expect(fixture.externalRequests).toEqual([])
  })

  test('scenario 1b: viewpoint actions append bounded revisions and render the server evaluation', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo, true)
    await installAdvancedFixture(page)
    await page.addInitScript(() => localStorage.setItem('last_stock:stock-analysis', JSON.stringify({ symbol: '600519.SH', name: '贵州茅台' })))
    await page.goto('/stock-analysis')

    const panel = page.getByRole('region', { name: '归因观点与表现校准' })
    await panel.getByRole('button', { name: '添加修订' }).click()
    await panel.getByLabel('修订结论').fill('保持中性，但补充已验证证据。')
    await panel.getByRole('button', { name: '保存修订' }).click()
    await panel.getByRole('button', { name: '添加更正' }).click()
    await expect(panel.getByRole('button', { name: '保存更正' })).toBeDisabled()
    await panel.getByLabel('更正原因').fill('修正来源日期')
    await panel.getByRole('button', { name: '保存更正' }).click()
    await panel.getByRole('button', { name: '运行服务端评估' }).click()
    await expect(panel.getByText('已由服务端完成评估')).toBeVisible()
  })

  test('scenario 2: frozen experiment failures never become feedback evidence', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo, true)
    const fixture = await installAdvancedFixture(page)
    await page.goto('/backtest')
    await expect(page.getByRole('heading', { name: '实验规格与运行' })).toBeVisible()
    await expect(page.getByText('sha256:governed')).toBeVisible()
    await expect(page.getByText('运行未完成：timeout_exceeded')).toBeVisible()
    await expect(page.getByRole('button', { name: '以新运行重试' })).toBeVisible()
    await expect(page.getByRole('button', { name: '记录研究反馈' })).toBeDisabled()
    await expect(page.getByText('此运行未完成，不能记录研究反馈。')).toBeVisible()
    expect(fixture.externalRequests).toEqual([])
  })

  test('scenario 3: promotion requires all five gates and an accessible rationale dialog', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo, true)
    const fixture = await installAdvancedFixture(page)
    await page.goto('/backtest')
    await expect(page.getByText('排序不代表可晋级；所有门禁必须独立通过。')).toBeVisible()
    for (const gate of advancedFixture.candidate.gates) await expect(page.getByRole('row', { name: new RegExp(gate.name) })).toBeVisible()
    await page.getByRole('button', { name: '批准晋级为研究策略' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('heading', { name: '确认晋级为研究策略' })).toBeVisible()
    await expect(dialog.getByLabel(/批准理由/)).toBeVisible()
    await expect(dialog.getByRole('button', { name: '确认晋级为研究策略' })).toBeDisabled()
    await expect(page.getByRole('button', { name: /启用监控|创建交易计划|执行市场操作/ })).toHaveCount(0)
    expect(fixture.externalRequests).toEqual([])
  })

  test('scenario 3b: frozen runner scope, gate actions, and terminal sandbox runs remain bounded', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo, true)
    await installAdvancedFixture(page)
    await page.goto('/backtest')

    await page.getByLabel('策略 ID').fill('strategy-fixture')
    await page.getByLabel('开始日期').fill('2026-01-01')
    await page.getByLabel('结束日期').fill('2026-06-30')
    await page.getByLabel('标的代码（可选，逗号分隔）').fill('600519.SH')
    await page.getByLabel('资产类型').selectOption('stock')
    await page.getByLabel('参数（可选 JSON）').fill('{"lookback":20}')
    await expect(page.getByRole('button', { name: '新建实验规格' })).toBeEnabled()

    const pendingCandidate = page.getByText('父策略 v2').locator('..')
    for (const label of ['合同/沙箱安全', '来源完整性', '样本内与样本外', '稳健性', '成本与可实现性']) {
      await expect(pendingCandidate.getByRole('button', { name: `评估门禁：${label}` })).toBeVisible()
    }
    await expect(page.getByText('resource limit reached')).toBeVisible()
    await expect(page.getByText('proof-fixture')).toBeVisible()
    await expect(page.getByText(/\/tmp\/|traceback|source code|token|PATH=/i)).toHaveCount(0)
  })

  test('scenario 4: scoped agent displays allowlisted stages and rejects without a task stream', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo, true)
    const allowed = await installAdvancedFixture(page)
    await page.addInitScript(() => localStorage.setItem('last_stock:stock-analysis', JSON.stringify({ symbol: '600519.SH', name: '贵州茅台' })))
    await page.goto('/stock-analysis')
    const launch = page.getByRole('button', { name: '启动受限研究任务' })
    await expect(launch).toBeVisible({ timeout: 1_000 })
    await launch.click()
    await expect(page.getByText('等待人工复核')).toBeVisible()
    await expect(page.getByText('查看安全审计摘要')).toBeVisible()
    await expect(page.getByText(/advanced-job-fixture|job_id|token|allowlist/i)).toHaveCount(0)
    expect(allowed.externalRequests).toEqual([])

    const rejected = await installAdvancedFixture(page, { rejected: true })
    await page.reload()
    await page.getByRole('button', { name: '启动受限研究任务' }).click()
    await expect(page.getByRole('alert')).toHaveText('任务未启动：scope_denied')
    await expect(page.getByText('正在验证授权范围…')).toHaveCount(0)
    expect(rejected.externalRequests).toEqual([])
  })

  test('scenario 5: same-request contract and source stay redacted across sandbox validation', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo, true)
    const fixture = await installAdvancedFixture(page, { rejected: true })
    await page.goto('/backtest')
    await expect(page.getByRole('heading', { name: '自定义策略沙箱' })).toBeVisible()
    await expect(page.getByText('正在检查策略合同与限制…')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '验证并运行受限策略' })).toBeDisabled()
    await expect(page.getByText(/traceback|\/tmp\/|source code|token/i)).toHaveCount(0)
    expect(fixture.externalRequests).toEqual([])
  })

  test('scenario 6: keyboard and responsive controls preserve required mobile geometry', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo, true)
    const fixture = await installAdvancedFixture(page)
    for (const viewport of [{ width: 1440, height: 960 }, { width: 1024, height: 900 }, { width: 375, height: 844 }]) {
      await page.setViewportSize(viewport)
      await page.goto('/backtest')
      const sandboxAction = page.getByRole('button', { name: '验证并运行受限策略' })
      await expect(sandboxAction).toBeVisible({ timeout: 1_000 })
      const box = await sandboxAction.boundingBox()
      expect(box?.height).toBeGreaterThanOrEqual(44)
      const strategyTab = page.getByRole('tab', { name: '策略回测' })
      await strategyTab.focus()
      await page.keyboard.press('ArrowLeft')
      await expect(page.getByRole('tab', { name: '因子回测' })).toBeFocused()
      await expect(page.getByText('左右滚动查看完整记录')).toHaveCount(0)
    }
    expect(fixture.externalRequests).toEqual([])
  })
})
