import { defineConfig } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Isolated real FastAPI + Vite pair for Phase 05 CR-01 Shadow real-host proof.
 * Backend: backend/tests/phase5_real_host_harness.py on 127.0.0.1:3018
 * Frontend: Vite on 127.0.0.1:4175 (proxies /api to production optional host)
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..')
const backendRoot = path.join(repoRoot, 'backend')
const pythonBin = path.join(backendRoot, '.venv', 'bin', 'python3')
const browserUrl = 'http://127.0.0.1:4175'
const apiUrl = 'http://127.0.0.1:3018'
const password = process.env.PHASE5_REAL_HOST_PASSWORD ?? 'phase5-real-host-password'
const venvBin = path.join(backendRoot, '.venv', 'bin')

const backendCommand = [
  `export PATH="${venvBin}:$PATH"`,
  `cd "${backendRoot}"`,
  'export PHASE5_REAL_HOST_PORT=3018',
  `export PHASE5_REAL_HOST_PASSWORD='${password}'`,
  'export ATHENA_ALLOW_NETWORK=0',
  'export PYTHONPATH=.',
  `"${pythonBin}" -m uvicorn tests.phase5_real_host_harness:create_app --factory --host 127.0.0.1 --port 3018`,
].join(' && ')

export default defineConfig({
  testDir: './e2e',
  testMatch: /phase5-shadow-real-host\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 240_000,
  reporter: [['list'], ['json', { outputFile: 'test-results/phase5-shadow-real-host.json' }]],
  use: {
    baseURL: browserUrl,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    launchOptions: {
      args: ['--disable-features=HttpsFirstBalancedModeAutoEnable,HttpsUpgrades'],
    },
  },
  webServer: [
    {
      command: backendCommand,
      url: `${apiUrl}/health`,
      reuseExistingServer: false,
      timeout: 180_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: 'npx --no-install vite --host 127.0.0.1 --port 4175 --strictPort',
      url: browserUrl,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
  projects: [
    {
      name: 'phase5-shadow-real-host',
      use: {
        baseURL: browserUrl,
        browserName: 'chromium',
        viewport: { width: 1440, height: 960 },
      },
    },
  ],
})
