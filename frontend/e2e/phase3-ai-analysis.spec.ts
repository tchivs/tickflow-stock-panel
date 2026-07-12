import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

const subject = { kind: 'stock', key: '600519.SH' }
const report = {
  id: 'report-moutai-1', subject, version: 1, status: 'validated', generated_at: '2024-07-01T10:00:00Z',
  evidence_limitations: ['收入同比存在未解决来源差异'],
  perspectives: [{ name: '基本面', conclusion: '收入增长需要核验', evidence_count: 2, limitations: ['口径不同'] }],
  score: { value: 60, dimensions: [{ name: '盈利质量', contribution: 60, evidence_ids: ['number-revenue'], rationale: '已披露口径不同' }] },
  valuation: { applicable: false, reason: '材料输入不完整' },
  ic_memo: { thesis: '等待独立来源确认', risks: ['收入数字存在差异'], open_questions: ['确认报告期口径'] }, signal_id: 'signal-moutai',
}
const portfolioReport = {
  ...report,
  id: 'report-portfolio-1',
  subject: { kind: 'portfolio', key: '1' },
  evidence_limitations: [],
  signal_id: 'signal-portfolio',
}
const evidence = {
  report_id: report.id,
  sources: [
    { id: 'source-filing', name: '公司公告', grade: 'A', source_type: 'governed_filing', retrieved_at: '2024-06-30T00:00:00Z' },
    { id: 'source-secondary', name: '二级数据源', grade: 'B', source_type: 'secondary', retrieved_at: '2024-06-30T00:00:00Z' },
    { id: 'source-assist', name: '待验证辅助来源', grade: 'C', source_type: 'assisted', retrieved_at: '2024-06-30T00:00:00Z' },
  ],
  material_numbers: [{ id: 'number-revenue', label: '收入同比', value: 12.4, unit: '%', period: '2024Q1', source_count: 2, cross_check: 'conflicting', difference_reason: '报告期口径不一致' }],
}
const history = {
  signal_id: 'signal-portfolio', current_state: 'priced_in',
  events: [
    { state: 'strengthened', occurred_at: '2024-01-02T10:00:00Z', evidence_summary: '新增 A 级来源', source_grade: 'A', cross_check: 'confirmed' },
    { state: 'weakened', occurred_at: '2024-02-02T10:00:00Z', evidence_summary: '增长放缓', source_grade: 'B', cross_check: 'unresolved' },
    { state: 'falsified', occurred_at: '2024-03-02T10:00:00Z', evidence_summary: '失效条件触发', source_grade: 'A', cross_check: 'confirmed' },
    { state: 'priced_in', occurred_at: '2024-04-02T10:00:00Z', evidence_summary: '价格已反映事件', source_grade: 'B', cross_check: 'confirmed' },
  ],
  pending_review_id: 'review-server-issued',
  reviews: [
    { id: 'review-server-issued', prior_state: 'active', proposed_state: 'strengthened', status: 'pending', evidence_ids: ['source-filing'], rationale: '新增可归因证据', created_at: '2024-07-01T10:00:00Z' },
    { id: 'review-confirmed', prior_state: 'active', proposed_state: 'strengthened', status: 'confirmed', evidence_ids: ['source-filing'], rationale: '已确认提案', created_at: '2024-06-01T10:00:00Z' },
    { id: 'review-rejected', prior_state: 'strengthened', proposed_state: 'weakened', status: 'rejected', evidence_ids: ['source-secondary'], rationale: '已拒绝提案', created_at: '2024-05-01T10:00:00Z' },
  ],
  plans: [{ id: 'plan-server-issued', review_id: 'review-confirmed', event_id: 'event-confirmed', window_days: 60, benchmark: 'CSI300', metric: 'excess_return', created_at: '2024-06-01T10:00:00Z', outcomes: [{ id: 'outcome-server-issued', plan_id: 'plan-server-issued', observed_at: '2024-08-30T10:00:00Z', created_at: '2024-08-30T10:00:00Z', outcome: { status: 'complete', observed_value: 0.12, notes: 'tracked' } }] }],
  outcome: { status: 'recorded', outcomes: [{ id: 'outcome-server-issued', plan_id: 'plan-server-issued', observed_at: '2024-08-30T10:00:00Z', created_at: '2024-08-30T10:00:00Z', outcome: { status: 'complete', observed_value: 0.12, notes: 'tracked' } }] },
}

async function installAnalysisFixture(page: import('@playwright/test').Page) {
  await page.route('**/api/**', route => route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ detail: `Unhandled fixture route: ${new URL(route.request().url()).pathname}` }),
  }))
  await page.route('**/api/settings', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ onboarding_completed: true }) }))
  await page.route('**/api/portfolio/**', route => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    if (path.endsWith('/accounts')) return json({ accounts: [{ id: 1, name: '测试账户', archived_at: null }] })
    if (path.endsWith('/summary')) return json({ total_assets: 100000, available_funds: 10000, market_value: 90000, unrealized_pnl: 1000, positions: [] })
    if (path.endsWith('/positions')) return json({ positions: [] })
    return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled portfolio fixture route: ${path}` }) })
  })
  await page.route('**/api/monitor/rules**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ rules: [] }) }))
  await page.route('**/api/analysis/**', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    const selectedReport = /\/subjects\/account\//.test(path) ? portfolioReport : report
    if (path.endsWith('/reports') && /\/subjects\/(instrument|account)\//.test(path)) return json({ reports: [selectedReport] })
    if (path.endsWith(`/reports/${report.id}`)) return json({ report })
    if (path.endsWith(`/reports/${portfolioReport.id}`)) return json({ report: portfolioReport })
    if (path.endsWith(`/reports/${report.id}/evidence`)) return json(evidence)
    if (path.endsWith(`/reports/${portfolioReport.id}/evidence`)) return json({ ...evidence, report_id: portfolioReport.id })
    if (path.endsWith(`/signals/${history.signal_id}/history`)) return json(history)
    if (path.endsWith('/runs') && request.method() === 'POST') {
      const body = request.postDataJSON() as { subject_kind?: string }
      if (body.subject_kind !== 'instrument' && body.subject_kind !== 'account') return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: 'subject kind must be server-owned instrument or account' }) })
      return json({ run: { id: 'run-moutai-1', subject, status: 'running' } })
    }
    if (path.endsWith('/confirm')) {
      expect(request.postDataJSON()).toEqual({ window_days: 60 })
      return json({ review: { id: 'review-server-issued', status: 'confirmed' } })
    }
    if (path.endsWith('/reject')) {
      expect(request.postData()).toBeNull()
      return json({ review: { id: 'review-server-issued', status: 'rejected' } })
    }
    return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture route: ${path}` }) })
  })
}

test.describe('Phase 3 evidence-first analysis contracts', () => {
  test('stock report exposes source grades, material evidence, and conflict before conclusions', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium only')
    await installAnalysisFixture(page)
    await page.addInitScript(() => localStorage.setItem('last_stock:stock-analysis', JSON.stringify({ symbol: '600519.SH', name: '贵州茅台' })))
    await page.goto('/stock-analysis')
    await expect(page.getByRole('button', { name: '生成含证据说明的分析' })).toBeVisible()
    await expect(page.getByText('存在未解决差异').first()).toBeVisible()
    await expect(page.getByText('受未解决来源差异影响').first()).toBeVisible()
    await expect(page.getByText('投资委员会备忘录')).toBeVisible()
    await expect(page.getByText('AI 结论基于所列证据生成；来源等级和核验状态限制其可采信程度，不构成投资建议。')).toBeVisible()
    await page.getByRole('tab', { name: '来源与核验' }).click()
    await expect(page.getByText('A=原始或已治理来源')).toBeVisible()
    await expect(page.getByRole('rowheader', { name: '收入同比' })).toBeVisible()
    await page.locator('summary', { hasText: '查看收入同比的 2 个来源' }).click()
    await expect(page.getByText('A 级 公司公告')).toBeVisible()
  })

  test('portfolio lifecycle keeps server-owned history and review actions scoped', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium only')
    await installAnalysisFixture(page)
    await page.goto('/portfolio')
    await page.getByLabel('选择账户').selectOption('1')
    await page.getByRole('tab', { name: '信号历史' }).click()
    await expect(page.getByRole('heading', { name: '信号生命周期' })).toBeVisible()
    await expect(page.getByText('信号已计价').first()).toBeVisible()
    await expect(page.getByText('待审生命周期提案：信号已强化')).toBeVisible()
    await expect(page.getByText('审阅记录')).toBeVisible()
    await expect(page.getByText('60 个交易日观察计划')).toBeVisible()
    await expect(page.getByText('已记录结果').first()).toBeVisible()
    const confirm = page.getByRole('button', { name: '确认服务端审阅' })
    await expect(confirm).toBeVisible()
    await confirm.click()
    await expect(page.getByText('信号已计价').first()).toBeVisible()
  })

  test('responsive keyboard controls retain accessible analysis panels', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium only')
    await installAnalysisFixture(page)
    await page.addInitScript(() => localStorage.setItem('last_stock:stock-analysis', JSON.stringify({ symbol: '600519.SH', name: '贵州茅台' })))
    for (const viewport of [{ width: 1440, height: 960 }, { width: 1024, height: 900 }, { width: 375, height: 844 }]) {
      await page.setViewportSize(viewport)
      await page.goto('/stock-analysis')
      const reportTab = page.getByRole('tab', { name: '分析结论' })
      await reportTab.focus({ timeout: 1_000 })
      await page.keyboard.press('ArrowRight')
      await expect(page.getByRole('tab', { name: '来源与核验' })).toBeFocused()
      await page.keyboard.press('Enter')
      await expect(page.getByRole('table', { name: /材料数字/ })).toBeVisible()
      const generate = page.getByRole('button', { name: '生成含证据说明的分析' })
      const box = await generate.boundingBox()
      expect(box?.height).toBeGreaterThanOrEqual(44)
    }
  })
})
