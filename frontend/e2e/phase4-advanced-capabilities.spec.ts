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
    version: 3,
    source_profile: 'operator-research-v1',
    scope: 'CN-A / 600519.SH',
    published_at: '2026-06-01T10:00:00Z',
    conclusion: '中性观察', confidence: 'medium', window_days: 60, benchmark: '000300.SH',
    status: 'unevaluable', reason: '缺少冻结基准价格', revision_kind: 'material_change',
  }],
  calibration: { low: { hit_rate: 0.4, relative_return: -0.01, samples: 3, coverage: '2026Q1' }, medium: { hit_rate: 0.5, relative_return: 0.02, samples: 2, coverage: '2026Q1' }, high: { hit_rate: 0.7, relative_return: 0.04, samples: 1, coverage: '2026Q1' } },
  run: { id: 'advanced-run-fixture', specification_version: 1, governed_fingerprint: 'sha256:governed', asset_version: 'factor-v1', parameters: { lookback: 20 }, environment: 'fixture', resource_limits: { timeout_seconds: 5, memory_limit_mb: 128 }, status: 'constraint_rejected', constraint_reason: 'timeout_exceeded', audit_reference: 'audit-fixture' },
  candidate: { name: '候选策略 A', version: 'v2', parent_version: 'v1', mutation: 'bounded_parameter_shift', seed: 7, resolved_config: { lookback: 20 }, gates: ['合同/沙箱安全', '来源完整性', '样本内与样本外', '稳健性', '成本与可实现性'].map(name => ({ name, status: 'passed', evidence: 'fixture evidence' })) },
  sandbox: { contract_version: 'advanced-strategy-v1', declared_inputs: ['governed_panel'], timeout_seconds: 5, memory_limit_mb: 128, checks: { ast: 'passed', imports: 'passed', timeout: 'passed', memory: 'passed' }, status: 'rejected', safe_reason: 'isolation_unavailable', audit_reference: 'audit-fixture' },
}

async function installAdvancedFixture(page: Page, { rejected = false }: { rejected?: boolean } = {}) {
  const externalRequests: string[] = []
  page.on('request', request => {
    if (!request.url().startsWith('http://127.0.0.1') && !request.url().startsWith('http://localhost')) externalRequests.push(request.url())
  })
  await page.route('**/api/**', route => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }) }))
  await page.route('**/api/settings', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ onboarding_completed: true }) }))
  await page.route('**/api/advanced/**', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.endsWith('/progress')) {
      return route.fulfill({ contentType: 'text/event-stream', body: `event: advanced_progress\ndata: ${JSON.stringify(advancedProgress)}\n\n` })
    }
    if (path.endsWith('/viewpoints')) return json({ viewpoints: advancedFixture.viewpoints, calibration: advancedFixture.calibration })
    if (path.endsWith('/experiments')) return json({ specifications: [], runs: [advancedFixture.run] })
    if (path.endsWith('/candidates')) return json({ candidates: [advancedFixture.candidate] })
    if (path.endsWith('/sandbox/validate') || path.endsWith('/sandbox/runs')) return json({ sandbox: advancedFixture.sandbox }, rejected ? 409 : 200)
    if (path.endsWith('/jobs') && request.method() === 'POST') return rejected ? json({ audit_reference: 'audit-fixture', safe_reason: 'scope_denied' }, 403) : json({ job: advancedProgress })
    if (path.endsWith('/audits/audit-fixture')) return json({ audit: { reference: 'audit-fixture', decision: rejected ? 'rejected' : 'recorded', reason: rejected ? 'scope_denied' : 'safe_fixture' } })
    return json({ detail: `Unhandled advanced fixture route: ${path}` }, 500)
  })
  return { externalRequests }
}

function futurePhase4Ui(testInfo: import('@playwright/test').TestInfo) {
  test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium owns the explicit viewport matrix')
  test.fail(true, 'Phase 4 advanced UI/API wiring is intentionally absent while this Wave 0 contract is RED')
}

test.describe('Phase 4 advanced capability browser contracts', () => {
  test('strict advanced progress parser rejects browser scope and unknown stages', () => {
    expect(parseAdvancedProgress(JSON.stringify(advancedProgress))).toEqual(advancedProgress)
    expect(parseAdvancedProgress(JSON.stringify({ ...advancedProgress, subject_key: 'browser-supplied' }))).toBeNull()
    expect(parseAdvancedProgress(JSON.stringify({ ...advancedProgress, stage: 'running' }))).toBeNull()
    expect(parseAdvancedProgress(JSON.stringify({ ...advancedProgress, token: 'browser-secret' }))).toBeNull()
  })

  test('scenario 1: immutable viewpoint lineage preserves calibration uncertainty', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo)
    const fixture = await installAdvancedFixture(page)
    await page.addInitScript(() => localStorage.setItem('last_stock:stock-analysis', JSON.stringify({ symbol: '600519.SH', name: '贵州茅台' })))
    await page.goto('/stock-analysis')
    await expect(page.getByRole('heading', { name: '归因观点与表现校准' })).toBeVisible()
    await expect(page.getByText('材料立场变化')).toBeVisible()
    await expect(page.getByText('不可评估：缺少冻结基准价格')).toBeVisible()
    await expect(page.getByText('样本不足，暂不能评价置信度校准。')).toBeVisible()
    await expect(page.getByText(/20|60|120 个交易日/)).toBeVisible()
    await expect(page.getByText(/000300\.SH/)).toBeVisible()
    await expect(page.getByText('0%')).toHaveCount(0)
    expect(fixture.externalRequests).toEqual([])
  })

  test('scenario 2: frozen experiment failures never become feedback evidence', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo)
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
    futurePhase4Ui(testInfo)
    const fixture = await installAdvancedFixture(page)
    await page.goto('/backtest')
    await expect(page.getByText('排序不代表可晋级；所有门禁必须独立通过。')).toBeVisible()
    for (const gate of advancedFixture.candidate.gates) await expect(page.getByRole('row', { name: new RegExp(gate.name) })).toBeVisible()
    await page.getByRole('button', { name: '批准晋级为研究策略' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('确认晋级为研究策略')).toBeVisible()
    await expect(dialog.getByLabel(/批准理由/)).toBeVisible()
    await expect(dialog.getByRole('button', { name: '确认晋级为研究策略' })).toBeDisabled()
    await expect(page.getByText(/启用监控|创建交易计划|执行市场操作/)).toHaveCount(0)
    expect(fixture.externalRequests).toEqual([])
  })

  test('scenario 4: scoped agent displays allowlisted stages and rejects without a task stream', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo)
    const allowed = await installAdvancedFixture(page)
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
    futurePhase4Ui(testInfo)
    const fixture = await installAdvancedFixture(page, { rejected: true })
    await page.goto('/backtest')
    await expect(page.getByRole('heading', { name: '自定义策略沙箱' })).toBeVisible()
    await expect(page.getByText('正在检查策略合同与限制…')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '验证并运行受限策略' })).toBeDisabled()
    await expect(page.getByRole('alert')).toHaveText('策略未运行：isolation_unavailable')
    await expect(page.getByText(/traceback|\/tmp\/|source code|token/i)).toHaveCount(0)
    expect(fixture.externalRequests).toEqual([])
  })

  test('scenario 6: keyboard and responsive controls preserve required mobile geometry', async ({ page }, testInfo) => {
    futurePhase4Ui(testInfo)
    const fixture = await installAdvancedFixture(page)
    for (const viewport of [{ width: 1440, height: 960 }, { width: 1024, height: 900 }, { width: 375, height: 844 }]) {
      await page.setViewportSize(viewport)
      await page.goto('/backtest')
      const strategyTab = page.getByRole('tab', { name: '策略回测' })
      await strategyTab.focus()
      await page.keyboard.press('ArrowLeft')
      await expect(page.getByRole('tab', { name: '因子回测' })).toBeFocused()
      const sandboxAction = page.getByRole('button', { name: '验证并运行受限策略' })
      await expect(sandboxAction).toBeVisible({ timeout: 1_000 })
      const box = await sandboxAction.boundingBox()
      expect(box?.height).toBeGreaterThanOrEqual(44)
      await expect(page.getByText('左右滚动查看完整记录')).toBeVisible()
    }
    expect(fixture.externalRequests).toEqual([])
  })
})
