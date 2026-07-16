#!/usr/bin/env node
/** Strict Playwright RED verifier for the Phase 05 13-scenario UI contract. */
import { spawnSync } from 'node:child_process'
import { readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import process from 'node:process'

const SPEC = 'e2e/phase5-optional-enhancements.spec.ts'
const SPEC_BASENAME = SPEC.split('/').at(-1)
const EXPECTED_TITLES = [
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
]
const REQUIRED_MISSING_SURFACE = new Map([
  [EXPECTED_TITLES[0], 'Shadow 成交证据与策略候选'],
  [EXPECTED_TITLES[1], 'Shadow 成交证据与策略候选'],
  [EXPECTED_TITLES[2], 'Shadow 成交证据与策略候选'],
  [EXPECTED_TITLES[3], 'Shadow 成交证据与策略候选'],
  [EXPECTED_TITLES[4], '投资论点'],
  [EXPECTED_TITLES[5], '投资论点'],
  [EXPECTED_TITLES[6], '投资论点'],
  [EXPECTED_TITLES[7], '概率预测'],
  [EXPECTED_TITLES[8], '概率预测'],
  [EXPECTED_TITLES[9], '概率预测'],
  [EXPECTED_TITLES[10], '概率预测'],
  [EXPECTED_TITLES[11], 'Shadow 成交证据与策略候选'],
  [EXPECTED_TITLES[12], 'Shadow 成交证据与策略候选'],
])
const FATAL_ERROR_PATTERNS = [
  /SyntaxError/i,
  /ReferenceError/i,
  /TypeError:/i,
  /Unhandled fixture route/i,
  /Unhandled (?:Shadow|Thesis|Forecast) fixture route/i,
  /browserType\.launch/i,
  /Executable doesn't exist/i,
  /net::ERR_/i,
  /webServer/i,
  /Test timeout of \d+ms exceeded/i,
  /beforeAll|beforeEach|afterAll|afterEach/i,
  /JSON.*(?:parse|report)/i,
  /unexpected external request/i,
]

function fail(message, details = '') {
  console.error(`Phase 05 Playwright RED verifier rejected: ${message}`)
  if (details) console.error(details)
  process.exit(1)
}

function flattenSuites(suites, inherited = []) {
  const specs = []
  for (const suite of suites ?? []) {
    const titles = suite.title ? [...inherited, suite.title] : inherited
    for (const spec of suite.specs ?? []) specs.push({ ...spec, suiteTitles: titles })
    specs.push(...flattenSuites(suite.suites ?? [], titles))
  }
  return specs
}

const reportPath = join(tmpdir(), `athena-phase5-red-${process.pid}.json`)
const run = spawnSync(
  'pnpm',
  ['exec', 'playwright', 'test', SPEC, '--project=desktop-chromium', '--reporter=json'],
  {
    cwd: process.cwd(),
    encoding: 'utf8',
    timeout: 120_000,
    maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, PLAYWRIGHT_JSON_OUTPUT_FILE: reportPath },
  },
)
if (run.error) {
  const reason = run.error.code === 'ETIMEDOUT' ? 'Playwright command timeout' : `Playwright launch failed: ${run.error.message}`
  fail(reason, `${run.stdout ?? ''}\n${run.stderr ?? ''}`)
}
if (run.signal) fail(`Playwright terminated by ${run.signal}`, `${run.stdout}\n${run.stderr}`)
if (run.status !== 0) fail(`Playwright returned ${run.status}; expected only declared expected failures`, `${run.stdout}\n${run.stderr}`)

let report
try {
  report = JSON.parse(readFileSync(reportPath, 'utf8'))
} catch (error) {
  fail(`JSON report parse failed: ${error instanceof Error ? error.message : String(error)}`, `${run.stdout}\n${run.stderr}`)
} finally {
  rmSync(reportPath, { force: true })
}

if ((report.errors ?? []).length) fail('report contains top-level collection/config/server errors', JSON.stringify(report.errors, null, 2))
const specs = flattenSuites(report.suites).filter(spec => spec.file === SPEC_BASENAME)
const titles = specs.map(spec => spec.title)
if (JSON.stringify(titles) !== JSON.stringify(EXPECTED_TITLES)) {
  const missing = EXPECTED_TITLES.filter(title => !titles.includes(title))
  const extra = titles.filter(title => !EXPECTED_TITLES.includes(title))
  fail(`scenario inventory changed; missing=${JSON.stringify(missing)} extra=${JSON.stringify(extra)} order=${JSON.stringify(titles)}`)
}

for (const spec of specs) {
  if (spec.tests?.length !== 1) fail(`${spec.title} must resolve to exactly one desktop test result`)
  const test = spec.tests[0]
  if (test.projectName !== 'desktop-chromium') fail(`${spec.title} ran in unexpected project ${test.projectName}`)
  if (test.expectedStatus !== 'failed') fail(`${spec.title} lost its explicit expected-failure contract`)
  if ((test.annotations ?? []).some(annotation => annotation.type === 'skip' || annotation.type === 'fixme')) {
    fail(`${spec.title} was skipped/fixme instead of executing`)
  }
  if (test.results?.length !== 1) fail(`${spec.title} retried or did not produce exactly one result`)
  const result = test.results[0]
  if (result.status !== 'failed') fail(`${spec.title} unexpectedly ${result.status}; unexpected pass/skip cannot satisfy RED`)
  const errorText = [result.error?.message, result.error?.stack, ...(result.errors ?? []).flatMap(error => [error.message, error.stack])]
    .filter(Boolean)
    .join('\n')
  const surface = REQUIRED_MISSING_SURFACE.get(spec.title)
  if (!surface || !errorText.includes(surface) || !/toBeVisible|Expected.*visible/i.test(errorText)) {
    fail(`${spec.title} failed outside its approved missing production locator`, errorText)
  }
  const fatal = FATAL_ERROR_PATTERNS.find(pattern => pattern.test(errorText))
  if (fatal) fail(`${spec.title} matched fatal failure ${fatal}`, errorText)
}

const stats = report.stats ?? {}
if (stats.expected !== EXPECTED_TITLES.length || stats.unexpected !== 0 || stats.flaky !== 0 || stats.skipped !== 0) {
  fail(`unexpected report stats ${JSON.stringify(stats)}`)
}
console.log(`Phase 05 Playwright RED contract accepted: ${EXPECTED_TITLES.length} exact scenarios; only allowlisted missing production surfaces failed.`)
