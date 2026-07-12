import { expect, test } from '@playwright/test'

test('real FastAPI host accepts an authorized advanced job and emits root SSE progress', async ({ page }) => {
  await page.goto('/stock-analysis')

  const result = await page.evaluate(async () => {
    const stream = new EventSource('/api/intraday/stream')
    const event = new Promise<string>((resolve, reject) => {
      stream.addEventListener('advanced_progress', message => resolve(message.data))
      stream.addEventListener('error', () => reject(new Error('root SSE did not connect')))
    })
    const response = await fetch('/api/advanced/subjects/600000.SH/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_type: 'research_draft' }),
    })
    const body = await response.json()
    const payload = await event
    stream.close()
    return { status: response.status, body, payload }
  })

  expect(result.status).toBe(200)
  expect(result.body.job.audit_reference).toBeTruthy()
  expect(JSON.parse(result.payload)).toMatchObject({
    job_id: result.body.job.id,
    stage: result.body.job.stage,
    audit_reference: result.body.job.audit_reference,
  })
})
