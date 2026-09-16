/**
 * S7.4 — the live capture's config. Not a test suite; see `e2e-live/ecertis.spec.ts`.
 *
 * No `webServer` and no fake API: it drives whatever is already running at `E2E_LIVE_BASE`,
 * which is the point — the images it takes are of real services answering.
 *
 * Start that server with `NEXT_DIST_DIR=.next-verify`, the one alternate build directory the
 * repository already ignores in git, eslint and prettier. A fresh name has to be added to all
 * three or `npm run lint` reports a few thousand problems in generated output — which is what
 * a `.next-guide` cost the first time.
 */
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e-live',
  outputDir: './test-results-live',
  workers: 1,
  reporter: [['list']],
  timeout: 120_000,
  use: {
    baseURL: process.env.E2E_LIVE_BASE ?? 'http://127.0.0.1:3200',
    navigationTimeout: 60_000,
    actionTimeout: 15_000,
    screenshot: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
        channel: process.env.E2E_BROWSER_CHANNEL,
      },
    },
  ],
})
