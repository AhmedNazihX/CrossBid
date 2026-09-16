/**
 * Playwright for the web app (story S7.7): `npm run test:e2e` from `frontend/`.
 *
 * **What the suite is.** Six journeys in `e2e/`, each written against a defect the
 * 2026-09-15 audit found shipped — the new-bid flow's frozen checklist and wrong default,
 * the transparent "Review verdict" control, the 2 px tab strip — plus the 404 page and a
 * console-error guard that runs on every test. The Next app is real; the API is replaced at
 * the browser's network edge by `e2e/support/fake-api.ts`, typed from `lib/api.ts`, and a
 * call nothing stubbed fails the test by name. So a run needs **no API, no database, no
 * Supabase and no secrets** — and cannot create rows anywhere, which matters because the
 * stack a developer has running points at the owner's hosted project.
 *
 * **How it gets a server — two ways, neither silent.**
 *
 * 1. `E2E_BASE_URL` unset (the default): the `webServer` block below starts `next dev` on
 *    `127.0.0.1:3100` in dev auth mode, with the fake's origin baked in as
 *    `NEXT_PUBLIC_API_URL`, and stops it afterwards. `reuseExistingServer` is `false` on
 *    purpose: something already on :3100 is an error naming the port, not a server to trust.
 *    It is `next dev`, never `next build`: `output: 'standalone'` means `next start` cannot
 *    serve this app, and a build while a dev server serves `:3000` overwrites the directory
 *    that server reads from (HANDOVER.md). And it is `NEXT_DIST_DIR=.next-verify`, not a
 *    fresh name: `next dev` adds `<distDir>/types/**` to `tsconfig.json`'s `include` if it is
 *    missing, so any new directory would rewrite a checked-in file on every run;
 *    `.next-verify` is already listed and gitignored. The cost is that the e2e server and
 *    the verification build (`NEXT_DIST_DIR=.next-verify npm run build`) share a directory —
 *    do not run both at once.
 *
 * 2. `E2E_BASE_URL=http://host:port`: no `webServer`; the suite runs against that server.
 *    It must have been started with `NEXT_PUBLIC_AUTH_MODE=dev`, and with both
 *    `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SUPABASE_URL` equal to `E2E_API_URL` (default
 *    `http://127.0.0.1:8100`) — the fake tells API calls from the app's own by origin, and
 *    the source panel may frame only that origin; a mismatch fails every test with the calls
 *    it saw, or with the CSP refusing the frame.
 *    Nothing is running there → every `goto` fails with a connection error. Nothing passes.
 *
 * `E2E_BROWSER_CHANNEL=chrome` drives the installed Google Chrome instead of Playwright's
 * bundled Chromium (`npx playwright install chromium` fetches the latter; nothing here does).
 */
import { defineConfig, devices } from '@playwright/test'

import type { E2EOptions } from './e2e/support/test'

const DEV_SERVER_PORT = 3100
const DEV_SERVER_HOST = '127.0.0.1'
/** Nothing listens here. It exists so the app's build-time API origin is one the fake can claim. */
const DEFAULT_API_ORIGIN = 'http://127.0.0.1:8100'
/** Any well-formed id: the fake never reads the `X-Dev-Company` header it becomes. */
const E2E_COMPANY_ID = '11111111-1111-4111-8111-111111111111'

/** `next dev` compiles a route on its first request; the budgets below are for that, not for the app. */
const DEV_SERVER_START_MS = 180_000
const NAVIGATION_TIMEOUT_MS = 60_000
const TEST_TIMEOUT_MS = 90_000
/** Interactions and `expect` poll for this long. The audit's 2 px tab strip hung a click for the default five seconds; five is kept so that defect fails fast, not slowly. */
const ACTION_TIMEOUT_MS = 5_000

const externalServer = process.env.E2E_BASE_URL
const baseURL = externalServer ?? `http://${DEV_SERVER_HOST}:${DEV_SERVER_PORT}`
const apiOrigin = process.env.E2E_API_URL ?? DEFAULT_API_ORIGIN
const isCI = process.env.CI !== undefined

export default defineConfig<E2EOptions>({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: true,
  forbidOnly: isCI,
  retries: 0,
  // Two workers: the first request to each route compiles it, and four compiling at once on
  // a laptop is slower than two, twice.
  workers: isCI ? 1 : 2,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  timeout: TEST_TIMEOUT_MS,
  expect: { timeout: ACTION_TIMEOUT_MS },
  use: {
    baseURL,
    apiOrigin,
    actionTimeout: ACTION_TIMEOUT_MS,
    navigationTimeout: NAVIGATION_TIMEOUT_MS,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // The desktop artboards are drawn for this width (ADR-0060 measured at 1440×900).
        viewport: { width: 1440, height: 900 },
        channel: process.env.E2E_BROWSER_CHANNEL,
      },
    },
  ],
  webServer:
    externalServer !== undefined
      ? undefined
      : {
          command: `npx next dev --hostname ${DEV_SERVER_HOST} --port ${DEV_SERVER_PORT}`,
          url: `${baseURL}/login`,
          reuseExistingServer: false,
          timeout: DEV_SERVER_START_MS,
          stdout: 'ignore',
          stderr: 'pipe',
          env: {
            NEXT_DIST_DIR: '.next-verify',
            NEXT_PUBLIC_AUTH_MODE: 'dev',
            NEXT_PUBLIC_DEV_COMPANY_ID: E2E_COMPANY_ID,
            NEXT_PUBLIC_API_URL: apiOrigin,
            // The source panel frames the signed URL the API hands out, and the CSP frames
            // only 'self' and this origin. In dev auth mode nothing else reads it — there is
            // no Supabase client without NEXT_PUBLIC_AUTH_MODE=supabase — so the fake, which
            // hands out URLs on its own origin, is also the "Storage" that may be framed.
            NEXT_PUBLIC_SUPABASE_URL: apiOrigin,
          },
        },
})
